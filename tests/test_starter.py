"""PRESS-0126: the plain starter site (docs/specs/PRESS-0126-starter-site.md).

The marker's name is written out here rather than imported, so a module
naming another file fails.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_publishing import KEY, _github, _settings
from test_themes import _contrast

from pressless import builder, publishing, starter, store
from pressless import look as starter_look

NAME = 'A <b> & "Co"'


def _filled(tmp_path: Path, name: str = "A Site") -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    starter.fill(folder, name)
    return folder


def _built(folder: Path, tmp_path: Path) -> Path:
    into = tmp_path / "site"
    builder.build(folder, _settings(folder), into)
    return into


def test_a_filled_starter_builds(tmp_path):
    """INV-2. Breaks when a furniture file is missing, or a marker pair does
    not pair."""
    into = _built(_filled(tmp_path), tmp_path)
    for relative in ("index.html", "pages/about.html", "look/style.css"):
        assert (into / relative).is_file(), relative


def test_fill_writes_only_what_is_absent(tmp_path, monkeypatch):
    """INV-3: never over a file the Store holds, and the marker before any
    Store file. Breaks when the sentinel header is replaced, or no marker is
    left by the interrupted fill."""
    folder = tmp_path / "data"
    folder.mkdir()
    mine = "<header>mine {{NAVIGATION}}</header>\n"
    store.write_html(folder, store.FURNITURE_FOLDER, "header", mine)
    starter.fill(folder, "A Site")
    assert store.read_html(store.html_path_for(folder, store.FURNITURE_FOLDER, "header")) == mine
    assert store.html_path_for(folder, store.PAGES_FOLDER, "about").is_file()

    other = tmp_path / "other"
    other.mkdir()

    def refuse(*args, **kwargs):
        raise store.StoreError("the disk is full")

    monkeypatch.setattr(store, "write_html", refuse)
    with pytest.raises(store.StoreError):
        starter.fill(other, "A Site")
    assert (other / "starter-unpublished").is_file()
    assert not store.holds_a_site(other)


def test_the_name_is_escaped(tmp_path):
    """INV-4. Breaks when the name is written unescaped."""
    page = (_built(_filled(tmp_path, NAME), tmp_path) / "index.html").read_text(encoding="utf-8")
    assert "A &lt;b&gt; &amp; &quot;Co&quot;" in page
    assert "<b>" not in page


def test_the_menu_is_home_and_about(tmp_path):
    """INV-5. Breaks when a journal link is left in, or data-nav and the
    marker's page disagree."""
    folder = _filled(tmp_path)
    menu = store.read_html(store.html_path_for(folder, store.FURNITURE_FOLDER, "navigation"))
    assert re.findall(r'data-nav="([^"]*)"', menu) == ["Home", "about"]
    assert "blog/" not in menu
    into = _built(folder, tmp_path)
    home = (into / "index.html").read_text(encoding="utf-8")
    about = (into / "pages" / "about.html").read_text(encoding="utf-8")
    assert re.search(r'<a [^>]*data-nav="Home" aria-current="page"', home)
    assert re.search(r'<a [^>]*data-nav="about" aria-current="page"', about)


def test_the_starter_publishes_with_no_entries(tmp_path):
    """INV-16. Breaks when the fill leaves the journal on."""
    folder = _filled(tmp_path)
    github = _github()
    publishing.publish(folder, _settings(folder), KEY, entry=None, transport=github)
    assert github.requests
    assert not (folder / "starter-unpublished").exists()


def test_the_furniture_names_the_site_by_placeholder(tmp_path):
    """PRESS-0213 INV-10 (docs/specs/PRESS-0213-site-identity.md § 4.6): a
    rename in the Store reaches the header and footer with no file rewritten.

    Breaks when fill writes the name into either file."""
    folder = _filled(tmp_path, "Quite Unusual Name")
    header = store.read_html(store.html_path_for(folder, store.FURNITURE_FOLDER, "header"))
    footer = store.read_html(store.html_path_for(folder, store.FURNITURE_FOLDER, "footer"))
    for text in (header, footer):
        assert "{{SITE_NAME}}" in text
        assert "Quite Unusual Name" not in text
    assert "{{SITE_DESCRIPTION}}" in header


def test_each_look_writes_its_own_style(tmp_path):
    """PRESS-0239: each look fills its own style code, every one styling the
    entry body the Builder writes; a look Pressless does not have fills the
    first. Breaks when two looks share a stylesheet, or a forged look fails."""
    styles = {}
    for look in (*starter.LOOKS, "nonsense"):
        folder = tmp_path / look
        folder.mkdir()
        starter.fill(folder, "A Site", look)
        styles[look] = store.read_style_code(folder)
    assert len({styles[look] for look in starter.LOOKS}) == len(starter.LOOKS) == 3
    assert styles["nonsense"] == styles[starter.LOOKS[0]]
    for look in starter.LOOKS:
        assert ".prose" in styles[look], look


# PRESS-0248: the text pairs each look's rules put together, written out here
# rather than read from look.py, so a look cannot pass by dropping a pair.
# The floor is the one PRESS-0239 set, 7:1 (WCAG AAA): the first user is
# partially sighted.
_TEXT_PAIRS = (("ink", "paper"), ("soft", "paper"), ("link", "paper"), ("heading", "paper"),
               ("on-band", "band"), ("band-soft", "band"),
               ("on-foot", "foot"), ("foot-link", "foot"))
_FLOOR = 7.0


@pytest.mark.parametrize("dark", (False, True), ids=("light", "dark"))
@pytest.mark.parametrize("look", starter.LOOKS)
def test_every_look_reads_at_seven_to_one_in_light_and_dark(look, dark):
    """Breaks when a text colour falls below 7:1 on its background in either
    scheme."""
    colours = starter_look.palette(look, dark)
    for text, ground in _TEXT_PAIRS:
        ratio = _contrast(colours[text], colours[ground])
        assert ratio >= _FLOOR, f"{look} {text} on {ground}: {ratio:.2f}"


def test_meadow_footer_sits_on_the_paper():
    """Meadow's footer paints `foot` since PRESS-0196, where it painted nothing
    over the paper before; its defaults keep the two equal, so the look is
    unchanged (PRESS-0196 INV-1). Breaks when the two part."""
    for dark in (False, True):
        colours = starter_look.palette("meadow", dark)
        assert colours["foot"] == colours["paper"]


@pytest.mark.parametrize("look", starter.LOOKS)
def test_each_look_turns_dark_with_the_computer_and_names_no_other_colour(tmp_path, look):
    """PRESS-0248: the style code carries a dark set of every colour, and the
    rules outside the two sets name only those colours. Breaks when a rule
    keeps a colour of its own, which the dark set would not reach."""
    starter.fill(tmp_path, "A Site", look)
    css = store.read_style_code(tmp_path)
    light = re.search(r"^:root \{ color-scheme: light dark; ([^}]*) \}$", css, re.M)
    dark = re.search(r"^@media \(prefers-color-scheme: dark\) \{ :root \{ ([^}]*) \} \}$",
                     css, re.M)
    assert light and dark
    for declared in (light.group(1), dark.group(1)):
        assert re.findall(r"--([a-z-]+):", declared) == list(starter_look.COLOURS)
    rules = css.replace(light.group(0), "").replace(dark.group(0), "")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", rules)
    # PRESS-0196 § 4.2: the four measures beside the colours, and nothing else.
    measures = {"body-font", "heading-font", "text-size", "width"}
    assert set(re.findall(r"var\(--([a-z-]+)\)", rules)) <= set(starter_look.COLOURS) | measures
