# Starting something new from a template (PRESS-0017).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0017-templates.md
# § 5. Route names are written out rather than imported, and every server starts
# inside the test that uses it, as in tests/test_editor.py.
from __future__ import annotations

import contextlib
import hashlib
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from test_editor import _Browser, _entry, _folder

from pressless import editor, face, marks, store, templates

TEMPLATES = "templates"


@contextlib.contextmanager
def _served(folder: Path) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        templates.register(served, folder)
        yield _Browser(served)
    finally:
        served.stop()


def _template(folder: Path, name: str, **fields) -> Path:
    return store.write_template(folder, _entry(name, **fields))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _only_draft(folder: Path) -> store.Entry:
    (slug,) = store.list_slugs(folder, draft=True)
    return store.read(store.path_for(folder, slug, draft=True))


# ------------------------------------------------------------------ INV-1 ---


def test_picking_a_template_copies_its_words(tmp_path):
    folder = _folder(tmp_path)
    path = store.write_template(folder, store.Entry(
        slug="poem", title="A poem", date=datetime(2020, 1, 2), categories=("poems",),
        tags=("verse",), body="First line\nSecond line", extra=()))
    before = path.read_bytes()
    with _served(folder) as browser:
        status, _, _ = browser.request("POST", "/new", {"title": "Rain", "template": "poem"})
    assert status == 303
    draft = _only_draft(folder)
    assert (draft.title, draft.body) == ("Rain", "First line\nSecond line")
    assert (draft.categories, draft.tags) == (("poems",), ("verse",))
    assert path.read_bytes() == before


# ------------------------------------------------------------------ INV-2 ---


def test_no_template_is_a_blank_entry(tmp_path):
    folder = _folder(tmp_path)
    _template(folder, "poem", body="Not this.")
    with _served(folder) as browser:
        browser.request("POST", "/new", {"title": "Plain", "template": ""})
        browser.request("POST", "/new", {"title": "Also plain"})
    for slug in store.list_slugs(folder, draft=True):
        entry = store.read(store.path_for(folder, slug, draft=True))
        assert (entry.body, entry.categories, entry.tags, entry.extra) == ("", (), (), ())


# ------------------------------------------------------------------ INV-3 ---


def test_starters_are_written_once(tmp_path):
    absent = tmp_path / "absent"
    absent.mkdir()
    assert templates.seed(absent) is True
    assert store.list_templates(absent) == ("journal", "lyric", "photograph", "poem")

    empty = tmp_path / "empty"
    (empty / TEMPLATES).mkdir(parents=True)
    assert templates.seed(empty) is False
    assert store.list_templates(empty) == ()

    changed = tmp_path / "changed"
    changed.mkdir()
    poem = _template(changed, "poem", body="His own poem.")
    assert templates.seed(changed) is False
    assert store.list_templates(changed) == ("poem",)
    assert store.read(poem).body == "His own poem."


# ------------------------------------------------------------------ INV-4 ---


def test_every_starter_is_well_formed(tmp_path):
    assert [starter.slug for starter in templates.STARTERS] == [
        "poem", "lyric", "photograph", "journal"]
    for starter in templates.STARTERS:
        assert store.read(store.write_template(tmp_path, starter)) == starter
        rendered = marks.render(starter.body, lambda name: "/o/" + name)
        assert not re.search(r"\{[a-z#/]|\*\*", rendered), starter.slug


# ------------------------------------------------------------------ INV-5 ---


def test_a_template_save_touches_only_its_file(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("poem"), draft=True)
    path = _template(folder, "poem", body="Old.")
    entries = (store.list_slugs(folder, draft=True), store.list_slugs(folder, draft=False))
    with _served(folder) as browser:
        status, _, _ = browser.request("POST", "/template/save", {
            "name": "poem", "base": _digest(path), "title": "A poem",
            "categories": "Poems, Bad/Name", "tags": "", "body": "New\r\nlines"})
    assert status == 200
    saved = store.read(path)
    assert saved.body == "New\nlines"
    assert saved.categories == ("poems", "bad-name")  # editor.save's rule
    assert (store.list_slugs(folder, draft=True), store.list_slugs(folder, draft=False)) == entries
    assert store.read(store.path_for(folder, "poem", draft=True)).body == "Words."


def test_a_stale_template_save_writes_nothing(tmp_path):
    folder = _folder(tmp_path)
    path = _template(folder, "poem", body="Old.")
    before = path.read_bytes()
    with _served(folder) as browser:
        status, _, _ = browser.request("POST", "/template/save", {
            "name": "poem", "base": "stale", "title": "", "categories": "", "tags": "",
            "body": "New."})
    assert status == 409
    assert path.read_bytes() == before


def test_a_template_bin_touches_only_its_file(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("poem"), draft=True)
    path = _template(folder, "poem")
    with _served(folder) as browser:
        status, headers, _ = browser.request("POST", "/template/bin", {
            "name": "poem", "base": _digest(path)})
    assert (status, headers.get("Location")) == (303, "/")
    assert store.list_templates(folder) == ()
    assert [p.name for p in (folder / "bin").rglob("*.txt")] == ["poem.txt"]
    assert store.list_slugs(folder, draft=True) == ("poem",)


def test_a_stale_template_bin_moves_nothing(tmp_path):
    folder = _folder(tmp_path)
    _template(folder, "poem")
    with _served(folder) as browser:
        status, _, _ = browser.request("POST", "/template/bin", {"name": "poem", "base": "x"})
    assert status == 409
    assert store.list_templates(folder) == ("poem",)


# ------------------------------------------------------------------ INV-6 ---


def test_a_new_template_takes_a_free_name(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("song"), draft=False)
    with _served(folder) as browser:
        first = browser.request("POST", "/template/new", {"name": "Song"})
        second = browser.request("POST", "/template/new", {"name": "Song"})
    assert first[1].get("Location") == "/template?name=song"
    assert second[1].get("Location") == "/template?name=song-2"
    # The four starters are there too: this folder had no templates folder.
    assert {"song", "song-2"} <= set(store.list_templates(folder))
    assert store.read(store.template_path_for(folder, "song")).title == "Song"


# ------------------------------------------------------------- the pages ---


def test_the_list_offers_each_template_by_its_title(tmp_path):
    folder = _folder(tmp_path)
    _template(folder, "poem", title="A poem")
    _template(folder, "blank-title")
    with _served(folder) as browser:
        status, _, page = browser.request("GET", "/")
    assert status == 200
    assert '<option value="">' in page
    assert '<option value="poem">A poem</option>' in page
    assert '<option value="blank-title">blank-title</option>' in page
    assert 'href="/template?name=poem"' in page


def test_a_template_page_carries_the_box_and_the_cheat_sheet(tmp_path):
    folder = _folder(tmp_path)
    _template(folder, "poem", body="A line.")
    with _served(folder) as browser:
        status, _, page = browser.request("GET", "/template?name=poem")
    assert status == 200
    assert "A line.</textarea>" in page
    assert 'id="cheat-sheet"' in page
