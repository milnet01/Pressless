# Likes and dislikes on an entry (PRESS-0211).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0211-likes-and-dislikes.md § 5. Google is a double answering
# by step, so no test reaches the network. INV-6 to INV-8 need Firestore's rules
# or a browser: scripts/by-hand-votes-rules.py and
# scripts/by-hand-browser-checks.py hold them.
from __future__ import annotations

import contextlib
import dataclasses
import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser
from test_builder import _entry as _built_entry
from test_builder import _settings as _built_settings
from test_builder import _store as _built_store
from test_editor import _base, _editor
from test_editor import _entry as _editor_entry
from test_editor import _folder as _editor_folder
from test_page_editor import _key, _pages
from test_pages import _folder_with_menu, _github, _reshape
from test_setup import _answers, _GitHub, _saved, _setup_page, _Store
from test_sitefile import _a_file_store as _a_file_store  # noqa: F401, PLC0414 -- a fixture
from test_undo import _content, _furnished, _previous, _undo
from test_undo import _entry as _undo_entry
from test_undo import _folder as _undo_folder

from pressless import (
    builder,
    face,
    settings,
    sitefile,
    sites,
    starter,
    store,
    votes,
    votes_setup,
)
from pressless.words import say

# Written out rather than imported: shared, they would compare the module with
# itself (docs/working-here.md).
VOTE_KEY = "vote-key"
UNDONE = "Undone"
API_KEY = "sentinel-api-key-for-tests"
PROJECT = "sentinel-project"
APP_ID = "1:23:web:abc123"
RECAPTCHA = "sentinel-recaptcha-key-for-tests"
VOTES = settings.Votes(api_key=API_KEY, project_id=PROJECT, app_id=APP_ID, recaptcha_key=None)
PASTED = f'''const firebaseConfig = {{
  apiKey: "{API_KEY}",
  authDomain: "{PROJECT}.firebaseapp.com",
  projectId: "{PROJECT}",
  appId: "{APP_ID}"
}};'''
MARKUP = 'class="votes"'
FIRESTORE = "firestore.googleapis.com"
CHECK_ENTRY = "entries/0000-00-00-pressless-check/votes/"


def _with_votes(folder: Path, value: settings.Votes | None = VOTES) -> settings.Settings:
    saved = settings.load(folder)
    changed = dataclasses.replace(saved, votes=value)
    settings.save(folder, changed)
    return changed


# ------------------------------------------------------------------ INV-1 ---


def test_settings_votes_round_trip(tmp_path: Path) -> None:
    """INV-1. Breaks when a field is dropped on save, or absent and null stop
    loading as None."""
    plain = _saved(tmp_path)
    written = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert settings.load(tmp_path).votes is None and written["version"] == 1

    del written["votes"]
    (tmp_path / "settings.json").write_text(json.dumps(written), encoding="utf-8")
    assert settings.load(tmp_path).votes is None

    for held in (VOTES, dataclasses.replace(VOTES, recaptcha_key=RECAPTCHA)):
        settings.save(tmp_path, dataclasses.replace(plain, votes=held))
        written = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert written["votes"] == {"api_key": API_KEY, "project_id": PROJECT, "app_id": APP_ID,
                                    "recaptcha_key": held.recaptcha_key}
        assert settings.load(tmp_path).votes == held


def test_settings_page_keeps_votes(tmp_path: Path, monkeypatch) -> None:
    """INV-1. Breaks when setup._candidate omits `votes`, since it names every
    field of the Settings it builds."""
    _Store(monkeypatch)
    _saved(tmp_path, votes=VOTES)
    with _setup_page(tmp_path, _GitHub()) as browser:
        status, page = browser.post(_answers(key=""))
    assert status == 200, page
    assert settings.load(tmp_path).votes == VOTES


