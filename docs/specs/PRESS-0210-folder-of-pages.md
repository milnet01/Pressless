<!-- ants-spec-format: 1 -->
# PRESS-0210 — Import takes in a site that is a folder of web pages

**Status:** spec draft (2026-10-31).
**Kind:** feature.
**Source:** ROADMAP PRESS-0210 (user decision 2026-10-02; one review round
chosen by the user 2026-10-29).

**Changes:** PRESS-0218 § 3 decision 1, § 4.5 and INV-2; PRESS-0197 §§ 4.1
and 4.6; PRESS-0008 (the forwards a build writes, what it publishes, and
`content/`); PRESS-0015
(`undo._FORWARDS`); PRESS-0005 (one more forwards file); `docs/design.md`
§ What Import brings across. § 11 lists each edit. **Pairs with:** PRESS-0333,
whose pages come in by this spec's reading.

Layman: someone whose site is a folder of web pages, on their computer or in
a GitHub repository, brings it into Pressless, keeps its look and its
addresses, and can edit every part of it from then on.

## 1. Goal

A copy of Pressless holding no site takes in a folder of web pages, from a
ZIP or from a GitHub repository Pressless did not make. Each page becomes a
Pressless page, and the header, footer and menu the pages share become the
single copies. The stylesheets become the style code, and the other files
become photographs and added files. An old address forwards to its page's new
one. The user is told what will come across before anything is written, and
item by item afterwards. Sign of success: S13.

## 2. Problem

1. **Nothing reads a folder of pages.** `pressless_import.bring_in` reads a
   WordPress export only.
2. **Setup refuses such a repository.** `setup`'s `check_pages` answers
   `setup.hint.made_elsewhere` where `takein.look` says not `made_here`.
3. **Pressless's addresses differ from a plain site's.** The Builder writes
   `index.html` and `pages/<name>.html`, and a page name is one lower-case
   slug (`store._LEGAL_SLUG`). A plain site has `about.html` and
   `team/index.html`, so bringing it in would break every link from elsewhere.
4. **`builder._Build.page_forwards` forwards only under `pages/`**, from one
   page name to another.
5. **Two of a plain site's usual file kinds may not be kept.** PRESS-0197 § 3
   decision 1 refuses SVG and script files as added files, and `builder.file_allowed`
   has no font or `.ico` kind.

## 3. Scope decisions (agreed with the user)

1. **Each page becomes a page; the shared header and footer are parted out
   into the single copy; the stylesheet becomes the style code.** The user,
   2026-10-02 (`docs/design.md` § What Import brings across).
2. **A repository Pressless did not make comes here.** The user, 2026-10-23
   (PRESS-0218 § 3 decision 1).
3. **The user is told before any change, and after it.** The user, 2026-10-23.
4. **PRESS-0197's refusal of script and SVG files stands.** The user,
   2026-10-16. So they are carried inside pages (§ 4.6), never as files.
5. **One review round.** The user, 2026-10-29.
6. **(decided here) A ZIP is how a folder is handed over.** The steps say how
   to make one on each system. A browser's folder chooser is PRESS-0335.
7. **(decided here) Every page is a page, none an entry.** Nothing in a plain
   page says reliably that it is a dated post. The journal is off.
8. **(decided here) The site keeps its own look.** Its stylesheets become
   style code with no `choices.json`. The Look screen's existing state for
   style code it did not make applies, and no look is asked for.
9. **(decided here) An old address keeps working by a forward**, as a renamed
   page's does (§ 4.10).
10. **(decided here) Fonts and `.ico` join the kept kinds.** They carry no code,
    and a plain site's look needs them.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The two ways in

Both lay the folder out at `import/folder/` in the open site's folder, then
read it the same way (§ 4.3) and write it the same way (§ 4.9). `import/` is
never published and never saved in a site file (PRESS-0125 § 4.2).

```python
# src/pressless_import/_folder.py — new; re-exported by the package

FOLDER = "folder"                    # in IMPORT_FOLDER
MEMBERS_MOST = 20_000                # a ZIP holding more is refused
SVG_LARGEST = 256 * 1024             # § 4.6

def unpack_folder(source: Path, into: Path,
                  room: Callable[[], int]) -> tuple[tuple[str, str], ...]: ...
def read_folder(folder: Path) -> Found: ...
def bring_in_folder(folder: Path, into: Path, *,
                    left: tuple[tuple[str, str], ...] = (),
                    commit: str = "") -> Brought: ...

@dataclass(frozen=True)
class Found:
    pages: tuple[str, ...]           # folder-relative paths
    photographs: tuple[str, ...]
    files: tuple[str, ...]
    inside_pages: tuple[str, ...]    # scripts and SVGs a page carries (§ 4.6)
    style: tuple[str, ...]           # stylesheets (§ 4.7)
    left: tuple[tuple[str, str], ...]  # (path, why it will not come across)
    roots: tuple[str, ...]           # root entries holding a path not in left
    built_by_a_tool: bool            # § 4.3

@dataclass(frozen=True)
class Brought:
    report: Report
    roots: tuple[str, ...]           # root entries something was carried from
```

