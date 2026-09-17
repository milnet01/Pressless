# PRESS-0013 — review loop log

`review-contract` rows for `docs/specs/PRESS-0013-publish.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-17 | 3, cold — genre pinned `spec`; a new spec, whole document gated. Packet carried design rules 1, 9 and 10 and § Errors, windows on PRESS-0008, 0009, 0011, 0012, 0021 and 0022, and the Publisher, Credentials, Settings, Store, Builder, editor, Face, setup and launch code. GitHub, a browser and Windows declared unrunnable | 0 | 5 | 4 | 1 | **Ten verified, ten fixed, none dismissed.** Nothing let a caller tell an unforeseen upload failure from a build failure; the guard refused the deletes and undo design rule 9 exempts; a failed bin after a good publish read as a failure; a put-back could not be byte-identical through the Store; `save` and its caller could both take the lock; an ordinary draft published its `Replaces`; a capture could hold its lock through the upload; the failure reply pinned `draft` true; the re-fixtured launch test opened a browser; INV-1 named the wrong request. |