@pytest.mark.parametrize("changes", [
    {"api_key": "short"},
    {"api_key": 'sentinel-api-key"-for-tests'},
    {"api_key": "sentinel-api-key-for-tests\n"},
    {"project_id": "Capital-project"},
    {"project_id": "x"},
    {"project_id": 'sentinel"project'},
    {"app_id": "1:23:ios:abc123"},
    {"app_id": "1:23:web:abc123</script>"},
    {"recaptcha_key": "short"},
    {"recaptcha_key": "sentinel-recaptcha<key-for-tests"},
])
def test_settings_refuses_a_bad_votes_value(tmp_path: Path, changes: dict[str, str]) -> None:
    """INV-1 and § 4.1's table. Breaks when `check` lets a quote through."""
    plain = _saved(tmp_path)
    bad = dataclasses.replace(plain, votes=dataclasses.replace(VOTES, **changes))
    with pytest.raises(settings.SettingsError) as refused:
        settings.check(bad)
    assert refused.value.key == "votes"
    for value in changes.values():
        assert value not in str(refused.value)


# ------------------------------------------------------------------ INV-2 ---


def _built(tmp_path: Path, into: str, **overrides) -> dict[str, str]:
    folder = tmp_path / "data"
    if not folder.exists():
        folder = _built_store(tmp_path)
        store.write(folder, _built_entry("seaside", tags=("sea",)), draft=False)
        store.write(folder, _built_entry("harbour"), draft=False)
        store.write_forwards(folder, {"old-seaside": "seaside"})
    target = tmp_path / into
    builder.build(folder, _built_settings(**overrides), target)
    return {path.relative_to(target).as_posix(): path.read_text(encoding="utf-8")
            for path in target.rglob("*.html")}


def test_off_adds_nothing(tmp_path: Path) -> None:
    """INV-2. Breaks when the markup or style is written unconditionally."""
    pages = _built(tmp_path, "site")
    assert len(pages) > 3
    for name, page in pages.items():
        for word in (MARKUP, FIRESTORE, ".vote-count", "pressless-votes"):
            assert word not in page, (name, word)


# ------------------------------------------------------------------ INV-3 ---


def test_publish_entry_pages_only(tmp_path: Path) -> None:
    """INV-3. Breaks when the code goes through `_Build.page` for every page."""
    pages = _built(tmp_path, "site", votes=VOTES)
    code = votes.page_code(VOTES)
    entries = {name: page for name, page in pages.items()
               if "<article" in page and 'class="post-tags"' in page and "old-seaside" not in name}
    assert len(entries) == 2, sorted(pages)
    for name, page in pages.items():
        if name in entries:
            assert page.count(MARKUP) == 1 and page.count(code) == 1, name
            # It sits straight after the tags paragraph, and is disabled.
            tags_end = page.index("</p>", page.index('class="post-tags"')) + len("</p>")
            assert page[tags_end:page.index(MARKUP)].lstrip().startswith("<style>")
            assert page[:page.index("</head>")].count(code) == 1, "the code goes in the head"
            assert page.count(" disabled>") == 2, name
            key = "2020-01-02-seaside" if "seaside" in name else "2020-01-02-harbour"
            assert f'data-vote="{key}"' in page, name
        else:
            assert MARKUP not in page and FIRESTORE not in page, name
    assert any("old-seaside" in name for name in pages), "no forward was built to check"


def test_preview_has_no_code(tmp_path: Path) -> None:
    """INV-3. Breaks when `preview` passes the code."""
    folder = _built_store(tmp_path)
    entry = _built_entry("seaside")
    into = tmp_path / "preview"
    relative = builder.preview(folder, _built_settings(votes=VOTES), into, entry,
                               photo_src=lambda name: name)
    page = (into / relative).read_text(encoding="utf-8")
    assert page.count(MARKUP) == 1 and page.count(" disabled>") == 2
    assert FIRESTORE not in page and "<script" not in page


