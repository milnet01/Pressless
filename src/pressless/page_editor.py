"""The fixed pages and the furniture: the words in a box, the code behind a
button (PRESS-0014).

His changes wait in a copy of their own, beside the live file, until he
publishes that page, so a publish of anything else never sends out a
half-typed footer (docs/specs/PRESS-0014-fixed-pages.md § 3 decision 1). The
words view replaces pieces of text in place and the code view writes what he
typed; neither parses a file to regenerate it (§ 4.9).

Nothing is held between requests: every route reads the Store afresh, and a
save refuses a file this window did not see, as the entry editor's does.
"""
from __future__ import annotations

import difflib
import hashlib
import html
import json
import re
import threading
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from pressless import builder, credentials, editor, publisher, publishing, settings, setup, store
from pressless.face import (
    SENTENCES,
    Face,
    Reply,
    Request,
    Sentence,
    Site,
    render_notices,
)

WORDS = "words"
CODE = "code"
HOME = "index"                      # the fixed page furniture previews first
NEWEST = "_newest"                  # a `show` naming his newest entry; no page name holds "_"


class PiecesChanged(Exception):
    """The box holds a different number of paragraphs from the page (§ 4.2)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[PiecesChanged] = Sentence(
    "The box now holds a different number of paragraphs from your page, so Pressless "
    "did not save it.",
    Site.UNCHANGED,
    "Put the paragraphs back as they were, or press Show me the code to add or "
    "remove one.",
)

STRAY = ("The text you put between the header or footer markers will be replaced "
         "from the one Header or Footer when your site is built. Edit the Header or "
         "Footer instead.")

_KEPT_COPY = ("Your changes were published, but their waiting copy was left in place. "
              "You can throw it away.")
# After an unknown outcome the live file already holds the changes (§ 4.7), so
# throwing the copy away loses nothing either way (PRESS-0144).
_KEPT_COPY_UNKNOWN = ("Pressless cannot tell whether your changes were published, and "
                      "their waiting copy was left in place. You can throw it away.")

_HIDDEN = frozenset(("script", "style", "template"))
_LABELS = {"header": "Header", "footer": "Footer", "navigation": "Navigation"}
_JSON = "application/json"
_HTML = "text/html; charset=utf-8"


@dataclass(frozen=True)
class Piece:
    start: int          # offsets into the file's text
    end: int
    shown: str          # what the box shows for it


# ------------------------------------------------------ the words (§ 4.2) ---


class _Runs(HTMLParser):
    """Every run of text between two markup constructs, as offsets, and
    whether it sits inside an element the box leaves out."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.text = text
        self.starts = [0] + [at + 1 for at, char in enumerate(text) if char == "\n"]
        self.runs: list[list[int | bool]] = []     # [start, end, hidden]
        self.hidden = 0

    def _at(self) -> int:
        line, column = self.getpos()
        return self.starts[line - 1] + column

    def _text(self, length: int) -> None:
        start = self._at()
        if self.runs and self.runs[-1][1] == start:
            self.runs[-1][1] = start + length
        else:
            self.runs.append([start, start + length, self.hidden > 0])

    def _reference(self, raw: str) -> None:
        start = self._at()
        self._text(len(raw) + (self.text.startswith(";", start + len(raw))))

    def handle_data(self, data: str) -> None:
        self._text(len(data))

    def handle_entityref(self, name: str) -> None:
        self._reference(f"&{name}")

    def handle_charref(self, name: str) -> None:
        self._reference(f"&#{name}")

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _HIDDEN:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN and self.hidden:
            self.hidden -= 1


def pieces(name: str, html_text: str) -> tuple[Piece, ...]:
    """The pieces the box shows, in file order (§ 4.2)."""
    spans = builder.furniture_spans(name, html_text)
    parser = _Runs(html_text)
    parser.feed(html_text)
    parser.close()
    found = []
    for start, end, hidden in parser.runs:
        if hidden or any(inside <= start < closing for inside, closing in spans):
            continue
        shown = re.sub(r"\s+", " ", html.unescape(html_text[start:end])).strip()
        if shown:
            found.append(Piece(start, end, shown))
    return tuple(found)


