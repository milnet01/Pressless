# PRESS-0012 — The editor: the box, the real page beside it, and changes kept apart until he publishes

**Status:** accepted (2026-09-17). Gated for two loops, the spec cap; every
verified finding fixed, none left in the tail.
**Kind:** implement.
**Source:** ROADMAP PRESS-0012 (`docs/design.md` § The parts, § State;
discovery S2, S7, S10).

**Blocked by:** PRESS-0004, PRESS-0005, PRESS-0007, PRESS-0008, PRESS-0011 —
all shipped.
**Blocker for:** PRESS-0013, PRESS-0014, PRESS-0015, PRESS-0016, PRESS-0017,
PRESS-0128.

Layman: he opens an entry from a list, types into a box, and beside it sees
the real finished page. His words save themselves. An entry already on his
site keeps its live version until he publishes the changes.

## 1. Goal

After this ships, the Face has a list of his entries at `/`, a New entry
button, and an editor at `/edit`. The editor has fields for the title,
categories and tags, the writing box, and the real page beside it. Every
change saves itself shortly after he stops typing, and each save rebuilds the
preview. Changes to a published entry go into a working copy, so the live
version is untouched until PRESS-0013 publishes them.

## 2. Problem

1. **Nothing lets him write.** The Store reads and writes entries, and no page
   calls it.
2. **A preview rebuilds the whole site.** `builder.build` with `change` writes
   every page of the site for each preview, where the editor needs one.
3. **The Face cannot serve a preview.** `Face.add_page` wraps every answer in
   Pressless's own page and matches one exact path. A built page is a whole
   document at a nested address, and it links the site's stylesheets and his
   photographs.
4. **A published entry has one file.** `docs/design.md` rule 4 has the Builder
   write every published entry into the site folder. Saving an unfinished edit
   into that file would put it on the live site with the next publish of
   anything, which is S7 broken.
5. **Previews would count as visits.** His page furniture carries Google's
   visitor-counting script, and some pages load Spotify and YouTube players.
6. **Two specs leave this item jobs.** PRESS-0005 § 9 leaves it choosing a new
   entry's address. PRESS-0007 § 10 leaves it keeping the preview copy of the
   site's `assets/` off the live site.

## 3. Scope decisions (agreed with the user)

1. **The preview is the real finished page, built one page at a time.**
   Decided by the user 2026-09-17. The Builder gains `preview` (§ 4.2).
2. **Changes to a published entry go into a working copy.** Decided by the
   user 2026-09-17. The live version is unchanged until he publishes that
   entry (PRESS-0013).
3. **In scope: the list, New entry, and title, category and tag fields.**
   Decided by the user 2026-09-17. Deleting an entry and changing a published
   entry's address are PRESS-0128.
4. **The preview blocks everything from outside his computer.** Decided by
   the user 2026-09-17, so a preview never counts as a visit.
5. **An entry with no title gets the address `untitled`, then `untitled-2`.**
   Decided by the user 2026-09-17.
6. **A new entry is dated when he first publishes it.** Decided by the user
   2026-09-17, and PRESS-0013 sets it. Until then a draft holds the moment he
   made it, because the Store requires a date. **This item writes no marker**:
   PRESS-0013 dates every draft it publishes that is not a working copy. An
   entry undo turns back into a draft would be dated again too, so keeping its
   date is PRESS-0015's to mark.
7. **The Builder addition is specified here**, with a pointer from PRESS-0008.
   Decided by the user 2026-09-17, as PRESS-0021 added `settings.check`.
8. **(decided here) His work saves itself** about a second after he stops
   typing, and when he leaves the page. S7 says he can close the app
   mid-sentence. There is no Save button.
9. **(decided here) A working copy is a draft carrying a `Replaces` header**
   that names the published entry. The Store keeps an unrecognised header
   (PRESS-0005 § 4.2), so its shape does not change. `docs/design.md` already
   has undo keep his unpublished edits as drafts under addresses of their own.
10. **(decided here) The editor lives in the Face, as
    `src/pressless/editor.py`.** Only the Face knows what order things happen
    in (design rule 1).
11. **(decided here) This item wires no double-click.** PRESS-0013 calls
    `editor.register`, as it calls `setup.register`.
12. **(decided here) A draft's address changes only on a button**, never while
    he types the title. Every change writes a new file and bins the old one
    (`docs/design.md`), so following the title would fill the bin.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The editor's public surface

