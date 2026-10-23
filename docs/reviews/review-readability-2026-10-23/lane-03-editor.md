I found 20 readability problems in the editor lane and 4 likely bugs. None is HIGH; the worst are MEDIUM. The bugs are listed under *Correctness leads* and are not graded.

## Files read
- `src/pressless/editor.py` — 1106 / 1106
- `src/pressless/marks.py` — 786 / 786
- `src/pressless/templates.py` — 190 / 190
- `src/pressless/photographs.py` — 124 / 124
- `src/pressless/files.py` — 43 / 43
- `src/pressless/files_screen.py` — 130 / 130

Outside the lane I read only small parts of other files, to confirm candidates or grade a cost: `page_editor.py` (lines 30–60, 395–410, 480–530, 820–835, 1040–1062, 1235–1260, 1375–1440, and the body of `_name_refused`) and `publishing.py` (lines 25–50). Everything else came from searches.

## What I started with
- The global `~/.claude/CLAUDE.md`.
- The user's email, attached by the harness.
- The review-lane agent file (my own instructions).
- A start-up message saying the Ants MCP was connected.
- Then this brief and its shared context.

There was no project `CLAUDE.md`, no memory index and no git snapshot.

## Summary
This code is the writing side of Pressless.
- **`editor.py`** draws the list of entries and the editing screen. It saves the writing about a second after typing stops and rebuilds the preview beside it. Changes to a published entry go into a separate "working copy" until they are pressed to the site.
- **`marks.py`** is the small styling language: bold, colours, pictures, quotes, links. It holds one table of the marks, turns typed text into structure, and turns that structure into web-page HTML.
- **`templates.py`** keeps starter shapes for a new entry.
- **`photographs.py`** and **`files.py`** store uploaded pictures and other files under safe names.
- **`files_screen.py`** lists the stored files and refuses to remove one that a page still uses.

## Findings

[Q4] MEDIUM `editor.py:801` — `# The page's script (§ 4.7). A change saves about a second after the last one,` — This comment sits over `_UNDO_SCRIPT`. Its first two sentences describe the autosave, which lives in `_EDITOR_SCRIPT` at 861; the rest describes the undo script. A stranger looking for the autosave timing would read the wrong script. Nothing sits above `_EDITOR_SCRIPT` to correct them. — Fix: move the autosave sentences above `_EDITOR_SCRIPT` and keep only the undo half here.
Cost: one edit (comment only).

[Q1] MEDIUM `editor.py:1057` — `while (inFlight) await new Promise((resolve) => setTimeout(resolve, 100));` — "Wait for any save in flight" is written out three times in `_EDITOR_SCRIPT`: publish (971–975), address (1056–1059) and throw (1086–1090). The copies have drifted:
- publish and throw then set `inFlight = true` to block later saves;
- address does not;
- `page_editor.py` has a single `settle()` doing this job.

A stranger fixing the wait in one handler would miss the others, and cannot tell whether address leaving `inFlight` unset was meant. — Fix: one `settle()` in `_EDITOR_SCRIPT`, as `page_editor` has, with the `inFlight` choice stated once.
Cost: unsure — `tests/test_editor.py:807` and `tests/test_pressing.py:265` read `editor._EDITOR_SCRIPT` as a value. I did not read what they assert about its text. Docs search for `_EDITOR_SCRIPT`: specs PRESS-0242 and PRESS-0235 name the script, not its handlers.
dup:07ba3fef1681

[Q1] MEDIUM `editor.py:988` — `if (reply.busy) {` — The handling for "another press is running, keep asking" (PRESS-0235) and for "turn the View site button on" (PRESS-0234) is copied in four places:
- `editor.py:984–1000` (publish);
- `page_editor.py:1382–1400` (publish);
- `page_editor.py:1431–1437` (Remove/Rename);
- `editor.py:845` (undo, in `_UNDO_SCRIPT`).

Each copy carries the same ticket comment, which shows each feature had to be added to every copy. The copies have drifted: the page editor's Remove/Rename copy does not set `dirty = true`, and the page publish sets `offSite` and calls `posted.saved`. A stranger changing what a busy reply does would fix one or two copies. — Fix: put the busy-reply and View-site steps in `pressing.SCRIPT`'s `window.presslessPress` and call them from each handler.
Cost: unsure — same script-reading tests as above (`test_editor.py:807`, `test_pressing.py:265–266`), not read.
dup:ddec6d16246b, dup:0b513ee26e27

