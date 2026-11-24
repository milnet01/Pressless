"""What Pressless remembers of his choices between visits (PRESS-0263).

Kept in choices.json in the open site's folder, unlike theme.json, which is
the machine's. A file rather than the browser's storage for the reason
theme.json is one: the Face's port changes every run, and a browser keeps its
storage per port. Nothing here is sent anywhere. A missing or unreadable file
reads as no choices, and a choice that cannot be written is only forgotten.
"""
from __future__ import annotations

import dataclasses
import threading
from dataclasses import dataclass
from pathlib import Path

from pressless import json_record

FILE_NAME = "choices.json"
_LOCK = threading.Lock()  # two pages opening at once each keep the other's choice


@dataclass(frozen=True)
class Choices:
    page: tuple[str, str] | None = None  # (kind, name) last opened in the page editor
    shown_on: str = ""                   # the page the furniture was last shown on
    view: str = ""                       # the view a page was last switched to
    entry_view: str = ""                 # the view an entry was last switched to (PRESS-0346)
    true_colours: bool = False           # the preview's true-colours switch


def read(folder: Path, *, strict: bool = False) -> Choices:
    """The choices held. Each one of the wrong shape reads as not made.
    `strict` raises where the file is there but cannot be read now."""
    data = json_record.read(Path(folder) / FILE_NAME, strict=strict)
    page = data.get("page")
    if not (isinstance(page, list) and len(page) == 2
            and all(isinstance(part, str) and part for part in page)):
        page = None
    shown_on, view, entry_view = data.get("shown_on"), data.get("view"), data.get("entry_view")
    return Choices(page=tuple(page) if page else None,
                   shown_on=shown_on if isinstance(shown_on, str) else "",
                   view=view if isinstance(view, str) else "",
                   entry_view=entry_view if isinstance(entry_view, str) else "",
                   true_colours=data.get("true_colours") is True)


def remember(folder: Path, **changes: object) -> bool:
    """Keep `changes` beside the choices already held. False where the file
    could not be read or written, which costs only the choice."""
    with _LOCK:
        try:
            now = read(folder, strict=True)
            held = dataclasses.replace(now, **changes)
            if held != now:   # PRESS-0492: an unchanged choice waits on no disk
                json_record.write(Path(folder) / FILE_NAME, dataclasses.asdict(held))
        except OSError:
            return False
    return True
