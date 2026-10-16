<!-- ants-spec-format: 1 -->
# PRESS-0223 — Pressless holds several sites

**Status:** accepted (2026-10-16).
**Kind:** feature.
**Source:** ROADMAP PRESS-0223 (user-request-2026-10-03).

**Blocker for:** PRESS-0224, PRESS-0225, PRESS-0221.
**Pairs with:** PRESS-0224, whose file opens as one of these sites.

Layman: one copy of Pressless keeps more than one website, and a Sites
screen lists them, starts a new one, and switches between them.

## 1. Goal

After this ships, `Pressless-data` holds a `sites/` folder with one
folder per site, and a file naming the site that is open. Everything that
belongs to a site sits in that site's folder; what belongs to the machine
stays at the top. A Sites screen lists the sites, starts a new one and
opens another, and an existing install's one site is moved into
`sites/site-1` on the first start, with nothing lost.

## 2. Problem

1. **The folder holds one site.** `__main__.main` hands the one folder
   `paths.ensure(paths.own_folder())` returns to every part, and
   `store.py`'s functions, `settings.load` and `credentials.read` all
   treat that folder as the site's. A second site needs a second copy of
   Pressless.
2. **Site files and machine files are mixed at one level.** The Store's
   folders (`store.PUBLISHED_FOLDER` and the rest) and
   `settings.FILE_NAME` sit beside `log.FILE_NAME`,
   `updater.FILE_NAME`, `themes.FILE_NAME` and `__main__._LOCK_NAME`.
   Nothing names which side each is on.
3. **The keys are filed under fixed names.** `setup.GITHUB_ACCOUNT` is
   `"github"` and `google_setup.GOOGLE_ACCOUNT` is `"google"`, so a
   second site's key would overwrite the first's.

## 3. Scope decisions (agreed with the user)

1. **Several sites, and a whole site to one file** — user, 2026-10-03.
2. **Sites live inside `Pressless-data`**, not wherever the user puts
   them. Recommended by Claude, 2026-10-16: `docs/design.md` § Where
   everything sits on disk chooses the drive by where the program is,
   and a site placed elsewhere would break that rule.
3. **Site folders are named `site-1`, `site-2` and so on**, never from
   the site's name. Recommended by Claude, 2026-10-16: a name can change,
   repeat or hold characters no file system allows, and the screen shows
   the site's own name anyway.
4. **Switching is a restart.** Recommended by Claude, 2026-10-16:
   PRESS-0203's restart already builds a fresh Face and registers every
   part again, so no part can keep acting on the old site. The cost is a
   new browser tab, as Restart costs today.
5. **Listing the sites in a GitHub account** (the user, 2026-10-05) is
   not in this item; § 9.

## 4. Design

### 4.1 The layout

```
Pressless-data/
  sites.json          {"version": 1, "open": "site-1"}
  sites/
    site-1/           one site: every name in SITE_NAMES
    site-2/
  pressless.log  pressless.log.1  updates.json  update.log
  pressless.lock  theme.json  usage.json  usage-sent.json
```

A new module, `src/pressless/sites.py`, owns the layout. It imports no
part of Pressless, only `safe_write` (PRESS-0141), so every part may use
it.

```python
SITES_FOLDER = "sites"
OPEN_FILE = "sites.json"
SITE_NAMES = frozenset({...})     # § 4.2: what belongs to a site
MACHINE_NAMES = frozenset({...})  # § 4.2: what belongs to the machine

def open_site(own: Path) -> Path: ...      # the open site's folder, created
def all_sites(own: Path) -> list[Path]: ... # site-1, site-2, ... in number order
def new_site(own: Path) -> Path: ...       # creates site-<highest + 1>
def choose(own: Path, site: str) -> None:  # writes OPEN_FILE
def move_in(own: Path) -> str | None: ...  # § 4.3
```

`open_site` reads `OPEN_FILE`. Where it is missing, unreadable, or names
a folder that is not under `sites/`, it opens the lowest-numbered site,
creating `site-1` where there is none, and writes `OPEN_FILE`. A name
is accepted only where it matches `site-[1-9][0-9]*`, so no value in the
file can reach outside `sites/`.

