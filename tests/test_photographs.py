# Adding a photograph (PRESS-0016).
#
# There is no spec: the user chose on 2026-09-29 to let these tests hold the
# naming rule the roadmap item records. Names and sentences are written out here
# rather than imported from the modules under test: shared, they would compare
# the module against itself (docs/working-here.md, the test_settings.py trap).
#
# Every server is started inside the test that uses it, never in a fixture.
from __future__ import annotations

import contextlib
import hashlib
import html
import http.client
import io
import json
import urllib.parse
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from _face_session import session_cookie
from PIL import Image

from pressless import editor, face, marks, photographs, settings, store


def _picture(fmt: str = "JPEG", colour: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), colour).save(out, fmt)
    return out.getvalue()


def _originals(folder: Path) -> dict[str, bytes]:
    where = folder / "photographs"
    if not where.is_dir():
        return {}
    return {path.name: path.read_bytes() for path in where.iterdir()}


# ------------------------------------------------------------- the name ---

@pytest.mark.parametrize(("chosen", "fmt", "kept"), [
    ("IMG 1234 (Beach).JPG", "JPEG", "img-1234-beach.jpg"),
    ("Café au lait.jpeg", "JPEG", "cafe-au-lait.jpeg"),
    ("sea_front-2.png", "PNG", "sea_front-2.png"),
    (r"C:\Users\him\Pictures\Dusk.webp", "WEBP", "dusk.webp"),
    ("scan", "GIF", "scan.gif"),
    ("really a jpeg.png", "JPEG", "really-a-jpeg.jpg"),
    ("日本.png", "PNG", "photograph.png"),
    ("....jpg", "JPEG", "photograph.jpg"),
    ("a" * 80 + ".jpg", "JPEG", "a" * 60 + ".jpg"),
])
def test_a_name_is_the_chosen_name_made_plain(chosen, fmt, kept):
    assert photographs.name_for(chosen, fmt) == kept


@pytest.mark.parametrize("chosen", [
    ".hidden.jpg", "con.jpg", "NUL .jpg", "a|b.jpg", "a b .jpg", "..", "",
    "x}y.jpg", "{photo: z}.jpg", "tab\there.jpg", "trailing.",
])
def test_every_name_passes_the_mark_and_the_store(tmp_path, chosen):
    name = photographs.add(tmp_path, chosen, _picture())
    assert marks.parse(f"{{photo: {name}}}") == (marks.Photo(mark="photo", name=name,
                                                              caption=None),)
    assert store.photograph_path_for(tmp_path, name).read_bytes() == _picture()
    assert not name.startswith(".")


def test_a_device_name_is_kept_as_name_2(tmp_path):
    assert photographs.add(tmp_path, "con.jpg", _picture()) == "con-2.jpg"


# ------------------------------------------------------------ keep both ---

def test_a_taken_name_keeps_both(tmp_path):
    red, blue = _picture(colour=(255, 0, 0)), _picture(colour=(0, 0, 255))
    assert photographs.add(tmp_path, "dusk.jpg", red) == "dusk.jpg"
    assert photographs.add(tmp_path, "Dusk.jpg", blue) == "dusk-2.jpg"
    assert _originals(tmp_path) == {"dusk.jpg": red, "dusk-2.jpg": blue}


def test_the_same_photograph_twice_is_kept_once(tmp_path):
    red, blue = _picture(colour=(255, 0, 0)), _picture(colour=(0, 0, 255))
    photographs.add(tmp_path, "dusk.jpg", red)
    photographs.add(tmp_path, "dusk.jpg", blue)
    assert photographs.add(tmp_path, "dusk.jpg", blue) == "dusk-2.jpg"
    assert photographs.add(tmp_path, "dusk.jpg", red) == "dusk.jpg"
    assert sorted(_originals(tmp_path)) == ["dusk-2.jpg", "dusk.jpg"]


# ----------------------------------------------------------- what it takes ---

def _animated(fmt: str) -> bytes:
    out = io.BytesIO()
    frames = [Image.new("RGB", (64, 64), c) for c in ((1, 2, 3), (200, 9, 9), (9, 200, 9))]
    frames[0].save(out, fmt, save_all=True, append_images=frames[1:])
    return out.getvalue()


