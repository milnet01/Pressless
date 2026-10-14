<!-- ants-spec-format: 1 -->
# PRESS-0216 — The header, footer and menu in the visual editor

**Status:** accepted (2026-10-14). Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0216 (S15; the user's decision 2026-10-02
under PRESS-0198; a short spec and one review round, the user
2026-10-14).

**Blocked by:** PRESS-0260, shipped. **Changes:** PRESS-0014 § 3
decision 5 and § 4.4; PRESS-0215 § 3 decision 6, § 4.6 and § 4.7;
PRESS-0260 § 4.1 and § 4.2 (§ 11).

Layman: they change the top and bottom of every page, and the menu, the
same way they change a page, with no code.

## 1. Goal

The header and footer open in the visual view of PRESS-0260: the
preview shows a page with them in place, and the user picks and changes
their sections there. The menu opens in a visual view of its own: a
list of its links, each with its words and its address, which the user
reorders, changes, adds to and removes from. The code view stays for
all three.

## 2. Problem

1. **The furniture opens in the code view only.** `page_editor._view`
   returns `page_editor.CODE` for `store.FURNITURE_FOLDER` (PRESS-0014 § 3
   decision 5), so changing the header's words means editing HTML.
2. **The furniture carries the Builder's placeholders.**
   `builder._Furniture.fill` replaces `{{SITE_NAME}}`, `{{YEAR}}`,
   `{{UP}}`, `{{NAVIGATION}}` and others. The preview shows their
   filled values, so text typed over a filled value would write the
   value into the file and the placeholder would be gone from every
   page.
3. **Blocks makes an area only inside `main`.** `blocks.adopt` takes the
   content of the first `main`; a header or footer file has none.
4. **The menu may not be regenerated.** `menu.py` edits one link's
   bytes and keeps every other byte, because PRESS-0014 § 4.9 forbids
   parsing a file to write it back. Sections would rewrite it.

## 3. Scope decisions (agreed with the user)

1. **The header, footer and menu are changed in the visual editor.**
   The user, 2026-10-02 (PRESS-0198).
2. **A short spec, gated for one round.** The user, 2026-10-14.
3. **(decided here) The header and footer are held as sections; the
   menu is not.** The menu is a list of links, edited as one, in place
   (§ 4.4).
4. **(decided here) Words holding a Builder placeholder are shown as
   code.** They can be changed in the code box and never by typing over
   their filled value (§ 4.2).
5. **(decided here) The furniture opens in the visual view**, as a page
   does, unless the code was asked for. PRESS-0263's remembered view
   applies to it, and `_open` records a view asked for on the furniture
   as it does on a page.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 Sections in the header and footer

`blocks.adopt(html, furniture, element="main")` gains the keyword
`element`. The page editor's `_area` passes `"header"` for the header
file and `"footer"` for the footer file, and keeps `"main"` for a page.
Nothing else in `adopt` changes: the area is the first such element's
content, and a file with none opens in the code view with
`notice.page_editor.code_only`, as a page does (PRESS-0260 § 4.1).

The starter's header and footer adopt as they are written today: each
run of nodes inside `header` or `footer` that is not a plain `p`,
heading or picture becomes one code section.

### 4.2 Placeholders

**A text or heading section whose `html` holds `{{` is offered as code.**
`page_editor.outline` gives it `kind: "code"`, `marked: true`, and its
bytes between the marks as `code`, so the panel shows it in the code
box and the frame cannot be typed in. A save that leaves it unchanged
keeps it by its path, so its bytes and its text marks stay. A save that
changes it posts it as code, and it is written in code marks.

This holds for every page, not only the furniture: a page's own words
rarely hold `{{`, and where they do, the code box is the safe place for
them.

**Addresses keep `{{UP}}`.** For the furniture, the `up` `page_editor._panel`
puts before a held photograph's address is `{{UP}}` rather than `../`,
since one header serves pages at every depth. A picture's `src` or a
button's `href` holding `{{UP}}` is not a placeholder in words and does
not make its section code. A held photograph the header or footer names
is published as one a page names is: `builder._held_pictures` reads the
header and footer too, with `{{UP}}` read as the site's root.

### 4.3 The preview

`builder.preview_html(..., marks=True)` with a furniture `change` keeps
**that furniture file's marks**, wherever it is filled into the shown
page, and drops every other mark, the shown page's included. So the
frame pairs the header's or footer's sections and nothing else. Without
`marks`, and in every build for the site folder, `_Furniture.fill`
removes the furniture's marks by `blocks.unmarked`, as
`_Build.fixed_page` does for a page.

