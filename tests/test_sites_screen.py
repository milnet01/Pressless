# The Sites screen (PRESS-0223 § 4.6): opening another site, and refusing a
# site that is not there.
from __future__ import annotations

import datetime
import io
import json
import time
import zipfile
from pathlib import Path

from _face_session import Browser
from test_publishing import _entry

from pressless import backups, editor, face, sitefile, sites, sites_screen, store

OPEN = "sites.json"


def _own(tmp_path: Path) -> Path:
    own = tmp_path / "own"
    for name in ("site-1", "site-2"):
        (own / "sites" / name).mkdir(parents=True)
    sites.choose(own, "site-1")
    return own


def _settled(restarts: list[int], count: int) -> list[int]:
    """The restart is asked for after the answer is sent, on the server's own
    thread, so the answer can arrive first. Waits up to five seconds."""
    deadline = time.monotonic() + 5
    while len(restarts) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    return restarts


def _serve(own: Path, restarts: list[int]) -> tuple[face.Face, Browser]:
    """One pass of the launcher, as __main__._serve_once makes it: the open
    site's editor, and the Sites screen over Pressless's own folder."""
    site = sites.open_site(own)
    served = face.serve(own, site=site)
    editor.register(served, site)
    sites_screen.register(served, own, lambda: restarts.append(1))
    return served, Browser(served)


def test_sites_keep_their_own_writing(tmp_path: Path) -> None:
    """INV-7. Breaks when two sites share a Store folder."""
    own = _own(tmp_path)
    store.write(own / "sites" / "site-1", _entry("seaside-walk"), draft=True)
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        assert "Seaside-Walk" in browser.request("GET", "/")[2]
        status, _, page = browser.request("POST", "/sites/open", {"site": "site-2"})
        assert status == 200 and "Pressless is restarting." in page
    finally:
        served.stop()
    assert _settled(restarts, 1) == [1]
    served, browser = _serve(own, restarts)
    try:
        assert "Seaside-Walk" not in browser.request("GET", "/")[2]
    finally:
        served.stop()
    assert (own / "sites" / "site-1" / "drafts" / "seaside-walk.txt").is_file()
    assert not (own / "sites" / "site-2" / "drafts").exists()


def test_a_bad_site_changes_nothing(tmp_path: Path) -> None:
    """INV-8. Breaks when the form's value reaches a path."""
    own = _own(tmp_path)
    before = (own / OPEN).read_bytes()
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        for named in ("../site-1", "site-7", "sites/site-2", ""):
            status, _, page = browser.request("POST", "/sites/open", {"site": named})
            assert status == 200 and "That site is not here any more." in page, named
    finally:
        served.stop()
    assert (own / OPEN).read_bytes() == before
    assert restarts == []


def test_the_screen_lists_each_site_by_name_and_starts_a_new_one(tmp_path: Path) -> None:
    """§ 4.6. Breaks when a site is listed by its folder rather than its name,
    the open one is offered to open, or a new site is not opened next."""
    own = _own(tmp_path)
    store.write_identity(own / "sites" / "site-2", store.Identity("The Second Site"))
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        page = browser.request("GET", "/sites")[2]
        assert "New site</b> (open now)" in page
        assert "The Second Site" in page and 'value="site-2"' in page
        assert 'value="site-1"' not in page
        browser.request("POST", "/sites/new")
    finally:
        served.stop()
    assert json.loads((own / OPEN).read_text(encoding="utf-8"))["open"] == "site-3"
    assert (own / "sites" / "site-3").is_dir() and _settled(restarts, 1) == [1]


# ------------------------------------------------------------ PRESS-0224 ----


def test_save_downloads_the_site(tmp_path: Path) -> None:
    """PRESS-0224 INV-9. Breaks when the file is answered inline, or left in
    the folder."""
    own = _own(tmp_path)
    site = own / "sites" / "site-1"
    store.write_identity(site, store.Identity("Sea & Sky!"))
    store.write(site, _entry("seaside-walk"), draft=True)
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        status, headers, data = browser.raw("GET", "/sites/save")
    finally:
        served.stop()
    assert status == 200
    stamp = datetime.date.today().isoformat()
    assert headers["Content-Disposition"].startswith(
        f'attachment; filename="Sea Sky {stamp}.zip"')
    with zipfile.ZipFile(io.BytesIO(data)) as saved:
        assert "drafts/seaside-walk.txt" in saved.namelist()
    assert not list(own.glob(".saving-*"))


