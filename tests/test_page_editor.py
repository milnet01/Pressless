# Editing a fixed page: the words in a box, the code behind a button (PRESS-0014).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0014-fixed-pages.md § 5. The folder names, the notice and
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
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from test_editor import _Browser
from test_publisher import _listing, _reads, _Transport, _writes

from pressless import credentials, editor, face, page_editor, settings, store

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
ABOUT_WORDS = "Hello\n\nTea & toast, it’s late.\n\nSecond one."
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
        site_name="A Journal", site_address="https://example.org",
        daily_prompt_filter="", untouchable=("CNAME",),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))
    return folder


@contextlib.contextmanager
def _pages(folder: Path, transport: _Transport | None = None) -> Iterator[_Browser]:
    served = face.serve(folder, open_browser=False)
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


def _binned(folder: Path) -> list[str]:
    found = folder / "bin"
    return sorted(p.relative_to(found).as_posix().split("/", 1)[1]
                  for p in found.rglob("*") if p.is_file()) if found.exists() else []


def _said(kind: type[Exception]) -> str:
    return face.sentence_for(kind("x"), publishing=False).what


# ------------------------------------------------------------------ INV-1 ---


def test_words_change_only_their_own_bytes(tmp_path):
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        status, _, text = _save(browser, "pages", "about", "words",
                                ABOUT_WORDS.replace("Hello", "Welcome", 1),
                                waiting=False, base=_digest(_live(folder, "pages", "about")))
    assert status == 200, text
    expected = ABOUT.replace(">Hello<", ">Welcome<")
    assert expected != ABOUT
    assert _waiting(folder, "pages", "about").read_bytes() == expected.encode("utf-8")


# ------------------------------------------------------------------ INV-2 ---


def test_the_box_leaves_out_what_is_not_words():
    page = (
        "<html><head><style>p { color: red }</style>"
        '<script>var shown = "Script words";</script></head>\n'
        "<body>\n"
        "<!-- HEADER:START -->\n<p>Header words</p>\n<!-- HEADER:END -->\n"
        "<template><p>Template words</p></template>\n"
        "<!-- Comment words -->\n"
        "   \t\n"
        "<h1>A heading</h1>\n"
        "<p>A paragraph.</p>\n"
        "</body></html>\n"
    )
    assert page_editor.words("about", page) == "A heading\n\nA paragraph."


# ------------------------------------------------------------------ INV-3 ---


def test_a_changed_paragraph_count_writes_nothing(tmp_path):
    folder = _folder(tmp_path)
    base = _digest(_live(folder, "pages", "about"))
    added = ABOUT_WORDS + "\n\nAnother."
    emptied = ABOUT_WORDS.replace("Tea & toast, it’s late.", "")
    with _pages(folder) as browser:
        for box in (added, emptied):
            status, _, text = _save(browser, "pages", "about", "words", box,
                                    waiting=False, base=base)
            assert status == 200, text
            reply = json.loads(text)
            assert _said(page_editor.PiecesChanged) in (reply["hint"] or ""), reply
            assert reply["base"] == base
            assert reply["waiting"] is False
            assert not _waiting(folder, "pages", "about").exists()

    # PRESS-0143: a run of blank lines is one gap, and an emptied paragraph is
    # refused however many blank lines it leaves behind.
    spaced = ABOUT_WORDS.replace("Hello\n\n", "Hello\n\n\n  \n")
    assert (page_editor.put_words("about", ABOUT, spaced)
            == page_editor.put_words("about", ABOUT, ABOUT_WORDS))
    for gap in ("\n\n\n", "\n\n\n\n"):
        with pytest.raises(page_editor.PiecesChanged):
            page_editor.put_words("about", ABOUT, f"Hello{gap}Second one.")


# ------------------------------------------------------------------ INV-4 ---


def test_typed_markup_is_written_as_text():
    box = ABOUT_WORDS.replace("Second one.", "a <b>bold</b> & more")
    written = page_editor.put_words("about", ABOUT, box)
    assert "  <p>a &lt;b&gt;bold&lt;/b&gt; &amp; more</p>\r\n" in written
    assert "<b>" not in written


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
                ("pages", "about", "words",
                 (ABOUT_WORDS.replace("Hello", "One"), ABOUT_WORDS.replace("Hello", "Two"))),
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
        status, _, text = _save(browser, "pages", "about", "words", ABOUT_WORDS,
                                waiting=False, base=_digest(_live(folder, "pages", "about")))
        assert status == 200, text
        first = json.loads(text)["base"]
        for box, expected in (("One", 200), ("Two", 409)):
            status, _, text = _save(browser, "pages", "about", "words",
                                    ABOUT_WORDS.replace("Hello", box),
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
    changed = ABOUT_WORDS.replace("Hello", "Published")

    def publish(root: Path, transport: _Transport) -> tuple[Path, dict]:
        folder = _folder(root)
        with _pages(folder, transport) as browser:
            status, _, text = _save(browser, "pages", "about", "words", changed,
                                    waiting=False, base=_digest(_live(folder, "pages", "about")),
                                    route="/page/publish")
        assert status == 200, text
        return folder, json.loads(text)

    github = _Transport(reads=_reads(_listing([])), writes=_writes())
    folder, reply = publish(tmp_path / "published", github)
    assert reply["published"] is True, reply
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
    changed = ABOUT_WORDS.replace("Hello", "Published")
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
            status, _, text = _save(browser, "pages", "about", "words", changed,
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
    store.write_html(folder, store.PAGES_FOLDER, "music", ABOUT.replace(
        "<!-- FOOTER:START -->\r\n", "<!-- FOOTER:START -->\r\nAlready there\r\n"))
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

        status, _, answer = _save(browser, "pages", "music", "words",
                                  ABOUT_WORDS.replace("Hello", "Hi"), waiting=False,
                                  base=_digest(_live(folder, "pages", "music")))
    assert status == 200, answer
    assert STRAY not in json.loads(answer)["notices"]
    assert b"Already there" in _waiting(folder, "pages", "music").read_bytes()


# ----------------------------------------------------------------- INV-13 ---


def test_furniture_has_no_words_view(tmp_path):
    folder = _folder(tmp_path)
    with _pages(folder) as browser:
        status, _, text = browser.request("GET", "/page?kind=furniture&name=footer&view=words")
    assert status == 200, text
    assert f">\n{html.escape(FOOTER)}</textarea>" in text
    assert "Show me the code" not in text and "Back to the words" not in text


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

        status, _, text = _save(browser, "pages", "about", "words",
                                ABOUT_WORDS.replace("Hello", "Gone"), waiting=False,
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
            status, _, _ = _save(browser, "pages", "about", "words", ABOUT_WORDS,
                                 waiting=False, base=base, **request)
            assert status == 403, request
            assert not _waiting(folder, "pages", "about").exists()
        status, _, text = _save(browser, "pages", "about", "words", ABOUT_WORDS,
                                waiting=False, base=base)
    assert status == 200, text
    assert _waiting(folder, "pages", "about").exists()
