"""Put a checked update in place of the running Pressless -- PRESS-0023 § 4.7.

On Linux the new version is put in place, and once this process has stopped,
the new file replaces it in the same process (PRESS-0408), so it keeps his
terminal. On Windows a helper is started that swaps it in once this process
has gone, and the caller exits.

The Windows helper is handed every path as an argument and never as script
text (FIBR-0327), so no quoting rule stands between a folder named with an
apostrophe and the command that runs. update.log holds fixed words only, each
after a timestamp -- never a path or an error text (docs/design.md § Logging).

Imports no network module and nothing of the Updater's (§ 4.1).
"""
from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import time
from collections.abc import MutableMapping
from pathlib import Path


class UpdateError(Exception):
    """An update did not happen. The base of every update failure (§ 4.10)."""


class InstallFailed(UpdateError):
    """The new version could not be put in place; this one is still installed."""


# One line per word, `YYYY-MM-DD HH:MM:SS <word>`, written by _stamp here and
# Stamp in WINDOWS_SCRIPT. The two are in different languages, so a change to
# the format is made in both.
LOG_NAME = "update.log"
# The Windows helper's script, beside the program until it removes itself. A
# start removes one a helper that died left (updating).
SCRIPT_PREFIX = "pressless-update-"

# $Program the running Pressless folder, $Staged the unpacked update beside
# it, $Log update.log. Waits on image paths, never a process id (FIBR-0131):
# the program is two processes deep behind the batch file, and any process
# still running from the folder holds it against the rename.
WINDOWS_SCRIPT = r"""
param([string]$Program, [string]$Staged, [string]$Log)
$ErrorActionPreference = 'Stop'
function Stamp([string]$Word, [switch]$First) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $Word
    # Best effort, as _stamp: under 'Stop' a held log would end the helper.
    try {
        if ($First) { Set-Content -LiteralPath $Log -Value $line -Encoding ascii }
        else { Add-Content -LiteralPath $Log -Value $line -Encoding ascii }
    } catch { }
}
function Retry([scriptblock]$Step) {
    for ($try = 1; $try -le 5; $try++) {
        try { & $Step; return $true } catch { if ($try -lt 5) { Start-Sleep -Milliseconds 500 } }
    }
    return $false
}
function Forget([string]$Path) {
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
}
Stamp 'waiting' -First
$inside = (Join-Path $Program '')
$deadline = (Get-Date).AddSeconds(60)
while ($true) {
    # PRESS-0337 § 4.9: an AI app keeps its bridge running, which would hold
    # the folder for good. A bridge holds no state, so each pass ends any
    # started from this folder, one started during the wait included.
    try {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ExecutablePath -and
            $_.ExecutablePath.StartsWith($inside, [StringComparison]::OrdinalIgnoreCase) -and
            $_.CommandLine -and $_.CommandLine.TrimEnd().EndsWith('--assistant') } |
            Invoke-CimMethod -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null
    } catch { }
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith($inside, [StringComparison]::OrdinalIgnoreCase) }
    if (-not $running) { break }
    if ((Get-Date) -ge $deadline) {
        Forget $Staged; Stamp 'gave up'; Forget $PSCommandPath; exit 1
    }
    Start-Sleep -Milliseconds 200
}
# Not $home: PowerShell names ignore case, and $HOME is read-only.
$home_ = Split-Path -Parent $Program
$old = Join-Path $home_ 'Pressless.old'
Forget $old
if (-not (Retry { Move-Item -LiteralPath $Program -Destination $old })) {
    Forget $Staged; Stamp 'gave up'; Forget $PSCommandPath; exit 1
}
if (-not (Retry { Move-Item -LiteralPath (Join-Path $Staged 'Pressless') -Destination $Program })) {
    if (Retry { Move-Item -LiteralPath $old -Destination $Program }) { Stamp 'rolled back' }
    else { Stamp 'rollback failed' }
    Forget $Staged; Forget $PSCommandPath; exit 1
}
Stamp 'swapped'
$batch = Join-Path $home_ 'Start Pressless.bat'
$newBatch = Join-Path $Staged 'Start Pressless.bat'
if (Test-Path -LiteralPath $newBatch) {
    # The swap is done, so nothing here may stop the restart (PRESS-0173):
    # an unreadable batch file counts as changed, and one that will not be
    # replaced leaves the old one, which still starts the new program.
    $same = $false
    try {
        $same = (Test-Path -LiteralPath $batch) -and (
            (Get-FileHash -LiteralPath $batch).Hash -eq (Get-FileHash -LiteralPath $newBatch).Hash)
    } catch { }
    if (-not $same) {
        Retry { Move-Item -LiteralPath $newBatch -Destination $batch -Force } | Out-Null
    }
}
Forget $old
Forget $Staged
# Not Start-Process: it reads -FilePath as a wildcard, so a folder name
# holding [ ] could not be started (PRESS-0135).
$start = New-Object Diagnostics.ProcessStartInfo
$start.FileName = $batch; $start.WorkingDirectory = $home_; $start.UseShellExecute = $true
[void][Diagnostics.Process]::Start($start)
Stamp 'started'
Forget $PSCommandPath
"""


