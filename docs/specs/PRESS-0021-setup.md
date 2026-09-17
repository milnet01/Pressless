# PRESS-0021 — Setup: the publishing key once, and the same page as Settings

**Status:** accepted (2026-09-17). Gated for two loops, the spec cap; every
verified finding fixed, none left in the tail. Amended 2026-09-17 for
PRESS-0124: setup no longer needs published writing, and the Daily Prompt
filter is an answer on the form.
**Kind:** implement.
**Source:** ROADMAP PRESS-0021 (`docs/design.md` § What may depend on what,
ADR-0003, discovery S5).

**Blocked by:** PRESS-0002, PRESS-0005, PRESS-0008, PRESS-0009, PRESS-0011.
**Blocker for:** PRESS-0013, PRESS-0122.

Layman: he pastes his publishing key in once and types three facts about his
site; Pressless checks them with GitHub, keeps the key safe, and works out
which files on his site it must never touch.

## 1. Goal

After this ships, the Face has one page at `/setup`. On a machine with no
settings file it is first-run setup. Afterwards the same page is Settings. It
checks his answers, asks GitHub what sits at the repository root, stores the
publishing key, derives the untouchable list, and saves Settings last.

## 2. Problem

1. **Nothing writes a settings file.** `settings.load` raises `NotSetUp`, and
   the Face's sentence for it says *"Go through setup first."* There is no
   setup.
2. **The untouchable list has an owner and no code.** `docs/design.md` says
   setup derives it: the Face asks the Publisher what sits at the root and
   removes what the Builder produces. `publisher.root_entries` returns the
   root, and `builder.ROOT_OUTPUT` names the Builder's root output. Nothing
   joins them. PRESS-0009 § 4.4 requires the removal to fold case with
   `str.casefold`.
3. **Setup cannot check an answer without a second copy of Settings' rules.**
   The shape rules live inside `settings.load` and are private. `settings.save`
   validates nothing it is handed (PRESS-0001 § 4.4). A setup that saves an
   answer `load` refuses leaves a file that fails on the next launch.
4. **Several Face sentences point at a Settings page that does not exist.**
   `credentials.NotStored`, `publisher.Refused`,
   `publisher.RepositoryMissing` and `publisher.SiteFolderMissing` say
   *"in Settings"*.
5. **The Face's `SettingsError` sentence says *"Go through setup again."*.**
   `docs/standards/versioning-overrides.md` § Setup state forbids sending him
   to setup over an unreadable file, because setup would overwrite the one file
   that could be repaired.
6. **`publisher.root_entries` takes a whole `Settings`**, and at first run
   there is none. Setup has to build one in memory without saving it.
   PRESS-0001 § 3 decision 4 forbids saving an empty list as a placeholder.

## 3. Scope decisions (agreed with the user)

1. **The Google step is not this item's.** Decided by the user 2026-09-17 and
   moved to PRESS-0122. Setup writes `credentials.google_account` and
   `analytics_property_id` as absent, which PRESS-0001 § 4.2 already allows.
2. **He types the repository, the site's name and its address.** Decided by
   the user 2026-09-17. One form, checked before anything is saved.
3. **The same page is Settings afterwards.** Decided by the user 2026-09-17.
   His answers are filled in, and an empty key box keeps the saved key. Saving
   derives the untouchable list again. That is the button
   `docs/design.md` offers after setup.
4. **The site folder is chosen for him.** Decided by the user 2026-09-17: a
   folder named `site` inside Pressless's own folder. He is never asked.
5. **(decided here) Setup lives in the Face, as `src/pressless/setup.py`.**
   Only the Face knows what order things happen in (design rule 1), and only
   the Face reaches Credentials (rule 10). The design has no Setup part.
6. **(decided here) Settings gains `check`, and `load` calls it.** That keeps
   one copy of the shape rules (§ 2 item 3).
7. **(decided here) A refused answer is not a failure.** Nothing happened, so
   it is shown beside its field and not logged. Everything that happens after
   the answers are accepted is shown through `Face.fail`, except a repository
   GitHub cannot find (§ 4.6 step 2).
8. **(decided here) This item wires no double-click.** PRESS-0013 replaces
   `pressless.__main__` and calls `setup.register` (PRESS-0011 § 3
   decision 6).
