"""The Windows tray's half (PRESS-0204 INV-5, INV-6). Windows only: it runs
on the Windows runner and on the box.

A real hidden window and a real Shell_NotifyIconW, so where Explorer runs the
icon shows for a moment.
"""
from __future__ import annotations

import queue
import sys
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