### 4.2 Which side each name is on

| Side | Names |
|---|---|
| Site (`SITE_NAMES`) | the Store's folders (`store.PUBLISHED_FOLDER`, `DRAFTS_FOLDER`, `BIN_FOLDER`, `PAGES_FOLDER`, `FURNITURE_FOLDER`, each value of `WAITING_FOLDERS`, `TEMPLATES_FOLDER`, `COMMENTS_FOLDER`, `PHOTOGRAPHS_FOLDER`, `FILES_FOLDER`, `FORWARDS_FOLDER`, `OPTIONS_FOLDER`, `IDENTITY_FOLDER`, `LOOK_FOLDER`), `settings.FILE_NAME`, `credentials.FILE_NAME`, `setup.SITE_FOLDER`, `editor.PREVIEW_FOLDER`, `paths.PREVIEW_ASSETS`, `starter.MARKER`, `insights.CACHE_NAME`, `undo.FETCH_FOLDER`, `wizard.FOLDER`, `choices.FILE_NAME` |
| Machine (`MACHINE_NAMES`) | `log.FILE_NAME`, `log.OLD_NAME`, `updater.FILE_NAME`, `installer.LOG_NAME`, `__main__._LOCK_NAME`, `themes.FILE_NAME`, `usage.FILE_NAME`, `usage.SENT_NAME`, `backups.FILE_NAME` (PRESS-0225), `sites.OPEN_FILE`, `sites.SITES_FOLDER` |

`sites.py` spells the names as strings, since it may not import those
parts; a test compares each with the constant it copies (INV-2).
`choices.json` is the site's: it remembers the page last opened, which
names a page of one site.

### 4.3 Moving an existing site in

`__main__._serve` calls `sites.move_in(own)` once `_hold` succeeds, so
a second Pressless cannot move the same files:

1. Where `sites/` exists and holds no `.moving` folder, return `None`.
2. Create `sites/.moving` where absent. Rename each top-level name in
   `SITE_NAMES` that exists into it, one rename each. Names in neither
   set are left where they are.
3. Rename `sites/.moving` to `sites/site-1`, then write `OPEN_FILE`
   naming `site-1`.

Every step is a rename inside one folder on one drive, so each is whole
or not done. A start that finds `sites/.moving` begins again at step 2,
which moves only what is still at the top. Where a rename fails,
`move_in` returns a sentence naming the folder by name only, `__main__`
prints it and stops with exit code 1, and nothing is deleted.

### 4.4 Handing folders to the parts

`_serve_once(own)` takes `site = sites.open_site(own)` at the top of each
pass, so a restart opens whichever site `OPEN_FILE` now names.

- **`own`** goes to `face.serve` (the log and the theme),
  `updating.register` and `sites_screen.register`, and to the lock.
  `sites_screen.register` also takes `restart.set`, as
  `restarting.register` does.
- **`site`** goes to `setup`, `github_setup`, `google_setup`,
  `dashboard`, `editor`, `templates`, `publishing`, `undo`,
  `page_editor`, `look_screen`, `files_screen`,
  `setup.carry_name_across`, `setup.follow_the_folder` and
  `settings.load`.
- **`usage.register(served, own, site=site)`**: `usage.json` stays in
  `own`, and its question loads the site's settings.
- **`setup.register(served, site, own=own)`**: setup's reports step
  writes the answer to `own`, and is left out where `own` already holds
  one, so a later site's setup does not ask again.
- **`face.serve(own, site=site)`**: `Face` gains `site`, which
  `Face.live_address` reads settings from and `Face`'s true-colours
  route remembers choices in. The details box's copy and open buttons
  keep `own`, where the log is.

`setup.follow_the_folder` already points `site_folder` at
`<site>/site`, which is what keeps each site building into its own
folder.

### 4.5 The keys

```python
# src/pressless/sites.py
def account(kind: str, site: Path) -> str:
    """'github' or 'google' for site-1, and for a folder that is no
    numbered site; 'github-site-2' and so on after."""
```

