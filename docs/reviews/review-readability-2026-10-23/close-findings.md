# close-findings — review-readability 2026-10-23

The disposition of every finding in this folder's lane files, and of the
bug leads they produced (PRESS-0296 to PRESS-0325). One section per lane.
`fixed` names its commit; `queued` names its roadmap item; `dismissed`
says why.

## HIGH findings closed first

| Finding | Disposition |
|---|---|
| lane-09 `scripts/windows-gate.sh` exit 2 | fixed, PRESS-0296 (0c23bcd) |
| lane-01 `choices.py` docstring folder | fixed (0b3ea13) |
| lane-05 `publisher.py` `_NoCrossOriginAuth` twins | fixed (0b3ea13) |
| lane-07 `starter.py` marker folder | fixed (0b3ea13) |
| lane-08 `_bring.py` `_MISSING` | fixed (0b3ea13) |

## lane-09 tooling

| Finding | Sev | Disposition |
|---|---|---|
| `windows-gate.sh` exit 2 | HIGH | fixed, PRESS-0296 (0c23bcd) |
| `by-hand-browser-checks.py` save-wait copies | HIGH | fixed (1c1a3d0) |
| `build-linux.sh` Python-finding loop copies | MEDIUM | fixed (69efc2d) |
| `write_google_secret.py` does not strip, unlike `write_usage_key.py` | MEDIUM | queued PRESS-0324 — stripping changes what PRESS-0122 § 4.7 specifies |
| `by-hand-browser-checks.py` row order (`code_colours`) | MEDIUM | fixed (a517fae) |
| `by-hand-browser-checks.py` inline rows' `seaside` state | MEDIUM | fixed (a517fae) — a comment names the states; the split into row functions needs a browser run to check |
| `by-hand-browser-checks.py` countdown 2099 | LOW | fixed (a517fae) |
| `by-hand-browser-checks.py` rebound `added`, `shown` | LOW | fixed (a517fae) |
| `by-hand-browser-checks.py` docstring row list | LOW | fixed (a517fae) |
| `by-hand-browser-checks.py` drag `outer` | LOW | fixed (a517fae) |
| `windows-gate.sh` `tree.zip` copy | LOW | fixed (b13b905) |
| `local-ci.sh` config-key copies | LOW | fixed (14bf3c9) |
| `.githooks/commit-msg` machine-local standard | LOW | fixed (93dfab5) |
| `make-signing-key.py` usage from docstring | LOW | fixed (93dfab5) |
| tool: `by-hand-browser-checks.py` unused `violations` | — | fixed (a517fae) |
| tool: `by-hand-browser-checks.py` `editor as ed` | — | fixed (a517fae) |
| lead PRESS-0300 `local-ci.sh` unknown option | — | real; fixed, shipped (14bf3c9) |
| lead PRESS-0324 Google secret line break | — | real; queued, same item — spec first |
| lead PRESS-0325 deleted unstaged file | — | real; fixed, shipped (b13b905) |
| lead `windows-gate.sh` pytest exit 2 | — | fixed, PRESS-0296 (0c23bcd) |

Sweep: searched docs/, tests/, CLAUDE.md and README.md for `tree.zip`,
the old row list, the Python loop and its reason, the save-wait
expression, and each changed script's name. Nothing was stale.
