"""PRESS-0003 — the rolling log.

One test per invariant, except INV-1 (a behavioural test plus an import walk)
and INV-3 (one per reachable failure). The spec's §7 owns which is which.

The literals under test are written out here rather than imported from the
module. Sharing them would compare the module against itself, so `path_for`
could name any file and stay green -- the same rule tests/test_settings.py
keeps for "settings.json".
"""

from __future__ import annotations

import ast
import inspect
import io
import os
import re
from pathlib import Path

import pytest

from pressless import log as log_module

# INV-5's denylist. `logging.handlers` imports socket itself, but the walk
# below records only top-level names from *this* module's own AST, so that
# transitive import is invisible to it -- which is what makes INV-5 passable
# against a faithful implementation (spec §5 INV-5).
_FORBIDDEN_NETWORK_IMPORTS = {"socket", "http", "urllib", "requests", "ssl"}

# INV-1's denylist: anything that puts an identifying value one attribute
# access from a log line.
_FORBIDDEN_IDENTIFYING_IMPORTS = {"keyring"}

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")


def _top_level_imports(module) -> set[str]:
    """The module's own direct imports, by top-level name.

    Walks the AST as tests/test_marks.py::test_marks_is_pure does, and reads
    the source from here rather than from the module under test.
    """
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


class _FailingStream(io.StringIO):
    """A stream that opens fine and then fails, which is the only way to
    reach `note` and `close`'s failure paths.

    A folder that cannot be written reaches `open_log` and stops there --
    §4.4 hands back a Log that writes nothing, so `note` on it cannot raise
    however `note` is written (spec §5 INV-3).
    """

    def __init__(self, *, on_write=False, on_flush=False):
        super().__init__()
        self._on_write = on_write
        self._on_flush = on_flush

    def write(self, text):  # noqa: D102
        if self._on_write:
            raise OSError("no space left on device")
        return super().write(text)

    def flush(self):  # noqa: D102
        if self._on_flush:
            raise OSError("no space left on device")
        return super().flush()


# --- INV-1 -----------------------------------------------------------------


def test_note_adds_nothing(tmp_path):
    """INV-1: a line is the timestamp and the message, and nothing else.

    Breaks when someone appends context -- the folder, the repository, the
    machine name -- to a line.
    """
    entry = open_and_note(tmp_path, "published 587 files")
    assert _TIMESTAMP.match(entry), f"no timestamp on {entry!r}"
    assert entry[len("2026-09-08 14:02:11 ") :] == "published 587 files", (
        f"note added something to the message: {entry!r}"
    )


def test_log_imports_nothing_identifying():
    """INV-1: the module imports no other pressless module and no credential
    library, so no identifying value is one attribute access away.

    Weak in the way the spec names (§5): an import walk passes against a
    module that does nothing. test_note_adds_nothing is what carries INV-1.
    """
    imported = _top_level_imports(log_module)
    assert "pressless" not in imported, "log.py imports a sibling pressless module"
    forbidden = imported & _FORBIDDEN_IDENTIFYING_IMPORTS
    assert not forbidden, f"log.py imports {sorted(forbidden)!r}"


# --- INV-2 -----------------------------------------------------------------


def test_rolls_by_size_keeping_one_old_copy(tmp_path):
    """INV-2: past the size the log rolls, and exactly one old copy is kept.

    Asserts the EXACT file set. A test asserting merely that the old copy
    exists passes just as well with a `.2` beside it, which is the unbounded
    case wearing the bounded case's clothes (spec §5 INV-2).
    """
    handle = log_module.open_log(tmp_path)
    line = "x" * 200
    for _ in range(40_000):
        handle.note(line)
    handle.close()

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "pressless.log",
        "pressless.log.1",
    ], "the roll left something other than exactly the log and one old copy"


# --- INV-3, one per reachable failure ---------------------------------------


def test_open_log_survives_an_unwritable_folder(tmp_path):
    """INV-3: opening against a folder that cannot be written does not raise.

    The skip is keyed on the OBSERVED state, never on the platform: chmod does
    not bind a process running as root, and there a platform-keyed test passes
    vacuously -- green against an open_log with no except at all (spec §7).
    """
    folder = tmp_path / "shut"
    folder.mkdir()
    os.chmod(folder, 0o500)
    try:
        try:
            (folder / "probe").write_text("x", encoding="utf-8")
        except OSError:
            pass
        else:
            pytest.skip(
                "chmod did not make the folder unwritable -- running as root, or "
                "a filesystem that ignores the mode. INV-3's open_log case cannot "
                "be exercised here."
            )
        handle = log_module.open_log(folder)
        handle.note("this goes nowhere")
        handle.close()
    finally:
        os.chmod(folder, 0o700)


def test_open_log_survives_a_missing_folder(tmp_path):
    """INV-3: a folder that does not exist does not raise, and nothing is
    created -- creating it would mask the setup stop docs/design.md § Where
    everything sits on disk requires."""
    absent = tmp_path / "not-there"
    handle = log_module.open_log(absent)
    handle.note("this goes nowhere either")
    handle.close()
    assert not absent.exists(), "open_log created the folder, masking setup's stop"


def test_note_survives_a_failing_write(tmp_path, monkeypatch):
    """INV-3: a write that fails on a Log that opened successfully does not
    raise."""
    handle = _log_on_stream(tmp_path, monkeypatch, _FailingStream(on_write=True))
    handle.note("the disk filled just now")
    handle.close()


