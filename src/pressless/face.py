"""The Face (PRESS-0011): the local server, and the error contract.

The contract is docs/specs/PRESS-0011-face.md. Two jobs, and they are one job:
this is the web server on his own machine that his browser talks to, and it is
the one place a failure any part raises becomes a sentence he understands
(`docs/design.md` § Errors). Every part raises typed failures and writes no
prose; the words live here, keyed by the failure's class.

Nothing here keeps state between requests (`docs/design.md` § State) beyond
what the server itself needs: the secret made at launch, the pages later items
add, and the log it holds open.
"""

from __future__ import annotations

import contextlib
import enum
import html
import http.cookies
import http.server
import os
import secrets
import subprocess
import sys
import threading
import urllib.parse
import warnings
import webbrowser
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from pressless import builder, credentials, insights, log, paths, publisher, settings, store

LABEL = "the Pressless-data folder, beside the program"

# One next step for every notice: StoreNotice covers three occasions under one
# type, so the Face cannot tell them apart (§ 4.4).
NOTICE_NEXT = "Nothing was lost. Send this to whoever helps you if you did not expect it."

_UNFORESEEN_WHAT = "Something went wrong that Pressless did not expect."
_UNFORESEEN_NEXT = "Try again, and send the details below to whoever helps you."

# What a credential sentence says where the Face named no secret.
_UNNAMED_NOUN = "that secret"


class Site(enum.Enum):
    UNCHANGED = "Your site has not changed."
    UNKNOWN = "Pressless cannot tell whether your site changed."
    UPDATED = "Your site has been updated."  # a notice's only (§ 4.4)


@dataclass(frozen=True)
class Sentence:
    what: str  # what happened, in his words; may hold the "{secret}" slot
    site: Site  # what it means for his site
    next: str  # what to do next


@dataclass(frozen=True)
class Notice:
    """A notice a part adds about a publish, with its own site part (§ 4.4).
    A captured Store or Settings notice is a plain string: those calls never
    touch the site (PRESS-0145)."""
    text: str
    site: Site = Site.UNCHANGED


class FolderNotOpened(Exception):
    """The platform's opener is missing or failed (§ 6)."""


def _say(what: str, next_step: str, site: Site = Site.UNCHANGED) -> Sentence:
    return Sentence(what, site, next_step)


_AGAIN = "Try again. If it keeps happening, send the details below to whoever helps you."

