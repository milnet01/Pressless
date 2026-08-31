# PRESS-0006 — The rest of the Store: fixed pages, furniture, templates and comments

**Status:** draft.
**Kind:** implement.
**Source:** ROADMAP PRESS-0006 (`docs/design.md` § What may depend on
what, § Where everything sits on disk).

**Blocked by:** PRESS-0005.
**Blocker for:** PRESS-0007, PRESS-0008, PRESS-0014, PRESS-0017.

*Layman:* his About page, the bits repeated on every page, his starting
templates and the old readers' comments all become ordinary files beside
his entries, in the same folder Pressless keeps his writing in.

## 1. Goal

After this ships the Store holds everything that shapes the site, not
only entries. Four kinds join them: the fixed pages, the page furniture
he edits once and sees everywhere, the templates a new piece starts
from, and the historical comments readers left.

Each is a file the Store reads and writes and nothing else interprets.
A fixed page and a furniture file keep the bytes he typed, which is what
lets the plain box and the code view edit the same file without fighting
(`docs/design.md` § What may depend on what, under *Where the fixed pages
live*). A comments file carries every comment Import brings, including those on
entries the Builder filters out of the site, and never an email address
or an IP address.

The photographs are here only as far as their place on disk goes.
`docs/standards/versioning-overrides.md` § The breaking surfaces makes
that place PRESS-0006's to choose; the picture mark and the web-sized
copy are PRESS-0016's. § 9 draws the line.

## 2. Problem

Three items are waiting on the shape of these files. Import (PRESS-0007)
writes all of them once, and the comments are the only part of the
archive it can never fetch again. The Builder (PRESS-0008) reads them to
build every page. The Face edits pages and furniture (PRESS-0014) and
copies a template into a new draft (PRESS-0017).

Nothing defines any of them today. The Store holds entries and nothing
else, so each of those items would otherwise invent its own answer, and
the header is the one edit that reaches every page on the site.

These files are also a breaking surface on the same footing as the entry
file: `docs/standards/versioning-overrides.md` names the on-disk format,
and the 1.0 promise is that a file written by 1.0 stays readable.

## 3. Scope decisions (agreed with the user)

Where a decision was made elsewhere this section cites it rather than
restating the reasoning. The rest were made in this spec and are marked
**(decided here)** — which means exactly that: they were taken while
writing it and have not been put to the writer. Any of them is his to
overturn, and none of the cited ones is.

1. **A fixed page and a furniture file are HTML, held verbatim, and are
   never generated from marks.** `docs/design.md` § What may depend on
   what, under *Where the fixed pages live*. The plain box rewrites the visible words in place and the code
   view edits the file entire; neither regenerates it.

2. **There is exactly one copy of the header, footer and navigation**,
   and they sit in the Store rather than in Settings because they are
   site material he edits. Same section.

3. **A template is a Store file in the same marks as an entry and never
   becomes a page.** `docs/design.md` § What may depend on what, under *A
   template is a Store file*. It follows that a template is an entry file in a folder the Builder does
   not read — nothing new to parse. **(decided here: that the entry
   format is reused whole rather than a template format invented.)**

4. **The historical comments sit in a file beside the entry rather than
   inside it, are read-only, and never carry an email address or an IP
   address.** `docs/design.md` § What may depend on what, under *What
   Import brings across*.

5. **Beside means a folder of their own, not the entry's folder.**
   **(decided here.)** `store.list_slugs` lists a folder by file name and
   returns every name ending in the entry suffix, so a comments file
   taking that suffix beside the entry would be returned as an entry. A
   different suffix in the same folder avoids that and still leaves the
   folder of his prose holding files that are not his prose. A separate
   folder settles both, and the entry folders keep one rule: one file,
   one entry.

