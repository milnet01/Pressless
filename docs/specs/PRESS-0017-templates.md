# PRESS-0017 — Start something new from a template

**Status:** accepted (2026-09-27). Gated for two loops, the spec cap; every verified finding fixed, none left in the tail.
**Kind:** implement.
**Source:** ROADMAP PRESS-0017 (`docs/design.md` § What may depend on
what, under *A template is a Store file*; discovery § Starting something
new).

**Blocked by:** PRESS-0006, PRESS-0012.  **Pairs with:** PRESS-0016.

**Layman:** When he starts a new entry he can pick a shape — a poem, a
lyric, an entry around a photograph, a plain journal entry — and the box
opens with that shape already in it; he can change the shapes and add his
own.

## 1. Goal

Starting a new entry offers a list of templates. Picking one opens a new
draft already holding that template's words, categories and tags. He can
open any template in a box of its own, change it, bin it, or add a new
one. A fresh install starts with four.

## 2. Problem

1. `POST /new` (`src/pressless/editor.py::_new`, PRESS-0012 § 4.6) always
   writes an empty body. Every new piece starts from nothing, so a shape
   he uses often is retyped each time.
2. The Store already holds templates and nothing reads them for him.
   PRESS-0006 § 4.1 gives `store.TEMPLATES_FOLDER`,
   `store.template_path_for`, `store.list_templates` and
   `store.write_template`, and names this item as the picker that binds to
   `list_templates`. The Builder copies the folder into `content/`
   unrendered (`builder.py`, the `list_templates` loop in the content
   copy), and undo restores it (`undo.py`, `_State.templates`).
3. No templates exist anywhere. Import writes none: its `TEMPLATES`
   argument is the site's header and footer (PRESS-0007 § 4.9), not
   writing shapes. So neither the first writer nor a stranger has a
   template to pick.

## 3. Scope decisions (agreed with the user)

1. **A template is an entry file in the templates folder, and never
   becomes a page.** `docs/design.md`, and PRESS-0006 § 3 decision 3.
   Nothing in the Store, the Builder or Marks changes for this item —
   the design's own test that this is the right shape.
2. **Four starters ship with Pressless: a poem, a lyric with verses, an
   entry around one photograph, a plain journal entry.** The list is the
   design's.
3. **(decided here) The starters are written into the templates folder
   only when that folder does not exist.** A folder that exists, empty
   or not, is his, so a starter he binned stays binned and one he changed
   stays changed. This is also what gives the first writer his four: his
   folder came from Import, which writes no templates.
4. **(decided here) A template's title is its name in the list, and is
   never copied into the draft.** The draft's title is what he typed in
   the New form, exactly as today.
5. **(decided here) A template opens in a page of its own, with the same
   writing box and cheat sheet, saved by a button.** There is no preview
   and no save-while-typing: the preview shows a page, and a template is
   never one. The entry editor's page and script are untouched.
6. **(decided here) The starters name nobody and assume nothing about the
   writer's life.** They ship to every install.

## 4. Design

### 4.1 Where it lives

A new Face module, `src/pressless/templates.py`, registered from
`__main__._serve_held` beside the editor. It imports `editor` for
`address_for`, `LOCK` and the digest the entry editor already uses for
its `base` check; `editor` does not import it back.

```python
def starters() -> tuple[store.Entry, ...]: ...  # the four, named poem, lyric,
                                    # photograph, journal; their words are
                                    # looked up when called (PRESS-0242)
def seed(folder: Path) -> bool: ... # §4.2; False where the folder existed
def register(face: Face, folder: Path) -> None: ...
```

Routes, all behind the Face's session and Origin checks like every other
page:

| Route | What it does |
|---|---|
| `GET /template?name=N` | the template's page (§4.4) |
| `POST /template/save` | `name`, `base`, `title`, `categories`, `tags`, `body` (§4.4) |
| `POST /template/new` | `name` → a new, empty template, then its page (§4.5) |
| `POST /template/bin` | `name`, `base` → the bin, then the list (§4.5) |

### 4.2 The starters

