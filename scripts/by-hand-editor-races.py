"""The editor scripts' save races, driven in a browser (PRESS-0135 #13, #14, #15).

Like scripts/by-hand-browser-checks.py, deliberately outside the gate and CI:
it needs Chrome on the machine. Run it by hand after changing either editor's
script, from the venv docs/working-here.md § "Windows and browser checks"
makes:

    .venv-browsers/bin/python scripts/by-hand-editor-races.py

It drives a throwaway instance -- a folder beside the repository, the
Publisher tests' recording transport double slowed so a publish lasts a few
seconds -- and reaches no network, no keyring and none of the writer's own
files.

#14 (Change address waiting for a save in flight) has no row: a local save
finishes before the click lands, so no timing here reaches the race.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_publishing as tp  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from pressless import credentials, editor, face, page_editor, publishing, store, words  # noqa: E402

RESULTS: list[tuple[str, bool]] = []
_PUBLISHED_OR_STOPPED = (
    "document.getElementById('publish-status').textContent.startsWith('Published')"
    " || document.getElementById('save-status').textContent === 'Not saved'")
_CLICK_PUBLISH = ("[...document.querySelectorAll('button')]"
                  ".find(x => x.textContent.trim() === 'Press to site').click()")


def check(name: str, ok: bool) -> None:
    RESULTS.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")


def slowed(transport, seconds: float):
    real = transport.request

    def request(*args, **kwargs):
        time.sleep(seconds)
        return real(*args, **kwargs)

    transport.request = request
    return transport


def typing_during_publish(page, url: str, box: str, name: str) -> None:
    """Type, publish, type again while it runs: saving carries on afterwards."""
    page.goto(url)
    field = page.locator(box).first
    field.click()
    page.keyboard.press("End")
    page.keyboard.type(" one")
    page.wait_for_timeout(1500)
    page.evaluate(_CLICK_PUBLISH)
    # PRESS-0345: the press first shows what will change; Publish now starts it.
    page.locator("dialog.plan").wait_for(state="visible", timeout=15000)
    page.get_by_role("button", name=words.say("script.plan.go"), exact=True).click()
    page.wait_for_timeout(300)
    field.click()
    page.keyboard.press("End")
    page.keyboard.type(" two")
    page.wait_for_function(_PUBLISHED_OR_STOPPED, timeout=60000)
    page.wait_for_timeout(2500)
    check(f"#13 {name}: typing during a publish is saved afterwards",
          page.inner_text("#save-status") == "Saved")


def main() -> int:
    # Beside the repository, never the system temporary folder, which is
    # memory on the maintainer's machine.
    tmp = Path(tempfile.mkdtemp(prefix="pressless-editor-races-", dir=ROOT.parent))
    folder = tp._folder(tmp)
    store.write(folder, tp._entry("seaside", body="Words."), draft=True)
    store.write_html(folder, store.PAGES_FOLDER, "about",
                     "<html><body><p>Hello there.</p></body></html>")
    credentials.read = lambda kind, folder, account: tp.KEY
    publishing._now = lambda: tp.NOW

    served = face.serve(folder)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=slowed(tp._github(), 0.4))
        page_editor.register(served, folder, transport=slowed(tp._github(), 0.4))
        origin = "http://" + urllib.parse.urlsplit(served.url).netloc
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path="/usr/bin/google-chrome",
                                        headless=True)
            page = browser.new_page()
            page.goto(served.url)
            typing_during_publish(page, origin + "/edit?slug=seaside&view=marks",
                                  "textarea[name=body]", "entry editor")
            typing_during_publish(page, origin + "/page?kind=pages&name=about&view=code",
                                  "textarea[name=text]", "page editor")

            page.goto(origin + "/edit?slug=seaside&view=marks")
            # Past the 64 KiB a keepalive request carries (editor.py), so the
            # change cannot be sent as the page goes and the editor asks first.
            page.evaluate("const t = document.querySelector('textarea[name=body]');"
                          "t.value += 'x'.repeat(70000);"
                          "t.dispatchEvent(new Event('input', {bubbles: true}))")
            asked: list[str] = []

            def answer(dialog) -> None:
                # With a listener, Playwright leaves a dialog open until it is answered.
                asked.append(dialog.type)
                dialog.accept()

            page.on("dialog", answer)
            page.close(run_before_unload=True)
            time.sleep(1)
            check("#15: a change too large to send as the page goes asks first",
                  asked == ["beforeunload"])
            browser.close()
    finally:
        served.stop()
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
