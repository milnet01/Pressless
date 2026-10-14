# Editing a fixed page: on the page itself, or its code (PRESS-0014, PRESS-0260).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0014-fixed-pages.md § 5, or from
# docs/specs/PRESS-0260-visual-editor.md § 5 under its own heading. The folder names, the notice and
# the field names are written out here rather than imported from the modules:
# shared, they would compare a module against itself (the trap CLAUDE.md
# records for test_settings.py).
#
# Every server is started inside the test that uses it, never in a fixture, so
# a red run against a stub fails in the test body for the stub's reason.
from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from test_editor import _Browser
from test_publisher import _listing, _reads, _Transport, _writes

from pressless import (
    blocks,
    builder,
    credentials,
    editor,
    face,
    menu,
    page_editor,
    settings,
    starter,
    store,
    words,
)

PAGES_WAITING = "pages-waiting"
FURNITURE_WAITING = "furniture-waiting"
KEY = "ghp_SENTINELpageEDITORkey0123456789"
UNKNOWN_WORDS = "Pressless cannot tell whether your site changed."
STRAY = ("The text you put between the header or footer markers will be replaced "
         "from the one Header or Footer when your site is built. Edit the Header or "
         "Footer instead.")

HEADER = "<header>{{NAVIGATION}}</header>\n"
NAVIGATION = '<nav><a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a></nav>'
FOOTER = "<footer>{{YEAR}}</footer>\n"

# CRLF endings, a named and a numbered character reference in text, an
# attribute holding the very word that is also a piece, a comment, and
# indentation that is nobody's house style: each is something a parser, a
# re-serialiser or a replace-by-value would change.
ABOUT = (
    "<!doctype html>\r\n"
    "<html><body>\r\n"
    "<!-- HEADER:START -->\r\n"
    "<!-- HEADER:END -->\r\n"
    '   <h1 title="Hello">Hello</h1>\r\n'
    "<!-- a comment holding words -->\r\n"
    "      <p>Tea &amp; toast, it&#8217;s late.</p>\r\n"
    "  <p>Second one.</p>\r\n"
    "<!-- FOOTER:START -->\r\n"
    "<!-- FOOTER:END -->\r\n"
    "</body></html>\r\n"
)
# What the code view posts: the browser sends a textarea's lines with "\n".
ABOUT_CODE = ABOUT.replace("\r\n", "\n")
# A page Pressless never marked, with a main to take into sections.
UNMARKED = ("<html><body>\n<!-- HEADER:START -->\n<!-- HEADER:END -->\n<main>\n"
            "  <h1>Hi</h1>\n  <p>One &amp; two</p>\n  <div>loose</div>\n</main>\n"
            "<!-- FOOTER:START -->\n<!-- FOOTER:END -->\n</body></html>\n")
INDEX = ("<html><body>\n<!-- HEADER:START nonav -->\n<!-- HEADER:END -->\n"
         "<p>Home words.</p>\n</body></html>\n")


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir(parents=True)
    for name, text in (("header", HEADER), ("navigation", NAVIGATION), ("footer", FOOTER)):
        store.write_html(folder, store.FURNITURE_FOLDER, name, text)
    store.write_html(folder, store.PAGES_FOLDER, "about", ABOUT)
    store.write_html(folder, store.PAGES_FOLDER, "index", INDEX)
    store.write(folder, store.Entry(
        slug="seaside", title="Seaside", date=datetime(2020, 1, 2, 3, 4, 5),
        categories=(), tags=(), body="Words.", extra=()), draft=False)
    settings.save(folder, settings.Settings(
        site_folder=folder / "site", repository="owner/owner.github.io",
        site_address="https://example.org",
        daily_prompt_filter="", untouchable=("CNAME",),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))
    return folder


@contextlib.contextmanager
def _pages(folder: Path, transport: _Transport | None = None) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        page_editor.register(served, folder, transport=transport)
        yield _Browser(served)
    finally:
        served.stop()


def _live(folder: Path, kind: str, name: str) -> Path:
    return folder / kind / f"{name}.html"


def _waiting(folder: Path, kind: str, name: str) -> Path:
    return folder / {"pages": PAGES_WAITING, "furniture": FURNITURE_WAITING}[kind] / f"{name}.html"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(browser: _Browser, kind: str, name: str, view: str, text: str, *,
          waiting: bool, base: str, route: str = "/page/save", **request
          ) -> tuple[int, dict[str, str], str]:
    return browser.request("POST", route, {
        "kind": kind, "name": name, "view": view, "show": "", "waiting": "1" if waiting else "0",
        "base": base, "text": text}, **request)