def words(name: str, html_text: str) -> str:
    """The box's text: every piece's shown form, a blank line between each."""
    return "\n\n".join(piece.shown for piece in pieces(name, html_text))


def put_words(name: str, html_text: str, box: str) -> str:
    """The file with each changed paragraph written into its own piece, every
    other byte as it was (§ 4.2)."""
    lines = box.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parts, current = [], []
    for line in lines:
        if line.strip():
            current.append(line)
        else:
            parts.append("\n".join(current).strip())
            current = []
    parts.append("\n".join(current).strip())
    # Every empty part goes, so a run of blank lines is one gap (PRESS-0143).
    parts = [part for part in parts if part]

    found = pieces(name, html_text)
    if len(parts) != len(found):
        raise PiecesChanged(f"the box holds {len(parts)} paragraphs and the page {len(found)}")
    out = html_text
    for piece, part in reversed(tuple(zip(found, parts, strict=True))):
        if part == piece.shown:
            continue
        raw = html_text[piece.start:piece.end]
        leading = raw[:len(raw) - len(raw.lstrip())]
        trailing = raw[len(raw.rstrip()):]
        out = (out[:piece.start] + leading + html.escape(part, quote=False) + trailing
               + out[piece.end:])
    return out


# ------------------------------------------------------- the code (§ 4.3) ---


def put_code(html_text: str, text: str) -> str:
    """The posted text as the file to write, each untouched line keeping its own
    line ending (§ 4.3)."""
    posted = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    last_ends = posted[-1] == ""
    if last_ends:
        posted.pop()
    old = [(match.group(1), match.group(2))
           for match in re.finditer(r"([^\r\n]*)(\r\n|\n|\r|\Z)", html_text)
           if match.group(0) or match.start() < len(html_text)]
    kept: dict[int, str] = {}
    matcher = difflib.SequenceMatcher(None, [line for line, _ in old], posted, autojunk=False)
    for tag, first, _, second, second_end in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(second_end - second):
                ending = old[first + offset][1]
                if ending:
                    kept[second + offset] = ending
    fallback = old[0][1] if old and old[0][1] else "\n"
    out, previous = [], None
    for number, line in enumerate(posted):
        if number == len(posted) - 1 and not last_ends:
            out.append(line)
            break
        ending = kept.get(number) or previous or fallback
        out.append(line + ending)
        previous = ending
    return "".join(out)


def stray_furniture(name: str, html_text: str) -> bool:
    """Whether a marker block holds anything but whitespace (§ 4.3). A file
    whose markers do not pair answers False: its preview shows that instead."""
    try:
        spans = builder.furniture_spans(name, html_text)
    except builder.BuildStopped:
        return False
    return any(html_text[inside:closing].strip() for inside, closing in spans)


# ----------------------------------------------------------- the routes ---


def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None:
    """Add the page editor's routes to `face` (§ 4.4). The preview's files are
    served by `editor.register`, which the launch calls first."""
    folder = Path(folder)

    def route(handler):
        return lambda request: handler(face, folder, editor.LOCK, request)

    face.add_page("GET", "/page", route(_open))
    face.add_page("POST", "/page/save", route(_save))
    face.add_page("POST", "/page/discard", route(_discard))
    face.add_page("POST", "/page/publish",
                  lambda request: _publish(face, folder, request, transport))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _page_address(kind: str, name: str, **more: str) -> str:
    return "/page?" + urllib.parse.urlencode({"kind": kind, "name": name, **more})


def _view(kind: str, asked: str) -> str:
    """§ 4.4: the furniture always opens in the code view (§ 3 decision 5)."""
    if kind == store.FURNITURE_FOLDER:
        return CODE
    return CODE if asked == CODE else WORDS