`unpack_folder` checks every member first, by `sitefile.stays_inside` and
`sitefile.is_link`, and refuses the ZIP on any failure, writing nothing. It
also refuses a ZIP with more than `MEMBERS_MOST` members, or whose members do
not fit `room()`. A member larger than `builder.FILE_LARGEST`, one with a path
segment `store.file_path_for` refuses, and one whose path folds to the same
`casefold()` as an earlier member are not unpacked. Each is returned with why.
Where every member sits inside one top folder, that folder is removed from
each path, because a zipped folder arrives that way.

### 4.2 The wizard

`importing.py` registers a second wizard at `/import/folder`, on
`wizard.Wizard`, with its progress in `wizards/import-folder.json`. It answers
only while `not store.holds_a_site(folder)`; otherwise it redirects to `/`.
The two offers PRESS-0125 § 4.1 shows gain a second link to it.

| Step | Shows | Check before Next |
|------|-------|-------------------|
| `folder` | How to make a ZIP on Windows and on Linux, and a file box posting to `/import/folder/zip` | a folder is held, and `read_folder` found a page and not `built_by_a_tool` |
| `found` | § 4.3's counts; every path in `left` and in `import/folder-left.json`; that the site keeps its own look | none |
| `bring` | What Next does, then the Report (§ 4.12) | `bring_in_folder` has written |

