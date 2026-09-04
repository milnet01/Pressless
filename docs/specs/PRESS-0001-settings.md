# PRESS-0001 — Settings: what is true of this machine, and nothing else

**Status:** accepted (2026-09-04). A third run of two cold-eyes loops, both folded in; the tail is empty. A violent cap — a majority of the last loop’s findings landed on text the run itself wrote, so the review ends here and the document routes to implementation rather than to a further gate. What the run mostly did was audit: about one finding in ten falls inside the change that armed it.
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
kept, and the Analytics property id. Every part reads it except Marks, which is
pure calculation, and Credentials, which is handed what it needs rather than
reading (`docs/design.md` rule 10). Settings itself reads nothing else: no
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
   untouchable list, Insights reads the Analytics id, and the Face reads where
   the credentials are kept and hands them to PRESS-0002 (`docs/design.md`
   rule 10). A key renamed later is a rename across six parts.
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
   no standard-library writer, so it would cost a third-party dependency this
   spec does not otherwise need.
2. **Settings is handed its folder; it never derives one.** The caller passes
   the directory. This keeps § The parts' *depends on nothing* true and keeps
   the AppImage location problem inside PRESS-0022.
3. **A key Settings does not recognise is preserved on save, at the top level.**
   A newer Pressless must be able to write a key an older one then saves over
   without losing it, so it puts that key at the top level — §4.4 rebuilds
   `credentials` from the dataclass.
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

**The file is UTF-8, read and written, whatever the machine's locale.** JSON
is UTF-8 by definition, and Python's default is the locale's — cp1252 on
Windows — so a `site_folder` or account name holding one accented character
would be written here and unreadable there. This is an on-disk shape the
writer's installation carries between versions and machines, so its BYTES are
part of the contract rather than an implementation detail: UTF-8, and `\n`
line endings on every system. Left to the platform, the same settings differ
by which machine last wrote them.

**`version` is the file's, not the dataclass's.** `save()` always writes
`version: 1`; `load()` requires it, accepts the JSON number `1` and nothing
else — not `true` and not `1.0`, each of which compares equal to `1` in
Python, so the check is on the type as well as the value — and raises
`SettingsError` naming the value for anything else — a file written by a later Pressless is not
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
| File present, not valid JSON or not decodable as UTF-8 | `SettingsError`, naming the file |
| Valid JSON, a required key missing or the wrong type | `SettingsError`, naming the key |
| Valid JSON, `version` absent or not `1` | `SettingsError`, naming the value |
| Valid JSON, a value whose *shape* is wrong — `repository` not `owner/name` with each half holding only letters, digits, `.`, `_` and `-` (the value reaches an API URL, where `?`, `#`, `%` and whitespace change what is asked for), `credentials.store` outside `"keyring"` and `"file"`, `site_folder` not absolute, an `untouchable` entry empty or naming a path inside a directory (a trailing `/` is permitted and names that same root entry, which the Publisher ignores when matching), `analytics_property_id` present and not the numeric id §4.2 fixes it as | `SettingsError`, naming the key |
| Valid | `Settings` |

**The shape row is why this is a list rather than four cases.** `repository`
`store` and `site_folder` are contracts other parts read, not free strings: a
`str` holding `"ownername"`, `"vault"` or `"site"` is present and correctly
typed, so without the row `load()` accepts it and the Publisher, PRESS-0002 or
the Builder meets it later, with less to say about it. A relative
`site_folder` is the costly one — the Builder would resolve it against
whatever directory the process happens to be in, which differs between the
Face's server and a command-line run, so the finished site lands in two
places.

**Nothing in the failing rows writes.** A file we could not read is a file
we do not overwrite: the writer's settings are recoverable by hand only as
long as they are still there.

### 4.4 Saving

`save()` writes to a temporary file in the same directory, flushes and fsyncs
it, then replaces the target with `os.replace`, which is atomic on both
systems. A crash mid-save leaves either the old file or the new one, never a
truncated one. **The sync is part of that mechanism rather than a refinement
of it:** `os.replace` orders the namespace and not the data, so without it a
power loss can commit the rename ahead of the blocks and leave an empty file
where this section promises the previous one.

