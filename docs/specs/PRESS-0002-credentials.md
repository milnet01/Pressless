# PRESS-0002 — Credentials: where the two secrets are kept, and how they are reached

**Status:** accepted (2026-09-02). Re-gated after §3 decision 6 added the fallback read's checks (PRESS-0085), which changed direction and re-armed `CLAUDE.md` rule 14. Two more cold loops, both folded in, nothing left unfixed — that run reached the spec cap of 2 as the 2026-08-25 run did. **A violent cap again:** four of the last loop's seven findings landed on text this run wrote, so a third cold read would mostly repair the second. Implementation is the better third reviewer and this document is routed there. **The gate earned its lanes rather than auditing:** most of both loops' findings fell inside the amended span, and the sharpest were the new invariant naming no exception type, its test being unable to fail, and the new rule being reachable by a door the test never checked.
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
under this account*. Setup uses it to decide and record; the Face reads a
secret and hands it to the Publisher or Insights as an argument
(`docs/design.md` rule 10). It owns ADR-0003's two paths — the operating
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

1. **Three parts bind to the surface, and one of them reaches it.** Setup
   writes both secrets. The Publisher and Insights need one each, and
   `docs/design.md` rule 10 has the Face fetch it and hand it over as an
   argument — so rules 5 and 8 stay literally true and both parts stay
   testable without a real keyring. §11 records how that was settled.
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

The choices below were preference rather than deduction. **Decisions 1 and 2
were put to the user on 2026-08-25 and answered, and decision 6 on 2026-09-02;
the rest were made in session.** §8 carries what each beat.

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
3. **The fallback file lives in Pressless's own folder.** ADR-0003 said the
   writer's profile directory and was corrected on 2026-08-25; §11 records
   that. `docs/design.md` § Where everything sits on disk puts it beside the
   settings file, and PRESS-0001 §4.5 hands the question here rather than
   answering it.
4. **One fallback file holds both secrets.** Two files would mean two atomic
   writes and the same permission question asked twice.
5. **A store's answer is a `str` or it is an error.** The measured non-string
   answer in §4.6 is not a value this module may hand to the Publisher.
6. **A read of the fallback file checks that the file is ours, and does not
   check its mode.** Decision 1's reason applies to the read as much as to
   the write: the writer chooses where Pressless sits, and on a shared or
   removable drive another user can substitute the file, so `read()` would
   hand their secret to the Publisher. The read refuses a symlink, and
   refuses a file owned by somebody else. It does not refuse on the mode,
   because a file carried from another machine is what recovery reads and
   its mode did not survive the journey, while its ownership becomes the
   writer's on the copy that carried it.

   **What this reaches is the shared drive, not the removable one.** Media
   formatted without ownership — vfat, exFAT — report the mounting user as
   every file's owner, so the comparison cannot fire there and a substituted
   file passes it. The symlink refusal still holds. Stated because decision
   1 names both drives and this check answers one of them.

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

def choose() -> Choice: ...
def read(store: str, folder: Path, account: str) -> str: ...
def write(store: str, folder: Path, account: str, secret: str) -> None: ...

