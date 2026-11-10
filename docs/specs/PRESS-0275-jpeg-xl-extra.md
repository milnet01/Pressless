<!-- ants-spec-format: 1 -->
# PRESS-0275 — JPEG XL photographs, through a decoder downloaded once and checked before every use

**Status:** accepted (2026-11-10), implemented. Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0275 (split from PRESS-0274 by the user's
2026-10-15 choice; plugin route decided by the user 2026-10-22).

**Builds on:** PRESS-0023 (`updater.download`, its TLS and its size and hash
checks), PRESS-0008 § 4.6 (the web copy). **Changes:** PRESS-0008 § 4.6
step 3 and INV-11's allowlist, PRESS-0260 § 4.6's "serves the Store's
originals", PRESS-0223's names table.

Layman: a writer can add photographs saved as JPEG XL. The first time, one
click downloads a small decoder made by the JPEG XL project. Pressless checks
it is the exact file it expects every time it uses it. The site gets a WebP
copy every browser shows.

## 1. Goal

After this ships, a `.jxl` photograph can be added in both upload boxes,
shown in the editor and the preview, and published as a WebP web copy. The
decoding is done by libjxl's own `djxl` program. Pressless downloads it on
the writer's click, from a release on Pressless's GitHub page. It runs it
only while its SHA-256 equals one compiled into Pressless. Without the
decoder, a JPEG XL photograph is refused with a sentence saying how to add
it.

## 2. Problem

1. **Pillow 13.0.0 reads no JPEG XL.** `builder.photograph_format` opens
   every photograph with `Image.open`, so a `.jxl` returns `None` and
   `photographs.add` raises `NotAPhotograph`.
2. **The Python readers cannot ship inside Pressless.** `pillow-jxl-plugin`
   is GPL-3.0-or-later. The BSD readers need numpy, roughly doubling the
   Windows zip (PRESS-0274's measurements). The user decided on 2026-10-22
   that JPEG XL is a separate download.
3. **Running downloaded code is the risk.** A decoder fetched from an
   address is run when someone else controls that address. PRESS-0023 met
   the same problem and answered it with a check on the bytes.
4. **libjxl's own archives cannot be unpacked by the standard library on
   Windows.** `jxl-x64-windows-static.zip` (libjxl v0.12.0) stores its
   members with Deflate64, compress type 9. `zipfile` raises
   `NotImplementedError: That compression method is not supported`
   (measured 2026-11-10). The `.7z` forms need a 7-Zip reader. The Linux
   `.tar.lz` does unpack with `lzma`'s raw LZMA1 filter, measured the same
   day.
5. **Browsers mostly do not show JPEG XL.** The editor and the preview serve
   the Store's originals by name (`editor.photo_src`, the
   `PREVIEW_ADDRESS + "photographs/"` route), so an original `.jxl` would
   show as a broken picture.

## 3. Scope decisions (agreed with the user)

1. **JPEG XL is a separate download, not part of Pressless.** Decided by the
   user 2026-10-22.
2. **(decided here) The decoder is libjxl's `djxl` program, run as its own
   process, not a Python module loaded into Pressless.** It needs no match
   with the bundled Python, a crash in it cannot take Pressless down, and its
   licence is BSD-3-Clause (`gh api repos/libjxl/libjxl/license`). § 8 has
   the in-process alternative.
3. **(decided here) Pressless's own GitHub page hosts the two programs, on a
   release of their own.** The writer's machine then downloads one plain
   file and unpacks nothing (Problem 4). libjxl's licence permits
   redistribution with its notice, and the release carries the notice.
4. **(decided here) The check is a SHA-256 compiled into Pressless, not a
   signature.** Pressless is itself signed (PRESS-0023), so a hash inside it
   is as trusted as the program. No key is added.
5. **(decided here) The web copy of a JPEG XL photograph is WebP.** Every
   browser shows it, and Pillow already writes it for WebP originals.
6. **(decided here) Only the first frame of an animated JPEG XL is used**,
   as the Builder already does for an animated PNG.
7. **(decided here) The decoder is fetched only on the writer's click.**
   Nothing downloads it on its own.

## 4. Design

