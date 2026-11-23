"""Publisher — making GitHub match the folder it was handed.

The contract is docs/specs/PRESS-0009-publisher.md, an umbrella covering
PRESS-0009 and PRESS-0010. This module imports no other part of Pressless
than Settings, and only the modules §5 INV-1 names beside it, which import
none: it is handed the publishing key as an argument and never reaches
Credentials, which is what keeps docs/design.md rule 10 true.

Its core is three requests: make the repository match this folder, report
what sits at the repository root, and fetch back an earlier state. Beside
them sit setup's reads of an account and a repository, and the GitHub Pages
reads and switches that setup, the takeover and a custom domain make. It
writes no prose for the writer, keeps no state between calls, and cannot
tell an entry from a stylesheet.

Every failure is one of the typed exceptions below, and none of them carries
the key (§5 INV-7). The Face turns each into the three-part sentence
docs/design.md § Errors requires; this module writes none of them.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import shutil
import tempfile
import threading
import time
import urllib.parse
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Protocol

from pressless import https, os_reason, progress, safe_write
from pressless.settings import Settings, root_key

API = "https://api.github.com"

_SIGN_IN_PREFIX = "ghu_"   # every GitHub App sign-in's pass; no publishing key starts so

# GitHub asks for at least a second between successive write requests (§4.3).
# A breach is answered with a retry hint rather than a plain refusal, so the
# wait is honoured and the write retried; only an exhausted bound raises.
PACE_SECONDS = 1.0

# Blob creation is paced faster, and the split is measured rather than advised
# (§4.3). PRESS-0092 sent 550 blob creations inside one rate-limit hour, serial,
# every one accepted, at a sustained 136 a minute -- past both documented
# content-generating thresholds. Half a second is 120 a minute, under what was
# measured accepted, so this reduces the pace rather than removing it. The tree,
# the commit and the reference update keep PACE_SECONDS: those three are
# plausibly what the documented limits are about, nothing has measured them,
# and there are three per publish so pacing them costs nothing (PRESS-0114).
BLOB_PACE_SECONDS = 0.5

MAX_RETRIES = 4

# What to wait when GitHub says slow down and names no interval. Its own
# documentation asks for at least a minute; waiting PACE_SECONDS instead spent
# the whole retry bound in about four seconds, so the retry could not clear a
# limit it had never waited out (PRESS-0046).
RATE_LIMIT_SECONDS = 60.0

# The longest wait honoured. A secondary limit asks for seconds; the PRIMARY
# one names a reset that can be most of an hour away, and sleeping that out
# would block with nothing said to the writer. A longer ask raises RateLimited
# instead, which §6 already gives the Face a row for (PRESS-0046).
MAX_WAIT_SECONDS = 120.0

# A publish and a fetch are the exception, once per request: past the hourly
# allowance they wait for the reset GitHub names, counting down on the progress
# record, so a large publish finishes in its one commit rather than failing
# late and sending every file again (PRESS-0471), and a take-in, undo or
# takeover read finishes rather than failing (PRESS-0490). The allowance is
# hourly, so a reset further off than this is a clock or an answer gone
# wrong, and is refused.
MAX_RESET_WAIT_SECONDS = 3900.0
# A fetch made while a page loads waits only this long: a browser gives up on
# a load after about 300 s (Firefox), so a longer wait would end in its error
# rather than a countdown (PRESS-0490).
PAGE_RESET_WAIT_SECONDS = 240.0
COUNTDOWN_SECONDS = 1.0

# Successive retries wait longer. GitHub's rate-limit documentation asks for an
# exponentially increasing wait between retries and warns that continuing to
# request while limited risks the integration being banned; the wait was flat,
# bounded only by the retry count (PRESS-0113). The factor multiplies the hint
# GitHub gave, so the FIRST retry still waits exactly as asked.
RETRY_BACKOFF = 2.0

# A fetch reads its blobs a few at a time (PRESS-0461, §4.5). GitHub's
# documented secondary limits allow 100 requests at once and 900 points a
# minute, a read costing one. Starts are spaced READ_PACE_SECONDS apart, 800 a
# minute, so a fast line stays under the points whatever the count; four
# readers keep that rate busy where a read takes a quarter of a second, and
# more would only hold more connections and memory. FETCH_AHEAD bounds the
# blobs read and not yet written.
FETCH_WORKERS = 4
READ_PACE_SECONDS = 60 / 800
FETCH_AHEAD = 2 * FETCH_WORKERS

# Every blob is written with the ordinary file mode. §4.3 takes one rule for
# prose and photographs alike rather than two split by a property of the file.
BLOB_MODE = "100644"

# The tree entry that REMOVES a path: a null sha, per GitHub's tree API.
REMOVED = None

# Every request carries this, so a black-holed connection fails instead of
# hanging forever (PRESS-0041). It bounds each socket operation rather than
# the whole request, so a large upload that keeps making progress is not cut
# off.
TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Outcome:
    commit: str                  # sha written; "" when nothing differed
    uploaded: tuple[str, ...]    # repository-relative paths written
    removed: tuple[str, ...]     # repository-relative paths deleted


@dataclass(frozen=True)
class Fetched:
    commit: str                  # the sha fetched from
    paths: tuple[str, ...]       # repository-relative paths written out


class PublishError(Exception):
    """Anything this module refuses to act on."""


class Unreachable(PublishError):
    """No answer from GitHub, before the branch was touched."""


class OutcomeUnknown(PublishError):
    """A write that may have moved the branch (the reference update, or a
    Contents API write: the start file, `.nojekyll` or `CNAME`) was attempted
    and its result is unknown."""


class Refused(PublishError):
    """Key rejected, or no write access."""


class SignInRefused(Refused):
    """A sign-in's pass rejected, or no write access with it (PRESS-0233)."""


class RepositoryMissing(PublishError):
    """The repository URL itself answers 404."""


class Conflict(PublishError):
    """The branch moved under us."""


class TooLarge(PublishError):
    """A documented GitHub limit was hit."""


class RateLimited(PublishError):
    """GitHub asked us to slow down, and retrying did not clear it."""


class NoPreviousState(PublishError):
    """Nothing before the current commit."""


# Each type below is its own because `docs/design.md` § Errors requires
# every message to end with what to do next, and for these that differs
# (§4.1, PRESS-0116). SiteFolderMissing: fix the setting. StrayFile: remove
# the file. SiteWouldBeEmptied: rebuild the site. FetchNotWritten: free
# space. RemoteStateMissing: retry. UnfetchablePath: rename that file on the
# site (PRESS-0160). RepositoryMoved: enter the repository's new name
# (PRESS-0167).


class SiteFolderMissing(PublishError):
    """The handed folder is not a directory."""


class StrayFile(PublishError):
    """The folder holds what the Builder did not produce (§4.4)."""


class SiteWouldBeEmptied(PublishError):
    """Every unprotected path removed and none written."""


class FetchNotWritten(PublishError):
    """fetch_previous could not write into the folder it was handed."""


class RemoteStateMissing(PublishError):
    """Something INSIDE a repository that answers is absent."""


class UnfetchablePath(PublishError):
    """A fetched path this system's disk cannot hold (§4.5)."""


class RepositoryMoved(PublishError):
    """A write was redirected: the repository was renamed or moved (§6)."""


