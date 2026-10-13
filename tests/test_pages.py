# Adding, removing and renaming a page, with the menu following (PRESS-0195).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0195-add-remove-rename-pages.md § 5. The page editor's own
# fixtures are reused: this item works on the same Store, server and fake
# GitHub as PRESS-0014's tests.
from __future__ import annotations

import html
import json
from pathlib import Path

import pytest
from test_page_editor import (
    _binned,
    _digest,
    _folder,
    _key,
    _live,
    _pages,
    _save,
    _uploaded,
    _waiting,
)
from test_publisher import _listing, _reads, _Transport, _writes

from pressless import settings, store

MENU = ('<nav><a href="{{UP}}index.html" data-nav="Home">Home</a> '
        '<a href="{{UP}}pages/about.html" data-nav="about">About</a> '
        '<a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a></nav>')
UNUSUAL = ('<nav><ul><li><a href="{{UP}}pages/about.html">About</a></li></ul></nav>')


def _folder_with_menu(root: Path, menu: str = MENU) -> Path:
    folder = _folder(root)
    store.write_html(folder, store.FURNITURE_FOLDER, "navigation", menu)
    return folder


def _github(*paths: str) -> _Transport:
    """A GitHub whose site already holds `paths`, so a removal shows up."""
    return _Transport(reads=_reads(_listing([(path, "old-sha") for path in paths])),
                      writes=_writes())


def _refusing() -> _Transport:
    return _Transport(responses=[(401, {}, b'{"message": "Bad credentials"}')])


def _removed(transport: _Transport) -> set[str]:
    trees = [json.loads(body) for method, url, body, _ in transport.requests
             if method == "POST" and url.endswith("/git/trees")]
    return {entry["path"] for tree in trees for entry in tree["tree"] if entry["sha"] is None}


def _new(browser, name: str) -> tuple[int, dict, str]:
    return browser.request("POST", "/page/new", {"name": name})


def _reshape(browser, route: str, name: str, to: str = "") -> dict:
    status, _, text = browser.request("POST", f"/page/{route}",
                                      {"kind": "pages", "name": name, "to": to})
    assert status == 200, text
    return json.loads(text)


def _held(folder: Path) -> list[tuple[str, bytes]]:
    """Every file the Store holds, with its bytes; the server's own log is not
    one."""
    return sorted((p.relative_to(folder).as_posix(), p.read_bytes())
                  for p in folder.rglob("*") if p.is_file() and p.name != "pressless.log")


def _menu(folder: Path, waiting: bool = False) -> str:
    return store.read_html(store.html_path_for(folder, "furniture", "navigation",
                                               waiting=waiting))


# ------------------------------------------------------------ a new page ---


def test_a_new_page_waits(tmp_path):
    """INV-1: /page/new writes the waiting copy and nothing else -- no live
    page, the menu byte-identical -- and the list shows the page.

    Breaks when the route writes the live file, or the list reads live pages
    only."""
    folder = _folder_with_menu(tmp_path)
    with _pages(folder) as browser:
        status, headers, _ = _new(browser, "Gigs & Tours")
        assert status == 303
        assert headers["Location"] == "/page?kind=pages&name=gigs-tours"
        listed = browser.request("GET", "/")[2]
    copy = _waiting(folder, "pages", "gigs-tours").read_text(encoding="utf-8")
    assert "<title>Gigs &amp; Tours</title>" in copy
    assert '<!-- HEADER:START page="gigs-tours" -->' in copy
    assert not _live(folder, "pages", "gigs-tours").exists()
    assert _menu(folder) == MENU
    assert "/page?kind=pages&amp;name=gigs-tours" in listed


@pytest.mark.parametrize("name, code", [
    ("!!!", "empty"), ("Index", "taken"), ("About", "taken"),
    ("Waiting", "taken"), ("Old Gigs", "forwarded"), ("Con", "unusable"),
])
def test_a_taken_page_name_is_refused(tmp_path, name, code):
    """INV-2: each § 4.3 step 1 refusal writes nothing and sends the list a
    hint it shows under the box.

    Breaks when a taken name is suffixed or overwritten."""
    folder = _folder_with_menu(tmp_path)
    store.write_html(folder, "pages", "waiting", "<p>w</p>", waiting=True)
    store.write_page_forwards(folder, {"old-gigs": "about"})
    before = _held(folder)
    with _pages(folder) as browser:
        status, headers, _ = _new(browser, name)
        listed = browser.request("GET", headers["Location"])[2]
    assert status == 303 and headers["Location"] == f"/?page_hint={code}"
    assert _held(folder) == before
    hint = listed.split('<p id="page-hint" role="status">', 1)[1].split("</p>", 1)[0]
    assert hint, listed


