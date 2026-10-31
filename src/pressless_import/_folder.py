"""A folder of web pages into an empty Store (PRESS-0210).

The contract is docs/specs/PRESS-0210-folder-of-pages.md. `unpack_folder` lays a
ZIP out at import/folder/; `read_folder` says what that folder holds, writing
nothing; `bring_in_folder` writes it as `_bring.bring_in` writes an export, into
import/work/ and then all at once.

Every page keeps its bytes but for what the spec names, so nothing here parses a
page to write it back: each change is an edit at offsets `blocks`' scanner reports.
"""
from __future__ import annotations

import base64
import dataclasses
import html
import json
import os
import posixpath
import re
import shutil
import zipfile
import zlib
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from pressless import blocks, builder, menu, safe_write, sitefile, starter, store, templates
from pressless.words import say

from . import Dropped, ImportStopped, Report, _writing, resolve_slug
from ._bring import _MOVING, _WORK, IMPORT_FOLDER, finish

MEMBERS_MOST = 20_000                # a ZIP holding more is refused
SVG_LARGEST = 256 * 1024             # § 4.6
BROUGHT = "brought.json"             # in IMPORT_FOLDER: answers a Finish pressed again (§ 4.11)

_UP = "{{UP}}"                       # the Builder fills it in the furniture files alone
_NAVIGATION = "{{NAVIGATION}}"
_STYLE_LINK = f'<link rel="stylesheet" href="{_UP}{builder.STYLE_CODE}">'
_HOME = "Home"                       # what menu._nav and starter.home_page call the front page
_FRONT = "index"
_PAGE_SUFFIXES = (".html", ".htm")
_VERIFICATION = ("google", "yandex_", "pinterest-")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_CHARSET = re.compile(r"""<meta\b[^>]*?\bcharset\s*=\s*["']?\s*([\w.:-]+)""", re.I)
_OPENS_HEAD = re.compile(r"<head\b[^>]*>", re.I)
_OPENS_BODY = re.compile(r"<body\b", re.I)
# § 4.9: what the Builder would otherwise fill or read.
_BUILDER_MARK = re.compile(r"<!--\s*(?:(?:HEADER|FOOTER):(?:START|END)[^>]*?"
                           r"|/?pressless:[a-z]+\s*)-->")
_SCRIPT_CLOSES = re.compile(r"</script|<!--.*<script", re.I | re.S)
_TAG_OPENING = re.compile(r"<[^\s/>]+")
_ATTRIBUTE = re.compile(r"""\s*([^\s=>/"']+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>"']+))?""")
_CANDIDATE = re.compile(r"(\s*)(\S+)([^,]*)(,?)")
_TAGS = re.compile(r"<[^>]*>")
# In a CSS file: what must be read, and a comment or string, which must not be.
_CSS_TOKEN = re.compile(
    r"""/\*.*?\*/
    | (?P<charset>@charset\s+(?:"[^"]*"|'[^']*')\s*;[ \t]*\r?\n?)
    | (?P<import>@import\s+
        (?:url\(\s*(?:"(?P<i1>[^"]*)"|'(?P<i2>[^']*)'|(?P<i3>[^)\s]*))\s*\)
           |"(?P<i4>[^"]*)"|'(?P<i5>[^']*)')
        (?P<condition>[^;]*);[ \t]*\r?\n?)
    | (?<![\w-])url\(\s*(?:"(?P<u1>[^"]*)"|'(?P<u2>[^']*)'|(?P<u3>[^)\s]*))\s*\)
    | "(?:[^"\\\n]|\\.)*"
    | '(?:[^'\\\n]|\\.)*'
    """, re.I | re.S | re.X)
# § 4.8: an end tag a browser does not need, so its absence unbalances nothing.
_MAY_STAY_OPEN = frozenset(("p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "tfoot",
                            "option", "optgroup", "colgroup", "caption"))
_MENU_IDS = frozenset(("nav", "menu", "navigation"))
_MENU_MARKS = frozenset(("active", "current", "selected"))
_NOT_FURNITURE_IN = frozenset(("main", "article", "section"))


@dataclass(frozen=True)
class Found:
    pages: tuple[str, ...]           # folder-relative paths
    photographs: tuple[str, ...]
    files: tuple[str, ...]
    inside_pages: tuple[str, ...]    # scripts and SVGs a page carries (§ 4.6)
    style: tuple[str, ...]           # stylesheets (§ 4.7)
    left: tuple[tuple[str, str], ...]  # (path, why it will not come across)
    roots: tuple[str, ...]           # root entries holding a path not in left
    built_by_a_tool: bool            # § 4.3
    left_links: tuple[tuple[str, str], ...] = ()  # (page, a left path it links to) (§ 4.11)


@dataclass(frozen=True)
class Brought:
    report: Report
    roots: tuple[str, ...]           # root entries something was carried from


# ------------------------------------------------- what may be kept (§ 4.1) ----


class _Paths:
    """The paths taken so far, folded, so a second one a case-blind drive could
    not hold beside them is noticed, a folder's path among them."""

    def __init__(self) -> None:
        self._files: set[str] = set()
        self._folders: set[str] = set()

    def take(self, path: str) -> bool:
        folded = path.casefold().split("/")
        above = {"/".join(folded[:n]) for n in range(1, len(folded))}
        whole = "/".join(folded)
        if whole in self._files or whole in self._folders or above & self._files:
            return False
        self._files.add(whole)
        self._folders |= above
        return True


def _why_not_kept(path: str, size: int, taken: _Paths) -> str | None:
    """§ 4.1's three tests, which § 4.3 makes again for a repository's paths."""
    if size > builder.FILE_LARGEST:
        return say("import.folder.why.large", **builder.largest_slots())
    try:
        for segment in path.split("/"):
            store.file_path_for(Path(), segment)
    except store.StoreError:
        return say("import.folder.why.segment")
    if not taken.take(path):
        return say("import.folder.why.twin")
    return None


def _one_top_folder(names: list[str]) -> str:
    """The folder every member sits inside, with its slash, or ""."""
    tops = {name.split("/", 1)[0] for name in names}
    if len(tops) == 1 and all("/" in name for name in names):
        return f"{tops.pop()}/"
    return ""


