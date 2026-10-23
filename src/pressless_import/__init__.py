"""Import — a WordPress site carried into Pressless's own files.

Two runs share this reading and converting. The maintainer's `run`
(PRESS-0007) turns the first writer's export, originals and live site into a
new folder, once. `bring_in` (PRESS-0125, in `_bring`) is the Import anyone
runs, which the Face's wizard (`pressless.importing`) starts on an empty
Store, and `fetch` is the one module that reaches the network, for it alone
(`docs/design.md` rule 9).

Both write through the Store's own calls and keep no copy of the Store's
rules: a value the Store refuses stops the import, and what it was filling
is removed, so the result appears whole or not at all.

The contracts are `docs/specs/PRESS-0007-import.md` and
`docs/specs/PRESS-0125-wordpress-import.md`; a bare section or INV-N
reference below is to PRESS-0007.
"""
from __future__ import annotations

import dataclasses
import difflib
import html
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable, Container, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from pressless import store
from pressless.marks import render
from pressless.paths import PREVIEW_ASSETS

from ._html import Lookup, autop, convert, is_markup, visible_lines, wordpress_markup

__all__ = [
    "IMPORT_FOLDER",
    "MEDIA_FOLDER",
    "Dropped",
    "Export",
    "ImportStopped",
    "Lookup",
    "Report",
    "autop",
    "bring_in",
    "convert",
    "finish",
    "is_markup",
    "main",
    "printable",
    "read",
    "resolve_slug",
    "run",
    "unpack_media",
    "visible_lines",
    "wordpress_markup",
]


@dataclass(frozen=True)
class Dropped:
    slug: str   # the entry it happened in, by its Store slug; or pages/<name>, or navigation
    what: str   # the construct, and where it matters the address


@dataclass(frozen=True)
class Report:
    published: int
    drafts: int
    comments: int
    photographs: int
    renamed_slugs: tuple[tuple[str, str], ...]        # (wanted, given)
    # (upload path, Store name): every attachment renamed, a file's as well
    # as a photograph's, though the field's name says photographs.
    renamed_photographs: tuple[tuple[str, str], ...]
    pages: tuple[str, ...]                            # the fixed pages carried, sorted
    dropped: tuple[Dropped, ...]
    # PRESS-0125 § 4.8.
    waiting: tuple[tuple[str, str], ...] = ()     # (slug, "" for review, else when scheduled)
    # (upload path, why it is not held); an attachment with no usable place
    # is keyed by its full address instead, as fetch.fetch_all keys it.
    unfetched: tuple[tuple[str, str], ...] = ()
    menus: tuple[str, ...] = ()                   # the menu carried first, then any other
    other_types: tuple[tuple[str, int], ...] = ()  # (post type not carried, how many)
    files: int = 0                                # kept in files/, not photographs


class ImportStopped(Exception):
    """INTO was not made. The message names a file by its own name or its
    upload path, and never by a full path (`docs/design.md` § Logging)."""


_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_RESIZED = re.compile(r"-\d+x\d+(?=\.[^./]+$)")
_GALLERY = re.compile(r"\[gallery\b[^\]]*\]")
_UPLOADS = "/uploads/"
# A Report reason _bring.bring_in matches to put the fetch's own reason in its
# place, so it is spelled once.
MISSING = "its original is missing"

# §4.9, matched as today's generator matches them.
_START = re.compile(r"<!--\s*(HEADER|FOOTER):START[^>]*?-->")
_ANY_END = re.compile(r"<!--\s*(?:HEADER|FOOTER):END\s*-->")
_STAMP = re.compile(r"""(["'](?:\.\./)*assets/[^"'\s?#]*)\?v=[0-9a-fA-F]+(?=["'])""")
_NAV = re.compile(r'[ \t]*<nav class="primary.*?</nav>\r?\n', re.S)


