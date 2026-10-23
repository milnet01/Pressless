## Files read
- `src/pressless/store.py`: read 1646 of 1646 lines
- `src/pressless/undo.py`: read 568 of 568 lines
- `src/pressless/safe_write.py`: read 104 of 104 lines
- `src/pressless/log.py`: read 138 of 138 lines
- `src/pressless/paths.py`: read 99 of 99 lines

## What I started with
- The global `~/.claude/CLAUDE.md`.
- A SessionStart hook message about the Ants MCP verbs.
- An environment block (working directory `/home/ants/.cache/lane-neutral`, date 2026-10-23).
- The user's email from the account context.
- No project `CLAUDE.md`, no memory index and no git snapshot.
- I read the shared context file once, as STEP 1 says.

I found no disagreement between the brief and the lane rules. The brief's "you may go outside your files to confirm" is consistent with the lane's evidence boundary.

## Summary
The Store keeps the writer's site as plain files: one text file per entry, drafts in one folder and published entries in another. Pages, comments, settings-like options and the site's look each sit in their own folder, and nothing is ever deleted; old versions go to a "bin" folder. Undo fetches the site as it was one publish ago, makes the writer's files match it (keeping his own versions as drafts), then publishes again. If anything fails partway, Undo reverses the steps it took. The other three files are small helpers: one saves a file so that a crash leaves either the old or the new version, one keeps a size-limited plain-English log, and one decides where Pressless keeps its own folder.

## Findings

[Q1] MEDIUM `src/pressless/undo.py:89` — `def captured(step: Callable[[], _T]) -> _T:` — The same "run a step, collect its notices whatever happens" wrapper is written out five times:
- `undo.py:89-96` (`captured`)
- `undo.py:514-521` (`gathered`)
- `publishing.py:150-157` (`captured`)
- `publishing.py:324-331` (`gathered`)
- `page_editor.py:934-940` (`_gatherer`, which already is a factory taking `face` and `notices`)

The copies differ only in which capture they call and which list they extend. A stranger fixing how notices are gathered (for example, also gathering on an early return) would fix the copy in front of them and miss the others. Nothing links them. — Fix: have the four inline copies call one shared factory shaped like `page_editor._gatherer`, taking the capture callable and the list.
Cost: one edit — Searched: `docs/specs` for `captured(` and `gathered(` (no hits); `docs/` for `_gatherer` (no hits). No ANCHORS.
Confirms dup:d9e64d75ba0a and dup:a7914cd27d9c. Searched: `caught: list\[str\] \| None` across the tree, which found exactly these five sites.

[Q1] MEDIUM `src/pressless/undo.py:377` — `for name, template in sorted(state.templates.items()):` — `_restore_other_kinds` holds five hand-copies of one pattern: "read what is there, bin it if it differs, write the fetched one, record the reversal". The copies are templates, forwards, identity, options and comments. Two more live in `_restore_html` (443) and `_restore_look` (352). They have drifted:
- templates, comments and html test `path.is_file()`, then exit early with `continue`/`return`;
- forwards and identity nest under `if remembered != …`;
- identity reads with `read_identity`, with no `is_file` test.

Each recent ticket (PRESS-0182, 0213, 0214, 0196) added one more. The next stranger adding a kind has no single model to copy, and the length of the function hides which differences are deliberate. Only options' "absence is restored" difference has a comment (415-418). — Fix: extract one `_restore_one(path, remembered, wanted, write, reversals)` step and keep the options exception as its own commented block.
Cost: pinned — `docs/specs/PRESS-0214-journal-switch.md` line 135 names `_restore_other_kinds`. Splitting it inside its own name keeps that name, so this may still be one edit; I did not read that spec passage.
Confirms the size candidate `undo.py:366`.

[Q3] LOW `src/pressless/undo.py:401` — `for identity in state.identity.values():             # PRESS-0213 § 4.5` — This reads as "for each identity". In fact the site has exactly one identity file, so the dict holds at most one item. The loop recomputes the same `identity_path_for(folder)` on each pass. A stranger would think several identities can exist and might try to key them. — Fix: hold the fetched identity as `Identity | None` in `_State`, or comment that the dict holds at most one item.
Cost: one edit — Searched: `docs/specs` for `_State` names (none found); not pinned by ANCHORS.

[Q1] MEDIUM `src/pressless/store.py:1179` — `data = target.read_bytes()` — "Read bytes; on OSError, StoreError with `_why`; decode UTF-8 / parse JSON" is repeated in seven places:
- `read` (211)
- `read_html` (764)
- `read_comments` (861)
- `_read_mapping` (989)
- `read_options` (1027)
- `read_identity` (1116)
- `read_look_file` (1178)

They differ in the missing-file answer: `EntryNotFound`, `StoreError`, `()`, `{}`, `{}`, `None`, `None`. Each function's docstring states its own answer, so those differences are deliberate. The shared half is not shared, though. The no-full-path rule that `_why` exists for (PRESS-0005 § 4.4), or any change to the decode error's wording, has to be applied seven times. A stranger will reasonably assume one helper does it. — Fix: one `_read_text(target, on_missing)` helper that the seven call.
Cost: one edit — Searched: `docs/specs` for `_read_mapping` (no hits). The public function names stay.
Confirms dup:31dab15739b5.

