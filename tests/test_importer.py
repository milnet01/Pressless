# INV-1 to INV-4 and INV-6 to INV-12 for PRESS-0007 (Import), and INV-5's
# test of `visible_lines`. Pure: every export and every original is built in
# the test, so this runs in CI. The archive halves of INV-2, INV-3, INV-5,
# INV-6 and INV-7 live in test_importer_archive.py instead, because the export
# is personal data that cannot ship in a public repository.
#
# Why this exists: docs/specs/PRESS-0007-import.md is the contract, and Import
# runs once -- anything it gets wrong is outside Pressless for good (§2). Each
# test below is named for the invariant it locks, per that spec's §5 and §10.
#
# Every address here is example.org or a documentation range, and every
# contact value is .invalid: nothing names a real person or site.
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

import pressless_import
from pressless import store
from pressless.marks import render
from pressless_import import (
    ImportStopped,
    convert,
    is_markup,
    main,
    resolve_slug,
    run,
    visible_lines,
)

SITE_HOST = "old.example.org"      # the WordPress site the export came from
SITE = f"https://{SITE_HOST}"
UPLOADS = f"{SITE}/wp-content/uploads"


# ------------------------------------------------------------- the export ----


def _comment(identifier, *, parent="0", approved="1", kind="", email="", ip="",
             content="Lovely.", date="2012-05-02 11:00:00"):
    return (
        "<wp:comment>"
        f"<wp:comment_id>{identifier}</wp:comment_id>"
        "<wp:comment_author><![CDATA[A reader]]></wp:comment_author>"
        f"<wp:comment_author_email><![CDATA[{email}]]></wp:comment_author_email>"
        "<wp:comment_author_url>https://reader.example.org</wp:comment_author_url>"
        f"<wp:comment_author_IP><![CDATA[{ip}]]></wp:comment_author_IP>"
        f"<wp:comment_date><![CDATA[{date}]]></wp:comment_date>"
        f"<wp:comment_content><![CDATA[{content}]]></wp:comment_content>"
        f"<wp:comment_approved><![CDATA[{approved}]]></wp:comment_approved>"
        f"<wp:comment_type><![CDATA[{kind}]]></wp:comment_type>"
        f"<wp:comment_parent>{parent}</wp:comment_parent>"
        "</wp:comment>"
    )


def _item(post_id, *, kind="post", status="publish", slug="", title="A title",
          date="2012-05-01 10:00:00", body="", categories=(), tags=(),
          comments=(), attachment="", menu_order=0, extra=""):
    terms = "".join(
        f'<category domain="category" nicename="{name}"><![CDATA[{name}]]></category>'
        for name in categories
    ) + "".join(
        f'<category domain="post_tag" nicename="{name}"><![CDATA[{name}]]></category>'
        for name in tags
    )
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<content:encoded><![CDATA[{body}]]></content:encoded>"
        f"<wp:post_id>{post_id}</wp:post_id>"
        f"<wp:post_date><![CDATA[{date}]]></wp:post_date>"
        f"<wp:post_name><![CDATA[{slug}]]></wp:post_name>"
        f"<wp:status><![CDATA[{status}]]></wp:status>"
        f"<wp:post_type><![CDATA[{kind}]]></wp:post_type>"
        f"<wp:menu_order>{menu_order}</wp:menu_order>"
        + extra
        + (f"<wp:attachment_url><![CDATA[{UPLOADS}/{attachment}]]></wp:attachment_url>"
           if attachment else "")
        + terms
        + "".join(comments)
        + "</item>"
    )


def _export(*items: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"'
        ' xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"'
        ' xmlns:content="http://purl.org/rss/1.0/modules/content/"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:wp="http://wordpress.org/export/1.2/">\n'
        f"<channel><title>A site</title><link>{SITE}</link>"
        f"<wp:base_site_url>{SITE}</wp:base_site_url>"
        f"<wp:base_blog_url>{SITE}</wp:base_blog_url>"
        + "".join(items)
        + "</channel></rss>\n"
    )


_HEADER = (
    "<!-- A note for whoever edits this template. -->\n"
    '  <header class="site">\n'
    '    <h1><a href="{{UP}}index.html">A site</a></h1>\n'
    '    <nav class="primary{{ANIM3}}" aria-label="Primary">\n'
    '      <a href="{{UP}}index.html" data-nav="Home">Home</a>\n'
    "    </nav>\n"
    '    <hr class="rule">\n'
    "  </header>\n"
)
_FOOTER = "<!-- Another note. -->\n  <footer>{{YEAR}}</footer>\n"


def _files(root: Path, files: dict[str, str | bytes]):
    root.mkdir(parents=True, exist_ok=True)
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            target.write_bytes(data)
        else:
            target.write_text(data, encoding="utf-8", newline="")


def _world(tmp_path: Path, export_text: str, originals: dict[str, bytes] | None = None, *,
           live_site: dict[str, str | bytes] | None = None,
           templates: dict[str, str] | None = None):
    """The export file, an originals folder holding `originals`, a live site
    and a templates folder beside them (§4.9's smallest usable ones unless
    given), and an INTO that does not exist yet."""
    export = tmp_path / "export.xml"
    export.write_text(export_text, encoding="utf-8")
    folder = tmp_path / "originals"
    _files(folder, originals or {})
    _files(tmp_path / "live-site", live_site if live_site is not None else {
        "index.html": "<p>home</p>\n", "assets/site.css": "body {}\n"})
    _files(tmp_path / "templates", templates if templates is not None else {
        "header.html": _HEADER, "footer.html": _FOOTER})
    return export, folder, tmp_path / "pressless-data"


def _run(export: Path, originals: Path, into: Path):
    """run(), handed the live site and templates _world put beside INTO."""
    return run(export, originals, into.parent / "live-site", into.parent / "templates", into)


def _whats(report, slug):
    return [d.what for d in report.dropped if d.slug == slug]


# ------------------------------------------------------------ INV-1 -------


def test_every_carried_item_lands_once(tmp_path):
    """INV-1: every carried item is written exactly once -- a published post
    into the published folder, a draft, private post or WordPress page into
    drafts, and a trashed post nowhere.

    Breaks when a private post is left out, a page is skipped, or a trashed
    post is carried (spec §5)."""
    export, originals, into = _world(tmp_path, _export(
        _item(1, slug="published-one"),
        _item(2, status="draft", slug="a-draft"),
        _item(3, status="private", slug="a-private"),
        _item(4, status="trash", slug="binned"),
        _item(8, status="pending", slug="for-review"),
        _item(9, status="future", slug="scheduled"),
        _item(5, kind="page", slug="about"),
        _item(6, kind="attachment", status="inherit", slug="a-picture",
              attachment="2012/05/a.jpg"),
        _item(7, kind="nav_menu_item", slug="menu"),
    ), {"2012/05/a.jpg": b"a"})

    report = _run(export, originals, into)

    assert store.list_slugs(into, draft=False) == ("published-one",), (
        f"only the published post belongs in published: "
        f"{store.list_slugs(into, draft=False)!r}"
    )
    drafts = store.list_slugs(into, draft=True)
    assert sorted(drafts) == ["a-draft", "a-private", "about", "for-review", "scheduled"], (
        f"the draft, the private, pending and scheduled posts and the page arrive as "
        f"drafts, once each: {drafts!r}"
    )
    assert (report.published, report.drafts) == (1, 5), f"the report's counts: {report!r}"


# ------------------------------------------------------------ INV-2 -------


def test_a_contested_slug_goes_to_the_live_address(tmp_path):
    """INV-2: a slug follows PRESS-0005 §3 decision 4's rule; a contested one
    goes to decision 5's winner and each loser takes `<slug>-<post id>`, and
    nothing written is ever written over.

    Breaks when the draft keeps the slug and the published address moves, or
    the second write replaces the first (spec §5)."""
    assert resolve_slug("2001%ef%bb%bf", "9") == "2001", "percent-decoded, the BOM dropped"
    assert resolve_slug("Café Olé!", "9") == "cafe-ole", "folded to ASCII, joined by hyphens"
    assert resolve_slug("", "42") == "42", "the post id where nothing survives"
    assert resolve_slug("%%%", "7") == "7", "the post id where nothing survives"

    # The page comes first in the export, so document order cannot be what
    # decides: the live address has to win on rank.
    export, originals, into = _world(tmp_path, _export(
        _item(10, kind="page", slug="same", title="the page"),
        _item(11, status="draft", slug="same", title="the draft"),
        _item(12, slug="same", title="the live one"),
        _item(13, slug="con", title="a device name"),
    ))

    report = _run(export, originals, into)

    live = store.read(store.path_for(into, "same", draft=False))
    assert live.title == "the live one", f"the published post keeps the live address: {live!r}"
    for slug, title in (("same-11", "the draft"), ("same-10", "the page")):
        loser = store.read(store.path_for(into, slug, draft=True))
        assert loser.title == title, f"{slug!r} must hold {title!r}, not be written over: {loser!r}"
    device = store.read(store.path_for(into, "con-13", draft=False))
    assert device.title == "a device name", "a slug the Store refuses is treated as lost"
    assert set(report.renamed_slugs) == {("same", "same-10"), ("same", "same-11"),
                                         ("con", "con-13")}, (
        f"every renamed slug is in the report: {report.renamed_slugs!r}"
    )


