"""The parts of scripts/by-hand-votes-rules.py that run without the emulators.

The script itself needs Java and firebase-tools (PRESS-0211 INV-6), so it is
run by hand. These tests load it by path and call the pieces that decide what
it sends and how it fails; nothing here starts an emulator or opens a socket.
"""
from __future__ import annotations

import pytest
from _scripts import load_script

from pressless import votes


def _script():
    return load_script("by-hand-votes-rules.py")


def test_a_failed_sign_up_stops_the_run_saying_why(monkeypatch):
    """Breaks when the check is an assert, which `python -O` removes."""
    script = _script()
    monkeypatch.setattr(script, "_call", lambda *args, **kwargs: (400, "no such project"))
    with pytest.raises(SystemExit, match="400.*no such project"):
        script._visitor()


def test_only_the_local_emulators_are_called():
    """Breaks when _call opens any address it is given."""
    script = _script()
    with pytest.raises(ValueError, match="not an emulator address"):
        script._call("GET", "file:///no-such-file-anywhere")


def test_the_key_length_rows_follow_the_rules_limit():
    """Breaks when votes.RULES changes its key limit and the script does not."""
    script = _script()
    assert f"entry.size() <= {script.KEY_LIMIT}" in votes.RULES
    assert len(script.KEY_OVER) == script.KEY_LIMIT + 1
    assert len(script.KEY_AT) == script.KEY_LIMIT
