# PRESS-0210: a folder of web pages comes into an empty Store. The pure parts:
# what a ZIP may hold, how a folder is read, and what is written.
#
# Why this exists: docs/specs/PRESS-0210-folder-of-pages.md §§ 4.1 and 4.3 to
# 4.9. The wizard's routes are in tests/test_importing.py, and the repository
# route in tests/test_takein.py.
from __future__ import annotations

import io
import os
import posixpath
import re
import stat
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from _face_session import Browser
from PIL import Image
from test_builder import _settings

import pressless_import
from pressless import builder, face, look, look_screen, menu, store
from pressless_import import ImportStopped


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (4, 3), "teal").save(out, "PNG")
    return out.getvalue()


PDF = b"%PDF-1.4 words\n"
HEADER = '<header><a href="{up}index.html">Site</a></header>'
FOOTER = "<footer><p>Mine</p></footer>"


def _page(body: str, *, head: str = "<title>A page</title>") -> str:
    return f"<!doctype html>\n<html>\n<head>{head}</head>\n<body>\n{body}\n</body>\n</html>\n"


def _laid_out(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    folder = tmp_path / "held"
    for path, content in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return folder


def _brought(tmp_path: Path, files: dict[str, str | bytes], **given):
    into = tmp_path / "site"
    into.mkdir()
    return into, pressless_import.bring_in_folder(_laid_out(tmp_path, files), into, **given)


def _built(tmp_path: Path, into: Path) -> Path:
    site = tmp_path / "built"
    builder.build(into, _settings(), site)
    return site


def _said(brought) -> str:
    """Everything the Report says, as one text."""
    report = brought.report
    return "\n".join((*(f"{where}: {what}" for where, what in report.unfetched),
                      *(f"{row.slug}: {row.what}" for row in report.dropped)))


class _Addresses(HTMLParser):
    """Every address a built page names, in § 4.5's places."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src", "poster") and value:
                self.found.append(value)
            elif name == "srcset" and value:
                self.found += [piece.split()[0] for piece in value.split(",")]
            elif name == "style" and value:
                self.found += re.findall(r"url\(['\"]?([^'\")]+)", value)


def _unresolved(site: Path, relative: str) -> list[str]:
    """Each address on the built page `relative` naming no built file."""
    reader = _Addresses()
    reader.feed((site / relative).read_text(encoding="utf-8"))
    missing = []
    for address in reader.found:
        parts = urlsplit(address)
        if parts.scheme or parts.netloc or not parts.path:
            continue
        place = posixpath.normpath(posixpath.join(posixpath.dirname(relative),
                                                  unquote(parts.path)))
        if not (site / place).is_file():
            missing.append(address)
    return missing


# ----------------------------------------------------------------- INV-2 ---


@pytest.mark.parametrize("bad", ["../x.html", "/abs.html", "a\\b.html"])
def test_a_bad_zip_writes_nothing(tmp_path, bad):
    """INV-2. Breaks when members are checked as they are unpacked."""
    # Written under a stand-in, then the stored bytes changed: on Windows,
    # zipfile would write the backslash as a slash.
    stand_in = "x" * len(bad)
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w") as made:
        made.writestr("good.html", "<p>Good</p>")
        made.writestr(stand_in, "<p>Bad</p>")
    source = tmp_path / "held.zip"
    source.write_bytes(held.getvalue().replace(stand_in.encode(), bad.encode()))
    into = tmp_path / "import" / "folder"
    with pytest.raises(ImportStopped):
        pressless_import.unpack_folder(source, into, lambda: 10**9)
    assert not into.exists()


def test_a_zip_holding_a_link_writes_nothing(tmp_path):
    """INV-2's link."""
    source = tmp_path / "held.zip"
    link = zipfile.ZipInfo("link.html")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "w") as made:
        made.writestr("good.html", "<p>Good</p>")
        made.writestr(link, "/etc/passwd")
    into = tmp_path / "folder"
    with pytest.raises(ImportStopped):
        pressless_import.unpack_folder(source, into, lambda: 10**9)
    assert not into.exists()


def test_a_zip_that_is_not_one_or_does_not_fit_writes_nothing(tmp_path):
    """§ 4.1 and § 6: not a ZIP, too many members, or more than the room."""
    into = tmp_path / "folder"
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    with pytest.raises(ImportStopped):
        pressless_import.unpack_folder(junk, into, lambda: 10**9)
    fits = tmp_path / "fits.zip"
    with zipfile.ZipFile(fits, "w") as made:
        made.writestr("a.html", "x" * 100)
    with pytest.raises(ImportStopped):
        pressless_import.unpack_folder(fits, into, lambda: 99)
    assert not into.exists()


