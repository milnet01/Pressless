<!-- ants-spec-format: 1 -->
# PRESS-0215 — Blocks: a page held as ready-made sections

**Status:** spec draft (2026-10-13).
**Kind:** feature.
**Source:** ROADMAP PRESS-0215 (S15; `docs/design.md` § What may depend
on what, under *Pages, and how they are held*; the user 2026-10-02 and
2026-10-13).

**Blocker for:** PRESS-0260, the visual editor, which reads and writes
pages only through this. **Pairs with:** PRESS-0126 and PRESS-0195,
whose new pages this item writes in sections.

Layman: no visible change yet. Every page Pressless makes is now held as
sections, such as a heading, a paragraph or a picture, so the visual
editor can change them; the published pages look exactly as before.

## 1. Goal

A new module, `src/pressless/blocks.py`, reads a fixed page into a list
of sections and writes the list back. A page Pressless did not mark can
be taken into sections without changing what it shows. The Builder
publishes pages without the marks. Starter and newly added pages are
written in sections from the start.

## 2. Problem

1. **Nothing says where one part of a page ends and the next begins.**
   A fixed page is the user's own HTML (PRESS-0006), and the only marks
   in it are the header and footer pairs `builder.furniture_spans`
   finds. A visual editor needs units it can show, move and change.
2. **The two editors would fight without a rule.** `docs/design.md`
   § What may depend on what sets it, under its round-trip rule: a section whose stored HTML
   is not exactly what Blocks would write is a code section, kept
   byte for byte. Nothing yet decides what "exactly" means.
3. **Every page that exists today has no marks.** Imported pages
   (`pressless_import._fixed_pages`), the starter set (`starter.fill`)
   and added pages (`starter.new_page`) are plain HTML.
4. **WordPress shows the cost of changing a section's HTML later.** Its
   editor compares stored HTML against what each block's code writes
   today, so a code change turns older pages' blocks invalid, which is
   why each block carries a list of its earlier forms. Source:
   https://developer.wordpress.org/block-editor/explanations/architecture/data-flow/

## 3. Scope decisions (agreed with the user)

1. **Split into three items.** The user, 2026-10-13: this item is
   Blocks; the visual editor is PRESS-0260; code-box highlighting is
   PRESS-0261.
2. **An unmarked page has its plain paragraphs, headings and pictures
   recognised, and everything else kept as code.** The user,
   2026-10-13. The file is reshaped once, when it is first taken into
   sections (§4.6).
3. **The Builder leaves the marks out of the published site.** The
   user, 2026-10-13. The Store's file keeps them.
4. **The nine kinds are the roadmap's.** The user, 2026-10-02: text, a
   heading, a picture, a row of pictures, a button, a video, a music
   player, a download, and columns.
5. **(decided here) A mark is an HTML comment naming the kind and
   nothing else.** Every value a section holds is read from its HTML,
   so nothing is stored twice (§8).
6. **(decided here) A page has one sections area, inside its `main`.**
   Everything outside it, the header and footer markers included, is
   the page's frame and is changed only in the code view.
7. **(decided here) A video is the user's own file or a YouTube
   address.** A YouTube video is shown through
   `www.youtube-nocookie.com`.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/blocks.py -- pure calculation: no disk, no network

TEXT, HEADING, PICTURE, PICTURES, BUTTON = "text", "heading", "picture", "pictures", "button"
VIDEO, MUSIC, DOWNLOAD, COLUMNS = "video", "music", "download", "columns"
KINDS = (TEXT, HEADING, PICTURE, PICTURES, BUTTON, VIDEO, MUSIC, DOWNLOAD, COLUMNS)
CODE = "code"

class SectionRefused(ValueError): ...   # write() was handed a section it cannot write

@dataclass(frozen=True)
class Section:
    kind: str                                   # one of KINDS, or CODE
    fields: Mapping[str, str] = {}              # § 4.4, per kind
    parts: tuple[tuple["Section", ...], ...] = ()   # PICTURES: one; COLUMNS: one per column
    source: str = ""                            # CODE only: its bytes, marks included

