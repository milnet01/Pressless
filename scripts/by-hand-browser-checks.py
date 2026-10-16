"""PRESS-0133 by-hand browser rows, driven rather than read.

Rows satisfied here (all say "nothing in CI -- by hand, in a browser"):
  PRESS-0013 s10: the script's waiting message and page switch (s 4.4)
  PRESS-0012 s10: the script's timing, pagehide save, no two saves in flight (s 4.7)
  PRESS-0012 s10 (Chrome half only): the policies block Google's script
  PRESS-0018: the cheat sheet folds open below the box, and prints
  PRESS-0017 s7: picking the poem opens a draft holding it
  PRESS-0260 s10: INV-5's no-script half, INV-9, and the visual view's keys
    and buttons (s 4.3, s 4.4)
  PRESS-0261: the code boxes' colours line up with the letters typed over them
  PRESS-0263: the true-colours switch is kept, and the preview starts undimmed
  PRESS-0264: Move to takes a section between columns, out of them and back
  PRESS-0265: a section is dragged into place with the mouse
  PRESS-0216: the header is typed in on the page; the menu's links are
    changed, moved and added in its list
  PRESS-0217 s10: the pieces behave on the published site, and in the
    visual editor show their fallbacks, a script piece among them inert
  PRESS-0273: a style piece shows as its code, and its CSS reaches the
    preview frame but never the Face's own page
  PRESS-0197 s10: INV-10's upload half -- a file uploaded from a music
    section's panel sets the field to ../files/<name>

Deliberately NOT in the gate and NOT in CI, so each spec's s10 row stays
true: it needs a browser on the machine, which local-ci.sh does not assume.
Run it by hand before a release:

    python3 scripts/by-hand-browser-checks.py
    python3 scripts/by-hand-browser-checks.py --browser firefox
    python3 scripts/by-hand-browser-checks.py --cdp http://127.0.0.1:19222 \
        --port 47501 --site-port 47502

Firefox is Playwright's own build (`playwright install firefox`); it cannot
drive the system Firefox. `--cdp` drives a browser already started with a
debugging port -- Edge on the Windows box, through an SSH tunnel -- which
reaches this machine only where both ports are forwarded back to it
(`ssh -R 47501:127.0.0.1:47501 -R 47502:127.0.0.1:47502 <box>`).

It drives a throwaway instance -- temp folder, recording transport double --
so it reaches no network, no keyring and none of the writer's own files.

What it does NOT cover, and what still needs a person (PRESS-0133):
the Windows box's console window, the real keyring prompt, and a real
publish to GitHub.
"""
from __future__ import annotations

import argparse
import functools
import io
import json
import sys
import tempfile
import threading
import time
import urllib.parse
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_publishing as tp  # noqa: E402
from PIL import Image  # noqa: E402

from pressless import (  # noqa: E402
    blocks,
    builder,
    cheatsheet,
    credentials,
    editor,
    face,
    files_screen,
    marks,
    page_editor,
    publishing,
    settings,
    setup,
    sites,
    sites_screen,
    store,
    templates,
    undo,
)

