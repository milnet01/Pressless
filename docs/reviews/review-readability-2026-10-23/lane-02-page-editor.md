## Files read
- `src/pressless/page_editor.py`: lines 1–2548 of 2548, read in two pages
- `src/pressless/blocks.py`: lines 1–905 of 905
- `src/pressless/menu.py`: lines 1–222 of 222

## What I started with
- The global `~/.claude/CLAUDE.md`, injected into my context.
- A user-email context line.
- An Ants MCP SessionStart hook message.
- The review-lane agent file, which is my system prompt.
- No project `CLAUDE.md`, no memory index and no git snapshot.
- I read the shared-context brief (STEP 1) before the subject files.

## Summary
These three files run the part of Pressless where the user edits a fixed page, the header, the footer or the menu. He can edit them on a picture of the page itself or as raw code. `blocks.py` reads a page as a row of ready-made sections (a paragraph, a heading, a picture, columns and so on) and writes them back. A section it does not recognise is kept exactly as written. `menu.py` edits the user's own menu HTML, such as adding, removing or renaming one link, and leaves every other character alone. `page_editor.py` holds the web pages and the browser scripts for the editor. It also saves a change to a waiting copy and publishes it, or puts everything back if the publish fails.

## Findings

[Q1] MEDIUM `page_editor.py:931` — `def _gatherer(face: Face, notices: list):` — The "capture this step's notices whatever happens" helper exists three times: here, inline as `gathered` at `publishing.py:324`, and inline at `undo.py:514`. The bodies are identical. Someone changing how press notices are collected, for example dropping duplicates, would fix one press route and leave the other two behaving differently. — Fix: move one typed `gathered` helper somewhere all three can import it, and call it from each.
Cost: one edit — Searched: `docs/` for `_gatherer` (nothing found). A search for `gathered` found only prose in the PRESS-0015 spec, not a name.
Confirms dup:d9e64d75ba0a. Searched: `def gathered|def _gatherer|_gatherer\(` across the tree; three sites.

[Q1] MEDIUM `page_editor.py:1196` — `# The page's script (§ 4.5), PRESS-0012 § 4.7's with this page's fields.` — `_PAGE_SCRIPT` copies the entry editor's save-and-publish script in `editor.py`, and the two copies now behave differently in how they wait:
- Here, `inFlight` is a promise that is awaited (`while (inFlight) await inFlight`).
- In `editor.py:983-1004`, it is a true/false flag checked every 100 ms (`while (inFlight) await new Promise(... setTimeout(resolve, 100))`).
- The comment says the only difference is "this page's fields", which is false.

The `pagehide` and `beforeunload` handlers and the "a save queued while this runs" lock are both copied, and both copies carry the same ticket tag (PRESS-0135). That tag is evidence that an earlier fix had to patch both scripts. The next fix to the save race would also be needed twice, and nothing in either file names the other copy. — Fix: say in the comment that the script was copied from `editor.py`'s `_EDITOR_SCRIPT`, and name how the two differ. Or extract the shared autosave core into one script.
Cost: pinned — PRESS-0285 (lines 26 and 139) and PRESS-0242 (line 35) name `_PAGE_SCRIPT` and `editor._EDITOR_SCRIPT`. A comment-only fix needs no search.
Confirms dup:ddec6d16246b, dup:0b513ee26e27, dup:bba7f8636431 and dup:d81b7676150a.

[Q1] MEDIUM `page_editor.py:641` — `_KINDS = (blocks.TEXT, blocks.HEADING, ... blocks.SCRIPT, blocks.STYLE)` — This tuple is a hand-kept copy of `blocks.KINDS` (`blocks.py:45`). The same set is kept by hand three more times:
- in `_KIND_WORDS`;
- as `KINDS` inside `_VISUAL_SCRIPT` (line 1701);
- as `HOLDERS` there (line 1706), which mirrors `blocks._HOLDERS`.

They match today. Someone adding a section kind to `blocks.KINDS` would get it read and written correctly, but it would be missing from the Add list or from the script's rules about what may go in a column. — Fix: set `_KINDS = blocks.KINDS`, and pass the kind and holder lists to the script in the `sections` JSON it already reads.
Cost: pinned — PRESS-0217 § "`page_editor._KINDS` and `_KIND_WORDS` gain the six" (spec line 95) names `_KINDS`.

[Q1] MEDIUM `menu.py:106` — `if html.unescape(inside).strip() in old_words:` — There are two ways of reading "a link's words", and they disagree. `rename` unescapes and trims the raw inside of the link. `_words` (line 129), used by the menu view, also strips tags first. A link written `<a href=...><span>About</span></a>` therefore shows as "About" in the menu view, but `rename` will not recognise it as "About".

Writing a link's words also differs: `rename` (line 109) and `add` (line 87) use `html.escape(words)`, which escapes quotes, while `_changed` (line 156) and `arranged` (line 201) use `quote=False`. Someone fixing how link words are read or written would fix one path and miss the others. — Fix: have `rename` compare with `_words`, and write link words through one helper.
Cost: one edit — Searched: `docs/` for `def rename`. PRESS-0195 gives only `rename`'s signature, which this fix keeps.

