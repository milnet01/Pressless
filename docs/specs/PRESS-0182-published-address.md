# PRESS-0182 — Changing a published entry's address, and forwarding the old one

**Status:** accepted (2026-09-29). Gated for one loop, the user's round budget; every verified finding fixed, none left in the tail.
**Kind:** feature.
**Source:** ROADMAP PRESS-0182 (split from PRESS-0128 by the user
2026-09-29; the forwarding decision 2026-09-27; the scope decisions
2026-09-29).

**Amends:** PRESS-0012 (§4.4, §4.9, §4.11), PRESS-0008 (§4.2, §4.3, §4.7,
§4.9), PRESS-0005 (§4.3), PRESS-0015 (§4.4) and `docs/design.md`. §11
lists each edit.

Layman: he can change the web address of an entry already on his site,
and links people shared still reach it.

## 1. Goal

After this ships, the editor offers Change address on a published entry,
not only on a draft. He is warned first. The entry moves to its new
address in the Store at once, and his site follows at the next press.
From then on, the old address holds a small page that sends readers to
the new one, through every later press, rename and undo.

## 2. Problem

1. **Only a draft's address can change.** `editor._address` answers
   *"Only a draft's address can be changed here."* for a published entry,
   and PRESS-0012 §4.11 says the editor never changes one.
2. **A rename would break every shared link.** An entry's page is
   `blog/YYYY/MM/DD/<slug>/index.html` (`builder._entry_path`). A new slug
   is a new page, and the old page leaves the site at the next press
   because the Publisher removes what the Builder no longer produces.
3. **Nothing lasting records an old address.** `docs/design.md` § What may
   depend on what says a rename bins the old file. The bin is not
   read by the Builder (PRESS-0008 §4.2), so nothing remembers the old
   address after one press.
4. **The site cannot redirect at the server.** It is a GitHub Pages site
   built into static files. Google recommends a server-side redirect and
   treats an instant `meta refresh` as a permanent one. Source:
   <https://developers.google.com/search/docs/crawling-indexing/301-redirects>

## 3. Scope decisions (agreed with the user)

1. **Warn first, then forward the old address.** The user, 2026-09-27.
2. **The Store changes at once; the site at the next press.** The user,
   2026-09-29. This is how PRESS-0128's Throw this entry away works.
3. **An entry with a working copy cannot change address.** He presses or
   bins the proof first. The user, 2026-09-29.
4. **A forwarded address stays reserved.** No other entry takes it. The
   entry it forwards to may move back to it. The user, 2026-09-29.
5. **Throwing an entry away removes its forwards.** Its old addresses
   stop at the next press, as its own does. The user, 2026-09-29.
6. **One review round.** The user, 2026-09-29.

## 4. Design

### 4.1 The forwards file, in the Store

```python
# src/pressless/store.py — added

FORWARDS_FOLDER = "forwards"         # in Pressless's own folder, beside published/
FORWARDS_FILE = "forwards.json"     # the one file in it

def forwards_path_for(folder: Path) -> Path: ...
def read_forwards(folder: Path) -> dict[str, str]: ...
def write_forwards(folder: Path, forwards: dict[str, str]) -> Path: ...
```

**The file maps an old address to the address it forwards to**, both
slugs:

```json
{
  "old-seaside": "seaside"
}
```

**`read_forwards`** returns `{}` where the file is absent. It raises
`StoreError` naming the file where it is not valid JSON, is not an
object, holds a key or value `path_for` refuses, or maps a slug to
itself. The writer may open the file (S3), and every key becomes a
folder name on his site, so a slug is checked here as `path_for`
checks one.

**`write_forwards`** writes the object with sorted keys, two-space
indent, UTF-8, LF and a final newline, through the Store's atomic write.
An empty mapping is written as `{}`.

**The file is not an entry.** `exists` and `list_slugs` do not see it.
`FORWARDS_FOLDER` joins `_BINNABLE`, so `move_to_bin` takes the file, as
undo needs (§4.4). Keeping a forwarded address reserved is a rule
the editor keeps (§4.2), as Store-wide uniqueness already is.

### 4.2 The editor

**`free_address`** also skips a candidate that is a key of
`read_forwards(folder)`, read once before the first candidate, so its
`StoreError` stops the search rather than being skipped as a refused
name. This reaches every caller: a new entry, a
working copy's address, and undo's kept draft.

**`POST /address`** keeps PRESS-0012 §4.9's fields and adds `draft`
(`1` or `0`). Under the lock:

1. **Refused, writing nothing**, with a hint beside the field:
   - a working copy: *"A proof's address cannot be changed."*
   - a published entry that has a working copy: *"Press your changes to
     your site, or bin this proof, then change the address."*
   - an address `store.exists` refuses with `StoreError`, or another
     entry holds: today's hints.
   - an address that is a forwards key whose value is not `slug`:
     *"Another entry's old address forwards from there."*

   The same address as `slug` writes nothing and gives no hint.
2. A digest that differs from `base` raises `ChangedElsewhere`, answered
   as PRESS-0012 §4.8's failures are.
3. **Write the entry at the new address**, in the folder it came from.
4. **Rewrite the forwards:** remove the key equal to the new address,
   and change every value equal to `slug` to the new address. For a
   published entry, also add `slug` → the new address. So a chain always
   points at the newest address, moving back leaves no loop, and a draft
   an undo demoted takes its forwards with it.
5. **Move its comments file**, as PRESS-0012 §4.9 step 4 does.
6. **Bin the old entry file.**

The reply is PRESS-0012 §4.9's JSON, with `draft` as the entry's.

**The order means an interruption leaves two copies, never none.** After
step 3 or 4, both files are published. The Builder then builds the old
address as the entry it still is, not as a forward (§4.3).

**The page.** A published entry's page shows the Address field and its
button while `data-draft` is `0`. A working copy's page never does. When
the first save turns the page into a working copy's editor, the field and
button are hidden in `adopt()`. On a published entry the button asks
first, through `window.confirm`:

> Change this entry's address? It moves now in your Pressless-data folder,
> and on your site the next time you press to site. Links to the old
> address will still reach it.

A draft is not asked.

**Throw this entry away** (PRESS-0128) gains one step whenever it bins a
published entry — `named` in `editor._throw`, which a working copy's
page reaches too. After that file is binned, every forwards pair whose
value is `named` is removed. A throw that bins only an ordinary draft
does not touch the forwards.

### 4.3 The Builder

`build` reads `store.read_forwards(folder)` once. For each pair, sorted
by key, it writes a forwarding page, except where:

- the value is not an entry `build` writes a page for, or is filtered
  (PRESS-0008 §4.2);
- the key is the slug of an entry `build` writes a page for. The entry's
  own page wins.

"An entry `build` writes a page for" is `read_entries`' map, `change`
included.