def test_a_zip_too_full_is_refused(tmp_path, monkeypatch):
    """§ 4.1: MEMBERS_MOST."""
    monkeypatch.setattr("pressless_import._folder.MEMBERS_MOST", 1)
    source = tmp_path / "held.zip"
    with zipfile.ZipFile(source, "w") as made:
        made.writestr("a.html", "a")
        made.writestr("b.html", "b")
    with pytest.raises(ImportStopped):
        pressless_import.unpack_folder(source, tmp_path / "folder", lambda: 10**9)


def test_unpacking_drops_the_one_top_folder_and_answers_what_it_left(tmp_path, monkeypatch):
    """§ 4.1: a zipped folder's top folder goes, and a member too large, with a
    segment the Store refuses, or folding to an earlier one's path is not
    unpacked, and is returned with why."""
    monkeypatch.setattr(builder, "FILE_LARGEST", 50)
    source = tmp_path / "held.zip"
    with zipfile.ZipFile(source, "w") as made:
        made.writestr("site/", "")
        made.writestr("site/index.html", "<p>Home</p>")
        made.writestr("site/sub/Page.html", "<p>One</p>")
        made.writestr("site/sub/page.html", "<p>Two</p>")
        made.writestr("site/big.pdf", "x" * 51)
        made.writestr("site/con/x.txt", "windows refuses")
    into = tmp_path / "folder"
    left = dict(pressless_import.unpack_folder(source, into, lambda: 10**9))
    assert (into / "index.html").is_file() and (into / "sub/Page.html").is_file()
    assert set(left) == {"sub/page.html", "big.pdf", "con/x.txt"}, left
    assert not (into / "big.pdf").exists()
    assert [path.name for path in (into / "sub").iterdir()] == ["Page.html"]
    assert (into / "sub/Page.html").read_text(encoding="utf-8") == "<p>One</p>"
    assert all(left.values())


# ---------------------------------------------------------------- INV-10 ---


def test_every_file_is_accounted_for(tmp_path):
    """INV-10: a fixture of every row of § 4.3's table. Breaks when a kind is
    skipped without being added to `left`."""
    files = {
        "index.html": _page('<link rel="stylesheet" href="a.css">'
                            '<img src="logo.svg"><script src="run.js"></script>'
                            '<img src="pic.png">'),
        "sub/page.htm": _page("<p>Two</p>"),
        "google123.html": "google-site-verification: google123.html",
        "yandex_1.html": "<html>yandex</html>",
        "words-only.html": "No markup here",
        "pic.png": _png(),
        "doc.pdf": PDF,
        "font.woff2": b"wOF2 rest",
        "a.css": '@import "b.css";\nbody{}',
        "b.css": "p{}",
        "lonely.css": "p{}",
        "logo.svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
        "unused.svg": "<svg/>",
        "run.js": "var a;",
        "unused.js": "var b;",
        "tool.exe": b"MZ",
        "CNAME": "example.org\n",
        ".hidden": "x",
        ".git/config": "x",
        "404.html": "<p>Lost</p>",
        "sub/404.html": _page("<p>A page here</p>"),
    }
    folder = _laid_out(tmp_path, files)
    found = pressless_import.read_folder(folder)
    left = [path for path, _why in found.left]
    together = [*found.pages, *found.photographs, *found.files, *found.inside_pages,
                *found.style, *left]
    assert sorted(together) == sorted(files)
    assert set(found.pages) == {"index.html", "sub/page.htm", "sub/404.html"}
    assert found.photographs == ("pic.png",)
    assert set(found.files) == {"doc.pdf", "font.woff2"}
    assert set(found.style) == {"a.css", "b.css"}
    assert set(found.inside_pages) == {"logo.svg", "run.js"}
    assert set(left) == {"google123.html", "yandex_1.html", "words-only.html", "lonely.css",
                         "unused.svg", "unused.js", "tool.exe", "CNAME", ".hidden",
                         ".git/config", "404.html"}
    assert all(why for _path, why in found.left)
    assert set(found.roots) == {"index.html", "sub", "pic.png", "doc.pdf", "font.woff2",
                                "a.css", "b.css", "logo.svg", "run.js"}


@pytest.mark.skipif(os.name == "nt", reason="the fixture is what Windows cannot hold")
def test_a_path_the_store_would_refuse_is_left(tmp_path):
    """§ 4.3: a repository's paths meet no unpack_folder, so read_folder makes
    the same tests."""
    folder = _laid_out(tmp_path, {"index.html": _page("<p>Home</p>"),
                                  "con/x.txt": "windows refuses"})
    found = pressless_import.read_folder(folder)
    assert [path for path, _why in found.left] == ["con/x.txt"]


