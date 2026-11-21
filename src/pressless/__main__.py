"""The program that gets packaged — PRESS-0022 § 4.5 and PRESS-0013 § 4.5.

`--assistant` is the AI helper's bridge (PRESS-0337 § 4.4): it prints no
report, since its stdout belongs to the protocol. The other two routes print
the same report first, one machine-readable line each. The
report's shape is a contract: the release job reads the exit code and
tests/features/packaging/ parses the lines.

    pressless: ok
    folder: <the folder, relative to the artefact's own folder>
    store: <keyring|file> <member name>

`--self-check` stops there. The double-click then serves the Face, with setup,
the editor, publishing, undo and the page editor on it, opens his browser,
and runs until the console window is closed or the tray icon's Stop is
chosen. Restart in Settings or the tray serves a fresh Face in the same
window (PRESS-0203, PRESS-0204). Every part is imported here at
module level, so a packaged `--self-check` proves each one loads in the bundle.
"""
from __future__ import annotations

import _thread
import ctypes
import errno
import os
import signal
import sys
import threading
import urllib.parse
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from pressless import (
    about,
    assistant,
    backups,
    bridge,
    cheatsheet,
    credentials,
    dashboard,
    domain,
    editor,
    face,
    files_screen,
    github_setup,
    google_setup,
    importing,
    installer,
    jpegxl_screen,
    languages,
    look_screen,
    manual,
    os_reason,
    overview,
    page_editor,
    paths,
    pressing,
    publishing,
    report,
    restarting,
    sendlog,
    settings,
    setup,
    shortcuts,
    sites,
    sites_screen,
    templates,
    tray,
    undo,
    updating,
    usage,
    votes_setup,
    words,
    youtube_screen,
)
from pressless.words import say

_USAGE = "usage: pressless [--self-check | --assistant]"
_LOCK_NAME = "pressless.lock"


def main(argv: list[str]) -> int:
    """Print the report, then serve unless this is --self-check.

    `--self-check` is non-zero only where a report question could not be
    answered at all -- NotPackaged, FolderUnusable, or choose() raising. A
    double-click also returns 1 where moving in, an Import's moves or the
    launch failed, or an updated version could not be opened, 3 where another
    Pressless holds the folder, and 130 for an interrupt before the Face was
    waiting. An unknown argument exits 2, and `--assistant` returns the
    bridge's own code. A source run's `--assistant` takes the folder its Face
    uses (PRESS-0337 § 4.4); a packaged one finds its own, so a settings file
    cannot send its calls to another door. `store: file` is not a failure: this
    program cannot tell a machine with no store from a bundle that lost its
    metadata, and PRESS-0022 § 7 decides which by controlling the machine.
    """
    told_folder = (len(argv) == 2 and argv[0] == "--assistant"
                   and not getattr(sys, "frozen", False))
    if argv not in ([], ["--self-check"], ["--assistant"]) and not told_folder:
        print(_USAGE, file=sys.stderr)
        raise SystemExit(2)
    if argv[:1] == ["--assistant"]:
        # PRESS-0337 § 4.4: before the report, since stdout is the protocol's.
        return bridge.main(Path(argv[1]) if told_folder else None)

    _unbundle_environment()
    print("pressless: ok")
    try:
        own = paths.ensure(paths.own_folder())
        # Relative, so the report names no full path (docs/design.md
        # § Logging): a correct build prints Pressless-data, and anything else
        # is the misplacement PRESS-0022 INV-2 names.
        print(f"folder: {os.path.relpath(own, paths.artefact_path().parent)}")
    except (paths.NotPackaged, paths.FolderUnusable) as exc:
        print(f"folder: unanswered -- {exc}")
        return 1
    # PRESS-0241 § 4.3: before the Face, the tray or a translated line.
    words.choose(languages.for_screens(own)[0])

    try:
        choice = credentials.choose()
    except (credentials.NoStore, credentials.CredentialError) as exc:
        print(f"store: unanswered -- {type(exc).__name__}")
        return 1
    print(f"store: {choice.store} {choice.name}")

    if argv == ["--self-check"]:
        return 0
    try:
        return _serve(own)
    except KeyboardInterrupt:
        # Ctrl+C, or a closed terminal (_stop_on_close), before the Face was
        # waiting: he asked it to stop, so no words, and no traceback.
        return 130
    except Exception as exc:  # noqa: BLE001 -- the last resort at launch
        # A traceback names full paths, which the console must not carry
        # (PRESS-0011 § 4.5's rule, reached before handle_error exists).
        print(say("main.could_not_start", kind=type(exc).__name__))
        return 1


