"""The cheat sheet, generated from Marks' one table (PRESS-0018).

docs/design.md § Where the cheat sheet comes from: neither the panel beside
the box nor the printable page is written by hand, because a hand-written card
drifts the first time a mark changes, and then it teaches him something that
does not work. Every row is read from marks.MARKS when the sheet is asked for.
"""
from __future__ import annotations

import html

from pressless import marks
from pressless.face import Face, Request
from pressless.words import say

ADDRESS = "/cheat-sheet"


def _table() -> str:
    rows = "".join(f"<tr><td><code>{html.escape(say('mark.' + row.name + '.example'))}"
                   f"</code></td><td>{html.escape(say('mark.' + row.name))}</td></tr>"
                   for row in marks.MARKS)
    return (f'<table class="cheat-sheet"><thead><tr><th>{say("cheatsheet.you_type")}</th>'
            f'<th>{say("cheatsheet.does")}</th></tr></thead><tbody>{rows}</tbody></table>')


def panel() -> str:
    """The sheet as it sits below the box he writes in, folded until opened."""
    return (f'<details id="cheat-sheet"><summary>{say("cheatsheet.panel")}</summary>'
            f"{_table()}"
            f'<p><a href="{ADDRESS}" target="_blank">{say("cheatsheet.print")}</a></p>'
            "</details>")


def _printable(request: Request) -> str:
    return (f'<h1>{say("cheatsheet.title")}</h1>'
            f'<p>{say("cheatsheet.where")}</p>' + _table())


def register(face: Face) -> None:
    """Add the printable page to `face`."""
    face.add_page("GET", ADDRESS, _printable)
