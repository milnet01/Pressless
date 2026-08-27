# Versioning overrides — Pressless

**Pressless follows the global standards unmodified.** This is not a
delta. It holds the two answers `~/.claude/standards/versioning.md`
refuses to supply — § 3's breaking surfaces and § 4's `1.0` exit
condition — which `~/.claude/standards/README.md` § The three cases pins
to this path.

## What would make this 1.0

`ROADMAP.md` § Milestones owns it, agreed with the user 2026-08-25:
every sign of success holds, and the entry file format is frozen. Not
restated here — a rule stated twice is two rules that will disagree.

## The breaking surfaces

A change to anything below is breaking however small the diff: someone
who upgrades has something that used to work stop working. Inside `0.x`
that bumps the MINOR and resets the PATCH (`versioning.md` § 4).

### The writer's own files

- **The entry file's format** — its `Key: value` header, its body, and
  that every newline in the body is a line break (ADR-0001). Twelve
  years of archive, and the surface the 1.0 promise is about.
- **What a mark means, and which marks exist.** Marks lives in the files
  *and* in the writer's hands. Change what a mark does and everything
  already written renders differently, with nothing to migrate: the file
  on disk never changed. **Adding** a mark is the same breach by the
  other route — ADR-0001 preserves anything the parser does not
  recognise byte-for-byte, so a new mark restyles text that has been
  rendering literally for years.
- **Where the Store keeps things** — the layout separating drafts from
  published. Not chosen yet (PRESS-0005, PRESS-0006), and listed now
  because the choice is harder to unmake than to make.
- **How an entry names a photograph** — not built yet (PRESS-0016), for
  the same reason.

### Setup state

**Nothing here may be lost to an upgrade.** Decided by the user
2026-08-27: an update that overwrites settings is not a good update
system. S5 asks that the publishing key be given exactly once, and an
upgrade that asks again has broken it.

- **`settings.json`.** `load()` accepts one version and refuses every
  other, so two routes lose the writer's settings and both are this
  breach: a key that changes meaning while the version stays put, and a
  version bump with nothing that carries the old file's values forward.
- **The keyring account names.** Change one and the secret reads as
  absent, so setup asks for what was already given.
- **The credential file's shape**, where there is no keyring (ADR-0003)
  — the same consequence by the other route.

### The live site

- **A published page's address.** Decided by the user 2026-08-27.
  Inbound links, search results and anything already shared point at
  pages that exist. Pressless cannot tell that an address it changed was
  in use, so the first report comes from a reader.

## What is deliberately not a surface

Named because over-caution costs as much as carelessness.
`docs/design.md` § Where everything sits on disk names all three, and
each is exempt for its own reason rather than a shared one.

- **The Insights cache** — `docs/design.md` § State: deleting it costs a
  fresh fetch and nothing else.
- **The rolling log** — `docs/design.md` § Logging makes it plain
  English for the writer to read, so nothing binds to its shape.
- **The area a previous state is laid out in for undo**, emptied when
  that sequence ends. What it holds came from GitHub and can be fetched
  again, so losing it costs a re-fetch rather than the undo.

## A surface nobody wrote down is still a surface

`versioning.md` § 3's rule, repeated rather than cited because this list
is young and most of what it names is not built. If the writer relies on
something and an upgrade stops it working, that release was breaking
whether or not this file mentions it.

## What checks this

| Claim | What checks it |
|---|---|
| A release's level matches what it changed | Nothing. `cut-release` does not choose the level, and its `Added`-forbids-a-PATCH floor is skipped while MAJOR is `0`. |
| A surface here still has the shape described | Nothing. Most are not built yet. |
| This file and `ROADMAP.md` § Milestones agree on 1.0 | Nothing mechanical. It points rather than copies, which is what keeps them from disagreeing. |

## Review loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-27 | 3, cold — genre pinned `standard`, packet carried the global `versioning.md` §§ 1-4, the standards index's three cases, ROADMAP § Milestones, the two ADRs cited, discovery's signs of success, `settings.py`'s version constant and `cut-release`'s level floor | 2 | 2 | 1 | n/a | **Five verified, five fixed; one dismissed.** **All three lanes independently found the same two defects**, which is the strongest signal in the run. The `settings.json` bullet named a key changing meaning under a static version as the breach, which by implication exempted a `FILE_VERSION` bump — and `load()` refuses every version but one, so a bump discards the whole file and asks for the publishing key again, breaking S5. The bullet now names both routes. And the 1.0 section said the promise was "not restated here" while restating it almost verbatim from § Milestones, with the What-checks-this table claiming divergence was impossible because the file points rather than copies; the copy is deleted, so all three statements are true. **The Q3 came from one lane and needed ADR-0001 to see**: unrecognised text is preserved byte-for-byte, so *adding* a mark restyles archive text that has been rendering literally — a conformer could not tell whether that was a MINOR or a PATCH. **One Q1 was found by resolving a lane's open question rather than by a lane**: the not-a-surface list rested on "each is a copy of something that can be got again", which is false of a log. Each entry now carries its own reason. **Dismissed:** a lane read the undo staging area as the only route back; `fetch_previous` re-fetches it from GitHub, so the exemption stands and only its stated ground was wrong. **Before dispatch, 1b found one defect of its own** — the entry-file bullet credited ADR-0001 with "one file per entry", which is the Store's rule. **And 4a step 3 caught an over-reach in a fix**: "no code reads the log" is not something `design.md` says or this run could run, narrowed to what § Logging supports. |
