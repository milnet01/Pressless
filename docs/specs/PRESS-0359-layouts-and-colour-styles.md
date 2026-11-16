<!-- ants-spec-format: 1 -->
# PRESS-0359 — Eight layouts and eleven colour styles on the Look screen

**Status:** spec draft (2026-11-16).
**Kind:** feature.
**Source:** ROADMAP PRESS-0359 (user request 2026-11-13).
**Pairs with:** PRESS-0196, whose § 4.1 table and § 9 this item changes.

Layman: the Look screen offers eight page layouts, one for each common kind
of site, and eleven sets of colours any of them can wear, each shown as a
small drawing with the kind of site written under it.

## 1. Goal

After this ships, a site can take one of eight layouts and wear any of
eleven colour styles. The Look screen shows each as a grid of small
drawings, with the kind of site under each one. Choosing a colour style
fills the colour boxes, and the site's saved look keeps the colours
themselves, as it does now.

## 2. Problem

1. `look.LAYOUTS` holds three layouts, so most Pressless sites look alike.
2. Each layout's colours live inside it: `look._PALETTES` is keyed by layout,
   and `look.palette(layout, dark)` reads it. A site cannot take Meadow's
   shape in Harbour's colours without setting every colour box by hand.
3. The drawings in `setup.look_choices` take their colours from hex values
   copied into `face`'s `.mini-sunrise`, `.mini-meadow` and `.mini-harbour`
   rules. Nothing ties those copies to `look._PALETTES`.

## 3. Scope decisions (agreed with the user)

The user chose the first four on 2026-11-15, on the session's
recommendation.

1. **Layouts and colour styles are separate choices.** A layout is the
   shape of a page. A colour style is a set of colours any layout can wear.
2. **Five new layouts, one per common kind of site**: portfolio, small
   business, musician or band, club or community, plain document.
3. **Eight new colour styles.** With the three layouts' own colours, that
   makes eleven.
4. **Both are shown as a grid of small drawings**, as the layouts are shown
   now, with the kind of site under each drawing.
5. **(decided here) A layout stays CSS alone.** Every layout styles the
   HTML the Builder already writes, so switching layout changes one file,
   `look/style.css`, and never a page.
6. **(decided here) A colour style is not saved.** Choosing one fills the
   colour boxes, as PRESS-0352's "Use this layout's own colours" button
   does, and `choices.json` keeps the colours. The only change to the
   saved look is five new `layout` values.
7. **(decided here) Each layout wears one of the eleven styles by
   default.** The three old layouts keep their own colours, each now a
   style of the same name. The new layouts take a style from the eleven
   rather than adding colour sets of their own.
8. **(decided here) Setup and WordPress import offer the eight layouts,
   each in its own colours.** Colour styles appear only on the Look screen,
   so first run stays one choice.
9. **(decided here) The layout and colour-style names are the session's.**
   The shown words live in `words.py` and can change at any time. The
   layout keys in § 4.1 are saved in sites' files, so they are fixed.

## 4. Design

### 4.1 Layouts

`look.LAYOUTS` becomes, in this order:

```python
LAYOUTS = ("sunrise", "meadow", "harbour", "studio", "market", "stage",
           "commons", "letter")
```

`sunrise` stays first, so it stays the default wherever
`LAYOUTS[0]` or `starter.LOOKS[0]` is used.

| Key | Kind of site | Shape | Own style |
|---|---|---|---|
| `sunrise` | a personal site or journal | as now | `sunrise` |
| `meadow` | writing, such as poems or stories | as now | `meadow` |
| `harbour` | news or a newsletter | as now | `harbour` |
| `studio` | a portfolio | no band; the name left and the menu right on one line above a thin rule; a wide column | `ink` |
| `market` | a small business | a tall band with the name and the menu centred; the page as a raised card on the paper | `slate` |
| `stage` | a musician or band | a tall band with a large name; the menu as a row of boxed links | `night` |
| `commons` | a club or community | the name in a band, the menu in a strip of its own beneath it | `sky` |
| `letter` | a plain document | no band; one narrow centred column, the name as a plain heading | `ink` |

