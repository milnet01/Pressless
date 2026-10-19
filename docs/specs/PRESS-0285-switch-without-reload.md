<!-- ants-spec-format: 1 -->
# PRESS-0285 — The editor switches between the page and its code in place

**Status:** accepted (2026-10-19).
**Kind:** enhancement.
**Source:** ROADMAP PRESS-0285 (user-hand-check-2026-10-16; the user's
answers 2026-10-16).

**Changes:** PRESS-0014 § 4.5's switch, PRESS-0260 § 4.1 and § 4.2
(§ 11).

Layman: moving between editing the page and seeing its code happens in
place, with no reload, and nothing typed is lost on the way.

## 1. Goal

**View editor** and **Show me the code** change the editor's view in
place: the Face page stays loaded, the side panel or the code box takes
the other's place, and the preview reloads alone. What was typed before
the click is saved first and shows in the other view. Code the visual
view cannot read leaves the code view showing, with the reason.

## 2. Problem

1. **Each switch is a page load.** `page_editor._page` writes the switch
   as an `a data-page-link`, and `_PAGE_SCRIPT` follows such a link with
   `window.location.href` once the save settles.
2. **Each view's page carries only its own parts.** `_page` writes the
   side panel and `_VISUAL_SCRIPT` only where `sections` is given, the
   menu panel and `_MENU_SCRIPT` only where `links` is, and the code box
   otherwise.
3. **The visual script builds its model once.** `_VISUAL_SCRIPT` reads
   the `sections` JSON `_panel` writes, at load, into `model` and
   `byPath`; `_MENU_SCRIPT` reads `links` the same way. Nothing builds
   either again from another outline.
4. **Only `_open` decides which view a file can have.** It reads the
   file, tries `builder.furniture_spans`, `menu.links` or `_area`, falls
   back to `CODE` with a notice, and builds the preview, inline.

## 3. Scope decisions (agreed with the user)

1. **The switch reads "View editor" in the code view.** The user,
   2026-10-16. Shipped; not reopened here.
2. **The switch happens with no reload.** The user, 2026-10-16.
3. **A short spec with one review round, built in 0.10.0.** The user,
   2026-10-16.
4. **(decided here) The server decides the view, as at opening.** A
   switch asks a route that answers with what opening the file in that
   view would give, so code the visual view cannot read is judged by
   `blocks`, `menu` and `builder`, as now.
5. **(decided here) The switch shows whenever the file opens**, a file
   whose furniture cannot be read included. A switch into the visual
   view there answers with the code view and the reason. The switch
   keeps its place on the screen.
6. **(decided here) A switch refused, or a save refused before it,
   leaves the view as it was.**

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 One function decides the view

`_open`'s steps from reading the file to building the preview move into
one function, called by `_open` and by the switch route alike. Given
the kind, name, asked view and `show`, it returns the view granted, the
file's text, `base`, `waiting`, the outline or the menu's links, the
photographs and kept files, any `broken` failure, the notices and the
preview. Its rules are `_open`'s today, but for the listing § 4.3 moves.

It writes nothing. A page with no area is adopted in memory, as
PRESS-0260 § 4.1 step 2 says.

### 4.2 The route

`GET /page/view?kind=&name=&view=&show=`, under `editor.LOCK`, answers
JSON:

| Key | Holds |
|---|---|
| `view` | the view granted: `visual` or `code` |
| `address` | the address that opens the file in the view granted, as `_page_address(kind, name, view=…)` writes it |
| `base`, `waiting` | as a save's reply |
| `text` | the file's text, in the code view |
| `sections` | `outline`'s list, in a page's or furniture file's visual view |
| `links` | `menu.links`, in the menu's visual view |
| `broken` | the failure `_open` shows in `#broken`, or `""` |
| `notices`, `preview`, `failure` | as a save's reply |

It remembers the asked view by `choices.remember`, as `_open` does.
A `store.StoreError` answers 409 with the failure, as a refused save
does. Unlike `_open`, it never answers with `pressing.holding`'s page;
a save does not either.

### 4.3 The page carries both views

For a page or a furniture file, `_page` writes the code box and the
side panel; for the menu, the code box and the menu panel. The view not
showing is `hidden`. A page or a furniture file carries `_VISUAL_SCRIPT`
and `_drag`; the menu carries `_MENU_SCRIPT`. `_open` lists the
photographs and kept files in either view, for the panel. A listing
failure is `broken` in either view.

The switch is two links in one place, `data-switch="visual"` and
`data-switch="code"`, one `hidden`. Each keeps its `href`, the address
the switch has today, so a link opened in a new tab still works.

### 4.4 The click

1. The view being left, and the frame, take `inert`, so nothing more is
   typed into them.
2. The script settles the save: a save in flight is waited for, and an
   unsaved change is saved. A save refused stops there: `inert` is
   removed and the refusal shows, as today.
3. The switch holds the save queue, as Publish does, and asks the
   route with `state.show`.
4. Where the reply grants the view asked for, the script shows that
   view's parts and hides the other's, swaps the two links, sets
   `state.view` and the form's `data-view`, and puts the reply's
   address in the address bar with `history.replaceState`. Into the
   code view it fills the box with `text` and repaints its colours;
   into the visual view, `presslessVisual.open` takes `sections`, or
   `links` for the menu.
5. Either way it adopts `base`, `waiting` and `notices` as after a
   save, fills `#broken` and the failure box, sets the frame to
   `preview`, and removes `inert`.

### 4.5 The visual and menu scripts open again