# ------------------------------------------------------------ INV-3 -------


def test_a_plain_body_is_written_as_it_is(tmp_path):
    """INV-3: a plain body is written byte for byte, and a markup body is
    never written as it came.

    Breaks when a plain body is run through the converter, or `is_markup`
    departs from today's generator's test (spec §5)."""
    for markup in ("<p>x", "<P>x", "<!-- wp:paragraph -->", "<h6>x", "<iframe src=x>",
                   "<em>x", "<strong>x", '<a href="x">', "<blockquote>", "<figure>",
                   "<ul>", "<ol>", "<div>", "<img src=x>"):
        assert is_markup(markup), f"{markup!r} is markup by today's generator's test"
    for plain in ("<pre>x", "<span>x", "<emx>", "<pb>", "a < p", "<table>", "plain"):
        assert not is_markup(plain), f"{plain!r} is plain by today's generator's test"

    plain_body = 'a&nbsp;b\nthe lone * here\na stray <span id="x">tag\n[gallery ids="1"]'
    export, originals, into = _world(tmp_path, _export(
        _item(1, slug="plain", body=plain_body),
        _item(2, slug="marked", body="<p>converted</p>"),
    ))

    report = _run(export, originals, into)

    written = store.read(store.path_for(into, "plain", draft=False)).body
    assert written == plain_body, f"a plain body is written byte for byte: {written!r}"
    assert any("gallery" in what for what in _whats(report, "plain")), (
        f"a shortcode in a plain body is listed: {report.dropped!r}"
    )
    converted = store.read(store.path_for(into, "marked", draft=False)).body
    assert converted == "converted", f"a markup body is never written as it came: {converted!r}"


# ------------------------------------------------------------ INV-4 -------

_ATTACHMENTS = {
    "2012/05/a.jpg": "a.jpg",
    "2012/05/b.jpg": "b.jpg",
    "2012/05/song.mp3": "song.mp3",
    "2012/05/clip.mp4": "clip.mp4",
}


def _by_address(address):
    """The lookup §4.1 describes, over _ATTACHMENTS: every attachment answers,
    traced by its decoded upload path, a resized copy's suffix tried away."""
    marker = "/wp-content/uploads/"
    if marker not in address:
        return None
    upload_path = address.split(marker, 1)[1].split("?", 1)[0]
    if upload_path in _ATTACHMENTS:
        return _ATTACHMENTS[upload_path]
    return _ATTACHMENTS.get(re.sub(r"-\d+x\d+(?=\.\w+$)", "", upload_path))


def _by_id(attachment_id):
    return {"1": "a.jpg", "2": "b.jpg"}.get(attachment_id)


# (WordPress, the marks it becomes, a word the report's entry must carry or None)
_ROWS = [
    ("<!-- wp:paragraph --><p>a</p><!-- /wp:paragraph -->", "a", None),
    ('<!-- wp:social-link {"url":"https://social.example.org/me","service":"x"} /-->',
     "", "https://social.example.org/me"),
    ("<p>a</p><p>b</p>", "a\n\nb", None),
    ("<p>a<br>b</p>", "a\nb", None),
    ("<p><strong>x</strong> and <b>y</b></p>", "**x** and **y**", None),
    ("<p><em>x</em> and <i>y</i></p>", "*x* and *y*", None),
    ('<p><span style="color:#c0453a">red</span></p>', "{#c0453a}red{/}", None),
    ('<p style="color:#c0453a">a<br>b</p>', "{#c0453a}a{/}\n{#c0453a}b{/}", None),
    ('<p style="color:#c0453a;font-size:16px">x</p>', "{#c0453a}x{/}", "font-size"),
    ('<h2 style="color:#123456">loud</h2>', "{#123456}loud{/}", "heading"),
    ('<p><a style="color:#123456" href="https://example.org">x</a></p>',
     "{link: https://example.org}{#123456}x{/}{/}", None),
    ('<p><a href="https://example.org/a?b=1&amp;c=2">x</a></p>',
     "{link: https://example.org/a?b=1&c=2}x{/}", None),
    (f'<p><a href="{SITE}/2012/05/another-post/">see</a></p>', "see", "link"),
    (f'<a href="{UPLOADS}/2012/05/a.jpg"><img src="{UPLOADS}/2012/05/a-300x200.jpg"></a>',
     "{photo: a.jpg}", None),
    (f'<a href="https://elsewhere.example.org/"><img src="{UPLOADS}/2012/05/a.jpg"></a>',
     "{photo: a.jpg}", "elsewhere.example.org"),
    (f'<figure><img src="{UPLOADS}/2012/05/a.jpg"><figcaption>Late light</figcaption></figure>',
     "{photo: a.jpg | Late light}", None),
    # Markup in a caption is flattened, and said so (PRESS-0162).
    (f'<figure><img src="{UPLOADS}/2012/05/a.jpg"><figcaption>'
     '<a href="https://example.org">Late</a> light</figcaption></figure>',
     "{photo: a.jpg | Late light}", "caption"),
    ('[gallery ids="1,2"]', "{photo: a.jpg}\n{photo: b.jpg}", None),
    ("<blockquote><p>a<br>b</p><p>c</p></blockquote>", "> a\n> b\n>\n> c", None),
    ('<figure class="wp-block-pullquote"><blockquote><p>x</p></blockquote></figure>', "> x", None),
    ('<iframe src="https://video.example.org/v/1"></iframe>',
     "{link: https://video.example.org/v/1}https://video.example.org/v/1{/}", None),
    ('<img src="https://elsewhere.example.org/p.jpg">',
     "{link: https://elsewhere.example.org/p.jpg}https://elsewhere.example.org/p.jpg{/}",
     "missing from the export"),
    (f'<p><a href="{UPLOADS}/2012/05/song.mp3">my song</a></p>', "my song", "not a picture"),
    (f'<video src="{UPLOADS}/2012/05/clip.mp4"></video>', "", "a video from a file"),
    ("<div>a</div><div>b</div>", "a\n\nb", None),
    ("<h2>A heading</h2><p>x</p>", "A heading\n\nx", "heading"),
    ("<figure><p>x</p></figure>", "x", None),
    ("<p>a&nbsp;b</p>", "a&nbsp;b", None),
    # The wrap-mark rules: whitespace moves outside, a run never crosses a
    # line, bold and italic together are bold, and a newline is a space.
    ("<p><strong> word</strong></p>", "**word**", None),
    # A literal no-break space is whitespace to Marks too (PRESS-0162).
    ("<p><strong>\u00a0word</strong></p>", "\u00a0**word**", None),
    ('<p><a href="https://example.org"> x</a></p>', "{link: https://example.org}x{/}", None),
    ("<p><strong>a<br>b</strong></p>", "**a**\n**b**", None),
    ("<p><strong><em>x</em></strong></p>", "**x**", "italic"),
    ("<p>a\nb</p>", "a b", None),
]


@pytest.mark.parametrize(("html", "marks", "reported"), _ROWS)
def test_each_construct_becomes_its_mark(html, marks, reported):
    """INV-4: each row of §4.3's table produces its mark; a newline in a
    markup body produces none; and no wrap mark begins or ends with
    whitespace or crosses a line.

    Breaks when a row is converted to something else, whitespace is left
    inside a mark or a mark crosses a line -- each puts literal characters on
    the page -- or a source newline becomes a line break (spec §5)."""
    text, dropped = convert(html, _by_address, _by_id, old_site=SITE_HOST)
    assert text == marks, f"{html!r} must become {marks!r}, got {text!r}"
    if reported is not None:
        assert any(reported in what for what in dropped), (
            f"{html!r} must be listed with {reported!r} in the report: {dropped!r}"
        )
    else:
        # Decision 9's report is read before the folder is handed over, so a
        # line in it that records nothing lost buries the lines that do.
        assert dropped == (), f"{html!r} lost nothing, so nothing is listed: {dropped!r}"
    rendered = render(text, lambda name: name)
    assert "**" not in rendered and "{" not in rendered, (
        f"a mark that did not form reaches the page as literal characters: {rendered!r}"
    )


