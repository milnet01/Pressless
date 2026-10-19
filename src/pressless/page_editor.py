"""The fixed pages and the furniture: a page edited on the page itself, the
code behind a button (PRESS-0014, PRESS-0260).

His changes wait in a copy of their own, beside the live file, until he
publishes that page, so a publish of anything else never sends out a
half-typed footer (docs/specs/PRESS-0014-fixed-pages.md § 3 decision 1). The
visual view saves a page as its Blocks sections, keeping every section he did
not change byte for byte (docs/specs/PRESS-0260-visual-editor.md § 4.5); the
code view writes what he typed.

Nothing is held between requests: every route reads the Store afresh, and a
save refuses a file this window did not see, as the entry editor's does.
"""
from __future__ import annotations

import dataclasses
import difflib
import hashlib
import html
import json
import re
import threading
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from pressless import (
    blocks,
    builder,
    choices,
    editor,
    files,
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
    true_colours,
)
from pressless.photographs import ACCEPT as PHOTOGRAPH_TYPES
from pressless.words import say

VISUAL = "visual"
CODE = "code"
HOME = "index"                      # the fixed page furniture previews first
NEWEST = "_newest"                  # a `show` naming his newest entry; no page name holds "_"


class SectionsUnreadable(Exception):
    """A visual save names the page's sections wrongly, or would write a file
    that does not read back as them (PRESS-0260 § 4.5)."""


# Added here rather than in face.py, which cannot import this module back.
SENTENCES[SectionsUnreadable] = Sentence(
    "failure.page_editor.SectionsUnreadable.what",
    Site.UNCHANGED,
    "failure.page_editor.SectionsUnreadable.next",
)

# PRESS-0195 § 4.2: caught where a menu is edited and said as a notice, but
# every failure type carries its sentence (docs/design.md § Errors).
SENTENCES[menu.Unusual] = Sentence(
    "failure.menu.Unusual.what",
    Site.UNCHANGED,
    "failure.menu.Unusual.next",
)
SENTENCES[menu.Refused] = Sentence(
    "failure.menu.Refused.what",
    Site.UNCHANGED,
    "failure.menu.Refused.next",
)

_LABELS = {"header": "editor.pages.header", "footer": "editor.pages.footer",
           "navigation": "editor.pages.navigation"}
_JSON = "application/json"
_HTML = "text/html; charset=utf-8"


# ------------------------------------------- the sections (PRESS-0260 § 4.5) ---


def _paths(page: blocks.Page) -> dict[tuple[int, ...], blocks.Section]:
    """Every section of `page` by its path: (i,) at the top, (i, c, j) inside."""
    found: dict[tuple[int, ...], blocks.Section] = {}
    for at, section in enumerate(page.sections):
        found[(at,)] = section
        for column, part in enumerate(section.parts):
            for inside, child in enumerate(part):
                found[(at, column, inside)] = child
    return found


def _marked(section: blocks.Section) -> bool:
    """Whether the section sits between two marks; an unmarked code run does not."""
    if section.kind != blocks.CODE:
        return True
    opening = re.match(r"<!-- pressless:([a-z]+) -->", section.source)
    return bool(opening) and section.source.endswith(f"<!-- /pressless:{opening.group(1)} -->")


def _script_json(payload: object) -> str:
    """JSON for an inline `<script type="application/json">` block, with every
    character that could open an HTML tag or comment escaped, so user content
    carried in it cannot break out of the element (OWASP A03 / CWE-116). A
    `</script>`, a `<!--` and a `<script` all begin with `<`, so escaping `<`
    (and `>`/`&` with it) closes the hole the bare `</` replacement left open."""
    return (json.dumps(payload)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def outline(page: blocks.Page) -> list[dict]:
    """§ 4.2: every section's path, kind and fields, in order, marked or not. A
    marked code section carries its HTML without its two marks."""
    shown = []
    for path, section in _paths(page).items():
        item = {"path": list(path), "kind": section.kind, "marked": _marked(section),
                "fields": dict(section.fields), "parts": len(section.parts)}
        # PRESS-0216 § 4.2: words holding a Builder placeholder are shown as
        # the code they are, since the frame shows them filled.
        if section.kind in (blocks.TEXT, blocks.HEADING) and "{{" in section.fields["html"]:
            item.update(kind=blocks.CODE, fields={})
        if item["kind"] == blocks.CODE and item["marked"]:
            source = section.source or blocks.section_html(section)
            item["code"] = source[source.index("-->") + 3:source.rindex("<!--")]
        shown.append(item)
    return shown


# PRESS-0216 § 4.1: the element a furniture file's sections area is made in.
_AREAS = {"header": "header", "footer": "footer"}


def _area(kind: str, name: str, text: str) -> str | None:
    """The file with a sections area: as it is, or adopted in memory (§ 4.1
    step 2). None where Blocks finds no area to make; BuildStopped where the
    furniture markers do not pair."""
    if blocks.read(name, text) is not None:
        return text
    element = _AREAS.get(name, "") if kind == store.FURNITURE_FOLDER else "main"
    if not element:
        return None
    return blocks.adopt(text, builder.furniture_spans(name, text), element)


def _menu(kind: str, name: str) -> bool:
    """Whether the file is the menu, whose visual view is its list of links
    (PRESS-0216 § 4.4)."""
    return kind == store.FURNITURE_FOLDER and name == "navigation"


def _path(value: object, held: dict) -> tuple[int, ...]:
    if (not isinstance(value, list) or len(value) not in (1, 3)
            or not all(isinstance(at, int) and not isinstance(at, bool) for at in value)
            or tuple(value) not in held):
        raise SectionsUnreadable(f"{value!r} names no section of the page")
    return tuple(value)


def put_sections(name: str, text: str, posted: object, removed: object) -> str:
    """§ 4.5 steps 3 to 5: the page written from the posted sections. Raises
    SectionsUnreadable, or blocks.SectionRefused from a section built anew."""
    page = blocks.read(name, text)
    if page is None or not isinstance(posted, list) or not isinstance(removed, list):
        raise SectionsUnreadable(f"the save of {name} does not name its sections")
    held = _paths(page)
    kept: list[tuple[int, ...]] = []

    def built(item: object) -> blocks.Section:
        if not isinstance(item, dict):
            raise SectionsUnreadable(f"{item!r} is not a section")
        if "keep" in item:
            path = _path(item["keep"], held)
            kept.append(path)
            return held[path]
        if "code" in item:
            if not isinstance(item["code"], str):
                raise SectionsUnreadable("a code section's HTML is not text")
            return blocks.Section(blocks.CODE, source="<!-- pressless:code -->" + item["code"]
                                  + "<!-- /pressless:code -->")
        fields, parts = item.get("fields", {}), item.get("parts", [])
        if (not isinstance(fields, dict) or not isinstance(parts, list)
                or not all(isinstance(part, list) for part in parts)):
            raise SectionsUnreadable(f"{item!r} is not a section")
        fields = dict(fields)
        for field in ("html", "caption"):
            if field in fields:
                written = blocks.inline(fields[field]) if isinstance(fields[field], str) else None
                if written is None:
                    raise blocks.SectionRefused(f"a section's {field} is not plain words and links")
                fields[field] = written
        return blocks.Section(str(item.get("kind", "")), fields,
                              tuple(tuple(built(child) for child in part) for part in parts))

    sections = tuple(built(item) for item in posted)
    gone = [_path(path, held) for path in removed]
    named = kept + gone
    if len(set(named)) != len(named):
        raise SectionsUnreadable(f"the save of {name} names a section twice")
    for path in held:
        top = path[:1]
        if path in named:
            if len(path) == 3 and top in kept:
                raise SectionsUnreadable(f"the save of {name} names a section twice")
        elif not (len(path) == 3 and top in named):
            raise SectionsUnreadable(f"the save of {name} leaves out section {list(path)}")
    gaps = tuple(page.gaps[item["keep"][0]] if isinstance(item, dict) and "keep" in item
                 and len(item["keep"]) == 1 else "\n" for item in posted) + (page.gaps[-1],)
    wanted = blocks.Page(page.before, sections, gaps, page.after)
    new = blocks.write(wanted)
    if blocks.read(name, new) != wanted:
        raise SectionsUnreadable(f"the save of {name} would not read back as its sections")
    return new


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
    face.add_page("GET", "/page/view", route(_switch))  # PRESS-0285
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
    """A page or a furniture file opens in the visual view unless the code was
    asked for (PRESS-0260 § 4.1, PRESS-0216 § 3 decision 5), so an old
    `view=words` address opens the visual view."""
    return CODE if asked == CODE else VISUAL


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
             show: str | None, *, marks: bool = False) -> tuple[str | None, str | None]:
    """§ 4.6 step 5: the preview's address, or the failure in its place.
    `marks` keeps the page's section marks, for the visual view (PRESS-0260
    § 4.2)."""
    try:
        saved = settings.load(folder)
        relative = builder.preview_html(folder, saved, folder / editor.PREVIEW_FOLDER,
                                        builder.Html(kind, name, text), show=show,
                                        photo_src=editor.photo_src, marks=marks)
    except Exception as exc:  # noqa: BLE001 -- a preview failure never undoes the save
        return None, face.fail(exc, publishing=False)
    return editor.PREVIEW_ADDRESS + relative, None


