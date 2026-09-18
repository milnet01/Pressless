# PRESS-0127 — review loop log

`review-contract` rows for `docs/specs/PRESS-0127-empty-repository.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-18 | 3, cold — genre pinned `spec`; packet carried `publisher.py` and `setup.py` windows, the Face's sentences, the test double, ADR-0002, PRESS-0009 §4.1–§4.3, INV-2–5, INV-9, §6 and PRESS-0021 §4.6–§4.9, §6. GitHub's live API unrunnable | 4 | 1 | 0 | 0 | **Five verified, five fixed, none dismissed. First gate on this document.** One found building the packet: §7 misdescribed the test double. Two lanes: §2 claimed `commits/main` was measured at 409, when only `Conflict` was recorded — §7 now owes a by-hand check. Two lanes: the not-a-directory refusal is `publish`'s, not `_local_files`'. One lane: an empty answer mapped to `RemoteStateMissing` would be caught with setup's 404. One open question resolved to a defect: §11 named a PRESS-0009 row that does not exist. Five open questions resolved clean. |
