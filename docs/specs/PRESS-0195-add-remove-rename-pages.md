<!-- ants-spec-format: 1 -->
# PRESS-0195 — Adding, removing and renaming a page, with the menu following

**Status:** accepted (2026-10-13). Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0195 (part of PRESS-0194, the user 2026-10-01;
the menu and timing decisions 2026-10-13).

**Amends:** PRESS-0014 (§4.8, §4.9, §9), PRESS-0182 (§9), PRESS-0199 (§9),
PRESS-0214 (§4.5, §9), PRESS-0005 (§4.3), PRESS-0006 (§4.1),
PRESS-0008 (§4.2, §4.7), PRESS-0015 (§4.4), PRESS-0012 (§4.5),
PRESS-0235 (§4.4) and `docs/design.md`. §11 lists
each edit.

Layman: he can make a new page such as Gigs, delete one, or rename it,
and the site menu keeps up.

## 1. Goal

After this ships, the list's pages card has a New page box, and a
fixed page's editor has Rename and Remove buttons. A new page waits,
like any page edit, until he presses it to his site; that press also
puts its link in his menu. Remove and Rename ask first, then press to
his site at once, taking the page's menu link out or pointing it at the
new address. A renamed page's old address forwards to the new one.

## 2. Problem

1. **The page set cannot change.** `store.list_html` reads the pages
   folder, and nothing in the Face writes a new name there or bins one.
   PRESS-0014 §4.9 says the page editor never adds, removes or renames
   a page.
2. **The menu is his own HTML.** `furniture/navigation.html` is a file
   he writes; `builder._Furniture.fill` pastes it at `{{NAVIGATION}}`
   and marks the link whose `data-nav` equals the page marker's `page`.
   A new page has no link in it, and a removed one keeps its link.
3. **A new page has no live file.** `page_editor._pressed` reads the
   live file before writing over it, and `editor._pages` lists live
   pages only, so a page that exists only as a waiting copy can be
   neither shown nor pressed.
4. **A rename breaks shared links.** `builder._Build.fixed_page` writes
   `pages/<name>.html`, and the Publisher removes a file the build no
   longer writes. PRESS-0182's forwards cover entries only.

## 3. Scope decisions (agreed with the user)

1. **The menu stays his HTML.** Pressless adds, removes or re-points
   the page's link inside it, and says so where the menu is too unusual
   to edit safely. Reordering and hiding wait for PRESS-0216. The user,
   2026-10-13. This reverses `docs/design.md`'s "the menu is a list the
   Store holds".
2. **Remove and Rename confirm, then publish at once, as a press. A new
   page waits for its own Press to site.** The user, 2026-10-13.
3. **A removed page goes to the bin; a renamed one forwards its old
   address; the homepage cannot be removed or renamed.** Settled by
   `docs/design.md` § Pages, and how they are held, and PRESS-0182.
4. **The Privacy page cannot be removed while counting is on.**
   PRESS-0199 §9. **(decided here)** It is never renamed:
   `starter.add_privacy` keys on `pages/privacy.html`, and would write a
   second one when counting is next switched on.
5. **(decided here) A page with unpublished changes cannot be renamed.**
   He presses or throws them away first, as PRESS-0182 decision 3 has
   it for an entry. Remove takes the changes to the bin with the page.
6. **(decided here) A new name already taken is refused, not
   suffixed.** An entry gets `-2`; a page's name is its menu label and
   its address, and a silent `-2` would show in both.
7. **(decided here) A forwarded page address stays reserved**, as
   PRESS-0182 decision 4 has it for an entry.
8. **(decided here) Only the navigation file is edited.** A link to a
   removed page in the header or footer is reported, not removed.
9. **One review round.** The user's budget for a new spec.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The Store

```python
# src/pressless/store.py — added or widened

PAGE_FORWARDS_FILE = "pages.json"    # in FORWARDS_FOLDER, beside forwards.json

def page_forwards_path_for(folder: Path) -> Path: ...
def read_page_forwards(folder: Path) -> dict[str, str]: ...
def write_page_forwards(folder: Path, forwards: dict[str, str]) -> Path: ...
def list_html(folder: Path, kind: str, *, waiting: bool = False) -> tuple[str, ...]: ...
```

