"""The scripts that write a module the program imports (PRESS-0342, PRESS-0242).

Each is loaded by path and writes into the test's own folder; the committed
modules are never touched. Text from outside -- the public suffix list,
the flag-icons package -- must not be able to break or add to the module.
"""
from __future__ import annotations

import importlib.util
import json

import pytest
from _scripts import load_script

_LIST = """// VERSION: 2026-11-04_19-07-29_UTC
// COMMIT: aae37acca5d0f3d09e7c1fe4da9024c514674ac9
// ===BEGIN ICANN DOMAINS===
com
co.za   words after the rule
// a comment
   // an indented comment
*.ck
!www.ck
{extra}
// ===END ICANN DOMAINS===
// ===BEGIN PRIVATE DOMAINS===
github.io
// ===END PRIVATE DOMAINS===
"""


def _imported(path):
    spec = importlib.util.spec_from_file_location("generated", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _suffixes(monkeypatch, tmp_path, text):
    script = load_script("public-suffixes.py")
    target = tmp_path / "_public_suffixes.py"
    monkeypatch.setattr(script, "TARGET", target)
    source = tmp_path / "list.dat"
    source.write_text(text, encoding="utf-8")
    script.main(source)
    return target


def test_a_rule_ends_at_its_first_space(monkeypatch, tmp_path):
    """review-code: the list's format reads a rule up to its first space, and
    the rest of the line became part of the rule."""
    target = _suffixes(monkeypatch, tmp_path, _LIST.format(extra=""))
    assert _imported(target).RULES == {"com", "co.za", "*.ck", "!www.ck"}


@pytest.mark.parametrize("text", [
    _LIST.format(extra='x", __import__("os").getcwd(), "'),
    _LIST.format(extra="back\\slash"),
    _LIST.replace("2026-11-04_19-07-29_UTC", 'v"""1'),
])
def test_text_that_could_change_the_module_is_refused(monkeypatch, tmp_path, text):
    """review-code: a rule or version holding a quote or backslash was pasted
    between quotes, where it could break the module or add code to it."""
    with pytest.raises(SystemExit):
        _suffixes(monkeypatch, tmp_path, text)
    assert not (tmp_path / "_public_suffixes.py").exists()


def _flags(monkeypatch, tmp_path, version="7.2.3", licence="MIT License\n"):
    script = load_script("make_flags.py")
    target = tmp_path / "_flag_data.py"
    monkeypatch.setattr(script, "TARGET", target)
    package = tmp_path / "flag-icons"
    (package / "flags" / "4x3").mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (package / "country.json").write_text(json.dumps([{"code": "za", "name": "South Africa"}]),
                                          encoding="utf-8")
    (package / "LICENSE").write_text(licence, encoding="utf-8")
    (package / "flags" / "4x3" / "za.svg").write_text("<svg/>", encoding="utf-8")
    return script.main([str(package)]), target


def test_the_flags_module_imports_back(monkeypatch, tmp_path):
    done, target = _flags(monkeypatch, tmp_path)
    assert done == 0
    assert _imported(target).NAMES == {"ZA": "South Africa"}


@pytest.mark.parametrize("version, licence", [
    ('7"""', "MIT License\n"), ("7.2.3", 'Say """ here\n'), ("7.2.3", "C:\\New\n")])
def test_package_text_that_could_change_the_flags_module_is_refused(
        monkeypatch, tmp_path, version, licence):
    """review-code: the version and the licence went into a docstring raw, so a
    quote or a backslash could break the module or add code to it."""
    done, target = _flags(monkeypatch, tmp_path, version, licence)
    assert done == 1
    assert not target.exists()


_WHOLE = _LIST.format(extra="")


@pytest.mark.parametrize("text", [
    "",
    _WHOLE.replace("// VERSION:", "// VERSIONS:"),
    _WHOLE.replace("// COMMIT:", "// COMMITS:"),
    _WHOLE.replace("// ===END ICANN DOMAINS===", ""),
    _WHOLE.replace("// ===BEGIN ICANN DOMAINS===", ""),
])
def test_a_list_cut_short_is_refused_in_words(monkeypatch, tmp_path, text):
    """review-code: a truncated or wrong download ended in an AttributeError
    or IndexError traceback rather than a refusal."""
    with pytest.raises(SystemExit, match="refused: the list"):
        _suffixes(monkeypatch, tmp_path, text)
    assert not (tmp_path / "_public_suffixes.py").exists()


class _Recorded:
    """A TARGET that keeps how it was written, as Windows would translate it."""

    def write_text(self, text, encoding=None, newline=None):
        self.newline = newline


def test_the_generated_modules_are_written_with_lf_on_any_system(monkeypatch, tmp_path):
    """review-code: written in text mode with no newline, they took CRLF on
    Windows, and git saw every line change."""
    target = _Recorded()
    script = load_script("public-suffixes.py")
    monkeypatch.setattr(script, "TARGET", target)
    source = tmp_path / "list.dat"
    source.write_text(_LIST.format(extra=""), encoding="utf-8")
    script.main(source)
    assert target.newline == "\n"
    target = _Recorded()
    flags = load_script("make_flags.py")
    _flags(monkeypatch, tmp_path)
    monkeypatch.setattr(flags, "TARGET", target)
    flags.main([str(tmp_path / "flag-icons")])
    assert target.newline == "\n"
