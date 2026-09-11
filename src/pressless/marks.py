"""Marks — one table, one parser, one renderer (PRESS-0004).

The writer's small styling language: text in, structure out, structure to
HTML. Every part that renders reads this module, so the box he types into
and the page his readers see cannot disagree about what a poem looks like
(`docs/design.md` § What may depend on what, rule 2).

It touches no disk and no network (rule 3). A picture's address comes from
the `photo_src` callable the caller supplies.

The contract is `docs/specs/PRESS-0004-marks.md`; the section and INV-N
references below are to it.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby

__all__ = [
    "MARKS",
    "Block",
    "Document",
    "Line",
    "Mark",
    "Node",
    "Paragraph",
    "Photo",
    "PhotoSrc",
    "Quote",
    "Renderer",
    "Span",
    "Text",
    "parse",
    "render",
    "to_html",
]


# ---------------------------------------------------------------- structure --
# §4.3. Line is its own level rather than a <br> in a node list, which is
# what makes INV-1 structural: a document cannot represent a lost line break.


@dataclass(frozen=True)
class Text:
    """Literal writing. Escaped on the way out, never re-parsed."""

    value: str


@dataclass(frozen=True)
class Span:
    """One wrap mark and what it wraps. `arg` is its matched argument."""

    mark: str
    arg: str | None
    children: tuple[Node, ...]


@dataclass(frozen=True)
class Photo:
    """A picture mark. `name` is the file name — Marks never builds a path."""

    mark: str
    name: str
    caption: str | None


@dataclass(frozen=True)
class Line:
    """One typed line."""

    children: tuple[Node, ...]


@dataclass(frozen=True)
class Paragraph:
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class Quote:
    """A quotation. It carries `mark` for the reason Photo does, and holds
    Paragraphs so INV-1 reaches inside it unchanged."""

    mark: str
    paragraphs: tuple[Paragraph, ...]


Node = Text | Span | Photo
Block = Paragraph | Photo | Quote
Document = tuple[Block, ...]

#: Given a picture's file name, the address to put in `src`. The Builder
#: passes its web-copy naming rule; the Face passes a preview address.
PhotoSrc = Callable[[str], str]

#: A mark's own HTML: its node, its already-rendered children, `photo_src`.
#: A Quote's children are its rendered paragraphs, joined by '\n'.
Renderer = Callable[[Span | Photo | Quote, str, PhotoSrc], str]


# ----------------------------------------------------------------- escaping --
# §4.6. Two different rules, and mixing them up is how an injection gets in.

# A character reference WordPress already wrote, or a bare '&'. The trailing
# group is optional so one pass tells the two apart.
_CHAR_REF_OR_AMP = re.compile(
    r"&(?:[A-Za-z][A-Za-z0-9]{0,30};|#[0-9]{1,7};|#[xX][0-9A-Fa-f]{1,6};)?"
)

# One rainbow step: a character reference the text already carries, or any
# single character. Built from the pattern above so §4.6's grammar has one
# copy -- a second would be a second rule.
_RAINBOW_UNIT = re.compile(f"{_CHAR_REF_OR_AMP.pattern}|.", re.DOTALL)


def _escape_text(value: str) -> str:
    """INV-4, text half: '<' and '>' always; '&' only where it does not
    already begin a character reference, so the archive's own entities
    survive untouched."""
    value = _CHAR_REF_OR_AMP.sub(
        lambda found: found.group(0) if len(found.group(0)) > 1 else "&amp;", value
    )
    return value.replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(value: str) -> str:
    """INV-4, attribute half: all five, unconditionally. A caller returning a
    name with a quote in it cannot break out of the tag."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ---------------------------------------------------------------- renderers --
# Each row's HTML is built here and nowhere else (§4.2). `to_html` calls
# `row.render` and compares against no mark name at all — INV-6.


def _wrap_in(tag: str) -> Renderer:
    def render_wrapped(node: Span | Photo | Quote, children: str, photo_src: PhotoSrc) -> str:
        return f"<{tag}>{children}</{tag}>"

    return render_wrapped


def _named_colour(css: str) -> Renderer:
    """§3.2: a named colour renders as the CSS variable, never as a hex
    value, so repainting the site repaints twelve years of entries."""

    def render_named(node: Span | Photo | Quote, children: str, photo_src: PhotoSrc) -> str:
        return f'<span style="color:{_escape_attr(css)}">{children}</span>'

    return render_named


