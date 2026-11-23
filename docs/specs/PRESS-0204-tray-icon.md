<!-- ants-spec-format: 1 -->
# PRESS-0204 — A tray icon opens, restarts and stops Pressless

**Status:** accepted (2026-11-18).
**Kind:** implement.
**Source:** ROADMAP PRESS-0204 (user request 2026-10-02; placed after
1.0 by the user 2026-10-03).

**Changes:** PRESS-0011 § 4.5's link rule, and PRESS-0013 § 4.5's launch
steps (§ 11).
**Blocker for:** PRESS-0205.

Layman: a small Pressless icon by the clock opens Pressless's page again,
restarts it or stops it, even after the browser is closed.

## 1. Goal

While Pressless runs, an icon in the system tray (Windows' notification
area, a Linux desktop's status area) offers **Open Pressless**,
**Restart** and **Stop Pressless**. Open reaches the page even after the
browser was closed, which today needs a restart. Where a system has no
tray, Pressless runs exactly as it does now.

## 2. Problem

1. **The opening link works once.** `face.Face._follow_link` honours
   `?t=<secret>` once (`_link_spent`); after that only the session cookie
   admits, and the cookie has no expiry, so a browser that was closed
   has none. The 403 page says to start Pressless again
   (`face.link_spent`).
2. **The port is unknown to the writer.** `face.Face` binds port 0, so
   even a browser with the cookie has no address to go back to.
3. **The console is the only control.** Restart lives on the Settings
   page (`restarting.register`), which needs the page; stopping needs the
   console window (`__main__._stop_on_close`, `_watch_console`).

## 3. Scope decisions (agreed with the user)

- **Three entries: open, restart, stop.** The user, 2026-10-02.
- **Windows and Linux both**, Windows parity first. The user, 2026-10-02.
- **After 1.0.** The user, 2026-10-03.
- **No new library; Pressless's own code on both systems.** Mine,
  2026-11-18, under the user's standing instruction to act on my
  recommendation (§ 8 says why).
- **No confirm step on Restart or Stop.** Mine. A tray menu is already a
  deliberate two-click act, the stop is Ctrl+C's (safe during a publish,
  PRESS-0410), and a confirm needs a window toolkit Pressless does not
  have. Settings' Restart keeps its confirm page.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/tray.py — new. Every word lives in words.py (PRESS-0242).
class Tray:
    def __init__(self, stop: Callable[[], None]) -> None: ...
    def start(self) -> bool:            # False: no tray here, and nothing else changes
    def serve(self, face: Face, restart: Callable[[], None]) -> None:
        """The Face and restart the entries act on now; one call per Face.
        Notes go to `face.note`. `face.at_stop` makes the tray forget the Face."""
    def close(self) -> None:            # removes the icon; idempotent

# src/pressless/face.py — added
class Face:
    def fresh_link(self, path: str = "/") -> str:
        """A new one-use link to `path`; the previous link stops admitting."""
```

The system half lives in two private modules, chosen once at import:
`_tray_windows.py` where `sys.platform == "win32"`, else
`_tray_linux.py`. `tray.py` holds what both share: the three actions and
their words.

### 4.2 The actions

| Entry | What it does |
|---|---|
| Open Pressless (also a left click on the icon) | `webbrowser.open(face.fresh_link())`; where no browser opens, print the link, as launch does (PRESS-0013 § 4.5 step 5) |
| Restart | the `restart` callable `serve` was given: the same path as Settings' Restart after its confirm (PRESS-0203) |
| Stop Pressless | `stop`: `_thread.interrupt_main()`, Ctrl+C's way out (PRESS-0013 § 4.5 step 6). Once: a second Stop does nothing, as a second close signal does (PRESS-0208) |

An action runs on the tray's own thread and never raises into it: a
failure is noted by type in the log of the Face `serve` last named, and
the icon stays.

From a Face's stop steps until the next `serve`, the tray holds no Face:
Open and Restart do nothing, a failure is not noted, and Stop still
stops.

### 4.3 The link, re-armed (amends PRESS-0011 § 4.5)

`fresh_link` makes a new secret with `secrets.token_urlsafe(32)`, never
equal to the session, and under `_link_lock` replaces `_secret` and sets
`_link_spent` false. It returns `http://127.0.0.1:<port><path>?t=<secret>`,
and `url` becomes the new link at `/`, so it never names a dead one.

