"""The Face side of updating: the offer, the switch, Update now -- PRESS-0023 § 4.9.

The check runs once per process, in the background, when a packaged Pressless
starts. What it finds is held in memory for the life of the process, as is a
Later. A Restart, or opening another site, serves a new Face in the same
process, and __main__ registers it against the same Updates. Losing them costs
one check at the next start, and nothing of his is in them. Skip and the switch
are written to updates.json.

Imported by __main__ alone. Your site draws the offer, and Settings the switch,
through Face.add_piece; neither imports this module.
"""
from __future__ import annotations

import contextlib
import html
import os
import re
import shutil
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from pressless import __version__, editor, installer, paths, updater
from pressless.face import SENTENCES, Face, Reply, Request, Sentence, Site
from pressless.words import say

# § 4.10. The base carries the generic sentence; each type below it its own.
SENTENCES[installer.UpdateError] = Sentence(
    "failure.installer.UpdateError.what", Site.UNCHANGED,
    "failure.installer.UpdateError.next")
SENTENCES[updater.DownloadFailed] = Sentence(
    "failure.updater.DownloadFailed.what", Site.UNCHANGED,
    "failure.updater.DownloadFailed.next")
SENTENCES[updater.DiskFull] = Sentence(
    "failure.updater.DiskFull.what",
    Site.UNCHANGED,
    "failure.updater.DiskFull.next")
SENTENCES[updater.DownloadEndedEarly] = Sentence(
    "failure.updater.DownloadEndedEarly.what", Site.UNCHANGED,
    "failure.updater.DownloadEndedEarly.next")
SENTENCES[updater.UpdateRejected] = Sentence(
    "failure.updater.UpdateRejected.what",
    Site.UNCHANGED,
    "failure.updater.UpdateRejected.next")
SENTENCES[installer.InstallFailed] = Sentence(
    "failure.installer.InstallFailed.what",
    Site.UNCHANGED,
    "failure.installer.InstallFailed.next")

# Replaced by the tests, which must not end the process running them.
_exit = os._exit


def miss_line(miss: updater.Miss) -> str:
    """The log line for a check that stopped: the step, never a URL or a path."""
    return f"The update check stopped at step {miss.step}."


class Updates:
    """What this process knows: the offer, and whether Later was chosen. One
    per process; each Face it serves is registered against it."""

    def __init__(self) -> None:
        self.offer: updater.Offer | None = None
        self.later = False
        # Taken when an Update now starts; only its failure lets it go.
        self.busy = threading.Lock()
        # The Face now served: a check that ends after a Restart notes to it.
        self.face: Face | None = None
        # The AppImage a Linux Update now put in place, and its version.
        # __main__ opens it in this process's place once the Face has stopped
        # (PRESS-0408).
        self.installed: tuple[Path, str] | None = None
        self._thread: threading.Thread | None = None

    def wait(self, timeout: float | None = None) -> None:
        """Until the check has finished. Where no check runs, at once."""
        if self._thread is not None:
            self._thread.join(timeout)


def register(face: Face, own: Path, *, artefact: Path | None = None,
             platform: str | None = None, running: str = __version__,
             transport: updater.Transport | None = None,
             state: Updates | None = None,
             stop: Callable[[], None] = lambda: _exit(0)) -> Updates:
    """Add the offer, the switch and their routes to `face`, and start the
    check where this is a packaged run. `own` is Pressless's own folder.

    `state` is what an earlier Face of this process registered against: its
    offer and Later stand, and its check is not started again. `stop` ends
    this Face once a Linux Update now's page is sent; __main__'s then opens
    the new version in this process's place (PRESS-0408)."""
    own = Path(own)
    if artefact is None:
        try:
            artefact = paths.artefact_path()
        except paths.NotPackaged:
            artefact = None
    platform = platform or ("windows" if sys.platform == "win32" else "linux")
    state = Updates() if state is None else state
    state.face = face

    def shown() -> updater.Offer | None:
        offer = state.offer
        if offer is None or state.later or updater.read_state(own).skip == offer.version:
            return None
        return offer

    def later(request: Request) -> Reply:
        state.later = True
        return _home()

    def skip(request: Request) -> Reply:
        offer = shown()
        if offer is not None:
            updater.write_state(own, check=updater.read_state(own).check, skip=offer.version)
        return _home()

    def checking(request: Request) -> Reply:
        form = request.form()
        wanted = (form.get("check") or ["true"])[0] != "false"
        updater.write_state(own, check=wanted, skip=updater.read_state(own).skip)
        return Reply(b"", "text/plain", status=303, location="/setup/computer")  # the switch

    def update_now(request: Request) -> str | Reply:
        offer = shown()
        # One at a time: a second click, or a second tab, goes home rather
        # than downloading beside the first.
        if offer is None or artefact is None or not state.busy.acquire(blocking=False):
            return _home()
        return _update_now(face, own, offer, artefact, platform, transport, state, stop)

    face.add_page("POST", "/update", update_now)
    face.add_page("POST", "/update/later", later)
    face.add_page("POST", "/update/skip", skip)
    face.add_page("POST", "/update/checking", checking)
    face.add_piece("site-notices", lambda: _offer_html(shown(), running))
    face.add_piece("computer", lambda: _switch_html(updater.read_state(own).check))

    if artefact is not None and state._thread is None:
        _clear_leftovers(artefact.parent)

        def look() -> None:
            found = updater.check(own, running, platform, transport)
            if isinstance(found, updater.Offer):
                state.offer = found
            # Step 1 is the switch being off, which is no failure (PRESS-0023
            # § 4.4); every other step stopped a check that was wanted.
            elif found.step > 1 and state.face is not None:
                state.face.note(miss_line(found))

        state._thread = threading.Thread(target=look, name="pressless-update-check",
                                         daemon=True)
        state._thread.start()
    return state