def _cut(data: bytes) -> bytes:
    """Three quarters of a file: it still opens, and a frame cannot be decoded."""
    return data[:len(data) * 3 // 4]


@pytest.mark.parametrize("data", [
    b"", b"not a picture", _picture("BMP"),
    _cut(_picture("JPEG")), _cut(_animated("PNG")), _cut(_animated("WEBP")),
    _cut(_animated("GIF")),
], ids=["empty", "text", "bmp", "cut-jpeg", "cut-png", "cut-webp", "cut-gif"])
def test_only_a_picture_the_builder_publishes_is_kept(tmp_path, data):
    with pytest.raises(photographs.NotAPhotograph):
        photographs.add(tmp_path, "dusk.jpg", data)
    assert _originals(tmp_path) == {}


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP", "GIF"])
def test_each_published_format_is_kept_under_its_own_ending(tmp_path, fmt):
    ending = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}[fmt]
    assert photographs.add(tmp_path, "picture", _picture(fmt)) == "picture" + ending


# -------------------------------------------------------------- missing ---

def test_missing_names_only_the_photographs_it_lacks(tmp_path):
    photographs.add(tmp_path, "have.jpg", _picture())
    body = "Words.\n{photo: have.jpg}\n{photo: lack.jpg | A caption}\n{photo: also.png}"
    assert photographs.missing(tmp_path, body) == ["also.png", "lack.jpg"]
    assert photographs.missing(tmp_path, "No photographs.") == []


# ------------------------------------------------------------ the editor ---

@contextlib.contextmanager
def _served(folder: Path) -> Iterator[tuple[int, str]]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        yield urllib.parse.urlsplit(served.url).port, session_cookie(served.url)
    finally:
        served.stop()


def _post(port: int, cookie: str, path: str, body: bytes,
          kind: str = "application/octet-stream") -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"127.0.0.1:{port}")
        conn.putheader("Cookie", cookie)
        conn.putheader("Origin", f"http://127.0.0.1:{port}")
        conn.putheader("Content-Type", kind)
        conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        conn.close()


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    for name, text in (("header", "<header></header>\n"), ("navigation", "<nav></nav>"),
                       ("footer", "<footer></footer>\n")):
        store.write_html(folder, store.FURNITURE_FOLDER, name, text)
    settings.save(folder, settings.Settings(
        site_folder=folder / "site", repository="owner/owner.github.io",
        site_name="A Journal", site_address="https://example.org",
        daily_prompt_filter="", untouchable=("CNAME",),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))
    return folder


def test_the_editor_keeps_a_posted_photograph(tmp_path):
    folder = _folder(tmp_path)
    with _served(folder) as (port, cookie):
        status, text = _post(port, cookie, "/photograph?name=" +
                             urllib.parse.quote("Sea Front.JPG"), _picture())
    assert status == 200 and json.loads(text)["name"] == "sea-front.jpg"
    assert _originals(folder) == {"sea-front.jpg": _picture()}


def test_the_editor_refuses_a_file_that_is_not_a_picture(tmp_path):
    folder = _folder(tmp_path)
    with _served(folder) as (port, cookie):
        status, text = _post(port, cookie, "/photograph?name=notes.txt", b"words")
    assert status == 409
    assert html.escape("That file is not a picture Pressless can put on your site, "
                       "so it was not added.") in text
    assert _originals(folder) == {}


def test_the_editor_says_which_photographs_it_lacks(tmp_path):
    folder = _folder(tmp_path)
    photographs.add(folder, "have.jpg", _picture())
    entry = store.Entry(slug="dusk", title="Dusk", date=datetime(2020, 1, 2), categories=(),
                        tags=(), body="{photo: have.jpg}\n{photo: lack.jpg}", extra=())
    store.write(folder, entry, draft=True)
    base = hashlib.sha256(store.path_for(folder, "dusk", draft=True).read_bytes()).hexdigest()
    with _served(folder) as (port, cookie):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/edit?slug=dusk", headers={"Cookie": cookie})
        page = conn.getresponse().read().decode("utf-8")
        conn.close()
        form = urllib.parse.urlencode({"slug": "dusk", "draft": "1", "base": base,
                                       "title": "Dusk", "categories": "", "tags": "",
                                       "body": "{photo: gone.png}"}).encode()
        status, text = _post(port, cookie, "/save", form,
                             "application/x-www-form-urlencoded")
    assert f'data-missing="{html.escape(json.dumps(["lack.jpg"]))}"' in page
    assert status == 200 and json.loads(text)["missing"] == ["gone.png"]
