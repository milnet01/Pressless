"""PRESS-0215: a page held as ready-made sections (docs/specs/PRESS-0215-blocks.md)."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pressless import blocks, builder, starter, store
from pressless.blocks import Section

FORMS = Path(__file__).parent / "features" / "blocks" / "forms"
OPEN, CLOSE = "<!-- pressless:page -->", "<!-- /pressless:page -->"


def _page(*sections: str, before="<main>", after="</main>\n") -> str:
    return before + OPEN + "\n" + "\n".join(sections) + "\n" + CLOSE + after


def _picture(number: int, **extra: str) -> Section:
    return Section(blocks.PICTURE, {"src": f"{number}.jpg", "alt": f"picture {number}", **extra})


# One section per kind and per optional field (INV-3).
EVERY_KIND = (
    Section(blocks.TEXT, {"html": 'A <a href="x.html">link</a> &amp; <strong>b</strong> '
                                  "<em>i</em><br>end"}),
    Section(blocks.TEXT, {"html": ""}),
    *(Section(blocks.HEADING, {"level": str(level), "html": "A heading"}) for level in range(1, 7)),
    _picture(1),
    _picture(2, width="640"),
    _picture(3, height="480"),
    _picture(4, width="640", height="480", caption='A <a href="mailto:a@example.org">cap</a>'),
    Section(blocks.PICTURES, parts=((_picture(5), _picture(6)),)),
    Section(blocks.BUTTON, {"href": "https://example.org/?a=1&b=2", "label": 'Go "now" & <run>'}),
    Section(blocks.VIDEO, {"src": "files/a film.mp4"}),
    Section(blocks.VIDEO, {"youtube": "dQw4w9WgXc_"}),
    Section(blocks.MUSIC, {"src": "files/a.mp3"}),
    Section(blocks.DOWNLOAD, {"href": "files/a.pdf", "label": "A file"}),
    Section(blocks.COLUMNS, parts=((Section(blocks.TEXT, {"html": "left"}),),
                                   (Section(blocks.HEADING, {"level": "2", "html": "right"}),
                                    _picture(7)))),
    Section(blocks.COLUMNS, parts=tuple((Section(blocks.TEXT, {"html": str(n)}),)
                                        for n in range(4))),
)


def _starter_pages(tmp_path: Path) -> dict[str, str]:
    """Each starter page, an added page and the Privacy page, with a site
    name and a page title holding both quotes."""
    folder = tmp_path / "data"
    folder.mkdir(parents=True)
    starter.fill(folder, 'Ann\'s "Site"')
    pages = {name: store.read_html(store.html_path_for(folder, store.PAGES_FOLDER, name))
             for name in ("index", "about")}
    pages["added"] = starter.new_page("added", 'It\'s "new"', ("look/style.css",))
    pages["privacy"] = starter.privacy_page('Ann\'s "Site"', ("look/style.css",))
    return pages


def _adopted(tmp_path: Path, *, with_source: bool = False) -> dict[str, str | tuple]:
    """ADOPTABLE and each starter page with its marks removed, each adopted;
    with `with_source`, beside the page it was adopted from."""
    sources = {"fixture": ADOPTABLE, **{name: blocks.unmarked(name, text) for name, text
                                        in _starter_pages(tmp_path / "starter").items()}}
    out = {}
    for name, text in sources.items():
        adopted = blocks.adopt(text, builder.furniture_spans(name, text))
        assert adopted is not None and adopted != text, name
        out[name] = (text, adopted) if with_source else adopted
    return out


# Pages whose marks do not pair, each by a different fault of §4.3 step 3.
FAULTS = (
    _page("<!-- pressless:text --><p>no close</p>"),
    _page("<p>a</p><!-- /pressless:text -->"),
    _page("<!-- pressless:text --><p>a</p><!-- /pressless:heading -->"),
    _page("<!-- pressless:text --><p>a</p>\n  <!-- pressless:heading --><h2>b</h2>"
          "<!-- /pressless:heading -->"),
    _page("loose words  ", "<!-- pressless:unknown -->x<!-- /pressless:unknown -->"),
    _page("<!-- pressless:column --><p>a</p><!-- /pressless:column -->"),
    _page("<!-- pressless:columns --><div class=\"pressless-columns\">"
          "<!-- pressless:column --><div class=\"pressless-column\">"
          "<!-- pressless:columns --><div class=\"pressless-columns\"></div>"
          "<!-- /pressless:columns --></div><!-- /pressless:column --></div>"
          "<!-- /pressless:columns -->"),
    _page("<!-- pressless:pictures --><div class=\"pressless-pictures\">"
          "<p>not a picture</p></div><!-- /pressless:pictures -->"),
    _page(""),
    OPEN + CLOSE,
    "\r\n" + OPEN + "\r\n\t<!-- pressless:text --><p>x</p><!-- /pressless:text -->\r\n" + CLOSE,
    _page("<!-- pressless:text --><p>a</p><!-- /pressless:text --><!-- pressless:page -->"),
)


# ------------------------------------------------------------------ INV-1 ---


def test_every_page_writes_back_as_it_was(tmp_path):
    """INV-1. Breaks when a gap, an unmarked run or a code section's source is
    re-spelled on the way through."""
    pages = [*_starter_pages(tmp_path).values(), *FAULTS,
             *(_page(blocks.section_html(section)) for section in EVERY_KIND),
             *_adopted(tmp_path).values()]
    for text in pages:
        page = blocks.read("page", text)
        assert page is not None, text
        assert len(page.gaps) == len(page.sections) + 1
        assert blocks.write(page) == text


def test_a_mark_fault_is_kept_as_code():
    """§4.3 step 3: a stray or unpaired mark is a code run, and the stretch
    after it still reads."""
    page = blocks.read("page", FAULTS[3])
    assert [section.kind for section in page.sections] == [blocks.CODE, blocks.HEADING]
    assert page.sections[0].source == "<!-- pressless:text --><p>a</p>"
    page = blocks.read("page", FAULTS[4])
    assert [section.source for section in page.sections] == [
        "loose words", "<!-- pressless:unknown -->x<!-- /pressless:unknown -->"]
    assert page.gaps[1] == "  \n"
    for text in (FAULTS[5], FAULTS[6], FAULTS[7]):
        assert [s.kind for s in blocks.read("page", text).sections] == [blocks.CODE], text
    assert blocks.read("page", "<main>" + OPEN + "</main>") is None
    assert blocks.read("page", "<main>" + CLOSE + OPEN + "</main>") is None


# ------------------------------------------------------------------ INV-2 ---


def test_a_changed_section_reads_as_code():
    """INV-2. Breaks when §4.3 step 2 compares anything looser than bytes."""
    written = blocks.section_html(Section(blocks.TEXT, {"html": "Words"}))
    for changed in (written.replace("<p>", '<p class="x">'),
                    written.replace("Words", "<span>Words</span>"),
                    written.replace("Words", "Words &#8217;"),
                    written.replace("<p>", "<P>").replace("</p>", "</P>"),
                    written.replace("<p>", "<p >")):
        page = blocks.read("page", _page(changed))
        assert page.sections == (Section(blocks.CODE, source=changed),), changed
    picture = blocks.section_html(_picture(1, width="9"))
    button = blocks.section_html(Section(blocks.BUTTON, {"href": "a.html", "label": "A & B"}))
    for changed in (picture.replace('src="1.jpg" alt="picture 1"', 'alt="picture 1" src="1.jpg"'),
                    picture.replace('"1.jpg"', "'1.jpg'"),
                    picture.replace(">", " >", 2).replace(" >", ">", 1),
                    button.replace("&amp;", "&#38;"),
                    button.replace('"a.html"', '"a&#46;html"')):
        assert changed != picture and changed != button
        page = blocks.read("page", _page(changed))
        assert page.sections == (Section(blocks.CODE, source=changed),), changed
    hand_spaced = blocks.section_html(EVERY_KIND[-1]).replace("</div><!-- /pressless:column -->",
                                                              "</div>\n<!-- /pressless:column -->")
    assert blocks.read("page", _page(hand_spaced)).sections[0].kind == blocks.CODE


# ------------------------------------------------------------------ INV-3 ---


def test_every_kind_reads_back_as_written():
    """INV-3. Breaks when a field is written but not read back."""
    assert {section.kind for section in EVERY_KIND} == set(blocks.KINDS)
    for section in EVERY_KIND:
        page = blocks.read("page", _page(blocks.section_html(section)))
        assert page.sections == (section,), section
    together = _page(*(blocks.section_html(section) for section in EVERY_KIND))
    assert blocks.read("page", together).sections == EVERY_KIND
    optional = blocks.read("page", _page(blocks.section_html(_picture(1))))
    assert set(optional.sections[0].fields) == {"src", "alt"}


# ------------------------------------------------------------------ INV-4 ---


def test_every_earlier_form_still_reads():
    """INV-4. One frozen file per kind per form; a fixture is added with each
    new form and never edited. Breaks when a change to `section_html` drops
    the reader for the form it replaced."""
    files = sorted(FORMS.glob("*.html"))
    assert {path.name.split("-")[0] for path in files} == set(blocks.KINDS)
    for path in files:
        written = path.read_text(encoding="utf-8").rstrip("\n")
        page = blocks.read("page", _page(written))
        assert [section.kind for section in page.sections] == [path.name.split("-")[0]], path
        assert blocks.write(page) == _page(written)


# ------------------------------------------------------------------ INV-5 ---


class _Events(HTMLParser):
    """What HTMLParser reports, text decoded and joined, attributes as sets,
    a self-closed tag as its start tag."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.events: list[tuple] = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.events.append(("start", tag, frozenset(attrs)))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        self.events.append(("end", tag))

    def handle_data(self, data):
        if self.events and self.events[-1][0] == "data":
            self.events[-1] = ("data", self.events[-1][1] + data)
        else:
            self.events.append(("data", data))

    def handle_comment(self, data):
        self.events.append(("comment", data))

    def handle_decl(self, decl):
        self.events.append(("decl", decl))