class Transport(Protocol):
    """The one seam to the network (§4.1). Tests hand in a double, and the other
    modules that call a web service take the same shape.

    Three things about it are part of the contract, because a test double
    must supply all three. It returns the response HEADERS, which is where a
    rate-limit hint arrives. It signals *no answer* by raising OSError; every
    HTTP status, error statuses included, is RETURNED rather than raised, so
    this module owns the mapping to the types above. And `wait` is the pacing
    clock -- nothing here calls sleep itself, so a test observes the spacing
    INV-9 asserts by recording calls rather than by waiting real seconds.
    """

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]
                ) -> tuple[int, dict[str, str], bytes]: ...

    def wait(self, seconds: float) -> None: ...


class _Urllib(https.Client):
    """The module's own client, used when no double is handed in. The
    request is the shared client's (PRESS-0331); the pacing clock is ours."""

    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        super().__init__(timeout, keep_alive=True)    # PRESS-0461

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


def blob_hash(data: bytes) -> str:
    """The git blob hash of `data`, computed locally (§4.2).

    Measured against `git hash-object` on text, binary and empty input: all
    three agree. This is what lets an unchanged file be recognised without
    downloading it.
    """
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data,
                        usedforsecurity=False).hexdigest()


def publish(settings: Settings, folder: Path, token: str, message: str,
            transport: Transport | None = None) -> Outcome:
    """Make the repository match `folder`, in one commit -- two on a
    repository with no commits.

    Four writes in the order §4.3 fixes, and only the last changes what a
    reader sees: blobs, one tree, one commit, one reference update. An
    interruption at any earlier point leaves the site exactly as it was.

    A repository with no commits is first started with one file of the
    folder, written through the Contents API (PRESS-0127 §4.3). That write
    precedes the blobs; there is no earlier site for it to damage.
    """
    folder = _site_folder(folder)
    session = _Session(transport or _Urllib(), token, waits_for_reset="progress.sending")
    branch = _default_branch(session, settings.repository)
    untouchable = settings.untouchable
    started: _Started | None = None
    head = _head(session, settings.repository, branch)
    if head is None:
        started = _start(session, settings.repository, folder, untouchable, message)
        if started is None:
            return Outcome(commit="", uploaded=(), removed=())
        head = _head(session, settings.repository, branch)
        if head is None:
            # The start is made once (PRESS-0127 INV-6), never retried.
            raise RemoteStateMissing(
                "GitHub still reports the repository empty after its first "
                "commit was written"
            )
    base_commit = _required(head, "sha", "the head commit")
    listing = _tree(session, settings.repository, base_commit)
    remote = _blobs_in(listing)

    local = started.local if started else _local_files(folder, untouchable)

    uploaded, removed = _compare(local, remote, untouchable)

    if not uploaded and not removed:
        # Nothing differed, so nothing is written at all (§5 INV-4) -- unless
        # the start commit already was, and then it is what was published.
        if started:
            return Outcome(commit=started.commit, uploaded=(started.path,), removed=())
        return Outcome(commit="", uploaded=(), removed=())

    entries = []
    whole = sum(file.size for file in uploaded.values())
    size = 0
    progress.count("progress.sending", 0, len(uploaded), size, whole)
    for path, file in uploaded.items():
        content = _read_again(path, file)
        sha = _required(
            session.write("POST", _repo_url(settings.repository, "git/blobs"),
                          {"content": base64.b64encode(content).decode("ascii"),
                           "encoding": "base64"},
                          pace=BLOB_PACE_SECONDS),
            "sha", "a blob",
        )
        entries.append({"path": path, "mode": BLOB_MODE, "type": "blob",
                        "sha": sha})
        size += len(content)
        progress.count("progress.sending", len(entries), len(uploaded), size, whole)
    for path in removed:
        entries.append({"path": path, "mode": BLOB_MODE, "type": "blob",
                        "sha": REMOVED})

    tree = _required(
        session.write("POST", _repo_url(settings.repository, "git/trees"),
                      {"base_tree": _required(listing, "sha", "the base tree"),
                       "tree": entries}),
        "sha", "the tree",
    )
    commit = _required(
        session.write("POST", _repo_url(settings.repository, "git/commits"),
                      {"message": message, "tree": tree,
                       "parents": [base_commit]}),
        "sha", "the commit",
    )

    # The reference update is the last write, and it is never forced (§5
    # INV-3, INV-5). The commit's parent is the state that was read, so a
    # branch that moved meanwhile is not a fast-forward and GitHub refuses
    # it -- which becomes Conflict. Forcing would discard the other write.
    session.write("PATCH",
                  _repo_url(settings.repository,
                            f"git/refs/heads/{_segment(branch)}"),
                  {"sha": commit, "force": False},
                  outcome_unknown=True)

    # The start file went up in its own commit, so the listing holds it and
    # _compare does not; the Outcome still names it (PRESS-0127 INV-8).
    sent = {*uploaded, *([started.path] if started else [])}
    return Outcome(commit=commit, uploaded=tuple(sorted(sent)), removed=tuple(removed))


@dataclass(frozen=True)
class _Started:
    """An empty repository's first commit (PRESS-0127 §4.3): the folder as
    read before it, the one file it wrote, and that commit's sha."""
    local: dict[str, _Local]
    path: str
    commit: str


def _start(session: _Session, repository: str, folder: Path,
           untouchable: tuple[str, ...], message: str) -> _Started | None:
    """Start an empty repository with one file of `folder`; None, writing
    nothing, where the folder holds nothing unprotected.

    The Git Data API cannot write a first commit (PRESS-0127 §2), so one file
    goes through the Contents API. The folder is read before that write, so
    every refusal leaves the repository still empty."""
    local = _local_files(folder, untouchable)
    path = next((path for path in sorted(local) if not _is_protected(path, untouchable)), "")
    if not path:
        return None
    answer = session.write(
        "PUT",
        _repo_url(repository, f"contents/{_segment(path)}"),
        {"message": message,
         "content": base64.b64encode(_read_again(path, local[path])).decode("ascii")},
        outcome_unknown=True,
    )
    written = answer.get("commit")
    commit = written.get("sha") if isinstance(written, dict) else None
    if not commit:
        # GitHub acted and did not say how, so the start commit may exist
        # (§6, PRESS-0166).
        raise OutcomeUnknown(
            "GitHub took the start file without naming its commit, so "
            "whether the site moved is unknown")
    return _Started(local, path, commit)


@dataclass(frozen=True)
class Plan:
    """What a publish of the folder would do (PRESS-0345 § 4.1)."""
    uploaded: tuple[str, ...]   # paths it would write, sorted
    removed: tuple[str, ...]    # paths it would delete, sorted


def plan(settings: Settings, folder: Path, token: str,
         transport: Transport | None = None, *,
         named: frozenset[str] = frozenset()) -> Plan:
    """PRESS-0345 § 4.1: the reads `publish` makes before its first write, and
    no write. `named` paths are files the folder does not carry, compared by
    presence alone: uploaded where the listing lacks one, never removed. A
    repository with no commits plans every unprotected file as uploaded, which
    is what `publish` sends once it has started one."""
    folder = _site_folder(folder)
    session = _Session(transport or _Urllib(), token)
    local: dict[str, _Local | None] = {
        **_local_files(folder, settings.untouchable), **dict.fromkeys(named)}
    uploaded, removed = _compare(local, _remote(session, settings.repository),
                                 settings.untouchable)
    return Plan(tuple(uploaded), tuple(removed))


def remote_paths(settings: Settings, token: str,
                 transport: Transport | None = None) -> tuple[str, ...]:
    """Every file on the default branch, sorted; () for a repository with no
    commits. It decides nothing: rule 5 leaves this module unable to tell an
    entry page from any other file (PRESS-0446)."""
    session = _Session(transport or _Urllib(), token)
    return tuple(sorted(_remote(session, settings.repository)))


