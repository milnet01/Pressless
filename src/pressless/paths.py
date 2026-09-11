"""Where Pressless's own folder is.

The contract is docs/specs/PRESS-0022-packaging.md § 4.2. This is the caller
PRESS-0001 § 2 says must exist: the entry point asks it for a folder and hands
that folder to Settings and Credentials, which never look for one themselves.
It resolves downward only and imports no other part of Pressless (INV-1).

The folder sits beside the artefact the writer downloaded -- the AppImage on
Linux, the extracted program folder on Windows -- so he chooses the drive by
choosing where the artefact lives (docs/design.md § Where everything sits on
disk). Where it cannot be used, Pressless stops rather than falling back to the
home directory, which would fill the drive this rule exists to protect.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# INV-8: every installed machine binds to this name, so it is a breaking change
# after the first release (scope decision 5 chose it so it cannot be confused
# with the Pressless/ folder the Windows zip unpacks beside it).
FOLDER_NAME = "Pressless-data"

# Honoured only when NOT frozen, so a stray value in the writer's environment
# can never move his writing (INV-4). It is how the suite and a development run
# get a folder at all.
OVERRIDE = "PRESSLESS_FOLDER"


class NotPackaged(Exception):
    """Cannot tell where Pressless is running from."""


class FolderUnusable(Exception):
    """Found the place, and cannot use it."""


def artefact_path() -> Path:
    """The AppImage, or the frozen program folder on Windows (§ 4.2's table).

    Never sys.executable or sys._MEIPASS on Linux: an AppImage runs from a
    read-only temporary mount, and both point inside it (INV-2). $APPIMAGE is
    set by the AppImage runtime and nothing else, and a stale value inherited
    from a parent process names a file that is gone -- so it must name a file
    that exists (INV-3).
    """
    if not getattr(sys, "frozen", False):
        raise NotPackaged("Pressless is not running from a packaged artefact")
    if sys.platform == "win32":
        return Path(sys.executable).parent
    named = os.environ.get("APPIMAGE")
    if named and Path(named).is_file():
        return Path(named)
    # The variable, never the path it held (§ 6): a stale value is a full
    # filesystem path, which docs/design.md § Logging forbids.
    raise NotPackaged(
        "$APPIMAGE names no file that exists, so where Pressless is running "
        "from cannot be told"
    )


def own_folder() -> Path:
    """Pressless's own folder. Resolved, never created -- ensure() creates it."""
    if not getattr(sys, "frozen", False):
        override = os.environ.get(OVERRIDE)
        if override:
            return Path(override)
    return artefact_path().parent / FOLDER_NAME


def ensure(folder: Path) -> Path:
    """Create the folder if absent and prove it writable. Returns it.

    Proven by writing a probe and removing it, so the folder is left holding
    nothing Pressless did not put there on purpose (§ 4.5). Refuses rather than
    choosing another location (INV-5), and the refusal names the folder by its
    own name and never by its path (§ 6).
    """
    target = Path(folder)
    try:
        target.mkdir(exist_ok=True)
        handle, probe = tempfile.mkstemp(dir=target, prefix=".probe-")
        os.close(handle)
        os.unlink(probe)
    except OSError as exc:
        raise FolderUnusable(
            f"the {target.name} folder beside the program could not be "
            f"created or written: {exc.strerror or type(exc).__name__}"
        ) from exc
    return target
