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
from pathlib import Path

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


# ------------------------------------------------------------ PRESS-0109 ----
#
# Three more capabilities the suite ASSUMED, each an assumption that holds on
# the developer's Linux box and not on the platform this project must ship to.
# Written the same way _require_posix_modes is, and for the same reason: the
# question is what the MOUNT will do, asked in the folder the test will use.
# A skipif on os.name answers a different question and answers it wrongly on
# a vfat stick plugged into Linux.
#
# What a missing probe costs is not the same in each case, and the difference
# is worth stating. Without hard links or symlinks a test FAILS or ERRORS for
# the environment, which is noisy and wrong but visible. On a case-folding
# mount the fixture silently cannot be built and the assertion holds whatever
# the code does -- green, and proving nothing. That one is the dangerous one.


def _require_hard_links(folder) -> None:
    """Skip unless `folder`'s filesystem can make a hard link.

    store.py's move is `os.link` then `os.unlink` on POSIX, and deliberately
    so: no single call refuses an existing destination on both systems, which
    is what INV-10 turns on. A mount without hard links -- vfat, exFAT, most
    FUSE mounts, a mounted Windows share -- makes every move raise StoreError
    carrying the system's own message. That is a correct implementation
    failing for the environment, and without this guard it is indistinguishable
    from a regression in the move itself.
    """
    source = Path(folder) / ".hardlinkprobe-source"
    target = Path(folder) / ".hardlinkprobe-target"
    source.write_text("", encoding="utf-8")
    refused = ""
    try:
        os.link(source, target)
    except (OSError, NotImplementedError) as exc:
        refused = f"{type(exc).__name__}: {exc}"
    finally:
        for probe in (target, source):
            try:
                probe.unlink()
            except OSError:
                pass
    if refused:
        pytest.skip(
            f"this filesystem refused a hard link ({refused}), and store.py's "
            f"move is os.link on POSIX -- so a move here fails for the mount "
            f"rather than for the code (PRESS-0109)"
        )


def _require_symlinks(folder) -> None:
    """Skip unless `folder`'s filesystem can make a symlink.

    Windows refuses one to an unprivileged account outside Developer Mode.
    The refusal lands while the FIXTURE is being built rather than at the
    assertion, so the test ERRORS where it should skip -- and an error reads
    as a real failure in a CI log, which is the opposite of what it means.
    """
    target = Path(folder) / ".symlinkprobe-target"
    link = Path(folder) / ".symlinkprobe-link"
    target.write_text("", encoding="utf-8")
    refused = ""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        refused = f"{type(exc).__name__}: {exc}"
    finally:
        for probe in (link, target):
            try:
                probe.unlink()
            except OSError:
                pass
    if refused:
        pytest.skip(
            f"this filesystem refused a symlink ({refused}), so the fixture "
            f"cannot be built and there is no refusal to observe (PRESS-0109)"
        )


def _require_distinct_case(folder) -> None:
    """Skip unless `folder` can hold two names differing only in case.

    The quiet one. A case-folding mount -- the default on Windows and macOS,
    and reachable on Linux through vfat, exFAT or a share -- collapses the two
    names into one file. So a fixture needing both cannot be built, and an
    assertion about which of them wins holds whatever the code does. The test
    stays GREEN and stops proving anything, with no skip to say so.

    Measured by writing both and reading the first back: a folded mount
    returns the second file's text, because the second write landed on the
    same file.
    """
    lower = Path(folder) / ".caseprobe"
    upper = Path(folder) / ".CASEPROBE"
    try:
        lower.write_text("lower", encoding="utf-8")
        upper.write_text("upper", encoding="utf-8")
        folded = lower.read_text(encoding="utf-8") != "lower"
    finally:
        for probe in (lower, upper):
            try:
                probe.unlink()
            except OSError:
                pass
    if folded:
        pytest.skip(
            "this filesystem folds case, so one folder cannot hold two names "
            "differing only in case -- the fixture cannot be built and the "
            "assertion would hold whatever the code did (PRESS-0109)"
        )
