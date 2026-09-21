# Undo: one step back, ending with the site and his files agreeing (PRESS-0015).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0015-undo.md
# § 5. INV-3, INV-4 and INV-5 live in tests/test_publishing.py, because each is
# about what `publishing._move` does with the mark rather than about the
# sequence.
#
# The Publisher is reached through a fake Transport, as tests/test_publisher.py
# does, and Credentials through a double, so no test reaches the network or a
# real keyring. The fixtures are imported from tests/test_publishing.py rather
# than copied -- the same reuse that file makes of tests/test_publisher.py.
from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import pytest
from test_publisher import _blob_hash, _listing, _reads, _Transport, _writes
from test_publishing import _binned, _entry, _folder, _settings, _state

from pressless import builder, log, publisher, store, undo

KEY = "ghp_SENTINELundoKEY0123456789abcd"
UNDONE = "Undone"
REPLACES = "Replaces"
HEADER = "<header>{{NAVIGATION}}</header>\n"
NAVIGATION = '<nav><a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a></nav>'
FOOTER = "<footer>{{YEAR}}</footer>\n"


def _content(tmp_path: Path, *, published: tuple[store.Entry, ...] = (),
             comments: tuple[tuple[str, tuple[store.Comment, ...]], ...] = (),
             pages: tuple[tuple[str, str], ...] = (),
             furniture: tuple[tuple[str, str], ...] = (),
             templates: tuple[store.Entry, ...] = ()) -> dict[str, bytes]:
    """The `content/` the Builder would have written for this state, as
    repository-relative path -> bytes (PRESS-0008 § 4.7).

    Built by writing through the Store into a throwaway folder and reading the
    bytes back, so a fixture can never hold bytes the Store's own reader would
    refuse -- which would make a test about undo fail for a reason about the
    fixture.
    """
    scratch = tmp_path / "previous"
    scratch.mkdir(exist_ok=True)
    files: dict[str, bytes] = {}
    for entry in published:
        files[f"content/{store.PUBLISHED_FOLDER}/{entry.slug}{store.FILE_SUFFIX}"] = (
            store.write(scratch, entry, draft=False).read_bytes())
    for slug, items in comments:
        files[f"content/{store.COMMENTS_FOLDER}/{slug}{store.COMMENTS_SUFFIX}"] = (
            store.write_comments(scratch, slug, items).read_bytes())
    for name, html in pages:
        files[f"content/{store.PAGES_FOLDER}/{name}{store.HTML_SUFFIX}"] = (
            store.write_html(scratch, store.PAGES_FOLDER, name, html).read_bytes())
    for name, html in furniture:
        files[f"content/{store.FURNITURE_FOLDER}/{name}{store.HTML_SUFFIX}"] = (
            store.write_html(scratch, store.FURNITURE_FOLDER, name, html).read_bytes())
    for entry in templates:
        files[f"content/{store.TEMPLATES_FOLDER}/{entry.slug}{store.FILE_SUFFIX}"] = (
            store.write_template(scratch, entry).read_bytes())
    return files


def _comment(identifier: str) -> store.Comment:
    return store.Comment(identifier=identifier, author="A reader", author_url="",
                         date=datetime(2015, 3, 1, 9, 0), body="Words.", parent="")


def _previous(files: dict[str, bytes], *, refused: bool = False,
              **kwargs) -> _Transport:
    """A transport whose parent commit's tree holds exactly `files`.

    The per-blob answers are prepended to `_reads`, whose own `/git/blobs/`
    entry answers every blob with one body: first match wins, so each file's
    own sha has to be named before it.
    """
    tree = [(path, _blob_hash(data)) for path, data in files.items()]
    blobs = [
        (f"/git/blobs/{_blob_hash(data)}",
         (200, {}, json.dumps({"content": base64.b64encode(data).decode("ascii"),
                               "encoding": "base64"}).encode("utf-8")))
        for data in files.values()
    ]
    # An empty substring matches every URL, so it refuses every write while the
    # reads the fetch makes still answer normally.
    writes = [("", (401, {}, b'{"message": "Bad credentials"}'))] if refused else _writes()
    return _Transport(reads=blobs + _reads(_listing(tree)), writes=writes, **kwargs)


