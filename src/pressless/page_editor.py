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
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from pressless import (
    builder,
    editor,
    github_setup,
    menu,
    pressing,
    publisher,
    publishing,
    settings,
    starter,
    store,
)
from pressless.face import (
    SENTENCES,
    Face,
    Notice,
    Reply,
    Request,
    Sentence,
    Site,
    message_box,
    render_notices,
    sentence_for,
    true_colours,
)
from pressless.words import say

WORDS = "words"
CODE = "code"
HOME = "index"                      # the fixed page furniture previews first
NEWEST = "_newest"                  # a `show` naming his newest entry; no page name holds "_"


class PiecesChanged(Exception):
    """The box holds a different number of paragraphs from the page (§ 4.2)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[PiecesChanged] = Sentence(
    "failure.page_editor.PiecesChanged.what",
    Site.UNCHANGED,
    "failure.page_editor.PiecesChanged.next",
)

# PRESS-0195 § 4.2: caught where a menu is edited and said as a notice, but
# every failure type carries its sentence (docs/design.md § Errors).
SENTENCES[menu.Unusual] = Sentence(
    "failure.menu.Unusual.what",
    Site.UNCHANGED,
    "failure.menu.Unusual.next",
)

_HIDDEN = frozenset(("script", "style", "template"))
_LABELS = {"header": "editor.pages.header", "footer": "editor.pages.footer",
           "navigation": "editor.pages.navigation"}
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
    # PRESS-0195: a new page, and removing or renaming one.
    face.add_page("POST", "/page/new", route(_new))
    face.add_page("POST", "/page/remove",
                  lambda request: _reshape(face, folder, request, transport, renaming=False))
    face.add_page("POST", "/page/rename",
                  lambda request: _reshape(face, folder, request, transport, renaming=True))


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
    digest = _digest(store.write_html(folder, kind, name, new, waiting=True))
    pressing.forget()  # PRESS-0235 decision 6
    return new, digest


def _hint(failure: PiecesChanged) -> str:
    said = sentence_for(failure, publishing=False)
    return f"{said.what} {said.next}"


def _failed(face: Face, notices: list[str], failure: Exception) -> Reply:
    body = render_notices(notices) + face.fail(failure, publishing=False)
    return Reply(body.encode("utf-8"), _HTML, status=409)


def _json(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


def _open(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str:
    """§ 4.5."""
    kind, name = request.query.get("kind", ""), request.query.get("name", "")
    # PRESS-0235 § 4.5: during a press, a page that opens the editor once it ends.
    held = pressing.holding()
    if held is not None:
        return held
    broken = None
    with lock, face.capture() as notices:
        try:
            path, waiting = _read(folder, kind, name)
            text = store.read_html(path)
            base = _digest(path)
            show = _show(folder, kind, name, request.query.get("show", ""))
            # PRESS-0214 § 4.5: no newest entry to show a change on while the
            # journal is off.
            entries = (store.list_slugs(folder, draft=False)
                       if store.journal_on(folder) else ())
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
        preview, preview_failure, builder.stylesheets(folder),
        face.view_site(), starter.unpublished(folder))


def _page(kind: str, name: str, view: str, show: str | None, waiting: bool, base: str,
          box: str, held: tuple[str, ...], has_entries: bool, broken: str | None,
          preview: str | None, failure: str | None, sheets: tuple[str, ...],
          visit: str, off_site: bool) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    def link(label: str, address: str, current: bool = False) -> str:
        marked = ' aria-current="page"' if current else ""
        return f'<a data-page-link href="{attr(address)}"{marked}>{html.escape(label)}</a>'

    shown = NEWEST if show is None else show
    if kind == store.PAGES_FOLDER:
        title = say("editor.pages.home") if name == HOME else name
    else:
        title = say(_LABELS[name]) if name in _LABELS else name
    switch = ""
    if kind == store.PAGES_FOLDER and broken is None:
        other, label = ((CODE, say("page_editor.show_code")) if view == WORDS
                        else (WORDS, say("page_editor.show_words")))
        switch = f"<p>{link(label, _page_address(kind, name, view=other))}</p>"
    picker = ""
    if kind == store.FURNITURE_FOLDER:
        choices = [link(say("editor.pages.home") if page == HOME else page,
                        _page_address(kind, name, show=page), page == show)
                   for page in held]
        if has_entries:
            choices.append(link(say("page_editor.newest"), _page_address(kind, name, show=NEWEST),
                                show is None))
        picker = f"<p>{say('page_editor.show_on')} " + " ".join(choices) + "</p>"
    # PRESS-0195 § 4.4: every fixed page but the homepage.
    reshape = ""
    if kind == store.PAGES_FOLDER and name != HOME:
        reshape = (f'<p><button type="button" data-pages="rename">'
                   f'{say("page_editor.rename")}</button> '
                   f'<button type="button" data-pages="remove">'
                   f'{say("page_editor.remove")}</button></p>')
    box_class = f' class="{attr(builder.BODY_CLASS)}"' if view == WORDS else ""
    # PRESS-0234: the press row's status line, between presses. The script
    # keeps it in step (its `standing`).
    standing_word = say("script.standing.off_site" if off_site else
                        "script.standing.changes" if waiting else "script.standing.on_site")
    said, running, ended = pressing.shown(standing_word)
    pressed = editor._RUNNING if running else ""
    stylesheets = "".join(
        f'<link rel="stylesheet" href="{attr(editor.PREVIEW_ADDRESS + sheet)}">'
        for sheet in sheets)
    return f"""{stylesheets}
