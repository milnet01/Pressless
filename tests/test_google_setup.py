# Setup's second step: signing in with Google (PRESS-0122 § 4.2 to § 4.5).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0122-google-signin.md § 5. Every server is started inside
# the test that uses it. Google is a recording double answering by address,
# and the credential store is a recording double: no test reaches Google or
# the machine's real keyring.
from __future__ import annotations

import contextlib
import dataclasses
import json
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser

from pressless import (
    credentials,
    face,
    google_setup,
    google_signin,
    insights,
    settings,
    setup,
    starter,
    store,
)

CLIENT = "client.apps.googleusercontent.com"
SECRET = "sentinel-client-secret"  # noqa: S105 -- a sentinel, not a secret
RETURN = "/setup/google/back"
PERMISSIONS = "https://myaccount.google.com/permissions"
LOG_NAME = "pressless.log"

NEW_REFRESH = "1//SENTINELnewrefresh0123456789"
OLD_REFRESH = "1//SENTINELoldrefresh0123456789"
LISTED = ("111", "222")


class _Google:
    """A Transport double answering by address. A refresh token's access
    token is its own text with `access-` in front, so a test can tell which
    sign-in a token came from."""

    def __init__(self, *, revoke: BaseException | int = 200, exchange: int = 200,
                 listed: tuple[str, ...] = LISTED, streams: list | None = None) -> None:
        self.clock = 1000.0
        self.calls: list[tuple[str, str, dict[str, list[str]]]] = []
        self.revoke = revoke
        self.exchange = exchange
        self.listed = listed
        self.streams = streams     # PRESS-0199: a property's data streams

    def request(self, method, url, body, headers):
        form = urllib.parse.parse_qs((body or b"").decode())
        self.calls.append((method, url, form))
        if url.startswith("https://oauth2.googleapis.com/token"):
            if form["grant_type"] == ["authorization_code"]:
                if self.exchange != 200:
                    return self.exchange, {}, json.dumps({"error": "invalid_request"}).encode()
                return 200, {}, json.dumps({"refresh_token": NEW_REFRESH}).encode()
            refresh = form["refresh_token"][0]
            return 200, {}, json.dumps({"access_token": f"access-{refresh}",
                                        "expires_in": 3600}).encode()
        if "/dataStreams" in url:
            return 200, {}, json.dumps({"dataStreams": self.streams or []}).encode()
        if url.startswith("https://analyticsadmin.googleapis.com/"):
            summaries = [{"property": f"properties/{p}", "displayName": f"Site {p}"}
                         for p in self.listed]
            return 200, {}, json.dumps({"accountSummaries": [
                {"displayName": "Mine", "propertySummaries": summaries}]}).encode()
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            if isinstance(self.revoke, BaseException):
                raise self.revoke
            return self.revoke, {}, b""
        return 404, {}, b""

    def now(self) -> float:
        return self.clock

    def token_requests(self) -> int:
        return sum(1 for _m, url, _f in self.calls if url.endswith("/token"))


class _Store:
    """Recording doubles for credentials.read and write."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, saved: str = OLD_REFRESH) -> None:
        self.writes: list[tuple[str, str, str]] = []
        self.saved = saved

        def read(kind: str, folder: Path, account: str) -> str:
            return self.saved

        def write(kind: str, folder: Path, account: str, secret: str) -> None:
            self.writes.append((kind, account, secret))
            self.saved = secret

        monkeypatch.setattr(credentials, "read", read)
        monkeypatch.setattr(credentials, "write", write)


class _Browser(Browser):
    def __init__(self, served: face.Face) -> None:
        super().__init__(served)
        self.pages: list[str] = []

    def send(self, method: str, path: str, fields: dict[str, str] | None = None, *,
             cookie: bool = True) -> tuple[int, dict[str, str], str]:
        status, headers, text = self.request(method, path, fields, cookie=cookie)
        self.pages.append(text)
        return status, headers, text

    def start(self) -> str:
        """Press Sign in with Google; the state Google would carry back."""
        status, headers, _ = self.send("POST", "/setup/google/start")
        assert status == 303, status
        address = headers["Location"]
        assert address.startswith("https://accounts.google.com/")
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(address).query))["state"]

    def come_back(self, state: str) -> tuple[int, str]:
        """Google's redirect: no cookie, as a SameSite=Strict one never rides it."""
        query = urllib.parse.urlencode({"state": state, "code": "4/code"})
        status, _, page = self.send("GET", f"{RETURN}?{query}", cookie=False)
        return status, page


