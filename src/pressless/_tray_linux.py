"""The tray icon on Linux: a StatusNotifierItem over jeepney (PRESS-0204 § 4.6).

The item lives at /StatusNotifierItem under its own bus name and registers
with the desktop's org.kde.StatusNotifierWatcher; its menu lives at /MenuBar
on com.canonical.dbusmenu. One thread owns the connection and answers every
call, so nothing else ever reads from it.

Sources: https://specifications.freedesktop.org/status-notifier-item/0.1/
status-notifier-item.html and the dbusmenu interface,
https://docs.rs/crate/ksni/0.3.3/source/spec/DBusMenu.xml
"""
from __future__ import annotations

import contextlib
import os
import socket
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from jeepney import (
    DBusAddress,
    HeaderFields,
    Message,
    MessageType,
    new_error,
    new_method_call,
    new_method_return,
)
from jeepney.bus_messages import MatchRule, message_bus
from jeepney.io.blocking import DBusConnection, open_dbus_connection
from PIL import Image

_ITEM_PATH = "/StatusNotifierItem"
_MENU_PATH = "/MenuBar"
_ITEM = "org.kde.StatusNotifierItem"
_MENU = "com.canonical.dbusmenu"
_PROPERTIES = "org.freedesktop.DBus.Properties"
_WATCHER_NAME = "org.kde.StatusNotifierWatcher"
_WATCHER = DBusAddress("/StatusNotifierWatcher", bus_name=_WATCHER_NAME,
                       interface=_WATCHER_NAME)
_UNKNOWN_METHOD = "org.freedesktop.DBus.Error.UnknownMethod"
_UNKNOWN_PROPERTY = "org.freedesktop.DBus.Error.UnknownProperty"
_INVALID_ARGS = "org.freedesktop.DBus.Error.InvalidArgs"
_PRIMARY_OWNER = 1          # RequestName's reply when the name is ours
_SIZES = (22, 44)           # measured on Plasma 6: the panel's size and twice it
_START_WAIT = 10.0          # seconds for the bus to answer a start call
_ICON = "pressless.png"     # inside the AppImage, as shortcuts._ICON
_SOURCE_ICON = Path(__file__).resolve().parents[2] / "packaging" / "icons" / _ICON


def _icon_file() -> Path:
    """The AppImage's own icon, or the repository's on a source run."""
    bundled = os.environ.get("APPDIR")
    return Path(bundled) / _ICON if bundled else _SOURCE_ICON


def _pixmap(image: Image.Image, size: int) -> tuple[int, int, bytes]:
    """One IconPixmap entry: ARGB32 in network byte order."""
    rgba = image.resize((size, size)).tobytes()
    argb = bytearray(len(rgba))
    argb[0::4], argb[1::4], argb[2::4], argb[3::4] = (
        rgba[3::4], rgba[0::4], rgba[1::4], rgba[2::4])
    return size, size, bytes(argb)


