"""A backup of every site, made by itself each day (PRESS-0225).

Each backup is the file PRESS-0224 saves (sitefile.save), named for the site
and the day: `<name> (site-N <install>) <YYYY-MM-DD>.zip`. The site's folder
in the name, not its name, is what tells one site's backups from another's,
since a name can change; `<install>` tells this Pressless's from another's
sharing the folder, whose sites are numbered the same. Each site keeps its
last KEEP. Nothing else in the folder is ever removed but half-written files
a save left, so a folder he also uses for other things is safe.

They go to a folder he chose, or to DEFAULT_FOLDER beside Pressless's own
folder: away from Pressless-data, so deleting that folder does not take the
backups with it. The record of his choice, and of the last failure, is the
machine's `backups.json`.
"""
from __future__ import annotations

import contextlib
import datetime
import errno
import os
import re
import secrets
import threading
import time
from pathlib import Path

from pressless import json_record, os_reason, sitefile, sites
from pressless.words import say

FILE_NAME = "backups.json"
DEFAULT_FOLDER = "Pressless-backups"
KEEP = 7
_EVERY = 60 * 60   # seconds between looks while Pressless is open
_DAY = re.compile(r" \((site-[1-9][0-9]*) ([0-9a-f]{6})\) (\d{4}-\d{2}-\d{2})\.zip$")
_INSTALL = re.compile(r"[0-9a-f]{6}")
_LOCK = threading.Lock()          # one round of backups at a time
_RECORD_LOCK = threading.Lock()   # one read-merge-write of the record at a time
_OLD_PART = ".pressless-backup-"  # what a backup was written to before PRESS-0383
_STALE = 60 * 60                  # seconds before a half-made file is surely no one's


def _record(own: Path, *, strict: bool = False) -> dict:
    """backups.json as this Pressless wrote it, else {}. With `strict`, a
    file that is there but cannot be read now raises its OSError, so a write
    never drops the folder it holds."""
    return json_record.read(Path(own) / FILE_NAME, strict=strict)


def _write(own: Path, **changes: object) -> None:
    with _RECORD_LOCK:
        json_record.write(Path(own) / FILE_NAME, {**_record(own, strict=True), **changes})


def _chosen(record: dict) -> Path | None:
    chosen = record.get("folder")
    return Path(chosen) if isinstance(chosen, str) and chosen and Path(chosen).is_absolute() \
        else None


def default_folder(own: Path) -> Path:
    """DEFAULT_FOLDER beside Pressless's own folder."""
    return Path(own).parent / DEFAULT_FOLDER


def folder_of(own: Path) -> Path:
    """Where backups go: the folder he chose, else default_folder."""
    return _chosen(_record(own)) or default_folder(own)


def ready_folder(own: Path) -> Path:
    """folder_of, there to write in. Only the default folder is made: a
    chosen one that has gone, a drive unplugged, raises FileNotFoundError,
    as making it again would hide the backups on the disk under the drive."""
    chosen = _chosen(_record(own, strict=True))
    if chosen is None:
        folder = default_folder(own)
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    if not chosen.is_dir():
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), chosen.name)
    return chosen


def set_folder(own: Path, text: str) -> Path:
    """Choose the folder backups go to. It must be a whole address of a
    folder that exists, outside Pressless's own folder, where a site's added
    files would publish them; anything else raises ValueError and changes
    nothing."""
    chosen = Path(text.strip())
    if not text.strip() or not chosen.is_absolute() or not chosen.is_dir() \
            or chosen.resolve().is_relative_to(Path(own).resolve()):
        raise ValueError("that is not the address of a folder")
    _write(own, folder=str(chosen))
    return chosen


def trouble(own: Path) -> str | None:
    """What went wrong at the last attempt, or None where it went well."""
    said = _record(own).get("trouble")
    return said if isinstance(said, str) and said else None


