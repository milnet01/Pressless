"""Signing in with Google (PRESS-0122): the part of Insights that asks Google
for permission, turns it into the short-lived token `insights.read` takes, and
lists the Analytics properties the signed-in account can see.

The contract is docs/specs/PRESS-0122-google-signin.md § 4.1. It belongs to
Insights, the one part allowed to talk to Google (`docs/design.md` rule 8), so
it imports `insights` and nothing else of Pressless. The secret it produces is
handed back to the Face, which alone reaches Credentials (rule 10).

Google requires the Desktop client's secret despite its docs. It is never
committed: a release build writes it into `_google_secret` (§ 3 decision 3,
§ 4.7), and a checkout without that file cannot sign in. PKCE is kept.
Nothing here writes to disk or keeps state between calls.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import urllib.parse
from dataclasses import dataclass

from pressless import insights
from pressless.insights import InsightsError, Transport

try:
    from pressless._google_secret import CLIENT_SECRET
except ImportError:  # a development checkout, before write_google_secret.py runs
    CLIENT_SECRET = ""

# The registered Desktop client (§ 4.6). An id, not a secret: it ships in the
# program by design. Its secret comes from `_google_secret`, above.
CLIENT_ID = "407838712240-ioic610gg2obnav839qe4pdk07ar1gki.apps.googleusercontent.com"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 -- an address, not a secret
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
ACCOUNTS_URL = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
ATTEMPT_SECONDS = 600.0  # how long a sign-in may take on Google's page
PAGE_LIMIT = 10          # accountSummaries pages followed, at 200 accounts each
STREAMS_URL = "https://analyticsadmin.googleapis.com/v1beta/properties/{}/dataStreams"
# settings.check's pattern (PRESS-0199 § 4.1), restated because this module
# imports only insights (INV-1); an id it would refuse is never returned.
_MEASUREMENT_ID = re.compile(r"\AG-[A-Z0-9]+\Z")

_FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@dataclass(frozen=True)
class Attempt:
    state: str
    verifier: str
    redirect_uri: str
    started: float       # the transport's clock


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_at: float    # the transport's clock


@dataclass(frozen=True)
class Property:
    id: str              # digits only, the form Settings keeps
    name: str            # Google's display name
    account: str         # the Analytics account's display name


class Declined(InsightsError):
    """He said no on Google's page."""


class Expired(InsightsError):
    """The sign-in took too long, or came back for an attempt it was not."""


def available() -> bool:
    """Whether this copy of Pressless carries a registered client (§ 4.6)."""
    return CLIENT_ID != "" and CLIENT_SECRET != ""


def begin(redirect_uri: str, client: Transport | None = None) -> tuple[Attempt, str]:
    """A new attempt and the address of Google's sign-in page. No request."""
    transport = client if client is not None else insights._own_client()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    query = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # Both, or Google hands back a refresh token on the first consent only.
        "access_type": "offline",
        "prompt": "consent",
    })
    return Attempt(state, verifier, redirect_uri, transport.now()), f"{AUTH_URL}?{query}"


def finish(attempt: Attempt, query: dict[str, str],
           client: Transport | None = None) -> str:
    """Google's return, exchanged for the refresh token.

    Every check runs before any request (INV-3): a code that came back for
    some other attempt is never sent to Google.
    """
    transport = client if client is not None else insights._own_client()
    if not hmac.compare_digest(query.get("state", ""), attempt.state):
        raise Expired("the sign-in came back for a different attempt")
    if not 0.0 <= transport.now() - attempt.started < ATTEMPT_SECONDS:
        raise Expired("the sign-in took too long")
    error = query.get("error")
    if error == "access_denied":
        raise Declined("he declined on Google's page")
    if error is not None:
        raise InsightsError("Google ended the sign-in", error[:insights.DETAIL_LIMIT])
    answer = _post(transport, TOKEN_URL, {
        "code": query.get("code", ""),
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code_verifier": attempt.verifier,
        "redirect_uri": attempt.redirect_uri,
        "grant_type": "authorization_code",
    }, (query.get("code", ""), attempt.verifier))
    return _field(answer, "refresh_token")


