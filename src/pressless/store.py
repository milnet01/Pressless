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

import json
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
    _refuse_illegal_slug(slug, "a slug")
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

    # A blank line ends the header, and a Windows editor spells that line
    # "\r\n\r\n" -- which contains no "\n\n" at all, so looking only for the
    # Unix spelling rejected the writer's own entry after his editor saved it
    # (PRESS-0047). Both are accepted and the EARLIER one wins: a body may
    # hold blank lines of its own, and the header ends at the first.
    # The body is handed back exactly as found either way. §4.4 forbids a
    # repair and INV-5 keeps every line break he typed, so a CRLF body stays
    # CRLF rather than being quietly converted.
    breaks = [at for at in (text.find("\n\n"), text.find("\r\n\r\n")) if at >= 0]
    if not breaks:
        raise StoreError(
            f"{target} has no blank line, so where the header ends and the "
            f"body begins is undecidable"
        )
    at = min(breaks)
    header = text[:at]
    body = text[at + (4 if text.startswith("\r\n\r\n", at) else 2):]

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
    _write_atomically(folder, target, _entry_text(entry), prefix=".entry-", newline="\n")
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


# ---------------------------------------------------------------------------
# PRESS-0006 — the rest of the Store: fixed pages, furniture, templates,
# comments, and where a photograph's original sits.
#
# The contract is docs/specs/PRESS-0006-pages-furniture-comments.md. These
# share the name rule, the atomic write, the error types and the folder handle
# with the entry code above, which is why they are here rather than in a second
# module (§8): one part of the design, one Store.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Comment:
    identifier: str    # unique within its file; what a reply points at
    author: str        # the name as given, published as it is today
    author_url: str    # may be empty
    date: datetime     # naive wall clock, as Entry.date is
    body: str          # verbatim
    parent: str        # the identifier this replies to, or "" if top level


PAGES_FOLDER = "pages"
FURNITURE_FOLDER = "furniture"
TEMPLATES_FOLDER = "templates"
COMMENTS_FOLDER = "comments"
PHOTOGRAPHS_FOLDER = "photographs"
HTML_SUFFIX = ".html"
COMMENTS_SUFFIX = ".json"

# §3 decision 2: the site has exactly one header, one footer and one
# navigation. The page set is open (decision 8) and this one is not -- both
# constants are exported because the Builder and the Face have to agree about
# whether a fourth furniture file can exist.
FURNITURE_NAMES = ("header", "footer", "navigation")

# §4.1's six fields, in §4.1's order. The set is exact both ways: a comments
# file missing one is unreadable, and one carrying a seventh is refused rather
# than read, because the likeliest seventh is a field §4.5 forbids (§6).
_COMMENT_FIELDS = ("identifier", "author", "author_url", "date", "body", "parent")


class DanglingReply(StoreError):
    """A reply names a parent its own set does not hold; nothing was written."""


def html_path_for(folder: Path, kind: str, name: str) -> Path:
    """Where the fixed page or furniture file `name` sits (§4.3).

    One pair of calls serves both because a fixed page and a furniture file
    are the same thing -- HTML held verbatim -- in different folders. Only
    what reads them differs, and that is the Builder's business rather than
    the Store's (§4.1).
    """
    subfolder = _html_subfolder(kind)
    _refuse_illegal_slug(name, f"a {kind} name")
    if kind == FURNITURE_FOLDER and name not in FURNITURE_NAMES:
        raise StoreError(
            f"{name!r} is not a furniture file: the site has one "
            f"{', one '.join(FURNITURE_NAMES)}, and an open furniture folder "
            f"would let a fourth exist that the Builder has no place for"
        )
    return Path(folder) / subfolder / f"{name}{HTML_SUFFIX}"


def list_html(folder: Path, kind: str) -> tuple[str, ...]:
    """The names in one HTML folder, sorted, read off the file names (§4.4).

    Opens nothing, as list_slugs does. The fixed-page set is open (§3 decision
    8): Import creates the pages the site has, and a fifth page later costs a
    file rather than a code change.
    """
    return _list_names(folder, _html_subfolder(kind), HTML_SUFFIX)


