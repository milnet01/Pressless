"""PRESS-0133 by-hand browser rows, driven rather than read.

Rows satisfied here (all say "nothing in CI -- by hand, in a browser"):
  PRESS-0013 s10: the script's waiting message and page switch (s 4.4)
  PRESS-0012 s10: the script's timing, pagehide save, no two saves in flight (s 4.7)
  PRESS-0012 s10 (Chrome half only): the policies block Google's script

Deliberately NOT in the gate and NOT in CI, so each spec's s10 row stays
true: it needs a browser on the machine, which local-ci.sh does not assume.
Run it by hand before a release:

    python3 scripts/by-hand-browser-checks.py

It drives a throwaway instance -- temp folder, recording transport double --
so it reaches no network, no keyring and none of the writer's own files.

What it does NOT cover, and what still needs a person (PRESS-0133):
Edge, the Windows box's console window, the real keyring prompt, and a real
publish to GitHub.
"""
from __future__ import annotations

import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_publishing as tp  # noqa: E402

from pressless import credentials, editor, face, publishing, store  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pressless-browser-check-"))
    folder = tp._folder(tmp)
    store.write(folder, tp._entry("seaside", body="Words."), draft=True)
    credentials.read = lambda kind, folder, account: tp.KEY
    publishing._now = lambda: tp.NOW

    served = face.serve(folder, open_browser=False)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=tp._github())
        parts = urllib.parse.urlsplit(served.url)
        secret = urllib.parse.parse_qs(parts.query)["t"][0]
        origin = f"http://{parts.netloc}"
        run(origin, secret, folder)
    finally:
        served.stop()

    print()
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


def run(origin: str, secret: str, folder: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True)
        page = browser.new_page()
        console: list[str] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))

        posts: list[float] = []
        page.on("request", lambda r: posts.append(time.monotonic())
                if r.method == "POST" and r.url.endswith("/save") else None)

        # The token link authenticates at the root and redirects WITHOUT the
        # query, so visit it first for the cookie, then the editor page.
        page.goto(f"{origin}/?t={secret}", wait_until="networkidle")
        page.goto(f"{origin}/edit?slug=seaside", wait_until="networkidle")

        # ---- PRESS-0012 s4.7: the page's shape -------------------------------
        box = page.locator("textarea")
        check("PRESS-0012 s4.7: the box is a textarea", box.count() == 1,
              f"count={box.count()}")
        check("PRESS-0012 s4.7: the preview is a sandboxed iframe",
              page.locator("iframe[sandbox]").count() == 1)
        sandbox = page.locator("iframe[sandbox]").first.get_attribute("sandbox") or ""
        check("PRESS-0012 s4.7: sandbox is allow-same-origin allow-scripts",
              set(sandbox.split()) == {"allow-same-origin", "allow-scripts"}, sandbox)

        # ---- PRESS-0012 s4.7: about a second after the last change -----------
        posts.clear()
        typed_at = time.monotonic()
        box.click()
        box.type("Hello", delay=30)
        page.wait_for_timeout(2500)
        check("PRESS-0012 s4.7: typing triggers exactly one /save", len(posts) == 1,
              f"saves={len(posts)}")
        if posts:
            delay = posts[0] - typed_at
            check("PRESS-0012 s4.7: the save waits about a second after the change",
                  0.6 <= delay <= 2.2, f"{delay:.2f}s after typing began")

        # ---- PRESS-0012 s4.7: never two saves in flight ----------------------
        posts.clear()
        box.click()
        for chunk in ("A", "B", "C", "D"):
            box.type(chunk, delay=10)
            page.wait_for_timeout(300)
        page.wait_for_timeout(2500)
        check("PRESS-0012 s4.7: four changes inside the window coalesce, no pile-up",
              1 <= len(posts) <= 2, f"saves={len(posts)}")

        # ---- PRESS-0012 s4.7: pagehide saves an unsaved change ---------------
        posts.clear()
        box.click()
        box.type(" tail", delay=10)
        page.wait_for_timeout(150)          # inside the ~1s window: unsaved
        before = len(posts)
        page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        page.wait_for_timeout(800)
        check("PRESS-0012 s4.7: pagehide saves the unsaved change",
              len(posts) > before, f"before={before} after={len(posts)}")

        # ---- PRESS-0012 s10: the policy blocks Google's script ---------------
        csp = google_blocked(page, origin, folder)
        check("PRESS-0012 s10 (Chrome): the preview policy blocks Google's script and the player",
              csp[0], csp[1])

        # ---- PRESS-0013 s4.4: the Publish button, its message and the switch --
        page.goto(f"{origin}/edit?slug=seaside", wait_until="networkidle")
        publish = page.locator("button:has-text('Publish'), input[value*='Publish']")
        check("PRESS-0013 s4.4: the editor page carries a Publish button",
              publish.count() >= 1, f"count={publish.count()}")

        if publish.count() >= 1:
            btn = publish.first
            # Sample from the click until the reply lands. The transport is a
            # double, so the in-flight window is short; a single poll can miss
            # it entirely and that is a fact about the probe, not the page.
            page.evaluate(
                """() => {
                     window.__seen = [];
                     const b = [...document.querySelectorAll('button')]
                       .find(x => x.textContent.trim() === 'Publish');
                     const grab = () => window.__seen.push(
                       document.body.innerText.slice(0, 400) + '||' +
                       (b && b.disabled ? 'DISABLED' : 'enabled'));
                     window.__t = setInterval(grab, 20); grab();
                   }""")
            btn.click()
            page.wait_for_timeout(3000)
            samples = page.evaluate("() => { clearInterval(window.__t); return window.__seen; }")
            waiting = [x for x in samples
                       if "this can take a few minutes the first time" in x]
            disabled_while_waiting = [x for x in waiting if x.endswith("DISABLED")]
            check("PRESS-0013 s4.4: it shows the waiting message while publishing",
                  bool(waiting),
                  f"{len(waiting)} of {len(samples)} samples carried it")
            check("PRESS-0013 s4.4: it says to keep the page open",
                  any("Keep this page open" in x for x in waiting))
            check("PRESS-0013 s4.4: the button is disabled while that shows",
                  bool(disabled_while_waiting),
                  f"{len(disabled_while_waiting)} of {len(waiting)} waiting samples")
            after = page.inner_text("body")
            check("PRESS-0013 s4.4: it then shows the published message",
                  "Published." in after and "Your site shows it within a few minutes"
                  in after, repr(_snip(after, "Published")))
            check("PRESS-0013 s4.4: the address bar carries the slug",
                  "slug=seaside" in page.url, page.url.split("?")[-1][:60])

        print("\n  console during the run:")
        for line in console[-12:]:
            print(f"    {line[:160]}")
        browser.close()


