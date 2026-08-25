# PRESS-0001 — Settings: what is true of this machine, and nothing else

**Status:** spec draft (2026-08-25).
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
kept, and the Analytics property id. Every other part reads it. It reads
nothing else: no Store, no network, no other part of Pressless.

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
    daily_prompt_filter: str     # the tag pattern the Builder excludes
    untouchable: tuple[str, ...] # repository-root entries the Publisher leaves alone
    credentials: Credentials     # where the two secrets are kept -- never the secrets
    analytics_measurement_id: str | None

@dataclass(frozen=True)
class Credentials:
    store: str                   # "keyring" or "file" -- ADR-0003's two paths
    github_account: str          # the keyring account name, or the file's key name
    google_account: str

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
  "analytics_measurement_id": "G-XXXXXXXXXX"
}
```

`version` exists so a later shape change has something to branch on. Every
other key is required except `analytics_measurement_id`, which is `null`
where the writer declined the dashboard — ADR-0005 makes that step
declinable, so its absence is a normal state rather than a broken one.

The `untouchable` values above are illustrative. The real ones are the
output of § What may depend on what's rule, derived at setup against the
live repository root.

### 4.3 Loading

`load()` has four outcomes and they are distinguishable:

| State | Result |
|---|---|
| No file at `path_for(folder)` | `NotSetUp` |
| File present, not valid JSON | `SettingsError`, naming the file |
| Valid JSON, a required key missing or the wrong type | `SettingsError`, naming the key |
| Valid | `Settings` |

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

### 4.5 What Settings never holds

No secret value, ever — only the store name and the two account names under
which ADR-0003's keyring or fallback file holds them. Settings is written to
disk in plain text beside the program; a key in it would sit outside the
protection ADR-0003 exists to provide.

## 5. Invariants

- **INV-1** — Settings imports nothing that reaches a disk beyond its own
  file, a network, or another Pressless part.
  *Test:* `tests/test_settings.py::test_settings_imports_nothing_forbidden`,
  reading `src/pressless/settings.py`'s import list.
  *Breaks when:* an implementer imports `publisher` to validate the
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
  *Test:* `tests/test_settings.py::test_save_is_atomic` — patch the writer
  to raise after the temporary file is written and before the replace, then
  load.
  *Breaks when:* an implementer opens the target file directly and writes
  into it. The fixture isolates the replace step: the settings value written
  is valid, so a rejection afterwards can only come from a partial write.

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

- **INV-7** — `load()` and `save()` act on `path_for(folder)` and on no
  other path.
  *Test:* `tests/test_settings.py::test_only_touches_its_own_file` — run both
  against a temporary folder and list what the folder holds afterwards.
  *Breaks when:* a search for a settings file in a parent directory or the
  home directory is added, which is scope decision 2 undone.

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
- **`repository` is not `owner/name`.** Shape is checked; existence is not.
  Existence needs the network.
- **The file is read-only.** `save()` raises `SettingsError` naming the
  file. This is the state a settings file copied from another machine
  arrives in.
- **Two Pressless windows save at once.** The last write wins, whole.
  §4.4's replace is what makes "whole" true; nothing here makes it "both".

## 7. Tests

`tests/test_settings.py`, unlabelled — it needs no fixture beyond a
temporary directory and must run everywhere, unlike the archive test
PRESS-0004 carries.

One test per invariant, named in §5. Each is written and seen to fail
against the absent module before `settings.py` exists — and per this
project's own `CLAUDE.md`, a collection error is not a failing test: the
collected count is what says whether an assertion ran.

**INV-1's test is the weak one, and it is weak in a way this project has
already met.** Reading an import list proves what the module imports, not
that it works — the same shape as `test_marks_is_pure`, which `CLAUDE.md`
records as passing against an empty file. It is worth having because the
rule it locks is about imports, and it must not be read as evidence that
loading or saving does anything.

## 8. Alternatives considered (and rejected)

- **TOML.** Friendlier to hand-edit and comment. The standard library reads
  it and does not write it, so saving would need a dependency, against
  `docs/design.md` § The stack, and what it rules out. Its one advantage is
  comments the writer would read, and §3 decision 1 settled that he does not
  open the file. Revisit only if that changes.
- **An INI file.** No list type, so `untouchable` would become a delimited
  string and a path containing the delimiter would silently split.
- **A Python module as config.** Executable settings, and the file sits
  beside a program that publishes to the writer's live site.
- **Settings finds its own folder.** Breaks § The parts' *depends on
  nothing*, and duplicates the AppImage location problem PRESS-0022 owns.
- **Settings validates the paths and the repository it holds.** Every check
  worth having needs a disk or a network, both of which its row forbids;
  the parts that already have them are the ones that can report usefully.
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
| §4.4's atomic replace on Windows | **nothing** — `os.replace` is documented atomic on both, and this suite runs on Linux; the Windows box named in `CLAUDE.md` is where it would be observed, tracked by PRESS-0022 |

## 11. Cross-doc impact

- `CLAUDE.md` — the state block, and the § Build and test note about which
  tests need an environment variable, once this suite exists.
- `CHANGELOG.md` — an entry when it ships.
- No sibling spec changes. PRESS-0004 does not read Settings.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
