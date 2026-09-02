# PRESS-0022 — Package Pressless into one artefact per system

**Status:** spec draft (2026-09-02).
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
deliberate.** Every public function in `settings.py` and
`credentials.py` — `settings.path_for`, `settings.load`,
`settings.save`, `credentials.read`, `credentials.write` — takes
`folder: Path` as its first argument and is handed it. PRESS-0001 §4.1
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
proportional to the bundle on an app opened daily, and leaves
`sys.executable` pointing at a bootloader. One-folder starts at once and
puts the executable where it actually lives, which §4.2 depends on.
The AppImage supplies Linux's single-file convenience without paying
for it twice.

### 4.2 Finding Pressless's own folder

A new module, `src/pressless/paths.py`. It is the caller that PRESS-0001
§2 says must exist, and it resolves downward only: the entry point asks
it for a folder and hands that folder to Settings and Credentials.

```python
class NotPackaged(Exception): ...      # cannot tell where we are
class FolderUnusable(Exception): ...   # found the place, cannot use it

def artefact_path() -> Path:
    """The file the writer double-clicked, or its folder on Windows."""

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

**PyInstaller is pinned in `pyproject.toml`, and nothing pins it
today.** It is named by `CLAUDE.md` § Build and test as a build-time
packager belonging beside the gate's tools rather than in
`dependencies`, and it appears in no manifest, no gate script and no
workflow. It gets its own optional-dependency group, so the two
release runners install the same packager as each other and as anyone
reproducing a build. A floor rather than a ceiling, matching the
reasoning already in that file for `keyring` and the gate's tools.

**The gate workflow is untouched.** `ci.yml` runs
`scripts/local-ci.sh` and holds no checks of its own; releasing is a
different trigger and a different file.

### 4.5 The program that gets packaged

`src/pressless/__main__.py`. It exists because packaging cannot be
proved without something to package, and it is deliberately the
smallest thing that proves it. PRESS-0013 replaces its body and changes
nothing in §4.1 to §4.4.

It answers the three questions an artefact must answer, prints each as
a line the writer could read aloud, and exits non-zero if any fails:

| Question | How it is answered |
|---|---|
| Did it start at all? | it printed, on a machine with no interpreter |
| Where is its folder, and can it be written? | `paths.own_folder()` then `paths.ensure()`, reporting the path |
| Which credential store answered? | `credentials.choose()`, reporting the member's name |

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

The steps say to extract over the previous copy (scope decision 2), and
say plainly what is lost by not doing so — that the writing sits beside
the old copy and is the one thing nothing backs up.

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
  patching `sys.frozen`, `sys.executable` and `$APPIMAGE` to a real
  file in a temporary directory; asserts the result is that file and
  is not a parent of `sys.executable`.
  *Breaks when:* the resolver falls back to `sys.executable` or
  `sys._MEIPASS` on Linux — the fixture separates them, so a resolver
  reading either returns the mount and fails.

- **INV-3** — `$APPIMAGE` naming a file that does not exist is treated
  as unset.
  *Test:* `tests/test_paths.py::test_stale_appimage_is_not_an_address`
  — set to a deleted path, expect `NotPackaged`.
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

- **INV-6** — The packaged artefact resolves a real credential backend
  on a machine that has one: `credentials.choose()` names a member, and
  does not raise `NoStore` or report the failure backend.
  *Test:* `tests/features/packaging/` — run the built artefact with
  `--self-check` and read the reported member.
  *Breaks when:* the bundle omits keyring's entry-point metadata. This
  is the check §4.3 says replaces PRESS-0068 item 1's build flags.

- **INV-7** — The artefact runs on a machine with no Python.
  *Test:* the clean-room step of §7 — `env -i PATH=/nonexistent` on
  Linux, and the Windows box, which has no interpreter by design.
  *Breaks when:* a build stops bundling the interpreter, or a runtime
  import reaches outside the bundle.

## 6. Failure modes

| When | What happens |
|---|---|
| `$APPIMAGE` unset or stale on a frozen Linux run | `NotPackaged`. Pressless stops and says it cannot tell where it is, naming what it looked for |
| The folder's parent is read-only or full | `FolderUnusable`, naming the path. Never a fallback (INV-5) |
| The folder is on a mount with no POSIX modes | `credentials.write` raises `NoStore` per PRESS-0002 §4.6 — correct, and newly reachable now that the writer chooses the drive |
| The bundle registers no credential backend | `--self-check` reports it and exits non-zero, so the release never ships (INV-6) |
| The writer extracts version 2 elsewhere | first-run setup, writing stranded beside version 1. Accepted (scope decision 2); §4.6 states it |
| A CI runner is unavailable | no release. ADR-0004 already names this as a concentrated dependency with no local route around it |

## 7. Tests

`tests/test_paths.py` locks INV-1 to INV-5 and runs in the ordinary
suite: they are all resolution rules, and patching `sys.frozen`,
`sys.executable` and the environment exercises every branch without a
build.

`tests/features/packaging/` locks INV-6 and INV-7 and does not run in
the ordinary suite — it needs a built artefact. It is marked
`packaging` and skipped cleanly when none is present, the way the
`archive` marker already works for tests needing the export.

**The release workflow runs the clean-room step on both runners**
before attaching anything: freeze, then run the artefact with
`--self-check` in an environment with no interpreter on the path. A
non-zero exit fails the release. finbreak's `windows-build.yml` carries
the same step and shows it can be automated rather than staged by hand.

**Staging to the Windows box stays, and is not replaced by the runner.**
The runner proves the bundle is complete; the box proves the writer's
own route works, from a downloaded zip to a double-clicked batch file.
Both PRESS-0001 §10 and PRESS-0002 §10 name that staging as the only
place their Windows rows are ever observed.

**Every test above must be seen failing before the code exists.** For
INV-6 that means a bundle built with keyring's metadata deliberately
withheld, which is the only way to know the check can fail at all.

## 8. Alternatives considered (and rejected)

- **One-file on both systems**, as finbreak does. Rejected for §4.1's
  reason: it costs an unpack on every launch and puts `sys.executable`
  on a bootloader rather than where the program lives. finbreak freezes
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
| INV-6 | `tests/features/packaging/`, run on both release runners. **Half on Windows:** the runner proves the bundle carries a backend, the test box proves the writer's own route, and the box is driven by hand |
| INV-7 | the clean-room step of §7, on both runners |
| §4.6's written steps, and therefore S4 | **nothing** — no check reads a README. `verify-instructions` executes such steps and is not scheduled anywhere in this project |
| §4.2's `Pressless-data` name | **nothing, and nothing needs to** — a name binds no code; §15 asks the writer |
| Scope decision 2's accepted risk | **nothing, and nothing can** — it fires on where the writer chose to extract, which the app never sees |

## 11. Cross-doc impact

- **README** — § Install gains the steps of §4.6.
- **CHANGELOG** — an Added entry, and the first release this item makes
  possible.
- **`pyproject.toml`** — a group pinning PyInstaller (§4.4), and a
  `packaging` marker declared beside `archive` so §7's build tests skip
  cleanly without one.
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

**Scope decision 2 is the whole mechanism: the writer extracts over
the old copy, and the folder is already there.** Nothing migrates,
nothing is remembered, nothing is searched for.

`docs/standards/versioning-overrides.md` § Setup state says nothing
there may be lost to an upgrade, and names S5 — the key asked for
exactly once. Extracting over the old copy satisfies it: the folder is
untouched, so `settings.json` and the credential are where they were.

**Where it is not satisfied is a writer who extracts elsewhere**, and
that case is accepted rather than solved. §4.6 states it in the steps,
which is the only place it can be stated — the app cannot see where he
chose to extract, and §10 records that nothing checks it.

## 15. Open questions

- **Is `Pressless-data` the right name for the folder the writer will
  see beside his download?** It is accurate and it does not collide
  with the extracted `Pressless/` folder on Windows. Nothing binds to
  it, so it is cheap to change before the first release and awkward
  afterwards.
- **Does Windows need the batch file at all?** One-folder puts
  `Pressless.exe` at the top of the extracted folder, so it can be
  double-clicked directly. The batch file was decided on 2026-08-26,
  before one-folder was chosen; it may now be an extra step rather
  than a convenience, or it may still earn its place by keeping the
  console open after §4.5's report.