def test_buttons_are_words_with_room_for_a_number() -> None:
    """§ 3 decision 10 and § 4.3: words from Words, and a space kept empty."""
    markup = votes.buttons("2026-11-01-seaside")
    assert say("votes.like") == "Like" and say("votes.dislike") == "Dislike"
    assert ('<button type="button" class="vote" data-value="1" aria-pressed="false" disabled>'
            'Like <span class="vote-count"></span></button>') in markup
    assert ('<button type="button" class="vote" data-value="-1" aria-pressed="false" disabled>'
            'Dislike <span class="vote-count"></span></button>') in markup
    assert 'data-vote="2026-11-01-seaside"' in markup


def test_only_a_chosen_recaptcha_brings_firebase_files() -> None:
    """§ 3 decisions 7 and 8. Breaks when App Check's files load for every site."""
    plain = votes.page_code(VOTES)
    chosen = votes.page_code(dataclasses.replace(VOTES, recaptcha_key=RECAPTCHA))
    assert plain.startswith('<script type="module">') and API_KEY in plain and PROJECT in plain
    assert "gstatic" not in plain and "X-Firebase-AppCheck" not in plain
    assert "firebasejs/13.1.0/firebase-app-check.js" in chosen and RECAPTCHA in chosen


# ------------------------------------------------------------------ INV-4 ---


@pytest.mark.parametrize("hostile", [
    '2020-01-02-x" onload="alert(1)',
    "2020-01-02-<script>",
    "2020-01-02-a/b",
    "2020-01-02-a b",
    "2020-01-02-a&b",
    "2020-01-02-it's",
    "not-a-date",
    "2020-01-02-" + "a" * 190,
    "",
])
def test_hostile_vote_key_gets_no_buttons(tmp_path: Path, hostile: str) -> None:
    """INV-4. Breaks when `vote_key` returns a field unchecked."""
    entry = _built_entry("seaside", extra=((VOTE_KEY, hostile),))
    assert store.vote_key(entry) is None
    folder = _built_store(tmp_path)
    store.write(folder, entry, draft=False)
    into = tmp_path / "site"
    builder.build(folder, _built_settings(votes=VOTES), into)
    for path in into.rglob("*.html"):
        page = path.read_text(encoding="utf-8")
        assert MARKUP not in page and FIRESTORE not in page, path


def test_vote_key_is_the_field_else_the_date_and_slug() -> None:
    """§ 4.2. The longest key the rule's size test allows passes."""
    assert store.vote_key(_built_entry("seaside", "2026-03-05 09:00:00")) == "2026-03-05-seaside"
    held = _built_entry("moved", extra=((VOTE_KEY, "2019-01-01-first"),))
    assert store.vote_key(held) == "2019-01-01-first"
    longest = "2020-01-02-" + "a" * 189
    assert store.vote_key(_built_entry("x", extra=((VOTE_KEY, longest),))) == longest
    assert len(longest) == 200
    assert store.vote_key(_built_entry("a" * 190)) is None


@pytest.mark.parametrize("pasted", [
    'apiKey: "<script>alert(1)</script>xxxxx", projectId: "sentinel-project", appId: "1:2:web:a"',
    f'apiKey: "{API_KEY}", projectId: "Sentinel\\"s", appId: "{APP_ID}"',
    f'apiKey: "{API_KEY}", projectId: "{PROJECT}", appId: "1:2:web:a\\"><b>"',
    f'apiKey: "{API_KEY}", projectId: "{PROJECT}"',
    f'projectId: "{PROJECT}", appId: "{APP_ID}"',
    "",
    "not a config at all",
])
def test_parse_config_refuses_markup(pasted: str) -> None:
    """INV-4. Breaks when `parse_config` skips § 4.1, or takes a missing field."""
    with pytest.raises(settings.SettingsError) as refused:
        votes.parse_config(pasted)
    assert refused.value.key == "votes"
    assert "<script" not in str(refused.value)


def test_parse_config_reads_both_shapes() -> None:
    """§ 4.6: each `name: "value"` or `"name": "value"`."""
    found = {"api_key": API_KEY, "project_id": PROJECT, "app_id": APP_ID}
    assert votes.parse_config(PASTED) == found
    assert votes.parse_config(json.dumps({"apiKey": API_KEY, "projectId": PROJECT,
                                          "appId": APP_ID})) == found


