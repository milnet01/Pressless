"""scripts/build-linux.sh and scripts/build-windows.sh, run in a throwaway
repository with stand-ins for freeze_flags.py, PyInstaller and appimagetool.
Nothing is frozen: the stand-ins record what the scripts asked of them.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(sys.platform == "win32" or _BASH is None,
                                reason="the build scripts are run here under bash on Linux")

# Prints one flag, then fails when FREEZE_FAILS is set, as a crash part-way
# through printing the list would.
_FREEZE_FLAGS = """import os, sys
if sys.argv[1] == "version":
    print("9.9.9")
    raise SystemExit
print("--name=Pressless", flush=True)
if os.environ.get("FREEZE_FAILS"):
    raise SystemExit(1)
print("--onedir")
"""

# `python -m PyInstaller` finds this first: -m puts the working folder at the
# front of sys.path, and the scripts run from the repository's root.
_PYINSTALLER = """import pathlib, sys
pathlib.Path("pyinstaller-ran.txt").write_text(" ".join(sys.argv[1:]))
program = pathlib.Path("build/freeze/dist/Pressless")
program.mkdir(parents=True)
(program / "Pressless").write_text("")
"""


def _build(tmp_path: Path, script: str, **env: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    for name in (script, "python.sh"):
        shutil.copy(ROOT / "scripts" / name, repository / "scripts")
    (repository / "scripts" / "freeze_flags.py").write_text(_FREEZE_FLAGS, encoding="utf-8")
    (repository / "PyInstaller").mkdir()
    (repository / "PyInstaller" / "__main__.py").write_text(_PYINSTALLER, encoding="utf-8")
    shutil.copytree(ROOT / "packaging" / "linux", repository / "packaging" / "linux")
    (repository / "packaging" / "icons").mkdir()
    shutil.copy(ROOT / "packaging" / "icons" / "pressless.png", repository / "packaging" / "icons")
    (repository / "src").symlink_to(ROOT / "src")
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    (stand_ins / "python3").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    # appimagetool --runtime-file <runtime> <AppDir> <out>: keeps the AppDir's entry.
    (stand_ins / "appimagetool").write_text(
        f'#!/bin/sh\ncp "$3/pressless.desktop" "{tmp_path}/entry.desktop"\ntouch "$4"\n',
        encoding="utf-8")
    for name in ("python3", "appimagetool"):
        (stand_ins / name).chmod(0o755)
    runtime = tmp_path / "runtime"
    runtime.write_bytes(b"")
    environment = {"PATH": f"{stand_ins}:/usr/bin:/bin", "HOME": str(tmp_path),
                   "APPIMAGE_RUNTIME": str(runtime), **env}
    ran = subprocess.run([_BASH, str(repository / "scripts" / script)],  # noqa: S603 -- this repository's own script
                         env=environment, capture_output=True, text=True, timeout=120, check=False)
    return ran, repository


@pytest.mark.parametrize("script", ["build-linux.sh", "build-windows.sh"])
def test_a_flag_list_cut_short_stops_the_build(tmp_path, script):
    """Breaks when freeze_flags.py's exit status is lost, as it is inside a
    process substitution, and PyInstaller freezes from the partial list."""
    ran, repository = _build(tmp_path, script, FREEZE_FAILS="1")
    assert ran.returncode != 0
    assert not (repository / "pyinstaller-ran.txt").exists()


@pytest.mark.parametrize("script", ["build-linux.sh", "build-windows.sh"])
def test_a_whole_flag_list_reaches_pyinstaller(tmp_path, script):
    """The control: the same build with every flag printed."""
    ran, repository = _build(tmp_path, script)
    assert ran.returncode == 0, ran.stderr
    assert (repository / "pyinstaller-ran.txt").read_text() == "--name=Pressless --onedir"


def test_the_appimage_menu_text_is_in_every_language(tmp_path):
    """PRESS-0241: a desktop that reads the AppImage's own entry shows its
    menu text in the user's language, the words setup's shortcut uses.
    Breaks when the entry carries the English line alone."""
    from pressless import words

    ran, _ = _build(tmp_path, "build-linux.sh")
    assert ran.returncode == 0, ran.stderr
    entry = (tmp_path / "entry.desktop").read_text(encoding="utf-8").splitlines()
    assert f"Comment={words.say_in('en', 'shortcuts.comment')}" in entry
    for code in words.LANGUAGES:
        if code != "en":
            assert f"Comment[{code}]={words.say_in(code, 'shortcuts.comment')}" in entry, code
