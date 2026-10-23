<!-- ants-spec-format: 1 -->
# PRESS-0196 — The site's look: a panel of choices, and their own CSS

**Status:** accepted (2026-10-15). Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0196 (the user 2026-10-01 under PRESS-0194; the
panel, the extra-CSS box, CSS-only effects and the two scope calls, the user
2026-10-15).

**Builds on:** PRESS-0126 (the starter site and its style code), PRESS-0248
(each look's named colours, light and dark). **Changes:** PRESS-0126 § 9,
which deferred the look's editing and its travel in `content/` to this item.
**Split off:** PRESS-0276 (an imported site's look), PRESS-0273 (a page's
own CSS).

Layman: a Look screen lets them change their website's colours (for light
and dark), fonts, text size, page width and header layout, and switch on a
few gentle effects, watching the homepage change as they go. Anyone who
knows CSS can add their own styling at the bottom. It reaches the website the
next time they publish.

## 1. Goal

A site with a Pressless look is restyled from a Look screen in the Face,
without editing a stylesheet. Each choice shows at once in a preview of the
homepage, a readability warning appears beside any text colour that is hard
to read, and Save keeps the choices for the next publish. Undo brings back an
earlier look along with the rest of the site.

## 2. Problem

1. The site's style code, `look/style.css` in the Store, is written once, by
   `starter.fill` where it is absent, from `starter._style_code`. Nothing
   else writes it and no screen edits it, so the look chosen at setup cannot
   be changed afterwards except by hand.
2. Which look was chosen is not recorded: `setup` passes it to `starter.fill`
   and keeps nothing, so a later screen cannot tell what the stylesheet was
   made from.
3. The style code is not carried in `content/` (`builder._Build.content`
   copies nothing under `look/`) and `undo._read` has no branch for it, so an
   undo cannot bring an earlier look back. PRESS-0126 § 9 left both to this
   item.
4. The user asked (2026-10-15) for CSS-only interactivity beside PRESS-0217's
   script pieces: effects a visitor's browser runs without any script.

## 3. Scope decisions (agreed with the user)

1. **Choices plus an extra-CSS box**, as WordPress offers. The user,
   2026-10-15, from three outcomes offered (choices only, choices plus CSS,
   the stylesheet itself).
2. **CSS-only effects belong here**: pictures that lift on hover, sections
   that fade in as they scroll into view, smooth scrolling. The user,
   2026-10-15. A page's own CSS is PRESS-0273.
3. **An imported site is out of scope.** It has no style code; its pages link
   `builder.STYLESHEETS`, which live only in the published repository, and
   each imported fixed page carries those links in its own HTML. The panel
   says so and changes nothing (§ 4.5); switching such a site is PRESS-0276.
   The user, 2026-10-15.
4. **A hard-to-read colour is warned about and still saved.** The bar is WCAG
   AA, 4.5:1, for each text pair. The user, 2026-10-15.
5. **(decided here) The choices are a file of their own, and the stylesheet
   is generated from them.** `look/choices.json` holds the choices,
   `look/extra.css` the user's CSS, and `look/style.css` stays the one file
   the Builder publishes and every page links, so the Builder, the preview
   and every page's `<link>` are unchanged.
6. **(decided here) The three starter looks become the three layouts.**
   Sunrise, Meadow and Harbour each keep their arrangement of header, menu
   and page; everything else about them becomes a choice whose default is
   what the look sets today. `starter.fill` writes a look by saving its
   defaults (§ 4.6).
7. **(decided here) Fonts are the visitor's own.** The Face serves the
   preview under `face.FILES_POLICY`, whose `font-src 'self'` refuses an
   outside font, and Pressless loads nothing from elsewhere; each font
   choice is a named stack of fonts found on most computers.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The choices file

`look/choices.json` in the Store, written whole and atomically as
`store.write_identity` writes its file:

```json
{
  "version": 1,
  "layout": "sunrise",
  "colours": {
    "light": {"paper": "#fffaf2", "ink": "#2b1d14", "...": "..."},
    "dark":  {"paper": "#1a1410", "ink": "#f5e9dc", "...": "..."}
  },
  "body_font": "system",
  "heading_font": "serif",
  "text_size": "large",
  "width": "medium",
  "effects": ["lift", "smooth"]
}
```

