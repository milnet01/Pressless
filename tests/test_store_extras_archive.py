# PRESS-0006 §7 — the Store's archive conformance run for comments.
#
# Why this exists: the comments are the one part of the archive Import can
# never fetch again (§2), so a field the Store drops or reshapes is lost for
# good — and the export carries an email address and an IP address around
# every one of them that INV-4 says the Store must never write.
# docs/specs/PRESS-0006-pages-furniture-comments.md §7 names this test and its
# skip condition; §10 says what it proves and what it does not.
#
# This file names no person, no site and no domain — only "the writer" and
# "the archive" — per this repository's own CLAUDE.md § This repository is
# PUBLIC.
"""§7: every comment Import would carry, written through the Store and read back.

Population
----------
Import's population is the published, draft AND private posts (PRESS-0005
§7), so the comments this run carries are those hanging off one of those
items — wider than the published entries alone, which §11 makes a point of.
Both figures are printed.

Comments hanging off anything else the export holds — an attachment, a
fixed page — are outside it: Import brings entries, and a comments file is
named for the entry it belongs to (§4.3).

The key a comments file is named for
------------------------------------
NOT a slug. §4.3 has a comments file named for its entry's slug, and what
resolves an entry's slug is PRESS-0007's — PRESS-0005 §3 decision 4 puts
that rule in a private sibling workspace this repository does not reach.
This run needs only a key that is stable, unique per entry and legal by
`store.path_for`'s rule, so it uses the item's own `wp:post_id`: digits
alone always satisfy §4.2's slug rule, and a post id is not the writer's
words. Nothing here is evidence about what an entry will really be called.

The trap §4.2 names
-------------------
The export spells a top-level comment's `comment_parent` as `0`. The Store
treats any non-empty parent as naming another comment in the same file, so
a `0` carried through unchanged is a dangling reply and the whole archive
is refused. `0` becomes `""` where a `Comment` is built here — the one
place the export and the Store do not line up.

Measurements, not prose
-----------------------
§7 has this run print the archive's figures rather than the spec quoting
them: how many comments the import population carries, how many sit on
published entries alone, how many are replies, how many entries have any.

Nothing from the archive — no comment text, no commenter name, no email
address, no IP address, no domain — is written into this file, a fixture or
a report, and none is printed by a passing run. It is read at run time only,
from a path outside this repository, exactly as the personal-data section of
this project's CLAUDE.md requires. A FAILING assertion names the comment id
it failed on, because otherwise the failure is not diagnosable; it reports a
difference as an offset and a length and never as the text itself.

That last rule needs `_through_the_store` to hold, and it is not tidiness:
pytest prints a failing frame's ARGUMENTS, and a `write_comments` frame holds
every comment on an entry — so an ordinary failure inside the Store would
print readers' names and words into a log. Every Store call here goes through
that helper, and no Store call is made anywhere else in this file.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from pressless import store

PRESSLESS_ARCHIVE = os.environ.get("PRESSLESS_ARCHIVE")

pytestmark = pytest.mark.archive

needs_archive = pytest.mark.skipif(
    not PRESSLESS_ARCHIVE,
    reason="PRESS-0006: set PRESSLESS_ARCHIVE to a WordPress export path to run this",
)

# §4.2: a comment's date is written in the same format an entry's Date header
# uses, and the export's own comment_date is already that shape.
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# PRESS-0005 §7's population, restated because it decides which comments
# Import carries.
IMPORT_STATUSES = ("publish", "draft", "private")

# The two fields §4.5 and INV-4 forbid the Store to carry.
CONTACT_FIELDS = ("comment_author_email", "comment_author_IP")

# The fields a Comment keeps, in the order §4.1 declares them.
COMMENT_FIELDS = ("identifier", "author", "author_url", "date", "body", "parent")


def _namespaces(root) -> dict[str, str]:
    """The export's own `wp:` namespace, taken from the document.

    Discovered rather than pinned: WXR has shipped several versions of the
    URI, and a pinned one that does not match the file finds no comments at
    all — which would read as an archive with nothing in it rather than as a
    parse that missed.
    """
    for element in root.iter():
        tag = element.tag
        if isinstance(tag, str) and tag.startswith("{http://wordpress.org/export/"):
            return {"wp": tag[1:].split("}", 1)[0]}
    raise AssertionError(
        f"{PRESSLESS_ARCHIVE} declares no http://wordpress.org/export/ namespace "
        f"— not a WordPress WXR export?"
    )


def _open_archive():
    """The export's <channel> and its namespaces, or a failure naming the path."""
    xml_path = Path(PRESSLESS_ARCHIVE)
    assert xml_path.is_file(), f"PRESSLESS_ARCHIVE does not name a file: {xml_path}"
    root = ET.parse(xml_path).getroot()
    namespaces = _namespaces(root)
    channel = root.find("channel")
    assert channel is not None, f"{xml_path} has no <channel> — not a WXR export?"
    return channel, namespaces


