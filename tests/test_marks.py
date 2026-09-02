# INV-1..4, 6..8 for PRESS-0004 (Marks). Pure, no fixtures on disk, runs in
# CI. INV-5 is the archive conformance run and lives in test_marks_archive.py
# instead, because it needs a WordPress export that cannot ship in a public
# repository (docs/specs/PRESS-0004-marks.md §7).
#
# Why this exists: docs/specs/PRESS-0004-marks.md is the contract. Each test
# below is named for the invariant it locks, per that spec's §5 and §10.
from __future__ import annotations

import ast
import html.parser
import inspect
import time

import pressless.marks as marks_module
from pressless.marks import (
    MARKS,
    Line,
    Paragraph,
    Photo,
    Span,
    Text,
    parse,
    render,
)


def _no_photos(name: str) -> str:
    """A photo_src that fails loudly if a test triggers it unexpectedly.

    Every test below except the photo-specific ones passes bodies with no
    {photo: ...} mark in them, so this proves photo_src was never called.
    """
    raise AssertionError(f"photo_src should not have been called for {name!r}")


def _iter_nodes(obj):
    """Yield every Node reachable from a Document, a Block, or a Node,
    however deeply nested — the shared walk every structural test below
    needs, since Document/Block/Node are unions rather than one tree type
    (spec §4.3)."""
    if isinstance(obj, tuple):
        for item in obj:
            yield from _iter_nodes(item)
    elif isinstance(obj, Paragraph):
        for line in obj.lines:
            yield from _iter_nodes(line)
    elif isinstance(obj, Line):
        yield from _iter_nodes(obj.children)
    elif isinstance(obj, Span):
        yield obj
        yield from _iter_nodes(obj.children)
    elif isinstance(obj, (Text, Photo)):
        yield obj


class _AttrCapture(html.parser.HTMLParser):
    """Collects every `src` and `style` attribute value a real HTML parser
    sees, so escaping is checked by round-tripping through a parser rather
    than by pinning one entity spelling (§4.6 names no particular spelling,
    only the property that the value cannot break out of its attribute)."""

    def __init__(self):
        super().__init__()
        self.srcs: list[str] = []
        self.styles: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_by_name = dict(attrs)
        if "src" in attrs_by_name:
            self.srcs.append(attrs_by_name["src"])
        if "style" in attrs_by_name:
            self.styles.append(attrs_by_name["style"])


def _parsed_attrs(html_text: str) -> _AttrCapture:
    parser = _AttrCapture()
    parser.feed(html_text)
    return parser


# --------------------------------------------------------------- INV-1 ----


def test_every_newline_survives():
    """INV-1: every single newline in a paragraph produces exactly one
    <br>; no input collapses two lines into one.

    Breaks when a paragraph rule joins lines, or Line is flattened out of
    the structure (spec §5)."""
    body = "first light over the water\nstill air, no bird sings\nand the tide does not answer"
    doc = parse(body)
    assert len(doc) == 1, f"expected one paragraph block, got {len(doc)}: {doc!r}"
    (para,) = doc
    assert isinstance(para, Paragraph), f"expected a Paragraph, got {para!r}"
    assert len(para.lines) == 3, (
        f"expected 3 Line nodes for 3 newline-separated lines, "
        f"got {len(para.lines)}: {para.lines!r}"
    )

    out = render(body, _no_photos)
    assert out.count("<br>") == 2, (
        f"expected 2 <br> for 3 lines, got {out.count('<br>')} in: {out!r}"
    )
    for line in ("first light over the water", "still air, no bird sings",
                 "and the tide does not answer"):
        assert line in out, f"line {line!r} is missing from the rendered output: {out!r}"


# --------------------------------------------------------------- INV-2 ----


