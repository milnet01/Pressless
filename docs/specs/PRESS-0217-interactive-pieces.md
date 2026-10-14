<!-- ants-spec-format: 1 -->
# PRESS-0217 — Ready-made interactive pieces, and a place for their own script

**Status:** accepted (2026-10-14). Gated for one round, the user's budget for
a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0217 (the user 2026-10-02 under PRESS-0198; a short
spec and one review round, the user 2026-10-14).

**Blocked by:** PRESS-0215 (Blocks) and PRESS-0260 (the visual editor), both
shipped. **Changes:** PRESS-0215 § 4.1 (the kinds) and § 4.4 (the kind table);
PRESS-0260 § 4.3 (the panel per kind). **Builds on the security invariant of**
PRESS-0266 and PRESS-0260 § 4.2 (INV-5).

Layman: a page can hold a few ready-made interactive pieces — a picture
slideshow, questions that fold open, a picture that enlarges, a back-to-top
button, a countdown — chosen from a list like any other section, and anyone
who writes their own small script can drop that in too. None of it runs inside
Pressless; it runs only on the published site.

## 1. Goal

The visual editor offers five ready-made interactive pieces and a place for the
user's own script, each added, picked, moved and removed as a section is today
(PRESS-0260 § 4.3). Each piece works with the page's look and needs no outside
service. The behaviour runs only on the **published** site; inside Pressless
the preview shows each piece's static fallback and never runs its script.

## 2. Problem

1. **Every section Pressless offers is static.** `blocks.KINDS` holds nine
   kinds (`blocks.py` § 4.1) and none carries behaviour. A writer who wants a
   slideshow or a countdown must hand-write HTML and script into a code
   section, which the visual editor cannot pick or change.
2. **The preview must not run the behaviour.** PRESS-0260 § 4.2 (INV-5)
   sandboxes the preview frame with `allow-same-origin` and no `allow-scripts`,
   so a piece's script cannot run there — and PRESS-0266 records why it must
   not: a script that ran in the Face's origin would carry the session cookie
   and could reach a Face endpoint. So a piece has to look right in the preview
   **without** its script.
3. **A user script is arbitrary code.** It must reach the published page
   verbatim, be shown inertly in the editor, and never be interpreted,
   executed or trusted by Pressless.
4. **A page that uses no piece must not change.** Today's published pages carry
   no behaviour script; adding this feature must leave such a page byte-for-byte
   as it is.

## 3. Scope decisions (agreed with the user)

1. **Five ready-made pieces, and a place for the user's own script.** The user,
   2026-10-02 and 2026-10-14: questions that fold open, a picture slideshow, a
   picture that enlarges when clicked, back to top, and a countdown.
2. **A short spec, gated for one round.** The user, 2026-10-14.
3. **(decided here) Each ready-made piece is a new Blocks kind.** It joins
   `blocks.KINDS` with its own fields, writer and reader, so it is stored,
   read back, picked, moved and removed exactly as the nine kinds are (§ 4.1).
   The user's own script is a new kind, `script`.
4. **(decided here) The behaviour is one script Pressless ships, added to the
   published page only.** A page that uses a ready-made piece gets Pressless's
   `assets/pieces.js`, which progressively enhances the static HTML by its
   class and `data-` hooks. Nothing is loaded from elsewhere (§ 4.3).
5. **(decided here) In the preview, every piece shows its no-script fallback.**
   The static HTML alone is meaningful: a slideshow shows its pictures, folding
   questions are shown open, a countdown shows its target as text, back-to-top
   is a plain link. The piece is visible and pickable; it does not run.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The pieces as Blocks kinds

`blocks.py` gains the kinds `SLIDESHOW`, `QUESTIONS`, `ENLARGE`, `TOP`,
`COUNTDOWN` and `SCRIPT`, each added to `KINDS`, `_WRITERS`, `_READERS` and
`_FORMS` (`blocks.py` § 4.1, § 4.4, § 4.5) and to the placement sets (`_AT_TOP`,
and `_IN_A_COLUMN` where the piece may sit in a column). Each writes semantic
HTML inside its two marks, carrying a `pressless-<kind>` class and whatever
`data-` attributes its fallback and `pieces.js` need, and nothing that a
page's existing CSS does not style:

| Kind | Fields | Static HTML (the fallback) |
|---|---|---|
| slideshow | none; `parts[0]` its pictures | the pictures in a `<div class="pressless-slideshow">`, all shown in order |
| questions | none; `parts` one list per question | a `<dl class="pressless-questions">`, each question a `<dt>` and its answer a visible `<dd>` |
| enlarge | a picture's fields | a picture in a `<figure class="pressless-enlarge">`; the click-to-enlarge behaviour is script-only |
| top | none | `<a class="pressless-top" href="#top">` with its words; a plain in-page link without script |
| countdown | `to` (an ISO date-time), `label` | `<p class="pressless-countdown" data-to="…">` showing the target as text |
| script | `code` (the user's script) | a `<script>` holding the code verbatim; it runs on the published host and is inert in the preview (§ 4.4) |

`section_html` refuses a piece with a malformed field as it refuses the nine
kinds today — a `countdown` whose `to` is not an ISO date-time, a `slideshow`
or `questions` with no parts — and writes nothing (`blocks.py` § 4.4,
`SectionRefused`).

`page_editor._KINDS` and `_KIND_WORDS` gain the six, so the panel's **Add**
list offers them, and `_panel` shows each piece's settings by kind
(PRESS-0260 § 4.3). `outline` carries them as it carries any kind.

### 4.2 The preview runs no piece

The preview is unchanged from PRESS-0260 § 4.2: the frame keeps
`sandbox="allow-same-origin"` with no `allow-scripts`, so neither `pieces.js`
nor a `script` piece runs there. The editor shows each piece's static
fallback (§ 4.1), so a slideshow, a countdown and folding questions are all
visible and pickable without behaving. A `script` piece shows in the panel as
a code box, as a code section does (PRESS-0216 § 4.2), and never runs.

### 4.3 The behaviour on the published site

`builder` ships `pieces.js` as a packaged asset. Building the site folder,
`_Build.fixed_page` adds `<script src="…/pieces.js" defer></script>` to a page
**only where that page carries a ready-made piece** (a `pressless-<kind>` the
script enhances), injected at the end of `<head>` or after `<body>` the way the
counting code is (`builder.py` `counted`, PRESS-0199 § 4.2). A fixed page
carries its own stylesheet `<link>` in its HTML, so the script is injected, not
linked through `stylesheets`. `pieces.js` reads only the DOM and the `data-`
hooks; it loads nothing from the network and needs no outside service.

The published site runs on the external host (GitHub Pages), not the Face, so
its own scripts run normally there; the Face's CSP and sandbox never apply to
it. In the Face, the same `pieces.js` served under `/preview/` is inert,
because the frame has no `allow-scripts` (§ 4.2).

### 4.4 The user's own script

A `script` piece holds the user's code in its `code` field. `section_html`
emits it as a `<script>` element holding the code verbatim
(`blocks._WRITERS[SCRIPT]`), so it is part of the page's content like any
section — stored in the Store's file, read back and round-tripped (INV-1). On
the published host the script runs; in the preview it is inert, because the
frame is sandboxed without `allow-scripts` (§ 4.2). Pressless never parses,
executes or trusts the code: it is the user's, on the user's own site. A
`script` piece is shown in the editor as a code box.

### 4.5 What this item never does

- It never runs a piece's script, or a user's script, in the Face's origin.
- It never adds a piece's script to a published page that carries no piece.
- It never loads a ready-made piece's behaviour from an outside service.
- It never interprets or validates the user's own script.

## 5. Invariants

- **INV-1** — A page holding a ready-made piece is read by `blocks.read` and
  written back by `blocks.write` byte for byte when nothing changed, and the
  piece is picked, moved and removed in the visual editor as the nine kinds
  are.
  *Test:* `tests/test_blocks.py::test_a_piece_round_trips`.
  *Breaks when:* a new kind's reader does not accept its own writer's bytes, so
  the section is kept as code and the editor cannot pick it.

- **INV-2** — No piece's behaviour script and no `script` piece runs in the
  Face's origin: the preview frame keeps `sandbox="allow-same-origin"` with no
  `allow-scripts`, and no code path adds `allow-scripts` to it (the frame is
  written in the editor page — `page_editor.py`, `editor.py`).
  *Test:* `tests/test_page_editor.py::test_the_piece_preview_runs_no_script`
  finds the preview frame sandboxed without `allow-scripts` on a page holding a
  slideshow and a `script` piece.
  *Breaks when:* the preview is given `allow-scripts` so a piece can be shown
  behaving, which lets a `script` piece reach the Face's endpoints.

- **INV-3** — A published page that carries no piece is written byte for byte
  as it is today: no `pieces.js` link and no behaviour script.
  *Test:* `tests/test_builder.py::test_a_page_with_no_piece_is_unchanged`.
  *Breaks when:* `pieces.js` is linked on every page rather than only where a
  piece is present.

- **INV-4** — Each ready-made piece's static HTML is meaningful without script:
  a slideshow's pictures are all present, folding questions are readable, a
  countdown shows its target, back-to-top is a working in-page link.
  *Test:* `tests/test_blocks.py::test_each_piece_has_a_fallback`.
  *Breaks when:* a piece writes an empty shell that needs `pieces.js` to show
  anything, so the preview and a no-script visitor see nothing.

- **INV-5** — A `script` piece's `code` reaches the published page verbatim and
  is never interpreted by Pressless; the preview leaves it inert.
  *Test:* `tests/test_builder.py::test_a_user_script_is_published_verbatim`.
  *Breaks when:* the Builder escapes, rewrites or drops the user's code.

- **INV-6** — `section_html` refuses a piece with a malformed field — a
  `countdown` whose `to` is not an ISO date-time, a `slideshow` or `questions`
  with no parts — and writes nothing.
  *Test:* `tests/test_blocks.py::test_a_malformed_piece_is_refused`.
  *Breaks when:* a bad field is written into the page rather than refused.

## 6. Failure modes

| What goes wrong | What happens |
|---|---|
| A countdown's target is not an ISO date-time | `section_html` refuses it; the save is refused and nothing is written (§ 4.1) |
| A page carries a piece but `pieces.js` is missing | the static fallback shows; nothing behaves (§ 4.1) |
| The user's script is broken | it is the user's own site's concern; Pressless neither runs nor checks it (§ 4.4) |
| A piece sits where its placement set forbids | refused as an out-of-place section is today (PRESS-0215 § 4.3) |

## 7. Tests

INV-1, INV-4 and INV-6 in `tests/test_blocks.py`; INV-2 in
`tests/test_page_editor.py`; INV-3 and INV-5 in `tests/test_builder.py`. Each
is seen failing first against the code before this item. The pieces' behaviour
on the published site is checked in Chrome by
`scripts/by-hand-browser-checks.py`, and in Firefox and Edge by hand.

## 8. Alternatives considered (and rejected)

- **One generic "piece" code section.** Rejected: the visual editor could not
  offer structured settings per piece, which is the point of a ready-made
  list; a code section is already available for hand-written HTML.
- **Running the pieces in the preview.** Rejected: it needs `allow-scripts`,
  which with `allow-same-origin` defeats the sandbox and lets a `script` piece
  reach the Face's endpoints (PRESS-0266). The static fallback is enough to
  edit by.
- **Fetching a piece's behaviour from a CDN.** Rejected: the pieces must need
  no outside service (the user, 2026-10-02); `pieces.js` ships with Pressless.

## 9. Out of scope

- A library of pieces beyond the five — deferred; not yet queued.
- Letting the user's own script run in the preview — never; it is the security
  boundary this item keeps (§ 4.2).
- Styling controls for a piece beyond the page's own look — deferred.

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | `tests/test_blocks.py::test_a_piece_round_trips` |
| INV-2 | `tests/test_page_editor.py::test_the_piece_preview_runs_no_script` |
| INV-3 | `tests/test_builder.py::test_a_page_with_no_piece_is_unchanged` |
| INV-4 | `tests/test_blocks.py::test_each_piece_has_a_fallback` |
| INV-5 | `tests/test_builder.py::test_a_user_script_is_published_verbatim` |
| INV-6 | `tests/test_blocks.py::test_a_malformed_piece_is_refused` |
| § 4.3 the behaviour in a browser | **nothing** in CI — `scripts/by-hand-browser-checks.py`, by hand |

## 11. Cross-doc impact

Landed with the code, each recording what the build settles under this spec:

- `docs/specs/PRESS-0215-blocks.md`: § 4.1 and § 4.4 annotated — the new kinds
  join `KINDS`, each with its writer, reader and form.
- `docs/specs/PRESS-0260-visual-editor.md`: § 4.3 annotated — the panel offers
  the pieces and shows each piece's settings.
- `CHANGELOG.md`: one entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0217-interactive-pieces-loop-log.md`.

## 13. Resource cost

No new dependency. `pieces.js` is one packaged asset, linked only on a page
that uses a piece. A save reads and writes one file and builds one preview, as
today.

## 14. As built (2026-10-14)

What the build settled, recorded rather than decided here:

- **`pieces.js` is published at `look/pieces.js`**, not `assets/pieces.js`
  (§ 3 decision 4): the Builder never writes under `assets/` (PRESS-0008 § 3
  decision 3). Its text is `blocks.PIECES_SCRIPT`, beside the writers whose
  classes it reads, so `builder.py`'s import allowlist (PRESS-0008 INV-11) is
  unchanged.
- **A preview never carries `pieces.js`**, neither the link nor the file, as a
  preview never carries the counting code. § 4.3's "served under `/preview/`"
  does not arise, and a preview page opened outside its frame runs no piece.
  `tests/test_builder.py::test_a_preview_never_carries_pieces_js` holds it.
- **A piece in the header or footer** links `pieces.js` from every page the
  furniture is filled into, the journal's pages included.
- **`top` holds its words in a `label` field**, so they survive a change of
  the app's language; the editor fills it with its own words when the piece
  is added.
- **Each question is a part whose first section is a text section**, the
  question, and whose others are its answer: a `dt` holding the first and a
  `dd` holding the rest. An answer holds no section that holds others.
- **A `script` section is refused where its code holds `</script` or
  `<!--`**: either changes where a browser ends the element, so the code
  could not reach the page as written.
- **The editor shows a `script` section's code in the frame**, by a style the
  editor adds there, so it can be picked; the sandbox keeps it from running.
