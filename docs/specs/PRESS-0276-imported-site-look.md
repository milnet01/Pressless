<!-- ants-spec-format: 1 -->
# PRESS-0276 — A site with its own stylesheets: CSS on top, or a Pressless look

**Status:** accepted (2026-11-08). No review gate: nothing outside Pressless binds to it, it adds no new kind of file, and the screen undoes a switch.
**Kind:** feature.
**Source:** ROADMAP PRESS-0276 (split from PRESS-0196 by the user's
2026-10-15 choice).

**Builds on:** PRESS-0196 (the Look screen and its three look files),
PRESS-0126 § 4.6 (`builder.stylesheets`). **Changes:** PRESS-0196 § 4.5 and
INV-9, PRESS-0126 § 4.6's "a fixed page is unchanged", PRESS-0008 INV-8.

Layman: a site that brought its own stylesheets with it can now use the Look
screen. They either keep those stylesheets and add their own CSS on top, or
switch to one of Pressless's designs. They can switch back the same way.

## 1. Goal

On a site whose look is its own stylesheets, the Look screen offers two
routes: keep those stylesheets and add CSS after them, or take a Pressless
look. Either shows in the preview first, reaches every page at the next
publish, and can be reversed from the same screen. A site that saves nothing
builds exactly as it does today.

## 2. Problem

1. `look_screen._open` shows only a notice where the Store has no style code
   (PRESS-0196 § 4.5), and both POST routes refuse.
2. Such a site's pages link `builder.STYLESHEETS`, which live only in the
   published repository. Generated pages get them from `builder.stylesheets`.
   Each fixed page carries them in its own HTML, written by the import, and
   PRESS-0126 § 4.6 publishes a fixed page's links byte for byte, so nothing
   the Store holds can change what a fixed page links.
3. Which sites this is: the WordPress import (`_bring.bring_in`) saves a
   Pressless look, and the folder import writes style code (PRESS-0210
   § 4.7), so both reach PRESS-0196's states 1 and 2. A site with no style
   code comes from the maintainer's import (PRESS-0007), or from a take-in of
   a site published before PRESS-0196 (PRESS-0218).

## 3. Scope decisions (agreed with the user)

1. **Both routes, as the roadmap item names them.** The user, 2026-10-15.
2. **(decided here) The Builder rewrites a fixed page's links to the site's
   stylesheets as it builds; the Store's pages are never rewritten.** So a
   switch writes only look files, the way back is one file to the bin, and a
   page added in either state follows the site's current look. The cost: a
   fixed page's code view still shows the links it was written with.
3. **(decided here) The CSS on top is published as its own file,
   `look/extra.css`,** linked after the site's own stylesheets. It is the
   Store's `look/extra.css`, which PRESS-0196 § 4.1 already defines.
4. **(decided here) Going back keeps the choices.** Taking the own-stylesheets
   route on a switched site moves `look/style.css` to the bin and leaves
   `choices.json`, so switching again starts from the last look chosen.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 Which stylesheets a page links

`builder` gains:

```python
EXTRA_CSS = "look/extra.css"     # where the CSS on top is published
SITE_SHEETS = (*STYLESHEETS, STYLE_CODE, EXTRA_CSS)   # links the Builder may rewrite

def stylesheets(folder: Path) -> tuple[str, ...]
    # (STYLE_CODE,) where the Store has style code;
    # else STYLESHEETS + (EXTRA_CSS,) where look/extra.css holds anything
    #   but white space;
    # else STYLESHEETS, as today.
def own_stylesheets(folder: Path) -> bool
    # whether any page in pages/, published or waiting, links an entry
    # of STYLESHEETS
```

**A site-sheet link** is a `<link>` whose `rel` includes `stylesheet` and whose
`href`, without any leading `../` and `{{UP}}`, equals an entry of
`SITE_SHEETS`. A link with a query or a fragment is not one.

### 4.2 The fixed page at build

`_Build.fixed_page` passes the page's text through one new step before
filling its furniture. That step is the same for a preview and a publish.
**A page whose site-sheet links, in order, are `stylesheets(folder)` is left
as it is, byte for byte.** Any other page with site-sheet links has its first
one replaced by one `<link rel="stylesheet" href="…">` per entry of
`stylesheets(folder)`, prefixed `../` once per depth, joined by a newline.
Every later site-sheet link is removed, with the line it stood alone on. A
page with no site-sheet links is left alone, and so is every other byte.