@pytest.mark.parametrize(("files", "built"), [
    ({"_config.yml": "x", "index.html": "<p>Home</p>"}, True),
    ({"_layouts/a.html": "<p>A</p>", "index.html": "<p>Home</p>"}, True),
    ({"index.html": "---\ntitle: Home\n---\n<p>Home</p>"}, True),
    ({".nojekyll": "", "index.html": "---\ntitle: Home\n---\n<p>Home</p>"}, False),
    ({"index.html": "<p>Home</p>"}, False),
    ({"index.html": "---- a rule\n<p>Home</p>"}, False),
])
def test_what_a_tool_builds_from_is_named(tmp_path, files, built):
    """§ 4.3's `built_by_a_tool`."""
    assert pressless_import.read_folder(_laid_out(tmp_path, files)).built_by_a_tool is built


# ----------------------------------------------------------------- INV-3 ---


def test_every_address_resolves_once_built(tmp_path):
    """INV-3. Breaks when addresses are rewritten without the page's new depth,
    or a build publishes only what a section's field names."""
    pic = _png()
    root = _page(
        '<a href="about.html#team">One</a> <a href="team/">Two</a> <a href="about">Three</a>'
        ' <a href="/about.html?from=home">Four</a> <a href="/repo/team/index.html">Five</a>'
        ' <a href="https://example.org/about.html">Away</a> <a href="#here">Here</a>'
        '<div class="odd"><img src="images/a%20b.png" alt="Picture">'
        ' <a href="/repo/docs/guide.pdf">Guide</a></div>'
        '<img srcset="images/a%20b.png 1x, /images/c.png 2x" src="images/c.png" alt="">'
        '<video poster="images/c.png"></video>'
        '<div style="background: url(images/c.png)">Styled</div>'
        '<style>.x { background: url("images/c.png"); }</style>')
    sub = _page('<a href="../index.html">Home</a> <a href="./">Team</a>'
                '<div><img src="../images/c.png" alt=""><a href="/docs/guide.pdf">Guide</a></div>')
    into, _brought_in = _brought(tmp_path, {
        "index.html": root, "about.html": _page("<p>About</p>"), "team/index.html": sub,
        "images/a b.png": pic, "images/c.png": pic, "docs/guide.pdf": PDF})
    site = _built(tmp_path, into)
    for relative in ("index.html", "pages/about.html", "pages/team.html"):
        assert _unresolved(site, relative) == [], relative
    built = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="pages/about.html#team"' in built and 'href="pages/team.html"' in built
    assert 'href="pages/about.html?from=home"' in built
    assert 'href="https://example.org/about.html"' in built and 'href="#here"' in built
    assert 'src="photographs/a%20b.png"' in built and 'href="files/guide.pdf"' in built
    assert "url(photographs/c.png)" in built and 'url("photographs/c.png")' in built
    assert (site / "photographs/c.png").is_file() and (site / "files/guide.pdf").is_file()
    team = (site / "pages/team.html").read_text(encoding="utf-8")
    assert 'href="../index.html"' in team and 'src="../photographs/c.png"' in team


def test_an_address_to_what_was_not_carried_stays_on_its_path_and_is_listed(tmp_path):
    """§ 4.5's last row, from the page's new depth."""
    into, brought = _brought(tmp_path, {
        "index.html": _page("<p>Home</p>"),
        "about.html": _page('<a href="tool.exe">Tool</a> <a href="gone.html">Gone</a>'),
        "tool.exe": b"MZ"})
    about = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "about"))
    assert 'href="../tool.exe"' in about and 'href="../gone.html"' in about
    assert "tool.exe" in _said(brought) and "gone.html" in _said(brought)


def test_a_page_holding_a_base_keeps_its_addresses(tmp_path):
    """§ 4.5: `<base>` changes what every address means, so none is rewritten."""
    into, brought = _brought(tmp_path, {
        "index.html": _page('<a href="about.html">About</a>',
                            head='<base href="https://example.org/"><title>Home</title>'),
        "about.html": _page("<p>About</p>")})
    index = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "index"))
    assert 'href="about.html"' in index
    assert "pages/index" in _said(brought)


def test_a_page_is_named_as_the_spec_says(tmp_path):
    """§ 4.4, and § 4.10's forwards: each old path not a new one."""
    into, brought = _brought(tmp_path, {
        "index.html": _page("<p>Home</p>"), "index.htm": _page("<p>Twin</p>"),
        "about.html": _page("<p>One</p>"), "team/index.html": _page("<p>Two</p>"),
        "blog/first post.htm": _page("<p>Three</p>"), "team.html": _page("<p>Four</p>"),
        "pic.png": _png(), "sub/pic.png": _png()})
    assert set(store.list_html(into, store.PAGES_FOLDER)) == {
        "index", "index-2", "about", "team", "team-2", "blog-first-post"}
    assert store.read_address_forwards(into) == {
        "index.htm": "index-2", "about.html": "about", "team.html": "team",
        "team/index.html": "team-2", "blog/first post.htm": "blog-first-post"}
    assert set(store.list_photographs(into)) == {"pic.png", "sub-pic.png"}
    report = brought.report
    assert ("sub/pic.png", "sub-pic.png") in report.renamed_photographs
    assert ("team", "team-2") in report.renamed_slugs
    assert ("about.html", "about") in report.moved


