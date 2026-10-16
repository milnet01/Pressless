"""About Pressless (PRESS-0278): which version this is, that it is an
independent project, and where its source and licence are. Every screen's
top bar links here, so the version is one click from anywhere.
"""
from __future__ import annotations

import html

from pressless import __version__, updater
from pressless.face import Face, Request
from pressless.words import say

ADDRESS = "/about"
PROJECT_ADDRESS = f"https://github.com/{updater.REPOSITORY}"


def _page(request: Request) -> str:
    return (
        f'<h1>{say("face.about")}</h1>'
        f'<p>{say("about.version", version=html.escape(__version__))}</p>'
        f'<p>{say("about.independent")}</p>'
        f'<p>{say("about.licence", address=html.escape(PROJECT_ADDRESS, quote=True))}</p>'
    )


def register(face: Face) -> None:
    """Add the About page to `face`."""
    face.add_page("GET", ADDRESS, _page)
