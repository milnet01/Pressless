"""Record the manual's short videos from the throwaway instance, with captions
(PRESS-0219 § 4.6).

    python3 scripts/manual-media/video.py              # every video
    python3 scripts/manual-media/video.py publishing   # only these

Each lands in `kit.WORK/vid` as `<name>.webm` and `<name>.en.vtt`: silent,
with a pointer an injected script draws, and captions timed from the run.
Play each, then copy the ones wanted into `src/pressless/manual_files/media/`.
Needs `ffmpeg`. The indented lines it prints are what the screen answered,
so a clip that recorded a failure shows as one.
"""
import shutil
import subprocess
import sys
import time

import kit
from playwright.sync_api import sync_playwright

OUT = kit.WORK / "vid"
ONLY = set(sys.argv[1:])
W, H = 1280, 720

# A headless browser draws no pointer. This dot follows the mouse, and is a
# popover so that it stays above an open dialog: it is lifted again when one opens.
POINTER = """
addEventListener('DOMContentLoaded', () => {
  const d = document.createElement('div');
  d.setAttribute('popover', 'manual');
  d.style.cssText = 'position:fixed;margin:0;inset:auto;width:22px;height:22px;'
    + 'border-radius:50%;background:rgba(220,60,40,.55);border:2px solid #fff;'
    + 'box-shadow:0 0 0 1px #000;pointer-events:none;padding:0;overflow:visible;'
    + 'left:-50px;top:-50px';
  document.documentElement.append(d);
  const lift = () => {
    try { d.hidePopover(); } catch (e) {}
    try { d.showPopover(); } catch (e) {}
  };
  addEventListener('mousemove', e => {
    d.style.left = (e.clientX - 11) + 'px';
    d.style.top = (e.clientY - 11) + 'px';
    const dialog = document.querySelector('dialog[open]');
    if (!d.matches(':popover-open') || dialog && !d.dataset.up) {
      lift();
      d.dataset.up = dialog ? '1' : '';
    }
  }, true);
  document.addEventListener('mouseleave', () => { d.style.left = '-50px'; });
});
"""
PREVIEW_WORDS = "() => document.body.innerText.replace(/\\s+/g,' ').slice(0,200)"


def stamp(seconds):
    return f"{int(seconds // 60):02d}:{seconds % 60:06.3f}"


def captions(cues, end):
    """The cues as WebVTT, each shown until the next begins."""
    lines = ["WEBVTT", ""]
    for index, (began, text) in enumerate(cues):
        stop = cues[index + 1][0] if index + 1 < len(cues) else end
        lines += [f"{stamp(max(0, began))} --> {stamp(stop)}", text, ""]
    return "\n".join(lines)


def clip(browser, state, base, name, path, act):
    """Record `act` on the screen at `path` as `name`.webm, with its captions.

    `act(p, cue, to)` drives the page: `cue(text)` starts a caption, and
    `to(locator)` glides the pointer there and clicks.
    """
    if ONLY and name not in ONLY:
        return
    raw_folder = OUT / f"raw-{name}"
    shutil.rmtree(raw_folder, ignore_errors=True)
    context = browser.new_context(
        viewport={"width": W, "height": H}, color_scheme="light", storage_state=state,
        record_video_dir=str(raw_folder), record_video_size={"width": W, "height": H})
    context.add_init_script(POINTER)
    began = time.monotonic()
    p = context.new_page()
    p.goto(base + path)
    p.wait_for_timeout(1500)
    # The recording runs from the context's start; the clip starts once the screen is up.
    lead = time.monotonic() - began
    cues = []

    def cue(text):
        cues.append((time.monotonic() - began - lead, text))

    def to(locator, click=True):
        box = locator.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        p.mouse.move(x, y, steps=30)
        p.wait_for_timeout(450)
        if click:
            p.mouse.click(x, y)
            p.wait_for_timeout(350)

    p.mouse.move(W / 2, H / 2)
    act(p, cue, to)
    p.wait_for_timeout(1200)
    end = time.monotonic() - began - lead
    context.close()
    raw = next(raw_folder.glob("*.webm"))
    made = OUT / f"{name}.webm"
    subprocess.run(  # noqa: S603 -- fixed arguments, no shell
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{lead:.2f}", "-i", str(raw),  # noqa: S607
         "-t", f"{end:.2f}", "-an", "-vf", "fps=12", "-c:v", "libvpx-vp9", "-crf", "40",
         "-b:v", "0", "-row-mt", "1", str(made)], check=True)
    shutil.rmtree(raw_folder)
    (OUT / f"{name}.en.vtt").write_text(captions(cues, end))
    print("clip", name, f"{end:.1f}s", made.stat().st_size, "bytes")