def resolve_slug(raw: str, post_id: str) -> str:
    """PRESS-0005 §3 decision 4's rule, re-homed from today's generator:
    decode percent-encoding, drop marks and control characters, fold to ASCII
    lower case, join the rest with hyphens -- and the post id where nothing
    survives (§4.4)."""
    text = unquote(raw or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf"))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or post_id


# -------------------------------------------------------- reading (§4.2) ----


@dataclass
class _Item:
    post_id: str
    rank: int          # decision 5: the live address first, then drafts, then pages
    draft: bool
    waiting: str | None  # PRESS-0157: "" for review, the scheduled date, or None
    wanted: str
    title: str
    date: datetime
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    body: str
    comments: tuple[store.Comment, ...]
    featured: str      # the featured image's attachment id, or ""
    page: bool
    slug: str = ""
    dropped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Export:
    """A read export: its channel and the namespaces to search it with."""
    channel: ET.Element
    ns: dict[str, str]


# Before the root element: space, the XML declaration, and comments.
_PROLOG = re.compile(rb"\s+|<\?.*?\?>|<!--.*?-->", re.S)


def _declares(data: bytes) -> bool:
    """PRESS-0125 § 4.3: whether the prolog holds anything but the root's own
    start -- a DOCTYPE or ENTITY declaration, which WordPress never writes,
    and which is how an XML file expands past its size. A file that does not
    begin with markup, as one not in UTF-8 does, counts too."""
    position = 3 if data.startswith(b"\xef\xbb\xbf") else 0
    while (found := _PROLOG.match(data, position)) and found.end() > position:
        position = found.end()
    return not data.startswith(b"<", position) or data.startswith(b"<!", position)


def read(export: Path) -> Export:
    """The export, refused before parsing where it declares anything
    (PRESS-0125 § 4.3)."""
    export = Path(export)
    try:
        data = export.read_bytes()
    except OSError as exc:
        raise ImportStopped(
            f"the export {export.name} cannot be read ({type(exc).__name__})") from None
    if _declares(data):
        raise ImportStopped(f"{export.name} is not a WordPress export Pressless can read")
    try:
        root = ET.fromstring(data)   # _declares refused every declaration first
    except ET.ParseError as exc:
        raise ImportStopped(
            f"the export {export.name} cannot be read ({type(exc).__name__})") from None
    # Read off the document, never pinned: WXR has shipped several.
    namespace = next(
        (element.tag[1:].split("}", 1)[0] for element in root.iter()
         if isinstance(element.tag, str)
         and element.tag.startswith("{http://wordpress.org/export/")),
        None,
    )
    channel = root.find("channel")
    if namespace is None or channel is None:
        raise ImportStopped(f"{export.name} is not a WordPress export")
    return Export(channel, {"wp": namespace,
                            "content": "http://purl.org/rss/1.0/modules/content/"})


def _field(element, name: str, ns) -> str:
    return (element.findtext(f"wp:{name}", "", ns) or "").strip()


def _upload_path(address: str) -> str | None:
    """An address's place under the uploads folder, decoded: `YYYY/MM/name`."""
    path = unquote(urlparse(address).path)
    index = path.find(_UPLOADS)
    return path[index + len(_UPLOADS):] if index >= 0 else None


def _wall_clock(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), _DATE_FORMAT)  # noqa: DTZ007 -- the export's wall clock
    except ValueError:
        return None


def _date(value: str, post_id: str) -> datetime:
    when = _wall_clock(value)
    if when is None:
        raise ImportStopped(f"post {post_id} carries a date the Store cannot hold")
    return when


def _comments(item, ns) -> tuple[tuple[store.Comment, ...], list[str]]:
    """§4.6: the comments today's site shows, and what was listed. The email
    and IP fields are never read, so no route can write them (PRESS-0006
    INV-4). A comment the Store could not hold is listed and skipped, and a
    reply whose parent is not carried goes to the top (PRESS-0158)."""
    carried: list[store.Comment] = []
    listed: list[str] = []
    for element in item.findall("wp:comment", ns):
        if _field(element, "comment_approved", ns) != "1":
            continue
        if _field(element, "comment_type", ns) not in ("", "comment"):
            continue
        identifier = _field(element, "comment_id", ns)
        when = _wall_clock(_field(element, "comment_date", ns))
        if not identifier:
            listed.append("a comment with no number, not brought in")
            continue
        if any(comment.identifier == identifier for comment in carried):
            listed.append(f"comment {identifier}, whose number another comment has, "
                          f"not brought in")
            continue
        if when is None:
            listed.append(f"comment {identifier}, whose date cannot be read, not brought in")
            continue
        parent = _field(element, "comment_parent", ns)
        carried.append(store.Comment(
            identifier=identifier,
            author=element.findtext("wp:comment_author", "", ns) or "",
            author_url=element.findtext("wp:comment_author_url", "", ns) or "",
            date=when,
            body=element.findtext("wp:comment_content", "", ns) or "",
            # The export's top level is 0; the Store's is "" (PRESS-0006 §4.2).
            parent="" if parent in ("", "0") else parent,
        ))
    held = {comment.identifier for comment in carried}
    for number, comment in enumerate(carried):
        if comment.parent and comment.parent not in held:
            listed.append(f"comment {comment.identifier} replied to one not brought in, "
                          f"so it now stands on its own")
            carried[number] = dataclasses.replace(comment, parent="")
    return tuple(carried), listed


