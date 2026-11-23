# PRESS-0022 § 4.5: the program that gets packaged, and its report.
#
# The report's shape is a contract -- § 7's release job and
# tests/features/packaging/ parse it, and the job reads its exit code -- so it
# is pinned here against the same patched resolution tests/test_paths.py uses,
# without a build. INV-6 itself needs a built artefact and lives with the
# packaging tests.
from __future__ import annotations

import errno
import http.client
import os
import signal
import socket
import sys
import threading
import urllib.parse
import webbrowser

import pytest
from _face_session import session_cookie
from conftest import QuietIcon
from test_paths import _artefact, _frozen_linux

import pressless.__main__ as main_module
from pressless import settings
from pressless.credentials import Choice

# The report's three line keys and the folder's name, written out rather than
# imported, so the test holds its own copy of the contract.
_FOLDER_NAME = "Pressless-data"


def _store(monkeypatch, choice):
    """Answer credentials.choose() with `choice`, or raise it if it is an
    exception -- the packaged program must not touch the real keyring here."""
    def choose():
        if isinstance(choice, Exception):
            raise choice
        return choice
    monkeypatch.setattr(main_module.credentials, "choose", choose)


def test_self_check_reports_three_lines(monkeypatch, tmp_path, capsys):
    """A packaged run answers all three questions and exits 0.

    `folder:` is relative to the artefact's own folder, so a correct build
    prints Pressless-data and the report names no full path (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    assert main_module.main(["--self-check"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == [
        "pressless: ok",
        f"folder: {_FOLDER_NAME}",
        "store: keyring SecretService",
    ], out
    assert str(tmp_path) not in out, f"the report names a full path: {out!r}"


class _Opened:
    """Replaces the serving half of a double-click (PRESS-0013 § 4.5): the real
    Face runs, the browser is a recorder, and the wait returns at once."""

    def __init__(self, monkeypatch):
        self.faces = []
        self.links = []
        # A port named in the shell running the suite would pin every launch.
        monkeypatch.delenv("PRESSLESS_PORT", raising=False)
        real_serve = main_module.face.serve

        def serve(folder, **kwargs):
            served = real_serve(folder, **kwargs)
            self.faces.append(served)
            return served

        monkeypatch.setattr(main_module.face, "serve", serve)
        monkeypatch.setattr(webbrowser, "open",
                            lambda url: self.links.append(url) or True)
        monkeypatch.setattr(main_module, "_wait", lambda restart: False)
        # PRESS-0183: the launch refreshes his shortcuts. Recorded, never run,
        # so no test reaches the shortcuts in the real home folder.
        self.refreshed = []
        monkeypatch.setattr(main_module, "_refresh_shortcuts", self.refreshed.append)
        # A frozen run starts the update check (PRESS-0023 § 4.4); no test
        # reaches the network, so it answers "off" without asking.
        self.checks: list[tuple] = []
        monkeypatch.setattr(main_module.updating.updater, "check",
                            lambda *args: self.checks.append(args)
                            or main_module.updating.updater.Miss(1))


def test_the_double_click_takes_the_same_path(monkeypatch, tmp_path, capsys):
    """No flag at all is the writer's double-click, and it prints the same
    report -- so the route that was tested is the writer's route (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    _Opened(monkeypatch)

    assert main_module.main([]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "pressless: ok"


def test_the_double_click_opens_pressless(monkeypatch, tmp_path, capsys):
    """PRESS-0013 INV-8: the double-click serves setup, the editor and
    publishing, and opens /setup until setup is done; --self-check serves
    nothing."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    opened = _Opened(monkeypatch)

    assert main_module.main(["--self-check"]) == 0
    assert opened.faces == [] and opened.links == []

    assert main_module.main([]) == 0
    assert capsys.readouterr().out.splitlines()[:3] == [
        "pressless: ok", f"folder: {_FOLDER_NAME}", "store: keyring SecretService"]
    pages = set(opened.faces[0]._pages)
    for route in (("GET", "/setup"), ("GET", "/"), ("POST", "/save"), ("POST", "/publish"),
                  ("POST", "/undo"), ("GET", "/page"), ("POST", "/page/save"),
                  ("POST", "/page/discard"), ("POST", "/page/publish"),
                  ("POST", "/page/new"), ("POST", "/page/remove"), ("POST", "/page/rename"),
                  ("POST", "/update"), ("POST", "/update/checking")):
        assert route in pages, route
    assert urllib.parse.urlsplit(opened.links[0]).path == "/setup"

    # PRESS-0223: a site's settings are in its own folder; the first is site-1.
    folder = artefact.parent / _FOLDER_NAME / "sites" / "site-1"
    settings.save(folder, settings.Settings(
        site_folder=folder / "site", repository="owner/owner.github.io",
        site_address="https://example.org",
        daily_prompt_filter="", untouchable=(),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))
    assert main_module.main([]) == 0
    assert urllib.parse.urlsplit(opened.links[1]).path == "/"


def test_restart_serves_a_fresh_face(monkeypatch, tmp_path, capsys):
    """PRESS-0203: a restart stops the Face, serves a new one with a new link
    behind the same lock, and opens it; closing the window still ends it."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    opened = _Opened(monkeypatch)
    answers = iter([True, False])
    monkeypatch.setattr(main_module, "_wait", lambda restart: next(answers))

    assert main_module.main([]) == 0
    assert len(opened.faces) == 2 and len(opened.links) == 2
    assert opened.links[0] != opened.links[1]
    assert ("POST", "/restart") in opened.faces[1]._pages
    assert "Pressless is restarting." in capsys.readouterr().out
    assert not opened.faces[0]._thread.is_alive(), "the first Face was not stopped"
    assert main_module.editor.LOCK.acquire(blocking=False), "the restart kept the lock"
    main_module.editor.LOCK.release()


def test_the_tray_follows_each_face_and_closes_last(monkeypatch, tmp_path, capsys):
    """PRESS-0204 § 4.4: one tray per process, served each Face in turn with
    that Face's restart, and closed once the last Face has stopped.

    Breaks when _serve_once stops serving the tray, so its Open after a
    restart reaches a closed port."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    opened = _Opened(monkeypatch)
    monkeypatch.setattr(main_module, "_wait", lambda restart: next(answers))
    answers = iter([True, False])
    served = []
    real_serve = main_module.tray.Tray.serve

    def serve(self, face, restart):
        served.append((self, face))
        return real_serve(self, face, restart)

    monkeypatch.setattr(main_module.tray.Tray, "serve", serve)
    assert main_module.main([]) == 0
    assert [face for _, face in served] == opened.faces and len(served) == 2
    assert served[0][0] is served[1][0], "a restart made a second tray"
    assert len(QuietIcon.made) == 1 and QuietIcon.made[0].closed


class _NoTray(QuietIcon):
    def start(self):
        raise OSError("no session bus")


def test_a_tray_that_cannot_start_leaves_the_launch_as_it_was(monkeypatch, tmp_path, capsys):
    """PRESS-0204 INV-6: no tray here is a note in the log; the browser
    opens, the console line is printed and the launch ends as before.

    Breaks when a tray failure escapes _serve_behind_lock."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    opened = _Opened(monkeypatch)
    monkeypatch.setattr(main_module.tray, "_Icon", _NoTray)

    assert main_module.main([]) == 0
    assert len(opened.links) == 1
    assert main_module.say("main.running") in capsys.readouterr().out
    log = (artefact.parent / _FOLDER_NAME / "pressless.log").read_text(encoding="utf-8")
    assert "the tray icon could not start: OSError" in log


class _InterruptedOnEntry:
    """editor.LOCK as a restart meets it when a stop arrives during its wait:
    _thread.interrupt_main()'s KeyboardInterrupt lands once the lock is
    taken, before the block runs (measured, PRESS-0427)."""

    def __enter__(self):
        raise KeyboardInterrupt

    def __exit__(self, *exc):
        return False


def test_a_stop_while_a_restart_waits_still_stops_the_face(monkeypatch, tmp_path, capsys):
    """PRESS-0427: a stop that arrives while a restart waits for a save still
    runs the old Face's stop steps, as a plain stop does (PRESS-0013 § 4.5
    step 6), and the process stops rather than serving a new Face.

    Breaks when the interrupt leaves _serve_once before served.stop()."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    opened = _Opened(monkeypatch)
    monkeypatch.setattr(main_module, "_wait", lambda restart: True)
    monkeypatch.setattr(main_module.editor, "LOCK", _InterruptedOnEntry())
    ran = []
    real_register = main_module.restarting.register

    def register(served, restart):
        served.at_stop(lambda: ran.append("stop steps"))
        return real_register(served, restart)

    monkeypatch.setattr(main_module.restarting, "register", register)

    assert main_module.main([]) == 130
    assert len(opened.faces) == 1, "a new Face was served after the stop"
    assert ran == ["stop steps"], "the old Face's stop steps did not run"
    assert not opened.faces[0]._thread.is_alive(), "the old Face was not stopped"


def test_a_restart_keeps_what_the_update_check_found(monkeypatch, tmp_path, capsys):
    """PRESS-0023 § 4.9: the update offer and a Later last for the life of
    the process, and a restart is the same process.

    Breaks when each pass registers updating against its own state."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    _Opened(monkeypatch)
    answers = iter([True, False])
    monkeypatch.setattr(main_module, "_wait", lambda restart: next(answers))
    handed = []

    def register(served, own, **kwargs):
        handed.append(kwargs.get("state"))
        return kwargs.get("state")

    monkeypatch.setattr(main_module.updating, "register", register)
    assert main_module.main([]) == 0
    assert len(handed) == 2 and handed[0] is not None and handed[0] is handed[1], handed


def test_an_interrupt_while_starting_prints_no_traceback(monkeypatch, tmp_path, capsys):
    """review-code 2026-11-16 lane 11: a Ctrl+C, or a closed terminal, before
    the Face waits escaped main's `except Exception`, and Python printed a
    traceback naming full paths. It now ends quietly with 130.

    Breaks when KeyboardInterrupt leaves main."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    def interrupted(own):
        raise KeyboardInterrupt

    monkeypatch.setattr(main_module.sites, "move_in", interrupted)
    try:
        code = main_module.main([])
    except KeyboardInterrupt:
        pytest.fail("the interrupt left main, so Python printed its traceback")
    assert code == 130
    assert "Traceback" not in "".join(capsys.readouterr())


def test_an_unanswerable_question_exits_non_zero(monkeypatch, tmp_path, capsys):
    """NotPackaged is one of the three reasons to exit non-zero, and the
    report still names no path -- a stale $APPIMAGE value is one."""
    gone = _artefact(tmp_path)
    gone.unlink()
    _frozen_linux(monkeypatch, tmp_path, appimage=gone)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    assert main_module.main(["--self-check"]) != 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "pressless: ok", "it did not say it started"
    assert str(tmp_path) not in out, f"the report names a full path: {out!r}"


def test_a_file_store_is_not_a_failure(monkeypatch, tmp_path, capsys):
    """`store: file` exits 0: this program cannot tell a machine with no store
    from a bundle that lost its metadata, so § 7 decides which by controlling
    the machine (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("file", "file"))

    assert main_module.main(["--self-check"]) == 0
    assert capsys.readouterr().out.splitlines()[2] == "store: file file"


def test_a_store_that_raises_exits_non_zero(monkeypatch, tmp_path, capsys):
    """choose() raising is the third reason to exit non-zero (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, main_module.credentials.CredentialError("no store"))

    assert main_module.main(["--self-check"]) != 0


def test_no_store_is_a_report_line_not_a_traceback(monkeypatch, tmp_path, capsys):
    """choose() raises NoStore on Windows with no store (PRESS-0002 § 4.2).
    main reports it as it reports CredentialError: the type alone, non-zero,
    and never an escaping exception, whose traceback prints full paths
    (PRESS-0257)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, main_module.credentials.NoStore(str(tmp_path)))

    assert main_module.main(["--self-check"]) != 0
    out = capsys.readouterr().out
    assert out.splitlines()[2] == "store: unanswered -- NoStore", out
    assert str(tmp_path) not in out, f"the report names a full path: {out!r}"


