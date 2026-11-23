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
from collections.abc import Callable
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
# The decoder's memory: this much, and this much again for each pixel the
# header claims (§ 4.4 step 3). libjxl v0.12.0's djxl needed about 53 bytes a
# pixel for a 16-bit lossless picture with alpha, the costliest kind measured
# (2026-11-23). An animation keeps every frame and extra channels add to each,
# so this, not MAX_PIXELS, is what bounds them.
MEMORY_BASE = 512 * 1024 * 1024
MEMORY_PER_PIXEL = 80

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


_HEAD = 18                              # bytes of codestream the SizeHeader fits in


def _codestream_head(source) -> bytes | None:
    """The first bytes of the codestream in an open JPEG XL file: the file's
    start, or inside the container's `jxlc` box, or its `jxlp` boxes joined
    in order, as the decoder joins them. None where no codestream box is
    found."""
    head = source.read(len(_CONTAINER))
    if head.startswith(_CODESTREAM):
        return head + source.read(_HEAD - len(head))
    found = b""
    while len(found) < _HEAD and (header := source.read(8)):
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
            taken += 4
        left = size - taken             # what the box holds past its header
        if size == 0:                   # the box runs to the end of the file
            left = None
        elif left < 0:
            return None
        if kind in (b"jxlc", b"jxlp"):
            want = _HEAD - len(found)
            found += source.read(want if left is None else min(want, left))
            if kind == b"jxlc" or left is None:
                break
            source.seek(max(left - want, 0), 1)
        elif left is None:
            return None
        else:
            source.seek(left, 1)
    return found or None


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


def _refuse_past_the_limit(original: Path) -> int:
    """§ 4.4 step 2: the pixels the file's own header claims, else
    Unreadable where it is missing or claims more than MAX_PIXELS. Read
    before the decoder runs, since the decoder holds the whole picture in
    memory and writes it out in full."""
    with open(original, "rb") as source:
        head = _codestream_head(source)
    if head is None or not head.startswith(_CODESTREAM):
        raise Unreadable("the JPEG XL file holds no size header")
    width, height = _size(head)
    if width * height > MAX_PIXELS:
        raise Unreadable("the JPEG XL picture is past the pixel limit")
    return width * height


def _limit_memory(process: subprocess.Popen, limit: int) -> Callable[[], None]:
    """§ 4.4 step 3: hold the running `process` to `limit` bytes of memory,
    and on Linux to no core file. Returns what lets it go, called once the
    process has ended. OSError where the limit cannot be set."""
    if sys.platform == "win32":
        return _limit_windows(process, limit)
    import resource
    try:
        resource.prlimit(process.pid, resource.RLIMIT_DATA, (limit, limit))
        resource.prlimit(process.pid, resource.RLIMIT_CORE, (0, 0))
    except ProcessLookupError:
        pass                            # it has already ended
    return lambda: None


def _limit_windows(process: subprocess.Popen, limit: int) -> Callable[[], None]:
    """A job object holding `process` to `limit` bytes of committed memory.
    Closing it ends whatever still runs in it."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "reads", "writes", "others", "read_bytes", "written_bytes", "other_bytes")]

    class Basic(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("least_working_set", ctypes.c_size_t),
                    ("most_working_set", ctypes.c_size_t), ("processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", Counters), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t),
                    ("peak_job_memory", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                 ctypes.c_void_p, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = Extended()
    # JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    info.basic.flags = 0x100 | 0x2000
    info.process_memory = limit
    # PROCESS_SET_QUOTA | PROCESS_TERMINATE, which AssignProcessToJobObject needs.
    handle = kernel32.OpenProcess(0x0100 | 0x0001, False, process.pid)
    extended = 9                        # JobObjectExtendedLimitInformation
    held = (handle and kernel32.SetInformationJobObject(
                job, extended, ctypes.byref(info), ctypes.sizeof(info))
            and kernel32.AssignProcessToJobObject(job, handle))
    error = ctypes.get_last_error()
    if handle:
        kernel32.CloseHandle(handle)
    if not held:
        kernel32.CloseHandle(job)
        raise ctypes.WinError(error)
    return lambda: kernel32.CloseHandle(job)


def decode(program: Path, original: Path, work: Path) -> Path:
    """§ 4.4: `original` decoded to `work`/decoded.png by `program`, hashed
    again first. `work` is a fresh directory the caller removes."""
    system = this_system()
    if system is None or not _matches(program, PINS[system]):
        raise NotInstalled("the JPEG XL decoder is not the file Pressless expects")
    pixels = _refuse_past_the_limit(original)
    shutil.copyfile(original, Path(work) / SOURCE)
    out = Path(work) / DECODED
    try:
        process = subprocess.Popen(  # noqa: S603 -- the pinned program, two fixed names
            [str(program), SOURCE, DECODED], cwd=work,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        raise Unreadable(f"the JPEG XL decoder did not start: {type(exc).__name__}") from None
    try:
        release = _limit_memory(process, MEMORY_BASE + MEMORY_PER_PIXEL * pixels)
    except OSError:
        process.kill()
        process.wait()
        raise Unreadable("the JPEG XL decoder's memory could not be limited") from None
    try:
        code = process.wait(timeout=DECODE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise Unreadable("the JPEG XL decoder ran past its time") from None
    finally:
        release()
    if code != 0 or not out.is_file():
        raise Unreadable("the JPEG XL decoder gave no picture")
    return out