def _picked_colour(node: Span | Photo | Quote, children: str, photo_src: PhotoSrc) -> str:
    # INV-8: this argument reached here only by matching the hex pattern in
    # full. Escaped as well, because the style attribute is a trust boundary.
    return f'<span style="color:{_escape_attr(node.arg or "")}">{children}</span>'


def _rainbow(node: Span | Photo | Quote, children: str, photo_src: PhotoSrc) -> str:
    """One span per unit carrying an index, so the site's stylesheet owns the
    palette and Marks owns no colour decision (§4.2). A unit is a whole
    character reference where the text carries one, and a single character
    otherwise; a unit that is one whitespace character is emitted bare and
    does not advance the count, while a character reference always takes a
    span, `&nbsp;` included.

    The only row that ignores its rendered children and walks its own text
    itself — its `content` is "text", so nothing inside it is a mark.
    """
    out: list[str] = []
    index = 0
    text = "".join(n.value for n in node.children if isinstance(n, Text))
    for found in _RAINBOW_UNIT.finditer(text):
        unit = found.group(0)
        if unit.isspace():
            out.append(_escape_text(unit))
            continue
        out.append(
            f'<span class="mk-rainbow" style="--mk-i:{index}">{_escape_text(unit)}</span>'
        )
        index += 1
    return "".join(out)


def _figure(node: Span | Photo | Quote, children: str, photo_src: PhotoSrc) -> str:
    """The caller owns the file world: if `photo_src` raises, Marks does not
    catch it (§6)."""
    src = _escape_attr(photo_src(node.name))
    # §4.2: the caption is the picture's description. Where none is written
    # alt is empty, which declares the picture decorative. The caption
    # reaches two places under two different rules (§4.6) -- the attribute
    # rule here, the text rule in the figcaption -- so a caption carrying a
    # quote cannot break out of the tag (INV-10).
    alt = _escape_attr(node.caption) if node.caption is not None else ""
    caption = (
        f"<figcaption>{_escape_text(node.caption)}</figcaption>"
        if node.caption is not None
        else ""
    )
    return f'<figure><img src="{src}" alt="{alt}">{caption}</figure>'


def _link(node: Span | Photo | Quote, children: str, photo_src: PhotoSrc) -> str:
    # INV-11: this argument reached here only by matching the address grammar
    # in full, so once the whitespace it allows either side is stripped it is
    # one http or https address. Escaped as well, because href is a trust
    # boundary (§4.6).
    return f'<a href="{_escape_attr((node.arg or "").strip())}">{children}</a>'


# --------------------------------------------------------------- the table --


@dataclass(frozen=True)
class Mark:
    """One mark. MARKS is the only route to any of them (§4.2)."""

    name: str  # Span.mark / Photo.mark / Quote.mark
    kind: str  # "wrap" | "block" | "prefix"
    opens: str  # literal prefix; longest is tried first
    closes: str | None  # None for a block or prefix mark
    arg: str | None  # regex the argument must match IN FULL
    content: str  # "marks" | "text" -- is the body scanned on?
    render: Renderer  # this mark's HTML, built here and nowhere else
    example: str  # what the cheat sheet shows, and a fixture
    explains: str  # one plain-English line


_HEX_COLOUR = r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$"

# The name, and an optional caption after a bar. Named groups because the
# scanner builds a Photo from them.
#
# The name's grammar is this pattern and nothing else (§4.2), so MARKS stays
# the only route: a name breaking it fails the row's own match and the line
# is literal. It refuses both separators, a colon, control characters, and
# `.` / `..` -- everything that could carry the name outside the folder the
# caller meant, on either platform. Marks hands this string to photo_src
# BEFORE any escaping (INV-9), so nothing downstream defends it. At least as
# strict as PRESS-0006's INV-11, which governs where the original is kept.
# The name's first character may not be whitespace: leaving it optional lets
# the leading \s* give a space back on backtracking, and the dot refusal --
# anchored at the name's start -- then never sees the dots at all. Measured
# 2026-09-06: '{photo: ..}' formed a mark whose name was ' ..'.
_PHOTO_ARG = (
    r"^\s*(?P<name>(?!\.{1,2}(?:\s|\||$))"
    r"[^\s|/\\:\x00-\x1f\x7f][^|/\\:\x00-\x1f\x7f]*?)"
    r"\s*(?:\|\s*(?P<caption>.+?)\s*)?$"
)

# One absolute http or https address, whitespace either side (§4.2). After
# the scheme: no whitespace, quote, angle bracket, brace or backslash. That
# refuses javascript: and every other scheme, which is what defends the href
# (INV-11) -- compared with re.fullmatch, like every row's `arg`.
_LINK_ADDRESS = r"^\s*https?://[^\s\"'<>{}\\]+\s*$"


