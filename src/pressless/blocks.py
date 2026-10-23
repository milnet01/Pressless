"""Blocks — a fixed page held as ready-made sections (PRESS-0215).

A page's sections sit inside one area of its `main`, each between two HTML
comments naming its kind. Every value a section holds is read from its HTML,
and a section is its kind only where its bytes are exactly what this module
writes for it; anything else is kept as code, byte for byte, so the visual
editor and the code view never fight over a page (`docs/design.md` § What may
depend on what, the round-trip rule).

Pure calculation: no disk, no network, and the standard library alone, since
the Builder imports this module (§4.1).

The contract is `docs/specs/PRESS-0215-blocks.md`; the section and INV-N
references below are to it. The ready-made pieces and the script section are
`docs/specs/PRESS-0217-interactive-pieces.md`'s.
"""
from __future__ import annotations

import html as _html
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from types import MappingProxyType

__all__ = [
    "BUTTON", "CODE", "COLUMNS", "COUNTDOWN", "DOWNLOAD", "ENLARGE", "HEADING", "HOLDERS",
    "KINDS",
    "MUSIC", "PICTURE", "PICTURES", "PIECES", "PIECES_SCRIPT", "QUESTIONS", "SCRIPT",
    "SLIDESHOW", "STYLE", "TEXT", "TOP", "VIDEO",
    "Page", "Section", "SectionRefused",
    "adopt", "inline", "read", "section_html", "unmarked", "write",
]

TEXT, HEADING, PICTURE, PICTURES, BUTTON = "text", "heading", "picture", "pictures", "button"
VIDEO, MUSIC, DOWNLOAD, COLUMNS = "video", "music", "download", "columns"
# PRESS-0217 § 4.1: the ready-made pieces, which pieces.js enhances on the
# published site, and a place for the writer's own script, which it does not.
SLIDESHOW, QUESTIONS, ENLARGE, TOP, COUNTDOWN = (
    "slideshow", "questions", "enlarge", "top", "countdown")
SCRIPT = "script"
# PRESS-0273: the writer's own CSS, for the whole page it sits on.
STYLE = "style"
PIECES = (SLIDESHOW, QUESTIONS, ENLARGE, TOP, COUNTDOWN)
KINDS = (TEXT, HEADING, PICTURE, PICTURES, BUTTON, VIDEO, MUSIC, DOWNLOAD, COLUMNS,
         *PIECES, SCRIPT, STYLE)
CODE = "code"

_PAGE, _COLUMN = "page", "column"
_WHITESPACE = " \t\n\r\f"
_MARK = re.compile(r"<!-- (/?)pressless:([a-z]+) -->")
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
# A countdown's end: a date and a time, then optionally seconds and an offset.
_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?")
# What would end a script element early or change how a browser reads where
# it ends; HTML's rule, not a reading of the script.
_SCRIPT_END = re.compile(r"</script|<!--", re.IGNORECASE)
_STYLE_END = re.compile(r"</style", re.IGNORECASE)
_VOID = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                   "meta", "source", "track", "wbr"))


class SectionRefused(ValueError):
    """`section_html` was handed a section it cannot write (§4.4)."""


@dataclass(frozen=True)
class Section:
    kind: str                                         # one of KINDS, or CODE
    fields: Mapping[str, str] = field(default_factory=dict)   # §4.4, per kind
    parts: tuple[tuple[Section, ...], ...] = ()       # PICTURES: one; COLUMNS: one per column
    source: str = ""     # the bytes it was read from, marks included, for CODE and an
                         # earlier form (§4.5); else empty

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True)
class Page:
    before: str                  # the file up to and including the area's opening mark
    sections: tuple[Section, ...]
    gaps: tuple[str, ...]        # whitespace before each section, then before the closing mark
    after: str                   # the closing mark and the rest of the file


# ------------------------------------------------------------- scanning ----


@dataclass(frozen=True)
class _Event:
    kind: str                    # start, startend, end, data, comment or other
    start: int
    end: int
    tag: str = ""
    attrs: tuple[tuple[str, str | None], ...] = ()
    text: str = ""               # data, decoded


@dataclass(frozen=True)
class _Mark:
    start: int
    end: int
    closing: bool
    name: str


