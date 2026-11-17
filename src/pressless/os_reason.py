"""An error's reason, without the path it failed on (PRESS-0401).

`str(exc)` on a stock file error quotes the path it failed on, and
`docs/design.md` § Logging forbids a full filesystem path in anything
Pressless shows or writes down. `strerror` is the reason alone.

It is not a part of Pressless: it imports nothing at all, so a module whose
import rule admits it reaches nothing else through it, as with `safe_write`.
"""
from __future__ import annotations


def of(exc: BaseException) -> str:
    """The reason `exc` carries, never its own words.

    An OSError's `strerror`; where it has none, or `exc` is not an OSError,
    the type's name stands in.
    """
    return (exc.strerror if isinstance(exc, OSError) else None) or type(exc).__name__
