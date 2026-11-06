# Setup takes over a site GitHub Actions builds, in the same repository
# (PRESS-0333). Each test names the invariant it holds, from
# docs/specs/PRESS-0333-take-over-actions-site.md § 5. INV-10 and INV-11 live in
# tests/test_importer_fetch.py, beside the fetches they share.
#
# GitHub is tests/test_takein.py's recording double, with GitHub Pages built by
# Actions. The live site is a fake network behind fetch's resolver and connection,
# so the test sees each address asked for. Words the pages must carry are written
# out here, for the reason tests/test_setup.py gives.
from __future__ import annotations

import base64
import contextlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_importer_fetch import GLOBAL, _Answer, _Network
from test_publishing import _entry, _settings
from test_setup import (
    _Browser,
    _next,
    _step,
    _Store,
    _walk_to,
)
from test_setup import (
    _setup_page as _setup,
)
from test_takein import KEY, REPOSITORY, _empty_store, _picture, _published, _Repository

import pressless_import
from pressless import (
    builder,
    editor,
    face,
    publisher,
    publishing,
    settings,
    setup,
    store,
    takein,
    takeover,
    undo,
)
from pressless_import import fetch

HOST = "owner.github.io"
SITE = f"https://{HOST}/"
BUILD = ".github/workflows/deploy.yml"
BUILD_TEXT = b"jobs:\n  deploy:\n    steps:\n      - uses: actions/deploy-pages@v4\n"
OTHER = ".github/workflows/test.yml"
SOURCE = {BUILD: BUILD_TEXT, OTHER: b"jobs: {}\n", "package.json": b"{}\n",
          "src/index.md": b"# Home\n", "content/post.md": b"# A post\n"}
FRONT = (b'<html><head><title>Built Site</title><link rel="stylesheet" href="/style.css">'
         b'</head><body><h1>Home</h1><a href="/about/">About</a>'
         b'<img src="https://owner.github.io/pic.png" alt=""></body></html>')
ABOUT = b"<html><head><title>About</title></head><body><p>About us</p></body></html>"
PAGES_ANSWERS = {"/": FRONT, "/about/": ABOUT, "/style.css": b"body { color: red; }",
                 "/pic.png": _picture("PNG", "teal")}


class _Built(_Repository):
    """_Repository whose Pages is built by Actions until a `PUT pages` says otherwise."""

    def __init__(self, files: dict[str, bytes] | None = None, *, cname: str | None = None,
                 build: str = "workflow", branch: str = "main", **kwargs) -> None:
        super().__init__(SOURCE if files is None else files, **kwargs)
        self.build, self.cname, self.branch = build, cname, branch
        self.sent_pages: dict | None = None
        self.refuse_switch = self.refuse_publish = False
        self.tree_paths: list[str] = []

    def request(self, method, url, body, headers):
        path = url.removeprefix(publisher.API)
        if method == "POST" and path == f"{REPOSITORY}git/trees":
            self.tree_paths += [entry["path"] for entry in json.loads(body)["tree"]]
        if self.refuse_publish and method == "PATCH" and path.endswith("git/refs/heads/main"):
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 403, {}, b'{"message": "refused"}'
        if method == "POST" and path == f"{REPOSITORY}pages/builds":
            # GitHub's "request a GitHub Pages build": 201, the build queued.
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 201, {}, b'{"status": "queued"}'
        if path == f"{REPOSITORY}pages":
            self.calls.append((method, url, headers.get("Authorization", "")))
            if method == "PUT":
                if self.refuse_switch:
                    return 403, {}, b'{"message": "refused"}'
                self.sent_pages = json.loads(body)
                self.build = self.sent_pages["build_type"]
                self.cname = self.sent_pages.get("cname", self.cname)
                return 204, {}, b""
            return 200, {}, json.dumps({
                "html_url": SITE, "build_type": self.build, "cname": self.cname,
                "source": {"branch": self.branch, "path": "/"}}).encode()
        if method == "GET" and path == f"{REPOSITORY}contents/CNAME":
            self.calls.append((method, url, headers.get("Authorization", "")))
            held = self.holds().get("CNAME")
            if held is None:
                return 404, {}, b'{"message": "Not Found"}'
            return 200, {}, json.dumps({
                "sha": "cname-sha", "encoding": "base64",
                "content": base64.b64encode(held).decode("ascii")}).encode()
        return super().request(method, url, body, headers)

    def remove(self, path: str = BUILD) -> None:
        """The person presses GitHub's delete button."""
        self.commit_files({name: data for name, data in self.holds().items() if name != path})