`register` calls `seed(folder)` once, at start. `seed` writes the four
`starters()` with `store.write_template` when
`folder / store.TEMPLATES_FOLDER` does not exist, and does nothing
otherwise, returning `False`. A `StoreError` from a write propagates out
of `seed`; `register` catches it and `face.note` records `templates:
starters not written`. **A failure is final**: the
first write creates the folder, so the starters written before it stay
and no later start writes the rest (§3 decision 3). He can still add
his own.

Each starter is an `Entry` with an empty `extra`, empty categories and
tags, and a body written in marks: lines of a poem; verses separated by
a blank line with a `{muted}` chorus label; a `{photo: … | …}` line with
a line of text below it; a plain paragraph. **The photograph starter is
usable once PRESS-0016 can put an original in the Store**; both are
0.6.0 items.

### 4.3 Picking one

The list's New form (`editor._list`, PRESS-0012 § 4.5) gains a `<select
name="template">` after the title field. Its first option is a blank
entry, value `""`. Then one option per `store.list_templates(folder)`
name, in that order, labelled with the template's title, or its name
where the title is empty. A template that does not read is left out of
the options.

`POST /new` reads `template` as well as `title`. Empty or absent: exactly
PRESS-0012 § 4.6's draft. Otherwise the draft is PRESS-0012 § 4.6's
draft with the named template's `body`, `categories` and `tags`. Nothing
else is taken from it, and the template file is not written.

### 4.4 A template's page

`GET /template?name=N` reads `store.template_path_for(folder, N)` and
shows a form: the name as text, Title, Categories, Tags, the body in a
`textarea` with the entry editor's body class, a Save button, a Bin this
template button, and `cheatsheet.panel()`. The form carries `base`, the
file's digest as read.

`POST /template/save` refuses with `editor.ChangedElsewhere` where the
file's digest is not `base`. Otherwise it writes an `Entry` with slug
`N`, the posted title and body, the date the file already holds, and
its `extra`, through `store.write_template`, and answers with the page
again. Categories and tags are read as `editor.save` reads them, through
`editor._names_of`, notices included, because a draft picked from the
template carries them to the site unchanged. Line endings in the body
are normalised as `editor.save` does.

### 4.5 Adding and binning

`POST /template/new` takes `name`, turns it into a name with
`editor.address_for`, and adds `-2`, `-3` … until no file exists at
`store.template_path_for(folder, name)`. A file check rather than
`list_templates`, which leaves out a name it cannot use: on Windows a
hand-named `Poem.txt` answers for `poem`, so it is not overwritten.
Only the templates folder is asked: PRESS-0006 § 3 decision 11 lets a
template share an entry's name. It writes an empty template, titled with
the name as typed, and answers 303 to its page.

`POST /template/bin` checks `base` as save does, then
`store.move_to_bin(folder, store.template_path_for(folder, name))`, and
answers 303 to the list.

The list page shows the templates under **Your templates**, each linking
to its page, with the New template form below them. It reaches the list
through `face.add_to_list(..., above=False)`, so `editor` does not import
this module.

### 4.6 What the site gets

Nothing new. The Builder already copies every template into `content/`
unrendered on each press (§2 item 2), so a starter, and anything he
writes into a template, reaches the site's repository as a text file and
never as a page. That was PRESS-0006's decision and this item does not
revisit it.

## 5. Invariants

- **INV-1** — Picking a template gives a new draft whose body, categories
  and tags are the template's, whose title is the one typed, and leaves
  the template file byte-for-byte unchanged.
  *Test:* `tests/test_templates.py::test_picking_a_template_copies_its_words`.
  *Breaks when:* the draft is written from the template's title, or a
  save path writes back to the template.
- **INV-2** — A New form with no template, or an empty one, writes
  exactly PRESS-0012 § 4.6's draft.
  *Test:* `tests/test_templates.py::test_no_template_is_a_blank_entry`.
  *Breaks when:* the blank option is taken as a template name, or the
  first template in the list becomes the default.
- **INV-3** — `seed` writes the four starters where the templates folder
  does not exist, and writes nothing where it exists, empty or not.
  *Test:* `tests/test_templates.py::test_starters_are_written_once`, over
  an absent folder, an empty one, and one holding a changed `poem`.
  *Breaks when:* seeding is keyed on the folder being empty, which
  brings back every starter he binned, or on each starter's file being
  absent, which brings back one.
- **INV-4** — Every starter survives `store.write_template` then
  `store.read` unchanged, and renders through `marks.render` with no mark
  left as typed text.
  *Test:* `tests/test_templates.py::test_every_starter_is_well_formed`.
  *Breaks when:* a starter uses a mark Marks does not have, or carries a
  value the entry format cannot hold.
- **INV-5** — Saving or binning a template touches only
  `templates/<name>.txt` and the bin: both `store.list_slugs` results are
  unchanged, and a stale `base` writes nothing.
  *Test:* `tests/test_templates.py::test_a_template_save_touches_only_its_file`
  and `::test_a_stale_template_save_writes_nothing`, and for binning
  `::test_a_template_bin_touches_only_its_file` and
  `::test_a_stale_template_bin_moves_nothing`.
  *Breaks when:* the save goes through `store.write`, or either route skips
  the digest check.
- **INV-6** — A new template's name is `address_for` of what was typed,
  with `-2` onwards only where a file already sits at its template path;
  an entry of that name does not count.
  *Test:* `tests/test_templates.py::test_a_new_template_takes_a_free_name`.
  *Breaks when:* the check uses `store.exists`, which asks the entry
  folders.

## 6. Failure modes

| When | What happens |
|---|---|
| The starters cannot be written | the log says so (§4.2); the picker offers whatever was written before the failure, and a blank entry; no later start retries |
| A template file does not read | it is left out of the picker; its page shows the Store's sentence for the failure, as the entry editor does |
| He posts a template name that no longer exists | `store.EntryNotFound`, shown with its existing sentence |
| The template changed in another window | `editor.ChangedElsewhere`, whose sentence already tells him what to do |
| A template name the Store refuses | the Store's own refusal, shown with its sentence; nothing is written |

## 7. Tests

`tests/test_templates.py` locks INV-1, INV-2, INV-3, INV-4, INV-5 and INV-6
against a served Face, in
the pattern of `tests/test_editor.py`: the server starts inside each test,
and route names are written out rather than imported. Each is watched
failing against the unchanged `_new` or a stub before it is trusted.

`scripts/by-hand-browser-checks.py` gains a row: pick the poem, and the
box opens holding it.

## 8. Alternatives considered (and rejected)

- **Built-in templates always offered, with his edits kept as copies.**
  Rejected: a starter he did not want could never leave the list, and
  two templates of one name would need a rule for which wins.
- **Seeding when the templates folder is empty.** Rejected: binning all
  four would bring them all back at the next start.
- **Editing a template in the entry editor, with its preview and
  save-while-typing.** Rejected: that page, its script and its preview
  folder are keyed on entry slugs, and a template may share an entry's
  name (PRESS-0006 § 3 decision 11), so a preview could overwrite the
  entry's. The gain is a preview of something never published.
- **Copying the template's title into the draft.** Rejected: every poem
  would start titled "A poem".

## 9. Out of scope

- Photographs themselves — PRESS-0016.
- A template for a fixed page — deferred; not yet queued.
- Turning an existing entry into a template — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_templates.py::test_picking_a_template_copies_its_words` |
| INV-2 | `tests/test_templates.py::test_no_template_is_a_blank_entry` |
| INV-3 | `tests/test_templates.py::test_starters_are_written_once` |
| INV-4 | `tests/test_templates.py::test_every_starter_is_well_formed` |
| INV-5 | `tests/test_templates.py::test_a_template_save_touches_only_its_file`, `::test_a_stale_template_save_writes_nothing`, `::test_a_template_bin_touches_only_its_file`, `::test_a_stale_template_bin_moves_nothing` |
| INV-6 | `tests/test_templates.py::test_a_new_template_takes_a_free_name` |
| Scope decision 6, the starters name nobody | **Partial:** the gate's leak sweep reads every committed file; nothing judges whether a starter assumes too much about a stranger |
| §4.3's option labels | **nothing** — no test reads the rendered `<select>`; the browser row sees one pick |

## 11. Cross-doc impact

- **CHANGELOG** — an Added entry.
- **PRESS-0012** — § 4.6 gains a pointer: the draft may be filled from a
  template (PRESS-0017 § 4.3).
- **`docs/design.md`** — no change; it already carries the shape.
- **`scripts/by-hand-browser-checks.py`** — the §7 row.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0017-templates-loop-log.md`.