def _furnished(tmp_path: Path) -> dict[str, bytes]:
    """The furniture every fetched state carries, so a build after the undo has
    a header, navigation and footer to render with."""
    return _content(tmp_path, furniture=(("header", HEADER), ("navigation", NAVIGATION),
                                         ("footer", FOOTER)))


def _undo(folder: Path, transport: _Transport, **kwargs) -> undo.Undone:
    from test_publishing import _settings as settings_for
    return undo.undo(folder, settings_for(folder), KEY, transport=transport, **kwargs)


def _files_under(folder: Path) -> dict[str, bytes]:
    """Every file in the Store's own folders, by relative path. Reads BYTES, so
    a test can see a file that appeared as well as one that changed."""
    found = {}
    for name in (store.PUBLISHED_FOLDER, store.DRAFTS_FOLDER, store.PAGES_FOLDER,
                 store.FURNITURE_FOLDER, store.TEMPLATES_FOLDER, store.COMMENTS_FOLDER):
        subfolder = folder / name
        if not subfolder.is_dir():
            continue
        for path in sorted(subfolder.rglob("*")):
            if path.is_file():
                found[str(path.relative_to(folder))] = path.read_bytes()
    return found


# ------------------------------------------------------------------ INV-1 ---


def test_the_fetch_area_is_emptied_at_both_ends(tmp_path, monkeypatch):
    """The fetch area is emptied before fetching and again however the sequence
    ends -- so undo never reads a fetch area it did not just create."""
    def stray(folder: Path) -> Path:
        fetch = folder / undo.FETCH_FOLDER
        fetch.mkdir(parents=True, exist_ok=True)
        left = fetch / "left-from-last-time.txt"
        left.write_text("stale", encoding="utf-8")
        return left

    def empty(folder: Path) -> bool:
        fetch = folder / undo.FETCH_FOLDER
        return fetch.is_dir() and not any(fetch.rglob("*"))

    # Success.
    (tmp_path / "ok").mkdir(exist_ok=True)
    folder = _folder(tmp_path / "ok")
    store.write(folder, _entry("seaside", body="Now."), draft=False)
    files = {**_furnished(tmp_path), **_content(tmp_path, published=(_entry("seaside"),))}
    left = stray(folder)
    _undo(folder, _previous(files))
    assert empty(folder) and not left.exists()

    # A definite failure -- the key is refused.
    (tmp_path / "refused").mkdir(exist_ok=True)
    folder = _folder(tmp_path / "refused")
    store.write(folder, _entry("seaside", body="Now."), draft=False)
    left = stray(folder)
    with pytest.raises(publisher.PublishError):
        _undo(folder, _previous(files, refused=True))
    assert empty(folder) and not left.exists()

    # An unknown outcome -- no answer on the reference update itself.
    (tmp_path / "unknown").mkdir(exist_ok=True)
    folder = _folder(tmp_path / "unknown")
    store.write(folder, _entry("seaside", body="Now."), draft=False)
    left = stray(folder)
    with pytest.raises(publisher.OutcomeUnknown):
        _undo(folder, _previous(files, fail_at="/git/refs"))
    assert empty(folder) and not left.exists()


# ------------------------------------------------------------------ INV-2 ---


