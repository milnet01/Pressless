"""The pre-commit hook's two blocks over staged markdown: a link to a file that
does not exist, and deleted text that survives elsewhere.

Each test stages files in a throwaway repository holding the real hook, and
runs it as git would.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"
_BASH = shutil.which("bash")
_GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(sys.platform == "win32" or _BASH is None or _GIT is None,
                                reason="the hook runs under bash, with git")

# Long enough to count as a rule: the hook ignores deleted lines under 45 characters.
_RULE = "Every saved page is written whole, never in place, so a crash leaves the old one."


class _Repository:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "repository"
        self.root.mkdir()
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"}
        self.git("init", "-q")

    def git(self, *arguments: str) -> None:
        subprocess.run([_GIT, *arguments], cwd=self.root, env=self.env,  # noqa: S603 -- a scratch repository
                       check=True, capture_output=True)

    def write(self, name: str, text: str) -> None:
        (self.root / name).write_text(text, encoding="utf-8")

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("-c", "user.name=hook", "-c", "user.email=hook@example.invalid",
                 "commit", "-qm", "start")

    def hook(self) -> subprocess.CompletedProcess[str]:
        self.git("add", "-A")
        return subprocess.run([_BASH, str(_HOOK)], cwd=self.root, env=self.env,  # noqa: S603 -- this repository's hook
                              capture_output=True, text=True, timeout=60, check=False)


def test_a_broken_link_blocks(tmp_path):
    """The control: the plainest case the hook exists for."""
    repository = _Repository(tmp_path)
    repository.write("guide.md", "See [the notes](missing.md).\n")
    ran = repository.hook()
    assert ran.returncode == 1
    assert "BLOCK link guide.md" in ran.stderr
    assert "-> missing.md" in ran.stderr


def test_a_document_whose_name_has_a_space_is_checked(tmp_path):
    """Breaks when the staged names are split on spaces, and both halves of
    `my guide.md` fail the file test and go unchecked, unannounced."""
    repository = _Repository(tmp_path)
    repository.write("my guide.md", "See [the notes](missing.md).\n")
    ran = repository.hook()
    assert ran.returncode == 1
    assert "my guide.md" in ran.stderr


def test_a_broken_link_with_an_anchor_blocks(tmp_path):
    """Breaks when the link pattern stops at `#`, and `missing.md#section`
    never reaches the existence test."""
    repository = _Repository(tmp_path)
    repository.write("guide.md", "See [the notes](missing.md#section).\n")
    ran = repository.hook()
    assert ran.returncode == 1
    assert "-> missing.md" in ran.stderr


def test_a_link_with_an_anchor_to_a_file_that_exists_passes(tmp_path):
    """The control for the anchor case: the anchor is dropped before the test."""
    repository = _Repository(tmp_path)
    repository.write("notes.md", "# Section\n")
    repository.write("guide.md", "See [the notes](notes.md#section).\n")
    ran = repository.hook()
    assert ran.returncode == 0, ran.stderr


def test_a_date_elsewhere_in_the_file_excuses_no_other_link(tmp_path):
    """Breaks when the dated-line exemption asks every line naming the path,
    so a dated mention of it anywhere lets an undated broken link through."""
    repository = _Repository(tmp_path)
    repository.write("guide.md",
                     "On 2026-01-02 we removed missing.md.\n\nSee [the notes](missing.md).\n")
    ran = repository.hook()
    assert ran.returncode == 1
    assert "guide.md:3 -> missing.md" in ran.stderr


def test_a_dated_link_is_excused(tmp_path):
    """The control for the case above: the dated line's own link passes."""
    repository = _Repository(tmp_path)
    repository.write("guide.md", "On 2026-01-02 [the notes](missing.md) were removed.\n")
    ran = repository.hook()
    assert ran.returncode == 0, ran.stderr


def test_a_renamed_document_is_checked(tmp_path):
    """Breaks when the staged names leave out renames, and a document moved and
    edited in one commit escapes both checks."""
    repository = _Repository(tmp_path)
    repository.write("old.md", "".join(f"Line {n} of a long document.\n" for n in range(20)))
    repository.commit()
    repository.git("mv", "old.md", "new.md")
    with (repository.root / "new.md").open("a", encoding="utf-8") as document:
        document.write("See [the notes](missing.md).\n")
    ran = repository.hook()
    assert ran.returncode == 1
    assert "new.md" in ran.stderr


@pytest.mark.parametrize("rule", [_RULE, f"- {_RULE}"])
def test_deleted_text_that_survives_elsewhere_blocks(tmp_path, rule):
    """The survivor block: a rule deleted from one document but still stated in
    another. A bullet too, which git prints deleted as `-- text`: breaks when
    the diff header filter also drops every deleted bullet."""
    repository = _Repository(tmp_path)
    repository.write("one.md", f"{rule}\n")
    repository.write("two.md", f"{rule}\n")
    repository.commit()
    repository.write("one.md", "Changed.\n")
    ran = repository.hook()
    assert ran.returncode == 1
    assert "BLOCK survivor one.md -> two.md:1:" in ran.stderr


def test_text_moved_to_a_document_this_change_adds_it_to_passes(tmp_path):
    """The move exclusion: the copy the same change added is where the text went."""
    repository = _Repository(tmp_path)
    repository.write("one.md", f"{_RULE}\n")
    repository.commit()
    repository.write("one.md", "Moved.\n")
    repository.write("two.md", f"  {_RULE}  \n")
    ran = repository.hook()
    assert ran.returncode == 0, ran.stderr


def test_text_deleted_from_a_renamed_document_that_survives_elsewhere_blocks(tmp_path):
    """Breaks when a renamed document's diff names only its new path: the
    whole file then reads as added, and nothing it deleted is seen."""
    repository = _Repository(tmp_path)
    body = "".join(f"Line {n} of a long document.\n" for n in range(20))
    repository.write("old.md", f"{body}{_RULE}\n")
    repository.write("two.md", f"{_RULE}\n")
    repository.commit()
    repository.git("mv", "old.md", "new.md")
    repository.write("new.md", body)
    ran = repository.hook()
    assert ran.returncode == 1
    assert "BLOCK survivor new.md -> two.md:1:" in ran.stderr
