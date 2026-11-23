"""The site's look: the choices it is made from, and the style code made from
them (PRESS-0196, docs/specs/PRESS-0196-site-look.md).

A site's look is three files in the Store's look/ folder: choices.json, what
the Look screen offers; extra.css, their own CSS, added last; and style.css,
made from the two and the one file the Builder publishes and every page
links. The starter's looks are the layouts here, and a layout's defaults
are that layout wearing its own colour style (PRESS-0359 § 4.2).
Nothing here imports the Face.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from pressless import store
from pressless.words import say

# PRESS-0239: looks to start from, each with large type, underlined links and
# a visible focus ring, and each rearranging itself to the screen's width: the
# first user is partially sighted. The names are the layouts' own, as file
# names are, and are never shown: the words table holds what setup says about
# each. They are saved in sites' files, so none is renamed (PRESS-0359 § 4.1).
# A layout added here needs an entry in OWN_STYLE, _OWN_WIDTH, _HEADING_FONT
# and _LAYOUT_RULES too.
LAYOUTS = ("sunrise", "meadow", "harbour", "studio", "market", "stage", "commons", "letter")

# PRESS-0248: the colours by name, the rules below naming no other. The dark
# set applies where the visitor's computer is set to dark.
COLOURS = ("paper", "ink", "soft", "link", "heading", "band", "on-band", "band-soft",
           "accent", "foot", "on-foot", "foot-link", "line")

# PRESS-0359 § 4.2: sets of colours any layout can wear. Choosing one fills
# the colour boxes; a site saves the colours, never a style's name. Every text
# colour has a contrast of at least 7:1 against its background, by the WCAG
# formula, in light and in dark.
STYLES = ("sunrise", "meadow", "harbour", "ink", "slate", "plum", "sand", "coral", "teal",
          "night", "sky")
OWN_STYLE = {"sunrise": "sunrise", "meadow": "meadow", "harbour": "harbour", "studio": "ink",
             "market": "slate", "stage": "night", "commons": "sky", "letter": "ink"}

# Each style's rows: a colour's name, its light value and its dark value.
_PALETTES = {
    "sunrise": """
        paper     #fffaf2 #1a1410
        ink       #2b1d14 #f5e9dc
        soft      #3a3a3a #d4c4b2
        link      #7c2a0b #ffb38a
        heading   #2b1d14 #f5e9dc
        band      #9a3412 #6b230a
        on-band   #ffffff #ffffff
        band-soft #ffffff #ffffff
        accent    #ffffff #ffffff
        foot      #f3e3cf #2b2019
        on-foot   #2b1d14 #f5e9dc
        foot-link #7c2a0b #ffb38a
        line      #f3e3cf #4a3a2e
    """,
    "meadow": """
        paper     #f6f8f4 #111a14
        ink       #1c2a1f #e2ece4
        soft      #3a3a3a #b9c9bc
        link      #1d5c32 #8fd8a7
        heading   #1f4d2b #a6e3b8
        band      #1f4d2b #183d22
        on-band   #ffffff #ffffff
        band-soft #ffffff #ffffff
        accent    #ffffff #ffffff
        foot      #f6f8f4 #111a14
        on-foot   #1c2a1f #e2ece4
        foot-link #1d5c32 #8fd8a7
        line      #c9d6c9 #34483a
    """,
    "harbour": """
        paper     #ffffff #0e1525
        ink       #14213d #e6ecf7
        soft      #3a3a3a #b6c2d8
        link      #1e40af #9fc2ff
        heading   #14213d #e6ecf7
        band      #14213d #18264a
        on-band   #ffffff #ffffff
        band-soft #dbe4f3 #dbe4f3
        accent    #f4a261 #f4a261
        foot      #14213d #18264a
        on-foot   #ffffff #ffffff
        foot-link #ffffff #ffffff
        line      #dbe4f3 #2c3c63
    """,
    "ink": """
        paper     #ffffff #000000
        ink       #111111 #f2f2f2
        soft      #333333 #cccccc
        link      #0b3d91 #9cc3ff
        heading   #000000 #ffffff
        band      #111111 #1f1f1f
        on-band   #ffffff #ffffff
        band-soft #e6e6e6 #e6e6e6
        accent    #ffffff #ffffff
        foot      #f2f2f2 #141414
        on-foot   #111111 #f2f2f2
        foot-link #0b3d91 #9cc3ff
        line      #111111 #f2f2f2
    """,
    "slate": """
        paper     #f4f6f8 #12161c
        ink       #1f2933 #e4e9ef
        soft      #3a4450 #b9c3cf
        link      #1f4e8c #9cc3f5
        heading   #1f2933 #e4e9ef
        band      #1b4580 #1a2c45
        on-band   #ffffff #ffffff
        band-soft #e3ebf5 #d5deea
        accent    #f2c14e #f2c14e
        foot      #2d3742 #1c232c
        on-foot   #ffffff #e4e9ef
        foot-link #ffffff #c9dcf5
        line      #d3dae2 #2f3946
    """,
    "plum": """
        paper     #fbf6ec #1b1220
        ink       #2a1630 #f1e6f3
        soft      #4a3a4f #cdbcd2
        link      #5b1f6e #e2b4f0
        heading   #4b1659 #ecc8f5
        band      #4b1659 #3a1145
        on-band   #ffffff #ffffff
        band-soft #f3e3f7 #f3e3f7
        accent    #f5d48a #f5d48a
        foot      #f1e6d4 #24182a
        on-foot   #2a1630 #f1e6f3
        foot-link #5b1f6e #e2b4f0
        line      #e2d2bc #3d2d44
    """,
    "sand": """
        paper     #faf5ec #1c1712
        ink       #33261a #f1e7da
        soft      #4a3e33 #cfc2b2
        link      #7a3e12 #f0b98a
        heading   #5a3618 #f0d3b4
        band      #5e3b1e #4a2f17
        on-band   #ffffff #ffffff
        band-soft #f6e7d4 #f6e7d4
        accent    #e8b04a #e8b04a
        foot      #efe3cf #2a2219
        on-foot   #33261a #f1e7da
        foot-link #6a3410 #f0b98a
        line      #e3d3b9 #44382b
    """,
    "coral": """
        paper     #ffffff #1a1212
        ink       #2b1a1a #f6e8e6
        soft      #4a3a3a #d3c1be
        link      #a3271b #ffb4a8
        heading   #8a2418 #ffc1b6
        band      #ff8a75 #7a2318
        on-band   #2b1a1a #ffffff
        band-soft #2b1a1a #ffffff
        accent    #2b1a1a #ffe08a
        foot      #fdeae6 #2a1b1a
        on-foot   #2b1a1a #f6e8e6
        foot-link #8f2116 #ffb4a8
        line      #f6d4cd #4a3330
    """,
    "teal": """
        paper     #f4f7f7 #0f1a1b
        ink       #17302f #dfeeed
        soft      #3a4a4a #b5c9c8
        link      #0b5a57 #86dcd5
        heading   #0b4f4c #9fe5df
        band      #094c49 #0c3f3d
        on-band   #ffffff #ffffff
        band-soft #e0f3f1 #e0f3f1
        accent    #f6c38b #f6c38b
        foot      #e6eceb #172223
        on-foot   #17302f #dfeeed
        foot-link #084a47 #86dcd5
        line      #cfdad9 #2b3b3c
    """,
    "night": """
        paper     #121218 #0a0a0f
        ink       #ecebf5 #ecebf5
        soft      #c4c2d6 #c4c2d6
        link      #ffd166 #ffd166
        heading   #ffffff #ffffff
        band      #000000 #000000
        on-band   #ffffff #ffffff
        band-soft #ffd166 #ffd166
        accent    #ff4f8b #ff4f8b
        foot      #000000 #000000
        on-foot   #ecebf5 #ecebf5
        foot-link #ffd166 #ffd166
        line      #2c2c3a #2c2c3a
    """,
    "sky": """
        paper     #f3f8fd #0d1622
        ink       #13263f #e3edf8
        soft      #34465c #b9c8da
        link      #134a8e #9ccaff
        heading   #0f2f5c #b9d8ff
        band      #cfe4f7 #16304f
        on-band   #0f2f5c #ffffff
        band-soft #1d3d66 #d6e6f7
        accent    #0f2f5c #9ccaff
        foot      #0f2f5c #16304f
        on-foot   #ffffff #ffffff
        foot-link #ffffff #d6e6f7
        line      #cfe0f0 #26405f
    """,
}

# § 4.1: each font a stack of families found on most computers, ending in a
# generic one; the preview's font-src 'self' refuses an outside font.
FONTS = {
    "system": 'system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    "serif": 'Georgia, "Times New Roman", serif',
    "humanist": ('Seravek, "Gill Sans Nova", Ubuntu, Calibri, "DejaVu Sans", '
                 "source-sans-pro, sans-serif"),
    "mono": ('ui-monospace, "Cascadia Code", "Source Code Pro", Menlo, Consolas, '
             '"DejaVu Sans Mono", monospace'),
}
TEXT_SIZES = {"normal": "100%", "large": "118.75%", "larger": "137.5%"}
WIDTHS = ("narrow", "medium", "wide")
_FIXED_WIDTHS = {"narrow": "38rem", "wide": "56rem"}
# `medium` is each layout's own width, and what it set before.
_OWN_WIDTH = {"sunrise": "46.5rem", "meadow": "42rem", "harbour": "46rem", "studio": "60rem",
              "market": "48rem", "stage": "50rem", "commons": "50rem", "letter": "38rem"}
_HEADING_FONT = {"sunrise": "serif", "meadow": "system", "harbour": "system",
                 "studio": "system", "market": "humanist", "stage": "system",
                 "commons": "humanist", "letter": "serif"}
EFFECTS = ("lift", "reveal", "smooth")

# PRESS-0248's pairs, the same for every layout: each text colour and the
# background it is painted on. Every layout paints its footer with `foot`.
TEXT_PAIRS = (("ink", "paper"), ("soft", "paper"), ("link", "paper"), ("heading", "paper"),
              ("on-band", "band"), ("band-soft", "band"),
              ("on-foot", "foot"), ("foot-link", "foot"))
WARN_BELOW = 4.5   # WCAG AA for normal text; the user's bar, 2026-10-15

VERSION = 1
_HEX = re.compile(r"#[0-9a-f]{6}")
_FIELDS = ("version", "layout", "colours", "body_font", "heading_font", "text_size",
           "width", "effects")


class LookUnreadable(store.StoreError):
    """choices.json is not a file this version of Pressless reads."""


@dataclass(frozen=True)
class Choices:
    layout: str
    light: dict[str, str]
    dark: dict[str, str]
    body_font: str
    heading_font: str
    text_size: str
    width: str
    effects: tuple[str, ...]


def palette(style: str, dark: bool) -> dict[str, str]:
    """A colour style's colours by name, light or dark. The three first
    layouts' own styles share their names, so a layout's name works here."""
    rows = [row.split() for row in _PALETTES[style].strip().splitlines()]
    if [name for name, *_ in rows] != list(COLOURS):
        raise ValueError(f"{style}'s colours are not COLOURS, in order")
    return {name: values[dark] for name, *values in rows}


def defaults(layout: str) -> Choices:
    """A layout wearing its own style; for the three first, what the starter
    look of that name set before the Look screen existed."""
    if layout not in LAYOUTS:
        raise ValueError(f"no layout is called {layout!r}")
    style = OWN_STYLE[layout]
    return Choices(layout, palette(style, False), palette(style, True), "system",
                   _HEADING_FONT[layout], "large", "medium", ())


def problem(choices: Choices) -> str | None:
    """Why `choices` is not one § 4.1's table allows, or None."""
    if choices.layout not in LAYOUTS:
        return f"no layout is called {choices.layout!r}"
    for scheme in (choices.light, choices.dark):
        if not isinstance(scheme, dict) or sorted(scheme) != sorted(COLOURS):
            return "the colours are not exactly the look's colour names"
        for name, value in scheme.items():
            if not isinstance(value, str) or not _HEX.fullmatch(value):
                return f"{name} is not a colour written #rrggbb"
    for font in (choices.body_font, choices.heading_font):
        if font not in FONTS:
            return f"no font is called {font!r}"
    if choices.text_size not in TEXT_SIZES:
        return f"no text size is called {choices.text_size!r}"
    if choices.width not in WIDTHS:
        return f"no width is called {choices.width!r}"
    if any(effect not in EFFECTS for effect in choices.effects):
        return "an effect is not one Pressless offers"
    if len(set(choices.effects)) != len(choices.effects):
        return "an effect is named twice"
    return None