MARKS: tuple[Mark, ...] = (
    Mark(
        name="bold",
        kind="wrap",
        opens="**",
        closes="**",
        arg=None,
        content="marks",
        render=_wrap_in("strong"),
        example="**said out loud**",
        explains="Bold, for a word you want louder.",
    ),
    Mark(
        name="italic",
        kind="wrap",
        opens="*",
        closes="*",
        arg=None,
        content="marks",
        render=_wrap_in("em"),
        example="*whispered*",
        explains="Italic, for a word leaning away from the rest.",
    ),
    Mark(
        name="accent",
        kind="wrap",
        opens="{accent}",
        closes="{/}",
        arg=None,
        content="marks",
        render=_named_colour("var(--accent)"),
        example="{accent}his own name{/}",
        explains="The site's own highlight colour.",
    ),
    Mark(
        name="muted",
        kind="wrap",
        opens="{muted}",
        closes="{/}",
        arg=None,
        content="marks",
        render=_named_colour("var(--muted)"),
        example="{muted}a quieter aside{/}",
        explains="The site's own quieter ink, for a line that sits back.",
    ),
    Mark(
        name="colour",
        kind="wrap",
        opens="{",
        closes="{/}",
        arg=_HEX_COLOUR,
        content="marks",
        render=_picked_colour,
        example="{#c0453a}the red line{/}",
        explains="Any colour you pick, written as a hash and its hex code.",
    ),
    Mark(
        name="rainbow",
        kind="wrap",
        opens="{rainbow}",
        closes="{/}",
        arg=None,
        content="text",
        render=_rainbow,
        example="{rainbow}every colour at once{/}",
        explains="Every letter a different colour. Marks inside it stay as typed.",
    ),
    Mark(
        name="photo",
        kind="block",
        opens="{photo:",
        closes=None,
        arg=_PHOTO_ARG,
        content="marks",
        render=_figure,
        example="{photo: seaside.jpg | Late light}",
        explains="A photograph on a line of its own, with a caption if you want one.",
    ),
    Mark(
        name="link",
        kind="wrap",
        opens="{link:",
        closes="{/}",
        arg=_LINK_ADDRESS,
        content="marks",
        render=_link,
        example="{link: https://example.org}the words{/}",
        explains="A link: the address, then the words a reader clicks.",
    ),
    Mark(
        name="quote",
        kind="prefix",
        opens=">",
        closes=None,
        arg=None,
        content="marks",
        render=_wrap_in("blockquote"),
        example="> a line someone else wrote",
        explains="A quotation: begin each of its lines with >. A blank line ends it.",
    ),
)


_ROW_BY_NAME: dict[str, Mark] = {row.name: row for row in MARKS}

# Longest `opens` first, so '**' is tried before '*' and '{accent}' before '{'.
_WRAP_MARKS: tuple[Mark, ...] = tuple(
    sorted((row for row in MARKS if row.kind == "wrap"),
           key=lambda row: len(row.opens), reverse=True)
)
_BLOCK_MARKS: tuple[Mark, ...] = tuple(
    sorted((row for row in MARKS if row.kind == "block"),
           key=lambda row: len(row.opens), reverse=True)
)
# §4.5: the line scanner never tries a prefix row. §4.4 step 4 matches it at
# the start of a line, before the line is scanned.
_PREFIX_MARKS: tuple[Mark, ...] = tuple(
    sorted((row for row in MARKS if row.kind == "prefix"),
           key=lambda row: len(row.opens), reverse=True)
)


# ----------------------------------------------------------------- scanning --
# §4.5. Left to right, one line at a time. Anything that fails to form a
# complete mark is literal text and scanning resumes one character on.

# §4.5's extra adjacency clause is the asterisk family's alone: those
# delimiters are characters the writing itself is full of, so no mark opens at
# the first asterisk of '***x***' and '*x **' closes nothing. The brace marks
# need no such rule, and giving them one would reject the nesting
# '{accent}{muted}x{/}{/}'.
_RUN_DELIMITER = "*"

# An argument runs from the end of its row's `opens` to the next '}' on the
# line. Every argument-bearing mark is a brace mark, so this is the one
# terminator there is.
_ARG_END = "}"

# §6 promises literal text for malformed input, and names photo_src as the one
# thing that raises. Without a bound, _scan recurses once per nesting level and
# a few kilobytes of openers on one line raised an uncaught RecursionError
# instead (PRESS-0054). Past this depth the rest of the line is literal, which
# is the degradation the module already documents. Far above anything written
# on purpose: nesting is at most a colour inside an emphasis inside a bold.
_MAX_NESTING = 64


