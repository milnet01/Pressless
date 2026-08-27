# PRESS-0005 — The Store: one file per entry, drafts kept apart

**Status:** spec draft (2026-08-27).
**Kind:** implement.
**Source:** ROADMAP PRESS-0005 (`docs/design.md` § Persistence,
§ Where everything sits on disk; ADR-0001).

**Blocked by:** PRESS-0001.
**Blocker for:** PRESS-0006, PRESS-0007, PRESS-0008.

*Layman:* every entry becomes one ordinary text file in an ordinary
folder, openable in Notepad, and unfinished ones are kept in a
different folder that never reaches the web.

## 1. Goal

After this ships there is one part that turns an entry into a file and
a file back into an entry, and it keeps unfinished writing in a
different folder from finished writing. It is handed the folder it
works in, exactly as Settings is. Every entry is UTF-8 text a person
can read without Pressless, which is S3. Every line break the writer
typed is still there, which is S2. Nothing it writes into the
published folder is unfinished, which is where S7 starts.

This spec covers entries only. The rest of what the Store holds — the
fixed pages, the templates, the page furniture, the historical
comments and photographs — is PRESS-0006.

## 2. Problem

Nothing can read or write an entry yet, and three items are waiting on
the answer. Import (PRESS-0007) has to write the whole archive out
once. The Builder (PRESS-0008) has to list and read the published
entries. PRESS-0006 adds the other file kinds beside them and needs
the entry's shape settled first.

The shape is also the thing hardest to change afterwards.
`docs/standards/versioning-overrides.md` names the entry file's format
a breaking surface, and the 1.0 promise is about it: a file written by
1.0 stays readable by every later version. Getting it wrong is
expensive in the literal sense — twelve years of writing would have to
be rewritten.

## 3. Scope decisions (agreed with the user)

Where a decision was already made elsewhere this section cites it
rather than restating the reasoning. The rest were made in this spec
and are marked so.

