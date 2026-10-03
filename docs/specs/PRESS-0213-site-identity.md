<!-- ants-spec-format: 1 -->
# PRESS-0213 — The site's name and short description

**Status:** accepted (2026-10-03).
**Kind:** feature.
**Source:** ROADMAP PRESS-0213 (user decision 2026-10-02, PRESS-0198,
settled 2026-10-03; `docs/design.md` § Pages, and how they are held).

**Amends:** PRESS-0001 (§§ 4.1–4.4, INV-6), PRESS-0005 (§ 4.1,
`move_to_bin`'s folders), PRESS-0008 (§ 3 decision 2, §§ 4.3, 4.7, the
furniture table), PRESS-0015 (§ 4.4), PRESS-0021 (the Settings page's
fields, INV-5), PRESS-0126 (§ 3 decision 8, § 4.3), PRESS-0199 (the Privacy page's
name), PRESS-0212 (the *site* step). § 11 lists each edit.

Layman: the site's name and a one-line description belong to the site,
not to the computer. They travel with the site, undo brings them back,
and changing the name reaches every page's header and footer.

## 1. Goal

After this ships, the site's name and a short description are held in the
Store, set on the first-run wizard's *site* step and on the Settings page.
Every page Pressless builds carries the name in its title, and a header or
footer that names the site shows the current name and description. An
install from before this keeps its name: it is moved into the Store once,
at launch.

## 2. Problem

1. **The name is a machine fact.** `settings.Settings.site_name` holds it,
   so it is not in `content/`, and undo cannot bring it back.
   `docs/design.md` puts the identity in the Store.
2. **There is no description.** Nothing holds one, and no page shows one.
3. **A rename reaches only the Builder's own titles.** `starter.fill` writes
   the name into the header and footer as text, so a site renamed in
   Settings still shows the old name in both.

## 3. Scope decisions (agreed with the user)

1. **The name and a short description now; the icon and the sharing
   picture in 0.10.0**, beside PRESS-0197's uploads. Decided by the user
   2026-10-03.
2. **The name moves from Settings to the Store, carried across on an
   existing install; Settings keeps the address.** Decided with the user
   2026-10-02 (`docs/design.md` § Pages, and how they are held).
3. **The identity is its own file, `identity/identity.json`, not keys in
   `options/options.json`.** *(decided here)* Undo restores the options
   file's absence (PRESS-0214 § 4.4). Undoing to a state from before this
   change would then wipe the name. Its own file is restored as the
   forwards file is: a fetched state without one keeps the Store's.
4. **No draft for the identity yet.** *(decided here)* A change goes out
   with the next publish, as a Settings change does today. The design gives
   the identity a draft alongside the header, footer, look and site-wide
   script; nothing builds drafts for those either, and they belong
   together.
5. **The header and footer name the site through two new placeholders,
   `{{SITE_NAME}}` and `{{SITE_DESCRIPTION}}`.** *(decided here)* The
   furniture already has placeholders the Builder fills (PRESS-0008's
   table), so a rename reaches every page with no page rewritten. The
   starter writes them in place of the name. Furniture written before this
   keeps the name as text: Pressless never rewrites the user's HTML.
6. **A fixed page's own `<title>` is not filled.** *(decided here)* A fixed
   page is kept byte for byte outside its furniture markers (PRESS-0014),
   and the starter's homepage and About page carry the name as text.
7. **No new failure type.** *(decided here)* A refused answer is a hint on
   the form, found by `store.identity_problem` before anything is written.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The Store

```python
# src/pressless/store.py — added
IDENTITY_FOLDER = "identity"
IDENTITY_FILE = "identity.json"

@dataclass(frozen=True)
class Identity:
    name: str
    description: str = ""

def identity_path_for(folder: Path) -> Path: ...  # folder / IDENTITY_FOLDER / IDENTITY_FILE
def identity_problem(identity: Identity) -> str | None: ...  # "name", "description" or None
def read_identity(folder: Path) -> Identity | None: ...
def write_identity(folder: Path, identity: Identity) -> Path: ...
```

The file is UTF-8 JSON, an object with string values `"name"` and
`"description"`.

- **`identity_problem`** returns `"name"` where the name is empty after
  stripping or holds a line break, `"description"` where the description
  holds a line break, and None otherwise. These are `settings.check`'s rule
  for `site_name` today, moved.