class Icon:
    """One StatusNotifierItem, on a connection and a thread of its own."""

    def __init__(self, entries: Sequence[tuple[int, str]], tooltip: str,
                 run: Callable[[int], None]) -> None:
        self._entries = list(entries)
        self._tooltip = tooltip
        self._run = run
        self._closing = threading.Event()
        self._thread: threading.Thread | None = None
        self._name = f"{_ITEM}-{os.getpid()}-1"
        self._properties: dict[str, tuple[str, object]] = {}
        self._conn: DBusConnection | None = None

    def start(self) -> None:
        """Register the item, or wait for a watcher to appear. Raises where
        there is no session bus or no icon file (INV-6)."""
        with Image.open(_icon_file()) as opened:
            image = opened.convert("RGBA")
        pixmaps = [_pixmap(image, size) for size in _SIZES]
        conn = open_dbus_connection(bus="SESSION")
        try:
            reply = conn.send_and_get_reply(message_bus.RequestName(self._name),
                                            timeout=_START_WAIT)
            if reply.header.message_type is MessageType.error or reply.body[0] != _PRIMARY_OWNER:
                raise OSError(f"the bus name was refused: {reply.body!r}")
            # Plasma starting late, or restarted: register when a watcher appears.
            rule = MatchRule(type="signal", sender="org.freedesktop.DBus",
                             interface="org.freedesktop.DBus", member="NameOwnerChanged")
            rule.add_arg_condition(0, _WATCHER_NAME)
            conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=_START_WAIT)
            self._properties = self._table(pixmaps)
            self._register(conn)
        except BaseException:
            conn.close()
            raise
        self._conn = conn
        self._thread = threading.Thread(target=self._serve, args=(conn,),
                                        name="pressless-tray", daemon=True)
        self._thread.start()

    def _table(self, pixmaps: list[tuple[int, int, bytes]]) -> dict[str, tuple[str, object]]:
        return {
            "Category": ("s", "ApplicationStatus"),
            "Id": ("s", "pressless"),
            "Title": ("s", "Pressless"),
            "Status": ("s", "Active"),
            "WindowId": ("i", 0),
            "IconName": ("s", ""),
            "IconPixmap": ("a(iiay)", pixmaps),
            "ToolTip": ("(sa(iiay)ss)", ("", [], "Pressless", self._tooltip)),
            "ItemIsMenu": ("b", False),     # so a left click sends Activate
            "Menu": ("o", _MENU_PATH),
        }

    def close(self) -> None:
        """End the thread, which closes the connection: the bus then
        releases the name and the watcher drops the item. Shutting the
        socket wakes the thread, which otherwise sleeps until a call."""
        self._closing.set()
        if self._conn is not None:
            with contextlib.suppress(OSError):
                self._conn.sock.shutdown(socket.SHUT_RDWR)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def _register(self, conn: DBusConnection) -> None:
        # Not send_and_get_reply: that drops any call arriving before the
        # reply. Its reply needs nothing either way: an error means no
        # watcher yet, and NameOwnerChanged registers when one appears.
        conn.send(new_method_call(_WATCHER, "RegisterStatusNotifierItem", "s",
                                  (self._name,)))

    def _serve(self, conn: DBusConnection) -> None:
        try:
            while not self._closing.is_set():
                message = conn.receive()
                try:
                    self._take(conn, message)
                except OSError:
                    raise
                except Exception:  # noqa: BLE001 -- one odd message never ends the tray
                    if message.header.message_type is MessageType.method_call:
                        conn.send(new_error(message, _INVALID_ARGS))
        except OSError:
            pass    # the bus went away, or close(): there is no tray to serve
        finally:
            conn.close()

    def _take(self, conn: DBusConnection, message: Message) -> None:
        header = message.header
        if header.message_type is MessageType.signal:
            # NameOwnerChanged(name, old, new): a watcher has appeared.
            if header.fields.get(HeaderFields.member) == "NameOwnerChanged" \
                    and message.body[0] == _WATCHER_NAME and message.body[2]:
                self._register(conn)
        elif header.message_type is MessageType.method_call:
            self._answer(conn, message)

    def _answer(self, conn: DBusConnection, call: Message) -> None:
        fields = call.header.fields
        path = fields.get(HeaderFields.path)
        interface = fields.get(HeaderFields.interface)
        member = fields.get(HeaderFields.member)
        after: Callable[[], None] | None = None
        if interface == _PROPERTIES and member in ("GetAll", "Get"):
            reply = self._property(call, path)
        elif path == _ITEM_PATH and interface == _ITEM:
            reply = new_method_return(call)
            if member == "Activate":
                after = self._activate
        elif path == _MENU_PATH and interface == _MENU:
            reply, after = self._menu(call, member)
        else:
            reply = new_error(call, _UNKNOWN_METHOD)
        conn.send(reply)
        if after is not None:
            after()     # once answered, so the desktop is not kept waiting

    def _activate(self) -> None:
        self._run(self._entries[0][0])

    def _property(self, call: Message, path: str | None) -> Message:
        table = self._properties if path == _ITEM_PATH else {
            "Version": ("u", 3), "Status": ("s", "normal"),
            "TextDirection": ("s", "ltr"), "IconThemePath": ("as", []),
        }
        if call.header.fields.get(HeaderFields.member) == "GetAll":
            return new_method_return(call, "a{sv}", (table,))
        name = call.body[1]
        if name not in table:
            return new_error(call, _UNKNOWN_PROPERTY)
        return new_method_return(call, "v", (table[name],))

    def _menu(self, call: Message,
              member: str | None) -> tuple[Message, Callable[[], None] | None]:
        labels = dict(self._entries)
        if member == "GetLayout":
            parent = call.body[0]
            if parent in labels:
                layout = (parent, {"label": ("s", labels[parent])}, [])
            else:
                children = [("(ia{sv}av)", (entry, {"label": ("s", label)}, []))
                            for entry, label in self._entries]
                layout = (0, {"children-display": ("s", "submenu")}, children)
            return new_method_return(call, "u(ia{sv}av)", (1, layout)), None
        if member == "GetGroupProperties":
            wanted = call.body[0] or list(labels)
            rows = [(entry, {"label": ("s", labels[entry])})
                    for entry in wanted if entry in labels]
            return new_method_return(call, "a(ia{sv})", (rows,)), None
        if member == "GetProperty":
            entry, name = call.body
            if entry in labels and name == "label":
                return new_method_return(call, "v", (("s", labels[entry]),)), None
            return new_error(call, _UNKNOWN_PROPERTY), None
        if member == "AboutToShow":
            return new_method_return(call, "b", (False,)), None
        if member == "AboutToShowGroup":
            return new_method_return(call, "aiai", ([], [])), None
        if member == "Event":
            entry, kind = call.body[0], call.body[1]
            return new_method_return(call), self._clicked([(entry, kind)])
        if member == "EventGroup":
            events = [(entry, kind) for entry, kind, _data, _time in call.body[0]]
            missing = [entry for entry, _ in events if entry not in labels]
            return new_method_return(call, "ai", (missing,)), self._clicked(events)
        return new_error(call, _UNKNOWN_METHOD), None

    def _clicked(self, events: list[tuple[int, str]]) -> Callable[[], None] | None:
        chosen = [entry for entry, kind in events
                  if kind == "clicked" and entry in dict(self._entries)]
        if not chosen:
            return None

        def run_chosen() -> None:
            for entry in chosen:
                self._run(entry)

        return run_chosen