def read_html(path: Path) -> str:
    """One page or furniture file, decoded and otherwise untouched (§4.2).

    Bytes are decoded here rather than opened as text, so no newline
    translation can reach the markup. No parse, no reformat, no reindent, no
    entity rewriting: the file comes back as it went in, markup errors and
    all, which is what lets the code view hand him his own file (INV-1).
    """
    target = Path(path)
    try:
        data = target.read_bytes()
    except FileNotFoundError as exc:
        raise StoreError(f"there is no file at {target}") from exc
    except OSError as exc:
        raise StoreError(f"{target} could not be read: {exc}") from exc

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Not decoded with a replacement character: that would silently change
        # his page on the next save (§6).
        raise StoreError(f"{target} is not UTF-8: {exc}") from exc


def write_html(folder: Path, kind: str, name: str, html: str) -> Path:
    """Write a page or furniture file, whole or not at all (§4.4).

    Written with newline translation OFF, so the line endings he saved are the
    line endings on disk. Entries, templates and comments take the LF rule
    instead: a fixed page is different because the code view hands him the file
    entire, so its bytes are his, and rewriting them on save is the
    reformatting §3 decision 1 exists to forbid (INV-1, INV-10).
    """
    target = html_path_for(folder, kind, name)
    _write_atomically(folder, target, html, prefix=".page-", newline="")
    return target


def template_path_for(folder: Path, name: str) -> Path:
    """Where the template `name` sits (§4.3)."""
    _refuse_illegal_slug(name, "a template name")
    return Path(folder) / TEMPLATES_FOLDER / f"{name}{FILE_SUFFIX}"


def list_templates(folder: Path) -> tuple[str, ...]:
    """The template names, sorted, read off the file names (§4.4).

    What PRESS-0017's picker binds to, and what write_template names its file
    from.
    """
    return _list_names(folder, TEMPLATES_FOLDER, FILE_SUFFIX)


def write_template(folder: Path, entry: Entry) -> Path:
    """Write an entry file into the templates folder (§4.1).

    A template IS an entry file -- the same header, the same blank line, the
    same body, written by the same code (§4.2), so there is nothing new to
    parse. This call exists only because `write` chooses between the two entry
    folders and a template belongs in neither. There is no read_template for
    the mirror reason: `read` takes a path, so it already reads one.

    Nothing here can move a template into an entry folder, and no other call
    offers to (INV-7).
    """
    target = template_path_for(folder, entry.slug)
    _refuse_what_the_format_cannot_carry(entry)
    _write_atomically(folder, target, _entry_text(entry), prefix=".entry-", newline="\n")
    return target


def comments_path_for(folder: Path, slug: str) -> Path:
    """Where the comments on `slug` sit (§4.3).

    A folder of their own rather than beside the entry (§3 decision 5).
    list_slugs returns every name ending in the entry suffix, so a comments
    file sharing that folder would be returned as an entry; a separate folder
    settles that and leaves the entry folders one rule -- one file, one entry.

    The file is named for the entry it belongs to, which is what makes it
    findable without an index.
    """
    _refuse_illegal_slug(slug, "a comments slug")
    return Path(folder) / COMMENTS_FOLDER / f"{slug}{COMMENTS_SUFFIX}"


def read_comments(path: Path) -> tuple[Comment, ...]:
    """The comments in one file, in the order they were written (§4.2).

    An absent file is (), not an error: most entries have none, so this is the
    ordinary case rather than a failure and the Builder needs no separate
    existence call (§6).

    Never sorted and never re-nested. Ordering is the Builder's decision, and
    reordering at rest makes the file no longer what was written (INV-6).
    """
    target = Path(path)
    try:
        data = target.read_bytes()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise StoreError(f"{target} could not be read: {exc}") from exc

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StoreError(f"{target} is not UTF-8: {exc}") from exc
    try:
        carried = json.loads(text)
    except ValueError as exc:
        # Never rewritten into something parseable (§6): a silent repair loses
        # what was there, and these are records nobody can retype.
        raise StoreError(f"{target} is not JSON: {exc}") from exc
    if not isinstance(carried, list):
        raise StoreError(
            f"{target} holds a {type(carried).__name__}, not a list of comments"
        )

    comments: list[Comment] = []
    for position, record in enumerate(carried):
        if not isinstance(record, dict):
            raise StoreError(
                f"{target}: comment {position} is a {type(record).__name__}, "
                f"not an object"
            )
        _refuse_the_wrong_comment_fields(record, position, target)
        comments.append(Comment(
            identifier=record["identifier"],
            author=record["author"],
            author_url=record["author_url"],
            date=_parse_date(record["date"], target),
            body=record["body"],
            parent=record["parent"],
        ))
    return tuple(comments)


