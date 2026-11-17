# The Look screen (PRESS-0196).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0196-site-look.md
# § 5. Route names are written out rather than imported, and every server starts
# inside the test that uses it, as in tests/test_editor.py. The look module is
# imported as `starter_look`: `look` is a parametrize name in the tests beside
# these.
from __future__ import annotations

import contextlib
import dataclasses
import html
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_editor import _binned, _Browser, _folder, _said

from pressless import builder, editor, face, look_screen, settings, starter, store
from pressless import look as starter_look

LOOK_FILES = (store.LOOK_CHOICES_NAME, store.EXTRA_CSS_NAME, store.STYLE_CODE_NAME)


@contextlib.contextmanager
def _served(folder: Path) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        look_screen.register(served, folder)
        yield _Browser(served)
    finally:
        served.stop()


def _site(tmp_path: Path, layout: str = "sunrise") -> Path:
    """A set-up folder holding the starter site, its look saved by fill."""
    folder = _folder(tmp_path)
    starter.fill(folder, "A Site", layout)
    return folder


def _form(choices: starter_look.Choices, extra: str, base: str) -> dict[str, str]:
    """What the screen's form posts for these choices."""
    form = {"base": base, "layout": choices.layout, "body_font": choices.body_font,
            "heading_font": choices.heading_font, "text_size": choices.text_size,
            "width": choices.width, "extra": extra}
    for scheme, colours in (("light", choices.light), ("dark", choices.dark)):
        form.update({f"{scheme}.{name}": value for name, value in colours.items()})
    form.update({f"effect.{name}": "on" for name in choices.effects})
    return form


def _files(folder: Path) -> dict[str, bytes | None]:
    found = {}
    for name in LOOK_FILES:
        path = store.look_path_for(folder, name)
        found[name] = path.read_bytes() if path.is_file() else None
    return found


def _base(page: str) -> str:
    found = re.search(r'name="base" value="([0-9a-f]{64})"', page)
    assert found, "the screen carries no digest"
    return found.group(1)


# ------------------------------------------------------------------ INV-6 ---


def test_hard_to_read_text_is_warned_about_and_still_saved(tmp_path):
    """Breaks when the warning list omits a pair, or the save refuses."""
    folder = _site(tmp_path)
    plain = starter_look.defaults("sunrise")
    unreadable = dataclasses.replace(plain, light={**plain.light, "ink": plain.light["paper"]},
                                     dark={**plain.dark, "ink": plain.dark["paper"]})
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        form = _form(unreadable, "", _base(page))
        status, _, text = browser.request("POST", "/look/preview", form)
        assert status == 200, text
        warned = {(scheme, colour, ground)
                  for scheme, colour, ground, _ in json.loads(text)["warnings"]}
        assert {("light", "ink", "paper"), ("dark", "ink", "paper")} <= warned
        assert store.read_look_file(folder, store.LOOK_CHOICES_NAME) == starter_look.to_json(plain)

        status, headers, _ = browser.request("POST", "/look/save", form)
        assert (status, headers.get("Location")) == (303, "/look?saved=1")
        assert starter_look.read(folder) == unreadable
        _, _, page = browser.request("GET", "/look?saved=1")
    for scheme in ("light", "dark"):
        slot = re.search(rf'data-warn="{scheme}\.ink"[^>]*>([^<]*)<', page)
        assert slot and "1.00:1" in slot.group(1), scheme


# ------------------------------------------------------------------ INV-7 ---


def test_saving_over_hand_made_style_code_keeps_a_copy(tmp_path, monkeypatch):
    """Breaks when the old stylesheet is overwritten without a copy, or moved
    away before the new one is written."""
    folder = _site(tmp_path)
    mine = "/* made by hand */ body { color: teal; }\n"
    store.write_style_code(folder, mine)
    written = []
    real = store.write_look_file

    def watched(at: Path, name: str, text: str) -> Path:
        # Every write look.save makes, the stylesheet's own included, finds
        # the hand-made one still in place.
        written.append(store.read_style_code(at))
        return real(at, name, text)

    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        assert "a copy of the current one in the bin" in page
        monkeypatch.setattr(store, "write_look_file", watched)
        status, _, text = browser.request(
            "POST", "/look/save", _form(starter_look.defaults("meadow"), "", _base(page)))
    assert status == 303, text
    assert written and set(written) == {mine}
    assert store.read_style_code(folder) == starter_look.css(starter_look.defaults("meadow"), "")
    copies = [path for path in (folder / "bin").rglob("*") if path.is_file()]
    assert [path.read_text(encoding="utf-8") for path in copies] == [mine]