### 4.1 The parts

Two new modules. `src/pressless/jpegxl.py` imports only `paths` and the
standard library, so the Builder may import it: PRESS-0008 INV-11's
allowlist gains `pressless.jpegxl`, with `contextlib` and `tempfile` for
`open_original`. `src/pressless/jpegxl_screen.py` is the
Face side, as `updating.py` is the Updater's: it imports `updater`, `jpegxl`
and the Face, holds `install` and the § 4.6 line and route, and is imported
only by `__main__`.

```python
@dataclass(frozen=True)
class Pin:
    name: str        # the asset's file name, also the installed name
    size: int
    sha256: str      # 64 lowercase hex

RELEASE = "jpeg-xl-0.12.0"           # the tag on milnet01/Pressless
PINS = {
    "linux":   Pin("djxl-0.12.0-linux-x86_64", 4924448,
                   "67bdc98fdca7f93d7b77f3473e818b251ba107109ee83b3b37ccbd90066f2454"),
    "windows": Pin("djxl-0.12.0-windows-x64.exe", 4152832,
                   "6970ce73de51e046b39bd5f28fc7bc5da64e9f6505c11194319f43d8849d2bf4"),
}
FOLDER_NAME = "extras"               # in Pressless's own folder; a MACHINE_NAMES entry
DECODE_SECONDS = 120

class NotInstalled(Exception): ...   # no decoder, or one whose bytes are not the pin's
class Unreadable(OSError): ...       # no picture; caught where Pillow's errors are

def is_jpeg_xl(head: bytes) -> bool: ...
def installed(folder: Path, platform: str) -> Path | None: ...
def program() -> Path | None: ...    # installed(paths.own_folder(), this system)
def download_url(platform: str) -> str: ...  # the pin's asset on RELEASE
def decode(program: Path, original: Path, work: Path) -> Path: ...

# jpegxl_screen.py
def install(folder: Path, platform: str, transport=None) -> Path: ...
```

The pins are the bytes of `tools/djxl` in libjxl v0.12.0's
`jxl-linux-x86_64-static.tar.lz`, and of `x64-windows-static/bin/djxl.exe`
in its `jxl-x64-windows-static.zip`. Both archives matched the SHA-256
GitHub records for them. Both programs are statically linked; `file` reports
the Linux one as such.

### 4.2 Recognising a JPEG XL file

`is_jpeg_xl(head)` is true when `head` starts with `FF 0A` (a bare
codestream) or with `00 00 00 0C 4A 58 4C 20 0D 0A 87 0A` (the container).
The bytes decide, never the name, as PRESS-0008 § 4.6 step 3 decides for
every other format.

### 4.3 Installing

`installed(folder, platform)` returns `folder / FOLDER_NAME / PINS[platform].name`
when that file exists and its size and SHA-256 equal the pin. Otherwise it
returns `None`. It hashes the whole file on every call.

`install` builds an `updater.Offer` from the pin: version `RELEASE`, the URL
`download_url(platform)`, which is
`https://github.com/milnet01/Pressless/releases/download/<RELEASE>/<name>`,
and the pin's size and hash. It calls `updater.download(offer, beside)` with
`beside = folder / FOLDER_NAME`, created first. That call already streams
over the certifi context, refuses a non-https redirect, removes the file on
any failure and returns it only when size and hash match (PRESS-0023
§§ 4.5–4.6). `install` then sets mode `0o700` on Linux, and `os.replace`s
the file onto the pinned name. Any file in `extras/` not named by a pin is
left alone. A failure raises `updater.DownloadFailed`, `DiskFull` or
`UpdateRejected` as `download` does, and leaves no file behind.

**A Pressless release that moves the pin makes the old decoder "not
installed".** The line in § 4.6 then offers the download again.

### 4.4 Decoding

`decode(program, original, work)`:

1. Re-hashes `program` against the pin for this platform. A mismatch raises
   `NotInstalled` and nothing runs.