`read_page_forwards` and `write_page_forwards` keep PRESS-0182 §4.1's
rules for `read_forwards` and `write_forwards`, with names checked by
`html_path_for(folder, PAGES_FOLDER, name)`. It also refuses `index` as
a key or a value. Absent reads as `{}`. The file is in `FORWARDS_FOLDER`,
which `_BINNABLE` already holds.

`list_html(..., waiting=True)` lists `WAITING_FOLDERS[kind]` by the same
rules. The default is unchanged.

### 4.2 The menu

A new module, pure text in and out:

```python
# src/pressless/menu.py

class Unusual(Exception): ...   # the menu is laid out in a way Pressless does not edit

def links_to(text: str, name: str) -> tuple[tuple[int, int], ...]: ...
def add(text: str, name: str, words: str) -> str: ...
def remove(text: str, name: str) -> str: ...
def rename(text: str, old: str, new: str, old_words: tuple[str, ...],
           new_words: str) -> str: ...
```

**A link** is an `<a` start tag up to the next `</a>`, case-insensitive.
**A link to `name`** is one whose `href` value, single- or double-quoted,
is exactly `{{UP}}pages/<name>.html`. `links_to` returns each one's
offsets, in order.

**A plain menu** is one where removing every comment and every link
leaves no tag but one `<nav …>` and its `</nav>`, and holds at least
one link. `add` and `remove` raise `Unusual` on any other menu, and
write nothing. Every menu in §5 INV-5's fixtures is plain; a menu of
`<ul><li>` items is not.

- **`add`** inserts a link after the last link whose `href` starts with
  `{{UP}}pages/`, else after the last link. It is preceded by the run of
  whitespace that precedes the link it follows, possibly empty:
  `<a href="{{UP}}pages/<name>.html" data-nav="<name>">{words}</a>`,
  `words` through `html.escape`. So a page lands before a Journal link.
- **`remove`** deletes each link to `name`, with the whitespace run
  immediately before it. No link to `name` returns `text` unchanged.
- **`rename`** never raises. In each link to `old` it replaces the
  `href` value with `{{UP}}pages/<new>.html`. Where the link's text,
  unescaped and stripped, equals one of `old_words`, it becomes
  `new_words` through `html.escape`. `data-nav` is left alone: the page's own
  marker still names it.

Every byte outside the changed links is kept.

### 4.3 A new page

The pages card on the list (`editor._pages`) lists the sorted union of
`list_html(folder, PAGES_FOLDER)` and its `waiting=True` listing. Below
it, a box and a New page button post `name` to `POST /page/new`. Under
`editor.LOCK`:

1. **`page = editor.name_address(name)`.** Refused, writing nothing,
   with a hint beside the box, where `page` is empty, is `index`, is a
   live or waiting page, is a key of `read_page_forwards`, or
   `html_path_for` refuses it.
2. **Write the waiting copy**, `store.write_html(folder, PAGES_FOLDER,
   page, <text>, waiting=True)`. `<text>` is `starter.privacy_page`'s
   shape: `builder.stylesheets(folder)` linked from depth 1, a header
   pair with `page="<page>"`, a `<title>` and `<h1>` holding `name`
   through `html.escape`, one paragraph of placeholder words, and a
   footer pair.
3. **`pressing.forget()`**, as every other write does (PRESS-0235 §4.4).
4. **Answer 303** to the page editor for `page`.

The live page and the menu are untouched. **Throw away changes**
(PRESS-0014 §4.8) on a page with no live file bins its only copy, and
its 303 goes to the list instead of the page editor.

**Its first press** is PRESS-0014 §4.7 with these changes, where the
live file is absent at step 3:

- Step 3 remembers *absent* for the page. It also remembers the live
  navigation file's text, and its waiting copy's where one exists. It
  writes `menu.add` of each, `words` being the page's `<title>` text,
  unescaped, else `builder.label(page)`.
- A copy `menu.add` raises `Unusual` on is left as it is, and the reply
  carries a notice saying the menu was not changed and how to add the
  link in its code.
- The put-back after a failure bins the live page it wrote and writes
  each remembered navigation text back.

### 4.4 Remove and Rename

The page editor shows Remove and Rename on a fixed page other than
`index`. Each asks first, through `window.confirm`; Rename asks for the
new name too. Remove's question says unpublished changes go with the
page. Each posts `kind`, `name` and, for Rename, `to`, to
`POST /page/remove` or `POST /page/rename`. Both run as a press
(PRESS-0235 §4.4); a `busy` answer writes nothing.

