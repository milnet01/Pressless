<!-- ants-spec-format: 1 -->
# PRESS-0125 — Anyone brings their WordPress site in

**Status:** accepted (2026-10-22). Gated for one round by the user's
budget; every verified finding fixed, not converged. Built 2026-10-22;
§§ 4.2 to 4.8 and § 6 record what the build settled.
**Kind:** feature.
**Source:** ROADMAP PRESS-0125 (user decisions 2026-09-17, 2026-10-02 and
2026-10-22).

**Changes:** PRESS-0007 § 3 decisions 3 and 11, § 4.1, § 4.2, § 4.3,
§ 4.5, § 4.6, § 4.7, § 4.8, INV-6, INV-7, INV-8, INV-10 and § 6, and
`docs/design.md` rule 9
(§ 11). **Carries:** PRESS-0156,
PRESS-0157, PRESS-0158 and PRESS-0161, each decided by the user
2026-09-26.

Layman: someone with a WordPress site brings all of it into Pressless
themselves — posts, pages, menu, comments, photographs and files — and is
told, item by item, about anything that could not come across.

## 1. Goal

A copy of Pressless holding no site offers **Bring in a WordPress site**.
The user makes WordPress's export file and hands it over. Pressless fetches
every photograph and file from the old site while it is still online,
takes a media download for whatever it could not fetch, and asks for a
look. It then writes the whole site into the empty Store at once, and shows
a Report naming everything that did not come across as written. From then
on every part of the site is edited in Pressless. Sign of success: S13.

## 2. Problem

1. **Import runs only on the maintainer's machine.** `pressless_import.run`
   takes the export, an originals folder, the live site's folder and the
   sibling generator's templates, and only `pressless_import.main` calls
   it. No module under `src/pressless/` imports `pressless_import`.
2. **It needs files a general user does not have.** `_fixed_pages` reads
   the live site's built pages and `_furniture` the generator's templates.
   `_photographs` checks every original in a local folder laid out as the
   uploads folder is, and raises `ImportStopped` where one is missing.
3. **It reads the export as trusted.** `_read` parses with `xml.etree`,
   and `pyproject.toml` exempts the package from ruff's S314 because the
   file came from the maintainer (PRESS-0007 § 4.8).
4. **Four review findings make other blogs lose words**: PRESS-0156
   (paragraphs collapse), PRESS-0157 (pending and scheduled posts vanish),
   PRESS-0158 (one broken comment or missing original stops the run) and
   PRESS-0161 (list items fuse; script text shows).
5. **A WordPress export holds no look.** The theme's styling is not in it;
   a block theme's `wp_global_styles` and `wp_template_part` items are its
   settings, not a stylesheet.

## 3. Scope decisions (agreed with the user)

1. **An Import anyone can run, for a whole WordPress site.** The user,
   2026-09-17 and 2026-10-02: pages, menus, media, and a journal where it
   has one — never only a blog.
