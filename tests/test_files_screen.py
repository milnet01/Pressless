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

from test_editor import _binned, _Browser, _folder
from test_photographs import _post

from pressless import editor, face, files, files_screen, store

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
        assert headers["Content-Security-Policy"] == face.FILES_POLICY
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
        assert status == 409
        assert "gigs" in refused
        assert _kept(folder) == ["spare.pdf", "used.pdf"]

        status, headers, _ = browser.request("POST", "/files/remove", {"name": "spare.pdf"})
        assert status == 303, headers
        assert _kept(folder) == ["used.pdf"]
        assert _binned(folder) == ["spare.pdf"]


def test_an_upload_is_kept_or_refused_in_words(tmp_path):
    """§ 4.4's POST /file. Breaks when the route stops calling files.add, or a
    refusal is not told in the words table's sentence."""
    folder = _folder(tmp_path)
    with _served(folder) as browser:
        status, text = _post(browser.port, browser.cookie,
                             "/file?name=" + urllib.parse.quote("My Song.MP3"), SONG)
        assert status == 200 and json.loads(text)["name"] == "my-song.mp3"
        status, text = _post(browser.port, browser.cookie, "/file?name=a.html", b"<html>")
    assert status == 409
    said = face.sentence_for(files.NotAllowed("x"), publishing=False).what
    assert html.escape(said) in text
    assert _kept(folder) == ["my-song.mp3"]