`setup` and `google_setup` use `sites.account("github", site)` and
`sites.account("google", site)` everywhere they use `GITHUB_ACCOUNT`
and `GOOGLE_ACCOUNT` today — filing, reading and deleting — and record
that name in `settings.Credentials` as today. `site-1` keeps the names
an existing install's key is already filed under, so the move in § 4.3
touches no keyring.

### 4.6 The Sites screen

`src/pressless/sites_screen.py`, at `/sites`, linked from every screen's
top bar after Your writing. Look and View your site keep their places
beside Settings (PRESS-0196, PRESS-0232).

- A list of the sites, the open one marked. Each shows its name:
  `store.read_identity`'s `name`, else `settings`' `repository`, else
  the words *New site*.
- **Open**, beside each other site: `POST /sites/open` with `site=site-N`
  calls `sites.choose`, then asks for PRESS-0203's restart after the
  reply, and answers with the restart's *going* page.
- **Start a new site**: `POST /sites/new` calls `sites.new_site` and
  `sites.choose`, then restarts as Open does. The new site has no
  settings, so the launch opens `/setup`, as for a first run.

A site whose `site=` names no folder under `sites/` gets the screen
again with a hint, and nothing changes.

## 5. Invariants

- **INV-1** — `sites.open_site` returns `<own>/sites/site-1`, creating
  it, for an empty folder; returns `site-2` where `OPEN_FILE` names it
  and it exists; and returns the lowest site for an `OPEN_FILE` naming
  `../x`, `site-0`, `site-9` where absent, or holding bytes that are not
  JSON. *Test:* `tests/test_sites.py::test_the_open_site`.
  *Breaks when:* a name outside `sites/` is opened, or a broken file stops
  the start.
- **INV-2** — Every name in `SITE_NAMES` and `MACHINE_NAMES` equals the
  constant it copies, and the two sets share no name. *Test:*
  `tests/test_sites.py::test_every_name_is_on_one_side`.
  *Breaks when:* a part renames its file and `sites.py` keeps the old
  name, so the move leaves it behind.
- **INV-3** — Over a folder laid out as today's one site, with an extra
  file `notes.txt`, `move_in` leaves every `SITE_NAMES` entry under
  `sites/site-1` with the same bytes, every `MACHINE_NAMES` entry and
  `notes.txt` at the top, and `OPEN_FILE` naming `site-1`. Run again, it
  changes nothing. *Test:*
  `tests/test_sites.py::test_an_existing_site_moves_in_whole`.
  *Breaks when:* a file is lost, copied rather than moved, or moved twice.
- **INV-4** — A folder left with `sites/.moving` holding half the site
  and the rest at the top ends, after `move_in`, exactly as INV-3's.
  *Test:* `tests/test_sites.py::test_a_stopped_move_finishes`.
  *Breaks when:* the second start treats `sites/` as done.
- **INV-5** — `sites.account("github", <own>/sites/site-1)` is `"github"`;
  for `site-3` it is `"github-site-3"`. Setup on `site-2` files and
  reads the key under `"github-site-2"` and leaves the `"github"` entry.
  *Test:* `tests/test_sites.py::test_each_site_keeps_its_own_key`, with
  one stand-in keyring both sites share, patched over
  `keyring.get_keyring` as `tests/test_credentials.py` does.
  *Breaks when:* a second site's key overwrites the first's.
- **INV-6** — After `POST /sites/open` with `site=site-2`, the next pass
  of `_serve_once` hands `site-2` to every part § 4.4 names it for, and
  `own` to the rest. *Test:*
  `tests/test_main.py::test_a_switch_hands_the_new_site_to_every_part`,
  with `face.serve` and each `register` replaced by a recorder.
  *Breaks when:* a part keeps the old site, or the log moves into a site.
- **INV-7** — A draft saved in `site-1`, then the user switches to
  `site-2`, is not listed in `site-2`'s Your writing and is still in
  `site-1`'s `drafts/`. *Test:*
  `tests/test_sites_screen.py::test_sites_keep_their_own_writing`.
  *Breaks when:* two sites share a Store folder.
- **INV-8** — `POST /sites/open` with `site=../site-1` or `site=site-7`
  where absent writes nothing and asks for no restart. *Test:*
  `tests/test_sites_screen.py::test_a_bad_site_changes_nothing`.
  *Breaks when:* the form's value reaches a path.
