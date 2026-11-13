<!-- ants-spec-format: 1 -->
# PRESS-0353 — Lay the screens out as a website editor

**Status:** accepted (2026-11-13). No review: no contract or hard-to-reverse trigger fires (`CLAUDE.md` rule 14); the user chose the design from drawn alternatives.
**Kind:** ux.
**Source:** ROADMAP PRESS-0353 (user request 2026-11-13).

Layman: Pressless opens on a screen showing each part of your website, and
every part has its own screen, so a newcomer finds each thing without
hunting.

## 1. Goal

After this ships, Pressless opens on **Your site**: a tile for each part of
a website. Pages, the journal and Settings each have a screen of their own,
and the top bar names the parts of a site. Nothing a screen does today is
removed; each thing has one new home.

## 2. Problem

The screens carry a blog's shape.

1. `/` is the list, `editor._list`, headed "Your writing". It holds
   everything: the setup checklist, the New entry box, undo, the journal
   switch, drafts, published entries, pages, the parts of every page, and
   whatever `Face.add_to_list` hangs above and below.
2. Pages hang off that list as its third folded card, though a site need
   not have a journal at all (`starter.fill` turns it off).
3. The top bar, `face._page`, reads Your writing, Sites, View your site,
   Settings, Look, Files, Help, More. Visitors, the site's own address,
   likes and the AI helper have no place in it.
4. Settings is one long form, `setup._form`, followed by links to further
   screens.

## 3. Scope decisions (agreed with the user)

The first four were chosen by the user on 2026-11-13, each on the
session's recommendation, from drawn alternatives.

1. **The first screen is Your site**, an overview of tiles, with the
   site's name, View your site and Publish above them and Finish setting
   up below.
2. **The top bar is by part of the site**: the site's name, Your site,
   Pages, Journal, Look, Files, Visitors, Settings, Help, More.
3. **The journal has its own screen.** Off, it says what a journal is and
   offers to turn it on.
4. **Settings opens on a short list of sections**, each its own screen.
5. **No count of unpublished changes on Your site.** *(decided here)* The
   drawing the user chose showed one. Knowing it needs GitHub's listing,
   and the first screen must not wait on the network (ADR-0005). Publish
   opens PRESS-0345's box, which lists the changes.
6. **Screen addresses are free to change.** *(decided here)* Nothing binds
   them: `docs/standards/versioning-overrides.md` freezes no screen
   address, and the AI door calls functions, not screens.
7. **First-run setup is untouched.** *(decided here)* PRESS-0212's steps
   stay as they are. Only Settings, the screen at `/setup` once setup is
   done, is split.
8. **It is built in three stages, each releasable** (§ 4.7). *(decided
   here)*

## 4. Design

### 4.1 Screens and addresses

| Address | Screen | Owner |
|---|---|---|
| `/` | Your site | `overview.py`, new |
| `/pages` | Pages | `editor.py` |
| `/journal` | Journal | `editor.py` |
| `/setup` | Settings: the list of sections | `setup.py` |
| `/setup/<section>` | one section of Settings | `setup.py` |

Every other address stays. `/edit`, `/page`, `/look`, `/files`,
`/visitors`, `/sites` and the rest are reached as below.

### 4.2 The top bar

`face._page` writes, in this order:

```
<site's name> → /sites     Your site → /     Pages → /pages
Journal → /journal         Look → /look      Files → /files
Visitors → /visitors       Settings → /setup Help → /manual
More: Suggest or report a problem, Usage reports, About, theme, text size
```

The first link shows the open site's name, and "Sites" before a site is
set up. View your site leaves the bar for Your site (§ 4.3). More holds
what it holds today.

`face.your_writing` is replaced by `face.your_site`, "Your site". Every
screen's own way back (`<p class="nav">`) goes to the screen above it:
the entry editor and a template to Journal, the page editor to Pages, and
the rest to Your site.

