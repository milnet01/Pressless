# PRESS-0127 — Empty repository: setup finishes, and the first publish starts it

**Status:** spec draft (2026-09-18).
**Kind:** fix.
**Source:** ROADMAP PRESS-0127 (the PRESS-0021 amendment gate, 2026-09-17;
the probe and the user's decision, 2026-09-18).

**Amends:** PRESS-0009 (§4.2, §6, INV-3) and PRESS-0021 (§6). §11 lists
each edit.

Layman: someone whose GitHub repository is brand new and empty can finish
setup, and their first Publish just works. Pressless puts the first file in
itself.

## 1. Goal

After this ships, a repository with no commits is a normal starting point.
Setup against one finishes. The first publish to one makes the repository
match the site folder, as any other publish does. The writer does nothing
extra.

## 2. Problem

GitHub answers several requests with `409` and the message
`Git Repository is empty.` when a repository has no commits. Measured
2026-09-18 against a throwaway empty repository, and recorded on the
PRESS-0127 roadmap item:

- `GET commits/HEAD` and `GET commits/main` answer 409.
- `POST git/blobs` and `POST git/trees` answer 409.
- `PUT contents/<path>` succeeds and creates a first commit. After it,
  `POST git/blobs` succeeds.

`publisher._failure` maps every 409 to `Conflict`, *"the branch moved since
it was read"*. So:

1. `publisher.root_entries` raises `Conflict`, and setup shows the
   branch-moved sentence and never finishes.
2. `publisher.publish` raises `Conflict` on its head read.
3. Mapping the 409 alone would not help `publish`. The Git Data API that
   ADR-0002 publishes through cannot write the first commit.
4. `publisher.fetch_previous` raises `Conflict` where the answer is that
   there is nothing to go back to.

Pressless is for anyone with a GitHub Pages repository, and a new one starts
empty.

## 3. Scope decisions (agreed with the user)

1. **Pressless starts an empty repository itself.** Decided by the user
   2026-09-18. The alternative was a message telling the writer to add a
   file on GitHub first.
2. **The start happens at the first Publish, not during setup.** Decided by
   the user 2026-09-18. Setup keeps reading GitHub and never writing to it.
3. **The start commit holds one real file of the site.** Decided by the user
   2026-09-18. No placeholder is written, so nothing is removed afterwards.

## 4. Design

### 4.1 Recognising an empty repository

A read (`GET`) answered `409`, whose JSON `message` contains `empty` after
`str.casefold`, means the repository has no commits. Any other 409 keeps
today's mapping.

The message is part of the test because GitHub's documentation gives a 409
on `GET commits/{ref}` no meaning beyond *"conflict"*. A status-only test
would treat an unexplained 409 on a repository that has commits as empty,
and §4.3 would then write to it.

Three reads are affected, and each has one answer:

| Read | Caller | Answer on an empty repository |
|---|---|---|
| `commits/HEAD` | `root_entries` | returns `()` |
| `commits/HEAD` | `fetch_previous` | raises `NoPreviousState` |
| `commits/{branch}` | `publish` | starts the repository (§4.3) |

`root_entries` returning `()` needs nothing new from setup. `untouchable(())`
is `()`, and `setup._done` already says Pressless found nothing it must leave
alone.

`fetch_previous` raises before it creates `into`.

An empty answer anywhere else is not handled here and maps to
`RemoteStateMissing` (§6).

### 4.2 The public surface

Unchanged. No type, function or argument is added. The start write goes
through the same `Transport` seam as every other request.

### 4.3 The first publish to an empty repository

`publish` reads the default branch, then its head. When that read reports an
empty repository:

1. **Read the folder.** `_local_files` runs as it does today, so a folder
   that is not a directory, a stray and an unreadable file all refuse here.
   The repository is still empty.
2. **Choose the start file.** It is the first path, in sorted order, that
   `_is_protected` does not match. No such path: return
   `Outcome(commit="", uploaded=(), removed=())` and write nothing.
3. **Write it.** One request:

   ```
   PUT {API}/repos/{repository}/contents/{path}
   {"message": <the handed message>, "content": <base64 of the file's bytes>}
   ```

   The path is encoded by `_segment`, which keeps its slashes. The
   body carries no `branch` and no `sha`. GitHub's documented default for
   `branch` is the repository's default branch, which is the branch
   `publish` resolved.
4. **Carry on.** Read the branch's head again and publish as PRESS-0009
   §4.2 and §4.3 describe. The start file's blob hash now matches the
   listing, so it is not uploaded again.

The start write is made at most once per call. If the second head read still
reports an empty repository, `publish` raises `RemoteStateMissing` and writes
nothing more.

**What `publish` returns.** `Outcome.uploaded` includes the start file.
`Outcome.commit` is the last commit written: the publish commit, or the
start commit's sha from the `PUT` answer (`commit.sha`) when nothing else
differed.

### 4.4 Why the start may come before the blobs

PRESS-0009 INV-3 makes the reference update the first request that changes
the branch. The start write changes it earlier. This spec amends INV-3 for
one case: a repository with no commits.

What INV-3 protects is a site left half-updated. An empty repository has no
earlier site to damage. An interruption after the start leaves one real file
of the site the writer asked to publish. The next publish reads a repository
with commits and completes it through the normal path.

## 5. Invariants

- **INV-1** — `root_entries` on an empty repository returns `()` and makes
  no write request.
  *Test:* `tests/test_publisher.py::test_root_entries_of_an_empty_repository_is_empty`.
  *Breaks when:* the 409 on `commits/HEAD` reaches `_failure`, which raises
  `Conflict` today.

- **INV-2** — `fetch_previous` on an empty repository raises
  `NoPreviousState` and creates nothing under `into`.
  *Test:* `tests/test_publisher.py::test_fetch_previous_of_an_empty_repository_has_no_previous_state`.
  *Breaks when:* the empty answer maps to `Conflict`, or `into` is created
  before the head read.

- **INV-3** — A publish to an empty repository makes exactly one start
  write, before any blob write. It is a `PUT` to `contents/<path>` for the
  first unprotected path in sorted order. Its body holds the handed message
  and that file's bytes in base64, and nothing else. That path is never
  sent as a blob.
  *Test:* `tests/test_publisher.py::test_an_empty_repository_is_started_with_one_real_file`,
  against a double whose head read answers the empty 409 until a `PUT` is
  recorded.
  *Breaks when:* the start writes a placeholder, picks a protected or
  unsorted path, sends a `branch` field, or uploads the start file again as
  a blob.

- **INV-4** — No write request reaches an empty repository before the folder
  is accepted. A folder that is not a directory, a stray, an unreadable file
  and a folder with nothing unprotected each make no write at all.
  *Test:* `tests/test_publisher.py::test_nothing_is_written_to_an_empty_repository_before_the_folder_is_accepted`.
  *Breaks when:* the start write is made as soon as the empty answer
  arrives, before `_local_files` has run.

- **INV-5** — The start write's lost answer or server error raises
  `OutcomeUnknown`. A 409 or 422 answering it raises `Conflict`.
  *Test:* `tests/test_publisher.py::test_a_lost_start_write_is_outcome_unknown`.
  *Breaks when:* the start write is sent without the outcome-unknown flag
  the reference update uses, so a dropped connection reads as `Unreachable`.

- **INV-6** — The start is written at most once per call. A head read that
  still reports an empty repository after the start raises
  `RemoteStateMissing` and makes no further write.
  *Test:* `tests/test_publisher.py::test_an_empty_repository_is_started_at_most_once`.
  *Breaks when:* the start sits in a retry loop keyed on the empty answer.

- **INV-7** — A 409 answering a read whose message does not contain `empty`
  keeps today's mapping, `Conflict`, and makes no write.
  *Test:* `tests/test_publisher.py::test_a_conflict_that_does_not_say_empty_is_still_a_conflict`.
  *Breaks when:* the empty test keys on the status alone.

- **INV-8** — After a start, `Outcome.uploaded` includes the start file.
  `Outcome.commit` is the start commit's sha when nothing else differed,
  and the publish commit's sha otherwise.
  *Test:* `tests/test_publisher.py::test_a_started_publish_reports_the_start_file`,
  which covers a one-file folder and a larger one.
  *Breaks when:* the second pass returns its own empty `Outcome` because
  the start file already matches the listing.

- **INV-9** — Setup against an empty repository finishes, saves an empty
  untouchable list, and sends no write request to GitHub.
  *Test:* `tests/test_setup.py::test_setup_finishes_against_an_empty_repository`.
  *Breaks when:* `root_entries` raises on the empty answer, or setup starts
  the repository itself.

## 6. Failure modes

Every row of PRESS-0009 §6 still holds. These are the rows this spec adds or
changes.

| What happens | What is raised | What the repository holds |
|---|---|---|
| The folder is refused, or has nothing unprotected | as PRESS-0009 §6, or nothing | no commits |
| No answer, or a server error, on the start write | `OutcomeUnknown` | no commits, or the start file |
| A 409 or 422 on the start write — someone wrote first | `Conflict` | whatever the other writer left |
| A 413 on the start write | `TooLarge` | no commits |
| Still empty after the start write | `RemoteStateMissing` | unknown; the next publish reads it |
| Any failure after the start write | its PRESS-0009 §6 type | the start file |
| An empty answer to any read not in §4.1's table | `RemoteStateMissing` | unchanged |

**The next publish settles every row.** A repository still empty is started
again. One holding the start file is published through the normal path.

**The last-but-one row's sentence is imprecise.** The Face says *"Your site
has not changed."* for those types, and the repository gained the start
file. §10 records it.

## 7. Tests

`tests/test_publisher.py` gains the tests for INV-1, INV-2, INV-3, INV-4,
INV-5, INV-6, INV-7 and INV-8.
`tests/test_setup.py` gains INV-9's.

The existing `_Transport` double answers by URL and cannot change its answer
mid-call. The INV-3, INV-6 and INV-8 tests need a head read that answers the
empty 409 until a `PUT` is recorded, and then a commit. Give that its own
double, answering each read by URL, as `CLAUDE.md` asks of test doubles.

Each test is seen failing against today's `publisher.py`, then
mutation-probed once the code lands, one mutation per *Breaks when*.

## 8. Alternatives considered (and rejected)

- **Tell the writer to add a file on GitHub first.** Rejected by the user
  2026-09-18 (§3 decision 1). Pressless exists so he needs no one technical.
- **Start the repository during setup.** Rejected by the user 2026-09-18
  (§3 decision 2). Setup would write to GitHub before he had published
  anything.
- **A placeholder start file, removed by the same publish.** Rejected by
  the user 2026-09-18 (§3 decision 3). The history shows a file added and
  then deleted, and a placeholder gains nothing over a file the publish
  needs anyway.
- **Write the first commit through the Git Data API.** Not possible:
  `git/blobs` and `git/trees` answer 409 on an empty repository (§2).
- **Recognise an empty repository by the 409 alone.** Rejected in §4.1. A
  misread sends a start write to a repository that has commits.

## 9. Out of scope

- **Undoing the first publish to a started repository.** The publish
  commit's parent is the start commit, so going back one step fetches one
  file. Tracked by PRESS-0015, which owns undo.
- **Checking that GitHub Pages serves the default branch.** PRESS-0009 §10
  already records that nothing checks it. Unchanged here.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_publisher.py::test_root_entries_of_an_empty_repository_is_empty` |
| INV-2 | `tests/test_publisher.py::test_fetch_previous_of_an_empty_repository_has_no_previous_state` |
| INV-3 | `tests/test_publisher.py::test_an_empty_repository_is_started_with_one_real_file` |
| INV-4 | `tests/test_publisher.py::test_nothing_is_written_to_an_empty_repository_before_the_folder_is_accepted` |
| INV-5 | `tests/test_publisher.py::test_a_lost_start_write_is_outcome_unknown` |
| INV-6 | `tests/test_publisher.py::test_an_empty_repository_is_started_at_most_once` |
| INV-7 | `tests/test_publisher.py::test_a_conflict_that_does_not_say_empty_is_still_a_conflict` |
| INV-8 | `tests/test_publisher.py::test_a_started_publish_reports_the_start_file` |
| INV-9 | `tests/test_setup.py::test_setup_finishes_against_an_empty_repository` |
| That GitHub still answers an empty repository as §2 measured | **nothing** — no test reaches the network. If the wording loses `empty`, an empty repository falls back to today's `Conflict` |
| The Face's *"Your site has not changed."* after a failure past the start write | **nothing** — the sentence is imprecise there (§6). Publishing again settles it, which is S6's promise |

## 11. Cross-doc impact

- **PRESS-0009** — INV-3 gains *"amended by PRESS-0127"*, pointing at §4.4.
  §6's 409 row names the empty exception and points here. §4.2's
  `root_entries` and `fetch_previous` paragraph points at §4.1. The new
  direction is gated in this spec; those edits are pointers to it.
- **PRESS-0021** — §6 gains a row: a repository with no commits finishes
  setup with nothing left alone.
- **ADR-0002** — its Consequences gain one line: a repository with no
  commits is started with one file through the Contents API.
- `CHANGELOG.md` — an entry when it ships.
- `setup.py` and `face.py` are unchanged.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0127-empty-repository-loop-log.md`.
