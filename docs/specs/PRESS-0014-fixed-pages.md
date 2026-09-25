# PRESS-0014 — Editing a fixed page: the words in a box, the code behind a button

**Status:** accepted (2026-09-25). Gated for two loops, the spec cap; every verified finding fixed, none left in the tail.
**Kind:** implement.
**Source:** ROADMAP PRESS-0014 (`docs/design.md` § What may depend on what,
under *Where the fixed pages live*; discovery S8).

**Blocked by:** PRESS-0006, PRESS-0012, PRESS-0013 — all shipped.
**Pairs with:** PRESS-0015, whose Undo button this page carries.

Layman: he opens his About page from the list, changes its wording in a box,
and sees the real page beside it. A button opens the page's own code for
anything the box cannot do. The header, footer and navigation open the same
way. Nothing reaches his site until he presses Publish on that page.

## 1. Goal

After this ships, the list at `/` also lists his fixed pages and the three
furniture files. Opening one shows a words view or a code view, and the real
page beside it. His changes wait in a copy of their own until he publishes
that page, and a publish of anything else leaves them waiting.

## 2. Problem

1. **Nothing lets him edit a fixed page or the furniture.** The Store holds
   them (PRESS-0006) and no page calls it.
2. **An edit written into the page file would go out with the next publish of
   anything.** The Builder builds every fixed page from the Store, so a
   half-typed footer would publish with an unrelated poem.
3. **A preview builds one entry.** `builder.preview` takes an `Entry`. A fixed
   page, or a page shown with changed furniture, has no preview.
4. **The words and the tags share one file.** `docs/design.md` has the box
   write words back in place, every tag byte-for-byte as it was. Nothing yet
   says what a word is.

## 3. Scope decisions (agreed with the user)

1. **Changes wait in a copy until he publishes that page.** Decided by the
   user 2026-09-25. The live file is unchanged until then, as PRESS-0012
   decision 2 has it for an entry.
2. **The words view is one box, one paragraph per piece of text.** Decided by
   the user 2026-09-25. Adding or removing a paragraph is refused, and the
   refusal points him to the code view.
3. **Furniture previews on the home page, with a picker.** Decided by the user
   2026-09-25. The picker offers every fixed page and his newest entry.
4. **Text typed between a page's header or footer markers is warned about when
   it is saved.** Decided by the user 2026-09-25. The words view never shows
   that text.
5. **(decided here) The furniture has the code view only.** It carries the
   Builder's placeholders, `{{NAVIGATION}}` and `{{YEAR}}` among them, as
   text. A words view would show them as words, and a changed one would break
   every page.
6. **(decided here) The code view keeps each untouched line's own line
   ending.** A browser hands a form's text back with `\n` alone, and PRESS-0006
   § 4.2 forbids translating his line endings. Import leaves some pages with
   mixed endings.
7. **(decided here) The editor for these lives in the Face, as
   `src/pressless/page_editor.py`.** `editor.py` already carries the entry
   editor, and only the Face knows what order things happen in (design
   rule 1).
8. **(decided here) The Builder exports how it finds the marker blocks.**
   The Builder fills each block and this item reads around them, so both use
   one function.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/store.py — added

WAITING_FOLDERS = {PAGES_FOLDER: "pages-waiting",
                   FURNITURE_FOLDER: "furniture-waiting"}

def html_path_for(folder: Path, kind: str, name: str, *,
                  waiting: bool = False) -> Path: ...        # widened
def write_html(folder: Path, kind: str, name: str, html: str, *,
               waiting: bool = False) -> Path: ...           # widened
```

With `waiting=True` the file sits in `WAITING_FOLDERS[kind]` under the same
name, checked by the same rules. Both waiting folders join the folders
`move_to_bin` accepts. `list_html` is unchanged: it lists the live folders
only.

```python
# src/pressless/builder.py — added

def furniture_spans(name: str, html: str) -> tuple[tuple[int, int], ...]: ...
def preview_html(folder: Path, settings: Settings, into: Path, change: Html, *,
                 show: str | None, photo_src: PhotoSrc) -> str: ...
