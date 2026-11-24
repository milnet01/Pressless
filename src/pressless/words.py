"""Every word Pressless shows, looked up in one table (PRESS-0242).

English is `ENGLISH` (in `english_words`); every other language is a JSON file in
`language_files`, whose entries count only while the English they were
made from is unchanged (PRESS-0241 § 4.1). Each word is looked up when it
is shown, so the table `choose` puts in front of English changes every
screen from the next request on. A key is a dotted name grouped by
screen, never the English words, so rewording English changes no key.

The table itself, `ENGLISH`, lives in `english_words` and is re-exported
here, so `words.ENGLISH` stays the one name readers use. This module reads
only its own language files, touches no network, and imports only the
standard library and that table.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import importlib.resources
import json
from collections.abc import Callable, Iterator
from pathlib import Path

from pressless.english_words import ENGLISH  # the table; `words.ENGLISH` stays its public name

# The language chosen and its table in front of ENGLISH, for every thread
# holding none of its own (spec § 4.1). One tuple, replaced whole, so no
# thread sees one language's words with another's plural forms or
# thousands mark.
_current: tuple[str, dict[str, str]] = ("en", {})
# The one a request's thread holds while it is answered (PRESS-0469), so a
# language chosen meanwhile waits for the next request.
_held: contextvars.ContextVar[tuple[str, dict[str, str]] | None] = (
    contextvars.ContextVar("pressless_words_held", default=None))


def _in_force() -> tuple[str, dict[str, str]]:
    return _held.get() or _current


@contextlib.contextmanager
def held() -> Iterator[None]:
    """Keep the language in use now for this thread while the block runs,
    whatever is chosen meanwhile. The Face holds one for each request."""
    token = _held.set(_in_force())
    try:
        yield
    finally:
        _held.reset(token)


def carried[T](work: Callable[..., T]) -> Callable[..., T]:
    """`work`, speaking on whichever thread runs it the language in use
    where carried() is called: for work a request hands to another thread."""
    language = _in_force()

    def run(*args: object, **kwargs: object) -> T:
        token = _held.set(language)
        try:
            return work(*args, **kwargs)
        finally:
            _held.reset(token)
    return run


def _lookup(key: str, held: dict[str, str] | None = None) -> str:
    found = (_in_force()[1] if held is None else held).get(key)
    return found if found is not None else ENGLISH[key]


def say(key: str, **slots: str) -> str:
    """The words for `key` in the table in use, gaps filled.

    A key the table in use lacks takes ENGLISH's words. A key ENGLISH lacks,
    or a gap left unfilled, raises KeyError. Slot values go in as given:
    each caller escapes what it passes.
    """
    return _lookup(key).format_map(slots)


def say_count(amount: int, one: str, many: str, *, code: str | None = None,
              **slots: str) -> str:
    """`say` for `amount` of something: key `one` where `code`'s language
    (default: the one in use) takes its one form for `amount`, `many`
    otherwise. The `count` gap is `number(amount, code)` unless the caller
    passes its own.

    A one form writes `{count}`, never "1": a language's one form may cover
    other amounts, as French's covers 0 (PRESS-0241 INV-8)."""
    language, held = _in_force() if code is None else (code, table(code))
    slots.setdefault("count", number(amount, language))
    key = one if amount in _ones(language) else many
    return _lookup(key, held).format_map(slots)


@contextlib.contextmanager
def use(table: dict[str, str]) -> Iterator[None]:
    """Put `table` in front of ENGLISH while the block runs, for every thread
    holding no language of its own. A table names no language, so the one
    in use keeps its plural forms and thousands mark."""
    global _current
    before = _current
    _current = (before[0], dict(table))
    try:
        yield
    finally:
        _current = before


def for_scripts() -> str:
    """Every `script.` entry, gaps unfilled, as a JSON object safe inside
    <script>. The page's own `say` fills the gaps.

    Every `<` is written as its JSON escape, so no entry can close the block
    (`</script>`) or open a comment that hides its close (`<!--<script`)."""
    held = _in_force()[1]
    chosen = {key: _lookup(key, held) for key in ENGLISH if key.startswith("script.")}
    return json.dumps(chosen).replace("<", "\\u003c")


# ------------------------------------------------- languages (PRESS-0241) --

# Read through importlib.resources so a frozen bundle finds it as the source
# tree does (as manual.FOLDER is).
FOLDER = Path(str(importlib.resources.files("pressless") / "language_files"))
# The order the pickers show; each language § 4.6 adds puts its code here.
LANGUAGES: tuple[str, ...] = ("en", "es", "af", "fr", "de")

# Keyed by folder as well as code because tests point FOLDER elsewhere.
_files: dict[tuple[Path, str], dict] = {}     # a file as read, by folder and code
_tables: dict[tuple[Path, str], dict[str, str]] = {}
_unreadable: set[str] = set()


