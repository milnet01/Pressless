# PRESS-0007 — Import: twelve years carried across, once, with nothing lost

**Status:** accepted (2026-09-11). Two cold-eyes loops, both folded in, nothing deferred — the run reached the spec cap of 2. A calm cap: three of loop 2's eight findings landed on text loop 1 wrote. Built only after PRESS-0004's link and quote marks.
**Kind:** implement.
**Source:** ROADMAP PRESS-0007 (`docs/design.md` § The parts, rule 9, *What
Import brings across*).

**Blocked by:** PRESS-0005 and PRESS-0006, shipped; PRESS-0004 §3 decision
4's link and quote marks, specified and built first; PRESS-0008 for the
fixed pages and furniture only (§3 decision 10).
**Blocker for:** PRESS-0008's conformance run, which needs a Store to build.

**Layman:** A one-time job that turns his WordPress entries, their comments
and their photographs into Pressless's own files — and carries everything,
because it only ever runs once.

## 1. Goal

After this ships, the maintainer can run one command over the WordPress
export and the photograph originals and get a Pressless-data folder holding
every entry, draft, comment and photograph, in the Store's own files. The
writer receives that folder; nothing in his copy of Pressless runs Import.

## 2. Problem

1. **Nothing turns the archive into Store files.** The Store, Marks and the
   comments shape exist and have never been handed the archive's contents.
2. **Rule 9 makes every loss permanent.** Anything Import declines to carry
   is outside Pressless for good (`docs/design.md` *What Import brings
   across*).
3. **Some bodies are WordPress HTML**, and an entry is never HTML
   (ADR-0001, design rule 6). PRESS-0004 §9 leaves what Import writes for
   them to this item.
4. **The archive breaks two Store rules as it stands.** One slug is wanted
   by a published entry and a draft (PRESS-0005 §3 decision 5), and two
   photographs share one file name while the Store keeps them in one
   folder (PRESS-0006 §4.3).

## 3. Scope decisions (agreed with the user)

1. **The maintainer runs Import once, on the machine that holds the export,
   the photograph originals and the live site's files, and hands the writer
   the folder it made.** Decided by the user 2026-09-11; `docs/design.md`
   rule 9 records it.
2. **The WordPress-HTML bodies are converted into marks, the link and quote
   marks included.** Decided by the user 2026-09-11; PRESS-0004 §3 decision
   4 adds the two marks.
3. **Everything is carried** (`docs/design.md` *What Import brings
   across*): published posts as published entries, drafts and private posts
   as drafts, trashed posts never. Daily Prompt entries keep their tag.
4. **(decided here) The WordPress pages come across as drafts.** They are
   his writing, and the rule is to carry it. The live site's own pages
   replace them on the site (decision 10).
5. **(decided here) Where two items want one slug, the one with a live
   address keeps it.** A published post outranks a draft or private post,
   which outranks a WordPress page. Each item that loses takes
   `<slug>-<post id>`. A published address is a breaking surface
   (PRESS-0005 §3 decision 4); a draft has no address yet.
6. **(decided here) A photograph keeps its own file name in the Store.**
   Where two share one, each takes its upload year and month in front,
   `YYYY-MM-<name>`. PRESS-0016 owns how an entry names a photograph from
   here on, and inherits these names.
7. **(decided here) A picture link is dropped and its picture kept.** The
   archive wraps pictures in a link to their own full-size file, which is
   an original, and originals are never published (`docs/design.md` § Where
   everything sits on disk).
8. **(decided here) Import makes a folder that does not exist yet, whole or
   not at all.** A second run can never write over the first, and a run
   that fails leaves nothing behind (§4.7).
9. **(decided here) Import reports whatever it could not convert**, entry
   by entry, and the maintainer reads that report before handing the folder
   over. A conversion that drops something silently is the loss rule 9
   forbids.