class _Answers(dict):
    """A live site: each ask gets a fresh answer, and an unknown address a 404."""

    def __missing__(self, key):
        return _Answer(404)


def _site(monkeypatch: pytest.MonkeyPatch, pages: dict[str, bytes] | None = None) -> _Network:
    answers = _Answers()
    served = PAGES_ANSWERS if pages is None else pages

    class Live(_Network):
        def connect(self, address, host, port, secure):
            answers.clear()
            for path, data in served.items():
                kind = "text/css" if path.endswith(".css") else "text/html"
                answers[f"{HOST}{path}"] = _Answer(200, data, {"Content-Type": kind})
            return super().connect(address, host, port, secure)

    network = Live({HOST: [GLOBAL]}, answers)
    monkeypatch.setattr(fetch, "_resolve", network.resolve)
    monkeypatch.setattr(fetch, "_connect", network.connect)
    return network


def _finished(tmp_path: Path, monkeypatch, github: _Built) -> Path:
    """Setup walked to its end over a site Actions builds."""
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        done = _next(browser, _walk_to(browser, "site"))
    assert _step(done) is None and settings.path_for(folder).exists(), done
    return folder


@contextlib.contextmanager
def _pressing(folder: Path, github: _Built) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=github)
        setup.register(served, folder, transport=github)
        yield _Browser(served)
    finally:
        served.stop()


def _shown(folder: Path, github: _Built) -> str:
    with _pressing(folder, github) as browser:
        return browser.request("GET", publishing.TAKEOVER_ADDRESS)[2]


def _press(folder: Path, github: _Built) -> str:
    with _pressing(folder, github) as browser:
        return browser.post({}, path=publishing.TAKEOVER_ADDRESS)[1]


def _held(folder: Path) -> dict[str, bytes]:
    """The Store, without what setup and the wizard keep beside it."""
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*")
            if p.is_file() and p.parent != folder
            and p.relative_to(folder).parts[0] not in ("wizards", "bin", "fetch", "import")}


# ----------------------------------------------------------------- INV-1 ---


def test_setup_writes_nothing_to_github(tmp_path, monkeypatch):
    """INV-1. Breaks when `check_pages` falls through to `switch_pages_on`."""
    _site(monkeypatch)
    github = _Built()
    folder = _finished(tmp_path, monkeypatch, github)
    assert github.repository_writes() == []
    assert github.build == "workflow"
    assert {"index", "about"} <= set(store.list_html(folder, store.PAGES_FOLDER))
    assert takeover.owed(folder)
    saved = settings.load(folder)
    assert saved.site_address == SITE.rstrip("/") or saved.site_address == SITE


# ----------------------------------------------------------------- INV-2 ---


@pytest.mark.parametrize(("github", "pages", "said"), [
    (lambda: _Built(build="legacy", branch="gh-pages"), None, "choose a different, new repository"),
    (lambda: _Built({**SOURCE, BUILD: b"jobs: {}\n"}), None, "choose a different, new repository"),
    (lambda: _Built(), {}, "could not read its front page"),
], ids=("a-branch-build", "no-deploy-step", "front-page-404"))
def test_what_cannot_be_taken_over_is_refused(tmp_path, monkeypatch, github, pages, said):
    """INV-2. Breaks when `built_by_actions` alone opens the way, or a failed front
    page goes on with no pages. The last fixture fails only the front page: its
    repository is built by Actions and names `BUILD_MARK`."""
    _site(monkeypatch, pages)
    double = github()
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, double) as browser:
        after = _next(browser, _walk_to(browser, "pages"))
    assert _step(after) == "pages", after
    assert said in after
    assert double.repository_writes() == []
    assert not (folder / pressless_import.IMPORT_FOLDER / pressless_import.FOLDER).exists()


# ----------------------------------------------------------------- INV-3 ---