# Keyed by the class object, never its name: publisher and insights both define
# Unreachable, Refused and RateLimited (§ 4.2). Each Publisher type's next step
# follows the answer PRESS-0009 § 4.1 pairs with it.
SENTENCES: dict[type[Exception], Sentence] = {
    paths.NotPackaged: _say(
        "Pressless could not tell where it is running from.",
        "Start Pressless by double-clicking the file you downloaded.",
    ),
    paths.FolderUnusable: _say(
        "Pressless could not create or write its Pressless-data folder.",
        "Move Pressless to a folder you can save files in, then start it again.",
    ),
    store.StoreError: _say("Pressless could not use one of your files.", _AGAIN),
    store.EntryNotFound: _say(
        "Pressless could not find that entry.",
        "Go back to your list of entries and choose it again.",
    ),
    store.SlugInUse: _say(
        "Another entry already uses that address, so nothing was moved.",
        "Choose a different address and save again.",
    ),
    store.DanglingReply: _say(
        "A reply points at a comment that is not there, so nothing was saved.",
        "Send the details below to whoever helps you.",
    ),
    builder.BuildStopped: _say(
        "Pressless could not build your site from one of your files.",
        "Check the file named in the details below, then try again. If it keeps "
        "happening, send the details to whoever helps you.",
    ),
    builder.SiteFolderUnusable: _say(
        "Pressless could not write the folder your site is built into.",
        _AGAIN,
    ),
    insights.InsightsError: _say(
        "Google sent back an answer Pressless could not use.",
        "Try again later. If it keeps happening, send the details below to whoever "
        "helps you.",
    ),
    insights.NotConfigured: _say(
        "The visitor numbers are not set up.",
        "Set up the dashboard in Settings if you want to see them.",
    ),
    insights.Unreachable: _say(
        "Pressless could not reach Google.",
        "Check your internet connection and try again.",
    ),
    insights.Refused: _say(
        "Google would not let Pressless read your visitor numbers.",
        "Sign in to Google again from Settings.",
    ),
    insights.RateLimited: _say(
        "Google asked Pressless to wait before asking again.",
        "Try again later.",
    ),
    credentials.NoStore: _say(
        "Pressless found nowhere safe on this computer to keep {secret}.",
        "Send the details below to whoever helps you.",
    ),
    credentials.NotStored: _say(
        "Pressless does not have {secret} yet.",
        "Enter it again in Settings.",
    ),
    credentials.CredentialError: _say(
        "Pressless could not safely read {secret}.",
        "Enter it again in Settings. If this keeps happening, send the details below to "
        "whoever helps you.",
    ),
    settings.NotSetUp: _say(
        "Pressless is not set up yet.",
        "Go through setup first.",
    ),
    settings.SettingsError: _say(
        "Pressless could not read its settings.",
        "Pressless changed nothing in them. Send the details below to whoever helps you.",
    ),
    publisher.PublishError: _say(
        "GitHub answered in a way Pressless did not expect.",
        _AGAIN,
    ),
    publisher.Unreachable: _say(
        "Pressless could not reach GitHub.",
        "Check your internet connection and try again.",
    ),
    publisher.OutcomeUnknown: _say(
        "Pressless lost touch with GitHub while your site was being updated.",
        "Check your internet connection and click Publish again. Publishing again is safe "
        "and settles it.",
        Site.UNKNOWN,
    ),
    publisher.Refused: _say(
        "GitHub would not accept your publishing key.",
        "Enter your publishing key again in Settings, then try again.",
    ),
    publisher.RepositoryMissing: _say(
        "GitHub could not find your site's repository.",
        "Check the repository name in Settings, then click Publish again.",
    ),
    publisher.Conflict: _say(
        "Your site on GitHub changed while Pressless was publishing.",
        "Try again.",
    ),
    publisher.TooLarge: _say(
        "Something you are publishing is larger than GitHub accepts.",
        "If you added a large file, remove or shrink it. Then try again, and if it keeps "
        "happening, send the details below to whoever helps you.",
    ),
    publisher.RateLimited: _say(
        "GitHub asked Pressless to slow down.",
        "Wait a while, then try again.",
    ),
    publisher.NoPreviousState: _say(
        "There is no earlier version of your site to go back to.",
        "Nothing needs undoing.",
    ),
    publisher.SiteFolderMissing: _say(
        "Pressless could not find the folder your site is built into.",
        "Build your site again, then click Publish again. If it keeps happening, send the "
        "details below to whoever helps you.",
    ),
    publisher.StrayFile: _say(
        "Your site folder holds a file Pressless did not make.",
        "Remove that file from your site folder, then click Publish again.",
    ),
    publisher.SiteWouldBeEmptied: _say(
        "Publishing now would empty your site, so Pressless stopped.",
        "Build your site again, then click Publish again.",
    ),
    publisher.FetchNotWritten: _say(
        "Pressless could not save the earlier version of your site to this computer.",
        "Free some space on this computer's drive, then try again.",
    ),
    publisher.RemoteStateMissing: _say(
        "Something Pressless needed from GitHub was not there.",
        "Try again.",
    ),
    FolderNotOpened: _say(
        "Pressless could not open the folder.",
        "Use Copy location instead, and paste it into your file manager.",
    ),
}