# Decision 3 and PRESS-0157: how each status of a post arrives.
_DRAFT_STATUSES = ("draft", "private", "pending", "future")


def _items(channel, ns, *, page_statuses: Container[str] | None = None,
           titled_drafts: bool = False) -> list[_Item]:
    """Every carried post, and every page whose status is in `page_statuses`,
    or every page where that is None. With `titled_drafts`, a draft whose
    post_name resolves to nothing takes its title's slug before its post id:
    WordPress names a draft only when it is published (PRESS-0125 § 4.5)."""
    items = []
    for item in channel.findall("item"):
        kind, status = _field(item, "post_type", ns), _field(item, "status", ns)
        if kind == "post" and status == "publish":
            rank, draft = 0, False
        elif kind == "post" and status in _DRAFT_STATUSES:
            rank, draft = 1, True
        elif kind == "page" and (page_statuses is None or status in page_statuses):
            rank, draft = 2, True
        else:
            continue
        post_id = _field(item, "post_id", ns)
        title = (item.findtext("title") or "").strip()
        wanted = resolve_slug(_field(item, "post_name", ns), "")
        if not wanted and draft and titled_drafts:
            wanted = resolve_slug(title, "")
        meta = {_field(each, "meta_key", ns): _field(each, "meta_value", ns)
                for each in item.findall("wp:postmeta", ns)}
        date = _date(_field(item, "post_date", ns), post_id)
        waiting = {"pending": "", "future": date.strftime("%Y-%m-%d %H:%M")}.get(status)
        comments, listed = _comments(item, ns)
        categories, tags = [], []
        for term in item.findall("category"):
            nicename = term.get("nicename")
            if nicename and term.get("domain") == "category":
                categories.append(nicename)
            elif nicename and term.get("domain") == "post_tag":
                tags.append(nicename)
        items.append(_Item(
            post_id=post_id,
            rank=rank,
            draft=draft,
            waiting=waiting if kind == "post" else None,
            wanted=wanted or post_id,
            title=title,
            date=date,
            categories=tuple(categories),
            tags=tuple(tags),
            body=item.findtext("content:encoded", "", ns) or "",
            comments=comments,
            featured=meta.get("_thumbnail_id", ""),
            page=kind == "page",
            dropped=listed,
        ))
    return items


# ---------------------------------------------------------- slugs (§4.4) ----


def _refused(slug: str) -> bool:
    """The Store's own rule, asked rather than copied (§4.4)."""
    try:
        store.path_for(Path(), slug, draft=False)
    except store.StoreError:
        return True
    return False


def _resolve(items: list[_Item]) -> list[tuple[str, str]]:
    """Decision 5, before anything is written: the item with the live address
    keeps a contested slug, and each loser takes `<slug>-<post id>`."""
    renamed = []
    taken = set()
    by_slug: dict[str, list[_Item]] = {}
    for item in items:
        by_slug.setdefault(item.wanted, []).append(item)
    losers = []
    for slug, wanting in by_slug.items():
        ranked = sorted(wanting, key=lambda item: item.rank)
        if _refused(slug):
            losers.extend(ranked)
            continue
        ranked[0].slug = slug
        taken.add(slug)
        losers.extend(ranked[1:])
    for item in losers:
        given = f"{item.wanted}-{item.post_id}"
        if given in taken or _refused(given):
            raise ImportStopped(f"post {item.post_id} has no slug left to take: {given}")
        item.slug = given
        taken.add(given)
        renamed.append((item.wanted, given))
    return renamed