def test_an_entry_the_previous_state_lacks_becomes_a_draft(tmp_path):
    """An entry the fetched state does not hold is demoted, never deleted."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Kept."), draft=False)
    store.write(folder, _entry("harbour", body="Newer."), draft=False)
    files = {**_furnished(tmp_path),
             **_content(tmp_path, published=(_entry("seaside", body="Kept."),))}

    result = _undo(folder, _previous(files))

    assert result.demoted == ("harbour",)
    assert "harbour" in store.list_slugs(folder, draft=True)
    assert "harbour" not in store.list_slugs(folder, draft=False)
    demoted = store.read(store.path_for(folder, "harbour", draft=True))
    assert demoted.body == "Newer."
    assert any(name == UNDONE for name, _ in demoted.extra)
    assert _binned(folder) == []


# ------------------------------------------------------------------ INV-6 ---


def test_his_own_version_is_kept_beside_the_one_put_back(tmp_path):
    """A version of his that undo writes over is kept as a draft under a free
    address, with no `Replaces` naming the entry it was kept from."""
    folder = _folder(tmp_path)
    # A published entry whose Store version differs.
    store.write(folder, _entry("seaside", body="His newer words.",
                               extra=((REPLACES, "seaside"),)), draft=False)
    # A draft whose slug the fetched state publishes, carrying a Replaces that
    # names some OTHER entry -- § 3 decision 7 says that one survives.
    store.write(folder, _entry("harbour", body="His draft.",
                               extra=((REPLACES, "elsewhere"),)), draft=True)
    store.write(folder, _entry("elsewhere", body="Other."), draft=False)
    files = {**_furnished(tmp_path),
             **_content(tmp_path, published=(_entry("seaside", body="The older words."),
                                             _entry("harbour", body="The older harbour."),
                                             _entry("elsewhere", body="Other.")))}

    result = _undo(folder, _previous(files))

    assert sorted(result.kept) == ["harbour-before-undo", "seaside-before-undo"]
    kept = store.read(store.path_for(folder, "seaside-before-undo", draft=True))
    assert kept.body == "His newer words."
    assert kept.date == datetime(2014, 11, 9, 21, 32)
    assert kept.slug == "seaside-before-undo"
    # It was kept FROM a file carrying `Replaces: seaside`, so this is the case
    # that would refute the clause rather than one that cannot.
    assert (REPLACES, "seaside") not in kept.extra

    copy = store.read(store.path_for(folder, "harbour-before-undo", draft=True))
    assert copy.body == "His draft."
    assert (REPLACES, "elsewhere") in copy.extra   # § 3 decision 7

    assert store.read(store.path_for(folder, "seaside", draft=False)).body == "The older words."
    assert store.read(store.path_for(folder, "harbour", draft=False)).body == (
        "The older harbour.")


# ------------------------------------------------------------------ INV-7 ---


def test_a_file_the_previous_state_lacks_is_kept(tmp_path):
    """A fixed page, template or furniture file the fetched state does not hold
    is kept untouched -- an undo removes nothing of his from the Store."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    store.write_html(folder, store.PAGES_FOLDER, "about", "<p>About me.</p>")
    store.write_template(folder, _entry("poem", body="A template."))
    # A page the fetched state DOES hold, so the same run covers both
    # directions: what is not named is kept, what is named is put back. Without
    # the second, skipping the whole non-entry restore passes every test --
    # measured with mutation_probe, which is how this assertion got here.
    store.write_html(folder, store.PAGES_FOLDER, "colophon", "<p>His newer colophon.</p>")
    store.write_template(folder, _entry("sonnet", body="His newer sonnet."))
    store.write_comments(folder, "seaside", (_comment("2"),))
    files = {**_furnished(tmp_path),
             **_content(tmp_path, published=(_entry("seaside"),),
                        pages=(("colophon", "<p>The older colophon.</p>"),),
                        templates=(_entry("sonnet", body="The older sonnet."),),
                        comments=(("seaside", (_comment("1"),)),))}

    _undo(folder, _previous(files))

    assert store.read_html(store.html_path_for(folder, store.PAGES_FOLDER, "about")) == (
        "<p>About me.</p>")
    assert store.read(store.template_path_for(folder, "poem")).body == "A template."
    assert store.read_html(store.html_path_for(folder, store.PAGES_FOLDER, "colophon")) == (
        "<p>The older colophon.</p>")
    assert store.read(store.template_path_for(folder, "sonnet")).body == "The older sonnet."
    restored = store.read_comments(store.comments_path_for(folder, "seaside"))
    assert [one.identifier for one in restored] == ["1"]
    # The superseded version goes to the bin first, so nothing of his is lost
    # (§ 4.4). Every removal the reconcile makes is a move_to_bin (§ 4.7).
    assert _binned(folder) == ["colophon.html", "seaside.json", "sonnet.txt"]
    site = _settings(folder).site_folder
    assert (site / "pages" / "about.html").is_file(), sorted(
        str(p.relative_to(site)) for p in site.rglob("*.html"))


# ------------------------------------------------------------------ INV-8 ---


