# INV-1 and INV-14 for PRESS-0125 (the Import anyone runs): the wizard at
# /import, on a served Face. No network: every export here names no file to
# fetch, or the fetch is replaced.
#
# Why this exists: docs/specs/PRESS-0125-wordpress-import.md §§ 4.1, 4.2 and
# 4.8. Import writes a whole site, so it must never write over one, and its
# Report shows what an export from anyone names, so nothing in it may run.
from __future__ import annotations

import io
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from _face_session import Browser
from PIL import Image
from test_importer import _export, _item
from test_publishing import _settings

import pressless_import
from pressless import (
    editor,
    face,
    files_screen,
    importing,
    page_editor,
    settings,
    setup,
    sitefile,
    sites,
    store,
)
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
    assert "could not bring your site in" in page and 'value="bring"' in page
    assert not store.holds_a_site(folder)


def test_setups_done_page_offers_import_where_nothing_was_filled():
    """§ 4.1: setup's done page links to /import where the starter was not
    filled and the Store holds no site, and nowhere else."""
    from test_builder import _settings

    final = _settings()
    assert setup.IMPORT in setup._done(final, None, False, empty=True)
    assert setup.IMPORT not in setup._done(final, None, True, empty=True)
    assert setup.IMPORT not in setup._done(final, None, False, empty=False)


# ------------------------------------------------- a folder of pages (PRESS-0210) ---

FOLDER_ADDRESS = "/import/folder"