```

`furniture_spans` returns the offsets of the text inside each marker block:
from the end of a `HEADER:START` or `FOOTER:START` marker to the start of the
next END marker **of the same kind**. It raises `BuildStopped` naming `name`
where an END has no START before it, or a START has no END after it.
`_fill_fixed_page` fills the spans it returns.

`preview_html` writes the one page `build(folder, settings, into,
photo_src=photo_src, change=change)` would write for `show`, and returns its
path relative to `into` as `preview` does. `show` names a fixed page; `None`
names his newest published entry the Daily Prompt filter keeps, by date then
address, since `build` writes no page for one it filters out. It keeps
PRESS-0012 § 4.2's other rules: no web copy of a photograph, PRESS-0008
§ 4.8's order, and each preview replacing the last. `None` with no such entry,
or a `show` the Store does not hold, raises `BuildStopped`.

```python
# src/pressless/page_editor.py

WORDS = "words"
CODE = "code"
HOME = "index"                      # the fixed page furniture previews first

class PiecesChanged(Exception): ... # the box holds a different number of paragraphs

def pieces(name: str, html: str) -> tuple[Piece, ...]: ...
def words(name: str, html: str) -> str: ...
def put_words(name: str, html: str, box: str) -> str: ...
def put_code(html: str, text: str) -> str: ...
def stray_furniture(name: str, html: str) -> bool: ...
def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None: ...
```

`page_editor.py` adds `PiecesChanged`'s sentence to `face.SENTENCES` when it
is imported, as `editor.py` does. `Piece` is a frozen dataclass of `start`,
`end` (offsets into the file's text) and `shown` (§ 4.2).

### 4.2 The words view

**A piece** is a run of text between two markup constructs, as the file holds
it: character references undecoded, whitespace included. A tag, a comment, a
doctype and a processing instruction are markup. Each piece is found with
Python's `html.parser.HTMLParser`, which reads markup that is not well
formed rather than refusing it, so such a page still has pieces.

**`pieces(name, html)` returns the pieces the box shows, in file order.**
`BuildStopped` from `furniture_spans` passes through it. It leaves
out:

- text inside a `script`, `style` or `template` element;
- text inside a span `furniture_spans` returns;
- a piece whose shown form is empty.

**A piece's shown form** is `html.unescape(piece)`, with every run of
whitespace made one space, and stripped.

**`words(name, html)`** is the shown forms joined by one blank line, `"\n\n"`.

**`put_words(name, html, box)`** reads the box back:

1. `\r\n` and a lone `\r` become `\n`.
2. It is split on every line that is empty or whitespace alone. Each part is
   stripped, and empty parts at either end are dropped.
3. **A count that differs from `pieces(name, html)`'s raises `PiecesChanged`.**
4. A part equal to its piece's shown form leaves the piece's bytes as they
   are. Any other part replaces the piece with the piece's own leading
   whitespace, then `html.escape(part, quote=False)`, then its own trailing
   whitespace.

Every byte outside a changed piece is the file's as it was.

### 4.3 The code view

**`put_code(html, text)`** turns the posted text into the file to write. The
text's `\r\n` and lone `\r` become `\n`. Its lines are matched against the
file's lines, compared without their endings, with `difflib.SequenceMatcher`.
**The posted text decides which lines end**: every line but a last one with no
line break after it. **An ending line the match leaves unchanged ends as it did
in the file**, where it had an ending there. Any other ending line takes the
ending of the line before it in the result, or the file's first line's ending
where it is first, or `\n` for a file with none.

**`stray_furniture(name, html)`** is true where any span `furniture_spans`
returns holds anything but whitespace, and false where `furniture_spans`
raises: the preview shows that failure instead. After a code-view save
of a fixed page it adds a notice: *"The text you put between the header or
footer markers will be replaced from the one Header or Footer when your site
is built. Edit the Header or Footer instead."*

### 4.4 The routes

`register` adds these. Every Store and Settings call runs inside
`face.capture()`, and its notices are shown. Every write, preview and publish
runs under `editor.LOCK`. Every page is registered with `publishing=False`.

| Route | What it does |
|---|---|
| `GET /page?kind=&name=&view=&show=` | the page editor (§ 4.5) |
| `POST /page/save` | saves and previews (§ 4.6) |
| `POST /page/discard` | bins the waiting copy (§ 4.8), then 303 to the page |
| `POST /page/publish` | saves, then publishes the waiting copy (§ 4.7) |

`kind` is `pages` or `furniture`. `view` is `words` or `code`, and defaults to
`words` for a fixed page. **The furniture always opens in `code`** (§ 3
decision 5). `show` defaults to `HOME` where the Store holds it, else the
first fixed page `list_html` gives, else the newest entry.

**The list at `/`** (PRESS-0012 § 4.5) gains a section after the entries: each
fixed page by name, `index` shown as *Home*, then *Header*, *Footer* and
*Navigation*. Each row opens `/page?kind=&name=` and says where its changes
are not on the site yet. `editor._list` draws it from `store.list_html` and
`store.html_path_for(..., waiting=True)`, so `editor.py` imports nothing of
`page_editor.py`, which imports it.

### 4.5 The page editor

`GET /page` reads the waiting copy where one exists, else the live file.
`EntryNotFound` through `Face.fail` where neither exists. **A file whose
markers do not pair opens in the code view**, whatever `view` says, with
`BuildStopped`'s sentence above the box.

The page carries `kind`, `name`, `view`, `show`, `waiting` (`1` where it read
the waiting copy, else `0`), and `base`: the SHA-256 hex digest of the file's
bytes as read. It holds one `<textarea>` whose content
starts with a line break (PRESS-0012 § 4.7) and then the escaped words or the
escaped file. The preview sits in the same sandboxed frame as the entry
editor's.

- A **Show me the code** button, or **Back to the words**, reloads the page in
  the other view. The furniture shows neither.
- The furniture shows the picker: a link per fixed page, and one for his
  newest entry where he has one. Each reloads the page with that `show`.
- With a waiting copy it shows **Throw away changes** and says its changes are
  not on the site yet. Without one it says his changes stay on this computer
  until he publishes this page.
- It shows **Publish** and, after a publish, the **Undo the last publish**
  button PRESS-0015 § 4.6 puts beside the Published message.
- The box's styling class is `builder.BODY_CLASS` in the words view only.

**Opening builds the preview**, as PRESS-0012 § 4.7 does: § 4.6 step 5 for the
file opened.

**Its script** is PRESS-0012 § 4.7's: a save about a second after the last
change, never two in flight, a save on `pagehide`, and a stop on any reply
that is not 200. A switch of view or a picker link waits for a save in flight
and saves an unsaved change first.

### 4.6 A save

Fields: `kind`, `name`, `view`, `show`, `waiting`, `base`, `text`. In order,
under the lock:

1. **Read the file `waiting` names.** A missing one raises `EntryNotFound`.
2. **Check it is the one this window saw.** A digest that differs from `base`
   raises `editor.ChangedElsewhere`. So does a waiting copy that exists where
   `waiting` is `0`.
3. **Make the new file.** `put_words` or `put_code`, by `view`.
   **`PiecesChanged` writes nothing** and answers § 4.6's JSON with `hint` set
   to its sentence and `base` unchanged. The page keeps saving.
4. **Write it** with `store.write_html(..., waiting=True)`. The new `base` is
   the digest of the written file.
5. **Preview it.** `settings.load(folder)`, then `builder.preview_html(folder,
   settings, folder / editor.PREVIEW_FOLDER, Html(kind, name, <the new
   file>), show=…, photo_src=editor.photo_src)`. A fixed page shows itself.

A failure at steps 1, 2 and 4, and a `BuildStopped` at step 3, answers `Reply`
status 409 holding
`face.fail(failure, publishing=False)`, and nothing is written. **A failure at
step 5 keeps the save** and is shown in the preview's place, as PRESS-0012
§ 4.8 does.

A save answers status 200, `application/json`:

```json
{"waiting": <bool>, "base": "…", "preview": "/preview/…" or null,
 "failure": "<fragment>" or null, "hint": "<sentence>" or null,
 "notices": "<fragment>"}
