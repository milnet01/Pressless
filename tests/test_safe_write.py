# The one copy of the replace-a-file-whole steps (PRESS-0141).
#
# The contract is docs/specs/PRESS-0001-settings.md § 4.4, which states
# write_whole's surface; § 11 names the modules that call it. Each module's
# own tests still check its own file. These check the steps themselves, once.
from __future__ import annotations

import ast
import inspect
import os
import stat
import sys

import pytest
from _durability_watch import _assert_synced_before_replace, _watch_durability

from pressless import safe_write
from pressless.safe_write import write_whole

_NETWORK = {
    "socket", "ssl", "urllib", "http", "requests", "httpx",
    "ftplib", "smtplib", "poplib", "imaplib", "xmlrpc", "webbrowser",
}


def test_it_imports_nothing_of_ours_and_no_network():
    """§ 4.4: it imports no pressless module and no network module, so a
    module whose INV-1 allows it inherits no route to anything else.

    Breaks when the helper imports a sibling, which would reach every module
    that calls it."""
    imported = set()
    relative = []
    for node in ast.walk(ast.parse(inspect.getsource(safe_write))):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.append(node)
            elif node.module:
                imported.add(node.module.split(".")[0])
    assert "pressless" not in imported
    assert not relative
    assert not imported & _NETWORK, imported & _NETWORK


def test_it_replaces_the_file_whole(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")
    write_whole(target, "new é\n", prefix=".state-")
    assert target.read_bytes() == "new é\n".encode()
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


@pytest.mark.parametrize("newline, written", [("\n", b"a\nb\n"), ("", b"a\r\nb\n")])
def test_newline_is_the_callers(tmp_path, newline, written):
    """"\\n" writes the same bytes on both systems; "" turns translation off
    and keeps what it was handed, which a Store page needs.

    Breaks when the default is left to the platform, which writes CRLF on
    Windows."""
    target = tmp_path / "page.html"
    write_whole(target, "a\r\nb\n" if newline == "" else "a\nb\n",
                prefix=".page-", newline=newline)
    assert target.read_bytes() == written


def test_the_temporary_sits_beside_the_target_and_is_synced_first(tmp_path, monkeypatch):
    events = _watch_durability(monkeypatch)
    target = tmp_path / "state.json"
    write_whole(target, "text", prefix=".state-")
    _assert_synced_before_replace(events, "write_whole")
    made = os.path.basename(events[0][2])
    assert made.startswith(".state-") and made.endswith(".tmp"), made
    assert os.path.dirname(events[0][2]) == str(tmp_path)


def test_check_sees_the_raw_descriptor_before_a_byte_is_written(tmp_path):
    seen = []

    def check(handle):
        seen.append(os.fstat(handle).st_size)

    write_whole(tmp_path / "state.json", "text", prefix=".state-", check=check)
    assert seen == [0]


def test_a_refusing_check_leaves_the_target_and_no_temporary(tmp_path):
    """What check raises reaches the caller unchanged, the descriptor is
    closed and the temporary removed: Credentials refuses there, before the
    secret is written.

    Breaks when the helper wraps the refusal, leaks the descriptor, or
    writes first."""
    target = tmp_path / "state.json"
    target.write_text("before", encoding="utf-8")
    handles = []

    class Refused(Exception):
        pass

    def check(handle):
        handles.append(handle)
        raise Refused("no")

    with pytest.raises(Refused):
        write_whole(target, "secret", prefix=".state-", check=check)
    assert target.read_text(encoding="utf-8") == "before"
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]
    with pytest.raises(OSError):
        os.fstat(handles[0])