def access_token(refresh_token: str, client: Transport | None = None) -> AccessToken:
    """A fresh access token for the saved sign-in."""
    transport = client if client is not None else insights._own_client()
    asked = transport.now()
    answer = _post(transport, TOKEN_URL, {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, (refresh_token,))
    value = _field(answer, "access_token")
    lifetime = answer.get("expires_in")
    if isinstance(lifetime, bool) or not isinstance(lifetime, (int, float)):
        raise InsightsError("Google's token answer named no lifetime")
    return AccessToken(value, asked + float(lifetime))


def properties(token: str, client: Transport | None = None) -> tuple[Property, ...]:
    """The Analytics properties the signed-in account can see, in Google's
    order, following at most PAGE_LIMIT pages (INV-8)."""
    transport = client if client is not None else insights._own_client()
    found: list[Property] = []
    page_token = ""
    for _ in range(PAGE_LIMIT):
        query = {"pageSize": "200"}
        if page_token:
            query["pageToken"] = page_token
        answer = _answer(transport, "GET", f"{ACCOUNTS_URL}?{urllib.parse.urlencode(query)}",
                         None, {"Authorization": f"Bearer {token}"}, (token,))
        # Google omits an empty list rather than sending one, so absence is
        # no properties, never a missing field (§ 4.1).
        for account in answer.get("accountSummaries") or ():
            if not isinstance(account, dict):
                continue
            account_name = str(account.get("displayName", ""))
            for summary in account.get("propertySummaries") or ():
                if not isinstance(summary, dict):
                    continue
                digits = str(summary.get("property", "")).removeprefix("properties/")
                if digits.isascii() and digits.isdigit():
                    found.append(Property(digits, str(summary.get("displayName", "")),
                                          account_name))
        page_token = answer.get("nextPageToken") or ""
        if not isinstance(page_token, str) or not page_token:
            break
    return tuple(found)


def measurement_ids(token: str, property_id: str, site_address: str,
                    client: Transport | None = None) -> tuple[str, ...]:
    """PRESS-0199 § 4.3: the measurement ids of the property's web streams,
    following at most PAGE_LIMIT pages. Where one stream measures the site's
    own host, ignoring case and a leading www., its id alone."""
    transport = client if client is not None else insights._own_client()
    host = _host(site_address)
    found: list[tuple[str, str]] = []
    page_token = ""
    for _ in range(PAGE_LIMIT):
        query = {"pageSize": "200"}
        if page_token:
            query["pageToken"] = page_token
        answer = _answer(transport, "GET",
                         f"{STREAMS_URL.format(property_id)}?{urllib.parse.urlencode(query)}",
                         None, {"Authorization": f"Bearer {token}"}, (token,))
        for stream in answer.get("dataStreams") or ():
            if not isinstance(stream, dict) or stream.get("type") != "WEB_DATA_STREAM":
                continue
            data = stream.get("webStreamData")
            if not isinstance(data, dict):
                continue
            found_id = data.get("measurementId")
            if isinstance(found_id, str) and _MEASUREMENT_ID.fullmatch(found_id):
                found.append((found_id, _host(str(data.get("defaultUri") or ""))))
        page_token = answer.get("nextPageToken") or ""
        if not isinstance(page_token, str) or not page_token:
            break
    mine = [found_id for found_id, stream_host in found if host and stream_host == host]
    return (mine[0],) if mine else tuple(found_id for found_id, _ in found)


def _host(address: str) -> str:
    host = (urllib.parse.urlsplit(address).hostname or "").casefold()
    return host.removeprefix("www.")


def revoke(refresh_token: str, client: Transport | None = None) -> None:
    """Tell Google to forget the sign-in. A 200 is the whole answer; its body
    is not read."""
    transport = client if client is not None else insights._own_client()
    body = urllib.parse.urlencode({"token": refresh_token}).encode("ascii")
    status, data = _request(transport, "POST", REVOKE_URL, body, dict(_FORM), (refresh_token,))
    if status != 200:
        raise _failure(status, data, (refresh_token,))


def _post(transport: Transport, url: str, fields: dict[str, str],
          secret: tuple[str, ...]) -> dict:
    body = urllib.parse.urlencode(fields).encode("ascii")
    return _answer(transport, "POST", url, body, dict(_FORM), secret)


def _answer(transport: Transport, method: str, url: str, body: bytes | None,
            headers: dict[str, str], secret: tuple[str, ...]) -> dict:
    status, data = _request(transport, method, url, body, headers, secret)
    if status != 200:
        raise _failure(status, data, secret)
    try:
        answer = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise InsightsError("Google's answer was not JSON") from None
    if not isinstance(answer, dict):
        raise InsightsError("Google's answer was not a JSON object")
    return answer


def _request(transport: Transport, method: str, url: str, body: bytes | None,
             headers: dict[str, str], secret: tuple[str, ...]) -> tuple[int, bytes]:
    try:
        status, _headers, data = transport.request(method, url, body, headers)
    except OSError as exc:
        # The URL is safe to name; the error's own words may quote the request.
        raise insights.Unreachable(f"no answer from {urllib.parse.urlsplit(url).netloc}",
                                   _scrub(type(exc).__name__, secret)) from None
    return status, data


def _failure(status: int, data: bytes, secret: tuple[str, ...]) -> InsightsError:
    """§ 4.1's table. `detail` carries Google's error code, never its free text,
    which may quote what was sent (INV-7)."""
    detail = _error_detail(data, secret)
    if status in (401, 403) or (status == 400 and _error_code(data) == "invalid_grant"):
        return insights.Refused(f"Google refused the sign-in ({status})", detail)
    if status == 429:
        return insights.RateLimited("Google asked us to slow down", detail)
    return InsightsError(f"Google answered {status}", detail)


def _error_detail(data: bytes, secret: tuple[str, ...]) -> str | None:
    """The sign-in endpoints' `error` code, or the Admin API's `error.status`.
    Their descriptions and messages are free text and are left out."""
    try:
        answer = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    error = answer.get("error") if isinstance(answer, dict) else None
    if isinstance(error, dict):
        error = error.get("status")
    if not isinstance(error, str) or not error:
        return None
    return _scrub(error, secret)[:insights.DETAIL_LIMIT]


def _error_code(data: bytes) -> str | None:
    try:
        answer = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    error = answer.get("error") if isinstance(answer, dict) else None
    return error if isinstance(error, str) else None


def _field(answer: dict, name: str) -> str:
    value = answer.get(name)
    if not isinstance(value, str) or not value:
        raise InsightsError(f"Google's answer carried no {name.replace('_', ' ')}")
    return value


def _scrub(text: str, secret: tuple[str, ...]) -> str:
    # The client secret is withheld everywhere, sent or not (INV-7).
    for value in (*secret, CLIENT_SECRET):
        if value:
            text = text.replace(value, "[withheld]")
    return text
