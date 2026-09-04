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


def test_every_network_open_passes_a_timeout():
    """Breaks when an opener call loses its timeout keyword, or when a new
    module opens a socket without one.

    The found count is asserted too: a walk that matches nothing passes for
    the same reason a correct one does, and this project has already shipped
    tests that could not fail (PRESS-0075).
    """
    untimed: list[str] = []
    found = 0

    for source in sorted(_SRC.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _opens_the_network(node):
                continue
            found += 1
            if not any(word.arg == "timeout" for word in node.keywords):
                untimed.append(f"{source.name}:{node.lineno}")

    assert found, (
        f"no network open was found under {_SRC}, so this test asserted "
        f"nothing. Either the matcher stopped recognising the call shape or "
        f"the modules moved"
    )
    assert not untimed, (
        f"these network opens pass no timeout, so a silent peer hangs "
        f"Pressless with no upper bound: {untimed}"
    )
