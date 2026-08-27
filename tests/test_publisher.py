# INV-1..9 for PRESS-0009 (Publisher). One test per invariant, named in that
# spec's §5 and tabulated in §10. No test reaches the network (spec §7):
# every test hands in a recording double through the `transport` argument,
# which is what lets INV-3, INV-5 and INV-9 assert on request order,
# absence and spacing.
#
# Why this exists: docs/specs/PRESS-0009-publisher.md is the contract.
#
# INV-1 passes against the stub, by design (spec §7) -- it is evidence
# about imports, never about where the key came from. Every other
# invariant needs the real implementation; against the stub each one fails
# where it calls publish(), root_entries() or fetch_previous(), because the
# stub raises NotImplementedError unconditionally. That failure is expected
# and is the point of this run (PRESS-0009 is not yet implemented).
from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

import pytest

import pressless.publisher as publisher_module
from pressless.publisher import (
    Conflict,
    Fetched,
    NoPreviousState,
    Outcome,
    OutcomeUnknown,
    RateLimited,
    Refused,
    RepositoryMissing,
    TooLarge,
    Unreachable,
    fetch_previous,
    publish,
)
from pressless.settings import Credentials, Settings

# A value no real publishing key would be. INV-7 asserts it reaches no
# failure's str() or repr().
SENTINEL = "sentinel-key-must-not-appear-in-any-message"


def _settings(**overrides) -> Settings:
    """A Settings whose fields tests don't care about are filled with
    neutral placeholders. Never a real repository, account or path."""
    values = {
        "site_folder": Path("/writer/Pressless/site"),
        "repository": "owner/name",
        "daily_prompt_filter": "dailyprompt-*",
        "untouchable": ("CNAME", ".nojekyll", "vendor"),
        "credentials": Credentials(
            store="keyring", github_account="publishing-key", google_account=None
        ),
        "analytics_property_id": None,
    }
    values.update(overrides)
    return Settings(**values)


def _blob_hash(data: bytes) -> str:
    """§4.2's measured formula: sha1(b"blob " + len + b"\\0" + data). Written
    out here rather than imported, so a change to the module's own hashing
    cannot silently validate itself (the same reasoning CLAUDE.md gives for
    FILE_NAME in test_credentials.py)."""
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _listing(entries: list[tuple[str, str]], truncated: bool = False) -> bytes:
    """A recursive tree listing shaped like GitHub's own API (§4.2): each
    entry is a path and its git blob hash; `truncated` is the flag INV-6
    reads."""
    return json.dumps(
        {
            "sha": "base-tree-sha",
            "truncated": truncated,
            "tree": [
                {"path": path, "type": "blob", "sha": sha} for path, sha in entries
            ],
        }
    ).encode("utf-8")


def _is_write(method: str) -> bool:
    """Any non-GET request -- a write, in §4.3's sense."""
    return method != "GET"


def _is_tree_write(method: str, url: str) -> bool:
    """The tree-CREATION write (§4.3 step 2). Matched on METHOD AND URL
    together, never URL alone: §4.2's read of the repository state is
    itself a GET to a tree-LISTING endpoint that can share a URL stem
    with this POST -- only the method tells the two apart."""
    return _is_write(method) and "/git/trees" in url


def _is_reference_update(method: str, url: str) -> bool:
    """The reference-update write (§4.3 step 4), matched the same way as
    _is_tree_write -- method and URL together."""
    return _is_write(method) and "/git/refs" in url