9. **Setup is offered on an empty install.** Decided by the user 2026-09-17
   (PRESS-0124). Setup never reads the Store. The guard against replacing a
   live site with an empty one belongs to publishing (`docs/design.md`
   rule 9), and PRESS-0013 builds it.
10. **The Daily Prompt filter is an optional answer.** Decided by the user
    2026-09-17 (PRESS-0124). First run offers an empty box, and an empty
    filter hides nothing.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/setup.py

SITE_FOLDER = "site"                  # inside Pressless's own folder
GITHUB_ACCOUNT = "github"             # the account the publishing key is filed under
KEY = "your publishing key"           # the {secret} noun (PRESS-0011 § 4.2)

def untouchable(root: Iterable[str]) -> tuple[str, ...]: ...
def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None: ...
```

`folder` is Pressless's own folder, the one `face.serve` was handed.
`register` adds `GET /setup` and `POST /setup`. `transport` reaches
`publisher.root_entries` and exists for the tests.

```python
# src/pressless/settings.py — added

class SettingsError(Exception):
    key: str | None      # the settings key a shape refusal names; None otherwise

def check(settings: Settings) -> None: ...   # raises SettingsError
```

`check` holds every shape rule `load` applies to a parsed value. `load`
builds the `Settings` and then calls `check`. Each refusal sets `key` to the
top-level name it refuses: `site_folder`, `repository`, `site_name`,
`site_address`, `untouchable`, `credentials` or `analytics_property_id`.
Refusals of the file itself — its reading, its JSON, its version, a missing
or mistyped field — keep `key` as `None`.

### 4.2 Which page he sees

Every request to `/setup` first runs `settings.load(folder)` inside
`face.capture()`:

| Outcome | What `/setup` does |
|---|---|
| `NotSetUp` | **first run**: an empty form |
| `SettingsError` whose `key` is `site_folder` | **first run**: an empty form |
| any other `SettingsError` | shows it through `Face.fail`; no form, and a POST writes nothing |
| a `Settings` | **Settings**: the form filled from it |

Setup never reads the Store (§ 3 decision 9). A folder holding no Store is
first run like any other.

**A `site_folder` refusal is a file carried from another machine.**
PRESS-0001 § 4.2 says so, and says the other machine runs setup. First run
writes § 4.5's first-run values over that file, the Google fields included:
`load` refused it, so nothing in it is read.

### 4.3 The form

Five fields, posted under these names: `repository`, `site_name`,
`site_address`, `daily_prompt_filter` and `key`. The filter is optional on
both paths. The key is
an `<input type="password" autocomplete="off">` with no `value` attribute,
ever. Every value placed in the page is escaped with
`html.escape(value, quote=True)`.

In Settings the page says an empty key box keeps the saved key, and the
submit button says it checks the repository again.

The words on the page, and how to make a key, are the implementer's.

### 4.4 Checking the answers

The body is read with `urllib.parse.parse_qs`. Each answer is stripped of
surrounding whitespace.

**The key.** On first run an empty key is refused. A key that is not ASCII,
not printable, or holds whitespace is refused on either path. Executed
against `publisher.root_entries`: a key holding a line break is refused by
`http.client` before any request, and the Publisher raises `Unreachable`, so
he is told to check his internet connection. A key holding a space is sent,
and GitHub's refusal comes back as `Refused`.

**The rest.** Setup builds the candidate `Settings` (§ 4.5) with
`untouchable=()` and calls `settings.check`. A `SettingsError` whose `key` is
`repository`, `site_name` or `site_address` is a refused answer. Any other
`SettingsError` is shown through `Face.fail`.

**A refused answer** re-renders the form with the other answers filled in, a
hint beside the refused field, and an empty key box. `check` stops at its
first refusal, so a second is found on the next submission. Nothing is written
and nothing is logged. No request is made, except for § 4.6 step 2's refusal.

### 4.5 The candidate `Settings`

| Field | First run | Settings |
|---|---|---|
| `site_folder` | `folder / SITE_FOLDER` | `folder / SITE_FOLDER` |
| `repository`, `site_name`, `site_address` | his answers | his answers |
| `daily_prompt_filter` | the answer, `""` when the box is empty | the answer, `""` when the box is empty |
| `untouchable` | `()` until § 4.6 step 2 | `()` until § 4.6 step 2 |
| `credentials.store` | `"keyring"` until § 4.6 step 3 replaces it | the saved value |
| `credentials.github_account` | `GITHUB_ACCOUNT` | the saved value |
| `credentials.google_account` | `None` | the saved value |
| `analytics_property_id` | `None` | the saved value |

**An empty filter hides nothing.** The Builder excludes an entry when
`fnmatch.fnmatchcase(tag, pattern)` holds for one of its tags. With `""` that
holds only for an empty tag, and `store`'s `_parse_list` drops empty tags on
reading. In Settings the box is filled from the saved value, so an emptied box
is a cleared filter. Unlike the key box, it does not keep the saved value.
`check` has no rule for the filter, so it is never a refused answer.

**First run's store is a placeholder** so the candidate passes `check`. Step 3
replaces it with `Choice.store` before anything is saved.

**`site_folder` is rewritten in Settings too.** It is an absolute path, and
Pressless's own folder moves with the program, so a saved one can name a
folder that is no longer there.

### 4.6 The sequence, once the answers are accepted

Each step runs only when the one before it succeeded. A failure is shown
through `Face.fail` and ends the request.

1. **The key in hand.** The key he typed. On Settings with an empty key box,
   `credentials.read(saved store, folder, saved github_account)`.
2. **Ask GitHub.** `publisher.root_entries(candidate, key, transport)`. The
   untouchable list is `untouchable(entries)`. **A `publisher.RemoteStateMissing`
   here is a refused `repository` answer**, not a failure: `root_entries`
   first reads the repository's `commits/HEAD`, and `_names_the_repository`
   sends a 404 on that address to `RemoteStateMissing`, never to
   `RepositoryMissing`. The hint says GitHub has no repository by that name
   that this key can reach.
3. **Choose the store — first run only.** `credentials.choose()`. Settings
   keeps the saved store and never asks again (PRESS-0002 § 4.2).
4. **Store the key — only when he typed one.**
   `credentials.write(store, folder, github_account, key)`.
5. **Save.** `settings.save(folder, final)`, inside `face.capture()`, where
   `final` is the candidate with the list and the store filled in.

Then the page says setup is done. It names the files it will leave alone. On
first run it names the store that answered, `Choice.name`, and where that is
`"file"` it says plainly that no keyring was found (ADR-0003).

**Why this order.** A wrong key or a missing repository is found at step 2,
before anything is written. The settings file is what makes a machine set up,
so it is written last. An interruption before step 5 leaves first run where
it was, and step 4 replaces a key written by an earlier attempt.

**A credential failure passes `secret=KEY`** to `Face.fail`. That is steps 1,
3 and 4. `credentials.NoStore` ends setup, and the page says above the failure that
setup cannot finish on this computer (ADR-0003).

### 4.7 Deriving the list

```python
def untouchable(root):
    produced = {name.casefold() for name in builder.ROOT_OUTPUT}
    return tuple(sorted(e for e in root if e.rstrip("/").casefold() not in produced))
