# INV-1..9 for PRESS-0002 (Credentials). One test per invariant, named in
# that spec's §5 and tabulated in its §10. Unlabelled and needs nothing but a
# temporary directory (spec §7).
#
# Why this exists: docs/specs/PRESS-0002-credentials.md is the contract.
#
# NO TEST TOUCHES THE REAL STORE. Every test that names the operating
# system's store patches keyring.get_keyring, which is the module's only way
# in. A test that called the library for real would write into the machine's
# own login keyring (spec §7).
from __future__ import annotations

import ast
import inspect
import json
import os
import stat
import sys
from pathlib import Path

import keyring.errors
import pytest

import pressless.credentials as credentials_module
from pressless.credentials import (
    Choice,
    CredentialError,
    NoStore,
    NotStored,
    choose,
    read,
    write,
)

# The documented fallback file name (§4.4). Written out here rather than
# imported: share the literal and INV-5 compares the module against itself,
# so the file could be renamed to anything and stay green. CLAUDE.md forbids
# tidying this into an import.
FILE_NAME = "credentials.json"

# A value no real secret would be. INV-6 asserts it reaches no message.
SENTINEL = "sentinel-secret-must-not-appear-in-any-message"

# The REAL host, captured before any test patches sys.platform. INV-5's mode
# half is unenforceable on a Windows filesystem (§10); its mechanism half
# runs everywhere.
_REAL_WINDOWS = os.name == "nt"


class _Masking:
    """Answers with a truthy non-str object for a secret that is not there.

    Modelled on the kernel-keyring backend §4.6 measured, and built here
    rather than imported from it: INV-3 is a rule about any such answer, not
    a requirement on that distribution. Calling the object is what hangs the
    app, so it records whether anything did.
    """

    called = False

    def __call__(self, *args, **kwargs):
        _Masking.called = True
        return "a password read from a terminal prompt nobody asked for"


class _Store:
    """A patchable stand-in for whatever keyring.get_keyring() returns."""

    def __init__(self, name="fake store", values=None, raises=None, events=None,
                 backends=None):
        self.name = name
        self._values = dict(values or {})
        self._raises = raises
        self.events = events if events is not None else []
        if backends is not None:
            self.backends = backends

    def get_password(self, service, account):
        self.events.append(("get", self.name))
        if self._raises is not None:
            raise self._raises
        return self._values.get((service, account))

    def set_password(self, service, account, secret):
        self.events.append(("set", self.name))
        if self._raises is not None:
            raise self._raises
        self._values[(service, account)] = secret

    def delete_password(self, service, account):
        self.events.append(("delete", self.name))
        self._values.pop((service, account), None)


def _use(monkeypatch, store):
    monkeypatch.setattr(credentials_module.keyring, "get_keyring", lambda: store)


def _not_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")


def _windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")


def test_credentials_imports_no_sibling():
    """INV-1: credentials.py imports no other pressless module.

    Walks the module's AST, as test_settings_imports_nothing_forbidden does.

    Breaks when an implementer imports pressless.settings to fetch the
    account names itself, which makes the Publisher's one documented way in
    two.

    Weak in the way the spec names (§5): an import walk passes against a
    module that does nothing. It is evidence about imports, never about
    reaching a store, and it passes against the stub by design.
    """
    tree = ast.parse(inspect.getsource(credentials_module))

    imported_top_level = set()
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_top_level.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_imports.append(node)
            elif node.module:
                imported_top_level.add(node.module.split(".")[0])

    assert "pressless" not in imported_top_level, (
        "credentials.py imports another pressless module. INV-1 keeps the "
        "Publisher's one documented way in singular"
    )
    assert not relative_imports, (
        f"credentials.py has relative import(s) "
        f"{[n.module for n in relative_imports]!r}, which can only name a "
        f"sibling pressless module"
    )


def test_windows_never_writes_a_file(tmp_path, monkeypatch):
    """INV-2: on Windows no code path writes a secret to a file.

    Asserting the TYPE is what makes this bite: a locked store on Windows
    also leaves the folder empty, so asserting merely that something was
    raised passes against an implementation reporting a locked keyring as
    'nowhere to keep it' — §4.2's discriminator undone.

    Breaks when the fallback is written once and applied on both systems,
    which §4.6's chmod measurement makes unsafe.
    """
    _windows(monkeypatch)
    _use(monkeypatch, _Store(raises=keyring.errors.NoKeyringError("no store")))

    with pytest.raises(NoStore):
        choose()
    with pytest.raises(NoStore):
        write("file", tmp_path, "publishing-key", SENTINEL)

    assert list(tmp_path.iterdir()) == [], (
        "Windows left a file behind; os.chmod there sets only the read-only "
        "flag, so that file is readable by anyone on the PC"
    )


