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
import re
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path

import pressless.safe_write as safe_write
from pressless.safe_write import write_whole
from pressless.words import ENGLISH

FILE_NAME = "settings.json"

# The file's version, not the dataclass's (§4.2). save() always writes it;
# load() accepts this and nothing else, because a file written by a later
# Pressless is not one this build may guess at.
FILE_VERSION = 1

_STORES = ("keyring", "file")

# Neither half of a GitHub owner/name holds anything else, so this states the
# shape §4.3 requires rather than guessing at it. The value goes straight into
# an API URL, where "?", "#", "%" and whitespace change what is asked for or
# truncate it (PRESS-0066).
_NAME_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)

_MEASUREMENT_ID = re.compile(r"\AG-[A-Z0-9]+\Z")   # PRESS-0199 § 4.1

# §4.3: http or https, a host of ASCII letters, digits, "." and "-", an optional
# port, and "/"-separated path segments, with an optional trailing "/". The
# address is joined into sitemap.xml and robots.txt (PRESS-0008 §4.9), where a
# query, a fragment, a "%" or whitespace carries an address the site does not
# serve. A pattern rather than a parse, because INV-1 keeps urllib out.
_SITE_ADDRESS = re.compile(
    r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~-]+)*/?"
)


@dataclass(frozen=True)
class Credentials:
    """Where the two secrets are kept — never the secrets (§4.5)."""

    store: str                    # "keyring" or "file" -- ADR-0003's two paths
    github_account: str           # the keyring account name, or the file's key name
    google_account: str | None    # the keyring account name, or the file's key
                                  # name; None where the dashboard was declined


@dataclass(frozen=True)
class Settings:
    site_folder: Path             # where the Builder writes the finished site
    repository: str               # "owner/name" on GitHub
    site_address: str             # its absolute address, joined into the sitemap
    daily_prompt_filter: str      # fnmatch glob, matched per tag (§4.2)
    untouchable: tuple[str, ...]  # repository-root entries the Publisher leaves alone
    credentials: Credentials      # where the two secrets are kept -- never the secrets
    analytics_property_id: str | None  # the NUMERIC property id, not the G-... tag
    # PRESS-0199 § 4.1: the G-... id the counting code carries; optional on
    # load, so a file written before it loads as None.
    measurement_id: str | None = None


class NotSetUp(Exception):
    """No settings file yet — run setup."""


class SettingsNotice(UserWarning):
    """Something the caller should know that is not a failure (§4.1).

    Emitted where the filesystem would not grant the file owner-only (INV-8).
    Its own category rather than the Store's `StoreNotice`, because Settings
    may import no other part, the Store included (§5 INV-1).

    One notice per save. Suppressing repeats is the caller's: the default
    warnings filter shows a repeat once, but a caller that CAPTURES sees every
    one -- and capturing is what the Face must do to render it.

    Raised with a key in the words table and its slots, as StoreNotice is
    (PRESS-0242).
    """

    def __init__(self, key: str, **slots: str) -> None:
        super().__init__(ENGLISH[key].format_map(slots))
        self.key, self.slots = key, slots


class SettingsError(Exception):
    """A settings file we will not act on.

    `key` names the top-level setting a shape refusal refuses, and is None for
    a refusal of the file itself -- its reading, its JSON, its version, a
    missing or mistyped field. Setup reads it to tell a refused answer from a
    file it must leave alone (PRESS-0021 § 4.1).
    """

    def __init__(self, message: str, key: str | None = None) -> None:
        super().__init__(message)
        self.key = key


def _why(exc: OSError) -> str:
    """The reason an OSError carries, never its own words.

    `str(exc)` on a stock file error quotes the path it failed on, and
    `docs/design.md` § Logging forbids a full filesystem path in anything
    Pressless shows or writes down. `strerror` is the reason alone, and it
    is absent on an OSError raised without one, so the type stands in.

    Copied rather than shared: §5 INV-1 lets this module import no
    `pressless` module but `safe_write`, whose contract is the file-writing
    steps alone, so a shared copy would need INV-1 changed first.
    """
    return exc.strerror or type(exc).__name__


