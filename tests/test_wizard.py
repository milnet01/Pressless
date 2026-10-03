# The shared wizard pattern (PRESS-0220), held by PRESS-0212's INV-1 to INV-4
# (docs/specs/PRESS-0212-setup-wizard.md § 4.1, § 4.2).
#
# Every server is started inside the test that uses it, and the wizard here is
# a three-step one with no GitHub behind it, so these tests are about the
# pattern alone. Setup's own steps are tests/test_setup.py's.
from __future__ import annotations

import contextlib
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

from test_setup import _Browser

from pressless import face, wizard

ADDRESS = "/try"


def _show(name: str):
    def show(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
        return wizard.field(name, name, answers, hint)
    return show


def _steps(check=None) -> list[wizard.Step]:
    return [
        wizard.Step("first", "The first", ("one",), _show("one")),
        wizard.Step("second", "The second", ("two",), _show("two"), check),
        wizard.Step("third", "The third", ("three",), _show("three"),
                    lambda answers: wizard.Done("<p>All done.</p>")),
    ]


@contextlib.contextmanager
def _served(folder: Path, steps: list[wizard.Step]) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        made = wizard.Wizard("try", steps, folder, ADDRESS)
        served.add_page("GET", ADDRESS, lambda request: made.page(served, request))
        served.add_page("POST", ADDRESS, lambda request: made.page(served, request))
        yield _Browser(served)
    finally:
        served.stop()


def _get(browser: _Browser) -> str:
    return browser._send("GET", b"", cookie=True, origin=None, path=ADDRESS)[1]


def _go(browser: _Browser, step: str, go: str, **fields: str) -> str:
    return browser.post({"step": step, "go": go, **fields}, path=ADDRESS)[1]


def _progress(folder: Path) -> Path:
    return folder / "wizards" / "try.json"


def test_each_screen_is_one_step(tmp_path):
    """INV-1. Breaks when a page shows two steps' fields, the counter counts
    the done screen, or the first step offers Back."""
    with _served(tmp_path, _steps()) as browser:
        first = _get(browser)
        second = _go(browser, "first", "next", one="a")
        third = _go(browser, "second", "next", two="b")
        back = _go(browser, "third", "back")
    assert "Step 1 of 3" in first and 'name="one"' in first and 'name="two"' not in first
    assert 'value="back"' not in first
    assert "Step 2 of 3" in second and 'name="two"' in second and 'name="one"' not in second
    assert 'value="back"' in second and 'value="next"' in second
    assert "Step 3 of 3" in third and 'name="three"' in third
    assert "Step 2 of 3" in back


def test_a_refused_check_stays_put(tmp_path):
    """INV-2. Breaks when the wizard writes the posted answers before running
    the check, or moves on after a Hint."""
    said: list[object] = [wizard.Hint("two", "Not that."), wizard.Stop("<p>It broke.</p>")]

    def check(answers):
        return said.pop(0) if said else answers

    with _served(tmp_path, _steps(check)) as browser:
        _go(browser, "first", "next", one="a")
        before = _progress(tmp_path).read_bytes()
        hinted = _go(browser, "second", "next", two="refused")
        assert _progress(tmp_path).read_bytes() == before
        stopped = _go(browser, "second", "next", two="refused")
        assert _progress(tmp_path).read_bytes() == before
        moved = _go(browser, "second", "next", two="kept")
    assert "Step 2 of 3" in hinted and "Not that." in hinted and 'value="refused"' in hinted
    assert "Step 2 of 3" in stopped and "It broke." in stopped
    assert "Step 3 of 3" in moved


def test_a_new_launch_resumes(tmp_path):
    """INV-3. Breaks when progress lives only in memory, or GET always starts
    at the first step."""
    with _served(tmp_path, _steps()) as browser:
        _go(browser, "first", "next", one="a")
        _go(browser, "second", "next", two="b")
    with _served(tmp_path, _steps()) as browser:
        resumed = _get(browser)
        back = _go(browser, "third", "back")
    assert "Step 3 of 3" in resumed
    assert "Step 2 of 3" in back and 'value="b"' in back


def test_a_stale_tab_cannot_skip_a_check(tmp_path):
    """INV-4. Breaks when the wizard trusts the posted step and runs or skips a
    check from it."""
    ran: list[str] = []

    def check(answers):
        ran.append(answers["two"])
        return wizard.Hint("two", "Not yet.")

    with _served(tmp_path, _steps(check)) as browser:
        _go(browser, "first", "next", one="a")
        stale = _go(browser, "first", "next", one="again")
        skipped = _go(browser, "third", "next", three="c")
    assert ran == []
    assert "Step 2 of 3" in stale and "Step 2 of 3" in skipped


def test_done_forgets_the_progress(tmp_path):
    """§ 4.2: Done removes the progress file and its fragment is the page."""
    with _served(tmp_path, _steps()) as browser:
        _go(browser, "first", "next", one="a")
        _go(browser, "second", "next", two="b")
        done = _go(browser, "third", "next", three="c")
        again = _get(browser)
    assert "All done." in done
    assert not _progress(tmp_path).exists()
    assert "Step 1 of 3" in again


def test_an_unreadable_progress_file_starts_over(tmp_path):
    """§ 4.2: a file that will not read as the shape is treated as absent."""
    _progress(tmp_path).parent.mkdir(parents=True)
    for broken in ("not json", '{"version": 1, "step": "gone", "answers": {}}',
                   '{"version": 2, "step": "third", "answers": {}}'):
        _progress(tmp_path).write_text(broken, encoding="utf-8")
        with _served(tmp_path, _steps()) as browser:
            assert "Step 1 of 3" in _get(browser), broken


def test_a_field_ending_in_key_is_never_kept(tmp_path):
    """§ 4.2: the progress file never holds a field whose name ends in key."""
    steps = [wizard.Step("first", "The first", ("publishing_key",), _show("publishing_key")),
             wizard.Step("second", "The second", (), lambda a, h: "")]
    with _served(tmp_path, steps) as browser:
        _go(browser, "first", "next", publishing_key="plain words for a key")
    assert b"plain words" not in _progress(tmp_path).read_bytes()
    assert "publishing_key" not in urllib.parse.unquote(_progress(tmp_path).read_text())
