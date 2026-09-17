# PRESS-0008 — The Builder: the Store and Settings become the site folder

**Status:** accepted (2026-09-13). Built 2026-09-17.
**Kind:** implement.
**Source:** ROADMAP PRESS-0008 (`docs/design.md` § The parts, § What may
depend on what).

**Blocked by:** PRESS-0001, for the two Settings fields §3 decision 2 adds;
PRESS-0007 decision 10, for the fixed pages and furniture the archive run
builds.
**Blocker for:** PRESS-0015, PRESS-0016, PRESS-0021, and PRESS-0007's
fixed pages and furniture (§3 decision 5).

Layman: the part that turns his files into the finished website, page by
page, at the same addresses the site has today — and never lets a draft
onto it.

## 1. Goal

After this ships, one call turns the Store and Settings into a finished site
folder: every page the live site serves today, at the same address, built
through Marks, plus `content/`, the sitemap and `robots.txt`. The Face can
hand that folder to the Publisher, and a preview build lands in a folder of
its own.

## 2. Problem

1. **Nothing makes the site.** The Store, Marks and Settings exist, and the
   only thing that turns entries into pages is today's generator in the
   sibling workspace, which reads the WordPress export rather than the Store.
2. **Other parts wait on what the Builder writes.** The Publisher refuses
   strays it can recognise and asks the Builder to declare the rest
   (PRESS-0009 §4.4). Setup derives the untouchable list by removing what the
   Builder produces (`docs/design.md` § What may depend on what). Undo writes
   `content/` back into the Store (PRESS-0015). Import carries the fixed
   pages and furniture in whatever shape the Builder fills (PRESS-0007
   decision 10).
3. **S7 has one holder.** Rule 4 makes the Builder the only part that can
   keep a draft off the site.
4. **A published page's address is a breaking surface**
   (`docs/standards/versioning-overrides.md` § The live site). The first
   publish replaces every page today's generator wrote; a moved address is
   found by a reader.

## 3. Scope decisions (agreed with the user)

1. **A Daily Prompt entry the filter excludes is copied into `content/` and
   is on no page.** Decided by the user 2026-09-11 (PRESS-0008 roadmap
   note), so an undo keeps it published and the filter stays reversible.
2. **(decided here) Settings gains `site_name` and `site_address`.** A page
   title carries the site's name and the sitemap needs its absolute address.
   Both are facts about the site, which is Settings' charter, and neither may
   be written into this public repository's code. PRESS-0001 is amended
   before this is built (§11).
3. **(decided here) The Builder does not produce `assets/`.** The site's
   stylesheets, script and images stay what they are. By the design's own
   rule an entry the Builder does not produce is untouchable, so setup's
   derivation protects `assets/` and the Publisher never changes it. Nothing
   in S1 to S11 asks him to edit a stylesheet, and a Store kind for one would
   amend two accepted documents for no sign of success. §8 records it.
4. **(decided here) Web copies of photographs go in `photographs/` under
   their Store names.** They cannot go under `assets/` (decision 3), and the
   Store's names carry no upload folder to rebuild today's addresses from
   (PRESS-0007 decision 6).
5. **(decided here) A fixed page keeps today's marker comments, with nothing
   between them, and the Builder fills them.** This settles PRESS-0007
   decision 10. §4.4 gives the shape Import writes.
6. **(decided here) Comments render flat, in the order the file holds them,
   as today's site shows them.** Threading would change what readers see, and
   nobody asked for it.
7. **A category's label is its slug with each hyphen a space and the first
   letter upper case.** Agreed with the user 2026-09-13. Today's labels are a table in the
   generator's code, and the Store holds only the slug. The archive run
   prints every label that differs from today's (§7).
8. **(decided here) A page's links to the site's stylesheets carry no `?v=`
   stamp.** The stamp hashed files under `assets/`, which the Builder does
   not read (decision 3).

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/builder.py

ROOT_OUTPUT = ("index.html", "pages", "blog", "photographs", "content",
               "sitemap.xml", "robots.txt")
PER_PAGE = 20
LONGEST_SIDE = 1600

