"""What the manual's media scripts share: where things are, the throwaway
instance, and the browser (PRESS-0219 § 4.6, PRESS-0361).

Linux only. `shots.py` and `video.py` run under the system `python3`, which
holds Playwright; the instance runs under the project's `.venv`, which holds
what Pressless needs. Everything written lands in WORK, never in the tree:
`scratch/` is gitignored, and PRESSLESS_MANUAL_WORK names another place.
"""
from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = Path(os.environ.get("PRESSLESS_MANUAL_WORK") or ROOT / "scratch" / "manual-media")
INSTANCE = WORK / "instance"
CHROME = "/usr/bin/google-chrome"
PHOTOGRAPH = HERE / "harbour-dawn.jpg"

_running: list[subprocess.Popen] = []


def stop() -> None:
    """End the instance and remove its folder."""
    while _running:
        process = _running.pop()
        process.terminate()
        process.wait()
    shutil.rmtree(INSTANCE, ignore_errors=True)


atexit.register(stop)


def start(mode: str = "site") -> str:
    """Restart the instance and return its link.

    `site` is the made-up Seaside Notes site; `fresh` is an empty install.
    The link admits ONE browser, so every script that wants a new browser
    context without the first one's cookies restarts it.
    """
    stop()
    WORK.mkdir(parents=True, exist_ok=True)
    log = WORK / "instance.log"
    with log.open("w") as out:
        _running.append(subprocess.Popen(  # noqa: S603 -- our own script, fixed arguments
            [str(ROOT / ".venv" / "bin" / "python"), "-u", str(HERE / "instance.py"), mode],
            stdout=out, stderr=subprocess.STDOUT))
    for _ in range(60):
        found = re.search(r"LINK (\S+)", log.read_text())
        if found:
            return found.group(1)
        if _running[0].poll() is not None:
            break
        time.sleep(0.5)
    raise SystemExit(f"the instance did not start:\n{log.read_text()}")


def origin(link: str) -> str:
    """`http://127.0.0.1:<port>`, without the path or the one-time secret."""
    return re.match(r"https?://[^/]+", link).group(0)


def chrome(playwright, **options):
    return playwright.chromium.launch(executable_path=CHROME, headless=True, **options)