The page goes at `_entry_path` of the target with the key in place of its
slug: `blog/YYYY/MM/DD/<old>/index.html`, dated by the target. The target
is the sibling folder `../<new>/index.html`.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="canonical" href="{site_address}/{entry path}/index.html">
<meta http-equiv="refresh" content="0; url=../{new}/index.html">
</head>
<body>
<p>This entry has moved to <a href="../{new}/index.html">{title}</a>.</p>
</body>
</html>
```

`{title}` is the target's heading as its own page writes it, `entry.title
or _long_date(entry.date)`, through `html.escape`. `{site_address}` is `settings.site_address` without a
trailing `/`, as the sitemap joins it.

A forwarding page is in no listing and no sitemap line.
It is under `blog/`, so it stays inside `ROOT_OUTPUT`.

**`content/forwards/forwards.json`** is written byte for byte whenever the Store
holds the file, beside the other `content/` files (PRESS-0008 §4.7).

### 4.4 Undo

`undo._read` also recognises `content/forwards/forwards.json`. It reads
it with `store.read_forwards(fetch / "content")`, whose layout matches
the Store's.

Reconciling (PRESS-0015 §4.4): where the fetched state holds the file and
it differs from the Store's, the Store's goes to the bin and the fetched
one is written, with a reversal like every other kind. Where the fetched
state does not hold it, the Store's is kept, as for every other kind.

A forward left pointing at an entry the undo demoted is not built
(§4.3), and it still reserves its address.

## 5. Invariants

- **INV-1** — `read_forwards` returns exactly what `write_forwards` wrote,
  and refuses a file whose key or value is not a legal slug, or maps a
  slug to itself.
  *Test:* `tests/test_store.py::test_forwards_round_trip` and
  `test_forwards_refuse_an_illegal_slug` (a key `../x`, a value `Con`, a
  pair `a` → `a`).
  *Breaks when:* a hand-edited key such as `../x` reaches the Builder as a
  folder name.

- **INV-2** — Changing a published entry's address from `a` to `b` leaves
  `published/b.txt` with the entry's fields, `a`'s file and comments file
  in the bin, `b`'s comments file equal to `a`'s, and forwards `{a: b}`.
  *Test:* `tests/test_editor.py::test_a_published_address_change_forwards_the_old_one`.
  *Breaks when:* step 4 is skipped, or the entry is written as a draft.

- **INV-3** — Moving `a` to `b` and then `b` to `c` gives forwards
  `{a: c, b: c}`. Where `b` is a draft, the second move gives `{a: c}`.
  *Test:* `tests/test_editor.py::test_a_second_move_retargets_the_first_forward`.
  *Breaks when:* step 4 adds the new pair without retargeting, leaving
  `{a: b, b: c}`, or skips drafts, leaving `a` aimed at a free `b`.

- **INV-4** — Moving `a` to `b` and back to `a` gives forwards `{b: a}`.
  *Test:* `tests/test_editor.py::test_moving_back_drops_the_forward_it_lands_on`.
  *Breaks when:* step 4 keeps the key equal to the new address, leaving a
  forward from `a` while `a` is the entry.

- **INV-5** — A forwarded address is refused to every entry but the one it
  forwards to. `free_address` skips it, and `/address` refuses it to
  another entry with its hint and writes nothing.
  *Test:* `tests/test_editor.py::test_a_forwarded_address_stays_reserved`.
  With forwards `{a: b}` and no entry at `a`, `free_address(folder, "a")`
  answers `a-2`, which only the forward can cause; a draft `c` asking for
  `a` gets the hint; `b` asking for `a` is moved.
  *Breaks when:* `free_address` consults `store.exists` alone.

- **INV-6** — A published entry with a working copy, and a working copy
  itself, are refused with their hints, and nothing is written.
  *Test:* `tests/test_editor.py::test_an_address_change_waits_for_the_proof`.
  *Breaks when:* the refusal checks only `_replaced` of the named file, so
  the published entry is moved and its working copy's `Replaces` names
  nothing.

- **INV-7** — Throwing away a published entry `b` removes every forwards
  pair whose value is `b`, and keeps the rest.
  *Test:* `tests/test_editor.py::test_throwing_an_entry_away_removes_its_forwards`,
  with forwards `{a: b, x: y}` giving `{x: y}`, once from `b`'s page and
  once from its working copy's.
  *Breaks when:* the step keys on the `draft` field, so a throw from the
  proof's page bins `b` and leaves `a` reserved.

- **INV-8** — `build` writes a forwarding page at the old address, dated by
  the target, whose refresh and link reach the target's page, and adds it
  to no listing or sitemap line.
  *Test:* `tests/test_builder.py::test_a_forward_is_built_beside_its_entry`.
  *Breaks when:* the page goes under the build's date, or the sitemap
  lists the old address.

- **INV-9** — `build` writes no forwarding page where the target is not a
  published unfiltered entry, or where the old address is a published
  entry's.
  *Test:* `tests/test_builder.py::test_a_forward_to_nothing_is_not_built`
  and `test_an_entry_wins_over_a_forward_at_its_address`.
  *Breaks when:* a forward overwrites a published entry's page, or links
  to a page that was never built.

- **INV-10** — `content/forwards/forwards.json` holds the Store's file byte for
  byte, and is absent where the Store has none.
  *Test:* `tests/test_builder.py::test_content_carries_the_forwards`.
  *Breaks when:* the Builder re-serialises the mapping.

- **INV-11** — An undo whose fetched state holds
  `content/forwards/forwards.json`
  leaves the Store's forwards equal to it, with the replaced file in the
  bin. One whose fetched state has none keeps the Store's.
  *Test:* `tests/test_undo.py::test_undo_restores_the_forwards` and
  `test_undo_keeps_forwards_the_fetched_state_lacks`.
  *Breaks when:* `_read` skips the `forwards` kind, as it skips every
  kind it does not name today.

- **INV-12** — The Address field shows on a published entry with no
  proof, hides once a save makes a proof, and a change on a published
  entry asks first.
  *Test:* rows in `scripts/by-hand-browser-checks.py`, in headless Chrome.
  *Breaks when:* `adopt()` does not hide the field, so a proof's page
  offers a change §4.2 refuses.

## 6. Failure modes

| What happens | Result |
|---|---|
| Interrupted after step 3 or 4 | two published copies; the next press builds both as entries; no forward page at the old address |
| Interrupted after step 5 | the same, and the comments file in both places |
| `forwards.json` unreadable or refused | `StoreError` naming it; the address change, the throw and the build stop, and it is shown through `Face.fail` |
| He edits `forwards.json` by hand to a slug no entry holds | no page is built for that pair (§4.3); the address stays reserved |
| The target's `Date` is edited by hand | the forwarding page moves with it, and the old dated address stops |

## 7. Tests

`tests/test_store.py` gains INV-1's. `tests/test_editor.py` gains INV-2,
INV-3, INV-4, INV-5, INV-6 and INV-7's. `tests/test_builder.py` gains
INV-8, INV-9 and INV-10's.
`tests/test_undo.py` gains INV-11's. `scripts/by-hand-browser-checks.py`
gains INV-12's rows. Each test is seen to fail before the code it locks
exists. The Windows hand checks before 0.5.1 gain one row: change a
published entry's address and press.

## 8. Alternatives considered (and rejected)

- **Hold the new address until the press, with the working copy.** Keeps
  the published file untouched until a press, as edits are. Rejected by
  the user (§3 decision 2): the press step would have to learn to rename,
  and Throw already acts at once.
- **Forwards in Settings.** Settings holds what is true of the machine,
  and undo never reaches it, so an undone rename would keep its forward.
- **A forwards key per entry, as a header field.** A binned or renamed
  entry would carry its old addresses away, and a new entry could not see
  that an address is reserved without reading every file.
- **A delayed refresh with a notice.** Google reads a delayed refresh as
  temporary (§2), so the old address would stay in search results.

## 9. Out of scope

- **Renaming a fixed page.** PRESS-0014 does not rename them.
- **Insights joining an old address's history to the new one.** Deferred;
  not yet queued.
- **A forward from an address that was never published.** A draft's
  rename writes no forward, since nothing was shared.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_store.py::test_forwards_round_trip`, `test_forwards_refuse_an_illegal_slug` |