<p><a href="/">{say("face.your_writing")}</a> <span id="save-status"></span></p>
<h1>{html.escape(title)}</h1>
<div id="standing" data-waiting="{'1' if waiting else '0'}">
<p data-when="1"{'' if waiting else ' hidden'}>{say("editor.standing.waiting")}</p>
<form data-when="1" method="post" action="/page/discard"{'' if waiting else ' hidden'}>
<input type="hidden" name="kind" value="{attr(kind)}">
<input type="hidden" name="name" value="{attr(name)}">
<input type="hidden" name="base" value="{attr(base)}">
<button>{say("editor.bin_proof")}</button></form>
<p data-when="0"{' hidden' if waiting else ''}>{say("page_editor.standing")}</p>
</div>
{switch}{picker}
<div id="broken">{broken or ""}</div>
{message_box("notices")}
<p id="save-hint"></p>
<form id="editor" data-kind="{attr(kind)}" data-name="{attr(name)}" data-view="{attr(view)}"
 data-show="{attr(shown)}" data-waiting="{'1' if waiting else '0'}" data-base="{attr(base)}"
 data-off-site="{'1' if off_site else '0'}" onsubmit="return false">
<p><button type="button" data-editor="publish">{say("editor.press")}</button>
 {visit}
 <button type="button" data-undo>{say("editor.undo")}</button></p>
<p id="publish-status" class="press-status" role="status"{pressed}>{attr(said)}</p>
{reshape}<textarea name="text"{box_class} rows="24">
{html.escape(box)}</textarea>
</form>
{message_box("failure", (failure or "") + (ended or ""), forgets=True)}
<div id="undo-result"></div>
<div id="proof">{true_colours()}
<iframe id="preview" title="{attr(say("editor.proof_title"))}" sandbox="allow-same-origin"
 src="{attr(preview or 'about:blank')}"></iframe></div>
