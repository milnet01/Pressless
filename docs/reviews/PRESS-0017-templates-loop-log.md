# PRESS-0017 — review loop log

`review-contract` rows for `docs/specs/PRESS-0017-templates.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-27 | 2, cold, run one after the other; every lane held every question. New spec, genre pinned `spec`. No unrunnable region; one added Windows claim was run on the Windows box | 1 | 0 | 2 | 0 | **Three verified, three fixed, none dismissed.** Both lanes found §4.2's retry false: the first template write creates the folder, so a failed seed is final; §4.2 and §6 now say so. Both found template categories and tags unparsed; they now go through `editor._names_of`. A lane's open question became the third: the free-name check is a file check, which on Windows also finds `Poem.txt`. Four open questions resolved clean. |