### 4.3 Your site

In this order, and the order does not change with the site's state:

1. **The site's line**: its name and address (`editor._site_line` moves
   here), View your site, Publish, and Undo the last press
   (`editor._undo_row`).
2. **Notices**: the place `site-notices` (§ 4.6), then the press's
   failure box (PRESS-0235 INV-8 holds as written).
3. **Tiles**, each a heading, one line of figures, and its links:

   | Tile | Figures | Opens |
   |---|---|---|
   | Pages | the pages' names | `/pages` |
   | Journal | entries on the site, drafts; or "Off" | `/journal` |
   | Look | the layout's name | `/look` |
   | Menu, header and footer | — | each part's editor |
   | Files | how many files | `/files` |
   | Visitors | the cached figure, or "Not set up yet" | `/visitors` |

   Then the place `site-tiles`, for a part that adds a tile of its own.
   A tile's figures come from the Store and from caches. No tile reaches
   the network.
4. **Finish setting up**: `checklist.render`, then the place `site-below`.

**Publish** asks `publishing.PLAN_ADDRESS` for the site as it stands and
shows PRESS-0345's box. Publish now posts to a new `/publish/site`, which
runs `publishing.press_site` through `pressing.run` as a page's press
does. The plan route gains the site form: a request naming neither a
slug nor a page.

### 4.4 Pages and Journal

**Pages** holds the New page form, the pages (`editor._pages`), and Parts
of every page. The cards are open, not folded: each screen now holds one
kind of thing.

**Journal** holds, with the journal on: the switch
(`editor._journal_switch`), the New entry form (`editor._new_entry_form`),
Drafts, On your site, then the place `journal-below`. With the journal
off it holds the switch and its explanation, and published entries where
there are any, under a line saying they are off the site. It holds no New
entry form then.

A form that answered with a redirect to `/` answers with a redirect to
the screen it sits on.

### 4.5 Settings

`/setup`, once setup is done, lists the sections. Each line names what
the section holds.

| Section | Address | Holds |
|---|---|---|
| Your site's name and pictures | `/setup/site` | `site_name`, `site_description`, `site_icon`, `site_picture` |
| Your site's address | `/setup/address` | `site_address`, and the link to `/domain` |
| GitHub | `/setup/connection` | `repository`, the signed-in note, the key |
| Visitors and Google | `/setup/visitors` | `measurement_id`, the Google link or offer, the YouTube link |
| Journal | `/setup/journal` | `daily_prompt_filter`, the link to likes (`/votes`) |
| AI helper | `/assistant/setup` | as today |
| This computer | `/setup/computer` | the shortcuts, Restart, the place `computer` |

**A section's Save changes only its own fields.** It reads the saved
settings, replaces the fields the section holds, and hands the whole to
`setup._save_sequence`, so the checks a save runs today still run on
every save. A field the section does not hold is taken from the saved
settings, never from the request.

`/setup/github` and `/setup/google` are sign-in flows today and keep
their addresses, which is why the GitHub section is `/setup/connection`.

### 4.6 Places: how a part reaches a screen it does not own

`Face.add_to_list(render, above=)` becomes:

```python
PLACES = ("site-notices", "site-tiles", "site-below", "journal-below", "computer")

def add_piece(self, place: str, render: Callable[[], str]) -> None: ...
def pieces(self, place: str) -> list[str]: ...   # in registration order
```

A name outside `PLACES` raises `ValueError` at registration. Each caller
of `add_to_list` moves to one place:

| Piece | Place |
|---|---|
| `setup._unpublished_starter`, `setup._takeover_owed` | `site-notices` |
| `usage._question` | `site-notices` |
| `updating._offer_html` | `site-notices` |
| the Import offer (`id="import-offer"`) | `site-notices` |
| the AI helper's line (`list_line`) | `site-notices` |
| `youtube_screen._card` | `site-tiles` |
| `dashboard._card` | none: it becomes the Visitors tile |
| `checklist.render` | none: Your site writes it (§ 4.3) |
| `templates._listed` | `journal-below` |
| `updating._switch_html` | `computer` |
| `jpegxl_screen.line_html` | `computer` |

