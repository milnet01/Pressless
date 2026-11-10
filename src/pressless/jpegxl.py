"""JPEG XL photographs through libjxl's own decoder -- PRESS-0275.

The decoder is `djxl`, downloaded once on the writer's click into
`extras/` in Pressless's own folder (`jpegxl_screen.install`). It is run as
its own process, and only while its bytes hash to the pin compiled in here:
Pressless is signed, so a hash inside it is as trusted as Pressless itself.

The Builder imports this module, so it reaches only `paths` and the standard
library, and never the network (PRESS-0008 INV-11).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pressless import paths


@dataclass(frozen=True)
class Pin:
    name: str        # the asset's file name, also the installed name
    size: int
    sha256: str      # 64 lowercase hex


RELEASE = "jpeg-xl-0.12.0"           # the tag on milnet01/Pressless
_DOWNLOADS = "https://github.com/milnet01/Pressless/releases/download"
# The bytes of `tools/djxl` in libjxl v0.12.0's jxl-linux-x86_64-static.tar.lz,
# and of `x64-windows-static/bin/djxl.exe` in its jxl-x64-windows-static.zip.
PINS = {
    "linux": Pin("djxl-0.12.0-linux-x86_64", 4924448,
                 "67bdc98fdca7f93d7b77f3473e818b251ba107109ee83b3b37ccbd90066f2454"),
    "windows": Pin("djxl-0.12.0-windows-x64.exe", 4152832,
                   "6970ce73de51e046b39bd5f28fc7bc5da64e9f6505c11194319f43d8849d2bf4"),
}
FOLDER_NAME = "extras"               # in Pressless's own folder
DECODE_SECONDS = 120

_CODESTREAM = b"\xff\x0a"
_CONTAINER = b"\x00\x00\x00\x0cJXL \r\n\x87\x0a"
DECODED = "decoded.png"


class NotInstalled(Exception):
    """No decoder, or one whose bytes are not the pin's."""


class Unreadable(OSError):
    """The decoder gave no picture. An OSError, so it is caught where
    Pillow's own errors are."""


def download_url(platform: str) -> str:
    """Where `jpegxl_screen.install` fetches the decoder for `platform`."""
    return f"{_DOWNLOADS}/{RELEASE}/{PINS[platform].name}"


def this_system() -> str:
    return "windows" if sys.platform == "win32" else "linux"


def is_jpeg_xl(head: bytes) -> bool:
    """§ 4.2: the bytes decide, never the name."""
    return head.startswith(_CODESTREAM) or head.startswith(_CONTAINER)


def _matches(program: Path, pin: Pin) -> bool:
    """The whole file hashed, every time (§ 4.3)."""
    try:
        if program.stat().st_size != pin.size:
            return False
        digest = hashlib.sha256()
        with open(program, "rb") as source:
            while chunk := source.read(1 << 20):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest() == pin.sha256


def installed(folder: Path, platform: str) -> Path | None:
    """The decoder in `folder`'s extras/, where its size and hash are the pin's."""
    pin = PINS[platform]
    program = Path(folder) / FOLDER_NAME / pin.name
    return program if program.is_file() and _matches(program, pin) else None


def program() -> Path | None:
    """This system's decoder in Pressless's own folder; None where there is
    none, or no folder can be told."""
    try:
        own = paths.own_folder()
    except paths.NotPackaged:
        return None
    return installed(own, this_system())


def decode(program: Path, original: Path, work: Path) -> Path:
    """§ 4.4: `original` decoded to `work`/decoded.png by `program`, hashed
    again first. `work` is a fresh directory the caller removes."""
    if not _matches(program, PINS[this_system()]):
        raise NotInstalled("the JPEG XL decoder is not the file Pressless expects")
    out = Path(work) / DECODED
    try:
        finished = subprocess.run(  # noqa: S603 -- the pinned program, two absolute paths
            [str(program), str(Path(original).resolve()), str(out)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=DECODE_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise Unreadable("the JPEG XL decoder ran past its time") from None
    except OSError as exc:
        raise Unreadable(f"the JPEG XL decoder did not start: {type(exc).__name__}") from None
    if finished.returncode != 0 or not out.is_file():
        raise Unreadable("the JPEG XL decoder gave no picture")
    return out