def _through_the_store(description: str, call):
    """Make one Store call, and let no failure inside it print the archive.

    `call` takes NO arguments and closes over what the Store needs: pytest
    shows the arguments of every frame in a traceback, so a helper taking the
    comments through would print them itself — which is what this exists to
    stop. The exception is re-raised with its type, its own message and the
    line that raised it, and without the frames that carry a reader's words.
    The message is the Store's own; it is expected to name a path, a slug or
    a field, which is what makes the failure diagnosable.
    """
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 -- any failure here must be re-raised scrubbed
        raised_at = exc.__traceback__
        while raised_at is not None and raised_at.tb_next is not None:
            raised_at = raised_at.tb_next
        where = (
            f"{Path(raised_at.tb_frame.f_code.co_filename).name}:{raised_at.tb_lineno}"
            if raised_at is not None
            else "an unknown line"
        )
        raise AssertionError(
            f"{description} failed inside the Store, so nothing downstream of it "
            f"was checked.\n"
            f"  expected: the call to return\n"
            f"  actual:   {type(exc).__name__}: {exc} (raised at {where}). The "
            f"frames are dropped on purpose — they carry the archive"
        ) from None


def _comment(element, namespaces) -> store.Comment:
    """One export <wp:comment> as §4.1's record.

    Every field is carried across as it stands except the parent: `0` is the
    export's way of saying top level and the Store's way of saying "a comment
    with that identifier" (§4.2). The email address and the IP address the
    export holds beside these are read here and go nowhere — `Comment` has no
    field for either, which is INV-4.
    """
    def field(name: str) -> str:
        return element.findtext(f"wp:{name}", "", namespaces) or ""

    identifier = field("comment_id").strip()
    parent = field("comment_parent").strip()
    # The export carries local wall-clock time with no zone, as an entry's
    # date does — an offset the archive does not have would be invented here.
    # Parsed here rather than left to strptime's own error, whose message
    # quotes the string it was given.
    try:
        date = datetime.strptime(field("comment_date").strip(), DATE_FORMAT)  # noqa: DTZ007
    except ValueError as exc:
        raise AssertionError(
            f"comment id {identifier!r} carries a comment_date the Store's own "
            f"date format cannot hold.\n"
            f"  expected: {DATE_FORMAT}\n"
            f"  actual:   a value {len(field('comment_date').strip())} characters "
            f"long that does not parse ({exc.__class__.__name__})"
        ) from None
    return store.Comment(
        identifier=identifier,
        author=field("comment_author"),
        author_url=field("comment_author_url"),
        date=date,
        body=field("comment_content"),
        parent="" if parent in ("", "0") else parent,
    )


def _import_population(channel, namespaces):
    """Every entry Import brings that has comments, as (key, comments, published).

    Document order is kept: §4.2 stores comments "in the order they are to be
    read back" and INV-6 forbids sorting, so the order the export gives them
    in is the order this run writes and expects back.
    """
    population = []
    for item in channel.findall("item"):
        if item.findtext("wp:post_type", "", namespaces) != "post":
            continue
        status = item.findtext("wp:status", "", namespaces)
        if status not in IMPORT_STATUSES:
            continue
        elements = item.findall("wp:comment", namespaces)
        if not elements:
            continue
        key = (item.findtext("wp:post_id", "", namespaces) or "").strip()
        assert key, "an item Import would bring carries no wp:post_id to key its comments by"
        comments = tuple(_comment(element, namespaces) for element in elements)
        population.append((key, comments, status == "publish"))
    return population


def _archive_population():
    """The population, asserted non-empty so a mis-parse cannot pass quietly."""
    channel, namespaces = _open_archive()
    population = _import_population(channel, namespaces)
    assert population, (
        f"found no published, draft or private post carrying a comment in "
        f"{PRESSLESS_ARCHIVE} — expected at least one"
    )
    return population


