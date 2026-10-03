"""One way for a test to get a Face session: follow the opening link once.

Why it is shared rather than copied: PRESS-0011 § 4.5 spends the link on its
first use and hands back a session cookie that is not the link's secret, so a
test that builds the cookie from the link is refused. Many test files talk to a
served Face, and a copy of how to log in per file is copies that will disagree.
"""
from __future__ import annotations

import http.client
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pressless import face


def follow_link(url: str) -> tuple[int, dict[str, str]]:
    """GET the opening link with no cookie; the status and the headers."""
    parts = urllib.parse.urlsplit(url)
    conn = http.client.HTTPConnection("127.0.0.1", parts.port, timeout=10)
    try:
        conn.putrequest("GET", f"{parts.path}?{parts.query}", skip_host=True,
                        skip_accept_encoding=True)
        conn.putheader("Host", parts.netloc)
        conn.endheaders()
        response = conn.getresponse()
        response.read()
        return response.status, dict(response.getheaders())
    finally:
        conn.close()


def session_cookie(url: str) -> str:
    """The `name=value` the Face sets when its link is followed."""
    status, headers = follow_link(url)
    assert status in (302, 303), f"the opening link answered {status}"
    return headers["Set-Cookie"].split(";", 1)[0]


class Browser:
    """Talks to a served Face with the cookie, Host and Origin under the test's control.

    Each test file adds its own few steps on top (save, publish, a wizard
    step); the talking itself is here once.
    """

    def __init__(self, served: face.Face, *, follow: bool = True,
                 timeout: float = 10) -> None:
        """`follow=False` leaves the link unspent, for a test that spends it."""
        parts = urllib.parse.urlsplit(served.url)
        assert parts.port is not None
        self.served = served
        self.port = parts.port
        self.host = f"127.0.0.1:{self.port}"
        self.origin = f"http://{self.host}"
        self.timeout = timeout
        self.cookie = session_cookie(served.url) if follow else ""

    def request(self, method: str, path: str, form: dict[str, str] | None = None, *,
                cookie: bool = True, origin: str | None = "own",
                host: str | None = None) -> tuple[int, dict[str, str], str]:
        """The status, headers and text. A POST carries `origin`, "own" by default."""
        body = urllib.parse.urlencode(form or {}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", host or self.host)
            if cookie:
                conn.putheader("Cookie", self.cookie)
            if method == "POST":
                if origin:
                    conn.putheader("Origin", self.origin if origin == "own" else origin)
                conn.putheader("Content-Type", "application/x-www-form-urlencoded")
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body if method == "POST" else None)
            response = conn.getresponse()
            return (response.status, dict(response.getheaders()),
                    response.read().decode("utf-8", "replace"))
        finally:
            conn.close()
