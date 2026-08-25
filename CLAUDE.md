# Pressless — instructions for Claude Code

## Where this project is

**State:** 4 — Between items. The design was broken into `PRESS-NNNN`
items on 2026-08-25 and `check-queue` was run: every sign S1–S11 is named
by at least one item, and every item carries a `Blocked-by:` line.
**Next:** pick an item and build it (`~/.claude/workflow.md` § 6).
`PRESS-0001` and `PRESS-0004` are the two with no blockers.
**In flight:** nothing.

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

(Filled once the stack exists.)

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

Sweep before any push — **expect exactly one hit, this line itself**,
because the pattern names what it is looking for. Two or more hits means
something leaked:

```
git grep -n -iE "charl|jordaan|18down|G-Y7N2F5SNY2|192\.168" -- .
```

And sweep the history too, not just the tree — that is the mistake this
whole section exists to prevent:

```
git grep -l -iE "charl|jordaan|18down" $(git rev-list --all) -- .
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
