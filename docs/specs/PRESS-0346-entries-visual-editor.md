<!-- ants-spec-format: 1 -->
# PRESS-0346 — Entries edited as they look, like pages

**Status:** accepted (2026-11-06). No review: the file format is kept and a save that would not read back writes nothing (`CLAUDE.md` rule 14).
**Kind:** ux.
**Source:** ROADMAP PRESS-0346 (the 2026-11-03 usability study; the
user's decision 2026-11-06).

**Builds on:** PRESS-0260, whose typing it shares, and PRESS-0285, whose
in-place switch it copies. **Changes:** PRESS-0004 § 4.1 and PRESS-0012
§ 4.7 and § 4.8 (§ 11).

Layman: they click a paragraph of their journal entry, shown as it will
look, and type there; a panel beside it adds, moves and removes
paragraphs, photographs and quotations. The marks still work for anyone
who wants them.

## 1. Goal

An entry's body opens in a visual view: the Builder's own preview of the
entry, in which the user types into paragraphs and quotations and picks
any block to change it in a side panel. Each save writes the body as
marks, keeping every block the user did not change byte for byte. The
marks box stays, as the second view.

## 2. Problem

1. **Entries are typed in marks**, beside a cheat sheet and a preview
   (`editor._page`). A general user has a markup to learn before a word
   is bold; pages have not needed one since PRESS-0260.
2. **The entry file format must not change** (user, 2026-11-06). The
   body stays marks (PRESS-0004), so whatever the page shows has to be
   written back as marks.
3. **Marks has no escape character** (PRESS-0004 § 3 decision 3). Words
   typed on the page such as `*really*`, or a line that is `{photo:
   a.jpg}`, would become marks when written back as they are.
4. **Some marks show as something else.** `{years_since: …}` shows as a
   worked-out number and `{rainbow}` as one span per character. Words
   read back from the page lose the mark.

## 3. Scope decisions (agreed with the user)

1. **Entries are edited as they look, like pages, and keep their file
   format.** The user, 2026-11-06.
2. **(decided here) Only the body is typed on the page.** Title,
   categories, tags and address stay the fields above the frame.
3. **(decided here) The marks view stays**, with the cheat sheet, and
   is remembered once chosen. A writer fluent in marks keeps them.
4. **(decided here) Three kinds of block:** paragraph, photograph and
   quotation, which is what `marks.parse` gives (PRESS-0004 § 4.3).
5. **(decided here) Typing behaves as on pages** (PRESS-0260 § 3
   decisions 3 and 4, § 4.4): Enter starts a new paragraph, Shift+Enter
   a new line, and add, move and remove sit in the side panel.
6. **(decided here) The panel's styling is Bold, Italic, Link and
   Colour.** Colour offers the site's accent, its muted colour, or a
   picked colour, the three colour marks.
7. **(decided here) A block holding a mark the page cannot show as
   typed** (`rainbow`, a value mark) **is changed in a marks box in the
   panel**, never typed on, so the mark is not lost.
8. **(decided here) The frame runs no script and the preview gains no
   marks.** The body's blocks are found by position (§ 4.2).

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The views

`GET /edit` opens the visual view, or the marks view where
`view=marks` was asked or `choices` remembers it (`entry_view`, new).
The marks view is today's page: the box and `cheatsheet.panel()`. The
switch link (*Show me the marks*, *View editor*) changes view in place
as PRESS-0285 § 4.4 does for pages, saving first, and remembers the
view through `POST /edit/view`.

### 4.2 Finding the blocks

`marks.to_html` writes one element per block, joined by `\n`: `<p>`,
`<figure>` or `<blockquote>`, and the Builder writes them alone inside
the element whose `class` is `builder.BODY_CLASS`. So the element
children of that element are the body's blocks, in order.

The editor page carries the outline of the body as read: per block its
kind, whether it may be typed on (decision 7), its marks as written
(for the panel's marks box), and for a photograph its name and caption.
The script, `editor._VISUAL_SCRIPT` (new), pairs the frame's body
children with the outline by position. **Where the frame shows the
entry and its blocks do not pair, the entry opens in the marks view**
with a notice saying why. A preview that failed shows its failure, and
the next save rebuilds it.

An empty body shows one empty paragraph with the caret in it. It is not
a change until something is typed.

### 4.3 The panel

Beside the frame, at a fixed place and size (PRESS-0260 § 4.3):

| Kind | In the panel |
|---|---|
| paragraph | Bold, Italic, Link, Colour |
| quotation | Bold, Italic, Link, Colour |
| photograph | Choose a photograph, or *Add a photograph*; its caption |
| a block not typed on | its marks, in a box |

- **Add below**: paragraph, photograph, quotation. With nothing picked,
  **Add at the end**. A paragraph or quotation is added empty with the
  caret in it. A photograph is placed at once and saved once one is
  chosen.
- **Move up, Move down, Remove**, shown disabled, never hidden, where
  they cannot act.

**Link** takes only an address the `link` row's `arg` matches (PRESS-0004
§ 4.2), and the page is given that pattern from `marks.MARKS`, not a
copy. Photographs are `store.list_photographs`, and *Add a photograph*
posts to `/photograph` as today.

### 4.4 Typing

PRESS-0260 § 4.4's keys, paste and reading of the words are shared,
not copied: they move out of `page_editor._VISUAL_SCRIPT` into one
script both editors load, `editor.TYPING_SCRIPT`. For entries the
words read also keep a colour mark's `span`, as `to_html` wrote it. In
a quotation, Enter starts a new paragraph of the same quotation, and
words a browser leaves loose in it are a paragraph of their own.

### 4.5 Saving

The save keeps `/save`, its timing and its fields (PRESS-0012 § 4.8),
and the press and leaving hooks with them (`editor.SAVING_SCRIPT`,
`editor.LEAVING_SCRIPT`). In the visual view the form carries `view=visual`,
`blocks` and `removed` in place of `body`:

```
blocks  := [item, ...]
item    := {"keep": i}                          block i of the body at `base`, unchanged
         | {"paragraph": inline}                a paragraph built anew; <br> ends a line
         | {"quote": [inline, ...]}             a quotation, one inline per paragraph
         | {"photo": name, "caption": text}     a photograph
         | {"marks": text}                      typed in the panel's marks box
removed := [i, ...]                             blocks of the body at `base` removed
inline  := the words as PRESS-0260 § 4.4 reads them, plus § 4.4's colour spans
```

**New in `marks`** (PRESS-0004 § 4.1 gains them):

- `sources(body)`: each block's text as written and the text between
  blocks, which join back to `body` exactly.
- `from_inline(inline) -> Paragraph | None`: the words as marks nodes,
  or `None` for an element, link or colour a mark cannot hold.
  Whitespace at a mark's edges moves outside it, an empty mark is
  dropped, and an empty line is dropped. It recognises a mark by the
  tags that row's renderer writes, so the table stays the only route
  (PRESS-0004 INV-6).
- `write(block) -> str`: the block as marks, escaping with a character
  reference (`&#42;` for `*`, and so on) only where the words would
  otherwise form a mark, begin a quotation, or be read as a character
  reference. Where two marks' asterisks would touch, as in Bold
  around Italic, it puts a word joiner (`&#8288;`) between them, which
  shows as nothing. It raises `marks.Unwritable` unless `parse` of
  what it wrote reads as `block` in normal form.

**Normal form**: in every `Text`, character references read as the
characters they stand for, word joiners removed, neighbouring `Text`s
joined, and empty ones dropped; a mark's argument without the spaces
around it.

`editor.save`, for the visual view, between today's steps 2 and 3:

1. `sources` of the body as read. Every block index is kept or removed
   exactly once, or `editor.BlocksUnreadable` (new) is raised.
2. Build the body: the text before the first block and after the last
   as read; each block's text as written where kept, or `write` of it
   where built; between two blocks the text read between them where
   both are kept and were neighbours in that order, else `"\n\n"`.
3. **Read it back.** `parse` of the new body must equal, in normal
   form, the posted list: a kept block as read, a built block as
   built, a `marks` item as `parse` gives it. Otherwise raise
   `BlocksUnreadable` and write nothing.

Then today's steps 3 to 5 with that body. `from_inline` returning
`None` raises `Unwritable`. `Unwritable` and `BlocksUnreadable` answer
409 and write nothing, each with its `face.SENTENCES` entry and
`words.py` keys; `editor.SAVE_FAILURES` names them for the save route
and the press route alike. The user's words stay in the frame.

A block emptied on the page is posted as removed, and stays on the
page to be typed into.

**Every save reply, and the press's, gains `body` and `outline`**, the
body as written and its outline, so either view can open from the
reply after a switch. After a visual save, block indices are the new outline's, and
the frame is rebuilt from the reply's preview except while the caret is
in a block (PRESS-0260 § 4.5).

### 4.6 What this item never does

- It changes no entry's file format.
- It re-spells no block the user did not change.
- It runs no script in the frame (PRESS-0012 INV-20 holds).
- It adds no dependency.

## 5. Invariants

- **INV-1** — A visual save that keeps every block in its place writes
  the body it read, byte for byte.
  *Test:* `tests/test_editor.py::test_a_visual_save_of_nothing_changed_keeps_every_byte`,
  over bodies with odd gaps, leading and trailing blank lines, and a
  lone `>` line; `tests/test_marks_archive.py::test_every_body_joins_back_from_its_sources`
  over the archive.
  *Breaks when:* step 2 gives kept neighbours `"\n\n"`, or `sources`
  drops the whitespace `parse` strips.

- **INV-2** — A block the save does not change keeps its bytes when
  others are changed, added, moved or removed.
  *Test:* `tests/test_editor.py::test_unchanged_blocks_keep_their_bytes`:
  a body holding a hand-spaced quotation, a photograph line and a
  paragraph with `***x***`; one save changes another paragraph, adds a
  photograph and moves the quotation up.
  *Breaks when:* a kept block is written through `write`.

- **INV-3** — `write` takes every block of the archive, and words that
  look like marks, and each reads back as itself.
  *Test:* `tests/test_marks_archive.py::test_every_block_is_written_back_as_it_reads`
  over every archive block; `tests/test_marks.py::test_typed_words_are_not_read_as_marks`
  writes paragraphs whose words are `*really*`, `{photo: a.jpg}` alone
  on a line, a line starting `>`, `&amp;` and `AT&T`, and finds each
  reads back as those words.
  *Breaks when:* `write` escapes nothing, so `*really*` reads back
  italic.

- **INV-4** — A save writes nothing unless the body reads back as the
  posted blocks.
  *Test:* `tests/test_editor.py::test_a_visual_save_that_would_not_read_back_writes_nothing`:
  with `marks.write` replaced by one that drops a paragraph's `**`, and
  with a list leaving out a block it does not name as removed, each
  answers 409 and leaves the file as it was. The first fixture isolates
  step 3, since the replaced `write` makes no check of its own; the
  second isolates step 1.
  *Breaks when:* step 3 is skipped, so the first fixture saves plain
  words where bold was shown.

- **INV-5** — A visual save over a file this window did not see writes
  nothing.
  *Test:* `tests/test_editor.py::test_a_visual_save_over_a_changed_file_writes_nothing`.
  *Breaks when:* the visual branch skips the `base` check.

- **INV-6** — A block holding a mark the page cannot show as typed is
  never typed on.
  *Test:* `tests/test_editor.py::test_a_value_mark_is_not_typed_on`:
  the outline of a body with `{years_since: 2010-01-01}` and one with
  `{rainbow}x{/}` marks both blocks not typed on.
  *Breaks when:* the outline marks them typed, so a save writes the
  worked-out years as words.

- **INV-7** — Words typed with Bold, Italic, Link and Colour are saved
  as marks, and Enter and Shift+Enter as a new paragraph and a new
  line.
  *Test:* `scripts/by-hand-browser-checks.py`: typing with each, and
  pasting styled text, saves a body holding `**`, `*`, `{link: …}`, a
  colour mark, a blank line and a single line break.
  *Breaks when:* the shared reader drops the colour `span`, so the
  colour is lost on save.

## 6. Failure modes

| What happens | What the user sees |
|---|---|
| The frame's entry does not pair with the outline | The marks view, with a notice saying so (§ 4.2) |
| Words a mark cannot hold, such as a `mailto:` link | Not saved; the reason in the failure box; the words stay in the frame |
| A save would not read back (INV-4) | Not saved; the reason in the failure box; the file as it was |
| The file changed elsewhere | Not saved, as today (`editor.ChangedElsewhere`) |
| The preview fails to build | The failure where the frame was, as today; the save stands |

## 7. Tests

| Test | Locks |
|---|---|
| `tests/test_editor.py` | INV-1, INV-2, INV-4, INV-5, INV-6, § 4.1's remembered view, § 4.2's escaped outline |
| `tests/test_marks.py` | INV-3's typed words |
| `tests/test_marks_archive.py` | INV-1's and INV-3's archive halves |
| `tests/test_page_editor.py` | PRESS-0260's typing, unchanged by the shared script |
| `scripts/by-hand-browser-checks.py` | INV-7, and § 4.3's buttons, in Chrome |
| By hand | Firefox on this machine, Edge on the Windows box: open an entry, type, Enter, add a photograph, press |

Each test is seen failing before the code it locks exists.

## 8. Alternatives considered (and rejected)

- **Storing entries as Blocks, like pages.** The user kept the file
  format (§ 3 decision 1).
- **Marks in the preview to find blocks.** `to_html` already writes one
  element per block, so position is enough, and the preview stays the
  published page.
- **Writing the whole body from the page at each save.** It re-spells
  every block, and loses value and rainbow marks; keeping blocks by
  index keeps their bytes.
- **Escaping every `*` and `{`.** Correct, but the marks view fills
  with character references; escaping only where a mark would form
  keeps the marks readable.
- **The script writing the marks.** The rules then live in JavaScript
  beside the Python ones; `write` keeps them in `marks`, tested over
  the archive.

## 9. Out of scope

- The template editor (`src/pressless/templates.py`) keeps its marks box.
- Typing the title on the page.
- Dragging blocks.

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | `tests/test_editor.py::test_a_visual_save_of_nothing_changed_keeps_every_byte`; `tests/test_marks_archive.py::test_every_body_joins_back_from_its_sources` |
| INV-2 | `tests/test_editor.py::test_unchanged_blocks_keep_their_bytes` |
| INV-3 | `tests/test_marks_archive.py::test_every_block_is_written_back_as_it_reads`; `tests/test_marks.py::test_typed_words_are_not_read_as_marks` |
| INV-4 | `tests/test_editor.py::test_a_visual_save_that_would_not_read_back_writes_nothing` |
| INV-5 | `tests/test_editor.py::test_a_visual_save_over_a_changed_file_writes_nothing` |
| INV-6 | `tests/test_editor.py::test_a_value_mark_is_not_typed_on` |
| INV-7 | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand before a release |
| § 4.3 buttons, § 4.2 fallback | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |
| § 4.6 "never re-spells" | INV-1 and INV-2 |

## 11. Cross-doc impact

Landed with the code, as PRESS-0260 § 3 decision 8 did.

- `docs/specs/PRESS-0004-marks.md` § 4.1: annotated *amended by
  PRESS-0346*: `sources`, `from_inline`, `write`, `normal` and `Unwritable` join
  the public surface; INV-6 reaches `from_inline` and `write`.
- `docs/specs/PRESS-0012-editor.md` § 4.7 and § 4.8: annotated: the
  page opens in the visual view, the box is the marks view, and a save
  takes `blocks` and answers `body` and `outline` (PRESS-0346 § 4.5).
- `CHANGELOG.md`: one line, saying entries are edited on the page
  itself, and the marks stay for those who want them.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0346-entries-visual-editor-loop-log.md`.

## 13. Resource cost

No new dependency. A save reads and writes one entry and builds one
preview, as today; `sources` and the read-back parse the body twice
more.
