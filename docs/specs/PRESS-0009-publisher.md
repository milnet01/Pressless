# PRESS-0009 — Publisher: making GitHub match the folder it was handed

**Status:** accepted (2026-08-26). Two cold-eyes loops, both folded in, nothing left unfixed — the run reached the spec cap of 2. **A cap on the violent side:** four of the last loop's seven findings landed on text the run itself wrote, three of them the one subject — the transport seam loop 1 introduced and loop 2 pinned on its remaining axes. Implementation is the better third reviewer and this document is routed there rather than to another gate. **One finding is surfaced rather than applied:** `docs/design.md` rule 5 permits the Publisher to read and names no write, while §4.5 has `fetch_previous` write a fetched state to disk. That is another document's gate.
**Kind:** implement.
**Source:** ROADMAP PRESS-0009 and PRESS-0010 (`docs/design.md` § The
parts, § What may depend on what rules 5, 7 and 10; ADR-0002).

**Covers:** PRESS-0009 and PRESS-0010, as one umbrella
(`spec-format.md` §2). PRESS-0010 is the fetch-back capability — §4.5 and
INV-8 — and it shares this module's transport, branch resolution, failure
types and test seam. Two specs would restate all four.

**Blocked by:** PRESS-0001 and PRESS-0002, both shipped.
**Blocker for:** the Face's publish sequence; PRESS-0015, the undo
sequence that uses fetch-back; PRESS-0014, via PRESS-0010.

*Layman:* the part that sends the finished site to GitHub without git
being installed, leaves alone the handful of files that are not ours,
and can fetch back the version before this one.

## 1. Goal

After this ships, one module answers three requests and nothing else:
*make the repository match this folder*, *what sits at the repository
root*, and *fetch back the state before the current one*.

It reads Settings and a folder of finished files. It is handed a
publishing key rather than fetching one. It writes no prose for the
writer, holds no state between calls, and cannot tell an entry from a
stylesheet.

## 2. Problem

ADR-0002 rules out shelling out to `git`, because that means the writer
installing and configuring git before he can publish — which is the
thing this project exists to remove. So publishing is HTTP against
GitHub's own interface, and every safety property git would have given
for free has to be built and checked here instead.
`docs/decisions/ADR-0002-publish-via-github-api.md` says so outright:
*"If Pressless computes the wrong set of changed files, nothing
downstream catches it"*.

Four things make this a contract rather than a helper.

1. **Three callers bind to the surface.** The Face's publish sequence,
   its undo sequence, and setup's derivation of the untouchable list all
   call this module, and rule 1 gives the Face the ordering. A surface
   that changes shape later changes all three.

2. **Deleting the wrong file is unrecoverable in a way a bad page is
   not.** `docs/design.md` says it in those terms: one root entry holds
   the custom domain and another proves the site's identity to a search
   engine, and losing either is silent and slow. The rule that protects
   them is *every root entry the Builder does not produce*, and the list
   Settings holds is that rule's derived form.

3. **Publishing is many writes that must read as one act.** S6 requires
   the writer never be left unsure whether his change went out. A
   sequence that can stop halfway with the site half-updated cannot
   deliver that, so where the sequence is interruptible has to be a
   decided property rather than an accident of the code.

4. **Undo is the highest-value safety feature in the app** — the design
   calls the header edit the highest-blast-radius act there is, and undo
   is the answer to it. What "the previous state" means is not obvious
   once undo itself publishes, and getting it wrong restores the very
   thing the writer rejected.

## 3. Scope decisions (agreed with the user)

1. **Undo goes plain one step back.** Decided by the user 2026-08-26,
   with the consequence stated in the question and accepted: because an
   undo is itself an ordinary publish, pressing undo twice returns the
   site to the version the first undo rejected. Two alternatives were
   offered and declined — skipping past previous undos, and disabling
   undo after one press. §8 records why they lost. **This is a decided
   behaviour, not a defect**, and §10 records that nothing catches it.

2. **The Publisher is handed its key, never fetches one.**
   `docs/design.md` rule 10, settled 2026-08-25. This is what keeps rule
   5 literally true and lets every test here run without a keyring.

