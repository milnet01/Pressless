"""Reading a WordPress markup body (PRESS-0007 §4.3): whether a body is
markup at all, the marks it becomes, and the lines a reader sees. A classic
body that is not markup is first given its paragraphs (`autop`, PRESS-0125
§ 4.5).

Nothing here touches a disk. What a picture's address resolves to comes
from the lookups the caller passes, exactly as Marks takes `photo_src`.
"""
from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from pressless.marks import MARKS

Lookup = Callable[[str], str | None]

# §4.3: today's generator passes a body through as HTML where it holds a
# block comment, or one of these tags followed by a word boundary, in any
# case. Every other body it runs through wpautop(), and so is plain.
_HAS_TAGS = re.compile(r"<(p|div|img|a|blockquote|figure|ul|ol|h[1-6]|iframe|em|strong)\b", re.I)

# The two grammars a converted value must pass, read from the table that owns
# them rather than copied: a second copy is a second rule.
_COLOUR = next(row.arg for row in MARKS if row.name == "colour")
_LINK = next(row.arg for row in MARKS if row.name == "link")

_GALLERY = re.compile(r"\[gallery\b[^\]]*\]")
_GALLERY_IDS = re.compile(r'\bids\s*=\s*"([^"]*)"')
_SOCIAL_LINK = re.compile(r"^\s*wp:social-link\s+(\{.*\})\s*/?\s*$", re.S)

# HTML's own whitespace. Not \s: a no-break space the writer typed is not
# one a browser collapses, and collapsing it would change his line.
_HTML_SPACE = re.compile(r"[ \t\n\r\f]+")

_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input",
                   "link", "meta", "source", "track", "wbr"})
_HEADINGS = frozenset(f"h{n}" for n in range(1, 7))
_COLOURED = frozenset({"span", "p", "a", "div"}) | _HEADINGS
_PARAGRAPHS = frozenset({"p", "div", "figcaption"}) | _HEADINGS
_MEDIA = frozenset({"iframe", "video", "audio", "embed"})
_KNOWN = (_PARAGRAPHS | _MEDIA
          | {"#root", "br", "strong", "b", "em", "i", "span", "a", "img", "figure",
             "blockquote", "source"})
# The attributes §4.3's table reads. `style` is read wherever a colour may
# sit, and figure's class is what marks an embed. An img's alt is not carried
# but listed with its picture, so _picture reads it (decision 13).
_USED = {"a": {"href"}, "img": {"src", "alt"}, "figure": {"class"}, "source": {"src"},
         **{tag: {"src"} for tag in _MEDIA}}


def is_markup(body: str) -> bool:
    """§4.3: exactly where today's generator passes a body through."""
    return "<!-- wp:" in body or bool(_HAS_TAGS.search(body))


def wordpress_markup(body: str) -> bool:
    """PRESS-0125 § 4.5: as WordPress decides it. Block content is markup;
    any other body is a classic post, which WordPress gives paragraphs."""
    return "<!-- wp:" in body


# The tags autop leaves a run of text alone around: a run holding one is
# already laid out by its own markup.
_BLOCK_TAG = re.compile(
    r"</?(?:address|article|aside|audio|blockquote|dd|details|div|dl|dt|fieldset"
    r"|figcaption|figure|footer|form|h[1-6]|header|hr|iframe|li|main|nav|ol|p|pre"
    r"|section|table|tbody|td|tfoot|th|thead|tr|ul|video)\b", re.I)
_PRE = re.compile(r"<pre\b.*?</pre\s*>", re.I | re.S)
_BLANK_LINE = re.compile(r"\n[ \t]*\n")


def autop(body: str) -> str:
    """A classic post as WordPress shows it, written from PRESS-0125 § 4.5's
    description of that behaviour and never from WordPress's code (INV-12
    there): a blank line ends a paragraph and a lone newline is a line break,
    outside <pre> and runs holding a block-level tag."""
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    parts, position = [], 0
    for found in _PRE.finditer(text):
        parts.append(_paragraphs(text[position:found.start()]))
        parts.append(found.group(0))
        position = found.end()
    parts.append(_paragraphs(text[position:]))
    return "\n".join(part for part in parts if part)


