# Pressless — instructions for Claude Code

## Where this project is

**State:** 5 — Building. **In flight:** nothing. Next: open review
findings, then the roadmap towards v0.5.0.

> Keep the block above true, and keep it to two facts — the state and
> what is in flight. Everything else is read off things that cannot lie:
> whether a spec exists, whether tests fail, what `git status` says,
> whether the roadmap bullet is 🚧. `roadmap_query` with
> `status: "shipped"` answers what is done. `python3 -m pytest` answers
> where the code stands. Do not record a step number.

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
only by `builder.py` (PRESS-0008). The gate needs `pytest`,
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
over the commits being pushed. Two things decide whether anything is
gated at all: `core.hooksPath` must be set, and
`~/.claude/githooks/pre-push` must be present and executable.
`ants.gate.docsGlob` only decides which checks run.

**Machine-local git config keys, and a fresh clone has none of them.**

```bash
git config core.hooksPath .githooks
git config ants.gate.docsGlob 'docs/*|*.md|LICENSE|*.txt|*.rst'
```

**`core.hooksPath` is what makes any hook fire at all.** Unset here and
machine-wide, git looks in `.git/hooks`, nothing runs, and nothing says
so. `.githooks/pre-push` only delegates to the machine-wide gate; where
that is absent it prints `NOTHING WAS CHECKED` and exits 0, so it warns
rather than blocks.

**`ants.gate.docsGlob`'s value here is the hook's own fallback**, so
setting it alters no behaviour today. The wide list is right because
`--docs` runs the leak sweep, which is the check a markdown edit in this
repository can actually breach, and no test reads a document as data.
Narrow it if either stops being true — and a narrowing reverts on any
clone where the key is unset.

**The archive test files are skipped in CI and they are the most
important ones.** `tests/test_marks_archive.py`,
`tests/test_store_archive.py` and `tests/test_store_extras_archive.py`
prove S2 against the real WordPress export, which is personal data and
cannot live in a public repository — so they run only where that file
is, and a green CI run says nothing about any of them. The gate points
`PRESSLESS_ARCHIVE` at a path held in a machine-local git config key:

```bash
git config ants.pressless.archive /path/to/wordpress-export.xml
```

**The first two need a second thing the third does not**, and it decides
what a green push proves. They load the sibling generator in a private
workspace, so they skip where no generator is found at all — which
includes the isolated checkout the pre-push hook builds, unless
`PRESSLESS_GENERATOR` is exported in the pushing shell. **Absence is the
only skip** (PRESS-0108): a generator that is present and will not load,
has been renamed, or is one of several candidates is a FAILURE naming
its cause. Set `PRESSLESS_GENERATOR` to pin which generator is read.
`test_store_extras_archive.py` keys comments by the export's own post id
and needs nothing but the export, so it DOES run at pre-push. Read the
skip reasons, not the exit code.

Or set it for one run:

```bash
PRESSLESS_ARCHIVE=<path to the WordPress export> python3 -m pytest
```

`tests/test_importer_archive.py` proves Import against the same export
(PRESS-0007). Its INV-6, INV-7 and INV-11 tests run the whole import, so
they also need the photograph originals, the live site's folder and
today's header and footer templates, each held the same way; its INV-2
and INV-3 tests need the sibling generator; INV-5's needs the export
alone:

```bash
git config ants.pressless.originals /path/to/originals
git config ants.pressless.liveSite /path/to/the/live/site
git config ants.pressless.templates /path/to/the/templates
```

`tests/test_builder_archive.py` proves the Builder against the live site
(PRESS-0008 INV-15). It imports the archive first, so it needs all of the
above, and it builds with the site's own name and address. Both identify
the writer, so they are machine-local values the gate exports as
`PRESSLESS_SITE_NAME` and `PRESSLESS_SITE_ADDRESS`. Read them off the live
site — its page titles and `sitemap.xml` — never from memory:

```bash
git config ants.pressless.siteName '<the name after the dash in a page title>'
git config ants.pressless.siteAddress '<the address sitemap.xml lists>'
```

**Two test results mean less than they look.** `test_marks_is_pure`
(INV-7) passes against *any* module that imports and calls nothing
forbidden — an empty file included — so it is evidence about imports and
calls, never about the code working. And with `marks.py` absent the suite
errors at *collection*, so no assertion runs at all: a run that says
nothing failed may have run nothing. Read the collected count, not the
exit code.