2. Runs, with no shell:

   ```python
   [str(program), str(original.resolve()), str(work / "decoded.png")]
   ```

   `work` is a fresh directory from `tempfile.mkdtemp()`, removed by the
   caller. Both paths are absolute, so neither can read as an option.
   stdin, stdout and stderr go to `DEVNULL`. The timeout is
   `DECODE_SECONDS`. On Windows, `creationflags` is `CREATE_NO_WINDOW`, read
   with `getattr(subprocess, ..., 0)`.
3. A non-zero exit, a timeout (the process is killed) or no
   `decoded.png` raises `Unreadable`. Nothing from the process's output
   reaches the log.
4. Returns `work / "decoded.png"`. The caller opens it with Pillow, so
   Pillow's own decompression-bomb limit applies as it does to any PNG.

### 4.5 Where photographs are read

**`builder.open_original(path)`**, a new context manager, is the one place
the Builder opens an original. For a JPEG XL file it decodes the file into a
work directory and yields the PNG opened by Pillow, with `format` reported as
`"JXL"`. For anything else it yields `Image.open(path)`. It raises
`jpegxl.NotInstalled` where `jpegxl.program()` is `None`. The three places that
call `Image.open` on an original use it: `photograph_format`, the web copy
and the site icon.

- **Taking one in.** `photograph_format` returns `"JXL"` for a JPEG XL file
  the decoder reads. `photographs.SUFFIXES` gains `"JXL": (".jxl",)`.
  `photographs.ACCEPT` gains `image/jxl,.jxl`; the suffix is there because
  a file picker may not know the type. `NotInstalled` reaches the upload
  route as its own failure: `editor._photograph` catches it, and `editor`
  registers `SENTENCES[jpegxl.NotInstalled]` with § 4.6's sentence, and
  `jpegxl.Unreadable` with `NotAPhotograph`'s. The route's reply carries
  `address`, `builder.web_photograph(name)`, which the page editor writes
  into a picture section. Import's two callers, in
  `pressless_import/_folder.py` and `_bring.py`, call
  `builder.is_photograph`, which counts a file raising `NotInstalled` as a
  photograph, so a site's `.jxl` originals are kept and its publish stops
  until the decoder is added.
- **Publishing.** PRESS-0008 § 4.6 step 3 gains JXL: the decoded picture is
  rotated, shrunk and stripped as a PNG is, and saved as WebP with Pillow's
  defaults and any ICC profile. The decoder is told nothing about
  orientation, and the decoded PNG passes through `ImageOps.exif_transpose`
  like every other format.
- **The published name.** `builder.web_name(name)` is `name + ".webp"` for a
  name ending `.jxl`, ignoring case, and `name` otherwise. `web_photograph`,
  the web copy's target and the `photographs=False` record all use it, so
  `seaside.jxl` publishes as `photographs/seaside.jxl.webp`. Where that name
  is also another photograph's own name, the build is `BuildStopped` naming
  both. A page's picture names the web copy, so `_held_pictures` reads the
  place `photographs/<n>.jxl.webp` as the original `<n>.jxl` where the Store
  holds it. A JPEG XL original whose name does not end `.jxl` is
  `BuildStopped`, naming it, and so is a `.jxl` name holding another
  format. So no web copy is published under another type's suffix.
- **No decoder at publish.** `NotInstalled` becomes `BuildStopped`, naming
  the photograph and the § 4.6 line.

### 4.6 What the writer sees

**One line under the list at `/`**, registered with `face.add_to_list(...,
above=False)` as the update switch is. It reads *JPEG XL photographs* with
one button. Before the decoder is installed: **Add JPEG XL support**, and the
size in MB. After: *ready*, and no button. The line keeps its place and
height in both states.

The button posts to `/jpeg-xl`. The route calls `install` and sends the
browser back to `/`, where the line is drawn again. Once installed, the
button is hidden but keeps its place. On a failure the line carries its own
sentence until the next try: no
connection, a full disk, and *the download was not the expected file, so it
was thrown away* for `UpdateRejected`. These three are not added to
`SENTENCES`, which is keyed by type and already holds the update's sentences
for them.

**A JPEG XL photograph added without the decoder** is refused with: *This is
a JPEG XL photograph. Add JPEG XL support from the list page first.*

### 4.7 The editor and the preview