def _install(own: Path) -> str:
    """This Pressless's mark in its backups' names, made at its first backup
    and kept in the record. A backup made before there was one, or by
    another Pressless, is never counted or removed."""
    with _RECORD_LOCK:
        record = _record(own, strict=True)
        held = record.get("install")
        if isinstance(held, str) and _INSTALL.fullmatch(held):
            return held
        made = secrets.token_hex(3)
        json_record.write(Path(own) / FILE_NAME, {**record, "install": made})
        return made


def _backup_name(site: Path, install: str, day: datetime.date) -> str:
    return f"{sitefile.stem(site)} ({site.name} {install}) {day.isoformat()}.zip"


def _held(folder: Path, site: Path, install: str) -> list[tuple[str, Path]]:
    """This site's backups in `folder`, oldest first, by the day in the name."""
    found = []
    for path in folder.iterdir():
        matched = _DAY.search(path.name)
        if matched and matched.group(1, 2) == (site.name, install) and path.is_file():
            found.append((matched.group(3), path))
    return sorted(found)


def _back_up(own: Path, site: Path, today: datetime.date) -> None:
    """One site's backup for `today`, where it has none, then its last KEEP.
    The backup made now is never the one rotated out, even where the clock
    has gone back and older backups carry later days."""
    folder = ready_folder(own)
    install = _install(own)
    held = _held(folder, site, install)
    day = today.isoformat()
    if not any(when == day for when, _ in held):
        sitefile.save_as(site, folder / _backup_name(site, install, today))
        held = _held(folder, site, install)
    others = [path for when, path in held if when != day]
    for old in others[:max(0, len(held) - KEEP)]:
        old.unlink()


def make_due(own: Path, today: datetime.date) -> str | None:
    """Back up every site holding anything that has no backup dated `today`,
    and keep each site's last KEEP. Returns a sentence where it failed, kept
    in the record too, or None."""
    with _LOCK:
        failed = None
        try:
            held_sites = sites.all_sites(own)
        except OSError as exc:
            held_sites, failed = [], exc
        # One site that cannot be read or saved never stops the others, and
        # nothing a site holds ends the round, whatever it raises.
        for site in held_sites:
            try:
                if not sitefile.unused(site):
                    _back_up(own, site, today)
            except Exception as exc:  # noqa: BLE001 -- said, never swallowed
                failed = failed or exc
        if failed is not None:
            said = _trouble(own, failed)
            with contextlib.suppress(OSError):
                _write(own, trouble=said)
            return said
        if trouble(own) is not None:
            with contextlib.suppress(OSError):
                _write(own, trouble="")
        return None


def _trouble(own: Path, failed: BaseException) -> str:
    return say("backups.trouble", folder=folder_of(own).name,
               reason=os_reason.of(failed))


def clear_leftovers(own: Path) -> None:
    """At start, behind the folder's lock: delete the half-made site files a
    stopped Pressless left in its own folder and in the backups folder. Each
    is a whole site, drafts included. One in the backups folder is left
    while it may still be another Pressless's, writing now."""
    def half_made(path: Path) -> bool:
        return (path.name.startswith(sitefile.SAVING) and path.suffix == ".zip"
                or path.name.startswith(_OLD_PART) and path.suffix == ".part")

    # Each delete is tried again at the next start where it fails now.
    with contextlib.suppress(OSError):
        for path in Path(own).iterdir():
            if half_made(path):
                path.unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        for path in folder_of(own).iterdir():
            if half_made(path) and time.time() - path.stat().st_mtime > _STALE:
                path.unlink(missing_ok=True)
    sites.clear_leftovers(own)


def start(own: Path, stop: threading.Event, note=None) -> threading.Thread:
    """Back up now, then every hour until `stop` is set, in the background.
    `note` hears a failure, for the log."""
    def run() -> None:
        while True:
            try:
                said = make_due(own, datetime.date.today())
            except Exception as exc:  # noqa: BLE001 -- one bad round never ends the backups
                said = _trouble(own, exc)
            # Once stopped, the Face's log may be closed.
            if said is not None and note is not None and not stop.is_set():
                note(said)
            if stop.wait(_EVERY):
                return

    worker = threading.Thread(target=run, name="pressless-backups", daemon=True)
    worker.start()
    return worker
