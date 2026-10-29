# Setup takes in a Pressless site already in a GitHub repository (PRESS-0218).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0218-take-in-github-site.md § 5. INV-10 lives in
# tests/test_publisher.py, beside fetch_previous's own tests.
#
# GitHub is a recording double that keeps what is published to it and serves
# it back, so the site a take-in reads is what a publish wrote rather than a
# hand copy (§ 7). It answers the setup doubles' other requests as
# tests/test_setup.py's do. Words the pages must carry are written out here,
# for the reason tests/test_setup.py gives.
from __future__ import annotations

import ast
import base64
import dataclasses
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from test_publisher import _blob_hash
from test_publishing import _settings
from test_setup import (
    _app,
    _next,
    _SignInGitHub,
    _step,
    _Store,
    _walk,
    _walk_to,
)
from test_setup import (
    _setup_page as _setup,
)

from pressless import (
    builder,
    files,
    photographs,
    publisher,
    publishing,
    settings,
    starter,
    store,
    takein,
)

KEY = "a-plain-test-key-for-take-in"
REPOSITORY = "/repos/owner/owner.github.io/"
FIRST_REFRESH = "ghr_plain-first"
SEED = {"CNAME": b"example.org\n"}
NOT_MADE_HERE = "Pressless did not make"
ALWAYS_SAID = ("Your drafts", "full-size photographs", "Daily Prompt filter")


class _Repository(_SignInGitHub):
    """GitHub, holding one repository, owner/owner.github.io, as commits.

    A publish's blob, tree, commit and reference writes are kept, and the
    reads answer from what is kept: the head, a commit, a tree by commit or
    tree sha, recursive or not, and a blob. A sha it does not hold is a 404.
    `commit_files` puts a commit holding exactly `files` on top of the head,
    as another computer's publish would. Everything else -- Pages, the
    sign-in, the repository's own record -- is tests/test_setup.py's double.
    """

    def __init__(self, files: dict[str, bytes] | None = None, **kwargs) -> None:
        super().__init__(taken="full", **kwargs)
        self.blobs: dict[str, bytes] = {}
        self.trees: dict[str, dict[str, str]] = {}
        self.commits: dict[str, tuple[str, str]] = {}   # sha -> (tree, parent)
        self.head = ""
        if files is not None:
            self.commit_files(files)

    def commit_files(self, files: dict[str, bytes]) -> str:
        tree = self._tree({path: self._blob(data) for path, data in files.items()})
        self.head = self._commit(tree, self.head)
        return self.head

    def holds(self, commit: str = "") -> dict[str, bytes]:
        """Every file at `commit`, or at the head."""
        tree = self.trees[self.commits[commit or self.head][0]]
        return {path: self.blobs[sha] for path, sha in tree.items()}

    def _blob(self, data: bytes) -> str:
        sha = _blob_hash(data)
        self.blobs[sha] = data
        return sha

    def _tree(self, paths: dict[str, str]) -> str:
        sha = hashlib.sha1(json.dumps(sorted(paths.items())).encode(),
                           usedforsecurity=False).hexdigest()
        self.trees[sha] = dict(paths)
        return sha

    def _commit(self, tree: str, parent: str) -> str:
        sha = hashlib.sha1(f"{tree} {parent} {len(self.commits)}".encode(),
                           usedforsecurity=False).hexdigest()
        self.commits[sha] = (tree, parent)
        return sha

    def request(self, method, url, body, headers):
        path = url.removeprefix(publisher.API)
        if not path.startswith(REPOSITORY) or path.startswith(REPOSITORY + "pages"):
            return super().request(method, url, body, headers)
        self.calls.append((method, url, headers.get("Authorization", "")))
        rest, _, query = path.removeprefix(REPOSITORY).partition("?")
        sent = json.loads(body) if body else {}
        if method == "GET" and rest.startswith("commits/"):
            sha = rest.removeprefix("commits/")
            sha = self.head if sha in ("HEAD", "main") else sha
            if not sha:
                return 409, {}, b'{"message": "Git Repository is empty."}'
            if sha not in self.commits:
                return 404, {}, b'{"message": "Not Found"}'
            tree, parent = self.commits[sha]
            return _json({"sha": sha, "parents": [{"sha": parent}] if parent else [],
                          "commit": {"tree": {"sha": tree}}})
        if method == "GET" and rest.startswith("git/trees/"):
            sha = rest.removeprefix("git/trees/")
            sha = self.commits[sha][0] if sha in self.commits else sha
            if sha not in self.trees:
                return 404, {}, b'{"message": "Not Found"}'
            return _json({"sha": sha, "truncated": False,
                          "tree": _listing(self.trees[sha], "recursive=1" in query)})
        if method == "GET" and rest.startswith("git/blobs/"):
            data = self.blobs.get(rest.removeprefix("git/blobs/"))
            if data is None:
                return 404, {}, b'{"message": "Not Found"}'
            return _json({"content": base64.b64encode(data).decode("ascii"),
                          "encoding": "base64"})
        if method == "POST" and rest == "git/blobs":
            return 201, {}, json.dumps(
                {"sha": self._blob(base64.b64decode(sent["content"]))}).encode()
        if method == "POST" and rest == "git/trees":
            paths = dict(self.trees[sent["base_tree"]])
            for entry in sent["tree"]:
                if entry["sha"] is None:
                    paths.pop(entry["path"], None)
                else:
                    paths[entry["path"]] = entry["sha"]
            return 201, {}, json.dumps({"sha": self._tree(paths)}).encode()
        if method == "POST" and rest == "git/commits":
            sha = self._commit(sent["tree"], sent["parents"][0])
            return 201, {}, json.dumps({"sha": sha}).encode()
        if method == "PATCH" and rest == "git/refs/heads/main":
            if self.commits[sent["sha"]][1] != self.head:
                return 422, {}, b'{"message": "Update is not a fast forward"}'
            self.head = sent["sha"]
            return _json({"object": {"sha": self.head}})
        return 404, {}, b'{"message": "Not Found"}'

    def repository_writes(self) -> list[tuple[str, str]]:
        """Every non-GET request naming the repository (INV-1)."""
        return [(method, path) for method, path in self.writes()
                if path.startswith(REPOSITORY.rstrip("/"))]


