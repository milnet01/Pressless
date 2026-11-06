"""Publish: one button writes, builds and publishes (PRESS-0013).

The Face owns the order (docs/design.md rule 1): save the box, read Settings
and the key, move the entry into what is published, build, then upload. A
definite failure puts his files back, so his list never says an entry is on
the site when it is not; an upload whose outcome is unknown is left published,
and publishing again settles it (docs/specs/PRESS-0013-publish.md § 4.3).
"""
from __future__ import annotations

import dataclasses
import hashlib
import html
import json
import urllib.parse
import warnings
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pressless import (
    builder,
    editor,
    github_setup,
    pressing,
    publisher,
    settings,
    starter,
    store,
    takeover,
)
from pressless.face import (
    SENTENCES,
    Face,
    Notice,
    Reply,
    Request,
    Sentence,
    Site,
    gatherer,
    message_box,
    nothing_captured,
    render_notices,
)
from pressless.words import say

MESSAGE = "Publish {slug}"     # the commit message; {slug} is the entry's address

# The header marking a draft undo demoted (PRESS-0015 § 4.5). Nothing parses the
# value -- it is the moment of the demotion, written so that a person reading his
# own file can see what happened. Presence is what is read. Spelled in editor,
# whose list labels it (PRESS-0015 § 4.6) and which this module imports.
UNDONE = editor.UNDONE



