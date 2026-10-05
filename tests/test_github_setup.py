# The GitHub pass, and signing in to GitHub again (PRESS-0231 § 4.2, § 4.4).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0231-github-sign-in.md § 5. Every server is started inside
# the test that uses it. GitHub's sign-in endpoint is a recording double, the
# clock is a fake, and the credential store is a recording double: no test
# reaches GitHub or the machine's real keyring. Secrets are plain words, so the
# push gate's secret scanner does not mistake them.
from __future__ import annotations

import contextlib
import json
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser
from test_publishing import _base, _entry
from test_publishing import _Browser as _PublishBrowser
from test_publishing import _folder as _publishing_folder
from test_publishing import _github as _publishing_github

from pressless import (
    credentials,
    editor,
    face,
    github_setup,
    github_signin,
    publishing,
    settings,
    setup,
    store,
)

KEY = "ghp_plain-hand-made-key"
REFRESH = "ghr_plain-first-refresh"
SECOND_REFRESH = "ghr_plain-second-refresh"
SECOND_ACCESS = "ghu_plain-second-access"
USER_CODE = "WDJB-MJHT"
PAGE = "/setup/github"
START = 1000.0


class _GitHub:
    """github.com's sign-in endpoints as a recording double. The n-th refresh
    hands back `ghu_renewed-n` and `ghr_renewed-n`, so a test can tell which
    renewal a pass came from; with `refuse`, every refresh is refused. A poll
    of a device code answers with the second sign-in's tokens."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.sent: list[tuple[str, str, dict[str, list[str]], dict[str, str]]] = []

    def request(self, method, url, body, headers):
        form = urllib.parse.parse_qs((body or b"").decode())
        self.sent.append((method, url, form, headers))
        if url == "https://github.com/login/device/code":
            return 200, {}, json.dumps({
                "device_code": "plain-device-code", "user_code": USER_CODE,
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900, "interval": 5}).encode()
        if form.get("grant_type") == ["refresh_token"]:
            if self.refuse:
                spent = form["refresh_token"][0]
                return 200, {}, json.dumps({"error": "bad_refresh_token",
                                            "error_description": f"{spent} is spent"}).encode()
            n = self.refreshes()
            return 200, {}, json.dumps({"access_token": f"ghu_renewed-{n}",
                                        "refresh_token": f"ghr_renewed-{n}",
                                        "expires_in": 28800}).encode()
        return 200, {}, json.dumps({"access_token": SECOND_ACCESS,
                                    "refresh_token": SECOND_REFRESH,
                                    "expires_in": 28800}).encode()

    def wait(self, seconds: float) -> None:
        return None

    def refreshes(self) -> int:
        return sum(1 for _m, _u, form, _h in self.sent
                   if form.get("grant_type") == ["refresh_token"])


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now


class _Store:
    """Recording doubles for credentials.read and write; a write is what the
    next read returns."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, saved: str,
                 write_raises: Exception | None = None) -> None:
        self.saved = saved
        self.writes: list[tuple[str, str, str]] = []

        def read(kind: str, folder: Path, account: str) -> str:
            return self.saved

        def write(kind: str, folder: Path, account: str, secret: str) -> None:
            if write_raises is not None:
                raise write_raises
            self.writes.append((kind, account, secret))
            self.saved = secret

        monkeypatch.setattr(credentials, "read", read)
        monkeypatch.setattr(credentials, "write", write)


@pytest.fixture(autouse=True)
def _registered(monkeypatch):
    monkeypatch.setattr(github_signin, "CLIENT_ID", "Iv1.plain-client")
    monkeypatch.setattr(github_signin, "APP_SLUG", "pressless-app")


@contextlib.contextmanager
def _served(folder: Path, github: _GitHub, clock: _Clock, *,
            with_setup: bool = False) -> Iterator[Browser]:
    served = face.serve(folder)
    try:
        if with_setup:
            setup.register(served, folder)
        github_setup.register(served, folder, transport=github, clock=clock)
        yield Browser(served)
    finally:
        served.stop()


def _saved(folder: Path) -> None:
    settings.save(folder, settings.Settings(
        site_folder=folder / "site", repository="owner/owner.github.io",
        site_address="https://example.org", daily_prompt_filter="", untouchable=(),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))


def _token(folder: Path) -> str:
    return github_setup.token(folder, "keyring", "github")