<script>{_PAGE_SCRIPT}</script>
<script>{editor._UNDO_SCRIPT}</script>"""


def _save(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.6."""
    form = editor._form(request)
    kind, name = form.get("kind", ""), form.get("name", "")
    changed: PiecesChanged | None = None
    with lock, face.capture() as notices:
        try:
            new, base = _write(folder, form)
        except PiecesChanged as exc:
            # Answered after the block: capture fills `notices` only on exit,
            # so a reply built in here dropped every notice (PRESS-0162).
            changed, failure = exc, None
        except (store.StoreError, editor.ChangedElsewhere, builder.BuildStopped) as exc:
            failure: Exception | None = exc
        else:
            failure = None
            if (kind == store.PAGES_FOLDER and _view(kind, form.get("view", "")) == CODE
                    and stray_furniture(name, new)):
                notices.append(say("notice.page_editor.stray"))
            preview, preview_failure = _preview(
                face, folder, kind, name, new, _show(folder, kind, name, form.get("show", "")))
    if changed is not None:
        return _json({"waiting": form.get("waiting") == "1", "base": form.get("base", ""),
                      "preview": None, "failure": None, "hint": _hint(changed),
                      "notices": render_notices(notices)})
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
    # PRESS-0195 § 4.3: a page never pressed had only this copy, so its editor
    # has nothing left to open.
    live = store.html_path_for(folder, kind, name)
    return Reply(b"", "text/plain; charset=utf-8", status=303,
                 location=_page_address(kind, name) if live.is_file() else "/")


def _publish(face: Face, folder: Path, request: Request,
             transport: publisher.Transport | None) -> Reply:
    """§ 4.7, run as a press (PRESS-0235 § 4.4)."""
    form = editor._form(request)

    def busy(said: str) -> Reply:
        """Nothing saved: the page keeps the file it posted (PRESS-0235 § 4.4)."""
        return _json({"published": False, "waiting": form.get("waiting") == "1",
                      "base": form.get("base", ""), "failure": None, "hint": None,
                      "notices": "", "busy": True, "said": said})

    return pressing.run(pressing.PUBLISH, busy,
                        lambda told: _pressed(face, folder, form, transport, told))


def _pressed(face: Face, folder: Path, form: dict[str, str],
             transport: publisher.Transport | None,
             told: Callable[[pressing.Outcome], None]) -> Reply:
    kind, name = form.get("kind", ""), form.get("name", "")
    notices: list[str] = []
    said: list[str] = []
    gathered = _gatherer(face, notices)

    with editor.LOCK:
        try:
            new, _ = gathered(lambda: _write(folder, form))
        except PiecesChanged as exc:
            told(pressing.Outcome(say("script.press.paragraphs")))
            return _json({"published": False, "waiting": form.get("waiting") == "1",
                          "base": form.get("base", ""), "failure": None, "hint": _hint(exc),
                          "notices": render_notices(notices), "busy": False})
        except (store.StoreError, editor.ChangedElsewhere, builder.BuildStopped) as exc:
            told(pressing.Outcome(say("script.press.not_published"),
                                  face.fail(exc, publishing=False)))
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
            key = github_setup.token(folder, saved.credentials.store,
                                     saved.credentials.github_account)
            changes = _Changes(folder)
            # PRESS-0195 § 4.3: a new page's first press, with no live file.
            first = (kind == store.PAGES_FOLDER
                     and not store.html_path_for(folder, kind, name).is_file())
            gathered(lambda: changes.write(kind, name, new))
            if first:
                words = _title(new) or builder.label(name)
                if not gathered(lambda: _edit_menu(folder, changes,
                                                   lambda text: menu.add(text, name, words))):
                    said.append(say("notice.pages.menu_unusual"))
            try:
                publishing.publish(folder, saved, key, entry=None, capture=face.capture,
                                   notices=notices, transport=transport)
            except publisher.OutcomeUnknown:
                if finish():
                    notices.append(Notice(say("notice.page_editor.kept_copy_unknown"),
                                          Site.UNKNOWN))
                raise
            except BaseException:
                # A failure here is raised in place of the original (§ 4.7).
                gathered(changes.put_back)
                raise
            kept = finish()
        except Exception as exc:  # noqa: BLE001 -- every failure is shown beside the save
            failure: str | None = (face.fail(exc, publishing=False,
                                             secret=say("failure.secret.publishing_key"))
                                   + publishing.replace_link(exc))
            published = False
            notices.extend(_menu_said(said, False, isinstance(exc, publisher.OutcomeUnknown)))
        else:
            failure = None
            published = True
            notices.extend(_menu_said(said, True, False))
            if kept:
                notices.append(Notice(say("notice.page_editor.kept_copy"), Site.UPDATED))
        told(pressing.Outcome(say("script.press.published"), None) if published
             else pressing.Outcome(say("script.press.not_published"), failure))
        waiting, base = gathered(lambda: _left(folder, kind, name))

    return _json({"published": published, "waiting": waiting, "base": base,
                  "failure": failure, "hint": None, "notices": render_notices(notices),
                  "busy": False})


