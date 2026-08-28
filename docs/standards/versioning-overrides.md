# Versioning overrides — Pressless

**Pressless follows the global standards unmodified.** This is not a
delta. It holds the two answers `~/.claude/standards/versioning.md`
refuses to supply — § 3's breaking surfaces and § 4's `1.0` exit
condition — which `~/.claude/standards/README.md` § The three cases pins
to this path.

## What would make this 1.0

**MAJOR stays 0 until every sign of success in `docs/discovery.md`
§ Signs it is working holds, and the entry file format is frozen.**

`versioning.md` § 4 requires that line in this file, so the copy is
deliberate: `ROADMAP.md` § Milestones states the same condition and
carries which item belongs to which milestone. Change them together —
nothing checks that they agree.

**The version numbers in `ROADMAP.md` § Milestones name goalposts, not
cut releases.** Decided by the user 2026-08-27; that section's opening
line already says a number there records which signs of success hold. A
release takes the level § 4 gives it, so a goalpost is reached at
whatever number the ladder has produced by then — which will not be the
number the goalpost is written as.

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
- **Where the Store keeps things.** That drafts sit outside the site
  folder, apart from published work, is already decided by
  `docs/design.md` § Where everything sits on disk, and S7 rests on it.
  PRESS-0005 has since chosen the entry half of the layout inside
  Pressless's own folder: `published/` and `drafts/`, one `.txt` per
  entry named by its slug. That is now a breaking surface rather than
  an open choice. PRESS-0006 still chooses the rest — the fixed pages,
  templates, page furniture, comments and photographs.
- **How an entry names a photograph** — not built yet (PRESS-0016), for
  the same reason.

### Setup state

**Nothing here may be lost to an upgrade.** Decided by the user
2026-08-27: an update that overwrites settings is not a good update
system. S5 asks that the publishing key be given exactly once, and an
upgrade that asks again has broken it. **What is protected is the
writer's values, not their spelling**: a change here that carries every
existing value forward takes nothing away, so it is not this breach.

- **`settings.json`.** `load()` refuses any version but its own and
  writes nothing, so a bump carrying no values forward leaves the writer
  unable to start rather than wiped. The repair is the old file, so an
  upgrade must not send him to setup over it — `load()` distinguishes a
  missing file from an unreadable one (INV-2) precisely so it can tell.
  A key that changes meaning under an unmoved version lands the same way.
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
| A surface here still has the shape described | Partly. `tests/test_settings.py::test_field_names_are_the_documented_set` pins the Settings field-name set. Nothing pins the version refusal this file names as a breach, and most other surfaces are not built. |
| This file and `ROADMAP.md` § Milestones agree on 1.0 | Nothing. § 4 requires the condition stated here, so the copy is deliberate and both have to be changed together. |

## Review loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-27 | 3, cold — genre pinned `standard`, packet carried the global `versioning.md` §§ 1-4, the standards index's three cases, ROADMAP § Milestones, the two ADRs cited, discovery's signs of success, `settings.py`'s version constant and `cut-release`'s level floor | 2 | 2 | 1 | n/a | **Five verified, five fixed; one dismissed.** **All three lanes independently found the same two defects**, which is the strongest signal in the run. The `settings.json` bullet named a key changing meaning under a static version as the breach, which by implication exempted a `FILE_VERSION` bump — and `load()` refuses every version but one, so a bump discards the whole file and asks for the publishing key again, breaking S5. The bullet now names both routes. And the 1.0 section said the promise was "not restated here" while restating it almost verbatim from § Milestones, with the What-checks-this table claiming divergence was impossible because the file points rather than copies; the copy is deleted, so all three statements are true. **The Q3 came from one lane and needed ADR-0001 to see**: unrecognised text is preserved byte-for-byte, so *adding* a mark restyles archive text that has been rendering literally — a conformer could not tell whether that was a MINOR or a PATCH. **One Q1 was found by resolving a lane's open question rather than by a lane**: the not-a-surface list rested on "each is a copy of something that can be got again", which is false of a log. Each entry now carries its own reason. **Dismissed:** a lane read the undo staging area as the only route back; `fetch_previous` re-fetches it from GitHub, so the exemption stands and only its stated ground was wrong. **Before dispatch, 1b found one defect of its own** — the entry-file bullet credited ADR-0001 with "one file per entry", which is the Store's rule. **And 4a step 3 caught an over-reach in a fix**: "no code reads the log" is not something `design.md` says or this run could run, narrowed to what § Logging supports. |
| 2 | 2026-08-27 | 3, cold — identical brief, packet rebuilt whole from disk and extended with `load()`'s executed refusal | 3 | 3 | 0 | n/a | **Six verified, six fixed; one surfaced.** **Half landed on loop 1's own fixes.** Loop 1 deleted the copied 1.0 promise and left a compressed copy under the words *not restated here*, which all three lanes found; the section now only points. Loop 1's own word *lose* was wrong about the mechanism — `load()` refuses and writes nothing, so a bad version leaves the writer unable to start rather than wiped, and sending him to setup would overwrite the one file that could be repaired. And the intro made any change to a listed surface breaking while § Setup state made only a lossy one breaking, so one migrated change had two version numbers; the section now says values, not spellings, are what is protected. **Two pre-existing Q1s.** The Store bullet said the draft layout was unchosen — `design.md` already fixes drafts outside the site folder and S7 rests on it, so a builder could have published unfinished work. And the checks table said nothing checks a surface's shape; a settings test does, while nothing pins the version refusal this file names as a breach. **Surfaced, not fixed:** the milestone numbers may be unreachable under § 4. |
| 3 | 2026-08-27 | 3, cold — identical brief, packet rebuilt whole from disk and extended with the executed `load()` results, the settings test inventory and the spec's INV-2 / INV-6 | 0 | 2 | 1 | n/a | **Three verified, two fixed, one already surfaced. Cap reached (3 for a standard), and it is a VIOLENT cap** — a majority of this loop's findings landed on text loops 1 and 2 wrote. **All three lanes found the same defect, and it is this run's own doing.** Loop 1 read the copied 1.0 condition as a contradiction and deleted the promise; loop 2 deleted the summary that was left; loop 3 found that `versioning.md` § 4 requires the line to be stated *here*, so the file had come to breach the rule it exists to satisfy — and § 4's next bullet calls a project with no such line one whose leading zero has gone inert. The condition is stated again, with the copy declared deliberate, which is the answer no earlier loop reached. **A Q3 from two lanes:** *the layout inside that folder* had the site folder as its nearer antecedent while meaning Pressless's own, and those two are opposite surfaces — one published in full, one never. Named explicitly. **Already surfaced before this loop, not fixed:** the milestone names may not be reachable levels under § 4, which is the user's decision and is filed as its own item. **Routing:** the document is small, so the cap is not a size signal; it is not re-gated as it stands, and what re-arms the gate is an authoring edit that changes direction. |
