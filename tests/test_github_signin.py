# Signing in to GitHub: the device flow and the GitHub App requests (PRESS-0231).
#
# The protocol's own tests, from docs/specs/PRESS-0231-github-sign-in.md
# § 4.1 and § 7: each request's address and fields, and each `error` answer's
# type. GitHub is a recording double answering by address; no test reaches
# it. Secrets are plain words, so the push gate's secret scanner does not
# mistake them.
from __future__ import annotations

import json
import urllib.parse

import pytest

from pressless import github_signin, publisher

CLIENT = "Iv1.plain-client"
APP = "pressless-app"
DEVICE = "plain-device-code"
ACCESS = "ghu_plain-access"
REFRESH = "ghr_plain-refresh"
NEW_REFRESH = "ghr_plain-new-refresh"

DEVICE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105 -- an address
GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class _GitHub:
    """Answers each request with the next of `answers`, a (status, body) pair,
    and records what was sent."""

    def __init__(self, *answers: tuple[int, object]) -> None:
        self.answers = list(answers)
        self.sent: list[tuple[str, str, bytes | None, dict[str, str]]] = []

    def request(self, method, url, body, headers):
        self.sent.append((method, url, body, headers))
        if not self.answers:
            raise OSError("no answer")
        status, answer = self.answers.pop(0)
        data = answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        return status, {}, data

    def wait(self, seconds: float) -> None:
        return None

    def form(self, index: int = -1) -> dict[str, list[str]]:
        return urllib.parse.parse_qs((self.sent[index][2] or b"").decode())


@pytest.fixture(autouse=True)
def _registered(monkeypatch):
    monkeypatch.setattr(github_signin, "CLIENT_ID", CLIENT)
    monkeypatch.setattr(github_signin, "APP_SLUG", APP)


def _code() -> github_signin.DeviceCode:
    return github_signin.DeviceCode(DEVICE, "WDJB-MJHT", "https://github.com/login/device",
                                    900, 5)


def _tokens(refresh: str = NEW_REFRESH) -> dict:
    return {"access_token": ACCESS, "refresh_token": refresh, "expires_in": 28800,
            "refresh_token_expires_in": 15897600, "token_type": "bearer"}


def test_available_needs_both_constants(monkeypatch):
    assert github_signin.available()
    monkeypatch.setattr(github_signin, "APP_SLUG", "")
    assert not github_signin.available()
    monkeypatch.setattr(github_signin, "APP_SLUG", APP)
    monkeypatch.setattr(github_signin, "CLIENT_ID", "")
    assert not github_signin.available()


def test_begin_asks_github_for_a_code():
    github = _GitHub((200, {"device_code": DEVICE, "user_code": "WDJB-MJHT",
                            "verification_uri": "https://github.com/login/device",
                            "expires_in": 900, "interval": 5}))
    code = github_signin.begin(github)
    assert code == _code()
    method, url, _body, headers = github.sent[0]
    assert (method, url) == ("POST", DEVICE_URL)
    assert github.form() == {"client_id": [CLIENT]}
    assert headers["Accept"] == "application/json"


def test_poll_sends_the_device_code_and_reads_the_tokens():
    github = _GitHub((200, _tokens()))
    tokens = github_signin.poll(_code(), github)
    assert tokens == github_signin.Tokens(ACCESS, NEW_REFRESH, 28800)
    method, url, _body, headers = github.sent[0]
    assert (method, url) == ("POST", TOKEN_URL)
    assert github.form() == {"client_id": [CLIENT], "device_code": [DEVICE],
                             "grant_type": [GRANT]}
    assert headers["Accept"] == "application/json"


@pytest.mark.parametrize(("error", "kind"), [
    ("authorization_pending", github_signin.Pending),
    ("slow_down", github_signin.Pending),
    ("expired_token", github_signin.Expired),
    ("access_denied", github_signin.Declined),
    ("device_flow_disabled", publisher.Refused),
    ("incorrect_device_code", publisher.PublishError),
])
def test_each_poll_error_has_its_type(error, kind):
    github = _GitHub((200, {"error": error, "error_description": f"about {DEVICE}"}))
    with pytest.raises(kind) as raised:
        github_signin.poll(_code(), github)
    assert type(raised.value) is kind
    assert DEVICE not in str(raised.value)


