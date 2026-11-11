# Versioning overrides — Pressless

This file holds the two answers `~/.claude/standards/versioning.md`
refuses to supply — § 3's breaking surfaces and § 4's `1.0` exit
condition — which `~/.claude/standards/README.md` § The three cases pins
to this path. **It also carries one delta**: § The MINOR follows the
milestones, which departs from § 4.

## What would make this 1.0

**MAJOR stays 0 until every sign of success in `docs/discovery.md`
§ Signs it is working holds, and the entry file format is frozen.**

`versioning.md` § 4 requires that line in this file, so the copy is
deliberate: `ROADMAP.md` § Milestones states the same condition and
carries which item belongs to which milestone. Change them together —
nothing checks that they agree.

## The MINOR follows the milestones

**A departure from `versioning.md` § 4**, decided by the user
2026-09-28. It replaces the 2026-08-27 decision that the milestone
numbers were goalposts only. Under § 4 every release since 0.1.0 is a
PATCH, so the history would run 0.1.x straight to 1.0.0 and say nothing
about progress a user can see.

- **A release takes the number of the highest milestone in `ROADMAP.md`
  § Milestones whose section has every item shipped**, where that is
  higher than the last release. `roadmap_query` with `status:
  ["planned","in-progress"]` answers it: the lowest section still listed
  is the first milestone not reached.
- **Any other release bumps the PATCH.**
- **A breaking change waits for the next milestone release.** It is
  never shipped in a PATCH, and it never takes a MINOR of its own, so the
  MINOR always names a milestone. Its changelog entry says what the
  writer must do.

## The breaking surfaces

A change to anything below is breaking however small the diff: someone
who upgrades has something that used to work stop working. It ships
only in a milestone release (§ The MINOR follows the milestones).

**From 1.0.0 every surface below is frozen**: changing one is a MAJOR
release under `versioning.md` § 2. § Which test holds each surface names
the test that fails when one changes.

### The writer's own files

- **The entry file's format** — its `Key: value` header, its body, and
  that every newline in the body is a line break (ADR-0001). Twelve
  years of archive, and the surface the 1.0 promise is about.
- **What a mark means, and which marks exist.** Marks lives in the files
  *and* in the writer's hands. Change what a mark does and everything
  already written renders differently, with nothing to migrate: the file
  on disk never changed. **Adding** a mark is the same breach by the
  other route — ADR-0001 preserves anything the parser does not
  recognise byte-for-byte, so a new mark restyles text that has been
  rendering literally for years.
- **Where the Store keeps things**, inside each site's folder in
  Pressless's own folder. `docs/design.md` § Where everything sits on
  disk keeps drafts outside the site folder, and S7 rests on it. Each
  folder's name and file shape is owned by the spec named beside it:
  - `published/` and `drafts/`, one `.txt` per entry named by its slug
    (PRESS-0005);
  - `pages/`, `furniture/`, and the waiting copies beside them
    (PRESS-0006, PRESS-0014, PRESS-0195);
  - `templates/` (PRESS-0017) and `comments/` (PRESS-0006);
  - `photographs/` and `files/` (PRESS-0006, PRESS-0197);
  - `forwards/`, which keeps old addresses alive (PRESS-0182,
    PRESS-0195, PRESS-0210);
  - `options/`, `identity/` and `look/` (PRESS-0214, PRESS-0213,
    PRESS-0196).
- **How an entry names a photograph** — the `{photo: name}` mark,
  resolved inside `photographs/` (PRESS-0004).
- **The folder of sites** — `sites/site-N/`, and which names belong to a
  site rather than the machine (PRESS-0223 § 4.2).
- **A saved site file and the daily backups.** The site file's manifest
  and contents (PRESS-0224), and a backup's folder and file name, which
  is how old backups are found and pruned (PRESS-0225).

### Setup state

**Nothing here may be lost to an upgrade.** Decided by the user
2026-08-27: an update that overwrites settings is not a good update
system. S5 asks that the publishing key be given exactly once, and an
upgrade that asks again has broken it. **What is protected is the
writer's values, not their spelling**: a change here that carries every
existing value forward takes nothing away, so it is not this breach.

- **`settings.json`.** `load()` refuses any version but its own and
  writes nothing, so a bump carrying no values forward leaves the writer
  unable to start rather than wiped. The repair is the old file, so an
  upgrade must not send him to setup over it — `load()` distinguishes a
  missing file from an unreadable one (INV-2) precisely so it can tell.
  A key that changes meaning under an unmoved version lands the same way.
- **The keyring account names.** Change one and the secret reads as
  absent, so setup asks for what was already given.
- **The credential file's shape**, where there is no keyring (ADR-0003)
  — the same consequence by the other route.
- **`sites.json`**, which names the open site (PRESS-0223). A file this
  build does not read opens the lowest-numbered site and is written
  over, so the writer's choice is lost without a word.

### The live site