def _site_folder(folder: Path) -> Path:
    """`folder`, checked first and typed by `publish` and `plan` alike: a walk
    that read a missing folder as empty would have §4.4 read every unprotected
    remote path as a deletion the writer asked for, and report the wipe as a
    successful publish (PRESS-0043)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise SiteFolderMissing(
            "the site folder is not a directory, so there is nothing to publish"
        )
    return folder


def _head(session: _Session, repository: str, ref: str = "HEAD") -> dict | None:
    """The commit `ref` stands at, or None for a repository with no commits.
    Each caller says what an empty repository means to it."""
    return session.read(_repo_url(repository, f"commits/{_segment(ref)}"), empty_ok=True)


def _remote(session: _Session, repository: str) -> dict[str, str]:
    """Each file on the default branch and its blob hash; {} for a repository
    with no commits."""
    head = _head(session, repository, _default_branch(session, repository))
    if head is None:
        return {}
    return _blobs_in(_tree(session, repository, _required(head, "sha", "the head commit")))


def _compare(local: dict[str, _Local | None], remote: dict[str, str],
             untouchable: tuple[str, ...]
             ) -> tuple[dict[str, _Local | None], list[str]]:
    """What differs (§4.2, INV-4): the unprotected files whose hash the listing
    does not hold, and the unprotected remote paths the folder lacks. A file
    with no `_Local` is compared by presence (PRESS-0345 § 4.1).

    Raises SiteWouldBeEmptied where every unprotected remote path would go and
    nothing would be written: a finished build is never empty, and §3 decision
    1 makes the commit unrecoverable from inside Pressless (PRESS-0043). `plan`
    shares it, so a preview refuses as the press would."""
    uploaded: dict[str, _Local | None] = {}
    for path, file in sorted(local.items()):
        if _is_protected(path, untouchable):
            continue
        if path in remote if file is None else remote.get(path) == file.sha:
            continue
        uploaded[path] = file
    unprotected = [path for path in remote if not _is_protected(path, untouchable)]
    removed = sorted(path for path in unprotected if path not in local)
    if not uploaded and removed and len(removed) == len(unprotected):
        raise SiteWouldBeEmptied(
            "publishing the site folder would delete every file on the site "
            "and add none, so it is refused"
        )
    return uploaded, removed


def root_entries(settings: Settings, token: str | None,
                 transport: Transport | None = None) -> tuple[str, ...]:
    """Every entry at the repository root, as bare names (§4.4).

    Files and directories alike, with no trailing slash, in the form
    settings.untouchable holds. It decides nothing and filters nothing --
    rule 5 leaves this module unable to tell a stylesheet from an entry, so
    it cannot know which of them the Builder produces. Setup and the Face
    remove those and store the rest. With no key it reads a Public
    repository as `public_repository` does (PRESS-0231 § 4.3).
    """
    return _root_names(_Session(transport or _Urllib(), token), settings.repository)


def _root_names(session: _Session, repository: str) -> tuple[str, ...]:
    """root_entries' answer over `session`; () for an empty repository."""
    head = _head(session, repository)
    if head is None:
        return ()
    listing = _tree(session, repository, _required(head, "sha", "the head commit"),
                    recursive=False)
    return tuple(sorted(
        entry["path"] for entry in listing.get("tree", []) if entry.get("path")
    ))


# PRESS-0212 § 4.5: the setup wizard's reads, and the one switch it makes.

NO_JEKYLL = ".nojekyll"   # Pages serves the files as they are, `_dsc1234.jpg` included
CNAME = "CNAME"           # where a branch build stores a custom domain (PRESS-0333)


@dataclass(frozen=True)
class Pages:
    on: bool
    address: str | None       # GitHub's html_url while on
    serves_root: bool         # a branch build of the default branch's "/"
    built_by_actions: bool = False   # PRESS-0333: its build_type is "workflow"
    domain: str | None = None        # PRESS-0333: its custom domain
    https_enforced: bool = False     # PRESS-0222
    certificate: str = ""            # PRESS-0222: its HTTPS certificate's state
    branch: str | None = None        # PRESS-0336: a branch build's branch, not the default

    @property
    def built_elsewhere(self) -> bool:
        """Built by Actions, or from another branch: what a takeover replaces."""
        return self.built_by_actions or self.branch is not None


def account_exists(account: str, transport: Transport | None = None) -> bool:
    """Whether GitHub has an account by this name. Sends no key: there is none yet."""
    try:
        _Session(transport or _Urllib(), None).read(f"{API}/users/{_segment(account)}")
    except RemoteStateMissing:
        return False
    return True


def public_repository(repository: str, transport: Transport | None = None) -> bool:
    """Whether `owner/name` is a repository GitHub shows without a key: a
    Private one answers 404 exactly as a missing one does."""
    try:
        _Session(transport or _Urllib(), None).read(_repo_url(repository, ""))
    except RepositoryMissing:
        return False
    return True


def pages(repository: str, token: str, transport: Transport | None = None) -> Pages:
    """Whether Pages is on, where it answers, and whether it serves what
    Pressless publishes."""
    return _pages(_Session(transport or _Urllib(), token), repository)


def switch_pages_on(repository: str, token: str,
                    transport: Transport | None = None) -> Pages:
    """Write an empty `.nojekyll` where the root lacks one, then switch Pages
    on for the default branch's root. On an empty repository the file is the
    first commit, which Pages needs."""
    session = _Session(transport or _Urllib(), token)
    _write_no_jekyll(session, repository)
    branch = _default_branch(session, repository)
    try:
        session.write("POST", _repo_url(repository, "pages"),
                      {"build_type": "legacy", "source": {"branch": branch, "path": "/"}})
    except PublishError:
        # GitHub switches Pages on by itself when the first commit lands in
        # <account>.github.io, then refuses the switch with 409. On is on.
        shown = _pages(session, repository)
        if shown.on:
            return shown
        raise
    return _pages(session, repository)


def _write_no_jekyll(session: _Session, repository: str) -> None:
    if NO_JEKYLL not in _root_names(session, repository):
        session.write("PUT", _repo_url(repository, f"contents/{NO_JEKYLL}"),
                      {"message": "Serve the site as it is", "content": ""},
                      outcome_unknown=True)


def switch_pages_to_branch(repository: str, token: str, domain: str | None,
                           transport: Transport | None = None) -> Pages:
    """PRESS-0333 § 4.5: Pages moves from an Actions build to the default branch's
    root, keeping `domain`. A branch build stores a custom domain in a `CNAME` file
    in its root, which an Actions build ignores, so one may be absent or stale.
    `cname` is sent only with a value: GitHub documents null as removing the domain.
    A branch site is built only when a commit lands, and every commit here came
    before the switch, so a build is asked for last; without it the old site stayed
    up until the next publish (hand check, 2026-11-03)."""
    session = _Session(transport or _Urllib(), token)
    _write_no_jekyll(session, repository)
    if domain:
        _write_cname(session, repository, domain)
    switch: dict = {"build_type": "legacy",
                    "source": {"branch": _default_branch(session, repository), "path": "/"}}
    if domain:
        switch["cname"] = domain
    session.write("PUT", _repo_url(repository, "pages"), switch, no_content=True)
    _request_build(session, repository)
    return _pages(session, repository)


def request_build(repository: str, token: str, transport: Transport | None = None) -> None:
    """PRESS-0333 § 4.5 step 3: ask Pages to build again, for a switch whose
    own request for one may never have landed."""
    _request_build(_Session(transport or _Urllib(), token), repository)