```

`builder.ROOT_OUTPUT` is read at call time, never copied. The fold is
`str.casefold`, as PRESS-0009 § 4.4 pins. `content` is Builder output and is
removed. `assets` is not, and is kept (PRESS-0008 § 3 decision 3).

### 4.8 Changes to the Face

- `settings.SettingsError`'s next step stops sending him to setup. It says
  Pressless changed nothing in its settings, and to send the details to
  whoever helps him. A refusal whose `key` is `site_folder` never reaches
  that sentence: `/setup` treats it as first run (§ 4.2), and PRESS-0013
  opens `/setup` when a launch meets one.
- `publisher.SiteFolderMissing` and `builder.SiteFolderUnusable` stop naming
  a site-folder setting, which this page does not have.
- **Every sentence a `root_entries` failure can reach names a next step that
  also holds on this page.** Today several end *"then click Publish again"*,
  and setup has no Publish button. They say *"try again"* instead.

### 4.9 What setup never does

- It never writes the key into a page, the log, the console or Settings.
- It never saves a settings file with a list it did not derive.
- It never writes over a settings file `load` refused, unless the refusal's
  `key` is `site_folder` (§ 4.2).
- It never calls `credentials.choose` once a settings file loads.
- It never runs Import (`docs/design.md` rule 9).
- It never reads the Store.
- It never touches `google_account` or `analytics_property_id` in a settings
  file that loads.

## 5. Invariants

The tests below are in `tests/test_setup.py` unless named otherwise. Each
runs the page through `face.serve(tmp_path, open_browser=False)` with a fake
Publisher transport, as `tests/test_publisher.py` does, and recording doubles
for `credentials.choose`, `read` and `write`. The doubles keep every test off
the machine's real store, which matters on Windows CI: there
`credentials.write` refuses the file store.

- **INV-1** — Nothing is written before GitHub has answered. A refused answer,
  or any failure from `root_entries`, leaves no settings file, no stored key,
  and no call to `credentials.choose`.
  *Test:* `test_nothing_is_written_before_github_answers`. It submits a
  refused site address, then a key GitHub answers 401, then a repository
  whose `commits/HEAD` GitHub answers 404. The last must re-render the form
  with the repository hint.
  *Breaks when:* `credentials.write` or `choose` moves ahead of
  `root_entries`, or the address check is dropped and the form reaches
  GitHub.

- **INV-2** — The settings file is saved last. A failure at § 4.6 step 3 or 4
  leaves no settings file on first run, and the previous file byte-identical
  in Settings.
  *Test:* `test_the_settings_file_is_written_last`. First run, with `choose`
  raising `CredentialError`, then with `write` raising `NoStore`. Then
  Settings, with a new key typed and `write` raising `NoStore`, over a saved
  file whose `untouchable` differs from the list the run derives.
  *Breaks when:* `save` runs before the key is stored.

- **INV-3** — The derived list is the root minus `builder.ROOT_OUTPUT`,
  compared with `str.casefold` on both sides.
  *Test:* `test_the_list_is_the_root_minus_what_the_builder_makes`. It feeds
  `untouchable` a root holding `Index.html`, `content`, `CNAME`, `assets` and
  `.nojekyll`, and expects the last three. It then patches
  `builder.ROOT_OUTPUT` to hold `straße` and `extra`, and expects `STRASSE`
  and `extra` removed from the root.
  *Breaks when:* the comparison is exact, which keeps `Index.html`; uses
  `str.lower`, which keeps `STRASSE`; or reads a copy of `ROOT_OUTPUT`, which
  keeps `extra`.

- **INV-4** — A settings file `load` refuses is never written over, unless
  the refusal names `site_folder`. With a refused file in place, `GET /setup`
  offers no form and `POST /setup` changes nothing. With one refused for its
  `site_folder`, first run is offered.
  *Test:* `test_an_unreadable_settings_file_is_left_alone`, with a file whose
  `repository` is `"ownername"`, then a file whose `site_folder` is relative.
  `save` accepts the first file, so only setup can protect it. The POST over
  it must leave its bytes unchanged and record no request, no `choose` and no
  `write`.
  *Breaks when:* every `SettingsError` from `load` is treated as `NotSetUp`,
  which writes over the first file; or none is, which leaves the second
  machine with no way to set up.

- **INV-5** — Setup is offered on an empty install. With no Store in `folder`,
  `GET` offers the first-run form and `POST` saves.
  *Test:* `test_setup_works_on_an_empty_install`. It replaces every public
  function of `pressless.store` with one that raises, runs first run in a
  folder holding nothing, and asserts the saved file loads.
  *Breaks when:* setup calls into the Store at all, which includes a setup
  that still requires published writing.

- **INV-6** — The key never reaches a page, the log or the console.
  *Test:* `test_the_key_is_never_shown`. It submits a sentinel key through a
  success, a refused site name and a 401. After each, the response body, the
  log file and `capfd` must not hold the sentinel, and the page must hold no
  `value=` on the key field.
  *Breaks when:* the re-rendered form fills the key box, or the done page
  echoes it.

- **INV-7** — `credentials.choose` is called on first run only. In Settings
  the key is read from and written to the saved store.
  *Test:* `test_settings_never_asks_for_a_store_again`, with a saved store of
  `"file"` and a `choose` double answering `"keyring"`. The `write` double
  must record `"file"`.
  *Breaks when:* Settings calls `choose`, which files the key in the keyring
  while Settings still names the file.

- **INV-8** — In Settings an empty key box keeps the saved key.
  `credentials.write` is not called, and `root_entries` receives the saved
  key. On first run an empty key is a refused answer.
  *Test:* `test_an_empty_key_box_keeps_the_saved_key`.
  *Breaks when:* the empty string is stored as the key, or first run accepts
  one.

- **INV-9** — Settings carries forward what the page does not ask.
  `analytics_property_id`, `credentials.store`,
  `credentials.github_account` and `credentials.google_account` are saved
  unchanged.
  *Test:* `test_settings_keeps_what_it_does_not_ask`, over a saved file with
  a property id and a Google account.
  *Breaks when:* Settings builds the candidate from first-run defaults, which
  erases PRESS-0122's fields.

- **INV-10** — First run saves the values § 4.5 names, and the file loads.
  *Test:* `test_first_run_saves_a_file_that_loads`. It runs first run twice,
  each in a fresh folder, with the `choose` double answering `"keyring"` and
  then `"file"`.
  Each time it asserts `settings.load(folder)` equals the expected
  `Settings`, with `site_folder` equal to `folder / "site"` written out
  rather than read from `SITE_FOLDER`.
  *Breaks when:* a value departs from § 4.5, `save` writes what `load`
  refuses, or the placeholder store is saved instead of `Choice.store` —
  which only the second run can see.

- **INV-11** — `settings.check` and `settings.load` refuse the same shapes,
  and a shape refusal names its key.
  *Test:* `tests/test_settings.py::test_check_refuses_what_load_refuses`. For
  each shape refusal it asserts both that `check` raises with the expected
  `key` and that `load` raises over a file holding that value.
  *Breaks when:* a rule is removed from `check` but kept inline in `load`, or
  `key` names the wrong field.

- **INV-12** — A malformed key is a refused answer, not a network failure.
  *Test:* `test_a_malformed_key_is_refused_before_any_request`, with a key
  holding a newline and one holding a space. The fake transport records no
  call.
  *Breaks when:* the key check is dropped. The newline then reaches
  `http.client`, which refuses the header, and the Publisher raises
  `Unreachable`; the space reaches the transport as a request.

- **INV-13** — A credential failure names the publishing key.
  *Test:* `test_a_credential_failure_names_the_key`. It makes `choose` raise
  `NoStore`, and `read` raise `NotStored`, and expects `KEY` in the page.
  *Breaks when:* the failure escapes to the page catch, which calls
  `Face.fail` without `secret`, so the page names the Face's fallback noun
  instead.

- **INV-15** — The Daily Prompt filter is the answer typed, on both paths. An
  empty box saves `""`.
  *Test:* `test_the_filter_is_the_answer`. First run with an empty filter box
  saves `""`. Settings over a saved `"dailyprompt-*"` shows that value in the
  box. Posting `"x-*"` saves `"x-*"`, and posting an empty box saves `""`.
  *Breaks when:* first run writes a default filter, or Settings carries the
  saved filter forward in place of the answer.

- **INV-14** — The server boundary is the Face's, unchanged. `/setup` is
  reached only through `Face.add_page`, so a request without the cookie, or a
  POST from another origin, is refused before setup runs.
  *Test:* `test_setup_sits_behind_the_faces_boundary`, POSTing a key with no
  cookie and then with a foreign `Origin`; both answer 403 and nothing is
  written. The same POST with the cookie and the Face's own `Origin` then
  reaches setup and saves.
  *Breaks when:* setup serves its own handler or never registers on the Face.
  The third request then gets 404 and nothing is saved.

## 6. Failure modes

| What breaks | What he sees | What is left on disk |
|---|---|---|
| A fresh install, with no Store | the first-run form | nothing, until the form is saved |
| The settings file is unreadable | `SettingsError`, and no form | the file, untouched |
| The settings file came from another machine | the first-run form | the file, until he saves |
| GitHub is unreachable, or refuses the key | the Publisher's sentence | nothing new |
| GitHub has no such repository this key can reach | the form, with a hint on the repository | nothing new |
| Any other failure from `root_entries` | its sentence | nothing new |
| No keyring, on Windows or a mount without modes | `NoStore`, naming the key | nothing new |
| The keyring is locked or broken | `CredentialError`, naming the key | nothing new |
| The saved key is missing in Settings | `NotStored`, naming the key | the settings file, unchanged |
| The settings file cannot be written | `SettingsError` | the key stored; first run stays first run |
| Two submissions at once | each runs the sequence | one wins; `save` is atomic and `write` replaces |

## 7. Tests

`tests/test_setup.py` — new, in CI. It carries INV-1, INV-2, INV-3, INV-4,
INV-5, INV-6, INV-7, INV-8, INV-9, INV-10, INV-12, INV-13, INV-14 and INV-15.

`tests/test_settings.py` gains INV-11's test.

Each test is seen failing against a stub `setup.py` whose functions raise
`NotImplementedError`, then mutation-probed once the code lands.

## 8. Alternatives considered (and rejected)

- **Setup keeps its own copy of the shape rules.** Rejected: two copies are
  two rules, and the one that drifts saves a file `load` refuses.
- **Validate by saving and loading back.** Rejected: the file is written
  before the check, which is what INV-1 forbids.
- **Save Settings first, then store the key.** Rejected: an interruption
  leaves a machine that reads as set up with no key, and `NotStored` sends him
  to a page that cannot tell a lost key from one never given.
- **A separate "check the repository again" action.** Rejected: saving
  already asks GitHub, and a second route is a second sequence to keep in step.
- **Public `publisher._is_protected` for the removal.** Rejected: rule 7 keeps
  a part's insides private, and PRESS-0009 § 4.4 pins the fold by name, so both
  ends can conform without sharing code.
- **He picks the site folder.** Rejected by the user; § 3 decision 4.

## 9. Out of scope

- The Google step, the property id and declining the dashboard — PRESS-0122.
- Opening setup on a double-click — PRESS-0013.
- Running Import — never; `docs/design.md` rule 9.
- A branch other than the repository's default — PRESS-0009 § 4.2 rules out a
  branch field.
- Removing a stored key — deferred; not yet queued. `credentials.write`
  replaces, and nothing yet needs a removal.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_setup.py::test_nothing_is_written_before_github_answers` |
