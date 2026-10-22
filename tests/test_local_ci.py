"""The gate's --sweep option (PRESS-0277): the leak pattern over named files.

A review packet sits outside the tree, so the tree, commit and ref sweeps
never read it. --sweep runs the script's own pattern over the files named,
and nothing else, so the pattern stays in one place.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "local-ci.sh"
_BASH = shutil.which("bash")

# Built here, so the tree sweep never meets the whole word in this file.
_NAMED = "Ch" + "arl"

# On Windows `bash` can resolve to WSL's, which sees none of this checkout.
pytestmark = pytest.mark.skipif(sys.platform == "win32" or _BASH is None,
                                reason="the gate script runs under bash on Linux and in CI")


def _sweep(*files: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([_BASH, str(_SCRIPT), "--sweep", *map(str, files)],  # noqa: S603 -- this repository's own gate
                          capture_output=True, text=True, timeout=120, check=False)


def test_a_named_file_naming_the_writer_fails(tmp_path):
    packet = tmp_path / "packet.md"
    packet.write_text(f"Plain words.\nA line by {_NAMED} here.\n", encoding="utf-8")
    ran = _sweep(packet)
    assert ran.returncode == 1
    assert "2:A line by" in ran.stderr
    assert f"{packet} names the writer" in ran.stderr


def test_a_clean_file_passes_and_nothing_else_runs(tmp_path):
    packet = tmp_path / "packet.md"
    packet.write_text("Plain words.\n", encoding="utf-8")
    ran = _sweep(packet)
    assert ran.returncode == 0, ran.stderr
    assert f"clean: {packet}" in ran.stdout
    assert "clean: tree" not in ran.stdout
    assert "=== ruff ===" not in ran.stdout


def test_every_file_named_is_swept(tmp_path):
    clean, named = tmp_path / "clean.md", tmp_path / "named.md"
    clean.write_text("Plain words.\n", encoding="utf-8")
    named.write_text(f"{_NAMED}\n", encoding="utf-8")
    ran = _sweep(clean, named)
    assert ran.returncode == 1
    assert f"{named} names the writer" in ran.stderr


def test_a_missing_file_fails_rather_than_passing(tmp_path):
    ran = _sweep(tmp_path / "absent.md")
    assert ran.returncode == 1
    assert "absent.md" in ran.stderr


def test_sweep_with_no_file_fails():
    ran = _sweep()
    assert ran.returncode == 1
    assert "--sweep" in ran.stderr
