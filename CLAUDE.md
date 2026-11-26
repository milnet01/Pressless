# Pressless — instructions for Claude Code

## Where this project is

Read it; nothing here records it, because a written position goes stale:

- **The version being worked towards** is the lowest version heading in
  `ROADMAP.md` still carrying open items. `Done outside a version` and
  `Milestones` are not versions. Every open item goes into a version,
  never a backlog (user, 2026-11-03).
- **What is in flight** is the un-parked 🚧 bullet (`workflow.md` § 1).
- **Where an item has got to** is whether a spec exists, whether tests
  fail, and what `git status` says.
- **What is done** is `roadmap_query` with `status: "shipped"`.

`~/.claude/workflow.md` and `~/.claude/standards/` are read in place;
this project has no copies.

## This project's own facts

### Stack

Python 3, the standard library's web server for the Face, `Pillow` for
photographs, the OS keyring for the publishing key, PyInstaller for one
artefact per system. `docs/design.md` § The stack, and what it rules out
owns the choice.

### Build and test

`keyring` is reached only by `credentials.py` (PRESS-0002), `jeepney`
only by `_tray_linux.py`, and `Pillow` only by `builder.py` (PRESS-0008)
and `_tray_linux.py` (PRESS-0204). That is present state, not a cap.
PyInstaller is the `packaging` group, never a runtime dependency
(PRESS-0022). `pip install -e '.[dev]'` installs what CI runs; `src/` is
on the path through `pyproject.toml`.

```bash
./scripts/local-ci.sh             # the gate: leak sweep, lint, suite
./scripts/local-ci.sh --docs      # documentation push: leak sweep alone
./scripts/local-ci.sh --release   # the gate on the release lock's versions
.venv/bin/python -m pytest        # the suite alone
.venv/bin/python -m ruff check src/ tests/   # lint alone
```

**A gate run brings the gitignored `.venv` up to what a fresh install
resolves**, so use `.venv` for a suite or lint run alone.
`.github/workflows/ci.yml` calls `scripts/local-ci.sh` and holds no
checks of its own.

**A fresh clone runs `./scripts/setup-hooks.sh` once**, to set
`core.hooksPath`; without it no hook fires and nothing says so.
`.githooks/pre-push` delegates to the machine-wide gate, and prints
`NOTHING WAS CHECKED` where that is absent.

**`ants.gate.docsGlob` is committed in `.ants/gate.conf`** (`local-gate.md`
§ 6.2). It lists only files no test reads, because `--docs` runs the leak
sweep alone. So `CHANGELOG.md` and `*.txt` stay out (a test reads
`CHANGELOG.md` and the manual's `en.txt`; the release build reads
`packaging/release-requirements.txt`; PRESS-0362). Narrow it if that stops
being true.

**Read `docs/working-here.md` one section at a time** (`read_region` with
`section=`), when its task comes up. A comment saying "CLAUDE.md records"
one of these means that file now:

- *Archive tests and a fresh clone's keys* — running the archive tests
  (the most important; CI skips them) or setting up a clone.
- *Writing or changing tests* — writing, changing or mutation-probing one.
- *Releasing* — signing or publishing a release.
- *Registering the Google client* — `google_signin.CLIENT_ID` or its setup.
- *Registering the GitHub App* — `github_signin.CLIENT_ID`, `APP_SLUG`.
- *Registering the usage-report property* — the usage key or property.
- *The log relay* — `relay/`, `sendlog.RELAY` or the relay's GitHub App.
- *Windows and browser checks* — the Windows box or a browser.
- *Remaking the manual's pictures and videos* — after a screen changes.
- *Editing the roadmap* — a `Layman:` line or a section intro.
- *Editing documents and building reviews* — an exact-match edit to
  wrapped prose, or a review packet.

### This repository is PUBLIC, and nothing here may name the writer

`milnet01/Pressless` on GitHub, MIT. The site it publishes belongs to a
real person; this repository is about the app. **Write "the writer",
never a name** — in documents, roadmap bullets, commits and comments.

**Never reintroduce** (removed 2026-08-25): his name, his band, his
domain, his GitHub account, his audience size, or a hard-coded Google
Analytics measurement id (it belongs in Settings).

**The sibling generator's source names him, and so does its directory.**
Reading it is normal: Decision 4 sends you there for `safe_slug`, and two
archive tests load it. Never write the name or path into this repository,
a commit, or a review packet. Call it the sibling workspace. The leak
sweep does not catch the directory name.

**Publishing a document publishes its history**: `git log` still serves
what a later edit removed.

**The gate's leak sweep covers everything a push publishes** — tree,
every commit's files, messages, identities and paths, and every ref. It
prints where a hit is, never its text. Where no hook runs, run
`./scripts/local-ci.sh --docs` by hand. **The pattern lives only in that
script**, plus strings that cannot be spelled here, in a machine-local
key (PRESS-0119): `git config ants.pressless.leakPatterns '<patterns>'`.

### How documents get written here

**A number that is evidence is printed by a test, and the test is cited**;
a number in prose goes stale, and a reader edits toward it. **Ask of each fix, not only each finding, whether it serves the
document's stated purpose**; an edit that changes nothing anyone builds
does not belong. **A committed review loop-log row is permanent**, so
write it short the first time.

### Roadmap IDs

`PRESS-NNNN` (`roadmap-format.md` § 3.5.1). **The roadmap is the Ants
store; `ROADMAP.md` is a render**, and a hand edit is discarded. Read
with `roadmap_query`, write with `roadmap_log`. Commit subjects are
`<ID>: <description>`.

### Overrides

Departures from a global standard go in `docs/standards/`, with the
reason; its `README.md` sorts the kinds. `versioning-overrides.md`
mostly answers `versioning.md` §§ 3 and 4; its one departure is that a
release takes the number of the milestone it completes.

---

This file's review loop log is `docs/claude-md-review-2026-08-27.md`;
how its rules came to say what they say is `docs/history/claude-md.md`.