# ------------------------------------------------------------ INV-5 -------


def test_visible_lines_breaks_where_a_reader_sees_one():
    """INV-5's instrument: `visible_lines` splits where a reader sees a new
    line, and nowhere else -- at <br>, <img>, <div>, <h1> to <h6>, and each
    paragraph, quotation and figure -- decoding character references,
    removing block comments and collapsing whitespace inside a line.

    Breaks when a split point is missed, so a merged line on both sides of
    the comparison passes as unchanged (spec §4.3, §5)."""
    cases = [
        ("<p>a<br>b</p>", ("a", "b")),
        ("a<img src=x>b", ("a", "b")),
        ("<div>a</div>b", ("a", "b")),
        *[(f"a<h{n}>b</h{n}>c", ("a", "b", "c")) for n in range(1, 7)],
        ("<p>a</p><p>b</p>", ("a", "b")),
        ("a<blockquote>b</blockquote>c", ("a", "b", "c")),
        ("a<figure>b</figure>c", ("a", "b", "c")),
        ("<p>x &amp; y&nbsp;z</p>", ("x & y z",)),
        ("<p>a<!-- wp:paragraph -->b</p>", ("ab",)),
        ("<p>a \n\t b</p>", ("a b",)),
        ("<p>a <strong>b</strong> <em>c</em></p>", ("a b c",)),
        # PRESS-0125 § 4.5's splits (INV-11 there): each list item, row, cell,
        # rule and preformatted line is a line of its own.
        ("<ul><li>one</li><li>two</li></ul>", ("one", "two")),
        ("<table><tr><td>a</td><td>b</td></tr><tr><th>c</th></tr></table>",
         ("a", "b", "c")),
        ("a<hr>b", ("a", "b")),
        ("<pre>one\ntwo</pre>", ("one", "two")),
        ("a<script>var shown = 1;</script>b<style>p {}</style>", ("ab",)),
    ]
    for markup, lines in cases:
        assert visible_lines(markup) == lines, (
            f"{markup!r} shows a reader {lines!r}, got {visible_lines(markup)!r}"
        )


# ------------------------------------------------------------ INV-6 -------


def test_a_header_saved_with_crlf_keeps_its_navigation(tmp_path):
    """PRESS-0162 (review-code L10.9): the navigation had to end in a bare
    newline, so a header saved with CRLF was refused as holding none. Its
    own line ending is kept on both halves."""
    crlf = _HEADER.replace("\n", "\r\n").encode("utf-8")
    export, originals, into = _world(tmp_path, _export(_item(1, slug="words")),
                                     templates={"header.html": crlf, "footer.html": _FOOTER})
    _run(export, originals, into)
    header = store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "header"))
    navigation = store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, "navigation"))
    assert "{{NAVIGATION}}\r\n" in header
    assert navigation.rstrip().endswith("</nav>") and "\r\n" in navigation


def test_renamed_photographs_that_differ_only_in_case_stop_the_import(tmp_path):
    """Decision 6 compares names as Windows compares them, and the upload-month
    names were never compared (PRESS-0162, review-code L10.2): 2019/05/IMG.jpg
    and 2019/05/img.jpg became 2019-05-IMG.jpg and 2019-05-img.jpg, one file
    in a Windows folder."""
    originals_bytes = {"2019/05/IMG.jpg": b"one", "2019/05/img.jpg": b"two"}
    export, originals, into = _world(tmp_path, _export(
        _item(20, kind="attachment", status="inherit", attachment="2019/05/IMG.jpg"),
        _item(21, kind="attachment", status="inherit", attachment="2019/05/img.jpg"),
        _item(1, slug="words"),
    ), originals_bytes)

    with pytest.raises(ImportStopped, match="differ only in case"):
        _run(export, originals, into)


def test_photographs_arrive_under_their_names(tmp_path):
    """INV-6: every original is copied byte for byte under decision 6's name,
    and every picture mark names a file in the photographs folder.

    Breaks when two same-named originals are written to one file, or a body
    keeps the WordPress address (spec §5)."""
    originals_bytes = {
        "2012/05/a.jpg": b"the first a",
        "2013/06/A.JPG": b"the second a, differing only in case",
        "2013/06/b.jpg": b"the only b",
    }
    body = (
        "<p>x</p>"
        f'<img src="{UPLOADS}/2012/05/a-300x200.jpg">'
        f'<img src="{UPLOADS}/2013/06/A.JPG">'
        f'<img src="{UPLOADS}/2013/06/b.jpg">'
    )
    export, originals, into = _world(tmp_path, _export(
        _item(20, kind="attachment", status="inherit", attachment="2012/05/a.jpg"),
        _item(21, kind="attachment", status="inherit", attachment="2013/06/A.JPG"),
        _item(22, kind="attachment", status="inherit", attachment="2013/06/b.jpg"),
        _item(1, slug="pictures", body=body),
    ), originals_bytes)

    report = _run(export, originals, into)

    expected = {"2012-05-a.jpg": "2012/05/a.jpg", "2013-06-A.JPG": "2013/06/A.JPG",
                "b.jpg": "2013/06/b.jpg"}
    assert sorted(store.list_photographs(into)) == sorted(expected), (
        f"names shared regardless of case take their upload month: "
        f"{store.list_photographs(into)!r}"
    )
    for name, upload_path in expected.items():
        copied = store.photograph_path_for(into, name).read_bytes()
        assert copied == originals_bytes[upload_path], (
            f"{name} must be {upload_path}, byte for byte"
        )
    written = store.read(store.path_for(into, "pictures", draft=False)).body
    for name in expected:
        assert f"{{photo: {name}}}" in written, f"the body must name {name}: {written!r}"
    assert "wp-content" not in written, f"no body keeps a WordPress address: {written!r}"
    assert set(report.renamed_photographs) == {("2012/05/a.jpg", "2012-05-a.jpg"),
                                               ("2013/06/A.JPG", "2013-06-A.JPG")}, (
        f"every renamed photograph is in the report: {report.renamed_photographs!r}"
    )
    assert report.photographs == 3, f"the report's count: {report!r}"


def test_an_absent_original_is_listed_and_its_picture_kept_as_a_link(tmp_path):
    """INV-6, as PRESS-0125 amended it (PRESS-0158): an attachment whose
    original is absent is listed, and its picture keeps its address as a link.

    Breaks when a missing original stops Import or gets a picture mark."""
    address = f"{UPLOADS}/2012/05/gone.jpg"
    export, originals, into = _world(tmp_path, _export(
        _item(20, kind="attachment", status="inherit", attachment="2012/05/gone.jpg"),
        _item(1, slug="pictures", body=f'<p>x</p><img src="{address}">'),
    ))

    report = _run(export, originals, into)

    written = store.read(store.path_for(into, "pictures", draft=False)).body
    assert "{photo:" not in written, f"no mark names a file that is not there: {written!r}"
    assert f"{{link: {address}}}" in written, f"the picture keeps its address: {written!r}"
    assert [place for place, _why in report.unfetched] == ["2012/05/gone.jpg"], (
        f"the missing original is listed by its upload path: {report.unfetched!r}"
    )
    assert report.photographs == 0 and not store.list_photographs(into)


# ------------------------------------------------------------ INV-7 -------


def test_comments_follow_their_entry(tmp_path):
    """INV-7: every comment §4.6 carries is in its entry's comments file, with
    `0` read as top level, and no value from a commenter's email or IP field
    reaches any file Import writes.

    Breaks when the parent `0` is carried through and the set is refused, or
    a comment follows the WordPress id rather than the Store slug (spec §5)."""
    def contact(n):
        return {"email": f"reader-{n}@contact.invalid", "ip": f"203.0.113.{n}"}

    export, originals, into = _world(tmp_path, _export(
        _item(30, slug="same", comments=[_comment(501, **contact(5))]),
        # The draft loses "same" to the published post, so its comments must
        # follow the slug the Store gives it, not the one it asked for.
        _item(31, status="draft", slug="same", comments=[
            _comment(101, **contact(1)),
            _comment(102, parent="101", **contact(2)),
            _comment(103, kind="pingback", **contact(3)),
            _comment(104, approved="0", **contact(4)),
            # PRESS-0158: its parent is the unapproved one, which is not carried.
            _comment(105, parent="104", **contact(6)),
        ]),
    ))

    report = _run(export, originals, into)

    draft_comments = store.read_comments(store.comments_path_for(into, "same-31"))
    assert [(c.identifier, c.parent) for c in draft_comments] == [
        ("101", ""), ("102", "101"), ("105", "")], (
        f"the approved comment and its reply, 0 read as top level, a reply whose parent "
        f"is not carried at the top, and neither the pingback nor the unapproved one: "
        f"{draft_comments!r}"
    )
    live_comments = store.read_comments(store.comments_path_for(into, "same"))
    assert [c.identifier for c in live_comments] == ["501"], f"{live_comments!r}"
    assert report.comments == 4, f"the report's count: {report!r}"
    assert any("105" in what for what in _whats(report, "same-31")), (
        f"the reply carried at the top is listed: {report.dropped!r}"
    )

    written = b"".join(path.read_bytes() for path in into.rglob("*") if path.is_file())
    for n in range(1, 7):
        for value in contact(n).values():
            assert value.encode() not in written, (
                f"a commenter's contact value reached a file Import wrote (fixture {n})"
            )