def _meaning(text: str) -> list[tuple]:
    return _Events(text).events


ADOPTABLE = (
    "<!doctype html>\n<html><head><title>T &amp; t</title></head><body>\n"
    '  <!-- HEADER:START page="about" -->\n  <!-- HEADER:END -->\n'
    "  <main class='page'>\n"
    "    <h1>Caf&eacute; &#8217;s</h1>\n"
    "    <p>One  two\n   three &amp; <a href=pages/x.html>x</a><br/>y</p>\n"
    "    <p class=\"lead\">classed</p>\n"
    "    <p>a <b>bold</b> word</p>\n"
    "    <figure><img src='a.jpg' alt='a'></figure>\n"
    "    <img alt=\"b\" src=b.jpg width=10 height='20'/>\n"
    "    <img src=c.jpg>\n"
    "    <p><a href=\"javascript:alert(1)\">bad</a></p>\n"
    "    <script>var s = '<p>not a node</p>';</script>\n"
    "    <!-- a comment -->\n"
    "    loose words\n"
    "    <H2>Shouting</H2>\n"
    "  </main>\n"
    "  <!-- FOOTER:START -->\n  <!-- FOOTER:END -->\n</body></html>\n"
)


def test_adopting_keeps_what_the_page_shows(tmp_path):
    """INV-5. Breaks when a recognised node loses an attribute, or whitespace
    inside it is collapsed."""
    adopted = blocks.adopt(ADOPTABLE, builder.furniture_spans("about", ADOPTABLE))
    assert _meaning(blocks.unmarked("about", adopted)) == _meaning(ADOPTABLE)
    kinds = [section.kind for section in blocks.read("about", adopted).sections]
    assert kinds == [blocks.HEADING, blocks.TEXT, blocks.CODE, blocks.PICTURE, blocks.CODE,
                     blocks.HEADING]
    assert "<h1>Café ’s</h1>" in adopted
    assert '<img src="b.jpg" alt="b" width="10" height="20">' in adopted
    for name, (text, adopted) in _adopted(tmp_path, with_source=True).items():
        assert _meaning(blocks.unmarked(name, adopted)) == _meaning(text), name