def test_a_failed_replace_leaves_the_target_and_no_temporary(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text("before", encoding="utf-8")

    def refused(source, destination):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", refused)
    with pytest.raises(OSError) as raised:
        write_whole(target, "after", prefix=".state-")
    assert raised.value.errno == 28
    assert target.read_text(encoding="utf-8") == "before"
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


def test_text_utf8_cannot_carry_is_raised_and_cleaned_up(tmp_path):
    """A lone surrogate is a value UTF-8 cannot encode. The Store turns the
    UnicodeError into its own error (PRESS-0005 INV-9), so it must arrive
    unchanged, with nothing left behind."""
    with pytest.raises(UnicodeError):
        write_whole(tmp_path / "state.json", "a\ud800b", prefix=".state-")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Windows grants no 0600")
def test_the_file_is_owner_only_where_the_mount_grants_it(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("wide", encoding="utf-8")
    target.chmod(0o644)
    write_whole(target, "narrow", prefix=".state-")
    assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0


@pytest.mark.parametrize("refusals, written", [(2, True), (50, False)])
def test_a_replace_windows_refuses_for_a_moment_is_retried(tmp_path, monkeypatch,
                                                           refusals, written):
    """PRESS-0159: on Windows a scanner opening the file just written refuses
    the replace for a moment (measured on the Windows box: error 5). The
    platform is read from safe_write._is_windows(), which is what this patches.

    Breaks when the first refusal is final on Windows, or when one still
    refused after the wait is swallowed."""
    monkeypatch.setattr(safe_write, "_is_windows", lambda: True)
    monkeypatch.setattr(safe_write.time, "sleep", lambda seconds: None)
    target = tmp_path / "state.json"
    target.write_text("before", encoding="utf-8")
    real = os.replace
    left = [refusals]

    def held(source, destination):
        if left[0]:
            left[0] -= 1
            raise PermissionError(13, "Access is denied")
        return real(source, destination)

    monkeypatch.setattr(os, "replace", held)
    if written:
        write_whole(target, "after", prefix=".state-")
    else:
        with pytest.raises(PermissionError):
            write_whole(target, "after", prefix=".state-")
    monkeypatch.setattr(os, "replace", real)
    assert (target.read_text(encoding="utf-8") == "after") is written
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


def test_off_windows_the_first_refusal_is_final(tmp_path, monkeypatch):
    monkeypatch.setattr(safe_write, "_is_windows", lambda: False)
    calls = []

    def held(source, destination):
        calls.append(source)
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "replace", held)
    with pytest.raises(PermissionError):
        write_whole(tmp_path / "state.json", "after", prefix=".state-")
    assert len(calls) == 1


@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="Windows opens no folder descriptor to sync")
def test_the_folder_is_synced_after_the_replace(tmp_path, monkeypatch):
    """PRESS-0376: the replace is a change to the FOLDER, and on POSIX a
    power loss can lose it unless the folder is synced too -- a save reported
    done comes back as the old version, or a first save vanishes.

    Breaks when only the temporary's descriptor is synced."""
    synced = []
    real_fsync = os.fsync

    def watched(descriptor):
        found = os.fstat(descriptor)
        synced.append((stat.S_ISDIR(found.st_mode), found.st_ino))
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", watched)
    write_whole(tmp_path / "state.json", "text", prefix=".state-")
    assert (True, os.stat(tmp_path).st_ino) in synced, "the folder was never synced"
    assert synced.index((True, os.stat(tmp_path).st_ino)) > 0, "the folder was synced first"


