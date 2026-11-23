"""Take in a Pressless site already in a GitHub repository (PRESS-0218).

The Face owns the order (docs/design.md rule 1). `look` fetches a state and
says what it holds, writing nothing to the Store. `take_in` fetches that same
state again and fills an empty Store from it through the Store's own calls,
recording a reversal for each write so a failure leaves the Store empty. The
contract is docs/specs/PRESS-0218-take-in-github-site.md.

A repository holding plain pages comes in another way (PRESS-0210 § 4.11):
`look_folder` lays it out where a ZIP would be, and `bring_folder` brings that
in. A site GitHub Actions builds holds no pages, so `look_site` downloads the live
site to the same place (PRESS-0333 § 4.2). Nothing here writes to GitHub.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

import pressless_import
from pressless import builder, photographs, publisher, safe_write, store, undo
from pressless.face import SENTENCES, Sentence, Site, _room, gatherer, nothing_captured
from pressless.settings import Settings
from pressless_import import fetch

# What a take-in fetches: the Store's own files, and what the Builder
# publishes from the photographs, the kept files and the icon (§ 4.2).
PREFIXES = (undo.CONTENT, f"{store.PHOTOGRAPHS_FOLDER}/", f"{store.FILES_FOLDER}/",
            builder.SITE_ICON)
_FOLDER_RECORD = "folder.json"   # in the import folder: the commit import/folder/ holds
# The last state `look` read, by site folder, repository and commit. A commit
# names one state, so the site step shows what the pages step read without
# downloading it again (PRESS-0461).
_LOOKED: dict[tuple[str, str, str], Found] = {}
_LOOKED_LOCK = threading.Lock()


class TakeInStopped(Exception):
    """The Store already holds a site, so a take-in would mix two (§ 4.3)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[TakeInStopped] = Sentence(
    "failure.takein.TakeInStopped.what",
    Site.UNCHANGED,
    "failure.takein.TakeInStopped.next",
)
# docs/design.md § Errors: what a stopped Import says. Here rather than in
# importing.py, since setup's Finish brings a site in too (PRESS-0210 § 4.11).
SENTENCES[pressless_import.ImportStopped] = Sentence(
    "failure.pressless_import.ImportStopped.what",
    Site.UNCHANGED,
    "failure.pressless_import.ImportStopped.next",
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


def look(folder: Path, settings: Settings, key: str, commit: str = "",
         transport: publisher.Transport | None = None) -> Found:
    """§ 4.2: what the state at `commit`, or the branch's current one, holds.
    Writes nothing to the Store; the fetch area is emptied before and after.
    A commit the last look read is answered from it."""
    where = str(Path(folder).resolve())
    with _LOOKED_LOCK:
        known = _LOOKED.get((where, settings.repository, commit)) if commit else None
    if known is not None:
        return known
    with undo.fetch_area(folder) as fetch_area:
        found = _fetch_and_read(fetch_area, settings, key, commit, transport).found
    with _LOOKED_LOCK:
        _LOOKED.clear()
        _LOOKED[(where, settings.repository, found.commit)] = found
    return found


def take_in(folder: Path, settings: Settings, key: str, commit: str, *,
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
    _refuse_a_site(folder, captured)

    reversals: list[Callable[[], None]] = []
    with undo.fetch_area(folder) as fetch_area:
        read = _fetch_and_read(fetch_area, settings, key, commit, transport, captured)
        try:
            # Asked again under the writes' own capture: the fetch held no
            # capture, and anything may have filled the Store meanwhile (INV-3).
            captured(lambda: (_refuse_a_site(folder), _write(folder, fetch_area, read,
                                                              reversals)))
        except BaseException:
            captured(lambda: undo.reverse(reversals))
            raise
    return TakenIn(read.found, lambda: captured(lambda: undo.reverse(reversals)))


def _refuse_a_site(folder: Path, captured: Callable = lambda step: step()) -> None:
    if captured(lambda: store.holds_a_site(folder)):
        raise TakeInStopped("the Store already holds a site")


def _fetch_and_read(fetch_area: Path, settings: Settings, key: str, commit: str,
                    transport: publisher.Transport | None,
                    captured: Callable = lambda step: step()) -> _Read:
    fetched = publisher.fetch_state(settings, key, fetch_area, PREFIXES, commit, transport)
    state = captured(lambda: undo.read_state(fetch_area, fetched.paths))
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


def _write(folder: Path, fetch_area: Path, read: _Read,
           reversals: list[Callable[[], None]]) -> None:
    """§ 4.3 steps 1 to 3, each write recording its reversal as it lands."""
    undo.reconcile(folder, read.state, reversals)                        # step 1

    for name in read.photographs:                                        # step 2
        placed = _place(fetch_area / store.PHOTOGRAPHS_FOLDER / name, name,
                        lambda n: store.photograph_path_for(folder, n))
        reversals.append(lambda p=placed: store.unplace_photograph(folder, p))
    for name in read.files:
        kept = _place(fetch_area / store.FILES_FOLDER / name, name,
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
        icon = _place(fetch_area / builder.SITE_ICON, builder.SITE_ICON,
                      lambda n: store.photograph_path_for(folder, n))
        reversals.append(lambda: store.unplace_photograph(folder, icon))
    store.write_identity(folder, dataclasses.replace(identity, icon=icon))
    reversals.append(lambda: store.write_identity(folder, identity))


def _place(source: Path, name: str, path_for: Callable[[str], Path]) -> str:
    """Keep the fetched file `source` under `name`, which the Builder
    published it as, so the name maps to itself (§ 4.3 step 2)."""
    return photographs.keep(path_for, source.read_bytes(), lambda staged: name)


# ------------------------------------------------- PRESS-0210 § 4.11 ----


def _imports(folder: Path) -> Path:
    return Path(folder) / pressless_import.IMPORT_FOLDER


def _held_folder(folder: Path) -> Path:
    return _imports(folder) / pressless_import.FOLDER


def _record_path(folder: Path) -> Path:
    return _imports(folder) / _FOLDER_RECORD


def forget_record(folder: Path) -> None:
    """The commit import/folder/ held, forgotten: a folder the user hands
    over is no repository's (PRESS-0210 § 4.2)."""
    _record_path(folder).unlink(missing_ok=True)


def _held_commit(folder: Path) -> str:
    """The commit import/folder/ holds; "" where it is gone or unnamed."""
    if not _held_folder(folder).is_dir():
        return ""
    try:
        commit = json.loads(_record_path(folder).read_text(encoding="utf-8"))["commit"]
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    return commit if isinstance(commit, str) else ""


def look_folder(folder: Path, settings: Settings, key: str, commit: str = "",
                transport: publisher.Transport | None = None
                ) -> tuple[pressless_import.Found, str]:
    """The whole repository at `commit`, or the branch's current one, laid out
    at import/folder/; what `read_folder` found there, and the commit read."""
    held = _cleared_held(folder)
    # "/" selects the whole repository (publisher._within_prefix).
    fetched = publisher.fetch_state(settings, key, held, ("/",), commit, transport)
    safe_write.write_whole(_record_path(folder),
                           json.dumps({"commit": fetched.commit}, indent=1) + "\n",
                           prefix=".folder-")
    return pressless_import.read_folder(held), fetched.commit


def look_site(folder: Path, settings: Settings, key: str, address: str, commit: str = "",
              transport: publisher.Transport | None = None
              ) -> tuple[pressless_import.Found, str]:
    """The live site at `address` laid out at import/folder/ (PRESS-0333 § 4.2); what
    `read_folder` found there, and the commit it stands for, which names the state
    shown though the pages did not come from it. An address it cannot read leaves the
    folder empty, so no `index.html` is found."""
    held = _cleared_held(folder)
    commit = commit or publisher.head_commit(settings, key, transport)
    crawled = fetch.fetch_site(address, held, lambda: _room(held))
    # The record last: it says the folder is whole, so a close between the
    # two never leaves a held commit without its list of what was left out.
    pressless_import.write_folder_left(_imports(folder), crawled.left)
    safe_write.write_whole(_record_path(folder), json.dumps({"commit": commit}, indent=1) + "\n",
                           prefix=".folder-")
    return pressless_import.read_folder(held), commit


def _cleared_held(folder: Path) -> Path:
    """import/folder/, forgotten and gone. On Windows a file another program
    holds open survives the forgetting, and a read on top of it would bring in
    a page from the state read before, so that stops here."""
    forget_folder(folder)
    held = _held_folder(folder)
    if held.exists():
        raise undo.FetchAreaInUse("import/folder could not be emptied")
    return held


def forget_folder(folder: Path) -> None:
    """A repository read and refused, or one read again, leaves no copy behind."""
    shutil.rmtree(_held_folder(folder), ignore_errors=True)
    _record_path(folder).unlink(missing_ok=True)
    pressless_import.forget_folder_left(_imports(folder))


def _lay_out(folder: Path, settings: Settings, key: str, commit: str, address: str,
             transport: publisher.Transport | None) -> pressless_import.Found:
    if address:
        return look_site(folder, settings, key, address, commit, transport)[0]
    return look_folder(folder, settings, key, commit, transport)[0]


def read_held_or_fetch(folder: Path, settings: Settings, key: str, commit: str,
               transport: publisher.Transport | None = None,
               address: str = "") -> pressless_import.Found:
    """What the state at `commit` holds: from import/folder/ where it holds that
    state, so the screen shows what Finish writes; else laid out again, from the
    live site where `address` names one."""
    if _held_commit(folder) == commit:
        return pressless_import.read_folder(_held_folder(folder))
    return _lay_out(folder, settings, key, commit, address, transport)


def bring_folder(folder: Path, settings: Settings, key: str, commit: str, *,
                 capture: Callable[[], AbstractContextManager[list[str]]] = nothing_captured,
                 notices: list[str] | None = None,
                 transport: publisher.Transport | None = None,
                 address: str = "") -> pressless_import.Brought:
    """Bring in the repository as it stood at `commit`, where nothing has yet.
    A press after a failed save, or after a close during the moves, answers from
    what was brought in then, reading nothing from GitHub. `capture` wraps the
    Store's reads and writes and never the fetch, as take_in's does. With `address`,
    the pages came from the live site there (PRESS-0333 § 4.3)."""
    folder = Path(folder)
    gathered = notices if notices is not None else []
    captured = gatherer(capture, gathered)
    stopped = pressless_import.finish(folder)
    if stopped is not None:
        raise pressless_import.ImportStopped(stopped)
    if captured(lambda: store.holds_a_site(folder)):
        brought = pressless_import.read_brought(folder, commit)
        if brought is not None:
            forget_folder(folder)
            return brought
    # A Store holding a site this commit did not bring in is refused by
    # `bring_in_folder` below, so nothing is downloaded for it first: a close
    # during the moves was finished by `finish` above.
    if _held_commit(folder) != commit and not captured(lambda: store.holds_a_site(folder)):
        _lay_out(folder, settings, key, commit, address, transport)
    left = pressless_import.read_folder_left(_imports(folder)) if address else ()
    return captured(lambda: pressless_import.bring_in_folder(_held_folder(folder), folder,
                                                              left=left, commit=commit))