def _clear_leftovers(beside: Path) -> None:
    """Remove what an update stopped part way left beside the program: a
    download or an unpacked folder, from a Pressless stopped during either,
    and a Windows helper's script, from a helper that died. Run once per
    process, before its check, so it never meets this process's own update.
    Best effort: what stays is tried again at the next start."""
    try:
        found = list(Path(beside).iterdir())
    except OSError:
        return
    for path in found:
        name = path.name
        if name.startswith(updater.UNPACK_PREFIX):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
        elif name.startswith(updater.DOWNLOAD_PREFIX) or (
                name.startswith(installer.SCRIPT_PREFIX) and name.endswith(".ps1")):
            with contextlib.suppress(OSError):
                path.unlink()


def _home() -> Reply:
    return Reply(b"", "text/plain", status=303, location="/")


def _offer_html(offer: updater.Offer | None, running: str) -> str:
    if offer is None:
        return ""
    buttons = "".join(
        f'<form method="post" action="{action}" style="display:inline">'
        f"<button>{say(key)}</button></form> "
        for action, key in (("/update", "updating.update_now"),
                            ("/update/later", "updating.later"),
                            ("/update/skip", "updating.skip")))
    words = say("updating.offer", version=html.escape(offer.version))
    # Below the buttons, so opening it moves none of them.
    return (f'<section id="update"><p>{words}</p>{buttons}'
            f"{_changes_html(offer.changes, running)}</section>")


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_ITEM_ID = re.compile(r" \([A-Z]+-[0-9]+(?:, [A-Z]+-[0-9]+)*\)")


def _changes_html(changes: tuple[tuple[str, str], ...], running: str) -> str:
    """§ 4.12: every release since `running`, folded shut under one line."""
    if not changes:
        return ""
    releases = "".join(
        f'<h3>{say("updating.changes.version", version=html.escape(version))}</h3>'
        f"{_release_html(text)}" for version, text in changes)
    summary = say("updating.changes", version=html.escape(running))
    return f"<details><summary>{summary}</summary>{releases}</details>"


def _release_html(text: str) -> str:
    """One release's changelog text as headings, lists and paragraphs. The
    text is escaped first; the only marks read after that are the changelog's
    own: a `###` heading, a `- ` item, and `**bold**`."""
    blocks: list[tuple[str, str]] = []   # (tag, words)
    for line in text.splitlines():
        words = html.escape(_LINK.sub(r"\1", line.strip()), quote=False)
        if not words:
            blocks.append(("", ""))
        elif line.startswith("### "):
            blocks.append(("h4", words.removeprefix("### ")))
        elif line.startswith("- "):
            blocks.append(("li", words.removeprefix("- ")))
        elif blocks and blocks[-1][0] in ("li", "p"):
            blocks[-1] = (blocks[-1][0], f"{blocks[-1][1]} {words}")
        else:
            blocks.append(("p", words))
    # Once a block is whole: an item's ids and its bold may run over a line end.
    out = ""
    for tag, words in blocks:
        if tag:
            words = _BOLD.sub(r"<strong>\1</strong>", _ITEM_ID.sub("", words))
            out += f"<{tag}>{words}</{tag}>"
    # Each run of items becomes one list.
    return re.sub(r"(?:<li>.*?</li>)+", lambda run: f"<ul>{run.group(0)}</ul>", out)


def _switch_html(checking: bool) -> str:
    words, value, label = (
        ("updating.checking", "false", "updating.stop_looking")
        if checking else
        ("updating.not_checking", "true", "updating.look"))
    return ('<form method="post" action="/update/checking" id="update-switch" '
            f'class="switch-row"><p>{say(words)}</p>'
            f'<input type="hidden" name="check" value="{value}">'
            f"<button>{say(label)}</button></form>")


def _update_now(face: Face, own: Path, offer: updater.Offer, artefact: Path,
                platform: str, transport: updater.Transport | None,
                state: Updates, stop: Callable[[], None]) -> str:
    """§ 4.9's five steps, holding `state.busy`, which only a failure
    releases."""
    going = False
    try:
        try:
            staged = updater.download(offer, artefact.parent, transport)
            if platform == "windows":
                staged = updater.unpack(staged, artefact.parent)
        except installer.UpdateError as exc:
            return face.fail(exc, publishing=False)

        # Never released on the success path: no save or publish may start
        # between the swap and this process's end.
        editor.LOCK.acquire()
        try:
            if platform == "windows":
                installer.apply_windows(artefact, staged, own)
            else:
                installer.apply_linux(artefact, staged, own)
        except installer.UpdateError as exc:
            editor.LOCK.release()
            return face.fail(exc, publishing=False)
        except BaseException:
            editor.LOCK.release()
            raise
        going = True
    finally:
        if not going:
            state.busy.release()

    if platform == "windows":
        # Start Pressless.bat ends with `pause`, so the old console stays open
        # once this process has gone (scripts/build-windows.sh).
        print(say("updating.console"), flush=True)
        face.after_reply(lambda: _exit(0))
    else:
        state.installed = (artefact, offer.version)
        face.after_reply(stop)
    return f'<p>{say("updating.installing", version=html.escape(offer.version))}</p>'
