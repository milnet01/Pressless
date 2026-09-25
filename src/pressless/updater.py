"""The Updater: find the latest release, prove it, download it -- PRESS-0023.

The contract is docs/specs/PRESS-0023-self-update.md §§ 4.2-4.6. A release is
trusted only through its signed list (§ 4.3), which names the version and each
artefact's size and SHA-256; signing the version is what stops an old release
being served as new (INV-4). The address it came from is never the proof.

Every read is bounded or chunked, every open carries TIMEOUT_SECONDS, and no
redirect may leave https (INV-7). A check never raises (INV-5): it answers an
Offer or the Miss of the step that stopped it.

May not open the Store, Settings or Credentials, or call Marks, the Builder or
the Face (§ 4.1).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import ssl
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

import certifi
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from pressless import update_key
from pressless.installer import UpdateError

# The app's repository, not his site's. PRESSLESS_UPDATE_REPOSITORY replaces it
# for one run, which is how § 7.1 points a build at a scratch repository; it
# moves nothing trust rests on, since only TRUSTED makes a release an offer.
REPOSITORY = "milnet01/Pressless"
OVERRIDE = "PRESSLESS_UPDATE_REPOSITORY"
TIMEOUT_SECONDS = 30.0
FILE_NAME = "updates.json"

_API_LIMIT = 256 * 1024
_LIST_LIMIT = 16 * 1024
_SIG_SIZES = (64, 128, 192, 256)
_LARGEST = 512 * 1024 * 1024
_CHUNK = 64 * 1024
PLATFORMS = ("linux", "windows")


class DownloadFailed(UpdateError):
    """The download did not complete."""


class DownloadEndedEarly(DownloadFailed):
    """The stream ended before the size the signed list names (FIBR-0327)."""


class UpdateRejected(UpdateError):
    """The bytes are not the ones the signed list vouches for."""


@dataclass(frozen=True)
class Offer:
    version: str      # "X.Y.Z"
    asset_url: str    # https, the platform's artefact
    size: int         # from the signed list
    sha256: str       # from the signed list


@dataclass(frozen=True)
class Miss:
    step: int         # the step of § 4.4 that stopped the check


class Response(Protocol):
    status: int
    headers: dict[str, str]

    def read(self, n: int) -> bytes: ...  # at most n bytes; b"" at the end
    def close(self) -> None: ...


class Transport(Protocol):
    def open(self, url: str) -> Response: ...


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """Refuses a redirect to anything but https (INV-7). The Updater's own,
    not publisher._NoCrossOriginAuth: the two are not shared (rule 7)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.request.urlparse(newurl).scheme != "https":
            raise urllib.error.URLError("an update redirect left https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Urllib:
    """TLS verified against the bundled certifi set, not the host's store: the
    AppImage's OpenSSL looks where this distribution keeps nothing (§ 2
    problem 5)."""

    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        context = ssl.create_default_context(cafile=certifi.where())
        self._opener = urllib.request.build_opener(
            _HttpsOnly, urllib.request.HTTPSHandler(context=context))

    def open(self, url: str) -> Response:
        if not url.startswith("https://"):
            raise urllib.error.URLError("an update address is not https")
        request = urllib.request.Request(  # noqa: S310 -- https checked just above
            url, headers={"User-Agent": "Pressless"})
        try:
            return self._opener.open(request, timeout=self._timeout)
        except urllib.error.HTTPError as error:
            return error  # a status is an answer; the caller reads it


_VERSION = re.compile(r"v?([0-9]+)\.([0-9]+)\.([0-9]+)", re.ASCII)


def parse_version(text: str) -> tuple[int, int, int] | None:
    """Three dot-separated runs of ASCII digits, with an optional leading v.
    int() is not the guard: it accepts "1_0" and " 1" (finbreak D13)."""
    matched = _VERSION.fullmatch(text)
    if matched is None:
        return None
    major, minor, patch = (int(part) for part in matched.groups())
    return major, minor, patch


# ------------------------------------------------------------ updates.json ---


def read_state(folder: Path) -> tuple[bool, str | None]:
    """(check, skip). Missing, unparseable or wrong-shaped reads as on with
    nothing skipped, so the switch shows what is actually in force."""
    try:
        data = json.loads((Path(folder) / FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, None
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("check"), bool)
            or not (data.get("skip") is None or isinstance(data.get("skip"), str))):
        return True, None
    return data["check"], data["skip"]


def write_state(folder: Path, *, check: bool, skip: str | None) -> None:
    """Write the switch and the skipped version, replacing the file whole."""
    target = Path(folder) / FILE_NAME
    staging = target.with_name(f".{FILE_NAME}.{secrets.token_hex(4)}")
    text = json.dumps({"version": 1, "check": check, "skip": skip})
    try:
        with open(staging, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)


# ------------------------------------------------------------------ reads ---


def _read(transport: Transport, url: str, limit: int) -> bytes:
    """The whole body of a 200 answer, refused past `limit` bytes."""
    response = transport.open(url)
    try:
        if response.status != 200:
            raise OSError(f"status {response.status}")
        parts: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(_CHUNK, limit + 1 - total))
            if not chunk:
                return b"".join(parts)
            total += len(chunk)
            if total > limit:
                raise OSError("the answer is larger than its bound")
            parts.append(chunk)
    finally:
        response.close()


