# INV-1..10 for PRESS-0005 (the Store). One test per invariant, named in that
# spec's §5 and §10. Unlabelled: it needs nothing but a temporary directory and
# must run everywhere (§7), unlike the archive round trip, which lives in
# tests/test_store_archive.py because it needs the WordPress export.
#
# Why this exists: docs/specs/PRESS-0005-store.md is the contract.
from __future__ import annotations

import ast
import builtins
import dataclasses
import inspect
import io
import os
import pathlib
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import pytest

import pressless.store as store_module
from pressless.store import (
    RECOGNISED_FIELDS,
    Entry,
    SlugInUse,
    StoreError,
    list_slugs,
    path_for,
    publish,
    read,
    unpublish,
    write,
)

# The documented folder names and suffix (§4.1, §4.3), written out here rather
# than imported from the module under test. Sharing the literal would have the
# module compared against itself: PUBLISHED_FOLDER could name anything and
# every assertion below would stay green.
_PUBLISHED = "published"
_DRAFTS = "drafts"
_SUFFIX = ".txt"

# Naive on purpose: §4.2's Date is `YYYY-MM-DD HH:MM:SS` and carries no zone,
# so an aware fixture would be the wrong shape for the format under test.
_A_DATE = datetime(2014, 11, 9, 21, 32, 0)  # noqa: DTZ001 -- see above


def _entry(slug: str = "an-example", **overrides) -> Entry:
    """§4.1's Entry, valid unless an override makes it otherwise."""
    fields = {
        "slug": slug,
        "title": "An example",
        "date": _A_DATE,
        "categories": ("poetry",),
        "tags": ("one", "two"),
        "body": "The body starts here.\n",
        "extra": (),
    }
    fields.update(overrides)
    return Entry(**fields)


