# Setup: the publishing key once, and the same page as Settings (PRESS-0021).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0021-setup.md
# § 5. Words and names the page must carry are written out here rather than
# imported from setup.py: shared, they would compare the module against itself
# (the trap CLAUDE.md records for test_settings.py).
#
# Every server is started inside the test that uses it, never in a fixture, so
# a red run against a stub fails in the test body for the stub's reason. The
# credential store is always a recording double: Windows CI refuses the file
# store, and no test may touch the machine's real keyring (spec § 5).
from __future__ import annotations

import contextlib
import dataclasses
import inspect
import json
import re
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser

from pressless import (
    builder,
    credentials,
    editor,
    face,
    github_setup,
    github_signin,
    publisher,
    settings,
    setup,
    shortcuts,
    starter,
    store,
)

KEY_NOUN = "your publishing key"
SENTINEL_KEY = "ghp_SENTINELkey0123456789abcdef"
LOG_NAME = "pressless.log"

ROOT = ("CNAME", "assets", "content", "index.html")
DERIVED = ("CNAME", "assets")

ADDRESS = "https://example.org"

ANSWERS = {
    "repository": "owner/owner.github.io",
    "site_name": "A Journal",
    "site_address": ADDRESS,
    "daily_prompt_filter": "",
    "key": SENTINEL_KEY,
}


class _GitHub:
    """A recording double for the Publisher's Transport, answering by URL.

    `refuse` maps a URL substring to the status that address answers with.
    Everything else answers as a public repository `owner/owner.github.io`
    whose root holds `root`, under the account `owner`. `pages` is "root"
    (on, serving the main branch's root), "elsewhere" (on, serving /docs) or
    "off"; switching it on makes it "root" (PRESS-0212 § 4.5).
    """

    def __init__(self, root: tuple[str, ...] = ROOT, refuse: dict[str, int] | None = None,
                 pages: str = "root"):
        self.root = root
        self.refuse = refuse or {}
        self.pages = pages
        self.calls: list[tuple[str, str, str]] = []

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((method, url, headers.get("Authorization", "")))
        for fragment, status in self.refuse.items():
            if fragment in url:
                return status, {}, b'{"message": "refused"}'
        path = url.removeprefix(publisher.API)
        if method == "GET" and path == "/users/owner":
            return 200, {}, b'{"login": "owner"}'
        if method == "GET" and path == "/repos/owner/owner.github.io":
            return 200, {}, b'{"default_branch": "main", "private": false}'
        if path == "/repos/owner/owner.github.io/pages":
            if method == "POST":
                self.pages = "root"
                return 201, {}, b"{}"
            if self.pages == "off":
                return 404, {}, b'{"message": "Not Found"}'
            source = {"branch": "main", "path": "/docs" if self.pages == "elsewhere" else "/"}
            return 200, {}, json.dumps({"html_url": ADDRESS, "build_type": "legacy",
                                        "source": source}).encode()
        if method == "PUT" and path.endswith("/contents/.nojekyll"):
            return 201, {}, b'{"commit": {"sha": "c1"}}'
        if url.endswith("/commits/HEAD"):
            return 200, {}, json.dumps({"sha": "abc123"}).encode()
        if "/git/trees/abc123" in url:
            tree = [{"path": name, "type": "blob"} for name in self.root]
            return 200, {}, json.dumps({"tree": tree}).encode()
        return 404, {}, b'{"message": "Not Found"}'

    def wait(self, seconds: float) -> None:
        return None

    def writes(self) -> list[tuple[str, str]]:
        return [(method, url.removeprefix(publisher.API))
                for method, url, _auth in self.calls if method != "GET"]


class _Store:
    """Recording doubles for credentials.choose, read and write."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, answers: str = "keyring",
                 saved_key: str = SENTINEL_KEY,
                 choose_raises: Exception | None = None,
                 read_raises: Exception | None = None,
                 write_raises: Exception | None = None) -> None:
        self.chosen = 0
        self.reads: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str, str]] = []

        def choose() -> credentials.Choice:
            self.chosen += 1
            if choose_raises is not None:
                raise choose_raises
            return credentials.Choice(answers, f"{answers} double")

        def read(kind: str, folder: Path, account: str) -> str:
            self.reads.append((kind, account))
            if read_raises is not None:
                raise read_raises
            return saved_key

        def write(kind: str, folder: Path, account: str, secret: str) -> None:
            if write_raises is not None:
                raise write_raises
            self.writes.append((kind, account, secret))

        monkeypatch.setattr(credentials, "choose", choose)
        monkeypatch.setattr(credentials, "read", read)
        monkeypatch.setattr(credentials, "write", write)


class _Browser(Browser):
    def get(self) -> tuple[int, str]:
        status, _, page = self.request("GET", "/setup")
        return status, page

    def post(self, answers: dict[str, str], *, cookie: bool = True,
             origin: str | None = "own", path: str = "/setup") -> tuple[int, str]:
        status, _, page = self.request("POST", path, answers, cookie=cookie, origin=origin)
        return status, page


@contextlib.contextmanager
def _setup_page(folder: Path, github: _GitHub,
                places: shortcuts.Places | None = None,
                clock: _Clock | None = None) -> Iterator[_Browser]:
    """With `clock`, the GitHub pass is registered too (PRESS-0231), over the
    same double."""
    served = face.serve(folder)
    try:
        setup.register(served, folder, transport=github, shortcut_places=lambda: places)
        if clock is not None:
            github_setup.register(served, folder, transport=github, clock=clock)
        yield _Browser(served)
    finally:
        served.stop()


def _answers(**changes: str) -> dict[str, str]:
    return {**ANSWERS, **changes}


# PRESS-0212: first run is a wizard. These walk it as a person would.

FIRST_RUN = {"account": "owner", "repository": "owner.github.io", "key": SENTINEL_KEY,
             "site_name": "A Journal", "site_description": "", "start": ""}
STEP_FIELDS = {"welcome": (), "account": ("account",), "repository": ("repository",),
               "key": ("key",), "pages": (), "site": ("site_name", "site_description", "start"),
               "signin": (), "install": ()}


def _step(page: str) -> str | None:
    """The wizard step a page shows, or None for a page that is no step."""
    found = re.search(r'name="step" value="([a-z]+)"', page)
    return found.group(1) if found else None


def _next(browser: _Browser, page: str, **changes: str) -> str:
    """Press Next on the step `page` shows, with FIRST_RUN's answers."""
    step = _step(page)
    assert step is not None, "not a wizard step"
    answers = {**FIRST_RUN, **changes}
    return browser.post({"step": step, "go": "next",
                         **{name: answers[name] for name in STEP_FIELDS[step]}})[1]


def _first_run(browser: _Browser, **changes: str) -> str:
    """Walk the wizard from where it stands until a step does not move on, or
    the wizard ends; the last page."""
    page = browser.get()[1]
    while _step(page) is not None:
        after = _next(browser, page, **changes)
        if _step(after) == _step(page):
            return after
        page = after
    return page


