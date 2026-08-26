# PRESS-0001 — Settings: what is true of this machine, and nothing else

**Status:** accepted (2026-08-25). Two cold-eyes loops, both folded in, nothing deferred — the run reached the spec cap of 2 and every verified finding is fixed. A calm cap: only three of the last loop's findings landed on text the run itself wrote, so the document held more defects than the cap held loops rather than the run repairing itself. Implementation is the third reviewer.
**Kind:** implement.
**Source:** ROADMAP PRESS-0001 (`docs/design.md` § The parts; ADR-0003).

**Blocker for:** PRESS-0002, PRESS-0003, PRESS-0005, PRESS-0008, PRESS-0009,
PRESS-0011, PRESS-0019.

*Layman:* the small file that remembers where the site lives on this
machine and which site to publish to, so nothing else has to be told twice.

## 1. Goal

After this ships there is one place that holds the facts about *this
machine and this site* — where the finished site folder is written, which
repository it is published to, which tag the Builder filters, which paths
in that repository are not ours to touch, where the two credentials are
kept, and the Analytics property id. Every part but Marks reads it — Marks is
pure calculation and reads nothing. Settings itself reads nothing else: no
Store, no network, no other part of Pressless.

## 2. Problem

Nothing holds these facts yet, and six parts need them before they can be
written. `docs/design.md` § The parts gives Settings the row *"Deliberately
knows nothing about: everything. It depends on nothing"*, and every rule in
§ What may depend on what that mentions another part starts by granting it
Settings.

Three things make this a contract rather than a file format.

1. **Other code binds to the key names.** The Builder reads the site folder
   and the Daily Prompt filter, the Publisher reads the repository and the
   untouchable list, Insights reads the Analytics id, and PRESS-0002 reads
   where the credentials are kept. A key renamed later is a rename across
   six parts.
2. **One of the fields is a safety boundary, not a preference.**
   `docs/design.md` § What may depend on what states the rule the untouchable
   list is the output of — *every entry at the repository root that the
   Builder does not produce* — and names what deleting two of those entries
   costs: the custom domain detaches, and the site silently un-verifies in
   search results months later. The Publisher is defined as the part that
   *"must not be able to tell an entry from a stylesheet"*, so it has nothing
   to decide with and this list is the whole of its protection.
3. **It is an on-disk shape the writer's installation carries forward.**
   Getting it wrong is not a rebuild; it is a migration on a machine we do
   not have.

**And Settings must not become the part that knows where it is.** The
roadmap bullet records the decision that Pressless's own folder sits beside
the program file, and that PRESS-0022 owns finding that location — which on
an AppImage is not the running process's own path. A Settings that resolved
its own path would depend on PRESS-0022 and break its own row in § The parts.

## 3. Scope decisions (agreed with the user)

Four choices below were preference rather than deduction. **The first was put
to the user on 2026-08-25 and answered; the other three were made by this
session.** §8 carries what each beat.

1. **The file is JSON, named `settings.json`, and the writer never opens
   it.** Asked and answered 2026-08-25: the settings file is the app's own
   record, changed through Pressless's screens rather than by hand. That
   removes the one argument for TOML — comments he would read — and TOML has
   no standard-library writer, so it would cost a bundled dependency against
   `docs/design.md` § The stack, and what it rules out.
2. **Settings is handed its folder; it never derives one.** The caller passes
   the directory. This keeps § The parts' *depends on nothing* true and keeps
   the AppImage location problem inside PRESS-0022.
3. **A key Settings does not recognise is preserved on save.** A newer
   Pressless must be able to write a key an older one then saves over without
   losing it.
4. **An absent untouchable list is an error; an empty one is valid.** They are
   different facts — *nobody has derived the list* and *the repository root
   holds nothing the Builder does not produce* — and defaulting the first to
   the second is what lets a half-finished setup delete his `CNAME` on the
   next publish.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/settings.py

@dataclass(frozen=True)
class Settings:
    site_folder: Path            # where the Builder writes the finished site
    repository: str              # "owner/name" on GitHub
    daily_prompt_filter: str     # fnmatch glob, matched per tag -- see below
    untouchable: tuple[str, ...] # repository-root entries the Publisher leaves alone
    credentials: Credentials     # where the two secrets are kept -- never the secrets
    analytics_property_id: str | None

