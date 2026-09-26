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
import http.client
import inspect
import json
import re
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import session_cookie

from pressless import builder, credentials, face, settings, setup, store

KEY_NOUN = "your publishing key"
SENTINEL_KEY = "ghp_SENTINELkey0123456789abcdef"
LOG_NAME = "pressless.log"

ROOT = ("CNAME", "assets", "content", "index.html")
DERIVED = ("CNAME", "assets")

ANSWERS = {
    "repository": "owner/owner.github.io",
    "site_name": "A Journal",
    "site_address": "https://example.org",
    "daily_prompt_filter": "",
    "key": SENTINEL_KEY,
}


class _GitHub:
    """A recording double for the Publisher's Transport, answering by URL.

    `refuse` maps a URL substring to the status that address answers with.
    Everything else answers as a repository whose root holds `root`.
    """

    def __init__(self, root: tuple[str, ...] = ROOT, refuse: dict[str, int] | None = None):
        self.root = root
        self.refuse = refuse or {}
        self.calls: list[tuple[str, str, str]] = []

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((method, url, headers.get("Authorization", "")))
        for fragment, status in self.refuse.items():
            if fragment in url:
                return status, {}, b'{"message": "refused"}'
        if url.endswith("/commits/HEAD"):
            return 200, {}, json.dumps({"sha": "abc123"}).encode()
        if "/git/trees/abc123" in url:
            tree = [{"path": name, "type": "blob"} for name in self.root]
            return 200, {}, json.dumps({"tree": tree}).encode()
        return 404, {}, b'{"message": "Not Found"}'

    def wait(self, seconds: float) -> None:
        return None


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


class _Browser:
    """Talks to a served Face with the cookie and Origin under the test's control."""

    def __init__(self, served: face.Face) -> None:
        parts = urllib.parse.urlsplit(served.url)
        assert parts.port is not None
        self.port = parts.port
        self.host = f"127.0.0.1:{self.port}"
        self.origin = f"http://{self.host}"
        self.cookie = session_cookie(served.url)

    def _send(self, method: str, body: bytes, *, cookie: bool, origin: str | None
              ) -> tuple[int, str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, "/setup", skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", self.host)
            if cookie:
                conn.putheader("Cookie", self.cookie)
            if origin:
                conn.putheader("Origin", origin)
            if method == "POST":
                conn.putheader("Content-Type", "application/x-www-form-urlencoded")
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body if method == "POST" else None)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def get(self) -> tuple[int, str]:
        return self._send("GET", b"", cookie=True, origin=None)

    def post(self, answers: dict[str, str], *, cookie: bool = True,
             origin: str | None = "own") -> tuple[int, str]:
        body = urllib.parse.urlencode(answers).encode("utf-8")
        return self._send("POST", body, cookie=cookie,
                          origin=self.origin if origin == "own" else origin)


@contextlib.contextmanager
def _setup_page(folder: Path, github: _GitHub) -> Iterator[_Browser]:
    served = face.serve(folder, open_browser=False)
    try:
        setup.register(served, folder, transport=github)
        yield _Browser(served)
    finally:
        served.stop()


def _answers(**changes: str) -> dict[str, str]:
    return {**ANSWERS, **changes}


