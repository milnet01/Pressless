"""Publishing the JPEG XL decoder's release (PRESS-0275 INV-8).

scripts/publish-jpeg-xl.py is loaded by path: its name is not an importable
module name. `gh` is replaced by a recorder; nothing reaches GitHub.
"""
from __future__ import annotations

import io
import json
import lzma
import subprocess
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from _scripts import load_script


def _script():
    return load_script("publish-jpeg-xl.py")


class _Gh:
    def __init__(self, answer: str = "") -> None:
        self.calls: list[list[str]] = []
        self.answer = answer

    def __call__(self, argv, **options):
        self.calls.append(argv)
        return SimpleNamespace(stdout=self.answer)


def test_the_release_is_a_pre_release_never_the_latest(tmp_path):
    """INV-8: without both flags, the Updater would read jpeg-xl-0.12.0 as
    the latest release and stop offering updates."""
    script = _script()
    gh = _Gh()
    script.create([tmp_path / "djxl-0.12.0-linux-x86_64"], run=gh)
    [argv] = gh.calls
    assert argv[:3] == ["gh", "release", "create"]
    assert argv[3] == "jpeg-xl-0.12.0"
    assert "--draft" in argv
    assert "--prerelease" in argv
    assert "--latest=false" in argv
    assert argv[argv.index("-R") + 1] == "milnet01/Pressless"


def test_the_asset_list_must_be_exactly_the_files(tmp_path):
    """§ 4.8 step 4."""
    script = _script()
    listed = json.dumps({"assets": [{"name": "a"}, {"name": "b"}]})
    script.check_assets({"a", "b"}, run=_Gh(listed))
    with pytest.raises(script.Refused):
        script.check_assets({"a"}, run=_Gh(listed))


def test_a_wrong_github_digest_is_refused(tmp_path):
    """§ 4.8 step 1: nothing is downloaded where GitHub's digest differs."""
    script = _script()
    assets = [{"name": name, "digest": "sha256:" + "0" * 64}
              for name, _ in script.ARCHIVES.values()]
    gh = _Gh(json.dumps({"assets": assets}))
    with pytest.raises(script.Refused):
        script.fetch_archives(tmp_path, run=gh)
    assert len(gh.calls) == 1


def test_the_linux_program_and_licences_come_out_of_an_lzip_tar(tmp_path):
    """§ 4.8 step 2: lzip read with lzma's raw LZMA1 filter."""
    script = _script()
    tarred = io.BytesIO()
    with tarfile.open(fileobj=tarred, mode="w") as tar:
        for name, data in (("tools/djxl", b"program"), ("tools/cjxl", b"other"),
                           ("LICENSE.jpeg-xl", b"bsd")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    raw = lzma.compress(tarred.getvalue(), format=lzma.FORMAT_RAW, filters=[{
        "id": lzma.FILTER_LZMA1, "dict_size": 1 << 20, "lc": 3, "lp": 0, "pb": 2}])
    archive = tmp_path / "a.tar.lz"
    archive.write_bytes(b"LZIP\x01\x14" + raw + b"\0" * 20)   # 0x14: a 1 MiB dictionary
    out = tmp_path / "out"
    out.mkdir()
    program, licences = script.extract_linux(archive, out)
    assert program.name == "djxl-0.12.0-linux-x86_64"
    assert program.read_bytes() == b"program"
    assert [path.name for path in licences] == ["LICENSE.jpeg-xl"]


def _failing(stderr):
    def run(argv, **options):
        raise subprocess.CalledProcessError(1, argv, output="", stderr=stderr)
    return run


def test_a_failing_gh_or_7z_is_a_refusal_in_its_own_words(tmp_path):
    """review-code: gh's and 7z's errors were captured and thrown away, and the
    failure escaped as a traceback."""
    script = _script()
    with pytest.raises(script.Refused, match="HTTP 404"):
        script.gh(["release", "view"], run=_failing("HTTP 404: Not Found"))
    archive = tmp_path / "a.zip"
    with pytest.raises(script.Refused, match="Can not open"):
        script.extract_windows(archive, tmp_path, run=_failing("Can not open the file"))


def test_a_release_is_public_only_once_its_assets_check(monkeypatch, tmp_path):
    """review-code: the pre-release was public before its asset list was
    checked, so a wrong one stayed published. It is a draft until then, and
    its files are worked on beside the repository, never in /tmp, which is
    memory on the maintainer's machine."""
    script = _script()
    where = []

    def archives(into, run=None):
        where.append(into)
        return {"linux": into / "l", "windows": into / "w"}

    def never(*args, **options):
        raise AssertionError("a real program was started")

    monkeypatch.setattr(subprocess, "run", never)
    monkeypatch.setattr(script, "fetch_archives", archives)
    monkeypatch.setattr(script, "extract_linux", lambda archive, into: (into / "djxl", []))
    monkeypatch.setattr(script, "extract_windows",
                        lambda archive, into, run=None: (into / "djxl.exe", []))
    monkeypatch.setattr(script, "check_pin", lambda program, system: None)
    gh = _Gh(json.dumps({"assets": [{"name": "djxl"}]}))   # one of the two: a mismatch
    assert script.main(run=gh) == 1
    assert [argv[1:3] for argv in gh.calls] == [["release", "create"], ["release", "view"]]
    assert "--draft" in gh.calls[0]
    assert not Path(where[0]).is_relative_to(tempfile.gettempdir())

    gh.calls.clear()
    gh.answer = json.dumps({"assets": [{"name": "djxl"}, {"name": "djxl.exe"}]})
    assert script.main(run=gh) == 0
    edit = gh.calls[-1]
    assert edit[1:3] == ["release", "edit"]
    assert "--draft=false" in edit
    assert "--latest=false" in edit
