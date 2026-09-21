"""Undo: one step back, ending with the site and his files agreeing (PRESS-0015).

The Face owns the order (docs/design.md rule 1): empty the fetch area, fetch the
state before the current commit, read it whole, reconcile the Store with it, then
publish. A definite failure runs the reversals recorded so far, so his files are
never left part old and part new; an upload whose outcome is unknown leaves the
Store as undo made it, because GitHub may already show the older state
(docs/specs/PRESS-0015-undo.md § 4.3).
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import shutil
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TypeVar

from pressless import credentials, editor, publisher, publishing, settings, setup, store
from pressless.face import SENTENCES, Face, Reply, Request, Sentence, Site, render_notices

FETCH_FOLDER = "fetch"      # inside Pressless's own folder; emptied when the sequence ends
CONTENT = "content/"        # the prefix fetched (PRESS-0008 § 4.7)
KEPT_SUFFIX = "-before-undo"

_T = TypeVar("_T")


class NothingToUndo(Exception):
    """The state before holds no `content/` (§ 3 decision 5)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[NothingToUndo] = Sentence(
    "Pressless cannot undo your very first publish.",
    Site.UNCHANGED,
    "There is no earlier version of your site to go back to.",
)


@dataclass(frozen=True)
class Undone:
    outcome: publisher.Outcome
    restored: tuple[str, ...]  # addresses the fetched state put back
    demoted: tuple[str, ...]   # entries turned back into drafts
    kept: tuple[str, ...]      # addresses his own versions were kept under


@contextlib.contextmanager
def _nothing_captured() -> Iterator[list[str]]:
    yield []


def undo(folder: Path, settings: settings.Settings, key: str, *,
         capture: Callable[[], AbstractContextManager[list[str]]] = _nothing_captured,
         notices: list[str] | None = None,
         transport: publisher.Transport | None = None) -> Undone:
    """§ 4.3: empty, fetch, refuse a first publish, read whole, reconcile, publish.

    `capture` wraps the read and the reconcile and nothing else (§ 4.1): both are
    long runs of Store calls that emit a StoreNotice only a capturing caller
    sees, while a fetch is minutes long and a capture holds a process-wide lock.
    """
    folder = Path(folder)
    gathered = notices if notices is not None else []
    fetch = folder / FETCH_FOLDER

    def captured(step: Callable[[], _T]) -> _T:
        caught: list[str] | None = None
        try:
            with capture() as caught:
                return step()
        finally:
            if caught is not None:
                gathered.extend(caught)

    _empty(fetch)                                                        # step 1
    try:
        fetched = publisher.fetch_previous(settings, key, fetch, CONTENT, transport)  # step 2
        if not fetched.paths:                                            # step 3
            raise NothingToUndo("the state before this commit holds no site")

        state = captured(lambda: _read(fetch, fetched.paths))            # step 4
        reversals: list[Callable[[], None]] = []
        try:
            changed = captured(lambda: _reconcile(folder, state, reversals))  # step 5
            published = publishing.publish(                              # step 6
                folder, settings, key, entry=None, emptying=True,
                capture=capture, notices=gathered, transport=transport)
        except publisher.OutcomeUnknown:
            # The Store stays as undo made it: GitHub may have taken the change,
            # and his files must not disagree with a site that may already show
            # the older state (§ 4.3).
            raise
        except BaseException:
            # A failure while reversing is raised in place of the original, so he
            # is told something is wrong with his files rather than only with
            # GitHub (§ 4.3).
            captured(lambda: _reverse(reversals))
            raise
    finally:
        _empty(fetch)                                                    # step 7

    return Undone(published.outcome, tuple(changed.restored),
                  tuple(changed.demoted), tuple(changed.kept))


def _empty(fetch: Path) -> None:
    """§ 4.3 steps 1 and 7. Undo never reads a fetch area it did not just create:
    PRESS-0009 § 4.5 leaves a window where a failed fetch leaves the folder part
    old and part new, and says this item must not assume otherwise."""
    shutil.rmtree(fetch, ignore_errors=True)
    fetch.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------- reading ---


@dataclass(frozen=True)
class _State:
    """The fetched state, read through the Store's own reader for each kind
    (§ 4.4). Read whole before anything is written, so a file the Store cannot
    read raises with the Store untouched (INV-11)."""
    entries: dict[str, store.Entry] = field(default_factory=dict)
    comments: dict[str, tuple[store.Comment, ...]] = field(default_factory=dict)
    pages: dict[str, str] = field(default_factory=dict)
    furniture: dict[str, str] = field(default_factory=dict)
    templates: dict[str, store.Entry] = field(default_factory=dict)