def _zipped(files: dict[str, str | bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as made:
        for path, content in files.items():
            made.writestr(path, content)
    return out.getvalue()


def _folder_step(browser: Browser, step: str) -> str:
    status, _headers, page = browser.request("POST", FOLDER_ADDRESS,
                                             {"step": step, "go": "next"})
    assert status == 200, (step, status)
    return page


def _handed_over(browser: Browser, files: dict[str, str | bytes]) -> bytes:
    status, _headers, page = browser.raw("POST", f"{FOLDER_ADDRESS}/zip", _zipped(files))
    assert status == 200 and b'value="folder"' in page, page[:400]
    return page


SMALL_SITE = {
    "site/index.html": "<html><head><title>Home</title></head><body><p>Home</p></body></html>",
    "site/about.html": "<html><head><title>About</title></head><body><p>About</p></body></html>",
    "site/tool.exe": b"MZ",
}


def test_a_folder_goes_only_into_an_empty_store(tmp_path):
    """INV-1: /import/folder on a filled Store redirects to /, and bring_in_folder
    into a Store where store.holds_a_site is True raises ImportStopped.

    Breaks when the check is made at the first step only."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        status, _headers, page = browser.request("GET", FOLDER_ADDRESS)
        assert status == 200 and 'value="folder"' in page
        _handed_over(browser, SMALL_SITE)
        _folder_step(browser, "folder")
        _folder_step(browser, "found")
        store.write(folder, store.Entry(slug="his", title="", date=datetime(2020, 1, 2),
                                        categories=(), tags=(), body="Words.", extra=()),
                    draft=False)
        status, headers, _page = browser.request(
            "POST", FOLDER_ADDRESS, {"step": "bring", "go": "next"})
        assert status == 303 and headers["Location"] == "/"
        status, headers, _page = browser.request("GET", FOLDER_ADDRESS)
        assert status == 303 and headers["Location"] == "/"
        status, headers, _page = browser.raw("POST", f"{FOLDER_ADDRESS}/zip",
                                             _zipped(SMALL_SITE))
        assert status == 303
    finally:
        served.stop()
    assert store.list_html(folder, store.PAGES_FOLDER) == ()
    with pytest.raises(ImportStopped):
        pressless_import.bring_in_folder(folder / "import" / "folder", folder)


def test_the_folder_wizard_brings_a_site_in(tmp_path):
    """§ 4.2: the three steps, from the ZIP to the Report, which is also written
    to import/report.txt; the folder's progress is forgotten and the folder gone."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        held = _handed_over(browser, SMALL_SITE)
        assert b"Compressed (zipped) folder" in held
        found = _folder_step(browser, "folder")
        assert 'value="found"' in found and "tool.exe" in found and "own look" in found
        assert (folder / "wizards" / "import-folder.json").is_file()
        _folder_step(browser, "found")
        page = _folder_step(browser, "bring")
        assert "about.html" in page and "tool.exe" in page, page
        assert "published entries" not in page, "a folder has no posts to count"
        status, headers, _page = browser.request("GET", FOLDER_ADDRESS)
        assert status == 303 and headers["Location"] == "/"
    finally:
        served.stop()
    assert set(store.list_html(folder, store.PAGES_FOLDER)) == {"index", "about"}
    assert store.read_style_code(folder) == ""
    assert "about.html" in (folder / "import" / "report.txt").read_text(encoding="utf-8")
    assert not (folder / "import" / "folder").exists()
    assert not (folder / "wizards" / "import-folder.json").exists()


def test_a_zip_that_holds_no_page_is_refused_and_not_kept(tmp_path):
    """§ 6: the folder step says so; nothing is kept. Next is then refused."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        assert b"holds no web page" in _handed_over(browser, {"notes.txt": "Words."})
        assert not (folder / "import" / "folder").exists()
        assert b"could not read that ZIP" in _handed_over_bytes(browser, b"not a zip")
        page = _folder_step(browser, "folder")
        assert 'value="folder"' in page and "Choose a ZIP" in page, page
    finally:
        served.stop()
    assert not list(folder.glob(".upload-*"))


def _handed_over_bytes(browser: Browser, body: bytes) -> bytes:
    status, _headers, page = browser.raw("POST", f"{FOLDER_ADDRESS}/zip", body)
    assert status == 200, page[:200]
    return page


def test_what_a_tool_builds_from_is_refused_at_the_folder_step(tmp_path):
    """§ 4.2's check before Next: `built_by_a_tool`."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        _handed_over(browser, {"_config.yml": "x", "index.html": "<p>Home</p>"})
        page = _folder_step(browser, "folder")
        assert 'value="folder"' in page and "a tool builds" in page, page
    finally:
        served.stop()


def test_a_new_zip_replaces_the_held_folder(tmp_path):
    """§ 4.2: a new ZIP replaces import/folder/ and deletes import/folder.json."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        _handed_over(browser, {"old.html": "<p>Old</p>"})
        (folder / "import" / "folder.json").write_text("{}", encoding="utf-8")
        _handed_over(browser, {"new.html": "<p>New</p>"})
    finally:
        served.stop()
    assert not (folder / "import" / "folder" / "old.html").exists()
    assert (folder / "import" / "folder" / "new.html").is_file()
    assert not (folder / "import" / "folder.json").exists()


def test_what_a_zip_left_out_is_shown_and_reported(tmp_path):
    """§ 4.2: `unpack_folder`'s answer is kept in import/folder-left.json, shown
    on the found step, and passed to bring_in_folder as `left`."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        _handed_over(browser, {"index.html": "<p>Home</p>", "con/x.txt": "refused"})
        assert "con/x.txt" in _folder_step(browser, "folder")
        _folder_step(browser, "found")
        assert "con/x.txt" in _folder_step(browser, "bring")
    finally:
        served.stop()


def test_the_folder_screens_escape_what_they_name(tmp_path):
    """INV-18: a file named `<img src=x>.exe` and a title of `<script>`, on the
    found step and the Report. Breaks when a path is written raw."""
    folder = tmp_path / "site"
    folder.mkdir()
    served, browser = _serve(folder)
    try:
        _handed_over(browser, {
            "index.html": "<html><head><title>&lt;script&gt;</title></head>"
                          '<body><a href="<img src=y>.html">Gone</a></body></html>',
            "<img src=x>.exe": b"MZ"})
        found = _folder_step(browser, "folder")
        assert "<img src=x>" not in found and "&lt;img src=x&gt;" in found, found
        _folder_step(browser, "found")
        page = _folder_step(browser, "bring")
    finally:
        served.stop()
    assert "<img src=x>" not in page and "&lt;img src=x&gt;" in page, page
    assert "<img src=y>" not in page and "&lt;script&gt;" not in page.replace(
        "&lt;img src=x&gt;", ""), page


def test_a_brought_in_script_is_not_run_by_the_face(tmp_path):
    """INV-19, and the early check PRESS-0210 asked for: a preview of a brought-in
    page answers with script-src 'none', and the `../photographs/` and `../files/`
    addresses its code sections hold are served there.

    Breaks when a brought-in page is served by a route outside that policy."""
    folder = tmp_path / "site"
    folder.mkdir()
    picture = io.BytesIO()
    Image.new("RGB", (4, 3), "teal").save(picture, "PNG")
    pressless_import.bring_in_folder(_laid_out_folder(tmp_path, {
        "index.html": "<html><head><title>H</title></head><body><p>Home</p></body></html>",
        "about.html": ('<html><head><title>A</title></head><body>'
                       '<div class="odd"><img src="pic.png" alt=""><a href="doc.pdf">Doc</a></div>'
                       "<script>document.title = 'ran';</script></body></html>"),
        "pic.png": picture.getvalue(), "doc.pdf": b"%PDF-1.4 words\n"}), folder)
    settings.save(folder, _settings(folder))
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        page_editor.register(served, folder)
        files_screen.register(served, folder)
        browser = Browser(served)
        status, _headers, page = browser.request("GET", "/page?kind=pages&name=about")
        assert status == 200, page[:400]
        preview = re.search(r'src="(/preview/[^"]*pages/about\.html)', page)
        assert preview, page[:2000]
        status, headers, shown = browser.request("GET", preview.group(1))
        assert status == 200 and "document.title" in shown
        assert "script-src 'none'" in headers["Content-Security-Policy"]
        assert 'src="../photographs/pic.png"' in shown and 'href="../files/doc.pdf"' in shown
        where = preview.group(1).rsplit("/pages/", 1)[0]
        assert browser.request("GET", f"{where}/photographs/pic.png")[0] == 200
        assert browser.request("GET", f"{where}/files/doc.pdf")[0] == 200
    finally:
        served.stop()


def _laid_out_folder(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    held = tmp_path / "held"
    for path, content in files.items():
        (held / path).parent.mkdir(parents=True, exist_ok=True)
        (held / path).write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return held


def test_both_offers_name_the_folder_wizard():
    """§ 4.2: the two offers PRESS-0125 § 4.1 shows gain a second link."""
    from test_builder import _settings as final

    assert FOLDER_ADDRESS in setup._done(final(), None, False, empty=True)
    assert setup.import_offer().count('href="') == 2 and FOLDER_ADDRESS in setup.import_offer()