# ------------------------------------------------------------ INV-8 -------


def _stops(tmp_path, export, originals, into):
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(ImportStopped):
        _run(export, originals, into)
    after = sorted(p.name for p in tmp_path.iterdir())
    assert after == before, f"a stopped import leaves nothing behind: {before!r} -> {after!r}"


def test_nothing_is_made_when_it_stops(tmp_path, capsys):
    """INV-8: INTO appears whole or not at all.

    Breaks when entries are written into INTO directly, or the folder of
    step 5 survives a failure (spec §5)."""
    # An INTO that already exists is refused, and not touched.
    existing = tmp_path / "existing"
    existing.mkdir()
    export, originals, into = _world(existing, _export(_item(1, slug="one")))
    into.mkdir()
    (into / "keep.txt").write_text("his", encoding="utf-8")
    _stops(existing, export, originals, into)
    assert [p.name for p in into.iterdir()] == ["keep.txt"], "an existing INTO is not changed"

    # main says why it stopped, exits 1, and names no full path.
    assert main([str(export), str(originals), str(existing / "live-site"),
                 str(existing / "templates"), str(into)]) == 1
    said = capsys.readouterr()
    assert str(tmp_path) not in said.out + said.err, (
        f"main's words never name a full filesystem path: {said!r}"
    )

    # An export that cannot be read stops it before anything is made.
    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()
    export, originals, into = _world(unreadable, "<rss><channel>")
    _stops(unreadable, export, originals, into)
    assert not into.exists()

    # A refusal the Store raises while writing -- a category holding the
    # list's own separator -- stops it and removes the folder of step 5.
    refused = tmp_path / "refused"
    refused.mkdir()
    export, originals, into = _world(refused, _export(
        _item(1, slug="one"), _item(2, slug="two", categories=("a,b",)),
    ))
    _stops(refused, export, originals, into)
    assert not into.exists()


# ------------------------------------------------------------ INV-9 -------


def test_what_is_dropped_is_reported(tmp_path):
    """INV-9: what Import could not convert is in Report.dropped, by entry.

    Breaks when an unknown tag is removed without a record, or an `alt` is
    listed without its text or its picture (spec §5)."""
    body = (
        "<table><tr><td>cell</td></tr></table>"
        '<p class="lead" style="font-size:2em">big</p>'
        '<!-- wp:social-link {"url":"https://social.example.org/me","service":"x"} /-->'
        # Resized addresses, so a line naming the address cannot pass for one
        # naming the Store name.
        f'<img alt="a harbour at dusk" src="{UPLOADS}/2012/05/a-300x200.jpg">'
        f'<img alt="the rehearsal room" src="{UPLOADS}/2012/05/b-1024x768.jpg">'
    )
    export, originals, into = _world(tmp_path, _export(
        _item(41, kind="attachment", status="inherit", attachment="2012/05/a.jpg"),
        _item(42, kind="attachment", status="inherit", attachment="2012/05/b.jpg"),
        _item(40, slug="tabled", body=body),
    ), {"2012/05/a.jpg": b"a", "2012/05/b.jpg": b"b"})

    report = _run(export, originals, into)

    written = store.read(store.path_for(into, "tabled", draft=False)).body
    assert "cell" in written and "big" in written, f"the words are kept: {written!r}"
    whats = _whats(report, "tabled")
    # One word per kind §4.3 names: an unknown tag, a style that is not a hex
    # colour, an attribute the table does not use, and a social link.
    for word in ("table", "font-size", "class", "https://social.example.org/me"):
        assert any(word in what for what in whats), (
            f"{word!r} must be listed against its entry: {report.dropped!r}"
        )
    # Decision 13: each alt is listed with its text and its picture's Store
    # name, one line per picture, so the maintainer can caption it by hand.
    for alt, name in (("a harbour at dusk", "a.jpg"), ("the rehearsal room", "b.jpg")):
        assert any(alt in what and name in what for what in whats), (
            f"the alt {alt!r} must be listed with {name}: {report.dropped!r}"
        )
    settings = [name for what in whats if what.startswith("settings")
                for name in what.split(": ", 1)[1].split(", ")]
    assert sum("description of the picture" in what for what in whats) == 2, whats
    assert "alt" not in settings, f"the attribute is not listed a second time: {whats!r}"


def test_settings_and_formatting_are_one_line_each():
    """PRESS-0294: an entry's unread attributes and styles are each said in
    one line, naming every one, rather than a line per tag.

    Breaks when each is listed on its own line again, or one is left out of
    the line (PRESS-0007 §4.3 still has every one listed)."""
    _text, dropped = convert(
        '<p class="lead" id="top" style="font-size:2em">a</p>'
        '<p class="lead" style="text-align:center">b</p>', _by_address, _by_id)
    settings = [what for what in dropped if what.startswith("settings")]
    formatting = [what for what in dropped if what.startswith("formatting")]
    assert len(settings) == 1 and settings[0].endswith(": class, id"), dropped
    assert len(formatting) == 1 and formatting[0].endswith(
        ": font-size 2em, text-align center"), dropped


# ----------------------------------------------------------- INV-11 -------

_INDEX = (
    "<!doctype html>\n"
    '<link rel="stylesheet" href="assets/site.css?v=0123abcd">\n'
    '<link rel="alternate" href="https://elsewhere.example.org/feed?v=12ab">\n'
    "<body>\n"
    '  <!-- HEADER:START page="Home" animate nonav -->\n'
    "  <header>yesterday's header</header>\n"
    "  <!-- HEADER:END -->\n"
    "<main>his words, and a ?v=1234 in them</main>\n"
    "\t<!-- FOOTER:START -->\n"
    "\t<footer>yesterday's footer</footer>\n"
    "\t<!-- FOOTER:END -->\n"
    "<script src='assets/site.js?v=89ef'></script>\n"
)
_INDEX_CARRIED = (
    "<!doctype html>\n"
    '<link rel="stylesheet" href="assets/site.css">\n'
    '<link rel="alternate" href="https://elsewhere.example.org/feed?v=12ab">\n'
    "<body>\n"
    '  <!-- HEADER:START page="Home" animate nonav -->\n'
    "  <!-- HEADER:END -->\n"
    "<main>his words, and a ?v=1234 in them</main>\n"
    "\t<!-- FOOTER:START -->\n"
    "\t<!-- FOOTER:END -->\n"
    "<script src='assets/site.js'></script>\n"
)
_ABOUT = (
    '<link rel="stylesheet" href="../assets/site.css?v=0123abcd">\r\n'
    '<!-- HEADER:START page="About" --><nav>old</nav>\r\n'
    '    <!--HEADER:END-->\r\n'
    "<p>about him</p>\r\n"
)
_ABOUT_CARRIED = (
    '<link rel="stylesheet" href="../assets/site.css">\r\n'
    '<!-- HEADER:START page="About" -->\n'
    '    <!--HEADER:END-->\r\n'
    "<p>about him</p>\r\n"
)


def test_fixed_pages_and_furniture_come_across(tmp_path):
    """INV-11: each fixed page is the live page with its marker pairs emptied
    and its stamps removed, and nothing else changed; and `header` with
    `navigation` put back in place of {{NAVIGATION}} equals today's header
    template.

    Breaks when text between the markers survives, a stamp is left, a byte
    outside the markers changes, or the navigation is cut short (spec §5)."""
    site = {"index.html": _INDEX, "pages/about.html": _ABOUT, "other.html": "<p>not a page</p>",
            "assets/site.css": "body {}\n"}
    export, originals, into = _world(tmp_path, _export(_item(1, slug="one")), live_site=site)

    report = _run(export, originals, into)

    assert report.pages == ("about", "index"), f"the pages carried, sorted: {report.pages!r}"
    assert store.list_html(into, store.PAGES_FOLDER) == ("about", "index"), (
        "only index.html and pages/<name>.html are fixed pages"
    )
    for name, expected in (("index", _INDEX_CARRIED), ("about", _ABOUT_CARRIED)):
        carried = store.read_html(store.html_path_for(into, store.PAGES_FOLDER, name))
        assert carried == expected, f"{name}: markers emptied, stamps removed, nothing else"

    furniture = {name: store.read_html(store.html_path_for(into, store.FURNITURE_FOLDER, name))
                 for name in store.FURNITURE_NAMES}
    assert furniture["footer"] == _FOOTER, "the footer template, as it is"
    assert "<nav" not in furniture["header"], "the navigation is cut out of the header"
    assert "\n{{NAVIGATION}}\n" in furniture["header"], "and a line of its own stands in for it"
    assert furniture["navigation"].startswith("    <nav class=") and \
        furniture["navigation"].endswith("</nav>"), (
        f"the navigation is the element, indentation and all: {furniture['navigation']!r}"
    )
    rebuilt = furniture["header"].replace("{{NAVIGATION}}", furniture["navigation"])
    assert rebuilt == _HEADER, "putting the navigation back gives the template byte for byte"