def test_censored_words_and_divider_are_literal():
    """INV-2: a delimiter that does not form a complete mark on its own
    line is rendered as literal text, byte for byte.

    Fixtures are the archive's own censored words and its 35-asterisk
    divider line (spec §5) — not invented prettier ones, because the point
    is that real writing already contains exactly these. Breaks when the
    opener test drops its "not followed by a space or its own delimiter"
    clause, or the closer is allowed to be missing.

    The archive's three fixtures alone measure NEITHER adjacency clause —
    measured by mutation 2026-08-25, delete either one and all three still
    render literally, because each is carried by the other clause or by
    having no partner at all. Each clause has two independent halves, a
    space half and an asterisk half, so there are four routes and one
    fixture apiece: '* a*' and '*a *' for the space halves, '*x **' and
    '**x*' for the asterisk ones. The spec's INV-2 names all four."""
    divider = "*" * 35
    for body in ("b**bs", "f*cking", divider, "*x **", "* a*", "*a *"):
        out = render(body, _no_photos)
        assert body in out, f"expected {body!r} preserved literally, got: {out!r}"
        assert "<strong>" not in out and "<em>" not in out, (
            f"unmatched asterisks in {body!r} were turned into a mark: {out!r}"
        )

    # The opener clause decides WHERE the boundary falls rather than whether a
    # mark forms, so its fixture is not a literal one and cannot join the loop
    # above. '**x*' must open at the second asterisk, leaving the first as
    # text; drop the clause and it opens at the first instead, rendering
    # '<p><em>*x</em></p>' — the same tags around different text, which is
    # exactly why an assertion on the tags alone cannot see it (spec §4.5).
    assert render("**x*", _no_photos) == "<p>*<em>x</em></p>", (
        f"the opener adjacency clause did not hold: an asterisk run must not "
        f"open a mark at its first asterisk, got: {render('**x*', _no_photos)!r}"
    )


# --------------------------------------------------------------- INV-3 ----


def test_no_mark_spans_a_newline():
    """INV-3: no mark spans a newline — no Text inside a Span contains
    '\\n', and a mark's opener and closer come from the same Line.

    Not restated as "a Span never contains a Line": Node excludes Line, so
    that form is unconstructible and would pass on any input (spec §5).
    Breaks when scanning runs over the whole body instead of per line —
    which is how a lone asterisk pairs with one three lines down."""
    # A lone opener on the first line of a paragraph and a lone,
    # unrelated-looking closer two lines further down, with ordinary text
    # between them. Both asterisks sit hard against a word (no surrounding
    # space) so each is individually a valid opener/closer attempt by
    # §4.5's adjacency rule -- the only thing standing between them and a
    # wrongly-formed span is the per-line boundary. Whole-body scanning
    # would pair them into one italic span running through the middle
    # line; per-line scanning must not.
    body = (
        "the first line opens a *mark right here\n"
        "the middle line has no asterisk in it at all\n"
        "and this closing line ends with a stray* of its own"
    )
    doc = parse(body)
    nodes = list(_iter_nodes(doc))
    spans = [n for n in nodes if isinstance(n, Span)]
    assert not spans, (
        f"a lone '*' paired across separate lines into a Span: {spans!r}"
    )

    # Positive control: legitimate same-line marks on different lines of
    # one paragraph must still hold — no Text inside either Span carries a
    # newline, and each span's own text is exactly what it wrapped.
    body_with_marks = "**bold on the first line**\n*italic on the second line*"
    doc_with_marks = parse(body_with_marks)
    marked_nodes = list(_iter_nodes(doc_with_marks))
    marked_spans = [n for n in marked_nodes if isinstance(n, Span)]
    assert marked_spans, f"expected same-line marks to parse as Spans: {doc_with_marks!r}"
    for span in marked_spans:
        for inner in _iter_nodes(span.children):
            if isinstance(inner, Text):
                assert "\n" not in inner.value, (
                    f"Text {inner.value!r} inside Span(mark={span.mark!r}) "
                    f"contains a newline"
                )


# --------------------------------------------------------------- INV-4 ----


