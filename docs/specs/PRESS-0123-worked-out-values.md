# PRESS-0123 — A mark carrying a value worked out when he publishes

**Status:** draft (2026-09-29).
**Kind:** feature.
**Source:** ROADMAP PRESS-0123 (asked for 2026-09-17; the calculation
menu and the publish-time rule decided 2026-09-17 and 2026-09-27; the
first calculation and the spelling decided 2026-09-29).

**Amends:** PRESS-0004 (§4.1, §4.2, §4.3, §4.5), PRESS-0008 (§4.1, §4.3,
INV-6), PRESS-0012 (§4.2) and PRESS-0014 (§4.1). §11 lists each edit.

Layman: he can type something like "years since" a date into an entry,
and the published page shows the number worked out for him.

## 1. Goal

After this ships, an entry can hold `{years_since: 2010-01-01}`. The page
built from it shows how many whole years have passed since that date,
as plain text. The preview shows the same number the publish writes.

## 2. Problem

Some numbers on the site move with time, such as how long something has
been going. Today he edits each one by hand when it changes, and a
missed edit leaves a wrong figure on a public page.

Marks renders an entry and reads no clock: it takes text and returns
HTML (`docs/design.md` § What may depend on what, rule 3, and PRESS-0004
§1). The Builder already reads one, for the footer's year
(`src/pressless/builder.py`, `datetime.now().year`). So the date has to
come from the Builder, and Marks does the sum.

## 3. Scope decisions (agreed with the user)

1. **Ready-made calculations, not a formula language.** Each calculation
   is one row in Marks' table. (2026-09-17)
2. **Worked out when he publishes.** The page holds plain text and no
   script. A number that moves with the calendar changes only on his
   next publish; he accepted that. (2026-09-17)
3. **In his entries only.** Fixed pages and furniture are published as
   written (`docs/design.md`). (2026-09-17)
4. **The first calculation is years since a date.** Music counts join
   later, once PRESS-0080 finds how to read them. (2026-09-27,
   2026-09-29)
5. **The date is typed in the mark**, as `{years_since: 2010-01-01}`.
   Nothing is named or stored elsewhere, so no new screen and no new
   Store file. (2026-09-29)
6. **(decided here) A value that cannot be worked out shows as he typed
   it.** That is how every other malformed mark behaves (PRESS-0004 §6),
   and he sees the mistake in the preview.

## 4. Design

### 4.1 Marks

A new kind of mark, `value`: a brace mark with an argument and no
closer, found anywhere in a line. The table gains one row.

| `name` | Written | Kind | Becomes |
|---|---|---|---|
| `years_since` | `{years_since: 2010-01-01}` | value | the number of whole years from that date to `today`, as text |

- **`arg`** is `^\s*[0-9]{4}-[0-9]{2}-[0-9]{2}\s*$`, matched in full.
  `[0-9]`, not `\d`, which also matches other scripts' digits.
- **Scanning.** At each position the scanner tries the `value` rows with
  the `wrap` rows, longest `opens` first (PRESS-0004 §4.5). The argument
  ends at the next `}`, as for every brace mark. No adjacency clause
  applies. Inside `{rainbow}` it stays literal, like every mark there.
- **Structure.** A new node, `Value(mark, arg, written)`: `arg` is the
  argument with its whitespace stripped, and `written` is the mark
  exactly as typed. `Node` becomes `Text | Span | Photo | Value`.