def unpack_folder(source: Path, into: Path, room: Callable[[], int]
                  ) -> tuple[tuple[str, str], ...]:
    """§ 4.1: every member checked first, and any failure refuses the ZIP and
    writes nothing. What is left out is returned with why. `into` is replaced."""
    into = Path(into)
    staged = into.with_name(f".{into.name}.part")
    try:
        with zipfile.ZipFile(source) as held:
            infos = held.infolist()
            if len(infos) > MEMBERS_MOST:
                raise ImportStopped("the ZIP holds too many files")
            for info in infos:
                # As stored: on Windows, zipfile turns a backslash into `/` in `filename`,
                # and § 4.1 refuses such a ZIP on every system.
                if not sitefile.stays_inside(info.orig_filename):
                    raise ImportStopped("the ZIP holds a name outside its folder")
                if sitefile.is_link(info):
                    raise ImportStopped("the ZIP holds a link")
            members = [info for info in infos if not info.is_dir()]
            top = _one_top_folder([info.filename for info in members])
            taken, kept, left = _Paths(), [], []
            for info in members:
                path = info.filename.removeprefix(top)
                why = _why_not_kept(path, info.file_size, taken)
                if why is None:
                    kept.append((path, info))
                else:
                    left.append((path, why))
            if sum(info.file_size for _path, info in kept) > room():
                raise ImportStopped("the ZIP's files are larger than the room on this drive")
            shutil.rmtree(staged, ignore_errors=True)
            staged.mkdir(parents=True)
            for path, info in kept:
                target = staged / path
                target.parent.mkdir(parents=True, exist_ok=True)
                with held.open(info) as unpacked, open(target, "wb") as out:
                    shutil.copyfileobj(unpacked, out)
        if into.exists():
            shutil.rmtree(into)
        os.replace(staged, into)
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError,
            zlib.error) as exc:
        shutil.rmtree(staged, ignore_errors=True)
        raise ImportStopped(f"the ZIP could not be read ({type(exc).__name__})") from None
    except ImportStopped:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return tuple(left)


# ------------------------------------------------------------ text (§ 4.9) ----


def _decoded(data: bytes, declared: str = "") -> tuple[str, bool] | None:
    """The text, and whether it was in an older encoding; None where nothing
    decodes it."""
    try:
        return data.removeprefix(b"\xef\xbb\xbf").decode("utf-8"), False
    except UnicodeDecodeError:
        pass
    for encoding in (declared, "cp1252"):
        try:
            return data.decode(encoding), True
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def _page_text(data: bytes) -> tuple[str, bool] | None:
    found = _CHARSET.search(data[:4096].decode("latin-1"))
    return _decoded(data, found.group(1) if found else "")


def _declares_utf8(text: str) -> str:
    """§ 4.9: the declared charset rewritten; one added where none is declared."""
    found = _CHARSET.search(text)
    if found:
        return text[:found.start(1)] + "utf-8" + text[found.end(1):]
    tag = '<meta charset="utf-8">'
    head = _OPENS_HEAD.search(text)
    if head:
        return text[:head.end()] + tag + text[head.end():]
    body = _OPENS_BODY.search(text)
    return text[:body.start()] + tag + text[body.start():] if body else text


# ------------------------------------------------------ addresses (§ 4.5) ----


def _split_address(address: str) -> tuple[str, str] | None:
    """The address's path and its query and fragment; None for one that stays
    as written: a scheme or host, only a fragment or query, or nothing."""
    address = address.strip()
    if not address or address[0] in "#?" or address.startswith("//") or _SCHEME.match(address):
        return None
    at = min((found for found in (address.find("?"), address.find("#")) if found >= 0),
             default=len(address))
    return address[:at], address[at:]


def _place_from(path: str, own: str) -> str:
    """The path `path` names, read from the file at `own`, from the folder's
    root. A browser stops climbing at the root, and so does this."""
    joined = unquote(path) if path.startswith("/") else (
        f"{posixpath.dirname(own)}/{unquote(path)}")
    parts: list[str] = []
    for segment in joined.split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment not in ("", "."):
            parts.append(segment)
    return "/".join(parts)


class _Folder:
    """Every path in the folder, for § 4.5's order of looking."""

    def __init__(self, files: list[str]) -> None:
        self.files = frozenset(files)
        self.folders = frozenset({"", *(parent for path in files
                                        for parent in _parents(path))})
        self.roots = frozenset(path.split("/")[0] for path in files)

    def _look(self, place: str) -> str | None:
        if place in self.files:
            return place
        joined = f"{place}/" if place else ""
        if place in self.folders:
            for name in ("index.html", "index.htm"):
                if f"{joined}{name}" in self.files:
                    return f"{joined}{name}"
        for suffix in _PAGE_SUFFIXES:
            if place and f"{place}{suffix}" in self.files:
                return f"{place}{suffix}"
        return None

    def resolved(self, path: str, own: str) -> str | None:
        """The folder's file that `path`, on the page `own`, reaches."""
        place = _place_from(path, own)
        found = self._look(place)
        if found is None and path.startswith("/") and place.split("/")[0] not in self.roots:
            # A site served under its repository's name writes that name first.
            found = self._look(place.partition("/")[2])
        return found

    def target(self, address: str, own: str) -> str | None:
        """The file an address as written reaches; None for one naming no
        file here, or one that stays as written."""
        split = _split_address(address)
        return self.resolved(split[0], own) if split else None


def _parents(path: str) -> Iterator[str]:
    parts = path.split("/")
    for number in range(1, len(parts)):
        yield "/".join(parts[:number])


# ---------------------------------------------------- reading a page's parts ----


@dataclass(frozen=True)
class _Spot:
    """A place in a page's text an address is written. `kind` says how to read
    `value`, which is decoded; `start` and `end` hold it, quotes and all."""
    kind: str
    start: int
    end: int
    value: str
    quote: str = '"'
    tag: str = ""
    attribute: str = ""
    media: str = ""                  # SHEET: its `media` attribute
    remove_to: int = 0               # SHEET and SCRIPT: where the element ends
    element: int = 0                 # SHEET and SCRIPT: where the element starts
    src: tuple[int, int] = (0, 0)    # SCRIPT: the attribute, its leading space too
    tag_end: int = 0                 # SCRIPT: where its start tag ends
    module: bool = False
    defer: bool = False


_ADDRESS, _SRCSET, _CSS, _SHEET, _SCRIPT = "address", "srcset", "css", "sheet", "script"


def _attributes(tag: str) -> Iterator[tuple[str, str | None, re.Match]]:
    """Each attribute of a start tag, its name lower-cased and its value as
    written, with the match holding its offsets in `tag`."""
    opening = _TAG_OPENING.match(tag)
    pos = opening.end() if opening else 0
    while pos < len(tag):
        found = _ATTRIBUTE.match(tag, pos)
        if found is None:
            pos += 1
            continue
        yield found.group(1).lower(), found.group(2), found
        pos = found.end()


def _unquoted(written: str) -> tuple[str, str]:
    """An attribute's value without its quotes, decoded, and the quote it wore."""
    if written[:1] in ("'", '"'):
        return html.unescape(written[1:-1]), written[0]
    return html.unescape(written), '"'


def _closing(events, first: int) -> int | None:
    """The index of the end tag closing the element opened at `first`."""
    tag, depth = events[first].tag, 0
    for number in range(first, len(events)):
        event = events[number]
        if event.tag == tag and event.kind == "start":
            depth += 1
        elif event.tag == tag and event.kind == "end":
            depth -= 1
            if depth == 0:
                return number
    return None