def _saved(folder: Path, **changes) -> settings.Settings:
    """Save a settings file in `folder`, as an earlier setup would have."""
    value = settings.Settings(
        site_folder=folder / "site",
        repository="owner/owner.github.io",
        site_name="A Journal",
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
    """INV-1. Breaks when credentials.write or choose moves ahead of
    root_entries, or the address check is dropped and the form reaches GitHub."""
    keyring = _Store(monkeypatch)

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

    assert not _settings_file(tmp_path).exists()
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
        browser.post(_answers())
    assert not _settings_file(first).exists()

    second = tmp_path / "write-fails"
    second.mkdir()
    keyring = _Store(monkeypatch, write_raises=credentials.NoStore("none here"))
    with _setup_page(second, _GitHub()) as browser:
        browser.post(_answers())
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
    assert not _offers_the_form(shown)
    assert _settings_file(refused).read_bytes() == before
    assert github.calls == []
    assert keyring.chosen == 0 and keyring.writes == []

    carried = tmp_path / "carried"
    carried.mkdir()
    _saved(carried, site_folder=Path("site"))
    with _setup_page(carried, _GitHub()) as browser:
        _, shown = browser.get()
    assert _offers_the_form(shown)


# --------------------------------------------------------------- INV-5 ----


def test_setup_works_on_an_empty_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-5. Breaks when setup calls into the Store at all."""
    touched: list[str] = []

    def refuse(name: str):
        def refused(*args, **kwargs):
            touched.append(name)
            raise AssertionError(f"setup called store.{name}")
        return refused

    for name, function in inspect.getmembers(store, inspect.isfunction):
        if not name.startswith("_") and function.__module__ == store.__name__:
            monkeypatch.setattr(store, name, refuse(name))
    _Store(monkeypatch)

    with _setup_page(tmp_path, _GitHub()) as browser:
        _, shown = browser.get()
        browser.post(_answers())
    assert _offers_the_form(shown)
    assert touched == []
    assert settings.load(tmp_path).repository == "owner/owner.github.io"


# --------------------------------------------------------------- INV-6 ----


def test_the_key_is_never_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """INV-6. Breaks when the re-rendered form fills the key box, or the done
    page echoes it."""
    cases = [
        ("success", _GitHub(), _answers()),
        ("refused site name", _GitHub(), _answers(site_name=" ")),
        ("refused key", _GitHub(refuse={"/commits/HEAD": 401}), _answers()),
    ]
    for label, github, answers in cases:
        folder = tmp_path / label.replace(" ", "-")
        folder.mkdir()
        _Store(monkeypatch)
        with _setup_page(folder, github) as browser:
            _, page = browser.post(answers)
        captured = capfd.readouterr()
        assert SENTINEL_KEY not in page, label
        assert SENTINEL_KEY not in _log(folder), label
        assert SENTINEL_KEY not in captured.out + captured.err, label
        for field in _key_inputs(page):
            assert "value=" not in field, label
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
        _, page = browser.post(_answers(key=""))
    assert _offers_the_form(page) and _hint_for("key", page)
    assert github.calls == [] and keyring.writes == []
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
            browser.post(_answers())
        assert settings.load(folder) == settings.Settings(
            site_folder=folder / "site",
            repository="owner/owner.github.io",
            site_name="A Journal",
            site_address="https://example.org",
            daily_prompt_filter="",
            untouchable=DERIVED,
            credentials=settings.Credentials(store=answered, github_account="github",
                                             google_account=None),
            analytics_property_id=None,
        ), answered


# -------------------------------------------------------------- INV-12 ----


def test_a_malformed_key_is_refused_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-12. Breaks when the key check is dropped.

    A line break and a space are the spec's two cases, and both are
    whitespace. A control character and a non-ASCII letter are not, so they
    are what show the printable and ASCII halves of § 4.4's rule held."""
    for malformed in ("ghp_abc\ndef", "ghp_abc def", "ghp_abc\x00def", "ghp_abcédef"):
        _Store(monkeypatch)
        github = _GitHub()
        with _setup_page(tmp_path, github) as browser:
            _, page = browser.post(_answers(key=malformed))
        assert github.calls == [], repr(malformed)
        assert _offers_the_form(page) and _hint_for("key", page), repr(malformed)


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
        _, page = browser.post(_answers())
    assert KEY_NOUN in page

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
    """INV-14. Breaks when setup serves its own handler or never registers on
    the Face."""
    _Store(monkeypatch)
    with _setup_page(tmp_path, _GitHub()) as browser:
        assert browser.post(_answers(), cookie=False)[0] == 403
        assert browser.post(_answers(), origin="http://pressless.example")[0] == 403
        assert not _settings_file(tmp_path).exists()
        assert browser.post(_answers())[0] == 200
    assert _settings_file(tmp_path).exists()


# -------------------------------------------------------------- INV-15 ----


def test_the_filter_is_the_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-15. Breaks when first run writes a default filter, or Settings
    carries the saved filter forward in place of the answer."""
    first_run = tmp_path / "first-run"
    first_run.mkdir()
    _Store(monkeypatch)
    with _setup_page(first_run, _GitHub()) as browser:
        browser.post(_answers(daily_prompt_filter=""))
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
    """PRESS-0127 INV-9. Breaks when root_entries raises on the empty answer,
    or setup starts the repository itself."""
    _Store(monkeypatch)
    github = _EmptyGitHub()

    with _setup_page(tmp_path, github) as browser:
        status, page = browser.post(_answers())

    assert status == 200
    assert "Setup is done." in page
    assert settings.load(tmp_path).untouchable == ()
    assert github.calls, "setup never asked GitHub, so this proved nothing"
    assert [method for method, _url, _auth in github.calls if method != "GET"] == []