class _Scanner(HTMLParser):
    """What HTMLParser reports, each with its offsets. Every handler records
    where its construct starts; each ends where the next one starts."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self._lines = [0] + [found.end() for found in re.finditer("\n", text)]
        self._found: list[tuple[str, int, str, tuple, str]] = []
        self.feed(text)
        self.close()
        starts = [at for _kind, at, *_rest in self._found] + [len(text)]
        self.events = tuple(_Event(kind, at, starts[number + 1], tag, attrs, data)
                            for number, (kind, at, tag, attrs, data) in enumerate(self._found))

    def _note(self, kind: str, tag: str = "", attrs=(), data: str = "") -> None:
        line, column = self.getpos()
        self._found.append((kind, self._lines[line - 1] + column, tag, tuple(attrs), data))

    def handle_starttag(self, tag, attrs):
        self._note("start", tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._note("startend", tag, attrs)

    def handle_endtag(self, tag):
        self._note("end", tag)

    def handle_data(self, data):
        self._note("data", data=data)

    def handle_comment(self, data):
        self._note("comment")

    def handle_decl(self, decl):
        self._note("other")

    def handle_pi(self, data):
        self._note("other")

    def unknown_decl(self, data):
        self._note("other")


def _scan(text: str) -> tuple[_Event, ...]:
    return _Scanner(text).events


def _marks(text: str, events: tuple[_Event, ...]) -> list[_Mark]:
    """§4.2: a mark counts only where HTMLParser reports it as a comment."""
    marks = []
    for event in events:
        if event.kind == "comment" and (found := _MARK.fullmatch(text, event.start, event.end)):
            marks.append(_Mark(event.start, event.end, found.group(1) == "/", found.group(2)))
    return marks


def _wrap(name: str, inner: str) -> str:
    return f"<!-- pressless:{name} -->{inner}<!-- /pressless:{name} -->"


# ------------------------------------------------------------- checking ----


def address_allowed(value: str, *, mailto: bool) -> bool:
    """§4.4: a relative path, or http:, https: or (for an href) mailto:. The
    scheme is read as a browser reads it: outer spaces and controls stripped,
    tabs and line breaks removed, case folded."""
    folded = re.sub(r"[\t\n\r]", "", value.strip("".join(map(chr, range(0x21)))))
    scheme = _SCHEME.match(folded)
    if scheme is None:
        return True
    return scheme.group(1).lower() in (("http", "https", "mailto") if mailto
                                       else ("http", "https"))


def _inline_from(events) -> str | None:
    """`events` written as <inline> (§4.4), or None where they hold anything
    else. `<br/>` is accepted and written `<br>`."""
    out, open_tags = [], []
    for event in events:
        if event.kind == "data":
            out.append(_html.escape(event.text, quote=False))
        elif event.kind in ("start", "startend") and event.tag == "br" and not event.attrs:
            out.append("<br>")
        elif event.kind != "start":
            if event.kind != "end" or not open_tags or open_tags[-1] != event.tag:
                return None
            out.append(f"</{open_tags.pop()}>")
        elif event.tag in ("strong", "em") and not event.attrs:
            open_tags.append(event.tag)
            out.append(f"<{event.tag}>")
        elif (event.tag == "a" and "a" not in open_tags and len(event.attrs) == 1
              and event.attrs[0][0] == "href" and event.attrs[0][1] is not None
              and address_allowed(event.attrs[0][1], mailto=True)):
            open_tags.append("a")
            out.append(f'<a href="{_html.escape(event.attrs[0][1], quote=True)}">')
        else:
            return None
    return None if open_tags else "".join(out)


def _is_inline(markup: str) -> bool:
    return inline(markup) == markup


def inline(markup: str) -> str | None:
    """`markup` as `section_html` writes <inline> (§4.4), or None where it holds
    anything else. The visual editor's typed words pass through it (PRESS-0260
    § 4.5)."""
    return _inline_from(_scan(markup))


_FIELDS = {
    TEXT: ({"html"}, set()),
    HEADING: ({"level", "html"}, set()),
    PICTURE: ({"src", "alt"}, {"width", "height", "caption"}),
    PICTURES: (set(), set()),
    BUTTON: ({"href", "label"}, set()),
    MUSIC: ({"src"}, set()),
    DOWNLOAD: ({"href", "label"}, set()),
    COLUMNS: (set(), set()),
    _COLUMN: (set(), set()),
    SLIDESHOW: (set(), set()),
    QUESTIONS: (set(), set()),
    ENLARGE: ({"src", "alt"}, {"width", "height", "caption"}),
    TOP: ({"label"}, set()),
    COUNTDOWN: ({"to", "label"}, set()),
    SCRIPT: ({"code"}, set()),
    STYLE: ({"code"}, set()),
}

# The kinds that hold other sections, which no column or answer holds.
_HOLDERS = frozenset((COLUMNS, PICTURES, SLIDESHOW, QUESTIONS, _COLUMN))
# Those of them a page can be given, for the visual view's rules.
HOLDERS = tuple(kind for kind in KINDS if kind in _HOLDERS)


def _check(section: Section) -> None:
    """Raise SectionRefused for anything §4.4 says `section_html` refuses."""
    kind, fields = section.kind, section.fields
    if kind == VIDEO:
        wanted, optional = ({"youtube"} if "youtube" in fields else {"src"}), set()
    elif kind in _FIELDS:
        wanted, optional = _FIELDS[kind]
    else:
        raise SectionRefused(f"there is no kind of section called {kind!r}")
    if not wanted <= set(fields) or not set(fields) <= wanted | optional:
        raise SectionRefused(f"a {kind} section holds {sorted(fields)}, not {sorted(wanted)}")
    if not all(isinstance(value, str) for value in fields.values()):
        raise SectionRefused(f"a {kind} section holds a value that is not text")
    for name in ("html", "caption"):
        if name in fields and not _is_inline(fields[name]):
            raise SectionRefused(f"a {kind} section's {name} is not plain words and links")
    if kind == HEADING and fields["level"] not in ("1", "2", "3", "4", "5", "6"):
        raise SectionRefused(f"a heading's level is {fields['level']!r}")
    if kind == VIDEO and "youtube" in fields and not _YOUTUBE_ID.fullmatch(fields["youtube"]):
        raise SectionRefused(f"{fields['youtube']!r} is not a YouTube video's id")
    for name, mailto in (("src", False), ("href", True)):
        if name in fields and not address_allowed(fields[name], mailto=mailto):
            raise SectionRefused(f"a {kind} section may not link to {fields[name]!r}")
    if kind == COUNTDOWN and not _is_when(fields["to"]):
        raise SectionRefused(f"a countdown's end, {fields['to']!r}, is not a date and a time")
    if kind == SCRIPT and _SCRIPT_END.search(fields["code"]):
        raise SectionRefused("a script section cannot hold </script or <!--")
    if kind == STYLE and _STYLE_END.search(fields["code"]):
        raise SectionRefused("a style section cannot hold </style")
    _check_parts(section)


def _is_when(value: str) -> bool:
    if not _WHEN.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _check_parts(section: Section) -> None:
    kind, parts = section.kind, section.parts
    if kind in (PICTURES, SLIDESHOW):
        if len(parts) != 1 or not parts[0] or any(part.kind != PICTURE for part in parts[0]):
            raise SectionRefused(f"a {kind} section holds pictures, and nothing else")
    elif kind == COLUMNS:
        if not 2 <= len(parts) <= 4:
            raise SectionRefused(f"columns come two to four at a time, not {len(parts)}")
        if any(part.kind in _HOLDERS for column in parts for part in column):
            raise SectionRefused("a column holds no section that holds others")
    elif kind == QUESTIONS:
        # PRESS-0217 § 4.1: each part is a question, its words then its answer.
        if not parts or any(len(asked) < 2 or asked[0].kind != TEXT for asked in parts):
            raise SectionRefused("each question is a paragraph, then its answer")
        if any(part.kind in _HOLDERS for asked in parts for part in asked):
            raise SectionRefused("an answer holds no section that holds others")
    elif kind == _COLUMN:
        if len(parts) != 1:
            raise SectionRefused("a column is one list of sections")
    elif parts:
        raise SectionRefused(f"a {kind} section holds no other sections")
    for column in parts:
        for part in column:
            if part.kind != CODE and not part.source:
                _check(part)


# -------------------------------------------------------------- writing ----


def _bytes(section: Section) -> str:
    return section.source or section_html(section)


def _attr(value: str) -> str:
    return _html.escape(value, quote=True)


def _text(value: str) -> str:
    return _html.escape(value, quote=False)


def _img(fields) -> str:
    img = f'<img src="{_attr(fields["src"])}" alt="{_attr(fields["alt"])}"'
    for name in ("width", "height"):
        if name in fields:
            img += f' {name}="{_attr(fields[name])}"'
    return img + ">"


def _caption(fields) -> str:
    return f"<figcaption>{fields['caption']}</figcaption>" if "caption" in fields else ""


def _write_picture(fields) -> str:
    if "caption" in fields:
        return f"<figure>{_img(fields)}{_caption(fields)}</figure>"
    return _img(fields)


def _write_questions(section: Section) -> str:
    return '<dl class="pressless-questions">' + "".join(
        f"<dt>{_bytes(asked[0])}</dt><dd>" + "".join(_bytes(part) for part in asked[1:])
        + "</dd>" for asked in section.parts) + "</dl>"


def _write_video(fields) -> str:
    if "youtube" in fields:
        return (f'<iframe src="https://www.youtube-nocookie.com/embed/{fields["youtube"]}"'
                ' title="YouTube video" allowfullscreen loading="lazy"></iframe>')
    return f'<video controls preload="metadata" src="{_attr(fields["src"])}"></video>'


def _write_parts(css: str, parts) -> str:
    return f'<div class="{css}">' + "".join(_bytes(part) for part in parts) + "</div>"


# Each kind's HTML between its marks, as this Pressless writes it.
_WRITERS: dict[str, Callable[[Section], str]] = {
    TEXT: lambda s: f"<p>{s.fields['html']}</p>",
    HEADING: lambda s: f"<h{s.fields['level']}>{s.fields['html']}</h{s.fields['level']}>",
    PICTURE: lambda s: _write_picture(s.fields),
    PICTURES: lambda s: _write_parts("pressless-pictures", s.parts[0]),
    BUTTON: lambda s: (f'<p class="pressless-button"><a href="{_attr(s.fields["href"])}">'
                       f"{_text(s.fields['label'])}</a></p>"),
    VIDEO: lambda s: _write_video(s.fields),
    MUSIC: lambda s: f'<audio controls preload="metadata" src="{_attr(s.fields["src"])}"></audio>',
    DOWNLOAD: lambda s: (f'<p class="pressless-download"><a href="{_attr(s.fields["href"])}"'
                         f" download>{_text(s.fields['label'])}</a></p>"),
    COLUMNS: lambda s: '<div class="pressless-columns">' + "".join(
        _wrap(_COLUMN, _write_parts("pressless-column", column)) for column in s.parts) + "</div>",
    _COLUMN: lambda s: _write_parts("pressless-column", s.parts[0]),
    SLIDESHOW: lambda s: _write_parts("pressless-slideshow", s.parts[0]),
    QUESTIONS: _write_questions,
    ENLARGE: lambda s: (f'<figure class="pressless-enlarge">{_img(s.fields)}'
                        f"{_caption(s.fields)}</figure>"),
    TOP: lambda s: f'<a class="pressless-top" href="#top">{_text(s.fields["label"])}</a>',
    COUNTDOWN: lambda s: (f'<p class="pressless-countdown" data-to="{_attr(s.fields["to"])}">'
                          f'{_text(s.fields["label"])} <time>'
                          f'{_text(s.fields["to"].replace("T", " "))}</time></p>'),
    # PRESS-0217 § 4.4: the writer's code verbatim, never read or changed.
    SCRIPT: lambda s: f"<script>{s.fields['code']}</script>",
    STYLE: lambda s: f"<style>{s.fields['code']}</style>",
}


def section_html(section: Section) -> str:
    """The section's bytes, marks included; for CODE, its `source`. Raises
    SectionRefused for anything §4.4 lists."""
    if section.kind == CODE:
        return section.source
    if section.kind not in KINDS:
        raise SectionRefused(f"there is no kind of section called {section.kind!r}")
    _check(section)
    return _wrap(section.kind, _WRITERS[section.kind](section))


# -------------------------------------------------------------- reading ----


def _read_attrs(tag: str) -> dict[str, str] | None:
    events = _scan(tag)
    if len(events) != 1 or events[0].kind not in ("start", "startend"):
        return None
    attrs = dict(events[0].attrs)
    if len(attrs) != len(events[0].attrs) or None in attrs.values():
        return None
    return attrs


def _read_picture(inner: str):
    found = re.fullmatch(r"(<img [^>]*>)|<figure>(<img [^>]*>)<figcaption>(.*)"
                         r"</figcaption></figure>", inner, re.S)
    if found is None:
        return None
    return _picture_attrs(found.group(1) or found.group(2), found.group(3))


def _picture_attrs(img: str, caption: str | None):
    attrs = _read_attrs(img)
    if attrs is None:
        return None
    if caption is not None:
        attrs["caption"] = caption
    return attrs


def _read_enlarge(inner: str):
    found = re.fullmatch(r'<figure class="pressless-enlarge">(<img [^>]*>)'
                         r"(?:<figcaption>(.*)</figcaption>)?</figure>", inner, re.S)
    return found and _picture_attrs(found.group(1), found.group(2))


def _read_countdown(inner: str):
    found = re.fullmatch(r'<p class="pressless-countdown" data-to="([^"]*)">(.*) <time>'
                         r"[^<]*</time></p>", inner, re.S)
    return found and {"to": _html.unescape(found.group(1)),
                      "label": _html.unescape(found.group(2))}


def _read_link(css: str, extra: str):
    def reader(inner: str):
        found = re.fullmatch(rf'<p class="{css}"><a href="([^"]*)"{extra}>(.*)</a></p>', inner,
                             re.S)
        return found and {"href": _html.unescape(found.group(1)),
                          "label": _html.unescape(found.group(2))}
    return reader


def _read_media(tag: str):
    def reader(inner: str):
        found = re.fullmatch(rf'<{tag} controls preload="metadata" src="([^"]*)"></{tag}>', inner)
        return found and {"src": _html.unescape(found.group(1))}
    return reader


def _read_video(inner: str):
    found = re.fullmatch(r'<iframe src="https://www\.youtube-nocookie\.com/embed/([^"]*)"'
                         r' title="YouTube video" allowfullscreen loading="lazy"></iframe>', inner)
    return {"youtube": found.group(1)} if found else _read_media("video")(inner)


_READERS: dict[str, Callable[[str], dict[str, str] | None]] = {
    TEXT: lambda inner: ({"html": inner[3:-4]} if inner.startswith("<p>")
                         and inner.endswith("</p>") else None),
    HEADING: lambda inner: ((found := re.fullmatch(r"<h([1-6])>(.*)</h\1>", inner, re.S))
                            and {"level": found.group(1), "html": found.group(2)}),
    PICTURE: _read_picture,
    BUTTON: _read_link("pressless-button", ""),
    VIDEO: _read_video,
    MUSIC: _read_media("audio"),
    DOWNLOAD: _read_link("pressless-download", " download"),
    ENLARGE: _read_enlarge,
    TOP: lambda inner: ((found := re.fullmatch(r'<a class="pressless-top" href="#top">(.*)</a>',
                                               inner, re.S))
                        and {"label": _html.unescape(found.group(1))}),
    COUNTDOWN: _read_countdown,
    SCRIPT: lambda inner: ((found := re.fullmatch(r"<script>(.*)</script>", inner, re.S))
                           and {"code": found.group(1)}),
    STYLE: lambda inner: ((found := re.fullmatch(r"<style>(.*)</style>", inner, re.S))
                          and {"code": found.group(1)}),
}

# §4.5: every form each kind has been written in, oldest first, as a reader
# beside its writer. The last is the one `section_html` writes. A change to a
# kind's HTML adds a form here and never removes one. The kinds that hold
# other sections have no reader here: `_Reading.candidate` and `questions`
# read them in their current HTML only, so an older form of one needs a reader
# there, changed together with its writer.
_FORMS: dict[str, tuple[tuple[Callable, Callable[[Section], str]], ...]] = {
    kind: ((_READERS.get(kind), _WRITERS[kind]),) for kind in (*KINDS, _COLUMN)
}

# What a section of each kind may hold, by where it sits (§4.3).
_AT_TOP = frozenset(KINDS)
_IN_COLUMNS = frozenset((_COLUMN,))
_IN_A_COLUMN = frozenset(KINDS) - _HOLDERS
_IN_AN_ANSWER = _IN_A_COLUMN
_IN_PICTURES = frozenset((PICTURE,))


class _Reading:
    def __init__(self, text: str, marks: list[_Mark]):
        self.text = text
        self.marks = marks
        self.at = {mark.start: mark for mark in marks}

    def partner(self, opening: _Mark, end: int) -> _Mark | None:
        """The closing mark of the same kind at the same depth, before `end`."""
        depth = 0
        for mark in self.marks:
            if mark.start < opening.end or mark.name != opening.name:
                continue
            if mark.end > end:
                return None
            if not mark.closing:
                depth += 1
            elif depth == 0:
                return mark
            else:
                depth -= 1
        return None

    def sequence(self, start: int, end: int, allowed) -> tuple[tuple[Section, ...],
                                                              tuple[str, ...]]:
        """§4.3's three rules over text[start:end]."""
        text, sections, gaps, pos = self.text, [], [], start
        while True:
            after_space = pos
            while after_space < end and text[after_space] in _WHITESPACE:
                after_space += 1
            gaps.append(text[pos:after_space])
            pos = after_space
            if pos == end:
                return tuple(sections), tuple(gaps)
            mark = self.at.get(pos)
            closing = self.partner(mark, end) if mark and not mark.closing else None
            if closing is not None:
                sections.append(self.section(mark, closing, allowed))
                pos = closing.end
                continue
            stop = next((other.start for other in self.marks
                         if not other.closing and pos < other.start < end), end)
            stop = len(text[:stop].rstrip(_WHITESPACE)) if stop > pos else stop
            sections.append(Section(CODE, source=text[pos:stop]))
            pos = stop

    def section(self, opening: _Mark, closing: _Mark, allowed) -> Section:
        source = self.text[opening.start:closing.end]
        if opening.name in allowed:
            for number, (reader, writer) in enumerate(_FORMS[opening.name]):
                found = self.candidate(opening.name, reader, opening.end, closing.start)
                if found is None:
                    continue
                try:
                    _check(found)
                    written = _wrap(found.kind, writer(found))
                except SectionRefused:
                    continue
                if written == source:
                    latest = number == len(_FORMS[opening.name]) - 1
                    return found if latest else Section(found.kind, found.fields, found.parts,
                                                        source)
        return Section(CODE, source=source)

    def candidate(self, kind: str, reader, start: int, end: int) -> Section | None:
        """The section `reader` finds in text[start:end], to be checked against
        its writer; None where it finds none."""
        if kind == QUESTIONS:
            return self.questions(start, end)
        if kind in (PICTURES, SLIDESHOW, COLUMNS, _COLUMN):
            css = {PICTURES: "pressless-pictures", SLIDESHOW: "pressless-slideshow",
                   COLUMNS: "pressless-columns", _COLUMN: "pressless-column"}[kind]
            opening, closing = f'<div class="{css}">', "</div>"
            inner = self.text[start:end]
            if not (inner.startswith(opening) and inner.endswith(closing)):
                return None
            allowed = {PICTURES: _IN_PICTURES, SLIDESHOW: _IN_PICTURES,
                       COLUMNS: _IN_COLUMNS, _COLUMN: _IN_A_COLUMN}[kind]
            parts, _gaps = self.sequence(start + len(opening), end - len(closing), allowed)
            if kind == COLUMNS:
                if any(part.kind != _COLUMN for part in parts):
                    return None
                return Section(COLUMNS, parts=tuple(part.parts[0] for part in parts))
            return Section(kind, parts=(parts,))
        fields = reader(self.text[start:end])
        return Section(kind, fields) if fields else None

    def questions(self, start: int, end: int) -> Section | None:
        """PRESS-0217 § 4.1: text[start:end] as `_write_questions` writes it,
        each question one marked paragraph in a `dt`, its answer the marked
        sections in the `dd` after it; None where it is anything else."""
        text = self.text
        opening, closing = '<dl class="pressless-questions">', "</dl>"
        if not (text.startswith(opening, start) and text.endswith(closing, start, end)):
            return None
        pos, stop, parts = start + len(opening), end - len(closing), []
        while pos < stop:
            asked = self.at.get(pos + len("<dt>"))
            if not text.startswith("<dt>", pos) or asked is None or asked.closing:
                return None
            asked_end = self.partner(asked, stop)
            if asked_end is None or not text.startswith("</dt><dd>", asked_end.end):
                return None
            answer = pos = asked_end.end + len("</dt><dd>")
            while (mark := self.at.get(pos)) is not None and not mark.closing:
                partner = self.partner(mark, stop)
                if partner is None:
                    return None
                pos = partner.end
            if not text.startswith("</dd>", pos):
                return None
            told, _gaps = self.sequence(answer, pos, _IN_AN_ANSWER)
            parts.append((self.section(asked, asked_end, frozenset((TEXT,))), *told))
            pos += len("</dd>")
        return Section(QUESTIONS, parts=tuple(parts))