def test_escaping_text_and_attributes():
    """INV-4: in text, < and > are always escaped and & is escaped only
    where it does not already begin a character reference; in an
    attribute value, all five of & < > " ' are escaped unconditionally.

    Breaks when one escape helper is used for both contexts (spec §5)."""
    # Text context, first half: < and > are always escaped, even where
    # they came from stray editor markup rather than deliberate HTML.
    stray_tag = render('a stray <span id="selectionBoundary_42"> tag', _no_photos)
    assert "<span" not in stray_tag, f"a literal '<' reached the output unescaped: {stray_tag!r}"
    assert "&lt;span" in stray_tag, f"expected '<' escaped to '&lt;': {stray_tag!r}"
    assert "&gt;" in stray_tag, f"expected '>' escaped to '&gt;': {stray_tag!r}"

    # Text context, second half: & is left alone where it already begins a
    # character reference (the archive's own entities), and escaped where
    # it does not (a bare &).
    for entity in ("&nbsp;", "&apos;", "&amp;"):
        out = render(f"an existing {entity} entity", _no_photos)
        assert entity in out, (
            f"an existing character reference {entity!r} was altered: {out!r}"
        )
        assert f"&amp;{entity[1:]}" not in out, (
            f"an existing character reference {entity!r} was re-escaped: {out!r}"
        )

    bare_amp = render("salt & light", _no_photos)
    assert "salt &amp; light" in bare_amp, (
        f"a bare '&' that does not begin a character reference must be "
        f"escaped to '&amp;': {bare_amp!r}"
    )

    # Attribute-value context: strict, unconditional escaping of & < > " '.
    # Round-tripped through a real HTML parser rather than pinned to one
    # entity spelling, so the check is "cannot break out of the attribute
    # and decodes back to the original value" rather than "produces this
    # exact string".
    malicious = 'x.jpg"><script>alert(1)</script><img src=x'
    photo_html = render("{photo: whatever.jpg}", lambda name: malicious)
    assert "<script>" not in photo_html, (
        f"an unescaped attribute value broke out of its tag: {photo_html!r}"
    )
    parsed = _parsed_attrs(photo_html)
    assert parsed.srcs == [malicious], (
        f"expected the img src to decode back to {malicious!r} once escaped "
        f"and reparsed, got {parsed.srcs!r} from: {photo_html!r}"
    )


# --------------------------------------------------------------- INV-6 ----


def test_every_table_row_parses():
    """INV-6, first half: every row in MARKS parses — its example yields
    a structure whose mark field is that row's name.

    Breaks when a mark is added to the scanner without a row, which is
    exactly what would leave the cheat sheet teaching something that does
    not work (spec §5)."""
    assert MARKS, "MARKS is empty — nothing for this test, or the cheat sheet, to show"
    for row in MARKS:
        doc = parse(row.example)
        found = [
            n for n in _iter_nodes(doc)
            if isinstance(n, (Span, Photo)) and n.mark == row.name
        ]
        assert found, (
            f"row {row.name!r}'s own example {row.example!r} did not parse "
            f"to a node carrying mark={row.name!r}; parsed as: {doc!r}"
        )


