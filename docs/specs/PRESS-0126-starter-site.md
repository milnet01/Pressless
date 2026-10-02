<!-- ants-spec-format: 1 -->
# PRESS-0126 — A plain starter site for an install that never ran Import

**Status:** spec draft (2026-10-02).
**Kind:** implement.
**Source:** ROADMAP PRESS-0126 (user decision 2026-09-17 at the PRESS-0124
design gate; `docs/design.md` § Setup's three starts, rewritten 2026-10-02).

**Blocked by:** PRESS-0214.
**Amends:** PRESS-0021 (§ 3 decision 9, § 4.6, § 4.9), PRESS-0013 (§ 4.3),
PRESS-0008 (§ 4.1), PRESS-0006 (§ 4.1). § 11 lists each edit.

Layman: someone starting from nothing ticks one box in setup and gets a
simple site — header, footer, menu, Home and About pages and a plain
stylesheet — that they can preview, change and publish; Pressless will not
let that starter site replace a real site already on GitHub by accident.

## 1. Goal

After this ships, setup on an install whose Store holds no site offers the
starter site. Ticked, setup fills the Store with Pressless's own plain
header, footer, menu, Home and About pages, the templates and a plain
stylesheet, with the journal off. The install can then preview, edit and
publish. The starter's first publish refuses where the repository already
holds a site, until the user says in so many words to replace it.

## 2. Problem

1. **An empty install cannot build.** `builder._Build.read_html` reads the
   three furniture files through `store.read_html`, which raises
   `StoreError` (*"there is no file header.html"*) where the Store holds
   none. Executed 2026-09-17 and recorded on the roadmap item. So the
   editor, the page editor's preview and Publish all fail on an install
   that never ran Import.
2. **Nothing supplies a stylesheet.** Every page the Builder writes links
   `builder.STYLESHEETS` — `assets/site.css` and `assets/blog.css` — and
   PRESS-0008 § 3 decision 3 leaves `assets/` outside Pressless. An
   imported site carries its own `assets/`; a new repository has none, so a
   starter site would publish unstyled.
3. **Setup never reads or fills the Store** (PRESS-0021 § 4.9), yet
   `docs/design.md` § Setup's three starts has setup fill an empty Store.
4. **Nothing stops a starter site replacing a real one.** A program moved
   beside a new `Pressless-data` folder runs first-run setup again against
   the same repository. `publishing.publish` would build the starter site and
   `publisher.publish` would make the repository match it.
5. **The publish guard refuses a site with no entries.**
   `publishing.publish` raises `NothingToPublish` where
   `store.list_slugs(folder, draft=False)` is empty, and a starter site has
   no entries. The design limits that guard to a site whose journal is on;
   PRESS-0214 builds the switch.

## 3. Scope decisions (agreed with the user)

1. **The starter is a choice in setup, not automatic.** Decided by the user
   2026-10-02. Import and take-in run only into an empty copy, so filling
   every empty install would lock out a later Import.
2. **The starter's stylesheet is kept with the user's files.** Decided by the
   user 2026-10-02: a Store file the Builder publishes, which is where the
   design puts the look's style code. Not a file placed once on GitHub.
3. **PRESS-0214's journal switch is built first.** Decided by the user
   2026-10-02. This item turns the journal off through it.
4. **The starter set lives in code, as `src/pressless/starter.py`.**
   *(decided here)* `templates.STARTERS` is the precedent; package data files
   would need `--add-data` in both build scripts.
5. **"Already holds a site" means an `index.html` at the repository root.**
   *(decided here)* GitHub Pages serves that file. A list of harmless names
   would be typed from memory, which design rule 9's derivation forbids.
6. **The check runs at the publish, not at setup.** *(decided here)* The
   design places it there, and the publish is the act that replaces.
7. **Whether the starter is still unpublished is a marker file in
   Pressless's own folder.** *(decided here)* Settings' field set is a
   breaking surface (PRESS-0001 INV-6).
8. **The site's name is written into the header and footer once, as text.**
   *(decided here)* Moving the name into the Store is PRESS-0213's.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/starter.py — new; the Face's, as templates.py is
MARKER = "starter-unpublished"   # in Pressless's own folder; empty file

def offered(folder: Path) -> bool: ...         # § 4.4
def fill(folder: Path, site_name: str) -> None: ...
def unpublished(folder: Path) -> bool: ...      # MARKER exists
def published(folder: Path) -> None: ...        # removes MARKER; absent is fine
```

```python
# src/pressless/store.py — added
LOOK_FOLDER = "look"
STYLE_CODE_NAME = "style.css"

def style_code_path(folder: Path) -> Path: ...  # folder / LOOK_FOLDER / STYLE_CODE_NAME
def read_style_code(folder: Path) -> str | None: ...   # None where there is none
def write_style_code(folder: Path, css: str) -> Path: ...
def holds_a_site(folder: Path) -> bool: ...
```

```python
# src/pressless/builder.py — added and changed
STYLE_CODE = "look/style.css"    # where the Store's style code is published
ROOT_OUTPUT = (..., "look")      # gains "look"

def stylesheets(folder: Path) -> tuple[str, ...]: ...
```

```python
# src/pressless/publishing.py — added and changed
class WouldReplaceASite(Exception): ...   # the starter's first publish met a site

def publish(..., replacing: bool = False) -> Published: ...
```

### 4.2 The Store's look

`read_style_code` decodes bytes as `read_html` does: `None` where the file
is absent, `StoreError` where it is unreadable or not UTF-8.
`write_style_code` writes whole or not at all through
`_write_atomically(..., newline="")`, as `write_html` does. Nothing bins the
file in this item, so `_BINNABLE` is unchanged.

**`holds_a_site`** is True where any of `published/`, `drafts/`, `pages/`,
`furniture/`, both `WAITING_FOLDERS`, `comments/`, `photographs/` or
`forwards/` holds a file. `templates/` and `look/` are not counted:
`templates.register` seeds the templates at every launch, and neither is a
site on its own.

### 4.3 The starter set

`fill(folder, site_name)`, in this order:

1. Write `MARKER`.
2. Write each file below **only where it is absent** — never over one the
   Store holds.
3. `templates.seed(folder)`, which writes nothing where `templates/` exists.
4. Turn the journal off through PRESS-0214's switch.

| Store file | Must hold |
|---|---|
| `furniture/header.html` | a link to `{{UP}}index.html` whose text is the site's name, and `{{NAVIGATION}}` once |
| `furniture/navigation.html` | `<nav class="primary" aria-label="Primary">` holding Home (`href="{{UP}}index.html" data-nav="Home"`) and About (`href="{{UP}}pages/about.html" data-nav="about"`), and no link to `blog/` |
| `furniture/footer.html` | `{{YEAR}}` and the site's name |
| `pages/index.html` | a whole HTML document linking `look/style.css`, with a `HEADER:START page="Home"` / `HEADER:END` pair, a `FOOTER:START` / `FOOTER:END` pair, and a heading and a sentence telling the user this is their homepage to change |
| `pages/about.html` | the same at depth 1: it links `../look/style.css`, and its header pair carries `page="about"` |
| `look/style.css` | a plain stylesheet for those pages and for the Builder's page shell (`builder.BODY_CLASS` included) |

The site's name is escaped with `html.escape(site_name, quote=True)`
wherever it is written. The words are the implementer's. Like
`templates.STARTERS`, they name nobody and assume nothing about the user.
Body text and links have a contrast ratio of at least 4.5:1 against their
background: the first user is partially sighted.

### 4.4 Setup

`offered(folder)` is `not store.holds_a_site(folder) or unpublished(folder)`.
The second half lets a fill an interruption cut short be completed.

- **The form** (PRESS-0021 § 4.3) gains a checkbox named `start` with value
  `starter`, on either path, only where `offered` holds. It is ticked on
  first run. Its words say that leaving it unticked keeps this copy empty for
  bringing in a site the user already has.
- **The sequence** (PRESS-0021 § 4.6) gains a step between storing the key
  and saving: **fill**, only where `start` is `starter` and `offered` still
  holds. It is `starter.fill(folder, candidate.site_name)` inside
  `face.capture()`. A failure is shown through `Face.fail` and ends the
  request, so first run saves no settings file.
- **The done page** says the starter site is in place and is not on the web
  until the user publishes it.

A posted `start` where `offered` is False is ignored.

### 4.5 Publishing

In `publishing.publish`, the guard step gains a check that runs first:

1. Where `starter.unpublished(folder)` and not `replacing`, call
   `publisher.root_entries(settings, key, transport)`. Where any entry,
   with any trailing `/` removed and folded with `str.casefold`, equals
   `"index.html"`, raise `WouldReplaceASite`. That fold is PRESS-0009 § 4.4's.
2. The existing guard, unchanged here; PRESS-0214 limits it to a site whose
   journal is on.

Both run before the build, so a refusal leaves the site folder and GitHub
untouched, and the entry move is put back as for `NothingToPublish`.

After `publisher.publish` returns, `starter.published(folder)` removes the
marker. An `OSError` there is caught and given to the log; the publish's
result stands.

`SENTENCES[WouldReplaceASite]` says the repository already holds a website,
that the starter site would replace it, and that Pressless stopped
(`Site.UNCHANGED`). Its next step names the replace page.

**The replace page**, added by `publishing.register`:

- `GET /publish/replace` — only while `starter.unpublished(folder)`;
  otherwise it says there is nothing to replace. It names the repository,
  says what replacing does, lists `settings.untouchable` with a ticked
  "keep" checkbox per entry, and asks the user to type the repository's name.
- `POST /publish/replace` — where the typed name, stripped, is not exactly
  `settings.repository`, the page is shown again with a hint, and nothing is
  written or requested. Otherwise, where any entry was unticked,
  `settings.save` writes the list without it. Then
  `publish(folder, saved, key, entry=None, replacing=True, ...)` runs, and
  its result is shown as `/page/publish` shows one.

### 4.6 The Builder

`stylesheets(folder)` is `(STYLE_CODE,)` where
`store.style_code_path(folder).is_file()`, otherwise `STYLESHEETS`.

- `build`, `preview` and `preview_html` write the style code to
  `STYLE_CODE` in the folder they build into, where the Store holds it.
- The page shell (`_Build.page`) links `stylesheets(self.folder)` in place of
  `STYLESHEETS`.
- `editor` and `page_editor` link `PREVIEW_ADDRESS + sheet` for each sheet in
  `builder.stylesheets(folder)` in place of `builder.STYLESHEETS`.
- A fixed page is unchanged: it carries its own links, byte for byte.
- `content()` does not copy the style code (§ 9).

`ROOT_OUTPUT` gains `"look"`, so `setup.untouchable` removes it like any
other Builder output.

## 5. Invariants

- **INV-1** — `store.holds_a_site` is False for a folder holding only
  seeded templates and style code, and True once any one of § 4.2's counted
  folders holds a file. *Test:*
  `tests/test_store.py::test_holds_a_site_counts_writing_not_templates`,
  one case per counted folder.
  *Breaks when:* `templates/` is counted, so every launched install holds a
  site, or a counted folder is left out.
- **INV-2** — After `fill`, `builder.build` succeeds and writes
  `index.html`, `pages/about.html` and `look/style.css`. *Test:*
  `tests/test_starter.py::test_a_filled_starter_builds`.
  *Breaks when:* a furniture file is missing, or a marker pair does not pair.
- **INV-3** — `fill` writes `MARKER` before any Store file, and never
  overwrites a file the Store holds. *Test:*
  `tests/test_starter.py::test_fill_writes_only_what_is_absent`, with a
  sentinel header present and a write that fails after the marker.
  *Breaks when:* the sentinel header is replaced, or no marker is left by
  the interrupted fill.
- **INV-4** — The site's name reaches the header and footer escaped. *Test:*
  `tests/test_starter.py::test_the_name_is_escaped`, with the name
  `A <b> & "Co"`; the built `index.html` holds `A &lt;b&gt; &amp; &quot;Co&quot;`
  and no `<b>`.
  *Breaks when:* the name is written unescaped.
- **INV-5** — The starter's menu links Home and About and nothing under
  `blog/`, and the built Home page marks Home `aria-current="page"`. *Test:*
  `tests/test_starter.py::test_the_menu_is_home_and_about`.
  *Breaks when:* a journal link is left in, or `data-nav` and the marker's
  `page` disagree.
- **INV-6** — Setup shows the `start` box only while `offered` holds, and a
  posted `start=starter` where it does not leaves the Store byte-identical.
  *Test:* `tests/test_setup.py::test_the_starter_is_offered_only_on_an_empty_store`.
  *Breaks when:* the box shows over an imported Store, or a forged post fills
  over one.
- **INV-7** — On first run a failed fill leaves no settings file. *Test:*
  `tests/test_setup.py::test_a_failed_fill_saves_nothing`, with
  `starter.fill` raising `StoreError`.
  *Breaks when:* the fill runs after the save.
- **INV-8** — An unticked box leaves the Store holding no site, and setup
  finishes. *Test:* `tests/test_setup.py::test_an_unticked_box_fills_nothing`.
  *Breaks when:* the fill ignores the box.
- **INV-9** — While the marker exists, a publish to a repository whose root
  holds `Index.html` raises `WouldReplaceASite` before the build: the site
  folder is not written and no upload request is made. A root of
  `README.md` alone publishes. *Test:*
  `tests/test_publishing.py::test_the_starter_will_not_replace_a_site`, with
  a fake transport.
  *Breaks when:* the check folds no case, runs after the build, or treats any
  root entry as a site.
- **INV-10** — The marker is gone after a publish `publisher.publish`
  returned from, and still there after one that raised. *Test:*
  `tests/test_publishing.py::test_the_marker_outlives_only_a_failed_publish`.
  *Breaks when:* the marker is removed before the upload, or never.
- **INV-11** — Without the marker, a publish makes no `root_entries`
  request. *Test:*
  `tests/test_publishing.py::test_an_imported_site_publishes_as_before`,
  counting the fake transport's requests.
  *Breaks when:* the check runs on every publish.
- **INV-12** — `POST /publish/replace` with a wrong repository name writes
  and requests nothing. With the right name and `CNAME` unticked, the saved
  list lacks `CNAME` before the publish runs with `replacing=True`. *Test:*
  `tests/test_publishing.py::test_replace_needs_the_name_and_drops_what_is_unticked`.
  *Breaks when:* the name is not checked, or the list is saved after the
  publish.
- **INV-13** — Where the Store holds style code, an entry page links
  `look/style.css` alone and the site folder holds it. Where it holds none,
  the page links `STYLESHEETS` and the site folder has no `look/`. *Test:*
  `tests/test_builder.py::test_the_style_code_replaces_the_assets_links`.
  *Breaks when:* `look/style.css` is written or linked for a Store without
  style code, or the assets links stay beside it.
- **INV-14** — `setup.untouchable(("look", "CNAME"))` is `("CNAME",)`.
  *Test:* `tests/test_setup.py::test_the_look_is_builder_output`.
  *Breaks when:* `"look"` is not in `ROOT_OUTPUT`.
- **INV-15** — A preview of a fixed page writes `look/style.css` into the
  preview folder where the Store holds style code. *Test:*
  `tests/test_builder.py::test_a_preview_carries_the_style_code`.
  *Breaks when:* only `build` writes it, and the preview shows unstyled.
- **INV-16** — After `fill`, a publish of the untouched starter site is not
  refused with `NothingToPublish`. *Test:*
  `tests/test_starter.py::test_the_starter_publishes_with_no_entries`,
  written once PRESS-0214 lands.
  *Breaks when:* the fill leaves the journal on.

## 6. Failure modes

- **A fill cut short** leaves the marker and some files. Setup showed the
  failure and, on first run, saved nothing. `offered` still holds, so the
  next setup offers the box, and `fill` writes only what is missing.
- **`root_entries` fails at the publish.** The publish stops with that
  failure's own sentence, before the build, and the entry move is put back.
- **The marker cannot be removed after a publish that landed.** The result
  stands. The next publish finds its own `index.html` and refuses, so the
  user confirms a replace once. Safe, and noisy once.
- **`OutcomeUnknown`.** The marker stays, with the same consequence.
- **A live repository holding its own root `look` entry** stops being
  protected at the next derivation, and the Builder's `look/` replaces it.
  § 7 owes a check of the first writer's root.
- **Style code that is not UTF-8** stops the build with `StoreError`, as a
  bad page does.
- **Unticked and never filled**, the install shows today's empty-install
  errors (§ 9).

## 7. Tests

`tests/test_starter.py` is new, in CI. It carries INV-2, INV-3, INV-4,
INV-5 and INV-16. `tests/test_store.py` gains INV-1; `tests/test_setup.py`
INV-6, INV-7, INV-8 and INV-14; `tests/test_publishing.py` INV-9, INV-10,
INV-11 and INV-12;
`tests/test_builder.py` INV-13 and INV-15.

Each test is seen failing against the code before this item, then
mutation-probed once the code lands.

**By hand, before release:**

- On the Windows box: an empty install, setup with the box ticked, then the
  editor, the page editor's preview and a publish to a new repository.
- The contrast of `look/style.css`, checked with a contrast tool.
- `setup.untouchable` over the first writer's repository root keeps every
  entry it kept before this item (§ 6).

## 8. Alternatives considered (and rejected)

- **Fill every empty install without asking.** Rejected by the user (§ 3
  decision 1).
- **Put the stylesheet on GitHub once.** Rejected by the user (§ 3 decision
  2): Pressless could never update it, and undo could not bring it back.
- **Link the style code beside the `assets/` pair.** Rejected: a starter
  site asks for two files that do not exist, and an imported site would get
  two stylesheets fighting.
- **Starter files as package data.** Rejected (§ 3 decision 4).
- **Detect a site by any root entry beyond a list of harmless names.**
  Rejected (§ 3 decision 5).
- **Check the repository at setup.** Rejected (§ 3 decision 6).
- **Keep the marker in Settings.** Rejected (§ 3 decision 7).

## 9. Out of scope

- Offering to take the repository's site in on the refusal — PRESS-0218.
- The journal switch — PRESS-0214.
- The site's name, description and icon held in the Store — PRESS-0213.
- Choosing and editing the look, its draft, and the style code travelling in
  `content/` for undo — PRESS-0196.
- The Privacy page in the starter set — PRESS-0199.
- Starter pages written as Blocks sections — PRESS-0215. They are fixed
  pages as PRESS-0014 holds them today.
- The editor's errors on an install left empty — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_store.py::test_holds_a_site_counts_writing_not_templates` |
| INV-2 | `tests/test_starter.py::test_a_filled_starter_builds` |
| INV-3 | `tests/test_starter.py::test_fill_writes_only_what_is_absent` |
| INV-4 | `tests/test_starter.py::test_the_name_is_escaped` |
| INV-5 | `tests/test_starter.py::test_the_menu_is_home_and_about` |
| INV-6 | `tests/test_setup.py::test_the_starter_is_offered_only_on_an_empty_store` |
| INV-7 | `tests/test_setup.py::test_a_failed_fill_saves_nothing` |
| INV-8 | `tests/test_setup.py::test_an_unticked_box_fills_nothing` |
| INV-9 | `tests/test_publishing.py::test_the_starter_will_not_replace_a_site` |
| INV-10 | `tests/test_publishing.py::test_the_marker_outlives_only_a_failed_publish` |
| INV-11 | `tests/test_publishing.py::test_an_imported_site_publishes_as_before` |
| INV-12 | `tests/test_publishing.py::test_replace_needs_the_name_and_drops_what_is_unticked` |
| INV-13 | `tests/test_builder.py::test_the_style_code_replaces_the_assets_links` |
| INV-14 | `tests/test_setup.py::test_the_look_is_builder_output` |
| INV-15 | `tests/test_builder.py::test_a_preview_carries_the_style_code` |
| INV-16 | `tests/test_starter.py::test_the_starter_publishes_with_no_entries` |
| § 4.3 contrast | **nothing** in CI — by hand (§ 7) |
| § 4.3 words name nobody | **Partial:** the leak sweep in `scripts/local-ci.sh` catches the patterns it holds; the rest is read |
| § 6 a root `look` on a live repository | **nothing** in CI — by hand against the first writer's root (§ 7) |

## 11. Cross-doc impact

Each edit below is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0021-setup.md` § 3 decision 9 and § 4.9 — setup now reads
  the Store to decide the offer, and writes it only through `starter.fill`.
  § 4.6 gains the fill step.
- `docs/specs/PRESS-0013-publish.md` § 4.3 — the guard step gains the
  replace check, and `publish` gains `replacing`.
- `docs/specs/PRESS-0008-builder.md` § 4.1 — `ROOT_OUTPUT` gains `look`, and
  the page shell links `stylesheets(folder)`.
- `docs/specs/PRESS-0006-pages-furniture-comments.md` § 4.1 — the Store gains
  the look's style code.
- `docs/specs/PRESS-0012-editor.md` and
  `docs/specs/PRESS-0014-fixed-pages.md` — their screens link
  `builder.stylesheets(folder)`.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0126-starter-site-loop-log.md`.

## 13. Resource cost

One empty marker file, removed by the first successful publish, and one
extra GitHub request on each publish while it exists. No new dependency.
