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


def outline(page: blocks.Page) -> list[dict]:
    """§ 4.2: every section's path, kind and fields, in order, marked or not. A
    marked code section carries its HTML without its two marks."""
    shown = []
    for path, section in _paths(page).items():
        item = {"path": list(path), "kind": section.kind, "marked": _marked(section),
                "fields": dict(section.fields), "parts": len(section.parts)}
        if section.kind == blocks.CODE and item["marked"]:
            opening = section.source.index("-->") + 3
            item["code"] = section.source[opening:section.source.rindex("<!--")]
        shown.append(item)
    return shown


def _area(name: str, text: str) -> str | None:
    """The file with a sections area: as it is, or adopted in memory (§ 4.1
    step 2). None where Blocks finds no area to make; BuildStopped where the
    furniture markers do not pair."""
    if blocks.read(name, text) is not None:
        return text
    return blocks.adopt(text, builder.furniture_spans(name, text))


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
    """§ 4.4: the furniture always opens in the code view (§ 3 decision 5); a
    page in the visual view unless the code was asked for (PRESS-0260 § 4.1),
    so an old `view=words` address opens the visual view."""
    if kind == store.FURNITURE_FOLDER:
        return CODE
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
    else:
        adopted = _area(name, text)
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
            SectionsUnreadable, blocks.SectionRefused)


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
    # PRESS-0263: an address that names no view, or no page to show the
    # furniture on, takes the one he chose last.
    remembered = choices.read(folder)
    asked_view = request.query.get("view", remembered.view)
    asked_show = request.query.get("show", remembered.shown_on)
    with lock, face.capture() as notices:
        try:
            path, waiting = _read(folder, kind, name)
            text = store.read_html(path)
            base = _digest(path)
            show = _show(folder, kind, name, asked_show)
            # PRESS-0214 § 4.5: no newest entry to show a change on while the
            # journal is off.
            entries = (store.list_slugs(folder, draft=False)
                       if store.journal_on(folder) else ())
            held = store.list_html(folder, store.PAGES_FOLDER)
        except store.StoreError as exc:
            failure: Exception | None = exc
        else:
            failure = None
            view = _view(kind, asked_view)
            shown, sections, photographs = text, None, ()
            try:
                builder.furniture_spans(name, text)
            except builder.BuildStopped as exc:
                view, broken = CODE, face.fail(exc, publishing=False)
            if view == VISUAL:
                # PRESS-0260 § 4.1: adopted in memory only; nothing is written.
                shown = _area(name, text)
                if shown is None:
                    view, shown = CODE, text
                    notices.append(say("notice.page_editor.code_only"))
                else:
                    sections = outline(blocks.read(name, shown))
                    try:
                        photographs = store.list_photographs(folder)
                    except store.StoreError as exc:
                        broken = face.fail(exc, publishing=False)
            preview, preview_failure = _preview(face, folder, kind, name, shown, show,
                                                marks=view == VISUAL)
    if failure is not None:
        return render_notices(notices) + face.fail(failure, publishing=False)
    changes: dict[str, object] = {"page": (kind, name)}
    if kind == store.PAGES_FOLDER and "view" in request.query:
        changes["view"] = _view(kind, request.query["view"])
    if kind == store.FURNITURE_FOLDER and "show" in request.query:
        changes["shown_on"] = request.query["show"]
    choices.remember(folder, **changes)
    return render_notices(notices) + _page(
        kind, name, view, show, waiting, base, text, held, bool(entries), broken,
        preview, preview_failure, builder.stylesheets(folder),
        face.view_site(), starter.unpublished(folder), sections, photographs,
        remembered.true_colours)


def _page(kind: str, name: str, view: str, show: str | None, waiting: bool, base: str,
          box: str, held: tuple[str, ...], has_entries: bool, broken: str | None,
          preview: str | None, failure: str | None, sheets: tuple[str, ...],
          visit: str, off_site: bool, sections: list[dict] | None = None,
          photographs: tuple[str, ...] = (), undimmed: bool = False) -> str:
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
        other, label = ((CODE, say("page_editor.show_code")) if view == VISUAL
                        else (VISUAL, say("page_editor.show_visual")))
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
{reshape}{_panel(name, sections, photographs) if view == VISUAL else
          _code_box(f'<textarea name="text" rows="24">{chr(10)}{html.escape(box)}</textarea>')}