def _write(folder: Path, form: dict[str, str]) -> tuple[str, str]:
    """§ 4.6 steps 1 to 4, and PRESS-0260 § 4.5 for the visual view: write the
    waiting copy, and return the file written and its digest. Takes no lock;
    the caller holds LOCK."""
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
    if _view(kind, form.get("view", "")) == CODE:
        new = put_code(text, form.get("text", ""))
    elif _menu(kind, name):
        try:
            posted = json.loads(form.get("links", ""))
        except ValueError:
            raise menu.Refused("the menu save does not list its links") from None
        new = menu.arranged(text, posted)
    else:
        adopted = _area(kind, name, text)
        if adopted is None:
            raise SectionsUnreadable(f"the page {name} has no sections area to save into")
        try:
            posted, removed = json.loads(form.get("sections", "")), json.loads(
                form.get("removed", "[]"))
        except ValueError:
            raise SectionsUnreadable(f"the save of {name} does not name its sections") from None
        new = put_sections(name, adopted, posted, removed)
    digest = _digest(store.write_html(folder, kind, name, new, waiting=True))
    pressing.forget()  # PRESS-0235 decision 6
    return new, digest


# What a save refuses with, writing nothing (PRESS-0260 § 4.5).
_REFUSED = (store.StoreError, editor.ChangedElsewhere, builder.BuildStopped,
            SectionsUnreadable, blocks.SectionRefused, menu.Refused, menu.Unusual)


def _failed(face: Face, notices: list[str], failure: Exception) -> Reply:
    body = render_notices(notices) + face.fail(failure, publishing=False)
    return Reply(body.encode("utf-8"), _HTML, status=409)