Keys `load()` did not recognise are carried through unchanged, **at the top
level only**: `credentials` is rebuilt from the dataclass, so a stranger key
nested inside it is not preserved. A later Pressless adding a key puts it at
the top level. `save()` therefore reads the existing file before writing. A save over one it
cannot parse raises rather than discarding what it could not read — and so
does a save over one whose `version` is not this build's — **by §4.2's test,
not a looser one**, or a file `load()` refuses is the file `save()` accepts —
because carrying a
newer file's keys forward under this build's stamp relabels a file another
Pressless wrote, after which neither can read it.

**`save()` validates nothing it is HANDED.** Shape is `load()`'s (§4.3), so a
`Settings` built by hand with a relative `site_folder` or a malformed
`repository` is written as handed and refused on the next read. Measured, not
assumed. Putting the checks here too would give setup a failure §6 does not
carry. The file already on disk is the other question, and the paragraph above
settles it.

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
  temporary folders, one empty, one holding `settings.json` containing `{`,
  **plus an assertion that neither class is a subclass of the other**.
  *Breaks when:* an implementer catches both as "no usable settings" and
  sends the writer to setup, which then overwrites the file he could have
  fixed. **The two folders alone cannot catch that.** Make `NotSetUp` a
  subclass of `SettingsError` and both raises still pass, while a caller's
  `except SettingsError` swallows the absent case — the same confusion,
  arriving by inheritance. The subclass assertion is what closes that route.

- **INV-3** — An absent `untouchable` key is a `SettingsError`. An
  `untouchable` key present and empty loads.
  *Test:* `tests/test_settings.py::test_untouchable_absent_is_an_error` — two
  files differing only in whether the key is present.
  *Breaks when:* an implementer gives the field a default of `()`. Both
  fixtures are otherwise complete and valid, so no other rule rejects
  either one — the pair fails only if this rule is missing.

- **INV-4** — A top-level key `load()` does not recognise is present,
  unchanged, in the file after a `save()` of the loaded value. Nested keys are
  not covered — §4.4 rebuilds `credentials` from the dataclass.
  *Test:* `tests/test_settings.py::test_unknown_keys_survive_a_save`.
  *Breaks when:* `save()` is written from the dataclass alone rather than
  over the file's existing contents.

- **INV-5** — after a save interrupted before completion, the file on disk is
  the previous one.
  *Test:* `tests/test_settings.py::test_save_is_atomic` — patch `os.replace`
  itself to record its destination and then raise; assert the recorded
  destination is `path_for(folder)`, and that `load()` still returns the
  previous value. One patch carries both halves. Patching the write instead
  never reaches the replace, so the destination could not be asserted at all.
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

- **INV-7** — `load()` and `save()` open no path outside `folder`, and *add*
  nothing inside it but `path_for(folder)`. §4.4's temporary file is the one
  permitted extra path and is gone once `save()` returns. **An addition rule,
  never a cleanup rule:** other parts keep files in this same folder —
  Insights' cache (`docs/design.md` rule 8) and ADR-0003's fallback
  credentials file — and Settings removes nothing it did not write. The
  prescribed fixture runs in an empty folder, so it cannot tell the two
  readings apart.
  *Test:* `tests/test_settings.py::test_only_touches_its_own_file` — two
  phases. Patch the filesystem calls both functions make, require every path
  opened to sit under `folder`, then list the folder afterwards. Then hand
  `load()` an empty child folder whose parent does hold a settings file, and
  require `NotSetUp` with no path opened outside the child.
  *Breaks when:* a search for a settings file in a parent directory or the home
  directory is added, which is scope decision 2 undone. **The first phase
  cannot catch that**: a parent search only runs when the handed folder holds
  no file, so every assertion in it stays green. The second phase is the one
  that fails, which is why both are prescribed.

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
- **The existing file was written by another Pressless.** `save()` raises
  `SettingsError` naming the version it found, rather than carrying that
  file's keys forward under this build's stamp. The writer's settings stay
  where he can repair them.
- **`repository` names a repository that is not there.** §4.3 rejects the
  wrong *shape*; existence is not checked at all, because checking it needs
  the network. The Publisher is where a well-formed name with nothing behind
  it surfaces.