def _request_build(session: _Session, repository: str) -> None:
    session.write("POST", _repo_url(repository, "pages/builds"), {})


def set_domain(repository: str, token: str, domain: str,
               transport: Transport | None = None) -> Pages:
    """PRESS-0222: a branch build serves `domain`, by its `CNAME` file and its setting."""
    session = _Session(transport or _Urllib(), token)
    _write_cname(session, repository, domain)
    session.write("PUT", _repo_url(repository, "pages"), {"cname": domain}, no_content=True)
    return _pages(session, repository)


def enforce_https(repository: str, token: str, domain: str,
                  transport: Transport | None = None) -> None:
    """PRESS-0222. `cname` is sent too: omitting it is undocumented (`switch_pages_to_branch`)."""
    session = _Session(transport or _Urllib(), token)
    session.write("PUT", _repo_url(repository, "pages"),
                  {"cname": domain, "https_enforced": True}, no_content=True)


def kept_on_a_branch(untouchable: tuple[str, ...], domain: str | None) -> tuple[str, ...]:
    """What a branch build needs a publish to leave alone. A `CNAME` with no domain behind
    it comes off the list, so a publish removes it, or the build would read it as one."""
    wanted = {NO_JEKYLL, *([CNAME] if domain else [])}
    held = {root_key(name) for name in untouchable}
    kept = [name for name in untouchable if domain
            or root_key(name) != CNAME.casefold()]
    return (*kept, *sorted(name for name in wanted if name.casefold() not in held))


def _write_cname(session: _Session, repository: str, domain: str) -> None:
    url = _repo_url(repository, f"contents/{CNAME}")
    change: dict = {"message": "Keep the site's own domain",
                    "content": base64.b64encode(f"{domain}\n".encode()).decode("ascii")}
    try:
        held = session.read(url)
    except RemoteStateMissing:
        held = None
    if held is not None:
        if _content_of(held).decode("utf-8", "replace").strip() == domain:
            return
        change["sha"] = _required(held, "sha", "the CNAME file")
    session.write("PUT", url, change, outcome_unknown=True)


def head_commit(settings: Settings, token: str, transport: Transport | None = None) -> str:
    """The commit the default branch stands at. A repository with no commits
    raises RemoteStateMissing, as fetch_state does."""
    head = _head(_Session(transport or _Urllib(), token), settings.repository)
    if head is None:
        raise RemoteStateMissing("the repository has no commits to read")
    return _required(head, "sha", "the head commit")


def can_push(repository: str, token: str, transport: Transport | None = None) -> bool:
    """Whether this key's account may write to `repository`. A public repository can be
    read by anyone, so a read proves nothing. A repository it cannot see is False. An
    answer naming no permissions is not a refusal, so it is not treated as one."""
    try:
        answer = _Session(transport or _Urllib(), token).read(_repo_url(repository, ""))
    except (RepositoryMissing, Refused):
        return False
    permissions = answer.get("permissions")
    return not isinstance(permissions, dict) or permissions.get("push") is not False


def default_branch(repository: str, token: str, transport: Transport | None = None) -> str:
    return _default_branch(_Session(transport or _Urllib(), token), repository)


def _pages(session: _Session, repository: str) -> Pages:
    try:
        answer = session.read(_repo_url(repository, "pages"))
    except RemoteStateMissing:
        return Pages(on=False, address=None, serves_root=False)
    source = answer.get("source") if isinstance(answer.get("source"), dict) else {}
    address = answer.get("html_url")
    # An answer with no build_type predates the field, when every Pages site
    # was built from a branch, so it is read as one.
    served = source.get("branch") if answer.get("build_type") in (None, "legacy") else None
    default = _default_branch(session, repository) if isinstance(served, str) and served else None
    serves_root = default is not None and served == default and source.get("path") == "/"
    domain = answer.get("cname")
    certificate = answer.get("https_certificate")
    state = certificate.get("state") if isinstance(certificate, dict) else None
    return Pages(on=True, address=address if isinstance(address, str) else None,
                 serves_root=serves_root, built_by_actions=answer.get("build_type") == "workflow",
                 domain=domain if isinstance(domain, str) and domain else None,
                 https_enforced=answer.get("https_enforced") is True,
                 certificate=state if isinstance(state, str) else "",
                 branch=served if default is not None and served != default else None)


def fetch_previous(settings: Settings, token: str, into: Path,
                   prefix: str = "",
                   transport: Transport | None = None) -> Fetched:
    """Write the state before the current commit into `into` (§4.5).

    Reads the current commit's FIRST parent -- not the branch's
    second-newest commit, which differs as soon as anything is merged. It
    writes files and returns; it does not publish, does not touch the Store,
    and does not decide what the fetched state means.

    A fetched file lands at `into` joined to its full repository-relative
    path, with `prefix` used to SELECT and never to strip, so Fetched.paths
    and the layout under `into` are the same strings.

    Nothing lands in `into` until every file has been fetched. Writing them
    as it went left a failure part-way through as a mixture of the previous
    state and whatever was already there, which the Face cannot tell from a
    complete fetch -- and undo is the feature that must not produce one
    (PRESS-0046).
    """
    session = _Session(transport or _Urllib(), token, waits_for_reset="progress.downloading")
    current = _head(session, settings.repository)
    if current is None:
        raise NoPreviousState(
            "the repository has no commits, so there is no state before it"
        )
    parents = current.get("parents") or []
    if not parents:
        raise NoPreviousState(
            "the current commit has no parent, so there is no state before it"
        )
    parent = _required(parents[0], "sha", "the first parent")
    return _fetch(session, settings.repository, parent, (prefix,), Path(into))


def fetch_state(settings: Settings, token: str, into: Path,
                prefixes: tuple[str, ...], commit: str = "",
                transport: Transport | None = None, *,
                longest_reset_wait: float = MAX_RESET_WAIT_SECONDS) -> Fetched:
    """Write the state at `commit`, or at the default branch's current commit
    where `commit` is "", into `into`, keeping only paths within one of
    `prefixes` (PRESS-0218 § 4.1).

    fetch_previous's body, so it keeps the same guarantees: each path lands
    at its full repository-relative path, nothing lands until every file has
    been fetched, and a path outside `into` is refused. A repository with no
    commits, or a commit it no longer holds, raises RemoteStateMissing.
    A reset further off than `longest_reset_wait` raises RateLimited (§4.3).
    """
    session = _Session(transport or _Urllib(), token, waits_for_reset="progress.downloading",
                       longest_reset_wait=longest_reset_wait)
    if not commit:
        current = _head(session, settings.repository)
        if current is None:
            raise RemoteStateMissing("the repository has no commits to read")
        commit = _required(current, "sha", "the head commit")
    return _fetch(session, settings.repository, commit, prefixes, Path(into))


