# INV-1 to INV-13 for PRESS-0008 (the Builder). Pure: every Store and every
# image is built in the test, so this runs in CI. INV-14 lives in
# test_failure_messages.py and INV-15 in test_builder_archive.py.
#
# Why this exists: docs/specs/PRESS-0008-builder.md is the contract. The
# Builder is the only part that can keep a draft off the site (S7), and every
# address it writes is one a reader already holds (§2). Each test below is
# named for the invariant it locks, per that spec's §5 and §10.
#
# Every address here is example.org and every name is made up: nothing names a
# real person or site.
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import locale
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

import pressless.builder as builder
from pressless import marks, store
from pressless.builder import (
    LONGEST_SIDE,
    PER_PAGE,
    ROOT_OUTPUT,
    BuildStopped,
    Built,
    SiteFolderUnusable,
    build,
    web_photograph,
)
from pressless.settings import Credentials, Settings

SENTINEL = "zqxsentinelzqx"
YEAR = datetime.now().year

HEADER = (
    "<!-- header: the comment the build removes -->\n"
    '  <header class="site">\n'
    '    <a class="logo{{ANIM1}}" href="{{UP}}index.html">Home</a>\n'
    '    <p class="line{{ANIM2}}{{ANIM3}}">A line</p>\n'
    "{{NAVIGATION}}\n"
    "  </header>\n"
)
NAVIGATION = (
    "    <!-- the menu keeps this comment -->\n"
    '    <nav class="primary" aria-label="Primary">\n'
    '      <a href="{{UP}}index.html" data-nav="Home">Home</a>\n'
    '      <a href="{{UP}}pages/about.html" data-nav="about">About</a>\n'
    '      <a href="{{UP}}pages/about.html" data-nav="about">About again</a>\n'
    '      <a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a>\n'
    "    </nav>"
)
FOOTER = (
    "<!-- footer: the comment the build removes -->\n"
    '  <footer><p>&copy; {{YEAR}} <a href="{{UP}}pages/privacy.html">Privacy</a></p></footer>\n'
)


def _settings(**overrides) -> Settings:
    values = {
        "site_folder": Path("/writer/Pressless/site"),
        "repository": "owner/name",
        "site_name": "A Journal",
        "site_address": "https://example.org/",
        "daily_prompt_filter": "dailyprompt-*",
        "untouchable": ("CNAME", "assets"),
        "credentials": Credentials(store="keyring", github_account="publishing-key",
                                   google_account=None),
        "analytics_property_id": None,
    }
    values.update(overrides)
    return Settings(**values)


def _entry(slug, date="2020-01-02 03:04:05", *, title="", body="Words.", categories=(),
           tags=(), extra=()) -> store.Entry:
    return store.Entry(slug=slug, title=title,
                       date=datetime.strptime(date, "%Y-%m-%d %H:%M:%S"),
                       categories=tuple(categories), tags=tuple(tags), body=body,
                       extra=tuple(extra))


def _comment(identifier="1", body="Lovely.", author="A reader") -> store.Comment:
    return store.Comment(identifier=identifier, author=author, author_url="",
                         date=datetime(2020, 1, 3, 4, 5, 6), body=body, parent="")


def _store(tmp_path: Path, *, furniture=True, pages=None) -> Path:
    folder = tmp_path / "data"
    folder.mkdir(parents=True)
    if furniture:
        for name, text in (("header", HEADER), ("navigation", NAVIGATION),
                           ("footer", FOOTER)):
            store.write_html(folder, store.FURNITURE_FOLDER, name, text)
    for name, text in (pages if pages is not None else {
        "index": "<html><body>\n<!-- HEADER:START nonav animate -->\n<!-- HEADER:END -->\n"
                 "<p>Home</p>\n</body></html>\n",
    }).items():
        store.write_html(folder, store.PAGES_FOLDER, name, text)
    return folder


def _photograph(folder: Path, name: str, data: bytes) -> None:
    target = store.photograph_path_for(folder, name)
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(data)


