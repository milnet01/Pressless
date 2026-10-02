<!-- ants-spec-format: 1 -->
# PRESS-0214 — A site need not have a journal

**Status:** spec draft (2026-10-02).
**Kind:** feature.
**Source:** ROADMAP PRESS-0214 (user decision 2026-10-02, PRESS-0198;
`docs/design.md` § A site need not have a journal).

**Blocker for:** PRESS-0126.
**Amends:** PRESS-0008 (§§ 4.2, 4.7, 4.9), PRESS-0013 (§ 4.3), PRESS-0015 (§ 4.4),
PRESS-0005 (§ 4.1, `move_to_bin`'s folders). § 11 lists each edit.

Layman: a site can switch its journal off, so a business or band site with
no dated posts publishes without a journal page, and switching it back on
brings every entry back.

## 1. Goal

After this ships, the user can turn their site's journal off and on from the
"Your writing" page. Off, the Builder makes no journal pages, a publish is
not refused for having no entries, and publishing an entry is refused with a
sentence saying why. A site that never chose is on, so every existing site
builds exactly as before.

## 2. Problem

1. **Every build makes a journal.** `builder._Build.run` always calls
   `listings` and `archive`, which write `blog/index.html` and
   `blog/archive/index.html` even with no entries, and `sitemap` always lists
   both addresses.
2. **A publish with no entries is refused.** `publishing.publish`'s guard
   raises `NothingToPublish` where `store.list_slugs(folder, draft=False)` is
   empty, unless `emptying`. A site with pages and no entries cannot publish.
3. **Nothing holds the choice.** `docs/design.md` says a site need not have a
   journal and puts site material in the Store and in `content/`, so undo
   brings it back. There is no Store file for it.

## 3. Scope decisions (agreed with the user)

1. **The journal is something a site can have, not something it must.**
   Decided by the user 2026-10-02 (PRESS-0198).
2. **This is built before PRESS-0126.** Decided by the user 2026-10-02: the
   starter site turns the journal off through this switch.
3. **The choice is a Store file, and its absence means on.** *(decided
   here)* Site material belongs in the Store (`docs/design.md` § Where
   everything sits on disk). Absent-means-on leaves every existing Store
   unchanged with nothing to migrate.
4. **The switch sits on the "Your writing" page.** *(decided here)* That page
   lists the entries the switch governs. The Settings page asks GitHub on
   every save, which a switch has no reason to do.
5. **Publishing an entry while the journal is off is refused.** *(decided
   here)* The alternative publishes a file that no page shows, and Publish
   would appear to do nothing.
6. **Off keeps published entries in `content/`.** *(decided here)* Removing
   them would make undo's fetched state hold no entries, and undo would then
   demote every published entry to a draft (PRESS-0015 § 4.4). Their text was
   published already, which `docs/design.md` § Where everything sits on disk
   accepts.
7. **The file is `options/options.json`, a JSON object.** *(decided here)*
   One file for site-wide switches. Its folder is not `site`, which is the
   site folder's name inside Pressless's own folder (`setup.SITE_FOLDER`).

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The Store

```python
# src/pressless/store.py — added
OPTIONS_FOLDER = "options"
OPTIONS_FILE = "options.json"

def options_path_for(folder: Path) -> Path: ...   # folder / OPTIONS_FOLDER / OPTIONS_FILE
def journal_on(folder: Path) -> bool: ...
def write_journal(folder: Path, on: bool) -> Path: ...
```

The file is UTF-8 JSON, an object. `"journal"` is a boolean.

- **`journal_on`** returns True where the file is absent, or holds no
  `"journal"` key. It raises `StoreError` where the file cannot be read, is
  not a JSON object, or holds a `"journal"` that is not a boolean.
- **`write_journal`** reads the object (an absent file is `{}`), sets
  `"journal"`, keeps every other key, and writes the file whole or not at
  all through `_write_atomically`, as `write_forwards` does.
- **`OPTIONS_FOLDER` joins `_BINNABLE`**, because undo bins the version it
  replaces (§ 4.4).

### 4.2 The Builder

`_Build.run` reads `store.journal_on(self.folder)` once. Where it is False:

- the entries are read as none, so no entry page and no forward is written;
- `listings` and `archive` are not called, so nothing is written under
  `blog/`;
- `sitemap` lists no `blog/` address and no entry.

The fixed pages, the furniture, `content()` and the rest of the build are
unchanged. `content()` still copies the published entries, and copies
`options/options.json` where it exists.

`preview` and `preview_html` do not read the switch. An entry's preview
still shows the entry as it would look, and § 4.5 stops the page editor
offering a newest entry to show a change on.

### 4.3 Publishing

```python
# src/pressless/publishing.py — added
class JournalOff(Exception): ...   # an entry was asked to publish with the journal off
```

In `publish`:

1. **Before the move**, where `entry` is not None and
   `store.journal_on(folder)` is False, raise `JournalOff`. Nothing has moved,
   so nothing is put back.
2. **The guard** raises `NothingToPublish` only where `store.journal_on` is
   True — otherwise as today.

`SENTENCES[JournalOff]` says the journal is off, so entries are not on the
site, and that turning it on from "Your writing" lets this entry publish
(`Site.UNCHANGED`). The entry stays saved as the draft it was.

### 4.4 Undo

`undo._read` reads `content/options/options.json` from the fetched state.
`_restore_other_kinds` restores it as it restores `forwards.json`: where it
differs from the Store's or the Store holds none, the Store's goes to the bin
and the fetched one is written, with a reversal recorded. A fetched state
holding none leaves the Store's file untouched, as every other kind is.

### 4.5 The "Your writing" page

`editor._list` shows one line saying whether the journal is on, and one
button that posts to a new `POST /journal`, which `editor.register` adds.

- **`POST /journal`** sets the journal to the opposite of
  `store.journal_on(folder)` through `store.write_journal`, inside
  `editor.LOCK` and `face.capture()`, and returns to the list. A
  `StoreError` is shown through `Face.fail`.
- **While it is off**, the page says entries are not on the site, and that
  turning the journal off took them off at the next publish.
- **Turning it off where an entry is published** shows, beside the button,
  that the published entries leave the site at the next publish and come
  back when the journal is turned on again.

`page_editor`'s "Your newest entry" choice is offered only where
`store.journal_on(folder)` holds as well as where an entry is published.

## 5. Invariants

- **INV-1** — `journal_on` is True for an absent file and for `{}`, False
  for `{"journal": false}`, and raises `StoreError` for `[]`,
  `{"journal": "no"}` and bytes that are not UTF-8. *Test:*
  `tests/test_store.py::test_journal_on_reads_the_options_file`.
  *Breaks when:* an absent file reads as off, or a malformed one reads as on.
- **INV-2** — `write_journal` keeps every other key in the file. *Test:*
  `tests/test_store.py::test_write_journal_keeps_other_options`, with
  `{"other": 1}` present.
  *Breaks when:* the file is written as `{"journal": ...}` alone.
- **INV-3** — With the journal off and a published entry, a build writes
  nothing under `blog/`, and `sitemap.xml` names no `blog/` address. With
  it on, the same Store builds byte-identically to a Store with no options
  file. *Test:*
  `tests/test_builder.py::test_a_site_with_its_journal_off_has_no_blog`.
  *Breaks when:* `listings` or `archive` still runs, or the on case reads the
  file differently from its absence.
- **INV-4** — With the journal off, `content/published/` still holds the
  published entry, and `content/options/options.json` is written. *Test:*
  `tests/test_builder.py::test_off_keeps_entries_in_content`.
  *Breaks when:* entries are dropped from `content/`.
- **INV-5** — With the journal off and no published entry, a publish with
  `entry=None` is not refused. With it on, it raises `NothingToPublish` as
  before. *Test:*
  `tests/test_publishing.py::test_the_guard_runs_only_with_a_journal`.
  *Breaks when:* the guard ignores the switch, or is dropped.
- **INV-6** — With the journal off, publishing an entry raises `JournalOff`,
  leaves the draft where it was, and makes no request. *Test:*
  `tests/test_publishing.py::test_an_entry_will_not_publish_with_the_journal_off`.
  *Breaks when:* the check runs after the move, or not at all.
- **INV-7** — An undo whose fetched state holds `{"journal": true}` over a
  Store holding `{"journal": false}` writes the fetched file and bins the
  Store's. A fetched state with no options file leaves the Store's alone.
  *Test:* `tests/test_undo.py::test_undo_restores_the_journal_switch`.
  *Breaks when:* undo ignores the file, or removes the Store's.
- **INV-8** — `POST /journal` turns an absent file into
  `{"journal": false}` and, posted again, into `{"journal": true}`. *Test:*
  `tests/test_editor.py::test_the_journal_button_switches_it`.
  *Breaks when:* the post sets a fixed value rather than the opposite.
- **INV-9** — The page editor offers "Your newest entry" only while the
  journal is on. *Test:*
  `tests/test_page_editor.py::test_no_newest_entry_choice_with_the_journal_off`.
  *Breaks when:* the choice shows with the journal off.

## 6. Failure modes

- **A malformed options file** stops the build, the publish and the list
  page's switch line with `StoreError`, naming the file. It is never read as
  on or off by guess.
- **Turning off by mistake** takes published entries off the site at the next
  publish. Turning the journal on and publishing brings them back; nothing in
  the Store moves.
- **An entry's draft saved while off** is kept as a draft. The editor still
  saves and previews it.
- **An old address** of an entry stops working while the journal is off, and
  works again when it is on. Search engines see it go and return.

## 7. Tests

`tests/test_store.py` gains INV-1 and INV-2; `tests/test_builder.py` INV-3
and INV-4; `tests/test_publishing.py` INV-5 and INV-6; `tests/test_undo.py`
INV-7; `tests/test_editor.py` INV-8; `tests/test_page_editor.py` INV-9.

Each test is seen failing against the code before this item, then
mutation-probed once the code lands.

## 8. Alternatives considered (and rejected)

- **A Settings field.** Rejected: Settings holds machine facts, and its
  field set is a breaking surface (PRESS-0001 INV-6). Undo would not bring it
  back.
- **The switch on the Settings page.** Rejected (§ 3 decision 4).
- **Publishing an entry while off, unshown.** Rejected (§ 3 decision 5).
- **Dropping entries from `content/` while off.** Rejected (§ 3 decision 6).
- **Off whenever the Store holds no entry.** Rejected: a writer who bins
  their last entry would lose the guard against publishing an emptied site,
  which is what the guard exists for.

## 9. Out of scope

- The menu as a list the Store holds, which drops a journal link by itself —
  PRESS-0195. Until then the menu is the navigation furniture file, edited by
  hand.
- The starter site turning the journal off — PRESS-0126.
- Other site-wide options in `options.json` — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_store.py::test_journal_on_reads_the_options_file` |
| INV-2 | `tests/test_store.py::test_write_journal_keeps_other_options` |
| INV-3 | `tests/test_builder.py::test_a_site_with_its_journal_off_has_no_blog` |
| INV-4 | `tests/test_builder.py::test_off_keeps_entries_in_content` |
| INV-5 | `tests/test_publishing.py::test_the_guard_runs_only_with_a_journal` |
| INV-6 | `tests/test_publishing.py::test_an_entry_will_not_publish_with_the_journal_off` |
| INV-7 | `tests/test_undo.py::test_undo_restores_the_journal_switch` |
| INV-8 | `tests/test_editor.py::test_the_journal_button_switches_it` |
| INV-9 | `tests/test_page_editor.py::test_no_newest_entry_choice_with_the_journal_off` |
| § 4.5 the page's words | **nothing** — read on the page |

## 11. Cross-doc impact

Each edit below is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0008-builder.md` §§ 4.2 and 4.9 — the journal pages and
  their sitemap addresses depend on the switch; § 4.7 — `content/` carries
  the options file.
- `docs/specs/PRESS-0013-publish.md` § 4.3 — the guard depends on the switch,
  and `JournalOff` precedes the move.
- `docs/specs/PRESS-0015-undo.md` § 4.4 — undo restores the options file.
- `docs/specs/PRESS-0005-store.md` § 4.1 — `move_to_bin` takes `options/`.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0214-journal-switch-loop-log.md`.