def _show(folder: Path, kind: str, name: str, asked: str) -> str | None:
    """The page a preview shows (§ 4.4): a fixed page shows itself; the
    furniture shows what was asked for, else Home, else the first fixed page,
    else his newest entry."""
    if kind == store.PAGES_FOLDER:
        return name
    if asked == NEWEST:
        return None
    held = store.list_html(folder, store.PAGES_FOLDER)
    if asked in held:
        return asked
    if HOME in held:
        return HOME
    return held[0] if held else None


def _read(folder: Path, kind: str, name: str) -> tuple[Path, bool]:
    """§ 4.5: the waiting copy where one exists, else the live file."""
    copy = store.html_path_for(folder, kind, name, waiting=True)
    if copy.is_file():
        return copy, True
    live = store.html_path_for(folder, kind, name)
    if not live.is_file():
        raise store.EntryNotFound(f"there is no {kind} file {name}")
    return live, False


def _preview(face: Face, folder: Path, kind: str, name: str, text: str,
             show: str | None) -> tuple[str | None, str | None]:
    """§ 4.6 step 5: the preview's address, or the failure in its place."""
    try:
        saved = settings.load(folder)
        relative = builder.preview_html(folder, saved, folder / editor.PREVIEW_FOLDER,
                                        builder.Html(kind, name, text), show=show,
                                        photo_src=editor.photo_src)
    except Exception as exc:  # noqa: BLE001 -- a preview failure never undoes the save
        return None, face.fail(exc, publishing=False)
    return editor.PREVIEW_ADDRESS + relative, None


def _write(folder: Path, form: dict[str, str]) -> tuple[str, str]:
    """§ 4.6 steps 1 to 4: write the box to the waiting copy, and return the
    file written and its digest. Takes no lock; the caller holds LOCK."""
    kind, name = form.get("kind", ""), form.get("name", "")
    waiting = form.get("waiting") == "1"
    copy = store.html_path_for(folder, kind, name, waiting=True)
    path = copy if waiting else store.html_path_for(folder, kind, name)
    if not path.is_file():
        raise store.EntryNotFound(f"there is no {kind} file {name}")
    if _digest(path) != form.get("base", ""):
        raise editor.ChangedElsewhere(f"the {kind} file {name} changed since this window read it")
    if not waiting and copy.is_file():
        raise editor.ChangedElsewhere(f"the {kind} file {name} gained a waiting copy")
    text = store.read_html(path)
    posted = form.get("text", "")
    new = (put_code(text, posted) if _view(kind, form.get("view", "")) == CODE
           else put_words(name, text, posted))
    return new, _digest(store.write_html(folder, kind, name, new, waiting=True))


def _hint(failure: PiecesChanged) -> str:
    said = SENTENCES[PiecesChanged]
    return f"{said.what} {said.next}"


def _failed(face: Face, notices: list[str], failure: Exception) -> Reply:
    body = render_notices(notices) + face.fail(failure, publishing=False)
    return Reply(body.encode("utf-8"), _HTML, status=409)


