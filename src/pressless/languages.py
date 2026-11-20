"""The language the screens speak, and how it is chosen (PRESS-0241 § 4.3).

The computer's language, read at startup, unless the writer chose one from
the top bar. The choice is kept in language.json in Pressless's own folder,
as the theme is, so it holds across starts and across sites. Where the
computer's language cannot be told and nothing is chosen, every screen
offers the list until one is.
"""
from __future__ import annotations

import html
import locale
import os
import re
import sys
from pathlib import Path

from pressless import json_record, store, words
from pressless.words import say

FILE_NAME = "language.json"
FOLLOW = "follow"   # no language of its own: the computer's
ADDRESS = "/language"

_CODE = re.compile(r"[a-z]{2,3}")
# The variables glibc reads for a program's messages, first set wins.
_VARIABLES = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")
_UNTOLD = ("c", "posix")


def _code(value: str) -> str | None:
    """`value`'s language as a code: `es_MX.UTF-8` is `es`."""
    first = re.split(r"[_.@:-]", value.strip(), maxsplit=1)[0].lower()
    return first if _CODE.fullmatch(first) and first not in _UNTOLD else None


def _ui_language() -> int:
    """Windows' language id for the user's screens."""
    import ctypes
    return ctypes.WinDLL("kernel32").GetUserDefaultUILanguage()


def computer() -> str | None:
    """The computer's language as a code, or None where it cannot be told."""
    if sys.platform == "win32":
        named = locale.windows_locale.get(_ui_language())
        return None if named is None else _code(named)
    for variable in _VARIABLES:
        value = os.environ.get(variable, "")
        if value:
            # LANGUAGE is a list, best first: af:en.
            return _code(value.split(":", 1)[0])
    return None


def known(code: str) -> bool:
    """A choice the picker offers: FOLLOW or a language Pressless has."""
    return code == FOLLOW or code in words.LANGUAGES


def read_choice(folder: Path) -> str:
    """The chosen code. Missing, unparseable or unknown reads as FOLLOW."""
    code = json_record.read(Path(folder) / FILE_NAME).get("language")
    return code if isinstance(code, str) and known(code) else FOLLOW


def write_choice(folder: Path, code: str) -> None:
    """Write the choice. `code` must be known."""
    if not known(code):
        raise ValueError(f"no language is called {code!r}")
    json_record.write(Path(folder) / FILE_NAME, {"language": code})


def for_screens(folder: Path) -> tuple[str, bool]:
    """The code the screens use, and whether to offer the list."""
    chosen = read_choice(folder)
    if chosen != FOLLOW:
        return chosen, False
    found = computer()
    if found is None:
        return "en", True
    return (found if found in words.LANGUAGES else "en"), False


def of_site(folder: Path) -> str:
    """The language a site's own words are written in (§ 4.4): its
    identity's, "en" where that records none (decision 7), and the screens'
    where no identity is written yet, which is what the wizard will record
    for it. A malformed identity raises StoreError."""
    identity = store.read_identity(folder)
    if identity is None:
        return words.in_use()
    return identity.language or "en"


def picker(chosen: str) -> str:
    """The top bar's select, beside the theme's. The page's script keeps a
    change and reloads the page in it."""
    def option(code: str, shown: str, lang: str = "") -> str:
        selected = " selected" if code == chosen else ""
        spoken = f' lang="{lang}"' if lang else ""
        return f'<option value="{code}"{spoken}{selected}>{html.escape(shown)}</option>'

    options = [option(FOLLOW, say("languages.follow"))]
    options += [option(code, words.name(code), code) for code in words.LANGUAGES]
    return (f'<label class="theme">{say("languages.label")} <select data-language-picker>'
            + "".join(options) + "</select></label>")


def offer() -> str:
    """The list at the top of every screen while the language cannot be told."""
    buttons = "".join(
        f'<button type="button" data-language="{code}" lang="{code}">'
        f"{html.escape(words.name(code))}</button> " for code in words.LANGUAGES)
    return f'<div class="languages-offer"><p>{say("languages.offer")}</p><p>{buttons}</p></div>'