- **INV-9** — The Sites screen lists every site by name, opens another
  in a new tab, and starts a new one at setup. *Test:* a row in
  `scripts/by-hand-browser-checks.py`.
  *Breaks when:* the restart's new tab opens the old site.

The form's `site` value is the one input crossing the Face's boundary;
INV-1 and INV-8 hold it to `site-N` under `sites/`.

## 6. Failure modes

- **A rename refused** (a file held open on Windows): the move stops,
  says so, and the next start finishes it (INV-4).
- **An older Pressless run after this one** finds no site at the top and
  opens setup. Nothing is lost: the site is in `sites/site-1`, and
  moving its contents back to the top restores it. The README's
  upgrading section says so.
- **A site folder deleted by hand** while another is open: `open_site`
  opens the lowest remaining one, or makes `site-1`.
- **A switch while a publish runs**: the restart already waits on
  `editor.LOCK` before stopping the Face (PRESS-0203).

## 7. Tests

`tests/test_sites.py` locks INV-1, INV-2, INV-3, INV-4 and INV-5; `tests/test_main.py` INV-6,
`tests/test_sites_screen.py` INV-7 and INV-8, and
`scripts/by-hand-browser-checks.py` INV-9. Existing tests that build a
Face over one folder keep passing that folder as `own` and `site` both.
The screen's words go through `words.py` and `tests/test_words.py`. Each
test is seen failing before the code exists, and mutation-probed once it
lands.

## 8. Alternatives considered (and rejected)

- **A site anywhere the user picks, like a document.** Rejected: § 3
  decision 2.
- **Leaving the first site at the top, and adding others under
  `sites/`.** Rejected: one site would be laid out differently from the
  rest, and every save, backup and switch would carry the difference.
- **Switching in place, re-registering routes on the running Face.**
  Rejected: every part's module state would have to be reset by hand, and
  one missed would act on the old site.
- **Renaming the existing keyring entries at the move.** Rejected: a
  keyring can prompt or refuse mid-move; keeping `site-1`'s names needs
  no keyring at all.

## 9. Out of scope

- Listing the sites in a GitHub account and adding one from there (the
  user, 2026-10-05) — PRESS-0290.
- Removing a site — PRESS-0291.
- Saving and opening a site as one file — PRESS-0224.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_sites.py::test_the_open_site` |
| INV-2 | `tests/test_sites.py::test_every_name_is_on_one_side` |
| INV-3 | `tests/test_sites.py::test_an_existing_site_moves_in_whole` |
| INV-4 | `tests/test_sites.py::test_a_stopped_move_finishes` |
| INV-5 | `tests/test_sites.py::test_each_site_keeps_its_own_key` |
| INV-6 | `tests/test_main.py::test_a_switch_hands_the_new_site_to_every_part` |
| INV-7 | `tests/test_sites_screen.py::test_sites_keep_their_own_writing` |
| INV-8 | `tests/test_sites_screen.py::test_a_bad_site_changes_nothing` |
| INV-9 | `scripts/by-hand-browser-checks.py`, run in Chrome; Firefox and Edge by hand |
| § 4.2 a new file a part adds | **Partial:** INV-2 catches a renamed name; a new name in neither set is caught by nothing |

## 11. Cross-doc impact

- `docs/design.md` § Where everything sits on disk — Pressless's own
  folder holds the machine's files and `sites/`, one folder per site.
- `docs/specs/PRESS-0003-log.md` INV-4 — the log sits in Pressless's own
  folder; the settings file is in the site's.
- `docs/specs/PRESS-0021-setup.md` § 4.5 — the site folder is
  `<site>/site`.
- `docs/specs/PRESS-0023-self-update.md` INV-14 — unchanged; the names
  it lists are machine names.
- `README.md` § Upgrading without losing anything — the folder's new
  shape, and moving a site back for an older Pressless.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0223-several-sites-loop-log.md`.

## 13. Migration / compatibility

§ 4.3 is the migration. `Pressless-data`'s own name is unchanged
(PRESS-0022 INV-8). A site's folder has the shape the whole of
`Pressless-data` had, so every part reads it as before.
