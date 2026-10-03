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