class _Transport:
    """A recording double for §4.1's Transport protocol.

    Every call is recorded, in call order, in `.requests` as
    (method, url, body, headers) -- what INV-2, INV-3, INV-5 and INV-7
    read.

    `responses` is a positional fallback, answered by call index and
    repeating its last entry -- correct wherever a fixture needs only ONE
    fixed answer (most reads, and any write whose content nothing checks),
    and safe against an unanticipated extra read: §4.2 resolves the
    default branch "once per call", almost certainly its own GET, and a
    single-entry `responses` list answers that call exactly as it answers
    every other one, whatever position it falls in.

    `writes` answers a non-GET request by URL substring instead, checked
    before `responses` and independent of call position -- for a fixture
    that must hand back a DIFFERENT body per write step (one blob
    response, the tree, the commit, the reference update) regardless of
    how many reads preceded them. Each entry is (url_substring, response);
    the first substring contained in the URL wins. Never answers a GET:
    §4.2's read of the repository state can share a URL stem with a write
    endpoint (a tree LISTING is GET .../git/trees/{sha}, a tree CREATION
    is POST .../git/trees), so `writes` is gated on method as well as on
    the substring.

    `fail_at` names the request that raises `OSError` instead of
    answering -- §4.1's "no answer at all" signal, never a status code. A
    string matches the first request whose URL contains it AND whose
    method agrees with `fail_on_read` (a write by default; a read when
    `fail_on_read=True`) -- the same method-plus-URL pairing `writes`
    uses, for the same reason.

    `rate_limited_writes` answers that many non-GET requests with a
    429-shaped rate-limit hint before falling through to `writes` /
    `responses`; `-1` means every write is rate-limited (INV-9's
    exhausted-bound case). Reads are never rate-limited, matching §4.3's
    "writes are paced".

    `.waits` records every `wait(seconds)` call, in order -- INV-9 reads
    it for pacing.
    """

    def __init__(
        self,
        responses: list[tuple[int, dict[str, str], bytes]] | None = None,
        writes: list[tuple[str, tuple[int, dict[str, str], bytes]]] | None = None,
        fail_at: str | None = None,
        fail_on_read: bool = False,
        rate_limited_writes: int = 0,
    ) -> None:
        self.requests: list[tuple[str, str, bytes | None, dict[str, str]]] = []
        self.waits: list[float] = []
        self._responses = list(responses) if responses is not None else [
            (200, {}, b"{}")
        ]
        self._writes = list(writes) if writes is not None else []
        self._fail_at = fail_at
        self._fail_on_read = fail_on_read
        self._rate_limited_writes = rate_limited_writes
        self._rate_limit_hits = 0
        self._failed = False

    def request(
        self, method: str, url: str, body: bytes | None, headers: dict[str, str]
    ) -> tuple[int, dict[str, str], bytes]:
        index = len(self.requests)
        self.requests.append((method, url, body, headers))
        if self._should_fail(method, url):
            self._failed = True
            raise OSError("no answer from GitHub")
        if _is_write(method) and (
            self._rate_limited_writes < 0
            or self._rate_limit_hits < self._rate_limited_writes
        ):
            self._rate_limit_hits += 1
            return (429, {"Retry-After": "1"}, b'{"message": "rate limited"}')
        if _is_write(method):
            for substring, response in self._writes:
                if substring in url:
                    return response
        return self._responses[min(index, len(self._responses) - 1)]

    def _should_fail(self, method: str, url: str) -> bool:
        if self._fail_at is None or self._failed:
            return False
        matches_kind = _is_write(method) != self._fail_on_read
        return matches_kind and self._fail_at in url

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)


# --------------------------------------------------------------- INV-1 ----


def test_publisher_imports_no_forbidden_sibling():
    """INV-1: publisher.py imports no pressless module other than
    pressless.settings.

    Walks the module's AST, as test_settings_imports_nothing_forbidden
    does.

    Breaks when an implementer imports pressless.credentials to fetch the
    key rather than taking it as an argument, which is the breach of
    docs/design.md rule 10 that spec §5 was written to catch.

    Weak in the way the spec names (§5): an import walk passes against a
    module that does nothing. It is evidence about imports and never
    about where the key came from -- and it passes against the stub by
    design.
    """
    tree = ast.parse(inspect.getsource(publisher_module))

    pressless_imports = set()
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "pressless":
                    pressless_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_imports.append(node)
            elif node.module and node.module.split(".")[0] == "pressless":
                if node.module == "pressless":
                    for alias in node.names:
                        pressless_imports.add(f"pressless.{alias.name}")
                else:
                    pressless_imports.add(node.module)

    forbidden = pressless_imports - {"pressless.settings"}
    assert not forbidden, (
        f"publisher.py imports {sorted(forbidden)!r}, not just "
        f"pressless.settings -- this is the breach of docs/design.md "
        f"rule 10 that INV-1 exists to catch: fetching the key via "
        f"pressless.credentials rather than taking it as an argument"
    )
    assert not relative_imports, (
        f"publisher.py has relative import(s) "
        f"{[n.module for n in relative_imports]!r}, which can only name a "
        f"sibling pressless module"
    )


