"""The tray icon on Windows: Shell_NotifyIconW over ctypes (PRESS-0204 § 4.5).

A hidden top-level window, on a thread of its own, owns the icon and takes
its clicks. Top-level, not message-only: only a top-level window receives
TaskbarCreated, which Explorer broadcasts when it restarts, and which adds
the icon again. The calls are bound when the icon starts, so a system
missing one fails start() rather than the import (INV-6).
"""
from __future__ import annotations

import ctypes
import functools
import sys
import threading
import types
from collections.abc import Callable, Sequence
from ctypes import wintypes
from pathlib import Path

_SOURCE_ICON = Path(__file__).resolve().parents[2] / "packaging" / "icons" / "pressless.ico"

_CALLBACK = 0x8001          # WM_APP + 1: the icon's messages
_CLOSE_ICON = 0x8002        # WM_APP + 2: close() alone; another program's WM_CLOSE is ignored
_ICON_ID = 1
_WM_NULL, _WM_DESTROY, _WM_CLOSE = 0x0000, 0x0002, 0x0010
_WM_LBUTTONUP, _WM_RBUTTONUP = 0x0202, 0x0205
_NIM_ADD, _NIM_DELETE = 0, 2
_NIF_MESSAGE, _NIF_ICON, _NIF_TIP = 0x1, 0x2, 0x4
_TPM_RIGHTBUTTON, _TPM_NONOTIFY, _TPM_RETURNCMD = 0x2, 0x80, 0x100
_IMAGE_ICON, _LR_LOADFROMFILE = 1, 0x10
_SM_CXSMICON, _SM_CYSMICON = 49, 50
_START_WAIT = 10.0
_TIP_UNITS = 127            # szTip's UTF-16 units, less its closing null

_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                              wintypes.LPARAM)


