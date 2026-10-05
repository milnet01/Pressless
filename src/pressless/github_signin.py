"""Signing in to GitHub (PRESS-0231): the device flow that turns a code typed
on GitHub's page into a short-lived pass and the refresh token that renews it,
and the GitHub App requests setup makes with that pass.

The contract is docs/specs/PRESS-0231-github-sign-in.md § 4.1. It belongs to
the Publisher (`docs/design.md` rule 5): it uses `publisher.Transport` and the
Publisher's failure types, and reaches no other part of Pressless. The secrets
it produces are handed back to the Face, which alone reaches Credentials
(rule 10). Nothing here writes to disk or keeps state between calls.

The device flow needs no client secret, for the first token or for renewing
it (§ 3 decision 3), so nothing secret ships in Pressless.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass

from pressless import publisher
from pressless.publisher import PublishError, Transport

# The registered GitHub App (§ 4.1). Neither is a secret: both ship in the
# program by design. Until both are filled, available() is false and setup
# asks for a hand-made key instead.
CLIENT_ID = "Iv23liTJMrp5m0HkID6A"
APP_SLUG = "pressless-app"        # its name in github.com/apps/<slug>

DEVICE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105 -- an address
INSTALL_URL = "https://github.com/apps/{}/installations/new"
_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_DETAIL_LIMIT = 60                # GitHub's error codes are short words

_FORM = {"Accept": "application/json", "User-Agent": "Pressless",
         "Content-Type": "application/x-www-form-urlencoded"}


@dataclass(frozen=True)
class DeviceCode:
    device_code: str   # never shown
    user_code: str     # shown: the person types it on GitHub
    address: str       # GitHub's verification_uri
    expires_in: int    # seconds, as GitHub gives it
    interval: int


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str
    expires_in: int    # the access token's life, in seconds


@dataclass(frozen=True)
class Installation:
    id: int
    all_repositories: bool            # repository_selection == "all"


class Pending(PublishError):
    """GitHub has not heard from him yet: authorization_pending or slow_down."""


class Expired(PublishError):
    """The device code ran out before he typed it: expired_token."""


class Declined(PublishError):
    """He clicked Cancel on GitHub's page: access_denied."""


class SignedOut(PublishError):
    """GitHub refused to renew the pass: the sign-in has lapsed or been revoked."""


_POLL_ERRORS: dict[str, type[PublishError]] = {
    "authorization_pending": Pending,
    "slow_down": Pending,
    "expired_token": Expired,
    "access_denied": Declined,
    "device_flow_disabled": publisher.Refused,
}


def available() -> bool:
    """Whether this copy of Pressless carries a registered GitHub App."""
    return CLIENT_ID != "" and APP_SLUG != ""


def begin(transport: Transport | None = None) -> DeviceCode:
    """A new device code, for him to type on GitHub's page."""
    answer = _form(transport, DEVICE_URL, {"client_id": CLIENT_ID})
    error = answer.get("error")
    if error is not None:
        raise _POLL_ERRORS.get(error, PublishError)(
            f"GitHub would not start a sign-in ({_code(error, ())})")
    return DeviceCode(_text(answer, "device_code"), _text(answer, "user_code"),
                      _text(answer, "verification_uri"),
                      _number(answer, "expires_in"), _number(answer, "interval"))


def poll(code: DeviceCode, transport: Transport | None = None) -> Tokens:
    """GitHub's answer for `code`: the tokens, or the failure naming why not."""
    secret = (code.device_code,)
    answer = _form(transport, TOKEN_URL, {"client_id": CLIENT_ID,
                                          "device_code": code.device_code,
                                          "grant_type": _DEVICE_GRANT})
    error = answer.get("error")
    if error is not None:
        raise _POLL_ERRORS.get(error, PublishError)(
            f"GitHub answered the sign-in with {_code(error, secret)}")
    return _tokens(answer)


def refresh(refresh_token: str, transport: Transport | None = None) -> Tokens:
    """A new pass and a new refresh token. The one handed in stops working."""
    answer = _form(transport, TOKEN_URL, {"client_id": CLIENT_ID,
                                          "grant_type": "refresh_token",
                                          "refresh_token": refresh_token},
                   signed_out=True)
    error = answer.get("error")
    if error is not None:
        raise SignedOut(f"GitHub would not renew the sign-in "
                        f"({_code(error, (refresh_token,))})")
    return _tokens(answer)


def login(token: str, transport: Transport | None = None) -> str:
    """The signed-in account's name."""
    name = _api(transport, "GET", "/user", token)[1].get("login")
    if not isinstance(name, str) or not name:
        raise PublishError("GitHub's answer does not name the account")
    return name


