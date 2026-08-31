# INV-5 for PRESS-0004 (Marks) — the archive conformance run.
#
# Why this exists: render() must be byte-identical to today's live
# generator for every raw-text entry, or migrating loses or reshapes real
# writing. docs/specs/PRESS-0004-marks.md §5/§7 name this test and its
# skip condition; §10 is the map from invariant to test.
#
# This file names no person, no site and no domain — only "the writer" and
# "the archive" — per this repository's own CLAUDE.md § This repository is
# PUBLIC.
"""INV-5: render() matches today's wpautop() for every raw-text entry.

Where the oracle comes from
----------------------------
`wpautop()`, and the raw-text/Gutenberg/classic-HTML classification
`render_body()` makes before calling it, live in a sibling PRIVATE
workspace's `tools/build_blog.py` — today's generator, not part of
Pressless and not part of this repository. It is loaded here by file
path rather than by package import, because it sits outside `src/` and
is never installed; nothing from it is copied into this file.

That module will not exist on any other machine or in CI, so this test
is skipped, cleanly, in two independent cases: PRESSLESS_ARCHIVE unset
(no export to check), and the sibling module unreachable (no oracle to
check against). Neither case is an error — both are the expected state
everywhere except the maintainer's own machine.

Nothing from the archive itself — no post text, no commenter name, no
email address, no IP address — is written into this file, a fixture, or
a report. It is read at run time only, from a path outside this
repository, exactly as the personal-data section of this project's
CLAUDE.md requires.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pressless.marks import render

PRESSLESS_ARCHIVE = os.environ.get("PRESSLESS_ARCHIVE")

pytestmark = pytest.mark.archive


def _exec_module(spec, module) -> bool:
    """Run a module loaded by path. Any failure means "no oracle on this
    machine", which is a skip rather than a test failure."""
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 -- any failure here means "no oracle", not a test failure
        return False
    return True


