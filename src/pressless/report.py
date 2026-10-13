"""Suggest or report a problem (PRESS-0179).

Every screen's top bar links here. The page says the issue will be public,
points a security problem at GitHub's private route (SECURITY.md), and opens
a new issue on Pressless's repository with a short form already filled in:
the Pressless version, the system it runs on, and three questions. Nothing
else is sent -- no site address, no writing, no settings, no log -- and the
user reads and changes it before submitting. Usage reports are a separate
channel, sent only where the user said yes (PRESS-0262, usage.py).
"""
from __future__ import annotations

import html
import urllib.parse

from pressless import __version__, updater, usage
from pressless.face import Face, Request
from pressless.words import say

ADDRESS = "/report"
SECURITY_ADDRESS = f"https://github.com/{updater.REPOSITORY}/security/advisories/new"


def issue_address() -> str:
    body = (f"Pressless {__version__} on {usage.system()}\n\n"
            "What I pressed:\n\n\n"
            "What I expected:\n\n\n"
            "What I saw instead:\n\n")
    query = urllib.parse.urlencode({"title": "A suggestion or a problem: ", "body": body})
    return f"https://github.com/{updater.REPOSITORY}/issues/new?{query}"


def _page(request: Request) -> str:
    e = html.escape
    security = e(SECURITY_ADDRESS, quote=True)
    issue = e(issue_address(), quote=True)
    return (
        f'<h1>{say("face.report")}</h1>'
        f'<p>{say("report.what")}</p>'
        f'<p>{say("report.public")}</p>'
        f'<p>{say("report.security", address=security)}</p>'
        f'<p>{say("report.open", address=issue)}</p>'
    )


def register(face: Face) -> None:
    """Add the report page to `face`."""
    face.add_page("GET", ADDRESS, _page)
