<!-- ants-spec-format: 1 -->
# PRESS-0224 — A whole site saves to one file, and opens again

**Status:** accepted (2026-10-16). Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0224 (user-request-2026-10-03).

**Blocked by:** PRESS-0223.
**Blocker for:** PRESS-0225, PRESS-0221, which make and open this file.
**Pairs with:** PRESS-0223.

Layman: a whole site, its writing, photographs and settings, saves as
one file, and that file opens later, or on another computer, as a site.

## 1. Goal

After this ships, the Sites screen (PRESS-0223 § 4.6) saves the open
site as one `.zip` file the browser downloads, and opens such a file as
a site. The file never holds a key. A file from elsewhere is checked
whole before anything is written, and one that fails a check writes
nothing.

## 2. Problem

1. **A site cannot leave the machine whole.** Drafts and photograph
   originals are kept only in the site's folder (`docs/design.md`
   § Where everything sits on disk: "unfinished work is not backed up").
   No code writes a site to a file; the one `zipfile` use is
   `updater.unpack`.
2. **The Face cannot take a large file.** `face._MAX_BODY` refuses a
   body over 64 MiB, and every body is read whole into memory before a
   page sees it. A site with its photographs is larger.
3. **The Face cannot hand back a file to save.** Nothing sends a file
   as a download.

## 3. Scope decisions (agreed with the user)

1. **One format for saving and for backups** — user, 2026-10-03
   (PRESS-0221, PRESS-0225 share it).
2. **No key in the file; opening asks for it again** — user, 2026-10-03.
3. **The file is a plain `.zip`.** Recommended by Claude, 2026-10-16:
   any computer opens one without Pressless, so the writing inside is
   never locked in, as entries stay readable in Notepad (ADR-0001).
4. **Opening makes a new site; it never writes over one.** Recommended
   by Claude, 2026-10-16. The one exception is an unused site (§ 4.4),
   which a fresh install starts with.
5. **The format is frozen with the rest at 1.0.0** — user, 2026-10-03.

## 4. Design

### 4.1 The file

```
<name> <YYYY-MM-DD>.zip
  pressless-site.json     {"format": "pressless-site", "version": 1}
  settings.json           the site's, with "site_folder": ""
  published/ drafts/ ...  each KEPT name present in the site, as it is there
```

A new module, `src/pressless/sitefile.py`:

```python
MANIFEST = "pressless-site.json"
VERSION = 1
KEPT = frozenset({...})     # the Store's folders, settings.json,
                            # preview-assets, starter-unpublished
LEFT_OUT = frozenset({...}) # credentials.json, site, preview, fetch,
                            # insights.json, wizards, choices.json

def save(site: Path, target: Path) -> None: ...
def check(source: Path, room: int) -> None: ...      # raises Refused
def open_into(source: Path, own: Path) -> Path: ...  # the new site

class Refused(Exception): ...   # what failed, never a path
```

`KEPT` and `LEFT_OUT` together are exactly PRESS-0223's `SITE_NAMES`.
What is left out is a key, something rebuilt on demand, or where the user
was last.

`<name>` is the site's name (PRESS-0223 § 4.6) with every character but
letters, digits, spaces and hyphens removed, else `Pressless site`.

### 4.2 Saving

`save` holds `editor.LOCK`, so no save or publish lands half in the
file, and writes `target` as a new zip: the manifest first, then every
file under each `KEPT` name present, by its path relative to the site,
with `/` between parts. Members under `photographs/` and `files/` are
stored; the rest are deflated. `settings.json` goes in as read, but with
`site_folder` set to `""`, so the file names no path on this computer.

`GET /sites/save` saves to `<own>/.saving-<random>.zip` and answers with
it as a download (§ 4.5), named as § 4.1 says.

### 4.3 Checking

`check` opens `source` as a zip and raises `Refused` for any of:

- not a zip, or no `MANIFEST`, or a manifest whose `format` is not
  `pressless-site`;
- `version` above `VERSION`, with words saying a newer Pressless made it;
- a member name that is absolute, holds `..`, a backslash or a drive
  letter, or whose first part is neither `MANIFEST` nor in `KEPT`
  (`updater._allowed` is the precedent);
