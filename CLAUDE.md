# Pressless — instructions for Claude Code

## Where this project is

Nothing here records it, deliberately. Read it:

- **The version being worked towards** is the lowest version heading in
  `ROADMAP.md` still carrying open items. `Backlog — no version yet` and
  `Milestones` are not versions, wherever they sit in the file.
- **What is in flight** is the un-parked 🚧 bullet — `workflow.md` § 1
  owns what parked means, and what it means when every bullet is.
- **Where an item has got to** is whether a spec exists, whether tests
  fail, and what `git status` says. Never a recorded step number.
- **What is done** is `roadmap_query` with `status: "shipped"`.

A position written down is maintained by hand, and starts lying the
first time a session forgets it while still reading as authoritative.

## How work is done here

- **`~/.claude/workflow.md`** — the states, the gates, and what "done"
  means. Read in place. This project does not have its own copy.
- **`~/.claude/standards/`** — how to write code, tests, commits,
  documents, releases. Also read in place.

Neither is summarised here. A rule restated in two places is two rules
that will disagree.

## This project's own facts

### Stack

Python 3, the standard library's own web server for the Face, `Pillow` for
photographs, the operating system's keyring for the publishing key, and
PyInstaller to package one artefact per system. `docs/design.md` § The
stack, and what it rules out owns the choice and the reasoning.

### Build and test

`keyring` is reached only by `credentials.py` (PRESS-0002) and `Pillow`
only by `builder.py` (PRESS-0008). That is present state, not a cap.
The gate needs `pytest`,
`pytest-randomly` and `ruff` on top, and PyInstaller is the `packaging`
group beside those, never a runtime dependency (PRESS-0022).
`pip install -e '.[dev]'` installs what CI runs. `pyproject.toml` holds
the packaging and the pytest settings; `src/` is on the path through it,
so there is no install step beyond that one.

```bash
./scripts/local-ci.sh      # the gate: leak sweep, lint, suite
./scripts/local-ci.sh --docs   # documentation push: leak sweep alone
python3 -m pytest          # the suite alone
ruff check src/ tests/     # lint alone
```

**`scripts/local-ci.sh` is the gate, and `.github/workflows/ci.yml` calls
that same file** — it holds no checks of its own, so the two cannot
drift. The machine-wide hook discovers the script by name and runs it
over the commits being pushed. Whether anything is gated at all needs
`core.hooksPath` set, and `$ANTS_GLOBAL_HOOKS/pre-push` — defaulting to
`~/.claude/githooks/pre-push` — present and executable.
`ants.gate.docsGlob` only decides which checks run.

**Machine-local git config keys, and a fresh clone has none of them.**
The two below are the gate's. The rest are in `docs/working-here.md`,
listed at the end of this section.

```bash
git config core.hooksPath .githooks
git config ants.gate.docsGlob 'docs/*|*.md|LICENSE|*.txt|*.rst'
```

**`core.hooksPath` is what makes any hook fire at all.** Unset here and
machine-wide, git looks in `.git/hooks`, nothing runs, and nothing says
so. `.githooks/pre-push` only delegates to the machine-wide gate; where
that is absent it prints `NOTHING WAS CHECKED` and exits 0, so it warns
rather than blocks.

**`local-gate.md` § 6.2 makes the UNSET key the breach**: a shared hook
cannot know what a given pipeline reads, so it has to be told, and that
standard's own table says nothing announces the omission. The value
here is the hook's own fallback, so setting it alters no behaviour
today — set it anyway. The wide list is right because
`--docs` runs the leak sweep, which is the check a markdown edit in this
repository can actually breach, and no test reads a document as data.
Narrow it if either stops being true — and a narrowing reverts on any
clone where the key is unset.

**Read `docs/working-here.md` when the task comes up**, one section at
a time (`read_region` with `section=`). A comment or spec saying
"CLAUDE.md records" one of these notes means that file now:

- *Archive tests and a fresh clone's keys* — before running the archive
  tests or setting up a clone. They are the most important tests, and
  CI skips them.