**Refused, writing nothing and pressing nothing**, with a hint:

- `name` is `index`, or is not a live page;
- Remove, where `name` is `privacy` and `settings.measurement_id` is
  set; Rename, where `name` is `privacy` (§3 decision 4);
- Rename, where a waiting copy of `name` exists;
- Rename, where `editor.name_address(to)` is empty, `index`, equal to
  `name`, a live or waiting page, a page-forwards key whose value is not
  `name`, or a name `html_path_for` refuses.

Then, under `editor.LOCK` held throughout, as PRESS-0014 §4.7 steps 2
to 4: settings and the key, then remember, write, and publish. **Every
file the step writes or bins is remembered first**, as its text or as
absent.

**Remove** bins the live page and its waiting copy. It writes
`menu.remove` of the live navigation and its waiting copy, and the page
forwards without each pair whose value is `name`.

**Rename**, with `new = editor.name_address(to)`, writes the live text
byte for byte at `new` and bins `name`. It rewrites the page forwards
as PRESS-0182 §4.2 step 4 does: drop the key `new`, re-point each value
`name` to `new`, add `name` → `new`. It writes `menu.rename(…, name,
new, old_words, to.strip())` of the live navigation and its waiting
copy. `old_words` holds `builder.label(name)` and, where the live page
has one, its `<title>` text, unescaped: §4.3 gives a page Pressless
added the typed name as its link words, and an imported page's link
reads as its label.

**A failure while publishing puts each remembered file back**, in
reverse order: text is written, absent is binned. An
`publisher.OutcomeUnknown` is not put back, as PRESS-0014 §4.7 has it.

The reply is JSON: `published`, `failure`, `hint`, `notices`, `busy`,
and `address` — the list after a Remove, the editor for `new` after a
Rename, the page's own editor otherwise. `hint` is null except on a
refusal. A `busy` reply adds `said`, the running press's words. Its
notices say where `menu.remove` raised `Unusual` or found no link to
`name`, and where the header or footer still holds `pages/<name>.html`.

### 4.5 The Builder

`build` reads `store.read_page_forwards(folder)` once. For each pair,
sorted by key, where the value is a page this build writes and the key
is not, it writes `pages/<old>.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{label}</title>
<link rel="canonical" href="{site_address}/pages/{new}.html">
<meta http-equiv="refresh" content="0; url={new}.html">
</head>
<body>
<p>This page has moved to <a href="{new}.html">{label}</a>.</p>
</body>
</html>
```

`{label}` is `builder.label(new)` through `html.escape`; `{site_address}`
is as PRESS-0182 §4.3 has it. "A page this build writes" is
`read_html`'s map, `change` included. A forwarding page is in no
sitemap line.

`content()` writes `content/forwards/pages.json` byte for byte where the
Store holds it.

### 4.6 Undo

`undo._read` recognises `content/forwards/pages.json` and reconciles it
as PRESS-0182 §4.4 reconciles `forwards.json`. Pages themselves are
already restored by `undo._restore_html`: a removed page comes back with
the menu that linked it. **An undo keeps a page the fetched state does
not hold** (PRESS-0015 §4.4), so undoing a new page's first press
leaves the page on the site with no menu link, and undoing a rename
leaves both names, the menu pointing at the old one.

## 5. Invariants

Route tests run through `face.serve(tmp_path)` with a fake transport, as
`tests/test_page_editor.py` does. The menu fixtures are the starter's
(`starter._navigation`), a one-line menu
(`<nav><a href="{{UP}}index.html" data-nav="Home">Home</a> <a href="{{UP}}pages/about.html" data-nav="About">About</a></nav>`),
and a four-link menu whose last link is `{{UP}}blog/index.html`.

- **INV-1** — `POST /page/new` writes the waiting copy and nothing else:
  no live page, the navigation byte-identical, and the list shows the
  page.
  *Test:* `tests/test_pages.py::test_a_new_page_waits`.
  *Breaks when:* the route writes the live file, or the list reads live
  pages only.
- **INV-2** — Each §4.3 step 1 refusal writes nothing.
  *Test:* `tests/test_pages.py::test_a_taken_page_name_is_refused`, one
  case each: empty, `index`, live, waiting, forwarded.
  *Breaks when:* a taken name is suffixed or overwritten.
