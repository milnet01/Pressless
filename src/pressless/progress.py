"""How far a long job has got, for the note every page shows (PRESS-0435).

The Face holds a record for each POST while it runs (`job`); the loops that
download, send and pack report into the record their thread holds (`count`);
GET /progress reads the one updated last (`now`). The contract is
docs/specs/PRESS-0435-long-job-progress.md.

This module imports no other part of Pressless, so the Publisher may call it
without a route to the publishing key (PRESS-0009 INV-1).
"""
from __future__ import annotations

import contextlib
import itertools
import threading
from collections.abc import Iterator
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Counted:
    """A job's last report: the words table key saying what it does, files
    done and of how many, and bytes done and of how many. None where not
    known. `seconds_left` is what remains of a wait the job is in, None where
    it is in none (PRESS-0471)."""
    key: str
    done: int = 0
    total: int | None = None
    bytes_done: int = 0
    bytes_total: int | None = None
    seconds_left: int | None = None


# One record per running job, keyed by its thread. _LOCK is held only to read
# or change them. Each report takes the next tick, so `now` can tell which
# record moved last.
_LOCK = threading.Lock()
_held: dict[int, tuple[int, Counted | None]] = {}
_ticks = itertools.count(1)


@contextlib.contextmanager
def job() -> Iterator[None]:
    """The calling thread holds a record while the block runs."""
    me = threading.get_ident()
    with _LOCK:
        _held[me] = (0, None)
    try:
        yield
    finally:
        with _LOCK:
            _held.pop(me, None)


def count(key: str, done: int = 0, total: int | None = None,
          bytes_done: int = 0, bytes_total: int | None = None) -> None:
    """The calling thread's record now says `key` with these numbers. Nothing
    happens on a thread holding no record."""
    me = threading.get_ident()
    with _LOCK:
        if me in _held:
            _held[me] = (next(_ticks), Counted(key, done, total, bytes_done, bytes_total))


def waiting(seconds_left: int | None, key: str) -> None:
    """The calling thread's record keeps its words and numbers and now says
    `seconds_left` remain of a wait; None ends the wait. A record that has
    reported nothing yet says `key`. Nothing happens on a thread holding no
    record."""
    me = threading.get_ident()
    with _LOCK:
        if me in _held:
            counted = _held[me][1] or Counted(key)
            _held[me] = (next(_ticks), replace(counted, seconds_left=seconds_left))


def now() -> Counted | None:
    """The record updated last among those running; None where none has
    reported."""
    with _LOCK:
        reported = [held for held in _held.values() if held[1] is not None]
    return max(reported, key=lambda held: held[0])[1] if reported else None
