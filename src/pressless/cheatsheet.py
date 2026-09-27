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

ADDRESS = "/cheat-sheet"


def _table() -> str:
    rows = "".join(f"<tr><td><code>{html.escape(row.example)}</code></td>"
                   f"<td>{html.escape(row.explains)}</td></tr>"
                   for row in marks.MARKS)
    return ('<table class="cheat-sheet"><thead><tr><th>You type</th>'
            f"<th>What it does</th></tr></thead><tbody>{rows}</tbody></table>")


def panel() -> str:
    """The sheet as it sits below the box he writes in, folded until opened."""
    return ('<details id="cheat-sheet"><summary>Cheat sheet: how to style your '
            f"words</summary>{_table()}"
            f'<p><a href="{ADDRESS}" target="_blank">A page to print</a></p></details>')


def _printable(request: Request) -> str:
    return ("<h1>Pressless cheat sheet</h1>"
            "<p>Type these in the box where you write an entry.</p>" + _table())


def register(face: Face) -> None:
    """Add the printable page to `face`."""
    face.add_page("GET", ADDRESS, _printable)
