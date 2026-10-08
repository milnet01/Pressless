"""Publish: one button writes, builds and publishes (PRESS-0013).

The Face owns the order (docs/design.md rule 1): save the box, read Settings
and the key, move the entry into what is published, build, then upload. A
definite failure puts his files back, so his list never says an entry is on
the site when it is not; an upload whose outcome is unknown is left published,
and publishing again settles it (docs/specs/PRESS-0013-publish.md § 4.3).
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import html
import json
import urllib.parse
import warnings
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from pressless import (
    builder,
    editor,
    github_setup,
    pressing,
    publisher,
    settings,
    starter,
    store,
)
from pressless.face import (
    SENTENCES,
    Face,
    Notice,
    Reply,
    Request,
    Sentence,
    Site,
    message_box,
    render_notices,
)
from pressless.words import say

MESSAGE = "Publish {slug}"     # the commit message; {slug} is the entry's address

# The header marking a draft undo demoted (PRESS-0015 § 4.5). Nothing parses the
# value -- it is the moment of the demotion, written so that a person reading his
# own file can see what happened. Presence is what is read.
UNDONE = "Undone"

_T = TypeVar("_T")


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

SENTENCES[WouldReplaceASite] = Sentence(
    "failure.publishing.WouldReplaceASite.what",
    Site.UNCHANGED,
    "failure.publishing.WouldReplaceASite.next",
)

# GitHub Pages serves either as a site's front page (PRESS-0126 § 3 decision 5).
_A_SITE = frozenset({"index.html", "index.md"})

def replace_link(failure: BaseException) -> str:
    """The way to the replace page, beside a WouldReplaceASite failure; a
    Sentence is escaped text and cannot carry it."""
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


@contextlib.contextmanager
def _nothing_captured() -> Iterator[list[str]]:
    yield []


def publish(folder: Path, settings: settings.Settings, key: str, *, entry: str | None,
            emptying: bool = False,
            capture: Callable[[], AbstractContextManager[list[str]]] = _nothing_captured,
            notices: list[str | Notice] | None = None,
            transport: publisher.Transport | None = None) -> Published:
    """§ 4.3: move the entry, guard, build, upload, finish. `capture` wraps every
    step but the upload, and what each capture gathers is added to `notices`."""
    folder = Path(folder)
    gathered = notices if notices is not None else []

    def captured(step: Callable[[], _T]) -> _T:
        caught: list[str] | None = None
        try:
            with capture() as caught:
                return step()
        finally:
            if caught is not None:
                gathered.extend(caught)

    # PRESS-0214 § 4.3: before the move, so nothing has moved to put back.
    if entry is not None and not captured(lambda: store.journal_on(folder)):
        raise JournalOff("the journal is off")
    moved = captured(lambda: _move(folder, entry))

    def guard_and_build() -> None:
        # PRESS-0126 § 4.5: the starter's first publish, whether or not
        # emptying, refuses where the repository holds a site. The fold is
        # PRESS-0009 § 4.4's.
        if starter.unpublished(folder) and any(
                entry.rstrip("/").casefold() in _A_SITE
                for entry in publisher.root_entries(settings, key, transport)):
            raise WouldReplaceASite("the repository already holds a site")
        if (not emptying and store.journal_on(folder)
                and not store.list_slugs(folder, draft=False)):
            raise NothingToPublish("no published entry would remain")
        builder.build(folder, settings, settings.site_folder)

    def finish() -> bool:
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
        if finish():
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
    return Published(outcome, finish())


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
    named = next((value for name, value in draft.extra if name == editor.REPLACES), None)

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

    def gathered(step: Callable[[], _T]) -> _T:
        caught: list[str] | None = None
        try:
            with face.capture() as caught:
                return step()
        finally:
            if caught is not None:
                notices.extend(caught)

    with editor.LOCK:
        try:
            written, _ = gathered(lambda: editor.save(folder, form))
        except (store.StoreError, editor.ChangedElsewhere, editor.TooManyCopies) as exc:
            failed = face.fail(exc, publishing=False)
            told(pressing.Outcome(say("script.press.not_published"), failed))
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
        told(pressing.Outcome(say("script.press.published"), None) if published
             else pressing.Outcome(say("script.press.not_published"), failure))
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
    named = next((value for name, value in written.extra if name == editor.REPLACES), None)
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
            return (f"<h1>{say('publishing.ready.heading')}</h1>"
                    f"<p>{say('publishing.ready', repository=e(saved.repository))}</p>"
                    f'<p><a href="/">{say("face.your_writing")}</a></p>')
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
