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


def test_an_unknown_option_is_refused_before_anything_runs(tmp_path):
    """PRESS-0300. Breaks when the gate takes a mistyped option, `--doc` for
    `--docs`, as no option, and runs the whole gate instead of refusing.

    A Python that refuses to run is first on PATH, so a regression stops at
    the gate's interpreter step rather than running the suite from inside it.
    """
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    for name in ("python3", "python"):
        (stand_ins / name).write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (stand_ins / name).chmod(0o755)
    ran = subprocess.run([_BASH, str(_SCRIPT), "--doc"],  # noqa: S603 -- this repository's own gate
                         env={"PATH": f"{stand_ins}:/usr/bin:/bin", "HOME": str(tmp_path)},
                         capture_output=True, text=True, timeout=120, check=False)
    assert ran.returncode == 1
    assert "unknown option --doc" in ran.stderr
    assert "=== " not in ran.stdout


def _gate_in_a_scratch_repository(tmp_path: Path, env: dict[str, str]) -> tuple[Path, str]:
    """The real gate script, run in a throwaway repository with a stand-in for
    Python that records each call and answers yes. Returns the repository and
    the record."""
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    for name in ("local-ci.sh", "python.sh"):
        shutil.copy(_SCRIPT.parent / name, repository / "scripts" / name)
    (repository / "pyproject.toml").write_text("", encoding="utf-8")
    record = tmp_path / "record.txt"
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    # `-m venv <where>` makes <where>/bin/python, the stand-in again.
    python = (f'#!/bin/sh\necho "$0 $*" >> "{record}"\n'
              'if [ "$1 $2" = "-m venv" ]; then mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; fi\n')
    (stand_ins / "python3").write_text(python, encoding="utf-8")
    (stand_ins / "python3").chmod(0o755)
    environment = {"PATH": f"{stand_ins}:/usr/bin:/bin", "HOME": str(tmp_path),
                   "GIT_CONFIG_NOSYSTEM": "1", **env}
    identity = ["-c", "user.name=gate", "-c", "user.email=gate@example.invalid"]
    git = shutil.which("git")
    for arguments in (["init", "-q"], ["add", "."], [*identity, "commit", "-qm", "scratch"]):
        subprocess.run([git, *arguments], cwd=repository, env=environment,  # noqa: S603 -- a scratch repository
                       check=True, capture_output=True)
    ran = subprocess.run([_BASH, str(repository / "scripts" / "local-ci.sh")],  # noqa: S603 -- this repository's own gate
                         env=environment, capture_output=True, text=True, timeout=120, check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    return repository, record.read_text(encoding="utf-8")


def test_a_local_run_uses_the_versions_github_would_install(tmp_path):
    """A local run brings its own environment up to what a fresh install
    resolves today, and runs ruff and pytest from it.

    Breaks when the gate runs whatever this machine last installed, so it can
    pass what GitHub then fails."""
    repository, record = _gate_in_a_scratch_repository(tmp_path, {})
    assert "-m venv .venv" in record
    own = next(line for line in record.splitlines() if "pip install" in line)
    assert own.split()[0].endswith(".venv/bin/python")
    assert "--upgrade --upgrade-strategy eager -e .[dev]" in own
    for tool in ("-m ruff check src/ tests/", "-m pytest -ra"):
        line = next(line for line in record.splitlines() if tool in line)
        assert line.split()[0].endswith(".venv/bin/python"), line
    assert (repository / ".venv").is_dir()


def test_github_keeps_the_environment_it_installed(tmp_path):
    """On GitHub the workflow has just installed everything, and a second
    environment would only cost the run's time.

    Breaks when the gate makes .venv under CI too."""
    repository, record = _gate_in_a_scratch_repository(tmp_path, {"CI": "true"})
    assert "-m venv" not in record
    assert "pip install" not in record
    assert not (repository / ".venv").exists()
