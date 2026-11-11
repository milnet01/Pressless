"""The manual inside the app, at /manual (PRESS-0219).

The words are one text file per language in `manual_files`, and the pictures
and videos a folder beside it shared by every language, so a translation is
added files rather than edited code (§ 4.1). The text format is § 4.2's and
nothing more: a line's start decides what it is, every word is escaped, and a
line that is not a construct is paragraph words. The search is the page's own
script hiding tasks as he types (§ 4.3); the Face is not asked.
"""
from __future__ import annotations

import html
import importlib.resources
import re
from pathlib import Path

from pressless.face import SENTENCES, Face, Request, Sentence, Site, within
from pressless.words import say

ADDRESS = "/manual"
MEDIA = ADDRESS + "/media/"
# Not `manual`, which would shadow this module on import (§ 4.1). Read through
# importlib.resources so a frozen bundle finds it as the source tree does.
FOLDER = Path(str(importlib.resources.files("pressless") / "manual_files"))
LANGUAGE = "en"   # PRESS-0241 chooses; until then the manual is English

_TASK = re.compile(r"== ([a-z0-9-]+) \| (\S.*)")
_STEP = re.compile(r"\d+\.\s+(.*)")
_PICTURE = re.compile(r"picture ([a-z0-9-]+\.png) \|(.*)")
_VIDEO = re.compile(r"video ([a-z0-9-]+)\.webm \|(.*)")


class ManualMissing(Exception):
    """The manual's text could not be read: a broken bundle (§ 6)."""


SENTENCES[ManualMissing] = Sentence(
    "failure.manual.ManualMissing.what",
    Site.UNCHANGED,
    "failure.manual.ManualMissing.next",
)


def _e(text: str) -> str:
    return html.escape(text.strip(), quote=True)


def _picture(name: str, alt: str) -> str:
    return f'<img src="{MEDIA}{name}" alt="{_e(alt)}" loading="lazy">'


def _video(stem: str, label: str) -> str:
    return (f'<video controls preload="none" src="{MEDIA}{stem}.webm" aria-label="{_e(label)}">'
            f'<track kind="captions" src="{MEDIA}{stem}.{LANGUAGE}.vtt" srclang="{LANGUAGE}" '
            f'label="{_e(say("manual.captions"))}" default></video>')


def render(text: str) -> str:
    """The manual's tasks as HTML, from the text of one language's file."""
    out: list[str] = []
    words: list[str] = []      # the paragraph being gathered
    steps: list[str] = []      # the run of steps being gathered
    counted = 0                # steps already shown in this task
    in_task = False

    def flush() -> None:
        nonlocal counted
        if words:
            out.append(f"<p>{_e(' '.join(words))}</p>")
            words.clear()
        if steps:
            start = f' start="{counted + 1}"' if counted else ""
            out.append(f"<ol{start}>" + "".join(f"<li>{_e(s)}</li>" for s in steps) + "</ol>")
            counted += len(steps)
            steps.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if (task := _TASK.fullmatch(line)):
            flush()
            out.append(("</section>" if in_task else "")
                       + f'<section id="{task.group(1)}" class="manual-task">'
                       f"<h2>{_e(task.group(2))}</h2>")
            in_task, counted = True, 0
        elif (step := _STEP.fullmatch(line)):
            if words:
                flush()
            steps.append(step.group(1))
        elif (picture := _PICTURE.fullmatch(line)):
            flush()
            out.append(_picture(*picture.groups()))
        elif (video := _VIDEO.fullmatch(line)):
            flush()
            out.append(_video(*video.groups()))
        elif not line:
            flush()
        else:
            if steps:
                flush()
            words.append(line)
    flush()
    return "".join(out) + ("</section>" if in_task else "")


_STYLE = """<style>
.manual-task img, .manual-task video { display: block; max-width: 100%; height: auto; }
.manual-task { margin-block: 2em; }
</style>"""

# INV-8: a task shows when every typed word is in its words, ignoring case.
_SCRIPT = r"""
(() => {
  const box = document.getElementById("manual-search");
  const found = document.getElementById("manual-found");
  const tasks = [...document.querySelectorAll("section.manual-task")].map(section => ({
    section,
    text: [section.textContent,
           ...[...section.querySelectorAll("img[alt], video[aria-label]")]
             .map(m => m.getAttribute("alt") ?? m.getAttribute("aria-label"))]
          .join(" ").toLowerCase(),
  }));
  box.addEventListener("input", () => {
    const wanted = box.value.toLowerCase().split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const task of tasks) {
      task.section.hidden = !wanted.every(word => task.text.includes(word));
      if (!task.section.hidden) shown += 1;
    }
    found.textContent = !wanted.length ? ""
      : shown === 0 ? say("script.manual.none")
      : shown === 1 ? say("script.manual.found_one")
      : say("script.manual.found", {count: shown});
  });
})();
"""


def _page(folder: Path):
    def page(request: Request) -> str:
        try:
            text = (folder / f"{LANGUAGE}.txt").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ManualMissing("the manual's text could not be read") from exc
        body = render(text)
        # The search box sits between the opening paragraph and the tasks.
        cut = body.find("<section")
        cut = len(body) if cut < 0 else cut
        return (f'{_STYLE}<h1>{_e(say("manual.title"))}</h1>{body[:cut]}'
                f'<input type="search" id="manual-search" aria-label="{_e(say("manual.search"))}">'
                '<p role="status" id="manual-found"></p>'
                f"{body[cut:]}<script>{_SCRIPT}</script>")
    return page


def register(face: Face, folder: Path = FOLDER) -> None:
    """Add /manual and its pictures and videos to `face`."""
    face.add_page("GET", ADDRESS, _page(folder))
    face.add_files(MEDIA, within(folder / "media"))
