"""The words table (PRESS-0242, docs/specs/PRESS-0242-screen-words.md)."""

from __future__ import annotations

import ast
import html
import json
import re
import threading
import warnings
from datetime import datetime
from pathlib import Path

import pytest
from _face_session import Browser
from test_setup import _saved

from pressless import (
    _flag_data,
    builder,
    cheatsheet,
    dashboard,
    editor,
    face,
    github_setup,
    google_setup,
    insights,
    marks,
    page_editor,
    pressing,
    publishing,
    report,
    restarting,
    setup,
    starter,
    store,
    templates,
    undo,
    updating,
    wizard,
    words,
)

SOURCE = Path(words.__file__).parent

# A run of two words, or one capitalised word, is English (spec INV-3).
ENGLISH_RUN = re.compile(r"[A-Za-z’']+\s+[A-Za-z’']+|\b[A-Z][a-z]{2,}\b")
KEY = re.compile(r"[a-z_]+(?:\.[A-Za-z0-9_-]+)+")
QUOTED_KEY = re.compile(r"""["']([a-z_]+(?:\.[A-Za-z0-9_-]+)+)["']""")


@pytest.fixture
def entry(monkeypatch):
    """Adds entries to ENGLISH for one test."""
    def add(key: str, text: str) -> None:
        monkeypatch.setitem(words.ENGLISH, key, text)
    return add


def test_say_fills_gaps_and_keeps_a_doubled_brace(entry) -> None:
    entry("test.hello", "Hello {name}, {{not a gap}}.")
    assert words.say("test.hello", name="you") == "Hello you, {not a gap}."


def test_a_missing_key_or_gap_raises(entry) -> None:
    """§ 6. Breaks when say() answers an unknown key or an unfilled gap with
    something a page would show."""
    entry("test.hello", "Hello {name}.")
    with pytest.raises(KeyError):
        words.say("test.no-such-key")
    with pytest.raises(KeyError):
        words.say("test.hello")


def test_a_table_in_use_comes_first_and_falls_back_to_english(entry) -> None:
    """§ 4.1. Breaks when use() hides English for keys its table lacks, or
    outlives its block."""
    entry("test.one", "One")
    entry("test.two", "Two")
    with words.use({"test.one": "Un"}):
        assert words.say("test.one") == "Un"
        assert words.say("test.two") == "Two"
    assert words.say("test.one") == "One"


def test_the_table_in_use_reaches_every_thread(entry) -> None:
    """§ 4.1: process-wide, so pages built on the server's threads follow it.
    Breaks when use() is made thread-local."""
    entry("test.one", "One")
    seen: list[str] = []
    with words.use({"test.one": "Un"}):
        reader = threading.Thread(target=lambda: seen.append(words.say("test.one")))
        reader.start()
        reader.join()
    assert seen == ["Un"]


def test_scripts_get_every_script_entry_and_nothing_else(entry) -> None:
    """§ 4.3. Breaks when a script entry is left out, a server-only entry is
    sent, or the JSON can close the <script> it sits in."""
    entry("script.test.saved", "Saved </script> {count}")
    entry("test.server", "Server only")
    sent = words.for_scripts()
    assert "</" not in sent
    shipped = json.loads(sent)
    assert shipped["script.test.saved"] == "Saved </script> {count}"
    assert "test.server" not in shipped
    assert all(key.startswith("script.") for key in shipped)
    with words.use({"script.test.saved": "Enregistré"}):
        assert json.loads(words.for_scripts())["script.test.saved"] == "Enregistré"


def test_the_two_families_come_from_their_sources() -> None:
    """§ 4.1. Breaks when a country or a cheat-sheet row has no entry."""
    for code, name in _flag_data.NAMES.items():
        assert words.say(f"country.{code}") == name
    for row in marks.MARKS:
        assert words.say(f"mark.{row.name}") == row.explains
        assert words.say(f"mark.{row.name}.example") == row.example


# ------------------------------------------------------------- the source ---


def _parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _docstrings(tree: ast.Module) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            found.add(id(node.body[0].value))
    return found


def _strings(tree: ast.Module, skip: set[int]) -> list[ast.Constant]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
            and isinstance(node.value, str) and id(node) not in skip]


# ------------------------------------------------------------------ INV-4 ---


def _asked() -> dict[str, str]:
    """Every literal key the source names, outside words.py, with where: a
    string that is a key, or a quoted key inside a script."""
    prefixes = {key.split(".", 1)[0] for key in words.ENGLISH}
    asked: dict[str, str] = {}
    for path in sorted(SOURCE.glob("*.py")):
        if path.name == "words.py":     # the table names every key itself
            continue
        tree = _parsed(path)
        for node in _strings(tree, _docstrings(tree)):
            found = [node.value] if KEY.fullmatch(node.value) else QUOTED_KEY.findall(node.value)
            for key in found:
                if key.split(".", 1)[0] in prefixes:
                    asked.setdefault(key, f"{path.name}:{node.lineno}")
    return asked