def path_for(folder: Path) -> Path:
    return Path(folder) / FILE_NAME


def retired_site_name(folder: Path) -> str | None:
    """The site name a Pressless from before PRESS-0213 kept here, where it is
    one non-blank line -- the Store's rule for a name, written out because
    this module imports no other part (§5 INV-1). None otherwise, and never
    raises (PRESS-0213 § 4.2)."""
    try:
        raw = json.loads(path_for(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    name = raw.get("site_name") if isinstance(raw, dict) else None
    if not isinstance(name, str) or not name.strip() or "\n" in name or "\r" in name:
        return None
    return name


def _read(target: Path, *, saving: bool) -> dict | None:
    """The settings file's raw mapping, or None where there is no file.

    load() and save() judge the file by this one check, so a file one refuses
    the other refuses too (PRESS-0053). `saving` picks the wording: a refused
    save says what saving over the file would do. Raises SettingsError for a
    file that cannot be read, decoded, parsed, is not an object, or carries a
    version other than this build's.
    """
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as exc:
        # A UnicodeDecodeError is a ValueError and NOT an OSError, so without
        # this arm it escaped as something in neither of this module's
        # families -- §4.3 has this row, and the Face has nothing to report
        # it with (PRESS-0049).
        raise SettingsError(
            "the settings file is not readable as UTF-8, so it cannot be parsed: "
            f"{exc}"
        ) from exc
    except OSError as exc:
        raise SettingsError(
            f"the settings file could not be read: {_why(exc)}"
        ) from exc

    try:
        raw = json.loads(text)
    except (ValueError, RecursionError) as exc:
        # RecursionError is not a ValueError, so deeply nested JSON needs its
        # own arm -- §4.3 has this row (PRESS-0066).
        lost = (", so saving over it would discard what could not be parsed"
                if saving else "")
        raise SettingsError(f"the settings file is not valid JSON{lost}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError(f"the settings file holds {type(raw).__name__}, not an object")

    version = raw.get("version")
    # The type is checked as well as the value. A bool IS an int in Python, so
    # `!=` alone accepted `true`, and a float 1.0 compares equal to 1 too.
    # §4.3 refuses anything that is not the number 1 (PRESS-0066). A save
    # refuses it too: carrying unknown keys forward under this build's own
    # version stamp would relabel a file another Pressless wrote (PRESS-0053).
    if type(version) is not int or version != FILE_VERSION:
        if saving:
            raise SettingsError(
                f"the settings file has version {version!r}; this Pressless "
                f"writes version {FILE_VERSION}, and saving over it would "
                "relabel a file written by another"
            )
        raise SettingsError(
            f"the settings file has version {version!r}; this Pressless reads "
            f"version {FILE_VERSION}"
        )
    return raw


def load(folder: Path) -> Settings:
    """Read the settings file in `folder`.

    Raises NotSetUp where there is no file, and SettingsError for a file
    there is no safe way to act on. The two are distinguishable on purpose:
    sending a writer to setup over a file he could have fixed overwrites it
    (§5 INV-2). Nothing here writes.
    """
    raw = _read(path_for(folder), saving=False)
    if raw is None:
        raise NotSetUp("there is no settings file")

    site_folder = _required(raw, "site_folder", str)
    repository = _required(raw, "repository", str)
    site_address = _required(raw, "site_address", str)
    daily_prompt_filter = _required(raw, "daily_prompt_filter", str)
    untouchable = _required(raw, "untouchable", list)
    credentials = _required(raw, "credentials", dict)
    store = _required(credentials, "store", str, "credentials.")
    github_account = _required(credentials, "github_account", str, "credentials.")
    google_account = _optional(credentials, "google_account", str, "credentials.")
    analytics_property_id = _optional(raw, "analytics_property_id", str)
    measurement_id = _optional(raw, "measurement_id", str)

    loaded = Settings(
        site_folder=Path(site_folder),
        repository=repository,
        site_address=site_address,
        daily_prompt_filter=daily_prompt_filter,
        untouchable=tuple(untouchable),
        credentials=Credentials(
            store=store,
            github_account=github_account,
            google_account=google_account,
        ),
        analytics_property_id=analytics_property_id,
        measurement_id=measurement_id,
    )
    check(loaded)
    return loaded


def check(settings: Settings) -> None:
    """Refuse a Settings whose values have a shape no other part can use.

    Every shape rule load() applies lives here and only here, so setup can
    check the answers it is about to save against the rules the next launch
    reads them with (PRESS-0021 § 4.1). Raises SettingsError naming the
    top-level key it refuses. Stops at the first refusal.
    """
    for index, entry in enumerate(settings.untouchable):
        if not isinstance(entry, str):
            raise SettingsError(
                f"untouchable[{index}] is "
                f"{type(entry).__name__}, not a name",
                "untouchable",
            )
        # Shape, not merely type (§4.3). PRESS-0009 §4.4 matches an entry
        # against a path's FIRST segment, so one naming a path inside a
        # directory protects nothing -- not even itself -- while reading as
        # configured. A trailing slash is left alone: it names one root
        # entry unambiguously, and the Publisher ignores it (PRESS-0044).
        if not entry.rstrip("/") or "/" in entry.rstrip("/"):
            raise SettingsError(
                f"untouchable[{index}] is {entry!r}, which is not "
                "a repository-root name; an entry naming a path inside a "
                "directory protects nothing",
                "untouchable",
            )

    # Shape, not merely type. `repository`, `store` and `site_folder` are
    # contracts other parts read: a str holding "ownername", "vault" or
    # "site" is present and correctly typed, and the part that meets it
    # later has less to say about it than this one does (§4.3).
    if not Path(settings.site_folder).is_absolute():
        raise SettingsError(
            "site_folder is not an absolute path", "site_folder"
        )
    owner, _, name = settings.repository.partition("/")
    # The character check subsumes the second-slash one that stood here: "/"
    # is not a name character either (PRESS-0066).
    # "." and ".." are made of name characters, but in the API URL they are dot
    # segments, which resolve to a different path than the one typed
    # (PRESS-0171).
    if (not owner or not name or not _NAME_CHARS.issuperset(owner + name)
            or {owner, name} & {".", ".."}):
        raise SettingsError(
            "repository is not \"owner/name\"", "repository"
        )
    # Shape, like repository. It identifies the site, so the refusal names the
    # key and never quotes the value (§4.3).
    if not _SITE_ADDRESS.fullmatch(settings.site_address):
        raise SettingsError(
            "site_address is not an absolute http or https address the "
            "sitemap can carry",
            "site_address",
        )
    store = settings.credentials.store
    if store not in _STORES:
        raise SettingsError(
            f"credentials.store is {store!r}, not one of "
            f"{' or '.join(repr(s) for s in _STORES)}",
            "credentials",
        )
    # Shape, like the three above. §4.2 fixes this as the numeric property id
    # and says the G-... tag is a different identifier that fails every fetch,
    # so a pasted tag reached Google as a 404 the writer could not read
    # (PRESS-0056). isascii() as well, because isdigit() is true of full-width
    # and superscript digits, which Google's URL is not.
    property_id = settings.analytics_property_id
    if property_id is not None and not (property_id.isascii() and property_id.isdigit()):
        raise SettingsError(
            f"analytics_property_id is {property_id!r}, "
            "not the numeric property id; the tag in the site's footer is a "
            "different identifier and fails every fetch",
            "analytics_property_id",
        )
    # PRESS-0199 § 4.1: the Builder writes this into every published page, so
    # its shape is what keeps the tag from carrying anything else.
    measurement_id = settings.measurement_id
    if measurement_id is not None and not _MEASUREMENT_ID.fullmatch(measurement_id):
        raise SettingsError(
            "measurement_id is not Google's G- id for the counting code",
            "measurement_id",
        )


def save(folder: Path, settings: Settings, *, retire: tuple[str, ...] = ()) -> None:
    """Write `settings` into `folder`, whole or not at all.

    A temporary file beside the target, then os.replace, which is atomic on
    both systems: a crash mid-save leaves either the old file or the new one,
    never a truncated one (§4.4). Keys this build does not recognise are
    carried through, so a newer Pressless can write one an older then saves
    over. No existing file is not an error — the first save, at setup, has
    nothing to carry. `retire` names carried keys to leave out, which only the
    site name's move to the Store does (PRESS-0213 § 4.3).
    """
    target = path_for(folder)
    carried = _read(target, saving=True) or {}

    data = {key: value for key, value in carried.items() if key not in retire}
    data.update({
        "version": FILE_VERSION,
        "site_folder": str(settings.site_folder),
        "repository": settings.repository,
        "site_address": settings.site_address,
        "daily_prompt_filter": settings.daily_prompt_filter,
        "untouchable": list(settings.untouchable),
        "credentials": {
            "store": settings.credentials.store,
            "github_account": settings.credentials.github_account,
            "google_account": settings.credentials.google_account,
        },
        "analytics_property_id": settings.analytics_property_id,
        "measurement_id": settings.measurement_id,
    })

    # newline is named rather than left to the platform: §4.2's file is a
    # shape the installation carries between machines, so its bytes may not
    # depend on which system wrote it (PRESS-0039). The check runs on the raw
    # descriptor, before a byte is written (§4.4).
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        write_whole(target, text, prefix=".settings-",
                    check=lambda handle: _report_a_wide_grant(handle, target))
    except OSError as exc:
        raise SettingsError(
            f"the settings file could not be written: {_why(exc)}"
        ) from exc


def _is_windows() -> bool:
    """Read at call time, so a test can patch this module's platform test
    alone (§4.4). The platform rule itself, and why it is not `os.name`, is
    safe_write._is_windows."""
    return safe_write._is_windows()


def _report_a_wide_grant(handle: int, target: Path) -> None:
    """Say so where the mount granted more than owner-only (§4.4, INV-8).

    Read off the DESCRIPTOR, as `credentials.py` does (PRESS-0042): that is the
    one call reporting what the mount actually granted, where `mkstemp` only
    asked. The predicate is Credentials' `& 0o077` -- any group or other bit --
    and not `tests/_mode_support.py`'s exact `0600`, which asks the different
    question of whether the mount enforces modes at all.

    Credentials REFUSES here and this reports: §4.5 keeps every secret out of
    this file, so refusing would stop the writer using Pressless from a memory
    stick in order to protect nothing.

    Windows is outside it: `mkstemp` never grants `0600` there, so the grant is
    identical in the case that must report and the case that must not, and
    INV-7 forbids opening anything outside `folder` to find another signal.
    """
    if _is_windows():
        return
    granted = stat.S_IMODE(os.fstat(handle).st_mode)
    if granted & 0o077:
        warnings.warn(SettingsNotice("notice.settings.not_private", mode=f"{granted:03o}"),
                      stacklevel=2)


def _required(mapping: dict, key: str, kind: type, prefix: str = ""):
    if key not in mapping:
        raise SettingsError(f"the settings file is missing {prefix}{key}")
    value = mapping[key]
    if not isinstance(value, kind):
        raise SettingsError(
            f"{prefix}{key} is {type(value).__name__}, "
            f"not {kind.__name__}"
        )
    return value


def _optional(mapping: dict, key: str, kind: type, prefix: str = ""):
    """Absent and null both read as None (§4.2). Two fields carry a declined
    dashboard, and ADR-0005 makes that step declinable — requiring either
    would leave a declined setup unable to load at all."""
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, kind):
        raise SettingsError(
            f"{prefix}{key} is {type(value).__name__}, "
            f"not {kind.__name__} or absent"
        )
    return value
