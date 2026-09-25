"""The program knows its own version (PRESS-0023 INV-17).

pyproject.toml is not in the bundle, so the version the Updater compares
against is __version__, and a release that bumps one and not the other would
offer itself to itself, or never offer the next.
"""
from __future__ import annotations

from pathlib import Path

import tomllib

import pressless

_MANIFEST = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_the_program_knows_its_version():
    with open(_MANIFEST, "rb") as manifest:
        declared = tomllib.load(manifest)["project"]["version"]
    assert pressless.__version__ == declared