def sentence_for(
    failure: BaseException, *, publishing: bool, secret: str | None = None
) -> Sentence:
    """The failure's own type's sentence, never a base's (§ 4.2).

    A subclass with no entry is unforeseen: a base's sentence is written for no
    situation in particular. An unforeseen failure while publishing says the
    outcome is unknown, because the Face cannot tell whether the site moved.
    """
    entry = SENTENCES.get(type(failure))
    if entry is None:
        site = Site.UNKNOWN if publishing else Site.UNCHANGED
        return Sentence(_UNFORESEEN_WHAT, site, _UNFORESEEN_NEXT)
    return Sentence(entry.what.replace("{secret}", secret or _UNNAMED_NOUN), entry.site, entry.next)


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


def render_failure(
    failure: BaseException, *, publishing: bool, secret: str | None = None
) -> str:
    """The three-part sentence and Show details, as an HTML fragment.

    Everything inserted is escaped: a failure's words are text, not markup. The
    fragment names the log by its file name and its folder by LABEL, never by a
    path; the page's own script fetches the path only when Copy is clicked.
    """
    sentence = sentence_for(failure, publishing=publishing, secret=secret)
    e = html.escape
    return (
        '<section class="failure">'
        f'<p class="what">{e(sentence.what)}</p>'
        f'<p class="site">{e(sentence.site.value)}</p>'
        f'<p class="next">{e(sentence.next)}</p>'
        "<details><summary>Show details</summary>"
        f"<pre>{e(details_for(failure))}</pre>"
        f"<p>The log is {e(log.FILE_NAME)}, and the older part of it {e(log.OLD_NAME)}, "
        f"in {e(LABEL)}.</p>"
        '<button type="button" data-action="copy-location">Copy location</button> '
        '<button type="button" data-action="open-folder">Open folder</button>'
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
    items = "".join(
        f'<li><p class="what">{e(notice.text)}</p>'
        f'<p class="site">{e(notice.site.value)}</p>'
        f'<p class="next">{e(NOTICE_NEXT)}</p></li>'
        for notice in shown
    )
    return f'<ul class="notices">{items}</ul>'


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class Reply:
    """A page's answer sent as it is, unwrapped (PRESS-0012 § 4.3)."""
    body: bytes
    content_type: str
    status: int = 200
    location: str | None = None


Page = Callable[[Request], "str | Reply"]  # a str is the page's HTML body
Locate = Callable[[str], Path]

FILES_POLICY = ("default-src 'self'; img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; font-src 'self'; "
                "script-src 'self'; connect-src 'self'; frame-src 'none'; "
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
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}

# Every wrapped page carries this, so a frame on a Face page can only show an
# address the Face serves: a link followed in the preview never leaves.
_FRAMES_POLICY = "frame-src 'self'; frame-ancestors 'self'"

# Every other answer carries this alone. A page on another 127.0.0.1 port is
# the same site, so a frame of the Face would carry the cookie and its clicks
# the Face's own Origin (PRESS-0011 § 4.5).
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
    return "<h1>Pressless is running.</h1>"


def _is_secret(offered: str, secret: str) -> bool:
    """Constant-time, as bytes: compare_digest raises TypeError on a str holding
    a non-ASCII character, and a wrong secret is refused, never dropped
    (§ 4.5, PRESS-0135)."""
    return secrets.compare_digest(offered.encode("utf-8", "replace"), secret.encode("utf-8"))


# How long Open folder waits for xdg-open to say whether it managed. It hands
# the folder to the desktop's own opener and exits; one that is still running
# after this is taken to have opened it.
_OPENER_SECONDS = 5


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
            f"the opener could not start: {exc.strerror or type(exc).__name__}"
        ) from None
    try:
        code = opener.wait(timeout=_OPENER_SECONDS)
    except subprocess.TimeoutExpired:
        return
    if code != 0:
        raise FolderNotOpened(f"the opener could not open it (it answered {code})")


# The buttons' script. It lives in the page, never in a fragment, and it asks
# for the path only when Copy is clicked, so the path is never in the document.
_SCRIPT = """
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "copy-location") {
    const answer = await fetch("/folder/location");
    if (answer.ok) await navigator.clipboard.writeText(await answer.text());
  } else if (button.dataset.action === "open-folder") {
    const answer = await fetch("/folder/open", {method: "POST"});
    if (!answer.ok) {
      // The answer is a Face page saying it could not open the folder.
      document.open(); document.write(await answer.text()); document.close();
    }
  }
});
"""