def _visual(browser: _Browser, name: str, sections: list, removed: list | None = None, *,
            waiting: bool, base: str, route: str = "/page/save", kind: str = "pages"
            ) -> tuple[int, dict[str, str], str]:
    """A save from the visual view (PRESS-0260 § 4.5)."""
    return browser.request("POST", route, {
        "kind": kind, "name": name, "view": "visual", "show": "",
        "waiting": "1" if waiting else "0", "base": base,
        "sections": json.dumps(sections), "removed": json.dumps(removed or [])})


def _kept(text: str) -> list:
    """Every top-level section of `text`, adopted where it has no area, kept."""
    page = blocks.read("page", text) or blocks.read("page", blocks.adopt(
        text, builder.furniture_spans("page", text)))
    return [{"keep": [at]} for at in range(len(page.sections))]


def _binned(folder: Path) -> list[str]:
    found = folder / "bin"
    return sorted(p.relative_to(found).as_posix().split("/", 1)[1]
                  for p in found.rglob("*") if p.is_file()) if found.exists() else []


def _said(kind: type[Exception]) -> str:
    return face.sentence_for(kind("x"), publishing=False).what


def test_the_refusal_moves_nothing():
    # A hand check found the refusal pushing the press row and the box down:
    # the hint's spot above them was empty, so it took no room until it was
    # written. Three lines are held for it, as the press row's status line is
    # held, so no control moves when status text appears.
    held = re.search(r"\.face #save-hint \{ min-height: ([\d.]+)em; \}", face._STYLE)
    assert held, "the hint's spot is not held open"
    assert float(held.group(1)) >= 4.65, held.group(0)  # three lines at 1.55


# ------------------------------------------------------------------ INV-5 ---


def test_code_keeps_untouched_line_endings():
    original = "<p>one</p>\r\n<p>two</p>\n<p>three</p>\r\n<p>four</p>\n<p>five</p>\r\n"
    posted = "<p>one</p>\n<p>two</p>\n<p>THREE</p>\n<p>four</p>\n<p>five</p>\n"
    assert page_editor.put_code(original, posted) == (
        "<p>one</p>\r\n<p>two</p>\n<p>THREE</p>\n<p>four</p>\n<p>five</p>\r\n")


# ------------------------------------------------------------------ INV-6 ---


def test_edits_wait_in_a_copy(tmp_path):
    folder = _folder(tmp_path)
    live = {kind: _live(folder, kind, name).read_bytes()
            for kind, name in (("pages", "about"), ("furniture", "footer"))}
    with _pages(folder) as browser:
        for kind, name, view, texts in (
                ("pages", "about", "code",
                 (ABOUT_CODE.replace(">Hello<", ">One<"), ABOUT_CODE.replace(">Hello<", ">Two<"))),
                ("furniture", "footer", "code",
                 ("<footer>One</footer>\n", "<footer>Two</footer>\n"))):
            waiting, base = False, _digest(_live(folder, kind, name))
            for text in texts:
                status, _, answer = _save(browser, kind, name, view, text,
                                          waiting=waiting, base=base)
                assert status == 200, answer
                reply = json.loads(answer)
                waiting, base = reply["waiting"], reply["base"]
            assert waiting is True
    for kind, name in (("pages", "about"), ("furniture", "footer")):
        assert _live(folder, kind, name).read_bytes() == live[kind]
        held = _waiting(folder, kind, name).parent
        assert sorted(p.name for p in held.iterdir()) == [f"{name}.html"]
    assert b"Two" in _waiting(folder, "pages", "about").read_bytes()
    assert _waiting(folder, "furniture", "footer").read_bytes() == b"<footer>Two</footer>\n"


# ------------------------------------------------------------------ INV-7 ---


def test_a_stale_page_window_writes_nothing(tmp_path):
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        status, _, text = _save(browser, "pages", "about", "code", ABOUT_CODE,
                                waiting=False, base=_digest(_live(folder, "pages", "about")))
        assert status == 200, text
        first = json.loads(text)["base"]
        for box, expected in (("One", 200), ("Two", 409)):
            status, _, text = _save(browser, "pages", "about", "code",
                                    ABOUT_CODE.replace(">Hello<", f">{box}<"),
                                    waiting=True, base=first)
            assert status == expected, text
        assert html.escape(_said(editor.ChangedElsewhere)) in text
        assert b"One" in _waiting(folder, "pages", "about").read_bytes()

        status, _, text = browser.request("GET", "/page?kind=pages&name=index")
        assert status == 200, text
        base = _digest(_live(folder, "pages", "index"))
        store.write_html(folder, store.PAGES_FOLDER, "index", "behind", waiting=True)
        status, _, text = _save(browser, "pages", "index", "code", "<p>Mine</p>\n",
                                waiting=False, base=base)
    assert status == 409, text
    assert html.escape(_said(editor.ChangedElsewhere)) in text
    assert _waiting(folder, "pages", "index").read_bytes() == b"behind"


