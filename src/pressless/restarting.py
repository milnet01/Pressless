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
from pressless.words import say

PATH = "/restart"


def link() -> str:
    """Settings' link to the restart page."""
    return f'<p><a href="{PATH}">{say("restarting.link")}</a></p>'


def register(face: Face, restart: Callable[[], None]) -> None:
    """Add `GET` and `POST` `/restart` to `face`. `restart` runs once the
    answer has been sent, so the page that asked always arrives."""

    def ask(request: Request) -> str:
        return (f'<h1>{say("restarting.ask.title")}</h1>'
                f'<p>{say("restarting.ask")}</p>'
                f'<form method="post" action="{PATH}">'
                f'<button>{say("restarting.restart")}</button></form>'
                f'<p><a href="/setup">{say("restarting.back")}</a></p>')

    def go(request: Request) -> str:
        face.after_reply(restart)
        return (f'<h1>{say("restarting.going.title")}</h1>'
                f'<p>{say("restarting.going")}</p>')

    face.add_page("GET", PATH, ask)
    face.add_page("POST", PATH, go)
