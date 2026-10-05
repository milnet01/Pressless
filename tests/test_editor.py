# The editor: the list, the box, and the real page beside it (PRESS-0012).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0012-editor.md
# § 5. Names the routes and files must carry are written out here rather than
# imported from editor.py: shared, they would compare the module against itself
# (the trap CLAUDE.md records for test_settings.py).
#
# Every server is started inside the test that uses it, never in a fixture, so
# a red run against a stub fails in the test body for the stub's reason.
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import html
import json
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from _face_session import Browser
from test_setup import _saved

from pressless import editor, face, marks, page_editor, settings, setup, starter, store

PREVIEW = "preview"
REPLACES = "Replaces"

HEADER = "<header>{{NAVIGATION}}</header>\n"
NAVIGATION = '<nav><a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a></nav>'
FOOTER = "<footer>{{YEAR}}</footer>\n"


class _Browser(Browser):
    def save(self, slug: str, draft: bool, base: str, *, title: str = "A title",
             categories: str = "", tags: str = "", body: str = "Words."
             ) -> tuple[int, dict[str, str], str]:
        return self.request("POST", "/save", {
            "slug": slug, "draft": "1" if draft else "0", "base": base, "title": title,
            "categories": categories, "tags": tags, "body": body})


@contextlib.contextmanager
def _editor(folder: Path) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        yield _Browser(served)
    finally:
        served.stop()


def _folder(tmp_path: Path, *, set_up: bool = True) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    for name, text in (("header", HEADER), ("navigation", NAVIGATION), ("footer", FOOTER)):
        store.write_html(folder, store.FURNITURE_FOLDER, name, text)
    if set_up:
        settings.save(folder, settings.Settings(
            site_folder=folder / "site", repository="owner/owner.github.io",
            site_address="https://example.org",
            daily_prompt_filter="", untouchable=("CNAME",),
            credentials=settings.Credentials(store="keyring", github_account="github",
                                             google_account=None),
            analytics_property_id=None))
    return folder


def _entry(slug: str, *, body: str = "Words.", title: str = "", date: str = "2020-01-02",
           extra: tuple[tuple[str, str], ...] = ()) -> store.Entry:
    return store.Entry(slug=slug, title=title, date=datetime.fromisoformat(date),
                       categories=(), tags=(), body=body, extra=extra)


def _base(folder: Path, slug: str, *, draft: bool) -> str:
    return hashlib.sha256(store.path_for(folder, slug, draft=draft).read_bytes()).hexdigest()


def _copies(folder: Path, slug: str) -> list[str]:
    found = []
    for draft in store.list_slugs(folder, draft=True):
        entry = store.read(store.path_for(folder, draft, draft=True))
        if (REPLACES, slug) in entry.extra:
            found.append(draft)
    return found


def _binned(folder: Path) -> list[str]:
    bin_folder = folder / "bin"
    if not bin_folder.exists():
        return []
    return sorted(p.name for p in bin_folder.rglob("*") if p.is_file())


def _said(kind: type[Exception]) -> str:
    return html.escape(face.sentence_for(kind("x"), publishing=False).what)


# ------------------------------------------------------------------ INV-1 ---