# ------------------------------------------------------------------ INV-9 ---


def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credentials, "read", lambda kind, folder, account: KEY)


def _uploaded(transport: _Transport) -> list[bytes]:
    return [base64.b64decode(json.loads(body)["content"])
            for method, url, body, _ in transport.requests
            if method == "POST" and "/git/blobs" in url]


def test_publishing_a_page(tmp_path, monkeypatch):
    _key(monkeypatch)
    changed = ABOUT_CODE.replace(">Hello<", ">Published<")

    def publish(root: Path, transport: _Transport) -> tuple[Path, dict]:
        folder = _folder(root)
        with _pages(folder, transport) as browser:
            status, _, text = _save(browser, "pages", "about", "code", changed,
                                    waiting=False, base=_digest(_live(folder, "pages", "about")),
                                    route="/page/publish")
        assert status == 200, text
        return folder, json.loads(text)

    github = _Transport(reads=_reads(_listing([])), writes=_writes())
    folder, reply = publish(tmp_path / "published", github)
    assert reply["published"] is True, reply
    assert reply["busy"] is False  # PRESS-0235 § 4.4
    written = ABOUT.replace(">Hello<", ">Published<").encode("utf-8")
    assert _live(folder, "pages", "about").read_bytes() == written
    assert not _waiting(folder, "pages", "about").exists()
    assert f"{PAGES_WAITING}/about.html" in _binned(folder)
    assert any(b">Published<" in blob for blob in _uploaded(github))
    assert reply["waiting"] is False
    assert reply["base"] == _digest(_live(folder, "pages", "about"))

    refusing = _Transport(responses=[(401, {}, b'{"message": "Bad credentials"}')])
    folder, reply = publish(tmp_path / "refused", refusing)
    assert reply["published"] is False and reply["failure"], reply
    assert _live(folder, "pages", "about").read_bytes() == ABOUT.encode("utf-8")
    assert _waiting(folder, "pages", "about").read_bytes() == written
    assert reply["waiting"] is True
    assert reply["base"] == _digest(_waiting(folder, "pages", "about"))

    unknown = _Transport(reads=_reads(_listing([])), writes=_writes(), fail_at="/git/refs")
    folder, reply = publish(tmp_path / "unknown", unknown)
    assert reply["published"] is False and UNKNOWN_WORDS in reply["failure"], reply
    assert _live(folder, "pages", "about").read_bytes() == written
    assert not _waiting(folder, "pages", "about").exists()
    assert f"{PAGES_WAITING}/about.html" in _binned(folder)


def test_a_copy_left_behind_is_said(tmp_path, monkeypatch):
    """§ 4.7 step 5 on both paths that run it (PRESS-0144): a waiting copy
    that cannot be binned is named in the reply after a publish that
    succeeded AND after one whose outcome is unknown -- which must not claim
    the changes were published."""
    _key(monkeypatch)

    def cannot_bin(folder, path):
        raise store.StoreError("the bin is not writable")

    monkeypatch.setattr(store, "move_to_bin", cannot_bin)
    changed = ABOUT_CODE.replace(">Hello<", ">Published<")
    for name, transport, left, site in (
        ("published", _Transport(reads=_reads(_listing([])), writes=_writes()),
         "Your changes were published, but their waiting copy was left in place.",
         "Your site has been updated."),
        ("unknown", _Transport(reads=_reads(_listing([])), writes=_writes(),
                               fail_at="/git/refs"),
         "their waiting copy was left in place.", UNKNOWN_WORDS),
    ):
        folder = _folder(tmp_path / name)
        with _pages(folder, transport) as browser:
            status, _, text = _save(browser, "pages", "about", "code", changed,
                                    waiting=False,
                                    base=_digest(_live(folder, "pages", "about")),
                                    route="/page/publish")
        assert status == 200, text
        reply = json.loads(text)
        assert left in html.unescape(reply["notices"]), (name, reply)
        # PRESS-0145: the notice's own site part, never "not changed".
        assert site in html.unescape(reply["notices"]), (name, reply)
        assert "Your site has not changed." not in html.unescape(reply["notices"]), reply
        assert reply["waiting"] is True, (name, reply)
        if name == "unknown":
            assert "Your changes were published" not in html.unescape(reply["notices"]), reply


# ----------------------------------------------------------------- INV-12 ---