The Windows step names Explorer's *Send to*, *Compressed (zipped) folder*.
`Compress-Archive` on Windows PowerShell 5.1 writes `\` in member names, which
§ 4.1 refuses; the shell's own ZIP writes `/` (run on the Windows box,
2026-10-31; refute by listing each ZIP's entries).

The upload goes through `Face.add_upload`, so it is never held in memory. A new
ZIP replaces `import/folder/` and deletes `import/folder.json`. `unpack_folder`'s
answer is kept in `import/folder-left.json` and passed to `bring_in_folder` as
`left`.

### 4.3 Reading the folder

`read_folder` reads and writes nothing else. Each file is one of:

| A file that is | Becomes |
|---|---|
| `.html` or `.htm`, and not a verification file | a page |
| something `builder.photograph_format` names | a photograph |
| `builder.file_allowed` | an added file |
| `.css`, linked from a page or another stylesheet | style code (§ 4.7) |
| `.js` or `.svg`, used as § 4.6 says | inside its page |
| anything else | `left`, with why |

Names beginning with a dot are `left`, at any depth, and so are `CNAME`, a root
`404.html`, a stylesheet nothing links, and a script or SVG § 4.6 cannot carry.
GitHub Pages serves a root `404.html` at every missing address, where a relative
forward would reload for ever.

A path failing one of § 4.1's tests on size, segment or folded name is `left`
too, because a repository's paths meet no `unpack_folder`.

**A verification file** is a root `.html` file named `google*`, `yandex_*` or
`pinterest-*`, or one holding no `<` at all. It is `left`, because it proves
ownership of a site to a search engine (`docs/design.md` § the untouchable rule).

**`built_by_a_tool`** is true where the root holds `_config.yml` or
`_layouts`, or any page opens with a `---` line, unless the root holds
`.nojekyll`. Such a folder is the source a tool builds pages from, not the pages.

### 4.4 A page's name

`index.html` or `index.htm` at the root is the front page, `index`. With
neither, the front page is `home` or `default`, else the first page by path;
this choice is listed.

Any other page's name is `resolve_slug` of its path, without its suffix and
with `/` as a separator, and a trailing `/index` is dropped: `about.html` is
`about`, `team/index.html` is `team`, and `blog/first post.htm` is
`blog-first-post`. A name taken, or refused by `store.html_path_for`, takes
`-2`, `-3` and so on, and is listed. Pages are named in path order, so a run
over the same folder gives the same names.

A photograph or file keeps its name. One taken or refused takes its folders
joined by `-` before the name, and then a number, and is listed.

### 4.5 Addresses

Every address in a page's `href`, `src`, `srcset` and `poster`, and in a CSS
`url(...)` in its `style` attributes and `style` elements, is read against the
page's old path. An address with a scheme or host stays as written. So does one
that is only a fragment. Otherwise it is resolved in this order, its query and
fragment kept:

1. the file at that path;
2. that path with `index.html` or `index.htm` joined, where it names a folder;
3. that path with `.html` or `.htm` added, as GitHub Pages serves it;
4. where it began with `/` and its first segment names nothing in the folder,
   the same three without that segment, as a site served under its repository's
   name writes it.

What it resolved to decides what is written, from the page's new depth:

| Resolved to | Written as |
|---|---|
| a page | its new address |
| a photograph or file | `builder.web_photograph` or `builder.web_file` |
| nothing carried | the same site path from the new depth, and listed |

The last row keeps a link to a file that stays on the repository working. Where
the next publish removes that file, § 4.11 names the link.

A page holding a `<base>` element has its addresses left alone, and is listed.

### 4.6 Scripts and SVG

`<script src>` naming a `.js` file in the folder has the file's text placed
inside the element, and `src` removed. An inline script ignores `defer` (run in
Firefox, 2026-10-31), so an element with `defer` also moves to the end of the
body, in its order. Where the text holds `</script`, or the element has
`type="module"`, the element is left as § 4.5 writes it, and the file is `left`.
Each script carried is listed, once per file.

An address naming an `.svg` file, in an `<img>`'s `src` or a CSS `url(...)`, is
written as a `data:image/svg+xml;base64,` address. A browser runs no script in
an image. An SVG over `SVG_LARGEST`, or named in any other way, is `left`.

### 4.7 The style code

Every stylesheet the folder's pages link is joined in the order pages first
link them, pages taken in path order. An `@import` of a stylesheet in the
folder is replaced by that sheet's text, each sheet once. A `media` attribute
wraps its sheet's text in `@media`. An `@import` of an address outside the folder
moves to the top of the result, that `media` as its own condition, because a
browser ignores one below another rule (run in Firefox, 2026-10-31). `@charset`
is dropped. Each `url(...)` is read against its own
sheet's old path and written from `builder.STYLE_CODE`'s place, by § 4.5's
rows. A sheet that only some pages link is listed: its rules now reach every
page.

The result goes to `store.write_style_code`, an empty file where there is
none, so `builder.stylesheets` answers the one sheet. No `choices.json` or
`extra.css` is written.

### 4.8 The header, footer and menu

Addresses are first written with `{{UP}}` in place of the depth (§ 4.5), and
each page's site header, footer and menu found:

- the first `<header>` or `<div id="header">`, and the last `<footer>` or
  `<div id="footer">`, not inside `main`, `article` or `section`;
- the first `<nav>` or `<div id="nav">`, `id="menu"` or `id="navigation"`,
  inside that header or not inside those three.

Each is compared across pages with outer whitespace trimmed, and with
`aria-current` and the class names `active`, `current` and `selected` removed.
Which link is marked current differs on every page, and would otherwise make
no two menus equal. Where those marks were removed, that is listed once: the
Builder marks the current link with `aria-current`, and the site's own rule for
those classes no longer applies.

**A block is shared where it is the most common among pages, and at least half
hold it.** A page holding the shared block has it replaced by the Builder's
marker pair, and the text goes to the furniture file. A page holding another
keeps its own, and is listed. Only the furniture files keep `{{UP}}`, because the
Builder fills it there alone; everywhere else in a page it becomes that page's
own depth. A site with no shared block has none parted out,
and that is listed. Its furniture files are still written, from `starter.header`,
`starter.footer` and `starter.navigation`, as a build needs them.

**The menu.** A shared menu inside the header goes to the navigation file, with
`{{NAVIGATION}}` left in its place. A shared menu with only whitespace between
it and the shared header joins the header's marker pair, the header file
holding `{{NAVIGATION}}` on the matching side. A shared menu with no shared
header makes the header file `{{NAVIGATION}}` alone. Any other shared menu stays
in each page, and is listed: the Menu screen then edits nothing the site shows.

Each link in the navigation file that resolved to a page gains
`data-nav="<name>"`, and each page's header marker has `page="<name>"`, which
`builder._current` matches. For the front page both hold `Home`, as `menu._nav`
and `starter.home_page` do. A menu `menu.links` calls `Unusual` is kept as written and
listed, because new pages will not join it by themselves (`docs/design.md`
§ The menu follows the pages).

### 4.9 A page, and writing it

**A page's text.** It is decoded as UTF-8, a leading byte-order mark dropped.
Failing that, it is decoded by its `<meta charset>`, else as `cp1252`, and the
declared charset rewritten to `utf-8`; each such page is listed. A file that
none of these decode is `left`.

Any Builder marker comment or `pressless:page` mark the page holds is removed
and listed, because the Builder would otherwise fill or read it.

The head keeps its bytes but for § 4.5's addresses, § 4.6, each local stylesheet
link removed, and one link to `builder.STYLE_CODE` in place of the first.

The body keeps its bytes but for § 4.5, § 4.6 and § 4.8's marker pairs. Where
it has no `<main>`, what lies between its header and its footer, shared or its
own, is wrapped in a plain `<main>`, so `blocks.adopt` can make its area and the visual editor can reach
it. A page with no `<body>` takes `starter.new_page`'s shape, its text as
`main`, and its title from its first `<h1>`, else its name. Whatever no section
fits is a code section, kept byte for byte (`docs/design.md` § Pages, and how
they are held).

**The whole or nothing.** `bring_in_folder` refuses with `ImportStopped` where
`store.holds_a_site(into)`, and otherwise follows PRESS-0125 § 4.7: every Store
file is written into `import/work/` through Store calls, then `import/moving`
is written and each folder moved in by `pressless_import.finish`, which also
deletes `import/folder/`. It writes the pages, furniture, style code, address
forwards (§ 4.10), photographs, files, templates (`templates.seed`), and
`store.write_journal(work, False)`.

An identity is written where `into` holds none: its name is the front page's
`<title>`, its description that page's description `<meta>`, each with its runs
of whitespace made one space. Where the name is then blank, which
`store.identity_problem` refuses, no identity is written. `Brought.roots` names
each root entry at least one file was carried from.

Before `import/moving`, `bring_in_folder` writes `import/brought.json`, holding
`commit`, `Brought.roots` and the Report (§ 4.11).

### 4.10 Old addresses (Store and Builder)

```python
# src/pressless/store.py — added
ADDRESS_FORWARDS_FILE = "addresses.json"   # in FORWARDS_FOLDER
def address_forwards_path_for(folder: Path) -> Path: ...
def read_address_forwards(folder: Path) -> dict[str, str]: ...
def write_address_forwards(folder: Path, forwards: dict[str, str]) -> Path: ...
```

Each key is a page's old path from the site's root, and each value the name of
the page. A key must be relative, end in `.html` or `.htm`, and have every
segment accepted by `store.file_path_for`, or the file is a `StoreError`. A
value must be `index` or a legal page name. `bring_in_folder` writes one where a
page's old path is not its new one.

`builder._Build.address_forwards(pages, written)` runs after `page_forwards`.
For each key, the target is the value, or where `read_page_forwards` maps that
name, the name it maps to. It writes a forward page in `page_forwards`' shape at
the key's path, its link and refresh relative to that path's depth, unless:

- the target is not in `pages`, because the page was removed; or
- a file already written folds to the same `casefold()` as the key, because the
  site's own file wins.

`builder.roots_produced(folder)` answers `ROOT_OUTPUT` and the first segment of
each key. `_refuse_a_folder_it_did_not_make` reads it, or a second build stops
with `SiteFolderUnusable` at its own `about.html`. `setup.untouchable` reads it,
so a take-in's list leaves the forwards off.

`sitemap` lists no forward. `_Build.content` carries the file, and
`undo._FORWARDS` gains it, so a take-in and an undo bring it back.

### 4.11 A repository Pressless did not make (amends PRESS-0218 § 4.5)

`takein.py` gains the order of things, the Face's as `take_in` is:

```python
def look_folder(folder: Path, settings: Settings, key: str, commit: str = "",
                transport: publisher.Transport | None = None) -> tuple[Found, str]: ...
