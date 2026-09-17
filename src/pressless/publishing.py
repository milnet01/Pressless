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
import json
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from pressless import builder, credentials, editor, publisher, settings, setup, store
from pressless.face import SENTENCES, Face, Reply, Request, Sentence, Site, render_notices

MESSAGE = "Publish {slug}"     # the commit message; {slug} is the entry's address

_T = TypeVar("_T")


class NothingToPublish(Exception):
    """No published entry would remain (docs/design.md rule 9)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[NothingToPublish] = Sentence(
    "Publishing now would leave your site with no entries, so Pressless stopped.",
    Site.UNCHANGED,
    "Send the details below to whoever helps you.",
)

_KEPT_COPY = ("The waiting draft of your changes was left in place after publishing. "
              "You can throw it away.")


@dataclass(frozen=True)
class Published:
    outcome: publisher.Outcome
    copy_kept: bool          # § 4.3 step 5 could not bin the working copy


def _now() -> datetime:
    return datetime.now()


@contextlib.contextmanager
def _nothing_captured() -> Iterator[list[str]]:
    yield []


def publish(folder: Path, settings: settings.Settings, key: str, *, entry: str | None,
            emptying: bool = False,
            capture: Callable[[], AbstractContextManager[list[str]]] = _nothing_captured,
            notices: list[str] | None = None,
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

    moved = captured(lambda: _move(folder, entry))

    def guard_and_build() -> None:
        if not emptying and not store.list_slugs(folder, draft=False):
            raise NothingToPublish("no published entry would remain")
        builder.build(folder, settings, settings.site_folder)

    def finish() -> bool:
        if moved is None or moved.copy is None:
            return False
        try:
            captured(lambda: store.move_to_bin(folder, moved.copy))
        except Exception:  # noqa: BLE001 -- never replaces the publish's result (§ 4.3 step 5)
            return True
        return False

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
    except publisher.OutcomeUnknown:
        finish()
        raise
    except BaseException:
        if moved is not None:
            captured(moved.put_back)   # a failure here is raised in place of the original
        raise
    return Published(outcome, finish())


@dataclass
class _Moved:
    published: str                  # the address now published
    copy: Path | None               # the working copy to bin once published
    put_back: Callable[[], None]


def _move(folder: Path, entry: str | None) -> _Moved | None:
    """§ 4.3 step 1."""
    if entry is None:
        return None
    path = store.path_for(folder, entry, draft=True)
    draft = store.read(path)
    stripped = tuple(field for field in draft.extra if field[0] != editor.REPLACES)
    named = next((value for name, value in draft.extra if name == editor.REPLACES), None)

    if named is not None and named in store.list_slugs(folder, draft=False):
        remembered = store.read(store.path_for(folder, named, draft=False))
        store.write(folder, dataclasses.replace(draft, slug=named, date=remembered.date,
                                                extra=stripped), draft=False)
        return _Moved(named, path, lambda: store.write(folder, remembered, draft=False))

    store.write(folder, dataclasses.replace(draft, date=_now().replace(microsecond=0),
                                            extra=stripped), draft=True)
    store.publish(folder, entry)

    def put_back() -> None:
        store.unpublish(folder, entry)
        store.write(folder, draft, draft=True)

    return _Moved(entry, None, put_back)


def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None:
    """Add `POST /publish` to `face` (§ 4.2)."""
    folder = Path(folder)
    face.add_page("POST", "/publish",
                  lambda request: _publish(face, folder, request, transport))


def _publish(face: Face, folder: Path, request: Request,
             transport: publisher.Transport | None) -> Reply:
    """§ 4.2."""
    fields = urllib.parse.parse_qs(request.body.decode("utf-8"), keep_blank_values=True)
    form = {name: values[0] for name, values in fields.items()}
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
            body = render_notices(notices) + face.fail(exc, publishing=False)
            return Reply(body.encode("utf-8"), "text/html; charset=utf-8", status=409)

        try:
            saved = gathered(lambda: settings.load(folder))
            key = credentials.read(saved.credentials.store, folder,
                                   saved.credentials.github_account)
            result = publish(folder, saved, key, entry=written.slug, capture=face.capture,
                             notices=notices, transport=transport)
        except Exception as exc:  # noqa: BLE001 -- every failure is shown beside the save
            failure: str | None = face.fail(exc, publishing=False, secret=setup.KEY)
            published = False
        else:
            failure = None
            published = True
            if result.copy_kept:
                notices.append(_KEPT_COPY)
        slug, draft, base = gathered(lambda: _left(folder, written))

    return Reply(json.dumps({
        "published": published, "slug": slug, "draft": draft, "base": base,
        "failure": failure, "notices": render_notices(notices),
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
