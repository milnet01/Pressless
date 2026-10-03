# Publish: one button writes, builds and publishes (PRESS-0013).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0013-publish.md
# § 5. The words the page must carry are written out here rather than imported:
# shared, they would compare the module against itself (CLAUDE.md, the trap
# recorded for test_settings.py).
#
# GitHub is the Publisher tests' own recording double, answering by URL, and
# Credentials is a double, so no test reaches the network or a real keyring.
from __future__ import annotations

import contextlib
import hashlib
import html
import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from _face_session import Browser
from test_editor import _binned
from test_publisher import _listing, _reads, _Transport, _tree_creation_paths, _writes

from pressless import builder, credentials, editor, face, publisher, publishing, settings, store

KEY = "ghp_SENTINELpublishingKEY0123456789"
REPLACES = "Replaces"
UNKNOWN_WORDS = "Pressless cannot tell whether your site changed."
HEADER = "<header>{{NAVIGATION}}</header>\n"
NAVIGATION = '<nav><a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a></nav>'
FOOTER = "<footer>{{YEAR}}</footer>\n"
NOW = datetime(2026, 9, 17, 10, 0, 0, 123456)


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    for name, text in (("header", HEADER), ("navigation", NAVIGATION), ("footer", FOOTER)):
        store.write_html(folder, store.FURNITURE_FOLDER, name, text)
    settings.save(folder, _settings(folder))
    return folder


def _settings(folder: Path) -> settings.Settings:
    return settings.Settings(
        site_folder=folder / "site", repository="owner/owner.github.io",
        site_address="https://example.org",
        daily_prompt_filter="", untouchable=("CNAME",),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None)


def _entry(slug: str, *, body: str = "Words.", date: str = "2014-11-09 21:32:00",
           extra: tuple[tuple[str, str], ...] = ()) -> store.Entry:
    return store.Entry(slug=slug, title=slug.title(), date=datetime.fromisoformat(date),
                       categories=(), tags=(), body=body, extra=extra)


def _github(**kwargs) -> _Transport:
    return _Transport(reads=_reads(_listing([])), writes=_writes(), **kwargs)


def _refusing() -> _Transport:
    return _Transport(responses=[(401, {}, b'{"message": "Bad credentials"}')])


def _key(monkeypatch: pytest.MonkeyPatch, *, raises: Exception | None = None) -> None:
    def read(kind: str, folder: Path, account: str) -> str:
        if raises is not None:
            raise raises
        return KEY
    monkeypatch.setattr(credentials, "read", read)


def _base(folder: Path, slug: str, *, draft: bool) -> str:
    return hashlib.sha256(store.path_for(folder, slug, draft=draft).read_bytes()).hexdigest()


def _state(folder: Path) -> dict[tuple[bool, str], store.Entry]:
    return {(draft, slug): store.read(store.path_for(folder, slug, draft=draft))
            for draft in (True, False) for slug in store.list_slugs(folder, draft=draft)}


class _Browser(Browser):
    def __init__(self, served: face.Face) -> None:
        super().__init__(served, timeout=30)

    def publish(self, slug: str, draft: bool, base: str, *, body: str | None = None,
                folder: Path) -> tuple[int, str]:
        entry = store.read(store.path_for(folder, slug, draft=draft))
        form = {"slug": slug, "draft": "1" if draft else "0", "base": base,
                "title": entry.title, "categories": "", "tags": "",
                "body": entry.body if body is None else body}
        status, _, page = self.request("POST", "/publish", form)
        return status, page


@contextlib.contextmanager
def _pressless(folder: Path, transport: _Transport) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=transport)
        yield _Browser(served)
    finally:
        served.stop()


# ------------------------------------------------------------------ INV-1 ---