[Q1] MEDIUM `photographs.py:110` — `text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")` — There are two copies of "turn a name into a web address", and they have drifted:
- `editor.name_address` (118–122) first removes control and format characters (Unicode categories Cc, Cf). So `a<TAB>b` becomes `ab`.
- `photographs._plain` (109–111) turns them into `-`. So `a<TAB>b` becomes `a-b`.

The keeping of `_` is documented; the control-character difference is stated nowhere. `photographs.LONGEST_NAME = 60  # … as a new entry's address` is also a hand-kept mirror of `editor.LONGEST_ADDRESS = 60`. A stranger changing either rule or the length would change only one. — Fix: one shared normaliser with each difference passed in and named, or a comment on each copy naming the difference.
Cost: pinned — PRESS-0012 (`address_for` / `name_address` / `free_address` and the Cc/Cf rule) names `name_address`. PRESS-0195 §§ 4.3–4.4 call `editor.name_address`. Searched: `normalize("NFKD"` in `src` — a third copy is at `src/pressless_import/__init__.py:114`, not read.

[Q1] LOW `templates.py:168` — `name = wanted if number == 1 else f"{wanted}-{number}"` — The `name`, `name-2`, `name-3` loop exists three times: `editor.free_address` (133), `templates._new` (168) and `photographs.keep` (87). The rules for when a name counts as free differ on purpose, and `_new`'s docstring says why. But the copies also differ when the Store refuses a name, such as a Windows device name like `con`: `free_address` and `keep` skip on to `-2`, while `_new` fails the whole request. Nothing says this difference is meant. — Fix: a comment in `_new` naming the refused-name difference, or catching it as the others do.
Cost: pinned — PRESS-0012 names `free_address`; PRESS-0017 § 4.5 describes the template `-2`, `-3` rule. Searched: `-\{number\}` in `src`.

[Q3] MEDIUM `editor.py:191` — `def _named(folder: Path, draft: str) -> str | None:` — Three helpers with near-identical names all answer "which entry does this draft replace?":
- `_named(folder, draft)` reads the draft from disk;
- `_replaces(entry)` gives the raw `Replaces` value;
- `_replaced(folder, entry)` gives it only where it names an entry that is really published.

`_replaces` and `_replaced` differ by one letter but differ in checking. A stranger who uses `_replaces` where `_replaced` is meant would treat an ordinary draft as a working copy. `_named` says nothing of what it names. — Fix: names that say the difference, e.g. "replaces header", "replaced published entry", "draft's replaces header".
Cost: pinned — PRESS-0015 names `editor._replaced`. Docs search for `_named\b` and `_replaces\b`: no hits.

[Q3] MEDIUM `editor.py:272` — `def _failed(face: Face, notices: list[str], failure: Exception) -> Reply:` — Several underscore helpers in `editor.py` are really shared across modules:
- `_form`, `_failed`, `_json`, `_digest` and `_names_of` are used by `templates.py`, `files_screen.py`, `look_screen.py` and `page_editor.py`;
- `_RUNNING` and `_UNDO_SCRIPT` are used by `page_editor.py`.

`page_editor.py` meanwhile keeps its own identical `_failed`, `_json` and `_digest`. The underscore tells a stranger only `editor.py` calls these. They would change a signature, break four other screens, and could not tell which `_failed` is the real one. — Fix: drop the underscore on the shared helpers, or move them to a shared module, and delete `page_editor`'s copies.
Cost: pinned — PRESS-0017 names `editor._names_of`; PRESS-0235 and PRESS-0242 name `editor._UNDO_SCRIPT` / `_EDITOR_SCRIPT`; tests use `editor._EDITOR_SCRIPT`, `_UNDO_SCRIPT`, `_site_line`, `_pages` and `page_editor._digest`. Searched: `editor\._[a-z_]+` across the tree.