@pytest.mark.parametrize("site, templates, why", [
    ({"pages/x.html": '<!-- HEADER:START page="X" -->\n<p>x</p>\n'}, None, "a START with no END"),
    ({"pages/x.html": "<p>x</p>\n<!-- FOOTER:END -->\n"}, None, "an END with no START"),
    ({"pages/x.html": "<!-- HEADER:START -->\n<!-- FOOTER:END -->\n"}, None,
     "an END of the other kind"),
    ({"pages/index.html": "<p>again</p>\n"}, None, "the name index taken twice"),
    ({"pages/sub/deep.html": "<p>deep</p>\n"}, None, "a file under pages/ that is no page"),
    ({"pages/notes.txt": "a note\n"}, None, "a file under pages/ that is no page"),
    ({}, {"header.html": "<header></header>\n", "footer.html": _FOOTER}, "a header with no nav"),
    ({}, {"header.html": _HEADER + _HEADER, "footer.html": _FOOTER}, "a header with two navs"),
    ({"index.html": None}, None, "a live site with no index.html"),
    ({"assets/site.css": None}, None, "a live site with no assets/"),
])
def test_a_site_that_cannot_be_carried_stops_import(tmp_path, site, templates, why):
    """INV-11, §4.9 and §6: each of these stops Import, and nothing is made."""
    live = {"index.html": "<p>home</p>\n", "assets/site.css": "body {}\n"}
    live.update(site)
    live = {path: data for path, data in live.items() if data is not None}
    export, originals, into = _world(tmp_path, _export(_item(1, slug="one")),
                                     live_site=live, templates=templates)
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(ImportStopped) as stopped:
        _run(export, originals, into)
    assert sorted(p.name for p in tmp_path.iterdir()) == before, f"{why}: nothing is made"
    assert str(tmp_path) not in str(stopped.value), f"{why}: the message names no full path"


# ----------------------------------------------------------- INV-12 -------


def test_the_site_assets_are_copied_for_previews(tmp_path):
    """INV-12: INTO/<PREVIEW_ASSETS>/ holds every file of the live assets/
    folder byte for byte, and nothing from outside it; and PREVIEW_ASSETS is
    preview-assets.

    Breaks when a file is left out, or the name changes after a folder has
    been handed over, so the Face finds no copy and every preview loses its
    look (spec §5)."""
    # The name is written out here, never imported from paths: shared, the test
    # would compare paths against itself (the project CLAUDE.md, INV-5 there).
    from pressless import paths
    assert paths.PREVIEW_ASSETS == "preview-assets", "every handed folder binds to this name"

    assets = {"assets/site.css": "body {}\n", "assets/img/deep/logo.png": b"\x89PNG\x00\xff",
              "assets/fonts/a.woff2": b"\x00\x01"}
    site = {"index.html": "<p>home</p>\n", "robots.txt": "User-agent: *\n", **assets}
    export, originals, into = _world(tmp_path, _export(_item(1, slug="one")), live_site=site)

    _run(export, originals, into)

    copy = into / "preview-assets"
    held = sorted(path.relative_to(copy).as_posix() for path in copy.rglob("*") if path.is_file())
    assert held == sorted(path.removeprefix("assets/") for path in assets), (
        f"the copy holds what assets/ holds and nothing else: {held!r}"
    )
    for path in assets:
        assert (copy / path.removeprefix("assets/")).read_bytes() == \
            (tmp_path / "live-site" / path).read_bytes(), f"{path} byte for byte"


# ----------------------------------------------------------- INV-10 -------

# The whole of what Import may import, by full dotted name. An ALLOWLIST, as
# PRESS-0004 INV-7's test is: a denylist is only ever as long as the last
# person's imagination (PRESS-0110). Add a name only for a module that reaches
# no network, and say what needs it.
_ALLOWED_IMPORTS = {
    "__future__",
    "collections", "collections.abc",   # Lookup's Callable
    "dataclasses",                      # Dropped and Report
    "datetime",                         # an entry's and a comment's date
    "difflib",                          # the self-check's line comparison
    "html", "html.parser",              # reading a markup body
    "json",                             # a social-link block's attributes
    "os", "pathlib", "shutil", "tempfile",  # the folder of step 5 and the copies
    "re", "sys", "unicodedata",
    "urllib", "urllib.parse",           # decoding a slug and an address -- never fetching
    "xml", "xml.etree", "xml.etree.ElementTree",  # the export
    "pressless", "pressless.marks", "pressless.paths", "pressless.store",
    # PRESS-0125: the Import anyone runs writes a whole site through the
    # parts that own each piece, and unpacks a media download.
    "pressless.blocks", "pressless.builder", "pressless.look", "pressless.menu",
    "pressless.sitefile", "pressless.starter", "pressless.templates", "zipfile",
}


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def test_import_reaches_no_network():
    """INV-10: Import reaches no network -- every module of pressless_import
    but `fetch`, which PRESS-0125 § 4.4 owns, imports only what the allowlist
    names, compared by full dotted name, so `urllib.parse` is admitted and
    `urllib.request` is not.

    Breaks when a module other than `fetch` gains a network import (spec §5)."""
    package = Path(pressless_import.__file__).parent
    modules = sorted(path for path in package.glob("*.py") if path.name != "fetch.py")
    assert (package / "fetch.py").is_file(), "the one exempt module is where it is named"
    seen = set()
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    seen.add(alias.name)
                    assert alias.name in _ALLOWED_IMPORTS, (
                        f"{module.name} imports {alias.name}, which the allowlist does not admit"
                    )
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                seen.add(node.module)
                assert node.module in _ALLOWED_IMPORTS, (
                    f"{module.name} imports from {node.module}, which the allowlist does not admit"
                )
                for alias in node.names:
                    dotted = f"{node.module}.{alias.name}"
                    if _is_module(dotted):
                        seen.add(dotted)
                        assert dotted in _ALLOWED_IMPORTS, (
                            f"{module.name} imports {dotted}, which the allowlist does not admit"
                        )
    assert "xml.etree.ElementTree" in seen, (
        f"the walk saw no import of the export's parser, so it is not reading "
        f"pressless_import at all: {sorted(seen)!r}"
    )


def test_run_reaches_no_network(tmp_path, monkeypatch):
    """INV-10: the maintainer's run completes with every socket refused, a
    picture whose original is missing included -- it is listed, never fetched.

    Breaks when a picture is fetched from the old site by the maintainer's run."""
    import socket

    def refused(*args, **kwargs):
        raise AssertionError("the maintainer's run opened a socket")

    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket, "getaddrinfo", refused)
    export, originals, into = _world(tmp_path, _export(
        _item(20, kind="attachment", status="inherit", attachment="2012/05/gone.jpg"),
        _item(1, slug="one", body=f'<p>x</p><img src="{UPLOADS}/2012/05/gone.jpg">'),
    ))
    report = _run(export, originals, into)
    assert report.unfetched and store.list_slugs(into, draft=False) == ("one",)


@pytest.mark.parametrize("attachment",
                         ["{outside}", "../outside.jpg", "2012/05/../../../outside.jpg"])
def test_an_attachment_address_leaving_the_uploads_folder_stops_it(tmp_path, attachment):
    """PRESS-0135 #33: an attachment's upload path is joined onto ORIGINALS and
    the file copied into INTO, which is handed on. A path that is absolute, or
    climbs out with `..`, reached any file the maintainer can read: pathlib
    drops the left side for an absolute right side. It stops the run and copies
    nothing.

    Breaks when the upload path is joined without checking it stays inside.
    """
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"not an upload")
    address = attachment.format(outside="/" + str(outside).lstrip("/"))
    export, originals, into = _world(tmp_path, _export(
        _item("1", slug="seaside", body="Words."),
        _item("9", kind="attachment", attachment=address)),
        {"2012/05/real.jpg": b"an upload"})
    _stops(tmp_path, export, originals, into)