10. **(decided here) The fixed pages and the page furniture are carried
    once PRESS-0008 settles how a hand-written page is parted from the
    header and footer written into it.** PRESS-0006 gives both their Store
    shape. The furniture comes from today's generator's templates, and a
    fixed page is one the site serves as a page, never an untouchable file
    (`docs/design.md` *What Import brings across*). `run` then gains the
    live site's folder and `Report` a field for them. **The maintainer runs
    Import once, after both halves are built**, since decision 8 forbids
    adding to a folder already made.
11. **(decided here) Import is a package of its own, `pressless_import`,
    beside `pressless` and outside it.** Nothing in Pressless imports it, so
    it can be deleted without changing what the others do (rule 9), and the
    Face's walk of `pressless`'s failure types (PRESS-0011 INV-1) never
    meets it. The packaged program does not carry it.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless_import/__init__.py

@dataclass(frozen=True)
class Dropped:
    slug: str          # the entry it happened in, by its Store slug
    what: str          # the construct, e.g. "a <table>", "styled asterisks"

@dataclass(frozen=True)
class Report:
    published: int
    drafts: int
    comments: int
    photographs: int
    renamed_slugs: tuple[tuple[str, str], ...]        # (wanted, given)
    renamed_photographs: tuple[tuple[str, str], ...]  # (upload path, Store name)
    dropped: tuple[Dropped, ...]

class ImportStopped(Exception): ...   # INTO was not made

Lookup = Callable[[str], str | None]   # to a photograph's Store name, or None

def resolve_slug(raw: str, post_id: str) -> str: ...
def is_markup(body: str) -> bool: ...
def convert(body: str, picture_by_address: Lookup,
            picture_by_id: Lookup) -> tuple[str, tuple[str, ...]]: ...
