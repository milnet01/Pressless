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

import functools
import html
import html.parser
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
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
    "Unwritable",
    "Value",
    "from_inline",
    "parse",
    "render",
    "sources",
    "to_html",
    "value_text",
    "write",
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
    """A picture mark. `name` is the file name — Marks never builds a path.
    It carries `mark` because to_html finds the renderer by the row's name."""

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


@dataclass(frozen=True)
class Value:
    """A value mark (PRESS-0123 §4.1): `arg` stripped, `written` exactly as
    typed, which is what shows where the value cannot be worked out."""

    mark: str
    arg: str
    written: str


Node = Text | Span | Photo | Value
Block = Paragraph | Photo | Quote
Document = tuple[Block, ...]

#: Given a picture's file name, the address to put in `src`. The Builder
#: passes its web-copy naming rule; the Face passes a preview address.
PhotoSrc = Callable[[str], str]

#: A mark's own HTML: its node, its already-rendered children, `photo_src`.
#: A Quote's children are its rendered paragraphs, joined by '\n'.
Renderer = Callable[[Span | Photo | Quote | Value, str, PhotoSrc], str]


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
    def render_wrapped(node: Span | Photo | Quote | Value, children: str,
                       photo_src: PhotoSrc) -> str:
        return f"<{tag}>{children}</{tag}>"

    return render_wrapped


def _named_colour(css: str) -> Renderer:
    """§3.2: a named colour renders as the CSS variable, never as a hex
    value, so repainting the site repaints twelve years of entries."""

    def render_named(node: Span | Photo | Quote | Value, children: str, photo_src: PhotoSrc) -> str:
        return f'<span style="color:{_escape_attr(css)}">{children}</span>'

    return render_named


def _picked_colour(node: Span | Photo | Quote | Value, children: str, photo_src: PhotoSrc) -> str:
    # INV-8: this argument reached here only by matching the hex pattern in
    # full. Escaped as well, because the style attribute is a trust boundary.
    return f'<span style="color:{_escape_attr(node.arg or "")}">{children}</span>'


def _rainbow(node: Span | Photo | Quote | Value, children: str, photo_src: PhotoSrc) -> str:
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


def _figure(node: Span | Photo | Quote | Value, children: str, photo_src: PhotoSrc) -> str:
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


def _link(node: Span | Photo | Quote | Value, children: str, photo_src: PhotoSrc) -> str:
    # INV-11: this argument reached here only by matching the address grammar
    # in full, so once the whitespace it allows either side is stripped it is
    # one http or https address. Escaped as well, because href is a trust
    # boundary (§4.6).
    return f'<a href="{_escape_attr((node.arg or "").strip())}">{children}</a>'


def _as_given(node: Span | Photo | Quote | Value, children: str, photo_src: PhotoSrc) -> str:
    """A value row's HTML: `to_html` has already worked the value out and
    escaped it, so the row adds nothing (PRESS-0123 §4.1)."""
    return children


def _years_since(arg: str, today: date) -> str | None:
    """Whole years from the date to `today`, or None where the argument is
    not a calendar date or falls after `today` (PRESS-0123 §4.1)."""
    try:
        since = date.fromisoformat(arg)
    except ValueError:
        return None
    if since > today:
        return None
    before_anniversary = (today.month, today.day) < (since.month, since.day)
    return str(today.year - since.year - before_anniversary)


# --------------------------------------------------------------- the table --


@dataclass(frozen=True)
class Mark:
    """One mark. MARKS is the only route to any of them (§4.2)."""

    name: str  # Span.mark / Photo.mark / Quote.mark / Value.mark
    kind: str  # "wrap" | "block" | "prefix" | "value"
    opens: str  # literal prefix; longest is tried first
    closes: str | None  # None for a block, prefix or value mark
    arg: str | None  # regex the argument must match IN FULL
    content: str  # "marks" | "text" -- is the body scanned on?
    render: Renderer  # this mark's HTML, built here and nowhere else
    example: str  # what the cheat sheet shows, and a fixture
    explains: str  # one plain-English line
    # A value row's sum: the argument and `today` in, the text to show out,
    # or None where it cannot be worked out (PRESS-0123 §4.1).
    value: Callable[[str, date], str | None] | None = None


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
# It also refuses what PRESS-0006 decision 10 refuses so Windows keeps the
# name as written (PRESS-0164): `< > " ? *`, a trailing dot, and a device
# name judged on the part before the first dot, spaces trimmed, case ignored.
_PHOTO_DEVICE = (r"(?i:con|prn|aux|nul|conin\$|conout\$"
                 r"|com[1-9\u00b9\u00b2\u00b3]|lpt[1-9\u00b9\u00b2\u00b3])")
