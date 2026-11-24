"""The Face (PRESS-0011): the local server, and the error contract.

The contract is docs/specs/PRESS-0011-face.md. Two jobs, and they are one job:
this is the web server on his own machine that his browser talks to, and it is
the one place a failure any part raises becomes a sentence he understands
(`docs/design.md` § Errors). Every part raises typed failures and writes no
prose; the sentences live here, keyed by the failure's class, and their words
in the words table (PRESS-0242).

Nothing here keeps state between requests (`docs/design.md` § State) beyond
what the server itself needs: its link's secret, which `fresh_link` replaces,
and whether that link is spent; the session a restart hands on, and whether a
tab came back; the pages later items add; the log it holds open; and the
choices a request may change: theme, text size and language.
"""

from __future__ import annotations

import contextlib
import enum
import hashlib
import html
import http.server
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TypeVar

from pressless import (
    blocks,
    builder,
    choices,
    credentials,
    face_scripts,
    face_style,
    github_signin,
    google_signin,
    insights,
    languages,
    log,
    look,
    os_reason,
    paths,
    progress,
    publisher,
    sendlog,
    settings,
    shortcuts,
    sites,
    store,
    themes,
    usage,
    words,
)
from pressless.notices import gathered
from pressless.words import say


class Site(enum.Enum):
    """Each value is a key in the words table (PRESS-0242)."""
    UNCHANGED = "site.unchanged"
    UNKNOWN = "site.unknown"
    UPDATED = "site.updated"  # a notice's only (§ 4.4)

    @property
    def words(self) -> str:
        return say(self.value)


@dataclass(frozen=True)
class Sentence:
    """In SENTENCES each part is a key in the words table; `sentence_for`
    returns the same shape holding the words (PRESS-0242)."""
    what: str  # what happened, in his words; may hold the "{secret}" slot
    site: Site  # what it means for his site
    next: str  # what to do next
    link: tuple[str, str] | None = None  # a fixed page and its label, after `next`


@dataclass(frozen=True)
class Notice:
    """A notice a part adds about a publish, with its own site part (§ 4.4).
    A captured Store or Settings notice is a plain string: those calls never
    touch the site (PRESS-0145)."""
    text: str
    site: Site = Site.UNCHANGED


class FolderNotOpened(Exception):
    """The platform's opener is missing or failed (§ 6)."""


class NoRoom(Exception):
    """An upload would leave the drive less than _SPARE free, or its free
    space cannot be read (PRESS-0224 § 4.5)."""


def _keys(what: str, next_step: str, *, site: Site = Site.UNCHANGED,
          link: tuple[str, str] | None = None) -> Sentence:
    """A SENTENCES entry: it holds words keys, which sentence_for looks up.
    `site` is keyword-only: Sentence takes it second, this takes it third."""
    return Sentence(what, site, next_step, link)


# Keyed by the class object, never its name: publisher and insights both define
# Unreachable, Refused and RateLimited (§ 4.2). Each Publisher type's next step
# follows the answer PRESS-0009 § 4.1 pairs with it.
SENTENCES: dict[type[Exception], Sentence] = {
    paths.NotPackaged: _keys(
        "failure.paths.NotPackaged.what",
        "failure.paths.NotPackaged.next",
    ),
    paths.FolderUnusable: _keys(
        "failure.paths.FolderUnusable.what",
        "failure.paths.FolderUnusable.next",
    ),
    store.StoreError: _keys("failure.store.StoreError.what", "failure.again"),
    store.EntryNotFound: _keys(
        "failure.store.EntryNotFound.what",
        "failure.store.EntryNotFound.next",
    ),
    store.SlugInUse: _keys(
        "failure.store.SlugInUse.what",
        "failure.store.SlugInUse.next",
    ),
    store.DanglingReply: _keys(
        "failure.store.DanglingReply.what",
        "failure.store.DanglingReply.next",
    ),
    # Here rather than in look_screen.py, so no import order decides it.
    look.LookUnreadable: _keys(
        "failure.look.LookUnreadable.what",
        "failure.look.LookUnreadable.next",
    ),
    blocks.SectionRefused: _keys("failure.blocks.SectionRefused.what", "failure.again"),
    builder.BuildStopped: _keys(
        "failure.builder.BuildStopped.what",
        "failure.builder.BuildStopped.next",
    ),
    builder.SiteFolderUnusable: _keys(
        "failure.builder.SiteFolderUnusable.what",
        "failure.again",
    ),
    insights.InsightsError: _keys(
        "failure.insights.InsightsError.what",
        "failure.insights.InsightsError.next",
    ),
    insights.NotConfigured: _keys(
        "failure.insights.NotConfigured.what",
        "failure.insights.NotConfigured.next",
    ),
    insights.Unreachable: _keys(
        "failure.insights.Unreachable.what",
        "failure.insights.Unreachable.next",
    ),
    insights.Refused: _keys(
        "failure.insights.Refused.what",
        "failure.insights.Refused.next",
    ),
    insights.RateLimited: _keys(
        "failure.insights.RateLimited.what",
        "failure.insights.RateLimited.next",
    ),
    google_signin.Declined: _keys(
        "failure.google_signin.Declined.what",
        "failure.google_signin.Declined.next",
    ),
    google_signin.Expired: _keys(
        "failure.google_signin.Expired.what",
        "failure.google_signin.Expired.next",
    ),
    credentials.NoStore: _keys(
        "failure.credentials.NoStore.what",
        "failure.credentials.NoStore.next",
    ),
    credentials.NotStored: _keys(
        "failure.credentials.NotStored.what",
        "failure.credentials.NotStored.next",
    ),
    # Setup's store step and first save raise this too, where nothing was
    # read and re-entering fixes nothing -- a locked keyring, or on Windows a
    # program started over a remote connection, which the vault refuses
    # (PRESS-0120, PRESS-0162). So it names reaching, and the unlock first.
    credentials.CredentialError: _keys(
        "failure.credentials.CredentialError.what",
        "failure.credentials.CredentialError.next",
    ),
    settings.NotSetUp: _keys(
        "failure.settings.NotSetUp.what",
        "failure.settings.NotSetUp.next",
    ),
    settings.SettingsError: _keys(
        "failure.settings.SettingsError.what",
        "failure.settings.SettingsError.next",
    ),
    publisher.PublishError: _keys(
        "failure.publisher.PublishError.what",
        "failure.again",
    ),
    publisher.Unreachable: _keys(
        "failure.publisher.Unreachable.what",
        "failure.publisher.Unreachable.next",
    ),
    publisher.OutcomeUnknown: _keys(
        "failure.publisher.OutcomeUnknown.what",
        "failure.publisher.OutcomeUnknown.next",
        site=Site.UNKNOWN,
    ),
    publisher.Refused: _keys(
        "failure.publisher.Refused.what",
        "failure.publisher.Refused.next",
    ),
    publisher.SignInRefused: _keys(
        "failure.publisher.SignInRefused.what",
        "failure.publisher.SignInRefused.next",
        link=("/setup/github", "failure.publisher.SignInRefused.link"),
    ),
    publisher.RepositoryMissing: _keys(
        "failure.publisher.RepositoryMissing.what",
        "failure.publisher.RepositoryMissing.next",
    ),
    publisher.Conflict: _keys(
        "failure.publisher.Conflict.what",
        "failure.publisher.Conflict.next",
    ),
    publisher.TooLarge: _keys(
        "failure.publisher.TooLarge.what",
        "failure.publisher.TooLarge.next",
    ),
    publisher.RateLimited: _keys(
        "failure.publisher.RateLimited.what",
        "failure.publisher.RateLimited.next",
    ),
    publisher.NoPreviousState: _keys(
        "failure.publisher.NoPreviousState.what",
        "failure.publisher.NoPreviousState.next",
    ),
    publisher.SiteFolderMissing: _keys(
        "failure.publisher.SiteFolderMissing.what",
        "failure.publisher.SiteFolderMissing.next",
    ),
    publisher.StrayFile: _keys(
        "failure.publisher.StrayFile.what",
        "failure.publisher.StrayFile.next",
    ),
    publisher.SiteWouldBeEmptied: _keys(
        "failure.publisher.SiteWouldBeEmptied.what",
        "failure.publisher.SiteWouldBeEmptied.next",
    ),
    publisher.FetchNotWritten: _keys(
        "failure.publisher.FetchNotWritten.what",
        "failure.publisher.FetchNotWritten.next",
    ),
    publisher.UnfetchablePath: _keys(
        "failure.publisher.UnfetchablePath.what",
        "failure.publisher.UnfetchablePath.next",
    ),
    publisher.RepositoryMoved: _keys(
        "failure.publisher.RepositoryMoved.what",
        "failure.publisher.RepositoryMoved.next",
    ),
    publisher.RemoteStateMissing: _keys(
        "failure.publisher.RemoteStateMissing.what",
        "failure.publisher.RemoteStateMissing.next",
    ),
    # PRESS-0231 § 4.2. The sign-in step words the first three as hints; these
    # are for anywhere else they reach.
    github_signin.Pending: _keys(
        "failure.github_signin.Pending.what",
        "failure.github_signin.Pending.next",
    ),
    github_signin.Expired: _keys(
        "failure.github_signin.Expired.what",
        "failure.github_signin.Expired.next",
    ),
    github_signin.Declined: _keys(
        "failure.github_signin.Declined.what",
        "failure.github_signin.Declined.next",
    ),
    github_signin.SignedOut: _keys(
        "failure.github_signin.SignedOut.what",
        "failure.github_signin.SignedOut.next",
        link=("/setup/github", "failure.github_signin.SignedOut.link"),
    ),
    FolderNotOpened: _keys(
        "failure.face.FolderNotOpened.what",
        "failure.face.FolderNotOpened.next",
    ),
    NoRoom: _keys("failure.face.NoRoom.what", "failure.face.NoRoom.next"),
    shortcuts.ShortcutError: _keys(
        "failure.shortcuts.ShortcutError.what",
        "failure.again",
    ),
    sendlog.LogNotSent: _keys(
        "failure.sendlog.LogNotSent.what",
        "failure.sendlog.LogNotSent.next",
    ),
}