```

`waiting` and `base` name the file the page saves to next.

### 4.7 Publishing a page

`POST /page/publish` takes § 4.6's fields. Under `editor.LOCK`, held
throughout:

1. **Save**, as § 4.6 steps 1 to 4. A 409 there answers as a failed save does.
   A `PiecesChanged` publishes nothing and answers status 200 with the reply
   below, `published` false and `hint` set to its sentence.
2. **Settings and the key**, as PRESS-0013 § 4.2 steps 2 and 3.
3. **Move.** Remember the live file's text. Write the waiting copy's text over
   it with `store.write_html`.
4. **Publish.** `publishing.publish(folder, settings, key, entry=None,
   capture=face.capture, notices=…, transport=transport)`, with the
   `transport` `register` was handed, as `publishing.register` takes one.
5. **Finish.** Bin the waiting copy. A failure here never replaces the
   publish's result; the reply says the waiting copy was left and can be
   thrown away.

**A failure at step 4 writes the remembered text back over the live file,
then is shown.** The waiting copy is left as it is. **An
`publisher.OutcomeUnknown` is not put back**: step 5 runs and it is shown, as
PRESS-0013 § 4.3 has it. A failure while putting back is shown in place of the
original.

The reply is PRESS-0013 § 4.2's JSON with `slug` and `draft` left out, and
`waiting`, `base` and `hint` as § 4.6's reply has them. `waiting` and `base`
are read from disk after the publish: the waiting copy where one is left, else
the live file.

### 4.8 Throwing away changes

Fields: `kind`, `name`, `base`. Under the lock, `editor.ChangedElsewhere`
unless a waiting copy exists and its digest equals `base`, answered as § 4.6's
failures are. Then `store.move_to_bin` on it. The live file is not touched.

### 4.9 What this item never does

- It never writes a live page or furniture file except at § 4.7 step 3 and its
  put-back.
- It never parses a file to regenerate it. The words view replaces pieces in
  place, and the code view writes what he typed.
- It never builds into `settings.site_folder` for a preview.
- It never adds, removes or renames a fixed page.
- It never unlinks a file; the bin is how anything goes.

## 5. Invariants

The tests below are in `tests/test_page_editor.py` unless named otherwise. The
route tests run through `face.serve(tmp_path, open_browser=False)`, as
`tests/test_editor.py` does, over furniture and pages made with
`store.write_html`.

- **INV-1** — A words save changes only the pieces he changed.
  *Test:* `test_words_change_only_their_own_bytes`. A page carrying CRLF
  endings, `&amp;` and `&#8217;` in text, an attribute holding a word that is
  also a piece, a comment, and irregular indentation. One paragraph changes.
  The written file equals the original with that one piece replaced, compared
  as bytes.
  *Breaks when:* the file is re-serialised by a parser, or a replace-by-value
  hits the attribute's copy of the word.

