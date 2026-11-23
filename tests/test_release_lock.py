"""A release installs only a hash-checked lock file (PRESS-0022 INV-9, INV-10).

The manifest holds floors, so two builds of one commit could bundle different
libraries. The release jobs therefore install packaging/release-requirements.txt,
exact versions with their hashes, and nothing else from pip (PRESS-0150).

Its last test runs the Linux job's Build step itself: a build that fails must
fail that step.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_LOCK = _ROOT / "packaging" / "release-requirements.txt"
_WORKFLOW = _ROOT / ".github" / "workflows" / "release.yml"
_INSTALL = "python -m pip install --require-hashes -r packaging/release-requirements.txt"


def _name(text: str) -> str:
    return re.sub(r"[-_.]+", "-", text).lower()


def _numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _locked() -> dict[str, tuple[str, int]]:
    """Each requirement's pinned version and how many hashes it carries."""
    locked: dict[str, tuple[str, int]] = {}
    current = None
    for line in _LOCK.read_text(encoding="utf-8").splitlines():
        head = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", line)
        if head:
            current = _name(head[1])
            locked[current] = (head[2], 0)
        elif current and "--hash=sha256:" in line:
            version, hashes = locked[current]
            locked[current] = (version, hashes + 1)
    return locked


def test_lock_covers_the_manifest():
    """Breaks when a dependency is added or its floor raised without
    regenerating the lock, or a hand edit drops a requirement's hashes."""
    with open(_ROOT / "pyproject.toml", "rb") as manifest:
        project = tomllib.load(manifest)["project"]
    wanted = [*project["dependencies"], *project["optional-dependencies"]["dev"],
              *project["optional-dependencies"]["packaging"]]
    locked = _locked()
    for requirement in wanted:
        # A marker (jeepney's "; sys_platform == 'linux'") limits where, not what.
        bare = requirement.split(";", 1)[0].strip()
        name, floor = re.fullmatch(r"([A-Za-z0-9._-]+)>=(\S+)", bare).groups()
        assert _name(name) in locked, f"{name} is not in the lock"
        version, _ = locked[_name(name)]
        assert _numbers(version) >= _numbers(floor), f"{name} {version} is below {floor}"
    for name, (_, hashes) in locked.items():
        assert hashes >= 1, f"{name} carries no hash"


def test_release_installs_only_the_lock():
    """Breaks when a job goes back to installing the project with its extras,
    or gains a second pip install that bypasses the hashes."""
    installs = [line.strip().removeprefix("run:").strip()
                for line in _WORKFLOW.read_text(encoding="utf-8").splitlines()
                if "pip install" in line]
    assert len(installs) == 2, installs  # the Linux job and the Windows job
    assert all(install == _INSTALL for install in installs), installs


# GitHub's documented commands for a step's shell on Linux: unnamed, and `bash`.
_SHELLS = {None: ["bash", "-e"], "bash": ["bash", "--noprofile", "--norc", "-eo", "pipefail"]}


def _linux_build_step() -> tuple[str | None, str]:
    """The Linux job's Build step: its `shell:` (or the job's default) and its script."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    job = re.search(r"^  linux:\n(.*?)(?=^  \S)", text, re.M | re.S).group(1)
    step = re.search(r"^      - name: Build\n(.*?)(?=^      - |\Z)", job, re.M | re.S).group(1)
    shell = re.search(r"^        shell: (\S+)", step, re.M) or re.search(
        r"^    defaults:\n      run:\n        shell: (\S+)", job, re.M)
    lines = []
    for line in step.split("        run: |\n", 1)[1].splitlines():
        if line.strip() and not line.startswith("          "):
            break  # the block ends where its indent does
        lines.append(line.removeprefix("          "))
    return (shell.group(1) if shell else None), "\n".join(lines) + "\n"


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                    reason="the Linux job's step runs under bash")
def test_a_failed_linux_build_fails_the_build_step(tmp_path: Path):
    """Breaks when the build's exit status is lost, as it is inside `echo
    "artefact=$(...)"` or a pipeline without pipefail, and Build goes green
    with an empty artefact."""
    shell, script = _linux_build_step()
    (tmp_path / "scripts").mkdir()
    build = tmp_path / "scripts" / "build-linux.sh"
    build.write_text("#!/bin/sh\necho building >&2\nexit 1\n", encoding="utf-8")
    build.chmod(0o755)
    (tmp_path / "step.sh").write_text(script, encoding="utf-8")
    output = tmp_path / "output.txt"
    env = {**os.environ, "GITHUB_OUTPUT": str(output), "RUNNER_TEMP": str(tmp_path)}
    ran = subprocess.run([*_SHELLS[shell], "step.sh"], cwd=tmp_path, env=env,  # noqa: S603 -- the workflow's own step
                         capture_output=True, text=True, timeout=60, check=False)
    assert ran.returncode != 0, (shell, script)
    assert "building" in ran.stderr