def test_it_writes_nothing_but_the_folder(monkeypatch, tmp_path, capsys):
    """Beside the artefact there is the artefact and the empty folder, and
    nothing else (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    main_module.main(["--self-check"])
    assert sorted(p.name for p in artefact.parent.iterdir()) == sorted(
        [artefact.name, _FOLDER_NAME]
    )
    assert list((artefact.parent / _FOLDER_NAME).iterdir()) == []


def test_programs_it_starts_do_not_load_the_bundle(monkeypatch, tmp_path, capsys):
    """PRESS-0146: PyInstaller points LD_LIBRARY_PATH at the bundle, and a
    /bin/sh that is bash then loads the bundle's libreadline and dies -- the
    browser launcher and xdg-open among it. A frozen Linux run hands its
    children the value from before the bundle: the _ORIG copy, or nothing."""
    artefact = _artefact(tmp_path)
    bundle = str(tmp_path / "mount" / "_internal")
    for orig in ("/usr/lib/before", None):
        _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
        _store(monkeypatch, Choice("keyring", "SecretService"))
        for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            monkeypatch.setenv(name, bundle)
            if orig is None:
                monkeypatch.delenv(f"{name}_ORIG", raising=False)
            else:
                monkeypatch.setenv(f"{name}_ORIG", orig)

        assert main_module.main(["--self-check"]) == 0
        for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            assert main_module.os.environ.get(name) == orig, (name, orig)


_ALREADY = ("Pressless is already running. Use the browser tab it opened, or close its "
            "window and start it again.")


def _try_lock(path) -> object | None:
    """Take the folder's lock the way a second Pressless would: its own open
    file, exclusive and non-blocking. The handle, or None where it is held."""
    handle = open(path, "a+b")  # noqa: SIM115 -- held open while the lock is
    try:
        # The running system's call, as _hold chooses it: sys.platform may be
        # a test's pretence here too.
        try:
            import fcntl
        except ImportError:  # Windows
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def test_one_pressless_per_folder(monkeypatch, tmp_path, capsys):
    """PRESS-0023 INV-16. Breaks when the lock is not taken, is taken
    blocking, or is released before the process ends; or --self-check takes
    it."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    opened = _Opened(monkeypatch)
    folder = artefact.parent / _FOLDER_NAME
    folder.mkdir()
    lock = folder / "pressless.lock"

    other = _try_lock(lock)
    assert other is not None
    try:
        answered: list[int] = []
        second = threading.Thread(target=lambda: answered.append(main_module.main([])))
        second.start()
        second.join(5)
        assert answered == [3], "a second start served, or waited on the lock"
        assert _ALREADY in capsys.readouterr().out
        assert opened.faces == []
        assert main_module.main(["--self-check"]) == 0
    finally:
        other.close()

    held_while_serving: list[bool] = []

    def serving(restart: threading.Event) -> bool:
        handle = _try_lock(lock)
        held_while_serving.append(handle is None)
        if handle is not None:
            handle.close()
        return False

    monkeypatch.setattr(main_module, "_wait", serving)
    assert main_module.main([]) == 0
    assert held_while_serving == [True], "the lock was not held while serving"


