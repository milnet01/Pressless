"""Put a checked update in place of the running Pressless -- PRESS-0023 § 4.7.

Each function returns once the new version is in place and a helper has been
started to open it; the caller then exits. Nothing re-executes in place:
finbreak's relaunch did, and the app closed without reopening.

The helpers are handed every path as an argument and never as script text
(FIBR-0327), so no quoting rule stands between a folder named with an
apostrophe and the command that runs. update.log holds fixed words only, each
after a timestamp -- never a path or an error text (docs/design.md § Logging).

Imports no network module and nothing of the Updater's (§ 4.1).
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path


class UpdateError(Exception):
    """An update did not happen. The base of every update failure (§ 4.10)."""


class InstallFailed(UpdateError):
    """The new version could not be put in place; this one is still installed."""


LOG_NAME = "update.log"

# $1 the AppImage, $2 the process to outlive, $3 update.log. Polls every 0.1 s
# for at most 60 s, then starts the new file whether or not the old process
# has gone -- by then the swap is done and the old process is the only thing
# the wait was for.
WAITER = r"""
program=$1 old=$2 log=$3
stamp() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$log"; }
stamp waiting
tries=0
while kill -0 "$old" 2>/dev/null && [ "$tries" -lt 600 ]; do
    sleep 0.1
    tries=$((tries + 1))
done
stamp started
exec "$program"
"""

# $Program the running Pressless folder, $Staged the unpacked update beside
# it, $Log update.log. Waits on image paths, never a process id (FIBR-0131):
# the program is two processes deep behind the batch file, and any process
# still running from the folder holds it against the rename.
WINDOWS_SCRIPT = r"""
param([string]$Program, [string]$Staged, [string]$Log)
$ErrorActionPreference = 'Stop'
function Stamp([string]$Word, [switch]$First) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $Word
    if ($First) { Set-Content -LiteralPath $Log -Value $line -Encoding ascii }
    else { Add-Content -LiteralPath $Log -Value $line -Encoding ascii }
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
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith($inside, [StringComparison]::OrdinalIgnoreCase) }
    if (-not $running) { break }
    if ((Get-Date) -ge $deadline) {
        Forget $Staged; Stamp 'gave up'; Forget $PSCommandPath; exit 1
    }
    Start-Sleep -Milliseconds 200
}
$home_ = Split-Path -Parent $Program
$old = Join-Path $home_ 'Pressless.old'
Forget $old
if (-not (Retry { Move-Item -LiteralPath $Program -Destination $old })) {
    Forget $Staged; Stamp 'gave up'; Forget $PSCommandPath; exit 1
}
if (-not (Retry { Move-Item -LiteralPath (Join-Path $Staged 'Pressless') -Destination $Program })) {
    Retry { Move-Item -LiteralPath $old -Destination $Program } | Out-Null
    Stamp 'rolled back'; Forget $Staged; Forget $PSCommandPath; exit 1
}
Stamp 'swapped'
$batch = Join-Path $home_ 'Start Pressless.bat'
$newBatch = Join-Path $Staged 'Start Pressless.bat'
if (Test-Path -LiteralPath $newBatch) {
    $same = (Test-Path -LiteralPath $batch) -and (
        (Get-FileHash -LiteralPath $batch).Hash -eq (Get-FileHash -LiteralPath $newBatch).Hash)
    if (-not $same) { Move-Item -LiteralPath $newBatch -Destination $batch -Force }
}
Forget $old
Forget $Staged
Start-Process -FilePath $batch -WorkingDirectory $home_
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


def _helper_environment() -> dict[str, str]:
    """The environment the new AppImage should start in (FIBR-0122).

    The AppImage runtime sets its own variables afresh for the new file, and
    PyInstaller's bundle path must not reach it: a /bin/sh that loads the
    bundle's libraries dies (PRESS-0146).
    """
    env = dict(os.environ)
    for name in ("APPDIR", "APPIMAGE", "ARGV0"):
        env.pop(name, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        before = env.pop(f"{name}_ORIG", None)
        if before is None:
            env.pop(name, None)
        else:
            env[name] = before
    return env


def apply_linux(appimage: Path, staged: Path, folder: Path) -> bool:
    """Replace `appimage` with `staged` and start a helper that opens it once
    this process has gone. True where the helper started.

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
                            f"{exc.strerror or type(exc).__name__}") from exc

    log = Path(folder) / LOG_NAME
    _stamp(log, "swapped", first=True)
    try:
        subprocess.Popen(  # noqa: S603 -- a fixed script; every path is an argument
            ["/bin/sh", "-c", WAITER, "sh", str(appimage), str(os.getpid()), str(log)],
            env=_helper_environment(), start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        _stamp(log, "not started")
        return False
    return True


def _powershell() -> str:
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
    script = Path(staged).parent / f"pressless-update-{secrets.token_hex(4)}.ps1"
    log = Path(folder) / LOG_NAME
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        script.write_text(WINDOWS_SCRIPT, encoding="utf-8")
        subprocess.Popen(  # noqa: S603 -- a fixed script; every path is an argument
            [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), str(program), str(staged), str(log)],
            creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    except OSError as exc:
        script.unlink(missing_ok=True)
        shutil.rmtree(staged, ignore_errors=True)
        raise InstallFailed(f"the updater could not be started: "
                            f"{exc.strerror or type(exc).__name__}") from exc
