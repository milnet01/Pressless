"""Store and Settings notices, gathered per thread (PRESS-0011 § 4.4).

A notice raised on a thread inside `gathered` joins that block's list. On a
thread outside one it is a warning, as it always was. Per thread, so one
request gathering holds no other: a press's build holds no screen
(PRESS-0463).

This module imports no other part of Pressless, so the Store and Settings
may both raise through it.
"""
from __future__ import annotations

import contextlib
import threading
import warnings
from collections.abc import Iterator

# Each thread's open blocks, innermost last.
_open = threading.local()


@contextlib.contextmanager
def gathered() -> Iterator[list[Warning]]:
    """The notices this thread raises inside the block, innermost block
    only, in the order raised."""
    lists: list[list[Warning]] = _open.__dict__.setdefault("lists", [])
    caught: list[Warning] = []
    lists.append(caught)
    try:
        yield caught
    finally:
        lists.pop()


def notify(notice: Warning, stacklevel: int = 1) -> None:
    """Raise `notice`: into this thread's innermost open block, else as a
    warning, `stacklevel` counted as `warnings.warn` counts it from the
    caller."""
    lists = getattr(_open, "lists", None)
    if lists:
        lists[-1].append(notice)
    else:
        warnings.warn(notice, stacklevel=stacklevel + 1)
