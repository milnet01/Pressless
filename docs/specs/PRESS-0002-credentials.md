# PRESS-0002 — Credentials: where the two secrets are kept, and how they are reached

**Status:** draft (2026-08-25) — not yet gated.
**Kind:** security.
**Source:** ROADMAP PRESS-0002 (`docs/design.md` § Where everything sits on disk; ADR-0003, ADR-0005).

**Blocked by:** PRESS-0001, which is shipped.
**Blocker for:** PRESS-0009, PRESS-0019, PRESS-0021.

*Layman:* the part that hands the publishing key to whatever needs it, keeps
it where the operating system keeps other passwords, and refuses to keep it
anywhere a stranger on the same computer could read.

## 1. Goal

After this ships, one small module answers two questions and nothing else:
*where can a secret be kept on this machine*, and *what is the secret filed
under this account*. Setup uses it to decide and record; the Publisher and
Insights use it to read. It owns ADR-0003's two paths — the operating
system's own store, and the fallback file — and it is the only code that
touches either.

It writes no prose, keeps no state between calls, and reads no other part of
Pressless.

## 2. Problem

PRESS-0001 records *where* the secrets are kept and refuses to hold the
secrets themselves. Its §4.5 says so and names this item as the owner of both
stores. So the fields exist, three parts bind to them, and nothing reaches
them.

Four things make this a contract rather than a helper.

1. **Three parts bind to the surface.** Setup writes both secrets, the
   Publisher reads the GitHub key, Insights reads the Google authorisation.
   `docs/design.md` § What may depend on what gives rules 5 and 8 their
   *"and nothing else"*, so this module is inside the Settings lane and is
   reached the same way from both.
2. **It is a security boundary.** The GitHub key can rewrite the live site.
   The rules below are what stop it reaching a file anyone else can open, and
   there is no observable difference between a key kept safely and a key kept
   badly until someone else has it.
3. **The library's answer cannot be trusted at face value.** Measured on the
   development machine (§4.6): the store the library nominates is a chain, one
   of whose members keeps secrets in plain text, and a read for a secret that
   does not exist came back as a truthy object rather than `None`. Both would
   pass an implementation written from the library's documented types.
4. **It is an on-disk shape an installation carries forward.** The fallback
   file survives upgrades on a machine we do not have.

## 3. Scope decisions (agreed with the user)

Five choices below were preference rather than deduction. **The first two were
put to the user on 2026-08-25 and answered; the other three were made by this
session.** §8 carries what each beat.

1. **Windows never falls back to a file.** Where no operating-system store can
   be used, Windows setup stops and says so. `os.chmod` on Windows sets only
   the read-only flag and cannot make a file private to one user (§4.6), so a
   fallback there is a readable key rather than a protected one — and the
   writer chooses where Pressless sits, which may be a shared or removable
   drive.
2. **The store that answered is named, every time.** `choose()` reports which
   store served the round-trip, so a plaintext store cannot pass for a
   protected one. The module reports the store's identity; wording it is the
   Face's, per `docs/design.md` § Errors.
3. **The fallback file lives in Pressless's own folder.** ADR-0003 says the
   writer's profile directory; `docs/design.md` § Where everything sits on
   disk and PRESS-0001 §4.5 both put it beside the settings file, and both are
   later. §11 records the correction the ADR needs.
4. **One fallback file holds both secrets.** Two files would mean two atomic
   writes and the same permission question asked twice.
5. **A store's answer is a `str` or it is an error.** The measured non-string
   answer in §4.6 is not a value this module may hand to the Publisher.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/credentials.py

SERVICE = "Pressless"            # what both secrets are filed under in the store
PROBE = "pressless-store-probe"  # the account choose() round-trips; never a secret
FILE_NAME = "credentials.json"   # the fallback file, in Pressless's own folder
FILE_VERSION = 1

@dataclass(frozen=True)
class Choice:
    store: str      # "keyring" or "file" -- goes straight into Settings.credentials.store
    name: str       # the store that answered, as the library identifies it

def choose(folder: Path) -> Choice: ...
def read(store: str, folder: Path, account: str) -> str: ...
def write(store: str, folder: Path, account: str, secret: str) -> None: ...