def to_json(choices: Choices) -> str:
    data = {"version": VERSION, "layout": choices.layout,
            "colours": {"light": choices.light, "dark": choices.dark},
            "body_font": choices.body_font, "heading_font": choices.heading_font,
            "text_size": choices.text_size, "width": choices.width,
            "effects": list(choices.effects)}
    return json.dumps(data, indent=2) + "\n"


def from_json(text: str) -> Choices:
    """The choices in `text`, or LookUnreadable for anything § 4.1 refuses."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LookUnreadable(f"{store.LOOK_CHOICES_NAME} is not JSON: {exc}") from exc
    if not isinstance(data, dict) or sorted(data) != sorted(_FIELDS):
        raise LookUnreadable(f"{store.LOOK_CHOICES_NAME} does not hold the look's fields")
    if type(data["version"]) is not int or data["version"] != VERSION:   # true == 1
        raise LookUnreadable(f"{store.LOOK_CHOICES_NAME} is version {data['version']!r}")
    colours, effects = data["colours"], data["effects"]
    if (not isinstance(colours, dict) or sorted(colours) != ["dark", "light"]
            or not isinstance(effects, list)):
        raise LookUnreadable(f"{store.LOOK_CHOICES_NAME} does not hold the look's fields")
    try:
        choices = Choices(data["layout"], colours["light"], colours["dark"], data["body_font"],
                          data["heading_font"], data["text_size"], data["width"], tuple(effects))
        why = problem(choices)
    except TypeError as exc:   # an unhashable value where a name belongs
        raise LookUnreadable(f"{store.LOOK_CHOICES_NAME}: {exc}") from exc
    if why:
        raise LookUnreadable(f"{store.LOOK_CHOICES_NAME}: {why}")
    # In the look's order, whatever the file's: css() declares them in it.
    return dataclasses.replace(choices, light={name: choices.light[name] for name in COLOURS},
                               dark={name: choices.dark[name] for name in COLOURS})


def read(folder: Path) -> Choices | None:
    """The site's choices; None where it has no choices.json."""
    text = store.read_look_file(folder, store.LOOK_CHOICES_NAME)
    return None if text is None else from_json(text)