def _fetch(session: _Session, repository: str, commit: str,
           prefixes: tuple[str, ...], into: Path) -> Fetched:
    """The body fetch_previous and fetch_state share: the tree of `commit`,
    each path within one of `prefixes`, staged and then moved into `into`."""
    listing = _tree(session, repository, commit)
    if _ON_WINDOWS:
        _refuse_what_windows_cannot_hold(listing, prefixes)

    wanted = [entry for entry in listing.get("tree", [])
              if entry.get("path") and entry.get("type") == "blob"
              and any(_within_prefix(entry["path"], prefix) for prefix in prefixes)]
    # PRESS-0435: the listing gives each blob's size; a listing without one
    # leaves the bar to run on files.
    sizes = [entry.get("size") for entry in wanted]
    whole = sum(sizes) if all(isinstance(size, int) for size in sizes) else None
    progress.count("progress.downloading", 0, len(wanted), 0, whole)

    def not_written(exc: OSError) -> FetchNotWritten:
        return FetchNotWritten(
            f"the fetched state could not be written to the fetch area: {os_reason.of(exc)}")

    def cannot_hold(path: str, target: Path, exc: OSError | ValueError) -> PublishError:
        # A path too long for Windows is no reason to free space (PRESS-0160):
        # past MAX_PATH where long paths are off, an OSError; past 32,767
        # characters, a ValueError before the system is asked.
        if isinstance(exc, ValueError) or (_ON_WINDOWS
                                           and len(str(target)) >= _WINDOWS_LONGEST):
            return UnfetchablePath(
                f"the fetched state names {path!r}, which this computer cannot hold")
        return not_written(exc)

    try:
        # Staged inside `into` rather than beside it, so the move at the end
        # is a rename on one filesystem rather than a copy that can fail
        # half-done. The same temp-then-replace shape settings.save uses.
        into.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=into, prefix=".fetch-"))
    except OSError as exc:
        # A full disk, or a folder that cannot be written. §4.1 says every
        # failure is one of the types above (PRESS-0073).
        raise not_written(exc) from exc

    # Each blob counts once, as its read lands, into this thread's record
    # from whichever reader read it (PRESS-0435 INV-3, PRESS-0461).
    report = progress.counter()
    counting = threading.Lock()
    read = {"files": 0, "bytes": 0}

    def read_blob(entry: dict) -> dict:
        # _blobs_in reads the same field with .get; this site indexed it
        # and raised a bare KeyError on an entry without one, which is
        # neither of §4.1's types (PRESS-0073).
        sha = _required(entry, "sha", f"a sha for {entry['path']!r}")
        blob = session.paced_read(_repo_url(repository, f"git/blobs/{_segment(sha)}"))
        with counting:
            read["files"] += 1
            read["bytes"] += entry["size"] if isinstance(entry.get("size"), int) else 0
            report("progress.downloading", read["files"], len(wanted), read["bytes"], whole)
        return blob

    pool = ThreadPoolExecutor(FETCH_WORKERS, thread_name_prefix="fetch")
    try:
        written = []
        # Read ahead in listing order and written in it, so the first failure
        # raised is the first in the listing, as it was one at a time.
        entries = iter(wanted)
        ahead: deque[tuple[dict, Future]] = deque()
        while True:
            while len(ahead) < FETCH_AHEAD and (entry := next(entries, None)) is not None:
                ahead.append((entry, pool.submit(read_blob, entry)))
            if not ahead:
                break
            entry, reading = ahead.popleft()
            blob = reading.result()
            path = entry["path"]
            target = staging / path
            try:
                inside = _within_folder(target, staging)
                if inside:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(_content_of(blob))
            except (OSError, ValueError) as exc:
                raise cannot_hold(path, target, exc) from exc
            if not inside:
                raise PublishError(
                    f"the repository listing names {path!r}, which would be "
                    f"written outside the folder asked for"
                )
            written.append(path)

        try:
            # Every directory first, so the moves that follow are renames
            # with nothing left to fail on.
            for path in written:
                (into / path).parent.mkdir(parents=True, exist_ok=True)
            for path in written:
                _replace_patiently(session, staging / path, into / path)
        except OSError as exc:
            raise not_written(exc) from exc
    finally:
        pool.shutdown(cancel_futures=True)
        shutil.rmtree(staging, ignore_errors=True)

    return Fetched(commit=commit, paths=tuple(sorted(written)))