def test_non_string_answer_is_absence(tmp_path, monkeypatch):
    """INV-3: read() returns a str or raises, and a non-str answer is absence.

    Breaks when an implementer returns the store's answer unexamined, so an
    object reaches the Publisher as an authorisation header — or reads it as
    a malfunction, which sends a writer who has no key yet down the
    broken-store path instead of asking him for one.
    """
    _Masking.called = False
    _use(monkeypatch, _Store(values={("Pressless", "publishing-key"): _Masking()}))

    with pytest.raises(NotStored) as caught:
        read("keyring", tmp_path, "publishing-key")

    assert not _Masking.called, (
        "the answer was called. §4.6: calling it opens a hidden getpass "
        "prompt that hangs the app"
    )
    assert "terminal prompt" not in str(caught.value), (
        "what the store answered reached the caller through the message"
    )


def test_absent_and_broken_differ(tmp_path, monkeypatch):
    """INV-4: a store holding nothing raises NotStored; a store that cannot
    be used raises CredentialError. Neither is the other.

    Neither fixture uses None: §4.6 measured that the chain on the machine
    running this suite never returns it, so a None fixture exercises a signal
    that cannot occur there.

    Breaks when both are caught as 'no key' and setup overwrites the key the
    writer still had.
    """
    _use(monkeypatch, _Store(values={("Pressless", "publishing-key"): _Masking()}))
    with pytest.raises(Exception) as absent:
        read("keyring", tmp_path, "publishing-key")

    _use(monkeypatch, _Store(raises=keyring.errors.KeyringLocked("locked")))
    with pytest.raises(Exception) as broken:
        read("keyring", tmp_path, "publishing-key")

    assert isinstance(absent.value, NotStored)
    assert isinstance(broken.value, CredentialError)
    assert type(absent.value) is not type(broken.value), (
        "absent and broken are the same outcome, so setup sends a writer who "
        "has a key to re-enter it and overwrites the one he had"
    )


def test_fallback_file_is_owner_only(tmp_path, monkeypatch):
    """INV-5: the fallback file is owner-only from the instant it exists.

    Asserting the MECHANISM is what makes this bite: a direct write followed
    by a chmod ends at the same mode, so the mode check alone would pass
    against the implementation this rule exists to reject.

    Breaks when an implementer opens the target directly and chmods
    afterwards, leaving a window in which the key is readable.
    """
    _not_windows(monkeypatch)
    destinations = []
    real_replace = os.replace

    def spy(source, destination):
        destinations.append(Path(destination))
        return real_replace(source, destination)

    monkeypatch.setattr(credentials_module.os, "replace", spy)
    write("file", tmp_path, "publishing-key", SENTINEL)

    assert destinations == [tmp_path / FILE_NAME], (
        f"write() did not reach os.replace with {tmp_path / FILE_NAME} as its "
        f"destination; it reached {destinations!r}. A direct write leaves a "
        f"window in which the key is readable"
    )

    if _REAL_WINDOWS:
        pytest.skip("the file mode is unenforceable on Windows (§10); INV-2 "
                    "removes the case rather than checking it")
    mode = stat.S_IMODE((tmp_path / FILE_NAME).stat().st_mode)
    assert mode == 0o600, f"the fallback file is mode {mode:#o}, not owner-only"


def test_no_failure_names_the_secret(tmp_path, monkeypatch):
    """INV-6: no exception this module raises contains a secret value.

    Forces every failure that has a secret in hand as well as every row of
    §4.3's table. §4.3's table alone cannot catch it: that table enumerates
    read()'s outcomes, and read() is never handed a secret. write() is the
    side that is.

    Breaks when an implementer puts the value in a message to make a failure
    easier to diagnose, and the log or a screenshot then carries the key.

    Sets the platform BOTH ways: one of the failures is the Windows refusal
    itself, and the rest need the file store to work.
    """
    messages = []

    def collect(kind, *args):
        with pytest.raises(Exception) as caught:
            kind(*args)
        messages.append(str(caught.value))

    # The Windows refusal — the one failure that needs Windows.
    _windows(monkeypatch)
    collect(write, "file", tmp_path, "publishing-key", SENTINEL)

    # Everything else needs the file store to work.
    _not_windows(monkeypatch)
    missing = tmp_path / "no-such-folder"
    collect(write, "file", missing, "publishing-key", SENTINEL)

    _use(monkeypatch, _Store(raises=keyring.errors.KeyringLocked("locked")))
    collect(write, "keyring", tmp_path, "publishing-key", SENTINEL)
    collect(read, "keyring", tmp_path, "publishing-key")

    _use(monkeypatch, _Store(values={("Pressless", "publishing-key"): _Masking()}))
    collect(read, "keyring", tmp_path, "publishing-key")

    empty = tmp_path / "empty"
    empty.mkdir()
    collect(read, "file", empty, "publishing-key")

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / FILE_NAME).write_text("{not json", encoding="utf-8")
    collect(read, "file", broken, "publishing-key")

    later = tmp_path / "later"
    later.mkdir()
    (later / FILE_NAME).write_text(
        json.dumps({"version": 99, "secrets": {"publishing-key": SENTINEL}}),
        encoding="utf-8",
    )
    collect(read, "file", later, "publishing-key")

    leaked = [m for m in messages if SENTINEL in m]
    assert not leaked, f"a failure message carries the secret: {leaked!r}"


