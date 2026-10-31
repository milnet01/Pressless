<!-- ants-spec-format: 1 -->
# PRESS-0197 — Upload music, video, PDF, ZIP and text files

**Status:** accepted (2026-10-16).
**Kind:** feature.
**Source:** ROADMAP PRESS-0197 (user request 2026-10-01, PRESS-0194;
decisions 2026-10-16).

**Blocker for:** PRESS-0227.
**Amends:** PRESS-0006 (§ 4.1, the Store's folders), PRESS-0005 (§ 4.1,
`move_to_bin`'s folders), PRESS-0008 (§ 4.1 `ROOT_OUTPUT`), PRESS-0013
(§ 4.3, a kept folder the build fills), PRESS-0021 (decision 3,
`untouchable`), PRESS-0012 (§ 4.3's type table),
PRESS-0260 (§ 3 decision 6, § 4.6). § 11 lists each edit.

Layman: the writer can upload songs, videos, PDFs, ZIP files and text
files, pick one in a video, music or download section, and remove one
nothing uses from a new Files screen.

## 1. Goal

After this ships, Pressless keeps uploaded files of nine kinds (§ 4.1)
beside its photographs. The visual editor's video, music and download
sections choose one from a list or upload one, as a picture section
chooses a photograph. A file a page names is published with the site, byte
for byte. A Files screen lists every kept file and removes one no page
names.

## 2. Problem

1. **Only photographs can be uploaded.** `editor._photograph` hands every
   upload to `photographs.add`, which raises `NotAPhotograph` for anything
   Pillow cannot decode.
2. **A video, music or download section takes a typed address**
   (PRESS-0260 § 3 decision 6), so its file has to live somewhere else
   already.
3. **Nothing lists or removes an upload.** No Face route does, and
   `store._BINNABLE` leaves out `PHOTOGRAPHS_FOLDER`.

## 3. Scope decisions (agreed with the user)

1. **A set list of kinds, chosen by suffix and checked by content.**
   Decided by the user 2026-10-16. Web pages, SVG and script files are
   refused, because they can carry code; code on a page goes through the
   script piece (PRESS-0217).
2. **50 MiB at most per file.** Decided by the user 2026-10-16. Git warns
   above it: "If you attempt to add or update a file that is larger than 50
   MiB, you will receive a warning from Git." Source:
   https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
3. **Sections choose a file, and a Files screen lists and removes them.**
   Decided by the user 2026-10-16.
4. **The suffix must match the content, or the file is refused.** *(decided
   here)* A photograph's wrong suffix is replaced, because Pillow names its
   format. Here a `.docx` is a ZIP by its bytes, and renaming it `.zip` would
   surprise the writer.
5. **A file is published byte for byte.** *(decided here)* Photographs are
   re-encoded to drop location data (PRESS-0008 § 4.6). None of these kinds
   carries location the way a camera's picture does, and re-encoding sound
   or video needs a dependency the stack rules out.
6. **The Files screen lists only `files/`, not photographs.** *(decided
   here)* A photograph original is deliberately not binnable
   (`store._BINNABLE` leaves it out), and changing that is its own item.
7. **Removal is refused while a page names the file.** *(decided here)* A
   removed file would leave a section pointing at nothing, and the Builder
   skips an address it does not hold, so nothing else would say so.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The kinds

| Kind | Suffix | The bytes begin | Served as | Chosen by |
|---|---|---|---|---|
| MP3 | `.mp3` | `ID3`, or `0xFF` then a byte whose top three bits are set | `audio/mpeg` | music, download |
| Ogg | `.ogg` | `OggS` | `audio/ogg` | music, download |
| WAV | `.wav` | `RIFF`, any four bytes, `WAVE` | `audio/wav` | music, download |
| M4A | `.m4a` | any four bytes, then `ftyp` | `audio/mp4` | music, download |
| MP4 | `.mp4` | any four bytes, then `ftyp` | `video/mp4` | video, download |
| WebM | `.webm` | `1A 45 DF A3` | `video/webm` | video, download |
| PDF | `.pdf` | `%PDF-` | `application/pdf` | download |
| ZIP | `.zip` | `PK\x03\x04` or `PK\x05\x06` | `application/zip` | download |
| Text | `.txt` | decodes as UTF-8 throughout, holding no NUL | `text/plain; charset=utf-8` | download |
| WOFF | `.woff` | `wOFF` | `font/woff` | no section |
| WOFF2 | `.woff2` | `wOF2` | `font/woff2` | no section |
| TrueType | `.ttf` | `00 01 00 00` or `true` | `font/ttf` | no section |
| OpenType | `.otf` | `OTTO` | `font/otf` | no section |
| Icon | `.ico` | `00 00 01 00` | `image/x-icon` | no section |

The last five are PRESS-0210 § 3 decision 10's, for a brought-in site's look.
The suffix is compared lower-cased. The *Chosen by* column is what each
section's list offers (§ 4.5); the Builder publishes any kept file a page
names, whatever section names it (§ 4.6).

### 4.2 The module

```python
# src/pressless/builder.py — added, beside photograph_format
FILE_LARGEST = 50 * 1024 * 1024
def file_allowed(name: str, data: bytes) -> bool: ...   # § 4.1, by name's suffix

# src/pressless/files.py — new
ACCEPT: dict[str, str]   # "music" | "video" | "download" -> the input's accept=
class NotAllowed(Exception): ...   # suffix not listed, or bytes not that kind
class TooLarge(Exception): ...
def add(folder: Path, filename: str, data: bytes) -> str: ...
```

The content test sits in `builder.py`, as `photograph_format` does, so the
Builder can re-check a file without a new import (PRESS-0008 INV-11), and
`files.py` imports it as `photographs.py` does.

- **`add`** raises `TooLarge` where `len(data) > builder.FILE_LARGEST`, and
  `NotAllowed` where `builder.file_allowed` is False, before anything is
  written. Otherwise it names and places the file as `photographs.add` does:
  the stem lower-cased and reduced to `[a-z0-9_-]`, cut to
  `photographs.LONGEST_NAME`, `"file"` when empty, the suffix kept; a taken
  name moves to `-2`, `-3`; identical bytes return the existing name; a name
  `store.file_path_for` refuses is passed over; staged then `os.replace`d.
  **The naming and placing steps are one function shared with
  `photographs.add`, not a copy.**

### 4.3 The Store

```python
# src/pressless/store.py — added
FILES_FOLDER = "files"
def file_path_for(folder: Path, name: str) -> Path: ...
def list_files(folder: Path) -> tuple[str, ...]: ...
```

`file_path_for` refuses the names `photograph_path_for` refuses, by the
same check, and returns `folder / FILES_FOLDER / name`. `list_files`
returns whole names, sorted, passing over a refused one with a notice, as
`list_photographs` does. **`FILES_FOLDER` joins `_BINNABLE`.** It does not
join `_SITE_FOLDERS`. Undo never touches it: like photographs, the folder
sits outside `content/`.

### 4.4 The Face

- **`face._FILE_TYPES`** holds § 4.1's suffixes and types.
  `FILES_POLICY` is unchanged: audio and video fall under its
  `default-src 'self'`.
- **`files_screen.register`** adds:

  | Route | Does |
  |---|---|
  | `GET /files` | lists each kept file: its name, its size, the pages naming it, and a *Remove* button |
  | `POST /file?name=…` | the body is the file; `files.add` under `editor.LOCK`; answers `{"name", "notices"}` as `editor._photograph` does |
  | `POST /files/remove` | form field `name`; refused with a sentence naming the pages where any page names it; else `store.move_to_bin(file_path_for(...))` |
  | files at `/preview/files/` | `face.add_files(..., lambda n: store.file_path_for(folder, n))` |

- **The header** carries a *Files* link beside *Look*.
- **Its words** live in the words table, and `NotAllowed` and `TooLarge`
  join `editor.SENTENCES`. The module joins `tests/test_words.py`'s
  `_served` and `_pages`.

### 4.5 The side panel

In `page_editor._panel`, the video (`src`, not `youtube`), music and
download sections gain what the picture section has: a list of kept files
of § 4.1's *Chosen by* column and an *Upload a file* button whose input
takes `files.ACCEPT[kind]`. A chosen file over `FILE_LARGEST` is refused
in the browser with the limit, before it is sent; otherwise the button posts
to `/file`. A chosen file's
address is `builder.web_file(name)`, with `../` before it on a page in
`pages/`. The typed address stays.

### 4.6 The Builder

```python
# src/pressless/builder.py — added
ROOT_OUTPUT = (..., "files")
def web_file(name: str) -> str: ...   # "files/" + quote(name, safe="")
def files_named(folder: Path) -> dict[str, tuple[str, ...]]: ...  # name -> pages naming it
```

- **What a page names** is every section's `src` or `href` that, read from
  the page's place as `_held_pictures` reads one, is `files/<name>` for a
  name `store.list_files` holds. Photographs are collected from `picture` and
  `enlarge` sections' `src`. The two share one address reader. **Both also take
  each held file named by any `href`, `src`, `srcset`, `poster` or CSS `url(...)`
  in a page, a furniture file or the style code (PRESS-0210 § 4.13).**
- **Building the site folder**, each named file is copied byte for byte to
  `files/<name>`, once. A name beginning with a dot, a file over
  `FILE_LARGEST`, or one `file_allowed` refuses is `BuildStopped`, naming
  the file.
- **`files_named`** reads the header, the footer and every fixed page, each
  both published and waiting (`store.WAITING_FOLDERS`), so a page still being
  edited keeps its files. `/files` and its removal use it; the build reads
  the published copies alone.

### 4.7 A repository's own `files` folder

With `files` in `ROOT_OUTPUT`, a new setup does not keep a repository's own
`files` folder, and a publish replaces what it holds. That is what happens
to a repository's own `pages` folder today (PRESS-0021). An install set up
before this may have `files` on its saved list, and two rules keep that
folder safe:

- **Publishing refuses.** `publishing.publish`, before it calls
  `publisher.publish`, raises `KeptFolderBuilt` where the built site folder
  holds a first segment that is both in `ROOT_OUTPUT` and on the saved
  `untouchable` list, compared with casefold. Its sentence names that
  segment and says to move that folder on GitHub, then save the Settings
  page again. `publisher.publish` is unchanged (PRESS-0009 § 4.4).
- **Saving Settings keeps a kept entry.** `setup.untouchable(root, kept=())`
  also keeps each entry of `kept` that `root` still holds. The Settings page
  passes its saved list; the first-run wizard passes none. So a save made
  before the folder is moved keeps the protection, and the refusal keeps
  firing.

## 5. Invariants

- **INV-1** — `files.add` keeps each § 4.1 kind given its suffix and
  matching bytes, and raises `NotAllowed`, writing nothing, for a `.pdf`
  holding `<html>`, a `.html`, a `.svg`, a `.docx` holding ZIP bytes, and a
  `.txt` holding a NUL or bytes that are not UTF-8. *Test:*
  `tests/test_files.py::test_only_the_listed_kinds_are_kept`.
  *Breaks when:* a suffix outside § 4.1 is kept, or bytes not of their
  suffix's kind are.
- **INV-2** — A body of `FILE_LARGEST + 1` bytes raises `TooLarge` and
  writes nothing; one of `FILE_LARGEST` bytes is kept. *Test:*
  `tests/test_files.py::test_a_file_over_the_limit_is_refused`.
  *Breaks when:* the check is off by one, or runs after the write.
- **INV-3** — `files.add` names as `photographs.add` does: `My Song.MP3`
  becomes `my-song.mp3`, a second different file under that name takes
  `my-song-2.mp3`, and identical bytes return `my-song.mp3`.
  *Test:* `tests/test_files.py::test_names_follow_the_photograph_rule`.
  *Breaks when:* the two modules name differently.
- **INV-4** — `file_path_for` refuses every name `photograph_path_for`
  refuses, and `move_to_bin` moves `files/a.pdf` to the bin. *Test:*
  `tests/test_store_extras.py::test_files_are_named_and_binned_like_writing`.
  *Breaks when:* a refused name is accepted, or `FILES_FOLDER` is not in
  `_BINNABLE`.
- **INV-5** — `GET /preview/files/a.mp3` answers `audio/mpeg` with
  `FILES_POLICY` and `nosniff`; `a.txt` answers `text/plain;
  charset=utf-8`; a name the Store refuses answers 404. *Test:*
  `tests/test_files_screen.py::test_kept_files_are_served_under_the_policy`.
  *Breaks when:* a kind is served as another type, or without the policy.
- **INV-6** — A fixed page whose music section names a kept
  `files/a.mp3` builds a site folder holding `files/a.mp3` equal to the
  Store's bytes; a kept file no page names is not in it; a named file whose
  bytes no longer pass `file_allowed` stops the build. *Test:*
  `tests/test_builder.py::test_named_files_are_published_byte_for_byte`.
  *Breaks when:* an unnamed file is published, a named one is altered, or
  a changed one is published.
- **INV-7** — `setup.untouchable(("files", "CNAME"))` is `("CNAME",)`.
  With `kept=("files",)` it is `("CNAME", "files")`; with
  `kept=("files",)` over a root of `("CNAME",)` it is `("CNAME",)`.
  *Test:* `tests/test_setup.py::test_files_is_builder_output`.
  *Breaks when:* `"files"` is not in `ROOT_OUTPUT`, a kept entry the root
  still holds is dropped, or one it no longer holds is kept.
- **INV-8** — With the saved `untouchable` holding `Files` and the built
  site folder holding `files/a.pdf`, `publishing.publish` raises
  `KeptFolderBuilt` naming `Files`, and `publisher.publish` is not called.
  With `untouchable` holding only `CNAME`, it publishes as before. *Test:*
  `tests/test_publishing.py::test_a_kept_folder_the_build_fills_stops_the_publish`.
  *Breaks when:* the file is dropped silently, or the Publisher is
  reached.
- **INV-9** — `POST /files/remove` for a file no page names moves it to the
  bin; for one a page names it answers a sentence naming that page and the
  file stays, a page named only by its waiting copy included. `GET /files`
  lists both, with sizes. *Test:*
  `tests/test_files_screen.py::test_removal_is_refused_while_a_page_names_the_file`.
  *Breaks when:* a named file is removed, a waiting page is not read, or
  an unnamed file is not removed.
- **INV-10** — The side panel of a music section lists only music kinds of
  the kept files; a video section only video kinds; a download section
  every kept file. A file uploaded from the panel of a page in `pages/`
  sets the field to `../files/<name>`. *Test:*
  `tests/test_page_editor.py::test_the_panel_offers_kept_files_by_kind`,
  and a row in `scripts/by-hand-browser-checks.py` for the upload.
  *Breaks when:* a section lists another kind, or the address lacks `../`.

The preview frame keeps `sandbox="allow-same-origin"` without
`allow-scripts`, and `FILES_POLICY` is unchanged; the existing
`tests/test_face.py` checks of both stand.

## 6. Failure modes

- **An upload over 50 MiB** is refused in the browser (§ 4.5). One sent
  anyway meets `TooLarge`, or the Face's 413 above `face._MAX_BODY`.
- **Seeking in the preview.** The Face answers whole files with no range
  support (`_send_file`), so a long video may not seek there. The
  published site is served by GitHub.
- **A large publish holds every changed file in memory**, base64 included
  (PRESS-0088). A 50 MiB file adds several times that while it is sent.
- **A site past GitHub Pages' size.** "Published GitHub Pages sites may be
  no larger than 1 GB." Source:
  https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
  Pressless does not count it; GitHub's refusal reaches the writer as a
  publish failure.
- **Imported attachments** already sit in `photographs/` (PRESS-0007
  § 4.5), videos and PDFs included. They stay there, unpublished, until an
  item moves them.

## 7. Tests

`tests/test_files.py` (new) gains INV-1, INV-2 and INV-3;
`tests/test_store_extras.py` INV-4; `tests/test_files_screen.py` (new)
INV-5 and INV-9; `tests/test_builder.py` INV-6; `tests/test_setup.py`
INV-7; `tests/test_publishing.py` INV-8; `tests/test_page_editor.py` and
`scripts/by-hand-browser-checks.py` INV-10. Fixtures use short made-up
bytes behind each signature, never real media. Each test is seen failing
against the code before this item, then mutation-probed once it lands.

## 8. Alternatives considered (and rejected)

- **Any file, served only as a download.** Rejected by the user (§ 3
  decision 1).
- **Keeping files in `photographs/`.** Rejected: every reader of that
  folder assumes Pillow can open what it holds.
- **Replacing a wrong suffix, as photographs do.** Rejected (§ 3
  decision 4).
- **Letting removal break the page.** Rejected (§ 3 decision 7).
- **Range requests in the Face.** Rejected for now: the preview plays a
  file from the start without them, and `_send_file` is shared by every
  file the Face serves.

## 9. Out of scope

- Removing photographs, or listing them on the Files screen — deferred;
  not yet queued.
- Moving imported non-picture attachments out of `photographs/` —
  deferred; not yet queued.
- A link to a file from inside a paragraph's text — deferred; not yet
  queued.
- The site icon and the sharing picture — PRESS-0227.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_files.py::test_only_the_listed_kinds_are_kept` |
| INV-2 | `tests/test_files.py::test_a_file_over_the_limit_is_refused` |
| INV-3 | `tests/test_files.py::test_names_follow_the_photograph_rule` |
| INV-4 | `tests/test_store_extras.py::test_files_are_named_and_binned_like_writing` |
| INV-5 | `tests/test_files_screen.py::test_kept_files_are_served_under_the_policy` |
| INV-6 | `tests/test_builder.py::test_named_files_are_published_byte_for_byte` |
| INV-7 | `tests/test_setup.py::test_files_is_builder_output` |
| INV-8 | `tests/test_publishing.py::test_a_kept_folder_the_build_fills_stops_the_publish` |
| INV-9 | `tests/test_files_screen.py::test_removal_is_refused_while_a_page_names_the_file` |
| INV-10 | `tests/test_page_editor.py::test_the_panel_offers_kept_files_by_kind`; `scripts/by-hand-browser-checks.py` |
| § 4.4 the screen's words | `tests/test_words.py` |
| § 6 seeking in the preview | **nothing** — a limit, not a defect |

## 11. Cross-doc impact

Each edit below is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0006-pages-furniture-comments.md` § 4.1 — the Store
  gains `files/`, `file_path_for` and `list_files`.
- `docs/specs/PRESS-0005-store.md` § 4.1 — `move_to_bin` takes `files/`.
- `docs/specs/PRESS-0008-builder.md` § 4.1 — `ROOT_OUTPUT` gains `files`;
  named files are copied byte for byte.
- `docs/specs/PRESS-0013-publish.md` § 4.3 — `KeptFolderBuilt` before the
  Publisher is called.
- `docs/specs/PRESS-0021-setup.md` § 3 decision 3 and `untouchable` — a
  save keeps a kept entry the repository still holds.
- `docs/specs/PRESS-0012-editor.md` § 4.3 — the type table gains § 4.1's
  rows.
- `docs/specs/PRESS-0260-visual-editor.md` § 3 decision 6 and § 4.6 — the
  three sections choose kept files.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0197-upload-any-file-loop-log.md`.