def _json(payload: dict) -> tuple[int, dict, bytes]:
    return 200, {}, json.dumps(payload).encode("utf-8")


def _listing(paths: dict[str, str], recursive: bool) -> list[dict]:
    if recursive:
        return [{"path": path, "type": "blob", "sha": sha} for path, sha in sorted(paths.items())]
    top = sorted({path.split("/")[0] for path in paths})
    return [{"path": name, "type": "blob" if name in paths else "tree"} for name in top]


def _picture(fmt: str, colour: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), colour).save(out, fmt)
    return out.getvalue()


ICON = "face.png"
PHOTOGRAPH = "seaside.jpg"
KEPT = "notes.txt"


def _published(tmp_path: Path, *, icon: bool = True) -> tuple[_Repository, Path]:
    """§ 7's fixture: a Store built from the starter, with a published entry
    and its comments, a forwards file, a photograph, a kept file and an icon,
    published into the double. The Store's folder comes back too."""
    folder = tmp_path / "published-from"
    folder.mkdir()
    starter.fill(folder, "A Journal")
    store.write_journal(folder, True)
    photographs.add(folder, PHOTOGRAPH, _picture("JPEG", "teal"))
    photographs.add(folder, ICON, _picture("PNG", "orange"))
    files.add(folder, KEPT, b"Plain words to keep.\n")
    index = store.html_path_for(folder, store.PAGES_FOLDER, "index")
    store.write_html(folder, store.PAGES_FOLDER, "index", store.read_html(index).replace(
        "<!-- pressless:page -->\n", "<!-- pressless:page -->\n<!-- pressless:download -->"
        f'<p class="pressless-download"><a href="files/{KEPT}" download>Notes</a></p>'
        '<!-- /pressless:download -->\n', 1))
    store.write(folder, store.Entry(
        slug="hello", title="Hello", date=datetime(2014, 11, 9, 21, 32), categories=(),
        tags=(), body=f"Words.\n\n{{photo: {PHOTOGRAPH} | The sea}}\n", extra=()),
        draft=False)
    store.write_comments(folder, "hello", (store.Comment(
        identifier="1", author="A reader", author_url="", date=datetime(2015, 3, 1, 9, 0),
        body="Lovely.", parent=""),))
    store.write_forwards(folder, {"old-hello": "hello"})
    store.write_identity(folder, store.Identity(
        "A Journal", "Words and pictures", icon=ICON if icon else ""))
    github = _Repository(SEED)
    publishing.publish(folder, _settings(folder), KEY, entry=None, transport=github)
    return github, folder