class NoStore(Exception): ...           # nowhere safe to keep it -- setup stops
class NotStored(Exception): ...         # the store works and holds nothing here
class CredentialError(Exception): ...   # a store we will not act on
```

`folder` is Pressless's own folder, supplied by the caller, exactly as
PRESS-0001 §4.1 takes it. This module does not create it, search for it, or
fall back to another one.

`store` is the string PRESS-0001 already validates against `"keyring"` and
`"file"`, passed in rather than re-read, so nothing here imports Settings.

`account` is `Settings.credentials.github_account` or `.google_account`. The
Google one is `None` where the dashboard was declined (ADR-0005), and a caller
checks that before calling — `read()` is not given `None`.

### 4.2 Choosing a store

`choose()` is setup's question and is asked once. It does a round-trip against
the operating system's store: write `PROBE`, read it back, delete it.

- The round-trip succeeds → `Choice("keyring", <the member that answered>)`.
- It raises, or returns something other than what was written → the store
  exists and cannot be relied on. That is a `CredentialError`, not a reason to
  fall back: a locked keyring is not an absent one, and writing the key to a
  file while a working store sits locked is the wrong repair.
- No store at all, on Windows → `NoStore`.
- No store at all, elsewhere → `Choice("file", "file")`.

**The name comes from the member that answered, not from the library's
nomination.** The library may nominate a chain; the chain is not a store and
hides which of its members served the read. So after a successful probe the
members are asked in order and the first returning the probe value is the
name. Where the nominated store is not a chain it is its own single member.

### 4.3 Reading and writing

`read(store, folder, account)` returns the secret as a `str`.

| What it meets | What it raises |
|---|---|
| The store holds nothing for `account` | `NotStored` |
| The store cannot be used at all | `CredentialError` |
| The store answers with something that is not a `str` | `CredentialError` |
| The fallback file is absent, unreadable, or not valid JSON | `NotStored` for absent, `CredentialError` for the rest |

`write(store, folder, account, secret)` files it. On Windows with
`store == "file"` it raises `NoStore` rather than writing — §3 decision 1
applies wherever the file store is reached, not only where it is chosen, so a
settings file carried from another machine cannot open the hole the decision
closes. `read()` carries no such refusal: reading one back is how such a
machine is recovered.

**Absent and broken are different on purpose**, for PRESS-0001 §5 INV-2's
reason: sending the writer to re-enter a key he still has is how the one he
has gets overwritten.

### 4.4 The fallback file

```json
{ "version": 1, "secrets": { "<account>": "<secret>" } }
```

In `folder`, named `FILE_NAME`, UTF-8, one file for both secrets.

Written the way PRESS-0001 §4.4 writes settings — a temporary file made by
`tempfile.mkstemp` beside the target, then `os.replace`. That mechanism is
chosen twice over here: it is atomic, and `mkstemp` creates its file
owner-only, a mode `os.replace` carries onto the target (§4.6). So the file is
private from the instant it exists and no `chmod` follows a write that has
already left a readable file behind.

A write reads the existing file first and replaces one entry, so the other
secret survives.

### 4.5 What this module never does

- **Never writes a secret anywhere but the chosen store.** Not to the log, not
  to the settings file, not to an exception message, not to the screen —
  `docs/design.md` § Logging and ADR-0003.
- **Never words anything for the writer.** It raises typed failures; the Face
  turns them into sentences (`docs/design.md` § Errors).
- **Never decides whether a store is good enough.** It reports which one
  answered. Judging that is the writer's, once he is told.

### 4.6 What was measured, and where

These three decided the design above and none of them follows from the
library's documented types. Each was run on the development machine on
2026-08-25; the commands are in the run, and INV-3, INV-5 and INV-7 are what
hold them once the code exists.

- **A read for a secret that is not there came back truthy and not a string.**
  The nominated store is a chain whose members include a kernel-keyring
  backend that answers with an object. An implementation testing the result
  for truth would report a key that does not exist.
- **The chain includes a plaintext file backend.** So "the operating system's
  store" can be a plain file, which is what ADR-0003 exists to avoid, and
  nothing distinguishes the two without naming the member that answered.
- **`mkstemp` creates its file owner-only and `os.replace` preserves that
  mode.** Verified by writing one, replacing a world-readable target, and
  reading the mode back.
- **`os.chmod` on Windows sets only the read-only flag.** All other bits are
  ignored, so no `chmod` can make a file private to one user there.
  Source: https://docs.python.org/3/library/os.html#os.chmod

## 5. Invariants

- **INV-1** — `src/pressless/credentials.py` imports no other `pressless`
  module.
  *Test:* `tests/test_credentials.py::test_credentials_imports_no_sibling`,
  walking the module's imports as
  `tests/test_settings.py::test_settings_imports_nothing_forbidden` does.
  *Breaks when:* an implementer imports `pressless.settings` to fetch the
  account names itself, which makes the Publisher's one documented way in
  two.
  **It is a weak test and weak in a way this project has already met**: an
  import walk passes against a module that does nothing. It is evidence about
  imports and never about reaching a store.

- **INV-2** — On Windows no code path writes a secret to a file. `choose()`
  raises `NoStore` where no operating-system store can be used, and
  `write(store="file", ...)` raises `NoStore` however it was reached.
  *Test:* `tests/test_credentials.py::test_windows_never_writes_a_file` —
  patch the platform to Windows, make the store unavailable, and assert both
  calls raise and that `folder` is empty afterwards.
  *Breaks when:* the fallback is written once and applied on both systems,
  which §4.6's `chmod` measurement makes unsafe.
  Only this rule can reject the fixture: on any other platform the same
  arguments select and write the file store.

- **INV-3** — `read()` returns a `str` or raises. A store answering with
  anything else is a `CredentialError`.
  *Test:* `tests/test_credentials.py::test_non_string_answer_is_an_error` — a
  patched store returning a truthy object, as the development machine's does.
  *Breaks when:* an implementer returns the store's answer unexamined, and an
  object reaches the Publisher as an authorisation header.
  The fixture is isolated: a store returning `None` is INV-4's, and no other
  rule here inspects the answer's type.

- **INV-4** — A store holding nothing for an account raises `NotStored`; a
  store that cannot be used raises `CredentialError`. Neither is the other.
  *Test:* `tests/test_credentials.py::test_absent_and_broken_differ` — two
  patched stores, one returning `None`, one raising.
  *Breaks when:* both are caught as "no key" and setup overwrites the key the
  writer still had.
  Both fixtures are otherwise valid, so only the requirement that the two
  outcomes *differ* can fail the pair.

- **INV-5** — The fallback file is owner-only from the instant it exists.
  *Test:* `tests/test_credentials.py::test_fallback_file_is_owner_only` —
  assert `write()` reaches `os.replace` with `folder / FILE_NAME` as its
  destination, then write one and read the mode back.
  *Breaks when:* an implementer opens the target directly and chmods
  afterwards, leaving a window in which the key is readable.
  **Asserting the mechanism is what makes it bite:** a direct write followed
  by a `chmod` ends at the same mode, so the mode check alone would pass
  against the implementation this rule exists to reject.

- **INV-6** — No exception this module raises contains a secret value.
  *Test:* `tests/test_credentials.py::test_no_failure_names_the_secret` —
  write a sentinel through the file store, force each failure in §4.3's
  table, and assert the sentinel appears in no message.
  *Breaks when:* an implementer puts the value in a message to make a failure
  easier to diagnose, and the log or a screenshot then carries the key.

- **INV-7** — `choose()` names the store that answered the round-trip, not the
  one the library nominates.
  *Test:* `tests/test_credentials.py::test_choice_names_the_answering_store` —
  a patched chain whose first member holds nothing and whose second holds the
  probe; assert the name is the second member's.
  *Breaks when:* the name is taken from the nominated store, which on the
  development machine is a chain — not a store, and one hiding a plaintext
  member.
  Only this rule can reject the fixture: the probe succeeds either way, so
  every other rule here passes against a chain that names itself.

- **INV-8** — Writing one account's secret leaves the other's unchanged.
  *Test:* `tests/test_credentials.py::test_second_write_keeps_the_first` —
  write two accounts through the file store, then read the first back.
  *Breaks when:* the file is rebuilt from the one secret in hand, so setting
  up the dashboard discards the publishing key.

## 6. Failure modes

- **No store, on Windows.** `choose()` raises `NoStore` and setup stops.
  There is no route that finishes setup with the key in a file there.
- **No store, elsewhere.** The file store is chosen and named. ADR-0003
  requires the writer be told, and §4.2 gives the Face the fact to tell him
  with.
- **A store that is present but locked.** The probe fails, so `CredentialError`
  rather than a fallback. The remedy is unlocking it, and a fallback would
  leave the key in a file while a working store sits beside it.
- **The store holds nothing on a new machine.** `NotStored`. ADR-0003 records
  that moving machines means entering the key again, and that the writer is
  told rather than left guessing.
- **The dashboard was declined.** `Settings.credentials.google_account` is
  `None` and nothing calls `read()` for it. ADR-0005 requires that this costs
  the dashboard and nothing else.
- **A keyring prompt appears at an odd moment.** The operating system is
  asking, not Pressless, and the wording is not ours. ADR-0003 already puts
  the warning in the setup instructions.
- **Two Pressless windows write at once.** The last write wins, whole. §4.4's
  replace is what makes *whole* true; nothing here makes it *both*.

## 7. Tests

`tests/test_credentials.py`, unlabelled — it needs no fixture beyond a
temporary directory and must run everywhere, unlike the archive test
PRESS-0004 carries. One test per invariant, named in §5 and tabulated in
§10.

**No test touches the real store.** Every test that names the operating
system's store patches it. A test that called the library for real would write
into the machine's own keyring, which is somebody's login keyring on the one
machine that runs this suite.

**The red run is made against a stub `credentials.py`, never against an absent
one.** With the module absent the suite errors at collection and no assertion
runs — this project's `CLAUDE.md` records that trap. The stub declares every
name in §4.1 and raises `NotImplementedError` from each function.

**Not every test then fails, and that is by design.** A stub importing no
sibling already satisfies INV-1, whose test reads the module's imports rather
than its behaviour. The red run is every test collected with the behavioural
ones failing on assertions; INV-1's going red against the stub means the stub
is wrong, not the test. Read the collected count, not the exit code.

## 8. Alternatives considered (and rejected)

- **Talk to each operating system's store directly, with no dependency.**
  `ctypes` to Windows Credential Manager, D-Bus to Secret Service. It keeps
  the project dependency-free, which `CLAUDE.md` § Build and test currently
  claims. Rejected because ADR-0003 chose one library covering both, and
  because it means two hand-written backends of which only one can ever be
  exercised on the machine that develops it.
- **Let the fallback fire on Windows with a warning.** Rejected by the user
  2026-08-25 (§3 decision 1): a key that can rewrite the live site, readable
  by anyone using that computer, is not repaired by a sentence.
- **Encrypt the fallback file.** Rejected: the key that decrypts it would have
  to sit beside it, so it protects against nothing the file mode does not.
- **Decide the store by inspecting what the library nominates.** Cheaper than
  a round-trip. Rejected on measurement (§4.6): the nomination is a chain, it
  is not the library's own failure backend, and it can answer from a plaintext
  member — so inspection reports a protected store where there is none.
- **One fallback file per secret.** Rejected: two atomic writes and the same
  permission question twice, for no gain.
- **Record the fallback file's path in Settings.** Rejected: PRESS-0001 §4.5
  owns this and refuses it — the path follows the program file, so a recorded
  one is invalidated by the move Settings must survive.
- **A `forget()` for removing a secret.** Rejected as unneeded now. Declining
  the dashboard after granting it is PRESS-0021's, and `write()` already
  replaces.

## 9. Out of scope

- Asking the writer for either secret, and the two-step setup ADR-0005
  requires — PRESS-0021.
- Finding Pressless's own folder from the running program — PRESS-0022.
- Carrying the store's backends into the packaged executable, which needs
  their entry-point metadata — PRESS-0022.
- What the writer is shown when any of this fails — PRESS-0011.
- Whether the store that answered is good enough. This module names it; the
  writer decides.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_credentials.py::test_credentials_imports_no_sibling` |