def sentence_for(
    failure: BaseException, *, publishing: bool, secret: str | None = None
) -> Sentence:
    """The failure's own type's sentence, never a base's (§ 4.2).

    A subclass with no entry is unforeseen: a base's sentence is written for no
    situation in particular. An unforeseen failure while publishing says the
    outcome is unknown, because the Face cannot tell whether the site moved.
    The sentence returned holds words, its keys looked up now.
    """
    entry = SENTENCES.get(type(failure))
    unforeseen = Sentence(say("failure.unforeseen.what"),
                          Site.UNKNOWN if publishing else Site.UNCHANGED,
                          say("failure.unforeseen.next"))
    if entry is None:
        return unforeseen
    try:
        link = (entry.link[0], say(entry.link[1])) if entry.link else None
        # A failure may carry the words for its sentence's gaps. The secret is
        # the one the Face names, else the failure's own, else "that secret".
        slots = dict(getattr(failure, "slots", {}))
        slots["secret"] = secret or slots.get("secret") or say("failure.unnamed_secret")
        return Sentence(say(entry.what, **slots), entry.site, say(entry.next, **slots), link)
    except Exception:  # noqa: BLE001 -- the last-resort catch runs this
        # A gap the failure left unfilled, or slots of the wrong shape.
        # Raising here would leave him with no answer at all.
        return unforeseen


def details_for(failure: BaseException) -> str:
    """What Show details holds and the log records (§ 4.3).

    A typed failure's type and its own words, which the part that raised kept
    free of a credential, an account name and a full path; an Insights
    failure's detail beside them. An unforeseen failure's type alone, since a
    stock file error quotes the path it failed on. Never a cause, a context, a
    traceback or a frame's locals.
    """
    kind = type(failure)
    if kind not in SENTENCES:
        return kind.__qualname__
    text = f"{kind.__module__}.{kind.__qualname__}: {failure}"
    if isinstance(failure, insights.InsightsError) and failure.detail:
        text += "\n" + failure.detail
    return text


def said_decimal(value: float) -> str:
    """`value` to one decimal, marked as the language in use marks a
    decimal (`words.decimal`)."""
    return words.decimal(value, 1)


def _said_bytes(count: int) -> str:
    """`count` bytes in KB, MB or GB to one decimal (`said_decimal`)."""
    value, unit = count / 1024, "KB"
    for bigger in ("MB", "GB"):
        if value < 1024:
            break
        value, unit = value / 1024, bigger
    return said_decimal(value) + f" {unit}"


def progress_said(counted: progress.Counted) -> dict:
    """GET /progress's answer for a running job (PRESS-0435 § 4.3): its words,
    with each number not known left out, and how far it has got, as a
    fraction, where that is known."""
    parts = []
    if counted.total is not None:
        parts.append(say("progress.of", done=words.number(counted.done),
                         total=words.number(counted.total)))
    elif counted.done:
        parts.append(say("progress.so_far", done=words.number(counted.done)))
    if counted.bytes_total is not None:
        parts.append(say("progress.size_of", size=_said_bytes(counted.bytes_done),
                         whole=_said_bytes(counted.bytes_total)))
    elif counted.bytes_done:
        parts.append(_said_bytes(counted.bytes_done))
    what = say(counted.key)
    said = (say("progress.line", what=what, parts=", ".join(parts)) if parts
            else say("progress.bare", what=what))
    if counted.seconds_left is not None:     # PRESS-0471: a countdown, as m:ss
        minutes, seconds = divmod(counted.seconds_left, 60)
        said += " " + say("progress.waiting", left=f"{minutes}:{seconds:02d}")
    fraction = None
    if counted.bytes_total:   # truthy, not `is not None`: a total of 0 counts files
        fraction = counted.bytes_done / counted.bytes_total
    elif counted.total:
        fraction = counted.done / counted.total
    return {"running": True, "said": said, "fraction": fraction}


def _bare_failure() -> str:
    """The unforeseen sentence alone, for where the failure page itself could
    not be drawn. Nothing here can raise but `say`, and then it is empty."""
    try:
        what, then = say("failure.unforeseen.what"), say("failure.unforeseen.next")
        return (f'<section class="failure"><p class="what">{html.escape(what)}</p>'
                f'<p class="next">{html.escape(then)}</p></section>')
    except Exception:  # noqa: BLE001 -- an empty answer still beats none
        return ""


def render_failure(
    failure: BaseException, *, publishing: bool, secret: str | None = None
) -> str:
    """The three-part sentence and Show details, as an HTML fragment.

    Everything inserted is escaped: a failure's words are text, not markup. The
    fragment names the log by its file name and its folder in words, never by a
    path; the page's own script fetches the path only when Copy is clicked.
    """
    sentence = sentence_for(failure, publishing=publishing, secret=secret)
    e = html.escape
    return (
        '<section class="failure">'
        f'<p class="what">{e(sentence.what)}</p>'
        f'<p class="site">{e(sentence.site.words)}</p>'
        f'<p class="next">{e(sentence.next)}</p>'
        + (f'<p class="next"><a href="{e(sentence.link[0], quote=True)}">'
           f"{e(sentence.link[1])}</a></p>" if sentence.link else "")
        + sendlog.button()
        + f"<details><summary>{say('failure.show_details')}</summary>"
        f"<pre>{e(details_for(failure))}</pre>"
        f"<p>{say('failure.log', log=e(log.FILE_NAME), old=e(log.OLD_NAME))}</p>"
        '<button type="button" data-action="copy-location">'
        f"{say('failure.copy_location')}</button> "
        f'<button type="button" data-action="open-folder">{say("failure.open_folder")}</button>'
        "</details></section>"
    )