def test_a_draft_is_dated_and_published(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    monkeypatch.setattr(publishing, "_now", lambda: NOW)
    _key(monkeypatch)
    github = _github()
    with _pressless(folder, github) as browser:
        status, text = browser.publish("seaside", True, _base(folder, "seaside", draft=True),
                                       folder=folder)
    assert status == 200, text
    reply = json.loads(text)
    assert reply["published"] is True and reply["slug"] == "seaside"
    assert reply["draft"] is False
    assert store.list_slugs(folder, draft=True) == ()
    published = store.read(store.path_for(folder, "seaside", draft=False))
    assert published.date == datetime(2026, 9, 17, 10, 0, 0)
    assert "blog/2026/09/17/seaside/index.html" in (_tree_creation_paths(github) or set())


# ------------------------------------------------------------------ INV-2 ---


def test_a_working_copy_is_published_over_its_entry(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Before."), draft=False)
    store.write(folder, _entry("seaside-changes", body="After.", date="2020-01-01 00:00:00",
                               extra=((REPLACES, "seaside"),)), draft=True)
    _key(monkeypatch)
    with _pressless(folder, _github()) as browser:
        status, text = browser.publish("seaside-changes", True,
                                       _base(folder, "seaside-changes", draft=True),
                                       folder=folder)
    assert status == 200, text
    published = store.read(store.path_for(folder, "seaside", draft=False))
    assert published.body == "After."
    assert published.date == datetime(2014, 11, 9, 21, 32)
    assert all(name != REPLACES for name, _ in published.extra)
    assert store.list_slugs(folder, draft=True) == ()
    assert _binned(folder) == ["seaside-changes.txt"]


def test_a_copy_left_behind_is_said(tmp_path, monkeypatch):
    """§ 4.2: a working copy that cannot be binned after a publish that
    succeeded is named in the reply, and its site part says the site was
    updated -- never that it did not change (PRESS-0145)."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Before."), draft=False)
    store.write(folder, _entry("seaside-changes", body="After.", date="2020-01-01 00:00:00",
                               extra=((REPLACES, "seaside"),)), draft=True)
    _key(monkeypatch)

    def cannot_bin(folder, path):
        raise store.StoreError("the bin is not writable")

    monkeypatch.setattr(store, "move_to_bin", cannot_bin)
    with _pressless(folder, _github()) as browser:
        status, text = browser.publish("seaside-changes", True,
                                       _base(folder, "seaside-changes", draft=True),
                                       folder=folder)
    assert status == 200, text
    reply = json.loads(text)
    assert reply["published"] is True, reply
    notices = html.unescape(reply["notices"])
    assert "was left in place after publishing" in notices, notices
    assert "Your site has been updated." in notices, notices
    assert "Your site has not changed." not in notices, notices


# ------------------------------------------------------------------ INV-3 ---


def test_a_failed_publish_puts_the_files_back(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Before."), draft=False)
    store.write(folder, _entry("seaside-changes", body="After.",
                               extra=((REPLACES, "seaside"),)), draft=True)
    store.write(folder, _entry("harbour"), draft=True)
    saved = _settings(folder)
    before = _state(folder)

    for entry in ("seaside-changes", "harbour"):
        with pytest.raises(publisher.Refused):
            publishing.publish(folder, saved, KEY, entry=entry, transport=_refusing())
        assert _state(folder) == before, entry
        assert _binned(folder) == []

    def stopped(*args, **kwargs):
        raise builder.BuildStopped("a file cannot be built")

    monkeypatch.setattr(builder, "build", stopped)
    for entry in ("seaside-changes", "harbour"):
        with pytest.raises(builder.BuildStopped):
            publishing.publish(folder, saved, KEY, entry=entry, transport=_github())
        assert _state(folder) == before, entry
        assert _binned(folder) == []


def test_a_stop_during_the_upload_puts_nothing_back(tmp_path, monkeypatch):
    """PRESS-0162 (review-code L7.3): a KeyboardInterrupt mid-upload is not
    an Exception, so it reached the put-back -- though GitHub may already
    have taken the upload, and § 4.6 never puts back an entry whose
    publish outcome is unknown. The stop still goes on up."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("harbour"), draft=True)
    saved = _settings(folder)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(publisher, "publish", interrupted)
    with pytest.raises(KeyboardInterrupt):
        publishing.publish(folder, saved, KEY, entry="harbour", transport=_github())
    assert store.list_slugs(folder, draft=False) == ("harbour",)
    assert store.list_slugs(folder, draft=True) == ()


# ------------------------------------------------------------------ INV-4 ---


def test_an_unknown_outcome_stays_published(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Before."), draft=False)
    store.write(folder, _entry("seaside-changes", body="After.",
                               extra=((REPLACES, "seaside"),)), draft=True)
    _key(monkeypatch)
    with _pressless(folder, _github(fail_at="/git/refs")) as browser:
        status, text = browser.publish("seaside-changes", True,
                                       _base(folder, "seaside-changes", draft=True),
                                       folder=folder)
    assert status == 200, text
    reply = json.loads(text)
    assert reply["published"] is False and UNKNOWN_WORDS in reply["failure"]
    assert store.read(store.path_for(folder, "seaside", draft=False)).body == "After."
    assert _binned(folder) == ["seaside-changes.txt"]
    assert reply["slug"] == "seaside" and reply["draft"] is False


def test_an_unknown_outcome_says_the_copy_was_left(tmp_path, monkeypatch):
    """§ 4.3: a working copy that cannot be binned after an unknown outcome is
    named in a notice whose site part is unknown (PRESS-0147)."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Before."), draft=False)
    store.write(folder, _entry("seaside-changes", body="After.",
                               extra=((REPLACES, "seaside"),)), draft=True)
    _key(monkeypatch)

    def cannot_bin(folder, path):
        raise store.StoreError("the bin is not writable")

    monkeypatch.setattr(store, "move_to_bin", cannot_bin)
    with _pressless(folder, _github(fail_at="/git/refs")) as browser:
        status, text = browser.publish("seaside-changes", True,
                                       _base(folder, "seaside-changes", draft=True),
                                       folder=folder)
    assert status == 200, text
    reply = json.loads(text)
    assert reply["published"] is False and UNKNOWN_WORDS in reply["failure"]
    assert store.list_slugs(folder, draft=True) == ("seaside-changes",)
    notices = html.unescape(reply["notices"])
    assert "waiting draft from this publish was left in place" in notices, notices
    assert "Pressless cannot tell whether your site changed." in notices, notices
    assert "was left in place after publishing" not in notices, notices
    assert "Your site has been updated." not in notices, notices


# ------------------------------------------------------------------ INV-5 ---


def test_nothing_moves_without_a_key(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    _key(monkeypatch, raises=credentials.NotStored("no key"))
    github = _github()
    with _pressless(folder, github) as browser:
        status, text = browser.publish("seaside", True, _base(folder, "seaside", draft=True),
                                       folder=folder)
    assert status == 200, text
    assert json.loads(text)["published"] is False
    assert store.list_slugs(folder, draft=True) == ("seaside",)
    assert store.read(store.path_for(folder, "seaside", draft=True)).date == datetime(
        2014, 11, 9, 21, 32)
    assert github.requests == []


# ------------------------------------------------------------------ INV-6 ---


def test_publishing_nothing_is_refused(tmp_path):
    folder = _folder(tmp_path)
    saved = _settings(folder)
    github = _github()
    with pytest.raises(publishing.NothingToPublish):
        publishing.publish(folder, saved, KEY, entry=None, transport=github)
    assert not saved.site_folder.exists()
    assert github.requests == []

    publishing.publish(folder, saved, KEY, entry=None, emptying=True, transport=github)
    assert saved.site_folder.is_dir()
    assert github.requests


# ------------------------------------------------------------------ INV-7 ---


def test_the_key_is_never_shown(tmp_path, monkeypatch, capfd):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    store.write(folder, _entry("harbour"), draft=True)
    _key(monkeypatch)
    bodies = []
    with _pressless(folder, _github()) as browser:
        bodies.append(browser.publish("seaside", True, _base(folder, "seaside", draft=True),
                                      folder=folder)[1])
    with _pressless(folder, _refusing()) as browser:
        bodies.append(browser.publish("harbour", True, _base(folder, "harbour", draft=True),
                                      folder=folder)[1])
    assert "Refused" not in bodies[0] and json.loads(bodies[1])["published"] is False
    log = (folder / "pressless.log").read_text(encoding="utf-8")
    out, err = capfd.readouterr()
    for text in (*bodies, log, out, err):
        assert KEY not in text


# ------------------------------------------------------------------ INV-9 ---


def test_a_failed_publish_names_the_saved_file(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    _key(monkeypatch)
    with _pressless(folder, _refusing()) as browser:
        status, text = browser.publish("seaside", False,
                                       _base(folder, "seaside", draft=False),
                                       body="Changed.", folder=folder)
    assert status == 200, text
    reply = json.loads(text)
    copy = editor.working_copy(folder, "seaside")
    assert reply["published"] is False and copy is not None
    assert reply["slug"] == copy and reply["draft"] is True
    assert reply["base"] == _base(folder, copy, draft=True)


# ---------------------------------------- PRESS-0015 INV-3, INV-4, INV-5 ---
#
# The three that live here rather than in tests/test_undo.py: each is about
# what `publishing._move` does with the mark undo leaves, not about the undo
# sequence (docs/specs/PRESS-0015-undo.md § 5).


UNDONE = "Undone"


def test_a_demoted_draft_keeps_its_date(tmp_path, monkeypatch):
    """PRESS-0015 INV-3: publishing a demoted draft again keeps the date it
    carried as a published entry, and strips the mark."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", date="2014-11-09 21:32:00",
                               extra=((UNDONE, "2026-09-21 14:02:11"),)), draft=True)
    monkeypatch.setattr(publishing, "_now", lambda: NOW)
    _key(monkeypatch)
    with _pressless(folder, _github()) as browser:
        status, text = browser.publish("seaside", True, _base(folder, "seaside", draft=True),
                                       folder=folder)
    assert status == 200, text
    published = store.read(store.path_for(folder, "seaside", draft=False))
    assert published.date == datetime(2014, 11, 9, 21, 32)
    assert all(name != UNDONE for name, _ in published.extra)
    assert UNDONE not in store.path_for(folder, "seaside", draft=False).read_text("utf-8")


def test_a_copy_of_a_demoted_entry_publishes_over_it(tmp_path, monkeypatch):
    """PRESS-0015 INV-4: a working copy whose `Replaces` names a demoted draft
    publishes over that address, and both drafts are binned."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Before.", date="2014-11-09 21:32:00",
                               extra=((UNDONE, "2026-09-21 14:02:11"),)), draft=True)
    store.write(folder, _entry("seaside-changes", body="After.",
                               date="2020-01-01 00:00:00",
                               extra=((REPLACES, "seaside"),)), draft=True)
    monkeypatch.setattr(publishing, "_now", lambda: NOW)
    _key(monkeypatch)
    with _pressless(folder, _github()) as browser:
        status, text = browser.publish("seaside-changes", True,
                                       _base(folder, "seaside-changes", draft=True),
                                       folder=folder)
    assert status == 200, text
    published = store.read(store.path_for(folder, "seaside", draft=False))
    assert published.body == "After."
    assert published.date == datetime(2014, 11, 9, 21, 32)
    assert all(name not in (REPLACES, UNDONE) for name, _ in published.extra)
    assert store.list_slugs(folder, draft=True) == ()
    assert _binned(folder) == ["seaside-changes.txt", "seaside.txt"]


def test_a_replaces_naming_a_plain_draft_is_not_a_copy(tmp_path, monkeypatch):
    """PRESS-0015 INV-5: the widening in INV-4 keys on the mark, not on
    `Replaces` alone -- otherwise one draft would destroy another."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Mine.", date="2014-11-09 21:32:00"),
                draft=True)
    store.write(folder, _entry("seaside-changes", body="After.",
                               extra=((REPLACES, "seaside"),)), draft=True)
    monkeypatch.setattr(publishing, "_now", lambda: NOW)
    _key(monkeypatch)
    with _pressless(folder, _github()) as browser:
        status, text = browser.publish("seaside-changes", True,
                                       _base(folder, "seaside-changes", draft=True),
                                       folder=folder)
    assert status == 200, text
    assert store.list_slugs(folder, draft=False) == ("seaside-changes",)
    published = store.read(store.path_for(folder, "seaside-changes", draft=False))
    assert published.body == "After."
    left = store.read(store.path_for(folder, "seaside", draft=True))
    assert left.body == "Mine." and left.date == datetime(2014, 11, 9, 21, 32)


