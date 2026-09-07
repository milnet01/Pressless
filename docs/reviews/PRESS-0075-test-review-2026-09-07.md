# PRESS-0075 — test review, 2026-09-07

`review-tests`, five cold lanes over 14 files. This file is the lanes' returns
as they came back, kept because a report living only in a transcript is gone
when the session is. The synthesis is in the commit that adds this file.

**Baseline (whole suite, `PRESSLESS_ARCHIVE` set): 208 passed, 0 failed,
0 skipped, 1.57s.** Every finding below sits under a green suite.
`addopts` carries no coverage writer, so the run wrote nothing into the tree.

**Suite size:** 9,282 lines of tests against 3,833 lines of source. The
roadmap item's figures (4,298 / 2,256) were badly stale.

**Withheld from the lanes on purpose:** the three invariants a prior code
review recorded as unfalsifiable, and the known rainbow-whitespace gap. If a
lane found one independently it is confirmed; if not, that is its own signal.

## Chunk map

| Lane | Files | Weighting |
|---|---|---|
| 1 | test_store.py, test_store_extras.py | #1 #5 #14 |
| 2 | test_publisher.py, test_network_timeouts.py | #1 #5 #9 |
| 3 | test_insights.py, test_credentials.py | #1 #5 #14 |
| 4 | test_marks.py, test_settings.py | #1 #5 #12 |
| 5 | 3 archive files + 3 shared helpers | #8 #1 #5 |

All five dispatched, all five returned. No chunk dropped, none re-dispatched.

## Verified by mutation probe

The project's own note on this item says to run the probe rather than read the
assertions. Nine mutations were run against lane claims.

| Claim | Outcome |
|---|---|
| INV-6's tie-break on country code removed | **SURVIVED** — claim confirmed |
| INV-25's length cap on Google's words removed | **SURVIVED** — claim confirmed |
| INV-24's two `_discard` calls removed | **SURVIVED** — claim confirmed |
| INV-4's `&` escaping removed from `_escape_attr` | **SURVIVED** — claim confirmed |
| INV-4's `'` escaping removed from `_escape_attr` | **SURVIVED** — claim confirmed |
| INV-4's `"` escaping removed (control) | killed — the control behaves |
| Publisher's rate-limit `wait(hint)` removed | **KILLED**, by a different test than the lane cited |
| Store's returns-once de-duplication removed | **KILLED** on Linux; the lane's claim is about case-folding filesystems |

## Lane 1 — the Store

**[MEDIUM] [dim 1] tests/test_store.py:1027** — on a case-folding filesystem
the fixture cannot exist: `write_text` on `ordinary.TXT` reopens the same file
as `ordinary.txt`, so `again.count("ordinary") == 1` whatever the
implementation does, and the "returned once" rule is verified nowhere. Green,
no skip. The identical condition IS guarded eleven lines later at :1372.
*Orchestrator: probe KILLED this on Linux, so the assertion is live here and
vacuous on Windows/macOS — which is a platform this project must ship to.*

**[LOW] [dim 1] tests/test_store_extras.py:312** — `_snapshot` keeps only
`if path.is_file()`, so the "produces no path and no side effect" clause
cannot fail for an eagerly-`mkdir`ing path function, which is the one side
effect these calls could plausibly acquire. Same shape at test_store.py:991.

**[LOW] [dim 5] tests/test_store.py:486** — four move tests assume the
`tmp_path` mount supports hard links. On a mount without them `os.link` raises
EPERM and they fail indistinguishably from a real regression. The suite treats
mount capability as first-class everywhere else.

## Lane 2 — the Publisher

**[HIGH→LOW] [dim 1] tests/test_publisher.py:777 and :1371** — `assert
retried_once.waits` is non-empty from pacing alone (four writes, three pacing
waits), so it carries none of its stated weight.
*Orchestrator: DOWNGRADED. The probe removing `wait(hint)` was KILLED — by
`test_a_rate_limit_naming_no_interval_waits_the_documented_minute`, a
different test. So the assertion is weak, and the behaviour is covered.*