# ---------------------------------------------------- photographs (§4.5) ----


def _place(item, ns) -> str:
    """An attachment's upload path, or why it has none Import may use."""
    post_id = _field(item, "post_id", ns)
    upload_path = _upload_path(_field(item, "attachment_url", ns))
    if not upload_path:
        raise ImportStopped(f"attachment {post_id} names no place in the uploads folder")
    if upload_path.startswith("/") or ".." in PurePosixPath(upload_path).parts:
        # Joined onto a folder and copied into the Store: an absolute path
        # replaces the folder outright, and `..` climbs out of it (PRESS-0135).
        raise ImportStopped(f"attachment {post_id}'s address leaves the uploads folder")
    try:
        # Each part one name a Windows folder keeps too, as the Store asks of
        # a photograph's: a decoded backslash is a separator there.
        for part in upload_path.split("/"):
            store.photograph_path_for(Path(), part)
    except store.StoreError:
        raise ImportStopped(f"attachment {post_id}'s address names no place a folder "
                            f"can hold") from None
    return upload_path


def _photographs(channel, ns, originals: Path, *, strict: bool = True,
                 shown: Callable[[Path], bool] | None = None):
    """Every attachment -- a file as well as a photograph, whatever the
    name says -- whose original is in `originals`, by its upload path,
    with its Store name; the two lookups, answering for those `shown` admits
    (all, where none is given); and each attachment not held, with why. A
    name two attachments share, compared without regard to case, takes its
    upload month in front (decision 6). Where not `strict`, an attachment
    with no usable place, or a name the Store refuses, is listed rather than
    stopping Import (PRESS-0125 § 4.4)."""
    attachments, unheld = [], []
    for item in channel.findall("item"):
        if _field(item, "post_type", ns) != "attachment":
            continue
        try:
            attachments.append((_field(item, "post_id", ns), _place(item, ns)))
        except ImportStopped as exc:
            if strict:
                raise
            unheld.append((_field(item, "attachment_url", ns), str(exc)))
    shared: dict[str, set[str]] = {}
    for _post_id, upload_path in attachments:
        shared.setdefault(upload_path.rsplit("/", 1)[-1].casefold(), set()).add(upload_path)
    names: dict[str, str] = {}
    by_id_path: dict[str, str] = {}
    taken: dict[str, str] = {}
    for post_id, upload_path in attachments:
        own = upload_path.rsplit("/", 1)[-1]
        name = own if len(shared[own.casefold()]) == 1 else upload_path.replace("/", "-")
        # The renamed names too, as Windows compares them: 2019/05/IMG.jpg and
        # 2019/05/img.jpg become two names one Windows folder cannot hold
        # (decision 6, PRESS-0162).
        other = taken.setdefault(name.casefold(), upload_path)
        if other != upload_path:
            raise ImportStopped(f"{other} and {upload_path} would take names that differ "
                                f"only in case")
        try:
            store.photograph_path_for(Path(), name)
        except store.StoreError:
            if strict:
                raise ImportStopped(f"{upload_path} has no name the Store can hold") from None
            unheld.append((upload_path, "it has no name the Store can hold"))
            continue
        if not (originals / upload_path).is_file():
            # PRESS-0158: listed, and its pictures take the no-attachment path.
            unheld.append((upload_path, MISSING))
            continue
        names[upload_path] = name
        by_id_path[post_id] = upload_path
    pictures = {upload_path: name for upload_path, name in names.items()
                if shown is None or shown(originals / upload_path)}

    def by_address(address: str) -> str | None:
        upload_path = _upload_path(address)
        if upload_path is None:
            return None
        return pictures.get(upload_path) or pictures.get(_RESIZED.sub("", upload_path))

    def by_id(post_id: str) -> str | None:
        return pictures.get(by_id_path.get(post_id, ""))

    return names, by_address, by_id, unheld


# ------------------------------------------------------- the self-check ----


def _made_by_deleting_stars(source: str, rendered: str) -> bool:
    position = 0
    for character in source:
        if position < len(rendered) and character == rendered[position]:
            position += 1
        elif character != "*":
            return False
    return position == len(rendered)


