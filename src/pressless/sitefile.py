"""A whole site as one .zip file, saved and opened again (PRESS-0224).

The contract is docs/specs/PRESS-0224-site-file.md. The file is a plain zip,
so any computer opens it without Pressless: a manifest naming the format, the
site's settings with no path in them, and the site's files under their own
names. It never holds a key. A file to open may come from anyone, so every
member is checked before a byte is written, and a refused file writes nothing.
"""
from __future__ import annotations

import errno
import json
import os
import secrets
import shutil
import stat
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from pressless import credentials, editor, progress, settings, sites, starter, store, zip_member
from pressless.safe_write import write_whole
from pressless.words import say

MANIFEST = "pressless-site.json"
FORMAT = "pressless-site"
VERSION = 1
# § 4.1: what stays out of every site file. Anything not named here travels.
LEFT_OUT = frozenset({
    "credentials.json",                    # a key
    "site", "preview", "jpeg-xl-views",    # rebuilt on demand from what travels
    "fetch",                               # a fetch area, emptied after each use
    "insights.json", "youtube.json",       # caches, fetched again
    "wizards", "choices.json",             # where he was last
    "import",                              # Import's export (PRESS-0125 § 4.2)
})
KEPT = sites.SITE_NAMES - LEFT_OUT
# Kept as they are: photographs and added files are compressed already.
_STORED = frozenset({"photographs", "files"})
SAVING = ".saving-"   # a site file being written; whole once renamed or handed over
_SPARE = 1024 * 1024 * 1024   # the drive keeps this much free after an open
MEMBERS_MOST = 100_000        # § 4.3: a file holding more members is refused
STEM_MOST = 60                # § 4.1: characters of the site's name in a file's name
_MANIFEST_MOST = 64 * 1024    # bytes; the manifest is two short fields
# What reading the zip or a member can raise, as check and the unpack do: a
# bad checksum, a locked or oddly packed member, a cut-short file, and JSON
# nested past Python's depth, whose RecursionError is a RuntimeError. Each is
# a refusal.
_UNREADABLE = (OSError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError,
               EOFError, zlib.error)
# What the opened settings can raise in _settle, a refusal too. Its OSError
# is the drive's, so it is not here.
_BAD_SETTINGS = (ValueError, RuntimeError, settings.SettingsError, store.StoreError)


class Refused(Exception):
    """The file is not one this Pressless opens. Says what failed, never a
    path; `newer` where a newer Pressless made it."""

    def __init__(self, message: str, *, newer: bool = False) -> None:
        super().__init__(message)
        self.newer = newer


def name_of(site: Path) -> str:
    """The site's own name, else the repository it publishes to, else the
    words for a site not set up yet (PRESS-0223 § 4.6)."""
    try:
        identity = store.read_identity(site)
    except store.StoreError:
        identity = None
    if identity is not None and identity.name.strip():
        return identity.name
    try:
        return settings.load(site).repository
    except (settings.NotSetUp, settings.SettingsError):
        return say("sites_screen.unnamed")


def stem(site: Path) -> str:
    """§ 4.1: the site's name kept to letters, digits, spaces and hyphens, its
    spaces collapsed and cut to STEM_MOST characters, for a file's name. The
    cut keeps a backup's whole path inside Windows' limit."""
    kept = "".join(c for c in name_of(site) if c.isalnum() or c in " -")
    return " ".join(kept.split())[:STEM_MOST].rstrip() or say("sites_screen.file_unnamed")


def _members(site: Path) -> list[tuple[str, Path]]:
    """Every file under each kept name, by its name in the file."""
    found = []
    for name in sorted(KEPT):
        top = site / name
        if top.is_file() and not top.is_symlink():
            found.append((name, top))
        elif top.is_dir() and not top.is_symlink():
            found.extend((path.relative_to(site).as_posix(), path)
                         for path in sorted(top.rglob("*"))
                         if path.is_file() and not path.is_symlink())
    return found


def save(site: Path, target: Path) -> None:
    """§ 4.2: write the site to `target`, a new zip. Holds the editor's lock,
    so no save or publish lands half in the file, but not while it packs the
    photographs and added files: those it links under the lock instead."""
    site = Path(site)
    linked: tuple[Path, list[tuple[str, Path]]] | None = None
    # A file dated before 1980 is ordinary in a hand-editable folder; zip
    # cannot record it, and strict timestamps would refuse the whole save.
    with zipfile.ZipFile(target, "w", strict_timestamps=False) as made:
        made.writestr(MANIFEST, json.dumps({"format": FORMAT, "version": VERSION}))
        try:
            with editor.LOCK:
                members = _members(site)
                linked = _link_stored(site, members)
                later = linked[1] if linked is not None else []
                waiting = {name for name, _ in later}
                now = [member for member in members if member[0] not in waiting]
                for done, (name, path) in enumerate(now):
                    progress.count("progress.packing", done, len(members))
                    _write_member(made, name, path)
            for done, (name, link) in enumerate(later, start=len(now)):
                progress.count("progress.packing", done, len(members))
                _write_member(made, name, link)
        finally:
            if linked is not None:
                shutil.rmtree(linked[0], ignore_errors=True)
        progress.count("progress.packing", len(members), len(members))