- **INV-3** — A new page's first press writes the live page, adds its
  link to the live navigation and its waiting copy, and the site the
  fake transport receives holds `pages/<page>.html` and the link.
  *Test:* `tests/test_pages.py::test_a_new_pages_first_press_adds_its_link`.
  *Breaks when:* the link is added at `/page/new`, or to one copy only.
- **INV-4** — A failed first press leaves no live page and both
  navigation texts byte-identical.
  *Test:* `tests/test_pages.py::test_a_failed_first_press_puts_back`,
  with a transport that raises.
  *Breaks when:* the put-back writes the absent page back as empty, or
  forgets the navigation.
- **INV-5** — `menu.add` inserts one link after the last `pages/` link
  with that link's leading whitespace, and every other byte is kept, on
  each fixture. A `<ul><li>` menu raises `Unusual`.
  *Test:* `tests/test_menu.py::test_add_places_the_link_after_the_last_page`.
  *Breaks when:* the link goes after Journal, or the separator is
  hard-coded.
- **INV-6** — `menu.remove` deletes every link to `name` with its
  leading whitespace and nothing else; a link whose `href` is
  `{{UP}}pages/about.html.bak` is kept.
  *Test:* `tests/test_menu.py::test_remove_takes_only_that_pages_links`.
  *Breaks when:* the match is a substring rather than the whole value.
- **INV-7** — `menu.rename` changes the `href`, and the text only where
  it equals one of `old_words`, on a `<ul><li>` menu as well.
  *Test:* `tests/test_menu.py::test_rename_repoints_any_menu`.
  *Breaks when:* rename checks for a plain menu, or rewrites
  `data-nav`.
- **INV-8** — Remove bins the live page and its waiting copy, takes its
  link out, drops page forwards to it, and the published site lacks the
  page.
  *Test:* `tests/test_pages.py::test_removing_a_page`.
  *Breaks when:* the waiting copy survives, so the page returns on the
  list.
- **INV-9** — Each §4.4 refusal writes nothing and presses nothing.
  *Test:* `tests/test_pages.py::test_remove_and_rename_refusals`, one
  case each.
  *Breaks when:* `privacy` is removable with `measurement_id` set.
- **INV-10** — A failed Remove or Rename puts every file back byte for
  byte; an `OutcomeUnknown` puts nothing back.
  *Test:* `tests/test_pages.py::test_a_failed_remove_or_rename_puts_back`.
  *Breaks when:* the bin is not reversed, or the forwards are not.
- **INV-11** — Rename writes the page byte-identical at the new name,
  bins the old, re-points the menu, and leaves the forwards with no
  loop when a page moves back. A page added as "Live Shows" has its
  link words changed too.
  *Test:* `tests/test_pages.py::test_renaming_a_page_and_back`.
  *Breaks when:* moving back leaves `a` → `a`, or `old_words` holds the
  label alone.
- **INV-12** — The build writes `pages/<old>.html` for a forward to a
  written page, none where `<old>` is itself a page, and no sitemap
  line for it.
  *Test:* `tests/test_builder.py::test_a_renamed_page_forwards`.
  *Breaks when:* a forward overwrites a real page.
- **INV-13** — `read_page_forwards` refuses invalid JSON, a name
  `html_path_for` refuses, `index`, and a self-map.
  *Test:* `tests/test_store_extras.py::test_page_forwards_follow_the_name_rule`.
  *Breaks when:* a key like `../x` reaches the Builder.
- **INV-14** — Undo restores `pages.json` from a fetched state that
  holds it, and keeps the Store's where it does not.
  *Test:* `tests/test_undo.py::test_undo_restores_page_forwards`.
  *Breaks when:* `content()` leaves the file out.

## 6. Failure modes

- **An unusual menu.** The page change still happens; the reply says
  the menu was left, and the navigation's editor is a link away.
- **A link Pressless does not recognise**, such as an absolute address:
  Remove reports no link found. Rename leaves it, and the forward
  catches it.
- **An interrupted Remove or Rename**, the app killed mid-step: the
  Store holds whatever was written, the put-back never ran, and the
  next press publishes it. Each write is the Store's atomic one, so no
  file is half-written.
- **A preview of a new page** shows a menu without its link: the link
  is added at the press.

## 7. Tests

Each is seen failing against code without the change.

- `tests/test_pages.py`, new: the routes — INV-1, INV-2, INV-3, INV-4,
  INV-8, INV-9, INV-10, INV-11.
