# Standards for Pressless

**The standards are global and are read in place**, at
`~/.claude/standards/`. There is exactly one copy of each, shared by
every project on this machine. Nothing copies them here.

`~/.claude/standards/README.md` is the index and owns the three cases: a
project follows the global set, overrides one with a deltas-only file, or
owns a standard outright.

## This directory

Three things belong here, and nothing else:

1. **Overrides** — a deltas-only file naming where this project departs
   from a global standard, and why.
2. **Answers a global standard asks each project for.**
   `versioning-overrides.md` is the one, and it is not a delta: § 3 and
   § 4 of the global `versioning.md` refuse to supply this project's
   breaking surfaces and its `1.0` exit condition, and pin both to that
   path. `~/.claude/standards/README.md` § The three cases carries the
   carve-out.
3. **Standards this project owns outright** — a rule that is genuinely
   about this project and has no global equivalent.

**Pressless follows the global set unmodified**, and the file named
above does not change that. Nothing else here departs from a global
standard; if anything ever does, it goes in a file of kind 1 with its
reason.

**A copy of a global standard does not belong here.** Two copies are two
standards that will disagree, and the one nobody is looking at will be
the one being followed.
