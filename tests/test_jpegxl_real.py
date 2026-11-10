"""The pinned decoders decode real JPEG XL (PRESS-0275 INV-9).

Skipped unless PRESSLESS_DJXL names a file matching this system's pin. Run
on Linux and on the Windows box before a release that ships a pin; CI skips
it. The fixtures in tests/jxl/ were made once with libjxl v0.12.0's cjxl by
scripts/make-jxl-fixtures.py:

- still.jxl: a lossy 64x48 picture, left half red, right half blue;
- oriented.jxl: a 64x48 JPEG with EXIF orientation 6, recompressed losslessly;
- animation.jxl: two 32x32 frames, red then green.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageOps

from pressless import builder, jpegxl

_FIXTURES = Path(__file__).resolve().parent / "jxl"
_GIVEN = os.environ.get("PRESSLESS_DJXL", "")


def _usable() -> bool:
    return bool(_GIVEN) and jpegxl._matches(Path(_GIVEN), jpegxl.PINS[jpegxl.this_system()])


pytestmark = pytest.mark.skipif(not _usable(),
                                reason="PRESSLESS_DJXL names no file matching this system's pin")


@pytest.fixture
def decoder(tmp_path, monkeypatch) -> Path:
    """The real decoder, installed in a Pressless folder of the test's own."""
    own = tmp_path / "own"
    extras = own / jpegxl.FOLDER_NAME
    extras.mkdir(parents=True)
    program = extras / jpegxl.PINS[jpegxl.this_system()].name
    shutil.copyfile(_GIVEN, program)
    program.chmod(0o700)
    monkeypatch.setenv("PRESSLESS_FOLDER", str(own))
    assert jpegxl.program() == program
    return program


def _near(pixel, colour, slack=40) -> bool:
    return all(abs(a - b) <= slack for a, b in zip(pixel[:3], colour, strict=True))


def test_a_still_decodes_at_its_size(decoder):
    with builder.open_original(_FIXTURES / "still.jxl") as picture:
        assert picture.format == "JXL"
        assert picture.size == (64, 48)
        rgb = picture.convert("RGB")
        assert _near(rgb.getpixel((8, 24)), (255, 0, 0))
        assert _near(rgb.getpixel((56, 24)), (0, 0, 255))


def test_an_oriented_jpeg_comes_out_upright(decoder):
    """§ 4.5: the decoder is told nothing about orientation, and
    exif_transpose finishes the job, as for every other format."""
    with builder.open_original(_FIXTURES / "oriented.jxl") as picture:
        upright = ImageOps.exif_transpose(picture).convert("RGB")
    assert upright.size == (48, 64)
    # Orientation 6 turns the picture a quarter clockwise: the red left half
    # ends on top.
    assert _near(upright.getpixel((24, 8)), (255, 0, 0))
    assert _near(upright.getpixel((24, 56)), (0, 0, 255))


def test_an_animation_gives_its_first_frame(decoder, tmp_path):
    """Decision 6, and § 6's row on numbered files: one decoded.png."""
    work = tmp_path / "work"
    work.mkdir()
    out = jpegxl.decode(decoder, _FIXTURES / "animation.jxl", work)
    assert sorted(path.name for path in work.iterdir()) == ["decoded.png"]
    with Image.open(out) as picture:
        assert picture.size == (32, 32)
        assert _near(picture.convert("RGB").getpixel((16, 16)), (255, 0, 0))


def test_the_web_copy_is_webp(decoder, tmp_path):
    target = tmp_path / "view.webp"
    builder.webp_copy(_FIXTURES / "oriented.jxl", target)
    with Image.open(target) as web:
        assert web.format == "WEBP"
        assert web.size == (48, 64)