def test_with_no_index_the_front_page_is_chosen_and_listed(tmp_path):
    """§ 4.4: `home`, else `default`, else the first by path."""
    into, brought = _brought(tmp_path, {
        "about.html": _page("<p>About</p>"), "home.html": _page("<p>Home</p>")})
    assert "Home" in store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "index"))
    assert "home.html" in _said(brought)


# ----------------------------------------------------------------- INV-6 ---


NAV = ('<nav class="primary"><a {current}href="{up}index.html">Home</a>'
       '<a href="{up}{about}">About</a></nav>')


def test_shared_furniture_is_parted_out(tmp_path):
    """INV-6. Breaks when pages are compared before their addresses are written
    the same."""
    def page(up: str, current: str, words: str) -> str:
        nav = NAV.format(up=up, about="sub/about.html", current=current)
        return _page(f'<header class="site">{HEADER.format(up=up)[8:-9]}\n{nav}</header>\n'
                     f"<p>{words}</p>\n{FOOTER}")

    into, brought = _brought(tmp_path, {
        "index.html": page("", 'class="active" ', "Home words"),
        "sub/about.html": page("../", "", "About words")})

    header = store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "header"))
    footer = store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "footer"))
    navigation = store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "navigation"))
    assert '<a href="{{UP}}index.html">Site</a>' in header and "{{NAVIGATION}}" in header
    assert "<nav" not in header and "Mine" in footer
    assert 'data-nav="Home"' in navigation and 'data-nav="sub-about"' in navigation
    assert "active" not in navigation
    assert [word for word, _address in menu.links(navigation)] == ["Home", "About"]

    for name in ("index", "sub-about"):
        text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, name))
        assert "<header" not in text and "<footer" not in text and "<nav" not in text
        assert "HEADER:START" in text and "FOOTER:START" in text
    assert 'page="Home"' in store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "index"))
    assert "aria-current" in _said(brought)

    site = _built(tmp_path, into)
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="pages/sub-about.html"' in index and "Mine" in index
    assert re.search(r'data-nav="Home"[^>]*aria-current="page"', index)
    about = (site / "pages/sub-about.html").read_text(encoding="utf-8")
    assert 'href="../index.html"' in about and 'href="../pages/sub-about.html"' in about
    assert re.search(r'data-nav="sub-about"[^>]*aria-current="page"', about)
    assert _unresolved(site, "index.html") == []
    assert _unresolved(site, "pages/sub-about.html") == []


def test_a_menu_beside_the_header_joins_its_marker_pair(tmp_path):
    """§ 4.8: only whitespace between them, on the matching side."""
    nav = '<nav><a href="index.html">Home</a></nav>'
    into, _b = _brought(tmp_path, {
        "index.html": _page(f"<header>Site</header>\n{nav}\n<p>One</p>"),
        "two.html": _page(f"<header>Site</header>\n{nav}\n<p>Two</p>")})
    header = store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "header"))
    assert header.index("</header>") < header.index("{{NAVIGATION}}")
    text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "two"))
    assert "<nav" not in text and "<header" not in text


def test_a_menu_with_no_header_is_the_header_file(tmp_path):
    """§ 4.8: a shared menu with no shared header."""
    nav = '<nav><a href="index.html">Home</a></nav>'
    into, _b = _brought(tmp_path, {
        "index.html": _page(f"{nav}\n<p>One</p>"), "two.html": _page(f"{nav}\n<p>Two</p>")})
    assert store.read_html(store.html_path_for(
        into, store.FURNITURE_FOLDER, "header")).strip() == "{{NAVIGATION}}"
    site = _built(tmp_path, into)
    assert "<nav" in (site / "pages/two.html").read_text(encoding="utf-8")


def test_a_menu_elsewhere_stays_in_each_page_and_is_listed(tmp_path):
    """§ 4.8: the Menu screen then edits nothing the site shows."""
    nav = '<nav><a href="index.html">Home</a></nav>'
    into, brought = _brought(tmp_path, {
        "index.html": _page(f"<header>Site</header><p>Between</p>{nav}<p>One</p>"),
        "two.html": _page(f"<header>Site</header><p>Between</p>{nav}<p>Two</p>")})
    assert "<nav" in store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "two"))
    assert "navigation:" in _said(brought)


