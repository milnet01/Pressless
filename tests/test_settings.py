# INV-1..7 for PRESS-0001 (Settings). One test per invariant, named in that
# spec's §5 and §10. Unlabelled and needs nothing but a temporary directory
# (spec §7), unlike the archive test PRESS-0004 carries.
#
# Why this exists: docs/specs/PRESS-0001-settings.md is the contract.
from __future__ import annotations

import ast
import builtins
import dataclasses
import inspect
import io
import json
import os
from pathlib import Path

import pytest
from _durability_watch import _assert_synced_before_replace, _watch_durability
from _open_watch import _watch_opens

import pressless.settings as settings_module
from pressless.settings import (
    Credentials,
    NotSetUp,
    Settings,
    SettingsError,
    load,
    path_for,
    save,
)

# The documented file name (§4.1, §4.2). Written out here rather than taken
# from path_for(), because several fixtures below must exist before anything
# in the module under test is called.
FILE_NAME = "settings.json"


def _valid_mapping(**overrides) -> dict:
    """§4.2's file, complete and valid. Overrides replace a key; a value of
    _ABSENT removes it, which is how INV-3's pair differs by one key only."""
    mapping = {
        "version": 1,
        "site_folder": "/home/writer/Pressless/site",
        "repository": "owner/owner.github.io",
        "daily_prompt_filter": "dailyprompt-*",
        "untouchable": ["CNAME", ".nojekyll", "README.md"],
        "credentials": {
            "store": "keyring",
            "github_account": "publishing-key",
            "google_account": "analytics",
        },
        "analytics_property_id": "123456789",
    }
    mapping.update(overrides)
    return {k: v for k, v in mapping.items() if v is not _ABSENT}


class _Absent:
    def __repr__(self):
        return "_ABSENT"


_ABSENT = _Absent()


def _write(folder: Path, mapping) -> Path:
    """Put a settings file in `folder`. A str is written byte for byte, so a
    fixture can be invalid JSON."""
    target = folder / FILE_NAME
    target.write_text(mapping if isinstance(mapping, str) else json.dumps(mapping))
    return target


# --------------------------------------------------------------- INV-1 ----

# Network modules, and nothing else. `os` is NOT here: §4.4 requires it, and
# INV-1 says so — it is INV-7 that holds the path rule. That is the one
# difference from test_marks_is_pure, which bans `os` outright.
_FORBIDDEN_TOP_LEVEL_IMPORTS = {
    "socket", "ssl", "urllib", "http", "requests", "httpx",
    "ftplib", "smtplib", "poplib", "imaplib", "xmlrpc", "webbrowser",
}


def test_settings_imports_nothing_forbidden():
    """INV-1: settings.py imports no network module and no other pressless
    module.

    Walks the module's AST, as test_marks_is_pure does. Reads the module's
    source from the test, never from settings.py itself.

    Breaks when an implementer imports pressless.publisher to validate the
    repository name, or urllib to check it exists.

    This test is weak in a way the spec names (§7): an import list proves what
    the module imports, never that loading or saving does anything. It passes
    against the stub by design."""
    tree = ast.parse(inspect.getsource(settings_module))

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

    forbidden = imported_top_level & (_FORBIDDEN_TOP_LEVEL_IMPORTS | {"pressless"})
    assert not forbidden, (
        f"settings.py imports {forbidden!r} — a network module, or another "
        f"pressless module. Its row in docs/design.md § The parts is "
        f"'depends on nothing'"
    )
    assert not relative_imports, (
        f"settings.py has relative import(s) {[n.module for n in relative_imports]!r}, "
        f"which can only name a sibling pressless module"
    )


# --------------------------------------------------------------- INV-2 ----


def test_absent_and_unreadable_differ(tmp_path):
    """INV-2: no settings file raises NotSetUp; a file that is present but
    unreadable raises SettingsError. Neither is the other.

    Breaks when an implementer catches both as "no usable settings" and sends
    the writer to setup, which then overwrites the file he could have fixed."""
    # The two exceptions must also be unrelated by inheritance. If NotSetUp
    # were a subclass of SettingsError, both pytest.raises below would still
    # pass while a caller's `except SettingsError` swallowed the absent case —
    # the very confusion this invariant forbids, arriving by another route.
    assert not issubclass(NotSetUp, SettingsError), (
        "NotSetUp is a subclass of SettingsError, so `except SettingsError` "
        "catches both and the two outcomes are not distinguishable"
    )
    assert not issubclass(SettingsError, NotSetUp), (
        "SettingsError is a subclass of NotSetUp, so `except NotSetUp` "
        "catches both and the two outcomes are not distinguishable"
    )

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(NotSetUp):
        load(empty)

    broken = tmp_path / "broken"
    broken.mkdir()
    _write(broken, "{")
    with pytest.raises(SettingsError):
        load(broken)


