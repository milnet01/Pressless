"""The one flag list both freezes read — PRESS-0022 § 4.4.

The Linux and Windows build scripts take their PyInstaller arguments from
here rather than spelling flags out, so a dependency collected for one system
cannot be silently absent from the other's bundle.

The hidden-import and collect lists are EMPTY ON PURPOSE. PyInstaller ships
hook-keyring.py and hook-win32ctypes.core.py, which already collect what
keyring needs (§ 4.3, measured against PyInstaller 6.20.0). A flag duplicating
a shipped hook stops meaning anything the day the hook changes, and nothing
would notice; running the bundle is the check instead (INV-6).

    python scripts/freeze_flags.py version
    python scripts/freeze_flags.py args <work folder>
"""
from __future__ import annotations

import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
NAME = "Pressless"
ENTRY = ROOT / "src" / "pressless" / "__main__.py"
HIDDEN_IMPORTS: list[str] = []
COLLECT_ALL: list[str] = []


def version() -> str:
    """The manifest's version -- what the artefact's filename carries, and
    what the release job checks the tag against (§ 4.4)."""
    with open(ROOT / "pyproject.toml", "rb") as manifest:
        return tomllib.load(manifest)["project"]["version"]


def pyinstaller_args(work: Path) -> list[str]:
    """One-folder, never one-file (§ 4.1), and a console build: the program
    reports to a console, and a windowed build nulls sys.stdout (scope
    decision 4)."""
    args = [
        "--noconfirm", "--clean", "--onedir", "--name", NAME,
        "--paths", str(ROOT / "src"),
        "--distpath", str(work / "dist"),
        "--workpath", str(work / "build"),
        "--specpath", str(work),
    ]
    for module in HIDDEN_IMPORTS:
        args += ["--hidden-import", module]
    for package in COLLECT_ALL:
        args += ["--collect-all", package]
    return [*args, str(ENTRY)]


if __name__ == "__main__":
    if sys.argv[1:] == ["version"]:
        print(version())
    elif len(sys.argv) == 3 and sys.argv[1] == "args":
        print("\n".join(pyinstaller_args(Path(sys.argv[2]))))
    else:
        sys.exit("usage: freeze_flags.py version | args <work folder>")
