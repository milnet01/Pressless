## Files read
- `src/pressless/builder.py`: all 1226 lines read
- `src/pressless/look.py`: all 517 lines read
- `src/pressless/look_screen.py`: all 315 lines read
- `src/pressless/publisher.py`: all 1183 lines read
- `src/pressless/publishing.py`: all 438 lines read
- `src/pressless/pressing.py`: all 167 lines read

## What I started with
- The global `~/.claude/CLAUDE.md`.
- The review-lane agent file.
- A startup hook note saying the Ants MCP verbs were connected.
- No memory index, no project `CLAUDE.md` and no git snapshot.
- Then I read the shared-context brief (STEP 1).

I resolved one disagreement between the lane file and the brief. The lane file says to open with line counts. The brief's format asks for "lines read / total" under *Files read*. I followed the brief's form, and it gives the same numbers.

## Summary
This code turns his writing and his settings into a finished website folder. The Builder writes every page, picture and listing, and swaps the new folder in only when it is complete. The Look files make the site's colours, fonts and layout, and show a live preview while he changes them. The Publisher makes his GitHub repository match that folder: it uploads what changed, removes what is gone, and can fetch back the previous version for undo. Publish ties it together behind one button, and the running-press record lets any open page show that a publish or undo is under way.

## Findings

[Q1] HIGH `publisher.py:201` — `class _NoCrossOriginAuth(urllib.request.HTTPRedirectHandler):`
- **The problem.** `_NoCrossOriginAuth`, `_origin`, `_Urllib` and `_no_answer` are copied whole in `insights.py:195-306`. The copies already differ in their docstrings and in `wait` versus `now`. Two past fixes had to patch both copies: both carry the same PRESS-0135 comment (the error body read under the guard) and the same PRESS-0142 comment (certifi).
- **What a stranger gets wrong.** INV-1 forbids sharing the code, so it stays copied. `insights.py` points back here ("for the reason publisher.py gives"), but nothing in `publisher.py` names the twin. Someone fixing the redirect handler that strips the key, which is security code, would fix it here and leave `insights.py` open.
- Fix: put a comment on each of the four copies in `publisher.py` naming its `insights.py` twin and INV-1, as `credentials._why` already does.
- Cost: one edit (comment only).
- Confirms dup:cfea936c5d6b, dup:2219d0a65502 and dup:5670ccf581b4.
- Searched: read `insights.py:180-310`. In docs, `_NoCrossOriginAuth` is named only in PRESS-0023 and PRESS-0122, and neither ties the pair together.

[Q1] MEDIUM `publishing.py:150` — `def captured(step: Callable[[], _T]) -> _T:`
- **The problem.** The "capture a step's notices and add them to a list" helper exists five times:
  - `publishing.py:150` and `publishing.py:324`
  - `undo.py:89` and `undo.py:514`
  - `page_editor.py:931`, already pulled out there as `_gatherer`
- **What a stranger gets wrong.** A change to how notices are gathered (for example, also gathering on an exception path) would be made in one copy and missed in four.
- Fix: have all five use one shared `_gatherer`.
- Cost: one edit. Searched: `_gatherer` in docs (no hits).
- Confirms dup:a7914cd27d9c, dup:d9e64d75ba0a and dup:e7d15d913ec3.

[Q1] MEDIUM `look_screen.py:43` — `# Each choice's words keys, in look.py's order.`
- **The problem.** `_COLOUR_WORDS`, `_FONT_WORDS`, `_SIZE_WORDS`, `_WIDTH_WORDS` and `_EFFECT_WORDS` are hand-kept copies of `look.COLOURS`, `FONTS`, `TEXT_SIZES`, `WIDTHS` and `EFFECTS`. They match today. `look.py` does not point back to them.
- **What a stranger gets wrong.**
  - Adding a font, size or width to `look.py`: the screen's dropdowns iterate the words dicts, so the new option is never offered and no error says why.
  - Adding a colour: the page fails with a `KeyError` when drawn.
- Fix: build each dict from `look.py`'s tuple, since every key is `look_screen.<kind>.<name>`.
- Cost: one edit. Searched: `_COLOUR_WORDS|_FONT_WORDS` in docs (no hits).