RESULTS: list[tuple[str, bool, str]] = []
RESTARTS: list[int] = []
OPTIONS = argparse.Namespace(browser="chrome", cdp=None, port=0, site_port=0)


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="PRESS-0133's browser rows, driven.")
    parser.add_argument("--browser", choices=("chrome", "firefox"), default="chrome")
    parser.add_argument("--cdp", help="drive the browser at this debugging address instead")
    parser.add_argument("--port", type=int, default=0, help="the Face's port")
    parser.add_argument("--site-port", type=int, default=0, help="the built site's port")
    parser.parse_args(namespace=OPTIONS)
    # PRESS-0271: removed on the way out, failure included; /tmp is RAM here.
    with tempfile.TemporaryDirectory(prefix="pressless-browser-check-") as tmp:
        folder = tp._folder(Path(tmp))
        store.write(folder, tp._entry("seaside", body="Words."), draft=True)
        credentials.read = lambda kind, folder, account: tp.KEY
        publishing._now = lambda: tp.NOW

        served = face.serve(folder, OPTIONS.port)
        try:
            editor.register(served, folder)
            cheatsheet.register(served)
            templates.register(served, folder)
            publishing.register(served, folder, transport=tp._github())
            undo.register(served, folder, transport=tp._github())
            page_editor.register(served, folder, transport=tp._github())
            files_screen.register(served, folder)
            setup.register(served, folder, transport=tp._github(),
                           shortcut_places=lambda: None)
            # PRESS-0223: the Sites screen over a Pressless-data of its own,
            # holding two sites; a restart is only recorded.
            sites_own = Path(tmp) / "sites-own"
            for number, named in ((1, "The First Site"), (2, "The Second Site")):
                site = sites_own / "sites" / f"site-{number}"
                site.mkdir(parents=True)
                store.write_identity(site, store.Identity(named))
            sites.choose(sites_own, "site-1")
            sites_screen.register(served, sites_own, lambda: RESTARTS.append(1))
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
        if OPTIONS.cdp:
            browser = pw.chromium.connect_over_cdp(OPTIONS.cdp)
            page = browser.contexts[0].new_page()
            # A real window's size is the desktop's; the rows were measured at
            # the launched browsers' default, and PRESS-0261's needs the code
            # box to overflow it.
            page.set_viewport_size({"width": 1280, "height": 720})
        elif OPTIONS.browser == "firefox":
            browser = pw.firefox.launch(headless=True)
            page = browser.new_page()
        else:
            browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome",
                                         headless=True)
            page = browser.new_page()
        print("  browser:", browser.browser_type.name, browser.version)
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
        # The bytes rather than the path, which a browser on another machine lacks.
        picker.value.set_files({"name": chosen.name, "mimeType": "image/jpeg",
                                "buffer": chosen.read_bytes()})
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
        check("PRESS-0012 s10 (Chrome): the preview policy blocks Google's script, the player "
              "and every script of the page's own, opened outside the frame (PRESS-0268)",
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

        visual_editor(page, origin, folder)
        code_colours(page, origin)
        true_colours_kept(page, origin)
        move_between_columns(page, origin, folder)
        drag_sections(page, origin, folder)
        furniture_views(page, origin, folder)
        pieces(page, origin, folder)
        kept_files(page, origin, folder)
        players_picked(page, origin, folder)
        added_by_upload(page, origin, folder)
        sites_listed(page, origin, folder)
        site_file(page, origin, folder)
        move_wizard(page, origin)
        enlarge_photograph(page, origin, folder)
        settings_pictures(page, origin, folder)

        print("\n  console during the run:")
        for line in console[-12:]:
            print(f"    {line[:160]}")
        if OPTIONS.cdp:
            page.close()  # the browser is the person's; leave it running
        else:
            browser.close()


# PRESS-0260: a page whose code section would set the frame's title if a
# script ran there (INV-5).
VISUAL_PAGE = (
    "<!doctype html><html><head><title>Visual</title></head><body>\n"
    "<!-- HEADER:START -->\n<!-- HEADER:END -->\n<main><!-- pressless:page -->\n"
    "<!-- pressless:heading --><h1>Title words</h1><!-- /pressless:heading -->\n"
    "<!-- pressless:text --><p>First paragraph.</p><!-- /pressless:text -->\n"
    "<!-- pressless:code --><script>document.title = 'RAN';</script>"
    "<div>code part</div><!-- /pressless:code -->\n"
    "<!-- /pressless:page --></main>\n<!-- FOOTER:START -->\n<!-- FOOTER:END -->\n"
    "</body></html>\n")


def kept_files(page, origin: str, folder: Path) -> None:
    """PRESS-0197 INV-10: a file uploaded from a music section's panel."""
    store.write_html(folder, store.PAGES_FOLDER, "songs",
                     VISUAL_PAGE.replace("<title>Visual", "<title>Songs"))
    waiting = store.html_path_for(folder, store.PAGES_FOLDER, "songs", waiting=True)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{origin}/page?kind=pages&name=songs", wait_until="networkidle")
    page.select_option("#add-kind", "music")
    page.fill("#add-address", "typed.mp3")
    page.locator("[data-act=add]").click()
    page.locator("#file-file").set_input_files(
        {"name": "My Song.mp3", "mimeType": "audio/mpeg", "buffer": b"ID3 a made-up song"})
    page.wait_for_timeout(1600)
    page.wait_for_function("document.getElementById('save-status').textContent !== "
                           "'Saving'", timeout=5000)
    music = [s.fields.get("src") for s in blocks.read("songs", store.read_html(waiting)).sections
             if s.kind == "music"]
    kept = folder / "files" / "my-song.mp3"
    check("PRESS-0197 INV-10: an upload from the panel sets ../files/<name>",
          music == ["../files/my-song.mp3"] and kept.is_file(), f"{music} kept={kept.is_file()}")
    page.goto(f"{origin}/files", wait_until="networkidle")
    listed = page.locator("table.kept-files").inner_text()
    check("PRESS-0197 s4.4: the Files screen names the page using the file",
          "my-song.mp3" in listed and "songs" in listed, listed)
    check("PRESS-0197: the upload raised no script error", not errors, str(errors))


def players_picked(page, origin: str, folder: Path) -> None:
    """PRESS-0287: a click on a player picks its section."""
    tone = folder / "files" / "tone.wav"
    tone.parent.mkdir(exist_ok=True)
    with wave.open(str(tone), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b"\0\0" * 8000)
    players = (
        '<!-- pressless:music --><audio controls preload="metadata" src="../files/tone.wav">'
        "</audio><!-- /pressless:music -->\n"
        '<!-- pressless:video --><video controls preload="metadata" src="../files/tone.wav">'
        "</video><!-- /pressless:video -->\n"
        '<!-- pressless:video --><iframe src="https://www.youtube-nocookie.com/embed/aaaaaaaaaaa"'
        ' title="YouTube video" allowfullscreen loading="lazy"></iframe>'
        "<!-- /pressless:video -->\n")
    store.write_html(folder, store.PAGES_FOLDER, "players", VISUAL_PAGE.replace(
        "<title>Visual", "<title>Players").replace("<!-- /pressless:page -->",
                                                    players + "<!-- /pressless:page -->"))
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{origin}/page?kind=pages&name=players", wait_until="networkidle")
    frame = page.frame_locator("#preview")
    named = []
    for player in ("audio", "video", "iframe"):
        frame.locator("p", has_text="First paragraph.").click()
        box = frame.locator(player).bounding_box()
        # On the control bar, where a player's own controls take the click.
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] - 12)
        named.append(page.locator("#picked").text_content())
    check("PRESS-0287: a click on a music, video or YouTube player picks its section",
          named == ["Changing: Music", "Changing: Video", "Changing: Video"], str(named))
    check("PRESS-0287: picking players raised no script error", not errors, str(errors))


def sites_listed(page, origin: str, folder: Path) -> None:
    """PRESS-0223 INV-9: the Sites screen names each site, and Open chooses
    another and restarts. That the restart opens it is INV-6's test."""
    sites_own = folder.parent / "sites-own"
    page.goto(f"{origin}/sites", wait_until="networkidle")
    listed = page.locator("ul.sites").inner_text()
    check("PRESS-0223: the Sites screen names each site, the open one marked",
          "The First Site (open now)" in listed and "The Second Site" in listed, listed)
    page.locator("ul.sites button").click()
    page.wait_for_load_state("networkidle")
    opened = json.loads((sites_own / "sites.json").read_text(encoding="utf-8"))["open"]
    check("PRESS-0223: Open chooses the other site and restarts",
          opened == "site-2" and RESTARTS == [1]
          and "Pressless is restarting." in page.locator("main").inner_text(),
          f"open={opened} restarts={RESTARTS}")


def site_file(page, origin: str, folder: Path) -> None:
    """PRESS-0224 INV-10: Save downloads the open site as one file, and Open
    with that file makes it a new site and restarts."""
    sites_own = folder.parent / "sites-own"
    shown = sites.open_site(sites_own)
    store.write(shown, tp._entry("saved-and-opened"), draft=True)
    before = len(RESTARTS)
    page.goto(f"{origin}/sites", wait_until="networkidle")
    with page.expect_download() as saving:
        page.get_by_text("Save this site to a file").click()
    saved = Path(saving.value.path())
    check("PRESS-0224: Save downloads the site as a .zip",
          saving.value.suggested_filename.endswith(".zip") and saved.stat().st_size > 0,
          saving.value.suggested_filename)
    with page.expect_file_chooser() as chooser:
        page.locator("#open-site-file").click()
    chooser.value.set_files(str(saved))
    page.wait_for_function("document.body.innerText.includes('Pressless is restarting.')",
                           timeout=10000)
    opened = sites.open_site(sites_own)
    check("PRESS-0224: Open makes the file a new site and restarts",
          opened != shown and (opened / "drafts" / "saved-and-opened.txt").is_file()
          and len(RESTARTS) == before + 1, f"opened={opened.name}")


