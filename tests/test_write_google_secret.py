"""Where the Google client secret comes from (PRESS-0122 § 4.7, INV-16).

scripts/write_google_secret.py runs as a separate process with no terminal,
as it does in a release job, so it never stops to ask. Every value here is a
made-up sentinel: the real secret is never read by a test.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "write_google_secret.py"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
SENTINEL = "GOCSPX-SENTINEL_secret-0123456789"


def _run(target: Path, value: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "GOOGLE_CLIENT_SECRET"}
    if value is not None:
        env["GOOGLE_CLIENT_SECRET"] = value
    return subprocess.run([sys.executable, str(SCRIPT), str(target)], env=env,  # noqa: S603
                          stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          timeout=30, check=False)


def test_the_secret_file_is_ignored_by_git():
    """INV-16. Breaks when the .gitignore line is dropped, and git add -A
    commits the secret to a public repository."""
    git = shutil.which("git")
    assert git, "git is not installed"
    found = subprocess.run([git, "check-ignore", "-q",  # noqa: S603 -- fixed arguments
                            "src/pressless/_google_secret.py"], cwd=ROOT, check=False)
    assert found.returncode == 0


@pytest.mark.parametrize("value", [None, "", 'abc"; import os #', "has space"])
def test_a_missing_or_unsafe_secret_writes_nothing(tmp_path: Path, value: str | None):
    """INV-16. Breaks when the script writes an empty secret, and a release
    ships with the Google step silently unavailable."""
    target = tmp_path / "_google_secret.py"
    ran = _run(target, value)
    assert ran.returncode != 0
    assert not target.exists()


def test_a_valid_secret_imports_back_and_is_never_printed(tmp_path: Path):
    """INV-16. Breaks when the value is written unquoted or echoed to the
    release log."""
    target = tmp_path / "_google_secret.py"
    ran = _run(target, SENTINEL)
    assert ran.returncode == 0, ran.stderr
    assert SENTINEL not in ran.stdout + ran.stderr
    spec = importlib.util.spec_from_file_location("_google_secret_check", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CLIENT_SECRET == SENTINEL


def _steps(job: str) -> list[str]:
    """The release job's steps, each as its own block of text, in order."""
    text = RELEASE.read_text(encoding="utf-8")
    body = re.search(rf"^  {job}:\n(.*?)(?=^  \S|\Z)", text, re.M | re.S)
    assert body, job
    return re.split(r"^      - ", body.group(1), flags=re.M)[1:]


@pytest.mark.parametrize("job", ["linux", "windows"])
def test_each_release_job_writes_the_secret_before_building(job: str):
    """INV-16. Breaks when a job loses the step, or runs it after Build, and
    that job's artefact ships without the Google step."""
    steps = _steps(job)

    def where(predicate) -> int:
        hits = [i for i, step in enumerate(steps) if predicate(step)]
        assert len(hits) == 1, (job, hits)
        return hits[0]

    suite = where(lambda s: s.startswith("name: The suite"))
    secret = where(lambda s: "write_google_secret.py" in s)
    build = where(lambda s: s.startswith("name: Build"))
    assert suite < secret < build, (job, suite, secret, build)
    assert re.search(r"GOOGLE_CLIENT_SECRET: \$\{\{ secrets\.GOOGLE_CLIENT_SECRET \}\}",
                     steps[secret]), steps[secret]