[Q4] MEDIUM `publisher.py:693` — `# The reference update is the one request whose failure`
- **The problem.** `outcome_unknown=True` is also passed for the start-file PUT (`:345`) and the `.nojekyll` PUT (`:513`), so "the one request" is false. The class docstring `OutcomeUnknown` (`:115`, "The reference update was attempted") and the message at `:765` ("to the reference update") make the same claim.
- **What a stranger gets wrong.** Trusting the comment, they would edit `outcome_unknown` handling while reasoning only about the PATCH, and miss the two Contents API writes.
- Fix: say "a write that may have moved the branch" (the reference update, the start write, `.nojekyll`) in all three places.
- Cost: one edit (comment only).

[Q4] MEDIUM `builder.py:35` — `ROOT_OUTPUT = ("index.html", "pages", "blog", "photographs", "content",`
- **The problem.** `ROOT_OUTPUT` must list every top-level name the Builder writes. Nothing beside it says so, and it repeats the literal `"site-icon.png"` rather than using `SITE_ICON`.
- **What a stranger gets wrong.** Someone adding a new root file or folder writes it and builds once. Every later build then refuses the site folder ("holds X, which Pressless does not make"), and `setup` and `KeptFolderBuilt` misjudge it. The rule exists only in PRESS-0008 § 4.1.
- Fix: a one-line comment that every root path written must be listed here; use `SITE_ICON` in the tuple.
- Cost: pinned for the tuple. PRESS-0008 line 98 quotes the tuple, and PRESS-0126, PRESS-0197 and PRESS-0227 name it. The comment alone is one edit.

