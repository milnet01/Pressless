"""The AppImage's entry point, packaging/linux/AppRun (PRESS-0022 § 4.1).

It finds the frozen program from $APPDIR, which the AppImage runtime sets,
or else from its own path. Each test lays out an AppDir whose program only
says where it ran from.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_APPRUN = Path(__file__).resolve().parent.parent / "packaging" / "linux" / "AppRun"
_SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(sys.platform == "win32" or _SH is None,
                                reason="the AppImage runs on Linux")


def _app_dir(tmp_path: Path) -> Path:
    app_dir = tmp_path / "Pressless.AppDir"
    program = app_dir / "usr" / "bin" / "Pressless" / "Pressless"
    program.parent.mkdir(parents=True)
    program.write_text('#!/bin/sh\necho "ran with $*"\n', encoding="utf-8")
    program.chmod(0o755)
    shutil.copy(_APPRUN, app_dir / "AppRun")
    return app_dir


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env={"PATH": "/usr/bin:/bin", **env},  # noqa: S603 -- the AppDir's own entry
                          capture_output=True, text=True, timeout=30, check=False)


def test_the_runtime_s_appdir_is_used(tmp_path):
    app_dir = _app_dir(tmp_path)
    ran = _run([_SH, str(app_dir / "AppRun"), "--self-check"], tmp_path, {"APPDIR": str(app_dir)})
    assert ran.stdout == "ran with --self-check\n", ran.stderr


def test_a_run_by_path_from_the_app_dir_finds_the_program(tmp_path):
    app_dir = _app_dir(tmp_path)
    ran = _run([_SH, str(app_dir / "AppRun"), "x"], tmp_path, {})
    assert ran.stdout == "ran with x\n", ran.stderr


def test_a_run_by_bare_name_inside_the_app_dir_finds_the_program(tmp_path):
    """Breaks when $0 holds no slash (`sh AppRun` inside the AppDir) and
    ${0%/*} leaves `AppRun` itself as the folder."""
    app_dir = _app_dir(tmp_path)
    ran = _run([_SH, "AppRun", "x"], app_dir, {})
    assert ran.stdout == "ran with x\n", ran.stderr