[Q2] MEDIUM `editor.py:390` — `return (render_notices(notices) + failure +` — In `_list`, a stranger loses the thread here. The return is one 27-line expression mixing `+` and f-strings, with ticket comments between its parts. Just before it, lines 362–370 work out `changed`, `drafts`, `undone` and `notes` in dense set logic that the nested `rows` closure then reads. To add one card, the stranger has to find which part of the expression to edit and which sets feed it. — Fix: build the page from named parts (header, new-entry form, press row, cards) joined once.
Cost: unsure — PRESS-0014, 0214, 0015, 0023 and 0017 each describe what `editor._list` shows. Splitting keeps the name, but I could not tell whether those specs require it to draw those parts itself.
size `src/pressless/editor.py:335:_list`

[Q2] MEDIUM `editor.py:703` — `if hint is None and entry is not None and address != slug:` — In `_address`, the thread breaks here. The refusal chain above (686–702) and the move below (704–725) share one `try`, and the move re-tests `address != slug` that the chain already branched on. `forwards` is read at 698 only for a hint, then read and rebuilt at 712–716 for the move. A stranger adding a refusal cannot tell whether it must also stop the move. — Fix: split into "why this address is refused" and "move the entry", with the second run only when the first says nothing.
Cost: pinned — PRESS-0182 names `editor._address`.
size `src/pressless/editor.py:674:_address`

[Q5] LOW `editor.py:680` — `draft = form.get("draft", "1") == "1"` — When no `draft` field is posted, `_address` treats the entry as a draft. `save` (617) and `_throw` (766) treat it as published. Nothing says why. A stranger making the three routes consistent cannot tell which default is safe. — Fix: a comment giving the reason, or one default for all three.
Cost: one edit (comment) — a behaviour change is out of my scope.

[Q3] LOW `editor.py:542` — `published, waiting = (" hidden", "") if proof else ("", " hidden")` — These two hold HTML ` hidden` attribute text, not yes/no flags. In `_list`, `published` is a set of slugs. A stranger would read `if published` as "is it published". — Fix: name them for what they hold, e.g. "published hidden".
Cost: one edit — local variables. No spec names them; searched docs for the function names above.

[Q4] LOW `editor.py:53` — `UNDONE = "Undone"                   # publishing.UNDONE, the mark undo leaves` — The comment reads as if this copies `publishing.UNDONE`. In fact `publishing.py:54` is `UNDONE = editor.UNDONE`, so this line is the original. A stranger changing the value would go to `publishing.py` first. — Fix: say that publishing takes it from here.
Cost: one edit (comment only).

[Q1] LOW `editor.py:202` — `return next((value for name, value in entry.extra if name == REPLACES), None)` — The same lookup is written out at `publishing.py:246` and `publishing.py:373` instead of calling `_replaces`. That makes three copies; they are identical today. — Fix: call one helper from all three.
Cost: one edit — Searched: docs for `_replaces\b` (no hits); `publishing.py` lines 246/373 found by searching `REPLACES` in `src`.

[Q4] LOW `marks.py:263` — `name: str  # Span.mark / Photo.mark / Quote.mark` — It leaves out `Value.mark`. On line 266, `closes … # None for a block or prefix mark` leaves out value marks, which also have `closes=None`. A stranger adding a value mark would think a closer is required. — Fix: add `Value` to both comments.
Cost: one edit (comment only).

[Q4] LOW `marks.py:89` — `"""A quotation. It carries `mark` for the reason Photo does,` — `Photo`'s docstring (67–68) gives no reason for carrying `mark`, so this points at nothing. — Fix: state the reason (`to_html` finds the renderer by `mark`) in one of the two places.
Cost: one edit (comment only).

[Q4] LOW `marks.py:539` — `@functools.lru_cache(maxsize=32)` — The docstring explains the right-to-left pass but not the cache. Yet the cache is what keeps it fast: `_closes_at` is asked at every position on a line, and each uncached call rebuilds the whole table, which brings back the slowdown PRESS-0162 fixed. A stranger tidying decorators would remove it. — Fix: a comment saying the table is built once per row and line and reused for every position.
Cost: one edit (comment only).

[Q5] LOW `marks.py:647` — `return Photo(mark=row.name, name=matched["name"], caption=matched["caption"])` — `_as_block` loops over every block row, but it always builds a `Photo` from `name` and `caption` groups. It also skips any block row without an argument pattern (`arg`). This holds only because photo is the one block row, and the comment at 279–280 states the named groups for photo alone. A stranger adding a second block mark would get a `Photo`, or a `KeyError`. — Fix: a comment on the table or `_BLOCK_MARKS` that every block row needs an `arg` with `name` and `caption` groups.
Cost: one edit (comment only).

