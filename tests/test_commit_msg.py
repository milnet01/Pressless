"""The commit-msg hook's subject checks, run as git would on a message file."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "commit-msg"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(sys.platform == "win32" or _BASH is None,
                                reason="the hook runs under bash")


def _hook(tmp_path: Path, message: str) -> subprocess.CompletedProcess[str]:
    """In a folder with no ROADMAP.md, so `<component>: ` is the form."""
    (tmp_path / "MSG").write_text(message, encoding="utf-8")
    return subprocess.run([_BASH, str(_HOOK), "MSG"], cwd=tmp_path,  # noqa: S603 -- this repository's hook
                          env={"PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, timeout=60, check=False)


def test_a_subject_after_leading_blank_lines_is_checked(tmp_path):
    """Breaks when a message opening with a blank line reads as having no
    subject and passes: git strips that line, and the unchecked paragraph
    below becomes the subject."""
    ran = _hook(tmp_path, "\n\nhooks: a subject ending in a period.\n")
    assert ran.returncode == 1
    assert "ends with a period" in ran.stderr


def test_a_good_subject_after_a_blank_line_passes(tmp_path):
    """The control for the case above."""
    ran = _hook(tmp_path, "\nhooks: a subject that keeps the rules\n\nThe body.\n")
    assert ran.returncode == 0, ran.stderr
