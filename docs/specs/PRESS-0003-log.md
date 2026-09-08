# PRESS-0003 — The rolling log: what Pressless writes down, and what it never does

**Status:** draft (2026-09-08).
**Kind:** implement.
**Source:** ROADMAP PRESS-0003 (`docs/design.md` § Logging, § Errors).

**Blocked by:** PRESS-0001, which is shipped.
**Blocker for:** PRESS-0011.

*Layman:* a plain diary of what the app did, kept beside the settings, that
never grows without limit and never contains anything that could identify the
writer or unlock his account.

## 1. Goal

After this ships, one small module writes a plain-English record of what
Pressless did, beside the settings file. The Face holds it open and calls it;
nothing else does (`docs/design.md` § Logging).

Two properties are the whole point. **It is bounded**: it rolls by size and
keeps exactly one old copy, so it cannot fill the drive the writer chose. And
**it never becomes a problem of its own**: a log that cannot be written is
silently not written, because the alternative is an app that refuses to publish
because it could not record that it published.

It reads no other part of Pressless, holds no secret, and touches no network.

## 2. Problem

`docs/design.md` § Logging says there is one rolling plain-English log beside
the settings, that the Face writes it, and that nothing shown or written down
carries a credential, an account name either secret is filed under, or a full
filesystem path. It does not say how large the log may grow, what the file is
called, or what happens when the disk refuses the write.

Those three are not detail an implementer settles equally well either way. An
unbounded log fills the drive the writer picked precisely because it had room
for his photographs. A log that raises turns a bookkeeping failure into a
publishing failure. And PRESS-0011 must name the file's location on screen,
which it cannot do without knowing what the file is called.

The identifying half is settled and is *not* this item's to enforce. The design
puts the obligation on the part that raises — `security.md` § 6, strip before
the call, not after — so by the time text reaches this module it is already
clean. Bringing the shipped messages into line is PRESS-0068 item 4 and
PRESS-0087, both open. This module's own contribution is narrower and stated as
INV-1: it adds nothing to what it is given.

## 3. Scope decisions (agreed with the user)

1. **The log rolls by SIZE, keeping exactly one old copy** — decided
   2026-09-08. Past a set size the file is renamed and a fresh one started.
   Bounded on disk forever, no clock needed, and the two files together always
   cover the recent past.

   Rolling by day was rejected: a single busy day is unbounded, and it drags in
   date handling this module does not otherwise need. See § 8.

2. **The size is set here rather than in `docs/design.md`** — that document
   records the policy and delegates the number, because the number is the kind
   of thing that moves and the policy is not.

3. **The location is shown to the writer as a label, never as a path** —
   decided 2026-09-08, and owned by `docs/design.md` § Errors. This spec fixes
   the file's name so PRESS-0011 has something to label, and nothing more.

4. **This item does not clean up the shipped failure messages.** The rule they
   must meet is in `docs/design.md` § Logging; applying it to
   `credentials.py` and `settings.py` is PRESS-0068 item 4 and PRESS-0087.
   Absorbing them here would leave both ids pointing at nothing.

## 4. Design

### 4.1 Public surface

```python
FILE_NAME = "pressless.log"
OLD_NAME = "pressless.log.1"   # what the rolled copy is called
MAX_BYTES = 1_048_576          # one mebibyte; § 4.3 owns the choice
OLD_COPIES = 1                 # exactly one, per § 3 decision 1

def path_for(folder: Path) -> Path: ...       # folder / FILE_NAME
def open_log(folder: Path) -> Log: ...        # never raises

class Log:
    def note(self, message: str) -> None: ...  # never raises
    def close(self) -> None: ...               # never raises
```

`path_for` mirrors `settings.path_for` deliberately: the same argument, the
same shape, the same folder. The Face already holds that folder.

### 4.2 What a line looks like

A line is a timestamp and the message it was handed, and nothing else:

```
2026-09-08 14:02:11 published 587 files
```

The timestamp is local time, seconds precision. It identifies nobody, and it is
what makes two runs distinguishable in a file the helper reads.

**`note` adds nothing to the message.** It does not append context, the
settings, the folder, or the machine's name. That is INV-1, and it is the whole
of this module's contribution to the identifying rule — everything else is
settled before the call reaches here.

### 4.3 Rolling

`logging.handlers.RotatingFileHandler` with `maxBytes=MAX_BYTES` and
`backupCount=OLD_COPIES`. It is the standard library's own implementation of
exactly the decided policy, it adds no dependency, and it names the old copy
`pressless.log.1`.

Measured 2026-09-08 on Python 3: forty lines written through a handler with
`maxBytes=200, backupCount=1` left exactly two files, both bounded. Repeated
rolls do not accumulate a `.2`. The conformance test in § 7 is that measurement
at the shipped size.