def _opens_at(text: str, i: int, closes: str) -> bool:
    """Whether a mark sharing `closes` opens at `i` (§4.5's depth counter).

    Counted on an opener rather than on the closer's first character. That
    character is '{', which the writing itself is full of, so an ordinary
    brace used to increment the depth and swallow the real closer -- and the
    whole line then fell out as literal, losing the mark (PRESS-0054).

    Every brace mark is checked, not just this row: '{accent}{muted}x{/}{/}'
    is nesting the scanning section names as one it must accept.
    """
    for row in _WRAP_MARKS:
        if row.closes != closes:
            continue
        start = _content_starts(row, text, i)
        if start is None:
            continue
        if row.arg is not None:
            if not re.fullmatch(row.arg, text[i + len(row.opens) : start - 1]):
                continue
        return True
    return False


def _content_starts(row: Mark, text: str, i: int) -> int | None:
    """Where this row's opening construct ends, or None if it is not here.

    For a row with an argument the construct runs past the argument to its
    closing brace; for the rest it is `opens` alone.
    """
    if not text.startswith(row.opens, i):
        return None
    after = i + len(row.opens)
    if row.arg is None:
        return after
    end = text.find(_ARG_END, after)
    if end < 0:
        return None
    return end + 1


def _closes_at(row: Mark, text: str, start: int) -> int | None:
    """Index of this row's closer, or None.

    §4.5: on the same line, not immediately preceded by whitespace, and — for
    the asterisk family — not by another asterisk. A mark whose opener and closer
    differ can contain itself, so those count nesting depth, and the counter
    alone decides which closer belongs to which span.
    """
    closes = row.closes
    if closes is None:
        return None
    nests = row.opens != closes
    if text.find(closes, start) < 0:
        # Nothing further on the line can close this, so the walk below can
        # only reach the end. Checked up front because _try_wrap asks at
        # every position, which made an unclosable line quadratic
        # (PRESS-0054).
        return None
    depth = 0
    i = start
    while i < len(text):
        if text.startswith(closes, i):
            if depth:
                depth -= 1
                i += len(closes)
                continue
            before = text[i - 1 : i]
            if before.isspace() or (before == _RUN_DELIMITER and row.opens[0] == _RUN_DELIMITER):
                i += 1
                continue
            return i
        if nests and _opens_at(text, i, closes):
            depth += 1
        i += 1
    return None


def _try_wrap(text: str, i: int, depth: int) -> tuple[Span, int] | None:
    """The first wrap row that forms a complete mark at `i`, with the index
    just past it."""
    for row in _WRAP_MARKS:
        start = _content_starts(row, text, i)
        if start is None:
            continue
        arg = text[i + len(row.opens) : start - 1] if row.arg is not None else None
        if arg is not None and not re.fullmatch(row.arg, arg):
            continue
        after_opener = text[start : start + 1]
        if after_opener.isspace() or (
            after_opener == _RUN_DELIMITER and row.opens[0] == _RUN_DELIMITER
        ):
            continue
        end = _closes_at(row, text, start)
        if end is None:
            continue
        inner = text[start:end]
        children = (_scan(inner, depth + 1) if row.content == "marks"
                    else (Text(inner),))
        return Span(mark=row.name, arg=arg, children=children), end + len(row.closes or "")
    return None


def _scan(text: str, depth: int = 0) -> tuple[Node, ...]:
    """One line's worth of nodes."""
    if depth > _MAX_NESTING:
        return (Text(text),)
    nodes: list[Node] = []
    literal: list[str] = []
    i = 0
    while i < len(text):
        found = _try_wrap(text, i, depth)
        if found is None:
            literal.append(text[i])
            i += 1
            continue
        if literal:
            nodes.append(Text("".join(literal)))
            literal.clear()
        node, i = found
        nodes.append(node)
    if literal:
        nodes.append(Text("".join(literal)))
    return tuple(nodes)


def _as_block(line: str) -> Photo | None:
    """§4.2: a block mark is a mark only when it owns the whole line. With any
    other text beside it, it stays literal."""
    stripped = line.strip()
    for row in _BLOCK_MARKS:
        if row.arg is None:
            continue
        if not stripped.startswith(row.opens) or not stripped.endswith(_ARG_END):
            continue
        arg = stripped[len(row.opens) : -1]
        if _ARG_END in arg:
            continue
        matched = re.fullmatch(row.arg, arg)
        if matched is None:
            continue
        return Photo(mark=row.name, name=matched["name"], caption=matched["caption"])
    return None


