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

from pressless import jpegxl, jpegxl_screen, setup, updater

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
    assert jpegxl.find_program() is None


@pytest.mark.parametrize("platform, machine, system", [
    ("linux", "x86_64", "linux"),
    ("linux", "aarch64", None),
    ("darwin", "arm64", None),
    ("darwin", "x86_64", None),
    ("win32", "AMD64", "windows"),
    ("win32", "ARM64", "windows"),
], ids=["linux-x86_64", "linux-arm", "mac-arm", "mac-intel", "windows", "windows-arm"])
def test_only_a_system_a_pin_runs_on_is_given_one(monkeypatch, platform, machine, system):
    """§ 4.1: a pin is for 64-bit Intel or AMD Linux, or for Windows, which
    runs the x64 program on ARM too. Any other computer has no system, so
    nothing is downloaded or run there."""
    monkeypatch.setattr(jpegxl.sys, "platform", platform)
    monkeypatch.setattr(jpegxl, "machine", lambda: machine)
    assert jpegxl.this_system() == system


def test_a_computer_with_no_pin_runs_nothing(tmp_path, monkeypatch):
    """§ 6: where no pin fits, find_program finds nothing and decode runs
    nothing, even a file holding this system's pinned bytes."""
    own = tmp_path / "own"
    program = standin.installed(monkeypatch, own, standin.png(tmp_path / "p.png"))
    marker = tmp_path / "ran"
    standin.tell(own / jpegxl.FOLDER_NAME, record=str(marker))
    monkeypatch.setattr(jpegxl, "this_system", lambda: None)
    assert jpegxl.find_program() is None
    work = tmp_path / "work"
    work.mkdir()
    original = tmp_path / "seaside.jxl"
    original.write_bytes(standin.CODESTREAM)
    with pytest.raises(jpegxl.NotInstalled):
        jpegxl.decode(program, original, work)
    assert not marker.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no execute bit")
def test_a_decoder_that_cannot_run_is_not_installed(tmp_path, monkeypatch):
    """§ 4.3: a decoder that lost its execute bit is not installed, so the
    line offers the download, which puts it back."""
    own = tmp_path / "own"
    program = standin.write(own / jpegxl.FOLDER_NAME)
    standin.pin(monkeypatch, program)
    assert jpegxl.installed(own, standin.PLATFORM) == program
    program.chmod(0o600)
    assert jpegxl.installed(own, standin.PLATFORM) is None


# ----------------------------------------------------------------- INV-3 ---


@pytest.mark.parametrize("folder", ["photographs", "Fotografías été"], ids=["plain", "accented"])
def test_decode_runs_one_fixed_command(tmp_path, monkeypatch, folder):
    """INV-3: the stand-in runs in the work directory and is given exactly
    its copy of the original and decoded.png there, plain names whatever
    the paths hold, and its picture is returned."""
    own = tmp_path / "own"
    picture = standin.png(tmp_path / "decoded-source.png")
    program = standin.installed(monkeypatch, own, picture)
    record = own / jpegxl.FOLDER_NAME / "argv.json"
    work = tmp_path / folder / "wörk"
    work.mkdir(parents=True)
    original = tmp_path / folder / "séaside.jxl"
    original.write_bytes(standin.CODESTREAM)
    monkeypatch.chdir(tmp_path / folder)

    out = jpegxl.decode(program, Path("séaside.jxl"), work)

    assert out == work / "decoded.png"
    assert out.read_bytes() == picture.read_bytes()
    assert json.loads(record.read_text(encoding="utf-8")) == ["original.jxl", "decoded.png"]
    assert (work / "original.jxl").read_bytes() == standin.CODESTREAM


@pytest.mark.parametrize("name, pixels", [
    ("still.jxl", 64 * 48), ("oriented.jxl", 64 * 48), ("animation.jxl", 32 * 32),
])
def test_a_picture_past_the_pixel_limit_never_reaches_the_decoder(
        tmp_path, monkeypatch, name, pixels):
    """§ 4.4 step 2: the size the file's own header claims is read before the
    decoder runs. At the limit it runs; one pixel over, it does not, and the
    file is Unreadable. The fixtures hold both header shapes: a bare
    codestream, and one inside the container."""
    own = tmp_path / "own"
    program = standin.installed(monkeypatch, own, standin.png(tmp_path / "p.png"))
    marker = tmp_path / "ran"
    standin.tell(own / jpegxl.FOLDER_NAME, record=str(marker), png=str(tmp_path / "p.png"))
    original = Path(__file__).parent / "jxl" / name
    work = tmp_path / "work"
    work.mkdir()

    monkeypatch.setattr(jpegxl, "MAX_PIXELS", pixels - 1)
    with pytest.raises(jpegxl.Unreadable):
        jpegxl.decode(program, original, work)
    assert not marker.exists(), "the decoder ran past the limit"

    monkeypatch.setattr(jpegxl, "MAX_PIXELS", pixels)
    assert jpegxl.decode(program, original, work).is_file()
    assert marker.exists()


