"""The key maker's privacy check (PRESS-0162, review-code L8.8).

scripts/make-signing-key.py is loaded by path. Only its check runs here: no
key is made, and the real one is never touched.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make-signing-key.py"


def _maker():
    spec = importlib.util.spec_from_file_location("make_signing_key", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
