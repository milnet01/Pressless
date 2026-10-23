# Several sites in one Pressless-data folder (PRESS-0223).
#
# The folder's names are written out here rather than imported from sites.py,
# so a test holds its own copy of the layout it pins.
from __future__ import annotations

import json
from pathlib import Path

import pytest
import test_setup
import test_usage
from _face_session import Browser
from test_credentials import _Store, _use

import pressless_import
from pressless import __main__ as main_module
from pressless import (
    backups,
    choices,
    credentials,
    editor,
    face,
    insights,
    installer,
    log,
    paths,
    settings,
    setup,
    sites,
    starter,
    store,
    themes,
    undo,
    updater,
    usage,
    wizard,
    words,
)

SITES = "sites"
OPEN = "sites.json"


def _opened(own: Path) -> str:
    return json.loads((own / OPEN).read_text(encoding="utf-8"))["open"]


# ------------------------------------------------------------------ INV-1 ---


def test_the_open_site(tmp_path: Path) -> None:
    """INV-1. Breaks when a name outside sites/ is opened, or a broken file
    stops the start."""
    own = tmp_path / "own"
    own.mkdir()
    first = sites.open_site(own)
    assert first == own / SITES / "site-1" and first.is_dir()
    assert _opened(own) == "site-1"

    (own / SITES / "site-2").mkdir()
    (own / OPEN).write_text(json.dumps({"version": 1, "open": "site-2"}), encoding="utf-8")
    assert sites.open_site(own) == own / SITES / "site-2"

    (own / "x").mkdir()
    for written in ('{"version": 1, "open": "../x"}', '{"version": 1, "open": "site-0"}',
                    '{"version": 1, "open": "site-9"}', "not json", '{"open": "site-2"}',
                    '{"version": 1, "open": 2}'):
        (own / OPEN).write_text(written, encoding="utf-8")
        assert sites.open_site(own) == own / SITES / "site-1", written
        assert _opened(own) == "site-1", written
    assert not (own / SITES / "site-9").exists()


def test_the_sites_are_listed_in_number_order_and_a_new_one_follows(tmp_path: Path) -> None:
    """INV-1's helpers. Breaks when site-10 sorts before site-2, or a folder
    that is not a site is listed."""
    own = tmp_path / "own"
    for name in ("site-2", "site-10", "site-1", ".moving", "notes"):
        (own / SITES / name).mkdir(parents=True)
    assert [path.name for path in sites.all_sites(own)] == ["site-1", "site-2", "site-10"]
    made = sites.new_site(own)
    assert made == own / SITES / "site-11" and made.is_dir()
    sites.choose(own, "site-2")
    assert _opened(own) == "site-2"
    with pytest.raises(ValueError):
        sites.choose(own, "../site-1")
    with pytest.raises(ValueError):
        sites.choose(own, "site-7")
    assert _opened(own) == "site-2"


# ------------------------------------------------------------------ INV-2 ---


def test_every_name_is_on_one_side() -> None:
    """INV-2. Breaks when a part renames its file and sites.py keeps the old
    name, so the move leaves it behind."""
    site_names = {store.PUBLISHED_FOLDER, store.DRAFTS_FOLDER, store.BIN_FOLDER,
                  store.PAGES_FOLDER, store.FURNITURE_FOLDER, *store.WAITING_FOLDERS.values(),
                  store.TEMPLATES_FOLDER, store.COMMENTS_FOLDER, store.PHOTOGRAPHS_FOLDER,
                  store.FILES_FOLDER, store.FORWARDS_FOLDER, store.OPTIONS_FOLDER,
                  store.IDENTITY_FOLDER, store.LOOK_FOLDER, settings.FILE_NAME,
                  credentials.FILE_NAME, setup.SITE_FOLDER, editor.PREVIEW_FOLDER,
                  paths.PREVIEW_ASSETS, starter.MARKER, insights.CACHE_NAME,
                  undo.FETCH_FOLDER, wizard.FOLDER, choices.FILE_NAME,
                  pressless_import.IMPORT_FOLDER}
    machine_names = {log.FILE_NAME, log.OLD_NAME, updater.FILE_NAME, installer.LOG_NAME,
                     main_module._LOCK_NAME, themes.FILE_NAME, usage.FILE_NAME,
                     usage.SENT_NAME, backups.FILE_NAME, OPEN, SITES}
    assert sites.SITE_NAMES == site_names
    assert sites.MACHINE_NAMES == machine_names
    assert not site_names & machine_names
    assert sites.OPEN_FILE == OPEN and sites.SITES_FOLDER == SITES


# --------------------------------------------------------------- INV-3, 4 ---


def _one_site(own: Path) -> dict[str, bytes]:
    """Today's layout: one site's files beside the machine's, and one file
    of nobody's. Returns every file's bytes by its path under `own`."""
    files = {
        "drafts/seaside.txt": b"a draft",
        "photographs/sea.jpg": b"\xff\xd8 a photograph",
        "settings.json": b'{"version": 1}',
        "credentials.json": b'{"version": 1, "secrets": {}}',
        "look/style.css": b"p {}",
        "wizards/setup.json": b"{}",
        "choices.json": b"{}",
        "starter-unpublished": b"",
        "pressless.log": b"the log",
        "theme.json": b'{"version": 1, "theme": "dark"}',
        "usage.json": b"{}",
        "updates.json": b"{}",
        "notes.txt": b"his own note",
    }
    for name, data in files.items():
        (own / name).parent.mkdir(parents=True, exist_ok=True)
        (own / name).write_bytes(data)
    return files