1. **The Store is handed its folder and never derives one.** Same
   shape as Settings (PRESS-0001 §3 decision 2), and for the same
   reason: finding Pressless's own folder from the running program is
   PRESS-0022's job. Settings does not carry that path either — its
   field set (PRESS-0001 §4.1, locked by that spec's INV-6) has no key
   for it, so adding one would be a breaking change to Settings.
   *Decided in this spec.*
2. **Drafts and published entries live in separate folders, not in one
   folder distinguished by a header field.** `docs/design.md`
   § Where everything sits on disk requires them kept apart; which
   mechanism was open. A folder makes S7 structural: the Builder is
   handed the published folder and has no way to reach a draft, so no
   parsing mistake can publish unfinished writing. A header field
   would put S7 behind a correct read of every file.
   *Agreed with the user 2026-08-27.*
3. **Both folders sit inside Pressless's own folder, outside the site
   folder.** `docs/design.md` § Where everything sits on disk, on the
   measurement that everything in the repository is publicly
   fetchable. Published entries are also fetchable in `content/` once
   the Builder has written them there, and that is fine — they are the
   source text of writing already on the page.
4. **The entry's header carries the slug that is its address**, in the
   form the live site already uses, rather than the raw WordPress one.
   The address is a breaking surface. Storing the resolved value keeps
   one place deciding it; storing the raw value would leave the rule
   that resolves it as a second place, where a change silently moves
   every address. Resolving it is a one-time job and belongs to Import
   (PRESS-0007). *Agreed with the user 2026-08-27.*
5. **A file's name is not a contract; its header is.** The header's
   `Slug` is the address. The file name exists so a person can find an
   entry in a folder. Renaming a file therefore changes no address and
   is not a breaking change. *Decided in this spec.*

## 4. Design

### 4.1 The public surface

```python
@dataclass(frozen=True)
class Entry:
    slug: str                       # the address; never empty
    title: str                      # may be empty -- many entries have none
    date: datetime                  # date and time; ordering needs the time
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    body: str                       # verbatim, every newline a line break
    extra: tuple[tuple[str, str], ...]   # unrecognised header fields, in file order

FILE_SUFFIX = ".txt"
PUBLISHED_FOLDER = "published"
DRAFTS_FOLDER = "drafts"

def path_for(folder: Path, slug: str, *, draft: bool) -> Path: ...
def exists(folder: Path, slug: str, *, draft: bool) -> bool: ...
def list_slugs(folder: Path, *, draft: bool) -> tuple[str, ...]: ...
def read(path: Path) -> Entry: ...
def write(folder: Path, entry: Entry, *, draft: bool) -> Path: ...
def publish(folder: Path, slug: str) -> Path: ...

class StoreError(Exception): ...
class EntryNotFound(StoreError): ...
```

`write` is create-or-replace. Two entries at one slug is a
contradiction rather than a case to handle: the slug is the address,
and one address holds one entry. Choosing a slug that is not already
taken belongs to whatever offers the writer a new entry (PRESS-0012);
`exists` is what it asks.

`publish` moves a draft into the published folder by rename. It reads
and writes no body, so it cannot alter one.

### 4.2 The entry file

UTF-8. A short `Key: value` header, one blank line, then the body
verbatim. ADR-0001 fixes this shape; what follows is the part ADR-0001
leaves to the Store.

```
Title: An example
Slug: an-example
Date: 2014-11-09 21:32:00
Categories: poetry
Tags: one, two

The body starts here.
Every single newline is a line break.
```

- **Five recognised fields: `Title`, `Slug`, `Date`, `Categories`,
  `Tags`.** Read off `tools/build_blog.py::Post` in the sibling
  workspace, which is what the live site is built from today. Losing
  any of them costs the site its categories, its tags or its by-year
  archive.
- **`Slug` and `Date` must be present and non-empty. `Title`,
  `Categories` and `Tags` must be present and may be empty.** An
  untitled entry is ordinary here, not an error — a large share of the
  archive has no title, which `tests/test_store_archive.py` measures.
- **`Date` is `YYYY-MM-DD HH:MM:SS`.** The time is carried because
  entries share a day often enough that ordering needs it, which the
  same archive test measures.
- **`Categories` and `Tags` are comma-separated.** A value may not
  contain a comma; one that does is refused on write rather than
  written and silently split on the next read (INV-9).
- **A header value is one line.** A wrapped value would be read back
  as a new field, so a value containing a newline is refused by the
  same rule.
- **A field the Store does not recognise is kept byte-for-byte, in the
  position it was found.** ADR-0001's promise, and the reason the
  Store never rewrites a file it was only asked to read.
- **The header ends at the first blank line.** Everything after it is
  body, including a line that looks like a field.
- **LF line endings, written explicitly.** Windows would otherwise
  write CRLF, and a changed line ending is a changed file to git — so
  every publish would look as though it had touched the whole site.

### 4.3 Where the files sit

```
<Pressless's own folder>/
    published/<slug>.txt
    drafts/<slug>.txt
```

`.txt` so that double-clicking opens a text editor on Windows, which
is what S3 describes. The file name is the slug; §3 decision 5 is why
that is safe to change later.

Neither folder is the site folder. The Builder copies published
entries into `content/` when it runs; that is PRESS-0008's, and
nothing here writes into the site folder.

### 4.4 Reading

`read` opens one file and returns an `Entry`. It writes nothing —
not a repair, not a normalisation, not a re-save of a file whose
header it found untidy. A file that cannot be parsed raises
`StoreError` naming the path; it is never rewritten into something
parseable.

`list_slugs` returns the slugs in one folder, sorted, without reading
a body.

### 4.5 Writing

A temporary file in the destination folder, then `os.replace` over the
target, which is atomic on both Windows and Linux — so a crash
mid-save leaves the previous file rather than half an entry. This is
the shape `src/pressless/settings.py::save` already uses.

The five recognised fields are written first, in the order §4.2 lists
them, then any `extra` fields in their original order, then the blank
line, then the body.

### 4.6 What the Store never does

- **It never produces HTML.** `docs/design.md` § What may depend on
  what rule 6: turning marked text into HTML is Marks' job. The Store
  does not import Marks.
- **It never reaches the network**, and never opens the site folder.
- **It never decides what is published.** It offers two folders and a
  move between them; the decision is the writer's, through the Face.

## 5. Invariants

- **INV-1** — `src/pressless/store.py` imports no network module and
  does not import `pressless.marks`.
  *Test:* `tests/test_store.py::test_store_imports_nothing_forbidden`,
  walking the module's imports as
  `tests/test_marks.py::test_marks_is_pure` does.
  *Breaks when:* an implementer imports Marks to validate a body, or
  `urllib` to check that a slug is a legal address.

- **INV-2** — `read` and `list_slugs` open no path for writing and
  leave the folder's file list unchanged.
  *Test:* `tests/test_store.py::test_reading_never_writes` — patch the
  filesystem calls to record every mode a path is opened with, read
  and list a folder holding an entry with an unrecognised header
  field and an untidy one, then compare the folder listing and each
  file's bytes before and after.
  *Breaks when:* an implementer makes `read` normalise a header it
  finds untidy, or `list_slugs` build an index file. The untidy
  fixture is what makes it bite: against a well-formed file there is
  nothing a repairing implementation would rewrite, so the assertion
  would stay green.

- **INV-3** — After a write interrupted before completion, the file on
  disk is the previous one.
  *Test:* `tests/test_store.py::test_write_is_atomic` — patch
  `os.replace` to record its destination and then raise; assert the
  destination is `path_for(...)` and that `read` still returns the
  previous entry.
  *Breaks when:* an implementer opens the target file and writes into
  it. Asserting the destination is what makes it bite: against a
  direct write there is no replace to interrupt, so the interruption
  half alone would pass against the implementation it exists to
  reject.

- **INV-4** — A header field the Store does not recognise is present,
  unchanged and in its original position, after a `read` followed by a
  `write`.
  *Test:* `tests/test_store.py::test_unknown_header_fields_survive`.
  *Breaks when:* `write` is built from the dataclass's five known
  fields alone. This is ADR-0001's promise, and it is the one an
  implementation drops without noticing.

- **INV-5** — A body survives `read` then `write` byte-for-byte,
  including consecutive newlines, trailing newlines and a line that
  looks like a header field.
  *Test:* `tests/test_store.py::test_body_survives_a_round_trip` — a
  body containing a blank line, a `Looks: like a field` line, no
  trailing newline in one case and two in another.
  *Breaks when:* an implementer strips, collapses or normalises the
  body, which is S2 broken. The `Looks: like a field` line is what
  catches a parser that re-reads the header past the blank line.

- **INV-6** — Files are written UTF-8 with LF line endings whatever
  the platform's defaults.
  *Test:* `tests/test_store.py::test_written_bytes_are_utf8_lf` —
  write an entry whose title and body carry an accented character and
  a newline, then assert on the raw bytes, not on decoded text.
  *Breaks when:* an implementer opens the file in text mode without
  naming the encoding and newline. Asserting bytes is the whole test:
  reading it back through the same defaults that wrote it passes on
  every platform.

- **INV-7** — `list_slugs(folder, draft=False)` never returns a slug
  whose file is in the drafts folder, and `write(..., draft=True)`
  never creates a file under `published/`.
  *Test:* `tests/test_store.py::test_a_draft_never_reaches_published`
  — write the same slug as a draft and list the published folder;
  then list the whole tree and assert where the file is.
  *Breaks when:* the two folders are collapsed into one with a header
  field, or `publish` copies rather than moves and leaves the draft
  behind as well. This is where S7 starts.

- **INV-8** — The recognised header field names are exactly the five
  §4.2 lists, and `Entry`'s field names are exactly the set §4.1
  lists.
  *Test:* `tests/test_store.py::test_field_names_are_the_documented_set`
  — compare against a literal set written out in the test.
  *Breaks when:* someone adds a sixth field, which changes the file
  format three other items bind to. Stated as the whole set rather
  than as "no extra field", because a rule about absence passes
  against every file that happens not to have one.

- **INV-9** — A value containing a comma, or a newline, in `Title`,
  `Slug`, `Categories` or `Tags` is refused with `StoreError` and
  nothing is written.
  *Test:* `tests/test_store.py::test_a_value_that_would_break_the_format_is_refused`
  — one case per field, asserting the folder is unchanged afterwards.
  *Breaks when:* an implementer writes the value anyway. The
  written-nothing half is the load-bearing one: raising after a
  partial write leaves a file the next read cannot parse.

## 6. Failure modes

- **The folder does not exist.** `read` and `list_slugs` raise
  `EntryNotFound` and `StoreError` respectively; `write` raises
  `StoreError` rather than creating a tree, because a mistyped folder
  is not a folder to start filling.
- **A file that cannot be parsed** — no blank line, a header line with
  no colon, a missing `Slug` or `Date`. `StoreError` naming the path.
  Never repaired in place (INV-2).
- **A slug whose file name the platform cannot hold.** The archive
  carries at least one slug long enough to threaten the Windows path
  limit once the folder path is added, which
  `tests/test_store_archive.py` measures. The write fails and says so;
  it is not silently truncated, because a truncated name could collide
  with another entry's. §3 decision 5 is the repair — renaming the
  file changes no address.
- **`publish` on a slug that is not a draft.** `EntryNotFound`.
  Nothing is moved.

## 7. Tests

Two files.

`tests/test_store.py`, unlabelled — it needs no fixture beyond a
temporary directory and must run everywhere. One test per invariant in
§5.

`tests/test_store_archive.py`, needing `PRESSLESS_ARCHIVE` and skipped
without it, as `tests/test_marks_archive.py` is. It reads the real
WordPress export, writes every entry through the Store into a
temporary folder, reads them all back, and asserts the round trip is
faithful. It also prints the archive's measurements this spec relies
on rather than stating them here: how many entries carry no title, how
many share a day, the longest slug, and whether any two entries
resolve to one slug. Those numbers are evidence and they move; the
test is where they live.

**The red run is made against a stub `store.py`, never against an
absent one.** With the module absent the suite errors at collection
and no assertion runs, which this project's `CLAUDE.md` records as a
trap. The stub declares every name in §4.1 and raises
`NotImplementedError`, so every test is collected.

**Not every test then goes red, and that is expected.** A stub that
declares §4.1's names and imports nothing forbidden already satisfies
INV-1 and INV-8, whose tests read the module rather than run it. Their
going red against the stub means the stub is wrong, not the test. Read
the collected count, not the exit code.

**INV-1's test is weak in a way this project has already met.**
Reading an import list proves what a module imports, never that it
works — `CLAUDE.md` records `test_marks_is_pure` passing against an
empty file. It is worth having because the rule it locks is about
imports.

## 8. Alternatives considered (and rejected)

- **One folder, with a `Status: draft` header field.** Fewer moving
  parts, and `publish` becomes an edit rather than a rename. Rejected
  because it puts S7 behind a correct read of every file: one parsing
  mistake and an unfinished poem is on the live site, which is the
  failure `docs/design.md` calls the worst kind — a draft appearing
  and nobody noticing.
- **JSON or TOML for the whole entry.** Both survive any value without
  an escaping rule, which INV-9 would not then need. Rejected because
  S3 is the point of the format: opened in Notepad a JSON entry is
  quoted, escaped and one line, and the body's line breaks stop being
  line breaks in the file. ADR-0001 already settled that the body is
  verbatim text.
- **Storing the raw WordPress slug and resolving it at build time.**
  Rejected in §3 decision 4 — it leaves two places deciding an
  address.
- **Naming files `<date>-<slug>.txt`.** Sorts chronologically in a
  file manager, which is genuinely nice. Rejected because it makes the
  longest names longer, against a platform limit this design already
  has to name, and buys nothing the `Date` field does not already
  carry.
- **Truncating a slug that is too long for the platform.** Rejected
  because two truncated slugs can collide, and a collision here loses
  an entry silently. Failing loudly is recoverable; §3 decision 5 says
  why the repair is cheap.
- **The Store reading Settings for its folder.** Permitted by
  `docs/design.md` rule 6, and rejected in §3 decision 1: Settings has
  no such key, and adding one is a breaking change to a spec that
  locks its field set.

## 9. Out of scope

- The fixed pages, templates, page furniture, historical comments and
  photographs the Store also holds — PRESS-0006.
- Turning the WordPress export into Store files — PRESS-0007.
- Copying published entries into the site folder — PRESS-0008.
- Choosing a slug for a new entry, and what the writer is shown when a
  write fails — PRESS-0011 owns the error contract, PRESS-0012 the
  editor.
- Finding Pressless's own folder from the running program —
  PRESS-0022.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_store.py::test_store_imports_nothing_forbidden` |
| INV-2 | `tests/test_store.py::test_reading_never_writes` |
| INV-3 | `tests/test_store.py::test_write_is_atomic` |
| INV-4 | `tests/test_store.py::test_unknown_header_fields_survive` |
| INV-5 | `tests/test_store.py::test_body_survives_a_round_trip` |
| INV-6 | `tests/test_store.py::test_written_bytes_are_utf8_lf` |
| INV-7 | `tests/test_store.py::test_a_draft_never_reaches_published` |
| INV-8 | `tests/test_store.py::test_field_names_are_the_documented_set` |
| INV-9 | `tests/test_store.py::test_a_value_that_would_break_the_format_is_refused` |
| The whole archive surviving a round trip (§7) | `tests/test_store_archive.py` — **but it is skipped wherever the export is absent, so a green CI run says nothing about it** |
| That the slug stored here is the address the live site serves (§3 decision 4) | **half** — the archive test proves the Store keeps whatever it was handed; nothing proves Import hands it the resolved value. PRESS-0007 is where that is decided |
| That the Builder reads only the published folder (§3 decision 2) | **nothing here** — the Store cannot check who reads it. PRESS-0008 is where a breach would show, and S7 rests on it |
| LF endings and atomic replace behaving this way on Windows | **nothing** — this suite runs on Linux, and `os.replace` is documented atomic on both. PRESS-0022 stages the built executable to a Windows box, which is the only place it would be observed |
| The Windows path limit (§6) | **nothing** — same reason. The failure mode is named so that it is recognised rather than diagnosed |

## 11. Cross-doc impact

- `CLAUDE.md` — the state block, and § Build and test, which today
  says one test is skipped by default. This adds a second, so that
  paragraph changes when this ships.
- `docs/standards/versioning-overrides.md` — its Store bullet says
  PRESS-0005 and PRESS-0006 still choose the layout inside Pressless's
  own folder. This spec makes that choice, so the bullet is updated
  when this ships.
- `CHANGELOG.md` — an entry when it ships.
- No sibling spec changes. PRESS-0001 is read but not altered; ADR-0001
  is implemented, not amended.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|

## 13. Resource cost

No new dependency; the standard library alone. The Store holds files
and no memory state, and `list_slugs` reads names rather than bodies,
so listing does not grow with what an entry contains. The archive is
the largest population this will ever hold in one folder and it is
small enough that no cap or eviction rule is needed —
`tests/test_store_archive.py` is what would show that changing.
