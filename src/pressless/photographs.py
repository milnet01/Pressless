"""Adding a photograph, and naming the ones Pressless does not have (PRESS-0016).

The Store gives an original its place and the Builder makes the web copy; this
is the one module that puts an original there after Import. Decided by the user
2026-09-27 and recorded on PRESS-0016, which holds the naming rule in place of
a spec (user, 2026-09-29):

- A name is the chosen file's name, lower-cased, reduced to a-z, 0-9, `_` and
  `-`, ending in the suffix its format is served under. So it passes both the
  picture mark's grammar and the Store's check, and a web address needs no
  escaping.
- A name already holding a different photograph keeps both: the new one is
  `name-2`, then `name-3`. The same photograph added twice is kept once.
"""
from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from pathlib import Path

from pressless import builder, marks, store

FALLBACK = "photograph"   # the name of a file whose own name leaves nothing
LONGEST_NAME = 60         # before the suffix, as a new entry's address

# The endings each publishable format is served under, the first the one given
# where the chosen file carries another: a JPEG named .png would be sent to
# browsers as a PNG.
SUFFIXES = {"JPEG": (".jpg", ".jpeg"), "MPO": (".jpg", ".jpeg"), "PNG": (".png",),
            "WEBP": (".webp",), "GIF": (".gif",)}


class NotAPhotograph(Exception):
    """The chosen file is not a picture the Builder publishes."""


def name_for(filename: str, fmt: str) -> str:
    """The name a file chosen as `filename`, in the format `fmt`, is kept under."""
    base = re.split(r"[\\/]", filename)[-1]
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        stem, suffix = base, ""
    suffix = "." + suffix.lower()
    if suffix not in SUFFIXES[fmt]:
        suffix = SUFFIXES[fmt][0]
    return (_plain(stem)[:LONGEST_NAME].strip("-") or FALLBACK) + suffix


def add(folder: Path, filename: str, data: bytes) -> str:
    """Keep `data` as an original and return its name. The caller holds the
    editor's lock, so no other add can take the name between look and write.

    The bytes are written beside the originals first and checked there, so a
    photograph is never half-written under its name and the Builder reads a
    file rather than memory."""
    staged = _stage(store.photograph_path_for(folder, FALLBACK).parent, data)
    try:
        fmt = builder.photograph_format(staged)
        if fmt is None:
            raise NotAPhotograph(f"{filename!r} is not a picture Pressless publishes")
        stem, suffix = os.path.splitext(name_for(filename, fmt))
        number = 1
        while True:
            name = stem + suffix if number == 1 else f"{stem}-{number}{suffix}"
            number += 1
            try:
                target = store.photograph_path_for(folder, name)
            except store.StoreError:
                continue  # a device name such as con.jpg; con-2.jpg is kept
            if target.exists():
                if target.is_file() and target.read_bytes() == data:
                    return name
                continue
            os.replace(staged, target)
            return name
    finally:
        staged.unlink(missing_ok=True)


def missing(folder: Path, body: str) -> list[str]:
    """The photographs `body` names that Pressless does not have, sorted."""
    named = {block.name for block in marks.parse(body) if isinstance(block, marks.Photo)}
    return sorted(named - set(store.list_photographs(folder)))


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9_]+", "-", text.lower()).strip("-")


def _stage(where: Path, data: bytes) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    handle, staged = tempfile.mkstemp(dir=where, prefix=".photograph-")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
    except BaseException:
        Path(staged).unlink(missing_ok=True)
        raise
    return Path(staged)