def write_comments(folder: Path, slug: str, comments: tuple[Comment, ...]) -> Path:
    """Replace the comments file for `slug` whole (§4.1).

    Whole rather than one at a time: comments are read-only to the writer, so
    Import writes each entry's set once and there is no add-one-comment call
    to build.

    JSON rather than the entry format (§3 decision 6): a comment body may
    contain any line, including a blank one, so a text file holding many of
    them needs a delimiter no body can produce. Comments are also the one
    thing here he never writes -- records rather than his prose -- so the entry
    format's reason for existing does not reach them.
    """
    target = comments_path_for(folder, slug)
    _refuse_a_dangling_reply(comments, target)
    records = [
        {
            "identifier": comment.identifier,
            "author": comment.author,
            "author_url": comment.author_url,
            # The same format an entry's Date header uses, so one date rule
            # covers the whole Store (§4.2).
            "date": comment.date.strftime(_DATE_FORMAT),
            "body": comment.body,
            "parent": comment.parent,
        }
        for comment in comments
    ]
    text = json.dumps(records, indent=2, ensure_ascii=False) + "\n"
    _write_atomically(folder, target, text, prefix=".comments-", newline="\n")
    return target


def photograph_path_for(folder: Path, name: str) -> Path:
    """Where the original of the photograph `name` sits (§4.1).

    A weaker rule than the slug one, deliberately: §3 decision 10 leaves what
    a photograph's file may be called to PRESS-0016, and the archive's own
    attachment names would not pass a slug rule -- most carry an underscore.
    What is checked is the one thing a folder needs, that the name is a single
    path component and so cannot reach outside it (INV-11).

    The Store gives a photograph a place and nothing else. It neither copies
    nor opens one, and offers no call that could: putting an original there is
    Import's for the archive and PRESS-0016's afterwards, and the originals
    are never copied to the site folder.
    """
    if (
        not name
        or name in (".", "..")
        # Both separators, not just this platform's: a name carrying a
        # backslash is one component on Linux and two on Windows, and the app
        # runs on both.
        or "/" in name
        or "\\" in name
        or os.path.basename(name) != name
    ):
        raise StoreError(
            f"{name!r} is not a file name: a photograph's name is a single "
            f"path component, so that it cannot reach outside the folder it "
            f"was meant for"
        )
    return Path(folder) / PHOTOGRAPHS_FOLDER / name


def list_photographs(folder: Path) -> tuple[str, ...]:
    """The photograph file names, sorted, whole (§4.4).

    Whole rather than stemmed, unlike every other listing here: what a
    photograph's file is called is PRESS-0016's, so the Store cannot assume a
    suffix to strip.
    """
    return _list_names(folder, PHOTOGRAPHS_FOLDER, "")


def _html_subfolder(kind: str) -> str:
    """Refuse a `kind` that is neither pages nor furniture, naming what was
    passed (§6)."""
    if kind not in (PAGES_FOLDER, FURNITURE_FOLDER):
        raise StoreError(
            f"kind is {kind!r}; the HTML the Store holds is either "
            f"{PAGES_FOLDER!r} or {FURNITURE_FOLDER!r}"
        )
    return kind


def _refuse_illegal_slug(name: str, what: str) -> None:
    """The one name rule, shared by every call that turns a name into a
    slug-shaped file name (§4.3).

    This is the Store's trust boundary. Every name reaching these calls came
    from a file the writer or the archive supplied, and a name is the only
    thing here that decides where a write lands -- so it is guarded once,
    where the name becomes a path, rather than in each caller (INV-3).
    """
    if not _LEGAL_SLUG.match(name):
        raise StoreError(
            f"{name!r} is not {what}: one or more of a-z, 0-9 and '-', "
            f"and nothing else"
        )


def _refuse_the_wrong_comment_fields(record: dict, position: int, target: Path) -> None:
    """§6: a comments file carrying a field the record does not have raises,
    naming the path and the field.

    Unlike an entry's unknown header field, which ADR-0001 keeps, an
    unexpected field here is most likely one §4.5 forbids -- the email address
    or the IP address WordPress collected around a comment.
    """
    unexpected = sorted(set(record) - set(_COMMENT_FIELDS))
    if unexpected:
        raise StoreError(
            f"{target}: comment {position} carries {unexpected!r}, which a "
            f"comment does not have. A comment is {list(_COMMENT_FIELDS)!r} "
            f"and nothing else"
        )
    missing = sorted(set(_COMMENT_FIELDS) - set(record))
    if missing:
        raise StoreError(
            f"{target}: comment {position} is missing {missing!r}"
        )