def test_every_key_is_in_the_table() -> None:
    """INV-4. Breaks when a key is misspelled."""
    missing = {key: where for key, where in _asked().items() if key not in words.ENGLISH}
    assert not missing, missing


def test_every_entry_is_used() -> None:
    """INV-4. Breaks when a moved string leaves its old entry behind. The two
    families are asked for by prefix (country., mark.), so they count whole."""
    asked = _asked()
    unused = [key for key in words.ENGLISH
              if key not in asked and not key.startswith(("country.", "mark."))]
    assert not unused, unused


# ------------------------------------------------------------------ INV-3 ---

_HTTP_HEADERS = "an HTTP header's name"
_ISSUE = "the issue form, read by whoever helps (decision 4)"
_FIELDS = "a field name in the entry file's format"
_MESSAGE = "part of an exception message (decision 4)"
_LAUNCHER = "the desktop launcher's own keys, or a file name"
_CSS = "CSS"

# Literals that are not words on a screen, named by the constant they are
# assigned to where they have one, else by their text, with why.
NOT_SCREEN_WORDS: dict[str, dict[str, str]] = {
    "dashboard.py": {
        "_CHANNELS": "Google's channel names, matched against its answer",
        "where": "a value Google sends",
        "Search": "the end of Google's channel names, matched against its answer",
        "card wide": "CSS class names", "ranked pages": "CSS class names",
    },
    "editor.py": {"REPLACES": _FIELDS},
    "face.py": {
        "_STYLE": _CSS, "_SHAPES": _CSS,
        "FILES_POLICY": "a Content-Security-Policy value",
        "_FRAMES_POLICY": "a Content-Security-Policy value",
        "_ANCESTORS_POLICY": "a Content-Security-Policy value",
        "cookie": "a cookie's attributes",
        "Page": "a type annotation",
        "_SAY": "the script's own error for a missing key, read by whoever helps",
        "_ICON": "the app's name, in its icon",
        "Pressless": "the app's name", "Press less": "the app's name, in the bar",
        **dict.fromkeys(("Content-Type", "Content-Length", "Cache-Control",
                         "Content-Security-Policy", "X-Content-Type-Options", "Set-Cookie",
                         "Location", "Host", "Origin", "Cookie", "origin", "location",
                         "length", "left", "jar"), _HTTP_HEADERS),
    },
    "publishing.py": {"MESSAGE": "a git commit message (decision 4)",
                      "UNDONE": "a git commit message (decision 4)"},
    "report.py": {"body": _ISSUE, "query": _ISSUE, "Windows": _ISSUE, "Linux": _ISSUE,
                  "Linux (": _ISSUE, "an unknown system": _ISSUE},
    "shortcuts.py": {
        "lines": _LAUNCHER, "wanted": _LAUNCHER, "found": _LAUNCHER, "done": _LAUNCHER,
        "_LINK": _LAUNCHER, "_BATCH": _LAUNCHER, "Desktop": "a folder's name",
        "Categories=Office;": _LAUNCHER, "Icon=": _LAUNCHER, "Terminal=true": _LAUNCHER,
        "Exec=": _LAUNCHER, "Comment=": _LAUNCHER,
        "_WINDOWS_SCRIPT": "PowerShell",
    },
    "starter.py": {"_SUNRISE": _CSS, "_MEADOW": _CSS, "_HARBOUR": _CSS, "_JOURNAL_RULES": _CSS,
                   "Home": "a data-nav name, which the Builder matches on"},
    "store.py": {
        "RECOGNISED_FIELDS": _FIELDS, "one_line": _FIELDS,
        **dict.fromkeys(("Title", "Slug", "Date", "Categories", "Tags", "Title:", "Slug:",
                         "Date:", "Categories:", "Tags:", "Categories[", "Tags["), _FIELDS),
        "occupied": _MESSAGE,
        **dict.fromkeys(("a slug", "a template name", "a comments slug", "an address",
                         "extra name", "already holds"), _MESSAGE),
    },
    "updating.py": {"The update check stopped at step": "a log line"},
}

_SELECTOR = re.compile(r"[#.]?[\w-]+(?:\[[^\]]*\])?(?: [#.]?[\w-]+(?:\[[^\]]*\])?)*")