def read(name: str, html: str) -> Page | None:
    """The page's sections area as sections, or None where it has none
    (§4.2). `name` is the page's, for the caller's messages."""
    marks = _marks(html, _scan(html))
    opening = next((mark for mark in marks if not mark.closing and mark.name == _PAGE), None)
    if opening is None:
        return None
    closing = next((mark for mark in marks if mark.closing and mark.name == _PAGE
                    and mark.start >= opening.end), None)
    if closing is None:
        return None
    inside = [mark for mark in marks if opening.end <= mark.start and mark.end <= closing.start]
    sections, gaps = _Reading(html, inside).sequence(opening.end, closing.start, _AT_TOP)
    return Page(html[:opening.end], sections, gaps, html[closing.start:])


def write(page: Page) -> str:
    """`before`, each gap and its section's bytes, the last gap, `after`."""
    middle = "".join(gap + _bytes(section)
                     for gap, section in zip(page.gaps[:-1], page.sections, strict=True))
    return page.before + middle + page.gaps[-1] + page.after


# ------------------------------------------------------------- adopting ----


def _node_end(events, first: int) -> int:
    """The index after the last event of the top-level node starting at
    events[first]: an element runs to its own end tag, counting nested ones
    of its name; anything else is one event."""
    event = events[first]
    if event.kind != "start" or event.tag in _VOID:
        return first + 1
    depth = 0
    for number in range(first + 1, len(events)):
        other = events[number]
        if other.tag == event.tag and other.kind == "start":
            depth += 1
        elif other.tag == event.tag and other.kind == "end":
            if depth == 0:
                return number + 1
            depth -= 1
    return len(events)


