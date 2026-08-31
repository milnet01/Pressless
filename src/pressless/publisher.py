"""Publisher — making GitHub match the folder it was handed.

The contract is docs/specs/PRESS-0009-publisher.md, an umbrella covering
PRESS-0009 and PRESS-0010. This module imports no other part of Pressless
than Settings (§5 INV-1): it is handed the publishing key as an argument and
never reaches Credentials, which is what keeps docs/design.md rule 10 true.

It answers three requests and nothing else — make the repository match this
folder, report what sits at the repository root, and fetch back the state
before the current one. It writes no prose for the writer, keeps no state
between calls, and cannot tell an entry from a stylesheet.

Every failure is one of the typed exceptions below, and none of them carries
the key (§5 INV-7). The Face turns each into the three-part sentence
docs/design.md § Errors requires; this module writes none of them.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pressless.settings import Settings

API = "https://api.github.com"

# GitHub asks for at least a second between successive write requests (§4.3).
# A breach is answered with a retry hint rather than a plain refusal, so the
# wait is honoured and the write retried; only an exhausted bound raises.
PACE_SECONDS = 1.0
MAX_RETRIES = 4

# Every blob is written with the ordinary file mode. §4.3 takes one rule for
# prose and photographs alike rather than two split by a property of the file.
BLOB_MODE = "100644"

# The tree entry that REMOVES a path: a null sha, per GitHub's tree API.
REMOVED = None


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
    """The reference update was attempted and its result is unknown."""


class Refused(PublishError):
    """Key rejected, or no write access."""


class RepositoryMissing(PublishError):
    """settings.repository resolves to nothing."""


class Conflict(PublishError):
    """The branch moved under us."""


class TooLarge(PublishError):
    """A documented GitHub limit was hit."""


class RateLimited(PublishError):
    """GitHub asked us to slow down, and retrying did not clear it."""


class NoPreviousState(PublishError):
    """Nothing before the current commit."""


class Transport(Protocol):
    """The one seam. Tests are its only other caller (§4.1).

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


class _Urllib:
    """The module's own client, used when no double is handed in.

    urllib.request rather than a third-party HTTP library (§3 decision 3):
    PRESS-0022 has to carry every dependency into a packaged artefact, and a
    convenience library here would be a third bought for syntax.
    """

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]
                ) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(url, data=body, headers=headers,
                                         method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return (response.status, dict(response.headers),
                        response.read())
        except urllib.error.HTTPError as error:
            # An error STATUS is an answer, so it is returned rather than
            # raised -- only a genuine absence of one reaches the caller as
            # OSError, which is what the seam promises.
            return (error.code, dict(error.headers or {}), error.read())

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
    """Make the repository match `folder`, in one commit.

    Four writes in the order §4.3 fixes, and only the last changes what a
    reader sees: blobs, one tree, one commit, one reference update. An
    interruption at any earlier point leaves the site exactly as it was.
    """
    session = _Session(transport or _Urllib(), token)
    branch = _default_branch(session, settings.repository)
    head = session.read(_repo_url(settings.repository, f"commits/{branch}"))
    base_commit = _required(head, "sha", "the head commit")
    listing = _tree(session, settings.repository, base_commit)
    remote = _blobs_in(listing)

    local = _local_files(Path(folder))
    untouchable = settings.untouchable

    uploaded: dict[str, bytes] = {}
    for path, data in sorted(local.items()):
        if _is_protected(path, untouchable):
            continue
        if remote.get(path) == blob_hash(data):
            continue
        uploaded[path] = data

    removed = sorted(
        path for path in remote
        if path not in local and not _is_protected(path, untouchable)
    )

    if not uploaded and not removed:
        # Nothing differed, so nothing is written at all (§5 INV-4).
        return Outcome(commit="", uploaded=(), removed=())

    entries = []
    for path, data in uploaded.items():
        sha = _required(
            session.write("POST", _repo_url(settings.repository, "git/blobs"),
                          {"content": base64.b64encode(data).decode("ascii"),
                           "encoding": "base64"}),
            "sha", "a blob",
        )
        entries.append({"path": path, "mode": BLOB_MODE, "type": "blob",
                        "sha": sha})
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
                  _repo_url(settings.repository, f"git/refs/heads/{branch}"),
                  {"sha": commit, "force": False},
                  outcome_unknown=True)

    return Outcome(commit=commit, uploaded=tuple(sorted(uploaded)),
                   removed=tuple(removed))