# --------------------------------------------------------------- INV-3 ----


def test_untouchable_absent_is_an_error(tmp_path):
    """INV-3: an absent `untouchable` key is a SettingsError; a key present
    and empty loads.

    The two files differ only in whether the key is present, so no other rule
    rejects either one. Breaks when an implementer gives the field a default
    of (), which is what lets a half-finished setup delete the CNAME and
    detach the domain (spec §3 decision 4)."""
    without = tmp_path / "without"
    without.mkdir()
    _write(without, _valid_mapping(untouchable=_ABSENT))
    with pytest.raises(SettingsError):
        load(without)

    empty_list = tmp_path / "empty_list"
    empty_list.mkdir()
    _write(empty_list, _valid_mapping(untouchable=[]))
    loaded = load(empty_list)
    assert loaded.untouchable == (), (
        f"an untouchable key present and empty must load as an empty "
        f"collection, got {loaded.untouchable!r}"
    )


# --------------------------------------------------------------- INV-4 ----


def test_relative_site_folder_is_rejected(tmp_path):
    """§4.3's shape row. A relative site_folder is present and correctly
    typed, so only a shape check catches it. Left accepted, the Builder
    resolves it against whatever directory the process happens to be in --
    different for the Face's server and a command-line run -- and the
    finished site lands in two places."""
    _write(tmp_path, _valid_mapping(site_folder="site"))
    with pytest.raises(SettingsError) as raised:
        load(tmp_path)
    assert "site_folder" in str(raised.value), (
        f"the error must name the key that is wrong, got {raised.value!r}"
    )


def test_unknown_keys_survive_a_save(tmp_path):
    """INV-4: a key load() does not recognise is present, unchanged, in the
    file after a save() of the loaded value.

    Breaks when save() is written from the dataclass alone rather than over
    the file's existing contents (spec §4.4). A newer Pressless must be able
    to write a key an older one then saves over."""
    stranger = {"written_by_a_later_pressless": {"nested": ["value", 1, None]}}
    target = _write(tmp_path, _valid_mapping(**stranger))

    save(tmp_path, load(tmp_path))

    after = json.loads(target.read_text())
    assert "written_by_a_later_pressless" in after, (
        f"save() dropped a key it did not recognise; the file now holds "
        f"{sorted(after)!r}"
    )
    assert after["written_by_a_later_pressless"] == stranger["written_by_a_later_pressless"], (
        f"save() altered an unrecognised key's value: "
        f"{after['written_by_a_later_pressless']!r}"
    )


# --------------------------------------------------------------- INV-5 ----


def test_save_is_atomic(tmp_path, monkeypatch):
    """INV-5: save() never leaves a file that load() rejects. After a save
    interrupted before completion, the file on disk is the previous one.

    Two halves, and the spec requires both. Asserting the MECHANISM is what
    makes the fixture bite: against a direct write into the target there is no
    replace to interrupt, so the interruption half alone would pass green
    against the implementation it exists to reject.

    path_for's own value is pinned here too. Comparing the replace destination
    to path_for(folder) alone passes when both are wrong together, and the
    file name is what setup and every later Pressless bind to (§4.2)."""
    assert path_for(tmp_path) == tmp_path / FILE_NAME, (
        f"path_for must name {FILE_NAME!r} inside the folder it is handed, "
        f"got {path_for(tmp_path)!r}"
    )

    previous = _valid_mapping()
    _write(tmp_path, previous)
    before = load(tmp_path)

    calls = []
    real_replace = os.replace

    def interrupted_replace(src, dst, *args, **kwargs):
        calls.append((os.fspath(src), os.fspath(dst)))
        raise OSError("interrupted before the replace completed")

    monkeypatch.setattr(os, "replace", interrupted_replace)

    changed = dataclasses.replace(before, repository="someone/else.github.io")
    # Not `Exception`: save wraps the OSError, so a blind assertion here
    # passed against any failure at all, including the wrong one.
    with pytest.raises(SettingsError):
        save(tmp_path, changed)

    monkeypatch.setattr(os, "replace", real_replace)

    assert calls, (
        "save() never reached os.replace — it wrote into the target directly, "
        "so there is no point at which an interruption leaves the old file"
    )
    destinations = {dst for _, dst in calls}
    assert destinations == {os.fspath(path_for(tmp_path))}, (
        f"save() replaced {destinations!r}; §4.4 requires the target to be "
        f"path_for(folder) = {path_for(tmp_path)!r}"
    )

    assert load(tmp_path) == before, (
        "after a save interrupted at the replace, load() no longer returns "
        "the previous settings — the old file was not left intact"
    )


# --------------------------------------------------------------- INV-6 ----


