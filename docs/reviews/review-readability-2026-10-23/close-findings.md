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

## lane-01 face

| Finding | Sev | Disposition |
|---|---|---|
| `choices.py` docstring names the wrong folder | HIGH | fixed (0b3ea13) |
| `face.py` four wrapped-page sends | MEDIUM | fixed (2151e68) |
| `face.py` four Content-Length checks | MEDIUM | fixed (2151e68) — every over-limit body now gets 413 |
| `words.py` 50 MiB typed by hand | MEDIUM | fixed (3434f46) |
| `wizard.py` `is_secret` naming rule | MEDIUM | fixed (6a73eb0) — comment form |
| `face.py` `_say` holds keys | LOW | fixed (27a86df) — now `_keys` |
| `face.py` `_THEME_LIMIT` serves true-colours too | LOW | fixed (2151e68) — now `_CHOICE_LIMIT` |
| `face.py` docstring's kept-state list | LOW | fixed (27a86df) |
| `face.py` hard-wired routes shadow `add_page` | LOW | fixed (27a86df) — comment form |
| `wizard.py` last step must return `Done` | LOW | fixed (6a73eb0) |
| `words.py` group headers | LOW | fixed (d139327) |
| `words.py` `_words` beside `_WORDS` | LOW | fixed (d139327) — now `_lookup` |
| lead PRESS-0301 ticket id on screen | — | real; fixed, shipped (c2911be) |
| lead PRESS-0304 failed upload not drained | — | real; fixed, shipped (bbb8210) |
| lead `_send_download` `.zip` special case | — | fixed (2151e68) — reads `_FILE_TYPES` |
| lead PRESS-0305 `secret` slot collision | — | real, latent; fixed, shipped (3092738) |

Sweep: searched docs/, tests/, CLAUDE.md and README.md for
`_THEME_LIMIT`, `_say`, `_words`, the 52 MB sentence, the download's
content type, `is_secret`, `_drain`, and a 400 answer to an over-long
theme. Nothing was stale.