@contextlib.contextmanager
def _served(folder: Path, google: _Google, *, with_setup: bool = False
            ) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        if with_setup:
            setup.register(served, folder)
        google_setup.register(served, folder, client=google)
        yield _Browser(served)
    finally:
        served.stop()


def _saved(folder: Path, **changes) -> settings.Settings:
    value = settings.Settings(
        site_folder=folder / "site",
        repository="owner/owner.github.io",
        site_address="https://example.org",
        daily_prompt_filter="",
        untouchable=("CNAME",),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None,
    )
    value = dataclasses.replace(value, **changes)
    settings.save(folder, value)
    return value


def _signed_in(folder: Path) -> settings.Settings:
    return _saved(folder, credentials=settings.Credentials(
        store="keyring", github_account="github", google_account="google"),
        analytics_property_id="999")


@pytest.fixture
def registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(google_signin, "CLIENT_ID", CLIENT)
    monkeypatch.setattr(google_signin, "CLIENT_SECRET", SECRET)


# -------------------------------------------------------------- INV-10 ----


def test_the_return_is_honoured_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                     registered: None) -> None:
    """INV-10. Breaks when a wrong state spends the attempt, or the right one
    is accepted twice."""
    _Store(monkeypatch)
    _saved(tmp_path)
    with _served(tmp_path, _Google()) as browser:
        assert browser.come_back("no-attempt")[0] == 403
        state = browser.start()
        assert browser.come_back("wrong")[0] == 403
        status, page = browser.come_back(state)
        assert status == 200 and 'href="/setup/google"' in page
        assert browser.come_back(state)[0] == 403


# -------------------------------------------------------------- INV-11 ----


def test_the_sign_in_is_stored_and_never_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    registered: None,
) -> None:
    """INV-11. Breaks when the return page echoes Google's answer, or a
    failure's detail carries the token."""
    store = _Store(monkeypatch)
    _saved(tmp_path)
    with _served(tmp_path, _Google()) as browser:
        browser.come_back(browser.start())
        browser.send("GET", "/setup/google")
        browser.send("POST", "/setup/google/choose", {"property": "111"})
        browser.send("GET", "/setup/google")
    assert store.writes == [("keyring", "google", NEW_REFRESH)]
    log = (tmp_path / LOG_NAME).read_text(encoding="utf-8") \
        if (tmp_path / LOG_NAME).exists() else ""
    shown = "".join(browser.pages) + log + capsys.readouterr().out
    assert NEW_REFRESH not in shown


# -------------------------------------------------------------- INV-12 ----


def test_only_a_listed_property_is_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         registered: None) -> None:
    """INV-12. Breaks when the return page saves the first property or stores
    the new sign-in, or choose trusts the posted id."""
    store = _Store(monkeypatch)
    _signed_in(tmp_path)
    before = settings.path_for(tmp_path).read_bytes()
    google = _Google()
    with _served(tmp_path, google) as browser:
        assert google_setup.token(tmp_path) == f"access-{OLD_REFRESH}"
        browser.come_back(browser.start())
        assert settings.path_for(tmp_path).read_bytes() == before
        assert store.writes == []
        assert google_setup.token(tmp_path) == f"access-{OLD_REFRESH}"

        status, _, page = browser.send("POST", "/setup/google/choose", {"property": "999"})
        assert status == 200 and 'id="property-hint"' in page and 'value="111"' in page
        assert settings.path_for(tmp_path).read_bytes() == before

        browser.send("POST", "/setup/google/choose", {"property": LISTED[1]})
    saved = settings.load(tmp_path)
    assert saved.credentials.google_account == "google"
    assert saved.analytics_property_id == LISTED[1]


# -------------------------------------------------------------- INV-13 ----


@pytest.mark.parametrize("revoke", [200, OSError("offline")])
def test_turning_off_clears_both_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                        registered: None, revoke) -> None:
    """INV-13. Breaks when a failed revoke stops the save, so offline he
    cannot turn the dashboard off."""
    _Store(monkeypatch)
    _signed_in(tmp_path)
    google = _Google(revoke=revoke)
    with _served(tmp_path, google) as browser:
        status, _, page = browser.send("POST", "/setup/google/off")
    assert status == 200
    assert any(url.endswith("/revoke") and form == {"token": [OLD_REFRESH]}
               for _m, url, form in google.calls)
    saved = settings.load(tmp_path)
    assert saved.credentials.google_account is None
    assert saved.analytics_property_id is None
    assert (PERMISSIONS in page) == (revoke != 200)


