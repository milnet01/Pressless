# PRESS-0022 — Package Pressless into one artefact per system

**Status:** accepted (2026-09-02). Two cold-eyes loops, both folded in, nothing deferred — the run reached the spec cap of 2 and every verified finding is fixed. **A violent cap:** about ten of loop 2's twelve findings landed on text loop 1 wrote, so a third cold read would mostly repair the second. The document is routed to implementation rather than to another gate, and implementation is the better third reviewer. **One region no cold read could judge:** Windows and AppImage behaviour is unrunnable from this machine, which the packet declared up front — §10 records what that leaves unchecked, and PRESS-0022 exists to make it observable.
**Kind:** package.
**Source:** ROADMAP PRESS-0022 (`docs/design.md` § The stack, and what it
rules out; § Where everything sits on disk; ADR-0004).

**Blocked by:** PRESS-0013.  **Pairs with:** PRESS-0068.

**Layman:** The writer gets one file to download for his system, and
running it needs nothing installed first.

## 1. Goal

Pressless ships as one artefact per system, built by CI, that runs on a
machine with no Python on it. An AppImage on Linux; a zip on Windows
holding the program folder and a batch file that starts it. Each keeps
its own folder beside itself, so the writer chooses the drive by
choosing where the artefact lives.

After this ships, S4 is demonstrable rather than argued: the Windows
test box — which has no interpreter, deliberately — runs the artefact
and reports what it found. Every Windows claim this project has made so
far is reasoned; this is what makes the next one measured.

**It does not ship a finished Pressless.** PRESS-0013 owns the Publish
button and is not built. What is packaged here is a deliberately minimal
program (§4.5) whose whole job is to answer the three questions
packaging must answer. The Face replaces it without changing anything
in §4.1 to §4.4.

## 2. Problem

**Nothing here can be run by the writer.** `src/pressless/` holds
library modules and no entry point: no `__main__.py`, no
`[project.scripts]` table in `pyproject.toml`, nothing that starts. The
suite exercises the modules directly.

**Nothing here knows where Pressless's own folder is, and that is
deliberate.** Every function of `settings.py` and `credentials.py` that
reaches disk — `settings.path_for`, `settings.load`, `settings.save`,
`credentials.read`, `credentials.write` — takes `folder: Path` as its
first argument and is handed it. (`credentials.choose()` asks the store
and takes no folder.) PRESS-0001 §4.1
states the rule: *"`folder` is Pressless's own folder, supplied by the
caller. Settings does not create it, search for it, or fall back to
another one."* PRESS-0002 §4.1 repeats it. Both name this item as the
owner of the gap, in §2, §8 and §9 apiece. So the caller does not
exist, and this spec builds it.

**The writer cannot see a Windows defect, and neither can we.** Three
Windows-parity fixes shipped on 2026-09-02 (PRESS-0047, and PRESS-0067
items 2 and 3) and not one was executed on Windows: the suite runs on
Linux and the test box has no interpreter, by design. PRESS-0001 §10
and PRESS-0002 §10 each carry a row saying the real behaviour is
observable only where this item stages an artefact, and that neither
schedules a check of its own. Until an artefact exists, those rows
schedule nothing anywhere.

**A packaged credential store can fail in a way that reads as a
verdict.** PRESS-0002 §4.2 makes `keyring.errors.NoKeyringError` the
sole discriminator between *no store* and *a store that cannot be
relied on*, and INV-9 pins that reading. A bundle that omits keyring's
entry-point metadata registers no backend, raises exactly that error,
and is reported as *no store*. On Windows PRESS-0002 INV-2 turns that
into `NoStore` and setup stops; on Linux it is worse and quieter — the
writer's publishing key lands in the fallback file while his real
keyring sits working and unused. PRESS-0068 item 1 diagnoses this and
assigns it here.

## 3. Scope decisions (agreed with the user)

1. **Build the pipeline now, against a minimal program** (§4.5), rather
   than waiting for PRESS-0013. Decided 2026-09-02. The Blocked-by
   constrains when this item closes, not when it starts: §4.1 to §4.4
   are settled by the artefact's shape and not by what it runs.

2. **A new version migrates nothing.** Decided 2026-09-02. The written
   steps say to extract over the old copy, so the folder is already
   beside the new artefact. Nothing is remembered outside the app,
   nothing is moved, and nothing is searched for. This is the first of
   the three branches the design gate deferred here.

3. **One shape each, not one shape twice.** Decided 2026-08-26. Linux
   is an AppImage; Windows is a zip holding the program folder and a
   batch file that starts it.