def _unbundle_environment() -> None:
    """Give every program Pressless starts the loader paths from before the
    bundle (PRESS-0146).

    PyInstaller points LD_LIBRARY_PATH at the bundle, keeping any earlier value
    as LD_LIBRARY_PATH_ORIG. A /bin/sh that is bash then loads the bundle's
    libreadline and dies, and the browser launchers are sh scripts. The loader
    read the variable when this process started, so changing it here moves
    only what children see.
    """
    if not getattr(sys, "frozen", False) or sys.platform == "win32":
        return
    installer.restore_loader_paths(os.environ)


def _lock_now(handle: BinaryIO) -> None:
    """Lock `handle` exclusively without waiting, or raise OSError.

    Chosen by which call the running system provides, never by sys.platform:
    tests set that to exercise another system's paths, and the lock must
    still be this system's (the Windows runner has no fcntl).
    """
    try:
        import fcntl
    except ImportError:  # Windows
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _hold(own: Path) -> BinaryIO | None:
    """The lock on Pressless's own folder, held for the life of the process
    (PRESS-0023 § 4.11), or None where another Pressless holds it. Never
    waits."""
    handle = open(own / _LOCK_NAME, "a+b")  # noqa: SIM115 -- open while held
    try:
        _lock_now(handle)
    except OSError as exc:
        handle.close()
        # Only a lock someone else holds is "already running". Any other
        # refusal -- a file system with no locking, say -- is a failure, or
        # every launch there would say another copy runs (PRESS-0162).
        if exc.errno in _HELD:
            return None
        raise
    return handle


# How each system refuses a lock another process holds: flock answers
# EWOULDBLOCK (EAGAIN), and msvcrt's non-blocking lock EACCES or EDEADLOCK.
_HELD = frozenset({errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES, errno.EDEADLK})


def _serve(own: Path) -> int:
    """Serve behind the folder's lock until stopped. Where a Linux Update now
    put a new version in place, it then replaces this process (PRESS-0408),
    once the stop steps have run and the lock is let go."""
    updates = updating.Updates()
    code = _serve_behind_lock(own, updates)
    if updates.installed is None:
        return code
    program, version = updates.installed
    print(say("restarting.going.title"), flush=True)
    installer.reopen_linux(program, own)   # returns only where it could not
    print(say("updating.not_reopened", version=version))
    return 1


def _serve_behind_lock(own: Path, updates: updating.Updates) -> int:
    """PRESS-0013 § 4.5 steps 3 to 6, behind the folder's lock."""
    held = _hold(own)
    if held is None:
        print(say("main.already"))
        return 3
    try:
        # PRESS-0223 § 4.3: behind the lock, so no second Pressless moves it.
        failed = sites.move_in(own)
        stopped = None if failed is None else say(
            "main.moving_in", folder=own.name,
            reason=os_reason.of(failed))
        # PRESS-0125 § 4.7: an Import stopped part way through its moves
        # finishes before anything reads that site.
        for site in sites.all_sites(own):
            finished = importing.finish_moves(site)    # every site, though one stops
            stopped = stopped or finished
        backups.clear_leftovers(own)   # PRESS-0383: what a stopped save or open left
        if stopped is not None:
            print(stopped)
            return 1
        kept = _stop_on_close()
        stopped = threading.Event()
        unwatch = _watch_console(stopped)
        # PRESS-0204 § 4.4: one per process. Its Stop is Ctrl+C's way out.
        icon = tray.Tray(_thread.interrupt_main)
        try:
            return _serve_held(own, updates, icon)
        finally:
            icon.close()    # after the last Face's stop steps
            stopped.set()   # the stop steps have run: a closing console may end us
            unwatch()
            for number, handler in kept.items():
                signal.signal(number, handler)
    finally:
        held.close()