- **`read_identity`** returns None where the file is absent. It raises
  `StoreError` where the file cannot be read, is not UTF-8, is not a JSON
  object, lacks `"name"`, holds a value for either key that is not a
  string, or holds an `Identity` that `identity_problem` refuses. A missing
  `"description"` reads as `""`. Other keys are ignored.
- **`write_identity`** raises `StoreError` where `identity_problem` refuses
  the identity, before anything is written. Otherwise it writes
  `{"description": …, "name": …}` whole through `_write_atomically`, keys
  sorted, as `write_options` does.
- **`IDENTITY_FOLDER` joins `_BINNABLE`**, because undo bins the version it
  replaces (§ 4.5). It does not join `_SITE_FOLDERS`: a name alone is no
  site, so the starter is still offered.

### 4.2 Settings

`Settings` loses `site_name`. `load` no longer reads it, `check` no longer
checks it, and `save` no longer writes it. A `"site_name"` already in the
file is carried through like any other key `load` does not read
(PRESS-0001 § 4.4), until § 4.3 retires it.

```python
# src/pressless/settings.py — added
def retired_site_name(folder: Path) -> str | None: ...
def save(folder: Path, settings: Settings, *, retire: tuple[str, ...] = ()) -> None: ...
```

- **`save`'s `retire`** names carried keys to leave out of what it writes.
  Only § 4.3 passes it.
- **`retired_site_name`** returns the settings file's `"site_name"` where
  the file exists, parses as a JSON object, and holds a string there that
  `store.identity_problem` would accept as a name. Otherwise None. It
  raises nothing.

### 4.3 Carrying the name across

```python
# src/pressless/setup.py — added
def carry_name_across(folder: Path) -> str | None: ...
```

`__main__._serve_held` calls it once, inside `served.capture()`, before
the `settings.load` that chooses the first page. In order:

1. `name = settings.retired_site_name(folder)`. None → return None.
2. Where `store.read_identity(folder)` is None, write
   `store.Identity(name)`. A `StoreError` stops here and returns a sentence
   saying the site's name could not be moved and will be tried at the next
   launch, with the error's own words. `_serve_held` prints it to the
   console.
3. `settings.save(folder, settings.load(folder), retire=("site_name",))`.
   A `SettingsError` here leaves the key for a later launch and returns
   None: the identity is already written.

The identity is written before the key is retired, and no other save
retires it, so a failure at either step loses nothing.

### 4.4 The Builder

`_Build` reads `store.read_identity(self.folder)` once. Where it is None,
the name and description are both `""`.

- **A page's title** (`page`) is `<title> — <name>` where the name is not
  empty, and the page's own title alone where it is.
- **The furniture** (`_Furniture.fill`) fills two more placeholders, in the
  header and in the footer, after `{{NAVIGATION}}` so they are filled
  inside it too:

  | Placeholder | Becomes |
  |---|---|
  | `{{SITE_NAME}}` | the name, `html.escape(…, quote=True)` |
  | `{{SITE_DESCRIPTION}}` | the description, escaped the same way |

- **`content()`** copies `identity/identity.json` where it exists.

The preview and the page editor build through the same code, so they show
the current name.

### 4.5 Undo

`undo._read` reads `content/identity/identity.json` from the fetched state
with `store.read_identity`, into the state's own field. Where the fetched
identity is not None and differs from `store.read_identity(folder)`, the
Store's file goes to the bin where there is one, and the fetched identity
is written. A reversal is recorded for each step. **A fetched state without
the file keeps the Store's**, as PRESS-0015 § 4.4 does for every kind but
the options file.

### 4.6 The wizard's *site* step and the Settings page

Both forms gain a field `site_description`, labelled "A short description
of your site (optional)", beside `site_name`.

- **The *site* step's fields are `site_name`, `site_description` and
  `start`.** Its check builds `store.Identity` from the two answers. Where
  `identity_problem` returns a key, the step answers with a `wizard.Hint`
  on that field: the name's hint is `_HINTS["site_name"]` as today, and the
  description's is "Write the description on one line, or leave it empty."
- **The Settings page** shows the name and description from
  `store.read_identity(folder)`, empty where it is None, and checks them
  the same way, with the same hints.
- **`_save_sequence` takes an `identity: store.Identity`** and writes it
  with `store.write_identity` after the starter fill and before
  `settings.save`. The settings file is still written last, so its
  presence still says first run finished. A `StoreError` stops the
  sequence before the save, through `Face.fail`.
