# The cheat sheet is generated from Marks' one table (PRESS-0018,
# docs/design.md § Where the cheat sheet comes from).
#
# A hand-written card drifts the first time a mark changes. So these tests hold
# that every row of MARKS is on the sheet, and that a row added to the table
# reaches the sheet with nothing else edited.
from __future__ import annotations

import dataclasses
import html
import http.client
import urllib.parse

from _face_session import session_cookie

from pressless import cheatsheet, face, marks

PRINTABLE = "/cheat-sheet"


def _get(served: face.Face, path: str) -> tuple[int, str]:
    parts = urllib.parse.urlsplit(served.url)
    conn = http.client.HTTPConnection("127.0.0.1", parts.port, timeout=10)
    try:
        conn.request("GET", path, headers={"Cookie": session_cookie(served.url)})
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        conn.close()


def test_every_mark_is_on_the_sheet():
    """Breaks when the panel is written by hand, or skips a kind of mark."""
    panel = cheatsheet.panel()
    for row in marks.MARKS:
        assert html.escape(row.example) in panel, row.name
        assert html.escape(row.explains) in panel, row.name


def test_a_new_mark_reaches_the_sheet_with_nothing_else_edited(monkeypatch):
    """Breaks when the sheet holds a copy of the table rather than reading it."""
    removed = marks.MARKS[0]
    added = dataclasses.replace(removed, name="new", example="<b>&new",
                                explains="A mark added to the table & nowhere else.")
    monkeypatch.setattr(marks, "MARKS", (*marks.MARKS[1:], added))
    panel = cheatsheet.panel()
    assert html.escape(added.example) in panel
    assert html.escape(added.explains) in panel
    assert html.escape(removed.example) not in panel


def test_the_printable_page_is_served(tmp_path):
    """Breaks when the printable page is not registered, or is not the sheet."""
    served = face.serve(tmp_path)
    try:
        cheatsheet.register(served)
        status, page = _get(served, PRINTABLE)
    finally:
        served.stop()
    assert status == 200
    for row in marks.MARKS:
        assert html.escape(row.example) in page, row.name


def test_the_panel_links_to_the_printable_page():
    assert f'href="{PRINTABLE}"' in cheatsheet.panel()
