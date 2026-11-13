"""Take the manual's pictures from the throwaway instance (PRESS-0219 § 4.6).

    python3 scripts/manual-media/shots.py            # every picture
    python3 scripts/manual-media/shots.py look menu  # only these

They land in `kit.WORK/out`. Look at each, then copy the ones wanted into
`src/pressless/manual_files/media/`. The AI helper screen shows this
machine's paths, so its picture is cut to the heading and the switch.
"""
import sys

import kit
from playwright.sync_api import sync_playwright

OUT = kit.WORK / "out"
ONLY = set(sys.argv[1:])
W, H = 1280, 800

# The bar sticks to the top of the window, so a full-page picture would
# draw it over whatever has scrolled beneath it.
UNSTICK_BAR = """
addEventListener('DOMContentLoaded', () => {
  const s = document.createElement('style');
  s.textContent = 'header.bar{position:static!important}';
  document.head.append(s);
});
"""
BOX = """([s]) => {
  const r = document.querySelector(s).getBoundingClientRect();
  return [r.x + scrollX, r.y + scrollY, r.width, r.height];
}"""
OPEN_LISTS = """(open) => document.querySelectorAll('#listing details')
  .forEach((d, i) => d.open = open.includes(i))"""
SHORT_MARKS_BOX = """() => {
  document.getElementById('cheat-sheet').open = true;
  const t = document.querySelector('textarea[name=body]');
  t.style.height = '110px';
  t.style.minHeight = '0';
}"""
# A <select> does not draw open in a headless browser; a sized one shows its choices.
SHOW_CHOICES = """() => {
  const s = document.querySelector('#panel select');
  s.size = s.options.length;
  s.style.height = 'auto';
}"""


def want(name):
    return not ONLY or name in ONLY


def union(p, *selectors, pad=14):
    """The rectangle around every selector's first match, as a clip."""
    boxes = []
    for selector in selectors:
        p.locator(selector).first.scroll_into_view_if_needed()
        boxes.append(p.evaluate(BOX, [selector]))
    left = max(0, min(b[0] for b in boxes) - pad)
    top = max(0, min(b[1] for b in boxes) - pad)
    right = min(W, max(b[0] + b[2] for b in boxes) + pad)
    bottom = max(b[1] + b[3] for b in boxes) + pad
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def snap(p, name, clip=None, view=False):
    """Save `name`.png: the window as it stands, or a clip of the whole page."""
    if not want(name):
        return
    p.wait_for_timeout(500)
    if view:
        p.screenshot(path=str(OUT / f"{name}.png"))
    else:
        p.screenshot(path=str(OUT / f"{name}.png"), full_page=True, clip=clip)
    print("shot", name)


def open_page(browser, mode):
    """A page signed in to a freshly started instance, and its address."""
    link = kit.start(mode)
    context = browser.new_context(viewport={"width": W, "height": H}, color_scheme="light")
    context.add_init_script(UNSTICK_BAR)
    p = context.new_page()
    p.goto(link)
    p.wait_for_timeout(600)
    return p, kit.origin(link)


def home(p):
    snap(p, "help-link", union(p, "header.bar", pad=0))
    snap(p, "finish-setting-up", union(p, "#checklist"))
    p.evaluate(OPEN_LISTS, [0, 1, 2])
    snap(p, "your-writing", union(p, "#listing"))
    p.evaluate(OPEN_LISTS, [2])
    p.fill("form[action='/page/new'] input", "Contact")
    third = "#listing details:nth-of-type(3)"
    snap(p, "new-page", union(p, third) if p.locator(third).count() else None)


def entry_editor(p, go):
    go("/edit?slug=rain-on-the-quay")
    p.frames[1].click("text=Something about rain")
    p.wait_for_timeout(400)
    snap(p, "style-buttons", union(
        p, "#panel button[data-act=bold]", "#panel button[data-act=colour]",
        "label:has(#picked-colour)", "#panel button[data-colour=muted]", pad=24))
    p.select_option("#add-kind", "photo")
    p.click("button[data-act=add]")
    p.wait_for_timeout(500)
    p.set_input_files("#panel-photograph-file", str(kit.PHOTOGRAPH))
    p.wait_for_timeout(2500)
    p.fill("#panel input[data-field=caption]", "The harbour at dawn")
    p.wait_for_timeout(2500)
    p.locator("#panel").scroll_into_view_if_needed()
    p.mouse.wheel(0, 120)
    snap(p, "photograph-part", view=True)
    go("/edit?slug=rain-on-the-quay&view=marks")
    p.evaluate(SHORT_MARKS_BOX)
    snap(p, "marks", union(p, "#marks-view"))
    go("/edit?slug=rain-on-the-quay")
    p.click("button[data-editor=publish]")
    p.wait_for_selector("dialog[open] >> text=Publish now")
    snap(p, "publish-plan", union(p, "dialog[open]", pad=0))
    p.keyboard.press("Escape")


def page_editor(p, go):
    go("/page?kind=pages&name=index")
    p.locator("form#editor").scroll_into_view_if_needed()
    snap(p, "page-editor", view=True)
    p.evaluate(SHOW_CHOICES)
    snap(p, "add-section", union(p, "#panel select", pad=30))
    go("/page?kind=furniture&name=navigation")
    p.locator("form#editor").scroll_into_view_if_needed()
    snap(p, "menu", view=True)


def other_screens(p, go):
    go("/look")
    p.locator("form#look").scroll_into_view_if_needed()
    p.mouse.wheel(0, -60)
    snap(p, "look", view=True)
    go("/setup")
    snap(p, "settings", view=True)
    go("/domain")
    snap(p, "own-domain", union(p, "main h1", "main form"))
    go("/visitors")
    snap(p, "who-is-reading", view=True)
    go("/sites")
    snap(p, "sites", union(p, "main h1", "main ul.sites", "main form"))
    p.click("text=Move Pressless to a new computer")
    p.wait_for_timeout(400)
    snap(p, "move-computer", union(p, "dialog#move-wizard", pad=0))
    go("/assistant/setup")
    snap(p, "ai-helper", union(p, "main h1", "main form.switch-row"))
    go("/")
    p.click("details.more summary")
    p.wait_for_timeout(300)
    snap(p, "more", union(p, "header.bar", "details.more div"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = kit.chrome(pw)
        if want("setup-welcome"):
            p, _ = open_page(browser, "fresh")
            snap(p, "setup-welcome", union(p, "header.bar", "main form"))
            p.context.close()

        p, base = open_page(browser, "site")

        def go(path):
            p.goto(base + path)
            p.wait_for_timeout(1300)

        home(p)
        go("/")
        p.fill("input[name=title]", "Low tide")
        snap(p, "new-entry", union(p, "#listing form:has(input[name=title])"))
        entry_editor(p, go)
        page_editor(p, go)
        other_screens(p, go)
        browser.close()


if __name__ == "__main__":
    main()