class NothingToPublish(Exception):
    """No published entry would remain (docs/design.md rule 9)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[NothingToPublish] = Sentence(
    "failure.publishing.NothingToPublish.what",
    Site.UNCHANGED,
    "failure.publishing.NothingToPublish.next",
)


class JournalOff(Exception):
    """An entry was asked to publish with the journal off (PRESS-0214 § 4.3)."""


SENTENCES[JournalOff] = Sentence(
    "failure.publishing.JournalOff.what",
    Site.UNCHANGED,
    "failure.publishing.JournalOff.next",
)

class WouldReplaceASite(Exception):
    """The starter site's first publish met a repository already holding a
    site (PRESS-0126 § 4.5)."""


REPLACE_ADDRESS = "/publish/replace"


class TakeoverOwed(Exception):
    """The site is still built by GitHub Actions, so a publish would never reach
    the web, and the build would run over it (PRESS-0333 § 4.5)."""


TAKEOVER_ADDRESS = "/publish/takeover"

SENTENCES[TakeoverOwed] = Sentence(
    "failure.publishing.TakeoverOwed.what",
    Site.UNCHANGED,
    "failure.publishing.TakeoverOwed.next",
)

SENTENCES[WouldReplaceASite] = Sentence(
    "failure.publishing.WouldReplaceASite.what",
    Site.UNCHANGED,
    "failure.publishing.WouldReplaceASite.next",
)

class KeptFolderBuilt(Exception):
    """The built site fills a folder or file Settings keeps on GitHub, which a
    publish would leave as it was (PRESS-0197 § 4.7, PRESS-0227 § 4.4)."""

    def __init__(self, message: str, folder: str) -> None:
        super().__init__(message)
        self.slots = {"folder": folder}


SENTENCES[KeptFolderBuilt] = Sentence(
    "failure.publishing.KeptFolderBuilt.what",
    Site.UNCHANGED,
    "failure.publishing.KeptFolderBuilt.next",
)

# GitHub Pages serves either as a site's front page (PRESS-0126 § 3 decision 5).
A_SITE = frozenset({"index.html", "index.md"})

def replace_link(failure: BaseException) -> str:
    """The way to the replace page, beside a WouldReplaceASite failure, or to the
    takeover, beside a TakeoverOwed; a Sentence is escaped text and cannot carry it."""
    if isinstance(failure, TakeoverOwed):
        return f'<p><a href="{TAKEOVER_ADDRESS}">{say("publishing.takeover")}</a></p>'
    if not isinstance(failure, WouldReplaceASite):
        return ""
    return f'<p><a href="{REPLACE_ADDRESS}">{say("publishing.replace")}</a></p>'


@dataclass(frozen=True)
class Published:
    outcome: publisher.Outcome
    copy_kept: bool          # § 4.3 step 5 could not bin the working copy


def _now() -> datetime:
    return datetime.now()


def undone_stamp() -> str:
    """The moment of a demotion, for the `UNDONE` header (PRESS-0015 § 4.5)."""
    return _now().replace(microsecond=0).isoformat(sep=" ")


def publish(folder: Path, settings: settings.Settings, key: str, *, entry: str | None,
            emptying: bool = False, taking_over: bool = False,
            capture: Callable[[], AbstractContextManager[list[str]]] = nothing_captured,
            notices: list[str | Notice] | None = None,
            transport: publisher.Transport | None = None) -> Published:
    """§ 4.3: move the entry, guard, build, upload, finish. `capture` wraps every
    step but the upload, and what each capture gathers is added to `notices`."""
    folder = Path(folder)
    gathered = notices if notices is not None else []

    captured = gatherer(capture, gathered)

    # PRESS-0214 § 4.3: before the move, so nothing has moved to put back.
    if entry is not None and not captured(lambda: store.journal_on(folder)):
        raise JournalOff("the journal is off")
    moved = captured(lambda: _move(folder, entry))

    def guard_and_build() -> None:
        if takeover.owed(folder) and not taking_over:    # PRESS-0333 § 4.5
            raise TakeoverOwed("the site is still built by GitHub Actions")
        # PRESS-0126 § 4.5: the starter's first publish, whether or not
        # emptying, refuses where the repository holds a site. The fold is
        # PRESS-0009 § 4.4's.
        if starter.unpublished(folder) and any(
                name.rstrip("/").casefold() in A_SITE
                for name in publisher.root_entries(settings, key, transport)):
            raise WouldReplaceASite("the repository already holds a site")
        if (not emptying and store.journal_on(folder)
                and not store.list_slugs(folder, draft=False)):
            raise NothingToPublish("no published entry would remain")
        builder.build(folder, settings, settings.site_folder)
        # PRESS-0197 § 4.7: the Publisher leaves a kept folder alone, so a
        # build filling one would be dropped in silence.
        kept = {name.rstrip("/").casefold(): name.rstrip("/") for name in settings.untouchable}
        produced = {name.casefold() for name in builder.roots_produced(folder)}
        for child in sorted(settings.site_folder.iterdir()):
            if child.name.casefold() in produced and child.name.casefold() in kept:
                folder_name = kept[child.name.casefold()]
                raise KeptFolderBuilt(f"the build fills {folder_name}, which Settings keeps",
                                      folder_name)

    def bin_copy_failed() -> bool:
        """Bin the working copy the move left; True where that failed."""
        if moved is None or not moved.copy:
            return False
        try:
            for path in moved.copy:
                captured(lambda target=path: store.move_to_bin(folder, target))
        except Exception:  # noqa: BLE001 -- never replaces the publish's result (§ 4.3 step 5)
            return True
        return False

    interrupted = False
    try:
        captured(guard_and_build)
        message = MESSAGE.format(slug=moved.published if moved else "site")
        try:
            outcome = publisher.publish(settings, settings.site_folder, key, message, transport)
        except publisher.PublishError:
            raise
        except Exception as exc:  # noqa: BLE001 -- GitHub may have taken it (§ 4.3)
            raise publisher.OutcomeUnknown(
                f"the upload stopped on {type(exc).__name__}") from None
        except BaseException:
            # Stopped mid-upload -- Ctrl-C, SystemExit: GitHub may have taken
            # it, so nothing is put back (§ 4.6), and the stop goes on up.
            interrupted = True
            raise
    except publisher.OutcomeUnknown:
        if bin_copy_failed():
            gathered.append(Notice(say("notice.publishing.kept_copy_unknown"), Site.UNKNOWN))
        raise
    except BaseException:
        if moved is not None and not interrupted:
            captured(moved.put_back)   # a failure here is raised in place of the original
        raise
    def forget_the_starter() -> None:
        # PRESS-0126 § 4.5: the publish landed, so the starter is on the web.
        try:
            starter.published(folder)
        except OSError:
            warnings.warn(store.StoreNotice("notice.publishing.starter_kept"), stacklevel=2)

    captured(forget_the_starter)
    return Published(outcome, bin_copy_failed())


@dataclass
class _Moved:
    published: str                  # the address now published
    copy: list[Path]                # the drafts to bin once published; may be empty
    put_back: Callable[[], None]


def _move(folder: Path, entry: str | None) -> _Moved | None:
    """§ 4.3 step 1."""
    if entry is None:
        return None
    path = store.path_for(folder, entry, draft=True)
    draft = store.read(path)
    stripped = tuple(field for field in draft.extra
                     if field[0] not in (editor.REPLACES, UNDONE))
    named = editor.replaces_field(draft)

    if named is not None and named in store.list_slugs(folder, draft=False):
        remembered = store.read(store.path_for(folder, named, draft=False))
        store.write(folder, dataclasses.replace(draft, slug=named, date=remembered.date,
                                                extra=stripped), draft=False)
        return _Moved(named, [path], lambda: store.write(folder, remembered, draft=False))

    # PRESS-0015 § 4.5: a draft whose `Replaces` names a draft carrying the mark
    # is a working copy of the entry undo demoted. The mark is what makes this
    # safe -- without it any draft naming another would publish over it.
    if named is not None and named in store.list_slugs(folder, draft=True):
        demoted_path = store.path_for(folder, named, draft=True)
        demoted = store.read(demoted_path)
        if any(name == UNDONE for name, _ in demoted.extra):
            store.write(folder, dataclasses.replace(draft, slug=named, date=demoted.date,
                                                    extra=stripped), draft=False)
            # Nothing else removes a file the Store did not hold before, so the
            # put-back bins what was just written and leaves his two drafts as
            # they were (§ 4.5).
            return _Moved(named, [path, demoted_path],
                          lambda: store.move_to_bin(
                              folder, store.path_for(folder, named, draft=False)))

    # A draft carrying the mark keeps its date: § 2 item 3's branch would
    # otherwise date an entry from years ago to today and put it at the top of
    # his site (PRESS-0015 § 4.5).
    marked = any(name == UNDONE for name, _ in draft.extra)
    dated = draft.date if marked else _now().replace(microsecond=0)
    store.write(folder, dataclasses.replace(draft, date=dated, extra=stripped), draft=True)
    try:
        store.publish(folder, entry)
    except BaseException:
        # Nothing is recorded to put back yet, so the rewrite is undone here; a
        # failure writing it back is raised in its place (PRESS-0135).
        store.write(folder, draft, draft=True)
        raise

    def put_back() -> None:
        store.unpublish(folder, entry)
        store.write(folder, draft, draft=True)

    return _Moved(entry, [], put_back)


def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None:
    """Add `POST /publish` to `face` (§ 4.2)."""
    folder = Path(folder)
    face.add_page("POST", "/publish",
                  lambda request: _publish(face, folder, request, transport))
    face.add_page("GET", REPLACE_ADDRESS, lambda request: _replace(face, folder, request))
    face.add_page("POST", REPLACE_ADDRESS, lambda request: _replace(face, folder, request))
    face.add_page("GET", TAKEOVER_ADDRESS,
                  lambda request: _takeover_page(face, folder, transport))
    face.add_page("POST", TAKEOVER_ADDRESS,
                  lambda request: _take_over(face, folder, transport))


def _publish(face: Face, folder: Path, request: Request,
             transport: publisher.Transport | None) -> Reply:
    """§ 4.2, run as a press (PRESS-0235 § 4.4)."""
    fields = urllib.parse.parse_qs(request.body.decode("utf-8"), keep_blank_values=True)
    form = {name: values[0] for name, values in fields.items()}

    def busy(said: str) -> Reply:
        """Nothing saved: the page keeps the file it posted (PRESS-0235 § 4.4)."""
        return Reply(json.dumps({
            "published": False, "slug": form.get("slug", ""),
            "draft": form.get("draft") == "1", "base": form.get("base", ""),
            "failure": None, "notices": "", "busy": True, "said": said,
        }).encode("utf-8"), "application/json")

    return pressing.run(pressing.PUBLISH, busy,
                        lambda told: _pressed(face, folder, form, transport, told))


def _pressed(face: Face, folder: Path, form: dict[str, str],
             transport: publisher.Transport | None,
             told: Callable[[pressing.Outcome], None]) -> Reply:
    notices: list[str] = []

    gathered = gatherer(face.capture, notices)

    with editor.LOCK:
        try:
            written, _ = gathered(lambda: editor.save(folder, form))
        except (store.StoreError, editor.ChangedElsewhere, editor.TooManyCopies) as exc:
            failed = face.fail(exc, publishing=False)
            told(pressing.ended(pressing.PUBLISH, False, failed))
            body = render_notices(notices) + failed
            return Reply(body.encode("utf-8"), "text/html; charset=utf-8", status=409)

        try:
            saved = gathered(lambda: settings.load(folder))
            key = github_setup.token(folder, saved.credentials.store,
                                     saved.credentials.github_account)
            result = publish(folder, saved, key, entry=written.slug, capture=face.capture,
                             notices=notices, transport=transport)
        except Exception as exc:  # noqa: BLE001 -- every failure is shown beside the save
            failure: str | None = (face.fail(exc, publishing=False,
                                             secret=say("failure.secret.publishing_key"))
                                   + replace_link(exc))
            published = False
        else:
            failure = None
            published = True
            if result.copy_kept:
                notices.append(Notice(say("notice.publishing.kept_copy"), Site.UPDATED))
        told(pressing.ended(pressing.PUBLISH, published, failure))
        slug, draft, base = gathered(lambda: _left(folder, written))

    return Reply(json.dumps({
        "published": published, "slug": slug, "draft": draft, "base": base,
        "failure": failure, "notices": render_notices(notices), "busy": False,
    }).encode("utf-8"), "application/json")


def _left(folder: Path, written: store.Entry) -> tuple[str, bool, str]:
    """The file the page saves to next, read from disk (§ 4.2): the working copy
    of the published entry where one is left, else the published entry, else
    the draft."""
    published = store.list_slugs(folder, draft=False)
    named = editor.replaces_field(written)
    target = named if named in published else written.slug
    if target in published:
        try:
            copy = editor.working_copy(folder, target)
        except editor.TooManyCopies:
            copy = None
        if copy is None:
            return target, False, _digest(store.path_for(folder, target, draft=False))
        return copy, True, _digest(store.path_for(folder, copy, draft=True))
    return written.slug, True, _digest(store.path_for(folder, written.slug, draft=True))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace(face: Face, folder: Path, request: Request) -> str:
    """PRESS-0126 § 4.5: the user's say-so to replace the site on GitHub. It
    trims the untouchable list as asked and removes the marker, and publishes
    nothing: a refused publish put its change back, so the next one carries it."""
    with editor.LOCK, face.capture() as notices:
        body = _replace_page(face, folder, request)
    return render_notices(notices) + body


def _replace_page(face: Face, folder: Path, request: Request) -> str:
    e = html.escape
    if not starter.unpublished(folder):
        return (f"<h1>{say('publishing.nothing.heading')}</h1><p>{say('publishing.nothing')} "
                f'<a href="/">{say("face.your_writing")}</a></p>')
    try:
        saved = settings.load(folder)
    except (settings.NotSetUp, settings.SettingsError) as exc:
        return face.fail(exc, publishing=False)
    hint = ""
    if request.method == "POST":
        fields = urllib.parse.parse_qs(request.body.decode("utf-8", "replace"),
                                       keep_blank_values=True)
        typed = (fields.get("repository") or [""])[0].strip()
        if typed == saved.repository:
            keep = set(fields.get("keep", []))
            kept = tuple(entry for entry in saved.untouchable if entry in keep)
            try:
                if kept != saved.untouchable:
                    settings.save(folder, dataclasses.replace(saved, untouchable=kept))
                starter.published(folder)
            except (settings.SettingsError, OSError) as exc:
                return face.fail(exc, publishing=False)
            pressing.forget()  # PRESS-0272: this answers the refusal's box
            return (f"<h1>{say('publishing.ready.heading')}</h1>"
                    f"<p>{say('publishing.ready', repository=e(saved.repository))}</p>"
                    f'<p class="nav"><a href="/">{say("face.your_writing")}</a></p>')
        hint = message_box("repository-hint", say("publishing.hint"), focus="repository")
    boxes = "".join(
        f'<li><label><input type="checkbox" name="keep" value="{e(entry, quote=True)}" '
        f"checked> {e(entry)}</label></li>" for entry in saved.untouchable)
    left = (f"<p>{say('publishing.keep')}</p><ul>{boxes}</ul>" if boxes
            else f"<p>{say('publishing.keep_none')}</p>")
    return (f"<h1>{say('publishing.replace')}</h1>"
            f"<p>{say('publishing.replace.intro', repository=e(saved.repository))}</p>"
            f'<form method="post" action="{REPLACE_ADDRESS}">{left}'
            f"<p><label>{say('publishing.replace.confirm', repository=e(saved.repository))} "
            '<input type="text" name="repository" autocomplete="off"></label></p>'
            f"{hint}<p><button>{say('publishing.replace.button')}</button></p></form>")


# ------------------------------------------------------- PRESS-0333 § 4.5 ----


def _takeover_page(face: Face, folder: Path, transport: publisher.Transport | None,
                   hint: str = "") -> str:
    """What will change, a link to remove each build file, and the go-ahead."""
    if not takeover.owed(folder):
        return (f"<h1>{say('publishing.nothing.heading')}</h1><p>{say('publishing.nothing')} "
                f'<a href="/">{say("face.your_writing")}</a></p>')
    e = html.escape
    try:
        saved = settings.load(folder)
        key = github_setup.token(folder, saved.credentials.store,
                                 saved.credentials.github_account)
        files = takeover.build_files(folder, saved, key, transport)
        domain = publisher.pages(saved.repository, key, transport).domain
        branch = publisher.default_branch(saved.repository, key, transport)
        entries = publisher.root_entries(saved, key, transport)
    except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page
        return face.fail(exc, publishing=False, secret=say("failure.secret.publishing_key"))
    stale = any(entry.casefold() == publisher.CNAME.casefold() for entry in entries)
    rows = takeover.change_rows(takeover.named(folder) or files, saved.site_address, domain,
                                stale and not domain)
    links = "".join(
        f'<li><a href="{e(_delete_link(saved.repository, branch, name), quote=True)}" '
        f'target="_blank" rel="noopener">'
        f"{say('publishing.takeover.delete', file=e(name))}</a></li>" for name in files)
    removing = (f"<p>{say('publishing.takeover.steps')}</p><ul>{links}</ul>" if files
                else f"<p>{say('publishing.takeover.removed')}</p>")
    return (f"<h1>{say('publishing.takeover')}</h1>" + hint
            + f"<p>{say('publishing.takeover.intro', repository=e(saved.repository))}</p><ul>"
            + "".join(f"<li>{row}</li>" for row in rows) + "</ul>" + removing
            + f'<form method="post" action="{TAKEOVER_ADDRESS}">'
            + f"<p><button>{say('publishing.takeover.button')}</button></p>"
            + '<p class="press-status" role="status"></p></form>'
            + f"<script>{_WORKING_SCRIPT}</script>")


# PRESS-0339: the takeover publishes before its page answers, which can take a
# minute, so the press says so at once. The button goes off after the submit
# event, once the form's data is taken.
_WORKING_SCRIPT = """(() => {
  const form = document.currentScript.previousElementSibling;
  form.addEventListener("submit", () => {
    form.querySelector("[role=status]").textContent = say("script.press.publishing");
    setTimeout(() => { form.querySelector("button").disabled = true; });
  });
})();"""


def _delete_link(repository: str, branch: str, path: str) -> str:
    """GitHub's own page for removing a file: a workflow file changes only with a
    permission Pressless does not hold, and the person's own sign-in has it."""
    quoted = "/".join(urllib.parse.quote(part, safe="") for part in
                      (*repository.split("/"), "delete", *branch.split("/"), *path.split("/")))
    return f"https://github.com/{quoted}"


