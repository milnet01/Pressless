## Cold-eyes loop log

| Loop | Date | Reviewer | Q1 | Q2 | Q3 | Q4 | Findings | Fixed | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-16 | 2, cold, every lane every question, headless, one at a time | 2 | 0 | 1 | 2 | 5 | 5 | One round by the user's budget: not converged, and no lane has read the fixes; implementation is their reader. Found while building the packet and fixed before dispatch: `usage`'s question loads settings, so it takes the site too; the Sites screen needs `own` and the restart. Both lanes: setup reads and `google_setup` deletes keys under the fixed names, and INV-5's file store could not see a shared keyring. One lane: INV-6's recorder missed `face.serve`. Seven open questions, none became a finding. The armed change is the whole draft, so no own-fix or span share. |
| pointer | 2026-11-15 | none: pointer from PRESS-0353 stage 1; no reviewer dispatched | 0 | 0 | 0 | 0 | 0 | 0 | § 4.6: Sites is the bar's first link. |
| amend | 2026-11-17 | none: PRESS-0383 review fixes; no reviewer dispatched | 0 | 0 | 0 | 0 | 0 | 0 | § 4.1: `made` in sites.json, and an unreadable file is left alone; § 4.2 gains `starter.FILLED`. |
| pointer | 2026-11-17 | none: pointer from PRESS-0381; no reviewer dispatched | 0 | 0 | 0 | 0 | 0 | 0 | § 4.4: `_serve_once` is named without its arguments, since it now also takes the process's `updating.Updates`. |
