"""The site's look: the choices it is made from, and the style code made from
them (PRESS-0196, docs/specs/PRESS-0196-site-look.md).

A site's look is three files in the Store's look/ folder: choices.json, what
the Look screen offers; extra.css, their own CSS, added last; and style.css,
made from the two and the one file the Builder publishes and every page
links. The starter's three looks are the three layouts here, and a layout's
defaults are what that look set before the Look screen existed (§ 4.2).
Nothing here imports the Face.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pressless import store
from pressless.words import say

# PRESS-0239: three looks to start from, each with large type, underlined
# links and a visible focus ring, and each rearranging itself to the screen's
# width: the first user is partially sighted. Every text colour of a layout's
# defaults has a contrast of at least 7:1 against its background, by the WCAG
# formula, in light and in dark. The names are the layouts' own, as file names
# are, and are never shown: the words table holds what setup says about each.
LAYOUTS = ("sunrise", "meadow", "harbour")

# PRESS-0248: each layout's colours by name, the rules below naming no other.
# The dark set applies where the visitor's computer is set to dark.
COLOURS = ("paper", "ink", "soft", "link", "heading", "band", "on-band", "band-soft",
           "accent", "foot", "on-foot", "foot-link", "line")

# Each row a colour's name, its light default and its dark default.
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
_OWN_WIDTH = {"sunrise": "46.5rem", "meadow": "42rem", "harbour": "46rem"}
_HEADING_FONT = {"sunrise": "serif", "meadow": "system", "harbour": "system"}
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


def palette(layout: str, dark: bool) -> dict[str, str]:
    """A layout's default colours by name, light or dark."""
    rows = [row.split() for row in _PALETTES[layout].strip().splitlines()]
    if [name for name, *_ in rows] != list(COLOURS):
        raise ValueError(f"{layout}'s colours are not COLOURS, in order")
    return {name: values[dark] for name, *values in rows}


def defaults(layout: str) -> Choices:
    """What the starter look of that name set before the Look screen existed."""
    if layout not in LAYOUTS:
        raise ValueError(f"no layout is called {layout!r}")
    return Choices(layout, palette(layout, False), palette(layout, True), "system",
                   _HEADING_FONT[layout], "large", "medium", ())


def problem(choices: Choices) -> str | None:
    """Why `choices` is not one § 4.1's table allows, or None."""
    if choices.layout not in LAYOUTS:
        return f"no layout is called {choices.layout!r}"
    for scheme in (choices.light, choices.dark):
        if not isinstance(scheme, dict) or list(scheme) != list(COLOURS):
            return "the colours are not exactly the look's colour names, in order"
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
    if data["version"] != VERSION:
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
    return choices


def read(folder: Path) -> Choices | None:
    """The site's choices; None where it has no choices.json."""
    text = store.read_look_file(folder, store.LOOK_CHOICES_NAME)
    return None if text is None else from_json(text)


def read_extra(folder: Path) -> str:
    """Their own CSS; empty where there is none."""
    return store.read_look_file(folder, store.EXTRA_CSS_NAME) or ""


def made_here(folder: Path) -> bool:
    """Whether the style code is exactly what the choices beside it make (§ 4.4
    state 1). False where there are no choices, or they cannot be read."""
    try:
        choices = read(folder)
    except LookUnreadable:
        return False
    return choices is not None and store.read_style_code(folder) == css(choices,
                                                                        read_extra(folder))


def digest(folder: Path) -> str:
    """SHA-256 over choices.json, extra.css and style.css in that order, an
    absent file counting as a fixed marker (§ 4.4, INV-8)."""
    total = hashlib.sha256()
    for name in (store.LOOK_CHOICES_NAME, store.EXTRA_CSS_NAME, store.STYLE_CODE_NAME):
        path = store.look_path_for(folder, name)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            total.update(b"absent\0")
            continue
        total.update(b"%d\0" % len(data) + data)
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
    WARN_BELOW, light first (§ 3 decision 4)."""
    found = []
    for scheme, colours in (("light", choices.light), ("dark", choices.dark)):
        for text, ground in TEXT_PAIRS:
            ratio = contrast(colours[text], colours[ground])
            if ratio < WARN_BELOW:
                found.append((scheme, text, ground, round(ratio, 2)))
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


def css(choices: Choices, extra: str) -> str:
    """The style code, in § 4.2's order: the palette, the four measures, the
    layout's rules, the journal's, the effects chosen, and last their own CSS.

    made_here compares a site's saved style code with this byte for byte. So
    changing any rule below, or the three notes' words, makes every saved look
    read as hand-edited (PRESS-0314); a test in test_look.py says so."""
    def declared(colours: dict[str, str]) -> str:
        return " ".join(f"--{name}: {value};" for name, value in colours.items())
    width = _FIXED_WIDTHS.get(choices.width, _OWN_WIDTH[choices.layout])
    parts = [
        f"/* {say('look.style_note')} */\n",
        f":root {{ color-scheme: light dark; {declared(choices.light)} }}\n",
        f"@media (prefers-color-scheme: dark) {{ :root {{ {declared(choices.dark)} }} }}\n",
        f":root {{ --body-font: {FONTS[choices.body_font]};\n"
        f"  --heading-font: {FONTS[choices.heading_font]};\n"
        f"  --text-size: {TEXT_SIZES[choices.text_size]}; --width: {width}; }}\n",
        _LAYOUT_RULES[choices.layout], "\n",
        f"/* {say('look.journal_note')} */\n", _JOURNAL_RULES,
    ]
    parts += [_EFFECT_RULES[effect] for effect in EFFECTS if effect in choices.effects]
    parts += [f"/* {say('look.extra_note')} */\n", extra]
    return "".join(parts)


# The layout, journal and effect rules below are part of every saved look:
# see css() before changing one.

# Sunrise: a warm band across the top, one centred column.
_SUNRISE = """
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
a { color: var(--link); text-decoration: underline; text-underline-offset: 0.15em; }
a:focus-visible, button:focus-visible { outline: 3px solid var(--ink); outline-offset: 3px; }