def test_a_site_from_before_the_look_screen_starts_from_a_layout(tmp_path):
    """§ 4.4 state 2: no choices.json, so the panel shows the defaults of the
    layout picked. Breaks when the layout asked for is not the one shown."""
    folder = _site(tmp_path)
    store.look_path_for(folder, store.LOOK_CHOICES_NAME).unlink()
    harbour = starter_look.defaults("harbour")
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look?layout=harbour")
    assert re.search(r'name="layout" value="harbour" checked', page)
    assert f'name="light.paper" value="{harbour.light["paper"]}"' in page
    assert "data-restart" in page and "a copy of the current one in the bin" in page


# The screen's script runs in a browser; Node runs it against a stand-in form
# holding the fields it sets, so a layout picked can be watched.
_NODE = shutil.which("node")
_RESTART_HARNESS = """const fields = {};
const field = (name, value) => (fields[name] = {name, value, checked: false, dataset: {}});
for (const scheme of ["light", "dark"]) {
  for (const name of COLOURS) field(scheme + "." + name, "#000000").type = "color";
}
for (const name of ["body_font", "heading_font", "text_size", "width"]) field(name, "");
for (const name of EFFECTS) field("effect." + name, "on").checked = true;
field("extra", "p { color: red; }");
let typed = null;
const named = /^(?:input|select)\\[name="?([^"\\]]+)"?\\]$/;
const form = {
  dataset: {restart: RESTART},
  querySelector: (selector) => (named.exec(selector) || [])[1] in fields
    ? fields[named.exec(selector)[1]] : null,
  querySelectorAll: (selector) => selector === 'input[name^="effect."]'
    ? Object.values(fields).filter((one) => one.name.startsWith("effect.")) : [],
  addEventListener: (kind, run) => { if (kind === "input") typed = run; },
};
const window = {location: {href: "/look"}};
const document = {getElementById: (id) => id === "look" ? form
  : {addEventListener() {}, textContent: ""}};
const say = (key) => key;
const fetch = () => new Promise(() => {});
SCRIPT
typed({target: {name: "layout", value: "harbour", dataset: {}}});
const values = {};
for (const [name, one] of Object.entries(fields)) {
  values[name] = name.startsWith("effect.") ? one.checked : one.value;
}
process.stdout.write(JSON.stringify({href: window.location.href, values}));
process.exit(0);
"""


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_picking_a_layout_to_start_from_keeps_the_css_typed(tmp_path):
    """§ 4.4 state 2. Breaks when picking a layout reloads the screen, which
    loses the CSS typed below it, or when the fields do not take the
    layout's own choices."""
    folder = _site(tmp_path)
    store.look_path_for(folder, store.LOOK_CHOICES_NAME).unlink()
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
    restart = re.search(r'<form id="look"[^>]*\sdata-restart="([^"]*)"', page)
    assert restart, "the form carries no layouts to start from"
    script = look_screen._SCRIPT
    assert f"<script>{script}</script>" in page
    harness = tmp_path / "restart.js"
    harness.write_text(
        _RESTART_HARNESS.replace("COLOURS", json.dumps(starter_look.COLOURS))
        .replace("EFFECTS", json.dumps(starter_look.EFFECTS))
        .replace("RESTART", json.dumps(html.unescape(restart.group(1))))
        .replace("SCRIPT", script), encoding="utf-8")
    run = subprocess.run([_NODE, str(harness)], capture_output=True,  # noqa: S603
                         check=True, timeout=30)
    shown = json.loads(run.stdout)
    harbour = starter_look.defaults("harbour")
    assert shown["href"] == "/look"
    assert shown["values"]["extra"] == "p { color: red; }"
    assert {name: shown["values"][f"light.{name}"] for name in starter_look.COLOURS} == (
        harbour.light)
    assert {name: shown["values"][f"dark.{name}"] for name in starter_look.COLOURS} == (
        harbour.dark)
    for name in ("body_font", "heading_font", "text_size", "width"):
        assert shown["values"][name] == getattr(harbour, name), name
    assert [name for name in starter_look.EFFECTS if shown["values"][f"effect.{name}"]] == (
        list(harbour.effects))