The two photograph routes, `ORIGINALS_ADDRESS` and `PREVIEW_ADDRESS +
"photographs/"`, find a file through one function,
`editor.photograph_file(folder, name)`:

- a name ending `.jxl`, or `.jxl.webp`, whose `.jxl` original the Store
  holds → the **view copy** of that original;
- any other name → `store.photograph_path_for(folder, name)`, as today.

The view copy is `<site>/jpeg-xl-views/<name>.webp`, made by
`builder.webp_copy(original, target)`. It and the web copy re-encode
through one function, so the two match. It is remade when the original is newer than it. The Face
sends it as `image/webp` from its suffix, so PRESS-0012's Content-Type table
gains no row. `jpeg-xl-views` is `editor.VIEWS_FOLDER`. It joins `SITE_NAMES`
and `sitefile.LEFT_OUT`, being remade on demand as the preview is. The
Builder and the Publisher never read it. Where the decoder is missing, the
route answers 404, as it does for a missing original.

### 4.8 Publishing the two programs

`scripts/publish-jpeg-xl.py`, run by hand by the maintainer, as
`sign-release.py` is:

1. Downloads libjxl's two archives for the version in `RELEASE`, and
   requires each asset's GitHub `digest` to match a SHA-256 written in the
   script.
2. Extracts `tools/djxl` with `lzma` and `tarfile`, and
   `x64-windows-static/bin/djxl.exe` with `7z`. It requires each to match
   `jpegxl.PINS`, and refuses otherwise.
3. Creates the release `RELEASE` on `milnet01/Pressless` as a
   **pre-release, never the latest**. Its body says it is libjxl's decoder,
   for Pressless's JPEG XL support. It uploads the two programs under the
   pins' names, and each archive's licence files: the Linux archive's
   `LICENSE.*`, and the Windows archive's
   `x64-windows-static/licenses/LICENSE.*` with a `windows-` prefix. The
   Windows program links libraries, such as libjpeg-turbo and libwebp, whose
   notices only that archive carries.
4. Reads the asset list back and requires exactly those names.

**The release must exist before any Pressless carrying its pin is
published.** The pre-release mark keeps it away from the updater:
`/releases/latest` leaves pre-releases out (PRESS-0023 § 4.4 step 2).

## 5. Invariants

- **INV-1** — A decoder whose bytes differ from the pin is never run, and
  is reported as not installed. *Test:*
  `tests/test_jpegxl.py::test_a_changed_decoder_never_runs` — a stand-in
  program that writes a marker file, pinned, then one byte appended. Neither
  `installed` nor `decode` runs it, and no marker appears.
  *Breaks when:* `decode` trusts `installed`'s earlier answer, or compares
  the size alone.
- **INV-2** — `install` keeps nothing whose size or hash is not the pin's.
  It never writes outside `extras/`, and never under a name other than the
  pin's. *Test:* `tests/test_jpegxl.py::test_install_rows` — a transport
  double serving the right bytes, one byte changed and one byte short. Only
  the first leaves a file, and `extras/` then holds exactly the pin's name.
  A spy on `updater.download` sees every row reach it. *Breaks when:* the file is renamed onto the pin's
  name before the hash is compared, or `install` re-implements the download
  instead of calling `updater.download`.
- **INV-3** — The decoder runs with no shell, with absolute paths, a
  timeout, and no output kept. *Test:*
  `tests/test_jpegxl.py::test_decode_runs_one_fixed_command` — the argv
  recorded by a stand-in equals § 4.4's list. A stand-in that sleeps past a
  shortened timeout raises `Unreadable` and leaves no process behind. The
  last half runs on Linux only: on Windows the stand-in is a batch file, and
  the kill does not reach the Python it starts.
  *Breaks when:* `shell=True`, a relative path, or a missing timeout.
- **INV-4** — A JPEG XL file is recognised by its bytes alone. *Test:*
  `tests/test_jpegxl.py::test_recognised_by_bytes` — both signatures named
  `photo.png` are recognised; a PNG named `photo.jxl` is not.
  *Breaks when:* the suffix is consulted.