| Field | Values |
|---|---|
| `layout` | one of `starter.LOOKS`: `sunrise`, `meadow`, `harbour` |
| `colours.light`, `colours.dark` | exactly the names in `starter.COLOURS`, each a `#rrggbb` value |
| `body_font`, `heading_font` | `system`, `serif`, `humanist`, `mono` |
| `text_size` | `normal`, `large`, `larger`; every layout's default is `large`, today's `118.75%` |
| `width` | `narrow`, `medium`, `wide`; `medium`, the default, is the layout's own width |
| `effects` | any of `lift`, `reveal`, `smooth`, each at most once |

A file that fails any row, or whose `version` is not 1, is unreadable:
`look.read` raises `look.LookUnreadable` and nothing is written over it
(§ 6). Keys outside the table are refused the same way, so a later version's
file is never half-read.

`look/extra.css` holds the user's CSS as typed, UTF-8, and may be absent
(read as empty). Pressless never parses it.

`store` gains `LOOK_CHOICES_NAME = "choices.json"` and
`EXTRA_CSS_NAME = "extra.css"` beside `STYLE_CODE_NAME`, and one path
function, `look_path_for(folder, name)`, for all three.
`read_look_file` and `write_look_file` read and write any of them;
`read_style_code` and `write_style_code` stay as their style-code cases.
`LOOK_FOLDER` joins `_BINNABLE`, because a save over an unmanaged
stylesheet (§ 4.4) and an undo (§ 4.7) each bin the version they replace.
`copy_to_bin` is `move_to_bin` that leaves the file in place, so § 4.4's
state 2 keeps `style.css` present while it is replaced.

### 4.2 The generator: `look.py`

A new module owning the choices and the stylesheet made from them. It takes
over `starter.COLOURS`, `starter._PALETTES`, `starter.palette`,
`starter._LOOK_RULES` and `starter._JOURNAL_RULES`, so `starter` imports
`look` and never the reverse. It imports nothing from the Face.

```python
FONTS: dict[str, str]          # key -> CSS font-family stack
TEXT_SIZES: dict[str, str]     # key -> html font-size
WIDTHS: dict[str, str]         # narrow, wide -> the main column's max-width;
                               # medium is the layout's own width
EFFECTS = ("lift", "reveal", "smooth")
TEXT_PAIRS: tuple[tuple[str, str], ...]   # (text colour, its background)

@dataclass(frozen=True)
class Choices: ...             # the fields of § 4.1

def defaults(layout: str) -> Choices       # what the starter look sets today
def read(folder: Path) -> Choices | None   # None where choices.json is absent
def css(choices: Choices, extra: str) -> str
def save(folder: Path, choices: Choices, extra: str) -> None
def warnings(choices: Choices) -> list[tuple[str, str, str, float]]
    # (scheme, text, background, ratio) for each TEXT_PAIRS pair under 4.5
def digest(folder: Path) -> str
    # SHA-256 over choices.json, extra.css and style.css in that order,
    # an absent file counting as a fixed marker
class LookUnreadable(store.StoreError): ...
```

`TEXT_PAIRS` is PRESS-0248's list, the same for every layout: `ink`,
`soft`, `link` and `heading` on `paper`; `on-band` and `band-soft` on
`band`; `on-foot` and `foot-link` on `foot`. Every layout paints its footer
with `foot` (item 4 of the layout rules below), so each pair is a background that is really
painted.

`css` returns, in this order: the palette (the light set on `:root` and the
dark set under `prefers-color-scheme: dark`, as `starter._palette_code` does
today, now from the choices), a `:root` block declaring `--body-font`,
`--heading-font`, `--text-size` and `--width`, the layout's rules, the
journal rules (`starter._JOURNAL_RULES`), the effects chosen (§ 4.3), and
last `extra` after a comment naming it. Effects use the palette's
names, never a colour of their own: `lift`'s shadow is
`color-mix(in srgb, var(--ink) 25%, transparent)`.

The layout rules are today's `starter._LOOK_RULES` with four changes:

1. The body's font family is `var(--body-font)`, and every layout's
   headings and `.site-name` take `var(--heading-font)`. The defaults are
   `serif` headings for Sunrise, which sets Georgia today, and `system` for
   Meadow and Harbour, whose headings inherit the body's family today.
2. The `html` font size is `var(--text-size)`.
3. The main column's `max-width` is `var(--width)`, and the header's and
   footer's side padding, which today aligns their text with that column
   (`calc((100% - 44rem) / 2)` in Sunrise, `43.5rem` in Harbour), is
   `calc((100% - var(--width) + 2.5rem) / 2)` inside the same `max()`.
4. Meadow's footer paints `background: var(--foot)`, whose default equals
   `paper` in both schemes, so the panel's `foot` colour does something and
   every footer pair is checked against what is painted.