def test_a_menu_pressless_cannot_edit_is_kept_and_listed(tmp_path):
    """§ 4.8: `menu.links` calls it Unusual."""
    nav = '<nav><ul><li><a href="index.html">Home</a></li></ul></nav>'
    into, brought = _brought(tmp_path, {
        "index.html": _page(f"<header>Site{nav}</header><p>One</p>"),
        "two.html": _page(f"<header>Site{nav}</header><p>Two</p>")})
    navigation = store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "navigation"))
    assert "<ul>" in navigation
    with pytest.raises(menu.Unusual):
        menu.links(navigation)
    assert "navigation:" in _said(brought)


def test_a_site_sharing_nothing_gets_the_starters_files(tmp_path):
    """§ 4.8: furniture a build needs, and that is listed."""
    into, brought = _brought(tmp_path, {
        "index.html": _page("<p>One</p>"), "two.html": _page("<p>Two</p>")})
    for name in ("header", "footer", "navigation"):
        assert store.html_path_for(into, store.FURNITURE_FOLDER, name).is_file(), name
    site = _built(tmp_path, into)
    assert "<header" not in (site / "index.html").read_text(encoding="utf-8")
    assert "header" in _said(brought)


# ----------------------------------------------------------------- INV-7 ---


def test_a_different_header_stays_in_its_page(tmp_path):
    """INV-7. Breaks when a page's header is replaced because it has one."""
    shared, other = "<header>Shared</header>", "<header>Its own</header>"
    into, brought = _brought(tmp_path, {
        "a.html": _page(f"{shared}<p>A</p>"), "b.html": _page(f"{shared}<p>B</p>"),
        "c.html": _page(f"{other}<p>C</p>"), "index.html": _page(f"{shared}<p>D</p>")})
    assert "Shared" in store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "header"))
    kept = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "c"))
    assert other in kept and "HEADER:START" not in kept
    assert "HEADER:START" in store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "a"))
    assert "pages/c" in _said(brought)


def test_a_header_inside_an_article_is_no_site_header(tmp_path):
    """§ 4.8: not inside `main`, `article` or `section`."""
    block = "<article><header>A heading</header><p>Words</p></article>"
    into, _b = _brought(tmp_path, {"index.html": _page(block), "two.html": _page(block)})
    text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "two"))
    assert "A heading" in text and "HEADER:START" not in text


# ----------------------------------------------------------------- INV-8 ---


def test_stylesheets_become_the_style_code(tmp_path):
    """INV-8. Breaks when `look.save` is called, which replaces it with a
    Pressless look."""
    pic = _png()
    into, brought = _brought(tmp_path, {
        "index.html": _page("<p>Home</p>", head=(
            '<link rel="stylesheet" href="css/a.css">'
            '<link rel="stylesheet" media="print" href="css/b.css"><title>Home</title>')),
        "two.html": _page("<p>Two</p>", head=(
            '<link rel="stylesheet" href="css/a.css"><title>Two</title>')),
        "css/a.css": ('@charset "utf-8";\n@import "c.css";\n'
                      '@import url("https://fonts.example/f.css");\n'
                      ".a { background: url(../images/pic.png); }\n"),
        "css/b.css": '@import "https://fonts.example/p.css";\n.b { color: red; }\n',
        "css/c.css": ".c { color: blue; }\n",
        "images/pic.png": pic})

    code = store.read_style_code(into)
    assert code.startswith("@import")
    assert '@import url("https://fonts.example/f.css");' in code
    assert re.search(r'@import "https://fonts.example/p.css"\s+print;', code)
    assert "@charset" not in code
    assert code.index(".c {") < code.index(".a {") < code.index(".b {")
    assert re.search(r"@media print\s*\{[^}]*\.b \{", code)
    assert "url(../photographs/pic.png)" in code
    assert "css/b.css" in brought.report.sheets_for_some
    assert "css/a.css" not in brought.report.sheets_for_some

    assert look.read(into) is None
    assert builder.stylesheets(into) == (builder.STYLE_CODE,)
    served = face.serve(into)
    look_screen.register(served, into)
    try:
        status, _headers, shown = Browser(served).request("GET", look_screen.ADDRESS)
    finally:
        served.stop()
    assert status == 200 and 'name="layout"' in shown, "§ 4.4 state 2: a layout picker"
    assert store.read_style_code(into) == code, "showing the screen changes nothing"
    site = _built(tmp_path, into)
    assert (site / "photographs/pic.png").is_file(), "the style code names it"
    index = (site / "index.html").read_text(encoding="utf-8")
    assert index.count('rel="stylesheet"') == 1 and 'href="look/style.css"' in index
    two = (site / "pages/two.html").read_text(encoding="utf-8")
    assert 'href="../look/style.css"' in two
    assert (site / "look/style.css").read_text(encoding="utf-8") == code


