## Files read
- `src/pressless/face.py` — 1445 / 1445
- `src/pressless/words.py` — 1725 / 1725
- `src/pressless/themes.py` — 219 / 219
- `src/pressless/wizard.py` — 199 / 199
- `src/pressless/cheatsheet.py` — 43 / 43
- `src/pressless/report.py` — 49 / 49
- `src/pressless/about.py` — 29 / 29
- `src/pressless/restarting.py` — 42 / 42
- `src/pressless/choices.py` — 60 / 60

## What I started with
- The global `~/.claude/CLAUDE.md`.
- A userEmail context block.
- A SessionStart hook message about the Ants MCP verbs.
- The review-lane agent file (my own instructions).
- Environment details: cwd `/home/ants/.cache/lane-neutral`, not a git repo.
- No project `CLAUDE.md`, no memory index and no git snapshot.
- The shared-context file, read in Step 1 as the brief.

## Summary
This code is the part of Pressless the user actually sees. It runs a small web server on his own computer, and his browser shows the app's screens through it. When anything goes wrong it turns the failure into three plain sentences: what happened, what it means for his website, and what to do next. Every word on screen comes from one big table in `words.py`, so the wording can change, or a translation can be added, in one place. The other files provide the colour themes, the step-by-step setup and import wizards, the cheat sheet, the About and problem-report pages, the restart page, and a small file that remembers his last choices between visits.

## Findings

[Q4] HIGH `src/pressless/choices.py:3` — `Kept in choices.json in Pressless's own folder, beside theme.json and for the` — This is false. `face.py:1286` says *"the log and the theme are the machine's… the settings and choices are the open site's"*, and `face.py:1129` calls `choices.remember(face._site, …)`, while `theme.json` goes in `face._folder`. When a site is open, the two folders differ. A stranger who trusts this docstring and adds a new caller would pass Pressless's own folder. That splits his choices across two files, and nothing in `choices.py` would put them right. — Fix: say choices.json is kept in the open site's folder, unlike theme.json.
Cost: one edit — comment only.
Searched: `choices\.(read|remember)\(` across the tree (callers in editor.py, page_editor.py, face.py, tests).

[Q1] MEDIUM `src/pressless/face.py:1043` — `self._send(500, _page(face.fail(exc, publishing=False), face._theme,` — The same "wrap in the frame, add `_FRAMES_POLICY`" send is written out four times: at 1043-1045, 1143-1145, 1156-1157 and 1208-1210. The comment at 438 says *"Every wrapped page carries this"*. A stranger adding a header to every wrapped page, or changing what `_page` receives, has to find all four copies. Missing one would leave the folder-open or download failure page without it. — Fix: one `_send_page(status, body)` method on `_Handler` that all four call.
Cost: one edit — Searched: docs for `_FRAMES_POLICY|_answer|_send_download|_dispatch`. PRESS-0262 names `_answer` as where usage reports fire, which this fix leaves in place. No ANCHORS.

[Q1] MEDIUM `src/pressless/face.py:1066` — `length = _length(self.headers.get("Content-Length")) if method == "POST" else 0` — The Content-Length check is repeated four times and the copies have drifted apart:
- **`_dispatch` (1066-1079):** None gives 400 with no drain; over the cap is drained and gets 413.
- **`_take_upload` (1165-1172):** None gives 400; over the room is drained and gets 413.
- **`_choose_theme` and `_choose_true_colours` (1098-1102 and 1120-1124, identical):** None *or* over the cap gives `_drain()` and then **400**.