So a look's defaults reproduce today's computed style (INV-1). `starter._style_code` is withdrawn; its one caller,
`starter.fill`, saves defaults instead (§ 4.6).

`save` writes `choices.json`, then `extra.css`, then `style.css` from
`css(choices, extra)`, each atomically. The stylesheet is written last, so
the one file the Builder publishes is never newer than the choices it was
made from.

### 4.3 The effects

Each effect is CSS alone, and each sits inside
`@media (prefers-reduced-motion: no-preference)`, so a visitor who asked
their computer for less motion gets none:

- `lift` — a picture in the page lifts slightly, with a soft shadow, under
  the pointer.
- `reveal` — each top-level section of the page fades and rises into place
  as it scrolls into view, through `animation-timeline: view()`, inside
  `@supports (animation-timeline: view())`. A browser without scroll-driven
  animations shows every section at once, as today.
- `smooth` — `html { scroll-behavior: smooth; }`, so an in-page link (the
  back-to-top piece, PRESS-0217) glides rather than jumps.

None hides content before it animates in a browser that lacks the feature.

### 4.4 The Look screen

`look_screen.py`, registered in `__main__` with the other screens, adds
`GET /look`, `POST /look/preview` and `POST /look/save`, and the Face's bar
gains a "Look" link beside Settings (`face._page`).

`GET /look` shows one of three states:

1. **The site has `choices.json`** — the panel, filled from `look.read`.
2. **The site has style code that its choices did not make** — no
   `choices.json` (a site filled before this item), or a `style.css` that is
   not `look.css` of the choices and extra CSS beside it (edited by hand).
   The words inside the notes `look.css` writes as CSS comments are not
   compared (`look.made_here`): they come from the words table, and
   rewording one must not turn a saved look into a hand-edited one.
   The panel opens on the choices where they are readable, else on a layout
   picker (default `sunrise`) showing `look.defaults` of the layout picked.
   It says above Save that the current stylesheet will be replaced and a
   copy kept in the bin. Save writes that copy into the bin first, leaving
   `look/style.css` in place, then calls `look.save`, which replaces it
   last.
3. **The site has no style code** — the imported case (§ 4.5).

The panel: the layout; for each colour name a colour input in a light and a
dark column; the two fonts; text size; width; a checkbox per effect; and a
code box for the extra CSS. Beside them, a frame shows the homepage as the
preview builds it — the same `sandbox="allow-same-origin"` frame without
`allow-scripts` that `page_editor` shows.

**Live preview.** Every change posts the form to `/look/preview`, which
answers `{"css": look.css(...), "warnings": look.warnings(...)}` without
writing anything. The screen's script, scripting into the frame's document
as `page_editor`'s `pair()` already does, disables each `<link>` whose
address ends `look/style.css` and puts the answer in a
`<style id="pressless-look-draft">`. Each warning is shown beside its colour
in words, naming the pair, the scheme and the ratio against 4.5:1.

**Save** posts to `/look/save` with the `look.digest` the screen was drawn
from. Under `editor.LOCK`, a digest that no longer matches raises
`editor.ChangedElsewhere` and writes nothing, as `templates._save` does;
otherwise `look.save` runs and the screen says the look reaches the website
at the next publish. Warnings never stop a save (§ 3 decision 4).

**The Look screen links none of the site's stylesheets into its own
document.** The site's CSS reaches only the frame, so no extra CSS, however
broken, can hide or restyle the controls that would fix it. The entry and
page editors link `builder.stylesheets` into the Face page itself; this
screen deliberately does not.

### 4.5 A site with no style code

`GET /look` says the site's look comes from its own stylesheets, which
Pressless does not change, and shows no panel. `/look/preview` and
`/look/save` answer 409 and write nothing. PRESS-0276 is where this changes.

### 4.6 The starter site

`starter.fill(folder, site_name, look)` calls
`look.save(folder, look.defaults(look), "")` where it wrote
`_style_code(look)` before, under the same "only where `look/style.css` is
absent" rule. A new site therefore starts with `choices.json`, and setup's
look choice is recorded.

### 4.7 Undo and `content/`

`_Build.content` copies each of `look/choices.json`, `look/extra.css` and
`look/style.css` that exists, as it copies `identity.json`
(PRESS-0213 § 4.4).

`undo._read` gains a branch for the `look` folder collecting those three
files. Reconciling treats them as one unit:

- **The fetched state carries any of the three** — each Store file that
  differs from its fetched version, or that the fetched state lacks, goes to
  the bin, and the fetched versions are written; each step records its
  reversal as the identity steps do.