def _replace_patiently(session: _Session, source: Path, target: Path) -> None:
    """On Windows a scanner briefly holding a newly written file refuses its
    rename with a sharing error, which is no reason to free space. This is
    safe_write.patiently on the session's clock, so a test sees each pause
    (§4.1's `wait`) rather than sleeping."""
    for attempt in range(safe_write.WINDOWS_TRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if not _ON_WINDOWS or attempt == safe_write.WINDOWS_TRIES - 1:
                raise
            session.pause(safe_write.WINDOWS_PAUSE)


class _Session:
    """One call's worth of requests, with the pacing and retry §4.3 fixes.

    Holds the key for the length of a call and never puts it in a message.
    """

    def __init__(self, client: Transport, token: str | None, *,
                 waits_for_reset: str = "",
                 longest_reset_wait: float = MAX_RESET_WAIT_SECONDS) -> None:
        self._client = client
        self._token = token     # None for the wizard's reads before there is a key
        self._written = False
        # A publish's and a fetch's (PRESS-0471, PRESS-0490): the progress key
        # its wait for the hourly reset says where nothing was counted yet; ""
        # where a spent allowance fails at once. Made on the job's thread, so
        # a reader thread's countdown reaches the job's record.
        self._waits_for_reset = waits_for_reset
        self._longest_reset_wait = longest_reset_wait   # PAGE_RESET_WAIT_SECONDS in a page load
        self._waiting = progress.waiter()
        self._pace = threading.Lock()
        self._last_read = -math.inf     # when the latest paced read may start
        self._hold_until = -math.inf    # a slow-down one reader was told of

    def paced_read(self, url: str) -> dict | None:
        """`read`, started READ_PACE_SECONDS after the paced one before it and
        after any slow-down a reader was told of, from whichever thread (§4.5,
        PRESS-0461). Each takes its start under the lock and waits outside it,
        so a slow-down told meanwhile is seen, and the start taken again."""
        while True:
            with self._pace:
                now = time.monotonic()
                start = max(now, self._last_read + READ_PACE_SECONDS, self._hold_until)
                self._last_read = start
                held = self._hold_until
            if start > now:
                self._client.wait(start - now)
            with self._pace:
                told = self._hold_until > held
            if not told:
                return self.read(url)

    def read(self, url: str, *, empty_ok: bool = False) -> dict | None:
        """GET `url`. With `empty_ok`, a repository with no commits answers
        None rather than a failure (PRESS-0127 §4.1)."""
        return self._call("GET", url, None, empty_ok=empty_ok)

    def pause(self, seconds: float) -> None:
        """Wait on the transport's clock, which a test records."""
        self._client.wait(seconds)

    def _wait_for_reset(self, seconds: float) -> None:
        """Wait out a spent hourly allowance a step at a time, the progress
        record saying how long is left at each (PRESS-0471)."""
        left = seconds
        try:
            while left > 0:
                self._waiting(math.ceil(left), self._waits_for_reset)
                step = min(COUNTDOWN_SECONDS, left)
                self._client.wait(step)
                left -= step
        finally:
            self._waiting(None, self._waits_for_reset)

    def write(self, method: str, url: str, payload: dict, *,
              outcome_unknown: bool = False, no_content: bool = False,
              pace: float = PACE_SECONDS) -> dict:
        # The pace before a write is the pace THAT write requires, not the one
        # before it -- so a tree write following a blob still waits the full
        # second. Applied after each write instead, the rule would depend on
        # ordering and the tree would inherit the blob's half second (§4.3).
        if self._written:
            self._client.wait(pace)
        self._written = True
        return self._call(method, url, payload,
                          outcome_unknown=outcome_unknown, no_content=no_content)

    def _call(self, method: str, url: str, payload: dict | None, *,
              outcome_unknown: bool = False, empty_ok: bool = False,
              no_content: bool = False) -> dict | None:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Pressless",
        }
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        if body is not None:
            # urllib inserts application/x-www-form-urlencoded whenever a
            # body is present and this is unset, which describes §4.3's
            # JSON as a form. A body-less read has nothing to declare.
            headers["Content-Type"] = "application/json"
        attempts = 0
        reset_waited = False
        while True:
            try:
                status, response_headers, data = self._client.request(
                    method, url, body, headers
                )
            except OSError as exc:
                # A write that may have moved the branch (the reference
                # update, or a Contents API write: the start file,
                # `.nojekyll`, `CNAME`) leaves the site's state genuinely
                # unknown when it fails (§6).
                failure = OutcomeUnknown if outcome_unknown else Unreachable
                raise failure(
                    f"no answer from GitHub for {method} {_without_account(url)}"
                    f" ({type(exc).__name__})"
                ) from None  # a substituted transport's error may carry the key

            hint = _retry_hint(status, response_headers, data)
            if hint is not None:
                if (hint.reset and self._waits_for_reset and not reset_waited
                        and MAX_WAIT_SECONDS < hint.seconds <= self._longest_reset_wait):
                    reset_waited = True
                    self._wait_for_reset(hint.seconds)
                    continue
                if hint.seconds > MAX_WAIT_SECONDS:
                    # Honouring it would block for as long as GitHub asked,
                    # with nothing said to the writer (PRESS-0046).
                    raise RateLimited(
                        f"GitHub asked us to wait {hint.seconds:.0f}s on {method} "
                        f"{_without_account(url)}, longer than a publish "
                        f"will block for"
                    )
                attempts += 1
                if attempts > MAX_RETRIES:
                    raise RateLimited(
                        f"GitHub asked us to wait on {method} "
                        f"{_without_account(url)} and was "
                        f"still asking after {MAX_RETRIES} retries"
                    )
                # Clamped rather than raised. The check above raises on what
                # GitHub ASKS for; the growth is ours, so exceeding the bound
                # by our own multiplication is not the writer's problem to be
                # told about -- it just stops growing (§4.3).
                backoff = min(hint.seconds * RETRY_BACKOFF ** (attempts - 1),
                              MAX_WAIT_SECONDS)
                with self._pace:
                    # The other readers of a fetch wait it out too (§4.5).
                    self._hold_until = max(self._hold_until, time.monotonic() + backoff)
                self._client.wait(backoff)
                continue

            if status in (301, 302, 303, 307, 308) and method != "GET":
                # GitHub's answer to a write for a renamed or moved
                # repository. https.Client follows none for a write, and
                # following would publish where Settings does not point
                # (§6, PRESS-0167).
                raise RepositoryMoved(
                    f"GitHub redirected {method} {_without_account(url)}: the "
                    f"repository was renamed or moved"
                )
            if no_content and status == 204:
                return {}
            if status in (200, 201):
                if not outcome_unknown:
                    return _parse(data)
                try:
                    return _parse(data)
                except PublishError:
                    # GitHub acted and the answer cannot say how (§6,
                    # PRESS-0166).
                    raise OutcomeUnknown(
                        f"GitHub's answer to {method} {_without_account(url)} "
                        f"is not readable, so whether the site moved is unknown"
                    ) from None
            if outcome_unknown and 200 <= status < 300:
                raise OutcomeUnknown(
                    f"GitHub answered {status} to {method} "
                    f"{_without_account(url)}, so whether the site moved is "
                    f"unknown"
                )
            if outcome_unknown and status >= 500:
                # An answer, but not one that says whether the branch moved:
                # a gateway can fail after the write was applied, which
                # leaves the site exactly as unknown as a dropped connection
                # does. §6's OutcomeUnknown row reads "no answer" and this is
                # its other route (PRESS-0046). Every other status is a
                # definitive refusal -- GitHub authenticates and validates
                # before it acts -- so those keep their own type and their
                # row's "unchanged".
                raise OutcomeUnknown(
                    f"GitHub answered {status} to {method} "
                    f"{_without_account(url)}, so whether the site moved is "
                    f"unknown"
                )
            if empty_ok and status in (409, 422) and _says_empty(data):
                # GitHub's answer for a repository with no commits (PRESS-0127
                # §4.1). The message is part of the test: its docs give the
                # status no meaning beyond "conflict". Told apart here, before
                # any type is chosen, so a 404 keeps its own.
                return None
            raise _failure(status, method, url, signed_in=(self._token or "").startswith(
                _SIGN_IN_PREFIX))


def _default_branch(session: _Session, repository: str) -> str:
    """The repository's default branch, resolved from the repository itself
    once per call (§4.2).

    Settings holds no branch field, and adding one would change PRESS-0001's
    shipped file format -- so the alternative to resolving it is hard-coding
    a name that is wrong for any repository whose default differs.
    """
    return _required(session.read(_repo_url(repository, "")), "default_branch",
                     "the default branch")


def _tree(session: _Session, repository: str, ref: str,
          recursive: bool = True) -> dict:
    """The repository's state at `ref`, as a tree listing.

    A listing GitHub flags as cut short raises TooLarge rather than being
    used (§5 INV-6): treating a cut listing as the repository's contents
    would make every missing path look locally-new and every deletion
    invisible.
    """
    suffix = "?recursive=1" if recursive else ""
    listing = session.read(
        _repo_url(repository, f"git/trees/{_segment(ref)}{suffix}")
    )
    if listing.get("truncated"):
        raise TooLarge(
            "GitHub cut the repository listing short, so what differs cannot "
            "be worked out from it"
        )
    return listing


def _repo_url(repository: str, suffix: str) -> str:
    base = f"{API}/repos/{repository}"
    return f"{base}/{suffix}" if suffix else base


def _without_account(url: str) -> str:
    """The request's URL with the account it sits under taken out.

    Every URL here carries `repos/<account>/<name>` or `users/<account>`,
    and `docs/design.md` § Logging names a repository by its short name,
    never `account/name`: the account identifies the writer as surely as a
    path does. The method and what was asked for still say which request
    failed.
    """
    for marker in ("/repos/", "/users/"):
        head, found, rest = url.partition(marker)
        if found:
            return f"{head}{found}{rest.partition('/')[2]}"
    return url


def _segment(value: str) -> str:
    """A value safe to put in a URL path (PRESS-0069).

    A refname may carry `#`, which starts a URL fragment and would silently
    truncate the request, or a non-ASCII character, which urlopen refuses
    outright rather than encoding. Slashes are kept: a refname may be
    several segments deep and those are real path separators.
    """
    return urllib.parse.quote(value, safe="/")


def _within_folder(target: Path, folder: Path) -> bool:
    """Whether `target` really lands inside `folder` (PRESS-0069).

    A tree entry's path comes verbatim from GitHub, so one carrying `..`
    would otherwise be written outside the folder the caller named. Both
    sides are resolved, so a symlinked folder compares as what it points at.
    """
    try:
        return target.resolve().is_relative_to(folder.resolve())
    except OSError:
        return False


def _blobs_in(listing: dict) -> dict[str, str]:
    return {
        entry["path"]: entry.get("sha", "")
        for entry in listing.get("tree", [])
        if entry.get("type") == "blob" and entry.get("path")
    }


def _is_link(path: Path) -> bool:
    """A symlink, or on Windows a directory junction, which is_symlink() does
    not see and is_dir() follows (PRESS-0135)."""
    return path.is_symlink() or path.is_junction()