def _spots(text: str) -> list[_Spot]:
    """§ 4.5's places, stylesheet links and script files included, in order."""
    events = blocks._scan(text)
    found: list[_Spot] = []
    for number, event in enumerate(events):
        if event.kind not in ("start", "startend"):
            continue
        tag = text[event.start:event.end]
        attrs = {name: value for name, value in event.attrs}
        if (event.tag == "link" and attrs.get("href")
                and "stylesheet" in (attrs.get("rel") or "").lower().split()):
            found.append(_Spot(_SHEET, event.start, event.end, attrs["href"], tag="link",
                               attribute="href", media=(attrs.get("media") or "").strip(),
                               element=event.start, remove_to=event.end))
            continue
        if event.tag == "script" and attrs.get("src") and event.kind == "start":
            closed = _closing(events, number)
            if closed is not None:
                found.append(_script_spot(event, events[closed], tag, attrs))
                continue
        for name, written, match in _attributes(tag):
            if written is None:
                continue
            at = event.start + match.start(2)
            value, quoted = _unquoted(written)
            kind = {"href": _ADDRESS, "src": _ADDRESS, "poster": _ADDRESS, "srcset": _SRCSET,
                    "style": _CSS}.get(name)
            if kind is not None:
                found.append(_Spot(kind, at, at + len(written), value, quoted, event.tag, name))
        if event.tag == "style" and event.kind == "start":
            closed = _closing(events, number)
            if closed is not None and event.end < events[closed].start:
                found.append(_Spot(_CSS, event.end, events[closed].start,
                                   text[event.end:events[closed].start], tag="style",
                                   element=event.start))
    return found


def _script_spot(event, closing, tag: str, attrs: dict) -> _Spot:
    src = (0, 0)
    for name, _written, match in _attributes(tag):
        if name == "src":
            src = (event.start + match.start(), event.start + match.end())
    return _Spot(_SCRIPT, event.start, event.end, attrs["src"], tag="script", attribute="src",
                 element=event.start, remove_to=closing.end, src=src, tag_end=event.end,
                 module=(attrs.get("type") or "").strip().lower() == "module",
                 defer="defer" in attrs)


# What an address is used as, for § 4.6's rule on SVG.
_IN_IMAGE, _ELSEWHERE = True, False


def _url_written(found: re.Match, write: Callable[[str, bool], str | None]) -> str | None:
    """A url() token through `write`; None where it stays."""
    address = found.group("u1") or found.group("u2") or found.group("u3")
    if not address:
        return None
    new = write(address, _IN_IMAGE)
    if new is None:
        return None
    whole = found.group(0)
    at = whole.index(address)
    return whole[:at] + new + whole[at + len(address):]


def _new_css(css: str, write: Callable[[str, bool], str | None],
             in_style_code: Callable[[str], bool] = lambda address: False) -> str | None:
    """Each url() in `css` through `write`, and each @import of what is now in
    the style code gone; None where nothing changed."""
    changed = False

    def token(found: re.Match) -> str:
        nonlocal changed
        if found.group("import") and in_style_code(_import_address(found)):
            changed = True
            return ""
        new = _url_written(found, write)
        changed = changed or new is not None
        return found.group(0) if new is None else new

    written = _CSS_TOKEN.sub(token, css)
    return written if changed else None


def _new_srcset(value: str, write: Callable[[str, bool], str | None]) -> str | None:
    """Each candidate in a srcset through `write`; None where none changed."""
    changed = False

    def candidate(found: re.Match) -> str:
        nonlocal changed
        lead, address, descriptor, comma = found.groups()
        if address.endswith(","):
            address, comma = address[:-1], ","
        new = write(address, _ELSEWHERE)
        changed = changed or new is not None
        return f"{lead}{new if new is not None else address}{descriptor}{comma}"

    written = _CANDIDATE.sub(candidate, value)
    return written if changed else None


def _new_value(spot: _Spot, write: Callable[[str, bool], str | None]) -> str | None:
    """What a spot's value becomes through `write`; None where it stays."""
    if spot.kind == _CSS:
        return _new_css(spot.value, write)
    if spot.kind == _SRCSET:
        return _new_srcset(spot.value, write)
    return write(spot.value, spot.tag == "img" and spot.attribute == "src")


# --------------------------------------------------------- reading (§ 4.3) ----


@dataclass
class _Read:
    """A folder read, and what writing it needs beside `Found`."""
    folder: _Folder
    root: Path
    pages: dict[str, tuple[str, bool]]  # path: (text, was in an older encoding)
    photographs: list[str]
    files: list[str]
    carried: set[str]                # scripts and SVGs that go inside pages
    style: list[str]                 # the stylesheets, in § 4.7's order
    links: dict[str, str]            # a linked stylesheet: its first `media`
    sheet_pages: dict[str, set[str]]
    left: dict[str, str]
    left_links: list[tuple[str, str]] = field(default_factory=list)
    built_by_a_tool: bool = False

    def text_of(self, path: str) -> str:
        """The text of a stylesheet or script, which reading found decodes."""
        decoded = _decoded((self.root / path).read_bytes())
        return decoded[0] if decoded else ""


def _names(folder: Path) -> list[str]:
    """Every file in `folder`, relative, in path order. Neither way in lays a
    link out: unpacking refuses one, and a repository's arrives as a file."""
    found = []
    for at, _folders, files in os.walk(folder):
        for name in files:
            found.append((Path(at) / name).relative_to(folder).as_posix())
    return sorted(found)


def _verification(path: str, text: str) -> bool:
    name = path.casefold()
    return "/" not in path and (name.startswith(_VERIFICATION) or "<" not in text)


def _opens_with_a_rule(text: str) -> bool:
    first, _newline, _rest = text.partition("\n")
    return first.rstrip() == "---"


def _sort_files(folder: Path, names: list[str]):
    """§ 4.3's table, but for what only the pages' uses can decide: the pages,
    photographs and files; and `rest`, each .css, .js and .svg, and each left."""
    pages: dict[str, tuple[str, bool]] = {}
    photographs, files, rest = [], [], []
    left: dict[str, str] = {}
    taken = _Paths()
    for path in names:
        where = folder / path
        if any(segment.startswith(".") for segment in path.split("/")):
            left[path] = say("import.folder.why.dot")
        elif (why := _why_not_kept(path, where.stat().st_size, taken)) is not None:
            left[path] = why
        elif path == "CNAME":
            left[path] = say("import.folder.why.cname")
        elif path.casefold() == "404.html":
            left[path] = say("import.folder.why.lost")
        elif path.casefold().endswith(_PAGE_SUFFIXES):
            decoded = _page_text(where.read_bytes())
            if decoded is None:
                left[path] = say("import.folder.why.undecodable")
            elif _verification(path, decoded[0]):
                left[path] = say("import.folder.why.verification")
            else:
                pages[path] = decoded
        elif builder.photograph_format(where) is not None:
            photographs.append(path)
        elif builder.file_allowed(path.rsplit("/", 1)[-1], where.read_bytes()):
            files.append(path)
        else:
            rest.append(path)
    return pages, photographs, files, rest, left


def _can_carry_script(folder: Path, path: str) -> bool:
    """§ 4.6's test of a file's text; `<!--` followed by `<script` changes where
    a browser reads the element's end, and a Builder mark would be filled."""
    decoded = _decoded((folder / path).read_bytes())
    return (decoded is not None and not _SCRIPT_CLOSES.search(decoded[0])
            and not _BUILDER_MARK.search(decoded[0]))