@dataclass(frozen=True)
class Page:
    before: str                  # the file up to and including the area's opening mark
    sections: tuple[Section, ...]
    gaps: tuple[str, ...]        # whitespace before each section, then before the closing mark
    after: str                   # the closing mark and the rest of the file

def read(name: str, html: str) -> Page | None: ...
def write(page: Page) -> str: ...
def section_html(section: Section) -> str: ...
def adopt(html: str, furniture: tuple[tuple[int, int], ...]) -> str | None: ...
def unmarked(name: str, html: str) -> str: ...
```

`read` returns `None` for a file with no sections area. `adopt` returns
`None` where § 4.6 finds no area to make. `Section.fields` is a frozen
mapping. `len(gaps) == len(sections) + 1`.

**`blocks` imports only the standard library.** The Builder imports it
(§4.7), so it cannot import the Builder; `adopt`'s caller passes
`builder.furniture_spans(name, html)` as `furniture`.

### 4.2 Marks

```
<!-- pressless:page -->        opens the sections area
<!-- /pressless:page -->       closes it
<!-- pressless:<kind> -->      opens a section of that kind
<!-- /pressless:<kind> -->     closes it
<!-- pressless:column -->      opens one column inside a columns section
<!-- /pressless:column -->     closes it
```

Each mark is exactly these bytes: `<!-- `, the name, ` -->`, one space
each side. `<kind>` is one of `KINDS` or `code`. **A mark counts only
where `html.parser.HTMLParser` reports it as a comment**, so text inside
a `script` or `style` element, or inside an attribute, is never a mark.

**The area** is the text between the first `pressless:page` opening
mark and the next `/pressless:page` mark. A page with no opening mark,
or an opening mark with no closing one, has no area.

### 4.3 Reading

`read` walks the area from its start. At each point, after any
whitespace (which goes into `gaps`):

1. **An opening section mark** starts a section running to the next
   closing mark of the same kind at the same depth. The section's
   bytes are both marks and everything between.
2. **A section's bytes are read as its kind only where
   `section_html(<the section read>)` returns exactly those bytes.**
   Any other bytes, and a kind not in `KINDS`, make it a `CODE` section
   whose `source` is the bytes.
3. **An opening mark with no matching closing mark, a closing mark
   with no opening one, and any other content** start an unmarked code
   run. It runs to the next opening section mark at this depth, or to
   the area's end, with trailing whitespace left to `gaps`. It is a
   `CODE` section whose `source` holds no marks.

A columns section reads each `pressless:column` pair inside it by the
same three rules, one depth down; a column holds no columns or row of
pictures. A row of pictures reads its pictures the same way.

**`write(page)`** is `before`, then each gap followed by its section's
bytes, then the last gap and `after`. A section's bytes are `source`
for `CODE`, else `section_html(section)`.

### 4.4 The kinds

`<inline>` is text and these elements only: `a` with an `href` and no
other attribute, `strong`, `em`, `br`. Text is written through
`html.escape(text, quote=False)`; an attribute value through
`html.escape(value, quote=True)`. `section_html` writes each kind
inside its two marks, with no whitespace between a mark and the HTML:

| Kind | Fields | HTML between the marks |
|---|---|---|
| text | `html` | `<p><inline></p>` |
| heading | `level` (`1`–`6`), `html` | `<h<level>><inline></h<level>>` |
| picture | `src`, `alt`, optional `width`, `height`, `caption` | `<img src alt [width height]>`; with a caption, `<figure>` round the `img` and a `<figcaption><inline></figcaption>` |
| pictures | none; `parts[0]` its pictures | `<div class="pressless-pictures">` round the picture sections |
| button | `href`, `label` | `<p class="pressless-button"><a href>label</a></p>` |
| video | `src`, or `youtube` (an id) | `<video controls preload="metadata" src></video>`, or an `iframe` to `https://www.youtube-nocookie.com/embed/<id>` with `title`, `allowfullscreen` and `loading="lazy"` |
| music | `src` | `<audio controls preload="metadata" src></audio>` |
| download | `href`, `label` | `<p class="pressless-download"><a href download>label</a></p>` |
| columns | none; `parts` two to four columns | `<div class="pressless-columns">` round each `<div class="pressless-column">`, each column in its marks |