def _recognised(events) -> Section | None:
    """§4.6 step 2: a plain paragraph, heading or picture, as a section."""
    first = events[0]
    if first.kind in ("start", "startend") and first.tag == "img":
        attrs = dict(first.attrs)
        if (len(attrs) != len(first.attrs) or None in attrs.values()
                or not {"src", "alt"} <= set(attrs) <= {"src", "alt", "width", "height"}):
            return None
        return Section(PICTURE, attrs)
    heading = re.fullmatch(r"h([1-6])", first.tag)
    if (first.kind != "start" or first.attrs or (first.tag != "p" and not heading)
            or len(events) < 2 or events[-1].kind != "end" or events[-1].tag != first.tag):
        return None
    inline = _inline_from(events[1:-1])
    if inline is None:
        return None
    if heading:
        return Section(HEADING, {"level": heading.group(1), "html": inline})
    return Section(TEXT, {"html": inline})


def adopt(html: str, furniture: tuple[tuple[int, int], ...], element: str = "main"
          ) -> str | None:
    """§4.6: the page with its `main`'s content taken into sections; the page
    unchanged where it already has an area; None where there is no `main` to
    make one in. `furniture` is `builder.furniture_spans(name, html)`.
    `element` names another element to make the area in: `header` or `footer`
    for the furniture files (PRESS-0216 § 4.1)."""
    if read("", html) is not None:
        return html
    events = _scan(html)

    def in_furniture(at: int) -> bool:
        return any(start <= at < end for start, end in furniture)

    for first, event in enumerate(events):
        if event.kind != "start" or event.tag != element or in_furniture(event.start):
            continue
        last = _node_end(events, first) - 1
        if (events[last].kind != "end" or events[last].tag != element
                or in_furniture(events[last].start)):
            continue
        start, end = event.end, events[last].start
        if any(start <= span <= end for span, _end in furniture):
            return None
        return html[:start] + _sections_of(html, events[first + 1:last], start, end) + html[end:]
    return None