def read_folder(folder: Path) -> Found:
    """§ 4.3: what `folder` holds. Reads, and writes nothing else."""
    held = _read_folder(Path(folder))
    left = tuple(sorted(held.left.items()))
    not_left = [path for path in sorted(held.folder.files) if path not in held.left]
    return Found(
        pages=tuple(held.pages), photographs=tuple(held.photographs), files=tuple(held.files),
        inside_pages=tuple(sorted(held.carried)), style=tuple(held.style), left=left,
        roots=tuple(sorted({path.split("/")[0] for path in not_left})),
        built_by_a_tool=held.built_by_a_tool, left_links=tuple(held.left_links))


@dataclass
class _Uses:
    """What every page's addresses reach."""
    all: list[tuple[str, str]] = field(default_factory=list)   # (page or sheet, file)
    links: dict[str, str] = field(default_factory=dict)        # a sheet: its first `media`
    sheet_pages: dict[str, set[str]] = field(default_factory=dict)
    scripts: set[str] = field(default_factory=set)
    pictures: set[str] = field(default_factory=set)


def _survey(root: Path, folder: _Folder, pages: dict[str, tuple[str, bool]],
            rest: set[str]) -> _Uses:
    """Which stylesheets, scripts and SVGs the pages use, as § 4.3 needs."""
    uses = _Uses()

    def is_kind(target: str | None, suffix: str) -> bool:
        return target is not None and target in rest and target.casefold().endswith(suffix)

    for path, (text, _older) in pages.items():
        if _holds_base(text):
            continue

        def noted(address: str, image: bool, path: str = path) -> None:
            target = folder.target(address, path)
            if target is not None:
                uses.all.append((path, target))
                if image and is_kind(target, ".svg"):
                    uses.pictures.add(target)

        for spot in _spots(text):
            target = folder.target(spot.value, path)
            if spot.kind == _SHEET and is_kind(target, ".css"):
                uses.links.setdefault(target, spot.media)
                uses.sheet_pages.setdefault(target, set()).add(path)
            elif (spot.kind == _SCRIPT and not spot.module and is_kind(target, ".js")
                    and _can_carry_script(root, target)):
                uses.scripts.add(target)
            elif spot.kind in (_SHEET, _SCRIPT):
                noted(spot.value, _ELSEWHERE)
            else:
                _new_value(spot, noted)
            if spot.tag == "style" and spot.kind == _CSS:
                for token in _CSS_TOKEN.finditer(spot.value):
                    target = folder.target(_import_address(token), path) if token.group(
                        "import") else None
                    if is_kind(target, ".css"):
                        uses.links.setdefault(target, token.group("condition").strip())
                        uses.sheet_pages.setdefault(target, set()).add(path)
    return uses


def _read_folder(root: Path) -> _Read:
    names = _names(root)
    folder = _Folder(names)
    pages, photographs, files, rest, left = _sort_files(root, names)
    uses = _survey(root, folder, pages, set(rest))
    style = _reach_sheets(root, folder, uses, set(rest))
    pictures = {path for path in uses.pictures if (root / path).stat().st_size <= SVG_LARGEST}
    carried = uses.scripts | pictures
    for path in rest:
        if path not in carried and path not in style:
            left[path] = say(_why_left(path))
    left_links = list(dict.fromkeys((own, target) for own, target in uses.all if target in left))
    built = ".nojekyll" not in names and (
        "_config.yml" in names or "_layouts" in folder.folders
        or any(_opens_with_a_rule(text) for text, _older in pages.values()))
    return _Read(folder, root, pages, photographs, files, carried, style, uses.links,
                 uses.sheet_pages, left, left_links, built)


def _why_left(path: str) -> str:
    suffix = path.casefold().rpartition(".")[2]
    return {"css": "import.folder.why.sheet", "js": "import.folder.why.script",
            "svg": "import.folder.why.svg"}.get(suffix, "import.folder.why.kind")


def _holds_base(text: str) -> bool:
    return any(event.tag == "base" and event.kind in ("start", "startend")
               for event in blocks._scan(text))


def _import_address(found: re.Match) -> str:
    """The address an @import token names."""
    return next(value for value in (found.group(name) for name in ("i1", "i2", "i3", "i4", "i5"))
                if value is not None)


def _reach_sheets(root: Path, folder: _Folder, uses: _Uses, rest: set[str]) -> list[str]:
    """§ 4.7: each sheet the pages link, and each one those import, once, in
    join order. A sheet's pages include those of whatever imports it, and an
    SVG one names joins the pictures."""
    reached: list[str] = []

    def walk(path: str, seen: set[str], pages: set[str]) -> None:
        uses.sheet_pages.setdefault(path, set()).update(pages)
        decoded = _decoded((root / path).read_bytes())
        if path in seen or decoded is None:
            return
        seen.add(path)
        if path not in reached:
            reached.append(path)
        for found in _CSS_TOKEN.finditer(decoded[0]):
            if found.group("import"):
                target = folder.target(_import_address(found), path)
                if target in rest and target.casefold().endswith(".css"):
                    walk(target, seen, pages)
                elif target is not None:
                    uses.all.append((path, target))
            elif (address := found.group("u1") or found.group("u2") or found.group("u3")):
                target = folder.target(address, path)
                if target is not None:
                    uses.all.append((path, target))
                    if target in rest and target.casefold().endswith(".svg"):
                        uses.pictures.add(target)

    for path in uses.links:
        walk(path, set(), set(uses.sheet_pages[path]))
    return reached


# --------------------------------------------------------- names (§ 4.4) ----


def _page_refused(name: str) -> bool:
    try:
        store.html_path_for(Path(), store.PAGES_FOLDER, name)
    except store.StoreError:
        return True
    return False


def _without_suffix(path: str) -> str:
    return path.rpartition(".")[0]


def _front_page(pages: list[str]) -> tuple[str, bool]:
    """The front page's path, and whether it was chosen rather than found."""
    # Folded, as a site made on Windows may say INDEX.HTM.
    folded = {path.casefold(): path for path in reversed(pages)}
    for name in ("index.html", "index.htm"):
        if name in folded:
            return folded[name], False
    for stem in ("home", "default"):
        for suffix in _PAGE_SUFFIXES:
            if f"{stem}{suffix}" in folded:
                return folded[f"{stem}{suffix}"], True
    return pages[0], True


def _name_pages(pages: list[str]) -> tuple[dict[str, str], list[tuple[str, str]], list[Dropped]]:
    """Each page's name, in path order so a run gives the same names, with each
    one renamed, and the front page's choice where one was made."""
    front, chosen = _front_page(pages)
    names = {front: _FRONT}
    renamed: list[tuple[str, str]] = []
    taken = {_FRONT}
    for path in pages:
        if path == front:
            continue
        stem = _without_suffix(path)
        wanted = resolve_slug(stem.removesuffix("/index"), "page")
        name, number = wanted, 1
        while name in taken or _page_refused(name):
            number += 1
            name = f"{wanted}-{number}"
        if name != wanted:
            renamed.append((wanted, name))
        names[path] = name
        taken.add(name)
    listed = [Dropped(f"{store.PAGES_FOLDER}/{_FRONT}", say("import.folder.front", path=front))
              ] if chosen else []
    return names, renamed, listed


