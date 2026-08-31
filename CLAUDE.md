# Pressless — instructions for Claude Code

## Where this project is

**State:** 5 — Building. **In flight:** nothing. `PRESS-0001`,
`PRESS-0002`, `PRESS-0004`, `PRESS-0005`, `PRESS-0009`, `PRESS-0010`,
`PRESS-0019`, `PRESS-0024`, `PRESS-0025`, `PRESS-0026`, `PRESS-0033`,
`PRESS-0032`, `PRESS-0034` and `PRESS-0035` are ✅. Run
`python3 -m pytest` for where
code stands, and the roadmap for what is queued, blocked or newly filed.

> Keep the block above true, and keep it to three facts — the state, what
> is in flight, and what is done. That is the only position this project
> records; everything else is read off the roadmap. Everything else about where
> work stands is read off things that cannot lie — whether a spec exists,
> whether tests fail, what `git status` says, whether the roadmap bullet
> is 🚧. A recorded step number starts lying the first time a session
> forgets to update it, and still reads as authoritative.

## How work is done here

- **`~/.claude/workflow.md`** — the states, the gates, and what "done"
  means. Read in place. This project does not have its own copy.
- **`~/.claude/standards/`** — how to write code, tests, commits,
  documents, releases. Also read in place.

Neither is summarised here. A rule restated in two places is two rules
that will disagree.

## This project's own facts

Everything below is specific to this project, which is why it lives here
rather than in a standard.

### Stack

Python 3, the standard library's own web server for the Face, `Pillow` for
photographs, the operating system's keyring for the publishing key, and
PyInstaller to package one artefact per system. `docs/design.md` § The
stack, and what it rules out owns the choice and the reasoning; this line
records it rather than restating why.

### Build and test

Python. One runtime dependency today — `keyring`, the operating system's
credential store, reached only by `credentials.py` (PRESS-0002); `Pillow`
joins it when photographs land (§ Stack). That is present state, not a
cap. The gate needs `pytest` and `ruff` on top, and PyInstaller is a
build-time packager that belongs beside those rather than in
`dependencies`. `pip install -e '.[dev]'` installs what CI runs. `pyproject.toml`
holds the packaging and the pytest settings; `src/` is on the path
through it, so there is no install step beyond that one.

```bash
./scripts/local-ci.sh      # the gate: leak sweep, lint, suite
./scripts/local-ci.sh --docs   # documentation push: leak sweep alone
python3 -m pytest          # the suite alone
ruff check src/ tests/     # lint alone
```

**`scripts/local-ci.sh` is the gate, and `.github/workflows/ci.yml` calls
that same file** — it holds no checks of its own, so the two cannot
drift. The machine-wide hook discovers the script by name and runs it
over the commits being pushed — so a failing tree cannot leave a machine
where `core.hooksPath` is set **and `~/.claude/githooks/pre-push` is
present**. Those two decide whether anything is gated at all;
`ants.gate.docsGlob` only decides which checks run.

**Three machine-local git config keys, and a fresh clone has none of
them.** Two belong here; `ants.pressless.archive` has its own paragraph
below.

```bash
git config core.hooksPath .githooks
git config ants.gate.docsGlob 'docs/*|*.md|LICENSE|*.txt|*.rst'
```

**`core.hooksPath` is what makes any hook fire at all.** Unset, git looks
in `.git/hooks`, nothing runs, and nothing says so. `.githooks/pre-push`
only delegates to the machine-wide gate; where that is absent it prints
`NOTHING WAS CHECKED` and exits 0, so it warns rather than blocks.

**`ants.gate.docsGlob` records a decision rather than changing one.** Its
value here is deliberately the hook's own fallback, so setting it alters
no behaviour today. `commits.md` § 4.2 makes the *unset* key the breach: a
shared hook cannot know what a given pipeline reads, so it has to be
told. The wide list is right here because `--docs` runs the leak sweep,
which is the check a markdown edit in this repository can actually
breach, and no test reads a document as data. Narrow it if either stops
being true — and a narrowing reverts on any clone where the key is unset.

**Two tests are skipped by default and they are the most important
ones.** `tests/test_marks_archive.py` and `tests/test_store_archive.py`
prove S2 against the real WordPress export, which is personal data and
cannot live in a public repository — so they run only where that file
is, and a green CI run says nothing about either. The gate points
`PRESSLESS_ARCHIVE` at a path held in a machine-local git config key,
so they run here without that path entering this repository:

```bash
git config ants.pressless.archive /path/to/wordpress-export.xml
```

Or set it for one run:

```bash
PRESSLESS_ARCHIVE=<path to the WordPress export> python3 -m pytest
```

**Two test results mean less than they look.** `test_marks_is_pure`
(INV-7) passes against *any* module that imports nothing forbidden — an
empty file included — so it is evidence about imports, never about the
code working. And with `marks.py` absent the suite errors at
*collection*, so no assertion runs at all: a run that says nothing failed
may have run nothing. Read the collected count, not the exit code.

**Proving a test red before the code exists takes a stub; proving it
CATCHES anything takes more.** `mutation_probe` refuses without a green
baseline, so it cannot run while the tests are red — the two checks never
overlap. What works: red the tests against a stub that declares the surface
and raises `NotImplementedError`, then write a throwaway reference
implementation *outside* the tree, probe that, and delete it. PRESS-0001's
INV-7 test passed its own red run and still could not see the breach it
names; only the probe found that.

**The throwaway is not needed where the real implementation is next.**
PRESS-0009 probed the shipped module instead, immediately after
`write-code`, and that is better evidence — it measures the code that
ships rather than a stand-in. It found INV-5's "never forced" clause
unfalsifiable: the clause stripped spaces out of the request body and
then searched it for a needle carrying a space of its own, so no body
could ever match it, forced or not. The red run passed against that and
could not have seen it. Probe after the code lands, and probe one
mutation per route the invariant's own *Breaks when* names.

**A test double written before the implementation encodes a guess about
the request shape, and the guess can make a faithful implementation
impossible to pass.** `tests/test_publisher.py`'s first draft answered
every read with one generic response. The Publisher makes three reads
whose answers have nothing in common — the repository names its default
branch, the head commit names its tree, then the tree listing — so no
correct implementation could satisfy it. The fix is to give the double a
by-URL answer for each read rather than to bend the code toward the
fixture. Watch for it whenever a double answers positionally: an
implementation that legitimately adds one request shifts every later
answer onto the wrong step.

**A test that pins a name must hold its own copy of the name.**
`tests/test_settings.py` writes `"settings.json"` out rather than importing
`FILE_NAME` from the module under test. Share the literal and INV-5 compares
the module against itself, so `path_for` could name any file and stay green.
Do not tidy this into an import.

**Windows is testable, and that is not obvious from anything else here.**
Development happens on Linux and the app must run on both. A Windows 10
test box is reachable over SSH from the maintainer's machine under the
host alias `wintest`; the connection details live in that machine's SSH
config and deliberately not in this public repository. Chrome and Edge
are both installed.

**Python is NOT installed on that box, and must not be.** A machine with
an interpreter cannot show that the packaged executable carries
everything it needs, which is the whole of S4. Anything the app needs at
runtime it must bring with it.

### This repository is PUBLIC, and nothing here may name the writer

`milnet01/Pressless` on GitHub, MIT. The site it publishes belongs to a
real person; **this repository is about the app, and must not identify
him.** Write "the writer", never a name — in documents, roadmap bullets,
commit messages and code comments alike.

**What was removed on 2026-08-25, so it is not reintroduced:** his name,
his band, his domain, his GitHub account, his audience size, and a
hard-coded Google Analytics measurement id. The id belongs in Settings
by dependency rule 8, which is where the design already put it — writing
it into a document was the mistake, not just the leak.

**Publishing a document is publishing its history**, which is the whole
reason this needs saying. De-personalising a file changes nothing about
what `git log` serves. The pre-public history was archived off-repo
before the first push rather than published.

The gate sweeps all three surfaces, so where it runs this is already
done. Sweep by hand where it does not. **The only expected hits are the
pattern lines themselves** — the ones below, and the copies of them in
`scripts/local-ci.sh`, which name what they are looking for. Anything
else means something leaked:

```
git grep -n -iE "charl|jordaan|18down|G-Y7N2F5SNY2|192\.168" -- .
```

And sweep the history too, not just the tree — that is the mistake this
whole section exists to prevent:

```
git grep -n -iE "charl|jordaan|18down|G-Y7N2F5SNY2|192\.168" $(git rev-list --all) -- . \
  | grep -vF 'charl|jordaan|18down'
```

**That searches the FILES in every commit, and not the commit MESSAGES.**
`git grep` reads trees, so a name written into a subject line passes it
without a hit — and a message is published by the same push. Sweep those
separately:

```
git log --all --format='%H %s%n%b' | grep -inE "charl|jordaan|18down|G-Y7N2F5SNY2|192\.168"
```

### The roadmap carries two `Layman:` styles, and they stay