- **`starter.fill(folder, site_name)`** keeps its signature. Its header
  writes `{{SITE_NAME}}` where it wrote the name, and a
  `<p class="site-description">{{SITE_DESCRIPTION}}</p>` after the link.
  Its footer writes `{{SITE_NAME}}` where it wrote the name. The homepage's
  and About page's own titles and headings still carry the name as text
  (§ 3 decision 6).
- **The Privacy page** (`setup._privacy`, `google_setup`) is given
  `store.read_identity(folder)`'s name, and "this site" where it is None.

## 5. Invariants

- **INV-1** — `read_identity` returns None for an absent file,
  `Identity("A", "")` for `{"name": "A"}`, and raises `StoreError` for `[]`,
  `{}`, `{"name": 1}`, `{"name": " "}`, `{"name": "A", "description":
  "x\ny"}` and bytes that are not UTF-8. *Test:*
  `tests/test_store.py::test_read_identity_reads_the_identity_file`.
  *Breaks when:* a malformed file is read as some name, or an absent one
  raises.
- **INV-2** — `write_identity` refuses an identity `identity_problem`
  refuses, and writes nothing. *Test:*
  `tests/test_store.py::test_write_identity_refuses_a_bad_name`, with a
  file already holding `Identity("A")`, then a name of `"two\nlines"`.
  *Breaks when:* a refused identity reaches the disk.
- **INV-3** — The field names of `Settings` no longer include `site_name`.
  `save` over a file carrying `"site_name"` keeps it, and the same save
  with `retire=("site_name",)` writes a file without it. *Test:*
  `tests/test_settings.py::test_field_names_are_the_documented_set` and
  `::test_save_retires_only_what_it_is_told`.
  *Breaks when:* the field stays, an ordinary save drops the key, or
  `retire` keeps it.
- **INV-4** — With a settings file carrying `"site_name": "Old"` and no
  identity, `carry_name_across` leaves `Identity("Old")` in the Store and no
  `"site_name"` in the settings file. With an identity `Identity("New")`
  already there, it keeps `"New"` and still retires the key. Where the
  identity cannot be written, the settings file is unchanged and a sentence
  is returned. Where `settings.load` refuses the file, the identity is
  written, the key stays, and None is returned. *Test:*
  `tests/test_setup.py::test_the_name_is_carried_across_once`.
  *Breaks when:* the key is retired before the identity is written, an
  existing identity is overwritten, or a moved name is reported as not
  moved.
- **INV-5** — A built entry page's title ends ` — A & B`, escaped, for an
  identity named `A & B`, and is the entry's title alone with no identity.
  A header holding `{{SITE_NAME}}` and `{{SITE_DESCRIPTION}}` builds with
  both filled and escaped, on an entry page and on a fixed page. *Test:*
  `tests/test_builder.py::test_the_identity_names_every_page`.
  *Breaks when:* the title reads Settings, or a placeholder is left or
  filled unescaped.
- **INV-6** — `content/identity/identity.json` is written where the Store
  holds the file, and not otherwise. *Test:*
  `tests/test_builder.py::test_content_carries_the_identity`.
  *Breaks when:* the file is left out of `content/`.
- **INV-7** — An undo whose fetched state holds `Identity("Then")` over a
  Store holding `Identity("Now")` writes `"Then"` and bins the Store's
  file. A fetched state with no identity file keeps `"Now"`. *Test:*
  `tests/test_undo.py::test_undo_restores_the_identity_and_keeps_it_when_absent`.
  *Breaks when:* undo ignores the file, or wipes the name where the fetched
  state has none.
- **INV-8** — The wizard's *site* step, walked with a name and a
  description, finishes with both in the Store and no `site_name` in the
  settings file. A description holding a line break, or an empty name,
  answers with a hint on that field and writes neither the identity nor
  the settings file. *Test:*
  `tests/test_setup.py::test_the_site_step_saves_the_identity`.
  *Breaks when:* the identity is written into Settings, after the settings
  file, or past a refused answer.
- **INV-9** — The Settings page shows the Store's name and description, and
  a save with a new name changes the identity and leaves no `site_name` in
  the settings file. *Test:*
  `tests/test_setup.py::test_settings_page_edits_the_identity`.
  *Breaks when:* the page reads or writes the name anywhere but the Store.
- **INV-10** — The starter's header and footer hold `{{SITE_NAME}}` and not
  the name as text, and its header holds `{{SITE_DESCRIPTION}}`. *Test:*
  `tests/test_starter.py::test_the_furniture_names_the_site_by_placeholder`.
  *Breaks when:* `fill` writes the name into either file.