def test_an_opened_file_becomes_the_next_site(tmp_path: Path) -> None:
    """PRESS-0224 § 4.5: the upload opens the file as a site and restarts;
    a refused file shows the screen again and changes nothing."""
    origin = _own(tmp_path / "a")
    store.write(origin / "sites" / "site-1", _entry("seaside-walk"), draft=True)
    saved = tmp_path / "saved.zip"
    sitefile.save(origin / "sites" / "site-1", saved)
    own = _own(tmp_path / "b")
    store.write(own / "sites" / "site-1", _entry("own-writing"), draft=True)
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        status, _, page = browser.raw("POST", "/sites/open-file", b"not a zip")
        assert status == 200 and b"could not be opened" in page and restarts == []
        status, _, page = browser.raw("POST", "/sites/open-file", saved.read_bytes())
        assert status == 200 and b"Pressless is restarting." in page
    finally:
        served.stop()
    assert _settled(restarts, 1) == [1]
    assert json.loads((own / OPEN).read_text(encoding="utf-8"))["open"] == "site-3"
    assert (own / "sites" / "site-3" / "drafts" / "seaside-walk.txt").is_file()
    assert not list(own.glob(".upload-*"))


# ------------------------------------------------------------ PRESS-0225 ----


def test_the_screen_sets_where_backups_go_and_says_what_went_wrong(tmp_path: Path) -> None:
    """PRESS-0225. Breaks when a chosen folder is not kept, a bad one is,
    or a failed backup is not said."""
    own = _own(tmp_path)
    chosen = tmp_path / "usb drive"
    chosen.mkdir()
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        page = browser.request("GET", "/sites")[2]
        assert "the Pressless-backups folder beside the program" in page
        page = browser.request("POST", "/sites/backups", {"folder": "not/a/whole/address"})[2]
        assert "That is not the address of a folder" in page
        assert backups.folder_of(own) == tmp_path / "Pressless-backups"
        page = browser.request("POST", "/sites/backups", {"folder": str(chosen)})[2]
        assert "Backups now go to the folder you chose." in page
        backups._write(own, trouble="The last backup could not be made in the x folder: y.")
        page = browser.request("GET", "/sites")[2]
        assert "The last backup could not be made" in page
    finally:
        served.stop()
    assert backups.folder_of(own) == chosen and restarts == []


# ------------------------------------------------------------ PRESS-0221 ----


def test_the_move_wizard_saves_each_site_and_says_what_comes_next(tmp_path: Path) -> None:
    """PRESS-0221. Breaks when the wizard is a page of its own rather than a
    dialog, a site has no way to be saved from it, or a step is missing."""
    own = _own(tmp_path)
    store.write_identity(own / "sites" / "site-2", store.Identity("Hill Notes"))
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        page = browser.request("GET", "/sites")[2]
    finally:
        served.stop()
    assert 'data-help="move-wizard"' in page
    wizard = page.split('<dialog id="move-wizard"', 1)[1].split("</dialog>", 1)[0]
    assert wizard.count('data-step="') == 3
    assert 'href="/sites/save?site=site-1"' in wizard
    assert 'href="/sites/save?site=site-2"' in wizard and "Hill Notes" in wizard
    assert "Open a site file" in wizard and "publishing key" in wizard