4. **`--windowed` is not taken on Windows.** Following from 2, not a
   preference: the minimal program of §4.5 reports to a console, and a
   windowed build nulls `sys.stdout`. PRESS-0013 revisits it when there
   is a Face to show.

5. **The folder is named `Pressless-data`.** Decided 2026-09-02, over
   friendlier names, because it cannot be confused with the
   `Pressless/` folder the zip unpacks beside it. INV-8 pins the
   literal: every installed machine binds to it, so it is cheap now and
   a breaking change after the first release.

6. **The Windows batch file stays.** Decided 2026-09-02, and one-folder
   is why it still earns its place rather than why it stopped: §4.5's
   program prints a report and finishes, so a double-clicked `.exe`
   would open and close a console before the writer could read it.
   PRESS-0013 revisits it, since a Face opens a browser instead.

## 4. Design

### 4.1 The two artefacts

Both are frozen by PyInstaller in **one-folder** mode. Linux wraps that
folder in an AppImage; Windows zips it beside a batch file.

| System | What is published | What the writer does |
|---|---|---|
| Linux | `Pressless-<version>-x86_64.AppImage` | makes it executable, double-clicks it |
| Windows | `Pressless-<version>-windows.zip`, holding `Pressless/` (the frozen folder) and `Start Pressless.bat` | extracts it, double-clicks the batch file |

**One-folder rather than one-file, on both.** One-file unpacks the whole
bundle to a temporary directory on every launch, which costs a delay
proportional to the bundle on an app opened daily. That is the whole
reason: measured 2026-09-02, `sys.executable` is the artefact's own path
on disk in **both** modes — only `sys._MEIPASS` differs — so §4.2's
Windows row would resolve either way. The AppImage supplies Linux's
single-file convenience without paying for it twice.

### 4.2 Finding Pressless's own folder

A new module, `src/pressless/paths.py`. It is the caller that PRESS-0001
§2 says must exist, and it resolves downward only: the entry point asks
it for a folder and hands that folder to Settings and Credentials.

```python
class NotPackaged(Exception): ...      # cannot tell where we are
class FolderUnusable(Exception): ...   # found the place, cannot use it

def artefact_path() -> Path:
    """The AppImage, or the frozen program folder on Windows."""

def own_folder() -> Path:
    """Pressless's own folder. Resolved, never created."""

def ensure(folder: Path) -> Path:
    """Create it if absent and prove it writable. Returns it."""
```

**`paths.py` imports no other `pressless` module**, keeping the
direction PRESS-0001 INV-1 and PRESS-0002 INV-1 already enforce on
their own side. Neither `settings.py` nor `credentials.py` may import
it: doing so would make them derive their own folder, which PRESS-0001
scope decision 2 forbids in as many words.

**How `artefact_path` resolves**, in this order:

| State | Resolves to |
|---|---|
| Frozen, `sys.platform == "win32"` | `Path(sys.executable).parent` — the extracted folder |
| Frozen, `$APPIMAGE` set **and** naming an existing file | `Path($APPIMAGE)` — the AppImage itself |
| Frozen, anything else | `NotPackaged` |
| Not frozen | `NotPackaged` |

**Both guards on `$APPIMAGE`, not just the first.** A stale value
inherited from a parent process names a file that is no longer there,
and treating it as an address puts the writer's folder somewhere he
will never look. Prior art: finbreak's
`src/finbreak/services/update_installer.py::detect_installer` applies
exactly these two guards, and its
`tests/features/auto_update/` suite pins the stale case separately from
the unset one.

**Never `sys.executable` or `sys._MEIPASS` on Linux.** An AppImage runs
from a read-only temporary mount, so both point inside it: a folder
resolved that way is unwritable, and would vanish on exit if it were
not.

**`own_folder` is `artefact_path().parent / "Pressless-data"`** — a
sibling of the artefact, never inside it. On Windows that puts it
beside the extracted folder rather than within it, which is what makes
scope decision 2 safe: extracting a new zip over the old copy replaces
`Pressless/` and cannot touch writing that was never in it.

**`PRESSLESS_FOLDER` overrides `own_folder`, and only when not
frozen.** It is how the suite and a development run get a folder at
all. A packaged artefact ignores it, so a stray value in the writer's
environment can never redirect his writing.

### 4.3 The credential store inside a bundle

PRESS-0068 item 1 prescribes two build flags — `--copy-metadata
keyring` and `pywin32-ctypes`. **Measured, both are already done for us,
and taking them anyway would be a charm rather than a fix.**

