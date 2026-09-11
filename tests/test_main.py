# PRESS-0022 § 4.5: the program that gets packaged, and its report.
#
# The report's shape is a contract -- § 7's release job and
# tests/features/packaging/ parse it, and the job reads its exit code -- so it
# is pinned here against the same patched resolution tests/test_paths.py uses,
# without a build. INV-6 itself needs a built artefact and lives with the
# packaging tests.
from __future__ import annotations

import pytest
from test_paths import _artefact, _frozen_linux

import pressless.__main__ as main_module
from pressless.credentials import Choice

# The report's three line keys and the folder's name, written out rather than
# imported, so the test holds its own copy of the contract.
_FOLDER_NAME = "Pressless-data"


def _store(monkeypatch, choice):
    """Answer credentials.choose() with `choice`, or raise it if it is an
    exception -- the packaged program must not touch the real keyring here."""
    def choose():
        if isinstance(choice, Exception):
            raise choice
        return choice
    monkeypatch.setattr(main_module.credentials, "choose", choose)


def test_self_check_reports_three_lines(monkeypatch, tmp_path, capsys):
    """A packaged run answers all three questions and exits 0.

    `folder:` is relative to the artefact's own folder, so a correct build
    prints Pressless-data and the report names no full path (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    assert main_module.main(["--self-check"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == [
        "pressless: ok",
        f"folder: {_FOLDER_NAME}",
        "store: keyring SecretService",
    ], out
    assert str(tmp_path) not in out, f"the report names a full path: {out!r}"


def test_the_double_click_takes_the_same_path(monkeypatch, tmp_path, capsys):
    """No flag at all is the writer's double-click, and it prints the same
    report -- so the route that was tested is the writer's route (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    assert main_module.main([]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "pressless: ok"


def test_an_unanswerable_question_exits_non_zero(monkeypatch, tmp_path, capsys):
    """NotPackaged is one of the three reasons to exit non-zero, and the
    report still names no path -- a stale $APPIMAGE value is one."""
    gone = _artefact(tmp_path)
    gone.unlink()
    _frozen_linux(monkeypatch, tmp_path, appimage=gone)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    assert main_module.main(["--self-check"]) != 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "pressless: ok", "it did not say it started"
    assert str(tmp_path) not in out, f"the report names a full path: {out!r}"


def test_a_file_store_is_not_a_failure(monkeypatch, tmp_path, capsys):
    """`store: file` exits 0: this program cannot tell a machine with no store
    from a bundle that lost its metadata, so § 7 decides which by controlling
    the machine (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("file", "file"))

    assert main_module.main(["--self-check"]) == 0
    assert capsys.readouterr().out.splitlines()[2] == "store: file file"


def test_a_store_that_raises_exits_non_zero(monkeypatch, tmp_path, capsys):
    """choose() raising is the third reason to exit non-zero (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, main_module.credentials.CredentialError("no store"))

    assert main_module.main(["--self-check"]) != 0


def test_it_writes_nothing_but_the_folder(monkeypatch, tmp_path, capsys):
    """Beside the artefact there is the artefact and the empty folder, and
    nothing else (§ 4.5)."""
    artefact = _artefact(tmp_path)
    _frozen_linux(monkeypatch, tmp_path, appimage=artefact)
    _store(monkeypatch, Choice("keyring", "SecretService"))

    main_module.main(["--self-check"])
    assert sorted(p.name for p in artefact.parent.iterdir()) == sorted(
        [artefact.name, _FOLDER_NAME]
    )
    assert list((artefact.parent / _FOLDER_NAME).iterdir()) == []


def test_there_is_no_other_flag(monkeypatch, tmp_path, capsys):
    """Only the double-click and --self-check exist (§ 4.5); anything else is
    refused rather than read as one of them."""
    with pytest.raises(SystemExit) as caught:
        main_module.main(["--something-else"])
    assert caught.value.code != 0
