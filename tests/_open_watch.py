"""One shared open-watcher for the Store's two test files.

Why it is shared rather than copied: PRESS-0005 INV-6 and PRESS-0006 INV-10
both ask what the Store NAMED when it opened a file, and neither can be
answered from the bytes on Linux -- os.linesep is "\n" here, so a write that
left the newline to the platform produces the same bytes as one that named it,
and the assertion passes against the very defect it exists to catch. Measured
2026-09-02 by mutation probe: newline=None survived a byte-level INV-10.

It lives beside the tests rather than in either of them because two copies of
a watcher are two watchers that will disagree.
"""
from __future__ import annotations

import builtins
import io
import os
import pathlib
from typing import NamedTuple


class _Open(NamedTuple):
    """One filesystem open the module under test performed."""

    path: str | None      # None where the call named a file descriptor
    mode: str
    encoding: str | None
    newline: str | None
    binary: bool

    def writes(self) -> bool:
        return any(character in self.mode for character in "wxa+")


def _watch_opens(monkeypatch) -> list[_Open]:
    """Record every open the code under test performs, with its mode.

    Six entry points, because which one an implementation reaches for is its
    own choice and the invariants are about all of them: builtins.open and
    io.open (the same function, patched at both names a module may hold),
    os.open and os.fdopen (what tempfile.mkstemp and §4.5's shape use), and
    Path.open / Path.write_text / Path.write_bytes (what settings.py's
    read_text goes through). A watch that missed the one the implementation
    happened to use would report nothing and look like a clean pass."""
    opens: list[_Open] = []

    real_open = builtins.open
    real_io_open = io.open
    real_os_open = os.open
    real_fdopen = os.fdopen
    real_path_open = pathlib.Path.open
    real_write_text = pathlib.Path.write_text
    real_write_bytes = pathlib.Path.write_bytes

    def _record(path, mode, encoding, newline):
        try:
            named = None if path is None else os.fspath(path)
        except TypeError:
            named = None
        opens.append(_Open(named, mode, encoding, newline, "b" in mode))

    def _argument(args, kwargs, index, name):
        """One optional argument of an open(), however it was passed.

        Reading it from kwargs alone is wrong and was measured so: os.fdopen
        and Path.write_text both delegate inwards POSITIONALLY, so a
        conforming write that named UTF-8 and a newline was recorded as having
        named neither -- INV-6 then failed against exactly the code it exists
        to accept."""
        if name in kwargs:
            return kwargs[name]
        return args[index] if len(args) > index else None

    def watched_open(file, mode="r", *args, **kwargs):
        _record(file, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_open(file, mode, *args, **kwargs)

    def watched_io_open(file, mode="r", *args, **kwargs):
        _record(file, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_io_open(file, mode, *args, **kwargs)

    def watched_os_open(path, flags, *args, **kwargs):
        writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        # Always binary at this level, so INV-6 asks nothing of it -- the
        # os.fdopen that wraps it is where an encoding would be named.
        _record(path, "wb" if writing else "rb", None, None)
        return real_os_open(path, flags, *args, **kwargs)

    def watched_fdopen(fd, mode="r", *args, **kwargs):
        _record(None, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_fdopen(fd, mode, *args, **kwargs)

    def watched_path_open(self, mode="r", *args, **kwargs):
        _record(self, mode, _argument(args, kwargs, 1, "encoding"),
                _argument(args, kwargs, 3, "newline"))
        return real_path_open(self, mode, *args, **kwargs)

    def watched_write_text(self, data, *args, **kwargs):
        _record(self, "w", _argument(args, kwargs, 0, "encoding"),
                _argument(args, kwargs, 2, "newline"))
        return real_write_text(self, data, *args, **kwargs)

    def watched_write_bytes(self, data):
        _record(self, "wb", None, None)
        return real_write_bytes(self, data)

    monkeypatch.setattr(builtins, "open", watched_open)
    monkeypatch.setattr(io, "open", watched_io_open)
    monkeypatch.setattr(os, "open", watched_os_open)
    monkeypatch.setattr(os, "fdopen", watched_fdopen)
    monkeypatch.setattr(pathlib.Path, "open", watched_path_open)
    monkeypatch.setattr(pathlib.Path, "write_text", watched_write_text)
    monkeypatch.setattr(pathlib.Path, "write_bytes", watched_write_bytes)
    return opens
