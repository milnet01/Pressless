"""A release installs only a hash-checked lock file (PRESS-0022 INV-9, INV-10).

The manifest holds floors, so two builds of one commit could bundle different
libraries. The release jobs therefore install packaging/release-requirements.txt,
exact versions with their hashes, and nothing else from pip (PRESS-0150).
"""
from __future__ import annotations

import re
from pathlib import Path

import tomllib

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
        name, floor = re.fullmatch(r"([A-Za-z0-9._-]+)>=(\S+)", requirement).groups()
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
