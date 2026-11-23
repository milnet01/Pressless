# PRESS-0241 — review loop log

`review-contract` rows for `docs/specs/PRESS-0241-more-languages.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-11-18 | 2 | 1 | 5 | 4 | 2 | 12 findings, 11 verified / 1 dismissed (sample pages: local detail). All 11 fixed; one false § 6 clause deleted outside the tally. Cap of 1 reached, calm: no earlier loop's text to land on. Fixes read by no lane. |
| 1-check | 2026-11-18 | none — no reviewer dispatched | 1 | 0 | 0 | 0 | The return check found a loop-1 fix false: a bring-in does write an identity (`_write_all`). § 4.4 corrected; the behaviour is unchanged. |
| impl | 2026-11-20 | none — implementation, no reviewer dispatched | 0 | 0 | 0 | 0 | Machinery built. Choices inside the spec: English is recorded as `""`; `date.medium` keeps the two-digit day; `translations.py stamp` stamps plain strings only, so a stale pair stays stale. |
| amend | 2026-11-23 | none — no reviewer dispatched | 0 | 0 | 0 | 0 | PRESS-0456: § 4.2 and INV-8 — a one form writes `{count}`, never "1"; INV-8 gains the test that holds it. |
| amend | 2026-11-23 | none — no reviewer dispatched | 0 | 0 | 0 | 0 | PRESS-0456: § 4.3 and INV-5 — `computer` takes LANGUAGE's first language Pressless has, and a code may have three letters. |