def _name_held(paths: list[str], path_for: Callable[[Path, str], Path]
               ) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """§ 4.4: a photograph or file keeps its name; one taken or refused takes
    its folders before the name, then a number."""
    names: dict[str, str] = {}
    renamed: list[tuple[str, str]] = []
    taken: set[str] = set()

    def free(name: str) -> bool:
        if name.casefold() in taken:
            return False
        try:
            path_for(Path(), name)
        except store.StoreError:
            return False
        return True

    for path in paths:
        own = path.rsplit("/", 1)[-1]
        name = own
        if not free(name):
            joined = path.replace("/", "-")
            stem, dot, suffix = joined.rpartition(".")
            name, number = joined, 1
            while not free(name):
                number += 1
                name = f"{stem}-{number}{dot}{suffix}"
            renamed.append((path, name))
        names[path] = name
        taken.add(name.casefold())
    return names, renamed


def _page_place(name: str) -> str:
    return "index.html" if name == _FRONT else f"pages/{name}{store.HTML_SUFFIX}"


# -------------------------------------------- writing a page's addresses ----


class _Writer:
    """§ 4.5's rows, read from what the folder became."""

    def __init__(self, held: _Read, names: dict[str, str], photographs: dict[str, str],
                 files: dict[str, str]) -> None:
        self.held = held
        self.places = {path: _page_place(name) for path, name in names.items()}
        self.places |= {path: builder.web_photograph(name) for path, name in photographs.items()}
        self.places |= {path: builder.web_file(name) for path, name in files.items()}
        self.named: set[str] = set()     # what some address reached

    def address(self, address: str, own: str, up: str, listed: list[str], image: bool
                ) -> str | None:
        """What `address`, on the file `own`, is written as, `up` from the
        root; None where it stays as written."""
        split = _split_address(address)
        if split is None:
            return None
        path, tail = split
        target = self.held.folder.resolved(path, own)
        if target is not None and target in self.held.carried and image and (
                target.casefold().endswith(".svg")):
            data = base64.b64encode((self.held.root / target).read_bytes()).decode("ascii")
            return f"data:image/svg+xml;base64,{data}"
        if target is not None and target in self.places:
            self.named.add(target)
            return up + self.places[target] + tail
        place = target if target is not None else _place_from(path, own)
        listed.append(say("import.folder.not_carried", path=place))
        trailing = "/" if path.endswith("/") and place else ""
        return up + quote(place, safe="/") + trailing + tail

    def page(self, text: str, own: str) -> tuple[str, list[str], list[str]]:
        """The page's addresses written with `{{UP}}`, its stylesheet links
        down to one, and its scripts inside it. With each script moved to the
        end of the body, and what to list."""
        listed: list[str] = []
        edits: list[tuple[int, int, str]] = []
        deferred: list[str] = []
        linked = False

        def write(address: str, image: bool) -> str | None:
            return self.address(address, own, _UP, listed, image)

        def in_style_code(address: str) -> bool:
            return self.held.folder.target(address, own) in self.held.style

        for spot in _spots(text):
            if spot.kind == _SHEET:
                if in_style_code(spot.value):
                    edits.append((spot.element, spot.remove_to, "" if linked else _STYLE_LINK))
                    linked = True
                    continue
                new = write(spot.value, _ELSEWHERE)
                if new is not None:
                    edits.append(_attribute_edit(text, spot, new))
            elif spot.kind == _SCRIPT:
                self._script(text, spot, own, edits, deferred, write)
            elif spot.tag == "style" and spot.kind == _CSS:
                new = _new_css(spot.value, write, in_style_code)
                if new is not None:
                    edits.append((spot.start, spot.end, new))
                    if not linked and any(
                            token.group("import") and in_style_code(_import_address(token))
                            for token in _CSS_TOKEN.finditer(spot.value)):
                        edits.append((spot.element, spot.element, _STYLE_LINK))
                        linked = True
            else:
                new = _new_value(spot, write)
                if new is not None:
                    edits.append((spot.start, spot.end, _quoted(new, spot.quote)))
        return _edited(text, edits), deferred, listed

    def _script(self, text: str, spot: _Spot, own: str, edits: list, deferred: list[str],
                write: Callable[[str, bool], str | None]) -> None:
        target = self.held.folder.target(spot.value, own)
        if target not in self.held.carried or spot.module:
            new = write(spot.value, _ELSEWHERE)
            if new is not None:
                edits.append(_attribute_edit(text, spot, new))
            return
        tag = text[spot.start:spot.src[0]] + text[spot.src[1]:spot.tag_end]
        inline = f"{tag}{self.held.text_of(target)}</script>"
        if spot.defer:
            deferred.append(inline)
            inline = ""
        edits.append((spot.element, spot.remove_to, inline))


def _quoted(value: str, quote_mark: str) -> str:
    return f"{quote_mark}{html.escape(value, quote=True)}{quote_mark}"


def _attribute_edit(text: str, spot: _Spot, new: str) -> tuple[int, int, str]:
    """An edit of the element's address attribute, where `spot` holds the whole
    element rather than the value."""
    tag = text[spot.start:spot.tag_end or spot.remove_to]
    for name, written, match in _attributes(tag):
        if name == spot.attribute and written is not None:
            at = spot.start + match.start(2)
            quote_mark = written[0] if written[0] in "'\"" else '"'
            return at, at + len(written), _quoted(new, quote_mark)
    return spot.start, spot.start, ""


def _edited(text: str, edits: list[tuple[int, int, str]]) -> str:
    """`text` with each edit made. One inside another goes with the outer."""
    out, pos = [], 0
    for start, end, new in sorted(edits, key=lambda edit: (edit[0], -edit[1])):
        if start < pos:
            continue
        out += (text[pos:start], new)
        pos = end
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------- the style code (§ 4.7) ----


def _style_code(held: _Read, writer: _Writer) -> tuple[str, list[str]]:
    """Every sheet joined, each once, its own `@import`s in its place and those
    leaving the folder at the top, where a browser reads them. What could not
    be carried comes back to list."""
    seen: set[str] = set()
    top: list[str] = []
    listed: list[str] = []
    up = "../" * builder.STYLE_CODE.count("/")

    def joined(path: str, condition: str) -> str:
        if path in seen:
            return ""
        seen.add(path)

        def write(address: str, image: bool) -> str | None:
            return writer.address(address, path, up, listed, image)

        def token(found: re.Match) -> str:
            if found.group("charset"):
                return ""
            if found.group("import"):
                return imported(found, write, condition, path)
            new = _url_written(found, write)
            return found.group(0) if new is None else new

        return _CSS_TOKEN.sub(token, held.text_of(path))

    def imported(found: re.Match, write, condition: str, own: str) -> str:
        address = _import_address(found)
        target = held.folder.target(address, own)
        its_own = found.group("condition").strip()
        both = " and ".join(part for part in (condition, its_own) if part)
        if target in held.style:
            return _wrapped(joined(target, both), its_own)
        new = write(address, False)
        rule = found.group("import").rstrip()[:-1].rstrip()
        if new is not None:
            rule = rule.replace(address, new, 1)
        if condition:
            rule = f"{rule} and {condition}" if its_own else f"{rule} {condition}"
        top.append(f"{rule};\n")
        return ""

    bodies = [_wrapped(joined(path, held.links[path]), held.links[path])
              for path in held.style if path in held.links]
    return "".join(top) + "\n".join(body for body in bodies if body), listed


