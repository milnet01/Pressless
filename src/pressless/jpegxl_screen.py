"""The Face side of JPEG XL support: its line on the list, and the download
-- PRESS-0275 §§ 4.3 and 4.6.

Imported by __main__ alone, as updating.py is. A failed download is held in
memory and shown on the line until the next try; losing it costs nothing.
"""
from __future__ import annotations

import os
from pathlib import Path

from pressless import jpegxl, updater
from pressless.face import Face, Reply, Request
from pressless.words import say


def install(folder: Path, platform: str, transport: updater.Transport | None = None) -> Path:
    """Download this system's decoder into `folder`/extras under the pin's
    name. `updater.download` keeps nothing whose size or hash is not the
    pin's; its failures are raised as they are."""
    pin = jpegxl.PINS[platform]
    beside = Path(folder) / jpegxl.FOLDER_NAME
    beside.mkdir(parents=True, exist_ok=True)
    offer = updater.Offer(version=jpegxl.RELEASE,
                          asset_url=jpegxl.download_url(platform),
                          size=pin.size, sha256=pin.sha256)
    staged = updater.download(offer, beside, transport)
    target = beside / pin.name
    try:
        if platform == "linux":
            staged.chmod(0o700)
        os.replace(staged, target)
    except OSError:
        staged.unlink(missing_ok=True)
        raise
    return target


def register(face: Face, own: Path, *, platform: str | None = None,
             transport: updater.Transport | None = None) -> None:
    """Add the line below the list, and its route. `own` is Pressless's own
    folder."""
    own = Path(own)
    platform = platform or jpegxl.this_system()
    failure: list[str] = []      # the last try's sentence key, until the next

    def add(request: Request) -> Reply:
        failure.clear()
        if jpegxl.installed(own, platform) is None:
            try:
                install(own, platform, transport)
            except updater.DiskFull:
                failure.append("jpegxl.disk_full")
            except updater.UpdateRejected:
                failure.append("jpegxl.rejected")
            except (updater.UpdateError, OSError):
                failure.append("jpegxl.no_connection")
        return Reply(b"", "text/plain", status=303, location="/")

    face.add_page("POST", "/jpeg-xl", add)
    face.add_to_list(lambda: line_html(jpegxl.installed(own, platform) is not None,
                                       jpegxl.PINS[platform].size, failure[:1]),
                     above=False)


def line_html(ready: bool, size: int, failure: list[str]) -> str:
    """§ 4.6: one line, the same height in both states; the button keeps its
    place, unseen and so not clickable, once the decoder is in."""
    words = say("jpegxl.ready") if ready else say("jpegxl.line")
    told = "".join(f'<p class="failure-line">{say(key)}</p>' for key in failure)
    button = say("jpegxl.add", size=f"{size / 1_000_000:.1f}")
    return ('<form method="post" action="/jpeg-xl" id="jpeg-xl" class="switch-row">'
            f'<div class="states"><p>{words}</p>{told}</div>'
            f'<span class="states"><button{" hidden" if ready else ""}>{button}</button>'
            '</span></form>')
