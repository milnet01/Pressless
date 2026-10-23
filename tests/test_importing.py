# INV-1 and INV-14 for PRESS-0125 (the Import anyone runs): the wizard at
# /import, on a served Face. No network: every export here names no file to
# fetch, or the fetch is replaced.
#
# Why this exists: docs/specs/PRESS-0125-wordpress-import.md §§ 4.1, 4.2 and
# 4.8. Import writes a whole site, so it must never write over one, and its
# Report shows what an export from anyone names, so nothing in it may run.
from __future__ import annotations

import time
from pathlib import Path

import pytest
from _face_session import Browser
from test_importer import _export, _item

import pressless_import
from pressless import face, importing, setup, sitefile, sites, store
from pressless_import import ImportStopped


def _serve(folder: Path):
    served = face.serve(folder)
    importing.register(served, folder)
    return served, Browser(served)


def _next(browser: Browser, step: str, **fields) -> str:
    status, _headers, page = browser.request("POST", importing.ADDRESS,
                                             {"step": step, "go": "next", **fields})
    assert status == 200, (step, status)
    return page


def _through_fetching(browser: Browser) -> str:
    """Next on the media step until the fetch has ended."""
    for _ in range(100):
        page = _next(browser, "media")
        if 'value="gaps"' in page:
            return page
        time.sleep(0.05)
    raise AssertionError("the fetch never ended")


def _bring_in(browser: Browser, export_text: str) -> str:
    status, _headers, page = browser.raw("POST", f"{importing.ADDRESS}/export",
                                         export_text.encode("utf-8"))
    assert status == 200 and b'value="export"' in page, page[:400]
    _next(browser, "export")
    _through_fetching(browser)
    _next(browser, "gaps")
    _next(browser, "look", look="harbour")
    return _next(browser, "bring")


def test_import_answers_only_on_an_empty_store(tmp_path):
    """INV-1: /import on a Store holding a site redirects to /, and bring_in
    into such a folder raises ImportStopped.

    Breaks when the check is made at the first step only, and a site written
    in another window is overwritten at Bring it in."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        status, _headers, page = browser.request("GET", importing.ADDRESS)
        assert status == 200 and 'value="export"' in page
        browser.raw("POST", f"{importing.ADDRESS}/export",
                    _export(_item(1, slug="one")).encode("utf-8"))
        _next(browser, "export")
        _through_fetching(browser)
        _next(browser, "gaps")
        _next(browser, "look", look="harbour")
        # Another window writes a site before Bring it in.
        store.write(folder, store.Entry(slug="his", title="", date=__import__(
            "datetime").datetime(2020, 1, 2), categories=(), tags=(), body="Words.",
            extra=()), draft=False)
        status, headers, _page = browser.request(
            "POST", importing.ADDRESS, {"step": "bring", "go": "next"})
        assert status == 303 and headers["Location"] == "/"
        status, headers, _page = browser.request("GET", importing.ADDRESS)
        assert status == 303 and headers["Location"] == "/"
        status, headers, _page = browser.raw("POST", f"{importing.ADDRESS}/export",
                                             _export(_item(1)).encode("utf-8"))
        assert status == 303
    finally:
        served.stop()
    assert store.list_slugs(folder, draft=False) == ("his",)
    with pytest.raises(ImportStopped):
        pressless_import.bring_in(folder / "import" / "export.xml",
                                  folder / "import" / "media", folder, "harbour")


def test_the_wizard_brings_a_site_in(tmp_path):
    """§ 4.2: the five steps, from the export to the Report; the export is
    kept in import/, the Report written beside it, and /import then leads
    to the list."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        page = _bring_in(browser, _export(
            _item(1, slug="one", body="Words."),
            _item(2, status="pending", slug="waiting"),
            _item(5, kind="page", slug="about", title="About"),
            _item(9, kind="wp_block", slug="reused")))
        assert "waiting" in page and "wp_block" in page, page
        status, headers, _page = browser.request("GET", importing.ADDRESS)
        assert status == 303 and headers["Location"] == "/"
    finally:
        served.stop()
    assert store.list_slugs(folder, draft=False) == ("one",)
    assert store.list_html(folder, store.PAGES_FOLDER) == ("index",)
    assert (folder / "import" / "export.xml").is_file()
    report = (folder / "import" / "report.txt").read_text(encoding="utf-8")
    assert "waiting" in report and "wp_block" in report, report
    assert not (folder / "wizards" / "import.json").exists(), "the progress is forgotten"


