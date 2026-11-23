"""Replacing a file whole, so an interrupted save leaves the old file or the new;
and reading back the versioned JSON files Settings and Credentials keep.

The contract is docs/specs/PRESS-0001-settings.md § 4.4, which states this
module's functions; § 11 there names the modules that call it. It is not a
part of Pressless: it imports no pressless module and no network module, so a
module allowed to import it reaches nothing else through it (PRESS-0141).

Each caller keeps its own error type. The writing steps propagate everything
unchanged, because only the caller knows which sentence a failure becomes. The
reading steps raise the error type and file label their caller passes, so a
refusal one reader makes the other makes too (PRESS-0447).
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

# Windows refuses to replace a file another program holds open -- its own
# scanners open what was just written for a moment -- where Linux does not
# (measured on the Windows box: error 5). A short wait clears that; a file
# marked read-only is refused throughout and fails as before (PRESS-0159).
# The Publisher's fetch retries its renames on the same terms, on its own clock.
WINDOWS_TRIES = 10
WINDOWS_PAUSE = 0.1

# Windows reads these names as devices whatever the extension, so opening
# `nul.txt` there reaches the null device rather than failing (PRESS-0067).
# Measured on a Windows 10 box with CreateFileW (PRESS-0164): `com0`, `lpt0`
# and `clock$` are ordinary files. The Store refuses them on every system and
# the Publisher's fetch on Windows; a newly measured device goes in here.
WINDOWS_DEVICES = frozenset(
    ["con", "prn", "aux", "nul", "conin$", "conout$"]
    + [f"{port}{n}" for port in ("com", "lpt") for n in "123456789\u00b9\u00b2\u00b3"])
_T = TypeVar("_T")


def write_whole(
    target: Path,
    text: str,
    *,
    prefix: str,
    newline: str = "\n",
    check: Callable[[int], None] | None = None,
) -> None:
    """Write `text` to a temporary beside `target`, sync it, and replace.

    `check` runs on the raw descriptor before a byte is written; whatever it
    raises reaches the caller unchanged. `newline` is the line-ending
    translation: "\\n" gives the same bytes on both systems, and "" keeps the
    bytes it was handed. mkstemp creates the temporary owner-only, and the
    replace carries that mode onto the target where the mount grants it.
    """
    target = Path(target)
    handle, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=prefix, suffix=".tmp")
    try:
        try:
            if check is not None:
                check(handle)
            stream = os.fdopen(handle, "w", encoding="utf-8", newline=newline)
        except BaseException:
            # mkstemp hands back a RAW descriptor and only fdopen takes
            # ownership of it, so a failure before that point closes it here;
            # unlinking the path alone would leak one per failed save
            # (PRESS-0066).
            os.close(handle)
            raise
        with stream:
            stream.write(text)
            # rename(2) orders the namespace, not the data, so without this a
            # power loss can commit the rename before the blocks and leave an
            # empty file where the previous one was promised (PRESS-0039).
            stream.flush()
            os.fsync(stream.fileno())
        patiently(lambda: os.replace(temporary, target))
    except BaseException:
        _discard(temporary)
        raise
    sync_folder(target.parent)


def sync_folder(folder: Path) -> None:
    """Make a rename, link or unlink in `folder` survive a power loss on POSIX.

    The file's own fsync covers its blocks, not the folder entry naming it, so
    without this a save already reported done can come back as the old version.
    Best effort: some file systems refuse to sync a folder, and by then the
    change is made, so a refusal must not report it as failed. Windows opens
    no folder descriptor, so it does nothing there (PRESS-0376)."""
    if _is_windows():
        return
    try:
        handle = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def patiently(step: Callable[[], _T]) -> _T:
    """Run `step` and return what it returns, retrying a PermissionError for a
    moment on Windows only, where a scanner briefly refuses a file just
    written (PRESS-0135 #2). PRESS-0001 § 11 names its callers."""
    for attempt in range(WINDOWS_TRIES):
        try:
            return step()
        except PermissionError:
            if not _is_windows() or attempt == WINDOWS_TRIES - 1:
                raise
            time.sleep(WINDOWS_PAUSE)


def read_ordinary(target: Path, *, follow: bool = True,
                  check: Callable[[int], None] | None = None) -> str | None:
    """`target`'s text as UTF-8, or None where it is not a regular file: a
    FIFO, a folder, a device, read as a file, answers empty or forever.

    O_NONBLOCK, so a FIFO planted at that name cannot hold the open forever
    (PRESS-0162). A missing file raises FileNotFoundError.
    `follow=False` refuses a symlink at the open, which is the only place a
    symlink can be seen. `check` runs on the open descriptor, as write_whole's
    does, so what was checked is what is read; what it raises propagates.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    if not follow:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    handle = os.open(target, flags)
    try:
        ordinary = stat.S_ISREG(os.fstat(handle).st_mode)
        if ordinary and check is not None:
            check(handle)
    except BaseException:
        os.close(handle)
        raise
    if not ordinary:
        os.close(handle)
        return None
    with os.fdopen(handle, "r", encoding="utf-8") as stream:
        return stream.read()


def read_mapping(target: Path, *, label: str, error: type[Exception],
                 reason: Callable[[OSError], str], saving: bool = False,
                 follow: bool = True,
                 check: Callable[[int], None] | None = None) -> dict | None:
    """The JSON object in `target`, or None where there is no file.

    Raises `error`, naming the file as `label`, for a file that is not an
    ordinary one, cannot be read, is not UTF-8 (a ValueError, not an OSError:
    PRESS-0049, PRESS-0135), is not JSON or nests too deep (RecursionError is
    not a ValueError: PRESS-0066), or holds something other than an object.
    `reason` words an OSError without its path. `saving` picks the wording: a
    refused save says what saving over the file would do. `follow` and
    `check` are read_ordinary's.
    """
    try:
        text = read_ordinary(target, follow=follow, check=check)
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as exc:
        raise error(f"the {label} is not readable as UTF-8, so it cannot be "
                    f"parsed: {exc}") from None
    except OSError as exc:
        raise error(f"the {label} could not be read: {reason(exc)}") from None
    if text is None:
        raise error(f"the {label} is not an ordinary file, so it is not the "
                    "file Pressless wrote")

    try:
        raw = json.loads(text)
    except (ValueError, RecursionError) as exc:
        if saving:
            raise error(f"the {label} is not valid JSON, so saving over it would "
                        f"discard what could not be parsed: {exc}") from None
        raise error(f"the {label} is not valid JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise error(f"the {label} holds {type(raw).__name__}, not an object")
    return raw


def refuse_other_version(raw: dict, *, version: int, label: str,
                         error: type[Exception], saving: bool = False) -> None:
    """Raise `error` unless `raw` carries `version`, as the number itself.

    The type is checked as well as the value: a bool IS an int in Python and
    a float 1.0 equals 1, so `!=` alone accepts both (PRESS-0066, PRESS-0100).
    A save refuses too: carrying unknown keys forward under this build's
    version stamp would relabel a file another Pressless wrote (PRESS-0053).
    """
    found = raw.get("version")
    if type(found) is int and found == version:
        return
    if saving:
        raise error(f"the {label} has version {found!r}; this Pressless writes "
                    f"version {version}, and saving over it would relabel a "
                    "file written by another")
    raise error(f"the {label} has version {found!r}; this Pressless reads "
                f"version {version}")


def wider_than_owner(handle: int) -> int:
    """The mode the mount granted `handle`, where it reaches any group or
    other bit; else 0. Read off the descriptor, the one call reporting what
    the mount actually granted, where mkstemp only asked (PRESS-0042). Each
    caller decides whether that is refused or reported."""
    granted = stat.S_IMODE(os.fstat(handle).st_mode)
    return granted if granted & 0o077 else 0


def _is_windows() -> bool:
    """Read at call time, so the platform is what a test patches (§ 4.4).
    Underscored, but the platform test the whole program shares: other
    modules call it and tests patch it by this name, which PRESS-0001 and
    PRESS-0005 cite, so search them before changing it.

    `os.name` would be the obvious signal and cannot be patched in a test:
    `pathlib` branches on it to choose a path class, so setting it strands
    every Path the write is about to make.
    """
    return sys.platform.startswith("win")


def _discard(temporary: str) -> None:
    """Remove this call's own temporary file, and nothing else."""
    try:
        os.unlink(temporary)
    except OSError:
        # Swallowed deliberately: this runs while a failure is already on its
        # way up, and a temporary that cannot be removed must not replace the
        # error saying what actually went wrong. What is left is inert.
        pass


def windows_device(name: str) -> bool:
    """Whether Windows reads the file name `name` as a device: the part before
    its first dot, trailing spaces removed, case ignored, so `nul .jpg` is one.
    `str.casefold` agrees with an A-Z fold here: no other letter folds into a
    device name's."""
    return name.split(".")[0].rstrip(" ").casefold() in WINDOWS_DEVICES