def test_stray_furniture_is_warned_about(tmp_path):
    folder = _folder(tmp_path)
    music = UNMARKED.replace("<!-- FOOTER:START -->\n", "<!-- FOOTER:START -->\nAlready there\n")
    store.write_html(folder, store.PAGES_FOLDER, "music", music)
    with _pages(folder) as browser:
        waiting, base = False, _digest(_live(folder, "pages", "about"))
        for between, warned in (("Stray", True), (" \r\n  ", False)):
            text = ABOUT.replace("<!-- FOOTER:START -->\r\n",
                                 f"<!-- FOOTER:START -->\r\n{between}")
            status, _, answer = _save(browser, "pages", "about", "code", text,
                                      waiting=waiting, base=base)
            assert status == 200, answer
            reply = json.loads(answer)
            assert (STRAY in reply["notices"]) is warned, (between, reply["notices"])
            waiting, base = reply["waiting"], reply["base"]

        # PRESS-0260: the visual view writes no furniture, so it warns of none.
        status, _, answer = _visual(browser, "music", _kept(music), waiting=False,
                                    base=_digest(_live(folder, "pages", "music")))
    assert status == 200, answer
    assert STRAY not in json.loads(answer)["notices"]
    assert b"Already there" in _waiting(folder, "pages", "music").read_bytes()


# ----------------------------------------------------------------- INV-13 ---


def test_furniture_opens_in_the_visual_view(tmp_path):
    """PRESS-0216 § 3 decision 5, amending § 3 decision 5 here. Breaks when the
    header, footer or menu is held to the code view."""
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        footer = browser.request("GET", "/page?kind=furniture&name=footer")[2]
        menu_view = browser.request("GET", "/page?kind=furniture&name=navigation")[2]
        code = browser.request("GET", "/page?kind=furniture&name=footer&view=code")[2]
    assert 'id="sections"' in footer and "Show me the code" in footer
    assert 'id="menu-links"' in menu_view and '"Journal"' in menu_view
    assert f">\n{html.escape(FOOTER)}</textarea>" in code and "Back to the page" in code


# ----------------------------------------------------------------- INV-14 ---


def test_throwing_away_page_changes(tmp_path):
    folder = _folder(tmp_path)
    live = _live(folder, "pages", "about").read_bytes()
    with _pages(folder) as browser:
        status, _, text = browser.request("POST", "/page/discard", {
            "kind": "pages", "name": "about", "base": _digest(_live(folder, "pages", "about"))})
        assert status == 409, text
        assert html.escape(_said(editor.ChangedElsewhere)) in text
        assert _binned(folder) == []

        status, _, text = _save(browser, "pages", "about", "code",
                                ABOUT_CODE.replace(">Hello<", ">Gone<"), waiting=False,
                                base=_digest(_live(folder, "pages", "about")))
        assert status == 200, text
        status, headers, text = browser.request("POST", "/page/discard", {
            "kind": "pages", "name": "about", "base": json.loads(text)["base"]})
    assert status == 303, text
    assert headers["Location"] == "/page?kind=pages&name=about"
    assert _binned(folder) == [f"{PAGES_WAITING}/about.html"]
    assert _live(folder, "pages", "about").read_bytes() == live


# ----------------------------------------------------------------- INV-15 ---


def test_the_page_editor_sits_behind_the_faces_boundary(tmp_path):
    folder = _folder(tmp_path)
    base = _digest(_live(folder, "pages", "about"))
    with _pages(folder) as browser:
        status, _, _ = browser.request("GET", "/page?kind=pages&name=about", cookie=False)
        assert status == 403
        for request in ({"cookie": False}, {"origin": "http://elsewhere.example"}):
            status, _, _ = _save(browser, "pages", "about", "code", ABOUT_CODE,
                                 waiting=False, base=base, **request)
            assert status == 403, request
            assert not _waiting(folder, "pages", "about").exists()
        status, _, text = _save(browser, "pages", "about", "code", ABOUT_CODE,
                                waiting=False, base=base)
    assert status == 200, text
    assert _waiting(folder, "pages", "about").exists()


def test_the_page_preview_frame_runs_no_script(tmp_path):
    """PRESS-0012 INV-20 (PRESS-0169): this page writes its own copy of the
    preview frame, which PRESS-0014 § 4.4 makes the entry editor's. So it runs
    no script either, and keeps same-origin for the stylesheet's cookie.
    """
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        status, _, text = browser.request("GET", "/page?kind=pages&name=about")
    assert status == 200, text
    frames = re.findall(r"<iframe\b[^>]*>", text)
    assert len(frames) == 1, frames
    assert re.search(r'\bsandbox="allow-same-origin"', frames[0]), frames[0]


def test_the_page_editor_offers_the_previews_true_colours(tmp_path):
    """PRESS-0187: a dark look dims the preview; the switch undoes it."""
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        status, _, text = browser.request("GET", "/page?kind=pages&name=about")
    assert status == 200, text
    assert '<input type="checkbox" data-true-colours>' in text, text


# PRESS-0214 INV-9 (docs/specs/PRESS-0214-journal-switch.md § 4.5).