def test_a_new_pages_first_press_adds_its_link(tmp_path, monkeypatch):
    """INV-3: the first press writes the live page and adds its link to the
    live menu and its waiting copy, and the site GitHub receives holds both.

    Breaks when the link is added at /page/new, or to one copy only."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path)
    store.write_html(folder, "furniture", "navigation", MENU.replace("Home<", "Start<"),
                     waiting=True)
    github = _github()
    with _pages(folder, github) as browser:
        _new(browser, "Live Shows")
        copy = _waiting(folder, "pages", "live-shows")
        status, _, text = _save(browser, "pages", "live-shows", "code",
                                copy.read_text(encoding="utf-8"), waiting=True,
                                base=_digest(copy), route="/page/publish")
    assert status == 200 and json.loads(text)["published"] is True, text
    link = '<a href="{{UP}}pages/live-shows.html" data-nav="live-shows">Live Shows</a>'
    assert _menu(folder) == MENU.replace("About</a>", "About</a> " + link)
    assert link in _menu(folder, waiting=True) and "Start<" in _menu(folder, waiting=True)
    assert _live(folder, "pages", "live-shows").is_file()
    uploaded = b"".join(_uploaded(github))
    assert b'href="../pages/live-shows.html"' in uploaded
    assert b"<title>Live Shows</title>" in uploaded


def test_a_failed_first_press_puts_back(tmp_path, monkeypatch):
    """INV-4: a failed first press leaves no live page and both menu texts
    byte-identical.

    Breaks when the put-back writes the absent page back as empty, or
    forgets the menu."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path)
    store.write_html(folder, "furniture", "navigation", MENU, waiting=True)
    with _pages(folder, _refusing()) as browser:
        _new(browser, "Gigs")
        copy = _waiting(folder, "pages", "gigs")
        status, _, text = _save(browser, "pages", "gigs", "code",
                                copy.read_text(encoding="utf-8"), waiting=True,
                                base=_digest(copy), route="/page/publish")
    assert status == 200 and json.loads(text)["published"] is False, text
    assert not _live(folder, "pages", "gigs").exists()
    assert _waiting(folder, "pages", "gigs").is_file()
    assert _menu(folder) == MENU and _menu(folder, waiting=True) == MENU


def test_an_unusual_menu_is_left_and_said(tmp_path, monkeypatch):
    """§ 4.3: a menu Pressless does not edit is left as it is, the page still
    publishes, and the reply says so.

    Breaks when the link is pasted into an <li> menu, or nothing is said."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path, UNUSUAL)
    with _pages(folder, _github()) as browser:
        _new(browser, "Gigs")
        copy = _waiting(folder, "pages", "gigs")
        reply = json.loads(_save(browser, "pages", "gigs", "code",
                                 copy.read_text(encoding="utf-8"), waiting=True,
                                 base=_digest(copy), route="/page/publish")[2])
    assert reply["published"] is True, reply
    assert _menu(folder) == UNUSUAL
    assert "laid out in a way Pressless does not edit" in html.unescape(reply["notices"])


def test_throwing_away_a_new_page_returns_to_the_list(tmp_path):
    """§ 4.3: throwing away a never-pressed page bins its only copy and
    answers with the list, not an editor with nothing to open.

    Breaks when the 303 still names the page."""
    folder = _folder_with_menu(tmp_path)
    with _pages(folder) as browser:
        _new(browser, "Gigs")
        copy = _waiting(folder, "pages", "gigs")
        status, headers, _ = browser.request("POST", "/page/discard", {
            "kind": "pages", "name": "gigs", "base": _digest(copy)})
    assert status == 303 and headers["Location"] == "/"
    assert not copy.exists()


# -------------------------------------------------------- remove, rename ---


def test_removing_a_page(tmp_path, monkeypatch):
    """INV-8: Remove bins the live page and its waiting copy, takes its link
    out, drops the forwards to it, and the site GitHub receives lacks it.

    Breaks when the waiting copy survives, so the page returns on the list."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path)
    store.write_html(folder, "pages", "about", "<p>unpressed</p>", waiting=True)
    store.write_page_forwards(folder, {"story": "about", "gigs": "shows"})
    store.write_html(folder, "pages", "shows", "<p>Shows</p>")
    github = _github("pages/about.html", "index.html")
    with _pages(folder, github) as browser:
        reply = _reshape(browser, "remove", "about")
    assert reply["published"] is True and reply["address"] == "/", reply
    assert not _live(folder, "pages", "about").exists()
    assert not _waiting(folder, "pages", "about").exists()
    assert {"pages/about.html", "pages-waiting/about.html"} <= set(_binned(folder))
    assert _menu(folder) == MENU.replace(
        ' <a href="{{UP}}pages/about.html" data-nav="about">About</a>', "")
    assert store.read_page_forwards(folder) == {"gigs": "shows"}
    assert "pages/about.html" in _removed(github)