def _walk_to(browser: _Browser, step: str, **changes: str) -> str:
    """Walk the wizard to `step`'s page, from where it stands."""
    page = browser.get()[1]
    while _step(page) != step:
        assert _step(page) is not None, f"the wizard ended before {step}"
        after = _next(browser, page, **changes)
        assert _step(after) != _step(page), f"the wizard stayed on {_step(page)}"
        page = after
    return page


def _saved(folder: Path, **changes) -> settings.Settings:
    """Save a settings file in `folder`, as an earlier setup would have."""
    value = settings.Settings(
        site_folder=folder / "site",
        repository="owner/owner.github.io",
        site_address="https://example.org",
        daily_prompt_filter="",
        untouchable=DERIVED,
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None,
    )
    value = dataclasses.replace(value, **changes)
    settings.save(folder, value)
    return value


def _settings_file(folder: Path) -> Path:
    return folder / "settings.json"


def _offers_the_form(page: str) -> bool:
    return 'name="repository"' in page


def _hint_for(field: str, page: str) -> bool:
    return f'id="{field}-hint"' in page


def _key_inputs(page: str) -> list[str]:
    return re.findall(r"<input[^>]*name=\"key\"[^>]*>", page)


def _log(folder: Path) -> str:
    target = folder / LOG_NAME
    return target.read_text(encoding="utf-8") if target.exists() else ""


# --------------------------------------------------------------- INV-1 ----


def test_nothing_is_written_before_github_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-1, on Settings; the wizard's half is PRESS-0212 INV-6. Breaks when
    credentials.write moves ahead of root_entries, or the address check is
    dropped and the form reaches GitHub."""
    keyring = _Store(monkeypatch)
    _saved(tmp_path)
    before = _settings_file(tmp_path).read_bytes()

    github = _GitHub()
    with _setup_page(tmp_path, github) as browser:
        status, page = browser.post(_answers(site_address="ftp://example.org"))
    assert status == 200
    assert _offers_the_form(page) and _hint_for("site_address", page)
    assert github.calls == []

    github = _GitHub(refuse={"/commits/HEAD": 401})
    with _setup_page(tmp_path, github) as browser:
        status, page = browser.post(_answers())
    assert status == 200
    assert "GitHub would not accept your publishing key." in page
    assert github.calls, "the key never reached GitHub, so this proved nothing"

    github = _GitHub(refuse={"/commits/HEAD": 404})
    with _setup_page(tmp_path, github) as browser:
        status, page = browser.post(_answers())
    assert status == 200
    assert _offers_the_form(page) and _hint_for("repository", page)

    assert _settings_file(tmp_path).read_bytes() == before
    assert keyring.chosen == 0
    assert keyring.writes == []


# --------------------------------------------------------------- INV-2 ----


def test_the_settings_file_is_written_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-2. Breaks when save runs before the key is stored."""
    first = tmp_path / "choose-fails"
    first.mkdir()
    _Store(monkeypatch, choose_raises=credentials.CredentialError("locked"))
    with _setup_page(first, _GitHub()) as browser:
        _first_run(browser)
    assert not _settings_file(first).exists()

    second = tmp_path / "write-fails"
    second.mkdir()
    keyring = _Store(monkeypatch, write_raises=credentials.NoStore("none here"))
    with _setup_page(second, _GitHub()) as browser:
        _first_run(browser)
    assert keyring.chosen == 1, "the run never reached the store, so this proved nothing"
    assert not _settings_file(second).exists()

    third = tmp_path / "settings-write-fails"
    third.mkdir()
    _saved(third, untouchable=("OLD-ENTRY",))
    before = _settings_file(third).read_bytes()
    _Store(monkeypatch, write_raises=credentials.NoStore("none here"))
    with _setup_page(third, _GitHub()) as browser:
        browser.post(_answers(key="ghp_a-new-key"))
    assert _settings_file(third).read_bytes() == before


# --------------------------------------------------------------- INV-3 ----


def test_the_list_is_the_root_minus_what_the_builder_makes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INV-3. Breaks when the comparison is exact, uses str.lower, or reads a
    copy of ROOT_OUTPUT."""
    root = ("Index.html", "content", "CNAME", "assets", ".nojekyll")
    assert setup.untouchable(root) == (".nojekyll", "CNAME", "assets")

    monkeypatch.setattr(builder, "ROOT_OUTPUT", ("straße", "extra"))
    assert setup.untouchable(("STRASSE", "extra", "CNAME")) == ("CNAME",)


# --------------------------------------------------------------- INV-4 ----


def test_an_unreadable_settings_file_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-4. Breaks when every SettingsError from load is treated as NotSetUp,
    or none is."""
    keyring = _Store(monkeypatch)

    refused = tmp_path / "refused"
    refused.mkdir()
    _saved(refused, repository="ownername")
    before = _settings_file(refused).read_bytes()
    github = _GitHub()
    with _setup_page(refused, github) as browser:
        _, shown = browser.get()
        browser.post(_answers())
        browser.post({"step": "welcome", "go": "next"})
    assert not _offers_the_form(shown) and _step(shown) is None
    assert _settings_file(refused).read_bytes() == before
    assert github.calls == []
    assert keyring.chosen == 0 and keyring.writes == []

    carried = tmp_path / "carried"
    carried.mkdir()
    _saved(carried, site_folder=Path("site"))
    with _setup_page(carried, _GitHub()) as browser:
        _, shown = browser.get()
    assert _step(shown) == "welcome"


# --------------------------------------------------------------- INV-5 ----


def test_setup_works_on_an_empty_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-5. Breaks when setup calls into the Store for anything but whether
    it holds a site and the identity it writes, with the starter box
    unticked. PRESS-0126 § 4.4 lets setup read the first, to offer the starter
    site; PRESS-0213 § 4.6 has it check and write the second."""
    touched: list[str] = []

    def refuse(name: str):
        def refused(*args, **kwargs):
            touched.append(name)
            raise AssertionError(f"setup called store.{name}")
        return refused

    for name, function in inspect.getmembers(store, inspect.isfunction):
        if (not name.startswith("_") and function.__module__ == store.__name__
                and name not in ("holds_a_site", "identity_problem", "write_identity",
                                 "identity_path_for")):
            monkeypatch.setattr(store, name, refuse(name))
    _Store(monkeypatch)

    with _setup_page(tmp_path, _GitHub()) as browser:
        _, shown = browser.get()
        _first_run(browser)
    assert _step(shown) == "welcome"
    assert touched == []
    assert settings.load(tmp_path).repository == "owner/owner.github.io"


# --------------------------------------------------------------- INV-6 ----


def test_the_key_is_never_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """INV-6. Breaks when the re-rendered form fills the key box, or the done
    page echoes it."""
    cases = [
        ("success", _GitHub(), {}),
        ("refused site name", _GitHub(), {"site_name": " "}),
        ("refused key", _GitHub(refuse={"/commits/HEAD": 401}), {}),
    ]
    for label, github, changes in cases:
        folder = tmp_path / label.replace(" ", "-")
        folder.mkdir()
        _Store(monkeypatch)
        pages = []
        with _setup_page(folder, github) as browser:
            page = browser.get()[1]
            while _step(page) is not None:
                pages.append(page)
                after = _next(browser, page, **changes)
                if _step(after) == _step(page):
                    pages.append(after)
                    break
                page = after
            else:
                pages.append(page)
        captured = capfd.readouterr()
        for shown in pages:
            assert SENTINEL_KEY not in shown, label
            for box in _key_inputs(shown):
                assert "value=" not in box, label
        assert SENTINEL_KEY not in _log(folder), label
        assert SENTINEL_KEY not in captured.out + captured.err, label
    assert _settings_file(tmp_path / "success").exists(), "the success case did not succeed"


# --------------------------------------------------------------- INV-7 ----


def test_settings_never_asks_for_a_store_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-7. Breaks when Settings calls choose."""
    _saved(tmp_path, credentials=settings.Credentials(
        store="file", github_account="github", google_account=None))
    keyring = _Store(monkeypatch, answers="keyring")
    with _setup_page(tmp_path, _GitHub()) as browser:
        browser.post(_answers(key="ghp_a-new-key"))
    assert keyring.chosen == 0
    assert keyring.writes == [("file", "github", "ghp_a-new-key")]