In those last two, `_drain()` on a None length is a no-op, because `_drain` re-reads the header and gets 0. So the code looks like it drains a body it never drains. The comment at 1073-1075 says an over-long page body is refused *"as an over-long theme or true-colours body already is"*, but those answer 400 where the page answers 413. A stranger changing the refusal rule, for example to answer 411 or to handle chunked bodies, would fix one or two copies and leave the others. — Fix: one `_body_length(limit)` helper that returns the length or sends the refusal itself, with a single status for over-limit.
Cost: one edit — Searched: docs for `_choose_theme|_choose_true_colours|_take_upload|_THEME_LIMIT` (no hits). PRESS-0122 names `_dispatch` only for the cookie check, which this fix does not touch.
Confirms dup:e2351df32666 and dup:9a4377c8af1e.

[Q1] MEDIUM `src/pressless/words.py:257` — `"That file is larger than 50 MiB (about 52 MB), so it was not added."` — The limit is typed by hand into two entries here (257 and 583, `script.visual.file_too_large`). The real limit is `builder.FILE_LARGEST = 50 * 1024 * 1024` (`builder.py:164`). A stranger raising `FILE_LARGEST` would leave both sentences telling him the old limit. Nothing beside the constant points at the words. — Fix: give both entries a `{limit}` slot, filled from `builder.FILE_LARGEST` where they are said.
Cost: unsure — PRESS-0197 § 3 decision 2 records 50 MiB as a user decision. That pins the value, not the key text, but I did not check whether the spec quotes these sentences.
Searched: `50 \* 1024 \* 1024|50 MiB` across the tree.

[Q5] MEDIUM `src/pressless/wizard.py:61` — `return name.endswith("key")` — Whether an answer is ever written to disk depends on a naming rule: names ending in "key" are secrets. `Step.fields` (line 56) does not mention this rule, and neither does the module docstring (which only says the file *"never holds a key"*). A stranger adding a secret field called `token` or `password` to a wizard step would have it written in plain text to `wizards/<name>.json`. A harmless field ending in "key" (say `monkey`) would silently never be filled back in. — Fix: state the naming rule on `Step.fields`, or replace the suffix test with an explicit `secret` set on `Step`.
Cost: one edit for the comment form. For the `Step` form, unsure — I did not search specs for `Step`'s field list.
Searched: `Step\("` in src. The only secret field today is `"key"` (`setup.py:965`).

[Q3] LOW `src/pressless/face.py:89` — `def _say(what: str, next_step: str, site: Site = Site.UNCHANGED, *,` — Beside the imported `say`, which looks words up, `_say` reads as "say these words", but it only stores keys. The `Sentence` type holds keys in `SENTENCES` and words once `sentence_for` returns it. A stranger reading `SENTENCES[x].what` as text would show a key on screen. The `Sentence` docstring nearby would set them right. — Fix: rename `_say` to something like `_keys`.
Cost: one edit — Searched: docs for `` `_say` `` (no hits).

[Q3] LOW `src/pressless/face.py:1259` — `_THEME_LIMIT = 64` — The name and the comment (*"The longest theme key"*) say it is about themes, but `_choose_true_colours` (1121) uses it too. A stranger tightening it to suit theme keys would not expect to change the true-colours route. — Fix: name it for both small preference bodies, or give true-colours its own limit.
Cost: one edit — Searched: docs for `_THEME_LIMIT` (no hits).

[Q4] LOW `src/pressless/face.py:10` — `Nothing here keeps state between requests (`docs/design.md` § State) beyond` — The list that follows (secret, pages, log) leaves out state that requests do change: `face._theme`, rewritten by `_choose_theme` (1114), and `_link_spent`. A stranger trusting the list would miss that `_theme` is shared mutable state written from request threads. — Fix: add the chosen theme and the spent-link flag to the list.
Cost: one edit — comment only.

[Q5] LOW `src/pressless/face.py:1036` — `if method == "GET" and parts.path == "/folder/location":` — Four routes (`/folder/location`, `/folder/open`, `/theme`, `/true-colours`) are hard-wired ahead of the registered pages. `add_page`'s docstring (1326) promises *"replacing any before it"*, but a page registered at one of these paths is never reached, and no comment says so. — Fix: say so in a comment, or have `add_page` refuse these paths.
Cost: one edit — comment form.

