# What Pressless remembers of his choices between visits (PRESS-0263).
#
# The file name and its fields are written out here rather than imported, so a
# renamed field fails here instead of being compared with itself.
from __future__ import annotations

import http.client
import json
from pathlib import Path

import pytest
from test_page_editor import CODED, _folder, _pages

from pressless import choices, store

FILE_NAME = "choices.json"


def _held(folder: Path) -> dict:
    return json.loads((folder / FILE_NAME).read_text(encoding="utf-8"))


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"version": 2, "view": "code"}',
                                  '{"version": 1, "page": "about", "view": 3, '
                                  '"shown_on": [], "true_colours": "yes"}',
                                  '{"version": 1, "page": ["pages", ""]}'])
def test_an_unusable_choice_reads_as_not_made(tmp_path, text) -> None:
    """Breaks when a garbled file, or one field of the wrong shape, reaches a page."""
    (tmp_path / FILE_NAME).write_text(text, encoding="utf-8")
    assert choices.read(tmp_path) == choices.Choices()


def test_a_choice_is_kept_beside_the_others(tmp_path) -> None:
    """Breaks when remembering one choice forgets another."""
    assert choices.read(tmp_path) == choices.Choices()
    assert choices.remember(tmp_path, view="code", page=("pages", "about"))
    assert choices.remember(tmp_path, true_colours=True)
    assert _held(tmp_path) == {"version": 1, "page": ["pages", "about"], "shown_on": "",
                               "view": "code", "true_colours": True}
    assert choices.read(tmp_path) == choices.Choices(
        page=("pages", "about"), view="code", true_colours=True)


def test_a_choice_that_cannot_be_written_is_only_forgotten(tmp_path) -> None:
    """Breaks when a full disk or a locked folder stops a page opening."""
    missing = tmp_path / "gone"
    assert not choices.remember(missing, view="code")
    assert choices.read(missing) == choices.Choices()


def _view(text: str) -> str:
    return "code" if 'data-view="code"' in text else "visual"


def test_a_page_opens_in_the_view_he_last_switched_to(tmp_path) -> None:
    """Breaks when the code view is forgotten at the next page, or an address
    that names a view is overruled by the remembered one."""
    folder = _folder(tmp_path)
    for name in ("about", "index"):
        store.write_html(folder, store.PAGES_FOLDER, name, CODED)
    with _pages(folder) as browser:
        first = browser.request("GET", "/page?kind=pages&name=about")[2]
        browser.request("GET", "/page?kind=pages&name=about&view=code")
        later = browser.request("GET", "/page?kind=pages&name=index")[2]
        named = browser.request("GET", "/page?kind=pages&name=index&view=visual")[2]
        back = browser.request("GET", "/page?kind=pages&name=about")[2]
    assert _view(first) == "visual"
    assert _view(later) == "code"
    assert _view(named) == "visual"
    assert _view(back) == "visual"


def test_the_furniture_shows_the_page_he_last_picked(tmp_path) -> None:
    """Breaks when the header's preview goes back to Home after he picked
    another page, or keeps a picked page that has since gone."""
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        browser.request("GET", "/page?kind=furniture&name=header&show=about")
        footer = browser.request("GET", "/page?kind=furniture&name=footer")[2]
        (folder / store.PAGES_FOLDER / "about.html").unlink()
        gone = browser.request("GET", "/page?kind=furniture&name=footer")[2]
    assert 'data-show="about"' in footer
    assert 'data-show="index"' in gone


def test_the_list_offers_the_page_he_last_opened(tmp_path) -> None:
    """Breaks when the list offers no way back to the last page, names it by
    its file rather than its label, or offers a page that has gone."""
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        before = browser.request("GET", "/")[2]
        browser.request("GET", "/page?kind=furniture&name=navigation")
        browser.request("GET", "/page?kind=pages&name=about")
        after = browser.request("GET", "/")[2]
        (folder / store.PAGES_FOLDER / "about.html").unlink()
        gone = browser.request("GET", "/")[2]
    assert "Carry on with:" not in before
    assert ('<p>Carry on with: <a href="/page?kind=pages&amp;name=about">About</a></p>'
            in after), after
    assert "Carry on with:" not in gone


def _post(browser, body: bytes) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", browser.port, timeout=10)
    try:
        conn.request("POST", "/true-colours", body=body, headers={
            "Host": browser.host, "Cookie": browser.cookie, "Origin": browser.origin})
        return conn.getresponse().status
    finally:
        conn.close()


def test_the_true_colours_switch_is_kept(tmp_path) -> None:
    """Breaks when the switch is forgotten between visits, or the route keeps
    anything but a yes or a no."""
    folder = _folder(tmp_path)
    box = '<input type="checkbox" data-true-colours checked>'
    with _pages(folder) as browser:
        off = browser.request("GET", "/page?kind=pages&name=about")[2]
        refused = _post(browser, b"yes")
        kept = _post(browser, b"1")
        page = browser.request("GET", "/page?kind=pages&name=about")[2]
        entry = browser.request("GET", "/edit?slug=seaside")[2]
        _post(browser, b"0")
        again = browser.request("GET", "/page?kind=pages&name=about")[2]
    assert (refused, kept) == (400, 204)
    assert box not in off and box in page and box in entry and box not in again
