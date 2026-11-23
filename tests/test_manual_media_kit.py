"""The manual's media kit removes only the instance folder it made
(PRESS-0361; review-code lane-19 kit.py:21).

scripts/manual-media/kit.py is loaded by path. No instance starts: the
program it would run is replaced by one that only prints its link.
"""
from __future__ import annotations

import atexit

import pytest
from _scripts import load_script


class _Instance:
    """Stands in for the instance's process: prints a link and waits."""

    def __init__(self, argv, stdout, stderr):
        stdout.write("LINK http://127.0.0.1:1/?t=x\n")
        stdout.flush()

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self):
        return 0


@pytest.fixture
def kit(tmp_path, monkeypatch):
    registered: list[object] = []
    monkeypatch.setattr(atexit, "register", registered.append)
    monkeypatch.setattr(atexit, "unregister", lambda hook: None)
    loaded = load_script("manual-media/kit.py")
    loaded.registered = registered
    monkeypatch.setattr(loaded, "WORK", tmp_path)
    monkeypatch.setattr(loaded, "INSTANCE", tmp_path / "instance")
    monkeypatch.setattr(loaded.subprocess, "Popen", _Instance)
    return loaded


def test_importing_the_kit_removes_nothing_on_exit(kit):
    """frozen_check.py and the instance import the kit; at their exit it
    removed the folder a running shots.py or video.py was using."""
    assert kit.registered == []


def test_a_folder_the_kit_did_not_make_is_never_removed(kit):
    """PRESSLESS_MANUAL_WORK naming a real folder lost any instance/ in it."""
    (kit.INSTANCE / "kept").mkdir(parents=True)
    with pytest.raises(SystemExit, match="not made by"):
        kit.start()
    kit.stop()
    assert (kit.INSTANCE / "kept").is_dir()


def test_the_kit_removes_the_folder_it_made(kit):
    assert kit.start() == "http://127.0.0.1:1/?t=x"
    assert kit.registered == [kit.stop]
    assert kit.INSTANCE.is_dir()
    kit.start()                       # a restart replaces its own folder
    kit.stop()
    assert not kit.INSTANCE.exists()