def searching(p, cue, to):
    cue("Type a word in the search box.")
    to(p.locator("#manual-search"))
    p.keyboard.type("photograph", delay=160)
    p.wait_for_timeout(600)
    cue("Only the tasks holding that word stay on the page.")
    p.wait_for_timeout(3200)
    print("  found:", p.inner_text("#manual-found"))


def writing(p, cue, to):
    cue("Type the entry's name in the Title box.")
    to(p.locator("input[name=title]"))
    p.keyboard.type("Low tide", delay=150)
    p.wait_for_timeout(700)
    cue("Click New entry.")
    to(p.locator("button:has-text('New entry')"))
    p.wait_for_load_state()
    p.wait_for_timeout(2200)
    preview = p.frames[1]
    print("  new entry preview:", preview.evaluate(PREVIEW_WORDS),
          "| panel:", p.inner_text("#picked"))
    cue("Click under the title on the page, and type your words.")
    to(preview.locator(".post-body p").first)
    p.keyboard.type("The tide went out and left the boats leaning.", delay=70)
    p.wait_for_timeout(2500)
    cue("Pressless saves as you type.")
    to(p.locator("#save-status"), click=False)
    p.wait_for_timeout(2200)
    print("  status:", p.inner_text("#save-status"),
          "| body:", p.input_value("textarea[name=body]"))


def publishing(p, cue, to):
    cue("Click Press to site.")
    to(p.locator("button[data-editor=publish]"))
    p.wait_for_selector("dialog[open] >> text=Publish now")
    p.wait_for_timeout(1800)
    cue("Pressless lists what will change. Click Publish now.")
    p.wait_for_timeout(1500)
    to(p.locator("dialog[open] >> text=Publish now"))
    p.wait_for_selector("#publish-status:has-text('Published')")
    cue("Pressless says Published when it is done.")
    to(p.locator("#publish-status"), click=False)
    p.wait_for_timeout(2800)


def look(p, cue, to):
    font = p.locator("select[name=heading_font]")
    font.scroll_into_view_if_needed()
    p.wait_for_timeout(700)
    cue("Change a choice, such as the headings font.")
    to(font, click=False)
    p.wait_for_timeout(900)
    font.select_option(label="Typewriter")
    p.wait_for_timeout(1200)
    cue("The preview beside it changes at once.")
    p.wait_for_timeout(3000)
    cue("Click Save to keep it.")
    save = p.locator("form#look button:has-text('Save')")
    save.scroll_into_view_if_needed()
    p.wait_for_timeout(700)
    to(save)
    p.wait_for_timeout(2200)
    print("  look status:", p.inner_text("#look-status")[:120])


CLIPS = (
    ("searching", "/manual", searching),
    ("writing-an-entry", "/", writing),
    ("publishing", "/edit?slug=rain-on-the-quay", publishing),
    ("changing-the-look", "/look", look),
)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    link = kit.start("site")
    with sync_playwright() as pw:
        browser = kit.chrome(pw)
        # The link admits one browser: sign in once, and hand each clip its cookies.
        first = browser.new_context()
        first.new_page().goto(link)
        state = first.storage_state()
        first.close()
        for name, path, act in CLIPS:
            clip(browser, state, kit.origin(link), name, path, act)
        browser.close()


if __name__ == "__main__":
    main()