- **INV-2** — The words view shows only visible text.
  *Test:* `test_the_box_leaves_out_what_is_not_words`. Text inside `script`,
  `style` and `template`, between a `HEADER:START` and `HEADER:END`, in a
  comment, and whitespace alone, is absent from `words`. A heading and a
  paragraph are present, in order.
  *Breaks when:* script or style text is treated as data, or the marker span is
  not skipped.

- **INV-3** — A box whose paragraph count changed writes nothing and keeps the
  page saving.
  *Test:* `test_a_changed_paragraph_count_writes_nothing`. A box with one
  paragraph added, and one with a paragraph emptied, each answer 200 with
  `PiecesChanged`'s sentence as `hint`, the old `base`, `waiting` false, and no
  waiting copy.
  *Breaks when:* extra paragraphs are appended to the last piece, or the
  refusal answers 409.

- **INV-4** — Words go back as words.
  *Test:* `test_typed_markup_is_written_as_text`. A paragraph changed to
  `a <b>bold</b> & more` is written `a &lt;b&gt;bold&lt;/b&gt; &amp; more`.
  *Breaks when:* the part is written unescaped.

- **INV-5** — A code save keeps the endings of the lines he did not touch.
  *Test:* `test_code_keeps_untouched_line_endings`. A file mixing `\r\n` and
  `\n` lines, posted back with every ending `\n` and one line changed. Every
  other line's bytes are the original's, ending included.
  *Breaks when:* the text is written as posted, or every line takes one
  ending.

- **INV-6** — Editing never changes the live file, and later saves write the
  one waiting copy.
  *Test:* `test_edits_wait_in_a_copy`. Two saves of a fixed page and two of the
  footer. Each live file's bytes are unchanged; each waiting folder holds one
  file.
  *Breaks when:* a save writes the file it read.

- **INV-7** — A save over a file this window did not see writes nothing.
  *Test:* `test_a_stale_page_window_writes_nothing`. Two saves with one `base`:
  the second answers 409 with `ChangedElsewhere`'s sentence. Then a window
  opened on the live file, a waiting copy written behind it, and a save: 409,
  and the copy is unchanged.
  *Breaks when:* the digest check is dropped, or the live-file case checks the
  digest alone.

- **INV-8** — A waiting copy never reaches the site.
  *Test:* `tests/test_builder.py::test_a_waiting_copy_is_not_built`. A Store
  with a waiting copy of a page and of the footer builds a site whose files
  equal, byte for byte, those of the same Store without them. `content/`
  holds neither folder.
  *Breaks when:* the Builder lists a waiting folder, or `content()` copies one.

