# The menu entry and the desktop icon (PRESS-0183).
#
# The Linux tests write real .desktop files into the test's own folder and run
# on both systems, since the format is text. The Windows tests write real .lnk
# files through PowerShell and run only on Windows: the shortcut is the
# system's own binary format, and nothing here can fake the writer.
#
# File names are written out here rather than imported from shortcuts.py, so a
# renamed file cannot pass by comparing the module against itself.
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from pressless import shortcuts

ENTRY = "pressless.desktop"
LINK = "Pressless.lnk"


def _linux(tmp_path: Path, program: Path | None = None, *, desktop: bool = True,
           icon: bool = True) -> shortcuts.Places:
    program = program or _program(tmp_path / "apps")
    source = tmp_path / "mount" / "pressless.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"\x89PNG not really")
    data = tmp_path / "data"
    desk = tmp_path / "Desktop"
    desk.mkdir(exist_ok=True)
    return shortcuts.Places(
        windows=False,
        menu=data / "applications" / ENTRY,
        desktop=desk / ENTRY if desktop else None,
        program=program,
        working=program.parent,
        icon=source if icon else None,
        icon_copy=data / "icons" / "hicolor" / "256x256" / "apps" / "pressless.png",
    )


def _program(folder: Path, name: str = "Pressless-0.8.0-x86_64.AppImage") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / name
    program.write_bytes(b"not really an AppImage")
    return program


def _field(text: str, key: str) -> str:
    return next(line.split("=", 1)[1] for line in text.splitlines()
                if line.startswith(f"{key}="))


@pytest.mark.skipif(sys.platform == "win32", reason="a Linux launcher names a POSIX path")
def test_both_shortcuts_are_made_and_start_the_program(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=True)

    assert shortcuts.present(where) == (True, True)
    for made in (where.menu, where.desktop):
        text = made.read_text(encoding="utf-8")
        assert text.startswith("[Desktop Entry]\n")
        assert _field(text, "Exec") == f'"{where.program}"'
        assert _field(text, "Terminal") == "true"
        assert _field(text, "Icon") == str(where.icon_copy)
    # The menu cannot read inside the AppImage, so the picture is copied out.
    assert where.icon_copy.read_bytes() == where.icon.read_bytes()


@pytest.mark.skipif(sys.platform == "win32", reason="execute bits are a POSIX idea")
def test_the_desktop_icon_is_marked_as_a_program(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=False, desktop=True)
    assert where.desktop.stat().st_mode & stat.S_IXUSR


def test_only_the_ticked_one_is_made(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=False)
    assert shortcuts.present(where) == (True, False)


def test_unticking_takes_both_away_and_the_icon_copy_with_them(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=True)
    shortcuts.apply(where, menu=True, desktop=False)
    assert shortcuts.present(where) == (True, False)
    assert where.icon_copy.exists()

    shortcuts.apply(where, menu=False, desktop=False)
    assert shortcuts.present(where) == (False, False)
    assert not where.icon_copy.exists()


def test_no_picture_found_still_makes_a_shortcut(tmp_path):
    where = _linux(tmp_path, icon=False)
    shortcuts.apply(where, menu=True, desktop=False)
    text = where.menu.read_text(encoding="utf-8")
    assert "Icon=" not in text
    assert not where.icon_copy.exists()


@pytest.mark.parametrize(("name", "exec_value"), [
    ("Press less.AppImage", '"{folder}/Press less.AppImage"'),
    ('say "hi".AppImage', '"{folder}/say \\\\"hi\\\\".AppImage"'),
    ("cost$5.AppImage", '"{folder}/cost\\\\$5.AppImage"'),
    ("50%.AppImage", '"{folder}/50%%.AppImage"'),
    ("tick`.AppImage", '"{folder}/tick\\\\`.AppImage"'),
])
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file names")
def test_exec_quotes_the_path_as_the_desktop_entry_spec_says(tmp_path, name, exec_value):
    # The spec escapes ", `, $ and \ inside the quotes, doubles %, and then
    # escapes each backslash again as a string value.
    program = _program(tmp_path / "apps", name)
    where = _linux(tmp_path, program)
    shortcuts.apply(where, menu=True, desktop=False)
    text = where.menu.read_text(encoding="utf-8")
    assert _field(text, "Exec") == exec_value.format(folder=program.parent)


def test_a_line_break_in_the_path_is_refused(tmp_path):
    where = _linux(tmp_path)
    where = shortcuts.Places(**{**where.__dict__, "program": tmp_path / "a\nb"})
    with pytest.raises(shortcuts.ShortcutError) as caught:
        shortcuts.apply(where, menu=True, desktop=False)
    assert str(tmp_path) not in str(caught.value)
    assert not where.menu.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="a Linux launcher names a POSIX path")
def test_a_moved_program_is_followed_at_the_next_launch(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=True)

    moved = _program(tmp_path / "elsewhere")
    later = shortcuts.Places(**{**where.__dict__, "program": moved,
                                "working": moved.parent})
    shortcuts.refresh(later)
    for made in (later.menu, later.desktop):
        assert _field(made.read_text(encoding="utf-8"), "Exec") == f'"{moved}"'


def test_a_deleted_shortcut_stays_deleted(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=True)
    where.desktop.unlink()
    shortcuts.refresh(where)
    assert shortcuts.present(where) == (True, False)


def test_a_current_shortcut_is_not_rewritten(tmp_path, monkeypatch):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=True)
    written: list[Path] = []
    monkeypatch.setattr(shortcuts, "_write", lambda w, target: written.append(target))
    shortcuts.refresh(where)
    assert written == []