def test_a_site_with_no_stylesheet_has_empty_style_code(tmp_path):
    """§ 4.7: an empty file, so `builder.stylesheets` answers the one sheet."""
    into, _b = _brought(tmp_path, {"index.html": _page("<p>Home</p>")})
    assert store.read_style_code(into) == ""
    assert builder.stylesheets(into) == (builder.STYLE_CODE,)


def test_a_style_elements_import_reaches_the_style_code(tmp_path):
    """§ 4.3's "linked from a page": an older site's `<style>@import`. The page
    then links the style code, and keeps the rest of its element."""
    into, brought = _brought(tmp_path, {"index.html": _page("<p>H</p>", head=(
        "<style>@import url(a.css); p { color: red; }</style>")), "a.css": ".a { margin: 0; }"})
    assert ".a {" in store.read_style_code(into)
    assert "a.css" not in dict(brought.report.unfetched)
    index = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "index"))
    assert "@import" not in index and "p { color: red; }" in index
    assert index.index('href="look/style.css"') < index.index("<style>")


def test_a_front_page_is_found_whatever_its_capitals(tmp_path):
    """§ 4.4, for a site made on Windows; its old address still forwards."""
    into, _b = _brought(tmp_path, {"ABOUT.HTM": _page("<p>About</p>"),
                                   "INDEX.HTM": _page("<p>Home</p>")})
    assert "Home" in store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "index"))
    assert store.read_address_forwards(into) == {"ABOUT.HTM": "about", "INDEX.HTM": "index"}


def test_css_that_only_looks_like_an_address_is_left_alone(tmp_path):
    """§ 4.7: a comment and a string are not addresses or rules."""
    css = ('/* @import "gone.css"; url(gone.png) */\n'
           '.a::after { content: "url(gone.png) @import"; }\n')
    into, _b = _brought(tmp_path, {
        "index.html": _page("<p>H</p>", head='<link rel="stylesheet" href="a.css">'),
        "a.css": css})
    assert store.read_style_code(into).strip() == css.strip()


# ----------------------------------------------------------------- INV-9 ---


def test_scripts_and_svgs_are_carried_inside_pages(tmp_path):
    """INV-9. Breaks when `builder._FILE_KINDS` gains them, reversing PRESS-0197
    § 3 decision 1."""
    svg = "<svg xmlns='http://www.w3.org/2000/svg'><circle r='1'/></svg>"
    into, brought = _brought(tmp_path, {
        "index.html": _page(
            '<img src="pic.svg" alt="A picture"><object data="obj.svg"></object>'
            '<script type="module" src="mod.js"></script>'
            '<script src="closes.js"></script>'
            '<script defer src="later.js"></script><p>Last words</p>',
            head='<script src="first.js"></script><title>Home</title>'),
        "first.js": "var first = 1;", "later.js": "var later = 2;",
        "closes.js": "document.write('</script>');", "mod.js": "export const a = 1;",
        "unused.js": "var unused;", "pic.svg": svg, "obj.svg": svg})
    index = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "index"))
    assert "<script>var first = 1;</script>" in index
    assert index.index("var first") < index.index("</head>")
    assert index.index("Last words") < index.index("var later") < index.index("</body>")
    assert 'src="later.js"' not in index and 'src="first.js"' not in index
    assert 'src="data:image/svg+xml;base64,' in index
    assert 'src="closes.js"' in index and 'src="mod.js"' in index
    found_left = dict(brought.report.unfetched)
    assert {"closes.js", "mod.js", "obj.svg", "unused.js"} <= set(found_left)
    assert set(brought.report.inside_pages) == {"first.js", "later.js", "pic.svg"}
    held = store.list_files(into)
    assert not [name for name in held if name.endswith((".js", ".svg"))]


def test_a_large_svg_is_left(tmp_path, monkeypatch):
    """§ 4.6: SVG_LARGEST."""
    monkeypatch.setattr("pressless_import._folder.SVG_LARGEST", 10)
    folder = _laid_out(tmp_path, {"index.html": _page('<img src="pic.svg">'),
                                  "pic.svg": "<svg>" + "x" * 10 + "</svg>"})
    assert "pic.svg" in dict(pressless_import.read_folder(folder).left)


# ---------------------------------------------------------------- INV-11 ---


def test_a_stop_leaves_the_store_empty(tmp_path, monkeypatch):
    """INV-11. Breaks when files are written straight into the site's folder."""
    files = {"index.html": _page("<p>Home</p>"), "pic.png": _png()}
    held = _laid_out(tmp_path, files)
    into = tmp_path / "site"
    into.mkdir()

    def refuses(*args, **kwargs):
        raise store.StoreError("the templates were refused")

    monkeypatch.setattr("pressless.templates.seed", refuses)
    with pytest.raises(ImportStopped):
        pressless_import.bring_in_folder(held, into)
    assert not store.holds_a_site(into)
    assert not (into / "import" / "work").exists()
    assert (held / "pic.png").is_file(), "a file moved is moved back"