- **A published page's address.** Decided by the user 2026-08-27.
  Inbound links, search results and anything already shared point at
  pages that exist. Pressless cannot tell that an address it changed was
  in use, so the first report comes from a reader. A forwarded old
  address is the same promise.
- **The fixed files every page links to** — the site icon, the
  stylesheets and the interactive pieces' script (PRESS-0227,
  PRESS-0126, PRESS-0217).
- **`content/` in the site's repository.** Undo fetches older states
  from it, so a state published by an older Pressless must still read
  (PRESS-0008, PRESS-0015).
- **The vote key and where a vote is stored** (PRESS-0211 § 4.2). Change
  either and every existing like and dislike stops counting.

## What is deliberately not a surface

Named because over-caution costs as much as carelessness.
Each is exempt for its own reason rather than a shared one.

- **The Insights cache** — `docs/design.md` § State: deleting it costs a
  fresh fetch and nothing else.
- **The rolling log** — `docs/design.md` § Logging makes it plain
  English for the writer to read, so nothing binds to its shape.
- **The area a previous state is laid out in for undo**, emptied when
  that sequence ends. What it holds came from GitHub and can be fetched
  again, so losing it costs a re-fetch rather than the undo.
- **Work in progress** — a wizard's progress (PRESS-0212) and an
  Import's working folder (PRESS-0125). A wizard that cannot read its
  progress starts over by design; an Import can be run again from the
  export.
- **The preview and the built site** — Pressless writes both again from
  the Store.
- **The machine's own preferences** — the theme, where the writer was
  last, the usage answers, the update record and the lock. Losing one
  costs a choice made again, never his work.

## Which test holds each surface

Each test compares against a literal copy of the shape, so it fails
when the shape changes. `tests/test_frozen.py` holds the pins that had
no other home.

| Surface | Test |
|---|---|
| Entry file format | `test_store.py::test_an_absent_recognised_field_is_not_written_back`, `::test_unknown_header_fields_survive` |
| The marks, and what each renders | `test_frozen.py::test_the_marks_are_the_frozen_set`, `::test_each_mark_still_renders_as_it_always_has` |
| `published/` and `drafts/` | `test_store.py::test_a_draft_never_reaches_published` |
| `pages/`, `furniture/`, waiting copies | `test_store_extras.py::test_illegal_names_are_refused`, `::test_waiting_copies_follow_the_name_rule` |
| `templates/` | `test_store_extras.py::test_a_template_is_never_an_entry` |
| `comments/` | `test_store_extras.py::test_comments_carry_no_contact_details` |
| `photographs/`, and how an entry names one | `test_store_extras.py::test_photographs_stay_where_they_are` |
| `files/` | `test_store_extras.py::test_files_are_named_and_binned_like_writing` |
| `forwards/` | `test_store.py::test_forwards_round_trip`, `test_store_extras.py::test_page_forwards_follow_the_name_rule`, `test_frozen.py::test_an_address_forwards_file_still_reads` |
| `options/` | `test_store.py::test_write_journal_keeps_other_options` |
| `identity/` | `test_store_extras.py::test_an_identity_without_pictures_is_written_as_before` |
| `look/` | `test_frozen.py::test_a_version_one_look_still_reads_and_writes_back_the_same` |
| The folder of sites | `test_sites.py::test_an_existing_site_moves_in_whole` |
| The site file | `test_sitefile.py::test_a_saved_site_holds_no_key_and_no_path`, `::test_a_site_comes_back_whole` |
| Daily backups | `test_backups.py::test_each_site_gets_one_backup_a_day` |
| Pressless's own folder name | `test_paths.py::test_folder_name_is_pinned` |
| `settings.json` | `test_settings.py::test_field_names_are_the_documented_set`, `::test_a_version_that_is_not_the_number_one_is_refused`, `test_frozen.py::test_settings_writes_the_frozen_keys` |
| Keyring account names | `test_sites.py::test_each_site_keeps_its_own_key` |
| The credential file | `test_frozen.py::test_a_version_one_credentials_file_still_gives_its_secret`, `::test_the_credentials_file_is_still_written_as_version_one` |
| `sites.json` | `test_sites.py::test_the_open_site` |
| Published addresses | `test_builder.py::test_pages_sit_at_their_addresses`, `::test_a_filtered_entry_is_kept_off_every_page` |
| Fixed files every page links to | `test_builder.py::test_the_icon_is_square_and_on_every_page`, `::test_the_style_code_replaces_the_assets_links`, `::test_a_page_with_no_piece_is_unchanged` |
| `content/` in the repository | `test_builder.py::test_a_filtered_entry_is_kept_off_every_page` |
| Votes | `test_votes.py::test_vote_key_is_the_field_else_the_date_and_slug`, `::test_check_order_and_where_it_writes` |