6. **Comments are stored as JSON; every other Store file stays the
   format it already is.** **(decided here.)** A comment body may contain
   any line, including a blank one, and the export's own comments do
   contain line breaks — so a single text file holding many comments
   needs an invented delimiter or an escaping rule that a body could
   break. Comments are also the one thing here he never writes: they are
   records rather than his prose, so the entry format's reason for
   existing does not reach them. `settings.py` already writes JSON, so
   this introduces no new dependency and no new format to the project.
   § 8 records the text alternative and why it lost.

7. **Replies are preserved.** **(decided here.)** The export carries a
   parent for each comment and some of them are replies to another
   comment. Flattening them would silently reshape what readers wrote,
   which is the same class of loss S2 forbids for his own writing. The
   conformance run in § 7 prints the figures rather than this spec
   quoting them.

8. **The fixed-page set is open, not the four named.**
   **(decided here.)** `docs/design.md` names Home, About, Music and
   Privacy because those are the pages that exist and because leaving
   Privacy out is a legal exposure. Nothing needs the Store to know that
   list: it lists the folder. Import creates the pages the site has, and
   a fifth page later costs a file rather than a code change.

9. **A photograph's original sits in a folder of Pressless's own and is
   never copied to the site folder.** `docs/design.md` § Where everything
   sits on disk puts the originals there and keeps them unpublished.
   `docs/standards/versioning-overrides.md` § The breaking surfaces
   assigns the choice of place to this item, so leaving it open would
   leave Import inventing one.

10. **A photograph's name is a legal slug, a dot, and a lowercase
    extension.** **(decided here.)** A slug alone cannot name a file that
    has to keep its kind, and the name still has to be checked, because
    it arrives from the archive and decides where a write lands (INV-11).

## 4. Design

### 4.1 The public surface

Added to `src/pressless/store.py`, beside the entry surface PRESS-0005
§4.1 defines. § 8 records why this is not a second module.

```python
@dataclass(frozen=True)
class Comment:
    identifier: str    # unique within its file; what a reply points at
    author: str        # the name as given, published as it is today
    author_url: str    # may be empty
    date: datetime     # naive wall clock, as Entry.date is
    body: str          # verbatim
    parent: str        # the identifier this replies to, or "" if top level

PAGES_FOLDER = "pages"
FURNITURE_FOLDER = "furniture"
TEMPLATES_FOLDER = "templates"
COMMENTS_FOLDER = "comments"
PHOTOGRAPHS_FOLDER = "photographs"
HTML_SUFFIX = ".html"
COMMENTS_SUFFIX = ".json"
FURNITURE_NAMES = ("header", "footer", "navigation")

def html_path_for(folder: Path, kind: str, name: str) -> Path: ...
def list_html(folder: Path, kind: str) -> tuple[str, ...]: ...
def read_html(path: Path) -> str: ...
def write_html(folder: Path, kind: str, name: str, html: str) -> Path: ...

def template_path_for(folder: Path, name: str) -> Path: ...
def list_templates(folder: Path) -> tuple[str, ...]: ...
def write_template(folder: Path, entry: Entry) -> Path: ...

def comments_path_for(folder: Path, slug: str) -> Path: ...
def read_comments(path: Path) -> tuple[Comment, ...]: ...
def write_comments(folder: Path, slug: str, comments: tuple[Comment, ...]) -> Path: ...

def photograph_path_for(folder: Path, name: str) -> Path: ...
def list_photographs(folder: Path) -> tuple[str, ...]: ...

class DanglingReply(StoreError): ...
```

`kind` is `PAGES_FOLDER` or `FURNITURE_FOLDER`, and any other value
raises `StoreError`. **Under `FURNITURE_FOLDER` the name must be one of
`FURNITURE_NAMES`, and any other raises `StoreError`**: decision 2 gives
the site exactly one header, one footer and one navigation, and an open
furniture folder would let a fourth file exist that the Builder has no
place for. The page set is open (decision 8); the furniture set is not,
and that asymmetry is why both constants are exported. One set of functions serves both because a fixed
page and a furniture file are the same thing — HTML held verbatim — in
different folders; only what reads them differs, and that is the
Builder's business rather than the Store's.

