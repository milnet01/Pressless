<!-- ants-spec-format: 1 -->
# PRESS-0241 — Pressless speaks Spanish, Afrikaans, French and German

**Status:** accepted (2026-11-18). One review round, the user's budget for a
new spec; its fixes were read by no lane.
**Kind:** feature.
**Source:** ROADMAP PRESS-0241 (user request 2026-10-07).

**Pairs with:** PRESS-0242, which put every screen's words in one table
(`docs/specs/PRESS-0242-screen-words.md`).

Layman: Pressless shows its screens in your computer's language, and each
website you make speaks its own language to its readers.

## 1. Goal

After this ships, Pressless shows its screens, its manual and its console
lines in Spanish, Afrikaans, French or German when the computer is set to
one of them, and in English otherwise. The writer can choose another
language from the top bar. Each site has a language of its own, which the
words Pressless writes onto the published site follow: dates, "Archive",
"Older →", the sample pages. A site made before this item reads, byte for
byte, as it does today.

## 2. Problem

1. **One table, no second.** `words.use` can put a table in front of
   `words.ENGLISH`, but no translation exists and nothing calls it outside
   the tests.
2. **Dates come from the C library or a fixed English list.** The
   dashboard (`dashboard._day_name`, `dashboard.when`) and the list
   (`editor.py`, an entry's `{entry.date:%d %b %Y}`) use `strftime`'s `%a`
   and `%b`. The Builder uses `builder._MONTHS`.
3. **The Builder writes English of its own.** `builder._entries_text`,
   `_Build.listing`'s "Page … of …" and "Older →", `_Build.listings`' "The
   journal", `_Build.archive`'s "Archive" and "All … by year",
   `_Build.comments`' note, and `builder._forward_page`'s "This … has
   moved". PRESS-0242 decision 3 left these to this item.
4. **Every page says `lang="en"`**: `face._page`, `builder._forward_page`,
   `_Build.page`, and the sample pages in `starter.py`.
5. **The manual is pinned to English.** `manual.LANGUAGE` is `"en"`, both
   for the text file and for each video's captions.
6. **`say_count` knows English plurals only.** It takes the *one* form for
   exactly one; French takes it for zero too.

## 3. Scope decisions (agreed with the user)

1. **Spanish, Afrikaans, French and German first.** Decided by the user
   2026-11-18.
2. **The screens follow the computer's language, read at startup.** Where
   Pressless has no translation for it, English. Where the language cannot
   be told, English, with a list to choose from. Decided by the user
   2026-10-08.
3. **Each site has its own language for its published words.** It starts
   as the screens' language when the site is made, and the writer can
   change it in Settings. Decided by the user 2026-11-18.
4. **The sample pages are translated.** Decided by the user 2026-10-08.
5. **Translations are checked with Chrome and Gemini** for the right
   wording. The user, 2026-10-08.
6. **The top bar's More menu also offers the language, as it offers the
   theme**, with "Follow the computer" first. *(decided here)* Decision 2
   gives someone on an English computer who reads Afrikaans no way in.
7. **A site with no language recorded builds in English.** *(decided
   here)* Every site made before this item is one, and must build as
   today.
8. **A translation that is missing, or was made from English that has
   since changed, shows the English.** *(decided here)* Out-of-date words
   can say the wrong thing; English never does. The gate does not fail on
   it: a report lists what needs translating, and the release checklist
   runs it.
9. **Show details, the log, exception messages, commit messages, the
   self-check line and the command-line tools stay English** — PRESS-0242
   decision 4, unchanged.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 A language file

One JSON file per language in `src/pressless/language_files/`, named by
its code: `es.json`, `af.json`, `fr.json`, `de.json`. English has none; it
is `words.ENGLISH`, with `one` `[1]` and `,` for thousands.

```json
{
  "name": "Español",
  "one": [1],
  "thousands": ".",
  "words": {
    "<key>": ["<made-from>", "<words>"]
  }
}
```

- `name` — the language in its own words, for the pickers.
- `one` — the numbers that take a key's *one* form (`[0, 1]` for French).
- `thousands` — what separates thousands in a written number.
- `made-from` — the first eight hexadecimal characters of the SHA-256 of
  the UTF-8 English the entry was translated from.

The folder is named as `manual_files` is (PRESS-0219 § 4.1), and bundled
beside it (`scripts/freeze_flags.py`).

### 4.2 The words module

```python
# src/pressless/words.py — additions
LANGUAGES: tuple[str, ...]        # "en", then each code § 4.6 adds; the order shown

def table(code: str) -> dict[str, str]: ...
    # The language's entries whose made-from matches today's English.
    # "en", or a code with no file, gives {}.

def name(code: str) -> str: ...   # the file's "name"; "English" for "en"

def choose(code: str) -> None: ...
    # Puts table(code) in front of ENGLISH from now on, every thread
    # included, and makes `code` the language in use.

def in_use() -> str: ...          # the code chosen, "en" before any

def say_in(code: str, key: str, **slots: str) -> str: ...
    # `say` with `code`'s table in front of ENGLISH, whatever is in use.

def number(value: int, code: str | None = None) -> str: ...
    # `value` with the thousands marked as `code` (default: in use) marks them.
```

- **`say_count` takes `code` as `number` does**, and that language's
  `one`. Its `count` gap is `number(...)` in that language unless the
  caller passes its own. Every `:,` thousands format under `src/pressless` becomes
  `number(...)`. A one form writes `{count}`, never "1", because French's
  one covers 0.
- **The Builder's counts keep today's unmarked digits** in every language,
  passing their own `count`.
- **`words.use` stays the tests' seam.** `choose` is what startup and the
  picker call.
- **Months and days are entries**: `date.month.1` … `date.month.12`,
  `date.mon.1` … `date.mon.12`, `date.day.0` … `date.day.6` (Monday is 0),
  and the formats `date.long` (`{day} {month} {year}`), `date.medium`
  (`{day} {mon} {year}`), `date.short` (`{day} {mon}`), `date.month_year`
  (`{month} {year}`), `date.mon_year` (`{mon} {year}`) and `date.weekday`
  (`{weekday} {day} {mon}`). One function each in `words` fills them; no
  module calls `strftime` for a name.

### 4.3 The screens' language

```python
# src/pressless/languages.py — new
FILE_NAME = "language.json"   # in Pressless's own folder; one of sites.MACHINE_NAMES
FOLLOW = "follow"

def computer() -> str | None: ...
    # The computer's language as a two- or three-letter code, or None
    # where it cannot be told. Linux: the first set of LANGUAGE, LC_ALL,
    # LC_MESSAGES, LANG; from LANGUAGE's list, the first language
    # Pressless has, else the first told. "C" and "POSIX", with or
    # without an encoding, cannot be told. Windows: kernel32's GetUserDefaultUILanguage,
    # through locale.windows_locale.

def read_choice(folder: Path) -> str: ...    # a code, or FOLLOW
def write_choice(folder: Path, code: str) -> None: ...

def for_screens(folder: Path) -> tuple[str, bool]: ...
    # The code the screens use, and whether to offer the list:
    # a chosen language wins; then the computer's, where it is in
    # words.LANGUAGES; then "en". The list is offered only where nothing
    # is chosen and computer() is None.
```

- **At startup** `__main__` calls `words.choose(for_screens(...)[0])`
  once its own folder is known, before the Face, the tray or the first
  translated console line.
- **The top bar's More menu** carries a language picker beside the theme
  (`themes.picker`), each language named in its own words. A choice is
  written, `words.choose` is called, and the page reloads in it.
- **Where the list is offered**, every screen shows it at the top of
  `<main>` until one is chosen.
- **`face._page` writes `lang="<words.in_use()>"`**, and the page scripts'
  words come from `words.for_scripts()` as today.
- **The manual** reads `<in use>.txt` and each video's
  `<stem>.<in use>.vtt`, and the English file where that language's is
  missing.

### 4.4 A site's language

`store.Identity` gains `language: str = ""`. `""` means English, and is
left out of the file as an unchosen picture is, so an identity written
without one keeps today's bytes. A non-empty value is two or three
lowercase letters; anything else is refused as a malformed identity is
today.

- **A new site** — the wizard's *site* step — records `words.in_use()`
  where the identity holds no language yet. Take-in keeps the language the
  identity it takes in carries. A bring-in writes the identity it reads
  from the site's front page (`pressless_import._folder._write_all`) with
  no language, so decision 7 applies until one is chosen.
  `carry_name_across` records nothing.
- **The Settings page** shows a *Site language* row in the identity
  section, offering `words.LANGUAGES` by name, and saves the row's choice.
- **The Builder** writes every word of its own with `words.say_in(site
  language, …)`, its dates through § 4.2's date functions, and
  `lang="<site language or en>"` on the pages it makes. A code with no
  table gives English.
- **The sample pages and templates** are written with the site's
  language, `lang` included.

### 4.5 Making a translation

A helper translates `ENGLISH` into one language, keeping each key, each
`{slot}` and each tag. The user's instruction (decision 5) is the second
opinion on wording. `scripts/translations.py stamp` writes made-from for
each entry that comes back as plain words, and leaves an entry that has one,
so English reworded since still reads as out of date. With `--report` it
lists, per language, each key missing or made from older English. The
manual and its captions are translated the same way.

### 4.6 Building it

The machinery first, with no language file: every page reads as today.
Then one commit per language: its code in `LANGUAGES`, its table, manual
and captions together.
The gate is green after every commit.

## 5. Invariants

- **INV-1** — A site with no language recorded builds byte for byte as
  before this item, whatever language the screens use.
  *Test:* `tests/test_builder_archive.py::test_the_first_publish_moves_no_page`
  (archive), and `tests/test_languages.py::test_a_site_without_a_language_builds_as_before`
  — build a fixture site with the screens in a test language whose table
  marks every entry, and compare with the build under English.
  *Breaks when:* the Builder takes the screens' language, or writes
  `lang` from it.

- **INV-2** — A site's published words follow the site's language, not
  the screens'.
  *Test:* `tests/test_languages.py::test_published_words_follow_the_site`
  — screens in English, site in a test language whose table marks every
  entry: the archive, listing, entry date and forward pages carry no
  English word the Builder wrote, and `lang` is the site's.
  *Breaks when:* a Builder word uses `say` rather than `say_in`, or a date
  takes `builder._MONTHS`.

- **INV-3** — A translated entry keeps its English's gaps and tags.
  *Test:* `tests/test_languages.py::test_translations_keep_gaps_and_tags`
  — for every entry of every file, the set of `{slot}` names and the
  sequence of tag names equal its English entry's.
  *Breaks when:* a translation drops `{count}`, or turns `<b>` into
  `<strong>`.

- **INV-4** — An entry missing, or made from other English, shows the
  English.
  *Test:* `tests/test_languages.py::test_stale_or_missing_shows_english`
  — a file whose entry has a wrong made-from, and one lacking a key.
  *Breaks when:* `table` ignores made-from.

- **INV-5** — `computer()` reads the language as § 4.3 says.
  *Test:* `tests/test_languages.py::test_the_computers_language_is_read`
  — a table of environments (`LANG=es_MX.UTF-8` → `es`, `LANGUAGE=af:en`
  → `af`, `LANGUAGE=pt_BR:fr` → `fr`, `LANG=C.UTF-8` → None, all unset → None) and of Windows
  language ids (`0x0436` → `af`, an id `locale.windows_locale` lacks →
  None), the Windows call replaced.
  *Breaks when:* `LC_ALL` loses to `LANG`, `C.UTF-8` reads as a
  language, or `LANGUAGE`'s later entries are ignored.

- **INV-6** — Where the language cannot be told and none is chosen,
  every screen offers the list; once one is chosen, the screens use it and
  the list is gone.
  *Test:* `tests/test_languages.py::test_the_list_is_offered_until_one_is_chosen`
  — a Face driven as `tests/test_face.py`'s `_Client` drives one.
  *Breaks when:* the list shows on only the first screen, or after a
  choice.

- **INV-7** — No module names a month or a day through the C library or
  a list of its own.
  *Test:* `tests/test_words.py::test_no_screen_writes_english`, widened to
  refuse `%a`, `%A`, `%b` and `%B` in a format passed to `strftime` or
  after a date's `:` in an f-string, anywhere under `src/pressless`; and
  `builder._MONTHS` removed. `%APPDATA%` in a comment is not a format.
  *Breaks when:* someone writes `strftime("%b")`.

- **INV-8** — A number and a count on a screen read as the language
  writes them.
  *Test:* `tests/test_words.py::test_say_count_follows_the_language` —
  French takes *one* for 0 and 1, English for 1 only; `number(1234,
  "de")` is `1.234`; and
  `tests/test_words.py::test_every_counted_one_form_carries_its_count` —
  every one form the source counts with holds `{count}`.
  *Breaks when:* `say_count` keeps `number == 1`, or a one form writes "1".

- **INV-9** — Every language in `words.LANGUAGES` but English has a file
  that loads, with a name.
  *Test:* `tests/test_languages.py::test_every_language_loads` — and
  `pyinstaller_args` carries the folder, as `tests/test_manual.py` checks
  `manual_files`.
  *Breaks when:* the folder is left out of `freeze_flags.DATA`, or a file
  is not JSON.

## 6. Failure modes

- **A language file that will not load** in a built app gives English and
  a log line. INV-9 stops this reaching a release from source.
- **An unknown language code in an identity** (from a newer Pressless)
  builds in English and is kept as written.
- **An older Pressless saving the identity** drops `language`, so the
  site builds in English until it is chosen again.
- **A longer translation** wraps where English fitted. Nothing checks
  this; § 4.6's by-hand look at each language does.
- **The tray menu** takes the language at startup; a choice in the
  picker reaches it at the next start.

## 7. Tests

`tests/test_languages.py` is new and holds INV-1's second half, INV-2 to
INV-6 and INV-9. `tests/test_words.py` gains INV-7's widening and INV-8.
Each is seen failing against the code before this item.

## 8. Alternatives considered (and rejected)

- **`gettext` and `.po` files.** Rejected by PRESS-0242 § 8; a key here is
  not the English.
- **The browser's language rather than the computer's.** The user chose
  the computer's (decision 2).
- **The published words in the screens' language.** An English site made
  on a Spanish computer would show Spanish month names (decision 3).
- **The language in `Settings`.** Settings holds machine facts; the
  language is the site's, and must travel with it, as the name does.
- **Failing the gate on an out-of-date translation.** Every English
  rewording would then need four translations before it could land.
- **Python modules rather than JSON** for a language. A translation is
  data, and JSON is what a translation tool reads.

## 9. Out of scope

- Languages beyond the four, and plural rules with more than two forms —
  deferred; not yet queued.
- The manual's pictures and videos taken in each language — deferred; not
  yet queued.
- The AI assistant's replies, and the usage reports — deferred; not yet
  queued. A usage change owes the privacy policy text.
- What stays English (decision 9).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_languages.py::test_a_site_without_a_language_builds_as_before`; the archive test adds the writer's real site, **skipped in CI** |
| INV-2 | Partial: `tests/test_languages.py::test_published_words_follow_the_site`, over the pages it builds |
| INV-3 | `tests/test_languages.py::test_translations_keep_gaps_and_tags` |
| INV-4 | `tests/test_languages.py::test_stale_or_missing_shows_english` |
| INV-5 | Partial: `tests/test_languages.py::test_the_computers_language_is_read`; the real Windows call is checked on the box by hand |
| INV-6 | `tests/test_languages.py::test_the_list_is_offered_until_one_is_chosen` |
| INV-7 | Partial: `tests/test_words.py::test_no_screen_writes_english`; a name built another way passes it |
| INV-8 | `tests/test_words.py::test_say_count_follows_the_language` |
| INV-9 | `tests/test_languages.py::test_every_language_loads` |
| That a translation says the right thing | **nothing** — Gemini's second opinion and the user's look (decision 5) |
| That a translation fits its screen | **nothing** — by hand in the browser, per language |

## 11. Cross-doc impact

- `docs/specs/PRESS-0242-screen-words.md` § 4.1 — `choose`, `say_in`,
  `number`, the date functions, and `say_count`'s language rule; decision
  3's Builder words are now this item's.
- `docs/specs/PRESS-0213-site-identity.md` § 4.1 — `Identity.language`;
  § 4.6 — the Settings row.
- `docs/specs/PRESS-0008-builder.md` INV-12 — a date reads the same on
  every system *for a site's language*; `builder._MONTHS` goes.
- `docs/specs/PRESS-0219-in-app-manual.md` § 4.1 — the language in use
  picks the file and the captions.
- `docs/specs/PRESS-0223-several-sites.md` § 4.2 — `language.json` is a
  machine name.
- `docs/working-here.md` *Releasing* — run `scripts/translations.py
  --report` and bring each language up to date.
- `README.md`, `CHANGELOG.md` — the languages.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0241-more-languages-loop-log.md`.
