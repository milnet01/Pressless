"""One way for a test to get a Face session: follow the opening link once.

Why it is shared rather than copied: PRESS-0011 § 4.5 spends the link on its
first use and hands back a session cookie that is not the link's secret, so a
test that builds the cookie from the link is refused. Four test files talk to a
served Face, and four copies of how to log in are four that will disagree.
"""
from __future__ import annotations

import http.client
import urllib.parse


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
