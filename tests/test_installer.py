# Putting a checked update in place (PRESS-0023 § 4.7).
#
# The helpers' runtime is proved by hand (§ 7.1); what the suite holds is the
# swap, and the command and environment each helper is handed. Popen is always
# replaced, so no test starts a program -- except the one that runs the Linux
# waiter itself against a process that has already ended.
from __future__ import annotations

import ntpath
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pressless import installer


class _Spawned:
    """Records what Popen was handed, instead of starting anything."""

    def __init__(self, monkeypatch, *, fails: bool = False) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.fails = fails
        monkeypatch.setattr(installer.subprocess, "Popen", self)

    def __call__(self, args, **kwargs):
        if self.fails:
            raise OSError("cannot start")
        self.calls.append((list(args), kwargs))
        return object()


def _no_exec(monkeypatch) -> list[object]:
    called: list[object] = []
    monkeypatch.setattr(installer.os, "execv", lambda *a: called.append(a))
    monkeypatch.setattr(installer.os, "execve", lambda *a: called.append(a), raising=False)
    return called


def _log(folder: Path) -> list[str]:
    return [line.split(" ", 2)[-1]
            for line in (folder / "update.log").read_text(encoding="ascii").splitlines()]


# ----------------------------------------------------------------- INV-10 ---


def test_linux_swap(tmp_path, monkeypatch):
    """Breaks when the file is written in place."""
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    apps = tmp_path / "apps"
    apps.mkdir()
    appimage = apps / "Pressless-0.1.2-x86_64.AppImage"

    # A failure before the replace leaves the old bytes and removes the stage.
    appimage.write_bytes(b"old program")
    staged = apps / ".pressless-update-a"
    staged.write_bytes(b"new program")
    spawned = _Spawned(monkeypatch)
    real_replace = os.replace

    def refuse(*args):
        raise OSError("busy")

    monkeypatch.setattr(installer.os, "replace", refuse)
    with pytest.raises(installer.InstallFailed):
        installer.apply_linux(appimage, staged, folder)
    assert appimage.read_bytes() == b"old program"
    assert not staged.exists()
    assert spawned.calls == []

    monkeypatch.setattr(installer.os, "replace", real_replace)
    staged.write_bytes(b"new program")
    _no_exec(monkeypatch)
    assert installer.apply_linux(appimage, staged, folder) is True
    assert appimage.read_bytes() == b"new program"
    assert not staged.exists()
    if os.name == "posix":
        assert appimage.stat().st_mode & 0o777 == 0o755
    assert _log(folder) == ["swapped"]
    assert len(spawned.calls) == 1

    # A helper that cannot start: the new bytes stay, and it says so.
    staged.write_bytes(b"newer program")
    _Spawned(monkeypatch, fails=True)
    assert installer.apply_linux(appimage, staged, folder) is False
    assert appimage.read_bytes() == b"newer program"
    assert _log(folder) == ["swapped", "not started"]


# ----------------------------------------------------------------- INV-11 ---


def test_linux_helper(tmp_path, monkeypatch):
    """Breaks when a path is spliced into the script, or the helper inherits
    LD_LIBRARY_PATH pointing into the bundle."""
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    apps = tmp_path / "it's my apps"
    apps.mkdir()
    appimage = apps / "Pressless-0.1.2-x86_64.AppImage"
    appimage.write_bytes(b"old")
    staged = apps / ".pressless-update-b"
    staged.write_bytes(b"new")
    for name, value in (("APPDIR", "/mount"), ("APPIMAGE", str(appimage)),
                        ("ARGV0", "./x"), ("LD_LIBRARY_PATH", "/mount/_internal"),
                        ("LD_LIBRARY_PATH_ORIG", "/usr/lib/before"),
                        ("LD_PRELOAD", "/mount/_internal/x.so")):
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LD_PRELOAD_ORIG", raising=False)
    spawned = _Spawned(monkeypatch)
    execs = _no_exec(monkeypatch)

    assert installer.apply_linux(appimage, staged, folder) is True
    [(args, kwargs)] = spawned.calls
    assert args == ["/bin/sh", "-c", installer.WAITER, "sh", str(appimage),
                    str(os.getpid()), str(folder / "update.log")], args
    assert str(apps) not in installer.WAITER and "it's" not in installer.WAITER
    env = kwargs["env"]
    for gone in ("APPDIR", "APPIMAGE", "ARGV0", "LD_PRELOAD"):
        assert gone not in env, gone
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert env["LD_LIBRARY_PATH"] == "/usr/lib/before"
    assert kwargs["start_new_session"] is True
    for stream in ("stdin", "stdout", "stderr"):
        assert kwargs[stream] is subprocess.DEVNULL, stream
    assert execs == []

    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    staged.write_bytes(b"newer")
    spawned = _Spawned(monkeypatch)
    installer.apply_linux(appimage, staged, folder)
    assert "LD_LIBRARY_PATH" not in spawned.calls[0][1]["env"]


@pytest.mark.skipif(sys.platform == "win32", reason="the waiter is a POSIX sh script")
def test_the_waiter_runs(tmp_path):
    """The waiter itself, against a process that has already ended: it logs
    waiting then started, and execs its first argument, which is a path
    holding a space and an apostrophe."""
    started = tmp_path / "it's started"
    program = tmp_path / "new program's"
    program.write_text(f"#!/bin/sh\ntouch \"{started}\"\n", encoding="utf-8")
    program.chmod(0o755)
    ended = subprocess.Popen(["true"])  # noqa: S607 -- a process that ends at once
    ended.wait()
    log = tmp_path / "update.log"
    log.write_text("x swapped\n", encoding="ascii")
    subprocess.run(["/bin/sh", "-c", installer.WAITER, "sh", str(program),  # noqa: S603
                    str(ended.pid), str(log)], check=True, timeout=30)
    assert started.exists()
    assert _log(tmp_path) == ["swapped", "waiting", "started"]


# ----------------------------------------------------------------- INV-12 ---


def test_windows_helper(tmp_path, monkeypatch):
    """Breaks when the wait uses $PID or -Id, or a path is written into the
    script text."""
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    program = tmp_path / "Pressless"
    program.mkdir()
    staged = tmp_path / "Pressless.new-c"
    (staged / "Pressless").mkdir(parents=True)
    spawned = _Spawned(monkeypatch)

    assert installer.apply_windows(program, staged, folder) is None
    [(args, kwargs)] = spawned.calls
    assert ntpath.isabs(args[0]) and args[0].lower().endswith("powershell.exe"), args[0]
    for flag in ("-NoProfile", "-NonInteractive", "-File"):
        assert flag in args, flag
    script = Path(args[args.index("-File") + 1])
    assert script.parent == staged.parent, script
    assert args[-3:] == [str(program), str(staged), str(folder / "update.log")], args
    text = script.read_text(encoding="utf-8")
    for path in (program, staged, folder):
        assert str(path) not in text, path
    assert "-Id" not in text and "$pid" not in text.lower()
    assert kwargs["stdin"] is subprocess.DEVNULL

    # A spawn that fails removes the staged folder and its own script.
    scripts = {p for p in tmp_path.iterdir() if p.suffix == ".ps1"}
    _Spawned(monkeypatch, fails=True)
    with pytest.raises(installer.InstallFailed):
        installer.apply_windows(program, staged, folder)
    assert not staged.exists()
    assert {p for p in tmp_path.iterdir() if p.suffix == ".ps1"} == scripts