| INV-2 | `tests/test_setup.py::test_the_settings_file_is_written_last` |
| INV-3 | `tests/test_setup.py::test_the_list_is_the_root_minus_what_the_builder_makes` |
| INV-4 | `tests/test_setup.py::test_an_unreadable_settings_file_is_left_alone` |
| INV-5 | `tests/test_setup.py::test_setup_works_on_an_empty_install` |
| INV-6 | `tests/test_setup.py::test_the_key_is_never_shown` |
| INV-7 | `tests/test_setup.py::test_settings_never_asks_for_a_store_again` |
| INV-8 | `tests/test_setup.py::test_an_empty_key_box_keeps_the_saved_key` |
| INV-9 | `tests/test_setup.py::test_settings_keeps_what_it_does_not_ask` |
| INV-10 | `tests/test_setup.py::test_first_run_saves_a_file_that_loads` |
| INV-11 | `tests/test_settings.py::test_check_refuses_what_load_refuses` |
| INV-12 | `tests/test_setup.py::test_a_malformed_key_is_refused_before_any_request` |
| INV-13 | `tests/test_setup.py::test_a_credential_failure_names_the_key` |
| INV-14 | `tests/test_setup.py::test_setup_sits_behind_the_faces_boundary` |
| INV-15 | `tests/test_setup.py::test_the_filter_is_the_answer` |
| The page's words and how he makes a key | **nothing** — the implementer's words; read on the page |
| That a reachable sentence's next step holds on this page (§ 4.8) | **nothing** — words; read against `root_entries`' failure types |
| The real keyring prompt on Windows, in the desktop session | **nothing** in CI — the Windows box, by hand (`CLAUDE.md`) |

## 11. Cross-doc impact

- `docs/specs/PRESS-0001-settings.md` § 4.1 — `check` and `SettingsError.key`
  are added; the section points here.
- `docs/specs/PRESS-0011-face.md` § 4.5 — `/setup` is one of the pages added.
- `docs/design.md` rule 9 — amended with this spec (PRESS-0124): setup is
  offered on an empty install, and publishing keeps the guard.
- PRESS-0013 — builds that publishing guard, and opens `/setup` when a
  launch meets a `site_folder` refusal (§ 4.8).
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0021-setup-loop-log.md`.