- **The row's sum.** `Mark` gains `value: Callable[[str, date], str |
  None] | None`, `None` on every row but a `value` row. Given the
  argument and `today`, it returns the text to show, or `None` where the
  value cannot be worked out.
- **Rendering.** `to_html(doc, photo_src, today=None)` and
  `render(body, photo_src, today=None)`. For a `Value` node, `to_html`
  calls the row's `value` and escapes the result by the text rule
  (PRESS-0004 §4.6). Where that returns `None`, or `today` is `None`, it
  escapes `written` instead. The row's `render` returns its children
  unchanged, so `to_html` still branches on no mark name (PRESS-0004
  INV-6).
- **`value_text(node, today)`**, exported, returns the same text
  unescaped, for the Builder's excerpts (§4.2).

**Years since.** Whole years from the date to `today`: `today.year -
date.year`, less one where `today`'s month and day fall before the
date's. A date of 29 February therefore counts its year on 1 March in a
year with no 29 February. `None` where the argument is not a real
calendar date (`date.fromisoformat` refuses it), or where the date is
after `today`.

Marks still reads no clock. `datetime` joins its import allowlist for
the `date` type and `date.fromisoformat`; nothing in it reads the time.

### 4.2 The Builder

`build`, `preview` and `preview_html` gain `today: date | None = None`.
`None` means the computer's local date, read once when the build starts.
One build uses that one date everywhere:

- an entry page's body is `marks.render(entry.body, src, today)`;
- a listing's excerpt and an untitled entry's teaser take a `Value`'s
  text from `marks.value_text`, so a card shows the number, not the
  mark;
- the footer's year is `today.year`, replacing its own clock reads.

A fixed page, furniture, a comment and every plain-text `to_html` call
pass no `today`, so a value mark there stays as written.

The editor's preview calls `preview` with no `today`, as the publish
calls `build`, so on the same day both show the same number.

## 5. Invariants

- **INV-1** — `years_since` gives whole years from its date to `today`.
  *Test:* `tests/test_marks.py::test_years_since_counts_whole_years` —
  from 2010-06-15: today 2026-06-14 gives 15, 2026-06-15 gives 16;
  from 2020-02-29: today 2021-02-28 gives 0, 2021-03-01 gives 1.
  *Breaks when:* the sum subtracts years alone, which shows 16 on
  2026-06-14.

- **INV-2** — A value mark that cannot be worked out renders exactly as
  written, escaped.
  *Test:* `tests/test_marks.py::test_a_value_that_cannot_be_worked_out_stays_as_written`
  — `{years_since: 2023-02-30}`, a date after `today`, and a good date
  rendered with no `today`.
  *Breaks when:* a refused date renders as `0` or empty, or `to_html`
  raises for want of `today`.

- **INV-3** — Marks reads no clock.
  *Test:* `tests/test_marks.py::test_marks_is_pure` — its call walk also
  refuses `today`, `now`, `utcnow` and any call into `time`.
  *Breaks when:* the row's sum calls `date.today()` rather than using
  the `today` it is given.

- **INV-4** — One build shows one number: an entry page, its card in a
  listing and a preview of it, given the same `today`, all carry the
  same worked-out text, and none carries the mark.
  *Test:* `tests/test_builder.py::test_a_value_mark_is_worked_out_once_per_build`
  — a titled entry holding the mark, built and previewed with one
  `today`.
  *Breaks when:* `preview` or the card's excerpt is not handed `today`,
  and shows the mark as written.

- **INV-5** — A value mark in a fixed page or furniture file stays as
  written.
  *Test:* `tests/test_builder.py::test_a_value_mark_outside_an_entry_is_left_alone`.
  *Breaks when:* fixed pages start going through `marks.render`.

## 6. Failure modes

| When | What happens |
|---|---|
| Not a calendar date — `{years_since: 2023-02-30}` | Shown as written (INV-2). He sees it in the preview. |
| A date after today | Shown as written (INV-2). |
| An unknown calculation — `{months_since: …}` | Literal text, like any unknown mark (PRESS-0004 §6). |
| He publishes rarely | The number is as of his last publish (§3 decision 2). |
| A build straddles midnight | One date for the whole build (§4.2). |

## 7. Tests

`tests/test_marks.py` carries INV-1, INV-2 and INV-3;
`tests/test_builder.py` carries INV-4 and INV-5. All run in CI. The cheat sheet gains the row
from the table, which PRESS-0004 INV-6 already checks.

## 8. Alternatives considered (and rejected)

| Rejected | Why |
|---|---|
| A formula language | §3 decision 1. |
| A script working the number out in the reader's browser | §3 decision 2: no script, and it works for every reader. |
| Named values kept in the Store, used by name | §3 decision 5. A new screen and a new file for one date he types once. |
| Marks reading the clock itself | Breaks what makes Marks testable, and a preview and publish could disagree across midnight. |
| Showing `0` for a date after today | Hides a typing mistake he would otherwise see (§3 decision 6). |

## 9. Out of scope

- Music counts, and anything read from outside Pressless — PRESS-0080 and
  PRESS-0081 to PRESS-0084.
- Rebuilding the site on its own when a number changes. He publishes.
- Value marks in fixed pages or furniture (§3 decision 3).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_marks.py::test_years_since_counts_whole_years` |
| INV-2 | `tests/test_marks.py::test_a_value_that_cannot_be_worked_out_stays_as_written` |
| INV-3 | `tests/test_marks.py::test_marks_is_pure` |
| INV-4 | `tests/test_builder.py::test_a_value_mark_is_worked_out_once_per_build` |
| INV-5 | `tests/test_builder.py::test_a_value_mark_outside_an_entry_is_left_alone` |
| That the editor's preview uses the local date | **nothing** — `editor.py` passes no `today`, and no test runs a preview across midnight |

## 11. Cross-doc impact

The new direction is gated in this spec; each edit below is a pointer to
it.

- **PRESS-0004** — §4.1's signatures gain `today`, and its export list
  gains `Value` and `value_text`. §4.2's `Mark` gains `value`, `kind`
  gains `"value"`, and the table gains the `years_since` row. §4.3's
  `Node` gains `Value`. §4.5 says `value` rows are tried with `wrap`
  rows. Each points at PRESS-0123 §4.1.
- **PRESS-0008** — §4.1's `build` gains `today`. §4.3's *"the body is
  `marks.render(entry.body, photo_src)`"* gains `today`. INV-6's *"in the
  same year"* becomes *"given the same `today`"*, and its *"the clock
  below the year"* becomes *"a clock read other than `today`"*. Each
  points at PRESS-0123 §4.2.
- **PRESS-0012** — §4.2's `preview` gains `today`, pointing at PRESS-0123
  §4.2.
- **PRESS-0014** — §4.1's `preview_html` gains `today`, pointing at
  PRESS-0123 §4.2.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0123-worked-out-values-loop-log.md`.