def _sections_of(html: str, events, start: int, end: int) -> str:
    """§4.6 step 3: html[start:end] as a sections area."""
    out, pos = ["<!-- pressless:page -->"], start

    def code(upto: int) -> None:
        run = html[pos:upto]
        body = run.strip(_WHITESPACE)
        if not body:
            out.append(run)
            return
        lead = len(run) - len(run.lstrip(_WHITESPACE))
        out.extend((run[:lead], _wrap(CODE, body), run[lead + len(body):]))

    number = 0
    while number < len(events):
        after = _node_end(events, number)
        section = _recognised(events[number:after])
        if section is not None:
            try:
                written = section_html(section)
            except SectionRefused:
                written = None
            if written is not None:
                code(events[number].start)
                out.append(written)
                pos = events[after - 1].end
        number = after
    code(end)
    out.append("<!-- /pressless:page -->")
    return "".join(out)


# ------------------------------------------------------------ publishing ---


def unmarked(name: str, html: str) -> str:
    """§4.7: `html` with every mark-shaped comment removed. A mark alone on
    its line takes the line with it. `name` is the page's."""
    cuts = []
    for mark in _marks(html, _scan(html)):
        line_start = html.rfind("\n", 0, mark.start) + 1
        line_end = html.find("\n", mark.end)
        line_end = len(html) if line_end < 0 else line_end + 1
        if (not html[line_start:mark.start].strip(" \t")
                and not html[mark.end:line_end].strip(" \t\r\n")):
            cuts.append((line_start, line_end))
        else:
            cuts.append((mark.start, mark.end))
    if not cuts:
        return html
    out, pos = [], 0
    for start, end in cuts:
        out.append(html[pos:start])
        pos = end
    out.append(html[pos:])
    return "".join(out)