| INV-2 | `tests/test_credentials.py::test_windows_never_writes_a_file` |
| INV-3 | `tests/test_credentials.py::test_non_string_answer_is_an_error` |
| INV-4 | `tests/test_credentials.py::test_absent_and_broken_differ` |
| INV-5 | `tests/test_credentials.py::test_fallback_file_is_owner_only` |
| INV-6 | `tests/test_credentials.py::test_no_failure_names_the_secret` |
| INV-7 | `tests/test_credentials.py::test_choice_names_the_answering_store` |
| INV-8 | `tests/test_credentials.py::test_second_write_keeps_the_first` |
| ADR-0003's promise that the store protects the secret as well as the writer's other passwords | **nothing** — INV-7 makes the store *nameable*, which is all this module can do. Whether a named store is good enough is not decidable here, and §3 decision 2 is the reason the question reaches the writer at all |
| INV-2's rule on the machine it protects | **half** — the test patches the platform, and no Windows runs this suite. PRESS-0022 stages the built executable to a Windows box before release, which is the only place the real behaviour is observed; it schedules no check of its own |
| INV-5's file mode on Windows | **nothing, and nothing can** — §4.6's measurement is that the mode is unenforceable there. INV-2 removes the case rather than checking it |
| No secret reaching the rolling log | **nothing here** — INV-6 covers this module's own messages. The log is the Face's and `docs/design.md` § Logging is the rule; PRESS-0011 owns the surface |
| The Publisher and Insights actually calling this rather than reaching a store themselves | **nothing here** — INV-1 stops this module reaching them, not them reaching past it. PRESS-0009 and PRESS-0019 are where that would show |

## 11. Cross-doc impact

- `docs/decisions/ADR-0003` — three corrections. It puts the fallback file in
  the writer's profile directory, where `docs/design.md` § Where everything
  sits on disk and PRESS-0001 §4.5 both put it beside the settings file. It
  does not contemplate a platform on which the fallback is refused at all.
  And in `docs/decisions/ADR-0003-where-the-key-lives.md`,
  *"Pressless says plainly that it fell back"* gains *and names the store
  that answered*.
- `pyproject.toml` — gains the keyring library, the project's first runtime
  dependency.
- `CLAUDE.md` § Build and test — *"no dependencies beyond the standard library
  and `pytest`"* stops being true when that lands.
- `docs/design.md` § The stack already names the operating system's keyring,
  and § Where everything sits on disk already places the fallback file. Both
  are unchanged.
- `CHANGELOG.md` — an entry when it ships.
- PRESS-0001 is unchanged. This fills the hole its §4.5 names rather than
  moving anything it holds.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