def _json(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


@dataclasses.dataclass(frozen=True)
class _Opened:
    """What opening a file in a view gives (PRESS-0285 § 4.1)."""
    view: str
    text: str
    base: str
    waiting: bool
    show: str | None
    held: tuple[str, ...]
    entries: bool
    sections: list[dict] | None
    links: list[tuple[str, str]] | None
    photographs: tuple[str, ...]
    kept: tuple[str, ...]
    broken: str | None
    preview: str | None
    failure: str | None


def _opening(face: Face, folder: Path, kind: str, name: str, asked_view: str,
             asked_show: str, notices: list) -> _Opened:
    """§ 4.5 and PRESS-0285 § 4.1: read the file, decide the view it can have,
    and build its preview. Writes nothing, and raises `store.StoreError`. Takes
    no lock; the caller holds LOCK and captures the notices."""
    path, waiting = _read(folder, kind, name)
    text = store.read_html(path)
    base = _digest(path)
    show = _show(folder, kind, name, asked_show)
    # PRESS-0214 § 4.5: no newest entry to show a change on while the
    # journal is off.
    entries = store.list_slugs(folder, draft=False) if store.journal_on(folder) else ()
    held = store.list_html(folder, store.PAGES_FOLDER)
    view, broken = _view(kind, asked_view), None
    shown, sections, links, photographs, kept = text, None, None, (), ()
    try:
        builder.furniture_spans(name, text)
    except builder.BuildStopped as exc:
        view, broken = CODE, face.fail(exc, publishing=False)
    if view == VISUAL and _menu(kind, name):
        try:
            links = menu.links(text)
        except menu.Unusual:
            view = CODE
            notices.append(say("notice.page_editor.menu_code_only"))
    elif view == VISUAL:
        # PRESS-0260 § 4.1: adopted in memory only; nothing is written.
        shown = _area(kind, name, text)
        if shown is None:
            view, shown = CODE, text
            notices.append(say("notice.page_editor.furniture_code_only"
                               if kind == store.FURNITURE_FOLDER
                               else "notice.page_editor.code_only"))
        else:
            sections = outline(blocks.read(name, shown))
    # PRESS-0285 § 4.3: the side panel is on the page in either view.
    if broken is None:
        try:
            photographs = store.list_photographs(folder)
            kept = store.list_files(folder)
        except store.StoreError as exc:
            broken = face.fail(exc, publishing=False)
    preview, failure = _preview(face, folder, kind, name, shown, show,
                                marks=sections is not None)
    return _Opened(view, text, base, waiting, show, held, bool(entries), sections, links,
                   photographs, kept, broken, preview, failure)


def _remember(folder: Path, kind: str, name: str, request: Request) -> None:
    """PRESS-0263: the view and the page shown on, as asked."""
    changes: dict[str, object] = {"page": (kind, name)}
    if "view" in request.query:
        changes["view"] = _view(kind, request.query["view"])
    if kind == store.FURNITURE_FOLDER and "show" in request.query:
        changes["shown_on"] = request.query["show"]
    choices.remember(folder, **changes)


def _open(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str:
    """§ 4.5."""
    kind, name = request.query.get("kind", ""), request.query.get("name", "")
    # PRESS-0235 § 4.5: during a press, a page that opens the editor once it ends.
    held = pressing.holding()
    if held is not None:
        return held
    # PRESS-0263: an address that names no view, or no page to show the
    # furniture on, takes the one he chose last.
    remembered = choices.read(folder)
    with lock, face.capture() as notices:
        try:
            opened = _opening(face, folder, kind, name, request.query.get("view", remembered.view),
                              request.query.get("show", remembered.shown_on), notices)
        except store.StoreError as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return render_notices(notices) + face.fail(failure, publishing=False)
    _remember(folder, kind, name, request)
    return render_notices(notices) + _page(
        kind, name, opened, builder.stylesheets(folder), face.view_site(),
        starter.unpublished(folder), remembered.true_colours)


def _switch(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0285 § 4.2: what the other view needs, as opening it would give,
    so the switch changes view without loading the page."""
    kind, name = request.query.get("kind", ""), request.query.get("name", "")
    remembered = choices.read(folder)
    with lock, face.capture() as notices:
        try:
            opened = _opening(face, folder, kind, name, request.query.get("view", ""),
                              request.query.get("show", remembered.shown_on), notices)
        except store.StoreError as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    _remember(folder, kind, name, request)
    reply: dict[str, object] = {
        "view": opened.view, "address": _page_address(kind, name, view=opened.view),
        "base": opened.base, "waiting": opened.waiting, "broken": opened.broken or "",
        "notices": render_notices(notices), "preview": opened.preview,
        "failure": opened.failure}
    if opened.view == CODE:
        reply["text"] = opened.text
    elif opened.links is not None:
        reply["links"] = opened.links
    else:
        reply["sections"] = opened.sections
    return _json(reply)


def _page(kind: str, name: str, opened: _Opened, sheets: tuple[str, ...], visit: str,
          off_site: bool, undimmed: bool = False) -> str:
    """The editor, carrying both views; the one not shown is hidden
    (PRESS-0285 § 4.3)."""
    view, show, waiting, base, held = (opened.view, opened.show, opened.waiting,
                                       opened.base, opened.held)
    menu_file = _menu(kind, name)

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
    # PRESS-0285 § 4.3: one link to each view, in one place, the one to the
    # view shown hidden; the script swaps them.
    switch = '<p class="nav">' + "".join(
        f'<a data-switch="{to}" href="{attr(_page_address(kind, name, view=to))}"'
        f'{" hidden" if to == view else ""}>{say(key)}</a>'
        for to, key in ((CODE, "page_editor.show_code"),
                        (VISUAL, "page_editor.show_visual"))) + "</p>"
    picker = ""
    if kind == store.FURNITURE_FOLDER:
        choices = [link(say("editor.pages.home") if page == HOME else page,
                        _page_address(kind, name, show=page), page == show)
                   for page in held]
        if opened.entries:
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
<p class="nav"><a href="/">{say("face.your_writing")}</a> <span id="save-status"></span></p>
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
<div id="broken">{opened.broken or ""}</div>
{message_box("notices")}
<p id="save-hint"></p>
<form id="editor" data-kind="{attr(kind)}" data-name="{attr(name)}" data-view="{attr(view)}"
 data-show="{attr(shown)}" data-waiting="{'1' if waiting else '0'}" data-base="{attr(base)}"
 data-off-site="{'1' if off_site else '0'}" onsubmit="return false">
<p><button type="button" data-editor="publish">{say("editor.press")}</button>
 {visit}
 <button type="button" data-undo>{say("editor.undo")}</button></p>
<p id="publish-status" class="press-status" role="status"{pressed}>{attr(said)}</p>
{reshape}{_menu_panel(opened.links or [], held, hidden=view == CODE) if menu_file
          else _panel(kind, name, opened.sections, opened.photographs, opened.kept,
                      hidden=view == CODE)}
{_code_box(f'<textarea name="text" rows="24">{chr(10)}{html.escape(opened.text)}</textarea>',
           hidden=view == VISUAL)}
</form>
{message_box("failure", (opened.failure or "") + (ended or ""), forgets=True)}
<div id="undo-result"></div>
<div id="proof">{true_colours(undimmed)}
<iframe id="preview" title="{attr(say("editor.proof_title"))}" sandbox="allow-same-origin"
 src="{attr(opened.preview or 'about:blank')}"></iframe>{"" if menu_file else _drag()}</div>
<script>{_PAGE_SCRIPT}</script>
<script>{_CODE_SCRIPT}</script>
<script>{_MENU_SCRIPT if menu_file else _VISUAL_SCRIPT}</script>
<script>{editor._UNDO_SCRIPT}</script>"""


# PRESS-0265: the handle that drags the picked section, and the line that
# shows where it will land. Both sit over the frame, so nothing moves; the
# keyboard's way is the panel's Move buttons, so the handle takes no focus.
def _drag() -> str:
    return ('<button type="button" id="drag-handle" tabindex="-1" aria-hidden="true" hidden>'
            f'{say("page_editor.drag")}</button><div id="drop-line" hidden></div>')


_KINDS = (blocks.TEXT, blocks.HEADING, blocks.PICTURE, blocks.PICTURES, blocks.BUTTON,
          blocks.VIDEO, blocks.MUSIC, blocks.DOWNLOAD, blocks.COLUMNS, *blocks.PIECES,
          blocks.SCRIPT, blocks.STYLE)
# Each kind's name on the screen; the script reads the same keys by kind.
_KIND_WORDS = {
    blocks.TEXT: "script.visual.kind.text", blocks.HEADING: "script.visual.kind.heading",
    blocks.PICTURE: "script.visual.kind.picture", blocks.PICTURES: "script.visual.kind.pictures",
    blocks.BUTTON: "script.visual.kind.button", blocks.VIDEO: "script.visual.kind.video",
    blocks.MUSIC: "script.visual.kind.music", blocks.DOWNLOAD: "script.visual.kind.download",
    blocks.COLUMNS: "script.visual.kind.columns", blocks.CODE: "script.visual.kind.code",
    # PRESS-0217 § 4.1: the ready-made pieces and the writer's own script.
    blocks.SLIDESHOW: "script.visual.kind.slideshow",
    blocks.QUESTIONS: "script.visual.kind.questions",
    blocks.ENLARGE: "script.visual.kind.enlarge", blocks.TOP: "script.visual.kind.top",
    blocks.COUNTDOWN: "script.visual.kind.countdown", blocks.SCRIPT: "script.visual.kind.script",
    blocks.STYLE: "script.visual.kind.style",
}


def _panel(kind: str, name: str, sections: list[dict] | None,
           photographs: tuple[str, ...], kept: tuple[str, ...] = (), *,
           hidden: bool = False) -> str:
    """PRESS-0260 § 4.3: the side panel, every control in place from the
    start; the script shows the ones the picked section's kind uses, inside a
    panel of fixed size, so nothing beside it moves."""
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    def field(key: str, name: str, kinds: str, more: str = "") -> str:
        return (f'<label data-for="{kinds}">{say(key)} '
                f'<input data-field="{name}" autocomplete="off"{more}></label>')

    # PRESS-0216 § 4.2: one header serves every depth, so its addresses start
    # at the site's root by the Builder's own placeholder.
    up = "{{UP}}" if kind == store.FURNITURE_FOLDER else "../" if name != HOME else ""
    # § 4.6: a held photograph is offered by the address the site will use.
    choices = "".join(
        f'<option value="{attr(up + builder.web_photograph(photo))}">{html.escape(photo)}</option>'
        for photo in photographs)
    # PRESS-0197 § 4.5: each of the three sections lists the kept files of
    # its own kinds, by the address the site will use.
    lists = "".join(
        f'<datalist id="{section}-list">' + "".join(
            f'<option value="{attr(up + builder.web_file(held))}">{html.escape(held)}</option>'
            for held in kept
            if "." + held.rpartition(".")[2].lower() in accept.split(","))
        + "</datalist>" for section, accept in files.ACCEPT.items())
    kinds = "".join(f'<option value="{kind}">{say(_KIND_WORDS[kind])}</option>'
                    for kind in _KINDS)
    columns = "".join(f'<button type="button" data-act="add-to" data-column="{number}">'
                      f'{say("page_editor.panel.add_to_column", number=str(number + 1))}'
                      "</button>" for number in range(4))
    data = _script_json({"sections": sections or [], "up": up, "accept": files.ACCEPT,
                         "largest": builder.FILE_LARGEST})
    return f"""<aside id="panel" aria-label="{attr(say("page_editor.panel.title"))}"{
        " hidden" if hidden else ""}>
<script type="application/json" id="sections">{data}</script>
<p id="picked" role="status">{say("script.visual.nothing")}</p>
<div class="panel-add"><label>{say("page_editor.panel.add")}
 <select id="add-kind">{kinds}</select></label>
<label>{say("page_editor.panel.address")} <input id="add-address" autocomplete="off"
 list="photograph-list"></label>
<button type="button" data-act="add">{say("page_editor.panel.add_button")}</button>
<p id="add-where">{say("script.visual.end")}</p></div>
<div class="panel-row" data-for="text heading">
<button type="button" data-act="bold"><b>{say("page_editor.panel.bold")}</b></button>
<button type="button" data-act="italic"><i>{say("page_editor.panel.italic")}</i></button>
<button type="button" data-act="link">{say("page_editor.panel.link")}</button></div>
<label data-for="heading">{say("page_editor.panel.level")} <select data-field="level">{
    "".join(f'<option value="{level}">{level}</option>' for level in range(1, 7))}</select></label>
<datalist id="photograph-list">{choices}</datalist>
<p data-for="picture enlarge"><button type="button" data-act="photograph">{
    say("editor.add_photograph")}</button>
<input type="file" id="photograph-file" hidden
 accept="{PHOTOGRAPH_TYPES}"></p>
{field("page_editor.panel.photograph", "src", "picture enlarge", ' list="photograph-list"')}
{lists}<p data-for="video music download"><button type="button" data-act="file">{
    say("page_editor.panel.add_file")}</button>
<input type="file" id="file-file" hidden></p>
{field("page_editor.panel.address", "src", "video", ' list="video-list"')}
{field("page_editor.panel.address", "src", "music", ' list="music-list"')}
{field("page_editor.panel.address", "href", "button")}
{field("page_editor.panel.address", "href", "download", ' list="download-list"')}
{field("page_editor.panel.alt", "alt", "picture enlarge")}
{field("page_editor.panel.caption", "caption", "picture enlarge")}
{field("page_editor.panel.ends", "to", "countdown", ' type="datetime-local"')}
{field("page_editor.panel.label", "label", "button download top countdown")}
<p data-for="pictures slideshow"><button type="button" data-act="add-picture">{
    say("page_editor.panel.add_picture")}</button></p>
<p data-for="questions"><button type="button" data-act="add-question">{
    say("page_editor.panel.add_question")}</button></p>
<label data-for="columns">{say("page_editor.panel.columns")} <select data-field="count">{
    "".join(f'<option value="{count}">{count}</option>' for count in range(2, 5))}</select></label>
<p class="panel-row" data-for="columns">{columns}</p>
<label data-for="code script style">{say("page_editor.panel.code")}
{_code_box('<textarea data-field="code" rows="10" spellcheck="false"></textarea>')}</label>
<p data-for="style">{say("page_editor.panel.style_note")}</p>
<p class="panel-row"><button type="button" data-act="up">{say("page_editor.panel.move_up")}</button>
<button type="button" data-act="down">{say("page_editor.panel.move_down")}</button>
<button type="button" data-act="remove">{say("page_editor.panel.remove")}</button></p>
<p class="panel-row"><label>{say("page_editor.panel.move_to")}
 <select id="move-to"></select></label>
<button type="button" data-act="move-to">{say("page_editor.panel.move")}</button></p>
<p id="panel-said" role="status"></p>
</aside>"""


def _shape(kind: str, name: str, text: str) -> dict:
    """What a visual view's script holds of the file just written: the menu's
    links, or the sections."""
    if _menu(kind, name):
        return {"links": menu.links(text)}
    return {"sections": outline(blocks.read(name, text))}


def _menu_panel(links: list[tuple[str, str]], pages: tuple[str, ...], *,
                hidden: bool = False) -> str:
    """PRESS-0216 § 4.4: the menu's links, in order, each with its words and
    where it goes; the script fills the list from the links it is given."""
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    def place(page: str) -> str:
        address = "{{UP}}index.html" if page == HOME else f"{{{{UP}}}}pages/{page}.html"
        label = say("editor.pages.home") if page == HOME else builder.label(page)
        return f'<option value="{attr(address)}">{html.escape(label)}</option>'

    places = "".join(place(page) for page in pages)
    data = _script_json({"links": links})
    row = (f'<li class="panel-row"><label>{say("page_editor.menu.words")} '
           '<input data-link="words" autocomplete="off"></label>'
           f'<label>{say("page_editor.menu.address")} '
           '<input data-link="href" list="page-list" autocomplete="off"></label>'
           f'<button type="button" data-act="up">{say("page_editor.panel.move_up")}</button>'
           f'<button type="button" data-act="down">{say("page_editor.panel.move_down")}</button>'
           f'<button type="button" data-act="remove">{say("page_editor.panel.remove")}</button>'
           "</li>")
    return f"""<aside id="panel" aria-label="{attr(say("page_editor.menu.title"))}"{
        " hidden" if hidden else ""}>
<script type="application/json" id="links">{data}</script>
<datalist id="page-list">{places}</datalist>
<template id="link-row">{row}</template>
<ol id="menu-links"></ol>
<p><button type="button" data-act="add-link">{say("page_editor.menu.add")}</button></p>
</aside>"""


def _save(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.6."""
    form = editor._form(request)
    kind, name = form.get("kind", ""), form.get("name", "")
    visual = _view(kind, form.get("view", "")) == VISUAL
    with lock, face.capture() as notices:
        try:
            new, base = _write(folder, form)
        except _REFUSED as exc:
            failure: Exception | None = exc
        else:
            failure = None
            if kind == store.PAGES_FOLDER and not visual and stray_furniture(name, new):
                notices.append(say("notice.page_editor.stray"))
            preview, preview_failure = _preview(
                face, folder, kind, name, new, _show(folder, kind, name, form.get("show", "")),
                marks=visual)
    if failure is not None:
        return _failed(face, notices, failure)
    reply = {"waiting": True, "base": base, "preview": preview, "failure": preview_failure,
             "notices": render_notices(notices)}
    if visual:
        # § 4.5: after a save the posted list is the file's.
        reply.update(_shape(kind, name, new))
    return _json(reply)


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
                      "base": form.get("base", ""), "failure": None,
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
        except _REFUSED as exc:
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

    reply = {"published": published, "waiting": waiting, "base": base,
             "failure": failure, "notices": render_notices(notices), "busy": False}
    if _view(kind, form.get("view", "")) == VISUAL:
        # Live or waiting, the file the next save reads holds what was written.
        reply.update(_shape(kind, name, new))
    return _json(reply)


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
# waits for a save in flight and saves an unsaved change first. In the visual
# view, _VISUAL_SCRIPT supplies what is posted and is told what was saved
# (PRESS-0260 § 4.5).
_PAGE_SCRIPT = pressing.SCRIPT + """
(() => {
  const form = document.getElementById("editor");
  const state = {kind: form.dataset.kind, name: form.dataset.name, view: form.dataset.view,
                 show: form.dataset.show, waiting: form.dataset.waiting, base: form.dataset.base};
  const status = document.getElementById("save-status");
  const hint = document.getElementById("save-hint");
  let timer = null, inFlight = null, dirty = false, stopped = false;

  // The visual view's snapshot of the page, or null in the code view.
  const posting = () => state.view !== "code" && window.presslessVisual
    ? window.presslessVisual.post() : null;
  const fields = (posted = posting()) => {
    const data = new URLSearchParams();
    for (const name of ["kind", "name", "view", "show", "waiting", "base"]) {
      data.set(name, state[name]);
    }
    if (posted) {
      for (const key of ["sections", "removed", "links"]) {
        if (key in posted) data.set(key, posted[key]);
      }
    } else {
      data.set("text", form.elements.text.value);
    }
    return data;
  };
  const adopt = (reply) => {
    state.waiting = reply.waiting ? "1" : "0"; state.base = reply.base;
    document.querySelectorAll("input[name=base]").forEach((input) => { input.value = reply.base; });
    document.querySelectorAll("#standing [data-when]").forEach((part) => {
      part.hidden = part.dataset.when !== state.waiting;
    });
    document.getElementById("notices").innerHTML = reply.notices;
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
      const posted = posting();
      const answer = await fetch("/page/save", {method: "POST", body: fields(posted)});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      const reply = JSON.parse(text);
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      if (posted) {
        posted.saved(reply);
      } else if (reply.preview) {
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

  const changed = () => { dirty = true; schedule(); };
  form.addEventListener("input", changed);
  // The visual view's changes happen in the frame and the panel.
  window.presslessPage = {changed};
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

  // PRESS-0285 § 4.4: the switch changes view in place. The view being left
  // takes nothing more, what was typed is saved, and the route answers with
  // what opening the other view would show.
  const codeBox = form.elements.text.closest(".code-box");
  const panel = document.getElementById("panel");
  const frame = document.getElementById("preview");
  const part = (view) => view === "code" ? codeBox : panel;
  let switching = false;
  document.querySelectorAll("a[data-switch]").forEach((link) => {
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      if (switching || stopped) return;
      switching = true;
      part(state.view).inert = frame.inert = true;
      const free = () => {
        codeBox.inert = panel.inert = frame.inert = false;
        switching = false;
      };
      await settle();
      if (stopped) { free(); return; }
      let switched;
      inFlight = new Promise((resolve) => { switched = resolve; });
      try {
        const asked = new URLSearchParams({kind: state.kind, name: state.name,
                                           view: link.dataset.switch, show: state.show});
        const answer = await fetch("/page/view?" + asked);
        const text = await answer.text();
        if (answer.status !== 200) { stop(text); return; }
        const reply = JSON.parse(text);
        adopt(reply);
        if (reply.view !== state.view) {
          state.view = form.dataset.view = reply.view;
          codeBox.hidden = reply.view !== "code";
          panel.hidden = reply.view === "code";
          document.querySelectorAll("a[data-switch]").forEach((each) => {
            each.hidden = each.dataset.switch === reply.view;
          });
          if (reply.view === "code") {
            form.elements.text.value = reply.text;
            window.presslessCode.paint();
          } else {
            window.presslessVisual.open(reply.sections || reply.links);
          }
          history.replaceState(null, "", reply.address);
        }
        document.getElementById("broken").innerHTML = reply.broken;
        document.getElementById("failure").innerHTML = reply.failure || "";
        frame.src = reply.preview ? reply.preview + "?n=" + Date.now() : "about:blank";
      } catch (error) {
        stop("");
      } finally {
        free();
        inFlight = null;
        switched();
        if (dirty && !stopped) schedule();
      }
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
      const posted = posting();
      const body = fields(posted);
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
      if (posted) posted.saved(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      said.textContent = reply.published ? say("script.press.published")
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


def _code_box(textarea: str, *, hidden: bool = False) -> str:
    """PRESS-0261: a code box, with the coloured copy _CODE_SCRIPT paints."""
    return (f'<div class="code-box"{" hidden" if hidden else ""}>'
            f'<pre aria-hidden="true"></pre>{textarea}</div>')


# PRESS-0261: colour in the code boxes. A coloured copy of the code sits behind
# each box, whose own letters are transparent, so typing, the caret and a
# selection stay the browser's own. Colour is the only difference, since a bold
# or italic letter would be wider than the one above it. Each theme has its own
# code colours, tested readable and apart (PRESS-0283); a note takes its soft.
# HTML is coloured as tags, attributes, values and text; a <style> holds CSS,
# coloured as selectors, properties and values; a <script> stays plain.
_CODE_SCRIPT = r"""
(() => {
  const COPIED = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight",
    "letterSpacing", "wordSpacing", "tabSize", "paddingTop", "paddingRight", "paddingBottom",
    "paddingLeft", "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth"];
  const NAME = /<\/?([A-Za-z][\w:.-]*)/y;
  const ATTRIBUTE = /(\s+)|([^\s"'>\/=]+)(?:(\s*=\s*)("[^"]*"?|'[^']*'?|[^\s>]*))?|(\/)|(>)/y;
  const CSS = new RegExp(String.raw`/\*[\s\S]*?(?:\*/|$)|"(?:[^"\\\n]|\\.)*"?|` +
                         String.raw`'(?:[^'\\\n]|\\.)*'?|[{}:;]|[^{}:;"'/]+|/`, "g");

  // The pieces of `text` as [words, kind] pairs, kind "" for plain. Joined
  // they are `text` exactly, whatever it holds, or the colours would drift
  // from the letters typed over them.
  function colour(text) {
    const pieces = [];
    const put = (words, kind = "") => { if (words) pieces.push([words, kind]); };
    let at = 0;
    while (at < text.length) {
      const open = text.indexOf("<", at);
      if (open < 0) { put(text.slice(at)); break; }
      put(text.slice(at, open));
      if (text.startsWith("<!--", open)) {
        const end = text.indexOf("-->", open + 4);
        at = end < 0 ? text.length : end + 3;
        put(text.slice(open, at), "note");
        continue;
      }
      NAME.lastIndex = open;
      const name = NAME.exec(text);
      if (!name) { put("<"); at = open + 1; continue; }
      put(name[0], "tag");
      at = NAME.lastIndex;
      let closed = false;
      while (at < text.length && !closed) {
        ATTRIBUTE.lastIndex = at;
        const part = ATTRIBUTE.exec(text);
        if (!part) { put(text[at]); at += 1; continue; }
        if (part[1]) put(part[1]);
        else if (part[2]) { put(part[2], "attr"); put(part[3]); put(part[4], "value"); }
        else put(part[0], "tag");
        closed = Boolean(part[6]);
        at = ATTRIBUTE.lastIndex;
      }
      const tag = name[1].toLowerCase();
      if (closed && name[0][1] !== "/" && (tag === "style" || tag === "script")) {
        const end = text.toLowerCase().indexOf("</" + tag, at);
        const inner = text.slice(at, end < 0 ? text.length : end);
        if (tag === "style") pieces.push(...sheet(inner)); else put(inner);
        at += inner.length;
      }
    }
    return pieces;
  }

  // CSS: what comes before a "{" is a selector; in a block, what comes before
  // the first ":" of a declaration is its property and the rest its value.
  function sheet(text) {
    const pieces = [], held = [];
    let depth = 0;
    const settle = (opening) => {
      let property = depth > 0 && !opening;
      for (const [words, kind] of held) {
        if (kind) { pieces.push([words, kind]); continue; }
        if (opening) { pieces.push([words, "tag"]); continue; }
        if (property && words === ":") { property = false; pieces.push([words, ""]); continue; }
        pieces.push([words, property ? "attr" : depth > 0 && !opening ? "value" : ""]);
      }
      held.length = 0;
    };
    for (const [words] of text.matchAll(CSS)) {
      if (words === "{" || words === ";" || words === "}") {
        settle(words === "{");
        pieces.push([words, ""]);
        depth = Math.max(0, depth + (words === "{" ? 1 : words === "}" ? -1 : 0));
      } else {
        held.push([words, words.startsWith("/*") ? "note" : ""]);
      }
    }
    settle(depth === 0);
    return pieces;
  }

  function paint(box) {
    const copy = box.firstElementChild, area = box.lastElementChild;
    const made = document.createDocumentFragment();
    for (const [words, kind] of colour(area.value)) {
      if (!kind) { made.append(words); continue; }
      const span = document.createElement("span");
      span.className = "k-" + kind;
      span.textContent = words;
      made.append(span);
    }
    // A last empty line still takes its height in the box.
    if (area.value.endsWith("\n")) made.append(" ");
    copy.replaceChildren(made);
    copy.scrollTop = area.scrollTop;
    copy.scrollLeft = area.scrollLeft;
  }

  const boxes = [...document.querySelectorAll(".code-box")];
  const waiting = new Set();
  let frame = 0;
  const later = (box) => {
    waiting.add(box);
    if (!frame) frame = requestAnimationFrame(() => {
      frame = 0;
      waiting.forEach(paint);
      waiting.clear();
    });
  };
  for (const box of boxes) {
    const copy = box.firstElementChild, area = box.lastElementChild;
    const style = getComputedStyle(area);
    for (const name of COPIED) copy.style[name] = style[name];
    area.addEventListener("input", () => later(box));
    area.addEventListener("scroll", () => {
      copy.scrollTop = area.scrollTop;
      copy.scrollLeft = area.scrollLeft;
    });
    paint(box);
  }
  // A script that sets a box's value repaints it here.
  window.presslessCode = {colour, paint: () => boxes.forEach(paint)};
})();
"""


# PRESS-0216 § 4.4: the menu view. It keeps the menu's links in order, each
# with the place it held in the file last read (`at`, null for a new one), and
# posts them as the save's `links`. A new link is posted once it has words and
# an address; a kept link emptied is posted with what it last saved.
_MENU_SCRIPT = r"""
(() => {
  const list = document.getElementById("menu-links");
  const row = document.getElementById("link-row");
  const frame = document.getElementById("preview");
  const links = [];
  // PRESS-0285 § 4.5: the links are taken at load, and again at each switch
  // into this view.
  function open(given) {
    links.splice(0, links.length,
                 ...given.map(([words, href], at) => ({at, words, href, kept: {words, href}})));
    draw(null, "");
  }

  function draw(link, act) {
    list.replaceChildren(...links.map((each, at) => {
      const item = row.content.firstElementChild.cloneNode(true);
      item.querySelector("[data-link=words]").value = each.words;
      item.querySelector("[data-link=href]").value = each.href;
      item.querySelector("[data-act=up]").disabled = at === 0;
      item.querySelector("[data-act=down]").disabled = at === links.length - 1;
      item.link = each;
      return item;
    }));
    const shown = [...list.children].find((item) => item.link === link);
    if (shown) shown.querySelector(act ? "[data-act=" + act + "]" : "input").focus();
  }
  const changed = () => window.presslessPage.changed();

  list.addEventListener("input", (event) => {
    const item = event.target.closest("li");
    if (!item || !event.target.dataset.link) return;
    item.link[event.target.dataset.link] = event.target.value;
    changed();
  });
  list.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-act]");
    if (!button) return;
    const link = button.closest("li").link;
    const at = links.indexOf(link);
    const act = button.dataset.act;
    if (act === "remove") {
      links.splice(at, 1);
      draw(links[Math.min(at, links.length - 1)], "remove");
    } else {
      const to = at + (act === "up" ? -1 : 1);
      if (to < 0 || to >= links.length) return;
      links.splice(at, 1);
      links.splice(to, 0, link);
      draw(link, links.indexOf(link) === (act === "up" ? 0 : links.length - 1)
        ? (act === "up" ? "down" : "up") : act);
    }
    changed();
  });
  document.querySelector("[data-act=add-link]").addEventListener("click", () => {
    const link = {at: null, words: "", href: "", kept: null};
    links.push(link);
    draw(link, "");
  });

  function post() {
    const sent = links.filter((link) => link.kept
      || (link.words.trim() && link.href.trim()));
    const entries = sent.map((link) => ({
      at: link.at,
      words: link.words.trim() || link.kept.words,
      href: link.href.trim() || link.kept.href,
    }));
    return {
      links: JSON.stringify(entries),
      saved(reply) {
        // The file now holds the links as they were posted, in that order.
        sent.forEach((link, at) => { link.at = at; link.kept = entries[at]; });
        if (reply.preview) frame.src = reply.preview + "?n=" + Date.now();
      },
    };
  }
  window.presslessVisual = {post, open};
  open(JSON.parse(document.getElementById("links").textContent).links);
})();
"""


# PRESS-0260 § 4.2 to § 4.5: the visual view. The frame runs no script of its
# own, so this one, on the Face's page, reaches into it (§ 3 decision 9). It
# keeps a model of the page: per section its kind, its fields, its path in the
# file at `base` (null for one not saved yet), and whether he changed it.
_VISUAL_SCRIPT = r"""
(() => {
  const frame = document.getElementById("preview");
  const panel = document.getElementById("panel");
  const proof = document.getElementById("proof");
  const handle = document.getElementById("drag-handle");
  const line = document.getElementById("drop-line");
  const given = JSON.parse(document.getElementById("sections").textContent);
  const up = given.up;
  const KINDS = ["text", "heading", "picture", "pictures", "button", "video", "music",
                 "download", "columns", "slideshow", "questions", "enlarge", "top",
                 "countdown", "script", "style"];
  // The kinds holding other sections, which no column or answer holds; a row
  // of them holds pictures alone.
  const HOLDERS = ["columns", "pictures", "slideshow", "questions"];
  const ROWS = ["pictures", "slideshow"];
  const IN_COLUMN = KINDS.filter((kind) => !HOLDERS.includes(kind));
  const ADDRESSED = ["picture", "pictures", "button", "video", "music", "download",
                     "slideshow", "enlarge"];
  const YOUTUBE = new RegExp("^\\s*(?:https?:)?//(?:(?:www\\.|m\\.)?youtube(?:-nocookie)?\\.com/"
                             + "(?:watch\\?(?:.*&)?v=|embed/|shorts/)|youtu\\.be/)"
                             + "([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", "i");
  const key = (path) => JSON.stringify(path);

  // ---- the model -------------------------------------------------------
  let rev = 0;
  const node = (kind, fields, path, marked, code, parts, parent) => ({
    kind, fields: {...fields}, path, marked, code, parts, parent,
    changed: path === null, rev: 0, start: null, end: null, el: null});
  const model = [];
  const byPath = new Map();
  let removed = [];
  let picked = null;
  let destinations = [];  // where the picked section may be moved to (PRESS-0264)
  let dragging = null;  // the section being dragged, and where it would land (PRESS-0265)
  let editing = null;
  let frameSections = [];
  let waitingPreview = null;
  // PRESS-0285 § 4.5: the model is built from an outline at load, and again
  // at each switch into this view, from the file as the switch read it.
  function open(sections) {
    if (picked) show(null, false);
    model.length = 0;
    byPath.clear();
    removed = [];
    destinations = [];
    dragging = editing = waitingPreview = null;
    line.hidden = true;
    for (const item of sections) {
      const parent = item.path.length === 1 ? null : byPath.get(key(item.path.slice(0, 1)));
      const made = node(item.kind, item.fields, item.path, item.marked, item.code,
                        Array.from({length: item.parts}, () => []), parent);
      made.changed = false;
      byPath.set(key(item.path), made);
      if (parent) {
        made.column = item.path[1];
        parent.parts[item.path[1]].push(made);
      } else {
        model.push(made);
      }
    }
    frameSections = sections;
  }
  open(given.sections);

  const listOf = (item) => item.parent ? item.parent.parts[item.column] : model;
  const each = (list, visit) => list.forEach((item) => {
    visit(item);
    item.parts.forEach((part) => each(part, visit));
  });
  const touch = (item) => {
    for (let at = item; at; at = at.parent) { at.changed = true; at.rev = ++rev; }
    window.presslessPage.changed();
  };

  // ---- § 4.4: the words, read from the element's nodes ----------------
  const text = (value) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/ /g, " ");
  const allowed = (href) => /^(https?:|mailto:)/i.test(href.trim())
    || !/^[A-Za-z][A-Za-z0-9+.-]*:/.test(href.trim());
  function inline(element) {
    let out = "";
    const walk = (parent, linked) => {
      for (const child of parent.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) { out += text(child.data); continue; }
        if (child.nodeType !== Node.ELEMENT_NODE) continue;
        const tag = child.localName;
        const href = child.getAttribute("href");
        if (tag === "br") {
          out += "<br>";
        } else if (tag === "b" || tag === "strong" || tag === "i" || tag === "em") {
          const written = tag === "b" || tag === "strong" ? "strong" : "em";
          wrap("<" + written + ">", "</" + written + ">", child, linked);
        } else if (tag === "a" && !linked && href && allowed(href)) {
          wrap('<a href="' + text(href).replace(/"/g, "&quot;") + '">', "</a>", child, true);
        } else {
          walk(child, linked);
        }
      }
    };
    // An emptied Bold or Italic, as a split at its edge leaves, is dropped.
    const wrap = (opening, closing, child, linked) => {
      const at = out.length;
      walk(child, linked);
      out = out.length === at ? out : out.slice(0, at) + opening + out.slice(at) + closing;
    };
    walk(element, false);
    return out.replace(/<br>$/, "");
  }

  // ---- what is posted (§ 4.5) ------------------------------------------
  const synced = () => each(model, (item) => {
    if (item.el && item.changed) item.fields.html = inline(item.el);
  });
  function item(of) {
    if (!of.changed && of.path) return {keep: of.path};
    if (of.kind === "code") return {code: of.code};
    return {kind: of.kind, fields: {...of.fields},
            parts: of.parts.map((part) => part.map(item))};
  }
  function post() {
    synced();
    // Where each section sits in the posted list, which becomes the file's.
    const places = new Map(), revs = new Map();
    model.forEach((top, at) => {
      places.set(top, [at]);
      top.parts.forEach((part, column) => part.forEach((child, inside) => {
        places.set(child, [at, column, inside]);
      }));
    });
    each(model, (item) => revs.set(item, item.rev));
    const sections = model.map(item);
    const gone = removed.filter((item) => item.path).map((item) => item.path);
    each(model, (item) => { if (item.changed && item.path) gone.push(item.path); });
    const sent = new Set(removed.filter((item) => item.path));
    return {
      sections: JSON.stringify(sections),
      removed: JSON.stringify(gone),
      saved(reply) {
        // § 4.5: each posted section's path is its place in the posted list.
        for (const [item, path] of places) {
          item.path = path;
          if (revs.get(item) === item.rev) item.changed = false;
        }
        removed = removed.filter((item) => !sent.has(item));
        if (reply.sections) frameSections = reply.sections;
        if (reply.preview) rebuild(reply.preview + "?n=" + Date.now());
      },
    };
  }
  window.presslessVisual = {post, open};

  // ---- the frame (§ 4.2) -----------------------------------------------
  // PRESS-0217 § 4.2: a script section is shown as its code, which the
  // sandbox keeps from running, so it can be picked like any other; a style
  // section (PRESS-0273) is shown the same way, and its CSS applies too.
  const STYLE = "[data-pressless-picked]{box-shadow:0 0 0 3px #e9a23b}"
    + "[data-pressless-empty]:empty::before{content:attr(data-pressless-empty);opacity:.5}"
    + "script[data-pressless-code],style[data-pressless-code]{display:block;white-space:pre-wrap;"
    + "font:12px/1.4 monospace;border:1px #888 dashed;padding:4px;min-height:1.4em}"
    // PRESS-0287: a player's own controls keep its click, so the frame takes it.
    + "audio,video,iframe{pointer-events:none}";
  function pair() {
    const doc = frame.contentDocument;
    // PRESS-0285 § 4.5: idle while the code view shows.
    if (!doc || !doc.body || document.getElementById("editor").dataset.view === "code") return;
    const style = doc.createElement("style");
    style.textContent = STYLE;
    doc.head.appendChild(style);
    const marks = [];
    const walker = doc.createTreeWalker(doc, NodeFilter.SHOW_COMMENT);
    while (walker.nextNode()) {
      const found = /^ (\/?)pressless:([a-z]+) $/.exec(walker.currentNode.data);
      if (found) marks.push({at: walker.currentNode, closing: found[1] === "/", name: found[2]});
    }
    const partner = (from) => {
      let depth = 0;
      for (let at = from + 1; at < marks.length; at++) {
        if (marks[at].name !== marks[from].name) continue;
        if (!marks[at].closing) depth++;
        else if (depth === 0) return at;
        else depth--;
      }
      return -1;
    };
    each(model, (item) => { item.start = item.end = item.el = null; });
    const order = frameSections.filter((entry) => entry.marked);
    let next = 0, skip = -1;
    marks.forEach((mark, at) => {
      if (at <= skip || mark.closing || mark.name === "page" || mark.name === "column") return;
      const closing = partner(at);
      if (closing < 0 || next >= order.length) return;
      const entry = order[next++];
      const item = byPathNow().get(key(entry.path));
      if (!HOLDERS.includes(entry.kind)) skip = closing;
      if (!item || item.kind !== entry.kind) return;
      item.start = mark.at; item.end = marks[closing].at;
      if (item.kind === "script" || item.kind === "style") {
        const code = between(item).find((at) => at.localName === item.kind);
        if (code) code.setAttribute("data-pressless-code", "");
      }
      if (item.kind === "text" || item.kind === "heading") {
        item.el = item.start.nextSibling;
        if (item.changed && item.fields.html !== undefined) item.el.innerHTML = item.fields.html;
        // An empty one shows its kind faintly, so it can be seen and picked.
        item.el.setAttribute("data-pressless-empty", say("script.visual.kind." + item.kind));
      }
    });
    doc.addEventListener("click", clicked, true);
    doc.addEventListener("keydown", keyed);
    doc.addEventListener("input", typed);
    doc.addEventListener("paste", pasted);
    doc.addEventListener("focusout", () => { editing = null; setTimeout(settled, 0); });
    doc.defaultView.addEventListener("scroll", placeHandle);
    doc.addEventListener("focusin", (event) => {
      editing = picked && picked.el && picked.el.contains(event.target) ? picked : null;
    });
    if (picked) show(picked, false);
  }
  const byPathNow = () => {
    const found = new Map();
    each(model, (item) => { if (item.path) found.set(key(item.path), item); });
    return found;
  };
  const between = (item) => {
    const nodes = [];
    let at = item.start && item.start.nextSibling;
    for (; at && at !== item.end; at = at.nextSibling) nodes.push(at);
    return nodes;
  };
  const inside = (item, target) => item.start && item.end
    && (item.start.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING)
    && (item.end.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_PRECEDING);

  // § 4.5: never rebuilt while the caret is in a section.
  function rebuild(address) {
    waitingPreview = address;
    settled();
  }
  function settled() {
    if (editing || !waitingPreview) return;
    synced();  // the words typed since the save outlive the old frame
    const scrolled = frame.contentWindow ? frame.contentWindow.scrollY : 0;
    frame.addEventListener("load", () => {
      frame.contentWindow.scrollTo(0, scrolled);
    }, {once: true});
    frame.src = waitingPreview;
    waitingPreview = null;
  }
  frame.addEventListener("load", pair);
  if (frame.contentDocument && frame.contentDocument.readyState === "complete"
      && frame.contentDocument.body) pair();

  // ---- picking, and the side panel (§ 4.3) -----------------------------
  function clicked(event) {
    event.preventDefault();
    let found = null;
    each(model, (item) => { if (item.marked && inside(item, event.target)) found = item; });
    // PRESS-0287: a click through a player lands on what holds it, so find the
    // section by where the click fell.
    if (!found) each(model, (item) => { if (item.marked && under(item, event)) found = item; });
    if (found !== picked) show(found, Boolean(found));
  }
  const under = (item, event) => between(item).some((at) => {
    if (at.nodeType !== Node.ELEMENT_NODE) return false;
    const box = at.getBoundingClientRect();
    return event.clientX >= box.left && event.clientX <= box.right
      && event.clientY >= box.top && event.clientY <= box.bottom;
  });
  // PRESS-0280: Escape lets go of the picked section, in the page or the panel.
  function letGo(event) {
    if (event.key !== "Escape" || !picked) return false;
    event.preventDefault();
    show(null, false);
    return true;
  }
  panel.addEventListener("keydown", letGo);
  function mark(item, on) {
    for (const at of item ? between(item) : []) {
      if (at.nodeType === Node.ELEMENT_NODE) {
        if (on) at.setAttribute("data-pressless-picked", "");
        else at.removeAttribute("data-pressless-picked");
      }
    }
  }
  function show(item, focus) {
    if (picked && picked.el) picked.el.removeAttribute("contenteditable");
    mark(picked, false);
    picked = item;
    mark(picked, true);
    if (picked && picked.el) {
      picked.el.setAttribute("contenteditable", "true");
      picked.el.setAttribute("data-pressless-empty", say("script.visual.kind." + picked.kind));
      if (focus) picked.el.focus();
    }
    fill();
  }
  const field = (name) => panel.querySelector("[data-field=" + name + "]");
  const act = (name) => panel.querySelector("[data-act=" + name + "]");
  function fill() {
    const kind = picked ? picked.kind : "";
    panel.querySelectorAll("[data-for]").forEach((part) => {
      part.hidden = !part.dataset.for.split(" ").includes(kind);
    });
    document.getElementById("picked").textContent = picked
      ? say("script.visual.picked", {kind: say("script.visual.kind." + kind)})
      : say("script.visual.nothing");
    document.getElementById("panel-said").textContent = "";
    if (picked) {
      const fields = picked.fields;
      panel.querySelectorAll("[data-for]:not([hidden]) [data-field]").forEach((input) => {
        const name = input.dataset.field;
        input.value = name === "code" ? (picked.kind === "code" ? picked.code : fields.code) || ""
          : name === "count" ? String(picked.parts.length)
          : name === "src" && fields.youtube ? "https://www.youtube.com/watch?v=" + fields.youtube
          : name === "caption" ? (fields.caption || "").replace(/<[^>]*>/g, "")
              .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&")
          : fields[name] || "";
      });
      window.presslessCode.paint();
      panel.querySelectorAll("[data-act=add-to]").forEach((button) => {
        button.hidden = kind !== "columns" || Number(button.dataset.column) >= picked.parts.length;
      });
    }
    const list = picked ? listOf(picked) : model;
    const at = picked ? list.indexOf(picked) : -1;
    // PRESS-0217: a question's words stay first in it, above its answer.
    const asked = picked && picked.parent && picked.parent.kind === "questions";
    act("up").disabled = !picked || at <= (asked ? 1 : 0);
    act("down").disabled = !picked || at >= list.length - 1 || (asked && at === 0);
    act("remove").disabled = !picked;
    destinations = places(picked);
    const where = document.getElementById("move-to");
    where.replaceChildren(...(destinations.length ? destinations.map((place, at) => new Option(
      place.below ? say("script.visual.move.below")
        : say("script.visual.move.column", {number: String(place.column + 1)}), String(at)))
      : [new Option(say("script.visual.move.nowhere"), "")]));
    where.disabled = act("move-to").disabled = !destinations.length;
    const fits = !picked ? KINDS : picked.parent && ROWS.includes(picked.parent.kind) ? ["picture"]
      : picked.parent ? IN_COLUMN : KINDS;
    document.querySelectorAll("#add-kind option").forEach((option) => {
      option.disabled = !fits.includes(option.value);
    });
    const choice = document.getElementById("add-kind");
    if (choice.selectedOptions[0] && choice.selectedOptions[0].disabled) choice.value = fits[0];
    document.getElementById("add-where").textContent =
      say(picked ? "script.visual.below" : "script.visual.end");
    placeHandle();
  }

  panel.addEventListener("input", (event) => {
    const input = event.target;
    const name = input.dataset.field;
    if (!picked || !name || name === "count") return;
    const value = input.value;
    if (name === "code" && picked.kind === "code") {
      picked.code = value;
    } else if (name === "caption") {
      if (value.trim()) picked.fields.caption = text(value);
      else delete picked.fields.caption;
    } else if (name === "src" && picked.kind === "video") {
      const id = YOUTUBE.exec(value);
      picked.fields = id ? {youtube: id[1]} : {src: value};
    } else {
      picked.fields[name] = value;
    }
    touch(picked);
  });
  panel.addEventListener("change", (event) => {
    const input = event.target;
    if (!picked || input.dataset.field !== "count") return;
    const count = Number(input.value);
    if (picked.parts.slice(count).some((column) => column.length)) {
      input.value = String(picked.parts.length);
      document.getElementById("panel-said").textContent = say("script.visual.fewer_columns");
      return;
    }
    while (picked.parts.length < count) picked.parts.push([]);
    picked.parts.length = count;
    touch(picked);
    fill();
  });
  document.getElementById("add-address").addEventListener("input", (event) => {
    event.stopPropagation();  // typing an address to add is not yet a change
  });

  // Bold, Italic and Link keep the caret in the frame.
  ["bold", "italic", "link"].forEach((name) => {
    act(name).addEventListener("mousedown", (event) => event.preventDefault());
    act(name).addEventListener("click", () => format(name));
  });
  function format(name) {
    if (!picked || !picked.el) return;
    const doc = frame.contentDocument;
    if (name === "link") {
      const address = window.prompt(say("script.visual.ask_link"), "https://");
      if (!address || !allowed(address)) return;
      // With no words picked Firefox links nothing; give the link its address.
      if (doc.getSelection().isCollapsed) {
        doc.execCommand("insertHTML", false, '<a href="' + text(address).replace(/"/g, "&quot;")
          + '">' + text(address) + "</a>");
      } else {
        doc.execCommand("createLink", false, address);
      }
    } else {
      doc.execCommand(name);
    }
    touch(picked);
  }

  // ---- adding, moving, removing ----------------------------------------
  function made(kind, address, parent, column) {
    const fields = kind === "text" ? {html: ""} : kind === "heading" ? {level: "2", html: ""}
      : kind === "picture" ? {src: address, alt: ""}
      : kind === "button" || kind === "download" ? {href: address, label: address}
      : kind === "video" ? (YOUTUBE.exec(address) ? {youtube: YOUTUBE.exec(address)[1]}
                            : {src: address})
      : kind === "music" ? {src: address}
      : kind === "enlarge" ? {src: address, alt: ""}
      : kind === "top" ? {label: say("script.visual.top_label")}
      : kind === "countdown" ? {to: weekAhead(), label: ""}
      : kind === "script" || kind === "style" ? {code: ""} : {};
    const parts = kind === "columns" ? [[], []]
      : ROWS.includes(kind) || kind === "questions" ? [[]] : [];
    const item = node(kind, fields, null, true, undefined, parts, parent);
    item.column = column;
    if (ROWS.includes(kind)) item.parts[0].push(made("picture", address, item, 0));
    if (kind === "questions") item.parts[0] = question(item, 0);
    return item;
  }
  // A question's words and its answer, each a paragraph to type into.
  const question = (holder, column) => [made("text", "", holder, column),
                                        made("text", "", holder, column)];
  // A countdown starts a week from now, to the minute, in local time.
  function weekAhead() {
    const when = new Date(Date.now() + 7 * 86400000);
    const two = (number) => String(number).padStart(2, "0");
    return when.getFullYear() + "-" + two(when.getMonth() + 1) + "-" + two(when.getDate())
      + "T" + two(when.getHours()) + ":" + two(when.getMinutes());
  }
  function place(item, list, at) {
    list.splice(at, 0, item);
    if (item.kind !== "text" && item.kind !== "heading") return;
    const doc = frame.contentDocument;
    const before = list[at - 1], after = list[at + 1];
    let anchor = null, where = null;
    if (before && before.end) { anchor = before.end; where = "after"; }
    else if (after && after.start) { anchor = after.start; where = "before"; }
    else if (!item.parent && doc) {
      const walker = doc.createTreeWalker(doc, NodeFilter.SHOW_COMMENT);
      while (walker.nextNode()) {
        if (walker.currentNode.data === " /pressless:page ") anchor = walker.currentNode;
      }
      where = "before";
    }
    if (!anchor) return;
    item.start = doc.createComment(" pressless:" + item.kind + " ");
    item.end = doc.createComment(" /pressless:" + item.kind + " ");
    item.el = doc.createElement(item.kind === "text" ? "p" : "h" + item.fields.level);
    const fragment = doc.createDocumentFragment();
    fragment.append(item.start, item.el, item.end);
    if (where === "after") anchor.after(fragment); else anchor.before(fragment);
  }
  // Adds below `at`, or at the page's end; with a column, into that column of
  // `at`, which is a columns section.
  function addTo(kind, address, at, column) {
    document.getElementById("add-address").value = "";
    if (column !== undefined) {
      at.parts[column].push(made(kind, address, at, column));
      touch(at);
      return;
    }
    const parent = at ? at.parent : null;
    const list = at ? listOf(at) : model;
    const item = made(kind, address, parent, at ? at.column : undefined);
    place(item, list, at ? list.indexOf(at) + 1 : list.length);
    touch(parent || item);
    item.changed = true;
    show(item, true);
  }
  // PRESS-0282: a section playing or offering a file is added by choosing
  // the file, so Add with no address asks for it, and the upload's answer
  // is the address. Every other kind needs its address typed.
  const FILED = ["video", "music", "download"];
  let adding = null;
  function asked(kind, address, column) {
    if (!ADDRESSED.includes(kind) || address) return false;
    if (FILED.includes(kind)) {
      adding = {kind, at: picked, column};
      filer.accept = given.accept[kind];
      filer.value = "";
      filer.click();
    } else {
      document.getElementById("panel-said").textContent = say("script.visual.needs_address");
    }
    return true;
  }
  act("add").addEventListener("click", () => {
    const kind = document.getElementById("add-kind").value;
    const address = document.getElementById("add-address").value.trim();
    if (!asked(kind, address)) addTo(kind, address, picked);
  });
  panel.querySelectorAll("[data-act=add-to]").forEach((button) => {
    button.addEventListener("click", () => {
      const kind = document.getElementById("add-kind").value;
      const address = document.getElementById("add-address").value.trim();
      if (!picked || !IN_COLUMN.includes(kind)) return;
      const column = Number(button.dataset.column);
      if (!asked(kind, address, column)) addTo(kind, address, picked, column);
    });
  });
  act("add-picture").addEventListener("click", () => {
    const address = document.getElementById("add-address").value.trim()
      || (field("src") && field("src").value.trim());
    if (!picked || !ROWS.includes(picked.kind)) return;
    if (!address) {
      document.getElementById("panel-said").textContent = say("script.visual.needs_address");
      return;
    }
    picked.parts[0].push(made("picture", address, picked, 0));
    document.getElementById("add-address").value = "";
    touch(picked);
  });
  act("add-question").addEventListener("click", () => {
    if (!picked || picked.kind !== "questions") return;
    picked.parts.push(question(picked, picked.parts.length));
    touch(picked);
  });
  function move(by) {
    if (!picked) return;
    const list = listOf(picked);
    const at = list.indexOf(picked), to = at + by;
    if (to < 0 || to >= list.length) return;
    const other = list[to];
    list.splice(at, 1);
    list.splice(to, 0, picked);
    if (picked.start && other.start) {
      const nodes = [picked.start, ...between(picked), picked.end];
      if (by < 0) other.start.before(...nodes); else other.end.after(...nodes);
    }
    if (picked.parent) touch(picked.parent); else window.presslessPage.changed();
    fill();
  }
  act("up").addEventListener("click", () => move(-1));
  act("down").addEventListener("click", () => move(1));

  // PRESS-0264: a section in a column moves to another column of the same
  // columns, or below them; one on the page moves into a column of the
  // columns right above it, so the two moves undo each other. It goes at the
  // end of a column.
  function places(item) {
    if (!item || !IN_COLUMN.includes(item.kind)) return [];
    if (item.parent && item.parent.kind === "columns") {
      return [...item.parent.parts.map((_, column) => ({columns: item.parent, column}))
        .filter((place) => place.column !== item.column), {below: item.parent}];
    }
    if (item.parent) return [];
    const above = model[model.indexOf(item) - 1];
    return above && above.kind === "columns"
      ? above.parts.map((_, column) => ({columns: above, column})) : [];
  }
  // The element a column's sections sit in, in the frame.
  function holder(columns, column) {
    const box = between(columns).find((at) => at.nodeType === Node.ELEMENT_NODE);
    const opening = box ? [...box.childNodes].filter((at) => at.nodeType === Node.COMMENT_NODE
      && at.data === " pressless:column ") : [];
    return opening[column] ? opening[column].nextSibling : null;
  }
  act("move-to").addEventListener("click", () => {
    const place = destinations[Number(document.getElementById("move-to").value)];
    if (!picked || !place) return;
    const item = picked;
    const nodes = item.start ? [item.start, ...between(item), item.end] : [];
    const list = listOf(item);
    list.splice(list.indexOf(item), 1);
    if (place.below) {
      model.splice(model.indexOf(place.below) + 1, 0, item);
      item.parent = null;
      item.column = undefined;
      if (nodes.length && place.below.end) place.below.end.after(...nodes);
    } else {
      place.columns.parts[place.column].push(item);
      item.parent = place.columns;
      item.column = place.column;
      const inside = holder(place.columns, place.column);
      if (nodes.length && inside) inside.append(...nodes);
    }
    touch(place.columns || place.below);
    fill();
  });
  function drop(item) {
    const list = listOf(item);
    list.splice(list.indexOf(item), 1);
    removed.push(item);
    if (item.start) [item.start, ...between(item), item.end].forEach((at) => at.remove());
    if (item.parent) touch(item.parent); else window.presslessPage.changed();
  }
  act("remove").addEventListener("click", () => {
    if (!picked) return;
    const gone = picked;
    show(null, false);
    const holder = gone.parent;
    if (holder && holder.kind === "questions" && listOf(gone).indexOf(gone) === 0) {
      // A question's words go with the whole question, answer and all.
      const column = gone.column;
      [...holder.parts[column]].forEach(drop);
      holder.parts.splice(column, 1);
      holder.parts.slice(column).forEach((part, at) => part.forEach((item) => {
        item.column = column + at;
      }));
      touch(holder);
    } else {
      drop(gone);
    }
    fill();
  });

  // ---- PRESS-0265: dragging a section into place -----------------------
  // The handle sits at the picked section's top right corner. Dragged, a line shows
  // where the section will land: before or after the section under the
  // pointer, in that section's list, where its kind fits there; else beside
  // the columns or row holding it. A row of pictures keeps its last picture.
  function box(item) {
    const rects = between(item).filter((at) => at.nodeType === Node.ELEMENT_NODE)
      .map((at) => at.getBoundingClientRect()).filter((at) => at.width || at.height);
    if (!rects.length) return null;
    return {top: Math.min(...rects.map((at) => at.top)),
            bottom: Math.max(...rects.map((at) => at.bottom)),
            left: Math.min(...rects.map((at) => at.left)),
            right: Math.max(...rects.map((at) => at.right))};
  }
  // Where the page in the frame starts, measured from the proof.
  function origin() {
    const outer = frame.getBoundingClientRect(), holder = proof.getBoundingClientRect();
    return {x: outer.left - holder.left + frame.clientLeft,
            y: outer.top - holder.top + frame.clientTop, height: frame.clientHeight};
  }
  function placeHandle() {
    if (!handle) return;
    const at = picked && !dragging ? box(picked) : null;
    const from = origin();
    handle.hidden = !at || at.bottom < 0 || at.top > from.height;
    if (handle.hidden) return;
    // At its top right, where the line above most often ends short.
    handle.style.left = Math.max(0, Math.min(at.right, frame.clientWidth) - handle.offsetWidth)
      + from.x + "px";
    handle.style.top = Math.max(0, at.top - handle.offsetHeight) + from.y + "px";
  }
  const fits = (item, owner) => !owner || (ROWS.includes(owner.kind)
    ? item.kind === "picture" : IN_COLUMN.includes(item.kind));
  function landing(item, x, y) {
    const doc = frame.contentDocument;
    const under = doc && doc.elementFromPoint(x, y);
    if (!under) return null;
    let target = null;
    each(model, (at) => { if (at.marked && inside(at, under)) target = at; });
    while (target && !fits(item, target.parent)) target = target.parent;
    for (let at = target; at; at = at.parent) if (at === item) return null;
    if (!target) return null;
    const edges = box(target);
    if (!edges) return null;
    const after = y > (edges.top + edges.bottom) / 2;
    const list = listOf(target);
    const next = list[list.indexOf(target) + (after ? 1 : -1)];
    if (next === item) return null;
    const row = item.parent && ROWS.includes(item.parent.kind) ? item.parent : null;
    if (row && row !== target.parent && row.parts[0].length === 1) return null;
    return {target, after, edges};
  }
  function relocate(item, target, after) {
    const from = item.parent;
    const nodes = item.start ? [item.start, ...between(item), item.end] : [];
    const old = listOf(item);
    old.splice(old.indexOf(item), 1);
    const list = listOf(target);
    list.splice(list.indexOf(target) + (after ? 1 : 0), 0, item);
    item.parent = target.parent;
    item.column = target.column;
    if (nodes.length && target.start) {
      if (after) target.end.after(...nodes); else target.start.before(...nodes);
    }
    for (const owner of new Set([from, target.parent])) {
      if (owner) touch(owner); else window.presslessPage.changed();
    }
    fill();
  }
  if (handle) {
    handle.addEventListener("pointerdown", (event) => {
      if (!picked) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      dragging = {item: picked, landing: null};
    });
    handle.addEventListener("pointermove", (event) => {
      if (!dragging) return;
      const from = origin(), holder = proof.getBoundingClientRect();
      const found = landing(dragging.item, event.clientX - holder.left - from.x,
                            event.clientY - holder.top - from.y);
      dragging.landing = found;
      line.hidden = !found;
      if (!found) return;
      line.style.left = found.edges.left + from.x + "px";
      line.style.width = found.edges.right - found.edges.left + "px";
      line.style.top = (found.after ? found.edges.bottom : found.edges.top) + from.y - 1 + "px";
    });
    const stop = (event) => {
      if (!dragging) return;
      const {item, landing: found} = dragging;
      dragging = null;
      line.hidden = true;
      if (found && event.type === "pointerup") relocate(item, found.target, found.after);
      placeHandle();
    };
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
    window.addEventListener("resize", placeHandle);
  }

  // ---- typing (§ 4.4) --------------------------------------------------
  function typed(event) {
    if (picked && picked.el && picked.el.contains(event.target)) touch(picked);
    placeHandle();
  }
  function pasted(event) {
    if (!picked || !picked.el) return;
    event.preventDefault();
    const words = (event.clipboardData.getData("text/plain") || "").replace(/\s*\n\s*/g, " ");
    frame.contentDocument.execCommand("insertText", false, words);
  }
  function keyed(event) {
    if (letGo(event)) return;
    if (!picked || !picked.el || !picked.el.contains(event.target)) return;
    const doc = frame.contentDocument;
    const selection = doc.getSelection();
    if ((event.ctrlKey || event.metaKey) && ["b", "i", "k"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      format({b: "bold", i: "italic", k: "link"}[event.key.toLowerCase()]);
      return;
    }
    if (event.key === "Enter" && event.shiftKey) {
      event.preventDefault();
      doc.execCommand("insertLineBreak");
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (!selection.rangeCount) return;
      const range = selection.getRangeAt(0);
      range.deleteContents();
      const rest = doc.createRange();
      rest.setStart(range.startContainer, range.startOffset);
      rest.setEnd(picked.el, picked.el.childNodes.length);
      const after = rest.extractContents();
      const list = listOf(picked);
      const item = made("text", "", picked.parent, picked.column);
      touch(picked);
      place(item, list, list.indexOf(picked) + 1);
      if (item.el) item.el.append(after);
      item.fields.html = item.el ? inline(item.el) : "";
      touch(picked.parent || item);
      item.changed = true;
      show(item, true);
      if (item.el) selection.collapse(item.el, 0);
      return;
    }
    if (event.key === "Backspace" && picked.kind === "text" && selection.isCollapsed
        && selection.rangeCount) {
      const head = doc.createRange();
      head.setStart(picked.el, 0);
      head.setEnd(selection.anchorNode, selection.anchorOffset);
      if (head.toString() !== "" || head.cloneContents().querySelector("br, img")) return;
      event.preventDefault();
      const list = listOf(picked);
      const above = list[list.indexOf(picked) - 1];
      if (!above || above.kind !== "text" || !above.el) return;
      const joined = above.el.childNodes.length;
      above.el.append(...picked.el.childNodes);
      const gone = picked;
      touch(above);
      show(above, true);
      drop(gone);
      selection.collapse(above.el, joined);
    }
  }

  // ---- a photograph Pressless holds (§ 4.6) ------------------------------
  const chooser = document.getElementById("photograph-file");
  act("photograph").addEventListener("click", () => { chooser.value = ""; chooser.click(); });
  chooser.addEventListener("change", async () => {
    const file = chooser.files[0];
    if (!file || !picked || !["picture", "enlarge"].includes(picked.kind)) return;
    const answer = await fetch("/photograph?name=" + encodeURIComponent(file.name),
                               {method: "POST", body: file});
    const reply = await answer.text();
    if (answer.status !== 200) { document.getElementById("failure").innerHTML = reply; return; }
    const name = JSON.parse(reply).name;
    const address = up + "photographs/" + encodeURIComponent(name);
    const option = document.createElement("option");
    option.value = address; option.textContent = name;
    document.getElementById("photograph-list").append(option);
    picked.fields.src = address;
    field("src").value = address;
    touch(picked);
  });

  // ---- a kept file (PRESS-0197 § 4.5) ------------------------------------
  const filer = document.getElementById("file-file");
  act("file").addEventListener("click", () => {
    if (!picked || !given.accept[picked.kind]) return;
    adding = null;
    filer.accept = given.accept[picked.kind];
    filer.value = "";
    filer.click();
  });
  filer.addEventListener("cancel", () => { adding = null; });
  filer.addEventListener("change", async () => {
    const file = filer.files[0];
    const adds = adding;
    adding = null;
    const kind = adds ? adds.kind : picked && picked.kind;
    if (!file || !given.accept[kind]) return;
    const said = document.getElementById("panel-said");
    if (file.size > given.largest) {
      said.textContent = say("script.visual.file_too_large");
      return;
    }
    const answer = await fetch("/file?name=" + encodeURIComponent(file.name),
                               {method: "POST", body: file});
    const reply = await answer.text();
    if (answer.status !== 200) { document.getElementById("failure").innerHTML = reply; return; }
    const name = JSON.parse(reply).name;
    const address = up + "files/" + encodeURIComponent(name);
    const suffix = name.slice(name.lastIndexOf("."));
    Object.keys(given.accept).forEach((section) => {
      const list = document.getElementById(section + "-list");
      if (!given.accept[section].split(",").includes(suffix)
          || [...list.options].some((option) => option.value === address)) return;
      const option = document.createElement("option");
      option.value = address; option.textContent = name;
      list.append(option);
    });
    if (adds) {
      addTo(adds.kind, address, adds.at, adds.column);
      return;
    }
    if (!picked || picked.kind !== kind) return;
    const place = picked.kind === "download" ? "href" : "src";
    if (picked.kind === "video") picked.fields = {src: address};
    else picked.fields[place] = address;
    panel.querySelector("[data-for]:not([hidden]) [data-field=" + place + "]").value = address;
    touch(picked);
  });

  fill();
})();
"""