header.site {
  background: var(--band);
  color: var(--on-band);
  padding: 1.5rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
}
header.site a { color: var(--on-band); }
header.site a:focus-visible { outline-color: var(--on-band); }
.site-name {
  font-family: var(--heading-font);
  font-size: 1.9rem;
  font-weight: bold;
  text-decoration: none;
}
.site-description { margin: 0.25rem 0 0; font-size: 1.05rem; color: var(--band-soft); }
.site-description:empty { display: none; }
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 1rem; }
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none;
  border-bottom: 3px solid var(--accent); }

main, .wrap { flex: 1 0 auto; width: 100%; box-sizing: border-box; max-width: var(--width);
  margin: 0 auto; padding: 2rem 1.25rem; }
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.25;
  color: var(--heading); }
h1 { font-size: 2.2rem; margin-top: 0.5rem; }
img { max-width: 100%; height: auto; border-radius: 0.5rem; }

footer.site {
  background: var(--foot);
  color: var(--on-foot);
  padding: 1.25rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
  font-size: 0.95rem;
}
footer.site p { margin: 0; }
footer.site a { color: var(--foot-link); }
"""

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
a { color: var(--link); text-decoration: underline; text-underline-offset: 0.15em; }
a:focus-visible, button:focus-visible { outline: 3px solid var(--ink); outline-offset: 3px; }

header.site { background: var(--band); color: var(--on-band); padding: 1.5rem 1.25rem; }
header.site a { color: var(--on-band); }
header.site a:focus-visible { outline-color: var(--on-band); }
.site-name { font-family: var(--heading-font); font-size: 1.7rem; font-weight: bold;
  text-decoration: none; line-height: 1.2; }
.site-description { margin: 0.5rem 0 0; font-size: 1rem; color: var(--band-soft); }
.site-description:empty { display: none; }
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 1rem; }
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none;
  border-bottom: 3px solid var(--accent); }

main, .wrap { max-width: var(--width); padding: 2rem 1.25rem; }
h1, h2, h3 { font-family: var(--heading-font); line-height: 1.25; }
h1 { font-size: 2.1rem; margin-top: 0.5rem; color: var(--heading); }
img { max-width: 100%; height: auto; border-radius: 0.5rem; }

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
_HARBOUR = """
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
a { color: var(--link); text-decoration: underline; text-underline-offset: 0.15em; }
a:focus-visible, button:focus-visible { outline: 3px solid var(--ink); outline-offset: 3px; }

header.site {
  background: var(--band);
  color: var(--on-band);
  padding: 1.25rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
}
header.site a { color: var(--on-band); }
header.site a:focus-visible { outline-color: var(--on-band); }
.site-name { font-family: var(--heading-font); font-size: 1.6rem; font-weight: 800;
  text-decoration: none; letter-spacing: 0.01em; }
.site-description { margin: 0.25rem 0 0; font-size: 1rem; color: var(--band-soft); }
.site-description:empty { display: none; }
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 0.75rem; }
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none;
  border-bottom: 3px solid var(--accent); }

/* Wide screens: the name on the left, the menu on the right. */
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

main, .wrap { flex: 1 0 auto; width: 100%; box-sizing: border-box; max-width: var(--width);
  margin: 0 auto; padding: 2.5rem 1.25rem; }
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
img { max-width: 100%; height: auto; border-radius: 0.5rem; }

footer.site {
  background: var(--foot);
  color: var(--on-foot);
  padding: 1.5rem max(1.25rem, calc((100% - var(--width) + 2.5rem) / 2));
  font-size: 0.95rem;
}
footer.site a { color: var(--foot-link); }
footer.site p { margin: 0; }
"""

_LAYOUT_RULES = {"sunrise": _SUNRISE, "meadow": _MEADOW, "harbour": _HARBOUR}

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