def test_a_key_is_used_and_a_refresh_token_is_not(tmp_path, monkeypatch):
    """INV-1. Breaks when every secret is refreshed, or the stored secret is
    sent as the bearer token."""
    github = _GitHub()
    keyring = _Store(monkeypatch, KEY)
    with _served(tmp_path, github, _Clock()):
        assert _token(tmp_path) == KEY
        assert github.sent == []
        keyring.saved = REFRESH
        assert _token(tmp_path) == "ghu_renewed-1"
    assert github.refreshes() == 1
    assert all(REFRESH not in headers.get("Authorization", "")
               for _m, _u, _f, headers in github.sent)


def test_the_pass_is_renewed_when_nearly_spent(tmp_path, monkeypatch):
    """INV-2. Breaks when every call refreshes, the held token is used past
    expiry, or the new refresh token is not stored."""
    github = _GitHub()
    clock = _Clock()
    keyring = _Store(monkeypatch, REFRESH)
    with _served(tmp_path, github, clock):
        first = _token(tmp_path)
        clock.now = START + 3600
        assert _token(tmp_path) == first == "ghu_renewed-1"
        assert github.refreshes() == 1
        clock.now = START + 7 * 3600 + 59.5 * 60
        assert _token(tmp_path) == "ghu_renewed-2"
        assert github.refreshes() == 2
    assert keyring.writes == [("keyring", "github", "ghr_renewed-1"),
                              ("keyring", "github", "ghr_renewed-2")]

    # The new refresh token is stored before the pass is used: a write that
    # fails returns no token, and holds none for the next call to use.
    github = _GitHub()
    _Store(monkeypatch, REFRESH, write_raises=credentials.CredentialError("locked"))
    with _served(tmp_path, github, _Clock()):
        with pytest.raises(credentials.CredentialError):
            _token(tmp_path)
        with pytest.raises(credentials.CredentialError):
            _token(tmp_path)
    assert github.refreshes() == 2


def test_a_lapsed_sign_in_says_sign_in_again(tmp_path, monkeypatch):
    """INV-11. Breaks when the failure reads as a refused key, or the publish
    goes on with no token."""
    folder = _publishing_folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    _Store(monkeypatch, REFRESH)
    writes = _publishing_github()
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=writes)
        github_setup.register(served, folder, transport=_GitHub(refuse=True), clock=_Clock())
        status, text = _PublishBrowser(served).publish(
            "seaside", True, _base(folder, "seaside", draft=True), folder=folder)
    finally:
        served.stop()
    assert status == 200, text
    reply = json.loads(text)
    assert reply["published"] is False
    assert "GitHub has signed Pressless out." in reply["failure"]
    assert "Your site has not changed." in reply["failure"]
    assert f'href="{PAGE}"' in reply["failure"]
    assert "would not accept your publishing key" not in reply["failure"]
    assert REFRESH not in reply["failure"]
    assert writes.requests == []


def test_signing_in_again_replaces_the_pass(tmp_path, monkeypatch):
    """INV-12. Breaks when the old held token outlives the new sign-in."""
    _saved(tmp_path)
    github = _GitHub()
    keyring = _Store(monkeypatch, REFRESH)
    with _served(tmp_path, github, _Clock()) as browser:
        assert _token(tmp_path) == "ghu_renewed-1"
        status, _, page = browser.request("POST", PAGE)
        assert status == 200 and USER_CODE in page, page
        status, headers, _ = browser.request("POST", PAGE)
        assert status == 303 and headers["Location"] == "/setup"
        assert keyring.saved == SECOND_REFRESH
        assert _token(tmp_path) == SECOND_ACCESS
    assert github.refreshes() == 1


def test_settings_says_it_is_signed_in(tmp_path, monkeypatch):
    """§ 4.4: the line above the key box, only where the stored secret is a
    sign-in."""
    _saved(tmp_path)
    keyring = _Store(monkeypatch, REFRESH)
    with _served(tmp_path, _GitHub(), _Clock(), with_setup=True) as browser:
        signed_in = browser.request("GET", "/setup")[2]
        keyring.saved = KEY
        with_a_key = browser.request("GET", "/setup")[2]
    assert "Pressless is signed in to GitHub" in signed_in
    assert f'href="{PAGE}"' in signed_in
    assert "Pressless is signed in to GitHub" not in with_a_key