`_VISUAL_SCRIPT` gains `open(sections)`, taking `outline`'s list: it
empties `model`, `byPath` and `removed`, lets go of the picked section,
forgets `editing`, `dragging` and a waiting preview, and builds the
model and `frameSections` from the list as the load does now. `up`,
`accept` and `largest` stay as read at load. The load calls it with
`given.sections`. `_MENU_SCRIPT` gains the same for its `links`. Each
script offers it as `presslessVisual.open`.

**While the code view shows, both are idle.** `posting()` in
`_PAGE_SCRIPT` gives `null` where `state.view` is `code`, so a save
posts `text`. `pair` returns at once, so the frame takes no clicks and
no `contenteditable`.

## 5. Invariants

- **INV-1** — A switch loads no new Face page.
  *Test:* `scripts/by-hand-browser-checks.py`, row `switch_in_place`:
  a value set on `window` before the switch is still there after it,
  both ways, for a page, the header and the menu.
  *Breaks when:* the switch link's click follows its `href`.

- **INV-2** — What was typed before a switch shows in the other view
  and is in the waiting copy.
  *Test:* `switch_in_place`: words typed into the frame, then the
  switch clicked at once, show in the code box; code typed into the
  box, then the switch clicked at once, shows in the frame.
  *Breaks when:* step 3 of § 4.4 asks the route before the save
  settles, so the route reads the file without the typing.

- **INV-3** — After a switch into the visual view, sections added in
  the code view can be picked, and a save keeps every byte of the
  sections not changed.
  *Test:* `switch_in_place`: a text section added in the code box, the
  switch, the new section picked and typed in; the waiting copy holds
  both sections, the first byte for byte.
  *Breaks when:* the model is the one built at load, so the new section
  cannot be picked, and the save posts paths of the old file and is
  refused.

- **INV-4** — While the code view shows, a save posts the box's text.
  *Test:* `switch_in_place`: after a switch from the visual view, code
  typed into the box reaches the waiting copy.
  *Breaks when:* `posting()` still asks the visual script, so the
  save posts its model and the box's change is lost.

- **INV-5** — The route grants what opening the file in that view
  gives.
  *Test:* `tests/test_page_editor.py::test_a_switch_answers_as_opening_does`:
  for a page, an unmarked page, a page that cannot be adopted, the
  header and an unusual menu, the route's `view` and `sections` or
  `links` equal those of `GET /page` with the same `view`. Where it
  grants the code view, its `text` is the file.
  *Breaks when:* the route decides the view by its own rules and drops
  `_open`'s fallback for an unusual menu.

- **INV-6** — A switch writes no page file.
  *Test:* `tests/test_page_editor.py::test_a_switch_writes_nothing`:
  after the route on an unmarked page, the live file's digest is
  unchanged and there is no waiting copy.
  *Breaks when:* the route writes the adopted text.

- **INV-7** — A switch whose save is refused leaves the view as it was.
  *Test:* `switch_in_place`: the file changed on disk, then typing and
  the switch; the code view still shows, the failure box says why, and
  nothing is `inert`.
  *Breaks when:* step 2 of § 4.4 goes on after a refused save.

## 6. Failure modes

| What happens | What the user sees |
|---|---|
| The visual view cannot read the code | The code view stays, with the notice opening gives (§ 3 decision 5) |
| The save before the switch is refused | The view stays; the failure box says why (INV-7) |
| The file has gone | The view stays; the failure box says so, and saving stops |
| The preview fails to build | The switch happens; the failure box says why, as at opening |
| A press runs | The switch waits until the press lets go of `editor.LOCK`, as a save does |

## 7. Tests

| Test | Locks |
|---|---|
| `tests/test_page_editor.py` | INV-5, INV-6 |
| `scripts/by-hand-browser-checks.py`, row `switch_in_place` | INV-1, INV-2, INV-3, INV-4, INV-7, in Chrome |
| By hand | Firefox on this machine, Edge on the Windows box: switch both ways after typing |

Each test is seen failing before the code it locks exists.

## 8. Alternatives considered (and rejected)

- **Fetching the other view's whole page and swapping it in.** The
  scripts start themselves once and bind their listeners then, so
  running them again binds every listener twice.
- **Building the visual model from the code in the browser.** The
  outline is `blocks.read`'s, in Python; a second reader in the script
  would disagree with it.
- **Making the reload look smooth.** The user asked for no reload.
- **Hiding the switch where the furniture cannot be read**, as now.
  A control that comes and goes moves what is beside it.

## 9. Out of scope

- The furniture's *Show on* links, which still reload.
- Rename, Remove and *Bin this proof*, which leave the page.

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand before a release |
| INV-2 | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |
| INV-3 | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |
| INV-4 | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |
| INV-5 | `tests/test_page_editor.py::test_a_switch_answers_as_opening_does` |
| INV-6 | `tests/test_page_editor.py::test_a_switch_writes_nothing` |
| INV-7 | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |

## 11. Cross-doc impact

Landed with the code, as PRESS-0260 § 3 decision 8 did:

- `docs/specs/PRESS-0014-fixed-pages.md` § 4.5: the switch line
  annotated *amended by PRESS-0285*: it changes view in place.
- `docs/specs/PRESS-0260-visual-editor.md` § 4.1's switch sentence and
  § 4.2's "waits for the frame's `load`" annotated the same way: the
  model is built at each switch into the visual view.
- `CHANGELOG.md`: one line, saying the switch no longer reloads.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0285-switch-without-reload-loop-log.md`.

## 13. Resource cost

A switch reads one file and builds one preview, as a reload did, and
no longer loads the Face page and its scripts. A page in either view
carries both views' controls and scripts.