# -------------------------------------------------------------- INV-14 ----


def test_the_token_is_reused_until_it_nearly_expires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registered: None
) -> None:
    """INV-14. Breaks when every dashboard view refreshes, or a token from
    before Turn off is still handed out."""
    _Store(monkeypatch)
    _signed_in(tmp_path)
    google = _Google()
    with _served(tmp_path, google) as browser:
        assert google_setup.token(tmp_path) == f"access-{OLD_REFRESH}"
        assert google.token_requests() == 1
        google.clock += 3600 - 61
        google_setup.token(tmp_path)
        assert google.token_requests() == 1
        google.clock += 2
        google_setup.token(tmp_path)
        assert google.token_requests() == 2

        browser.come_back(browser.start())
        browser.send("POST", "/setup/google/choose", {"property": "111"})
        asked = google.token_requests()
        assert google_setup.token(tmp_path) == f"access-{NEW_REFRESH}"
        assert google.token_requests() == asked

        browser.send("POST", "/setup/google/off")
        with pytest.raises(insights.NotConfigured):
            google_setup.token(tmp_path)


# -------------------------------------------------------------- INV-15 ----


@pytest.mark.parametrize("empty", ["CLIENT_ID", "CLIENT_SECRET"])
def test_an_unregistered_copy_offers_no_sign_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registered: None, empty: str
) -> None:
    """INV-15. Breaks when the button is shown and Google answers him with an
    error page about a missing client, or a missing secret."""
    monkeypatch.setattr(google_signin, empty, "")
    _Store(monkeypatch)
    _saved(tmp_path)
    google = _Google()
    with _served(tmp_path, google, with_setup=True) as browser:
        page = browser.send("GET", "/setup/google")[2]
        assert "Sign in with Google" not in page and "/setup/google/start" not in page
        status, headers, _ = browser.send("POST", "/setup/google/start")
        assert status == 200 and "Location" not in headers
        assert 'href="/setup/google"' not in browser.send("GET", "/setup")[2]

        monkeypatch.setattr(google_signin, empty, {"CLIENT_ID": CLIENT,
                                                    "CLIENT_SECRET": SECRET}[empty])
        # The control: with a client, the same pages offer it.
        assert "Sign in with Google" in browser.send("GET", "/setup/google")[2]
        assert 'href="/setup/google"' in browser.send("GET", "/setup")[2]
    assert [url for _m, url, _f in google.calls] == []


# -------------------------------------------------------------- INV-17 ----


@pytest.mark.parametrize("google", [
    pytest.param(lambda: _Google(exchange=400), id="exchange-fails"),
    pytest.param(lambda: _Google(listed=()), id="no-property"),
])
def test_a_failed_return_stays_on_screen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         registered: None, google) -> None:
    """INV-17. Breaks when the refresh is added to every return, and the
    failure flashes past before it can be read -- which the first real
    sign-in measured."""
    _Store(monkeypatch)
    _saved(tmp_path)
    with _served(tmp_path, google()) as browser:
        status, page = browser.come_back(browser.start())
    assert status == 200
    assert 'href="/setup/google"' in page
    assert 'http-equiv="refresh"' not in page
    assert "You are signed in" not in page
    assert ('class="failure"' in page) or ("No Analytics site found" in page)

    # The control: a return that worked moves on by itself.
    with _served(tmp_path, _Google()) as browser:
        assert 'http-equiv="refresh"' in browser.come_back(browser.start())[1]


# ----------------------------------------------------------- PRESS-0206 ----


