# Putting a checked update in place (PRESS-0023 § 4.7).
#
# The new version's start is proved by hand (§ 7.1); what the suite holds is
# the swap, and the command and environment each start is handed. Popen and
# os.execve are always replaced, so no test starts a program -- except the one
# that runs the Windows helper against a folder no process runs from.
from __future__ import annotations

import ntpath
import os
import signal
import subprocess
import sys
import time
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
    execs = _no_exec(monkeypatch)
    real_replace = os.replace

    def refuse(*args):
        raise OSError("busy")

    monkeypatch.setattr(installer.os, "replace", refuse)
    with pytest.raises(installer.InstallFailed):
        installer.apply_linux(appimage, staged, folder)
    assert appimage.read_bytes() == b"old program"
    assert not staged.exists()

    # The swap alone: the program opens the new file itself once it has
    # stopped (reopen_linux), so nothing is started here.
    monkeypatch.setattr(installer.os, "replace", real_replace)
    staged.write_bytes(b"new program")
    installer.apply_linux(appimage, staged, folder)
    assert appimage.read_bytes() == b"new program"
    assert not staged.exists()
    if os.name == "posix":
        assert appimage.stat().st_mode & 0o777 == 0o755
    assert _log(folder) == ["swapped"]
    assert spawned.calls == [] and execs == []


# ----------------------------------------------------------------- INV-11 ---


class _Exec:
    """Records what os.execve was handed, instead of replacing the process,
    and which descriptors would have outlived it."""

    def __init__(self, monkeypatch, *, fails: bool = False) -> None:
        self.calls: list[tuple[str, list[str], dict[str, str]]] = []
        self.kept: list[int] = []
        self.fails = fails
        monkeypatch.setattr(installer.os, "execve", self)

    def __call__(self, path, args, env):
        self.kept = [int(fd) for fd in os.listdir("/proc/self/fd")
                     if int(fd) > 2 and _inheritable(int(fd))]
        if self.fails:
            raise OSError("cannot run")
        self.calls.append((path, list(args), dict(env)))


def _inheritable(fd: int) -> bool:
    try:
        return os.get_inheritable(fd)
    except OSError:   # the listing's own descriptor, gone by now
        return False


@pytest.fixture
def _signals_put_back():
    """reopen_linux gives the new program the signal dispositions a started
    program gets; the test runner's are put back afterwards."""
    names = [name for name in ("SIGPIPE", "SIGXFSZ") if hasattr(signal, name)]
    kept = {name: signal.getsignal(getattr(signal, name)) for name in names}
    yield names
    for name, handler in kept.items():
        signal.signal(getattr(signal, name), handler)


@pytest.mark.skipif(sys.platform == "win32", reason="the AppImage is Linux's")
def test_linux_reopen(tmp_path, monkeypatch, _signals_put_back):
    """PRESS-0408: the new AppImage replaces this process, so it keeps the
    terminal, Ctrl+C and a later Restart. Breaks when it is started beside
    this process, a path reaches a shell, the AppImage runtime's descriptors
    outlive the exec (the old file's mount stays up), or it inherits
    LD_LIBRARY_PATH pointing into the bundle."""
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    apps = tmp_path / "it's my apps"
    apps.mkdir()
    appimage = apps / "Pressless-0.1.2-x86_64.AppImage"
    appimage.write_bytes(b"new")
    for name, value in (("APPDIR", "/mount"), ("APPIMAGE", str(appimage)),
                        ("ARGV0", "./x"), ("LD_LIBRARY_PATH", "/mount/_internal"),
                        ("LD_LIBRARY_PATH_ORIG", "/usr/lib/before"),
                        ("LD_PRELOAD", "/mount/_internal/x.so")):
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LD_PRELOAD_ORIG", raising=False)
    spawned = _Spawned(monkeypatch)
    execs = _Exec(monkeypatch)
    for name in _signals_put_back:
        signal.signal(getattr(signal, name), signal.SIG_IGN)
    # What the AppImage runtime leaves open: the pipe that keeps the old
    # file's mount up for as long as anything holds it.
    keepalive, other_end = os.pipe()
    os.set_inheritable(keepalive, True)
    try:
        installer.reopen_linux(appimage, folder)
        assert execs.kept == [], execs.kept
    finally:
        os.close(keepalive)
        os.close(other_end)

    [(path, args, env)] = execs.calls
    assert path == str(appimage) and args == [str(appimage)], (path, args)
    for gone in ("APPDIR", "APPIMAGE", "ARGV0", "LD_PRELOAD"):
        assert gone not in env, gone
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert env["LD_LIBRARY_PATH"] == "/usr/lib/before"
    for name in _signals_put_back:
        assert signal.getsignal(getattr(signal, name)) == signal.SIG_DFL, name
    assert spawned.calls == []
    assert _log(folder) == ["started"]

    # One that cannot run returns, and says so.
    _Exec(monkeypatch, fails=True)
    installer.reopen_linux(appimage, folder)
    assert _log(folder) == ["started", "started", "not started"]


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


