"""Credentials — where the two secrets are kept, and how they are reached.

The contract is docs/specs/PRESS-0002-credentials.md. This module imports no
other part of Pressless (§5 INV-1): it is handed the store name, the folder
and the account, and never reads Settings itself.

It never writes a secret anywhere but the chosen store, never words anything
for the writer, and never decides whether a store is good enough — it raises
typed failures and reports which store answered (§4.5). The Face turns those
into sentences.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import keyring
import keyring.errors

SERVICE = "Pressless"            # what both secrets are filed under in the store
PROBE = "pressless-store-probe"  # the account choose() round-trips; never a secret
FILE_NAME = "credentials.json"   # the fallback file, in Pressless's own folder
FILE_VERSION = 1

# What choose() round-trips. Never a secret: it is written into whatever store
# answers, and §4.6's whole point is that one of those may be a plain file.
_PROBE_VALUE = "pressless-store-probe-value"

_FILE = "file"
_KEYRING = "keyring"


@dataclass(frozen=True)
class Choice:
    store: str      # "keyring" or "file" -- goes straight into Settings.credentials.store
    name: str       # the store that answered, as the library identifies it


class NoStore(Exception):
    """Nowhere safe to keep it — setup stops."""


class NotStored(Exception):
    """The store works and holds nothing here."""


class CredentialError(Exception):
    """A store we will not act on."""


def choose() -> Choice:
    """Ask this machine which store it has. Setup's question, asked once.

    Writes the probe, asks the store's members which of them returns that
    value, and only then deletes it — the walk needs the value still to be
    there (§4.2). Takes no folder: it is a question about the machine.
    """
    store = keyring.get_keyring()
    try:
        store.set_password(SERVICE, PROBE, _PROBE_VALUE)
    except keyring.errors.NoKeyringError as exc:
        # NoKeyringError is the discriminator and the only one (§4.2).
        # Absence and malfunction both arrive as a raised exception, so
        # without naming the type the fallback either never runs or runs
        # while a working store sits merely locked.
        if _is_windows():
            raise NoStore(
                "this machine has no credential store Pressless can use, and "
                "Pressless will not keep a secret in a file on Windows"
            ) from exc
        return Choice(_FILE, _FILE)
    except Exception as exc:
        raise CredentialError(
            f"this machine's credential store could not be used: {exc}"
        ) from exc

    try:
        answering = _answering_member(store)
    finally:
        _delete_probe(store)

    if answering is None:
        raise CredentialError(
            "this machine's credential store accepted a value, and no part of "
            "it returned that value when asked"
        )
    return Choice(_KEYRING, answering)


def read(store: str, folder: Path, account: str) -> str:
    """Return the secret filed under `account`, as a str, or raise.

    NotStored where the store works and holds nothing — absent and broken are
    different on purpose (§4.3): sending the writer to re-enter a key he
    still has is how the one he has gets overwritten.
    """
    if store == _FILE:
        return _read_file(Path(folder), account)
    if store == _KEYRING:
        return _read_keyring(account)
    raise CredentialError(f"{store!r} is not a store this Pressless knows")


def write(store: str, folder: Path, account: str, secret: str) -> None:
    """File `secret` under `account` in the chosen store.

    Every failure is typed. An OSError allowed to escape here would reach the
    Face's last-resort catch, and the writer would be told that something
    unexpected went wrong after failing to save his key (§4.3).
    """
    if store == _FILE:
        _write_file(Path(folder), account, secret)
        return
    if store == _KEYRING:
        try:
            keyring.get_keyring().set_password(SERVICE, account, secret)
        except Exception as exc:
            raise CredentialError(
                f"this machine's credential store could not be written: {exc}"
            ) from exc
        return
    raise CredentialError(f"{store!r} is not a store this Pressless knows")


def _is_windows() -> bool:
    """Read at call time, so the platform is what a test patches (spec §7)."""
    return sys.platform.startswith("win")


def _members(store):
    """The store's members, in the order the library would ask them.

    A chain answers with its first member that answers AT ALL, so a member
    that answers unconditionally masks every member behind it — including the
    plaintext one §4.6 found there. Asking the members directly is the only
    way the store that really holds the value can be named. A store that is
    not a chain is its own single member.
    """
    return tuple(getattr(store, "backends", None) or (store,))


def _answering_member(store) -> str | None:
    for member in _members(store):
        try:
            answer = member.get_password(SERVICE, PROBE)
        except Exception:
            continue  # a member that cannot answer is not the one holding it
        if isinstance(answer, str) and answer == _PROBE_VALUE:
            return str(getattr(member, "name", None) or type(member).__name__)
    return None


def _delete_probe(store) -> None:
    """Best effort, and last. The probe is not a secret, and a store that
    will not give it up is not a reason to refuse one that answered."""
    try:
        store.delete_password(SERVICE, PROBE)
    except Exception:
        pass


def _read_keyring(account: str) -> str:
    try:
        answer = keyring.get_keyring().get_password(SERVICE, account)
    except Exception as exc:
        raise CredentialError(
            f"this machine's credential store could not be read: {exc}"
        ) from exc
    if not isinstance(answer, str):
        # Not a str means nothing is stored, and that is measured rather than
        # chosen (§4.3, §4.6): here an absent secret comes back as a truthy
        # object and never as None. The answer is not returned, not named in
        # this message, and above all not CALLED — calling it opens a hidden
        # password prompt that hangs the app.
        raise NotStored(
            f"this machine's credential store holds nothing for {account!r}"
        )
    return answer


def _read_file(folder: Path, account: str) -> str:
    target = folder / FILE_NAME
    raw = _read_mapping(target)
    if raw is None:
        raise NotStored(f"there is no {target}")

    version = raw.get("version")
    if version != FILE_VERSION:
        raise CredentialError(
            f"{target} has version {version!r}; this Pressless reads "
            f"version {FILE_VERSION}"
        )

    secrets = raw.get("secrets")
    if not isinstance(secrets, dict):
        raise CredentialError(f"{target} is missing secrets, or it is not an object")

    value = secrets.get(account)
    if not isinstance(value, str):
        raise NotStored(f"{target} holds nothing for {account!r}")
    return value


def _write_file(folder: Path, account: str, secret: str) -> None:
    # §3 decision 1, applied wherever the file store is REACHED rather than
    # only where it is chosen, so a settings file carried from another
    # machine cannot open the hole that decision closes. read() carries no
    # such refusal: reading one back is how such a machine is recovered.
    if _is_windows():
        raise NoStore(
            "Pressless will not keep a secret in a file on Windows: os.chmod "
            "there sets only the read-only flag, so the file would be "
            "readable by anyone on this PC"
        )

    target = folder / FILE_NAME
    # Read first and replace one entry, so the other secret survives (§4.4).
    carried = _read_mapping(target) or {}
    existing = carried.get("secrets")
    data = dict(carried)
    data["version"] = FILE_VERSION
    data["secrets"] = {
        **(existing if isinstance(existing, dict) else {}),
        account: secret,
    }

    # mkstemp then os.replace: atomic, and mkstemp creates its file
    # owner-only, a mode os.replace carries onto the target (§4.6). So the
    # file is private from the instant it exists, and no chmod follows a
    # write that has already left a readable file behind.
    try:
        handle, temporary = tempfile.mkstemp(
            dir=str(folder), prefix=".credentials-", suffix=".tmp"
        )
    except OSError as exc:
        raise CredentialError(f"{target} could not be written: {exc}") from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, target)
    except OSError as exc:
        _discard(temporary)
        raise CredentialError(f"{target} could not be written: {exc}") from exc
    except BaseException:
        _discard(temporary)
        raise


def _read_mapping(target: Path) -> dict | None:
    """The file as a mapping, or None where there is no file. Raises where
    saving over it would discard what could not be parsed (§4.3)."""
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CredentialError(f"{target} could not be read: {exc}") from exc

    try:
        raw = json.loads(text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CredentialError(f"{target} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise CredentialError(f"{target} holds {type(raw).__name__}, not an object")
    return raw


def _discard(temporary: str) -> None:
    """Leave nothing behind in the folder but the credentials file."""
    try:
        os.unlink(temporary)
    except OSError:
        pass
