"""Suggest or report a problem (PRESS-0179).

Every screen's top bar links here. The page says the issue will be public,
points a security problem at GitHub's private route (SECURITY.md), and opens
a new issue on Pressless's repository with a short form already filled in:
the Pressless version, the system it runs on, and three questions. Nothing
else is sent -- no site address, no writing, no settings, no log -- and the
user reads and changes it before submitting.
"""
from __future__ import annotations

import html
import platform
import urllib.parse

from pressless import __version__, updater
from pressless.face import Face, Request

ADDRESS = "/report"
SECURITY_ADDRESS = f"https://github.com/{updater.REPOSITORY}/security/advisories/new"


def _system() -> str:
    """The system, plainly: "Windows 11", or "Linux (openSUSE Tumbleweed)"."""
    name = platform.system()
    if name == "Windows":
        return f"Windows {platform.release()}"
    if name == "Linux":
        try:
            pretty = platform.freedesktop_os_release().get("PRETTY_NAME")
        except OSError:
            pretty = None
        return f"Linux ({pretty})" if pretty else "Linux"
    return name or "an unknown system"


def issue_address() -> str:
    body = (f"Pressless {__version__} on {_system()}\n\n"
            "What I pressed:\n\n\n"
            "What I expected:\n\n\n"
            "What I saw instead:\n\n")
    query = urllib.parse.urlencode({"title": "A suggestion or a problem: ", "body": body})
    return f"https://github.com/{updater.REPOSITORY}/issues/new?{query}"


def _page(request: Request) -> str:
    e = html.escape
    return (
        "<h1>Suggest or report a problem</h1>"
        "<p>This opens a new issue on Pressless's page on GitHub, with a short form "
        "already filled in: which Pressless you have, the system it runs on, and "
        "three questions for you to answer. Nothing else is sent, and you can read "
        "and change all of it before you submit it.</p>"
        "<p><strong>An issue is public</strong>: anyone can read it. Leave out your "
        "site's address, your writing and your publishing key.</p>"
        "<p>Found a security problem? Please do not report it here. Use GitHub's "
        f'<a href="{e(SECURITY_ADDRESS, quote=True)}" target="_blank" '
        'rel="noopener noreferrer">private report</a> instead.</p>'
        f'<p><a href="{e(issue_address(), quote=True)}" target="_blank" '
        'rel="noopener noreferrer">Open the report on GitHub</a></p>'
    )


def register(face: Face) -> None:
    """Add the report page to `face`."""
    face.add_page("GET", ADDRESS, _page)