_SETTINGS_FIELDS = {
    "site_folder",
    "repository",
    "daily_prompt_filter",
    "untouchable",
    "credentials",
    "analytics_property_id",
}
_CREDENTIALS_FIELDS = {"store", "github_account", "google_account"}


def test_field_names_are_the_documented_set():
    """INV-6: the field names of Settings and Credentials are exactly the set
    §4.1 lists.

    Stated as the whole set rather than as "no secret field": that form passes
    against every settings value that happens not to have one, so only a rule
    about the set itself fails when a field is added. Breaks when someone adds
    github_token "just for the fallback path", or renames a key six other
    parts read.

    `version` is absent on purpose — §4.2 makes it the file's, written from
    the schema and never from a dataclass field.

    This test passes against the stub by design (spec §7)."""
    assert {f.name for f in dataclasses.fields(Settings)} == _SETTINGS_FIELDS, (
        f"Settings' fields are {sorted(f.name for f in dataclasses.fields(Settings))!r}, "
        f"not §4.1's set {sorted(_SETTINGS_FIELDS)!r}"
    )
    assert {f.name for f in dataclasses.fields(Credentials)} == _CREDENTIALS_FIELDS, (
        f"Credentials' fields are "
        f"{sorted(f.name for f in dataclasses.fields(Credentials))!r}, "
        f"not §4.1's set {sorted(_CREDENTIALS_FIELDS)!r}"
    )


# --------------------------------------------------------------- INV-7 ----


def test_only_touches_its_own_file(tmp_path, monkeypatch):
    """INV-7: load() and save() open no path outside `folder`, and leave
    nothing inside it but path_for(folder). §4.4's temporary file is the one
    permitted extra path and is gone once save() returns.

    Breaks when a search for a settings file in a parent or the home directory
    is added, which is scope decision 2 undone. Listing the folder cannot
    catch that — a read elsewhere leaves the listing identical — which is why
    every path opened is recorded, not just what the folder ends up holding."""
    _write(tmp_path, _valid_mapping())
    folder = Path(os.path.realpath(tmp_path))
    opened: list[str] = []

    def _record(path):
        try:
            opened.append(os.path.realpath(os.fspath(path)))
        except TypeError:
            pass  # an already-open file descriptor names no path

    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def watched_open(file, *args, **kwargs):
        _record(file)
        return real_open(file, *args, **kwargs)

    def watched_io_open(file, *args, **kwargs):
        _record(file)
        return real_io_open(file, *args, **kwargs)

    def watched_os_open(path, *args, **kwargs):
        _record(path)
        return real_os_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watched_open)
    monkeypatch.setattr(io, "open", watched_io_open)
    monkeypatch.setattr(os, "open", watched_os_open)
    try:
        loaded = load(tmp_path)
        save(tmp_path, loaded)
    finally:
        monkeypatch.undo()

    strays = [p for p in opened if os.path.dirname(p) != os.fspath(folder)]
    assert not strays, (
        f"load()/save() opened {strays!r}, which is outside the folder they "
        f"were handed ({folder!r}). Settings is handed its folder and never "
        f"searches for another (spec §3 decision 2)"
    )
    assert opened, "no filesystem call was recorded at all — the watch did not fire"

    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == [FILE_NAME], (
        f"after save() returned the folder holds {left!r}; §4.4's temporary "
        f"file must be gone and nothing else may be left behind"
    )

    # The breach this invariant names arrives by a route the phase above
    # cannot reach: a fallback that searches upwards only runs when the
    # folder it was handed has no file. Measured by mutation 2026-08-25 —
    # add that fallback and every assertion above stays green. So the
    # second phase hands load() an EMPTY folder whose parent does hold a
    # settings file, which is the shape a parent search would satisfy.
    child = tmp_path / "pressless"
    child.mkdir()
    opened.clear()
    monkeypatch.setattr(builtins, "open", watched_open)
    monkeypatch.setattr(io, "open", watched_io_open)
    monkeypatch.setattr(os, "open", watched_os_open)
    try:
        with pytest.raises(NotSetUp):
            load(child)
    finally:
        monkeypatch.undo()

    outside = [p for p in opened if os.path.dirname(p) != os.path.realpath(child)]
    assert not outside, (
        f"load() on a folder with no settings file opened {outside!r} — it "
        f"searched outside the folder it was handed (spec §3 decision 2)"
    )


# --------------------------------------------- PRESS-0044 (§4.3's shape) ----


