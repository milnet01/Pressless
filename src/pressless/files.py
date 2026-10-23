"""Keeping an uploaded file that is not a photograph (PRESS-0197).

Nine kinds, chosen by suffix and checked by content (§ 4.1), kept byte for
byte in the Store's `files` folder and named by the photographs' rule, which
`photographs.keep` holds for both. The contract is
`docs/specs/PRESS-0197-upload-any-file.md`.
"""
from __future__ import annotations

from pathlib import Path

from pressless import builder, photographs, store

FALLBACK = "file"   # the name of a file whose own name leaves nothing

_MUSIC = (".mp3", ".ogg", ".wav", ".m4a")
_VIDEO = (".mp4", ".webm")

# § 4.1's Chosen by column: what each section's upload box and list offer.
ACCEPT = {"music": ",".join(_MUSIC), "video": ",".join(_VIDEO),
          "download": ",".join((*_MUSIC, *_VIDEO, ".pdf", ".zip", ".txt"))}


class NotAllowed(Exception):
    """The suffix is not one § 4.1 lists, or the bytes are not that kind."""


class TooLarge(Exception):
    """The file is larger than builder.FILE_LARGEST, which its slots state."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.slots = builder.largest_slots()


def add(folder: Path, filename: str, data: bytes) -> str:
    """Keep `data` and return its name, refusing before anything is written.
    The caller holds the editor's lock, as for photographs.add."""
    if len(data) > builder.FILE_LARGEST:
        raise TooLarge(f"{filename!r} is larger than the limit")
    if not builder.file_allowed(filename, data):
        raise NotAllowed(f"{filename!r} is not a kind of file Pressless keeps")
    suffix = "." + filename.rpartition(".")[2].lower()
    name = photographs.plain_name(filename, (suffix,), FALLBACK)
    return photographs.keep(lambda name: store.file_path_for(folder, name), data,
                            lambda staged: name)