def _page(body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Pressless</title></head><body>{body}<script>{_SCRIPT}</script>"
        "</body></html>"
    )


# catch_warnings swaps process-wide state, so every capture in the process
# shares one lock (§ 4.4). Re-entrant so a capture nested on one thread works.
_CAPTURE_LOCK = threading.RLock()


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

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Write nothing: the standard one prints the request line, secret
        included, to the console (§ 4.5)."""
        return

    def do_GET(self) -> None:  # noqa: N802 -- the name http.server dispatches to
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def _send(
        self, status: int, body: str, content_type: str, headers: tuple[tuple[str, str], ...] = ()
    ) -> None:
        self._send_bytes(status, body.encode("utf-8"), f"{content_type}; charset=utf-8", headers)

    def _send_bytes(
        self, status: int, data: bytes, content_type: str,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if not any(name == "Content-Security-Policy" for name, _ in headers):
            self.send_header("Content-Security-Policy", _ANCESTORS_POLICY)
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _refuse(self) -> None:
        self._send(403, "Forbidden", "text/plain")

    def _has_cookie(self, face: Face) -> bool:
        try:
            jar = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return False
        morsel = jar.get(face._cookie)
        return morsel is not None and _is_secret(morsel.value, face._session)

    def _dispatch(self, method: str) -> None:
        face = self.server.face
        if self.headers.get("Host") != face._host:
            self._refuse()
            return
        parts = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if method == "GET" and "t" in query:
            # The link is honoured once: it reached the browser on its command
            # line, so it must not stay the key for the whole run (§ 4.5).
            with face._link_lock:
                honoured = not face._link_spent and _is_secret(query["t"], face._secret)
                face._link_spent = face._link_spent or honoured
            if not honoured:
                self._refuse()
                return
            cookie = f"{face._cookie}={face._session}; HttpOnly; SameSite=Strict; Path=/"
            self._send(
                303,
                "",
                "text/plain",
                (("Set-Cookie", cookie), ("Location", parts.path or "/")),
            )
            return
        if not self._has_cookie(face):
            self._refuse()
            return
        if method == "POST":
            origin = self.headers.get("Origin")
            if origin is not None and origin != face._origin:
                self._refuse()
                return

        if method == "GET" and parts.path == "/folder/location":
            self._send(200, str(face._folder), "text/plain")
            return
        if method == "POST" and parts.path == "/folder/open":
            try:
                _open_folder(face._folder)
            except FolderNotOpened as exc:
                self._send(500, _page(face.fail(exc, publishing=False)), "text/html")
                return
            self._send(204, "", "text/plain")
            return

        registered = face._pages.get((method, parts.path))
        if registered is None:
            self._send_file(method, parts.path, face)
            return
        page, publishing = registered
        length = int(self.headers.get("Content-Length") or 0) if method == "POST" else 0
        request = Request(method, parts.path, query, self.rfile.read(length) if length else b"")
        face._reply.after = []
        try:
            self._answer(face, page, request, publishing)
        finally:
            # PRESS-0023 § 4.9 step 5: what runs once this answer is sent.
            actions, face._reply.after = face._reply.after, None
            if actions:
                self.wfile.flush()
                for action in actions:
                    action()

    def _answer(self, face: Face, page: Page, request: Request, publishing: bool) -> None:
        try:
            body = page(request)
        except Exception as exc:  # noqa: BLE001 -- § Errors' last-resort catch
            self._send(500, _page(face.fail(exc, publishing=publishing)), "text/html",
                       (("Content-Security-Policy", _FRAMES_POLICY),))
            return
        if isinstance(body, Reply):
            location = (("Location", body.location),) if body.location is not None else ()
            self._send_bytes(body.status, body.body, body.content_type, location)
            return
        self._send(200, _page(body), "text/html",
                   (("Content-Security-Policy", _FRAMES_POLICY),))

    def _send_file(self, method: str, path: str, face: Face) -> None:
        """The longest registered prefix's file, or 404 (PRESS-0012 § 4.3)."""
        prefixes = [prefix for prefix in face._files if path.startswith(prefix)]
        target = None
        if method == "GET" and prefixes:
            prefix = max(prefixes, key=len)
            target = _served_file(path[len(prefix):], face._files[prefix])
        try:
            data = target.read_bytes() if target is not None else None
        except OSError:
            data = None  # unreadable is answered like absent, never as a failure
        if target is None or data is None:
            self._send(404, "Not found", "text/plain")
            return
        kind = _FILE_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send_bytes(200, data, kind, (
            ("Content-Security-Policy", FILES_POLICY),
            ("X-Content-Type-Options", "nosniff"),
        ))


