# Pressless — instructions for Claude Code

## Where this project is

**State:** 5 — Building `PRESS-0004` (Marks). Its spec is accepted and
its tests are written and failing; `src/pressless/marks.py` does not
exist yet.
**Next:** write that module until the suite is green. `PRESS-0001` is the
other unblocked item.
**In flight:** `PRESS-0004`, 🚧 on the roadmap. Run `python3 -m pytest`
to see where it stands — the tests are the position, not this line.

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

(Decided in design — `docs/design.md`. Until then, undecided.)

### Build and test

Python, no dependencies beyond the standard library and `pytest`.
`pyproject.toml` holds the packaging and the pytest settings; `src/` is
on the path through it, so no install step is needed.

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

Sweep before any push. **The only expected hits are the two pattern
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
