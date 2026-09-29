# PRESS-0004 — Marks: history

How `docs/specs/PRESS-0004-marks.md` came to say what it says. Nothing
here instructs anything; the spec governs.

## Status history, moved out of the spec 2026-09-29

**Status:** accepted (2026-08-25), amended three times the same day by
implementation. Writing the tests showed INV-4 and INV-5 agreed only because
the archive happens to contain nothing that separates them; §2, §4.6, §5 and
§7 now state the difference and the test checks it. Writing the code then
showed §4.5's two adjacency clauses rejected §4.2's own photo syntax, and
that nothing said where an argument ends; §4.5 now scopes the clauses to a
`wrap` and names the terminator. A mutation probe then showed §4.5's own
gloss *"so `***…***` opens nothing"* was false of the rule it glossed, and
that INV-2's fixtures measure neither adjacency clause; §4.5 and INV-2 now
say what the rule does and which two inputs separate it. No re-gate for any
of the three: the document reached its cold-eyes cap, and this is the
implementation finding the tail that rule 14 says it should. Amended
again 2026-09-06 (PRESS-0059, PRESS-0055): §5 claimed the escapes were
the trust boundary's whole defence, which was never true of the
photograph name — it reaches `photo_src` before any escaping — so §4.2
now pins that name's grammar; and a photograph's caption is now its
description. Both change what a conformer builds, so this one was gated,
reaching its cap with an empty tail on 2026-09-06. Amended again
2026-09-11 (PRESS-0007): §3 decision 4 adds the link and quote marks,
with INV-11 and INV-12. That changes what is built, so it is gated.
Amended 2026-09-27 (PRESS-0164): §4.2's photograph name refuses what
PRESS-0006 decision 10 now refuses, a write-back of PRESS-0006 loop 4.
