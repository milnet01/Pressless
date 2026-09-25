"""The Face side of updating: the offer, the switch, Update now -- PRESS-0023 § 4.9.

The check runs once, in the background, when a packaged Pressless starts. What
it finds is held in memory for the life of the process, as is a Later: losing
either costs one check at the next start, and nothing of his is in them. Skip
and the switch are written to updates.json.

Imported by __main__ alone. The editor draws the offer and the switch through
Face.add_to_list and never imports this module.
"""
from __future__ import annotations

import html
import os
import sys
import threading
import urllib.parse
from pathlib import Path

from pressless import __version__, editor, installer, paths, updater
from pressless.face import SENTENCES, Face, Reply, Request, Sentence, Site

# § 4.10. The base carries the generic sentence; each type below it its own.
SENTENCES[installer.UpdateError] = Sentence(
    "Pressless could not update itself.", Site.UNCHANGED,
    "Keep using this version, and try again later.")
SENTENCES[updater.DownloadFailed] = Sentence(
    "Pressless could not download the new version.", Site.UNCHANGED,
    "Check your internet connection and click Update now again.")
SENTENCES[updater.DownloadEndedEarly] = Sentence(
    "The download stopped before it finished.", Site.UNCHANGED,
    "Click Update now again.")
SENTENCES[updater.UpdateRejected] = Sentence(
    "The download did not prove it came from Pressless, so nothing was installed.",
    Site.UNCHANGED,
    "Keep using this version, and send the details below to whoever helps you.")
SENTENCES[installer.InstallFailed] = Sentence(
    "Pressless could not put the new version in place. This version is still installed.",
    Site.UNCHANGED,
    "Try again later. If it keeps happening, send the details below to whoever helps you.")

_UPDATING_CONSOLE = "Pressless is updating. You can close this window."

# Replaced by the tests, which must not end the process running them.
_exit = os._exit


def miss_line(miss: updater.Miss) -> str:
    """The log line for a check that stopped: the step, never a URL or a path."""
    return f"The update check stopped at step {miss.step}."


class Updates:
    """What this process knows: the offer, and whether Later was chosen."""

    def __init__(self) -> None:
        self.offer: updater.Offer | None = None
        self.later = False
        self._thread: threading.Thread | None = None

    def wait(self, timeout: float | None = None) -> None:
        """Until the check has finished. Where no check runs, at once."""
        if self._thread is not None:
            self._thread.join(timeout)


def register(face: Face, folder: Path, *, artefact: Path | None = None,
             platform: str | None = None, running: str = __version__,
             transport: updater.Transport | None = None) -> Updates:
    """Add the offer, the switch and their routes to `face`, and start the
    check where this is a packaged run. `folder` is Pressless's own folder."""
    folder = Path(folder)
    if artefact is None:
        try:
            artefact = paths.artefact_path()
        except paths.NotPackaged:
            artefact = None
    platform = platform or ("windows" if sys.platform == "win32" else "linux")
    state = Updates()

    def shown() -> updater.Offer | None:
        offer = state.offer
        if offer is None or state.later or updater.read_state(folder)[1] == offer.version:
            return None
        return offer

    def later(request: Request) -> Reply:
        state.later = True
        return _home()

    def skip(request: Request) -> Reply:
        offer = shown()
        if offer is not None:
            updater.write_state(folder, check=updater.read_state(folder)[0], skip=offer.version)
        return _home()

    def checking(request: Request) -> Reply:
        form = urllib.parse.parse_qs(request.body.decode("utf-8", "replace"))
        wanted = (form.get("check") or ["true"])[0] != "false"
        updater.write_state(folder, check=wanted, skip=updater.read_state(folder)[1])
        return _home()

    def update_now(request: Request) -> str | Reply:
        offer = shown()
        if offer is None or artefact is None:
            return _home()
        return _update_now(face, folder, offer, artefact, platform, transport)

    face.add_page("POST", "/update", update_now)
    face.add_page("POST", "/update/later", later)
    face.add_page("POST", "/update/skip", skip)
    face.add_page("POST", "/update/checking", checking)
    face.add_to_list(lambda: _offer_html(shown()), above=True)
    face.add_to_list(lambda: _switch_html(updater.read_state(folder)[0]), above=False)

    if artefact is not None:
        def look() -> None:
            found = updater.check(folder, running, platform, transport)
            if isinstance(found, updater.Offer):
                state.offer = found
            elif found.step > 1:
                face.note(miss_line(found))

        state._thread = threading.Thread(target=look, name="pressless-update-check",
                                         daemon=True)
        state._thread.start()
    return state


def _home() -> Reply:
    return Reply(b"", "text/plain", status=303, location="/")


def _offer_html(offer: updater.Offer | None) -> str:
    if offer is None:
        return ""
    buttons = "".join(
        f'<form method="post" action="{action}" style="display:inline">'
        f"<button>{label}</button></form> "
        for action, label in (("/update", "Update now"), ("/update/later", "Later"),
                              ("/update/skip", "Skip this version")))
    return (f'<section id="update"><p>Pressless {html.escape(offer.version)} is ready to '
            f"install. Your writing stays where it is.</p>{buttons}</section>")


def _switch_html(checking: bool) -> str:
    words, value, label = (
        ("Pressless looks for a new version each time it starts.", "false", "Stop looking")
        if checking else
        ("Pressless does not look for new versions.", "true", "Look when Pressless starts"))
    return ('<form method="post" action="/update/checking" id="update-switch"><p>'
            f'{words} <input type="hidden" name="check" value="{value}">'
            f"<button>{label}</button></p></form>")


def _update_now(face: Face, folder: Path, offer: updater.Offer, artefact: Path,
                platform: str, transport: updater.Transport | None) -> str:
    """§ 4.9's five steps."""
    try:
        staged = updater.download(offer, artefact.parent, transport)
        if platform == "windows":
            staged = updater.unpack(staged, artefact.parent)
    except installer.UpdateError as exc:
        return face.fail(exc, publishing=False)

    # Never released on the success path: no save or publish may start
    # between the swap and the exit.
    editor.LOCK.acquire()
    try:
        if platform == "windows":
            installer.apply_windows(artefact, staged, folder)
            started = True
        else:
            started = installer.apply_linux(artefact, staged, folder)
    except installer.UpdateError as exc:
        editor.LOCK.release()
        return face.fail(exc, publishing=False)
    except BaseException:
        editor.LOCK.release()
        raise

    if platform == "windows":
        print(_UPDATING_CONSOLE, flush=True)
    face.after_reply(lambda: _exit(0))
    version = html.escape(offer.version)
    if not started:
        return (f"<p>Pressless is updated to version {version} but could not open again "
                "by itself. Close its window and start it again.</p>")
    return (f"<p>Pressless is installing version {version} and will open again by itself "
            "in a moment. You can close this tab.</p>")
