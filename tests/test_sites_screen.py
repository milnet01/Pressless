# The Sites screen (PRESS-0223 § 4.6): opening another site, and refusing a
# site that is not there.
from __future__ import annotations

import json
from pathlib import Path

from _face_session import Browser
from test_publishing import _entry

from pressless import editor, face, sites, sites_screen, store

OPEN = "sites.json"


def _own(tmp_path: Path) -> Path:
    own = tmp_path / "own"
    for name in ("site-1", "site-2"):
        (own / "sites" / name).mkdir(parents=True)
    sites.choose(own, "site-1")
    return own


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
    assert restarts == [1]
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
    assert (own / "sites" / "site-3").is_dir() and restarts == [1]