def bring_folder(folder: Path, settings: Settings, key: str, commit: str, *,
                 capture=..., notices=None, transport=None) -> Brought: ...
```

`look_folder` empties `import/folder/`, calls `publisher.fetch_state` with prefix
`"/"`, which selects the whole repository, into it, and answers `read_folder`'s
`Found` and the commit read. It records that commit in `import/folder.json`.

**pages.** Where `takein.look` says not `made_here`, `look_folder` runs. Where
`built_by_a_tool`, or where the root holds no `index.html`, the answer is still
`setup.hint.made_elsewhere`, reworded to say this repository holds what a tool
builds a site from, and no write is sent. Otherwise the answers gain
`bring_in_commit`, and Pages is read and switched on as today.

**site**, where the answers carry `bring_in_commit`. The body names, from
`read_folder` over the held folder:

- the counts;
- that Finish copies it into Pressless on this computer and changes nothing on
  GitHub;
- what the next publish will change on GitHub, which is every root entry not on
  the list Finish will save: the old pages become forwards, and the rest there is
  replaced or removed, staying in the repository's history. Each `left` path among
  them is named, and each page link to one;
- what stays on GitHub untouched: each entry on that list, such as `CNAME` or
  `README.md`.

**The list** is `untouchable(entries)` without `Found.roots` on this step and
`Brought.roots` at Finish, compared with `casefold`, so a forward at `about.html`
is published.

**Finish.** `_save_sequence` takes `bring_in_commit` in the fill's place.
`bring_folder` lays the folder out again only where `import/folder/` is absent or
`import/folder.json` does not name that commit, so what is written is what was
shown. The done page says the site came in, and shows the Report.

**A Finish pressed again.** Where `store.holds_a_site` and `import/brought.json`
names the commit, `bring_folder` writes nothing and answers from the file. So a
failed Settings save (PRESS-0021 § 4.6), or a close during the moves, is retried
without a second bring. Nothing is reversed, which needs no second caller of
`store.unplace_photograph` (PRESS-0218 INV-12).

### 4.12 The Report

`Report` gains `moved` (old path, new name), `inside_pages` and `sheets_for_some`.
`left` paths go in `unfetched`, whose `(place, why)` shape is theirs. The Face
shows it as PRESS-0125 § 4.8 does, through `importing._lines` and `_shown`, and
writes `import/report.txt`. Its words are `import.report.*` keys.

### 4.13 What a build publishes (amends PRESS-0197 § 4.6)

Today a build publishes a held photograph only where a `picture` or `enlarge`
section's `src` names it, and a held file only where a section's `src` or `href`
does. A code section names neither, and most of a brought-in page is code
sections (§ 4.9). Run on 2026-10-31 over a page adopted by `blocks.adopt`:
`_held_pictures` and `_held_files` each answered nothing.

So `_Build` also copies each held photograph and file named by any `href`, `src`,
`srcset`, `poster` or CSS `url(...)`, read from its own place, in a page's text, a
furniture file's text and the style code. `files_named` reads the same names, so
PRESS-0197's removal guard sees them. This holds for every site.

A carried file nothing names stays in the Store, is not published, and is listed.

## 5. Invariants

- **INV-1** — A folder goes only into a Store that holds no site.
  *Test:* `tests/test_importing.py::test_a_folder_goes_only_into_an_empty_store`
  — `/import/folder` on a filled Store redirects to `/`, and `bring_in_folder`
  into a Store where `store.holds_a_site` is True raises `ImportStopped`.
  *Breaks when:* the check is made at the first step only.

- **INV-2** — A ZIP holding a name outside its folder, or a link, writes nothing.
  *Test:* `tests/test_importer_folder.py::test_a_bad_zip_writes_nothing` — one
  member each of `../x.html`, `/abs.html`, `a\b.html` and a link, beside a good
  page: each raises `ImportStopped` and `import/folder/` is not made.
  *Breaks when:* members are checked as they are unpacked.

- **INV-3** — Every link between a folder's own pages and files still resolves
  once built. *Test:*
  `tests/test_importer_folder.py::test_every_address_resolves_once_built` — a
  fixture with pages at the root and in a subfolder, linking each other, a
  picture and a PDF by relative, root-relative, repository-name-prefixed, folder
  and no-suffix addresses, each with a query or fragment somewhere, some inside a
  `<div>` so in a code section, and by `srcset`, `poster` and a style `url()`: after
  `builder.build`, each such address in each built page resolves to a built file.
  *Breaks when:* addresses are rewritten without the page's new depth, or a build
  publishes only what a section's field names.

- **INV-4** — Each old page address serves something that reaches the page.
  *Test:* `tests/test_builder.py::test_an_old_address_forwards_to_its_page` —
  `about.html` and `team/index.html` each hold a refresh to the page, relative to
  their own depth, and a second `builder.build` into the same folder succeeds.
  *Breaks when:* the forward's link assumes depth 1, as `page_forwards`' does, or
  the Builder refuses its own forward as a file it did not make.

- **INV-5** — An address forwards file naming a path outside the site is refused,
  and a build follows the page. *Test:*
  `tests/test_store.py::test_address_forwards_refuse_a_path_outside_the_site` —
  `../x.html`, `/x.html`, `a/../x.html` and `x.png`; and
  `tests/test_builder.py::test_an_old_address_follows_the_page` — a renamed target
  forwards to its new name, a removed one writes nothing, and a page whose own
  file is the key keeps it.
  *Breaks when:* the Builder joins a key to the site folder unchecked.

- **INV-6** — A header, footer and menu shared across depths and current-link
  marks are parted out once. *Test:*
  `tests/test_importer_folder.py::test_shared_furniture_is_parted_out` — a root
  page and a subfolder page whose header links differ only by `../`, and whose
  menus differ only in `class="active"`: each file holds one copy, each page holds
  a marker pair, and a build of each page shows the links.
  *Breaks when:* pages are compared before their addresses are written the same.

- **INV-7** — A page with another header keeps its own, and is listed. *Test:*
  `tests/test_importer_folder.py::test_a_different_header_stays_in_its_page`.
  *Breaks when:* a page's header is replaced because it has one.

- **INV-8** — Every linked stylesheet reaches the style code, and the Look screen
  leaves it alone until a save. *Test:*
  `tests/test_importer_folder.py::test_stylesheets_become_the_style_code` — two
  sheets, an `@import`, a remote `@import`, a `media` attribute and a `url()` to a
  picture: the built stylesheet holds them in order with the remote one first, and
  the picture resolves from `look/style.css`, `look.read` is None, and `/look` shows
  the state for style code it did not make.
  *Breaks when:* `look.save` is called, which replaces it with a Pressless look.

- **INV-9** — No script or SVG is kept as a file, and neither is lost while it is
  in use as § 4.6 says. *Test:*
  `tests/test_importer_folder.py::test_scripts_and_svgs_are_carried_inside_pages`
  — a `<script src>` in the head, a `<script defer src>`, one holding `</script`, a
  `type="module"`, an `<img>` SVG, an `<object>` SVG and an unused `.js`: the first
  runs inline where it was, the `defer` one inline at the body's end, the `<img>` SVG
  is a `data:` address, the rest are `left`, and `store.list_files` holds no `.js` or
  `.svg`.
  *Breaks when:* `builder._FILE_KINDS` gains them, reversing PRESS-0197 § 3
  decision 1.

- **INV-10** — Every file in the folder is accounted for: `Found`'s tuples hold
  each path exactly once. *Test:*
  `tests/test_importer_folder.py::test_every_file_is_accounted_for` — a fixture
  of every row of § 4.3's table, walked and compared with the tuples.
  *Breaks when:* a kind is skipped without being added to `left`.

- **INV-11** — The Store is either untouched or holds the whole site. *Test:*
  `tests/test_importer_folder.py::test_a_stop_leaves_the_store_empty` (a Store
  refusal during writing) and `::test_a_stop_during_the_moves_finishes_next_start`.
  *Breaks when:* files are written straight into the site's folder.

- **INV-12** — A brought-in site published and taken in again keeps its forwards,
  and an undo brings them back. *Test:*
  `tests/test_takein.py::test_a_brought_in_site_comes_back_with_its_forwards`, with
  the forwards' paths off the saved untouchable list, and
  `tests/test_undo.py::test_address_forwards_come_back`.
  *Breaks when:* `_Build.content` or `undo._FORWARDS` lacks the file.

- **INV-13** — A repository holding plain pages goes on, and only Pages being
  switched on, with its `.nojekyll`, is written to GitHub. *Test:*
  `tests/test_takein.py::test_a_plain_site_goes_on_and_writes_nothing_to_github`.
  *Breaks when:* a step adopts the repository by writing to it.

- **INV-14** — A repository holding what a tool builds from is still a `Hint` on
  the *pages* step, and no write is sent. This replaces PRESS-0218 INV-2's
  refusal of every site made elsewhere. *Test:*
  `tests/test_takein.py::test_a_site_made_elsewhere_is_refused`, over one fixture
  each: Markdown posts under `content/posts/`; `_config.yml` beside `index.md`; an
  `index.html` opening `---`; and `.nojekyll` beside an `index.html` opening `---`,
  which goes on. A root holding none of `content`, `index.html` and `index.md` goes
  on as a new repository (PRESS-0218 § 4.5).
  *Breaks when:* `built_by_a_tool` reads only `_config.yml`, or ignores
  `.nojekyll`.

- **INV-15** — Before Finish the *site* step names every change the next publish
  makes and every path left, and the Store is unchanged. *Test:*
  `tests/test_takein.py::test_the_screen_says_what_a_publish_will_change`.
  *Breaks when:* a `left` path is dropped without being named, or the step's body
  writes to the Store.

- **INV-16** — A root entry nothing was carried from stays on GitHub unless the
  Builder makes that name, and an old page does not. *Test:*
  `tests/test_takein.py::test_what_was_not_carried_stays_untouchable` —
  `CNAME`, `README.md`, a `google123.html` and a `downloads/` of `.exe` files stay on
  the list; `about.html`, `images/`, `team/` and a left `sitemap.xml` are not on it,
  and the *site* step says the last is replaced; and a publish to the
  recording double updates `about.html` to its forward and leaves `CNAME` alone.
  *Breaks when:* the list is `untouchable(entries)` unchanged, so `about.html` keeps
  its old page for good.

- **INV-17** — Finish pressed again after a failed Settings save, or after a close
  during the moves, brings nothing in twice. *Test:*
  `tests/test_takein.py::test_finish_again_saves_without_a_second_bring` — failing the
  save once, and in a second run stopping at the moves and calling
  `pressless_import.finish`: the next press sends no fetch, and Settings saves.
  *Breaks when:* a second press is stopped by `store.holds_a_site`.

- **INV-18** — What Pressless shows of a folder is escaped. *Test:*
  `tests/test_importing.py::test_the_folder_screens_escape_what_they_name` — a file
  named `<img src=x>.exe` and a title of `<script>`, on the `found` step and the
  Report.
  *Breaks when:* a path is written raw.

- **INV-19** — A brought-in page's script never runs in the Face. *Test:*
  `tests/test_importing.py::test_a_brought_in_script_is_not_run_by_the_face` — a
  preview of a page holding an inline script answers with `script-src 'none'`
  (PRESS-0012, PRESS-0268).
  *Breaks when:* a brought-in page is served by a route outside that policy.

- **INV-20** — A page in an older encoding keeps its words. *Test:*
  `tests/test_importer_folder.py::test_an_older_encoding_is_read` — `caf\xe9` in a
  page declaring `iso-8859-1`, and in one declaring nothing: the page written says
  `café` and declares `utf-8`, and each is listed.
  *Breaks when:* the bytes are decoded as UTF-8 with replacement.

- **INV-21** — A folder's fonts and `.ico` are kept, by content. *Test:*
  `tests/test_builder.py::test_font_and_icon_kinds_are_checked_by_content` — each new
  suffix with its own opening bytes, and with a text file's.
  *Breaks when:* the suffix alone decides, against PRESS-0197 § 3 decision 4.

## 6. Failure modes

| What fails | What happens |
|---|---|
| The ZIP is not a ZIP, or holds no page | `folder` step says so; nothing is kept |
| The ZIP is larger than the drive's room | Refused before anything is unpacked; nothing is kept |
| A member cannot be held on Windows | Not unpacked on any system, and listed (§ 4.1) |
| A repository path cannot be held on Windows | On Windows, `UnfetchablePath` from `fetch_state`, and the *pages* step is a `Stop` (PRESS-0009 § 4.5); elsewhere `left` (§ 4.3) |
| The fetch fails part-way | Nothing lands (PRESS-0218 INV-10); the *pages* step or Finish is a `Stop` |
| The held folder has gone before Finish | `bring_folder` fetches `bring_in_commit` again; `RemoteStateMissing` is a `Stop` saying to go Back |
| Pressless closes during the moves | The next start finishes them (PRESS-0125 § 4.7); Finish then answers from `import/brought.json` (INV-17) |
| A Settings save fails after the bring | Finish can be pressed again (INV-17) |
| The user presses Back and chooses another repository after the bring | `ImportStopped`, a `Stop`: the Store holds a site |
| A page's CSS relied on `body > *`, so the added `<main>` changes it | Not detected; the hand check in § 10 looks at this |
| A script names a file by its old address | Not detected; each carried script is listed, so the user knows where to look |

## 7. Tests

`tests/test_importer_folder.py` is new and holds the pure parts: INV-2, INV-3,
INV-6, INV-7, INV-8, INV-9, INV-10, INV-11 and INV-20. `tests/test_importing.py`
holds the wizard's routes (INV-1, INV-18, INV-19), and `tests/test_takein.py` the
repository route through its recording GitHub double (INV-12, INV-13, INV-14,
INV-15, INV-16, INV-17). `tests/test_builder.py` holds INV-4, INV-5's second half
and INV-21, `tests/test_store.py` INV-5's first half, and `tests/test_undo.py`
INV-12's second. Each named test is seen to fail against today's code before its
change.

**By hand, before release:** a real plain site, zipped and brought in, and a real
scratch repository holding one, each published and compared with the old site
in a browser; and § 4.2's ZIP steps read on Windows and on Linux.

## 8. Alternatives considered (and rejected)

- **Keep each page at its old address.** Rejected: the Store's page names, the
  Builder's layout, the menu and the page editor all rest on `pages/<name>.html`.
- **A browser's folder chooser now.** Rejected for this spec: `Face.add_upload`
  takes one file per request, so it needs a new upload shape. PRESS-0335 has it.
- **Keep scripts and SVGs as added files.** Rejected: the user refused both kinds
  (§ 3 decision 4).
- **Inline an SVG as an `<svg>` element.** Rejected: there it can run a script, and
  an `<img>`'s sizing attributes would no longer apply.
- **Leave a page's stylesheets as files.** Rejected: `.css` is not a kept kind, and
  the design makes the stylesheet the style code.
- **Reverse a bring-in when a Settings save fails.** Rejected: a retry reaches the
  same place without a new way of deleting photographs (§ 4.11).

## 9. Out of scope

- A site GitHub Actions builds — PRESS-0333, which reuses § 4.3 to § 4.10.
- Bringing a folder in after setup onto a site that holds one: Import fills only an
  empty Store (`docs/design.md` rule 9).
- A Pressless look over a brought-in site beyond what the Look screen does today —
  PRESS-0276.
- Turning plain pages into dated entries — deferred; not yet queued.
- A folder chooser in the browser — PRESS-0335.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_importing.py::test_a_folder_goes_only_into_an_empty_store` |
| INV-2 | `tests/test_importer_folder.py::test_a_bad_zip_writes_nothing` |
| INV-3 | `tests/test_importer_folder.py::test_every_address_resolves_once_built` |
| INV-4 | `tests/test_builder.py::test_an_old_address_forwards_to_its_page` |
| INV-5 | `tests/test_store.py::test_address_forwards_refuse_a_path_outside_the_site`, `tests/test_builder.py::test_an_old_address_follows_the_page` |
| INV-6 | `tests/test_importer_folder.py::test_shared_furniture_is_parted_out` |
| INV-7 | `tests/test_importer_folder.py::test_a_different_header_stays_in_its_page` |
| INV-8 | `tests/test_importer_folder.py::test_stylesheets_become_the_style_code` |
| INV-9 | `tests/test_importer_folder.py::test_scripts_and_svgs_are_carried_inside_pages` |
| INV-10 | `tests/test_importer_folder.py::test_every_file_is_accounted_for` |
| INV-11 | `tests/test_importer_folder.py` (two tests, § 5) |
| INV-12 | `tests/test_takein.py::test_a_brought_in_site_comes_back_with_its_forwards`, `tests/test_undo.py::test_address_forwards_come_back` |
| INV-13 | `tests/test_takein.py::test_a_plain_site_goes_on_and_writes_nothing_to_github` |
| INV-14 | `tests/test_takein.py::test_a_site_made_elsewhere_is_refused` |
| INV-15 | `tests/test_takein.py::test_the_screen_says_what_a_publish_will_change` |
| INV-16 | `tests/test_takein.py::test_what_was_not_carried_stays_untouchable` |
| INV-17 | `tests/test_takein.py::test_finish_again_saves_without_a_second_bring` |
| INV-18 | `tests/test_importing.py::test_the_folder_screens_escape_what_they_name` |
| INV-19 | `tests/test_importing.py::test_a_brought_in_script_is_not_run_by_the_face` |
| INV-20 | `tests/test_importer_folder.py::test_an_older_encoding_is_read` |
| INV-21 | `tests/test_builder.py::test_font_and_icon_kinds_are_checked_by_content` |
| A brought-in site looks as it did | **nothing** — § 7's hand comparison |
| § 4.2's ZIP steps are right on each system | **nothing** — § 7's hand reading |
| A carried script still works in its page | **nothing** — § 7's hand comparison; each is listed |

