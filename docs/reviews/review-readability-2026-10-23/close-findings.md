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

## lane-05 build and publish

| Finding | Sev | Disposition |
|---|---|---|
| `publisher.py` `_NoCrossOriginAuth` twins | HIGH | fixed (0b3ea13) |
| `publishing.py` `captured` written five times | MEDIUM | fixed (43db56b) — now `face.gatherer` |
| `look_screen.py` words dicts copy `look.py` | MEDIUM | fixed (400ed2f) — literals kept for INV-4; a test checks they match |
| `publisher.py` "the one request" | MEDIUM | fixed (209c62a) |
| `builder.py` `ROOT_OUTPUT` rule unstated | MEDIUM | fixed (762fb31) — comment; tuple keeps PRESS-0008's spelling |
| `builder.py` `photo_src is None` unnamed | MEDIUM | fixed (762fb31) — `_Build.publishing` |
| `builder.py` names hiding modules | MEDIUM | fixed (762fb31) — the two locals; the three parameters are spec-quoted signatures |
| `builder.py` `page="Journal"` unexplained | MEDIUM | fixed (762fb31) — comment form |
| `pressing.py` success read from words | MEDIUM | queued PRESS-0326 |
| `look.py` `made_here` constraint unstated | MEDIUM | fixed (c15e3da) — comment and a test pinning `css()` |
| `builder.py` `icon_copy` docstring | MEDIUM | fixed (762fb31) |
| `look.py` layout rules written three times | LOW | fixed (2c7c774) — output byte for byte unchanged |
| `publishing.py` `finish()` returns failure | LOW | fixed (aaa771e) — now `bin_copy_failed` |
| `publishing.py` `entry` hides the slug | LOW | fixed (aaa771e) |
| `look_screen.py` `_has_style_code` | LOW | fixed (aaa771e) — now `_refuse_without_style_code` |
| `look_screen.py` script copies `STYLE_CODE` | LOW | fixed (aaa771e) |
| `publisher.py` `FetchNotWritten` message thrice | LOW | fixed (aaa771e) |
| `builder.py` `_entries` returns text | LOW | fixed (762fb31) — now `_entries_text` |
| `pressing.py` `forget` caller list | LOW | fixed (aaa771e) |
| lead PRESS-0298 Journal link never current | — | real; spec-pinned by PRESS-0216, left open with a note |
| lead PRESS-0313 wrong request named | — | real; fixed, shipped (209c62a) |
| lead PRESS-0314 note rewording orphans looks | — | real, latent; guarded (c15e3da), left open: PRESS-0196 state 2 |
| lead PRESS-0315 forward under wrong date | — | not real; dropped (an address change keeps the date) |

Sweep: searched docs/, tests/, CLAUDE.md and README.md for
`_has_style_code`, `_gatherer`, `captured(`, `finish()`, `_entries`,
`photo_src is None`, "refused as web_copy" and the OutcomeUnknown
"reference update" claim. Nothing was stale. `test_words.py`'s CSS
allow-list lacked the new look.py constants; fixed (b148268).

## lane-07 app, sites and update

