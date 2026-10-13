<!-- ants-spec-format: 1 -->
# PRESS-0238 — Adding and removing a paragraph in the words box

**Status:** spec draft (2026-10-13).
**Kind:** feature.
**Source:** ROADMAP PRESS-0238 (the user 2026-10-05, after the PRESS-0234
hand check; the three decisions in §3, the user 2026-10-13).

**Amends:** PRESS-0014 (§4.2 step 3, INV-3). §11 lists each edit.

Layman: a new paragraph can be started, or one deleted, straight in the
words box, without opening the page's code.

## 1. Goal

A blank line and new words in a fixed page's words box save as a new
paragraph after the one they follow. Deleting a paragraph's words saves
as that paragraph gone. Every other byte of the page stays as it was.

## 2. Problem

`page_editor.put_words` pairs each part of the box with one piece of the
page, in order. A box holding more or fewer parts than the page has
pieces raises `PiecesChanged`, which saves nothing (PRESS-0014 §4.2
step 3, INV-3). So the commonest edit after rewording, a new paragraph,
needs the code view. The user hit this on the first try in the PRESS-0234
hand check.

A piece is a run of text between two tags, not a paragraph
(`page_editor.pieces`). A paragraph holding a link is three pieces, and
a heading or a list item is one. So "add" and "remove" have to say what
they do beside headings, lists and links.

## 3. Scope decisions (agreed with the user)

1. **A spec, gated for one round.** The user, 2026-10-13: it changes a
   rule PRESS-0014 promises.
2. **A new paragraph matches what it follows.** After a paragraph, a
   paragraph; after a list item, a list item; after a heading, a plain
   paragraph. The user, 2026-10-13.
3. **Only whole blocks are deleted.** A paragraph, heading or list item
   whose text is all one piece goes when that piece's words go. A piece
   sharing its block with other text, such as the words beside a link,
   is refused. The user, 2026-10-13.
4. **(decided here) A box with the page's own count is read as today.**
   PRESS-0014 §4.2 step 4 pairs parts and pieces in order, and INV-1
   there keeps holding. Only a count that differs is aligned (§4.2).
5. **(decided here) Every refusal keeps PRESS-0014's shape.** It raises
   `PiecesChanged`, writes nothing, and the page says why in the hint.

## 4. Design

### 4.1 Blocks

**A block** is a `p`, `h1` to `h6`, or `li` element whose start tag and
matching end tag are both in the file. An end tag matches the nearest
open start tag of its name, as `HTMLParser` reports them; a start tag no
end tag matches is no block. **A piece's block** is the nearest block
holding it. A piece in no block has none.

A block **is a piece's own** where that piece is the only piece inside
it. Blocks are found in the same `HTMLParser` pass as the pieces, from
offsets into the file's text, as `_Runs` finds pieces.

### 4.2 Reading a box whose count differs

`put_words` keeps steps 1, 2 and 4 of PRESS-0014 §4.2. Where the count
of parts differs from the count of `pieces(name, html)`, step 3 becomes:

1. `difflib.SequenceMatcher(None, shown, parts, autojunk=False)`, where
   `shown` is each piece's shown form, gives the opcodes.
2. **`equal`** leaves those pieces as they are. **`replace`** with as
   many parts as pieces is step 4's edit of each, in order.
3. **`insert`** is new paragraphs after the piece before it (§4.3).
4. **`delete`** removes the blocks of those pieces (§4.4).
5. Anything else raises `PiecesChanged`: a `replace` whose two sides
   differ in length, such as one paragraph split in two.

Each change is made on the original text's offsets, last first, so one
save may hold several.

### 4.3 A new paragraph

The parts of an `insert` go after the piece before them, `P`.

- **Refused** where `P` does not exist (the box's first paragraph is
  new), where `P` has no block, or where `P` is not the last piece in
  its block.
- **Its element** is `li` where `P`'s block is an `li`, and `p`
  otherwise. Tag name only: no attribute is copied.