[Q5] MEDIUM `builder.py:676` — `if self.photo_src is None:      # PRESS-0227 § 4.3`
- **The problem.** "Publishing build versus preview" is decided by `photo_src is None` at about eight sites (`:618`, `:711`, `:772`, `:781`, `:800`, `:821`, and `build`'s `_replace(..., photo_src is None, ...)`). No name in the code says that.
- **What a stranger gets wrong.** Someone adding a new preview path that passes `photo_src=None` would get the Google tag, the icon, `pieces.js` and real picture copies in the preview.
- Fix: a named `publishing` property on `_Build`, used at every site.
- Cost: pinned — PRESS-0227 lines 104-105 name `photo_src is None` as the test.

[Q3] MEDIUM `builder.py:230` — `today: date | None = None, marks: bool = False) -> str:`
- **The problem.** Several parameters and locals hide module imports of the same name:
  - the parameter `marks` hides the `marks` module here and in `_Build.fixed_page` (`:705`)
  - the parameter `html` hides the `html` module in `furniture_spans` (`:445`)
  - the local `blocks = []` hides the `blocks` module in `archive` (`:1030`)
  - the local `label` hides the module-level `label()` in `card` (`:958`)
  - the parameter `settings` hides the `settings` module in `publishing.publish` (`publishing.py:140`)
- **What a stranger gets wrong.** Adding `marks.parse(...)`, `html.escape(...)` or `settings.load(...)` inside one of these bodies fails with an `AttributeError` on a bool or str.
- Fix: rename the locals and parameters (`keep_marks`, `text`, `sections`, `heading`).
- Cost: pinned for `marks`, because PRESS-0260 (about line 336), PRESS-0215 and PRESS-0216 name `preview_html(..., marks=True)`. The others are one edit; I searched docs for `marks=` and found no spec naming the other locals.
- [tool?: redefined-outer-name]

[Q5] MEDIUM `builder.py:755` — `{self.furniture.fill("HEADER", depth, page="Journal")}`
- **The problem.** Every generated page (entry, listing, archive) marks the menu link whose `data-nav` is `"Journal"` as the current page. Nothing in `src` writes `data-nav="Journal"`. `menu._nav` gives only `"Home"` or a fixed page's name, and the starter writes `Home` and `about`.
- **What a stranger gets wrong.** They cannot tell where `"Journal"` comes from, or whether renaming the journal link breaks it.
- Fix: a comment naming which menus carry `data-nav="Journal"` (presumably imported ones).
- Cost: one edit (comment only).
- Searched: `data-nav=` in `src`, and `_nav` in `menu.py`.

[Q5] MEDIUM `pressing.py:94` — `done = ended[-1].said in (say("script.press.published"), say("script.press.undone"))`
- **The problem.** Whether a press succeeded, for the usage report, is decided by comparing the displayed words.
- **What a stranger gets wrong.** Changing what a successful publish says (for example, a "published, with a note" outcome), or adding a third press kind, would quietly count successes as failures.
- Fix: give `Outcome` a success flag that `run` reads.
- Cost: unsure. I searched docs for `pressing.Outcome` and `Outcome(said` and found no hits, but PRESS-0235 § 4 may define `Outcome`'s shape under another spelling.

[Q4] MEDIUM `look.py:216` — `def made_here(folder: Path) -> bool:`
- **The problem.** `made_here` compares the saved style code byte for byte with `css(...)`'s output today. That output includes the three CSS layout strings and three words-table notes (`look.style_note` and the others). Nothing says that changing any of them (a focus-ring fix, a reworded note) turns every existing site into "style code the choices did not make". Its next save then copies it into the bin and shows the "replaces" warning.
- **What a stranger gets wrong.** They would make what looks like a harmless CSS or wording change.
- Fix: a comment on `css()` and on `_SUNRISE`/`_MEADOW`/`_HARBOUR` stating this constraint.
- Cost: one edit (comment only).

[Q1] LOW `look.py:311` — `a { color: var(--link); text-decoration: underline; text-underline-offset: 0.15em; }`
- **The problem.** The link, focus-ring, header-link, `.site-description:empty`, `nav.primary a` and `img` rules are written out three times, once in each layout. The two other copies are at `:362-375` and `:424-441`.
- **What a stranger gets wrong.** The PRESS-0239 promise (underlined links, a visible focus ring) has to be changed in three places. All three sit in one file, so a stranger would likely notice.
- Fix: one shared rules block emitted before the layout's own rules.
- Cost: unsure. It changes `css()` output, which carries the `made_here` constraint above. I did not read PRESS-0196 § 4.2's order to see whether it allows a shared block. Searched: `_SUNRISE` in docs (no hits).
- Confirms dup:07ecd2d2aef2 and dup:bfc26a93e6d4.

[Q4] MEDIUM `builder.py:916` — `and centred, refused as web_copy refuses one."""`
- **The problem.** `icon_copy` does not refuse what `web_copy` refuses:
  - no dot-name check
  - no check that the format is one Pressless publishes; any format Pillow opens is turned into PNG

  The shared part is only the "not in the photographs folder" check (`:877-879` / `:917-919`).
- **What a stranger gets wrong.** Trusting the docstring, they would assume a BMP or dot-named icon is refused.
- Fix: say which refusals apply, or that the icon accepts any picture Pillow reads.
- Cost: one edit (comment only).
- Confirms dup:f1e3e239e09d as diverged.

[Q3] LOW `publishing.py:186` — `def finish() -> bool:`
- **The problem.** It returns True when binning the working copy *failed* (`copy_kept`).
- **What a stranger gets wrong.** Reading `if finish():` at `:213` as "finished cleanly". The `Published.copy_kept` field nearby corrects them.
- Fix: rename to something like `bin_copy_failed`.
- Cost: one edit. Searched: `finish\(\)` in docs; the only hit is a review log, not a spec.

[Q3] LOW `publishing.py:169` — `entry.rstrip("/").casefold() in _A_SITE`
- **The problem.** The generator variable `entry` (a name at the repository root) hides the parameter `entry` (the slug) of the same function.
- **What a stranger gets wrong.** Reading it as the slug.
- Fix: rename to `name`.
- Cost: one edit (local name).

[Q3] LOW `look_screen.py:76` — `def _has_style_code(folder: Path) -> None:`
- **The problem.** A "has" name that returns None and raises.
- **What a stranger gets wrong.** Writing `if not _has_style_code(folder):`, which is always true. The docstring on the next line corrects them.
- Fix: rename to `_refuse_without_style_code`.
- Cost: one edit. Searched: `_has_style_code` in docs (no hits).

[Q1] LOW `look_screen.py:268` — `if (link.href.endsWith("look/style.css")) link.disabled = true;`
- **The problem.** This is a hand copy of `builder.STYLE_CODE` inside the script.
- **What a stranger gets wrong.** Moving `STYLE_CODE` leaves the preview showing both stylesheets, with no error.
- Fix: put `builder.STYLE_CODE` into the script text.
- Cost: one edit.
- Searched: `look/style\.css` in `src`. It also appears in `starter.py:59`, as a link.

[Q1] LOW `publisher.py:589` — `raise FetchNotWritten(`
- **The problem.** The same message is built three times in `fetch_previous` (`:589`, `:619`, `:633`).
- **What a stranger gets wrong.** Rewording one and missing another. All three are within 50 lines, so it would likely be noticed.
- Fix: one small helper inside `fetch_previous`.
- Cost: one edit. Searched: `FetchNotWritten(` in docs; only the class declaration in PRESS-0009 matches.
- Confirms dup:c84820de44d7.

[Q3] LOW `builder.py:83` — `def _entries(count: int) -> str:`
- **The problem.** It returns the text "N entries", not a list of entries. `publisher._entries` returns paths.
- **What a stranger gets wrong.** Guessing a list. The call sites, inside f-strings, correct them.
- Fix: rename to `_entries_text`.
- Cost: one edit (private).

[Q4] LOW `pressing.py:60` — `"""An ended outcome stops being shown: a save, OK on its failure box, the journal switch or a Settings save`
- **The problem.** The docstring lists the callers. `publishing._replace_page` (`publishing.py:422`, PRESS-0272) also calls `forget()` and is not in the list.
- **What a stranger gets wrong.** Trusting the list as complete.
- Fix: drop the caller list, or add the replace page to it.
- Cost: one edit (comment only).
- Searched: `pressing\.forget\(` in `src`: `page_editor` 390 and 1054, `setup` 320, `editor` 331 and 636, `publishing` 422.

## Candidates dismissed
- **dup:076b9c51df39** — import lists, not behaviour.
- **dup:850a6de8538e** — `credentials._why` says it is deliberately duplicated under INV-1. `publisher._why` is the same INV-1 case, and is covered by the broader publisher/insights finding. There are also copies in `builder.py:334`, `settings.py:114` and `store.py:624`. `builder._why` has no INV-1 restriction, but each copy is only two lines, so it is taste.
- **size `publisher.py:299` `publish`** — long, but each phase (start commit, diff, refuse emptying, four writes) has a comment. I found no point where a reader loses the thread.
- **size `publisher.py:672` `_Session._call`** — a flat chain of status cases, each commented. Followable.
- **size `publisher.py:542` `fetch_previous`** — staged write, then move, both commented. Followable.
- **size `publishing.py:140` `publish`** — the nested try with `interrupted` (`:196-219`) is dense but commented. The one real snag is `finish()`'s name, filed under Q3.
- **comment `publisher.py:49` "550 blob creations"** — a dated measurement record, not a count that changes.
- **comment `publisher.py:69` "6 already gives"** — the tool misread "§6 already gives"; it is a section reference.
- **comment `publisher.py:772` "404 keeps"** — "a 404 keeps its own" type. Accurate.

## Correctness leads
- `builder.py:755` — journal pages pass `page="Journal"`, but no menu Pressless writes carries `data-nav="Journal"`. On starter-built or menu-edited sites, the Journal link is never marked current. Searched: `data-nav=` in `src`; `menu._nav`.
- `publisher.py:765` — the `OutcomeUnknown` message says "to the reference update" even when the request was the start-file or `.nojekyll` PUT, so the user is shown the wrong request. Searched: `outcome_unknown=True` in `src`.
- `look.py:216` / `look.py:284` — `css()` puts `say('look.style_note')` (and two other notes) into the saved style code. Editing that words-table text makes every site's saved look read as "not made here", and its next Look save bins it. Searched: none beyond this file.
- `builder.py:1067` — a forwarding page is written under the *new* entry's date folder, on the assumption that the old address shared that date. If a rename can change the date, the forward lands at an address nobody had. Searched: none; I did not read `store.read_forwards` or PRESS-0182.

## Not checked
- PRESS-0196 § 4.2's wording on CSS order, so the cost of the shared-rules fix stays "unsure".
- Whether `editor._form`, `editor._failed` and `editor._json` (private names used from `look_screen.py`) are meant to be used from outside `editor`. I did not search `editor.py` for them.
- The embedded script in `look_screen.py` calls a global `say(...)`. I did not confirm where it is defined.
- PRESS-0235's definition of `Outcome`, for the cost of the success-flag fix.