def _write_member(made: zipfile.ZipFile, name: str, path: Path) -> None:
    if name == settings.FILE_NAME:
        _write_settings(made, path)
        return
    kind = zipfile.ZIP_STORED if name.split("/")[0] in _STORED else zipfile.ZIP_DEFLATED
    made.write(path, name, compress_type=kind)


def _link_stored(site: Path, members: list[tuple[str, Path]]
                 ) -> tuple[Path, list[tuple[str, Path]]] | None:
    """§ 4.2: a hard link to each photograph and added file, in a fresh folder
    beside the site, so they are packed once the lock is let go. None is ever
    written in place -- a new one takes a new name -- so a link keeps the
    bytes the lock saw, even where the file is moved to the bin meanwhile.
    None where there are none, or the drive cannot link them, and then
    nothing is left."""
    stored = [(name, path) for name, path in members if name.split("/")[0] in _STORED]
    if not stored:
        return None
    folder = sites.throwaway(site.parent, sites.LINKED)
    try:
        folder.mkdir()   # never one another save is using
    except OSError:
        return None
    try:
        linked = []
        for number, (name, path) in enumerate(stored):
            link = folder / str(number)
            os.link(path, link)
            linked.append((name, link))
    except OSError:
        shutil.rmtree(folder, ignore_errors=True)
        return None
    return folder, linked