- **Its text** is `html.escape(part, quote=False)`, as PRESS-0014
  §4.2 step 4 writes an edit.
- **Its place** is right after the end tag of `P`'s block. Where only
  whitespace stands between the start of that block's first line and its
  start tag, each new element is written as a line ending, that
  whitespace, then the element. The line ending is the one ending the
  block's last line, else `"\n"`. Otherwise each is written straight
  after, with nothing between.

Several parts in one `insert` are written in box order.

### 4.4 A removed paragraph

Each piece of a `delete` must have a block that is its own; otherwise
the save is refused. The block goes from its start tag to its end tag,
with the whitespace before the start tag, as `menu.remove` takes a
link with the whitespace before it. A list left with no item keeps its
`ul` or `ol` tags.

**Refused also** where the box holds no paragraph at all: emptying the
whole box is more often an accident than a wish.

### 4.5 Where a change could go in two places

`SequenceMatcher` places a paragraph beside an identical one at one of
the two. Where the blocks differ, that choice changes what is written.
So an `insert` or `delete` is refused where the piece just outside it,
on either side, has the same shown form as a part it adds or a piece it
removes.

### 4.6 The words

`failure.page_editor.PiecesChanged.what` becomes *"Not saved: Pressless
could not tell where that change goes on your page."* and `.next`
becomes *"Put it back, or make it in Show me the code."*.
`script.press.paragraphs` stays: it is still true of every refusal.

## 5. Invariants

The tests are in `tests/test_page_editor.py`, over its `ABOUT` page:
an `h1` "Hello", then two `p` elements, "Tea & toast, it’s late." and
"Second one.", with CRLF endings and their own indents.

- **INV-1** — A paragraph added after a paragraph is a new `p` right
  after it, every other byte as it was.
  *Test:* `test_a_new_paragraph_follows_its_own`. `put_words` with
  `ABOUT_WORDS + "\n\nThird & last."` returns `ABOUT` with
  `"\r\n  <p>Third &amp; last.</p>"` after `<p>Second one.</p>`,
  compared as bytes.
  *Breaks when:* the words are appended to the last piece, the line
  ending or indent is not the block's own, or the text is not escaped.

- **INV-2** — A paragraph added after a heading is a `p`, and one added
  after a list item is an `li`.
  *Test:* `test_a_new_paragraph_takes_the_right_element`. After "Hello",
  the new element is `<p>`, on its own line with `h1`'s indent. On a
  page holding `<ul>\n  <li>One</li>\n</ul>`, one added after "One" is
  `\n  <li>Two</li>` inside the list.
  *Breaks when:* the heading's own tag is copied, or a list's new item
  lands after `</ul>`.

- **INV-3** — Deleting a paragraph's words removes its block and the
  whitespace before it.
  *Test:* `test_a_deleted_paragraph_takes_its_block`. A box without
  "Tea & toast, it’s late." returns `ABOUT` without
  `"\r\n      <p>Tea &amp; toast, it&#8217;s late.</p>"`.
  *Breaks when:* only the words go and an empty `<p></p>` is left.

- **INV-4** — A change that cannot be placed writes nothing.
  *Test:* `test_unplaceable_changes_are_refused`. Each raises
  `PiecesChanged` from `put_words`, and the save route answers its hint
  with no waiting copy:
  (a) deleting "now" from `<p>Go <a href="x">here</a> now</p>`;
  (b) adding a paragraph between "Go" and "here" there;
  (c) adding one after `<div>Loose</div>`;
  (d) a new first paragraph;
  (e) "Hello" split into "Hel" and "lo";
  (f) deleting one of `<p>Same</p><h2>Same</h2>`;
  (g) an empty box;
  (h) deleting "a" from `<p>a<p>b</p>`.
  Each fixture is refused by the rule its letter names alone: without
  that rule, (a) and (h) delete a block, (b) and (c) write a new one,
  (d) writes before the first, (e) writes two edits, (f) deletes one of
  two, and (g) empties the page.
  *Breaks when:* any of those rules is missing.