**`spec_lint` does not check a spec's test surfaces here, and says so
only in one field.** It resolves a surface only in a
`tests/features/<name>/` shape, which this project does not use, so on a
spec here it reports `surfaces_resolved: 0` beside `surfaces_checked:
true` and `ok`. `doc_citations` counts a citation `ok` when the cited
line exists, and `unchecked` when nothing on that line was compared. So
each `*Test:*` clause is resolved by hand before its item ships: the
named test must exist and must assert what the clause says.

**Probe after the code lands, and probe one mutation per route the
invariant's own *Breaks when* names.** `mutation_probe` refuses without a
green baseline, so it cannot run while the tests are red. Where a stub is
the only thing that exists, the probe needs a throwaway reference
implementation outside the tree.

**A `killed` verdict can be a false kill — read the run's exit code, not
the verdict word.** A mutation that leaves the file unparseable exits 2,
having run no test, and the envelope still reports `killed`. Exit 1 is not
proof either: a mutation naming something undefined fails every test on a
`NameError`, which says nothing about the rule it meant to break. Mutate
with values that run. **And a batch of kills does not mean the suite is
sound** — the survivors are where the evidence is.

**A test double written before the implementation encodes a guess about
the request shape, and the guess can make a faithful implementation
impossible to pass.** Give the double a by-URL answer for each read
rather than bending the code toward the fixture. Watch for it whenever a
double answers positionally: an implementation that legitimately adds one
request shifts every later answer onto the wrong step.

**A test that pins a name must hold its own copy of the name.**
`tests/test_settings.py` writes `"settings.json"` out rather than
importing `FILE_NAME` from the module under test. Share the literal and
INV-5 compares the module against itself, so `path_for` could name any
file and stay green. Do not tidy this into an import.

**Every `PublishError` subclass needs a Face sentence, a private one
included.** `tests/test_face.py::test_every_failure_type_has_a_sentence`
walks every subclass, so a private type used only for internal control
flow reddens the gate.

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

**A program started over SSH cannot reach the Windows credential vault.**
The packaged self-check answers `store: unanswered -- CredentialError`
there and `store: keyring Windows WinVaultKeyring` in the desktop session
(PRESS-0120). Run anything touching the keyring in the logged-on session:
a one-off `schtasks /Create ... /IT` then `/Run`, writing its output to a
file, and delete the task afterwards.

**A packaged run holds its output back when a script reads it through a
pipe.** Check the packaged program from a console, or with
`--self-check`, which prints and exits.

**A browser check runs through Playwright and the system Chrome.** The
Claude-in-Chrome extension is not connected on this machine; the
`playwright` Python package is installed and drives
`/usr/bin/google-chrome` headless. It says nothing about Windows, which
stays the Windows box's by-hand row.

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

### The roadmap carries two `Layman:` styles, and they stay

`roadmap_log op:"amend_field"` corrects a bullet's `Layman:` after
creation. It writes the store column, so it works wherever the render
composes that trailer — the bold-style bullets. Where the body declares
`Layman:` at a line start it refuses `field_shadowed_by_body` and names
`op:"amend_body"` as the route, because a declaration wins at render and
would be re-parsed back over the column.

**What stays one-way is the declaration itself**: deleting it does not
hand the column back, because the render gate refuses a bullet left
carrying no `Layman:` at all. **Leave the two styles as they are** —
reconciling them changes nothing anyone reads.

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

**A section intro is amendable.** `roadmap_log op:"set_intro"` replaces
one. A hand edit to `ROADMAP.md` is still discarded by the next render,
so the verb is the only route. **Still avoid a count, an id list or a
date in an intro** — the Milestones intro carries all three and every one
has gone stale (PRESS-0136). Amendable is not the same as maintained.

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
not one of those** — it holds the answers `versioning.md` §§ 3 and 4 ask
every project for, which is why a project following the global set
unmodified still writes it. That directory's own `README.md` sorts the
two: a departure is its kind 1, a deltas-only file.

---

**How these rules came to say what they say is
[`docs/history/claude-md.md`](docs/history/claude-md.md)** — dated
corrections, superseded wording, and the argument that settled a rule.
Nothing there instructs anything; this file governs.