**[MEDIUM] [dim 1] tests/test_network_timeouts.py:63** — `assert found` fires
only when the walk matches nothing. If one of the two opener sites loses its
recognisable shape, `found` drops to 1, the test stays green, and that
module's opener is no longer checked at all.

**[MEDIUM] [dim 5] tests/test_publisher.py:1218** — `Path.symlink_to` raises
at setup where symlinks are unprivileged-forbidden (Windows without Developer
Mode, FAT/exFAT, some CIFS). The test errors rather than skipping. The
neighbouring platform-dependent test at :1271 is guarded.

**[MEDIUM] [dim 1] tests/test_publisher.py:1371** — as above.

**[LOW] [dim 1] tests/test_network_timeouts.py:54** — `glob` is not recursive,
so a module at `src/pressless/<subpackage>/client.py` is never walked, while
the docstring claims the whole of `src/` is.

**[LOW] [dim 1] tests/test_publisher.py:13** — the file header still says the
stub raises `NotImplementedError` and "PRESS-0009 is not yet implemented".
`publisher.py` is 749 lines and the baseline is 208 passed.

## Lane 3 — Insights and Credentials

**[MEDIUM] [dim 1] tests/test_insights.py:453** — INV-6 is two clauses,
"ordered by people descending AND ties by country code", and no fixture in the
file ever presents a tie. *Probe SURVIVED — confirmed.*

**[MEDIUM] [dim 1] tests/test_insights.py:581** — INV-24's "no temporary left
behind" clause is observed only after a SUCCESSFUL read; no test forces a
failure inside `_store`. The credentials side has this assertion; insights has
no twin. *Probe SURVIVED — confirmed.*

**[MEDIUM] [dim 1] tests/test_insights.py:488** — INV-7 is stated absolutely
and this test observes `str()` and `repr()` only. `credentials.py` raises
`from None` and asserts on `traceback.format_exception`; `insights.py:328`
raises `from exc`, keeping the cause, and nothing constrains what a transport
puts in its message.

**[MEDIUM] [dim 1] tests/test_credentials.py:530** — INV-10's own Test line
requires asserting `write()` refuses the patched owner. The patch is
installed, one `read()` is made, and it is reverted. The write side is never
exercised against it.

**[LOW] [dim 1] tests/test_insights.py:1355** — INV-25 says Google's words are
"capped in length" and nothing asserts the cap. *Probe SURVIVED — confirmed.*

## Lane 4 — Marks and Settings

**[MEDIUM] [dim 1] tests/test_marks.py:236** — INV-4 names five characters to
escape in an attribute value; the fixture contains `"`, `<`, `>` and neither
`&` nor `'`. The other candidate observer compares AFTER an HTMLParser round
trip, which cannot separate them: a bare `&` and `&amp;` both decode the same.
*Probe SURVIVED for both `&` and `'`; the `"` control was killed. Confirmed,
and this is a security invariant with no sanitiser downstream.*

**[MEDIUM] [dim 1] tests/test_marks.py:324** — INV-7's forbidden-import list
is a seven-name denylist. `http`, `ssl`, `ftplib`, `smtplib`, `httpx`,
`xmlrpc`, `webbrowser`, `shutil`, `tempfile`, `glob`, `zipfile` all pass it.
Visible because `test_settings.py:82` bans nine of those names outright — so
`import http.client` fails in the module ALLOWED `os`, and passes in the
module INV-7 exists to keep off the network.

**[LOW] [dim 1] tests/test_marks.py:365** — the `open` walk matches only a
bare `ast.Name` call, so `builtins.open(...)` and `__import__("pathlib")`
pass both halves.

**[LOW] [dim 1] tests/test_settings.py:335** — the watch intercepts three
`open` entry points, and the docstring's stated trigger is a search of the
home directory, which would probe with `Path.exists()` / `os.stat()` and
record nothing. Phase 2 has no `assert opened` guard where phase 1 does.