@dataclass(frozen=True)
class Credentials:
    store: str                   # "keyring" or "file" -- ADR-0003's two paths
    github_account: str          # the keyring account name, or the file's key name
    google_account: str | None   # None where the dashboard was declined

def load(folder: Path) -> Settings: ...
def save(folder: Path, settings: Settings) -> None: ...
def path_for(folder: Path) -> Path: ...      # folder / "settings.json"

class NotSetUp(Exception): ...               # no file yet -- run setup
class SettingsError(Exception): ...          # a file we will not act on
```

`folder` is Pressless's own folder, supplied by the caller. Settings does
not create it, search for it, or fall back to another one.

### 4.2 The file

```json
{
  "version": 1,
  "site_folder": "/home/writer/Pressless/site",
  "repository": "owner/owner.github.io",
  "daily_prompt_filter": "dailyprompt-*",
  "untouchable": ["CNAME", ".nojekyll", "README.md"],
  "credentials": {
    "store": "keyring",
    "github_account": "publishing-key",
    "google_account": "analytics"
  },
  "analytics_property_id": "123456789"
}
```

**`version` is the file's, not the dataclass's.** `save()` always writes
`version: 1`; `load()` requires it, accepts `1`, and raises `SettingsError`
naming the value for anything else — a file written by a later Pressless is not
one this build may guess at. It is deliberately not a `Settings` field, so
INV-6's field set does not carry it, and §4.4's carry-through does not reach it
either: `version` is written from the schema, never from what was read.

**`analytics_property_id` holds the numeric property id, not the `G-…`
tag.** Google's reporting interface is addressed by the number. The tag in
the site's footer is a different identifier and fails every fetch; Pressless
never writes that tag, so it does not hold one.

**Two fields carry a declined dashboard, and both are optional:
`analytics_property_id` and the `google_account` inside `credentials`.**
ADR-0005 makes that step declinable — *"he can decline the Google step and
lose the dashboard and nothing besides"* — so requiring the Google account
name would leave a declined setup unable to load at all, which is the wall
that ADR forbids. **Absent and `null` both load as `None`. Every other key
must be present.**

`daily_prompt_filter` is an **`fnmatch` glob matched against each tag,
case-sensitively** — not a regex, not a prefix. `docs/design.md` § What may
depend on what pins the target as WordPress's own `dailyprompt-NNNN` tag, and
**the two readings are not merely different, they are inverted.** Measured:

| tag | `fnmatch.fnmatchcase(tag, "dailyprompt-*")` | `re.fullmatch("dailyprompt-*", tag)` |
|---|---|---|
| `dailyprompt-1234` | `True` — excluded | `False` — published |
| `dailyprompt` | `False` — published | `True` — excluded |

A regex reading therefore publishes what the writer asked to be filtered and
filters entries that are his own tagging habit. The glob is the contract.

`site_folder` is **absolute**, as the example shows. It is the writer's own
choice of where the built site goes and may sit on another drive entirely, so
it is never resolved against `folder`.

The `untouchable` values above are illustrative. The real ones are the
output of § What may depend on what's rule, derived at setup against the
live repository root.

### 4.3 Loading

`load()`'s outcomes, and they are distinguishable:

| State | Result |
|---|---|
| No file at `path_for(folder)` | `NotSetUp` |
| File present, not valid JSON | `SettingsError`, naming the file |
| Valid JSON, a required key missing or the wrong type | `SettingsError`, naming the key |
| Valid JSON, `version` absent or not `1` | `SettingsError`, naming the value |
| Valid JSON, a value whose *shape* is wrong — `repository` not `owner/name`, `credentials.store` outside `"keyring"` and `"file"` | `SettingsError`, naming the key |
| Valid | `Settings` |

**The shape row is why this is a list rather than four cases.** `repository`
and `store` are contracts other parts read, not free strings: a `str` holding
`"ownername"` or `"vault"` is present and correctly typed, so without the row
`load()` accepts it and the Publisher or PRESS-0002 meets it later, with less
to say about it.

**Nothing in the failing rows writes.** A file we could not read is a file
we do not overwrite: the writer's settings are recoverable by hand only as
long as they are still there.

### 4.4 Saving

`save()` writes to a temporary file in the same directory and replaces the
target with `os.replace`, which is atomic on both systems. A crash mid-save
leaves either the old file or the new one, never a truncated one.

Keys `load()` did not recognise are carried through unchanged. `save()`
therefore reads the existing file before writing, and a save over an
unreadable file raises rather than discarding what it could not parse.

**No existing file is not an error.** The first save, at setup, has nothing to
read and nothing to carry through, and writes a new file. `load()`'s `NotSetUp`
is about loading; it never reaches `save()`. An existing file that cannot be
parsed raises rather than being silently discarded — and §6 carries `save()`'s
other failures, which this rule does not speak for.

### 4.5 What Settings never holds

No secret value, ever — only the store name and the account names under which
ADR-0003's keyring or fallback file holds them. Settings is written to
disk in plain text beside the program; a key in it would sit outside the
protection ADR-0003 exists to provide.

**And no path to the fallback file.** `store: "file"` names ADR-0003's weaker
path rather than a location: where that file lives is PRESS-0002's, which owns
both stores. A path recorded here would be invalidated by the very move
Settings must survive — the program file's, which `folder` follows. That
reasoning is about **Pressless's own** files and does not reach `site_folder`,
which is the writer's choice of somewhere else and is stored absolute.

## 5. Invariants

- **INV-1** — `src/pressless/settings.py` imports no network module and no
  other `pressless` module. Named modules on purpose: an import list sees what
  is imported and not what it is used for, so *reaches no disk but its own
  file* is not a rule this test could carry — §4.4 requires `os`, and `os`
  reaches every disk there is. INV-7 is what holds the path rule.
  *Test:* `tests/test_settings.py::test_settings_imports_nothing_forbidden`,
  walking the module's imports as
  `tests/test_marks.py::test_marks_is_pure` does — which bans `os` outright,
  and is the precedent rather than the rule here.
  *Breaks when:* an implementer imports `pressless.publisher` to validate the
  repository name, or `urllib` to check it exists.

- **INV-2** — `load()` on a folder with no settings file raises `NotSetUp`,
  and on a file that is present but unreadable raises `SettingsError`.
  Neither is the other.
  *Test:* `tests/test_settings.py::test_absent_and_unreadable_differ` — two
  temporary folders, one empty, one holding `settings.json` containing `{`.
  *Breaks when:* an implementer catches both as "no usable settings" and
  sends the writer to setup, which then overwrites the file he could have
  fixed. The fixture isolates this rule alone: a folder with no file and a
  folder with a broken file are both rejected by every other rule here, so
  only the requirement that the two outcomes *differ* can fail it.

- **INV-3** — An absent `untouchable` key is a `SettingsError`. An
  `untouchable` key present and empty loads.
  *Test:* `tests/test_settings.py::test_untouchable_absent_is_an_error` — two
  files differing only in whether the key is present.
  *Breaks when:* an implementer gives the field a default of `()`. Both
  fixtures are otherwise complete and valid, so no other rule rejects
  either one — the pair fails only if this rule is missing.

- **INV-4** — A key `load()` does not recognise is present, unchanged, in
  the file after a `save()` of the loaded value.
  *Test:* `tests/test_settings.py::test_unknown_keys_survive_a_save`.
  *Breaks when:* `save()` is written from the dataclass alone rather than
  over the file's existing contents.

- **INV-5** — `save()` never leaves a file that `load()` rejects. After a
  save interrupted before completion, the file on disk is the previous one.
  *Test:* `tests/test_settings.py::test_save_is_atomic` — assert `save()`
  reaches `os.replace` with `path_for(folder)` as its destination, then patch
  the write to raise before that call and confirm `load()` still returns the
  previous value.
  *Breaks when:* an implementer opens the target file directly and writes into
  it. **Asserting the mechanism is what makes the fixture bite:** against a
  direct write there is no replace to interrupt, so the interruption half on
  its own would pass green against the implementation it exists to reject.

- **INV-6** — The field names of `Settings` and `Credentials` are exactly
  the set §4.1 lists.
  *Test:* `tests/test_settings.py::test_field_names_are_the_documented_set` —
  compare both dataclasses' field names against a literal set in the test.
  *Breaks when:* someone adds `github_token` "just for the fallback path",
  which is where ADR-0003's weaker path already keeps it; or renames a key
  six other parts read. Stated as the whole set rather than as "no secret
  field" on purpose: *no secret field* passes against every settings value
  that happens not to have one, so only a rule about the set itself can fail
  when a field is added.

- **INV-7** — `load()` and `save()` open no path outside `folder`, and leave
  nothing inside it but `path_for(folder)`. §4.4's temporary file is the one
  permitted extra path and is gone once `save()` returns.
  *Test:* `tests/test_settings.py::test_only_touches_its_own_file` — patch the
  filesystem calls both functions make, require every path opened to sit under
  `folder`, then list the folder afterwards.
  *Breaks when:* a search for a settings file in a parent directory or the home
  directory is added, which is scope decision 2 undone. **Listing the folder
  cannot catch that**: a read elsewhere leaves the listing identical, which is
  why the test asserts the paths opened rather than the folder's contents.

## 6. Failure modes

- **The folder does not exist.** `load()` raises `NotSetUp`; `save()` raises
  `SettingsError` rather than creating a tree, because a mistyped folder is
  indistinguishable from a missing one and the wrong answer is a second set
  of settings nobody finds.
- **`site_folder` names a path that is gone.** `load()` succeeds. Settings
  records what it was told; the Builder is the part that discovers the
  folder is missing and PRESS-0011 owns what the writer is told. Validating
  it here would put a filesystem question in the part that depends on
  nothing.
- **`repository` names a repository that is not there.** §4.3 rejects the
  wrong *shape*; existence is not checked at all, because checking it needs
  the network. The Publisher is where a well-formed name with nothing behind
  it surfaces.
- **The file or its folder cannot be written.** `save()` reports whatever the
  write raises, as a `SettingsError` naming the path, and does not probe
  permissions first. **A read-only settings *file* is not that state on
  Linux.** Measured: `os.replace` onto a mode-444 target in a writable
  directory succeeds and replaces it, where a direct `open('w')` on the same
  file raises `PermissionError`; on Windows the replace itself raises. So
  §4.4's mechanism decides this, the folder's permissions are what bite on
  Linux, and a settings file copied read-only from another machine is replaced
  rather than refused.
- **Two Pressless windows save at once.** The last write wins, whole.
  §4.4's replace is what makes "whole" true; nothing here makes it "both".

## 7. Tests

`tests/test_settings.py`, unlabelled — it needs no fixture beyond a
temporary directory and must run everywhere, unlike the archive test
PRESS-0004 carries.

One test per invariant, named in §5. **The red run is made against a stub
`settings.py`, never against an absent one.** With the module absent the suite
errors at collection and collects nothing, so no assertion runs — this
project's own `CLAUDE.md` records that trap, and calling that error a red run
is the substitution it forbids. The stub declares every name in §4.1 and raises
`NotImplementedError` from each function, so every test is collected.

**Not every test then fails, and that is by design.** A stub declaring §4.1's
names and importing nothing forbidden already satisfies INV-1 and INV-6, whose
tests read the module's imports and its field names rather than its behaviour.
The red run is every test collected with the behavioural ones failing on
assertions; INV-1's or INV-6's going red against the stub means the stub is
wrong, not the test. Read the collected count, not the exit code.

**INV-1's test is the weak one, and it is weak in a way this project has
already met.** Reading an import list proves what the module imports, not
that it works — the same shape as `test_marks_is_pure`, which `CLAUDE.md`
records as passing against an empty file. It is worth having because the
rule it locks is about imports, and it must not be read as evidence that
loading or saving does anything.

## 8. Alternatives considered (and rejected)

- **TOML.** Friendlier to hand-edit and comment. The standard library has no
  TOML writer, so saving would need a dependency, against
  `docs/design.md` § The stack, and what it rules out. Its one advantage is
  comments the writer would read, and §3 decision 1 settled that he does not
  open the file. Revisit only if that changes.
- **An INI file.** No list type, so `untouchable` would become a delimited
  string and a path containing the delimiter would silently split.
- **A Python module as config.** Executable settings, and the file sits
  beside a program that publishes to the writer's live site.
- **Settings finds its own folder.** Breaks § The parts' *depends on
  nothing*, and duplicates the AppImage location problem PRESS-0022 owns.
- **Settings checks that the paths and the repository it holds EXIST.** Every
  such check needs a disk or a network, both of which its row forbids; the
  parts that already have them are the ones that can report usefully. §4.3's
  shape row is not this: shape is decidable from the string alone.
- **Storing the untouchable rule instead of its output.** The rule needs the
  repository root to evaluate, which is a network read. Settings holds the
  output and §4.2 records that the rule is the contract.

## 9. Out of scope

- Deriving the untouchable list against the live repository — the derivation
  needs GitHub, and it belongs to setup; tracked by PRESS-0021.
- Finding Pressless's own folder from the running program — tracked by
  PRESS-0022.
- Reading and writing the secrets themselves — tracked by PRESS-0002.
- What the writer is shown when loading fails — the error contract is
  tracked by PRESS-0011.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_settings.py::test_settings_imports_nothing_forbidden` |
| INV-2 | `tests/test_settings.py::test_absent_and_unreadable_differ` |
| INV-3 | `tests/test_settings.py::test_untouchable_absent_is_an_error` |
| INV-4 | `tests/test_settings.py::test_unknown_keys_survive_a_save` |
| INV-5 | `tests/test_settings.py::test_save_is_atomic` |
| INV-6 | `tests/test_settings.py::test_field_names_are_the_documented_set` |
| INV-7 | `tests/test_settings.py::test_only_touches_its_own_file` |
| The key names other parts bind to (§4.1) | **half** — INV-6 fails on a rename here, so it cannot happen by accident. Nothing makes the consuming part follow: each reads the key independently, and a shared constant would be a part depending on Settings' internals, which § What may depend on what rule 7 forbids. PRESS-0008 is the first consumer that would notice |
| The untouchable list actually protecting the repository root (§2) | **nothing here** — Settings holds the list and cannot check it is obeyed; the Publisher is where a breach shows, tracked by PRESS-0009 |
| §4.3's `version` and shape rows | **nothing** — no invariant locks them, so an implementer could drop either row and this suite stays green. They are the two rejections whose absence is silent: a missing `version` makes the file unreadable by the next Pressless, and a malformed `repository` or `store` reaches PRESS-0009 or PRESS-0002 as a value they did not expect. Worth an invariant if either is ever seen to slip |
| §4.4's atomic replace on Windows | **nothing** — `os.replace` is documented atomic on both, and this suite runs on Linux. PRESS-0022 stages the built executable to a Windows box and runs it there before release, which is the only place this would be observed; it schedules no check of its own |

## 11. Cross-doc impact

- `docs/design.md` § The parts — its Settings row enumerates what Settings
  holds and does not name the Analytics id. It gains it.
- `docs/decisions/ADR-0003` — its text covers the publishing key alone, and
  the widening to both credentials is recorded only in PRESS-0002's roadmap
  bullet. This spec leans on it for both, so the ADR gains the Google
  authorisation.
- `CLAUDE.md` — the state block only. This suite needs no environment
  variable, so § Build and test's note about the one test that does is
  unchanged.
- `CHANGELOG.md` — an entry when it ships.
- No sibling spec changes. PRESS-0004 does not read Settings.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-25 | 3, cold — genre pinned `spec`, packet carried the design rules, ADR-0003 and ADR-0005 verbatim, and the tree's real test and packaging facts | 1 | 4 | 4 | 4 | **Thirteen verified, TWELVE fixed, one escaped; one dismissed as inert.** *(Q2 and the counts corrected while writing loop 2's row — see that row's opening. This row first read "twelve verified, twelve fixed", which was false: a verified Q2 was never fixed.)* **All three lanes independently found the same two**, which is the strongest signal in the run. INV-7 said `load()` and `save()` act on `path_for(folder)` "and on no other path" while §4.4 requires a temporary file and a replace — so the two invariants could not both be satisfied, and an implementer holding INV-7 literally writes the non-atomic implementation INV-5 exists to forbid. And §7 demanded the red run be "seen to fail against the absent module", which this project's own `CLAUDE.md` says is impossible: with the module absent the suite errors at collection and no assertion runs, so the clause required exactly the substitution the sentence it cited forbids. The red run is now made against a stub raising `NotImplementedError`. **The best single finding came from one lane and got worse when measured.** `daily_prompt_filter` never pinned its matching language, and the Builder binds to it. Run rather than reasoned: `fnmatch.fnmatchcase` and `re.fullmatch` are not merely different on the two live tag shapes, they are **inverted** — a regex reading publishes the `dailyprompt-NNNN` entries the writer asked to filter and filters the bare-`dailyprompt` entries that are his own. The glob is now the contract, with the measurement in §4.2. **Three more Q4s were fixtures that could not catch the breach they named**: INV-5 patched an interruption that never fires against a direct write, INV-7 listed a folder to catch a read somewhere else, and INV-1 asked an import list to enforce "reaches no disk but its own file" while §4.4 requires `os`. **One Q2 would have locked a writer out of his own app**: `credentials.google_account` was required, and ADR-0005 makes the Google step declinable "or it becomes a wall". **Two Q3s were the first-ever call**: `save()` with no existing file was specified nowhere though setup binds to it, and nothing said where ADR-0003's fallback file lives. **One finding was this loop's own collateral**, caught by the post-fix re-read: making `google_account` optional left §4.5 still saying "the two account names". **Dismissed as true-but-inert** (found by a lane and filed as an open question rather than a finding, correctly): §2 claims every dependency rule mentioning another part grants it Settings, and rules 1, 2, 3, 7 and 9 do not — false, and no line of the built thing changes, so recorded rather than fixed. |
| 2 | 2026-08-25 | 3, cold — identical brief, packet rebuilt from disk and given the measured `fnmatch`-versus-regex table, which no lane can run for itself | 2 | 5 | 3 | 0 | **Ten verified, ten fixed. Cap reached (2 for a spec); the run files its tail and ships.** **It opens with a correction to loop 1's own row.** Reconciling the ledger before writing this one showed loop 1 verified THIRTEEN findings and fixed twelve: a lane's Q2 on `repository` shape was verified and then dropped while merging, and the row asserted a clean twelve-for-twelve. Loop 2's lanes found it again independently, which is the only reason it is here. The row above is corrected rather than left standing. **The best finding is a self-defeating loop two lanes found in the file shape.** `version` was documented as a required key of the file and was not a field of `Settings`, while INV-6 pins the field set to exactly §4.1's list — so `save()` built from the dataclass writes a file with no `version`, which the very next `load()` must reject. Setup would have produced a file the app could not open. §4.2 now makes `version` the file's rather than the dataclass's, written from the schema and checked on load, and §4.3 gains the row. **One Q1 was settled by running it rather than reading it.** §6 claimed `save()` raises on a read-only file; §4.4 specifies a temporary file and `os.replace`. Measured here: the replace onto a mode-444 target in a writable directory SUCCEEDS and silently replaces it, where a direct `open('w')` on the same file raises `PermissionError` — so the document required one behaviour and its own mechanism delivered another on the platform it is developed on. Two lanes reached it by reading POSIX semantics and both flagged that it needed a run. **Three of the ten landed on text THIS RUN wrote** — the stub red run, §4.5's over-wide principle and §4.4's over-claiming *only*-clause were all loop 1 fixes. That is a low share, so this is a CALM cap: the document held more defects than the cap held loops, and shipping is right rather than the run oscillating. **Four open questions across the three lanes resolved clean and are not counted**: `test_marks_is_pure` does ban `os` outright, and two lanes independently opened the roadmap and confirmed PRESS-0022 owns both the program-file location step and the Windows staging this document attributes to it. |
