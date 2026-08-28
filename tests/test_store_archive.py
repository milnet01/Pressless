# PRESS-0005 §7 — the Store's archive conformance run.
#
# Why this exists: every entry the writer has must survive being written to a
# file and read back unchanged, or migrating loses or reshapes real writing.
# docs/specs/PRESS-0005-store.md §7 names this test and its skip condition;
# §10 says what it proves and what it does not.
#
# This file names no person, no site and no domain — only "the writer" and
# "the archive" — per this repository's own CLAUDE.md § This repository is
# PUBLIC.
"""§7: the whole archive, written through the Store and read back.

Population
----------
Everything Import brings: the published entries AND the drafts and private
posts, which arrive as drafts. Not the published alone — §3 decision 5's
uniqueness rule spans the whole Store, so a measurement over one folder
would not test it (§7).

Where the slug rule comes from
------------------------------
§3 decision 4 names ONE place that resolves a slug: `safe_slug` in a
sibling PRIVATE workspace's `tools/build_blog.py` — today's generator, not
part of Pressless and not part of this repository — with a fallback to the
WordPress post id where nothing survives. It is loaded here by file path at
run time rather than by import, because it sits outside `src/` and is never
installed. Nothing from it is copied into this file: a copy would be the
second deciding place decision 4 exists to prevent.

That module will not exist on any other machine or in CI, so this test is
skipped, cleanly, in two independent cases: PRESSLESS_ARCHIVE unset (no
export to write), and the sibling module unreachable (no slug rule).
Neither is an error — both are the expected state everywhere except the
maintainer's own machine.

Measurements, not prose
-----------------------
§7 has this test print the archive figures the spec relies on rather than
transcribe them into text that ages. Slug and path LENGTHS are printed, not
the slugs themselves: a slug is the writer's own words, and a passing run's
output is not a place for them. A failing assertion does name the entry it
failed on, because otherwise the failure is not diagnosable.

Nothing from the archive — no post text, no commenter name, no email
address, no IP address — is written into this file, a fixture, or a report.
It is read at run time only, from a path outside this repository, exactly as
the personal-data section of this project's CLAUDE.md requires.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
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
    reason="PRESS-0005: set PRESSLESS_ARCHIVE to a WordPress export path to run this",
)

# §4.2: a slug is one or more of a-z, 0-9 and '-', and nothing else.
LEGAL_SLUG = re.compile(r"[a-z0-9-]+\Z")

# §6's failure mode: a slug whose file name the platform cannot hold. Windows
# refuses a path over 260 characters unless long paths are enabled, and the
# path is Pressless's own folder plus what the Store adds to it — so what this
# run can measure is the Store's part, and the budget the writer's folder has
# left. Printed rather than asserted: where Pressless sits is the writer's
# choice, and §10 records that nothing here runs on Windows.
WINDOWS_PATH_LIMIT = 260

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _exec_module(spec, module) -> bool:
    """Run a module loaded by path. Any failure means "no slug rule on this
    machine", which is a skip rather than a test failure."""
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 -- any failure here means "no rule", not a test failure
        return False
    return True


