<!-- ants-spec-format: 1 -->
# PRESS-0242 — Every screen's words come from one table

**Status:** spec draft (2026-10-08).
**Kind:** refactor.
**Source:** ROADMAP PRESS-0242 (user request 2026-10-07: the preparation half
of PRESS-0241, wanted before 1.0.0).

**Pairs with:** PRESS-0241, which adds the translations and chooses the
language.

Layman: no visible change; behind the scenes, every word Pressless shows
comes from one list, so adding another language later means translating
that list.

## 1. Goal

After this ships, every word Pressless shows on its own screens, in its
console window and in the sample pages it writes for a new site comes from
one English table, `src/pressless/words.py`. Each word is looked up when it
is shown, so PRESS-0241 can put a second table in front of it. A test fails
when someone writes English straight into a screen. Every page reads exactly
as it does today.

## 2. Problem

1. **The words are spread over most of the modules under `src/pressless`**,
   as constants (`pressing.PUBLISHING`), dictionaries (`face.SENTENCES`,
   which `editor`, `page_editor`, `publishing`, `undo` and `updating` add to
   at import), and f-strings inside page builders. A
   translator would have to find them all, and miss some.
2. **Some words are written twice.** The standing words ("On your site",
   "Changes not published yet", "Not on your site yet") are in
   `editor.py`'s and `page_editor.py`'s page builders and again in their
   scripts, `editor._EDITOR_SCRIPT` and `page_editor._PAGE_SCRIPT`.
3. **The page scripts write English of their own** ("Saving", "Saved",
   "Back to your writing", the `confirm()` questions). Only the press words
   reach a script from Python, and `pressing.SCRIPT` bakes them in when the
   module is imported.
4. **Words fixed at import cannot change language.** `face.SENTENCES`,
   `pressing.SCRIPT` and every module constant hold their words from import
   on, before PRESS-0241 could choose a language.

## 3. Scope decisions (agreed with the user)

1. **In scope: the app's screens, its console lines, and the sample pages
   and templates it writes for a new site.** Decided by the user
   2026-10-08.
2. **The language is chosen in PRESS-0241, by the computer's language, with
   English where there is no translation and a list to choose from where the
   language cannot be told.** Decided by the user 2026-10-08. This item has
   one table, so nothing chooses.
3. **Out of scope: the words the Builder writes on every build of the
   published site** ("Archive", "Older →", month names). The user named the
   sample pages, not these. They follow the site's language, which is a
   separate choice.
4. **Show details, the log, exception messages, git commit messages, the
   self-check line and the command-line tools stay English.** *(decided
   here)* They are read by whoever helps, and searched for online.
5. **A table entry may hold the markup its sentence needs, and names its
   gaps as `{slot}`.** *(decided here)* Splitting a sentence around a
   `<b>` or a link fixes its word order, which a translation cannot keep.
6. **One table, keyed by dotted names grouped by screen** (`setup.key_missing`,
   `press.publishing`). *(decided here)* A key is not the English words, so
   rewording English changes no key.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The table

```python
# src/pressless/words.py — new
ENGLISH: dict[str, str]          # key -> words; the only table

def say(key: str, **slots: str) -> str: ...
    # The words for `key` in the table in use, gaps filled. A key the table
    # in use lacks takes ENGLISH's words. A key ENGLISH lacks, or a gap left
    # unfilled, raises KeyError.

def use(table: dict[str, str]) -> contextlib.AbstractContextManager: ...
    # Puts `table` in front of ENGLISH while the block runs. The tests'
    # seam, and the hook PRESS-0241's language choice uses.

def for_scripts() -> str: ...
    # Every "script." entry, as a JSON object safe inside <script>.
```

`say` inserts slot values as given. Each caller escapes what it passes, as
each f-string does today. A literal brace in an entry is written `{{`.

### 4.2 Where words are looked up

- **When shown, never at import.** A module constant holding words becomes
  a key, or a function returning `say(...)`.
- **`face.SENTENCES`** keeps its keys and shape; a `Sentence`'s `what` and
  `next` hold keys, and `face.sentence_for` looks them up.
- **Notices.** A notice raised by a module that does not import `words`
  (`store.StoreNotice`) carries a key and slots instead of English;
  `face.render_notices` looks it up. `store.py` keeps its imports.
- **Countries.** `_flag_data.NAMES` moves into the table as `country.<code>`.
- **The cheat sheet.** `marks.Mark.explains` moves into the table as
  `mark.<name>`, which `cheatsheet.py`, its only reader, looks up.
  `marks.py` keeps its standard-library-only imports.
- **Sample pages and templates** (`starter.py`, `templates.STARTERS`) take
  their words when they are written into a site, so a site starts in the
  language in use that day.

### 4.3 The page scripts

