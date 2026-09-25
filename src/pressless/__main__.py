"""The program that gets packaged — PRESS-0022 § 4.5 and PRESS-0013 § 4.5.

Both routes print the same report first, one machine-readable line each. The
report's shape is a contract: the release job reads the exit code and
tests/features/packaging/ parses the lines.

    pressless: ok
    folder: <the folder, relative to the artefact's own folder>
    store: <keyring|file> <member name>

`--self-check` stops there. The double-click then serves the Face, with setup,
the editor, publishing, undo and the page editor on it, opens his browser,
and runs until the console window is closed. Every part is imported here at
module level, so a packaged `--self-check` proves each one loads in the bundle.
"""
from __future__ import annotations

import os
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from pressless import (
    credentials,
    editor,
    face,
    page_editor,
    paths,
    publishing,
    settings,
    setup,
    undo,
)

_USAGE = "usage: pressless [--self-check]"


def main(argv: list[str]) -> int:
    """Print the report, then serve unless this is --self-check.

    Non-zero only where a report question could not be answered at all --
    NotPackaged, FolderUnusable, or choose() raising. `store: file` is not a
    failure: this program cannot tell a machine with no store from a bundle that
    lost its metadata, and PRESS-0022 § 7 decides which by controlling the
    machine.
    """
    if argv not in ([], ["--self-check"]):
        print(_USAGE, file=sys.stderr)
        raise SystemExit(2)

    print("pressless: ok")
    try:
        folder = paths.ensure(paths.own_folder())
        # Relative, so the report names no full path (docs/design.md
        # § Logging): a correct build prints Pressless-data, and anything else
        # is the misplacement PRESS-0022 INV-2 names.
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

    if argv == ["--self-check"]:
        return 0
    return _serve(folder)


def _serve(folder: Path) -> int:
    """PRESS-0013 § 4.5 steps 3 to 6."""
    served = face.serve(folder, open_browser=False)
    try:
        setup.register(served, folder)
        editor.register(served, folder)
        publishing.register(served, folder)
        undo.register(served, folder)
        page_editor.register(served, folder)

        first = "/"
        with served.capture():
            try:
                settings.load(folder)
            except settings.NotSetUp:
                first = "/setup"
            except settings.SettingsError as exc:
                # A file carried from another machine is first run (PRESS-0021 § 4.8).
                if exc.key == "site_folder":
                    first = "/setup"

        link = urllib.parse.urlunsplit(
            urllib.parse.urlsplit(served.url)._replace(path=first))
        try:
            opened = webbrowser.open(link)
        except Exception:  # noqa: BLE001 -- no browser is a case, not a failure
            opened = False
        if not opened:
            print(f"Open this link in your browser: {link}")
        print("Pressless is running. Keep this window open while you use it, "
              "and close it to stop Pressless.")
        try:
            _wait()
        except KeyboardInterrupt:
            pass
    finally:
        served.stop()
    return 0


def _wait() -> None:
    """Block until the console window is closed or interrupted."""
    threading.Event().wait()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