- **INV-9** — Publishing a page publishes its waiting copy and bins it; a
  definite failure puts the live file back.
  *Test:* `test_publishing_a_page`. Through the recording transport PRESS-0013
  uses: a publish leaves the live file holding the copy's text, the copy in
  the bin, and the uploaded page holding the change. With the transport
  answering 401, the live file's bytes are the originals and the copy is
  unchanged. With the transport raising on the reference update, the live file
  holds the change and the copy is in the bin.
  *Breaks when:* the copy is binned before the upload, or an unknown outcome
  is put back.

- **INV-10** — A page preview is the Builder's page.
  *Test:* `tests/test_builder.py::test_a_page_preview_is_the_page_build_writes`.
  For a changed footer shown on `about`, on `index` and on the newest entry,
  and for a changed `about` shown on itself, `preview_html` writes bytes equal
  to `build(..., change=…)` at the returned path.
  *Breaks when:* `preview_html` fills the furniture from the Store rather than
  from `change`, or renders a fixed page by its own route.

- **INV-11** — A page preview writes one page.
  *Test:* `tests/test_builder.py::test_a_page_preview_writes_one_page`. After
  two previews showing different pages, `into` holds exactly the second's
  path.
  *Breaks when:* `preview_html` runs the whole build.

- **INV-12** — Text between a page's markers is warned about, and nothing
  else is.
  *Test:* `test_stray_furniture_is_warned_about`. A code save putting a word
  between `FOOTER:START` and `FOOTER:END` answers with the notice. A save
  leaving only whitespace there answers without it, and so does a words save
  of a page whose live file already holds a word there.
  *Breaks when:* the check reads the whole file, or runs on words saves.

- **INV-13** — The furniture opens in the code view only.
  *Test:* `test_furniture_has_no_words_view`. `GET /page?kind=furniture&name=
  footer&view=words` shows the file in the box, and no view button.
  *Breaks when:* `view` is honoured for the furniture.

- **INV-14** — Throwing away changes bins the waiting copy and nothing else.
  *Test:* `test_throwing_away_page_changes`. The copy is in the bin and the
  live file's bytes are unchanged. With no waiting copy the request answers
  `ChangedElsewhere` and moves nothing.
  *Breaks when:* the live file is binned, or a missing copy is read as the live
  file.

- **INV-15** — Every page route sits behind the Face's boundary.
  *Test:* `test_the_page_editor_sits_behind_the_faces_boundary`. `GET /page`
  and `POST /page/save` without the cookie answer 403. `POST /page/save` with a
  foreign `Origin` answers 403 and writes nothing, and with the Face's own
  `Origin` it saves.
  *Breaks when:* a route is served through anything but `add_page`.

- **INV-16** — A waiting copy's name follows the live file's rule.
  *Test:* `tests/test_store_extras.py::test_waiting_copies_follow_the_name_rule`.
  `html_path_for(..., waiting=True)` refuses what it refuses without, and
  `sidebar` under the furniture. `move_to_bin` takes a waiting copy.
  *Breaks when:* the waiting path skips the name check, or the bin refuses the
  folder.

`PiecesChanged` gets a sentence.
`tests/test_face.py::test_every_failure_type_has_a_sentence` finds it without
a change.

## 6. Failure modes

| What breaks | What he sees | What is left on disk |
|---|---|---|
| He adds or removes a paragraph in the box | the hint; saving continues | the file as it was |
| Another window saved the page first | `ChangedElsewhere`; saving stops | the other window's save |
| A marker with no partner, typed in the code view | the save succeeds; `BuildStopped` in the preview's place | the save |
| Pressless is not set up | the save succeeds; `NotSetUp` in the preview's place | the save |
| The publish fails | the failure; the live page as it was | the waiting copy |
| The upload's outcome is unknown | `OutcomeUnknown`'s sentence | the change live in the Store; the copy binned |
| The copy cannot be binned after a publish | the Published message and a note | the copy |
| He types between the markers | the notice | the save |

## 7. Tests

`tests/test_page_editor.py` — new, in CI. It carries INV-1, INV-2, INV-3,
INV-4, INV-5, INV-6, INV-7, INV-9, INV-12, INV-13, INV-14 and INV-15.

`tests/test_builder.py` gains INV-8, INV-10 and INV-11.
`tests/test_store_extras.py` gains INV-16.

Each test is seen failing against stubs that raise `NotImplementedError`,
then mutation-probed once the code lands, one mutation per route its
*Breaks when* names.