def test_a_stop_during_the_moves_finishes_next_start(tmp_path, monkeypatch):
    """INV-11: a close during the moves; the next start finishes them."""
    held = _laid_out(tmp_path, {"index.html": _page("<p>Home</p>")})
    into = tmp_path / "site"
    (into / "import").mkdir(parents=True)
    target = into / "import" / "folder"
    held.rename(target)

    real = pressless_import._folder.finish

    def stops(_into):
        return "the moves stopped"

    monkeypatch.setattr("pressless_import._folder.finish", stops)
    with pytest.raises(ImportStopped):
        pressless_import.bring_in_folder(target, into)
    assert (into / "import" / "moving").exists()
    assert not store.holds_a_site(into)

    assert real(into) is None
    assert store.list_html(into, store.PAGES_FOLDER) == ("index",)
    assert not (into / "import" / "moving").exists()
    assert not target.exists(), "finish deletes the folder"


def test_a_store_holding_a_site_is_refused(tmp_path):
    """INV-1's second half, here too."""
    into = tmp_path / "site"
    (into / store.PAGES_FOLDER).mkdir(parents=True)
    (into / store.PAGES_FOLDER / "index.html").write_text("<p>Mine</p>", encoding="utf-8")
    with pytest.raises(ImportStopped):
        pressless_import.bring_in_folder(
            _laid_out(tmp_path, {"index.html": _page("<p>Home</p>")}), into)
    assert (into / store.PAGES_FOLDER / "index.html").read_text(encoding="utf-8") == "<p>Mine</p>"


def test_a_brought_record_is_written_before_the_moves(tmp_path):
    """§ 4.9: import/brought.json holds the commit, the roots and the Report,
    so a Finish pressed again answers from it (§ 4.11)."""
    into, brought = _brought(tmp_path, {
        "index.html": _page("<p>Home</p>"), "images/pic.png": _png(), "tool.exe": b"MZ"},
        commit="abc123", left=(("too/big.pdf", "it is too large"),))
    assert set(brought.roots) == {"index.html", "images"}
    assert pressless_import.read_brought(into, "abc123") == brought
    assert pressless_import.read_brought(into, "another") is None
    assert ("too/big.pdf", "it is too large") in brought.report.unfetched
    assert not (into / "import" / "folder").exists()


# ---------------------------------------------------------------- INV-20 ---


def test_an_older_encoding_is_read(tmp_path):
    """INV-20. Breaks when the bytes are decoded as UTF-8 with replacement."""
    declared = ('<html><head><meta charset="iso-8859-1"><title>T</title></head>'
                "<body><p>caf\xe9</p></body></html>").encode("latin-1")
    silent = "<html><head><title>T</title></head><body><p>caf\xe9</p></body></html>".encode(
        "latin-1")
    into, brought = _brought(tmp_path, {"index.html": declared, "two.html": silent})
    for name in ("index", "two"):
        text = store.html_path_for(into, store.PAGES_FOLDER, name).read_bytes().decode("utf-8")
        assert "café" in text, name
        assert re.search(r'<meta charset="utf-8"', text), name
        assert f"pages/{name}" in _said(brought)
    assert "iso-8859-1" not in store.read_html(
        store.html_path_for(into, store.PAGES_FOLDER, "index"))


def test_a_file_nothing_decodes_is_left(tmp_path):
    """§ 4.9: cp1252 has bytes it does not define."""
    folder = _laid_out(tmp_path, {"index.html": _page("<p>Home</p>"),
                                  "two.html": b"<p>\x81\xff</p>"})
    assert "two.html" in dict(pressless_import.read_folder(folder).left)


def test_a_byte_order_mark_is_dropped(tmp_path):
    """§ 4.9."""
    into, _b = _brought(tmp_path, {"index.html": b"\xef\xbb\xbf" + _page("<p>H</p>").encode()})
    assert store.html_path_for(into, store.PAGES_FOLDER, "index").read_bytes().startswith(
        b"<!doctype")


# ------------------------------------------------------ a page, and writing ---


def test_marks_a_page_holds_are_removed_and_listed(tmp_path):
    """§ 4.9: the Builder would otherwise fill or read them."""
    into, brought = _brought(tmp_path, {"index.html": _page(
        "<!-- HEADER:START --><!-- HEADER:END --><!-- pressless:page -->"
        "<p>Home</p><!-- /pressless:page -->")})
    assert "pages/index" in _said(brought)
    site = _built(tmp_path, into)
    assert "HEADER:START" not in (site / "index.html").read_text(encoding="utf-8")