</form>
{message_box("failure", (failure or "") + (ended or ""), forgets=True)}
<div id="undo-result"></div>
<div id="proof">{true_colours(undimmed)}
<iframe id="preview" title="{attr(say("editor.proof_title"))}" sandbox="allow-same-origin"
 src="{attr(preview or 'about:blank')}"></iframe></div>
<script>{_PAGE_SCRIPT}</script>
<script>{_CODE_SCRIPT}</script>
{f"<script>{_VISUAL_SCRIPT}</script>" if view == VISUAL else ""}
<script>{editor._UNDO_SCRIPT}</script>"""


_KINDS = (blocks.TEXT, blocks.HEADING, blocks.PICTURE, blocks.PICTURES, blocks.BUTTON,
          blocks.VIDEO, blocks.MUSIC, blocks.DOWNLOAD, blocks.COLUMNS)
# Each kind's name on the screen; the script reads the same keys by kind.
_KIND_WORDS = {
    blocks.TEXT: "script.visual.kind.text", blocks.HEADING: "script.visual.kind.heading",
    blocks.PICTURE: "script.visual.kind.picture", blocks.PICTURES: "script.visual.kind.pictures",
    blocks.BUTTON: "script.visual.kind.button", blocks.VIDEO: "script.visual.kind.video",
    blocks.MUSIC: "script.visual.kind.music", blocks.DOWNLOAD: "script.visual.kind.download",
    blocks.COLUMNS: "script.visual.kind.columns", blocks.CODE: "script.visual.kind.code",
}


def _panel(name: str, sections: list[dict] | None, photographs: tuple[str, ...]) -> str:
    """PRESS-0260 § 4.3: the side panel, every control in place from the
    start; the script shows the ones the picked section's kind uses, inside a
    panel of fixed size, so nothing beside it moves."""
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    def field(key: str, name: str, kinds: str, more: str = "") -> str:
        return (f'<label data-for="{kinds}">{say(key)} '
                f'<input data-field="{name}" autocomplete="off"{more}></label>')

    up = "../" if name != HOME else ""
    # § 4.6: a held photograph is offered by the address the site will use.
    choices = "".join(
        f'<option value="{attr(up + builder.web_photograph(photo))}">{html.escape(photo)}</option>'
        for photo in photographs)
    kinds = "".join(f'<option value="{kind}">{say(_KIND_WORDS[kind])}</option>'
                    for kind in _KINDS)
    columns = "".join(f'<button type="button" data-act="add-to" data-column="{number}">'
                      f'{say("page_editor.panel.add_to_column", number=str(number + 1))}'
                      "</button>" for number in range(4))
    data = json.dumps({"sections": sections or [], "up": up}).replace("</", "<\\/")
    return f"""<aside id="panel" aria-label="{attr(say("page_editor.panel.title"))}">
<script type="application/json" id="sections">{data}</script>
<p id="picked" role="status">{say("script.visual.nothing")}</p>
<div class="panel-row" data-for="text heading">
<button type="button" data-act="bold"><b>{say("page_editor.panel.bold")}</b></button>
<button type="button" data-act="italic"><i>{say("page_editor.panel.italic")}</i></button>
<button type="button" data-act="link">{say("page_editor.panel.link")}</button></div>
<label data-for="heading">{say("page_editor.panel.level")} <select data-field="level">{
    "".join(f'<option value="{level}">{level}</option>' for level in range(1, 7))}</select></label>
<datalist id="photograph-list">{choices}</datalist>
<p data-for="picture"><button type="button" data-act="photograph">{
    say("editor.add_photograph")}</button>
<input type="file" id="photograph-file" hidden
 accept="image/jpeg,image/png,image/webp,image/gif"></p>
{field("page_editor.panel.photograph", "src", "picture", ' list="photograph-list"')}
{field("page_editor.panel.address", "src", "video music")}
{field("page_editor.panel.address", "href", "button download")}
{field("page_editor.panel.alt", "alt", "picture")}
{field("page_editor.panel.caption", "caption", "picture")}
{field("page_editor.panel.label", "label", "button download")}
<p data-for="pictures"><button type="button" data-act="add-picture">{
    say("page_editor.panel.add_picture")}</button></p>