The `html` and `caption` fields hold `<inline>` as `section_html`
writes it. Attributes are written in the table's order, each value in
double quotes. Nothing separates the parts inside a pictures or columns
section, so a hand-spaced one reads as `CODE` (§4.3 step 2).

**`section_html` raises `SectionRefused`** for a kind outside `KINDS`
and `CODE`, a missing field, an `html` or `caption` that is not
`<inline>`, a `level` outside `1`–`6`, a `youtube` id outside
`[A-Za-z0-9_-]{11}`, columns with fewer than two or more than four
parts, and any address (`src`, `href`) that is not a relative path or
an `http:`, `https:` or (for `href` only) `mailto:` address. For `CODE`
it returns `source`.

### 4.5 Earlier forms

`blocks` keeps, per kind, every form `section_html` has ever written,
as a reader beside the current writer. Step 2 of § 4.3 accepts a
section whose bytes are any recorded form of its kind; the section read
is then written in the current form at the next save. **A change to a
kind's HTML adds a form, and never removes one.** This item ships one
form per kind.

### 4.6 Taking a page into sections

**`adopt(html, furniture)`** returns `html` unchanged where it already
has an area. Otherwise:

1. **The area to make** is the content of the first `main` element
   whose start and end tags both lie outside every span in
   `furniture`. No such element, or one holding a furniture span,
   gives `None`.
2. **Its top-level nodes are sorted.** A `p` with no attributes whose
   content is `<inline>` is a text section. An `h1` to `h6` with no
   attributes whose content is `<inline>` is a heading. An `img` with
   `src` and any of `alt`, `width` and `height` and nothing else is a
   picture. Every other run of nodes between two of these is one code
   section, its bytes as they were.
3. **The file is rewritten:** the area's marks just inside `main`'s
   tags, each recognised node as `section_html` writes it, each code
   run in `code` marks round its own bytes, and the whitespace between
   nodes as it was. Every byte outside `main`'s content is as it was.

A recognised node's rewrite changes only spellings: how a character
is written (`&#8217;` becomes `’`), attribute quoting and order. What
`HTMLParser` reports for it, text decoded, is the same before and
after (INV-5).

### 4.7 Publishing without the marks

**`unmarked(name, html)`** returns `html` with every mark `read` finds
removed: the area's two, each section's two and each column's two. A
mark alone on its line takes its line, the line ending included; any
other mark takes only its own bytes. A file `read` finds no area in is
returned as it is.

The Builder's `_Build.fixed_page` passes each page through `unmarked`
before `_fill_fixed_page`, for the site folder and for `preview_html`
alike. The Store's file is never written by the Builder.

### 4.8 New pages

`starter._PAGE`, `starter.new_page` and `starter.privacy_page` write
their `main`'s content as a sections area: the heading as a heading
section and each paragraph as a text section. The words those
functions write are unchanged, and PRESS-0014's words view still finds
them, since marks are comments and `page_editor.pieces` skips markup.

### 4.9 What this item never does

- It changes no page on disk except a page it writes new (§4.8). Taking
  an existing page into sections waits for PRESS-0260, which calls
  `adopt` at a save.
- It shows nothing new on any screen.
- It sends nothing anywhere, and loads nothing from elsewhere.

## 5. Invariants

- **INV-1** — `write(read(name, html)) == html` for every `html` `read`
  finds an area in, byte for byte.
  *Test:* `tests/test_blocks.py::test_every_page_writes_back_as_it_was`,
  over every page fixture in the suite, every mark-pairing fault in
  § 4.3 step 3, and the real archive's pages in
  `tests/test_blocks_archive.py`.
  *Breaks when:* a gap, an unmarked run or a code section's source is
  re-spelled on the way through.