| INV-2 | `tests/test_editor.py::test_a_published_address_change_forwards_the_old_one` |
| INV-3 | `tests/test_editor.py::test_a_second_move_retargets_the_first_forward` |
| INV-4 | `tests/test_editor.py::test_moving_back_drops_the_forward_it_lands_on` |
| INV-5 | `tests/test_editor.py::test_a_forwarded_address_stays_reserved` |
| INV-6 | `tests/test_editor.py::test_an_address_change_waits_for_the_proof` |
| INV-7 | `tests/test_editor.py::test_throwing_an_entry_away_removes_its_forwards` |
| INV-8 | `tests/test_builder.py::test_a_forward_is_built_beside_its_entry` |
| INV-9 | `tests/test_builder.py::test_a_forward_to_nothing_is_not_built`, `test_an_entry_wins_over_a_forward_at_its_address` |
| INV-10 | `tests/test_builder.py::test_content_carries_the_forwards` |
| INV-11 | `tests/test_undo.py::test_undo_restores_the_forwards`, `test_undo_keeps_forwards_the_fetched_state_lacks` |
| INV-12 | **Partial:** `scripts/by-hand-browser-checks.py`, run by hand. CI does not run it |
| §4.2's interruption order | **nothing** — no test interrupts between steps; the order is read in review |
| That a browser follows the refresh on GitHub Pages | **Partial:** the Windows hand check (§7), once, before release |

## 11. Cross-doc impact

The new direction is gated in this spec; each edit below is a pointer to
it.

- **PRESS-0012** — §4.4's `/address` row reads *"changes an entry's
  address (§4.9; PRESS-0182)"*. §4.9 gains a first line: a published
  entry's change is PRESS-0182 §4.2. §4.11's bullets *"never writes into
  `published/`"* and *"never changes a published entry's address"* gain
  *"except PRESS-0182's address change"*.
- **PRESS-0008** — §4.2's *"Nothing else is read"* names
  `store.read_forwards`. §4.3's table gains the forwarding page row.
  §4.7's list gains `content/forwards/forwards.json`. §4.9 says forwarding pages
  are not listed. Each points at PRESS-0182 §4.3.
- **PRESS-0005** — §4.3's layout gains `forwards/forwards.json`, pointing at
  PRESS-0182 §4.1.
- **PRESS-0015** — §4.4 gains one sentence: the forwards file is
  reconciled like the other kinds, PRESS-0182 §4.4.
- **`docs/design.md`** — § What may depend on what: *"Renaming an
  entry's slug writes the new file and moves the old one to the bin"*
  gains *"and, for a published entry, leaves a page at the old address
  that forwards to the new one (PRESS-0182)"*.
- `CHANGELOG.md` — an entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0182-published-address-loop-log.md`.