# ------------------------------------------------------------------ INV-5 ---


def _move(browser: Browser, folder: Path, slug: str, address: str, *, draft: bool) -> dict:
    status, _, text = browser.request("POST", "/address", {
        "slug": slug, "draft": "1" if draft else "0",
        "base": _base(folder, slug, draft=draft), "address": address})
    assert status == 200, text
    reply = json.loads(text)
    assert reply["hint"] is None, reply
    return reply


def _fields(folder: Path, slug: str, *, draft: bool) -> list[str]:
    entry = store.read(store.path_for(folder, slug, draft=draft))
    return [value for name, value in entry.extra if name == VOTE_KEY]


def test_key_survives_moves_and_undo(tmp_path: Path) -> None:
    """INV-5. Breaks when `_address` overwrites a field, computes the key after
    the move, or leaves an undone draft out."""
    folder = _editor_folder(tmp_path)
    _with_votes(folder)
    first = "2020-01-02-seaside"
    store.write(folder, _editor_entry("seaside"), draft=False)
    store.write(folder, _editor_entry("gone", extra=((UNDONE, "2026-09-26 10:00:00"),)),
                draft=True)
    store.write(folder, _editor_entry("plain"), draft=True)
    with _editor(folder) as browser:
        _move(browser, folder, "seaside", "harbour", draft=False)
        assert _fields(folder, "harbour", draft=False) == [first]
        _move(browser, folder, "harbour", "bay", draft=False)
        assert _fields(folder, "bay", draft=False) == [first]
        _move(browser, folder, "bay", "seaside", draft=False)
        assert store.vote_key(store.read(store.path_for(folder, "seaside", draft=False))) == first

        _move(browser, folder, "gone", "gone-moved", draft=True)
        assert _fields(folder, "gone-moved", draft=True) == ["2020-01-02-gone"]
        _move(browser, folder, "plain", "plain-moved", draft=True)
        assert _fields(folder, "plain-moved", draft=True) == []

    # Undo turns a moved entry the older state lacks back into a draft, field kept.
    (tmp_path / "undo").mkdir()
    folder = _undo_folder(tmp_path / "undo")
    moved = _undo_entry("moved", extra=((VOTE_KEY, first),))
    store.write(folder, moved, draft=False)
    files = {**_furnished(tmp_path / "undo"),
             **_content(tmp_path / "undo", published=(_undo_entry("seaside"),))}
    _undo(folder, _previous(files))
    assert _fields(folder, "moved", draft=True) == [first]


def test_a_move_with_votes_off_adds_no_field(tmp_path: Path) -> None:
    """§ 6: an entry moved while `votes` was off has no field."""
    folder = _editor_folder(tmp_path)
    store.write(folder, _editor_entry("seaside"), draft=False)
    with _editor(folder) as browser:
        _move(browser, folder, "seaside", "harbour", draft=False)
    assert _fields(folder, "harbour", draft=False) == []


def test_kept_draft_has_no_key(tmp_path: Path) -> None:
    """INV-5. Breaks when `_keep` copies the field."""
    folder = _undo_folder(tmp_path)
    store.write(folder, _undo_entry("seaside", body="His newer words.",
                                    extra=((VOTE_KEY, "2019-01-01-first"),)), draft=False)
    files = {**_furnished(tmp_path),
             **_content(tmp_path, published=(_undo_entry("seaside", body="The older words."),))}
    _undo(folder, _previous(files))
    assert _fields(folder, "seaside-before-undo", draft=True) == []


# ------------------------------------------------------------------ INV-9 ---


ANALYTICS, FIREBASE, CAPTCHA = "Google Analytics", "Firebase", "reCAPTCHA"