@dataclass(frozen=True)
class Built:
    files: tuple[str, ...]      # every file written, relative to `into`, "/"-separated, sorted
    filtered: tuple[str, ...]   # published slugs the Daily Prompt filter kept off every page

@dataclass(frozen=True)
class Html:
    kind: str                   # store.PAGES_FOLDER or store.FURNITURE_FOLDER
    name: str
    html: str

class BuildStopped(Exception): ...        # the Store holds something that cannot be built
class SiteFolderUnusable(Exception): ...  # `into` could not be replaced

def web_photograph(name: str) -> str: ...   # "photographs/" + the name, percent-encoded
def build(folder: Path, settings: Settings, into: Path, *,
          photo_src: PhotoSrc | None = None,
          change: Entry | Html | None = None) -> Built: ...
```

`folder` is Pressless's own folder, which holds the Store. `into` is
`settings.site_folder` for a publish and the preview folder for a preview;
the Face chooses (`docs/design.md` rule 1).

**`photo_src` is `None` for a publish.** The Builder then writes web copies
(§4.6) and every picture's address is `web_photograph(name)`, prefixed with
`../` once per folder the page sits below the root. A preview passes the
Face's rule, and the Builder writes no web copies and uses that rule's
address as given.

**`change` is what the Face hands the Builder for a preview**
(`docs/design.md` § What may depend on what): an `Entry` built as though
published, in place of any published entry with its slug; or an `Html` page
or furniture file in place of the Store's file of that name. Nothing is
written to the Store, and `content/` is copied from the Store alone. A
publish never passes it; that is the Face's rule and §10 says nothing here
can check it.

`web_photograph` is the naming rule for web copies, and this is the one place
it is written. The file is `photographs/<name>`; the address encodes the name
with `urllib.parse.quote(name, safe="")`.

`build` returns only after `into` holds the new site. Both failure types
leave `into` as it was (§4.8). A `StoreError` or `StoreNotice` the Store
raises passes through unchanged, so the Face's sentences for them apply.

### 4.2 What is built

- **Entries.** `store.list_slugs(folder, draft=False)`, each read with
  `store.read`, plus an `Entry` passed as `change`. An entry whose
  tags match `settings.daily_prompt_filter` by `fnmatch.fnmatchcase`, tag by
  tag, is **filtered**: it is in `content/` and in `Built.filtered`, and on no
  page, listing or sitemap line.
- **Order.** Newest first by `date`, then by slug ascending where two dates
  are equal. Every listing takes this order.
- **Nothing else is read**: not the drafts folder, not the bin, not the
  site folder's previous contents.

### 4.3 Where each page goes

Every page is a folder holding `index.html`, as today, except the fixed
pages, which keep today's file names. All links are relative.

```
index.html                               the fixed page named "index"
pages/<name>.html                        every other fixed page
blog/YYYY/MM/DD/<slug>/index.html        an entry, dated by its own date
blog/index.html                          the journal, newest first
blog/page/<n>/index.html                 its page n, for n ≥ 2
blog/category/<category>/index.html      plus page/<n>/index.html
blog/tag/<tag>/index.html                plus page/<n>/index.html
blog/archive/index.html                  one page, a section per year, newest year first
photographs/<name>                       a web copy (§4.6)
content/...                              §4.7
sitemap.xml, robots.txt                  §4.9
```

A listing holds `PER_PAGE` entries per page. A category or tag page exists
only where an unfiltered entry carries it.

**A category or tag becomes a folder name, so it must pass the Store's slug
test.** The Builder asks `store.path_for(folder, name, draft=False)`, which
raises `StoreError` on a name outside the slug set (PRESS-0005 §4.1); the
Builder turns that into `BuildStopped` naming the entry and the name.

**The page itself is today's.** Its shell, heading, date line, category and
tag chips, excerpt, pagination links and comment list are what
`tools/build_blog.py` in the sibling workspace writes at that address, with
these differences: the body is `marks.render(entry.body, photo_src)`; a
listing's excerpt, and an untitled entry's teaser, are cut from the text of
`marks.parse(entry.body)`'s `Text` nodes, lines joined by a space, and
written through `marks.to_html` as one `Text`; the site's name comes from
`settings.site_name`; and decision 8's stamps are gone. INV-15's run
compares the elements it names. The generator's own code names the writer,
so it is ported, never copied: no string from it enters this repository
unread.

**A date is written the same on every system.** Month names are English and
come from a constant, and the day carries no leading zero, built from
`date.day` rather than a platform `strftime` flag. `%-d` is refused by
Windows.

**Comments** follow the body: a heading counting them, today's note that
comments are closed, then one item per comment in file order. The author is
the comment's `author`, or `Anonymous` where empty; the date is `date` as
`YYYY-MM-DD`. **The body goes through `marks.to_html`, never
`marks.render`**: the Builder splits it at blank lines into `Paragraph`s and
at newlines into `Line`s of one `Text` each. So Marks does the escaping, and
an asterisk a reader typed stays an asterisk.

### 4.4 Fixed pages and furniture

**A fixed page is written byte for byte, except between its markers.** A
marker pair is

```
<!-- HEADER:START page="About" -->
<!-- HEADER:END -->
<!-- FOOTER:START -->
<!-- FOOTER:END -->
```

The START comment's attributes are optional and space-separated:
`page="<word>"`, `animate`, `nonav`; any other attribute is kept and ignored,
as today. Whatever sits between START and END is
replaced by the filled furniture; the markers stay. A page with no markers
is written unchanged. A START with no END after it, or an END with no
START, is `BuildStopped` naming the page.

**The furniture files, as Import writes them and the Builder reads them:**

- `header` — today's header template, verbatim, with the
  `<nav class="primary…">` element `nonav` removes today replaced by the line
  `{{NAVIGATION}}`.
- `navigation` — that element.
- `footer` — today's footer template, verbatim.

**Filling one**, for a page `depth` folders below the root:

| Placeholder | Becomes |
|---|---|
| `{{NAVIGATION}}` | the `navigation` file, or nothing where the marker says `nonav`; replaced first, so the placeholders below are filled inside it too |
| `{{UP}}` | `../` repeated `depth` times |
| `{{ANIM1}}` to `{{ANIM3}}` | ` reveal-load d1`, ` reveal-load d2` and ` reveal-load d3`, each with its leading space, where the marker says `animate`; nothing otherwise |
| `{{YEAR}}` | the build's year |

The first HTML comment in `header` and in `footer` is removed, as today;
`navigation` keeps its comments. In the
navigation, the first link whose `data-nav` equals the marker's `page`, case
included, gains
`aria-current="page"`. A generated page is filled as a marker saying
`page="Journal"` would be. A furniture file the Store does not hold raises
the Store's own `StoreError`.

### 4.5 S7 — only published writing reaches the folder

The Builder never reads the drafts folder. It never
copies a draft, a draft's comments file, an original photograph or the bin
into `into`. A template is copied into `content/` and never becomes a page
(PRESS-0006 decision 3).

### 4.6 Photographs

For each picture mark in an unfiltered entry being built — top-level blocks
of `marks.parse(entry.body)`, since a block mark inside a quotation stays
literal (PRESS-0004 §4.2) — and only where `photo_src` is `None`:

1. **A name beginning with `.` is `BuildStopped`.** PRESS-0009 §4.4 refuses
   every publish carrying a dot-name segment outside an untouchable first
   segment, and `photographs` is not untouchable.
2. The original is `store.photograph_path_for(folder, name)`. Absent, it is
   `BuildStopped` naming the file.
3. **The format is the one Pillow decodes, never the file name's
   extension.** An image Pillow reports as `JPEG`, `MPO`, `PNG` or `WEBP` is
   re-encoded: rotated upright by its orientation tag, shrunk to fit
   `LONGEST_SIDE` on each side and never enlarged, and saved in its own
   format — an `MPO` as a JPEG of its first picture — carrying no EXIF, XMP
   or comment block. A JPEG is saved progressive at quality 82, as today's
   `_work/resize.py` does.
4. **A `GIF` is re-saved with every frame**, each shrunk the same way, its
   timing kept and no comment or XMP block carried. So no original is
   published (§4.5).
5. **Anything else is `BuildStopped`** naming the file. A format Pillow
   cannot open is refused rather than copied, because copying could publish
   location metadata nobody inspected.

Each web copy is written once, however many entries name it.

### 4.7 `content/`

Byte for byte, at the Store's own relative paths, so undo can write each file
back where it came from:

```
content/published/<slug>.txt     every published entry, filtered ones included
content/comments/<slug>.json     for every published entry that has one
content/pages/<name>.html
content/furniture/<name>.html
content/templates/<name>.txt
```

The bytes are read from the paths the Store's own calls return. Nothing is
parsed and rewritten on the way, so a file keeps its line endings. A preview
build writes `content/` too, and it is never published.

### 4.8 Writing the folder

1. Build everything into `<into>.pressless-new`, beside `into`.
2. On success, rename `into` to `<into>.pressless-old`, rename the new
   folder to `into`, then remove the old one.
3. On a failure before the new folder is renamed to `into`, rename
   `<into>.pressless-old` back where it exists, then remove the new folder;
   `into` is as it was. Failing to remove the old folder is not a failed
   build: the next build removes it.

Before step 1, a leftover `<into>.pressless-new` is removed; where `into`
is absent while `<into>.pressless-old` exists, the old folder is renamed back
first; and where both exist, the old folder is removed. Those two names are
Pressless's own. Nothing else beside `into` is touched.

Text is written UTF-8 with `newline="\n"`.

**Where `into` exists and holds a first segment outside `ROOT_OUTPUT`, the
build stops with `SiteFolderUnusable` before step 1 and touches nothing.** The
folder is Pressless's alone (PRESS-0009 §4.4), but a folder Settings was
pointed at by mistake is not one the Builder made, and replacing it would
delete what he keeps there.

`SiteFolderUnusable` is also raised where `into`'s parent does not exist, a
write into the new folder fails, or a rename fails.

**No message names a full path**: `into` is *the site folder* or *the
preview folder*, an entry is its slug, and any other file is its own name
(`docs/design.md` § Logging).

### 4.9 `sitemap.xml` and `robots.txt`

*The address* below is `settings.site_address` with any trailing `/`
removed.

`sitemap.xml` is a sitemaps.org 0.9 `urlset`. Its `loc` values are the
address joined to: `/` for the page `index`,
`/pages/<name>.html` for each other fixed page in name order,
`/blog/index.html`, `/blog/archive/index.html`, then
`/blog/YYYY/MM/DD/<slug>/index.html` for each unfiltered entry in §4.2's
order, with a `lastmod` of its date as `YYYY-MM-DD`. No
category, tag or listing page is listed.

`robots.txt` is exactly:

```
# Everything here is meant to be found.
User-agent: *
Allow: /

