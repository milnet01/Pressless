"""The practice copy's own guarantees (PRESS-0202).

scripts/practice.py is loaded by path, like the signer. Every module change
disarm() makes is passed through monkeypatch, so it is undone after each test.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from pressless import google_signin, insights, publisher, settings, updater

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "practice.py"


# The practice copy keeps its made-up key in a file, which Pressless refuses
# on Windows; run.sh, its only starter, is Linux's.
pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="the practice copy runs on Linux only")


def _practice():
    spec = importlib.util.spec_from_file_location("practice", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("text, port", [(None, 0), ("", 0), (" ", 0),
                                        ("1", 1), ("8471", 8471), ("65535", 65535)])
def test_a_port_is_read_from_port(text, port):
    assert _practice().port_from(text) == port


@pytest.mark.parametrize("text", ["0", "65536", "-1", "eighty", "84.71"])
def test_anything_else_is_refused(text):
    with pytest.raises(ValueError):
        _practice().port_from(text)


def test_the_seeded_folder_is_one_the_launcher_accepts(tmp_path):
    """Breaks when the launcher would send the practice copy to /setup."""
    _practice().seed(tmp_path)
    loaded = settings.load(tmp_path)
    assert loaded.site_folder == tmp_path / "site"
    assert loaded.site_folder.is_dir()


def test_a_disarmed_publish_never_reaches_github(monkeypatch, tmp_path):
    practice = _practice()
    practice.seed(tmp_path)
    practice.disarm(monkeypatch.setattr)
    with pytest.raises(publisher.Unreachable):
        publisher.publish(settings.load(tmp_path), tmp_path / "site", "not-a-key",
                          "practice")


def test_no_other_route_out_is_left(monkeypatch):
    practice = _practice()
    practice.disarm(monkeypatch.setattr)
    assert google_signin.available() is False
    with pytest.raises(OSError):
        insights._own_client().request("GET", "https://example.invalid", None, {})
    with pytest.raises(OSError):
        updater._Urllib().open("https://example.invalid")


@pytest.fixture
def main_without_serving(monkeypatch, tmp_path):
    """practice.main() with launcher._serve replaced by `serve`, and every
    module-level change main makes undone afterwards."""
    import os
    import signal

    from pressless import __main__ as launcher
    from pressless import face

    practice = _practice()
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("PORT", raising=False)
    for module, name in ((publisher, "_Urllib"), (updater, "_Urllib"),
                         (insights, "_own_client"), (google_signin, "available"),
                         (face, "serve")):
        monkeypatch.setattr(module, name, getattr(module, name))
    old = signal.getsignal(signal.SIGTERM)

    def run(serve):
        monkeypatch.setattr(launcher, "_serve", serve)
        try:
            return practice.main()
        finally:
            signal.signal(signal.SIGTERM, old)

    def terminate():
        os.kill(os.getpid(), signal.SIGTERM)

    return run, terminate


def test_a_second_sigterm_while_stopping_still_exits_0(main_without_serving):
    """PRESS-0208: the local web-server manager's SIGTERM to the process group
    can arrive twice; the second one used to escape as KeyboardInterrupt."""
    run, terminate = main_without_serving

    def serve(folder):
        try:
            terminate()
        except KeyboardInterrupt:
            terminate()   # a second one, while the first is shutting down
        return 0

    assert run(serve) == 0


def test_a_sigterm_while_starting_exits_0(main_without_serving):
    """Before the launcher's wait, nothing in it catches the interruption."""
    run, terminate = main_without_serving

    def serve(folder):
        terminate()
        return 0

    assert run(serve) == 0