# --------------------------------------------------------------- INV-8 ----


def test_an_empty_key_box_keeps_the_saved_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-8. Breaks when the empty string is stored as the key, or first run
    accepts one."""
    settings_path = tmp_path / "settings-page"
    settings_path.mkdir()
    _saved(settings_path)
    keyring = _Store(monkeypatch, saved_key="ghp_the-saved-key")
    github = _GitHub()
    with _setup_page(settings_path, github) as browser:
        browser.post(_answers(key=""))
    assert keyring.writes == []
    assert keyring.reads == [("keyring", "github")]
    assert github.calls and all(auth == "Bearer ghp_the-saved-key" for _, _, auth in github.calls)

    first_run = tmp_path / "first-run"
    first_run.mkdir()
    keyring = _Store(monkeypatch)
    github = _GitHub()
    with _setup_page(first_run, github) as browser:
        page = _first_run(browser, key="")
    assert _step(page) == "key" and _hint_for("key", page)
    assert all(auth == "" for _, _, auth in github.calls) and keyring.writes == []
    assert not _settings_file(first_run).exists()


# --------------------------------------------------------------- INV-9 ----


def test_settings_keeps_what_it_does_not_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-9. Breaks when Settings builds the candidate from first-run
    defaults, which erases PRESS-0122's fields."""
    kept = settings.Credentials(store="file", github_account="publishing-key",
                                google_account="analytics")
    _saved(tmp_path, credentials=kept, analytics_property_id="123456789")
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        browser.post(_answers(key=""))
    loaded = settings.load(tmp_path)
    assert loaded.credentials == kept
    assert loaded.analytics_property_id == "123456789"


# -------------------------------------------------------------- INV-10 ----


def test_first_run_saves_a_file_that_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-10. Breaks when a value departs from § 4.5, save writes what load
    refuses, or the placeholder store is saved instead of Choice.store."""
    for answered in ("keyring", "file"):
        folder = tmp_path / answered
        folder.mkdir()
        _Store(monkeypatch, answers=answered)
        with _setup_page(folder, _GitHub()) as browser:
            _first_run(browser)
        assert settings.load(folder) == settings.Settings(
            site_folder=folder / "site",
            repository="owner/owner.github.io",
            site_address=ADDRESS,
            daily_prompt_filter="",
            untouchable=DERIVED,
            credentials=settings.Credentials(store=answered, github_account="github",
                                             google_account=None),
            analytics_property_id=None,
        ), answered
        assert store.read_identity(folder) == store.Identity("A Journal"), answered


# -------------------------------------------------------------- INV-12 ----


def test_a_malformed_key_is_refused_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-12. Breaks when the key check is dropped.

    A line break and a space are the spec's two cases, and both are
    whitespace. A control character and a non-ASCII letter are not, so they
    are what show the printable and ASCII halves of § 4.4's rule held."""
    for malformed in ("ghp_abc\ndef", "ghp_abc def", "ghp_abc\x00def", "ghp_abcédef"):
        folder = tmp_path / str(abs(hash(malformed)))
        folder.mkdir()
        _Store(monkeypatch)
        github = _GitHub()
        with _setup_page(folder, github) as browser:
            page = _first_run(browser, key=malformed)
        assert all(auth == "" for _, _, auth in github.calls), repr(malformed)
        assert _step(page) == "key" and _hint_for("key", page), repr(malformed)


# -------------------------------------------------------------- INV-13 ----


def test_a_credential_failure_names_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-13. Breaks when the failure escapes to the page catch, which names
    the Face's fallback noun instead."""
    first_run = tmp_path / "no-store"
    first_run.mkdir()
    _Store(monkeypatch, choose_raises=credentials.NoStore("none here"))
    with _setup_page(first_run, _GitHub()) as browser:
        page = _first_run(browser)
    assert KEY_NOUN in page
    assert "Setup cannot finish on this computer." in page

    settings_path = tmp_path / "not-stored"
    settings_path.mkdir()
    _saved(settings_path)
    _Store(monkeypatch, read_raises=credentials.NotStored("nothing here"))
    with _setup_page(settings_path, _GitHub()) as browser:
        _, page = browser.post(_answers(key=""))
    assert KEY_NOUN in page


# -------------------------------------------------------------- INV-14 ----


def test_setup_sits_behind_the_faces_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-14, on Settings; the wizard's is PRESS-0212 INV-12. Breaks when
    setup serves its own handler or never registers on the Face."""
    _Store(monkeypatch)
    _saved(tmp_path)
    store.write_identity(tmp_path, store.Identity("Before"))
    with _setup_page(tmp_path, _GitHub()) as browser:
        assert browser.post(_answers(key=""), cookie=False)[0] == 403
        assert browser.post(_answers(key=""), origin="http://pressless.example")[0] == 403
        assert store.read_identity(tmp_path).name == "Before"
        assert browser.post(_answers(key=""))[0] == 200
    assert store.read_identity(tmp_path).name == "A Journal"


# -------------------------------------------------------------- INV-15 ----


def test_the_filter_is_the_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-15. Breaks when first run writes a default filter, or Settings
    carries the saved filter forward in place of the answer."""
    first_run = tmp_path / "first-run"
    first_run.mkdir()
    _Store(monkeypatch)
    with _setup_page(first_run, _GitHub()) as browser:
        _first_run(browser)
    assert settings.load(first_run).daily_prompt_filter == ""

    settings_path = tmp_path / "settings-page"
    settings_path.mkdir()
    _saved(settings_path, daily_prompt_filter="dailyprompt-*")
    with _setup_page(settings_path, _GitHub()) as browser:
        _, shown = browser.get()
        assert 'value="dailyprompt-*"' in shown
        browser.post(_answers(key="", daily_prompt_filter="x-*"))
        assert settings.load(settings_path).daily_prompt_filter == "x-*"
        browser.post(_answers(key="", daily_prompt_filter=""))
    assert settings.load(settings_path).daily_prompt_filter == ""