| Finding | Sev | Disposition |
|---|---|---|
| `starter.py` `MARKER` said Pressless's own folder | HIGH | fixed (0b3ea13) |
| `__main__.py` `folder` flips meaning | MEDIUM | fixed (bdbe57f) — now `own`, in `updating.register` too |
| `sites_screen.py` / `importing.py` file box scripts | MEDIUM | fixed (9a5c1a9) — one `face.file_box` |
| `starter.py` `_PAGE` / `_PRIVACY` skeletons | MEDIUM | fixed (a1267ae) — output byte for byte unchanged |
| `__main__.py` / `installer.py` loader-path loop | MEDIUM | fixed (2a62b18) — `installer.restore_loader_paths` |
| `sites_screen.py` `register` docstring | MEDIUM | fixed (104494a) |
| `installer.py` module docstring | LOW | fixed (1540444) |
| `updater.py` `_SIG_SIZES` cap | LOW | fixed (1540444) |
| `updater.py` tag spelling check | LOW | fixed (1540444) |
| `updating.py` `found.step > 1` | LOW | fixed (1540444) |
| `updater.py` "rule 7" | LOW | fixed (1540444) |
| `__main__.py` `_wait` docstring | LOW | fixed (bdbe57f) |
| `updater.py` `PLATFORMS` unused | tool | fixed (1540444) — removed |
| lead PRESS-0299 open site lost on a failed rename | — | real; fixed, shipped (abc6be9) |
| lead PRESS-0318 step 1 failure never logged | — | real for the opener; fixed, shipped (1540444) |
| lead PRESS-0319 file box stuck on a drop | — | real; fixed, shipped (9a5c1a9) |
| lead PRESS-0320 hard-coded English | — | real; backups half fixed (090f94a); sites half spec-pinned by PRESS-0223, left open with a note |

Sweep: searched docs/, tests/, CLAUDE.md and README.md for
`_OPEN_SCRIPT`, `_SEND_SCRIPT`, `_file_box`, `open-site-file`,
`_PRIVACY`, `_NEW_PAGE`, `PLATFORMS`, `rmtree(target)` and
`updating.register` with `folder`. Nothing was stale outside frozen
records. `scripts/by-hand-browser-checks.py` clicked `#open-site-file`;
fixed (9a5c1a9).

## lane-08 import

| Finding | Sev | Disposition |
|---|---|---|
| `_bring.py` `_MISSING` matched a literal reason | HIGH | fixed (0b3ea13) — now `pressless_import.MISSING` |
| `_bring.py` / `_html.py` host rule written four times | MEDIUM | fixed (d4a1137) — `_html.bare_host` and `_host` |
| `importing.py` `_SEND_SCRIPT` copy of the Sites file box | MEDIUM | fixed (9a5c1a9) — one `face.file_box` |
| `_bring.py` / `importing.py` two `_MEDIA` | MEDIUM | fixed (b34ee2b) — `pressless_import.MEDIA_FOLDER` |
| `__init__.py` `_photographs` / `renamed_photographs` cover files | MEDIUM | fixed (e4cd72a) — comments; the specs pin both names |
| `__init__.py` `Report.unfetched` keys | LOW | fixed (e4cd72a) — comment, and `fetch_all`'s docstring |
| `_bring.py` four-part `unfetched` expression | LOW | fixed (e4cd72a) — `_unfetched` |
| `__init__.py` "the run" banner | LOW | fixed (e4cd72a) — now heads `_old_site` |
| `importing.py` `_RELOAD` repeats the address | LOW | fixed (e4cd72a) — built from `ADDRESS` |
| `_bring.py` unknown-look fallback | LOW | fixed (e4cd72a) — comment |
| `_html.py` `_HIDDEN` "neither function" | LOW | fixed (d4a1137) |
| lead: file box `fetch` has no catch | — | fixed, shipped as PRESS-0319 (9a5c1a9) |
| lead PRESS-0321 progress counts off-lock | — | dropped — only `done` is read; one atomic store |
| lead PRESS-0322 refused file's reason by coincidence | — | dropped — the lookup runs only for `MISSING`, filed by upload path |
| lead PRESS-0323 private `_context` | — | real; fixed, shipped (5e1b433) |
| found: safe fetch used the host's certificate store | — | fixed, shipped as PRESS-0327 (e38192c) |

Sweep: searched docs/, tests/, CLAUDE.md and README.md for `_MEDIA`,
`_host`, `_RELOAD`, `_unfetched`, `_context`, "neither function" and
`removeprefix("www.")`. Nothing was stale outside frozen records. The
`_context` hit in `tests/test_certificates.py` showed the fetch missing
from PRESS-0142's certifi rule; fixed as PRESS-0327.
