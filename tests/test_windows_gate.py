"""What scripts/windows-gate.sh sends to the Windows box (PRESS-0325).

The script runs in a throwaway repository of its own, with `scp` and `ssh`
replaced by stand-ins on PATH: `scp` keeps what it is given, `ssh` answers
as a suite that passed. No machine is reached.
"""
from __future__ import annotations

import re
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


def _git_env(home: Path) -> dict[str, str]:
    """No config from this machine: its signing or hooks path would act on the
    scratch repository's commits."""
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1"}


def _repository(root: Path) -> None:
    (root / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "windows-gate.sh", root / "scripts")
    shutil.copy(ROOT / "pyproject.toml", root)
    (root / "kept.txt").write_text("kept\n", encoding="utf-8")
    (root / "removed.txt").write_text("removed\n", encoding="utf-8")
    for command in (["init", "-q"], ["add", "."],
                    ["-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                     "commit", "-q", "-m", "start"]):
        subprocess.run([_GIT, *command], cwd=root, env=_git_env(root.parent),  # noqa: S603 -- fixed arguments
                       check=True)


def _stand_ins(bin_dir: Path, kept: Path, *, ssh_fails: str = "", scp_fails: str = "") -> None:
    """`ssh_fails` and `scp_fails` are what that command prints on stderr
    before exiting as it does on a failure: 255 for ssh, 1 for scp."""
    bin_dir.mkdir()
    scp = ("#!/usr/bin/env bash\n"
           "args=()\n"
           "for a; do [[ $a == -* || $a == ConnectTimeout=* ]] || args+=(\"$a\"); done\n"
           f"cp \"${{args[@]:0:${{#args[@]}}-1}}\" '{kept}'\n")
    if scp_fails:
        scp = f"#!/usr/bin/env bash\necho '{scp_fails}' >&2\nexit 1\n"
    ssh = f"#!/usr/bin/env bash\necho '{ssh_fails}' >&2\nexit 255\n" if ssh_fails else \
        "#!/usr/bin/env bash\nexit 0\n"
    (bin_dir / "scp").write_text(scp, encoding="utf-8")
    (bin_dir / "ssh").write_text(ssh, encoding="utf-8")
    for name in ("scp", "ssh"):
        (bin_dir / name).chmod(0o755)


def _gate(tmp_path: Path, change=None, given: tuple[str, ...] = (),
          **failing: str) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """The gate run against a stand-in box. `change` gets the repository
    first. Returns the run, the repository and the folder holding what scp
    was given."""
    repo, kept = tmp_path / "repo", tmp_path / "sent"
    _repository(repo)
    kept.mkdir()
    _stand_ins(tmp_path / "bin", kept, **failing)
    if change:
        change(repo)
    env = {**_git_env(tmp_path), "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin"}
    ran = subprocess.run([_BASH, "scripts/windows-gate.sh", "box", *given], cwd=repo, env=env,  # noqa: S603
                         capture_output=True, text=True, timeout=60, check=False)
    return ran, repo, kept


def test_a_tracked_file_deleted_but_not_staged_does_not_fail_the_gate(tmp_path: Path):
    """Breaks when the zip step reads every name ls-files lists, and a file
    deleted from disk but not staged fails the gate as if the suite had."""
    ran, _, kept = _gate(tmp_path, change=lambda repo: (repo / "removed.txt").unlink())
    assert ran.returncode == 0, ran.stderr
    sent = next(kept.glob("*.zip"))
    with zipfile.ZipFile(sent) as archive:
        names = set(archive.namelist())
    assert "kept.txt" in names
    assert "removed.txt" not in names


@pytest.mark.parametrize("said", ["ssh: connect to host box port 22: No route to host",
                                  "ssh: connect to host box port 22: Connection timed out",
                                  "ssh: Could not resolve hostname box: Name or service not known"])
def test_a_box_that_cannot_be_reached_exits_2(tmp_path: Path, said: str):
    """The control: local-ci.sh warns and goes on for exit 2, and only for it."""
    ran, _, _ = _gate(tmp_path, ssh_fails=said, scp_fails=said)
    assert ran.returncode == 2, ran.stderr
    assert "not reachable" in ran.stderr


@pytest.mark.parametrize("said", ["Host key verification failed.",
                                  "box: Permission denied (publickey).",
                                  "Connection timed out during banner exchange"])
def test_a_box_that_answers_and_refuses_fails_the_gate(tmp_path: Path, said: str):
    """Breaks when every ssh 255 is read as an unreachable box, so a changed
    host key or a refused key passes the gate with a warning. A box that
    connected and then sent no greeting is not unreachable either."""
    ran, _, _ = _gate(tmp_path, ssh_fails=said, scp_fails=said)
    assert ran.returncode == 1, ran.stderr
    assert said in ran.stderr


def test_a_copy_that_fails_once_the_box_answered_fails_the_gate(tmp_path: Path):
    """Breaks when any scp failure, a full disk on the box for one, is read
    as an unreachable box."""
    ran, _, _ = _gate(tmp_path, scp_fails="scp: write: No space left on device")
    assert ran.returncode == 1, ran.stderr
    assert "could not copy" in ran.stderr


def test_a_file_deleted_here_is_absent_on_the_box(tmp_path: Path):
    """Breaks when the box checks HEAD out under the zip, and a file deleted
    and staged here, or the old name of a move, comes back from HEAD: a
    deleted test still runs, a removed module still imports.

    The box's own steps are PowerShell, so they are replayed here with the
    same git commands the script sends, on what the script sent."""
    def delete_and_move(repo: Path) -> None:
        for command in (["rm", "-q", "removed.txt"], ["mv", "kept.txt", "moved.txt"]):
            subprocess.run([_GIT, *command], cwd=repo, env=_git_env(tmp_path),  # noqa: S603
                           check=True)

    ran, _, kept = _gate(tmp_path, change=delete_and_move)
    assert ran.returncode == 0, ran.stderr
    script = next(kept.glob("*.ps1")).read_text(encoding="utf-8")
    clone = re.search(r"git clone --quiet (.*?)\"", script).group(1)
    assert "--no-checkout" in clone
    assert "git -C $work reset --quiet" in script
    box = tmp_path / "box"
    git = [_GIT, "-c", "core.autocrlf=false"]
    bundle = next(kept.glob("*.bundle"))
    subprocess.run([*git, "clone", "--quiet", *clone.split(), str(bundle), str(box)],  # noqa: S603
                   env=_git_env(tmp_path), check=True, capture_output=True)
    subprocess.run([*git, "-C", str(box), "reset", "--quiet"],  # noqa: S603
                   env=_git_env(tmp_path), check=True)
    with zipfile.ZipFile(next(kept.glob("*.zip"))) as archive:
        archive.extractall(box)
    assert (box / "moved.txt").is_file()
    assert not (box / "removed.txt").exists()
    assert not (box / "kept.txt").exists()


def test_each_run_first_clears_what_runs_cut_short_left(tmp_path: Path):
    """PRESS-0475: a run whose connection dropped never reaches its own
    finally, so the next run clears its folder and files once a day old. The
    sweep runs before the clone, in its own try, so its failure cannot fail
    the gate; and it matches the names a run takes and nothing near them.
    Breaks when the sweep goes, moves inside the run's try, ages nothing, or
    its patterns drift from the run's own names.

    The box's steps are PowerShell; their .NET patterns are read the same way
    by Python's re here. A run on the box against planted folders checked the
    rest."""
    ran, _, kept = _gate(tmp_path)
    assert ran.returncode == 0, ran.stderr
    script = next(kept.glob("*.ps1")).read_text(encoding="utf-8")
    sweep = script.index("$stale = (Get-Date).AddDays(-1)")
    sweep_try, run_try = script.rfind("try {", 0, sweep), script.index("try {", sweep)
    assert sweep_try < sweep < script.index("} catch {", sweep) < run_try
    assert run_try < script.index("git clone")
    assert script.count("-lt $stale") == 2
    folders, files = re.findall(r"-match '([^']+)'", script)
    run = next(kept.glob("*.ps1")).stem
    assert re.search(folders, run)
    for name in (f"{run}.zip", f"{run}.bundle", f"{run}.ps1"):
        assert re.search(files, name), name
    for near in ("python", "run-notes", f"{run}.txt", f"{run}.zip.bak", f"x{run}", "run-1-x"):
        assert not re.search(folders, near) and not re.search(files, near), near
    assert re.search(r"-LiteralPath \$gate -Directory", script)
    assert re.search(r"-LiteralPath \$userHome -File", script)


def test_tests_named_are_what_the_box_runs(tmp_path: Path):
    """`--tests` hands its arguments to pytest, each quoted, and refuses one
    holding anything PowerShell could read. Breaks when they are dropped or
    passed unchecked."""
    ran, _, kept = _gate(tmp_path, given=("--tests", "tests/test_a.py::t[folder]", "-k", "x"))
    assert ran.returncode == 0, ran.stderr
    script = next(kept.glob("*.ps1")).read_text(encoding="utf-8")
    assert 'pytest -ra -q -p no:cacheprovider "tests/test_a.py::t[folder]" "-k" "x"' in script
    for unsafe in ('a"b', "a$b", "a b", "a`b"):
        apart = tmp_path / unsafe.encode().hex()
        apart.mkdir()
        refused, _, _ = _gate(apart, given=("--tests", unsafe))
        assert refused.returncode == 64, unsafe
