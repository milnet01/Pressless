"""Settings — what is true of this machine and this site, and nothing else.

The contract is docs/specs/PRESS-0001-settings.md. Settings depends on
nothing: no Store, no network, no other part of Pressless. It is handed its
folder and never derives one (§3 decision 2).

Every read and write names UTF-8. JSON is UTF-8 by definition, and Python's
default text encoding is the locale's — cp1252 on Windows — so a site_folder
holding an accented character would be written here and unreadable there.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

FILE_NAME = "settings.json"

# The file's version, not the dataclass's (§4.2). save() always writes it;
# load() accepts this and nothing else, because a file written by a later
# Pressless is not one this build may guess at.
FILE_VERSION = 1

_STORES = ("keyring", "file")


@dataclass(frozen=True)
class Credentials:
    """Where the two secrets are kept — never the secrets (§4.5)."""

    store: str                    # "keyring" or "file" -- ADR-0003's two paths
    github_account: str           # the keyring account name, or the file's key name
    google_account: str | None    # None where the dashboard was declined


@dataclass(frozen=True)
class Settings:
    site_folder: Path             # where the Builder writes the finished site
    repository: str               # "owner/name" on GitHub
    daily_prompt_filter: str      # fnmatch glob, matched per tag (§4.2)
    untouchable: tuple[str, ...]  # repository-root entries the Publisher leaves alone
    credentials: Credentials      # where the two secrets are kept -- never the secrets
    analytics_property_id: str | None  # the NUMERIC property id, not the G-... tag


class NotSetUp(Exception):
    """No settings file yet — run setup."""


class SettingsError(Exception):
    """A settings file we will not act on."""


def path_for(folder: Path) -> Path:
    return Path(folder) / FILE_NAME


def load(folder: Path) -> Settings:
    """Read the settings file in `folder`.

    Raises NotSetUp where there is no file, and SettingsError for a file
    there is no safe way to act on. The two are distinguishable on purpose:
    sending a writer to setup over a file he could have fixed overwrites it
    (§5 INV-2). Nothing here writes.
    """
    target = path_for(folder)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise NotSetUp(f"there is no settings file at {target}") from exc
    except OSError as exc:
        raise SettingsError(f"{target} could not be read: {exc}") from exc

    try:
        raw = json.loads(text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SettingsError(f"{target} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError(f"{target} holds {type(raw).__name__}, not an object")

    version = raw.get("version")
    if version != FILE_VERSION:
        raise SettingsError(
            f"{target} has version {version!r}; this Pressless reads "
            f"version {FILE_VERSION}"
        )

    site_folder = _required(raw, "site_folder", str, target)
    repository = _required(raw, "repository", str, target)
    daily_prompt_filter = _required(raw, "daily_prompt_filter", str, target)
    untouchable = _required(raw, "untouchable", list, target)
    credentials = _required(raw, "credentials", dict, target)

    for index, entry in enumerate(untouchable):
        if not isinstance(entry, str):
            raise SettingsError(
                f"{target}: untouchable[{index}] is "
                f"{type(entry).__name__}, not a name"
            )
        # Shape, not merely type (§4.3). PRESS-0009 §4.4 matches an entry
        # against a path's FIRST segment, so one naming a path inside a
        # directory protects nothing -- not even itself -- while reading as
        # configured. A trailing slash is left alone: it names one root
        # entry unambiguously, and the Publisher ignores it (PRESS-0044).
        if not entry.rstrip("/") or "/" in entry.rstrip("/"):
            raise SettingsError(
                f"{target}: untouchable[{index}] is {entry!r}, which is not "
                f"a repository-root name; an entry naming a path inside a "
                f"directory protects nothing"
            )

    store = _required(credentials, "store", str, target, "credentials.")
    github_account = _required(credentials, "github_account", str, target, "credentials.")
    google_account = _optional(credentials, "google_account", str, target, "credentials.")

    # Shape, not merely type. `repository`, `store` and `site_folder` are
    # contracts other parts read: a str holding "ownername", "vault" or
    # "site" is present and correctly typed, and the part that meets it
    # later has less to say about it than this one does (§4.3).
    if not Path(site_folder).is_absolute():
        raise SettingsError(
            f"{target}: site_folder is {site_folder!r}, which is not an "
            f"absolute path"
        )
    owner, _, name = repository.partition("/")
    if not owner or not name or "/" in name:
        raise SettingsError(
            f"{target}: repository is {repository!r}, not \"owner/name\""
        )
    if store not in _STORES:
        raise SettingsError(
            f"{target}: credentials.store is {store!r}, not one of "
            f"{' or '.join(repr(s) for s in _STORES)}"
        )

    return Settings(
        site_folder=Path(site_folder),
        repository=repository,
        daily_prompt_filter=daily_prompt_filter,
        untouchable=tuple(untouchable),
        credentials=Credentials(
            store=store,
            github_account=github_account,
            google_account=google_account,
        ),
        analytics_property_id=_optional(raw, "analytics_property_id", str, target),
    )


def save(folder: Path, settings: Settings) -> None:
    """Write `settings` into `folder`, whole or not at all.

    A temporary file beside the target, then os.replace, which is atomic on
    both systems: a crash mid-save leaves either the old file or the new one,
    never a truncated one (§4.4). Keys this build does not recognise are
    carried through, so a newer Pressless can write one an older then saves
    over. No existing file is not an error — the first save, at setup, has
    nothing to carry.
    """
    target = path_for(folder)
    carried = {}
    try:
        existing = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise SettingsError(f"{target} could not be read: {exc}") from exc
    else:
        try:
            carried = json.loads(existing)
        except (ValueError, UnicodeDecodeError) as exc:
            raise SettingsError(
                f"{target} is not valid JSON, so saving over it would discard "
                f"what could not be parsed: {exc}"
            ) from exc
        if not isinstance(carried, dict):
            raise SettingsError(f"{target} holds {type(carried).__name__}, not an object")

    data = dict(carried)
    data.update({
        "version": FILE_VERSION,
        "site_folder": str(settings.site_folder),
        "repository": settings.repository,
        "daily_prompt_filter": settings.daily_prompt_filter,
        "untouchable": list(settings.untouchable),
        "credentials": {
            "store": settings.credentials.store,
            "github_account": settings.credentials.github_account,
            "google_account": settings.credentials.google_account,
        },
        "analytics_property_id": settings.analytics_property_id,
    })

    try:
        handle, temporary = tempfile.mkstemp(
            dir=str(folder), prefix=".settings-", suffix=".tmp"
        )
    except OSError as exc:
        raise SettingsError(f"{target} could not be written: {exc}") from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, target)
    except OSError as exc:
        _discard(temporary)
        raise SettingsError(f"{target} could not be written: {exc}") from exc
    except BaseException:
        _discard(temporary)
        raise


def _required(mapping: dict, key: str, kind: type, target: Path, prefix: str = ""):
    if key not in mapping:
        raise SettingsError(f"{target} is missing {prefix}{key}")
    value = mapping[key]
    if not isinstance(value, kind):
        raise SettingsError(
            f"{target}: {prefix}{key} is {type(value).__name__}, "
            f"not {kind.__name__}"
        )
    return value


def _optional(mapping: dict, key: str, kind: type, target: Path, prefix: str = ""):
    """Absent and null both read as None (§4.2). Two fields carry a declined
    dashboard, and ADR-0005 makes that step declinable — requiring either
    would leave a declined setup unable to load at all."""
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, kind):
        raise SettingsError(
            f"{target}: {prefix}{key} is {type(value).__name__}, "
            f"not {kind.__name__} or absent"
        )
    return value


def _discard(temporary: str) -> None:
    """Leave nothing behind in the folder but the settings file (§5 INV-7)."""
    try:
        os.unlink(temporary)
    except OSError:
        pass
