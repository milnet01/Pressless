"""What Pressless remembers of his choices between visits (PRESS-0263).

Kept in choices.json in the open site's folder, unlike theme.json, which is
the machine's. A file rather than the browser's storage for the reason
theme.json is one: the Face's port changes every run, and a browser keeps its
storage per port. Nothing here is sent anywhere. A missing or unreadable file
reads as no choices, and a choice that cannot be written is only forgotten.
"""
from __future__ import annotations

import dataclasses
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from pressless.safe_write import write_whole

FILE_NAME = "choices.json"
_LOCK = threading.Lock()  # two pages opening at once each keep the other's choice


@dataclass(frozen=True)
class Choices:
    page: tuple[str, str] | None = None  # (kind, name) last opened in the page editor
    shown_on: str = ""                   # the page the furniture was last shown on
    view: str = ""                       # the view a page was last switched to
    true_colours: bool = False           # the preview's true-colours switch


def read(folder: Path) -> Choices:
    """The choices held. Each one of the wrong shape reads as not made."""
    try:
        data = json.loads((Path(folder) / FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Choices()
    if not isinstance(data, dict) or data.get("version") != 1:
        return Choices()
    page = data.get("page")
    if not (isinstance(page, list) and len(page) == 2
            and all(isinstance(part, str) and part for part in page)):
        page = None
    shown_on, view = data.get("shown_on"), data.get("view")
    return Choices(page=tuple(page) if page else None,
                   shown_on=shown_on if isinstance(shown_on, str) else "",
                   view=view if isinstance(view, str) else "",
                   true_colours=data.get("true_colours") is True)


def remember(folder: Path, **changes: object) -> bool:
    """Keep `changes` beside the choices already held. False where the file
    could not be written, which costs only the choice."""
    with _LOCK:
        held = dataclasses.replace(read(folder), **changes)
        data = {"version": 1, **dataclasses.asdict(held)}
        try:
            write_whole(Path(folder) / FILE_NAME, json.dumps(data), prefix=f".{FILE_NAME}.")
        except OSError:
            return False
    return True