**One mebibyte is a preference call, made here.** It is large enough that an
ordinary session's record survives a roll, and small enough that two files are
an unremarkable amount of disk beside the photograph originals the same folder
holds. Nothing measures it; a different number would work, and the reason it is
written down is so PRESS-0011 and the writer's helper can rely on the file not
growing without limit.

### 4.4 Failure

**Every entry point swallows every exception**, and this is the design's one
genuinely load-bearing decision. Its reasoning:

The log records what Pressless did. If recording fails, what Pressless did is
unaffected. A module that raised here would convert "the disk is full" during
bookkeeping into a failed publish, and § Errors would then owe the writer a
sentence about a failure that changed nothing about his site. There is no
message worth writing for it.

So `open_log` on an unwritable or missing folder returns a `Log` that accepts
`note` calls and writes nothing. The caller cannot tell, and must not need to.

**This is the reason the module holds no invariant about the folder existing.**
Creating it is setup's job, and `docs/design.md` § Where everything sits on
disk already says Pressless stops when it cannot be created. A log that created
the folder would mask that stop.

### 4.5 What it does not do

No network (INV-5). No reading of Settings or Credentials (INV-1). No levels,
no filtering, no configuration — a plain-English record has one kind of line.

## 5. Invariants

- **INV-1** — `note` writes the timestamp and the message it was given, and
  nothing else. `src/pressless/log.py` imports no other `pressless` module and
  no credential library.
  *Test:* `tests/test_log.py::test_note_adds_nothing` — write a known message
  to a real file, read it back, and assert the line is the timestamp and that
  message with nothing appended. Plus
  `tests/test_log.py::test_log_imports_nothing_identifying`, walking the
  module's imports as
  `tests/test_settings.py::test_settings_imports_nothing_forbidden` does.
  *Breaks when:* someone adds context to a line — the settings, the folder,
  the repository, the machine name — or the module gains an import of
  `pressless.settings`, `pressless.credentials` or `keyring`, any of which
  puts an identifying value one attribute access from a log line.
  **The import walk is the weak half**, in the way PRESS-0002's INV-1 records
  of its own: it passes against a module that does nothing.
  `test_note_adds_nothing` is what carries this invariant.

- **INV-2** — The log and its one old copy are the only files the module
  creates, and rolling never accumulates a third.
  *Test:* `tests/test_log.py::test_rolls_by_size_keeping_one_old_copy` — write
  well past `MAX_BYTES`, then assert the folder holds **exactly** the two
  names `pressless.log` and `pressless.log.1`, and that no `pressless.log.2`
  exists.
  *Breaks when:* `backupCount` is not 1, so a `.2` accumulates and the bound
  is gone; or `maxBytes` is left at `RotatingFileHandler`'s own default of 0,
  which disables rolling entirely and produces one unbounded file.
  **Asserting the exact file set is what makes it bite:** a test asserting
  merely that `pressless.log.1` exists passes just as well with a `.2` beside
  it, which is the unbounded case wearing the bounded case's clothes.

- **INV-3** — No call raises, whatever the filesystem does.
  *Test:* `tests/test_log.py::test_note_survives_an_unwritable_folder` and
  `tests/test_log.py::test_open_log_survives_a_missing_folder` — call
  `open_log` and `note` against each, and assert no exception escapes and that
  execution continues past the call.
  *Breaks when:* an entry point gains a code path outside its `except`, or a
  future author decides a missing folder is worth reporting to the caller.

- **INV-4** — The log sits in the same folder as the settings file.
  *Test:* `tests/test_log.py::test_log_sits_beside_the_settings_file` —
  assert `path_for(folder).parent == folder`, and that the file lands beside a
  `settings.json` written into the same folder. The test writes the name
  `"pressless.log"` out rather than importing `FILE_NAME`, per this project's
  rule: sharing the literal compares the module against itself.
  *Breaks when:* someone gives the log a subdirectory of its own, which puts
  it outside the folder `docs/design.md` § Where everything sits on disk
  places it in, and outside the folder PRESS-0011's label names.

- **INV-5** — The module touches no network.
  *Test:* `tests/test_log.py::test_log_is_offline`, walking the module's
  imports for `socket`, `http`, `urllib` and `requests` as
  `tests/test_marks.py::test_marks_is_pure` does.
  *Breaks when:* a future author adds remote error reporting.
  **Weak in the same way INV-1's import walk is**, and recorded as such rather
  than relied on.

## 6. Failure modes

