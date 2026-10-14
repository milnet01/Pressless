<!-- ants-spec-format: 1 -->
# PRESS-0260 — The visual editor: typing on the page as it will look

**Status:** accepted (2026-10-13). Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0260 (S15; split from PRESS-0215 by the user
2026-10-13; the user's answers 2026-10-13).

**Blocked by:** PRESS-0215, shipped. **Pairs with:** PRESS-0261, the
code box's colours, and PRESS-0216, which brings the header, footer and
menu into this editor later. **Changes:** PRESS-0014's words view and
PRESS-0238, which it retires, and PRESS-0215 INV-7 (§ 11).

Layman: they click a heading or paragraph on their page, shown as it
will look, and type there; a panel beside it adds, moves and removes
sections such as a picture or a button, and the words box is gone.

## 1. Goal

A page opens in a visual view: the Builder's own preview of the page,
in which the user types into text and headings and picks any section to
change it in a side panel. Each save writes the page through
`blocks.write`, keeping every section the user did not change byte for
byte. A page Pressless never marked is taken into sections at its first
save. The words view is retired; the code view stays.

## 2. Problem

1. **The words box shows a page as a list of paragraphs, not as it
   looks.** `page_editor.words` joins the page's text runs with blank
   lines, and a preview beside it is the only picture of the page.
2. **The words box can only change words.** It cannot add a picture, a
   button or columns; PRESS-0238 reaches adding and removing
   paragraphs, through `page_editor._placed`'s guessing about where a
   new paragraph goes.
3. **Blocks exists and nothing edits through it.** PRESS-0215 § 4.9
   leaves adopting a page, and the preview marks an editor needs, to
   this item.
4. **The preview runs no script, and must not start.** It is served
   from the Face's own address with `sandbox="allow-same-origin"` alone
   (`page_editor._page`; PRESS-0169). A page's code section or the
   site-wide script running there would run as the Face.

## 3. Scope decisions (agreed with the user)

1. **Editing happens on the page itself, in the preview frame, with a
   side panel for a picked section's settings.** The user, 2026-10-13.
2. **It replaces the words view of PRESS-0014 and PRESS-0238.** The
   user, 2026-10-13.
3. **Add, move and remove sit in the side panel, not on the page.** The
   user, 2026-10-13: nothing on the page shifts.
4. **Enter splits a paragraph at the caret; Shift+Enter is a line
   break.** The user, 2026-10-13.
5. **A code section is editable in the side panel**, as its HTML in a
   box. The user, 2026-10-13.
6. **Video, music and download take a typed address.** Uploading those
   files is later work. The user, 2026-10-13.
7. **Moving a section between columns, or out of them, is later work.**
   The user, 2026-10-13.
8. **The older specs are brought into line with the code that retires
   them**, not gated separately. The user, 2026-10-13 (§ 11).
9. **(decided here) The frame runs no script.** The Face page's own
   script reaches into the frame, which `allow-same-origin` permits.
   Measured 2026-10-13 in Chrome through Playwright: with the sandbox
   unchanged, a script in the framed page did not run, the parent read
   the frame's comment nodes, a `contenteditable` paragraph took typing,
   and the parent's `click`, `keydown` and `input` listeners on the
   frame's nodes fired.
10. **(decided here) The marks reach the visual view's preview, and no
    other.** The Face finds sections by their mark comments; nothing is
    added to the page's elements.
11. **(decided here) A picture is a photograph Pressless holds, or a
    typed address.** One Pressless holds is published with the page.
12. **(decided here) The header, footer and menu stay in the code
    view** until PRESS-0216.
13. **(decided here) The preview keeps the Face's content policy**, so
    a video or picture from elsewhere is not shown there (§ 4.2).

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The views

`page_editor.WORDS` becomes `page_editor.VISUAL = "visual"`.
`page_editor._view` gives `CODE` for the furniture, and for a page
`CODE` where `view=code` was asked, else `VISUAL`; an old `view=words`
address opens the visual view. *Amended by PRESS-0216:* the furniture
takes the same rule as a page.

**Opening a page in the visual view** (`page_editor._open`):

1. Read the file as today (`_read`).
2. Where `blocks.read(name, text)` finds no area, take
   `blocks.adopt(text, builder.furniture_spans(name, text))` **in
   memory**. Nothing is written at opening.
3. Where `adopt` returns `None`, or `furniture_spans` raises
   `BuildStopped`, the page opens in the code view, and a notice says
   why (`notice.page_editor.code_only`).
4. Build the preview from the text of step 1 or step 2, with marks
   (§ 4.2).

The switch link offers *Show me the code* in the visual view and
*Back to the page* (`page_editor.show_visual`) in the code view.

### 4.2 The frame

`builder.preview_html` gains a keyword `marks: bool = False`. Where it
is true, `_Build.fixed_page` writes the shown page without calling
`blocks.unmarked`. Only the visual view passes it. *Amended by
PRESS-0216:* for a furniture file the shown page loses its marks and
that file keeps its own (PRESS-0216 § 4.3).

The frame keeps `sandbox="allow-same-origin"` and gains nothing.
The editor page carries the outline `blocks.read` gives: every
section's path (§ 4.5) and kind, in order, each marked or not. An
unmarked code run (PRESS-0215 § 4.3 step 3) has no marks, so it shows
in the frame but cannot be picked; the code view changes it.

The Face page's script, `page_editor._VISUAL_SCRIPT`, waits for the
frame's `load`, then walks its `contentDocument` for comment nodes,
pairing each marked section with the outline's next marked entry.
Between an opening mark and its closing mark lie the section's nodes.
The script keeps a model of the page: per section its kind, its fields
as shown, its path, and whether the user changed it.

**The preview loads nothing from elsewhere, and this item keeps it
so.** `face.FILES_POLICY` blocks a YouTube frame, and a picture, video
or music at a typed `http:` or `https:` address. There the frame shows
the browser's empty or broken box, and the side panel shows the
address.

It adds one `style` element to the frame's `head`: an outline round
the picked section, a placeholder for an empty text or heading, and
nothing that moves the page's layout.

### 4.3 Picking, and the side panel

A click on a section's nodes picks it. The side panel sits beside the
frame, at a fixed place and size. It shows:

- **The picked section's settings**, by kind:

| Kind | In the panel |
|---|---|
| text | Bold, Italic, Link |
| heading | Bold, Italic, Link; its level, 1 to 6 |
| picture | Choose a photograph, or type an address; the words that describe it (`alt`); an optional caption |
| pictures | its pictures, each picked and changed as a picture |
| button, download | the address; the words on it |
| video | the address: a YouTube address is kept as its id, any other as `src` |
| music | the address |
| columns | how many, 2 to 4 |
| code | its HTML, in a box |

- **Add below**, a list of the kinds the picked section's list may
  hold: the nine at the top of the page, no columns and no row of
  pictures in a column, a picture alone in a row (PRESS-0215 § 4.3).
  With nothing picked, **Add at the end**. A text or heading is added empty, with the caret in it.
  A kind needing an address is added once one is given.
- **Move up, Move down, Remove.** A section moves within the list it
  sits in: the page's, a column's, or a row of pictures'. At an end of
  its list, the button it cannot use is shown disabled, never hidden.

*Amended by PRESS-0217:* the Add list and this table gain its six kinds
(PRESS-0217 § 4.1, § 4.2).

A picked columns section's panel also offers **Add to column N** for
each column, and a picked row of pictures **Add a picture**. A row of
pictures is added with its first picture, since Blocks refuses an
empty row. Fewer columns is refused while a column to go still holds a
section.

### 4.4 Typing

A picked text or heading section's element is made
`contenteditable` in the frame.

- **Enter** splits it at the caret: the words before it stay, and the
  words after it become a new text section below, the caret at its
  start. **Shift+Enter**
  writes a `br`.
- **Backspace at the very start** of a text section joins it to the
  text section above, where there is one; elsewhere it does nothing.
- **Ctrl+B, Ctrl+I and Ctrl+K** are Bold, Italic and Link.
- **Pasting** inserts the clipboard's plain text.

**The words are read from the element's nodes, never from
`innerHTML`.** Text is written escaping `&`, `<` and `>`, a no-break
space as a space; `b` is written `strong`, `i` is written `em`; an `a`
keeps its `href` alone; `br` stays; any other element is replaced by
its content. The result is `<inline>` as `blocks` § 4.4 defines it.

### 4.5 Saving

**The save keeps PRESS-0014's route and timing**: `/page/save` about a
second after the last change, and the press route's save first
(`page_editor._pressed`). The posted form names `view=visual` and
carries `sections`, the whole page as JSON:

```
sections := [item, ...]
item     := {"keep": path}                       a section of the file at `base`, unchanged
          | {"kind": k, "fields": {...},
             "parts": [[item, ...], ...]}         a section built anew
          | {"code": "<html>"}                    a code section: the HTML between its marks
removed  := [path, ...]                          sections of the file at `base` the user removed
path     := [i] | [i, c, j]                      top-level section i; or section j of part c of section i
```

The form carries `removed` beside `sections`. The panel shows a code
section's HTML without its two marks, and posts it so.

`page_editor._write`, for the visual view, under `editor.LOCK`:

1. Check the file against `base`, as today.
2. Where it has no area, `blocks.adopt` it (§ 4.1 step 2).
3. `blocks.read` it, and resolve each `keep` to the `Section` read at
   that path. Every path of the file must be kept or removed exactly
   once, or `SectionsUnreadable` is raised.
4. Build the page: `before` and `after` as read; each kept top-level
   section keeps the gap before it, and every other one has `"\n"`;
   the last gap as read. A section built anew is a `blocks.Section`
   with no `source`; its `html` and `caption` are first rewritten by
   `blocks.inline`, new beside `blocks.read`, which returns markup as
   `section_html` writes `<inline>`, or `None`, which raises
   `SectionRefused`. A `code` item is a `CODE` section whose `source`
   is its HTML inside `<!-- pressless:code -->` and
   `<!-- /pressless:code -->`.
5. Write `blocks.write(page)` to the waiting copy, but only where
   `blocks.read` of it gives back the posted list: the same kinds at
   the same paths, each kept section's bytes unchanged. Otherwise raise
   `page_editor.SectionsUnreadable` and write nothing.

`blocks.SectionRefused` from step 4 writes nothing either. `_save` and
`_pressed` catch both beside the failures they catch today, and answer
as for those: not saved, and not published. `SectionsUnreadable` gets its `face.SENTENCES` entry and
`words.py` keys, as every failure type does; every new word on the
screen is a `words.py` key.

**After a save, the posted list is the file's**: each section's path
is its place in that list, which step 5 makes true, and the reply's
`base` is the next save's.

**After a save the frame is rebuilt** from the reply's preview, with
the same section picked by path — **except while the caret is in a
section.** The rebuild then waits until the caret leaves it.

### 4.6 Pictures Pressless holds

The panel lists `store.list_photographs` and offers the entry editor's
*Add a photograph*, which posts to `/photograph` as the entry editor
does. A chosen photograph's `src` is `builder.web_photograph(name)`,
with `../` before it on a page in `pages/`.

- **The Builder publishes it.** `_Build.fixed_page`, building the site
  folder, calls `web_copy` for each picture section of the page whose
  `src`, read from the page's place and percent-decoded, is
  `photographs/<name>` for a photograph the Store holds.
- **The preview shows it.** `editor.register` adds
  `face.add_files(PREVIEW_ADDRESS + "photographs/", ...)` serving the
  Store's originals, so the preview copies nothing.

### 4.7 What this item retires

From `page_editor`: `WORDS`, `Piece`, `_Block`, `_Runs`, `pieces`,
`_parse`, `words`, `put_words`, `_edit`, `_placed`, `_new_blocks`,
`_BLOCKS`, `PiecesChanged` with its `SENTENCES` entry, `_hint`, and the
`hint` branches in `_save` and `_pressed`. From `words.py`, the keys
only they used: `page_editor.show_words`, `script.press.paragraphs`,
`failure.page_editor.PiecesChanged.what` and `.next`. Their tests in
`tests/test_page_editor.py` go with them.

### 4.8 What this item never does

- It runs no script in the frame (§ 3 decision 9).
- It writes a page only at a save, never at opening.
- It re-spells no section the user did not change.
- It adds no dependency, and the preview loads nothing from elsewhere
  (§ 4.2).

## 5. Invariants

- **INV-1** — A save that keeps every section in its place writes the
  file the save read, byte for byte; for a page with no area, the file
  `adopt` makes.
  *Test:* `tests/test_page_editor.py::test_a_save_of_nothing_changed_keeps_every_byte`,
  over the starter pages, a page with code sections and odd gaps, and
  an unmarked page.
  *Breaks when:* step 4 of § 4.5 gives a kept section a new gap, or
  writes it through `section_html`.

- **INV-2** — A section the save does not change keeps its bytes when
  others are changed, added, moved or removed, a code section included.
  *Test:* `tests/test_page_editor.py::test_unchanged_sections_keep_their_bytes`:
  a page holding a hand-spelled code section, an unmarked code run and
  a text section; one save changes the text, adds a button and moves
  the code section up.
  *Breaks when:* a kept section is rebuilt from its fields.

- **INV-3** — A save writes nothing unless the file it would write
  reads back as the posted sections.
  *Test:* `tests/test_page_editor.py::test_a_save_that_would_not_read_back_writes_nothing`:
  a code item holding `<!-- /pressless:page -->`, a text item whose
  `html` holds a `span`, and a list leaving out a section it does not
  name as removed; each leaves the waiting copy as it was and answers
  409.
  *Breaks when:* step 5's read-back is skipped, so the first item ends
  the area early.

- **INV-4** — Opening a page writes nothing; a page with no area is
  adopted at its first save.
  *Test:* `tests/test_page_editor.py::test_a_page_is_adopted_at_its_first_save`:
  the file's digest is unchanged after `GET /page`, and after one save
  the waiting copy has an area and the live file is unchanged.
  *Breaks when:* `_open` writes the adopted text.

- **INV-5** — The visual view's frame carries `sandbox` with
  `allow-same-origin` alone.
  *Test:* `tests/test_page_editor.py::test_the_frame_runs_no_script`
  reads the opened page's `iframe`; `scripts/by-hand-browser-checks.py`
  opens a page whose code section sets the document title, and finds it
  unset.
  *Breaks when:* `allow-scripts` is added to make the frame's own
  script work.

- **INV-6** — Marks reach the visual view's preview and nothing else.
  *Test:* `tests/test_builder.py::test_only_the_visual_preview_keeps_marks`:
  `preview_html(..., marks=True)` keeps every mark; the same call
  without it, and a site build, keep none.
  *Breaks when:* `marks=True` reaches `fixed_page` on a site build.

- **INV-7** — A photograph Pressless holds, named by a page's picture
  section, is in the site folder and in the preview.
  *Test:* `tests/test_builder.py::test_a_page_picture_is_published`
  builds a page naming one held photograph and one typed address, and
  finds `photographs/<name>` and nothing for the address;
  `tests/test_page_editor.py::test_the_preview_serves_held_photographs`
  fetches it under the preview's address.
  *Breaks when:* only entries' photographs are copied, as today.

- **INV-8** — A save over a file this window did not see writes
  nothing, in the visual view as in the code view.
  *Test:* `tests/test_page_editor.py::test_a_visual_save_over_a_changed_file_writes_nothing`.
  *Breaks when:* the visual branch of `_write` skips the `base` check.

- **INV-9** — The words a user types are saved as `<inline>`.
  *Test:* `scripts/by-hand-browser-checks.py`: typing with Ctrl+B,
  Ctrl+I and a link, and pasting styled text, saves a text section that
  reads back as text, not code.
  *Breaks when:* the script reads `innerHTML`, so a browser's `b` or
  `&nbsp;` reaches the save and step 5 refuses it.

- **INV-10** — The words view is gone: no route, word or name of § 4.7
  remains.
  *Test:* `tests/test_page_editor.py::test_the_words_view_is_retired`
  checks `page_editor` has none of § 4.7's names and `words.py` none of
  its keys.
  *Breaks when:* a name is left behind.

## 6. Failure modes

| What happens | What the user sees |
|---|---|
| `adopt` finds no usable `main`, or the markers do not pair | The page opens in the code view, with a notice saying so (§ 4.1) |
| A save would not read back (INV-3) or Blocks refuses a section | Not saved; the reason in the failure box; the waiting copy as it was |
| The file changed elsewhere | Not saved, as today (`editor.ChangedElsewhere`) |
| A hand-edited section in the code view | It shows as a code section next time (PRESS-0215 § 4.3) |
| A browser where the frame cannot be edited | Not seen in Chrome; Edge and Firefox are by-hand rows (§ 7) |
| A YouTube video, or media at a typed address | An empty or broken box in the preview; the address in the side panel (§ 4.2) |
| The preview fails to build | The failure shows where the frame was, as today; the save stands |

## 7. Tests

| Test | Locks |
|---|---|
| `tests/test_page_editor.py` | INV-1, INV-2, INV-3, INV-4, INV-5's first half, INV-7's second half, INV-8, INV-10 |
| `tests/test_builder.py` | INV-6, INV-7's first half |
| `scripts/by-hand-browser-checks.py` | INV-5's second half, INV-9, and § 4.3 and § 4.4's keys and buttons, in Chrome |
| By hand | Firefox on this machine, Edge on the Windows box: open a page, type, Enter, add a picture, publish |

Each test is seen failing before the code it locks exists.

## 8. Alternatives considered (and rejected)

- **Section cards in a list.** The user chose editing on the page
  (§ 3 decision 1).
- **`allow-scripts` and an editing script inside the frame.** With
  `allow-same-origin` it lets a page's code section, or the site-wide
  script, act as the Face.
- **`data-` attributes in the preview instead of marks.** They change
  the page's elements, so the preview is no longer the published page.
- **Posting the edited HTML and parsing it back.** It re-spells
  whatever the browser rewrote, which is the fight the round-trip rule
  rules out; keeping sections by path keeps their bytes.
- **Rebuilding the frame on every save.** It moves the caret mid-word.

## 9. Out of scope

- The header, footer and menu in this editor — PRESS-0216.
- Interactive sections — PRESS-0217.
- Colours in the code box — PRESS-0261.
- Moving a section between columns, or out of them — PRESS-0264.
- Uploading video, music and download files — PRESS-0197.
- Dragging sections — PRESS-0265.

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | `tests/test_page_editor.py::test_a_save_of_nothing_changed_keeps_every_byte` |
| INV-2 | `tests/test_page_editor.py::test_unchanged_sections_keep_their_bytes` |
| INV-3 | `tests/test_page_editor.py::test_a_save_that_would_not_read_back_writes_nothing` |
| INV-4 | `tests/test_page_editor.py::test_a_page_is_adopted_at_its_first_save` |
| INV-5 | Partial: `tests/test_page_editor.py::test_the_frame_runs_no_script` reads the attribute; that no script runs is `scripts/by-hand-browser-checks.py`, by hand |
| INV-6 | `tests/test_builder.py::test_only_the_visual_preview_keeps_marks` |
| INV-7 | `tests/test_builder.py::test_a_page_picture_is_published`; `tests/test_page_editor.py::test_the_preview_serves_held_photographs` |
| INV-8 | `tests/test_page_editor.py::test_a_visual_save_over_a_changed_file_writes_nothing` |
| INV-9 | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand before a release |
| INV-10 | `tests/test_page_editor.py::test_the_words_view_is_retired` |
| § 4.3, § 4.4 keys and buttons | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |
| § 4.8 "never re-spells" | INV-1 and INV-2 |

## 11. Cross-doc impact

**Landed with the code, as § 3 decision 8 says.** Each records what the
build settles under this spec's reviewed direction.

- `docs/specs/PRESS-0014-fixed-pages.md`: INV-1 to INV-4 and the
  words-view half of § 4.2 marked withdrawn, citing PRESS-0260.
- `docs/specs/PRESS-0238-add-remove-paragraphs.md`: **Superseded by:**
  PRESS-0260, and each invariant marked withdrawn.
- `docs/specs/PRESS-0215-blocks.md`: INV-7 and § 4.7 annotated
  *amended by PRESS-0260*: the visual view's preview keeps the marks
  (§ 4.2); § 4.1 gains `inline` (§ 4.5).

Also:

- `docs/design.md` § The parts: the Face row's "the page editor" reads
  "the page editor, visual and code".
- `CHANGELOG.md`: one line, saying pages are edited on the page itself
  and the words box is gone.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0260-visual-editor-loop-log.md`.

## 13. Resource cost

No new dependency. Each save reads and writes one page and builds one
preview, as today; a held photograph in the preview is served from the
original, not copied.
