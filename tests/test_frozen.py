# The 1.0.0 freeze (PRESS-0138): shapes an upgrade must not change.
#
# docs/standards/versioning-overrides.md § The breaking surfaces lists every
# surface and names the test that pins each one. This file holds the pins that
# had no other home. Each compares against a literal copy written out here,
# never a name imported from the module under test (docs/working-here.md
# § Writing or changing tests): a shared name lets both sides move together
# and the test stay green.
from __future__ import annotations

import json
import sys
from datetime import date

import pytest
from test_settings import _valid_mapping, _write

from pressless import credentials, look, marks, settings, store

# ----------------------------------------------------------------- marks ----

# Every mark that exists, as the writer types it: name, kind, opening and
# closing text. Adding a row is a breach too -- ADR-0001 keeps text the parser
# does not know byte for byte, so a new mark restyles archive text that has
# rendered literally for years.
_MARKS = (
    ("bold", "wrap", "**", "**"),
    ("italic", "wrap", "*", "*"),
    ("accent", "wrap", "{accent}", "{/}"),
    ("muted", "wrap", "{muted}", "{/}"),
    ("colour", "wrap", "{", "{/}"),
    ("rainbow", "wrap", "{rainbow}", "{/}"),
    ("photo", "block", "{photo:", None),
    ("link", "wrap", "{link:", "{/}"),
    ("quote", "prefix", ">", None),
    ("years_since", "value", "{years_since:", None),
)

# What each mark means: one input per mark, and the HTML it has always made.
_RENDERED = {
    "**said**": "<p><strong>said</strong></p>",
    "*quiet*": "<p><em>quiet</em></p>",
    "{accent}his{/}": '<p><span style="color:var(--accent)">his</span></p>',
    "{muted}aside{/}": '<p><span style="color:var(--muted)">aside</span></p>',
    "{#c0453a}red{/}": '<p><span style="color:#c0453a">red</span></p>',
    "{rainbow}ab{/}": ('<p><span class="mk-rainbow" style="--mk-i:0">a</span>'
                       '<span class="mk-rainbow" style="--mk-i:1">b</span></p>'),
    "{photo: seaside.jpg | Late light}": (
        '<figure><img src="photographs/seaside.jpg" alt="Late light">'
        "<figcaption>Late light</figcaption></figure>"),
    "{link: https://example.org}words{/}": '<p><a href="https://example.org">words</a></p>',
    "> someone else": "<blockquote><p>someone else</p></blockquote>",
    "{years_since: 2010-01-01}": "<p>16</p>",
    # ADR-0001: every newline in a body is a line break; a blank line ends a
    # paragraph.
    "one\ntwo\n\nthree": "<p>one<br>\ntwo</p>\n<p>three</p>",
}


def test_the_marks_are_the_frozen_set():
    """Breaks when a mark is added, removed, renamed, or typed differently."""
    actual = tuple((m.name, m.kind, m.opens, m.closes) for m in marks.MARKS)
    assert actual == _MARKS, f"the marks are now {actual!r}"


def test_each_mark_still_renders_as_it_always_has():
    """Breaks when a mark's HTML changes: everything already written would
    render differently, with nothing on disk to migrate."""
    for body, html in _RENDERED.items():
        got = marks.render(body, lambda name: "photographs/" + name, date(2026, 1, 1))
        assert got == html, f"{body!r} now renders {got!r}, not {html!r}"


# ------------------------------------------------------------------ look ----