```python
# src/pressless/editor.py

PREVIEW_FOLDER = "preview"          # inside Pressless's own folder; the Face's alone
REPLACES = "Replaces"               # the header naming the published entry a copy changes
UNTITLED = "untitled"
COPY_SUFFIX = "-changes"
LONGEST_ADDRESS = 60
PREVIEW_ADDRESS = "/preview/"
ASSETS_ADDRESS = "/preview/assets/"
ORIGINALS_ADDRESS = "/originals/"

class ChangedElsewhere(Exception): ...   # the file is not the one this window last saw
class TooManyCopies(Exception): ...      # two drafts replace one published entry

def address_for(title: str) -> str: ...
def free_address(folder: Path, wanted: str) -> str: ...
def working_copy(folder: Path, slug: str) -> str | None: ...
def photo_src(name: str) -> str: ...
def register(face: Face, folder: Path) -> None: ...
```

`folder` is Pressless's own folder, the one `face.serve` was handed.

**`editor.py` adds the sentences for its two failure types to
`face.SENTENCES` when it is imported.** It imports the Face, so `face.py`
cannot import it back.

**`address_for`** removes control and format characters (Unicode categories
`Cc` and `Cf`), folds to ASCII with NFKD, lowers the case, and joins what is
left with hyphens: every run of characters outside `a-z` and `0-9` becomes one
`-`. It cuts the result to `LONGEST_ADDRESS` characters and strips hyphens from
both ends. Where nothing is left it returns `UNTITLED`.

**`free_address`** tries `wanted`, then `wanted-2`, `wanted-3` and so on. It
returns the first that `store.exists` answers `False` for. A candidate
`store.exists` refuses with `StoreError`, such as `con`, is skipped.

**`working_copy`** returns the draft whose `Replaces` value equals `slug`, as
`store.read` gives it, provided `slug` is published. It returns `None` where there is none or
`slug` is not published. Two such drafts raise `TooManyCopies`. **A draft whose
`Replaces` names no published entry is an ordinary draft**, everywhere in this
document.

**`photo_src`** is `ORIGINALS_ADDRESS + urllib.parse.quote(name, safe="")`.

### 4.2 Added to the Builder

```python
# src/pressless/builder.py — added

STYLESHEETS = ("assets/site.css", "assets/blog.css")   # every page links these, from the root
BODY_CLASS = "post-body prose"                         # the class an entry's body is written in

def preview(folder: Path, settings: Settings, into: Path, entry: Entry, *,
            photo_src: PhotoSrc) -> str: ...
```

`preview` writes the one page `build` would write for `entry` published, and
returns its path relative to `into`, `/`-separated, ending `index.html`. The
page's bytes are those `build(folder, settings, into, photo_src=photo_src,
change=entry)` writes at that path (INV-4).

- It reads the furniture and the entry's comments file from the Store, and no
  other entry.
- It writes no web copy of a photograph, and uses `photo_src` as given.
- It applies no Daily Prompt filter: a preview shows the page whatever its
  tags.
- It refuses a category or tag that cannot be part of an address with
  `BuildStopped`, as `build` does.
- It keeps PRESS-0008 § 4.8's order: settle an interrupted run, refuse a folder
  it did not make, write into `<into>.pressless-new`, then swap. So each
  preview replaces the last, and `into` holds only that page.

`page` links `STYLESHEETS`, and `entry_page` writes the body in `BODY_CLASS`,
rather than naming them, so the editor uses what the Builder uses.

### 4.3 Added to the Face

```python
# src/pressless/face.py — added

@dataclass(frozen=True)
class Reply:
    body: bytes
    content_type: str               # sent as given
    status: int = 200
    location: str | None = None     # sent as Location

Page = Callable[[Request], str | Reply]    # widened
Locate = Callable[[str], Path]

FILES_POLICY = ("default-src 'self'; img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; font-src 'self'; "
                "script-src 'self'; connect-src 'self'; frame-src 'none'; "
                "object-src 'none'; base-uri 'none'; form-action 'none'")

def within(folder: Path) -> Locate: ...

class Face:
    def add_files(self, prefix: str, locate: Locate) -> None: ...