def move_wizard(page, origin: str) -> None:
    """PRESS-0221: the move opens as a dialog over the Sites screen, one step
    at a time, and each site saves from it."""
    page.goto(f"{origin}/sites", wait_until="networkidle")
    box = page.locator("#move-wizard")
    page.locator("[data-help=move-wizard]").click()
    shown = lambda: box.locator("[data-step]:visible").get_attribute("data-step")  # noqa: E731
    seen = [box.evaluate("d => d.open && d.matches(':modal')"), shown()]
    box.locator("[data-move=next]").click()
    seen.append(shown())
    box.locator("[data-move=next]").click()
    seen += [shown(), box.locator("[data-move=next]").is_disabled()]
    box.locator("[data-move=back]").click()
    seen.append(shown())
    box.locator("[data-close]").click()
    page.locator("[data-help=move-wizard]").click()
    seen.append(shown())
    check("PRESS-0221: the move is a dialog, one step at a time, starting again on reopening",
          seen == [True, "1", "2", "3", True, "2", "1"], str(seen))
    with page.expect_download() as saving:
        box.locator("a[href*='/sites/save?site=']").first.click()
    check("PRESS-0221: a site saves from the dialog",
          saving.value.suggested_filename.endswith(".zip"), saving.value.suggested_filename)


def added_by_upload(page, origin: str, folder: Path) -> None:
    """PRESS-0282: Add with no address asks for the file, and the upload
    becomes the new section's address."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    store.write_html(folder, store.PAGES_FOLDER, "uploads",
                     VISUAL_PAGE.replace("<title>Visual", "<title>Uploads"))
    waiting = store.html_path_for(folder, store.PAGES_FOLDER, "uploads", waiting=True)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{origin}/page?kind=pages&name=uploads", wait_until="networkidle")
    asked = []
    # The Face checks a file's first bytes against its name.
    for kind, name, start in (("music", "Tune.mp3", b"ID3"),
                              ("download", "Notes.pdf", b"%PDF-1.4")):
        page.select_option("#add-kind", kind)
        page.fill("#add-address", "")
        try:
            with page.expect_file_chooser(timeout=3000) as chooser:
                page.locator("[data-act=add]").click()
            chooser.value.set_files({"name": name, "mimeType": "application/octet-stream",
                                     "buffer": start + b" made-up bytes"})
            asked.append(kind)
        except PlaywrightTimeout:
            continue  # no chooser opened: the failure this row reports
        page.wait_for_timeout(1600)
    page.wait_for_function("document.getElementById('save-status').textContent !== "
                           "'Saving'", timeout=5000)
    found = {s.kind: s.fields.get("src") or s.fields.get("href")
             for s in blocks.read("uploads", store.read_html(waiting)).sections
             if s.kind in ("music", "download")} if waiting.is_file() else {}
    check("PRESS-0282: Add with no address asks for the file, and the upload is its address",
          asked == ["music", "download"]
          and found == {"music": "../files/tune.mp3", "download": "../files/notes.pdf"},
          f"asked={asked} found={found}")
    check("PRESS-0282: adding by upload raised no script error", not errors, str(errors))


def enlarge_photograph(page, origin: str, folder: Path) -> None:
    """PRESS-0289: Add photograph fills an enlarge section, as a picture's."""
    store.write_html(folder, store.PAGES_FOLDER, "enlarged",
                     VISUAL_PAGE.replace("<title>Visual", "<title>Enlarged"))
    waiting = store.html_path_for(folder, store.PAGES_FOLDER, "enlarged", waiting=True)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{origin}/page?kind=pages&name=enlarged", wait_until="networkidle")
    page.select_option("#add-kind", "enlarge")
    page.fill("#add-address", "typed.png")
    page.locator("[data-act=add]").click()
    picture = io.BytesIO()
    Image.new("RGB", (300, 200), (40, 90, 160)).save(picture, "PNG")
    with page.expect_file_chooser() as chooser:
        page.locator("[data-act=photograph]").click()
    chooser.value.set_files({"name": "Big View.png", "mimeType": "image/png",
                             "buffer": picture.getvalue()})
    page.wait_for_timeout(1600)
    page.wait_for_function("document.getElementById('save-status').textContent !== "
                           "'Saving'", timeout=5000)
    src = [s.fields.get("src") for s in blocks.read("enlarged", store.read_html(waiting)).sections
           if s.kind == "enlarge"] if waiting.is_file() else []
    check("PRESS-0289: Add photograph sets an enlarge section's photograph",
          src == ["../photographs/big-view.png"], str(src))
    check("PRESS-0289: the enlarge photograph raised no script error", not errors, str(errors))


def settings_pictures(page, origin: str, folder: Path) -> None:
    """PRESS-0227 INV-9: Settings' picture rows upload, show and remove."""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{origin}/setup", wait_until="networkidle")
    row = page.locator('[data-picture="site_icon"]')
    kept = row.locator('input[name="site_icon"]')
    shown = row.locator(".picture-shown img")
    frame = row.locator(".picture-shown")
    before = frame.bounding_box()
    picture = io.BytesIO()
    Image.new("RGB", (300, 200), (40, 90, 160)).save(picture, "PNG")
    row.locator("input[type=file]").set_input_files(
        {"name": "Sample Icon.png", "mimeType": "image/png", "buffer": picture.getvalue()})
    page.wait_for_function(
        "document.querySelector('input[name=site_icon]').value !== ''", timeout=5000)
    name = kept.input_value()
    loaded = shown.evaluate("img => img.complete && img.naturalWidth > 0")
    check("PRESS-0227 INV-9: choosing a file uploads it, shows it and fills the input",
          (folder / "photographs" / name).is_file() and shown.is_visible() and loaded,
          f"{name!r} visible={shown.is_visible()} loaded={loaded}")
    during = frame.bounding_box()
    row.locator("button[data-remove]").click()
    after = frame.bounding_box()
    check("PRESS-0227: the picture's frame keeps its place, chosen or removed",
          before is not None and before == during == after, f"{before} {during} {after}")
    check("PRESS-0227 INV-9: Remove empties the input and hides the picture",
          kept.input_value() == "" and not shown.is_visible(), kept.input_value())

    picture_row = page.locator('[data-picture="site_picture"]')
    picture_row.locator("input[type=file]").set_input_files(
        {"name": "broken.png", "mimeType": "image/png", "buffer": b"not a picture at all"})
    said = page.locator("#site_picture-said")
    page.wait_for_function(
        "document.getElementById('site_picture-said').textContent.trim() !== ''",
        timeout=5000)
    check("PRESS-0227 s4.2: a refused upload says why, and keeps the input as it was",
          said.is_visible() and picture_row.locator('input[name="site_picture"]')
          .input_value() == "", said.inner_text()[:120])
    page.keyboard.press("Escape")
    check("PRESS-0227: the rows raised no script error", not errors, str(errors))


