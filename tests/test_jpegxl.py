# JPEG XL through a downloaded decoder (PRESS-0275).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0275-jpeg-xl-extra.md § 5. The decoder is a stand-in the
# test writes (tests/_jxl_standin.py); no test reaches the network, and the
# download address is written out here rather than built from the module.
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from pathlib import Path

import _jxl_standin as standin
import pytest

from pressless import jpegxl, jpegxl_screen, updater

DOWNLOADS = "https://github.com/milnet01/Pressless/releases/download"


# ----------------------------------------------------------------- INV-4 ---


def test_recognised_by_bytes(tmp_path):
    """INV-4: both signatures are JPEG XL whatever the name; a PNG named
    .jxl is not."""
    assert jpegxl.is_jpeg_xl(standin.CODESTREAM)
    assert jpegxl.is_jpeg_xl(standin.CONTAINER)
    png = standin.png(tmp_path / "photo.jxl").read_bytes()
    assert not jpegxl.is_jpeg_xl(png)
    assert not jpegxl.is_jpeg_xl(b"")
    assert not jpegxl.is_jpeg_xl(standin.CONTAINER[:11])


# ----------------------------------------------------------------- INV-1 ---


def test_a_changed_decoder_never_runs(tmp_path, monkeypatch):
    """INV-1: a pinned stand-in with one byte appended is reported as not
    installed, and decode refuses to run it."""
    own = tmp_path / "own"
    extras = own / jpegxl.FOLDER_NAME
    program = standin.write(extras)
    standin.pin(monkeypatch, program)
    marker = tmp_path / "ran"
    standin.tell(extras, record=str(marker), png=str(standin.png(tmp_path / "p.png")))
    assert jpegxl.installed(own, standin.PLATFORM) == program

    with open(program, "ab") as out:
        out.write(b"\n")
    assert jpegxl.installed(own, standin.PLATFORM) is None
    work = tmp_path / "work"
    work.mkdir()
    original = tmp_path / "seaside.jxl"
    original.write_bytes(standin.CODESTREAM)
    with pytest.raises(jpegxl.NotInstalled):
        jpegxl.decode(program, original, work)
    assert not marker.exists(), "the changed decoder ran"
    assert not (work / "decoded.png").exists()


def test_the_same_size_with_other_bytes_is_not_installed(tmp_path, monkeypatch):
    """INV-1's size half: equal length, different bytes."""
    own = tmp_path / "own"
    program = standin.write(own / jpegxl.FOLDER_NAME)
    standin.pin(monkeypatch, program)
    data = bytearray(program.read_bytes())
    data[-2] ^= 1
    program.write_bytes(bytes(data))
    assert jpegxl.installed(own, standin.PLATFORM) is None


def test_program_is_none_where_pressless_has_no_folder(monkeypatch):
    """A run from source with no folder named has nothing installed."""
    monkeypatch.delenv("PRESSLESS_FOLDER", raising=False)
    assert jpegxl.program() is None


# ----------------------------------------------------------------- INV-3 ---


def test_decode_runs_one_fixed_command(tmp_path, monkeypatch):
    """INV-3: the stand-in is given exactly the absolute original and the
    work directory's decoded.png, and its picture is returned."""
    own = tmp_path / "own"
    picture = standin.png(tmp_path / "decoded-source.png")
    program = standin.installed(monkeypatch, own, picture)
    record = own / jpegxl.FOLDER_NAME / "argv.json"
    work = tmp_path / "work"
    work.mkdir()
    original = tmp_path / "seaside.jxl"
    original.write_bytes(standin.CODESTREAM)
    monkeypatch.chdir(tmp_path)

    out = jpegxl.decode(program, Path("seaside.jxl"), work)

    assert out == work / "decoded.png"
    assert out.read_bytes() == picture.read_bytes()
    assert json.loads(record.read_text(encoding="utf-8")) == [
        str(original.resolve()), str(work / "decoded.png")]