So a site that has saved nothing builds as before (INV-1).

`build` writes `EXTRA_CSS` from the Store's file wherever `stylesheets`
includes it, and copies what that file names into the site, as it does
for the style code (`copy_what_is_named`). `_held_files` reads it, as it
reads the style code. `content()` already carries `look/extra.css`
(PRESS-0196 § 4.7).

### 4.3 The Look screen

`GET /look` now shows a **route choice**, two radio buttons named `route`,
where the Store has no style code or `builder.own_stylesheets(folder)`:

- `own` — "Keep its own stylesheets, and add CSS on top". Below it: the
  extra-CSS box alone.
- `pressless` — "Use a Pressless design". Below it: PRESS-0196's panel,
  extra-CSS box included.

The choice sits above everything it changes. It opens on `own` where there
is no style code, else on `pressless`. The Pressless panel opens on
`look.read`'s choices where readable, else on the layout picker's defaults
(PRESS-0196 § 4.4 state 2). The extra-CSS box opens on `look.read_extra`.
Where neither condition holds, as on a starter site, the screen is PRESS-0196's,
unchanged.

**Live preview.** `/look/preview` posts `route` too. Route `own` answers
`{"css": extra, "warnings": [], "sheets": [ASSETS_ADDRESS + "site.css",
ASSETS_ADDRESS + "blog.css"]}`. Route `pressless` answers PRESS-0196's
reply with `"sheets": []`. In the frame, the screen's script disables every
`<link>` whose address ends in an entry of `builder.SITE_SHEETS`, adds a
`<link>` per address in `sheets`, then the draft `<style>`. So each route
previews correctly whichever state the Store is in.

**Save** keeps PRESS-0196's digest check under `editor.LOCK`, for both
routes.

- Route `own` writes `look/extra.css` as typed. Where `style.css` exists, it
  then moves it to the bin (`store.move_to_bin`), whether or not its
  choices made it, and leaves `choices.json`.
- Route `pressless` is PRESS-0196's save. With no style code there is
  nothing to bin, and the next build links `look/style.css` on every page
  (§ 4.2).

A post naming neither route, or `own` where neither condition holds, is
refused (`LookRefused`) and writes nothing.

### 4.4 Undo

Unchanged: PRESS-0196 § 4.7 restores the three files as one unit. An undo to
a publish from before a switch carries no look files and so keeps the
Store's look. The route choice is the way back to the site's own
stylesheets.

## 5. Invariants

- **INV-1** — A Store with no look files builds every page as it did before
  this item.
  *Test:* `tests/test_builder.py` builds a site whose fixed pages link
  `assets/site.css` and `../assets/site.css` and `../assets/blog.css`, with
  no `look/` folder, and finds each fixed page equal to its
  `_fill_fixed_page` output and no `look/` in the build. The archive tests
  build the writer's site the same way.
  *Breaks when:* the rewrite runs on a page whose links already match.

- **INV-2** — At every depth, a fixed page's site-sheet links become
  `stylesheets(folder)`. Every other byte stays, and the Store's page is
  unchanged.
  *Test:* `tests/test_builder.py`, with style code present: a page at depth 0
  and one at depth 1, each linking both of `STYLESHEETS` and a stylesheet of
  its own, build to one `look/style.css` link at the right depth and keep
  their own link. A page linking `look/style.css` with no style code builds
  to the `STYLESHEETS` pair. A link with `?v=` is kept. Each Store file is
  byte-equal to before.
  *Breaks when:* the depth prefix is wrong, a later site-sheet link survives,
  or the rewrite writes back to the Store.

- **INV-3** — With no style code, `look/extra.css` holding text is linked
  after `STYLESHEETS` on every page, generated and fixed, and published
  equal to the Store's file. White space alone is neither linked nor
  published.
  *Test:* `tests/test_builder.py` builds with `extra.css` holding a rule,
  then holding only a newline.
  *Breaks when:* `stylesheets` ignores `extra.css`, or the build forgets to
  write it.