def test_a_starter_page_adopts_into_the_sections_it_was_written_in(tmp_path):
    """§4.6 over §4.8: taking a starter page's published form into sections
    gives back the page Pressless wrote, spaced as adoption spaces it."""
    for name, adopted in _adopted(tmp_path).items():
        if name == "fixture":
            continue
        written = _starter_pages(tmp_path / name)[name]
        assert blocks.read(name, adopted).sections == blocks.read(name, written).sections, name


# ------------------------------------------------------------------ INV-6 ---


def test_adopting_touches_only_main():
    """INV-6. Breaks when the header markers or the head are re-spelled, or a
    second call adds a second area."""
    adopted = blocks.adopt(ADOPTABLE, builder.furniture_spans("about", ADOPTABLE))
    head, tail = ADOPTABLE.split("<main class='page'>")[0], ADOPTABLE.split("</main>")[1]
    assert adopted.startswith(head + "<main class='page'>" + OPEN)
    assert adopted.endswith(CLOSE + "</main>" + tail)
    assert blocks.adopt(adopted, builder.furniture_spans("about", adopted)) == adopted
    assert adopted.count(OPEN) == 1

    assert blocks.adopt("<body><p>no main</p></body>", ()) is None
    held = "<main><!-- HEADER:START -->\n<!-- HEADER:END --></main>"
    assert blocks.adopt(held, builder.furniture_spans("held", held)) is None
    inside = "<!-- HEADER:START --><main>x</main><!-- HEADER:END --><main><p>y</p></main>"
    assert blocks.adopt(inside, builder.furniture_spans("inside", inside)) == (
        "<!-- HEADER:START --><main>x</main><!-- HEADER:END --><main>" + OPEN
        + "<!-- pressless:text --><p>y</p><!-- /pressless:text -->" + CLOSE + "</main>")
    assert blocks.adopt("<main><p>unclosed", ()) is None