```
$ python3 -m PyInstaller --onedir -n probeA probe.py      # no flags
$ python3 -m PyInstaller --onedir --copy-metadata keyring -n probeB probe.py
$ ./distA/probeA/probeA ; ./distB/probeB/probeB
# both: entry_points ['KWallet','SecretService','Windows','chainer',
#                     'libsecret','macOS']
# both: backend keyring.backends.chainer.ChainerBackend (priority: 10)
```

Measured 2026-09-02 against PyInstaller 6.20.0 and keyring 25.7.0.
PyInstaller ships `PyInstaller/hooks/hook-keyring.py`, whose two lines
are `collect_submodules('keyring.backends')` and
`copy_metadata('keyring')` — the flags item 1 asks for, applied
automatically. It ships `hook-win32ctypes.core.py` for the Windows
half, and keyring's own metadata declares
`pywin32-ctypes>=0.2.0; sys_platform == "win32"`, so a Windows runner
installs it without being told to.

**So the risk is real and the prescribed fix is not the answer.** A flag
that duplicates a shipped hook silently stops meaning anything if the
hook changes, and nothing would notice: the build still succeeds, and
PRESS-0002 §4.2 turns the failure into a confident sentence about the
writer's machine.

**What closes it is a check, not a flag.** §4.5's program reports which
backend answered, and §7 asserts that it is a real one. A flag proves
nothing about the bundle; running the bundle proves it whatever the
hooks do.

**What this measurement does not reach.** It was taken on Linux.
`keyring.backends.Windows` imports `win32ctypes` inside a function
guarded by `ExceptionTrap`, and forces a demand-import to make it
raise — a shape static analysis is least likely to follow. Whether the
Windows freeze carries it can only be found by running the artefact on
Windows, which is §7's clean-room step and the reason this item exists.

### 4.4 How it is built

**One flag list, read by both freezes.** `scripts/freeze_flags.py`
holds the hidden imports, collected packages and data pairs as plain
Python lists; the Linux and Windows build scripts import it rather than
spelling flags out. A dependency collected for one system cannot then
be silently absent from the other's bundle. Prior art: finbreak's
`scripts/windows_freeze_flags.py`, which adds a test asserting the two
freezes agree — worth copying once there are two hand-written
invocations to disagree.

**`.github/workflows/release.yml`, triggered by a version tag.** Two
jobs, `ubuntu-latest` and `windows-latest`, each freezing and running
§4.5's self-check on its own runner, then attaching its artefact to the
release. ADR-0004 requires this from the first release rather than
later, because there is no other way to produce the Windows file.

The Linux job downloads `appimagetool` and wraps the frozen folder in
an `AppDir` with the three files an AppImage requires — `AppRun`, a
`.desktop` file and an icon.

**The tag is the version, and it reaches two places.** The workflow
triggers on `v<X.Y.Z>`; the artefact filenames of §4.1 and
`pyproject.toml`'s `version` carry the same `<X.Y.Z>`. **The README
names no version** — it links to the latest release page, so nothing
there goes stale and no step edits it at release time. That is what
keeps S4's "the steps are complete" true of a README nobody updates.

`pyproject.toml` reads `0.0.0` today, and `cut-release` is what moves
it — this item adds no version-bumping of its own. It requires only
that the workflow reject a tag disagreeing with the manifest, so a
mislabelled artefact cannot be published.

**PyInstaller is pinned in `pyproject.toml`, and nothing pins it
today.** It is named by `CLAUDE.md` § Build and test as a build-time
packager belonging beside the gate's tools rather than in
`dependencies`, and it appears in no manifest, no gate script and no
workflow. It gets its own optional-dependency group, so the two
release runners install it the same way and anyone can reproduce a
build from the manifest. **A floor, not a pin**, matching the reasoning
already in that file for `keyring` and the gate's tools — so two builds
months apart may use different PyInstaller releases, and a release that
breaks us shows up on the next build rather than months later. Byte
reproducibility is not claimed and is not a goal here.

**The gate workflow is untouched.** `ci.yml` runs
`scripts/local-ci.sh` and holds no checks of its own; releasing is a
different trigger and a different file.

### 4.5 The program that gets packaged

`src/pressless/__main__.py`. It exists because packaging cannot be
proved without something to package, and it is deliberately the
smallest thing that proves it. PRESS-0013 replaces its body and changes
nothing in §4.1 to §4.4.

