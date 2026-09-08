"""Every network open in src/ passes a timeout.

PRESS-0041 gave the two openers one and PRESS-0071 measured that no tool in
the check-code set can see it go: bandit's B113 reads the requests and httpx
modules only, so urllib is checked by nothing. A regression here is a hang
with no upper bound rather than a failure, which is the shape that does not
announce itself.

The whole of src/ is walked rather than the two modules known to open a
socket today, so a third one is covered on the day it is written -- which is
the regression this test exists for.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src" / "pressless"


def _opens_the_network(call: ast.Call) -> bool:
    """Whether this call opens a network connection.

    Narrow on purpose. `os.open` in credentials.py is a file and must not be
    caught, so an attribute named `open` counts only where it is reached
    through an opener.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == "urlopen"
    if isinstance(func, ast.Attribute):
        if func.attr == "urlopen":
            return True
        if func.attr == "open":
            root = func.value
            name = root.attr if isinstance(root, ast.Attribute) else (
                root.id if isinstance(root, ast.Name) else "")
            return "opener" in name.lower()
    return False


# A module that imports one of these is asking to open a socket, so the walk
# below owes it at least one match. Named as a set rather than counted: a
# count of expected call sites is stale the day a third opener is written,
# and this has to hold for the module that does not exist yet.
_NETWORK_MODULES = {
    "urllib.request", "socket", "http.client", "requests", "httpx",
    "ftplib", "smtplib", "poplib", "imaplib",
}


def _imports_network_machinery(tree: ast.AST) -> bool:
    """Whether this module imports something that can open a socket.

    `urllib.parse` does not count and `urllib.request` does, so the whole
    dotted name is tested rather than its first part -- publisher.py and
    insights.py both import the two side by side.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        else:
            continue
        for name in names:
            if any(
                name == module or name.startswith(f"{module}.")
                for module in _NETWORK_MODULES
            ):
                return True
    return False


def test_every_network_open_passes_a_timeout():
    """Breaks when an opener call loses its timeout keyword, or when a new
    module opens a socket without one.

    The walk is held against the source rather than against a count. Every
    module that imports network machinery owes at least one matched call, so
    losing one of the opener sites -- or the matcher ceasing to recognise the
    call shape -- fails here instead of quietly reducing the tally. `assert
    found` alone fired only at ZERO, so one site could go while the file's
    headline claim became false and the run stayed green (PRESS-0110).

    And at least one module must import that machinery at all, or the
    per-module rule is true of nothing and this test asserts nothing again by
    a different route.
    """
    untimed: list[str] = []
    unmatched: list[str] = []
    opening_modules: list[str] = []

    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        found_here = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _opens_the_network(node):
                continue
            found_here += 1
            if not any(word.arg == "timeout" for word in node.keywords):
                untimed.append(f"{source.name}:{node.lineno}")
        if not _imports_network_machinery(tree):
            continue
        opening_modules.append(source.name)
        if not found_here:
            unmatched.append(source.name)

    assert opening_modules, (
        f"no module under {_SRC} imports anything that can open a socket, so "
        f"the per-module rule below is true of nothing and this test asserted "
        f"nothing. Either the openers moved or _NETWORK_MODULES is stale"
    )
    assert not unmatched, (
        f"these modules import network machinery and no call in them matched "
        f"the opener shape, so their opens are unchecked: {unmatched}. Either "
        f"an opener site was lost or _opens_the_network stopped recognising it"
    )
    assert not untimed, (
        f"these network opens pass no timeout, so a silent peer hangs "
        f"Pressless with no upper bound: {untimed}"
    )