def test_there_is_no_other_flag(monkeypatch, tmp_path, capsys):
    """Only the double-click and --self-check exist (§ 4.5); anything else is
    refused rather than read as one of them."""
    with pytest.raises(SystemExit) as caught:
        main_module.main(["--something-else"])
    assert caught.value.code != 0


@pytest.mark.parametrize("pretend", ["win32", "linux"])
def test_the_folder_lock_is_this_systems_whatever_platform_a_test_pretends(
        monkeypatch, tmp_path, pretend):
    """The lock is taken with the call the RUNNING system provides. Tests set
    sys.platform to exercise another system's paths (test_paths'
    _frozen_linux), and a lock chosen from it imported fcntl on the Windows
    runner, which has none -- three tests red there and on no Linux machine.

    Breaks when _hold branches on sys.platform again."""
    monkeypatch.setattr(sys, "platform", pretend)
    held = main_module._hold(tmp_path)
    assert held is not None, "the lock was refused in an empty folder"
    held.close()


def test_only_a_held_lock_reads_as_already_running(monkeypatch, tmp_path):
    """PRESS-0162 (review-code L5.2): every OSError from the lock read as
    "already running", so a file system that refuses locking would say so on
    every launch. Only a held lock does; anything else is raised."""
    def held(handle):
        raise BlockingIOError(errno.EWOULDBLOCK, "held")

    def unsupported(handle):
        raise OSError(errno.ENOLCK, "no locks here")

    monkeypatch.setattr(main_module, "_lock_now", held)
    assert main_module._hold(tmp_path) is None
    monkeypatch.setattr(main_module, "_lock_now", unsupported)
    with pytest.raises(OSError):
        main_module._hold(tmp_path)


