# PRESS-0213 — review loop log

`review-contract` rows for `docs/specs/PRESS-0213-site-identity.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-10-03 | 2, cold, every lane every question, headless; Windows and GitHub unrunnable | 1 | 4 | 0 | 0 | Five verified, five fixed, none dismissed. One round by the user's budget: not converged, and no lane has read the fixes. Both lanes: the launch read is in `_serve_held`, not `main`. Others: undo could not keep the extra keys `write_identity` promised (promise deleted); every save dropping `site_name` lost a name after a failed carry-across (now only the carry retires it); a refused settings file reported a moved name as unmoved; PRESS-0126 § 4.3 also needed a pointer. Two of the five came from lanes' open questions. |
| 1-impl | 2026-10-03 | none — implementation, no reviewer dispatched | 0 | 0 | 0 | 0 | Building it found one clause the spec missed: PRESS-0021 INV-5 let setup call the Store only to ask whether it holds a site, and setup now checks and writes the identity. Added to § 11 and the Amends line, with a pointer in PRESS-0021. Records built, verified code, so no re-gate. |
