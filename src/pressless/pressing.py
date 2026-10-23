"""The running press and how it ended, known to Pressless itself (PRESS-0235).

A press is Press to site in either editor, or Undo the last press. It still runs
inside the request that started it; this module only records it beside that
request, so any page opened during it can say it is running, and then how it
ended (docs/specs/PRESS-0235-press-status.md § 4).
"""
from __future__ import annotations

import html
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass

from pressless import usage
from pressless.face import Face, Reply, Request
from pressless.words import say

PUBLISH, UNDO = "publish", "undo"

# Every press-row line has one home, the words table's `script.press.` keys,
# which Python and the scripts both read (§ 4.3, PRESS-0242).
_RUNNING = {PUBLISH: "script.press.publishing", UNDO: "script.press.undoing"}
_FAILED = {PUBLISH: "script.press.not_published", UNDO: "script.press.not_undone"}


@dataclass(frozen=True)
class Outcome:
    """How a press ended: the line's words, and the failure's HTML or None."""
    said: str
    failure: str | None = None


# One record per process. _LOCK is held only to read or change it, never for a
# press, so `state` answers while one runs (§ 4.1).
_LOCK = threading.Lock()
_running: str | None = None
_outcome: Outcome | None = None


def start(kind: str) -> bool:
    """Mark a press of `kind` running. False where one already is."""
    global _running, _outcome
    with _LOCK:
        if _running is not None:
            return False
        _running, _outcome = kind, None
        return True


def end(outcome: Outcome) -> None:
    """The press has ended, with `outcome`."""
    global _running, _outcome
    with _LOCK:
        _running, _outcome = None, outcome


def forget() -> None:
    """An ended outcome stops being shown (§ 3 decision 6); each screen whose
    action ends it calls this. Nothing while a press runs, since every
    publish saves first."""
    global _outcome
    with _LOCK:
        if _running is None:
            _outcome = None


def state() -> dict:
    """§ 4.2's JSON."""
    with _LOCK:
        if _running is not None:
            return {"running": True, "kind": _running, "said": say(_RUNNING[_running]),
                    "failure": None}
        if _outcome is not None:
            return {"running": False, "kind": None, "said": _outcome.said,
                    "failure": _outcome.failure}
        return {"running": False, "kind": None, "said": "", "failure": None}


def run(kind: str, busy: Callable[[str], Reply],
        press: Callable[[Callable[[Outcome], None]], Reply]) -> Reply:
    """§ 4.4: refuse at once where a press runs, answering `busy(running words)`;
    otherwise run `press`, which reports its outcome through the callable it is
    handed. The record ends in a `finally`, so an unforeseen exception still ends
    it, with the failed words. Only a press that started ends it."""
    if not start(kind):
        return busy(state()["said"])
    ended = [Outcome(say(_FAILED[kind]))]
    try:
        return press(lambda outcome: ended.append(outcome))
    finally:
        end(ended[-1])
        done = ended[-1].said in (say("script.press.published"), say("script.press.undone"))
        usage.report("press", kind=kind, ended="done" if done else "failed")


def register(face: Face) -> None:
    """Add GET /press and POST /press/forget. Neither takes editor.LOCK, so
    both answer during a press."""
    face.add_page("GET", "/press", _press)
    face.add_page("POST", "/press/forget", _forget)


def _press(request: Request) -> Reply:
    return Reply(json.dumps(state()).encode("utf-8"), "application/json")


def _forget(request: Request) -> Reply:
    forget()
    return Reply(b"", "text/plain; charset=utf-8", status=204)


def shown(standing: str) -> tuple[str, bool, str | None]:
    """A page's press-row line rendered now (§ 4.5): its words (the running
    words, the ended outcome's, else `standing`), whether a press runs, and the
    outcome's failure."""
    now = state()
    return now["said"] or standing, now["running"], now["failure"]


def holding() -> str | None:
    """An editor opened during a press (§ 4.5): a page holding the running words,
    which reloads itself when the press ends. None where no press runs."""
    now = state()
    if not now["running"]:
        return None
    return (f'<p class="nav"><a href="/">{say("face.your_writing")}</a></p>'
            '<p id="publish-status" class="press-status" role="status" data-press="hold">'
            f"{html.escape(now['said'])}</p><script>{SCRIPT}</script>")


# Every page with a press row carries this, ahead of its own script. The first
# copy on a page makes the one asker; later copies find it. It asks GET /press
# every two seconds while a press runs, with Press to site and Undo disabled,
# then writes how it ended (§ 4.5). A holding page reloads instead.
SCRIPT = """
window.presslessPress = window.presslessPress || (() => {
  const line = document.getElementById("publish-status") ||
    document.getElementById("undo-status");
  const failure = document.getElementById("failure") ||
    document.getElementById("undo-result");
  const buttons = () =>
    document.querySelectorAll("button[data-editor=publish], button[data-undo]");
  let standing = () => "";
  let asking = false;
  const ask = async () => {
    if (asking || !line) return;
    asking = true;
    buttons().forEach((button) => { button.disabled = true; });
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      let now;
      try { now = await (await fetch("/press")).json(); } catch (error) { continue; }
      if (now.running) { line.textContent = now.said; continue; }
      if (line.dataset.press === "hold") { window.location.reload(); return; }
      line.textContent = now.said || standing();
      if (failure && now.failure) failure.innerHTML = now.failure;
      break;
    }
    asking = false;
    buttons().forEach((button) => { button.disabled = false; });
  };
  // PRESS-0235: a reply saying another press runs puts its words on the line
  // and asks until that press ends. True where the reply said so.
  const busy = (reply) => {
    if (!reply.busy) return false;
    if (line) line.textContent = reply.said;
    ask();
    return true;
  };
  // PRESS-0234: a press put something on the site, so View site can open it.
  const viewable = () => {
    const view = document.querySelector("button[data-view-site]");
    if (view && view.dataset.viewSite) view.disabled = false;
  };
  if (line && line.dataset.press) ask();
  return {ask, busy, viewable, asking: () => asking,
          standing: (given) => { standing = given; }};
})();
"""
