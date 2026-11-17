"""Whether a zip member's name stays inside the folder it is unpacked into
(PRESS-0409).

The Updater, a saved site (PRESS-0224 § 4.3) and Import's ZIPs (PRESS-0125
§ 4.4, PRESS-0210 § 4.1) all check members by it. It is not a part of
Pressless: it imports none, so the Updater reaches nothing else through it.
"""
from __future__ import annotations

from pathlib import PurePosixPath


def stays_inside(name: str) -> bool:
    """A zip member name that stays inside the folder it is unpacked into, on
    every system: relative, with no backslash, and no part that is `..`,
    holds a `:` or ends in a dot or space. Each part is checked, as Windows
    starts a path again at a part such as `D:x`, and drops a part's trailing
    dots and spaces, so `.. ` climbs out."""
    if name.startswith("/") or "\\" in name:
        return False
    parts = PurePosixPath(name).parts
    return bool(parts) and not any(
        part == ".." or ":" in part or part[-1] in ". " for part in parts)