Sitemap: <the address>/sitemap.xml
```

### 4.10 What the Builder never does

- It never reaches the network (rule 4).
- It never imports the Publisher, Insights, Credentials or the Face, and
  never writes into the Store.
- It never produces HTML from marked text itself (rule 2): an entry body goes
  through `marks.render`, a comment through `marks.to_html`.
- It never writes a path whose first segment is outside `ROOT_OUTPUT`, or any
  segment beginning with `.` (PRESS-0009 §4.4).

## 5. Invariants

- **INV-1** — A draft's words reach no file in `into`, unless the Face hands
  it as `change`.
  *Test:* `tests/test_builder.py::test_no_draft_reaches_the_folder` — a Store
  holding a draft whose title, body, tag and comment each carry a sentinel,
  built without `change`; no file under `into` holds a sentinel. Built again
  with it as `change`, its page exists and `content/` still holds no
  sentinel.
  *Breaks when:* the Builder lists the drafts folder, or copies `comments/`
  whole rather than by published slug.

- **INV-2** — A filtered entry is on no page, listing or sitemap line, and is
  in `content/` with its comments.
  *Test:* `tests/test_builder.py::test_a_filtered_entry_is_kept_off_every_page`
  — entries tagged `dailyprompt-1234` and `dailyprompt` under the filter
  `dailyprompt-*`: the first is in `Built.filtered`, `content/published/`
  and `content/comments/`, and its slug is in no HTML file and not in
  `sitemap.xml`, and `blog/tag/dailyprompt-1234/` does not exist; the second
  has a page, and so does the tag `dailyprompt`.
  *Breaks when:* the filter is read as a regex or a prefix, applied to
  `content/`, or leaves a tag page listing only filtered entries.

- **INV-3** — Every page sits at §4.3's address, and a listing breaks every
  `PER_PAGE` entries in §4.2's order.
  *Test:* `tests/test_builder.py::test_pages_sit_at_their_addresses` — a
  Store of `PER_PAGE + 1` dated entries, two sharing a date, and pages
  `index` and `about`; asserts each path, page 2 of the journal holding the
  oldest, and the tie ordered by slug.
  *Breaks when:* an entry is dated by its build time, page 1 is written as
  `page/1/`, or `about` lands at the root.

- **INV-4** — `Built.files` is exactly the set of files under `into`; every
  one's first segment is in `ROOT_OUTPUT`; no segment begins with `.`.
  *Test:* `tests/test_builder.py::test_the_folder_is_what_it_declares` —
  walks `into` after a build of a Store holding every kind, and compares;
  then a picture named `.hidden.jpg` raises `BuildStopped`.
  *Breaks when:* a file is written outside `Built.files`, a new root output
  is added without `ROOT_OUTPUT`, or a dot-named photograph is copied.

- **INV-5** — A failed build leaves `into` byte-identical and leaves no
  `.pressless-new` folder, and a build never replaces a folder holding a
  first segment outside `ROOT_OUTPUT`.
  *Test:* `tests/test_builder.py::test_a_failed_build_changes_nothing` — a
  built `into`, then a Store whose last entry names a missing photograph, and
  one whose category is `Not A Slug`: each raises `BuildStopped`, `into`
  hashes the same, and no `.pressless-new` folder exists. Then an `into`
  holding `notes.txt` raises `SiteFolderUnusable` and still holds it.
  *Breaks when:* pages are written into `into` directly, the new folder
  survives the failure, or a folder Settings was pointed at by mistake is
  replaced.

- **INV-6** — Two builds of an unchanged Store in the same year write
  byte-identical folders.
  *Test:* `tests/test_builder.py::test_a_build_is_reproducible` — a Store
  with a JPEG, a PNG, tags and comments is built; a copy of it, its files
  written in reverse order, is built in a subprocess under a different
  `PYTHONHASHSEED`; the two folders are compared file by file.
  *Breaks when:* output depends on listing order, a set's order, the clock
  below the year, or an encoder setting that varies; each makes every
  publish upload unchanged files.

- **INV-7** — Every file in `content/` is byte-identical to the Store file at
  the same relative path, and nothing else is there.
  *Test:* `tests/test_builder.py::test_content_is_the_stores_own_bytes` — a
  Store whose entry, page and comments carry CRLF line endings and an
  unknown header field; each `content/` file equals its source, and no
  draft, original or bin file is present.
  *Breaks when:* an entry is re-emitted through the Store's writer, which
  normalises its header, or a line ending is translated.

- **INV-8** — A fixed page's bytes outside its marker pairs are unchanged,
  and between them sits the filled furniture of §4.4.
  *Test:* `tests/test_builder.py::test_a_fixed_page_keeps_its_own_bytes` — a
  page with irregular markup around a HEADER pair saying `page="about"
  nonav`; one with a HEADER pair saying `page="about" animate` and a FOOTER
  pair; and a page with no markers. The first's bytes outside its pairs equal
  the fixture's, both markers remain, and it holds no `<nav>`. The second's
  navigation carries `{{UP}}` filled for its depth and `aria-current="page"`
  on the link whose `data-nav` is `about`; its footer carries the build's
  year; and neither furniture file's first comment appears. The no-marker
  page is unchanged, and an unmatched START raises `BuildStopped`.
  *Breaks when:* the page is run through an HTML parser, the markers are
  dropped, or `nonav` is ignored.

- **INV-9** — A web copy exists for exactly the pictures unfiltered entries
  name; its format is the decoded one; and a re-encoded copy fits
  `LONGEST_SIDE` and carries no EXIF, XMP or comment block.
  *Test:* `tests/test_builder.py::test_web_copies_are_small_and_carry_nothing`
  — a large JPEG carrying a GPS tag, an orientation tag and an XMP packet
  holding a sentinel; a small JPEG carrying a GPS tag and a comment block
  holding the sentinel; a small PNG; a large two-frame GIF carrying a
  comment; a JPEG named `x.gif`; a file Pillow cannot open; a photograph no
  entry names; and one only a filtered entry names. The large JPEG's copy
  fits and is upright; neither JPEG's copy has a `getexif()` entry or the
  sentinel's bytes; the GIF's copy fits, keeps both frames and carries no
  comment; `x.gif` is re-encoded as a JPEG; the unreadable file raises
  `BuildStopped`; and neither of the last two has a copy.
  *Breaks when:* a small original is copied rather than re-encoded, which
  publishes its location; XMP or a comment is carried through; the
  extension decides the format; or a GIF is copied whole.

- **INV-10** — An entry body in a page is `marks.render`'s output, and a
  comment body is `marks.to_html`'s output over plain `Text`.
  *Test:* `tests/test_builder.py::test_writing_renders_through_marks` —
  replaces `marks.render` with a double returning a sentinel and asserts the
  entry page carries it; then a comment holding `*one* <b>` renders with its
  asterisks literal and its `<` escaped.
  *Breaks when:* the Builder keeps its own `wpautop`, or renders comments
  with `marks.render`.

- **INV-11** — The Builder imports nothing that reaches the network or
  another part's inside.
  *Test:* `tests/test_builder.py::test_the_builder_imports_only_what_it_may`
  — walks `builder.py`'s imports against an allowlist of full dotted names,
  as PRESS-0007 INV-10's test does: `pressless.store`, `pressless.marks`,
  `pressless.settings`, `PIL` and named standard-library modules.
  *Breaks when:* a missing photograph is fetched from the old site, or the
  Builder calls the Publisher.

- **INV-12** — A date reads the same on every system: an entry dated
  2024-03-05 shows `5 March 2024`.
  *Test:* `tests/test_builder.py::test_dates_do_not_depend_on_the_system` —
  asserts that text under the C locale, and that `builder.py`'s source holds
  no `%-` directive.
  *Breaks when:* `strftime("%-d")` is used, which Linux accepts and Windows
  refuses; this suite runs on Linux, so the source check is the half that
  fails.

- **INV-13** — `sitemap.xml` and `robots.txt` are §4.9's.
  *Test:* `tests/test_builder.py::test_the_sitemap_lists_what_readers_find` —
  a filtered entry absent, pages in name order, `lastmod` present on entries
  only, and `robots.txt` equal to §4.9's text for an address given with a
  trailing `/`.
  *Breaks when:* a filtered entry is listed, or the address is written from
  code rather than Settings.

- **INV-14** — No message the Builder raises names a full path.
  *Test:* `tests/test_failure_messages.py::test_no_builder_failure_names_a_path`
  — triggers each `BuildStopped` route and `SiteFolderUnusable` under a
  temporary folder and asserts no message holds it.
  *Breaks when:* a message formats `into` or a photograph's path.

- **INV-15** — Over the real archive, every `.html` page today's live site
  serves as `index.html`, under `pages/` or under `blog/` is built at the
  same address, with the same title, heading, date line, pagination links
  and chip addresses.
  *Test:* `tests/test_builder_archive.py::test_the_first_publish_moves_no_page`
  — Imports the archive, builds it, and compares against the live site's
  folder. It fails on a missing `.html` address or a differing element. It
  prints, and does not fail on, every other live file under a `ROOT_OUTPUT`
  segment the build does not produce, every category label whose text
  differs from today's (decision 7), and the build's duration.
  *Breaks when:* an address moves, a page is dropped, or an untitled entry's
  heading changes.

## 6. Failure modes

| What happens | What the Builder does |
|---|---|
| A category or tag is not a legal slug | `BuildStopped` naming the entry and the name; `into` unchanged |
| A picture names a missing original | `BuildStopped` naming the file |
| A picture names a dot-name, or a format §4.6 refuses | `BuildStopped` naming the file |
| Pillow cannot read an original | `BuildStopped` naming the file |
| A fixed page's markers do not pair | `BuildStopped` naming the page |
| A furniture file is absent | The Store's `StoreError`, unchanged |
| An entry file cannot be parsed | The Store's `StoreError`, unchanged |
| A listing skips a file | The Store's `StoreNotice`, passed through; the build goes on |
| `change` is an `Html` whose kind or name the Store refuses | The Store's `StoreError`, unchanged |
| `into`'s parent does not exist, or a rename fails | `SiteFolderUnusable`; `into` unchanged |
| `into` holds a first segment outside `ROOT_OUTPUT` | `SiteFolderUnusable`; nothing touched |
| The disk fills mid-build | `SiteFolderUnusable`; the new folder is removed and `into` unchanged |
| The app stops mid-build | A leftover new folder is removed on the next build (§4.8) |
| The app stops between the two renames | The next build renames the old folder back first (§4.8) |
| The app stops after the second rename | The next build removes the old folder (§4.8) |

## 7. Tests

`tests/test_builder.py` — in CI, over Stores built in a temporary folder with
small generated images. It carries INV-1, INV-2, INV-3, INV-4, INV-5, INV-6,
INV-7, INV-8, INV-9, INV-10, INV-11, INV-12 and INV-13.

`tests/test_failure_messages.py` gains INV-14's test.

`tests/test_builder_archive.py` — marked `archive`. It needs
`PRESSLESS_ARCHIVE` and `PRESSLESS_ORIGINALS`; `PRESSLESS_LIVE_SITE`, a
folder holding today's built site; and `PRESSLESS_SITE_NAME` and
`PRESSLESS_SITE_ADDRESS`, the Settings values it builds with, which identify
the writer and so cannot be written here. The gate sets those last three from
new machine-local keys `ants.pressless.liveSite`, `ants.pressless.siteName`
and `ants.pressless.siteAddress`. Its import also needs `PRESSLESS_TEMPLATES`
(PRESS-0007 §7). It skips only where one is
absent, and fails where one is present and unusable, as the other archive
tests do. It carries INV-15, and runs after PRESS-0007 carries the fixed
pages and furniture.

Each test is seen failing against a stub before the code exists, then
mutation-probed once it lands.

## 8. Alternatives considered (and rejected)

- **A Store kind for the site's stylesheets and images.** It would let
  Pressless restyle the site, which nobody asked for, at the cost of amending
  PRESS-0006 and `docs/design.md`. The untouchable rule already protects
  what the Builder does not produce.
- **Web copies at today's `assets/img/media/YYYY/MM/` addresses.** The
  Store's names carry no upload folder, and `assets/` is untouchable.
- **Every web copy saved as `.jpg`, as today.** `a.png` and `a.jpg` would
  claim one file.
- **Reusing a web copy from the previous build.** It needs state kept
  between builds, which `docs/design.md` § State forbids outside Insights.
- **Writing straight into `into`.** A failure leaves half a site, and a
  publish of it deletes the other half.
- **Rendering comments with `marks.render`.** A reader's paired asterisks
  would become italics on a page that shows them literally today.
- **Keeping the site's name and address in the Builder's code.** They
  identify the writer, and this repository is public.
- **A manifest file in the site folder.** Anything in that folder is
  published; `Built.files` declares the output without a file.

## 9. Out of scope

- Wiring `Built.files` into the Publisher, so an ordinary stray is refused —
  deferred; not yet queued. PRESS-0009 §10 records the gap.
- The `mk-rainbow` rule and the `--accent` and `--muted` variables in the
  site's stylesheet — deferred; not yet queued. Decision 3 leaves `assets/`
  outside Pressless (§14).
- Carrying the fixed pages and furniture — PRESS-0007 decision 10.
- The undo sequence — PRESS-0015.
- Deriving the untouchable list — PRESS-0021.
- The preview page and its photograph rule — PRESS-0012.
- Adding a photograph after Import — PRESS-0016.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_builder.py::test_no_draft_reaches_the_folder` |
| INV-2 | `tests/test_builder.py::test_a_filtered_entry_is_kept_off_every_page` |
| INV-3 | `tests/test_builder.py::test_pages_sit_at_their_addresses` |
| INV-4 | `tests/test_builder.py::test_the_folder_is_what_it_declares` |
| INV-5 | `tests/test_builder.py::test_a_failed_build_changes_nothing` |
| INV-6 | `tests/test_builder.py::test_a_build_is_reproducible` |
| INV-7 | `tests/test_builder.py::test_content_is_the_stores_own_bytes` |
| INV-8 | `tests/test_builder.py::test_a_fixed_page_keeps_its_own_bytes` |
| INV-9 | `tests/test_builder.py::test_web_copies_are_small_and_carry_nothing` |
| INV-10 | `tests/test_builder.py::test_writing_renders_through_marks` |
| INV-11 | `tests/test_builder.py::test_the_builder_imports_only_what_it_may` |
| INV-12 | **`Partial:`** `tests/test_builder.py::test_dates_do_not_depend_on_the_system` checks the source for `%-`; no suite runs on Windows, so another platform-dependent format passes |
| INV-13 | `tests/test_builder.py::test_the_sitemap_lists_what_readers_find` |
| INV-14 | `tests/test_failure_messages.py::test_no_builder_failure_names_a_path` |
| INV-15 | `tests/test_builder_archive.py::test_the_first_publish_moves_no_page` — **skipped in CI**; it runs where the archive, the originals and the live site are |
| That a publish build never passes `change` | **nothing here** — the Face's call; PRESS-0012 |
| That the Face never hands the preview folder to the Publisher | **nothing here** — the Face's sequence (`docs/design.md` rule 1) |
| That an ordinary non-dot stray in the site folder is refused | **nothing** — `Built.files` declares the output, and the Publisher does not read it yet (§9) |
| §4.3's page contents beyond INV-15's elements | **`Partial:`** INV-15 compares the elements it names; the rest of the shell is unchecked |