3. **The transport is the standard library.** `urllib.request`, not a
   third-party HTTP library. § The stack names one runtime dependency
   plus the imaging library, and PRESS-0022 has to carry every
   dependency into a packaged artefact. A convenience library here would
   be a third, bought for syntax.

4. **Fetching back may be narrowed by a path prefix.** The undo sequence
   needs one directory of the fetched state, and fetching a whole site
   to recover it costs the writer a large download on a domestic
   connection. The prefix is an opaque string to this module, so rule 5
   holds: it still cannot tell an entry from a stylesheet.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/publisher.py

@dataclass(frozen=True)
class Outcome:
    commit: str                  # sha written; "" when nothing differed
    uploaded: tuple[str, ...]    # repository-relative paths written
    removed: tuple[str, ...]     # repository-relative paths deleted

@dataclass(frozen=True)
class Fetched:
    commit: str                  # the sha fetched from
    paths: tuple[str, ...]       # repository-relative paths written out

class PublishError(Exception): ...
class Unreachable(PublishError): ...       # no answer from GitHub, before the branch was touched
class OutcomeUnknown(PublishError): ...    # the reference update was attempted and its result is unknown
class Refused(PublishError): ...           # key rejected, or no write access
class RepositoryMissing(PublishError): ... # settings.repository resolves to nothing
class Conflict(PublishError): ...          # the branch moved under us
class TooLarge(PublishError): ...          # a documented GitHub limit was hit
class RateLimited(PublishError): ...       # GitHub asked us to slow down, and retrying did not clear it
class NoPreviousState(PublishError): ...   # nothing before the current commit

class Transport(Protocol):
    """The one seam. Tests are its only other caller."""
    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]
                ) -> tuple[int, dict[str, str], bytes]: ...
    def wait(self, seconds: float) -> None: ...

def publish(settings: Settings, folder: Path, token: str, message: str,
            transport: Transport | None = None) -> Outcome: ...

def root_entries(settings: Settings, token: str,
                 transport: Transport | None = None) -> tuple[str, ...]: ...

def fetch_previous(settings: Settings, token: str, into: Path,
                   prefix: str = "",
                   transport: Transport | None = None) -> Fetched: ...
```

Every failure this module **raises** is one of the types above. A crash
raises nothing and is §6's own row. None of them carries a sentence for
the writer — `docs/design.md` § Errors gives that job to the Face alone.

**`transport` is the whole test seam, and it is stated here because §7
depends on it.** `None` means the module's own `urllib.request` client.
Nothing in Pressless passes it; tests hand in a double that answers with
prepared responses and records every request. A module-private global
patched by name would work equally well for tests and would leave the
surface silent about it, which is what an implementer would otherwise
have to invent.

**Three things about the seam are part of the contract, because a test
double must supply all three.** It returns the response **headers**, which
is where a rate-limit hint arrives and without which §4.3's retry could
not read one. It signals *no answer* by raising `OSError`; every HTTP
status, error statuses included, is returned rather than raised, so the
module owns the mapping to §4.1's types and a double does not have to
guess it. And `wait` is the pacing clock: the module never calls `sleep`
itself, so a test observes the spacing INV-9 asserts by recording calls
rather than by waiting real seconds.

### 4.2 Working out what differs, without downloading anything

The repository's current state is read once, as a recursive tree listing.
That listing carries each file's path and its git blob hash; it does not
carry file content.

A local file is unchanged when its own git blob hash equals the hash the
listing gives for that path. The hash is computable locally, so an
unchanged file is never uploaded and never downloaded.

**Measured 2026-08-26**, because the rule the whole design rests on was
otherwise being recalled:

```
printf 'hello world\n' > f.txt; head -c 2048 /dev/urandom > f.bin; : > f.empty
git hash-object f.txt f.bin f.empty
python3 -c 'import hashlib,pathlib,sys
for n in sys.argv[1:]:
    d=pathlib.Path(n).read_bytes()
    print(hashlib.sha1(b"blob %d\0"%len(d)+d).hexdigest())' f.txt f.bin f.empty
