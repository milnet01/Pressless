"""The program that gets packaged — PRESS-0022 § 4.5.

Packaging cannot be proved without something to package, and this is
deliberately the smallest thing that proves it. PRESS-0013 replaces its body
and changes nothing in § 4.1 to § 4.4.

It answers the three questions an artefact must answer, one machine-readable
line each. The report's shape is a contract: the release job reads the exit
code and tests/features/packaging/ parses the lines.

    pressless: ok
    folder: <the folder, relative to the artefact's own folder>
    store: <keyring|file> <member name>

It writes nothing but the folder: paths.ensure() removes its own probe, and
credentials.choose() deletes its own (PRESS-0002 § 4.2).
"""
from __future__ import annotations

import os
import sys

from pressless import credentials, paths

_USAGE = "usage: pressless [--self-check]"


def main(argv: list[str]) -> int:
    """Print the report and return its exit code.

    Non-zero only where a question could not be answered at all -- NotPackaged,
    FolderUnusable, or choose() raising. `store: file` is not a failure: this
    program cannot tell a machine with no store from a bundle that lost its
    metadata, and § 7 decides which by controlling the machine.

    --self-check prints the same report as a double-click. There is no other
    flag, so the writer's route is the one that was tested.
    """
    if argv not in ([], ["--self-check"]):
        print(_USAGE, file=sys.stderr)
        raise SystemExit(2)

    print("pressless: ok")
    try:
        folder = paths.ensure(paths.own_folder())
        # Relative, so the report names no full path (docs/design.md
        # § Logging): a correct build prints Pressless-data, and anything else
        # is the misplacement INV-2 names.
        print(f"folder: {os.path.relpath(folder, paths.artefact_path().parent)}")
    except (paths.NotPackaged, paths.FolderUnusable) as exc:
        print(f"folder: unanswered -- {exc}")
        return 1

    try:
        choice = credentials.choose()
    except credentials.CredentialError as exc:
        print(f"store: unanswered -- {type(exc).__name__}")
        return 1
    print(f"store: {choice.store} {choice.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