def made_from(english: str) -> str:
    """What a translation records of the English it was made from (§ 4.1)."""
    return hashlib.sha256(english.encode("utf-8")).hexdigest()[:8]


def _file(code: str) -> dict:
    """The language's file as an object; {} for English, a code with no
    file, or a file that will not load, which unreadable() then names."""
    if code == "en":
        return {}
    place = (FOLDER, code)
    found = _files.get(place)
    if found is None:
        try:
            found = json.loads((FOLDER / f"{code}.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            found = {}
        except (OSError, ValueError):
            found = None
        if not isinstance(found, dict):
            _unreadable.add(code)
            found = {}
        _files[place] = found
    return found


def unreadable() -> list[str]:
    """The codes whose file was there but would not load (§ 6), for a log line."""
    return sorted(_unreadable)


def table(code: str) -> dict[str, str]:
    """The language's entries whose made-from matches today's English. "en",
    or a code with no file, gives {}."""
    place = (FOLDER, code)
    found = _tables.get(place)
    if found is None:
        held = _file(code).get("words")
        found = {}
        if isinstance(held, dict):
            for key, pair in held.items():
                english = ENGLISH.get(key)
                if (english is not None and isinstance(pair, list) and len(pair) == 2
                        and all(isinstance(part, str) for part in pair)
                        and pair[0] == made_from(english)):
                    found[key] = pair[1]
        _tables[place] = found
    return found


def name(code: str) -> str:
    """The language in its own words, for the pickers; the code itself where
    its file gives none."""
    if code == "en":
        return "English"
    given = _file(code).get("name")
    return given if isinstance(given, str) and given else code


def choose(code: str) -> None:
    """Put `code`'s table in front of ENGLISH from now on, and make `code`
    the language in use, for every thread but one holding its own: a request
    under way keeps the one it started with (PRESS-0469)."""
    global _current
    _current = (code, dict(table(code)))


def in_use() -> str:
    """The code in use on this thread; "en" before any is chosen."""
    return _in_force()[0]


def say_in(code: str, key: str, **slots: str) -> str:
    """`say` with `code`'s table in front of ENGLISH, whatever is in use."""
    return _lookup(key, table(code)).format_map(slots)


def _ones(code: str) -> frozenset[int]:
    """The amounts that take a key's one form in `code`'s language."""
    given = _file(code).get("one")
    if isinstance(given, list) and given and all(type(item) is int for item in given):
        return frozenset(given)
    return frozenset({1})


def number(value: int, code: str | None = None) -> str:
    """`value` with its thousands marked as `code` (default: the language in
    use) marks them."""
    given = _file(_in_force()[0] if code is None else code).get("thousands")
    mark = given if isinstance(given, str) else ","
    return f"{value:,}".replace(",", mark)


def decimal(value: float, places: int, code: str | None = None) -> str:
    """`value` to `places` decimals, marked as `code` (default: the language
    in use) marks a decimal: a comma wherever it marks thousands otherwise."""
    mark = "." if number(1000, code) == "1,000" else ","
    return f"{value:.{places}f}".replace(".", mark)


# A date is anything with day, month and year, and weekday() for a weekday.
def _sayer(code: str | None) -> Callable[..., str]:
    return say if code is None else (lambda key, **slots: say_in(code, key, **slots))


def long_date(when, code: str | None = None) -> str:
    """`5 March 2026`."""
    said = _sayer(code)
    return said("date.long", day=str(when.day), month=said(f"date.month.{when.month}"),
                year=str(when.year))


def medium_date(when, code: str | None = None) -> str:
    """`05 Mar 2026`: the day in two digits, as the screens' lists have
    always written it, so a column of dates lines up."""
    said = _sayer(code)
    return said("date.medium", day=f"{when.day:02d}", mon=said(f"date.mon.{when.month}"),
                year=str(when.year))


def short_date(when, code: str | None = None) -> str:
    """`5 Mar`."""
    said = _sayer(code)
    return said("date.short", day=str(when.day), mon=said(f"date.mon.{when.month}"))


def month_year(when, code: str | None = None) -> str:
    """`March 2026`."""
    said = _sayer(code)
    return said("date.month_year", month=said(f"date.month.{when.month}"),
                year=str(when.year))


def mon_year(when, code: str | None = None) -> str:
    """`Mar 2026`."""
    said = _sayer(code)
    return said("date.mon_year", mon=said(f"date.mon.{when.month}"), year=str(when.year))


def weekday(when, code: str | None = None) -> str:
    """`Thu 5 Mar`."""
    said = _sayer(code)
    return said("date.weekday", weekday=said(f"date.day.{when.weekday()}"),
                day=str(when.day), mon=said(f"date.mon.{when.month}"))