```

Both commands agreed on all three, the empty file included. The
computation is `sha1(b"blob " + str(len(data)).encode() + b"\0" + data)`.

**Which branch, and it is not configurable.** All three functions act on
the repository's **default branch**, resolved from the repository itself
once per call rather than stored. Settings holds no branch field, and
adding one would change PRESS-0001's shipped file format and its setup —
so the alternative to resolving it is hard-coding a name that is wrong for
any repository whose default differs. §10 records that nothing here checks
the default branch is the branch GitHub Pages actually serves from.

**A truncated listing is a failure, not a smaller answer.** GitHub caps
the recursive listing and flags a response it had to cut. Treating a cut
listing as the repository's contents would make every missing path look
locally-new and every deletion invisible, so a flagged response raises
`TooLarge` rather than being used.

**Two conditions on the handed folder are refused rather than published.**
A folder that is not a directory is refused before the first request:
`rglob` yields nothing for one and raises nothing, so it would read as a
site with no files and every unprotected path would be deleted. And a
publish that would remove every unprotected path while writing none is
refused once the listing has been read and before the first write — a
finished build is never empty, and §3 decision 1 makes that commit
unrecoverable from inside Pressless. Both raise `PublishError`.

### 4.3 Writing the commit

Four steps, in this order, and the last one is the only one that changes
what a reader sees:

1. **One blob per changed file**, created explicitly and always
   base64-encoded. GitHub's tree endpoint also accepts inline content,
   and its documentation does not state what encoding that field takes —
   so this design does not use it. One rule covers prose and photographs
   alike rather than two rules split by a property of the file.
2. **One tree**, built on the current commit's tree, listing every
   changed path against its new blob and every removed path against a
   null hash.
3. **One commit**, whose parent is the commit the listing was read from.
4. **One reference update**, never forced.

**The site is unchanged until step 4.** Blobs and trees that nothing
points at are invisible to a reader and are collected by GitHub. So an
interruption at any earlier point leaves the site exactly as it was,
which is what lets the Face tell the writer *"your site has not
changed"* truthfully rather than hopefully.

**Never forcing step 4 is what makes a moved branch safe.** The commit's
parent is the state that was read, so if anything else has written to the
branch meanwhile the update is not a fast-forward and GitHub refuses it.
That refusal becomes `Conflict`. Forcing it would silently discard the
other write.

**Writes are paced, and a breach is honoured rather than raised.**
GitHub asks for at least a second between successive write requests, and
answers a breach with a retry hint rather than a plain refusal. The
Publisher waits as asked and retries, a bounded number of times; only when
that is exhausted does it raise `RateLimited`. Raising on the first hint
would fail a first publish for a condition GitHub expects the caller to
wait out. A first publish writes the whole site and is therefore slow —
ADR-0002 says so — and every publish after it writes a handful of files.

**The hint arrives two ways, and one too long to honour is refused.** A
secondary limit answers 429, or 403 carrying a `Retry-After`. The primary
limit sends no `Retry-After` at all: it reports a spent budget as
`x-ratelimit-remaining: 0` and names when it resets. Reading only
`Retry-After` made that an ordinary refusal, which sends the writer to
replace a key that is perfectly good. A hint naming longer than a publish
will block for raises `RateLimited` rather than being slept out, so the
writer is told rather than left waiting (PRESS-0046).

### 4.4 What is never touched

Settings holds the untouchable list. An entry on it is **neither written
nor removed**, whatever the handed folder contains. Both halves matter:
a list applied only to deletion still lets a stray file in the folder
overwrite the entry holding the custom domain.

**An entry is a bare repository-root name with no trailing slash, and it
matches a path's FIRST segment.** So an entry naming a directory protects
everything beneath it, and one naming a file matches only that file.
Comparing whole paths for equality instead would leave every file inside
an untouchable directory unprotected, which is the failure this list
exists to prevent.

Every other path is made to match the folder, deletions included, so a
page the writer removes actually goes.

**The rule is not re-evaluated at publish time.** `docs/design.md` is
explicit: the rule says what the list must contain, and the list is what
the Publisher consults. Deriving it afresh at publish would protect
exactly the pages the writer has just deleted, because the Builder has
stopped producing them.

`root_entries` is how the list is derived. It reports **every** entry at
the repository root, files and directories alike, as bare names with no
trailing slash. It decides nothing and filters nothing — rule 5 leaves it
unable to tell a stylesheet from an entry, so it cannot know which of them
the Builder produces. Setup and the Face remove those and store the rest.

**That filtering is theirs, and `docs/design.md` names the cost of getting
it wrong:** `content/` is ordinary Builder output, and a list that kept it
would make a deleted poem's source text permanent on the web.

### 4.5 Fetching back

`fetch_previous` reads the current commit's first parent and writes that
state into the folder it is given, optionally narrowed to a path prefix.
It writes files and returns; it does not publish, does not touch the
Store, and does not decide what the fetched state means. Undo is a
sequence the Face owns, and this is one step of it.

**A fetched file lands at `into` joined to its full repository-relative
path, with `prefix` used to select and never to strip.** So `Fetched.paths`
and the layout under `into` are the same strings, and the Face's undo step
reads them without reconstructing anything.

**`prefix` matches on path-segment boundaries, and a trailing slash is
optional and ignored** — the same rule §4.4 gives the untouchable list, for
the same reason. Matched as a bare string instead, `content` would also
select `contents.html`, and undo would write into the Store a file the
fetched directory never held.

Where the current commit has no parent there is nothing before it, and
that raises `NoPreviousState`.

**Nothing lands in `into` until every file has been fetched.** Written as
they go, a failure part-way leaves a mixture of the previous state and
whatever was already there — which the Face cannot tell from a complete
fetch, and undo is the feature that must not produce one (PRESS-0046).

**The consequence of §3 decision 1 lives here.** A second `fetch_previous`
called after an undo has been published reads the parent of the undo
commit, which is the state the undo replaced. That is the decided
behaviour.

### 4.6 What this module never does

- It never reaches Credentials. Rule 10 hands it a key.
- It never reaches the Store, the Builder, Marks or the Face.
- It never writes prose for the writer.
- It never decides what a draft is. Rule 4 carries S7, and rule 5 says
  this part has nothing to decide with.
- It never keeps state between calls.

## 5. Invariants

- **INV-1** — `src/pressless/publisher.py` imports no `pressless` module
  other than `pressless.settings`.
  *Test:* `tests/test_publisher.py::test_publisher_imports_no_forbidden_sibling`,
  walking the module's imports as
  `tests/test_settings.py::test_settings_imports_nothing_forbidden` does.
  *Breaks when:* an implementer imports `pressless.credentials` to fetch
  the key rather than taking it as an argument, which is the breach of
  rule 10 that rule 5 was rewritten to avoid.
  **It is a weak test in the way this project has already met:** an
  import walk passes against a module that does nothing. It is evidence
  about imports and never about where the key came from.

- **INV-2** — An entry on `settings.untouchable` is neither written nor
  removed, matched against a path's first segment. This holds when the
  handed folder contains a file of that name and when it does not, and it
  holds for every path beneath an entry naming a directory.
  *Test:* `tests/test_publisher.py::test_untouchable_is_neither_written_nor_removed`
  — three fixtures: the folder holds a *differing* file at an untouchable
  path; it holds nothing there; and the repository holds files beneath an
  untouchable *directory*. Assert the recorded requests carry no tree
  entry for any of them.
  *Breaks when:* an implementer applies the list to deletions only,
  which reads as protection and leaves the entry overwritable.
  **Only this rule can reject the write fixture:** every other rule in
  §4.4 makes a differing file an ordinary upload.

- **INV-3** — No request that changes the branch is made until every
  blob, the tree and the commit have succeeded. The reference update is
  the last write of a publish, and a transport failure raised *by that
  request* surfaces as `OutcomeUnknown`, never as the `Unreachable` any
  earlier step raises.
  *Test:* `tests/test_publisher.py::test_reference_update_is_last` — a
  recording transport; assert the reference update is the final entry,
  that a transport failing at the tree or commit step makes no reference
  request at all and raises `Unreachable`, and that one failing on the
  reference request itself raises `OutcomeUnknown`.
  *Breaks when:* an implementer updates the branch per batch to make a
  large first publish resumable, which is the change that turns a
  half-finished publish into a half-updated site.

- **INV-4** — A file whose local git blob hash equals the hash in the
  repository listing is not uploaded, and a publish where no file differs
  writes no commit and returns an empty `Outcome.commit`.
  *Test:* `tests/test_publisher.py::test_unchanged_files_are_not_uploaded`
  — publish against a listing that already matches the folder; assert no
  blob request, no commit request, and an empty commit sha.
  *Breaks when:* an implementer compares modification time or size,
  either of which reports a rewritten-but-identical file as changed —
  which is exactly what the Builder produces on every run.

- **INV-5** — The reference update is never forced, and a branch that
  moved since the listing was read raises `Conflict` rather than
  overwriting.
  *Test:* `tests/test_publisher.py::test_branch_that_moved_is_a_conflict`
  — assert no request body sets force, and that a refused update surfaces
  as `Conflict`.
  *Breaks when:* an implementer forces the update to clear a failure seen
  during development, which converts a refusal into silent data loss.
  **Asserting the type is what makes it bite:** an unreachable network
  also produces no successful update, so a clause asserting only that
  something was raised passes against an implementation reporting a
  conflict as a network fault.

- **INV-6** — A listing GitHub flags as cut short raises `TooLarge` and
  is never used to compute what differs.
  *Test:* `tests/test_publisher.py::test_truncated_listing_is_refused` —
  a listing carrying the truncation flag; assert `TooLarge` and that no
  blob request follows.
  *Breaks when:* an implementer reads the entries and ignores the flag,
  which makes every unlisted path look new and every deletion invisible.

- **INV-7** — No failure raised by this module carries the key, in its
  message or its representation.
  *Test:* `tests/test_publisher.py::test_no_failure_names_the_key` —
  force each failure type with a recognisable key value; assert that
  value appears in neither `str()` nor `repr()` of what is raised.
  *Breaks when:* an implementer includes the request headers in an error
  to make a failure diagnosable, and the key is a header.

- **INV-8** — `fetch_previous` reads the current commit's first parent,
  names the sha it fetched, and raises `NoPreviousState` where the
  current commit has no parent.
  *Test:* `tests/test_publisher.py::test_fetch_previous_names_its_source`
  and `::test_first_commit_has_no_previous_state`.
  *Breaks when:* an implementer resolves "previous" against the branch's
  second-newest commit by listing history, which differs from the first
  parent as soon as anything is merged.

- **INV-9** — Successive write requests are separated by the pacing wait,
  and a retry hint is waited out and retried rather than raised.
  *Test:* `tests/test_publisher.py::test_writes_are_paced_and_hints_retried`
  — a recording transport capturing the wait between writes, plus one
  answering the first write with a retry hint; assert the write is retried
  and that `RateLimited` is raised only once the bound is exhausted.
  *Breaks when:* an implementer writes as fast as the loop allows, which
  passes every other test in this file and fails on a first publish
  against the real service.

## 6. Failure modes

| What happens | What is raised | What the writer's site is |
|---|---|---|
| The handed folder is not a directory | `PublishError` | unchanged |
| The publish would remove every unprotected path and write none | `PublishError` | unchanged |
| No answer from GitHub, before the reference update | `Unreachable` | unchanged |
| No answer from GitHub, **during** the reference update | `OutcomeUnknown` | **unknown — may or may not have changed** |
| GitHub answers a server error **to** the reference update | `OutcomeUnknown` | **unknown — may or may not have changed** |
| Key rejected, or no write access | `Refused` | unchanged |
| `settings.repository` resolves to nothing | `RepositoryMissing` | unchanged |
| Branch moved since the listing was read | `Conflict` | unchanged |
| A documented GitHub limit was hit | `TooLarge` | unchanged |
| Retry hints exhausted | `RateLimited` | unchanged |
| Pressless stops before the reference update (crash, power loss) | nothing — the process is gone | unchanged |
| `fetch_previous` on a first commit | `NoPreviousState` | unchanged |

**Every row but one says *unchanged*, and the exception is the one that
matters.** §4.3's property is that nothing a reader sees changes until the
reference update — so a failure *during* that update is the single case
where the site's state is genuinely unknown. Reporting it as unchanged
would tell the writer his site had not moved when it had, which is exactly
the S6 promise §2 says this design exists to keep. **A server error is that
same case and not a refusal**: a gateway can fail after the update was
applied, so it leaves the state exactly as unknown as a dropped connection
does. Every other status is a definitive answer — GitHub authenticates and
validates before it acts — so each keeps its own row and its *unchanged*
(PRESS-0046). `OutcomeUnknown` is a
type of its own so the Face has something to branch on — a shared type
would leave it unable to tell the two apart. It must say the outcome is
unknown rather than claim either; confirming would mean reaching GitHub,
which is by definition what has just failed.

The Face turns each row into the three-part sentence `docs/design.md`
§ Errors requires; this module writes none of them.

## 7. Tests

`tests/test_publisher.py`, following the pattern of
`tests/test_credentials.py`.

**No test here reaches the network.** Every test hands in a double
through §4.1's `transport` argument — a recorder that answers with
prepared responses and keeps every request. That is what lets INV-3, INV-5
and INV-9 assert on request *order*, *absence* and *spacing*, which is
where this module's real risks are.

**A recording double is the test surface, not a convenience.** ADR-0002
notes that git's own safety checks are gone, so the checks have to be on
what Pressless sends. Assertions about the requests are the only place
that is observable.

Green against a stub that declares the surface and raises
`NotImplementedError`: INV-1 alone. Every other invariant needs the real
code, so a green INV-1 says nothing about the rest.

## 8. Alternatives considered (and rejected)

- **Shelling out to `git`.** Rejected by ADR-0002: it requires the writer
  to install and configure git, which is the problem this project exists
  to remove.
- **Undo that skips past previous undos.** Offered to the user
  2026-08-26 and declined in favour of §3 decision 1. It never restores a
  rejected version, at the cost of marking which commits were undos and
  of an undo whose effect depends on history the writer cannot see.
- **Undo disabled after one press.** Offered the same day and declined.
  It cannot restore a rejected version either, and needs nothing marked —
  but it leaves no way back beyond one step.
- **Inline file content in the tree request.** Rejected in §4.3: the
  documented field does not state its encoding, so photographs would rest
  on an assumption. Explicit base64 blobs cost one request per changed
  file and remove the question.
- **A third-party HTTP library.** Rejected by §3 decision 3 — a runtime
  dependency bought for syntax, which PRESS-0022 would then have to
  package.
- **Updating the branch in batches during a large first publish.**
  Rejected by INV-3: it makes the first publish resumable and every
  publish interruptible into a half-updated site, trading the property
  S6 depends on for a convenience on a run that happens once.

## 9. Out of scope

- **Deciding what is published.** Rule 4 gives that to the Builder.
- **The undo sequence itself.** Rule 1 gives the ordering to the Face;
  this module supplies one step of it.
- **Deriving and storing the untouchable list.** `root_entries` reports;
  setup and the Face decide and store.
- **Progress reporting during a slow first publish.** The Face's.
- **Photograph originals.** They never reach the site folder, so this
  module never sees one.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_publisher.py::test_publisher_imports_no_forbidden_sibling` |