def test_a_nested_untouchable_entry_is_rejected(tmp_path):
    """§4.3's shape rule, applied to the untouchable list.

    PRESS-0009 §4.4 matches an entry against a path's FIRST segment, so an
    entry naming a path inside a directory protects nothing -- not even
    itself -- while being a str that passes every type check. Nothing at any
    layer said so, and a guard that reads as configured and is inert is the
    one failure this list cannot afford (PRESS-0044).

    An empty entry is refused for the same reason. A trailing slash is not:
    it names one root entry unambiguously, and the Publisher ignores it, so
    refusing the file over it would stop a working installation loading.

    Breaks when an implementer checks isinstance and stops.
    """
    for index, entry in enumerate(("docs/robots.txt", "a/b/c", "")):
        folder = tmp_path / f"rejected-{index}"
        folder.mkdir()
        _write(folder, _valid_mapping(untouchable=[entry]))
        with pytest.raises(SettingsError):
            load(folder)

    accepted = tmp_path / "accepted"
    accepted.mkdir()
    _write(accepted, _valid_mapping(untouchable=["CNAME/"]))
    assert load(accepted).untouchable == ("CNAME/",), (
        "a trailing slash names one root entry unambiguously and must load; "
        "the Publisher is what ignores it"
    )


# ------------------------------------------------------------ PRESS-0039 ----


def test_save_reaches_the_disk_before_the_rename(tmp_path, monkeypatch):
    """§4.4's "never a truncated one" must hold against a power loss, not only
    against an exception.

    Asserting the ORDER is the whole test: the file left on disk is identical
    whether or not the temporary was synced, so nothing read back can tell a
    durable write from one whose blocks are still in the kernel's cache.

    Breaks when save() renames an unsynced temporary, which leaves an empty
    settings file where §4.4 promises the previous one.
    """
    _write(tmp_path, _valid_mapping())
    before = load(tmp_path)

    events = _watch_durability(monkeypatch)
    try:
        save(tmp_path, dataclasses.replace(before, repository="someone/else.github.io"))
    finally:
        monkeypatch.undo()

    _assert_synced_before_replace(events, "save()")


def test_save_names_the_line_endings(tmp_path, monkeypatch):
    """§4.2's file is a shape the installation carries between machines, so its
    bytes may not depend on which machine wrote it.

    Asserting what save() NAMED rather than the bytes it produced: os.linesep
    is "\\n" on the machine running this suite, so a write that left the
    newline to the platform produces the same bytes here as one that named it,
    and a byte-level assertion passes against the defect it exists to catch.

    Breaks when save() opens its temporary without newline="\\n", which writes
    CRLF on Windows.
    """
    _write(tmp_path, _valid_mapping())
    before = load(tmp_path)

    opens = _watch_opens(monkeypatch)
    try:
        save(tmp_path, before)
    finally:
        monkeypatch.undo()

    writing = [record for record in opens if record.writes() and not record.binary]
    assert writing, "no text write was recorded at all -- the watch did not fire"
    unnamed = [record for record in writing if record.newline != "\n"]
    assert not unnamed, (
        f"save() opened a text file naming newline "
        f"{[record.newline for record in unnamed]!r}; §4.2 requires '\\n' so "
        f"the file is byte-identical on both systems"
    )


# ------------------------------------------------------------ PRESS-0049 ----


def test_an_undecodable_settings_file_is_a_typed_failure(tmp_path):
    """PRESS-0049: a byte that is not UTF-8 raises UnicodeDecodeError, which
    is a ValueError and NOT an OSError -- so it escaped both arms of load()
    and reached the caller as neither NotSetUp nor SettingsError.

    §4.3 has the row: a file present but not decodable as UTF-8 is a
    SettingsError naming the file. It was not implemented. The guard EXISTED
    but sat around json.loads, which is handed a str and can never raise it.

    The module's own docstring names the scenario: a cp1252 write on Windows
    of an accented site_folder, written there and unreadable here.

    Breaks when an implementer catches OSError and assumes a read covers
    every way a read can fail. Nothing looks wrong -- the guard is right
    there, one block down.
    """
    target = tmp_path / FILE_NAME
    target.write_bytes(b'{"version": 1, "site_folder": "caf\xe9"}')

    with pytest.raises(SettingsError):
        load(tmp_path)


def test_saving_over_an_undecodable_file_is_a_typed_failure(tmp_path):
    """PRESS-0049: save() reads the existing file first, to carry through
    keys it does not recognise, and had the same hole.

    Breaks the same way, and matters more: this one is reached while the
    writer is trying to save.
    """
    target = tmp_path / FILE_NAME
    target.write_bytes(b'{"version": 1, "site_folder": "caf\xe9"}')

    settings = Settings(
        site_folder=tmp_path / "site",
        repository="owner/name",
        daily_prompt_filter="dailyprompt-*",
        untouchable=("CNAME",),
        credentials=Credentials(store="keyring",
                                github_account="publishing-key",
                                google_account=None),
        analytics_property_id=None,
    )

    with pytest.raises(SettingsError):
        save(tmp_path, settings)
