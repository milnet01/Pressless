# PRESS-0023 — Pressless updates itself, and installs nothing it cannot prove we signed

**Status:** spec draft (2026-09-25).
**Kind:** feature.
**Source:** ROADMAP PRESS-0023 (user-request-2026-08-25; finbreak's
updater lessons, FIBR-*).

**Blocked by:** PRESS-0022 — shipped.

Layman: when a new version of Pressless is out, the list page says so and
offers to install it. One click downloads it, checks it really came from us,
puts it in place of the old program and opens Pressless again. His writing
never moves.

## 1. Goal

After this ships, a packaged Pressless looks for a newer release each time it
starts, unless he has turned that off. It offers **Update now**, **Later** and
**Skip this version**. Update now installs only a download whose signature
verifies against a key compiled into the program, then restarts Pressless.
Nothing in Pressless's own folder is touched.

The move to the first version carrying this is still a download by hand. Every
move after it is not.

## 2. Problem

1. **A fix cannot reach him.** Every release so far is a manual download. He is
   not technical, and he will not go looking.
2. **An updater is a way to run someone else's code on his machine.** A
   download that is installed because it arrived from the right address is
   installed when someone else controls that address.
3. **A signature proves bytes, not a version.** finbreak signs each file
   (`update.py::download_and_verify` in the sibling project) and leaves open
   whether an older signed file can be served as new (FIBR-0169).
4. **The two artefacts differ in shape.** Linux is one AppImage file; Windows is
   the `Pressless/` folder beside `Start Pressless.bat`
   (`docs/specs/PRESS-0022-packaging.md` § 4.1). A running Windows program
   cannot be replaced while it runs.