| §4.2's two folder preconditions | `tests/test_publisher.py::test_a_site_folder_that_is_not_a_directory_is_refused` and `::test_a_publish_that_would_empty_the_site_is_refused` |
| §4.4's trailing-slash tolerance | `tests/test_publisher.py::test_an_untouchable_entry_with_a_trailing_slash_still_protects` |
| INV-2 | `tests/test_publisher.py::test_untouchable_is_neither_written_nor_removed` |
| INV-3 | `tests/test_publisher.py::test_reference_update_is_last` |
| INV-4 | `tests/test_publisher.py::test_unchanged_files_are_not_uploaded` |
| INV-5 | `tests/test_publisher.py::test_branch_that_moved_is_a_conflict` |
| INV-6 | `tests/test_publisher.py::test_truncated_listing_is_refused` |
| INV-7 | `tests/test_publisher.py::test_no_failure_names_the_key` |
| INV-8 | `tests/test_publisher.py::test_fetch_previous_names_its_source` and `::test_first_commit_has_no_previous_state` |
| That GitHub behaves as §4.3 describes | **nothing here** — no test reaches the network, so every assertion is about what Pressless sends and none about what GitHub does with it. PRESS-0022 stages a built artefact before release; the first real publish is where this is observed |
| §3 decision 1's consequence — a second undo restoring the rejected version | **nothing, and nothing should** — it is the decided behaviour, recorded here so a later reader does not fix it as a bug |
| Whether the stored untouchable list is still correct | **nothing** — a file added to the repository root outside Pressless is unprotected until `root_entries` is run again. `docs/design.md` names this and gives the Face a re-derive action; no check here can see it |
| The documented GitHub limits being the real ones | **nothing** — INV-6 refuses a listing GitHub itself flags, which needs no number. The limits in §4.3's reasoning are not asserted anywhere and would go stale silently if they were |
| INV-9 | `tests/test_publisher.py::test_writes_are_paced_and_hints_retried` |
| §6's server-error route to `OutcomeUnknown` | `tests/test_publisher.py::test_a_server_error_on_the_reference_update_is_outcome_unknown`, which also holds a refusal to its own row |
| §4.3's two hint shapes, and the bound on one | `tests/test_publisher.py::test_the_primary_rate_limit_is_waited_out_not_read_as_a_refusal`, `::test_a_rate_limit_naming_no_interval_waits_the_documented_minute` and `::test_a_wait_longer_than_the_bound_is_refused_rather_than_slept` |
| §4.5's all-or-nothing fetch | `tests/test_publisher.py::test_a_fetch_that_fails_part_way_leaves_the_folder_as_it_was` |
| Whether the pacing interval is long *enough* under real load | **nothing** — INV-9 fixes that the wait and the retry exist, which is falsifiable here. Whether the interval suffices is observable only against the real service, on a first publish |
| That the default branch is the branch GitHub Pages serves from | **nothing** — §4.2 resolves the default branch, and a repository serving Pages from another branch would publish successfully while the live site never changed. No check here can see it; the first real publish is where it shows |