def test_a_move_that_cannot_publish_leaves_the_draft_as_it_was(tmp_path, monkeypatch):
    """PRESS-0135 #26: step 1 rewrites an ordinary draft (dated, its marks
    stripped) and then publishes it. Where that publish fails -- a slug already
    published, a refused rename -- nothing had been recorded to put back, so
    the draft stayed rewritten. It is written back before the failure is
    raised.

    Breaks when the draft is rewritten and not restored on a failed move.
    """
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Mine.", extra=((publishing.UNDONE, "then"),)),
                draft=True)
    before = store.path_for(folder, "seaside", draft=True).read_bytes()

    def refused(*args, **kwargs):
        raise store.SlugInUse("seaside is already published")

    monkeypatch.setattr(store, "publish", refused)
    with pytest.raises(store.SlugInUse):
        publishing.publish(folder, _settings(folder), "a-key", entry="seaside",
                           transport=_github())
    assert store.path_for(folder, "seaside", draft=True).read_bytes() == before


# PRESS-0214 INV-5, INV-6 (docs/specs/PRESS-0214-journal-switch.md § 4.3).


def test_the_guard_runs_only_with_a_journal(tmp_path):
    """INV-5. Breaks when the guard ignores the switch, or is dropped."""
    folder = _folder(tmp_path)
    saved = _settings(folder)
    store.write_journal(folder, False)
    github = _github()
    publishing.publish(folder, saved, KEY, entry=None, transport=github)
    assert github.requests

    store.write_journal(folder, True)
    with pytest.raises(publishing.NothingToPublish):
        publishing.publish(folder, saved, KEY, entry=None, transport=_github())


