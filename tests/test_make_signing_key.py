"""The key maker's privacy check (PRESS-0162, review-code L8.8).

scripts/make-signing-key.py is loaded by path. Only its check runs here: no
key is made, and the real one is never touched.
"""
from __future__ import annotations

import os
import sys

import pytest
from _scripts import load_script

# The key maker runs on Linux only (user, 2026-11-16): owner-only is judged
# by POSIX modes, which Windows does not keep.
pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="the key maker runs on Linux only")


def _maker():
    return load_script("make-signing-key.py")


def test_a_file_others_can_read_is_not_private(tmp_path):
    """A drive with no POSIX modes answers the 0o600 open with whatever it
    always answers; the maker used to trust the request. Breaks when the
    check reads the requested mode rather than the file's."""
    maker = _maker()
    target = tmp_path / "key.pem"
    target.write_text("placeholder, not a key")
    target.chmod(0o600)
    assert maker.kept_private(target)
    target.chmod(0o644)
    assert not maker.kept_private(target)


def test_a_folder_that_is_not_there_is_refused_in_words(tmp_path, capsys):
    """PRESS-0184: a path in a folder not yet made ended in a
    FileNotFoundError traceback."""
    maker = _maker()
    target = tmp_path / "not-made" / "key.pem"
    assert maker.main([str(target)]) == 1
    assert "does not exist" in capsys.readouterr().err
    assert not target.parent.exists()


def test_windows_is_refused_before_a_key_is_made(tmp_path, capsys, monkeypatch):
    """review-code: on Windows the 0o600 asked for restricts nothing, and the
    check waved the key through. Breaks when the maker runs there."""
    maker = _maker()
    monkeypatch.setattr(sys, "platform", "win32")
    target = tmp_path / "key.pem"
    assert maker.main([str(target)]) == 2
    assert "Linux only" in capsys.readouterr().err
    assert not target.exists()


def test_a_key_not_safely_on_disk_is_removed_and_not_printed(tmp_path, capsys, monkeypatch):
    """review-code: the public key was printed before the private one was on
    the disk, and a failed write left a part-file that blocked a rerun."""
    maker = _maker()

    def broken(handle):
        raise OSError("the drive went away")

    monkeypatch.setattr(os, "fsync", broken)
    target = tmp_path / "key.pem"
    assert maker.main([str(target)]) == 1
    said = capsys.readouterr()
    assert said.out == ""
    assert "could not be written" in said.err
    assert not target.exists()


def test_the_key_and_its_folder_are_on_the_disk_before_it_is_printed(
        tmp_path, capsys, monkeypatch):
    """review-code: the key's bytes were synced but not the folder naming
    it, so a crash after the public half was pasted could lose the key."""
    import stat

    maker = _maker()
    synced: list[bool] = []
    real = os.fsync

    def noting(handle):
        synced.append(stat.S_ISDIR(os.fstat(handle).st_mode))
        real(handle)

    monkeypatch.setattr(os, "fsync", noting)
    assert maker.main([str(tmp_path / "key.pem")]) == 0
    assert synced == [False, True]
    assert capsys.readouterr().out.strip()