def _image(fmt: str, size=(40, 30), colour=(200, 40, 40), **save) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, fmt, **save)
    return out.getvalue()


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _html_files(root: Path):
    for path in root.rglob("*.html"):
        if "content" not in path.relative_to(root).parts:
            yield path


def _digest(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in _files(root)}


def _entry_page(into: Path, entry: store.Entry) -> Path:
    return into / "blog" / f"{entry.date:%Y/%m/%d}" / entry.slug / "index.html"


# ------------------------------------------------------------------ INV-1 ---


def test_no_draft_reaches_the_folder(tmp_path):
    """INV-1: a draft's words reach no file in `into`, unless the Face hands
    it as `change` -- and even then, not `content/`."""
    folder = _store(tmp_path)
    store.write(folder, _entry("shown", body="Published words."), draft=False)
    draft = _entry(f"draft-{SENTINEL}", title=f"Title {SENTINEL}",
                   body=f"Body {SENTINEL}", tags=(f"tag-{SENTINEL}",))
    store.write(folder, draft, draft=True)
    store.write_comments(folder, draft.slug, (_comment(body=f"Said {SENTINEL}"),))

    into = tmp_path / "site"
    build(folder, _settings(), into)
    leaked = [name for name in _files(into)
              if SENTINEL.encode() in (into / name).read_bytes() or SENTINEL in name]
    assert not leaked, f"a draft's words reached {leaked}"
    assert _entry_page(into, _entry("shown")).is_file()

    preview = tmp_path / "preview"
    build(folder, _settings(), preview, photo_src=lambda name: name, change=draft)
    assert _entry_page(preview, draft).is_file(), "the change was not built"
    leaked = [name for name in _files(preview / "content")
              if SENTINEL.encode() in (preview / "content" / name).read_bytes()
              or SENTINEL in name]
    assert not leaked, f"content/ took the change's words: {leaked}"


# ------------------------------------------------------------------ INV-2 ---


def test_a_filtered_entry_is_kept_off_every_page(tmp_path):
    """INV-2: a filtered entry is on no page, listing or sitemap line, and is in
    content/ with its comments."""
    folder = _store(tmp_path)
    hidden = _entry("hidden-answer", "2021-05-06 07:08:09",
                    tags=("dailyprompt-1234", "loss"), categories=("quotes",))
    shown = _entry("shown-answer", "2021-05-05 07:08:09", tags=("dailyprompt",))
    store.write(folder, hidden, draft=False)
    store.write(folder, shown, draft=False)
    store.write_comments(folder, hidden.slug, (_comment(),))

    into = tmp_path / "site"
    built = build(folder, _settings(), into)

    assert built.filtered == ("hidden-answer",)
    assert (into / "content/published/hidden-answer.txt").is_file()
    assert (into / "content/comments/hidden-answer.json").is_file()
    for path in _html_files(into):
        assert "hidden-answer" not in path.read_text(encoding="utf-8"), path
    assert "hidden-answer" not in (into / "sitemap.xml").read_text(encoding="utf-8")
    assert not (into / "blog/tag/dailyprompt-1234").exists()
    assert not (into / "blog/tag/loss").exists(), "a tag page lists only a filtered entry"
    assert not (into / "blog/category/quotes").exists()
    assert _entry_page(into, shown).is_file()
    assert (into / "blog/tag/dailyprompt/index.html").is_file()


# ------------------------------------------------------------------ INV-3 ---


