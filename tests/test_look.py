# The site's look and the style code made from it (PRESS-0196).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0196-site-look.md
# § 5. The module is imported as `starter_look`: `look` is a parametrize name in
# the tests beside these.
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path

import pytest

from pressless import look as starter_look
from pressless import store

# Their own CSS, holding what would end a rule or a <style> early.
EXTRA = "p { color: red; }\n</style><b>}"


def _changed(layout: str) -> starter_look.Choices:
    """A layout's defaults with every field moved off its default."""
    choices = starter_look.defaults(layout)
    return dataclasses.replace(
        choices, light={**choices.light, "ink": "#123456"},
        dark={**choices.dark, "link": "#abcdef"},
        body_font="mono", heading_font="humanist", text_size="larger", width="wide",
        effects=("reveal", "lift"))


def _files(folder: Path) -> dict[str, bytes | None]:
    found = {}
    for name in (store.LOOK_CHOICES_NAME, store.EXTRA_CSS_NAME, store.STYLE_CODE_NAME):
        path = store.look_path_for(folder, name)
        found[name] = path.read_bytes() if path.is_file() else None
    return found


# ------------------------------------------------------------------ INV-3 ---


@pytest.mark.parametrize("layout", starter_look.LAYOUTS)
def test_read_returns_what_save_wrote(tmp_path, layout):
    """Breaks when a field is dropped or changed between save and read."""
    for choices in (starter_look.defaults(layout), _changed(layout)):
        starter_look.save(tmp_path, choices, EXTRA)
        assert starter_look.read(tmp_path) == choices
        assert starter_look.read_extra(tmp_path) == EXTRA


def test_no_choices_file_reads_as_none(tmp_path):
    """§ 4.4 state 2's test. Breaks when an absent file reads as defaults."""
    assert starter_look.read(tmp_path) is None


def _swap_last_colour(data: dict) -> None:
    light = data["colours"]["light"]
    light["glow"] = light.pop("line")


# One file per row of § 4.1's table, each breaking that row alone.
_BROKEN = {
    "an unknown colour name": _swap_last_colour,
    "a colour not #rrggbb": lambda data: data["colours"]["dark"].update(ink="#12345"),
    "an unknown font": lambda data: data.update(body_font="fancy"),
    "an effect named twice": lambda data: data.update(effects=["lift", "lift"]),
    "version 2": lambda data: data.update(version=2),
    "an extra key": lambda data: data.update(shadow="soft"),
    "an unknown layout": lambda data: data.update(layout="garden"),
    "an unknown text size": lambda data: data.update(text_size="huge"),
    "an unknown width": lambda data: data.update(width="full"),
    "an unknown effect": lambda data: data.update(effects=["spin"]),
}


@pytest.mark.parametrize("edit", _BROKEN.values(), ids=_BROKEN)
def test_a_file_breaking_one_row_is_refused_and_left_alone(tmp_path, edit):
    """Breaks when a field is read with a fallback instead of refused."""
    starter_look.save(tmp_path, starter_look.defaults("sunrise"), "")
    data = json.loads(store.read_look_file(tmp_path, store.LOOK_CHOICES_NAME))
    edit(data)
    store.write_look_file(tmp_path, store.LOOK_CHOICES_NAME, json.dumps(data))
    before = _files(tmp_path)
    with pytest.raises(starter_look.LookUnreadable):
        starter_look.read(tmp_path)
    assert _files(tmp_path) == before


# ------------------------------------------------------------------ INV-4 ---


@pytest.mark.parametrize("layout", starter_look.LAYOUTS)
def test_their_own_css_comes_last_and_verbatim(layout):
    """Breaks when the extra CSS is placed before the layout, or changed."""
    for choices in (starter_look.defaults(layout), _changed(layout)):
        assert starter_look.css(choices, EXTRA).endswith(EXTRA)