def test_a_different_site_is_chosen_without_signing_in_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registered: None
) -> None:
    """PRESS-0206. Breaks when Choose a different site sends him to Google,
    or changes anything before he picks a site."""
    store = _Store(monkeypatch)
    _signed_in(tmp_path)
    before = settings.path_for(tmp_path).read_bytes()
    google = _Google()
    with _served(tmp_path, google) as browser:
        assert "/setup/google/sites" in browser.send("GET", "/setup/google")[2]
        status, headers, page = browser.send("POST", "/setup/google/sites")
        assert status == 200 and "Location" not in headers
        assert 'value="111"' in page and 'value="222"' in page
        assert settings.path_for(tmp_path).read_bytes() == before
        browser.send("POST", "/setup/google/choose", {"property": "222"})
    assert not any(form.get("grant_type") == ["authorization_code"]
                   for _m, _url, form in google.calls)
    saved = settings.load(tmp_path)
    assert saved.credentials.google_account == "google"
    assert saved.analytics_property_id == "222"
    assert store.saved == OLD_REFRESH


class _Offline(_Google):
    def request(self, method, url, body, headers):
        raise OSError("offline")


@pytest.mark.parametrize("google", [
    pytest.param(lambda: _Google(listed=()), id="no-property"),
    pytest.param(_Offline, id="offline"),
])
def test_a_failed_listing_stays_on_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registered: None, google
) -> None:
    """PRESS-0206. Breaks when a listing that failed, or found no site,
    changes the settings or moves on before he has read it."""
    _Store(monkeypatch)
    _signed_in(tmp_path)
    before = settings.path_for(tmp_path).read_bytes()
    with _served(tmp_path, google()) as browser:
        status, _, page = browser.send("POST", "/setup/google/sites")
    assert status == 200
    assert ('class="failure"' in page) or ("No Analytics site found" in page)
    assert 'href="/setup/google"' in page and 'http-equiv="refresh"' not in page
    assert settings.path_for(tmp_path).read_bytes() == before


# ------------------------------------------------------------ PRESS-0207 ----


@pytest.mark.parametrize("signed_in", [False, True])
def test_settings_names_visitor_numbers_once_they_are_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registered: None, signed_in: bool
) -> None:
    """PRESS-0207. Breaks when Settings still offers visitor numbers as a
    first-time option after they are set up, which is where the user looked
    for them and did not find them."""
    _Store(monkeypatch)
    (_signed_in if signed_in else _saved)(tmp_path)
    with _served(tmp_path, _Google(), with_setup=True) as browser:
        page = browser.send("GET", "/setup")[2]
    assert 'href="/setup/google"' in page
    assert ("Visitor numbers are on" in page) is signed_in
    assert ("Optional: " in page) is not signed_in


# PRESS-0199 INV-6 (docs/specs/PRESS-0199-counting-code.md § 4.3).

STREAM = [{"type": "WEB_DATA_STREAM",
           "webStreamData": {"measurementId": "G-ABC123", "defaultUri": "https://example.org"}}]


def test_choosing_a_property_switches_counting_on(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch,
                                                  registered: None) -> None:
    """INV-6. Breaks when the found id is not saved, overwrites a typed one,
    or the Privacy page is not added."""
    _Store(monkeypatch)
    for case, typed in (("found", None), ("typed", "G-TYPED1")):
        folder = tmp_path / case
        folder.mkdir()
        _saved(folder, measurement_id=typed)
        starter.fill(folder, "A Journal")
        with _served(folder, _Google(streams=STREAM)) as browser:
            browser.come_back(browser.start())
            browser.send("GET", "/setup/google")
            browser.send("POST", "/setup/google/choose", {"property": "111"})
        assert settings.load(folder).measurement_id == (typed or "G-ABC123"), case
        assert store.html_path_for(folder, store.PAGES_FOLDER, "privacy").is_file(), case
        footer = store.read_html(store.html_path_for(folder, store.FURNITURE_FOLDER, "footer"))
        assert footer.count("pages/privacy.html") == 1, case


# PRESS-0200: until Google approves the client, the page says so.


@pytest.mark.parametrize("approved", [False, True])
def test_the_page_says_while_google_has_not_approved_pressless(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registered: None, approved: bool
) -> None:
    """Breaks when the page explains Google's warning without saying the
    review is still pending, or keeps both once Google has approved."""
    monkeypatch.setattr(google_signin, "APPROVED", approved)
    _Store(monkeypatch)
    _saved(tmp_path)
    with _served(tmp_path, _Google()) as browser:
        page = browser.send("GET", "/setup/google")[2]
    assert "Sign in with Google" in page
    assert ("still checking Pressless" in page) is not approved
    assert ("<strong>Go to Pressless</strong>" in page) is not approved
