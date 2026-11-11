"""The key maker's privacy check (PRESS-0162, review-code L8.8).

scripts/make-signing-key.py is loaded by path. Only its check runs here: no
key is made, and the real one is never touched.
"""
from __future__ import annotations

import os

import pytest
from _scripts import load_script


def _maker():
    return load_script("make-signing-key.py")


@pytest.mark.skipif(os.name == "nt", reason="Windows keeps access in ACLs")
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
