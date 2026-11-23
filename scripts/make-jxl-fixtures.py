#!/usr/bin/env python3
"""Make the JPEG XL fixtures tests/test_jpegxl_real.py decodes -- PRESS-0275 INV-9.

    python3 scripts/make-jxl-fixtures.py <path to libjxl v0.12.0's cjxl>

Run once by hand; the files it writes into tests/jxl/ are committed.
The sources are drawn here with Pillow, so what each fixture holds is in
this file.
"""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

_OUT = Path(__file__).resolve().parent.parent / "tests" / "jxl"
_ORIENTATION = 0x0112


def _halves(size: tuple[int, int]) -> Image.Image:
    """Left half red, right half blue."""
    picture = Image.new("RGB", size, (0, 0, 255))
    picture.paste((255, 0, 0), (0, 0, size[0] // 2, size[1]))
    return picture


# PRESS-0485: a colour profile that is not sRGB, so the decoder keeps it.
PROFILE_NAME = "Pressless wide test"


def _profile() -> bytes:
    """An ICC v2 display profile: Adobe RGB (1998)'s primaries, gamma 2.2."""
    def fixed(*values: float) -> bytes:
        return b"".join(struct.pack(">i", round(value * 65536)) for value in values)

    name = PROFILE_NAME.encode("ascii") + b"\0"
    desc = b"desc\0\0\0\0" + struct.pack(">I", len(name)) + name + bytes(4 + 4 + 2 + 1 + 67)
    tags = [(b"desc", desc), (b"cprt", b"text\0\0\0\0No copyright\0"),
            (b"wtpt", b"XYZ \0\0\0\0" + fixed(0.9642, 1.0, 0.8249)),
            (b"rXYZ", b"XYZ \0\0\0\0" + fixed(0.6097, 0.3111, 0.0195)),
            (b"gXYZ", b"XYZ \0\0\0\0" + fixed(0.2053, 0.6257, 0.0609)),
            (b"bXYZ", b"XYZ \0\0\0\0" + fixed(0.1492, 0.0632, 0.7446))]
    curve = b"curv\0\0\0\0" + struct.pack(">IH", 1, 0x0233)    # gamma 2.2
    tags += [(b"rTRC", curve), (b"gTRC", curve), (b"bTRC", curve)]
    table, body, at = b"", b"", 128 + 4 + 12 * len(tags)
    for signature, data in tags:
        data += bytes(-len(data) % 4)
        table += signature + struct.pack(">II", at + len(body), len(data))
        body += data
    size = at + len(body)
    header = (struct.pack(">I", size) + bytes(4) + struct.pack(">I", 0x02100000)
              + b"mntrRGB XYZ " + bytes(12) + b"acsp" + bytes(4 + 4 + 4 + 4 + 8)
              + struct.pack(">I", 0) + fixed(0.9642, 1.0, 0.8249) + bytes(4 + 16 + 28))
    return header + struct.pack(">I", len(tags)) + table + body


def main(cjxl: str) -> int:
    _OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        _halves((64, 48)).save(work / "still.png")
        exif = Image.Exif()
        exif[_ORIENTATION] = 6
        _halves((64, 48)).save(work / "oriented.jpg", quality=95, exif=exif)
        frames = [Image.new("RGB", (32, 32), colour) for colour in ((255, 0, 0), (0, 255, 0))]
        frames[0].save(work / "animation.png", save_all=True, append_images=frames[1:],
                       duration=200, loop=0)
        # Left half red and opaque, right half blue and half see-through.
        profiled = _halves((64, 48)).convert("RGBA")
        profiled.putalpha(Image.new("L", (64, 48), 255))
        profiled.paste((0, 0, 255, 128), (32, 0, 64, 48))
        profiled.save(work / "profiled.png", icc_profile=_profile())
        for source, target, options in (
            ("still.png", "still.jxl", ["-d", "1.0"]),
            ("oriented.jpg", "oriented.jxl", ["--lossless_jpeg=1"]),
            ("animation.png", "animation.jxl", ["-d", "1.0"]),
            ("profiled.png", "profiled.jxl", ["-d", "0"]),
        ):
            subprocess.run([cjxl, str(work / source), str(_OUT / target), *options],  # noqa: S603
                           check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
