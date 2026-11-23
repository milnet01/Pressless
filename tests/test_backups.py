# Daily backups of every site (PRESS-0225).
from __future__ import annotations

import datetime
import json
import os
import threading
import zipfile
from pathlib import Path

import pytest
from test_publishing import _entry

from pressless import backups, json_record, sites, store, words

DAY = datetime.date(2026, 10, 16)
OURS = "a1b2c3"   # this install's mark in its backups' names


def _own(tmp_path: Path) -> Path:
    own = tmp_path / "Pressless-data"
    for number, name in ((1, "Sea Notes"), (2, "Hill Notes")):
        site = own / "sites" / f"site-{number}"
        site.mkdir(parents=True)
        store.write_identity(site, store.Identity(name))
        store.write(site, _entry(f"entry-{number}"), draft=True)
    sites.choose(own, "site-1")
    json_record.write(own / "backups.json", {"install": OURS})
    return own


def _made(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def test_each_site_gets_one_backup_a_day(tmp_path: Path) -> None:
    """Breaks when a site is missed, or its file is not the site's own."""
    own = _own(tmp_path)
    assert backups.make_due(own, DAY) is None
    folder = tmp_path / "Pressless-backups"
    assert _made(folder) == ["Hill Notes (site-2 a1b2c3) 2026-10-16.zip",
                             "Sea Notes (site-1 a1b2c3) 2026-10-16.zip"]
    with zipfile.ZipFile(folder / "Sea Notes (site-1 a1b2c3) 2026-10-16.zip") as saved:
        assert "drafts/entry-1.txt" in saved.namelist()

def test_a_site_is_not_backed_up_twice_in_a_day(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when a second round the same day saves a site again."""
    own = _own(tmp_path)
    assert backups.make_due(own, DAY) is None
    saved: list[str] = []
    monkeypatch.setattr(backups.sitefile, "save_as",
                        lambda site, target: saved.append(site.name))
    assert backups.make_due(own, DAY) is None
    assert saved == []


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
    first = sorted(name for name in _made(folder) if "(site-1 a1b2c3) " in name)
    assert first == [f"Sea Notes (site-1 a1b2c3) 2026-10-{day}.zip" for day in range(18, 25)]
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
    assert len([name for name in _made(folder) if "(site-1 a1b2c3) " in name]) == 7


def test_an_unused_site_is_not_backed_up(tmp_path: Path) -> None:
    """Breaks when a fresh install's empty site fills the folder."""
    own = tmp_path / "Pressless-data"
    sites.current_site(own)
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
    assert _made(tmp_path / "Pressless-backups") == ["Hill Notes (site-2 a1b2c3) 2026-10-16.zip"]


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


# ------------------------------------------------------- PRESS-0383 fixes ---


def test_a_site_whose_settings_are_no_object_is_still_backed_up(tmp_path: Path) -> None:
    """Breaks when a damaged settings file stops a site's backup, or the
    round, just when something on disk is already wrong."""
    own = _own(tmp_path)
    (own / "sites" / "site-1" / "settings.json").write_text("[]", encoding="utf-8")
    assert backups.make_due(own, DAY) is None
    assert _made(tmp_path / "Pressless-backups") == ["Hill Notes (site-2 a1b2c3) 2026-10-16.zip",
                                                     "Sea Notes (site-1 a1b2c3) 2026-10-16.zip"]


def test_a_failing_round_never_ends_the_backups(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when one round's unforeseen failure ends the hourly thread."""
    rounds: list[int] = []
    again = threading.Event()

    def fails_once(own: Path, today: datetime.date) -> str | None:
        rounds.append(1)
        if len(rounds) == 1:
            raise RuntimeError("made up")
        again.set()
        return None

    monkeypatch.setattr(backups, "make_due", fails_once)
    monkeypatch.setattr(backups, "_EVERY", 0.01)
    heard: list[str] = []
    stop = threading.Event()
    worker = backups.start(tmp_path / "own", stop, heard.append)
    try:
        assert again.wait(5), "no second round"
    finally:
        stop.set()
        worker.join(5)
    assert heard and "RuntimeError" in heard[0]


def test_a_chosen_folder_that_has_gone_is_not_made_again(tmp_path: Path) -> None:
    """Breaks when an unplugged drive's folder is made again on the disk
    under it, where the backups hide once the drive is back."""
    own = _own(tmp_path)
    chosen = tmp_path / "usb drive" / "backups"
    chosen.mkdir(parents=True)
    backups.set_folder(own, str(chosen))
    chosen.rmdir()
    said = backups.make_due(own, DAY)
    assert said is not None and str(tmp_path) not in said
    assert not chosen.exists()


def test_a_clock_gone_back_keeps_the_backup_it_makes(tmp_path: Path) -> None:
    """Breaks when seven backups dated later than today rotate out the one
    made now, so a whole site is written and deleted every hour."""
    own = _own(tmp_path)
    folder = tmp_path / "Pressless-backups"
    folder.mkdir()
    for offset in range(1, 8):
        later = DAY + datetime.timedelta(days=offset)
        (folder / f"Sea Notes (site-1 a1b2c3) {later.isoformat()}.zip").write_bytes(b"later")
    assert backups.make_due(own, DAY) is None
    assert (folder / "Sea Notes (site-1 a1b2c3) 2026-10-16.zip").is_file()
    assert len([name for name in _made(folder) if "(site-1 a1b2c3) " in name]) == 7


def test_a_folder_inside_pressless_is_refused(tmp_path: Path) -> None:
    """Breaks when backups can go inside a site's added files, which
    publishes every draft and setting they hold."""
    own = _own(tmp_path)
    inside = own / "sites" / "site-1" / "files"
    inside.mkdir()
    with pytest.raises(ValueError):
        backups.set_folder(own, str(inside))
    assert backups.folder_of(own) == tmp_path / "Pressless-backups"


def test_a_record_that_cannot_be_read_now_keeps_its_folder(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when a passing read failure, a file held on Windows, is taken
    for an empty record and the trouble written over the chosen folder."""
    own = _own(tmp_path)
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    backups.set_folder(own, str(chosen))
    read_text = Path.read_text

    def held(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == "backups.json":
            raise PermissionError(13, "Permission denied")
        return read_text(path, *args, **kwargs)

    def fails(site: Path, target: Path) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backups.sitefile, "save", fails)
    monkeypatch.setattr(Path, "read_text", held)
    assert backups.make_due(own, DAY) is not None
    monkeypatch.undo()
    assert backups.folder_of(own) == chosen


def test_a_folder_choice_is_never_lost_to_a_trouble_written_beside_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when the record's read, merge and write are not one step, so a
    round's trouble written as the folder is chosen puts the old record back."""
    own = _own(tmp_path)
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    inside, go_on = threading.Event(), threading.Event()
    record = backups._record

    def slow(own: Path, **kwargs: object) -> dict:
        found = record(own, **kwargs)
        if threading.current_thread().name == "trouble":
            inside.set()
            go_on.wait(5)
        return found

    monkeypatch.setattr(backups, "_record", slow)
    trouble = threading.Thread(target=backups._write, args=(own,),
                               kwargs={"trouble": "made up"}, name="trouble")
    trouble.start()
    assert inside.wait(5)
    write = json_record.write
    writing = threading.Event()

    def noting(path: Path, fields: dict) -> None:
        if threading.current_thread().name == "choosing":
            writing.set()
        write(path, fields)

    monkeypatch.setattr(backups.json_record, "write", noting)
    choosing = threading.Thread(target=backups.set_folder, args=(own, str(chosen)),
                                name="choosing")
    choosing.start()
    assert not writing.wait(0.1), "the choice was written inside the trouble's merge"
    go_on.set()
    trouble.join(5)
    choosing.join(5)
    assert backups.folder_of(own) == chosen and backups.trouble(own) == "made up"


def test_half_made_site_files_are_cleared_at_start(tmp_path: Path) -> None:
    """Breaks when a stopped save leaves a whole site, drafts included,
    beside Pressless or among the backups for good, or when one another
    Pressless may be writing now is taken."""
    own = _own(tmp_path)
    folder = tmp_path / "Pressless-backups"
    folder.mkdir()
    old = (own / ".saving-1.zip", folder / ".saving-2.zip",
           folder / ".pressless-backup-3.part")
    for path in old:
        path.write_bytes(b"half")
        os.utime(path, (0, 0))
    writing = folder / ".saving-4.zip"
    writing.write_bytes(b"half")
    (folder / "his own .saving-notes.zip").write_bytes(b"his")
    backups.clear_leftovers(own)
    assert not any(path.exists() for path in old)
    assert writing.is_file() and (folder / "his own .saving-notes.zip").is_file()


def test_another_pressless_sharing_the_folder_is_left_alone(tmp_path: Path) -> None:
    """Breaks when another install's backups, whose sites are numbered the
    same, or a backup older than the install's mark, count as this one's:
    its own backup is then skipped, or theirs rotated out."""
    own = _own(tmp_path)
    folder = tmp_path / "Pressless-backups"
    folder.mkdir()
    theirs = [f"Sea Notes (site-1 ffffff) 2026-10-{day:02d}.zip" for day in range(1, 17)]
    theirs.append("Sea Notes (site-1) 2026-10-01.zip")
    for name in theirs:
        (folder / name).write_bytes(b"theirs")
    for offset in range(9):
        assert backups.make_due(own, DAY + datetime.timedelta(days=offset)) is None
    assert all((folder / name).read_bytes() == b"theirs" for name in theirs)
    ours = [name for name in _made(folder) if f"(site-1 {OURS}) " in name]
    assert len(ours) == 7


def test_an_install_makes_its_mark_once(tmp_path: Path) -> None:
    """Breaks when the mark changes between rounds, so the install loses
    track of its own backups and never rotates them."""
    own = _own(tmp_path)
    json_record.write(own / "backups.json", {})
    assert backups.make_due(own, DAY) is None
    mark = json_record.read(own / "backups.json")["install"]
    assert backups.make_due(own, DAY + datetime.timedelta(days=1)) is None
    assert json_record.read(own / "backups.json")["install"] == mark
    assert len([name for name in _made(tmp_path / "Pressless-backups")
                if f"(site-1 {mark}) " in name]) == 2
