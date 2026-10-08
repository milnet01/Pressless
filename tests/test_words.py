"""The words table (PRESS-0242, docs/specs/PRESS-0242-screen-words.md)."""

from __future__ import annotations

import json
import threading

import pytest

from pressless import _flag_data, marks, words


@pytest.fixture
def entry(monkeypatch):
    """Adds entries to ENGLISH for one test."""
    def add(key: str, text: str) -> None:
        monkeypatch.setitem(words.ENGLISH, key, text)
    return add


def test_say_fills_gaps_and_keeps_a_doubled_brace(entry) -> None:
    entry("test.hello", "Hello {name}, {{not a gap}}.")
    assert words.say("test.hello", name="you") == "Hello you, {not a gap}."


def test_a_missing_key_or_gap_raises(entry) -> None:
    """§ 6. Breaks when say() answers an unknown key or an unfilled gap with
    something a page would show."""
    entry("test.hello", "Hello {name}.")
    with pytest.raises(KeyError):
        words.say("test.no-such-key")
    with pytest.raises(KeyError):
        words.say("test.hello")


def test_a_table_in_use_comes_first_and_falls_back_to_english(entry) -> None:
    """§ 4.1. Breaks when use() hides English for keys its table lacks, or
    outlives its block."""
    entry("test.one", "One")
    entry("test.two", "Two")
    with words.use({"test.one": "Un"}):
        assert words.say("test.one") == "Un"
        assert words.say("test.two") == "Two"
    assert words.say("test.one") == "One"


def test_the_table_in_use_reaches_every_thread(entry) -> None:
    """§ 4.1: process-wide, so pages built on the server's threads follow it.
    Breaks when use() is made thread-local."""
    entry("test.one", "One")
    seen: list[str] = []
    with words.use({"test.one": "Un"}):
        reader = threading.Thread(target=lambda: seen.append(words.say("test.one")))
        reader.start()
        reader.join()
    assert seen == ["Un"]


def test_scripts_get_every_script_entry_and_nothing_else(entry) -> None:
    """§ 4.3. Breaks when a script entry is left out, a server-only entry is
    sent, or the JSON can close the <script> it sits in."""
    entry("script.test.saved", "Saved </script> {count}")
    entry("test.server", "Server only")
    sent = words.for_scripts()
    assert "</" not in sent
    shipped = json.loads(sent)
    assert shipped["script.test.saved"] == "Saved </script> {count}"
    assert "test.server" not in shipped
    assert all(key.startswith("script.") for key in shipped)
    with words.use({"script.test.saved": "Enregistré"}):
        assert json.loads(words.for_scripts())["script.test.saved"] == "Enregistré"


def test_the_two_families_come_from_their_sources() -> None:
    """§ 4.1. Breaks when a country or a cheat-sheet row has no entry."""
    for code, name in _flag_data.NAMES.items():
        assert words.say(f"country.{code}") == name
    for row in marks.MARKS:
        assert words.say(f"mark.{row.name}") == row.explains
        assert words.say(f"mark.{row.name}.example") == row.example