# ------------------------------------------------- pieces.js (PRESS-0217) ---
#
# What makes a ready-made piece behave on the published site (§ 4.3). The
# Builder writes it into the site folder and links it from a published page
# only where that page carries a piece; never into a preview, since the Face's
# frame runs no script and a preview page opened on its own must run none
# either (§ 4.2, INV-2). It sits here beside the HTML it enhances, found by
# the classes and `data-` hooks the writers above give each piece. It reaches
# no network and shows no words of its own: the arrows are signs, and a
# countdown's units are the visitor's browser's own, in the visitor's language.

PIECES_SCRIPT = r"""(() => {
  "use strict";
  const each = (selector, enhance) => document.querySelectorAll(selector).forEach(enhance);
  const style = document.createElement("style");
  style.textContent = ".pressless-enlarge img{cursor:zoom-in}"
    + ".pressless-enlarged{padding:0;border:0;background:none;max-width:none;max-height:none}"
    + ".pressless-enlarged::backdrop{background:rgb(0 0 0 / .85)}"
    + ".pressless-enlarged img{display:block;max-width:95vw;max-height:90vh;"
    + "width:auto;height:auto;cursor:zoom-out}"
    + ".pressless-questions dt{cursor:pointer}"
    + ".pressless-slideshow-turn{display:flex;gap:.5em;align-items:center}";
  document.head.append(style);

  // A slideshow shows one picture at a time, with a sign either side to turn.
  each(".pressless-slideshow", (show) => {
    const slides = [...show.children];
    if (slides.length < 2) return;
    let at = 0;
    const turn = document.createElement("p");
    turn.className = "pressless-slideshow-turn";
    const count = document.createElement("span");
    count.setAttribute("aria-live", "polite");
    const sign = (text, by) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.addEventListener("click", () => go(at + by));
      return button;
    };
    const go = (to) => {
      at = (to + slides.length) % slides.length;
      slides.forEach((slide, number) => { slide.hidden = number !== at; });
      count.textContent = (at + 1) + " / " + slides.length;
    };
    turn.append(sign("‹", -1), count, sign("›", 1));
    show.after(turn);
    go(0);
  });

  // Questions fold shut, and each opens by its question.
  each(".pressless-questions", (list) => {
    list.querySelectorAll(":scope > dt").forEach((asked) => {
      const answer = asked.nextElementSibling;
      if (!answer || answer.localName !== "dd") return;
      const open = (shown) => {
        answer.hidden = !shown;
        asked.setAttribute("aria-expanded", String(shown));
      };
      asked.tabIndex = 0;
      asked.setAttribute("role", "button");
      asked.addEventListener("click", () => open(answer.hidden));
      asked.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        open(answer.hidden);
      });
      open(false);
    });
  });

  // A picture that enlarges fills the window until it is clicked or Escape.
  each(".pressless-enlarge img", (picture) => {
    const enlarge = () => {
      const shown = document.createElement("dialog");
      shown.className = "pressless-enlarged";
      const big = picture.cloneNode();
      big.removeAttribute("width");
      big.removeAttribute("height");
      shown.append(big);
      shown.addEventListener("click", () => shown.close());
      shown.addEventListener("close", () => { shown.remove(); picture.focus(); });
      document.body.append(shown);
      shown.showModal();
    };
    picture.tabIndex = 0;
    picture.setAttribute("role", "button");
    picture.addEventListener("click", enlarge);
    picture.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      enlarge();
    });
  });

  // Back to top glides there, unless the visitor asks for less motion.
  each(".pressless-top", (link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({top: 0, behavior: still ? "auto" : "smooth"});
    });
  });

  // A countdown shows the time left in the visitor's own words for the units,
  // and its end again once that has passed.
  each(".pressless-countdown", (box) => {
    const end = Date.parse(box.dataset.to);
    const shown = box.querySelector("time");
    if (!shown || Number.isNaN(end)) return;
    const target = shown.textContent;
    const unit = (name, amount) => new Intl.NumberFormat(undefined,
      {style: "unit", unit: name, unitDisplay: "long"}).format(amount);
    const tick = () => {
      const left = Math.floor((end - Date.now()) / 1000);
      if (left <= 0) {
        shown.textContent = target;
        clearInterval(timer);
        return;
      }
      const days = Math.floor(left / 86400), hours = Math.floor(left % 86400 / 3600);
      const parts = [];
      if (days) parts.push(unit("day", days));
      if (days || hours) parts.push(unit("hour", hours));
      parts.push(unit("minute", Math.floor(left % 3600 / 60)), unit("second", left % 60));
      shown.textContent = parts.join(" ");
    };
    const timer = setInterval(tick, 1000);
    tick();
  });
})();
"""