def test_a_page_without_main_gets_one_and_its_sections(tmp_path):
    """§ 4.9: between the header and the footer, shared or its own, so
    `blocks.adopt` can make its area."""
    into, _b = _brought(tmp_path, {
        "index.html": _page(f"<header>S</header>\n<h1>Words</h1>\n<p>More</p>\n{FOOTER}"),
        "two.html": _page(f"<header>S</header>\n<h1>Two</h1>\n{FOOTER}")})
    text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "two"))
    assert "<main>" in text and "<!-- pressless:page -->" in text
    assert text.index("HEADER:END") < text.index("<main>")
    assert text.index("</main>") < text.index("FOOTER:START")


def test_a_main_crossing_other_elements_is_not_made(tmp_path):
    """§ 4.9, and why: a `<main>` opened inside a wrapper and closed outside it
    would change what the browser builds. The page stays whole, and is listed."""
    body = '<div class="wrap"><header>S</header><p>Words</p></div><footer>F</footer>'
    into, brought = _brought(tmp_path, {"index.html": _page(body), "two.html": _page(body)})
    text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "two"))
    assert "<main>" not in text and "<p>Words</p>" in text
    assert "pages/two" in _said(brought)


def test_a_page_with_no_body_takes_the_starters_shape(tmp_path):
    """§ 4.9."""
    into, _b = _brought(tmp_path, {
        "index.html": _page("<p>H</p>"), "bit.html": "<h1>A <b>bit</b></h1>\n<p>Words</p>"})
    text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "bit"))
    assert "<title>A bit</title>" in text and "<p>Words</p>" in text
    assert "HEADER:START" in text and 'href="../look/style.css"' in text


def test_a_page_keeps_its_own_line_endings_and_bytes(tmp_path):
    """§ 4.9: the head and body keep their bytes but for what the spec names."""
    head = '<title>Home</title>\r\n  <meta name="x"   content="y" >\r\n'
    into, _b = _brought(tmp_path, {"index.html": _page(
        "<main>\r\n<p  class=odd>Words</p>\r\n</main>", head=head)})
    text = store.html_path_for(into, store.PAGES_FOLDER, "index").read_bytes().decode()
    assert head in text and "<p  class=odd>Words</p>" in text


def test_the_identity_comes_from_the_front_page(tmp_path):
    """§ 4.9: its title and description, runs of whitespace made one space."""
    into, _b = _brought(tmp_path, {"index.html": _page("<p>H</p>", head=(
        '<title> My\n  Site &amp; More </title>'
        '<meta name="description" content="Words\n about it">'))})
    identity = store.read_identity(into)
    assert identity.name == "My Site & More" and identity.description == "Words about it"


def test_no_identity_where_the_title_is_blank(tmp_path):
    """§ 4.9: `store.identity_problem` refuses a blank name."""
    into, _b = _brought(tmp_path, {"index.html": _page("<p>H</p>", head="<title> </title>")})
    assert store.read_identity(into) is None


def test_the_journal_is_off_and_the_templates_are_seeded(tmp_path):
    """§ 3 decision 7, § 4.9."""
    into, _b = _brought(tmp_path, {"index.html": _page("<p>H</p>")})
    assert store.journal_on(into) is False
    assert store.list_slugs(into, draft=False) == ()
    assert list((into / store.TEMPLATES_FOLDER).iterdir())


def test_a_carried_file_nothing_names_stays_and_is_listed(tmp_path):
    """§ 4.13's last line: in the Store, not published, and listed."""
    into, brought = _brought(tmp_path, {"index.html": _page("<p>H</p>"), "alone.pdf": PDF})
    assert store.list_files(into) == ("alone.pdf",)
    assert "alone.pdf" in _said(brought)
    assert not (_built(tmp_path, into) / "files" / "alone.pdf").exists()


def test_a_menu_inside_the_footer_goes_with_the_footer(tmp_path):
    """§ 4.8: the footer file carries it, once, and no page's words are repeated."""
    footer = '<footer><nav><a href="index.html">Home</a></nav><p>Mine</p></footer>'
    into, _b = _brought(tmp_path, {"index.html": _page(f"<p>One</p>{footer}"),
                                   "two.html": _page(f"<p>Two</p>{footer}")})
    text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "two"))
    assert "<nav" not in text and "Mine" not in text and text.count("FOOTER:START") == 1
    assert "HEADER:START" not in text, "the footer's menu is no header"
    assert "<nav" in store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "footer"))


def test_a_style_element_at_the_files_start_is_read_as_one(tmp_path):
    """§ 4.5: its address is CSS, written unescaped, wherever the element sits."""
    into, _b = _brought(tmp_path, {
        "index.html": '<style>a > b { background: url("pic.png"); }</style><body><p>H</p></body>',
        "pic.png": _png()})
    text = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, "index"))
    assert 'a > b { background: url("photographs/pic.png"); }' in text
