# The Face's themes and the picker that chooses one (PRESS-0190).
#
# The contrast floors are WCAG 2.1 AA, written out here rather than read from
# themes.py, so a theme cannot pass by lowering the bar it is measured against.
# The writer is partially sighted; a theme he cannot read is not a theme.
from __future__ import annotations

import http.client
import json
import re
import urllib.parse
from pathlib import Path

import pytest
from _face_session import session_cookie

from pressless import face, themes

TEXT = 4.5      # WCAG 1.4.3, normal text
NON_TEXT = 3.0  # WCAG 1.4.11, focus rings and borders that carry meaning
FILE_NAME = "theme.json"


def _luminance(colour: str) -> float:
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(one: str, two: str) -> float:
    light, dark = sorted((_luminance(one), _luminance(two)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("theme", themes.THEMES, ids=lambda theme: theme.key)
def test_every_theme_can_be_read(theme: themes.Theme) -> None:
    colours = dict(zip(themes.NAMES, theme.colours, strict=True))
    failures = []
    for text in ("ink", "soft", "amber-ink"):
        for ground in ("paper", "sheet"):
            ratio = _contrast(colours[text], colours[ground])
            if ratio < TEXT:
                failures.append(f"{text} on {ground}: {ratio:.2f}")
    for mark in ("amber", "alert"):
        for ground in ("paper", "sheet"):
            ratio = _contrast(colours[mark], colours[ground])
            if ratio < NON_TEXT:
                failures.append(f"{mark} on {ground}: {ratio:.2f}")
    ratio = _contrast(colours["on-press"], colours["press"])
    if ratio < TEXT:
        failures.append(f"on-press on press: {ratio:.2f}")
    assert not failures, failures


def test_the_high_contrast_themes_reach_aaa() -> None:
    for key in ("contrast-light", "contrast-dark"):
        theme = themes.find(key)
        assert theme is not None, key
        colours = dict(zip(themes.NAMES, theme.colours, strict=True))
        assert _contrast(colours["ink"], colours["paper"]) >= 7, key


def test_keys_are_unique_and_safe_in_markup() -> None:
    keys = [theme.key for theme in themes.THEMES]
    assert len(keys) == len(set(keys))
    assert all(re.fullmatch(r"[a-z][a-z-]*", key) for key in keys), keys
    assert "follow" not in keys


@pytest.mark.parametrize("text", ["", "not json", '["dark"]', '{"version": 2, "theme": "dark"}',
                                  '{"version": 1, "theme": "no-such-theme"}',
                                  '{"version": 1, "theme": 7}'])
def test_an_unusable_file_reads_as_follow(tmp_path: Path, text: str) -> None:
    (tmp_path / FILE_NAME).write_text(text, encoding="utf-8")
    assert themes.read_choice(tmp_path) == "follow"


def test_a_missing_file_reads_as_follow(tmp_path: Path) -> None:
    assert themes.read_choice(tmp_path) == "follow"


def test_an_unknown_key_is_never_written(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        themes.write_choice(tmp_path, "no-such-theme")
    assert not (tmp_path / FILE_NAME).exists()


def _post_theme(served: face.Face, cookie: str, body: str) -> int:
    port = urllib.parse.urlsplit(served.url).port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("POST", "/theme", body=body.encode("utf-8"), headers={
            "Host": f"127.0.0.1:{port}", "Cookie": cookie,
            "Origin": f"http://127.0.0.1:{port}"})
        return conn.getresponse().status
    finally:
        conn.close()


def _get(served: face.Face, cookie: str, path: str) -> str:
    port = urllib.parse.urlsplit(served.url).port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path, headers={"Host": f"127.0.0.1:{port}", "Cookie": cookie})
        response = conn.getresponse()
        assert response.status == 200
        return response.read().decode("utf-8")
    finally:
        conn.close()


def test_a_picked_theme_is_kept_and_every_page_wears_it(tmp_path: Path) -> None:
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        cookie = session_cookie(served.url)
        first = _get(served, cookie, "/words")
        assert "<html lang=\"en\">" in first, "with nothing chosen, the page follows the computer"
        assert '<option value="follow" selected>' in first
        assert _post_theme(served, cookie, "bonfire") == 204
        page = _get(served, cookie, "/words")
    finally:
        served.stop()
    assert '<html lang="en" data-theme="bonfire">' in page
    assert '<option value="bonfire" selected>' in page
    assert ':root[data-theme="bonfire"]' in page, "the page carries the theme's colours"
    assert json.loads((tmp_path / FILE_NAME).read_text(encoding="utf-8")) == {
        "version": 1, "theme": "bonfire"}
    # A later run starts in the theme he chose.
    again = face.serve(tmp_path)
    try:
        again.add_page("GET", "/words", lambda request: "<p>Words</p>")
        assert 'data-theme="bonfire"' in _get(again, session_cookie(again.url), "/words")
    finally:
        again.stop()


def test_follow_takes_the_theme_off(tmp_path: Path) -> None:
    themes.write_choice(tmp_path, "dark")
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        cookie = session_cookie(served.url)
        assert _post_theme(served, cookie, "follow") == 204
        page = _get(served, cookie, "/words")
    finally:
        served.stop()
    assert "data-theme=" not in page.split("<head>")[0]


@pytest.mark.parametrize("body", ["no-such-theme", '"><script>', "x" * 200])
def test_a_theme_that_does_not_exist_is_refused(tmp_path: Path, body: str) -> None:
    served = face.serve(tmp_path)
    try:
        assert _post_theme(served, session_cookie(served.url), body) == 400
    finally:
        served.stop()
    assert not (tmp_path / FILE_NAME).exists()


def test_the_picker_applies_a_theme_without_a_reload(tmp_path: Path) -> None:
    """Applied at once: the page's script sets data-theme on change, and every
    theme's rules are already in the page, so nothing waits on the server."""
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        page = _get(served, session_cookie(served.url), "/words")
    finally:
        served.stop()
    # Every plain script: the words' `say` sits in <head> ahead of this one.
    script = "".join(re.findall(r"<script>(.*?)</script>", page, re.S))
    assert "select[data-theme-picker]" in script
    assert "document.documentElement.dataset.theme = picker.value" in script
    for theme in themes.THEMES:
        assert f':root[data-theme="{theme.key}"]' in page, theme.key