- **INV-2** — A section whose bytes are not a recorded form of its kind
  reads as `CODE`, with those bytes as its `source`.
  *Test:* `tests/test_blocks.py::test_a_changed_section_reads_as_code`:
  a text section given `class="x"` on its `p`, and one with a `span`
  inside, each read as `CODE`.
  *Breaks when:* step 2 of § 4.3 compares anything looser than bytes,
  such as the parsed tree.

- **INV-3** — For every kind, `read` of a page holding
  `section_html(s)` gives back `s`.
  *Test:* `tests/test_blocks.py::test_every_kind_reads_back_as_written`,
  one section per kind and per optional field.
  *Breaks when:* a field is written but not read back, such as a
  picture's caption.

- **INV-4** — Every recorded form of every kind still reads as that
  kind.
  *Test:* `tests/features/blocks/forms/`, one frozen file per kind per
  form, each read by
  `tests/test_blocks.py::test_every_earlier_form_still_reads`. A
  fixture is added with each new form and never edited.
  *Breaks when:* a change to `section_html` drops the reader for the
  form it replaced.

- **INV-5** — `adopt` changes no node's meaning: the `HTMLParser`
  events of `unmarked(name, adopt(html, furniture))`, with text decoded and
  attributes compared as sets, equal those of `html`.
  *Test:* `tests/test_blocks.py::test_adopting_keeps_what_the_page_shows`,
  over fixtures holding character references, single-quoted and
  unquoted attributes, a `p` with a class, a `b`, a `figure`, a
  `script` and a comment; and over the archive's pages.
  *Breaks when:* a recognised node loses an attribute, or whitespace
  inside it is collapsed.

- **INV-6** — `adopt` leaves every byte outside the content of the
  `main` it marks as it was, and returns a page with an area already
  in it unchanged.
  *Test:* `tests/test_blocks.py::test_adopting_touches_only_main`
  compares the prefix and suffix, and adopts an adopted page twice.
  *Breaks when:* the header markers or the `head` are re-spelled, or a
  second call adds a second area.

- **INV-7** — No mark `read` finds reaches the site folder or a
  preview, and a page `read` finds no area in is built as before.
  *Test:* `tests/test_builder.py::test_marks_never_reach_the_site`
  builds a starter site and an adopted page, and searches every built
  file for `pressless:`; a page with no area builds byte-identical to
  today.
  *Breaks when:* `fixed_page` skips `unmarked` on one path.

- **INV-8** — `section_html` writes no address but a relative path or
  an `http:`, `https:` or `mailto:` one, and no text unescaped.
  *Test:* `tests/test_blocks.py::test_unsafe_addresses_are_refused`:
  `javascript:`, `data:`, ` javascript:` with a leading space and an
  upper-case `JAVASCRIPT:` each raise `SectionRefused`; a label holding
  `<script>` is written escaped.
  *Breaks when:* the scheme check reads the address before stripping
  and folding it, as a browser does.

- **INV-9** — A comment that `HTMLParser` does not report as a comment
  is never a mark.
  *Test:* `tests/test_blocks.py::test_marks_in_scripts_are_text`: a
  `script` holding `<!-- pressless:page -->` gives `read` no area, and
  `unmarked` leaves it.
  *Breaks when:* marks are found by a text search over the file.

- **INV-10** — A starter page and an added page read with every
  section a kind, none `CODE`.
  *Test:* `tests/test_blocks.py::test_new_pages_are_all_sections`, over
  each starter page, `new_page` and `privacy_page`.
  *Breaks when:* the starter's HTML drifts from `section_html`'s.

## 6. Failure modes

| What happens | What the user sees |
|---|---|
| Marks hand-edited so they no longer pair | That stretch is an unmarked code run; the page still opens and builds (§4.3 step 3) |
| A section's HTML hand-edited | It is a code section, kept byte for byte (INV-2) |
| `adopt` finds no usable `main` | `None`; PRESS-0260 opens the page in the code view, as today |
| Marker pairs that do not pair | `BuildStopped` from `furniture_spans`, as today |
| A page's words view adds a paragraph inside a text section (PRESS-0238) | That section becomes a code section; nothing is lost. PRESS-0260 retires the words view |
| A later Pressless writes a kind differently | The old form still reads as its kind (INV-4) |

