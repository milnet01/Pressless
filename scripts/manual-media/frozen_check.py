"""Drive the frozen program's manual offline: PRESS-0219 § 7's by-hand check
on Linux. `frozen-check.sh` runs this. It prints what it saw and judges
nothing: a person reads the lines against § 7.
"""
import time

import kit
from playwright.sync_api import sync_playwright

LINK = kit.WORK / "frozen-link.txt"
BROKEN_PICTURES = """async () => {
  const bad = [];
  for (const i of document.querySelectorAll('img')) {
    i.loading = 'eager';
    try { await i.decode() } catch (e) { bad.push(i.src) }
  }
  return bad;
}"""
SHOWN_TASKS = """() => [...document.querySelectorAll('section.manual-task')]
  .filter(s => !s.hidden).map(s => s.id)"""
# Per video: its file, whether it played, the caption track's mode, how many
# captions it holds, and the one showing.
PLAY_VIDEOS = """async () => {
  const out = [];
  for (const v of document.querySelectorAll('video')) {
    v.muted = true;
    await v.play();
    await new Promise(r => setTimeout(r, 1200));
    const t = v.textTracks[0];
    out.push([v.getAttribute('src').split('/').pop(), v.currentTime > 0.5, t.mode,
              t.cues ? t.cues.length : 0,
              t.activeCues && t.activeCues[0] ? t.activeCues[0].text : null]);
    v.pause();
  }
  return out;
}"""
# The size chosen, a paragraph's font size, and whether the page still fits its width.
TEXT_SIZE = """() => [document.documentElement.dataset.size,
  getComputedStyle(document.querySelector('main p')).fontSize,
  document.documentElement.scrollWidth <= innerWidth]"""


def main():
    for _ in range(60):
        if LINK.exists():
            break
        time.sleep(0.5)
    link = LINK.read_text().strip()
    base = kit.origin(link)
    outside = []

    def note(request):
        if not request.url.startswith((base, "data:", "blob:")):
            outside.append(request.url)

    with sync_playwright() as pw:
        # The network is cut by a user namespace, where Chrome's sandbox cannot start.
        browser = kit.chrome(pw, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 800},
                                      color_scheme="light")
        p = context.new_page()
        p.on("request", note)
        p.goto(link)
        p.wait_for_timeout(800)
        print("first screen:", p.url.replace(base, "").split("?")[0], "|",
              p.inner_text("main h1"))
        for path in ("/setup", "/sites", "/about"):
            p.goto(base + path)
            p.wait_for_timeout(400)
            heading = p.inner_text("main h1") if p.locator("main h1").count() else "?"
            p.click("header.bar a[href='/manual']")
            p.wait_for_timeout(500)
            print(f"Help from {path} ({heading}) ->", p.url.replace(base, ""),
                  "| tasks:", p.locator("section.manual-task").count())
        print("pictures that fail:", p.evaluate(BROKEN_PICTURES),
              "of", p.locator("main img").count())
        p.fill("#manual-search", "undo publish")
        p.wait_for_timeout(300)
        print("search 'undo publish':", p.inner_text("#manual-found"),
              "| shown:", p.evaluate(SHOWN_TASKS))
        p.fill("#manual-search", "")
        p.wait_for_timeout(200)
        print("videos:", p.evaluate(PLAY_VIDEOS))
        p.click("details.more summary")
        p.locator("details.more select").nth(1).select_option(label="Largest")
        p.wait_for_timeout(1200)
        print("text size:", p.evaluate(TEXT_SIZE))
        p.locator("#publishing").scroll_into_view_if_needed()
        p.screenshot(path=str(kit.WORK / "frozen-largest.png"))
        print("picture at the largest size:", kit.WORK / "frozen-largest.png")
        browser.close()
    print("requests outside the app:", outside)


if __name__ == "__main__":
    main()