## 11. Cross-doc impact

- **`docs/design.md` § What may depend on what — rule 5 named no write.
  Closed by PRESS-0026 on 2026-08-27, not by this spec.** §4.5 has
  `fetch_previous` write a fetched state into a folder it is handed, and
  rule 5 did not cover it. Rule 5 now takes rule 8's form. Its own gate
  found that naming the local write alone made things worse — it turned
  an omission into an exhaustive write list that excluded the Publisher's
  GitHub traffic — so the rule grants that traffic too.
- `docs/design.md` § The parts is unchanged, and rules 7 and 10 are used
  as they stand — which is what §3 decision 2 records.
- `ROADMAP.md` PRESS-0009 — its body carries the deferred undo question
  as open. §3 decision 1 settles it, and the bullet should record that.
- `ROADMAP.md` PRESS-0010 — **absorbed into this spec as an umbrella**,
  per the header. Its bullet stays as its own unit of work and closes with
  the code this contract governs; nothing about its scope moves. PRESS-0014
  and PRESS-0015, which depend on it, are unaffected.
- `docs/decisions/ADR-0002` is unchanged and is this spec's source.
- `CHANGELOG.md` — an entry when it ships.
- PRESS-0001 and PRESS-0002 are unchanged. This spec consumes
  `settings.repository` and `settings.untouchable` as shipped, and takes
  its key as an argument rather than reaching PRESS-0002 at all.