- **The fetched `choices.json` fails `look.read`** — the Store's look is
  kept, nothing under `look/` is written, and the undo's report says so.
- **The fetched state carries none** — a publish from before this item — and
  the Store's look is kept, as PRESS-0213 keeps an identity the fetched state
  lacks.

## 5. Invariants

- **INV-1** — For each layout, `look.css(look.defaults(layout), "")` styles a
  page exactly as `starter._style_code(layout)` did before this item, in
  light and in dark.
  *Test:* by hand, before `starter._style_code` is withdrawn: render the probe
  page of each layout in Chrome under both colour schemes from the old and
  the new stylesheet and compare every element's computed colour, background,
  borders, font family, font size and the main column's width.
  The one expected difference is Meadow's footer background, now `foot`
  where it was transparent over the same `paper`.
  *Breaks when:* a value lifted into a custom property is given a different
  default, or a rule is dropped in the move.

- **INV-2** — Every text pair in every layout's defaults reaches 7:1 in
  light and in dark (PRESS-0248's floor, unchanged by this item).
  *Test:* `tests/test_starter.py::test_every_look_reads_at_seven_to_one_in_light_and_dark`,
  re-pointed at `look.defaults`.
  *Breaks when:* a default colour is changed below the floor.

- **INV-3** — `look.read` returns exactly what `look.save` wrote, and refuses
  every file § 4.1's table rejects, writing nothing.
  *Test:* `tests/test_look.py` round-trips `defaults` for each layout and a
  changed copy; one case per table row writes a file breaking only that row
  (an unknown colour name, a colour not `#rrggbb`, an unknown font, an
  effect named twice, `version` 2, an extra key) and expects
  `LookUnreadable`.
  *Breaks when:* a field is read with a fallback instead of refused.

- **INV-4** — `look.css` puts the extra CSS last, verbatim, and every effect
  inside `prefers-reduced-motion: no-preference`; `reveal` also inside
  `@supports (animation-timeline: view())`.
  *Test:* `tests/test_look.py` asserts `css(c, extra).endswith(extra)` for an
  extra holding `}` and `</style>`, and parses each effect's rules out of
  `css` with every effect on to check its enclosing at-rules.
  *Breaks when:* an effect's rule is emitted outside its media query, or the
  extra CSS is placed before the layout.

- **INV-5** — `look.save` leaves `style.css` equal to
  `look.css(read(folder), extra)`.
  *Test:* `tests/test_look.py` saves, then reads the three files back and
  compares.
  *Breaks when:* `style.css` is written from different choices than
  `choices.json` holds.

- **INV-6** — A text pair under 4.5:1 appears in `/look/preview`'s
  `warnings` and on the screen, and `/look/save` still saves it.
  *Test:* `tests/test_look_screen.py` posts `ink` equal to `paper` and
  expects that pair in both schemes' warnings, then saves and reads it back.
  *Breaks when:* the warning list omits a pair or the save refuses.

- **INV-7** — Saving over a style code its choices did not make keeps a
  copy of the old `style.css` in the bin, and `style.css` is never absent
  during the save.
  *Test:* `tests/test_look_screen.py` writes a hand-made `style.css`, saves a
  layout and finds the hand-made text in the bin.
  *Breaks when:* the old stylesheet is overwritten without a copy, or
  moved away before the new one is written.

- **INV-8** — A save whose `look.digest` no longer matches writes nothing
  and reports the change made elsewhere, whichever of the three files
  changed.
  *Test:* `tests/test_look_screen.py` changes only `extra.css` after drawing
  the screen, saves with the old digest, and finds all three files
  unchanged.
  *Breaks when:* the save skips the digest check.

- **INV-9** — On a site with no style code, `/look` shows no panel and both
  POST routes answer 409, writing nothing.
  *Test:* `tests/test_look_screen.py` against a Store with no `look/` folder.
  *Breaks when:* a save creates style code on an imported site.

- **INV-10** — The Look screen's own document links no stylesheet from the
  site; the site's CSS reaches only the frame.
  *Test:* `tests/test_look_screen.py` reads `GET /look` and finds no `<link>`
  to `/preview/look/` or `/preview/assets/` outside the frame's `src`.
  *Breaks when:* the screen links `builder.stylesheets` as the editors do.

- **INV-11** — `content/` carries the look files that exist, and undo
  restores them as one unit; a fetched state without any keeps the Store's.
  *Test:* `tests/test_builder.py` builds a site with all three and finds them
  under `content/look/`; `tests/test_undo.py` undoes to a state with an
  earlier look, to one with none, and to one whose `choices.json` is
  unreadable.
  *Breaks when:* `content` omits a file, or undo restores `choices.json`
  without its `style.css`.

- **INV-12** — `starter.fill` writes `choices.json` equal to
  `look.defaults(look)` and `style.css` equal to its `css`.
  *Test:* `tests/test_starter.py` fills each layout and compares.
  *Breaks when:* fill writes a stylesheet with no choices behind it.

## 6. Failure modes

- **`choices.json` unreadable** (hand-edited, or from a newer Pressless) —
  `GET /look` says the look's settings cannot be read and shows no panel;
  nothing is written, and the published stylesheet is untouched.
- **A save interrupted between files** — `style.css` is written last and
  never moved away first (§ 4.4 state 2), so the published stylesheet is the
  previous one, intact. The panel then shows the
  newer choices; the next save writes a matching stylesheet.
- **Extra CSS that breaks the site's look** — it reaches only the frame and
  the published site, never the Look screen itself (INV-10), so it can be
  fixed there; undo also brings back the earlier look once published.
- **A browser without scroll-driven animations** — `reveal` does nothing and
  every section shows at once (§ 4.3).
- **A font missing on the visitor's computer** — each stack falls through to
  the next family and ends in a generic one.

## 7. Tests

New `tests/test_look.py` (INV-3, INV-4, INV-5) and `tests/test_look_screen.py`
(INV-6, INV-7, INV-8, INV-9, INV-10); `tests/test_starter.py` gains INV-12, keeps INV-2
re-pointed, and re-points PRESS-0248's
`test_each_look_turns_dark_with_the_computer_and_names_no_other_colour` at
`look.css(look.defaults(layout), "")`: it finds the light and dark sets by
their selectors rather than by position, allows the four non-colour
properties of § 4.2 beside `COLOURS`, and still refuses a raw colour in the
rules; `tests/test_builder.py` and `tests/test_undo.py` gain INV-11.
INV-1 is the by-hand Chrome comparison, run once before `_style_code` is
withdrawn, with its result recorded in the commit body. Each test is seen to
fail before the code it locks exists.

## 8. Alternatives considered (and rejected)

- **The Builder generates the stylesheet from the choices at each build.**
  Rejected: the preview, the editors and every page already read
  `look/style.css` from the Store, and the hand-written style code of
  state 2 has no choices to generate from.
- **Edit the stylesheet text itself.** Offered to the user and not chosen;
  the extra-CSS box covers someone who knows CSS.
- **Web fonts.** Refused by the preview's `font-src 'self'`, and a font
  service is an outside call on every visit.
- **Refuse hard-to-read colours.** Offered and not chosen (§ 3 decision 4).

## 9. Out of scope

- An imported site's look — tracked by PRESS-0276.
- A page's own CSS — tracked by PRESS-0273.
- More layouts than the three starter arrangements — deferred; not yet
  queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | **by hand** — the Chrome comparison in § 5, once, at the move |
| INV-2 | `tests/test_starter.py::test_every_look_reads_at_seven_to_one_in_light_and_dark` |
| INV-3 | `tests/test_look.py` |
| INV-4 | `tests/test_look.py` |
| INV-5 | `tests/test_look.py` |
| INV-6 | `tests/test_look_screen.py` |
| INV-7 | `tests/test_look_screen.py` |
| INV-8 | `tests/test_look_screen.py` |
| INV-9 | `tests/test_look_screen.py` |
| INV-10 | `tests/test_look_screen.py` |
| INV-11 | `tests/test_builder.py`, `tests/test_undo.py` |
| INV-12 | `tests/test_starter.py` |

## 11. Cross-doc impact

- PRESS-0126 § 9: its deferral of the look's editing and undo now points
  here.
- PRESS-0008 § 4.7 and PRESS-0015 § 4.4: a pointer to § 4.7 for the look
  files `content/` carries and undo restores.
- PRESS-0005 § 4.1: a pointer to § 4.1 for `LOOK_FOLDER` joining
  `_BINNABLE`.
- `CHANGELOG.md`: an Added entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0196-site-look-loop-log.md`.

## 13. Migration / compatibility

A site filled before this item has `look/style.css` and no `choices.json`:
state 2 of § 4.4 handles it, keeping a copy of the old stylesheet in the bin
on the first save. A site with neither is state 3. Older published states carry no look files in
`content/`, and undo keeps the Store's look for them (§ 4.7).