def _wrapped(css: str, media: str) -> str:
    return f"@media {media} {{\n{css}\n}}\n" if media and css else css


# ---------------------------------------------------- the furniture (§ 4.8) ----


@dataclass(frozen=True)
class _Block:
    start: int
    end: int
    text: str                        # compared across pages: trimmed, current marks gone
    marked: bool                     # the marks were there


@dataclass(frozen=True)
class _Blocks:
    header: _Block | None
    footer: _Block | None
    nav: _Block | None


def _without_marks(block: str) -> tuple[str, bool]:
    """§ 4.8: `aria-current` and the class names `active`, `current` and
    `selected` removed, since they differ on every page."""
    edits: list[tuple[int, int, str]] = []
    for event in blocks._scan(block):
        if event.kind not in ("start", "startend"):
            continue
        for name, written, match in _attributes(block[event.start:event.end]):
            if name == "aria-current":
                edits.append((event.start + match.start(), event.start + match.end(), ""))
            elif name == "class" and written is not None:
                words = _unquoted(written)[0].split()
                kept = [word for word in words if word.casefold() not in _MENU_MARKS]
                if len(kept) == len(words):
                    continue
                replaced = f'class="{html.escape(" ".join(kept), quote=True)}"' if kept else ""
                start = event.start + (match.start(1) if kept else match.start())
                edits.append((start, event.start + match.end(), replaced))
    return _edited(block, edits).strip(), bool(edits)


def _block(text: str, events, first: int) -> _Block | None:
    closed = _closing(events, first)
    if closed is None:
        return None
    start, end = events[first].start, events[closed].end
    normal, marked = _without_marks(text[start:end])
    return _Block(start, end, normal, marked)


def _furniture_blocks(text: str) -> _Blocks:
    events = blocks._scan(text)
    header, footer, nav = None, None, None
    depth = 0
    for number, event in enumerate(events):
        if event.kind == "end" and event.tag in _NOT_FURNITURE_IN:
            depth = max(0, depth - 1)
        if event.kind != "start":
            continue
        ident = (dict(event.attrs).get("id") or "").strip().lower() if event.tag == "div" else ""
        if depth == 0 and header is None and (event.tag == "header" or ident == "header"):
            header = _block(text, events, number)
        if depth == 0 and (event.tag == "footer" or ident == "footer"):
            footer = _block(text, events, number) or footer
        if nav is None and (event.tag == "nav" or ident in _MENU_IDS) and (
                depth == 0 or (header is not None and header.start < event.start < header.end)):
            nav = _block(text, events, number)
        if event.tag in _NOT_FURNITURE_IN:
            depth += 1
    if nav is not None and footer is not None and footer.start < nav.start < footer.end:
        nav = None                   # the footer file carries it
    return _Blocks(header, footer, nav)


def _most_common(texts: list[str], total: int) -> str | None:
    """§ 4.8: the block most pages hold, where at least half hold it."""
    if not texts:
        return None
    text, count = Counter(texts).most_common(1)[0]
    return text if count * 2 >= total else None


def _marker(kind: str, page: str = "", nonav: bool = False) -> str:
    named = f' page="{page}"' if page else ""
    return f"<!-- {kind}:START{named}{' nonav' if nonav else ''} --><!-- {kind}:END -->"


def _data_nav(navigation: str, names: dict[str, str]) -> str:
    """§ 4.8: each link to a page gains `data-nav="<name>"`, which
    `builder._current` matches; `Home` for the front page."""
    fronts = {_page_place(name): (_HOME if name == _FRONT else name) for name in names.values()}

    def link(found: re.Match) -> str:
        tag = found.group(0)
        value = next((written for name, written, _match in _attributes(tag)
                      if name == "href" and written), None)
        if value is None:
            return tag
        address, _quote = _unquoted(value)
        place = re.split(r"[?#]", address.removeprefix(_UP), maxsplit=1)[0]
        nav = fronts.get(place) if address.startswith(_UP) else None
        if nav is None or re.search(r"\bdata-nav\s*=", tag, re.I):
            return tag
        return f'{tag[:2]} data-nav="{html.escape(nav, quote=True)}"{tag[2:]}'

    return re.sub(r"<a\b[^>]*>", link, navigation, flags=re.I)


def _side_of(header: _Block, nav: _Block, text: str) -> str | None:
    """Which side of the header the menu sits on, with only whitespace between
    them; None otherwise."""
    if not text[header.end:nav.start].strip() and header.end <= nav.start:
        return "after"
    if not text[nav.end:header.start].strip() and nav.end <= header.start:
        return "before"
    return None


@dataclass
class _Parting:
    """§ 4.8's outcome: what each furniture file holds, and what to list."""
    header: str
    footer: str
    navigation: str
    listed: list[Dropped]


@dataclass(frozen=True)
class _Shared:
    """Which blocks the pages share, and where the shared menu goes."""
    header: str | None
    footer: str | None
    nav: str | None
    inside: bool                     # the menu is inside the shared header
    side: str | None                 # or beside it, on this side
    alone: bool                      # or there is no shared header

    @property
    def menu_goes(self) -> bool:
        return self.inside or self.alone or self.side is not None


def _shared(texts: dict[str, str], found: dict[str, _Blocks]) -> _Shared:
    total = len(texts)
    header = _most_common([b.header.text for b in found.values() if b.header], total)
    footer = _most_common([b.footer.text for b in found.values() if b.footer], total)
    nav = _most_common([b.nav.text for b in found.values() if b.nav], total)
    inside = bool(header and nav and nav in header)
    side = None
    if header and nav and not inside:
        sides = {_side_of(b.header, b.nav, texts[path]) for path, b in found.items()
                 if b.header and b.nav and b.header.text == header and b.nav.text == nav}
        side = sides.pop() if len(sides) == 1 else None
    return _Shared(header, footer, nav, inside, side, bool(nav and not header))


def _header_file(shared: _Shared) -> str:
    if shared.alone:
        return _NAVIGATION
    if not shared.header:
        return starter.header()
    if shared.inside:
        return shared.header.replace(shared.nav, _NAVIGATION, 1)
    if shared.side == "after":
        return f"{shared.header}\n{_NAVIGATION}"
    if shared.side == "before":
        return f"{_NAVIGATION}\n{shared.header}"
    return shared.header


def _parted_page(text: str, here: _Blocks, shared: _Shared, page: str, where: str
                 ) -> tuple[str, list[Dropped], bool]:
    """A page with the blocks it shares replaced by marker pairs; with what to
    list of the ones it keeps, and whether a current-link mark went."""
    edits: list[tuple[int, int, str]] = []
    listed: list[Dropped] = []
    marked = False
    holds_header = bool(here.header and here.header.text == shared.header)
    holds_nav = bool(here.nav and here.nav.text == shared.nav)
    if holds_header and shared.side and holds_nav:
        marked = here.header.marked or here.nav.marked
        edits.append((min(here.header.start, here.nav.start),
                      max(here.header.end, here.nav.end), _marker("HEADER", page)))
    elif holds_header:
        marked = here.header.marked
        # A shared menu beside the header joins its pair, and this page has none.
        edits.append((here.header.start, here.header.end,
                      _marker("HEADER", page, nonav=bool(shared.side))))
    elif here.header:
        listed.append(Dropped(where, say("import.folder.own_header")))
    if shared.alone and holds_nav:
        marked = here.nav.marked
        edits.append((here.nav.start, here.nav.end, _marker("HEADER", page)))
    if here.nav and (not holds_nav or (shared.header and not holds_header)):
        listed.append(Dropped(where, say("import.folder.own_menu")))
    if here.footer and here.footer.text == shared.footer:
        edits.append((here.footer.start, here.footer.end, _marker("FOOTER")))
    elif here.footer:
        listed.append(Dropped(where, say("import.folder.own_footer")))
    return _edited(text, edits), listed, marked