- `tests/test_menu.py`, new: the text functions — INV-5, INV-6, INV-7.
- `tests/test_pressing.py::test_a_second_press_is_refused` gains
  `/page/remove` and `/page/rename`.
- `tests/test_builder.py`: INV-12. `tests/test_store_extras.py`: INV-13.
  `tests/test_undo.py`: INV-14.

The buttons, the confirm text and a real press against GitHub are
checked by hand, in a browser.

## 8. Alternatives considered (and rejected)

- **The menu as a list the Store holds.** Rejected by the user
  2026-10-13: the menu stays his HTML.
- **Parsing the menu with `html.parser` and writing it back.** Rejected:
  PRESS-0014 §4.9 forbids regenerating a file from a parse, and a
  writer's spacing would not survive.
- **Adding the link at `/page/new`.** Rejected: the next press of
  anything would publish a menu linking a page that is not there.
- **One forwards file for entries and pages.** Rejected: the two name
  spaces overlap, so `about` could mean either.

## 9. Out of scope

- Reordering and hiding menu links — PRESS-0216.
- Editing a link in the header or footer — reported only (§3 decision 8).
- A page made from a template — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_pages.py::test_a_new_page_waits` |
| INV-2 | `tests/test_pages.py::test_a_taken_page_name_is_refused` |
| INV-3 | `tests/test_pages.py::test_a_new_pages_first_press_adds_its_link` |
| INV-4 | `tests/test_pages.py::test_a_failed_first_press_puts_back` |
| INV-5 | `tests/test_menu.py::test_add_places_the_link_after_the_last_page` |
| INV-6 | `tests/test_menu.py::test_remove_takes_only_that_pages_links` |
| INV-7 | `tests/test_menu.py::test_rename_repoints_any_menu` |
| INV-8 | `tests/test_pages.py::test_removing_a_page` |
| INV-9 | `tests/test_pages.py::test_remove_and_rename_refusals` |
| INV-10 | `tests/test_pages.py::test_a_failed_remove_or_rename_puts_back` |
| INV-11 | `tests/test_pages.py::test_renaming_a_page_and_back` |
| INV-12 | `tests/test_builder.py::test_a_renamed_page_forwards` |
| INV-13 | `tests/test_store_extras.py::test_page_forwards_follow_the_name_rule` |
| INV-14 | `tests/test_undo.py::test_undo_restores_page_forwards` |
| Remove and Rename answer `busy` during a press | `tests/test_pressing.py::test_a_second_press_is_refused` |
| New failures and hints have sentences | `tests/test_face.py::test_every_failure_type_has_a_sentence`, `tests/test_words.py` |
| The buttons, the confirm text and the notices on screen | **nothing** in CI — by hand, in a browser |
| A real Remove and Rename against GitHub | **nothing** in CI — by hand |

## 11. Cross-doc impact

- `docs/specs/PRESS-0014-fixed-pages.md` §4.8, §4.9 and §9 — the
  throw-away redirect, and adding, removing and renaming, point here.
- `docs/specs/PRESS-0182-published-address.md` §9 — renaming a page
  points here.
- `docs/specs/PRESS-0199-counting-code.md` §9 — the Privacy refusal
  points here.
- `docs/specs/PRESS-0214-journal-switch.md` §4.5, §9 and §11 — the menu
  stays the navigation file; a journal link stays until he removes it.
- `docs/specs/PRESS-0005-store.md` §4.3 — `forwards/pages.json` joins
  the layout.
- `docs/specs/PRESS-0006-pages-furniture-comments.md` §4.1 — `list_html`
  gains `waiting`.
- `docs/specs/PRESS-0008-builder.md` §4.2 and §4.7 — page forwards and
  `content/forwards/pages.json`.
- `docs/specs/PRESS-0015-undo.md` §4.4 — the page forwards file.
- `docs/specs/PRESS-0012-editor.md` §4.5 — the pages card's New page box.
- `docs/design.md` § The menu follows the pages, and § A site need not
  have a journal — written back after this spec's gate.
- `docs/specs/PRESS-0235-press-status.md` §4.4 — the two new press
  routes, and `/page/new` among the writes that call `pressing.forget`.
- `tests/test_main.py::test_the_double_click_opens_pressless` — its route
  list gains the three routes `page_editor.register` adds.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0195-add-remove-rename-pages-loop-log.md`.