# ------------------------------------------- PRESS-0127 INV-9: empty repo ----


class _EmptyGitHub(_GitHub):
    """A repository with no commits: GitHub answers the head read 409 with
    "Git Repository is empty." (measured 2026-09-18, PRESS-0127 § 2)."""

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        if "/commits/" in url:
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 409, {}, b'{"message": "Git Repository is empty."}'
        return super().request(method, url, body, headers)


def test_setup_finishes_against_an_empty_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRESS-0127 INV-9, which PRESS-0212 leaves to Settings. Breaks when
    root_entries raises on the empty answer, or Settings starts the
    repository itself."""
    _Store(monkeypatch)
    _saved(tmp_path)
    github = _EmptyGitHub()

    with _setup_page(tmp_path, github) as browser:
        status, page = browser.post(_answers(key=""))

    assert status == 200
    assert "Setup is done." in page
    assert settings.load(tmp_path).untouchable == ()
    assert github.calls, "setup never asked GitHub, so this proved nothing"
    assert github.writes() == []


# PRESS-0126 INV-6, INV-7, INV-8, INV-14 (docs/specs/PRESS-0126-starter-site.md
# § 4.4). The marker's name is written out rather than imported.


def _store_files(folder: Path) -> dict[str, bytes]:
    """Every file in a subfolder of `folder`: the Store, not settings, the log
    or the wizard's progress (PRESS-0212 § 4.2)."""
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob("*") if p.is_file() and p.parent != folder
            and p.relative_to(folder).parts[0] != "wizards"}


def test_the_starter_is_offered_only_on_an_empty_store(tmp_path, monkeypatch):
    """INV-6. Breaks when the box shows over an imported Store, or a forged
    post fills over one."""
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        empty = _walk_to(browser, "site")
    store.write_html(tmp_path, store.PAGES_FOLDER, "index", "<p>mine</p>\n")
    before = _store_files(tmp_path)
    with _setup_page(tmp_path, _GitHub()) as browser:
        held = browser.get()[1]
        _first_run(browser, start="starter")
    assert 'name="start"' in empty
    assert _step(held) == "site" and 'name="start"' not in held
    after = _store_files(tmp_path)
    after.pop("identity/identity.json")          # PRESS-0213: the site step writes it
    assert after == before
    assert not (tmp_path / "starter-unpublished").exists()


def test_a_failed_fill_saves_nothing(tmp_path, monkeypatch):
    """INV-7. Breaks when the fill runs after the save."""
    _Store(monkeypatch)

    def refuse(folder, site_name):
        raise store.StoreError("the disk is full")

    monkeypatch.setattr(starter, "fill", refuse)
    with _setup_page(tmp_path, _GitHub()) as browser:
        page = _first_run(browser, start="starter")
    assert _step(page) == "site"
    assert not _settings_file(tmp_path).exists()


def test_an_unticked_box_fills_nothing(tmp_path, monkeypatch):
    """INV-8, and the ticked case beside it. Breaks when the fill ignores the box."""
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        _first_run(browser)
    assert not store.holds_a_site(tmp_path)
    assert settings.load(tmp_path).repository == "owner/owner.github.io"

    ticked = tmp_path / "ticked"
    ticked.mkdir()
    with _setup_page(ticked, _GitHub()) as browser:
        done = _first_run(browser, start="starter")
    assert store.holds_a_site(ticked)
    assert store.journal_on(ticked) is False
    assert (ticked / "starter-unpublished").exists()
    assert "starter site" in done


def test_the_look_is_builder_output():
    """INV-14. Breaks when "look" is not in ROOT_OUTPUT."""
    assert setup.untouchable(("look", "CNAME")) == ("CNAME",)


# PRESS-0199 INV-7, INV-8 (docs/specs/PRESS-0199-counting-code.md §§ 4.4, 4.5).


def test_switching_counting_on_adds_privacy_once(tmp_path, monkeypatch):
    """INV-7. Breaks when the link is inserted on every save, the user's
    Privacy page is replaced, or an empty Store is written to."""
    _Store(monkeypatch)
    site = tmp_path / "site-held"
    site.mkdir()
    _saved(site)
    starter.fill(site, "A Journal")
    with _setup_page(site, _GitHub()) as browser:
        browser.post(_answers(measurement_id="G-ABC123", key=""))
        browser.post(_answers(measurement_id="G-ABC123", key=""))
    assert settings.load(site).measurement_id == "G-ABC123"
    assert store.html_path_for(site, store.PAGES_FOLDER, "privacy").is_file()
    footer = store.read_html(store.html_path_for(site, store.FURNITURE_FOLDER, "footer"))
    assert footer.count("pages/privacy.html") == 1

    mine = tmp_path / "mine"
    mine.mkdir()
    _saved(mine)
    starter.fill(mine, "A Journal")
    store.write_html(mine, store.PAGES_FOLDER, "privacy", "<p>my own</p>\n")
    with _setup_page(mine, _GitHub()) as browser:
        browser.post(_answers(measurement_id="G-ABC123", key=""))
    assert store.read_html(store.html_path_for(mine, store.PAGES_FOLDER, "privacy")) == (
        "<p>my own</p>\n")

    empty = tmp_path / "empty"
    empty.mkdir()
    _saved(empty)
    with _setup_page(empty, _GitHub()) as browser:
        browser.post(_answers(measurement_id="G-ABC123", key=""))
    assert settings.load(empty).measurement_id == "G-ABC123"
    assert not store.holds_a_site(empty)


def test_a_malformed_measurement_id_is_a_refused_answer(tmp_path, monkeypatch):
    """INV-8. Breaks when a malformed id reaches settings.save."""
    _Store(monkeypatch)
    _saved(tmp_path)
    before = _settings_file(tmp_path).read_bytes()
    with _setup_page(tmp_path, _GitHub()) as browser:
        _, page = browser.post(_answers(measurement_id="UA-1234", key=""))
    assert _hint_for("measurement_id", page)
    assert _settings_file(tmp_path).read_bytes() == before


# ------------------------------------------------------------ PRESS-0183 ----
# The menu entry and the desktop icon, offered once setup is done and kept in
# Settings. The shortcuts themselves are tests/test_shortcuts.py's.

SHORTCUTS = "/setup/shortcuts"


def _places(tmp_path: Path) -> shortcuts.Places:
    program = tmp_path / "apps" / "Pressless.AppImage"
    program.parent.mkdir(parents=True)
    program.write_bytes(b"not really an AppImage")
    (tmp_path / "Desktop").mkdir()
    return shortcuts.Places(
        windows=False, menu=tmp_path / "menu" / "pressless.desktop",
        desktop=tmp_path / "Desktop" / "pressless.desktop", program=program,
        working=program.parent, icon=None, icon_copy=tmp_path / "icon.png")


def _boxes(page: str) -> dict[str, bool]:
    """Each shortcut box on the page, and whether it is ticked."""
    return {name: "checked" in tag for tag, name in
            re.findall(r'(<input type="checkbox" name="(menu|desktop)"[^>]*>)', page)}


