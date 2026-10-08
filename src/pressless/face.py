"""The Face (PRESS-0011): the local server, and the error contract.

The contract is docs/specs/PRESS-0011-face.md. Two jobs, and they are one job:
this is the web server on his own machine that his browser talks to, and it is
the one place a failure any part raises becomes a sentence he understands
(`docs/design.md` § Errors). Every part raises typed failures and writes no
prose; the sentences live here, keyed by the failure's class, and their words
in the words table (PRESS-0242).

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
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from pressless import (
    builder,
    credentials,
    github_signin,
    google_signin,
    insights,
    log,
    paths,
    publisher,
    settings,
    shortcuts,
    store,
    themes,
    words,
)
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


def _say(what: str, next_step: str, site: Site = Site.UNCHANGED, *,
         link: tuple[str, str] | None = None) -> Sentence:
    return Sentence(what, site, next_step, link)


# Keyed by the class object, never its name: publisher and insights both define
# Unreachable, Refused and RateLimited (§ 4.2). Each Publisher type's next step
# follows the answer PRESS-0009 § 4.1 pairs with it.
SENTENCES: dict[type[Exception], Sentence] = {
    paths.NotPackaged: _say(
        "failure.paths.NotPackaged.what",
        "failure.paths.NotPackaged.next",
    ),
    paths.FolderUnusable: _say(
        "failure.paths.FolderUnusable.what",
        "failure.paths.FolderUnusable.next",
    ),
    store.StoreError: _say("failure.store.StoreError.what", "failure.again"),
    store.EntryNotFound: _say(
        "failure.store.EntryNotFound.what",
        "failure.store.EntryNotFound.next",
    ),
    store.SlugInUse: _say(
        "failure.store.SlugInUse.what",
        "failure.store.SlugInUse.next",
    ),
    store.DanglingReply: _say(
        "failure.store.DanglingReply.what",
        "failure.store.DanglingReply.next",
    ),
    builder.BuildStopped: _say(
        "failure.builder.BuildStopped.what",
        "failure.builder.BuildStopped.next",
    ),
    builder.SiteFolderUnusable: _say(
        "failure.builder.SiteFolderUnusable.what",
        "failure.again",
    ),
    insights.InsightsError: _say(
        "failure.insights.InsightsError.what",
        "failure.insights.InsightsError.next",
    ),
    insights.NotConfigured: _say(
        "failure.insights.NotConfigured.what",
        "failure.insights.NotConfigured.next",
    ),
    insights.Unreachable: _say(
        "failure.insights.Unreachable.what",
        "failure.insights.Unreachable.next",
    ),
    insights.Refused: _say(
        "failure.insights.Refused.what",
        "failure.insights.Refused.next",
    ),
    insights.RateLimited: _say(
        "failure.insights.RateLimited.what",
        "failure.insights.RateLimited.next",
    ),
    google_signin.Declined: _say(
        "failure.google_signin.Declined.what",
        "failure.google_signin.Declined.next",
    ),
    google_signin.Expired: _say(
        "failure.google_signin.Expired.what",
        "failure.google_signin.Expired.next",
    ),
    credentials.NoStore: _say(
        "failure.credentials.NoStore.what",
        "failure.credentials.NoStore.next",
    ),
    credentials.NotStored: _say(
        "failure.credentials.NotStored.what",
        "failure.credentials.NotStored.next",
    ),
    # Setup's store step and first save raise this too, where nothing was
    # read and re-entering fixes nothing -- a locked keyring, or on Windows a
    # program started over a remote connection, which the vault refuses
    # (PRESS-0120, PRESS-0162). So it names reaching, and the unlock first.
    credentials.CredentialError: _say(
        "failure.credentials.CredentialError.what",
        "failure.credentials.CredentialError.next",
    ),
    settings.NotSetUp: _say(
        "failure.settings.NotSetUp.what",
        "failure.settings.NotSetUp.next",
    ),
    settings.SettingsError: _say(
        "failure.settings.SettingsError.what",
        "failure.settings.SettingsError.next",
    ),
    publisher.PublishError: _say(
        "failure.publisher.PublishError.what",
        "failure.again",
    ),
    publisher.Unreachable: _say(
        "failure.publisher.Unreachable.what",
        "failure.publisher.Unreachable.next",
    ),
    publisher.OutcomeUnknown: _say(
        "failure.publisher.OutcomeUnknown.what",
        "failure.publisher.OutcomeUnknown.next",
        Site.UNKNOWN,
    ),
    publisher.Refused: _say(
        "failure.publisher.Refused.what",
        "failure.publisher.Refused.next",
    ),
    publisher.SignInRefused: _say(
        "failure.publisher.SignInRefused.what",
        "failure.publisher.SignInRefused.next",
        link=("/setup/github", "failure.publisher.SignInRefused.link"),
    ),
    publisher.RepositoryMissing: _say(
        "failure.publisher.RepositoryMissing.what",
        "failure.publisher.RepositoryMissing.next",
    ),
    publisher.Conflict: _say(
        "failure.publisher.Conflict.what",
        "failure.publisher.Conflict.next",
    ),
    publisher.TooLarge: _say(
        "failure.publisher.TooLarge.what",
        "failure.publisher.TooLarge.next",
    ),
    publisher.RateLimited: _say(
        "failure.publisher.RateLimited.what",
        "failure.publisher.RateLimited.next",
    ),
    publisher.NoPreviousState: _say(
        "failure.publisher.NoPreviousState.what",
        "failure.publisher.NoPreviousState.next",
    ),
    publisher.SiteFolderMissing: _say(
        "failure.publisher.SiteFolderMissing.what",
        "failure.publisher.SiteFolderMissing.next",
    ),
    publisher.StrayFile: _say(
        "failure.publisher.StrayFile.what",
        "failure.publisher.StrayFile.next",
    ),
    publisher.SiteWouldBeEmptied: _say(
        "failure.publisher.SiteWouldBeEmptied.what",
        "failure.publisher.SiteWouldBeEmptied.next",
    ),
    publisher.FetchNotWritten: _say(
        "failure.publisher.FetchNotWritten.what",
        "failure.publisher.FetchNotWritten.next",
    ),
    publisher.UnfetchablePath: _say(
        "failure.publisher.UnfetchablePath.what",
        "failure.publisher.UnfetchablePath.next",
    ),
    publisher.RepositoryMoved: _say(
        "failure.publisher.RepositoryMoved.what",
        "failure.publisher.RepositoryMoved.next",
    ),
    publisher.RemoteStateMissing: _say(
        "failure.publisher.RemoteStateMissing.what",
        "failure.publisher.RemoteStateMissing.next",
    ),
    # PRESS-0231 § 4.2. The sign-in step words the first three as hints; these
    # are for anywhere else they reach.
    github_signin.Pending: _say(
        "failure.github_signin.Pending.what",
        "failure.github_signin.Pending.next",
    ),
    github_signin.Expired: _say(
        "failure.github_signin.Expired.what",
        "failure.github_signin.Expired.next",
    ),
    github_signin.Declined: _say(
        "failure.github_signin.Declined.what",
        "failure.github_signin.Declined.next",
    ),
    github_signin.SignedOut: _say(
        "failure.github_signin.SignedOut.what",
        "failure.github_signin.SignedOut.next",
        link=("/setup/github", "failure.github_signin.SignedOut.link"),
    ),
    FolderNotOpened: _say(
        "failure.face.FolderNotOpened.what",
        "failure.face.FolderNotOpened.next",
    ),
    shortcuts.ShortcutError: _say(
        "failure.shortcuts.ShortcutError.what",
        "failure.again",
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
    if entry is None:
        site = Site.UNKNOWN if publishing else Site.UNCHANGED
        return Sentence(say("failure.unforeseen.what"), site, say("failure.unforeseen.next"))
    # Where the Face named no secret, the sentence says "that secret".
    noun = secret or say("failure.unnamed_secret")
    link = (entry.link[0], say(entry.link[1])) if entry.link else None
    return Sentence(say(entry.what, secret=noun), entry.site, say(entry.next), link)


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
    return f"<h1>{say('face.running')}</h1>"


def _is_secret(offered: str, secret: str) -> bool:
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
document.addEventListener("click", (event) => {
  const view = event.target.closest("button[data-view-site]");
  if (view) window.open(view.dataset.viewSite, "_blank", "noopener");
});
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
// PRESS-0190: a theme is applied the moment it is picked, then remembered.
document.addEventListener("change", (event) => {
  const picker = event.target.closest("select[data-theme-picker]");
  if (!picker) return;
  if (picker.value === "follow") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = picker.value;
  fetch("/theme", {method: "POST", body: picker.value});
});
// PRESS-0228: a "?" beside a box opens its help; Close or Escape shuts it.
document.addEventListener("click", (event) => {
  const opener = event.target.closest("button[data-help]");
  if (opener) document.getElementById(opener.dataset.help).showModal();
  const closer = event.target.closest("button[data-close]");
  if (closer) closer.closest("dialog").close();
});
// PRESS-0236: a message box opens when its words change, so nothing beside a
// control moves. A save writing the same words again leaves it shut; words
// cleared away close it. Closing returns to the field it is about.
for (const box of document.querySelectorAll("dialog.message")) {
  const words = box.firstElementChild;
  let shown = "";
  const look = () => {
    const now = words.innerHTML.trim();
    if (now === shown) return;
    shown = now;
    if (!now) { if (box.open) box.close(); }
    else if (!box.open) box.showModal();
  };
  new MutationObserver(look).observe(words,
    {childList: true, subtree: true, characterData: true});
  look();
  box.addEventListener("close", () => {
    const field = box.dataset.focus &&
      document.querySelector(`[name="${CSS.escape(box.dataset.focus)}"]`);
    if (field) field.focus();
  });
}
// PRESS-0187: a dark look dims the preview; this switch shows its true colours.
document.addEventListener("change", (event) => {
  const box = event.target.closest("input[data-true-colours]");
  if (!box) return;
  document.getElementById("preview").classList.toggle("undimmed", box.checked);
});
"""