def _sharing_said(shared: _Shared, navigation: str, marked: bool) -> list[Dropped]:
    """What § 4.8 lists of the site as a whole."""
    said: list[tuple[str, str]] = []
    if shared.menu_goes:
        try:
            menu.links(navigation)
        except menu.Unusual:
            said.append(("navigation", "import.folder.menu_unusual"))
        if marked:
            said.append(("navigation", "import.folder.current_marks"))
    elif shared.nav:
        said.append(("navigation", "import.folder.menu_stays"))
    else:
        said.append(("navigation", "import.folder.no_menu"))
    if not shared.header and not shared.menu_goes:
        said.append(("header", "import.folder.no_header"))
    if not shared.footer:
        said.append(("footer", "import.folder.no_footer"))
    return [Dropped(where, say(key)) for where, key in said]


def _part_out(texts: dict[str, str], names: dict[str, str]
              ) -> tuple[dict[str, str], _Parting]:
    """Each page with its shared blocks replaced by the Builder's marker pairs.
    `texts` holds addresses written with {{UP}}, so depth does not differ."""
    found = {path: _furniture_blocks(text) for path, text in texts.items()}
    shared = _shared(texts, found)
    pages: dict[str, str] = {}
    listed: list[Dropped] = []
    any_marked = False
    for path, text in texts.items():
        name = names[path]
        pages[path], said, marked = _parted_page(
            text, found[path], shared, _HOME if name == _FRONT else name,
            f"{store.PAGES_FOLDER}/{name}")
        listed += said
        any_marked = any_marked or marked
    navigation = _data_nav(shared.nav, names) if shared.menu_goes else starter.navigation()
    listed += _sharing_said(shared, navigation, any_marked)
    footer = shared.footer or starter.footer().rstrip()
    return pages, _Parting(f"{_header_file(shared)}\n", f"{footer}\n", navigation, listed)


# ------------------------------------------------- a page's shape (§ 4.9) ----


def _title_of(text: str, fallback: str) -> str:
    """A page's first `<h1>` as plain words, else `fallback`."""
    events = blocks._scan(text)
    for number, event in enumerate(events):
        if event.kind == "start" and event.tag == "h1":
            closed = _closing(events, number)
            if closed is not None:
                inner = text[event.end:events[closed].start]
                words = " ".join(html.unescape(_TAGS.sub("", inner)).split())
                if words:
                    return words
    return fallback


def _has_body(text: str) -> bool:
    return any(event.tag == "body" and event.kind == "start" for event in blocks._scan(text))


def _balanced(events) -> bool:
    """Whether a run of events could sit alone inside one new element: nothing
    in it closes what it did not open, or opens what must close outside it."""
    stack: list[str] = []
    for event in events:
        if event.kind == "start" and event.tag not in blocks._VOID:
            stack.append(event.tag)
        elif event.kind == "end":
            if event.tag not in stack:
                return False
            while stack.pop() != event.tag:
                pass
    return all(tag in _MAY_STAY_OPEN for tag in stack)


def _body_edges(text: str, events) -> tuple[int, int] | None:
    """Where a body's content starts and ends."""
    start = next((event.end for event in events
                  if event.kind == "start" and event.tag == "body"), None)
    if start is None:
        return None
    closes = [event.start for event in events
              if event.kind == "end" and event.tag in ("body", "html")]
    return start, min(closes) if closes else len(text)


def _with_main(text: str) -> tuple[str, bool]:
    """§ 4.9: where a page has no `<main>`, what lies between its header and its
    footer wrapped in one, shared or its own. False where a `<main>` there would
    cross another element's edges, as a page's whole must then stay as it is."""
    events = blocks._scan(text)
    if any(event.kind == "start" and event.tag == "main" for event in events):
        return text, True
    edges = _body_edges(text, events)
    if edges is None:
        return text, True
    start, end = edges
    for found in re.finditer(r"<!--\s*HEADER:END\s*-->", text):
        if start <= found.start() < end:
            start = found.end()
    for found in re.finditer(r"<!--\s*FOOTER:START[^>]*?-->", text):
        if start <= found.start() < end:
            end = found.start()
    own = _furniture_blocks(text)
    if own.header and own.header.end <= end:
        start = max(start, own.header.end)
    if own.footer and start <= own.footer.start:
        end = min(end, own.footer.start)
    if start >= end:
        return text, True
    inner = [event for event in events if start <= event.start < end]
    if not _balanced(inner):
        return text, False
    return f"{text[:start]}<main>{text[start:end]}</main>{text[end:]}", True


def _deferred_placed(text: str, deferred: list[str]) -> str:
    """§ 4.6: a `defer` script runs after the page, so it sits at the body's
    end, in its order."""
    if not deferred:
        return text
    edges = _body_edges(text, blocks._scan(text))
    at = edges[1] if edges else len(text)
    return text[:at] + "".join(deferred) + text[at:]


def _shaped(text: str, name: str, deferred: list[str], where: str, listed: list[Dropped]) -> str:
    """The page as it is written: {{UP}} filled, an area made where it can be."""
    front = name == _FRONT
    up = "" if front else "../"
    if not _has_body(text):
        title = _title_of(text, name)
        text = starter.new_page(_HOME if front else name, title, (builder.STYLE_CODE,),
                                main=text + "".join(deferred), root=front)
        return _adopted(text.replace(_UP, up), name)
    text, made = _with_main(text)
    if not made:
        listed.append(Dropped(where, say("import.folder.no_main")))
    text = _deferred_placed(text, deferred)
    return _adopted(text.replace(_UP, up), name)


def _adopted(text: str, name: str) -> str:
    try:
        return blocks.adopt(text, builder.furniture_spans(name, text)) or text
    except builder.BuildStopped:
        return text


# ---------------------------------------------------- the identity (§ 4.9) ----


def _identity(text: str) -> store.Identity | None:
    events = blocks._scan(text)
    title = ""
    for number, event in enumerate(events):
        if event.kind == "start" and event.tag == "title":
            closed = _closing(events, number)
            if closed is not None:
                title = html.unescape(text[event.end:events[closed].start])
            break
    description = next((dict(event.attrs).get("content") or "" for event in events
                        if event.tag == "meta" and event.kind in ("start", "startend")
                        and (dict(event.attrs).get("name") or "").casefold() == "description"),
                       "")
    identity = store.Identity(" ".join(title.split()), " ".join(description.split()))
    return None if store.identity_problem(identity) else identity


# ---------------------------------------------------- writing it (§ 4.9) ----


