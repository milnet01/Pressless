"""The Linux tray's half on a private session bus (PRESS-0204 INV-4, INV-6).

A private dbus-daemon stands in for the desktop's bus and a fake watcher,
written with jeepney, for Plasma's. Linux only. Where dbus-daemon is absent
the tests skip, except where CI is set: there they fail, so the Linux runner
cannot skip them quietly.
"""
from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

if sys.platform != "linux":
    pytest.skip("the Linux tray runs on Linux", allow_module_level=True)

from jeepney import DBusAddress, MessageType, new_method_call, new_method_return  # noqa: E402
from jeepney.bus_messages import message_bus  # noqa: E402
from jeepney.io.blocking import open_dbus_connection  # noqa: E402

from pressless import _tray_linux  # noqa: E402

_ENTRIES = [(1, "Open"), (2, "Again"), (3, "Stop")]
_WATCHER = "org.kde.StatusNotifierWatcher"
_WAIT = 5.0


@pytest.fixture
def bus(monkeypatch):
    """A private session bus; DBUS_SESSION_BUS_ADDRESS points at it."""
    program = shutil.which("dbus-daemon")
    if program is None:
        if os.environ.get("CI"):
            pytest.fail("dbus-daemon is missing on CI, so INV-4 would be skipped quietly")
        pytest.skip("dbus-daemon is not installed")
    daemon = subprocess.Popen(  # noqa: S603 -- a fixed program with fixed arguments
        [program, "--session", "--nofork", "--nopidfile", "--print-address=1"],
        stdout=subprocess.PIPE, text=True)
    try:
        address = daemon.stdout.readline().strip()
        assert address, "dbus-daemon printed no address"
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
        yield address
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)
        daemon.stdout.close()


class _Watcher:
    """Plasma's watcher, as far as registration goes: owns the name and
    records every RegisterStatusNotifierItem it is sent."""

    def __init__(self) -> None:
        self.registered: queue.Queue[str] = queue.Queue()
        self._conn = open_dbus_connection(bus="SESSION")
        reply = self._conn.send_and_get_reply(message_bus.RequestName(_WATCHER))
        assert reply.body == (1,), reply.body
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._done.is_set():
            try:
                message = self._conn.receive(timeout=0.1)
            except TimeoutError:
                continue
            if message.header.message_type is MessageType.method_call:
                self.registered.put(message.body[0])
                self._conn.send(new_method_return(message))

    def close(self) -> None:
        self._done.set()
        self._thread.join(timeout=_WAIT)
        self._conn.close()


class _Client:
    """The desktop's side: calls the item and its menu."""

    def __init__(self, name: str) -> None:
        self._conn = open_dbus_connection(bus="SESSION")
        self.name = name

    def call(self, path: str, interface: str, member: str, signature: str = "",
             body: tuple = ()):
        address = DBusAddress(path, bus_name=self.name, interface=interface)
        reply = self._conn.send_and_get_reply(
            new_method_call(address, member, signature, body), timeout=_WAIT)
        assert reply.header.message_type is MessageType.method_return, reply.body
        return reply.body

    def owner(self) -> bool:
        reply = self._conn.send_and_get_reply(message_bus.NameHasOwner(self.name),
                                              timeout=_WAIT)
        return bool(reply.body[0])

    def close(self) -> None:
        self._conn.close()


def _icon(chosen: queue.Queue[int]) -> _tray_linux.Icon:
    return _tray_linux.Icon(_ENTRIES, "running", chosen.put)


def test_the_item_registers_and_its_menu_runs_the_entries(bus) -> None:
    """INV-4: registration arrives, GetLayout lists the three entries, and
    Event(id, "clicked") and Activate each reach the recorder; closing
    releases the name.

    Breaks when the menu's ids and the action table disagree."""
    watcher = _Watcher()
    chosen: queue.Queue[int] = queue.Queue()
    icon = _icon(chosen)
    icon.start()
    client = None
    try:
        name = watcher.registered.get(timeout=_WAIT)
        assert name == f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        client = _Client(name)

        props = client.call("/StatusNotifierItem", "org.freedesktop.DBus.Properties",
                            "GetAll", "s", ("org.kde.StatusNotifierItem",))[0]
        assert props["ItemIsMenu"] == ("b", False)
        assert props["Menu"] == ("o", "/MenuBar")
        sizes = [(w, h, len(data)) for w, h, data in props["IconPixmap"][1]]
        assert sizes and all(length == w * h * 4 for w, h, length in sizes), sizes

        revision, (root, _, children) = client.call(
            "/MenuBar", "com.canonical.dbusmenu", "GetLayout", "iias", (0, -1, []))
        listed = [(entry, values["label"][1]) for _, (entry, values, _) in children]
        assert root == 0 and listed == _ENTRIES

        for entry, _ in _ENTRIES:
            client.call("/MenuBar", "com.canonical.dbusmenu", "Event", "isvu",
                        (entry, "clicked", ("s", ""), 0))
            assert chosen.get(timeout=_WAIT) == entry
        client.call("/MenuBar", "com.canonical.dbusmenu", "Event", "isvu",
                    (1, "hovered", ("s", ""), 0))
        client.call("/StatusNotifierItem", "org.kde.StatusNotifierItem", "Activate",
                    "ii", (0, 0))
        # Hovering runs nothing, so the next thing recorded is Activate's Open.
        assert chosen.get(timeout=_WAIT) == 1
        assert chosen.empty()

        icon.close()
        assert not client.owner(), "closing left the item's name on the bus"
    finally:
        icon.close()
        if client is not None:
            client.close()
        watcher.close()


def test_a_watcher_that_appears_later_is_registered_with(bus) -> None:
    """§ 4.6: Plasma starting late, or restarted. start() succeeds with no
    watcher, and the item registers when one takes the name."""
    chosen: queue.Queue[int] = queue.Queue()
    icon = _icon(chosen)
    icon.start()
    watcher = None
    try:
        watcher = _Watcher()
        assert watcher.registered.get(timeout=_WAIT).startswith("org.kde.StatusNotifierItem-")
    finally:
        icon.close()
        if watcher is not None:
            watcher.close()


def test_no_session_bus_or_no_icon_file_raises(bus, monkeypatch, tmp_path: Path) -> None:
    """INV-6's Linux causes: start() raises, for tray.Tray to note."""
    monkeypatch.setenv("APPDIR", str(tmp_path))       # an AppImage with no icon in it
    with pytest.raises(OSError):
        _icon(queue.Queue()).start()
    monkeypatch.delenv("APPDIR")
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS")
    with pytest.raises(KeyError):
        _icon(queue.Queue()).start()
