# PRESS-0235 — review loop log

`review-contract` rows for `docs/specs/PRESS-0235-press-status.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-10-07 | 2 | 0 | 1 | 4 | 1 | 6 findings, 6 verified / 0 dismissed, all fixed: busy reply's fields and `said`, `end` only after a won `start`, `forget` idle mid-press, empty `said`, failure on a page opened after a press, INV-4's raise. Lanes run one after the other, each holding every question; 4 open questions resolved clean. One round, the user's budget: fixes read by no lane. |
| 2 | 2026-10-12 | 2, cold — genre pinned `spec`; gate armed by PRESS-0246 (`8a38318`): decision 6, `POST /press/forget`, INV-8. Each lane held all four questions | 0 | 0 | 1 | 0 | **One verified, fixed; found by both lanes. One round by the budget, not converged; the fix was read by no lane.** The OK marker had no name, and "a box showing a press's failure" left the starting page's box, drawn before any outcome, unmarked; it is now `data-forget` on the three press-row failure boxes. Dismissed: that `_save_sequence` is first run only (`POST /setup` is the Settings page too). Inside the gated span: 1 of 1. |