def _differences(body: str, text: str) -> list[str]:
    """§4.3: the lines a reader sees, before and after, and every difference
    listed -- the three the check allows named as such."""
    before = visible_lines(body)
    after = visible_lines(render(text, lambda name: name))
    addresses = html.unescape(body)
    found = []
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed, added = list(before[i1:i2]), list(after[j1:j2])
        if any(_GALLERY.fullmatch(line) for line in removed):
            found.append("a gallery, now shown as its pictures")
            removed = [line for line in removed if not _GALLERY.fullmatch(line)]
        gained = [line for line in added
                  if line.startswith(("http://", "https://")) and line in addresses]
        if gained:
            found.append("an address, now a link")
            added = [line for line in added if line not in gained]
        if len(removed) == len(added) and all(
            _made_by_deleting_stars(s, r) for s, r in zip(removed, added, strict=True)
        ):
            if removed:
                found.append("words between asterisks, now shown in bold or italic")
            continue
        found.append(f"line {i1 + 1} of it changed on the way in: check it reads as it should")
    return found


def _convert(item: _Item, markup: Callable[[str], bool], by_address: Lookup,
             by_id: Lookup, old_site: str) -> str:
    """One body in marks, what it dropped and every difference the self-check
    found listed on the item. A body `markup` rejects is compared as `autop`
    gives it, since that is what a reader saw (PRESS-0125 § 4.5)."""
    source = item.body if markup(item.body) else autop(item.body)
    try:
        text, whats = convert(source, by_address, by_id, old_site=old_site)
        differences = _differences(source, text)
    except RecursionError:
        # Every unclosed tag nests the next, and the tree is walked
        # recursively (PRESS-0135).
        raise ImportStopped(
            f"post {item.post_id}'s body is nested too deeply to convert") from None
    item.dropped.extend(whats)
    item.dropped.extend(differences)
    return text


# ------------------------------------ fixed pages and furniture (§4.9) ----