def installation(token: str, login: str, transport: Transport | None = None
                 ) -> Installation | None:
    """This app's installation on `login`'s own account, or None. An
    organisation's installation of the app is never it."""
    answer = _api(transport, "GET", "/user/installations?per_page=100", token)[1]
    for found in answer.get("installations") or ():
        if not isinstance(found, dict) or found.get("app_slug") != APP_SLUG:
            continue
        account = found.get("account")
        owner = account.get("login") if isinstance(account, dict) else None
        number = found.get("id")
        if (isinstance(owner, str) and owner.casefold() == login.casefold()
                and isinstance(number, int) and not isinstance(number, bool)):
            return Installation(number, found.get("repository_selection") == "all")
    return None


def create_repository(token: str, name: str, transport: Transport | None = None) -> bool:
    """Make a Public repository `name` in his account. False where the name is
    already taken there (GitHub's 422)."""
    status, _ = _api(transport, "POST", "/user/repos", token,
                     {"name": name, "private": False}, allow=(422,))
    return status != 422


def include(token: str, installation: Installation, repository: str,
            transport: Transport | None = None) -> None:
    """Add `owner/name` to the installation, where it reaches chosen
    repositories only. Where it reaches them all, nothing is sent."""
    if installation.all_repositories:
        return
    owner, _, name = repository.partition("/")
    answer = _api(transport, "GET",
                  f"/repos/{publisher._segment(owner)}/{publisher._segment(name)}", token)[1]
    number = answer.get("id")
    if not isinstance(number, int) or isinstance(number, bool):
        raise PublishError("GitHub's answer does not name the repository's id")
    _api(transport, "PUT", f"/user/installations/{installation.id}/repositories/{number}",
         token)


def _form(transport: Transport | None, url: str, fields: dict[str, str], *,
          signed_out: bool = False) -> dict:
    """POST a sign-in form to github.com. GitHub answers its device-flow errors
    as JSON carrying `error`, usually with status 200; those are returned for
    the caller to name. A refused renewal is SignedOut whatever its status."""
    client = transport if transport is not None else publisher._Urllib()
    body = urllib.parse.urlencode(fields).encode("ascii")
    where = urllib.parse.urlsplit(url).path
    try:
        status, _headers, data = client.request("POST", url, body, dict(_FORM))
    except OSError as exc:
        raise publisher.Unreachable(
            f"no answer from github.com for {where} ({type(exc).__name__})") from None
    answer = _json(data)
    if answer is not None and (status == 200 or isinstance(answer.get("error"), str)):
        return answer
    if signed_out and status in (400, 401):
        raise SignedOut(f"GitHub refused to renew the sign-in ({status})")
    if status in (401, 403):
        raise publisher.Refused(f"GitHub refused {where} ({status})")
    raise PublishError(f"GitHub answered {status} for {where}")


def _api(transport: Transport | None, method: str, path: str, token: str,
         payload: dict | None = None, *, allow: tuple[int, ...] = ()) -> tuple[int, dict]:
    """One request to the GitHub API with the pass. A status in `allow` is
    returned for the caller to read; any other failure is the Publisher's
    typed failure for it, which never carries the pass."""
    client = transport if transport is not None else publisher._Urllib()
    url = f"{publisher.API}{path}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Pressless",
               "Authorization": f"Bearer {token}"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    where = f"{method} {publisher._without_account(url)}"
    try:
        status, answer_headers, data = client.request(method, url, body, headers)
    except OSError as exc:
        raise publisher.Unreachable(
            f"no answer from GitHub for {where} ({type(exc).__name__})") from None
    if 200 <= status < 300:
        return status, publisher._parse(data)
    if status in allow:
        return status, {}
    if publisher._retry_hint(status, answer_headers) is not None:
        raise publisher.RateLimited(f"GitHub asked us to wait on {where}")
    raise publisher._failure(status, method, url)


def _tokens(answer: dict) -> Tokens:
    return Tokens(_text(answer, "access_token"), _text(answer, "refresh_token"),
                  _number(answer, "expires_in"))


def _json(data: bytes) -> dict | None:
    try:
        answer = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return answer if isinstance(answer, dict) else None


def _text(answer: dict, name: str) -> str:
    """A field's value. Its name, never its value, reaches a message."""
    value = answer.get(name)
    if not isinstance(value, str) or not value:
        raise PublishError(f"GitHub's answer carried no {name.replace('_', ' ')}")
    return value


def _number(answer: dict, name: str) -> int:
    value = answer.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PublishError(f"GitHub's answer carried no {name.replace('_', ' ')}")
    return value


def _code(error: object, secret: tuple[str, ...]) -> str:
    """GitHub's error code, as a message may carry it. Its description is free
    text that may quote what was sent, and is left out."""
    text = str(error)
    for value in secret:
        if value:
            text = text.replace(value, "[withheld]")
    return text[:_DETAIL_LIMIT]