def test_pages_sit_at_their_addresses(tmp_path):
    """INV-3: every page sits at §4.3's address, and a listing breaks every
    PER_PAGE entries in §4.2's order."""
    folder = _store(tmp_path, pages={
        "index": "<p>home</p>\n",
        "about": "<p>about</p>\n",
    })
    entries = [
        _entry(f"entry-{n:02d}", f"2019-{(n % 12) + 1:02d}-{(n % 27) + 1:02d} 10:00:00",
               title=f"Entry {n}", categories=("poetry",), tags=("night",))
        for n in range(PER_PAGE - 1)
    ]
    # Two sharing a date, both newer than the rest: `b-tie` must follow `a-tie`.
    entries.append(_entry("b-tie", "2023-06-01 12:00:00", title="Tie B"))
    entries.append(_entry("a-tie", "2023-06-01 12:00:00", title="Tie A"))
    oldest = _entry("the-oldest", "2001-01-01 00:00:00", title="Oldest")
    entries.append(oldest)
    assert len(entries) == PER_PAGE + 2
    for entry in entries:
        store.write(folder, entry, draft=False)

    into = tmp_path / "site"
    build(folder, _settings(), into)

    assert (into / "index.html").read_text(encoding="utf-8") == "<p>home</p>\n"
    assert (into / "pages/about.html").is_file()
    assert not (into / "about.html").exists()
    for entry in entries:
        assert _entry_page(into, entry).is_file(), entry.slug
    journal = (into / "blog/index.html").read_text(encoding="utf-8")
    second = (into / "blog/page/2/index.html").read_text(encoding="utf-8")
    assert not (into / "blog/page/1").exists()
    assert "the-oldest" in second and "the-oldest" not in journal
    assert journal.index("a-tie/") < journal.index("b-tie/")
    assert (into / "blog/category/poetry/index.html").is_file()
    assert (into / "blog/tag/night/index.html").is_file()
    assert (into / "blog/archive/index.html").is_file()
    assert (into / "blog/page/2/index.html").is_file()
    assert not (into / "blog/page/3").exists()


# ------------------------------------------------------------------ INV-4 ---


def test_the_folder_is_what_it_declares(tmp_path):
    """INV-4: Built.files is exactly the set of files under `into`, each under
    ROOT_OUTPUT, and no segment begins with a dot."""
    folder = _store(tmp_path, pages={"index": "<p>home</p>\n", "about": "<p>a</p>\n"})
    store.write(folder, _entry("with-picture", body="{photo: a b.png | A caption}",
                               categories=("poetry",), tags=("night",)), draft=False)
    store.write_comments(folder, "with-picture", (_comment(),))
    store.write(folder, _entry("a-draft"), draft=True)
    store.write_template(folder, _entry("a-template"))
    _photograph(folder, "a b.png", _image("PNG"))

    into = tmp_path / "site"
    built = build(folder, _settings(), into)
    assert isinstance(built, Built)
    assert list(built.files) == _files(into)
    assert list(built.files) == sorted(built.files)
    for name in built.files:
        assert name.split("/")[0] in ROOT_OUTPUT, name
        assert not any(part.startswith(".") for part in name.split("/")), name
    assert "photographs/a b.png" in built.files
    assert web_photograph("a b.png") == "photographs/a%20b.png"
    assert "content/templates/a-template.txt" in built.files

    store.write(folder, _entry("hidden-picture", body="{photo: .hidden.jpg}"), draft=False)
    _photograph(folder, ".hidden.jpg", _image("JPEG"))
    with pytest.raises(BuildStopped, match=r"\.hidden\.jpg"):
        build(folder, _settings(), into)


# ------------------------------------------------------------------ INV-5 ---


def test_a_failed_build_changes_nothing(tmp_path):
    """INV-5: a failed build leaves `into` byte-identical and no
    .pressless-new folder; a folder holding a stray is never replaced."""
    folder = _store(tmp_path)
    store.write(folder, _entry("first", "2020-01-01 00:00:00"), draft=False)
    into = tmp_path / "site"
    build(folder, _settings(), into)
    before = _digest(into)
    new = tmp_path / "site.pressless-new"

    store.write(folder, _entry("zz-last", "1999-01-01 00:00:00",
                               body="{photo: missing.jpg}"), draft=False)
    with pytest.raises(BuildStopped, match="missing.jpg"):
        build(folder, _settings(), into)
    assert _digest(into) == before
    assert not new.exists()
    store.move_to_bin(folder, store.path_for(folder, "zz-last", draft=False))

    store.write(folder, _entry("badly-filed", categories=("Not A Slug",)), draft=False)
    with pytest.raises(BuildStopped, match="badly-filed"):
        build(folder, _settings(), into)
    assert _digest(into) == before
    assert not new.exists()
    assert not (tmp_path / "site.pressless-old").exists()

    mistaken = tmp_path / "mistaken"
    mistaken.mkdir()
    (mistaken / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SiteFolderUnusable):
        build(folder, _settings(), mistaken)
    assert (mistaken / "notes.txt").read_text(encoding="utf-8") == "mine"
    assert _files(mistaken) == ["notes.txt"]

    with pytest.raises(SiteFolderUnusable):
        build(folder, _settings(), tmp_path / "no-such-parent" / "site")