def test_a_published_entry_is_untouched_by_its_edits(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    published = store.path_for(folder, "seaside", draft=False).read_bytes()
    with _editor(folder) as browser:
        assert browser.request("GET", "/edit?slug=seaside")[0] == 200
        status, _, text = browser.save("seaside", False, _base(folder, "seaside", draft=False),
                                       body="Changed once.")
        assert status == 200, text
        reply = json.loads(text)
        assert reply["draft"] is True and reply["slug"] != "seaside"
        status, _, text = browser.save(reply["slug"], True, reply["base"], body="Twice.")
        assert status == 200, text
        assert json.loads(text)["slug"] == reply["slug"]

        assert store.path_for(folder, "seaside", draft=False).read_bytes() == published
        assert _copies(folder, "seaside") == [reply["slug"]]
        assert editor.working_copy(folder, "seaside") == reply["slug"]
        status, headers, _ = browser.request("GET", "/edit?slug=seaside")
        assert status == 303
        assert headers["Location"] == f"/edit?slug={reply['slug']}"


# ------------------------------------------------------------------ INV-2 ---


def test_a_save_from_a_stale_window_writes_nothing(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("draft"), draft=True)
    store.write(folder, _entry("seaside"), draft=False)
    store.write(folder, _entry("harbour"), draft=False)
    with _editor(folder) as browser:
        base = _base(folder, "draft", draft=True)
        assert browser.save("draft", True, base, body="First.")[0] == 200
        status, _, text = browser.save("draft", True, base, body="Second.")
        assert status == 409 and _said(editor.ChangedElsewhere) in text
        assert store.read(store.path_for(folder, "draft", draft=True)).body == "First."

        base = _base(folder, "seaside", draft=False)
        assert browser.save("seaside", False, base)[0] == 200
        assert browser.save("seaside", False, base)[0] == 409
        assert len(_copies(folder, "seaside")) == 1

        base = _base(folder, "harbour", draft=False)
        store.write(folder, _entry("harbour", body="Edited by hand."), draft=False)
        assert browser.save("harbour", False, base)[0] == 409
        assert _copies(folder, "harbour") == []


# ------------------------------------------------------------------ INV-3 ---


def test_a_working_copy_replaces_a_published_entry(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    store.write(folder, _entry("unfinished"), draft=True)
    store.write(folder, _entry("notes", extra=((REPLACES, "unfinished"),)), draft=True)
    assert editor.working_copy(folder, "unfinished") is None

    store.write(folder, _entry("seaside-changes", extra=((REPLACES, "seaside"),)), draft=True)
    assert editor.working_copy(folder, "seaside") == "seaside-changes"

    store.write(folder, _entry("seaside-again", extra=((REPLACES, "seaside"),)), draft=True)
    with pytest.raises(editor.TooManyCopies):
        editor.working_copy(folder, "seaside")


# ------------------------------------------------------------------ INV-6 ---


def test_a_save_never_touches_the_site_folder(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("draft"), draft=True)
    store.write(folder, _entry("seaside"), draft=False)
    with _editor(folder) as browser:
        assert browser.save("draft", True, _base(folder, "draft", draft=True))[0] == 200
        assert browser.save("seaside", False, _base(folder, "seaside", draft=False))[0] == 200
    assert not (folder / "site").exists()
    assert list((folder / PREVIEW).rglob("index.html"))


# ----------------------------------------------------------------- INV-10 ---


def test_a_new_entry_gets_a_free_address(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("taken"), draft=False)
    with _editor(folder) as browser:
        made = []
        for title in ("Late light — on the water", "", "", "con", "Taken", "a" * 70):
            status, headers, _ = browser.request("POST", "/new", {"title": title})
            assert status == 303, title
            made.append(headers["Location"])
    assert made == ["/edit?slug=late-light-on-the-water", "/edit?slug=untitled",
                    "/edit?slug=untitled-2", "/edit?slug=con-2", "/edit?slug=taken-2",
                    f"/edit?slug={'a' * 60}"]
    assert store.read(store.path_for(folder, "con-2", draft=True)).title == "con"


# ----------------------------------------------------------------- INV-11 ---


def test_a_save_keeps_his_lines(tmp_path):
    folder = _folder(tmp_path)
    kept = "\n  first\n second\n\nthird  \n"
    store.write(folder, _entry("poem", body=kept), draft=True)
    with _editor(folder) as browser:
        page = browser.request("GET", "/edit?slug=poem")[2]
        found = re.search(r"<textarea[^>]*>(.*?)</textarea>", page, re.S)
        assert found is not None
        content = found.group(1)
        # An HTML parser drops one line break straight after <textarea>.
        assert content.startswith("\n")
        as_typed = html.unescape(content[1:])
        posted = as_typed.replace("first\n", "first\r\n").replace("second\n\n", "second\r\r")
        status, _, text = browser.save("poem", True, _base(folder, "poem", draft=True),
                                       body=posted)
        assert status == 200, text
    assert store.read(store.path_for(folder, "poem", draft=True)).body == kept


# ----------------------------------------------------------------- INV-12 ---


def test_a_save_keeps_the_date_and_extra_fields(tmp_path):
    folder = _folder(tmp_path)
    mood = (("Mood", "blue"),)
    store.write(folder, _entry("draft", date="2014-11-09 21:32:00", extra=mood), draft=True)
    store.write(folder, _entry("seaside", date="2014-11-09 21:32:00", extra=mood), draft=False)
    with _editor(folder) as browser:
        assert browser.save("draft", True, _base(folder, "draft", draft=True))[0] == 200
        status, _, text = browser.save("seaside", False, _base(folder, "seaside", draft=False))
        assert status == 200, text
        copy = json.loads(text)["slug"]
    for slug, extra in (("draft", mood), (copy, (*mood, (REPLACES, "seaside")))):
        entry = store.read(store.path_for(folder, slug, draft=True))
        assert entry.date == datetime(2014, 11, 9, 21, 32)
        assert entry.extra == extra


# ----------------------------------------------------------------- INV-13 ---


def test_a_preview_failure_keeps_the_save(tmp_path):
    folder = _folder(tmp_path, set_up=False)
    store.write(folder, _entry("draft"), draft=True)
    with _editor(folder) as browser:
        status, _, text = browser.save("draft", True, _base(folder, "draft", draft=True),
                                       body="Kept anyway.")
    assert status == 200, text
    reply = json.loads(text)
    assert reply["preview"] is None
    assert _said(settings.NotSetUp) in reply["failure"]
    assert store.read(store.path_for(folder, "draft", draft=True)).body == "Kept anyway."


# ----------------------------------------------------------------- INV-14 ---


def test_a_draft_changes_address(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    store.write(folder, _entry("old"), draft=True)
    store.write_comments(folder, "old", (store.Comment(
        identifier="1", author="A reader", author_url="", date=datetime(2020, 1, 3),
        body="Lovely.", parent=""),))
    store.write(folder, _entry("taken"), draft=False)
    store.write(folder, _entry("copy", extra=((REPLACES, "taken"),)), draft=True)
    with _editor(folder) as browser:
        status, _, text = browser.request("POST", "/address", {
            "slug": "old", "base": _base(folder, "old", draft=True), "address": " new "})
        assert status == 200, text
        assert json.loads(text)["slug"] == "new" and json.loads(text)["hint"] is None
        assert store.path_for(folder, "new", draft=True).is_file()
        assert not store.path_for(folder, "old", draft=True).exists()
        assert store.comments_path_for(folder, "new").is_file()
        assert not store.comments_path_for(folder, "old").exists()
        assert _binned(folder) == ["old.json", "old.txt"]

        before = sorted(p.as_posix() for p in folder.rglob("*"))
        for slug, address in (("new", "taken"), ("new", "con"), ("copy", "elsewhere"),
                              ("taken", "elsewhere")):
            draft = slug != "taken"
            status, _, text = browser.request("POST", "/address", {
                "slug": slug, "base": _base(folder, slug, draft=draft), "address": address})
            assert status == 200, (slug, address, text)
            assert json.loads(text)["hint"], (slug, address)
        assert sorted(p.as_posix() for p in folder.rglob("*")) == before

        def refuse(*args, **kwargs):
            raise store.StoreError("the disk is full")

        monkeypatch.setattr(store, "write", refuse)
        status, _, _ = browser.request("POST", "/address", {
            "slug": "new", "base": _base(folder, "new", draft=True), "address": "newer"})
        assert status == 409
        assert store.path_for(folder, "new", draft=True).is_file()
        assert _binned(folder) == ["old.json", "old.txt"]


# ----------------------------------------------------------------- INV-15 ---


def test_throwing_away_changes_bins_the_copy(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    published = store.path_for(folder, "seaside", draft=False).read_bytes()
    store.write(folder, _entry("seaside-changes", extra=((REPLACES, "seaside"),)), draft=True)
    store.write(folder, _entry("plain"), draft=True)
    with _editor(folder) as browser:
        status, headers, _ = browser.request("POST", "/discard", {
            "slug": "seaside-changes",
            "base": _base(folder, "seaside-changes", draft=True)})
        assert status == 303 and headers["Location"] == "/edit?slug=seaside"
        status, _, text = browser.request("POST", "/discard", {
            "slug": "plain", "base": _base(folder, "plain", draft=True)})
        assert status == 409 and _said(editor.ChangedElsewhere) in text
    assert store.list_slugs(folder, draft=True) == ("plain",)
    assert _binned(folder) == ["seaside-changes.txt"]
    assert store.path_for(folder, "seaside", draft=False).read_bytes() == published


# -------------------------------------------------------------- PRESS-0128 ---


def _comments(folder: Path, slug: str) -> None:
    store.write_comments(folder, slug, (store.Comment(
        identifier="1", author="A reader", author_url="", date=datetime(2020, 1, 3),
        body="Lovely.", parent=""),))


def test_throwing_an_entry_away_bins_it_with_its_comments(tmp_path):
    """PRESS-0128: the entry the window shows goes to the bin -- a draft, a
    published entry, or a published entry seen through its working copy, which
    takes the copy with it. Its comments file follows it (docs/design.md)."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("plain"), draft=True)
    _comments(folder, "plain")
    store.write(folder, _entry("seaside"), draft=False)
    _comments(folder, "seaside")
    store.write(folder, _entry("seaside-changes", extra=((REPLACES, "seaside"),)), draft=True)
    store.write(folder, _entry("harbour"), draft=False)
    store.write(folder, _entry("kept"), draft=False)
    with _editor(folder) as browser:
        for slug, draft in (("plain", True), ("seaside-changes", True), ("harbour", False)):
            status, _, text = browser.request("POST", "/throw", {
                "slug": slug, "draft": "1" if draft else "0",
                "base": _base(folder, slug, draft=draft)})
            assert status == 200, (slug, text)
            assert json.loads(text)["thrown"] is True, slug
    assert store.list_slugs(folder, draft=True) == ()
    assert store.list_slugs(folder, draft=False) == ("kept",)
    assert not store.comments_path_for(folder, "plain").exists()
    assert not store.comments_path_for(folder, "seaside").exists()
    assert _binned(folder) == ["harbour.txt", "plain.json", "plain.txt", "seaside-changes.txt",
                               "seaside.json", "seaside.txt"]


def test_throwing_away_a_stale_window_moves_nothing(tmp_path):
    """PRESS-0128: a window that has not seen the file, or shows a published
    entry that has since gained a working copy, throws nothing away."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("plain"), draft=True)
    store.write(folder, _entry("seaside"), draft=False)
    stale = _base(folder, "seaside", draft=False)
    store.write(folder, _entry("seaside-changes", extra=((REPLACES, "seaside"),)), draft=True)
    with _editor(folder) as browser:
        for form in ({"slug": "plain", "draft": "1", "base": "0" * 64},
                     {"slug": "seaside", "draft": "0", "base": stale},
                     {"slug": "gone", "draft": "1", "base": "0" * 64}):
            status, _, text = browser.request("POST", "/throw", form)
            assert status == 409 and _said(editor.ChangedElsewhere) in text, form
    assert _binned(folder) == []
    assert store.list_slugs(folder, draft=True) == ("plain", "seaside-changes")
    assert store.list_slugs(folder, draft=False) == ("seaside",)


def test_the_editor_offers_to_throw_the_entry_away(tmp_path):
    """PRESS-0128: every editor page carries the button, and says whether the
    entry is on his site, which decides what he is told before it goes."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("plain"), draft=True)
    store.write(folder, _entry("seaside"), draft=False)
    store.write(folder, _entry("harbour"), draft=False)
    store.write(folder, _entry("harbour-changes", extra=((REPLACES, "harbour"),)), draft=True)
    with _editor(folder) as browser:
        for slug, on_site in (("plain", "0"), ("seaside", "1"), ("harbour-changes", "1")):
            status, _, page = browser.request("GET", f"/edit?slug={slug}")
            assert status == 200, slug
            assert 'data-editor="throw"' in page, slug
            assert f'data-on-site="{on_site}"' in page, slug


# ----------------------------------------------------------------- INV-16 ---


def test_the_list_shows_copies_and_unreadable_files(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    store.write(folder, _entry("seaside-changes", extra=((REPLACES, "seaside"),)), draft=True)
    store.write(folder, _entry("plain"), draft=True)
    store.path_for(folder, "broken", draft=True).write_bytes(b"\xff\xfe not an entry")
    with _editor(folder) as browser:
        status, _, page = browser.request("GET", "/")
    assert status == 200
    assert "/edit?slug=seaside" in page and "/edit?slug=plain" in page
    assert "/edit?slug=seaside-changes" not in page
    assert "broken" in page


def test_a_published_entry_page_carries_its_working_copy_state(tmp_path):
    """PRESS-0162 (review-code L4.3): the first save turns a published
    entry's page into a working copy's editor without a reload, and the page
    carried only the published wording -- no Bin this proof button until
    he reopened it (PRESS-0012 4.7). Both states are now in the page, the
    second hidden, and the script shows it and names the copy on a save.
    Driven in Chrome 2026-09-27: hidden before a save, shown after, naming
    `seaside-changes`, and the discard removed the copy."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    with _editor(folder) as browser:
        status, _, page = browser.request("GET", "/edit?slug=seaside")
    assert status == 200
    assert '<form data-when="1" hidden method="post" action="/discard">' in page
    assert "Bin this proof" in page
    assert "#standing input[name=slug]" in page, "the script does not name the copy"


def test_every_editor_page_carries_the_line_a_press_moves_it_to(tmp_path):
    """PRESS-0185: a press puts a draft, or a proof, on his site without
    reloading the page, and the line above the form went on saying it was
    not there. Both pages now carry the published wording, hidden until the
    script shows it. Driven in Chrome by scripts/by-hand-browser-checks.py."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("plain"), draft=True)
    store.write(folder, _entry("harbour"), draft=False)
    store.write(folder, _entry("harbour-changes", extra=((REPLACES, "harbour"),)), draft=True)
    on_site = '<p data-when="0"{}>This entry is on your site.'
    with _editor(folder) as browser:
        draft_status, _, draft = browser.request("GET", "/edit?slug=plain")
        proof_status, _, proof = browser.request("GET", "/edit?slug=harbour-changes")
    assert (draft_status, proof_status) == (200, 200)
    assert '<p id="draft-standing">A draft. It is not on your site.</p>' in draft
    assert '<div id="standing" hidden>' in draft and on_site.format("") in draft
    assert '<div id="standing">' in proof and on_site.format(" hidden") in proof
    assert '<p data-when="1">These changes are not on your site yet.</p>' in proof
    assert 'getElementById("draft-standing")' in draft, "the script keeps the draft line"
    # PRESS-0186: a proof's page holds the address of the entry it replaces,
    # hidden, for the press that makes this a published entry's page.
    field = '<span id="address"{}><label>Address <input name="address" value="{}">'
    assert field.format(" hidden", "harbour") in proof
    assert field.format("", "plain") in draft


def test_the_editor_shows_the_cheat_sheet(tmp_path):
    """PRESS-0018: the box he writes in carries the cheat sheet beside it,
    generated from Marks' table, with a link to the printable page."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    with _editor(folder) as browser:
        status, _, page = browser.request("GET", "/edit?slug=seaside")
    assert status == 200
    for row in marks.MARKS:
        assert html.escape(row.explains) in page, row.name
    assert 'href="/cheat-sheet"' in page


def test_the_editor_offers_the_previews_true_colours(tmp_path):
    """PRESS-0187: a dark look dims the preview; the switch undoes it."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    with _editor(folder) as browser:
        status, _, page = browser.request("GET", "/edit?slug=seaside")
    assert status == 200
    assert re.search(r'<input type="checkbox" data-true-colours>', page), page


def test_a_copy_of_an_unreadable_entry_is_not_listed_as_a_draft(tmp_path):
    """PRESS-0162 (review-code L4.2): `published` was built from the entries
    that READ, while working_copy and the editor ask list_slugs -- so a
    working copy of a published entry that will not read was listed as an
    ordinary draft, and the list and the editor disagreed about one file."""
    folder = _folder(tmp_path)
    store.path_for(folder, "seaside", draft=False).parent.mkdir(exist_ok=True)
    store.path_for(folder, "seaside", draft=False).write_bytes(b"\xff\xfe not an entry")
    store.write(folder, _entry("seaside-changes", extra=((REPLACES, "seaside"),)), draft=True)
    with _editor(folder) as browser:
        status, _, page = browser.request("GET", "/")
    assert status == 200
    assert "/edit?slug=seaside-changes" not in page, page


# ----------------------------------------------------------------- INV-17 ---


def test_a_preview_photograph_is_the_original(tmp_path):
    folder = _folder(tmp_path)
    original = b"\xff\xd8 the original's bytes"
    target = store.photograph_path_for(folder, "seaside dusk.jpg")
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(original)
    (target.parent / "nested").mkdir()
    (target.parent / "nested" / "inner.jpg").write_bytes(b"nested bytes")
    store.write(folder, _entry("seaside", body="{photo: seaside dusk.jpg}"), draft=False)
    with _editor(folder) as browser:
        assert browser.request("GET", "/edit?slug=seaside")[0] == 200
        pages = list((folder / PREVIEW).rglob("index.html"))
        assert len(pages) == 1
        assert "/originals/seaside%20dusk.jpg" in pages[0].read_text(encoding="utf-8")
        status, _, body = browser.request("GET", "/originals/seaside%20dusk.jpg")
        assert status == 200 and body.encode("utf-8", "replace")[-20:] == original[-20:]
        assert browser.request("GET", "/originals/nested%2finner.jpg")[0] == 404


# ----------------------------------------------------------------- INV-18 ---


def test_the_editor_sits_behind_the_faces_boundary(tmp_path):
    folder = _folder(tmp_path)
    store.write(folder, _entry("draft"), draft=True)
    (folder / PREVIEW).mkdir()
    (folder / PREVIEW / "page.html").write_text("<p>page</p>", encoding="utf-8")
    form = {"slug": "draft", "draft": "1", "base": _base(folder, "draft", draft=True),
            "title": "", "categories": "", "tags": "", "body": "Saved at last."}
    with _editor(folder) as browser:
        assert browser.request("GET", "/", cookie=False)[0] == 403
        assert browser.request("GET", "/preview/page.html", cookie=False)[0] == 403
        assert browser.request("POST", "/save", form, cookie=False)[0] == 403
        assert browser.request("POST", "/save", form, origin="http://127.0.0.1:1")[0] == 403
        assert store.read(store.path_for(folder, "draft", draft=True)).body == "Words."
        assert browser.request("POST", "/save", form)[0] == 200
    assert store.read(store.path_for(folder, "draft", draft=True)).body == "Saved at last."


# ----------------------------------------------------------------- INV-19 ---


def test_a_save_turns_names_into_addresses(tmp_path):
    """§ 4.8 step 3: a typed category or tag is stored as an address, and a part
    that leaves nothing usable is left out with a notice naming it (PRESS-0148)."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("draft"), draft=True)
    with _editor(folder) as browser:
        status, _, text = browser.save("draft", True, _base(folder, "draft", draft=True),
                                       categories="Poems, Short Stories, poems, !!!, Con, a--b",
                                       tags="Live Shows")
    assert status == 200, text
    reply = json.loads(text)
    saved = store.read(store.path_for(folder, "draft", draft=True))
    assert saved.categories == ("poems", "short-stories", "a--b")
    assert saved.tags == ("live-shows",)
    notices = html.unescape(reply["notices"])
    assert "!!!" in notices and "Con" in notices, notices
    assert reply["failure"] is None and reply["preview"], reply


# ----------------------------------------------------------------- INV-20 ---


def test_the_preview_frame_runs_no_script(tmp_path):
    """§ 4.7 (PRESS-0169): the frame is same-origin with the Face, so a script
    in it could send a publish or an undo with his cookie. Scripts go, not
    same-origin: without it the frame's stylesheet and photograph requests
    carry no SameSite=Strict cookie and the Face refuses them.
    """
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    with _editor(folder) as browser:
        page = browser.request("GET", "/edit?slug=seaside")[2]
    frames = re.findall(r"<iframe\b[^>]*>", page)
    assert len(frames) == 1, frames
    assert re.search(r'\bsandbox="allow-same-origin"', frames[0]), frames[0]


# -------------------------------------------------------------- PRESS-0182 ---
# docs/specs/PRESS-0182-published-address.md: a published entry changes its
# address and the old one forwards to it.


def _move(browser: _Browser, folder: Path, slug: str, address: str, *, draft: bool
          ) -> dict:
    status, _, text = browser.request("POST", "/address", {
        "slug": slug, "draft": "1" if draft else "0",
        "base": _base(folder, slug, draft=draft), "address": address})
    assert status == 200, text
    return json.loads(text)


def test_a_published_address_change_forwards_the_old_one(tmp_path):
    """INV-2: the entry moves within published/, its old file and comments go
    to the bin, the comments follow it, and the old address forwards.

    Breaks when step 4 is skipped, or the entry is written as a draft."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("a", title="Seaside", body="The sea."), draft=False)
    _comments(folder, "a")
    before = store.read(store.path_for(folder, "a", draft=False))
    comments = store.read_comments(store.comments_path_for(folder, "a"))
    with _editor(folder) as browser:
        reply = _move(browser, folder, "a", "b", draft=False)
    assert reply["slug"] == "b" and reply["draft"] is False and reply["hint"] is None
    assert reply["base"] == _base(folder, "b", draft=False)
    assert store.list_slugs(folder, draft=False) == ("b",)
    assert store.list_slugs(folder, draft=True) == ()
    moved = store.read(store.path_for(folder, "b", draft=False))
    assert moved == dataclasses.replace(before, slug="b")
    assert store.read_comments(store.comments_path_for(folder, "b")) == comments
    assert not store.comments_path_for(folder, "a").exists()
    assert _binned(folder) == ["a.json", "a.txt"]
    assert store.read_forwards(folder) == {"a": "b"}


def test_a_second_move_retargets_the_first_forward(tmp_path):
    """INV-3: a chain points at the newest address, and a draft an undo
    demoted takes its forwards with it.

    Breaks when step 4 adds the new pair without retargeting, or skips
    drafts, leaving `a` aimed at a free `b`."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("a"), draft=False)
    with _editor(folder) as browser:
        _move(browser, folder, "a", "b", draft=False)
        _move(browser, folder, "b", "c", draft=False)
    assert store.read_forwards(folder) == {"a": "c", "b": "c"}

    (tmp_path / "demoted").mkdir()
    demoted = _folder(tmp_path / "demoted")
    store.write(demoted, _entry("b"), draft=True)
    store.write_forwards(demoted, {"a": "b"})
    with _editor(demoted) as browser:
        _move(browser, demoted, "b", "c", draft=True)
    assert store.read_forwards(demoted) == {"a": "c"}


def test_moving_back_drops_the_forward_it_lands_on(tmp_path):
    """INV-4: a to b and back to a leaves {b: a} and no loop.

    Breaks when step 4 keeps the key equal to the new address."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("a"), draft=False)
    with _editor(folder) as browser:
        _move(browser, folder, "a", "b", draft=False)
        reply = _move(browser, folder, "b", "a", draft=False)
    assert reply["hint"] is None and reply["slug"] == "a"
    assert store.read_forwards(folder) == {"b": "a"}


def test_a_forwarded_address_stays_reserved(tmp_path):
    """INV-5: a forwarded address is refused to every entry but the one it
    forwards to. With no entry at `a`, only the forward can make free_address
    skip it.

    Breaks when free_address or /address consults store.exists alone."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("b"), draft=False)
    store.write(folder, _entry("c"), draft=True)
    store.write_forwards(folder, {"a": "b"})
    assert editor.free_address(folder, "a") == "a-2"
    with _editor(folder) as browser:
        before = sorted(p.as_posix() for p in folder.rglob("*"))
        reply = _move(browser, folder, "c", "a", draft=True)
        assert reply["hint"] == "Another entry's old address forwards from there."
        assert sorted(p.as_posix() for p in folder.rglob("*")) == before
        reply = _move(browser, folder, "b", "a", draft=False)
    assert reply["hint"] is None
    assert store.list_slugs(folder, draft=False) == ("a",)
    assert store.read_forwards(folder) == {"b": "a"}


def test_an_address_change_waits_for_the_proof(tmp_path):
    """INV-6: a published entry with a working copy, and the working copy
    itself, are refused with their hints and nothing is written.

    Breaks when the published entry is moved and its copy's Replaces then
    names nothing."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    store.write(folder, _entry("seaside-changes", extra=((REPLACES, "seaside"),)), draft=True)
    with _editor(folder) as browser:
        before = sorted(p.as_posix() for p in folder.rglob("*"))
        published = _move(browser, folder, "seaside", "harbour", draft=False)
        proof = _move(browser, folder, "seaside-changes", "harbour", draft=True)
        assert sorted(p.as_posix() for p in folder.rglob("*")) == before
    assert published["hint"] == ("Press your changes to your site, or bin this proof, "
                                 "then change the address.")
    assert proof["hint"] == "A proof's address cannot be changed."


def test_throwing_an_entry_away_removes_its_forwards(tmp_path):
    """INV-7: throwing away a published entry removes every pair aimed at it,
    from its own page and from its working copy's.

    Breaks when the step keys on the draft field, so a throw from the proof's
    page bins the entry and leaves its old address reserved."""
    for route in ("own page", "proof"):
        (tmp_path / route.replace(" ", "-")).mkdir()
        folder = _folder(tmp_path / route.replace(" ", "-"))
        store.write(folder, _entry("b"), draft=False)
        store.write(folder, _entry("y"), draft=False)
        store.write_forwards(folder, {"a": "b", "x": "y"})
        slug, draft = "b", False
        if route == "proof":
            store.write(folder, _entry("b-changes", extra=((REPLACES, "b"),)), draft=True)
            slug, draft = "b-changes", True
        with _editor(folder) as browser:
            status, _, text = browser.request("POST", "/throw", {
                "slug": slug, "draft": "1" if draft else "0",
                "base": _base(folder, slug, draft=draft)})
        assert status == 200, (route, text)
        assert store.read_forwards(folder) == {"x": "y"}, route


# PRESS-0214 INV-8 (docs/specs/PRESS-0214-journal-switch.md § 4.5).


def test_the_journal_button_switches_it(tmp_path):
    """INV-8. Breaks when the post sets a fixed value rather than the opposite."""
    folder = _folder(tmp_path)
    options = folder / "options" / "options.json"
    with _editor(folder) as browser:
        status, headers, _ = browser.request("POST", "/journal")
        assert status == 303 and headers.get("Location") == "/"
        assert json.loads(options.read_text(encoding="utf-8")) == {"journal": False}
        browser.request("POST", "/journal")
        assert json.loads(options.read_text(encoding="utf-8")) == {"journal": True}
        status, _, page = browser.request("GET", "/")
    assert status == 200 and 'action="/journal"' in page


# PRESS-0126 INV-15 (docs/specs/PRESS-0126-starter-site.md § 4.6).


def test_the_style_code_is_served_before_any_preview(tmp_path):
    """INV-15. Breaks when /preview/look/ is answered from the preview
    folder, so a screen is unstyled until a preview is built."""
    folder = _folder(tmp_path)
    store.write_style_code(folder, "body { color: black; }\n")
    assert not (folder / "preview").exists()
    with _editor(folder) as browser:
        status, _, css = browser.request("GET", "/preview/look/style.css")
    assert status == 200 and css == "body { color: black; }\n"


def test_view_your_site_sits_by_press_to_site_in_both_editors(tmp_path):
    """PRESS-0234. Breaks when either editor loses the button beside Press to
    site, puts a status between its buttons, or a publish in the page leaves
    the button greyed out."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    store.write_html(folder, store.PAGES_FOLDER, "index",
                     "<html><body>\n<p>Home words.</p>\n</body></html>\n")
    beside = ('Press to site</button>\n <button type="button" '
              'data-view-site="https://example.org">View your site</button>')
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        page_editor.register(served, folder)
        setup.register(served, folder)
        browser = _Browser(served)
        for path in ("/edit?slug=seaside", "/page?kind=pages&name=index"):
            status, _, page = browser.request("GET", path)
            assert status == 200 and beside in page, path
            # One status line of its own, below the row (no status between buttons).
            assert ('Undo the last press</button></p>\n<p id="publish-status" '
                    'class="press-status" role="status">On your site</p>') in page, path
        # A starter site never published has nothing to see yet.
        (folder / starter.MARKER).write_bytes(b"")
        for path in ("/edit?slug=seaside", "/page?kind=pages&name=index"):
            page = browser.request("GET", path)[2]
            assert beside.replace(">View", " disabled>View") in page, path
        assert "Not on your site yet</p>" in page
    finally:
        served.stop()
    for name, script in (("entry", editor._EDITOR_SCRIPT), ("page", page_editor._PAGE_SCRIPT)):
        after = script.split('"Published. Your site shows it within a few minutes."', 1)[1]
        added = after.split("} catch", 1)[0]
        assert 'document.querySelector("button[data-view-site]")' in added, name
        assert "view.disabled = false" in added, name


def test_the_list_names_the_site_it_edits(tmp_path):
    """The list says which site it is for: the Store's name, Settings'
    address. Nothing where the address cannot be read yet."""
    assert editor._site_line(tmp_path) == ""
    _saved(tmp_path)
    store.write_identity(tmp_path, store.Identity("Field Notes"))
    line = editor._site_line(tmp_path)
    assert "<b>Field Notes</b>" in line
    assert 'href="https://example.org"' in line and ">example.org</a>" in line