def _take_in(folder: Path, github: _Repository) -> takein.TakenIn:
    found = takein.look(folder, _settings(folder), KEY, transport=github)
    return takein.take_in(folder, _settings(folder), KEY, found.commit, transport=github)


def _held(folder: Path) -> dict[str, bytes]:
    """Every file in a folder § 4.3 writes into, by relative path."""
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob("*") if p.is_file() and p.parent != folder
            and p.relative_to(folder).parts[0] not in ("wizards", "bin", "fetch")}


def _empty_store(tmp_path: Path, name: str = "taken") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    return folder


# ----------------------------------------------------------------- INV-4 ---


def test_a_published_site_comes_back_whole(tmp_path):
    """INV-4. Breaks when a kind `_read` or the reconcile knows is skipped, or
    the take-in reads a second copy of `_read` that drifts."""
    github, _ = _published(tmp_path)
    folder = _empty_store(tmp_path)
    taken = _take_in(folder, github)
    held = github.holds()

    content = {path.removeprefix("content/"): data for path, data in held.items()
               if path.startswith("content/")}
    kinds = {path.split("/")[0] for path in content}
    assert {store.PUBLISHED_FOLDER, store.COMMENTS_FOLDER, store.PAGES_FOLDER,
            store.FURNITURE_FOLDER, store.FORWARDS_FOLDER, store.IDENTITY_FOLDER,
            store.LOOK_FOLDER} <= kinds, f"the fixture published only {sorted(kinds)}"
    identity_file = f"{store.IDENTITY_FOLDER}/{store.IDENTITY_FILE}"
    for path, data in content.items():
        if path != identity_file:
            assert (folder / path).read_bytes() == data, path
    published = store.read_identity(folder)
    assert published == store.Identity("A Journal", "Words and pictures",
                                       icon=builder.SITE_ICON)

    web_copies = {path.removeprefix("photographs/"): data for path, data in held.items()
                  if path.startswith("photographs/")}
    assert web_copies, "the fixture published no photograph"
    assert set(store.list_photographs(folder)) == {*web_copies, builder.SITE_ICON}
    for name, data in web_copies.items():
        assert store.photograph_path_for(folder, name).read_bytes() == data, name
    assert (store.photograph_path_for(folder, builder.SITE_ICON).read_bytes()
            == held[builder.SITE_ICON])

    kept = {path.removeprefix("files/"): data for path, data in held.items()
            if path.startswith("files/")}
    assert kept == {KEPT: b"Plain words to keep.\n"}
    assert {name: store.file_path_for(folder, name).read_bytes()
            for name in store.list_files(folder)} == kept

    assert taken.found.entries == 1 and taken.found.comments == 1
    assert taken.found.photographs == len(web_copies) and taken.found.files == 1
    assert taken.found.made_here and taken.found.left == ()


# ----------------------------------------------------------------- INV-8 ---


def test_the_icon_comes_back(tmp_path):
    """INV-8. Breaks when the identity keeps the old icon name, whose original
    is not in the repository, and the build stops."""
    github, _ = _published(tmp_path)
    assert f"photographs/{ICON}" not in github.holds(), "the original reached GitHub"
    folder = _empty_store(tmp_path)
    _take_in(folder, github)
    assert store.read_identity(folder).icon == builder.SITE_ICON
    site = tmp_path / "site"
    builder.build(folder, _settings(folder), site)
    assert (site / builder.SITE_ICON).is_file()