It answers the three questions an artefact must answer, and prints one
machine-readable line for each. **The report's shape is a contract**:
§7's tests parse it and §4.4's release job reads its exit code, so it
is fixed here rather than invented by whoever writes the program.

```
pressless: ok
folder: <absolute path>
store: <keyring|file> <member name>
```

| Question | How it is answered | Line |
|---|---|---|
| Did it start at all? | it printed, on a machine with no interpreter | `pressless: ok` |
| Where is its folder, and can it be written? | `paths.own_folder()` then `paths.ensure()` | `folder:` |
| Which credential store answered? | `credentials.choose()` | `store:` |

**It exits non-zero only where a question could not be answered at
all** — `NotPackaged`, `FolderUnusable`, or `choose()` raising. **A
`store: file` answer is not a failure here**, because this program
cannot tell a machine with no store from a bundle that lost its
metadata; §2 is the whole reason. Which of the two it is, is §7's to
decide, and it decides it by controlling the machine.

`--self-check` prints the same report and is what CI and the Windows
box run. There is no other flag: the double-click and the check take
the same path, so the writer's route is the one that was tested.

**It writes nothing but the folder.** No settings file, no credential,
no probe left behind — `credentials.choose()` already deletes its own
probe (PRESS-0002 §4.2), and this program adds nothing to disk beyond
the folder `ensure` creates.

### 4.6 The written steps

README § Install currently reads *"(Once there is something to
install.)"*. It gains real steps, one short list per system, naming the
file to download and what to do with it. S4 is the test of those steps:
complete for the writer's machine, nothing installed first, nothing
translated from the other system's list.

Each system's steps carry its own upgrade rule (§14): on Windows,
extract over the previous copy; on Linux, save the new AppImage into the
same directory as the old one. Both say plainly what is lost by not
doing so — the writing stays beside the old copy, and it is the one
thing nothing backs up.

## 5. Invariants

- **INV-1** — `paths.py` imports no other `pressless` module.
  *Test:* `tests/test_paths.py::test_paths_imports_nothing_of_ours`,
  walking the module's AST as PRESS-0001 INV-1 does.
  *Breaks when:* `paths` is changed to read `settings.FILE_NAME` to
  decide whether a folder is Pressless's, which inverts the direction
  §4.2 depends on.

  **The other half of §4.2's rule is already locked and is not
  restated here.** `settings.py` and `credentials.py` importing
  `paths` would be caught by PRESS-0001 INV-1 and PRESS-0002 INV-1,
  which ban importing any other `pressless` module. An invariant here
  covering that would claim a test it does not own.

- **INV-2** — Frozen on Linux, `artefact_path()` returns the path in
  `$APPIMAGE` and never a path under the running mount.
  *Test:* `tests/test_paths.py::test_appimage_path_is_not_the_mount`,
  patching `sys.platform` to a non-win32 value, plus `sys.frozen`,
  `sys.executable` and `$APPIMAGE` to a real file in a temporary
  directory; asserts the result is that file and is not a parent of
  `sys.executable`. **`sys.platform` is part of the fixture, not
  scenery** — §7 step 1 runs this suite on `windows-latest`, where the
  win32 row is taken before `$APPIMAGE` is read, so an unpatched
  fixture fails there for the platform rather than for the rule.
  *Breaks when:* the resolver falls back to `sys.executable` or
  `sys._MEIPASS` on Linux — the fixture separates them, so a resolver
  reading either returns the mount and fails.

- **INV-3** — `$APPIMAGE` naming a file that does not exist is treated
  as unset.
  *Test:* `tests/test_paths.py::test_stale_appimage_is_not_an_address`
  — frozen, `sys.platform` patched non-win32, `$APPIMAGE` set to a
  deleted path; expect `NotPackaged`.
  *Breaks when:* the resolver checks only that the variable is set. No
  other rule rejects this fixture: the variable is present and
  well-formed, so only the file-exists guard can fail it.

- **INV-4** — `PRESSLESS_FOLDER` is honoured when not frozen and
  ignored when frozen.
  *Test:* `tests/test_paths.py::test_override_is_ignored_when_frozen`,
  both arms in one test.
  *Breaks when:* the override is read before the frozen check, so a
  value in the writer's environment moves his folder.

- **INV-5** — `ensure()` raises `FolderUnusable` rather than choosing
  another location, and names the path it tried.
  *Test:* `tests/test_paths.py::test_unusable_folder_never_falls_back`,
  against a read-only parent directory. **It must skip where the user
  can write to a read-only directory anyway** — root defeats the
  fixture, and a test that cannot fail is worse than an absent one.
  *Breaks when:* a fallback to the home directory is added — which
  `docs/design.md` § Where everything sits on disk forbids by name,
  because it fills the drive the rule protects and nobody sees it
  happen.