def test_no_newest_entry_choice_with_the_journal_off(tmp_path):
    """INV-9. Breaks when the choice shows with the journal off."""
    folder = _folder(tmp_path)
    address = "/page?kind=furniture&name=header"
    with _pages(folder) as browser:
        _, _, on = browser.request("GET", address)
    store.write_journal(folder, False)
    with _pages(folder) as browser:
        _, _, off = browser.request("GET", address)
    assert "Your newest entry" in on
    assert "Your newest entry" not in off


# ----------------------------------------------- PRESS-0260 INV-1 to INV-10 ---
# docs/specs/PRESS-0260-visual-editor.md § 5: the visual view.

AREA_BEFORE = ("<html><body>\n<!-- HEADER:START -->\n<!-- HEADER:END -->\n<main>"
               "<!-- pressless:page -->")
AREA_AFTER = "<!-- /pressless:page --></main>\n</body></html>\n"
TEXT = "<!-- pressless:text --><p>Hello</p><!-- /pressless:text -->"
LOOSE = "<aside>loose</aside>"
HAND = "<!-- pressless:code -->  <div class=x>hand</div>\n<!-- /pressless:code -->"
# Odd gaps on purpose: each kept section keeps the gap before it.
CODED = AREA_BEFORE + "\n  " + TEXT + "\n  " + LOOSE + "\n\n" + HAND + "\n" + AREA_AFTER


def _starter(tmp_path: Path) -> Path:
    folder = _folder(tmp_path / "plain")
    starter_folder = tmp_path / "starter"
    starter_folder.mkdir()
    starter.fill(starter_folder, "A Site")
    (starter_folder / "settings.json").write_bytes((folder / "settings.json").read_bytes())
    return starter_folder


def test_a_save_of_nothing_changed_keeps_every_byte(tmp_path):
    """INV-1. Breaks when a kept section gets a new gap, or is written
    through section_html."""
    folder = _starter(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "coded", CODED)
    store.write_html(folder, store.PAGES_FOLDER, "plain", UNMARKED)
    names = store.list_html(folder, store.PAGES_FOLDER)
    assert {"index", "about", "coded", "plain"} <= set(names), names
    with _pages(folder) as browser:
        for name in names:
            live = _live(folder, "pages", name).read_text(encoding="utf-8")
            status, _, text = _visual(browser, name, _kept(live), waiting=False,
                                      base=_digest(_live(folder, "pages", name)))
            assert status == 200, (name, text)
            expected = blocks.adopt(live, builder.furniture_spans(name, live))
            assert _waiting(folder, "pages", name).read_text(encoding="utf-8") == expected, name
    assert _waiting(folder, "pages", "coded").read_bytes() == CODED.encode("utf-8")


def test_unchanged_sections_keep_their_bytes(tmp_path):
    """INV-2. Breaks when a kept section is rebuilt from its fields."""
    folder = _folder(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "coded", CODED)
    sections = [{"keep": [2]},
                {"kind": "text", "fields": {"html": "Changed &amp; new"}, "parts": []},
                {"keep": [1]},
                {"kind": "button", "fields": {"href": "go.html", "label": "Go"}, "parts": []}]
    with _pages(folder) as browser:
        status, _, text = _visual(browser, "coded", sections, [[0]], waiting=False,
                                  base=_digest(_live(folder, "pages", "coded")))
    assert status == 200, text
    expected = (AREA_BEFORE + "\n\n" + HAND
                + "\n<!-- pressless:text --><p>Changed &amp; new</p><!-- /pressless:text -->"
                + "\n  " + LOOSE
                + '\n<!-- pressless:button --><p class="pressless-button"><a href="go.html">Go'
                  "</a></p><!-- /pressless:button -->"
                + "\n" + AREA_AFTER)
    assert _waiting(folder, "pages", "coded").read_text(encoding="utf-8") == expected


def test_a_save_that_would_not_read_back_writes_nothing(tmp_path):
    """INV-3. Breaks when step 5's read-back is skipped."""
    folder = _folder(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "coded", CODED)
    with _pages(folder) as browser:
        status, _, text = _visual(browser, "coded", _kept(CODED), waiting=False,
                                  base=_digest(_live(folder, "pages", "coded")))
        assert status == 200, text
        base = json.loads(text)["base"]
        held = _waiting(folder, "pages", "coded").read_bytes()
        for sections, removed, said in (
                (_kept(CODED) + [{"code": "<p>x</p><!-- /pressless:page -->"}], [],
                 page_editor.SectionsUnreadable),
                (_kept(CODED)[1:] + [{"kind": "text", "fields": {"html": "<span>x</span>"},
                                      "parts": []}], [[0]], blocks.SectionRefused),
                (_kept(CODED)[1:], [], page_editor.SectionsUnreadable)):
            status, _, text = _visual(browser, "coded", sections, removed, waiting=True,
                                      base=base)
            assert status == 409, (sections, text)
            assert html.escape(_said(said)) in text, (sections, text)
            assert _waiting(folder, "pages", "coded").read_bytes() == held, sections


