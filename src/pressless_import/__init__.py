"""Import — twelve years carried across, once, with nothing lost (PRESS-0007).

The maintainer runs it once, on the machine holding the WordPress export and
the photograph originals, and hands the writer the folder it made
(`docs/design.md` rule 9). Nothing in Pressless imports this package, so it
can be deleted without changing what anything else does, and the packaged
program does not carry it.

It writes through the Store's own calls and keeps no copy of the Store's
rules: a value the Store refuses stops the import, and the folder it was
filling is removed, so INTO appears whole or not at all (§4.7).

The contract is `docs/specs/PRESS-0007-import.md`; the section and INV-N
references below are to it.
"""
from __future__ import annotations

import difflib
import html
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from pressless import store
from pressless.marks import render

from ._html import Lookup, convert, is_markup, visible_lines

__all__ = [
    "Dropped",
    "ImportStopped",
    "Lookup",
    "Report",
    "convert",
    "is_markup",
    "main",
    "resolve_slug",
    "run",
    "visible_lines",
]


@dataclass(frozen=True)
class Dropped:
    slug: str   # the entry it happened in, by its Store slug
    what: str   # the construct, and where it matters the address


@dataclass(frozen=True)
class Report:
    published: int
    drafts: int
    comments: int
    photographs: int
    renamed_slugs: tuple[tuple[str, str], ...]        # (wanted, given)
    renamed_photographs: tuple[tuple[str, str], ...]  # (upload path, Store name)
    dropped: tuple[Dropped, ...]


class ImportStopped(Exception):
    """INTO was not made. The message names a file by its own name or its
    upload path, and never by a full path (`docs/design.md` § Logging)."""


_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_RESIZED = re.compile(r"-\d+x\d+(?=\.[^./]+$)")
_GALLERY = re.compile(r"\[gallery\b[^\]]*\]")
_UPLOADS = "/uploads/"


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
    wanted: str
    title: str
    date: datetime
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    body: str
    comments: tuple[store.Comment, ...]
    slug: str = ""
    dropped: list[str] = field(default_factory=list)


def _read(export: Path):
    try:
        root = ET.parse(export).getroot()
    except (OSError, ET.ParseError) as exc:
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
    return channel, {"wp": namespace, "content": "http://purl.org/rss/1.0/modules/content/"}


def _field(element, name: str, ns) -> str:
    return (element.findtext(f"wp:{name}", "", ns) or "").strip()


def _upload_path(address: str) -> str | None:
    """An address's place under the uploads folder, decoded: `YYYY/MM/name`."""
    path = unquote(urlparse(address).path)
    index = path.find(_UPLOADS)
    return path[index + len(_UPLOADS):] if index >= 0 else None


def _date(value: str, post_id: str) -> datetime:
    try:
        return datetime.strptime(value.strip(), _DATE_FORMAT)  # noqa: DTZ007 -- the export's wall clock
    except ValueError:
        raise ImportStopped(f"post {post_id} carries a date the Store cannot hold") from None


def _comments(item, ns, post_id: str) -> tuple[store.Comment, ...]:
    """§4.6: the comments today's site shows. The email and IP fields are
    never read, so no route can write them (PRESS-0006 INV-4)."""
    carried = []
    for element in item.findall("wp:comment", ns):
        if _field(element, "comment_approved", ns) != "1":
            continue
        if _field(element, "comment_type", ns) not in ("", "comment"):
            continue
        parent = _field(element, "comment_parent", ns)
        carried.append(store.Comment(
            identifier=_field(element, "comment_id", ns),
            author=element.findtext("wp:comment_author", "", ns) or "",
            author_url=element.findtext("wp:comment_author_url", "", ns) or "",
            date=_date(_field(element, "comment_date", ns), post_id),
            body=element.findtext("wp:comment_content", "", ns) or "",
            # The export's top level is 0; the Store's is "" (PRESS-0006 §4.2).
            parent="" if parent in ("", "0") else parent,
        ))
    return tuple(carried)


def _items(channel, ns) -> list[_Item]:
    items = []
    for item in channel.findall("item"):
        kind, status = _field(item, "post_type", ns), _field(item, "status", ns)
        if kind == "post" and status == "publish":
            rank, draft = 0, False
        elif kind == "post" and status in ("draft", "private"):
            rank, draft = 1, True
        elif kind == "page":
            rank, draft = 2, True
        else:
            continue
        post_id = _field(item, "post_id", ns)
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
            wanted=resolve_slug(_field(item, "post_name", ns), post_id),
            title=(item.findtext("title") or "").strip(),
            date=_date(_field(item, "post_date", ns), post_id),
            categories=tuple(categories),
            tags=tuple(tags),
            body=item.findtext("content:encoded", "", ns) or "",
            comments=_comments(item, ns, post_id),
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