def _write_settings(made: zipfile.ZipFile, path: Path) -> None:
    """§ 4.2: settings.json with no path on this computer in it. One that is
    not a JSON object is left out, so a damaged file never stops the rest
    being saved; the opened site then goes to setup."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, RecursionError):
        return
    if not isinstance(held, dict):
        return
    held["site_folder"] = ""
    made.writestr(settings.FILE_NAME, json.dumps(held, indent=2) + "\n",
                  compress_type=zipfile.ZIP_DEFLATED)


def save_part(site: Path, folder: Path) -> Path:
    """Save the site to a fresh `.saving-<random>.zip` in `folder`, whole, and
    return it for the caller to rename or hand over. Nothing is left where
    the save fails (§ 4.2). Where the site would leave the drive less than
    _SPARE free, it raises ENOSPC and writes nothing, so a save never fills
    the drive other writes need."""
    folder = Path(folder)
    progress.count("progress.packing")   # before the lock, so a download says so
    if sum(path.stat().st_size for _, path in _members(Path(site))) \
            > shutil.disk_usage(folder).free - _SPARE:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
    part = folder / f"{SAVING}{secrets.token_hex(8)}.zip"
    try:
        save(site, part)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return part


def save_as(site: Path, target: Path) -> None:
    """Save the site to `target`, a name nothing holds, so that a file under
    that name is always whole."""
    part = save_part(site, Path(target).parent)
    try:
        part.rename(target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def _allowed(name: str) -> bool:
    """A member name that stays inside the site, under a kept name or the
    manifest, and names no Windows device, which a write would reach in
    place of a file."""
    if not zip_member.stays_inside(name):
        return False
    parts = PurePosixPath(name).parts
    return name == MANIFEST or (parts[0] in KEPT
                                and not any(map(store.windows_device, parts)))


def is_link(info: zipfile.ZipInfo) -> bool:
    """Whether a zip member is a symbolic link."""
    return stat.S_ISLNK(info.external_attr >> 16)


def check(source: Path, room: int) -> None:
    """§ 4.3: raise Refused unless every member may be unpacked, and they fit
    in `room` bytes. Writes nothing."""
    try:
        with zipfile.ZipFile(source) as held:
            infos = held.infolist()
            if len(infos) > MEMBERS_MOST:
                raise Refused("the file holds more files than a site does")
            try:
                found = held.getinfo(MANIFEST)
            except KeyError:
                raise Refused("the file has no Pressless manifest") from None
            if found.file_size > _MANIFEST_MOST:   # read whole, so its size first
                raise Refused("the file's manifest is not readable")
            try:
                manifest = json.loads(held.read(found))
            except (ValueError, RecursionError):
                raise Refused("the file's manifest is not readable") from None
    except _UNREADABLE as exc:
        raise Refused("the file is not a zip file Pressless can read") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise Refused("the file is not a saved Pressless site")
    version = manifest.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise Refused("the file's version is not one Pressless knows")
    if version > VERSION:
        raise Refused("a newer Pressless made the file", newer=True)
    for info in infos:
        if not _allowed(info.filename):
            raise Refused("the file holds a name outside a site")
        if is_link(info):
            raise Refused("the file holds a link")
        # save writes only these: anything else is locked, or packed in a way
        # zipfile cannot unpack.
        if info.flag_bits & 0x1 or info.compress_type not in (zipfile.ZIP_STORED,
                                                              zipfile.ZIP_DEFLATED):
            raise Refused("the file holds a member Pressless cannot unpack")
    if sum(info.file_size for info in infos) > room:
        raise Refused("the file is larger than the room on this drive")


def _room(own: Path) -> int:
    return shutil.disk_usage(own).free - _SPARE


def unused(site: Path) -> bool:
    """§ 4.4: no settings and nothing written, as on a fresh install. Loosen
    it with care: open_into writes an opened file over a site this calls
    unused, and deletes what was there; backups skip it too."""
    return not (site / settings.FILE_NAME).exists() and not store.holds_a_site(site)


def _settle(opened: Path, target: Path) -> None:
    """§ 4.4 step 4: point the site's settings at this computer, keeping every
    key it does not name. The starter's marker stays, but empty: consent to
    replace a site on GitHub is never taken from a file (PRESS-0126 § 4.5)."""
    marker = opened / starter.MARKER
    if marker.is_file():
        write_whole(marker, "", prefix=f".{starter.MARKER}.")
    path = opened / settings.FILE_NAME
    if not path.exists():
        return   # saved before setup: the opened site goes to setup
    held = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(held, dict):
        raise Refused("the file's settings are not readable")
    held["site_folder"] = str(target / "site")
    kept = held.get("credentials")
    if isinstance(kept, dict):
        try:
            kept["store"] = credentials.choose().store
        except (credentials.NoStore, credentials.CredentialError):
            pass   # Settings asks for the key as for any missing one
        # Every set-up site has a GitHub account name; Google's and
        # YouTube's are null until signed in, and stay so.
        kept["github_account"] = sites.account("github", target)
        if kept.get("google_account") is not None:
            kept["google_account"] = sites.account("google", target)
        if kept.get("youtube_account") is not None:
            kept["youtube_account"] = sites.account("youtube", target)
    write_whole(path, json.dumps(held, indent=2) + "\n", prefix=f".{settings.FILE_NAME}.")
    settings.load(opened)


def open_into(source: Path, own: Path) -> Path:
    """§ 4.4: open the file as a site in Pressless's own folder `own`, and
    name it the site the next start opens. Returns its folder. A refusal at
    any step leaves sites/ as it was, apart from an empty site-1 made where
    there was no site. Once the file is unpacked, an OSError is the drive's,
    no refusal, and reaches the caller as it is after the same cleanup; so
    does naming the site, the last step, after it is in place."""
    own = Path(own)
    check(source, _room(own))
    current = sites.current_site(own)
    opening = sites.throwaway(own / sites.SITES_FOLDER, sites.OPENING)
    opening.mkdir()   # never one another open is using
    made: Path | None = None
    try:
        try:
            _unpack(source, opening)
        except _UNREADABLE as exc:
            raise Refused("the file could not be opened as a site") from exc
        target = current if unused(current) else sites.new_site(own)
        if target != current:
            made = target
        try:
            _settle(opening, target)
        except _BAD_SETTINGS as exc:
            raise Refused("the file's settings are not readable") from exc
        _replace(target, opening)
        made = None
    except BaseException:
        _clean(opening, made)
        raise
    sites.choose(own, target.name)
    return target


def _unpack(source: Path, opening: Path) -> None:
    """§ 4.4 step 2: every member but the manifest, under `opening`."""
    with zipfile.ZipFile(source) as held:
        infos = held.infolist()
        whole = sum(info.file_size for info in infos)
        size = 0
        for done, info in enumerate(infos):
            progress.count("progress.unpacking", done, len(infos), size, whole)
            size += info.file_size
            if info.filename == MANIFEST:
                continue
            to = opening.joinpath(*PurePosixPath(info.filename).parts)
            if info.is_dir():
                to.mkdir(parents=True, exist_ok=True)
                continue
            to.parent.mkdir(parents=True, exist_ok=True)
            with held.open(info) as piece, open(to, "wb") as out:
                shutil.copyfileobj(piece, out)
        progress.count("progress.unpacking", len(infos), len(infos), whole, whole)


def _replace(target: Path, opening: Path) -> None:
    """§ 4.4 step 5, never losing `target` on the way (PRESS-0299): it moves
    aside, and comes back where the rename fails, so a refusal leaves sites/
    as it was. The aside name is fresh each time, so one left by a stopped
    open blocks nothing and is never mistaken for a site;
    sites.clear_leftovers puts it back or deletes it at the next start."""
    aside = sites.aside(target)
    target.rename(aside)
    try:
        opening.rename(target)
    except BaseException:
        aside.rename(target)
        raise
    shutil.rmtree(aside, ignore_errors=True)


def _clean(opening: Path, made: Path | None) -> None:
    shutil.rmtree(opening, ignore_errors=True)
    if made is not None:
        shutil.rmtree(made, ignore_errors=True)
