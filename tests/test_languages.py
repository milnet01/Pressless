"""More languages (PRESS-0241, docs/specs/PRESS-0241-more-languages.md)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _marked_language
import pytest
from _face_session import Browser
from _scripts import load_script
from test_builder import _built, _comment, _entry, _settings, _store

from pressless import builder, face, languages, store, words

LANGUAGE_FILES = Path(words.__file__).parent / "language_files"


def _site(tmp_path: Path, language: str = "") -> Path:
    """A site whose build writes every word the Builder has: a journal of two
    pages, a category and a tag, comments, an untitled entry, and an entry
    and a page that have moved."""
    folder = _store(tmp_path, pages={"index": "<p>zz</p>\n", "about": "<p>zz</p>\n"})
    # The menu is the writer's own words, which no language changes.
    store.write_html(folder, store.FURNITURE_FOLDER, "navigation",
                     '<nav><a href="{{UP}}blog/index.html" data-nav="Journal">zz</a></nav>')
    for number in range(builder.PER_PAGE + 1):
        store.write(folder, _entry(
            f"e{number}", f"2020-03-{number + 1:02d} 10:00:00",
            title="" if number == 0 else f"zz{number}",
            categories=("cats",), tags=("dogs",)), draft=False)
    store.write_comments(folder, "e1", (_comment(), _comment("2", author="")))
    store.write_forwards(folder, {"gone": "e2"})
    store.write_page_forwards(folder, {"old": "about"})
    store.write_identity(folder, store.Identity("zz", language=language))
    return folder


def _build(folder: Path, into: Path) -> dict[str, bytes]:
    builder.build(folder, _settings(), into)
    return _built(into)


def test_a_site_without_a_language_builds_as_before(tmp_path, monkeypatch) -> None:
    """INV-1. Breaks when the Builder takes the screens' language, or writes
    `lang` from it."""
    folder = _site(tmp_path)
    english = _build(folder, tmp_path / "english")
    with _marked_language.speaking(tmp_path / "languages", monkeypatch):
        assert words.say("site.older") != words.ENGLISH["site.older"]   # the screens moved
        marked = _build(folder, tmp_path / "marked")
    assert marked == english
    page = english["blog/index.html"].decode("utf-8")
    assert '<html lang="en">' in page and "Older →" in page


def _unmarked(page: str) -> str:
    """What a reader sees of `page` outside the markers: its text, and the
    labels it carries, innermost marker first, as a marked entry can hold
    another."""
    labels = re.findall(r'\b(?:title|alt|aria-label|content)="([^"]*)"', page)
    text = "\0".join([re.sub(r"<[^>]*>", "\0", page), *labels])
    pattern = f"{_marked_language.OPEN}[^{_marked_language.OPEN}{_marked_language.CLOSE}]*" \
              f"{_marked_language.CLOSE}"
    while (inner := re.sub(pattern, " ", text)) != text:
        text = inner
    return text


# The English the Builder writes of its own, in pieces of three letters or more.
def _builder_english() -> set[str]:
    pieces = set()
    for key, text in words.ENGLISH.items():
        if key.startswith(("site.", "date.month.", "date.mon.")):
            bare = re.sub(r"\{\w+\}|<[^>]*>", "\0", text)
            pieces |= {piece.strip() for piece in bare.split("\0")
                       if len(re.sub(r"\W", "", piece)) >= 3}
    return pieces


def test_published_words_follow_the_site(tmp_path, monkeypatch) -> None:
    """INV-2. Breaks when a Builder word uses `say` rather than `say_in`, or a
    date its own month names."""
    _marked_language.offered(tmp_path / "languages", monkeypatch)
    folder = _site(tmp_path, _marked_language.CODE)
    built = _build(folder, tmp_path / "into")
    shown = {name: data.decode("utf-8") for name, data in built.items()
             if name.endswith(".html") and (name.startswith(("blog/", "pages/old"))
                                            or name == "index.html")}
    assert {"blog/index.html", "blog/page/2/index.html", "blog/archive/index.html",
            "blog/category/cats/index.html", "blog/tag/dogs/index.html",
            "blog/2020/03/02/e1/index.html", "blog/2020/03/03/gone/index.html",
            "pages/old.html"} <= set(shown), sorted(shown)
    english = _builder_english()
    assert "Older →" in english and "March" in english and "This entry has moved to" in english
    left = {}
    for name, page in shown.items():
        if name not in ("index.html",):
            assert f'<html lang="{_marked_language.CODE}">' in page, name
        if found := sorted(piece for piece in english if piece in _unmarked(page)):
            left[name] = found
    assert not left, left
    assert f"{_marked_language.OPEN}Older →{_marked_language.CLOSE}" in shown["blog/index.html"]


def _gaps_and_tags(text: str) -> tuple[set[str], list[str]]:
    return (set(re.findall(r"(?<!\{)\{(\w+)\}", text)),
            re.findall(r"</?([a-zA-Z][\w-]*)", text))


def _mismatched(folder: Path) -> list[str]:
    """Every entry of every language file whose gaps or tags differ from its
    English's."""
    wrong = []
    for path in sorted(folder.glob("*.json")):
        held = json.loads(path.read_text(encoding="utf-8"))["words"]
        for key, (_, translated) in held.items():
            if key in words.ENGLISH and (_gaps_and_tags(translated)
                                         != _gaps_and_tags(words.ENGLISH[key])):
                wrong.append(f"{path.name} {key}")
    return wrong