def root_entries(settings: Settings, token: str,
                 transport: Transport | None = None) -> tuple[str, ...]:
    """Every entry at the repository root, as bare names (§4.4).

    Files and directories alike, with no trailing slash, in the form
    settings.untouchable holds. It decides nothing and filters nothing --
    rule 5 leaves this module unable to tell a stylesheet from an entry, so
    it cannot know which of them the Builder produces. Setup and the Face
    remove those and store the rest.
    """
    session = _Session(transport or _Urllib(), token)
    head = session.read(_repo_url(settings.repository, "commits/HEAD"))
    listing = _tree(session, settings.repository,
                    _required(head, "sha", "the head commit"),
                    recursive=False)
    return tuple(sorted(
        entry["path"] for entry in listing.get("tree", []) if entry.get("path")
    ))


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
    """
    session = _Session(transport or _Urllib(), token)
    current = session.read(_repo_url(settings.repository, "commits/HEAD"))
    parents = current.get("parents") or []
    if not parents:
        raise NoPreviousState(
            "the current commit has no parent, so there is no state before it"
        )
    parent = _required(parents[0], "sha", "the first parent")

    listing = _tree(session, settings.repository, parent)
    written = []
    for entry in listing.get("tree", []):
        path = entry.get("path")
        if not path or entry.get("type") != "blob":
            continue
        if not _within_prefix(path, prefix):
            continue
        blob = session.read(
            _repo_url(settings.repository, f"git/blobs/{entry['sha']}")
        )
        target = Path(into) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_content_of(blob))
        written.append(path)

    return Fetched(commit=parent, paths=tuple(sorted(written)))


class _Session:
    """One call's worth of requests, with the pacing and retry §4.3 fixes.

    Holds the key for the length of a call and never puts it in a message.
    """

    def __init__(self, client: Transport, token: str) -> None:
        self._client = client
        self._token = token
        self._written = False

    def read(self, url: str) -> dict:
        return self._call("GET", url, None)

    def write(self, method: str, url: str, payload: dict, *,
              outcome_unknown: bool = False) -> dict:
        if self._written:
            self._client.wait(PACE_SECONDS)
        self._written = True
        return self._call(method, url, payload,
                          outcome_unknown=outcome_unknown)

    def _call(self, method: str, url: str, payload: dict | None, *,
              outcome_unknown: bool = False) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Pressless",
        }
        attempts = 0
        while True:
            try:
                status, response_headers, data = self._client.request(
                    method, url, body, headers
                )
            except OSError as exc:
                # The reference update is the one request whose failure
                # leaves the site's state genuinely unknown (§6).
                failure = OutcomeUnknown if outcome_unknown else Unreachable
                raise failure(f"no answer from GitHub for {method} {url}") from exc

            hint = _retry_hint(status, response_headers)
            if hint is not None:
                attempts += 1
                if attempts > MAX_RETRIES:
                    raise RateLimited(
                        f"GitHub asked us to wait on {method} {url} and was "
                        f"still asking after {MAX_RETRIES} retries"
                    )
                self._client.wait(hint)
                continue

            if status in (200, 201):
                return _parse(data)
            raise _failure(status, method, url)


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
    listing = session.read(_repo_url(repository, f"git/trees/{ref}{suffix}"))
    if listing.get("truncated"):
        raise TooLarge(
            "GitHub cut the repository listing short, so what differs cannot "
            "be worked out from it"
        )
    return listing


def _repo_url(repository: str, suffix: str) -> str:
    base = f"{API}/repos/{repository}"
    return f"{base}/{suffix}" if suffix else base


def _blobs_in(listing: dict) -> dict[str, str]:
    return {
        entry["path"]: entry.get("sha", "")
        for entry in listing.get("tree", [])
        if entry.get("type") == "blob" and entry.get("path")
    }


def _local_files(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, keyed by repository-relative path."""
    files = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = path.read_bytes()
    return files


def _is_protected(path: str, untouchable: tuple[str, ...]) -> bool:
    """Whether `path`'s FIRST segment is on the untouchable list (§4.4).

    An entry naming a directory therefore protects everything beneath it,
    and one naming a file matches only that file. Comparing whole paths for
    equality would leave every file inside an untouchable directory
    unprotected, which is the failure the list exists to prevent.
    """
    return path.split("/", 1)[0] in untouchable


def _within_prefix(path: str, prefix: str) -> bool:
    """Whether `path` is selected by `prefix` (§4.5).

    Matched on path-segment boundaries, with a trailing slash optional and
    ignored -- the same rule §4.4 gives the untouchable list. Matched as a
    bare string instead, "content" would also select "contents.html".
    """
    if not prefix:
        return True
    prefix = prefix.rstrip("/")
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
    if blob.get("encoding", "base64") == "base64":
        return base64.b64decode(content)
    return content.encode("utf-8")


def _retry_hint(status: int, headers: dict[str, str]) -> float | None:
    """The wait GitHub asked for, or None where it asked for none.

    A breach of the write pace is answered with a hint rather than a plain
    refusal (§4.3), so it is honoured rather than raised. GitHub sends it as
    429, and as 403 carrying a Retry-After -- a 403 without one is an
    ordinary refusal and must not be retried.
    """
    after = None
    for key, value in headers.items():
        if key.lower() == "retry-after":
            after = value
            break
    if status != 429 and not (status == 403 and after is not None):
        return None
    try:
        return max(float(after), 0.0) if after is not None else PACE_SECONDS
    except (TypeError, ValueError):
        return PACE_SECONDS


def _failure(status: int, method: str, url: str) -> PublishError:
    """The typed failure for an HTTP status (§6). Never carries the key."""
    where = f"{method} {url}"
    if status in (401, 403):
        return Refused(f"GitHub refused the publishing key for {where}")
    if status == 404:
        return RepositoryMissing(f"GitHub has nothing at {where}")
    if status in (409, 422):
        return Conflict(
            f"the branch moved since it was read, so {where} was refused"
        )
    if status == 413:
        return TooLarge(f"GitHub refused {where} as too large")
    return PublishError(f"GitHub answered {status} for {where}")


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