def test_a_decoder_past_its_time_is_stopped(tmp_path, monkeypatch):
    """INV-3's timeout: a stand-in sleeping past a shortened limit raises
    Unreadable, writes no picture, and (on Linux) leaves no process behind."""
    own = tmp_path / "own"
    program = standin.installed(monkeypatch, own, standin.png(tmp_path / "p.png"))
    pid = tmp_path / "pid"
    standin.tell(own / jpegxl.FOLDER_NAME, sleep=5, pid=str(pid),
                 png=str(tmp_path / "p.png"))
    monkeypatch.setattr(jpegxl, "DECODE_SECONDS", 1)
    work = tmp_path / "work"
    work.mkdir()
    original = tmp_path / "seaside.jxl"
    original.write_bytes(standin.CODESTREAM)

    started = time.monotonic()
    with pytest.raises(jpegxl.Unreadable):
        jpegxl.decode(program, original, work)
    assert time.monotonic() - started < 4
    assert not (work / "decoded.png").exists()
    if sys.platform != "win32":
        # On Windows the stand-in is a batch file, so the Python it starts is
        # a grandchild the kill does not reach; the real djxl.exe is one
        # process. That half is checked on Linux only.
        assert pid.exists()
        assert not standin.alive(int(pid.read_text(encoding="ascii")))


@pytest.mark.parametrize("told", [{"fail": True}, {}], ids=["fails", "writes-nothing"])
def test_a_failing_decoder_is_unreadable(tmp_path, monkeypatch, told):
    """§ 4.4 step 3: a non-zero exit, or no decoded.png, raises Unreadable."""
    own = tmp_path / "own"
    program = standin.installed(monkeypatch, own, standin.png(tmp_path / "p.png"))
    standin.tell(own / jpegxl.FOLDER_NAME, **told)
    work = tmp_path / "work"
    work.mkdir()
    original = tmp_path / "seaside.jxl"
    original.write_bytes(standin.CODESTREAM)
    with pytest.raises(jpegxl.Unreadable):
        jpegxl.decode(program, original, work)


def test_decode_passes_no_shell_and_keeps_no_output(tmp_path, monkeypatch):
    """INV-3: the call itself carries no shell, a timeout, and DEVNULL for
    every stream."""
    seen = {}

    def run(argv, **options):
        seen.update(options, argv=argv)
        raise jpegxl.subprocess.TimeoutExpired(argv, 1)

    own = tmp_path / "own"
    program = standin.installed(monkeypatch, own, standin.png(tmp_path / "p.png"))
    monkeypatch.setattr(jpegxl.subprocess, "run", run)
    work = tmp_path / "work"
    work.mkdir()
    original = tmp_path / "a.jxl"
    original.write_bytes(standin.CODESTREAM)
    with pytest.raises(jpegxl.Unreadable):
        jpegxl.decode(program, original, work)
    assert seen["argv"] == [str(program), str(original.resolve()), str(work / "decoded.png")]
    assert not seen.get("shell")
    assert seen["timeout"] == jpegxl.DECODE_SECONDS
    for stream in ("stdin", "stdout", "stderr"):
        assert seen[stream] == jpegxl.subprocess.DEVNULL


# ----------------------------------------------------------------- INV-2 ---


class _Response:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.headers = {}
        self._body = io.BytesIO(body)

    def read(self, n: int) -> bytes:
        return self._body.read(min(n, 7))

    def close(self) -> None:
        pass


class _Net:
    def __init__(self, url: str, body: bytes) -> None:
        self.url, self.body = url, body
        self.requests: list[str] = []

    def open(self, url: str) -> _Response:
        self.requests.append(url)
        if url != self.url:
            raise OSError(f"no answer for {url}")
        return _Response(self.body)


_RIGHT = b"the decoder's bytes, as pinned"


