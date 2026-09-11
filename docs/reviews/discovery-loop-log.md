# `docs/discovery.md` — review loop log

`review-contract` rows for `docs/discovery.md`, kept here because that
document has never carried a loop log and a review table is not what its
readers come for.

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-11 | 3, cold — genre pinned `adr`; gating S6's rewording (PRESS-0028). Packet carried `docs/design.md` § Errors, PRESS-0009 § 6 and the `OutcomeUnknown` raise sites. GitHub and Windows unrunnable | 0 | 2 | 2 | n/a | **Four findings: three verified, two fixed, one surfaced as PRESS-0118; one dismissed as immaterial. One loop only, by user instruction: not converged.** All three lanes found the open question on visitor numbers contradicting S11. S6 now says publishing again is safe after an unknown outcome. Two of four inside the gated span. |
| 2 | 2026-09-11 | 3, cold — genre pinned `adr`; gating PRESS-0118's sentence taking a crash out of S6. Packet carried `docs/design.md` § Errors and PRESS-0009 § 6. GitHub and Windows unrunnable | 0 | 2 | 0 | n/a | **Two verified, two fixed, none dismissed. One loop only, by user instruction: not converged.** All three lanes: "during that step" took only the last step out of S6, leaving a crash at an earlier step owed a sentence nothing can show. Two lanes: S6 admitted one unknown outcome while `docs/design.md`'s last-resort catch reports one for any unforeseen failure mid-publish. S6 now names both, and design.md's "the one case S6 admits" is deleted. Both inside the gated span. |