def _read(fetch: Path, paths: tuple[str, ...]) -> _State:
    """§ 4.3 step 4. `paths` are repository-relative and the layout under `fetch`
    is the same strings (PRESS-0009 § 4.5), so each file is `fetch / path`."""
    state = _State()
    prefix = CONTENT.rstrip("/")
    for relative in paths:
        parts = PurePosixPath(relative).parts
        if len(parts) != 3 or parts[0] != prefix:
            continue
        kind, name = parts[1], parts[2]
        path = fetch.joinpath(*parts)
        if kind == store.PUBLISHED_FOLDER and name.endswith(store.FILE_SUFFIX):
            state.entries[_stem(name, store.FILE_SUFFIX)] = store.read(path)
        elif kind == store.COMMENTS_FOLDER and name.endswith(store.COMMENTS_SUFFIX):
            state.comments[_stem(name, store.COMMENTS_SUFFIX)] = store.read_comments(path)
        elif kind == store.PAGES_FOLDER and name.endswith(store.HTML_SUFFIX):
            state.pages[_stem(name, store.HTML_SUFFIX)] = store.read_html(path)
        elif kind == store.FURNITURE_FOLDER and name.endswith(store.HTML_SUFFIX):
            state.furniture[_stem(name, store.HTML_SUFFIX)] = store.read_html(path)
        elif kind == store.TEMPLATES_FOLDER and name.endswith(store.FILE_SUFFIX):
            state.templates[_stem(name, store.FILE_SUFFIX)] = store.read(path)
    return state


def _stem(name: str, suffix: str) -> str:
    return name[: -len(suffix)]


# ----------------------------------------------------------- reconciling ---


@dataclass
class _Changed:
    restored: list[str] = field(default_factory=list)
    demoted: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)


def _reconcile(folder: Path, state: _State, reversals: list[Callable[[], None]]) -> _Changed:
    """§ 4.4. Every write goes through the Store's own calls, never by copying
    bytes (§ 3 decision 11), and every removal is `store.move_to_bin` (§ 4.7).
    Each branch records one reversal undoing everything that branch did."""
    changed = _Changed()
    published = set(store.list_slugs(folder, draft=False))
    drafts = set(store.list_slugs(folder, draft=True))

    for slug, fetched in state.entries.items():
        if slug in published:
            _restore_over_published(folder, slug, fetched, reversals, changed)
        elif slug in drafts:
            _restore_over_draft(folder, slug, fetched, reversals, changed)
        else:
            store.write(folder, fetched, draft=False)
            reversals.append(_bin_later(folder, slug, draft=False))
            changed.restored.append(slug)

    for slug in sorted(published - set(state.entries)):
        _demote(folder, slug, reversals, changed)

    _restore_other_kinds(folder, state, reversals)
    return changed


def _restore_over_published(folder: Path, slug: str, fetched: store.Entry,
                            reversals: list[Callable[[], None]], changed: _Changed) -> None:
    """The Store publishes it. Nothing where it does not differ; otherwise his
    version is kept as a draft and the fetched entry written over it (§ 4.4)."""
    remembered = store.read(store.path_for(folder, slug, draft=False))
    if remembered == fetched:
        return
    kept = _keep(folder, remembered, slug)
    store.write(folder, fetched, draft=False)

    def back() -> None:
        store.write(folder, remembered, draft=False)
        store.move_to_bin(folder, store.path_for(folder, kept, draft=True))

    reversals.append(back)
    changed.kept.append(kept)
    changed.restored.append(slug)


def _restore_over_draft(folder: Path, slug: str, fetched: store.Entry,
                        reversals: list[Callable[[], None]], changed: _Changed) -> None:
    """A draft holds that slug. His draft is kept under a free address with its
    own fields, the old draft file is binned, and the fetched entry is published
    — otherwise one slug would name two files, which docs/design.md rules out."""
    his = store.read(store.path_for(folder, slug, draft=True))
    kept = _keep(folder, his, slug)
    store.move_to_bin(folder, store.path_for(folder, slug, draft=True))
    store.write(folder, fetched, draft=False)

    def back() -> None:
        store.move_to_bin(folder, store.path_for(folder, slug, draft=False))
        store.move_to_bin(folder, store.path_for(folder, kept, draft=True))
        # His draft is written back rather than moved out of the bin: nothing
        # moves a file out of the bin, and the binned copy is the spare copy of
        # what is now back in place (§ 4.3 step 5).
        store.write(folder, his, draft=True)

    reversals.append(back)
    changed.kept.append(kept)
    changed.restored.append(slug)


def _demote(folder: Path, slug: str, reversals: list[Callable[[], None]],
            changed: _Changed) -> None:
    """An entry the Store publishes and the fetched state does not hold is turned
    back into a draft carrying the mark (§ 4.4, § 4.5). It is never deleted."""
    remembered = store.read(store.path_for(folder, slug, draft=False))
    store.unpublish(folder, slug)
    marked = dataclasses.replace(
        remembered, extra=_without(remembered.extra, publishing.UNDONE)
        + ((publishing.UNDONE, publishing.undone_stamp()),))
    store.write(folder, marked, draft=True)

    def back() -> None:
        store.write(folder, remembered, draft=True)
        store.publish(folder, slug)

    reversals.append(back)
    changed.demoted.append(slug)


