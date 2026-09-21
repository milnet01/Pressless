# PRESS-0015 — review loop log

`review-contract` rows for `docs/specs/PRESS-0015-undo.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-21 | 3, cold — genre pinned `spec`; first gate on a new document. Packet carried the design's undo and dependency rules, the sibling specs this one cites, `publishing.py` whole, and windows on editor, store, publisher, builder and face. GitHub, Windows, the keyring and a browser declared unrunnable | 1 | 3 | 4 | 1 | **Nine verified, nine fixed, none dismissed.** All three lanes found INV-6's equality clause impossible: `store.Entry` is frozen and carries `slug`, so a kept draft under a free address cannot read back equal. Two lanes each found three more — `Undone` had no field for the count the summary promised; three passages disagreed on whether a failed undo reloads; decision 9 denied the Undo button § 4.6 requires. One lane found `copy_kept` unreachable, since undo publishes with `entry=None`. One lane found nothing calls `undo.register`. Both lanes' `capture` question was a real Q3: PRESS-0013's meaning *unchanged* would wrap the fetch in a process-wide lock. The comments rule contradicts `design.md`; that is a decision on a gated document, so § 11 files it rather than carrying it in. **One collision this run created, caught by the fix pass's own re-read rather than by a lane:** the reversal text forbade binning, which INV-10 needs for the kept draft. **Resolved clean, not counted:** `free_address` cannot loop on length, and `write_comments` exists — a packet gap, not a defect. |
