# PRESS-0011 — review loop log

`review-contract` rows for `docs/specs/PRESS-0011-face.md`.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-11 | 3, cold — genre pinned `spec`; a new spec, whole document. Packet carried `docs/design.md` § Errors, § State, § Logging and the rules, PRESS-0009 § 4.1 and § 6, PRESS-0002 § 4.3, PRESS-0003, PRESS-0022 § 3 and § 4.5, and every failure type's class. Windows and a real browser unrunnable | 1 | 5 | 3 | 2 | **Eleven verified, eleven fixed, none dismissed. One loop only, by user instruction: not converged.** All three lanes: Show details dropped the detail PRESS-0019 puts there for it. Two lanes: INV-7's test could not see the path it forbids, and what the console holds was left unsaid. Two were measured here: the standard server prints a traceback naming every file's path, and an uncaptured notice prints its caller's path. Pages gained `add_page`; notices take the three parts § Errors requires. |
| 2 | 2026-09-25 | 3, cold — genre pinned `spec`; gate armed by PRESS-0145 (`47cb4c0`): `Notice`, `Site.UPDATED`, § 4.4's notice rule, INV-2 and INV-8. Each lane held all four questions; each disclosed the commit subject | 0 | 0 | 0 | 1 | **One verified, one fixed, none dismissed.** All three lanes: INV-6 fed `render_notices` a string only, so a `Notice` inserted raw passed; it now feeds both. Four open questions resolved clean: the shared next step under `UNKNOWN`, who logs a `Notice`, the list's type hint, and whether a kept-copy notice can arrive through `capture()`. |