def visual_editor(page, origin: str, folder: Path) -> None:
    """PRESS-0260 s10: the rows no test without a browser reaches."""
    store.write_html(folder, store.PAGES_FOLDER, "visual", VISUAL_PAGE)
    waiting = store.html_path_for(folder, store.PAGES_FOLDER, "visual", waiting=True)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def sections() -> list[tuple[str, str]]:
        """The waiting copy's sections, as (kind, html or code) pairs."""
        read = blocks.read("visual", store.read_html(waiting))
        return [(s.kind, s.fields.get("html", s.source)) for s in read.sections]

    def saved() -> None:
        page.wait_for_timeout(1600)
        page.wait_for_function("document.getElementById('save-status').textContent !== "
                               "'Saving'", timeout=5000)

    page.goto(f"{origin}/page?kind=pages&name=visual", wait_until="networkidle")
    frame = page.frame_locator("#preview")
    nothing = page.locator("#picked").text_content()
    sandbox = page.locator("#preview").get_attribute("sandbox") or ""
    title = page.evaluate("document.getElementById('preview').contentDocument.title")
    check("PRESS-0260 INV-5: the frame runs no script of the page's",
          sandbox.split() == ["allow-same-origin"] and title == "Visual",
          f"sandbox={sandbox!r} title={title!r}")

    paragraph = frame.locator("p", has_text="First paragraph.")
    paragraph.click()
    picked = page.locator("#picked").text_content()
    check("PRESS-0260 s4.3: a click picks the section and the panel names it",
          picked == "Changing: Paragraph", picked)
    page.keyboard.press("End")
    page.keyboard.type(" More ")
    page.keyboard.press("Control+b")
    page.keyboard.type("bold")
    page.keyboard.press("Control+b")
    saved()
    check("PRESS-0260 INV-9: typed words with Ctrl+B save as a text section",
          ("text", "First paragraph. More <strong>bold</strong>") in sections(), str(sections()))

    page.keyboard.press("Enter")
    page.keyboard.type("Second")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("line")
    saved()
    texts = [words for kind, words in sections() if kind == "text"]
    check("PRESS-0260 s4.4: Enter splits, Shift+Enter writes a br",
          texts == ["First paragraph. More <strong>bold</strong>", "Second<br>line"], str(texts))

    if page.context.browser.browser_type.name == "firefox":
        # Firefox drops a made-up paste event's clipboardData, so paste for real.
        page.evaluate("""() => navigator.clipboard.write([new ClipboardItem({
          'text/html': new Blob(['<span style="color:red">styled&nbsp;words</span>'],
                                {type: 'text/html'}),
          'text/plain': new Blob([' pasted words'], {type: 'text/plain'})})])""")
        page.keyboard.press("Control+v")
    else:
        page.evaluate("""() => {
          const doc = document.getElementById('preview').contentDocument;
          const data = new DataTransfer();
          data.setData('text/html', '<span style="color:red">styled&nbsp;words</span>');
          data.setData('text/plain', ' pasted words');
          doc.activeElement.dispatchEvent(new ClipboardEvent('paste',
            {clipboardData: data, bubbles: true, cancelable: true}));
        }""")
    page.once("dialog", lambda dialog: dialog.accept("https://example.org/"))
    page.keyboard.press("Control+k")
    saved()
    texts = [words for kind, words in sections() if kind == "text"]
    check("PRESS-0260 INV-9: pasting takes the plain text, and Ctrl+K links",
          texts[1:] == ['Second<br>line pasted words<a href="https://example.org/">'
                        'https://example.org/</a>'], str(texts))

    second = frame.locator("p", has_text="pasted words")
    second.click()
    page.evaluate("""() => {
      const doc = document.getElementById('preview').contentDocument;
      const element = doc.activeElement;
      doc.getSelection().collapse(element, 0);
    }""")
    page.keyboard.press("Backspace")
    saved()
    joined = [words for kind, words in sections() if kind == "text"]
    check("PRESS-0260 s4.4: Backspace at the start joins it to the text above",
          joined == ["".join(texts)], str(joined))

    page.select_option("#add-kind", "button")
    page.fill("#add-address", "contact.html")
    page.locator("[data-act=add]").click()
    saved()
    kinds = [kind for kind, _ in sections()]
    check("PRESS-0260 s4.3: Add below puts a button under the picked section",
          kinds == ["heading", "text", "button", "code"], str(kinds))
    up = page.locator("[data-act=up]")
    up.click()
    saved()
    kinds = [kind for kind, _ in sections()]
    check("PRESS-0260 s4.3: Move up moves it", kinds == ["heading", "button", "text", "code"],
          str(kinds))
    up.click()
    disabled = up.is_disabled()
    check("PRESS-0260 s4.3: at the top, Move up is shown disabled, not hidden",
          disabled and up.is_visible(), f"disabled={disabled}")
    page.locator("[data-act=remove]").click()
    saved()
    kinds = [kind for kind, _ in sections()]
    check("PRESS-0260 s4.3: Remove takes it away", kinds == ["heading", "text", "code"],
          str(kinds))

    frame.locator("div", has_text="code part").click()
    shown = [act for act in ("bold", "italic", "link", "add-to")
             if page.locator(f"#panel [data-act={act}]").first.is_visible()]
    check("PRESS-0288: a code section's panel shows no Bold, Italic, Link or Add to column",
          not shown, str(shown))
    in_sight = page.evaluate("""() => {
      const panel = document.getElementById('panel');
      panel.scrollTop = panel.scrollHeight;
      const line = document.getElementById('picked').getBoundingClientRect();
      const at = document.elementFromPoint(line.left + 4, line.top + line.height / 2);
      return [panel.scrollTop, at ? at.id || at.tagName : null];
    }""")
    page.evaluate("document.getElementById('panel').scrollTop = 0")
    check("PRESS-0279: the Changing line stays in sight when the panel scrolls",
          in_sight[0] > 0 and in_sight[1] == "picked", str(in_sight))
    code = page.locator("[data-field=code]")
    shown = code.input_value()
    check("PRESS-0260 s4.5: the panel shows a code section's HTML without its marks",
          shown == "<script>document.title = 'RAN';</script><div>code part</div>", shown)
    code.fill("<div>new code</div>")
    saved()
    check("PRESS-0260 s3 decision 5: a code section is changed in the panel",
          ("code", "<!-- pressless:code --><div>new code</div><!-- /pressless:code -->")
          in sections(), str(sections()))

    painted = page.evaluate("""() => {
      const copy = document.querySelector('#panel .code-box > pre');
      return [copy.textContent, copy.querySelectorAll('.k-tag').length];
    }""")
    check("PRESS-0261: the panel's code box is coloured, and follows a change",
          painted[0] == "<div>new code</div>" and painted[1] == 4, str(painted))

    frame.locator("h2, h1", has_text="Title words").first.click()
    page.select_option("[data-field=level]", "3")
    saved()
    heading = blocks.read("visual", store.read_html(waiting)).sections[0]
    check("PRESS-0260 s4.3: a heading's size is changed in the panel",
          heading.kind == "heading" and heading.fields["level"] == "3", str(heading))

    boat = store.photograph_path_for(folder, "my boat.jpg")
    boat.parent.mkdir(exist_ok=True)
    Image.new("RGB", (40, 30), (20, 90, 160)).save(boat, "JPEG")
    page.select_option("#add-kind", "picture")
    page.fill("#add-address", "../photographs/my%20boat.jpg")
    page.locator("[data-act=add]").click()
    saved()
    page.wait_for_timeout(800)
    shown = page.evaluate("""() => {
      const img = document.getElementById('preview').contentDocument.querySelector('img');
      return img ? img.naturalWidth : -1;
    }""")
    check("PRESS-0260 s4.6: a held photograph shows in the preview",
          [kind for kind, _ in sections()][:2] == ["heading", "picture"] and shown == 40,
          f"{[kind for kind, _ in sections()]} naturalWidth={shown}")

    page.select_option("#add-kind", "columns")
    page.locator("[data-act=add]").click()
    page.select_option("[data-field=count]", "3")
    page.select_option("#add-kind", "text")
    page.locator("[data-act=add-to][data-column='2']").click()
    saved()
    columns = blocks.read("visual", store.read_html(waiting)).sections[2]
    check("PRESS-0260 s4.3: columns are added, widened, and given a section",
          columns.kind == "columns" and [len(part) for part in columns.parts] == [0, 0, 1],
          str(columns))
    page.select_option("[data-field=count]", "2")
    said = page.locator("#panel-said").text_content()
    check("PRESS-0260 s4.3: fewer columns is refused while the last holds a section",
          page.locator("[data-field=count]").input_value() == "3" and bool(said), said)
    frame.locator("h3", has_text="Title words").click()
    page.keyboard.press("Escape")
    escaped = page.locator("#picked").text_content()
    frame.locator("div", has_text="new code").click()
    box = page.locator("#preview").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] - 8)
    outside = page.locator("#picked").text_content()
    frame.locator("div", has_text="new code").click()
    page.locator("[data-act=remove]").focus()
    page.keyboard.press("Escape")
    in_panel = page.locator("#picked").text_content()
    check("PRESS-0280: Escape in the page or the panel, or a click outside every section, "
          "unpicks it", escaped == outside == in_panel == nothing,
          f"{escaped!r} {outside!r} {in_panel!r}")
    check("PRESS-0260: the visual view raised no script error", not errors, str(errors))