# look/choices.json as version 1 writes it: the sunrise starter look.
_LOOK = """{
  "version": 1,
  "layout": "sunrise",
  "colours": {
    "light": {
      "paper": "#fffaf2",
      "ink": "#2b1d14",
      "soft": "#3a3a3a",
      "link": "#7c2a0b",
      "heading": "#2b1d14",
      "band": "#9a3412",
      "on-band": "#ffffff",
      "band-soft": "#ffffff",
      "accent": "#ffffff",
      "foot": "#f3e3cf",
      "on-foot": "#2b1d14",
      "foot-link": "#7c2a0b",
      "line": "#f3e3cf"
    },
    "dark": {
      "paper": "#1a1410",
      "ink": "#f5e9dc",
      "soft": "#d4c4b2",
      "link": "#ffb38a",
      "heading": "#f5e9dc",
      "band": "#6b230a",
      "on-band": "#ffffff",
      "band-soft": "#ffffff",
      "accent": "#ffffff",
      "foot": "#2b2019",
      "on-foot": "#f5e9dc",
      "foot-link": "#ffb38a",
      "line": "#4a3a2e"
    }
  },
  "body_font": "system",
  "heading_font": "serif",
  "text_size": "large",
  "width": "medium",
  "effects": []
}
"""


def test_a_version_one_look_still_reads_and_writes_back_the_same():
    """Breaks when the look file's fields, colour names or version change.
    The reader refuses any other shape, and the Look screen then stops rather
    than saving over the writer's choices."""
    choices = look.from_json(_LOOK)
    assert choices.layout == "sunrise"
    assert choices.light["paper"] == "#fffaf2"
    assert choices.dark["line"] == "#4a3a2e"
    assert (choices.body_font, choices.heading_font) == ("system", "serif")
    assert (choices.text_size, choices.width, choices.effects) == ("large", "medium", ())
    assert look.to_json(choices) == _LOOK, "the look file is no longer written as version 1"
    assert store.LOOK_FOLDER == "look" and store.LOOK_CHOICES_NAME == "choices.json"


# ----------------------------------------------------------- credentials ----


def test_a_version_one_credentials_file_still_gives_its_secret(tmp_path):
    """ADR-0003's fallback file, written by hand as version 1 writes it.
    Breaks when the reader stops finding a secret there: setup would then ask
    again for a key the writer already gave (S5). Runs on Windows too, where
    reading one back is how a machine is recovered."""
    (tmp_path / "credentials.json").write_text(
        '{"version": 1, "secrets": {"github": "plain words"}}\n', encoding="utf-8")
    assert credentials.read("file", tmp_path, "github") == "plain words"


@pytest.mark.skipif(sys.platform == "win32", reason="Pressless writes no secret file on Windows")
def test_the_credentials_file_is_still_written_as_version_one(tmp_path):
    """Breaks when a write changes the file's shape or drops the secret
    already there."""
    (tmp_path / "credentials.json").write_text(
        '{"version": 1, "secrets": {"github": "plain words"}}\n', encoding="utf-8")
    credentials.write("file", tmp_path, "google", "other words")
    held = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))
    assert held == {"version": 1,
                    "secrets": {"github": "plain words", "google": "other words"}}


# --------------------------------------------------------------- forwards ----


def test_an_address_forwards_file_still_reads(tmp_path):
    """PRESS-0210: a brought-in page's old address. Breaks when the file moves
    or its shape changes -- the old address then stops forwarding, and the
    first anyone hears of it is a reader's broken link."""
    (tmp_path / "forwards").mkdir()
    (tmp_path / "forwards" / "addresses.json").write_text(
        '{\n  "old/about-me.html": "about"\n}\n', encoding="utf-8")
    assert store.read_address_forwards(tmp_path) == {"old/about-me.html": "about"}


# --------------------------------------------------------------- settings ----


def test_settings_writes_the_frozen_keys(tmp_path):
    """settings.json's keys as save() writes them. test_settings pins what
    load() accepts; this pins what save() writes, so an older file and a newer
    build keep reading each other."""
    _write(tmp_path, _valid_mapping())
    settings.save(tmp_path, settings.load(tmp_path))
    held = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert held["version"] == 1
    assert set(held) == {
        "version", "site_folder", "repository", "site_address", "daily_prompt_filter",
        "untouchable", "credentials", "analytics_property_id", "measurement_id", "votes",
        "youtube_channel",
    }
    assert set(held["credentials"]) == {
        "store", "github_account", "google_account", "youtube_account"}