def test_translations_keep_gaps_and_tags(tmp_path) -> None:
    """INV-3. Breaks when a translation drops {count}, or turns <b> into
    <strong>. The planted file shows the check can fail."""
    assert not _mismatched(LANGUAGE_FILES)
    moved = words.ENGLISH["site.moved.entry"]
    assert "<a " in moved and "</a>" in moved
    (tmp_path / "xx.json").write_text(json.dumps({"name": "x", "words": {
        "site.entries.many": ["", "entries"],
        "site.moved.entry": ["", moved.replace("<a ", "<b ").replace("</a>", "</b>")],
        "site.older": ["", "later"]}}), encoding="utf-8")
    assert _mismatched(tmp_path) == ["xx.json site.entries.many", "xx.json site.moved.entry"]


def test_stale_or_missing_shows_english(tmp_path, monkeypatch) -> None:
    """INV-4. Breaks when `table` ignores made-from."""
    monkeypatch.setattr(words, "FOLDER", tmp_path)
    (tmp_path / "xx.json").write_text(json.dumps({"name": "x", "words": {
        "site.older": [words.made_from(words.ENGLISH["site.older"]), "later"],
        "site.newer": ["00000000", "sooner"]}}), encoding="utf-8")
    assert words.table("xx") == {"site.older": "later"}
    assert words.say_in("xx", "site.older") == "later"
    assert words.say_in("xx", "site.newer") == words.ENGLISH["site.newer"]     # stale
    assert words.say_in("xx", "site.archive") == words.ENGLISH["site.archive"]  # missing


@pytest.mark.parametrize(("environment", "found"), [
    ({"LANG": "es_MX.UTF-8"}, "es"),
    ({"LANGUAGE": "af:en", "LANG": "en_GB.UTF-8"}, "af"),
    ({"LC_ALL": "de_DE.UTF-8", "LANG": "fr_FR.UTF-8"}, "de"),
    ({"LC_MESSAGES": "fr_FR", "LANG": "en_GB"}, "fr"),
    ({"LANG": "C.UTF-8"}, None),
    ({"LANG": "POSIX"}, None),
    ({}, None),
])
def test_the_computers_language_is_read(monkeypatch, environment, found) -> None:
    """INV-5, Linux. Breaks when LC_ALL loses to LANG, or C.UTF-8 reads as a
    language."""
    monkeypatch.setattr(sys, "platform", "linux")
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert languages.computer() == found


@pytest.mark.parametrize(("language_id", "found"), [(0x0436, "af"), (0x0C0A, "es"),
                                                    (0x7FFF, None)])