def test_the_screen_says_what_will_change(tmp_path, monkeypatch):
    """INV-3. Breaks when a row is dropped, or the body writes to the Store."""
    _site(monkeypatch)
    github = _Built(cname="www.example.org")
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
    for words in ("GitHub Pages switches", BUILD, "stays in the repository&#x27;s history",
                  "Any other file in .github/workflows stays", "www.example.org",
                  "the old site stays up", ".nojekyll", "CNAME",
                  "only what a link reaches", "builds in the browser"):
        assert words in page or words.replace("&#x27;", "'") in page, words
    assert OTHER not in page
    assert _held(folder) == {}, "the step's body wrote to the Store"
    assert github.repository_writes() == []


def test_the_screen_says_a_stale_cname_goes(tmp_path, monkeypatch):
    """§ 4.4: a `CNAME` with no domain behind it is named before anything changes."""
    _site(monkeypatch)
    github = _Built({**SOURCE, "CNAME": b"old.example.org\n"})
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
    assert "names a domain this site does not use" in page


# ----------------------------------------------------------------- INV-4 ---


def _publishable(tmp_path: Path) -> tuple[_Repository, Path]:
    """A published site with an earlier state to undo to, owing a takeover."""
    github, folder = _published(tmp_path)
    store.write(folder, _entry("second"), draft=False)
    publishing.publish(folder, _settings(folder), KEY, entry=None, transport=github)
    takeover.mark(folder, (BUILD,))
    return github, folder


@pytest.mark.parametrize("route", ("entry", "site", "undo"))
def test_no_publish_passes_the_marker(tmp_path, monkeypatch, route):
    """INV-4, through each way out. Breaks when the guard sits in `_pressed` alone."""
    github, folder = _publishable(tmp_path)
    store.write(folder, _entry("waiting"), draft=True)
    built: list[Path] = []
    monkeypatch.setattr(builder, "build", lambda *args, **kwargs: built.append(args[0]))
    github.calls.clear()
    with pytest.raises(publishing.TakeoverOwed):
        if route == "entry":
            publishing.publish(folder, _settings(folder), KEY, entry="waiting", transport=github)
        elif route == "site":
            publishing.publish(folder, _settings(folder), KEY, entry=None, transport=github)
        else:
            undo.undo(folder, _settings(folder), KEY, transport=github)
    assert built == []
    assert github.repository_writes() == []
    assert store.list_slugs(folder, draft=True) == ("waiting",), "the moved entry was not put back"


def test_the_refusal_links_to_the_takeover():
    """§ 4.5: the way on, beside the failure, as a replace has."""
    link = publishing.replace_link(publishing.TakeoverOwed("owed"))
    assert f'href="{publishing.TAKEOVER_ADDRESS}"' in link


# ----------------------------------------------------------------- INV-5 ---


def test_a_file_still_there_stops_it(tmp_path, monkeypatch):
    """INV-5. Breaks when the list is read once, from setup's answers."""
    _site(monkeypatch)
    github = _Built()
    folder = _finished(tmp_path, monkeypatch, github)
    before = settings.load(folder)
    shown = _shown(folder, github)
    link = "https://github.com/owner/owner.github.io/delete/main/.github/workflows/deploy.yml"
    assert f'href="{link}"' in shown
    assert 'target="_blank"' in shown and "Commit changes" in shown
    github.calls.clear()
    pressed = _press(folder, github)
    assert "still in the repository" in pressed
    assert github.repository_writes() == []
    assert settings.load(folder) == before
    assert takeover.owed(folder)


# ----------------------------------------------------------------- INV-6 ---


def test_the_switch_follows_the_publish(tmp_path, monkeypatch):
    """INV-6. Breaks when Pages is switched first, which serves the tool's source, or
    when no build is asked for after the switch: GitHub builds a branch site only on
    a commit, so the old site stayed up until the next publish (hand check,
    2026-11-03)."""
    _site(monkeypatch)
    github = _Built()
    folder = _finished(tmp_path, monkeypatch, github)
    github.remove()
    github.calls.clear()
    _press(folder, github)
    writes = [(method, path.removeprefix(REPOSITORY))
              for method, path in github.repository_writes()]
    assert writes.index(("PATCH", "git/refs/heads/main")) < writes.index(
        ("PUT", "contents/.nojekyll")) < writes.index(("PUT", "pages"))
    assert writes[-1] == ("POST", "pages/builds"), writes
    assert github.sent_pages["build_type"] == "legacy"
    assert github.sent_pages["source"] == {"branch": "main", "path": "/"}
    assert "index.html" in github.holds()
    assert not takeover.owed(folder)