# ------------------------------------------------------------------ INV-8 ---


def test_a_look_changed_elsewhere_is_not_saved_over(tmp_path):
    """Breaks when the save skips the digest check, whichever file changed."""
    folder = _site(tmp_path)
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        store.write_look_file(folder, store.EXTRA_CSS_NAME, "h1 { color: red; }")
        before = _files(folder)
        status, _, text = browser.request(
            "POST", "/look/save", _form(starter_look.defaults("harbour"), "", _base(page)))
    assert status == 409
    assert _said(editor.ChangedElsewhere) in text
    assert _files(folder) == before
    assert _binned(folder) == []


# --------------------------------------------- PRESS-0276 INV-4 to INV-8 ---
#
# A site whose pages link their own stylesheets (docs/specs/
# PRESS-0276-imported-site-look.md § 4.3). The addresses are written out.

OWN_PAGE = ('<html><head>\n<link rel="stylesheet" href="assets/site.css">\n'
            '<link rel="stylesheet" href="assets/blog.css">\n</head>\n'
            '<body><!-- HEADER:START --><!-- HEADER:END --><p>home</p></body></html>\n')


def _own(tmp_path: Path) -> Path:
    """A set-up folder whose one page links the live site's assets pair."""
    folder = _folder(tmp_path)
    store.write_html(folder, store.PAGES_FOLDER, "index", OWN_PAGE)
    return folder


def _routed(choices: starter_look.Choices, extra: str, base: str, route: str) -> dict[str, str]:
    return {**_form(choices, extra, base), "route": route}


def test_css_on_top_saves_only_the_extra_css(tmp_path):
    """INV-4. Breaks when choices.json is binned, or style.css is overwritten
    rather than moved to the bin."""
    folder = _own(tmp_path)
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        assert re.search(r'type="radio" name="route" value="own" checked', page)
        status, _, text = browser.request("POST", "/look/save", _routed(
            starter_look.defaults("sunrise"), "h1 { color: red; }", _base(page), "own"))
    assert status == 303, text
    assert _files(folder) == {store.LOOK_CHOICES_NAME: None,
                              store.EXTRA_CSS_NAME: b"h1 { color: red; }",
                              store.STYLE_CODE_NAME: None}
    assert _binned(folder) == []

    starter_look.save(folder, starter_look.defaults("harbour"), "")
    made = store.read_style_code(folder)
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        assert re.search(r'type="radio" name="route" value="pressless" checked', page)
        status, _, text = browser.request("POST", "/look/save", _routed(
            starter_look.defaults("harbour"), "p { margin: 0; }", _base(page), "own"))
    assert status == 303, text
    found = _files(folder)
    assert found[store.STYLE_CODE_NAME] is None
    assert found[store.EXTRA_CSS_NAME] == b"p { margin: 0; }"
    assert starter_look.read(folder) == starter_look.defaults("harbour")
    copies = [path for path in (folder / "bin").rglob("*") if path.is_file()]
    assert [path.read_text(encoding="utf-8") for path in copies] == [made]