Every page the Face serves carries one
`<script type="application/json" id="pressless-words">` holding
`words.for_scripts()`. Each script reads its words from there, and a small
`say(key, slots)` in `face._SCRIPT` fills gaps the same way `words.say`
does. No script holds English. `pressing.SCRIPT` stops baking in its words.

### 4.4 Building it

Screen by screen, one commit each, the gate green after every commit. A
commit moves words and changes nothing a page shows. A test that pins a
page's words keeps its expected words; one that reads a script's internals
(`tests/test_page_editor.py` pins the press words' JSON) follows the move.

## 5. Invariants

- **INV-1** — Every page, sample page, notice and console line reads, word
  for word, as before this item.
  *Test:* the existing tests that pin wording, with their expected words
  unedited.
  *Breaks when:* a key's English differs from the string it replaced, or a
  gap is filled with the wrong value.

- **INV-2** — Every word on a page is looked up when the page is shown.
  *Test:* `tests/test_words.py::test_pages_take_their_words_from_the_table`
  — under `words.use` with a table giving every key a marked form, render
  each page the tests can reach (the list, both editors, the holding page,
  each setup step, Settings, the dashboard, the report, the cheat sheet,
  the template list, a failure, a notice) and seed a starter site; strip
  markup and the writer's own content; no word outside a marker remains.
  *Breaks when:* a module fixes its words at import, or a page builder
  writes English itself.

- **INV-3** — No screen module or page script writes English itself.
  *Test:* `tests/test_words.py::test_no_screen_writes_english` — over every
  module under `src/pressless` that imports `face` or `words`, plus
  `starter.py` and `templates.py`, walk the string literals that are not
  docstrings, exception messages or log lines; strip markup, keeping the
  values of `title`, `alt`, `placeholder` and `aria-label`; in a script,
  take its string literals. A run of two words, or one capitalised word, is
  English. An allowlist in the test names each exception and why.
  *Breaks when:* someone adds `"Saved"` to a script or
  `f"<p>Nothing here</p>"` to a page builder.

- **INV-4** — Every key asked for is in `ENGLISH`, and every `ENGLISH` entry
  is asked for.
  *Test:* `tests/test_words.py::test_every_key_is_in_the_table` and
  `::test_every_entry_is_used` — literal keys passed to `say`, to a
  `Sentence`, to a notice or read by a script, against the table; a key
  built from a prefix (`country.`, `mark.`) counts for its family.
  *Breaks when:* a key is misspelled, or a moved string leaves its old entry
  behind.

## 6. Failure modes

- **A key the table lacks** raises `KeyError` where the page is built; the
  Face shows its unforeseen failure. INV-4 stops this reaching a release.
- **A gap left unfilled** raises the same way.
- **The words block missing from a page** leaves its script without words;
  every page gets it from the Face's page chrome, so only a page built
  outside the chrome could lack it.
- **INV-3's test misses one-word lowercase English** ("saving"). INV-2 still
  catches it on any page the tests render.

## 7. Tests

`tests/test_words.py` is new and holds INV-2, INV-3 and INV-4. Each is seen
failing against the code before this item. INV-1 rests on the existing
wording tests across the suite.

## 8. Alternatives considered (and rejected)

- **`gettext`, keyed by the English sentence.** Rewording English then
  changes the key and orphans every translation, and gettext does not reach
  the page scripts.
- **A table per module.** Not one place; a translator still hunts twenty
  files.
- **Splitting sentences around markup.** Fixes English word order into every
  language (decision 5).
- **The static check alone.** It cannot see words frozen at import; INV-2
  can.

## 9. Out of scope

- Translations and choosing the language — tracked by PRESS-0241.
- The Builder's words on the published site — deferred; not yet queued.
- Show details, the log, exception messages, commit messages and the
  command-line tools (decision 4).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | Partial: the existing wording tests; a branch no test renders is checked by **nothing** |
| INV-2 | Partial: `tests/test_words.py::test_pages_take_their_words_from_the_table`, over the pages it renders |
| INV-3 | Partial: `tests/test_words.py::test_no_screen_writes_english`; one lowercase word passes it |
| INV-4 | `tests/test_words.py::test_every_key_is_in_the_table`, `tests/test_words.py::test_every_entry_is_used` |
| § 4.4 one screen per commit | **nothing** — commit review |

## 11. Cross-doc impact

- `docs/design.md` § The parts — a row for the words table.
- `docs/specs/PRESS-0011-face.md` — `SENTENCES` holds keys (§ 4.2) and pages
  carry the words block (§ 4.3).
- `docs/specs/PRESS-0235-press-status.md` § 4.3 — the press words' home
  moves from `pressing.py` to the table.
- PRESS-0241's roadmap body — the user's 2026-10-08 language decision.
- `CHANGELOG.md` — none; nothing a user sees changes.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0242-screen-words-loop-log.md`.
