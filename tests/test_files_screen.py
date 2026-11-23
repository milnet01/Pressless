# The Files screen and the kept files' preview addresses (PRESS-0197).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0197-upload-any-file.md § 5. Route names are written out
# rather than imported, and every server starts inside the test that uses it,
# as in tests/test_editor.py. Fixtures are a few made-up bytes behind each
# kind's signature, never real media.
from __future__ import annotations

import contextlib
import html
import json
import os
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_editor import _binned, _Browser, _folder
from test_face import FILES_POLICY_WORDS
from test_photographs import _post

from pressless import builder, editor, face, files, files_screen, store, words
from pressless.notices import notify

PDF = b"%PDF- made up"   # thirteen bytes
SONG = b"ID3 a made-up song"
PAGE = ("<html><body><main><!-- pressless:page -->\n"
        '<!-- pressless:download --><p class="pressless-download">'
        '<a href="../files/{name}" download>A</a></p><!-- /pressless:download -->\n'
        "<!-- /pressless:page --></main></body></html>\n")


@contextlib.contextmanager
def _served(folder: Path) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        files_screen.register(served, folder)
        yield _Browser(served)
    finally:
        served.stop()


def _keep(folder: Path, name: str, data: bytes) -> None:
    target = store.file_path_for(folder, name)
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(data)


def _kept(folder: Path) -> list[str]:
    where = folder / "files"
    return sorted(path.name for path in where.iterdir()) if where.is_dir() else []


# ------------------------------------------------------------------ INV-5 ---


def test_kept_files_are_served_under_the_policy(tmp_path):
    """INV-5. Breaks when a kind is served as another type, or without the
    policy."""
    folder = _folder(tmp_path)
    _keep(folder, "a.mp3", SONG)
    _keep(folder, "a.txt", b"made up")
    if os.name != "nt":
        (folder / "files" / "con.mp3").write_bytes(SONG)   # a name the Store refuses
    with _served(folder) as browser:
        status, headers, _ = browser.request("GET", "/preview/files/a.mp3")
        assert status == 200
        assert headers["Content-Type"] == "audio/mpeg"
        assert headers["Content-Security-Policy"] == FILES_POLICY_WORDS
        assert headers["X-Content-Type-Options"] == "nosniff"
        status, headers, _ = browser.request("GET", "/preview/files/a.txt")
        assert (status, headers["Content-Type"]) == (200, "text/plain; charset=utf-8")
        status, _, _ = browser.request("GET", "/preview/files/con.mp3")
        assert status == 404


# ------------------------------------------------------------------ INV-9 ---


def test_removal_is_refused_while_a_page_names_the_file(tmp_path):
    """INV-9. Breaks when a named file is removed, a waiting page is not
    read, or an unnamed file is not removed."""
    folder = _folder(tmp_path)
    _keep(folder, "used.pdf", PDF)
    _keep(folder, "spare.pdf", PDF)
    store.write_html(folder, store.PAGES_FOLDER, "gigs", PAGE.format(name="used.pdf"),
                     waiting=True)
    with _served(folder) as browser:
        status, _, page = browser.request("GET", "/files")
        assert status == 200
        assert "used.pdf" in page and "spare.pdf" in page
        assert "13 bytes" in page
        assert "gigs" in page, "the page naming the file is not shown"

        status, _, refused = browser.request("POST", "/files/remove", {"name": "used.pdf"})
        assert status == 200 and refused.startswith("<!doctype html>"), refused
        assert "gigs" in refused
        assert _kept(folder) == ["spare.pdf", "used.pdf"]

        status, headers, _ = browser.request("POST", "/files/remove", {"name": "spare.pdf"})
        assert status == 303, headers
        assert _kept(folder) == ["used.pdf"]
        assert _binned(folder) == ["spare.pdf"]


def test_a_refusal_shows_its_notices(tmp_path, monkeypatch):
    """A refused removal is a whole Face page carrying the notices raised on
    the way. Breaks when it is answered inside the capture, which fills its
    list only as it ends."""
    folder = _folder(tmp_path)
    _keep(folder, "used.pdf", PDF)

    def noisy(_folder: Path) -> dict[str, tuple[builder.FileUser, ...]]:
        notify(store.StoreNotice("notice.store.not_private", file="notes.txt",
                                 mode="644"), stacklevel=2)
        return {"used.pdf": (builder.FileUser(store.PAGES_FOLDER, "gigs"),)}

    monkeypatch.setattr(builder, "files_named", noisy)
    with _served(folder) as browser:
        _, _, refused = browser.request("POST", "/files/remove", {"name": "used.pdf"})
    assert "notes.txt" in refused and "gigs" in refused