## Lane 5 — archive and shared helpers

**[HIGH] [dim 1] tests/test_store_extras_archive.py:434** — the test cannot
fail for the defect it names. `_comment()` builds `store.Comment` from six
explicitly named fields; the two address fields are read only by the SEARCH
side. The mutation its docstring names — a widened `Comment` — leaves the
field unset and writes nothing. *Confirmed by reading the data path:
`store.Comment` carries six fields and neither address field is among them.*

**[HIGH] [dim 8] tests/test_store_archive.py:189, twin at
tests/test_marks_archive.py:189** — the skip fires on three causes and reports
one. `_exec_module` swallows every `Exception`, so a SyntaxError, a missing
import or a renamed export all land in a skip whose message asserts the file
is simply absent. A rename in the sibling generator silently stops all three
tests including the S2 round trip. `SystemExit` is not an `Exception`, so that
case errors instead — the two "cannot load" paths behave oppositely.

**[MEDIUM] [dim 5] tests/test_marks_archive.py:71** — the oracle is whatever
`build_blog.py` sorts first under the repository's grandparent directory. A
stale checkout or backup that still exports the three names wins by sort
order, and nothing in the output names which file was used. Each candidate is
executed, up to four times per suite run.

**[MEDIUM] [dim 1] tests/test_store_archive.py:247** — `LEGAL_SLUG` is a
strictly weaker copy of the Store's rule: it omits `_RESERVED_NAMES`, so an
entry resolving to `nul` or `com1` passes a test named "resolves to slugs the
Store can hold".

**[MEDIUM] [dim 1] tests/test_marks_archive.py:107** — `render_body` is never
loaded; the classification INV-5's population depends on is re-implemented
locally, so the file's claim that it lives in the sibling workspace is true of
half of it.

**[LOW] [dim 1] tests/test_store_archive.py:332** — the round trip compares
five of `Entry`'s six fields; `extra` is omitted, which is ADR-0001's
keep-unknown-fields promise going unverified against real data.

**[LOW] [dim 1] tests/_durability_watch.py:69** — each `os.replace` is paired
with the LAST PRECEDING `mkstemp` by position rather than by path, and
`watched_mkstemp` discards the path so the correct pairing cannot be made. A
writer opening two temporaries before renaming either passes with only one
synced — PRESS-0039's exact failure. Shared by four writers' tests this lane
could not see.

## Lane cross-references worth keeping

- **Lane 5:** `_mode_support` and `_durability_watch` may collide. The former
  calls `tempfile.mkstemp`, which the latter patches; if the probe runs after
  the watch is installed in one test, its throwaway `mkstemp` becomes
  `opened[-1]` for the following `os.replace` and the assertion fails on
  correct code.
- **Lane 4, noted not mine:** `settings.py::_report_a_wide_grant` is called
  before `os.fdopen` takes the descriptor, and neither `except` arm closes it
  — the PRESS-0066 leak by a second route, one line above the fix that closed
  it. *(Introduced by this session's PRESS-0097 work.)*
- **Lane 1, noted not mine:** `store.py:400` uses `os.name` where `:1088` uses
  the patchable `_is_windows()`, so the Windows `os.rename` branch cannot be
  exercised by the technique the rest of the suite uses.
- **Lane 2, noted not mine:** `base64.b64decode` runs with `validate=False`,
  so a corrupt blob of non-alphabet junk decodes to `b""` and is written out
  as an empty file with the fetch reporting success.

## Coverage

Every chunk dispatched returned. No dimension was narrowed out by flag or
config; the floor (1, 4, 5) was carried by every lane. Dimension 12 fired
nowhere — the whole suite runs in 1.57s and the slowest test is 0.21s.
Dimension 9 was N/A in three chunks. No test file was left uncovered.

**check-code status unknown** — no report was handed to this run.