- The new link admits once, exactly as the launch link does.
- The previous link, spent or not, no longer admits.
- The session does not change, so tabs already open stay signed in.
- Only an in-process caller reaches it. No route serves a fresh link.

### 4.4 Launching (amends PRESS-0013 § 4.5)

`_serve_behind_lock` makes one `Tray` per process, after the move-in and
before the first Face, and closes it in its inner `finally`, the one
around `_serve_held`, after the last Face's stop steps. `_serve_once`
calls `tray.serve(served, restart.set)` once the pages are registered.
The first `serve` calls `start()`, so a tray that cannot start is noted
in that Face's log. A `start()` returning False changes nothing: the
console line and the console controls stay as they are. The console line
(`main.running`) is unchanged.

A Linux update replaces the process (PRESS-0408); the old tray goes with
the old process's bus connection and the new process makes its own.

### 4.5 Windows

`_tray_windows.py`, on `ctypes` alone, on a thread of its own:

- A hidden top-level window of a registered class: not a message-only
  window, because only a top-level window receives `TaskbarCreated`,
  which Explorer broadcasts when it restarts and which re-adds the icon.
- `Shell_NotifyIconW(NIM_ADD)` with the program's own icon (the one
  PyInstaller embeds in the `.exe`; a source run loads
  `packaging/icons/pressless.ico`), a tooltip, and a callback message.
- Left click: Open. Right click: a popup menu with the three entries,
  after `SetForegroundWindow`, so the menu closes on a click elsewhere.
- `close()` posts `WM_CLOSE`: `NIM_DELETE`, then the window and its
  thread end. Without `NIM_DELETE` a stale icon stays until the pointer
  passes over it.

### 4.6 Linux

`_tray_linux.py`, on `jeepney` (already shipped: `keyring` depends on it
through SecretStorage), on a thread of its own, with its own session-bus
connection:

- A **StatusNotifierItem** at `/StatusNotifierItem`, under the bus name
  `org.kde.StatusNotifierItem-<pid>-1`, registered with
  `org.kde.StatusNotifierWatcher`. `ItemIsMenu` false, so a left click
  sends `Activate`, which is Open.
  Source: https://specifications.freedesktop.org/status-notifier-item/0.1/status-notifier-item.html
- **Its menu** at `/MenuBar`, on `com.canonical.dbusmenu`: `GetLayout`,
  `GetGroupProperties`, `Event` (`clicked` runs the entry), `AboutToShow`.
  Source: https://docs.rs/crate/ksni/0.3.3/source/spec/DBusMenu.xml
- **The icon** as `IconPixmap`, ARGB32 in network byte order, made with
  Pillow from `$APPDIR/pressless.png` (`shortcuts._ICON`), or
  `packaging/icons/pressless.png` on a source run. No icon file is
  installed into a theme.
- **No watcher yet** (Plasma starting late, or restarted): watch
  `NameOwnerChanged` for `org.kde.StatusNotifierWatcher` and register when
  it appears. `start()` still returns True.
- The thread sleeps in `receive` until a message comes; `close()` shuts
  the socket to wake it, so it needs no second connection and no timed
  wake-ups. Closing the connection releases the name, and the watcher
  drops the item. A message the item cannot read is answered
  `InvalidArgs`, and the thread carries on.

Measured 2026-11-18 on Plasma 6 under Wayland, with `jeepney` 0.9.0 alone
and a throwaway probe: the watcher listed the item, and the tray called
`GetAll` on the item and `GetLayout(0, 1, [])` on the menu.

### 4.7 The trust boundary