def _rules(css: str) -> set[tuple[str, tuple[str, ...]]]:
    """Each rule holding declarations, as (its selector, the at-rules around
    it, outermost first)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found, around, start = set(), [], 0
    for at, char in enumerate(css):
        if char == "{":
            around.append(" ".join(css[start:at].split()))
            start = at + 1
        elif char == "}":
            inner = around.pop()
            if not inner.startswith("@") and css[start:at].strip():
                found.add((inner, tuple(around)))
            start = at + 1
        elif char == ";" and not around:
            start = at + 1
    return found


REDUCED = "@media (prefers-reduced-motion: no-preference)"
SCROLL = "@supports (animation-timeline: view())"


@pytest.mark.parametrize("effect", starter_look.EFFECTS)
def test_every_effect_sits_inside_reduced_motion(effect):
    """Breaks when an effect's rule is emitted outside its media query, or
    reveal's outside its @supports."""
    plain = starter_look.defaults("harbour")
    every = dataclasses.replace(plain, effects=starter_look.EFFECTS)
    without = dataclasses.replace(plain, effects=tuple(
        other for other in starter_look.EFFECTS if other != effect))
    added = _rules(starter_look.css(every, "")) - _rules(starter_look.css(without, ""))
    assert added, effect
    for selector, around in added:
        assert REDUCED in around, (effect, selector)
        if effect == "reveal":
            assert SCROLL in around, selector


# ------------------------------------------------------------------ INV-5 ---


def test_save_makes_the_style_code_from_what_it_wrote(tmp_path):
    """Breaks when style.css is written from different choices than
    choices.json holds."""
    for layout in starter_look.LAYOUTS:
        starter_look.save(tmp_path, _changed(layout), EXTRA)
        assert store.read_style_code(tmp_path) == starter_look.css(
            starter_look.read(tmp_path), starter_look.read_extra(tmp_path))


# ------------------------------------------------------------- PRESS-0314 ---

# What css() made for each layout's defaults with every effect, in 0.10.1.
SAVED_BY_0_10_1 = {
    "sunrise": "149c39acf5d31f03a1b806aefffb4ee44443d86b578728ce05756fe792bba113",
    "meadow": "62b5e8efa6b18d34a71306f116b430e4b627131969beddb1eb603a0b5505a3af",
    "harbour": "6d6b2c7592fc0052976070107d5ff1ba41c4f0f603c4960bcd94b67d3766600e",
}


@pytest.mark.parametrize("layout", starter_look.LAYOUTS)
def test_a_look_saved_by_an_earlier_version_still_reads_as_made_here(layout):
    """PRESS-0314. made_here compares the saved style code with css(), the
    notes' words aside, so any change to css()'s rules makes every saved look
    read as hand-edited: its next save bins a copy and warns. Breaks when
    css() output other than a note's words changes. Do not update the
    hashes: make made_here accept the earlier output first."""
    choices = dataclasses.replace(starter_look.defaults(layout),
                                  effects=starter_look.EFFECTS)
    made = hashlib.sha256(starter_look.css(choices, "").encode("utf-8")).hexdigest()
    assert made == SAVED_BY_0_10_1[layout]


@pytest.mark.parametrize("layout", starter_look.LAYOUTS)
def test_rewording_a_note_keeps_a_saved_look_made_here(layout, tmp_path, monkeypatch):
    """PRESS-0196 § 4.4 state 2, PRESS-0314. The style code saved here is
    0.10.1's, as the hash above proves. Breaks when made_here compares the
    notes' words, so rewording one turns every saved look hand-edited; or
    when it ignores more than those words."""
    choices = dataclasses.replace(starter_look.defaults(layout),
                                  effects=starter_look.EFFECTS)
    starter_look.save(tmp_path, choices, EXTRA)
    saved = store.read_style_code(tmp_path)
    assert hashlib.sha256(saved.removesuffix(EXTRA).encode("utf-8")).hexdigest() == (
        SAVED_BY_0_10_1[layout])
    said = starter_look.say
    monkeypatch.setattr(starter_look, "say",
                        lambda key: f"Reworded {key}." if key.endswith("_note") else said(key))
    assert "Reworded" in starter_look.css(choices, EXTRA)
    assert starter_look.made_here(tmp_path)
    store.write_style_code(tmp_path, saved.replace("--width", "--widths", 1))
    assert not starter_look.made_here(tmp_path)
    store.write_style_code(tmp_path, saved.replace("*/\n", "*/\np{}\n", 1))
    assert not starter_look.made_here(tmp_path)