def test_choice_names_the_answering_store(monkeypatch):
    """INV-7: choose() names the store that ANSWERED the round-trip, not the
    one the library nominates, and deletes the probe only after asking.

    Asserting the ORDER is what makes the fixture bite: a patched chain still
    holding the probe answers whichever way the code is written, so the
    naming half alone passes against an implementation that deletes first and
    then finds nothing on a real machine.

    Breaks when the name is taken from the nominated store, which on the
    development machine is a chain hiding a plaintext member; or when the
    probe is deleted as part of the round-trip.
    """
    events = []
    silent = _Store(name="holds nothing", events=events)
    holder = _Store(name="the answering member", events=events)
    chain = _Store(name="chainer", events=events, backends=[silent, holder])

    # The chain's write reaches the second member, and only that one.
    def chain_set(service, account, secret):
        events.append(("set", "chainer"))
        holder._values[(service, account)] = secret

    chain.set_password = chain_set
    _use(monkeypatch, chain)

    result = choose()

    assert result == Choice("keyring", "the answering member"), (
        f"choose() returned {result!r}; the name must be the member that "
        f"answered, not the chain the library nominates"
    )
    kinds = [kind for kind, _ in events]
    assert "delete" in kinds, "the probe was never deleted"
    assert kinds.index("delete") > max(
        i for i, kind in enumerate(kinds) if kind == "get"
    ), (
        f"the probe was deleted before the members were asked: {events!r}. On "
        f"a real machine nothing would hold the value by then"
    )


def test_second_write_keeps_the_first(tmp_path, monkeypatch):
    """INV-8: writing one account's secret leaves the other's unchanged.

    Breaks when the file is rebuilt from the one secret in hand, so setting
    up the dashboard discards the publishing key.
    """
    _not_windows(monkeypatch)
    write("file", tmp_path, "publishing-key", "the-github-one")
    write("file", tmp_path, "analytics", "the-google-one")

    assert read("file", tmp_path, "publishing-key") == "the-github-one", (
        "the second write discarded the first secret"
    )
    assert read("file", tmp_path, "analytics") == "the-google-one"


def test_locked_store_is_not_an_absent_one(monkeypatch):
    """INV-9: choose() reads NoKeyringError as 'no store' and every other
    exception as 'a store that cannot be relied on'.

    Breaks when an implementer catches every exception as 'no store', so the
    fallback fires against a keyring that is merely locked and the writer's
    key lands in a file while his own store works.
    """
    _not_windows(monkeypatch)

    _use(monkeypatch, _Store(raises=keyring.errors.NoKeyringError("absent")))
    absent = choose()
    assert absent.store == "file", (
        f"an absent store gave {absent!r}; off Windows it selects the file "
        f"fallback"
    )

    _use(monkeypatch, _Store(raises=keyring.errors.KeyringLocked("locked")))
    with pytest.raises(CredentialError):
        choose()


# ------------------------------------------------------------ PRESS-0042 ----


def test_a_folder_that_cannot_keep_a_file_private_is_refused(tmp_path, monkeypatch):
    """PRESS-0042: the owner-only guarantee is CHECKED, not asserted.

    ADR-0003 states a CAPABILITY test -- "where a file cannot be made private
    to one user there is no fallback: setup stops and says so". The module
    implemented a PLATFORM proxy instead: it refused Windows and allowed
    everything else. `mkstemp` asks for 0600, and a mount that does not
    enforce POSIX modes -- vfat, exFAT, NTFS, CIFS and many FUSE mounts --
    ignores it, `chmod` returns EPERM there, and `os.replace` carries the
    permissive mode onto the target. §3 decision 1 names the scenario as its
    own justification: the writer chooses where Pressless sits, which may be
    a shared or removable drive. §4.6's measurement was taken on ext4.

    The mode is read off the DESCRIPTOR `mkstemp` returned, before the secret
    is written into it, so the secret never reaches a filesystem that cannot
    keep it. `fstat` is the one call that reports what the mount actually
    granted, which is why faking it is how this fixture stands in for such a
    mount.

    Breaks when an implementer trusts the mode `mkstemp` asked for. INV-5
    cannot catch it: that test reads the mode back on ext4, where the request
    is honoured.
    """
    _not_windows(monkeypatch)
    real_fstat = os.fstat

    def permissive(fd):
        result = real_fstat(fd)
        return os.stat_result((result.st_mode | 0o066,) + tuple(result)[1:])

    monkeypatch.setattr(credentials_module.os, "fstat", permissive)
    try:
        with pytest.raises(NoStore):
            write("file", tmp_path, "publishing-key", SENTINEL)
    finally:
        monkeypatch.undo()

    left = sorted(path.name for path in tmp_path.iterdir())
    assert left == [], (
        f"a refused write left {left!r} behind; a folder that cannot hold a "
        f"private file must end the call holding nothing"
    )
