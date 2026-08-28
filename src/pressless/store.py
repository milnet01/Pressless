"""The Store — one file per entry, drafts kept apart from published.

The contract is docs/specs/PRESS-0005-store.md. The Store is handed its
folder and never derives one (§3 decision 1), exactly as Settings is. It
never produces HTML, never reaches the network, and never opens the site
folder (§4.6) — so it imports neither `pressless.marks` nor any network
module (INV-1).

Every read and write names UTF-8 and LF explicitly. Python's default text
encoding is the locale's — cp1252 on Windows — and its default newline is
the platform's, so an unnamed write would produce CRLF in cp1252 there. A
changed line ending is a changed file to git, and every publish would then
look as though it had touched the whole site (§4.2).
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    slug: str                            # the address's last segment; never empty
    title: str                           # may be empty -- many entries have none
    date: datetime                       # date and time; ordering needs the time
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    body: str                            # verbatim, every newline a line break
    extra: tuple[tuple[str, str], ...]   # unrecognised header fields, in file order


# The five §4.2 recognises, in the order §4.5 writes them. INV-8 locks the
# set: a sixth changes a file format three other items bind to.
RECOGNISED_FIELDS = ("Title", "Slug", "Date", "Categories", "Tags")
LIST_SEPARATOR = ", "
FILE_SUFFIX = ".txt"
PUBLISHED_FOLDER = "published"
DRAFTS_FOLDER = "drafts"

_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# §4.2: what safe_slug already yields, so every live address satisfies it.
# Pinned because the slug becomes a file name -- unpinned it admits "/", "\"
# and "..", which write outside the handed folder, and admits two slugs
# differing only in case, which are one file on Windows and two on Linux.
_LEGAL_SLUG = re.compile(r"\A[a-z0-9-]+\Z")


class StoreError(Exception):
    """A file or a value the Store will not act on."""


class EntryNotFound(StoreError):
    """No entry at that path, or no folder to look in."""


class SlugInUse(StoreError):
    """The destination already holds that slug; nothing was moved."""


def path_for(folder: Path, slug: str, *, draft: bool) -> Path:
    """Where the entry at `slug` sits, published or draft.

    The slug is checked here rather than in each caller: this is the one
    place a slug becomes a file name, so guarding it once covers write,
    exists, publish and unpublish alike (§4.2).
    """
    if not _LEGAL_SLUG.match(slug):
        raise StoreError(
            f"{slug!r} is not a slug: one or more of a-z, 0-9 and '-', "
            f"and nothing else"
        )
    subfolder = DRAFTS_FOLDER if draft else PUBLISHED_FOLDER
    return Path(folder) / subfolder / f"{slug}{FILE_SUFFIX}"


def exists(folder: Path, slug: str) -> bool:
    """Whether either folder holds `slug`.

    Across both, because §3 decision 5's uniqueness is Store-wide. It is a
    rule callers keep, not one `write` enforces: PRESS-0012 asks before
    offering a new entry and PRESS-0007 before writing an imported one,
    and Import writes both folders in one pass (§4.1).
    """
    return any(
        path_for(folder, slug, draft=draft).is_file() for draft in (False, True)
    )


def list_slugs(folder: Path, *, draft: bool) -> tuple[str, ...]:
    """The slugs in one folder, sorted, read off the file names (§4.4).

    Opens nothing. A missing published/ or drafts/ is not an error -- they
    are the Store's own layout rather than the caller's, so a fresh install
    needs no setup step for them (§6).
    """
    handed = Path(folder)
    if not handed.is_dir():
        raise StoreError(f"{handed} is not a folder")
    subfolder = handed / (DRAFTS_FOLDER if draft else PUBLISHED_FOLDER)
    if not subfolder.is_dir():
        return ()
    return tuple(sorted(
        path.name[: -len(FILE_SUFFIX)]
        for path in subfolder.iterdir()
        if path.is_file() and path.name.endswith(FILE_SUFFIX)
    ))


def read(path: Path) -> Entry:
    """Read one entry file. Writes nothing -- ever (§4.4, INV-2).

    Not a repair, not a normalisation, not a re-save of a header it found
    untidy. A file that cannot be parsed raises StoreError naming the path;
    it is never rewritten into something parseable, because S3 invites
    hand-editing and a silent repair loses what the writer meant.

    Bytes are decoded here rather than opened as text, so no newline
    translation can reach the body: every line break the writer typed is
    still there, which is S2 (INV-5).
    """
    target = Path(path)
    try:
        data = target.read_bytes()
    except FileNotFoundError as exc:
        raise EntryNotFound(f"there is no entry at {target}") from exc
    except OSError as exc:
        raise StoreError(f"{target} could not be read: {exc}") from exc

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StoreError(f"{target} is not UTF-8: {exc}") from exc

    header, separator, body = text.partition("\n\n")
    if not separator:
        raise StoreError(
            f"{target} has no blank line, so where the header ends and the "
            f"body begins is undecidable"
        )

    title = ""
    slug = None
    date = None
    categories: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    extra: list[tuple[str, str]] = []

    for line in header.split("\n"):
        name, colon, value = line.partition(":")
        if not colon:
            raise StoreError(f"{target}: header line {line!r} has no colon")
        if name == "Title":
            title = value.strip()
        elif name == "Slug":
            slug = value.strip()
        elif name == "Date":
            date = _parse_date(value.strip(), target)
        elif name == "Categories":
            categories = _parse_list(value)
        elif name == "Tags":
            tags = _parse_list(value)
        else:
            # Kept and never dropped, which is ADR-0001's promise, and read
            # exactly as the recognised fields are -- one rule for every
            # field rather than two.
            extra.append((name, value.strip()))

    # An absent Title, Categories or Tags reads as empty rather than as an
    # error (§4.2). Only these two are a parse failure: without a slug the
    # entry has no address, and without a date it has no place in the
    # archive.
    if not slug:
        raise StoreError(f"{target} has no Slug, so it names no address")
    if date is None:
        raise StoreError(f"{target} has no Date")

    if target.stem != slug:
        raise StoreError(
            f"{target} is named {target.stem!r} but its Slug header says "
            f"{slug!r}; the header is authoritative, so rename the file or "
            f"correct the header"
        )

    return Entry(
        slug=slug,
        title=title,
        date=date,
        categories=categories,
        tags=tags,
        body=body,
        extra=tuple(extra),
    )


def write(folder: Path, entry: Entry, *, draft: bool) -> Path:
    """Write `entry` into one folder, whole or not at all.

    Create-or-replace within its own folder: the slug identifies the entry,
    so writing a slug that folder already holds replaces that entry, and
    this consults no other folder (§4.1). Store-wide uniqueness is a rule
    callers keep -- Import writes both folders in one pass, and a write
    that consulted the other could not.

    A temporary file in the destination folder, then os.replace, which is
    atomic on both systems: an interrupted save leaves the previous file
    rather than half an entry (§4.5, INV-3).
    """
    target = path_for(folder, entry.slug, draft=draft)
    _refuse_what_the_format_cannot_carry(entry)

    handed = Path(folder)
    if not handed.is_dir():
        # A mistyped folder is not a folder to start filling (§6).
        raise StoreError(f"{handed} is not a folder")
    destination = target.parent
    try:
        destination.mkdir(exist_ok=True)
    except OSError as exc:
        raise StoreError(f"{destination} could not be created: {exc}") from exc

    lines = [
        f"Title: {entry.title}",
        f"Slug: {entry.slug}",
        f"Date: {entry.date.strftime(_DATE_FORMAT)}",
        f"Categories: {LIST_SEPARATOR.join(entry.categories)}",
        f"Tags: {LIST_SEPARATOR.join(entry.tags)}",
    ]
    # After the recognised five, in their original order relative to each
    # other. Entry.extra carries no anchor into the recognised fields, and
    # inventing one would buy an ordering nothing reads (§4.2).
    lines.extend(f"{name}: {value}" for name, value in entry.extra)
    text = "\n".join(lines) + "\n\n" + entry.body

    try:
        handle, temporary = tempfile.mkstemp(
            dir=str(destination), prefix=".entry-", suffix=".tmp"
        )
    except OSError as exc:
        raise StoreError(f"{target} could not be written: {exc}") from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, target)
    except OSError as exc:
        _discard(temporary)
        raise StoreError(f"{target} could not be written: {exc}") from exc
    except BaseException:
        _discard(temporary)
        raise
    return target


def publish(folder: Path, slug: str) -> Path:
    """Move a draft into the published folder. Reads no body, writes none."""
    return _move(folder, slug, from_draft=True)


def unpublish(folder: Path, slug: str) -> Path:
    """Move a published entry back into drafts.

    Required rather than symmetric: docs/design.md § What may depend on what
    has an undo turn an entry the fetched state does not hold back into a
    draft (§4.1).
    """
    return _move(folder, slug, from_draft=False)


def _move(folder: Path, slug: str, *, from_draft: bool) -> Path:
    """The one mechanism behind publish and unpublish.

    Refuses rather than overwriting (INV-10). os.replace is silent about a
    destination that exists, and a silent rename here destroys the entry at
    the destination -- which is what §3 decision 5's uniqueness rule exists
    to make impossible, and what this enforces.
    """
    source = path_for(folder, slug, draft=from_draft)
    target = path_for(folder, slug, draft=not from_draft)
    if not source.is_file():
        raise EntryNotFound(f"there is no entry at {source}")
    if target.exists():
        raise SlugInUse(
            f"{target} already holds {slug!r}; nothing was moved. One of the "
            f"two has to be renamed before this can go ahead"
        )
    try:
        target.parent.mkdir(exist_ok=True)
        os.replace(source, target)
    except OSError as exc:
        raise StoreError(f"{source} could not be moved to {target}: {exc}") from exc
    return target


def _refuse_what_the_format_cannot_carry(entry: Entry) -> None:
    """INV-9: refuse a value the format cannot carry, before anything is
    written. Raising after a partial write would leave a file the next read
    cannot parse, so this runs first and writes nothing.

    A comma in Title is fine -- the header runs to the end of the line, so
    nothing splits it, and refusing one would reject archive entries that
    exist. Date needs no check: it is a datetime, so the type refuses what
    this rule would.
    """
    one_line = [("Title", entry.title), ("Slug", entry.slug)]
    one_line.extend((f"Categories[{i}]", v) for i, v in enumerate(entry.categories))
    one_line.extend((f"Tags[{i}]", v) for i, v in enumerate(entry.tags))
    # The rule reaches extra deliberately (§4.2): writing back a field the
    # next read cannot parse would break ADR-0001's promise in the act of
    # keeping it. Its name carries a value too -- a newline in either splits
    # the line.
    for name, value in entry.extra:
        one_line.append((f"extra name {name!r}", name))
        one_line.append((f"extra {name}", value))

    for where, value in one_line:
        if "\n" in value or "\r" in value:
            raise StoreError(
                f"{where} contains a line break, and a header value is one "
                f"line -- a wrapped value would be read back as a new field"
            )

    for where, values in (("Categories", entry.categories), ("Tags", entry.tags)):
        for value in values:
            if "," in value:
                raise StoreError(
                    f"{where} value {value!r} contains a comma, which is "
                    f"{LIST_SEPARATOR!r}'s separator -- it would be silently "
                    f"split into two on the next read"
                )


def _parse_list(value: str) -> tuple[str, ...]:
    """Split on the comma and strip around each value, so a file
    hand-edited without the space still reads (§4.2)."""
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_date(value: str, target: Path) -> datetime:
    # Naive on purpose: §4.2 fixes Date as YYYY-MM-DD HH:MM:SS, which carries
    # no zone, and that is the shape the export and the live generator both
    # already use. An aware datetime here would not round-trip the format.
    try:
        return datetime.strptime(value, _DATE_FORMAT)  # noqa: DTZ007
    except ValueError as exc:
        raise StoreError(
            f"{target}: Date is {value!r}, not YYYY-MM-DD HH:MM:SS"
        ) from exc


def _discard(temporary: str) -> None:
    """Leave nothing behind in the folder but entry files (§4.5)."""
    try:
        os.unlink(temporary)
    except OSError:
        pass