def render_notices(notices: list[str | Notice]) -> str:
    """Each notice in the three parts § Errors requires, escaped (§ 4.4).

    A notice names files he named himself, so its words are text, not markup.
    A plain string is a Store or Settings notice, whose site part is
    UNCHANGED; a Notice carries its own (PRESS-0145).
    """
    if not notices:
        return ""
    e = html.escape
    shown = [notice if isinstance(notice, Notice) else Notice(notice) for notice in notices]
    # One next step for every notice: StoreNotice covers three occasions under
    # one type, so the Face cannot tell them apart (§ 4.4).
    items = "".join(
        f'<li><p class="what">{e(notice.text)}</p>'
        f'<p class="site">{e(notice.site.words)}</p>'
        f'<p class="next">{e(say("notice.next"))}</p></li>'
        for notice in shown
    )
    return f'<ul class="notices">{items}</ul>'


_T = TypeVar("_T")


@contextlib.contextmanager
def nothing_captured() -> Iterator[list[str]]:
    """The `capture` a caller with no Face passes: it catches nothing."""
    yield []


def gatherer(capture: Callable[[], AbstractContextManager[list[str]]],
             notices: list) -> Callable[[Callable[[], _T]], _T]:
    """Run a step inside `capture`, adding what it caught to `notices`
    whether the step returns or raises."""
    def gathered(step: Callable[[], _T]) -> _T:
        caught: list[str] | None = None
        try:
            with capture() as caught:
                return step()
        finally:
            if caught is not None:
                notices.extend(caught)
    return gathered


def loaded_settings(served: Face, folder: Path) -> tuple[settings.Settings | None, str]:
    """The settings in `folder`, or None where there are none or they are
    refused, and the notices loading them raised, rendered. A page showing
    a refused file differently loads it itself."""
    with served.capture() as notices:
        try:
            saved = settings.load(folder)
        except (settings.NotSetUp, settings.SettingsError):
            saved = None
    return saved, render_notices(notices)


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str]
    body: bytes

    def form(self, *, blanks: bool = False, strict: bool = False) -> dict[str, list[str]]:
        """The posted form, read with parse_qs. `blanks` keeps fields left
        empty. A body that is not UTF-8 reads with replacement characters, or
        raises UnicodeDecodeError where `strict`, which a page saving his
        words asks for rather than keep a character he did not type."""
        return urllib.parse.parse_qs(self.body.decode("utf-8", "strict" if strict else "replace"),
                                     keep_blank_values=blanks)


@dataclass(frozen=True)
class Reply:
    """A page's answer sent as it is, unwrapped (PRESS-0012 § 4.3)."""
    body: bytes
    content_type: str
    status: int = 200
    location: str | None = None


@dataclass(frozen=True)
class Download:
    """A page's answer sent as a file the browser saves (PRESS-0224 § 4.5):
    sent in pieces, then deleted."""
    path: Path
    name: str   # the name the browser saves it under


Page = Callable[[Request], "str | Reply | Download"]  # a str is the page's HTML body
Locate = Callable[[str], Path]

# PRESS-0268: no served file runs a script, so a preview page opened outside
# its sandboxed frame runs none of a site's scripts in the Face's origin.
FILES_POLICY = ("default-src 'self'; img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; font-src 'self'; "
                "script-src 'none'; connect-src 'self'; frame-src 'none'; "
                "object-src 'none'; base-uri 'none'; form-action 'none'; "
                "frame-ancestors 'self'")


# A fixed table rather than `mimetypes`, which reads the Windows registry and so
# answers whatever another program last wrote there (PRESS-0012 § 4.3).
_FILE_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    # PRESS-0197 § 4.1: the kept files' kinds.
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".txt": "text/plain; charset=utf-8",
    # PRESS-0219 § 4.3: the manual's video captions.
    ".vtt": "text/vtt; charset=utf-8",
}

# Every wrapped page carries this, so a frame on a Face page can only show an
# address the Face serves: a link followed in the preview never leaves. The
# editors link his site's stylesheets into the page, so its styles, fonts and
# pictures come from the Face too, never from the web (PRESS-0012 § 3
# decision 4).
_FRAMES_POLICY = ("style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; "
                  "frame-src 'self'; frame-ancestors 'self'")

# Every answer but a wrapped page or a served file carries this alone, added
# by _Handler.end_headers. A page on another 127.0.0.1 port is the same site,
# so a frame of the Face would carry the cookie and its clicks the Face's own
# Origin (PRESS-0011 § 4.5).
_ANCESTORS_POLICY = "frame-ancestors 'self'"


def within(folder: Path) -> Locate:
    """A Locate joining the rest of a path onto `folder`, refusing anything that
    resolves outside it -- a link inside pointing out included (§ 4.3)."""
    root = Path(folder)

    def locate(rest: str) -> Path:
        target = (root / rest).resolve(strict=True)
        if not target.is_relative_to(root.resolve(strict=True)):
            raise LookupError("outside the folder")
        return target

    return locate


def _served_file(rest: str, locate: Locate) -> Path | None:
    """§ 4.3's steps 1 to 4: the file `rest` names, or None for a 404."""
    try:
        decoded = urllib.parse.unquote(rest, errors="strict")
    except UnicodeDecodeError:
        return None
    if "\0" in decoded or "\\" in decoded:
        return None
    if any(segment in ("", ".", "..") for segment in decoded.split("/")):
        return None
    try:
        target = locate(decoded)
    except Exception:  # noqa: BLE001 -- any refusal is a 404, never a failure
        return None
    return target if target.is_file() else None


def _running(request: Request) -> str:
    return f"<h1>{say('face.running')}</h1>"


def is_secret(offered: str, secret: str) -> bool:
    """Constant-time, as bytes: compare_digest raises TypeError on a str holding
    a non-ASCII character, and a wrong secret is refused, never dropped
    (§ 4.5, PRESS-0135)."""
    return secrets.compare_digest(offered.encode("utf-8", "replace"), secret.encode("utf-8"))


# How long Open folder waits for xdg-open to say whether it managed. It hands
# the folder to the desktop's own opener and exits; one that is still running
# after this is taken to have opened it.
_OPENER_SECONDS = 5


def _length(value: str | None) -> int | None:
    """A request's Content-Length, or None where it is not a count."""
    try:
        length = int(value or 0)
    except ValueError:
        return None
    return length if length >= 0 else None