class _WindowClass(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", _WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class _Guid(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class _NotifyIconData(ctypes.Structure):
    """NOTIFYICONDATAW, Vista's size and later."""
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", _Guid), ("hBalloonIcon", wintypes.HICON)]


@functools.cache
def _api() -> types.SimpleNamespace:
    """Every call this module makes, with its types. Its own DLL objects, so
    the types set here reach no other module's calls."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    found = {}

    def bind(dll: ctypes.WinDLL, name: str, result: object, *arguments: object) -> None:
        function = getattr(dll, name)
        function.restype, function.argtypes = result, arguments
        found[name] = function

    handle, hwnd, uint = wintypes.HANDLE, wintypes.HWND, wintypes.UINT
    bind(kernel32, "GetModuleHandleW", wintypes.HMODULE, wintypes.LPCWSTR)
    bind(user32, "RegisterClassExW", wintypes.ATOM, ctypes.POINTER(_WindowClass))
    bind(user32, "UnregisterClassW", wintypes.BOOL, wintypes.LPCWSTR, wintypes.HINSTANCE)
    bind(user32, "CreateWindowExW", hwnd, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
         wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, hwnd,
         wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
    bind(user32, "DestroyWindow", wintypes.BOOL, hwnd)
    bind(user32, "DefWindowProcW", _LRESULT, hwnd, uint, wintypes.WPARAM, wintypes.LPARAM)
    bind(user32, "PostMessageW", wintypes.BOOL, hwnd, uint, wintypes.WPARAM, wintypes.LPARAM)
    bind(user32, "PostQuitMessage", None, ctypes.c_int)
    bind(user32, "GetMessageW", wintypes.BOOL, ctypes.POINTER(wintypes.MSG), hwnd, uint, uint)
    bind(user32, "TranslateMessage", wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
    bind(user32, "DispatchMessageW", _LRESULT, ctypes.POINTER(wintypes.MSG))
    bind(user32, "RegisterWindowMessageW", uint, wintypes.LPCWSTR)
    bind(user32, "CreatePopupMenu", wintypes.HMENU)
    bind(user32, "AppendMenuW", wintypes.BOOL, wintypes.HMENU, uint, wintypes.WPARAM,
         wintypes.LPCWSTR)
    bind(user32, "TrackPopupMenu", wintypes.BOOL, wintypes.HMENU, uint, ctypes.c_int,
         ctypes.c_int, ctypes.c_int, hwnd, wintypes.LPVOID)
    bind(user32, "DestroyMenu", wintypes.BOOL, wintypes.HMENU)
    bind(user32, "GetCursorPos", wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
    bind(user32, "SetForegroundWindow", wintypes.BOOL, hwnd)
    bind(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
    bind(user32, "LoadImageW", handle, wintypes.HINSTANCE, wintypes.LPCWSTR, uint,
         ctypes.c_int, ctypes.c_int, uint)
    bind(user32, "DestroyIcon", wintypes.BOOL, wintypes.HICON)
    bind(shell32, "ExtractIconExW", uint, wintypes.LPCWSTR, ctypes.c_int,
         ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), uint)
    bind(shell32, "Shell_NotifyIconW", wintypes.BOOL, wintypes.DWORD,
         ctypes.POINTER(_NotifyIconData))
    return types.SimpleNamespace(**found)


def _notify(message: int, data: _NotifyIconData) -> bool:
    """The module's one Shell_NotifyIconW call: INV-5's test wraps it."""
    return bool(_api().Shell_NotifyIconW(message, ctypes.byref(data)))


def _load_icon() -> int:
    """The icon PyInstaller embeds in the .exe, or the repository's .ico on
    a source run, at the size the notification area draws."""
    api = _api()
    if getattr(sys, "frozen", False):
        small = wintypes.HICON()
        if api.ExtractIconExW(sys.executable, 0, None, ctypes.byref(small), 1) and small:
            return small.value
        raise OSError("the program's icon could not be loaded")
    loaded = api.LoadImageW(None, str(_SOURCE_ICON), _IMAGE_ICON,
                            api.GetSystemMetrics(_SM_CXSMICON),
                            api.GetSystemMetrics(_SM_CYSMICON), _LR_LOADFROMFILE)
    if not loaded:
        raise ctypes.WinError(ctypes.get_last_error())
    return loaded


def _cut_tip(text: str) -> str:
    """`text` cut to what szTip holds, counted in UTF-16 units, never
    splitting a character."""
    units = text.encode("utf-16-le")[:2 * _TIP_UNITS]
    return units.decode("utf-16-le", errors="ignore")


class Icon:
    """One notification-area icon, on a hidden window and a thread of its own."""

    def __init__(self, entries: Sequence[tuple[int, str]], tooltip: str,
                 run: Callable[[int], None]) -> None:
        self._entries = list(entries)
        self._tooltip = _cut_tip(tooltip)
        self._run = run
        self._class = f"PresslessTray-{id(self)}"     # two icons never share a class
        self._procedure = _WNDPROC(self._window_procedure)   # kept alive while Windows calls it
        self._hwnd: int | None = None
        self._icon: int | None = None
        self._taskbar_created = 0
        self._ready = threading.Event()
        self._failure: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._abandoned = False      # start() gave up; the thread must add nothing

    def start(self) -> None:
        """Make the window and add the icon; raises where that cannot be done.
        An icon Explorer refuses now, while it starts, say, is added on its
        TaskbarCreated."""
        self._thread = threading.Thread(target=self._serve, name="pressless-tray",
                                        daemon=True)
        self._thread.start()
        self._ready.wait(_START_WAIT)
        with self._lock:
            if not self._ready.is_set():
                self._abandoned = True
                raise TimeoutError("the tray's window did not start")
        if self._failure is not None:
            raise self._failure

    def close(self) -> None:
        """Delete the icon, then end the window and its thread. Without
        NIM_DELETE a stale icon stays until the pointer passes over it."""
        if self._hwnd:
            _api().PostMessageW(self._hwnd, _CLOSE_ICON, 0, 0)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def _serve(self) -> None:
        api = instance = hwnd = None
        try:
            api = _api()
            instance = api.GetModuleHandleW(None)
            self._icon = _load_icon()
            window_class = _WindowClass(cbSize=ctypes.sizeof(_WindowClass),
                                        lpfnWndProc=self._procedure, hInstance=instance,
                                        lpszClassName=self._class)
            if not api.RegisterClassExW(ctypes.byref(window_class)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._taskbar_created = api.RegisterWindowMessageW("TaskbarCreated")
            hwnd = api.CreateWindowExW(0, self._class, "Pressless", 0, 0, 0, 0, 0,
                                       None, None, instance, None)
            if not hwnd:
                error = ctypes.WinError(ctypes.get_last_error())
                api.UnregisterClassW(self._class, instance)
                raise error
            with self._lock:
                if self._abandoned:
                    raise TimeoutError("the tray's window started after start() gave up")
                self._hwnd = hwnd
                _notify(_NIM_ADD, self._data())
                self._ready.set()
        except BaseException as exc:  # noqa: BLE001 -- handed to start(), which raises it
            self._failure = exc
            self._hwnd = None
            if hwnd:
                api.DestroyWindow(hwnd)
                api.UnregisterClassW(self._class, instance)
            if self._icon:
                _api().DestroyIcon(self._icon)
            self._ready.set()
            return
        message = wintypes.MSG()
        while api.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            api.TranslateMessage(ctypes.byref(message))
            api.DispatchMessageW(ctypes.byref(message))
        api.UnregisterClassW(self._class, instance)
        api.DestroyIcon(self._icon)

    def _data(self) -> _NotifyIconData:
        return _NotifyIconData(cbSize=ctypes.sizeof(_NotifyIconData), hWnd=self._hwnd,
                               uID=_ICON_ID, uFlags=_NIF_MESSAGE | _NIF_ICON | _NIF_TIP,
                               uCallbackMessage=_CALLBACK, hIcon=self._icon,
                               szTip=self._tooltip)

    def _window_procedure(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        api = _api()
        if message == _CALLBACK:
            event = lparam & 0xFFFF
            if event == _WM_LBUTTONUP:
                self._run(self._entries[0][0])
            elif event == _WM_RBUTTONUP:
                self._menu(hwnd)
            return 0
        if self._taskbar_created and message == self._taskbar_created:
            _notify(_NIM_ADD, self._data())      # Explorer restarted
            return 0
        if message == _CLOSE_ICON:
            _notify(_NIM_DELETE, self._data())
            api.DestroyWindow(hwnd)
            return 0
        if message == _WM_CLOSE:
            return 0        # another program's: the icon goes only with Pressless
        if message == _WM_DESTROY:
            api.PostQuitMessage(0)
            return 0
        return api.DefWindowProcW(hwnd, message, wparam, lparam)

    def _menu(self, hwnd: int) -> None:
        """The three entries at the pointer. SetForegroundWindow first, so a
        click elsewhere closes the menu; WM_NULL after, so a second right
        click opens it again (Microsoft's documented pairing)."""
        api = _api()
        menu = api.CreatePopupMenu()
        try:
            for entry, label in self._entries:
                api.AppendMenuW(menu, 0, entry, label)
            point = wintypes.POINT()
            api.GetCursorPos(ctypes.byref(point))
            api.SetForegroundWindow(hwnd)
            chosen = api.TrackPopupMenu(menu, _TPM_RIGHTBUTTON | _TPM_NONOTIFY | _TPM_RETURNCMD,
                                        point.x, point.y, 0, hwnd, None)
            api.PostMessageW(hwnd, _WM_NULL, 0, 0)
        finally:
            api.DestroyMenu(menu)
        if chosen:
            self._run(chosen)