def test_the_computers_language_is_read_on_windows(monkeypatch, language_id, found) -> None:
    """INV-5, Windows, with the system call replaced. Breaks when an id
    locale.windows_locale lacks reads as a language."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(languages, "_ui_language", lambda: language_id)
    assert languages.computer() == found


def test_the_list_is_offered_until_one_is_chosen(tmp_path, monkeypatch) -> None:
    """INV-6. Breaks when the list shows on only the first screen, or after a
    choice."""
    _marked_language.offered(tmp_path / "languages", monkeypatch)
    monkeypatch.setattr(languages, "computer", lambda: None)    # cannot be told
    own = tmp_path / "own"
    own.mkdir()
    served = face.serve(own)
    try:
        served.add_page("GET", "/one", lambda request: "<p>one</p>")
        served.add_page("GET", "/two", lambda request: "<p>two</p>")
        browser = Browser(served)
        before = [browser.request("GET", path)[2] for path in ("/one", "/two", "/one")]
        status, _, _ = browser.raw("POST", languages.ADDRESS,
                                   _marked_language.CODE.encode())
        after = [browser.request("GET", path)[2] for path in ("/one", "/two")]
    finally:
        served.stop()
        words.choose("en")
    assert all('class="languages-offer"' in page for page in before)
    assert status == 204
    assert not any('class="languages-offer"' in page for page in after)
    assert all(f'<html lang="{_marked_language.CODE}"' in page for page in after)
    assert languages.read_choice(own) == _marked_language.CODE


def test_a_chosen_language_wins_over_the_computers(tmp_path, monkeypatch) -> None:
    """§ 4.3's order: a choice, then the computer's where Pressless has it,
    then English. Breaks when the computer's outranks the choice."""
    _marked_language.offered(tmp_path / "languages", monkeypatch)
    monkeypatch.setattr(languages, "computer", lambda: "es")
    assert languages.for_screens(tmp_path) == ("en", False)    # no Spanish yet
    monkeypatch.setattr(languages, "computer", lambda: _marked_language.CODE)
    assert languages.for_screens(tmp_path) == (_marked_language.CODE, False)
    languages.write_choice(tmp_path, "en")
    assert languages.for_screens(tmp_path) == ("en", False)


def test_every_language_loads(tmp_path) -> None:
    """INV-9. Breaks when the folder is left out of freeze_flags.DATA, or a
    file is not JSON."""
    for code in words.LANGUAGES[1:]:
        held = json.loads((LANGUAGE_FILES / f"{code}.json").read_text(encoding="utf-8"))
        assert isinstance(held["name"], str) and held["name"], code
        assert words.table(code), code
    assert words.LANGUAGES[0] == "en"
    args = load_script("freeze_flags.py").pyinstaller_args(tmp_path)
    pairs = [args[i + 1] for i, flag in enumerate(args) if flag == "--add-data"]
    assert f"{LANGUAGE_FILES}:pressless/language_files" in pairs, pairs
    assert LANGUAGE_FILES.is_dir()


def test_a_language_file_that_will_not_load_gives_english(tmp_path, monkeypatch) -> None:
    """§ 6. Breaks when a broken file raises, so every screen fails."""
    monkeypatch.setattr(words, "FOLDER", tmp_path)
    (tmp_path / "xx.json").write_text("{not json", encoding="utf-8")
    assert words.say_in("xx", "site.older") == words.ENGLISH["site.older"]
    assert "xx" in words.unreadable()


def test_an_identity_keeps_todays_bytes_without_a_language(tmp_path) -> None:
    """§ 4.4. Breaks when an English site's identity gains a language field,
    or a malformed code is written."""
    store.write_identity(tmp_path, store.Identity("zz"))
    assert "language" not in store.identity_path_for(tmp_path).read_text(encoding="utf-8")
    store.write_identity(tmp_path, store.Identity("zz", language="af"))
    assert store.read_identity(tmp_path).language == "af"
    with pytest.raises(store.StoreError):
        store.write_identity(tmp_path, store.Identity("zz", language="Afrikaans"))


def test_the_translation_script_stamps_and_reports(tmp_path, monkeypatch) -> None:
    """§ 4.5. Breaks when stamping restamps an older entry, which would hide
    English reworded since, or the report misses a stale or missing key."""
    script = load_script("translations.py")
    path = tmp_path / "xx.json"
    path.write_text(json.dumps({"name": "x", "one": [1], "thousands": ".", "words": {
        "site.older": "later", "site.newer": ["00000000", "sooner"]}}), encoding="utf-8")
    assert script.stamp(path) == 1
    held = json.loads(path.read_text(encoding="utf-8"))["words"]
    assert held["site.older"] == [words.made_from(words.ENGLISH["site.older"]), "later"]
    assert held["site.newer"] == ["00000000", "sooner"]
    manual_folder = tmp_path / "manual"
    (manual_folder / "media").mkdir(parents=True)
    (manual_folder / "media" / "publishing.en.vtt").write_text("WEBVTT\n", encoding="utf-8")
    found = script.report(tmp_path, manual_folder, ("xx",))
    assert "xx out of date site.newer" in found and "xx missing site.archive" in found
    assert not any(line.endswith(" site.older") for line in found)
    assert "xx missing the manual, xx.txt" in found
    assert "xx missing the captions publishing.xx.vtt" in found
    path.write_text(json.dumps({"name": "x", "words": {"no.such.key": "x"}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        script.stamp(path)