- **INV-6** — The packaged artefact resolves a real credential store on
  a machine that has one: `credentials.choose()` returns
  `Choice("keyring", <member>)`.
  *Test:* `tests/features/packaging/` — run the built artefact with
  `--self-check` and read the store kind, not only the member.
  *Breaks when:* the bundle omits keyring's entry-point metadata. **The
  store kind is what makes this falsifiable, and a member name alone
  does not.** PRESS-0002 §4.2 turns `NoKeyringError` into
  `Choice("file", "file")` off Windows — which names a member, raises no
  `NoStore`, and names no failure backend. An invariant reading the
  member alone therefore passes green against exactly the metadata-less
  bundle §2 calls the worse and quieter case. This is the check §4.3
  says replaces PRESS-0068 item 1's build flags.

- **INV-7** — The artefact runs on a machine with no Python.
  *Test:* the clean-room step of §7 — `env -i PATH=/nonexistent` on
  Linux, and the Windows box, which has no interpreter by design.
  *Breaks when:* a build stops bundling the interpreter, or a runtime
  import reaches outside the bundle.

- **INV-8** — On the frozen branch, `own_folder` ends in the literal
  `Pressless-data`, and the test holds its own copy of that string.
  `PRESSLESS_FOLDER` is the folder itself and nothing is appended to
  it, so the override branch is outside this invariant.
  *Test:* `tests/test_paths.py::test_folder_name_is_pinned`, comparing
  against a literal written out in the test, never imported from
  `paths`.
  *Breaks when:* the name is changed after a release. Renaming it sends
  every writer who already has one back through setup with his key
  apparently gone — the breach `versioning-overrides.md` § Setup state
  forbids. Sharing the literal with the module would compare `paths`
  against itself, which is why `tests/test_settings.py` keeps its own
  copy of `FILE_NAME` and why this one does too.


## 6. Failure modes

| When | What happens |
|---|---|
| `$APPIMAGE` unset or stale on a frozen Linux run | `NotPackaged`. Pressless stops and says it cannot tell where it is, naming what it looked for |
| The folder's parent is read-only or full | `FolderUnusable`, naming the path. Never a fallback (INV-5) |
| The folder is on a mount with no POSIX modes | `credentials.write` raises `NoStore` per PRESS-0002 §4.6 — correct, and newly reachable now that the writer chooses the drive |
| The bundle registers no credential backend | it reports `store: file`, which §4.5 does not treat as a failure. §7 step 3 is what catches it, by creating a store first — so the release never ships one (INV-6) |
| The writer extracts, or saves, version 2 elsewhere | first-run setup, writing stranded beside version 1. Accepted (scope decision 2); §4.6 states it in both systems' steps |
| A CI runner is unavailable | no release. ADR-0004 already names this as a concentrated dependency with no local route around it |

## 7. Tests

`tests/test_paths.py` locks INV-1 to INV-5 and INV-8 and runs in the
ordinary suite: they are all resolution rules, and patching
`sys.frozen`, `sys.executable` and the environment exercises every
branch without a build.

`tests/features/packaging/` holds INV-6's test. It does not run in the
ordinary suite — it needs a built artefact — so it is marked
`packaging` and skipped cleanly when none is present, the way the
`archive` marker already works for tests needing the export.
`PRESSLESS_ARTEFACT` points it at the built file, exactly as
`PRESSLESS_ARCHIVE` points the archive tests at the export.
**INV-7 has no pytest test**: it is a workflow step, because what it
proves is a property of the machine rather than of the code.

**The release job runs three steps, and they are three because one run
cannot serve them all.**

1. **The suite**, `scripts/local-ci.sh`, on both runners, under
   `shell: bash`. ADR-0004 § Consequences requires it — *"the Windows
   job must still run the test suite rather than only producing a
   file"* — and this is the first time any of it runs on Windows.

   **Two things make that script Linux-only today, and both are this
   item's to fix.** It invokes `python3`, which is the Linux spelling —
   the Windows installer ships `python.exe` and a `py` launcher and
   creates no `python3` — so the script must resolve the interpreter
   rather than name one. And its leak sweep walks `git rev-list --all`,
   which a shallow clone cannot answer: `ci.yml` already sets
   `fetch-depth: 0` and says why, and the release workflow needs the
   same on both jobs. Without it the sweep reports a clean history it
   never fetched, which is the failure mode that comment exists to
   prevent.