def _screen_modules() -> list[Path]:
    """Every module importing face or words, plus starter.py and templates.py."""
    chosen = []
    for path in sorted(SOURCE.glob("*.py")):
        names = set()
        for node in ast.walk(_parsed(path)):
            if isinstance(node, ast.ImportFrom) and node.module == "pressless":
                names |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module in ("pressless.face",
                                                                       "pressless.words"):
                names.add(node.module.rsplit(".", 1)[1])
        if names & {"face", "words"} or path.name in ("starter.py", "templates.py"):
            chosen.append(path)
    return chosen


def _not_shown(tree: ast.Module) -> tuple[set[int], dict[int, str]]:
    """Docstrings, exception messages and log lines; and each literal's
    constant name, where it is assigned to one."""
    skip, named = _docstrings(tree), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            skip |= {id(inner) for inner in ast.walk(node.exc)}
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("note", "warn"):
            skip |= {id(inner) for inner in ast.walk(node)}
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    named.update((id(inner), target.id) for inner in ast.walk(node.value))
    return skip, named


def _english(text: str) -> list[str]:
    """The pieces of `text` that read as English. Markup is stripped, keeping
    the values of title, alt, placeholder and aria-label; a script gives its
    string literals; a key is a key."""
    if text in words.ENGLISH or KEY.fullmatch(text):
        return []
    if "=>" in text or "document." in text or "function " in text:
        pieces = [re.sub(r"<[^>]*>|\$\{[^}]*\}", " ", literal) for literal in
                  (next(g for g in m.groups() if g is not None) for m in re.finditer(
                      r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`([^`]*)`', text))]
    else:
        kept = re.findall(r'\b(?:title|alt|placeholder|aria-label)="([^"]*)"', text)
        bare = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->", " ", text,
                      flags=re.S)
        bare = re.sub(r"<[^>]*>?", " ", bare)
        pieces = [piece for piece in re.split(r"\s{2,}|\n", bare) if piece.strip()] + kept
    found = []
    for piece in (piece.strip() for piece in pieces):
        if not ENGLISH_RUN.search(piece) or KEY.fullmatch(piece) or '="' in piece:
            continue    # no words, a key, or a fragment of a tag's attributes
        if _SELECTOR.fullmatch(piece) and re.search(r"[#.\[]", piece):
            continue    # a CSS selector a script queries
        found.append(piece)
    return found


def test_no_screen_writes_english() -> None:
    """INV-3. Breaks when someone adds "Saved" to a script or
    f"<p>Nothing here</p>" to a page builder."""
    written = []
    for path in _screen_modules():
        tree = _parsed(path)
        skip, named = _not_shown(tree)
        allowed = NOT_SCREEN_WORDS.get(path.name, {})
        for node in _strings(tree, skip):
            if named.get(id(node)) in allowed:
                continue
            written += [f"{path.name}:{node.lineno} {piece!r}"
                        for piece in _english(node.value) if piece not in allowed]
    assert not written, "\n".join(written)


# ------------------------------------------------------------------ INV-2 ---

OPEN, CLOSE = "⟦", "⟧"
MARKED = {key: OPEN + text + CLOSE for key, text in words.ENGLISH.items()}
# Outside a marker a page may show the app's name, and the short month and
# day names strftime writes, which PRESS-0241 translates with the language.
_NAMES = re.compile(r"\bPress\W*less\b|\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|Jan|Feb|Mar|Apr"
                    r"|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b")
# The writer's own content: lowercase single words, which are not English
# by ENGLISH_RUN, so anything left over is the app's.
OWN = "zz"


def _unmarked(page: str, *, comments: bool = False) -> list[str]:
    """English a reader sees that no marker holds. Markup is stripped,
    keeping title, alt, placeholder and aria-label; so are scripts, styles,
    and the details Show details holds (decision 4)."""
    page = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<pre>.*?</pre>"
                  r"|<!-- *[A-Z]+:(?:START|END)\b.*?-->", " ", page, flags=re.S)
    if not comments:
        page = re.sub(r"<!--.*?-->", " ", page, flags=re.S)
    kept = re.findall(r'\b(?:title|alt|placeholder|aria-label)="([^"]*)"', page)
    # A tag ends a run of words: two list items are not a sentence.
    text = html.unescape("\0".join([re.sub(r"<(?!!--)[^>]*>", "\0", page), *kept]))
    while True:     # innermost first: a marked entry can hold another
        inner = re.sub(f"{OPEN}[^{OPEN}{CLOSE}]*{CLOSE}", " ", text)
        if inner == text:
            break
        text = inner
    return ENGLISH_RUN.findall(_NAMES.sub(" ", text))


def _served(folder: Path) -> face.Face:
    """The Face with every screen registered, as __main__ registers them."""
    served = face.serve(folder)
    setup.register(served, folder)
    github_setup.register(served, folder)
    google_setup.register(served, folder)
    dashboard.register(served, folder)
    editor.register(served, folder)
    cheatsheet.register(served)
    report.register(served)
    templates.register(served, folder)
    publishing.register(served, folder)
    undo.register(served, folder)
    page_editor.register(served, folder)
    pressing.register(served)
    updating.register(served, folder)
    restarting.register(served, lambda: None)
    return served


def _report() -> insights.Report:
    return insights.Report(
        people=1234, countries=(insights.Country("ZA", 9),
                                insights.Country(insights.UNKNOWN_COUNTRY, 1)),
        days=28, fetched_at=1_760_000_000.0, stale=True,
        daily=(insights.Day("2026-10-01", 0), insights.Day("2026-10-02", 3)),
        pages=(insights.Page("/zz/", 3, 2, 75.0),),
        sources=(insights.Source("Organic Search", OWN, 4, 2),
                 insights.Source(OWN, OWN, 1, 1)))


def _pages(tmp_path: Path, monkeypatch) -> dict[str, str]:
    """Every page the tests can reach, rendered under the table in use."""
    shown: dict[str, str] = {}
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    served = _served(fresh)
    try:
        browser = Browser(served)
        first_run = setup._first_run_wizard(served, fresh, None, lambda: None)
        for step in first_run._steps:
            first_run.progress.parent.mkdir(parents=True, exist_ok=True)
            first_run.progress.write_text(json.dumps(
                {"version": wizard.VERSION, "step": step.name, "answers": {}}),
                encoding="utf-8")
            shown[f"setup step {step.name}"] = browser.request("GET", "/setup")[2]
    finally:
        served.stop()

    folder = tmp_path / "data"
    folder.mkdir()
    _saved(folder, site_folder=folder / OWN)
    starter.fill(folder, OWN)
    store.write(folder, store.Entry(slug=OWN, title=OWN, date=datetime(2020, 1, 2),
                                    categories=(), tags=(), body=OWN, extra=()), draft=True)
    served = _served(folder)
    try:
        browser = Browser(served)
        for name, address in (
                ("the list", "/"), ("the editor", f"/edit?slug={OWN}"),
                ("the page editor", "/page?kind=pages&name=about"),
                ("Settings", "/setup"), ("GitHub sign-in", github_setup.PAGE),
                ("visitor numbers setup", google_setup.PAGE), ("the dashboard", dashboard.PAGE),
                ("the report page", report.ADDRESS), ("the cheat sheet", cheatsheet.ADDRESS),
                ("a template", "/template?name=poem"), ("restarting", restarting.PATH)):
            status, _, page = browser.request("GET", address)
            assert status == 200, (name, status)
            if name == "the list":
                # PRESS-0237: the site's own page names, shown as labels. They
                # are file names, which stay English, not the app's words.
                for own in store.list_html(folder, store.PAGES_FOLDER):
                    page = page.replace(f">{builder.label(own)}</a>", f">{OWN}</a>")
            shown[name] = page
        monkeypatch.setattr(pressing, "_running", pressing.PUBLISH)
        shown["the holding page"] = browser.request("GET", f"/edit?slug={OWN}")[2]
        monkeypatch.setattr(pressing, "_running", None)
        shown["a failure"] = served.fail(store.StoreError(OWN), publishing=True)
        with served.capture() as notices:
            warnings.warn(store.StoreNotice("notice.store.passed_over", file=OWN, reason=OWN),
                          stacklevel=1)
        shown["a notice"] = face.render_notices(notices)
    finally:
        served.stop()
    shown["the dashboard's numbers"] = dashboard._report(_report(), "https://example.org")
    return shown


def test_pages_take_their_words_from_the_table(tmp_path, monkeypatch) -> None:
    """INV-2. Breaks when a module fixes its words at import, or a page
    builder writes English itself."""
    with words.use(MARKED):
        shown = _pages(tmp_path, monkeypatch)
        site = tmp_path / "data"
        for path in sorted(site.rglob("*.html")):
            shown[f"the starter's {path.relative_to(site)}"] = path.read_text(encoding="utf-8")
        style = store.style_code_path(site).read_text(encoding="utf-8")
        shown["the starter's style notes"] = " ".join(re.findall(r"/\*(.*?)\*/", style,
                                                                 flags=re.S))
        for name in store.list_templates(site):
            starter_template = store.read(store.template_path_for(site, name))
            shown[f"the starter's template {name}"] = (
                f"{starter_template.title}\n{starter_template.body}")
        starter.add_privacy(site, OWN)
        privacy = store.html_path_for(site, store.PAGES_FOLDER, "privacy")
        shown["the Privacy page"] = privacy.read_text(encoding="utf-8")
    left = {name: found for name, page in shown.items()
            if (found := _unmarked(page, comments=name.startswith("the starter's")))}
    assert not left, left
    assert len(shown) > 20, sorted(shown)
