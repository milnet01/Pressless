"""What scripts/windows-gate.sh sends to the Windows box (PRESS-0325).

The script runs in a throwaway repository of its own, with `scp` and `ssh`
replaced by stand-ins on PATH: `scp` keeps what it is given, `ssh` answers
as a suite that passed. No machine is reached.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_BASH = shutil.which("bash")
_GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(sys.platform == "win32" or _BASH is None or _GIT is None,
                                reason="the gate script runs under bash, with git, on Linux")


def _repository(root: Path) -> None:
    (root / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "windows-gate.sh", root / "scripts")
    shutil.copy(ROOT / "pyproject.toml", root)
    (root / "kept.txt").write_text("kept\n", encoding="utf-8")
    (root / "removed.txt").write_text("removed\n", encoding="utf-8")
    for command in (["init", "-q"], ["add", "."],
                    ["-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                     "commit", "-q", "-m", "start"]):
        subprocess.run([_GIT, *command], cwd=root, check=True)  # noqa: S603 -- fixed arguments


def _stand_ins(bin_dir: Path, kept: Path) -> None:
    bin_dir.mkdir()
    (bin_dir / "scp").write_text(
        "#!/usr/bin/env bash\n"
        "args=()\n"
        "for a; do [[ $a == -* || $a == ConnectTimeout=* ]] || args+=(\"$a\"); done\n"
        f"cp \"${{args[@]:0:${{#args[@]}}-1}}\" '{kept}'\n", encoding="utf-8")
    (bin_dir / "ssh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for name in ("scp", "ssh"):
        (bin_dir / name).chmod(0o755)


def test_a_tracked_file_deleted_but_not_staged_does_not_fail_the_gate(tmp_path: Path):
    """Breaks when the zip step reads every name ls-files lists, and a file
    deleted from disk but not staged fails the gate as if the suite had."""
    repo, kept = tmp_path / "repo", tmp_path / "sent"
    _repository(repo)
    kept.mkdir()
    _stand_ins(tmp_path / "bin", kept)
    (repo / "removed.txt").unlink()
    env = {"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path)}
    ran = subprocess.run([_BASH, "scripts/windows-gate.sh", "box"], cwd=repo, env=env,  # noqa: S603
                         capture_output=True, text=True, timeout=60, check=False)
    assert ran.returncode == 0, ran.stderr
    sent = next(kept.glob("*.zip"))
    with zipfile.ZipFile(sent) as archive:
        names = set(archive.namelist())
    assert "kept.txt" in names
    assert "removed.txt" not in names