def test_markup_nested_too_deeply_stops_it_by_name(tmp_path):
    """PRESS-0135 #37: the converter walks the tree recursively, and every
    unclosed tag nests the next, so a few hundred unclosed ones raised a raw
    RecursionError -- a traceback, not the ImportStopped decision 9's run
    ends on. Marks caps its own nesting for the same reason (PRESS-0054).

    Breaks when the conversion's RecursionError escapes untyped.
    """
    export, originals, into = _world(tmp_path, _export(
        _item("1", slug="seaside", body="<p>" + "<b>" * 5000 + "deep</p>")))
    _stops(tmp_path, export, originals, into)


def test_a_report_prints_no_control_characters(tmp_path, monkeypatch, capsys):
    """PRESS-0135 #38: the report and a stop's message print alt text,
    addresses and upload paths from the export as they came, and decision 9
    makes the maintainer read that report. A character reference to ESC in an
    attribute, or %1b in an address, printed raw lets a crafted export rewrite
    the lines on his terminal. Control and format characters print escaped.

    Breaks when anything from the export reaches the terminal unescaped.
    """
    import pressless_import as imp

    hostile = "\x1b[2Jwiped‮"
    report = imp.Report(1, 0, 0, 0, ((hostile, "seaside"),), (), ("about",),
                        (imp.Dropped("seaside", hostile),))
    monkeypatch.setattr(imp, "run", lambda *args: report)
    assert imp.main(["a", "b", "c", "d", "into"]) == 0

    def stopped(*args):
        raise imp.ImportStopped(f"attachment {hostile} is missing")

    monkeypatch.setattr(imp, "run", stopped)
    assert imp.main(["a", "b", "c", "d", "into"]) == 1
    printed = capsys.readouterr()
    for stream in (printed.out, printed.err):
        assert "\x1b" not in stream and "‮" not in stream, repr(stream)
        assert "\\x1b" in stream, repr(stream)


# ------------------------------------- PRESS-0125: what both runs share ----
#
# docs/specs/PRESS-0125-wordpress-import.md § 5. These hold for the
# maintainer's run as for the Import anyone runs, since the code is shared
# (§ 3 decision 8).


def test_an_export_declaring_entities_is_refused(tmp_path, monkeypatch):
    """PRESS-0125 INV-2: an export declaring a DOCTYPE or an entity is
    refused before parsing, wherever in the prolog the declaration sits.

    Breaks when the check reads only the first line, and the declaration
    follows a comment."""
    import xml.etree.ElementTree as ET

    def parsed(*args, **kwargs):
        raise AssertionError("the export reached xml.etree")

    monkeypatch.setattr(ET, "fromstring", parsed)
    monkeypatch.setattr(ET, "parse", parsed)
    valid = _export(_item(1, slug="one"))
    head, rest = valid.split("\n", 1)
    nested = ('<!DOCTYPE rss [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>\n')
    for text in (head + "\n<!-- a comment first -->\n" + nested + rest,
                 head + "\n" + '<!DOCTYPE rss SYSTEM "x.dtd">\n' + rest,
                 head + "\n<!-- one -->\n<!ENTITY lone 'x'>\n" + rest):
        export = tmp_path / "export.xml"
        export.write_text(text, encoding="utf-8")
        with pytest.raises(ImportStopped, match="not a WordPress export Pressless can read"):
            pressless_import.read(export)


def test_a_post_body_naming_a_doctype_is_still_read(tmp_path):
    """The refusal reads the prolog, not the body: a post quoting an HTML
    page's `<!DOCTYPE html>` inside its CDATA is still an export."""
    export = tmp_path / "export.xml"
    export.write_text(_export(_item(1, slug="one", body="<p>&lt;!DOCTYPE html&gt;</p>"
                                    "<!DOCTYPE html>")), encoding="utf-8")
    assert pressless_import.read(export).channel.find("item") is not None


def test_waiting_posts_arrive_as_drafts(tmp_path):
    """PRESS-0125 INV-9: pending and scheduled posts arrive as drafts, each
    listed with how it was waiting.

    Breaks when _items keeps its three statuses."""
    export, originals, into = _world(tmp_path, _export(
        _item(1, status="pending", slug="for-review"),
        _item(2, status="future", slug="scheduled", date="2031-02-03 04:05:00"),
        _item(3, status="draft", slug="plain-draft"),
    ))

    report = _run(export, originals, into)

    assert sorted(store.list_slugs(into, draft=True)) == ["for-review", "plain-draft",
                                                          "scheduled"]
    assert sorted(report.waiting) == [("for-review", ""),
                                      ("scheduled", "2031-02-03 04:05")], (
        f"each waiting post is listed with what it waited for: {report.waiting!r}"
    )


def test_a_dangling_reply_is_carried(tmp_path):
    """PRESS-0125 INV-10: a reply whose parent is not among the comments
    carried is written at the top level and listed.

    Breaks when the reply is dropped, or written as is and refused."""
    export, originals, into = _world(tmp_path, _export(
        _item(1, slug="one", comments=[_comment(101), _comment(102, parent="999")]),
    ))

    report = _run(export, originals, into)

    comments = store.read_comments(store.comments_path_for(into, "one"))
    assert [(c.identifier, c.parent) for c in comments] == [("101", ""), ("102", "")]
    assert any("102" in what for what in _whats(report, "one")), report.dropped


def test_a_comment_that_cannot_be_held_is_listed_and_skipped(tmp_path):
    """PRESS-0125 § 4.3: a comment whose date cannot be read, or whose
    identifier is empty or repeated, is listed and skipped; Import carries on."""
    export, originals, into = _world(tmp_path, _export(
        _item(1, slug="one", comments=[
            _comment(101), _comment(102, date="not a date"), _comment(""),
            _comment(101, content="the same identifier again")]),
    ))

    report = _run(export, originals, into)

    comments = store.read_comments(store.comments_path_for(into, "one"))
    assert [c.identifier for c in comments] == ["101"]
    assert comments[0].body == "Lovely.", "the first of a repeated identifier is kept"
    assert len([w for w in _whats(report, "one") if "comment" in w]) == 3, report.dropped


def test_script_and_style_are_dropped_and_listed():
    """PRESS-0125 INV-11: script and style contents never reach a body, and
    each is listed; list items, cells, rules and preformatted lines each keep
    their own line in the conversion, as `visible_lines` sees them.

    Breaks when only one of the two functions gains the splits."""
    text, dropped = convert("<p>a</p><script>var shown = 1;</script><style>p {}</style>"
                            "<p>b</p>", _by_address, _by_id)
    assert "shown" not in text and "{}" not in text, text
    assert any(what.startswith("code the old site ran") for what in dropped), dropped
    assert any(what.startswith("styling code") for what in dropped), dropped

    for markup in ("<ul><li>one</li><li>two</li></ul>",
                   "<table><tr><td>one</td><td>two</td></tr></table>",
                   "<p>one</p><hr><p>two</p>",
                   "<pre>one\ntwo</pre>"):
        text, _dropped = convert(markup, _by_address, _by_id)
        shown = visible_lines(render(text, lambda name: name))
        assert shown == ("one", "two") == visible_lines(markup), (markup, text, shown)


def test_a_classic_post_keeps_its_paragraphs():
    """PRESS-0125 INV-8: a classic body keeps its paragraphs; block content
    converts as it is.

    Breaks when `is_markup` decides, so the `em` makes it one paragraph."""
    from pressless_import import autop, wordpress_markup

    classic = "One <em>word</em>.\n\nTwo."
    text, _dropped = convert(classic, _by_address, _by_id, markup=wordpress_markup)
    assert text == "One *word*.\n\nTwo.", text
    assert visible_lines(autop(classic)) == ("One word.", "Two.")

    blocks = ("<!-- wp:paragraph --><p>One <em>word</em>.\n\nTwo.</p><!-- /wp:paragraph -->")
    text, _dropped = convert(blocks, _by_address, _by_id, markup=wordpress_markup)
    assert text == "One *word*. Two.", f"block content converts as it is: {text!r}"

    assert autop("a\nb") == "<p>a<br>\nb</p>", "a lone newline is a line break"
    assert autop("<pre>a\n\nb</pre>") == "<pre>a\n\nb</pre>", "pre is left alone"
    assert autop("<ul>\n<li>a</li>\n</ul>\n\nNext") == "<ul>\n<li>a</li>\n</ul>\n<p>Next</p>"


# ------------------------------------ PRESS-0125: the Import anyone runs ----