# PRESS-0242 § 4.3: a page script's words, gaps filled as words.say fills them.
# It reads the words block on each call and declares nothing else, because a
# failure page written over this one by document.write runs it a second time.
_SAY = r"""
function say(key, slots = {}) {
  const table = JSON.parse(document.getElementById("pressless-words").textContent);
  if (!(key in table)) throw new Error("no words for " + key);
  return table[key].replace(/\{\{|\}\}|\{(\w+)\}/g, (found, name) => {
    if (found === "{{") return "{";
    if (found === "}}") return "}";
    if (!(name in slots)) throw new Error("no " + name + " for " + key);
    return slots[name];
  });
}
"""


# The Face's look (PRESS-0178, PRESS-0189). The colours are a theme's
# (themes.py, PRESS-0190); with none chosen they follow the computer, light or
# dark. Every rule sits under `.face`, because the editor links his site's
# stylesheets into this same document and a bare `body` or `a` rule of his
# would otherwise restyle the Face. The box keeps his site's font, and takes its
# colours only where his stylesheet sets none.
_SHAPES = """
body.face { margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.55 system-ui, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; }
.face .bar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center;
  flex-wrap: wrap;
  gap: .6rem; padding: .6rem 1.5rem; background: var(--sheet);
  border-bottom: 1px solid var(--line); box-shadow: 0 2px 10px var(--shadow); }
.face .bar svg { width: 1.3rem; height: auto; }
.face .bar svg [fill]:not([fill="none"]), .face .bar svg g { fill: var(--amber); }
.face .bar b { font: 700 1.2rem/1 Arial, Calibri, "Liberation Sans", Helvetica, sans-serif; }
.face .bar b span { font-family: system-ui, "Segoe UI", sans-serif; font-weight: 400; }
.face .bar .theme { margin: 0 0 0 auto; flex-direction: row; align-items: center; gap: .5rem; }
.face .bar .theme select { padding: .3rem .5rem; }
.face .bar > a { margin-left: .6rem; font-weight: 600; }
.face main { max-width: 72rem; margin: 0 auto; padding: 2rem 1.5rem 3rem; }
.face h1, .face h2 { font-family: Arial, Calibri, "Liberation Sans", Helvetica, sans-serif;
  font-weight: 600; line-height: 1.2; }
.face h1 { font-size: 2.1rem; margin: .25rem 0 1.5rem; letter-spacing: -.01em; }
.face h2 { font-size: 1.3rem; margin: 2rem 0 .75rem; }
.face .card { background: var(--sheet); border: 1px solid var(--line); border-radius: 14px;
  padding: 1.1rem 1.4rem; margin: 1.25rem 0; box-shadow: 0 4px 18px var(--shadow); }
.face .card > h2:first-child { margin-top: 0; }
.face .card > :last-child { margin-bottom: 0; }
.face a { color: var(--amber-ink); text-underline-offset: .15em; }
.face ul { padding-left: 1.2rem; }
.face li { margin: .3rem 0; }
.face small, .face .hint, .face [id$="-hint"], .face [id$="-status"] { color: var(--soft); }
.face label { display: inline-flex; flex-direction: column; gap: .25rem;
  margin: 0 1rem .75rem 0; font-size: .9rem; color: var(--soft); vertical-align: bottom; }
.face input, .face select, .face :where(textarea) { font: inherit; color: var(--ink);
  background: var(--paper); border: 1px solid var(--line); border-radius: 10px;
  padding: .5rem .7rem; }
.face input:focus, .face select:focus, .face :where(textarea:focus), .face button:focus-visible {
  outline: 2px solid var(--amber); outline-offset: 2px; }
.face button { font: inherit; font-weight: 600; cursor: pointer; color: var(--ink);
  background: var(--sheet); border: 1px solid var(--line); border-radius: 999px;
  padding: .5rem 1.1rem; vertical-align: bottom; box-shadow: 0 1px 3px var(--shadow);
  transition: border-color .15s, transform .15s, box-shadow .15s; }
.face label + button, .face label ~ button { margin-bottom: .75rem; }
.face .switch-row { display: flex; align-items: center; justify-content: space-between;
  gap: 1rem 1.5rem; flex-wrap: wrap; margin: 1.25rem 0; padding: .9rem 1.4rem;
  background: var(--sheet); border: 1px solid var(--line); border-radius: 14px; }
.face .switch-row p { margin: 0; }
.face .switch-row > .states { flex: 1 1 22rem; }
.face form.switch-row > button:only-of-type { flex: none; margin: 0; background: var(--paper);
  color: var(--ink); border-color: var(--line); }
.face .site-line { margin: -.4rem 0 1rem; color: var(--soft); }
.face button.help { padding: .4rem .8rem; min-width: 2.4rem; }
.face dialog { max-width: min(42rem, calc(100vw - 2rem)); color: var(--ink);
  background: var(--sheet); border: 1px solid var(--line); border-radius: 14px;
  padding: 1.1rem 1.4rem; box-shadow: 0 8px 30px var(--shadow); }
.face dialog::backdrop { background: rgba(0, 0, 0, .5); }
.face button:hover { border-color: var(--amber); transform: translateY(-1px);
  box-shadow: 0 3px 10px var(--shadow); }
.face button:disabled, .face button:disabled:hover { opacity: .45; cursor: not-allowed;
  border-color: var(--line); transform: none; box-shadow: none; }
.face .press-status { min-height: 4.5em; }
.face dialog.message [id] { color: var(--ink); }
.face [aria-invalid="true"] { outline: 3px solid var(--amber-ink); outline-offset: 2px; }
.face #save-status { display: inline-block; min-width: 6em; }
.face #photograph-status { display: block; min-height: 1.55em; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.face #editor > #photograph-missing { min-height: 4.65em; max-height: 4.65em;
  overflow-y: auto; margin-top: 0; }
.face #photograph-missing[hidden] { display: block; visibility: hidden; }
.face #address[hidden] { display: inline; visibility: hidden; }
.face .sign-in-slot { min-height: 6.5em; }
.face .states, .face #standing { display: grid; }
.face .states > * { grid-area: 1 / 1; }
.face #standing > [data-when="1"]:not(form) { grid-area: 1 / 1; }
.face #standing > form[data-when="1"] { grid-area: 2 / 1; }
.face #standing > [data-when="0"] { grid-area: 1 / 1 / 3 / 2; }
.face .states [hidden], .face #standing [hidden] { display: block; visibility: hidden; }
.face #standing[hidden] { display: grid; visibility: hidden; }
.face #save-hint { min-height: 4.7em; }
.face [data-editor="publish"], .face form > button:only-of-type { background: var(--press);
  color: var(--on-press); border-color: var(--press); }
.face #editor { display: flex; flex-wrap: wrap; align-items: flex-end; }
.face #editor > p { flex-basis: 100%; margin: .25rem 0 .75rem; }
.face :where(textarea) { box-sizing: border-box; width: 100%; }
.face :where(#editor textarea) { flex-basis: 100%; min-height: 60vh; resize: vertical;
  padding: 1rem 1.2rem; }
.face details { margin: 1rem 0; }
.face summary { cursor: pointer; color: var(--soft); }
.face table { border-collapse: collapse; margin: .5rem 0; }
.face th, .face td { text-align: left; padding: .4rem .8rem .4rem 0;
  border-bottom: 1px solid var(--line); vertical-align: top; }
.face code, .face pre { font: .9em/1.4 ui-monospace, Consolas, "DejaVu Sans Mono", monospace; }
.face pre { white-space: pre-wrap; background: var(--paper); padding: .7rem;
  border-radius: 10px; }
.face .failure, .face .notices > li { list-style: none; margin: 1rem 0;
  padding: .9rem 1.1rem; background: var(--sheet); border: 1px solid var(--line);
  border-left: 5px solid var(--alert); border-radius: 12px; box-shadow: 0 4px 18px var(--shadow); }
.face .notices { padding: 0; }
.face .notices > li { border-left-color: var(--amber); }
.face .failure p, .face .notices p { margin: .2rem 0; }
.face .failure .what, .face .notices .what { font-weight: 600; }
.face iframe#preview { width: 100%; min-height: 70vh; border: 1px solid var(--line);
  border-radius: 12px; background: #fff; filter: var(--preview-dim); }
.face iframe#preview.undimmed { filter: none; }
.face .true-colours { display: var(--preview-switch); margin: 0 0 .5rem; }
.face .true-colours label { margin: 0; }
.face label:has(> input[type="radio"]), .face label:has(> input[type="checkbox"]) {
  flex-direction: row; align-items: center; gap: .5rem; font-size: 1rem; color: var(--ink);
  cursor: pointer; }
.face input[type="radio"], .face input[type="checkbox"] { width: 1.25rem; height: 1.25rem;
  margin: 0; padding: 0; accent-color: var(--amber); flex: none; }
.face fieldset.looks { border: 0; margin: 0 0 1rem; padding: 0; }
.face fieldset.looks legend { padding: 0; margin-bottom: .5rem; }
.face label.look { display: flex; margin: 0 0 .75rem; }
.face .mini { flex: none; display: grid; width: 6rem; height: 4rem; overflow: hidden;
  border: 1px solid var(--soft); border-radius: 6px; }
.face .mini-sunrise { grid-template-rows: 1.4rem 1fr .7rem; }
.face .mini-sunrise > :nth-child(1) { background: #9a3412; }
.face .mini-sunrise > :nth-child(2) { background: #fffaf2; }
.face .mini-sunrise > :nth-child(3) { background: #f3e3cf; }
.face .mini-meadow { grid-template-columns: 1.8rem 1fr; grid-template-rows: 1fr .5rem; }
.face .mini-meadow > :nth-child(1) { background: #1f4d2b; grid-row: 1 / 3; }
.face .mini-meadow > :nth-child(2), .face .mini-meadow > :nth-child(3) { background: #f6f8f4; }
.face .mini-meadow > :nth-child(3) { border-top: 1px solid #c9d6c9; }
.face .mini-harbour { grid-template-rows: 1rem 1fr .9rem; }
.face .mini-harbour > :nth-child(1), .face .mini-harbour > :nth-child(3) { background: #14213d; }
.face .mini-harbour > :nth-child(2) { background: #ffffff; }
.face main:has(> #editor) { display: flex; flex-direction: column; }
.face main > #undo-result { order: -1; }
@media (min-width: 70rem) {
  .face main:has(> #editor) { max-width: none; display: grid; column-gap: 2rem;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .face main:has(> #editor) > * { grid-column: 1; }
  .face main > #proof { grid-column: 2; grid-row: 1 / span 12; align-self: start;
    position: sticky; top: 4.5rem; height: calc(100vh - 6rem);
    display: flex; flex-direction: column; }
  .face #proof > #preview { flex: 1; min-height: 0; }
}
@media (prefers-reduced-motion: reduce) { .face button { transition: none; }
  .face button:hover { transform: none; } }
@media print { .face .bar { display: none; } body.face { background: #fff; color: #000; }
  .face .card { box-shadow: none; } }
"""