@dataclass
class _Written:
    """Everything `bring_in_folder` writes, worked out before any of it is."""
    pages: dict[str, str]            # name: text
    header: str
    footer: str
    navigation: str
    style_code: str
    forwards: dict[str, str]
    photographs: dict[str, str]      # path: Store name
    files: dict[str, str]
    identity: store.Identity | None
    report: Report
    roots: tuple[str, ...]


def _work_out(held: _Read, left: tuple[tuple[str, str], ...]) -> _Written:
    pages = list(held.pages)
    names, renamed, listed = _name_pages(pages)
    photographs, renamed_photographs = _name_held(held.photographs, store.photograph_path_for)
    files, renamed_files = _name_held(held.files, store.file_path_for)
    writer = _Writer(held, names, photographs, files)

    texts: dict[str, str] = {}
    deferred: dict[str, list[str]] = {}
    furniture_able: dict[str, str] = {}
    for path, (raw, older) in held.pages.items():
        where = f"{store.PAGES_FOLDER}/{names[path]}"
        text = _BUILDER_MARK.sub("", raw)
        if text != raw:
            listed.append(Dropped(where, say("import.folder.marks")))
        if older:
            text = _declares_utf8(text)
            listed.append(Dropped(where, say("import.folder.older")))
        if _holds_base(text):
            listed.append(Dropped(where, say("import.folder.base")))
            texts[path], deferred[path] = text, []
        else:
            written, deferred[path], said = writer.page(text, path)
            texts[path] = written
            listed += [Dropped(where, what) for what in dict.fromkeys(said)]
        if _has_body(texts[path]):
            furniture_able[path] = texts[path]

    style_code, said = _style_code(held, writer)
    listed += [Dropped(store.LOOK_FOLDER, what) for what in dict.fromkeys(said)]
    parted, parting = _part_out(furniture_able, names) if furniture_able else ({}, _Parting(
        starter.header(), starter.footer(), starter.navigation(), []))
    listed += parting.listed
    texts.update(parted)
    shaped = {names[path]: _shaped(text, names[path], deferred[path],
                                   f"{store.PAGES_FOLDER}/{names[path]}", listed)
              for path, text in texts.items()}

    for path in (*held.photographs, *held.files):
        if path not in writer.named:
            listed.append(Dropped(path, say("import.folder.unnamed")))

    forwards = {path: name for path, name in names.items() if path != _page_place(name)}
    front_path = next(path for path, name in names.items() if name == _FRONT)
    carried = [*held.pages, *held.photographs, *held.files, *held.carried, *held.style]
    roots = tuple(sorted({path.split("/")[0] for path in carried}))
    report = Report(
        published=0, drafts=0, comments=0, photographs=len(photographs), files=len(files),
        renamed_slugs=tuple(renamed), renamed_photographs=(*renamed_photographs, *renamed_files),
        pages=tuple(sorted(shaped)), dropped=tuple(dict.fromkeys(listed)),
        unfetched=(*left, *sorted(held.left.items())),
        moved=tuple(sorted(forwards.items())), inside_pages=tuple(sorted(held.carried)),
        sheets_for_some=tuple(path for path in held.style
                              if held.sheet_pages.get(path, set()) != set(held.pages)),
        folder=True)
    return _Written(shaped, parting.header, parting.footer, parting.navigation, style_code,
                    forwards, photographs, files, _identity(held.pages[front_path][0]), report,
                    roots)


def bring_in_folder(folder: Path, into: Path, *,
                    left: tuple[tuple[str, str], ...] = (),
                    commit: str = "") -> Brought:
    """§ 4.9: the whole or nothing, as PRESS-0125 § 4.7 writes an export. `left`
    is what `unpack_folder` left out; `commit`, the repository state read."""
    folder, into = Path(folder), Path(into)
    if store.holds_a_site(into):
        raise ImportStopped("this site already holds a site, and Import writes only "
                            "into an empty one")
    held = _read_folder(folder)
    if not held.pages:
        raise ImportStopped("the folder holds no page")
    written = _work_out(held, left)
    held_folder = into / IMPORT_FOLDER
    work = held_folder / _WORK
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    moved: list[tuple[Path, Path]] = []
    try:
        _write_all(work, into, folder, written, moved)
        brought = Brought(written.report, written.roots)
        with _writing("the record of what was brought in"):
            _write_brought(into, brought, commit)
    except BaseException:
        for source, target in reversed(moved):
            try:
                os.rename(target, source)
            except OSError:
                pass
        shutil.rmtree(work, ignore_errors=True)
        raise
    (held_folder / _MOVING).write_bytes(b"")
    stopped = finish(into)
    if stopped is not None:
        raise ImportStopped(stopped)
    return brought


def _write_all(work: Path, into: Path, folder: Path, written: _Written,
               moved: list[tuple[Path, Path]]) -> None:
    for name, text in written.pages.items():
        with _writing(f"the page {name}"):
            store.write_html(work, store.PAGES_FOLDER, name, text)
    for name, text in (("header", written.header), ("footer", written.footer),
                       ("navigation", written.navigation)):
        with _writing(f"the furniture file {name}"):
            store.write_html(work, store.FURNITURE_FOLDER, name, text)
    with _writing("the style code"):
        store.write_style_code(work, written.style_code)
    with _writing("the old addresses"):
        store.write_address_forwards(work, written.forwards)
    for kept, path_for in ((written.photographs, store.photograph_path_for),
                           (written.files, store.file_path_for)):
        for path, name in kept.items():
            with _writing(f"the file {path}"):
                target = path_for(work, name)
                target.parent.mkdir(exist_ok=True)
                os.rename(folder / path, target)
                moved.append((folder / path, target))
    with _writing("the templates"):
        templates.seed(work)
    with _writing("the journal switch"):
        store.write_journal(work, False)
    with _writing("the site's name"):
        if written.identity is not None and store.read_identity(into) is None:
            store.write_identity(work, written.identity)


# ------------------------------------------- what was brought in (§ 4.11) ----


def _write_brought(into: Path, brought: Brought, commit: str) -> None:
    record = {"commit": commit, "roots": list(brought.roots),
              "report": dataclasses.asdict(brought.report)}
    safe_write.write_whole(into / IMPORT_FOLDER / BROUGHT, json.dumps(record, indent=1) + "\n",
                           prefix=".brought-")


_REPORT_PAIRS = ("renamed_slugs", "renamed_photographs", "waiting", "unfetched", "other_types",
                 "moved")
_REPORT_NAMES = ("pages", "menus", "inside_pages", "sheets_for_some")


def read_brought(into: Path, commit: str) -> Brought | None:
    """What `bring_in_folder` recorded, where it read `commit`; else None."""
    try:
        record = json.loads((Path(into) / IMPORT_FOLDER / BROUGHT).read_text(encoding="utf-8"))
        if record["commit"] != commit:
            return None
        report = dict(record["report"])
        for name in _REPORT_PAIRS:
            report[name] = tuple(tuple(row) for row in report[name])
        for name in _REPORT_NAMES:
            report[name] = tuple(report[name])
        report["dropped"] = tuple(Dropped(**row) for row in report["dropped"])
        return Brought(Report(**report), tuple(record["roots"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
