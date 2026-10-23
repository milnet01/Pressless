# Premise checks — review-readability 2026-10-23

Phase 3: each claim below rests on code the lane did not quote. Each was
checked by one read-only command at commit `0fe72df`. Nothing was
deleted from the lane files.

**Quotes.** Every finding's quoted line was matched against its cited
file within eight lines. All matched, allowing for the lanes' `…` elisions
and joined wrapped lines. `insights.py:195`'s three-name quote in lane 06
spans 195–298; the names are there.

## HIGH findings

| Lane | Finding | Claim | Command | Mark |
|---|---|---|---|---|
| 01 | `choices.py:3` | choices go in the open site's folder, theme in Pressless's own | `grep -rn 'choices\.(remember\|read)(' src`; `face.py:1284-1288` | confirmed |
| 05 | `publisher.py:201` | the twin in `insights.py` is not named in `publisher.py` | `grep -n -i insights src/pressless/publisher.py` → no hits | confirmed |
| 07 | `starter.py:20` | the marker lives in each site's folder | `sites.py:32` lists `starter-unpublished`; `setup.py:300-301` fills the site folder | confirmed |
| 08 | `_bring.py:55` | only three sites hold the wording | `grep -rn "its original is missing\|_MISSING\b" src` → three | confirmed |
| 09 | `windows-gate.sh:124` | the remote exits with pytest's code, and 2 reads as unreachable | `windows-gate.sh:66,119,126,133`; `local-ci.sh:226` | confirmed |
| 09 | `by-hand-browser-checks.py:816` | ten copies; `Saving` is `words.py:503` | `grep -n Saving` → ten; `grep -n 'wait_for_timeout(800)'` | confirmed |

Every HIGH is graded **one edit**. Re-running each named search found
nothing that pins the moved text. `starter.py:20`'s wrong comment is also
in `docs/specs/PRESS-0126-starter-site.md`, as the lane said.

## Other findings

| Lane | Finding | Claim | Command | Mark |
|---|---|---|---|---|
| 02 | `page_editor.py:307` | `kind` unused in `_view` | read `page_editor.py:307-311` | confirmed |
| 02 | `blocks.py:622` | `name` unused in `read` | `name` in `read`'s body: only `mark.name` | confirmed |
| 04 | `store.py:1527` | `list_slugs` uses `_raw_names`; `list_files` calls `_list_names` | `grep -n '_list_names\|_raw_names' store.py` | confirmed |
| 04 | `undo.py:224` | the tuple is unpacked by name at 390 | read `undo.py:388-392` | confirmed |
| 06 | `setup.py:10` | Setup reads the Store | `grep -n 'store\.' setup.py` → 325, 386 | confirmed |
| 07 | `__main__.py:280` | `_wait` only returns True | read `__main__.py:279-283` | confirmed |
| 07 | `updater.py:54` `[tool?]` | `PLATFORMS` never read | `grep -rn PLATFORMS src tests scripts` → one | confirmed |
| 09 | `windows-gate.sh:122` | `tree.zip` unused after the copy | `grep -n tree.zip` → 97, 122 | confirmed |

## Correctness leads

| Lane | Lead | Command | Mark |
|---|---|---|---|
| 01 | `words.py:906` shows PRESS-0230 on screen | read `words.py:904-907` | confirmed |
| 01 | `face.py:1217` branch unused; one `Download` maker | `grep -rn 'Download(' src` → `sites_screen.py:71` | confirmed |
| 02 | `menu.py:99-114` rename leaves `data-nav` | read `menu.rename` | confirmed |
| 04 | four `_is_windows` | `grep -rn 'def _is_windows' src` → four | confirmed |
| 04 | PRESS-0005 says `_list_names`' only caller is `list_photographs` | `docs/specs/PRESS-0005-store.md:1179-1182` | confirmed |
| 05 | no `data-nav="Journal"` | `menu._nav` returns `Home` or a fixed page; `grep -rn data-nav src` | confirmed |
| 06 | `github_setup.py:75` raises `RuntimeError` | read `github_setup.py:70-78`; callers listed by `grep -rn 'github_setup.token('` | claim confirmed; caller catches not checked |
| 07 | `sitefile.py:211` removes the target before the rename | read `sitefile.py:207-213` | confirmed |
| 09 | pytest exits 2 when interrupted | see the HIGH row above | confirmed in the tree; pytest's code taken from its documentation |
| 09 | `local-ci.sh:27` runs the full gate on an unknown argument | read `local-ci.sh:26-37`: no `*)` branch | confirmed |

Leads not listed here quote the code they rest on, or name a reading
the lane made itself; none was checked further.
