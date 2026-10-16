# Keeping an uploaded file that is not a photograph (PRESS-0197).
#
# Why this exists: docs/specs/PRESS-0197-upload-any-file.md is the contract,
# and INV-1 to INV-3 are tested here. Every fixture is a few made-up bytes
# behind a kind's signature, never real media (§ 7). Names are written out
# rather than imported from the modules under test, which would compare a
# module against itself.
from __future__ import annotations

from pathlib import Path

import pytest

from pressless import builder, files

# One file of each § 4.1 kind: its name and bytes that begin as the kind does.
_KEPT = {
    "a.mp3": b"ID3 made up",
    "b.mp3": b"\xff\xfb made up",
    "a.ogg": b"OggS made up",
    "a.wav": b"RIFF\x00\x00\x00\x00WAVE made up",
    "a.m4a": b"\x00\x00\x00\x18ftypM4A made up",
    "a.mp4": b"\x00\x00\x00\x18ftypisom made up",
    "a.webm": b"\x1a\x45\xdf\xa3 made up",
    "a.pdf": b"%PDF- made up",
    "a.zip": b"PK\x03\x04 made up",
    "b.zip": b"PK\x05\x06 made up",
    "a.txt": "A made-up line, caf\u00e9.\n".encode(),
}
# Each refused, though most begin as some kind does.
_REFUSED = {
    "a web page named as a PDF": ("a.pdf", b"<html>made up</html>"),
    "a web page": ("a.html", b"<html>made up</html>"),
    "an SVG": ("a.svg", b"<svg>made up</svg>"),
    "a Word file, which is a ZIP": ("a.docx", b"PK\x03\x04 made up"),
    "text holding a NUL": ("a.txt", b"made\x00up"),
    "text that is not UTF-8": ("a.txt", b"made \xff up"),
    "a PDF named as music": ("a.mp3", b"%PDF- made up"),
    "MP3 frame bits not all set": ("a.mp3", b"\xff\x1b made up"),
    "no suffix at all": ("pdf", b"%PDF- made up"),
    # One per remaining kind, so each signature's own check is needed.
    "a RIFF that is not WAVE": ("a.wav", b"RIFF\x00\x00\x00\x00AVI made up"),
    "ftyp in the wrong place": ("a.mp4", b"ftyp made up"),
    "music named as M4A": ("a.m4a", b"ID3 made up"),
    "music named as Ogg": ("a.ogg", b"ID3 made up"),
    "Ogg named as WebM": ("a.webm", b"OggS made up"),
    "PK not followed by a header": ("a.zip", b"PK made up"),
    "a PDF missing its dash": ("a.pdf", b"%PDF made up"),
}


def _kept(folder: Path) -> dict[str, bytes]:
    where = folder / "files"
    if not where.is_dir():
        return {}
    return {path.name: path.read_bytes() for path in where.iterdir()}


def test_only_the_listed_kinds_are_kept(tmp_path):
    """INV-1. Breaks when a suffix outside § 4.1 is kept, or bytes not of
    their suffix's kind are."""
    for description, (name, data) in _REFUSED.items():
        with pytest.raises(files.NotAllowed):
            files.add(tmp_path, name, data)
            pytest.fail(f"{description} was kept")
    assert _kept(tmp_path) == {}, "a refused file was written"

    for name, data in _KEPT.items():
        assert files.add(tmp_path, name.upper(), data) == name
    assert _kept(tmp_path) == _KEPT


def test_a_file_over_the_limit_is_refused(tmp_path, monkeypatch):
    """INV-2. Breaks when the check is off by one, or runs after the write.

    The limit is lowered for the test so it holds no 50 MiB body in memory
    twice; the real value is pinned first, and `add` reads the limit at call
    time, as § 4.2 says."""
    assert builder.FILE_LARGEST == 50 * 1024 * 1024
    monkeypatch.setattr(builder, "FILE_LARGEST", 64)
    body = b"%PDF-" + b"0" * 59
    with pytest.raises(files.TooLarge):
        files.add(tmp_path, "big.pdf", body + b"0")
    assert _kept(tmp_path) == {}
    assert files.add(tmp_path, "big.pdf", body) == "big.pdf"
    assert _kept(tmp_path) == {"big.pdf": body}


def test_names_follow_the_photograph_rule(tmp_path):
    """INV-3. Breaks when the two modules name differently."""
    song, other = b"ID3 a made-up song", b"ID3 another made-up song"
    assert files.add(tmp_path, "My Song.MP3", song) == "my-song.mp3"
    assert files.add(tmp_path, "my song.mp3", other) == "my-song-2.mp3"
    assert files.add(tmp_path, "MY SONG.mp3", song) == "my-song.mp3"
    assert files.add(tmp_path, "C:\\Music\\.mp3", song) == "file.mp3"
    assert files.add(tmp_path, "con.pdf", b"%PDF- made up") == "con-2.pdf"
    long = files.add(tmp_path, "x" * 80 + ".txt", b"made up")
    assert long == "x" * 60 + ".txt"
    assert sorted(_kept(tmp_path)) == sorted(
        ["my-song.mp3", "my-song-2.mp3", "file.mp3", "con-2.pdf", long])
