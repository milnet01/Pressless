"""The rolling plain-English log (PRESS-0003).

One record of what Pressless did, beside the settings file. The Face writes
it; no other part may, because rule 3 denies Marks a disk and rules 5 and 8
spend the Publisher's and Insights' one disk write elsewhere
(`docs/design.md` § Logging).

Two properties are the whole point. It is bounded: it rolls by size and keeps
exactly one old copy (§4.3). And it never becomes a problem of its own --
every entry point swallows every failure (§4.4), because a log that cannot be
written changes nothing about what Pressless did.

It adds nothing to the message it is given (§5 INV-1). The obligation to keep
a credential, an account name or a full path out of a line belongs to the part
that raises, and for a failure nothing in Pressless raised, to the Face --
`security.md` § 6 is strip before the call, not after.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

FILE_NAME = "pressless.log"

# What RotatingFileHandler names the rolled copy. Stated so PRESS-0011 has a
# name to work from; nothing here constructs it.
OLD_NAME = "pressless.log.1"

MAX_BYTES = 1_048_576
OLD_COPIES = 1

# Never the platform default. That default is the locale's encoding, and a
# line carrying one character outside it is dropped from the file while its
# neighbours are kept -- silently, since §4.4 silences the handler's own error
# path. `errors` covers the narrower gap UTF-8 itself leaves: a str can hold a
# lone surrogate, which an undecodable filename arrives carrying, and that is
# exactly the message class §2 expects to reach here unstripped (§4.3).
ENCODING = "utf-8"
ERRORS = "backslashreplace"

_LINE = "%(asctime)s %(message)s"
_STAMP = "%Y-%m-%d %H:%M:%S"


def path_for(folder: Path) -> Path:
    return Path(folder) / FILE_NAME


class _QuietHandler(logging.handlers.RotatingFileHandler):
    """A rotating handler that says nothing when it fails.

    `logging`'s default prints "--- Logging error ---" and a full traceback to
    stderr, and a traceback quotes absolute paths -- which `docs/design.md`
    § Logging forbids anything Pressless writes down from carrying. So this is
    a leak rather than only noise (§5 INV-6).

    Overridden here rather than through the global `logging.raiseExceptions`
    flag, which is process-wide state: a module setting it would change how
    every other library in the app reports its own failures.
    """

    def handleError(self, record: logging.LogRecord) -> None:
        return


def open_log(folder: Path) -> Log:
    """Open the log in `folder`. Never raises (§5 INV-3).

    Where the folder does not exist or cannot be written, the Log returned
    accepts `note` calls and writes nothing, and the caller cannot tell. It
    does not create the folder: creating it is setup's job, and
    `docs/design.md` § Where everything sits on disk has Pressless stop where
    it cannot be created -- a log that created it would mask that stop.
    """
    try:
        handler = _QuietHandler(
            path_for(folder),
            maxBytes=MAX_BYTES,
            backupCount=OLD_COPIES,
            encoding=ENCODING,
            errors=ERRORS,
        )
        handler.setFormatter(logging.Formatter(_LINE, datefmt=_STAMP))
    except Exception:  # noqa: BLE001 -- §4.4: no failure here is worth a message
        return Log(None)
    return Log(handler)


class Log:
    """A handle the Face holds for the life of the process.

    Not registered with `logging`'s global logger registry: that is
    process-wide state shared with every other library, and this module owns
    one file rather than a logging policy.
    """

    def __init__(self, handler: logging.Handler | None) -> None:
        self._handler = handler

    def note(self, message: str) -> None:
        """Write one line: the timestamp, then `message` unchanged (§5 INV-1).

        Never raises (§5 INV-3). A failed roll is the sharpest case: `emit`
        rolls before it writes, so a roll that fails drops this line and,
        having closed the stream, fails the same way on every later call. The
        record stops and the file stays bounded -- §9 accepts that rather than
        handling it.
        """
        if self._handler is None:
            return
        try:
            self._handler.emit(
                logging.LogRecord(
                    name="pressless",
                    level=logging.INFO,
                    pathname="",
                    lineno=0,
                    msg="%s",
                    args=(message,),
                    exc_info=None,
                )
            )
        except Exception:  # noqa: BLE001 -- §4.4
            return

    def close(self) -> None:
        """Never raises (§5 INV-3). This is the entry point that flushes, so
        it is where a full disk raises."""
        if self._handler is None:
            return
        try:
            self._handler.close()
        except Exception:  # noqa: BLE001 -- §4.4
            return