# ----------------------------------------------------------------- INV-7 ---


@pytest.mark.parametrize("held", (None, b"old.example.org\n"), ids=("absent", "stale"))
def test_the_domain_stays(tmp_path, monkeypatch, held):
    """INV-7. Breaks when the two files miss `untouchable`, or `cname` goes null."""
    _site(monkeypatch)
    files = {**SOURCE, **({"CNAME": held} if held else {})}
    github = _Built(files, cname="www.example.org")
    folder = _finished(tmp_path, monkeypatch, github)
    github.remove()
    _press(folder, github)
    assert github.sent_pages["cname"] == "www.example.org"
    assert github.holds()["CNAME"].strip() == b"www.example.org"
    store.write(folder, _entry("later"), draft=False)
    saved = settings.load(folder)
    publishing.publish(folder, saved, KEY, entry=None, transport=github)
    assert github.holds()["CNAME"].strip() == b"www.example.org"
    assert ".nojekyll" in github.holds()


def test_a_stale_cname_goes_before_the_switch(tmp_path, monkeypatch):
    """INV-7: with no domain, a branch build would read the old file as the domain."""
    _site(monkeypatch)
    github = _Built({**SOURCE, "CNAME": b"old.example.org\n"})
    folder = _finished(tmp_path, monkeypatch, github)
    github.remove()
    _press(folder, github)
    assert "CNAME" not in github.holds()
    assert "cname" not in github.sent_pages, "null removes a domain, and omitting it is the rule"


def test_a_re_point_by_hand_keeps_the_files(tmp_path, monkeypatch):
    """INV-7 and § 6: the switch was made elsewhere, so the marker goes, and a later
    publish still leaves `CNAME` alone."""
    _site(monkeypatch)
    github = _Built(cname="www.example.org")
    folder = _finished(tmp_path, monkeypatch, github)
    github.remove()
    github.build = "legacy"
    github.commit_files({**github.holds(), "CNAME": b"www.example.org\n"})
    github.calls.clear()
    pressed = _press(folder, github)
    assert "already been changed" in pressed
    assert github.repository_writes() == []
    assert not takeover.owed(folder)
    publishing.publish(folder, settings.load(folder), KEY, entry=None, transport=github)
    assert "CNAME" in github.holds()


# ----------------------------------------------------------------- INV-8 ---


def test_a_failure_can_be_pressed_again(tmp_path, monkeypatch):
    """INV-8. Breaks when the marker goes before the switch."""
    _site(monkeypatch)
    github = _Built()
    folder = _finished(tmp_path, monkeypatch, github)
    github.remove()

    head = github.head
    github.refuse_publish = True
    _press(folder, github)
    github.refuse_publish = False
    assert github.head == head and github.sent_pages is None and takeover.owed(folder)

    github.refuse_switch = True
    pressed = _press(folder, github)
    assert "not yet on the web" in pressed
    assert takeover.owed(folder) and github.build == "workflow"
    head = github.head

    github.refuse_switch = False
    github.calls.clear()
    pressed = _press(folder, github)
    assert github.build == "legacy" and not takeover.owed(folder)
    assert github.head == head, "the second press made a new commit"
    assert "earlier press" in pressed


# ----------------------------------------------------------------- INV-9 ---


def test_nothing_writes_a_workflow_file(tmp_path, monkeypatch):
    """INV-9. Breaks when `.github` leaves `untouchable`."""
    _site(monkeypatch)
    github = _Built()
    folder = _finished(tmp_path, monkeypatch, github)
    github.remove()
    github.calls.clear()
    _press(folder, github)
    assert github.holds()[OTHER] == SOURCE[OTHER]
    assert BUILD not in github.holds()
    assert github.tree_paths and not [path for path in github.tree_paths if ".github" in path]
    assert not [path for _method, path in github.repository_writes() if "contents/.github" in path]
    assert ".github" in settings.load(folder).untouchable