## 8. Alternatives considered (and rejected)

- **Save straight into the page file.** Rejected by the user: the next
  publish of anything would send out a half-finished page or footer.
- **A field per piece of text.** Rejected by the user: the home page's tiles
  alone would make a long column of small fields.
- **Always the home page for a furniture preview.** Rejected by the user: a
  footer broken only on entry pages would not show.
- **A standing note, or a locked marker span.** Rejected by the user: a note
  always shown stops being read, and a refusal while typing is jarring.
- **One box per HTML block, inline tags kept.** Rejected: writing a changed
  block back would have to decide where each inline tag's words went.
- **A nested `changes/pages/` folder.** Rejected: `move_to_bin` takes a file
  exactly one folder deep, and widening it widens what may be binned.
- **Normalise the code view to one line ending.** Rejected: it rewrites lines
  he never touched (PRESS-0006 § 4.2).

## 9. Out of scope

- Adding, removing or renaming a fixed page — not queued.
- Styling in the words view — `docs/design.md` rules it out.
- Choosing a template — PRESS-0017.
- The photographs a page shows — PRESS-0016.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_page_editor.py::test_words_change_only_their_own_bytes` |
| INV-2 | `tests/test_page_editor.py::test_the_box_leaves_out_what_is_not_words` |
| INV-3 | `tests/test_page_editor.py::test_a_changed_paragraph_count_writes_nothing` |
| INV-4 | `tests/test_page_editor.py::test_typed_markup_is_written_as_text` |
| INV-5 | `tests/test_page_editor.py::test_code_keeps_untouched_line_endings` |
| INV-6 | `tests/test_page_editor.py::test_edits_wait_in_a_copy` |
| INV-7 | `tests/test_page_editor.py::test_a_stale_page_window_writes_nothing` |
| INV-8 | `tests/test_builder.py::test_a_waiting_copy_is_not_built` |
| INV-9 | `tests/test_page_editor.py::test_publishing_a_page` |
| INV-10 | `tests/test_builder.py::test_a_page_preview_is_the_page_build_writes` |
| INV-11 | `tests/test_builder.py::test_a_page_preview_writes_one_page` |
| INV-12 | `tests/test_page_editor.py::test_stray_furniture_is_warned_about` |
| INV-13 | `tests/test_page_editor.py::test_furniture_has_no_words_view` |
| INV-14 | `tests/test_page_editor.py::test_throwing_away_page_changes` |
| INV-15 | `tests/test_page_editor.py::test_the_page_editor_sits_behind_the_faces_boundary` |
| INV-16 | `tests/test_store_extras.py::test_waiting_copies_follow_the_name_rule` |
| `PiecesChanged` has a sentence | `tests/test_face.py::test_every_failure_type_has_a_sentence` |
| The buttons, the picker and the script's timing (§ 4.5) | **nothing** in CI — by hand, in a browser; PRESS-0133 carries the by-hand rows |
| A real page publish against GitHub | **nothing** in CI — by hand |
| That the words view reads as his words on his real pages | **nothing** — read on the page, against the live site's About, Music and Privacy |

## 11. Cross-doc impact

- `docs/specs/PRESS-0006-pages-furniture-comments.md` § 4.1 and § 4.3 —
  `html_path_for` and `write_html` gain `waiting`, and the two waiting folders
  join the layout. The sections point here.
- `docs/specs/PRESS-0008-builder.md` § 4.1 and § 4.4 — `preview_html` and
  `furniture_spans` are added. The sections point here.
- `docs/specs/PRESS-0012-editor.md` § 4.5 — the list gains the pages section.
- `docs/specs/PRESS-0013-publish.md` § 4.1 — it already names this item as a
  caller of `publish` with `entry=None`; no change.
- `docs/specs/PRESS-0015-undo.md` — no change. A waiting copy is not under
  `content/`, so undo leaves it alone, as it leaves a draft.
- `docs/standards/versioning-overrides.md` § The writer's own files — the two
  waiting folders become part of where the Store keeps things. Adding them
  breaks nothing an upgrade relies on. PRESS-0138 owes them a check.
- `src/pressless/__main__.py` — the launch registers `page_editor.register`.
  PRESS-0013's INV-8 asserts which routes are registered, so its test gains
  the four.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0014-fixed-pages-loop-log.md`.

## 13. Resource cost

A save builds one page, as an entry's save does. The largest furniture change
is still one page per preview, whichever page the picker shows.