def test_first_run_offers_both_shortcuts_ticked(tmp_path, monkeypatch):
    """Breaks when the done page leaves the offer out, or offers it unticked."""
    _Store(monkeypatch)
    where = _places(tmp_path / "places")
    with _setup_page(tmp_path, _GitHub(), where) as browser:
        done = _first_run(browser)
    assert "Setup is done." in done
    assert _boxes(done) == {"menu": True, "desktop": True}
    assert f'action="{SHORTCUTS}"' in done
    assert shortcuts.present(where) == (False, False)   # offered, never assumed


def test_a_refused_answer_offers_no_shortcuts(tmp_path, monkeypatch):
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub(), _places(tmp_path / "places")) as browser:
        page = _first_run(browser, site_name=" ")
    assert _hint_for("site_name", page)
    assert _boxes(page) == {}


def test_settings_shows_the_shortcuts_as_they_are(tmp_path, monkeypatch):
    _Store(monkeypatch)
    _saved(tmp_path)
    where = _places(tmp_path / "places")
    shortcuts.apply(where, menu=True, desktop=False)
    with _setup_page(tmp_path, _GitHub(), where) as browser:
        _, page = browser.get()
    assert _boxes(page) == {"menu": True, "desktop": False}


def test_every_settings_box_has_help_beside_it(tmp_path, monkeypatch):
    """PRESS-0228: each box on Settings has a "?" that opens a dialog of its
    own and never submits the form; the key's help is the wizard's steps."""
    _Store(monkeypatch)
    _saved(tmp_path)
    with _setup_page(tmp_path, _GitHub()) as browser:
        _, page = browser.get()
    boxes = re.findall(r'<input type="(?:text|password)" name="([^"]+)"', page)
    assert "key" in boxes and "repository" in boxes
    for name in boxes:
        assert re.search(rf'<button type="button" class="help" data-help="{name}-help"',
                         page), f"{name} has no help button"
        assert f'<dialog id="{name}-help"' in page, f"{name} has no help dialog"
    assert page.count('class="help"') == len(boxes)
    assert setup._NEW_KEY in page and setup._NEW_KEY in setup._show_key({}, None)


def test_the_key_steps_ask_for_administration(tmp_path, monkeypatch):
    """PRESS-0230: GitHub switches Pages on only for a key with Administration
    write, so the wizard's key step, Settings' help and the refusal name it."""
    assert "<b>Administration</b>" in setup._show_key({}, None)
    assert "<b>Administration</b>" in setup._SETTINGS_HELP["key"]
    assert "Administration" in setup._NO_PAGES_WRITE


def test_a_finished_setup_says_how_to_publish_the_starter(tmp_path, monkeypatch):
    """The done page leads on to the list and says how the starter site first
    reaches the web; the list says so too, until the first publish."""
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        done = _first_run(browser, start="starter")
    assert "Setup is done." in done and starter.unpublished(tmp_path)
    assert '<a href="/">Go to your list</a>' in done
    assert "<b>Press to site</b>" in done

    served = face.serve(tmp_path)
    try:
        setup.register(served, tmp_path, transport=_GitHub())
        editor.register(served, tmp_path)
        browser = Browser(served)
        assert 'id="starter-unpublished"' in browser.request("GET", "/")[2]
        starter.published(tmp_path)
        assert 'id="starter-unpublished"' not in browser.request("GET", "/")[2]
    finally:
        served.stop()


def test_a_development_run_offers_no_shortcuts(tmp_path, monkeypatch):
    _Store(monkeypatch)
    _saved(tmp_path)
    with _setup_page(tmp_path, _GitHub()) as browser:
        _, page = browser.get()
        status, said = browser.post({"menu": "on"}, path=SHORTCUTS)
    assert _boxes(page) == {}
    assert status == 200 and "file you downloaded" in said


def test_saving_the_boxes_makes_and_removes_the_shortcuts(tmp_path, monkeypatch):
    """Breaks when the ticks are not read, or removal is not offered."""
    _Store(monkeypatch)
    _saved(tmp_path)
    where = _places(tmp_path / "places")
    with _setup_page(tmp_path, _GitHub(), where) as browser:
        _, made = browser.post({"menu": "on", "desktop": "on"}, path=SHORTCUTS)
        assert shortcuts.present(where) == (True, True)
        _, again = browser.post({"menu": "on", "desktop": "on"}, path=SHORTCUTS)
        _, removed = browser.post({}, path=SHORTCUTS)
    assert "right-click it" in made          # how to pin it, since nothing pins for him
    assert "icon on your desktop" in made
    assert "Nothing needed changing" in again
    assert shortcuts.present(where) == (False, False)
    assert "no longer in your app menu" in removed
    assert "gone from your desktop" in removed


def test_a_shortcut_failure_is_the_faces_sentence(tmp_path, monkeypatch):
    _Store(monkeypatch)
    _saved(tmp_path)
    where = _places(tmp_path / "places")
    where.menu.parent.parent.mkdir(parents=True, exist_ok=True)
    where.menu.parent.write_text("a file where the menu folder goes", encoding="utf-8")
    with _setup_page(tmp_path, _GitHub(), where) as browser:
        _, page = browser.post({"menu": "on"}, path=SHORTCUTS)
    assert "could not change its shortcut" in page
    assert str(tmp_path) not in page


def test_the_shortcut_page_sits_behind_the_faces_boundary(tmp_path, monkeypatch):
    _Store(monkeypatch)
    _saved(tmp_path)
    where = _places(tmp_path / "places")
    with _setup_page(tmp_path, _GitHub(), where) as browser:
        assert browser.post({"menu": "on"}, cookie=False, path=SHORTCUTS)[0] == 403
        assert browser.post({"menu": "on"}, origin="http://pressless.example",
                            path=SHORTCUTS)[0] == 403
    assert shortcuts.present(where) == (False, False)


# ------------------------------------------------------------ PRESS-0212 ----
# The setup wizard (docs/specs/PRESS-0212-setup-wizard.md § 5). The pattern's
# own invariants, INV-1 to INV-4, are tests/test_wizard.py's.


def _progress(folder: Path) -> Path:
    return folder / "wizards" / "setup.json"


def test_the_key_never_reaches_the_progress_file(tmp_path, monkeypatch):
    """INV-5. Breaks when the wizard writes every posted field, or a step
    stores the key in its answers."""
    keyring = _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        page = _walk_to(browser, "pages")
    assert keyring.writes == [("keyring", "github", SENTINEL_KEY)], "no key was taken"
    held = _progress(tmp_path).read_text(encoding="utf-8")
    assert SENTINEL_KEY not in held
    assert "key" not in json.loads(held)["answers"]
    assert SENTINEL_KEY not in page