def visible_lines(markup: str) -> tuple[str, ...]: ...
def run(export: Path, originals: Path, into: Path) -> Report: ...
def main(argv: list[str]) -> int: ...   # python -m pressless_import EXPORT ORIGINALS INTO
```

`convert` takes one markup body and returns the marked text and what it
dropped. `picture_by_address` resolves an `<img>`'s address, and
`picture_by_id` a gallery's attachment id. `convert` and `visible_lines`
touch no disk.

`main` prints the report and exits 0, or prints why it stopped and exits 1.
Its words never name a full filesystem path (`docs/design.md` § Logging):
a file is named by its own name, or by its upload path `YYYY/MM/name`,
which is a place in the export rather than on his machine.

### 4.2 Reading the export

- The export's `wp:` namespace is read off the document, not pinned. WXR
  has shipped several.
- An item is carried where its `post_type` is `post` and its status is
  `publish`, `draft` or `private`, or its `post_type` is `page`. Every other
  item type is WordPress's own machinery and is not his writing.
- The date is `wp:post_date`, the wall clock the export carries, with no
  zone added (PRESS-0005 §4.2).
- Categories and tags are each `<category>`'s `nicename`, by its domain.
- Title, date, categories and tags become the entry header; the body,
  converted where it is markup, becomes the entry body.

### 4.3 Converting a body

**A body is markup exactly where today's generator passes it through
rather than running `wpautop()` over it** (PRESS-0004 §2): it holds
`<!-- wp:`, or a `<` followed by `p`, `div`, `img`, `a`, `blockquote`,
`figure`, `ul`, `ol`, `h1` to `h6`, `iframe`, `em` or `strong` and then a word
boundary, in any case. That is `is_markup`.

**Every other body is plain, and is written byte for byte.** It is already
the Store's format, and PRESS-0004 INV-5 proves Marks renders it as the
live site does. That holds for a plain body carrying a stray `<span>` or a
`[gallery]` shortcode too, which the live site shows as written today;
Import lists such a shortcode in the report so the maintainer can decide.

**In a markup body a newline is a space**, as it is to a browser. Only the
table's rows make a line or a paragraph.

| WordPress | Becomes |
|---|---|
| `<!-- wp:… -->` block comments | nothing |
| `<p>` | a paragraph: a blank line after it |
| `<br>` | a new line |
| `<strong>`, `<b>` | `**…**` |
| `<em>`, `<i>` | `*…*` |
| `<span style="color:#…">` with a hex colour | `{#…}…{/}` |
| `<a href="…">` to another site | `{link: …}…{/}` |
| `<a>` around a picture | the picture alone (decision 7) |
| `<img>`, and a `<figure>` holding one | `{photo: name}` on its own line; with a `<figcaption>`, `{photo: name \| caption}` |
| `[gallery ids="…"]` | one picture mark per id, in order |
| `<blockquote>`, and a pull-quote `<figure>` holding one | its lines, each beginning `> `; a line holding only `>` between its paragraphs |
| a video or embed that is not an attachment | `{link: address}address{/}` on its own line |
| a link or a video pointing at an attachment that is not a picture | its words, without the link; listed |
| `<div>` | its contents, as a paragraph of their own |
| `<h1>` to `<h6>` | its words, as a paragraph of their own; listed, since Marks has no heading |
| `<figure>` otherwise | its contents |
| a character reference such as `&nbsp;` | kept as written in text; decoded in an address before the address becomes a link's or is traced to a picture |

**A wrap mark never begins or ends with whitespace, and never crosses a
line.** For every wrap run the table emits — bold, italic, colour and link —
whitespace at either edge moves outside it, an empty run is dropped, and a
run holding a line break is closed before the break and opened again after
it. Marks forms no wrap mark whose opener is followed by whitespace, and no
mark spans a line (PRESS-0004 §4.5, INV-3). **A run both bold and italic is
written bold, and the italic is listed**: Marks forms no mark from `***`
(PRESS-0004 §4.5).

**Anything else** — an unknown tag, an attribute the table does not use, a
style that is not a hex colour, a picture or gallery id with no attachment —
keeps its words, loses its markup, and is listed in `Report.dropped`. A
picture with no attachment keeps its address as a link.

**Import checks its own work.** For each converted body it compares
`visible_lines` of the WordPress body with `visible_lines` of what
`marks.render` gives the converted body. Visible lines split at each `<br>`,
`<img>`, `<div>` and `<h1>` to `<h6>`, and at each paragraph, quotation and
figure boundary, with character references decoded, block comments removed
and whitespace inside a line collapsed. Today's generator passes a markup
body through as it is, so the body's own text is what the live site shows,
and the check needs nothing but the body.

**Three conversions change what a reader sees on purpose, and the check
allows exactly them**: a `[gallery]` shortcode's text becomes its pictures,
and a video, an embed or a picture with no attachment gains its address as a
link's words. **So does a pair of `*` in his own words**, which Marks styles
since there is no escape character (PRESS-0004 §3 decision 3). That one is
allowed only where the WordPress body's own text holds `*`, the lines match
once `*` is removed from both, and the rendered lines hold no more `*` than
the source did — so an asterisk the converter added is never taken for his.
Every difference, allowed or not, is listed in `Report.dropped`.

### 4.4 Slugs

`resolve_slug` is PRESS-0005 §3 decision 4's rule, re-homed from today's
generator: decode percent-encoding, drop marks and control characters, fold
to ASCII lower case, join the rest with hyphens, and fall back to the post
id where nothing survives. It lives here because Import is the one caller
that resolves a WordPress slug.

**A slug the Store refuses** — one of PRESS-0005 §4.2's device names — is
treated as lost, as decision 5 treats a collision. Import asks the Store's
own `path_for`, which raises `StoreError` on such a slug, and keeps no copy
of the rule.

**Collisions are resolved before anything is written.** Every carried item
is resolved, then decision 5's ranking decides who keeps a contested slug.
The winner is unchanged. Each loser takes `<slug>-<post id>`, and the pair
is recorded in `Report.renamed_slugs`.

### 4.5 Photographs

Every attachment's original is at `ORIGINALS/<YYYY>/<MM>/<name>`, the same
path WordPress uploaded it to. Import copies each one — every attachment,
videos included — byte for byte to the Store's photographs folder under
decision 6's name. It never re-encodes or resizes one: the Builder makes
the web copies (PRESS-0008).

A picture in a body is traced to its attachment by the upload path in its
address, decoded. **Only where that path names no attachment** is a
`-<width>x<height>` suffix before the extension removed and the path tried
again. Its picture mark names the Store name, so a body always names the
file it will find.

### 4.6 Comments

Every approved comment on a carried item is carried, in the export's order,
into the comments file named for that item's Store slug (PRESS-0006 §4.1).
`comment_id` fills `identifier`; a `comment_parent` of `0` becomes `""`
(PRESS-0006 §4.2). **The comment's email address and IP address are never
read into anything Import holds**, so no route can write them into the
Store (PRESS-0006 INV-4).

### 4.7 Order of work

1. Refuse unless `INTO` does not exist.
2. Read the export; resolve every slug and its collisions (§4.4).
3. Trace every picture, and check every original exists (§4.5).
4. Convert every markup body (§4.3), and build every entry and comment set.
5. Write everything into a new folder beside `INTO`, through the Store's
   own calls, and copy the originals into it.
6. Only when every write has succeeded, rename that folder to `INTO`.

**Any failure stops Import with `ImportStopped` and removes the folder of
step 5**, whether it is a missing original, an unreadable export or a
refusal the Store raises during step 5. So `INTO` appears whole or not at
all, and the Store's own refusals need no copy here (design rule 7).

### 4.8 What Import never does

- It never reaches the network. Nothing it reads is fetched.
- It never writes outside the folder of step 5 and `INTO`, and never
  changes the export or an original.
- It never reads Settings or Credentials, and never writes a settings
  file: the handed folder carries the Store alone, and setup writes
  Settings on his machine (`docs/design.md` rule 9).
- It never filters an entry out for its tag.
- It parses the export with the standard library's `xml.etree`. The export
  is the writer's own file, read on the maintainer's machine, so the
  untrusted-XML rule `ruff`'s S314 guards against does not apply; the
  archive tests already take the same exemption in `pyproject.toml`.

## 5. Invariants

- **INV-1** — Every carried item is written exactly once: a published post
  into the published folder, a draft, private post or WordPress page into
  the drafts folder, and a trashed post nowhere.
  *Test:* `tests/test_importer.py::test_every_carried_item_lands_once` —
  a small export built in the test, holding one item of each status and
  type.
  *Breaks when:* a private post is left out, a page is skipped, or a
  trashed post is carried.

- **INV-2** — A slug follows PRESS-0005 §3 decision 4's rule, and a contested
  one goes to decision 5's winner while each loser takes `<slug>-<post id>`.
  Nothing written is ever written over.
  *Test:* `tests/test_importer.py::test_a_contested_slug_goes_to_the_live_address`
  — a published post and a draft wanting one slug, and a page wanting it
  too. `tests/test_importer_archive.py::test_slugs_match_the_live_rule` —
  `resolve_slug` equals today's generator on every item of the archive.
  *Breaks when:* the draft keeps the slug and the published address moves,
  or the second write replaces the first.

- **INV-3** — A plain body is written byte for byte, and a markup body is
  never written as it came.
  *Test:* `tests/test_importer.py::test_a_plain_body_is_written_as_it_is`
  — a plain body holding `&nbsp;`, a lone `*`, a stray `<span id="…">` and a
  `[gallery ids="1"]`, which is also listed in the report; and a body
  holding `<p>` is converted.
  *Breaks when:* a plain body is run through the converter, or `is_markup`
  departs from today's generator's test.

- **INV-4** — Each row of §4.3's table produces its mark; a newline in a
  markup body produces none; and no wrap mark begins or ends with
  whitespace or crosses a line.
  *Test:* `tests/test_importer.py::test_each_construct_becomes_its_mark` —
  one fixture per row, plus `<strong> word</strong>`, `<a href="…"> x</a>`,
  `<strong>a<br>b</strong>`, `<strong><em>x</em></strong>`,
  `<div>a</div><div>b</div>`, an address holding `&amp;`, and a newline
  inside a `<p>`.
  *Breaks when:* a row is converted to something else, whitespace is left
  inside a mark or a mark crosses a line — each puts literal characters on
  the page — or a source newline becomes a line break.

- **INV-5** — For every converted body in the archive, the lines a reader
  sees are unchanged, except for the differences §4.3's check allows.
  *Test:* `tests/test_importer_archive.py::test_no_line_is_lost` — compares
  `visible_lines` before and after over the real archive, and fails on any
  difference §4.3 does not allow, whether or not the report lists it; it
  prints how many bodies it compared and each allowed difference.
  *Breaks when:* a row drops its words, a quotation loses a line, a caption
  is lost, a newline in markup becomes a line break, a `<div>`'s line is
  merged into the next, or an asterisk the converter added is taken for
  his.

- **INV-6** — Every original is copied byte for byte under decision 6's
  name, and every picture mark names a file in the photographs folder.
  *Test:* `tests/test_importer.py::test_photographs_arrive_under_their_names`
  — two attachments sharing a file name in different months, and a body
  naming each. `tests/test_importer_archive.py::test_every_picture_resolves`.
  *Breaks when:* two same-named originals are written to one file, or a
  body keeps the WordPress address.

- **INV-7** — Every approved comment on a carried item is in its entry's
  comments file, with `0` read as top level, and no commenter's email
  address or IP address reaches any file Import writes.
  *Test:* `tests/test_importer.py::test_comments_follow_their_entry` —
  a reply, a top-level comment and a contact address in the fixture.
  `tests/test_importer_archive.py::test_no_address_reaches_the_folder`.
  *Breaks when:* the parent `0` is carried through and the set is refused,
  or a comment follows the WordPress id rather than the Store slug.

- **INV-8** — `INTO` appears whole or not at all.
  *Test:* `tests/test_importer.py::test_nothing_is_made_when_it_stops` — an
  existing `INTO`, a missing original, and a reply whose parent the export
  does not carry, which the Store refuses during writing; each raises
  `ImportStopped`, leaves no `INTO` where there was none, changes an
  existing one not at all, and leaves no folder of step 5 behind.
  *Breaks when:* entries are written into `INTO` directly, or the folder of
  step 5 survives a failure.

- **INV-9** — What Import could not convert is in `Report.dropped`, by entry.
  *Test:* `tests/test_importer.py::test_what_is_dropped_is_reported` — a
  markup body holding a `<table>` and a `<p style="font-size:2em">`.
  *Breaks when:* an unknown tag is removed without a record.

- **INV-10** — Import reaches no network.
  *Test:* `tests/test_importer.py::test_import_reaches_no_network` — walks
  every module of `pressless_import` for its imports, as PRESS-0004 INV-7's
  test does, and refuses `socket`, `http`, `urllib.request` and `ssl`.
  *Breaks when:* a picture is fetched from the old site.

## 6. Failure modes

| What happens | What Import does |
|---|---|
| `INTO` exists | Stops before reading anything |
| The export cannot be read, or is not a WXR export | Stops; nothing is made |
| An original is missing | Stops, naming the file by its own name; nothing is made |
| The Store refuses a write | Stops, naming the entry by its slug; the folder of step 5 is removed |
| A slug is contested | Decision 5; recorded in the report |
| A slug the Store refuses | Treated as contested; recorded |
| A construct the table does not know | Words kept, markup dropped, recorded |
| A picture with no attachment | Kept as a link; recorded |
| A shortcode in a plain body | Kept as written; recorded |
| A converted body whose lines differ | Recorded; the archive run fails on it unless §4.3's check allows the difference |

## 7. Tests

`tests/test_importer.py` — pure, in CI, over small exports and originals
built in the test. It carries the tests §5 names for INV-1, INV-2, INV-3,
INV-4, INV-6, INV-7, INV-8, INV-9 and INV-10.

`tests/test_importer_archive.py` — marked `archive`, over the real export
and the maintainer's originals. It needs `PRESSLESS_ARCHIVE`, a
`PRESSLESS_ORIGINALS` folder, and today's generator for INV-2's slug rule.
Absence skips; anything present and unusable fails, as the other archive
tests do (CLAUDE.md). It carries INV-2's, INV-5's, INV-6's and INV-7's
archive tests, runs the whole import into a temporary folder, and prints
what it carried and the report.

Each test is seen failing against a stub before the code exists, then
mutation-probed once it lands.

## 8. Alternatives considered (and rejected)

- **Setup runs Import on the writer's machine.** The originals exist only on
  the maintainer's; rejected by the user.
- **Fetching the photographs from WordPress.** Needs the old site still up,
  and puts network code in a part rule 9 would otherwise make trivial.
- **Keeping the HTML bodies as HTML.** Breaks ADR-0001; rejected by the
  user.
- **Converting only what Marks had.** Loses every link and quote for good.
- **Filtering the Daily Prompt entries at Import.** `docs/design.md` rejects
  it: filtering at build keeps his decision reversible.
- **Numbering the second of two same-named photographs.** Which one is
  "second" depends on export order; the upload month is a fact of each file.
- **Checking the Store's refusals before writing.** The rules are the
  Store's own and private; a copy here would drift, and design rule 7
  forbids reaching inside. Writing into a folder that is renamed only on
  success gets the same result with the Store's own calls.
- **Import inside `pressless`.** The Face's walk would then need a sentence
  for `ImportStopped`, and the Face would depend on Import against rule 9.

## 9. Out of scope

- The web copies of the photographs — PRESS-0008.
- How an entry names a photograph after Import — PRESS-0016.
- The untouchable list — setup and the Face (PRESS-0021).
- Editing what was imported — PRESS-0012.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_importer.py::test_every_carried_item_lands_once` |
| INV-2 | `tests/test_importer.py::test_a_contested_slug_goes_to_the_live_address`, `tests/test_importer_archive.py::test_slugs_match_the_live_rule` |
| INV-3 | `tests/test_importer.py::test_a_plain_body_is_written_as_it_is` |
| INV-4 | `tests/test_importer.py::test_each_construct_becomes_its_mark` |
| INV-5 | `tests/test_importer_archive.py::test_no_line_is_lost` — **skipped in CI**; it runs where the archive and the originals are |
| INV-6 | `tests/test_importer.py::test_photographs_arrive_under_their_names`, `tests/test_importer_archive.py::test_every_picture_resolves` |
| INV-7 | `tests/test_importer.py::test_comments_follow_their_entry`, `tests/test_importer_archive.py::test_no_address_reaches_the_folder` |
| INV-8 | `tests/test_importer.py::test_nothing_is_made_when_it_stops` |
| INV-9 | `tests/test_importer.py::test_what_is_dropped_is_reported` |
| INV-10 | `tests/test_importer.py::test_import_reaches_no_network` |
| That the maintainer reads the report before handing the folder over | **nothing** — a person does it |
| The fixed pages and furniture (decision 10) | **nothing yet** — not built until PRESS-0008 states their split |

## 11. Cross-doc impact

- `docs/design.md` — rule 9 and *What Import brings across* amended
  2026-09-11 for decision 1, and gated.
- PRESS-0004 — §3 decision 4 adds the link and quote marks, and gated.
- PRESS-0005 §3 decision 5 — the collision it records is resolved by
  decision 5 here.
- PRESS-0006 — Import writes the comments and photographs it shapes.
- PRESS-0011 — no change: Import is outside `pressless`, so the Face's
  INV-1 walk never meets `ImportStopped` (decision 11).
- PRESS-0016 — inherits decision 6's photograph names.
- PRESS-0021 — setup no longer runs Import.
- `pyproject.toml` — S314 ignored for `src/pressless_import/`, with §4.8's
  reason; `setuptools` finds the new package under `src/` as it finds
  `pressless`.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0007-import-loop-log.md`.

## 13. Resource cost

Runs once. It holds the export and every converted entry in memory, which is
what lets it resolve every slug before writing, and copies the originals
once. It keeps nothing afterwards; the folder of step 5 is renamed or
removed.