def read_extra(folder: Path) -> str:
    """Their own CSS; empty where there is none."""
    return store.read_look_file(folder, store.EXTRA_CSS_NAME) or ""


def made_here(folder: Path) -> bool:
    """Whether the style code is exactly what the choices beside it make, the
    words of its notes aside (§ 4.4 state 2): those come from the words table,
    and rewording one must not make a saved look hand-edited (PRESS-0314).
    A rule added since may be absent, so a look an earlier version saved
    stays made here. False where there are no choices, or they cannot be
    read."""
    try:
        choices = read(folder)
    except LookUnreadable:
        return False
    if choices is None:
        return False
    saved = store.read_style_code(folder)
    def matching(piece: str) -> str:
        if isinstance(piece, _Note):
            return _ANY_NOTE
        if isinstance(piece, _Added):
            return f"(?:{re.escape(piece)})?"
        return re.escape(piece)
    pattern = "".join(matching(piece) for piece in _pieces(choices, read_extra(folder)))
    return saved is not None and re.fullmatch(pattern, saved, re.DOTALL) is not None


def digest(folder: Path) -> str:
    """SHA-256 over choices.json, extra.css and style.css in that order, an
    absent file counting as a fixed marker (§ 4.4, INV-8)."""
    total = hashlib.sha256()
    for name in store.LOOK_FILES:
        data = store.read_look_bytes(folder, name)
        total.update(b"absent\0" if data is None else b"%d\0" % len(data) + data)
    return total.hexdigest()