def test_refresh_sends_the_refresh_token_and_reads_the_new_one():
    github = _GitHub((200, _tokens()))
    tokens = github_signin.refresh(REFRESH, github)
    assert tokens.refresh == NEW_REFRESH and tokens.access == ACCESS
    method, url, _body, headers = github.sent[0]
    assert (method, url) == ("POST", TOKEN_URL)
    assert github.form() == {"client_id": [CLIENT], "grant_type": ["refresh_token"],
                             "refresh_token": [REFRESH]}
    assert "Authorization" not in headers


@pytest.mark.parametrize("answer", [
    (200, {"error": "bad_refresh_token", "error_description": f"{REFRESH} is bad"}),
    (400, {"error": "bad_refresh_token"}),
])
def test_any_refresh_error_is_a_sign_out(answer):
    with pytest.raises(github_signin.SignedOut) as raised:
        github_signin.refresh(REFRESH, _GitHub(answer))
    assert REFRESH not in str(raised.value)


def test_no_answer_is_unreachable():
    with pytest.raises(publisher.Unreachable) as raised:
        github_signin.refresh(REFRESH, _GitHub())
    assert REFRESH not in str(raised.value)


def test_login_reads_the_user():
    github = _GitHub((200, {"login": "owner"}))
    assert github_signin.login(ACCESS, github) == "owner"
    method, url, _body, headers = github.sent[0]
    assert (method, url) == ("GET", f"{publisher.API}/user")
    assert headers["Authorization"] == f"Bearer {ACCESS}"


def test_installation_is_this_apps_on_this_account():
    listed = {"total_count": 4, "installations": [
        {"id": 1, "app_slug": "another-app", "account": {"login": "owner"},
         "repository_selection": "all"},
        {"id": 2, "app_slug": APP, "account": {"login": "an-organisation"},
         "repository_selection": "all"},
        {"id": 3, "app_slug": APP, "account": {"login": "Owner"},
         "repository_selection": "selected"},
    ]}
    github = _GitHub((200, listed))
    found = github_signin.installation(ACCESS, "owner", github)
    assert found == github_signin.Installation(3, all_repositories=False)
    assert github.sent[0][1].startswith(f"{publisher.API}/user/installations")
    assert github_signin.installation(
        ACCESS, "owner", _GitHub((200, {"installations": listed["installations"][:2]}))) is None


def test_create_repository_makes_a_public_one():
    github = _GitHub((201, {"full_name": "owner/site"}))
    assert github_signin.create_repository(ACCESS, "site", github) is True
    method, url, body, _headers = github.sent[0]
    assert (method, url) == ("POST", f"{publisher.API}/user/repos")
    assert json.loads(body) == {"name": "site", "private": False}
    taken = _GitHub((422, {"message": "Repository creation failed."}))
    assert github_signin.create_repository(ACCESS, "site", taken) is False
    with pytest.raises(publisher.Refused):
        github_signin.create_repository(ACCESS, "site", _GitHub((403, {"message": "no"})))


def test_reaches_reads_the_installations_repositories_where_they_are_chosen():
    listed = {"total_count": 1, "repositories": [{"full_name": "Owner/Site"}]}
    chosen = github_signin.Installation(7, False)
    github = _GitHub((200, listed))
    assert github_signin.reaches(ACCESS, chosen, "owner/site", github) is True
    assert [(m, u) for m, u, _b, _h in github.sent] == [
        ("GET", f"{publisher.API}/user/installations/7/repositories?per_page=100"),
    ]
    assert github_signin.reaches(ACCESS, chosen, "owner/other", _GitHub((200, listed))) is False
    every = _GitHub()
    assert github_signin.reaches(ACCESS, github_signin.Installation(7, True), "owner/site",
                                 every) is True
    assert every.sent == []