_PHOTO_ARG = (
    r"^\s*(?P<name>(?!\.{1,2}(?:\s|\||$))"
    rf"(?!{_PHOTO_DEVICE} *(?:\.|\s*(?:\||$)))"
    r'[^\s|/\\:<>"?*\x00-\x1f\x7f][^|/\\:<>"?*\x00-\x1f\x7f]*?(?<!\.))'
    r"\s*(?:\|\s*(?P<caption>.+?)\s*)?$"
)

# One absolute http or https address, whitespace either side (§4.2). After
# the scheme: no whitespace, quote, angle bracket, brace or backslash. That
# refuses javascript: and every other scheme, which is what defends the href
# (INV-11) -- compared with re.fullmatch, like every row's `arg`.
_LINK_ADDRESS = r"^\s*https?://[^\s\"'<>{}\\]+\s*$"

# PRESS-0123 §4.1: a date as ASCII digits, whitespace either side. [0-9],
# never \d, which also takes another script's digits.
_DATE_ARG = r"^\s*[0-9]{4}-[0-9]{2}-[0-9]{2}\s*$"


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
    Mark(
        name="years_since",
        kind="value",
        opens="{years_since:",
        closes=None,
        arg=_DATE_ARG,
        content="text",
        render=_as_given,
        example="{years_since: 2010-01-01}",
        explains="How many whole years since a date, worked out each time you publish.",
        value=_years_since,
    ),
)


_ROW_BY_NAME: dict[str, Mark] = {row.name: row for row in MARKS}

