"""The Face's colour themes, and which one he chose (PRESS-0190).

A theme is the Face's eleven colours and nothing else; the shapes are the
same in all of them. The choice is kept in theme.json in Pressless's own
folder, not in the browser: the Face's port changes every run, and a browser
keeps its storage per port, so a choice kept there would be lost each start.

The themes inspired by games, films and TV carry names of their own. This
repository is public, and a title is somebody's trademark.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pressless.safe_write import write_whole

FILE_NAME = "theme.json"
FOLLOW = "follow"  # no theme of its own: light or dark as the computer is set

# The custom properties every theme sets, in the order Theme.colours holds them.
NAMES = ("paper", "sheet", "ink", "soft", "line", "amber", "amber-ink",
         "press", "on-press", "alert")


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    group: str
    dark: bool
    colours: tuple[str, ...]  # one per NAMES entry


def _theme(key: str, name: str, group: str, dark: bool, colours: str) -> Theme:
    """`colours` is one hex value per NAMES entry, in that order."""
    values = tuple(colours.split())
    if len(values) != len(NAMES):
        raise ValueError(f"theme {key} has {len(values)} colours")
    return Theme(key, name, group, dark, values)


_BASIC = "Basic"
_GAMES = "Inspired by games"
_FILMS = "Inspired by films"
_TV = "Inspired by TV"

# Colours in NAMES order:
#      paper   sheet   ink     soft    line    amber   amber-ink press on-press alert
THEMES = (
    _theme("light", "Light", _BASIC, False,
           "#f4efe6 #fffdf8 #2b2620 #6b6255 #d9cfbf #b97a1c #8a5a12 #2b2620 #f4efe6 #b3412c"),
    _theme("dark", "Dark", _BASIC, True,
           "#1d1a16 #28241f #f4efe6 #b5aa99 #3e382f #e9a23b #f0b95e #e9a23b #1d1a16 #e27a62"),
    _theme("contrast-light", "High contrast, light", _BASIC, False,
           "#ffffff #ffffff #000000 #1f1f1f #000000 #0040c0 #0033a0 #000000 #ffffff #b00000"),
    _theme("contrast-dark", "High contrast, dark", _BASIC, True,
           "#000000 #000000 #ffffff #e6e6e6 #ffffff #ffd400 #ffe14d #ffd400 #000000 #ff6b6b"),
    # Games
    _theme("wasteland", "Wasteland terminal", _GAMES, True,
           "#0d1a0f #142417 #b8ffb8 #7fcf83 #2a4a2e #3cff6a #7dff9a #3cff6a #0d1a0f #ff7b6b"),
    _theme("forest-hero", "Forest hero", _GAMES, False,
           "#eef3e2 #fbfdf5 #1f2a1a #4f5d45 #c9d4b4 #8a6a0c #6b5200 #2e5e2a #fbfdf5 #a8322b"),
    _theme("silver-sword", "Silver sword", _GAMES, True,
           "#16181b #202327 #e6e6e6 #a9adb3 #34383e #d9483a #ff8a7d #c0392b #ffffff #ff8a7d"),
    _theme("neon-city", "Neon city", _GAMES, True,
           "#0b0b14 #15152a #f2f2f2 #a8a8c8 #2b2b4a #fcee0a #fcee0a #fcee0a #0b0b14 #ff4f86"),
    _theme("blocky-overworld", "Blocky overworld", _GAMES, False,
           "#e8e1d3 #f7f3ea #2d2416 #5e5140 #cbbfa8 #4f8a2b #356118 #3f7322 #ffffff #a23b2a"),
    _theme("pipe-land", "Pipe land", _GAMES, False,
           "#fff8e7 #ffffff #1b1b3a #4a4a6a #f0d9a8 #d8231f #b3121a #c81d19 #ffffff #8a1010"),
    _theme("speed-zone", "Speed zone", _GAMES, True,
           "#0b1f4b #12306b #ffffff #c3d0f0 #2a4c8f #ffd400 #ffd400 #ffd400 #0b1f4b #ff8a8a"),
    _theme("ringworld", "Ringworld", _GAMES, True,
           "#1a2124 #232c30 #e3ece8 #9fb3ab #36444a #5fd38d #7fe0a5 #5fd38d #102016 #ff8a65"),
    _theme("test-chamber", "Test chamber", _GAMES, False,
           "#f2f4f5 #ffffff #1d2326 #50595e #d3d9dc #c85d00 #9a4700 #0a6ebd #ffffff #b3261e"),
    _theme("bonfire", "Bonfire", _GAMES, True,
           "#120f0c #1c1813 #e8dcc8 #a8987e #3a3127 #ff8c1a #ffad5c #ff8c1a #120f0c #ff6f59"),
    _theme("valley-farm", "Valley farm", _GAMES, False,
           "#f6ecd2 #fff8e6 #3b2a17 #6b5536 #dcc79a #3f8f3a #2d6b29 #8b4a1c #fff8e6 #a8322b"),
    # Films
    _theme("hyperspace", "Hyperspace", _FILMS, True,
           "#05070d #0e1320 #f0f0f0 #a5adbf #24304a #ffe81f #ffe81f #ffe81f #05070d #ff6b6b"),
    _theme("digital-rain", "Digital rain", _FILMS, True,
           "#000a00 #031503 #b6ffb6 #6fdc6f #0f3a0f #00ff41 #00ff41 #00ff41 #001a00 #ff6b6b"),
    _theme("replicant-night", "Replicant night", _FILMS, True,
           "#0d0a14 #181226 #f1e9ff #b5a6cc #33284a #ff4fa3 #ff7ab9 #ff4fa3 #0d0a14 #ff9a6b"),
    _theme("middle-realm", "Middle realm", _FILMS, False,
           "#efe4c8 #f9f2df #2b1d0e #5e4a2e #d4c296 #8a6d1d #6b520f #2f4a23 #f9f2df #8f2a1c"),
    _theme("dream-house", "Dream house", _FILMS, False,
           "#fff0f6 #ffffff #3a0a26 #6e3a57 #f7c6dc #d6247f #a3165f #c21c72 #ffffff #b0213a"),
    _theme("spice-desert", "Spice desert", _FILMS, False,
           "#efdcb5 #f8ead0 #2e1d0b #5f4423 #d2b57f #a8521a #8a4210 #2e3f6e #f8ead0 #9c2a1a"),
    # TV
    _theme("upside-down", "Upside down", _TV, True,
           "#0a0606 #170c0c #f3e6e6 #bba2a2 #3a1d1d #e50914 #ff6b70 #e50914 #ffffff #ffb347"),
    _theme("desert-lab", "Desert lab", _TV, False,
           "#f1ead2 #fbf6e6 #1f2a1a #4e5a42 #d8cca6 #1f8a70 #146b56 #2f6f3a #ffffff #9a2f1f"),
    _theme("winter-is-near", "Winter is near", _TV, False,
           "#e9edf1 #f8fafc #1b2430 #4b5869 #c9d3de #3d6a99 #2a4e75 #1b2430 #f8fafc #9e2b25"),
    _theme("yellow-town", "Yellow town", _TV, False,
           "#fff7cc #fffdf0 #1f2a44 #4a5571 #f0dc80 #2a7ab8 #1d5a8a #1f2a44 #fff7cc #b3261e"),
    _theme("time-box", "Time box", _TV, True,
           "#0d1b3d #13254f #eef3ff #aab8d9 #2b4277 #6fb7ff #8cc7ff #6fb7ff #0d1b3d #ff8a7a"),
    _theme("bounty-hunter", "Bounty hunter", _TV, True,
           "#1b1d1f #26292c #e9ecef #a4abb3 #3b4045 #9fb4c7 #c5d4e2 #9fb4c7 #1b1d1f #ff8a65"),
)

_BY_KEY = {theme.key: theme for theme in THEMES}


def find(key: str) -> Theme | None:
    return _BY_KEY.get(key)


def known(key: str) -> bool:
    """A key the picker offers: FOLLOW or a theme's."""
    return key == FOLLOW or key in _BY_KEY


