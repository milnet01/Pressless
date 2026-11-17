"""The practice copy's own guarantees (PRESS-0202).

scripts/practice.py is loaded by path, like the signer. Every module change
disarm() makes is passed through monkeypatch, so it is undone after each test.
"""
from __future__ import annotations

import ast
import socket
import sys
from types import ModuleType

import pytest
from _scripts import load_script
from test_network_timeouts import _WALKED, _imports_network_machinery

from pressless import (
    github_signin,
    google_signin,
    https,
    insights,
    publisher,
    settings,
    updater,
    usage,
)
from pressless_import import fetch

# The practice copy keeps its made-up key in a file, which Pressless refuses
# on Windows; run.sh, its only starter, is Linux's.
pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="the practice copy runs on Linux only")


def _practice():
    return load_script("practice.py")


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


def _network_modules(roots) -> set[str]:
    """The dotted name of every module under `roots` that can open a socket,
    judged by what it imports, as the timeout test judges it."""
    found = set()
    for root in roots:
        for source in root.rglob("*.py"):
            if _imports_network_machinery(ast.parse(source.read_text(encoding="utf-8"))):
                parts = source.relative_to(root.parent).with_suffix("").parts
                found.add(".".join(part for part in parts if part != "__init__"))
    return found


def _disarmed(practice) -> set[str]:
    """The modules whose names disarm() replaces something in."""
    touched = set()

    def record(target, name, value):
        touched.add(target.__name__ if isinstance(target, ModuleType) else target.__module__)

    practice.disarm(record)
    return touched


def test_every_module_that_can_open_a_connection_is_disarmed(tmp_path):
    """Breaks when a module that opens connections is added, or gains a
    network import, and disarm() leaves it alone. The modules are found by
    walking the source, never listed, so a new one fails here the day it is
    written. The planted module proves the walk sees one it does not know."""
    practice = _practice()
    covered = _disarmed(practice) | set(practice.LOCAL_ONLY)
    found = _network_modules(_WALKED)
    assert "pressless.https" in found   # the walk sees the shared client at all
    assert found - covered == set()

    planted = tmp_path / "pressless"
    planted.mkdir()
    (planted / "planted.py").write_text("import socket\n", encoding="utf-8")
    assert _network_modules((*_WALKED, planted)) - covered == {"pressless.planted"}


@pytest.fixture
def no_network(monkeypatch):
    """A tripwire: reaching for the network fails the test, never with OSError,
    so only disarm's own refusal satisfies it."""
    def reached(*args, **kwargs):
        raise AssertionError("the practice copy reached for the network")

    for target, name in ((socket, "getaddrinfo"), (socket, "create_connection"),
                         (socket.socket, "connect")):
        monkeypatch.setattr(target, name, reached)


_URL = "https://example.invalid/"
_ROUTES = {
    "shared client: GitHub, Google, votes": lambda: https.Client(5).request("GET", _URL, None, {}),
    "Publish": lambda: publisher._Urllib().request("GET", _URL, None, {}),
    "Insights' own client: Analytics, YouTube":
        lambda: insights.own_client().request("GET", _URL, None, {}),
    "usage reports": lambda: usage._Opener().request("POST", _URL, b"{}", {}),
    "the Updater": lambda: updater._Urllib().open(_URL),
    "Import's name look-up": lambda: fetch.addresses("example.invalid", 443),
    "Import's connection": lambda: fetch._connect("192.0.2.1", "example.invalid", 443, True),
}


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_every_route_out_refuses(route, monkeypatch, no_network):
    """Breaks when a route still reaches for the network after disarm(), as
    YouTube, usage reports, votes and Import's fetch once did."""
    _practice().disarm(monkeypatch.setattr)
    with pytest.raises(OSError, match="practice copy"):
        _ROUTES[route]()


def test_both_sign_ins_are_switched_off(monkeypatch):
    _practice().disarm(monkeypatch.setattr)
    assert google_signin.available() is False
    assert github_signin.available() is False


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
    disarm = practice.disarm
    monkeypatch.setattr(practice, "disarm", lambda: disarm(monkeypatch.setattr))
    monkeypatch.setattr(face, "serve", face.serve)
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


def test_the_practice_site_is_seeded_once_inside_sites(main_without_serving, tmp_path):
    """PRESS-0223: the practice copy's site is site-1, like any other. Breaks
    when a second start seeds again at the top, or the port wrapper refuses
    the launcher's site."""
    from pressless import face

    run, _ = main_without_serving
    unwrapped = face.serve

    def serve(folder):
        face.serve(folder, site=folder / "sites" / "site-1").stop()
        return 0

    assert run(serve) == 0
    face.serve = unwrapped   # each start is its own process
    assert run(serve) == 0
    own = tmp_path / _practice().FOLDER_NAME
    assert settings.load(own / "sites" / "site-1").repository == "practice/not-a-real-repository"
    assert not (own / "settings.json").exists()
