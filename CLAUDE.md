# Pressless — instructions for Claude Code

## Where this project is

**State:** 5 — Building. **In flight:** nothing. `PRESS-0001`, `PRESS-0002`
and `PRESS-0004` are ✅ — spec, tests and code each. `PRESS-0009` and
`PRESS-0019` are unblocked: `docs/design.md` rule 10 made the decision they
waited on. **Also startable:** `PRESS-0024`. Run `python3 -m pytest` for
where code stands.

> Keep the three lines above true, and keep them to three lines. They are
> the only position this project records. Everything else about where
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
PyInstaller to package one file per system. `docs/design.md` § The stack,
and what it rules out owns the choice and the reasoning; this line records
it rather than restating why.

### Build and test

Python. One runtime dependency — `keyring`, the operating system's
credential store, reached only by `credentials.py` (PRESS-0002) — plus
`pytest` to run the suite. `pyproject.toml` holds the packaging and the
pytest settings; `src/` is on the path through it, so no install step is
needed beyond having those two present.

```bash
python3 -m pytest          # the suite
ruff check src/ tests/     # lint
```

**One test is skipped by default and it is the most important one.**
`tests/test_marks_archive.py` proves S2 against the real WordPress
export, which is personal data and cannot live in a public repository —
so it runs only where that file is, and a green CI run says nothing
about it:

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

Sweep before any push. **The only expected hits are the pattern
lines below**, which name what they are looking for — anything else means
something leaked:

```
git grep -n -iE "charl|jordaan|18down|G-Y7N2F5SNY2|192\.168" -- .
```

And sweep the history too, not just the tree — that is the mistake this
whole section exists to prevent:

```
git grep -l -iE "charl|jordaan|18down" $(git rev-list --all) -- .
```

**That searches the FILES in every commit, and not the commit MESSAGES.**
`git grep` reads trees, so a name written into a subject line passes it
without a hit — and a message is published by the same push. Sweep those
separately:

```
git log --all --format='%H %s%n%b' | grep -inE "charl|jordaan|18down"
```

### A corrected `Layman:` cannot be put back the way it was

`roadmap_log` sets a bullet's `Layman:` at creation and has no verb to
change it afterwards — the trailer is composed from a store column that
`amend_body` cannot reach, even though `roadmap_query` shows the text
inside `body`. The only route is to declare `Layman:` at a line start in
the body, and **that route is one-way**: deleting the declaration does
not fall back to the column, it clears the field, and the render gate
refuses the write.

So this roadmap carries two styles — plain `Layman:` on the four bullets
corrected on 2026-08-25, bold on the other eighteen. Both parse. **Do
not try to reconcile them**; the attempt is what discovers the gate.
Filed as feedback for the Ants MCP maintainer.

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
- **Everything truthful, factual, verifiable.** Run the case that would
  refute a claim, not the one that confirms it. Two of the Marks spec's
  worst defects — a false security rationale, and an unanchored pattern
  that admitted a CSS payload into a `style` attribute — were found only
  by executing them.

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

### Overrides

Any place this project deliberately departs from a global standard goes
in `docs/standards/`, with the reason. If that directory is empty, there
are none.
