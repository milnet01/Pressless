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

from pressless import credentials, insights, log, paths, publisher, settings, store

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


@dataclass(frozen=True)
class Sentence:
    what: str  # what happened, in his words; may hold the "{secret}" slot
    site: Site  # what it means for his site
    next: str  # what to do next


class FolderNotOpened(Exception):
    """The platform's opener is missing or failed (§ 6)."""


def _say(what: str, next_step: str, site: Site = Site.UNCHANGED) -> Sentence:
    return Sentence(what, site, next_step)


_AGAIN = "Try again. If it keeps happening, send the details below to whoever helps you."
_PUBLISH_AGAIN = (
    "Click Publish again. If it keeps happening, send the details below to whoever helps you."
)

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
        "Go through setup again. If this keeps happening, send the details below to "
        "whoever helps you.",
    ),
    publisher.PublishError: _say(
        "GitHub answered in a way Pressless did not expect.",
        _PUBLISH_AGAIN,
    ),
    publisher.Unreachable: _say(
        "Pressless could not reach GitHub.",
        "Check your internet connection and click Publish again.",
    ),
    publisher.OutcomeUnknown: _say(
        "Pressless lost touch with GitHub while your site was being updated.",
        "Check your internet connection and click Publish again. Publishing again is safe "
        "and settles it.",
        Site.UNKNOWN,
    ),
    publisher.Refused: _say(
        "GitHub would not accept your publishing key.",
        "Enter your publishing key again in Settings, then click Publish again.",
    ),
    publisher.RepositoryMissing: _say(
        "GitHub could not find your site's repository.",
        "Check the repository name in Settings, then click Publish again.",
    ),
    publisher.Conflict: _say(
        "Your site on GitHub changed while Pressless was publishing.",
        "Click Publish again.",
    ),
    publisher.TooLarge: _say(
        "Something you are publishing is larger than GitHub accepts.",
        "Remove or shrink the largest file you added, then click Publish again.",
    ),
    publisher.RateLimited: _say(
        "GitHub asked Pressless to slow down.",
        "Wait a while, then click Publish again.",
    ),
    publisher.NoPreviousState: _say(
        "There is no earlier version of your site to go back to.",
        "Nothing needs undoing.",
    ),
    publisher.SiteFolderMissing: _say(
        "Pressless could not find the folder your site is built into.",
        "Check the site folder in Settings, then click Publish again.",
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
        "Click Publish again.",
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


def render_notices(notices: list[str]) -> str:
    """Each notice in the three parts § Errors requires, escaped (§ 4.4).

    A notice names files he named himself, so its words are text, not markup.
    """
    if not notices:
        return ""
    e = html.escape
    items = "".join(
        f'<li><p class="what">{e(notice)}</p>'
        f'<p class="site">{e(Site.UNCHANGED.value)}</p>'
        f'<p class="next">{e(NOTICE_NEXT)}</p></li>'
        for notice in notices
    )
    return f'<ul class="notices">{items}</ul>'


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str]
    body: bytes


Page = Callable[[Request], str]  # returns the page's HTML body


def _running(request: Request) -> str:
    return "<h1>Pressless is running.</h1>"


def _open_folder(folder: Path) -> None:
    """Open `folder` in the platform's file manager. Raises FolderNotOpened."""
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 -- a folder path, never a shell command
        else:
            subprocess.Popen(  # noqa: S603 -- a fixed program and one path argument
                ["xdg-open", str(folder)],  # noqa: S607 -- xdg-open is found on PATH by design
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError as exc:
        raise FolderNotOpened(
            f"the opener could not start: {exc.strerror or type(exc).__name__}"
        ) from None


# The buttons' script. It lives in the page, never in a fragment, and it asks
# for the path only when Copy is clicked, so the path is never in the document.
_SCRIPT = """
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "copy-location") {
    const answer = await fetch("/folder/location");
    await navigator.clipboard.writeText(await answer.text());
  } else if (button.dataset.action === "open-folder") {
    await fetch("/folder/open", {method: "POST"});
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
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
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
        return morsel is not None and secrets.compare_digest(morsel.value, face._secret)

    def _dispatch(self, method: str) -> None:
        face = self.server.face
        if self.headers.get("Host") != face._host:
            self._refuse()
            return
        parts = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if method == "GET" and "t" in query:
            if not secrets.compare_digest(query["t"], face._secret):
                self._refuse()
                return
            cookie = f"{face._cookie}={face._secret}; HttpOnly; SameSite=Strict; Path=/"
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
            self._send(404, "Not found", "text/plain")
            return
        page, publishing = registered
        length = int(self.headers.get("Content-Length") or 0) if method == "POST" else 0
        request = Request(method, parts.path, query, self.rfile.read(length) if length else b"")
        try:
            body = page(request)
        except Exception as exc:  # noqa: BLE001 -- § Errors' last-resort catch
            self._send(500, _page(face.fail(exc, publishing=publishing)), "text/html")
            return
        self._send(200, _page(body), "text/html")


class Face:
    """The running server. Made by `serve`; one per launch."""

    def __init__(self, folder: Path) -> None:
        self._folder = Path(folder)
        self._log = log.open_log(self._folder)
        self._secret = secrets.token_urlsafe(32)
        self._pages: dict[tuple[str, str], tuple[Page, bool]] = {}
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