def test_a_page_is_adopted_at_its_first_save(tmp_path):
    """INV-4. Breaks when `_open` writes the adopted text."""
    folder = _folder(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "plain", UNMARKED)
    live = _live(folder, "pages", "plain")
    before = _digest(live)
    with _pages(folder) as browser:
        status, _, text = browser.request("GET", "/page?kind=pages&name=plain")
        assert status == 200, text
        assert 'data-view="visual"' in text, text
        assert _digest(live) == before
        assert not _waiting(folder, "pages", "plain").exists()
        status, _, text = _visual(browser, "plain", _kept(UNMARKED), waiting=False,
                                  base=before)
    assert status == 200, text
    assert _digest(live) == before
    assert "<!-- pressless:page -->" in _waiting(folder, "pages", "plain").read_text(
        encoding="utf-8")


def test_a_page_that_cannot_be_adopted_opens_in_the_code_view(tmp_path):
    """§ 4.1 step 3: no main, so no sections; the code view, and why."""
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        status, _, text = browser.request("GET", "/page?kind=pages&name=about")
    assert status == 200, text
    assert 'data-view="code"' in text
    assert html.escape(words.say("notice.page_editor.code_only")) in text


def test_the_frame_runs_no_script(tmp_path):
    """INV-5, first half. Breaks when allow-scripts is added to the frame."""
    folder = _folder(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "coded", CODED)
    with _pages(folder) as browser:
        status, _, text = browser.request("GET", "/page?kind=pages&name=coded")
    assert status == 200, text
    assert 'data-view="visual"' in text, text
    frames = re.findall(r"<iframe\b[^>]*>", text)
    assert len(frames) == 1, frames
    assert re.findall(r'\bsandbox="([^"]*)"', frames[0]) == ["allow-same-origin"], frames[0]


def test_the_preview_serves_held_photographs(tmp_path):
    """INV-7, second half. Breaks when only entries' photographs reach the preview."""
    folder = _folder(tmp_path)
    original = store.photograph_path_for(folder, "my boat.jpg")
    original.parent.mkdir(exist_ok=True)
    original.write_bytes(b"a picture, as far as this test is concerned")
    with _pages(folder) as browser:
        status, _, text = browser.request("GET", "/preview/photographs/my%20boat.jpg")
    assert status == 200, text
    assert text == "a picture, as far as this test is concerned"


def test_a_visual_save_over_a_changed_file_writes_nothing(tmp_path):
    """INV-8. Breaks when the visual branch of `_write` skips the base check."""
    folder = _folder(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "coded", CODED)
    base = _digest(_live(folder, "pages", "coded"))
    store.write_html(folder, store.PAGES_FOLDER, "coded", CODED.replace("Hello", "Elsewhere"))
    with _pages(folder) as browser:
        status, _, text = _visual(browser, "coded", _kept(CODED), waiting=False, base=base)
    assert status == 409, text
    assert html.escape(_said(editor.ChangedElsewhere)) in text
    assert not _waiting(folder, "pages", "coded").exists()


def test_the_words_view_is_retired():
    """INV-10. Breaks when a name or word of § 4.7 is left behind."""
    gone = ("WORDS", "Piece", "_Block", "_Runs", "pieces", "_parse", "words", "put_words",
            "_edit", "_placed", "_new_blocks", "_BLOCKS", "PiecesChanged", "_hint")
    assert [name for name in gone if hasattr(page_editor, name)] == []
    keys = ("page_editor.show_words", "script.press.paragraphs",
            "failure.page_editor.PiecesChanged.what", "failure.page_editor.PiecesChanged.next")
    assert [key for key in keys if key in words.ENGLISH] == []


# ------------------------------------------------------------- PRESS-0261 ---

# The colouring runs in a browser; Node runs the same script with no page, so
# it finds no boxes and leaves its `colour` to call.
_NODE = shutil.which("node")
_HARNESS = """const window = {};
const document = {querySelectorAll: () => []};
%s
const text = require("fs").readFileSync(0, "utf8");
process.stdout.write(JSON.stringify(window.presslessCode.colour(text)));
"""


