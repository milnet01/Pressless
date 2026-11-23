"""The Face side of JPEG XL support: its line on the list, and the download
-- PRESS-0275 §§ 4.3 and 4.6.

Imported by __main__ alone, as updating.py is. A failed download is held in
memory and shown on the line until the next try; losing it costs nothing.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from pressless import jpegxl, updater
from pressless.face import Face, Reply, Request
from pressless.words import say


def install(folder: Path, platform: str, transport: updater.Transport | None = None) -> Path:
    """Download this system's decoder into `folder`/extras under the pin's
    name. `updater.download` keeps nothing whose size or hash is not the
    pin's; its failures are raised as they are, and this function's own
    steps fail as DiskFull or DownloadFailed too (§ 4.3)."""
    pin = jpegxl.PINS[platform]
    beside = Path(folder) / jpegxl.FOLDER_NAME
    try:
        beside.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise updater.download_failure(exc, "the extras folder could not be made") from exc
    offer = updater.Offer(version=jpegxl.RELEASE,
                          asset_url=jpegxl.download_url(platform),
                          size=pin.size, sha256=pin.sha256)
    staged = updater.download(offer, beside, transport)
    target = beside / pin.name
    try:
        if platform == "linux":
            staged.chmod(0o700)
        os.replace(staged, target)
    except OSError as exc:
        staged.unlink(missing_ok=True)
        raise updater.download_failure(exc, "the decoder could not be put in place") from exc
    return target


def register(face: Face, own: Path, *, platform: str | None = None,
             transport: updater.Transport | None = None) -> None:
    """Add the line to Settings' place for this computer, and its route. `own` is Pressless's own
    folder."""
    own = Path(own)
    platform = platform or jpegxl.this_system()
    if platform is None:
        face.add_piece("computer", no_decoder_html)
        return
    failure: list[str] = []      # the last try's sentence key, until the next
    # One Add at a time: a second click waits, then finds the decoder in.
    adding = threading.Lock()

    def add(request: Request) -> Reply:
        with adding:
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
        return Reply(b"", "text/plain", status=303, location="/setup/computer")

    face.add_page("POST", "/jpeg-xl", add)
    face.add_piece("computer", lambda: line_html(jpegxl.installed(own, platform) is not None,
                                                 jpegxl.PINS[platform].size, failure[:1]))


def no_decoder_html() -> str:
    """§ 6: the line where no pin runs on this computer, with no button."""
    return (f'<div id="jpeg-xl" class="switch-row"><div class="states">'
            f'<p>{say("jpegxl.no_decoder")}</p></div></div>')


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