def _refuse_a_dangling_reply(comments: tuple[Comment, ...], target: Path) -> None:
    """INV-5: refuse a set in which a reply names a parent that set does not
    hold, before anything is written.

    The Builder has to render a tree, and a parent that is not there is a tree
    it cannot build; refusing at the write is where the caller still knows
    what it dropped. The export spells a top-level comment's parent `0` and
    the Store treats any non-empty parent as naming another comment, so a `0`
    carried through unchanged arrives here as a dangling reply and the whole
    archive is refused (§4.2). Turning the export's fields into a Comment is
    PRESS-0007's.
    """
    held = {comment.identifier for comment in comments}
    for comment in comments:
        if comment.parent and comment.parent not in held:
            raise DanglingReply(
                f"{target}: comment {comment.identifier!r} replies to "
                f"{comment.parent!r}, which is not in the same set; nothing "
                f"was written"
            )


def _list_names(folder: Path, subfolder: str, suffix: str) -> tuple[str, ...]:
    """File names in one subfolder, sorted, opening nothing (§4.4).

    A missing subfolder lists nothing rather than raising: these folders are
    the Store's own layout rather than the caller's, so a fresh install needs
    no setup step for them (§6). That is list_slugs' rule, shared rather than
    restated. An empty `suffix` returns whole file names, which is what
    list_photographs needs.
    """
    handed = Path(folder)
    if not handed.is_dir():
        raise StoreError(f"{handed} is not a folder")
    destination = handed / subfolder
    if not destination.is_dir():
        return ()
    return tuple(sorted(
        path.name[: -len(suffix)] if suffix else path.name
        for path in destination.iterdir()
        if path.is_file() and path.name.endswith(suffix)
    ))


def _entry_text(entry: Entry) -> str:
    """One entry file's text: the five recognised fields in §4.2's order, then
    any extra fields in their original order, then the blank line, then the
    body.

    Shared by `write` and `write_template` because a template IS an entry file
    (§4.2). Entry.extra carries no anchor into the recognised fields, and
    inventing one would buy an ordering nothing reads.
    """
    lines = [
        f"Title: {entry.title}",
        f"Slug: {entry.slug}",
        f"Date: {entry.date.strftime(_DATE_FORMAT)}",
        f"Categories: {LIST_SEPARATOR.join(entry.categories)}",
        f"Tags: {LIST_SEPARATOR.join(entry.tags)}",
    ]
    lines.extend(f"{name}: {value}" for name, value in entry.extra)
    return "\n".join(lines) + "\n\n" + entry.body


def _write_atomically(
    folder: Path, target: Path, text: str, *, prefix: str, newline: str
) -> None:
    """A temporary file in the destination folder, then os.replace over the
    target -- atomic on both systems, so an interrupted save leaves the
    previous file rather than half a new one (§4.5, INV-9).

    The destination subfolder is created; the handed folder is not. A mistyped
    folder is not a folder to start filling (§6).

    `newline` is named by every caller rather than defaulted: Python's default
    is the platform's, so an unnamed write produces CRLF on Windows. Entries,
    templates and comments pass "\\n"; a page passes "" to turn translation off
    and keep the bytes it was given (§4.2).
    """
    handed = Path(folder)
    if not handed.is_dir():
        raise StoreError(f"{handed} is not a folder")
    destination = Path(target).parent
    try:
        destination.mkdir(exist_ok=True)
    except OSError as exc:
        raise StoreError(f"{destination} could not be created: {exc}") from exc

    try:
        handle, temporary = tempfile.mkstemp(
            dir=str(destination), prefix=prefix, suffix=".tmp"
        )
    except OSError as exc:
        raise StoreError(f"{target} could not be written: {exc}") from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline=newline) as stream:
            stream.write(text)
            # rename(2) orders the namespace, not the data, so without
            # this a power loss can commit the rename before the blocks
            # and leave an empty file where §4.5 promises the previous one (PRESS-0039).
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        _discard(temporary)
        raise StoreError(f"{target} could not be written: {exc}") from exc
    except BaseException:
        _discard(temporary)
        raise
