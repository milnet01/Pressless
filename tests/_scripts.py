"""Load a file under scripts/ as a module, for tests that call its functions.

The scripts are not a package, and some have hyphens in their names, so they
cannot be imported by name.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load_script(filename: str) -> ModuleType:
    """Run scripts/<filename> as a fresh module and return it."""
    name = Path(filename).stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
