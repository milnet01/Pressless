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

The promise, as against the feature list: an entry file written by 1.0
stays readable by every later version. Before 1.0 the on-disk format of
ADR-0001 may still change; after it, S3 becomes a compatibility
guarantee rather than a design intention.

## The breaking surfaces

A change to anything below is breaking however small the diff: someone
who upgrades has something that used to work stop working. Inside `0.x`
that bumps the MINOR and resets the PATCH (`versioning.md` § 4).

### The writer's own files

- **The entry file's format** — its `Key: value` header, its body, and
  that every newline in the body is a line break (ADR-0001). Twelve
  years of archive, and the surface the 1.0 promise is about.
- **What a mark means.** Marks lives in the files *and* in the writer's
  hands. Change what a mark does and everything already written renders
  differently, with nothing to migrate: the file on disk never changed.
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

- **`settings.json`'s keys.** The file carries its own version and
  `load()` accepts one value, so a key that changes meaning while that
  number stays put is the breach this names.
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

Named because over-caution costs as much as carelessness. Each is a copy
of something that can be got again.

- **The Insights cache** — `docs/design.md` § State: deleting it costs a
  fresh fetch and nothing else.
- **The rolling log.**
- **The area a previous state is laid out in for undo**, emptied when
  that sequence ends.

## A surface nobody wrote down is still a surface

`versioning.md` § 3's rule, repeated rather than cited because this list
is young and most of what it names is not built. If the writer relies on
something and an upgrade stops it working, that release was breaking
whether or not this file mentions it.

## What checks this

| Claim | What checks it |
|---|---|
| A release's level matches what it changed | Nothing. `cut-release` does not choose the level, and its `Added`-forbids-a-PATCH floor is skipped while MAJOR is `0` — which is every release this file governs. |
| A surface here still has the shape described | Nothing. Most are not built yet. |
| This file and `ROADMAP.md` § Milestones agree on 1.0 | Nothing mechanical. It points rather than copies, which is what keeps them from disagreeing. |