def code_colours(page, origin: str) -> None:
    """PRESS-0261: the coloured copy behind the code box wraps, scrolls and
    reads as the box does, so each colour sits on its own letter."""
    page.goto(f"{origin}/page?kind=pages&name=visual&view=code", wait_until="networkidle")
    box = page.locator("textarea[name=text]")
    box.click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\n<p class=\"late\">" + "long words " * 40 + "</p>")
    box.evaluate("area => { area.scrollTop = area.scrollHeight; }")
    page.wait_for_timeout(300)
    seen = page.evaluate("""() => {
      const area = document.querySelector('textarea[name=text]');
      const copy = area.previousElementSibling;
      const a = getComputedStyle(area), c = getComputedStyle(copy);
      const same = ['fontFamily', 'fontSize', 'lineHeight', 'paddingLeft', 'paddingTop',
                    'borderLeftWidth', 'whiteSpace', 'overflowWrap'].filter(n => a[n] !== c[n]);
      return {text: copy.textContent.replace(/ $/, '') === area.value, same,
              width: [area.clientWidth, copy.clientWidth],
              height: [area.scrollHeight, copy.scrollHeight],
              top: [area.scrollTop, copy.scrollTop],
              tags: copy.querySelectorAll('.k-tag').length,
              attrs: copy.querySelectorAll('.k-attr').length,
              letters: getComputedStyle(area).webkitTextFillColor,
              shown: ['.k-tag', '.k-attr', '.k-value'].map((kind) => copy.querySelector(kind))
                .map((span) => span && getComputedStyle(span).color),
              ink: c.color};
    }""")
    check("PRESS-0261: the copy holds the box's text, coloured, as he types",
          seen["text"] and seen["tags"] > 4 and seen["attrs"] > 0, str(seen))
    check("PRESS-0261: the copy wraps and scrolls with the box",
          not seen["same"] and seen["width"][0] == seen["width"][1]
          and seen["height"][0] == seen["height"][1] and seen["top"][0] == seen["top"][1] > 0,
          str(seen))
    check("PRESS-0261: the box's own letters are transparent over the copy",
          seen["letters"] == "rgba(0, 0, 0, 0)", seen["letters"])
    check("PRESS-0283: tags, names and values each show their own colour, none the ink",
          None not in seen["shown"] and len({*seen["shown"], seen["ink"]}) == 4,
          f"{seen['shown']} ink={seen['ink']}")