def test_a_failure_at_launch_names_no_path(monkeypatch, tmp_path, capsys):
    """PRESS-0162 (review-code L5.3): a failure while starting printed a
    standard traceback naming full paths -- the console leak PRESS-0011
    § 4.5 closes for requests. It now prints one sentence and its type."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    secret = str(tmp_path / "a-private-path")

    def broken(folder, port=0, *, resume=None):
        raise RuntimeError(secret)

    monkeypatch.setattr(main_module, "_serve", broken)
    assert main_module.main([]) == 1
    out, err = capsys.readouterr()
    assert "RuntimeError" in out
    assert secret not in out + err and "Traceback" not in out + err


@pytest.mark.parametrize("text, port", [(None, 0), ("", 0), (" ", 0),
                                        ("1", 1), ("8471", 8471), ("65535", 65535)])
def test_a_port_is_read_from_port(text, port):
    assert main_module.port_from(text) == port


@pytest.mark.parametrize("text", ["0", "65536", "-1", "eighty", "84.71"])
def test_anything_but_a_port_is_refused(text):
    with pytest.raises(ValueError):
        main_module.port_from(text)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _launch(monkeypatch, tmp_path):
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    return _Opened(monkeypatch)


def _port_of(face) -> int:
    return urllib.parse.urlsplit(face.url).port


def test_the_port_pressless_port_names_is_served(monkeypatch, tmp_path):
    """PRESS-0431: the local web-server manager starts Pressless on a port it
    knows. Breaks when the launcher ignores PRESSLESS_PORT, or a restart
    moves to another port."""
    opened = _launch(monkeypatch, tmp_path)
    port = _free_port()
    monkeypatch.setenv("PRESSLESS_PORT", str(port))
    passes = iter([True, False])
    monkeypatch.setattr(main_module, "_wait", lambda restart: next(passes))

    assert main_module.main([]) == 0
    assert [_port_of(face) for face in opened.faces] == [port, port]


def test_a_bare_port_variable_is_not_read(monkeypatch, tmp_path):
    """PRESS-0011 § 8: a PORT some other tool exported must not pin the
    double-click's port."""
    opened = _launch(monkeypatch, tmp_path)
    port = _free_port()
    monkeypatch.setenv("PORT", str(port))

    assert main_module.main([]) == 0
    assert _port_of(opened.faces[0]) != port