There is no `read_template`: PRESS-0005's `read` takes a path and a
template file is an entry file, so it already reads one. `write_template`
exists only because `write` chooses between the two entry folders and a
template belongs in neither; it names the file from `entry.slug`, which
is what `list_templates` returns and what PRESS-0017's picker binds to.

The Store gives a photograph a place and a checked name and does not
open one. Copying the original in is the Face's, and every derived copy
is PRESS-0016's.

`write_comments` replaces the file whole. Comments are read-only to the
writer, so there is no add-one-comment call to build; Import writes each
entry's comments once.

### 4.2 The file shapes

**A fixed page and a furniture file are the bytes, and nothing else.**
`read_html` decodes UTF-8 and returns the text; `write_html` encodes it
back. No parse, no reformat, no reindent, no entity rewriting.

**Line endings are preserved here and normalised everywhere else, and
that is deliberate.** PRESS-0005 §4.2 writes entries LF whatever the
platform. A fixed page is different: the code view hands him the file
entire, so its bytes are his, and rewriting his line endings on save is
the reformatting decision 1 exists to forbid. Entries, templates and
comments keep the LF rule; pages and furniture keep what they were
given.

**A template file is an entry file** — the same header, the same blank
line, the same body, read and written by the same code. Its `Date` is
whatever it was created with and nothing reads it.

**A comments file is a JSON array of objects**, one per comment, in the
order they are to be read back, each carrying exactly the six fields of
`Comment` and no others. `identifier` and `parent` are strings because
they are opaque keys rather than numbers to do arithmetic with; the
export's own ids are what fills them. `date` is written in the same
format an entry's `Date` header uses, so one date rule covers the Store.

### 4.3 Where the files sit

```
<Pressless's own folder>/
    published/<slug>.txt
    drafts/<slug>.txt
    pages/<name>.html
    furniture/<name>.html
    templates/<name>.txt
    comments/<slug>.json
    photographs/<name>.<extension>
```

A comments file is named for the entry it belongs to, which is what
makes it findable without an index.

Every name that becomes a file name — a page's, a furniture file's, a
template's, and the slug a comments file is named for — is checked by the
same rule `store.path_for` applies to a slug. That is one rule for the whole Store and, more importantly, it is
the check that stops a name reaching outside the folder it was meant for.

None of these folders is the site folder. The Builder copies what belongs
there into `content/` when it runs; that is PRESS-0008's, and nothing
here writes into the site folder.

### 4.4 Reading and writing

Reading opens one file and returns it. It writes nothing — no repair, no
normalisation, no re-save of a file whose markup it finds untidy. A file
that cannot be parsed raises `StoreError` naming the path.

`list_html` and `list_templates` read file names and open nothing, as
`list_slugs` does.

Writing takes the same route as PRESS-0005 §4.5: a temporary file in the
destination folder, then `os.replace` over the target.

`write_comments` refuses a set in which a reply points at an identifier
the same set does not hold, raising `DanglingReply`. The Builder has to
render a tree, and a parent that is not there is a tree it cannot build;
refusing at the write is where the caller still knows what it dropped.

### 4.5 What this never does

- **It never produces HTML.** It stores HTML somebody else wrote. The
  Store still does not import Marks, which is PRESS-0005 INV-1.
- **It never parses the HTML it holds**, so it can hold a page that is
  not well formed and give it back unchanged.
- **It never publishes a template**, and offers no move that could.
- **It never carries the email address or IP address WordPress collected
  around a comment**, which is the one thing here that cannot be undone
  once written. A reader's own words are carried whole, whatever is in
  them (INV-4).

## 5. Invariants

