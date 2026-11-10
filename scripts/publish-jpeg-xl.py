#!/usr/bin/env python3
"""Publish libjxl's decoder for Pressless's JPEG XL support -- PRESS-0275 § 4.8.

    python3 scripts/publish-jpeg-xl.py

Run by hand, on the maintainer's machine, as sign-release.py is, and before
any Pressless pinning `jpegxl.RELEASE` is published.

1. Downloads libjxl's two archives for the version in `jpegxl.RELEASE`, and
   requires each one's GitHub digest, and its own bytes, to match the
   SHA-256 written below.
2. Takes `tools/djxl` out of the Linux archive with lzma and tarfile, and
   `x64-windows-static/bin/djxl.exe` out of the Windows one with 7z. Each
   must match `jpegxl.PINS`.
3. Creates the release `jpegxl.RELEASE` on milnet01/Pressless as a
   pre-release that is never the latest, so the Updater never offers it.
   It carries the two programs under the pins' names and each archive's
   licence files, the Windows ones prefixed `windows-`.
4. Reads the asset list back and requires exactly those names.

Needs `gh`, signed in, and `7z`.
"""
from __future__ import annotations

import hashlib
import io
import json
import lzma
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pressless import jpegxl  # noqa: E402 -- after the path it is found on

LIBJXL = "libjxl/libjxl"
REPOSITORY = "milnet01/Pressless"
# The archives of libjxl v0.12.0, as GitHub records them (measured 2026-11-10).
ARCHIVES = {
    "linux": ("jxl-linux-x86_64-static.tar.lz",
              "5318a1ea40adad76d023e0c17a03d4627f8282f83cb2b575e69be8e74f1ff456"),
    "windows": ("jxl-x64-windows-static.zip",
                "3025d7e308390796d20492322e606bc92decaee7b6bc99d3f7547870ae5db7de"),
}
_WINDOWS_PROGRAM = "x64-windows-static/bin/djxl.exe"
_WINDOWS_LICENCES = "x64-windows-static/licenses/LICENSE.*"
NOTES = ("libjxl's djxl decoder (BSD-3-Clause), for Pressless's JPEG XL support. "
         "Pressless downloads the program for its system and checks its SHA-256 "
         "before every use. The licence files are libjxl's and its libraries'.")


class Refused(Exception):
    """A check failed; nothing was published."""


def libjxl_tag() -> str:
    return "v" + jpegxl.RELEASE.removeprefix("jpeg-xl-")


def gh(args: list[str], run=subprocess.run) -> str:
    return run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_archives(into: Path, run=subprocess.run) -> dict[str, Path]:
    """Step 1: each archive, its GitHub digest and its bytes both checked."""
    release = json.loads(gh(["api", f"repos/{LIBJXL}/releases/tags/{libjxl_tag()}"], run))
    digests = {asset["name"]: asset.get("digest") for asset in release["assets"]}
    found = {}
    for system, (name, sha256) in ARCHIVES.items():
        if digests.get(name) != f"sha256:{sha256}":
            raise Refused(f"GitHub's digest for {name} is not the one written here")
        gh(["release", "download", libjxl_tag(), "-R", LIBJXL, "-p", name,
            "-D", str(into), "--clobber"], run)
        if _sha256(into / name) != sha256:
            raise Refused(f"the downloaded {name} is not the one written here")
        found[system] = into / name
    return found


def unlzip(data: bytes) -> bytes:
    """An lzip file's one member: a 6-byte header, raw LZMA1, a 20-byte trailer."""
    if data[:5] != b"LZIP\x01":
        raise Refused("the Linux archive is not an lzip file")
    code = data[5]
    size = 1 << (code & 0x1F)
    size -= (size // 16) * (code >> 5)
    decoder = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{
        "id": lzma.FILTER_LZMA1, "dict_size": size, "lc": 3, "lp": 0, "pb": 2}])
    return decoder.decompress(data[6:])


def extract_linux(archive: Path, into: Path) -> tuple[Path, list[Path]]:
    """Step 2, Linux: the program, and the archive's top-level LICENSE.* files."""
    program, licences = None, []
    with tarfile.open(fileobj=io.BytesIO(unlzip(archive.read_bytes()))) as tar:
        for member in tar.getmembers():
            name = member.name.removeprefix("./")
            if not member.isfile():
                continue
            if name == "tools/djxl":
                target = program = into / jpegxl.PINS["linux"].name
            elif "/" not in name and name.startswith("LICENSE."):
                target = into / name
                licences.append(target)
            else:
                continue
            target.write_bytes(tar.extractfile(member).read())
    if program is None:
        raise Refused("the Linux archive holds no tools/djxl")
    return program, sorted(licences)


def extract_windows(archive: Path, into: Path, run=subprocess.run) -> tuple[Path, list[Path]]:
    """Step 2, Windows: 7z, since the zip uses Deflate64 (spec Problem 4)."""
    out = into / "windows"
    out.mkdir()
    run(["7z", "e", "-y", f"-o{out}", str(archive), _WINDOWS_PROGRAM, _WINDOWS_LICENCES],
        check=True, capture_output=True)
    program = into / jpegxl.PINS["windows"].name
    (out / "djxl.exe").replace(program)
    licences = []
    for licence in sorted(out.glob("LICENSE.*")):
        licences.append(licence.replace(into / f"windows-{licence.name}"))
    return program, licences


def check_pin(program: Path, system: str) -> None:
    pin = jpegxl.PINS[system]
    if program.stat().st_size != pin.size or _sha256(program) != pin.sha256:
        raise Refused(f"the {system} program is not the one jpegxl.PINS names")


def create(files: list[Path], run=subprocess.run) -> None:
    """Step 3: a pre-release, never the latest (INV-8)."""
    gh(["release", "create", jpegxl.RELEASE, "-R", REPOSITORY,
        "--prerelease", "--latest=false",
        "--title", f"JPEG XL decoder ({libjxl_tag()})", "--notes", NOTES,
        *(str(path) for path in files)], run)


def check_assets(names: set[str], run=subprocess.run) -> None:
    """Step 4: the release holds exactly `names`."""
    found = json.loads(gh(["release", "view", jpegxl.RELEASE, "-R", REPOSITORY,
                           "--json", "assets"], run))
    held = {asset["name"] for asset in found["assets"]}
    if held != names:
        raise Refused(f"the release holds {sorted(held)}, not {sorted(names)}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="publish-jpeg-xl-") as work:
        where = Path(work)
        try:
            archives = fetch_archives(where)
            linux, linux_licences = extract_linux(archives["linux"], where)
            windows, windows_licences = extract_windows(archives["windows"], where)
            check_pin(linux, "linux")
            check_pin(windows, "windows")
            files = [linux, windows, *linux_licences, *windows_licences]
            create(files)
            check_assets({path.name for path in files})
        except Refused as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1
    print(f"Published {jpegxl.RELEASE} on {REPOSITORY} as a pre-release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