## 11. Cross-doc impact

- **PRESS-0001** — `Settings` gains `site_name` and `site_address`, with
  their shape rules and INV-6's field set. Gated before this is built.
- **`docs/design.md`** — the Settings row of § The parts gains the site's
  name and address.
- **PRESS-0007 decision 10** — Import writes the fixed pages from the live
  site's folder with §4.4's markers emptied, and the furniture from today's
  generator's template files; `run` gains both folders and `Report` a field.
- **PRESS-0011** — `face.SENTENCES` gains `BuildStopped` and
  `SiteFolderUnusable`, with the site part `UNCHANGED`, in the same change, or
  its INV-1 walk fails.
- **PRESS-0015** — undo reads `content/` at §4.7's paths.
- **PRESS-0021** — setup asks for the site's name and address and writes
  them, and removes `ROOT_OUTPUT` from the derived list, folded with
  `str.casefold()` as PRESS-0009 §4.4 requires.
- **PRESS-0004 §10** — its `mk-rainbow` row said this item adds the rule;
  §9 here leaves it outside Pressless.
- **PRESS-0022** — the packaged program carries Pillow.
- **`pyproject.toml`** — `Pillow` joins `dependencies`.
- **`scripts/local-ci.sh` and `CLAUDE.md`** — the gate sets §7's three new
  variables from their keys, and `CLAUDE.md` names the keys beside the
  archive's.
- **`CHANGELOG.md`** — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0008-builder-loop-log.md`.

## 13. Resource cost

A build holds every published entry in memory, one entry file at a time
read and rendered, and one image at a time decoded. It keeps nothing between
builds. Every web copy is re-encoded on every publish build, so a build's
time grows with the photographs published entries name; INV-15's run prints
it. A preview build writes no web copies. New dependency: Pillow, already
chosen in `docs/design.md` § The stack.

## 14. Open questions

- **The site's stylesheet defines `--accent` and `--muted` and has no
  `mk-rainbow` rule** (read 2026-09-13). A rainbow run shows unstyled on the
  live site until that rule is added to the stylesheet, which stays outside
  Pressless (§9).
- **Where a preview page's stylesheet comes from — decided by the user
  2026-09-13.** Import copies the live site's `assets/` once into
  Pressless's own folder, and the Face serves that copy for a preview and
  never publishes it (PRESS-0007, PRESS-0012). Decision 3 stands.