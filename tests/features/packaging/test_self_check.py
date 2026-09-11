# INV-6 for PRESS-0022: the built artefact resolves a real credential store on
# a machine that has one.
#
# It needs a built artefact, so it is marked `packaging` and skipped cleanly
# without PRESSLESS_ARTEFACT -- the way `archive` works for the export (§ 7).
#
# The release job runs it UNDER A SESSION THE JOB CREATES (§ 7 step 3), never
# conditioned on a store happening to be there: `store: file` is what a machine
# with no store and a bundle that lost keyring's metadata both report, so a
# skip keyed on "no store present" would be keyed on the very failure this
# exists to catch.
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.packaging


@pytest.fixture
def artefact() -> Path:
    named = os.environ.get("PRESSLESS_ARTEFACT")
    if not named:
        pytest.skip("no built artefact: set PRESSLESS_ARTEFACT to run INV-6")
    path = Path(named)
    assert path.is_file(), "PRESSLESS_ARTEFACT names no file"
    return path


def test_the_artefact_resolves_a_real_store(artefact):
    """INV-6: the STORE KIND is keyring, not merely some member name.

    PRESS-0002 § 4.2 turns NoKeyringError into Choice("file", "file") off
    Windows, which names a member and raises nothing -- so reading the member
    alone passes green against exactly the metadata-less bundle § 2 calls the
    worse and quieter case."""
    run = subprocess.run(  # noqa: S603 -- the artefact under test, by design
        [str(artefact), "--self-check"],
        capture_output=True, text=True, timeout=120, check=False,
    )
    lines = run.stdout.splitlines()
    assert run.returncode == 0, f"the self-check failed: {run.stdout!r} {run.stderr!r}"
    assert lines[0] == "pressless: ok", lines
    assert lines[1] == "folder: Pressless-data", lines
    kind, _, member = lines[2].removeprefix("store: ").partition(" ")
    assert kind == "keyring", (
        f"the bundle answered {lines[2]!r} where a store exists: keyring's "
        f"entry-point metadata is missing from it (§ 4.3)"
    )
    assert member, f"no member named: {lines[2]!r}"