def test_the_key_is_stored_once_github_answers(tmp_path, monkeypatch):
    """INV-6. Breaks when write moves ahead of root_entries or pages, or the
    save sequence keeps step 3 or 4 of PRESS-0021 § 4.6."""
    keyring = _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        page = _first_run(browser, key="ghp_abc def")
    assert _step(page) == "key"
    with _setup_page(tmp_path, _GitHub(refuse={"/commits/HEAD": 401})) as browser:
        page = _first_run(browser)
    assert "GitHub would not accept your publishing key." in page
    with _setup_page(tmp_path, _GitHub(refuse={"/pages": 403})) as browser:
        page = _first_run(browser)
    assert _step(page) == "key" and _hint_for("key", page)
    assert keyring.chosen == 0 and keyring.writes == []

    with _setup_page(tmp_path, _GitHub()) as browser:
        done = _first_run(browser)
    assert "Setup is done." in done
    assert keyring.chosen == 1
    assert keyring.writes == [("keyring", "github", SENTINEL_KEY)]

    again = tmp_path / "back-to-the-key"
    again.mkdir()
    keyring = _Store(monkeypatch)
    with _setup_page(again, _GitHub()) as browser:
        pages = _walk_to(browser, "pages")
        key = browser.post({"step": _step(pages), "go": "back"})[1]
        assert _step(key) == "key" and "Leave the box empty" in key
        pages = _next(browser, key, key="")
        key = browser.post({"step": _step(pages), "go": "back"})[1]
        _first_run(browser, key="ghp_a-second-key")
    assert keyring.chosen == 1
    assert keyring.writes == [("keyring", "github", SENTINEL_KEY),
                              ("keyring", "github", "ghp_a-second-key")]
    assert _settings_file(again).exists()


def test_settings_are_written_last_by_the_wizard(tmp_path, monkeypatch):
    """INV-7. Breaks when any earlier step saves a partial Settings."""
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        page = browser.get()[1]
        while _step(page) != "site":
            assert not _settings_file(tmp_path).exists(), _step(page)
            page = _next(browser, page)

        def refuse(folder, value):
            raise settings.SettingsError("the disk is full")

        monkeypatch.setattr(settings, "save", refuse)
        page = _next(browser, page)
    assert _step(page) == "site"
    assert not _settings_file(tmp_path).exists()


def test_pages_is_left_as_github_has_it(tmp_path, monkeypatch):
    """INV-8. Breaks when the step always POSTs, overwrites an existing Pages
    source, or accepts a site served from somewhere Pressless does not publish."""
    _Store(monkeypatch)
    for state, moved, writes in (
        ("root", True, []),
        ("off", True, [("PUT", "/repos/owner/owner.github.io/contents/.nojekyll"),
                       ("POST", "/repos/owner/owner.github.io/pages")]),
        ("elsewhere", False, []),
    ):
        folder = tmp_path / state
        folder.mkdir()
        github = _GitHub(pages=state)
        with _setup_page(folder, github) as browser:
            pages = _walk_to(browser, "pages")
            after = _next(browser, pages)
        assert (_step(after) == "site") is moved, state
        assert github.writes() == writes, state
        if moved:
            assert ADDRESS in after, state
        else:
            # PRESS-0229: sent elsewhere, never told to re-point a live site.
            assert "choose a different, new repository" in after, state
            assert "Deploy from a branch" not in after, state


def test_setup_writes_only_what_pages_needs(tmp_path, monkeypatch):
    """INV-9. Breaks when a step writes another file, a branch or a setting,
    or sends the switch before the empty repository has its first commit."""
    _Store(monkeypatch)
    nojekyll = ("PUT", "/repos/owner/owner.github.io/contents/.nojekyll")
    switch = ("POST", "/repos/owner/owner.github.io/pages")
    for label, github, writes in (
        ("held", _GitHub(pages="off"), [nojekyll, switch]),
        ("empty", _EmptyGitHub(pages="off"), [nojekyll, switch]),
        ("served-as-is", _GitHub(root=(*ROOT, ".nojekyll"), pages="off"), [switch]),
        ("already-on", _GitHub(), []),
    ):
        folder = tmp_path / label
        folder.mkdir()
        with _setup_page(folder, github) as browser:
            done = _first_run(browser)
        assert "Setup is done." in done, label
        assert github.writes() == writes, label


def test_a_finished_setup_shows_settings(tmp_path, monkeypatch):
    """INV-11. Breaks when Done leaves the file, or /setup checks the progress
    file before settings.load."""
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        _first_run(browser)
        _, shown = browser.get()
    assert not _progress(tmp_path).exists()
    assert _offers_the_form(shown) and "<h1>Settings</h1>" in shown


def test_the_wizard_sits_behind_the_faces_boundary(tmp_path, monkeypatch):
    """INV-12. Breaks when the wizard is served by its own handler."""
    _Store(monkeypatch)
    step = {"step": "welcome", "go": "next"}
    with _setup_page(tmp_path, _GitHub()) as browser:
        assert browser.post(step, cookie=False)[0] == 403
        assert browser.post(step, origin="http://pressless.example")[0] == 403
        assert not _progress(tmp_path).exists()
        status, page = browser.post(step)
    assert status == 200 and _step(page) == "account"
    assert _progress(tmp_path).exists()


# ------------------------------------------------------ PRESS-0213 INV-4 ----
# docs/specs/PRESS-0213-site-identity.md § 4.3, § 4.6.


def _with_old_name(folder: Path, name: str = "Old", **raw) -> None:
    """A settings file as a Pressless from before PRESS-0213 left it."""
    _saved(folder)
    target = _settings_file(folder)
    data = json.loads(target.read_text(encoding="utf-8"))
    data.update(site_name=name, **raw)
    target.write_text(json.dumps(data), encoding="utf-8")


def _carried(folder: Path) -> dict:
    return json.loads(_settings_file(folder).read_text(encoding="utf-8"))


def test_the_name_is_carried_across_once(tmp_path, monkeypatch):
    """INV-4. Breaks when the key is retired before the identity is written,
    an existing identity is overwritten, or a moved name is reported as not
    moved."""
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _with_old_name(fresh)
    assert setup.carry_name_across(fresh) is None
    assert store.read_identity(fresh) == store.Identity("Old")
    assert "site_name" not in _carried(fresh)
    assert setup.carry_name_across(fresh) is None          # nothing left to move

    renamed = tmp_path / "renamed"
    renamed.mkdir()
    _with_old_name(renamed)
    store.write_identity(renamed, store.Identity("New"))
    assert setup.carry_name_across(renamed) is None
    assert store.read_identity(renamed) == store.Identity("New")
    assert "site_name" not in _carried(renamed)

    carried_elsewhere = tmp_path / "carried"
    carried_elsewhere.mkdir()
    _with_old_name(carried_elsewhere, site_folder="site")
    assert setup.carry_name_across(carried_elsewhere) is None
    assert store.read_identity(carried_elsewhere) == store.Identity("Old")
    assert _carried(carried_elsewhere)["site_name"] == "Old"

    stuck = tmp_path / "stuck"
    stuck.mkdir()
    _with_old_name(stuck)
    before = _settings_file(stuck).read_bytes()

    def refuse(folder, identity):
        raise store.StoreError("identity.json could not be written: the disk is full")

    monkeypatch.setattr(store, "write_identity", refuse)
    said = setup.carry_name_across(stuck)
    assert said is not None and "the disk is full" in said
    assert _settings_file(stuck).read_bytes() == before


