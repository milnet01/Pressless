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
    "version true": lambda data: data.update(version=True),
    "version 1.0": lambda data: data.update(version=1.0),
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


def test_colours_in_another_order_read_in_the_looks_order(tmp_path):
    """§ 4.1: exactly the colour names, in any order, since a tool that
    sorts a JSON file's keys changes nothing it means. Breaks when the order
    is refused, or read in the file's order, which would reorder css()."""
    choices = starter_look.defaults("harbour")
    starter_look.save(tmp_path, choices, "")
    data = json.loads(store.read_look_file(tmp_path, store.LOOK_CHOICES_NAME))
    data["colours"]["light"] = dict(reversed(data["colours"]["light"].items()))
    data["colours"]["dark"] = dict(sorted(data["colours"]["dark"].items()))
    store.write_look_file(tmp_path, store.LOOK_CHOICES_NAME, json.dumps(data))
    read = starter_look.read(tmp_path)
    assert read == choices
    assert list(read.light) == list(read.dark) == list(starter_look.COLOURS)
    assert starter_look.made_here(tmp_path)


def test_a_look_file_that_cannot_be_read_is_a_store_failure(tmp_path):
    """Design § Errors: parts raise typed failures. Breaks when the digest
    lets a raw OSError out, which the Look screen shows as the last-resort
    page."""
    starter_look.save(tmp_path, starter_look.defaults("sunrise"), "")
    style = store.style_code_path(tmp_path)
    style.unlink()
    style.mkdir()
    with pytest.raises(store.StoreError):
        starter_look.digest(tmp_path)


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

# What css() made for each layout's defaults with every effect: 0.10.1's for
# the three layouts it had (PRESS-0359 INV-4), 1.0.0's for the five it added.
SAVED_BEFORE = {
    "sunrise": "149c39acf5d31f03a1b806aefffb4ee44443d86b578728ce05756fe792bba113",
    "meadow": "62b5e8efa6b18d34a71306f116b430e4b627131969beddb1eb603a0b5505a3af",
    "harbour": "6d6b2c7592fc0052976070107d5ff1ba41c4f0f603c4960bcd94b67d3766600e",
    "studio": "deade1ebe7f27f90a3d6f285742bb74b9af5317db3474db1cfb71974821b34e9",
    "market": "07521fd964aac7bf0db271f014a75b2e5244098493893ae887a9e1affbe8788d",
    "stage": "49cb807fe21ea684779df9212c7f55362800f87a213534f32d394d19ef0f6c8a",
    "commons": "3f3c559025ec6437748cb5483eab7e289ef194137c94bcd04c319d1676a3877b",
    "letter": "ac2acf20752a38b4a8493b60dd7bfe2586a4086866e861c9652b135419152d59",
}
# The rules css() has gained since, each written out: removing them gives
# back what those versions saved.
ADDED_SINCE = ("footer.site a:focus-visible { outline-color: var(--foot-link); }\n",)


def _made_before(choices: starter_look.Choices, extra: str) -> str:
    made = starter_look.css(choices, extra)
    for rule in ADDED_SINCE:
        assert made.count(rule) == 1, rule
        made = made.replace(rule, "", 1)
    return made


@pytest.mark.parametrize("layout", SAVED_BEFORE)
def test_a_look_saved_by_an_earlier_version_still_reads_as_made_here(layout):
    """PRESS-0314. made_here compares the saved style code with css(), the
    notes' words aside, and accepts it without the rules added since, so a
    change to css() leaves every saved look made here. Breaks when css()
    output other than a note's words and ADDED_SINCE changes. Do not update
    the hashes: make made_here accept the earlier output first."""
    choices = dataclasses.replace(starter_look.defaults(layout),
                                  effects=starter_look.EFFECTS)
    made = hashlib.sha256(_made_before(choices, "").encode("utf-8")).hexdigest()
    assert made == SAVED_BEFORE[layout]


