# PRESS-0009 — Publisher: making GitHub match the folder it was handed

**Status:** draft (2026-08-26). Not yet gated.
**Kind:** implement.
**Source:** ROADMAP PRESS-0009 (`docs/design.md` § The parts, § What may
depend on what rules 5, 7 and 10; ADR-0002).

**Blocked by:** PRESS-0001 and PRESS-0002, both shipped.
**Blocker for:** the Face's publish and undo sequences.

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
class Unreachable(PublishError): ...       # no answer from GitHub
class Refused(PublishError): ...           # key rejected, or no write access
class RepositoryMissing(PublishError): ... # settings.repository resolves to nothing
class Conflict(PublishError): ...          # the branch moved under us
class TooLarge(PublishError): ...          # a documented GitHub limit was hit
class NoPreviousState(PublishError): ...   # nothing before the current commit

def publish(settings: Settings, folder: Path, token: str,
            message: str) -> Outcome: ...

def root_entries(settings: Settings, token: str) -> tuple[str, ...]: ...

def fetch_previous(settings: Settings, token: str, into: Path,
                   prefix: str = "") -> Fetched: ...
```

Every failure is one of the types above. None of them carries a sentence
for the writer — `docs/design.md` § Errors gives that job to the Face
alone.

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

**A truncated listing is a failure, not a smaller answer.** GitHub caps
the recursive listing and flags a response it had to cut. Treating a cut
listing as the repository's contents would make every missing path look
locally-new and every deletion invisible, so a flagged response raises
`TooLarge` rather than being used.

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

**Writes are paced.** GitHub asks for at least a second between
successive write requests and answers a breach with a retry hint rather
than a plain refusal. A first publish writes the whole site and is
therefore slow — ADR-0002 says so — and every publish after it writes a
handful of files.

### 4.4 What is never touched

Settings holds the untouchable list. A path on it is **neither written
nor removed**, whatever the handed folder contains. Both halves matter:
a list applied only to deletion still lets a stray file in the folder
overwrite the entry holding the custom domain.

Every other path is made to match the folder, deletions included, so a
page the writer removes actually goes.

**The rule is not re-evaluated at publish time.** `docs/design.md` is
explicit: the rule says what the list must contain, and the list is what
the Publisher consults. Deriving it afresh at publish would protect
exactly the pages the writer has just deleted, because the Builder has
stopped producing them.

`root_entries` is how the list is derived. It reports what sits at the
repository root and decides nothing; setup and the Face turn that into
the stored list.

### 4.5 Fetching back

`fetch_previous` reads the current commit's first parent and writes that
state into the folder it is given, optionally narrowed to a path prefix.
It writes files and returns; it does not publish, does not touch the
Store, and does not decide what the fetched state means. Undo is a
sequence the Face owns, and this is one step of it.

Where the current commit has no parent there is nothing before it, and
that raises `NoPreviousState`.

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

- **INV-2** — A path on `settings.untouchable` is neither written nor
  removed. This holds when the handed folder contains a file of that
  name, and when it does not.
  *Test:* `tests/test_publisher.py::test_untouchable_is_neither_written_nor_removed`
  — one fixture where the folder holds a *differing* file at an
  untouchable path and one where it holds nothing there; assert the
  recorded requests carry no tree entry for that path in either case.
  *Breaks when:* an implementer applies the list to deletions only,
  which reads as protection and leaves the entry overwritable.
  **Only this rule can reject the write fixture:** every other rule in
  §4.4 makes a differing file an ordinary upload.

- **INV-3** — No request that changes the branch is made until every
  blob, the tree and the commit have succeeded. The reference update is
  the last write of a publish.
  *Test:* `tests/test_publisher.py::test_reference_update_is_last` — a
  recording transport; assert the reference update is the final entry,
  and that a transport failing at the tree or commit step makes no
  reference request at all.
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

## 6. Failure modes

| What happens | What is raised | What the writer's site is |
|---|---|---|
| No answer from GitHub | `Unreachable` | unchanged |
| Key rejected, or no write access | `Refused` | unchanged |
| `settings.repository` resolves to nothing | `RepositoryMissing` | unchanged |
| Branch moved since the listing was read | `Conflict` | unchanged |
| A documented GitHub limit was hit | `TooLarge` | unchanged |
| Interrupted before the reference update | the underlying failure | unchanged |
| `fetch_previous` on a first commit | `NoPreviousState` | unchanged |

Every row says *unchanged*, and that is §4.3's property rather than a
coincidence. The Face turns each into the three-part sentence
`docs/design.md` § Errors requires; this module writes none of them.

## 7. Tests

`tests/test_publisher.py`, following the pattern of
`tests/test_credentials.py`.

**No test here reaches the network.** The transport is supplied by the
caller-facing seam so a test can hand in a recording double that answers
with prepared listings and records every request made. That is what lets
INV-3 and INV-5 assert on request *order* and *absence*, which is where
this module's real risks are.

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
| Pacing being enough to avoid a refusal under load | **nothing** — observable only against the real service, on a first publish |

## 11. Cross-doc impact

- `docs/design.md` § The parts and § What may depend on what are
  unchanged. This spec is written to rules 5, 7 and 10 as they stand,
  which is what §3 decision 2 records.
- `ROADMAP.md` PRESS-0009 — its body carries the deferred undo question
  as open. §3 decision 1 settles it, and the bullet should record that.
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