def test_an_upload_that_is_not_an_export_is_refused_and_not_kept(tmp_path):
    """§ 6: the export step says so; nothing is kept."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        status, _headers, page = browser.raw(
            "POST", f"{importing.ADDRESS}/export",
            b'<?xml version="1.0"?>\n<!DOCTYPE rss [<!ENTITY a "a">]><rss/>')
        assert status == 200 and b'value="export"' in page
        page = _next(browser, "export")
        assert 'value="export"' in page, "Next is refused without an export"
    finally:
        served.stop()
    assert not (folder / "import" / "export.xml").exists()
    assert not list(folder.glob(".upload-*"))


def test_the_report_escapes_what_it_names(tmp_path):
    """INV-14: every value in the Report page is escaped, and a control
    character is shown escaped.

    Breaks when a slug or title is written raw."""
    folder = tmp_path / "site"
    folder.mkdir()
    hostile = "<script>alert(1)</script>\x1b"
    nav = (f'<!-- wp:navigation-link {{"label":"{hostile.replace(chr(27), "")}\\u001b",'
           '"url":"javascript:alert(1)","kind":"custom"} /-->')
    served, browser = _serve(folder)
    try:
        page = _bring_in(browser, _export(
            _item(1, slug="one"),
            _item(40, kind="wp_navigation", title="&lt;script&gt;menu", body=nav)))
    finally:
        served.stop()
    shown = page[page.index('<ul class="import-report">'):]
    assert "<script>menu" not in shown and "&lt;script&gt;menu" in shown, shown
    assert "\x1b" not in page and "\\x1b" in shown, shown


def test_a_count_of_one_takes_the_singular(tmp_path):
    """PRESS-0294: one post and one page are counted as "1 post" and "1 page",
    on the media step and in the Report.

    Breaks when a count is written into a plural noun again ("1 pages")."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        browser.raw("POST", f"{importing.ADDRESS}/export", _export(
            _item(1, slug="one"), _item(2, kind="page", slug="about")).encode("utf-8"))
        media = _next(browser, "export")
        _through_fetching(browser)
        _next(browser, "gaps")
        _next(browser, "look", look="harbour")
        report = _next(browser, "bring")
    finally:
        served.stop()
    assert "1 post, 1 page and 0 photographs and files." in media, media
    assert "1 published entry, 0 drafts, 0 comments" in report, report


def test_import_is_offered_only_on_a_store_holding_no_site(tmp_path):
    """§ 4.1: the list page links to /import while the Store holds no site."""
    folder = tmp_path / "site"
    folder.mkdir()
    served = face.serve(folder)
    try:
        importing.register(served, folder)
        assert any(importing.ADDRESS in piece for piece in served.list_pieces(above=True))
        store.write(folder, store.Entry(slug="his", title="", date=__import__(
            "datetime").datetime(2020, 1, 2), categories=(), tags=(), body="Words.",
            extra=()), draft=False)
        assert not any(importing.ADDRESS in piece for piece in served.list_pieces(above=True))
    finally:
        served.stop()
    assert setup.IMPORT == importing.ADDRESS


def test_the_import_folder_is_the_sites_and_never_saved(tmp_path):
    """§ 4.2: `import` moves with a site and a saved site file never carries
    the export."""
    assert "import" in sites.SITE_NAMES and "import" in sitefile.LEFT_OUT
    assert pressless_import.IMPORT_FOLDER == "import"


def test_moves_left_part_done_finish_at_start(tmp_path, monkeypatch):
    """§ 4.7: while import/moving exists, finish_moves completes them."""
    folder = tmp_path / "site"
    (folder / "import" / "work").mkdir(parents=True)
    store.write(folder / "import" / "work", store.Entry(
        slug="one", title="", date=__import__("datetime").datetime(2020, 1, 2),
        categories=(), tags=(), body="Words.", extra=()), draft=False)
    (folder / "import" / "moving").write_bytes(b"")
    assert importing.finish_moves(folder) is None
    assert store.list_slugs(folder, draft=False) == ("one",)
    assert not (folder / "import" / "moving").exists()


def test_a_stopped_import_says_so_and_writes_nothing(tmp_path):
    """§ 4.7 and § 6: a Store refusal at Bring it in is shown in Import's own
    words, and the Store still holds no site."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        page = _bring_in(browser, _export(_item(1, slug="one", categories=("a,b",))))
    finally:
        served.stop()
    assert "could not bring your WordPress site in" in page and 'value="bring"' in page
    assert not store.holds_a_site(folder)


def test_setups_done_page_offers_import_where_nothing_was_filled():
    """§ 4.1: setup's done page links to /import where the starter was not
    filled and the Store holds no site, and nowhere else."""
    from test_builder import _settings

    final = _settings()
    assert setup.IMPORT in setup._done(final, None, False, empty=True)
    assert setup.IMPORT not in setup._done(final, None, True, empty=True)
    assert setup.IMPORT not in setup._done(final, None, False, empty=False)