@pytest.mark.parametrize(("counting", "voting", "recaptcha"), [
    (True, False, False), (False, True, False), (False, True, True), (True, True, True),
])
def test_privacy_says_only_what_is_on(counting: bool, voting: bool, recaptcha: bool) -> None:
    """INV-9. Breaks when `privacy_page` keeps its counting words unconditionally."""
    page = starter.privacy_page("A site", ("look/style.css",), counting=counting, votes=voting,
                                recaptcha=recaptcha)
    assert (ANALYTICS in page) is counting
    assert (FIREBASE in page) is voting
    assert (CAPTCHA in page) is recaptcha
    if voting:
        for word in ("random id", "can be read by anyone", "email address",
                     "internet address", "policies.google.com/privacy"):
            assert word in page, word


def _privacy_text(folder: Path, *, waiting: bool = False) -> str:
    return store.read_html(store.html_path_for(folder, store.PAGES_FOLDER, "privacy",
                                               waiting=waiting))


def _site(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    starter.fill(folder, "A site")
    return folder


def test_privacy_adds_each_once(tmp_path: Path) -> None:
    """INV-9. Each disclosure reaches an existing page once. Breaks when words
    are added where the page has them, or a waiting copy is left behind."""
    folder = _site(tmp_path / "data")
    assert starter.add_privacy(folder, "A site", counting=True, votes=False,
                               recaptcha=False)[0] is True
    assert FIREBASE not in _privacy_text(folder)

    assert starter.add_privacy(folder, "A site", counting=True, votes=True,
                               recaptcha=False)[0] is False
    text = _privacy_text(folder)
    assert text.count(FIREBASE) >= 1 and CAPTCHA not in text
    assert text.index(FIREBASE) < text.index("<!-- /pressless:page -->")

    starter.add_privacy(folder, "A site", counting=True, votes=True, recaptcha=True)
    with_all = _privacy_text(folder)
    assert CAPTCHA in with_all and with_all.startswith(text.split("<!-- /pressless:page -->")[0])

    starter.add_privacy(folder, "A site", counting=True, votes=True, recaptcha=True)
    assert _privacy_text(folder) == with_all

    # A page lacking only the counting words gains them too.
    store.write_html(folder, store.PAGES_FOLDER, "privacy",
                     "<main><p>We use firebase, says the writer.</p></main>")
    starter.add_privacy(folder, "A site", counting=True, votes=True, recaptcha=False)
    own = _privacy_text(folder)
    assert "We use firebase" in own and FIREBASE not in own, "his own wording stands"
    assert ANALYTICS in own and own.index(ANALYTICS) < own.index("</main>")

    # With no main either, the words go at the end.
    store.write_html(folder, store.PAGES_FOLDER, "privacy", "<p>Bare.</p>")
    starter.add_privacy(folder, "A site", counting=False, votes=True, recaptcha=False)
    assert _privacy_text(folder).startswith("<p>Bare.</p>")
    assert FIREBASE in _privacy_text(folder)

    # A waiting copy replaces the page when pressed, so it gets them as well.
    store.write_html(folder, store.PAGES_FOLDER, "privacy", "<main><p>Live.</p></main>")
    store.write_html(folder, store.PAGES_FOLDER, "privacy", "<main><p>Waiting.</p></main>",
                     waiting=True)
    starter.add_privacy(folder, "A site", counting=False, votes=True, recaptcha=False)
    assert FIREBASE in _privacy_text(folder) and FIREBASE in _privacy_text(folder, waiting=True)


def test_privacy_adds_nothing_to_a_store_with_no_site(tmp_path: Path) -> None:
    """INV-9: a Store holding no site gets no page."""
    assert starter.add_privacy(tmp_path, "A site", counting=False, votes=True,
                               recaptcha=False) == (False, False)
    assert not store.html_path_for(tmp_path, store.PAGES_FOLDER, "privacy").exists()


def test_privacy_page_stays_while_votes_on(tmp_path: Path, monkeypatch) -> None:
    """INV-9. Breaks when `_reshape_hint` still reads `measurement_id` alone."""
    _key(monkeypatch)
    folder = _folder_with_menu(tmp_path)
    store.write_html(folder, "pages", "privacy", "<p>Privacy</p>")
    _with_votes(folder)
    with _pages(folder, _github()) as browser:
        reply = _reshape(browser, "remove", "privacy")
    assert reply["published"] is False and reply["hint"]
    assert store.html_path_for(folder, store.PAGES_FOLDER, "privacy").is_file()


def test_a_settings_save_adds_privacy_for_votes(tmp_path: Path, monkeypatch) -> None:
    """§ 4.5. Breaks when `setup._privacy` runs on `measurement_id` alone."""
    _Store(monkeypatch)
    _site(tmp_path)
    _saved(tmp_path, votes=VOTES)
    with _setup_page(tmp_path, _GitHub()) as browser:
        browser.post(_answers(key=""))
    text = _privacy_text(tmp_path)
    assert FIREBASE in text and ANALYTICS not in text


# ----------------------------------------------------------------- INV-10 ---


class _Google:
    """Answers each of Check's steps with `answers[step]`: a status, or an
    OSError to raise. Every step not named passes."""

    PASSES = {"signup": 200, "first": 200, "second": 403, "count": 200, "delete": 200}

    def __init__(self, **answers) -> None:
        self.answers = {**self.PASSES, **answers}
        self.steps: list[str] = []
        self.count_headers: dict[str, str] = {}
        self.paths: list[str] = []

    def _step(self, method: str, url: str, body: bytes | None) -> str:
        if "accounts:signUp" in url:
            return "signup"
        self.paths.append(url)
        if method == "DELETE":
            return "delete"
        if url.split("?")[0].endswith(":runAggregationQuery"):
            return "count"
        sent = json.loads(body or b"{}")["fields"]["value"]["integerValue"]
        return {"1": "first", "5": "second"}[sent]

    def request(self, method, url, body, headers):
        step = self._step(method, url, body)
        self.steps.append(step)
        if step == "count":
            self.count_headers = headers
        answer = self.answers[step]
        if isinstance(answer, OSError):
            raise answer
        if step == "signup" and answer == 200:
            reply = {"idToken": "sentinel-id-token", "localId": "sentinel-visitor"}
        elif step == "count" and answer == 200:
            reply = [{"result": {"aggregateFields": {"n": {"integerValue": "1"}}}}]
        else:
            reply = {}
        return answer, {}, json.dumps(reply).encode("utf-8")


@contextlib.contextmanager
def _screen(folder: Path, google: _Google | None = None) -> Iterator[Browser]:
    served = face.serve(folder)
    try:
        votes_setup.register(served, folder, client=google)
        yield Browser(served)
    finally:
        served.stop()


NO_ANSWER = OSError("no answer")
READY = "votes_setup.check.ready"
ANONYMOUS = "votes_setup.check.anonymous"
NO_RULES = "votes_setup.check.rules"
WRONG_RULES = "votes_setup.check.rules_wrong"
NO_DATABASE = "votes_setup.check.database"
UNREACHABLE = "votes_setup.check.unreachable"


@pytest.mark.parametrize(("answers", "said", "delete_sent"), [
    ({}, READY, True),
    ({"signup": 400}, ANONYMOUS, False),
    ({"signup": NO_ANSWER}, UNREACHABLE, False),
    ({"signup": 503}, UNREACHABLE, False),
    ({"first": 403}, NO_RULES, False),
    ({"first": 404}, NO_DATABASE, False),
    ({"first": NO_ANSWER}, UNREACHABLE, False),
    ({"first": 500}, UNREACHABLE, False),
    ({"second": 200}, WRONG_RULES, True),
    ({"second": NO_ANSWER}, UNREACHABLE, True),
    ({"second": 500}, UNREACHABLE, True),
    ({"count": 403}, WRONG_RULES, True),
    ({"count": NO_ANSWER}, UNREACHABLE, True),
    ({"count": 500}, UNREACHABLE, True),
    ({"delete": 403}, WRONG_RULES, True),
    ({"delete": NO_ANSWER}, UNREACHABLE, True),
    ({"second": 200, "delete": NO_ANSWER}, WRONG_RULES, True),
])
def test_check_answers(tmp_path: Path, answers: dict, said: str, delete_sent: bool) -> None:
    """INV-10: § 4.6's answer for each reply, and the test vote removed on every
    path past the first write. Breaks when a 403 on the first write reads as
    "could not reach Google", or a failure skips the delete."""
    _saved(tmp_path, votes=VOTES)
    google = _Google(**answers)
    with _screen(tmp_path, google) as browser:
        status, _, page = browser.request("POST", "/votes/check")
    assert status == 200, page
    assert say(said) in page, (answers, page)
    others = {READY, ANONYMOUS, NO_RULES, WRONG_RULES, NO_DATABASE, UNREACHABLE} - {said}
    for other in others:
        assert say(other) not in page, other
    assert ("delete" in google.steps) is delete_sent, google.steps


def test_check_order_and_where_it_writes(tmp_path: Path) -> None:
    """§ 4.6's order, on the check's own entry, counting with no sign-in."""
    _saved(tmp_path, votes=VOTES)
    google = _Google()
    with _screen(tmp_path, google) as browser:
        browser.request("POST", "/votes/check")
    assert google.steps == ["signup", "first", "second", "count", "delete"]
    assert f"projects/{PROJECT}/databases/(default)/documents/{CHECK_ENTRY}sentinel-visitor" in (
        google.paths[0])
    assert "Authorization" not in google.count_headers


def test_check_does_not_run_with_recaptcha(tmp_path: Path) -> None:
    """§ 4.6. Breaks when Check calls Google with App Check set."""
    _saved(tmp_path, votes=dataclasses.replace(VOTES, recaptcha_key=RECAPTCHA))
    google = _Google()
    with _screen(tmp_path, google) as browser:
        page = browser.request("POST", "/votes/check")[2]
    assert google.steps == []
    assert say("votes_setup.check.recaptcha") in page


# ----------------------------------------------------------------- INV-11 ---


def test_off_keeps_keys_and_privacy(tmp_path: Path) -> None:
    """INV-11. Breaks when switching off strips fields or rewrites the page."""
    _site(tmp_path)
    _saved(tmp_path, votes=VOTES)
    starter.add_privacy(tmp_path, "A site", counting=False, votes=True, recaptcha=False)
    held = _built_entry("moved", extra=((VOTE_KEY, "2019-01-01-first"),))
    store.write(tmp_path, held, draft=False)
    privacy = _privacy_text(tmp_path)

    with _screen(tmp_path) as browser:
        status, _, page = browser.request("POST", "/votes/off")
    assert status == 200, page

    saved = settings.load(tmp_path)
    assert saved.votes is None and saved.repository == "owner/owner.github.io"
    assert _privacy_text(tmp_path) == privacy
    assert _fields(tmp_path, "moved", draft=False) == ["2019-01-01-first"]
    into = tmp_path / "built"
    builder.build(tmp_path, saved, into)
    for path in into.rglob("*.html"):
        assert MARKUP not in path.read_text(encoding="utf-8"), path


# ----------------------------------------------------------------- INV-12 ---


def test_site_file_carries_votes(tmp_path: Path) -> None:
    """INV-12. Breaks when `sitefile`'s rewrite of the settings names its keys."""
    own = tmp_path / "from"
    own.mkdir()
    site = sites.open_site(own)
    _saved(site, votes=VOTES)
    target = tmp_path / "saved.zip"
    sitefile.save(site, target)
    fresh = tmp_path / "to"
    fresh.mkdir()
    shutil.rmtree(fresh / "sites", ignore_errors=True)
    assert settings.load(sitefile.open_into(target, fresh)).votes == VOTES


# --------------------------------------------------------------- the screen ---


def test_the_screen_gives_the_steps_and_the_rules(tmp_path: Path) -> None:
    """§ 4.6: each step, the rules to copy, the warning, and App Check's cost."""
    _saved(tmp_path)
    with _screen(tmp_path) as browser:
        page = browser.request("GET", "/votes")[2]
    for number in range(1, 6):
        assert say(f"votes_setup.step.{number}") in page, number
    assert say("votes_setup.warning") in page and say("votes_setup.app_check") in page
    assert "request.auth.uid == voter" in page and "<details" in page
    assert 'name="config"' in page and 'name="recaptcha_key"' in page
    assert say("votes_setup.off") not in page, "off is offered only while on"


def test_the_settings_page_links_to_the_screen(tmp_path: Path) -> None:
    """§ 4.6: reached from a row on the Settings page."""
    _saved(tmp_path)
    with _setup_page(tmp_path, _GitHub()) as browser:
        assert 'href="/votes"' in browser.request("GET", "/setup")[2]


def test_a_save_stores_adds_privacy_and_checks(tmp_path: Path) -> None:
    """§ 4.6: saving runs § 4.5, then Check, and says when buttons appear."""
    _site(tmp_path)
    _saved(tmp_path)
    google = _Google()
    with _screen(tmp_path, google) as browser:
        page = browser.request("POST", "/votes", {"config": PASTED, "recaptcha_key": ""})[2]
    assert settings.load(tmp_path).votes == VOTES
    assert FIREBASE in _privacy_text(tmp_path)
    assert say("votes_setup.saved") in page and say(READY) in page
    assert google.steps[-1] == "delete"


def test_a_save_keeps_settings_when_privacy_fails(tmp_path: Path, monkeypatch) -> None:
    """§ 4.5: a failure keeps the settings, as PRESS-0199 § 4.5 does."""
    _site(tmp_path)
    _saved(tmp_path)

    def refuse(*args, **kwargs):
        raise store.StoreError("the disk is full")

    monkeypatch.setattr(starter, "add_privacy", refuse)
    with _screen(tmp_path, _Google()) as browser:
        page = browser.request("POST", "/votes", {"config": PASTED, "recaptcha_key": ""})[2]
    assert settings.load(tmp_path).votes == VOTES
    assert say("setup.privacy.failed") in page


@pytest.mark.parametrize(("form", "hint"), [
    ({"config": "not a config"}, "votes_setup.hint"),
    ({"config": PASTED.replace(API_KEY, "<b>")}, "votes_setup.hint"),
    ({"config": PASTED, "recaptcha_key": "<short>"}, "votes_setup.hint.recaptcha"),
])
def test_a_refused_paste_saves_nothing(tmp_path: Path, form: dict[str, str], hint: str) -> None:
    """§ 4.6: a hint beside the box, nothing saved, nothing asked of Google."""
    _saved(tmp_path)
    google = _Google()
    with _screen(tmp_path, google) as browser:
        page = browser.request("POST", "/votes", form)[2]
    assert say(hint) in page
    assert settings.load(tmp_path).votes is None and google.steps == []
    assert "<b>" not in page.split('name="config"')[1].split("</textarea>")[0]


def test_the_screen_says_when_it_is_on(tmp_path: Path) -> None:
    """§ 4.6: the state first, with Check and off beside it."""
    _saved(tmp_path, votes=VOTES)
    with _screen(tmp_path) as browser:
        page = browser.request("GET", "/votes")[2]
    assert say("votes_setup.on", project=PROJECT) in page
    assert 'action="/votes/check"' in page and 'action="/votes/off"' in page


def test_the_screen_before_setup(tmp_path: Path) -> None:
    """A Face with no settings yet says so, and saves nothing."""
    with _screen(tmp_path) as browser:
        assert say("setup.first") in browser.request("GET", "/votes")[2]
        assert say("setup.first") in browser.request("POST", "/votes", {"config": PASTED})[2]
    assert not (tmp_path / "settings.json").exists()