# ------------------------------------------------------------------ INV-8 ---


def test_unsafe_addresses_are_refused():
    """INV-8. Breaks when the scheme check reads the address before stripping
    and folding it, as a browser does."""
    for address in ("javascript:alert(1)", "data:text/html,x", " javascript:alert(1)",
                    "JAVASCRIPT:alert(1)", "java\tscript:alert(1)", "\x01javascript:x",
                    "vbscript:x"):
        for section in (Section(blocks.BUTTON, {"href": address, "label": "x"}),
                        Section(blocks.DOWNLOAD, {"href": address, "label": "x"}),
                        Section(blocks.MUSIC, {"src": address}),
                        Section(blocks.PICTURE, {"src": address, "alt": ""}),
                        Section(blocks.TEXT, {"html": f'<a href="{html.escape(address)}">x</a>'})):
            with pytest.raises(blocks.SectionRefused):
                blocks.section_html(section)
    with pytest.raises(blocks.SectionRefused):
        blocks.section_html(Section(blocks.VIDEO, {"src": "mailto:a@example.org"}))
    for address in ("pages/a.html", "/a", "#top", "https://example.org", "HTTP://example.org",
                    "mailto:a@example.org"):
        blocks.section_html(Section(blocks.BUTTON, {"href": address, "label": "x"}))
    written = blocks.section_html(Section(blocks.BUTTON, {"href": "a\"b", "label": "<script>"}))
    assert "<script>" not in written and "&lt;script&gt;" in written and 'a&quot;b' in written


def test_what_section_html_refuses():
    """§4.4's other refusals."""
    for section in (Section("poem", {"html": "x"}), Section("column"),
                    Section(blocks.TEXT, {}), Section(blocks.TEXT, {"html": "x", "extra": "y"}),
                    Section(blocks.TEXT, {"html": "<span>x</span>"}),
                    Section(blocks.TEXT, {"html": "a < b"}),
                    Section(blocks.TEXT, {"html": "<br/>"}),
                    Section(blocks.TEXT, {"html": "<strong>open"}),
                    Section(blocks.HEADING, {"level": "7", "html": "x"}),
                    Section(blocks.VIDEO, {"youtube": "short"}),
                    Section(blocks.VIDEO, {"youtube": "dQw4w9WgXcQ", "src": "a.mp4"}),
                    Section(blocks.PICTURE, {"src": "a.jpg", "alt": "", "caption": "<p>x</p>"}),
                    Section(blocks.COLUMNS, parts=((Section(blocks.TEXT, {"html": "x"}),),)),
                    Section(blocks.COLUMNS, parts=((),) * 5),
                    Section(blocks.COLUMNS, parts=((EVERY_KIND[-1],), ())),
                    Section(blocks.PICTURES, parts=((Section(blocks.TEXT, {"html": "x"}),),))):
        with pytest.raises(blocks.SectionRefused):
            blocks.section_html(section)
    assert blocks.section_html(Section(blocks.CODE, source="<b>x</b>")) == "<b>x</b>"


# ------------------------------------------------------------------ INV-9 ---


def test_marks_in_scripts_are_text():
    """INV-9. Breaks when marks are found by a text search over the file."""
    for hidden in (f"<script>var a = '{OPEN}<p>x</p>{CLOSE}';</script>",
                   f"<style>/* {OPEN}{CLOSE} */</style>",
                   f'<p title="{OPEN}{CLOSE}">x</p>'):
        assert blocks.read("page", hidden) is None, hidden
        assert blocks.unmarked("page", hidden) == hidden


def test_unmarked_takes_a_lone_mark_with_its_line():
    """§4.7: a mark alone on its line takes the line; any other its bytes."""
    text = ("<main>\n  " + OPEN + "\r\n  <!-- pressless:text --><p>x</p>"
            "<!-- /pressless:text -->\n  <!-- /pressless:mystery -->\n" + CLOSE + "</main>")
    assert blocks.unmarked("page", text) == "<main>\n  <p>x</p>\n</main>"
    plain = "<main><!-- pressless --><!-- PRESSLESS:PAGE --><p>x</p></main>"
    assert blocks.unmarked("page", plain) == plain


# ----------------------------------------------------------------- INV-10 ---


def test_new_pages_are_all_sections(tmp_path):
    """INV-10. Breaks when the starter's HTML drifts from `section_html`'s."""
    for name, text in _starter_pages(tmp_path).items():
        page = blocks.read(name, text)
        assert page is not None, name
        kinds = [section.kind for section in page.sections]
        assert kinds[0] == blocks.HEADING and set(kinds[1:]) == {blocks.TEXT}, (name, kinds)
        assert re.search(r"<title>[^<]*&quot;", text), name