`roadmap_log op:"amend_field"` corrects a bullet's `Layman:` after
creation (ANTS-4667). It writes the store column, so it works wherever
the render composes that trailer — the bold-style bullets. Where the
body declares `Layman:` at a line start it refuses
`field_shadowed_by_body` and names `op:"amend_body"` as the route,
because a declaration wins at render and would be re-parsed back over
the column. Both branches verified 2026-08-27.

**What stays one-way is the declaration itself**: deleting it does not
hand the column back. Measured 2026-08-27 — `amend_body` removing a
`Layman:` declaration is refused by the render gate with
`render_gate_unmet`, because the bullet would be left carrying none. So the plain-style bullets
corrected on 2026-08-25 and the bold-style rest go on parsing by
different routes. **Leave them that way** — reconciling changes nothing
anyone reads.

### How documents get written here

Standing instructions from the user, given 2026-08-25 while the Marks
spec was being gated. They changed the outcome of that gate, so they are
recorded rather than remembered.

- **A fix must serve the document's stated purpose.** Ask it of the
  *fix*, not just of the finding that prompted it: if the edit changes
  nothing anyone builds, it does not belong, however true it is. This
  removed a block of measured counts from the Marks spec after those
  counts had already survived two review loops.
- **Avoid counts and line numbers.** They go stale fast, and a stale
  number is worse than none because a reader edits *toward* it. Where a
  number is genuinely evidence, ship a test that prints it and cite the
  test — the Marks spec's archive figures live in its conformance run,
  not in its prose.
- **Shorter prose.** Length is surface area: a reviewer finds defects in
  explanation that directs nothing. Rationale belongs in a sentence.
- **A review loop-log row is permanent the moment it is committed** —
  the global rule forbids editing a landed row, so a long one can never
  be shortened afterwards. Write it short the first time; the shorter
  prose rule above has no second chance here.
- **Everything truthful, factual, verifiable.** Run the case that would
  refute a claim, not the one that confirms it. Two of the Marks spec's
  worst defects — a false security rationale, and an unanchored pattern
  that admitted a CSS payload into a `style` attribute — were found only
  by executing them.

**Prose here hard-wraps at about 70 columns, and that breaks exact-match
editing.** A replacement string retyped from a sentence you just read will
not match, because the line breaks fall in places you did not notice — it
fails as a zero-count assertion, not as a wrong edit, so it is safe but it
costs a round trip every time. Build the `old` string from the file's
actual bytes (`sed -n 'A,Bp'`), never from memory of the sentence. The
same wrap is why a plain `grep` returns false negatives on a quoted
phrase: use `workspace_search` with `match_wrapped: true` before believing
a miss.

**Building a review packet trips the global config lock, and the message
names the wrong cause.** A gate assembles its brief from `~/.claude`
files; one shell command that both reads those paths and redirects to a
file is refused with *"the ~/.claude instruction surface is edited from a
session whose cwd is ~/.claude"* -- although nothing under `~/.claude` is
being written. The hook matches the command text, not its direction.
Split the read from the write, or reuse the brief half of the previous
packet. Do not reach for the bypass token or relaunch with the unlock
variable: neither is warranted, because no edit to that surface is
intended.

**A trap worth knowing: a section intro written by
`roadmap_log op:create_section` cannot be amended by any verb**, and a
hand edit to `ROADMAP.md` is discarded by the next render. Never put a
count, an id list or a date in one. The Milestones section carries a
stale item count for exactly this reason; filed as Ants MCP feedback.

### Roadmap IDs

`PRESS-NNNN`, per `roadmap-format.md` § 3.5.1. **The roadmap is served
from the Ants roadmap store, not from `ROADMAP.md`** — migrated
2026-08-25, so the file is a generated render and a hand edit to it is
discarded by the next write. Read it with `roadmap_query`, write it with
`roadmap_log`. Changed from `DOWN-`
2026-08-17, before any id was allocated: this app is deliberately not
named after its first user, and a prefix naming him would have said the
opposite in every commit subject. Commit subjects
are `<ID>: <description>`, per `commits.md`.

### Review history

This file is read in full by every session on every turn, so its
`review-contract` loop log is kept in
`docs/claude-md-review-2026-08-27.md` rather than here.

### Overrides

Any place this project deliberately departs from a global standard goes
in `docs/standards/`, with the reason. **`versioning-overrides.md` is
not one of those** — it holds the answers `versioning.md` §§ 3 and 4 ask
every project for, which is why a project following the global set
unmodified still writes it. That directory's own `README.md` sorts the
two, and a departure would be a third kind of file.