The shapes give the implementer direction; the CSS is settled while
writing it. Each new layout has an entry in `_LAYOUT_RULES`, `_OWN_WIDTH`
and `_HEADING_FONT`. Its rules name colours only through the custom
properties of `look.COLOURS`, as the three do now.

### 4.2 Colour styles

`look` gains:

```python
STYLES = ("sunrise", "meadow", "harbour", "ink", "slate", "plum", "sand",
          "coral", "teal", "night", "sky")
OWN_STYLE: dict[str, str]          # layout -> its default style, per § 4.1
def palette(style: str, dark: bool) -> dict[str, str]: ...
```

`_PALETTES` is keyed by style. The three old entries keep their values
exactly (INV-4). `palette` keeps its name and argument order, so its
callers, which pass an old layout key, still work. `defaults(layout)` takes
its colours from `palette(OWN_STYLE[layout], ...)`.

| Style | Colours | Kind of site under the drawing |
|---|---|---|
| `ink` | black on white, the strongest contrast | any site, easiest to read |
| `slate` | greys with a blue band | a business or a service |
| `plum` | deep purple with a cream page | an artist or a maker |
| `sand` | warm beige and brown | a café, a shop or a craft |
| `coral` | coral band, white page | a family or a children's group |
| `teal` | teal and soft grey | health or wellbeing |
| `night` | dark page, bright text | a band or an evening event |
| `sky` | light blue and navy | a school or a community group |

The three old styles carry the kind of site their layout carries.

Every style is a full set of `look.COLOURS` in light and dark. The hex
values are the implementer's, held to INV-2.

### 4.3 The drawings

A drawing's shape comes from its class, as now. **Its colours come from the
palette**, written onto the drawing as the custom properties `--band`,
`--paper`, `--foot` and `--link`, from the light set. `face`'s
`.mini-<layout>` rules keep the shape and lose their hex values. The
Face's own pages set no `style-src`, and `dashboard.py` already writes
custom properties inline this way.

- A **layout drawing** wears its layout's own style.
- A **colour drawing** is one fixed shape — a band, the page with a line in
  `--link`, and a footer — wearing that style.

Under each drawing: the name in bold, then the kind of site. Each grid cell
keeps one size, so marking a choice moves nothing.

### 4.4 The Look screen

The layout grid replaces `setup.look_choices`' row of three inside the
Look screen's layout fieldset. Setup and WordPress import use the same
function and so show eight.

A **colour styles** fieldset follows the layout fieldset. It holds one
radio per style, named `style`, each carrying its light and dark palettes
as data, as the button of PRESS-0352 carries layouts' palettes.

- **Choosing a style** writes its 26 values into the colour boxes and
  posts the preview, as that button does.
- **The marked style is the one whose 26 values equal the boxes.** The
  server marks it when drawing the screen. The script re-marks it after
  every change to a box. Where no style matches, none is marked.
- **`/look/save` and `/look/preview` ignore `style`.** The colours come
  from the boxes, so nothing new reaches `choices.json`.

PRESS-0352's rule stands: choosing a layout keeps the colours, and its
button fills the boxes with `palette(OWN_STYLE[layout], ...)`.

The overview's Look tile names the layout through `setup.look.<layout>`,
so each new layout gains that key and `setup.look.<layout>.about`, which
now holds the kind of site. Each style gains `look_screen.style.<style>`
and `look_screen.style.<style>.about`.

### 4.5 The saved look

`choices.json` is unchanged except that `layout` may be any of § 4.1's
eight. `version` stays 1. `look.from_json` already refuses a layout not in
`LAYOUTS`, so it reads the new keys with no change of its own.

## 5. Invariants