def _load_build_blog():
    """Load the sibling generator by path. Returns None where it is not
    on this machine, so the caller can skip rather than error.

    The workspace holding it is found relatively and never named: its
    directory name does not belong in a public repository. Both shapes are
    tried, because the generator may sit beside this repository or inside a
    sibling workspace one level down.
    """
    siblings = Path(__file__).resolve().parents[2]
    candidates = sorted(siblings.glob("tools/build_blog.py"))
    candidates += sorted(siblings.glob("*/tools/build_blog.py"))
    for module_path in candidates:
        spec = importlib.util.spec_from_file_location("press_test_build_blog_oracle", module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        loaded = _exec_module(spec, module)
        sys.modules.pop("press_test_build_blog_oracle", None)
        if not loaded:
            continue
        if (
            callable(getattr(module, "wpautop", None))
            and isinstance(getattr(module, "NS", None), dict)
            and getattr(module, "HAS_TAGS", None) is not None
        ):
            return module
    return None


def _import_population(channel: ET.Element, ns: dict) -> list[str]:
    """Every raw entry body Import carries: published, draft and private,
    never trashed — the same population design.md § What Import brings
    across names, and the one INV-5's own text pins (spec §2)."""
    keep_status = {"publish", "draft", "private"}
    bodies = []
    for item in channel.findall("item"):
        if item.findtext("wp:post_type", "", ns) != "post":
            continue
        if item.findtext("wp:status", "", ns) not in keep_status:
            continue
        bodies.append(item.findtext("content:encoded", "", ns) or "")
    return bodies


def _raw_text_only(bodies: list[str], has_tags) -> list[str]:
    """The population INV-5 makes a claim about: whichever of the three
    source shapes render_body() itself would call wpautop() on. Gutenberg
    and classic-HTML entries are excluded — spec §9 says this invariant
    makes no claim about them."""
    raw = []
    for body in bodies:
        if "<!-- wp:" in body:
            continue
        if has_tags.search(body):
            continue
        raw.append(body)
    return raw


# --- INV-5's two divergence sets -------------------------------------
#
# render() is NOT wpautop(). Two inputs tell them apart, and the archive
# contains neither -- which is a fact about the data, not a property of
# the code, so it is asserted rather than assumed (spec INV-5).
#
# Both detectors are written from the spec's own rules and touch
# pressless.marks not at all: a parser that is broken in exactly the way
# INV-5 exists to catch must not also be the thing deciding whether
# there was anything to catch.

_CHAR_REF = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{0,30};|#[0-9]{1,7};|#[xX][0-9A-Fa-f]{1,6};)")


def _has_bare_amp(body: str) -> bool:
    """An '&' that does not already begin a character reference. Marks
    escapes it to '&amp;'; wpautop() leaves it alone (spec §4.6)."""
    return any(not _CHAR_REF.match(body, m.start()) for m in re.finditer(r"&", body))


def _forms_a_mark(body: str) -> bool:
    """Whether any line could form a complete mark, so render() would
    produce markup where wpautop() emits the characters.

    Deliberately conservative -- it may say yes where the parser would
    say no, and a false positive costs a look while a false negative
    costs the invariant. Any brace at all counts, since every brace mark
    opens with one and the archive has no brace in it; asterisks need
    §4.5's adjacency rule, since unpaired ones are common in the writing
    (INV-2's own fixtures)."""
    for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if "{" in line:
            return True
        for delim in ("**", "*"):
            start = 0
            while (i := line.find(delim, start)) >= 0:
                rest = line[i + len(delim):]
                # §4.5: an opener is not followed by a space, nor by
                # another asterisk; its closer is not preceded by either.
                if rest and not rest[0].isspace() and rest[0] != "*":
                    j = rest.find(delim)
                    if j > 0 and not rest[j - 1].isspace() and rest[j - 1] != "*":
                        return True
                start = i + 1
    return False


def _harmless_photo_src(name: str) -> str:
    # Raw archive text predates {photo: ...} syntax, so this should never
    # actually be called; returning the name unchanged keeps a genuine
    # (surprising) call from crashing the run instead of being reported as
    # a mismatch, which is the more honest failure mode.
    return name


@pytest.mark.skipif(
    not PRESSLESS_ARCHIVE,
    reason="PRESS-0004: set PRESSLESS_ARCHIVE to a WordPress export path to run this",
)
def test_matches_wpautop():
    """INV-5: for every raw-text entry in the archive, render() produces
    output byte-identical to today's tools/build_blog.py::wpautop().

    Breaks when any escaping or paragraph rule changes; this is the proof
    of the migration's S2 rather than a claim about it (spec §5)."""
    build_blog = _load_build_blog()
    if build_blog is None:
        pytest.skip(
            "PRESS-0004: ../tools/build_blog.py is not reachable on this "
            "machine — it lives in a private sibling workspace, not in "
            "this repository, and this test has nothing to compare against"
        )

    xml_path = Path(PRESSLESS_ARCHIVE)
    assert xml_path.is_file(), f"PRESSLESS_ARCHIVE does not name a file: {xml_path}"

    channel = ET.parse(xml_path).getroot().find("channel")
    assert channel is not None, f"{xml_path} has no <channel> — not a WXR export?"

    all_bodies = _import_population(channel, build_blog.NS)
    bodies = _raw_text_only(all_bodies, build_blog.HAS_TAGS)
    assert bodies, f"found no raw-text entries among {len(all_bodies)} in {xml_path}"

    # INV-5's preconditions, checked before any comparison so a changed
    # archive and a broken renderer cannot arrive as the same failure.
    bare_amp = [b for b in bodies if _has_bare_amp(b)]
    with_marks = [b for b in bodies if _forms_a_mark(b)]
    print(f"entries with a bare '&' (Marks escapes, wpautop does not): {len(bare_amp)}")
    print(f"entries forming a complete mark (Marks renders, wpautop does not): {len(with_marks)}")

    assert not bare_amp, (
        f"{len(bare_amp)}/{len(bodies)} raw-text entries carry a bare '&'. "
        f"render() escapes it and wpautop() does not, so byte-identity "
        f"cannot hold and INV-5 needs a decision, not a fix: this is new "
        f"source material, not a fault in Marks. First one starts "
        f"{bare_amp[0][:60]!r}"
    )
    assert not with_marks, (
        f"{len(with_marks)}/{len(bodies)} raw-text entries form a complete "
        f"mark. render() turns it into markup and wpautop() emits the "
        f"characters, so byte-identity cannot hold. Same decision as "
        f"above: the archive changed, Marks did not. First one starts "
        f"{with_marks[0][:60]!r}"
    )

    mismatches = []
    for raw in bodies:
        expected = build_blog.wpautop(raw)
        actual = render(raw, _harmless_photo_src)
        if actual != expected:
            mismatches.append((raw, expected, actual))

    # §2's figures, printed rather than transcribed into prose that ages
    # (this project's CLAUDE.md § How documents get written here).
    print(f"entries in the Import population (published+draft+private): {len(all_bodies)}")
    print(f"raw-text entries checked against wpautop(): {len(bodies)}")
    print(f"  containing '*':        {sum(1 for b in bodies if '*' in b)}")
    print(f"  containing '&':        {sum(1 for b in bodies if '&' in b)}")
    print(f"  containing '<' or '>': {sum(1 for b in bodies if '<' in b or '>' in b)}")
    print(f"mismatches against wpautop(): {len(mismatches)}")

    if mismatches:
        raw, expected, actual = mismatches[0]
        raise AssertionError(
            f"{len(mismatches)}/{len(bodies)} raw-text entries diverge from "
            f"wpautop(). First mismatch, body starting {raw[:60]!r}:\n"
            f"  expected: {expected!r}\n"
            f"  actual:   {actual!r}"
        )