def save(folder: Path, choices: Choices, extra: str) -> None:
    """Write choices.json, then extra.css, then style.css made from them, each
    atomically; the stylesheet last, so the file the Builder publishes is never
    newer than the choices it was made from (§ 4.2)."""
    why = problem(choices)
    if why:
        raise ValueError(why)
    store.write_look_file(folder, store.LOOK_CHOICES_NAME, to_json(choices))
    store.write_look_file(folder, store.EXTRA_CSS_NAME, extra)
    store.write_style_code(folder, css(choices, extra))


def warnings(choices: Choices) -> list[tuple[str, str, str, float]]:
    """(scheme, text, background, ratio) for each TEXT_PAIRS pair under
    WARN_BELOW, light first (§ 3 decision 4). The ratio is cut to two
    places, never rounded, so a ratio under the bar never shows as it."""
    found = []
    for scheme, colours in (("light", choices.light), ("dark", choices.dark)):
        for text, ground in TEXT_PAIRS:
            ratio = contrast(colours[text], colours[ground])
            if ratio < WARN_BELOW:
                found.append((scheme, text, ground, math.floor(round(ratio * 100, 6)) / 100))
    return found


def contrast(one: str, two: str) -> float:
    """The WCAG 2 contrast ratio of two #rrggbb colours."""
    def luminance(colour: str) -> float:
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    light, dark = sorted((luminance(one), luminance(two)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class _Note(str):
    """A note's place in the style code: a CSS comment holding words-table
    words, which made_here does not compare."""


_ANY_NOTE = r"/\* (?:(?!\*/)[^\n])* \*/\n"   # "/* {words} */\n", any one-line words


class _Added(str):
    """A rule added to every layout after looks were saved without it, which
    made_here accepts absent (PRESS-0314)."""


def css(choices: Choices, extra: str) -> str:
    """The style code, in § 4.2's order: the palette, the four measures, the
    layout's rules, the journal's, the effects chosen, and last their own CSS."""
    return "".join(f"/* {say(piece)} */\n" if isinstance(piece, _Note) else piece
                   for piece in _pieces(choices, extra))


def _pieces(choices: Choices, extra: str) -> list[str]:
    """css()'s pieces in order, each note as its words-table key.

    made_here compares a site's saved style code with these, the notes' words
    aside. So changing any rule below makes every saved look read as
    hand-edited (PRESS-0314); a test in test_look.py says so. A new rule goes
    in as an _Added piece instead, which made_here accepts absent."""
    def declared(colours: dict[str, str]) -> str:
        return " ".join(f"--{name}: {colours[name]};" for name in COLOURS)
    width = _FIXED_WIDTHS.get(choices.width, _OWN_WIDTH[choices.layout])
    parts = [
        _Note("look.style_note"),
        f":root {{ color-scheme: light dark; {declared(choices.light)} }}\n",
        f"@media (prefers-color-scheme: dark) {{ :root {{ {declared(choices.dark)} }} }}\n",
        f":root {{ --body-font: {FONTS[choices.body_font]};\n"
        f"  --heading-font: {FONTS[choices.heading_font]};\n"
        f"  --text-size: {TEXT_SIZES[choices.text_size]}; --width: {width}; }}\n",
        _LAYOUT_RULES[choices.layout], _FOOT_FOCUS, _BLOCK_RULES, "\n",
        _Note("look.journal_note"), _JOURNAL_RULES,
    ]
    parts += [_EFFECT_RULES[effect] for effect in EFFECTS if effect in choices.effects]
    parts += [_Note("look.extra_note"), extra]
    return parts


# The layout, journal and effect rules below are part of every saved look:
# see _pieces before changing one.

# PRESS-0239's focus ring on a footer link, in a colour TEXT_PAIRS holds to
# contrast with the footer: `ink`, the ring's own, is some footers' colour.
_FOOT_FOCUS = _Added("footer.site a:focus-visible { outline-color: var(--foot-link); }\n")

# PRESS-0215 § 4.4: a columns section's columns side by side where the screen
# has room for them, one above the other where it has not, and a button
# section's link drawn as a button. Its border is the link's own colour.
_BLOCK_RULES = _Added("""\
.pressless-columns { display: grid; gap: 0 2rem; }
@media (min-width: 40rem) {
  .pressless-columns { grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); }
}
.pressless-button a { display: inline-block; padding: 0.5em 1.25em; border: 2px solid currentColor;
  border-radius: 0.5rem; font-weight: 600; text-decoration: none; }
""")

# Rules every layout holds, the same in each (PRESS-0239's underlined links
# and visible focus ring among them), joined into each layout's rules below.
_LINK_RULES = """\
a { color: var(--link); text-decoration: underline; text-underline-offset: 0.15em; }
a:focus-visible, button:focus-visible { outline: 3px solid var(--ink); outline-offset: 3px; }
"""
_PICTURE_RULE = """\
img { max-width: 100%; height: auto; border-radius: 0.5rem; }
"""
_NO_EMPTY_DESCRIPTION = """\
.site-description:empty { display: none; }
"""

# Header links on a band: every layout but Studio and Letter, whose header
# sits on the paper.
_HEADER_LINK_RULES = """\
header.site a { color: var(--on-band); }
header.site a:focus-visible { outline-color: var(--on-band); }
"""
# The menu's links: Sunrise, Meadow, Harbour and Market. The others write
# their own.
_NAV_LINK_RULES = """\
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none;
  border-bottom: 3px solid var(--accent); }
"""
# A page in one column between the header and the footer, the footer kept
# at the bottom of a short page.
_COLUMN_BODY = """
html { font-size: var(--text-size); }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--body-font);
  line-height: 1.65;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
""" + _LINK_RULES + """
"""
_NAME_LEFT_MENU_RIGHT = """/* Wide screens: the name on the left, the menu on the right. */
@media (min-width: 48rem) {
  header.site {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    column-gap: 2rem;
  }
  .site-name { grid-column: 1; }
  .site-description { grid-column: 1; }
  nav.primary { grid-column: 2; grid-row: 1 / 3; margin-top: 0; }
}
"""

# The main column of Harbour, Studio, Stage and Commons. Sunrise, Meadow,
# Market and Letter write their own.
_MAIN_COLUMN = """
main, .wrap { flex: 1 0 auto; width: 100%; box-sizing: border-box; max-width: var(--width);
  margin: 0 auto; padding: 2.5rem 1.25rem; }
"""
# The footer of Sunrise, Studio, Market, Stage and Commons. Meadow, Letter and
# Harbour write their own; Harbour's differs only in its padding and order.
_FOOT_RULES = """
footer.site {
  background: var(--foot);
  color: var(--on-foot);
  padding: 1.25rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
  font-size: 0.95rem;
}
footer.site p { margin: 0; }
footer.site a { color: var(--foot-link); }
"""

# Sunrise: a warm band across the top, one centred column.
_SUNRISE = _COLUMN_BODY + """header.site {
  background: var(--band);
  color: var(--on-band);
  padding: 1.5rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
}
""" + _HEADER_LINK_RULES + """\
.site-name {
  font-family: var(--heading-font);
  font-size: 1.9rem;
  font-weight: bold;
  text-decoration: none;
}
.site-description { margin: 0.25rem 0 0; font-size: 1.05rem; color: var(--band-soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 1rem; }
""" + _NAV_LINK_RULES + """
main, .wrap { flex: 1 0 auto; width: 100%; box-sizing: border-box; max-width: var(--width);
  margin: 0 auto; padding: 2rem 1.25rem; }
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.25;
  color: var(--heading); }
h1 { font-size: 2.2rem; margin-top: 0.5rem; }
""" + _PICTURE_RULE + _FOOT_RULES

# Meadow: the name and menu in a green panel, beside the page on a wide
# screen and above it on a narrow one.
_MEADOW = """
html { font-size: var(--text-size); }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--body-font);
  line-height: 1.65;
}
""" + _LINK_RULES + """
header.site { background: var(--band); color: var(--on-band); padding: 1.5rem 1.25rem; }
""" + _HEADER_LINK_RULES + """\
.site-name { font-family: var(--heading-font); font-size: 1.7rem; font-weight: bold;
  text-decoration: none; line-height: 1.2; }
.site-description { margin: 0.5rem 0 0; font-size: 1rem; color: var(--band-soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 1rem; }
""" + _NAV_LINK_RULES + """
main, .wrap { max-width: var(--width); padding: 2rem 1.25rem; }
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.25; }
h1 { font-size: 2.1rem; margin-top: 0.5rem; color: var(--heading); }
""" + _PICTURE_RULE + """
footer.site {
  background: var(--foot);
  color: var(--on-foot);
  border-top: 2px solid var(--line);
  margin: 2rem 1.25rem 0;
  padding: 1rem 0 1.5rem;
  font-size: 0.95rem;
}
footer.site a { color: var(--foot-link); }

/* Wide screens: the name and the menu sit in a panel on the left. */
@media (min-width: 56rem) {
  body {
    display: grid;
    grid-template-columns: 17rem minmax(0, 1fr);
    grid-template-rows: 1fr auto;
    min-height: 100vh;
  }
  header.site { grid-row: 1 / 3; padding: 2.5rem 1.75rem; }
  nav.primary { flex-direction: column; gap: 0.75rem; margin-top: 2rem; }
  nav.primary a { border-left: 4px solid transparent; padding-left: 0.6rem;
    margin-left: calc(-0.6rem - 4px); }
  nav.primary a[aria-current="page"] { border-bottom: none; border-left-color: var(--accent); }
  main, .wrap { padding: 3rem 3rem 2rem; }
  footer.site { margin: 0 3rem; }
}
"""

# Harbour: a navy bar, the name on the left and the menu on the right on a
# wide screen.
_HARBOUR = _COLUMN_BODY + """header.site {
  background: var(--band);
  color: var(--on-band);
  padding: 1.25rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
}
""" + _HEADER_LINK_RULES + """\
.site-name { font-family: var(--heading-font); font-size: 1.6rem; font-weight: 800;
  text-decoration: none; letter-spacing: 0.01em; }
.site-description { margin: 0.25rem 0 0; font-size: 1rem; color: var(--band-soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 0.75rem; }
""" + _NAV_LINK_RULES + """
""" + _NAME_LEFT_MENU_RIGHT + _MAIN_COLUMN + """\
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.2;
  color: var(--heading); }
h1 { font-size: clamp(2rem, 7vw, 2.6rem); font-weight: 800; margin-top: 0.5rem; }
h1::after {
  content: "";
  display: block;
  width: 4rem;
  height: 0.3rem;
  margin-top: 0.75rem;
  background: var(--accent);
  border-radius: 0.15rem;
}
""" + _PICTURE_RULE + """
footer.site {
  background: var(--foot);
  color: var(--on-foot);
  padding: 1.5rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
  font-size: 0.95rem;
}
footer.site a { color: var(--foot-link); }
footer.site p { margin: 0; }
"""

# Studio, for a portfolio: no band; the name and the menu on one line above a
# thin rule, and a wide column for pictures. Its header sits on the paper.
_STUDIO = _COLUMN_BODY + """
header.site {
  padding: 1.5rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2)) 1rem;
  border-bottom: 1px solid var(--line);
}
header.site a { color: var(--ink); }
.site-name { font-family: var(--heading-font); font-size: 1.5rem; font-weight: 700;
  text-decoration: none; letter-spacing: 0.04em; }
.site-description { margin: 0.25rem 0 0; font-size: 1rem; color: var(--soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 0.75rem; }
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none;
  border-bottom: 3px solid var(--link); }
""" + _NAME_LEFT_MENU_RIGHT + _MAIN_COLUMN + """\
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.2; color: var(--heading); }
h1 { font-size: clamp(2rem, 6vw, 2.8rem); font-weight: 700; letter-spacing: -0.01em;
  margin-top: 0.5rem; }
""" + _PICTURE_RULE + _FOOT_RULES + """\
footer.site { border-top: 1px solid var(--line); }
"""

# Market, for a small business: a tall band with the name and the menu
# centred, and the page a raised card on the paper, overlapping the band.
_MARKET = _COLUMN_BODY + """
header.site {
  background: var(--band);
  color: var(--on-band);
  text-align: center;
  padding: 2.5rem 1.25rem 4.5rem;
}
""" + _HEADER_LINK_RULES + """\
.site-name { font-family: var(--heading-font); font-size: 2.2rem; font-weight: 700;
  text-decoration: none; line-height: 1.2; }
.site-description { margin: 0.5rem 0 0; font-size: 1.1rem; color: var(--band-soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.5rem 1.75rem;
  margin-top: 1.25rem; }
""" + _NAV_LINK_RULES + """
main, .wrap { flex: 1 0 auto; width: calc(100% - 1.5rem); box-sizing: border-box;
  max-width: var(--width); margin: -2.5rem auto 2.5rem; padding: 2.25rem 1.5rem;
  background: var(--paper); border: 1px solid var(--line); border-radius: 0.75rem;
  box-shadow: 0 0.75rem 2rem color-mix(in srgb, var(--ink) 15%, transparent); }
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.25; color: var(--heading); }
h1 { font-size: 2.1rem; margin-top: 0; }
""" + _PICTURE_RULE + _FOOT_RULES + """\
footer.site { text-align: center; }
"""

# Stage, for a musician or a band: a tall band with a large name, and the menu
# a row of boxed links.
_STAGE = _COLUMN_BODY + """
header.site {
  background: var(--band);
  color: var(--on-band);
  padding: 3rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2)) 2rem;
}
""" + _HEADER_LINK_RULES + """\
.site-name { font-family: var(--heading-font); font-size: clamp(2.4rem, 9vw, 3.6rem);
  font-weight: 800; text-decoration: none; text-transform: uppercase;
  letter-spacing: 0.04em; line-height: 1.1; }
.site-description { margin: 0.5rem 0 0; font-size: 1.15rem; color: var(--band-soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 1.75rem; }
nav.primary a { display: inline-block; padding: 0.35rem 0.9rem; font-weight: 700;
  border: 2px solid var(--band-soft); border-radius: 0.3rem; }
nav.primary a[aria-current="page"] { text-decoration: none; border-color: var(--accent);
  box-shadow: inset 0 -3px 0 var(--accent); }
""" + _MAIN_COLUMN + """\
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.2; color: var(--heading); }
h1 { font-size: clamp(2rem, 7vw, 2.6rem); font-weight: 800; margin-top: 0.5rem; }
""" + _PICTURE_RULE + _FOOT_RULES

# Commons, for a club or a community: the name in a band, and the menu in a
# strip of its own beneath it, painted with the footer's colours.
_COMMONS = _COLUMN_BODY + """
header.site {
  background: var(--band);
  color: var(--on-band);
  padding: 1.75rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2)) 0;
}
""" + _HEADER_LINK_RULES + """\
.site-name { font-family: var(--heading-font); font-size: 1.9rem; font-weight: 700;
  text-decoration: none; }
.site-description { margin: 0.25rem 0 0; font-size: 1.05rem; color: var(--band-soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.75rem; margin-top: 1.25rem;
  padding: 0.75rem 0; background: var(--foot); box-shadow: 0 0 0 100vmax var(--foot);
  clip-path: inset(0 -100vmax); }
header.site nav.primary a { color: var(--foot-link); font-weight: 600; }
header.site nav.primary a:focus-visible { outline-color: var(--foot-link); }
nav.primary a[aria-current="page"] { text-decoration: none;
  border-bottom: 3px solid var(--foot-link); }
""" + _MAIN_COLUMN + """\
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.25; color: var(--heading); }
h1 { font-size: 2.2rem; margin-top: 0.5rem; }
""" + _PICTURE_RULE + _FOOT_RULES

# Letter, for a plain document: no band, one narrow centred column, and the
# name a plain heading above it.
_LETTER = _COLUMN_BODY + """
header.site, footer.site { width: 100%; box-sizing: border-box; max-width: var(--width);
  margin: 0 auto; }
header.site { padding: 3rem 1.25rem 0; }
header.site a { color: var(--link); }
header.site .site-name { font-family: var(--heading-font); font-size: 2rem; font-weight: bold;
  color: var(--heading); text-decoration: none; }
.site-description { margin: 0.25rem 0 0; font-size: 1.05rem; font-style: italic;
  color: var(--soft); }
""" + _NO_EMPTY_DESCRIPTION + """\
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.25rem; margin-top: 1rem;
  padding-bottom: 1rem; border-bottom: 1px solid var(--line); }
nav.primary a[aria-current="page"] { text-decoration: none; font-weight: 700; }
main, .wrap { flex: 1 0 auto; width: 100%; box-sizing: border-box; max-width: var(--width);
  margin: 0 auto; padding: 2rem 1.25rem; }
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.3; color: var(--heading); }
h1 { font-size: 1.9rem; margin-top: 0.5rem; }
""" + _PICTURE_RULE + """
footer.site {
  background: var(--foot);
  color: var(--on-foot);
  border-top: 1px solid var(--line);
  padding: 1.25rem;
  font-size: 0.95rem;
}
footer.site p { margin: 0; }
footer.site a { color: var(--foot-link); }
"""

_LAYOUT_RULES = {"sunrise": _SUNRISE, "meadow": _MEADOW, "harbour": _HARBOUR,
                 "studio": _STUDIO, "market": _MARKET, "stage": _STAGE, "commons": _COMMONS,
                 "letter": _LETTER}

_JOURNAL_RULES = """.prose { overflow-wrap: break-word; }
.post-meta, .eyebrow, .lead, .page-intro, .comments-note { color: var(--soft); }
.post-list, .comment-list { list-style: none; padding: 0; }
.post-list li, .comment { margin-bottom: 1.25rem; }
.chip { display: inline-block; margin: 0 0.5rem 0.5rem 0; }
.pager, .back { margin-top: 2rem; }
"""

# § 4.3: CSS alone, each inside prefers-reduced-motion: no-preference, so a
# visitor who asked for less motion gets none; colours by the palette's names.
_EFFECT_RULES = {
    "lift": """@media (prefers-reduced-motion: no-preference) {
  main img { transition: transform 0.2s ease, box-shadow 0.2s ease; }
  main img:hover { transform: translateY(-4px);
    box-shadow: 0 0.5rem 1.25rem color-mix(in srgb, var(--ink) 25%, transparent); }
}
""",
    "reveal": """@supports (animation-timeline: view()) {
  @media (prefers-reduced-motion: no-preference) {
    main > * { animation: pressless-reveal linear both; animation-timeline: view();
      animation-range: entry 0% entry 35%; }
    @keyframes pressless-reveal {
      from { opacity: 0; transform: translateY(1.5rem); }
      to { opacity: 1; transform: none; }
    }
  }
}
""",
    "smooth": """@media (prefers-reduced-motion: no-preference) {
  html { scroll-behavior: smooth; }
}
""",
}
