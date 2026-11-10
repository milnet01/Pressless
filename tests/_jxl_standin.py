# A stand-in for libjxl's djxl, for PRESS-0275's tests (spec § 7).
#
# It is a small program the test writes: on Linux a script whose first line
# names this Python, on Windows a batch file calling this Python on the
# script. It reads what to do from `standin.json` beside the script, records
# the arguments it was given, and copies a PNG to its second argument. Its
# size and hash replace this system's pin through monkeypatch, so the real
# decoder is never needed.
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image

from pressless import jpegxl

# The two signatures of spec § 4.2, followed by bytes no decoder reads.
CODESTREAM = b"\xff\x0a" + b"not really a picture"
CONTAINER = b"\x00\x00\x00\x0cJXL \r\n\x87\x0a" + b"not really a picture"

_SCRIPT = """\
import json, os, shutil, sys, time
from pathlib import Path

here = Path(__file__).resolve().parent
told = json.loads((here / "standin.json").read_text(encoding="utf-8"))
Path(told["record"]).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
if told.get("sleep"):
    Path(told["pid"]).write_text(str(os.getpid()), encoding="ascii")
    time.sleep(told["sleep"])
if told.get("fail"):
    sys.exit(1)
if told.get("png"):
    shutil.copyfile(told["png"], sys.argv[2])
"""

PLATFORM = "windows" if sys.platform == "win32" else "linux"


def png(path: Path, size=(40, 30), colour=(30, 90, 200)) -> Path:
    """A PNG for the stand-in to hand back as the decoded picture."""
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, "PNG")
    path.write_bytes(out.getvalue())
    return path


def write(folder: Path, name: str | None = None) -> Path:
    """The stand-in program in `folder`, under `name` (default: this system's
    pinned name), runnable as it is, without a shell."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "standin_script.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    name = name or jpegxl.PINS[PLATFORM].name
    if PLATFORM == "windows":
        program = folder / (name if name.lower().endswith(".bat") else name + ".bat")
        program.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="ascii")
    else:
        program = folder / name
        program.write_text(f"#!{sys.executable}\n" + _SCRIPT, encoding="utf-8")
        program.chmod(0o700)
    return program


def tell(folder: Path, **what) -> Path:
    """Write what the stand-in in `folder` does next; returns the file its
    arguments are recorded in."""
    record = folder / "argv.json"
    what.setdefault("record", str(record))
    (folder / "standin.json").write_text(json.dumps(what), encoding="utf-8")
    return Path(what["record"])


def pin(monkeypatch, program: Path) -> None:
    """Make `program`'s bytes this system's pin."""
    data = program.read_bytes()
    monkeypatch.setitem(jpegxl.PINS, PLATFORM, jpegxl.Pin(
        program.name, len(data), hashlib.sha256(data).hexdigest()))


def installed(monkeypatch, own: Path, picture: Path) -> Path:
    """A pinned stand-in installed in `own`, Pressless's own folder for this
    test, that hands back `picture`."""
    extras = own / jpegxl.FOLDER_NAME
    program = write(extras)
    pin(monkeypatch, program)
    tell(extras, png=str(picture))
    monkeypatch.setenv("PRESSLESS_FOLDER", str(own))
    return program


def alive(pid: int) -> bool:
    """Whether the process `pid` still runs (Linux only)."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
