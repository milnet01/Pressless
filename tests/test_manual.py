# The manual inside the app (PRESS-0219).
#
# The manual's words are one text file and its pictures and videos a folder
# beside it. These tests hold that the two agree, that every picture and video
# is described for someone who cannot see it, that no word in the file reaches
# the page as markup, that every screen links to it, and that it needs no
# internet. Names and the format's patterns are written out here rather than
# imported, so the module is not checked against itself.
from __future__ import annotations

import html
import http.client
import re
import urllib.parse
from pathlib import Path

from _face_session import session_cookie
from _scripts import load_script

from pressless import face, manual, words

ADDRESS = "/manual"
FILES = Path(__file__).resolve().parent.parent / "src" / "pressless" / "manual_files"
TEXT = FILES / "en.txt"
MEDIA = FILES / "media"

# § 4.2's constructs, strictly. A line starting with a construct's first word
# that does not match its pattern is malformed.
TASK = re.compile(r"== [a-z0-9-]+ \| \S.*")
PICTURE = re.compile(r"picture ([a-z0-9-]+\.png) \|(.*)")
VIDEO = re.compile(r"video ([a-z0-9-]+\.webm) \|(.*)")
STARTS = {"==": TASK, "picture": PICTURE, "video": VIDEO}

MB = 1024 * 1024


def _lines() -> list[str]:
    return TEXT.read_text(encoding="utf-8").splitlines()


def _named(pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    """(file name, description) for every line `pattern` matches."""
    return [(m.group(1), m.group(2).strip()) for line in _lines()
            if (m := pattern.fullmatch(line.strip()))]


def _get(served: face.Face, path: str) -> tuple[int, str]:
    parts = urllib.parse.urlsplit(served.url)
    conn = http.client.HTTPConnection("127.0.0.1", parts.port, timeout=10)
    try:
        conn.request("GET", path, headers={"Cookie": session_cookie(served.url)})
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        conn.close()


def _served(site: Path, path: str, **kwargs: object) -> tuple[int, str]:
    served = face.serve(site)
    try:
        manual.register(served, **kwargs)
        return _get(served, path)
    finally:
        served.stop()


def test_text_and_media_agree():
    """INV-1. Breaks when a picture is renamed and en.txt is not, or a file is
    left behind after its task is cut."""
    malformed = [line for line in _lines()
                 if (first := line.strip().split(" ", 1)[0]) in STARTS
                 and not STARTS[first].fullmatch(line.strip())]
    assert not malformed, malformed
    named = {name for name, _ in _named(PICTURE) + _named(VIDEO)}
    captions = {name.removesuffix(".webm") + ".en.vtt" for name, _ in _named(VIDEO)}
    present = {path.name for path in MEDIA.iterdir()}
    assert named - present == set(), "named in en.txt but missing"
    assert present - named - captions == set(), "in media but named by nothing"
    assert named, "the manual shows nothing"


def test_every_picture_and_video_is_described():
    """INV-2. Breaks on `picture x.png |` with nothing after the bar, or
    `x.webm` with no `x.en.vtt`."""
    for name, alt in _named(PICTURE):
        assert alt, f"{name} has no alt text"
    for name, label in _named(VIDEO):
        assert label, f"{name} has no label"
        assert (MEDIA / (name.removesuffix(".webm") + ".en.vtt")).is_file(), name


def test_words_are_escaped():
    """INV-3. Breaks when any construct writes its words unescaped."""
    page = manual.render(
        "<b>x</b> opening\n"
        "\n"
        "== a-task | <b>x</b> title\n"
        "<b>x</b> paragraph\n"
        "1. <b>x</b> step\n"
        "picture a.png | <b>x</b> alt\n"
        "video a.webm | <b>x</b> label\n")
    assert "<b>" not in page
    for where in ("opening", "title", "paragraph", "step", "alt", "label"):
        assert f"&lt;b&gt;x&lt;/b&gt; {where}" in page, where


def test_every_page_has_help():
    """INV-4. Breaks when the bar is rebuilt without it, or it moves under More."""
    page = face._page("<p>body</p>")
    assert 'href="/manual"' in page
    assert page.index('href="/manual"') < page.index('class="more"')


def test_manual_works_offline(tmp_path):
    """INV-5. Breaks when a picture or video is named by an online address.

    A data: address carries its content inline (the Face's icon), so it needs
    no network and is allowed."""
    status, page = _served(tmp_path, ADDRESS)
    assert status == 200
    named = re.findall(r'\b(?:src|href)="([^"]*)"', page)
    assert any(value.startswith("/manual/media/") for value in named)
    outside = [value for value in named
               if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:|//", value)
               and not value.startswith("data:")]
    assert not outside, outside


def test_media_stays_small():
    """INV-6. Breaks when a long or high-resolution video is added."""
    sizes = {path.name: path.stat().st_size for path in MEDIA.iterdir()}
    videos = {name: size for name, size in sizes.items() if name.endswith(".webm")}
    largest = max(videos.values(), default=0)
    print(f"media folder: {sum(sizes.values()) / MB:.2f} MB; "
          f"largest video: {largest / MB:.2f} MB")
    assert sum(sizes.values()) < 25 * MB
    assert largest < 3 * MB


def test_media_are_served(tmp_path):
    """Breaks when the media folder is not registered under /manual/media/."""
    name, _ = _named(PICTURE)[0]
    status, _ = _served(tmp_path, f"/manual/media/{name}")
    assert status == 200


def test_a_missing_manual_says_so(tmp_path):
    """§ 6: a broken bundle shows the failure page, not a crash."""
    _, page = _served(tmp_path, ADDRESS, folder=tmp_path / "nowhere")
    assert html.escape(words.say("failure.manual.ManualMissing.what")) in page
    assert 'href="/manual"' in page   # the Help link still shows


def test_tasks_are_sections_in_file_order():
    page = manual.render("== first | One\n1. a\n\n== second | Two\nwords\n")
    assert page.index('<section id="first"') < page.index('<section id="second"')
    assert "<h2>One</h2>" in page and "<h2>Two</h2>" in page


def test_steps_keep_counting_past_a_picture():
    """A picture between steps does not restart the numbering at 1."""
    page = manual.render("== t | T\n1. a\n2. b\npicture p.png | P\n3. c\n")
    assert '<ol start="3">' in page


def test_video_has_default_captions():
    page = manual.render("== t | T\nvideo clip.webm | Clip\n")
    assert 'preload="none"' in page and 'aria-label="Clip"' in page
    assert re.search(r'<track kind="captions" src="/manual/media/clip\.en\.vtt"[^>]*default',
                     page)


def test_a_malformed_construct_is_a_paragraph():
    page = manual.render("== t | T\npicture p.png\n")
    assert "<img" not in page
    assert "<p>picture p.png</p>" in page


def test_freeze_bundles_the_manual(tmp_path):
    """INV-7. Breaks when DATA loses the pair, or the folder is renamed.

    Only the flag is checked here; a built artefact proves the files arrive."""
    args = load_script("freeze_flags.py").pyinstaller_args(tmp_path)
    pairs = [args[i + 1] for i, flag in enumerate(args) if flag == "--add-data"]
    assert f"{FILES}:pressless/manual_files" in pairs, pairs
    assert FILES.is_dir()
