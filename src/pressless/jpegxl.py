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
import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from platform import machine

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
# Past this many pixels Pillow refuses any picture: twice its
# MAX_IMAGE_PIXELS, which this module cannot import (a test holds the pair).
MAX_PIXELS = 2 * 89_478_485

_CODESTREAM = b"\xff\x0a"
_CONTAINER = b"\x00\x00\x00\x0cJXL \r\n\x87\x0a"
# The names the decoder is given, inside the work directory it runs in.
# Plain ASCII, so no code page can mangle them on Windows.
SOURCE = "original.jxl"
DECODED = "decoded.png"
# The SizeHeader's fixed aspect ratios, width over height (ISO/IEC 18181-1).
_RATIOS = {1: (1, 1), 2: (12, 10), 3: (4, 3), 4: (3, 2), 5: (16, 9), 6: (5, 4), 7: (2, 1)}


class NotInstalled(Exception):
    """No decoder, or one whose bytes are not the pin's."""


class Unreadable(OSError):
    """The decoder gave no picture. An OSError, so it is caught where
    Pillow's own errors are."""


def download_url(platform: str) -> str:
    """Where `jpegxl_screen.install` fetches the decoder for `platform`."""
    return f"{_DOWNLOADS}/{RELEASE}/{PINS[platform].name}"


def this_system() -> str | None:
    """The PINS key whose decoder runs here, else None. The Linux pin is for
    64-bit Intel or AMD machines; Windows on ARM runs the x64 program, as it
    runs Pressless itself."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux") and machine().lower() in ("x86_64", "amd64"):
        return "linux"
    return None


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
    """The decoder in `folder`'s extras/, where its size and hash are the
    pin's, and on Linux where it may be run: one that lost its execute bit is
    downloaded again."""
    pin = PINS[platform]
    program = Path(folder) / FOLDER_NAME / pin.name
    if not (program.is_file() and _matches(program, pin)):
        return None
    if platform == "linux" and not os.access(program, os.X_OK):
        return None
    return program


def find_program() -> Path | None:
    """This system's decoder in Pressless's own folder; None where there is
    none, no pin runs here, or no folder can be told."""
    system = this_system()
    if system is None:
        return None
    try:
        own = paths.own_folder()
    except paths.NotPackaged:
        return None
    return installed(own, system)


def _codestream_head(source) -> bytes | None:
    """The first bytes of the codestream in an open JPEG XL file: the file's
    start, or inside the container's `jxlc` box or first `jxlp` box. None
    where no codestream box is found."""
    head = source.read(len(_CONTAINER))
    if head.startswith(_CODESTREAM):
        return head + source.read(16)
    while header := source.read(8):
        if len(header) < 8:
            return None
        size, kind = struct.unpack(">I4s", header)
        taken = 8
        if size == 1:
            wide = source.read(8)
            if len(wide) < 8:
                return None
            size, taken = struct.unpack(">Q", wide)[0], 16
        if kind == b"jxlp":
            source.read(4)              # the part's index
        if kind in (b"jxlc", b"jxlp"):
            return source.read(18)
        if size < taken:                # 0: the box runs to the end, and holds no codestream
            return None
        source.seek(size - taken, 1)
    return None


def _size(head: bytes) -> tuple[int, int]:
    """Width and height from a codestream's SizeHeader (ISO/IEC 18181-1), its
    bits read lowest first from the byte after FF 0A."""
    bits = int.from_bytes(head[2:11], "little")
    taken = 0

    def take(count: int) -> int:
        nonlocal taken
        value = (bits >> taken) & ((1 << count) - 1)
        taken += count
        return value

    def length(small: bool) -> int:
        if small:
            return (take(5) + 1) * 8
        return take((9, 13, 18, 30)[take(2)]) + 1

    small = bool(take(1))
    height = length(small)
    ratio = take(3)
    if ratio == 0:
        return length(small), height
    wide, high = _RATIOS[ratio]
    return height * wide // high, height


def _refuse_past_the_limit(original: Path) -> None:
    """§ 4.4 step 2: Unreadable where the file's own header is missing or
    claims more than MAX_PIXELS. Read before the decoder runs, since the
    decoder holds the whole picture in memory and writes it out in full."""
    with open(original, "rb") as source:
        head = _codestream_head(source)
    if head is None or not head.startswith(_CODESTREAM):
        raise Unreadable("the JPEG XL file holds no size header")
    width, height = _size(head)
    if width * height > MAX_PIXELS:
        raise Unreadable("the JPEG XL picture is past the pixel limit")


def decode(program: Path, original: Path, work: Path) -> Path:
    """§ 4.4: `original` decoded to `work`/decoded.png by `program`, hashed
    again first. `work` is a fresh directory the caller removes."""
    system = this_system()
    if system is None or not _matches(program, PINS[system]):
        raise NotInstalled("the JPEG XL decoder is not the file Pressless expects")
    _refuse_past_the_limit(original)
    shutil.copyfile(original, Path(work) / SOURCE)
    out = Path(work) / DECODED
    try:
        finished = subprocess.run(  # noqa: S603 -- the pinned program, two fixed names
            [str(program), SOURCE, DECODED], cwd=work,
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
