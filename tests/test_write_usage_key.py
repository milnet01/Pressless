"""Where the usage-report key comes from (PRESS-0262 § 4.1, INV-8).

scripts/write_usage_key.py runs as a separate process with no terminal, as it
does in a release job, so it never stops to ask. Every value here is made up:
the real key is never read by a test.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_write_google_secret import _steps

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "write_usage_key.py"
MEASUREMENT_ID = "G-PLAINWORDS"
SENTINEL = "plain-words-secret"
VARIABLES = ("PRESSLESS_USAGE_MEASUREMENT_ID", "PRESSLESS_USAGE_API_SECRET")


def _run(target: Path, measurement_id: str | None,
         secret: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in VARIABLES}
    for name, value in zip(VARIABLES, (measurement_id, secret), strict=True):
        if value is not None:
            env[name] = value
    return subprocess.run([sys.executable, str(SCRIPT), str(target)], env=env,  # noqa: S603
                          stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          timeout=30, check=False)


def test_the_key_file_is_ignored_by_git():
    """INV-8. Breaks when the .gitignore line is dropped, and git add -A
    commits the key to a public repository."""
    git = shutil.which("git")
    assert git, "git is not installed"
    found = subprocess.run([git, "check-ignore", "-q",  # noqa: S603 -- fixed arguments
                            "src/pressless/_usage_key.py"], cwd=ROOT, check=False)
    assert found.returncode == 0


@pytest.mark.parametrize(("measurement_id", "secret"), [
    (None, SENTINEL), (MEASUREMENT_ID, None), ("", SENTINEL), ("UA-123", SENTINEL),
    (MEASUREMENT_ID, ""), (MEASUREMENT_ID, 'abc"; import os #'), (MEASUREMENT_ID, "has space"),
])
def test_a_missing_or_unsafe_value_writes_nothing(tmp_path: Path, measurement_id, secret):
    """Breaks when the script writes a key that cannot work, and a release
    ships with usage reports silently unavailable."""
    target = tmp_path / "_usage_key.py"
    ran = _run(target, measurement_id, secret)
    assert ran.returncode != 0
    assert not target.exists()


def test_a_valid_key_imports_back_and_is_never_printed(tmp_path: Path):
    """Breaks when a value is written unquoted or echoed to the release log."""
    target = tmp_path / "_usage_key.py"
    ran = _run(target, MEASUREMENT_ID, SENTINEL)
    assert ran.returncode == 0, ran.stderr
    assert MEASUREMENT_ID not in ran.stdout + ran.stderr
    assert SENTINEL not in ran.stdout + ran.stderr
    spec = importlib.util.spec_from_file_location("_usage_key_check", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.MEASUREMENT_ID, module.API_SECRET) == (MEASUREMENT_ID, SENTINEL)


@pytest.mark.parametrize("job", ["linux", "windows"])
def test_each_release_job_writes_the_key_before_building(job: str):
    """Breaks when a job loses the step, or runs it after Build, and that
    job's artefact ships unable to send."""
    steps = _steps(job)
    key = [i for i, step in enumerate(steps) if "write_usage_key.py" in step]
    build = [i for i, step in enumerate(steps) if step.startswith("name: Build")]
    assert len(key) == 1 and len(build) == 1, (job, key, build)
    assert key[0] < build[0]
    for name in VARIABLES:
        assert f"{name}: ${{{{ secrets.{name} }}}}" in steps[key[0]], name