def _bring(tmp_path: Path, export_text: str, media: dict[str, bytes] | None = None, *,
           unfetched: dict[str, str] | None = None, look: str = "meadow"):
    """bring_in over a site folder holding the export and `media` in its own
    import folder, as the wizard leaves them."""
    from pressless_import import bring_in

    site = tmp_path / "site"
    held = site / "import"
    _files(held / "media", media or {})
    (held / "export.xml").write_text(export_text, encoding="utf-8")
    report = bring_in(held / "export.xml", held / "media", site, look,
                      unfetched=unfetched or {})
    return site, report


def _jpeg() -> bytes:
    import io

    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (4, 3), "teal").save(out, "JPEG")
    return out.getvalue()


def _meta(key, value):
    return (f"<wp:postmeta><wp:meta_key><![CDATA[{key}]]></wp:meta_key>"
            f"<wp:meta_value><![CDATA[{value}]]></wp:meta_value></wp:postmeta>")


def test_a_missing_original_is_listed_and_the_entry_carried(tmp_path):
    """PRESS-0125 INV-5: a file that cannot be had never stops Import -- one
    attachment answering 404 is listed, its entry is written with no
    `{photo:` mark, and the site builds.

    Breaks when the mark is written, so every publish stops on it."""
    from test_builder import _settings
    from test_importer_fetch import GLOBAL, _Answer, _Network

    from pressless import builder
    from pressless_import import fetch, read

    export_text = _export(
        _item(20, kind="attachment", status="inherit", attachment="2012/05/gone.jpg"),
        _item(21, kind="attachment", status="inherit", attachment="2012/05/here.jpg"),
        _item(1, slug="pictures", body=f'<p>x</p><img src="{UPLOADS}/2012/05/gone.jpg">'
                                       f'<img src="{UPLOADS}/2012/05/here.jpg">'),
    )
    export = tmp_path / "export.xml"
    export.write_text(export_text, encoding="utf-8")
    base = f"{SITE_HOST}/wp-content/uploads/2012/05"
    network = _Network({SITE_HOST: [GLOBAL]}, {f"{base}/gone.jpg": _Answer(404),
                                               f"{base}/here.jpg": _Answer(200, _jpeg())})
    fetched = tmp_path / "fetched"
    missing = fetch.fetch_all(read(export), fetched, lambda: 10**12,
                              resolve=network.resolve, connect=network.connect)

    site, report = _bring(tmp_path, export_text,
                          {path.relative_to(fetched).as_posix(): path.read_bytes()
                           for path in fetched.rglob("*") if path.is_file()},
                          unfetched=missing)

    body = store.read(store.path_for(site, "pictures", draft=False)).body
    assert "{photo: here.jpg}" in body and "{photo: gone" not in body, body
    assert dict(report.unfetched)["2012/05/gone.jpg"] == "the old site answered 404", (
        report.unfetched)
    builder.build(site, _settings(site_folder=site), tmp_path / "built")
    assert (tmp_path / "built" / "photographs").is_dir()


def test_a_media_zip_fills_gaps_only(tmp_path):
    """PRESS-0125 INV-6: a media download fills only missing places, matched
    by place; a member that would leave import/media/ refuses the download.

    Breaks when members are matched by bare name."""
    import zipfile

    from pressless_import import unpack_media

    media = tmp_path / "media"
    _files(media, {"2012/05/fetched.jpg": b"fetched"})
    missing = ("2012/05/fetched.jpg", "2013/06/gap.jpg", "2014/07/other.jpg")

    def download(*members) -> Path:
        made = tmp_path / f"media-{len(list(tmp_path.glob('media-*')))}.zip"
        with zipfile.ZipFile(made, "w") as out:
            for member in members:
                if isinstance(member, zipfile.ZipInfo):
                    out.writestr(member, "x")
                else:
                    out.writestr(member, f"from the download: {member}")
        return made

    link = zipfile.ZipInfo("uploads/2013/06/gap.jpg")
    link.external_attr = 0o120777 << 16
    for refused in (download("../x.jpg"), download("/abs.jpg"), download(link),
                    download("a\\..\\b.jpg")):
        with pytest.raises(ImportStopped):
            unpack_media(refused, media, missing, lambda: 10**9)
        assert not (media / "2013").exists(), "a refused download writes nothing"

    filled = unpack_media(download("wp-content/uploads/2012/05/fetched.jpg",
                                   "elsewhere/gap.jpg", "uploads/2013/06/gap.jpg",
                                   "2014/07/other.jpg.bak"),
                          media, missing, lambda: 10**9)

    assert filled == ("2013/06/gap.jpg",), filled
    assert (media / "2012/05/fetched.jpg").read_bytes() == b"fetched"
    assert (media / "2013/06/gap.jpg").read_text() == "from the download: uploads/2013/06/gap.jpg"
    assert not (media / "2014").exists()
    with pytest.raises(ImportStopped):
        unpack_media(download("uploads/2014/07/other.jpg"), media, missing, lambda: 3)


def test_a_stop_leaves_the_store_empty(tmp_path):
    """PRESS-0125 INV-7: a Store refusal while writing leaves the Store
    holding no site, and the fetched files where they were.

    Breaks when files are written straight into the site's folder."""
    with pytest.raises(ImportStopped):
        _bring(tmp_path, _export(
            _item(20, kind="attachment", status="inherit", attachment="2012/05/a.jpg"),
            _item(1, slug="one"), _item(2, slug="two", categories=("a,b",))),
            {"2012/05/a.jpg": _jpeg()})
    site = tmp_path / "site"
    assert not store.holds_a_site(site)
    assert not (site / "import" / "work").exists()
    assert (site / "import" / "media" / "2012" / "05" / "a.jpg").is_file(), (
        "a fetched file is never lost to a stop")


def test_a_stop_during_the_moves_finishes_next_start(tmp_path, monkeypatch):
    """PRESS-0125 INV-7: a stop part way through the moves leaves
    import/moving, and finishing them later gives the whole site."""
    import os

    import pressless_import

    real = os.rename
    calls = []

    def flaky(source, target):
        if (tmp_path / "site" / "import" / "moving").exists():
            calls.append(target)
            if len(calls) == 2:
                raise OSError(5, "the drive went away")
        return real(source, target)

    monkeypatch.setattr(os, "rename", flaky)
    export_text = _export(
        _item(20, kind="attachment", status="inherit", attachment="2012/05/a.jpg"),
        _item(1, slug="one", comments=[_comment(101)]),
        _item(5, kind="page", slug="about", title="About"))
    with pytest.raises(ImportStopped):
        _bring(tmp_path, export_text, {"2012/05/a.jpg": _jpeg()})
    site = tmp_path / "site"
    assert (site / "import" / "moving").is_file()
    monkeypatch.setattr(os, "rename", real)

    assert pressless_import.finish(site) is None

    assert store.list_slugs(site, draft=False) == ("one",)
    assert store.list_photographs(site) == ("a.jpg",)
    assert store.list_html(site, store.PAGES_FOLDER) == ("index",), "the one page is the front"
    assert store.read_comments(store.comments_path_for(site, "one"))
    for gone in ("moving", "work", "media"):
        assert not (site / "import" / gone).exists(), gone
    assert (site / "import" / "export.xml").is_file()


_PAGES_EXPORT = (
    _item(10, kind="page", slug="welcome", title="A site", menu_order=2,
          body=f'<p>Hello.</p><img src="{UPLOADS}/2012/05/a-300x200.jpg" alt="">'
               f'<a href="{UPLOADS}/2012/05/notes.pdf">notes</a>'),
    _item(11, kind="page", slug="about", title="About", menu_order=1,
          body=f'<!-- wp:paragraph --><p>Us.</p><!-- /wp:paragraph -->'
               f'<img src="{UPLOADS}/2012/05/gone.jpg">'),
    _item(12, kind="page", status="trash", slug="binned", title="Binned"),
    _item(20, kind="attachment", status="inherit", attachment="2012/05/a.jpg"),
    _item(21, kind="attachment", status="inherit", attachment="2012/05/notes.pdf"),
    _item(1, slug="one", body="Words.\n\nMore."),
    _item(30, kind="wp_block", slug="reused"), _item(31, kind="wp_block", slug="again"),
)