5. **The released Linux build cannot verify a certificate on this machine.**
   The v0.1.2 AppImage bundles an OpenSSL whose `OPENSSLDIR` is
   `/usr/lib/ssl` (read with `strings` over the bundle's `libcrypto.so.3`),
   and openSUSE has no such directory. finbreak shipped this bug and fixed it
   with the `certifi` bundle (`update_fetch.py::_ssl_context` there). The
   Publisher and Insights share it; § 9 says where that goes.
6. **Nothing stops two Pressless processes serving one folder.** The editor's
   lock is a `threading.Lock` (`editor.LOCK`), so it guards one process only.
   A restart racing a manual start is how finbreak met this (FIBR-0189).
7. **The program does not know its own version.** `src/pressless/__init__.py`
   is empty. The version lives in `pyproject.toml` only, which is not in the
   bundle.

## 3. Scope decisions (agreed with the user)

1. **Looking for updates is on by default, and he can turn it off.** Decided by
   the user 2026-09-25. finbreak's is off; its user is technical and this one
   is not, so off would mean a fix never reaches him.
2. **The offer is Update now, Later, and Skip this version.** Decided by the
   user 2026-09-25, following finbreak. Later hides the offer until Pressless
   next starts. Skip hides that one version for good; a newer one is offered.
3. **(decided here) One signed list per release, not one signature per file.**
   The list names the version and each artefact's size and SHA-256. Signing the
   version is what stops an old release being served as new (Problem 3), and
   one list covers the Windows zip without a per-file manifest inside it.
4. **(decided here) A key change is shipped before it is used.** The program
   trusts every key in a short list. A new key goes into a release signed with
   the old one. From then on every release is signed with both keys until the
   maintainer drops the old one, so a copy that missed or skipped the release
   carrying the new key still verifies the next. **A
   lost private key cannot be recovered from**: each installed copy must then
   be updated by hand once. That is stated, not solved.
5. **(decided here) CI never signs.** CI builds a draft release. The maintainer
   signs it on his own machine and publishes it (§ 4.8). A draft is invisible
   to the updater, so an unsigned release is never offered.
6. **(decided here) The switch sits on the list page at `/`.** The only page
   that edits settings is setup's (`setup.register`), and it is a first-run
   form. The switch is one line under the list.
7. **(decided here) The Linux file keeps its name.** The swap replaces the
   bytes of the AppImage he started, whose name carries the old version. A
   rename would break any shortcut he made to it.

## 4. Design

### 4.1 The parts, and what each may touch

A new part, **the Updater**, joins `docs/design.md` § The parts:

| Module | Job | May not |
|---|---|---|
| `src/pressless/updater.py` | Ask GitHub for the latest release, prove its signed list, download an artefact and check it against the list. Read and write `updates.json`. | Open the Store, Settings or Credentials; call Marks, the Builder or the Face |
| `src/pressless/update_key.py` | Hold `TRUSTED`, a tuple of base64 strings, each a raw 32-byte Ed25519 public key, decoded where a signature is checked. | Import anything of Pressless's |
| `src/pressless/installer.py` | Put a checked artefact in place of the running one and start the new one. Define `UpdateError` and `InstallFailed`. | Import a network module, or `updater` |
| `src/pressless/updating.py` | The Face side: start the check, show the offer and the switch, run Update now. | Be imported by any part but `__main__` |

**Network modules stay in three files: `publisher.py`, `insights.py` and
`updater.py`.** "Network module" is the set `tests/test_network_timeouts.py`
already names in `_NETWORK_MODULES`.

The GitHub repository is a constant in `updater.py`, `REPOSITORY =
"milnet01/Pressless"`. It is the app's repository, not his site's.
`PRESSLESS_UPDATE_REPOSITORY` replaces it for one run, which is how § 7.1
points a packaged build at a scratch repository. It moves nothing that trust
rests on: a release there is offered only if `TRUSTED` verifies it.

Two runtime dependencies are added: `cryptography`, for Ed25519, and `certifi`,
for Problem 5. Each gets a floor and a reason in `pyproject.toml`, as `keyring`
and `Pillow` do.

### 4.2 The version

`src/pressless/__init__.py` gains `__version__ = "<X.Y.Z>"`, equal to
`pyproject.toml`'s `version`. A version is three dot-separated parts, each one
or more ASCII digits, with an optional leading `v` on a tag:

```python
def parse_version(text: str) -> tuple[int, int, int] | None: ...
```

Anything else parses to `None`, and `None` is never offered. `int()` is not the
guard: it accepts `"1_0"` and `" 1"` (finbreak D13).

### 4.3 The signed list

Every release carries two extra assets: `Pressless-<X.Y.Z>-release.txt` and
`Pressless-<X.Y.Z>-release.txt.sig`. The list is ASCII, LF line endings, one
trailing LF, and exactly these lines in this order:

```
pressless-release 1
version <X.Y.Z>
linux Pressless-<X.Y.Z>-x86_64.AppImage <size in bytes> <sha256, 64 lowercase hex>
windows Pressless-<X.Y.Z>-windows.zip <size in bytes> <sha256, 64 lowercase hex>
```

The `.sig` holds one to four raw 64-byte Ed25519 signatures over the list's
exact bytes, concatenated. It verifies if any one of them verifies against any
key in `update_key.TRUSTED`. A list that differs
from this shape in any byte is refused whole.

### 4.4 The check

```python
@dataclass(frozen=True)
class Offer:
    version: str      # "X.Y.Z"
    asset_url: str    # https, the platform's artefact
    size: int         # from the signed list
    sha256: str       # from the signed list

def check(folder: Path, running: str, platform: str,
          transport: Transport = _Urllib()) -> Offer | Miss: ...

@dataclass(frozen=True)
class Miss:
    step: int         # the step of the list below that failed
```

`platform` is `"linux"` or `"windows"`. `Transport` is `updater.py`'s own.
`publisher.Transport` returns a whole body, and every read here is bounded or
chunked:

```python
class Transport(Protocol):
    def open(self, url: str) -> Response: ...  # redirects followed under § 4.5

class Response(Protocol):
    status: int
    headers: dict[str, str]
    def read(self, n: int) -> bytes: ...  # at most n bytes; b"" at the end
    def close(self) -> None: ...
```

Tests hand in a double that answers by URL. Steps, and the first that fails
returns `Miss(step)` with its number:

1. `updates.json` says the check is off. No request is made.
2. GET `https://api.github.com/repos/<REPOSITORY>/releases/latest`, read up to
   256 KiB. That endpoint leaves out drafts and pre-releases.
3. The tag parses, is greater than `running`, and is not the skipped version.
4. The release holds exactly one asset named for the list and one for its
   `.sig`, and one for this platform's artefact, each with an https
   `browser_download_url`.
5. Download the list (at most 16 KiB) and the `.sig` (64, 128, 192 or 256
   bytes).
6. The signature verifies (§ 4.3), and the list parses.
7. **The list's `version` equals the tag's.** A signed list for 0.1.2 behind a
   tag reading 0.1.9 is an old release served as new, and is refused.
8. The list's line for `platform` names the asset found in step 4, with a size
   no larger than 512 MiB.

**A failed check is silent.** Every exception is caught and becomes the
`Miss` of the step it happened in, and nothing is shown. For a `Miss` past
step 1, `updating` writes one line to the rolling log naming the step, never a
URL or a path.

**The check runs only in a packaged build.** Where `paths.artefact_path()`
raises `NotPackaged`, `updating` never calls `check`, and the switch reads
*"Updates are not available when Pressless is run this way."*

### 4.5 TLS and redirects

Every request uses a context built from `certifi.where()`, and an opener whose
redirect handler refuses any hop that is not https. Every open passes
`updater.TIMEOUT_SECONDS`, its own, as `publisher.py` and `insights.py` each
hold one — a timeout `tests/test_network_timeouts.py` already enforces for
all of `src/`. The handler is `updater.py`'s own; `publisher._NoCrossOriginAuth`
is the precedent, and the two are not shared, by design rule 7.

### 4.6 The download

```python
def download(offer: Offer, beside: Path, transport: Transport = _Urllib()) -> Path: ...
```

`beside` is the directory holding the artefact, so the swap is a rename on one
filesystem. The bytes stream to a new file there, created exclusively and
owner-only, named `.pressless-update-<random>`. SHA-256 is computed as each
chunk is written; nothing is read back.

| What happens | Raised | The file |
|---|---|---|
| `Content-Length` is present and is not `offer.size` | `DownloadFailed` | removed |
| The stream ends before `offer.size` bytes | `DownloadEndedEarly` (a `DownloadFailed`) | removed |
| More than `offer.size` bytes arrive | `UpdateRejected` | removed |
| The hash is not `offer.sha256` | `UpdateRejected` | removed |
| Any other error | `DownloadFailed` | removed |
| All checks pass | — | returned |

A short download is never reported as tampering (FIBR-0327).

**On Windows the checked zip is then unpacked** into a new folder beside
`Pressless/`, named `Pressless.new-<random>`. Every member must be
`Start Pressless.bat`, or `Pressless/` or a path under it — directory entries
included, which the build's `shutil.make_archive` writes — with no absolute path, no
`..` part and no drive letter; any other member raises `UpdateRejected` before
anything is written, and the zip and the folder are removed. The zip is removed
once unpacked.

### 4.7 Putting it in place

```python
def apply_linux(appimage: Path, staged: Path, folder: Path) -> None: ...
def apply_windows(program: Path, staged: Path, folder: Path) -> None: ...
```

Each raises `InstallFailed` where nothing has changed yet, and otherwise
returns: on Linux once `os.replace` has succeeded, whether or not the helper
then starts; on Windows once the helper is spawned. The caller then exits
(§ 4.9); nothing re-executes in place. `folder` is Pressless's own folder, where the helper
writes `update.log`.

**Linux.** `chmod 0o755` the staged file, then `os.replace` it over
`appimage`. A failure before the replace removes the staged file and raises
`InstallFailed`; the old file is untouched. Then spawn:

```python
["/bin/sh", "-c", WAITER, "sh", str(appimage), str(os.getpid()), str(log)]
```

Before the spawn, Python overwrites `update.log` with `swapped`. `WAITER` is a
constant: it appends `waiting` to `"$3"`, polls `kill -0 "$2"` every 0.1 s for
at most 60 s, appends `started`, then `exec "$1"`. A spawn that fails writes
`not started` and returns, because the new file is already in place. **The paths arrive as arguments and never appear in the
script text** (FIBR-0327). The environment drops `APPDIR`, `APPIMAGE` and
`ARGV0`, sets `PYINSTALLER_RESET_ENVIRONMENT=1`, and restores
`LD_LIBRARY_PATH` and `LD_PRELOAD` from their `_ORIG` copies, dropping each
where there is none (FIBR-0122). `start_new_session=True`, stdin, stdout and
stderr to `/dev/null`.

**Windows.** Spawn `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`
by absolute path, with `-NoProfile -NonInteractive -File` and a script written
beside the staged folder. The three paths arrive as the script's arguments. The
script:

1. Overwrites `update.log` with `waiting`, then waits until no process's image
   path lies under `program`, polling every
   200 ms for at most 60 s — **by image path, never by PID** (FIBR-0131). A
   process still there at 60 s: remove the staged folder, log `gave up`, start
   nothing.
2. Renames `program` to `Pressless.old`, then the staged `Pressless` folder to
   `program`, retrying each rename five times 500 ms apart.
3. If the second rename fails, renames `Pressless.old` back and logs
   `rolled back`. Otherwise it moves the staged `Start Pressless.bat` over the
   old one where the two differ — `cmd.exe` re-reads a running batch file
   from its old offset — and removes `Pressless.old`.
4. Starts `Start Pressless.bat` with the working directory set to its folder,
   then removes its own script file.

`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, read with `getattr(..., 0)` so
the module loads on Linux. A spawn that fails removes the staged folder and
raises `InstallFailed`.

**`update.log` is overwritten by each update, not appended**, so it stays one
update long. It holds fixed words only — `waiting`, `swapped`, `rolled back`,
`gave up`, `started`, `not started` — each after a timestamp. No path and no error text reach
it, because § Logging forbids a full path in anything Pressless writes down.

### 4.8 Signing a release

`scripts/make-signing-key.py <path>` writes a new Ed25519 private key to
`<path>`, owner-only, and prints only the public key, in `TRUSTED`'s base64
form. It refuses a
path that exists or lies inside the repository. The maintainer runs it once and
pastes the printed key into `update_key.TRUSTED`. **The private key never
enters the repository or a session's context.**

The release workflow creates the release as a **draft** (`gh release create
--draft`). Then `scripts/sign-release.py v<X.Y.Z>`, run by hand. It reads
`PRESSLESS_UPDATE_REPOSITORY` as `updater.py` does, so § 7.1's scratch
repository — a fork carrying the release workflow — is signed the same way:

1. Reads every key path from `git config --get-all ants.pressless.signingKey`.
2. Refuses unless the release is a draft and the release workflow run that
   built it was for the tag's own commit (FIBR-0318).
3. Downloads the two artefacts, writes the list (§ 4.3), and signs it with
   each key.
4. **Verifies every signature against `update_key.TRUSTED` as committed at
   the tag**, and refuses to attach anything if one fails.
5. Uploads the list and its `.sig`, reads the asset list back, and requires
   exactly the four names (FIBR-0275).
6. Publishes the draft.

### 4.9 What he sees

**`updating` reaches the page at `/` through a new
`Face.add_to_list(render, *, above)`**, where `render` returns HTML.
`editor._list` puts each registered piece above or below the list. The editor
never imports `updating`.

**The switch**, one line under the list at `/`: *"Pressless looks for a new
version each time it starts."* with **Stop looking**, or *"Pressless does not
look for new versions."* with **Look when Pressless starts**. It posts to
`/update/checking` and writes `updates.json`.

**The offer**, above the list at `/` once a check returns one: *"Pressless
<X.Y.Z> is ready to install. Your writing stays where it is."* with three
buttons, posting to `/update`, `/update/later` and `/update/skip`.

`updates.json` sits in Pressless's own folder:

```json
{"version": 1, "check": true, "skip": null}
```

A missing file reads as `check: true, skip: null`. So does a file that does not
parse or has another shape, and the switch then shows what is actually in force.

**The offer and a Later are held in memory for the life of the process.** That
is an exception to § State, which names none today — it calls the Insights
cache a cache rather than an exception. Nothing of his is
in them, and losing them costs one check at the next start. Skip is written to
`updates.json`.

**Update now**, in order:

1. Download, and on Windows unpack (§ 4.6), without the editor's lock. A failure
   shows its sentence (§ 4.10) and changes nothing.
2. Take `editor.LOCK`, waiting for any save or publish in flight. **It is never
   released on the success path**, so no write starts before the process ends.
3. Apply (§ 4.7) up to the spawn. A failure releases the lock and shows its
   sentence.
4. Answer with a page: *"Pressless is installing version <X.Y.Z> and will open
   again by itself in a moment. You can close this tab."* On Windows the
   console also prints *"Pressless is updating. You can close this window."*
5. Exit once the answer is sent. The new process opens a fresh tab as any start
   does.

### 4.10 Failures he can see

Each is a typed failure with a three-part sentence in `face.SENTENCES`:

| Type | What happened | His site | Next |
|---|---|---|---|
| `DownloadFailed` | Pressless could not download the new version. | not changed | Check your internet connection and click Update now again. |
| `DownloadEndedEarly` | The download stopped before it finished. | not changed | Click Update now again. |
| `UpdateRejected` | The download did not prove it came from Pressless, so nothing was installed. | not changed | Keep using this version, and send the details below to whoever helps you. |
| `InstallFailed` | Pressless could not put the new version in place. This version is still installed. | not changed | Try again later. If it keeps happening, send the details below to whoever helps you. |

`installer.UpdateError` is the base of all four and carries the generic
sentence. `updater.py` defines the first three as its subclasses.

### 4.11 One Pressless per folder

The serving path of `__main__` — never `--self-check` — opens
`pressless.lock` in Pressless's own folder and holds an exclusive,
non-blocking OS lock on it for the life of the process: `fcntl.flock` on
Linux, `msvcrt.locking` on Windows. Where the lock is held already, it prints
*"Pressless is already running. Use the browser tab it opened, or close its
window and start it again."* and exits 3, serving nothing.

## 5. Invariants

- **INV-1** — The check is on unless `updates.json` says `"check": false`.
  *Test:* `tests/test_updater.py::test_check_is_on_by_default` — a missing,
  an unparseable and a wrong-shaped file each make the first request; `false`
  makes none. *Breaks when:* the default is read as off, or a malformed file
  reads as off.
- **INV-2** — An offer is returned only for a list that verifies against
  `TRUSTED` and whose version equals a tag greater than the running version.
  *Test:* `tests/test_updater.py::test_only_a_signed_newer_list_is_offered` —
  one fixture per step of § 4.4, signed with a throwaway key patched into
  `TRUSTED`; one byte changed in the list or the `.sig` gives a `Miss`, and a
  `.sig` of two signatures verifies where either key is trusted.
  *Breaks when:* any step is skipped, a `.sig` from another key verifies, or
  only the first signature in a `.sig` is tried.
- **INV-3** — An empty `TRUSTED` offers nothing. *Test:*
  `tests/test_updater.py::test_no_key_no_offer`. *Breaks when:* verification
  is skipped where no key exists.
- **INV-4** — A validly signed list for an older version, behind a newer tag,
  is not offered. *Test:* `tests/test_updater.py::test_an_old_release_under_a_new_tag_is_refused`.
  *Breaks when:* the version is read from the tag alone (Problem 3).
- **INV-5** — A failed check raises nothing and shows nothing. *Test:*
  `tests/test_updater.py::test_a_failed_check_is_silent` — a double raising at
  each request makes `check` return a `Miss` naming that step, and the line
  `updating` then writes names no URL and no path.
  *Breaks when:* an exception escapes the check thread, or a log line carries
  a URL.
- **INV-6** — Only bytes matching the list's size and hash are returned from
  `download`, and every failure removes the file. *Test:*
  `tests/test_updater.py::test_download_rows` — one case per row of § 4.6.
  *Breaks when:* the hash is compared after the file is kept, or a short
  stream raises `UpdateRejected`.
- **INV-7** — No request follows a hop that is not https. *Test:*
  `tests/test_updater.py::test_redirect_to_http_is_refused` — the redirect
  handler raises on an `http://` target and passes an `https://` one.
  *Breaks when:* the default redirect handler is used.
- **INV-8** — Only `publisher.py`, `insights.py` and `updater.py` import a
  network module. *Test:* `tests/test_network_confined.py::test_only_three_modules_reach_the_network`,
  plus a planted `import socket` in a temporary file under a copy of the
  package being caught. *Breaks when:* `installer.py`, `updating.py` or any
  other module imports one.
- **INV-9** — A Windows zip with a member outside `Start Pressless.bat` and
  `Pressless/`, or with an absolute, `..` or drive-lettered path, writes
  nothing, and a zip made by `build-windows.sh`'s own `shutil.make_archive`
  call unpacks. *Test:* `tests/test_updater.py::test_a_stray_zip_member_writes_nothing`.
  *Breaks when:* members are checked while being written, or a directory entry
  is refused.
- **INV-10** — On Linux a failure before `os.replace` leaves the AppImage
  byte-for-byte as it was and removes the staged file; success leaves the new
  bytes at mode 0755. *Test:* `tests/test_installer.py::test_linux_swap`, with
  `Popen` and `os._exit` replaced. *Breaks when:* the file is written in place
  or staged on another filesystem.
- **INV-11** — The Linux helper gets the paths as arguments, the environment
  of § 4.7 and a new session, and nothing re-executes in place.
  *Test:* `tests/test_installer.py::test_linux_helper` — an AppImage path
  holding an apostrophe and a space: the script element of the argv handed to
  `Popen` equals `WAITER` and holds neither path, and `os.execv` is never
  called. *Breaks when:* a path is spliced into the script, or the
  helper inherits `LD_LIBRARY_PATH` pointing into the bundle.
- **INV-12** — The Windows helper waits by image path, not PID, and names
  PowerShell by absolute path. *Test:* `tests/test_installer.py::test_windows_helper`
  reads the command and script: no `-Id`, an absolute `powershell.exe`, the
  paths as arguments only. *Breaks when:* the wait uses `$PID` or `-Id`, or a
  path is written into the script text.
- **INV-13** — Skip persists and Later does not. *Test:*
  `tests/test_updating.py::test_skip_and_later` — after Skip 0.1.3, a new
  process offered 0.1.3 shows nothing and one offered 0.1.4 shows it; after
  Later, a new process shows it again. *Breaks when:* Later is written to disk
  or Skip is held in memory.
- **INV-14** — An update touches nothing in Pressless's own folder but
  `updates.json`, `update.log`, `pressless.lock` and the rolling log. *Test:*
  `tests/test_updating.py::test_update_now_leaves_his_folder_alone` —
  every other file's bytes and the folder's list of names are the same before
  and after Update now, with the spawn and exit replaced. *Breaks when:* the
  staged file or folder is put inside Pressless's own folder.
- **INV-15** — Update now takes `editor.LOCK` before applying and holds it to
  the exit. *Test:* `tests/test_updating.py::test_update_waits_for_a_save` — with
  the lock held by another thread, apply is not reached until it is released.
  *Breaks when:* the lock is skipped, or released before the exit.
- **INV-16** — A second serving start on a held folder serves nothing and
  exits 3; `--self-check` is unaffected. *Test:*
  `tests/test_main.py::test_one_pressless_per_folder`. *Breaks when:* on
  either platform the lock is not taken, is taken blocking, or is released
  before the process ends; or `--self-check` takes it.
- **INV-17** — `__version__` equals `pyproject.toml`'s `version`. *Test:*
  `tests/test_version.py::test_the_program_knows_its_version`. *Breaks when:*
  a release bumps one and not the other.
- **INV-18** — No tracked file holds a private key. *Test:*
  `tests/test_no_private_key.py` — `git ls-files` has no `*.key`, and no
  tracked file matches `BEGIN [A-Z ]*PRIVATE KEY`, the pattern assembled at
  run time so the test does not match itself (FIBR-0355). *Breaks when:* a key
  or a fixture spelling one out is committed.
- **INV-19** — `sign-release.py` attaches nothing when the signature does not
  verify against the committed `TRUSTED`, or the build's commit is not the
  tag's. *Test:* `tests/test_sign_release.py` drives its two refusal functions
  with a mismatched key and a mismatched commit. *Breaks when:* it verifies
  against the key it just signed with.
- **INV-20** — The four failure types each have a three-part sentence. *Test:*
  `tests/test_face.py::test_every_failure_type_has_a_sentence`, which already
  walks every subclass. *Breaks when:* a type is added without one.

## 6. Failure modes

- **GitHub is unreachable, slow or answers nonsense at start.** No offer, and
  nothing is shown (INV-5).
- **The download drops.** `DownloadEndedEarly`; the old version stays.
- **Someone serves a tampered or old release.** `UpdateRejected`, or no offer.
- **The Windows program is still running at 60 s** — a second copy, or an
  antivirus hold. The helper gives up, starts nothing, and the old version
  stays. He starts Pressless as usual.
- **The Windows swap fails halfway.** The rollback renames the old folder back.
  A rollback that also fails leaves `Pressless.old` beside `Pressless-data`,
  and `update.log` ends without `started`. His writing is untouched.
- **The Linux helper cannot start after the swap.** The new file is in place
  and the process exits anyway; starting Pressless by hand runs the new
  version.
- **He double-clicks Pressless while the helper waits.** Whichever process
  takes the folder lock first serves; the other says Pressless is already
  running (§ 4.11). On Windows the manual start holds the image, the helper
  gives up at 60 s, and he keeps the old version until the next offer.
- **The old Windows console stays open** with the old batch file's pause
  prompt. It says Pressless is updating first, so closing it is safe.
- **The signing key is lost.** Scope decision 4.

## 7. Tests

`tests/test_updater.py`, `tests/test_installer.py`, `tests/test_updating.py`,
`tests/test_network_confined.py`, `tests/test_version.py`,
`tests/test_no_private_key.py`, `tests/test_sign_release.py`, and one case in
`tests/test_main.py`. No test reaches the network: the `Transport` double
answers by URL, per `CLAUDE.md`'s warning about positional doubles. Signing
uses a key generated inside the test.

Each is seen red against a stub before its code is written, as PRESS-0014's
were, and each invariant gets one mutation per route its *Breaks when* names.

### 7.1 By hand, on the Windows box and on Linux

A helper's runtime cannot be proved by the suite, only its command. So, for
each system, two cycles — a restart fix proves out only on the update after
the one that ships it:

1. Build and sign releases N+1 and N+2 into a scratch repository, and start
   release N with `PRESSLESS_UPDATE_REPOSITORY` naming it.
2. Start release N, click Update now. It reopens by itself as N+1, and
   `update.log` reads `swapped`, `waiting`, `started` on Linux and `waiting`,
   `swapped`, `started` on Windows.
3. From N+1, update to N+2 the same way.
4. `Pressless-data`'s file list and every file's hash are unchanged across
   both.

On Windows this runs in the logged-on session (`CLAUDE.md`: a program started
over SSH cannot reach the credential vault).

## 8. Alternatives considered (and rejected)

- **One signature per artefact, as finbreak does.** Rejected by Problem 3: it
  leaves anti-rollback open, and the Windows folder would need a signed
  manifest anyway.
- **A pure-Python Ed25519 verifier.** No new dependency, but security code
  written here and reviewed by nobody else. `cryptography` is maintained,
  audited and what finbreak ships.
- **Updates off by default.** The user's call went the other way (scope
  decision 1).
