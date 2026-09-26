# PRESS-0022 § 4.5: the program that gets packaged, and its report.
#
# The report's shape is a contract -- § 7's release job and
# tests/features/packaging/ parse it, and the job reads its exit code -- so it
# is pinned here against the same patched resolution tests/test_paths.py uses,
# without a build. INV-6 itself needs a built artefact and lives with the
# packaging tests.
from __future__ import annotations

import sys
import threading
import urllib.parse

import pytest
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
        real_serve = main_module.face.serve

        def serve(folder, *, open_browser=True):
            served = real_serve(folder, open_browser=False)
            self.faces.append(served)
            return served

        monkeypatch.setattr(main_module.face, "serve", serve)
        monkeypatch.setattr(main_module.webbrowser, "open",
                            lambda url: self.links.append(url) or True)
        monkeypatch.setattr(main_module, "_wait", lambda: None)
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
                  ("POST", "/update"), ("POST", "/update/checking")):
        assert route in pages, route
    assert urllib.parse.urlsplit(opened.links[0]).path == "/setup"

    folder = artefact.parent / _FOLDER_NAME
    settings.save(folder, settings.Settings(
        site_folder=folder / "site", repository="owner/owner.github.io",
        site_name="A Journal", site_address="https://example.org",
        daily_prompt_filter="", untouchable=(),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))
    assert main_module.main([]) == 0
    assert urllib.parse.urlsplit(opened.links[1]).path == "/"


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

    def serving() -> None:
        handle = _try_lock(lock)
        held_while_serving.append(handle is None)
        if handle is not None:
            handle.close()

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
