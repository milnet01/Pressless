"""Wizards (PRESS-0220): the rare tasks of many steps, one step per screen.

The contract is docs/specs/PRESS-0212-setup-wizard.md § 4.1 and § 4.2. A
wizard is a list of steps served at one address. Each screen shows one step,
says which of how many, and offers Back and Next; Next runs the step's check
first. What was done is kept in a small progress file, so closing Pressless
halfway resumes at the step reached. That file never holds a key.

It lives in the Face (`docs/design.md` rule 1): a wizard is an order of things
happening, and only the Face knows that.
"""

from __future__ import annotations

import html
import json
import threading
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pressless import safe_write
from pressless.face import Face, Request

Answers = dict[str, str]

FOLDER = "wizards"          # inside Pressless's own folder
VERSION = 1


@dataclass(frozen=True)
class Hint:
    """A refused answer, shown beside its field."""
    field: str            # "" when the step has no field it is about
    text: str


@dataclass(frozen=True)
class Stop:
    """A failure fragment, from Face.fail, shown above the step."""
    fragment: str


@dataclass(frozen=True)
class Done:
    """The wizard is finished: show this, and forget the progress."""
    fragment: str


@dataclass(frozen=True)
class Step:
    name: str                                    # stable; the progress file names it
    title: str
    fields: tuple[str, ...]                      # the answers this step's form posts
    show: Callable[[Answers, Hint | None], str]  # the step's body, fields filled from Answers
    check: Callable[[Answers], Answers | Hint | Stop | Done] | None = None


def is_secret(name: str) -> bool:
    """A field the progress file never holds and a page never fills in."""
    return name.endswith("key")


def field(name: str, label: str, answers: Answers, hint: Hint | None,
          kind: str = "text") -> str:
    """One labelled box, filled from `answers` unless it holds a key, with its
    hint beneath when the hint is about it."""
    e = html.escape
    value = "" if is_secret(name) else f' value="{e(answers.get(name, ""), quote=True)}"'
    shown = (f'<p class="hint" id="{name}-hint">{e(hint.text)}</p>'
             if hint is not None and hint.field == name else "")
    return (f'<p><label>{e(label)} <input type="{kind}" name="{name}"{value} '
            f'autocomplete="off"></label></p>{shown}')


class Wizard:
    def __init__(self, name: str, steps: Sequence[Step], folder: Path, address: str) -> None:
        self._name = name
        self._steps = tuple(steps)
        self._folder = Path(folder)
        self._address = address
        self._lock = threading.Lock()

    @property
    def progress(self) -> Path:
        return self._folder / FOLDER / f"{self._name}.json"

    def page(self, face: Face, request: Request) -> str:
        with self._lock:
            index, answers = self._read()
            if request.method != "POST":
                return self._show(index, answers)
            posted = urllib.parse.parse_qs(request.body.decode("utf-8", "replace"),
                                           keep_blank_values=True)

            def one(name: str) -> str:
                return (posted.get(name) or [""])[0]

            step = self._steps[index]
            if one("step") != step.name:          # a stale tab, or a forged post
                return self._show(index, answers)
            if one("go") == "back":
                if index == 0:
                    return self._show(index, answers)
                return self._move(face, index - 1, index, answers)
            merged = {**answers, **{name: one(name).strip() for name in step.fields}}
            result = step.check(merged) if step.check is not None else merged
            if isinstance(result, Hint):
                return self._show(index, merged, hint=result)
            if isinstance(result, Stop):
                return self._show(index, merged, above=result.fragment)
            if isinstance(result, Done):
                self._forget(face)
                return result.fragment
            if index + 1 == len(self._steps):
                return self._show(index, result)
            return self._move(face, index + 1, index, result)

    def _move(self, face: Face, index: int, stay: int, answers: Answers) -> str:
        """Record `index` as the step reached and show it; on a write failure,
        stay on `stay` with the failure above it."""
        kept = {name: value for name, value in answers.items() if not is_secret(name)}
        record = {"version": VERSION, "step": self._steps[index].name, "answers": kept}
        try:
            self.progress.parent.mkdir(parents=True, exist_ok=True)
            safe_write.write_whole(self.progress, json.dumps(record, indent=1) + "\n",
                                   prefix=".wizard-")
        except OSError as exc:
            return self._show(stay, answers, above=face.fail(exc, publishing=False))
        return self._show(index, answers)

    def _forget(self, face: Face) -> None:
        try:
            self.progress.unlink(missing_ok=True)
        except OSError as exc:
            face.fail(exc, publishing=False)    # logged, not shown (§ 4.2)

    def _read(self) -> tuple[int, Answers]:
        try:
            record = json.loads(self.progress.read_text(encoding="utf-8"))
            names = [step.name for step in self._steps]
            answers = record["answers"]
            if (record.get("version") != VERSION or record.get("step") not in names
                    or not isinstance(answers, dict)
                    or not all(isinstance(k, str) and isinstance(v, str)
                               for k, v in answers.items())):
                raise ValueError("not a progress file")
            return names.index(record["step"]), answers
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return 0, {}

    def _show(self, index: int, answers: Answers, *, hint: Hint | None = None,
              above: str = "") -> str:
        e = html.escape
        step = self._steps[index]
        loose = (f'<p class="hint">{e(hint.text)}</p>'
                 if hint is not None and hint.field not in step.fields else "")
        back = ('<button type="submit" name="go" value="back">Back</button>'
                if index > 0 else "")
        return (
            f"<h1>{e(step.title)}</h1>"
            f'<p class="wizard-step">Step {index + 1} of {len(self._steps)}</p>'
            + above + loose
            + f'<form method="post" action="{e(self._address, quote=True)}">'
            f'<input type="hidden" name="step" value="{e(step.name, quote=True)}">'
            + step.show(answers, hint)
            # Next comes first, so pressing Enter in a box means Next.
            + '<p><button type="submit" name="go" value="next">Next</button> '
            + back + "</p></form>"
        )