The editor's picker for the shown page (PRESS-0014 § 3 decision 3) and
PRESS-0263's remembered page work as they do in the code view.

### 4.4 The menu

The navigation file opens in a menu view: the side panel lists its
links in order, each with its words and its address, and offers Move
up, Move down and Remove per link, and **Add a link**, which takes a
page from the list of fixed pages or a typed address. The preview shows
the shown page with the menu as it was last saved.

`menu.links(text)` returns each link's words and address, in order, from
a plain menu, raising `menu.Unusual` on any other (`menu._plain`). A
menu that is not plain opens in the code view, with a notice saying
why.

A save posts `view=visual` and `links`, a JSON list in the new order;
`page_editor._write` sends a navigation save with `links` to
`menu.arranged(text, posted)` rather than to `put_sections`. Each entry
is `{"at": ..., "words": ..., "href": ...}`: `at` is the link's 0-based
place in `menu.links(text)` of the file read, `null` for a new link, and
`words` and `href` are as `menu.links` gave them, words decoded and
trimmed. An entry posted back as it was given is unchanged.
`menu.arranged` writes the file:

- The text before the first link and after the last stays as it is.
- Each kept link keeps its own bytes, and the whitespace before it, in
  its new place. Where its words or address changed, only those bytes
  change, as `menu.rename` changes them; an address changed to a fixed
  page also sets `data-nav` to that page's, and one changed to any other
  address removes it.
- A new link is written as `menu.add` writes one, with `data-nav` where
  its address is a fixed page, after the whitespace the first link has
  before it. The home page is the exception: its address is
  `{{UP}}index.html` and its `data-nav` is `Home`, as the starter's menu
  writes it.
- A link not posted is gone, with the whitespace before it.

A posted entry naming an `at` that is not a link, or naming one twice,
an empty `words`, or an address `blocks` would not link to, refuses the
save and writes nothing.

### 4.5 Saving and publishing

A visual save of the header or footer goes through
`page_editor.put_sections` as a page's does; a menu save goes through
`menu.arranged`. Both write the waiting copy, and the press publishes
it, as PRESS-0014 § 4.6 and § 4.7 have it today. Undo and the preview's
rules for the furniture (design.md § Where everything sits on disk) are
unchanged.

### 4.6 What this item never does

- It never writes a placeholder's filled value into the file.
- It never rewrites a menu link it was not asked to change.
- It never publishes a mark.

## 5. Invariants

- **INV-1** — A visual save of a header or footer already holding a
  sections area, that changes nothing, writes the file byte for byte as
  it was. The first save of one without an area writes it adopted, as
  for a page (PRESS-0260 § 4.1).
  *Test:* `tests/test_page_editor.py::test_a_furniture_save_of_nothing_changed_keeps_every_byte`.
  *Breaks when:* writing a marked header's area re-spells a byte outside
  a changed section.

- **INV-2** — A text or heading section holding `{{` is offered as code,
  and a save can never replace a placeholder with its filled value.
  *Test:* `tests/test_page_editor.py::test_words_holding_a_placeholder_are_code`
  outlines a footer holding `<p>&copy; {{YEAR}} {{SITE_NAME}}</p>` and
  finds kind `code`.
  *Breaks when:* `outline` offers that section as text, so the frame's
  filled words are posted back.

- **INV-3** — No mark reaches the site folder, from the furniture or a
  page.
  *Test:* `tests/test_builder.py::test_furniture_marks_are_never_published`
  builds a site whose header holds marks and finds no `pressless:` in
  any written file.
  *Breaks when:* `_Furniture.fill` is given the header's text without
  `blocks.unmarked`.

- **INV-4** — The visual preview of a furniture file keeps that file's
  marks and no other.
  *Test:* `tests/test_builder.py::test_a_furniture_preview_keeps_its_own_marks_alone`
  previews a header change on a marked page and finds the header's
  marks and none of the page's or the footer's.
  *Breaks when:* the shown page keeps its marks, so the frame pairs the
  page's sections against the header's outline.

- **INV-5** — `menu.arranged` given every link in its own place and
  unchanged returns the text unchanged; reordered, every byte outside
  the moved links' spans and the whitespace before them is unchanged.
  *Test:* `tests/test_menu.py::test_an_arranged_menu_keeps_every_other_byte`.
  *Breaks when:* the menu is written from the list of links rather than
  by moving their bytes, so a comment or the writer's spacing is lost.

