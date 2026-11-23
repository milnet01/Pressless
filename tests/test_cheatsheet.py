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

from pressless import cheatsheet, face, marks, words

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
    # The words table builds its mark entries from MARKS when it is imported
    # (test_words holds that), so an edit to marks.py reaches it unasked.
    # Swapping MARKS after import does not, so the test adds them itself.
    monkeypatch.setitem(words.ENGLISH, "mark.new", added.explains)
    monkeypatch.setitem(words.ENGLISH, "mark.new.example", added.example)
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


def _marks_in(nodes) -> set[str]:
    found: set[str] = set()
    for node in nodes:
        if isinstance(node, marks.Paragraph):
            found |= _marks_in(child for line in node.lines for child in line.children)
        elif isinstance(node, marks.Quote):
            found.add(node.mark)
            found |= _marks_in(node.paragraphs)
        elif isinstance(node, (marks.Span, marks.Photo, marks.Value)):
            found.add(node.mark)
            found |= _marks_in(getattr(node, "children", ()))
    return found


def test_every_language_teaches_a_mark_that_works():
    """docs/design.md § Where the cheat sheet comes from: the sheet cannot
    teach a mark that does not work. Its examples are words a translator may
    change, so each language's example must still form its row's mark.

    Breaks when a translation changes a mark's syntax, say `{accent}` to
    `{akzent}`, and the sheet in that language teaches a mark that is text."""
    for code in words.LANGUAGES:
        for row in marks.MARKS:
            example = words.say_in(code, f"mark.{row.name}.example")
            assert row.name in _marks_in(marks.parse(example)), (code, row.name, example)