def test_a_held_port_is_told_plainly(monkeypatch, tmp_path, capsys):
    """PRESS-0431. Breaks when a held port reads as "could not start
    (OSError)", or Pressless moves to a port the manager does not watch."""
    opened = _launch(monkeypatch, tmp_path)
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        monkeypatch.setenv("PRESSLESS_PORT", str(port))
        assert main_module.main([]) == 1
    out = capsys.readouterr().out
    told = main_module.face.sentence_for(main_module.PortHeld(port), publishing=False)
    assert f"{told.what} {told.next}" in out and str(port) in told.what
    assert opened.faces == [] and opened.links == []


@pytest.mark.parametrize("text", ["0", "65536", "eighty"])
def test_a_port_that_is_no_port_is_refused(monkeypatch, tmp_path, capsys, text):
    opened = _launch(monkeypatch, tmp_path)
    monkeypatch.setenv("PRESSLESS_PORT", text)

    assert main_module.main([]) == 2
    assert main_module.say("main.port_unusable", name="PRESSLESS_PORT",
                           value=text) in capsys.readouterr().out
    assert opened.faces == []


def test_the_double_click_refreshes_the_shortcuts(monkeypatch, tmp_path, capsys):
    """PRESS-0183: every launch points his shortcuts at where it runs from."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    opened = _Opened(monkeypatch)

    assert main_module.main([]) == 0
    assert opened.refreshed == opened.faces


def test_a_shortcut_that_cannot_be_refreshed_is_logged_not_fatal(monkeypatch, tmp_path):
    noted = []

    class _Served:
        def note(self, text):
            noted.append(text)

    where = object()
    monkeypatch.setattr(main_module.shortcuts, "places", lambda: where)

    def refuse(given):
        assert given is where
        raise main_module.shortcuts.ShortcutError("refused")

    monkeypatch.setattr(main_module.shortcuts, "refresh", refuse)
    main_module._refresh_shortcuts(_Served())
    assert noted == ["a shortcut could not be refreshed: ShortcutError"]


# ------------------------------------------------------------ PRESS-0223 ----

# § 4.4: which parts take the site's folder, and which Pressless's own.
_SITE_PARTS = ("setup", "github_setup", "google_setup", "dashboard", "editor", "templates",
               "publishing", "undo", "page_editor", "look_screen", "files_screen")
_OWN_PARTS = ("updating", "sites_screen")


def test_a_switch_hands_the_new_site_to_every_part(monkeypatch, tmp_path, capsys):
    """PRESS-0223 INV-6. Breaks when a part keeps the old site, or the log
    moves into a site."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    own = artefact.parent / _FOLDER_NAME
    for name in ("site-1", "site-2"):
        (own / "sites" / name).mkdir(parents=True)
    calls: list[tuple[str, object, dict]] = []
    real_serve = main_module.face.serve

    def serve(folder, **kwargs):
        calls.append(("face", folder, kwargs))
        return real_serve(folder, **kwargs)

    monkeypatch.setattr(main_module.face, "serve", serve)
    for name in (*_SITE_PARTS, *_OWN_PARTS, "usage"):
        monkeypatch.setattr(getattr(main_module, name), "register",
                            lambda served, folder, *args, _name=name, **kwargs:
                            calls.append((_name, folder, kwargs)))
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    monkeypatch.setattr(main_module, "_refresh_shortcuts", lambda served: None)
    started: list[tuple] = []
    monkeypatch.setattr(main_module.backups, "start",
                        lambda folder, stop, note=None: started.append((folder, stop)))
    passes = iter([True, False])

    def wait(restart):
        main_module.sites.choose(own, "site-2")   # what POST /sites/open does
        return next(passes)

    monkeypatch.setattr(main_module, "_wait", wait)
    assert main_module.main([]) == 0

    for number, site in ((0, own / "sites" / "site-1"), (1, own / "sites" / "site-2")):
        made = [call for call in calls if call[0] == "face"][number]
        assert made[1] == own and made[2] == {"port": 0, "site": site, "session": None}, made
        for name in _SITE_PARTS:
            assert [c[1] for c in calls if c[0] == name][number] == site, name
        for name in _OWN_PARTS:
            assert [c[1] for c in calls if c[0] == name][number] == own, name
        usage_call = [c for c in calls if c[0] == "usage"][number]
        assert usage_call[1] == own and usage_call[2] == {"site": site}
    assert (own / "pressless.log").is_file()
    assert not list((own / "sites").glob("*/pressless.log"))
    # PRESS-0225: each pass starts the backups over Pressless's own folder,
    # and stops them when it ends.
    assert [call[0] for call in started] == [own, own]
    assert all(call[1].is_set() for call in started)