def test_remove_and_rename_refusals(tmp_path, monkeypatch):
    """INV-9: each § 4.4 refusal writes nothing and presses nothing.

    Breaks when privacy is removable with measurement_id set."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path)
    store.write_html(folder, "pages", "privacy", "<p>Privacy</p>")
    store.write_html(folder, "pages", "busy", "<p>b</p>")
    store.write_html(folder, "pages", "busy", "<p>changed</p>", waiting=True)
    store.write_html(folder, "pages", "new-one", "<p>n</p>", waiting=True)
    store.write_page_forwards(folder, {"old": "shows"})
    saved = settings.load(folder)
    settings.save(folder, settings.Settings(**{**saved.__dict__,
                                              "measurement_id": "G-TESTVALUE1"}))
    cases = [("remove", "index", ""), ("rename", "index", "Home two"),
             ("remove", "new-one", ""), ("remove", "privacy", ""),
             ("rename", "privacy", "Data"), ("rename", "busy", "Busy two"),
             ("rename", "about", ""), ("rename", "about", "About"),
             ("rename", "about", "Privacy"), ("rename", "about", "New One"),
             ("rename", "about", "Old")]
    before = _held(folder)
    github = _github()
    with _pages(folder, github) as browser:
        for route, name, to in cases:
            reply = _reshape(browser, route, name, to)
            assert reply["published"] is False and reply["hint"], (route, name, to, reply)
    assert _held(folder) == before
    assert github.requests == []


@pytest.mark.parametrize("route", ["remove", "rename"])
@pytest.mark.parametrize("outcome", ["refused", "unknown"])
def test_a_failed_remove_or_rename_puts_back(tmp_path, monkeypatch, route, outcome):
    """INV-10: a failed Remove or Rename puts every file back byte for byte;
    an OutcomeUnknown puts nothing back.

    Breaks when the bin is not reversed, or the forwards are not."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path)
    store.write_page_forwards(folder, {"story": "about"})
    files = ("pages/about.html", "furniture/navigation.html", "forwards/pages.json")
    before = {path: (folder / path).read_bytes() for path in files}
    transport = (_refusing() if outcome == "refused" else
                 _Transport(reads=_reads(_listing([])), writes=_writes(),
                            fail_at="/git/refs"))
    with _pages(folder, transport) as browser:
        reply = _reshape(browser, route, "about", "Our Story")
    assert reply["published"] is False and reply["failure"], reply
    after = {path: (folder / path).read_bytes() if (folder / path).exists() else None
             for path in files}
    if outcome == "refused":
        assert after == before
        assert not _live(folder, "pages", "our-story").exists()
        assert reply["address"] == "/page?kind=pages&name=about"
    else:
        assert after != before


def test_renaming_a_page_and_back(tmp_path, monkeypatch):
    """INV-11: Rename writes the page byte-identical at the new name, bins the
    old, points the menu on, and leaves no loop when the page moves back. A
    page added as "Live Shows" has its link words changed too.

    Breaks when moving back leaves a -> a, or old_words holds the label alone."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path)
    about = _live(folder, "pages", "about").read_bytes()
    with _pages(folder, _github()) as browser:
        reply = _reshape(browser, "rename", "about", "Our Story")
        assert reply["published"] is True, reply
        assert reply["address"] == "/page?kind=pages&name=our-story"
        assert _live(folder, "pages", "our-story").read_bytes() == about
        assert not _live(folder, "pages", "about").exists()
        assert store.read_page_forwards(folder) == {"about": "our-story"}
        assert ('<a href="{{UP}}pages/our-story.html" data-nav="about">Our Story</a>'
                in _menu(folder))

        assert _reshape(browser, "rename", "our-story", "About")["published"] is True
        assert store.read_page_forwards(folder) == {"our-story": "about"}
        assert _live(folder, "pages", "about").read_bytes() == about

        _new(browser, "Live Shows")
        copy = _waiting(folder, "pages", "live-shows")
        _save(browser, "pages", "live-shows", "code", copy.read_text(encoding="utf-8"),
              waiting=True, base=_digest(copy), route="/page/publish")
        assert _reshape(browser, "rename", "live-shows", "Concerts")["published"] is True
    assert ('<a href="{{UP}}pages/concerts.html" data-nav="live-shows">Concerts</a>'
            in _menu(folder))