def _load_slug_rule():
    """Load §3 decision 4's slug rule from the sibling generator, by path.

    Returns (safe_slug, namespaces), or None where the generator is not on
    this machine, so the caller can skip rather than error. The workspace is
    found relatively and never named: its directory name does not belong in a
    public repository.
    """
    siblings = Path(__file__).resolve().parents[2]
    candidates = sorted(siblings.glob("tools/build_blog.py"))
    candidates += sorted(siblings.glob("*/tools/build_blog.py"))
    for module_path in candidates:
        spec = importlib.util.spec_from_file_location("press_test_slug_rule", module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        loaded = _exec_module(spec, module)
        sys.modules.pop("press_test_slug_rule", None)
        if not loaded:
            continue
        safe_slug = getattr(module, "safe_slug", None)
        namespaces = getattr(module, "NS", None)
        if callable(safe_slug) and isinstance(namespaces, dict):
            return safe_slug, namespaces
    return None


def _open_archive(namespaces):
    """The export's <channel>, or a failure naming the path."""
    xml_path = Path(PRESSLESS_ARCHIVE)
    assert xml_path.is_file(), f"PRESSLESS_ARCHIVE does not name a file: {xml_path}"
    channel = ET.parse(xml_path).getroot().find("channel")
    assert channel is not None, f"{xml_path} has no <channel> — not a WXR export?"
    return channel


def _import_population(channel, namespaces, safe_slug):
    """Every entry Import brings, as (Entry, draft, gave_its_own_slug).

    Published, draft and private post items, never trashed — the population
    `docs/design.md` § What may depend on what names and §7 pins. A published
    item is written with draft=False; a draft or private one with draft=True,
    which is how they arrive.
    """
    keep_status = {"publish", "draft", "private"}
    population = []
    for item in channel.findall("item"):
        if item.findtext("wp:post_type", "", namespaces) != "post":
            continue
        status = item.findtext("wp:status", "", namespaces)
        if status not in keep_status:
            continue

        raw_slug = (item.findtext("wp:post_name", "", namespaces) or "").strip()
        post_id = str(item.findtext("wp:post_id", "0", namespaces) or "0")
        # §3 decision 4, exactly as the live addresses were made: the rule,
        # then the post id where nothing of the raw slug survives.
        slug = safe_slug(raw_slug) or post_id

        categories, tags = [], []
        for term in item.findall("category"):
            nicename = term.get("nicename")
            if not nicename:
                continue
            if term.get("domain") == "category":
                categories.append(nicename)
            elif term.get("domain") == "post_tag":
                tags.append(nicename)

        # The export carries local wall-clock time with no zone, and §4.1's
        # Date field is that same naive datetime — an offset the archive does
        # not have would be invented here, not preserved.
        raw_date = item.findtext("wp:post_date", "", namespaces)
        date = datetime.strptime(raw_date, DATE_FORMAT)  # noqa: DTZ007

        entry = store.Entry(
            slug=slug,
            title=(item.findtext("title") or "").strip(),
            date=date,
            categories=tuple(categories),
            tags=tuple(tags),
            body=item.findtext("content:encoded", "", namespaces) or "",
            extra=(),
        )
        population.append((entry, status != "publish", bool(safe_slug(raw_slug))))
    return population


def _archive_population():
    """The population, or a clean skip where either half is missing."""
    rule = _load_slug_rule()
    if rule is None:
        pytest.skip(
            "PRESS-0005: ../tools/build_blog.py is not reachable on this "
            "machine — it lives in a private sibling workspace, not in this "
            "repository, and §3 decision 4's slug rule lives in it"
        )
    safe_slug, namespaces = rule
    population = _import_population(_open_archive(namespaces), namespaces, safe_slug)
    assert population, f"found no published, draft or private posts in {PRESSLESS_ARCHIVE}"
    return population


def _first_difference(expected: str, actual: str) -> str:
    """Where two bodies first diverge, as an offset and a short window —
    enough to diagnose without printing an entry into the log."""
    for i, (a, b) in enumerate(zip(expected, actual)):
        if a != b:
            return f"offset {i}: expected {expected[i:i + 40]!r}, actual {actual[i:i + 40]!r}"
    shorter, longer = sorted((expected, actual), key=len)
    return (
        f"identical for {len(shorter)} characters, then one ends: "
        f"expected {len(expected)} characters, actual {len(actual)}; "
        f"the extra text starts {longer[len(shorter):len(shorter) + 40]!r}"
    )


@needs_archive
def test_the_archive_resolves_to_slugs_the_store_can_hold():
    """§7's measurements, and §4.2's rule about what a slug may contain.

    Every entry Import brings must resolve to a non-empty slug of a-z, 0-9
    and '-' — the Store refuses anything else (INV-9), so a single archive
    entry outside that set stops the import this spec exists to enable.
    """
    population = _archive_population()

    entries = [entry for entry, _draft, _own in population]
    drafts = [entry for entry, draft, _own in population if draft]
    untitled = [entry for entry in entries if not entry.title]
    no_slug_of_their_own = [entry for entry, _draft, own in population if not own]
    days = Counter(entry.date.date() for entry in entries)
    sharing_a_day = sum(count for count in days.values() if count > 1)
    longest = max(entries, key=lambda entry: len(entry.slug))
    store_relative = f"{store.PUBLISHED_FOLDER}/{longest.slug}{store.FILE_SUFFIX}"

    # §7: these figures are evidence, they move, and this is where they live.
    print(f"entries Import brings (published + draft + private): {len(entries)}")
    print(f"  written as drafts (draft + private):               {len(drafts)}")
    print(f"  carrying no title:                                 {len(untitled)}")
    print(f"  carrying no slug of their own (post id used):      {len(no_slug_of_their_own)}")
    print(f"  sharing a day with another entry:                  {sharing_a_day}")
    print(f"distinct days: {len(days)}")
    print(f"longest slug: {len(longest.slug)} characters")
    print(f"longest path the Store adds to its folder: {len(store_relative)} characters")
    print(
        f"  leaves {WINDOWS_PATH_LIMIT - len(store_relative)} characters for the path to "
        f"Pressless's own folder before Windows' {WINDOWS_PATH_LIMIT}-character limit (§6)"
    )

    illegal = [entry.slug for entry in entries if not LEGAL_SLUG.match(entry.slug)]
    assert not illegal, (
        f"{len(illegal)}/{len(entries)} entries resolve to a slug outside §4.2's "
        f"set (a-z, 0-9, '-', non-empty), which the Store refuses (INV-9). "
        f"Expected every resolved slug to match {LEGAL_SLUG.pattern!r}; "
        f"first offender: {illegal[0]!r}"
    )


@needs_archive
def test_no_two_entries_want_one_slug_in_one_folder():
    """The collision the Store itself loses an entry to.

    `write` is create-or-replace within its own folder (§4.1), so two
    entries resolving to one slug in ONE folder means the second silently
    replaces the first, and the round trip is short by one.

    §3 decision 5's uniqueness is Store-wide, and the Store enforces only
    the half it can see: across the two folders nothing is overwritten, so
    both files survive and no test here can fail on it. That half is
    Import's to stop on (§10), so it is reported rather than asserted.
    """
    population = _archive_population()
    per_folder = Counter((draft, entry.slug) for entry, draft, _own in population)
    store_wide = Counter(entry.slug for entry, _draft, _own in population)

    lost = {slug: count for (_draft, slug), count in per_folder.items() if count > 1}
    shared = sorted(slug for slug, count in store_wide.items() if count > 1)

    print(f"entries: {sum(store_wide.values())}; distinct slugs: {len(store_wide)}")
    print(f"slugs two entries in ONE folder want (the Store loses one): {len(lost)}")
    print(f"slugs wanted across BOTH folders (nothing lost here): {len(shared)}")
    for slug in shared:
        print(f"  {slug!r} — breaches §3 decision 5; PRESS-0007 decides which keeps it")

    assert not lost, (
        f"two entries in one folder resolve to one slug, so writing the "
        f"second replaces the first and an entry is lost. Expected 0, actual "
        f"{len(lost)} of {len(store_wide)}: "
        + ", ".join(f"{slug!r} wanted by {count}" for slug, count in sorted(lost.items()))
    )


@needs_archive
def test_the_archive_survives_a_round_trip(tmp_path):
    """§7: write every entry through the Store, read them all back, and
    assert nothing changed — body byte-for-byte (S2), title, date,
    categories, tags.

    Breaks when the format loses or reshapes anything the archive actually
    contains. §10: this proves the Store keeps what it was handed, and
    nothing about what Import hands it.
    """
    population = _archive_population()

    folder = tmp_path / "pressless"
    folder.mkdir()  # §6: the handed folder must exist; published/ and drafts/ need not

    written = []
    for entry, draft, _own in population:
        path = store.write(folder, entry, draft=draft)
        written.append((entry, draft, path))

    for entry, _draft, path in written:
        assert path.is_file(), (
            f"write() returned {path} for slug {entry.slug!r}, which is not a file"
        )

    published = store.list_slugs(folder, draft=False)
    drafts_held = store.list_slugs(folder, draft=True)
    longest = max(len(str(path)) for _entry, _draft, path in written)
    print(f"entries written: {len(written)}; longest path written: {longest} characters")
    print(f"published: {len(published)}")
    print(f"drafts:    {len(drafts_held)}")

    collected = len(published) + len(drafts_held)
    assert collected == len(population), (
        f"the Store holds a different number of entries than were written. "
        f"Expected {len(population)}, actual {collected} — an entry was lost, "
        f"which is what a slug collision (§3 decision 5) looks like from here"
    )

    mismatches = []
    for entry, _draft, path in written:
        back = store.read(path)
        for field in ("slug", "title", "date", "categories", "tags"):
            expected, actual = getattr(entry, field), getattr(back, field)
            if expected != actual:
                mismatches.append((entry.slug, field, repr(expected), repr(actual)))
        if back.body != entry.body:
            where = _first_difference(entry.body, back.body)
            mismatches.append((entry.slug, "body", "verbatim, byte for byte", where))

    print(f"entries read back: {len(written)}; fields that changed: {len(mismatches)}")

    if mismatches:
        slug, field, expected, actual = mismatches[0]
        raise AssertionError(
            f"{len(mismatches)} field(s) changed across a write/read round trip "
            f"of {len(written)} entries. First: entry {slug!r}, field {field!r}\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}"
        )