- PRESS-0019 is unaffected. It shares rule 10's hand-off shape but no
  code.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-26 | 3, cold — genre pinned `spec`; packet carried design.md rules 1-10, § The parts and § Errors, ADR-0002 and `settings.py` whole, and the executed blob-hash measurement. GitHub's live API declared an unrunnable region, so Q1 was out of scope there | 0 | 2 | 5 | 1 | **Eight verified, eight fixed, none dismissed. First gate on this document.** **All three lanes independently found the same two defects**, the strongest signal in the run. The spec never named **which reference it writes** — `Settings` carries no branch field, §11 claimed PRESS-0001 was unchanged, and `publish`, `root_entries` and `fetch_previous` must all agree; one builder hard-codes `main`, another resolves the default branch, a third adds a settings key and falsifies §11. And §7 required a **transport seam that §4.1 never declared**, while §1 closed the surface at "three requests and nothing else" — six of the eight invariant tests bind to that seam, so the test set rested on a contract the document did not state. Both are now in §4.1, the branch resolved per call and never stored. **The best single finding came from one lane and reaches the writer.** §6's table generalised that every failure leaves the site *unchanged*, which §4.3 supports only for an interruption **earlier than** the reference update — so a connection lost *during* that update would have had the Face tell the writer "Your site has not changed" for a publish that went out, breaking S6, the one promise §2 says this design exists to keep. That row is now split and its state named unknown. **One finding was the orchestrator's own process defect:** PRESS-0010 is a separate roadmap item whose entire scope — `fetch_previous`, `Fetched`, `NoPreviousState`, §4.5 and INV-8 — this spec had absorbed silently, because `write-spec` Step 1 item 5's id count was never run. It is now an umbrella naming both ids, per `spec-format.md` §2. **Two more were unstated contracts other parts bind to:** what the Publisher *does* with a rate-limit hint (it now waits and retries, raising the new `RateLimited` only when the bound is exhausted), and the untouchable list's string form — an entry naming a *directory* matched by equality would have deleted every file beneath it, so entries now match a path's first segment and INV-2 gains a directory fixture. **Q1 was zero**, which is what the packet bought: the two claims a lane could not check were the ones already executed before dispatch. **Three open questions resolved clean and are not counted** — § The stack does name one runtime dependency plus the imaging library, `tests/test_credentials.py` exists, and ROADMAP PRESS-0009 does carry the undo question as open. **One true finding was left unfixed as immaterial:** §9 does not name PRESS-0021 as the owner of the list's derivation, which changes nothing anyone builds. |