def true_colours_kept(page, origin: str) -> None:
    """PRESS-0263: the switch's change is sent, and the next page starts with
    it and with the preview undimmed."""
    address = f"{origin}/page?kind=pages&name=visual"
    page.goto(address, wait_until="networkidle")
    flip = """on => {
      const box = document.querySelector('input[data-true-colours]');
      box.checked = on;
      box.dispatchEvent(new Event('change', {bubbles: true}));
    }"""
    with page.expect_response(lambda r: r.url.endswith("/true-colours")) as sent:
        page.evaluate(flip, True)
    page.goto(address, wait_until="networkidle")
    seen = page.evaluate("""() => [
      document.querySelector('input[data-true-colours]').checked,
      document.getElementById('preview').classList.contains('undimmed')]""")
    with page.expect_response(lambda r: r.url.endswith("/true-colours")):
        page.evaluate(flip, False)
    check("PRESS-0263: the true-colours switch is kept, and the preview starts undimmed",
          sent.value.status == 204 and seen == [True, True], f"{sent.value.status} {seen}")


def _column_page(*columns: str, after: str) -> str:
    text = "<!-- pressless:text --><p>{}</p><!-- /pressless:text -->".format
    held = ('<!-- pressless:columns --><div class="pressless-columns">' + "".join(
        f'<!-- pressless:column --><div class="pressless-column">{text(words)}</div>'
        "<!-- /pressless:column -->" for words in columns) + "</div><!-- /pressless:columns -->")
    return VISUAL_PAGE.replace(VISUAL_PAGE[VISUAL_PAGE.index("<!-- pressless:heading"):
                                          VISUAL_PAGE.index("<!-- /pressless:page")],
                               held + "\n" + text(after) + "\n")


def move_between_columns(page, origin: str, folder: Path) -> None:
    """PRESS-0264: the Move to list, in the frame at once and in the file."""
    store.write_html(folder, store.PAGES_FOLDER, "split", _column_page("Left", "Right",
                                                                       after="Loose"))
    waiting = store.html_path_for(folder, store.PAGES_FOLDER, "split", waiting=True)

    def layout() -> list:
        """The waiting copy's top-level kinds, and each column's words."""
        read = blocks.read("split", store.read_html(waiting))
        return [[[c.fields["html"] for c in part] for part in s.parts] if s.parts
                else s.fields.get("html") for s in read.sections]

    def move(words: str, choice: str) -> list[str]:
        page.frame_locator("#preview").locator("p", has_text=words).click()
        offered = page.locator("#move-to option").all_text_contents()
        if choice:
            page.select_option("#move-to", label=choice)
            page.locator("[data-act=move-to]").click()
            page.wait_for_timeout(1600)
            page.wait_for_function("document.getElementById('save-status').textContent "
                                   "!== 'Saving'", timeout=5000)
            page.wait_for_timeout(800)
        return offered

    page.goto(f"{origin}/page?kind=pages&name=split&view=visual", wait_until="networkidle")
    offered = move("Right", "Column 1")
    moved = page.evaluate("""() => [...document.getElementById('preview').contentDocument
      .querySelectorAll('.pressless-column')].map(c => c.textContent)""")
    check("PRESS-0264: a section in a column is offered the other columns and below them",
          offered == ["Column 1", "Below the columns"], str(offered))
    check("PRESS-0264: Move to moves it to another column, on the page and in the file",
          moved == ["LeftRight", ""] and layout() == [[["Left", "Right"], []], "Loose"],
          f"{moved} {layout()}")
    move("Right", "Below the columns")
    check("PRESS-0264: Below the columns takes it out, just under them",
          layout() == [[["Left"], []], "Right", "Loose"], str(layout()))
    nowhere = move("Loose", "")
    disabled = page.locator("[data-act=move-to]").is_disabled()
    offered = move("Right", "Column 2")
    check("PRESS-0264: a section under the columns moves back in; one further down cannot",
          nowhere == ["No other place"] and disabled
          and offered == ["Column 1", "Column 2"]
          and layout() == [[["Left"], ["Right"]], "Loose"], f"{nowhere} {offered} {layout()}")


def drag_sections(page, origin: str, folder: Path) -> None:
    """PRESS-0265: the handle drags the picked section; the line shows where."""
    store.write_html(folder, store.PAGES_FOLDER, "dragged", _column_page("Left", "Right",
                                                                         after="Loose"))
    waiting = store.html_path_for(folder, store.PAGES_FOLDER, "dragged", waiting=True)
    frame = page.frame_locator("#preview")

    def layout() -> list:
        read = blocks.read("dragged", store.read_html(waiting))
        return [[[c.fields["html"] for c in part] for part in s.parts] if s.parts
                else s.fields.get("html") for s in read.sections]

    def drag(words: str, onto: str) -> bool:
        """Drag `words` onto the upper half of `onto`; whether the line showed."""
        frame.locator("p", has_text=words).click()
        grip = page.locator("#drag-handle").bounding_box()
        outer = page.locator("#preview").bounding_box()
        target = frame.locator("p", has_text=onto).bounding_box()
        page.mouse.move(grip["x"] + grip["width"] / 2, grip["y"] + grip["height"] / 2)
        page.mouse.down()
        page.mouse.move(target["x"] + 5, target["y"] + 3, steps=8)
        shown = page.locator("#drop-line").is_visible()
        page.mouse.up()
        page.wait_for_timeout(1600)
        page.wait_for_function("document.getElementById('save-status').textContent "
                               "!== 'Saving'", timeout=5000)
        page.wait_for_timeout(800)
        return shown and outer is not None

    page.goto(f"{origin}/page?kind=pages&name=dragged&view=visual", wait_until="networkidle")
    handle_hidden = page.locator("#drag-handle").is_hidden()
    shown = drag("Loose", "Right")
    check("PRESS-0265: dragged from the page into a column, with a line showing where",
          handle_hidden and shown and layout() == [[["Left"], ["Loose", "Right"]]],
          f"hidden first={handle_hidden} line={shown} {layout()}")
    shown = drag("Right", "Left")
    check("PRESS-0265: dragged from one column to another",
          shown and layout() == [[["Right", "Left"], ["Loose"]]], f"line={shown} {layout()}")