# ------------------------------------------------- PRESS-0213 INV-8, INV-9 ----


def test_the_site_step_saves_the_identity(tmp_path, monkeypatch):
    """INV-8. Breaks when the identity is written into Settings, after the
    settings file, or past a refused answer."""
    for label, changes, hint in (("no name", {"site_name": " "}, "site_name"),
                                 ("two lines", {"site_description": "a\nb"},
                                  "site_description")):
        folder = tmp_path / label.replace(" ", "-")
        folder.mkdir()
        _Store(monkeypatch)
        with _setup_page(folder, _GitHub()) as browser:
            page = _first_run(browser, **changes)
        assert _step(page) == "site" and _hint_for(hint, page), label
        assert store.read_identity(folder) is None, label
        assert not _settings_file(folder).exists(), label

    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        _first_run(browser, site_description="Poems, mostly.")
    assert store.read_identity(tmp_path) == store.Identity("A Journal", "Poems, mostly.")
    assert "site_name" not in _carried(tmp_path)


def test_settings_page_edits_the_identity(tmp_path, monkeypatch):
    """INV-9. Breaks when the page reads or writes the name anywhere but the
    Store."""
    _saved(tmp_path)
    store.write_identity(tmp_path, store.Identity("Shown Name", "Shown words."))
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        page = browser.get()[1]
        assert 'value="Shown Name"' in page and 'value="Shown words."' in page
        browser.post(_answers(key="", site_name="Renamed", site_description="New words."))
    assert store.read_identity(tmp_path) == store.Identity("Renamed", "New words.")
    assert "site_name" not in _carried(tmp_path)


# --------------------------------------------- PRESS-0231: GitHub sign-in ----
# docs/specs/PRESS-0231-github-sign-in.md § 5. GitHub's sign-in endpoints
# answer through the same recording double, at github.com rather than
# api.github.com. Secrets are plain words, so the push gate's secret scanner
# does not mistake them.