- **INV-6** — A menu save naming an unknown or doubled `at`, empty words,
  or an address `blocks` would not link to writes nothing.
  *Test:* `tests/test_page_editor.py::test_a_menu_save_that_names_no_link_writes_nothing`.
  *Breaks when:* `arranged` skips a bad entry and writes the rest.

- **INV-7** — A menu that is not plain opens in the code view and is
  never written by a menu save.
  *Test:* `tests/test_page_editor.py::test_an_unusual_menu_opens_in_the_code_view`.
  *Breaks when:* the menu view lists the links of a menu `_plain`
  refuses, and a save rewrites it.

- **INV-8** — A held photograph a picture section in the header or
  footer names is in the site folder after a build.
  *Test:* `tests/test_builder.py::test_a_furniture_picture_is_published`.
  *Breaks when:* `_held_pictures` reads only the shown page's text, so
  the header's picture is a broken image on the live site.

## 6. Failure modes

| What goes wrong | What happens |
|---|---|
| The header has no `header` element | Opens in the code view with the notice (§ 4.1) |
| The menu is not plain | Opens in the code view with a notice (§ 4.4) |
| A save names a section or link that is not there | Refused, nothing written, the reason shown as for a page (PRESS-0260 § 6) |
| The file changed elsewhere since it was read | Refused as `editor.ChangedElsewhere`, as for a page |
| The preview cannot be built | The save stands and the failure shows beside it, as for a page |

## 7. Tests

INV-1, INV-2, INV-6 and INV-7 in `tests/test_page_editor.py`; INV-3,
INV-4 and INV-8 in `tests/test_builder.py`; INV-5 in `tests/test_menu.py`.
Each is seen failing first against the code before this item. The
panel's controls and typing in the header are checked in Chrome by
`scripts/by-hand-browser-checks.py`, and in Firefox and Edge by hand.

## 8. Alternatives considered (and rejected)

- **The menu as sections.** Rejected: a link is not one of the nine
  kinds, and writing the menu from sections regenerates it, which
  PRESS-0014 § 4.9 forbids.
- **Showing placeholders unfilled in the preview, as `{{SITE_NAME}}`.**
  Rejected: the preview stops looking like the page, which is the
  point of the visual view; the code box shows them as they are.
- **Changing `blocks.read` so a text section with `{{` reads as code.**
  Rejected: it changes PRESS-0215's contract for every caller; the
  editor's outline is the one place the risk arises.

## 9. Out of scope

- Picking a menu link by clicking it in the preview — deferred; not yet
  queued.
- Changing the site's name and description from the header — Settings
  owns them (PRESS-0213).
- Links nested in a submenu — deferred; not yet queued. Such a menu is
  not plain and opens in the code view.

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | `tests/test_page_editor.py::test_a_furniture_save_of_nothing_changed_keeps_every_byte` |
| INV-2 | `tests/test_page_editor.py::test_words_holding_a_placeholder_are_code` |
| INV-3 | `tests/test_builder.py::test_furniture_marks_are_never_published` |
| INV-4 | `tests/test_builder.py::test_a_furniture_preview_keeps_its_own_marks_alone` |
| INV-5 | `tests/test_menu.py::test_an_arranged_menu_keeps_every_other_byte` |
| INV-6 | `tests/test_page_editor.py::test_a_menu_save_that_names_no_link_writes_nothing` |
| INV-7 | `tests/test_page_editor.py::test_an_unusual_menu_opens_in_the_code_view` |
| INV-8 | `tests/test_builder.py::test_a_furniture_picture_is_published` |
| § 4.4 the menu view's controls | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |

## 11. Cross-doc impact

Landed with the code, each recording what the build settles under this
spec:

- `docs/specs/PRESS-0014-fixed-pages.md`: § 3 decision 5 and § 4.4's
  "the furniture always opens in `code`" annotated *amended by
  PRESS-0216*.
- `docs/specs/PRESS-0215-blocks.md`: § 3 decision 6 and § 4.6 annotated:
  `adopt` takes the element, `header` and `footer` for the furniture;
  § 4.7 annotated: a furniture preview keeps that file's marks (§ 4.3).
- `docs/specs/PRESS-0260-visual-editor.md`: § 4.1 and § 4.2 annotated
  *amended by PRESS-0216*: the furniture opens in the visual view, and
  its preview keeps its own marks and not the page's.
- `CHANGELOG.md`: one entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0216-furniture-visual-loop-log.md`.

## 13. Resource cost

No new dependency. A save reads and writes one file and builds one
preview, as today.