def _open_folder(folder: Path) -> None:
    """Open `folder` in the platform's file manager. Raises FolderNotOpened."""
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 -- a folder path, never a shell command
            return
        opener = subprocess.Popen(  # noqa: S603 -- a fixed program and one path argument
            ["xdg-open", str(folder)],  # noqa: S607 -- xdg-open is found on PATH by design
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise FolderNotOpened(
            f"the opener could not start: {os_reason.of(exc)}"
        ) from None
    try:
        code = opener.wait(timeout=_OPENER_SECONDS)
    except subprocess.TimeoutExpired:
        return
    if code != 0:
        raise FolderNotOpened(f"the opener could not open it (it answered {code})")


def message_box(inner_id: str, content: str = "", *, focus: str = "",
                forgets: bool = False) -> str:
    """PRESS-0236: a message that opens over the page, so nothing beside a
    control moves when it appears. Scripts write into `inner_id`; the Face's
    script opens the box whenever those words change, OK closes it, and
    closing returns to the field named `focus`, where one is named. With
    `forgets`, OK also forgets a press's outcome (PRESS-0235 § 4.5)."""
    to = f' data-focus="{html.escape(focus, quote=True)}"' if focus else ""
    forget = " data-forget" if forgets else ""
    return (f'<dialog class="message"{to}><div id="{inner_id}">{content}</div>'
            f'<p><button type="button" data-close{forget}>{say("face.message.ok")}</button></p>'
            "</dialog>")


def file_box(name: str, accept: str, address: str, label: str, *,
             sending: str = "", folder: bool = False) -> str:
    """A button choosing one file, sent as the body to `address`; the answer
    replaces the page (PRESS-0224 § 4.6). `sending` is a `script.` words key
    the button reads while the file is sent. Where Pressless cannot be
    reached, the button comes back and a message says so (PRESS-0319).

    With `folder`, the button chooses a folder instead, and the browser sends
    it as one ZIP, so the address takes what a ZIP file box sends (PRESS-0335)."""
    wait = f' data-sending="{html.escape(sending, quote=True)}"' if sending else ""
    kind = 'webkitdirectory data-folder=""' if folder else f'accept="{accept}"'
    return (f'<p><button type="button" data-file="{name}"{wait}>{html.escape(label)}</button>'
            f'<input type="file" id="{name}" {kind} hidden '
            f'data-to="{html.escape(address, quote=True)}"></p>'
            + message_box(f"{name}-message") + f"<script>{face_scripts.FILE_SCRIPT}</script>")


def true_colours(on: bool = False) -> str:
    """Sits above each editor's preview; shown only on a dark look (PRESS-0187).
    `on` is his last choice, kept between visits (PRESS-0263)."""
    checked = " checked" if on else ""
    return (f'<p class="true-colours"><label><input type="checkbox" data-true-colours{checked}>'
            f' {say("face.true_colours")}</label></p>')


# The logo's mark, drawn inline so the bar needs no file (PRESS-0178).
_MARK = ('<svg viewBox="16 34 70 118" aria-hidden="true">'
         '<path d="M16 34 H62 L86 58 V146 a6 6 0 0 1 -6 6 H22 a6 6 0 0 1 -6 -6 V40 '
         'a6 6 0 0 1 6 -6 Z" fill="none" stroke="currentColor" stroke-width="6" '
         'stroke-linejoin="round"/><path d="M62 34 V52 a6 6 0 0 0 6 6 H86 Z" '
         'fill="#e9a23b"/><g fill="#e9a23b"><rect x="28" y="80" width="44" height="7" '
         'rx="3.5"/><rect x="28" y="98" width="44" height="7" rx="3.5"/>'
         '<rect x="28" y="116" width="30" height="7" rx="3.5"/></g></svg>')

# The browser tab's icon: packaging/icons/pressless-icon.svg, inline for the
# same reason as the mark (PRESS-0240). A test holds the two equal.
_ICON = "data:image/svg+xml," + urllib.parse.quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" width="256" height="256" '
    'role="img" aria-label="Pressless">\n'
    '  <rect width="160" height="160" rx="32" fill="#2b2620"/>\n'
    '  <g transform="translate(29 5)">\n'
    '    <path d="M16 34 H62 L86 58 V146 a6 6 0 0 1 -6 6 H22 a6 6 0 0 1 -6 -6 V40 '
    'a6 6 0 0 1 6 -6 Z" fill="none" stroke="#F4EFE6" stroke-width="6" '
    'stroke-linejoin="round"/>\n'
    '    <path d="M62 34 V52 a6 6 0 0 0 6 6 H86 Z" fill="#E9A23B"/>\n'
    '    <g fill="#E9A23B"><rect x="28" y="80" width="44" height="7" rx="3.5"/>'
    '<rect x="28" y="98" width="44" height="7" rx="3.5"/>'
    '<rect x="28" y="116" width="30" height="7" rx="3.5"/></g>\n'
    '  </g>\n'
    '</svg>', safe="")


def _page(body: str, theme: str = themes.FOLLOW, site_name: str = "",
          size: int = themes.NO_ZOOM, after: str = "", *,
          language: str = languages.FOLLOW, offer_languages: bool = False,
          setting_up: bool = False, other_sites: bool = False) -> str:
    """The whole document a Face screen is: `body` inside the top bar, whose
    first link names the open site, or says Sites before there is one.
    `language` is the picker's choice; `offer_languages` puts the list at
    the top of <main> (PRESS-0241 § 4.3).

    While `setting_up`, the bar leads nowhere, so setup cannot be left
    half-done by a stray click (user, 2026-11-21): Help and More's pages open
    in a new tab, and Sites stays only where `other_sites` gives a way back."""
    chosen = "" if theme == themes.FOLLOW else f' data-theme="{html.escape(theme, quote=True)}"'
    if size != themes.NO_ZOOM:
        chosen += f' data-size="{size}"'
    # PRESS-0353 § 4.2: the parts of a site, led by the open site's name.
    links = (("/sites", html.escape(site_name) if site_name else say("face.sites")),
             ("/", say("face.your_site")), ("/pages", say("face.pages")),
             ("/journal", say("face.journal")), ("/look", say("face.look")),
             ("/files", say("face.files")), ("/visitors", say("face.visitors")),
             ("/setup", say("face.settings")), ("/manual", say("face.help")))
    away = ' target="_blank" rel="noopener"' if setting_up else ""
    locked = f'<a aria-disabled="true" title="{html.escape(say("face.after_setup"))}">'

    def bar_link(address: str, words_: str) -> str:
        if address == "/manual":
            return f'<a href="{address}"{away}>{words_}</a>'
        if setting_up and not (address == "/sites" and other_sites):
            return f"{locked}{words_}</a>"
        return f'<a href="{address}">{words_}</a>'

    bar = "".join(bar_link(address, words_) for address, words_ in links)
    return (
        f'<!doctype html><html lang="{words.in_use()}"{chosen}><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Pressless</title><link rel="icon" href="{_ICON}">'
        f"<style>{face_style.STYLE}</style>"
        # PRESS-0242 § 4.3: before <main>, whose scripts run as they load.
        '<script type="application/json" id="pressless-words">'
        f"{words.for_scripts()}</script><script>{face_scripts.SAY}</script></head>"
        f'<body class="face"><header class="bar">{_MARK}<b>Press<span>less</span></b>{bar}'
        # PRESS-0343: the rest under More, which opens over the page.
        f'<details class="more"><summary>{say("face.more")}</summary><div>'
        # PRESS-0179: on every screen, failure pages included.
        f'<a href="/report"{away}>{say("face.report")}</a>'
        # PRESS-0262 § 4.3: beside Report a problem.
        f'<a href="{usage.ADDRESS}"{away}>{say("face.usage")}</a>'
        # PRESS-0278: beside Usage reports.
        f'<a href="/about"{away}>{say("face.about")}</a>'
        f'{themes.picker(theme)}{themes.size_picker(size)}{languages.picker(language)}'
        "</div></details></header>"
        f'<main>{languages.offer() if offer_languages else ""}{body}</main>'
        f"<script>{face_scripts.SCRIPT}</script>{after}</body></html>"
    )


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    face: Face

    def handle_error(self, request: object, client_address: object) -> None:
        """Note the type alone; print nothing.

        The standard one prints a traceback naming the full path of every file
        in it to the console (§ 4.5).
        """
        kind = sys.exc_info()[0]
        self.face._log.note(f"a request failed: {kind.__qualname__ if kind else 'unknown'}")