### 4.7 Build order

1. **The bar, Your site, Pages, Journal and places** → INV-1 to INV-5
   pass, and `scripts/by-hand-browser-checks.py` passes with its list
   rows pointed at the new screens.
2. **Settings in sections** → INV-6 and INV-7 pass.
3. **The manual**: `en.txt` says the new names, and every picture and
   video is remade with `scripts/manual-media/` → PRESS-0219 § 7's
   by-hand check.

Each stage ends with the gate green. The manual's words for a screen
change in the stage that changes the screen; stage 3 is the pictures and
the read-through.

## 5. Invariants

- **INV-1** — Every page the Face wraps carries the bar of § 4.2: those
  links, in that order, before More.
  *Test:* `tests/test_face.py::test_the_bar_names_the_parts_of_a_site`.
  It reads the `href`s outside More from a normal page and a failure
  page, and compares the list.
  *Breaks when:* a link is missing, added, or out of order, or View your
  site is still in the bar.

- **INV-2** — Every block the list held has exactly one home.
  *Test:* `tests/test_screens.py::test_each_block_has_one_home`. A seeded
  site with the journal on; for each of the New entry form, the New page
  form, the journal switch, the undo row, `id="checklist"` and Your
  templates, it asserts the screen that holds it and that `/`, `/pages`
  and `/journal` otherwise do not.
  *Breaks when:* a block is left on `/`, dropped, or shown twice.

- **INV-3** — Your site reaches no network.
  *Test:* `tests/test_screens.py::test_your_site_waits_on_nothing`. The
  site is set up for Google with nothing cached, and the transport
  raises on any request; `GET /` answers 200 and the Visitors tile says
  it has no figures yet.
  *Breaks when:* a tile asks Google or GitHub for its figure. The fixture
  isolates that rule: with a cached figure the tile would not need to
  ask.

- **INV-4** — With the journal off, Journal offers no New entry form,
  and the Journal tile says Off.
  *Test:* `tests/test_screens.py::test_a_journal_that_is_off`.
  *Breaks when:* the form shows on a site whose entries cannot publish.

- **INV-5** — A piece is shown in the place it registered for, and a
  place nobody defined is refused.
  *Test:* `tests/test_face.py::test_a_piece_shows_in_its_place`. A piece
  registered for `journal-below` shows on `/journal` and not on `/`;
  `add_piece("nowhere", …)` raises `ValueError`.
  *Breaks when:* places share one list, or a mistyped place is accepted
  and its piece never shows.

- **INV-6** — Saving one section of Settings leaves every other setting
  as it was.
  *Test:* `tests/test_setup.py::test_a_section_saves_only_its_fields`.
  Every field is given a value; each section is saved in turn with its
  own fields changed and with forged values for the fields of other
  sections; the settings file then differs only in that section's
  fields.
  *Breaks when:* a section builds its settings from the request alone,
  which blanks what the request lacks, or accepts a field it does not
  hold.

- **INV-7** — A section's save runs the checks a whole save runs.
  *Test:* `tests/test_setup.py::test_a_section_save_is_checked`. A
  repository GitHub refuses, saved from `/setup/connection`, is refused
  with the sentence the one-page form gave, and nothing is written.
  *Breaks when:* a section writes the settings file without
  `setup._save_sequence`.

## 6. Failure modes

- **The Store cannot be read**: Your site shows the failure as the list
  does today (`Face.fail`), with the bar, so Settings and Help are still
  reached.
- **A tile's figure cannot be read**: the tile shows its heading and its
  link without the figure. The other tiles are unaffected.
- **A section's save is refused**: the section shows again with the
  values typed and the refusal, as the one-page form does.
