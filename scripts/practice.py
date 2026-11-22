#!/usr/bin/env python3
"""Start a practice copy of Pressless from this source tree (PRESS-0202).

Made-up writing in a practice folder outside the repository, served by the
launcher's own start-up, so it shows every page the real program shows. It
never publishes and reaches no network: `disarm` makes every connection
Pressless can open refuse. The update check runs only in a packaged copy
(`updating.register`), so it never runs here.

`run.sh` starts this for the local web-server manager, which sets PORT and
stops it with SIGTERM, where no released program is named for it to run.
Without PORT the system chooses the port. It runs on
Linux only: its made-up key is kept in a file, which Pressless refuses on
Windows.

    python3 scripts/practice.py
"""
from __future__ import annotations

import operator
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pressless import __main__ as launcher  # noqa: E402
from pressless import (  # noqa: E402
    credentials,
    face,
    github_signin,
    google_signin,
    https,
    settings,
    sites,
    store,
    updater,
    words,
)
from pressless_import import fetch  # noqa: E402

FOLDER_NAME = "pressless-practice"
ACCOUNT = "github"
NOT_A_KEY = "practice-copy-not-a-real-key"
REFUSED = "this is a practice copy, which never connects to anything"
# Network modules disarm leaves alone. The AI helper's bridge is a separate
# program that reaches only this computer's Face (PRESS-0337 § 4.4).
LOCAL_ONLY = ("pressless.bridge",)

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


def _refuse(*args: object, **kwargs: object) -> None:
    """Every request is "no answer", the OSError each transport's caller expects."""
    raise OSError(REFUSED)


def disarm(set_attribute=setattr) -> None:
    """Make every connection Pressless can open refuse.

    Three modules open connections. `https.Client` carries every GitHub,
    Google, YouTube, votes and usage-report request. The Updater has its own
    client. Import's fetch looks names up and connects by itself, and the
    domain wizard uses its look-up. tests/test_practice.py finds those modules
    by what they import, and fails on one this leaves out. Both sign-ins also
    report that this copy carries no registered app.

    `set_attribute` is there so a test can pass monkeypatch.setattr and have
    the replacements undone.
    """
    set_attribute(https.Client, "request", _refuse)
    set_attribute(updater._Urllib, "open", _refuse)
    set_attribute(fetch, "addresses", _refuse)
    set_attribute(fetch, "_connect", _refuse)
    set_attribute(google_signin, "available", lambda: False)
    set_attribute(github_signin, "available", lambda: False)


PRACTICE_WHAT = "failure.practice.what"
PRACTICE_NEXT = "failure.practice.next"
# English only: these words belong to this script, not the shipped program,
# so they are not in words.ENGLISH or the language files.
PRACTICE_WORDS = {
    PRACTICE_WHAT: "This is a practice copy, so it never publishes or connects to anything.",
    PRACTICE_NEXT: "Nothing changed anywhere. To publish for real, use Pressless itself.",
}


def reword(set_item=operator.setitem) -> None:
    """Make every "could not reach" failure say this is a practice copy.

    disarm's refusal reaches the screen as each service's Unreachable, whose
    words tell him to check his connection (PRESS-0430). Call it once every
    screen has added its sentences, as importing the launcher does.
    `set_item` is there so a test can pass monkeypatch.setitem.
    """
    for key, text in PRACTICE_WORDS.items():
        set_item(words.ENGLISH, key, text)
    for kind, sentence in list(face.SENTENCES.items()):
        if kind.__name__ == "Unreachable":
            set_item(face.SENTENCES, kind,
                     face.Sentence(PRACTICE_WHAT, sentence.site, PRACTICE_NEXT, None))


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
        port = launcher.port_from(os.environ.get("PORT"))
    except ValueError:
        print(f"PORT must be a port number, 1 to 65535; it is {os.environ['PORT']!r}.",
              file=sys.stderr)
        return 2
    folder = practice_folder()
    folder.mkdir(parents=True, exist_ok=True)
    # PRESS-0223: the practice site is site-1, like any other; an older
    # practice copy's is moved in first, so it is not seeded twice.
    sites.move_in(folder)
    site = sites.open_site(folder)
    if not (site / settings.FILE_NAME).exists():
        seed(site)
    disarm()
    reword()
    signal.signal(signal.SIGTERM, _stop)
    print(f"Practice copy of Pressless, in {folder}. It never publishes.", flush=True)
    try:
        return launcher._serve(folder, port)
    except launcher.PortHeld:
        print(f"Port {port} is in use by another program.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:   # stopped before the launcher's wait caught it
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