- **INV-4** — Saving route `own` on a site with no style code writes only
  `extra.css`. On a switched site it also moves `style.css` to the bin and
  keeps `choices.json`.
  *Test:* `tests/test_look_screen.py` saves `own` on each, then compares
  the look folder and finds the old `style.css` in the bin.
  *Breaks when:* `choices.json` is binned, or `style.css` is overwritten
  rather than moved.

- **INV-5** — Saving route `pressless` on a site with no style code writes
  the three files `look.save` writes, bins nothing, and the next preview
  build links `look/style.css` from every fixed page.
  *Test:* `tests/test_look_screen.py`.
  *Breaks when:* the save is refused as in PRESS-0196 INV-9.

- **INV-6** — A save on either route with a stale digest writes nothing.
  *Test:* `tests/test_look_screen.py` changes `extra.css` after drawing the
  screen and saves each route with the old digest.
  *Breaks when:* the own route skips the digest check.

- **INV-7** — `/look/preview` with route `own` answers the extra CSS, no
  warnings and the two assets addresses, and writes nothing.
  *Test:* `tests/test_look_screen.py` compares the reply and the look
  folder's digest before and after.
  *Breaks when:* the reply sends the Pressless stylesheet for route `own`.

- **INV-8** — Where the Store has style code and no page links
  `STYLESHEETS`, the screen offers no route choice and a post with route
  `own` is refused.
  *Test:* `tests/test_look_screen.py` on a starter-filled Store finds no
  `type="radio" name="route"` and posts `own` to both routes.
  *Breaks when:* the choice is shown on a starter site.

## 6. Failure modes

- **Extra CSS that breaks the site** — it never reaches the Look screen
  itself (PRESS-0196 INV-10), so it can be fixed there.
- **A Pressless design that suits the imported pages badly** — the preview
  shows it before Save. The own route puts the old stylesheets back, and the
  bin keeps the replaced `style.css`.
- **No preview copy of the assets** (a taken-in site has no
  `paths.PREVIEW_ASSETS`) — the own route's preview shows the page unstyled
  but for the extra CSS. The published site is unaffected.
- **A save interrupted on route `own`** — `extra.css` is written before
  `style.css` moves, so the site keeps whichever look it had, whole.

## 7. Tests

`tests/test_builder.py` gains INV-1, INV-2 and INV-3. `tests/test_look_screen.py`
gains INV-4, INV-5, INV-6, INV-7 and INV-8, and its PRESS-0196 INV-9 test
is retired, INV-5 taking its place. Each test is seen to fail before the code it locks exists. A by-hand browser check in Chrome
switches a site whose pages link its own stylesheets both ways, and adds CSS
on top.

## 8. Alternatives considered (and rejected)

- **Rewrite each fixed page's links in the Store.** Every switch would rewrite
  every page, each needing its own undo step and bin copy. The way back would
  be the same rewrite again.
- **Put the CSS on top inside `look/style.css`.** That file existing is what
  means "a Pressless look" to `stylesheets`, `look_screen` and PRESS-0196's
  states, so this would need a fourth state.
- **Insert the extra link before `</head>` as `identified` inserts the icon.**
  That covers fixed pages only. The switch still needs the rewrite, so one
  rule does both.

## 9. Out of scope

- Editing the site's own stylesheets — they stay in the published repository.
- A preview copy of the assets for a taken-in site — not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_builder.py`, and the archive tests |
| INV-2 | `tests/test_builder.py` |
| INV-3 | `tests/test_builder.py` |
| INV-4 | `tests/test_look_screen.py` |
| INV-5 | `tests/test_look_screen.py` |
| INV-6 | `tests/test_look_screen.py` |
| INV-7 | `tests/test_look_screen.py` |
| INV-8 | `tests/test_look_screen.py` |

## 11. Cross-doc impact

- PRESS-0196 § 4.5 and INV-9: withdrawn; pointer here.
- PRESS-0126 § 4.6: `stylesheets` gains the extra-CSS case, and a fixed
  page's site-sheet links are rewritten; pointer here.
- PRESS-0008 INV-8: a fixed page's site-sheet links are the one other change
  outside its markers; pointer here.
- `CHANGELOG.md`: an Added entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0276-imported-site-look-loop-log.md`.

## 13. Migration / compatibility

Nothing is migrated. A site with no look files builds unchanged (INV-1). A
site with style code and pages linking `STYLESHEETS` (not one Pressless
makes today) gains the route choice, and at its next build its fixed pages
link the style code.
