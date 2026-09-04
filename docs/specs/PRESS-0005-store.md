# PRESS-0005 — The Store: one file per entry, drafts kept apart

**Status:** accepted (2026-08-27). Two cold-eyes loops, both folded in, nothing deferred — the run reached the spec cap of 2 and every verified finding is fixed. A calm cap: under half of the last loop's findings landed on text the run itself wrote, so the document held more defects than the cap held loops. Implementation is the third reviewer.
**Amended 2026-08-28, after implementation.** It was the third reviewer and it found two false claims: §3 decision 5 said nothing in the archive collides, and §10 said the round trip catches a collision. Both corrected. No line of the Store's contract changed, so the gate did not re-arm.
**Amended 2026-09-02, before implementation**, on two decisions the user
took: the legal slug set excludes Windows's reserved device names on every
system, and the file suffix is matched ignoring case. Both change direction,
so the gate re-armed and ran to the spec cap of 2 again. The code landed
the same day as PRESS-0067 items 2 and 3; § 10 names the tests, and the
row below them says what a suite running on Linux still cannot prove.
**Amended 2026-09-03, before implementation**, on a decision the user took
for PRESS-0067 item 6: a `Date` carrying a zone is refused, and one carrying
a fraction of a second is truncated. Measured first — an aware `datetime`
written at `21:32:00+02:00` read back as `21:32:00`, silently moving the
entry two hours. That changes direction, so the gate re-armed and ran to
the spec cap of 2, twelve verified findings, all fixed. **A cap on the
violent side**, and §12's last row says what that means here: half of
loop 6 landed on loop 5's own text, but in the rationale rather than in
the rule — what §4.2 decides survived both loops unchanged. Five of the
twelve fell inside the amendment; the other seven were audit. Routed to
implementation, which is the better third reviewer.

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
   mechanism was open. A folder takes *parsing* out of S7: which
   folder a file sits in is a fact about the filesystem, where a
   header field would put S7 behind a correct read of every file. It
   does not make S7 automatic — §4.1 hands out one folder and a
   `draft` flag, so the Builder still has to ask for the published
   one, and §10 records that nothing here can check that it does.
   What the split buys is that the only remaining way to publish a
   draft is asking for the wrong folder: one visible decision, rather
   than a parser being wrong about one file.
   *Agreed with the user 2026-08-27.*
3. **Both folders sit inside Pressless's own folder, outside the site
   folder.** `docs/design.md` § Where everything sits on disk, on the
   measurement that everything in the repository is publicly
   fetchable. Published entries are also fetchable in `content/` once
   the Builder has written them there, and that is fine — they are the
   source text of writing already on the page.
4. **The entry's header carries the slug in the form the live site
   already uses**, rather than the raw WordPress one. A published
   address is `blog/YYYY/MM/DD/<slug>`: the date supplies every
   segment but the last, and the whole of it is a breaking surface.
   Storing the resolved slug keeps
   one place deciding it; storing the raw value would leave the rule
   that resolves it as a second place, where a change silently moves
   every address. Resolving it is a one-time job and belongs to Import
   (PRESS-0007). **The rule is the one the live addresses already came
   from** — the sibling workspace's `tools/build_blog.py::safe_slug`,
   which decodes percent-encoding, drops marks and control characters,
   folds to ASCII lower case and joins the rest with hyphens, falling
   back to the WordPress post id where nothing survives. Naming it
   here is what stops §7's archive test and PRESS-0007 resolving slugs
   two different ways, which is the second deciding place this
   decision exists to prevent. *Agreed with the user 2026-08-27.*
5. **A slug is unique across the whole Store, which is stricter than
   the live site requires.** Dating the address means the site would
   allow one slug per day; the Store allows one altogether, because
   one flat folder per kind is what makes S3's "ordinary folder"
   something a person can browse. **The archive does not satisfy this
   rule**, which implementing the spec found: one slug is wanted both by
   a published entry and by a draft whose post-id fallback resolves to
   the same string. Both survive here, in different folders, so nothing
   is overwritten — but Import has one address for two entries.
   `tests/test_store_archive.py` reports it. The cost is that an entry
   cannot reuse a slug from an earlier year, and that Import must stop
   rather than overwrite — a case PRESS-0007 now has to handle rather
   than merely guard against.
   *Decided in this spec.*

## 4. Design

### 4.1 The public surface