def test_an_icon_the_repository_lacks_is_dropped(tmp_path):
    """§ 4.3 step 3: an identity naming an icon over a repository holding no
    site-icon.png keeps no icon name, so the next build does not stop."""
    github, _ = _published(tmp_path)
    held = github.holds()
    del held[builder.SITE_ICON]
    github.commit_files(held)
    folder = _empty_store(tmp_path)
    _take_in(folder, github)
    assert store.read_identity(folder).icon == ""
    assert builder.SITE_ICON not in store.list_photographs(folder)
    builder.build(folder, _settings(folder), tmp_path / "site")


# ----------------------------------------------------------------- INV-3 ---


def test_a_take_in_needs_an_empty_store(tmp_path):
    """INV-3. Breaks when the check is dropped, or tested after the first
    write."""
    github, _ = _published(tmp_path)
    folder = _empty_store(tmp_path)
    store.write(folder, store.Entry(
        slug="mine", title="Mine", date=datetime(2020, 1, 1), categories=(), tags=(),
        body="His own.", extra=()), draft=True)
    found = takein.look(folder, _settings(folder), KEY, transport=github)
    before = _held(folder)
    with pytest.raises(takein.TakeInStopped):
        takein.take_in(folder, _settings(folder), KEY, found.commit, transport=github)
    assert _held(folder) == before


# ---------------------------------------------------------------- INV-11 ---


def _before_identities(tmp_path: Path) -> _Repository:
    """A site published before PRESS-0213: its identity file taken out."""
    github, _ = _published(tmp_path, icon=False)
    held = github.holds()
    del held[f"content/{store.IDENTITY_FOLDER}/{store.IDENTITY_FILE}"]
    github.commit_files(held)
    return github


def test_a_site_from_before_identities_comes_in(tmp_path, monkeypatch):
    """INV-11. Breaks when `made_here` reads the identity alone."""
    github = _before_identities(tmp_path)
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
        done = _next(browser, page)
    assert _step(done) is None and settings.path_for(folder).exists(), done
    assert store.list_slugs(folder, draft=False) == ("hello",)
    assert store.read_identity(folder) is None


# ----------------------------------------------------------------- INV-2 ---


def test_a_site_made_elsewhere_is_refused(tmp_path, monkeypatch):
    """INV-2. Breaks when `made_here` tests for a `content/` folder alone, or
    its second arm counts a file outside the Store's own layout."""
    github = _Repository({
        **SEED, "index.html": b"<html>Elsewhere</html>",
        "content/posts/hello.md": b"---\ntitle: Hello\n---\nWords.\n",
        "content/published/hello.md": b"Not a Store file.\n",
    }, pages="off")
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "pages")
        after = _next(browser, page)
    assert _step(after) == "pages" and NOT_MADE_HERE in after
    assert github.repository_writes() == []
    assert github.pages == "off"


# ----------------------------------------------------------------- INV-5 ---


def test_looking_writes_nothing(tmp_path, monkeypatch):
    """INV-5. Breaks when `look` fills the Store, or the site step's body
    does."""
    github, _ = _published(tmp_path)
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        before = _held(folder)
        page = _walk_to(browser, "site")
        assert "A Journal" in page
        assert _held(folder) == before
        browser.get()                             # shown again
        assert _held(folder) == before


# ----------------------------------------------------------------- INV-6 ---


def test_the_state_shown_is_the_state_taken(tmp_path, monkeypatch):
    """INV-6. Breaks when `take_in` calls `fetch_state` with no commit."""
    github, _ = _published(tmp_path)
    shown = github.holds()
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
        moved = dict(shown)
        moved["content/published/later.txt"] = moved["content/published/hello.txt"].replace(
            b"Slug: hello", b"Slug: later")
        github.commit_files(moved)
        done = _next(browser, page)
    assert _step(done) is None and settings.path_for(folder).exists(), done
    assert store.list_slugs(folder, draft=False) == ("hello",)


# ----------------------------------------------------------------- INV-7 ---


