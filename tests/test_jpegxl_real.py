"""The pinned decoders decode real JPEG XL (PRESS-0275 INV-9).

Skipped unless PRESSLESS_DJXL names a file matching this system's pin. Run
on Linux and on the Windows box before a release that ships a pin; CI skips
it. The fixtures in tests/jxl/ were made once with libjxl v0.12.0's cjxl by
scripts/make-jxl-fixtures.py:

- still.jxl: a lossy 64x48 picture, left half red, right half blue;
- oriented.jxl: a 64x48 JPEG with EXIF orientation 6, recompressed losslessly;
- animation.jxl: two 32x32 frames, red then green;
- profiled.jxl: a lossless 64x48 picture, left half red and opaque, right
  half blue and half see-through, carrying a profile that is not sRGB.
"""
from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageCms, ImageOps

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
    assert jpegxl.find_program() == program
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
    """Decision 6, and § 6's row on numbered files: one decoded.pam."""
    work = tmp_path / "work"
    work.mkdir()
    out = jpegxl.decode(decoder, _FIXTURES / "animation.jxl", work)
    assert sorted(path.name for path in work.iterdir()) == [
        "decoded.icc", "decoded.pam", "original.jxl"]
    with builder._from_pam(out, work / "decoded.icc") as picture:
        assert picture.size == (32, 32)
        assert _near(picture.convert("RGB").getpixel((16, 16)), (255, 0, 0))


def test_the_web_copy_is_webp(decoder, tmp_path):
    target = tmp_path / "view.webp"
    builder.webp_copy(_FIXTURES / "oriented.jxl", target)
    with Image.open(target) as web:
        assert web.format == "WEBP"
        assert web.size == (48, 64)


def test_the_web_copy_keeps_a_profile_and_see_through_parts(decoder, tmp_path):
    """PRESS-0485: the decoder's PAM holds no profile, so the one it writes
    beside reaches the web copy, and the alpha comes through with it."""
    target = tmp_path / "view.webp"
    builder.webp_copy(_FIXTURES / "profiled.jxl", target)
    with Image.open(target) as web:
        assert web.mode == "RGBA"
        assert _near(web.getpixel((8, 24)), (255, 0, 0), slack=8)
        assert web.getpixel((8, 24))[3] == 255
        assert abs(web.getpixel((56, 24))[3] - 128) <= 2
        profile = ImageCms.ImageCmsProfile(io.BytesIO(web.info["icc_profile"]))
    assert ImageCms.getProfileDescription(profile).strip() == "Pressless wide test"


def test_a_picture_with_no_profile_gets_none(decoder, tmp_path):
    """PRESS-0485: the sRGB profile the decoder writes for a picture with
    none is dropped, as the web copy means sRGB without it."""
    target = tmp_path / "view.webp"
    builder.webp_copy(_FIXTURES / "still.jxl", target)
    with Image.open(target) as web:
        assert "icc_profile" not in web.info
