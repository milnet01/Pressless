"""Take in a Pressless site already in a GitHub repository (PRESS-0218).

The Face owns the order (docs/design.md rule 1). `look` fetches a state and
says what it holds, writing nothing to the Store. `take_in` fetches that same
state again and fills an empty Store from it through the Store's own calls,
recording a reversal for each write so a failure leaves the Store empty. The
contract is docs/specs/PRESS-0218-take-in-github-site.md.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from pressless import builder, photographs, publisher, settings, store, undo
from pressless.face import SENTENCES, Sentence, Site, gatherer, nothing_captured

# What a take-in fetches: the Store's own files, and what the Builder
# publishes from the photographs, the kept files and the icon (§ 4.2).
PREFIXES = (undo.CONTENT, f"{store.PHOTOGRAPHS_FOLDER}/", f"{store.FILES_FOLDER}/",
            builder.SITE_ICON)


class TakeInStopped(Exception):
    """The Store already holds a site, so a take-in would mix two (§ 4.3)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[TakeInStopped] = Sentence(
    "failure.takein.TakeInStopped.what",
    Site.UNCHANGED,
    "failure.takein.TakeInStopped.next",
)


@dataclass(frozen=True)
class Found:
    commit: str                       # the state read; the take-in uses this one
    made_here: bool                   # § 4.2's test of a Pressless site
    entries: int                      # published entries
    pages: int                        # fixed pages
    comments: int                     # entries with comments
    photographs: int
    files: int
    identity: store.Identity | None
    left: tuple[str, ...]             # fetched paths that will not come across (§ 4.4)


@dataclass(frozen=True)
class TakenIn:
    found: Found                      # what came across; the done page's counts
    reverse: Callable[[], None]       # undoes every write take_in made (§ 4.3)


@dataclass(frozen=True)
class _Read:
    """One fetched state: what the Store will hold, and what it will not."""
    found: Found
    state: undo.State
    photographs: tuple[str, ...]
    files: tuple[str, ...]
    icon: bool                        # the repository holds site-icon.png


def look(folder: Path, settings: settings.Settings, key: str, commit: str = "",
         transport: publisher.Transport | None = None) -> Found:
    """§ 4.2: what the state at `commit`, or the branch's current one, holds.
    Writes nothing to the Store; the fetch area is emptied before and after."""
    fetch = Path(folder) / undo.FETCH_FOLDER
    undo.empty_fetch(fetch)
    try:
        return _fetch_and_read(fetch, settings, key, commit, transport).found
    finally:
        _empty_quietly(fetch)


def take_in(folder: Path, settings: settings.Settings, key: str, commit: str, *,
            capture: Callable[[], AbstractContextManager[list[str]]] = nothing_captured,
            notices: list[str] | None = None,
            transport: publisher.Transport | None = None) -> TakenIn:
    """§ 4.3: refuse a Store holding a site, fetch `commit`, and write it.

    `capture` wraps the Store reads and writes and never the fetch, which is
    minutes long while a capture holds a process-wide lock, as undo's does.
    """
    folder = Path(folder)
    gathered = notices if notices is not None else []
    captured = gatherer(capture, gathered)
    if captured(lambda: store.holds_a_site(folder)):
        raise TakeInStopped("the Store already holds a site")

    fetch = folder / undo.FETCH_FOLDER
    undo.empty_fetch(fetch)
    reversals: list[Callable[[], None]] = []
    try:
        read = _fetch_and_read(fetch, settings, key, commit, transport, captured)
        try:
            captured(lambda: _write(folder, fetch, read, reversals))
        except BaseException:
            captured(lambda: undo.reverse(reversals))
            raise
    finally:
        _empty_quietly(fetch)
    return TakenIn(read.found, lambda: captured(lambda: undo.reverse(reversals)))


def _fetch_and_read(fetch: Path, settings: settings.Settings, key: str, commit: str,
                    transport: publisher.Transport | None,
                    captured: Callable = lambda step: step()) -> _Read:
    fetched = publisher.fetch_state(settings, key, fetch, PREFIXES, commit, transport)
    state = captured(lambda: undo.read_state(fetch, fetched.paths))
    kept_photographs, refused_photographs = _named(
        fetched.paths, store.PHOTOGRAPHS_FOLDER, store.photograph_path_for)
    kept_files, refused_files = _named(fetched.paths, store.FILES_FOLDER, store.file_path_for)
    # § 4.2: a published entry, fixed page or furniture piece in the Store's
    # own layout, or an identity file, and never a content/ folder alone.
    made_here = (state.identity is not None
                 or bool(state.entries or state.pages or state.furniture))
    found = Found(
        commit=fetched.commit, made_here=made_here, entries=len(state.entries),
        pages=len(state.pages), comments=len(state.comments),
        photographs=len(kept_photographs), files=len(kept_files), identity=state.identity,
        left=tuple(sorted((*state.skipped, *refused_photographs, *refused_files))))
    return _Read(found, state, kept_photographs, kept_files,
                 icon=builder.SITE_ICON in fetched.paths)


def _named(paths: tuple[str, ...], folder_name: str,
           path_for: Callable[[Path, str], Path]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The names under `folder_name/` the Store keeps, one segment each, and
    the paths it refuses (§ 4.4)."""
    kept, refused = [], []
    for path in paths:
        first, _, name = path.partition("/")
        if first != folder_name:
            continue
        try:
            path_for(Path(), name)
        except store.StoreError:
            refused.append(path)
        else:
            kept.append(name)
    return tuple(kept), tuple(refused)


def _write(folder: Path, fetch: Path, read: _Read,
           reversals: list[Callable[[], None]]) -> None:
    """§ 4.3 steps 1 to 3, each write recording its reversal as it lands."""
    undo.reconcile(folder, read.state, reversals)                        # step 1

    for name in read.photographs:                                        # step 2
        placed = _place(fetch / store.PHOTOGRAPHS_FOLDER / name, name,
                        lambda n: store.photograph_path_for(folder, n))
        reversals.append(lambda p=placed: store.unplace_photograph(folder, p))
    for name in read.files:
        kept = _place(fetch / store.FILES_FOLDER / name, name,
                      lambda n: store.file_path_for(folder, n))
        reversals.append(lambda k=kept: store.move_to_bin(folder, store.file_path_for(folder, k)))

    identity = read.state.identity                                       # step 3
    if identity is None or not identity.icon:
        return
    # The Builder publishes an icon as site-icon.png only, so the original it
    # was made from is not in the repository. Where the repository holds no
    # icon either, the name is dropped, or the next build would stop on it.
    icon = ""
    if read.icon:
        icon = _place(fetch / builder.SITE_ICON, builder.SITE_ICON,
                      lambda n: store.photograph_path_for(folder, n))
        reversals.append(lambda: store.unplace_photograph(folder, icon))
    store.write_identity(folder, dataclasses.replace(identity, icon=icon))
    reversals.append(lambda: store.write_identity(folder, identity))


def _place(source: Path, name: str, path_for: Callable[[str], Path]) -> str:
    """Keep the fetched file `source` under `name`, which the Builder
    published it as, so the name maps to itself (§ 4.3 step 2)."""
    return photographs.keep(path_for, source.read_bytes(), lambda staged: name)


def _empty_quietly(fetch: Path) -> None:
    """Never raised, for undo's reason: the next fetch empties the area again,
    and a raise here would replace what the sequence did."""
    try:
        undo.empty_fetch(fetch)
    except OSError:
        pass