- **INV-1** — `look.LAYOUTS` is § 4.1's tuple, and a `choices.json` naming
  any of the eight reads back the choices `look.save` wrote.
  *Test:* `tests/test_look.py`, parametrized over `look.LAYOUTS`, saves
  `defaults(layout)` and compares `read`; one more case asserts the tuple.
  *Breaks when:* a layout is added to `LAYOUTS` without its rules, width or
  heading font, so `defaults` or `css` raises; or `from_json` refuses one
  of the eight.

- **INV-2** — Every style's text pairs reach 7:1 in light and dark.
  `look.TEXT_PAIRS` are the same for every layout, so this holds for every
  layout wearing every style.
  *Test:* `tests/test_starter.py::test_every_look_reads_at_seven_to_one_in_light_and_dark`,
  re-pointed at `look.palette` over `look.STYLES`.
  *Breaks when:* one value of one style falls below the floor.

- **INV-3** — Each layout's defaults wear its own style:
  `defaults(l).light == palette(OWN_STYLE[l], False)` and likewise dark,
  and `OWN_STYLE[l]` is in `STYLES`.
  *Test:* `tests/test_look.py`, parametrized over `look.LAYOUTS`.
  *Breaks when:* a layout keeps colours outside the eleven styles.

- **INV-4** — The three old layouts' style code is unchanged:
  `look.css(look.defaults(l), "")` hashes as it did before this item.
  *Test:* `tests/test_look.py` pins the first 16 hex digits of each SHA-256.
  The values today are `sunrise 9c63a298284c833b`,
  `meadow c61d76927741d344` and `harbour 0a0d3877f1e4607b`. Changing
  Sunrise's light `paper` by one digit gave `24a1d0b071802236`.
  *Breaks when:* moving the palettes changes a value or a rule. A reworded
  note inside the CSS also breaks it: the test then needs re-pinning, which
  is deliberate.

- **INV-5** — Changing layout changes no page. Building the starter site
  under any two layouts gives byte-equal HTML for every page.
  *Test:* `tests/test_builder.py` fills one Store per layout and compares
  every built `.html` file. Only `look/` differs.
  *Breaks when:* a layout needs markup of its own, such as a class the
  Builder writes only for it.

- **INV-6** — Choosing a colour style reaches `choices.json` only as colour
  values. A save posted with a `style` field writes the version-1 fields
  and no other key.
  *Test:* `tests/test_look_screen.py` posts a save carrying `style=night`
  and a colour set different from `night`'s, then reads `choices.json`:
  it holds the posted colours and exactly `look._FIELDS`. Answering the
  posted `style` instead would write `night`'s colours, which this tells
  apart.
  *Breaks when:* the save takes colours from the style instead of the
  boxes, or writes the style's name.

- **INV-7** — The screen marks the style whose 26 values equal the saved
  colours, or none.
  *Test:* `tests/test_look_screen.py` saves `defaults("market")` and finds
  `slate` checked and no other; then saves the same with one box changed
  and finds none checked.
  *Breaks when:* the mark compares the light set only, or marks the
  layout's own style regardless of the boxes.

- **INV-8** — Every drawing's colours are its palette's. Each layout
  drawing carries `OWN_STYLE[layout]`'s light `band`, `paper`, `foot` and
  `link` as custom properties, and each colour drawing its own style's.
  No `.mini-` rule in `face` names a hex colour.
  *Test:* `tests/test_setup.py` parses `setup.look_choices` and the Look
  screen's style fieldset and compares each drawing to `look.palette`;
  a regex over `face`'s stylesheet finds no `#` value inside a `.mini-`
  rule.
  *Breaks when:* a drawing keeps a copied hex, and a palette change leaves
  it stale.

- **INV-9** — The grids hold still: choosing a layout or a style moves no
  control on the screen.
  *Test:* by hand in Chrome, per `docs/working-here.md` § Windows and
  browser checks. Note each fieldset's position, choose every cell in turn,
  and compare.
  *Breaks when:* a cell's size depends on its label's length or on being
  marked.

## 6. Failure modes

