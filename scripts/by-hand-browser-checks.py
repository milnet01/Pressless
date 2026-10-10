"""PRESS-0133 by-hand browser rows, driven rather than read.

Rows satisfied here (all say "nothing in CI -- by hand, in a browser"):
  PRESS-0013 s10: the script's waiting message and page switch (s 4.4)
  PRESS-0012 s10: the script's timing, pagehide save, no two saves in flight (s 4.7)
  PRESS-0012 s10 (Chrome half only): the policies block Google's script
  PRESS-0018: the cheat sheet folds open below the box, and prints
  PRESS-0017 s7: picking the poem opens a draft holding it

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
from PIL import Image  # noqa: E402

from pressless import (  # noqa: E402
    cheatsheet,
    credentials,
    editor,
    face,
    marks,
    publishing,
    store,
    templates,
    undo,
)

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

    served = face.serve(folder)
    try:
        editor.register(served, folder)
        cheatsheet.register(served)
        templates.register(served, folder)
        publishing.register(served, folder, transport=tp._github())
        undo.register(served, folder, transport=tp._github())
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
        check("PRESS-0012 s4.7: sandbox is allow-same-origin alone (PRESS-0169)",
              sandbox.split() == ["allow-same-origin"], sandbox)

        # ---- PRESS-0018: the cheat sheet -------------------------------------
        sheet = page.locator("details#cheat-sheet")
        check("PRESS-0018: the cheat sheet starts folded",
              sheet.count() == 1 and not sheet.evaluate("d => d.open"))
        sheet.locator("summary").click()
        rows = sheet.locator("tbody tr")
        check("PRESS-0018: opened, it shows one visible row per mark",
              rows.count() == len(marks.MARKS) and rows.first.is_visible(),
              f"rows={rows.count()} marks={len(marks.MARKS)}")
        with page.context.expect_page() as opened:
            sheet.locator("a").click()
        printable = opened.value
        printable.wait_for_load_state("networkidle")
        check("PRESS-0018: the print link opens the sheet in a new tab",
              printable.locator("table.cheat-sheet tbody tr").count() == len(marks.MARKS),
              printable.url)
        printable.close()
        sheet.locator("summary").click()

        # ---- PRESS-0016: Add a photograph, and the missing-photograph note ----
        chosen = folder.parent / "Sea Front.JPG"
        Image.new("RGB", (8, 8), (200, 30, 30)).save(chosen, "JPEG")
        box.click()
        box.evaluate("b => b.setSelectionRange(3, 3)")       # Wor|ds.
        with page.expect_file_chooser() as picker:
            page.get_by_role("button", name="Add a photograph", exact=True).click()
        picker.value.set_files(str(chosen))
        page.wait_for_timeout(2500)
        typed = box.input_value()
        check("PRESS-0016: the mark goes on its own line where he was typing",
              typed == "Wor\n{photo: sea-front.jpg}\nds.", repr(typed))
        check("PRESS-0016: the original is kept under its plain name",
              (folder / "photographs" / "sea-front.jpg").read_bytes()
              == chosen.read_bytes())
        check("PRESS-0016: it says what was added",
              page.inner_text("#photograph-status") == "Added sea-front.jpg.",
              repr(page.inner_text("#photograph-status")))
        note = page.locator("#photograph-missing")
        check("PRESS-0016: no note while every photograph is there", note.is_hidden())
        box.evaluate("b => { b.value += '\\n{photo: gone.jpg}';"
                     " b.dispatchEvent(new Event('input', {bubbles: true})); }")
        page.wait_for_timeout(2500)
        check("PRESS-0016: a photograph Pressless lacks is named as he writes",
              note.is_visible() and "gone.jpg" in note.inner_text()
              and "sea-front.jpg" not in note.inner_text(), repr(note.inner_text()))
        box.evaluate("b => { b.value = 'Words.';"
                     " b.dispatchEvent(new Event('input', {bubbles: true})); }")
        page.wait_for_timeout(2500)
        check("PRESS-0016: the note goes when the name does", note.is_hidden())

        # ---- PRESS-0017 s7: a template picked from the New form ---------------
        page.goto(f"{origin}/", wait_until="networkidle")
        page.fill("input[name=title]", "Rain")
        page.select_option("select[name=template]", "poem")
        page.click("text=New entry")
        page.wait_for_load_state("networkidle")
        poem = next(s for s in templates.starters() if s.slug == "poem").body
        typed = page.locator("textarea").input_value()
        check("PRESS-0017 s7: picking the poem opens a draft holding it",
              typed == poem and "/edit?slug=rain" in page.url, page.url)
        page.goto(f"{origin}/edit?slug=seaside", wait_until="networkidle")

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

        # ---- PRESS-0013 s4.4: the Press to site button, its message and the switch --
        page.goto(f"{origin}/edit?slug=seaside", wait_until="networkidle")
        # Exact text: "Press to site" and "Undo the last press" both hold "press", so a
        # has-text selector matches both and the count says nothing.
        publish = page.get_by_role("button", name="Press to site", exact=True)
        check("PRESS-0013 s4.4: the editor page carries a Press to site button",
              publish.count() >= 1, f"count={publish.count()}")

        if publish.count() >= 1:
            btn = publish.first
            # Sample from the click until the reply lands. The transport is a
            # double, so the in-flight window is short; a single poll can miss
            # it entirely and that is a fact about the probe, not the page.
            # A MutationObserver on the status element rather than a timer:
            # the in-flight window against a transport double can be shorter
            # than any sampling interval, so polling misses a message that was
            # genuinely shown. This records every value it ever held.
            page.evaluate(
                """() => {
                     window.__seen = [];
                     const said = document.getElementById("publish-status");
                     const b = [...document.querySelectorAll("button")]
                       .find(x => x.textContent.trim() === "Press to site");
                     const grab = () => window.__seen.push(
                       said.textContent + "||" +
                       (b && b.disabled ? "DISABLED" : "enabled"));
                     new MutationObserver(grab).observe(
                       said, {childList: true, characterData: true, subtree: true});
                     window.__grab = grab;
                   }""")
            btn.click()
            page.wait_for_timeout(3000)
            samples = page.evaluate("() => window.__seen")
            waiting = [x for x in samples
                       if "this can take a few minutes the first time" in x]
            disabled_while_waiting = [x for x in waiting if x.endswith("DISABLED")]
            check("PRESS-0013 s4.4: it shows the waiting message while publishing",
                  bool(waiting),
                  f"{len(waiting)} of {len(samples)} samples carried it")
            check("PRESS-0235: it no longer says to keep the page open",
                  bool(waiting) and not any("Keep this page open" in x for x in waiting))
            check("PRESS-0013 s4.4: the button is disabled while that shows",
                  bool(disabled_while_waiting),
                  f"{len(disabled_while_waiting)} of {len(waiting)} waiting samples")
            after = page.inner_text("body")
            check("PRESS-0013 s4.4: it then shows the published message",
                  "Published." in after and "Your site shows it within a few minutes"
                  in after, repr(_snip(after, "Published")))
            check("PRESS-0013 s4.4: the address bar carries the slug",
                  "slug=seaside" in page.url, page.url.split("?")[-1][:60])

        # ---- PRESS-0128: throwing away a published entry asks first ----------
        check("PRESS-0128: pressed without a reload, the button says entry, not draft",
              page.get_by_role("button", name="Throw this entry away", exact=True).count() == 1)
        # ---- PRESS-0185: and the line above the form stops calling it a draft --
        pressed = page.inner_text("body")
        check("PRESS-0185: pressed without a reload, the page no longer says a draft",
              "A draft. It is not on your site." not in pressed
              and "This entry is on your site." in pressed,
              repr(_snip(pressed, "on your site")))
        # The page is a published entry's from here: its next save makes a proof.
        page.locator("textarea").type(" More.", delay=10)
        page.wait_for_timeout(2500)
        proofed = page.inner_text("body")
        check("PRESS-0185: the next save on that page shows a proof's line and no address",
              editor.working_copy(folder, "seaside") is not None
              and "These changes are not on your site yet." in proofed
              and "A draft. It is not on your site." not in proofed
              and page.locator("#address").is_hidden(),
              repr(_snip(proofed, "on your site")))
        bin_proof = page.get_by_role("button", name="Bin this proof", exact=True)
        if bin_proof.count() == 1:
            bin_proof.click()
            page.wait_for_load_state("networkidle")
        check("PRESS-0185: Bin this proof on that page bins the proof",
              editor.working_copy(folder, "seaside") is None)
        page.goto(f"{origin}/edit?slug=seaside", wait_until="networkidle")
        asked: list[str] = []

        def say_no(dialog) -> None:
            asked.append(dialog.message)
            dialog.dismiss()

        page.once("dialog", say_no)
        page.get_by_role("button", name="Throw this entry away", exact=True).click()
        page.wait_for_timeout(500)
        check("PRESS-0128: a published entry's question says it leaves the site",
              len(asked) == 1 and "leaves your site" in asked[0], repr(asked))
        check("PRESS-0128: saying no throws nothing away",
              "seaside" in store.list_slugs(folder, draft=False) and "/edit" in page.url)

        # ---- PRESS-0015 s 4.6: the Undo button on both pages ---------------
        undo_here = page.get_by_role("button", name="Undo the last press",
                                     exact=True)
        check("PRESS-0015 s4.6: the editor page carries an Undo button",
              undo_here.count() == 1, f"count={undo_here.count()}")

        page.goto(f"{origin}/", wait_until="networkidle")
        undo_list = page.get_by_role("button", name="Undo the last press",
                                     exact=True)
        check("PRESS-0015 s4.6: the list page carries an Undo button, always shown",
              undo_list.count() == 1, f"count={undo_list.count()}")

        if undo_list.count() == 1:
            page.evaluate(
                """() => {
                     window.__undo = [];
                     const said = document.getElementById("undo-status");
                     new MutationObserver(
                       () => window.__undo.push(said.textContent)
                     ).observe(said, {childList: true, characterData: true,
                                      subtree: true});
                   }""")
            undo_list.click()
            page.wait_for_timeout(4000)
            said = page.evaluate("() => window.__undo")
            check("PRESS-0015 s4.6: it shows the putting-back message",
                  any("Putting your site back" in x
                      for x in said),
                  f"{len(said)} status changes: {said!r}"[:180])
            result = page.inner_text("#undo-result")
            check("PRESS-0015 s4.6: the reply replaces the box and links back",
                  "Back to your writing" in result
                  and page.locator("#listing").is_hidden(),
                  repr(result[:140]))
            check("PRESS-0015 s4.6: the page did not reload itself",
                  page.evaluate("() => window.__undo !== undefined"))

            # PRESS-0235 decision 6: the refusal stays shown, in its box with
            # OK (PRESS-0236), on every page until a save. Close it, then save.
            page.goto(f"{origin}/edit?slug=seaside", wait_until="networkidle")
            check("PRESS-0235: the next page still shows how the undo ended",
                  page.locator("dialog.message[open]").count() == 1)
            page.locator("dialog.message[open]").get_by_role(
                "button", name="OK", exact=True).click()
            page.locator("textarea").type(" Again.", delay=10)
            page.wait_for_timeout(2500)

        # ---- PRESS-0182: a published entry changes address, asked first ------
        # A fresh entry, so the seaside rows above keep their state.
        store.write(folder, tp._entry("harbour", body="Words."), draft=False)
        page.goto(f"{origin}/edit?slug=harbour", wait_until="networkidle")
        check("PRESS-0182: a published entry's page offers Change address",
              page.locator("#address").is_visible())
        page.fill("input[name=address]", "harbour-moved")
        moved_asked: list[str] = []

        def refuse_move(dialog) -> None:
            moved_asked.append(dialog.message)
            dialog.dismiss()

        page.once("dialog", refuse_move)
        page.get_by_role("button", name="Change address", exact=True).click()
        page.wait_for_timeout(500)
        check("PRESS-0182: it asks first, and says old links still reach it",
              len(moved_asked) == 1 and "Links to the old address" in moved_asked[0],
              repr(moved_asked))
        check("PRESS-0182: saying no moves nothing",
              "harbour" in store.list_slugs(folder, draft=False)
              and store.read_forwards(folder) == {})
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Change address", exact=True).click()
        page.wait_for_timeout(1000)
        check("PRESS-0182: saying yes moves it and forwards the old address",
              store.list_slugs(folder, draft=False).count("harbour-moved") == 1
              and store.read_forwards(folder) == {"harbour": "harbour-moved"}
              and "slug=harbour-moved" in page.url,
              f"{store.read_forwards(folder)!r} {page.url.split('?')[-1]}")
        page.locator("textarea").type(" More.", delay=10)
        page.wait_for_timeout(2500)
        check("PRESS-0182: once a save makes a proof, the address is hidden",
              editor.working_copy(folder, "harbour-moved") is not None
              and page.locator("#address").is_hidden())
        page.goto(f"{origin}/edit?slug=harbour-moved", wait_until="networkidle")
        check("PRESS-0182: a proof's own page offers no address",
              not page.locator("#address").is_visible(), page.url.split("?")[-1])
        # ---- PRESS-0185: pressing a proof from its own page ------------------
        page.get_by_role("button", name="Press to site", exact=True).click()
        page.wait_for_timeout(3000)
        pressed = page.inner_text("body")
        check("PRESS-0185: a pressed proof's page stops saying it is not on the site",
              "Published." in pressed
              and "These changes are not on your site yet." not in pressed
              and "This entry is on your site." in pressed
              and page.get_by_role("button", name="Bin this proof", exact=True).count() == 0,
              repr(_snip(pressed, "on your site")))
        # ---- PRESS-0186: the address comes back once the proof is pressed ----
        address = page.locator("input[name=address]")
        check("PRESS-0186: a proof pressed from its own page offers Change address",
              page.locator("#address").is_visible()
              and address.input_value() == "harbour-moved",
              address.input_value() if address.count() else "no field")
        page.locator("textarea").type(" Again.", delay=10)
        page.wait_for_timeout(2500)
        hidden = page.locator("#address").is_hidden()
        page.get_by_role("button", name="Press to site", exact=True).click()
        page.wait_for_timeout(3000)
        check("PRESS-0186: hidden for the next proof, and back when that is pressed",
              hidden and page.locator("#address").is_visible()
              and editor.working_copy(folder, "harbour-moved") is None,
              f"hidden for the proof={hidden}")

        # ---- PRESS-0128: throwing away a draft with a change still unsaved ----
        page.goto(f"{origin}/", wait_until="networkidle")
        page.fill("input[name=title]", "Gull")
        page.click("text=New entry")
        page.wait_for_load_state("networkidle")
        page.locator("textarea").type("Unsaved", delay=10)
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Throw this draft away", exact=True).click()
        page.wait_for_url(f"{origin}/", timeout=5000)
        binned = sorted(p.name for p in (folder / "bin").rglob("gull*.txt"))
        check("PRESS-0128: saying yes bins the draft and goes back to the list",
              "gull" not in store.list_slugs(folder, draft=True) and binned == ["gull.txt"],
              f"{binned!r} {page.url}")

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
    # The Builder refuses a preview folder holding files it did not make, so
    # the probe pages go before the next preview is built.
    (preview / "policycheck.html").unlink()
    (preview / "ran.js").unlink()
    ok =bool(google) and bool(player) and own_script_ran
    return ok, (f"csp={csp!r} google_blocked={bool(google)} "
                f"player_blocked={bool(player)} same-origin script still ran="
                f"{own_script_ran} violations={violations}")


def _snip(text: str, needle: str) -> str:
    i = text.find(needle)
    return text[max(0, i - 20):i + 120] if i >= 0 else text[:140]


if __name__ == "__main__":
    raise SystemExit(main())