def _gatherer(face: Face, notices: list):
    """A step's notices, captured and added to `notices` whatever it does."""
    def gathered(step):
        caught: list[str] | None = None
        try:
            with face.capture() as caught:
                return step()
        finally:
            if caught is not None:
                notices.extend(caught)
    return gathered


# ------------------------------------------- adding, removing, renaming ---
# PRESS-0195 (docs/specs/PRESS-0195-add-remove-rename-pages.md).


class _Changes:
    """Every file a press writes or bins, remembered first, so a failed
    publish puts each back in reverse order (§ 4.4)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._back: list[Callable[[], object]] = []

    def write(self, kind: str, name: str, text: str, *, waiting: bool = False) -> None:
        path = store.html_path_for(self.folder, kind, name, waiting=waiting)
        before = store.read_html(path) if path.is_file() else None
        store.write_html(self.folder, kind, name, text, waiting=waiting)
        self._back.append(
            (lambda: store.move_to_bin(self.folder, path)) if before is None else
            (lambda: store.write_html(self.folder, kind, name, before, waiting=waiting)))

    def bin(self, kind: str, name: str, *, waiting: bool = False) -> None:
        path = store.html_path_for(self.folder, kind, name, waiting=waiting)
        if not path.is_file():
            return
        before = store.read_html(path)
        store.move_to_bin(self.folder, path)
        self._back.append(
            lambda: store.write_html(self.folder, kind, name, before, waiting=waiting))

    def forwards(self, forwards: dict[str, str]) -> None:
        path = store.page_forwards_path_for(self.folder)
        before = store.read_page_forwards(self.folder) if path.is_file() else None
        if forwards == (before or {}):
            return
        store.write_page_forwards(self.folder, forwards)
        self._back.append(
            (lambda: store.move_to_bin(self.folder, path)) if before is None else
            (lambda: store.write_page_forwards(self.folder, before)))

    def put_back(self) -> None:
        for step in reversed(self._back):
            step()


def _title(text: str) -> str:
    """A page's <title> text, unescaped; "" where it has none."""
    found = re.search(r"<title\b[^>]*>(.*?)</title\s*>", text, re.IGNORECASE | re.DOTALL)
    return html.unescape(found.group(1)).strip() if found else ""


def _edit_menu(folder: Path, changes: _Changes, edit: Callable[[str], str]) -> bool:
    """`edit` applied to the live navigation and its waiting copy (§ 4.2).
    False where one of them is a menu Pressless does not edit; that copy is
    left as it is."""
    usual = True
    for waiting in (False, True):
        path = store.html_path_for(folder, store.FURNITURE_FOLDER, "navigation",
                                   waiting=waiting)
        if not path.is_file():
            continue
        text = store.read_html(path)
        try:
            edited = edit(text)
        except menu.Unusual:
            usual = False
            continue
        if edited != text:
            changes.write(store.FURNITURE_FOLDER, "navigation", edited, waiting=waiting)
    return usual


def _menu_said(said: list[str], published: bool, unknown: bool) -> list[Notice]:
    """§ 4.3, § 4.4: a press's menu notices, saying what became of the site.
    None where the press failed and everything was put back."""
    if not (published or unknown):
        return []
    site = Site.UPDATED if published else Site.UNKNOWN
    return [Notice(text, site) for text in said]


