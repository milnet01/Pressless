"""A language whose every entry is its English between markers, so a test
can tell a translated word from English the code wrote itself (PRESS-0241)."""
from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path

from pressless import words

CODE = "zz"
OPEN, CLOSE = "⟦", "⟧"


def write(folder: Path, code: str = CODE, *, name: str = "Zedish") -> Path:
    """A language file at `folder`/`code`.json marking every ENGLISH entry,
    each made from today's English."""
    folder.mkdir(parents=True, exist_ok=True)
    entries = {key: [words.made_from(text), OPEN + text + CLOSE]
               for key, text in words.ENGLISH.items()}
    path = folder / f"{code}.json"
    path.write_text(json.dumps({"name": name, "one": [1], "thousands": ".",
                                "words": entries}, ensure_ascii=False), encoding="utf-8")
    return path


def offered(folder: Path, monkeypatch, code: str = CODE) -> None:
    """Make the marked language one Pressless has, from `folder`."""
    write(folder, code)
    monkeypatch.setattr(words, "FOLDER", folder)
    monkeypatch.setattr(words, "LANGUAGES", (*words.LANGUAGES, code))


@contextlib.contextmanager
def speaking(folder: Path, monkeypatch, code: str = CODE) -> Iterator[None]:
    """The screens in the marked language while the block runs."""
    offered(folder, monkeypatch, code)
    words.choose(code)
    try:
        yield
    finally:
        words.choose("en")