def test_a_closed_window_stops_pressless_as_ctrl_c_does(monkeypatch, tmp_path, capsys):
    """PRESS-0337 § 4.2, found by § 7: closing the terminal (SIGHUP) or a stop
    from the system (SIGTERM) runs the same shutdown as Ctrl+C, so the AI
    helper's door file goes with the Face. A handler another program set
    stays, and the old ones are back afterwards."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    _Opened(monkeypatch)
    own = artefact.parent / _FOLDER_NAME
    own.mkdir(parents=True, exist_ok=True)
    (own / "assistant.json").write_text('{"on": true}', encoding="utf-8")
    names = [name for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)]
    before = {name: signal.getsignal(getattr(signal, name)) for name in names}
    for name in names:
        signal.signal(getattr(signal, name), signal.SIG_DFL)
    seen = []

    def wait(restart):
        assert (own / "assistant-door.json").exists()
        handler = signal.getsignal(getattr(signal, names[-1]))
        seen.append(handler)
        handler(getattr(signal, names[-1]), None)   # what the closed window sends
        return True                                  # never reached

    monkeypatch.setattr(main_module, "_wait", wait)
    try:
        assert main_module.main([]) == 0
        assert callable(seen[0])
        assert not (own / "assistant-door.json").exists()
        assert all(signal.getsignal(getattr(signal, name)) == signal.SIG_DFL
                   for name in names)
    finally:
        for name, handler in before.items():
            signal.signal(getattr(signal, name), handler)


_REAL_WAIT = main_module._wait   # before any test replaces it


def test_a_closed_windows_console_waits_for_the_stop(monkeypatch, tmp_path, capsys):
    """PRESS-0407: Windows has no SIGHUP. Closing the console sends
    CTRL_CLOSE_EVENT to a console handler on a thread of its own, and ends the
    process once that handler returns. So the handler starts Ctrl+C's way out
    and returns only once the stop steps have run: the AI helper's door file
    is gone by then. Ctrl+C itself is left to Python. The system's call is
    stood in for here; the box check proves the real one."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    _Opened(monkeypatch)
    waiting = threading.Event()

    def wait(restart):
        """The real wait, interrupted; the window is closed only once it is
        reached, as a person closes it after the Face is up."""
        waiting.set()
        return _REAL_WAIT(restart)

    monkeypatch.setattr(main_module, "_wait", wait)
    own = artefact.parent / _FOLDER_NAME
    own.mkdir(parents=True, exist_ok=True)
    (own / "assistant.json").write_text('{"on": true}', encoding="utf-8")
    door = own / "assistant-door.json"
    handlers, removed, seen = [], [], {}

    def install(on_event):
        handlers.append(on_event)
        return lambda: removed.append(on_event)

    monkeypatch.setattr(main_module, "_console_handler", install)

    def windows():
        """What Windows does when the window is closed: call the handler on a
        thread of its own, then end the process once it returns."""
        waiting.wait(10)
        seen["door_before"] = door.exists()
        seen["ctrl_c"] = handlers[0](0)        # CTRL_C_EVENT: Python's own
        seen["close"] = handlers[0](2)         # CTRL_CLOSE_EVENT
        seen["door"] = door.exists()

    closer = threading.Thread(target=windows, daemon=True)
    closer.start()
    assert main_module.main([]) == 0
    closer.join(timeout=10)
    assert seen == {"door_before": True, "ctrl_c": False, "close": True, "door": False}
    assert removed == handlers