def _name_refused(folder: Path, page: str, moving: str = "") -> str | None:
    """Why `page` cannot be a new page's name, as an editor.PAGE_HINTS code;
    None where it can. `moving` is the page a rename moves (§ 4.3, § 4.4)."""
    if not page:
        return "empty"
    try:
        store.html_path_for(folder, store.PAGES_FOLDER, page)
    except store.StoreError:
        return "unusable"
    held = (set(store.list_html(folder, store.PAGES_FOLDER))
            | set(store.list_html(folder, store.PAGES_FOLDER, waiting=True)))
    if page == HOME or page == moving or page in held:
        return "taken"
    forwards = store.read_page_forwards(folder)
    if page in forwards and forwards[page] != moving:
        return "forwarded"
    return None


def _new(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.3: the page's waiting copy, and nothing else."""
    named = editor._form(request).get("name", "").strip()
    page = editor.name_address(named)
    with lock, face.capture() as notices:
        try:
            refused = _name_refused(folder, page)
            if refused is None:
                store.write_html(folder, store.PAGES_FOLDER, page,
                                 starter.new_page(page, named, builder.stylesheets(folder)),
                                 waiting=True)
                pressing.forget()
        except store.StoreError as exc:
            return _failed(face, notices, exc)
    location = ("/?" + urllib.parse.urlencode({"page_hint": refused}) if refused
                else _page_address(store.PAGES_FOLDER, page))
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=location)


def _refused(folder: Path, form: dict[str, str], renaming: bool,
             saved: settings.Settings) -> str | None:
    """§ 4.4's refusals, as a words key; None where the change may go ahead."""
    name = form.get("name", "")
    if name == HOME:
        return "page_hint.home"
    if not store.html_path_for(folder, store.PAGES_FOLDER, name).is_file():
        return "page_hint.not_on_site"
    if not renaming:
        if name == "privacy" and saved.measurement_id is not None:
            return "page_hint.privacy_remove"
        return None
    if name == "privacy":
        return "page_hint.privacy_rename"
    if store.html_path_for(folder, store.PAGES_FOLDER, name, waiting=True).is_file():
        return "page_hint.changes"
    refused = _name_refused(folder, editor.name_address(form.get("to", "")), moving=name)
    return editor.PAGE_HINTS[refused] if refused else None


def _removed(folder: Path, name: str, changes: _Changes, notices: list) -> None:
    """§ 4.4 Remove: the page and its waiting copy to the bin, its link out of
    the menu, and the forwards to it dropped."""
    live = store.html_path_for(folder, store.FURNITURE_FOLDER, "navigation")
    linked = live.is_file() and bool(menu.links_to(store.read_html(live), name))
    changes.bin(store.PAGES_FOLDER, name)
    changes.bin(store.PAGES_FOLDER, name, waiting=True)
    if not _edit_menu(folder, changes, lambda text: menu.remove(text, name)):
        notices.append(say("notice.pages.menu_unusual"))
    elif not linked:
        notices.append(say("notice.pages.no_link"))
    changes.forwards({old: new for old, new in store.read_page_forwards(folder).items()
                      if new != name})
    for part in ("header", "footer"):
        path = store.html_path_for(folder, store.FURNITURE_FOLDER, part)
        if path.is_file() and f"pages/{name}{store.HTML_SUFFIX}" in store.read_html(path):
            notices.append(say("notice.pages.other_links"))
            break


def _renamed(folder: Path, name: str, to: str, changes: _Changes) -> None:
    """§ 4.4 Rename: the page byte for byte at its new name, the old one
    binned, its old name forwarded, and its menu link pointed on."""
    new = editor.name_address(to)
    text = store.read_html(store.html_path_for(folder, store.PAGES_FOLDER, name))
    changes.write(store.PAGES_FOLDER, new, text)
    changes.bin(store.PAGES_FOLDER, name)
    forwards = {old: (new if target == name else target)
                for old, target in store.read_page_forwards(folder).items() if old != new}
    forwards[name] = new
    changes.forwards(forwards)
    title = _title(text)
    old_words = (builder.label(name),) + ((title,) if title else ())
    _edit_menu(folder, changes, lambda menu_text: menu.rename(menu_text, name, new,
                                                              old_words, to))