| What breaks | What happens |
|---|---|
| An older Pressless opens a site saved with a new layout | Its `look.from_json` raises `LookUnreadable`. The Look screen shows that failure and the overview tile shows no layout. The Builder never reads `choices.json`, so the site still builds and publishes from `style.css`. |
| A posted `layout` not in `LAYOUTS` | Refused by `look.problem`, as now. |
| A posted `style` not in `STYLES` | Ignored, as every `style` is (§ 4.4). |
| The script does not run | The boxes, the layout grid and Save still work. Choosing a style fills nothing; the screen already needs its script for the live preview. |
| A style looks wrong on one layout | INV-2 holds the contrast. Taste is caught only by § 7's hand check. |

## 7. Tests

Each test above is seen failing first, against the code before this item
or with its rule deleted:

- INV-1, INV-3, INV-4: `tests/test_look.py`. INV-4 is written and green
  *before* the palettes move, so it proves the move.
- INV-2: the existing test in `tests/test_starter.py`, re-pointed.
- INV-5: `tests/test_builder.py`.
- INV-6, INV-7: `tests/test_look_screen.py`.
- INV-8: `tests/test_setup.py`.
- `tests/test_starter.py::test_each_look_turns_dark_with_the_computer_and_names_no_other_colour`
  is already parametrized over `starter.LOOKS`, so it covers the new
  layouts with no change.

**Hand check, in Chrome on Linux and on the Windows box:** each new
layout at a narrow and a wide window, light and dark, wearing its own
style and two others, on a page holding every block in `blocks.py`. Then
INV-9. Then retake the manual's `look.png`, `setup-welcome.png` and
`changing-the-look.webm` (`docs/working-here.md` § Remaking the manual's
pictures and videos).

## 8. Alternatives considered (and rejected)

- **Save the style's name in `choices.json`.** The colours are saved
  already. A name would be wrong the moment one box changes. And
  `from_json` refuses unknown keys, so every older build would refuse the
  file.
- **Raise `version` to 2.** Every older build would then refuse every
  site, old layouts included, though nothing about reading changes.
- **Layouts that change the page HTML**, such as a gallery grid for a
  portfolio. A switch would then change every page rather than one file,
  and the Builder would need to know each layout.
- **Colour styles in setup.** A second choice on first run, for something
  the Look screen offers one click later.
- **Five more colour sets, one per new layout.** The user's count is
  eleven sets; the new layouts wear styles from among them.

## 9. Out of scope

- Starter pages written for each kind of site, such as a business's
  Contact page — deferred; not yet queued.
- Styling block classes beyond what a layout's shape needs — PRESS-0215
  § 9 defers it; not yet queued.
- Fonts from outside the computer — refused by PRESS-0196 § 3 decision 7.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_look.py` |
| INV-2 | `tests/test_starter.py::test_every_look_reads_at_seven_to_one_in_light_and_dark` |
| INV-3 | `tests/test_look.py` |
| INV-4 | `tests/test_look.py` |
| INV-5 | `tests/test_builder.py` |
| INV-6 | `tests/test_look_screen.py` |
| INV-7 | `tests/test_look_screen.py` |
| INV-8 | `tests/test_setup.py` |
| INV-9 | **by hand** — § 7, in Chrome |
| A layout or style looks good | **nothing** — taste; § 7's hand check |
| The script re-marks the style after a box changes | **nothing** — no browser test runs in the suite; § 7's hand check |

## 11. Cross-doc impact

- PRESS-0196 § 4.1: the `layout` row names `look.LAYOUTS` and points here.
  § 9: the deferral of more layouts points here.
- `src/pressless/manual_files/en.txt`: the Look and setup pages, and the
  three media files § 7 names.
- `CHANGELOG.md`: an Added entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0359-layouts-and-colour-styles-loop-log.md`.

## 13. Migration / compatibility

Nothing to migrate. Every existing `choices.json` names one of the three
old layouts, which keep their keys and colours (INV-4), and
`tests/test_frozen.py::test_a_version_one_look_still_reads_and_writes_back_the_same`
still passes. A newer site opened by an older Pressless is § 6's first row.