def _photographs(channel, ns, originals: Path):
    """Every attachment's Store name and original. A name two attachments
    share, compared without regard to case, takes its upload month in front
    (decision 6)."""
    attachments = []
    for item in channel.findall("item"):
        if _field(item, "post_type", ns) != "attachment":
            continue
        post_id = _field(item, "post_id", ns)
        upload_path = _upload_path(_field(item, "attachment_url", ns))
        if not upload_path:
            raise ImportStopped(f"attachment {post_id} names no place in the uploads folder")
        attachments.append((post_id, upload_path))
    shared: dict[str, set[str]] = {}
    for _post_id, upload_path in attachments:
        shared.setdefault(upload_path.rsplit("/", 1)[-1].casefold(), set()).add(upload_path)
    names: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for post_id, upload_path in attachments:
        own = upload_path.rsplit("/", 1)[-1]
        name = own if len(shared[own.casefold()]) == 1 else upload_path.replace("/", "-")
        try:
            store.photograph_path_for(Path(), name)
        except store.StoreError:
            raise ImportStopped(f"{upload_path} has no name the Store can hold") from None
        if not (originals / upload_path).is_file():
            raise ImportStopped(f"the original of {upload_path} is missing")
        names[upload_path] = name
        by_id[post_id] = name

    def by_address(address: str) -> str | None:
        upload_path = _upload_path(address)
        if upload_path is None:
            return None
        return names.get(upload_path) or names.get(_RESIZED.sub("", upload_path))

    return names, by_address, by_id.get


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
            found.append("a gallery shortcode's text became its pictures")
            removed = [line for line in removed if not _GALLERY.fullmatch(line)]
        gained = [line for line in added
                  if line.startswith(("http://", "https://")) and line in addresses]
        if gained:
            found.append("an address became a link's words")
            added = [line for line in added if line not in gained]
        if len(removed) == len(added) and all(
            _made_by_deleting_stars(s, r) for s, r in zip(removed, added, strict=True)
        ):
            if removed:
                found.append("a pair of his asterisks, styled by Marks")
            continue
        found.append(f"a line a reader sees changed in conversion, at visible line {i1 + 1}")
    return found


# ------------------------------------------------------------- the run ----


def _old_site(channel, ns) -> str:
    base = (_field(channel, "base_blog_url", ns) or _field(channel, "base_site_url", ns)
            or (channel.findtext("link") or "").strip())
    return urlparse(base).netloc


def run(export: Path, originals: Path, into: Path) -> Report:
    """§4.7, in order: refuse an INTO that exists; read the export and resolve
    every slug; trace every picture and check every original; convert every
    markup body; write it all into a new folder beside INTO; and rename that
    folder to INTO only once every write has succeeded."""
    export, originals, into = Path(export), Path(originals), Path(into)
    if into.exists() or into.is_symlink():
        raise ImportStopped(f"{into.name} already exists, and Import only makes a new folder")

    channel, ns = _read(export)
    items = _items(channel, ns)
    renamed_slugs = _resolve(items)
    names, by_address, by_id = _photographs(channel, ns, originals)
    old_site = _old_site(channel, ns)

    bodies = {}
    for item in items:
        if is_markup(item.body):
            text, whats = convert(item.body, by_address, by_id, old_site=old_site)
            item.dropped.extend(whats)
            item.dropped.extend(_differences(item.body, text))
            bodies[item.post_id] = text
        else:
            if _GALLERY.search(item.body):
                item.dropped.append("a [gallery] shortcode, kept as written")
            bodies[item.post_id] = item.body

    if not into.parent.is_dir():
        raise ImportStopped(f"the folder {into.name} would sit in does not exist")
    work = Path(tempfile.mkdtemp(dir=into.parent, prefix=f".{into.name}-"))
    doing = "the folder"
    try:
        for item in items:
            doing = f"the entry {item.slug}"
            store.write(work, store.Entry(
                slug=item.slug, title=item.title, date=item.date,
                categories=item.categories, tags=item.tags,
                body=bodies[item.post_id], extra=(),
            ), draft=item.draft)
            if item.comments:
                doing = f"the comments on {item.slug}"
                store.write_comments(work, item.slug, item.comments)
        for upload_path, name in names.items():
            doing = f"the photograph {upload_path}"
            target = store.photograph_path_for(work, name)
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(originals / upload_path, target)
        doing = f"the folder {into.name}"
        if into.exists():
            raise ImportStopped(f"{into.name} appeared while Import was writing")
        os.rename(work, into)
    except BaseException as exc:
        shutil.rmtree(work, ignore_errors=True)
        if isinstance(exc, ImportStopped):
            raise
        if isinstance(exc, store.StoreError):
            raise ImportStopped(f"the Store refused {doing}: {exc}") from None
        if isinstance(exc, OSError):
            raise ImportStopped(
                f"{doing} could not be written: {exc.strerror or type(exc).__name__}") from None
        raise

    return Report(
        published=sum(1 for item in items if not item.draft),
        drafts=sum(1 for item in items if item.draft),
        comments=sum(len(item.comments) for item in items),
        photographs=len(names),
        renamed_slugs=tuple(renamed_slugs),
        renamed_photographs=tuple(
            (upload_path, name) for upload_path, name in names.items()
            if name != upload_path.rsplit("/", 1)[-1]
        ),
        dropped=tuple(
            Dropped(item.slug, what) for item in items for what in dict.fromkeys(item.dropped)
        ),
    )


def _describe(report: Report, into: str) -> str:
    lines = [
        f"Import made {into}: {report.published} published, {report.drafts} drafts, "
        f"{report.comments} comments, {report.photographs} photographs."
    ]
    if report.renamed_slugs:
        lines.append("Slugs renamed, the live address keeping its own:")
        lines.extend(f"  {wanted} -> {given}" for wanted, given in report.renamed_slugs)
    if report.renamed_photographs:
        lines.append("Photographs renamed, a shared name taking its upload month:")
        lines.extend(f"  {path} -> {name}" for path, name in report.renamed_photographs)
    if report.dropped:
        lines.append("Not carried as written -- read these before handing the folder over:")
        lines.extend(f"  {d.slug}: {d.what}" for d in report.dropped)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """python -m pressless_import EXPORT ORIGINALS INTO: prints the report and
    exits 0, or prints why it stopped and exits 1."""
    if len(argv) != 3:
        print("usage: python -m pressless_import EXPORT ORIGINALS INTO", file=sys.stderr)
        return 1
    try:
        report = run(Path(argv[0]), Path(argv[1]), Path(argv[2]))
    except ImportStopped as exc:
        print(f"Import stopped: {exc}", file=sys.stderr)
        return 1
    print(_describe(report, Path(argv[2]).name))
    return 0