- **The file or its folder cannot be written.** `save()` reports whatever the
  write raises, as a `SettingsError` naming the path, and does not probe
  permissions first. **A read-only settings *file* is not that state on
  Linux.** Measured: `os.replace` onto a mode-444 target in a writable
  directory succeeds and replaces it, where a direct `open('w')` on the same
  file raises `PermissionError`. That measurement is Linux's; Windows is
  expected to refuse the replace on a read-only target and is observed
  nowhere, which §10's last row already records. So
  §4.4's mechanism decides this, the folder's permissions are what bite on
  Linux, and a settings file copied read-only from another machine is replaced
  rather than refused.
- **Two Pressless windows save at once.** The last write wins, whole.
  §4.4's replace is what makes "whole" true; nothing here makes it "both".

## 7. Tests

`tests/test_settings.py`, unlabelled — it needs no fixture beyond a
temporary directory and must run everywhere, unlike the archive test
PRESS-0004 carries.

One test per invariant in §5, plus the extra rows §10 names. **The red run is made against a stub
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
  TOML writer, so saving would need a third-party dependency this spec does
  not otherwise need. Its one advantage is
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
| §4.3's `site_folder` shape row | `tests/test_settings.py::test_relative_site_folder_is_rejected` |
| §4.3's `untouchable` entry shape | `tests/test_settings.py::test_a_nested_untouchable_entry_is_rejected` |
| §4.3's `version` row | `tests/test_settings.py::test_a_version_that_is_not_the_number_one_is_refused`. Added after both slipped: comparing with `!=` alone accepted `true` and `1.0`, because a bool is an int in Python and a float compares equal (PRESS-0066) |
| §4.3's `repository` shape | `tests/test_settings.py::test_a_repository_carrying_url_punctuation_is_refused` and `::test_a_repository_with_the_punctuation_github_allows_still_loads`. The second is the half that matters: the value reaches an API URL, so the rule has to reject punctuation without rejecting the writer's own site |
| §4.3's `store` shape | **nothing** — no invariant locks it, so an implementer could drop the row and this suite stays green. Its absence is silent: a malformed `store` reaches PRESS-0002 as a value it did not expect. Worth an invariant if it is ever seen to slip |
| §4.3's not-decodable-as-UTF-8 row | `tests/test_settings.py::test_an_undecodable_settings_file_is_a_typed_failure` and `::test_saving_over_an_undecodable_file_is_a_typed_failure` |
| §4.2's `\n` line endings | `tests/test_settings.py::test_save_names_the_line_endings` |
| §4.4's sync before the replace | `tests/test_settings.py::test_save_reaches_the_disk_before_the_rename` |
| §4.4's refusal to save over another build's file | `tests/test_settings.py::test_saving_over_a_newer_settings_file_is_refused` and `::test_a_save_over_a_version_that_is_not_the_number_one_is_refused`, with `::test_the_first_save_still_works_with_no_file_to_carry` holding the no-file case it must not catch. The second is the one that pairs the gate with `load()`'s: without it the two ends can disagree and the suite stays green |
| §4.3's `analytics_property_id` shape | `tests/test_settings.py::test_a_property_id_that_is_not_numeric_is_refused` and `::test_a_declined_dashboard_still_loads`. The second is the half that matters: ADR-0005 makes the Google step declinable, so the rule has to reject a pasted tag without rejecting a writer who declined |
| §4.3's not-valid-JSON row, on input that exhausts the parser | `tests/test_settings.py::test_deeply_nested_json_is_a_typed_failure` |
| `save()` leaving no descriptor behind when it cannot open its temporary file | `tests/test_settings.py::test_a_save_whose_temporary_file_cannot_be_opened_leaks_no_descriptor` |
| §4.4's atomic replace on Windows | **nothing** — `os.replace` is documented atomic on both, and this suite runs on Linux. PRESS-0022 stages the built executable to a Windows box and runs it there before release, which is the only place this would be observed; it schedules no check of its own |

