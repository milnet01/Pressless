"""Does this folder's filesystem enforce POSIX modes? (PRESS-0057)

PRESS-0001 INV-8 and PRESS-0005 INV-11 both hold only "on a filesystem that
enforces POSIX modes", and that condition is the MOUNT rather than the
platform. mkstemp ASKS for 0600; vfat, exFAT, NTFS, CIFS and many FUSE mounts
ignore the request, and os.replace then carries the permissive mode onto the
target -- the case PRESS-0042 found for the fallback credentials file, where
Credentials reads the granted mode off the descriptor and refuses.

A skipif on os.name cannot see any of that. Run from such a mount it reports a
breach of a rule neither spec makes there. So the guard asks the filesystem the
same question Credentials asks, in the folder the test will actually use.

Shared rather than copied for the reason _open_watch.py gives -- two copies of
a probe are two probes that will disagree.
"""
from __future__ import annotations

import os
import stat
import tempfile

import pytest


def _require_posix_modes(folder) -> None:
    """Skip unless a fresh mkstemp in `folder` is granted exactly 0600.

    Read off the DESCRIPTOR, not off the path afterwards: that is the one call
    reporting what the mount actually granted, and it is what credentials.py
    does (PRESS-0042). Windows fails this check too, so it needs no separate
    platform clause.
    """
    handle, path = tempfile.mkstemp(dir=str(folder), prefix=".modeprobe-")
    try:
        granted = stat.S_IMODE(os.fstat(handle).st_mode)
    finally:
        os.close(handle)
        os.unlink(path)
    if granted != 0o600:
        pytest.skip(
            f"this filesystem granted {granted:#o} to a fresh mkstemp, not 0o600, "
            f"so it does not enforce POSIX modes and neither invariant claims "
            f"anything here (PRESS-0042)"
        )