def _read_text(path: Path, shown: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except OSError as exc:
        raise ImportStopped(
            f"{shown} could not be read: {exc.strerror or type(exc).__name__}") from None
    except UnicodeDecodeError:
        raise ImportStopped(f"{shown} is not UTF-8") from None


def _empty_markers(text: str, shown: str) -> str:
    """Each marker pair emptied: what lies between a START's `-->` and the
    next END of its kind becomes a newline and the spaces and tabs in front of
    that END. Both comments stay as written."""
    out, pos = [], 0
    while True:
        start = _START.search(text, pos)
        before = start.start() if start else len(text)
        if _ANY_END.search(text, pos, before):
            raise ImportStopped(f"{shown} has a marker END with no START before it")
        if start is None:
            out.append(text[pos:])
            return "".join(out)
        kind = start.group(1)
        end = re.compile(rf"<!--\s*{kind}:END\s*-->").search(text, start.end())
        if end is None:
            raise ImportStopped(f"{shown} has a {kind}:START with no {kind}:END after it")
        between = text[start.end():end.start()]
        indent = re.search(r"[ \t]*\Z", between).group(0)
        out.append(text[pos:start.end()] + "\n" + indent + end.group(0))
        pos = end.end()


def _fixed_pages(live_site: Path) -> dict[str, str]:
    """index.html as `index` and each pages/<name>.html as `<name>`, markers
    emptied and stamps removed. Anything else under pages/ stops Import: pages
    is the Builder's, so the first publish would not keep it."""
    index = live_site / "index.html"
    if not index.is_file():
        raise ImportStopped("the live site's folder holds no index.html")
    if not (live_site / "assets").is_dir():
        raise ImportStopped("the live site's folder holds no assets folder")
    found = {"index": index}
    pages = live_site / "pages"
    if pages.is_dir():
        for path in sorted(pages.rglob("*")):
            if path.is_dir():
                continue
            shown = path.relative_to(live_site).as_posix()
            if path.parent != pages or path.suffix != store.HTML_SUFFIX:
                raise ImportStopped(
                    f"{shown} is not a fixed page, and the first publish would not keep it")
            if path.stem in found:
                raise ImportStopped(f"{shown} would take the name {path.stem} twice")
            found[path.stem] = path
    return {
        name: _STAMP.sub(r"\1", _empty_markers(
            _read_text(path, path.relative_to(live_site).as_posix()),
            path.relative_to(live_site).as_posix()))
        for name, path in found.items()
    }


def _furniture(templates: Path) -> dict[str, str]:
    """The footer as it is, and the header with its navigation cut out into
    `navigation`, a line of `{{NAVIGATION}}` standing in for it."""
    texts = {}
    for name in ("header", "footer"):
        path = templates / f"{name}{store.HTML_SUFFIX}"
        if not path.is_file():
            raise ImportStopped(f"the templates folder holds no {path.name}")
        texts[name] = _read_text(path, path.name)
    navs = list(_NAV.finditer(texts["header"]))
    if len(navs) != 1:
        raise ImportStopped(
            f"header.html holds {'no' if not navs else 'more than one'} navigation element")
    nav = navs[0]
    header = texts["header"]
    # The file's own line ending, so a header saved with CRLF is not refused
    # as holding no navigation (PRESS-0162).
    ending = "\r\n" if nav.group(0).endswith("\r\n") else "\n"
    return {
        "header": header[:nav.start()] + "{{NAVIGATION}}" + ending + header[nav.end():],
        "navigation": nav.group(0)[:-len(ending)],
        "footer": texts["footer"],
    }


# ------------------------------------------------------------- the run ----


def _old_site(channel, ns) -> str:
    base = (_field(channel, "base_blog_url", ns) or _field(channel, "base_site_url", ns)
            or (channel.findtext("link") or "").strip())
    return urlparse(base).netloc


@contextmanager
def _writing(what: str) -> Iterator[None]:
    """§4.7: a write the Store refuses, or the drive fails, stops the import
    with a message naming `what` was being written."""
    try:
        yield
    except store.StoreError as exc:
        raise ImportStopped(f"the Store refused {what}: {exc}") from None
    except OSError as exc:
        raise ImportStopped(
            f"{what} could not be written: {exc.strerror or type(exc).__name__}") from None


def _entry(item: _Item, body: str) -> store.Entry:
    return store.Entry(slug=item.slug, title=item.title, date=item.date,
                       categories=item.categories, tags=item.tags, body=body, extra=())


def _write_entries(work: Path, items: list[_Item], entries: dict[str, store.Entry]) -> None:
    """Each item's entry, as a draft where it is one, and its comments."""
    for item in items:
        with _writing(f"the entry {item.slug}"):
            store.write(work, entries[item.post_id], draft=item.draft)
        if item.comments:
            with _writing(f"the comments on {item.slug}"):
                store.write_comments(work, item.slug, item.comments)


def _counts(items: list[_Item]) -> dict[str, int]:
    """The Report's published, drafts and comments."""
    return {"published": sum(1 for item in items if not item.draft),
            "drafts": sum(1 for item in items if item.draft),
            "comments": sum(len(item.comments) for item in items)}


def run(export: Path, originals: Path, live_site: Path, templates: Path,
        into: Path) -> Report:
    """§4.7, in order: refuse an INTO that exists; read the export and resolve
    every slug; trace every picture and check every original, and read the
    fixed pages and templates (§4.9); convert every markup body; write it all
    into a new folder beside INTO; and rename that folder to INTO only once
    every write has succeeded."""
    export, originals, into = Path(export), Path(originals), Path(into)
    live_site, templates = Path(live_site), Path(templates)
    if into.exists() or into.is_symlink():
        raise ImportStopped(f"{into.name} already exists, and Import only makes a new folder")

    read_in = read(export)
    channel, ns = read_in.channel, read_in.ns
    items = _items(channel, ns)
    renamed_slugs = _resolve(items)
    names, by_address, by_id, unfetched = _photographs(channel, ns, originals)
    old_site = _old_site(channel, ns)
    pages = _fixed_pages(live_site)
    furniture = _furniture(templates)

    bodies = {}
    for item in items:
        if is_markup(item.body):
            bodies[item.post_id] = _convert(item, is_markup, by_address, by_id, old_site)
        else:
            if _GALLERY.search(item.body):
                item.dropped.append("a gallery, kept as the words WordPress wrote")
            bodies[item.post_id] = item.body

    if not into.parent.is_dir():
        raise ImportStopped(f"the folder {into.name} would sit in does not exist")
    work = Path(tempfile.mkdtemp(dir=into.parent, prefix=f".{into.name}-"))
    try:
        _write_entries(work, items, {item.post_id: _entry(item, bodies[item.post_id])
                                     for item in items})
        for upload_path, name in names.items():
            with _writing(f"the photograph {upload_path}"):
                target = store.photograph_path_for(work, name)
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(originals / upload_path, target)
        for kind, texts in ((store.PAGES_FOLDER, pages), (store.FURNITURE_FOLDER, furniture)):
            for name, text in texts.items():
                with _writing(f"the {kind} file {name}"):
                    store.write_html(work, kind, name, text)
        # Decision 12: the preview copy, byte for byte. The Face serves it and
        # never publishes it.
        with _writing("the preview copy of assets"):
            shutil.copytree(live_site / "assets", work / PREVIEW_ASSETS)
        with _writing(f"the folder {into.name}"):
            if into.exists():
                raise ImportStopped(f"{into.name} appeared while Import was writing")
            os.rename(work, into)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise

    return Report(
        **_counts(items),
        photographs=len(names),
        renamed_slugs=tuple(renamed_slugs),
        pages=tuple(sorted(pages)),
        renamed_photographs=tuple(
            (upload_path, name) for upload_path, name in names.items()
            if name != upload_path.rsplit("/", 1)[-1]
        ),
        dropped=tuple(
            Dropped(item.slug, what) for item in items for what in dict.fromkeys(item.dropped)
        ),
        waiting=_waiting(items),
        unfetched=tuple(unfetched),
    )


def _waiting(items: list[_Item]) -> tuple[tuple[str, str], ...]:
    return tuple((item.slug, item.waiting) for item in items if item.waiting is not None)


def _describe(report: Report, into: str) -> str:
    lines = [
        f"Import made {into}: {report.published} published, {report.drafts} drafts, "
        f"{report.comments} comments, {report.photographs} photographs."
    ]
    lines.append(f"Fixed pages carried: {', '.join(report.pages)}.")
    if report.renamed_slugs:
        lines.append("Slugs renamed, the live address keeping its own:")
        lines.extend(f"  {wanted} -> {given}" for wanted, given in report.renamed_slugs)
    if report.renamed_photographs:
        lines.append("Photographs renamed, a shared name taking its upload month:")
        lines.extend(f"  {path} -> {name}" for path, name in report.renamed_photographs)
    if report.waiting:
        lines.append("Arrived as drafts, having waited to be published:")
        lines.extend(f"  {slug}: scheduled for {when}" if when else f"  {slug}: waiting for review"
                     for slug, when in report.waiting)
    if report.unfetched:
        lines.append("Attachments not carried, so their pictures stay links:")
        lines.extend(f"  {path}: {why}" for path, why in report.unfetched)
    if report.dropped:
        lines.append("Not carried as written -- read these before handing the folder over:")
        lines.extend(f"  {d.slug}: {d.what}" for d in report.dropped)
    return "\n".join(printable(line) for line in lines)


def printable(text: str) -> str:
    """`text` with every control and format character escaped. Alt text,
    addresses and upload paths come from the export, and one carrying ESC or a
    direction override could rewrite the report on the terminal (PRESS-0135)."""
    return "".join(
        ch.encode("unicode_escape").decode("ascii")
        if unicodedata.category(ch) in ("Cc", "Cf") else ch
        for ch in text)


def main(argv: list[str]) -> int:
    """python -m pressless_import EXPORT ORIGINALS LIVE_SITE TEMPLATES INTO:
    prints the report and exits 0, or prints why it stopped and exits 1."""
    if len(argv) != 5:
        print("usage: python -m pressless_import EXPORT ORIGINALS LIVE_SITE TEMPLATES INTO",
              file=sys.stderr)
        return 1
    try:
        report = run(*(Path(arg) for arg in argv))
    except ImportStopped as exc:
        print(f"Import stopped: {printable(str(exc))}", file=sys.stderr)
        return 1
    print(_describe(report, Path(argv[4]).name))
    return 0


# The Import anyone runs (PRESS-0125) builds on everything above, so it is
# imported last.
from ._bring import IMPORT_FOLDER, MEDIA_FOLDER, bring_in, finish, unpack_media  # noqa: E402