- **Replace the Windows program file by file.** A failure halfway leaves a
  folder of two versions. A rename of the whole folder is all or nothing, and
  can be undone.
- **Relaunch by re-executing in place.** finbreak's relaunch did this and the
  app closed without reopening.
- **Hold the offer in `updates.json`.** It would survive a restart that is
  meant to re-check, and would need clearing when a newer release appears.
- **Sign in CI.** The key would live in the repository's secrets, and anyone
  who can change the workflow could sign.

## 9. Out of scope

- **The Publisher's and Insights' certificate check** (Problem 5). Same cause,
  same fix, a different part. Deferred; not yet queued.
- **Showing what changed in the new version.** The user chose the offer without
  it (scope decision 2). Deferred; not yet queued.
- **A "check now" button.** Deferred; not yet queued.
- **Automating a key change.** Scope decision 4. Deferred; not yet queued.
- **macOS.** No artefact exists.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_updater.py::test_check_is_on_by_default` |
| INV-2 | `tests/test_updater.py::test_only_a_signed_newer_list_is_offered` |
| INV-3 | `tests/test_updater.py::test_no_key_no_offer` |
| INV-4 | `tests/test_updater.py::test_an_old_release_under_a_new_tag_is_refused` |
| INV-5 | `tests/test_updater.py::test_a_failed_check_is_silent` |
| INV-6 | `tests/test_updater.py::test_download_rows` |
| INV-7 | `tests/test_updater.py::test_redirect_to_http_is_refused` |
| INV-8 | `tests/test_network_confined.py::test_only_three_modules_reach_the_network` |
| INV-9 | `tests/test_updater.py::test_a_stray_zip_member_writes_nothing` |
| INV-10 | `tests/test_installer.py::test_linux_swap` |
| INV-11 | `tests/test_installer.py::test_linux_helper` |
| INV-12 | Partial: `tests/test_installer.py::test_windows_helper` reads the command; the script's run is § 7.1 by hand |
| INV-13 | `tests/test_updating.py::test_skip_and_later` |
| INV-14 | `tests/test_updating.py::test_update_now_leaves_his_folder_alone` |
| INV-15 | `tests/test_updating.py::test_update_waits_for_a_save` |
| INV-16 | `tests/test_main.py::test_one_pressless_per_folder` |
| INV-17 | `tests/test_version.py::test_the_program_knows_its_version` |
| INV-18 | `tests/test_no_private_key.py` |
| INV-19 | `tests/test_sign_release.py` |
| INV-20 | `tests/test_face.py::test_every_failure_type_has_a_sentence` |
| § 4.7 the helpers restart the new version | **nothing** automated — § 7.1 by hand, on each system |
| § 4.8 the release is published only after signing | Partial: INV-19 covers the refusals; the draft flag in `release.yml` is checked by nothing |

## 11. Cross-doc impact

- `docs/design.md` § The parts gains the Updater row, § What may depend on
  what gains its rule (§ 4.1 here), § State gains the in-memory offer as an
  exception, and § Where everything sits on disk lists `updates.json`,
  `update.log` and `pressless.lock` in Pressless's own folder.
- `docs/specs/PRESS-0011-face.md` — `Face.add_to_list`, and
  `docs/specs/PRESS-0012-editor.md` § 4.5 — the list renders what is
  registered there.
- `docs/specs/PRESS-0022-packaging.md` § 4.4 — the release is a draft until
  signed, and § 14 — after the first updating release, moving to a new version
  is the updater's job.
- `CLAUDE.md` § Build and test — `ants.pressless.signingKey`, and the signing
  step after CI.
- `README.md` § Install — the updater, and how to turn it off.
- `pyproject.toml` — `cryptography` and `certifi`.
- `CHANGELOG.md` — the entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0023-self-update-loop-log.md`.

## 13. Resource cost

A download needs free space beside the artefact equal to its size — about
36 MB for the v0.1.2 AppImage and 18 MB for its Windows zip, read with
`gh release view v0.1.2 --json assets`. On Windows the unpacked folder needs
its own size again until the old one is removed. Memory holds one chunk at a
time. One request at each start, three when a release is offered.

## 14. Open questions

**The signing key must exist before the first updating release.** The
maintainer runs `scripts/make-signing-key.py` and pastes the public key into
`update_key.TRUSTED`. Until then `TRUSTED` is empty and nothing is offered
(INV-3).