def _names(version: str) -> dict[str, str]:
    return {"list": f"Pressless-{version}-release.txt",
            "sig": f"Pressless-{version}-release.txt.sig",
            "linux": f"Pressless-{version}-x86_64.AppImage",
            "windows": f"Pressless-{version}-windows.zip"}


def _verifies(text: bytes, signatures: bytes) -> bool:
    """Any one signature against any one trusted key (§ 4.3)."""
    keys = []
    for encoded in update_key.TRUSTED:
        try:
            keys.append(Ed25519PublicKey.from_public_bytes(
                base64.b64decode(encoded, validate=True)))
        except ValueError:
            continue
    for start in range(0, len(signatures), 64):
        signature = signatures[start:start + 64]
        for key in keys:
            try:
                key.verify(signature, text)
            except InvalidSignature:
                continue
            return True
    return False


_SIZE = r"(0|[1-9][0-9]*)"
_SHA = r"([0-9a-f]{64})"
_LIST = re.compile(
    rb"pressless-release 1\n"
    rb"version ([0-9]+\.[0-9]+\.[0-9]+)\n"
    rb"linux (Pressless-[0-9.]+-x86_64\.AppImage) " + _SIZE.encode() + rb" " + _SHA.encode()
    + rb"\nwindows (Pressless-[0-9.]+-windows\.zip) " + _SIZE.encode() + rb" "
    + _SHA.encode() + rb"\n")


def parse_list(text: bytes) -> tuple[str, dict[str, tuple[str, int, str]]]:
    """(version, {platform: (name, size, sha256)}), or ValueError for a list
    that differs from § 4.3's shape in any byte."""
    matched = _LIST.fullmatch(text)
    if matched is None:
        raise ValueError("the release list is not in its shape")
    version = matched.group(1).decode("ascii")
    lines = {"linux": matched.groups()[1:4], "windows": matched.groups()[4:7]}
    parsed = {}
    for platform, (name, size, sha) in lines.items():
        name = name.decode("ascii")
        if name != _names(version)[platform]:
            raise ValueError("an artefact's name does not carry the list's version")
        parsed[platform] = (name, int(size), sha.decode("ascii"))
    return version, parsed


# ------------------------------------------------------------------ check ---


def check(folder: Path, running: str, platform: str,
          transport: Transport | None = None) -> Offer | Miss:
    """§ 4.4's steps; the first that fails is the Miss. Never raises."""
    step = 1
    try:
        wanted, skipped = read_state(folder)
        if not wanted:
            return Miss(1)
        transport = transport or _Urllib()
        repository = os.environ.get(OVERRIDE) or REPOSITORY

        step = 2
        release = json.loads(_read(
            transport, f"https://api.github.com/repos/{repository}/releases/latest",
            _API_LIMIT))
        if not isinstance(release, dict):
            raise ValueError("the release is not an object")

        step = 3
        tag = release.get("tag_name")
        found, current = parse_version(tag if isinstance(tag, str) else ""), parse_version(running)
        if found is None or current is None or found <= current:
            return Miss(3)
        version = ".".join(str(part) for part in found)
        if tag.removeprefix("v") != version or version == skipped:
            return Miss(3)

        step = 4
        names = _names(version)
        urls: dict[str, str] = {}
        assets = release.get("assets")
        for which in ("list", "sig", platform):
            matching = [asset for asset in assets if isinstance(asset, dict)
                        and asset.get("name") == names[which]]
            if len(matching) != 1:
                return Miss(4)
            url = matching[0].get("browser_download_url")
            if not isinstance(url, str) or not url.startswith("https://"):
                return Miss(4)
            urls[which] = url

        step = 5
        text = _read(transport, urls["list"], _LIST_LIMIT)
        signatures = _read(transport, urls["sig"], max(_SIG_SIZES))
        if len(signatures) not in _SIG_SIZES:
            return Miss(5)

        step = 6
        if not _verifies(text, signatures):
            return Miss(6)
        listed, artefacts = parse_list(text)

        step = 7
        if listed != version:
            return Miss(7)

        step = 8
        name, size, sha256 = artefacts[platform]
        if name != names[platform] or size > _LARGEST:
            return Miss(8)
        return Offer(version, urls[platform], size, sha256)
    except Exception:  # noqa: BLE001 -- INV-5: a failed check is silent
        return Miss(step)