@pytest.mark.parametrize("head", [
    b"\xff\x0a\x6e",                                   # claims about a billion rows
    standin.CONTAINER[:12] + b"\x00\x00\x00\x10ftypjxl ",   # no codestream box
    standin.CONTAINER[:12] + b"\x00\x00\x00\x1ajxlc" + b"\x00" * 18,  # a box of no codestream
], ids=["huge", "no-header", "not-a-codestream"])
def test_a_header_that_cannot_be_trusted_never_reaches_the_decoder(tmp_path, monkeypatch, head):
    """§ 4.4 step 2: a size past the limit, or no size header at all, is
    Unreadable before anything runs."""
    own = tmp_path / "own"
    program = standin.installed(monkeypatch, own, standin.png(tmp_path / "p.png"))
    marker = tmp_path / "ran"
    standin.tell(own / jpegxl.FOLDER_NAME, record=str(marker))
    original = tmp_path / "huge.jxl"
    original.write_bytes(head + b"\xff" * 16)
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(jpegxl.Unreadable):
        jpegxl.decode(program, original, work)
    assert not marker.exists()


def test_the_pixel_limit_is_pillows_own():
    """§ 4.4 step 2: the limit is the size past which Pillow refuses any
    other picture, so a JPEG XL is held to what a PNG is."""
    from PIL import Image
    assert jpegxl.MAX_PIXELS == 2 * Image.MAX_IMAGE_PIXELS


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
    """§ 4.4 step 4: a non-zero exit, or no decoded.png, raises Unreadable."""
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
    assert seen["argv"] == [str(program), "original.jxl", "decoded.png"]
    assert seen["cwd"] == work
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
        setup.register(browser.served, folder)
        jpegxl_screen.register(browser.served, own, platform="linux", transport=net)
        before = _line_html(browser.request("GET", "/setup/computer")[2])
        assert "JPEG XL photographs: not added yet." in before
        assert "Add JPEG XL support (0.0 MB)</button>" in before
        status, headers, _ = _Browser.request(browser, "POST", "/jpeg-xl")
        assert status == 303 and headers.get("Location") == "/setup/computer"
        after = _line_html(browser.request("GET", "/setup/computer")[2])
    assert said in after
    assert "<button" in after
    assert ("<button hidden>" in after) == (served == _RIGHT)


@pytest.mark.parametrize("step, error, raised", [
    ("mkdir", OSError(28, "No space left on device"), updater.DiskFull),
    ("replace", OSError(13, "Permission denied"), updater.DownloadFailed),
], ids=["no-room-for-extras", "replace-refused"])
def test_install_raises_only_its_three_failures(tmp_path, monkeypatch, step, error, raised):
    """§ 4.3: a failure in install's own steps is DiskFull or DownloadFailed,
    as the download's are, and leaves no file behind. Breaks when a raw
    OSError gets out and the line calls a full disk a lost connection."""
    monkeypatch.setitem(jpegxl.PINS, "linux", jpegxl.Pin(
        "djxl-test", len(_RIGHT), hashlib.sha256(_RIGHT).hexdigest()))

    def refuse(*args, **kwargs):
        raise error

    if step == "mkdir":
        monkeypatch.setattr(Path, "mkdir", refuse)
    else:
        monkeypatch.setattr(jpegxl_screen.os, "replace", refuse)
    own = tmp_path / "own"
    if step == "replace":
        own.mkdir()
    with pytest.raises(raised) as caught:
        jpegxl_screen.install(own, "linux",
                              _Net(f"{DOWNLOADS}/jpeg-xl-0.12.0/djxl-test", _RIGHT))
    assert type(caught.value) is raised
    assert [path.name for path in own.rglob("*") if path.is_file()] == []


def test_two_clicks_download_once(tmp_path, monkeypatch):
    """§ 4.6: a second Add while the first is downloading waits for it, then
    finds the decoder in and downloads nothing. Breaks when the route checks
    `installed` outside a lock: both download, and on Windows the second
    replace meets the first's file held open."""
    import threading
    monkeypatch.setitem(jpegxl.PINS, "linux", jpegxl.Pin(
        "djxl-test", len(_RIGHT), hashlib.sha256(_RIGHT).hexdigest()))
    release = threading.Event()
    downloads = []
    real = updater.download

    def slow(offer, beside, transport=None):
        downloads.append(offer)
        release.wait(5)
        return real(offer, beside, transport)

    monkeypatch.setattr(updater, "download", slow)
    routes = {}

    class _Face:
        def add_page(self, method, path, handler):
            routes[path] = handler

        def add_piece(self, place, draw):
            pass

    own = tmp_path / "own"
    jpegxl_screen.register(_Face(), own, platform="linux",
                           transport=_Net(f"{DOWNLOADS}/jpeg-xl-0.12.0/djxl-test", _RIGHT))
    clicks = [threading.Thread(target=routes["/jpeg-xl"], args=(None,)) for _ in range(2)]
    for click in clicks:
        click.start()
    time.sleep(0.3)
    release.set()
    for click in clicks:
        click.join(10)
    assert len(downloads) == 1
    assert jpegxl.installed(own, "linux") == own / "extras" / "djxl-test"


def test_a_computer_with_no_pin_says_so_on_the_line(tmp_path, monkeypatch):
    """§ 6: where no pin fits this computer, the line says JPEG XL cannot be
    read here, and offers no download."""
    from test_editor import _editor, _folder
    folder = _folder(tmp_path)
    monkeypatch.setattr(jpegxl, "this_system", lambda: None)
    with _editor(folder) as browser:
        setup.register(browser.served, folder)
        jpegxl_screen.register(browser.served, tmp_path / "own")
        page = browser.request("GET", "/setup/computer")[2]
        refused = browser.request("POST", "/jpeg-xl")[0]
    start = page.index('id="jpeg-xl"')
    line = page[start:page.index("</div>", start)]
    assert "JPEG XL photographs cannot be read on this computer." in line
    assert "<button" not in line
    assert refused == 404