- **INV-1** — A page or furniture file's bytes survive `read_html` then
  `write_html` unchanged, including line endings, indentation and any
  markup error it was given.
  *Test:* `tests/test_store_extras.py::test_html_survives_a_round_trip`
  — a fixture carrying a CRLF line ending, an unclosed tag, a raw `&`
  and irregular indentation.
  *Breaks when:* an implementer runs the file through an HTML parser,
  a formatter or `str.splitlines()` and rejoins it. Each of those reads
  as tidying and each one changes his file.

- **INV-2** — `src/pressless/store.py` imports no HTML parser, no
  templating module and still no network module and not
  `pressless.marks`.
  *Test:* `tests/test_store_extras.py::test_store_imports_nothing_forbidden`,
  walking the module's imports as PRESS-0005 INV-1's test does.
  *Breaks when:* an implementer imports `html.parser` to check a page is
  well formed, which is the obvious way to be helpful here and is what
  makes INV-1 unholdable.

- **INV-3** — A page, furniture or template name, or a comments slug,
  that is not a legal slug raises `StoreError` and produces no path; and
  a furniture name outside `FURNITURE_NAMES` raises `StoreError` too.
  *Test:* `tests/test_store_extras.py::test_illegal_names_are_refused`,
  running `..`, a name containing `/`, an absolute path, an empty name
  and one with an uppercase letter against **every** call that turns a
  name into a path — `html_path_for`, `template_path_for` and
  `comments_path_for` — plus a legal-but-unlisted furniture name.
  *Breaks when:* a new path function joins the name without the guard.
  This is the Store's trust boundary: every name here arrives from a
  file the writer or the archive supplied, and a name is the only thing
  in this spec that decides where a write lands.

- **INV-4** — A `Comment` has no field for an email address or an IP
  address, and none of the export's `comment_author_email` or
  `comment_author_IP` values reaches a file the Store writes.
  *Test:* `tests/test_store_extras.py::test_comments_carry_no_contact_details`
  — assert on `Comment`'s field names, then build a `Comment` from an
  export record whose email and IP fields hold values appearing nowhere
  else in it, and search the written bytes for those two values.
  **A body is out of scope on purpose:** it is the reader's own words and
  INV-6 carries it verbatim, so an address a reader typed into their own
  comment stays. What this forbids is the Store carrying the fields
  WordPress collected around them.
  *Breaks when:* an implementer widens `Comment` to whatever the export
  offers, or keeps the original record alongside for later. Both are the
  same mistake: this is the field set, not a subset of a bigger one.

- **INV-5** — `write_comments` raises `DanglingReply` when a reply's
  parent is not in the same set, and writes nothing.
  *Test:* `tests/test_store_extras.py::test_a_dangling_reply_is_refused`
  — write a good set, then attempt one whose reply names an absent
  parent, and assert the file still holds the first set.
  *Breaks when:* an implementer validates nothing and leaves the Builder
  a tree with a missing branch, which shows up as a comment silently not
  rendering rather than as an error.

- **INV-6** — Comments survive `write_comments` then `read_comments`
  with every field and their order unchanged.
  *Test:* `tests/test_store_extras.py::test_comments_survive_a_round_trip`
  — a set whose bodies carry a blank line, a quotation mark, a backslash,
  a non-ASCII character and a line that looks like JSON, with one reply
  ordered before the comment it answers.
  *Breaks when:* an implementer sorts on read, or reorders replies under
  their parents at rest. Sorting looks like a service and makes the file
  no longer what was written; ordering is the Builder's decision.

- **INV-7** — A template is not reachable as an entry: no template
  appears in `list_slugs` for either entry folder, and the Store offers
  no call that moves one into them.
  *Test:* `tests/test_store_extras.py::test_a_template_is_never_an_entry`
  — write a template, assert both `list_slugs` results are empty, and
  assert the module exposes no publish-a-template call.
  *Breaks when:* an implementer stores templates as drafts with a marker
  field, which is the cheap shortcut and puts them one bug away from
  being published.

