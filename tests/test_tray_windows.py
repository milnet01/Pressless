"""The Windows tray's half (PRESS-0204 INV-5, INV-6). Windows only: it runs
on the Windows runner and on the box.

A real hidden window and a real Shell_NotifyIconW, so where Explorer runs the
icon shows for a moment.
"""
from __future__ import annotations

import queue
import sys
import time
from pathlib import Path

import pytest

if sys.platform != "win32":
    pytest.skip("the Windows tray runs on Windows", allow_module_level=True)

from pressless import _tray_windows  # noqa: E402

_ENTRIES = [(1, "Open"), (2, "Again"), (3, "Stop")]


def test_a_click_runs_open_and_close_deletes_the_icon(monkeypatch) -> None:
    """INV-5: the callback message with WM_LBUTTONUP runs Open; after
    close(), the module's one Shell_NotifyIconW call site saw NIM_DELETE,
    and the thread ended.

    Breaks when close() ends the thread without NIM_DELETE."""
    sent: list[int] = []
    real_notify = _tray_windows._notify

    def notify(message, data):
        sent.append(message)
        return real_notify(message, data)

    monkeypatch.setattr(_tray_windows, "_notify", notify)
    chosen: queue.Queue[int] = queue.Queue()
    icon = _tray_windows.Icon(_ENTRIES, "running", chosen.put)
    icon.start()
    try:
        assert sent == [_tray_windows._NIM_ADD]
        assert _tray_windows._api().PostMessageW(
            icon._hwnd, _tray_windows._CALLBACK, 0, _tray_windows._WM_LBUTTONUP)
        assert chosen.get(timeout=5) == 1
    finally:
        icon.close()
    assert _tray_windows._NIM_DELETE in sent
    assert not icon._thread.is_alive(), "the tray's thread did not end"


def test_a_missing_icon_file_raises(monkeypatch, tmp_path: Path) -> None:
    """INV-6's Windows cause on a source run: start() raises, for tray.Tray
    to note, and leaves no thread behind."""
    monkeypatch.setattr(_tray_windows, "_SOURCE_ICON", tmp_path / "missing.ico")
    icon = _tray_windows.Icon(_ENTRIES, "running", lambda entry: None)
    with pytest.raises(OSError):
        icon.start()
    icon._thread.join(timeout=5)
    assert not icon._thread.is_alive()


def _recording(monkeypatch) -> list[int]:
    sent: list[int] = []
    real_notify = _tray_windows._notify

    def notify(message, data):
        sent.append(message)
        return real_notify(message, data)

    monkeypatch.setattr(_tray_windows, "_notify", notify)
    return sent


def test_another_programs_close_leaves_the_icon(monkeypatch) -> None:
    """§ 4.5: a WM_CLOSE from outside deletes nothing and ends nothing;
    close() still does. Breaks when close() and an outside close share
    one message."""
    sent = _recording(monkeypatch)
    icon = _tray_windows.Icon(_ENTRIES, "running", lambda entry: None)
    icon.start()
    try:
        assert _tray_windows._api().PostMessageW(icon._hwnd, _tray_windows._WM_CLOSE, 0, 0)
        time.sleep(0.2)
        assert _tray_windows._NIM_DELETE not in sent
        assert icon._thread.is_alive()
    finally:
        icon.close()
    assert _tray_windows._NIM_DELETE in sent
    assert not icon._thread.is_alive()


def test_a_right_click_opens_the_menu_and_explorer_restarting_adds_the_icon(
        monkeypatch) -> None:
    """The window procedure's other two branches (review-tests lane H).
    Breaks when the right click or TaskbarCreated is dropped."""
    sent = _recording(monkeypatch)
    menus: queue.Queue[int] = queue.Queue()
    monkeypatch.setattr(_tray_windows.Icon, "_menu", lambda self, hwnd: menus.put(hwnd))
    icon = _tray_windows.Icon(_ENTRIES, "running", lambda entry: None)
    icon.start()
    try:
        api = _tray_windows._api()
        assert api.PostMessageW(icon._hwnd, _tray_windows._CALLBACK, 0,
                                _tray_windows._WM_RBUTTONUP)
        assert menus.get(timeout=5) == icon._hwnd
        assert api.PostMessageW(icon._hwnd, icon._taskbar_created, 0, 0)
        deadline = time.monotonic() + 5
        while sent.count(_tray_windows._NIM_ADD) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert sent.count(_tray_windows._NIM_ADD) == 2
    finally:
        icon.close()


def test_a_long_tooltip_is_cut_by_utf16_units(monkeypatch) -> None:
    """A tooltip of characters outside the basic range fits szTip. Breaks
    when it is cut by Python characters, which then overflow it."""
    sent = _recording(monkeypatch)
    icon = _tray_windows.Icon(_ENTRIES, "\U0001F600" * 127, lambda entry: None)
    assert len(icon._tooltip.encode("utf-16-le")) <= 2 * 127
    icon.start()
    try:
        assert sent == [_tray_windows._NIM_ADD]
    finally:
        icon.close()


def test_a_start_that_gives_up_leaves_no_icon(monkeypatch) -> None:
    """A window starting after start() timed out adds no icon and ends its
    thread. Breaks when the late thread adds an icon nothing deletes."""
    sent = _recording(monkeypatch)
    real_load = _tray_windows._load_icon

    def slow_load():
        time.sleep(0.5)
        return real_load()

    monkeypatch.setattr(_tray_windows, "_load_icon", slow_load)
    monkeypatch.setattr(_tray_windows, "_START_WAIT", 0.05)
    icon = _tray_windows.Icon(_ENTRIES, "running", lambda entry: None)
    with pytest.raises(TimeoutError):
        icon.start()
    icon._thread.join(timeout=5)
    assert not icon._thread.is_alive()
    assert sent == []