[Q3] LOW `marks.py:581` — `def _try_wrap(text: str, i: int, depth: int) -> tuple[Span | Value, int] | None:` — It also forms value marks, which have no closer. Its docstring on the next line says so, hence LOW. — Fix: a name covering both, such as "try inline".
Cost: unsure — `tests/test_marks.py:447` checks `marks.py`'s calls against an allowlist, and I did not read whether that list names this function.

[Q4] LOW `photographs.py:82` — `staged = _stage(path_for(FALLBACK).parent, data)` — It uses a dummy name (photographs' `FALLBACK`) only to find the folder. It does the same when `files.add` calls it, where `FALLBACK` would be `"file"`. A stranger would think the fallback name matters here, or would "fix" it for `files`. — Fix: a comment saying the name only locates the folder.
Cost: one edit (comment only).

[Q3] LOW `files.py:41` — `return photographs.keep(lambda name: store.file_path_for(folder, name), data,` — The first lambda's argument `name` hides the outer `name`, and the next lambda (`lambda staged: name`) returns the outer one. A stranger editing either would mix up which `name` is meant. — Fix: rename the outer variable, e.g. "kept name".
Cost: one edit — local.

## Candidates dismissed
- **dup:076b9c51df39** — import lists, not behaviour.
- **dup:ce0f37967d36** — the shared "catch, capture the failure, reply 409" pattern. Each route catches what it can raise: `_discard` leaves out `TooManyCopies` because `_replaced` cannot raise it, and `_photograph`/`_upload` add `OSError` for the file write. This is not one behaviour that drifted.
- **dup:797632e2ba38** — two identical copies with no comment showing a fix patched both. The real problem is reported under Q3 (`editor.py:272`).
- **dup:d81b7676150a**, **dup:bba7f8636431** — two identical JS copies each, with no comment showing a fix patched both.
- **comment `marks.py:293`** "10 refuses" — "decision 10" is a decision's number, not a count.
- **comment `marks.py:447`** "4 matches" — "§4.4 step 4" is a step number.
- **comment `marks.py:471`** "6 promises" — "§6" is a section number.
- **`editor.PAGE_HINTS` vs `page_editor._name_refused`** (my own check, not a candidate) — the codes match (`empty`, `unusable`, `taken`, `forwarded`), and the docstring points at `PAGE_HINTS`.
- **`pressing.SCRIPT` included twice on the editor page** (my own check) — the script uses `window.presslessPress || …`, so the second copy changes nothing. Not a problem.

## Correctness leads
- `editor.py:492–496` — In `_new`, `free_address` (which reads the address-forwarding file) and `store.write` sit outside the `try`. A `StoreError` from either escapes uncaught instead of showing the 409 failure page. — Searched: read `_new`; `free_address` calls `store.read_forwards` at line 130.
- `editor.py:1062` — The address button does not set `inFlight = true` before posting `/address`. A save scheduled during that request can post the old slug and base at the same time. — Searched: compared with publish (975) and throw (1090).
- `editor.py:902` — `addressField.hidden = false` uses `addressField` without the null check line 890 makes. Either the check is dead or this line can throw. — Searched: `_address_field` is always rendered by `_page` (559, 580).
- `templates.py:169` — `store.template_path_for` raising on a refused name, such as `con`, fails the New template request instead of trying `con-2`. — Searched: `-\{number\}` in `src`; PRESS-0017 § 4.5's wording "until no file exists" (headline only).

## Not checked
- `src/pressless_import/__init__.py:114`, a third copy of the name normaliser — not read.
- What `tests/test_editor.py:807` and `tests/test_pressing.py:265` assert about the script strings. This leaves three fix costs unsure.
- `page_editor.py` scripts beyond the windows cited.
- `builder.files_named`, so I could not judge whether `_FURNITURE_WORDS` in `files_screen.py` should also list navigation.
- What `store.move_to_bin` does with a missing file in `files_screen._remove`.
- Full spec text: I searched specs by headline only, so the "pinned" grades rest on the name appearing, not on reading the section.
