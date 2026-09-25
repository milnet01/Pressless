"""No tracked file holds a private key (PRESS-0023 INV-18).

The pattern is assembled at run time, so this file does not match itself
(FIBR-0355), and nothing in the repository spells a key header out.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_HEADER = re.compile(("BEG" + "IN [A-Z ]*" + "PRI" + "VATE KEY").encode("ascii"))


def _tracked() -> list[Path]:
    git = shutil.which("git")
    if git is None or not (_ROOT / ".git").exists():
        pytest.skip("not a git checkout, so there is no tracked set to read")
    listed = subprocess.run([git, "ls-files", "-z"], cwd=_ROOT, check=True,  # noqa: S603
                            capture_output=True).stdout
    return [_ROOT / name for name in listed.decode("utf-8").split("\0") if name]


def test_no_tracked_file_holds_a_private_key():
    """Breaks when a key, or a fixture spelling one out, is committed."""
    # The pattern must be able to fire, or an empty result proves nothing.
    assert _HEADER.search(("-----" + "BEG" + "IN OPENSSH PRI" + "VATE KEY-----").encode())

    tracked = _tracked()
    assert tracked, "git listed no files, so nothing was checked"
    named = [str(p.relative_to(_ROOT)) for p in tracked if p.suffix == ".key"]
    assert not named, named
    holding = [str(p.relative_to(_ROOT)) for p in tracked
               if p.is_file() and _HEADER.search(p.read_bytes())]
    assert not holding, holding