class _Replaced(BaseException):
    """What a real os.execve does to the caller: nothing after it runs."""


def test_an_update_reopens_in_this_process_once_it_has_stopped(monkeypatch, tmp_path,
                                                                capsys):
    """PRESS-0408: after a Linux update the stop steps run -- the AI helper's
    door file goes and the folder's lock is let go -- and then the new
    AppImage replaces this process, so it keeps the terminal, Ctrl+C and a
    later Restart. A Ctrl+C before that stops it, and nothing reopens.

    Breaks when the new program is started before the stop, beside this
    process, or not at all."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))
    _Opened(monkeypatch)
    own = artefact.parent / _FOLDER_NAME
    own.mkdir(parents=True, exist_ok=True)
    (own / "assistant.json").write_text('{"on": true}', encoding="utf-8")
    door = own / "assistant-door.json"
    handed: dict[str, object] = {}
    real_register = main_module.updating.register

    def register(served, own, **kwargs):
        handed.update(kwargs)
        return real_register(served, own, **kwargs)

    monkeypatch.setattr(main_module.updating, "register", register)
    seen = []

    def execve(path, args, env):
        held = main_module._hold(own)
        seen.append((path, args, door.exists(), held is not None))
        if held is not None:
            held.close()
        raise _Replaced

    monkeypatch.setattr(main_module.installer.os, "execve", execve)
    # The exec gives the new program default signal dispositions; the test
    # runner gets its own back.
    kept = {name: signal.getsignal(getattr(signal, name))
            for name in ("SIGPIPE", "SIGXFSZ") if hasattr(signal, name)}
    try:
        waits = []

        def updated(restart):
            """What Update now does once its page is sent (updating._update_now)."""
            waits.append(restart)
            assert len(waits) == 1, "a new Face was served after the update"
            assert door.exists()
            handed["state"].installed = (artefact, "9.9.9")
            handed["stop"]()
            return _REAL_WAIT(restart)

        monkeypatch.setattr(main_module, "_wait", updated)
        with pytest.raises(_Replaced):
            main_module.main([])
        assert seen == [(str(artefact), [str(artefact)], False, True)], seen

        def interrupted(restart):
            handed["state"].installed = (artefact, "9.9.9")
            raise KeyboardInterrupt

        seen.clear()
        monkeypatch.setattr(main_module, "_wait", interrupted)
        assert main_module.main([]) == 0
        assert seen == [] and not door.exists()
    finally:
        for name, handler in kept.items():
            signal.signal(getattr(signal, name), handler)


# ------------------------------------------------------------- PRESS-0428 ---
# A restart or an update hands the port and session to the next Face, so a
# tab still open carries on. A session a previous Face would have made: 43
# URL-safe characters, written so no scanner reads it as a real token.
_HANDED = "handed-over-session-" + "x" * 23


def _alive(port: int, cookie: str) -> int:
    """GET /alive on `port` with `cookie`; the status."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.putrequest("GET", "/alive", skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"127.0.0.1:{port}")
        conn.putheader("Cookie", cookie)
        conn.endheaders()
        response = conn.getresponse()
        response.read()
        return response.status
    finally:
        conn.close()


def test_a_restart_keeps_the_port_and_session(monkeypatch, tmp_path):
    """PRESS-0428 INV-1. Breaks when _serve_once is given no hand-over, or
    serve ignores `session`."""
    opened = _launch(monkeypatch, tmp_path)
    monkeypatch.setattr(main_module, "RETURN_SECONDS", 0.1)
    cookies: list[str] = []
    statuses: list[int] = []

    def wait(restart):
        if not cookies:
            cookies.append(session_cookie(opened.faces[0].url))
            return True
        statuses.append(_alive(opened.faces[1].port, cookies[0]))
        return False

    monkeypatch.setattr(main_module, "_wait", wait)
    assert main_module.main([]) == 0
    assert [face.port for face in opened.faces] == [opened.faces[0].port] * 2
    assert statuses == [200], "the old tab's cookie was refused after the restart"