[Q1] LOW `page_editor.py:764` — `address = "{{UP}}index.html" if page == HOME else f"{{{{UP}}}}pages/{page}.html"` — This builds the menu's page addresses again, by hand. `menu._HOME`, `menu._address` and `menu._PAGE` already define them, and `_removed` (line 1097) builds a third form, `f"pages/{name}{store.HTML_SUFFIX}"`. If the address format changes in `menu.py`, the choices offered here stop matching `menu._nav`, and links chosen from this list would lose their `data-nav` mark. — Fix: give `menu` a public address helper and call it here and in `_removed`.
Cost: unsure — I did not search the specs for `_HOME`, `_address` or `_PAGES`; my search for `_HOME` in `docs/` returned nothing.

[Q4] MEDIUM `blocks.py:489` — `# §4.5: every form each kind has been written in, oldest first, as a reader beside its writer. ... A change to a kind's HTML adds a form here and never removes one.` — For PICTURES, SLIDESHOW, COLUMNS, `_COLUMN` and QUESTIONS, the reader in `_FORMS` is `None` (`_READERS.get(kind)`). `_Reading.candidate` (lines 571–587) ignores it and hard-codes the current class names and `questions()` markup. Someone following this comment to change the HTML of a holder kind would add an "older form" that is never read with its old markup. Every existing section of that kind would then silently turn into code. — Fix: say in the comment that holder kinds are read by `candidate`/`questions`, which must change together with their writers.
Cost: comment only; no search needed. (PRESS-0217 line 75 names `_FORMS`, for information.)

[Q2] MEDIUM `page_editor.py:854` — `def _pressed(face: Face, folder: Path, form: dict[str, str],` — 75 lines. A stranger loses the thread at lines 894–906. There, a `try` nested inside another `try` has three arms:
- `OutcomeUnknown` calls `finish()`, which bins the waiting copy, and re-raises without putting anything back;
- every other failure puts back the changes;
- success sets `kept = finish()`.

That nesting sits inside a closure (`finish`), inside a wrapper (`gathered`), inside the lock. Notices also run in two streams, `notices` and `said`, which are merged only after the outcome is known. — Fix: lift the publish-and-recover step (lines 894–906) into a named function, with the asymmetry in the next finding stated there.
Cost: unsure — `_pressed` is not named in the specs I searched, but my last `docs/` search was truncated (see Not checked).
Confirms "size page_editor.py:854:_pressed".

[Q5] MEDIUM `page_editor.py:1160` — `except publisher.OutcomeUnknown:` / `raise` — In `_reshaped`, this arm does nothing but re-raise. To a stranger it looks redundant. Its only job is to stop the `except BaseException:` below from putting the files back when the site may already hold the new ones. No comment says so. In `_pressed` (line 897), the same asymmetry exists, again without a comment. Someone deleting the "redundant" arm, or merging the two arms, would put back a page that may already be published. — Fix: add one comment on each arm saying why an unknown outcome must not be put back.
Cost: comment only.

[Q4] LOW `page_editor.py:903` — `# A failure here is raised in place of the original (§ 4.7).` — "Here" reads as the publish failure. It actually means a failure inside `changes.put_back`, which would replace the publish's exception. Someone could take this as describing the `raise` and miss the real risk. Line 1163 has the same wording. — Fix: say "if putting back fails, that failure replaces the publish's".
Cost: comment only.

[Q5] MEDIUM `page_editor.py:214` — `for path in held:` — This loop (lines 214–220) enforces two unstated rules:
- A kept top-level section must not also have its children named.
- A child that is not named is fine only if its parent is named.

The gap rule on lines 221–222 is also unstated: a kept top-level section keeps the whitespace before it, and anything else gets `"\n"`. These rules depend on a contract that only `_VISUAL_SCRIPT`'s `post()` shows: a changed section is sent fresh, and its old path goes into `removed`. Someone changing either side would break saves with no hint why. — Fix: add one comment naming the posting contract, and the rule each `raise` enforces.
Cost: comment only.

[Q3] LOW `page_editor.py:307` — `def _view(kind: str, asked: str) -> str:` — `kind` is never used. Its presence, and every caller passing it, suggest that pages and furniture open in different views. They do not. Someone would look for kind-dependent behaviour that is not there. — Fix: drop the `kind` parameter.
Cost: one edit — Searched: `docs/` for `_view\(` (nothing found).

[Q3] LOW `page_editor.py:872` — `def finish() -> bool:` — The function returns True when binning *failed*. So `if finish():` (line 898) reads as "if it finished", which is the opposite. The docstring on the next line sets it right, hence LOW. — Fix: rename it to say that it reports a copy left behind, e.g. "bin copy, true if kept".
Cost: one edit — local closure; not named in any spec I searched.

[Q3] LOW `page_editor.py:160` — `def _menu(kind: str, name: str) -> bool:` — A yes/no check named like a noun. `elif _menu(kind, name):` reads as if it fetches the menu, next to the `menu` module and `_menu_panel`. — Fix: rename it to a claim, such as "is menu".
Cost: unsure — my search for `_menu\(` in `docs/` found nothing, but it was part of a combined pattern.