<label data-for="columns">{say("page_editor.panel.columns")} <select data-field="count">{
    "".join(f'<option value="{count}">{count}</option>' for count in range(2, 5))}</select></label>
<p class="panel-row" data-for="columns">{columns}</p>
<label data-for="code">{say("page_editor.panel.code")}
{_code_box('<textarea data-field="code" rows="10" spellcheck="false"></textarea>')}</label>
<div class="panel-add"><label>{say("page_editor.panel.add")}
 <select id="add-kind">{kinds}</select></label>
<label>{say("page_editor.panel.address")} <input id="add-address" autocomplete="off"
 list="photograph-list"></label>
<button type="button" data-act="add">{say("page_editor.panel.add_button")}</button>
<p id="add-where">{say("script.visual.end")}</p></div>
<p class="panel-row"><button type="button" data-act="up">{say("page_editor.panel.move_up")}</button>
<button type="button" data-act="down">{say("page_editor.panel.move_down")}</button>
<button type="button" data-act="remove">{say("page_editor.panel.remove")}</button></p>
<p id="panel-said" role="status"></p>
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
        reply["sections"] = outline(blocks.read(name, new))
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
        reply["sections"] = outline(blocks.read(name, new))
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
  const posting = () => window.presslessVisual ? window.presslessVisual.post() : null;
  const fields = (posted = posting()) => {
    const data = new URLSearchParams();
    for (const name of ["kind", "name", "view", "show", "waiting", "base"]) {
      data.set(name, state[name]);
    }
    if (posted) {
      data.set("sections", posted.sections);
      data.set("removed", posted.removed);
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


def _code_box(textarea: str) -> str:
    """PRESS-0261: a code box, with the coloured copy _CODE_SCRIPT paints."""
    return f'<div class="code-box"><pre aria-hidden="true"></pre>{textarea}</div>'


# PRESS-0261: colour in the code boxes. A coloured copy of the code sits behind
# each box, whose own letters are transparent, so typing, the caret and a
# selection stay the browser's own. Colour is the only difference, since a bold
# or italic letter would be wider than the one above it. The colours are the
# theme's ink, soft and amber-ink, which every theme is tested to keep readable.
# HTML is coloured as tags, attributes and text; a <style> holds CSS, coloured
# as selectors, properties and values; a <script> stays plain.
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
        else if (part[2]) { put(part[2], "attr"); put(part[3]); put(part[4]); }
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
        pieces.push([words, property ? "attr" : ""]);
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


# PRESS-0260 § 4.2 to § 4.5: the visual view. The frame runs no script of its
# own, so this one, on the Face's page, reaches into it (§ 3 decision 9). It
# keeps a model of the page: per section its kind, its fields, its path in the
# file at `base` (null for one not saved yet), and whether he changed it.
_VISUAL_SCRIPT = r"""
(() => {
  const frame = document.getElementById("preview");
  const panel = document.getElementById("panel");
  const given = JSON.parse(document.getElementById("sections").textContent);
  const up = given.up;
  const KINDS = ["text", "heading", "picture", "pictures", "button", "video", "music",
                 "download", "columns"];
  const IN_COLUMN = KINDS.filter((kind) => kind !== "columns" && kind !== "pictures");
  const ADDRESSED = ["picture", "pictures", "button", "video", "music", "download"];
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
  for (const item of given.sections) {
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
  let removed = [];
  let picked = null;
  let editing = null;
  let frameSections = given.sections;
  let waitingPreview = null;

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
  window.presslessVisual = {post};

  // ---- the frame (§ 4.2) -----------------------------------------------
  const STYLE = "[data-pressless-picked]{box-shadow:0 0 0 3px #e9a23b}"
    + "[data-pressless-empty]:empty::before{content:attr(data-pressless-empty);opacity:.5}";
  function pair() {
    const doc = frame.contentDocument;
    if (!doc || !doc.body) return;
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
      if (entry.kind !== "columns" && entry.kind !== "pictures") skip = closing;
      if (!item || item.kind !== entry.kind) return;
      item.start = mark.at; item.end = marks[closing].at;
      if (item.kind === "text" || item.kind === "heading") {
        item.el = item.start.nextSibling;
        if (item.changed && item.fields.html !== undefined) item.el.innerHTML = item.fields.html;
      }
    });
    doc.addEventListener("click", clicked, true);
    doc.addEventListener("keydown", keyed);
    doc.addEventListener("input", typed);
    doc.addEventListener("paste", pasted);
    doc.addEventListener("focusout", () => { editing = null; setTimeout(settled, 0); });
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
    if (found && found !== picked) show(found, true);
  }
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
        input.value = name === "code" ? picked.code || ""
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
    act("up").disabled = !picked || at <= 0;
    act("down").disabled = !picked || at >= list.length - 1;
    act("remove").disabled = !picked;
    const fits = !picked ? KINDS : picked.parent && picked.parent.kind === "pictures" ? ["picture"]
      : picked.parent ? IN_COLUMN : KINDS;
    document.querySelectorAll("#add-kind option").forEach((option) => {
      option.disabled = !fits.includes(option.value);
    });
    const choice = document.getElementById("add-kind");
    if (choice.selectedOptions[0] && choice.selectedOptions[0].disabled) choice.value = fits[0];
    document.getElementById("add-where").textContent =
      say(picked ? "script.visual.below" : "script.visual.end");
  }

  panel.addEventListener("input", (event) => {
    const input = event.target;
    const name = input.dataset.field;
    if (!picked || !name || name === "count") return;
    const value = input.value;
    if (name === "code") {
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
      doc.execCommand("createLink", false, address);
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
      : kind === "music" ? {src: address} : {};
    const parts = kind === "columns" ? [[], []] : kind === "pictures" ? [[]] : [];
    const item = node(kind, fields, null, true, undefined, parts, parent);
    item.column = column;
    if (kind === "pictures") item.parts[0].push(made("picture", address, item, 0));
    return item;
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
  act("add").addEventListener("click", () => {
    const kind = document.getElementById("add-kind").value;
    const address = document.getElementById("add-address").value.trim();
    if (ADDRESSED.includes(kind) && !address) {
      document.getElementById("panel-said").textContent = say("script.visual.needs_address");
      return;
    }
    const parent = picked ? picked.parent : null;
    const list = picked ? listOf(picked) : model;
    const item = made(kind, address, parent, picked ? picked.column : undefined);
    place(item, list, picked ? list.indexOf(picked) + 1 : list.length);
    document.getElementById("add-address").value = "";
    touch(parent || item);
    item.changed = true;
    show(item, true);
  });
  panel.querySelectorAll("[data-act=add-to]").forEach((button) => {
    button.addEventListener("click", () => {
      const kind = document.getElementById("add-kind").value;
      const address = document.getElementById("add-address").value.trim();
      if (!picked || !IN_COLUMN.includes(kind)) return;
      if (ADDRESSED.includes(kind) && !address) {
        document.getElementById("panel-said").textContent = say("script.visual.needs_address");
        return;
      }
      const column = Number(button.dataset.column);
      const item = made(kind, address, picked, column);
      picked.parts[column].push(item);
      document.getElementById("add-address").value = "";
      touch(picked);
    });
  });
  act("add-picture").addEventListener("click", () => {
    const address = document.getElementById("add-address").value.trim()
      || (field("src") && field("src").value.trim());
    if (!picked || picked.kind !== "pictures") return;
    if (!address) {
      document.getElementById("panel-said").textContent = say("script.visual.needs_address");
      return;
    }
    picked.parts[0].push(made("picture", address, picked, 0));
    document.getElementById("add-address").value = "";
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
    drop(gone);
    fill();
  });

  // ---- typing (§ 4.4) --------------------------------------------------
  function typed(event) {
    if (picked && picked.el && picked.el.contains(event.target)) touch(picked);
  }
  function pasted(event) {
    if (!picked || !picked.el) return;
    event.preventDefault();
    const words = (event.clipboardData.getData("text/plain") || "").replace(/\s*\n\s*/g, " ");
    frame.contentDocument.execCommand("insertText", false, words);
  }
  function keyed(event) {
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
    if (!file || !picked || picked.kind !== "picture") return;
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

  fill();
})();
"""