```python
@dataclass(frozen=True)
class Entry:
    slug: str                       # the address's last segment; never empty
    title: str                      # may be empty -- many entries have none
    date: datetime                  # date and time; ordering needs the time
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    body: str                       # verbatim, every newline a line break
    extra: tuple[tuple[str, str], ...]   # unrecognised header fields, in file order

RECOGNISED_FIELDS = ("Title", "Slug", "Date", "Categories", "Tags")
LIST_SEPARATOR = ", "
FILE_SUFFIX = ".txt"
PUBLISHED_FOLDER = "published"
DRAFTS_FOLDER = "drafts"

def path_for(folder: Path, slug: str, *, draft: bool) -> Path: ...
def exists(folder: Path, slug: str) -> bool: ...   # raises on an illegal slug
def list_slugs(folder: Path, *, draft: bool) -> tuple[str, ...]: ...
def read(path: Path) -> Entry: ...
def write(folder: Path, entry: Entry, *, draft: bool) -> Path: ...
def publish(folder: Path, slug: str) -> Path: ...
def unpublish(folder: Path, slug: str) -> Path: ...

class StoreError(Exception): ...
class EntryNotFound(StoreError): ...
class SlugInUse(StoreError): ...
```

`write` is create-or-replace within its own folder: the slug
identifies the entry, so writing a slug that folder already holds
replaces that entry, and `write` consults no other folder. **Decision
5's Store-wide uniqueness is a rule callers keep, not one `write`
enforces.** `exists` answers across both folders: PRESS-0012 asks it
before offering a new entry, PRESS-0007 before writing an imported
one. **`exists` and `path_for` raise `StoreError` on a slug outside
§4.2's set rather than answering `False`**, so a caller handed a name
the writer typed validates it before asking. `write` is left alone deliberately — Import writes both folders
in one pass, and a `write` that consulted the other could not. Where
the Store does enforce it is the two moves, which have somewhere to
collide (INV-10).