def _paragraphs(text: str) -> str:
    runs = (run.strip("\n") for run in _BLANK_LINE.split(text))
    return "\n".join(
        run if _BLOCK_TAG.search(run) else "<p>" + run.replace("\n", "<br>\n") + "</p>"
        for run in runs if run.strip())


# ------------------------------------------------------------- the tree ----


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    children: list


@dataclass(frozen=True)
class _Comment:
    text: str


class _TreeBuilder(HTMLParser):
    """A forgiving tree: an end tag closes the nearest open element of its
    name, and one with none open is ignored. Character references in text
    are kept as written (§4.3); in an attribute the parser decodes them."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.root = _Element("#root", {}, [])
        self._open = [self.root]

    def handle_starttag(self, tag, attrs):
        element = _Element(tag, {name: value or "" for name, value in attrs}, [])
        self._open[-1].children.append(element)
        if tag not in _VOID:
            self._open.append(element)

    def handle_startendtag(self, tag, attrs):
        self._open[-1].children.append(
            _Element(tag, {name: value or "" for name, value in attrs}, []))

    def handle_endtag(self, tag):
        for depth in range(len(self._open) - 1, 0, -1):
            if self._open[depth].tag == tag:
                del self._open[depth:]
                return

    def handle_data(self, data):
        self._text(data)

    def handle_entityref(self, name):
        self._text(f"&{name};")

    def handle_charref(self, name):
        self._text(f"&#{name};")

    def handle_comment(self, data):
        self._open[-1].children.append(_Comment(data))

    def _text(self, text):
        children = self._open[-1].children
        if children and isinstance(children[-1], str):
            children[-1] += text
        else:
            children.append(text)


def _tree(markup: str) -> _Element:
    builder = _TreeBuilder()
    builder.feed(markup)
    builder.close()
    return builder.root


def _descendants(element: _Element, *, into_figures: bool = True):
    for child in element.children:
        if isinstance(child, _Element):
            yield child
            if into_figures or child.tag != "figure":
                yield from _descendants(child, into_figures=into_figures)


def _plain_text(element: _Element) -> str:
    parts = []

    def walk(node):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, _Element):
            for child in node.children:
                walk(child)

    walk(element)
    return _HTML_SPACE.sub(" ", "".join(parts)).strip()


# ------------------------------------------------------------ the lines ----

# PRESS-0161: a list item, a table's row or cell, a rule and a preformatted
# block each make a line too (PRESS-0125 § 4.5).
_LINES = frozenset({"li", "tr", "td", "th", "hr"})
_SPLITS = (frozenset({"br", "img", "div", "p", "blockquote", "figure", "pre"})
           | _HEADINGS | _LINES)
# What a reader never sees, so neither visible_lines nor _Converter.walk
# hands it on.
_HIDDEN = frozenset({"script", "style"})

# ----------------------------------------------------------- the report ----

# PRESS-0294: the Report names what was lost in words a reader who has never
# seen web code can act on. A tag missing here is named as layout.
_TAG_WORDS = {
    "script": "code the old site ran, left out",
    "style": "styling code from the old site, left out",
    **{tag: "a list, kept as plain lines" for tag in ("ul", "ol", "li")},
    **{tag: "a table, kept as plain lines"
       for tag in ("table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption")},
    "hr": "a dividing line, left out",
    **{tag: "text in a typewriter font, kept as ordinary text" for tag in ("pre", "code")},
}
_MEDIA_WORDS = {"video": "a video", "audio": "a sound clip", "iframe": "an embedded item",
                "embed": "an embedded item"}


def _tag_words(tag: str) -> str:
    return _TAG_WORDS.get(tag, f'some of the old site\'s layout ("{tag}"), its words kept')


def visible_lines(markup: str) -> tuple[str, ...]:
    """§4.3's instrument: the lines a reader sees. A new line at each <br>,
    <img>, <div>, heading, <li>, <tr>, <td>, <th> and <hr>, at each paragraph,
    quotation, figure and <pre> boundary, and at each newline inside <pre>;
    character references decoded, block comments and script and style
    contents removed, and whitespace inside a line collapsed."""
    lines: list[str] = []
    current: list[str] = []

    def end_line():
        text = re.sub(r"\s+", " ", html.unescape("".join(current))).strip()
        if text:
            lines.append(text)
        current.clear()

    def walk(node, preformatted: bool):
        if isinstance(node, str):
            pieces = node.split("\n") if preformatted else [node]
            for number, piece in enumerate(pieces):
                if number:
                    end_line()
                current.append(piece)
        elif isinstance(node, _Element) and node.tag not in _HIDDEN:
            splits = node.tag in _SPLITS
            if splits:
                end_line()
            for child in node.children:
                walk(child, preformatted or node.tag == "pre")
            if splits:
                end_line()

    walk(_tree(markup), False)
    end_line()
    return tuple(lines)


# -------------------------------------------------------- the conversion ----


@dataclass(frozen=True)
class _Style:
    bold: bool = False
    italic: bool = False
    colour: str | None = None
    link: str | None = None


_PLAIN = _Style()


class _Blocks:
    """What a container gathers: paragraphs of styled runs, lines already in
    marks (a picture, a link on its own line), and quotations."""

    def __init__(self):
        self.out: list[tuple] = []
        self.lines: list[list[tuple[str, _Style]]] = [[]]

    def text(self, text: str, style: _Style):
        self.lines[-1].append((text, style))

    def line_break(self):
        self.lines.append([])

    def end_paragraph(self):
        if any(text.strip() for line in self.lines for text, _ in line):
            self.out.append(("paragraph", self.lines))
        self.lines = [[]]

    def block(self, block: tuple):
        self.end_paragraph()
        self.out.append(block)


class _Converter:
    def __init__(self, by_address: Lookup, by_id: Lookup, old_site: str):
        self._by_address = by_address
        self._by_id = by_id
        self._old_site = bare_host(old_site)
        self._caption: str | None = None
        self._preformatted = 0
        self.dropped: list[str] = []
        # An entry's unread attributes and styles, each named once and said
        # in one line at the end (PRESS-0294).
        self.settings: dict[str, None] = {}
        self.formatting: dict[str, None] = {}

    # The table, row by row.

    def walk(self, node, style: _Style, blocks: _Blocks):
        if isinstance(node, _Comment):
            self._comment(node.text)
            return
        if isinstance(node, str):
            self._text(node, style, blocks)
            return
        tag = node.tag
        if tag in _HIDDEN:
            self.dropped.append(_tag_words(tag))
            return
        style = self._attributes(node, style)
        if tag == "br":
            blocks.line_break()
        elif tag in _PARAGRAPHS:
            if tag in _HEADINGS:
                self.dropped.append("a heading, kept as an ordinary paragraph")
            blocks.end_paragraph()
            self._children(node, style, blocks)
            blocks.end_paragraph()
        elif tag in ("strong", "b"):
            self._children(node, _replace(style, bold=True), blocks)
        elif tag in ("em", "i"):
            self._children(node, _replace(style, italic=True), blocks)
        elif tag == "a":
            self._anchor(node, style, blocks)
        elif tag == "img":
            self._picture(node, blocks)
        elif tag == "figure":
            self._figure(node, style, blocks)
        elif tag == "blockquote":
            inner = _Blocks()
            self._children(node, style, inner)
            inner.end_paragraph()
            blocks.block(("quote", inner.out))
        elif tag in _MEDIA:
            self._media(node, blocks)
        else:
            if tag not in _KNOWN:
                self.dropped.append(_tag_words(tag))
            # PRESS-0161: a line of its own, as a paragraph is.
            breaks = tag in _LINES or tag == "pre"
            if breaks:
                blocks.end_paragraph()
            self._preformatted += tag == "pre"
            self._children(node, style, blocks)
            self._preformatted -= tag == "pre"
            if breaks:
                blocks.end_paragraph()

    def _children(self, node: _Element, style: _Style, blocks: _Blocks):
        for child in node.children:
            self.walk(child, style, blocks)

    def _comment(self, text: str):
        found = _SOCIAL_LINK.match(text)
        if found is None:
            return
        try:
            address = json.loads(found.group(1)).get("url", "")
        except (ValueError, AttributeError):
            address = ""
        self.dropped.append(f"a social link, which today's site does not show: {address}")

    def _text(self, text: str, style: _Style, blocks: _Blocks):
        if self._preformatted:
            # Each of its newlines is a line; its spaces are the writer's.
            for number, piece in enumerate(text.split("\n")):
                if number:
                    blocks.line_break()
                blocks.text(piece.replace("\t", " "), style)
            return
        text = _HTML_SPACE.sub(" ", text)
        start = 0
        for found in _GALLERY.finditer(text):
            blocks.text(text[start:found.start()], style)
            self._gallery(found.group(0), blocks)
            start = found.end()
        blocks.text(text[start:], style)

    def _gallery(self, shortcode: str, blocks: _Blocks):
        ids = _GALLERY_IDS.search(shortcode)
        if ids is None:
            self.dropped.append("a gallery with no pictures in it, left out")
            return
        for attachment_id in (part.strip() for part in ids.group(1).split(",")):
            name = self._by_id(attachment_id) if attachment_id else None
            if name is None:
                self.dropped.append(
                    f"a gallery picture missing from the export, left out: number {attachment_id}")
            else:
                blocks.block(("line", f"{{photo: {name}}}"))

    def _attributes(self, node: _Element, style: _Style) -> _Style:
        """The attributes the table reads, and every other one listed."""
        used = _USED.get(node.tag, set())
        for name, value in node.attrs.items():
            if name == "style":
                style = self._style(node.tag, value, style)
            elif name not in used:
                self.settings[name] = None
        return style

    def _style(self, tag: str, declarations: str, style: _Style) -> _Style:
        for declaration in declarations.split(";"):
            prop, _, value = declaration.partition(":")
            prop, value = prop.strip().lower(), value.strip()
            if not prop:
                continue
            if prop == "color" and tag in _COLOURED and re.fullmatch(_COLOUR, value):
                style = _replace(style, colour=value)
            else:
                self.formatting[f"{prop} {value}"] = None
        return style

    def _anchor(self, node: _Element, style: _Style, blocks: _Blocks):
        href = node.attrs.get("href", "").strip()
        pictures = [child for child in _descendants(node) if child.tag == "img"]
        if pictures:
            # Decision 7: the picture alone. A link to its own full-size file
            # is an original and never published; any other is listed.
            own = self._by_address(href) if href else None
            names = {self._by_address(img.attrs.get("src", "")) for img in pictures}
            if href and (own is None or own not in names):
                self.dropped.append(f"a link on a picture, left out, the picture kept: {href}")
            self._children(node, style, blocks)
            return
        if not href:
            self._children(node, style, blocks)
        elif self._by_address(href) is not None:
            self.dropped.append(
                f"a link to a file that is not a picture, kept as plain words: {href}")
            self._children(node, style, blocks)
        elif self._old_site and _host(href) == self._old_site:
            self.dropped.append(f"a link to the old site, kept as plain words: {href}")
            self._children(node, style, blocks)
        elif re.fullmatch(_LINK, href):
            self._children(node, _replace(style, link=href), blocks)
        else:
            self.dropped.append(f"a link Pressless cannot keep, kept as plain words: {href}")
            self._children(node, style, blocks)

    def _picture(self, img: _Element, blocks: _Blocks):
        caption, self._caption = self._caption, None
        src = img.attrs.get("src", "").strip()
        name = self._by_address(src) if src else None
        # Decision 13: the text and the picture it describes, one line per
        # picture, so the maintainer can caption the few real ones by hand. An
        # empty alt describes nothing and is not listed.
        alt = " ".join(img.attrs.get("alt", "").split())
        if alt:
            where = name or (f"at {src}" if src else "with no address")
            self.dropped.append(
                f"the description of the picture {where}, for readers who cannot see it, "
                f"not kept: {alt}")
        if name is not None:
            mark = f"{{photo: {name} | {caption}}}" if caption else f"{{photo: {name}}}"
            blocks.block(("line", mark))
            return
        if src:
            self.dropped.append(
                f"a picture missing from the export, kept as a link to where it was: {src}")
            self._address_line(src, blocks)
        else:
            self.dropped.append("a picture with no address, left out")
        if caption:
            blocks.block(("paragraph", [[(caption, _PLAIN)]]))

    def _figure(self, node: _Element, style: _Style, blocks: _Blocks):
        blocks.end_paragraph()
        classes = node.attrs.get("class", "").split()
        own_pictures = [child for child in _descendants(node, into_figures=False)
                        if child.tag == "img"]
        if "wp-block-embed" in classes and not own_pictures and not any(
            child.tag in _MEDIA for child in _descendants(node)
        ):
            self._embed(node, blocks)
        elif own_pictures:
            captions = [child for child in node.children
                        if isinstance(child, _Element) and child.tag == "figcaption"]
            self._caption = _plain_text(captions[0]) if captions else None
            # A caption is plain text in Marks, so any markup in it -- a link,
            # a colour -- is lost here; decision 9 has that said (PRESS-0162).
            if captions and any(isinstance(child, _Element)
                                for child in _descendants(captions[0])):
                self.dropped.append("styling inside a picture's caption, its words kept")
            for child in node.children:
                if not (isinstance(child, _Element) and child.tag == "figcaption"):
                    self.walk(child, style, blocks)
            if self._caption:
                blocks.block(("paragraph", [[(self._caption, _PLAIN)]]))
            self._caption = None
        else:
            self._children(node, style, blocks)
        blocks.end_paragraph()

    def _embed(self, node: _Element, blocks: _Blocks):
        for child in node.children:
            if isinstance(child, _Element) and child.tag == "figcaption":
                self.walk(child, _PLAIN, blocks)
            elif isinstance(child, _Element):
                address = _plain_text(child)
                if address:
                    self._address(address, _MEDIA_WORDS["embed"], blocks)

    def _media(self, node: _Element, blocks: _Blocks):
        src = node.attrs.get("src", "").strip()
        if not src:
            sources = [child for child in _descendants(node) if child.tag == "source"]
            src = sources[0].attrs.get("src", "").strip() if sources else ""
        if not src:
            self.dropped.append(f"{_MEDIA_WORDS[node.tag]} with no address, left out")
            return
        self._address(src, _MEDIA_WORDS[node.tag], blocks)

    def _address(self, address: str, what: str, blocks: _Blocks):
        if self._by_address(address) is not None:
            self.dropped.append(f"{what} from a file that is not a picture, left out: {address}")
        else:
            self._address_line(address, blocks)

    def _address_line(self, address: str, blocks: _Blocks):
        """A video, an embed or a picture with no attachment: its address as
        a link's words, on its own line (§4.3)."""
        if re.fullmatch(_LINK, address):
            blocks.block(("line", f"{{link: {address}}}{address}{{/}}"))
        else:
            self.dropped.append(
                f"an address Pressless cannot make a link of, kept as plain words: {address}")
            blocks.block(("paragraph", [[(address, _PLAIN)]]))