# --------------------------------------------------------------- download ---


def download(offer: Offer, beside: Path, transport: Transport | None = None) -> Path:
    """Stream the artefact to a new owner-only file in `beside`, hashing as it
    goes (§ 4.6). The file is returned only when size and hash both match;
    every failure removes it."""
    transport = transport or _Urllib()
    target = Path(beside) / f".pressless-update-{secrets.token_hex(8)}"
    try:
        handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_BINARY", 0), 0o600)
    except OSError as exc:
        raise DownloadFailed(f"no room to download beside the program: "
                             f"{exc.strerror or type(exc).__name__}") from exc
    kept = False
    try:
        with os.fdopen(handle, "wb") as out:
            _stream(offer, transport, out)
        kept = True
        return target
    finally:
        if not kept:
            target.unlink(missing_ok=True)


def _stream(offer: Offer, transport: Transport, out) -> None:
    try:
        response = transport.open(offer.asset_url)
    except Exception as exc:  # noqa: BLE001 -- § 4.6: any other error
        raise DownloadFailed(f"the download did not start: {type(exc).__name__}") from exc
    try:
        if response.status != 200:
            raise DownloadFailed(f"the download answered status {response.status}")
        declared = {key.lower(): value for key, value in dict(response.headers).items()}
        length = declared.get("content-length")
        if length is not None and length.strip() != str(offer.size):
            raise DownloadFailed("the download's length is not the signed list's")
        digest = hashlib.sha256()
        total = 0
        while True:
            try:
                chunk = response.read(_CHUNK)
            except Exception as exc:  # noqa: BLE001 -- a dropped stream
                raise DownloadFailed(f"the download broke off: {type(exc).__name__}") from exc
            if not chunk:
                break
            total += len(chunk)
            if total > offer.size:
                raise UpdateRejected("more bytes arrived than the signed list names")
            digest.update(chunk)
            out.write(chunk)
        if total < offer.size:
            raise DownloadEndedEarly(f"the download stopped at {total} of {offer.size} bytes")
        if digest.hexdigest() != offer.sha256:
            raise UpdateRejected("the download is not the file the signed list names")
        out.flush()
        os.fsync(out.fileno())
    except UpdateError:
        raise
    except Exception as exc:  # noqa: BLE001 -- § 4.6: any other error
        raise DownloadFailed(f"the download failed: {type(exc).__name__}") from exc
    finally:
        response.close()


# ----------------------------------------------------------------- unpack ---


_DRIVE = re.compile(r"^[A-Za-z]:")


def _allowed(name: str) -> bool:
    """`Start Pressless.bat`, or `Pressless/` or a path under it, with no
    absolute path, no `..` and no drive letter (§ 4.6). A backslash is a
    separator on the system that unpacks it."""
    if name.startswith(("/", "\\")) or _DRIVE.match(name):
        return False
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if ".." in parts or not parts:
        return False
    if name == "Start Pressless.bat":
        return True
    return name.startswith("Pressless/")


def unpack(archive: Path, beside: Path) -> Path:
    """Unpack the checked Windows zip into a new Pressless.new-<random> folder
    beside the program, checking every member before writing any. The zip is
    removed either way; a refused one leaves nothing."""
    target = Path(beside) / f"Pressless.new-{secrets.token_hex(4)}"
    try:
        with zipfile.ZipFile(archive) as opened:
            members = opened.namelist()
            if not all(_allowed(name) for name in members):
                raise UpdateRejected("the download holds a file outside Pressless's own")
            target.mkdir()
            opened.extractall(target)
    except UpdateError:
        shutil.rmtree(target, ignore_errors=True)
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise DownloadFailed(f"the download could not be unpacked: "
                             f"{type(exc).__name__}") from exc
    finally:
        Path(archive).unlink(missing_ok=True)
    return target