def _contact_values(channel, namespaces) -> tuple[str, ...]:
    """Every non-empty email address and IP address the export carries.

    Every comment in the file, not only the population's: a value that
    reaches a file written is a leak wherever in the export it came from.
    Empty values are dropped — the empty string is in every file ever
    written, so keeping one would fail this run against any implementation.
    """
    values = set()
    for element in channel.iter():
        tag = element.tag
        if not isinstance(tag, str) or not tag.endswith("}comment"):
            continue
        for field in CONTACT_FIELDS:
            value = (element.findtext(f"wp:{field}", "", namespaces) or "").strip()
            if value:
                values.add(value)
    return tuple(sorted(values))


def _as_text(value) -> str:
    """A field as the text a file would hold, so one comparison covers all six."""
    if isinstance(value, datetime):
        return value.strftime(DATE_FORMAT)
    return str(value)


def _where_they_differ(expected: str, actual: str) -> str:
    """How two field values diverge, as an offset and two lengths.

    Never the text: a comment is a reader's own words and a name is a
    reader's name, and neither belongs in a log. The offset is what an
    implementer needs — it says which part of the value the format lost.
    """
    for i, (a, b) in enumerate(zip(expected, actual, strict=False)):
        if a != b:
            return (
                f"first differs at offset {i} of {len(expected)} expected "
                f"characters ({len(actual)} actual)"
            )
    return (
        f"identical for {min(len(expected), len(actual))} characters, then one "
        f"ends: expected {len(expected)} characters, actual {len(actual)}"
    )


def _write_the_archive(folder: Path):
    """Write every population entry's comments through the Store.

    Returns (key, comments, path) per entry. The folder is created here
    because §6 has the caller supply a folder and the Store make its own
    layout inside it.
    """
    written = []
    for key, comments, _published in _archive_population():
        path = _through_the_store(
            f"write_comments for entry key {key!r} ({len(comments)} comments)",
            lambda key=key, comments=comments: store.write_comments(folder, key, comments),
        )
        written.append((key, comments, path))
    return written


@needs_archive
def test_the_archives_comments_are_the_figures_this_spec_does_not_quote():
    """§7's measurements, and the one thing an identifier has to be.

    `Comment.identifier` is "unique within its file; what a reply points at"
    (§4.1). Two comments on one entry sharing an id make a reply ambiguous
    and INV-5's parent check meaningless, so the archive is asserted to carry
    none.
    """
    population = _archive_population()

    comments = [comment for _key, group, _published in population for comment in group]
    published = [
        comment
        for _key, group, is_published in population
        if is_published
        for comment in group
    ]
    replies = [comment for comment in comments if comment.parent]
    per_entry = Counter(len(group) for _key, group, _published in population)
    busiest = max(per_entry)

    # §7: these figures are evidence, they move, and this is where they live.
    print(f"comments Import brings (publish + draft + private posts): {len(comments)}")
    print(f"  sitting on published entries alone:                    {len(published)}")
    print(f"  that are replies to another comment:                   {len(replies)}")
    print(f"entries carrying any comment: {len(population)}")
    print(f"most comments on one entry:   {busiest}")
    print(f"top-level comments (parent mapped from the export's '0'): "
          f"{len(comments) - len(replies)}")

    ambiguous = []
    for key, group, _published in population:
        counts = Counter(comment.identifier for comment in group)
        ambiguous.extend(
            (key, identifier, count) for identifier, count in counts.items() if count > 1
        )

    assert not ambiguous, (
        f"an identifier is unique within its file (§4.1), and {len(ambiguous)} is "
        f"not. Expected every comment on an entry to carry a distinct id, actual "
        f"first offender: entry key {ambiguous[0][0]!r}, comment id "
        f"{ambiguous[0][1]!r} used {ambiguous[0][2]} times"
    )