**The writer's real archive is checked only on a machine that holds
it.** The `*_archive.py` tests read it from environment variables and
skip without them, so CI runs none of them (`docs/working-here.md`
§ Archive tests and a fresh clone's keys).

## A surface nobody wrote down is still a surface

`versioning.md` § 3's rule, repeated rather than cited because this list
is young and most of what it names is not built. If the writer relies on
something and an upgrade stops it working, that release was breaking
whether or not this file mentions it.

## What checks this

| Claim | What checks it |
|---|---|
| A release's number matches the milestones reached | Nothing automatic. The `roadmap_query` call in § The MINOR follows the milestones answers it, and `cut-release` does not run it. |
| A breaking change waited for a milestone release | Nothing. `cut-release` does not choose the level, and its `Added`-forbids-a-PATCH floor is skipped while MAJOR is `0`. |
| A surface here still has the shape described | § Which test holds each surface. Nothing checks that the list is complete. |
| This file and `ROADMAP.md` § Milestones agree on 1.0 | Nothing. § 4 requires the condition stated here, so the copy is deliberate and both have to be changed together. |

## Review loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-27 | 3, cold — genre pinned `standard`, packet carried the global `versioning.md` §§ 1-4, the standards index's three cases, ROADMAP § Milestones, the two ADRs cited, discovery's signs of success, `settings.py`'s version constant and `cut-release`'s level floor | 2 | 2 | 1 | n/a | **Five verified, five fixed; one dismissed.** **All three lanes independently found the same two defects**, which is the strongest signal in the run. The `settings.json` bullet named a key changing meaning under a static version as the breach, which by implication exempted a `FILE_VERSION` bump — and `load()` refuses every version but one, so a bump discards the whole file and asks for the publishing key again, breaking S5. The bullet now names both routes. And the 1.0 section said the promise was "not restated here" while restating it almost verbatim from § Milestones, with the What-checks-this table claiming divergence was impossible because the file points rather than copies; the copy is deleted, so all three statements are true. **The Q3 came from one lane and needed ADR-0001 to see**: unrecognised text is preserved byte-for-byte, so *adding* a mark restyles archive text that has been rendering literally — a conformer could not tell whether that was a MINOR or a PATCH. **One Q1 was found by resolving a lane's open question rather than by a lane**: the not-a-surface list rested on "each is a copy of something that can be got again", which is false of a log. Each entry now carries its own reason. **Dismissed:** a lane read the undo staging area as the only route back; `fetch_previous` re-fetches it from GitHub, so the exemption stands and only its stated ground was wrong. **Before dispatch, 1b found one defect of its own** — the entry-file bullet credited ADR-0001 with "one file per entry", which is the Store's rule. **And 4a step 3 caught an over-reach in a fix**: "no code reads the log" is not something `design.md` says or this run could run, narrowed to what § Logging supports. |
| 2 | 2026-08-27 | 3, cold — identical brief, packet rebuilt whole from disk and extended with `load()`'s executed refusal | 3 | 3 | 0 | n/a | **Six verified, six fixed; one surfaced.** **Half landed on loop 1's own fixes.** Loop 1 deleted the copied 1.0 promise and left a compressed copy under the words *not restated here*, which all three lanes found; the section now only points. Loop 1's own word *lose* was wrong about the mechanism — `load()` refuses and writes nothing, so a bad version leaves the writer unable to start rather than wiped, and sending him to setup would overwrite the one file that could be repaired. And the intro made any change to a listed surface breaking while § Setup state made only a lossy one breaking, so one migrated change had two version numbers; the section now says values, not spellings, are what is protected. **Two pre-existing Q1s.** The Store bullet said the draft layout was unchosen — `design.md` already fixes drafts outside the site folder and S7 rests on it, so a builder could have published unfinished work. And the checks table said nothing checks a surface's shape; a settings test does, while nothing pins the version refusal this file names as a breach. **Surfaced, not fixed:** the milestone numbers may be unreachable under § 4. |
| 3 | 2026-08-27 | 3, cold — identical brief, packet rebuilt whole from disk and extended with the executed `load()` results, the settings test inventory and the spec's INV-2 / INV-6 | 0 | 2 | 1 | n/a | **Three verified, two fixed, one already surfaced. Cap reached (3 for a standard), and it is a VIOLENT cap** — a majority of this loop's findings landed on text loops 1 and 2 wrote. **All three lanes found the same defect, and it is this run's own doing.** Loop 1 read the copied 1.0 condition as a contradiction and deleted the promise; loop 2 deleted the summary that was left; loop 3 found that `versioning.md` § 4 requires the line to be stated *here*, so the file had come to breach the rule it exists to satisfy — and § 4's next bullet calls a project with no such line one whose leading zero has gone inert. The condition is stated again, with the copy declared deliberate, which is the answer no earlier loop reached. **A Q3 from two lanes:** *the layout inside that folder* had the site folder as its nearer antecedent while meaning Pressless's own, and those two are opposite surfaces — one published in full, one never. Named explicitly. **Already surfaced before this loop, not fixed:** the milestone names may not be reachable levels under § 4, which is the user's decision and is filed as its own item. **Routing:** the document is small, so the cap is not a size signal; it is not re-gated as it stands, and what re-arms the gate is an authoring edit that changes direction. |