def test_undoing_to_an_empty_site_is_not_refused(tmp_path):
    """Undo's publish passes `emptying=True`, so the no-published-entry guard
    does not refuse a previous state that held no entry."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    files = _furnished(tmp_path)

    result = _undo(folder, _previous(files))

    assert result.demoted == ("seaside",)
    assert store.list_slugs(folder, draft=False) == ()


# ------------------------------------------------------------------ INV-9 ---


def test_the_first_publish_cannot_be_undone(tmp_path):
    """A previous state holding no `content/` is refused, and nothing moves."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside"), draft=False)
    store.write(folder, _entry("harbour"), draft=True)
    before = _state(folder)

    # The parent commit's tree holds a README and no content/ at all.
    with pytest.raises(undo.NothingToUndo):
        _undo(folder, _previous({"README.md": b"# a site\n"}))

    assert _state(folder) == before
    assert _binned(folder) == []


# ----------------------------------------------------------------- INV-10 ---


def test_a_definite_failure_puts_the_files_back(tmp_path, monkeypatch):
    """A definite failure runs the reversals; an unknown outcome does not."""
    def stocked(where: Path) -> Path:
        where.mkdir(parents=True, exist_ok=True)
        folder = _folder(where)
        store.write(folder, _entry("seaside", body="His newer words."), draft=False)
        store.write(folder, _entry("harbour", body="Newer."), draft=False)
        store.write(folder, _entry("tideline", body="His draft."), draft=True)
        store.write_html(folder, store.PAGES_FOLDER, "about", "<p>His about.</p>")
        return folder

    files = {**_furnished(tmp_path),
             **_content(tmp_path,
                        published=(_entry("seaside", body="The older words."),
                                   _entry("tideline", body="The older tideline.")),
                        pages=(("about", "<p>The older about.</p>"),))}

    # The key is refused: a definite failure.
    folder = stocked(tmp_path / "refused")
    before = _files_under(folder)
    with pytest.raises(publisher.PublishError):
        _undo(folder, _previous(files, refused=True))
    after = _files_under(folder)
    assert after == before, sorted(set(after) ^ set(before))

    # The build raises: a definite failure before GitHub is reached at all.
    folder = stocked(tmp_path / "build")
    before = _files_under(folder)

    def raising(*args, **kwargs):
        raise builder.BuildStopped("the site could not be built")

    monkeypatch.setattr(builder, "build", raising)
    with pytest.raises(builder.BuildStopped):
        _undo(folder, _previous(files))
    monkeypatch.undo()
    after = _files_under(folder)
    assert after == before, sorted(set(after) ^ set(before))

    # No answer on the reference update: the Store holds the undone state.
    folder = stocked(tmp_path / "unknown")
    with pytest.raises(publisher.OutcomeUnknown):
        _undo(folder, _previous(files, fail_at="/git/refs"))
    assert store.read(store.path_for(folder, "seaside", draft=False)).body == (
        "The older words.")
    assert "harbour" in store.list_slugs(folder, draft=True)


# ----------------------------------------------------------------- INV-11 ---


def test_an_unreadable_fetched_file_moves_nothing(tmp_path):
    """Nothing in the Store moves before the fetched state has been read whole."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="His newer words."), draft=False)
    store.write(folder, _entry("harbour", body="Newer."), draft=False)
    before = _state(folder)

    files = {**_furnished(tmp_path),
             **_content(tmp_path, published=(_entry("seaside", body="Older."),))}
    files[f"content/{store.PUBLISHED_FOLDER}/tideline{store.FILE_SUFFIX}"] = (
        b"Title: broken\nDate: not-a-date\n\nBody.\n")

    with pytest.raises(store.StoreError) as raised:
        _undo(folder, _previous(files))

    assert "tideline" in str(raised.value)
    assert _state(folder) == before
    assert _binned(folder) == []


# ----------------------------------------------------------------- INV-12 ---


def test_the_key_is_never_shown(tmp_path, capfd):
    """The key never reaches a page, the log or the console."""
    folder = _folder(tmp_path)
    store.write(folder, _entry("seaside", body="Now."), draft=False)
    files = {**_furnished(tmp_path),
             **_content(tmp_path, published=(_entry("seaside", body="Older."),))}
    opened = log.open_log(folder)
    try:
        _undo(folder, _previous(files))
        with pytest.raises(publisher.PublishError) as raised:
            _undo(folder, _previous(files, refused=True))
    finally:
        opened.close()

    assert KEY not in str(raised.value) and KEY not in repr(raised.value)
    logged = log.path_for(folder)
    if logged.is_file():
        assert KEY not in logged.read_text("utf-8", errors="replace")
    printed = capfd.readouterr()
    assert KEY not in printed.out and KEY not in printed.err