_CLOSE_SIGNALS = tuple(getattr(signal, name) for name in ("SIGTERM", "SIGHUP")
                       if hasattr(signal, name))


def _stop_on_close() -> dict[int, object]:
    """A closed terminal (SIGHUP) or a stop from the system (SIGTERM) takes
    Ctrl+C's way out, so the Face's stop steps run and the AI helper's door
    file goes with it (PRESS-0337 § 4.2). A handler another program set
    stays. Returns the handlers to put back."""
    if threading.current_thread() is not threading.main_thread():
        return {}
    return {number: signal.signal(number, _interrupt) for number in _CLOSE_SIGNALS
            if signal.getsignal(number) == signal.SIG_DFL}


def _interrupt(number: int, frame: object) -> None:
    # A second signal while stopping must not cut the stop short (PRESS-0208).
    for each in _CLOSE_SIGNALS:
        signal.signal(each, signal.SIG_IGN)
    raise KeyboardInterrupt


# The console events that end the process once their handler returns
# (PRESS-0407): CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT and CTRL_SHUTDOWN_EVENT.
_CLOSE_EVENTS = frozenset({2, 5, 6})
# Windows ends the process itself a few seconds after a close; this bound only
# frees the handler's thread where the stop never finishes.
_CLOSE_WAIT = 30.0
# Every handler given to Windows, kept for the life of the process: Windows
# may still be running one after it is removed.
_ROUTINES: list[object] = []


def _watch_console(stopped: threading.Event) -> Callable[[], None]:
    """Windows' closed console (PRESS-0407). It sends no SIGHUP: it calls a
    console handler on a thread of its own and ends the process once that
    returns. So the handler takes Ctrl+C's way out, as _interrupt does, and
    returns only once `stopped` is set, after the stop steps. Ctrl+C itself
    is left to Python. Returns the handler's removal."""
    closing = threading.Event()

    def on_event(kind: int) -> bool:
        if kind not in _CLOSE_EVENTS:
            return False
        if not closing.is_set():   # a second event must not cut the stop short
            closing.set()
            _thread.interrupt_main()
        stopped.wait(_CLOSE_WAIT)
        return True

    return _console_handler(on_event)


