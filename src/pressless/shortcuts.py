"""The Start Menu entry and the desktop icon (PRESS-0183).

Two shortcuts, each made only when he ticks its box: one in the system's menu,
one on the desktop. Both start the file he downloaded -- the AppImage on Linux,
`Start Pressless.bat` on Windows -- so each names a path, and a path goes stale
when he moves the file. `refresh` runs at every launch and rewrites a shortcut
that exists but names somewhere else. One he deleted stays deleted: a shortcut's
presence is the only record that he said yes.

The Updater replaces the program in place under the same name (PRESS-0023
scope decision 7), so an update leaves every shortcut correct.

No taskbar or panel pinning: Windows lets only the person pin, and Linux
panels differ per desktop. The page says how to pin instead.

Linux writes freedesktop .desktop files, with the icon copied out of the
AppImage because a menu cannot read inside it. Windows writes .lnk files
through PowerShell's WScript.Shell, the one writer every Windows carries; the
icon is the one Pressless.exe carries. Failures raise ShortcutError, whose words
name no path (docs/design.md § Logging).
"""
from __future__ import annotations

import dataclasses
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from pressless import installer, paths, safe_write
from pressless.words import say

_ENTRY = "pressless.desktop"   # Linux, in the menu folder and on the desktop
_LINK = "Pressless.lnk"        # Windows, the same
_ICON = "pressless.png"        # inside the AppImage, and the copy made of it
_BATCH = "Start Pressless.bat"

# Windows: SHGetFolderPathW's ids for the user's Start Menu Programs folder and
# desktop. Asked of Windows rather than built from %APPDATA% or the profile,
# because a desktop redirected to OneDrive is somewhere else.
_CSIDL_PROGRAMS = 0x0002
_CSIDL_DESKTOP = 0x0010

# Every path reaches the script through the environment, never its text, so
# no quoting rule stands between an apostrophe in a folder name and the call
# (the same rule installer.py keeps).
_WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:PRESSLESS_LINK)
$s.TargetPath = $env:PRESSLESS_TARGET
$s.WorkingDirectory = $env:PRESSLESS_WORKING
$s.IconLocation = $env:PRESSLESS_ICON + ',0'
$s.Description = $env:PRESSLESS_COMMENT
$s.Save()
"""
_WINDOWS_SECONDS = 60


class ShortcutError(Exception):
    """A shortcut could not be made or removed."""


@dataclasses.dataclass(frozen=True)
class Places:
    """Where this copy's shortcuts go and what they start.

    `desktop` is None where there is no desktop folder to put an icon in.
    `icon` is the picture to show: on Linux the PNG to copy out of the
    AppImage (None where it cannot be found), on Windows Pressless.exe.
    `icon_copy` is where Linux copies it; None on Windows.
    """

    windows: bool
    menu: Path
    desktop: Path | None
    program: Path
    working: Path
    icon: Path | None
    icon_copy: Path | None


def places() -> Places | None:
    """This copy's Places, or None where there is nothing to offer: a
    development run has no file to point a shortcut at, and a Windows that
    names no Start Menu folder has nowhere to put one."""
    try:
        artefact = paths.artefact_path()
    except paths.NotPackaged:
        return None
    if sys.platform == "win32":
        return _windows_places(artefact)
    return _linux_places(artefact)


def present(where: Places) -> tuple[bool, bool]:
    """Whether the menu entry and the desktop icon exist now."""
    return where.menu.exists(), where.desktop is not None and where.desktop.exists()


def apply(where: Places, *, menu: bool, desktop: bool) -> None:
    """Make each shortcut that is wanted, and remove each that is not."""
    for target, wanted in ((where.menu, menu), (where.desktop, desktop)):
        if target is None:
            continue
        if wanted:
            _write(where, target)
        else:
            _remove(target)
    if not where.windows and where.icon_copy is not None and not any(present(where)):
        _remove(where.icon_copy)


def refresh(where: Places) -> None:
    """Rewrite each shortcut that exists and names somewhere else. One that
    does not exist is left absent, and one he changed in any other way is
    left as he made it. On Linux the icon copy is renewed too, since an
    update replaces the AppImage and its picture with it."""
    for target in (where.menu, where.desktop):
        if target is not None and target.exists() and not _current(where, target):
            _write(where, target)
    if (not where.windows and where.icon is not None and where.icon_copy is not None
            and any(present(where)) and not _same_bytes(where.icon, where.icon_copy)):
        try:
            shutil.copyfile(where.icon, where.icon_copy)
        except OSError as exc:
            raise ShortcutError(f"the menu's icon could not be renewed: "
                                f"{exc.strerror or type(exc).__name__}") from exc


def _linux_places(appimage: Path) -> Places:
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    desktop = _linux_desktop(home)
    bundled = os.environ.get("APPDIR")
    icon = Path(bundled) / _ICON if bundled else None
    return Places(
        windows=False,
        menu=data / "applications" / _ENTRY,
        desktop=desktop / _ENTRY if desktop is not None else None,
        program=appimage,
        working=appimage.parent,
        icon=icon if icon is not None and icon.is_file() else None,
        icon_copy=data / "icons" / "hicolor" / "256x256" / "apps" / _ICON,
    )


def _linux_desktop(home: Path) -> Path | None:
    """The desktop folder xdg-user-dirs names, else ~/Desktop; None where
    the folder is not there."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    found = home / "Desktop"
    try:
        text = (config / "user-dirs.dirs").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    match = re.search(r'^XDG_DESKTOP_DIR="([^"\n]*)"', text, re.MULTILINE)
    if match:
        value = match.group(1)
        if value.startswith("$HOME"):
            found = home / value[len("$HOME"):].lstrip("/")
        elif value.startswith("/"):
            found = Path(value)
    # A desktop folder set to the home folder itself means "no desktop".
    return found if found.is_dir() and found != home else None