## 11. Cross-doc impact

- **PRESS-0218**, amended in the same change: § 3 decision 1 and § 9 point here;
  § 4.5's *pages* refusal becomes § 4.11 here; INV-2 is annotated as narrowed by
  INV-14 here, its test keeping its name.
- **PRESS-0197 § 4.1** gains `.woff`, `.woff2`, `.ttf`, `.otf` and `.ico`, each checked by
  its opening bytes, served as `face._FILE_TYPES` says, which gains `font/ttf` and
  `font/otf`, and chosen by no section. § 3 decision 1 is unchanged.
- **PRESS-0197 § 4.6**: what a page names widens as § 4.13 here says.
- **PRESS-0008**: a build writes address forwards, `roots_produced` joins
  `ROOT_OUTPUT` (§ 4.10), a build publishes as § 4.13 says, and `content/` carries
  the forwards' file.
- **PRESS-0015**: `undo._FORWARDS` gains the file.
- **PRESS-0005**: the Store gains the file and its three calls.
- **PRESS-0212 § 4.4**: the *pages* and *site* steps gain § 4.11's words.
- **PRESS-0021 § 4.7**: the list is derived against `builder.roots_produced`.
- **PRESS-0021 § 4.9**: setup also writes the Store through `takein.bring_folder`.
- **`docs/design.md` § What Import brings across**, the folder bullet: a script and
  an SVG are carried inside the pages, not as added files, and an old address
  forwards to its page.
- **CHANGELOG** gains an Added entry when this ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0210-folder-of-pages-loop-log.md`.

## 13. Resource cost

- A ZIP is unpacked once, and its files move into the Store by rename, so a site
  takes its own size on disk, not twice. The uploaded ZIP is deleted after unpacking.
- Each page is read whole, and all of them once more to compare furniture, so the
  bring holds the site's HTML and CSS in memory for its length.
- A repository is fetched whole, once. Its blobs are read one request each.
- A script used by many pages is copied into each, so those pages grow by its size.
- No new dependency: `zipfile`, `html.parser`, `base64`.
