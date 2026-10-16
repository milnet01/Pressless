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
import json
import re
from collections.abc import Iterator
from pathlib import Path

from test_editor import _binned, _Browser, _folder, _said

from pressless import editor, face, look_screen, starter, store
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


# ------------------------------------------------------------------ INV-9 ---


def test_a_site_with_no_style_code_is_left_alone(tmp_path):
    """Breaks when a save creates style code on an imported site."""
    folder = _folder(tmp_path)
    form = _form(starter_look.defaults("sunrise"), "", starter_look.digest(folder))
    with _served(folder) as browser:
        status, _, page = browser.request("GET", "/look")
        assert status == 200
        assert 'id="look"' not in page and "<iframe" not in page
        for route in ("/look/preview", "/look/save"):
            status, _, text = browser.request("POST", route, form)
            assert status == 409, route
            assert _said(look_screen.NoStyleCode) in text, route
    assert not (folder / store.LOOK_FOLDER).exists()


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
    assert '<a href="/setup">Settings</a><a href="/look">Look</a>' in bar