The session bus admits only the writer's own processes, and any of them
can call the menu's `Event`. Open then makes a link that reaches the
browser on its command line, as the launch link already does. Neither
crosses a boundary the launch has not: a process running as the writer
can already read the keyring. The defences kept are PRESS-0011 § 4.5's:
the link is one-use, the cookie is never the secret, and the Face binds
only `127.0.0.1`.

### 4.8 What this item never does

- It never serves a fresh link over HTTP or D-Bus; it only opens one.
- It never stops a launch: a tray that cannot start is noted, not shown.
- It never writes a file for the tray: no icon into a theme, no autostart.

## 5. Invariants

- **INV-1** — `fresh_link` returns a link that admits once, and the link
  before it no longer admits, spent or not.
  *Test:* `tests/test_face.py`: follow the launch link, call
  `fresh_link`, and check the fresh link sets the cookie once and the old
  one gets 403 without the cookie; again with the launch link unspent.
  *Breaks when:* `fresh_link` re-arms `_link_spent` but keeps the old
  secret, or adds a second secret beside it.

- **INV-2** — `fresh_link` leaves the session alone: a cookie set before
  it still admits after.
  *Test:* `tests/test_face.py`, a page fetched with the earlier cookie
  after `fresh_link`.
  *Breaks when:* `fresh_link` also replaces `_session`.

- **INV-3** — Each entry runs its action on the Face `serve` last named:
  Open opens `fresh_link()`, Restart calls that `restart`, Stop calls
  `stop`, once however often it is chosen; once that Face stops, Open
  and Restart do nothing; and an action that raises is noted, not
  propagated.
  *Test:* `tests/test_tray.py`, driving the shared action table with a
  fake Face and recorders, the second `serve` replacing the first, and
  the fake Face's stop steps clearing it.
  *Breaks when:* the tray keeps the first Face it was given, so Open after
  a restart opens a dead port.

- **INV-4** — On Linux, the tray registers with a watcher, serves its
  menu, and a `clicked` event or an `Activate` runs the matching action.
  *Test:* `tests/test_tray_linux.py`, on a private `dbus-daemon` with a
  fake watcher written with `jeepney`: registration arrives, `GetLayout`
  lists the three entries, and `Event(id, "clicked")` and `Activate` each
  reach the recorder. It runs on Linux only. There it skips where
  `dbus-daemon` is absent, and fails instead where `CI` is set, so the
  Linux runner cannot skip it quietly.
  *Breaks when:* the menu's ids and the action table disagree.

- **INV-5** — On Windows, the callback message runs the action, and
  `close()` deletes the icon.
  *Test:* `tests/test_tray_windows.py`, on Windows only: post the
  callback message with `WM_LBUTTONUP` to the tray's window and see Open's
  recorder; after `close()`, the module's one `Shell_NotifyIconW` call
  site, wrapped by the test, saw `NIM_DELETE`, and the thread ended.
  *Breaks when:* `close()` ends the thread without `NIM_DELETE`.

- **INV-6** — A tray that cannot start changes nothing else: no session
  bus, no `Shell_NotifyIconW`, or a missing icon file leaves `start()`
  False, a note in the log, and the launch serving as before.
  *Test:* `tests/test_tray.py` and `tests/test_main.py`, with the system
  half replaced by one that fails.
  *Breaks when:* a tray failure escapes `_serve_behind_lock`.

- **INV-7** — A Linux bundle that cannot import `jeepney` fails its
  `--self-check`, rather than shipping with no tray.
  *Test:* `__main__` imports `tray`, which imports `_tray_linux` and
  `jeepney` at module level off Windows; `.github/workflows/release.yml`
  runs the built AppImage's `--self-check` in a clean room (PRESS-0022
  INV-7's step).
  *Breaks when:* `jeepney` is imported inside a function, or under
  `try/except ImportError`.

## 6. Failure modes

