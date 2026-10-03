"""PRESS-0126: the plain starter site (docs/specs/PRESS-0126-starter-site.md).

The marker's name is written out here rather than imported, so a module
naming another file fails.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_publishing import KEY, _github, _settings

from pressless import builder, publishing, starter, store

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