def test_save_takes_any_site_and_refuses_one_that_is_not_there(tmp_path: Path) -> None:
    """PRESS-0221: the wizard saves each site, open or not. Breaks when the
    open site is saved in another's place, or a bad name reaches a path."""
    own = _own(tmp_path)
    second = own / "sites" / "site-2"
    store.write_identity(second, store.Identity("Hill Notes"))
    store.write(second, _entry("on-the-hill"), draft=True)
    restarts: list[int] = []
    served, browser = _serve(own, restarts)
    try:
        status, headers, data = browser.raw("GET", "/sites/save?site=site-2")
        refused = browser.raw("GET", "/sites/save?site=../site-2")
    finally:
        served.stop()
    assert status == 200 and "Hill Notes" in headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(data)) as saved:
        assert "drafts/on-the-hill.txt" in saved.namelist()
    assert refused[0] == 200 and b"That site is not here any more." in refused[2]
    assert not list(own.glob(".saving-*"))


def test_the_file_box_sends_to_open_file_and_reads_opening(tmp_path: Path) -> None:
    """PRESS-0224 § 4.6. Breaks when the Sites screen's file box sends
    elsewhere, or no longer reads Opening… while it sends."""
    page = sites_screen._screen(_own(tmp_path))
    assert 'data-to="/sites/open-file"' in page
    assert 'data-sending="script.sites.opening"' in page


def _other_site(own: Path) -> Path:
    other = sites.new_site(own)
    store.write_identity(other, store.Identity("The other one"))
    (other / "kept.txt").write_text("words", encoding="utf-8")
    return other


def test_removing_a_site_asks_then_keeps_a_copy_and_lists_it_no_more(tmp_path: Path) -> None:
    """PRESS-0291. Breaks when the folder goes before its copy is whole, or with no asking."""
    own = _own(tmp_path)
    other = _other_site(own)
    (tmp_path / "kept-here").mkdir()
    backups.set_folder(own, str(tmp_path / "kept-here"))
    served, browser = _serve(own, [])
    try:
        asked = browser.request("POST", "/sites/remove", {"site": other.name})[2]
        assert "The other one" in asked and other.is_dir(), "the first press only asks"
        assert not list((tmp_path / "kept-here").iterdir())
        page = browser.request("POST", "/sites/remove", {"site": other.name, "sure": "yes"})[2]
    finally:
        served.stop()
    assert f'value="{other.name}"' not in page
    assert sorted(path.name for path in other.parent.iterdir()) == ["site-1", "site-2"]
    held = list((tmp_path / "kept-here").glob("*.zip"))
    assert len(held) == 1 and held[0].name in page
    with zipfile.ZipFile(held[0]) as copy:
        assert any(name.endswith("identity") or "identity" in name for name in copy.namelist())


def test_the_open_site_and_a_stranger_cannot_be_removed(tmp_path: Path) -> None:
    own = _own(tmp_path)
    open_now = sites.open_site(own)
    served, browser = _serve(own, [])
    try:
        for name in (open_now.name, "site-99", "../site-1", ""):
            browser.request("POST", "/sites/remove", {"site": name, "sure": "yes"})
    finally:
        served.stop()
    assert open_now.is_dir() and not (own.parent / backups.DEFAULT_FOLDER).exists()


def test_a_copy_that_cannot_be_written_removes_nothing(tmp_path: Path, monkeypatch) -> None:
    own = _own(tmp_path)
    other = _other_site(own)
    def refuse(_site, _target):
        raise OSError("the drive is full")
    monkeypatch.setattr(sites_screen.sitefile, "save", refuse)
    served, browser = _serve(own, [])
    try:
        browser.request("POST", "/sites/remove", {"site": other.name, "sure": "yes"})
    finally:
        served.stop()
    assert (other / "kept.txt").is_file()


def test_a_second_copy_the_same_day_overwrites_nothing(tmp_path: Path) -> None:
    own = _own(tmp_path)
    folder = tmp_path / "kept-here"
    folder.mkdir()
    backups.set_folder(own, str(folder))
    first = _other_site(own)
    served, browser = _serve(own, [])
    try:
        browser.request("POST", "/sites/remove", {"site": first.name, "sure": "yes"})
        again = _other_site(own)
        browser.request("POST", "/sites/remove", {"site": again.name, "sure": "yes"})
    finally:
        served.stop()
    assert len(list(folder.glob("*.zip"))) == 2
