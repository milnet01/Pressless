# Cold-eyes loop log

| Loop | Date | Reviewer | Q1 | Q2 | Q3 | Q4 | Findings | Fixed | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-14 | 2 cold lanes (spec) | 2 | 1 | 0 | 0 | 3 verified, 0 dismissed | 3 | One round, the user's budget. Loop 2 not run, so these fixes were not re-read cold; implementation is the next reader. Findings: a §4.4-vs-§4.1 contradiction on where the `script` piece's `<script>` is emitted (Q2); an imprecise `pieces.js`-vs-`stylesheets` mechanism (Q1); the sandbox misattributed to `preview_html` (Q1). Also corrected a false "tenth new kind" count by deletion (Phase 3 carve-out, out of tally). |
| amend | 2026-11-17 | none: PRESS-0374 review fixes; no reviewer dispatched | 0 | 0 | 0 | 0 | 0 | 0 | § 4.1: `top` has a `label`; a countdown's end gains the computer's offset when the editor saves it. |
| amend | 2026-11-23 | none: PRESS-0443 review fixes; no reviewer dispatched | 0 | 0 | 0 | 0 | 0 | 0 | § 4.1: a countdown's end in a year with no known offset is kept as typed. |