## 6. Failure modes

- **A malformed identity file** stops the build and the Settings page with
  `StoreError`, naming the file. It is never read as some name by guess.
- **A carry-across that fails** prints its sentence at launch and leaves
  the old key in place. Until a launch succeeds, pages build with no name
  in their titles, and the Settings page shows the name box empty; saving
  it there settles it.
- **A furniture file written before this** keeps the name as text, so a
  rename does not reach it. The user can write `{{SITE_NAME}}` there in the
  page editor.
- **An older Pressless** reading a settings file this one saved refuses it
  for its missing `site_name`. Self-update only moves forwards.

## 7. Tests

`tests/test_store.py` gains INV-1 and INV-2; `tests/test_settings.py`
INV-3; `tests/test_setup.py` INV-4, INV-8 and INV-9;
`tests/test_builder.py` INV-5 and INV-6; `tests/test_undo.py` INV-7;
`tests/test_starter.py` INV-10. Every test that builds a `Settings` with
`site_name` drops it, and one that relies on the name in a title writes an
identity instead.

Each test is seen failing against the code before this item, then
mutation-probed once the code lands.

## 8. Alternatives considered (and rejected)

- **Keys in `options/options.json`.** Rejected (§ 3 decision 3): undo
  would wipe the name on a state from before this change.
- **Keeping the name in Settings and adding only the description.**
  Rejected: the user decided the move (§ 3 decision 2).
- **Rewriting existing furniture to use the placeholders.** Rejected:
  Pressless never rewrites the user's HTML, and a name inside other text
  cannot be told from a coincidence.
- **Filling the placeholders in fixed pages too.** Rejected (§ 3 decision
  6): it breaks the byte-for-byte rule the page editor's round trip rests
  on.
- **A version 2 settings file.** Rejected: it changes nothing an older
  Pressless does, which refuses the file either way, and every reader of
  version 1 would need a migration.

## 9. Out of scope

- The icon and the sharing picture — 0.10.0, beside PRESS-0197.
- Drafts for the identity, with the header, footer, look and site-wide
  script — not yet queued.
- Filling the identity into a fixed page's own head.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_store.py::test_read_identity_reads_the_identity_file` |
| INV-2 | `tests/test_store.py::test_write_identity_refuses_a_bad_name` |
| INV-3 | `tests/test_settings.py::test_field_names_are_the_documented_set`, `::test_save_retires_only_what_it_is_told` |
| INV-4 | `tests/test_setup.py::test_the_name_is_carried_across_once` |
| INV-5 | `tests/test_builder.py::test_the_identity_names_every_page` |
| INV-6 | `tests/test_builder.py::test_content_carries_the_identity` |
| INV-7 | `tests/test_undo.py::test_undo_restores_the_identity_and_keeps_it_when_absent` |
| INV-8 | `tests/test_setup.py::test_the_site_step_saves_the_identity` |
| INV-9 | `tests/test_setup.py::test_settings_page_edits_the_identity` |
| INV-10 | `tests/test_starter.py::test_the_furniture_names_the_site_by_placeholder` |
| § 4.3 the launch sentence | **nothing** — read at the console |
| § 4.6 the forms' words | **nothing** — read on the page |

## 11. Cross-doc impact

Each edit below is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0001-settings.md` §§ 4.1–4.3 and INV-6 — `site_name`
  leaves `Settings`; § 4.4 — `save` takes `retire`.
- `docs/specs/PRESS-0005-store.md` § 4.1 — `move_to_bin` takes
  `identity/`.
- `docs/specs/PRESS-0008-builder.md` § 3 decision 2 and § 4.3 — the title
  reads the identity; the furniture table — two placeholders; § 4.7 —
  `content/` carries the identity file.
- `docs/specs/PRESS-0015-undo.md` § 4.4 — undo restores the identity file
  and keeps the Store's where the fetched state has none.
- `docs/specs/PRESS-0021-setup.md` — the Settings page's name comes from
  the Store, and the page gains the description; INV-5 — setup now also
  checks and writes the identity.
- `docs/specs/PRESS-0126-starter-site.md` § 3 decision 8 and § 4.3's
  header and footer rows — the header and footer name the site by
  placeholder, and the header carries the description.
- `docs/specs/PRESS-0199-counting-code.md` — the Privacy page's name comes
  from the Store.
- `docs/specs/PRESS-0212-setup-wizard.md` § 4 — the *site* step's fields
  and its save.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0213-site-identity-loop-log.md`.