## 7. Tests

| Test | Locks |
|---|---|
| `tests/test_blocks.py` | INV-1, INV-2, INV-3, INV-4, INV-5, INV-6, INV-8, INV-9, INV-10 |
| `tests/features/blocks/forms/` | INV-4's frozen forms |
| `tests/test_builder.py::test_marks_never_reach_the_site` | INV-7 |
| `tests/test_blocks_archive.py` | INV-1 and INV-5 over the real archive; skipped where the archive is absent, as the other archive tests are |

Each test is seen failing before the code it locks exists.

## 8. Alternatives considered (and rejected)

- **WordPress's JSON in the opening mark.** Every value would sit in
  the mark and again in the HTML, and the two could disagree. Reading
  values from the HTML keeps one copy.
- **`data-` attributes on each section's element.** They change the
  element, so an adopted page's nodes would gain attributes (INV-5),
  and a text section's `p` is no longer plain.
- **Comparing parsed trees instead of bytes for the round-trip rule.**
  Two spellings would both read as the kind, and the next save would
  re-spell what the user wrote by hand, which is the fight design.md
  rules out.
- **Keeping the marks in the published site.** The user chose to
  strip them (§3 decision 3).
- **Sections anywhere in the body.** The header markers, the `head`
  and wrapper elements would become things the visual editor could
  move. One area inside `main` keeps the frame out of reach.

## 9. Out of scope

- The visual editor, adopting a page at a save, and preview marks the
  editor may need — PRESS-0260.
- Highlighting in the code box — PRESS-0261.
- The header, footer and menu in sections — PRESS-0216.
- Interactive sections and their scripts — PRESS-0217.
- Recognising more than paragraphs, headings and pictures when a page
  is adopted — deferred; not yet queued.
- Styling the new classes in the three starter looks — deferred; not
  yet queued.

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | `tests/test_blocks.py::test_every_page_writes_back_as_it_was`; `tests/test_blocks_archive.py` |
| INV-2 | `tests/test_blocks.py::test_a_changed_section_reads_as_code` |
| INV-3 | `tests/test_blocks.py::test_every_kind_reads_back_as_written` |
| INV-4 | `tests/test_blocks.py::test_every_earlier_form_still_reads` |
| INV-5 | `tests/test_blocks.py::test_adopting_keeps_what_the_page_shows`; `tests/test_blocks_archive.py` |
| INV-6 | `tests/test_blocks.py::test_adopting_touches_only_main` |
| INV-7 | `tests/test_builder.py::test_marks_never_reach_the_site` |
| INV-8 | `tests/test_blocks.py::test_unsafe_addresses_are_refused` |
| INV-9 | `tests/test_blocks.py::test_marks_in_scripts_are_text` |
| INV-10 | `tests/test_blocks.py::test_new_pages_are_all_sections` |
| §4.5 "never removes a form" | INV-4's frozen fixtures, which fail when a reader goes |
| §4.9 "changes no page on disk" | **nothing** — no test watches every caller; review only |

## 11. Cross-doc impact

- `docs/decisions/ADR-0006-page-section-marks.md`, new, recording
  § 3 decisions 5 and 6 and § 8's first two rows; `docs/design.md`'s
  ADR table replaces its *Owed by PRESS-0215* row with it.
- `docs/design.md` § The parts: the Builder row gains "without the
  marks".
- PRESS-0126 § 9's "Starter pages written as Blocks sections" row is
  done by this item.
- `CHANGELOG.md`: one line, saying pages are now held as sections and
  nothing visible changes.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0215-blocks-loop-log.md`.

## 13. Resource cost

No new dependency. `read` and `adopt` are one parse of one page; no
state is kept between calls.