def _windows_places(program_folder: Path) -> Places | None:
    programs = _windows_folder(_CSIDL_PROGRAMS)
    desktop = _windows_folder(_CSIDL_DESKTOP)
    if programs is None:
        return None
    base = program_folder.parent
    return Places(
        windows=True,
        menu=programs / _LINK,
        desktop=desktop / _LINK if desktop is not None and desktop.is_dir() else None,
        program=base / _BATCH,
        working=base,
        icon=Path(sys.executable),
        icon_copy=None,
    )


def _windows_folder(csidl: int) -> Path | None:
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) != 0:
        return None
    return Path(buffer.value) if buffer.value else None


def _write(where: Places, target: Path) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if where.windows:
            _write_link(where, target)
            return
        icon = None
        if where.icon is not None and where.icon_copy is not None:
            where.icon_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(where.icon, where.icon_copy)
            icon = where.icon_copy
        safe_write.write_whole(target, _entry(where.program, icon), prefix=".pressless-")
        # The desktop runs an entry only when it is marked as a program.
        os.chmod(target, 0o755)  # noqa: S103 -- his own launcher, in his own folder
    except OSError as exc:
        raise ShortcutError(f"a shortcut could not be written: "
                            f"{exc.strerror or type(exc).__name__}") from exc


def _remove(target: Path) -> None:
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        raise ShortcutError(f"a shortcut could not be removed: "
                            f"{exc.strerror or type(exc).__name__}") from exc


def _current(where: Places, target: Path) -> bool:
    """Whether the shortcut at `target` already starts `where.program`."""
    try:
        held = target.read_bytes()
    except OSError:
        return False
    if where.windows:
        # A .lnk keeps its working folder as a UTF-16 string counted in
        # UTF-16 units. The program and its icon sit in that folder, so a
        # moved copy changes it.
        text = str(where.working).encode("utf-16-le")
        return struct.pack("<H", len(text) // 2) + text in held
    # Only the line that starts the program: anything else in the file may be
    # his own change, or a menu editor's.
    try:
        wanted = f"Exec={_exec_value(where.program)}"
        return wanted in held.decode("utf-8").splitlines()
    except (ValueError, ShortcutError):
        return False


def _same_bytes(one: Path, other: Path) -> bool:
    try:
        return one.read_bytes() == other.read_bytes()
    except OSError:
        return False


def _entry(program: Path, icon: Path | None) -> str:
    """A freedesktop launcher for `program`. Terminal, like the AppImage's own
    entry: the console is where Pressless says it is running and how to stop."""
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Pressless",
        f"Comment={say('shortcuts.comment')}",
        f"Exec={_exec_value(program)}",
    ]
    if icon is not None:
        lines.append(f"Icon={_string_value(str(icon))}")
    lines += ["Terminal=true", "Categories=Office;"]
    return "\n".join(lines) + "\n"


def _exec_value(program: Path) -> str:
    """The Desktop Entry spec quotes an Exec argument, escaping ", `, $ and
    \\ inside the quotes, doubles %, and then escapes the whole as a string."""
    quoted = re.sub(r'(["`$\\])', r"\\\1", str(program)).replace("%", "%%")
    return _string_value(f'"{quoted}"')


def _string_value(text: str) -> str:
    if any(c in text for c in "\n\r\t"):
        raise ShortcutError("the program's location holds a line break or a tab")
    return text.replace("\\", "\\\\")


def _write_link(where: Places, target: Path) -> None:
    env = dict(os.environ)
    env.update({
        "PRESSLESS_LINK": str(target),
        "PRESSLESS_TARGET": str(where.program),
        "PRESSLESS_WORKING": str(where.working),
        "PRESSLESS_ICON": str(where.icon),
        "PRESSLESS_COMMENT": say("shortcuts.comment"),
    })
    try:
        done = subprocess.run(  # noqa: S603 -- a fixed script; every path is in env
            [installer.powershell(), "-NoProfile", "-NonInteractive", "-Command",
             _WINDOWS_SCRIPT],
            env=env, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=_WINDOWS_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    except subprocess.TimeoutExpired as exc:
        raise ShortcutError("Windows took too long to write a shortcut") from exc
    if done.returncode != 0 or not target.exists():
        # PowerShell's own words quote the path, so they are not passed on.
        raise ShortcutError(f"Windows refused to write a shortcut "
                            f"(exit {done.returncode})")
