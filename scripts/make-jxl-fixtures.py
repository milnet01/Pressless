#!/usr/bin/env python3
"""Make the JPEG XL fixtures tests/test_jpegxl_real.py decodes -- PRESS-0275 INV-9.

    python3 scripts/make-jxl-fixtures.py <path to libjxl v0.12.0's cjxl>

Run once by hand; the three files it writes into tests/jxl/ are committed.
The sources are drawn here with Pillow, so what each fixture holds is in
this file.
"""
from __future__ import annotations

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
        for source, target, options in (
            ("still.png", "still.jxl", ["-d", "1.0"]),
            ("oriented.jpg", "oriented.jxl", ["--lossless_jpeg=1"]),
            ("animation.png", "animation.jxl", ["-d", "1.0"]),
        ):
            subprocess.run([cjxl, str(work / source), str(_OUT / target), *options],  # noqa: S603
                           check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