def test_an_interrupted_build_is_recovered(tmp_path):
    """INV-5, §4.8's leftovers: a stopped app leaves a new folder, an old one,
    or both, and the next build settles each."""
    folder = _store(tmp_path)
    store.write(folder, _entry("first"), draft=False)
    into = tmp_path / "site"
    build(folder, _settings(), into)
    before = _digest(into)
    new, old = tmp_path / "site.pressless-new", tmp_path / "site.pressless-old"

    # Stopped between the two renames: `into` absent, old present.
    into.rename(old)
    new.mkdir()
    (new / "index.html").write_text("half", encoding="utf-8")
    build(folder, _settings(), into)
    assert _digest(into) == before
    assert not new.exists() and not old.exists()

    # Stopped between the renames, and the next build fails: the site folder
    # still comes back, because it is renamed back before anything is tried.
    into.rename(old)
    store.write(folder, _entry("unbuildable", body="{photo: missing.jpg}"), draft=False)
    with pytest.raises(BuildStopped):
        build(folder, _settings(), into)
    assert _digest(into) == before
    assert not old.exists()
    store.move_to_bin(folder, store.path_for(folder, "unbuildable", draft=False))

    # Stopped after the second rename: both present.
    shutil.copytree(into, old)
    build(folder, _settings(), into)
    assert not old.exists()
    assert _digest(into) == before


# ------------------------------------------------------------------ INV-6 ---