- *Writing or changing tests* — before writing, changing or
  mutation-probing a test.
- *Releasing* — before signing or publishing a release.
- *Windows and browser checks* — before checking anything on the Windows
  box or in a browser.
- *Editing the roadmap* — before changing a `Layman:` line or a section
  intro.
- *Editing documents and building reviews* — before an exact-match edit
  to wrapped prose, or building a review packet.

### This repository is PUBLIC, and nothing here may name the writer

`milnet01/Pressless` on GitHub, MIT. The site it publishes belongs to a
real person; **this repository is about the app, and must not identify
him.** Write "the writer", never a name — in documents, roadmap bullets,
commit messages and code comments alike.

**What was removed on 2026-08-25, so it is not reintroduced:** his name,
his band, his domain, his GitHub account, his audience size, and a
hard-coded Google Analytics measurement id. The id belongs in Settings
by dependency rule 8, which is where the design already put it.

**The sibling generator's own source names him, and so does the
directory it sits in.** Decision 4 sends you there — `safe_slug` is the
one place a slug is resolved — and two archive tests load that
generator, so a session reading it is normal rather than exceptional.
Never write the name or the path into this repository, a commit message,
or a review packet a lane might quote back. Refer to it as the sibling
workspace and window the function bodies you need. The leak sweep does
not catch the directory name.

**Publishing a document is publishing its history.** De-personalising a
file changes nothing about what `git log` serves.

The gate sweeps what a push publishes: the tree, the files in every
commit, the commit messages, and every ref with its message, a tag's
included. `git grep` reads trees only, so a name in a subject line
passes a tree sweep. Where no hook runs the gate, run its leak step by
hand:

```
./scripts/local-ci.sh --docs
```

**The pattern lives in that script and nowhere else**, so a hand sweep
cannot drift from the gate. Strings that identify the writer but cannot
be spelled in a public repository sit in a machine-local key the script
reads (PRESS-0119). A checkout without it says so on every run:

```bash
git config ants.pressless.leakPatterns '<more patterns, pipe-separated>'
```

### How documents get written here

Standing instructions from the user.

- **A fix must serve the document's stated purpose.** Ask it of the
  *fix*, not just of the finding that prompted it: if the edit changes
  nothing anyone builds, it does not belong, however true it is.
- **Avoid counts and line numbers.** They go stale fast, and a stale
  number is worse than none because a reader edits *toward* it. Where a
  number is genuinely evidence, ship a test that prints it and cite the
  test.
- **Shorter prose.** Length is surface area: a reviewer finds defects in
  explanation that directs nothing. Rationale belongs in a sentence.
- **A review loop-log row is permanent the moment it is committed** —
  the global rule forbids editing a landed row, so a long one can never
  be shortened afterwards. Write it short the first time.
- **Everything truthful, factual, verifiable.** Run the case that would
  refute a claim, not the one that confirms it.

### Roadmap IDs

`PRESS-NNNN`, per `roadmap-format.md` § 3.5.1. **The roadmap is served
from the Ants roadmap store, not from `ROADMAP.md`** — the file is a
generated render and a hand edit to it is discarded by the next write.
Read it with `roadmap_query`, write it with `roadmap_log`. Commit
subjects are `<ID>: <description>`, per `commits.md`.

### Review history

This file is read in full by every session on every turn, so its
`review-contract` loop log is kept in
`docs/claude-md-review-2026-08-27.md` rather than here.

### Overrides

Any place this project deliberately departs from a global standard goes
in `docs/standards/`, with the reason. **`versioning-overrides.md` is
mostly not one of those** — it holds the answers `versioning.md` §§ 3
and 4 ask every project for. It also carries one departure: a release
takes the number of the milestone it completes, not § 4's PATCH. That
directory's own `README.md` sorts the kinds.

---

**How these rules came to say what they say is
[`docs/history/claude-md.md`](docs/history/claude-md.md)** — dated
corrections, superseded wording, and the argument that settled a rule.
Nothing there instructs anything; this file governs.