- **INV-8** — A comments file is written under `COMMENTS_FOLDER` and
  never into either entry folder.
  *Test:* `tests/test_store_extras.py::test_comments_are_not_entries` —
  assert `comments_path_for` resolves under `COMMENTS_FOLDER`, then write
  comments for a slug that exists and one that does not and assert both
  entry folders hold exactly the files they held before.
  *Breaks when:* an implementer puts the comments beside the entry after
  all. **Comparing `list_slugs` would not catch that**: it keeps only
  names ending in the entry suffix, so a `.json` file in an entry folder
  is invisible to it and the layout could be breached with the assertion
  still green. The folder listing is what has to be asserted.

- **INV-9** — After a write of any kind here interrupted before
  completion, the file on disk is the previous one.
  *Test:* `tests/test_store_extras.py::test_writes_are_atomic` — patch
  `os.replace` to record its destination and raise, once per writing
  call, and assert each destination and that the previous file reads
  back.
  *Breaks when:* an implementer writes the new calls with a plain open,
  having taken the atomic route only in the entry code it copied from.

- **INV-10** — A comments file is UTF-8 with LF line endings whatever
  the platform's defaults; a page or furniture file is UTF-8 and keeps
  the bytes it was given, line endings included. A template is an entry
  file and takes the entry rule unchanged (PRESS-0005 §4.2 and INV-6),
  which this spec does not restate.
  *Test:* `tests/test_store_extras.py::test_encodings_are_as_specified`
  — write a page whose text carries a CRLF and a non-ASCII character and
  assert the CRLF is still there; write a comments file whose body
  carries a CRLF and assert the JSON's own line endings are LF.
  *Breaks when:* an implementer applies one newline rule to everything.
  LF everywhere rewrites his page, which decision 1 forbids.

- **INV-11** — A photograph's original has a place in Pressless's own
  folder, a checked name, and no route to the site folder: the Store
  offers no call that copies one anywhere.
  *Test:* `tests/test_store_extras.py::test_photographs_stay_where_they_are`
  — assert `photograph_path_for` refuses a name that is not a slug, a
  dot and a lowercase extension, and that it lands under
  `PHOTOGRAPHS_FOLDER`; then assert the module's public names are exactly
  those § 4.1 lists, so a copy-a-photograph call cannot be added without
  this test failing.
  *Breaks when:* an implementer has the Store copy an original toward
  the site folder to save the Builder a step, which publishes the full
  original of every photograph he has.

## 6. Failure modes

| What happens | What the Store does |
|---|---|
| A folder is missing | Reading lists nothing; writing creates it. The layout is the Store's rather than the caller's, as PRESS-0005 has it for the entry folders |
| A page file is not valid UTF-8 | `StoreError` naming the path. It is not read with a replacement character, which would silently change his page on the next save |
| A comments file is not valid JSON | `StoreError` naming the path. It is never rewritten into something parseable |
| A comments file holds a field the record does not have | `StoreError` naming the path and the field. Unlike an entry's unknown header field, which ADR-0001 keeps, an unexpected field here is most likely one this spec forbids |
| A reply points at a parent that is absent | `DanglingReply`, and nothing is written (INV-5) |
| A name is not a legal slug | `StoreError` (INV-3) |
| `kind` is neither pages nor furniture | `StoreError` naming what was passed |
| A furniture name outside `FURNITURE_NAMES` | `StoreError` naming it and the three that are allowed |
| The disk fills mid-write | The temporary file fails; the previous file is untouched (INV-9) |

## 7. Tests

`tests/test_store_extras.py` — one test per invariant, named in § 5,
using a temporary folder as `tests/test_store.py` does.

`tests/test_store_extras_archive.py` — the conformance run, against the
real WordPress export. Every comment Import would carry is written
through the Store and read back, and the run asserts that no field
changed, that every reply's parent resolves, and that no
`comment_author_email` or `comment_author_IP` value from the export
appears in any file written.

