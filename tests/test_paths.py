# INV-1 to INV-5 and INV-8 for PRESS-0022 (packaging): where Pressless's own
# folder is. Unlabelled -- every rule here is a resolution rule, so patching
# sys.frozen, sys.platform, sys.executable and the environment reaches every
# branch without a build (§7).
#
# Why this exists: docs/specs/PRESS-0022-packaging.md is the contract.
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

import pressless.paths as paths_module
from pressless.paths import FolderUnusable, NotPackaged, artefact_path, ensure, own_folder

# INV-8's literal, written out here rather than imported from paths. Sharing it
# would compare the module against itself, which is why tests/test_settings.py
# keeps its own copy of FILE_NAME.
_FOLDER_NAME = "Pressless-data"


def _artefact(tmp_path: Path) -> Path:
    """A file standing where the downloaded AppImage would be."""
    home = tmp_path / "apps"
    home.mkdir(exist_ok=True)
    artefact = home / "Pressless-0.1.0-x86_64.AppImage"
    artefact.write_bytes(b"not really an AppImage")
    return artefact


def _frozen_linux(monkeypatch, tmp_path: Path, *, appimage: Path | None) -> Path:
    """A frozen Linux run. The interpreter sits inside a read-only mount, as it
    does in a real AppImage, and $APPIMAGE names `appimage` -- or is unset.

    sys.platform is part of the fixture (INV-2): §7 runs this suite on
    windows-latest, where the win32 row is read before $APPIMAGE."""
    mount = tmp_path / "mount" / "usr" / "bin"
    mount.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(mount / "pressless"))
    monkeypatch.delenv("PRESSLESS_FOLDER", raising=False)
    if appimage is None:
        monkeypatch.delenv("APPIMAGE", raising=False)
    else:
        monkeypatch.setenv("APPIMAGE", str(appimage))
    return mount


def test_paths_imports_nothing_of_ours():
    """INV-1: paths.py imports no other pressless module.

    Walks the module's AST, as test_credentials_imports_no_sibling does.

    Breaks when paths reads settings.FILE_NAME to decide whether a folder is
    Pressless's, which inverts the direction §4.2 depends on. Weak in the way
    every import walk is: it passes against a module that does nothing."""
    tree = ast.parse(inspect.getsource(paths_module))
    imported: set[str] = set()
    relative = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.append(node)
            elif node.module:
                imported.add(node.module.split(".")[0])
    assert "pressless" not in imported, "paths.py imports another pressless module (INV-1)"
    assert not relative, "paths.py has a relative import, which reaches a sibling (INV-1)"


def test_appimage_path_is_not_the_mount(monkeypatch, tmp_path):
    """INV-2: frozen on Linux, the artefact is the file $APPIMAGE names, and
    never a path under the running mount.

    Breaks when the resolver falls back to sys.executable or sys._MEIPASS on
    Linux. The fixture puts sys.executable inside a mount apart from the
    artefact, so either reading returns the mount and fails here."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    resolved = artefact_path()
    assert resolved == artefact, f"resolved {resolved}, not the file $APPIMAGE names"
    assert resolved not in Path(sys.executable).parents, "resolved a parent of the mount"


def test_stale_appimage_is_not_an_address(monkeypatch, tmp_path):
    """INV-3: $APPIMAGE naming a file that does not exist is treated as unset.

    And §6: the failure names the variable it read, never the path it held.
    Breaks when the resolver checks only that the variable is set -- nothing
    else rejects this fixture, so only the file-exists guard can fail it."""
    gone = _artefact(tmp_path)
    gone.unlink()
    _frozen_linux(monkeypatch, tmp_path, appimage=gone)
    with pytest.raises(NotPackaged) as caught:
        artefact_path()
    message = str(caught.value)
    assert "APPIMAGE" in message, f"the failure does not name the variable: {message!r}"
    assert str(tmp_path) not in message, f"the failure names the path it held: {message!r}"


def test_override_is_ignored_when_frozen(monkeypatch, tmp_path):
    """INV-4: PRESSLESS_FOLDER is honoured when not frozen and ignored when
    frozen. Both arms in one test.

    Breaks when the override is read before the frozen check, so a value in
    the writer's environment moves his folder."""
    chosen = tmp_path / "chosen"

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("PRESSLESS_FOLDER", str(chosen))
    assert own_folder() == chosen, "a development run ignored PRESSLESS_FOLDER"

    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    monkeypatch.setenv("PRESSLESS_FOLDER", str(chosen))
    assert own_folder() == artefact.parent / _FOLDER_NAME, (
        "a packaged run honoured PRESSLESS_FOLDER"
    )


def test_unusable_folder_never_falls_back(tmp_path):
    """INV-5: ensure() raises FolderUnusable rather than choosing another
    location, and the message never names the path it tried (§6).

    Skips where this user can write into a read-only directory anyway -- root
    defeats the fixture, and a test that cannot fail is worse than none. The
    skip is on that capability, never on the platform."""
    parent = tmp_path / "read-only"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        probe = parent / "probe"
        try:
            probe.touch()
        except OSError:
            pass
        else:
            probe.unlink()
            pytest.skip("this user can write into a read-only directory")
        target = parent / _FOLDER_NAME
        with pytest.raises(FolderUnusable) as caught:
            ensure(target)
        message = str(caught.value)
        assert str(tmp_path) not in message, f"the failure names the path: {message!r}"
        assert not target.exists(), "the folder was created anyway"
    finally:
        parent.chmod(0o700)


def test_ensure_leaves_only_the_folder(tmp_path):
    """§4.2 and §4.5: ensure creates the folder, proves it writable, and leaves
    nothing behind it but the folder -- the probe it writes is gone."""
    target = tmp_path / _FOLDER_NAME
    assert ensure(target) == target
    assert target.is_dir(), "the folder was not created"
    assert list(target.iterdir()) == [], "ensure left a file behind in the folder"
    assert ensure(target) == target, "an existing folder was refused"


def test_folder_name_is_pinned(monkeypatch, tmp_path):
    """INV-8: on the frozen branch own_folder ends in the literal
    Pressless-data, compared against this test's own copy of the string.

    Breaks when the name is changed after a release, which sends every writer
    who has one back through setup with his key apparently gone."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    assert own_folder() == artefact.parent / _FOLDER_NAME


def test_windows_folder_sits_beside_the_extracted_folder(monkeypatch, tmp_path):
    """§4.2's win32 row: the artefact is the extracted program folder, and the
    writer's folder sits beside it rather than inside it -- so extracting a new
    zip over the old copy cannot touch his writing (scope decision 2)."""
    program = tmp_path / "Pressless"
    program.mkdir()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(program / "Pressless.exe"))
    monkeypatch.delenv("PRESSLESS_FOLDER", raising=False)
    assert artefact_path() == program
    assert own_folder() == tmp_path / _FOLDER_NAME


def test_an_unpackaged_run_is_not_packaged(monkeypatch):
    """§4.2's last row: not frozen, and no override, is NotPackaged -- never a
    guess at a folder."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("PRESSLESS_FOLDER", raising=False)
    with pytest.raises(NotPackaged):
        own_folder()