@needs_archive
def test_every_reply_in_the_archive_names_a_parent_in_its_own_file():
    """INV-5 from the archive's side: `write_comments` refuses a set whose
    reply names an absent parent, so a real reply pointing outside its own
    entry would have the whole import refused.

    This is also where §4.2's trap shows: leave the export's `0` in place and
    every top-level comment becomes a reply to a comment that is not there.
    """
    population = _archive_population()

    dangling = []
    for key, group, _published in population:
        held = {comment.identifier for comment in group}
        dangling.extend(
            (key, comment.identifier, comment.parent)
            for comment in group
            if comment.parent and comment.parent not in held
        )

    replies = sum(1 for _key, group, _p in population for c in group if c.parent)
    print(f"replies: {replies}; whose parent is not in their own file: {len(dangling)}")

    assert not dangling, (
        f"{len(dangling)} reply/replies name a parent their own comments file does "
        f"not hold, so `write_comments` raises DanglingReply (INV-5) and the entry's "
        f"comments are all refused. Expected 0. First: entry key {dangling[0][0]!r}, "
        f"comment id {dangling[0][1]!r}, parent id {dangling[0][2]!r}"
    )


@needs_archive
def test_the_archives_comments_survive_a_round_trip(tmp_path):
    """§7: write every comment Import would carry through the Store, read them
    all back, and assert no field and no ordering changed (INV-6).

    Breaks when the format loses or reshapes anything the archive actually
    contains — a body's blank lines, a quotation mark, a non-ASCII character,
    a reply that sits before the comment it answers.
    """
    folder = tmp_path / "pressless"
    folder.mkdir()

    written = _write_the_archive(folder)

    for key, _comments, path in written:
        assert path.is_file(), (
            f"write_comments returned {path} for entry key {key!r}, which is not a file"
        )

    total = sum(len(comments) for _key, comments, _path in written)
    print(f"comments files written: {len(written)}; comments in them: {total}")

    mismatches = []
    short = []
    for key, comments, path in written:
        back = _through_the_store(
            f"read_comments for entry key {key!r}",
            lambda path=path: store.read_comments(path),
        )
        if len(back) != len(comments):
            short.append((key, len(comments), len(back)))
            continue
        for position, (expected, actual) in enumerate(
                zip(comments, back, strict=True)):
            for field in COMMENT_FIELDS:
                want, got = _as_text(getattr(expected, field)), _as_text(getattr(actual, field))
                if want != got:
                    mismatches.append(
                        (key, expected.identifier, position, field, _where_they_differ(want, got))
                    )

    print(f"comments read back: {total}; files short or long: {len(short)}; "
          f"fields that changed: {len(mismatches)}")

    assert not short, (
        f"{len(short)} comments file(s) read back a different number of comments than "
        f"were written. First: entry key {short[0][0]!r}, expected {short[0][1]}, "
        f"actual {short[0][2]}"
    )
    if mismatches:
        key, identifier, position, field, where = mismatches[0]
        raise AssertionError(
            f"{len(mismatches)} field(s) changed across a write/read round trip of "
            f"{total} comments. First: entry key {key!r}, comment id {identifier!r} at "
            f"position {position}, field {field!r}\n"
            f"  expected: the value written, unchanged\n"
            f"  actual:   {where}"
        )


@needs_archive
def test_no_address_the_export_carries_reaches_a_file_the_store_writes(tmp_path):
    """INV-4 against the real export: no `comment_author_email` and no
    `comment_author_IP` value the archive holds appears in anything written.

    The Store has no field for either (§4.1), so this can only fail where an
    implementer widened `Comment` or kept the export record beside it — which
    publishes a real reader's address the first time the site is built.

    Every file under the handed folder is searched, not only the comments
    files: a leak into a temporary file left behind is still a leak.
    """
    folder = tmp_path / "pressless"
    folder.mkdir()

    channel, namespaces = _open_archive()
    values = _contact_values(channel, namespaces)
    assert values, (
        f"found no email or IP value in {PRESSLESS_ARCHIVE} — this run would then "
        f"prove nothing, so it is a failure rather than a pass"
    )

    written = _write_the_archive(folder)
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    print(f"contact values searched for: {len(values)}; files written: {len(written)}; "
          f"files searched: {len(files)}")

    found = []
    for path in files:
        data = path.read_bytes()
        found.extend(
            (path.name, index)
            for index, value in enumerate(values)
            if value.encode("utf-8") in data
        )

    # The value itself is never printed, on a pass or a failure: it is the
    # very thing this test exists to keep out of a log. Its position in the
    # sorted list is enough to find it in the export by hand.
    assert not found, (
        f"{len(found)} email or IP value(s) the export carries appear in files the "
        f"Store wrote, which INV-4 forbids. Expected 0 of {len(values)} values in "
        f"{len(files)} file(s); actual first hit in file {found[0][0]!r} (value at "
        f"index {found[0][1]} of the sorted contact values — not printed)"
    )
