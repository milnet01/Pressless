"""The tray icon: Open Pressless, Restart and Stop Pressless (PRESS-0204).

This half is what both systems share: the three actions and their words. The
system half is `_tray_windows` on Windows and `_tray_linux` elsewhere, chosen
here at import, so a Linux bundle that cannot import jeepney fails its
--self-check rather than shipping with no tray (INV-7).

A system half's `Icon(entries, tooltip, run)`, `_Icon` here, shows `entries`, `(id, label)`
pairs, in a menu, and calls `run(id)` on its own thread when one is chosen;
a left click on the icon is the first entry. `start()` raises where this
system has no tray, and `close()` removes the icon.
"""
from __future__ import annotations

import functools
import sys
import threading
import webbrowser
from collections.abc import Callable
from typing import TYPE_CHECKING

from pressless.words import say

if sys.platform == "win32":
    from pressless._tray_windows import Icon as _Icon
else:
    from pressless._tray_linux import Icon as _Icon

if TYPE_CHECKING:
    from pressless.face import Face

# The menu's ids. The action table below and both menus are keyed by them.
OPEN, RESTART, STOP = 1, 2, 3
_ENTRIES = ((OPEN, "tray.open"), (RESTART, "tray.restart"), (STOP, "tray.stop"))


class Tray:
    """One per process (§ 4.4). Holds the Face its entries act on now, or
    none between a Face's stop steps and the next `serve`."""

    def __init__(self, stop: Callable[[], None]) -> None:
        self._stop = stop
        self._lock = threading.Lock()
        self._face: Face | None = None
        self._restart: Callable[[], None] | None = None
        self._stopping = False
        self._started = False
        self._icon: _Icon | None = None

    def start(self) -> bool:
        """Show the icon. False where this system has no tray: noted in the
        Face's log, and nothing else changes (INV-6)."""
        labels = [(entry, say(key)) for entry, key in _ENTRIES]
        try:
            icon = _Icon(labels, say("tray.tooltip"), self.run)
            icon.start()
        except Exception as exc:  # noqa: BLE001 -- a tray never stops a launch
            self._note(f"the tray icon could not start: {type(exc).__name__}")
            return False
        self._icon = icon
        return True

    def serve(self, face: Face, restart: Callable[[], None]) -> None:
        """The Face and restart the entries act on now; one call per Face.
        The first call starts the icon. `face.at_stop` makes the tray forget
        the Face, so Open never opens a port that has closed (INV-3)."""
        with self._lock:
            self._face, self._restart = face, restart
        face.at_stop(lambda: self._forget(face))
        if not self._started:
            self._started = True
            self.start()

    def run(self, entry: int) -> None:
        """Run one entry's action. It runs on the tray's own thread, so a
        failure is noted, never raised (§ 4.2)."""
        with self._lock:
            face, restart = self._face, self._restart
            first_stop = entry == STOP and not self._stopping
            self._stopping = self._stopping or entry == STOP
        if entry == STOP:
            # Once, as a second close signal does nothing (PRESS-0208).
            action = self._stop if first_stop else None
        elif face is None or restart is None:
            action = None   # between a Face's stop steps and the next serve
        elif entry == OPEN:
            action = functools.partial(_open, face)
        elif entry == RESTART:
            action = restart
        else:
            action = None
        if action is None:
            return
        try:
            action()
        except Exception as exc:  # noqa: BLE001 -- the icon stays
            self._note(f"a tray action failed: {type(exc).__name__}")

    def close(self) -> None:
        """Remove the icon. Idempotent, and never raises: it runs in the
        launch's last `finally`."""
        icon, self._icon = self._icon, None
        if icon is None:
            return
        try:
            icon.close()
        except Exception:  # noqa: BLE001, S110 -- the process is ending anyway
            pass

    def _forget(self, face: Face) -> None:
        with self._lock:
            if self._face is face:
                self._face = self._restart = None

    def _note(self, text: str) -> None:
        with self._lock:
            face = self._face
        if face is not None:
            face.note(text)


def _open(face: Face) -> None:
    """Open a fresh link (§ 4.3); where no browser opens, print it, as the
    launch does (PRESS-0013 § 4.5 step 5)."""
    link = face.fresh_link()
    try:
        opened = webbrowser.open(link)
    except Exception:  # noqa: BLE001 -- no browser is a case, not a failure
        opened = False
    if not opened:
        print(say("main.open_link", link=link), flush=True)