def _coloured(text: str, tmp_path: Path) -> list[tuple[str, str]]:
    script = tmp_path / "colour.js"
    script.write_text(_HARNESS % page_editor._CODE_SCRIPT, encoding="utf-8")
    run = subprocess.run([_NODE, str(script)], input=text.encode("utf-8"),  # noqa: S603
                         capture_output=True, check=True, timeout=30)
    return [tuple(piece) for piece in json.loads(run.stdout)]


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
@pytest.mark.parametrize("text", [
    "", "<", "<<a", 'a < b > c', '<a href="x', "<a href='x' b=c d/>", "<!-- open",
    "<style>a{color:", "<STYLE>p { margin: 0 }</STYLE>", "<script>if (a<b) go()</script>",
    "<p title='it\"s'>é 😀</p>\n", "<div\nclass=x>t</div>", "</>", "<a =>", "<p>&amp;</p>",
])
def test_the_colours_cover_every_letter_once(text, tmp_path):
    """PRESS-0261. Breaks when a piece is dropped or doubled, which would put
    the colours out of step with the letters typed over them."""
    assert "".join(words for words, _ in _coloured(text, tmp_path)) == text


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_tags_attributes_text_and_notes_take_their_own_colours(tmp_path):
    """PRESS-0261. Breaks when a tag, an attribute or a note is coloured as
    something else, or a script's code is coloured as HTML."""
    pieces = _coloured('<a href="x">Hi</a><!-- n --><script>a<b</script>', tmp_path)
    assert pieces == [("<a", "tag"), (" ", ""), ("href", "attr"), ("=", ""), ('"x"', ""),
                      (">", "tag"), ("Hi", ""), ("</a", "tag"), (">", "tag"),
                      ("<!-- n -->", "note"), ("<script", "tag"), (">", "tag"),
                      ("a<b", ""), ("</script", "tag"), (">", "tag")]


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_a_style_is_coloured_as_css(tmp_path):
    """PRESS-0261. Breaks when a selector, a property or a value takes
    another's colour, a colon in a selector included."""
    pieces = _coloured("<style>p a:hover { color: red; } /* c */</style>", tmp_path)
    # A space shows no colour, so its own is not asserted.
    inner = [piece for piece in pieces[2:-2] if piece[0].strip()]
    assert inner == [("p a", "tag"), (":", "tag"), ("hover ", "tag"), ("{", ""),
                     (" color", "attr"), (":", ""), (" red", ""), (";", ""), ("}", ""),
                     ("/* c */", "note")]


# ------------------------------------------------------------- PRESS-0264 ---


def _text(words: str) -> str:
    return f"<!-- pressless:text --><p>{words}</p><!-- /pressless:text -->"


def _columns(*columns: str) -> str:
    return ('<!-- pressless:columns --><div class="pressless-columns">' + "".join(
        f'<!-- pressless:column --><div class="pressless-column">{inner}</div>'
        "<!-- /pressless:column -->" for inner in columns) + "</div><!-- /pressless:columns -->")


@pytest.mark.parametrize(("posted", "written"), [
    # Out of a column, to just below the columns.
    ([{"kind": "columns", "fields": {}, "parts": [[], [{"keep": [0, 1, 0]}]]},
      {"keep": [0, 0, 0]}, {"keep": [1]}],
     [_columns("", _text("Right")), _text("Left"), _text("Loose")]),
    # Into a column, from just below the columns.
    ([{"kind": "columns", "fields": {}, "parts": [[{"keep": [0, 0, 0]}],
                                                  [{"keep": [0, 1, 0]}, {"keep": [1]}]]}],
     [_columns(_text("Left"), _text("Right") + _text("Loose"))]),
])
def test_a_section_moves_between_columns_and_the_page(tmp_path, posted, written):
    """PRESS-0264. Breaks when a section kept by its path is refused, or lost,
    in a list other than the one it was read from."""
    folder = _folder(tmp_path)
    page = (AREA_BEFORE + "\n" + _columns(_text("Left"), _text("Right")) + "\n"
            + _text("Loose") + "\n" + AREA_AFTER)
    store.write_html(folder, store.PAGES_FOLDER, "split", page)
    with _pages(folder) as browser:
        status, _, text = _visual(browser, "split", posted, [[0]], waiting=False,
                                  base=_digest(_live(folder, "pages", "split")))
    assert status == 200, text
    saved = _waiting(folder, "pages", "split").read_text(encoding="utf-8")

    def gapless(html_text: str) -> str:  # the gaps between sections are not at issue
        return re.sub(r"\s+(?=<!-- /?pressless)", "", html_text)
    assert gapless(saved) == gapless(AREA_BEFORE + "".join(written) + AREA_AFTER), saved


# ------------------------------------------------------------- PRESS-0216 ---
# docs/specs/PRESS-0216-furniture-visual.md § 5: the header, footer and menu.

MARKED_FOOTER = ("<footer><!-- pressless:page -->\n"
                 "<!-- pressless:text --><p>Words &amp; more</p><!-- /pressless:text -->\n"
                 "<!-- pressless:code --><p class=x>{{YEAR}}</p><!-- /pressless:code -->\n"
                 "<!-- /pressless:page --></footer>\n")


