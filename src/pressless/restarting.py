"""Restart Pressless from inside the app (PRESS-0203).

The launcher owns the restart; this part only asks for one. Settings links
here, and the page asks before restarting: the new Face has a new link and a
new session, so every open Pressless tab stops working, and anything typed
there and not saved is lost. The launch opens a fresh tab, and the tab that
asked says so rather than going dead.
"""
from __future__ import annotations

from collections.abc import Callable

from pressless.face import Face, Request

PATH = "/restart"

LINK = f'<p><a href="{PATH}">Restart Pressless</a></p>'

_ASK = (
    "<h1>Restart Pressless?</h1>"
    "<p>Pressless will close and open again in a new tab. Every Pressless tab "
    "open now stops working, so save anything you are writing in another tab "
    "first.</p>"
    f'<form method="post" action="{PATH}"><button>Restart</button></form>'
    '<p><a href="/setup">Go back to Settings</a></p>'
)

_GOING = (
    "<h1>Pressless is restarting.</h1>"
    "<p>It opens again in a new tab in a moment. You can close this one.</p>"
)


def register(face: Face, restart: Callable[[], None]) -> None:
    """Add `GET` and `POST` `/restart` to `face`. `restart` runs once the
    answer has been sent, so the page that asked always arrives."""

    def ask(request: Request) -> str:
        return _ASK

    def go(request: Request) -> str:
        face.after_reply(restart)
        return _GOING

    face.add_page("GET", PATH, ask)
    face.add_page("POST", PATH, go)