def test_pages_come_across_in_the_starter_shape(tmp_path):
    """PRESS-0125 § 4.6 and § 4.7: each page in new_page's shape with the
    look's stylesheet; the page titled as the site sits at the root; an
    uploads address Import holds points at the Store's copy, and one it does
    not hold stays and is listed; the furniture, templates, look and journal
    are written."""
    from pressless import blocks, look

    site, report = _bring(tmp_path, _export(*_PAGES_EXPORT),
                          {"2012/05/a.jpg": _jpeg(), "2012/05/notes.pdf": b"%PDF- notes"})

    assert sorted(store.list_html(site, store.PAGES_FOLDER)) == ["about", "index"]
    index = store.read_html(store.html_path_for(site, store.PAGES_FOLDER, "index"))
    about = store.read_html(store.html_path_for(site, store.PAGES_FOLDER, "about"))
    assert 'href="look/style.css"' in index and 'href="../look/style.css"' in about
    assert 'src="photographs/a.jpg"' in index and 'href="files/notes.pdf"' in index, index
    assert f"{UPLOADS}/2012/05/gone.jpg" in about
    assert any("gone.jpg" in what for d in report.dropped for what in [d.what]
               if d.slug == "pages/about"), report.dropped
    assert blocks.read("index", index) is not None, "Blocks reads the page's area"
    assert store.list_photographs(site) == ("a.jpg",) and store.list_files(site) == ("notes.pdf",)
    for name in ("header", "footer", "navigation"):
        assert store.html_path_for(site, store.FURNITURE_FOLDER, name).is_file(), name
    assert store.list_templates(site), "the starter's templates"
    assert look.read(site) == look.defaults("meadow")
    assert store.journal_on(site)
    entry = store.read(store.path_for(site, "one", draft=False))
    assert entry.body == "Words.\n\nMore.", "a classic post keeps its paragraphs"
    assert dict(report.other_types) == {"wp_block": 2}, report.other_types
    assert report.pages == ("about", "index")


def test_an_export_with_no_pages_or_posts_takes_the_starter_home(tmp_path):
    """§ 4.6: where the export holds no page, the starter's index is written;
    with no post, the journal is off (§ 6)."""
    site, _report = _bring(tmp_path, _export(_item(5, kind="page", status="trash",
                                                   slug="binned")))
    assert store.list_html(site, store.PAGES_FOLDER) == ("index",)
    assert not store.journal_on(site)


def test_bring_in_refuses_a_store_holding_a_site(tmp_path):
    """PRESS-0125 INV-1, its Import half: nothing is written over a site."""
    site = tmp_path / "site"
    site.mkdir()
    store.write(site, store.Entry(slug="his", title="", date=__import__("datetime").datetime(
        2020, 1, 2), categories=(), tags=(), body="Words.", extra=()), draft=False)
    with pytest.raises(ImportStopped):
        _bring(tmp_path, _export(_item(1, slug="one")))
    assert store.list_slugs(site, draft=False) == ("his",)


def _nav_item(post_id, order, *, title="", kind="post_type", object_id="", url="",
              parent="0", menu="main"):
    return _item(post_id, kind="nav_menu_item", title=title, menu_order=order,
                 extra=(f'<category domain="nav_menu" nicename="{menu}">'
                        f"<![CDATA[{menu.title()}]]></category>"
                        + _meta("_menu_item_type", kind)
                        + _meta("_menu_item_object_id", object_id)
                        + _meta("_menu_item_url", url)
                        + _meta("_menu_item_menu_item_parent", parent)))


def test_the_menu_points_at_carried_pages(tmp_path):
    """PRESS-0125 INV-13: the menu's links reach carried pages and entries,
    read by menu.links, from either source.

    Breaks when links keep the old site's addresses."""
    from pressless import menu

    pages_and_post = (
        _item(10, kind="page", slug="home", title="Home"),
        _item(11, kind="page", slug="about", title="About"),
        _item(1, slug="one", title="A post", date="2012-05-01 10:00:00"),
    )
    expected = [("Home", "{{UP}}index.html"), ("About", "{{UP}}pages/about.html"),
                ("A post", "{{UP}}blog/2012/05/01/one/index.html"),
                ("Elsewhere", "https://elsewhere.example.org/")]
    links = (
        '<!-- wp:navigation-link {"label":"Home","type":"page","id":10,'
        f'"url":"{SITE}/","kind":"post-type"}} /-->'
        '<!-- wp:navigation-link {"label":"About","type":"page","id":11,'
        f'"url":"{SITE}/about/","kind":"post-type"}} /-->'
        '<!-- wp:navigation-link {"label":"A post","type":"post","id":1,'
        f'"url":"{SITE}/one/","kind":"post-type"}} /-->'
        '<!-- wp:navigation-link {"label":"Elsewhere",'
        '"url":"https://elsewhere.example.org/","kind":"custom"} /-->')
    sources = {
        "wp_navigation": (_item(40, kind="wp_navigation", title="Header", body=links),),
        "nav_menu_item": (
            _nav_item(50, 1, object_id="10"), _nav_item(51, 2, object_id="11"),
            _nav_item(52, 3, object_id="1"),
            _nav_item(53, 4, title="Elsewhere", kind="custom",
                      url="https://elsewhere.example.org/"),
            _nav_item(54, 5, title="Under about", object_id="11", parent="51"),
            _nav_item(60, 1, object_id="10", menu="footer")),
    }
    for name, items in sources.items():
        site, report = _bring(tmp_path / name, _export(*pages_and_post, *items))
        navigation = store.read_html(store.html_path_for(site, store.FURNITURE_FOLDER,
                                                         "navigation"))
        read = menu.links(navigation)
        assert [link for link in read if link[0] != "Under about"] == expected, (name, read)
        assert report.menus, (name, report)
    assert report.menus == ("Main", "Footer"), report.menus
    assert read[2] == ("Under about", "{{UP}}pages/about.html"), "a child follows its parent"
    assert any("Under about" in d.what for d in report.dropped), report.dropped


@pytest.mark.parametrize("status", ["draft", "private", "pending", "future"])
def test_an_unpublished_page_arrives_as_a_draft(tmp_path, status):
    """PRESS-0125 INV-15: a page WordPress had not published becomes a draft
    entry, listed, beside a published page that becomes a Pressless page;
    with no post carried, the journal stays off (§ 4.7).

    Breaks when § 4.6 takes every page status, so the page is published at
    the next publish."""
    site, report = _bring(tmp_path, _export(
        _item(1, kind="page", slug="about", title="About", body="<p>Hello.</p>"),
        _item(2, kind="page", status=status, slug="secret", title="Secret",
              body="<p>Only for me.</p>")))

    assert store.list_html(site, store.PAGES_FOLDER) == ("index",)
    assert store.list_slugs(site, draft=True) == ("secret",)
    assert store.read(store.path_for(site, "secret", draft=True)).body == "Only for me."
    assert report.pages == ("index",) and report.drafts == 1
    assert any(d.slug == "secret" and "page" in d.what for d in report.dropped), report.dropped
    assert not store.journal_on(site)


def test_a_draft_with_no_slug_takes_its_title(tmp_path):
    """PRESS-0125 INV-16 (§ 4.5): an item arriving as a draft, an unpublished
    page included, with an empty post_name takes its title's slug; a
    published post with an empty post_name keeps PRESS-0007's post id.

    Breaks when the post id is the fallback for both, or the title for both."""
    site, _report = _bring(tmp_path, _export(
        _item(7, status="draft", title="Half written"),
        _item(8, kind="page", status="private", title="Private notes"),
        _item(9, title="Live one")))

    assert store.list_slugs(site, draft=True) == ("half-written", "private-notes")
    assert store.list_slugs(site, draft=False) == ("9",)


def test_a_featured_image_opens_the_body(tmp_path):
    """PRESS-0125 INV-17 (§ 4.5): a post's featured image is its body's first
    line; one the body already shows, captioned, is not added again; one not
    brought in is listed.

    Breaks when _thumbnail_id is not read, the mark is written twice, or the
    missing image is not listed."""
    site, report = _bring(tmp_path, _export(
        _item(20, kind="attachment", status="inherit", attachment="2012/05/a.jpg"),
        _item(21, kind="attachment", status="inherit", attachment="2012/05/b.jpg"),
        _item(22, kind="attachment", status="inherit", attachment="2012/05/gone.jpg"),
        _item(1, slug="one", body="<p>Words.</p>", extra=_meta("_thumbnail_id", "20")),
        _item(2, slug="two", extra=_meta("_thumbnail_id", "21"),
              body=f'<figure><img src="{UPLOADS}/2012/05/b.jpg">'
                   "<figcaption>Late light</figcaption></figure><p>More.</p>"),
        _item(3, slug="three", body="<p>Plain.</p>", extra=_meta("_thumbnail_id", "22"))),
        {"2012/05/a.jpg": _jpeg(), "2012/05/b.jpg": _jpeg()})

    def body(slug):
        return store.read(store.path_for(site, slug, draft=False)).body

    assert body("one") == "{photo: a.jpg}\n\nWords.", body("one")
    assert body("two").count("{photo: b.jpg") == 1, body("two")
    assert body("three") == "Plain.", body("three")
    assert any(d.slug == "three" and "featured image" in d.what for d in report.dropped), (
        report.dropped)