def test_windows_helper_gets_a_hidden_console(tmp_path, monkeypatch):
    """Windows PowerShell started with no console at all (DETACHED_PROCESS)
    exits before running a line: measured on the Windows box 2026-10-10, where
    Update now closed Pressless and nothing was installed or reopened. A
    console of its own, never shown, is what it needs.

    Breaks when the helper is started detached, or without a window of its
    own being suppressed. The run itself is test_the_windows_helper_runs.
    """
    for name, value in (("DETACHED_PROCESS", 0x8), ("CREATE_NEW_PROCESS_GROUP", 0x200),
                        ("CREATE_NO_WINDOW", 0x8000000)):
        monkeypatch.setattr(installer.subprocess, name, value, raising=False)
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    program = tmp_path / "Pressless"
    program.mkdir()
    staged = tmp_path / "Pressless.new-c"
    (staged / "Pressless").mkdir(parents=True)
    spawned = _Spawned(monkeypatch)
    installer.apply_windows(program, staged, folder)
    [(_, kwargs)] = spawned.calls
    flags = kwargs.get("creationflags", 0)
    assert flags & 0x8000000, hex(flags)
    assert not flags & 0x8, hex(flags)


@pytest.mark.skipif(sys.platform != "win32", reason="the helper is a Windows PowerShell script")
def test_the_windows_helper_runs(tmp_path):
    """The Windows twin of test_the_waiter_runs: the real helper, started as
    apply_windows starts it, swaps a folder no process runs from and starts
    the batch file beside it. It runs on the Windows box's gate.

    Breaks when PowerShell cannot start the way it is spawned, or the
    script stops before the restart.
    """
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    program = tmp_path / "Pressless"
    program.mkdir()
    (program / "old.txt").write_text("old", encoding="ascii")
    staged = tmp_path / "Pressless.new-c"
    (staged / "Pressless").mkdir(parents=True)
    (staged / "Pressless" / "new.txt").write_text("new", encoding="ascii")
    started = tmp_path / "started.txt"
    (tmp_path / "Start Pressless.bat").write_text(
        f'@echo off\r\necho started> "{started}"\r\n', encoding="ascii")

    installer.apply_windows(program, staged, folder)
    for _ in range(300):
        if started.exists() and (folder / "update.log").exists() and \
                _log(folder)[-1:] == ["started"]:
            break
        time.sleep(0.1)
    assert (folder / "update.log").exists(), "the helper never wrote its first line"
    assert _log(folder) == ["waiting", "swapped", "started"]
    assert (program / "new.txt").exists() and not staged.exists()
    assert started.exists()


def test_windows_helper_starts_outside_the_folder_it_renames(tmp_path, monkeypatch):
    """PRESS-0135 #27: Windows will not rename a folder that is any live
    process's working folder (measured on the Windows box: error 32). The
    helper inherited Pressless.exe's, which is the Pressless folder itself
    when he starts the exe directly, so every rename retry failed and nothing
    restarted. It starts in the folder above instead.

    Breaks when Popen is handed no cwd, or the program's own folder.
    """
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    program = tmp_path / "Pressless"
    program.mkdir()
    staged = tmp_path / "Pressless.new-c"
    (staged / "Pressless").mkdir(parents=True)
    spawned = _Spawned(monkeypatch)
    installer.apply_windows(program, staged, folder)
    [(_, kwargs)] = spawned.calls
    assert Path(kwargs.get("cwd") or "") == program.parent, kwargs.get("cwd")


def test_helper_ends_bridges():
    """PRESS-0337 INV-13, its script half: each pass of the wait loop ends a
    process started from the program folder whose command line ends in
    --assistant, before it looks for what still runs. § 7's by-hand check
    runs it on the Windows box.

    Breaks when the stop step matches every process in the folder, or sits
    outside the loop, so a bridge started during the wait holds the folder.
    """
    script = installer.WINDOWS_SCRIPT
    loop = script[script.index("while ($true) {"):script.index("if (-not $running) { break }")]
    stop = loop[loop.index("Get-CimInstance Win32_Process"):loop.index("$running =")]
    assert "Invoke-CimMethod -MethodName Terminate" in stop
    assert ".EndsWith('--assistant')" in stop
    assert "$_.ExecutablePath.StartsWith($inside" in stop