## 11. Cross-doc impact

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
| 3 | 2026-08-26 | 3, cold — genre pinned `spec`, packet rebuilt from disk with `settings.py` and `tests/test_settings.py` whole, the design rules, ADR-0003 and ADR-0005; Google, GitHub, Windows and PyInstaller declared an unrunnable region | 2 | 1 | 2 | 2 | **Seven verified, seven fixed, none dismissed. First loop of a new run**, triggered by renaming the Analytics field to `analytics_property_id`. **All three lanes independently found the same three.** The worst: §1 said every part but Marks reads Settings and §2 said PRESS-0002 reads where the credentials are kept, against `docs/design.md`'s Credentials row (*"Deliberately knows nothing about: Settings…"*) and rule 10 — and against the shipped `credentials.py`, which imports no settings at all. An implementer of PRESS-0002 would have given it the dependency its design row forbids, and lost the testability-without-a-keyring that rule 10 exists to protect. The other two were §11 listing two cross-document changes **both documents already carry**: the design gate made them on 2026-08-25 and §11 was never updated, so §11 read as a task list telling an implementer to add the Analytics identifier to a Settings row that names it and a Google paragraph to an ADR that has one — editing two accepted documents to duplicate facts that can then drift. Both bullets deleted rather than reworded. **Two Q4s were fixtures that could not catch the breach they named**, the same class the previous run's loop 1 found three of. INV-7's recipe was a single phase against a populated folder, and a parent search only runs when the handed folder is empty — the shipped test's own mutation note records that adding the fallback leaves every assertion green; the second phase is now prescribed. INV-5's two halves could not both run: patching the write to raise *before* `os.replace` never reaches the replace whose destination the same sentence asks you to assert. **The Q3 with teeth cost a code change.** Nothing rejected a relative `site_folder`, which is present and correctly typed, so the Builder would have resolved it against whatever directory the process happened to be in — different for the Face's server and a command-line run, landing the finished site in two places. Adding the §4.3 row made this document claim behaviour the code did not have, so the check and `test_relative_site_folder_is_rejected` landed in the same loop; proven red with the check removed, green with it. §10's row for the shape rejections was split to match. **The second Q3:** unknown-key carry-through never pinned its depth while `save()` rebuilds `credentials` from the dataclass, so a stranger key nested there is silently dropped — top-level-only is now stated, with the instruction that a later Pressless puts a new key at the top level. **One open question, raised by all three lanes, resolved clean and is not counted:** none could find the untouchable derivation rule in `docs/design.md` § What may depend on what. It is there; my packet window truncated that section. A packet defect, not a document one. |
| 4 | 2026-08-26 | 3, cold — identical brief, packet rebuilt whole from disk and given § What may depend on what COMPLETE, which loop 3's packet had truncated | 1 | 4 | 1 | 0 | **Six verified, six fixed, none dismissed. Cap reached (2 for a spec); the tail is empty and the run ships.** **A CALM cap: two of the six landed on text this run wrote**, each anchor checked against loop 3's ledger rather than recall — the document held more defects than the cap held loops, and at its present size the split signal does not fire. **The most dangerous finding came from one lane and concerns the publishing key.** INV-7 said `load()` and `save()` *"leave nothing inside it but `path_for(folder)`"*, while §4.1 defines that folder as Pressless's own — the folder `docs/design.md` rule 8 gives Insights' cache and ADR-0003 gives the fallback credentials file. A builder taking the invariant literally writes a `save()` that clears strays and deletes the file holding the key, and the prescribed fixture runs in an empty folder so it cannot tell the two readings apart. It is now an addition rule that removes nothing it did not write. **All three lanes found INV-5**, which claimed `save()` never leaves a file `load()` rejects; run rather than reasoned, `save()` accepts a `Settings` holding `repository="ownername"`, writes it, and the next `load()` refuses it — so setup could report success over a file the app cannot open. The invariant is narrowed to the interruption claim it tests, and §4.4 now states outright that `save()` validates nothing. **Two lanes found the on-disk encoding was never pinned** though the document calls the format a shape the installation carries between machines: the module already names UTF-8 everywhere and explains why, and the contract did not. **One lane found a misquote with a real consequence:** two passages blamed `docs/design.md` § The stack for ruling out a bundled dependency, and that section rules out no such thing — its own Chosen line takes `Pillow` and the keyring, and ADR-0003 mandates the latter, so a builder of PRESS-0002 could have rejected the library the code already imports. **Two findings were this run's own collateral, both from loop 3's additions and both found by the same lane:** the `at the top level only` qualifier added to §4.4 never reached INV-4 or scope decision 3, leaving an implementer free to deep-merge; and the eighth test added in loop 3 left §7 still saying one test per invariant against §5's seven, so a test file built from §7 would leave §4.3's costliest row unchecked while §10 claimed it covered. **Open questions resolved clean and not counted:** the PRESS-0022 attribution is one item (a lane checked the roadmap), and §2's claim about every dependency rule granting Settings is the same true-but-inert item the previous run dismissed, correctly filed as a question rather than a finding. |
| 4 | 2026-09-04 | 3, cold — genre pinned `spec`, packet carried `settings.py` and `tests/test_settings.py` whole, the design rules and both cited ADRs; no unrunnable region | 2 | 1 | 2 | 0 | **Five verified, five fixed; one dismissed. First loop of a new run**, armed by the `analytics_property_id` shape row. **All three lanes found the same two, and both are the spec trailing shipped code.** §4.4 promised a crash leaves the old file or the new one while naming only `os.replace`, which orders the namespace and not the data — so an implementer omits the fsync and ships PRESS-0039's defect a second time. And §4.4 said `save()` validates nothing, while the code refuses to save over a file another build stamped; following the spec restores PRESS-0053. Both are now stated, with a §6 row. **Two lanes: the untouchable trailing slash is settled nowhere** — the code accepts `CNAME/` and a shipped test requires it to load, while §4.3 as written sends a builder to reject any entry carrying a slash. **One lane: §7 promises a test per invariant plus the extra rows §10 names, and §10 named none** for the UTF-8 row or the save-side tests; since it marks unchecked rules explicitly, the gap read as covered rather than unwritten. **Dismissed, and it was my packet's defect rather than the document's:** two lanes read §4.2's `design.md` citation as naming a rule that section does not carry. It carries it, below where my window stopped, and both lanes raised it as an open question as well. Packet widened for loop 2. |
| 5 | 2026-09-04 | 3, cold — identical brief, packet rebuilt whole from disk with `docs/design.md` § What may depend on what given COMPLETE, which loop 4's packet truncated | 1 | 2 | 1 | 1 | **Five verified, five fixed; one filed against a neighbour. Cap reached (2 for a spec); the tail is empty and the run ships. A VIOLENT cap — three of the five landed on text this run wrote**, each anchor checked against loop 4's ledger. **Two lanes found the sharpest, and it is loop 4's own fix:** loop 4 added `save()`'s version refusal without pinning WHICH test, and the code had settled the two ends differently — `load()` checks type and value, `save()` value alone. Executed rather than reasoned: a file saying `"version": true` is accepted by `save()`, relabelled `1`, and its stranger keys carried — PRESS-0053's harm arriving by the one route PRESS-0066 left open when it closed the read side. §4.2 now pins the test and §4.4 defers to it; **the code half is surfaced rather than applied, because a docs gate may not edit code.** **Two lanes found INV-2's own fixture cannot falsify it:** make `NotSetUp` a subclass of `SettingsError` and both raises still pass while `except SettingsError` swallows the absent case, and the shipped test already carries the inheritance assertion the spec never prescribed. **One lane found §4.3 pins no character set for `repository`** while §10's row — written this run — requires rejecting punctuation, so a builder of §4.3 as written admits `owner/name?x=y` into an API URL. **One lane's open question was loop 4's own imprecision:** the code strips every trailing slash where loop 4 wrote "a single trailing `/`". **And §6 carried a Windows claim under a `Measured:` lead** while §10 records Windows as observed nowhere; the lead is now scoped to the Linux half. **Filed against `docs/design.md`, which has its own gate:** its untouchable rule has the Publisher match "unless its first segment is on the list", which a stored `CNAME/` does not satisfy — `_is_protected` strips the slash and the design rule never says so. **This run was mostly an audit rather than a gate: about one of its ten verified findings falls inside the span that armed it.** Route from here: implementation, not a third loop. |