def _entries(folder: Path, untouchable: tuple[str, ...]) -> list[Path]:
    """Every path under `folder` that the untouchable list does not name,
    sorted, never descending into a link: rglob walks into a junction before
    anything could refuse it (§4.4, PRESS-0135). A folder that cannot be read
    is a file that cannot be read (§6)."""
    found: list[Path] = []
    pending = [folder]
    while pending:
        here = pending.pop()
        try:
            children = list(here.iterdir())
        except OSError as exc:
            if here == folder:
                raise PublishError(
                    f"the site folder could not be read: {os_reason.of(exc)}") from exc
            raise _unreadable(here.relative_to(folder).as_posix(), exc) from exc
        for path in children:
            relative = path.relative_to(folder).as_posix()
            if _is_protected(relative, untouchable):
                continue
            found.append(path)
            try:
                descend = not _is_link(path) and path.is_dir()
            except OSError as exc:
                raise _unreadable(relative, exc) from exc
            if descend:
                pending.append(path)
    return sorted(found)



def _refuse_if_stray(relative: str, path: Path) -> None:
    """§4.4: the site folder is Pressless's alone, so a stray refuses.

    Refusing is not skipping. A skip publishes a correct site and says
    nothing, so the stray stays and nobody learns of it; making it visible is
    why this branch was chosen over a filter (PRESS-0089).

    The caller has already established this path is not under an untouchable
    first segment -- those are not Pressless's to refuse over either.
    """
    if _is_link(path):
        # Classified BEFORE it is followed. is_dir() and is_file() both
        # follow the link, so a symlinked directory would otherwise be
        # descended into and its target published to a public site (§4.4).
        raise StrayFile(
            f"{relative} in the site folder is a link, which the Builder "
            f"does not produce -- the folder is Pressless's alone, so the "
            f"publish is refused rather than sending it"
        )
    if not (path.is_file() or path.is_dir()):
        raise StrayFile(
            f"{relative} in the site folder is neither an ordinary file nor "
            f"a directory, so the Builder did not produce it and the publish "
            f"is refused rather than sending it"
        )
    dotted = next(
        (part for part in relative.split("/") if part.startswith(".")), None
    )
    if dotted is not None:
        raise StrayFile(
            f"{relative} in the site folder carries {dotted}, which is "
            f"machine state rather than site output -- the publish is "
            f"refused rather than sending it"
        )


@dataclass(frozen=True)
class _Local:
    """A file in the site folder: where it is, and its git blob hash when
    the folder was read. Only the hash is kept, so a publish holds one
    file's bytes at a time however large the site (PRESS-0088)."""

    path: Path
    sha: str
    size: int = 0                     # bytes when read, for PRESS-0435's count


def _unreadable(relative: str, exc: OSError) -> PublishError:
    """A file the writer cannot read is still a file in the site folder;
    the bare OSError was neither of §4.1's types (PRESS-0073)."""
    return PublishError(
        f"{relative} is in the site folder but could not be read: {os_reason.of(exc)}")


