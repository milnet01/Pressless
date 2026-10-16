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
from collections.abc import Callable
from pathlib import Path

from pressless import builder, marks, store

FALLBACK = "photograph"   # the name of a file whose own name leaves nothing
LONGEST_NAME = 60         # before the suffix, as a new entry's address

# The endings each publishable format is served under, the first the one given
# where the chosen file carries another: a JPEG named .png would be sent to
# browsers as a PNG.
SUFFIXES = {"JPEG": (".jpg", ".jpeg"), "MPO": (".jpg", ".jpeg"), "PNG": (".png",),
            "WEBP": (".webp",), "GIF": (".gif",), "AVIF": (".avif",)}

# What both upload boxes offer: the types of the formats above (PRESS-0274).
ACCEPT = "image/jpeg,image/png,image/webp,image/gif,image/avif"


class NotAPhotograph(Exception):
    """The chosen file is not a picture the Builder publishes."""


def name_for(filename: str, fmt: str) -> str:
    """The name a file chosen as `filename`, in the format `fmt`, is kept under."""
    return plain_name(filename, SUFFIXES[fmt], FALLBACK)


def plain_name(filename: str, suffixes: tuple[str, ...], fallback: str) -> str:
    """The naming rule above, shared with kept files (PRESS-0197 § 4.2): the
    suffix lower-cased where it is one of `suffixes`, else the first of them."""
    base = re.split(r"[\\/]", filename)[-1]
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        stem, suffix = base, ""
    suffix = "." + suffix.lower()
    if suffix not in suffixes:
        suffix = suffixes[0]
    return (_plain(stem)[:LONGEST_NAME].strip("-") or fallback) + suffix


def add(folder: Path, filename: str, data: bytes) -> str:
    """Keep `data` as an original and return its name. The caller holds the
    editor's lock, so no other add can take the name between look and write."""
    def named(staged: Path) -> str:
        fmt = builder.photograph_format(staged)
        if fmt is None:
            raise NotAPhotograph(f"{filename!r} is not a picture Pressless publishes")
        return name_for(filename, fmt)

    return keep(lambda name: store.photograph_path_for(folder, name), data, named)


def keep(path_for: Callable[[str], Path], data: bytes,
         named: Callable[[Path], str]) -> str:
    """Place `data` under the name `named` gives its staged copy, and return
    the name; shared with kept files (PRESS-0197 § 4.2).

    The bytes are written beside the others first and checked there, so a
    file is never half-written under its name and the Builder reads a file
    rather than memory. A name holding other bytes moves to `-2`, `-3`; the
    same bytes return the name they are kept under."""
    staged = _stage(path_for(FALLBACK).parent, data)
    try:
        stem, suffix = os.path.splitext(named(staged))
        number = 1
        while True:
            name = stem + suffix if number == 1 else f"{stem}-{number}{suffix}"
            number += 1
            try:
                target = path_for(name)
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