def _stamp(log: Path, word: str, *, first: bool = False) -> None:
    """One line of update.log. Best effort: a log that cannot be written never
    stops an update that is otherwise going ahead."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {word}\n"
    try:
        with open(log, "w" if first else "a", encoding="ascii") as out:
            out.write(line)
    except OSError:
        pass


def _reason(exc: OSError) -> str:
    """An error's own words, never its message, which names the path
    (docs/design.md § Logging)."""
    return exc.strerror or type(exc).__name__


def _helper_environment() -> dict[str, str]:
    """The environment the new program starts in, and on Windows the helper
    that starts it (FIBR-0122). PYINSTALLER_RESET_ENVIRONMENT makes the new
    program start afresh rather than as part of the old bundle, on either
    system.

    On Linux the AppImage runtime sets its own variables afresh for the new
    file, and PyInstaller's bundle path must not reach it: a /bin/sh that
    loads the bundle's libraries dies (PRESS-0146).
    """
    env = dict(os.environ)
    for name in ("APPDIR", "APPIMAGE", "ARGV0"):
        env.pop(name, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    restore_loader_paths(env, drop_copies=True)
    return env


def restore_loader_paths(env: MutableMapping[str, str], *, drop_copies: bool = False) -> None:
    """Give LD_LIBRARY_PATH and LD_PRELOAD the values they had before the
    bundle (PRESS-0146): PyInstaller keeps each as `<name>_ORIG`, and a name
    with no copy is dropped. `drop_copies` removes the copies too; the running
    process keeps them, because the helper's environment is built from its
    own later and reads them again."""
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        copy = f"{name}_ORIG"
        before = env.pop(copy, None) if drop_copies else env.get(copy)
        if before is None:
            env.pop(name, None)
        else:
            env[name] = before


def apply_linux(appimage: Path, staged: Path, folder: Path) -> None:
    """Replace `appimage` with `staged`. reopen_linux opens it once this
    process has stopped.

    Raises InstallFailed only while nothing has changed. The file keeps its
    name, whose version is now stale, because a rename would break any
    shortcut he made to it (scope decision 7).
    """
    try:
        os.chmod(staged, 0o755)  # noqa: S103 -- a program he runs, as the download was
        os.replace(staged, appimage)
    except OSError as exc:
        staged.unlink(missing_ok=True)
        raise InstallFailed(f"the new version could not replace the old: "
                            f"{_reason(exc)}") from exc
    _stamp(Path(folder) / LOG_NAME, "swapped", first=True)


# What Python ignores and a program it starts gets back at their defaults, as
# subprocess's restore_signals does; an exec would otherwise keep them ignored.
_RESTORED_SIGNALS = ("SIGPIPE", "SIGXFSZ")


def reopen_linux(appimage: Path, folder: Path) -> None:
    """Replace this process with the AppImage apply_linux put in place
    (PRESS-0408), with no arguments, as a double-click starts it. The same
    process keeps his terminal, so Ctrl+C and closing the window still stop
    Pressless, and a later Restart works. Call it once the stop steps have
    run and from the main thread. Returns only where the new file could not
    be run; update.log then ends `not started`.

    The AppImage runtime leaves descriptors open across an exec, the pipe
    that keeps the old file's mount up among them. Each is closed by the exec
    itself, so the old mount goes with this process and nothing runs from it
    afterwards.
    """
    log = Path(folder) / LOG_NAME
    _stamp(log, "started")
    try:
        held = [int(fd) for fd in os.listdir("/proc/self/fd")]
    except OSError:   # no /proc: the old mount stays up until the new process ends
        held = []
    for fd in held:
        if fd > 2:
            try:
                os.set_inheritable(fd, False)
            except OSError:   # the listing's own descriptor, closed by now
                pass
    for name in _RESTORED_SIGNALS:
        if hasattr(signal, name):   # a test on Windows has neither
            signal.signal(getattr(signal, name), signal.SIG_DFL)
    try:
        os.execve(str(appimage), [str(appimage)], _helper_environment())  # noqa: S606 -- no shell
    except OSError:
        _stamp(log, "not started")


def powershell() -> str:
    """By absolute path, never a bare name a search could resolve elsewhere."""
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return "\\".join((root.rstrip("\\"), "System32", "WindowsPowerShell", "v1.0",
                      "powershell.exe"))


def apply_windows(program: Path, staged: Path, folder: Path) -> None:
    """Start the helper that swaps the unpacked `staged` folder in for
    `program` once every process running from it has gone.

    Raises InstallFailed, removing the staged folder, where the helper cannot
    be started. Everything after the spawn is the helper's.
    """
    script = Path(staged).parent / f"{SCRIPT_PREFIX}{secrets.token_hex(4)}.ps1"
    log = Path(folder) / LOG_NAME
    # A console of its own, never shown. Windows PowerShell started with none
    # at all (DETACHED_PROCESS) exits before its first line: measured on the
    # Windows box, where Update now closed Pressless and nothing came back.
    flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        script.write_text(WINDOWS_SCRIPT, encoding="utf-8")
        subprocess.Popen(  # noqa: S603 -- a fixed script; every path is an argument
            [powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), str(program), str(staged), str(log)],
            # Not the program's own folder: Windows refuses to rename a folder
            # that is a live process's working folder (PRESS-0135).
            cwd=str(Path(program).parent), env=_helper_environment(),
            creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    except OSError as exc:
        script.unlink(missing_ok=True)
        shutil.rmtree(staged, ignore_errors=True)
        raise InstallFailed(f"the updater could not be started: "
                            f"{_reason(exc)}") from exc