class Face:
    """The running server. Made by `serve`; one per launch."""

    def __init__(self, folder: Path) -> None:
        self._folder = Path(folder)
        self._log = log.open_log(self._folder)
        self._secret = secrets.token_urlsafe(32)
        self._session = secrets.token_urlsafe(32)
        while self._session == self._secret:
            self._session = secrets.token_urlsafe(32)
        self._link_spent = False
        self._link_lock = threading.Lock()
        self._pages: dict[tuple[str, str], tuple[Page, bool]] = {}
        self._files: dict[str, Locate] = {}
        self._list_pieces: dict[bool, list[Callable[[], str]]] = {True: [], False: []}
        self._reply = threading.local()
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.face = self
        port = self._server.server_address[1]
        self._host = f"127.0.0.1:{port}"
        self._origin = f"http://{self._host}"
        # Browsers do not separate cookies by port, so the name carries it.
        self._cookie = f"pressless-{port}"
        self.url = f"http://{self._host}/?t={self._secret}"
        self.add_page("GET", "/", _running)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="pressless-face", daemon=True
        )
        self._thread.start()

    def add_page(self, method: str, path: str, page: Page, *, publishing: bool = False) -> None:
        """Register `page` for `method` and `path`, replacing any before it."""
        self._pages[(method.upper(), path)] = (page, publishing)

    def add_files(self, prefix: str, locate: Locate) -> None:
        """Answer GETs under `prefix`, which ends in "/", with the file `locate`
        names for the rest of the path (PRESS-0012 § 4.3)."""
        self._files[prefix] = locate

    def add_to_list(self, render: Callable[[], str], *, above: bool) -> None:
        """Have the list at / show `render()`'s HTML above or below the list
        (PRESS-0023 § 4.9), so a part can reach that page without the editor
        importing it."""
        self._list_pieces[above].append(render)

    def list_pieces(self, above: bool) -> list[str]:
        """What every part registered for that side of the list shows now."""
        return [render() for render in self._list_pieces[above]]

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
        with _CAPTURE_LOCK, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                yield notices
            finally:
                for warning in caught:
                    if issubclass(warning.category, (store.StoreNotice, settings.SettingsNotice)):
                        text = str(warning.message)
                        notices.append(text)
                        self._log.note(f"notice: {text}")

    def fail(self, failure: BaseException, *, publishing: bool, secret: str | None = None) -> str:
        """Note the failure's details in the log and return its fragment."""
        self._log.note(details_for(failure))
        return render_failure(failure, publishing=publishing, secret=secret)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        self._log.close()


def serve(folder: Path, *, open_browser: bool = True) -> Face:
    """Start the Face on 127.0.0.1, on a port the system chooses.

    Opens his browser at the one link carrying the secret, and prints that link
    to the console, which is his own, where no browser opens. With
    open_browser=False it prints nothing; that is how the tests run it.
    """
    face = Face(folder)
    if open_browser:
        try:
            opened = webbrowser.open(face.url)
        except Exception:  # noqa: BLE001 -- no browser is a case, not a failure
            opened = False
        if not opened:
            print(f"Pressless is running. Open this link in your browser: {face.url}")
    return face
