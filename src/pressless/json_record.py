"""A small JSON file Pressless keeps for itself, marked with its version
(PRESS-0398).

Every small JSON file Pressless keeps for itself is one object carrying
`"version": 1`; a search for `json_record.read` and `json_record.write` finds
them all. They are read and written here, so they read alike: a file this
Pressless did not write reads as no fields, never as a guess at them.

It imports no part of Pressless but `safe_write`, which imports none, so a
module whose import rule admits `safe_write` reaches nothing else through it.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from pressless.safe_write import write_whole

VERSION = 1


def read(path: Path, *, strict: bool = False) -> dict:
    """The file's fields, `version` included, as this Pressless wrote them.

    A missing file, one that is not a JSON object, and one of another
    version -- a newer Pressless's included, as downgrades are not supported
    -- read as {}. So does a file that is there but cannot be read now,
    unless `strict`: then its OSError is raised, so a merging write never
    replaces what the file holds with only the new fields.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    except OSError:
        if strict:
            raise
        return {}
    return data if isinstance(data, dict) and data.get("version") == VERSION else {}


def write(path: Path, fields: Mapping[str, object]) -> None:
    """Replace the file whole with `fields` and the version, written last so
    no field can mark the file with another. An OSError is the caller's."""
    path = Path(path)
    text = json.dumps({**fields, "version": VERSION}, indent=2) + "\n"
    write_whole(path, text, prefix=f".{path.name}.")
