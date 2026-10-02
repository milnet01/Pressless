# PRESS-0214 — review loop log

`review-contract` rows for `docs/specs/PRESS-0214-journal-switch.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-10-02 | 2, cold, run one after the other; every lane held every question — genre pinned `spec`; packet carried the design's journal and on-disk passages, PRESS-0008 §§ 4.2, 4.7, 4.9, PRESS-0013 § 4.3, PRESS-0015 § 4.4 and the Builder, Store, publishing, undo, editor and page-editor windows | 0 | 3 | 1 | 0 | **Four verified, four fixed, none dismissed. One loop only, by the user's budget for a new spec: not converged; the fixes are read by no lane.** Both lanes: undo kept an "off" file over a fetched state with none, though absence means on — a fetched state without the file now resets it; INV-3's byte-identical claim ignored the copied options file; undo needed whole-object `read_options` and `write_options`. One lane: the design's "the menu offers none" met a hand-made menu until PRESS-0195 — § 4.5 now says so, and the design carries a pointer. Four open questions resolved clean. |