def _take_over(face: Face, folder: Path, transport: publisher.Transport | None) -> str:
    """§ 4.5's POST, run as a press."""
    def busy(said: str) -> str:
        return message_box("takeover-hint", html.escape(said))

    return pressing.run(pressing.PUBLISH, busy,
                        lambda told: _takeover_pressed(face, folder, transport, told))


def _takeover_pressed(face: Face, folder: Path, transport: publisher.Transport | None,
                      told: Callable[[pressing.Outcome], None]) -> str:
    if not takeover.owed(folder):
        told(pressing.ended(pressing.PUBLISH, True))
        return _takeover_page(face, folder, transport)
    notices: list[str | Notice] = []
    gathered = gatherer(face.capture, notices)
    stage = ""

    def stopped(exc: BaseException) -> str:
        failed = (face.fail(exc, publishing=False, secret=say("failure.secret.publishing_key"))
                  + stage)
        told(pressing.ended(pressing.PUBLISH, False, failed))
        return render_notices(notices) + failed

    with editor.LOCK:
        try:
            saved = gathered(lambda: settings.load(folder))
            key = github_setup.token(folder, saved.credentials.store,
                                     saved.credentials.github_account)
            if takeover.build_files(folder, saved, key, transport):                   # step 1
                told(pressing.ended(pressing.PUBLISH, False))
                hint = message_box("takeover-hint", say("publishing.takeover.still_there"))
                return _takeover_page(face, folder, transport, hint)
            shown = publisher.pages(saved.repository, key, transport)                 # step 2
            final = dataclasses.replace(                                              # step 3
                saved, untouchable=publisher.kept_on_a_branch(saved.untouchable, shown.domain))
            if final != saved:
                gathered(lambda: settings.save(folder, final))
            if not shown.built_by_actions:
                gathered(lambda: takeover.done(folder))
                told(pressing.ended(pressing.PUBLISH, True))
                return f"<p>{say(_already_key(shown))}</p>"
            published = publish(folder, final, key, entry=None, taking_over=True,     # step 4
                                capture=face.capture, notices=notices, transport=transport)
            stage = f"<p>{say('publishing.takeover.not_switched')}</p>"
            publisher.switch_pages_to_branch(final.repository, key, shown.domain,     # step 5
                                             transport)
            stage = ""
            files = takeover.named(folder)
            stale = publisher.CNAME in published.outcome.removed
            gathered(lambda: takeover.done(folder))                                   # step 6
        except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page
            return stopped(exc)
    told(pressing.ended(pressing.PUBLISH, True))
    pressing.forget()
    return render_notices(notices) + _takeover_report(final, shown.domain, files, stale,
                                                      published.outcome)