# --------------------------------------------------------------- INV-2 ----


def _tree_creation_paths(transport: _Transport) -> set[str] | None:
    """The set of paths named in the tree-CREATION request's body (§4.3
    step 2, a POST), parsed as JSON rather than scanned as bytes -- a
    blob is base64-encoded (§4.3) and a tree could legitimately carry
    escaped JSON, so a raw substring match on the path can miss a real
    breach and can also flag an innocent one (a commit message that
    happens to mention a protected name). Returns None if no such request
    was made at all."""
    for method, url, body, _ in transport.requests:
        if _is_tree_write(method, url):
            payload = json.loads(body or b"{}")
            return {entry["path"] for entry in payload.get("tree", [])}
    return None


def test_untouchable_is_neither_written_nor_removed(tmp_path):
    """INV-2: an entry on settings.untouchable is neither written nor
    removed, matched against a path's first segment.

    Three fixtures, per §5: the folder holds a *differing* file at an
    untouchable path (CNAME); the folder holds nothing at another
    untouchable path the repository has (.nojekyll); and the repository
    holds files beneath an untouchable *directory* (vendor/lib.js), which
    only first-segment matching protects.

    Breaks when an implementer applies the list to deletions only, which
    reads as protection and leaves the entry overwritable. Only this rule
    can reject the write fixture: every other rule in §4.4 makes a
    differing file an ordinary upload.
    """
    (tmp_path / "CNAME").write_text("writer.example.test\n", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html>site</html>", encoding="utf-8")

    listing = _listing(
        [
            ("CNAME", _blob_hash(b"a different value entirely\n")),
            (".nojekyll", _blob_hash(b"")),
            ("vendor/lib.js", _blob_hash(b"// vendor library\n")),
        ]
    )
    transport = _Transport(responses=[(200, {}, listing)])
    settings = _settings(untouchable=("CNAME", ".nojekyll", "vendor"))

    publish(settings, tmp_path, "a-token", "a commit message", transport=transport)

    paths = _tree_creation_paths(transport)
    assert paths is not None, (
        "no tree-creation request (a non-GET to a /git/trees-shaped URL) "
        "was made; INV-2 cannot be checked against a publish that built "
        "no tree at all"
    )
    breached = {
        path for path in paths if path.split("/", 1)[0] in settings.untouchable
    }
    assert not breached, (
        f"the tree-creation request names untouchable path(s) {breached!r}: "
        f"{sorted(paths)!r}"
    )


# --------------------------------------------------------------- INV-3 ----


def test_reference_update_is_last(tmp_path):
    """INV-3: no request that changes the branch is made until every blob,
    the tree and the commit have succeeded. The reference update is the
    last write of a publish; a transport failure at an earlier write
    raises Unreachable and makes no reference request at all, and one
    failing on the reference request itself raises OutcomeUnknown.

    Chose the URL-naming form over the endpoint-free alternative: the
    reference update is the one non-GET request whose URL contains
    "/git/refs" (GitHub's own endpoint name, which §4.2/§4.3 build on),
    matched on METHOD AND URL TOGETHER -- never URL alone, because §4.2's
    read of the repository state is itself a GET that can share a URL
    stem with a write endpoint. No total request COUNT or ordinal
    position is asserted anywhere in this test, so an implementation that
    resolves the default branch with its own extra read (§4.2: "once per
    call") cannot break it.

    Breaks when an implementer updates the branch per batch to make a
    large first publish resumable, which is the change that turns a
    half-finished publish into a half-updated site (§8).
    """
    (tmp_path / "index.html").write_text("<html>new</html>", encoding="utf-8")
    listing = _listing([("index.html", _blob_hash(b"<html>old</html>"))])
    settings = _settings()

    def _reference_updates(transport):
        return [
            (m, u) for m, u, _, _ in transport.requests if _is_reference_update(m, u)
        ]

    # Failing at the commit write: Unreachable, and no reference request
    # is ever made.
    failing_at_commit = _Transport(
        responses=[(200, {}, listing)], fail_at="/git/commits"
    )
    with pytest.raises(Unreachable):
        publish(settings, tmp_path, "a-token", "message", transport=failing_at_commit)
    assert not _reference_updates(failing_at_commit), (
        f"a reference request was made after the commit write failed: "
        f"{failing_at_commit.requests!r}"
    )

    # Failing at the reference update itself: OutcomeUnknown, never
    # Unreachable -- the outcome is genuinely unknown.
    failing_at_ref = _Transport(responses=[(200, {}, listing)], fail_at="/git/refs")
    with pytest.raises(OutcomeUnknown):
        publish(settings, tmp_path, "a-token", "message", transport=failing_at_ref)

    # A clean publish: exactly one reference update -- never per batch,
    # §8 -- and it is the LAST request recorded. Since it is both unique
    # and last, every blob, tree and commit request necessarily precedes
    # it; no separate assertion is needed for that half.
    clean = _Transport(responses=[(200, {}, listing)])
    publish(settings, tmp_path, "a-token", "message", transport=clean)
    reference_updates = _reference_updates(clean)
    assert len(reference_updates) == 1, (
        f"expected exactly one reference update; got {reference_updates!r}"
    )
    last_method, last_url, _, _ = clean.requests[-1]
    assert _is_reference_update(last_method, last_url), (
        f"the last request was not the reference update: "
        f"{clean.requests[-1]!r}"
    )


# --------------------------------------------------------------- INV-4 ----


def test_unchanged_files_are_not_uploaded(tmp_path):
    """INV-4: a file whose local git blob hash equals the hash in the
    repository listing is not uploaded, and a publish where nothing
    differs writes no commit and returns an empty Outcome.commit.

    Asserts on WRITE requests only, never a total count: §4.2 resolves
    the default branch with its own read, so the number of GETs a clean
    no-op publish makes is not this invariant's business.

    Breaks when an implementer compares modification time or size, either
    of which reports a rewritten-but-identical file as changed -- which is
    exactly what the Builder produces on every run.
    """
    content = b"<html>unchanged</html>"
    (tmp_path / "index.html").write_bytes(content)
    listing = _listing([("index.html", _blob_hash(content))])
    transport = _Transport(responses=[(200, {}, listing)])
    settings = _settings()

    outcome = publish(settings, tmp_path, "a-token", "message", transport=transport)

    writes = [(m, u) for m, u, _, _ in transport.requests if _is_write(m)]
    assert not writes, (
        f"a publish where nothing differs made write request(s): {writes!r}"
    )
    assert isinstance(outcome, Outcome) and outcome.commit == "", (
        f"a publish where nothing differs returned commit "
        f"{getattr(outcome, 'commit', outcome)!r}, not an empty sha"
    )


# --------------------------------------------------------------- INV-5 ----


def test_branch_that_moved_is_a_conflict(tmp_path):
    """INV-5: the reference update is never forced, and a branch that
    moved since the listing was read raises Conflict rather than
    overwriting.

    Asserting the TYPE is what makes it bite (§5): an unreachable network
    also produces no successful update, so a clause asserting only that
    something was raised passes against an implementation reporting a
    conflict as a network fault.

    The refusal is answered by URL, not by call position: an extra
    leading read (§4.2's branch resolution) cannot shift which response
    lands on which write step.
    """
    (tmp_path / "index.html").write_text("<html>new</html>", encoding="utf-8")
    listing = _listing([("index.html", _blob_hash(b"<html>old</html>"))])
    # GitHub answers a non-fast-forward reference update with a refusal
    # status, never by dropping the connection (§4.1: every HTTP status is
    # returned, never raised).
    transport = _Transport(
        responses=[(200, {}, listing)],
        writes=[("/git/refs", (409, {}, b'{"message": "not a fast forward"}'))],
    )
    settings = _settings()

    with pytest.raises(Conflict):
        publish(settings, tmp_path, "a-token", "message", transport=transport)

    forced = [
        body
        for _, _, body, _ in transport.requests
        if body and b'"force": true' in body.replace(b" ", b"")
    ]
    assert not forced, f"a request body sets force: {forced!r}"


# --------------------------------------------------------------- INV-6 ----


def test_truncated_listing_is_refused(tmp_path):
    """INV-6: a listing GitHub flags as cut short raises TooLarge and is
    never used to compute what differs.

    Asserts on WRITE requests only, never a total count or a "requests
    after index 0" slice: an extra leading read that precedes the
    truncated listing itself must not make this test look like something
    followed it.

    Breaks when an implementer reads the entries and ignores the flag,
    which makes every unlisted path look new and every deletion
    invisible.
    """
    (tmp_path / "index.html").write_text("<html>site</html>", encoding="utf-8")
    truncated = _listing([], truncated=True)
    transport = _Transport(responses=[(200, {}, truncated)])
    settings = _settings()

    with pytest.raises(TooLarge):
        publish(settings, tmp_path, "a-token", "message", transport=transport)

    writes = [(m, u) for m, u, _, _ in transport.requests if _is_write(m)]
    assert not writes, f"a write request followed the truncated listing: {writes!r}"


# --------------------------------------------------------------- INV-7 ----


def test_no_failure_names_the_key(tmp_path):
    """INV-7: no failure raised by this module carries the key, in its
    message or its representation.

    Forces every failure type this module can raise, with SENTINEL as the
    key each attempt is made with; asserts SENTINEL appears in neither
    str() nor repr() of what is raised.

    Breaks when an implementer includes the request headers in an error
    to make a failure diagnosable, and the key is a header.
    """
    (tmp_path / "index.html").write_text("<html>site</html>", encoding="utf-8")
    listing = _listing([("index.html", _blob_hash(b"<html>old</html>"))])
    truncated = _listing([], truncated=True)
    settings = _settings()
    messages: list[tuple[str, str]] = []

    def collect(kind, invoke):
        with pytest.raises(kind) as caught:
            invoke()
        messages.append((str(caught.value), repr(caught.value)))

    # Unreachable -- no answer at the first read, before the branch was
    # touched. fail_on_read=True with an empty substring matches whatever
    # the first read turns out to be, however many precede the listing.
    collect(
        Unreachable,
        lambda: publish(
            settings,
            tmp_path,
            SENTINEL,
            "message",
            transport=_Transport(fail_at="", fail_on_read=True),
        ),
    )

    # OutcomeUnknown -- no answer on the reference update itself.
    collect(
        OutcomeUnknown,
        lambda: publish(
            settings,
            tmp_path,
            SENTINEL,
            "message",
            transport=_Transport(
                responses=[(200, {}, listing)], fail_at="/git/refs"
            ),
        ),
    )

    # Refused -- the key is rejected (GitHub's conventional 401).
    collect(
        Refused,
        lambda: publish(
            settings,
            tmp_path,
            SENTINEL,
            "message",
            transport=_Transport(
                responses=[(401, {}, b'{"message": "Bad credentials"}')]
            ),
        ),
    )

    # RepositoryMissing -- settings.repository resolves to nothing
    # (GitHub's conventional 404).
    collect(
        RepositoryMissing,
        lambda: publish(
            settings,
            tmp_path,
            SENTINEL,
            "message",
            transport=_Transport(responses=[(404, {}, b'{"message": "Not Found"}')]),
        ),
    )

    # Conflict -- the reference update is refused as a non-fast-forward,
    # answered by URL rather than position, as in test_branch_that_moved_
    # is_a_conflict.
    collect(
        Conflict,
        lambda: publish(
            settings,
            tmp_path,
            SENTINEL,
            "message",
            transport=_Transport(
                responses=[(200, {}, listing)],
                writes=[
                    ("/git/refs", (409, {}, b'{"message": "not a fast forward"}'))
                ],
            ),
        ),
    )

    # TooLarge -- a truncated listing.
    collect(
        TooLarge,
        lambda: publish(
            settings,
            tmp_path,
            SENTINEL,
            "message",
            transport=_Transport(responses=[(200, {}, truncated)]),
        ),
    )

    # RateLimited -- every write hint-limited, past the retry bound.
    collect(
        RateLimited,
        lambda: publish(
            settings,
            tmp_path,
            SENTINEL,
            "message",
            transport=_Transport(
                responses=[(200, {}, listing)], rate_limited_writes=-1
            ),
        ),
    )

    # NoPreviousState -- fetch_previous on a first commit.
    collect(
        NoPreviousState,
        lambda: fetch_previous(
            settings,
            SENTINEL,
            tmp_path,
            transport=_Transport(
                responses=[(200, {}, b'{"sha": "only-commit", "parents": []}')]
            ),
        ),
    )

    leaked = [(s, r) for s, r in messages if SENTINEL in s or SENTINEL in r]
    assert not leaked, f"a failure names the key: {leaked!r}"


# --------------------------------------------------------------- INV-8 ----


def test_fetch_previous_names_its_source(tmp_path):
    """INV-8: fetch_previous reads the current commit's first parent and
    names the sha it fetched.

    Breaks when an implementer resolves "previous" against the branch's
    second-newest commit by listing history, which differs from the first
    parent as soon as anything is merged.
    """
    commit_response = json.dumps(
        {
            "sha": "current-commit-sha",
            "parents": [{"sha": "parent-commit-sha"}, {"sha": "merged-in-sha"}],
        }
    ).encode("utf-8")
    tree_response = _listing([("index.html", "some-blob-sha")])
    transport = _Transport(
        responses=[(200, {}, commit_response), (200, {}, tree_response)]
    )
    settings = _settings()

    fetched = fetch_previous(settings, "a-token", tmp_path, transport=transport)

    assert isinstance(fetched, Fetched) and fetched.commit == "parent-commit-sha", (
        f"fetch_previous named {getattr(fetched, 'commit', fetched)!r} as its "
        f"source, not the FIRST parent 'parent-commit-sha' -- merging changes "
        f"which commit is second-newest but never which is the first parent"
    )


def test_first_commit_has_no_previous_state(tmp_path):
    """INV-8: fetch_previous raises NoPreviousState where the current
    commit has no parent.
    """
    commit_response = json.dumps(
        {"sha": "the-only-commit-sha", "parents": []}
    ).encode("utf-8")
    transport = _Transport(responses=[(200, {}, commit_response)])
    settings = _settings()

    with pytest.raises(NoPreviousState):
        fetch_previous(settings, "a-token", tmp_path, transport=transport)


# --------------------------------------------------------------- INV-9 ----


def test_writes_are_paced_and_hints_retried(tmp_path):
    """INV-9: successive write requests are separated by the pacing wait,
    and a retry hint is waited out and retried rather than raised --
    RateLimited is raised only once the retry bound is exhausted.

    Breaks when an implementer writes as fast as the loop allows, which
    passes every other test in this file and fails on a first publish
    against the real service.
    """
    (tmp_path / "index.html").write_text("<html>new</html>", encoding="utf-8")
    listing = _listing([("index.html", _blob_hash(b"<html>old</html>"))])
    settings = _settings()

    # A retry hint is waited out and retried: the publish still
    # completes. Each write step is answered by URL, not position, so an
    # extra leading read cannot shift which response lands on which step.
    retried_once = _Transport(
        responses=[(200, {}, listing)],
        writes=[
            ("/git/blobs", (201, {}, b'{"sha": "blob-sha"}')),
            ("/git/trees", (201, {}, b'{"sha": "tree-sha"}')),
            ("/git/commits", (201, {}, b'{"sha": "commit-sha"}')),
            ("/git/refs", (200, {}, b'{"object": {"sha": "commit-sha"}}')),
        ],
        rate_limited_writes=1,
    )
    outcome = publish(settings, tmp_path, "a-token", "message", transport=retried_once)
    assert isinstance(outcome, Outcome) and outcome.commit, (
        "a publish that hit one rate-limit hint and was retried did not "
        "complete"
    )
    assert retried_once.waits, (
        "no wait() call was recorded between a rate-limited write and its "
        "retry"
    )

    # Successive writes are paced even without a rate-limit hint. Counted
    # by method, never by position, so an extra leading read changes
    # nothing here either.
    paced = _Transport(responses=[(200, {}, listing)])
    publish(settings, tmp_path, "a-token", "message", transport=paced)
    write_count = sum(1 for method, *_ in paced.requests if _is_write(method))
    assert len(paced.waits) >= write_count - 1, (
        f"only {len(paced.waits)} wait() call(s) were recorded for "
        f"{write_count} write requests; successive writes must be paced"
    )

    # Retry hints exhausted: RateLimited, raised only once the bound gives
    # up, never on the first hint.
    always_limited = _Transport(
        responses=[(200, {}, listing)], rate_limited_writes=-1
    )
    with pytest.raises(RateLimited):
        publish(settings, tmp_path, "a-token", "message", transport=always_limited)