# PRESS-0217: every piece, a script piece that would set the title if it ran,
# a style piece (PRESS-0273) colouring the page's paragraphs, and enough
# page below them that back to top has somewhere to come back from.
_FORMS = ROOT / "tests" / "features" / "blocks" / "forms"
PIECES_PAGE = (
    "<!doctype html><html><head><title>Pieces</title></head><body>\n"
    "<!-- HEADER:START -->\n<!-- HEADER:END -->\n<main><!-- pressless:page -->\n"
    + "\n".join((_FORMS / f"{kind}-1.html").read_text(encoding="utf-8").strip()
                for kind in ("slideshow", "questions", "enlarge", "countdown"))
    + "\n<!-- pressless:script --><script>document.title = 'RAN';</script>"
    "<!-- /pressless:script -->\n"
    "<!-- pressless:style --><style>main p { color: rgb(1, 2, 3); }</style>"
    "<!-- /pressless:style -->\n"
    + "<!-- pressless:text --><p>Further down.</p><!-- /pressless:text -->\n" * 60
    + (_FORMS / "top-1.html").read_text(encoding="utf-8").strip()
    + "\n<!-- /pressless:page --></main>\n<!-- FOOTER:START -->\n<!-- FOOTER:END -->\n"
    "</body></html>\n").replace("2026-12-25T18:00", "2099-12-25T18:00").replace(
        "2026-12-25 18:00", "2099-12-25 18:00")


def pieces(page, origin: str, folder: Path) -> None:
    """PRESS-0217 s10: what no test without a browser reaches."""
    store.write_html(folder, store.PAGES_FOLDER, "pieces", PIECES_PAGE)
    waiting = store.html_path_for(folder, store.PAGES_FOLDER, "pieces", waiting=True)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    # ---- the editor: fallbacks, and the script shown as its code, inert ----
    page.goto(f"{origin}/page?kind=pages&name=pieces", wait_until="networkidle")
    frame = page.frame_locator("#preview")
    title = page.evaluate("document.getElementById('preview').contentDocument.title")
    shown = frame.locator(".pressless-slideshow > *:visible").count()
    answers = frame.locator(".pressless-questions dd:visible").count()
    check("PRESS-0217 INV-2/INV-4: in the editor nothing runs and every fallback shows",
          title == "Pieces" and shown == 2 and answers == 2
          and frame.locator(".pressless-slideshow-turn").count() == 0,
          f"title={title!r} slides={shown} answers={answers}")
    code = frame.locator("script[data-pressless-code]")
    box = code.bounding_box() if code.count() else None
    if box:
        code.click()
    picked = page.locator("#picked").text_content()
    check("PRESS-0217 s4.2: a script piece shows as its code and is picked by a click",
          bool(box) and box["height"] > 0 and picked == "Changing: Your own script"
          and "RAN" in (page.locator("[data-field=code]:visible").input_value() or ""),
          f"box={box} picked={picked!r}")
    sheet = frame.locator("style[data-pressless-code]")
    box = sheet.bounding_box() if sheet.count() else None
    if box:
        sheet.click()
    picked = page.locator("#picked").text_content()
    applied = frame.locator("main p").last.evaluate("p => getComputedStyle(p).color")
    leaked = page.evaluate("[...document.querySelectorAll('*')].some("
                           "(at) => getComputedStyle(at).color === 'rgb(1, 2, 3)')")
    check("PRESS-0273: a style piece shows as its code, is picked by a click, and its CSS "
          "styles the preview alone",
          bool(box) and box["height"] > 0 and picked == "Changing: Your own CSS"
          and applied == "rgb(1, 2, 3)" and not leaked,
          f"box={box} picked={picked!r} applied={applied} leaked={leaked}")
    page.select_option("#add-kind", "countdown")
    page.locator("[data-act=add]").click()
    page.locator("[data-field=label]:visible").fill("Until then")
    page.wait_for_timeout(1600)
    page.wait_for_function("document.getElementById('save-status').textContent !== "
                           "'Saving'", timeout=5000)
    page.wait_for_timeout(800)
    read = blocks.read("pieces", store.read_html(waiting)) if waiting.is_file() else None
    added = [s.fields for s in (read.sections if read else ()) if s.kind == "countdown"]
    check("PRESS-0217 s4.1: a countdown is added from the panel, a week ahead",
          len(added) == 2 and added[1]["label"] == "Until then"
          and blocks._is_when(added[1]["to"]), str(added))

    def questions() -> list[str]:
        read = blocks.read("pieces", store.read_html(waiting))
        held = next(s for s in read.sections if s.kind == "questions")
        return [asked[0].fields["html"] for asked in held.parts]

    def settle() -> None:
        page.wait_for_timeout(1600)
        page.wait_for_function("document.getElementById('save-status').textContent !== "
                               "'Saving'", timeout=5000)
        page.wait_for_timeout(800)

    # A click on a question's dt, outside its words, picks the whole piece.
    frame.locator(".pressless-questions dt").first.dispatch_event("click")
    page.locator("[data-act=add-question]").click()
    settle()
    grown = questions()
    frame.locator(".pressless-questions dt p").nth(2).click()
    up = page.locator("[data-act=up]").is_disabled()
    page.locator("[data-act=remove]").click()
    settle()
    check("PRESS-0217 s4.1: a question is added, and removing its words removes it",
          grown == ["Why?", "When?", ""] and up and questions() == ["Why?", "When?"],
          f"after adding={grown} up disabled={up} after removing={questions()}")

    # ---- the published site: each piece behaves -----------------------------
    site = folder.parent / "pieces-site"
    builder.build(folder, settings.load(folder), site)
    # Served over http as GitHub Pages serves it, so a browser on another
    # machine reaches it through the same tunnel as the Face.
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *args: None
    hosted = ThreadingHTTPServer(("127.0.0.1", OPTIONS.site_port), handler)
    threading.Thread(target=hosted.serve_forever, daemon=True).start()
    try:
        page.goto(f"http://127.0.0.1:{hosted.server_port}/pages/pieces.html",
                  wait_until="load")
        _published_pieces(page, errors)
    finally:
        hosted.shutdown()
        hosted.server_close()