_BUILD_IN_A_SUBPROCESS = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from test_builder import _settings
from pressless.builder import build
build(Path(sys.argv[3]), _settings(), Path(sys.argv[4]))
"""


def test_a_build_is_reproducible(tmp_path):
    """INV-6: two builds of an unchanged Store in the same year write
    byte-identical folders -- across hash seeds and file-creation order."""
    folder = _store(tmp_path, pages={"index": "<p>home</p>\n", "about": "<p>a</p>\n",
                                     "music": "<p>m</p>\n"})
    for n in range(PER_PAGE + 3):
        store.write(folder, _entry(
            f"entry-{n}", f"20{10 + n % 9}-0{1 + n % 9}-1{n % 9} 0{n % 9}:00:00",
            title=f"E{n}" if n % 3 else "", body=f"Line {n}\nnext\n\n{{photo: p{n % 2}.jpg}}",
            categories=("poetry", "random-thoughts")[: 1 + n % 2],
            tags=tuple(f"t{k}" for k in range(n % 5))), draft=False)
        store.write_comments(folder, f"entry-{n}", (_comment(), _comment("2", "Two")))
    _photograph(folder, "p0.jpg", _image("JPEG", (2000, 900)))
    _photograph(folder, "p1.jpg", _image("PNG", (300, 200)))

    first = tmp_path / "first"
    build(folder, _settings(), first)

    copy = tmp_path / "copy"
    for name in reversed(_files(folder)):
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / name, target)
    second = tmp_path / "second"
    env = dict(os.environ, PYTHONHASHSEED="12345")
    src = Path(builder.__file__).resolve().parents[1]
    subprocess.run(  # noqa: S603 -- the interpreter running this suite
        [sys.executable, "-c", _BUILD_IN_A_SUBPROCESS, str(src),
         str(Path(__file__).parent), str(copy), str(second)],
        check=True, env=env)
    assert _files(first) == _files(second)
    different = [name for name in _files(first)
                 if (first / name).read_bytes() != (second / name).read_bytes()]
    assert not different, f"these differ between two builds: {different}"


# ------------------------------------------------------------------ INV-7 ---


def test_content_is_the_stores_own_bytes(tmp_path):
    """INV-7: every file in content/ is byte-identical to the Store file at the
    same relative path, and nothing else is there."""
    folder = _store(tmp_path, pages={"index": "<p>home</p>\r\n<p>two</p>\r\n"})
    published = store.path_for(folder, "crlf", draft=False)
    published.parent.mkdir(exist_ok=True)
    published.write_bytes(b"Title: CRLF\r\nSlug: crlf\r\nDate: 2020-01-02 03:04:05\r\n"
                          b"Mood: unknown field\r\n\r\nOne\r\ntwo\r\n")
    comments = store.comments_path_for(folder, "crlf")
    comments.parent.mkdir(exist_ok=True)
    comments.write_bytes(b'[\r\n {"identifier": "1", "author": "A", "author_url": "",'
                         b' "date": "2020-01-02 03:04:05", "body": "x\\r\\ny",'
                         b' "parent": ""}\r\n]\r\n')
    store.write(folder, _entry("a-draft"), draft=True)
    store.write_template(folder, _entry("a-template"))
    store.write(folder, _entry("binned"), draft=False)
    store.move_to_bin(folder, store.path_for(folder, "binned", draft=False))
    _photograph(folder, "original.jpg", _image("JPEG"))

    into = tmp_path / "site"
    build(folder, _settings(), into)
    content = into / "content"
    expected = {
        "published/crlf.txt", "comments/crlf.json", "pages/index.html",
        "furniture/header.html", "furniture/navigation.html", "furniture/footer.html",
        "templates/a-template.txt",
    }
    assert set(_files(content)) == expected
    for name in expected:
        assert (content / name).read_bytes() == (folder / name).read_bytes(), name


# ------------------------------------------------------------------ INV-8 ---


def test_a_fixed_page_keeps_its_own_bytes(tmp_path):
    """INV-8: a fixed page's bytes outside its marker pairs are unchanged, and
    between them sits the filled furniture of §4.4."""
    home = ("<!DOCTYPE html><HTML>\r\n <body class=x>< p>unclosed\n"
            '    <!-- HEADER:START page="about" nonav -->\n    <!-- HEADER:END -->\n'
            "<p>after &amp; odd</P>\n")
    about = ("<html>\n"
             '  <!-- HEADER:START page="about" animate data-x="kept" -->\n'
             "  <!-- HEADER:END -->\n<main>About</main>\n"
             "  <!-- FOOTER:START -->\n  <!-- FOOTER:END -->\n</html>\n")
    plain = "<html><body>No markers {{UP}} here</body></html>\n"
    folder = _store(tmp_path, pages={"index": home, "about": about, "plain": plain})

    into = tmp_path / "site"
    build(folder, _settings(), into)

    # Bytes, not read_text: universal newlines would turn the fixture's CRLF into LF.
    built_home = (into / "index.html").read_bytes().decode("utf-8")
    start = '    <!-- HEADER:START page="about" nonav -->'
    end = "    <!-- HEADER:END -->"
    head, rest = built_home.split(start, 1)
    between, tail = rest.split(end, 1)
    assert head + start + "\n" + end + tail == home
    assert "<nav" not in built_home and "{{" not in built_home
    assert '<a class="logo reveal-load d1"' not in built_home
    assert '<a class="logo" href="index.html">' in between

    built_about = (into / "pages/about.html").read_bytes().decode("utf-8")
    assert built_about.startswith("<html>\n  <!-- HEADER:START page=\"about\" animate")
    assert built_about.endswith("  <!-- FOOTER:END -->\n</html>\n")
    assert "<main>About</main>" in built_about
    assert '<a class="logo reveal-load d1" href="../index.html">' in built_about
    assert 'class="line reveal-load d2 reveal-load d3"' in built_about
    assert ('<a href="../pages/about.html" data-nav="about" aria-current="page">About</a>'
            in built_about)
    assert built_about.count('aria-current="page"') == 1
    assert "the menu keeps this comment" in built_about
    assert f"&copy; {YEAR} " in built_about
    assert 'href="../pages/privacy.html"' in built_about
    assert "the comment the build removes" not in built_about
    assert "the comment the build removes" not in built_home
    assert "{{" not in built_about

    assert (into / "pages/plain.html").read_bytes().decode("utf-8") == plain

    broken = _store(tmp_path / "broken", pages={
        "index": "<!-- HEADER:START -->\n<p>no end</p>\n"})
    with pytest.raises(BuildStopped, match="index"):
        build(broken, _settings(), tmp_path / "broken-site")
    orphan = _store(tmp_path / "orphan", pages={"index": "<p>x</p>\n<!-- FOOTER:END -->\n"})
    with pytest.raises(BuildStopped, match="index"):
        build(orphan, _settings(), tmp_path / "orphan-site")


def test_a_generated_page_carries_the_journal_furniture(tmp_path):
    """§4.4: a generated page is filled as a marker saying page="Journal"
    would be, at its own depth."""
    folder = _store(tmp_path)
    entry = _entry("deep", title="Deep")
    store.write(folder, entry, draft=False)
    into = tmp_path / "site"
    build(folder, _settings(), into)
    page = _entry_page(into, entry).read_text(encoding="utf-8")
    up = "../" * 5
    assert f'<a href="{up}blog/index.html" data-nav="Journal" aria-current="page">' in page
    assert f'<a class="logo" href="{up}index.html">' in page
    assert f'href="{up}assets/site.css"' in page and "?v=" not in page
    assert "<title>Deep — A Journal</title>" in page


# ------------------------------------------------------------------ INV-9 ---


def _exif_with_gps(orientation: int | None = None) -> bytes:
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    gps = exif.get_ifd(0x8825)
    gps[1] = "S"
    gps[2] = (33.0, 55.0, 12.0)
    return exif.tobytes()


def test_web_copies_are_small_and_carry_nothing(tmp_path):
    """INV-9: a web copy exists for exactly the pictures unfiltered entries
    name; its format is the decoded one; a re-encoded copy fits LONGEST_SIDE
    and carries no EXIF, XMP or comment block."""
    folder = _store(tmp_path)
    xmp = (f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/'
           f'1999/02/22-rdf-syntax-ns#"><rdf:Description>{SENTINEL}</rdf:Description>'
           f"</rdf:RDF></x:xmpmeta>").encode()
    _photograph(folder, "large.jpg", _image("JPEG", (3200, 1600),
                                            exif=_exif_with_gps(6), xmp=xmp))
    _photograph(folder, "small.jpg", _image("JPEG", (40, 30), exif=_exif_with_gps(),
                                            comment=SENTINEL.encode()))
    _photograph(folder, "small.png", _image("PNG"))
    frames = [Image.new("RGB", (2400, 120), colour) for colour in ((255, 0, 0), (0, 0, 255))]
    out = io.BytesIO()
    frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=[70, 90],
                   loop=0, comment=SENTINEL.encode())
    _photograph(folder, "moving.gif", out.getvalue())
    _photograph(folder, "x.gif", _image("JPEG"))
    _photograph(folder, "unnamed.jpg", _image("JPEG"))
    _photograph(folder, "filtered-only.jpg", _image("JPEG"))
    body = "\n\n".join(f"{{photo: {name}}}" for name in
                       ("large.jpg", "small.jpg", "small.png", "moving.gif", "x.gif"))
    store.write(folder, _entry("pictures", body=body), draft=False)
    store.write(folder, _entry("again", body="{photo: small.png}"), draft=False)
    store.write(folder, _entry("prompted", body="{photo: filtered-only.jpg}",
                               tags=("dailyprompt-1",)), draft=False)
    # A block mark inside a quotation stays literal (PRESS-0004 §4.2).
    store.write(folder, _entry("quoted", body="> {photo: unnamed.jpg}"), draft=False)

    for name in ("large.jpg", "small.jpg", "moving.gif"):
        assert SENTINEL.encode() in store.photograph_path_for(folder, name).read_bytes(), (
            f"the fixture {name} does not carry the sentinel, so this test proves nothing")
    with Image.open(store.photograph_path_for(folder, "small.jpg")) as original:
        assert len(original.getexif()) > 0, "the fixture carries no EXIF to strip"

    into = tmp_path / "site"
    built = build(folder, _settings(), into)
    photographs = into / "photographs"
    assert sorted(p.name for p in photographs.iterdir()) == [
        "large.jpg", "moving.gif", "small.jpg", "small.png", "x.gif"]

    with Image.open(photographs / "large.jpg") as large:
        assert large.format == "JPEG"
        assert max(large.size) == LONGEST_SIDE
        assert large.size[1] > large.size[0], "the orientation tag was not applied"
        assert len(large.getexif()) == 0
    with Image.open(photographs / "small.jpg") as small:
        assert small.size == (40, 30), "a small picture was enlarged"
        assert len(small.getexif()) == 0
        assert "comment" not in small.info
    for name in ("large.jpg", "small.jpg", "moving.gif"):
        data = (photographs / name).read_bytes()
        assert SENTINEL.encode() not in data, name
        assert b"http://ns.adobe.com/xap/1.0/" not in data, name
    with Image.open(photographs / "small.png") as png:
        assert png.format == "PNG"
    with Image.open(photographs / "moving.gif") as gif:
        assert gif.format == "GIF"
        assert gif.n_frames == 2
        assert max(gif.size) <= LONGEST_SIDE
        assert "comment" not in gif.info
        durations = []
        for index in range(gif.n_frames):
            gif.seek(index)
            durations.append(gif.info.get("duration"))
        assert durations == [70, 90]
    with Image.open(photographs / "x.gif") as renamed:
        assert renamed.format == "JPEG"
    assert "photographs/small.png" in built.files

    _photograph(folder, "broken.jpg", b"this is not a picture")
    store.write(folder, _entry("broken", body="{photo: broken.jpg}"), draft=False)
    with pytest.raises(BuildStopped, match="broken.jpg"):
        build(folder, _settings(), into)

    store.move_to_bin(folder, store.path_for(folder, "broken", draft=False))
    _photograph(folder, "picture.bmp", _image("BMP"))
    store.write(folder, _entry("bitmap", body="{photo: picture.bmp}"), draft=False)
    with pytest.raises(BuildStopped, match="picture.bmp"):
        build(folder, _settings(), into)


def test_a_preview_writes_no_web_copies(tmp_path):
    """§4.1: `photo_src` given, no web copy is written and its address is used
    as given."""
    folder = _store(tmp_path)
    _photograph(folder, "a.jpg", _image("JPEG"))
    entry = _entry("pictured", body="{photo: a.jpg}")
    store.write(folder, entry, draft=False)
    into = tmp_path / "preview"
    build(folder, _settings(), into, photo_src=lambda name: f"/preview/{name}")
    assert not (into / "photographs").exists()
    assert 'src="/preview/a.jpg"' in _entry_page(into, entry).read_text(encoding="utf-8")

    site = tmp_path / "site"
    build(folder, _settings(), site)
    assert 'src="../../../../../photographs/a.jpg"' in _entry_page(
        site, entry).read_text(encoding="utf-8")


# ----------------------------------------------------------------- INV-10 ---


def test_writing_renders_through_marks(tmp_path, monkeypatch):
    """INV-10: an entry body in a page is marks.render's output, and a comment
    body is marks.to_html's output over plain Text."""
    folder = _store(tmp_path)
    entry = _entry("rendered", body="*bold* words")
    store.write(folder, entry, draft=False)
    store.write_comments(folder, entry.slug, (_comment(body="*one* <b>\nline two\n\nnext"),))

    monkeypatch.setattr(marks, "render", lambda body, photo_src: SENTINEL)
    into = tmp_path / "site"
    build(folder, _settings(), into)
    page = _entry_page(into, entry).read_text(encoding="utf-8")
    assert SENTINEL in page
    assert "<em>bold</em>" not in page and "<strong>bold</strong>" not in page

    monkeypatch.undo()
    build(folder, _settings(), into)
    page = _entry_page(into, entry).read_text(encoding="utf-8")
    assert "<p>*one* &lt;b&gt;<br>\nline two</p>\n<p>next</p>" in page