def test_a_furniture_save_of_nothing_changed_keeps_every_byte(tmp_path):
    """INV-1. Breaks when a header or footer save re-spells a byte outside a
    changed section."""
    folder = _folder(tmp_path)
    store.write_html(folder, store.FURNITURE_FOLDER, "footer", MARKED_FOOTER)
    with _pages(folder) as browser:
        status, _, text = _visual(browser, "footer", [{"keep": [0]}, {"keep": [1]}],
                                  waiting=False, kind="furniture",
                                  base=_digest(_live(folder, "furniture", "footer")))
    assert status == 200, text
    assert _waiting(folder, "furniture", "footer").read_bytes() == MARKED_FOOTER.encode()


def test_words_holding_a_placeholder_are_code(tmp_path):
    """INV-2. Breaks when a text section holding {{ is offered as text, so the
    frame's filled words would be posted back."""
    adopted = blocks.adopt("<footer><p>&copy; {{YEAR}} {{SITE_NAME}}</p></footer>\n", (),
                           "footer")
    assert adopted is not None and "<!-- pressless:text -->" in adopted
    shown = page_editor.outline(blocks.read("footer", adopted))
    assert [(item["kind"], item["code"]) for item in shown] == [
        ("code", "<p>© {{YEAR}} {{SITE_NAME}}</p>")]
    folder = _folder(tmp_path)
    store.write_html(folder, store.FURNITURE_FOLDER, "footer", adopted)
    with _pages(folder) as browser:
        page = browser.request("GET", "/page?kind=furniture&name=footer")[2]
    assert '"kind": "code"' in page and '"kind": "text"' not in page


def _links(browser: _Browser, folder: Path, links) -> tuple[int, dict[str, str], str]:
    return browser.request("POST", "/page/save", {
        "kind": "furniture", "name": "navigation", "view": "visual", "show": "",
        "waiting": "0", "base": _digest(_live(folder, "furniture", "navigation")),
        "links": json.dumps(links)})


def test_a_menu_save_that_names_no_link_writes_nothing(tmp_path):
    """INV-6. Breaks when a menu save skips a bad entry and writes the rest."""
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        status, _, text = _links(browser, folder, [{"at": 3, "words": "x", "href": "x.html"}])
        bad_href = _links(browser, folder, [{"at": None, "words": "Run",
                                            "href": "javascript:go()"}])[0]
        good, _, reply = _links(browser, folder, [
            {"at": None, "words": "About", "href": "{{UP}}pages/about.html"},
            {"at": 0, "words": "Journal", "href": "{{UP}}blog/index.html"}])
    assert (status, bad_href) == (409, 409), text
    assert html.escape(_said(menu.Refused)) in text
    assert good == 200, reply
    assert json.loads(reply)["links"] == [["About", "{{UP}}pages/about.html"],
                                          ["Journal", "{{UP}}blog/index.html"]]
    assert _waiting(folder, "furniture", "navigation").read_text(encoding="utf-8") == (
        '<nav><a href="{{UP}}pages/about.html" data-nav="about">About</a>'
        '<a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a></nav>')


def test_an_unusual_menu_opens_in_the_code_view(tmp_path):
    """INV-7. Breaks when the menu view lists, and a save rewrites, a menu
    that is not one <nav> of links."""
    unusual = '<ul><li><a href="{{UP}}index.html">Home</a></li></ul>'
    folder = _folder(tmp_path)
    store.write_html(folder, store.FURNITURE_FOLDER, "navigation", unusual)
    with _pages(folder) as browser:
        page = browser.request("GET", "/page?kind=furniture&name=navigation")[2]
        status = _links(browser, folder, [{"at": 0, "words": "Home",
                                           "href": "{{UP}}index.html"}])[0]
    assert 'id="menu-links"' not in page and "</textarea>" in page
    assert html.escape(words.say("notice.page_editor.menu_code_only")) in page
    assert status == 409
    assert not _waiting(folder, "furniture", "navigation").exists()


def test_inline_script_json_escapes_angle_brackets() -> None:
    """Security: user content in the inline <script type="application/json">
    blocks cannot open an HTML tag or comment and break out of the element.
    Breaks when the escaping drops back to replacing `</` alone, which leaves
    `<!--` and `<script` (and the `<` of `<\\/script>`) raw in the block."""
    payload = "<!--<script>pwn()</script>-->"
    sections = [{"kind": "code", "code": payload, "marked": True, "path": [0]}]
    panel = page_editor._panel("pages", "index", sections, ())
    block = panel.split('id="sections">', 1)[1].split("</script>", 1)[0]
    assert "<" not in block and ">" not in block
    assert "\\u003c" in block

    menu = page_editor._menu_panel([("words", payload)], ())
    links = menu.split('id="links">', 1)[1].split("</script>", 1)[0]
    assert "<" not in links and ">" not in links