def _snapshot(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, by path relative to it, with its bytes.

    Both halves matter wherever this is used: the key set catches a file
    created or removed, and the bytes catch one rewritten in place."""
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


class _Open(NamedTuple):
    """One filesystem open the module under test performed."""

    path: str | None      # None where the call named a file descriptor
    mode: str
    encoding: str | None
    newline: str | None
    binary: bool

    def writes(self) -> bool:
        return any(character in self.mode for character in "wxa+")


def _watch_opens(monkeypatch) -> list[_Open]:
    """Record every open the code under test performs, with its mode.

    Six entry points, because which one an implementation reaches for is its
    own choice and the invariants are about all of them: builtins.open and
    io.open (the same function, patched at both names a module may hold),
    os.open and os.fdopen (what tempfile.mkstemp and §4.5's shape use), and
    Path.open / Path.write_text / Path.write_bytes (what settings.py's
    read_text goes through). A watch that missed the one the implementation
    happened to use would report nothing and look like a clean pass."""
    opens: list[_Open] = []

    real_open = builtins.open
    real_io_open = io.open
    real_os_open = os.open
    real_fdopen = os.fdopen
    real_path_open = pathlib.Path.open
    real_write_text = pathlib.Path.write_text
    real_write_bytes = pathlib.Path.write_bytes

    def _record(path, mode, encoding, newline):
        try:
            named = None if path is None else os.fspath(path)
        except TypeError:
            named = None
        opens.append(_Open(named, mode, encoding, newline, "b" in mode))

    def _argument(args, kwargs, index, name):
        """One optional argument of an open(), however it was passed.

        Reading it from kwargs alone is wrong and was measured so: os.fdopen
        and Path.write_text both delegate inwards POSITIONALLY, so a
        conforming write that named UTF-8 and a newline was recorded as having
        named neither -- INV-6 then failed against exactly the code it exists
        to accept."""
        if name in kwargs:
            return kwargs[name]
        return args[index] if len(args) > index else None

    def watched_open(file, mode="r", *args, **kwargs):
        _record(file, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_open(file, mode, *args, **kwargs)

    def watched_io_open(file, mode="r", *args, **kwargs):
        _record(file, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_io_open(file, mode, *args, **kwargs)

    def watched_os_open(path, flags, *args, **kwargs):
        writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        # Always binary at this level, so INV-6 asks nothing of it -- the
        # os.fdopen that wraps it is where an encoding would be named.
        _record(path, "wb" if writing else "rb", None, None)
        return real_os_open(path, flags, *args, **kwargs)

    def watched_fdopen(fd, mode="r", *args, **kwargs):
        _record(None, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_fdopen(fd, mode, *args, **kwargs)

    def watched_path_open(self, mode="r", *args, **kwargs):
        _record(self, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_path_open(self, mode, *args, **kwargs)

    def watched_write_text(self, data, *args, **kwargs):
        _record(self, "w", _argument(args, kwargs, 0, "encoding"),
                _argument(args, kwargs, 2, "newline"))
        return real_write_text(self, data, *args, **kwargs)

    def watched_write_bytes(self, data):
        _record(self, "wb", None, None)
        return real_write_bytes(self, data)

    monkeypatch.setattr(builtins, "open", watched_open)
    monkeypatch.setattr(io, "open", watched_io_open)
    monkeypatch.setattr(os, "open", watched_os_open)
    monkeypatch.setattr(os, "fdopen", watched_fdopen)
    monkeypatch.setattr(pathlib.Path, "open", watched_path_open)
    monkeypatch.setattr(pathlib.Path, "write_text", watched_write_text)
    monkeypatch.setattr(pathlib.Path, "write_bytes", watched_write_bytes)
    return opens


# --------------------------------------------------------------- INV-1 ----

# Network modules, and nothing else. os, pathlib, tempfile, dataclasses and
# datetime are all legitimate here -- the Store's whole job is files -- which
# is the difference from test_marks_is_pure, whose module may touch no disk.
_FORBIDDEN_TOP_LEVEL_IMPORTS = {
    "socket", "ssl", "urllib", "http", "requests", "httpx",
    "ftplib", "smtplib", "poplib", "imaplib", "xmlrpc", "webbrowser",
}


def test_store_imports_nothing_forbidden():
    """INV-1: store.py imports no network module and does not import
    pressless.marks.

    Walks the module's AST, as test_marks_is_pure does. The source is read
    here, by the test, never by store.py itself.

    Breaks when an implementer imports Marks to validate a body, or urllib to
    check that a slug is a legal address (§4.6).

    This test is weak in a way the spec names (§7): an import list proves what
    the module imports, never that reading or writing works. It passes against
    the stub by design."""
    tree = ast.parse(inspect.getsource(store_module))

    imported: set[str] = set()
    relative_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_imports.append(node.module or "")
            elif node.module:
                imported.add(node.module)

    network = {name for name in imported if name.split(".")[0] in _FORBIDDEN_TOP_LEVEL_IMPORTS}
    assert not network, (
        f"store.py imports {sorted(network)!r}, a network module. §4.6: the "
        f"Store never reaches the network. Expected none of "
        f"{sorted(_FORBIDDEN_TOP_LEVEL_IMPORTS)!r}"
    )

    marks = {name for name in imported if name == "pressless.marks" or name.startswith(
        "pressless.marks.")}
    assert not marks, (
        f"store.py imports {sorted(marks)!r}. §4.6: turning marked text into "
        f"HTML is Marks' job and the Store does not import Marks"
    )
    assert "marks" not in relative_imports, (
        f"store.py has a relative import of {relative_imports!r}, which can "
        f"only name a sibling pressless module -- 'marks' is forbidden (§4.6)"
    )


# --------------------------------------------------------------- INV-2 ----

_WITH_AN_UNKNOWN_FIELD = (
    "Title: An example\n"
    "Slug: an-example\n"
    "Date: 2014-11-09 21:32:00\n"
    "Categories: poetry\n"
    "Tags: one, two\n"
    "X-Wordpress-Id: 1234\n"
    "\n"
    "The body starts here.\n"
)

# Untidy but parseable by §4.2: no Title line (absent is empty, not an error),
# the fields out of §4.2's order, no space after the list comma, and runs of
# spaces after a colon. Every one of those is something a repairing read would
# rewrite -- which is why INV-2 needs this file. Against a well-formed one
# there is nothing to repair and the assertion stays green whatever read does.
_UNTIDY = (
    "Slug: untidy\n"
    "Date:   2014-11-10 08:05:00\n"
    "Tags: one,two\n"
    "Categories:   poetry\n"
    "X-Untidy:   spaced\n"
    "\n"
    "Body of the untidy one.\n"
)


def test_reading_never_writes(tmp_path, monkeypatch):
    """INV-2: read and list_slugs open no path for writing and leave the
    folder's file list unchanged.

    Breaks when an implementer makes read normalise a header it finds untidy,
    or list_slugs build an index file (§4.4). The cost is S3: a file the writer
    hand-edited is silently rewritten under him, and a Store that repairs on
    read cannot be trusted to have left twelve years of writing alone."""
    published = tmp_path / _PUBLISHED
    published.mkdir()
    (published / ("an-example" + _SUFFIX)).write_text(_WITH_AN_UNKNOWN_FIELD, encoding="utf-8")
    (published / ("untidy" + _SUFFIX)).write_text(_UNTIDY, encoding="utf-8")

    before = _snapshot(tmp_path)

    try:
        opens = _watch_opens(monkeypatch)
        read(published / ("an-example" + _SUFFIX))
        read(published / ("untidy" + _SUFFIX))
        list_slugs(tmp_path, draft=False)
        list_slugs(tmp_path, draft=True)
    finally:
        monkeypatch.undo()

    assert opens, (
        "no filesystem open was recorded at all -- the watch did not fire, so "
        "this test proves nothing about what read() and list_slugs() opened"
    )
    writing = [record for record in opens if record.writes()]
    assert not writing, (
        f"read()/list_slugs() opened {[(r.path, r.mode) for r in writing]!r} "
        f"for writing. §4.4: reading writes nothing -- not a repair, not a "
        f"normalisation, not an index. Expected every open to be read-only"
    )

    after = _snapshot(tmp_path)
    assert sorted(after) == sorted(before), (
        f"the folder's file list changed across a read: before "
        f"{sorted(before)!r}, after {sorted(after)!r}"
    )
    for name, content in before.items():
        assert after[name] == content, (
            f"{name} was rewritten by a read. Expected {content!r}, "
            f"got {after[name]!r}"
        )


# --------------------------------------------------------------- INV-3 ----


def test_write_is_atomic(tmp_path, monkeypatch):
    """INV-3: after a write interrupted before completion, the file on disk is
    the previous one.

    Asserting os.replace's DESTINATION as well as the effect is what pins the
    mechanism (§4.5). Against an implementation that opens the target and
    writes into it the patch never fires, the write completes, and the entry on
    disk is the new one -- so the effect half alone would not bite.

    Breaks when an implementer writes straight into the target: a crash
    mid-save then leaves half an entry where a whole one used to be."""
    previous = _entry(body="The previous body.\n")
    target = write(tmp_path, previous, draft=False)
    before = Path(target).read_bytes()

    calls: list[tuple[str, str]] = []

    def interrupted_replace(src, dst, *args, **kwargs):
        calls.append((os.fspath(src), os.fspath(dst)))
        raise OSError("interrupted before the replace completed")

    monkeypatch.setattr(os, "replace", interrupted_replace)
    # Not a bare Exception: a blind assertion here passes against any failure
    # at all, the stub's NotImplementedError included.
    with pytest.raises((StoreError, OSError)):
        write(tmp_path, _entry(body="The new body.\n"), draft=False)
    monkeypatch.undo()

    assert calls, (
        "write() never reached os.replace -- it wrote into the target "
        "directly, so there is no point at which an interruption leaves the "
        "previous file (§4.5)"
    )
    expected = os.fspath(path_for(tmp_path, previous.slug, draft=False))
    destinations = {destination for _, destination in calls}
    assert destinations == {expected}, (
        f"write() replaced {destinations!r}; §4.5 requires the destination to "
        f"be path_for(folder, slug, draft=False) = {expected!r}"
    )

    assert Path(target).read_bytes() == before, (
        f"after a write interrupted at the replace the file on disk is not the "
        f"previous one. Expected {before!r}, got {Path(target).read_bytes()!r}"
    )
    assert read(target) == previous, (
        f"after an interrupted write read() no longer returns the previous "
        f"entry. Expected {previous!r}, got {read(target)!r}"
    )


# --------------------------------------------------------------- INV-4 ----


def test_unknown_header_fields_survive(tmp_path):
    """INV-4: a header field the Store does not recognise is present and
    byte-identical after a read followed by a write, and two of them keep their
    order relative to each other.

    Breaks when write is built from the dataclass's five known fields alone.
    This is ADR-0001's promise -- nothing dropped, nothing altered -- and it is
    the one an implementation drops without noticing, because every test that
    only round-trips the five recognised fields stays green."""
    source = tmp_path / "source"
    (source / _PUBLISHED).mkdir(parents=True)
    original = (
        "Title: An example\n"
        "Slug: an-example\n"
        "Date: 2014-11-09 21:32:00\n"
        "Categories: poetry\n"
        "Tags: one, two\n"
        "X-Wordpress-Id: 1234\n"
        "X-Comment-Count: 7\n"
        "\n"
        "The body starts here.\n"
    )
    (source / _PUBLISHED / ("an-example" + _SUFFIX)).write_text(original, encoding="utf-8")

    entry = read(source / _PUBLISHED / ("an-example" + _SUFFIX))
    assert entry.extra == (("X-Wordpress-Id", "1234"), ("X-Comment-Count", "7")), (
        f"read() lost or reordered the unrecognised fields. Expected "
        f"(('X-Wordpress-Id', '1234'), ('X-Comment-Count', '7')), got "
        f"{entry.extra!r}"
    )

    destination = tmp_path / "destination"
    destination.mkdir()
    written = Path(write(destination, entry, draft=False))
    raw = written.read_text(encoding="utf-8")

    for name, value in (("X-Wordpress-Id", "1234"), ("X-Comment-Count", "7")):
        assert f"{name}: {value}\n" in raw, (
            f"write() did not carry the unrecognised field {name!r} through "
            f"byte-identically. Expected a line {name + ': ' + value!r} in the "
            f"file, got:\n{raw}"
        )
    assert raw.index("X-Wordpress-Id") < raw.index("X-Comment-Count"), (
        f"two unrecognised fields did not keep their order relative to each "
        f"other (§4.2). Expected X-Wordpress-Id before X-Comment-Count, got:"
        f"\n{raw}"
    )

    again = read(written)
    assert again.extra == entry.extra, (
        f"the unrecognised fields did not survive read->write->read. Expected "
        f"{entry.extra!r}, got {again.extra!r}"
    )


# --------------------------------------------------------------- INV-5 ----


def test_body_survives_a_round_trip(tmp_path):
    """INV-5: a body survives read then write byte-for-byte, including
    consecutive newlines, trailing newlines and a line that looks like a header
    field.

    Breaks when an implementer strips, collapses or normalises the body, which
    is S2 broken -- every line break the writer typed is still there. The
    'Looks: like a field' line is what catches a parser that goes on reading
    the header past the blank line (§4.2)."""
    bodies = {
        "no trailing newline": (
            "First line.\n"
            "\n"
            "Looks: like a field\n"
            "\n"
            "\n"
            "Last line with no trailing newline."
        ),
        "two trailing newlines": (
            "First line.\n"
            "Looks: like a field\n"
            "\n"
            "Last line.\n"
            "\n"
        ),
    }

    for index, (case, body) in enumerate(bodies.items()):
        slug = f"round-trip-{index}"
        written = Path(write(tmp_path, _entry(slug=slug, body=body), draft=False))
        first = read(written)
        assert first.body == body, (
            f"{case}: the body did not survive write->read. Expected "
            f"{body!r}, got {first.body!r}"
        )

        rewritten = Path(write(tmp_path, first, draft=False))
        second = read(rewritten)
        assert second.body == body, (
            f"{case}: the body did not survive a second round trip. Expected "
            f"{body!r}, got {second.body!r}"
        )


# --------------------------------------------------------------- INV-6 ----


def test_written_bytes_are_utf8_lf(tmp_path, monkeypatch):
    """INV-6: files are written UTF-8 with LF line endings whatever the
    platform's defaults.

    Two halves, and the spec requires both. The newline lives in the BODY:
    INV-9 refuses one in a title, so a fixture putting it there could never
    reach its assertion.

    The byte half cannot catch the defect on this platform, and that was
    measured rather than reasoned (§5 INV-6): on Linux the unnamed defaults are
    already UTF-8 and LF, so an implementation that names neither produces
    identical bytes and the test goes green against exactly the code it exists
    to reject. It is Windows that would write CRLF in cp1252. Asserting the
    OPEN CALL is what makes the invariant bite on the platform the suite has --
    do not simplify this back to bytes alone."""
    entry = _entry(
        slug="accented",
        title="Un été à Paris",
        body="Première ligne\nDeuxième ligne\nTroisième ligne\n",
    )

    try:
        opens = _watch_opens(monkeypatch)
        written = Path(write(tmp_path, entry, draft=False))
    finally:
        monkeypatch.undo()

    raw = written.read_bytes()
    assert b"\r" not in raw, (
        f"the written file carries a carriage return, so its line endings are "
        f"not LF (§4.2). Expected no b'\\r' anywhere, got {raw!r}"
    )
    assert entry.title.encode("utf-8") in raw, (
        f"the accented title is not in the file as UTF-8. Expected "
        f"{entry.title.encode('utf-8')!r} in the bytes, got {raw!r}"
    )
    assert entry.body.encode("utf-8") in raw, (
        f"the accented body is not in the file as UTF-8, or its line breaks "
        f"were altered. Expected {entry.body.encode('utf-8')!r} in the bytes, "
        f"got {raw!r}"
    )

    writing = [record for record in opens if record.writes()]
    assert writing, (
        "write() performed no recorded open at all, so nothing here shows how "
        "the file was opened -- the watch did not fire"
    )
    unnamed = [
        record for record in writing
        if not record.binary
        and (
            (record.encoding or "").lower().replace("-", "") != "utf8"
            or record.newline not in ("\n", "")
        )
    ]
    assert not unnamed, (
        f"write() opened a file in text mode without naming UTF-8 and an "
        f"explicit newline: {[(r.path, r.mode, r.encoding, r.newline) for r in unnamed]!r}. "
        f"Expected encoding='utf-8' and newline='\\n' (or '') on every text "
        f"write. On Linux the unnamed defaults produce the right bytes anyway; "
        f"on Windows they produce CRLF in cp1252 (§4.2)"
    )


# --------------------------------------------------------------- INV-7 ----


def test_a_draft_never_reaches_published(tmp_path):
    """INV-7: list_slugs(folder, draft=False) never returns a slug whose file
    is in the drafts folder, and write(..., draft=True) never creates a file
    under published/.

    Breaks when the two folders are collapsed into one with a header field, or
    when publish copies rather than moves and leaves the draft behind. This is
    where S7 starts: the worst failure this project has is an unfinished poem
    on the live site with nobody noticing."""
    slug = "unfinished"
    written = Path(write(tmp_path, _entry(slug=slug), draft=True))

    assert written == tmp_path / _DRAFTS / (slug + _SUFFIX), (
        f"write(draft=True) put the file at {written!r}; §4.3 requires "
        f"{tmp_path / _DRAFTS / (slug + _SUFFIX)!r}"
    )
    assert not (tmp_path / _PUBLISHED / (slug + _SUFFIX)).exists(), (
        f"write(draft=True) created a file under {_PUBLISHED}/ as well -- the "
        f"drafts folder is not the only place a draft may sit (§4.3)"
    )
    assert slug not in list_slugs(tmp_path, draft=False), (
        f"list_slugs(draft=False) returned {slug!r}, whose only file is in "
        f"{_DRAFTS}/. Expected it absent, got {list_slugs(tmp_path, draft=False)!r}"
    )
    assert slug in list_slugs(tmp_path, draft=True), (
        f"list_slugs(draft=True) did not return {slug!r}, which was just "
        f"written as a draft. Got {list_slugs(tmp_path, draft=True)!r}"
    )

    # Second phase: this is what catches a publish that COPIES. The first
    # cannot, because nothing has moved yet (§5 INV-7).
    moved = Path(publish(tmp_path, slug))
    assert moved == tmp_path / _PUBLISHED / (slug + _SUFFIX), (
        f"publish() returned {moved!r}; §4.3 requires "
        f"{tmp_path / _PUBLISHED / (slug + _SUFFIX)!r}"
    )
    assert not (tmp_path / _DRAFTS / (slug + _SUFFIX)).exists(), (
        f"after publish() the drafts folder still holds {slug + _SUFFIX!r} -- "
        f"publish copied rather than moved, so the draft is still there to be "
        f"published again (§4.1)"
    )
    assert slug not in list_slugs(tmp_path, draft=True), (
        f"after publish() list_slugs(draft=True) still returns {slug!r}. Got "
        f"{list_slugs(tmp_path, draft=True)!r}"
    )
    assert slug in list_slugs(tmp_path, draft=False), (
        f"after publish() list_slugs(draft=False) does not return {slug!r}. "
        f"Got {list_slugs(tmp_path, draft=False)!r}"
    )


# --------------------------------------------------------------- INV-8 ----

# §4.2's five names, in §4.2's order, and §4.1's Entry fields. Written out here
# rather than imported: sharing the literal with the module would have the
# module compared against itself, and RECOGNISED_FIELDS could then name
# anything at all and stay green.
_RECOGNISED_FIELDS = ("Title", "Slug", "Date", "Categories", "Tags")
_ENTRY_FIELDS = {"slug", "title", "date", "categories", "tags", "body", "extra"}


def test_field_names_are_the_documented_set():
    """INV-8: RECOGNISED_FIELDS is exactly the five names §4.2 lists, in that
    order, and Entry's field names are exactly the set §4.1 lists.

    Stated as the whole set rather than as "no extra field": that form passes
    against every file that happens not to have one, so only a rule about the
    set itself fails when a sixth is added. Breaks when someone adds a field,
    which changes the file format three other items bind to and which the 1.0
    promise says stays readable for ever (§2).

    This test passes against the stub by design (§7)."""
    assert tuple(RECOGNISED_FIELDS) == _RECOGNISED_FIELDS, (
        f"RECOGNISED_FIELDS is {tuple(RECOGNISED_FIELDS)!r}, not §4.2's five "
        f"names in order {_RECOGNISED_FIELDS!r}"
    )
    actual = {field.name for field in dataclasses.fields(Entry)}
    assert actual == _ENTRY_FIELDS, (
        f"Entry's fields are {sorted(actual)!r}, not §4.1's set "
        f"{sorted(_ENTRY_FIELDS)!r}"
    )


# --------------------------------------------------------------- INV-9 ----


def test_a_value_that_would_break_the_format_is_refused(tmp_path):
    """INV-9: a value the format or the file system cannot carry is refused
    with StoreError and NOTHING IS WRITTEN.

    The written-nothing half is the load-bearing one: raising after a partial
    write leaves a file the next read cannot parse, so every case below asserts
    the folder is byte-for-byte unchanged afterwards.

    Date needs no case -- it is a datetime, so the type refuses what this rule
    would. The last case is the opposite direction and is what stops the rule
    being widened into one Import cannot satisfy: a comma in a TITLE is
    ordinary, the header runs to the end of the line, and archive titles carry
    commas.

    Breaks when an implementer writes the value anyway, which splits a category
    on the next read or writes a file outside the folder the Store was handed."""
    (tmp_path / _PUBLISHED).mkdir()
    (tmp_path / _DRAFTS).mkdir()
    (tmp_path / _PUBLISHED / ("an-example" + _SUFFIX)).write_text(
        _WITH_AN_UNKNOWN_FIELD, encoding="utf-8"
    )
    before = _snapshot(tmp_path)

    refused = {
        # A newline in each of the four string-valued header fields ...
        "newline in title": _entry(title="Two\nlines"),
        "newline in slug": _entry(slug="two\nlines"),
        "newline in a category": _entry(categories=("po\netry",)),
        "newline in a tag": _entry(tags=("one", "t\nwo")),
        # ... and in an unrecognised one, which §4.2 reaches deliberately:
        # writing back a field the next read cannot parse breaks ADR-0001's
        # promise in the act of keeping it.
        "newline in an extra field's value": _entry(extra=(("X-Note", "two\nlines"),)),
        "newline in an extra field's name": _entry(extra=(("X-\nNote", "one line"),)),
        # A comma in the two list fields, which the next read would split.
        "comma in a category": _entry(categories=("poetry, prose",)),
        "comma in a tag": _entry(tags=("one, two",)),
        # A slug outside a-z, 0-9 and -, the empty slug included. Unpinned,
        # a slug writes outside the handed folder (§4.2).
        "slug with a path separator": _entry(slug="../escape"),
        "slug with an upper-case letter": _entry(slug="An-Example"),
        "empty slug": _entry(slug=""),
    }

    failures: list[str] = []
    for case, entry in refused.items():
        try:
            write(tmp_path, entry, draft=False)
        except StoreError:
            pass
        except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
            failures.append(
                f"{case}: write() raised {exc!r}; expected StoreError"
            )
        else:
            failures.append(
                f"{case}: write() accepted the value; expected StoreError"
            )
        after = _snapshot(tmp_path)
        if after != before:
            failures.append(
                f"{case}: the folder changed although the value was refused. "
                f"Expected {sorted(before)!r} with unchanged bytes, got "
                f"{sorted(after)!r}"
            )
    assert not failures, "INV-9 breaches:\n" + "\n".join(failures)

    # The positive case. A comma in a title is written unchanged.
    with_a_comma = _entry(slug="comma-title", title="Yes, a comma")
    written = Path(write(tmp_path, with_a_comma, draft=False))
    assert read(written).title == with_a_comma.title, (
        f"a title carrying a comma did not survive a round trip. Expected "
        f"{with_a_comma.title!r}, got {read(written).title!r}"
    )


# -------------------------------------------------------------- INV-10 ----


def test_a_move_never_overwrites(tmp_path):
    """INV-10: neither publish nor unpublish overwrites a file at its
    destination: given a slug held in both folders, each raises SlugInUse,
    moves nothing, and leaves both files byte-identical.

    Comparing BOTH files' bytes before and after is what makes it bite:
    asserting the exception alone passes against an implementation that raises
    after moving, and the entry at the destination is then already gone.

    Breaks when a move is written as os.replace, which is what §4.5 prescribes
    for write and is silent about a destination that exists. §3 decision 5's
    Store-wide uniqueness rule is what this enforces at the one place the Store
    can see a collision."""
    slug = "held-in-both"
    as_draft = Path(write(tmp_path, _entry(slug=slug, body="The draft body.\n"), draft=True))
    as_published = Path(
        write(tmp_path, _entry(slug=slug, body="The published body.\n"), draft=False)
    )
    draft_before = as_draft.read_bytes()
    published_before = as_published.read_bytes()
    assert draft_before != published_before, (
        "the fixture's two files are identical, so a move that overwrote one "
        "with the other would leave no trace -- this test would prove nothing"
    )

    for direction, move in (("publish", publish), ("unpublish", unpublish)):
        with pytest.raises(SlugInUse):
            move(tmp_path, slug)
        assert as_draft.exists(), (
            f"{direction}() removed the drafts file although the destination "
            f"was occupied (§6). Expected {as_draft!r} to still be there"
        )
        assert as_published.exists(), (
            f"{direction}() removed the published file although the "
            f"destination was occupied (§6). Expected {as_published!r} to "
            f"still be there"
        )
        assert as_draft.read_bytes() == draft_before, (
            f"{direction}() altered the drafts file. Expected "
            f"{draft_before!r}, got {as_draft.read_bytes()!r}"
        )
        assert as_published.read_bytes() == published_before, (
            f"{direction}() altered the published file. Expected "
            f"{published_before!r}, got {as_published.read_bytes()!r}"
        )