# ----------------------------------------------------------------- INV-11 ---

_ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses", "datetime", "fnmatch", "html", "os", "pathlib", "re", "shutil",
    "urllib", "urllib.parse",               # percent-encoding an address -- never fetching
    "PIL", "PIL.Image", "PIL.ImageOps", "PIL.ImageSequence",
    "pressless", "pressless.marks", "pressless.settings", "pressless.store",
}


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def test_the_builder_imports_only_what_it_may():
    """INV-11: builder.py imports only what the allowlist names, compared by
    full dotted name, so `urllib.parse` is admitted and `urllib.request` is not."""
    tree = ast.parse(Path(builder.__file__).read_text(encoding="utf-8"))
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
                assert alias.name in _ALLOWED_IMPORTS, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import escapes the allowlist"
            seen.add(node.module)
            assert node.module in _ALLOWED_IMPORTS, node.module
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}"
                if _is_module(dotted):
                    seen.add(dotted)
                    assert dotted in _ALLOWED_IMPORTS, dotted
    assert "PIL.Image" in seen and "pressless.marks" in seen, (
        f"the walk did not see the Builder's own imports: {sorted(seen)!r}")


# ----------------------------------------------------------------- INV-12 ---


def test_dates_do_not_depend_on_the_system(tmp_path):
    """INV-12: an entry dated 2024-03-05 shows `5 March 2024`, under the C
    locale, and builder.py holds no `%-` directive."""
    folder = _store(tmp_path)
    entry = _entry("dated", "2024-03-05 09:00:00")
    store.write(folder, entry, draft=False)
    saved = locale.setlocale(locale.LC_TIME)
    try:
        locale.setlocale(locale.LC_TIME, "C")
        into = tmp_path / "site"
        build(folder, _settings(), into)
    finally:
        locale.setlocale(locale.LC_TIME, saved)
    page = _entry_page(into, entry).read_text(encoding="utf-8")
    assert '<time datetime="2024-03-05">5 March 2024</time>' in page
    assert "<h1>5 March 2024</h1>" in page, "an untitled entry's heading is its date"
    assert "%-" not in Path(builder.__file__).read_text(encoding="utf-8")


