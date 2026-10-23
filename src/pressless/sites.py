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

import json
import re
from pathlib import Path

from pressless.safe_write import write_whole

SITES_FOLDER = "sites"
OPEN_FILE = "sites.json"
_MOVING = ".moving"
_NAME = re.compile(r"site-[1-9][0-9]*")

# § 4.2: what belongs to a site, moved into site-1 by move_in.
SITE_NAMES = frozenset({
    "published", "drafts", "bin", "pages", "furniture", "pages-waiting",
    "furniture-waiting", "templates", "comments", "photographs", "files", "forwards",
    "options", "identity", "look", "settings.json", "credentials.json", "site",
    "preview", "preview-assets", "starter-unpublished", "insights.json", "fetch",
    "wizards", "choices.json", "import",
})
# § 4.2: what belongs to the machine, left at the top.
MACHINE_NAMES = frozenset({
    "pressless.log", "pressless.log.1", "updates.json", "update.log", "pressless.lock",
    "theme.json", "usage.json", "usage-sent.json", "backups.json", OPEN_FILE, SITES_FOLDER,
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


def _write_open(own: Path, name: str) -> None:
    write_whole(Path(own) / OPEN_FILE, json.dumps({"version": 1, "open": name}) + "\n",
                prefix=f".{OPEN_FILE}.")


def _named(own: Path) -> str | None:
    try:
        data = json.loads((Path(own) / OPEN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    name = data.get("open")
    return name if isinstance(name, str) and _NAME.fullmatch(name) else None


def open_site(own: Path) -> Path:
    """The open site's folder. Where sites.json names no site there is, the
    lowest-numbered one opens, made as site-1 where there is none, and
    sites.json is written to say so."""
    named = _named(own)
    if named is not None and (Path(own) / SITES_FOLDER / named).is_dir():
        return Path(own) / SITES_FOLDER / named
    held = all_sites(own)
    site = held[0] if held else Path(own) / SITES_FOLDER / "site-1"
    site.mkdir(parents=True, exist_ok=True)
    _write_open(own, site.name)
    return site


def new_site(own: Path) -> Path:
    """Make the next site's folder, one past the highest, and return it."""
    held = all_sites(own)
    site = Path(own) / SITES_FOLDER / f"site-{_number(held[-1]) + 1 if held else 1}"
    site.mkdir(parents=True)
    return site


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