- a member that is a link (`external_attr`'s file type is a link);
- members whose sizes add up to more than `room` bytes.

Nothing is written before `check` passes.

### 4.4 Opening

`open_into(source, own)`:

1. `check(source, room)`, where `room` is the free space on the drive
   holding `own`, less 1 GiB.
2. Unpack every member but `MANIFEST` into `<own>/sites/.opening`,
   removed first where a stopped open left one.
3. The target is the open site where that site is unused, else
   `sites.new_site(own)`. **Unused** means it has no `settings.json` and
   `store.holds_a_site` is False for it, as on a fresh install after its
   first launch has seeded `templates/`.
4. Rewrite `.opening`'s `settings.json` as JSON, keeping every key it
   does not name: `site_folder` becomes `<target>/site`;
   `credentials.store` is `credentials.choose().store`, kept as it was
   where that raises; `github_account` is
   `sites.account("github", target)`, and `google_account`, where it is
   not null, `sites.account("google", target)`. Then `settings.load`
   must accept it, or the open is refused.
5. The target folder is removed, then `.opening` is renamed to its name.
6. `sites.choose(own, target.name)`, and PRESS-0223's restart opens it.

A refusal at any step removes `.opening` and any folder `new_site` made,
and leaves `sites/` as it was.

The site opens with no key. Publishing then says Pressless does not have
the publishing key yet, and to enter it in Settings
(`failure.credentials.NotStored`), as today for a missing key.

### 4.5 Large files through the Face

```python
# src/pressless/face.py
def add_upload(self, path: str, handler: Callable[[Path], str],
               into: Path) -> None: ...

@dataclass(frozen=True)
class Download:
    path: Path      # sent, then deleted
    name: str       # the name the browser saves it under
```

- **`add_upload`** registers a `POST` route that gets every check a
  registered page gets — host, cookie, origin — before its body is read.
  The body is the file itself, sent by `fetch` with no form around it.
  It is copied in 64 KiB pieces to `<into>/.upload-<random>`, refused
  with 413 where the declared length is over the drive's free space less
  1 GiB, and handed to `handler` by path. The handler runs as a
  registered page's does: `face.after_reply` works inside it, its `str`
  is wrapped as a page, and an exception reaches `Face.fail`. The file is
  deleted when `handler` returns or raises. `_MAX_BODY` is unchanged for
  every other route.
- **A page may return a `Download`.** The Face sends it in 64 KiB pieces
  with `Content-Disposition: attachment` and the name quoted as RFC 6266
  says, then deletes it.

`POST /sites/open-file` is an upload into `own`; its handler calls
`open_into`, and answers with the restart's *going* page, or the Sites
screen with the refusal's sentence.

### 4.6 The Sites screen

PRESS-0223 § 4.6's screen gains **Save this site to a file**, a link to
`GET /sites/save`, and **Open a site file**, a file input taking `.zip`
whose choice is sent to `POST /sites/open-file`. While it is sent, the button
reads *Opening…* and is disabled.

## 5. Invariants

- **INV-1** — A saved site holds `MANIFEST` and every file under each
  `KEPT` name present, and nothing under a `LEFT_OUT` name, with
  `credentials.json` holding a sentinel secret in the site. Its
  `settings.json` has `site_folder` `""`. *Test:*
  `tests/test_sitefile.py::test_a_saved_site_holds_no_key_and_no_path`.
  *Breaks when:* a left-out name is written, or the path stays in.
- **INV-2** — Saving a site and opening the file gives a site whose every
  file under a `KEPT` name has the same bytes, apart from
  `settings.json`'s `site_folder` and `credentials`. *Test:*
  `tests/test_sitefile.py::test_a_site_comes_back_whole`.
  *Breaks when:* a file is dropped, renamed, or changed in the trip.
- **INV-3** — `check` refuses a file holding each of: a member `../x`,
  `/x`, `a\b`, `C:x`, `secrets/x`, a link, no manifest, `version` 2;
  and `open_into` over each leaves `sites/` with the same names and bytes.
  *Test:* `tests/test_sitefile.py::test_a_bad_file_writes_nothing`.
  *Breaks when:* a member is unpacked before every member is checked, or
  one escapes the site's folder.
- **INV-4** — A file whose members add up to more than `room` is
  refused. *Test:*
  `tests/test_sitefile.py::test_a_file_too_big_for_the_drive_is_refused`,
  with `shutil.disk_usage` replaced.
  *Breaks when:* the sizes are not added before unpacking.
- **INV-5** — An opened site's settings name `<target>/site` and the
  target's own account names, and `settings.load` accepts them. *Test:*
  `tests/test_sitefile.py::test_an_opened_site_is_set_up_for_this_computer`.
  *Breaks when:* the opened site reads or writes another site's key.
- **INV-6** — Opening over a fresh install's unused `site-1`, its
  templates seeded, makes the file's site `site-1`; opening while
  `site-1` holds writing makes `site-2` and leaves `site-1` unchanged.
  *Test:* `tests/test_sitefile.py::test_opening_never_writes_over_a_site`.
  *Breaks when:* a site with settings or writing is removed.
- **INV-7** — An upload route takes a body larger than `face._MAX_BODY`,
  handing the handler a file with the same bytes, and deletes it after;
  the same body to a registered page is refused with 413. *Test:*
  `tests/test_face.py::test_an_upload_streams_past_the_page_ceiling`.
  *Breaks when:* the body is read whole, or the file is left behind.
- **INV-8** — An upload without the session cookie, or with another
  origin, is refused before a byte of the body is written; a download
  without the session cookie is refused.
  *Test:* `tests/test_face.py::test_an_upload_needs_the_session`.
  *Breaks when:* the upload route skips a check a page gets.
- **INV-9** — `GET /sites/save` answers with `Content-Disposition:
  attachment`, the § 4.1 name, the zip's bytes, and leaves no
  `.saving-` file. *Test:*
  `tests/test_sites_screen.py::test_save_downloads_the_site`.
  *Breaks when:* the file is answered inline, or left in the folder.
- **INV-10** — On the Sites screen, Save downloads a file and Open with
  that file opens it as a new site in a new tab. *Test:* a row in
  `scripts/by-hand-browser-checks.py`.
  *Breaks when:* the file input's choice is not sent as the body.

The file is the trust boundary: it may come from anyone. INV-3 and INV-4
hold what it can write, and every entry it carries is read afterwards by
the Store's own checks, as an entry from disk is today.

## 6. Failure modes

- **The drive fills while unpacking**: the write fails, `.opening` is
  removed, and the screen says the file could not be opened and no site
  changed.
- **Pressless stops mid-open**: `.opening` is left, never listed (it
  does not match `site-N`), and removed by the next open. A site
  `new_site` made is left empty.
- **The browser stops a download**: the `.saving-` file is deleted when
  the send ends, sent or not.
- **A file from a newer Pressless**: refused, with words to update
  Pressless first.
- **A keyring that refuses** at step 4: the store stays as the file had
  it, and Settings asks for the key as for any missing key.

## 7. Tests

`tests/test_sitefile.py` locks INV-1, INV-2, INV-3, INV-4, INV-5 and
INV-6; `tests/test_face.py` INV-7
and INV-8, `tests/test_sites_screen.py` INV-9, and
`scripts/by-hand-browser-checks.py` INV-10. Fixtures are sites built in
the test with sentinel words, never real writing, and a hostile zip is
built in the test with `zipfile`. Each test is seen failing before the
code exists, and mutation-probed once it lands.

## 8. Alternatives considered (and rejected)

- **A format of Pressless's own.** Rejected: § 3 decision 3.
- **Typing the file's path instead of uploading it.** Rejected: the user
  is not asked for a path anywhere else, and a browser's file chooser is
  what every other upload uses.
- **Saving into a folder on disk rather than a download.** Rejected for
  saving by hand: the browser already asks where to save. PRESS-0225's
  automatic backups write to a folder, and call `save` directly.
- **Raising `_MAX_BODY`.** Rejected: every body would still be held in
  memory whole.
- **Keeping the built site and the preview in the file.** Rejected: both
  are rebuilt on demand and would double the file's size.

## 9. Out of scope

- Daily automatic backups — PRESS-0225.
- The move-to-a-new-computer wizard — PRESS-0221.
- Opening a file over an existing site to restore it — deferred; not yet
  queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_sitefile.py::test_a_saved_site_holds_no_key_and_no_path` |
| INV-2 | `tests/test_sitefile.py::test_a_site_comes_back_whole` |
| INV-3 | `tests/test_sitefile.py::test_a_bad_file_writes_nothing` |
| INV-4 | `tests/test_sitefile.py::test_a_file_too_big_for_the_drive_is_refused` |
| INV-5 | `tests/test_sitefile.py::test_an_opened_site_is_set_up_for_this_computer` |
| INV-6 | `tests/test_sitefile.py::test_opening_never_writes_over_a_site` |
| INV-7 | `tests/test_face.py::test_an_upload_streams_past_the_page_ceiling` |
| INV-8 | `tests/test_face.py::test_an_upload_needs_the_session` |
| INV-9 | `tests/test_sites_screen.py::test_save_downloads_the_site` |
| INV-10 | `scripts/by-hand-browser-checks.py`, run in Chrome; Firefox and Edge by hand |
| § 4.1 `KEPT` and `LEFT_OUT` cover `SITE_NAMES` | `tests/test_sitefile.py::test_every_site_name_is_kept_or_left_out` |

## 11. Cross-doc impact

- `docs/design.md` § Where everything sits on disk — the sentence
  saying unfinished work is not backed up points here.
- `docs/specs/PRESS-0011-face.md` — the Face gains upload routes and
  downloads (§ 4.5).
- `README.md` § Upgrading without losing anything — save the site to a
  file, and open it on the new computer.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0224-site-file-loop-log.md`.

## 13. Migration / compatibility

A file's `version` is 1. A later Pressless that changes what the file
holds raises it, and keeps opening every earlier version.