2. **INV-7, in a clean room. Linux only**: `env -i PATH=/nonexistent`
   on the AppImage. There is no Windows form of it and none is
   invented: `windows-latest` ships Python, so a clean room cannot be
   made there by clearing variables. **INV-7's Windows evidence is the
   staged box**, which has no interpreter at all.
3. **INV-6, under a session the job CREATES.** On Linux the runner is
   headless and has no keyring, so the job starts one —
   `dbus-run-session` with a keyring daemon — and the arm then asserts
   rather than skipping. It cannot share step 2's environment, because
   `env -i` would strip the very session step 3 just created.

**Step 3 must not be allowed to skip, and that is the point of creating
the session.** The answer a metadata-less bundle gives on Linux is
`store: file`, and so is the answer a working bundle gives on a machine
with no store — §4.5 says why the program cannot tell them apart. A
skip conditioned on "no store present" is therefore conditioned on
exactly the failure it exists to catch, and INV-6 could never go red.
Creating the store is what makes `store: file` unambiguous.

**On Linux every artefact step runs the wrapped AppImage, after
`appimagetool` — never the bare frozen folder.** `$APPIMAGE` is set by
the AppImage runtime and by nothing else, so on the frozen folder
`artefact_path()` raises `NotPackaged` (§4.2) and a self-check there
fails every release for the wrong reason. It also exercises the
AppImage runtime, which INV-2's patched test cannot reproduce.

A non-zero exit at any step fails the release. finbreak's
`windows-build.yml` carries a clean-room step and shows it can be
automated rather than staged by hand.

**Staging to the Windows box stays, and is not replaced by the runner.**
The runner proves the bundle is complete; the box proves the writer's
own route works, from a downloaded zip to a double-clicked batch file.
Both PRESS-0001 §10 and PRESS-0002 §10 name that staging as the only
place their Windows rows are ever observed.

**Every test above must be seen failing before the code exists.** For
INV-6 the obvious route does not work and §4.3 is why: dropping
`--copy-metadata keyring` changes nothing, because PyInstaller's own
shipped hook collects it. The metadata has to be withheld deliberately —
an `--additional-hooks-dir` whose `hook-keyring.py` shadows the shipped
one with empty `datas`. Build that bundle once, watch INV-6 fail
against it, and throw it away.

## 8. Alternatives considered (and rejected)

- **One-file on both systems**, as finbreak does. Rejected for §4.1's
  reason, which is the unpack on every launch and nothing else.
  finbreak freezes
  a GUI it can afford to start slowly and resolves its own path for
  self-update rather than for a data folder, so the trade lands
  differently there.
- **Taking `--copy-metadata keyring` anyway**, as PRESS-0068 item 1
  prescribes. Rejected on the measurement in §4.3: it changes nothing
  today, and a flag whose effect is invisible is one nobody can tell
  has stopped working.
- **The folder inside the extracted Windows folder** rather than beside
  it. Rejected because scope decision 2 has the writer extract over the
  old copy: a folder inside is in the path of that extraction, and a
  writer who deletes the old folder first loses everything.
- **Remembering the folder's location outside the app**, and **asking
  when none is found**. Both put to the user 2026-09-02 and both
  declined in favour of scope decision 2.
- **Settings resolving its own folder.** Rejected by PRESS-0001 §8
  before this spec existed; repeated here because a resolver module is
  exactly the moment somebody proposes it again.

## 9. Out of scope

- The Face, and everything the writer actually does with Pressless —
  PRESS-0013.
- Signing, notarising or a Windows SmartScreen reputation — no id yet.
- Self-update — PRESS-0023.
- Photograph handling, which adds Pillow to the bundle and changes its
  size but nothing in §4 — PRESS-0016.