[Q1] MEDIUM `src/pressless/store.py:1279` — `_WINDOWS_DEVICES = frozenset(` — Three hand-kept lists of Windows device names:
- `store._RESERVED_NAMES` (68): con/prn/aux/nul plus com1-9 and lpt1-9.
- `store._WINDOWS_DEVICES` (1279): adds `conin$`, `conout$` and the superscript ports.
- `publisher._WINDOWS_DEVICES` (997): an identical copy of the second.

Neither of the store lists mentions the other. The gap between the first two cannot be seen for slugs, because `_LEGAL_SLUG` already refuses `$` and superscripts, but nothing says so. A stranger who measures a new device name (the lists came from measurements, PRESS-0159 and PRESS-0164) would add it to one list and miss the others. The forbidden-character sets also differ: publisher's includes `\\` and store's does not, because store refuses the backslash in `_single_name`. That difference is explained only by reading both functions. — Fix: make `_RESERVED_NAMES` derive from `_WINDOWS_DEVICES` (or say beside it why it is a subset), and cross-reference the publisher copy.
Cost: unsure — `docs/specs` has no hits for either name (searched). But a merge across `store` and `publisher` collides with "design rule 7 forbids reaching into another part" (`store.py:630`), so the shared home is undecided. The in-file derivation is one edit.

[Q4] MEDIUM `src/pressless/store.py:1527` — `no setup step for them (§6). That is list_slugs' rule, shared rather than` — The docstring says `_list_names` carries `list_slugs`' rule, shared. In fact `list_slugs` no longer calls it; it uses `_raw_names`. PRESS-0005 lines 1180-1181 say `_list_names`' only caller is `list_photographs`, and `list_files` (1310) is now a second caller. Both callers pass `suffix=""`, so the suffix branch is dead. It also matches the suffix case-sensitively, while `_raw_names` folds with `.lower()` and `_slugs_in` folds A-Z only. That gives three different suffix comparisons. A stranger fixing the listing rule in `_list_names`, trusting "shared", changes nothing that `list_slugs` does. — Fix: correct the docstring to name its real callers, drop the unused `suffix` parameter, and note that `_raw_names` is the entry-listing helper.
Cost: pinned — `docs/specs/PRESS-0005-store.md` around lines 867 and 1181 names `_list_names` and its callers; `tests/test_store.py:1375` names it in a docstring (not an ANCHORS entry). The comment-only part needs no search.

[Q4] LOW `src/pressless/store.py:1483` — `folded = suffix.lower()` — The comment at 187-190 states the rule: fold A-Z only, never `str.lower`, because `lower` also folds look-alikes. `_raw_names` uses `.lower()` for the suffix anyway. It is harmless for `.txt` and `.html` (I know of no non-ASCII character that lowercases into those letters), but it reads as a breach of the stated rule. A stranger might either "fix" it or copy it somewhere it matters. — Fix: use `_folded`, or comment why `lower` is safe for a fixed ASCII suffix.
Cost: one edit — Searched: `docs` for `_raw_names` (only `PRESS-0005:1180`, which names the function, not its body).

[Q4] LOW `src/pressless/store.py:112` — `place a slug becomes a file name, so guarding it once covers write,` / `exists, publish and unpublish alike (§4.2).` — `exists` does not go through `path_for`; it calls `_refuse_illegal_slug` itself (138). Nor is `path_for` the one place a slug becomes a file name: `html_path_for`, `template_path_for` and `comments_path_for` do it too. A stranger trusting this could remove `exists`' own check. That check's docstring (134-136) would put them right, hence LOW. — Fix: drop "exists" and "the one place", or point at `_refuse_illegal_slug` as the shared guard.
Cost: comment only.

[Q4] LOW `src/pressless/store.py:9` — `Every read and write names UTF-8 and LF explicitly.` — `write_html` (791) and `write_look_file` (1201) pass `newline=""`, which is no translation at all, not LF. A stranger reading the module header could "fix" those two to `"\n"` and reformat the writer's pages. `write_html`'s own docstring corrects this. — Fix: "names UTF-8 and its line-ending rule explicitly: LF, or none for pages and the look".
Cost: comment only.

[Q1] LOW `src/pressless/store.py:1575` — `def _is_windows() -> bool:` — Four identical copies: `safe_write.py:86`, `store.py:1575`, `settings.py:400`, `credentials.py:198`. `store._move_without_overwriting` branches on `store._is_windows()` and then calls `safe_write.patiently`, which branches on `safe_write._is_windows()`. A stranger (or a test) patching one gets a half-Windows path. Nothing at the call says two predicates are involved. — Fix: have `store` (and `settings`) use the predicate `safe_write` already exports, or comment the pairing at `_move_without_overwriting`.
Cost: pinned — `docs/specs/PRESS-0005-store.md:581` and `docs/specs/PRESS-0001-settings.md:317/352` name a per-module `_is_windows()` helper.
Confirms dup:baeb82c37ac4 in part.