def test_a_site_with_its_own_stylesheets_can_take_a_pressless_look(tmp_path):
    """INV-5. Breaks when the save is refused as PRESS-0196 INV-9 refused it."""
    folder = _own(tmp_path)
    meadow = starter_look.defaults("meadow")
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        status, _, text = browser.request(
            "POST", "/look/save", _routed(meadow, "", _base(page), "pressless"))
    assert status == 303, text
    assert starter_look.read(folder) == meadow
    assert store.read_style_code(folder) == starter_look.css(meadow, "")
    assert _binned(folder) == []
    built = tmp_path / "built"
    builder.build(folder, settings.load(folder), built)
    home = (built / "index.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="look/style.css">' in home
    assert "assets/" not in home


def test_either_route_with_a_stale_digest_writes_nothing(tmp_path):
    """INV-6. Breaks when the own route skips the digest check."""
    folder = _own(tmp_path)
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        store.write_look_file(folder, store.EXTRA_CSS_NAME, "h1 { color: red; }")
        before = _files(folder)
        for route in ("own", "pressless"):
            status, _, text = browser.request("POST", "/look/save", _routed(
                starter_look.defaults("sunrise"), "p {}", _base(page), route))
            assert status == 409, route
            assert _said(editor.ChangedElsewhere) in text, route
    assert _files(folder) == before


def test_the_own_route_previews_the_extra_css_on_the_sites_own(tmp_path):
    """INV-7. Breaks when the reply sends the Pressless stylesheet for route own."""
    folder = _own(tmp_path)
    base = starter_look.digest(folder)
    with _served(folder) as browser:
        status, _, text = browser.request("POST", "/look/preview", _routed(
            starter_look.defaults("sunrise"), "h1 { color: red; }", base, "own"))
    assert status == 200, text
    assert json.loads(text) == {"css": "h1 { color: red; }", "warnings": [],
                                "sheets": ["/preview/assets/site.css",
                                           "/preview/assets/blog.css"]}
    assert starter_look.digest(folder) == base


def test_a_starter_site_offers_no_route(tmp_path):
    """INV-8. Breaks when the choice is shown on a starter site."""
    folder = _site(tmp_path)
    form = _routed(starter_look.defaults("sunrise"), "", starter_look.digest(folder), "own")
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        assert 'type="radio" name="route"' not in page
        before = _files(folder)
        for route in ("/look/preview", "/look/save"):
            status, _, text = browser.request("POST", route, form)
            assert status == 409, route
            assert _said(look_screen.LookRefused) in text, route
    assert _files(folder) == before


def test_a_site_before_setup_offers_no_route(tmp_path):
    """PRESS-0368. A site setup has not written yet holds no stylesheets of
    its own to keep, so it gets the Pressless look alone. Breaks when the
    choice, opening on keeping them, is shown on an empty site."""
    folder = tmp_path / "empty"
    folder.mkdir()
    with _served(folder) as browser:
        status, _, page = browser.request("GET", "/look")
    assert status == 200, page
    assert 'type="radio" name="route"' not in page


# --------------------------------------------------------------- § 6, § 4.1 ---


def test_unreadable_choices_show_no_panel_and_are_not_saved_over(tmp_path):
    """§ 6: a choices.json Pressless cannot read stops the screen, and no
    save writes over it. Breaks when the save reads around it."""
    folder = _site(tmp_path)
    store.write_look_file(folder, store.LOOK_CHOICES_NAME, '{"version": 2}')
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        assert 'id="look"' not in page
        assert _said(starter_look.LookUnreadable) in page
        base = starter_look.digest(folder)
        before = _files(folder)
        status, _, _ = browser.request(
            "POST", "/look/save", _form(starter_look.defaults("sunrise"), "", base))
    assert status == 409
    assert _files(folder) == before


# ----------------------------------------------------------------- INV-10 ---


def test_the_screen_links_none_of_the_sites_stylesheets(tmp_path):
    """Breaks when the screen links builder.stylesheets as the editors do."""
    folder = _site(tmp_path)
    with _served(folder) as browser:
        status, _, page = browser.request("GET", "/look")
    assert status == 200
    frame = re.search(r'<iframe id="preview"[^>]*\ssrc="([^"]*)"', page)
    assert frame and frame.group(1).startswith(editor.PREVIEW_ADDRESS), "no preview frame"
    outside = page.replace(frame.group(0), "")
    assert not re.search(r"/preview/(?:look|assets)/", outside)
    assert "@import" not in outside


def test_the_bar_links_to_the_look_screen(tmp_path):
    """§ 4.4. Breaks when the bar loses the link."""
    with _served(_folder(tmp_path)) as browser:
        _, _, page = browser.request("GET", "/look")
    bar = page.split('<header class="bar">', 1)[1].split("</header>", 1)[0]
    assert ('<a href="/journal">Journal</a><a href="/look">Look</a>'
            '<a href="/files">Files</a>') in bar


def test_the_screen_offers_every_choice_look_makes():
    """Breaks when look.py gains a colour, font, size, width or effect and
    the screen's words lists, kept as literals for INV-4, do not."""
    lists = {
        "colour": (look_screen._COLOUR_WORDS, starter_look.COLOURS),
        "font": (look_screen._FONT_WORDS, starter_look.FONTS),
        "size": (look_screen._SIZE_WORDS, starter_look.TEXT_SIZES),
        "width": (look_screen._WIDTH_WORDS, starter_look.WIDTHS),
        "effect": (look_screen._EFFECT_WORDS, starter_look.EFFECTS),
        "style": (look_screen._STYLE_WORDS, starter_look.STYLES),
    }
    for kind, (shown, made) in lists.items():
        assert list(shown) == list(made), kind
        assert all(key == f"look_screen.{kind}.{name}" for name, key in shown.items()), kind


# --------------------------------------------------------------- PRESS-0352 ---


def test_a_saved_look_offers_each_layouts_own_colours(tmp_path: Path) -> None:
    """PRESS-0352: once a look is saved, choosing a layout keeps its colours,
    the screen says so, and its button carries every layout's own colours.
    Breaks when the button is missing, or a palette differs from the layout's."""
    folder = _site(tmp_path, "harbour")
    with _served(folder) as browser:
        page = browser.request("GET", "/look")[2]
    assert "Choosing another layout keeps your colours." in page
    found = re.search(r'data-own-colours="([^"]*)"', page)
    assert found, "no button for a layout's own colours"
    palettes = json.loads(found.group(1).replace("&quot;", '"'))
    assert set(palettes) == set(starter_look.LAYOUTS)
    for layout in starter_look.LAYOUTS:
        own = starter_look.defaults(layout)
        assert palettes[layout] == {"light": own.light, "dark": own.dark}, layout


# --------------------------------------------------------------- PRESS-0359 ---
# Each test names its invariant from
# docs/specs/PRESS-0359-layouts-and-colour-styles.md § 5.


def _marked_styles(page: str) -> list[str]:
    return re.findall(r'name="style" value="([a-z]+)"[^>]* checked', page)


def test_a_posted_style_reaches_the_choices_only_as_the_boxes_colours(tmp_path: Path) -> None:
    """PRESS-0359 INV-6. Breaks when the save takes colours from the style
    instead of the boxes, or writes the style's name."""
    folder = _site(tmp_path)
    posted = starter_look.defaults("sunrise")
    assert posted.light != starter_look.palette("night", False)
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        form = {**_form(posted, "", _base(page)), "style": "night"}
        status, _, text = browser.request("POST", "/look/save", form)
    assert status == 303, text
    saved = json.loads(store.read_look_file(folder, store.LOOK_CHOICES_NAME))
    assert sorted(saved) == sorted(starter_look._FIELDS)
    assert saved["colours"] == {"light": posted.light, "dark": posted.dark}


def test_the_style_whose_colours_fill_the_boxes_is_marked(tmp_path: Path) -> None:
    """PRESS-0359 INV-7. Breaks when the mark compares the light set only, or
    marks the layout's own style regardless of the boxes."""
    folder = _site(tmp_path)
    market = starter_look.defaults("market")
    starter_look.save(folder, market, "")
    with _served(folder) as browser:
        _, _, page = browser.request("GET", "/look")
        assert _marked_styles(page) == ["slate"]
        changed = dataclasses.replace(market, dark={**market.dark, "ink": "#fefefe"})
        starter_look.save(folder, changed, "")
        _, _, page = browser.request("GET", "/look")
    assert _marked_styles(page) == []
    assert len(re.findall(r'name="style" value=', page)) == len(starter_look.STYLES)


def test_the_unreadable_look_has_its_sentence_without_undo():
    """The Look screen shows an unreadable choices.json in its own words. The
    sentence is registered in the Face's own table, so it does not depend on
    undo, which never raises it, being imported first.

    Breaks when the registration lives in a module the screen never imports."""
    probe = ("import sys; from pressless import face, look; "
             "assert 'pressless.undo' not in sys.modules; "
             "assert look.LookUnreadable in face.SENTENCES")
    # Run from src/, which `python -c` puts first on the path.
    ran = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,  # noqa: S603
                         check=False, cwd=Path(face.__file__).resolve().parents[1])
    assert ran.returncode == 0, ran.stderr