def google_blocked(page, origin: str, folder: Path) -> tuple[bool, str]:
    """A PREVIEW page carrying Google's script and a player, loaded as the frame
    loads it, so FILES_POLICY is the policy under test (not the editor page's
    frames-only policy). PRESS-0012 s10 row: "the policies block Google's
    script, the players and a followed outside link in a browser"."""
    from pressless import editor as ed

    preview = folder / ed.PREVIEW_FOLDER
    preview.mkdir(parents=True, exist_ok=True)
    (preview / "policycheck.html").write_text(
        "<!doctype html><html><head>"
        "<script src='https://www.googletagmanager.com/gtag/js?id=G-TEST'></script>"
        "</head><body><p>probe</p>"
        "<iframe src='https://www.youtube.com/embed/dQw4w9WgXcQ'></iframe>"
        "<script src='ran.js'></script>"
        "</body></html>", encoding="utf-8")
    (preview / "ran.js").write_text("window.__ran = true;", encoding="utf-8")

    violations: list[str] = []
    page.goto("about:blank")
    page.add_init_script(
        "window.__v = [];"
        "document.addEventListener('securitypolicyviolation',"
        " e => window.__v.push(e.violatedDirective + ' <- ' + e.blockedURI));")
    response = page.goto(f"{origin}{ed.PREVIEW_ADDRESS}policycheck.html",
                         wait_until="load")
    page.wait_for_timeout(1200)
    csp = (response.headers or {}).get("content-security-policy", "")
    violations = page.evaluate("() => window.__v || []")
    google = [v for v in violations if "googletagmanager" in v]
    player = [v for v in violations if "youtube" in v]
    own_script_ran = page.evaluate("() => window.__ran === true")
    ok = bool(google) and bool(player) and own_script_ran
    return ok, (f"csp={csp!r} google_blocked={bool(google)} "
                f"player_blocked={bool(player)} same-origin script still ran="
                f"{own_script_ran} violations={violations}")


def _snip(text: str, needle: str) -> str:
    i = text.find(needle)
    return text[max(0, i - 20):i + 120] if i >= 0 else text[:140]


if __name__ == "__main__":
    raise SystemExit(main())
