"""Publishing the JPEG XL decoder's release (PRESS-0275 INV-8).

scripts/publish-jpeg-xl.py is loaded by path: its name is not an importable
module name. `gh` is replaced by a recorder; nothing reaches GitHub.
"""
from __future__ import annotations

import importlib.util
import io
import json
import lzma
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "publish-jpeg-xl.py"


def _script():
    spec = importlib.util.spec_from_file_location("publish_jpeg_xl", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