_STYLE = (
    f":root {{ color-scheme: light dark; {themes.declarations(themes.find('light'))}"
    f" --shadow: rgba(60, 40, 10, .10); {themes.preview(False)} }}\n"
    f"@media (prefers-color-scheme: dark) {{ :root {{ {themes.declarations(themes.find('dark'))}"
    f" --shadow: rgba(0, 0, 0, .45); {themes.preview(True)} }} }}\n"
    + themes.css() + _SHAPES
)


def message_box(inner_id: str, content: str = "", *, focus: str = "") -> str:
    """PRESS-0236: a message that opens over the page, so nothing beside a
    control moves when it appears. Scripts write into `inner_id`; the Face's
    script opens the box whenever those words change, OK closes it, and
    closing returns to the field named `focus`, where one is named."""
    to = f' data-focus="{html.escape(focus, quote=True)}"' if focus else ""
    return (f'<dialog class="message"{to}><div id="{inner_id}">{content}</div>'
            f'<p><button type="button" data-close>{say("face.message.ok")}</button></p>'
            "</dialog>")


def true_colours() -> str:
    """Sits above each editor's preview; shown only on a dark look (PRESS-0187)."""
    return ('<p class="true-colours"><label><input type="checkbox" data-true-colours>'
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


def _page(body: str, theme: str = themes.FOLLOW, site: str = "") -> str:
    chosen = "" if theme == themes.FOLLOW else f' data-theme="{html.escape(theme, quote=True)}"'
    # PRESS-0232: the editors' publish notes copy this link, so it is the one
    # place a page reads the site's address from.
    visit = (f'<a href="{html.escape(site, quote=True)}" target="_blank" rel="noopener" '
             f"data-site>{say('face.view_site')}</a>" if site else "")
    return (
        f'<!doctype html><html lang="en"{chosen}><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Pressless</title><link rel="icon" href="{_ICON}">'
        f"<style>{_STYLE}</style>"
        # PRESS-0242 § 4.3: before <main>, whose scripts run as they load.
        '<script type="application/json" id="pressless-words">'
        f"{words.for_scripts()}</script><script>{_SAY}</script></head>"
        f'<body class="face"><header class="bar">{_MARK}<b>Press<span>less</span></b>'
        f'{themes.picker(theme)}{visit}<a href="/setup">{say("face.settings")}</a>'
        # PRESS-0179: on every screen, failure pages included.
        f'<a href="/report">{say("face.report")}</a></header>'
        f"<main>{body}</main><script>{_SCRIPT}</script></body></html>"
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
        self._drain()
        self._send(403, say("face.forbidden"), "text/plain")

    def _drain(self) -> None:
        """Read and drop a body that will not be used, so the answer arrives.

        Closing a socket with unread bytes resets it, and the sender sees a
        dropped connection rather than the answer: WinError 10053 on Windows
        CI, a broken pipe on Linux for a body past the socket buffers.
        """
        left = _length(self.headers.get("Content-Length")) or 0
        while left > 0:
            chunk = self.rfile.read(min(left, 64 * 1024))
            if not chunk:
                return
            left -= len(chunk)

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
        if not self._has_cookie(face) and not (method == "GET" and parts.path in face._returns):
            # The one door without the cookie: a page Google's redirect lands on,
            # which authenticates the request itself (PRESS-0122 § 4.3).
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
                self._send(500, _page(face.fail(exc, publishing=False), face._theme,
                                      face.live_address()), "text/html")
                return
            self._send(204, "", "text/plain")
            return
        if method == "POST" and parts.path == "/theme":
            self._choose_theme(face)
            return

        registered = face._pages.get((method, parts.path))
        if registered is None:
            self._drain()
            self._send_file(method, parts.path, face)
            return
        page, publishing = registered
        length = _length(self.headers.get("Content-Length")) if method == "POST" else 0
        if length is None:
            # Unparseable or negative: read(-1) would wait for the client to
            # close, holding this thread (PRESS-0162).
            self._send(400, "", "text/plain")
            return
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

    def _choose_theme(self, face: Face) -> None:
        """PRESS-0190: remember the theme the picker has already applied."""
        length = _length(self.headers.get("Content-Length"))
        if length is None or length > _THEME_LIMIT:
            self._drain()
            self._send(400, "", "text/plain")
            return
        key = self.rfile.read(length).decode("utf-8", "replace")
        if not themes.known(key):
            self._send(400, "", "text/plain")
            return
        try:
            themes.write_choice(face._folder, key)
        except OSError:
            # The page has the theme already; only the next start forgets it.
            face._log.note("the theme could not be saved")
            self._send(500, "", "text/plain")
            return
        face._theme = key
        self._send(204, "", "text/plain")

    def _answer(self, face: Face, page: Page, request: Request, publishing: bool) -> None:
        try:
            body = page(request)
        except Exception as exc:  # noqa: BLE001 -- § Errors' last-resort catch
            self._send(500, _page(face.fail(exc, publishing=publishing), face._theme,
                                  face.live_address()), "text/html",
                       (("Content-Security-Policy", _FRAMES_POLICY),))
            return
        if isinstance(body, Reply):
            location = (("Location", body.location),) if body.location is not None else ()
            self._send_bytes(body.status, body.body, body.content_type, location)
            return
        self._send(200, _page(body, face._theme, face.live_address()), "text/html",
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
            self._send(404, say("face.not_found"), "text/plain")
            return
        kind = _FILE_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send_bytes(200, data, kind, (
            ("Content-Security-Policy", FILES_POLICY),
            ("X-Content-Type-Options", "nosniff"),
        ))


# How often the server's loop checks whether it has been asked to stop, in
# seconds; `stop` waits up to this long. The standard library's own default.
# tests/conftest.py shortens it: the suite starts and stops hundreds of servers.
_POLL_SECONDS = 0.5

# The longest theme key with room to spare; a longer body is not a key.
_THEME_LIMIT = 64


class Face:
    """The running server. Made by `serve`; one per launch."""

    def __init__(self, folder: Path, port: int = 0) -> None:
        self._folder = Path(folder)
        self._log = log.open_log(self._folder)
        self._theme = themes.read_choice(self._folder)
        self._secret = secrets.token_urlsafe(32)
        self._session = secrets.token_urlsafe(32)
        while self._session == self._secret:
            self._session = secrets.token_urlsafe(32)
        self._link_spent = False
        self._link_lock = threading.Lock()
        self._pages: dict[tuple[str, str], tuple[Page, bool]] = {}
        self._returns: set[str] = set()
        self._files: dict[str, Locate] = {}
        self._list_pieces: dict[bool, list[Callable[[], str]]] = {True: [], False: []}
        self._unseen: list[Callable[[], bool]] = []
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
        """Register `page` for `method` and `path`, replacing any before it."""
        self._pages[(method.upper(), path)] = (page, publishing)

    def add_return_page(self, path: str, page: Page) -> None:
        """Register `page` for GET `path`, reached WITHOUT the session cookie.

        For the page another site's redirect lands on, which a SameSite=Strict
        cookie never reaches. Every other check still runs; the page must
        authenticate the request itself (PRESS-0122 § 4.3).
        """
        self.add_page("GET", path, page)
        self._returns.add(path)

    @property
    def origin(self) -> str:
        """`http://127.0.0.1:<port>`, the Face's own origin."""
        return self._origin

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

    def live_address(self) -> str:
        """The site's address for the top bar (PRESS-0232), or "" before setup
        or where the settings file cannot be read: the page still renders, and
        the failure is told where the settings are used."""
        try:
            return settings.load(self._folder).site_address
        except (settings.NotSetUp, settings.SettingsError):
            return ""

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
        with _CAPTURE_LOCK, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                yield notices
            finally:
                for warning in caught:
                    if issubclass(warning.category, (store.StoreNotice, settings.SettingsNotice)):
                        notice = warning.message
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
        self._log.close()


def serve(folder: Path, port: int = 0) -> Face:
    """Start the Face on 127.0.0.1, on a port the system chooses.

    A caller naming `port` gets that port or the bind's OSError; only the
    practice copy's start script names one (PRESS-0202).

    Opens no browser and prints nothing: the launcher (PRESS-0013 § 4.5) owns
    which page opens first and the link printed where no browser opens.
    """
    return Face(folder, port)