2. **Import is one of setup's three starts, into an empty Store only.**
   The user, 2026-10-02 (`docs/design.md` rule 9, § Setup's three starts).
3. **Media comes from the old site first.** The user, 2026-10-22: Import
   fetches each file from the address the export names. What it cannot
   fetch is listed, and a media download can fill the gaps. This replaces
   the media half of 2026-10-02's decision.
4. **The four findings' fixes**, the user, 2026-09-26: markup is decided
   as WordPress decided it; pending and scheduled posts arrive as drafts,
   the Report saying how; a broken comment or a missing original is listed
   and Import carries on; lists, tables and preformatted text keep their
   lines, and script and style contents are dropped with a listing.
5. **(decided here) Import is a full page, not a dialog.** The 2026-10-05
   ruling keeps first-run setup a full page, and Import is one of its
   starts.
6. **(decided here) The site takes a Pressless look**, chosen from
   `starter.LOOKS` in the wizard, with the starter's header, footer and
   templates. The WordPress theme is not carried (§ 2 item 5).
7. **(decided here) A dangling reply is carried as a top-level comment**,
   and listed. Dropping it would lose a reader's words, which design's
   "What Import brings across" forbids.
8. **(decided here) The maintainer's run takes the PRESS-0157, PRESS-0158
   and PRESS-0161 fixes too**, since the code is shared. Its markup test
   stays the sibling generator's (§ 4.5), because that is what its readers
   saw.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 Where it starts

`src/pressless/importing.py` registers the Import wizard at `/import`,
built on `wizard.Wizard` as `setup._first_run_wizard` is, with its
progress in `wizards/import.json`. It answers only while
`not store.holds_a_site(folder)`; otherwise `/import` redirects to `/`.

Two links reach it, each shown only on a Store that holds no site: on
setup's done page where the starter was not filled, and on the list page
(`/`).

### 4.2 The steps

| Step | Shows | Check before Next |
|------|-------|-------------------|
| `export` | How to make the file: WordPress's **Tools → Export**, **All content**, **Download Export File**; and a file box | an export is held and reads (§ 4.3) |
| `media` | Counts read from the export, then fetching (§ 4.4) with progress | the fetch has ended |
| `gaps` | The files missing, how to download the uploads folder, and a ZIP box; where none is missing, that it says so | none; Next without a ZIP carries on |
| `look` | The looks, as setup's site step shows them | one of `starter.LOOKS` |
| `bring` | What Next does, then the Report (§ 4.8) | Import has written (§ 4.7) |

A wizard shows every step, so `gaps` is never skipped, and Next on
`bring` is what brings the site in. The two file boxes post to
`Face.add_upload` routes, `/import/export` and
`/import/media`, so neither file is held in memory. Every `import/` path
here is in the open site's folder under `sites/`, never the Builder's
site folder. The export is kept as `import/export.xml`; `import/` is
never published, since the Builder reads only the Store's own folders.
`import` joins `sites.SITE_NAMES` and `sitefile.LEFT_OUT`, so a saved
site file never carries the export.

### 4.3 Reading the export

`pressless_import` gains `read(export) -> Export`, used by both runs.
Before parsing, it refuses any export whose prolog — what comes before
the root element — holds a `<!DOCTYPE` or `<!ENTITY` declaration, or
does not begin with markup (`ImportStopped`, "is not a WordPress export
Pressless can read"): WordPress writes neither, and both are how an XML
file expands past its size. A post's body quoting one is not in the
prolog, and reads. An export over `EXPORT_LARGEST = 256 MiB` is
refused at upload. The S314 exemption in `pyproject.toml` stays, now
resting on that refusal.

What is carried, by `wp:post_type`:

| Type | Becomes |
|------|---------|
| `post` | an entry (§ 4.5) |
| `page` | a page (§ 4.6) |
| `attachment` | a file to fetch (§ 4.4) |
| `nav_menu_item`, `wp_navigation` | the menu (§ 4.6) |
| anything else | one Report line per type, with its count |

Comments are read as `pressless_import._comments` reads them: approved
only, and `comment_author_email` and `comment_author_IP` never read
(PRESS-0006 INV-4). A comment whose date cannot be read, or whose
identifier is empty or repeated, is listed and skipped.

### 4.4 Fetching the files

`pressless_import.fetch` does the fetching, and is the one module of the
package that reaches the network; the maintainer's `run` never calls it
(PRESS-0007 INV-10, as amended).

For each attachment, the address is its `attachment_url`, and its place is
`_upload_path` of that address, checked as `_photographs` checks it, each
part of it a single name the Store would hold; a place it would stop on
is refused, as below. The file goes to `import/media/<place>`. A file
already there is not fetched again, so a stopped fetch resumes.
`fetch.fetch_all` returns each place not fetched with why, and the wizard
keeps that in `import/unfetched.json` once the fetch has ended.

A fetch:

- uses only an `http` or `https` address the export names as an
  `attachment_url`;
- resolves the host, and refuses unless every address it resolves to is
  global (`ipaddress.ip_address(...).is_global`), and connects to an
  address it checked, never resolving again; each redirect, at most
  five, is checked the same way;
- sends no cookie and no `Authorization` header, and a `User-Agent` of
  `Pressless/<version>`;
- stops at 30 seconds without data, and at `builder.FILE_LARGEST` bytes;
- refuses to start where `room()` is below zero. `importing.py` passes
  `room`, answering `face._room(folder)`, which already keeps
  `face._SPARE` free.

A refused or failed fetch is one Report line, naming the place and why
("the old site answered 404"). It never stops Import.

**The media ZIP** (`pressless_import.unpack_media`) fills gaps by place: a member whose name ends in
`<YYYY>/<MM>/<name>` matching a missing place is unpacked to it. Members
are checked first by `sitefile.stays_inside` and `sitefile.is_link`, as a
site file's are — no absolute name, backslash, drive, `..` or link — and
the members taken must fit `room()`.
Other members are ignored.

### 4.5 Entries

`_items` carries a post whose status is `publish` as published, and
`draft`, `private`, `pending` or `future` as a draft. A `pending` or
`future` post adds a Report line: "arrived as a draft: it was waiting for
review" or "…: it was scheduled for <date>". In Import's run `_items`
takes no `page` item: § 4.6 carries pages, apart from the entries' slugs.

**Which body is markup.** `convert` takes `markup: Callable[[str], bool]`,
and passes a body `markup` rejects through `autop` before converting it.
Import's run passes `wordpress_markup`: a body holding `<!-- wp:` is block
content and converts as it is. `autop` does what WordPress's `wpautop`
does to a classic post — a blank line
ends a paragraph and a lone newline is a line break, outside `pre` and
block-level tags. The self-check compares such a body's conversion with
`autop(body)`, not the raw body. **`autop` is written from that described
behaviour and never translated from WordPress's source**, which is
GPL-licensed. The maintainer's run passes `is_markup`, unchanged, and
never hands `convert` a body `is_markup` rejects: that body is written
byte for byte (PRESS-0007 § 4.3).

**Splitting.** `visible_lines`' `_SPLITS` gains `li`, `tr`, `td`, `th`,
`hr` and `pre`, and the converter makes a line at each of them too, as
it does at the elements in its `_PARAGRAPHS`. Inside `pre` each newline
is a line. `script` and `style` elements are dropped with their contents,
each listed.

**A picture with no original in `photographs/`** — neither fetched nor
unpacked from the ZIP — is not written as a `{photo: …}` mark, because the Builder stops
on a photograph the folder lacks. The lookups return `None` for it, so it
takes the converter's existing "no attachment" path and is listed. They
return `None` too for a held file `builder.photograph_format` refuses,
which goes to `files/`; a held file `builder.file_allowed` refuses as
well is listed and not carried.

**A dangling reply** — one whose parent is not among the comments Import
carries — is
written with `parent=""` and listed, so `store.write_comments` accepts it.

### 4.6 Pages and the menu

Each `page` item becomes `pages/<slug>.html` in `starter.new_page`'s
shape, its title as the title, the stylesheets of the look chosen, and its
body in place of the area after § 4.5's markup rule. The page that
becomes `index` sits at the root, its links without `../`, as
`starter.fill` writes it. Addresses under the old site's uploads folder
whose file Import holds are rewritten to the page's `../`, or nothing for
`index`, + `builder.web_photograph(name)`, or `builder.web_file(name)` for
a file in `files/`; others stay and are listed. Blocks
reads what sections it can, and the rest is a code section (design.md
§ Pages, and how they are held).

**The front page.** A page whose slug is `home` or whose title is the
site's own becomes `index`; otherwise the first page by `wp:menu_order`.
Where the export holds no page, the starter's `index` is written.

**The menu.** One menu is read, and the Report names it and any other:

- a `wp_navigation` item, its `navigation-link` blocks giving each link's
  `label` and `url`; else
- the `nav_menu` term with the most `nav_menu_item` items, each link
  from its `_menu_item_type`, `_menu_item_object_id` and `_menu_item_url`
  postmeta, in `wp:menu_order`.

A link to a carried page becomes `{{UP}}pages/<slug>.html`, or
`{{UP}}index.html` for the front page, and a link to a carried entry
`{{UP}}` + `builder.entry_path(entry)` + `/index.html`; any other
address stays as written. A child (`_menu_item_menu_item_parent` not
`0`) joins the list after its parent and is listed. The links are written into the
starter's navigation shape by `menu.arranged`, so `menu.links` reads
them. A link no menu may hold is left out and listed; a menu left with
no link keeps the starter's Home link.

### 4.7 Writing, whole or not at all

`pressless_import.bring_in(export, media, into, look, *, unfetched=None)
-> Report` does the work, `unfetched` being `fetch_all`'s answer, in this
order: read and resolve slugs (PRESS-0007 § 4.4); convert
every body; write every Store file into `import/work/` through Store
calls, moving each held file from `import/media/` into
`photographs/`, or into `files/` where `builder.photograph_format`
returns `None`; write the starter's header, footer and templates, the
look (`look.save(look.defaults(layout), "")`) and the journal switch, on
where any post was carried; then move each folder in `import/work/` into
the site's folder, by rename. Where the site's folder already holds that
folder — `templates/`, which `templates.register` seeds at every launch —
each file moves in alone, and a file already there is kept.

A stop before the moves deletes `import/work/` and leaves the Store
empty. `import/moving` is an empty file written before the first move
and deleted after the last. While it exists,
`importing.finish_moves(folder)`, which `__main__` calls at start for
every site as it calls `sites.move_in`, moves what is left in
`import/work/` through `pressless_import.finish`; the wizard
cannot, since `holds_a_site` is True once a move lands. After the last move,
`import/media/` and `import/work/` are deleted, and `import/export.xml`
and `import/report.txt` stay.

### 4.8 The Report

`Report` gains `waiting` (pending and scheduled posts), `unfetched`
(place and reason), `menus`, `other_types` and `files` (held files kept
in `files/`). The Face shows it after **Bring it in**, each line passed
through `pressless_import.printable` and then HTML-escaped; it is also
written to `import/report.txt`. Its words are `import.report.*` keys in
the words table (PRESS-0242). Each line names the entry, page or file,
and what happened to it. A line's values — the converter's notes and a
fetch's reason among them — are `pressless_import`'s English.

## 5. Invariants

- **INV-1** — Import writes only into a Store that holds no site.
  *Test:* `tests/test_importing.py::test_import_answers_only_on_an_empty_store`
  — `/import` on a filled Store redirects to `/`, and `bring_in` into a
  folder where `store.holds_a_site` is True raises `ImportStopped`.
  *Breaks when:* the check is made at the first step only, and a site
  written in another window is overwritten at **Bring it in**.

- **INV-2** — An export declaring a DOCTYPE or an entity is refused
  before parsing. *Test:*
  `tests/test_importer.py::test_an_export_declaring_entities_is_refused`
  — an otherwise valid export with a nested entity declaration raises
  `ImportStopped`, and `xml.etree` is never called.
  *Breaks when:* the check reads only the first line, and the declaration
  follows a comment.

- **INV-3** — A fetch reaches only an address the export names, over
  `http` or `https`, at a global address, redirects included. *Test:*
  `tests/test_importer_fetch.py` — a fake resolver answering `127.0.0.1`,
  `10.0.0.1` or `169.254.169.254`, a `file:` address, and a redirect from
  a global host to `127.0.0.1`, and a resolver whose second answer is
  `127.0.0.1`, are each refused and listed, with no connection opened to
  a refused address.
  *Breaks when:* only the first hop is checked.

- **INV-4** — A fetch sends no cookie and no `Authorization` header.
  *Test:* `tests/test_importer_fetch.py::test_a_fetch_sends_no_credentials`
  — the recorded request's headers.
  *Breaks when:* a shared opener carrying the GitHub key is reused.

- **INV-5** — A file that cannot be had never stops Import: it is listed,
  and no mark names it. *Test:*
  `tests/test_importer.py::test_a_missing_original_is_listed_and_the_entry_carried`
  — one attachment answering 404: the entry is written without a
  `{photo:` mark, the Report lists it, and the build succeeds.
  *Breaks when:* the mark is written, so every publish stops on it.

- **INV-6** — A media ZIP fills only missing places, and a member that
  would leave `import/media/` is refused. *Test:*
  `tests/test_importer.py::test_a_media_zip_fills_gaps_only` — members
  `../x.jpg`, `/abs.jpg`, a link, and a match for a fetched place: the
  first three refuse the ZIP, the last leaves the fetched file unchanged.
  *Breaks when:* members are matched by bare name.

- **INV-7** — The Store is either untouched or holds the whole site.
  *Test:* `tests/test_importer.py::test_a_stop_leaves_the_store_empty`
  (a Store refusal during writing) and
  `::test_a_stop_during_the_moves_finishes_next_start`.
  *Breaks when:* files are written straight into the site's folder.

- **INV-8** — A classic body keeps its paragraphs; block content converts
  as it is. *Test:*
  `tests/test_importer.py::test_a_classic_post_keeps_its_paragraphs` —
  `"One <em>word</em>.\n\nTwo."` gives two paragraphs, and the same text
  inside `<!-- wp:paragraph -->` blocks gives what those blocks hold.
  *Breaks when:* `is_markup` decides, so the `em` makes it one paragraph.

- **INV-9** — Pending and scheduled posts arrive as drafts, each listed.
  *Test:* `tests/test_importer.py::test_waiting_posts_arrive_as_drafts`.
  *Breaks when:* `_items` keeps its three statuses.

- **INV-10** — A dangling reply is carried top-level and listed. *Test:*
  `tests/test_importer.py::test_a_dangling_reply_is_carried`.
  *Breaks when:* the reply is dropped, or written as is and refused.

- **INV-11** — List items, table cells, rules and preformatted lines each
  keep their own line, in the converter and in `visible_lines`; script and
  style contents never reach a body. *Test:* one fixture per element in
  `tests/test_importer.py::test_visible_lines_breaks_where_a_reader_sees_one`,
  and `::test_script_and_style_are_dropped_and_listed`.
  *Breaks when:* only one of the two functions gains the splits, so
  PRESS-0007 INV-5's self-check passes over fused lines.

- **INV-12** — `autop` is Pressless's own code. *Test:* none can be run;
  the review of the change checks it was written from § 4.5's description.
  *Breaks when:* WordPress's function is translated into the repository.

- **INV-13** — The menu's links reach carried pages and entries.
  *Test:* `tests/test_importer.py::test_the_menu_points_at_carried_pages`
  — one fixture per source (`wp_navigation`, `nav_menu_item`): each link
  to a carried page reads as `{{UP}}pages/<slug>.html` through
  `menu.links`.
  *Breaks when:* links keep the old site's addresses.

- **INV-14** — Every value in the Report page is escaped. *Test:*
  `tests/test_importing.py::test_the_report_escapes_what_it_names` — a
  title of `<script>` and a control character.
  *Breaks when:* a slug or title is written raw.

## 6. Failure modes

| Breaks | What happens |
|--------|--------------|
| The file is not an export | `export` step says so; nothing is kept |
| The old site is gone | every fetch fails and is listed; `gaps` offers the ZIP |
| A fetch hangs | stops at 30 seconds, listed |
| The disk fills | fetching stops before the spare is reached; each file left is listed as having no room |
| Pressless closes while fetching | the next visit resumes; held files are kept |
| Pressless closes during the moves | the next start finishes them (§ 4.7) |
| A slug cannot be held | as PRESS-0007 § 4.4: the item takes `<slug>-<post id>`, listed |
| The export holds no posts | the journal is off, and the pages are the site |
| A body nests too deeply | as `run`: `ImportStopped`, naming the post |

## 7. Tests

- `tests/test_importer.py` — the pure parts: reading (INV-2), files
  that cannot be had (INV-5), the ZIP (INV-6), whole-or-nothing (INV-7),
  markup (INV-8), statuses (INV-9), comments (INV-10), splits (INV-11)
  and the menu (INV-13).
- `tests/test_importer_fetch.py` — the fetch (INV-3, INV-4), through a
  fake resolver and a recording opener; no network.
- `tests/test_network_timeouts.py` walks `src/pressless_import/` too, so
  § 4.4's 30-second stop is checked.
- `tests/test_importing.py` — the wizard's routes on a Face test
  instance (INV-1, INV-14).
- INV-12 has no test (§ 10).
- The archive tests (`tests/test_importer_archive.py`) run the maintainer's
  `run` as now; PRESS-0007 INV-5 there must stay green with the new
  splits.
- **By hand, before release:** a fresh WordPress site with a block theme
  and one with a classic menu, each exported and brought in; and the
  export steps' wording checked against WordPress's screen.

Each named test is seen to fail against today's code before its change.

## 8. Alternatives considered (and rejected)

- **Media download only.** Rejected by the user 2026-10-22: self-hosted
  WordPress has no one-step media download.
- **Carry the WordPress theme's look.** Rejected: the export holds theme
  settings, not a stylesheet, and PRESS-0276 covers a look on top of an
  imported site.
- **A modal dialog.** Rejected (§ 3 decision 5).
- **Translate `wpautop`.** Rejected: GPL code in an MIT repository.
- **Drop a dangling reply.** Rejected (§ 3 decision 7).

## 9. Out of scope

- A site in a GitHub repository — PRESS-0218.
- A folder of web pages — PRESS-0210.
- An imported site's own look, or extra CSS — PRESS-0276.
- Slugs in other scripts kept as written — PRESS-0175.
- A guard against publishing an imported site over a repository that
  already holds one, as `starter.unpublished` guards the starter —
  deferred; not yet queued.
- A `.tar` media download — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_importing.py::test_import_answers_only_on_an_empty_store` |
| INV-2 | `tests/test_importer.py::test_an_export_declaring_entities_is_refused` |
| INV-3 | `tests/test_importer_fetch.py` |
| INV-4 | `tests/test_importer_fetch.py::test_a_fetch_sends_no_credentials` |
| INV-5 | `tests/test_importer.py::test_a_missing_original_is_listed_and_the_entry_carried` |
| INV-6 | `tests/test_importer.py::test_a_media_zip_fills_gaps_only` |
| INV-7 | `tests/test_importer.py` (two tests, § 5) |
| INV-8 | `tests/test_importer.py::test_a_classic_post_keeps_its_paragraphs` |
| INV-9 | `tests/test_importer.py::test_waiting_posts_arrive_as_drafts` |
| INV-10 | `tests/test_importer.py::test_a_dangling_reply_is_carried` |
| INV-11 | `tests/test_importer.py` (two tests, § 5) |
| INV-12 | **nothing** — authorship cannot be tested; the code review is the only check |
| INV-13 | `tests/test_importer.py::test_the_menu_points_at_carried_pages` |
| INV-14 | `tests/test_importing.py::test_the_report_escapes_what_it_names` |
| The export steps' wording | **nothing** — WordPress's screens change; § 7's hand run |

## 11. Cross-doc impact

- **PRESS-0007**, amended in the same change: decision 3 and § 4.2 gain
  `pending` and `future` as drafts; decision 11's packaged program now
  carries the package; § 4.3 gains § 4.5's splits and drops, and
  `is_markup` becomes the maintainer's run's choice; § 4.5, § 4.7, § 6
  and INV-8 list a missing original and carry on; § 4.6 carries a
  dangling reply; § 4.8 and INV-10 exempt `pressless_import.fetch`;
  § 4.1 points at this spec's `Report` fields and `markup` argument;
  INV-6's and INV-7's tests gain a missing original and a reply whose
  parent is not carried.
- **`docs/design.md`**, amended in the same change: rule 9 lets Import
  fetch the files the export names and write its own `import` folder, and
  "one site per copy" gives way to PRESS-0223's sites; the parts table,
  § Setup's three starts and *What Import brings across* say where the
  files come from; the disk table names the `import` folder.
- **PRESS-0262** INV-9, amended in the build: it holds within
  `src/pressless/`, and `pressless_import.fetch` is the one network
  module outside it.
- **The privacy policy on the Hub**, if it lists what Pressless contacts:
  Import contacts the user's old site. Checked when this ships.
- **CHANGELOG**, at release.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0125-wordpress-import-loop-log.md`.

## 13. Resource cost

- The export is parsed whole: `EXPORT_LARGEST` caps it at 256 MiB.
- Fetched files sit in `import/media/` once, and move into the Store by
  rename, so the media takes its own size on disk, not twice.
- No new dependency: `urllib.request`, `ipaddress`, `zipfile`.
