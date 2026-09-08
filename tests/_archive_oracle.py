"""One loader for the sibling generator the archive suites measure against
(PRESS-0108).

`tests/test_store_archive.py` and `tests/test_marks_archive.py` each carried
their own copy. Shared rather than copied for the reason `_open_watch.py`
gives -- two copies of a loader are two loaders that will disagree.

What this fixes, beyond the duplication. The old copies swallowed every
`Exception` from the module's own code and reported the result as "the file is
not on this machine". A syntax error, a missing import, a failure at import
time and a renamed export all became that same skip, so a rename could stop
the S2 round trip silently -- and CI skips these anyway, so nothing else would
have noticed. Here, absence is the ONLY skip. A generator that is present and
will not serve is a failure carrying the real reason.

The oracle is also pinned rather than discovered by sort order. Unpinned, the
old copies globbed the repository's grandparent and took whichever candidate
sorted first, so a stale checkout or a backup could win and nothing in the
output said which file had been read. Set `PRESSLESS_GENERATOR` to choose;
leave it unset and discovery still runs, but more than one candidate is a
failure rather than a silent pick.

WARNING -- the resolved path names the private sibling workspace, and that
directory's name identifies the writer. This module prints it so a wrong
oracle is diagnosable on the machine that has one. Never copy that output into
this repository, a commit message, or a review packet: see this project's
CLAUDE.md § This repository is PUBLIC.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ENV_VAR = "PRESSLESS_GENERATOR"

_MODULE_NAME = "press_test_generator_oracle"


def _candidates() -> tuple[list[Path], bool]:
    """The generators to consider, and whether the choice was pinned.

    The workspace holding it is found relatively and never named here: its
    directory name does not belong in a public repository. Both shapes are
    tried, because the generator may sit beside this repository or inside a
    sibling workspace one level down.
    """
    pinned = os.environ.get(ENV_VAR)
    if pinned:
        return [Path(pinned)], True
    siblings = Path(__file__).resolve().parents[2]
    found = sorted(siblings.glob("tools/build_blog.py"))
    found += sorted(siblings.glob("*/tools/build_blog.py"))
    return found, False


def load_generator(*required: str):
    """The sibling generator, with every name in `required` present.

    Skips only where no candidate exists at all -- the expected state on every
    machine except the maintainer's, and inside the isolated checkout the
    pre-push hook builds. Every other trouble is a failure naming its cause,
    because each of them is a real defect wearing a skip's clothes.
    """
    candidates, pinned = _candidates()

    if pinned and not candidates[0].is_file():
        pytest.fail(
            f"{ENV_VAR} is set and does not name a file: {candidates[0]}. "
            f"Unset it to fall back to discovery, or point it at the "
            f"generator."
        )
    if not candidates:
        pytest.skip(
            f"PRESS-0108: no generator found. It lives in a private sibling "
            f"workspace, not in this repository, so this is the expected "
            f"state everywhere except the maintainer's machine. Set {ENV_VAR} "
            f"to a tools/build_blog.py to run this."
        )
    if not pinned and len(candidates) > 1:
        pytest.fail(
            f"PRESS-0108: discovery found more than one generator, and the "
            f"one that sorts first is not necessarily the live one -- a stale "
            f"checkout or a backup wins on this path. Set {ENV_VAR} to the "
            f"one to measure against. Found: "
            f"{[str(path) for path in candidates]}"
        )

    module_path = candidates[0]
    print(f"PRESS-0108: archive oracle resolved to {module_path}")

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, module_path)
    if spec is None or spec.loader is None:
        pytest.fail(
            f"PRESS-0108: {module_path} exists and Python will not build an "
            f"import spec for it, so it cannot serve as the oracle."
        )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        pytest.fail(
            f"PRESS-0108: {module_path} exists and would not load, so the "
            f"oracle is unavailable for a reason that is NOT its absence: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        sys.modules.pop(_MODULE_NAME, None)

    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"PRESS-0108: {module_path} loaded and exports none of {missing} "
            f"-- the oracle has been renamed or moved. This is a failure and "
            f"not a skip: a rename that reads as absence stops these tests "
            f"without saying so."
        )
    return module