It **prints** the archive's figures rather than this spec quoting them —
how many comments the import population carries, how many are replies,
how many entries have any — for the reason `CLAUDE.md` § How documents
get written here gives: a number in prose goes stale and a reader edits
toward it.

**`tests/test_store_extras.py` always runs**; it needs nothing but a
temporary folder, and it is what checks INV-1 to INV-11.
`tests/test_store_extras_archive.py` alone skips cleanly where
`PRESSLESS_ARCHIVE` is unset, as PRESS-0004's and PRESS-0005's archive
runs do, so a green CI run says nothing about the archive. Nothing from
the archive is written into a fixture or a report.

**INV-2's test proves what the module imports and nothing else.** It is
the same weakness PRESS-0005 §7 records of its own import test, which
this project's `CLAUDE.md` has passing against an empty file. It is
worth having because the rule it locks is about imports; it is not
evidence that anything here works.

**The red run is made against a stub, never against an absent module.**
Adding these names to an absent `store.py` is not the case — the module
exists — but the new calls must be declared and raising
`NotImplementedError` before the tests are written, or the suite errors
where it should fail. INV-2's test will not go red against such a stub,
and that is expected rather than a fault.

## 8. Alternatives considered (and rejected)

**A second module for the non-entry material.** It would keep
`store.py` at its present size. Rejected: these files share the name
rule, the atomic write, the error types and the folder handle with the
entry code, so a second module either duplicates them or imports the
first — two modules for one part of the design, and the design has one
Store.

**One text file per entry holding all its comments.** It would keep one
format across the Store and stay double-clickable. Rejected: a comment
body may contain any line, and the export's own comments contain line
breaks, so the format needs a delimiter no body can produce or an
escaping rule — either of which is a format invented here, for the one
kind of file the writer never edits.

**A folder of one file per comment.** It removes the delimiter problem
without JSON. Rejected: `docs/design.md` says a file beside the entry,
and a folder per entry makes the common case — an entry with no comments
— a directory that may or may not exist.

**Templates as drafts carrying a marker field.** No new folder, no new
call. Rejected: it puts a template one filter mistake away from being
published, and INV-7 exists because that mistake is cheap to make.

**Storing the visible words of a fixed page separately from its
markup**, so the plain box has something simple to edit. Rejected: it
makes the file two sources of truth for one page, and
`docs/design.md` § What may depend on what settles the round trip the
other way — the box edits the words in place and leaves the tags alone.

## 9. Out of scope

- **Everything about a photograph except where its original sits.** The
  picture mark, how an entry names one, the web-sized copy and the
  copying-in are PRESS-0016's. Decision 9 settles the place because two
  documents assign that here and Import needs it; nothing else about a
  photograph is decided in this spec.
- **Rendering any of this.** The Builder (PRESS-0008) turns these files
  into pages.
- **Editing them.** The plain box and the code view are PRESS-0014; the
  template picker is PRESS-0017.
- **Writing them the first time.** Import (PRESS-0007) does that.
- **New comments.** The site takes none, by `docs/discovery.md`'s
  decision; these are the historical ones, read-only.
- **Undo.** PRESS-0015 owns what an undo does with a file the fetched
  state does not hold.

## 10. What checks this

