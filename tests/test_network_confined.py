"""Only the two clients reach the network (PRESS-0262 INV-9, which replaced
PRESS-0023 INV-8): the shared one, which the Publisher, Insights and usage
reports build on (PRESS-0331), and the Updater's own.

"Network module" is the set test_network_timeouts.py names, and the import
test is that file's own, so the two cannot disagree about what counts.
"""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

from test_network_timeouts import _SRC, _imports_network_machinery

_ALLOWED = {"https.py", "updater.py"}


def _reaching(package: Path) -> set[str]:
    return {source.name for source in sorted(package.rglob("*.py"))
            if _imports_network_machinery(ast.parse(source.read_text(encoding="utf-8")))}


def test_only_the_clients_reach_the_network(tmp_path):
    """Breaks when installer.py, updating.py or any other module imports one.

    The planted copy proves the walk can see a new module at all: a check
    that found only the ones it already knew would pass against anything.
    """
    assert _reaching(_SRC) == _ALLOWED

    copy = tmp_path / "pressless"
    shutil.copytree(_SRC, copy, ignore=shutil.ignore_patterns("__pycache__"))
    (copy / "planted.py").write_text("import socket\n", encoding="utf-8")
    assert _reaching(copy) == _ALLOWED | {"planted.py"}