class _Handler(http.server.BaseHTTPRequestHandler):
    server: _Server
    _policy_sent = False  # this answer named its own Content-Security-Policy
    _screen: str | None = None  # the screen to report once this answer is sent

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Write nothing: the standard one prints the request line, secret
        included, to the console (§ 4.5)."""
        return

    def setup(self) -> None:
        # A client that declares a body and stops sending holds this thread
        # until the stall limit, not for ever. Read here, per connection, so
        # a test that shortens _STALL_SECONDS reaches the next one.
        self.timeout = _STALL_SECONDS
        super().setup()

    def do_GET(self) -> None:  # noqa: N802 -- the name http.server dispatches to
        # PRESS-0464: a download packs as a POST's job runs, and counts too.
        # PRESS-0469: one language for the whole answer.
        with progress.job(), words.held():
            self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        # PRESS-0435: a long job's loops report how far they have got into
        # this request's record, which GET /progress reads.
        with progress.job(), words.held():
            self._dispatch("POST")

    def send_header(self, keyword: str, value: str) -> None:
        if keyword.lower() == "content-security-policy":
            self._policy_sent = True
        super().send_header(keyword, value)

    def end_headers(self) -> None:
        """§ 4.5: every answer carries frame-ancestors 'self', those
        http.server sends itself included (send_error's 400, 414, 431 and
        501). An answer naming its own policy keeps it."""
        if not self._policy_sent:
            super().send_header("Content-Security-Policy", _ANCESTORS_POLICY)
        self._policy_sent = False
        # PRESS-0435: the job's record ends with its answer, so neither what
        # runs after it nor the thread's closing reads as running.
        progress.end()
        super().end_headers()

    def _send(
        self, status: int, body: str, content_type: str, headers: tuple[tuple[str, str], ...] = ()
    ) -> None:
        self._send_bytes(status, body.encode("utf-8"), f"{content_type}; charset=utf-8", headers)

    def _send_bytes(
        self, status: int, data: bytes, content_type: str,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._send_head(status, content_type, len(data), headers)
        self.wfile.write(data)

    def _send_head(self, status: int, content_type: str, length: int,
                   headers: tuple[tuple[str, str], ...] = (), *,
                   cache: str = "no-store") -> None:
        """The headers every answer shares, then its own: a page, a file and a
        download alike. A 204 or a 304 carries no body, so it names no type or
        length (RFC 9110 §§ 8.6 and 15.4.5). `cache` is what a browser may keep."""
        self.send_response(status)
        if status not in (204, 304):
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()

    def _send_page(self, face: Face, status: int, body: str) -> None:
        """`body` wrapped in the Face's frame, carrying the frames policy.

        Failure pages come through here too, so what a part adds, or the
        site's name, failing costs only that piece: the page still goes."""
        after = []
        for render in face._every_page:
            try:
                after.append(render())
            except Exception as exc:  # noqa: BLE001 -- the page outranks one part
                face.note(f"a part failed on every page: {type(exc).__name__}")
        try:
            name = face.site_name()
        except Exception as exc:  # noqa: BLE001 -- the bar then says Sites
            face.note(f"the site's name could not be read: {type(exc).__name__}")
            name = ""
        try:
            setting_up = face.setting_up()
            other_sites = setting_up and face.other_sites()
        except Exception as exc:  # noqa: BLE001 -- the bar then stays open
            face.note(f"setup's state could not be read: {type(exc).__name__}")
            setting_up = other_sites = False
        try:
            page = _page(body, face._theme, name, face._size, "".join(after),
                         language=face._language, offer_languages=face._offer_languages,
                         setting_up=setting_up, other_sites=other_sites)
        except Exception as exc:  # noqa: BLE001 -- § Errors: he always gets an answer
            face.note(f"the page's frame could not be drawn: {type(exc).__name__}")
            self._send(500, _bare_failure(), "text/html")
            return
        self._send(status, page, "text/html", (("Content-Security-Policy", _FRAMES_POLICY),))

    def _body_length(self, limit: int,
                     too_long: Callable[[], None] | None = None) -> int | None:
        """The declared body length, or None once the request is refused.

        An unparseable or negative length gets 400 unread: read(-1) would wait
        for the client to close, holding this thread (PRESS-0162). A length
        past `limit` is drained, never read into memory, and answered by
        `too_long`, or else a bare 413.
        """
        length = _length(self.headers.get("Content-Length"))
        if length is None:
            self._send(400, "", "text/plain")
            return None
        if length > limit:
            self._drain()
            if too_long is None:
                self._send(413, "", "text/plain")
            else:
                too_long()
            return None
        return length

    def _refuse(self, key: str = "face.forbidden") -> None:
        """403. The request is anyone's, so its body is drained no further
        than _MAX_BODY; past that the connection closes, and the sender may
        see it dropped rather than the answer."""
        declared = _length(self.headers.get("Content-Length")) or 0
        self._drain(min(declared, _MAX_BODY))
        self.close_connection = True
        self._send(403, say(key), "text/plain")

    def _drain(self, left: int | None = None) -> None:
        """Read and drop a body that will not be used, so the answer arrives:
        the `left` bytes still unread, or by default the whole declared body.

        Closing a socket with unread bytes resets it, and the sender sees a
        dropped connection rather than the answer: WinError 10053 on Windows
        CI, a broken pipe on Linux for a body past the socket buffers.
        """
        if left is None:
            left = _length(self.headers.get("Content-Length")) or 0
        while left > 0:
            chunk = self.rfile.read(min(left, 64 * 1024))
            if not chunk:
                return
            left -= len(chunk)

    def _has_cookie(self, face: Face) -> bool:
        """Read by hand: other local programs' cookies arrive here too, and
        the standard parser drops the whole header at one it cannot read."""
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == face._cookie and is_secret(value, face._session):
                return True
        return False

    def _dispatch(self, method: str) -> None:
        """Every request, checked in the order § 4.5 sets. The order is the
        security policy: each check refuses before the next runs.

        1. Host, for every request, doors included.
        2. A door (PRESS-0337 § 4.3), which takes its own Authorization and
           never the cookie.
        3. The one-time link, which sets the cookie.
        4. The cookie, except a GET to a return page (PRESS-0122 § 4.3).
        5. A POST's Origin.

        Only then is the request answered: the Face's own routes (_OWN), then
        uploads, pages and files. A new route belongs after step 5.
        """
        face = self.server.face
        if self.headers.get("Host") != face._host:
            self._refuse()
            return
        parts = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(parts.query))
        door = face._doors.get(parts.path)
        if door is not None:
            self._through_door(face, method, parts.path, query, *door)
            return
        if method == "GET" and "t" in query:
            self._follow_link(face, parts.path or "/", query["t"])
            return
        admitted = self._has_cookie(face)
        if not admitted and not (method == "GET" and parts.path in face._returns):
            # Besides a door, the one page reached without the cookie is one
            # Google's redirect lands on, which authenticates the request
            # itself (PRESS-0122 § 4.3).
            self._refuse()
            return
        if admitted:
            face.returned.set()   # PRESS-0428 § 4.4: a tab holds this session
        if method == "POST":
            # A POST from any other origin names it, as "null" where its page
            # hides it, so one naming none is from here; the cookie admits it.
            origin = self.headers.get("Origin")
            if origin is not None and origin != face._origin:
                self._refuse()
                return

        own = self._OWN.get((method, parts.path))
        if own is not None:
            own(self, face)
            return
        upload = face._uploads.get(parts.path) if method == "POST" else None
        if upload is not None:
            self._take_upload(face, upload, parts.path, query)
            return
        registered = face._pages.get((method, parts.path))
        if registered is None:
            self._drain()
            self._send_file(method, parts.path, face)
            return
        page, publishing = registered
        length = self._body_length(_MAX_BODY) if method == "POST" else 0
        if length is None:
            return
        request = Request(method, parts.path, query, self.rfile.read(length) if length else b"")
        self._answer_then(face, page, request, publishing)

    def _follow_link(self, face: Face, path: str, offered: str) -> None:
        """The link is honoured once: it reached the browser on its command
        line, so it must not stay the key for the whole run (§ 4.5)."""
        with face._link_lock:
            honoured = not face._link_spent and is_secret(offered, face._secret)
            face._link_spent = face._link_spent or honoured
        if honoured:
            cookie = f"{face._cookie}={face._session}; HttpOnly; SameSite=Strict; Path=/"
            self._send(303, "", "text/plain", (("Set-Cookie", cookie), ("Location", path)))
        elif self._has_cookie(face):
            # PRESS-0245: a reload, Back or a restored session lands on the
            # spent link. The session already lets this browser in, so it goes
            # on to the page, with no new cookie.
            self._send(303, "", "text/plain", (("Location", path),))
        else:
            self._refuse("face.link_spent")

    def _send_progress(self, face: Face) -> None:
        """PRESS-0435 § 4.3. Takes no lock but progress's own, so it answers
        during a press."""
        counted = progress.now()
        said = progress_said(counted) if counted else {"running": False, "said": "",
                                                        "fraction": None}
        self._send(200, json.dumps(said), "application/json")

    def _send_alive(self, face: Face) -> None:
        """PRESS-0428 § 4.4: which Face is answering."""
        self._send(200, json.dumps({"face": face.id}), "application/json")

    def _send_location(self, face: Face) -> None:
        self._send(200, str(face._folder), "text/plain")

    def _open_the_folder(self, face: Face) -> None:
        try:
            _open_folder(face._folder)
        except FolderNotOpened as exc:
            self._send_page(face, 500, face.fail(exc, publishing=False))
            return
        self._send(204, "", "text/plain")

    def _through_door(self, face: Face, method: str, path: str, query: dict[str, str],
                      page: Page, admits: Callable[[str], bool]) -> None:
        """PRESS-0337 § 4.3: a door is answered without the cookie, and only
        to a POST with no Origin header whose Authorization `admits` takes.
        The cookie never opens it."""
        if (method != "POST" or self.headers.get("Origin") is not None
                or not admits(self.headers.get("Authorization", ""))):
            self._refuse()
            return
        length = self._body_length(_MAX_BODY)
        if length is None:
            return
        body = self.rfile.read(length) if length else b""
        self._answer_then(face, page, Request(method, path, query, body), False)

    def _answer_then(self, face: Face, page: Page, request: Request, publishing: bool) -> None:
        """Answer, then run what the page asked to run after (PRESS-0023 § 4.9)."""
        face._reply.after = []
        self._screen = None
        try:
            self._answer(face, page, request, publishing)
        finally:
            # PRESS-0023 § 4.9 step 5: what runs once this answer is sent.
            actions, face._reply.after = face._reply.after, None
            if actions or self._screen is not None:
                self.wfile.flush()
                for action in actions:
                    action()
            if self._screen is not None:
                # Its own path, never after_reply's: a page shown asks
                # for nothing to run after it (PRESS-0203).
                usage.report("screen", screen=self._screen)

    def _choose_theme(self, face: Face) -> None:
        """PRESS-0190: remember the theme the picker has already applied."""
        def keep(key: str) -> None:
            themes.write_choice(face._folder, key)
            face._theme = key

        self._choose(face, themes.known, keep, "theme")

    def _choose_language(self, face: Face) -> None:
        """PRESS-0241 § 4.3: keep the language chosen; the page then reloads
        in it. The tray menu takes it at the next start (§ 6)."""
        def keep(code: str) -> None:
            languages.write_choice(face._folder, code)
            face._language = code
            face._offer_languages = False
            words.choose(languages.for_screens(face._folder)[0])

        self._choose(face, languages.known, keep, "language")

    def _choose_size(self, face: Face) -> None:
        """PRESS-0338: remember the text size the picker has already applied."""
        def keep(text: str) -> None:
            themes.write_size(face._folder, int(text))
            face._size = int(text)

        self._choose(face, lambda text: text in {str(size) for size in themes.SIZES}, keep,
                     "size")

    def _choose(self, face: Face, offered: Callable[[str], bool],
                keep: Callable[[str], None], what: str) -> None:
        """A choice the page has already applied, kept for the next start."""
        length = self._body_length(_CHOICE_LIMIT)
        if length is None:
            return
        value = self.rfile.read(length).decode("utf-8", "replace")
        if not offered(value):
            self._send(400, "", "text/plain")
            return
        try:
            keep(value)
        except OSError:
            # The page has it already; only the next start forgets it.
            face._log.note(f"the {what} could not be saved")
            self._send(500, "", "text/plain")
            return
        self._send(204, "", "text/plain")

    def _choose_true_colours(self, face: Face) -> None:
        """PRESS-0263: remember the preview's true-colours switch, which the
        page has already applied."""
        length = self._body_length(_CHOICE_LIMIT)
        if length is None:
            return
        said = self.rfile.read(length)
        if said not in (b"0", b"1"):
            self._send(400, "", "text/plain")
            return
        if not choices.remember(face._site, true_colours=said == b"1"):
            face._log.note("the true-colours choice could not be saved")
            self._send(500, "", "text/plain")
            return
        self._send(204, "", "text/plain")

    # The Face's own routes, answered after every check and before any
    # route a part registers (add_page's docstring names them too).
    _OWN: dict[tuple[str, str], Callable[[_Handler, Face], None]] = {
        ("GET", "/folder/location"): _send_location,
        ("GET", "/progress"): _send_progress,
        ("GET", "/alive"): _send_alive,
        ("POST", "/folder/open"): _open_the_folder,
        ("POST", "/theme"): _choose_theme,
        ("POST", "/text-size"): _choose_size,
        ("POST", languages.ADDRESS): _choose_language,
        ("POST", "/true-colours"): _choose_true_colours,
    }

    def _answer(self, face: Face, page: Page, request: Request, publishing: bool) -> None:
        try:
            body = page(request)
        except Exception as exc:  # noqa: BLE001 -- § Errors' last-resort catch
            # PRESS-0262 § 4.4: the class name and the registered path, never
            # the message, which can hold paths and names.
            usage.report("failure", error=type(exc).__name__, screen=request.path,
                         publishing="yes" if publishing else "no")
            try:
                fragment = face.fail(exc, publishing=publishing)
            except Exception as again:  # noqa: BLE001 -- he always gets an answer
                face.note(f"the failure could not be worded: {type(again).__name__}")
                fragment = _bare_failure()
            self._send_page(face, 500, fragment)
            return
        if isinstance(body, Reply):
            location = (("Location", body.location),) if body.location is not None else ()
            self._send_bytes(body.status, body.body, body.content_type, location)
            return
        if isinstance(body, Download):
            self._send_download(face, body)
            return
        if request.method == "GET":
            # The registered path, no query. Reported once the page is sent,
            # so no screen waits for the list's write (PRESS-0262 § 4.5).
            self._screen = request.path
        self._send_page(face, 200, body)

    def _take_upload(self, face: Face, upload: _Upload, path: str,
                     query: dict[str, str]) -> None:
        """PRESS-0224 § 4.5: the body is a file, copied to disk in pieces, never
        held whole, and handed to the route's handler as a page is answered.
        Every check a page gets has run before this, and both size checks run
        on the declared length before a byte is written."""
        request = Request("POST", path, query, b"")
        if upload.too_large is not None:
            too_large = upload.too_large
            if self._body_length(upload.largest, lambda: self._answer_then(
                    face, too_large, request, False)) is None:
                return
        length = self._body_length(_room(upload.into), lambda: self._send_page(
            face, 413, face.fail(NoRoom("the drive is short of room"), publishing=False)))
        if length is None:
            return
        handler = upload.handler
        taken = upload.into / f".upload-{secrets.token_hex(8)}"
        failure: OSError | None = None
        left = length
        try:
            try:
                with open(taken, "xb", opener=log.owner_only) as out:
                    while left > 0:
                        piece = self.rfile.read(min(left, _PIECE))
                        if not piece:
                            break
                        left -= len(piece)
                        out.write(piece)
            except OSError as exc:
                # PRESS-0304: the rest is read and dropped, or the failure
                # page never arrives.
                failure = exc
                self._drain(left)
            if failure is None and left > 0:
                self._send(400, "", "text/plain")   # the sender stopped part way
                return

            def page(request: Request) -> str:
                if failure is not None:
                    raise failure
                return handler(taken)

            self._answer_then(face, page, request, False)
        finally:
            taken.unlink(missing_ok=True)

    def _send_download(self, face: Face, download: Download) -> None:
        """PRESS-0224 § 4.5: the file as an attachment, sent in pieces and
        then deleted, sent or not."""
        try:
            try:
                handle, size = _open_sized(download.path)
            except OSError as exc:
                self._send_page(face, 500, face.fail(exc, publishing=False))
                return
            with handle:
                plain = "".join(c if c.isascii() and (c.isalnum() or c in " ._-") else "_"
                                for c in download.name)
                quoted = urllib.parse.quote(download.name, safe="")
                # An attachment is saved, never shown, so it needs no
                # FILES_POLICY; end_headers gives it frame-ancestors.
                self._send_head(200, _FILE_TYPES.get(
                    Path(download.name).suffix.lower(), "application/octet-stream"), size, ((
                        "Content-Disposition",
                        f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quoted}"),))
                self._send_pieces(handle)
        finally:
            download.path.unlink(missing_ok=True)

    def _send_pieces(self, handle: BinaryIO) -> None:
        """The rest of `handle`, _PIECE bytes at a time, never held whole."""
        while piece := handle.read(_PIECE):
            self.wfile.write(piece)

    def _send_file(self, method: str, path: str, face: Face) -> None:
        """The longest registered prefix's file, or 404 (PRESS-0012 § 4.3).
        Sent in pieces: a kept song or video is never read whole."""
        prefixes = [prefix for prefix in face._files if path.startswith(prefix)]
        target, prefix = None, ""
        if method == "GET" and prefixes:
            prefix = max(prefixes, key=len)
            target = _served_file(path[len(prefix):], face._files[prefix])
        opened = None
        if target is not None:
            with contextlib.suppress(OSError):  # unreadable is answered like absent
                opened = _open_sized(target)
        if target is None or opened is None:
            self._send(404, say("face.not_found"), "text/plain")
            return
        handle, size = opened
        kind = _FILE_TYPES.get(target.suffix.lower(), "application/octet-stream")
        headers: tuple[tuple[str, str], ...] = (("Content-Security-Policy", FILES_POLICY),)
        with handle:
            if prefix not in face._kept_files:
                self._send_head(200, kind, size, headers)
                self._send_pieces(handle)
                return
            # PRESS-0478: tagged by its bytes, never its name, size or time,
            # so a name re-used for another photograph is always sent again.
            tag = '"' + hashlib.file_digest(handle, "sha256").hexdigest() + '"'
            handle.seek(0)
            held = {each.strip().removeprefix("W/")
                    for each in self.headers.get("If-None-Match", "").split(",")}
            headers += (("ETag", tag),)
            if tag in held:
                self._send_head(304, kind, 0, headers, cache="no-cache")
                return
            self._send_head(200, kind, size, headers, cache="no-cache")
            self._send_pieces(handle)


# How often the server's loop checks whether it has been asked to stop, in
# seconds; `stop` waits up to this long. The standard library's own default.
# tests/conftest.py shortens it: the suite starts and stops hundreds of servers.
_POLL_SECONDS = 0.5

# The longest a request may stall, in seconds, on one read or write. Generous:
# the browser is on this machine.
_STALL_SECONDS = 60

# The longest body the theme, text-size, language and true-colours routes
# take: the longest theme key with room to spare. A longer body is no choice of any.
_CHOICE_LIMIT = 64

# The ceiling on a registered page's POST body, read whole into memory. It sits
# above any file the page editor sends, which its script caps at
# builder.FILE_LARGEST first, and far below a size that would exhaust memory.
# Nothing caps a page save below it. A declared length past it is refused with
# 413 before a byte is read.
_MAX_BODY = 64 * 1024 * 1024

# PRESS-0224 § 4.5: an upload or a download moves in pieces of this size, and
# an upload is refused where it would leave the drive less than _SPARE free.
_PIECE = 64 * 1024
_SPARE = 1024 * 1024 * 1024


def _open_sized(path: Path) -> tuple[BinaryIO, int]:
    """`path` open to read, with its size. Closed again where the size
    cannot be read: Windows will not delete a file held open."""
    handle = open(path, "rb")  # noqa: SIM115 -- the caller closes it
    try:
        return handle, os.fstat(handle.fileno()).st_size
    except BaseException:
        handle.close()
        raise


def _room(folder: Path) -> int:
    """The bytes an upload into `folder` may take. -1 where the free space
    cannot be read, so every upload is refused, an empty one included."""
    try:
        return shutil.disk_usage(folder).free - _SPARE
    except OSError:
        return -1


@dataclass(frozen=True)
class _Upload:
    """A route `Face.add_upload` registered."""
    handler: Callable[[Path], str | Reply]
    into: Path
    largest: int
    too_large: Page | None


# PRESS-0353 § 4.6: where a part can show something on a screen it does not own.
PLACES = ("site-notices", "site-tiles", "site-below", "journal-below", "computer")


@dataclass(frozen=True)
class HandOver:
    """What one Face leaves the next, so a tab still open carries on
    (PRESS-0428 § 4.1): its port, and the session its tabs' cookie holds."""

    port: int
    session: str

    def text(self) -> str:
        """`<port>:<session>`, as PRESSLESS_RESUME carries it (§ 4.3)."""
        return f"{self.port}:{self.session}"

    @classmethod
    def read(cls, text: str | None) -> HandOver | None:
        """The hand-over `text` holds, or None for anything a Face would not
        have written: a port from 1 to 65535 and a session token_urlsafe(32)
        made."""
        found = _HAND_OVER.fullmatch(text or "")
        if found is None or not 1 <= int(found[1]) <= 65535:
            return None
        return cls(int(found[1]), found[2])


_HAND_OVER = re.compile(r"([0-9]{1,5}):([A-Za-z0-9_-]{43})")


class Face:
    """The running server. Made by `serve`; one per launch."""

    def __init__(self, folder: Path, port: int = 0, *, site: Path | None = None,
                 session: str | None = None) -> None:
        # PRESS-0223 § 4.4: the log and the theme are the machine's, in
        # Pressless's own folder; the settings and choices are the open site's.
        self._folder = Path(folder)
        self._site = Path(site) if site is not None else self._folder
        self._uploads: dict[str, _Upload] = {}
        self._log = log.open_log(self._folder)
        self._theme = themes.read_choice(self._folder)
        self._size = themes.read_size(self._folder)
        # PRESS-0241 § 4.3: the screens' language was chosen at startup;
        # this is what the picker shows, and whether the list is offered.
        self._language = languages.read_choice(self._folder)
        self._offer_languages = languages.for_screens(self._folder)[1]
        for code in words.unreadable():
            self._log.note(f"the language file {code}.json could not be read")
        # PRESS-0428 § 4.1: a restart's Face keeps the session open tabs hold.
        # The link is always new, since it is not the session.
        self._session = session if session is not None else secrets.token_urlsafe(32)
        self._secret = secrets.token_urlsafe(32)
        # The link carrying the secret travels on a command line, where other
        # programs can read it, so it must never also be the cookie (§ 4.5).
        while self._secret == self._session:
            self._secret = secrets.token_urlsafe(32)
        # PRESS-0428 § 4.4: which Face answers /alive, so the page that asked
        # for a restart can tell the new one from the old. Not a secret.
        self.id = secrets.token_hex(8)
        # Set by the first request the session cookie admits: a tab came back.
        self.returned = threading.Event()
        self._link_spent = False
        self._link_lock = threading.Lock()
        self._pages: dict[tuple[str, str], tuple[Page, bool]] = {}
        self._returns: set[str] = set()
        self._files: dict[str, Locate] = {}
        self._kept_files: set[str] = set()
        self._pieces: dict[str, list[Callable[[], str]]] = {place: [] for place in PLACES}
        self._unseen: list[Callable[[], bool]] = []
        self._doors: dict[str, tuple[Page, Callable[[str], bool]]] = {}
        self._every_page: list[Callable[[], str]] = []
        self._at_stop: list[Callable[[], None]] = []
        self._reply = threading.local()
        try:
            self._server = _Server(("127.0.0.1", port), _Handler)
        except OSError:
            # A named port that is held: no fallback, and no open log left
            # behind (§ 4.5).
            self._log.close()
            raise
        self._server.face = self
        port = self._server.server_address[1]
        self._host = f"127.0.0.1:{port}"
        self._origin = f"http://{self._host}"
        # Browsers do not separate cookies by port, so the name carries it.
        self._cookie = f"pressless-{port}"
        self.url = f"http://{self._host}/?t={self._secret}"
        self.add_page("GET", "/", _running)
        self._thread = threading.Thread(
            target=self._server.serve_forever, args=(_POLL_SECONDS,),
            name="pressless-face", daemon=True,
        )
        self._thread.start()

    def add_page(self, method: str, path: str, page: Page, *, publishing: bool = False) -> None:
        """Register `page` for `method` and `path`, replacing any before it.

        A door's path, the Face's own routes (_Handler._OWN) and an upload's
        path answer first, so a page registered at one of those is never
        reached."""
        self._pages[(method.upper(), path)] = (page, publishing)

    def add_upload(self, path: str, handler: Callable[[Path], str | Reply], into: Path, *,
                   largest: int = 0, too_large: Page | None = None) -> None:
        """Register a POST `path` whose body is a file, copied to `into` in
        pieces and handed to `handler` by path, then deleted (PRESS-0224
        § 4.5). The handler's answer is a page's. With `too_large`, a body
        declared longer than `largest` bytes is never written, and
        `too_large` answers instead."""
        self._uploads[path] = _Upload(handler, Path(into), largest, too_large)

    def add_return_page(self, path: str, page: Page) -> None:
        """Register `page` for GET `path`, reached WITHOUT the session cookie.

        For the page another site's redirect lands on, which a SameSite=Strict
        cookie never reaches. Every other check still runs; the page must
        authenticate the request itself (PRESS-0122 § 4.3).
        """
        self.add_page("GET", path, page)
        self._returns.add(path)

    def add_door(self, path: str, page: Page, admits: Callable[[str], bool]) -> None:
        """Register `page` for POST `path`, answered WITHOUT the session cookie
        to a request with no Origin header whose Authorization header
        `admits(header)` takes, and refused otherwise (PRESS-0337 § 4.3). The
        Host check still runs first; the page's answer is sent as it is."""
        self._doors[path] = (page, admits)

    def add_to_every_page(self, render: Callable[[], str]) -> None:
        """Have every wrapped page end with `render()`'s HTML (PRESS-0337 § 4.6)."""
        self._every_page.append(render)

    def at_stop(self, action: Callable[[], None]) -> None:
        """Run `action` when the Face stops, before its log closes."""
        self._at_stop.append(action)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def hand_over(self) -> HandOver:
        """This Face's port and session, for the next Face (PRESS-0428)."""
        return HandOver(self.port, self._session)

    @property
    def origin(self) -> str:
        """`http://127.0.0.1:<port>`, the Face's own origin."""
        return self._origin

    def fresh_link(self, path: str = "/") -> str:
        """A new one-use link to `path`; the previous link stops admitting,
        spent or not (PRESS-0204 § 4.3). The session stays, so open tabs stay
        signed in. Only an in-process caller reaches it: no route serves one."""
        secret = secrets.token_urlsafe(32)
        while secret == self._session:
            secret = secrets.token_urlsafe(32)
        with self._link_lock:
            self._secret = secret
            self._link_spent = False
            self.url = f"{self._origin}/?t={secret}"
        return f"{self._origin}{path}?t={secret}"

    def add_files(self, prefix: str, locate: Locate, *, kept: bool = False) -> None:
        """Answer GETs under `prefix`, which ends in "/", with the file `locate`
        names for the rest of the path (PRESS-0012 § 4.3). `kept` lets the
        browser keep each file, asking each time whether its bytes changed
        (PRESS-0478)."""
        self._files[prefix] = locate
        if kept:
            self._kept_files.add(prefix)

    def add_piece(self, place: str, render: Callable[[], str]) -> None:
        """Have the screen holding `place` show `render()`'s HTML there
        (PRESS-0353 § 4.6), so a part can reach a screen without its owner
        importing it. A place outside PLACES is refused."""
        if place not in self._pieces:
            raise ValueError(f"there is no place {place!r}")
        self._pieces[place].append(render)

    def pieces(self, place: str) -> list[str]:
        """What every part registered for `place` shows now, in registration order."""
        return [render() for render in self._pieces[place]]

    def site_name(self) -> str:
        """The open site's name for the top bar, or "" before setup or where
        it cannot be read: the bar then says Sites."""
        if not self.live_address():
            return ""
        try:
            identity = store.read_identity(self._site)
        except store.StoreError:
            return ""
        return identity.name if identity is not None else ""

    def live_address(self) -> str:
        """The site's address for the top bar (PRESS-0232), or "" before setup
        or where the settings file cannot be read: the page still renders, and
        the failure is told where the settings are used."""
        try:
            return settings.load(self._site).site_address
        except (settings.NotSetUp, settings.SettingsError):
            return ""

    def setting_up(self) -> bool:
        """Whether the open site is still in first-run setup: it has no
        settings, or a file carried from another machine (PRESS-0021 § 4.8)."""
        try:
            settings.load(self._site)
        except settings.NotSetUp:
            return True
        except settings.SettingsError as exc:
            return exc.key == "site_folder"
        return False

    def other_sites(self) -> bool:
        """Whether Pressless holds a site besides the open one."""
        return any(site != self._site for site in sites.all_sites(self._folder))

    def add_unseen(self, check: Callable[[], bool]) -> None:
        """Have View your site greyed out while `check()` holds: the site has
        nothing to see yet (PRESS-0234), so a part can say so without the
        editors importing it."""
        self._unseen.append(check)

    def view_site(self) -> str:
        """PRESS-0234: "View your site" beside Press to site, greyed out with no
        address or while a part says there is nothing to see. The editors'
        scripts turn it on after a publish."""
        address = self.live_address()
        live = bool(address) and not any(check() for check in self._unseen)
        return (f'<button type="button" data-view-site="{html.escape(address, quote=True)}"'
                f'{"" if live else " disabled"}>{say("face.view_site")}</button>')

    def note(self, text: str) -> None:
        """One line in the rolling log. The caller keeps URLs and paths out."""
        self._log.note(text)

    def after_reply(self, action: Callable[[], None]) -> None:
        """Run `action` once the current request's answer has been sent
        (PRESS-0023 § 4.9 step 5). Only inside a page."""
        pending = getattr(self._reply, "after", None)
        if pending is None:
            raise RuntimeError("after_reply was called outside a request")
        pending.append(action)

    @contextlib.contextmanager
    def capture(self) -> Iterator[list[str]]:
        """Record every Store and Settings notice raised inside it (§ 4.4).

        The list is filled when the capture ends. Every call into the Store or
        Settings runs inside one: outside, a notice is printed to the console
        with the path of the file that called it.
        """
        notices: list[str] = []
        # Gathered on this thread alone, so a capture holds no other request
        # (PRESS-0463).
        with gathered() as caught:
            try:
                yield notices
            finally:
                for notice in caught:
                    notices.append(say(notice.key, **notice.slots))
                    self._log.note(f"notice: {notice}")  # the log stays English

    def fail(self, failure: BaseException, *, publishing: bool, secret: str | None = None) -> str:
        """Note the failure's details in the log and return its fragment."""
        self._log.note(details_for(failure))
        return render_failure(failure, publishing=publishing, secret=secret)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        for action in self._at_stop:
            try:
                action()
            except Exception as exc:  # noqa: BLE001 -- the next one still runs
                self._log.note(f"a stop step failed: {type(exc).__name__}")
        self._log.close()


def after_restart(served: Face) -> str:
    """The attributes that send the page answering a restart home once a new
    Face answers /alive (PRESS-0428 § 4.5). The id is the Face sending the
    page, since the new one can answer before the page first asks."""
    return f'data-after-restart="/" data-face="{served.id}"'


def serve(folder: Path, port: int = 0, *, site: Path | None = None,
          session: str | None = None) -> Face:
    """Start the Face on 127.0.0.1, on a port the system chooses.

    A caller naming `port` gets that port or the bind's OSError. The
    launcher names one only where PRESSLESS_PORT is set (PRESS-0431).

    Opens no browser and prints nothing: the launcher (PRESS-0013 § 4.5) owns
    which page opens first and the link printed where no browser opens.
    `site` is the open site's folder (PRESS-0223 § 4.4), `folder` where none
    is named. `session` is the one a restart hands on (PRESS-0428 § 4.1), in
    place of a new one; the link is new either way.
    """
    return Face(folder, port, site=site, session=session)