[Q3] LOW `page_editor.py:1062` — `def _refused(folder, form, renaming, saved)` — It differs from `_REFUSED` (line 395, a tuple of exception types) only by case, and sits beside `_name_refused`. Someone searching for `_refused` gets both. — Fix: rename it after what it returns, such as "reshape hint".
Cost: unsure — the docs search for `_refused` was swamped by test names and truncated.

[Q4] LOW `page_editor.py:59` — `HOME = "index"  # the fixed page furniture previews first` — The comment presents `HOME` as a preview preference. It is actually the homepage's name, used to refuse removing or renaming the homepage (line 1066), for menu addresses (line 764) and for titles. Someone changing it to alter which page the preview shows first would break all of those. — Fix: say in the comment that this is the homepage's file name.
Cost: comment only.

[Q4] LOW `blocks.py:622` — `` `name` is the page's, for the caller's messages `` — `read` never uses `name` and produces no messages; `unmarked` (line 750) does the same. Someone would hunt for where `name` goes. — Fix: drop the parameter, or say it is unused and kept for the interface.
Cost: unsure — these are public names (`__all__`); I did not search the specs for `read(`/`unmarked(`.

[Q5] LOW `page_editor.py:518` — `request.query.get("view", ""), request.query.get("show", remembered.shown_on), notices)` — `_switch` copies `_open`'s read-under-lock block, but with two unexplained differences:
- the view defaults to `""` instead of `remembered.view`;
- there is no `pressing.holding()` check.

Nothing says whether a switch during a press is meant to go ahead. Someone merging the two would have to guess. — Fix: add one comment on `_switch` stating both differences.
Cost: comment only.
Partly confirms dup:ce0f37967d36, for the `_open`/`_switch` pair only.

[Q1] LOW `page_editor.py:1770` — `const allowed = (href) => /^(https?:|mailto:)/i.test(href.trim())` — This is the browser-side copy of `blocks.address_allowed`, and it differs. The server strips control characters and removes tabs and line breaks before reading the scheme; the browser only trims. So the browser accepts some addresses the server refuses, and the save then stops with a failure. Someone tightening one copy would miss the other. — Fix: add a comment on the browser copy naming `blocks.address_allowed` as the rule it must follow.
Cost: comment only.

[tool?: redefined-outer-name] `page_editor.py:570` — `choices = [link(...)]` hides the imported `choices` module inside `_page`; `_panel` (line 677) does the same.

[tool?: wrong type annotation] `page_editor.py:858` — `notices: list[str] = []`, but `Notice` objects are appended (lines 899, 918) and `_menu_said` returns `list[Notice]`.

[tool?: unused argument] `page_editor.py:307` `_view(kind)`; `blocks.py:621` `read(name)`; `blocks.py:750` `unmarked(name)`.

## Candidates dismissed
- dup:076b9c51df39 — The cited lines are the `from pressless import (...)` and `from pressless.face import (...)` import lists, not behaviour.
- dup:e7d15d913ec3 — Only the `pressing.run(...)` call and the `_pressed` signature line match. The bodies serve different subjects (entries vs pages) by design.
- dup:797632e2ba38 — `_failed`/`_json` are two identical copies (here and `editor.py:272-278`). No comment or ticket shows that a fix had to patch both.
- dup:ce0f37967d36 — Mostly the "try, record failure, else None" pattern, used across routes. The exception tuples differ by route on purpose. The one real divergence (`_open`/`_switch`) is reported above.

## Correctness leads
- `menu.py:99-114` — `rename` points the href at the new page but leaves `data-nav="<old name>"` on the link. `builder.py:431` marks the current page by `data-nav="{page}"`, so after a rename the renamed page's menu link is never marked current. A later page that reuses the old name would light up the renamed link instead. — Searched: `data-nav` in `src/` (menu.py, starter.py, builder.py:431).
- `page_editor.py:1770` — The browser's `allowed()` accepts addresses the server's `address_allowed` refuses (for example a scheme broken up by a tab). The save then fails with a refusal instead of being blocked when the link is added. — Searched: none beyond reading both.
- `page_editor.py:60` — `NEWEST = "_newest"  # no page name holds "_"` relies on `editor.name_address` mapping every `_` to `-`, which its `[^a-z0-9]+` rule does. That holds for new pages, but I did not confirm that `store` refuses a hand-made `pages/_newest.html`. — Searched: `name_address` definition.

## Not checked
- My final `docs/` search for `gathered|_marked|_PAGE_SCRIPT|...|HOME\b` came back `truncated: true` with a `next_offset`. I did not page through it. So the cost grades marked "unsure" above, and any claim that a name appears in no spec beyond the rows I read, are unconfirmed.
- I did not open `editor.py`'s `_EDITOR_SCRIPT` beyond lines 900–1010. Other differences between the two scripts outside that range were not checked.
- I did not search the specs for the public `blocks.read`/`blocks.unmarked` signatures.
- I did not verify whether `pressing.holding()` being absent from `_switch` is safe, for example whether the browser can send a switch during a press.