def _json(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


def _open(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str:
    """§ 4.5."""
    kind, name = request.query.get("kind", ""), request.query.get("name", "")
    broken = None
    with lock, face.capture() as notices:
        try:
            path, waiting = _read(folder, kind, name)
            text = store.read_html(path)
            base = _digest(path)
            show = _show(folder, kind, name, request.query.get("show", ""))
            entries = store.list_slugs(folder, draft=False)
            held = store.list_html(folder, store.PAGES_FOLDER)
        except store.StoreError as exc:
            failure: Exception | None = exc
        else:
            failure = None
            view = _view(kind, request.query.get("view", ""))
            try:
                builder.furniture_spans(name, text)
            except builder.BuildStopped as exc:
                view, broken = CODE, face.fail(exc, publishing=False)
            preview, preview_failure = _preview(face, folder, kind, name, text, show)
    if failure is not None:
        return render_notices(notices) + face.fail(failure, publishing=False)
    box = words(name, text) if view == WORDS else text
    return render_notices(notices) + _page(
        kind, name, view, show, waiting, base, box, held, bool(entries), broken,
        preview, preview_failure)


def _page(kind: str, name: str, view: str, show: str | None, waiting: bool, base: str,
          box: str, held: tuple[str, ...], has_entries: bool, broken: str | None,
          preview: str | None, failure: str | None) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    def link(label: str, address: str, current: bool = False) -> str:
        marked = ' aria-current="page"' if current else ""
        return f'<a data-page-link href="{attr(address)}"{marked}>{html.escape(label)}</a>'

    shown = NEWEST if show is None else show
    title = ("Home" if name == HOME else name) if kind == store.PAGES_FOLDER \
        else _LABELS.get(name, name)
    switch = ""
    if kind == store.PAGES_FOLDER and broken is None:
        other, label = (CODE, "Show me the code") if view == WORDS else (WORDS, "Back to the words")
        switch = f"<p>{link(label, _page_address(kind, name, view=other))}</p>"
    picker = ""
    if kind == store.FURNITURE_FOLDER:
        choices = [link("Home" if page == HOME else page,
                        _page_address(kind, name, show=page), page == show)
                   for page in held]
        if has_entries:
            choices.append(link("Your newest entry", _page_address(kind, name, show=NEWEST),
                                show is None))
        picker = "<p>Show it on: " + " ".join(choices) + "</p>"
    box_class = f' class="{attr(builder.BODY_CLASS)}"' if view == WORDS else ""
    stylesheets = "".join(
        f'<link rel="stylesheet" href="{attr(editor.PREVIEW_ADDRESS + sheet)}">'
        for sheet in builder.STYLESHEETS)
    return f"""{stylesheets}
<p><a href="/">Your writing</a> <span id="save-status"></span></p>
<h1>{html.escape(title)}</h1>
<div id="standing" data-waiting="{'1' if waiting else '0'}">
<p data-when="1"{'' if waiting else ' hidden'}>These changes are not on your site yet.</p>
<form data-when="1" method="post" action="/page/discard"{'' if waiting else ' hidden'}>
<input type="hidden" name="kind" value="{attr(kind)}">
<input type="hidden" name="name" value="{attr(name)}">
<input type="hidden" name="base" value="{attr(base)}">
<button>Throw away changes</button></form>
<p data-when="0"{' hidden' if waiting else ''}>Your changes stay on this computer until you
 publish this page.</p>
</div>
{switch}{picker}
<div id="broken">{broken or ""}</div>
<div id="notices"></div>
<p id="save-hint"></p>
<form id="editor" data-kind="{attr(kind)}" data-name="{attr(name)}" data-view="{attr(view)}"
 data-show="{attr(shown)}" data-waiting="{'1' if waiting else '0'}" data-base="{attr(base)}"
 onsubmit="return false">
<p><button type="button" data-editor="publish">Publish</button>
 <span id="publish-status"></span>
 <button type="button" data-undo>Undo the last publish</button>
 <span id="undo-status"></span></p>
<textarea name="text"{box_class} rows="24">
{html.escape(box)}</textarea>
</form>
<div id="failure">{failure or ""}</div>
<div id="undo-result"></div>
<iframe id="preview" title="Preview" sandbox="allow-same-origin allow-scripts"
 src="{attr(preview or 'about:blank')}"></iframe>
<script>{_PAGE_SCRIPT}</script>
<script>{editor._UNDO_SCRIPT}</script>"""


def _save(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.6."""
    form = editor._form(request)
    kind, name = form.get("kind", ""), form.get("name", "")
    with lock, face.capture() as notices:
        try:
            new, base = _write(folder, form)
        except PiecesChanged as exc:
            return _json({"waiting": form.get("waiting") == "1", "base": form.get("base", ""),
                          "preview": None, "failure": None, "hint": _hint(exc),
                          "notices": render_notices(notices)})
        except (store.StoreError, editor.ChangedElsewhere, builder.BuildStopped) as exc:
            failure: Exception | None = exc
        else:
            failure = None
            if (kind == store.PAGES_FOLDER and _view(kind, form.get("view", "")) == CODE
                    and stray_furniture(name, new)):
                notices.append(STRAY)
            preview, preview_failure = _preview(
                face, folder, kind, name, new, _show(folder, kind, name, form.get("show", "")))
    if failure is not None:
        return _failed(face, notices, failure)
    return _json({"waiting": True, "base": base, "preview": preview, "failure": preview_failure,
                  "hint": None, "notices": render_notices(notices)})


def _discard(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.8."""
    form = editor._form(request)
    kind, name = form.get("kind", ""), form.get("name", "")
    with lock, face.capture() as notices:
        try:
            copy = store.html_path_for(folder, kind, name, waiting=True)
            if not copy.is_file() or _digest(copy) != form.get("base", ""):
                raise editor.ChangedElsewhere(
                    f"the waiting copy of {name} is not the one this window read")
            store.move_to_bin(folder, copy)
        except (store.StoreError, editor.ChangedElsewhere) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    return Reply(b"", "text/plain; charset=utf-8", status=303,
                 location=_page_address(kind, name))


def _publish(face: Face, folder: Path, request: Request,
             transport: publisher.Transport | None) -> Reply:
    """§ 4.7."""
    form = editor._form(request)
    kind, name = form.get("kind", ""), form.get("name", "")
    notices: list[str] = []

    def gathered(step):
        caught: list[str] | None = None
        try:
            with face.capture() as caught:
                return step()
        finally:
            if caught is not None:
                notices.extend(caught)

    with editor.LOCK:
        try:
            new, _ = gathered(lambda: _write(folder, form))
        except PiecesChanged as exc:
            return _json({"published": False, "waiting": form.get("waiting") == "1",
                          "base": form.get("base", ""), "failure": None, "hint": _hint(exc),
                          "notices": render_notices(notices)})
        except (store.StoreError, editor.ChangedElsewhere, builder.BuildStopped) as exc:
            return _failed(face, notices, exc)

        copy = store.html_path_for(folder, kind, name, waiting=True)

        def finish() -> bool:
            """§ 4.7 step 5: True where the copy could not be binned."""
            try:
                gathered(lambda: store.move_to_bin(folder, copy))
            except Exception:  # noqa: BLE001 -- never replaces the publish's result
                return True
            return False

        try:
            saved = gathered(lambda: settings.load(folder))
            key = credentials.read(saved.credentials.store, folder,
                                   saved.credentials.github_account)
            remembered = gathered(lambda: store.read_html(store.html_path_for(folder, kind, name)))
            gathered(lambda: store.write_html(folder, kind, name, new))
            try:
                publishing.publish(folder, saved, key, entry=None, capture=face.capture,
                                   notices=notices, transport=transport)
            except publisher.OutcomeUnknown:
                if finish():
                    notices.append(_KEPT_COPY_UNKNOWN)
                raise
            except BaseException:
                # A failure here is raised in place of the original (§ 4.7).
                gathered(lambda: store.write_html(folder, kind, name, remembered))
                raise
            kept = finish()
        except Exception as exc:  # noqa: BLE001 -- every failure is shown beside the save
            failure: str | None = face.fail(exc, publishing=False, secret=setup.KEY)
            published = False
        else:
            failure = None
            published = True
            if kept:
                notices.append(_KEPT_COPY)
        waiting, base = gathered(lambda: _left(folder, kind, name))

    return _json({"published": published, "waiting": waiting, "base": base,
                  "failure": failure, "hint": None, "notices": render_notices(notices)})


def _left(folder: Path, kind: str, name: str) -> tuple[bool, str]:
    """The file the page saves to next, read from disk after the publish."""
    copy = store.html_path_for(folder, kind, name, waiting=True)
    if copy.is_file():
        return True, _digest(copy)
    return False, _digest(store.html_path_for(folder, kind, name))


# The page's script (§ 4.5), PRESS-0012 § 4.7's with this page's fields. A
# change saves about a second after the last one, never two saves at once, and
# on leaving only where a change is unsaved. A switch of view or a picker link
# waits for a save in flight and saves an unsaved change first.
_PAGE_SCRIPT = """
(() => {
  const form = document.getElementById("editor");
  const state = {kind: form.dataset.kind, name: form.dataset.name, view: form.dataset.view,
                 show: form.dataset.show, waiting: form.dataset.waiting, base: form.dataset.base};
  const status = document.getElementById("save-status");
  const hint = document.getElementById("save-hint");
  let timer = null, inFlight = null, dirty = false, stopped = false;

  const fields = () => {
    const data = new URLSearchParams();
    for (const name of ["kind", "name", "view", "show", "waiting", "base"]) {
      data.set(name, state[name]);
    }
    data.set("text", form.elements.text.value);
    return data;
  };
  const adopt = (reply) => {
    state.waiting = reply.waiting ? "1" : "0"; state.base = reply.base;
    document.querySelectorAll("input[name=base]").forEach((input) => { input.value = reply.base; });
    document.querySelectorAll("#standing [data-when]").forEach((part) => {
      part.hidden = part.dataset.when !== state.waiting;
    });
    document.getElementById("notices").innerHTML = reply.notices;
    hint.textContent = reply.hint || "";
  };
  const stop = (text) => {
    stopped = true;
    status.textContent = "Not saved";
    document.getElementById("failure").innerHTML = text;
  };

  async function send() {
    dirty = false; status.textContent = "Saving";
    try {
      const answer = await fetch("/page/save", {method: "POST", body: fields()});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      const reply = JSON.parse(text);
      adopt(reply);
      if (reply.hint) { status.textContent = "Not saved"; return; }
      document.getElementById("failure").innerHTML = reply.failure || "";
      if (reply.preview) {
        document.getElementById("preview").src = reply.preview + "?n=" + Date.now();
      }
      status.textContent = "Saved";
    } catch (error) {
      stop("");
    }
  }
  async function save() {
    if (stopped || inFlight || !dirty) return;
    inFlight = send();
    try { await inFlight; } finally {
      inFlight = null;
      if (dirty && !stopped) schedule();
    }
  }
  async function settle() {
    clearTimeout(timer);
    while (inFlight) await inFlight;
    if (dirty && !stopped) await save();
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(save, 1000); }

  form.addEventListener("input", () => { dirty = true; schedule(); });
  window.addEventListener("pagehide", () => {
    if (stopped || inFlight || !dirty) return;
    fetch("/page/save", {method: "POST", body: fields(), keepalive: true});
  });
  document.querySelectorAll("a[data-page-link]").forEach((link) => {
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      await settle();
      if (!stopped) window.location.href = link.href;
    });
  });

  const publish = document.querySelector("button[data-editor=publish]");
  publish.addEventListener("click", async () => {
    clearTimeout(timer);
    while (inFlight) await inFlight;
    const said = document.getElementById("publish-status");
    publish.disabled = true;
    said.textContent = "Publishing\\u2026 this can take a few minutes the first time. " +
      "Keep this page open.";
    try {
      const answer = await fetch("/page/publish", {method: "POST", body: fields()});
      const text = await answer.text();
      if (answer.status !== 200) { said.textContent = ""; stop(text); return; }
      const reply = JSON.parse(text);
      dirty = false;
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      said.textContent = reply.published
        ? "Published. Your site shows it within a few minutes." : "";
    } catch (error) {
      said.textContent = ""; stop("");
    } finally {
      publish.disabled = false;
    }
  });
})();
"""