[Q5] LOW `src/pressless/wizard.py:141` — `if index + 1 == len(self._steps):` — When the last step's check returns answers rather than `Done`, the same step is shown again and nothing is saved. Nothing says that a last step must return `Done` to finish. A stranger writing a new wizard whose last check returns answers would get a Next button that seems to do nothing. — Fix: one comment saying the last step's check must return `Done`.
Cost: one edit — comment only.

[Q4] LOW `src/pressless/words.py:1548` — `# The Look screen (look_screen.py).` — The group headers here do not match what sits under them:
- This header sits over the `files_screen.*` entries (1549-1568).
- `look.*` entries (1541-1547) sit under *"The starter site… (starter.py)"*.
- `starter.this_site` and `starter.privacy.*` (1631-1653) sit under no header, after the look-screen entries.

A stranger adding a key "in its section" would put it in the wrong group. — Fix: move the headers so each sits above its own group.
Cost: one edit — comments and order only. No test reads words.py as text, per ANCHORS; `tests/test_settings.py:154` reads names, not order.

[Q3] LOW `src/pressless/words.py:1692` — `def _words(key: str) -> str:` — `_words` (a lookup function) and `_WORDS` (the hand-written English dict before the generated families are merged) differ only in case. A stranger could add a word to the wrong one, or expect `_words` to read `_WORDS` and so miss the `country.`/`mark.` entries. — Fix: rename the function for what it does, for example `_lookup`.
Cost: one edit — Searched: docs for `_words\b`. The only hits were `old_words`/`put_words`, nothing naming this function.

## Candidates dismissed
- **dup:e2351df32666** — Confirmed, folded into the Content-Length Q1 finding above.
- **dup:9a4377c8af1e** — Confirmed as identical copies, folded into the same Q1 finding. With the page and upload copies there are four copies in all.
- **size `_Handler._dispatch` (89 lines)** — The function is a straight run of early returns: host, link, cookie, origin, fixed routes, uploads, pages, then length. Each step is commented, and I found no line where a reader loses the thread. Its real problems are the duplicated length check and the shadowed routes, both reported above.
- **comment census `face.py:1262` "~60 KB"** — True. The client-side cap is `> 60000` at `page_editor.py:1294` (also `editor.py:964`). Searched: `60000|60 KB` in src.
- **comment census `words.py:1668` "404 replies"** — True. `face.forbidden` and `face.link_spent` are the 403 bodies (`face.py:969`, `1015`) and `face.not_found` is the 404 body (`1244`).

## Correctness leads
- `src/pressless/words.py:906` — the user-facing setup step `setup.new_key.5` shows an internal ticket id on screen: *"…to switch your site on (PRESS-0230)."* — Searched: none.
- `src/pressless/face.py:1185` — In `_take_upload`, when a disk write fails partway, the rest of the request body is never drained before the 500 page is sent. `_drain`'s own docstring (974-976) says this resets the connection, so the user may never see the failure page. — Searched: none.
- `src/pressless/face.py:1217` — `_send_download` labels anything not ending in `.zip` as `application/octet-stream`. The only `Download` maker (`sites_screen.py:71`, `file_name` → `….zip`) always produces `.zip`, so that branch is unused, and `_FILE_TYPES` already maps `.zip`. — Searched: `Download(` in src.
- `src/pressless/face.py:299` — `say(entry.what, secret=noun, **slots)` raises TypeError if a failure's `slots` ever holds a `secret` key. — Searched: none.

## Not checked
- I did not open `docs/specs/PRESS-0197` to see whether it quotes the 50 MiB sentences, so that fix's cost is graded unsure.
- I did not search specs for `Step`'s field list (wizard Q5, field-on-`Step` form).
- I judged the embedded CSS only for comments and unstated special cases, not for whether each rule is still used.
- I did not run any tool-class checks, so there are no `[tool?]` items.
