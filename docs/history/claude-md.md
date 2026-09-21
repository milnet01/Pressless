# CLAUDE.md — how its rules came to say what they say

The project's instruction file states what is true now. Why a rule says
what it says is here, so a session reaches the instruction without
reading its pedigree first. Nothing here instructs anything. Where this
file and `CLAUDE.md` disagree, `CLAUDE.md` governs.

Moved out of `CLAUDE.md` on 2026-09-21 (PRESS-0137). Sections match its
headings.

## Where this project is

The section recorded a state number, what was in flight, and the version
being worked towards, until 2026-09-21. What is done was deliberately
never listed: `roadmap_query` with `status: "shipped"` answers it, and a
list kept by hand goes stale the first time a session forgets it — this
one had, twice. The recorded position went the same way, and for the
same reason: it said v0.3.0 for two milestones after v0.3.0 shipped.

A recorded step number starts lying the first time a session forgets to
update it, and still reads as authoritative. So position inside an item
is read off things that cannot lie rather than recorded.

## Build and test

`keyring` and `Pillow` were the whole of the runtime dependencies when
the list was written. The qualifier saying the reach statement is not a
cap belongs in `CLAUDE.md`, where it instructs someone; moving it here
on 2026-09-21 left the sentence reading as a possible architectural
rule, and the cold read that day found it.

The rule that an UNSET `ants.gate.docsGlob` is the breach was moved here
on 2026-09-21 and put straight back. Without it `CLAUDE.md` said only
that setting the key alters no behaviour, which reads as permission to
skip it — and `local-gate.md` § 6.2's own table says nothing announces
the omission, so the breach would never have surfaced. Three cold lanes
found it independently.

**Absence is the only skip** for the generator-loading archive tests
(PRESS-0108). A skip reporting every cause as absence could stop the S2
round trip silently, so a generator that is present and will not load,
has been renamed, or is one of several candidates is a failure naming
its cause.

**Proving a test red before the code exists takes a stub.** `mutation_probe`
refuses without a green baseline, so it cannot run while the tests are
red — the two checks never overlap. What worked: red the tests against a
stub that declares the surface and raises `NotImplementedError`, then
write a throwaway reference implementation outside the tree, probe that,
and delete it. PRESS-0001's INV-7 test passed its own red run and still
could not see the breach it names; only the probe found that.

**The throwaway is not needed where the real implementation is next.**
PRESS-0009 probed the shipped module instead, immediately after
`write-code`, and that is better evidence. It found INV-5's "never
forced" clause unfalsifiable: the clause stripped spaces out of the
request body and then searched it for a needle carrying a space of its
own, so no body could ever match it, forced or not. The red run passed
against that and could not have seen it.

**A `killed` verdict can be a false kill.** Met 2026-09-08 on
PRESS-0003: an `if True:` substitution orphaned an `except`, the
mutation exited 2 having run no test, and the envelope still reported
`killed` — so it proved nothing and read exactly like the ones that
proved something. Exit 1 is not proof either: met 2026-09-17 on
PRESS-0021, a mutation naming something undefined failed every test on a
`NameError`, which says nothing about the rule it meant to break. The
same run's honest survivors were three clauses no test could see, two of
them invariants the spec argued for at length and covered with nothing.

**A test double written before the implementation encodes a guess about
the request shape.** `tests/test_publisher.py`'s first draft answered
every read with one generic response. The Publisher makes three reads
whose answers have nothing in common — the repository names its default
branch, the head commit names its tree, then the tree listing — so no
correct implementation could satisfy it.

**Every `PublishError` subclass needs a Face sentence.** PRESS-0127 met
this with a private type used only for internal control flow, and
signalled "empty repository" with a `read(..., empty_ok=True)` returning
`None` instead. Found 2026-09-18.

**A packaged run holds its output back when a script reads it through a
pipe.** Measured 2026-09-17 on a frozen Linux build: the report appears
at once in a console and not at all to a reader capturing stdout, so a
scripted double-click check looks like a hang rather than a failure.

**The browser check runs through Playwright** because the
Claude-in-Chrome extension is not connected on this machine (tried
2026-09-17). That is how PRESS-0012's page script, its preview and the
policy that keeps a followed link inside the frame were checked.

## This repository is PUBLIC

The sibling generator's docstrings carry the writer's name and the
sibling directory is named after him, so the path is an identifier even
when the code is not. Found 2026-09-04 while building a
`review-contract` packet: the window stopped one line above the name by
luck, not design. The leak sweep would not have caught the directory
name.

The pre-public history was archived off-repo before the first push
rather than published.

Strings that identify the writer but cannot be spelled in a public
repository moved to a machine-local key the sweep script reads
(PRESS-0119).

## The roadmap's two `Layman:` styles

`roadmap_log op:"amend_field"` (ANTS-4667) writes the store column, so it
works on the bold-style bullets. Both branches verified 2026-08-27.

Deleting a `Layman:` declaration does not hand the column back. Measured
2026-08-27 — `amend_body` removing one is refused by the render gate with
`render_gate_unmet`, because the bullet would be left carrying none. So
the plain-style bullets corrected on 2026-08-25 and the bold-style rest
go on parsing by different routes, and reconciling them changes nothing
anyone reads.

## How documents get written here

Standing instructions from the user, given 2026-08-25 while the Marks
spec was being gated. They changed the outcome of that gate.

- Asking whether a fix serves the document's purpose removed a block of
  measured counts from the Marks spec after those counts had already
  survived two review loops.
- The Marks spec's archive figures live in its conformance run, not in
  its prose.
- Two of that spec's worst defects — a false security rationale, and an
  unanchored pattern that admitted a CSS payload into a `style`
  attribute — were found only by executing them.

## A section intro is amendable

It was not when the Milestones intro was written. `roadmap_log
op:"set_intro"` (ANTS-4949) was verified here 2026-09-21 with a dry run
against `milestones`, which reported `replaced_intro_chars: 1981`.

## Roadmap IDs

The prefix changed from `DOWN-` on 2026-08-17, before any id was
allocated: this app is deliberately not named after its first user, and
a prefix naming him would have said the opposite in every commit
subject.

The roadmap migrated to the Ants roadmap store on 2026-08-25, which is
why `ROADMAP.md` is a generated render.