- **An old address is asked for**: none is removed, so there is none.
- **The bar is wider than the window**: it wraps to a second line. § 7's
  by-hand check reads it at the largest text size.

## 7. Tests

INV-1 and INV-5 are in `tests/test_face.py`; INV-2, INV-3 and INV-4 in a
new `tests/test_screens.py`; INV-6 and INV-7 in `tests/test_setup.py`.
Each is seen to fail before its stage's code lands.

Existing tests that pin today's layout are changed in the stage that
moves what they pin. They are the tests of the bar in
`tests/test_face.py`, `tests/test_look_screen.py`,
`tests/test_manual.py`, `tests/test_about.py` and `tests/test_usage.py`,
and the tests that read the list at `/` in `tests/test_editor.py`,
`tests/test_updating.py` and the files that fetch it for one block.

**By hand, in a browser, after stage 1:** at the default and the largest
text size, the bar's links are all reachable, and each tile's link opens
its screen. `scripts/by-hand-browser-checks.py` carries the rows.

## 8. Alternatives considered (and rejected)

- **A pages list as the first screen.** Offered to the user and not
  chosen: a newcomer does not see what else a site has.
- **Three menus in the bar: Content, Design, Site.** Offered and not
  chosen: one more click each time.
- **The journal hidden until switched on.** Offered and not chosen:
  harder to find.
- **Settings left as one screen.** Offered and not chosen: a partially
  sighted reader scrolls further.
- **Redirecting `/` to `/pages`.** No overview, and it rejects
  decision 1.
- **Keeping `add_to_list` and adding a second hook.** Two ways to reach
  a screen, and `above=` names a list that no longer exists.

## 9. Out of scope

- The Look screen's own changes — tracked by PRESS-0352 and PRESS-0359.
- A count of unpublished changes — decision 5; deferred; not yet queued.
- First-run setup's steps — decision 7.
- Choosing the manual's language — tracked by PRESS-0241.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_face.py::test_the_bar_names_the_parts_of_a_site` |
| INV-2 | `tests/test_screens.py::test_each_block_has_one_home` |
| INV-3 | `tests/test_screens.py::test_your_site_waits_on_nothing` |
| INV-4 | `tests/test_screens.py::test_a_journal_that_is_off` |
| INV-5 | `tests/test_face.py::test_a_piece_shows_in_its_place` |
| INV-6 | `tests/test_setup.py::test_a_section_saves_only_its_fields` |
| INV-7 | `tests/test_setup.py::test_a_section_save_is_checked` |
| The order on Your site does not change with state (§ 4.3) | **nothing** |
| The screens are easier to use | **nothing** — the user's own use |
| The manual's pictures match the screens | **nothing** — PRESS-0219 § 9 |

## 11. Cross-doc impact

Each spec below states a place this spec moves. Each gets a pointer
line, in the stage that moves it, and a labelled loop-log row.

- The list at `/`: PRESS-0012 § 4.5, PRESS-0014 § 4.4, PRESS-0015 § 4.6,
  PRESS-0017 § 4.3, PRESS-0023 § 4.9, PRESS-0214 § 3 decision 4 and
  § 4.5, PRESS-0262 § 4.3, PRESS-0275 § 4.3, PRESS-0333 § 4.3,
  PRESS-0337 § 4.6.
- The bar: PRESS-0219 § 3 decision 6, § 4.4 and INV-4; PRESS-0223 § 4.6;
  PRESS-0196 § 4.4; PRESS-0197 § 4.4.
- Settings as one page: PRESS-0021 and PRESS-0212.
- `README.md`, `src/pressless/manual_files/en.txt` and `CHANGELOG.md`
  name Your writing.
- `scripts/manual-media/shots.py` and
  `scripts/by-hand-browser-checks.py` select the list's parts.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0353-screens-redesign-loop-log.md`.
