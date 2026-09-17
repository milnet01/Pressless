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
import hashlib
import html
import http.client
import json
import re
import urllib.parse
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from pressless import editor, face, settings, store

PREVIEW = "preview"
REPLACES = "Replaces"

HEADER = "<header>{{NAVIGATION}}</header>\n"
NAVIGATION = '<nav><a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a></nav>'
FOOTER = "<footer>{{YEAR}}</footer>\n"


class _Browser:
    """Talks to a served Face with the cookie and Origin under the test's control."""

    def __init__(self, served: face.Face) -> None:
        parts = urllib.parse.urlsplit(served.url)
        assert parts.port is not None
        self.port = parts.port
        secret = urllib.parse.parse_qs(parts.query)["t"][0]
        self.host = f"127.0.0.1:{self.port}"
        self.origin = f"http://{self.host}"
        self.cookie = f"pressless-{self.port}={secret}"

    def request(self, method: str, path: str, form: dict[str, str] | None = None, *,
                cookie: bool = True, origin: str | None = "own"
                ) -> tuple[int, dict[str, str], str]:
        body = urllib.parse.urlencode(form or {}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", self.host)
            if cookie:
                conn.putheader("Cookie", self.cookie)
            if method == "POST":
                if origin:
                    conn.putheader("Origin", self.origin if origin == "own" else origin)
                conn.putheader("Content-Type", "application/x-www-form-urlencoded")
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body if method == "POST" else None)
            response = conn.getresponse()
            return (response.status, dict(response.getheaders()),
                    response.read().decode("utf-8", "replace"))
        finally:
            conn.close()

    def save(self, slug: str, draft: bool, base: str, *, title: str = "A title",
             categories: str = "", tags: str = "", body: str = "Words."
             ) -> tuple[int, dict[str, str], str]:
        return self.request("POST", "/save", {
            "slug": slug, "draft": "1" if draft else "0", "base": base, "title": title,
            "categories": categories, "tags": tags, "body": body})


@contextlib.contextmanager
def _editor(folder: Path) -> Iterator[_Browser]:
    served = face.serve(folder, open_browser=False)
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
            site_name="A Journal", site_address="https://example.org",
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