`publish` moves a draft into the published folder by rename, and
`unpublish` moves one back. The reverse is required rather than
symmetric: `docs/design.md` § What may depend on what has an undo turn
an entry the fetched state does not hold back into a draft. Either
raises `SlugInUse` rather than overwriting what the destination
already holds. Neither reads or writes a body, so neither can alter
one.

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
- **A slug is one or more of `a-z`, `0-9` and `-`, and is none of
  `con`, `prn`, `aux`, `nul`, `com1`–`com9` or `lpt1`–`lpt9`.** The
  character set is what `safe_slug` already yields. The device names
  are a narrowing it does not make — decision 4's rule excludes
  nothing — so a resolved slug is not automatically an acceptable one.
  PRESS-0007 owns what happens next; §7's archive test, which may use
  decision 4's rule and no other, reports such an entry rather than
  renaming it. Pinned because the slug becomes
  a file name: an unpinned one admits `/`, `\` and `..`, which write
  outside the handed folder, and admits two slugs differing only in
  case, which are one file on Windows and two on Linux.
- **Those device names are refused on every system, not only on
  Windows.** Windows resolves them whatever the extension, so opening
  `nul.txt` there reaches the null device rather than failing: the
  write appears to succeed and the entry is gone, which is worse than a
  refusal. Refusing them everywhere is what makes an entry that saves
  on one machine save on the other, and it keeps one rule rather than a
  rule per system.
- **`Slug` and `Date` are always written and are never empty. `Title`,
  `Categories` and `Tags` are written only where the entry has a
  value.** An untitled entry is ordinary here, not an error — a large
  share of the archive has no title, which
  `tests/test_store_archive.py` measures. **A large share of what Import brings has no slug either**,
  WordPress rarely giving a draft one; supplying it is PRESS-0007's,
  by decision 4's rule, and the Store simply refuses an empty one.
- **The header carries what the entry has and nothing else.** A file
  the writer never gave a `Categories` line comes back without one.
  Writing the five unconditionally would add two empty lines to every
  entry of twelve imported years, which is Pressless editing files
  nobody asked it to change — and the design promises everywhere else
  that his files survive the round trip. Predictable shape is the
  argument the other way and it loses to that. Nothing is lost either
  way: the read rule below takes an absent `Title`, `Categories` or
  `Tags` as empty, so an omitted line and an empty one parse alike.
  *Agreed with the user 2026-09-02.*
- **On read, an absent `Title`, `Categories` or `Tags` is empty rather
  than an error.** Only `Slug` and `Date` missing is a parse failure.
  S3 invites hand-editing, and a file someone trimmed a blank `Tags:`
  line out of is still an entry.
- **`Date` is `YYYY-MM-DD HH:MM:SS`.** The time is carried because
  entries share a day often enough that ordering needs it, which the
  same archive test measures.
- **That format carries no zone and no fraction of a second, so the
  two are handled differently on write.** A `datetime` carrying a zone
  is refused (INV-9): the offset would come off in silence, and what is
  stored then reads back as a fact rather than as a loss. The refusal
  does not recover the offset — nothing can — it makes the caller decide.
  **Whoever holds one drops the offset and keeps the wall clock, never
  converting** — stated here, in decision 4's form, so that every caller
  decides alike: the refusal hands the question to Import and to §7's
  archive test at once, decision 4 makes the date supply every address
  segment but the last, and a conversion near midnight moves an entry to
  another day. A fraction of a second is truncated instead,
  because a second-resolution format dropping what falls below its own
  resolution misorders nothing, and refusing it would reject
  `datetime.now()` — the value the Face has when the writer saves.
- **`Categories` and `Tags` are separated by `LIST_SEPARATOR`, a
  comma and a space.** Reading splits on the comma and strips the
  whitespace around each value, so a file hand-edited without the
  space still reads. A value may not itself contain a comma; one that
  does is refused on write rather than written and silently split on
  the next read (INV-9). A comma anywhere else is ordinary — titles
  in the archive carry them.
- **A header line is one line — every value, and an unrecognised
  field's name as well as its value.** A wrapped one would be read back
  as a new field, so a newline in any of them is refused (INV-9). The rule
  reaches `extra` deliberately: preserving a field is ADR-0001's
  promise, and writing one back that the next read cannot parse would
  break that promise in the act of keeping it.
- **A field the Store does not recognise is never dropped or renamed,
  and two of them keep their order relative to each other.** Its value
  round-trips stripped of surrounding whitespace and the separator is
  re-spelled `": "`, exactly as a recognised field's is — one rule for
  every field rather than two — so the FIELD survives rather than the
  line's spacing. They are
  written after the recognised five rather than where they were
  found: `Entry.extra` carries no anchor into the recognised fields,
  and inventing one would buy an ordering nothing reads. ADR-0001's
  promise is that anything the parser does not recognise is *preserved
  byte-for-byte and never dropped*. The field is never dropped, and its
  name and value survive; what is not kept byte-for-byte is the
  surrounding spacing, which is the one place this format departs from
  that wording.
- **The header ends at the first blank line, spelled `\n\n` or
  `\r\n\r\n`, whichever comes first.** Everything after it is body,
  including a line that looks like a field. Both spellings are read
  because a Windows editor re-saves the whole file CRLF; the earlier
  wins because a body holds blank lines of its own. The body is
  returned exactly as found, unconverted (INV-5).
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
is what S3 describes. The file name is the slug, and it is how the
Store finds an entry.

**`list_slugs` and `exists` match the suffix ignoring case; `path_for`
composes it exactly.** The Store only ever writes `.txt`, but S3
invites the writer into the folder, and a file hand-renamed to `.TXT`
is the same file on Windows and a different one on Linux. **The
divergence this removes is a Windows one**: there the platform
resolves `<slug>.TXT` for `exists` while a case-sensitive `list_slugs`
cannot see it, so the two disagree about whether an address is taken.
On Linux they are blind together — consistent, but the writer's file
is discoverable by neither. Two names differing only in the suffix's
case — reachable on Linux only, never produced by the Store — name one
slug, and `list_slugs` returns it once.

On Linux that leaves an address reported as taken whose file `read`
cannot open, since `path_for` composes `<slug>.txt`. That is the
trade rather than an oversight: nothing writes over his file, and
`read` raises `EntryNotFound` naming the path it looked for. The
repair is the writer's, as §4.4 already says of a name that disagrees
with its `Slug` header.

Neither folder is the site folder. The Builder copies published
entries into `content/` when it runs; that is PRESS-0008's, and
nothing here writes into the site folder.

### 4.4 Reading

`read` opens one file and returns an `Entry`. It writes nothing —
not a repair, not a normalisation, not a re-save of a file whose
header it found untidy. A file that cannot be parsed raises
`StoreError` naming the path; it is never rewritten into something
parseable.

`list_slugs` returns the slugs in one folder, sorted, read off the
file names rather than by opening anything.

**The header's `Slug` is authoritative, and a file whose name does not
match it is a parse failure** naming both. The two cannot then drift:
`list_slugs` reads names and `read` reads headers, so letting them
disagree would have the same entry answer to two slugs — and the slug
is a breaking surface. Refusing is what keeps a hand-rename loud;
silently preferring either one moves an address or strands a file.

### 4.5 Writing

A temporary file in the destination folder, then `os.replace` over the
target, which is atomic on both Windows and Linux — so a crash
mid-save leaves the previous file rather than half an entry. This is
the shape `src/pressless/settings.py::save` already uses.

The recognised fields the entry has are written first, in the order
§4.2 lists them, then any `extra` fields in their original order, then
the blank line, then the body. `Slug` and `Date` are always among
them; `Title`, `Categories` and `Tags` appear only where they carry a
value (§4.2).

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
  it — the patch never fires, the write completes, and the entry on
  disk is the new one. Asserting the destination as well pins the
  mechanism rather than only its effect.

- **INV-4** — A header field the Store does not recognise is present
  after a `read` followed by a `write`, with its name and its stripped
  value unchanged, and two of them keep their order relative to each
  other — except where INV-9 refuses the name, which is a refusal
  rather than a breach of this rule.
  *Test:* `tests/test_store.py::test_unknown_header_fields_survive`.
  *Breaks when:* `write` is built from the dataclass's five known
  fields alone. This is ADR-0001's promise, and it is the one an
  implementation drops without noticing.

- **INV-5** — A body survives `read` then `write` byte-for-byte,
  including consecutive newlines, trailing newlines and a line that
  looks like a header field.
  *Test:* `tests/test_store.py::test_body_survives_a_round_trip` — a
  body containing a blank line, a `Looks: like a field` line, CRLF line
  endings in one case, no trailing newline in one and two in another.
  The CRLF case is what separates this rule from INV-6: §4.2 reads a
  file a Windows editor re-saved, so a CRLF body is reachable rather
  than hypothetical.
  *Breaks when:* an implementer strips, collapses or normalises the
  body, which is S2 broken. The `Looks: like a field` line is what
  catches a parser that re-reads the header past the blank line.

- **INV-6** — Files are written UTF-8 with LF line endings whatever
  the platform's defaults. **The rule governs the endings the Store
  itself emits** — the header lines, the blank line, and the
  translation the platform would otherwise apply. It never converts
  bytes the body already carries, which is INV-5's.
  *Test:* `tests/test_store.py::test_written_bytes_are_utf8_lf` —
  write an entry whose title carries an accented character and whose
  body carries an accented character and two line breaks, then assert
  on the raw bytes, not on decoded text. The newline belongs to the
  body: INV-9 refuses one in a title, so a fixture putting it there
  could never reach its assertion. **Then assert the call as well** —
  patch the open the module uses and require it named UTF-8 and an
  explicit newline.
  *Breaks when:* an implementer opens the file in text mode without
  naming either. **The byte half cannot catch that here, and this was
  measured rather than reasoned:** on Linux the unnamed defaults are
  already UTF-8 and LF, so the bytes come out identical and the test
  goes green against exactly the code it exists to reject. It is
  Windows that would write CRLF in cp1252, and §10 records that no
  test here runs there. Asserting the call is what makes the invariant
  bite on the platform the suite has.

- **INV-7** — `list_slugs(folder, draft=False)` never returns a slug
  whose file is in the drafts folder, and `write(..., draft=True)`
  never creates a file under `published/`.
  *Test:* `tests/test_store.py::test_a_draft_never_reaches_published`
  — write a slug as a draft, list the published folder, and assert
  where the file is; then `publish` it and assert the drafts folder no
  longer holds that slug. The second phase is what catches a `publish`
  that copies; the first cannot, because nothing has moved yet.
  *Breaks when:* the two folders are collapsed into one with a header
  field, or `publish` copies rather than moves and leaves the draft
  behind as well. This is where S7 starts.

- **INV-8** — `RECOGNISED_FIELDS` is exactly the five names §4.2
  lists, in that order, and `Entry`'s field names are exactly the set
  §4.1 lists.
  *Test:* `tests/test_store.py::test_field_names_are_the_documented_set`
  — compare against a literal set written out in the test.
  *Breaks when:* someone adds a sixth field, which changes the file
  format three other items bind to. Stated as the whole set rather
  than as "no extra field", because a rule about absence passes
  against every file that happens not to have one.

- **INV-9** — A value the format or the file system cannot carry is
  refused with `StoreError` and nothing is written: a newline in any
  header field, `extra` included; a comma in `Categories` or `Tags`; a
  slug outside §4.2's legal set, the empty slug and a reserved device
  name included; a `Date` carrying a zone; and an unrecognised field's
  NAME that is empty, carries a colon, or strips to one of
  `RECOGNISED_FIELDS`. The three name cases are refusals ADR-0001's
  promise requires rather than breaches of it: a name read back as `''`
  or split at its own colon is a field the next read cannot parse, and
  one colliding with a recognised name replaces the entry's own and
  then vanishes, the read being last-wins. A comma in `Title` is
  written unchanged — the header runs to the end of the line, so
  nothing splits it, and refusing one would reject archive entries that
  exist. A `Date`'s fraction of a second is truncated rather than
  refused, for the reason §4.2 gives.
  *Test:* `tests/test_store.py::test_a_value_that_would_break_the_format_is_refused`
  — a newline case for each of the four string-valued fields and for an
  `extra` field's value and its name, a comma case for the two list
  fields, and a slug outside the legal set and one reserved device
  name, each asserting the folder is unchanged afterwards; plus a title
  carrying a comma, which must be written and read back intact. That
  last case is what stops the rule being widened into one Import cannot
  satisfy. **`Date` needs two cases pointing opposite ways**, because
  the type alone refuses neither: an aware `datetime` must raise **and
  leave the folder unchanged**, as every other refusal case here does,
  and one carrying microseconds must be written and read back at whole
  seconds. Without the second the rule could be met by refusing every
  `datetime` the format cannot hold exactly, which is what §4.2 rules
  out.
  **A body UTF-8 cannot encode is a case of its own**, because the
  up-front check reads header values and cannot see it: the refusal has
  to come from the write. `tests/test_store.py::test_an_interruption_is_not_dressed_up_as_a_store_error`
  bounds it from the other side — an interruption escapes as itself
  rather than as a `StoreError`, so the rule cannot be met by catching
  everything.
  *Breaks when:* an implementer writes the value anyway. The
  written-nothing half is the load-bearing one: raising after a
  partial write leaves a file the next read cannot parse.

- **INV-10** — Neither `publish` nor `unpublish` overwrites a file at
  its destination: given a slug held in both folders, each raises
  `SlugInUse`, moves nothing, and leaves both files byte-identical.
  *Test:* `tests/test_store.py::test_a_move_never_overwrites` — write
  different entries at one slug as a draft and as published, call each
  direction, and compare both files' bytes before and after.
  *Breaks when:* a move is written as `os.replace`, which is what §4.5
  prescribes for `write` and is silent about a destination that
  exists. Asserting both files is what makes it bite: asserting the
  exception alone passes against an implementation that raises after
  moving.

## 6. Failure modes

- **The handed folder does not exist.** `read` and `list_slugs` raise
  `EntryNotFound` and `StoreError` respectively; `write` raises
  `StoreError` rather than creating a tree, because a mistyped folder
  is not a folder to start filling.
- **`published/` or `drafts/` is missing inside a handed folder that
  does exist.** `write` creates the one it needs, and `list_slugs`
  returns nothing rather than raising. They are the Store's own layout
  rather than the caller's, so a fresh install needs no setup step for
  them — which is what lets Import write the whole archive in one go.
- **A file that cannot be parsed** — no blank line, a header line with
  no colon, a missing `Slug` or `Date`. `StoreError` naming the path.
  Never repaired in place (INV-2).
- **A file whose name does not match its `Slug` header**, which a
  hand-rename produces. `StoreError` naming both, per §4.4. Nothing is
  moved and nothing is rewritten; the repair is the writer's, and it
  is either name.
- **A file whose `Slug` header is not a legal slug**, which a
  hand-created file produces. `StoreError` naming the path and the
  slug. §4.2's rule is stated of a slug rather than only of one being
  written, so it is refused when the file is opened; without that the
  entry read and only its save was refused.
- **A slug whose file name is too long for the platform.** Distinct
  from §4.2's reserved device names, which are refused on every system
  before anything is written and so never reach here. The archive
  carries at least one slug long enough to threaten the Windows path
  limit once the folder path is added, which
  `tests/test_store_archive.py` measures. The write fails and says so;
  it is not silently truncated, because a truncated name could collide
  with another entry's and lose one. The remedy is a shorter path to
  Pressless's own folder, which the writer chooses when he chooses
  where the program file lives (`docs/design.md` § Where everything
  sits on disk).
- **`publish` on a slug that is not a draft, or `unpublish` on one
  that is not published.** `EntryNotFound`. Nothing is moved.
- **`publish` onto a slug the published folder already holds, or
  `unpublish` onto one the drafts folder holds.** `SlugInUse`.
  Nothing is moved and neither file is opened. Without this a rename
  would silently destroy the entry at the destination, which §3
  decision 5's uniqueness rule is meant to make impossible and this is
  what enforces.

## 7. Tests

Two files.

`tests/test_store.py`, unlabelled — it needs no fixture beyond a
temporary directory and must run everywhere. At least one test per
invariant in §5 — at least, because INV-9 also carries the test that
bounds it. Some rules here have no invariant and are covered by tests
§10's table names instead: §4.2's reserved device names and §4.3's
case-insensitive suffix.

`tests/test_store_archive.py`, needing `PRESSLESS_ARCHIVE` and skipped
without it, as `tests/test_marks_archive.py` is. **It skips a second
time wherever the sibling generator decision 4 names is unreachable**,
which includes the isolated checkout the pre-push hook builds, so a
green push proves nothing about it either. It reads the real
WordPress export, writes every entry through the Store into a
temporary folder, reads them all back, and asserts the round trip is
faithful. **It covers everything Import brings — the published
entries, and the drafts and private posts that arrive as drafts — not
the published alone**, because the round trip is complete only over
everything Import brings. It REPORTS a cross-folder collision rather
than asserting its absence: decision 5 records that the archive holds
one, and §10 says why no round trip can fail on it. **It reports an
entry whose slug resolves to a reserved device name the same way**,
rather than failing on the `StoreError` `write` raises — §4.2 requires
it reported rather than renamed, and PRESS-0007 is where it is
resolved. It resolves slugs by decision 4's rule and no other. It also prints the
archive's measurements this spec relies on rather than stating them
here: how many entries carry no title, how many carry no slug, how
many share a day, the longest slug, and whether any two resolve to
one slug. Those numbers are evidence and they move; the test is where
they live.

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
  an entry silently. Failing loudly is recoverable and says what to do.
- **Folders per date, mirroring the address —
  `published/YYYY/MM/DD/<slug>.txt`.** Removes the collision question
  entirely, since it is exactly the site's own key. Rejected because
  it buries every entry several folders deep, which is the opposite of
  the ordinary folder S3 promises, and because it lengthens the path
  this design already has to fail on. §3 decision 5 takes the cost
  instead, where it is one stated rule.
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
| INV-10 | `tests/test_store.py::test_a_move_never_overwrites` |
| The whole archive surviving a round trip (§7) | `tests/test_store_archive.py` — **but it skips wherever the export is absent AND wherever decision 4's sibling generator is unreachable (§7), so neither a green CI run nor a green push says anything about it** |
| That the slug stored here is the last segment of the address the live site serves (§3 decision 4) | **half** — the archive test proves the Store keeps whatever it was handed; nothing proves Import hands it the resolved value. PRESS-0007 is where that is decided |
| That no two entries in ONE folder want one slug (§3 decision 5) | `tests/test_store_archive.py` — `write` is create-or-replace within its own folder, so a same-folder collision loses an entry and the round trip comes back short |
| That no two entries want one slug ACROSS the folders (§3 decision 5) | **nothing can** — both files survive in different folders, so no round trip can fail on it. The archive test reports the one the archive has; PRESS-0007 is where it is resolved |
| That Import stops rather than overwriting if two entries ever do collide (§3 decision 5) | **nothing here** — `write` is create-or-replace by design, so the Store cannot tell a correction from a collision. PRESS-0007 is where that check belongs |
| That the Builder reads only the published folder (§3 decision 2) | **nothing here** — the Store cannot check who reads it. PRESS-0008 is where a breach would show, and S7 rests on it |
| That callers keep decision 5's Store-wide uniqueness | **half** — INV-10 catches a move onto an occupied slug, which is where the Store can see one. `write` does not look across folders by design, so a caller that never asks `exists` collides silently; PRESS-0007 and PRESS-0012 are where that is kept |
| That a file's name and its `Slug` header agree (§4.4) | **nothing** — no invariant covers it, and the archive test cannot: it writes through the Store, so its names always match. Worth an invariant the first time a hand-rename is seen |
| LF endings and atomic replace behaving this way on Windows | **nothing** — this suite runs on Linux, and `os.replace` is documented atomic on both. PRESS-0022 stages the built executable to a Windows box, which is the only place it would be observed |
| The Windows path limit (§6) | **nothing** — same reason. The failure mode is named so that it is recognised rather than diagnosed |
| §4.2's reserved device names | `tests/test_store.py::test_every_windows_device_name_is_refused_and_near_misses_are_not`, which asserts the whole set rather than one member, plus six near misses; and `::test_a_reserved_name_is_refused_before_anything_is_written` for `path_for` and `exists`. INV-9's own test carries the case §5 names |
| §4.2's rule that the header carries only what the entry has | `tests/test_store.py::test_an_absent_recognised_field_is_not_written_back`, which asserts the emitted bytes rather than a re-read — a re-read cannot see the difference, since an omitted line and an empty one parse alike, so an assertion on the round-tripped `Entry` passes against either |
| §4.3's case-insensitive suffix | `tests/test_store.py::test_the_suffix_is_matched_ignoring_case_and_the_two_views_agree`, which asserts `list_slugs` and `exists` TOGETHER — the defect was the pair disagreeing, so either alone passes against a half-fix |
| That a reserved name is refused on WINDOWS rather than merely refused | **nothing** — this suite runs on Linux, so what is proved here is that the Store refuses the name, not what Windows would have done with it. PRESS-0022 is where that becomes observable |

## 11. Cross-doc impact

- `CLAUDE.md` — the state block. § Build and test already names
  `tests/test_store_archive.py` among the files skipped in CI, so
  nothing is owed there.
- `docs/standards/versioning-overrides.md` — already updated: its Store
  bullet records this spec's half of the layout as a breaking surface.
  PRESS-0006 still chooses the rest, which is PRESS-0006's to record.
- `CHANGELOG.md` — an entry when it ships.
- No sibling spec changes. PRESS-0001 is read but not altered; ADR-0001
  is implemented, not amended.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-27 | 3, cold — genre pinned `spec`; packet carried ADR-0001, four `design.md` sections, the signs of success, PRESS-0001's surface, `settings.py::save`, `build_blog.py`'s `Post` and `safe_slug`, and archive measurements taken that day | 1 | 4 | 4 | 2 | **Eleven verified, eleven fixed, none dismissed.** **All three lanes found two of them.** The Q1 was mine and structural: the draft called the slug the address, where the live address is `blog/YYYY/MM/DD/<slug>` — so a flat folder silently imposed uniqueness the site does not require. Stated as a deliberate rule instead. **The most expensive would have blocked Import**: INV-9 refused a comma in any field, and archive titles carry them. **Two fixes came from reading the design rather than the draft** — undo turns an entry into a draft, so the surface needed the reverse move, and a move that overwrites destroys work silently, which is now INV-10. Also settled: who creates the two subfolders, what the list separator is, and a constant for the recognised field names that INV-8 had nothing to bind to. A fixture asked for a newline in a title its own INV-9 refuses. |

| 2 | 2026-08-27 | 3, cold — identical brief; packet rebuilt whole from disk and extended with the archive's comma-in-title count, which loop 1 had to measure mid-run | 2 | 4 | 3 | 2 | **Eleven verified, eleven fixed, none dismissed. Cap reached (2 for a spec); the tail is empty and the run exits. A CALM cap — five of the eleven landed on text loop 1 wrote**, checked against its ledger rather than recall. **The worst was found by reading the design rather than the draft**: Import brings the drafts and private posts too, so the population is wider than loop 1 measured, and a large share of them carry no slug at all — which §4.2 required. Re-measured over all three statuses: still nothing collides. **The sharpest needed executing.** INV-6 asserted bytes to catch an implementation that names no encoding; run on Linux, the unnamed defaults already produce UTF-8 and LF, so the test went green against exactly the code it rejects. It now asserts the call. Also settled: the legal slug set, unpinned, admitted `..` and wrote outside the handed folder; uniqueness was stated as a Store property nothing enforced; the slug lived in file name and header with no authority named; and INV-9 left an unrecognised field free to carry a newline, breaking ADR-0001's promise in the act of keeping it. One false rationale of mine deleted — INV-3's interruption half does catch a direct write. |
| 3 | 2026-09-02 | 3, cold — genre pinned `spec`; packet carried four `store.py` windows, ADR-0001 whole, two `design.md` sections, the sibling specs by outline and both store test files by outline. Windows behaviour declared an unrunnable region | 3 | 1 | 3 | 0 | **Seven verified, five fixed, one dismissed, one deferred.** Trigger: the 2026-09-02 amendment adding the reserved-device-name exclusion and the case-insensitive suffix rule. **All three lanes independently found the same two items**, the strongest agreement this gate produces. The sharpest is lane A's alone and was confirmed by execution rather than reading: *"That is what `safe_slug` already yields, so every live address satisfies it"* was carried onto a clause `safe_slug` does not enforce — run against the real generator, `safe_slug("NUL")` returns `nul` and `safe_slug("LPT9")` returns `lpt9`, so a title CAN resolve to a refused slug and PRESS-0007 must handle it. The amendment had told Import the opposite. **The case-insensitive rule named `list_slugs` and nothing else**, so an implementer would have folded case there and left `path_for` exact — producing the same disagreement in the other direction on Linux; it now says which operations fold and states the cost. **Two pre-existing Q3s fixed:** what a blank line is on READ (the code accepts both spellings and the document directed neither), and that the one-line rule reaches an unrecognised field's NAME, which the code guards and §4.2 did not mention. **One pre-existing Q1 fixed from a lane's disclosed session knowledge:** §7 and §10 named one skip condition for the archive test and there are two — the export, and decision 4's sibling generator, unreachable in the pre-push checkout — so a green push proved less than the document claimed. **Dismissed as immaterial:** all three lanes reported that no device-name refusal exists in `store.py`. True, and the gate runs before implementation by design, so the implementer builds it either way; PRESS-0067 item 2 stays open until it lands. **Deferred to PRESS-0060:** INV-4's byte-identity claim against `read`'s `value.strip()` — verified and material, but its other half (header lines the round trip injects) is an open question this gate may not settle. **Collateral filed, not carried:** PRESS-0004 §7 and PRESS-0006 §7 understate their own archive tests' skip conditions the same way §7 here did. |
| 4 | 2026-09-02 | 3, cold — identical brief; packet rebuilt whole from disk and extended with a window on `_refuse_illegal_slug`, the gap two loop-3 lanes named. Windows behaviour again an unrunnable region | 4 | 1 | 2 | 0 | **Seven verified, seven fixed. Cap reached (2 for a spec); the tail is empty and the run exits.** **Three of the seven landed on text loop 3 wrote** — a moderate share, so a calm cap rather than an oscillating one. **All three lanes reported the same thing loop 3 dismissed**: §4.2's device names and §4.3's suffix rule describe code that does not exist. Loop 3 dismissed it as immaterial on the ground that the implementer builds it either way; said twice by six independent reads, the DISPOSITION was wrong rather than the finding — §10's job is to say what a green suite proves, and it was silent. Two rows added naming both as unenforced and citing PRESS-0067. **The sharpest of loop 3's own collateral:** *"Matched exactly, `list_slugs` was blind to a file the existence check could see"* was written unscoped and is true on Windows only — on Linux both are blind together, so a reader there would fail to reproduce it and doubt the rule. **Loop 3's other collateral:** *"PRESS-0007 handles the refusal"* said nothing about WHAT Import substitutes, while §7 forbids the archive test any rule but decision 4's — so that test could not have written such an entry at all. Measured while fixing it: no entry in the export resolves to a reserved name, so the new refusal costs the archive test nothing today. **Three pre-existing:** INV-4's *byte-identical* against `read`'s `value.strip()` — measured, `X-Note:  spaced  ` reads back `('X-Note', 'spaced')` and re-emits as `X-Note: spaced`, so an implementer taking the word literally builds a different `extra` contract; §7 implying the archive test ASSERTS cross-folder uniqueness where §10 says nothing can and decision 5 records the archive already breaking it; and `exists` given a total-looking `bool` contract when `path_for` raises `StoreError` on an illegal slug — measured — which is PRESS-0012's normal case, since its input is a name the writer typed. **Filed, not carried:** ADR-0001 and `design.md` still promise unrecognised fields *byte-for-byte*, so that claim now lives in three documents and two of them are another gate's. Added to PRESS-0060. **Across both loops of this run, half the verified findings fell inside the amended span and half were pre-existing** — as much audit as gate. |
| 5 | 2026-09-03 | 3, cold — genre pinned `spec`; packet carried six `store.py` windows, the versioning-overrides and ADR-0001 passages, and the measured aware/microsecond round trips | 3 | 3 | 1 | 1 | **Eight verified, eight fixed, none dismissed.** Trigger was the 2026-09-03 Date amendment (PRESS-0067 item 6). **Two lanes each found both §11 bullets false** — § Build and test names three skipped files including this spec's, and the versioning-overrides bullet was already updated, so an implementer working the ship checklist would have edited correct text and made a true count false. **Three landed on the amendment itself:** it refused an aware `datetime` without saying how the offset comes off, leaving Import and §7's archive test free to drop it and convert it and disagree about the address near midnight; its new INV-9 case asserted only that the write raises, not that the folder is unchanged, so a refusal placed after the temporary file exists would have passed it; and it justified truncation by *rounding*, which `strftime` does not do. **Two were pre-existing and both were run rather than reasoned.** INV-9's refusal list omitted the three unrecognised-NAME refusals the code has performed since PRESS-0048, and INV-4 read literally called them a breach — measured, a duplicate `Title` does replace the entry's own, the read being last-wins. And INV-5 and INV-6 disagreed about a CRLF body, which §4.2 makes reachable: executed, the code already emits an LF header and returns the body's own `\r\n` untouched, so the ambiguity was the document's alone. §7's one-test-per-invariant line was left behind by the tests added since — the same drift PRESS-0001's loop 4 records. |
| 6 | 2026-09-03 | 3, cold — identical brief; packet rebuilt whole from disk | 0 | 3 | 0 | 1 | **Four verified, four fixed, none dismissed. Cap reached (2 for a spec); the tail is empty and the run ships.** **All three lanes found the same [Q4], and it was loop 5's own fix**: the claim that asserting the folder unchanged stops an aware-`Date` refusal being placed inside the write path. Measured false — every route out of `_write_atomically` discards the temporary, so a late refusal passes that assertion too, and the lone-surrogate case four lines below endorses exactly such a placement. The sentence is deleted; the folder assertion stands as the ordinary refusal check. **A second landed on loop 5 too:** the amendment named the harm as a whole-hour reorder, which its own remedy reproduces byte-for-byte — dropping the offset is what the silent write already does. The harm is the silence, and the refusal buys a decision rather than the offset back. **Two pre-existing.** §4.2 promised §7's archive test would REPORT an entry resolving to a reserved device name, and §7's reported-not-asserted list named only the cross-folder collision, so a test built from §7 would fail on the `StoreError`. And §4.2 claimed ADR-0001's promise is that *nothing is dropped or altered* and that it holds, while ADR-0001 says *preserved byte-for-byte* and the same bullet strips spacing and re-spells the separator; quoted as written, with the spacing departure stated. **A cap on the violent side — half of this loop landed on text loop 5 wrote — but both were RATIONALE, not the rule**: what §4.2 decides (refuse a zone, truncate a fraction) survived both loops unchanged. Over the run, 5 of 12 findings fell inside the amendment that armed the gate, so the other 7 were audit. Routed to implementation. |

## 13. Resource cost

No new dependency; the standard library alone. The Store holds files
and no memory state, and `list_slugs` reads names rather than bodies,
so listing does not grow with what an entry contains. The archive is
the largest population this will ever hold in one folder and it is
small enough that no cap or eviction rule is needed —
`tests/test_store_archive.py` is what would show that changing.