| What happens | What the module does | What the writer sees |
|---|---|---|
| The folder does not exist | `open_log` returns a Log that writes nothing | Nothing. Setup already stopped for this (`docs/design.md` § Where everything sits on disk) |
| The folder is not writable | The same | Nothing |
| The disk fills mid-session | `note` swallows it; earlier lines remain | Nothing. His publish is unaffected |
| The file is deleted while open | `note` swallows it | Nothing |
| The rolled copy cannot be replaced | `note` swallows it; the current file keeps growing past `MAX_BYTES` | Nothing. Bounded-ness is lost until the next successful roll, which INV-2 does not cover and § 9 records |

## 7. Tests

`tests/test_log.py`, unlabelled — it declares no custom marker and needs
nothing beyond a temporary directory, so it runs in CI unlike the three
archive tests. One test per invariant, named in § 5; § 10 tabulates those and
the checks holding claims that are not invariants.

**Every test writes to a real temporary directory rather than a double.** The
module's whole job is what reaches the filesystem — rolling, the file set it
leaves behind, and surviving a directory it cannot write. A double would assert
the calls this module makes to the standard library, which is the
implementation restated, and would pass against a module that rolls wrongly.

**Two tests need a directory the process cannot write, and that is the one
awkward fixture here.** `chmod` is the route on Linux; on Windows it sets only
the read-only flag, which `PRESS-0002` § 4.6 already measured and which is why
that spec has no fallback file there. Where the unwritable state cannot be
produced, the test skips **naming that reason** — never silently, per this
project's rule that a skip reporting every cause as one cause can hide a
failure.

**The literals under test are written out, not imported.** A test importing
`FILE_NAME` compares the module against itself, so `path_for` could name any
file and stay green. This project already carries that rule for
`tests/test_settings.py` and its `"settings.json"`; do not tidy either into an
import.

## 8. Alternatives considered (and rejected)

**Roll by day.** Rejected by the user 2026-09-08. A single busy day is
unbounded, which loses the one property this design is for, and it needs date
handling the module otherwise does not.

**Keep more than one old copy.** Rejected with the same decision. Two files
cover the recent past; more of them buy history nobody reads and cost the
bound's simplicity.

**Let `note` raise, and have the Face decide.** Rejected here (§ 4.4). It
converts a bookkeeping failure into a publishing failure, and § Errors would
owe a sentence about a failure that changed nothing.

**Scrub identifying text at the log, as a last line of defence.** Rejected:
`security.md` § 6 is *strip before the call, not after* — "a redaction that
happens downstream has already written the value somewhere" — and
`docs/design.md` § Logging places the obligation on the part that raises. A
scrubber here would also make the design's rule look enforced when it is not,
which is worse than its absence.

## 9. Out of scope

- **Cleaning up the shipped failure messages** in `credentials.py` and
  `settings.py` that carry a path or an account. PRESS-0068 item 4 and
  PRESS-0087.
- **The Face's Show details toggle** and the label naming this file's location.
  PRESS-0011.
- **Recovering boundedness after a failed roll.** § 6's last row: if the roll
  itself cannot be performed, the current file grows until one succeeds. No
  invariant covers it and no test proves it, recorded here rather than implied.
- **Anything a level system would buy** — filtering, verbosity, separate error
  files.

## 10. What checks this

| Claim | What checks it |
|---|---|
| INV-1 | `test_note_adds_nothing`; `test_log_imports_nothing_identifying` partially |
| INV-2 | `test_rolls_by_size_keeping_one_old_copy` |
| INV-3 | `test_note_survives_an_unwritable_folder`, `test_open_log_survives_a_missing_folder` |
| INV-4 | `test_log_sits_beside_the_settings_file` |
| INV-5 | `test_log_is_offline` |
| One mebibyte is the right size | **nothing** — a preference call (§ 4.3), and no test can hold it |
| The log is readable as plain English by the writer's helper | **nothing** — it depends on what callers write, which is PRESS-0011's |
| No credential reaches the file | **nothing here.** INV-1 stops this module adding one; a caller passing one is not something this module can see. The obligation is the raise site's (`docs/design.md` § Logging) |
| Boundedness after a failed roll | **nothing** — § 9 |

## 11. Cross-doc impact

- `docs/design.md` § Logging delegates the size to "the spec"; § 4.3 is what it
  delegates to.
- PRESS-0011 binds to `FILE_NAME` and to the file's folder, for the label its
  Show details toggle carries.
- PRESS-0068 item 4 and PRESS-0087 apply the identifying rule to the shipped
  raise sites; this spec's § 2 and § 9 record that it does not.
- No change is owed to `docs/discovery.md`: the log serves no sign of success
  on its own, which PRESS-0003's own roadmap bullet already records.

## 12. Cold-eyes loop log

See `docs/reviews/PRESS-0003-log-loop-log.md`.