def _restore_other_kinds(folder: Path, state: _State,
                         reversals: list[Callable[[], None]]) -> None:
    """Every other kind the fetched state holds is written where it differs or is
    absent, the superseded version going to the bin first. Every file the fetched
    state does NOT hold is kept untouched (§ 4.4), so an undo removes nothing of
    his from the Store."""
    for name, html in sorted(state.pages.items()):
        _restore_html(folder, store.PAGES_FOLDER, name, html, reversals)
    for name, html in sorted(state.furniture.items()):
        _restore_html(folder, store.FURNITURE_FOLDER, name, html, reversals)

    for name, template in sorted(state.templates.items()):
        path = store.template_path_for(folder, name)
        remembered = store.read(path) if path.is_file() else None
        if remembered == template:
            continue
        if remembered is not None:
            store.move_to_bin(folder, path)
            reversals.append(lambda t=remembered: store.write_template(folder, t))
        else:
            reversals.append(lambda p=path: store.move_to_bin(folder, p))
        store.write_template(folder, template)

    for slug, comments in sorted(state.comments.items()):
        path = store.comments_path_for(folder, slug)
        remembered = store.read_comments(path) if path.is_file() else None
        if remembered == comments:
            continue
        if remembered is not None:
            store.move_to_bin(folder, path)
            reversals.append(
                lambda s=slug, c=remembered: store.write_comments(folder, s, c))
        else:
            reversals.append(lambda p=path: store.move_to_bin(folder, p))
        store.write_comments(folder, slug, comments)


def _restore_html(folder: Path, kind: str, name: str, html: str,
                  reversals: list[Callable[[], None]]) -> None:
    path = store.html_path_for(folder, kind, name)
    remembered = store.read_html(path) if path.is_file() else None
    if remembered == html:
        return
    if remembered is not None:
        store.move_to_bin(folder, path)
        reversals.append(lambda h=remembered: store.write_html(folder, kind, name, h))
    else:
        reversals.append(lambda p=path: store.move_to_bin(folder, p))
    store.write_html(folder, kind, name, html)


def _keep(folder: Path, entry: store.Entry, restored: str) -> str:
    """His version, as a draft under a free address (§ 4.4). It keeps its own
    fields, so a draft that was a working copy of some OTHER entry stays one —
    but never a `Replaces` naming the entry just put back, which § 3 decision 7
    rules out and `editor.TooManyCopies` would then refuse."""
    wanted = editor.free_address(folder, restored + KEPT_SUFFIX)
    extra = tuple(pair for pair in entry.extra
                  if not (pair[0] == editor.REPLACES and pair[1] == restored))
    store.write(folder, dataclasses.replace(entry, slug=wanted, extra=extra), draft=True)
    return wanted


def _without(extra: tuple[tuple[str, str], ...], name: str) -> tuple[tuple[str, str], ...]:
    return tuple(pair for pair in extra if pair[0] != name)


def _bin_later(folder: Path, slug: str, *, draft: bool) -> Callable[[], None]:
    return lambda: store.move_to_bin(folder, store.path_for(folder, slug, draft=draft))


def _reverse(reversals: list[Callable[[], None]]) -> None:
    """§ 4.3: the reversals recorded so far, in reverse order."""
    for back in reversed(reversals):
        back()


# ----------------------------------------------------------------- route ---


def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None:
    """Add `POST /undo` to `face` (§ 4.2)."""
    folder = Path(folder)
    face.add_page("POST", "/undo",
                  lambda request: _undo(face, folder, request, transport))


def _undo(face: Face, folder: Path, request: Request,
          transport: publisher.Transport | None) -> Reply:
    """§ 4.2. A failure at any step answers 200 rather than an error status, so
    the page can render it beside what it already shows."""
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
            saved = gathered(lambda: settings.load(folder))
            key = credentials.read(saved.credentials.store, folder,
                                   saved.credentials.github_account)
            result = undo(folder, saved, key, capture=face.capture,
                          notices=notices, transport=transport)
        except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page
            failure: str | None = face.fail(exc, publishing=True, secret=setup.KEY)
            summary: str | None = None
        else:
            failure = None
            summary = _summary(result)

    return Reply(json.dumps({
        "undone": failure is None, "failure": failure,
        "notices": render_notices(notices), "summary": summary,
    }).encode("utf-8"), "application/json")


def _summary(result: Undone) -> str:
    """One clause each for `restored`, `demoted` and `kept` (§ 4.2)."""
    clauses = []
    if result.restored:
        clauses.append(f"{_count(len(result.restored))} put back")
    if result.demoted:
        clauses.append(f"{_count(len(result.demoted))} turned back into "
                       + ("a draft" if len(result.demoted) == 1 else "drafts"))
    if result.kept:
        many = len(result.kept) > 1
        clauses.append(f"your own {'versions' if many else 'version'} of "
                       f"{_count(len(result.kept))} kept as "
                       + ("drafts" if many else "a draft"))
    if not clauses:
        return "Your site was already as it was before the last publish."
    return "Your site is back the way it was: " + ", ".join(clauses) + "."


def _count(number: int) -> str:
    return "1 entry" if number == 1 else f"{number} entries"