def test_close_survives_a_failing_flush(tmp_path, monkeypatch):
    """INV-3: close is the entry point that flushes, so it is where a full
    disk raises. A suite exercising only open_log stays green against a close
    written outside its try (spec §5 INV-3)."""
    handle = _log_on_stream(tmp_path, monkeypatch, _FailingStream(on_flush=True))
    handle.note("recorded fine")
    handle.close()


def test_note_survives_an_emit_that_raises(tmp_path, monkeypatch):
    """INV-3: note does not raise even when the handler's own emit does.

    The failing-stream tests cannot see this: logging.Handler.emit carries
    its OWN try/except that routes to handleError, so it swallows a stream
    failure before note's guard is reached. Probed 2026-09-08 -- removing
    note's guard entirely left every other test green. This is what makes
    the guard falsifiable rather than decorative.
    """
    handle = log_module.open_log(tmp_path)
    handler = next(v for v in vars(handle).values() if hasattr(v, "emit"))

    def _raise(record):
        raise OSError("emit itself failed")

    monkeypatch.setattr(handler, "emit", _raise)
    handle.note("this must not escape")
    handle.close()


# --- INV-7 -----------------------------------------------------------------


def test_the_file_is_utf8_whatever_the_platform_default(tmp_path):
    """INV-7: the encoding is pinned, never inherited from the locale.

    Asserts the value the handler was built with rather than the bytes,
    because on a UTF-8 machine the platform default and the pinned value
    produce identical files -- so a bytes-only test passes here and ships the
    defect to Windows, where the default is a codepage. PRESS-0006 INV-10's
    test asserts its call for the same reason.
    """
    handle = log_module.open_log(tmp_path)
    handler = next(v for v in vars(handle).values() if hasattr(v, "encoding"))
    assert handler.encoding == "utf-8", (
        f"the handler was built with encoding={handler.encoding!r}. None means "
        f"the locale's encoding, which drops a line silently on Windows."
    )
    handle.close()


def test_a_line_survives_a_character_utf8_cannot_hold(tmp_path):
    """INV-7: a str can hold what UTF-8 cannot, and the line still lands.

    A lone surrogate is what an undecodable filename arrives carrying through
    surrogateescape -- and a stock file error quoting such a path is exactly
    the message class that reaches the log unstripped (spec §2). Without
    `errors` the write raises inside emit, handleError swallows it, and the
    line vanishes while its neighbours remain.
    """
    handle = log_module.open_log(tmp_path)
    handle.note("before")
    handle.note("bad path: " + chr(0xD800))
    handle.note("after")
    handle.close()

    lines = (tmp_path / "pressless.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3, (
        f"expected all three lines, got {len(lines)}: {lines!r}. A line carrying "
        f"a character UTF-8 cannot encode was dropped in silence."
    )
    assert "bad path:" in lines[1]


# --- INV-4 -----------------------------------------------------------------


def test_log_sits_beside_the_settings_file(tmp_path):
    """INV-4: the log is in the folder it was handed, beside the settings.

    "pressless.log" is written out rather than imported: sharing the literal
    would let path_for name any file and stay green.
    """
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")
    assert log_module.path_for(tmp_path) == tmp_path / "pressless.log"

    handle = log_module.open_log(tmp_path)
    handle.note("a line")
    handle.close()
    assert (tmp_path / "pressless.log").exists()


# --- INV-5 -----------------------------------------------------------------


def test_log_is_offline():
    """INV-5: the module reaches no network.

    Weak in the same way the import walk above is, and recorded as such
    rather than relied on (spec §5 INV-5).
    """
    forbidden = _top_level_imports(log_module) & _FORBIDDEN_NETWORK_IMPORTS
    assert not forbidden, f"log.py imports {sorted(forbidden)!r}"


# --- INV-6 -----------------------------------------------------------------


def test_no_diagnostic_reaches_stderr(tmp_path, monkeypatch, capsys):
    """INV-6: no logging diagnostic reaches stderr on a failure.

    INV-3 cannot reach this: its tests assert no exception ESCAPES, and the
    default handleError escapes nothing -- it prints. So every INV-3 test
    stays green while a traceback quoting absolute paths goes to stderr,
    which is the leak §4.4 describes.
    """
    handle = _log_on_stream(tmp_path, monkeypatch, _FailingStream(on_write=True))
    handle.note("this write fails")
    handle.close()
    captured = capsys.readouterr()
    assert captured.err == "", (
        f"a logging diagnostic reached stderr: {captured.err!r}. A traceback "
        f"quotes absolute paths, which docs/design.md § Logging forbids."
    )


# --- helpers ----------------------------------------------------------------


def open_and_note(folder: Path, message: str) -> str:
    """Write one line and return it, without its trailing newline."""
    handle = log_module.open_log(folder)
    handle.note(message)
    handle.close()
    return (folder / "pressless.log").read_text(encoding="utf-8").rstrip("\n")


def _log_on_stream(folder: Path, monkeypatch, stream):
    """A Log whose handler opened successfully and whose stream then fails.

    Substitutes the stream after the handler is built, so open_log's own path
    is the real one and only the write and flush fail.
    """
    handle = log_module.open_log(folder)
    for candidate in vars(handle).values():
        if hasattr(candidate, "stream"):
            monkeypatch.setattr(candidate, "stream", stream, raising=False)
            return handle
    pytest.fail(
        "no handler with a stream found on the Log -- the double cannot reach "
        "note's or close's failure path, so this test would pass vacuously."
    )
    return None