| Invariant | What checks it |
|---|---|
| INV-1 page and furniture bytes survive | `test_html_survives_a_round_trip` |
| INV-2 imports | `test_store_imports_nothing_forbidden` |
| INV-3 name rule | `test_illegal_names_are_refused` |
| INV-4 no contact details | `test_comments_carry_no_contact_details`, and the archive run over the real export |
| INV-5 dangling reply refused | `test_a_dangling_reply_is_refused` |
| INV-6 comments round trip | `test_comments_survive_a_round_trip`, and the archive run |
| INV-7 a template is never an entry | `test_a_template_is_never_an_entry` |
| INV-8 comments are not entries | `test_comments_are_not_entries` |
| INV-9 atomic writes | `test_writes_are_atomic` |
| INV-10 encodings | `test_encodings_are_as_specified` |
| INV-11 photographs stay put | `test_photographs_stay_where_they_are` |
| That the plain box leaves the tags alone | **nothing here** — the Store holds the bytes and INV-1 proves it gives them back; whether the Face's box edits only the words is PRESS-0014's |
| That the Builder never reads `templates/` | **nothing here** — INV-7 proves the Store offers no route; that the Builder does not go looking is PRESS-0008's |

## 11. Cross-doc impact

- **PRESS-0005 §1** lists the photographs among what this item covers,
  without the narrowing § 9 draws. That spec is accepted, so the wording
  is its own to correct.
- **`docs/design.md` § What may depend on what**, under *What Import
  brings across*, cites the count of published comments in the sentence that tells Import to carry them.
  Import's population is wider than published entries — PRESS-0005 §7
  fixes it as published, draft and private — so the number of comments
  Import carries is larger than the figure quoted there. The conformance
  run in § 7 prints both populations. The design document's wording is
  its own to correct.
- **`docs/standards/versioning-overrides.md`** names the on-disk format a
  breaking surface. The comments file and the page files join the entry
  file under that promise.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-31 | 3, cold — genre pinned `spec`, packet carried the Store's `path_for` and `list_slugs` windows, PRESS-0005 §§1/4.1/4.3/4.5/4.6/5/7, the four `design.md` passages this spec rests on, `versioning-overrides.md` § The breaking surfaces and the measured shape of the export's comments | 1 | 4 | 3 | 2 | **Ten verified, ten fixed, one collateral; nothing dismissed.** **Three defects were found independently by all three lanes.** The name rule was stated as covering the whole Store and enumerated three kinds, leaving the slug `comments_path_for` takes — supplied by the archive — unguarded, so an implementer could write outside the folder with the suite green. `FURNITURE_NAMES` was exported with nothing saying what it constrained, so the Builder and the Face would have disagreed about whether a fourth furniture file can exist. And INV-4 ordered a byte search for an address that INV-6 requires a body to carry verbatim: a correct implementation had to fail it, and the repair an implementer would reach for is scrubbing a reader's words. Measured against the real export before fixing — no body, author name or url carries an email- or IP-shaped string — so the conflict was latent rather than a live conformance failure, and the invariant is now scoped to the fields WordPress collected. **Two lanes found a clause that could not fail.** INV-8 asserted comments do not change `list_slugs`, which filters on the entry suffix — a `.json` file in the entry folder is invisible to it, so the layout could be breached with the test green; it now asserts the folder listing. INV-11 asserted the module exposes "no call taking a destination outside the handed folder", which nothing could observe. **One lane alone found the sharpest Q2:** § 7 said "Both skip cleanly where `PRESSLESS_ARCHIVE` is unset", whose nearest antecedent is the unit suite — so an implementer would have put a module-level skip on the file that checks all eleven invariants, and CI would have gone green having run none of them. **The one Q1 came from resolving a lane's open question rather than from a lane:** the LF rule was attributed to PRESS-0005 § 4.5, which covers the atomic write; it lives in § 4.2 and INV-6. **Five open questions resolved clean** and are not in the tally — `Entry.date` is naive (`_parse_date` carries a DTZ007 waiver), the entry `Date` format is pinned, the 1.0 promise is where it was cited, `store.write` does create its folder, and the Privacy page is linked from every page today. |

## 13. Resource cost

One file per fixed page and per furniture file, one per template, and
one per entry that has comments — so the comments add files to a
minority of entries and nothing to the rest. Each is small. Reading a
comments file parses one JSON array; nothing here holds state between
calls or adds a build target.
