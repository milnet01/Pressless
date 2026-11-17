"""The sites in Pressless's own folder, and which one is open (PRESS-0223).

The contract is docs/specs/PRESS-0223-several-sites.md. Pressless's own folder
keeps what belongs to the machine at the top -- the log, the updater's files,
the lock, the Face's theme, the usage reports -- and one folder per site under
`sites/`, each shaped as the whole folder was before. Which site is open is
`sites.json`, read at every start of a Face, so a restart opens whichever site
it names.

It imports no part of Pressless, so every part may use it; the names in § 4.2
are spelled out here, and tests/test_sites.py compares each with the constant
it copies.
"""
from __future__ import annotations

import contextlib
import re
import secrets
import shutil
from pathlib import Path

from pressless import json_record

SITES_FOLDER = "sites"
OPEN_FILE = "sites.json"
_MOVING = ".moving"
_REMOVING = ".removing-"   # a removed site, its copy kept, being deleted
_REPLACED = ".replaced-"   # a site moved aside while an opened file takes its place
_NAME = re.compile(r"site-[1-9][0-9]*")

# § 4.2: what belongs to a site, moved into site-1 by move_in. It also
# decides what travels: each name must be placed in sitefile.KEPT or
# sitefile.LEFT_OUT, and KEPT goes into every saved site file and backup.
SITE_NAMES = frozenset({
    "published", "drafts", "bin", "pages", "furniture", "pages-waiting",
    "furniture-waiting", "templates", "comments", "photographs", "files", "forwards",
    "options", "identity", "look", "settings.json", "credentials.json", "site",
    "preview", "preview-assets", "starter-unpublished", "starter-filled.json",
    "takeover-owed", "insights.json",
    "youtube.json",
    "fetch",
    "wizards", "choices.json", "import", "jpeg-xl-views",
})
# § 4.2: what belongs to the machine, left at the top.
MACHINE_NAMES = frozenset({
    "pressless.log", "pressless.log.1", "updates.json", "update.log", "pressless.lock",
    "theme.json", "usage.json", "usage-sent.json", "backups.json", OPEN_FILE, SITES_FOLDER,
    "extras",
})


def _number(site: Path) -> int:
    return int(site.name.partition("-")[2])


def all_sites(own: Path) -> list[Path]:
    """The site folders under sites/, in number order; anything else there is
    not a site."""
    held = Path(own) / SITES_FOLDER
    if not held.is_dir():
        return []
    return sorted((path for path in held.iterdir()
                   if _NAME.fullmatch(path.name) and path.is_dir()), key=_number)


def _record(own: Path) -> dict:
    """sites.json as this Pressless wrote it, else {}. An OSError other than
    its absence is the caller's: a file that is there but cannot be read
    now is never written over."""
    return json_record.read(Path(own) / OPEN_FILE, strict=True)


def _write(own: Path, **changes: object) -> None:
    json_record.write(Path(own) / OPEN_FILE, {**_record(own), **changes})


def _write_open(own: Path, name: str) -> None:
    _write(own, open=name)


def open_site(own: Path) -> Path:
    """The open site's folder. Where sites.json names no site there is, the
    lowest-numbered one opens, made as site-1 where there is none, and
    sites.json is written to say so. Where sites.json cannot be read now,
    the lowest opens and the file is left as it is."""
    try:
        named, readable = _record(own).get("open"), True
    except OSError:
        named, readable = None, False
    if isinstance(named, str) and _NAME.fullmatch(named) \
            and (Path(own) / SITES_FOLDER / named).is_dir():
        return Path(own) / SITES_FOLDER / named
    held = all_sites(own)
    site = held[0] if held else Path(own) / SITES_FOLDER / "site-1"
    site.mkdir(parents=True, exist_ok=True)
    if readable:
        _write_open(own, site.name)
    return site


def new_site(own: Path) -> Path:
    """Make the next site's folder, one past the highest ever made, and
    return it. sites.json keeps that number, so a removed site's number,
    and with it its keys and backups, never goes to another (§ 4.1)."""
    held = all_sites(own)
    made = _record(own).get("made")
    highest = max(_number(held[-1]) if held else 0,
                  made if isinstance(made, int) and not isinstance(made, bool) else 0)
    site = Path(own) / SITES_FOLDER / f"site-{highest + 1}"
    site.mkdir(parents=True)
    _write(own, made=highest + 1)
    return site


def remove(site: Path) -> None:
    """Remove a site's folder, its copy already kept. It is renamed first, so a site half
    deleted is never listed; a rename's OSError leaves it whole, and what a delete leaves
    behind under the new name is no site."""
    going = site.with_name(f"{_REMOVING}{site.name}-{secrets.token_hex(4)}")
    site.rename(going)
    shutil.rmtree(going, ignore_errors=True)


def aside(site: Path) -> Path:
    """A fresh name beside `site` to move it to while a file opened as a site
    takes its place (PRESS-0224 § 4.4 step 5). It carries the site's name,
    so clear_leftovers can put back one a stopped open left."""
    return site.with_name(f"{_REPLACED}{site.name}-{secrets.token_hex(8)}")


def clear_leftovers(own: Path) -> None:
    """At start, behind the folder's lock: what a stopped remove or open left
    under sites/. A removed site's copy is already kept, so it goes. A site
    moved aside comes back where nothing took its place, else it goes."""
    held = Path(own) / SITES_FOLDER
    if not held.is_dir():
        return
    for path in held.iterdir():
        if path.name.startswith(_REMOVING):
            shutil.rmtree(path, ignore_errors=True)
        elif path.name.startswith(_REPLACED):
            name = path.name.removeprefix(_REPLACED).rpartition("-")[0]
            if _NAME.fullmatch(name) and not (held / name).exists():
                with contextlib.suppress(OSError):   # tried again at the next start
                    path.rename(held / name)
            else:
                shutil.rmtree(path, ignore_errors=True)


def choose(own: Path, name: str) -> None:
    """Name the site the next start opens. A name that is not a site folder
    under sites/ raises ValueError and writes nothing."""
    if not _NAME.fullmatch(name) or not (Path(own) / SITES_FOLDER / name).is_dir():
        raise ValueError("that is not one of the sites")
    _write_open(own, name)


def move_in(own: Path) -> OSError | None:
    """§ 4.3: move the one site an older Pressless kept at the top into
    sites/site-1. Every step is a rename inside one drive, so a stop part way
    leaves sites/.moving, and the next start finishes. Returns the failure
    where a rename failed, for __main__ to word; nothing is ever deleted."""
    own = Path(own)
    held = own / SITES_FOLDER
    moving = held / _MOVING
    if held.is_dir() and not moving.is_dir():
        return None
    present = [name for name in sorted(SITE_NAMES) if (own / name).exists()]
    if not present and not moving.is_dir():
        return None
    try:
        moving.mkdir(parents=True, exist_ok=True)
        for name in present:
            (own / name).rename(moving / name)
        moving.rename(held / "site-1")
        _write_open(own, "site-1")
    except OSError as exc:
        return exc
    return None


def account(kind: str, site: Path) -> str:
    """§ 4.5: the name a site's key is filed under. Site 1 keeps the name an
    older Pressless filed its key under, so the move touches no keyring, and
    so does a folder that is no numbered site, as a development run's is."""
    name = Path(site).name
    return f"{kind}-{name}" if _NAME.fullmatch(name) and name != "site-1" else kind