def _replace(style: _Style, **changes) -> _Style:
    return _Style(**{**style.__dict__, **changes})


def bare_host(netloc: str) -> str:
    """A host as Import compares two: lower case, without a leading www."""
    return netloc.lower().removeprefix("www.")


def _host(address: str) -> str:
    return bare_host(urlparse(address).netloc)


# ------------------------------------------------------------ the marks ----


def _wrapped(text: str, style: _Style) -> str:
    """One run in its marks: link outermost, then colour, bold, italic."""
    if style.italic:
        text = f"*{text}*"
    if style.bold:
        text = f"**{text}**"
    if style.colour:
        text = f"{{{style.colour}}}{text}{{/}}"
    if style.link:
        text = f"{{link: {style.link}}}{text}{{/}}"
    return text


def _line(segments: list[tuple[str, _Style]], dropped: list[str]) -> str:
    """One line of runs. A wrap mark never begins or ends with whitespace and
    never crosses a line; a run both bold and italic is written bold (§4.3)."""
    runs: list[list] = []
    for text, style in segments:
        if style.bold and style.italic:
            dropped.append("words both bold and italic, now just bold")
            style = _replace(style, italic=False)
        if runs and runs[-1][1] == style:
            runs[-1][0] += text
        else:
            runs.append([text, style])
    out = []
    for text, style in runs:
        # Every whitespace character, not only the space: Marks reads U+00A0
        # as whitespace at a wrap's edge, so one left inside printed the
        # marker literally (§4.3, PRESS-0162).
        core = text.strip()
        if style == _PLAIN or not core:
            out.append(text)
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        out.append(lead + _wrapped(core, style) + trail)
    line = "".join(out).strip(" ")
    # A line beginning with > is Marks' quotation. His own > is text, so it
    # goes in as the character reference, which a reader sees the same.
    if line.startswith(">"):
        line = "&gt;" + line[1:]
    return line