APP = "pressless-app"
DEVICE_CODE = "plain-device-code"
USER_CODE = "WDJB-MJHT"
FIRST_ACCESS = "ghu_plain-first-access"
FIRST_REFRESH = "ghr_plain-first-refresh"
INSTALLATION = "/user/installations/7/repositories/99"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _SignInGitHub(_GitHub):
    """_GitHub, with GitHub's sign-in endpoints and the GitHub App's requests.

    `polls` answers each poll of a device code in turn, its last repeating:
    an `error` code, or "tokens". `selection` is the installation's
    repository_selection, or None where the app is not installed. `taken` is
    what already holds the repository's name: None, "empty" or "full"; a
    repository Pressless makes is empty. `lose_create` makes the first create
    succeed on GitHub and lose its answer. `refuse_refresh` refuses every
    renewal of the pass.
    """

    def __init__(self, *, polls: tuple[str, ...] = ("tokens",),
                 selection: str | None = "selected", taken: str | None = None,
                 lose_create: bool = False, refuse_refresh: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.polls = list(polls)
        self.selection = selection
        self.taken = taken
        self.lose_create = lose_create
        self.refuse_refresh = refuse_refresh

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        path = url.removeprefix(publisher.API)
        if url.startswith("https://github.com/"):
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 200, {}, json.dumps(self._signing_in(url, body)).encode()
        if method == "GET" and path == "/user":
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 200, {}, b'{"login": "owner"}'
        if method == "GET" and path.startswith("/user/installations"):
            self.calls.append((method, url, headers.get("Authorization", "")))
            found = [] if self.selection is None else [
                {"id": 7, "app_slug": APP, "account": {"login": "owner"},
                 "repository_selection": self.selection}]
            return 200, {}, json.dumps({"total_count": len(found),
                                        "installations": found}).encode()
        if method == "POST" and path == "/user/repos":
            self.calls.append((method, url, headers.get("Authorization", "")))
            if self.taken is not None:
                return 422, {}, b'{"message": "Repository creation failed."}'
            self.taken = "empty"
            if self.lose_create:
                self.lose_create = False
                raise OSError("the answer was lost")
            return 201, {}, b'{"full_name": "owner/owner.github.io"}'
        if method == "PUT" and path == INSTALLATION:
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 204, {}, b""
        if method == "GET" and path == "/repos/owner/owner.github.io":
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 200, {}, b'{"id": 99, "default_branch": "main", "private": false}'
        if self.taken == "empty" and "/commits/" in url:
            self.calls.append((method, url, headers.get("Authorization", "")))
            return 409, {}, b'{"message": "Git Repository is empty."}'
        return super().request(method, url, body, headers)

    def _signing_in(self, url: str, body: bytes | None) -> dict:
        form = urllib.parse.parse_qs((body or b"").decode())
        if url.endswith("/login/device/code"):
            return {"device_code": DEVICE_CODE, "user_code": USER_CODE,
                    "verification_uri": "https://github.com/login/device",
                    "expires_in": 900, "interval": 5}
        if form.get("grant_type") == ["refresh_token"]:
            if self.refuse_refresh:
                return {"error": "bad_refresh_token",
                        "error_description": f"{form['refresh_token'][0]} is spent"}
            return {"access_token": "ghu_plain-renewed", "refresh_token": "ghr_plain-renewed",
                    "expires_in": 28800}
        answer = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
        if answer != "tokens":
            return {"error": answer, "error_description": f"about {DEVICE_CODE}"}
        return {"access_token": FIRST_ACCESS, "refresh_token": FIRST_REFRESH,
                "expires_in": 28800}

    def sent_to(self, ending: str) -> int:
        return sum(1 for _m, url, _a in self.calls if url.endswith(ending))


def _app(monkeypatch: pytest.MonkeyPatch) -> None:
    """A copy of Pressless carrying a registered GitHub App."""
    monkeypatch.setattr(github_signin, "CLIENT_ID", "Iv1.plain-client")
    monkeypatch.setattr(github_signin, "APP_SLUG", APP)


def _walk(browser: _Browser, until: str | None = None) -> tuple[list[str], str]:
    """Press Next from where the wizard stands, a second time on signin (the
    first press fetches the code), until `until`'s page or a step that does
    not move on. The steps passed, and the last page."""
    page = browser.get()[1]
    seen: list[str] = []
    while (step := _step(page)) is not None and step != until:
        seen.append(step)
        after = _next(browser, page)
        if step == "signin" and _step(after) == step:
            after = _next(browser, after)
        if _step(after) == step:
            return seen, after
        page = after
    return seen, page


def test_the_sign_in_secrets_stay_out_of_sight(tmp_path, monkeypatch):
    """INV-3. Breaks when a failure's text carries GitHub's answer, or the
    wizard writes the held code into the answers."""
    _app(monkeypatch)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    clock = _Clock()
    shown: list[str] = []
    with _setup_page(tmp_path, _SignInGitHub(refuse_refresh=True), clock=clock) as browser:
        page = _walk_to(browser, "signin")
        shown.append(page)
        coded = _next(browser, page)
        shown.append(coded)
        assert _step(coded) == "signin" and USER_CODE in coded
        install = _next(browser, coded)
        shown.append(install)
        assert _step(install) == "install"
        clock.now += 9 * 3600       # the pass is spent, and GitHub will not renew it
        lapsed = _next(browser, install)
        shown.append(lapsed)
    assert _step(lapsed) == "install" and "GitHub has signed Pressless out." in lapsed
    held = _progress(tmp_path).read_text(encoding="utf-8")
    for secret in (DEVICE_CODE, FIRST_ACCESS, FIRST_REFRESH):
        assert all(secret not in page for page in shown), secret
        assert secret not in _log(tmp_path), secret
        assert secret not in held, secret


def test_signing_in_stores_only_what_github_issued(tmp_path, monkeypatch):
    """INV-4. Breaks when a pending answer stores something, or the step
    advances on it."""
    _app(monkeypatch)
    keyring = _Store(monkeypatch, saved_key=FIRST_REFRESH)
    github = _SignInGitHub(polls=("authorization_pending", "expired_token",
                                  "access_denied", "tokens"))
    with _setup_page(tmp_path, github, clock=_Clock()) as browser:
        page = _walk_to(browser, "signin")
        said = {}
        for press in ("a code", "pending", "expired", "declined", "a new code"):
            page = _next(browser, page)
            said[press] = page
            assert _step(page) == "signin", press
            assert keyring.writes == [] and keyring.chosen == 0, press
        page = _next(browser, page)
    assert "GitHub has not heard from you yet." in said["pending"]
    assert "cancelled on GitHub" in said["declined"]
    assert _step(page) == "install"
    assert keyring.chosen == 1
    assert keyring.writes == [("keyring", "github", FIRST_REFRESH)]


def test_an_expired_code_is_replaced(tmp_path, monkeypatch):
    """INV-5. Breaks when the step polls a dead code and shows GitHub's error."""
    _app(monkeypatch)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    github = _SignInGitHub(polls=("expired_token",))
    clock = _Clock()
    with _setup_page(tmp_path, github, clock=clock) as browser:
        page = _next(browser, _walk_to(browser, "signin"))
        clock.now += 901
        page = _next(browser, page)
    assert _step(page) == "signin" and USER_CODE in page
    assert github.sent_to("/login/device/code") == 2
    assert github.sent_to("/login/oauth/access_token") == 0


def test_a_taken_name_is_left_alone(tmp_path, monkeypatch):
    """INV-6. Breaks when the step adopts any existing repository, or pages
    runs over it."""
    _app(monkeypatch)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    github = _SignInGitHub(taken="full")
    with _setup_page(tmp_path, github, clock=_Clock()) as browser:
        _, page = _walk(browser, until="repository")
        assert _step(page) == "repository" and 'value="owner.github.io"' in page
        after = _next(browser, page)
    assert _step(after) == "repository" and _hint_for("repository", after)
    assert "already exists" in after
    assert [write for write in github.writes() if write[1].startswith("/")] == [
        ("POST", "/user/repos")]


def test_a_second_press_finds_the_first_repository(tmp_path, monkeypatch):
    """INV-7. Breaks when the 422 is always a Hint, so a dropped answer strands
    the person."""
    _app(monkeypatch)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    github = _SignInGitHub(lose_create=True)
    with _setup_page(tmp_path, github, clock=_Clock()) as browser:
        _, page = _walk(browser, until="repository")
        lost = _next(browser, page)
        assert _step(lost) == "repository" and "Pressless could not reach GitHub." in lost
        assert github.sent_to("/user/repos") == 1
        after = _next(browser, lost)
    assert _step(after) == "pages"
    assert github.sent_to("/user/repos") == 2


def test_the_new_repository_is_included(tmp_path, monkeypatch):
    """INV-8. Breaks when the PUT is skipped for `selected`, so the pages step
    meets a 404."""
    _app(monkeypatch)
    for selection, included in (("selected", True), ("all", False)):
        folder = tmp_path / selection
        folder.mkdir()
        _Store(monkeypatch, saved_key=FIRST_REFRESH)
        github = _SignInGitHub(selection=selection, pages="off")
        with _setup_page(folder, github, clock=_Clock()) as browser:
            _, done = _walk(browser)
        assert "Setup is done." in done, selection
        assert (("PUT", INSTALLATION) in github.writes()) is included, selection
        # Where the app reaches every repository, the done page says how to narrow it.
        assert ("Only select repositories" in done) is not included, selection


def test_signed_in_setup_writes_only_what_it_needs(tmp_path, monkeypatch):
    """INV-9. Breaks when a step writes another file, setting or repository."""
    _app(monkeypatch)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    github = _SignInGitHub(pages="off")
    with _setup_page(tmp_path, github, clock=_Clock()) as browser:
        _, done = _walk(browser)
    assert "Setup is done." in done
    assert [write for write in github.writes() if write[1].startswith("/")] == [
        ("POST", "/user/repos"),
        ("PUT", INSTALLATION),
        ("PUT", "/repos/owner/owner.github.io/contents/.nojekyll"),
        ("POST", "/repos/owner/owner.github.io/pages"),
    ]
    assert all(url.startswith("https://github.com/login/")
               for method, url in github.writes() if not url.startswith("/"))
    assert all(method != "DELETE" for method, _url, _auth in github.calls)


def test_the_steps_follow_the_registration(tmp_path, monkeypatch):
    """INV-10. Breaks when a development copy offers a sign-in GitHub will
    refuse, or a registered one still asks for a key."""
    _Store(monkeypatch)
    folder = tmp_path / "unregistered"
    folder.mkdir()
    with _setup_page(folder, _GitHub(pages="off")) as browser:
        seen, done = _walk(browser)
    assert seen == ["welcome", "account", "repository", "key", "pages", "site"]
    assert "Setup is done." in done

    _app(monkeypatch)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    folder = tmp_path / "registered"
    folder.mkdir()
    with _setup_page(folder, _SignInGitHub(pages="off"), clock=_Clock()) as browser:
        seen, done = _walk(browser)
    assert seen == ["welcome", "signin", "install", "repository", "pages", "site"]
    assert "Setup is done." in done


def test_signing_in_again_sits_behind_the_faces_boundary(tmp_path, monkeypatch):
    """INV-13. Breaks when the page is served by its own handler."""
    _app(monkeypatch)
    _saved(tmp_path)
    _Store(monkeypatch, saved_key=FIRST_REFRESH)
    github = _SignInGitHub()
    with _setup_page(tmp_path, github, clock=_Clock()) as browser:
        assert browser.post({}, cookie=False, path="/setup/github")[0] == 403
        assert browser.post({}, origin="http://pressless.example", path="/setup/github")[0] == 403
        assert github.calls == []
        status, page = browser.post({}, path="/setup/github")
    assert status == 200 and USER_CODE in page