def _already_key(shown: publisher.Pages) -> str:
    if not shown.on:
        return "publishing.takeover.already.off"
    return ("publishing.takeover.already.root" if shown.serves_root
            else "publishing.takeover.already.elsewhere")


def _takeover_report(final: settings.Settings, domain: str | None, files: tuple[str, ...],
                     stale: bool, outcome: publisher.Outcome) -> str:
    """Step 6: what changed, told afterwards (INV-14)."""
    e = html.escape
    rows = [say("publishing.takeover.done.pages")]
    rows += [say("publishing.takeover.done.file", file=f"<code>{e(name)}</code>") for name in files]
    rows.append(say("publishing.takeover.done.address", address=e(final.site_address)))
    if domain:
        rows.append(say("publishing.takeover.done.domain", domain=e(domain)))
    rows.append(say("publishing.takeover.done.added"))
    if domain:
        rows.append(say("publishing.takeover.done.added_domain"))
    if stale:
        rows.append(say("publishing.takeover.done.stale"))
    rows.append(say("publishing.takeover.done.earlier") if not outcome.commit else say(
        "publishing.takeover.done.counts",
        uploaded=len(outcome.uploaded), removed=len(outcome.removed)))
    return (f"<h1>{say('publishing.takeover.done.heading')}</h1><ul>"
            + "".join(f"<li>{row}</li>" for row in rows) + "</ul>"
            + f"<p>{say('publishing.takeover.done.wait')}</p>"
            + f'<p class="nav"><a href="/">{say("face.your_writing")}</a></p>')