[Q3] LOW `src/pressless/undo.py:75` — `def undo(folder: Path, settings: settings.Settings, key: str, *,` — The parameter `settings` hides the `settings` module inside `undo()`. The annotation still works only because of `from __future__ import annotations`. A stranger moving a call like `settings.load(folder)` (as `_pressed` makes at 525) into `undo()` gets an AttributeError on a Settings object. — Fix: rename the parameter (e.g. `saved`, the name `_pressed` already uses).
Cost: one edit — Searched: `docs/specs` for `captured(`/`gathered(` only. **This search does not cover the cost:** I did not search the specs for `undo(`'s parameter name, so grade this unsure in that respect.

[Q3] LOW `src/pressless/undo.py:224` — `state.forwards[name] = _FORWARDS[name][1](fetch / prefix)` — Here a tuple slot is picked by position (`[1]` is the reader). At 390 the same tuple is unpacked by name. A stranger reordering or extending the tuple's (path_for, read, write) layout would not see that this line depends on the order. — Fix: unpack it by name here too, or make the tuple a named tuple.
Cost: one edit — Searched: `docs/specs` for `_FORWARDS` (no hits).

[tool?: unused parameter / dead branch] `src/pressless/store.py:1522` — `_list_names`' `suffix` is always `""` at both call sites (searched `_list_names`: 1301 and 1310 only).

## Candidates dismissed
- **dup:4312e9c164bd** — `settings._report_a_wide_grant` and `store._report_a_wide_grant` differ only in the notice key and its slots, and in which spec section their docstrings cite. Each copy names its own contract (PRESS-0001 § 4.4, PRESS-0005 § 4.5). That is parameterised by design, not drift.
- **dup:3f9b6498042e** — the `StoreNotice` / `SettingsNotice` `__init__`. Two identical copies, and `settings.py` says why: "may not import from it", and "as StoreNotice is". No record of a past fix having to patch both.
- **dup:baeb82c37ac4** — five lines inside the pair above. The only shared hazard is `_is_windows`, reported under Findings.
- **dup:792b7d8a1eb8** — the `except` blocks of `move_to_bin` and `copy_to_bin`. Two copies differing only in the verb. The shared checks are already extracted (`_bin_target`).
- **dup:fef2be4c1beb** — the `list_slugs` / `list_templates` folder check. The `"the folder handed to the Store is not a folder"` guard recurs in five functions, identically, and has not diverged. Low value; not reported.
- **size `store.py:199` (`read`)** — long but straight-line: decode, split header from body, one `if` chain per field, then the checks. Every non-obvious line (BOM, CRLF break, stripping the name) has its reason beside it. I found no point where a reader loses the thread.
- **size `store.py:525` (`_refuse_what_the_format_cannot_carry`)** — a flat list of independent refusals, each with its reason in the error text. The nesting is the extra-field loop, which is commented.
- **size `undo.py:75` (`undo`)** — the steps are numbered 1 to 7 against § 4.3, and each `except` branch says why it raises or reverses.
- **comment `log.py:39` "2 expects"** — "§2 expects" is a section reference, not a count.
- **comment `undo.py:531` "6 raises"** — "step 6 raises OutcomeUnknown" names a step of § 4.3's numbered sequence, not a count.

## Correctness leads
- `src/pressless/store.py:393` — `copy_to_bin` creates the target with `"xb"` and then writes. A write that fails partway leaves a partial copy in the bin, and a retry in the same second then hits FileExistsError. — Searched: none.
- `src/pressless/store.py:512` — on Windows, `_move_without_overwriting` is chosen by `store._is_windows()`, but `patiently` retries only when `safe_write._is_windows()` is true. A patch of one predicate without the other gives the Windows rename without the retry. Test exposure only on real hardware. — Searched: `def _is_windows` (four definitions).
- `docs/specs/PRESS-0005-store.md:1181` says `_list_names`' only caller is `list_photographs`, but `list_files` (`store.py:1310`) also calls it. This is a stale spec claim, not code. — Searched: `_list_names` across the tree.

## Not checked
- I did not read the spec passages that name `_restore_other_kinds` (PRESS-0214 line 135), `_is_windows` (PRESS-0005 line 581, PRESS-0001 lines 317/352) or `_list_names` (PRESS-0005 lines 867/1181) beyond the search hits, so whether a refactor actually conflicts with them is unsure.
- I did not check `credentials.py:198`'s `_is_windows` body beyond the search hit showing it exists.
- `docs/design.md`'s "rule 7" (cited at `store.py:630`), which decides where a shared device list could live: not read.
- I made no judgement of the tests that walk these modules' ASTs. Reading their import checks, none pins a name these fixes would move.
- These five files hold no embedded JavaScript, HTML or CSS, so that part of the brief did not apply to this lane.