def _console_handler(on_event: Callable[[int], bool]) -> Callable[[], None]:
    """Give `on_event` to Windows as a console handler; return its removal.
    Chosen by whether the system has the call, never by sys.platform, as
    _lock_now is. Elsewhere it does nothing."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return lambda: None
    routine = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)(on_event)
    _ROUTINES.append(routine)
    windll.kernel32.SetConsoleCtrlHandler(routine, True)
    return lambda: windll.kernel32.SetConsoleCtrlHandler(routine, False)


def _serve_held(own: Path, updates: updating.Updates, icon: tray.Tray) -> int:
    # `updates` and `icon` are one per process: a restart keeps the update
    # offer and a Later, and does not check again (PRESS-0023 § 4.9), and
    # keeps the one tray icon (PRESS-0204 § 4.4).
    while _serve_once(own, updates, icon):
        print(say("restarting.going.title"))
    return 0


def _serve_once(own: Path, updates: updating.Updates, icon: tray.Tray) -> bool:
    """One Face, from start to stop. True where he asked for a restart
    (PRESS-0203): the caller then serves a new one, behind the same lock.
    Each pass opens the site sites.json names now, so opening another site is
    a restart (PRESS-0223 § 4.4): the machine's parts take Pressless's own
    folder, and the site's take the site's."""
    restart = threading.Event()
    stopping = threading.Event()
    again = False
    folder = sites.open_site(own)
    served = face.serve(own, site=folder)
    try:
        setup.register(served, folder, own=own)
        github_setup.register(served, folder)
        google_setup.register(served, folder)
        votes_setup.register(served, folder)
        youtube_screen.register(served, folder)
        domain.register(served, folder)
        dashboard.register(served, folder)
        editor.register(served, folder)
        overview.register(served, folder)                   # PRESS-0353
        cheatsheet.register(served)
        manual.register(served)                             # PRESS-0219
        report.register(served)
        sendlog.register(served, own)                       # PRESS-0436
        about.register(served)
        usage.register(served, own, site=folder)
        templates.register(served, folder)
        publishing.register(served, folder)
        undo.register(served, folder)
        page_editor.register(served, folder)
        look_screen.register(served, folder)
        files_screen.register(served, folder)
        pressing.register(served)
        updating.register(served, own, state=updates, stop=restart.set)
        jpegxl_screen.register(served, own)
        restarting.register(served, restart.set)
        sites_screen.register(served, own, restart.set)
        importing.register(served, folder)
        assistant.register(served, folder, own=own)         # PRESS-0337
        _refresh_shortcuts(served)
        icon.serve(served, restart.set)                     # PRESS-0204

        first = "/"
        with served.capture():
            moved = setup.carry_name_across(folder)          # PRESS-0213 § 4.3
            if moved is not None:
                print(moved)
            setup.follow_the_folder(folder)
            try:
                settings.load(folder)
            except settings.NotSetUp:
                first = "/setup"
            except settings.SettingsError as exc:
                # A file carried from another machine is first run (PRESS-0021 § 4.8).
                if exc.key == "site_folder":
                    first = "/setup"

        link = urllib.parse.urlunsplit(
            urllib.parse.urlsplit(served.url)._replace(path=first))
        try:
            opened = webbrowser.open(link)
        except Exception:  # noqa: BLE001 -- no browser is a case, not a failure
            opened = False
        if not opened:
            print(say("main.open_link", link=link))
        print(say("main.running"))
        # PRESS-0225: today's backups, then a look every hour, behind this Face.
        backups.start(own, stopping, served.note)
        try:
            # An update stops the Face as a restart does, but serves no new
            # one: _serve opens the new version in this process's place.
            again = _wait(restart) and updates.installed is None
        except KeyboardInterrupt:
            updates.installed = None   # he asked it to stop: it stays stopped
    finally:
        stopping.set()
        if again:
            # A save, publish or undo under way ends before its Face does,
            # since the next Face serves the same files. A plain stop does
            # not wait (PRESS-0013 § 4.5 step 6): the process ends with it.
            # A stop arriving during that wait is a plain stop (PRESS-0427).
            stopped = False
            try:
                with editor.LOCK:
                    served.stop()
                    stopped = True
            except KeyboardInterrupt:
                if not stopped:
                    served.stop()
                raise
        else:
            served.stop()
    return again


def _refresh_shortcuts(served: face.Face) -> None:
    """Point a shortcut he kept at where the program is now (PRESS-0183).
    Best effort: a launch never stops over a shortcut. A shortcut that is
    already right costs one read, so only a launch after a move waits."""
    try:
        where = shortcuts.places()
        if where is not None:
            shortcuts.refresh(where)
    except (shortcuts.ShortcutError, OSError) as exc:
        served.note(f"a shortcut could not be refreshed: {type(exc).__name__}")


def _wait(restart: threading.Event) -> bool:
    """Block until `restart` is set, then return True. An interrupt raises,
    a closed terminal or console included (_stop_on_close, _watch_console),
    so it never returns False. It waits in short spells because on Windows
    one long wait takes no interrupt until it ends (PRESS-0407, measured on
    the box). Its own function so the tests can replace it (PRESS-0013 § 4.5
    step 6)."""
    while not restart.wait(0.25):
        pass
    return True


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