def _reshape(face: Face, folder: Path, request: Request,
             transport: publisher.Transport | None, *, renaming: bool) -> Reply:
    """§ 4.4, run as a press (PRESS-0235 § 4.4)."""
    form = editor._form(request)

    def busy(said: str) -> Reply:
        """Nothing written (PRESS-0235 § 4.4)."""
        return _json({"published": False, "failure": None, "hint": None, "notices": "",
                      "busy": True, "said": said,
                      "address": _page_address(store.PAGES_FOLDER, form.get("name", ""))})

    return pressing.run(pressing.PUBLISH, busy,
                        lambda told: _reshaped(face, folder, form, transport, told,
                                               renaming))


def _reshaped(face: Face, folder: Path, form: dict[str, str],
              transport: publisher.Transport | None,
              told: Callable[[pressing.Outcome], None], renaming: bool) -> Reply:
    name, to = form.get("name", ""), form.get("to", "").strip()
    notices: list = []
    said: list[str] = []
    gathered = _gatherer(face, notices)
    hint: str | None = None
    failure: str | None = None
    unknown = False
    with editor.LOCK:
        try:
            saved = gathered(lambda: settings.load(folder))
            hint = gathered(lambda: _refused(folder, form, renaming, saved))
            if hint is None:
                key = github_setup.token(folder, saved.credentials.store,
                                         saved.credentials.github_account)
                changes = _Changes(folder)
                if renaming:
                    gathered(lambda: _renamed(folder, name, to, changes))
                else:
                    gathered(lambda: _removed(folder, name, changes, said))
                try:
                    publishing.publish(folder, saved, key, entry=None, capture=face.capture,
                                       notices=notices, transport=transport)
                except publisher.OutcomeUnknown:
                    raise
                except BaseException:
                    # A failure here is raised in place of the original.
                    gathered(changes.put_back)
                    raise
        except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page
            unknown = isinstance(exc, publisher.OutcomeUnknown)
            failure = (face.fail(exc, publishing=False,
                                 secret=say("failure.secret.publishing_key"))
                       + publishing.replace_link(exc))
        # Where he goes next, read from disk: the page where it still is.
        if store.html_path_for(folder, store.PAGES_FOLDER, name).is_file():
            address = _page_address(store.PAGES_FOLDER, name)
        elif renaming and hint is None and store.html_path_for(
                folder, store.PAGES_FOLDER, editor.name_address(to)).is_file():
            address = _page_address(store.PAGES_FOLDER, editor.name_address(to))
        else:
            address = "/"
    published = hint is None and failure is None
    notices.extend(_menu_said(said, published, unknown))
    told(pressing.Outcome(say("script.press.published") if published
                          else say("script.press.not_published"), failure))
    return _json({"published": published, "failure": failure,
                  "hint": say(hint) if hint else None,
                  "notices": render_notices(notices), "busy": False, "address": address})


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
_PAGE_SCRIPT = pressing.SCRIPT + """
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
    document.getElementById("publish-status").textContent = standing();
  };
  // PRESS-0234: what the press row's status line says between presses.
  const standing = () => say(form.dataset.offSite === "1" ? "script.standing.off_site"
    : state.waiting === "1" ? "script.standing.changes" : "script.standing.on_site");
  window.presslessPress.standing(standing);
  const stop = (text) => {
    stopped = true;
    status.textContent = say("script.editor.not_saved");
    document.getElementById("failure").innerHTML = text;
  };

  async function send() {
    dirty = false; status.textContent = say("script.editor.saving");
    try {
      const answer = await fetch("/page/save", {method: "POST", body: fields()});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      const reply = JSON.parse(text);
      adopt(reply);
      if (reply.hint) { status.textContent = say("script.editor.not_saved"); return; }
      document.getElementById("failure").innerHTML = reply.failure || "";
      if (reply.preview) {
        document.getElementById("preview").src = reply.preview + "?n=" + Date.now();
      }
      status.textContent = say("script.editor.saved");
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
    fetch("/page/save", {method: "POST", body: fields(), keepalive: true}).catch(() => {});
  });
  // A keepalive request carries at most 64 KiB, so a larger unsaved change
  // cannot be sent as the page goes; the browser asks before leaving instead
  // (PRESS-0135).
  window.addEventListener("beforeunload", (event) => {
    if (!stopped && dirty && new Blob([fields().toString()]).size > 60000) {
      event.preventDefault();
    }
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
    // A save queued while this runs waits for it: it would post the waiting
    // copy the publish is about to bin (PRESS-0135).
    let published;
    inFlight = new Promise((resolve) => { published = resolve; });
    const said = document.getElementById("publish-status");
    publish.disabled = true;
    said.textContent = say("script.press.publishing");
    try {
      const body = fields();
      dirty = false;
      const answer = await fetch("/page/publish", {method: "POST", body: body});
      const text = await answer.text();
      if (answer.status !== 200) { said.textContent = standing(); stop(text); return; }
      const reply = JSON.parse(text);
      // PRESS-0235: another press runs. Nothing was saved, so the change is
      // still to save, and the page asks until that press ends.
      if (reply.busy) {
        dirty = true;
        said.textContent = reply.said;
        window.presslessPress.ask();
        return;
      }
      if (reply.published) form.dataset.offSite = "0";
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      said.textContent = reply.published ? say("script.press.published")
        : reply.hint ? say("script.press.paragraphs")
        : say("script.press.not_published");
      // PRESS-0234: there is now something to see.
      const view = document.querySelector("button[data-view-site]");
      if (reply.published && view && view.dataset.viewSite) view.disabled = false;
    } catch (error) {
      said.textContent = standing(); stop("");
    } finally {
      publish.disabled = window.presslessPress.asking();
      inFlight = null;
      published();
      if (dirty && !stopped) schedule();
    }
  });

  // PRESS-0195 § 4.4: Remove and Rename ask first, save what is unsaved, then
  // press at once. Published, the page goes where the reply says, unless a
  // notice needs reading first.
  document.querySelectorAll("button[data-pages]").forEach((button) => {
    button.addEventListener("click", async () => {
      let to = "";
      if (button.dataset.pages === "rename") {
        to = window.prompt(say("script.pages.ask_rename"), "") || "";
        if (!to.trim()) return;
      } else if (!window.confirm(say("script.pages.confirm_remove"))) {
        return;
      }
      await settle();
      if (stopped) return;
      const said = document.getElementById("publish-status");
      said.textContent = say("script.press.publishing");
      try {
        const body = new URLSearchParams({kind: state.kind, name: state.name, to: to});
        const answer = await fetch("/page/" + button.dataset.pages,
                                   {method: "POST", body: body});
        const text = await answer.text();
        if (answer.status !== 200) { said.textContent = standing(); stop(text); return; }
        const reply = JSON.parse(text);
        if (reply.busy) {
          said.textContent = reply.said;
          window.presslessPress.ask();
          return;
        }
        document.getElementById("notices").innerHTML = reply.notices;
        hint.textContent = reply.hint || "";
        document.getElementById("failure").innerHTML = reply.failure || "";
        said.textContent = reply.published ? say("script.press.published")
          : reply.hint ? standing() : say("script.press.not_published");
        if (reply.published && !reply.notices) window.location.href = reply.address;
        // Read first, then on: this page's own editor may name a page that
        // has gone, and a save there would bring it back.
        else if (reply.published) {
          stopped = true;
          document.getElementById("notices").closest("dialog").addEventListener(
            "close", () => { window.location.href = reply.address; }, {once: true});
        }
      } catch (error) {
        said.textContent = standing(); stop("");
      }
    });
  });
})();
"""