def test_an_entry_will_not_publish_with_the_journal_off(tmp_path):
    """INV-6. Breaks when the check runs after the move, or not at all."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=True)
    store.write_journal(folder, False)
    before = _state(folder)
    github = _github()
    with pytest.raises(publishing.JournalOff):
        publishing.publish(folder, _settings(folder), KEY, entry="seaside", transport=github)
    assert _state(folder) == before
    assert github.requests == []
    assert face.sentence_for(publishing.JournalOff("x"), publishing=False).what


# PRESS-0126 INV-9 to INV-12 (docs/specs/PRESS-0126-starter-site.md § 4.5).
# The marker's name is written out rather than imported.

MARKER = "starter-unpublished"


def _starter_folder(tmp_path: Path) -> Path:
    folder = _folder(tmp_path)
    store.write_journal(folder, False)
    (folder / MARKER).write_bytes(b"")
    return folder


def _holding(*names: str, refuse_writes: bool = False) -> _Transport:
    writes = [("", (401, {}, b'{"message": "Bad credentials"}'))] if refuse_writes else _writes()
    return _Transport(reads=_reads(_listing([(name, "sha") for name in names])), writes=writes)


def test_the_starter_will_not_replace_a_site(tmp_path):
    """INV-9. Breaks when the check folds no case, runs after the build, or
    treats any root entry as a site."""
    for case, root, refused in (("html", ("Index.html",), True),
                                ("md", ("index.md",), True),
                                ("readme", ("README.md",), False)):
        base = tmp_path / case
        base.mkdir()
        folder = _starter_folder(base)
        saved = _settings(folder)
        github = _holding(*root)
        if refused:
            with pytest.raises(publishing.WouldReplaceASite):
                publishing.publish(folder, saved, KEY, entry=None, transport=github)
            assert not saved.site_folder.exists(), case
            assert all(method == "GET" for method, *_ in github.requests), case
        else:
            publishing.publish(folder, saved, KEY, entry=None, transport=github)
            assert saved.site_folder.is_dir(), case


def test_the_marker_outlives_only_a_failed_publish(tmp_path):
    """INV-10. Breaks when the marker is removed before the upload, or never."""
    folder = _starter_folder(tmp_path)
    saved = _settings(folder)
    with pytest.raises(publisher.PublishError):
        publishing.publish(folder, saved, KEY, entry=None,
                           transport=_holding(refuse_writes=True))
    assert (folder / MARKER).exists()
    publishing.publish(folder, saved, KEY, entry=None, transport=_github())
    assert not (folder / MARKER).exists()


def test_an_imported_site_publishes_as_before(tmp_path):
    """INV-11. Breaks when the check runs on every publish."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    github = _github()
    publishing.publish(folder, _settings(folder), KEY, entry=None, transport=github)
    assert github.requests
    assert not any(url.endswith("/commits/HEAD") for _method, url, *_ in github.requests)


def test_replace_needs_the_name_and_publishes_nothing(tmp_path):
    """INV-12. Breaks when the name is not checked, the marker stays, or the
    page publishes."""
    from test_editor import _Browser as _PageBrowser
    folder = _starter_folder(tmp_path)
    github = _github()
    served = face.serve(folder)
    try:
        publishing.register(served, folder, transport=github)
        browser = _PageBrowser(served)
        _, _, page = browser.request("GET", "/publish/replace")
        browser.request("POST", "/publish/replace", {"repository": "someone/else"})
        kept = settings.load(folder).untouchable
        marked = (folder / MARKER).exists()
        status, _, _ = browser.request(
            "POST", "/publish/replace", {"repository": " owner/owner.github.io "})
    finally:
        served.stop()
    assert 'name="keep"' in page and "CNAME" in page
    assert kept == ("CNAME",) and marked
    assert status == 200
    assert settings.load(folder).untouchable == ()
    assert not (folder / MARKER).exists()
    assert github.requests == []