# ---------------------------------------------------------------- INV-12 ---


def test_the_screen_lists_only_what_is_there(tmp_path, monkeypatch):
    """Breaks when the screen leads into a list it does not show, ties a downloaded
    file to the repository's list, or says Pressless adds a CNAME already there --
    each seen on 2026-11-03 over a real Jekyll site, whose root Pressless leaves alone."""
    front = FRONT + b'<a href="/feed.xml">Feed</a>'
    _site(monkeypatch, {**PAGES_ANSWERS, "/": front, "/feed.xml": b"<feed></feed>"})
    github = _Built({BUILD: BUILD_TEXT, "_config.yml": b"theme: minima\n",
                     "index.md": b"# Home\n", "CNAME": b"www.example.org\n"},
                    cname="www.example.org")
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
    assert "feed.xml" in page
    assert "will then change these on GitHub" not in page    # an empty list followed
    assert "Among those" not in page                         # feed.xml is not among them
    assert "adds a file, CNAME" not in page


def test_what_was_not_read_is_named(tmp_path, monkeypatch):
    """INV-12. Breaks when `Crawled.left` is not written to import/folder-left.json."""
    # A small cap: 50 MB through the fake network ran near the client's timeout.
    monkeypatch.setattr(builder, "FILE_LARGEST", 64 * 1024)
    front = FRONT + b'<a href="/gone/">Gone</a><a href="/big.pdf">Big</a>'
    _site(monkeypatch, {**PAGES_ANSWERS, "/": front,
                        "/big.pdf": b"x" * (builder.FILE_LARGEST + 1)})
    github = _Built()
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
        assert "gone/" in page and "big.pdf" in page, page
        done = _next(browser, page)
    assert "gone/" in done and "big.pdf" in done, done


# ---------------------------------------------------------------- INV-13 ---


def test_finish_writes_what_was_shown(tmp_path, monkeypatch):
    """INV-13. Breaks when `bring_folder` lays out by `look_folder`, or the marker is
    written after the save."""
    network = _site(monkeypatch)
    github = _Built()
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
        network.requests.clear()
        done = _next(browser, page)
    assert network.requests == [], "Finish downloaded the site again"
    assert _step(done) is None and takeover.owed(folder)


def test_a_folder_gone_is_downloaded_again(tmp_path, monkeypatch):
    """INV-13: `bring_folder` lays it out again from the site, never the repository."""
    network = _site(monkeypatch)
    github = _Built()
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
        takein.forget_folder(folder)
        network.requests.clear()
        done = _next(browser, page)
    assert network.requests, "nothing was downloaded"
    assert _step(done) is None
    assert "about" in store.list_html(folder, store.PAGES_FOLDER)


def test_a_second_press_downloads_nothing_and_keeps_the_marker(tmp_path, monkeypatch):
    """INV-13: a failed Settings save is retried with no second bring."""
    network = _site(monkeypatch)
    github = _Built()
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    real_save = settings.save
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")

        def save_fails(*args, **kwargs):
            raise settings.SettingsError("repository", "the save failed")

        monkeypatch.setattr(settings, "save", save_fails)
        failed = _next(browser, page)
        assert not settings.path_for(folder).exists(), failed
        assert takeover.owed(folder), "the marker must land before the save"
        monkeypatch.setattr(settings, "save", real_save)
        network.requests.clear()
        done = _next(browser, browser.get()[1])
    assert network.requests == []
    assert _step(done) is None and settings.path_for(folder).exists(), done
    assert takeover.owed(folder)


# ---------------------------------------------------------------- INV-14 ---


def test_the_report_says_what_changed(tmp_path, monkeypatch):
    """INV-14. Breaks when the POST redirects to the list."""
    _site(monkeypatch)
    github = _Built(cname="www.example.org")
    folder = _finished(tmp_path, monkeypatch, github)
    with _pressing(folder, github) as browser:
        assert "still comes from GitHub" in browser.request("GET", "/")[2]
    github.remove()
    pressed = _press(folder, github)
    for words in ("GitHub Pages switched", BUILD, "www.example.org", ".nojekyll", "CNAME",
                  "uploaded", "few minutes"):
        assert words in pressed, words
    assert not takeover.owed(folder)
    with _pressing(folder, github) as browser:
        assert "still comes from GitHub" not in browser.request("GET", "/")[2]