def test_the_windows_helpers_log_never_stops_it():
    """review-code 2026-11-16 lane 11: the helper runs under
    `$ErrorActionPreference = 'Stop'`, so an update.log a scanner held ended
    it: before the swap, with Pressless already gone, or after it, with
    nothing restarted. A log that cannot be written never stops an update,
    as _stamp promises for Python's lines. The run is
    test_the_windows_helper_runs, on the Windows box.

    Breaks when Stamp's write is outside a try whose catch swallows."""
    script = installer.WINDOWS_SCRIPT
    stamp = script[script.index("function Stamp"):script.index("function Retry")]
    body = stamp[stamp.index("{") + 1:].strip()
    assert body.startswith("$line =") and "try {" in body, stamp
    write = body[body.index("try {"):]
    assert "Set-Content" in write and "Add-Content" in write, stamp
    assert write.rstrip().removesuffix("}").rstrip().endswith("} catch { }"), stamp


def test_a_failed_rollback_is_logged_as_failed():
    """review-code 2026-11-16 lane 11: the log said `rolled back` even where
    putting the old folder back failed, which leaves no Pressless folder at
    all, the worst state an update can end in.

    Breaks when `rolled back` is written without the rename back having
    succeeded."""
    script = installer.WINDOWS_SCRIPT
    start = script.index("if (-not (Retry { Move-Item -LiteralPath (Join-Path $Staged")
    failed = script[start:script.index("Stamp 'swapped'")]
    assert "| Out-Null" not in failed, failed
    assert "if (Retry { Move-Item -LiteralPath $old -Destination $Program })" in failed
    assert "{ Stamp 'rolled back' }\n    else { Stamp 'rollback failed' }" in failed


def test_the_windows_helper_starts_the_new_program_afresh(tmp_path, monkeypatch):
    """review-code 2026-11-16 lane 11: the Linux helper sets
    PYINSTALLER_RESET_ENVIRONMENT and the Windows one passed no environment,
    so the new Pressless.exe inherited the old bundle's variables.

    Breaks when apply_windows hands Popen no environment, or one without the
    reset."""
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "the old bundle")
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    program = tmp_path / "Pressless"
    program.mkdir()
    staged = tmp_path / "Pressless.new-c"
    (staged / "Pressless").mkdir(parents=True)
    spawned = _Spawned(monkeypatch)
    installer.apply_windows(program, staged, folder)
    [(_, kwargs)] = spawned.calls
    assert kwargs.get("env", {}).get("PYINSTALLER_RESET_ENVIRONMENT") == "1", kwargs.get("env")


def test_the_hand_over_travels_in_the_environment(tmp_path, monkeypatch, _signals_put_back):
    """PRESS-0428 INV-4: the open tab's session reaches the new process in
    its environment, which only his account reads, and never on a command
    line, which every account can. Breaks when the session is added to an
    argument list."""
    session = "handed-over-session-" + "x" * 23
    resume = f"8471:{session}"
    folder = tmp_path / "Pressless-data"
    folder.mkdir()
    appimage = tmp_path / "Pressless-0.1.2-x86_64.AppImage"
    appimage.write_bytes(b"new")
    execs: list[tuple] = []
    monkeypatch.setattr(installer.os, "execve",
                        lambda path, args, env: execs.append((path, list(args), dict(env))),
                        raising=False)
    installer.reopen_linux(appimage, folder, resume)
    [(path, args, env)] = execs
    assert args == [str(appimage)], args
    assert env[installer.RESUME_VARIABLE] == resume

    program = tmp_path / "Pressless"
    program.mkdir()
    staged = tmp_path / "Pressless.new-c"
    (staged / "Pressless").mkdir(parents=True)
    spawned = _Spawned(monkeypatch)
    installer.apply_windows(program, staged, folder, resume)
    [(args, kwargs)] = spawned.calls
    assert args[-3:] == [str(program), str(staged), str(folder / "update.log")], args
    assert not any(session in arg for arg in args), args
    script = Path(args[args.index("-File") + 1])
    assert session not in script.read_text(encoding="utf-8")
    assert kwargs["env"][installer.RESUME_VARIABLE] == resume
