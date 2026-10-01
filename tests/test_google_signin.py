# Signing in with Google, the Insights half (PRESS-0122 § 4.1).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0122-google-signin.md § 5. Google's addresses are written
# out here rather than imported, so the tests do not compare the module
# against itself. No test reaches Google: every request goes to a recording
# double that answers from a script.
from __future__ import annotations

import ast
import base64
import hashlib
import inspect
import json
import string
import urllib.parse

import pytest

from pressless import google_signin, insights

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 -- an address
ACCOUNTS_URL = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
REDIRECT = "http://127.0.0.1:5555/setup/google/back"

REFRESH = "1//SENTINELrefresh0123456789"
ACCESS = "ya29.SENTINELaccess0123456789"
CODE = "4/SENTINELcode0123456789"
SECRET = "sentinel-client-secret"  # noqa: S105 -- a sentinel, not a secret
CLIENT = "client.apps.googleusercontent.com"


class _Google:
    """A Transport double: records every request, answers from `answers` in
    order (a tuple of status and body, or an exception to raise)."""

    def __init__(self, *answers, clock: float = 1000.0) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str, bytes | None, dict[str, str]]] = []
        self.clock = clock

    def request(self, method, url, body, headers):
        self.calls.append((method, url, body, dict(headers)))
        answer = self.answers.pop(0) if self.answers else (500, b"")
        if isinstance(answer, BaseException):
            raise answer
        status, data = answer
        if isinstance(data, (dict, list)):
            data = json.dumps(data).encode()
        return status, {}, data

    def now(self) -> float:
        return self.clock


def _attempt(client: _Google):
    attempt, _address = google_signin.begin(REDIRECT, client)
    return attempt


def _form(body: bytes | None) -> dict[str, list[str]]:
    return urllib.parse.parse_qs((body or b"").decode())


# --------------------------------------------------------------- INV-1 ----


def test_signin_imports_only_insights_and_its_secret():
    """INV-1. Breaks when it imports credentials or settings to fetch the
    token or the property id itself (docs/design.md rule 10)."""
    tree = ast.parse(inspect.getsource(google_signin))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "pressless":
                imported.update(alias.name for alias in node.names)
            elif node.module.startswith("pressless."):
                imported.add(node.module.split(".")[1])
            assert node.level == 0, "no relative imports"
        elif isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[1] for alias in node.names
                            if alias.name.startswith("pressless."))
    assert imported == {"insights", "_google_secret"}, imported


# --------------------------------------------------------------- INV-2 ----