def test_no_mark_outside_the_table():
    """INV-6, second half: to_html compares against no mark name at all —
    walking the module's AST, it holds no delimiter literal and no branch
    on a mark name, because it calls row.render.

    This is the falsifiable half: carrying the HTML as a template string
    instead of a callable would force to_html to special-case rows a
    template cannot express, which is the hidden second table this
    design exists to prevent (spec §4.2, §5)."""
    source = inspect.getsource(marks_module)
    tree = ast.parse(source)
    to_html_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "to_html"),
        None,
    )
    assert to_html_node is not None, "marks.py defines no to_html function"

    literals = {
        n.value for n in ast.walk(to_html_node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    mark_names = {row.name for row in MARKS}
    delimiters = {row.opens for row in MARKS} | {row.closes for row in MARKS if row.closes}

    hit_names = literals & mark_names
    assert not hit_names, (
        f"to_html contains the literal mark name(s) {hit_names!r} — it must "
        f"dispatch through row.render rather than branch on a name"
    )
    hit_delims = literals & delimiters
    assert not hit_delims, (
        f"to_html contains the literal delimiter(s) {hit_delims!r} — "
        f"delimiters belong only to MARKS[*].opens / .closes"
    )

    calls_a_render_attr = any(
        isinstance(n, ast.Attribute) and n.attr == "render"
        for n in ast.walk(to_html_node)
    )
    assert calls_a_render_attr, (
        "to_html never references a row's .render — INV-6 requires "
        "dispatch through MARKS, not a hidden second table"
    )


# --------------------------------------------------------------- INV-7 ----


_FORBIDDEN_TOP_LEVEL_IMPORTS = {"os", "io", "socket", "urllib", "requests", "subprocess", "pathlib"}


def test_marks_is_pure():
    """INV-7: marks.py imports nothing that reaches a disk or a network:
    not pathlib, os, io, open, socket, urllib, requests, subprocess, nor
    any other pressless module.

    Walks the module's AST rather than grepping its text (spec §5). Reads
    the module's *source* via inspect.getsource — that read is done here,
    by the test, not by marks.py itself, which is exactly what rule 3
    (docs/design.md § What may depend on what) requires: it takes text and
    returns a structure, and nothing about proving that may itself touch a
    disk from inside marks.py."""
    source = inspect.getsource(marks_module)
    tree = ast.parse(source)

    imported_top_level = set()
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_top_level.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                relative_imports.append(node)
            elif node.module:
                imported_top_level.add(node.module.split(".")[0])

    forbidden = imported_top_level & (_FORBIDDEN_TOP_LEVEL_IMPORTS | {"pressless"})
    assert not forbidden, (
        f"marks.py imports {forbidden!r}, which can reach a disk or a "
        f"network, or is another pressless module — rule 3 forbids both"
    )
    assert not relative_imports, (
        f"marks.py has {len(relative_imports)} relative import(s), which "
        f"can only name a sibling pressless module — rule 3 forbids depending "
        f"on one"
    )

    open_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "open"
    ]
    assert not open_calls, (
        f"marks.py calls the builtin open() {len(open_calls)} time(s) — "
        f"it must never touch a disk"
    )


# --------------------------------------------------------------- INV-8 ----


def test_colour_argument_cannot_carry_css():
    """INV-8: a colour argument reaches the style attribute only after
    matching ^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$ in full; a named colour
    reaches it only as one of the two fixed var(--…) strings.

    The anchors are the invariant: unanchored, the same pattern accepts
    '#c0453a;background:url(…)' and the payload reaches style= — this is
    the refuting case, executed during the spec's own gate (spec §5)."""
    valid3 = _parsed_attrs(render("{#c0a}word{/}", _no_photos))
    assert valid3.styles == ["color:#c0a"], (
        f"a valid 3-digit hex colour did not render as expected: {valid3.styles!r}"
    )

    valid6 = _parsed_attrs(render("{#c0453a}word{/}", _no_photos))
    assert valid6.styles == ["color:#c0453a"], (
        f"a valid 6-digit hex colour did not render as expected: {valid6.styles!r}"
    )

    # The refuting case: a colour-shaped prefix followed by CSS that has no
    # business being there. If the argument match is not anchored in full,
    # this reaches style= carrying the payload.
    payload = "{#c0453a;background:url(javascript:alert(1))}word{/}"
    attacked = _parsed_attrs(render(payload, _no_photos))
    assert not attacked.styles, (
        f"an unanchored colour argument let a CSS payload reach style=: "
        f"{attacked.styles!r} from input {payload!r}"
    )

    accent = _parsed_attrs(render("{accent}word{/}", _no_photos))
    assert accent.styles == ["color:var(--accent)"], (
        f"a named colour must render only as the fixed var(--accent) "
        f"string, got: {accent.styles!r}"
    )

    muted = _parsed_attrs(render("{muted}word{/}", _no_photos))
    assert muted.styles == ["color:var(--muted)"], (
        f"a named colour must render only as the fixed var(--muted) "
        f"string, got: {muted.styles!r}"
    )


# ------------------------------------------------------------ PRESS-0054 ----


def _html(text: str) -> str:
    return marks_module.to_html(parse(text), _no_photos)


def test_an_ordinary_brace_does_not_kill_a_colour_mark():
    """PRESS-0054: depth was counted on the closer's FIRST CHARACTER, which
    is '{'. So any brace in the writer's own words incremented the depth,
    the real {/} was consumed as a decrement, and the whole line fell out as
    literal -- the colour silently gone from the published page.

    §4.5 says a nested {...} OPENER increments the counter, which is what it
    does now.

    Breaks when an implementer counts the character rather than the opener.
    Nothing raises and nothing looks wrong; the writer just loses a colour
    for typing a brace.
    """
    out = _html("{accent}the set {x} of things{/}")

    assert "<span" in out, (
        f"a brace inside the mark killed it and the line came out literal: "
        f"{out!r}"
    )
    assert "{x}" in out, (
        f"the writer's own brace did not survive into the output: {out!r}"
    )
    assert "{accent}" not in out and "{/}" not in out, (
        f"the mark's own delimiters leaked into the output: {out!r}"
    )


def test_brace_marks_still_nest_inside_one_another():
    """PRESS-0054's counter-case. The scanning section names
    '{accent}{muted}x{/}{/}' as nesting it must accept, so the depth counter
    has to fire on EVERY brace mark's opener and not only the row being
    closed.

    Breaks when an implementer narrows the count to this row's own opener:
    the inner mark's {/} is then taken as the outer one's closer, and the
    outer span ends early.
    """
    nested = _html("{accent}{muted}x{/}{/}")
    assert nested.count("<span") == 2, (
        f"two nested colour marks did not both survive: {nested!r}"
    )

    # The same, with the argument-bearing colour row as the inner mark.
    mixed = _html("{accent}a {#ff0000}red{/} b{/}")
    assert mixed.count("<span") == 2 and "#ff0000" in mixed, (
        f"a hex colour nested inside accent did not survive: {mixed!r}"
    )


def test_a_deeply_nested_line_degrades_to_literal_rather_than_raising():
    """PRESS-0054: _scan recursed once per nesting level with no bound, so a
    few kilobytes of openers on one line raised an uncaught RecursionError.

    §6 promises literal text for malformed input and names photo_src as the
    only thing that raises, so a crash breaks the contract twice over. Past
    the bound the rest of the line is literal, which is the degradation the
    module already documents.

    Measured before the fix: 700 levels raised. Breaks when an implementer
    removes the bound, which no ordinary input reaches.
    """
    deep = "{accent}" * 700 + "x" + "{/}" * 700

    out = _html(deep)  # the assertion is that this returns at all

    assert "x" in out, f"the line's own text was lost entirely: {out[:120]!r}"


def test_an_unclosable_line_does_not_take_quadratic_time():
    """PRESS-0054: _closes_at scanned to end of line at every position where
    an opener matched and no closer existed. The asterisk family is
    short-circuited by its adjacency guards; the brace marks had none.

    Measured before the fix: 4000 openers took 8.2s and the cost quadrupled
    each time the input doubled. It is now checked once whether the closer
    occurs at all.

    The bound is deliberately loose -- this ran in well under a tenth of a
    second here, so it catches the defect returning without failing on a
    slow or loaded machine.
    """
    line = "{accent}a" * 4000

    started = time.monotonic()
    _html(line)
    elapsed = time.monotonic() - started

    assert elapsed < 3.0, (
        f"an unclosable line of {len(line)} characters took {elapsed:.1f}s; "
        f"before this fix it was 8.2s and quadratic in the line's length"
    )
