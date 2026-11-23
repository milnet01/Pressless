"""A small JSON file Pressless keeps for itself, marked with its version
(PRESS-0398). theme.json, choices.json, backups.json, sites.json,
updates.json and the starter's record are read and written through it."""
from __future__ import annotations

import ast
import inspect
import json

import pytest

from pressless import json_record


def test_a_written_file_reads_back_with_its_version(tmp_path):
    """Breaks when write and read disagree on the shape."""
    target = tmp_path / "record.json"
    json_record.write(target, {"open": "site-2", "made": 2})
    assert json_record.read(target) == {"open": "site-2", "made": 2, "version": 1}


def test_the_version_is_written_last(tmp_path):
    """A field named `version` never replaces the file's own, so a merged
    write cannot mark a file with another version.

    Breaks when the version is put first, where a field overrides it."""
    target = tmp_path / "record.json"
    json_record.write(target, {"theme": "dark", "version": 9})
    held = json.loads(target.read_text(encoding="utf-8"))
    assert held == {"theme": "dark", "version": 1}
    assert list(held)[-1] == "version"


@pytest.mark.parametrize("text", ["", "not json", "[1, 2]", '"version"',
                                  '{"theme": "dark"}', '{"version": 2, "theme": "dark"}',
                                  '{"version": "1", "theme": "dark"}'])
def test_anything_this_pressless_did_not_write_reads_as_nothing(tmp_path, text):
    """A missing version, another one -- a newer Pressless's included, since
    downgrades are not supported -- and a file that is not a JSON object all
    read as no fields, never as a guess at them.

    Breaks when a file of another version or shape is read as this one."""
    target = tmp_path / "record.json"
    target.write_text(text, encoding="utf-8")
    assert json_record.read(target) == {}
    assert json_record.read(target, strict=True) == {}


def test_a_missing_file_reads_as_nothing(tmp_path):
    """Breaks when a first run, which has no file yet, raises."""
    assert json_record.read(tmp_path / "record.json") == {}
    assert json_record.read(tmp_path / "record.json", strict=True) == {}


def test_a_file_there_but_unreadable_raises_only_when_strict(tmp_path):
    """A file that is there but cannot be read now reads as nothing, except
    with `strict`, where its OSError is raised, so a merging write never
    replaces what it holds with only the new fields.

    Breaks when strict swallows the error, or the plain read raises it."""
    target = tmp_path / "record.json"
    target.mkdir()   # read_text on a folder fails, on every system
    assert json_record.read(target) == {}
    with pytest.raises(OSError):
        json_record.read(target, strict=True)


def test_a_write_that_fails_raises_and_leaves_nothing(tmp_path):
    """The caller decides what a failed write costs, so it gets the OSError.

    Breaks when write swallows the failure."""
    with pytest.raises(OSError):
        json_record.write(tmp_path / "no-such-folder" / "record.json", {"theme": "dark"})
    assert list(tmp_path.iterdir()) == []


def test_it_imports_only_safe_write():
    """A module whose import rule admits safe_write may use it and reach
    nothing else through it (PRESS-0223 § 4.1, PRESS-0023 § 4.1).

    Breaks when it imports another part of Pressless, by a relative import
    too, whose module reads as None or a bare name."""
    imported = [node for node in ast.walk(ast.parse(inspect.getsource(json_record)))
                if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not [node.module for node in imported
                if isinstance(node, ast.ImportFrom) and node.level], "a relative import"
    ours = {node.module for node in imported
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pressless")}
    ours |= {alias.name for node in imported if isinstance(node, ast.Import)
             for alias in node.names if alias.name.startswith("pressless")}
    assert ours == {"pressless.safe_write"}