def read_choice(folder: Path) -> str:
    """The chosen key. Missing, unparseable or unknown reads as FOLLOW, so the
    Face always has a look."""
    try:
        data = json.loads((Path(folder) / FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return FOLLOW
    if not isinstance(data, dict) or data.get("version") != 1:
        return FOLLOW
    key = data.get("theme")
    return key if isinstance(key, str) and known(key) else FOLLOW


def write_choice(folder: Path, key: str) -> None:
    """Write the choice, replacing the file whole. `key` must be known."""
    if not known(key):
        raise ValueError(f"no theme is called {key!r}")
    target = Path(folder) / FILE_NAME
    write_whole(target, json.dumps({"version": 1, "theme": key}), prefix=f".{FILE_NAME}.")


def declarations(theme: Theme) -> str:
    """The theme's colours as custom-property declarations."""
    pairs = zip(NAMES, theme.colours, strict=True)
    return " ".join(f"--{name}: {colour};" for name, colour in pairs)


def preview(dark: bool) -> str:
    """PRESS-0187: the preview shows his site's own colours, so a dark look
    dims it rather than let a light site glare. The switch that brings the
    true colours back shows only where there is dimming."""
    if dark:
        return "--preview-dim: brightness(.75); --preview-switch: block;"
    return "--preview-dim: none; --preview-switch: none;"


def css() -> str:
    """One rule per theme, keyed on the page's data-theme. `:root[...]`
    outranks the plain `:root` and its dark media query, so a chosen theme
    wins over the computer's setting."""
    rules = []
    for theme in THEMES:
        values = declarations(theme)
        shadow = "rgba(0, 0, 0, .45)" if theme.dark else "rgba(60, 40, 10, .10)"
        scheme = "dark" if theme.dark else "light"
        rules.append(f':root[data-theme="{theme.key}"] {{ color-scheme: {scheme}; '
                     f"{values} --shadow: {shadow}; {preview(theme.dark)} }}")
    return "\n".join(rules)


def picker(chosen: str) -> str:
    """The top bar's select. The page's script applies a change at once."""
    def option(key: str, name: str) -> str:
        selected = " selected" if key == chosen else ""
        return f'<option value="{key}"{selected}>{name}</option>'

    groups: dict[str, list[str]] = {}
    for theme in THEMES:
        groups.setdefault(theme.group, []).append(option(theme.key, theme.name))
    parts = [option(FOLLOW, "Follow my computer")]
    parts.extend(f'<optgroup label="{group}">{"".join(items)}</optgroup>'
                 for group, items in groups.items())
    return ('<label class="theme">Theme <select data-theme-picker>'
            + "".join(parts) + "</select></label>")