- PRESS-0068 items 2, 3 and 4, which are `credentials.py`'s and not a
  packaging concern.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_paths.py::test_paths_imports_nothing_of_ours`. The converse — Settings or Credentials importing `paths` — is caught by PRESS-0001 INV-1 and PRESS-0002 INV-1, not here |
| INV-2 | **half** — the test patches `sys.frozen` and `$APPIMAGE`; the suite builds no AppImage. The release job builds one and runs `--self-check`, which reports the resolved folder and would show it landing under the mount |
| INV-3 | `tests/test_paths.py::test_stale_appimage_is_not_an_address` |
| INV-4 | `tests/test_paths.py::test_override_is_ignored_when_frozen` |
| INV-5 | `tests/test_paths.py::test_unusable_folder_never_falls_back` |
| INV-6 | `tests/features/packaging/`, run as §7's step 3 on both release runners, under a session the job creates — never the clean room, and never conditioned on a store happening to be there. **Half on Windows:** the runner proves the bundle resolves a keyring store, the test box proves the writer's own route, and the box is driven by hand |
| INV-7 | §7's step 2 on the Linux runner. **Nothing on the Windows runner** — `windows-latest` ships Python, so no clean room can be made there; the staged box is the Windows evidence and it is driven by hand |
| §4.6's written steps, and therefore S4 | **nothing** — no check reads a README. `verify-instructions` executes such steps and is not scheduled anywhere in this project |
| INV-8 | `tests/test_paths.py::test_folder_name_is_pinned` |
| Scope decision 2's accepted risk | **nothing, and nothing can** — it fires on where the writer chose to extract, which the app never sees |

## 11. Cross-doc impact

- **README** — § Install gains the steps of §4.6.
- **CHANGELOG** — an Added entry, and the first release this item makes
  possible.
- **`pyproject.toml`** — a group pinning PyInstaller (§4.4), and a
  `packaging` marker declared beside `archive` so §7's build tests skip
  cleanly without one.
- **`scripts/local-ci.sh`** — resolves the interpreter instead of
  naming `python3` (§7 step 1). It is the one file the pre-push hook
  and both CI workflows share, so the change is felt on every route
  and must keep the Linux behaviour identical.
- **`CLAUDE.md`** — § Build and test names PyInstaller as belonging
  beside the gate's tools; once §4.4 pins it, that line describes a
  file rather than an intention.
- **`docs/design.md`** — no change. § The stack and § Where everything
  sits on disk already carry the two shapes and the beside-the-artefact
  rule; this spec implements them rather than amending them.
- **ADR-0004** — no change. Its § Decision already names both shapes.
- **PRESS-0068** — item 1's prescribed fix is superseded by §4.3's
  measurement. That item stays open for items 2 to 4; a fold-back note
  belongs on it once this ships.
- **`docs/standards/versioning-overrides.md`** — no change, but §14
  reads against its § Setup state.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-09-02 | 3, cold — genre pinned `spec`; the packet declared Windows and AppImage behaviour an unrunnable region up front, so Q1 was out of scope there | 2 | 5 | 1 | 2 | **Ten verified, ten fixed, none dismissed. All three lanes independently found the same Q4**, which is the run's strongest signal: INV-6 read the credential store's MEMBER NAME, and PRESS-0002 §4.2 returns `Choice("file", "file")` off Windows — so the invariant passed green against exactly the metadata-less bundle §4.3 exists to reject. It now requires the store KIND. Its twin: §7's red run for it was unreachable, because the metadata comes from PyInstaller's shipped hook rather than the flag §7 said to drop. **The best Q2 was a release that could never go green** — the Linux self-check ran on the frozen folder, where `$APPIMAGE` is unset, so `artefact_path()` raises `NotPackaged`; and one `env -i` run was serving both INV-6 and INV-7, while `env -i` strips the session bus a keyring member needs. §7 is now three steps and runs the wrapped AppImage. **One Q2 caught a breach of this spec's own source**: ADR-0004 requires the Windows job to run the test suite, and §4.4 had it freeze and self-check only. **Two Q2s were the design being stated Windows-first**: `Pressless-data` was called unbound when every installed machine binds to it (now INV-8), and §14's extract-over rule described nothing that happens on Linux, where each release is a differently-named file. **Both Q1s were mine, not the lanes'** — a false universal about `folder` arguments that `credentials.choose()` breaks, and a rejection of one-file resting on `sys.executable`; all three lanes flagged the second as an open question and a measurement settled it false, so the one-folder choice now stands on the unpack delay alone. Q3: nothing said how a version tag reaches the artefact filename. Resolved clean and not counted: PRESS-0002 §4.6 does support §6's non-POSIX-mount row, raised by all three lanes. |
| 2 | 2026-09-02 | 3, cold — identical brief, packet rebuilt from disk and extended with the onefile measurement, PRESS-0002 §4.6 and ADR-0004 § Consequences | 1 | 6 | 3 | 2 | **Twelve verified, twelve fixed, none dismissed. Cap reached (2 for a spec), and it is a VIOLENT cap** — about ten of the twelve landed on text loop 1 wrote, each anchor checked against loop 1's ledger rather than recall. So the review ends here and the document is routed to implementation rather than to a third loop; nothing in the run suggests a third would stop. **The root cause of half the loop is one thing loop 1 created**: it made `--self-check` serve three consumers — the release job's exit code, the pytest tests, the Windows box — and pinned neither its output nor its exit rule, so §6 promised a metadata-less bundle never ships while §10 said the Linux arm may skip. §4.5 now fixes three machine-readable lines and says a `store: file` answer is NOT a failure, because the program cannot tell no-store from lost-metadata. **The sharpest finding is that loop 1's own fix was circular**: it let INV-6's Linux arm skip where no store is present, and a metadata-less bundle produces exactly that observation — so the skip condition WAS the failure condition and INV-6 could never go red. §7 step 3 now CREATES the session rather than hoping for one. **Two findings were loop 1 breaking its neighbours:** §8 still rejected one-file for the `sys.executable` reason loop 1 had just deleted from §4.1, and loop 1's own Windows suite step made INV-2 and INV-3 fail on `windows-latest`, because neither fixture patched `sys.platform` and the win32 row is read first. Also fixed: `env -i` named as the Windows clean room, where that runner ships Python and no clean room can be made; INV-8 false on the `PRESSLESS_FOLDER` branch; a floor pin promising byte reproducibility; and a versioned filename in a README nothing updates. **A packet defect of mine, reported by all three lanes and recorded rather than hidden:** the PRESS-0001 and PRESS-0002 §4.1 windows were empty — a `#` comment inside a python fence read as a heading — so §2's quotation went unverified by lanes in both loops. I verified it by grep; the lanes could not, and raised it as an open question rather than a finding, which is them working. Resolved clean and not counted: libfuse locates `fusermount` by absolute path, so `env -i` does not break an AppImage mount. |
| 2-post | 2026-09-02 | **No reviewer was dispatched.** Author-side, after the cap, while answering the section 15 questions | 1 | 0 | 1 | 0 | **Two findings, two fixed. Not a review loop** — the gate ended at loop 2's violent cap and is not re-run; this row exists because a row no dispatched review produced is otherwise written by nobody. **Q1: `scripts/local-ci.sh` cannot run on `windows-latest` as section 7 step 1 requires it to**, and section 7 was written without checking the script. It invokes `python3`, a spelling the Windows installer does not create, and its leak sweep walks `git rev-list --all`, which a shallow clone answers falsely — the exact failure `ci.yml`'s own `fetch-depth: 0` comment describes. Both are now named in step 1 and in section 11 as this item's to fix. Found by reading the script after lane D asked whether it was runnable there and I asserted section 7 without opening it. **Q3: section 15's two questions are decided** by the user — the folder stays `Pressless-data`, and the Windows batch file stays because section 4.5's program prints and exits, so a bare double-clicked `.exe` would close before it could be read. Both moved to section 3 as decisions 5 and 6, and section 15 is now empty. **Verified separately and NOT a finding:** `windows-latest` (Server 2025) does ship Python 3.9 to 3.13, so section 7 step 2's claim that no clean room can be made there holds. |