def _published_pieces(page, errors: list[str]) -> None:
    """PRESS-0217 s4.3 and s4.4, on the built site."""
    page.wait_for_timeout(1300)
    slides = page.locator(".pressless-slideshow > *:visible").count()
    page.locator(".pressless-slideshow-turn button").last.click()
    second = page.locator(".pressless-slideshow > *:visible figcaption").count()
    check("PRESS-0217 s4.3: the slideshow shows one picture and turns to the next",
          slides == 1 and second == 1, f"visible={slides} second has caption={second}")
    hidden = page.locator(".pressless-questions dd:visible").count()
    page.locator(".pressless-questions dt").first.click()
    opened = page.locator(".pressless-questions dd:visible").count()
    check("PRESS-0217 s4.3: the questions start folded and open by their question",
          hidden == 0 and opened == 1, f"before={hidden} after={opened}")
    page.locator(".pressless-enlarge img").click()
    big = page.locator("dialog.pressless-enlarged[open] img").count()
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)  # the close event is a task of its own
    gone = page.locator("dialog.pressless-enlarged").count()
    check("PRESS-0217 s4.3: the picture enlarges on a click, and Escape closes it",
          big == 1 and gone == 0, f"open={big} after Escape={gone}")
    told = page.locator(".pressless-countdown time").first.text_content() or ""
    check("PRESS-0217 s4.3: the countdown shows the time left in words",
          "2099" not in told and "day" in told, told)
    page.locator(".pressless-top").scroll_into_view_if_needed()
    page.locator(".pressless-top").click()
    page.wait_for_function("window.scrollY === 0", timeout=3000)
    ran = page.title()
    check("PRESS-0217 s4.4: back to top returns to the top; the writer's script runs",
          ran == "RAN", f"title={ran!r}")
    check("PRESS-0217: no script error in the editor or on the site", not errors, str(errors))


def furniture_views(page, origin: str, folder: Path) -> None:
    """PRESS-0216: the header in the visual view, and the menu view."""
    header = ('<header><!-- pressless:page -->\n<!-- pressless:text --><p>Header words</p>'
              "<!-- /pressless:text -->\n<!-- /pressless:page --></header>\n")
    store.write_html(folder, store.FURNITURE_FOLDER, "header", header)
    store.write_html(folder, store.FURNITURE_FOLDER, "navigation",
                     '<nav>\n  <a href="{{UP}}index.html" data-nav="Home">Home</a>\n'
                     '  <a href="{{UP}}pages/visual.html" data-nav="visual">Visual</a>\n</nav>')

    def saved() -> None:
        page.wait_for_timeout(1600)
        page.wait_for_function("document.getElementById('save-status').textContent !== "
                               "'Saving'", timeout=5000)

    def waiting(name: str) -> str:
        return store.read_html(store.html_path_for(folder, store.FURNITURE_FOLDER, name,
                                                   waiting=True))

    page.goto(f"{origin}/page?kind=furniture&name=header&view=visual&show=visual",
              wait_until="networkidle")
    page.frame_locator("#preview").locator("p", has_text="Header words").click()
    page.keyboard.press("End")
    page.keyboard.type(" more")
    saved()
    check("PRESS-0216: the header is typed in on the page and saved as its section",
          "<p>Header words more</p>" in waiting("header"), waiting("header"))

    page.goto(f"{origin}/page?kind=furniture&name=navigation&view=visual",
              wait_until="networkidle")
    rows = page.locator("#menu-links li")
    rows.nth(0).locator("[data-link=words]").fill("Start")
    rows.nth(0).locator("[data-act=down]").click()
    page.locator("[data-act=add-link]").click()
    rows.nth(2).locator("[data-link=words]").fill("Shop")
    rows.nth(2).locator("[data-link=href]").fill("https://example.org/")
    saved()
    check("PRESS-0216: a menu link is renamed, moved down and a new one added",
          waiting("navigation") == (
              '<nav>\n  <a href="{{UP}}pages/visual.html" data-nav="visual">Visual</a>\n'
              '  <a href="{{UP}}index.html" data-nav="Home">Start</a>\n'
              '  <a href="https://example.org/">Shop</a>\n</nav>'), waiting("navigation"))


def google_blocked(page, origin: str, folder: Path) -> tuple[bool, str]:
    """A PREVIEW page carrying Google's script and a player, loaded as the frame
    loads it, so FILES_POLICY is the policy under test (not the editor page's
    frames-only policy). PRESS-0012 s10 row: "the policies block Google's
    script, the players and a followed outside link in a browser". Since
    PRESS-0268 the page's own scripts are blocked too: a same-origin file, one
    under /preview/assets/ (the live site's copied assets), and an inline one."""
    from pressless import editor as ed
    from pressless import paths

    preview = folder / ed.PREVIEW_FOLDER
    preview.mkdir(parents=True, exist_ok=True)
    (preview / "policycheck.html").write_text(
        "<!doctype html><html><head>"
        "<script src='https://www.googletagmanager.com/gtag/js?id=G-TEST'></script>"
        "</head><body><p>probe</p>"
        "<iframe src='https://www.youtube.com/embed/dQw4w9WgXcQ'></iframe>"
        "<script src='ran.js'></script>"
        "<script src='/preview/assets/ran-assets.js'></script>"
        "<script>window.__inline = true;</script>"
        "</body></html>", encoding="utf-8")
    (preview / "ran.js").write_text("window.__ran = true;", encoding="utf-8")
    assets = folder / paths.PREVIEW_ASSETS
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "ran-assets.js").write_text("window.__assets = true;", encoding="utf-8")

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
    ran = page.evaluate("() => [window.__ran === true, window.__assets === true,"
                        " window.__inline === true]")
    # The Builder refuses a preview folder holding files it did not make, so
    # the probe pages go before the next preview is built.
    (preview / "policycheck.html").unlink()
    (preview / "ran.js").unlink()
    (assets / "ran-assets.js").unlink()
    ok = bool(google) and bool(player) and ran == [False, False, False]
    return ok, (f"csp={csp!r} google_blocked={bool(google)} "
                f"player_blocked={bool(player)} ran (own, assets, inline)={ran} "
                f"violations={violations}")


def _snip(text: str, needle: str) -> str:
    i = text.find(needle)
    return text[max(0, i - 20):i + 120] if i >= 0 else text[:140]


if __name__ == "__main__":
    raise SystemExit(main())