def test_the_marker_moves_with_the_site():
    """§ 4.3: a site opened from a file still owes the takeover."""
    from pressless import sitefile, sites
    assert takeover.MARKER in sites.SITE_NAMES and takeover.MARKER in sitefile.KEPT


# ---------------------------------------------------------------- INV-15 ---


def test_names_are_escaped(tmp_path, monkeypatch):
    """INV-15. Breaks when a name is written raw into the link or the list."""
    _site(monkeypatch)
    odd = ".github/workflows/a&'b x.yml"
    github = _Built({**SOURCE, odd: BUILD_TEXT, BUILD: b"jobs: {}\n"}, cname="a<b.example.org")
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
        assert "a<b.example.org" not in page and "a&lt;b.example.org" in page
        assert "a&'b x.yml" not in page and "a&amp;&#x27;b x.yml" in page
        done = _next(browser, page)
    assert _step(done) is None, done
    shown = _shown(folder, github)
    assert "workflows/a%26%27b%20x.yml" in shown
    assert "a<b.example.org" not in shown and "a&'b x.yml" not in shown


# ------------------------------------------------- the Publisher's own part ---


def test_a_204_from_put_pages_is_an_answer(tmp_path):
    """§ 4.5: GitHub documents 204, which the session raised on before this."""
    github = _Built()
    pages = publisher.switch_pages_to_branch("owner/owner.github.io", KEY, None, github)
    assert github.build == "legacy" and pages.on


def test_pages_reads_the_build_and_the_domain():
    pages = publisher.pages("owner/owner.github.io", KEY, _Built(cname="www.example.org"))
    assert pages.built_by_actions and pages.domain == "www.example.org" and not pages.serves_root
    branch_built = publisher.pages("owner/owner.github.io", KEY, _Built(build="legacy"))
    assert not branch_built.built_by_actions


def test_build_files_are_those_naming_the_deploy_action(tmp_path):
    github = _Built({**SOURCE, ".github/workflows/deep/x.yml": BUILD_TEXT,
                     ".github/workflows/notes.txt": BUILD_TEXT})
    folder = _empty_store(tmp_path)
    assert takeover.build_files(folder, _settings(folder), KEY, github) == (BUILD,)
    area = folder / undo.FETCH_FOLDER
    assert not area.exists() or not any(area.iterdir())


# ------------------------------------------------------------- PRESS-0339 ---

# The takeover form's script under node: a stand-in form, button and line.
_NODE = shutil.which("node")
_WORKING_HARNESS = """const on = {};
const button = {disabled: false};
const line = {textContent: ""};
const form = {addEventListener: (kind, run) => { on[kind] = run; },
              querySelector: (selector) => selector === "button" ? button : line};
const document = {currentScript: {previousElementSibling: form}};
const say = (key) => "<" + key + ">";
%s
on.submit();
const said = line.textContent;
setTimeout(() => process.stdout.write(JSON.stringify({said, disabled: button.disabled})), 10);
"""


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_the_takeover_says_publishing_the_instant_it_is_pressed(tmp_path, monkeypatch):
    """PRESS-0339: the page sat unchanged for about a minute while it
    published. Breaks when the form posts without saying so, or its button
    stays live for a second press."""
    _site(monkeypatch)
    github = _Built()
    folder = _finished(tmp_path, monkeypatch, github)
    shown = _shown(folder, github)
    form = re.search(rf'<form method="post" action="{publishing.TAKEOVER_ADDRESS}".*?</form>'
                     r"<script>(.*?)</script>", shown, re.S)
    assert form, "the takeover form carries no script"
    assert 'role="status"' in form.group(0)
    harness = tmp_path / "working.js"
    harness.write_text(_WORKING_HARNESS % form.group(1), encoding="utf-8")
    run = subprocess.run([_NODE, str(harness)], capture_output=True,  # noqa: S603
                         check=True, timeout=30)
    assert json.loads(run.stdout) == {"said": "<script.press.publishing>", "disabled": True}

