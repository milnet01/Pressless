"""Every word Pressless shows, in one table (PRESS-0242).

English is the only table. Each word is looked up when it is shown, so a
second table put in front of it with `use` changes every screen at once --
the hook PRESS-0241's language choice takes. A key is a dotted name grouped
by screen, never the English words, so rewording English changes no key.

A word a page script reads lives under `script.`, once, and Python reads
that same key where it shows the word too. An entry holds words and the
markup its sentence needs, never a page's template, and names its gaps as
`{slot}`; a literal brace is written `{{`.

Two families come from their own sources: `country.<code>` from
`_flag_data.NAMES`, which scripts/make_flags.py goes on generating, and
`mark.<name>` and `mark.<name>.example` from `marks.MARKS`, whose `example`
stays the parse fixture. This module touches no disk and no network, and
imports only the standard library and those two modules.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator

from pressless import _flag_data, marks

_WORDS: dict[str, str] = {
}

def _literal(text: str) -> str:
    """`text` as an entry with no gaps: a mark's own syntax uses braces."""
    return text.replace("{", "{{").replace("}", "}}")


ENGLISH: dict[str, str] = {
    **_WORDS,
    **{f"country.{code}": _literal(name) for code, name in _flag_data.NAMES.items()},
    **{f"mark.{row.name}": _literal(row.explains) for row in marks.MARKS},
    **{f"mark.{row.name}.example": _literal(row.example) for row in marks.MARKS},
}

# The table in front of ENGLISH, for the whole process: every server thread
# reads the same one (spec § 4.1).
_in_use: dict[str, str] = {}


def _words(key: str) -> str:
    found = _in_use.get(key)
    return found if found is not None else ENGLISH[key]


def say(key: str, **slots: str) -> str:
    """The words for `key` in the table in use, gaps filled.

    A key the table in use lacks takes ENGLISH's words. A key ENGLISH lacks,
    or a gap left unfilled, raises KeyError. Slot values go in as given:
    each caller escapes what it passes.
    """
    return _words(key).format_map(slots)


@contextlib.contextmanager
def use(table: dict[str, str]) -> Iterator[None]:
    """Put `table` in front of ENGLISH for the whole process while the block
    runs."""
    global _in_use
    before = _in_use
    _in_use = dict(table)
    try:
        yield
    finally:
        _in_use = before


def for_scripts() -> str:
    """Every `script.` entry, gaps unfilled, as a JSON object safe inside
    <script>. The page's own `say` fills the gaps."""
    chosen = {key: _words(key) for key in ENGLISH if key.startswith("script.")}
    return json.dumps(chosen).replace("</", "<\\/")