@pytest.mark.parametrize("served, kept", [
    (_RIGHT, True),
    (_RIGHT[:-1] + b"!", False),
    (_RIGHT[:-1], False),
], ids=["right", "one-byte-changed", "one-byte-short"])
def test_install_rows(tmp_path, monkeypatch, served, kept):
    """INV-2: only the pinned bytes are kept, under the pin's name alone,
    and every row goes through updater.download."""
    name = "djxl-test"
    monkeypatch.setitem(jpegxl.PINS, "linux", jpegxl.Pin(
        name, len(_RIGHT), hashlib.sha256(_RIGHT).hexdigest()))
    calls = []
    real = updater.download

    def spy(offer, beside, transport=None):
        calls.append(offer)
        return real(offer, beside, transport)

    monkeypatch.setattr(updater, "download", spy)
    url = f"{DOWNLOADS}/jpeg-xl-0.12.0/{name}"
    own = tmp_path / "own"

    if kept:
        got = jpegxl_screen.install(own, "linux", _Net(url, served))
        assert got == own / "extras" / name
        assert got.read_bytes() == _RIGHT
        if sys.platform != "win32":
            assert got.stat().st_mode & 0o777 == 0o700
    else:
        with pytest.raises(updater.UpdateError):
            jpegxl_screen.install(own, "linux", _Net(url, served))
    assert len(calls) == 1 and calls[0].asset_url == url
    assert calls[0].size == len(_RIGHT)
    left = sorted(path.name for path in own.rglob("*"))
    assert left == (sorted(["extras", name]) if kept else ["extras"])


def test_install_leaves_other_files_in_extras_alone(tmp_path, monkeypatch):
    """§ 4.3: a file in extras/ no pin names is kept."""
    monkeypatch.setitem(jpegxl.PINS, "linux", jpegxl.Pin(
        "djxl-test", len(_RIGHT), hashlib.sha256(_RIGHT).hexdigest()))
    own = tmp_path / "own"
    (own / "extras").mkdir(parents=True)
    (own / "extras" / "other").write_bytes(b"kept")
    jpegxl_screen.install(own, "linux",
                          _Net(f"{DOWNLOADS}/jpeg-xl-0.12.0/djxl-test", _RIGHT))
    assert (own / "extras" / "other").read_bytes() == b"kept"


def test_the_pins_are_the_measured_ones():
    """§ 4.1: the release tag and the two pins, written out here so a moved
    pin is a deliberate change to two files."""
    assert jpegxl.RELEASE == "jpeg-xl-0.12.0"
    assert jpegxl.PINS["linux"] == jpegxl.Pin(
        "djxl-0.12.0-linux-x86_64", 4924448,
        "67bdc98fdca7f93d7b77f3473e818b251ba107109ee83b3b37ccbd90066f2454")
    assert jpegxl.PINS["windows"] == jpegxl.Pin(
        "djxl-0.12.0-windows-x64.exe", 4152832,
        "6970ce73de51e046b39bd5f28fc7bc5da64e9f6505c11194319f43d8849d2bf4")


# ------------------------------------------------------------ the line, § 4.6 ---


def _line_html(page: str) -> str:
    start = page.index('<form method="post" action="/jpeg-xl"')
    return page[start:page.index("</form>", start)]


@pytest.mark.parametrize("served, said", [
    (_RIGHT, "JPEG XL photographs: ready."),
    (_RIGHT[:-1] + b"!", "The download was not the expected file, so it was thrown away."),
], ids=["installs", "rejected"])
def test_the_line_adds_support_on_a_click(tmp_path, monkeypatch, served, said):
    """§ 4.6: before, the line offers the download with its size; the click
    installs it, or says why not, and the button keeps its place."""
    from test_editor import _Browser, _editor, _folder
    folder = _folder(tmp_path)
    own = tmp_path / "own"
    monkeypatch.setitem(jpegxl.PINS, "linux", jpegxl.Pin(
        "djxl-test", len(_RIGHT), hashlib.sha256(_RIGHT).hexdigest()))
    net = _Net(f"{DOWNLOADS}/jpeg-xl-0.12.0/djxl-test", served)
    with _editor(folder) as browser:
        jpegxl_screen.register(browser.served, own, platform="linux", transport=net)
        before = _line_html(browser.request("GET", "/")[2])
        assert "JPEG XL photographs: not added yet." in before
        assert "Add JPEG XL support (0.0 MB)</button>" in before
        status, headers, _ = _Browser.request(browser, "POST", "/jpeg-xl")
        assert status == 303
        after = _line_html(browser.request("GET", "/")[2])
    assert said in after
    assert "<button" in after
    assert ("<button hidden>" in after) == (served == _RIGHT)