def test_begin_builds_a_pkce_address(monkeypatch: pytest.MonkeyPatch):
    """INV-2. Breaks when the challenge is the plain verifier, the state is
    fixed, or access_type=offline is dropped."""
    monkeypatch.setattr(google_signin, "CLIENT_ID", "client.apps.googleusercontent.com")
    client = _Google()
    first, address = google_signin.begin(REDIRECT, client)
    second, _ = google_signin.begin(REDIRECT, client)

    parts = urllib.parse.urlsplit(address)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == \
        "https://accounts.google.com/o/oauth2/v2/auth"
    query = dict(urllib.parse.parse_qsl(parts.query))
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(first.verifier.encode()).digest()).rstrip(b"=").decode()
    assert query == {
        "client_id": "client.apps.googleusercontent.com",
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/analytics.readonly",
        "state": first.state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    unreserved = set(string.ascii_letters + string.digits + "-._~")
    assert 43 <= len(first.verifier) <= 128 and set(first.verifier) <= unreserved
    assert first.state != second.state and first.verifier != second.verifier
    assert first.redirect_uri == REDIRECT and first.started == client.clock
    assert client.calls == []


# --------------------------------------------------------------- INV-3 ----


def test_finish_refuses_before_any_request():
    """INV-3. Breaks when the exchange runs first and the state is compared
    after."""
    client = _Google((200, {"refresh_token": REFRESH}))
    attempt = _attempt(client)

    with pytest.raises(google_signin.Expired):
        google_signin.finish(attempt, {"state": "not-it", "code": CODE}, client)

    client.clock += 601.0
    with pytest.raises(google_signin.Expired):
        google_signin.finish(attempt, {"state": attempt.state, "code": CODE}, client)
    client.clock -= 601.0

    with pytest.raises(google_signin.Declined):
        google_signin.finish(attempt, {"state": attempt.state, "error": "access_denied"},
                             client)
    assert client.calls == []


# --------------------------------------------------------------- INV-4 ----


def test_the_secret_goes_only_to_the_token_endpoint(monkeypatch: pytest.MonkeyPatch):
    """INV-4. Breaks when the secret is dropped from the refresh, after which
    every dashboard read after the first hour fails; or it is sent to the
    Admin API."""
    monkeypatch.setattr(google_signin, "CLIENT_ID", CLIENT)
    monkeypatch.setattr(google_signin, "CLIENT_SECRET", SECRET)
    client = _Google((200, {"refresh_token": REFRESH}),
                     (200, {"access_token": ACCESS, "expires_in": 3599}),
                     (200, {}), (200, b""))
    attempt = _attempt(client)
    assert google_signin.finish(attempt, {"state": attempt.state, "code": CODE},
                                client) == REFRESH
    token = google_signin.access_token(REFRESH, client)
    google_signin.properties(ACCESS, client)
    google_signin.revoke(REFRESH, client)

    (m1, url1, body1, _), (m2, url2, body2, _), *others = client.calls
    assert (m1, url1, m2, url2) == ("POST", TOKEN_URL, "POST", TOKEN_URL)
    assert _form(body1) == {
        "code": [CODE], "client_id": [CLIENT], "client_secret": [SECRET],
        "code_verifier": [attempt.verifier], "redirect_uri": [REDIRECT],
        "grant_type": ["authorization_code"],
    }
    assert _form(body2) == {
        "client_id": [CLIENT], "client_secret": [SECRET],
        "refresh_token": [REFRESH], "grant_type": ["refresh_token"],
    }
    assert token == google_signin.AccessToken(ACCESS, client.clock + 3599)
    assert len(others) == 2
    for _method, url, body, headers in others:
        assert SECRET not in f"{url} {body!r} {headers!r}", url


# --------------------------------------------------------------- INV-5 ----


def test_an_exchange_without_a_refresh_token_is_refused():
    """INV-5. Breaks when finish returns answer.get("refresh_token", "")."""
    client = _Google((200, {"access_token": ACCESS, "expires_in": 3599}))
    attempt = _attempt(client)
    with pytest.raises(insights.InsightsError):
        google_signin.finish(attempt, {"state": attempt.state, "code": CODE}, client)


# --------------------------------------------------------------- INV-6 ----


_ANSWERS = [
    (OSError("no route"), insights.Unreachable),
    ((400, {"error": "invalid_grant"}), insights.Refused),
    ((400, {"error": "invalid_request"}), insights.InsightsError),
    ((401, b""), insights.Refused),
    ((403, b""), insights.Refused),
    ((429, b""), insights.RateLimited),
    ((500, b""), insights.InsightsError),
]


def _calls(client: _Google):
    attempt = _attempt(client)
    return {
        "exchange": lambda: google_signin.finish(
            attempt, {"state": attempt.state, "code": CODE}, client),
        "refresh": lambda: google_signin.access_token(REFRESH, client),
        "properties": lambda: google_signin.properties(ACCESS, client),
        "revoke": lambda: google_signin.revoke(REFRESH, client),
    }


@pytest.mark.parametrize("call", ["exchange", "refresh", "properties", "revoke"])
def test_each_answer_maps_to_its_failure(call: str):
    """INV-6. Breaks when 400 invalid_grant becomes a plain InsightsError, and
    a revoked sign-in is told something went wrong instead of to sign in
    again."""
    for answer, expected in _ANSWERS:
        client = _Google(answer)
        with pytest.raises(insights.InsightsError) as caught:
            _calls(client)[call]()
        assert type(caught.value) is expected, (call, answer, type(caught.value))

    not_json = _Google((200, b"<html>"))
    if call == "revoke":
        # revoke reads no body, so any 200 is its whole answer.
        _calls(not_json)[call]()
    else:
        with pytest.raises(insights.InsightsError) as caught:
            _calls(not_json)[call]()
        assert type(caught.value) is insights.InsightsError


# --------------------------------------------------------------- INV-7 ----


def test_no_failure_names_a_token(monkeypatch: pytest.MonkeyPatch):
    """INV-7. Breaks when Google's error_description is copied into detail
    unfiltered while it quotes the token or the client secret."""
    monkeypatch.setattr(google_signin, "CLIENT_SECRET", SECRET)
    client = _Google()
    attempt = _attempt(client)
    quoted = {"error": f"invalid_grant {SECRET}",
              "error_description": f"{REFRESH} {ACCESS} {CODE} {SECRET} {attempt.verifier}"}
    failures = []
    for call in (
        lambda: google_signin.finish(attempt, {"state": attempt.state, "code": CODE}, client),
        lambda: google_signin.access_token(REFRESH, client),
        lambda: google_signin.properties(ACCESS, client),
        lambda: google_signin.revoke(REFRESH, client),
    ):
        client.answers = [(400, quoted)]
        with pytest.raises(insights.InsightsError) as caught:
            call()
        failures.append(caught.value)
    for call in (
        lambda: google_signin.finish(attempt, {"state": attempt.state, "code": CODE}, client),
        lambda: google_signin.access_token(REFRESH, client),
        lambda: google_signin.revoke(REFRESH, client),
    ):
        client.answers = [OSError(f"refused {REFRESH} {SECRET} {CODE} {attempt.verifier}")]
        with pytest.raises(insights.Unreachable) as caught:
            call()
        failures.append(caught.value)

    for failure in failures:
        words = f"{failure} {failure.detail or ''} {failure!r}"
        for secret in (REFRESH, ACCESS, CODE, attempt.verifier, SECRET):
            assert secret not in words, (type(failure), words)


# --------------------------------------------------------------- INV-8 ----


def test_properties_are_listed_across_pages():
    """INV-8. Breaks when the loop follows nextPageToken without a cap, or
    keeps an id settings.check would then refuse."""
    page_one = {"accountSummaries": [{"displayName": "Mine", "propertySummaries": [
        {"property": "properties/111", "displayName": "Journal"},
        {"property": "properties/12x", "displayName": "Broken"},
    ]}], "nextPageToken": "next"}
    page_two = {"accountSummaries": [{"displayName": "Other", "propertySummaries": [
        {"property": "properties/222", "displayName": "Shop"},
    ]}, {"displayName": "Empty"}]}
    client = _Google((200, page_one), (200, page_two))
    assert google_signin.properties(ACCESS, client) == (
        google_signin.Property("111", "Journal", "Mine"),
        google_signin.Property("222", "Shop", "Other"),
    )
    first, second = client.calls
    assert first[1] == f"{ACCOUNTS_URL}?pageSize=200"
    assert second[1] == f"{ACCOUNTS_URL}?pageSize=200&pageToken=next"
    assert first[3]["Authorization"] == f"Bearer {ACCESS}"

    endless = _Google(*[(200, {"nextPageToken": "again"})] * 50)
    assert google_signin.properties(ACCESS, endless) == ()
    assert len(endless.calls) == google_signin.PAGE_LIMIT

    assert google_signin.properties(ACCESS, _Google((200, {}))) == ()
