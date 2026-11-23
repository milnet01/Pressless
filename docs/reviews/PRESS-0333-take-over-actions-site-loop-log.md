# PRESS-0333 — review loop log

`review-contract` rows for `docs/specs/PRESS-0333-take-over-actions-site.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-01 | 2, cold, every lane every question, through `neutral-lane` | 2 | 4 | 6 | 2 | 14 findings, 13 verified and 13 fixed, 1 dismissed. **Capped by the user's budget of one round for a new spec (2026-09-29), not converged; the 13 fixes are read by no lane.** Unrunnable, so Q1 was out of scope there: GitHub's live behaviour. Three of the 13 came from settling a lane's open question or from verifying: `_Session._call` raises on `PUT pages`'s 204 (run), INV-15's name fails on Windows (run), and an address's landing is known only when the crawl ends. Dismissed: `takeover` importing `undo` makes a cycle, but a scratch copy imported in all five orders tried. Four open questions, none became a finding. New document, so both cap shares are unreadable; the findings are defects the draft held, a calm cap. |
| impl | 2026-11-03 | no reviewer dispatched; an amendment owes none | 0 | 0 | 0 | 0 | § 4.5 and INV-6: the § 7 hand check saw no build after the switch, so the old site stayed up. The switch now asks for a build last. |
| amend | 2026-11-08 | no reviewer dispatched; an amendment owes none | 0 | 0 | 0 | 0 | PRESS-0336: a branch build a workflow pushes to is taken over too. § 3 decision 8, §§ 4.1, 4.4, 4.5, 8, 9; INV-2 narrowed, INV-16 added. |
| pointer | 2026-11-15 | none — pointer from PRESS-0353 stage 1; no reviewer dispatched | 0 | 0 | 0 | 0 | § 4.3: the notice moved to Your site. |
| fix | 2026-11-17 | none: closing the 2026-11-16 reviews, no reviewer dispatched | - | - | - | - | PRESS-0385 amended § 4.2: a backslash in an address's path is read as a slash. No direction changed, so no gate. |
| amend-0379 | 2026-11-17 | none — no reviewer dispatched; an amendment | – | – | – | – | PRESS-0379: § 4.1 and step 6 — `takeover.done` is `takeover.unmark`; the test note names `fetch.addresses`. |
| impl | 2026-11-23 | none — amendment for PRESS-0446; no reviewer dispatched | 0 | 0 | 0 | 0 | § 4.5 step 3 asks for a build while the marker stands; step 6's marker that will not go is a notice. INV-8 names the build test. |
| impl | 2026-11-23 | none — amendment for PRESS-0446; no reviewer dispatched | 0 | 0 | 0 | 0 | § 4.5: `replace_link` is named `way_on`, since it also answers the takeover link. |
| impl | 2026-11-23 | none — amendment for PRESS-0448; no reviewer dispatched | 0 | 0 | 0 | 0 | § 4.2: `folder-left.json` is written before `folder.json`, through `write_folder_left`; § 4.3: `found_held` is named `read_held_or_fetch`. |
| impl | 2026-11-23 | none — amendment for PRESS-0454; no reviewer dispatched | 0 | 0 | 0 | 0 | § 4.2: a page's addresses are read against its `<base href>`; `_ASKED_MOST` caps the addresses asked; a file that cannot be rewritten is `left`. |