# Longest `opens` first, so '**' is tried before '*' and '{accent}' before '{'.
_WRAP_MARKS: tuple[Mark, ...] = tuple(
    sorted((row for row in MARKS if row.kind == "wrap"),
           key=lambda row: len(row.opens), reverse=True)
)
# Every block row needs an `arg` with `name` and `caption` groups: _as_block
# builds a Photo from them, since photo is the one block mark so far. A second
# block mark changes _as_block too.
_BLOCK_MARKS: tuple[Mark, ...] = tuple(
    sorted((row for row in MARKS if row.kind == "block"),
           key=lambda row: len(row.opens), reverse=True)
)
# PRESS-0123 §4.1: value rows are tried with the wrap rows, longest first.
_INLINE_MARKS: tuple[Mark, ...] = tuple(
    sorted((row for row in MARKS if row.kind in ("wrap", "value")),
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
    if text.find(closes, start) < 0:
        # Nothing further on the line can close this. Checked up front
        # because _try_inline asks at every position (PRESS-0054).
        return None
    return _closer_table(row.opens, closes, text)[start]


# The cache is what makes the table pay: _closes_at asks for one start at a
# time, at every position on the line, and each uncached call would build the
# whole table again -- the slowdown PRESS-0162 removed, back.
@functools.lru_cache(maxsize=32)
def _closer_table(opens: str, closes: str, text: str) -> tuple[int | None, ...]:
    """_closes_at's answer for every start on the line, in one right-to-left
    pass. The walk it replaces ran from each opener to the line's end, so a
    long line of unclosed openers was quadratic -- 18 KB took ten seconds
    (PRESS-0162). The rules are the walk's, unchanged:

    - at depth 0 a closer returns where it stands, unless whitespace (or,
      for the asterisk family, another asterisk) precedes it -- then the
      walk steps one character on;
    - at depth above 0 any closer, preceded by anything, drops the depth
      and the walk resumes just past it;
    - where the mark nests, an opener sharing this closer raises the depth,
      and the walk steps one character on.

    `inner[s]` is where a walk at depth 1 starting at `s` returns to depth
    0 (just past that closer); `found[s]` is the walk at depth 0.
    """
    n = len(text)
    nests = opens != closes
    width = len(closes)
    inner: list[int | None] = [None] * (n + 2)
    found: list[int | None] = [None] * (n + 2)
    for s in range(n - 1, -1, -1):
        closer = text.startswith(closes, s)
        opener = nests and not closer and _opens_at(text, s, closes)
        if closer:
            inner[s] = s + width
            before = text[s - 1 : s]
            skipped = before.isspace() or (before == _RUN_DELIMITER
                                           and opens[0] == _RUN_DELIMITER)
            found[s] = found[s + 1] if skipped else s
        elif opener:
            back = inner[s + 1]
            inner[s] = inner[back] if back is not None and back <= n else None
            found[s] = found[back] if back is not None and back <= n else None
        else:
            inner[s] = inner[s + 1]
            found[s] = found[s + 1]
    return tuple(found[: n + 1])


def _try_inline(text: str, i: int, depth: int) -> tuple[Span | Value, int] | None:
    """The first wrap or value row that forms a complete mark at `i`, with
    the index just past it."""
    for row in _INLINE_MARKS:
        start = _content_starts(row, text, i)
        if start is None:
            continue
        arg = text[i + len(row.opens) : start - 1] if row.arg is not None else None
        if arg is not None and not re.fullmatch(row.arg, arg):
            continue
        if row.kind == "value":
            # PRESS-0123 §4.1: no closer and no adjacency clause.
            return Value(mark=row.name, arg=(arg or "").strip(), written=text[i:start]), start
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
        found = _try_inline(text, i, depth)
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


def value_text(node: Value, today: date | None) -> str:
    """A value mark's text, unescaped: its row's sum against `today`, or the
    mark as written where that cannot be worked out (PRESS-0123 §4.1)."""
    row = _ROW_BY_NAME[node.mark]
    worked_out = row.value(node.arg, today) if row.value and today is not None else None
    return node.written if worked_out is None else worked_out


def to_html(doc: Document, photo_src: PhotoSrc, today: date | None = None) -> str:
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
        elif isinstance(node, Value):
            children = _escape_text(value_text(node, today))
        else:
            children = ""
        return row.render(node, children, photo_src)

    def block_html(block: Block) -> str:
        if isinstance(block, Paragraph):
            return paragraph_html(block)
        return node_html(block)

    return "\n".join(block_html(block) for block in doc)


def render(body: str, photo_src: PhotoSrc, today: date | None = None) -> str:
    """parse + to_html."""
    return to_html(parse(body), photo_src, today)


# ------------------------------------------------------------ writing back --
# PRESS-0346 § 4.5: the way back from the entry editor's visual view to
# marks. `sources` keeps what the writer did not touch byte for byte;
# `from_inline` reads the words typed on the page; `write` spells a block
# so that it reads back as itself.


class Unwritable(ValueError):
    """A block marks cannot spell so that `parse` reads it back as itself."""


# A word joiner shows as nothing. Between two marks' asterisks it stops them
# reading as one run, which is how Bold around Italic is spelled (§ 4.5).
_JOINER = "&#8288;"
_JOINER_CHARACTER = "⁠"
# What `write` puts in place of a character that would otherwise begin a
# mark, where the words are to stay words.
_ESCAPES = {_RUN_DELIMITER: "&#42;", "{": "&#123;"}
_PREFIX_ESCAPES = {">": "&gt;"}
_LINE_END = re.compile(r"\r\n|\r|\n")


def sources(body: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Each block's text as written, and the text around them (§ 4.5).

    Returns `(gaps, texts)`, one more gap than texts, where
    `gaps[0] + texts[0] + gaps[1] + ... + texts[-1] + gaps[-1] == body` and
    `parse(texts[i])` is `(parse(body)[i],)`. A gap holds the blank lines
    between blocks, and anything `parse` drops, such as a lone `>`.

    It walks the body as §4.4 does, a line at a time: a blank line, empty
    or whitespace-only, ends a chunk, as a run of blank lines does there.
    """
    lines = []  # (start, end) of each line, its line ending excluded
    start = 0
    for found in _LINE_END.finditer(body):
        lines.append((start, found.start()))
        start = found.end()
    lines.append((start, len(body)))

    spans: list[tuple[int, int]] = []

    def take(group: list[tuple[int, int]]) -> None:
        first, last = body[slice(*group[0])], body[slice(*group[-1])]
        spans.append((group[0][0] + len(first) - len(first.lstrip()),
                      group[-1][1] - (len(last) - len(last.rstrip()))))

    chunks: list[list[tuple[int, int]]] = [[]]
    for line in lines:
        if body[slice(*line)].strip():
            chunks[-1].append(line)
        elif chunks[-1]:
            chunks.append([])
    for chunk in chunks:
        pending: list[tuple[int, int]] = []
        for row, run in groupby(chunk, key=lambda line: _prefix_row(body[slice(*line)])):
            run = list(run)
            if row is not None:
                if pending:
                    take(pending)
                    pending = []
                if _quote(row, [_unprefixed(row, body[slice(*line)]) for line in run]):
                    take(run)
                continue
            for line in run:
                if _as_block(body[slice(*line)]) is None:
                    pending.append(line)
                    continue
                if pending:
                    take(pending)
                    pending = []
                take([line])
        if pending:
            take(pending)

    gaps, texts, at = [], [], 0
    for begin, end in spans:
        gaps.append(body[at:begin])
        texts.append(body[begin:end])
        at = end
    gaps.append(body[at:])
    return tuple(gaps), tuple(texts)


def _read_references(value: str) -> str:
    """A Text's words as a reader sees them: each character reference read
    as its character, and word joiners gone."""
    return _CHAR_REF_OR_AMP.sub(
        lambda found: html.unescape(found.group(0)) if len(found.group(0)) > 1 else "&",
        value).replace(_JOINER_CHARACTER, "")


def _normal_nodes(nodes: tuple[Node, ...]) -> tuple[Node, ...]:
    out: list[Node] = []
    for node in nodes:
        if isinstance(node, Text):
            words = _read_references(node.value)
            if out and isinstance(out[-1], Text):
                out[-1] = Text(out[-1].value + words)
            elif words:
                out.append(Text(words))
        elif isinstance(node, Span):
            out.append(Span(node.mark, None if node.arg is None else node.arg.strip(),
                            _normal_nodes(node.children)))
        else:
            out.append(node)
    return tuple(node for node in out if not (isinstance(node, Text) and not node.value))


def _normal_paragraph(paragraph: Paragraph) -> Paragraph:
    return Paragraph(tuple(Line(_normal_nodes(line.children)) for line in paragraph.lines))


def normal(block: Block) -> Block:
    """§ 4.5's normal form: two blocks a reader cannot tell apart are equal
    in it. Character references are read, word joiners removed, neighbouring
    Texts joined and empty ones dropped, and a mark's argument stripped."""
    if isinstance(block, Paragraph):
        return _normal_paragraph(block)
    if isinstance(block, Quote):
        return Quote(block.mark, tuple(_normal_paragraph(p) for p in block.paragraphs))
    caption = None if block.caption is None else _read_references(block.caption)
    return Photo(block.mark, block.name, caption)


def _write_text(value: str, escape: bool) -> str:
    if not escape:
        return value
    return "".join(_ESCAPES.get(character, character) for character in value)


def _write_arg(row: Mark, arg: str | None) -> str:
    # An argument after a colon takes one space, as the cheat sheet writes it.
    arg = (arg or "").strip()
    return (" " + arg if row.opens.endswith(":") else arg) + _ARG_END


def _joined(pieces: list[str]) -> str:
    out = ""
    for piece in pieces:
        if out.endswith(_RUN_DELIMITER) and piece.startswith(_RUN_DELIMITER):
            out += _JOINER
        out += piece
    return out


def _write_node(node: Node, escape: bool) -> str:
    if isinstance(node, Text):
        return _write_text(node.value, escape)
    if isinstance(node, Value):
        return node.written
    if isinstance(node, Photo):
        raise Unwritable("a photograph is a block of its own")
    row = _ROW_BY_NAME[node.mark]
    opening = row.opens + (_write_arg(row, node.arg) if row.arg is not None else "")
    if row.content == "marks":
        inner = _write_nodes(node.children, escape)
    else:
        inner = "".join(child.value for child in node.children if isinstance(child, Text))
    closes = row.closes or ""
    return _joined([opening, inner, closes]) if inner else ""


def _write_nodes(nodes: tuple[Node, ...], escape: bool) -> str:
    return _joined([_write_node(node, escape) for node in nodes])


def _write_line(line: Line, *, in_quote: bool) -> str:
    """A line as marks: as it stands where it reads back so, else with the
    characters that would begin a mark written as references."""
    wanted = _normal_nodes(line.children)
    for escape in (False, True):
        written = _write_nodes(line.children, escape)
        if escape and not in_quote:
            stripped = written.lstrip()
            lead = written[: len(written) - len(stripped)]
            if stripped[:1] in _PREFIX_ESCAPES:
                written = lead + _PREFIX_ESCAPES[stripped[0]] + stripped[1:]
        if not in_quote and (_prefix_row(written) is not None
                             or _as_block(written) is not None):
            continue
        if _normal_nodes(_scan(written)) == wanted:
            return written
    raise Unwritable(f"marks cannot spell the line {written!r} so it reads back")


def _write_paragraph(paragraph: Paragraph, *, in_quote: bool) -> str:
    return "\n".join(_write_line(line, in_quote=in_quote) for line in paragraph.lines)


def write(block: Block) -> str:
    """The block as marks, reading back as itself in normal form (§ 4.5).
    Raises Unwritable where no spelling does."""
    if isinstance(block, Paragraph):
        text = _write_paragraph(block, in_quote=False)
    elif isinstance(block, Quote):
        row = _ROW_BY_NAME[block.mark]
        paragraphs = ["\n".join(f"{row.opens} {line}" for line in
                                _write_paragraph(p, in_quote=True).split("\n"))
                      for p in block.paragraphs]
        text = f"\n{row.opens}\n".join(paragraphs)
    else:
        row = _ROW_BY_NAME[block.mark]
        caption = "" if block.caption is None else " | " + block.caption
        text = row.opens + _write_arg(row, block.name + caption)
    if tuple(normal(read) for read in parse(text)) != (normal(block),):
        raise Unwritable(f"marks cannot spell {text[:60]!r} so it reads back")
    return text


# ---------------------------------------------------------- reading the page --


def _opening(row: Mark) -> re.Pattern[str]:
    """The start tag a wrap row's renderer writes, as a pattern capturing its
    argument. Taken from the renderer itself, so MARKS stays the only route
    to a mark (INV-6)."""
    held, inside = "\x00", "\x01"
    probe = row.render(Span(row.name, held if row.arg is not None else None, ()),
                       inside, lambda name: name)
    return re.compile(re.escape(probe.split(inside)[0]).replace(held, "(.*?)"))


# No-argument rows first, so the site's accent is never taken for a picked
# colour; a row whose content is text alone (rainbow) is never typed.
_TYPED_MARKS: tuple[tuple[Mark, re.Pattern[str]], ...] = tuple(
    (row, _opening(row)) for row in sorted(
        (row for row in MARKS if row.kind == "wrap" and row.content == "marks"),
        key=lambda row: row.arg is not None))
_BREAK = object()


class _Inline(html.parser.HTMLParser):
    """PRESS-0260 § 4.4's `<inline>`, plus the colour spans, as a tree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: list = []
        self.stack: list[tuple[Mark | None, str | None, list]] = [(None, None, self.root)]
        self.refused = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "br":
            self.stack[-1][2].append(_BREAK)
            return
        written = self.get_starttag_text() or ""
        for row, pattern in _TYPED_MARKS:
            found = pattern.fullmatch(written)
            if found is None:
                continue
            arg = html.unescape(found.group(1)) if row.arg is not None else None
            if arg is not None and not re.fullmatch(row.arg, arg):
                continue
            children: list = []
            self.stack[-1][2].append((row, arg, children))
            self.stack.append((row, arg, children))
            return
        self.refused = True
        self.stack.append((None, None, []))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag == "br":
            self.stack[-1][2].append(_BREAK)
        else:
            self.refused = True

    def handle_endtag(self, tag: str) -> None:
        if len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.stack[-1][2].append(data)


def _as_source(words: str) -> str:
    """Words as a Text holds them: an '&' that would begin a character
    reference is written as one, so it stays an '&'."""
    return _CHAR_REF_OR_AMP.sub(
        lambda found: "&amp;" + found.group(0)[1:] if len(found.group(0)) > 1 else "&", words)


def _lines_of(items: list, inside: frozenset[str]) -> list[list[Node]]:
    """The tree split into lines at each break. A mark crossing a break is
    closed before it and opened again after, since no mark spans a line
    (PRESS-0004 INV-3); a mark inside the same mark is dropped."""
    lines: list[list[Node]] = [[]]
    for item in items:
        if item is _BREAK:
            lines.append([])
        elif isinstance(item, str):
            lines[-1].append(Text(re.sub(r"\s+", " ", item.replace("\xa0", " "))))
        else:
            row, arg, children = item
            parts = _lines_of(children, inside | {row.name})
            for at, part in enumerate(parts):
                if at:
                    lines.append([])
                if row.name in inside:
                    lines[-1].extend(part)
                else:
                    lines[-1].append(Span(row.name, arg, tuple(part)))
    return lines


def _tidy(nodes: list[Node] | tuple[Node, ...]) -> list[Node]:
    """Whitespace at a mark's edges moved outside it, empty marks dropped,
    neighbouring Texts joined and their space runs made one."""
    out: list[Node] = []

    def text(words: str) -> None:
        if out and isinstance(out[-1], Text):
            out[-1] = Text(re.sub(" +", " ", out[-1].value + words))
        elif words:
            out.append(Text(words))

    for node in nodes:
        if isinstance(node, Text):
            text(node.value)
            continue
        children = _tidy(node.children)
        lead = trail = ""
        if children and isinstance(children[0], Text):
            stripped = children[0].value.lstrip()
            lead = children[0].value[: len(children[0].value) - len(stripped)]
            children[0] = Text(stripped)
        if children and isinstance(children[-1], Text):
            stripped = children[-1].value.rstrip()
            trail = children[-1].value[len(stripped):]
            children[-1] = Text(stripped)
        children = [child for child in children
                    if not (isinstance(child, Text) and not child.value)]
        text(lead)
        if children:
            out.append(Span(node.mark, node.arg, tuple(children)))
        text(trail)
    return out


def from_inline(inline: str) -> Paragraph | None:
    """The words typed on the page as a paragraph of marks nodes, or None
    where they hold an element, link or colour no mark can hold (§ 4.5).
    Empty lines are dropped, so an empty paragraph has no lines."""
    reader = _Inline()
    reader.feed(inline)
    reader.close()
    if reader.refused:
        return None
    lines = []
    for nodes in _lines_of(reader.root, frozenset()):
        tidy = _tidy(nodes)
        if tidy and isinstance(tidy[0], Text):
            tidy[0] = Text(tidy[0].value.lstrip())
        if tidy and isinstance(tidy[-1], Text):
            tidy[-1] = Text(tidy[-1].value.rstrip())
        tidy = [node for node in tidy if not (isinstance(node, Text) and not node.value)]
        if tidy:
            lines.append(Line(tuple(_source(node) for node in tidy)))
    return Paragraph(tuple(lines))


def _source(node: Node) -> Node:
    if isinstance(node, Text):
        return Text(_as_source(node.value))
    if isinstance(node, Span):
        return Span(node.mark, node.arg, tuple(_source(child) for child in node.children))
    return node