_MACHINE_OR_NOBODYS = {"pressless.log", "theme.json", "usage.json", "updates.json",
                       "notes.txt"}


def _moved(own: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        top = name.split("/")[0]
        where = own / name if top in _MACHINE_OR_NOBODYS else own / SITES / "site-1" / name
        assert where.read_bytes() == data, name
        if top not in _MACHINE_OR_NOBODYS:
            assert not (own / top).exists(), f"{top} is still at the top"
    assert _opened(own) == "site-1"
    assert sorted(p.name for p in (own / SITES).iterdir()) == ["site-1"]


def test_an_existing_site_moves_in_whole(tmp_path: Path) -> None:
    """INV-3. Breaks when a file is lost, copied rather than moved, or moved
    twice."""
    own = tmp_path / "own"
    own.mkdir()
    files = _one_site(own)
    assert sites.move_in(own) is None
    _moved(own, files)
    assert sites.move_in(own) is None
    _moved(own, files)


def test_a_stopped_move_finishes(tmp_path: Path) -> None:
    """INV-4. Breaks when the second start treats sites/ as done."""
    own = tmp_path / "own"
    own.mkdir()
    files = _one_site(own)
    (own / SITES / ".moving").mkdir(parents=True)
    for name in ("drafts", "settings.json"):
        (own / name).rename(own / SITES / ".moving" / name)
    assert sites.move_in(own) is None
    _moved(own, files)


def test_a_fresh_folder_moves_nothing_in(tmp_path: Path) -> None:
    """INV-3's empty case: a folder holding no site makes no site-1 by moving.
    Breaks when an empty site-1 is created by the move rather than by
    open_site."""
    own = tmp_path / "own"
    own.mkdir()
    (own / "pressless.log").write_bytes(b"the log")
    assert sites.move_in(own) is None
    assert (own / "pressless.log").read_bytes() == b"the log"


def test_a_refused_move_names_no_path_and_deletes_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """§ 4.3: a rename that fails stops the move; __main__ words it from the
    words table, naming the folder by name only (PRESS-0320). Breaks when the
    failure escapes, quotes a path, is worded in sites.py, or something is
    lost."""
    own = tmp_path / "Pressless-data"
    own.mkdir()
    files = _one_site(own)
    real = Path.rename

    def refuse(self: Path, target: Path) -> Path:
        if self.name == "photographs":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, target)

    monkeypatch.setattr(Path, "rename", refuse)
    assert isinstance(sites.move_in(own), OSError)
    with words.use({"main.moving_in": "[{folder}] [{reason}]"}):
        assert main_module._serve(own) == 1
    said = capsys.readouterr().out
    assert said == "[Pressless-data] [Permission denied]\n"
    assert (own / "photographs" / "sea.jpg").read_bytes() == files["photographs/sea.jpg"]
    assert (own / SITES / ".moving" / "drafts" / "seaside.txt").is_file()
    monkeypatch.setattr(Path, "rename", real)
    assert sites.move_in(own) is None
    _moved(own, files)


# ------------------------------------------------------------------ INV-5 ---


def test_each_site_keeps_its_own_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-5. Breaks when a second site's key overwrites the first's."""
    own = tmp_path / "own"
    assert sites.account("github", own / SITES / "site-1") == "github"
    assert sites.account("google", own / SITES / "site-1") == "google"
    assert sites.account("github", own / SITES / "site-3") == "github-site-3"
    assert sites.account("google", own / SITES / "site-3") == "google-site-3"
    assert sites.account("github", tmp_path / "Pressless-data") == "github"

    shared = _Store(values={("Pressless", "github"): "the first site's key"})
    _use(monkeypatch, shared)
    second = own / SITES / "site-2"
    second.mkdir(parents=True)
    filed = sites.account("github", second)
    credentials.write("keyring", second, filed, "the second site's key")
    assert credentials.read("keyring", second, filed) == "the second site's key"
    assert credentials.read("keyring", own / SITES / "site-1", "github") == (
        "the first site's key")


def test_setup_on_a_second_site_files_its_key_under_that_site(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-5, through setup. Breaks when setup files or records the key under
    the first site's name."""
    second = tmp_path / "own" / SITES / "site-2"
    second.mkdir(parents=True)
    keyring = test_setup._Store(monkeypatch)
    with test_setup._setup_page(second, test_setup._GitHub()) as browser:
        test_setup._walk_to(browser, "pages")
    assert keyring.writes == [("keyring", "github-site-2", test_setup.SENTINEL_KEY)]


def test_a_second_sites_setup_keeps_the_reports_answer_with_the_machine(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§ 4.4: usage.json is the machine's. Breaks when setup on a site writes
    the reports answer into the site, or asks again once it is answered."""
    test_usage._keyed(monkeypatch)
    own = tmp_path / "own"
    second = own / SITES / "site-2"
    second.mkdir(parents=True)

    def first_steps() -> tuple[str, str]:
        served = face.serve(own, site=second)
        try:
            setup.register(served, second, own=own, transport=test_setup._GitHub(),
                           shortcut_places=lambda: None)
            browser = Browser(served)
            page = browser.request("GET", "/setup")[2]
            page = browser.request("POST", "/setup", {"step": "welcome", "go": "next"})[2]
            shown = test_setup._step(page)
            if shown == "reports":
                browser.request("POST", "/setup",
                                {"step": "reports", "go": "next", "reports": "yes"})
            return shown, test_setup._step(page)
        finally:
            served.stop()

    assert first_steps()[0] == "reports"
    assert usage.answer(own) is True and usage.answer(second) is None
    (second / "wizards" / "setup.json").unlink()
    assert first_steps()[0] == "account"