## 13. Resource cost

A one-folder freeze of the current dependencies measures 63 MB on
Linux (`du -sh` over the frozen folder, PyInstaller 6.20.0, keyring
25.7.0, no Pillow). Pillow lands with PRESS-0016 and will raise it.
No cap is set: the artefact is downloaded once per release, and a cap
chosen now would be a number with no argument behind it.

The folder `ensure()` creates grows with the writer's photographs and
is bounded by his drive, which is the whole reason it sits beside the
artefact rather than under his home directory.

## 14. Migration / compatibility

**Scope decision 2 is the whole mechanism, and it reads differently on
each system.** On Windows the writer extracts over the old copy, so the
folder is already beside the new program folder. **On Linux nothing is
extracted**: each release is a differently-named file, so the rule is
that he saves the new AppImage into the same directory as the old one —
`own_folder` resolves beside the artefact, so same directory is what
makes it the same folder. Either way nothing migrates, nothing is
remembered, and nothing is searched for.

`docs/standards/versioning-overrides.md` § Setup state says nothing
there may be lost to an upgrade, and names S5 — the key asked for
exactly once. Extracting over the old copy satisfies it: the folder is
untouched, so `settings.json` and the credential are where they were.

**Where it is not satisfied is a writer who puts version 2 elsewhere**, and
that case is accepted rather than solved. §4.6 states it in the steps,
which is the only place it can be stated — the app cannot see where he
chose to extract, and §10 records that nothing checks it.

## 15. Open questions

**None.** Both were settled by the user on 2026-09-02 and are now
§3 decisions 5 and 6.
