"""A backup of every site, made by itself each day (PRESS-0225).

Each backup is the file PRESS-0224 saves (sitefile.save), named for the site
and the day: `<name> (site-N) <YYYY-MM-DD>.zip`. The site's folder in the
name, not its name, is what tells one site's backups from another's, since a
name can change. Each site keeps its last KEEP; nothing else in the folder is
ever removed, so a folder he also uses for other things is safe.

They go to a folder he chose, or to DEFAULT_FOLDER beside Pressless's own
folder: away from Pressless-data, so deleting that folder does not take the
backups with it. The record of his choice, and of the last failure, is the
machine's `backups.json`.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import re
import secrets
import threading
from pathlib import Path

from pressless import sitefile, sites, store
from pressless.safe_write import write_whole
from pressless.words import say

FILE_NAME = "backups.json"
DEFAULT_FOLDER = "Pressless-backups"
KEEP = 7
_EVERY = 60 * 60   # seconds between looks while Pressless is open
_DAY = re.compile(r" \((site-[1-9][0-9]*)\) (\d{4}-\d{2}-\d{2})\.zip$")
_LOCK = threading.Lock()   # one round of backups at a time


def _record(own: Path) -> dict:
    try:
        data = json.loads((Path(own) / FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) and data.get("version") == 1 else {}


def _write(own: Path, **changes: object) -> None:
    data = {**_record(own), **changes, "version": 1}
    write_whole(Path(own) / FILE_NAME, json.dumps(data, indent=2) + "\n",
                prefix=f".{FILE_NAME}.")


def folder_of(own: Path) -> Path:
    """Where backups go: the folder he chose, else DEFAULT_FOLDER beside
    Pressless's own folder."""
    chosen = _record(own).get("folder")
    if isinstance(chosen, str) and chosen and Path(chosen).is_absolute():
        return Path(chosen)
    return Path(own).parent / DEFAULT_FOLDER


def set_folder(own: Path, text: str) -> Path:
    """Choose the folder backups go to. It must be a whole address of a
    folder that exists; anything else raises ValueError and changes nothing."""
    chosen = Path(text.strip())
    if not text.strip() or not chosen.is_absolute() or not chosen.is_dir():
        raise ValueError("that is not the address of a folder")
    _write(own, folder=str(chosen))
    return chosen


def trouble(own: Path) -> str | None:
    """What went wrong at the last attempt, or None where it went well."""
    said = _record(own).get("trouble")
    return said if isinstance(said, str) and said else None


def _backup_name(site: Path, day: datetime.date) -> str:
    return f"{sitefile.stem(site)} ({site.name}) {day.isoformat()}.zip"


def _held(folder: Path, site: Path) -> list[tuple[str, Path]]:
    """This site's backups in `folder`, oldest first, by the day in the name."""
    found = []
    for path in folder.iterdir():
        matched = _DAY.search(path.name)
        if matched and matched.group(1) == site.name and path.is_file():
            found.append((matched.group(2), path))
    return sorted(found)


def make_due(own: Path, today: datetime.date) -> str | None:
    """Back up every site holding anything that has no backup dated `today`,
    and keep each site's last KEEP. Returns a sentence where it failed, kept
    in the record too, or None."""
    with _LOCK:
        folder = folder_of(own)
        failed = None
        try:
            held_sites = sites.all_sites(own)
        except OSError as exc:
            held_sites, failed = [], exc
        # One site that cannot be read or saved never stops the others.
        for site in held_sites:
            try:
                if sitefile.unused(site):
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                held = _held(folder, site)
                if not any(day == today.isoformat() for day, _ in held):
                    part = folder / f".pressless-backup-{secrets.token_hex(6)}.part"
                    try:
                        sitefile.save(site, part)
                        part.rename(folder / _backup_name(site, today))
                    finally:
                        part.unlink(missing_ok=True)
                    held = _held(folder, site)
                for _, old in held[:-KEEP]:
                    old.unlink()
            except (OSError, ValueError, store.StoreError) as exc:
                failed = failed or exc
        if failed is not None:
            said = say("backups.trouble", folder=folder.name,
                       reason=getattr(failed, "strerror", None) or type(failed).__name__)
            with contextlib.suppress(OSError):
                _write(own, trouble=said)
            return said
        if trouble(own) is not None:
            _write(own, trouble="")
        return None


def start(own: Path, stop: threading.Event, note=None) -> threading.Thread:
    """Back up now, then every hour until `stop` is set, in the background.
    `note` hears a failure, for the log."""
    def run() -> None:
        while True:
            said = make_due(own, datetime.date.today())
            # Once stopped, the Face's log may be closed.
            if said is not None and note is not None and not stop.is_set():
                note(said)
            if stop.wait(_EVERY):
                return

    worker = threading.Thread(target=run, name="pressless-backups", daemon=True)
    worker.start()
    return worker