def test_a_development_run_offers_nothing(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert shortcuts.places() is None


def _frozen_linux(monkeypatch, tmp_path: Path, user_dirs: str | None) -> Path:
    """A packaged Linux run whose home is the test's folder."""
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    if user_dirs is not None:
        (home / ".config" / "user-dirs.dirs").write_text(user_dirs, encoding="utf-8")
    appdir = tmp_path / "mount"
    appdir.mkdir()
    (appdir / "pressless.png").write_bytes(b"png")
    program = _program(tmp_path / "apps")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("APPIMAGE", str(program))
    monkeypatch.setenv("APPDIR", str(appdir))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home


@pytest.mark.skipif(sys.platform == "win32", reason="a Linux home folder")
def test_linux_places_follow_the_freedesktop_folders(monkeypatch, tmp_path):
    home = _frozen_linux(monkeypatch, tmp_path,
                         'XDG_DESKTOP_DIR="$HOME/Schreibtisch"\n')
    (home / "Schreibtisch").mkdir()
    where = shortcuts.places()
    assert where is not None and not where.windows
    assert where.menu == home / ".local" / "share" / "applications" / ENTRY
    assert where.desktop == home / "Schreibtisch" / ENTRY
    assert where.program == Path(os.environ["APPIMAGE"])
    assert where.icon == tmp_path / "mount" / "pressless.png"


@pytest.mark.skipif(sys.platform == "win32", reason="a Linux home folder")
def test_no_desktop_folder_offers_no_desktop_icon(monkeypatch, tmp_path):
    _frozen_linux(monkeypatch, tmp_path, None)
    where = shortcuts.places()
    assert where is not None and where.desktop is None


@pytest.mark.skipif(sys.platform == "win32", reason="a Linux home folder")
def test_the_desktop_folder_defaults_to_desktop(monkeypatch, tmp_path):
    home = _frozen_linux(monkeypatch, tmp_path, "# nothing set\n")
    (home / "Desktop").mkdir()
    assert shortcuts.places().desktop == home / "Desktop" / ENTRY


# Windows: real shortcuts, written by the system's own writer.

def _windows(tmp_path: Path, base: Path | None = None) -> shortcuts.Places:
    base = base or tmp_path / "Pressless 0.8.0"
    (base / "Pressless").mkdir(parents=True, exist_ok=True)
    (base / "Start Pressless.bat").write_text("@echo off\r\n", encoding="ascii")
    (tmp_path / "Programs").mkdir(exist_ok=True)
    (tmp_path / "Desktop").mkdir(exist_ok=True)
    return shortcuts.Places(
        windows=True,
        menu=tmp_path / "Programs" / LINK,
        desktop=tmp_path / "Desktop" / LINK,
        program=base / "Start Pressless.bat",
        working=base,
        icon=Path(sys.executable),
        icon_copy=None,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="the .lnk writer is Windows's own")
def test_windows_makes_and_removes_real_shortcuts(tmp_path):
    where = _windows(tmp_path)
    shortcuts.apply(where, menu=True, desktop=True)
    assert shortcuts.present(where) == (True, True)
    shortcuts.apply(where, menu=False, desktop=False)
    assert shortcuts.present(where) == (False, False)


@pytest.mark.skipif(sys.platform != "win32", reason="the .lnk writer is Windows's own")
def test_windows_rewrites_only_a_shortcut_naming_somewhere_else(tmp_path, monkeypatch):
    where = _windows(tmp_path)
    shortcuts.apply(where, menu=True, desktop=False)
    written: list[Path] = []
    real = shortcuts._write
    monkeypatch.setattr(shortcuts, "_write",
                        lambda w, target: (written.append(target), real(w, target)))

    shortcuts.refresh(where)
    assert written == []

    moved = _windows(tmp_path, tmp_path / "Moved Pressless")
    shortcuts.refresh(moved)
    assert written == [moved.menu]
    shortcuts.refresh(moved)
    assert written == [moved.menu]


def test_a_shortcut_he_changed_otherwise_is_left_as_he_made_it(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=False)
    changed = where.menu.read_text(encoding="utf-8").replace("Name=Pressless",
                                                               "Name=My blog")
    where.menu.write_text(changed, encoding="utf-8")
    shortcuts.refresh(where)
    assert where.menu.read_text(encoding="utf-8") == changed


def test_an_updated_picture_reaches_the_menu_at_the_next_launch(tmp_path):
    where = _linux(tmp_path)
    shortcuts.apply(where, menu=True, desktop=False)
    where.icon.write_bytes(b"the next release's picture")
    shortcuts.refresh(where)
    assert where.icon_copy.read_bytes() == where.icon.read_bytes()


def test_a_windows_folder_name_outside_the_basic_plane_still_reads_as_current(
        tmp_path, monkeypatch):
    # A .lnk counts its strings in UTF-16 units, and an emoji takes two.
    working = tmp_path / "Pressless \N{OPEN BOOK}"
    held = ("x" * 10).encode("utf-16-le")
    text = str(working).encode("utf-16-le")
    link = tmp_path / LINK
    link.write_bytes(held + (len(text) // 2).to_bytes(2, "little") + text + held)
    where = shortcuts.Places(windows=True, menu=link, desktop=None,
                             program=working / "Start Pressless.bat", working=working,
                             icon=None, icon_copy=None)
    written: list[Path] = []
    monkeypatch.setattr(shortcuts, "_write", lambda w, target: written.append(target))
    shortcuts.refresh(where)
    assert written == []
