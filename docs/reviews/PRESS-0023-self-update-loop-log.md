# PRESS-0023 — review loop log

`review-contract` rows for `docs/specs/PRESS-0023-self-update.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-25 | 3, cold; every lane held every question | 1 | 3 | 7 | 2 | Thirteen verified, thirteen fixed, none dismissed. All three lanes found the download seam buffering a whole body, the check's failed step with no route to the log, and the list page with no seam for the offer. Also fixed: the Linux spawn failure, update.log's word order, the lock's unfalsifiable clause, the key literal, zip directory entries (checked against the v0.1.2 zip), and a .sig that can carry two keys. Windows helper runtime declared unrunnable. Lanes saw the draft's commit subject. |
| 2 | 2026-09-25 | 3, cold; every lane held every question | 1 | 2 | 4 | 4 | Eleven verified, eleven fixed; one of them (a stale Pressless.old blocking later updates) found while verifying. All three lanes found the Windows script writing neither swapped nor started. Five of eleven landed on loop 1's text; the document is new, so the share is unreadable as a verdict, and the five were unnamed seams rather than repairs of repairs. Cap reached; empty tail; routed to implementation. Lanes saw both commit subjects. |
| 3 | 2026-09-27 | 2, cold — genre pinned `spec`; gate armed by PRESS-0174 (`953b386`): `DiskFull`, § 4.6 and § 4.10 rows, INV-21. Packet carried CPython's `errmap.h` fact and the Linux `winerror` constructor fact, both executed. Windows declared unrunnable. Each lane held all four questions | 0 | 0 | 1 | 1 | **Two verified, two fixed.** Both lanes: the unpack row said "the same `errno` test", which could drop `winerror` 39 on the one path that runs only on Windows. One lane: `OSError(ENOSPC)` with one argument leaves `errno` as `None` (executed), so INV-21 now builds its doubles with two and adds a creation case. One round by the amendment budget; not converged. |