- **INV-5** — A JPEG XL original is never published as itself. Its web copy
  is WebP, at `web_name(name)`, with no EXIF or XMP. *Test:*
  `tests/test_builder.py::test_jpeg_xl_publishes_as_webp` — with the
  stand-in decoder, the built site holds `photographs/seaside.jxl.webp`,
  which Pillow opens as `WEBP` with no `exif`. It holds no
  `photographs/seaside.jxl`. The page's `src` names the `.webp`.
  *Breaks when:* the JXL branch falls through to step 5's copy or to a PNG
  save.
- **INV-6** — Without the decoder, a JPEG XL photograph is refused when
  added and stops a publish, each with its own sentence. *Test:*
  `tests/test_photographs.py::test_jpeg_xl_without_the_extra` and
  `tests/test_builder.py::test_jpeg_xl_without_the_extra_stops`.
  *Breaks when:* `NotInstalled` is caught as an unreadable picture, which
  would tell the writer the file is broken.
- **INV-7** — The editor and preview serve a JPEG XL original only as its
  WebP view copy. *Test:* `tests/test_editor.py::test_jpeg_xl_view_copy` —
  a GET of the original's address and of its `.jxl.webp` address both
  answer `image/webp`, and neither body starts with a JPEG XL signature.
  *Breaks when:* a route reaches `store.photograph_path_for` for a `.jxl`
  name.
- **INV-8** — The two programs' release is a pre-release, so the updater
  never offers it. *Test:* `tests/test_publish_jpeg_xl.py` — the script's
  `gh release create` argv carries `--prerelease` and `--latest=false`.
  *Breaks when:* either flag is dropped. The updater would then read
  `jpeg-xl-0.12.0` as the latest release and stop offering updates, its tag
  never parsing as a version.
- **INV-9** — The pins decode real JPEG XL. *Test:*
  `tests/test_jpegxl_real.py`, skipped unless `PRESSLESS_DJXL` names a file
  matching this platform's pin. It decodes the fixtures in `tests/jxl/`,
  made once by `scripts/make-jxl-fixtures.py` with `cjxl` — a lossy
  still, a JPEG recompressed with EXIF orientation 6, and an animation —
  and checks size, upright orientation and first frame. Run on Linux and on
  the Windows box before shipping. *Breaks when:* a pin names a build that
  cannot run on that system, or the decoder's output differs from what
  § 4.5 assumes.

## 6. Failure modes

| What happens | What the writer sees |
|---|---|
| No connection, or GitHub fails, during install | The line's no-connection sentence; nothing kept |
| Disk full during install | The full-disk sentence (`DiskFull`) |
| The download's bytes are not the pin's | *Not the expected file, thrown away*; nothing kept |
| The installed decoder is changed or damaged on disk | The line offers the download again; nothing runs |
| A Pressless update moves the pin | The same |
| The decoder crashes, fails or runs past `DECODE_SECONDS` | *Could not be read as a picture*, today's sentence |
| The decoder writes its animation as numbered files, not `decoded.png` | INV-9's animation fixture fails before shipping, and § 4.4 is amended to read the first file, keeping decision 6 |
| The decoded picture is past Pillow's pixel limit | The same, as for any picture today |
| A site holding `.jxl` photographs is opened on a machine without the decoder | Previews show no picture (404); a publish stops with § 4.5's sentence |
| An antivirus program blocks the decoder on Windows | *Could not be read as a picture*; the hand check in § 7 looks for it |
| The pinned release is deleted from GitHub | Install fails with the no-connection sentence. Restoring it with the same bytes repairs it; nothing else can |

**Between the hash check and the run, the file could be swapped.** Doing so
needs write access to Pressless's own folder, which already allows replacing
Pressless itself. It is stated, not defended.

## 7. Tests

The suite uses a **stand-in decoder**: a small program, written by the test,
that copies a PNG fixture to its second argument. Its hash replaces the pin
through `monkeypatch`. INV-1, INV-2, INV-3, INV-4, INV-5, INV-6 and INV-7
run everywhere, the Windows box included. INV-8 runs the script with `gh`
replaced.

INV-9 needs the real programs. Before shipping, the maintainer runs it on
Linux and on the Windows box. They also click **Add JPEG XL support** in a
packaged build on each system, add the three fixtures, and publish to a
scratch site.