def test_the_menu_and_the_look_are_named_in_words(tmp_path):
    """PRESS-0197 § 4.6: a file the menu or the style code names is shown
    beside those parts' words, never builder.files_named's own names."""
    folder = _folder(tmp_path)
    _keep(folder, "menu.pdf", PDF)
    _keep(folder, "a.woff2", b"wOF2 a made-up font")
    store.write_html(folder, store.FURNITURE_FOLDER, "navigation",
                     '<nav><a href="{{UP}}files/menu.pdf">Menu</a></nav>')
    store.write_style_code(folder, '@font-face { src: url("../files/a.woff2"); }')
    with _served(folder) as browser:
        page = browser.request("GET", "/files")[2]
    rows = {row.split("</td>")[0]: row for row in page.split("<tr><td>")[1:]}
    assert "the menu" in rows["menu.pdf"] and "navigation" not in rows["menu.pdf"]
    assert "the look" in rows["a.woff2"] and ">look<" not in rows["a.woff2"]


def test_a_page_named_as_a_part_is_shown_by_its_name(tmp_path):
    """PRESS-0197 § 4.6: a fixed page called header, footer, navigation or
    look is shown by its own name, and the part of that name by the part's
    words. Breaks when a user is told apart by its name alone."""
    folder = _folder(tmp_path)
    for part in ("header", "footer", "navigation", "look"):
        _keep(folder, f"{part}.pdf", PDF)
        store.write_html(folder, store.PAGES_FOLDER, part,
                         f'<p><a href="../files/{part}.pdf">x</a></p>')
    _keep(folder, "real.pdf", PDF)
    store.write_html(folder, store.FURNITURE_FOLDER, "footer",
                     '<footer><a href="{{UP}}files/real.pdf">x</a></footer>')
    with _served(folder) as browser:
        page = browser.request("GET", "/files")[2]
    rows = {row.split("</td>")[0]: row.split("</td>")[2] for row in page.split("<tr><td>")[1:]}
    assert rows == {"footer.pdf": "<td>footer", "header.pdf": "<td>header",
                    "look.pdf": "<td>look", "navigation.pdf": "<td>navigation",
                    "real.pdf": "<td>the footer"}, rows


def test_an_upload_is_kept_or_refused_in_words(tmp_path):
    """§ 4.4's POST /file. Breaks when the route stops calling files.add, or a
    refusal is not told in the words table's sentence."""
    folder = _folder(tmp_path)
    with _served(folder) as browser:
        status, text = _post(browser.port, browser.cookie,
                             "/file?name=" + urllib.parse.quote("My Song.MP3"), SONG)
        assert status == 200 and json.loads(text)["name"] == "my-song.mp3"
        # The address a page names it by, built where the Builder builds it.
        assert json.loads(text)["address"] == "files/my-song.mp3"
        status, text = _post(browser.port, browser.cookie, "/file?name=a.html", b"<html>")
    assert status == 409
    said = face.sentence_for(files.NotAllowed("x"), publishing=False).what
    assert html.escape(said) in text
    assert _kept(folder) == ["my-song.mp3"]


@pytest.mark.parametrize(("size", "language", "said"), [
    (999, "en", "999 bytes"), (999_499, "en", "999 KB"), (999_500, "en", "1.0 MB"),
    (1_500_000, "en", "1.5 MB"), (1_500_000, "de", "1,5 MB"),
])
def test_a_size_reads_as_the_language_writes_it(size, language, said):
    """PRESS-0241 INV-8 and § 4.4: a size never reads 1000 KB, and a decimal
    takes the language's mark. Breaks when 999,500 bytes round up to 1000
    KB, or German shows 1.5 MB, which it reads as fifteen hundred."""
    words.choose(language)
    with words.use({"files_screen.bytes": "{n} bytes", "files_screen.kb": "{n} KB",
                    "files_screen.mb": "{n} MB"}):
        assert files_screen._size(size) == said