def _hash_file(relative: str, path: Path) -> tuple[str, int]:
    """`path`'s git blob hash, as blob_hash gives it, read a mebibyte at a
    time, and its length. A file whose length moved during the read has
    changed."""
    try:
        with path.open("rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            digest = hashlib.sha1(b"blob %d\0" % size, usedforsecurity=False)
            read = 0
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                read += len(chunk)
    except OSError as exc:
        raise _unreadable(relative, exc) from exc
    if read != size:
        raise _changed(relative)
    return digest.hexdigest(), size


def _changed(relative: str) -> PublishError:
    return PublishError(
        f"{relative} changed while it was being published, so the site was "
        f"left as it was"
    )


def _read_again(relative: str, local: _Local) -> bytes:
    """`local`'s bytes, refused unless they are still what was compared:
    sent unchecked, a file changed meanwhile would go up under a
    comparison made of other bytes (PRESS-0088)."""
    try:
        data = local.path.read_bytes()
    except OSError as exc:
        raise _unreadable(relative, exc) from exc
    if blob_hash(data) != local.sha:
        raise _changed(relative)
    return data


def _local_files(folder: Path, untouchable: tuple[str, ...]) -> dict[str, _Local]:
    """Every file under `folder`, keyed by repository-relative path.

    A stray refuses the publish rather than being skipped or sent (§4.4,
    INV-10). Nothing on the untouchable list is judged or read: an entry there
    is neither written nor removed whatever the folder holds, so refusing
    over one, or failing to read one, would fail a publish on a file already
    decided to be left alone. That also leaves a protected symlink unfollowed
    (PRESS-0069).
    """
    files = {}
    found = _entries(folder, untouchable)
    # Every byte is read, so a large site counts (PRESS-0464).
    total = sum(1 for path in found if path.is_file())
    progress.count("progress.checking", 0, total)
    for path in found:
        relative = path.relative_to(folder).as_posix()
        try:
            _refuse_if_stray(relative, path)
            if not path.is_file():
                continue    # a directory carries no bytes of its own
        except OSError as exc:
            raise _unreadable(relative, exc) from exc
        files[relative] = _Local(path, *_hash_file(relative, path))
        progress.count("progress.checking", len(files), total)
    return files


def _is_protected(path: str, untouchable: tuple[str, ...]) -> bool:
    """Whether `path`'s FIRST segment is on the untouchable list (§4.4).

    An entry naming a directory therefore protects everything beneath it,
    and one naming a file matches only that file. Comparing whole paths for
    equality would leave every file inside an untouchable directory
    unprotected, which is the failure the list exists to prevent.

    A trailing slash on an entry is ignored rather than trusted to be
    absent, for two reasons that each suffice. `load` does not normalise it:
    executed, it stores `CNAME/` verbatim, and PRESS-0009 §4.4 says so.
    And a settings file written by hand reaches here without passing `load`
    at all. An entry that silently protects nothing is the one failure this
    list cannot afford (PRESS-0044).

    The comparison folds case, and with `str.casefold` rather than
    `str.lower` because §4.4 pins the operation by name: the two differ on
    non-ASCII names, and PRESS-0021's derivation of the list has to agree
    with this one, so both fold through `settings.root_key`. GitHub's paths
    are case-sensitive and the Windows and
    macOS local filesystems are not, so a stored entry and a live path can
    differ only in case and still be one address. Compared exactly it
    breaks in both directions and only one of them deletes: an entry the
    REMOTE path's first segment cannot match leaves that path unprotected,
    so it is removed -- which for CNAME takes the domain off the site. An
    entry the LOCAL path's cannot match uploads a second file claiming the
    same address and removes nothing (PRESS-0078).
    """
    first = root_key(path.split("/", 1)[0])
    return any(first == root_key(entry) for entry in untouchable)


# §4.5's Windows check. Its device names are the Store's, by
# safe_write.windows_device. The backslash is forbidden here because a fetched
# path segment has had no other check.
_ON_WINDOWS = os.name == "nt"
_WINDOWS_FORBIDDEN = set('<>:"|?*\\') | {chr(n) for n in range(32)}
# MAX_PATH less the 12 characters Windows keeps for a name inside a folder:
# with long paths off, a fetched path this long or longer fails as an OSError.
_WINDOWS_LONGEST = 260 - 12


def _refuse_what_windows_cannot_hold(listing: dict, prefixes: tuple[str, ...]) -> None:
    """Refuse, before any blob is read, a selected path equal once case is
    ignored to another or to a folder above one, or naming a segment Windows
    cannot hold -- all used to end as FetchNotWritten, whose answer is to
    free space (PRESS-0160)."""
    files: set[str] = set()
    folders: set[str] = set()
    for entry in listing.get("tree", []):
        path = entry.get("path")
        if (not path or entry.get("type") != "blob"
                or not any(_within_prefix(path, prefix) for prefix in prefixes)):
            continue
        folded = path.casefold().split("/")
        above = {"/".join(folded[:n]) for n in range(1, len(folded))}
        whole = "/".join(folded)
        if (whole in files or whole in folders or above & files
                or not all(map(_windows_can_hold, path.split("/")))):
            raise UnfetchablePath(
                f"the fetched state names {path!r}, which this computer "
                f"cannot hold"
            )
        files.add(whole)
        folders |= above


def _windows_can_hold(segment: str) -> bool:
    if not segment or segment[-1] in ". " or _WINDOWS_FORBIDDEN & set(segment):
        return False
    return not safe_write.windows_device(segment)


def _within_prefix(path: str, prefix: str) -> bool:
    """Whether `path` is selected by `prefix` (§4.5).

    Matched on path-segment boundaries, with a trailing slash optional and
    ignored. Matched as a bare string instead, "content" would also select
    "contents.html".

    §4.4's untouchable rule tolerates a trailing slash too. Where the two
    differ is depth: a prefix may name a path several segments deep, an
    untouchable entry may not, and `load` refuses one that does.
    """
    prefix = prefix.rstrip("/")
    if not prefix:
        # After the strip, not before it: "/" is a prefix selecting the whole
        # site, and testing emptiness first made it select nothing instead
        # (PRESS-0069).
        return True
    return path == prefix or path.startswith(f"{prefix}/")


def _content_of(blob: dict) -> bytes:
    """A blob's bytes.

    An ABSENT content field is a failure, never an empty file: writing one
    silently would put a truncated version of the writer's own site on disk
    and report success. An empty STRING is a genuinely empty file and is
    kept, which is why the test is membership rather than truthiness.
    """
    if "content" not in blob:
        raise PublishError("GitHub's answer does not carry the file's content")
    content = blob["content"]
    try:
        if blob.get("encoding", "base64") == "base64":
            # GitHub breaks its base64 into lines. Unvalidated, a blob of
            # non-alphabet junk decodes to b"" (PRESS-0129).
            return base64.b64decode("".join(content.split()), validate=True)
        return content.encode("utf-8")
    except (ValueError, TypeError, AttributeError) as exc:
        # Malformed base64, or a content field that is not a string. The bare
        # binascii.Error, TypeError or AttributeError was none of §4.1's types
        # (PRESS-0095).
        raise PublishError(
            f"GitHub's answer carries content that cannot be read: {exc}"
        ) from exc


class _Hint(NamedTuple):
    seconds: float
    reset: bool = False     # the spent hourly allowance's own reset (PRESS-0471)


def _retry_hint(status: int, headers: dict[str, str], body: bytes = b"") -> _Hint | None:
    """The wait GitHub asked for, or None where it asked for none.

    A breach of the write pace is answered with a hint rather than a plain
    refusal (§4.3), so it is honoured rather than raised. GitHub sends it
    three ways. A SECONDARY limit answers 429, or 403 carrying a Retry-After,
    or a 403 whose message names the rate limit and carries no header at all,
    which GitHub asks to be waited out for at least a minute. The PRIMARY
    limit sends no Retry-After -- it reports a spent budget as
    x-ratelimit-remaining: 0 and names the reset in x-ratelimit-reset, so
    reading only Retry-After made it fall through to Refused and tell the
    writer to re-enter a key that is fine (PRESS-0046).

    A 403 carrying none of the three is an ordinary refusal and must not be
    retried.
    """
    header = {key.lower(): value for key, value in headers.items()}
    after = header.get("retry-after")
    spent = str(header.get("x-ratelimit-remaining", "")).strip() == "0"
    if status != 429 and not (status == 403 and (
            after is not None or spent or "rate limit" in _message(body).casefold())):
        return None
    if after is not None:
        try:
            return _Hint(max(float(after), 0.0))
        except (TypeError, ValueError):
            return _Hint(RATE_LIMIT_SECONDS)
    if spent:
        # An absolute epoch second, so the wait is what is left of it. A reset
        # that reads as past while GitHub still says the budget is spent means
        # the two clocks disagree, which names no usable interval -- a wait of
        # 0 doubled stays 0, and every retry would go out against the spent
        # budget (PRESS-0162).
        try:
            left = float(header["x-ratelimit-reset"]) - time.time()
        except (KeyError, TypeError, ValueError):
            return _Hint(RATE_LIMIT_SECONDS)
        return _Hint(left, reset=True) if left > 0 else _Hint(RATE_LIMIT_SECONDS)
    return _Hint(RATE_LIMIT_SECONDS)


def _names_the_repository(url: str) -> bool:
    """Whether `url` is the repository itself rather than something in it.

    `_repo_url` builds every URL here, so the repository root is exactly
    `/repos/{owner}/{name}` and anything inside it is longer.
    """
    return len(urllib.parse.urlsplit(url).path.strip("/").split("/")) == 3


def _failure(status: int, method: str, url: str, *, signed_in: bool = False) -> PublishError:
    """The typed failure for an HTTP status (§6). Never carries the key.

    `signed_in` when the key is a sign-in's pass, whose refusal is answered by
    signing in again rather than by entering a key (PRESS-0233).
    """
    where = f"{method} {_without_account(url)}"
    if status in (401, 403):
        if signed_in:
            return SignInRefused(f"GitHub refused the sign-in for {where}")
        return Refused(f"GitHub refused the publishing key for {where}")
    if status == 404:
        if _names_the_repository(url):
            return RepositoryMissing(f"GitHub has nothing at {where}")
        # The repository answered; something asked for INSIDE it is absent --
        # a deleted branch, a sha that is not there. Reporting that as
        # `settings.repository resolves to nothing`, which is what this type
        # means in §6, sends the writer to check a setting that is correct
        # (PRESS-0069).
        return RemoteStateMissing(
            f"GitHub has no {where} -- the repository is there, but what was "
            f"asked for inside it is not"
        )
    if status in (409, 422) and method != "POST" and not _names_pages(url):
        # Only the reference update, a Contents API write (the start file,
        # `.nojekyll`, `CNAME`) and a read concern the branch. A POST writes a
        # blob, tree, commit or Pages build, and a PUT to `pages` changes a
        # setting; none touches the branch, so their refusal falls to the
        # base type below (§6, PRESS-0135).
        return Conflict(
            f"the branch moved since it was read, so {where} was refused"
        )
    if status == 413:
        return TooLarge(f"GitHub refused {where} as too large")
    return PublishError(f"GitHub answered {status} for {where}")


def _names_pages(url: str) -> bool:
    """Whether `url` is the repository's GitHub Pages setting."""
    return urllib.parse.urlsplit(url).path.rstrip("/").endswith("/pages")


def _says_empty(data: bytes) -> bool:
    """Whether an error answer's `message` names an empty repository."""
    return "empty" in _message(data).casefold()


def _message(data: bytes) -> str:
    """An answer's `message`, or "" where it carries none."""
    try:
        parsed = json.loads(data or b"{}")
    except ValueError:
        return ""
    message = parsed.get("message") if isinstance(parsed, dict) else None
    return message if isinstance(message, str) else ""


def _parse(data: bytes) -> dict:
    try:
        parsed = json.loads(data or b"{}")
    except ValueError as exc:
        raise PublishError(f"GitHub's answer is not valid JSON: {exc}") from exc
    return parsed if isinstance(parsed, dict) else {}


def _required(mapping: dict, key: str, what: str):
    value = mapping.get(key)
    if not value:
        raise PublishError(f"GitHub's answer does not name {what}")
    return value