Each test is seen to fail before the code it locks exists.

## 8. Alternatives considered (and rejected)

- **A Python reader loaded into Pressless** (`pillow-jxl-plugin`,
  `imagecodecs`). It must match the bundled Python exactly on each system.
  Loading it gives a third party's code all of Pressless's rights, and a
  crash in it ends Pressless. `pillow-jxl-plugin` is also GPL-3.0.
- **Downloading libjxl's own archives on the writer's machine.** The
  Windows zip needs Deflate64 (Problem 4), so it would need a decompressor
  in Pressless. It is also 40 MB for one 4 MB program.
- **Signing the programs with the update key.** It adds a signed list and
  a step per libjxl version. A hash inside the already-signed Pressless
  gives the same assurance.
- **Publishing the web copy as AVIF.** Pillow's AVIF encoder is slower, and
  WebP is shown by every browser Pressless targets.
- **Keeping the `.jxl` name for WebP bytes.** GitHub Pages sends a
  `Content-Type` from the suffix, and a `.jxl` sent as `image/jxl` holding
  WebP depends on each browser sniffing it.

## 9. Out of scope

- Publishing JPEG XL itself, for browsers that show it — deferred; not yet
  queued.
- Every frame of an animated JPEG XL — deferred; not yet queued.
- Decoders for other systems (Linux on ARM, 32-bit Windows) — Pressless
  ships for neither (PRESS-0022).
- Removing the decoder from inside Pressless — deleting `extras/` does it.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_jpegxl.py::test_a_changed_decoder_never_runs` |
| INV-2 | `tests/test_jpegxl.py::test_install_rows` |
| INV-3 | `tests/test_jpegxl.py::test_decode_runs_one_fixed_command` |
| INV-4 | `tests/test_jpegxl.py::test_recognised_by_bytes` |
| INV-5 | `tests/test_builder.py::test_jpeg_xl_publishes_as_webp` |
| INV-6 | `tests/test_photographs.py::test_jpeg_xl_without_the_extra`, `tests/test_builder.py::test_jpeg_xl_without_the_extra_stops` |
| INV-7 | `tests/test_editor.py::test_jpeg_xl_view_copy` |
| INV-8 | `tests/test_publish_jpeg_xl.py` |
| INV-9 | Partial: `tests/test_jpegxl_real.py`, which CI skips; a hand run on each system before a release |
| The release exists before a Pressless pinning it ships (§ 4.8) | **nothing** — the INV-9 hand run fails without it |
| No network module in `jpegxl.py` | PRESS-0262 INV-9's `tests/test_network_confined.py` |
| `extras` and `jpeg-xl-views` are named once | PRESS-0223 INV-2's `tests/test_sites.py::test_every_name_is_on_one_side` |

## 11. Cross-doc impact

- PRESS-0008 § 4.6 step 3: JXL is decoded by the extra and published as WebP.
  INV-11's allowlist: `pressless.jpegxl`, `contextlib`, `tempfile`.
- PRESS-0224 § 4.1: `jpeg-xl-views` is left out of a saved site.
- PRESS-0260 § 4.6 and `editor.register`'s comment: a JPEG XL original is
  served as its view copy.
- PRESS-0223's names table: `jpegxl.FOLDER_NAME` (machine) and
  `jpeg-xl-views` (site).
- `docs/design.md` § The parts: `jpegxl.py` and `jpegxl_screen.py`.
- `docs/working-here.md` *Releasing*: a new libjxl version means running
  `scripts/publish-jpeg-xl.py` before the Pressless release that pins it.
- README and `failure.photographs.NotAPhotograph.next`: JPEG XL in the
  photograph formats; CHANGELOG.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0275-jpeg-xl-extra-loop-log.md`.

## 13. Resource cost

About 5 MB on disk once the decoder is installed. One view copy per JPEG XL
photograph per site, no larger than the web copy. The decoded PNG in the
work directory is deleted after each use. No new Python dependency.

## 14. Open questions

- **Running libjxl's programs on this machine needs the user's permission.**
  The session that drafted this was refused running them. INV-9, and making
  the fixtures with `cjxl`, need it.