def test_a_held_handed_port_starts_afresh(monkeypatch, tmp_path, capsys):
    """PRESS-0428 INV-2: § 4.1's table. Breaks when the session is carried
    to another port, or the fallback raises."""
    opened = _launch(monkeypatch, tmp_path)
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        monkeypatch.setenv("PRESSLESS_RESUME", f"{port}:{_HANDED}")
        assert main_module.main([]) == 0
        [served] = opened.faces
        assert served.port != port and served.hand_over().session != _HANDED
        assert len(opened.links) == 1, "no tab opened for a session no tab holds"

        monkeypatch.setenv("PRESSLESS_RESUME", f"{port}:{_HANDED}")
        monkeypatch.setenv("PRESSLESS_PORT", str(port))
        assert main_module.main([]) == 1
    told = main_module.face.sentence_for(main_module.PortHeld(port), publishing=False)
    assert told.what in capsys.readouterr().out


@pytest.mark.parametrize("value, handed", [
    (f"8471:{_HANDED}", (8471, _HANDED)),
    ("8471", None), (f"0:{_HANDED}", None), (f"65536:{_HANDED}", None),
    (f"port:{_HANDED}", None), ("8471:short", None), (f"8471:{_HANDED}:more", None),
    (f"8471:{_HANDED[:-1]}!", None), ("", None),
])
def test_the_resume_variable_is_read_once_and_removed(monkeypatch, tmp_path, value, handed):
    """PRESS-0428 INV-3. Breaks when the variable is read and left in place,
    so a browser started later inherits the session."""
    _launch(monkeypatch, tmp_path)
    monkeypatch.setenv("PRESSLESS_RESUME", value)
    seen = []

    def serve(own, port=0, *, resume=None):
        seen.append((os.environ.get("PRESSLESS_RESUME"),
                     resume and (resume.port, resume.session)))
        return 0

    monkeypatch.setattr(main_module, "_serve", serve)
    assert main_module.main([]) == 0
    assert seen == [(None, handed)]


def test_a_returning_tab_means_no_new_tab(monkeypatch, tmp_path):
    """PRESS-0428 INV-5. Breaks when the launcher opens a tab regardless, or
    never opens one."""
    opened = _launch(monkeypatch, tmp_path)
    real_serve = main_module.face.serve
    port = _free_port()

    def returning(folder, **kwargs):
        served = real_serve(folder, **kwargs)
        if kwargs.get("session") == _HANDED:
            threading.Thread(target=_alive, args=(
                served.port, f"pressless-{served.port}={_HANDED}"), daemon=True).start()
        return served

    monkeypatch.setattr(main_module.face, "serve", returning)
    monkeypatch.setattr(main_module, "RETURN_SECONDS", 5)
    monkeypatch.setenv("PRESSLESS_RESUME", f"{port}:{_HANDED}")
    assert main_module.main([]) == 0
    assert opened.links == [], "a tab opened although the old one came back"

    # Nobody comes back: the launcher opens the tab once the wait ends.
    monkeypatch.setattr(main_module.face, "serve", real_serve)
    opened = _Opened(monkeypatch)
    monkeypatch.setattr(main_module, "RETURN_SECONDS", 0.1)
    monkeypatch.setenv("PRESSLESS_RESUME", f"{port}:{_HANDED}")
    assert main_module.main([]) == 0
    [served] = opened.faces
    [link] = opened.links
    assert (served.port, served.hand_over().session) == (port, _HANDED)
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(link).query) == \
        urllib.parse.parse_qs(urllib.parse.urlsplit(served.url).query)


def test_another_site_hands_nothing_over(monkeypatch, tmp_path):
    """PRESS-0428 INV-9 and § 3 decision 5: an old tab's save would land in
    the other site. Breaks when _serve_held hands over whatever the next
    pass opens."""
    opened = _launch(monkeypatch, tmp_path)
    cookies: list[str] = []
    statuses: list[int] = []

    def wait(restart):
        if not cookies:
            cookies.append(session_cookie(opened.faces[0].url))
            made = main_module.sites.new_site(opened.faces[0]._folder)
            main_module.sites.choose(opened.faces[0]._folder, made.name)   # POST /sites/open
            return True
        statuses.append(_alive(opened.faces[1].port, cookies[0]))
        return False

    monkeypatch.setattr(main_module, "_wait", wait)
    assert main_module.main([]) == 0
    first, second = opened.faces
    assert first._site != second._site
    assert second.hand_over().session != first.hand_over().session
    assert statuses == [403] and len(opened.links) == 2