```

**A page returning a `str`** is wrapped and sent as today, and now carries
`Content-Security-Policy: frame-src 'self'`, so a frame on a Face page can only
show an address the Face serves. **A page returning a
`Reply`** is sent as it is: its status, its `Content-Type`, its `Location` when
set, and `Cache-Control: no-store`.

**`add_files`** answers `GET` requests whose path starts with `prefix`, which
ends in `/`. A registered page's exact path is matched first; then the longest
matching prefix. The Face's boundary checks run before either (PRESS-0011
§ 4.5). For the rest of the path after the prefix, the Face:

1. percent-decodes it as strict UTF-8;
2. answers 404 if it holds a NUL or a backslash, or if any `/`-separated
   segment is empty, `.` or `..`;
3. calls `locate` with it, and answers 404 if `locate` raises anything;
4. answers 404 unless the returned path is a regular file;
5. sends the file's bytes with status 200.

A 404 here is not a failure: nothing is logged and no sentence is shown.

**Every file response carries** `Content-Security-Policy: FILES_POLICY`,
`X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. The policy is
what keeps Google's script, and Spotify and YouTube players, out of a preview
(§ 3 decision 4). The page itself is not rewritten, so it stays the Builder's
bytes.

**Its `Content-Type`** comes from the suffix, ignoring case:

| Suffix | Type |
|---|---|
| `.html` | `text/html; charset=utf-8` |
| `.css` | `text/css; charset=utf-8` |
| `.js` | `text/javascript; charset=utf-8` |
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.gif` | `image/gif` |
| `.webp` | `image/webp` |
| `.svg` | `image/svg+xml` |
| `.ico` | `image/x-icon` |
| `.woff2` | `font/woff2` |
| `.woff` | `font/woff` |
| anything else | `application/octet-stream` |

A fixed table, because `mimetypes` reads the Windows registry, which another
program can change. Source:
https://docs.python.org/3/library/mimetypes.html#mimetypes.init

**`within(folder)`** returns a `Locate` that joins the rest onto `folder`,
resolves it strictly, and raises unless the result sits inside
`folder.resolve()`. That refuses a link inside the folder pointing out of it.

### 4.4 The routes

`register` adds these. Every Store and Settings call runs inside
`face.capture()`, and its notices are shown. Every write, and every preview
build, runs under one lock held by the registered pages. Every page is
registered with `publishing=False`.

| Route | What it does |
|---|---|
| `GET /` | the list (§ 4.5) |
| `POST /new` | makes a draft (§ 4.6), then 303 to `/edit?slug=<its address>` |
| `GET /edit?slug=` | the editor, and a preview of what it opens (§ 4.7) |
| `POST /save` | saves and previews (§ 4.8) |
| `POST /address` | changes a draft's address (§ 4.9) |
| `POST /discard` | bins a working copy (§ 4.10), then 303 to `/edit?slug=<the published entry>` |
| `GET /preview/assets/…` | `within(folder / paths.PREVIEW_ASSETS)` |
| `GET /preview/…` | `within(folder / PREVIEW_FOLDER)` |
| `GET /originals/<name>` | `store.photograph_path_for(folder, name)` |

Every `POST` body is `application/x-www-form-urlencoded`, read with
`urllib.parse.parse_qs`, as setup's is.

`GET /` replaces the page PRESS-0011 put there. The originals route asks the
Store where a photograph sits, so the Face never composes a Store path (design
rule 7).

### 4.5 The list

Drafts, then published entries, each newest date first, ties by address. Each
row shows the title, or *untitled*, and the date, and opens `/edit?slug=`.

- **A working copy is not listed as a draft.** Its published entry's row says
  its changes are not on the site yet.
- **A file the Store cannot read** is listed by its address, marked as one
  Pressless cannot open. The first such failure is shown through `Face.fail`
  above the list. The list is still shown.
- A New entry form with one field, the title.
- After the entries, his fixed pages and the furniture:
  `docs/specs/PRESS-0014-fixed-pages.md` § 4.4.

### 4.6 A new entry

`POST /new` with `title`. The draft is `Entry(slug=free_address(folder,
address_for(title)), title=title.strip(), date=datetime.now()` with its
microseconds dropped, empty categories, tags and body, no extra fields)`,
written with `store.write(..., draft=True)`.

### 4.7 The editor page

`GET /edit?slug=<slug>` finds the file:

| What holds `slug` | What opens |
|---|---|
| a draft | that draft |
| a published entry with a working copy | 303 to `/edit?slug=<the copy>` |
| a published entry with none | the published entry, which the first save copies |
| neither | `EntryNotFound`, through `Face.fail` |
| a published entry with two copies | `TooManyCopies`, through `Face.fail` |

The page carries the file's address, whether it is a draft, and `base`: the
SHA-256 hex digest of the file's bytes as read. It holds the title, categories
and tags fields, the box, and the preview in an `<iframe sandbox="allow-same-origin
allow-scripts">`. Categories and tags are shown joined by
`store.LIST_SEPARATOR`.

**Opening builds the preview.** Under the lock, `GET /edit` runs § 4.8 step 5
for the file it opens, so the frame starts at that page, or holds the failure
in its place. A published entry previews as itself. It writes nothing but the
preview folder.

**A link followed in the preview stays out of the web.** The sandbox stops it
opening a new tab or replacing the editor, and the page's `frame-src 'self'`
stops the frame loading an address outside Pressless (§ 3 decision 4).

- **The box is a `<textarea>` whose content starts with a line break**, then
  the escaped body. An HTML parser drops one line break straight after
  `<textarea>`, so without it a body starting with an empty line would lose it
  on the first save (S2, INV-11). Source:
  https://html.spec.whatwg.org/multipage/parsing.html#parsing-main-inbody
  (a start tag whose tag name is "textarea").
- The page links `builder.STYLESHEETS` under `/preview/`, and the box takes the
  class `builder.BODY_CLASS`, so he types in the site's own font.
- A draft that is not a working copy shows its address and a Change address
  button. A working copy shows a Throw away changes button, and says its
  changes are not on the site yet. A published entry says his changes stay on
  this computer until he publishes it.

**Its script.** About a second after the last change to any field, it posts
`/save`. It never has two saves in flight; a change made during one is saved
after it. On `pagehide` it saves an unsaved change, with `keepalive`, unless a
save is already in flight; what he typed during that save is then lost (§ 6).
Opening an entry and leaving it unchanged saves nothing, so it makes no working
copy. After each reply it
takes the new `slug`, `draft` and `base`, shows the preview or the failure, and
replaces the address bar's `slug` without reloading. A reply that is not 200
stops the saving and shows its body. Every value placed in the page is escaped
with `html.escape(value, quote=True)`.

### 4.8 A save

Steps 1 to 4 are `editor.save`, and the page gains a Publish button:
`docs/specs/PRESS-0013-publish.md` § 4.1 and § 4.4.

Fields: `slug`, `draft` (`1` or `0`), `base`, `title`, `categories`, `tags`,
`body`. In order, under the lock:

1. **Read the file** at `store.path_for(folder, slug, draft=…)`. Missing raises
   `EntryNotFound`.
2. **Check it is the one this window saw.** A digest that differs from `base`
   raises `ChangedElsewhere`. For a published entry, so does a working copy
   that now exists.
3. **Make the entry.** Title stripped. Categories and tags split on `,`, each
   stripped, empties dropped. The body's `\r\n` and lone `\r` become `\n`, and
   nothing else about it changes. The date and extra fields come from the
   file. **For a published entry** the address is `free_address(folder, slug +
   COPY_SUFFIX)`, and the extra fields are the published entry's, without any
   `Replaces`, followed by `(REPLACES, slug)`.
4. **Write it** with `store.write(..., draft=True)`. The new `base` is the
   digest of the written file.
5. **Preview it.** `settings.load(folder)`, then `builder.preview(folder,
   settings, folder / PREVIEW_FOLDER, shown, photo_src=photo_src)`. `shown` is
   the entry as written, except that a working copy takes the address its
   `Replaces` names and loses every `Replaces` field.

A failure at steps 1 to 4 answers `Reply` status 409, `text/html;
charset=utf-8`, holding `face.fail(failure, publishing=False)`. Nothing is
written.

**A failure at step 5 does not undo the save.** It is shown through `Face.fail`
in the reply, in the preview's place. So is `NotSetUp`, and the `StoreError`
an install with no furniture raises (PRESS-0126).

A successful save answers status 200, `application/json`:

```json
{"slug": "…", "draft": true, "base": "…", "preview": "/preview/…" or null,
 "failure": "<fragment>" or null, "notices": "<fragment>"}
```

### 4.9 Changing a draft's address

Fields: `slug`, `base`, `address`. `address` is stripped. Under the lock:

1. **Refused, writing nothing**, with a hint beside the field: an address
   `store.exists` refuses with `StoreError`; an address another entry holds; a
   `slug` that is not a draft, or is a working copy. The same address as
   `slug` writes nothing and gives no hint.
2. A digest that differs from `base` raises `ChangedElsewhere`, answered as
   § 4.8's failures are.
3. **Write the entry at the new address**, as a draft.
4. **Move its comments file**, if the old address has one:
   `store.write_comments` at the new address, then `store.move_to_bin` on the
   old file (`docs/design.md`: an entry's comments file follows it).
5. **Bin the old entry file** with `store.move_to_bin`.

The order means an interruption leaves two copies, never none. The reply is
§ 4.8's JSON, with `"hint"` added, and `preview` and `failure` null.

### 4.10 Throwing away a working copy

Fields: `slug`, `base`. Under the lock, `ChangedElsewhere` unless `slug` is a
working copy whose digest equals `base`, answered as § 4.8's failures are.
Then `store.move_to_bin` on it. The published entry is not touched.

### 4.11 What the editor never does

- It never writes into `published/`, and never writes a published file.
- It never builds into `settings.site_folder`, and never hands a folder to the
  Publisher.
- It never unlinks a file; the bin is how anything goes (`docs/design.md`).
- It never changes a published entry's address.
- It never keeps an entry in memory between requests (`docs/design.md`
  § State).
- It never rewrites a built page before serving it.
- It never hands `preview-assets/` to the Builder or the Publisher.

## 5. Invariants

The tests below are in `tests/test_editor.py` unless named otherwise. Each runs
the routes through `face.serve(tmp_path, open_browser=False)`, as
`tests/test_setup.py` does, over a Store made with `store.write` and furniture
made with `store.write_html`.

- **INV-1** — Editing a published entry never changes it. Saves write one
  working copy, and later saves write that copy.
  *Test:* `test_a_published_entry_is_untouched_by_its_edits`. It opens a
  published entry, saves twice, and asserts the published file's bytes are
  unchanged. `working_copy` names one draft, and opening the published entry
  again answers 303 to it.
  *Breaks when:* a save writes the file it read; or the second save makes a
  second copy.

- **INV-2** — A save over a file this window did not see writes nothing. That
  includes a published entry that gained a working copy.
  *Test:* `test_a_save_from_a_stale_window_writes_nothing`. Two saves with the
  same `base` on one draft: the second answers 409 with `ChangedElsewhere`'s
  sentence, and the file holds the first. Then two saves with the same `base`
  on one published entry: the second answers 409, and there is one copy.
  Then a published entry rewritten on disk between opening and saving: the
  save answers 409 and makes no copy.
  *Breaks when:* the digest check is dropped, or a published entry is checked
  only for an existing copy.

- **INV-3** — `working_copy` counts only drafts replacing a published entry.
  *Test:* `test_a_working_copy_replaces_a_published_entry`. A draft whose
  `Replaces` names a draft is an ordinary draft; one naming `seaside` is
  seaside's copy; two raise `TooManyCopies`.
  *Breaks when:* the published check is dropped, which counts the first draft
  as a copy; or the search stops at the first match, which hides the second.

- **INV-4** — The preview is the Builder's page.
  *Test:* `tests/test_builder.py::test_a_preview_is_the_page_build_writes`. For
  an entry with a colour mark, a photograph, a category, a tag and a comments
  file, `preview` writes bytes equal to `build(..., photo_src=…, change=entry)`
  at the returned path.
  *Breaks when:* `preview` renders the entry by its own route, or uses a
  different page shell.

- **INV-5** — A preview writes one page, and no web copy.
  *Test:* `tests/test_builder.py::test_a_preview_writes_one_page`. After two
  previews of different entries, `into` holds exactly the second page's path.
  The Store holds a photograph named by the entry, and no `photographs` folder
  exists in `into`.
  *Breaks when:* `preview` calls the whole build, or keeps the last preview.

- **INV-6** — Nothing a preview uses reaches the site folder.
  *Test:* `test_a_save_never_touches_the_site_folder`. With Settings saved and
  its `site_folder` absent, saves of a draft and of a published entry leave
  `site_folder` absent. `folder / PREVIEW_FOLDER` holds the page.
  *Breaks when:* the preview is built into `settings.site_folder`.

- **INV-7** — File serving never answers outside its folder.
  *Test:* `tests/test_face.py::test_files_never_leave_their_folder`. A folder
  mounted with `within`, with a file beside it and a link inside it pointing
  out. `..`, `%2e%2e`, `a%2f..%2f..`, a backslash, `%00`, an empty segment and
  the link each answer 404 without the outside file's bytes. A file inside
  answers 200, and a mount at a longer prefix inside it answers its own file.
  Then a mount whose `Locate` joins without confining, so only
  § 4.3 step 2 can refuse: `%2e%2e/outside.txt` answers 404.
  *Breaks when:* step 2 is skipped or runs before decoding, which lets the
  plain join serve the outside file; or `within` does not resolve, which lets
  the link through.

- **INV-8** — Every file response carries the policy, `nosniff` and the table's
  type.
  *Test:* `tests/test_face.py::test_files_carry_the_policy`. The test writes
  the policy string out, rather than importing `FILES_POLICY`. An `.HTML`, a
  `.css`, a `.js` and a `.txt` each carry it, and their types are the table's.
  `mimetypes` names the last two `application/javascript` and `text/plain` on
  Linux, so a lookup there fails.
  *Breaks when:* the header is missing on any response, or the type is read
  from `mimetypes`.

- **INV-9** — A `Reply` is sent as it is, and a `str` is still wrapped, now
  with `Content-Security-Policy: frame-src 'self'`.
  *Test:* `tests/test_face.py::test_a_reply_is_sent_as_given`. A 303 with a
  location, and a JSON body, arrive unwrapped with their status and type. A
  `str` page arrives wrapped and carries the header, written out in the test.
  *Breaks when:* a `Reply` is wrapped, its status dropped, or the header left
  off a wrapped page.

- **INV-10** — A new entry's address comes from its title and is free.
  *Test:* `test_a_new_entry_gets_a_free_address`. Titles `"Late light — on
  the water"`, `""`, `""`, `"con"`, and a title whose address a published
  entry holds. They get `late-light-on-the-water`, `untitled`, `untitled-2`,
  `con-2` and that address with `-2`. A title of seventy letters gets sixty.
  *Breaks when:* `exists` is not asked, only one folder is asked, or a
  `StoreError` from `exists` escapes.

- **INV-11** — A save keeps every line he typed (S2).
  *Test:* `test_a_save_keeps_his_lines`. A draft whose body is `"\n  first\r\n
  second\r\rthird  \n"` is opened, the textarea's content is taken as a
  browser would, dropping one leading line break, and posted. The file's body
  is `"\n  first\n second\n\nthird  \n"`.
  *Breaks when:* the page omits the leading line break, the body is stripped,
  or `\r` is left in.

- **INV-12** — A save keeps what the form does not carry.
  *Test:* `test_a_save_keeps_the_date_and_extra_fields`. A draft with an
  extra field `Mood: blue` and a date of 2014 keeps both after a save. A
  published entry's copy keeps them too, plus `Replaces`.
  *Breaks when:* the entry is rebuilt with `datetime.now()` or no extra fields.

- **INV-13** — A preview failure does not undo a save.
  *Test:* `test_a_preview_failure_keeps_the_save`. With no settings file, a
  save answers 200, the file holds the body, `preview` is null, and `failure`
  holds `NotSetUp`'s sentence.
  *Breaks when:* the preview runs before the write, or its failure answers
  409.

- **INV-14** — Changing a draft's address moves the entry and its comments, and
  refuses what it must.
  *Test:* `test_a_draft_changes_address`. A draft with a comments file moves
  to a new address: the new files exist, and the old ones are in the bin. An
  address a published entry holds, `con`, a working copy's `slug` and a
  published `slug` are each refused with a hint and change nothing. Then, with
  `store.write` made to raise `StoreError` for the new address, the old draft
  is still in `drafts/` and the bin is empty.
  *Breaks when:* the old file is binned before the new is written, the
  comments stay behind, or a refusal writes.

- **INV-15** — Throwing away a working copy bins it and nothing else.
  *Test:* `test_throwing_away_changes_bins_the_copy`. The copy is in the bin,
  and the published file's bytes are unchanged. For an ordinary draft the same
  request answers `ChangedElsewhere` and moves nothing.
  *Breaks when:* any draft can be thrown away, or the published entry is
  touched.

- **INV-16** — The list shows a working copy under its published entry, not as
  a draft, and lists an unreadable file.
  *Test:* `test_the_list_shows_copies_and_unreadable_files`.
  *Breaks when:* every draft is listed as one, or one bad file fails the list.

- **INV-17** — The preview's photographs are the originals.
  *Test:* `test_a_preview_photograph_is_the_original`. A preview page of an
  entry naming `seaside dusk.jpg` holds `/originals/seaside%20dusk.jpg`, and
  that address answers the original's bytes. With a file at
  `photographs/nested/inner.jpg`, `/originals/nested%2finner.jpg` answers 404:
  its segments pass the Face's check, and only the Store's single-name rule
  refuses it.
  *Breaks when:* `photo_src` does not quote the name, or the route joins the
  name onto the folder itself.

- **INV-18** — Every editor route sits behind the Face's boundary.
  *Test:* `test_the_editor_sits_behind_the_faces_boundary`. `GET /`, a preview
  file and `POST /save` without the cookie answer 403. `POST /save` with a
  foreign `Origin` answers 403 and writes nothing. The same `POST /save` with
  the cookie and the Face's own `Origin` then saves.
  *Breaks when:* the editor serves through anything but `add_page` and
  `add_files`. The last request then gets 404 and nothing is saved.

`ChangedElsewhere` and `TooManyCopies` each get a sentence.
`tests/test_face.py::test_every_failure_type_has_a_sentence` walks the package
and finds them without a change.

## 6. Failure modes

| What breaks | What he sees | What is left on disk |
|---|---|---|
| Another window saved the entry first | `ChangedElsewhere`; saving stops | the other window's save |
| The file was edited by hand while open | `ChangedElsewhere`; saving stops | the hand edit |
| Two copies replace one published entry | `TooManyCopies` when it is opened | both copies |
| Pressless is not set up | the save succeeds; `NotSetUp` in the preview's place | the save |
| No furniture yet (PRESS-0126) | the save succeeds; `StoreError` in the preview's place | the save |
| A category or tag that cannot be an address | the save succeeds; `BuildStopped` in the preview's place | the save |
| A title or value the Store cannot carry | the Store's refusal; saving stops | the file as it was |
| The disk is full | `StoreError`; saving stops | the file as it was (PRESS-0005 § 4.5) |
| Pressless stops during an address change | nothing | both copies, or the new one alone |
| Two windows preview different entries | each sees the last preview built | one preview page |
| He follows a link inside the preview | *Not found* for his own site's pages; the browser refuses any address outside Pressless | nothing |
| He closes the browser before a save lands | nothing | everything up to the last save |

## 7. Tests

`tests/test_editor.py` — new, in CI. It carries INV-1, INV-2, INV-3, INV-6,
INV-10, INV-11, INV-12, INV-13, INV-14, INV-15, INV-16, INV-17 and INV-18.

`tests/test_builder.py` gains INV-4 and INV-5. `tests/test_face.py` gains
INV-7, INV-8 and INV-9.

`tests/test_builder_archive.py` prints how long one preview takes, beside the
whole build's duration it prints today. That is the evidence for § 3
decision 1, kept as output rather than as a figure here.

Each test is seen failing against stubs that raise `NotImplementedError`, then
mutation-probed once the code lands.

## 8. Alternatives considered (and rejected)

- **Rebuild the whole site for each preview.** Rejected by the user; § 2
  item 2.
- **Show his words alone, rendered by Marks, with the page on a button.**
  Rejected by the user: two views to keep matching, and no header or footer
  while he types.
- **Save straight into the published entry.** Rejected by the user: the next
  publish of anything would send out a half-finished edit (S7).
- **A third Store folder for working copies.** Rejected: it changes the Store's
  on-disk shape and every part that lists it, where a draft with one header
  does the job.
- **A Save button.** Rejected: work typed since the last click is lost when he
  closes the app (S7).
- **Strip the analytics script from the served page.** Rejected: the page would
  no longer be the Builder's bytes (INV-4). The policy header blocks it instead.
- **Reuse Import's slug rule.** Rejected: nothing may depend on Import (design
  rule 9). A new entry's address binds to no existing one, so a second rule
  costs nothing.
- **Mount the photographs folder with `within`.** Rejected: the Face would
  compose a Store path, and design rule 7 keeps that the Store's.

## 9. Out of scope

- The Publish button, dating an entry at its first publish, publishing a
  working copy over its entry, and the empty-Store guard — PRESS-0013.
- Opening Pressless on a double-click — PRESS-0013.
- Deleting an entry, and changing a published entry's address — PRESS-0128.
- Fixed pages, the page furniture and the code view — PRESS-0014.
- Choosing a template for a new entry — PRESS-0017.
- Adding a photograph — PRESS-0016.
- The cheat sheet — PRESS-0018.
- Following a link inside the preview — not queued.
- Backing drafts up — `docs/design.md` names it a later item; not queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_editor.py::test_a_published_entry_is_untouched_by_its_edits` |
| INV-2 | `tests/test_editor.py::test_a_save_from_a_stale_window_writes_nothing` |
| INV-3 | `tests/test_editor.py::test_a_working_copy_replaces_a_published_entry` |
| INV-4 | `tests/test_builder.py::test_a_preview_is_the_page_build_writes` |
| INV-5 | `tests/test_builder.py::test_a_preview_writes_one_page` |
| INV-6 | `tests/test_editor.py::test_a_save_never_touches_the_site_folder` |
| INV-7 | `tests/test_face.py::test_files_never_leave_their_folder` |
| INV-8 | `tests/test_face.py::test_files_carry_the_policy` |
| INV-9 | `tests/test_face.py::test_a_reply_is_sent_as_given` |
| INV-10 | `tests/test_editor.py::test_a_new_entry_gets_a_free_address` |
| INV-11 | `tests/test_editor.py::test_a_save_keeps_his_lines` |
| INV-12 | `tests/test_editor.py::test_a_save_keeps_the_date_and_extra_fields` |
| INV-13 | `tests/test_editor.py::test_a_preview_failure_keeps_the_save` |
| INV-14 | `tests/test_editor.py::test_a_draft_changes_address` |
| INV-15 | `tests/test_editor.py::test_throwing_away_changes_bins_the_copy` |
| INV-16 | `tests/test_editor.py::test_the_list_shows_copies_and_unreadable_files` |
| INV-17 | `tests/test_editor.py::test_a_preview_photograph_is_the_original` |
| INV-18 | `tests/test_editor.py::test_the_editor_sits_behind_the_faces_boundary` |
| That the policies block Google's script, the players and a followed outside link in a browser | **nothing** in CI — by hand, in a preview of a page carrying them, in Chrome and Edge on the Windows box |
| The script's timing, `pagehide` save and no two saves in flight (§ 4.7) | **nothing** in CI — by hand, typing and closing the tab mid-sentence |
| That the box uses the site's font | **nothing** — read on the page |
| That the one-page preview keeps up on Windows | **nothing** in CI — the Windows box, by hand, once PRESS-0013 wires the launch |
| That PRESS-0013 publishes a copy over its entry and removes `Replaces` | **nothing here** — PRESS-0013's |

## 11. Cross-doc impact

- `docs/specs/PRESS-0011-face.md` § 4.1 and § 4.5 — `Reply`, `add_files`,
  `within` and `FILES_POLICY` are added, and `/` becomes the list; the sections
  point here.
- `docs/specs/PRESS-0008-builder.md` § 4.1 — `preview`, `STYLESHEETS` and
  `BODY_CLASS` are added; the section points here.
- `docs/specs/PRESS-0007-import.md` § 10 — the row "That the preview copy is
  never published" stays **nothing**: the editor hands `preview-assets/` to no
  build or publish (§ 4.11), and no test here can see a later part that did.
- `docs/specs/PRESS-0005-store.md` § 9 — a new entry's address is § 4.1's
  `address_for` and `free_address`.
- `docs/specs/PRESS-0004-marks.md` § 4.1 — the Face's address rule is
  `editor.photo_src`.
- PRESS-0013 — calls `editor.register`; publishes a working copy over the
  entry `Replaces` names, without that field, and bins the copy; dates every
  other draft at its first publish (§ 3 decision 6).
- PRESS-0015 — a working copy is a draft, so undo leaves it alone. An entry
  undo turns back into a draft needs a mark, or PRESS-0013 dates it again.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0012-editor-loop-log.md`.