# ----------------------------------------------------------------- INV-13 ---


def test_the_sitemap_lists_what_readers_find(tmp_path):
    """INV-13: sitemap.xml and robots.txt are §4.9's."""
    folder = _store(tmp_path, pages={"index": "<p>h</p>\n", "zeta": "<p>z</p>\n",
                                     "about": "<p>a</p>\n"})
    store.write(folder, _entry("older", "2019-02-03 00:00:00"), draft=False)
    store.write(folder, _entry("newer", "2020-11-12 00:00:00"), draft=False)
    store.write(folder, _entry("prompted", "2021-01-01 00:00:00",
                               tags=("dailyprompt-9",)), draft=False)
    into = tmp_path / "site"
    build(folder, _settings(site_address="https://example.org/"), into)

    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.parse(into / "sitemap.xml").getroot()  # noqa: S314 -- a file this test built
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
    rows = [(url.findtext("s:loc", None, ns), url.findtext("s:lastmod", None, ns))
            for url in root.findall("s:url", ns)]
    assert rows == [
        ("https://example.org/", None),
        ("https://example.org/pages/about.html", None),
        ("https://example.org/pages/zeta.html", None),
        ("https://example.org/blog/index.html", None),
        ("https://example.org/blog/archive/index.html", None),
        ("https://example.org/blog/2020/11/12/newer/index.html", "2020-11-12"),
        ("https://example.org/blog/2019/02/03/older/index.html", "2019-02-03"),
    ]
    assert (into / "robots.txt").read_text(encoding="utf-8") == (
        "# Everything here is meant to be found.\n"
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "Sitemap: https://example.org/sitemap.xml\n"
    )
