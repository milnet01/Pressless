# Daily backups of every site (PRESS-0225).
from __future__ import annotations

import datetime
import json
import zipfile
from pathlib import Path

import pytest
from test_publishing import _entry

from pressless import backups, sites, store, words

DAY = datetime.date(2026, 10, 16)


def _own(tmp_path: Path) -> Path:
    own = tmp_path / "Pressless-data"
    for number, name in ((1, "Sea Notes"), (2, "Hill Notes")):
        site = own / "sites" / f"site-{number}"
        site.mkdir(parents=True)
        store.write_identity(site, store.Identity(name))
        store.write(site, _entry(f"entry-{number}"), draft=True)
    sites.choose(own, "site-1")
    return own


def _made(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def test_each_site_gets_one_backup_a_day(tmp_path: Path) -> None:
    """Breaks when a site is missed, backed up twice in a day, or its file
    is not the site's own."""
    own = _own(tmp_path)
    assert backups.make_due(own, DAY) is None
    folder = tmp_path / "Pressless-backups"
    assert _made(folder) == ["Hill Notes (site-2) 2026-10-16.zip",
                             "Sea Notes (site-1) 2026-10-16.zip"]
    with zipfile.ZipFile(folder / "Sea Notes (site-1) 2026-10-16.zip") as saved:
        assert "drafts/entry-1.txt" in saved.namelist()
    before = {path.name: path.stat().st_mtime_ns for path in folder.iterdir()}
    assert backups.make_due(own, DAY) is None
    assert {path.name: path.stat().st_mtime_ns for path in folder.iterdir()} == before


def test_the_last_seven_are_kept_and_nothing_else_is_touched(tmp_path: Path) -> None:
    """Breaks when an eighth backup is kept, a newer one is removed, or a
    file Pressless did not make is removed."""
    own = _own(tmp_path)
    folder = tmp_path / "Pressless-backups"
    folder.mkdir()
    (folder / "his own notes.zip").write_bytes(b"not ours")
    (folder / "Sea Notes (site-10) 2026-01-01.zip").write_bytes(b"another site's")
    for offset in range(9):
        assert backups.make_due(own, DAY + datetime.timedelta(days=offset)) is None
    first = sorted(name for name in _made(folder) if "(site-1) " in name)
    assert first == [f"Sea Notes (site-1) 2026-10-{day}.zip" for day in range(18, 25)]
    assert (folder / "his own notes.zip").read_bytes() == b"not ours"
    assert (folder / "Sea Notes (site-10) 2026-01-01.zip").is_file()


def test_a_renamed_site_keeps_counting_its_backups(tmp_path: Path) -> None:
    """Breaks when the backups are matched by the site's name, which can
    change, rather than its folder."""
    own = _own(tmp_path)
    folder = tmp_path / "Pressless-backups"
    for offset in range(4):
        backups.make_due(own, DAY + datetime.timedelta(days=offset))
    store.write_identity(own / "sites" / "site-1", store.Identity("Renamed"))
    for offset in range(4, 9):
        backups.make_due(own, DAY + datetime.timedelta(days=offset))
    assert len([name for name in _made(folder) if "(site-1) " in name]) == 7


def test_an_unused_site_is_not_backed_up(tmp_path: Path) -> None:
    """Breaks when a fresh install's empty site fills the folder."""
    own = tmp_path / "Pressless-data"
    sites.open_site(own)
    assert backups.make_due(own, DAY) is None
    folder = tmp_path / "Pressless-backups"
    assert not folder.exists() or _made(folder) == []


def test_the_folder_he_chose_is_used(tmp_path: Path) -> None:
    """Breaks when a chosen folder is ignored, or a relative or missing one
    is accepted."""
    own = _own(tmp_path)
    chosen = tmp_path / "usb drive"
    chosen.mkdir()
    backups.set_folder(own, str(chosen))
    assert backups.folder_of(own) == chosen
    assert backups.make_due(own, DAY) is None
    assert len(_made(chosen)) == 2
    for refused in ("relative/folder", str(tmp_path / "not there"), ""):
        with pytest.raises(ValueError):
            backups.set_folder(own, refused)
    assert backups.folder_of(own) == chosen


def test_a_backup_that_fails_says_so_and_leaves_nothing_half_made(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when a failure escapes as an exception, names a full path, or
    leaves a part-written file that looks like a backup."""
    own = _own(tmp_path)

    def fails(site: Path, target: Path) -> None:
        target.write_bytes(b"half")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backups.sitefile, "save", fails)
    said = backups.make_due(own, DAY)
    assert said is not None and str(tmp_path) not in said
    assert backups.trouble(own) == said
    assert _made(tmp_path / "Pressless-backups") == []
    monkeypatch.undo()
    assert backups.make_due(own, DAY) is None and backups.trouble(own) is None


def test_a_failed_backup_takes_its_words_from_the_table(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PRESS-0320. Breaks when the sentence shown on the Sites screen is
    written in backups.py rather than read from the words table."""
    own = _own(tmp_path)

    def fails(site: Path, target: Path) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backups.sitefile, "save", fails)
    with words.use({"backups.trouble": "[{folder}] [{reason}]"}):
        said = backups.make_due(own, DAY)
    assert said == "[Pressless-backups] [No space left on device]"


def test_one_failing_site_never_stops_the_others(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when the first failing site, or a StoreError, ends the pass
    and the sites after it go without a backup."""
    own = _own(tmp_path)
    save = backups.sitefile.save

    def fails_first(site: Path, target: Path) -> None:
        if site.name == "site-1":
            raise store.StoreError("unreadable")
        save(site, target)

    monkeypatch.setattr(backups.sitefile, "save", fails_first)
    said = backups.make_due(own, DAY)
    assert said is not None and backups.trouble(own) == said
    assert _made(tmp_path / "Pressless-backups") == ["Hill Notes (site-2) 2026-10-16.zip"]


def test_an_unreadable_sites_folder_is_said_not_raised(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when listing the sites raises out of make_due, which ends the
    hourly backup thread for the session."""
    own = _own(tmp_path)

    def unreadable(own: Path) -> list[Path]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(backups.sites, "all_sites", unreadable)
    said = backups.make_due(own, DAY)
    assert said is not None and "Permission denied" in said


def test_the_record_is_the_machines(tmp_path: Path) -> None:
    """PRESS-0223 INV-2's other half: the backups record sits with the
    machine's files, so moving a site in leaves it at the top."""
    own = _own(tmp_path)
    backups.set_folder(own, str(tmp_path))
    assert json.loads((own / "backups.json").read_text(encoding="utf-8"))["version"] == 1
    assert "backups.json" in sites.MACHINE_NAMES