| What breaks | What happens |
|---|---|
| No session bus (SSH, a bare window manager) | `start()` False, noted; the console controls stay |
| A desktop with no watcher at all (GNOME without the AppIndicator extension) | registered when one appears, which may be never; nothing shows, nothing fails |
| Explorer restarts | `TaskbarCreated` re-adds the icon |
| The process is killed | Linux: the bus drops the name and the icon. Windows: a stale icon until the pointer passes over it (Windows' own behaviour) |
| Open while no browser opens | the link is printed to the console, as at launch |
| Open, Restart or Stop during a restart | Open and Restart do nothing until the next `serve`; Stop stops |
| Stop during a publish | Ctrl+C's stop: safe, PRESS-0410 |

## 7. Tests

INV-1 to INV-6 as § 5 names them, each seen to fail first against code
without the clause. INV-7 rests on the packaging check.

**By hand**, from a released build, once per system: the icon shows;
close the browser, then Open reaches the page; Restart carries on in an
open tab, and opens a fresh one only where none is open (PRESS-0428);
Stop ends the process and the icon goes. On Linux, under Plasma (the
maintainer's desktop); on Windows, on the box (`docs/working-here.md`
§ Windows and browser checks).

## 8. Alternatives considered (and rejected)

- **`pystray`.** Its Linux tray needs PyGObject, which has no wheel and
  must be built and bundled, or falls back to an X11 backend that does not
  work under Wayland. Its last release was 2023. Windows would gain
  nothing over `ctypes`.
  Source: https://pystray.readthedocs.io/en/latest/faq.html
- **Opening `/` without a link**, relying on the cookie. A closed browser
  has no cookie, so Open would land on the 403 page — the case the item
  exists for.
- **A `file://` page that forwards to the link**, to keep the secret off
  the command line. It would protect the tray but not the launch, which
  sends the same kind of link; changing both is its own item, and the
  launch's exposure was accepted in PRESS-0011.
- **A message-only window on Windows.** It cannot receive `TaskbarCreated`,
  so the icon would vanish for good when Explorer restarts.

## 9. Out of scope

- Hiding the icon when the local web-server manager runs Pressless —
  tracked by PRESS-0205.
- Notifications from the tray (a finished publish, say) — deferred; not
  yet queued.
- A tray on macOS — Pressless ships no macOS build.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_face.py` |
| INV-2 | `tests/test_face.py` |
| INV-3 | `tests/test_tray.py` |
| INV-4 | `tests/test_tray_linux.py`, on the Linux runner |
| INV-5 | `tests/test_tray_windows.py`, on the Windows runner and the box |
| INV-6 | `tests/test_tray.py`, `tests/test_main.py` |
| INV-7 | `.github/workflows/release.yml`'s clean-room `--self-check` on the built AppImage |
| § 4.7 trust boundary | Partial: INV-1 and PRESS-0011's tests; nothing checks that no route serves a fresh link |
| The icon is seen and a click works on a real desktop | **nothing** automatic — § 7's by-hand check |

## 11. Cross-doc impact

- **PRESS-0011 § 4.5**: the link is one-use per link, and `fresh_link`
  re-arms it (§ 4.3).
- **PRESS-0013 § 4.5**: the tray's start, `serve` and close (§ 4.4).
- **`docs/design.md` § The stack, and what it rules out**: the tray,
  on `ctypes` and `jeepney`.
- **`pyproject.toml`**: `jeepney` declared on Linux, since Pressless now
  imports it itself.
- **`CLAUDE.md` § Build and test**: `jeepney` reached only by
  `_tray_linux.py`, and `Pillow` by `_tray_linux.py` as well as
  `builder.py`.
- **The in-app manual and README**: the icon and its three entries.
- **CHANGELOG**: the tray icon.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0204-tray-icon-loop-log.md`.

## 13. Resource cost

One thread and one hidden window on Windows; one thread and one
session-bus connection on Linux. No new dependency: `jeepney` already
ships in the Linux build, and Windows uses `ctypes`. Pillow makes two
small pixmaps once per process.