class NoStore(Exception): ...           # nowhere safe to keep it -- setup stops
class NotStored(Exception): ...         # the store works and holds nothing here
class CredentialError(Exception): ...   # a store we will not act on
```

`folder` is Pressless's own folder, supplied by the caller, exactly as
PRESS-0001 §4.1 takes it. This module does not create it, search for it, or
fall back to another one. `choose()` takes none: it asks the operating
system's store a question about the machine. It does not check the folder
first: in `docs/specs/PRESS-0001-settings.md` §6, `save()` makes the same
judgement — it "does not probe permissions first" and reports whatever the
write raises.

`store` is the string PRESS-0001 already validates against `"keyring"` and
`"file"`, passed in rather than re-read, so nothing here imports Settings.

`account` is `Settings.credentials.github_account` or `.google_account`. The
Google one is `None` where the dashboard was declined (ADR-0005), and a caller
checks that before calling — `read()` is not given `None`.

### 4.2 Choosing a store

`choose()` is setup's question and is asked once. It writes `PROBE` under
`SERVICE`, then asks the store's members in order which of them returns that
value, and **only then deletes it**. The delete is last because the walk needs
the value still to be there.

| What the write and the walk do | What `choose()` returns |
|---|---|
| A member returns the probe value | `Choice("keyring", <that member>)` |
| The write raises `keyring.errors.NoKeyringError` | there is no store: `NoStore` on Windows, `Choice("file", "file")` elsewhere |
| The write raises anything else, or no member returns the value | `CredentialError` |

**`NoKeyringError` is the discriminator, and it is the only one.** Absence and
malfunction both reach `choose()` as a raised exception, so without naming the
type the last two rows fire on the same observation — and either the fallback
never runs or it runs while a working store sits locked. §4.6 records that the
library's own failure backend raises exactly this from all three operations. A
locked keyring is not an absent one, and writing the key to a file while a
working store sits locked is the wrong repair.

**The verdict rests on the member walk, not on reading the value back through
the store.** The library may nominate a chain, and a chain answers with its
first member that answers at all — so a member that answers unconditionally
masks every member behind it, and a read through the chain can report failure
while a working member holds the value. §4.6 records a chain on which exactly
that happens. Asking the members directly is also the only way a plaintext
member could ever be *named*, which is what §3 decision 2 is for. Where the
nominated store is not a chain it is its own single member.

### 4.3 Reading and writing

`read(store, folder, account)` returns the secret as a `str`.

| What it meets | What it raises |
|---|---|
| The store answers with anything that is not a `str` — including nothing at all | `NotStored` |
| The store cannot be used at all | `CredentialError` |
| The fallback file is absent | `NotStored` |
| The fallback file is unreadable, is not valid JSON, or carries a `version` this build does not read | `CredentialError` |
| The fallback file is a symlink, or is owned by another user, where the platform offers those checks (§3 decision 6, §4.4) | `CredentialError` |

**Not-a-string means nothing is stored, and that is measured rather than
chosen.** §4.6 records that on the development machine an absent secret comes
back as a truthy object and never as `None`, so *absent* and *not a `str`* are
one observation rather than two. Reserving `CredentialError` for it would send
a writer who has no key yet down the broken-store path instead of asking him
for one. The version row follows PRESS-0001 §4.3, which refuses a file written
by a later Pressless rather than guessing at it.

`write(store, folder, account, secret)` files it.

| What it meets | What it raises |
|---|---|
| Windows, with `store == "file"` | `NoStore` |
| The folder cannot hold a file private to one user | `NoStore` |
| The store cannot be used at all | `CredentialError` |
| The fallback file's folder is missing or cannot be written | `CredentialError`, naming the path |
| The existing fallback file cannot be read, or is not valid JSON | `CredentialError` — saving over it would discard what could not be parsed |
| The existing fallback file is a symlink, or is owned by another user, where the platform offers those checks | `CredentialError` — §3 decision 6 covers the read `write()` makes first |

**Every one of these is typed, and that is a requirement rather than tidiness.**
`docs/design.md` § Errors has parts raise typed failures and a test walk the
list, so an `OSError` allowed to escape `write()` reaches the Face's
last-resort catch and the writer is told *something went wrong that Pressless
did not expect* after failing to save his key. `CredentialError` rather than
`NoStore` for the rows that arise from an `OSError`: the store is fine and the
attempt failed, so the remedy is to try again rather than to stop setting up.
The two `NoStore` rows are the other case — there is nowhere to keep it at
all, and setup stops rather than retrying. PRESS-0001 §4.4 makes the same
call for `settings.json`.

The Windows row is §3 decision 1
applying wherever the file store is reached, not only where it is chosen, so a
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

Every read of the fallback file — including the one `write()` makes first to
keep the other secret — opens it with `O_NOFOLLOW`, so a symlink at that name
is refused by the open rather than followed, and then refuses a file whose
owner is not the user running Pressless (§3 decision 6). The owner is read off
the open descriptor rather than the path, so what was checked is what is read;
a descriptor cannot report a symlink, which is why that half is the open's
job. Either refusal raises `CredentialError` — the file is a store that must
not be acted on rather than an absent one, and §4.3 records why that
distinction decides what setup does next.

Each check is applied where the platform offers it and skipped where it does
not. ADR-0003 asks for a capability test rather than a platform one, which is
the shape §4.6's mode check already takes.

Windows offers neither `O_NOFOLLOW` nor an owner to compare against, so the
read there is unchecked — the intended end state rather than an oversight.
Nothing on Windows writes this file (INV-2), so one found there was carried
deliberately, and refusing it would refuse the recovery §4.3 keeps open. And
decision 1's own finding is that Windows cannot make the file private in the
first place, so a check that cannot run there withholds no protection the
platform was offering.

### 4.5 What this module never does

- **Never writes a secret anywhere but the chosen store.** Not to the log, not
  to the settings file, not to an exception message, not to the screen —
  `docs/design.md` § Logging and ADR-0003.
- **Never words anything for the writer.** It raises typed failures; the Face
  turns them into sentences (`docs/design.md` § Errors).
- **Never decides whether a store is good enough.** It reports which one
  answered. Judging that is the writer's, once he is told.

### 4.6 What was measured, and where

These decided the design above, and none of them follows from the library's
documented types. Each was executed on the development machine on 2026-08-25,
or read from the library's own source where the claim is about what its code
does; the bullets say which. INV-3, INV-5, INV-7 and INV-9 are what hold them
once the code exists.

- **A read for a secret that is not there came back truthy, not a string, and
  never `None`.** The nominated store is a chain, and one of its members is a
  kernel-keyring backend whose own module docstring says it returns *"a
  callable instead of None in case of a non-existing password"*. The chain
  returns its first non-`None` answer, so it stops at that object and no later
  member is consulted — absence has no `None` left to signal it, which is why
  §4.3 reads *not a `str`* as *nothing is stored*. A read for a secret that IS
  there returns the string, so the keyring path stays reachable. **Read from
  that backend's source rather than executed:** the object is callable, and
  calling it prompts on the terminal and stores what it reads — so an
  implementation that "just uses the value" hangs the app on a password prompt
  nobody asked for.
- **The library's own failure backend raises `keyring.errors.NoKeyringError`**
  from `get_password`, `set_password` and `delete_password` alike. It
  subclasses `KeyringError`, which subclasses `RuntimeError`. §4.2 uses that
  type as its discriminator, so this is the fact that separates *no store*
  from *broken store*.
- **The chain includes a plaintext file backend, behind the masking member.**
  So "the operating system's store" can be a plain file — which is what
  ADR-0003 exists to avoid, and nothing distinguishes the two without naming
  the member that answered. On this chain a read *through the store* never
  reaches it, which is why §4.2 asks the members directly instead: a member
  that cannot be reached cannot be named either, and naming it is §3
  decision 2.
- **`mkstemp` creates its file owner-only and `os.replace` preserves that
  mode.** Verified by writing one, replacing a world-readable target, and
  reading the mode back — on ext4. A mount that does not enforce POSIX modes
  ignores the request and `chmod` cannot repair it, so `write()` reads the
  mode back off the descriptor `mkstemp` returned, before the secret is
  written into it, and raises `NoStore` where any group or other bit is set.
  That is ADR-0003's capability test rather than a platform proxy for it, and
  checking the temporary means the secret never reaches such a filesystem.
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
  raises `NoStore` where the write raises `NoKeyringError`, and
  `write(store="file", ...)` raises `NoStore` however it was reached.
  *Test:* `tests/test_credentials.py::test_windows_never_writes_a_file` —
  patch the platform to Windows, make the store's write raise
  `NoKeyringError`, and assert both calls raise **`NoStore` specifically** and
  that `folder` is empty afterwards.
  *Breaks when:* the fallback is written once and applied on both systems,
  which §4.6's `chmod` measurement makes unsafe.
  **Asserting the type is what makes it bite:** a *locked* store on Windows
  also leaves `folder` empty, so a clause asserting merely that something was
  raised passes against an implementation reporting a locked keyring as
  *nowhere to keep it* — §4.2's discriminator undone. Otherwise only this rule
  can reject the fixture: on any other platform the same arguments select and
  write the file store.

- **INV-3** — `read()` returns a `str` or raises. A store answering with
  anything else raises `NotStored`, and what it answered never reaches the
  caller.
  *Test:* `tests/test_credentials.py::test_non_string_answer_is_absence` — a
  patched store returning **any** truthy non-`str` object. §4.6's measurement
  is why the rule exists; it is not a requirement on the fixture, and the test
  must not import the distribution that produced the measured one.
  *Breaks when:* an implementer returns the store's answer unexamined, so an
  object reaches the Publisher as an authorisation header — or reads it as a
  malfunction, which sends a writer who has no key yet down the broken-store
  path instead of asking him for one.
  Only this rule can reject the fixture: the store answers rather than
  failing, so nothing else here fires.

- **INV-4** — A store holding nothing for an account raises `NotStored`; a
  store that cannot be used raises `CredentialError`. Neither is the other.
  *Test:* `tests/test_credentials.py::test_absent_and_broken_differ` — two
  patched stores, one answering with any truthy non-`str` object, one raising.
  *Breaks when:* both are caught as "no key" and setup overwrites the key the
  writer still had.
  **The fixture may not use `None`:** §4.6 measured that the chain on the
  machine running this suite never returns it, so a `None` fixture exercises a
  signal that cannot occur there. Both fixtures are otherwise valid, so only
  the requirement that the two outcomes *differ* can fail the pair.

- **INV-5** — The fallback file is owner-only from the instant it exists.
  *Test:* `tests/test_credentials.py::test_fallback_file_is_owner_only` —
  assert `write()` reaches `os.replace` with `folder / "credentials.json"` as
  its destination, then write one and read the mode back.
  **The test holds its own copy of that name and does not import
  `FILE_NAME`.** This project's `CLAUDE.md` requires it: share the literal and
  the invariant compares the module against itself, so the fallback file could
  be renamed to anything and stay green — which §2 point 4 makes an on-disk
  shape that orphans an existing machine's key.
  *Breaks when:* an implementer opens the target directly and chmods
  afterwards, leaving a window in which the key is readable.
  **Asserting the mechanism is what makes it bite:** a direct write followed
  by a `chmod` ends at the same mode, so the mode check alone would pass
  against the implementation this rule exists to reject. Both halves are
  skipped on a real Windows host: §4.6's capability read refuses the write
  there, so `write()` raises `NoStore` and never reaches `os.replace` — §7
  carries the rule for every clause that needs a file-store write.

- **INV-6** — No exception this module raises contains a secret value.
  *Test:* `tests/test_credentials.py::test_no_failure_names_the_secret` — with
  a sentinel as the secret, force every failure that has one in hand as well as
  every row of §4.3's table: `write()` into an unwritable folder, `write()`
  refused on Windows, and each read failure. Assert the sentinel appears in no
  message.
  *Breaks when:* an implementer puts the value in a message to make a failure
  easier to diagnose, and the log or a screenshot then carries the key.
  **§4.3's table alone cannot catch it:** that table enumerates `read()`'s
  outcomes, and `read()` is never handed a secret. `write()` is the side that
  is, so a clause testing only the table stays green against an implementer who
  names the secret in `write()`'s error.

- **INV-7** — `choose()` names the store that answered the round-trip, not the
  one the library nominates, and it deletes the probe only after asking.
  *Test:* `tests/test_credentials.py::test_choice_names_the_answering_store` —
  a patched chain whose first member holds nothing and whose second holds the
  probe; assert the name is the second member's, **and** that the delete was
  recorded after the members were asked rather than before.
  *Breaks when:* the name is taken from the nominated store, which on the
  development machine is a chain — not a store, and one hiding a plaintext
  member; or the probe is deleted as part of the round-trip, so nothing holds
  the value by the time the members are asked and none of them can answer.
  **Asserting the order is what makes the fixture bite:** a patched chain still
  holding the probe answers whichever way the code is written, so the naming
  half alone passes against an implementation that deletes first and then finds
  nothing on a real machine.

- **INV-8** — Writing one account's secret leaves the other's unchanged.
  *Test:* `tests/test_credentials.py::test_second_write_keeps_the_first` —
  write two accounts through the file store, then read the first back.
  *Breaks when:* the file is rebuilt from the one secret in hand, so setting
  up the dashboard discards the publishing key.

- **INV-9** — `choose()` reads `NoKeyringError` as *no store* and every other
  exception as *a store that cannot be relied on*.
  *Test:* `tests/test_credentials.py::test_locked_store_is_not_an_absent_one`
  — two patched stores whose write raises, one `NoKeyringError` and one any
  other `KeyringError`; off Windows, assert the first yields
  `Choice("file", ...)` and the second raises `CredentialError`.
  *Breaks when:* an implementer catches every exception as "no store", so the
  fallback fires against a keyring that is merely locked and the writer's key
  lands in a file while his own store works.
  Only this rule can reject the fixture: both stores raise and neither returns
  a value, so every other rule here behaves identically — only the requirement
  that the two outcomes differ *by type* can fail it.

- **INV-10** — every read of the fallback file, `write()`'s own pre-read
  included, refuses a symlink and refuses a file owned by another user,
  wherever the platform offers those checks. Both raise `CredentialError`. It
  does not refuse on the file's mode.
  *Test:* `tests/test_credentials.py::test_fallback_read_refuses_what_is_not_ours`
  — put a symlink at the file's name pointing at a **well-formed** fallback
  file holding a different secret for the same account, and assert `read()`
  raises `CredentialError` rather than returning that secret; patch the owner
  reported for the open descriptor and assert the same type again. Then write
  a file, widen its mode, and assert `read()` still returns the secret.
  Then assert `write()` refuses that same symlink and that same patched owner
  with `CredentialError`, leaving `folder` unchanged.
  *Breaks when:* an implementer refuses on the mode as well, which reads as
  stricter and rejects the file a recovering machine was carried — the case
  §3 decision 1 and `write()`'s own comment protect.
  **The symlink's target must be well-formed or the clause cannot fail:**
  pointed at any other file, an implementation with no `O_NOFOLLOW` follows
  the link, fails to parse it, and raises `CredentialError` from §4.3's
  not-valid-JSON row — green against the very defect the clause names.
  **And the permissive-mode case is what stops the pair being satisfied by
  refusing everything unusual:** only that assertion can fail such a build.
  **The `write()` clause is not a duplicate of the `read()` ones:** an
  implementer who guards `read()`'s own path and leaves the pre-read alone
  passes every other assertion here, and decision 6's attack survives intact
  — the planted file is merged forward into one the writer owns, which a
  later compliant `read()` then accepts.

## 6. Failure modes

- **No store, on Windows.** `choose()` raises `NoStore` and setup stops.
  There is no route that finishes setup with the key in a file there.
- **No store, elsewhere.** The file store is chosen and named. ADR-0003
  requires the writer be told, and §4.2 gives the Face the fact to tell him
  with.
- **A store that is present but locked.** The probe raises something other
  than `NoKeyringError`, so `CredentialError` rather than a fallback. That is
  what §4.2's discriminator buys: the remedy is unlocking it, and falling back
  would leave the key in a file while a working store sits beside it.
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

`tests/test_credentials.py`, unlabelled — it declares no custom marker and
needs no fixture beyond a temporary directory, unlike the archive test
PRESS-0004 carries. One test per invariant, named in §5 and tabulated in
§10.

**No test touches the real store.** Every test that names the operating
system's store patches it. A test that called the library for real would write
into the machine's own keyring, which is somebody's login keyring on the one
machine that runs this suite.

**The file-store tests patch the platform check, and some of them need more
than that.** INV-2 makes `write(store="file", ...)` raise on Windows however
it is reached, and INV-5, INV-6, INV-8 and INV-10 all write through the file
store — so on Windows they would fail against a correct implementation. They set the
platform to a non-Windows value, exactly as INV-2's own test sets it to
Windows.

**INV-6 sets it both ways inside one test**, because one of the failures it
must force is the Windows refusal itself, and the rest need the file store to
work. **And a real Windows host holds back every clause that needs a file-store
write to succeed** — not INV-5's mode read-back alone. Patching the platform
check does not give a Windows filesystem POSIX permissions, so §4.6's
capability read refuses the write there and `write()` raises `NoStore` before
it reaches `os.replace`. That is the correct behaviour, so a suite skipping
only the mode read-back goes red on a correct implementation.

**INV-10's two refusals are held back for a different reason** — in the code
rather than in the platform: §4.4 skips both checks where the platform offers
neither, so a correct implementation refuses nothing there and the assertions
would fail against it.

What runs everywhere is every clause needing no successful file-store write.

**The red run is made against a stub `credentials.py`, never against an absent
one.** With the module absent the suite errors at collection and no assertion
runs — this project's `CLAUDE.md` records that trap. The stub declares every
name in §4.1 and raises `NotImplementedError` from each function.

**Not every test then fails, and that is by design.** A stub importing no
sibling already satisfies INV-1, whose test reads the module's imports rather
than its behaviour — and it satisfies INV-6 as well, whose assertion is that a
sentinel appears in *no* message, which is trivially true of a stub that raises
`NotImplementedError` from everything. The red run is every test collected with
the rest failing on assertions; INV-1's or INV-6's going red against the
stub means the stub is wrong, not the test. Read the collected count, not the
exit code.

## 8. Alternatives considered (and rejected)

- **Talk to each operating system's store directly, with no dependency.**
  `ctypes` to Windows Credential Manager, D-Bus to Secret Service. It keeps
  the project dependency-free, which `CLAUDE.md` § Build and test no longer
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
- **Refusing the fallback file on its MODE as well as its owner** (§3
  decision 6). Rejected: a file carried from another machine is what recovery
  reads, and its mode did not survive the journey while its ownership became
  the writer's on the copy that carried it. A mode check reads as stricter and
  rejects exactly that file.

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
| INV-3 | `tests/test_credentials.py::test_non_string_answer_is_absence` |
| INV-4 | `tests/test_credentials.py::test_absent_and_broken_differ` |
| INV-5 | `tests/test_credentials.py::test_fallback_file_is_owner_only` |
| INV-6 | `tests/test_credentials.py::test_no_failure_names_the_secret` |
| INV-7 | `tests/test_credentials.py::test_choice_names_the_answering_store` |
| INV-8 | `tests/test_credentials.py::test_second_write_keeps_the_first` |
| INV-9 | `tests/test_credentials.py::test_locked_store_is_not_an_absent_one` |
| INV-10 | `tests/test_credentials.py::test_fallback_read_refuses_what_is_not_ours` |
| INV-10 where the platform offers no `O_NOFOLLOW` and no owner to compare | **nothing, and nothing can** — §4.4 skips both checks there, so there is no refusal to observe. INV-2 removes the write side of that platform rather than checking it |
| INV-10's ownership refusal against a file really owned by another user | **half** — the suite cannot create one without a second account, so that clause patches the owner the descriptor reports. The symlink refusal and the permissive-mode acceptance both run for real |
| ADR-0003's promise that the store protects the secret as well as the writer's other passwords | **nothing** — INV-7 makes the store *nameable*, which is all this module can do. Whether a named store is good enough is not decidable here, and §3 decision 2 is the reason the question reaches the writer at all |
| INV-2's rule on the machine it protects | **half** — the test patches the platform, and no Windows runs this suite. PRESS-0022 stages the built executable to a Windows box before release, which is the only place the real behaviour is observed; it schedules no check of its own |
| ADR-0003's capability test, where the filesystem does not enforce modes | `tests/test_credentials.py::test_a_folder_that_cannot_keep_a_file_private_is_refused` — INV-5 cannot, since it reads the mode back on ext4 where the request is honoured |
| INV-5's file mode on Windows | **nothing, and nothing can** — §4.6's measurement is that the mode is unenforceable there. INV-2 removes the case rather than checking it |
| No secret reaching the rolling log | **nothing here** — INV-6 covers this module's own messages. The log is the Face's and `docs/design.md` § Logging is the rule; PRESS-0011 owns the surface |
| The Face fetching a secret and handing it over, rather than the Publisher or Insights reaching a store themselves (design rule 10) | **nothing here** — INV-1 stops this module reaching them, not them reaching past it. PRESS-0009's and PRESS-0019's own INV-1 forbid the other direction |

## 11. Cross-doc impact

- **`docs/design.md` § The parts and § What may depend on what — and this one
  is a decision, not a wording fix.** Rule 5 lets the Publisher read
  *"Settings and a folder of finished files, and nothing else"* and rule 8
  lets Insights read *"Settings and may talk to Google, and nothing else"*.
  This module is not Settings and § The parts does not list it, so as those
  rules stand neither part may call it — and PRESS-0001 §4.5 refuses to hold
  the secret, so routing through Settings is not open either. **Settled
  2026-08-25 by `docs/design.md` rule 10:** the Face fetches the secret and
  hands it over, rules 5 and 8 unchanged.
- `docs/decisions/ADR-0003` — three corrections, all made 2026-08-25: the
  fallback file's home, the platform on which the fallback is refused, and
  naming the store that answered.
- `pyproject.toml` gained the keyring library and `CLAUDE.md` § Build and test
  was rewritten around it. Both landed with the implementation.
- `docs/design.md` § The stack already names the operating system's keyring,
  and § Where everything sits on disk already places the fallback file. Those
  two sections are unchanged; the two named above are not.
- `docs/decisions/ADR-0003` needs no fourth correction for §3 decision 6. Its
  capability test is the shape the read's checks take rather than something
  they depart from.
- `CHANGELOG.md` — an entry when it ships.
- PRESS-0001 is unchanged. This fills the hole its §4.5 names rather than
  moving anything it holds.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-25 | 3, cold — genre pinned `spec`; packet carried the measured keyring behaviour, both ADRs, PRESS-0001's surface and invariants, design.md's dependency rules and `settings.py` whole. Windows declared an unrunnable region, so Q1 was out of scope there | 0 | 5 | 2 | 1 | **Eight verified, eight fixed; one dismissed. First gate on this document.** **Two findings were made independently by all three lanes**, the strongest signal in the run. §4.2 specified the probe as *write, read back, delete* and then asked for *the first member returning the probe value* — the value being gone by then, so `choose()` names nothing on a real machine while INV-7's patched fixture, which never deletes, stays green. And §2 claimed design.md's rules 5 and 8 put this module "inside the Settings lane", when both read *Settings … and nothing else* and § The parts lists no such part — so as those rules stand neither the Publisher nor Insights may call it, and PRESS-0001 §4.5 refuses to hold the secret, so routing through Settings is not open either. **The best single finding came from one lane and got worse when measured.** §4.3 gave *holds nothing* → `NotStored` and *not a `str`* → `CredentialError` as separate rows, while §4.6's own measurement says an absent secret comes back truthy and not a string: one observation, two rows, no precedence. Run rather than reasoned — the backend's docstring says it returns *a callable instead of None*, and the chain returns its first non-`None` answer and stops there, so `None` never occurs on the machine that runs this suite and INV-4's `None` fixture tested a signal that cannot happen. The rule is now *anything that is not a `str` means nothing is stored*, merging two rows into one. **A second measured fix:** absence and malfunction both reach `choose()` as a raise, so the fallback either never fired or fired past a locked store; `NoKeyringError` is now the named and only discriminator. **One Q4 and one Q3 were clauses that could not catch what they named** — INV-6 forced only §4.3's read failures while `write()` is the side handed a secret, and nothing said what an unrecognised fallback-file `version` does though PRESS-0021 branches on the exception. **One finding was surfaced rather than fixed:** amending design.md's dependency rules is a decision about another document, so §11 records the two ways out and this spec chooses neither. **Dismissed as true-but-inert:** `Choice.name`'s format is unpinned, and §4.5 forbids this module from judging a store, so nothing parses it. **Three open questions resolved clean and are not counted** — a present secret does return a `str` (executed, so the keyring path is reachable and the delete-last ordering is measured rather than argued), design.md § The stack does name the keyring, and PRESS-0001 §4.5 hands the fallback location here rather than stating it, which corrected §3 decision 3's wording in passing. |
| 2 | 2026-08-25 | 3, cold — identical brief, packet rebuilt from disk and extended with the chain's read semantics read from source; Windows still an unrunnable region | 1 | 6 | 2 | 1 | **Ten verified, ten fixed. Cap reached (2 for a spec); the run files its tail and ships. A VIOLENT cap: six of the ten landed on text loop 1 wrote**, each anchor checked against loop 1's ledger rather than recalled — so the run was oscillating on the passages loop 1 rewrote, and a third loop would mostly repair the second. **The best finding is a mechanism defect one lane reached by reading the library's source.** §4.2 decided *keyring* by reading the probe back through the store, and a chain answers with its first member that answers at all — so a member answering unconditionally masks every member behind it, and the read-back can report failure while a working member holds the value. That is not hypothetical here: the masking member sits ahead of the plaintext one, so §4.6's plaintext bullet described a member a chain read can never reach, and §3 decision 2's promise to NAME the store could not have been kept. The verdict now rests on the member walk §4.2 already required for the name, which collapsed two mechanisms into one. **Two lanes independently found that `write()`'s failures were untyped** — §4.3's table was `read()`'s alone while INV-6 named *write() into an unwritable folder* as a failure to force, so `docs/design.md` § Errors would have been breached by an `OSError` reaching the Face's last-resort catch after the writer failed to save his key; §4.3 gains a `write()` table. **One lane caught a breach of this project's own rule**: INV-5's clause pointed the test at `folder / FILE_NAME`, and `CLAUDE.md` says a test that pins a name must hold its own copy and *"Do not tidy this into an import"* — as written the fallback file could be renamed to anything and stay green. **A Q4 found that loop 1's own discriminator had no checker at all**, no invariant and no `nothing` row, so an implementer could catch every exception as *no store* and ship the fallback firing against a locked keyring; INV-9 now holds it. **Three more were loop 1's collateral**: INV-6 needed both platforms while §7 pinned its tests to one, §7 named INV-1 as the only test green against the stub when INV-6 is too, and §7 claimed a platform patch keeps *runs everywhere* true when patching a check cannot give a Windows filesystem POSIX modes. **The one Q1 was the orchestrator's, found while re-reading §4.6**: its preamble said *These three* over five bullets and claimed all were executed, when the callable-prompts behaviour was read from source. The count is deleted rather than corrected and the bullet says which it is. **Three open questions resolved clean and are not counted** — all three lanes asked whether PRESS-0001 §6 says what §4.1 attributes to it, and it does; a plain grep first reported the phrase missing, which was the hard wrap rather than the document. |
| 3 | 2026-09-02 | 3, cold — new run, armed by §3 decision 6 (rule 14). Genre pinned `spec`; packet carried `credentials.py` and its tests whole, ADR-0003, `design.md`, PRESS-0001 §4.4–4.5 and the measured `O_NOFOLLOW` and ownership behaviour. Windows an unrunnable region | 3 | 4 | 3 | 1 | **Eleven verified, eleven fixed, none dismissed.** **All three lanes:** INV-10 named no exception type where §4.3 requires every failure typed — and the two candidates are not interchangeable, `NotStored` sending setup to overwrite a key the writer still has. **Two lanes:** the new test could not fail — a symlink pointed at any ordinary file is followed, fails to parse, and raises `CredentialError` from the not-valid-JSON row, green against the defect it names. **Two lanes:** decision 6 was reachable by the other door, `write()`'s pre-read going through the same helper, so a substituted file is merged and the next read passes both checks. **One lane:** *both are taken from the open descriptor* is false of the symlink half — `fstat` never reports one, so only the open can refuse it; measured. **Two lanes:** §1 and §2 still had the Publisher and Insights reaching Credentials, which design rule 10 settled the other way and §11 already recorded. Windows' unchecked read, raised as an open question by two lanes, is now stated as intended with its reason. |
| 4 | 2026-09-02 | 3, cold — identical brief, packet rebuilt whole from disk and corrected: two cross-references had leaked their own review logs, and PRESS-0001's excerpt had run to EOF. Windows still an unrunnable region | 2 | 3 | 0 | 2 | **Seven verified, seven fixed, none dismissed. Cap reached (2 for a spec); the tail is empty and the run ships. A VIOLENT cap: four of the seven landed on text this run wrote**, each anchor checked against loop 1's ledger rather than recalled. **The sharpest was one lane's alone** — loop 1 widened INV-10 to cover `write()`'s pre-read and left the test clause asserting `read()` only, so decision 6's own attack survived a green suite: the planted file is merged forward into one the writer owns, which a later compliant read accepts. **Two lanes found §7's Windows rule false and pre-existing:** §4.6's capability read refuses every file-store write on a real Windows host, so far more than the two named clauses are unreachable there, and the 4b sweep then found INV-5 restating the same false claim. **All three lanes** found §3 decision 3 still asking for an ADR correction §11 records as made. Also fixed: a table row stated unconditionally where §4.4 skips by capability, prose contradicting its own table's two `NoStore` rows, and a count loop 1 falsified. **Promoted from two lanes' open questions:** decision 6 named the removable drive, where ownership cannot fire — now scoped to the shared one. **The gate earned its lanes:** most of both loops' findings fell inside the amended span rather than auditing the rest. |
