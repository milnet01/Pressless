"""Replacing a file whole, so an interrupted save leaves the old file or the new.

The contract is docs/specs/PRESS-0001-settings.md § 4.4, which states this
module's two functions; § 11 there names the modules that call it. It is not a
part of Pressless: it imports no pressless module and no network module, so a
module allowed to import it reaches nothing else through it (PRESS-0141).

Each caller keeps its own error type. Everything here propagates unchanged,
because only the caller knows which sentence a failure becomes.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

# Windows refuses to replace a file another program holds open -- its own
# scanners open what was just written for a moment -- where Linux does not
# (measured on the Windows box: error 5). A short wait clears that; a file
# marked read-only is refused throughout and fails as before (PRESS-0159).
_WINDOWS_TRIES = 10
_WINDOWS_PAUSE = 0.1


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


def patiently(step: Callable[[], None]) -> None:
    """Run `step`, retrying a PermissionError for a moment on Windows only.

    write_whole replaces through it, and the Store's own rename does too: the
    scanner refuses both the same way (PRESS-0135 #2)."""
    for attempt in range(_WINDOWS_TRIES):
        try:
            step()
            return
        except PermissionError:
            if not _is_windows() or attempt == _WINDOWS_TRIES - 1:
                raise
            time.sleep(_WINDOWS_PAUSE)


def _is_windows() -> bool:
    """Read at call time, so the platform is what a test patches (§ 4.4).

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
