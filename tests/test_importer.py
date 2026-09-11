# INV-1 to INV-4 and INV-6 to INV-10 for PRESS-0007 (Import), and INV-5's
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
          comments=(), attachment=""):
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


def _world(tmp_path: Path, export_text: str, originals: dict[str, bytes] | None = None):
    """The export file, an originals folder holding `originals`, and an INTO
    that does not exist yet."""
    export = tmp_path / "export.xml"
    export.write_text(export_text, encoding="utf-8")
    folder = tmp_path / "originals"
    folder.mkdir()
    for upload_path, data in (originals or {}).items():
        target = folder / upload_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return export, folder, tmp_path / "pressless-data"


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
        _item(5, kind="page", slug="about"),
        _item(6, kind="attachment", status="inherit", slug="a-picture",
              attachment="2012/05/a.jpg"),
        _item(7, kind="nav_menu_item", slug="menu"),
    ), {"2012/05/a.jpg": b"a"})

    report = run(export, originals, into)

    assert store.list_slugs(into, draft=False) == ("published-one",), (
        f"only the published post belongs in published: "
        f"{store.list_slugs(into, draft=False)!r}"
    )
    drafts = store.list_slugs(into, draft=True)
    assert sorted(drafts) == ["a-draft", "a-private", "about"], (
        f"the draft, the private post and the page arrive as drafts, once each: {drafts!r}"
    )
    assert (report.published, report.drafts) == (1, 3), f"the report's counts: {report!r}"


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

    report = run(export, originals, into)

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

    report = run(export, originals, into)

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
    ('[gallery ids="1,2"]', "{photo: a.jpg}\n{photo: b.jpg}", None),
    ("<blockquote><p>a<br>b</p><p>c</p></blockquote>", "> a\n> b\n>\n> c", None),
    ('<figure class="wp-block-pullquote"><blockquote><p>x</p></blockquote></figure>', "> x", None),
    ('<iframe src="https://video.example.org/v/1"></iframe>',
     "{link: https://video.example.org/v/1}https://video.example.org/v/1{/}", None),
    ('<img src="https://elsewhere.example.org/p.jpg">',
     "{link: https://elsewhere.example.org/p.jpg}https://elsewhere.example.org/p.jpg{/}",
     "attachment"),
    (f'<p><a href="{UPLOADS}/2012/05/song.mp3">my song</a></p>', "my song", "attachment"),
    (f'<video src="{UPLOADS}/2012/05/clip.mp4"></video>', "", "attachment"),
    ("<div>a</div><div>b</div>", "a\n\nb", None),
    ("<h2>A heading</h2><p>x</p>", "A heading\n\nx", "heading"),
    ("<figure><p>x</p></figure>", "x", None),
    ("<p>a&nbsp;b</p>", "a&nbsp;b", None),
    # The wrap-mark rules: whitespace moves outside, a run never crosses a
    # line, bold and italic together are bold, and a newline is a space.
    ("<p><strong> word</strong></p>", "**word**", None),
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
    ]
    for markup, lines in cases:
        assert visible_lines(markup) == lines, (
            f"{markup!r} shows a reader {lines!r}, got {visible_lines(markup)!r}"
        )


# ------------------------------------------------------------ INV-6 -------


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

    report = run(export, originals, into)

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
        ]),
    ))

    report = run(export, originals, into)

    draft_comments = store.read_comments(store.comments_path_for(into, "same-31"))
    assert [(c.identifier, c.parent) for c in draft_comments] == [("101", ""), ("102", "101")], (
        f"the approved comment and its reply, 0 read as top level, and neither the "
        f"pingback nor the unapproved one: {draft_comments!r}"
    )
    live_comments = store.read_comments(store.comments_path_for(into, "same"))
    assert [c.identifier for c in live_comments] == ["501"], f"{live_comments!r}"
    assert report.comments == 3, f"the report's count: {report!r}"

    written = b"".join(path.read_bytes() for path in into.rglob("*") if path.is_file())
    for n in range(1, 6):
        for value in contact(n).values():
            assert value.encode() not in written, (
                f"a commenter's contact value reached a file Import wrote (fixture {n})"
            )


# ------------------------------------------------------------ INV-8 -------


def _stops(tmp_path, export, originals, into):
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(ImportStopped):
        run(export, originals, into)
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
    assert main([str(export), str(originals), str(into)]) == 1
    said = capsys.readouterr()
    assert str(tmp_path) not in said.out + said.err, (
        f"main's words never name a full filesystem path: {said!r}"
    )

    # A missing original stops it before anything is made.
    missing = tmp_path / "missing"
    missing.mkdir()
    export, originals, into = _world(missing, _export(
        _item(20, kind="attachment", status="inherit", attachment="2012/05/a.jpg"),
        _item(1, slug="one"),
    ))
    _stops(missing, export, originals, into)
    assert not into.exists()

    # A refusal the Store raises while writing -- a reply whose parent the
    # export does not carry -- stops it and removes the folder of step 5.
    refused = tmp_path / "refused"
    refused.mkdir()
    export, originals, into = _world(refused, _export(
        _item(1, slug="one", comments=[_comment(101, parent="999")]),
    ))
    _stops(refused, export, originals, into)
    assert not into.exists()


# ------------------------------------------------------------ INV-9 -------


def test_what_is_dropped_is_reported(tmp_path):
    """INV-9: what Import could not convert is in Report.dropped, by entry.

    Breaks when an unknown tag is removed without a record (spec §5)."""
    body = (
        "<table><tr><td>cell</td></tr></table>"
        '<p class="lead" style="font-size:2em">big</p>'
        '<!-- wp:social-link {"url":"https://social.example.org/me","service":"x"} /-->'
    )
    export, originals, into = _world(tmp_path, _export(_item(40, slug="tabled", body=body)))

    report = run(export, originals, into)

    written = store.read(store.path_for(into, "tabled", draft=False)).body
    assert "cell" in written and "big" in written, f"the words are kept: {written!r}"
    whats = _whats(report, "tabled")
    # One word per kind §4.3 names: an unknown tag, a style that is not a hex
    # colour, an attribute the table does not use, and a social link.
    for word in ("table", "font-size", "class", "https://social.example.org/me"):
        assert any(word in what for what in whats), (
            f"{word!r} must be listed against its entry: {report.dropped!r}"
        )


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
    "pressless", "pressless.marks", "pressless.store",
}


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def test_import_reaches_no_network():
    """INV-10: Import reaches no network -- every module of pressless_import
    imports only what the allowlist names, compared by full dotted name, so
    `urllib.parse` is admitted and `urllib.request` is not.

    Breaks when a picture is fetched from the old site (spec §5)."""
    package = Path(pressless_import.__file__).parent
    modules = sorted(package.glob("*.py"))
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