- **INV-5** — One save may add and remove in different places.
  *Test:* `test_one_save_adds_and_removes`. A box without "Tea & toast,
  it’s late." and with "Third." and "Fourth." after "Second one."
  returns `ABOUT` with the one block gone and the two new `p` elements
  in order.
  *Breaks when:* a later change is made on offsets an earlier one moved.

- **INV-6** — The save route and the press route read a new paragraph
  the same way.
  *Test:* `test_a_new_paragraph_saves_and_publishes`. `POST /page/save`
  with INV-1's box answers 200 with `hint` null and a waiting copy
  holding the new `p`. `POST /page/publish` with that box publishes it.
  *Breaks when:* a route still refuses a count that differs before
  `put_words` runs.

## 6. Failure modes

- **A save holding an edit beside a new or deleted paragraph** is often
  a `replace` of unequal length, and refused. The save script sends
  about a second after typing stops, so an edit has usually saved
  before the next paragraph starts.
- **A box with the page's count that both removed and added** is read
  in order, as today (§3 decision 4): the moved words land in the
  pieces after the removed one.
- **A block without its end tag**, which HTML allows for `p` and `li`,
  is no block, so adding after it or deleting it is refused.
- **A page whose structure the box cannot see**, such as a `div` of
  text, still saves edits; only adding and deleting are refused there.

## 7. Tests

Each is seen failing against code without the change.

- `tests/test_page_editor.py`: INV-1, INV-2, INV-3, INV-4, INV-5,
  INV-6.
- `tests/test_page_editor.py::test_a_changed_paragraph_count_writes_nothing`
  keeps its emptied-paragraph case and loses its added one, which now
  saves (INV-1).

How the box looks after a save is checked by hand, in a browser.

## 8. Alternatives considered (and rejected)

- **Align every box, whatever its count.** Rejected: a box rewritten
  piece for piece can align as deletes and inserts, so a reworded page
  would lose the markup inside its paragraphs. Today's reading keeps
  it, and PRESS-0014 INV-1 stays true unchanged.
- **Split a paragraph where the writer pressed Enter twice inside it.**
  Rejected: the split would have to decide which side keeps each inline
  tag, the problem PRESS-0014 §8 rejected per-block boxes over.
- **Copy the attributes of the block it follows.** Rejected: a copied
  `id` would no longer be unique, and a `class` such as a lead
  paragraph's is meant for one element.
- **Allow emptying the whole box.** Rejected: §4.4.

## 9. Out of scope

- Splitting or joining paragraphs — deferred; not yet queued.
- A new paragraph before the page's first — refused (§4.3); the code
  view does it.
- Styling a new paragraph — `docs/design.md` rules styling out of the
  words view.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_page_editor.py::test_a_new_paragraph_follows_its_own` |
| INV-2 | `tests/test_page_editor.py::test_a_new_paragraph_takes_the_right_element` |
| INV-3 | `tests/test_page_editor.py::test_a_deleted_paragraph_takes_its_block` |
| INV-4 | `tests/test_page_editor.py::test_unplaceable_changes_are_refused` |
| INV-5 | `tests/test_page_editor.py::test_one_save_adds_and_removes` |
| INV-6 | `tests/test_page_editor.py::test_a_new_paragraph_saves_and_publishes` |
| A box with the page's count is read as today | `tests/test_page_editor.py::test_words_change_only_their_own_bytes` (PRESS-0014 INV-1) |
| The new refusal words | `tests/test_face.py::test_every_failure_type_has_a_sentence` |
| The box and the preview after a save, on screen | **nothing** in CI — by hand, in a browser |

## 11. Cross-doc impact

- `docs/specs/PRESS-0014-fixed-pages.md` §4.2 step 3 and INV-3 — each
  points here for a count that differs.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0238-add-remove-paragraphs-loop-log.md`.