def test_a_failed_take_in_leaves_nothing(tmp_path, monkeypatch):
    """INV-7. Breaks when a write records no reversal, or a placed photograph
    is left behind."""
    github, _ = _published(tmp_path)
    keep = photographs.keep
    for failing in ("photograph", "settings"):
        folder = _empty_store(tmp_path, failing)
        _Store(monkeypatch)
        kept: list[str] = []

        # The fixture's photographs are the web copy and the icon, so the
        # second photograph placed is the last.
        def last_fails(path_for, data, named, kept=kept, failing=failing):
            photograph = path_for("x").parent.name == store.PHOTOGRAPHS_FOLDER
            if photograph and failing == "photograph" and len(kept) == 1:
                raise store.StoreError("the disk refused the last photograph")
            name = keep(path_for, data, named)
            if photograph:
                kept.append(name)
            return name

        def save_fails(*args, **kwargs):
            raise settings.SettingsError("the settings file could not be written")

        with monkeypatch.context() as patched, _setup(folder, github) as browser:
            page = _walk_to(browser, "site")
            before = _held(folder)
            patched.setattr(photographs, "keep", last_fails)
            if failing == "settings":
                patched.setattr(settings, "save", save_fails)
            after = _next(browser, page)
        assert _step(after) == "site", failing
        assert len(kept) == (1 if failing == "photograph" else 2), failing
        assert _held(folder) == before, failing
        assert not settings.path_for(folder).exists(), failing


# ----------------------------------------------------------------- INV-9 ---


def test_the_screen_says_what_stays_behind(tmp_path, monkeypatch):
    """INV-9. Breaks when a refused name is dropped without being listed."""
    github, _ = _published(tmp_path)
    left = ("photographs/old/beach.jpg", "files/old/notes.pdf",
            "content/posts/hello.md", "content/published/notes.md")
    github.commit_files({**github.holds(), **{path: b"left" for path in left}})
    folder = _empty_store(tmp_path, "setup")
    _Store(monkeypatch)
    with _setup(folder, github) as browser:
        page = _walk_to(browser, "site")
    found = takein.look(_empty_store(tmp_path, "looked"), _settings(folder), KEY,
                        transport=github)
    assert sorted(found.left) == sorted(left)
    for path in left:
        assert path in page, path
    for said in ALWAYS_SAID:
        assert said in page, said


# ----------------------------------------------------------------- INV-1 ---


def test_a_take_in_writes_nothing_to_github(tmp_path, monkeypatch):
    """INV-1. Breaks when any step adopts the repository by writing to it -- a
    `.nojekyll`, a starter, a publish."""
    from test_setup import _Clock
    github, _ = _published(tmp_path)
    github.calls.clear()                          # the fixture's own publish
    folder = _empty_store(tmp_path, "setup")
    _app(monkeypatch)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    with _setup(folder, github, clock=_Clock()) as browser:
        seen, done = _walk(browser)
    assert seen[-3:] == ["repository", "pages", "site"], seen
    assert _step(done) is None and settings.path_for(folder).exists(), done
    assert store.list_slugs(folder, draft=False) == ("hello",)
    assert github.repository_writes() == []
    assert [write for write in github.writes() if write[1].startswith("/")] == [
        ("POST", "/user/repos")]


# ---------------------------------------------------------------- INV-12 ---


def test_only_a_take_in_deletes_a_photograph(tmp_path):
    """INV-12. Breaks when another module deletes a photograph through it."""
    source = Path(takein.__file__).parent
    callers = set()
    for path in source.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr == "unplace_photograph":
                callers.add(path.name)
            if isinstance(node, ast.Name) and node.id == "unplace_photograph":
                callers.add(path.name)
    assert callers == {"takein.py"}
    folder = _empty_store(tmp_path)
    name = photographs.add(folder, PHOTOGRAPH, _picture("JPEG", "teal"))
    with pytest.raises(store.StoreError):
        store.move_to_bin(folder, store.photograph_path_for(folder, name))
    store.unplace_photograph(folder, name)
    assert store.list_photographs(folder) == ()


def test_found_counts_what_came_across(tmp_path):
    """§ 4.2's counts, which the site step and the done page show."""
    github, published = _published(tmp_path)
    found = takein.look(_empty_store(tmp_path), _settings(published), KEY, transport=github)
    assert dataclasses.replace(found, commit="", left=()) == takein.Found(
        commit="", made_here=True, entries=1,
        pages=len(store.list_html(published, store.PAGES_FOLDER)), comments=1,
        photographs=1, files=1, identity=store.read_identity(published), left=())