# ------------------------------------------------------------------ parsing --

# §4.4 step 3: a run of blank lines ends a paragraph, where blank means empty
# or whitespace-only. The same split today's generator makes.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def _paragraph(lines: list[str]) -> Paragraph | None:
    """§4.4 step 5: strip the paragraph, and drop it if nothing is left."""
    text = "\n".join(lines).strip()
    if not text:
        return None
    return Paragraph(tuple(Line(_scan(line)) for line in text.split("\n")))


def _end_paragraph(pending: list[str], blocks: list[Block]) -> None:
    """What has gathered becomes a paragraph, if anything is left of it, and
    gathering starts again."""
    paragraph = _paragraph(pending)
    pending.clear()
    if paragraph is not None:
        blocks.append(paragraph)


def _prefix_row(line: str) -> Mark | None:
    """§4.2: the prefix row this line begins with, whitespace before it
    aside, or None."""
    stripped = line.lstrip()
    for row in _PREFIX_MARKS:
        if stripped.startswith(row.opens):
            return row
    return None


def _unprefixed(row: Mark, line: str) -> str:
    """§4.4 step 4: the line without the whitespace before the prefix, the
    prefix, and one space after it where there is one."""
    return line.lstrip()[len(row.opens):].removeprefix(" ")


def _quote(row: Mark, lines: list[str]) -> Quote | None:
    """§4.4 step 4: a run of prefixed lines, as one Quote. A line left empty
    separates its paragraphs, and each is split into lines like any other.
    None where no paragraph is left, so a lone '>' renders nothing."""
    paragraphs = tuple(
        paragraph
        for part in _PARAGRAPH_BREAK.split("\n".join(lines))
        if (paragraph := _paragraph(part.split("\n"))) is not None
    )
    return Quote(mark=row.name, paragraphs=paragraphs) if paragraphs else None


def parse(body: str) -> Document:
    """Text in, structure out (§4.4).

    Steps 2, 3 and 5 discard whitespace deliberately, because today's
    generator does — INV-5 fails on the first entry with a leading newline
    otherwise, and looks like a broken test rather than a wrong rule.
    """
    body = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks: list[Block] = []
    for chunk in _PARAGRAPH_BREAK.split(body):
        pending: list[str] = []
        for row, run in groupby(chunk.split("\n"), key=_prefix_row):
            if row is not None:
                # §4.4 step 4: a run of prefixed lines ends the paragraph and
                # follows it as one Quote. Its lines are only ever scanned,
                # so a block mark inside one stays literal (§4.2).
                _end_paragraph(pending, blocks)
                quote = _quote(row, [_unprefixed(row, line) for line in run])
                if quote is not None:
                    blocks.append(quote)
                continue
            for line in run:
                block = _as_block(line)
                if block is None:
                    pending.append(line)
                    continue
                # §4.4 step 4: the block mark ends the paragraph and follows it.
                _end_paragraph(pending, blocks)
                blocks.append(block)
        _end_paragraph(pending, blocks)
    return tuple(blocks)


# ---------------------------------------------------------------- rendering --


def to_html(doc: Document, photo_src: PhotoSrc) -> str:
    """Structure to HTML (§4.4).

    INV-6: this function holds no delimiter literal and branches on no mark
    name. Every mark's HTML comes from its own row's renderer.
    """

    def paragraph_html(paragraph: Paragraph) -> str:
        body = "<br>\n".join(
            "".join(node_html(node) for node in line.children) for line in paragraph.lines
        )
        return f"<p>{body}</p>"

    def node_html(node: Node | Quote) -> str:
        if isinstance(node, Text):
            return _escape_text(node.value)
        row = _ROW_BY_NAME[node.mark]
        if isinstance(node, Span):
            children = "".join(node_html(child) for child in node.children)
        elif isinstance(node, Quote):
            # §4.4: a Quote's paragraphs render as any other, joined by '\n'.
            children = "\n".join(paragraph_html(p) for p in node.paragraphs)
        else:
            children = ""
        return row.render(node, children, photo_src)

    def block_html(block: Block) -> str:
        if isinstance(block, Paragraph):
            return paragraph_html(block)
        return node_html(block)

    return "\n".join(block_html(block) for block in doc)


def render(body: str, photo_src: PhotoSrc) -> str:
    """parse + to_html."""
    return to_html(parse(body), photo_src)