| 2 | 2026-08-26 | 3, cold — identical brief, packet rebuilt whole from disk and extended with § The stack, PRESS-0010's roadmap body and PRESS-0001's §10 hand-off row. GitHub's live API still an unrunnable region | 0 | 2 | 5 | 0 | **Seven verified, seven fixed; one dismissed as immaterial. Cap reached (2 for a spec); the tail is empty and the run ships.** **A cap on the violent side: four of the seven landed on text THIS RUN wrote**, each anchor checked against loop 1's ledger rather than recalled. What qualifies that reading is the shape — none of the four says loop 1's fix was *wrong*; each says it was incomplete, and three are one subject. **All three lanes independently found that subject:** loop 1 declared a `Transport` seam returning `(status, body)`, and then required §4.3 to read a rate-limit hint that conventionally arrives in a **response header** — so neither the module nor INV-9's own double could carry the signal the same loop had just mandated. Two further lanes found the seam's other unstated halves: how a transport signals *no answer at all* (INV-3 and INV-5 both assert on "a transport failing", which the Protocol never defined), and that nothing let a test control the pacing clock, so INV-9 either cost real wall-clock seconds or drove an implementer to patch `sleep` by name — the module-private route §4.1 had just rejected in writing. The seam now returns response headers, signals absence by raising `OSError` while returning every HTTP status, and carries `wait`. **The sharpest single finding was loop 1's own half-done repair.** Loop 1 split §6's row so a failure *during* the reference update no longer claimed the site was unchanged — and gave both stages the same `Unreachable` class, leaving the Face nothing to branch on, then told it to *re-read the branch*, which is the one thing it cannot do when GitHub is unreachable. `OutcomeUnknown` is now its own type, INV-3 owns both sides of the boundary, and the Face is told to report the outcome as unknown rather than confirm it. **Two pre-existing defects closed:** §4.1's "every failure is one of the types above" was falsified by §6's own *"the underlying failure"* row (a crash raises nothing, and is now its own row), and `prefix` was never pinned as byte or path-segment though §4.4 pins exactly that question for the untouchable list — matched as a bare string, `content` also selects `contents.html`. **One finding is surfaced, not applied:** design rule 5 permits the Publisher to *read* Settings and a folder and names no write, while rule 8 shows the form the design uses when a part writes — and §4.5 has `fetch_previous` write a fetched state to disk. §11 no longer claims that section is unchanged; amending it is another document's gate. **Dismissed as immaterial:** §10's *"the limits in §4.3's reasoning"* points loosely, the truncation cap being §4.2's — imprecise rather than false, and no conformer builds differently. **Routing:** not re-gated. A spec's cap is where implementation takes over, and implementation is the better third reviewer. |