def test_a_folder_that_cannot_be_synced_does_not_fail_a_save(tmp_path, monkeypatch):
    """PRESS-0376: the folder sync is best effort. Some file systems refuse
    to sync a folder; the file is already in place by then, so a refusal must
    not report a finished save as failed."""
    real_fsync = os.fsync

    def refusing(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(22, "Invalid argument")
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", refusing)
    target = tmp_path / "state.json"
    write_whole(target, "text", prefix=".state-")
    assert target.read_text(encoding="utf-8") == "text"


# ----------------------------------------------- the shared reader (PRESS-0447) ----
# Settings and Credentials read their versioned JSON file through one reader.
# Each refusal either made before is asked of all four doors: settings load and
# save, credentials read and write. A file refused is never written over.

_SECRETS = b', "secrets": {}}'
_REFUSED = {
    "not-utf8": (b"\xff\xfe{", b"\xff\xfe{"),                          # PRESS-0049, -0135
    "nested-too-deep": (b"[" * 100_000 + b"]" * 100_000,) * 2,         # PRESS-0066, -0135
    "not-json": (b"{not json", b"{not json"),
    "not-an-object": (b"[]", b"[]"),
    "version-true": (b'{"version": true}', b'{"version": true' + _SECRETS),   # PRESS-0066, -0100
    "version-float": (b'{"version": 1.0}', b'{"version": 1.0' + _SECRETS),
    "version-other": (b'{"version": 2}', b'{"version": 2' + _SECRETS),        # PRESS-0053
    "version-absent": (b'{"other": 1}', b'{"other": 1' + _SECRETS),
}


def _settings_value(folder):
    from pressless import settings
    return settings.Settings(
        site_folder=folder / "site", repository="owner/name",
        site_address="https://example.org", daily_prompt_filter="", untouchable=(),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None)


def _doors(folder):
    """Each reader's four doors, with the error each must raise."""
    from pressless import credentials, settings
    return {
        "settings load": (lambda: settings.load(folder), settings.SettingsError),
        "settings save": (lambda: settings.save(folder, _settings_value(folder)),
                          settings.SettingsError),
        "credentials read": (lambda: credentials.read("file", folder, "publishing-key"),
                             credentials.CredentialError),
        "credentials write": (lambda: credentials.write("file", folder, "publishing-key",
                                                        "a-secret"),
                              credentials.CredentialError),
        "credentials delete": (lambda: credentials.delete("file", folder, "publishing-key"),
                               credentials.CredentialError),
    }


@pytest.mark.parametrize("case", sorted(_REFUSED))
def test_both_readers_refuse_each_file_they_refused_before(tmp_path, monkeypatch, case):
    """Breaks when the shared reader drops a refusal, or one module stops
    calling it: the door that no longer refuses either succeeds or raises an
    error of the wrong type, and a write replaces the file."""
    from pressless import credentials, settings
    monkeypatch.setattr(sys, "platform", "linux")   # the file store writes off Windows only
    as_settings, as_credentials = _REFUSED[case]
    for door, (call, error) in _doors(tmp_path).items():
        name = settings.FILE_NAME if door.startswith("settings") else credentials.FILE_NAME
        content = as_settings if door.startswith("settings") else as_credentials
        (tmp_path / name).write_bytes(content)
        with pytest.raises(error):
            call()
        assert (tmp_path / name).read_bytes() == content, f"{door} replaced a refused file"


@pytest.mark.parametrize("shape", ["fifo", "folder"])
def test_both_readers_refuse_what_is_not_an_ordinary_file(tmp_path, monkeypatch, shape):
    """PRESS-0162's refusal, now the settings file's too: a FIFO planted at
    either name would hold the open forever, and launch reads the settings
    file. Run in a thread with a bound, so a reader that waits fails rather
    than hanging the suite. Breaks when the open loses O_NONBLOCK or the
    regular-file check."""
    import threading

    from pressless import credentials, settings
    if shape == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("this platform has no FIFO")
    monkeypatch.setattr(sys, "platform", "linux")
    for name in (settings.FILE_NAME, credentials.FILE_NAME):
        if shape == "fifo":
            os.mkfifo(tmp_path / name)
        else:
            (tmp_path / name).mkdir()
    doors = {**_doors(tmp_path),
             "settings retired name": (lambda: settings.retired_site_name(tmp_path), None)}
    for door, (call, error) in doors.items():
        outcome: list[object] = []

        def attempt(call=call, outcome=outcome):
            try:
                outcome.append(call())
            except BaseException as exc:  # noqa: BLE001 -- inspected below
                outcome.append(exc)

        worker = threading.Thread(target=attempt, daemon=True)
        worker.start()
        worker.join(5)
        if worker.is_alive():
            for name in (settings.FILE_NAME, credentials.FILE_NAME):
                os.close(os.open(tmp_path / name, os.O_WRONLY | os.O_NONBLOCK))
            pytest.fail(f"{door} waited on the FIFO")
        if error is None:
            assert outcome == [None], door
        else:
            # Refused as what it is: read as a file, a FIFO answers empty and
            # a device answers forever.
            assert isinstance(outcome[0], error), (door, outcome)
            assert "not an ordinary file" in str(outcome[0]), (door, outcome)