@pytest.mark.parametrize("layout", SAVED_BEFORE)
def test_rewording_a_note_keeps_a_saved_look_made_here(layout, tmp_path, monkeypatch):
    """PRESS-0196 § 4.4 state 2, PRESS-0314. The style code saved here is
    the earlier version's, as the hash above proves. Breaks when made_here
    compares the notes' words, so rewording one turns every saved look
    hand-edited; when it refuses the earlier output or this version's; or
    when it ignores more than those words and the added rules."""
    choices = dataclasses.replace(starter_look.defaults(layout),
                                  effects=starter_look.EFFECTS)
    starter_look.save(tmp_path, choices, EXTRA)
    assert starter_look.made_here(tmp_path)
    saved = _made_before(choices, EXTRA)
    store.write_style_code(tmp_path, saved)
    assert hashlib.sha256(saved.removesuffix(EXTRA).encode("utf-8")).hexdigest() == (
        SAVED_BEFORE[layout])
    said = starter_look.say
    monkeypatch.setattr(starter_look, "say",
                        lambda key: f"Reworded {key}." if key.endswith("_note") else said(key))
    assert "Reworded" in starter_look.css(choices, EXTRA)
    assert starter_look.made_here(tmp_path)
    store.write_style_code(tmp_path, saved.replace("--width", "--widths", 1))
    assert not starter_look.made_here(tmp_path)
    store.write_style_code(tmp_path, saved.replace("*/\n", "*/\np{}\n", 1))
    assert not starter_look.made_here(tmp_path)


@pytest.mark.parametrize("layout", starter_look.LAYOUTS)
def test_a_footer_link_shows_its_focus_ring_on_the_footer(layout):
    """PRESS-0239: a visible focus ring. Breaks when a footer link's ring
    takes `ink`, which three styles paint their footer in, instead of
    `foot-link`, which TEXT_PAIRS holds to contrast with the footer."""
    assert ("foot-link", "foot") in starter_look.TEXT_PAIRS
    css = starter_look.css(starter_look.defaults(layout), "")
    assert re.search(r"footer\.site a:focus-visible \{[^}]*"
                     r"outline-color: var\(--foot-link\)", css)


# ------------------------------------------------------------- PRESS-0359 ---
# Each test names its invariant from
# docs/specs/PRESS-0359-layouts-and-colour-styles.md § 5.


def test_the_layouts_are_the_eight_in_order():
    """PRESS-0359 INV-1. Breaks when a layout is dropped, renamed or moved:
    the keys are saved in sites' files, and the first is the default."""
    assert starter_look.LAYOUTS == ("sunrise", "meadow", "harbour", "studio", "market",
                                    "stage", "commons", "letter")


@pytest.mark.parametrize("layout", starter_look.LAYOUTS)
def test_every_layout_saves_and_reads_back(tmp_path, layout):
    """PRESS-0359 INV-1. Breaks when a layout lacks its rules, width or
    heading font, so defaults or css raises; or from_json refuses one."""
    choices = starter_look.defaults(layout)
    starter_look.save(tmp_path, choices, "")
    assert starter_look.read(tmp_path) == choices


@pytest.mark.parametrize("layout", starter_look.LAYOUTS)
def test_each_layouts_defaults_wear_its_own_style(layout):
    """PRESS-0359 INV-3. Breaks when a layout keeps colours outside the
    eleven styles."""
    style = starter_look.OWN_STYLE[layout]
    assert style in starter_look.STYLES
    choices = starter_look.defaults(layout)
    assert choices.light == starter_look.palette(style, False)
    assert choices.dark == starter_look.palette(style, True)


def test_a_warned_ratio_is_never_shown_at_the_bar(monkeypatch):
    """§ 3 decision 4. Breaks when 4.496:1, warned about as under 4.5:1, is
    rounded up and shown as 4.50."""
    monkeypatch.setattr(starter_look, "contrast", lambda one, two: 4.496)
    found = starter_look.warnings(starter_look.defaults("sunrise"))
    assert found
    assert {ratio for _scheme, _text, _ground, ratio in found} == {4.49}
