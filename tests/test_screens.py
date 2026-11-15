"""PRESS-0353: Your site, Pages and Journal each hold their own blocks.

Each test serves a seeded site with the parts that draw on these screens, and
reads the HTML each screen answers with.
"""
from __future__ import annotations

import contextlib
import dataclasses
import http.client
from collections.abc import Iterator
from pathlib import Path

import pytest
import test_publishing as tp
from _face_session import Browser

from pressless import (
    dashboard,
    editor,
    face,
    google_setup,
    overview,
    page_editor,
    settings,
    store,
    templates,
)

# Each block the old list held, by a string only it writes.
BLOCKS = {
    "the New entry form": 'action="/new"',
    "the New page form": 'action="/page/new"',
    "the journal switch": 'action="/journal"',
    "the undo row": '<button type="button" data-undo>',
    "the checklist": 'id="checklist"',
    "Your templates": 'action="/template/new"',
}
HOMES = {
    "the New entry form": "/journal", "the New page form": "/pages",
    "the journal switch": "/journal", "the undo row": "/",
    "the checklist": "/", "Your templates": "/journal",
}


class _Browser(Browser):
    def get(self, path: str) -> str:
        status, _, page = self.request("GET", path)
        assert status == 200, (path, status)
        return page


class _NoNetwork:
    """A Google double that refuses every request, and counts them."""

    def __init__(self) -> None:
        self.requests = 0

    def request(self, method, url, body, headers):
        self.requests += 1
        raise OSError("no network in this test")

    def now(self) -> float:
        return 1000.0


def _site(tmp_path: Path, *, journal: bool = True, google: bool = False) -> Path:
    folder = tp._folder(tmp_path)
    if google:
        saved = settings.load(folder)
        settings.save(folder, dataclasses.replace(
            saved, analytics_property_id="999",
            credentials=dataclasses.replace(saved.credentials, google_account="google")))
    store.write_identity(folder, store.Identity("Harbour notes"))
    store.write_html(folder, store.PAGES_FOLDER, "index", "<p>Home.</p>")
    store.write(folder, tp._entry("seaside"), draft=True)
    store.write(folder, tp._entry("harbour"), draft=False)
    store.write_journal(folder, journal)
    return folder


@contextlib.contextmanager
def _served(folder: Path, client: _NoNetwork | None = None) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        google_setup.register(served, folder, client=client)
        dashboard.register(served, folder, client=client)
        editor.register(served, folder)
        overview.register(served, folder)
        templates.register(served, folder)
        page_editor.register(served, folder)
        yield _Browser(served)
    finally:
        served.stop()


def test_each_block_has_one_home(tmp_path: Path) -> None:
    """INV-2. Breaks when a block is left on /, dropped, or shown twice."""
    with _served(_site(tmp_path)) as browser:
        screens = {path: browser.get(path) for path in ("/", "/pages", "/journal")}
    for block, marker in BLOCKS.items():
        holding = [path for path, page in screens.items() if marker in page]
        assert holding == [HOMES[block]], (block, holding)
        assert screens[HOMES[block]].count(marker) == 1, block


def test_your_site_waits_on_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-3. Google is set up with nothing cached, and any request outward
    raises. Breaks when a tile asks Google or GitHub for its figure."""
    def refused(self, *args, **kwargs):
        raise OSError("no network in this test")
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", refused)
    client = _NoNetwork()
    with _served(_site(tmp_path, google=True), client) as browser:
        page = browser.get("/")
    assert client.requests == 0
    tile = page.split("<h2>Visitors</h2>", 1)[1].split("</section>", 1)[0]
    assert "No figures yet." in tile


def test_a_journal_that_is_off(tmp_path: Path) -> None:
    """INV-4. Breaks when the New entry form shows on a site whose entries
    cannot publish, or the tile does not say Off."""
    with _served(_site(tmp_path, journal=False)) as browser:
        journal, home = browser.get("/journal"), browser.get("/")
    assert BLOCKS["the New entry form"] not in journal
    assert BLOCKS["the journal switch"] in journal
    assert "not on your site while the journal is off" in journal
    tile = home.split("<h2>Journal</h2>", 1)[1].split("</section>", 1)[0]
    assert "Off." in tile


def _waiting_line(page: str) -> str:
    """The line on Your site counting changes not on the site yet, or ''."""
    if 'class="waiting"' not in page:
        return ""
    return page.split('<p class="waiting">', 1)[1].split("</p>", 1)[0]


def test_your_site_counts_the_changes_not_on_it(tmp_path: Path) -> None:
    """PRESS-0364. A waiting page, a waiting part, a draft and a published
    entry's changes each count once, and each kind opens its screen. Breaks
    when a kind is missed, counted twice, or links nowhere."""
    folder = _site(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "index", "<p>New home.</p>", waiting=True)
    store.write_html(folder, store.FURNITURE_FOLDER, "header", "<p>Top.</p>", waiting=True)
    store.write(folder, dataclasses.replace(
        tp._entry("harbour-changes"), extra=((editor.REPLACES, "harbour"),)), draft=True)
    with _served(folder) as browser:
        line = _waiting_line(browser.get("/"))
    assert line == (
        "4 changes are not on your site yet: "
        f'<a href="{editor.PAGES_ADDRESS}">1 page</a>, '
        f'<a href="{editor.PAGES_ADDRESS}">1 part of every page</a>, '
        f'<a href="{editor.JOURNAL_ADDRESS}">2 journal entries</a>.')


def test_your_site_says_nothing_when_nothing_waits(tmp_path: Path) -> None:
    """PRESS-0364. With no draft and no waiting copy there is no line, and
    with the journal off its drafts cannot reach the site, so they are not
    counted. Breaks when an empty or impossible count shows."""
    folder = _site(tmp_path)
    store.path_for(folder, "seaside", draft=True).unlink()
    with _served(folder) as browser:
        assert _waiting_line(browser.get("/")) == ""
    (tmp_path / "off").mkdir()
    off = _site(tmp_path / "off", journal=False)
    with _served(off) as browser:
        assert _waiting_line(browser.get("/")) == ""


def test_a_stray_draft_file_is_reported_once(tmp_path: Path) -> None:
    """PRESS-0364. The count reads the drafts the Journal tile reads, so
    its notices repeat the tile's. Breaks when the count reports them again."""
    folder = _site(tmp_path)
    stray = store.path_for(folder, "seaside", draft=True).with_name(".txt")
    stray.write_text("not an entry\n", encoding="utf-8")
    with _served(folder) as browser:
        page = browser.get("/")
    assert page.count("drafts/.txt was passed over") == 1
