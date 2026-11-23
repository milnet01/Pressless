"""A lock that says when a thread starts to take it, so a test waits for
that instead of for a fixed time, which a loaded machine can outrun."""

from __future__ import annotations

import threading


class Signalled:
    """`lock`, setting `trying` each time a thread starts to take it."""

    def __init__(self, lock: threading.Lock | None = None,
                 trying: threading.Event | None = None) -> None:
        self.lock = lock or threading.Lock()
        self.trying = trying or threading.Event()

    def locked(self) -> bool:
        return self.lock.locked()

    def __enter__(self) -> None:
        self.trying.set()
        self.lock.acquire()

    def __exit__(self, *exc: object) -> None:
        self.lock.release()