def _paragraph(lines: list[list[tuple[str, _Style]]], dropped: list[str]) -> str:
    rendered = [_line(segments, dropped) for segments in lines]
    while rendered and not rendered[0]:
        rendered.pop(0)
    while rendered and not rendered[-1]:
        rendered.pop()
    return "\n".join(rendered)


def _marks(blocks: list[tuple], dropped: list[str]) -> str:
    parts: list[str] = []
    previous = None
    for kind, content in blocks:
        if kind == "paragraph":
            text = _paragraph(content, dropped)
        elif kind == "line":
            text = content
        else:
            inner = _marks(content, dropped)
            text = "\n".join(f"> {line}" if line.strip() else ">"
                             for line in inner.split("\n")) if inner else ""
        if not text:
            continue
        if parts:
            parts.append("\n" if kind == "line" and previous == "line" else "\n\n")
        parts.append(text)
        previous = kind
    return "".join(parts)


def convert(body: str, picture_by_address: Lookup, picture_by_id: Lookup, *,
            old_site: str = "", markup: Callable[[str], bool] | None = None,
            ) -> tuple[str, tuple[str, ...]]:
    """One markup body in marks, and what it could not carry (§4.3).

    `old_site` is the WordPress site's host: a link to one of its pages is
    not a link to another site, and keeps only its words. A body `markup`
    rejects is passed through `autop` first (PRESS-0125 § 4.5); with no
    `markup`, the body converts as it is.
    """
    if markup is not None and not markup(body):
        body = autop(body)
    converter = _Converter(picture_by_address, picture_by_id, old_site)
    blocks = _Blocks()
    converter.walk(_tree(body), _PLAIN, blocks)
    blocks.end_paragraph()
    text = _marks(blocks.out, converter.dropped)
    if converter.settings:
        converter.dropped.append("settings from the old site's look, which change nothing you "
                                 f"see now, left out: {', '.join(converter.settings)}")
    if converter.formatting:
        converter.dropped.append("formatting Pressless cannot show, left out, the words kept: "
                                 f"{', '.join(converter.formatting)}")
    return text, tuple(dict.fromkeys(converter.dropped))
