#!/usr/bin/env python3
"""Start a practice copy of Pressless from this source tree (PRESS-0202).

Made-up writing in a practice folder outside the repository, served by the
launcher's own start-up, so it shows every page the real program shows. It
never publishes and never reaches Google: both connections are replaced by
ones that refuse. The update check runs only in a packaged copy
(`updating.register`), so it never runs here.

`run.sh` starts this for the local web-server manager, which sets PORT and
stops it with SIGTERM. Without PORT the system chooses the port. It runs on
Linux only: its made-up key is kept in a file, which Pressless refuses on
Windows.

    python3 scripts/practice.py
"""
from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pressless import __main__ as launcher  # noqa: E402
from pressless import (  # noqa: E402
    credentials,
    face,
    github_signin,
    google_signin,
    insights,
    publisher,
    settings,
    store,
    updater,
)

FOLDER_NAME = "pressless-practice"
ACCOUNT = "github"
NOT_A_KEY = "practice-copy-not-a-real-key"
REFUSED = "this is a practice copy, which never connects to anything"

HEADER = "<header>{{NAVIGATION}}</header>"
NAVIGATION = ('<nav><a href="{{UP}}index.html" data-nav="Home">Home</a> '
              '<a href="{{UP}}about.html" data-nav="About">About</a></nav>')
FOOTER = "<footer>Practice Notes, {{YEAR}}</footer>"
HOME = """<!doctype html>
<html><body>
<!-- HEADER:START nonav -->
<!-- HEADER:END -->
<h1>Practice Notes</h1>
<p>A made-up site for trying Pressless out.</p>
<!-- FOOTER:START -->
<!-- FOOTER:END -->
</body></html>
"""
ABOUT = """<!doctype html>
<html><body>
<!-- HEADER:START -->
<!-- HEADER:END -->
<h1>About</h1>
<p>Nobody writes here. Every word is made up.</p>
<!-- FOOTER:START -->
<!-- FOOTER:END -->
</body></html>
"""
STYLE = "body{font-family:Georgia,serif;max-width:40rem;margin:2rem auto}\n"


def port_from(text: str | None) -> int:
    """The port PORT names, or 0 for the system's choice. ValueError otherwise."""
    if text is None or text.strip() == "":
        return 0
    port = int(text.strip())   # ValueError for anything that is not a number
    if not 1 <= port <= 65535:
        raise ValueError(f"{port} is not a port number")
    return port


def practice_folder() -> Path:
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / FOLDER_NAME


def seed(folder: Path) -> None:
    """Fill an empty practice folder with a made-up, already set-up site."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "site").mkdir(exist_ok=True)
    for name, html in (("header", HEADER), ("navigation", NAVIGATION), ("footer", FOOTER)):
        store.write_html(folder, store.FURNITURE_FOLDER, name, html)
    for name, html in (("index", HOME), ("about", ABOUT)):
        store.write_html(folder, store.PAGES_FOLDER, name, html)
    assets = folder / "preview-assets"
    assets.mkdir(exist_ok=True)
    (assets / "site.css").write_text(STYLE, encoding="utf-8")
    store.write(folder, store.Entry(
        slug="a-walk-by-the-sea", title="A walk by the sea",
        date=datetime(2026, 9, 12, 18, 30), categories=(), tags=("walks",),
        body="The tide was out, and the gulls had opinions.", extra=()), draft=False)
    store.write(folder, store.Entry(
        slug="half-a-thought", title="Half a thought",
        date=datetime(2026, 10, 1, 21, 5), categories=(), tags=(),
        body="Something about rain. Finish this later.", extra=()), draft=True)
    credentials.write("file", folder, ACCOUNT, NOT_A_KEY)
    settings.save(folder, settings.Settings(
        site_folder=folder / "site", repository="practice/not-a-real-repository",
        site_address="https://practice.example",
        daily_prompt_filter="", untouchable=(),
        credentials=settings.Credentials(store="file", github_account=ACCOUNT,
                                         google_account=None),
        analytics_property_id=None))
    store.write_identity(folder, store.Identity("Practice Notes"))


class _Refuse:
    """Every request is "no answer", the way each transport signals it."""

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        raise OSError(REFUSED)

    def open(self, url: str) -> object:
        raise OSError(REFUSED)

    def wait(self, seconds: float) -> None:
        pass

    def now(self) -> float:
        return time.time()


def disarm(set_attribute=setattr) -> None:
    """Replace every connection Pressless makes with one that refuses.

    `set_attribute` is there so a test can pass monkeypatch.setattr and have
    the replacements undone.
    """
    set_attribute(publisher, "_Urllib", _Refuse)
    set_attribute(updater, "_Urllib", _Refuse)
    set_attribute(insights, "_own_client", _Refuse)
    set_attribute(google_signin, "available", lambda: False)
    set_attribute(github_signin, "available", lambda: False)


def _stop(signum: int, frame: object) -> None:
    # The manager signals the whole process group, so a second SIGTERM can
    # land while the first is shutting down (PRESS-0208).
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise KeyboardInterrupt   # the launcher's own shutdown path


def main() -> int:
    if sys.platform == "win32":
        print("The practice copy runs on Linux only.", file=sys.stderr)
        return 2
    try:
        port = port_from(os.environ.get("PORT"))
    except ValueError:
        print(f"PORT must be a port number, 1 to 65535; it is {os.environ['PORT']!r}.",
              file=sys.stderr)
        return 2
    folder = practice_folder()
    if not (folder / settings.FILE_NAME).exists():
        seed(folder)
    disarm()
    real_serve = face.serve
    face.serve = lambda served_folder: real_serve(served_folder, port)
    signal.signal(signal.SIGTERM, _stop)
    print(f"Practice copy of Pressless, in {folder}. It never publishes.", flush=True)
    try:
        return launcher._serve(folder)
    except KeyboardInterrupt:   # stopped before the launcher's wait caught it
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
