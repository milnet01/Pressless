"""The editor: the list, the box, and the real page beside it (PRESS-0012).

His words save themselves shortly after he stops typing, and every save
rebuilds the preview, which is the Builder's own page for the entry
(docs/specs/PRESS-0012-editor.md § 4.2). Changes to a published entry go into
a working copy -- a draft carrying a `Replaces` header -- so the live version is
untouched until PRESS-0013 publishes them (§ 3 decision 2).

Nothing is held between requests: every route reads the Store afresh, and a
save refuses a file this window did not see (§ 4.8, design § State).
"""
from __future__ import annotations

import dataclasses
import hashlib
import html
import json
import re
import threading
import unicodedata
import urllib.parse
import warnings
from datetime import datetime
from pathlib import Path

from pressless import (
    builder,
    cheatsheet,
    choices,
    files,
    jpegxl,
    marks,
    paths,
    photographs,
    pressing,
    settings,
    store,
)
from pressless.face import (
    SENTENCES,
    Face,
    Reply,
    Request,
    Sentence,
    Site,
    message_box,
    render_notices,
    true_colours,
    within,
)
from pressless.words import say

PREVIEW_FOLDER = "preview"          # inside Pressless's own folder; the Face's alone
REPLACES = "Replaces"               # the header naming the published entry a copy changes
UNDONE = "Undone"                   # undo's mark (PRESS-0015 § 4.5), which publishing imports
UNTITLED = "untitled"
COPY_SUFFIX = "-changes"
LONGEST_ADDRESS = 60
PREVIEW_ADDRESS = "/preview/"
ASSETS_ADDRESS = "/preview/assets/"
LOOK_ADDRESS = "/preview/look/"     # PRESS-0126: the Store's style code
ORIGINALS_ADDRESS = "/originals/"
VIEWS_FOLDER = "jpeg-xl-views"      # PRESS-0275 § 4.7: JPEG XL originals as WebP, in a site
# PRESS-0346 § 4.1: an entry's two views.
VISUAL = "visual"
MARKS = "marks"


class ChangedElsewhere(Exception):
    """The file is not the one this window last saw (§ 4.8)."""


class TooManyCopies(Exception):
    """Two drafts replace one published entry (§ 4.1)."""


class BlocksUnreadable(Exception):
    """A visual save does not name the entry's blocks, or would not read back
    as them (PRESS-0346 § 4.5)."""


class LeftOut(store.StoreNotice):
    """A typed category or tag with nothing an address can keep (§ 4.8)."""


# Added here rather than in face.py, which cannot import this module back
# (§ 4.1).
SENTENCES[ChangedElsewhere] = Sentence(
    "failure.editor.ChangedElsewhere.what",
    Site.UNCHANGED,
    "failure.editor.ChangedElsewhere.next",
)
SENTENCES[TooManyCopies] = Sentence(
    "failure.editor.TooManyCopies.what",
    Site.UNCHANGED,
    "failure.editor.TooManyCopies.next",
)
SENTENCES[BlocksUnreadable] = Sentence(
    "failure.editor.BlocksUnreadable.what",
    Site.UNCHANGED,
    "failure.editor.BlocksUnreadable.next",
)
SENTENCES[marks.Unwritable] = Sentence(
    "failure.marks.Unwritable.what",
    Site.UNCHANGED,
    "failure.marks.Unwritable.next",
)
SENTENCES[photographs.NotAPhotograph] = Sentence(
    "failure.photographs.NotAPhotograph.what",
    Site.UNCHANGED,
    "failure.photographs.NotAPhotograph.next",
)
# A decoder that gives no picture is a file that is not one (PRESS-0275 § 6).
SENTENCES[jpegxl.Unreadable] = SENTENCES[photographs.NotAPhotograph]
SENTENCES[jpegxl.NotInstalled] = Sentence(
    "failure.jpegxl.NotInstalled.what",
    Site.UNCHANGED,
    "failure.jpegxl.NotInstalled.next",
)
SENTENCES[files.NotAllowed] = Sentence(
    "failure.files.NotAllowed.what",
    Site.UNCHANGED,
    "failure.files.NotAllowed.next",
)
SENTENCES[files.TooLarge] = Sentence(
    "failure.files.TooLarge.what",
    Site.UNCHANGED,
    "failure.files.TooLarge.next",
)

# What `save` raises, which the save route and the press route both answer.
SAVE_FAILURES = (store.StoreError, ChangedElsewhere, TooManyCopies, BlocksUnreadable,
                 marks.Unwritable)

# Every write, preview and publish runs under it; a threading.Lock cannot be
# taken twice, so `save` leaves it to its caller (PRESS-0013 § 4.1).
LOCK = threading.Lock()

# PRESS-0235 § 4.5: a press-row line rendered while a press runs; the script asks.
# Shared with page_editor; its spec names it with the underscore, as PRESS-0235
# and PRESS-0242 name _UNDO_SCRIPT and _EDITOR_SCRIPT, and PRESS-0017 _names_of.
_RUNNING = ' data-press="running"'
_JSON = "application/json"
_HTML = "text/html; charset=utf-8"


def address_for(title: str) -> str:
    """A new entry's address, from its title (§ 4.1)."""
    return name_address(title) or UNTITLED


def name_address(name: str) -> str:
    """`address_for`'s rule for a category or tag; "" where nothing is left.
    Control and format characters go first, so `a<TAB>b` is `ab`; a kept
    file's name joins them as `-` instead (photographs.plain_name)."""
    text = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf"))
    return photographs.folded(text)[:LONGEST_ADDRESS].strip("-")


def free_address(folder: Path, wanted: str) -> str:
    """`wanted`, or the first of `wanted-2`, `wanted-3` … no entry holds, no old
    address forwards from, and the Store accepts (§ 4.1; PRESS-0182)."""
    # Read once, outside the loop: its StoreError must stop the search, not be
    # skipped as a refused name (PRESS-0182 § 4.2).
    forwarded = store.read_forwards(folder)
    return photographs.first_free(wanted, lambda candidate: candidate not in forwarded
                            and not store.exists(folder, candidate))


def working_copy(folder: Path, slug: str) -> str | None:
    """The draft holding unpublished changes to the published entry `slug`
    (§ 4.1). Raises TooManyCopies where two drafts do."""
    if slug not in store.list_slugs(folder, draft=False):
        return None
    found = [draft for draft in store.list_slugs(folder, draft=True)
             if _draft_replaces(folder, draft) == slug]
    if len(found) > 1:
        raise TooManyCopies(f"{len(found)} drafts replace the entry {slug}")
    return found[0] if found else None


def photograph_file(folder: Path, name: str) -> Path:
    """The file the two photograph routes send for `name` (PRESS-0275 § 4.7):
    for a JPEG XL original the Store holds, named as itself or as its web
    copy, its WebP view copy, made or remade here; else the original. Raises
    where the view copy cannot be made, which the Face answers as a 404."""
    original_name = name[:-len(".webp")] if name.lower().endswith(".jxl.webp") else name
    if original_name.lower().endswith(".jxl"):
        original = store.photograph_path_for(folder, original_name)
        if original.is_file():
            view = Path(folder) / VIEWS_FOLDER / (original_name + ".webp")
            if not view.is_file() or view.stat().st_mtime < original.stat().st_mtime:
                builder.webp_copy(original, view)
            return view
    return store.photograph_path_for(folder, name)


def photo_src(name: str) -> str:
    """The preview's address for a photograph's original (§ 4.1)."""
    return ORIGINALS_ADDRESS + urllib.parse.quote(name, safe="")


def register(face: Face, folder: Path) -> None:
    """Add the editor's routes to `face` (§ 4.4). `folder` is Pressless's own
    folder, the one `face.serve` was handed."""
    folder = Path(folder)

    def route(handler):
        return lambda request: handler(face, folder, LOCK, request)

    face.add_page("GET", "/", route(_list))
    face.add_page("POST", "/new", route(_new))
    face.add_page("GET", "/edit", route(_edit))
    face.add_page("POST", "/save", route(_save))
    face.add_page("POST", "/edit/view", route(_view_chosen))
    face.add_page("POST", "/address", route(_address))
    face.add_page("POST", "/discard", route(_discard))
    face.add_page("POST", "/throw", route(_throw))
    face.add_page("POST", "/photograph", route(_photograph))
    face.add_page("POST", "/journal", route(_journal))
    face.add_files(ASSETS_ADDRESS, within(folder / paths.PREVIEW_ASSETS))
    # PRESS-0126 § 4.6: the style code straight from the Store, so a screen is
    # styled before any preview is built. The longest prefix wins.
    face.add_files(LOOK_ADDRESS, within(folder / store.LOOK_FOLDER))
    face.add_files(PREVIEW_ADDRESS, within(folder / PREVIEW_FOLDER))
    # PRESS-0260 § 4.6: a page's picture names its photograph as the site
    # will, so the preview serves the Store's originals there and copies none;
    # a JPEG XL original as its WebP view copy (PRESS-0275 § 4.7).
    face.add_files(PREVIEW_ADDRESS + store.PHOTOGRAPHS_FOLDER + "/",
                   lambda name: photograph_file(folder, name))
    face.add_files(ORIGINALS_ADDRESS, lambda name: photograph_file(folder, name))


# ------------------------------------------------------------- the Store ---


def _draft_replaces(folder: Path, draft: str) -> str | None:
    """The `Replaces` field of the draft `draft`, read from disk, or None -- an
    unreadable one included, which the list reports on its own (§ 4.5)."""
    try:
        entry = store.read(store.path_for(folder, draft, draft=True))
    except store.StoreError:
        return None
    return replaces_field(entry)


def replaces_field(entry: store.Entry) -> str | None:
    """The entry's `Replaces` field as written, checked against nothing: an
    ordinary draft may carry one naming no published entry. `_replaced`
    gives it only where it names one."""
    return next((value for name, value in entry.extra if name == REPLACES), None)


def _replaced(folder: Path, entry: store.Entry) -> str | None:
    """The published entry a draft is a working copy of, or None: a draft whose
    `Replaces` names no published entry is an ordinary draft (§ 4.1)."""
    named = replaces_field(entry)
    if named is None or named not in store.list_slugs(folder, draft=False):
        return None
    return named


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def form_fields(request: Request) -> dict[str, str]:
    """Every POST body is form-encoded, read as setup reads its own (§ 4.4)."""
    fields = urllib.parse.parse_qs(request.body.decode("utf-8"), keep_blank_values=True)
    return {name: values[0] for name, values in fields.items()}


def _usable(folder: Path, name: str) -> bool:
    """Whether the Store takes `name` as an address; the Builder asks the same."""
    try:
        store.path_for(folder, name, draft=False)
    except store.StoreError:  # a capital, a space, or a Windows device name
        return False
    return True


_LEFT_OUT = {"categories": "notice.editor.left_out.categories",
             "tags": "notice.editor.left_out.tags"}


def _names_of(folder: Path, value: str, box: str) -> tuple[str, ...]:
    """§ 4.8 step 3: a part the Store takes is kept, any other becomes an
    address, and repeats are dropped. A part that leaves nothing the Store would
    take is left out, and a notice names it. Templates call it too; PRESS-0017
    names it with the underscore."""
    names: list[str] = []
    for part in value.split(","):
        typed = part.strip()
        if not typed:
            continue
        name = typed if _usable(folder, typed) else name_address(typed)
        usable = bool(name) and _usable(folder, name)
        if not usable:
            warnings.warn(LeftOut(_LEFT_OUT[box], name=typed), stacklevel=2)
        elif name not in names:
            names.append(name)
    return tuple(names)


def _preview(face: Face, folder: Path, entry: store.Entry, *, draft: bool
             ) -> tuple[str | None, str | None]:
    """§ 4.8 step 5: the preview's address, or the failure in its place."""
    shown = entry
    named = _replaced(folder, entry) if draft else None
    if named is not None:
        shown = dataclasses.replace(entry, slug=named, extra=tuple(
            field for field in entry.extra if field[0] != REPLACES))
    try:
        saved = settings.load(folder)
        relative = builder.preview(folder, saved, folder / PREVIEW_FOLDER, shown,
                                   photo_src=photo_src)
    except Exception as exc:  # noqa: BLE001 -- a preview failure never undoes the save
        return None, face.fail(exc, publishing=False)
    return PREVIEW_ADDRESS + relative, None


def failed(face: Face, notices: list[str], failure: Exception) -> Reply:
    body = render_notices(notices) + face.fail(failure, publishing=False)
    return Reply(body.encode("utf-8"), _HTML, status=409)


def json_reply(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


def _edit_address(slug: str) -> str:
    return "/edit?slug=" + urllib.parse.quote(slug, safe="")


# ---------------------------------------------------------------- routes ---


def _journal_switch(journal: bool | None, published: bool) -> str:
    """PRESS-0214 § 4.5: whether the journal is on, and the one button that
    switches it. None where the options file could not be read."""
    if journal is None:
        return ""
    on = say("editor.journal.on")
    if published:
        on += " " + say("editor.journal.on_published")
    off = say("editor.journal.off")
    # PRESS-0236: both states' words in one place, the other one hidden, so
    # switching leaves the button and everything below where they were.
    when_on, when_off = ("", " hidden") if journal else (" hidden", "")
    return ('<form method="post" action="/journal" class="switch-row">'
            f'<div class="states"><p{when_off}>{off}</p><p{when_on}>{on}</p></div>'
            '<button><span class="states">'
            f'<span{when_off}>{say("editor.journal.turn_on")}</span>'
            f'<span{when_on}>{say("editor.journal.turn_off")}</span></span></button></form>')


def _site_line(folder: Path) -> str:
    """Which site this list is for: its name and its address. Empty where
    either cannot be read, which the rest of the page does not depend on."""
    try:
        identity = store.read_identity(folder)
        address = settings.load(folder).site_address
    except (store.StoreError, settings.SettingsError, settings.NotSetUp):
        return ""
    e = html.escape
    name = (identity.name if identity is not None and identity.name
            else say("editor.site_line.unnamed"))
    shown = re.sub(r"^https?://", "", address).rstrip("/")
    link = (f'<a href="{e(address, quote=True)}" target="_blank" rel="noopener">'
            f"{e(shown)}</a>")
    return f'<p class="site-line">{say("editor.site_line", name=e(name), address=link)}</p>'


def _journal(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0214 § 4.5: switch the journal to the opposite of what it is."""
    with lock, face.capture() as notices:
        try:
            store.write_journal(folder, not store.journal_on(folder))
        except store.StoreError as exc:
            return failed(face, notices, exc)
    pressing.forget()  # PRESS-0235 decision 6
    return Reply(b"", "text/plain; charset=utf-8", status=303, location="/")


def _list(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str:
    """§ 4.5."""
    readable: dict[bool, list[store.Entry]] = {True: [], False: []}
    unreadable: dict[bool, list[str]] = {True: [], False: []}
    first_failure: Exception | None = None
    with face.capture() as notices:
        for draft in (True, False):
            for slug in store.list_slugs(folder, draft=draft):
                try:
                    readable[draft].append(store.read(store.path_for(folder, slug, draft=draft)))
                except store.StoreError as exc:
                    first_failure = first_failure or exc
                    unreadable[draft].append(slug)
        hint = request.query.get("page_hint", "")
        try:
            listed = _pages(folder, hint)
        except store.StoreError as exc:
            first_failure = first_failure or exc
            listed = _Listed(f"<p>{say('editor.list.pages_unreadable')}</p>", 0, "", 0, "")
        site = _site_line(folder)
        try:
            journal: bool | None = store.journal_on(folder)
        except store.StoreError as exc:
            first_failure = first_failure or exc
            journal = None
    # Every listed slug, readable or not: _replaced and working_copy ask
    # list_slugs, so an unreadable published entry still has its working copy
    # (PRESS-0162).
    published = {entry.slug for entry in readable[False]} | set(unreadable[False])
    drafts, notes = _drafts_and_notes(readable[True], published)
    failure = face.fail(first_failure, publishing=False) if first_failure else ""
    # PRESS-0235 § 4.5: the list's press row is the undo line.
    said, running, ended = pressing.shown("")
    header = (render_notices(notices) + failure +
              f"<h1>{say('face.your_writing')}</h1>" + site + listed.carry_on
              # PRESS-0023 § 4.9: what other parts show here, without this
              # module importing them.
              + "".join(face.list_pieces(above=True))
              # PRESS-0236: a press's failure opens over the list.
              + message_box("failure", ended or "", forgets=True))
    controls = (_new_entry_form(folder) + _undo_row(said, running=running)
                + _journal_switch(journal, bool(published)))
    # PRESS-0189: each list is a card. PRESS-0344: folded shut under its count,
    # so the screen opens short; Your pages opens to show a refused name's hint.
    cards = (_fold("editor.list.drafts", len(drafts) + len(unreadable[True]),
                   _rows(drafts, unreadable[True], notes))
             + _fold("editor.list.on_site", len(readable[False]) + len(unreadable[False]),
                     _rows(readable[False], unreadable[False], notes))
             + _fold("editor.list.pages", listed.page_count, listed.pages,
                     shown=hint in PAGE_HINTS)
             + (_fold("editor.list.parts", listed.part_count, listed.parts)
                if listed.parts else ""))
    return (header + '<div id="undo-result"></div>'
            + '<div id="listing">' + controls + cards + "</div>"
            + "".join(face.list_pieces(above=False))
            + f"<script>{_UNDO_SCRIPT}</script>")


def _drafts_and_notes(read_drafts: list[store.Entry], published: set[str],
                      ) -> tuple[list[store.Entry], dict[str, str]]:
    """The drafts to list -- every draft but a working copy -- and the note
    beside an entry, by slug: a published entry's waiting changes, and undo's
    marks."""
    changed = {replaces_field(entry) for entry in read_drafts} & published
    drafts = [entry for entry in read_drafts if replaces_field(entry) not in published]
    # PRESS-0015 § 4.6: the draft undo took off the site, and a draft whose
    # `Replaces` names it -- the copy publishing._move publishes over it.
    undone = {entry.slug for entry in drafts if any(name == UNDONE for name, _ in entry.extra)}
    notes = {entry.slug: say("editor.list.undone") for entry in drafts if entry.slug in undone}
    notes.update({entry.slug: say("editor.list.later_changes") for entry in drafts
                  if replaces_field(entry) in undone})
    notes.update({slug: say("editor.list.changed") for slug in changed})
    return drafts, notes


def _rows(entries: list[store.Entry], broken: list[str], notes: dict[str, str]) -> str:
    """One list card's entries, newest first, then the slugs that did not read."""
    ordered = sorted(sorted(entries, key=lambda entry: entry.slug),
                     key=lambda entry: entry.date, reverse=True)
    items = []
    for entry in ordered:
        said = notes.get(entry.slug)
        note = f" <em>{said}</em>" if said else ""
        items.append(
            f'<li><a href="{html.escape(_edit_address(entry.slug), quote=True)}">'
            f"{html.escape(entry.title or say('editor.list.untitled'))}</a> "
            f"<small>{entry.date:%d %b %Y}</small>{note}</li>")
    items.extend(f"<li>{html.escape(slug)} <em>{say('editor.list.unreadable')}</em></li>"
                 for slug in broken)
    return "<ul>" + "".join(items) + "</ul>" if items else f"<p>{say('editor.list.none')}</p>"


def _fold(heading: str, count: int, inside: str, *, shown: bool = False) -> str:
    return (f'<details class="card fold"{" open" if shown else ""}><summary>'
            f"<h2>{say(heading)} ({count})</h2></summary>{inside}</details>")


@dataclasses.dataclass(frozen=True)
class _Listed:
    """Your pages and the parts of every page, each with its count, and the
    Carry on with line, which leads the screen rather than a folded list."""
    pages: str
    page_count: int
    parts: str
    part_count: int
    carry_on: str


def _new_entry_form(folder: Path) -> str:
    return (f'<form method="post" action="/new"><label>{say("editor.title")} '
            '<input name="title" autocomplete="off"></label> '
            f"{_template_choice(folder)}"
            f"<button>{say('editor.list.new')}</button></form>")


def _undo_row(said: str, *, running: bool) -> str:
    """PRESS-0015 § 4.6: it always shows, and nothing asks GitHub before
    showing it (§ 3 decision 3)."""
    return (f'<p><button type="button" data-undo>{say("editor.undo")}</button></p>'
            f'<p id="undo-status" class="press-status" role="status"'
            f'{_RUNNING if running else ""}>{html.escape(said)}</p>')


def _template_choice(folder: Path) -> str:
    """PRESS-0017 § 4.3: a blank entry first, then each template that reads,
    labelled with its title or, where that is empty, its name."""
    options = [f'<option value="">{say("editor.list.blank")}</option>']
    try:
        names = store.list_templates(folder)
    except store.StoreError:
        names = ()
    for name in names:
        try:
            label = store.read(store.template_path_for(folder, name)).title or name
        except store.StoreError:
            continue
        options.append(f'<option value="{html.escape(name, quote=True)}">'
                       f"{html.escape(label)}</option>")
    return (f'<label>{say("editor.list.start_from")} <select name="template">'
            f'{"".join(options)}</select></label> ')


# PRESS-0195 § 4.3: why a new page's name was refused, by the code its route
# sends back, so the list shows a sentence and never the query's own text.
PAGE_HINTS = {"empty": "page_hint.empty", "taken": "page_hint.taken",
              "forwarded": "page_hint.forwarded", "unusable": "page_hint.unusable"}


def _pages(folder: Path, hint: str = "") -> _Listed:
    """PRESS-0014 § 4.4: each fixed page, then the three furniture files, each
    saying where its changes are not on the site yet; a page only waiting to
    be pressed is listed too, and the New page box follows (PRESS-0195 § 4.3).
    The pages and the furniture come back apart, the furniture as the parts
    of every page (PRESS-0341). Drawn from the Store alone, so this module
    imports nothing of page_editor.py."""
    names = sorted(set(store.list_html(folder, store.PAGES_FOLDER))
                   | set(store.list_html(folder, store.PAGES_FOLDER, waiting=True)))
    rows = [(store.PAGES_FOLDER, name,
             say("editor.pages.home") if name == "index" else builder.label(name))
            for name in names]
    rows += [(store.FURNITURE_FOLDER, name, say(key))
             for name, key in (("header", "editor.pages.header"),
                               ("footer", "editor.pages.footer"),
                               ("navigation", "editor.pages.navigation"))]
    items: dict[str, list[str]] = {store.PAGES_FOLDER: [], store.FURNITURE_FOLDER: []}
    carry_on = ""
    last = choices.read(folder).page  # PRESS-0263: where he left off, while it is held
    for kind, name, label in rows:
        address = "/page?" + urllib.parse.urlencode({"kind": kind, "name": name})
        if (kind, name) == last:
            carry_on = (f'<p>{say("editor.list.carry_on")} <a href="'
                        f'{html.escape(address, quote=True)}">{html.escape(label)}</a></p>')
        note = (f" <em>{say('editor.list.changed')}</em>"
                if store.html_path_for(folder, kind, name, waiting=True).is_file() else "")
        items[kind].append(f'<li><a href="{html.escape(address, quote=True)}">'
                           f"{html.escape(label)}</a>{note}</li>")
    said = say(PAGE_HINTS[hint]) if hint in PAGE_HINTS else ""
    pages = ("<ul>" + "".join(items[store.PAGES_FOLDER]) + "</ul>"
             f'<form method="post" action="/page/new"><label>{say("editor.list.page_name")} '
             '<input name="name" autocomplete="off"></label> '
             f"<button>{say('editor.list.new_page')}</button></form>"
             f'<p id="page-hint" role="status">{html.escape(said)}</p>')
    parts = (f"<p>{say('editor.list.parts_note')}</p>"
             "<ul>" + "".join(items[store.FURNITURE_FOLDER]) + "</ul>")
    return _Listed(pages, len(items[store.PAGES_FOLDER]), parts,
                   len(items[store.FURNITURE_FOLDER]), carry_on)


def new_draft(folder: Path, title: str, template: str) -> store.Entry:
    """§ 4.6: a new draft titled `title`, from the template `template` or from
    nothing. Takes no lock; the caller holds LOCK (PRESS-0337 § 4.7)."""
    # PRESS-0017 § 4.3: the template's words, categories and tags; never its
    # title, and the template file is only read.
    shape = (store.read(store.template_path_for(folder, template)) if template
             else store.Entry(slug="", title="", date=datetime.now(),
                              categories=(), tags=(), body="", extra=()))
    entry = store.Entry(
        slug=free_address(folder, address_for(title)), title=title.strip(),
        date=datetime.now().replace(microsecond=0), categories=shape.categories,
        tags=shape.tags, body=shape.body, extra=())
    store.write(folder, entry, draft=True)
    return entry


def _new(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.6."""
    form = form_fields(request)
    with lock, face.capture() as notices:
        try:
            slug = new_draft(folder, form.get("title", ""), form.get("template", "")).slug
        except store.StoreError as exc:
            return failed(face, notices, exc)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=_edit_address(slug))


def _edit(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str | Reply:
    """§ 4.7."""
    slug = request.query.get("slug", "")
    # PRESS-0235 § 4.5: during a press, a page that opens the editor once it ends.
    held = pressing.holding()
    if held is not None:
        return held
    with lock, face.capture() as notices:
        try:
            if slug in store.list_slugs(folder, draft=True):
                draft = True
            elif slug in store.list_slugs(folder, draft=False):
                copy = working_copy(folder, slug)
                if copy is not None:
                    return Reply(b"", "text/plain; charset=utf-8", status=303,
                                 location=_edit_address(copy))
                draft = False
            else:
                raise store.EntryNotFound(f"there is no entry {slug!r}")
            path = store.path_for(folder, slug, draft=draft)
            entry = store.read(path)
            base = digest(path)
        except (store.StoreError, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
            preview, preview_failure = _preview(face, folder, entry, draft=draft)
            missing = photographs.missing(folder, entry.body)
    if failure is not None:
        return render_notices(notices) + face.fail(failure, publishing=False)
    # PRESS-0346 § 4.1: the view asked for, which is remembered, else the one
    # remembered, else the visual view.
    asked = request.query.get("view", "")
    if asked in (VISUAL, MARKS):
        choices.remember(folder, entry_view=asked)
    view = asked if asked in (VISUAL, MARKS) else choices.read(folder).entry_view
    return render_notices(notices) + _page(folder, entry, draft, base, preview, preview_failure,
                                           missing, face.view_site(),
                                           view=MARKS if view == MARKS else VISUAL)


def _view_chosen(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0346 § 4.1: an in-place switch remembers the view it went to."""
    view = form_fields(request).get("view", "")
    if view in (VISUAL, MARKS):
        choices.remember(folder, entry_view=view)
    return json_reply({"view": view})


def _page(folder: Path, entry: store.Entry, draft: bool, base: str,
          preview: str | None, failure: str | None, missing: list[str], visit: str,
          *, view: str = VISUAL) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    named = _replaced(folder, entry) if draft else None
    on_site = not draft or named is not None
    proof = named is not None
    hide_published, hide_waiting = (" hidden", "") if proof else ("", " hidden")
    # Both states on every page, because a save turns a published entry's page
    # into a working copy's editor, and a press turns a draft's or a proof's
    # into a published entry's, without reloading it; the script shows the one
    # that holds and names the copy (PRESS-0162, PRESS-0185).
    standing = (f'<div id="standing"{"" if on_site else " hidden"}>'
                f'<p data-when="0"{hide_published}>{say("editor.standing.published")}</p>'
                f'<p data-when="1"{hide_waiting}>{say("editor.standing.waiting")}</p>'
                f'<form data-when="1"{hide_waiting} method="post" action="/discard">'
                f'<input type="hidden" name="slug" value="{attr(entry.slug) if proof else ""}">'
                f'<input type="hidden" name="base" value="{attr(base)}">'
                f"<button>{say('editor.bin_proof')}</button></form></div>")
    if not on_site:
        standing = f'<p id="draft-standing">{say("editor.standing.draft")}</p>' + standing
    # PRESS-0182: a published entry moves too; the script hides this once a
    # save makes a proof, whose address cannot change, and shows it again
    # once that proof is pressed (PRESS-0186).
    address = _address_field(named if proof else entry.slug, hidden=proof)
    # PRESS-0234: the press row's status line, between presses. The script
    # keeps it in step (its `standing`).
    standing_word = say("script.standing.on_site" if not draft else
                        "script.standing.changes" if on_site else "script.standing.off_site")
    said, running, ended = pressing.shown(standing_word)
    pressed = _RUNNING if running else ""
    stylesheets = "".join(f'<link rel="stylesheet" href="{attr(PREVIEW_ADDRESS + sheet)}">'
                          for sheet in builder.stylesheets(folder))
    # PRESS-0346 § 4.1: one link to each view, the one to the view shown
    # hidden; the script swaps them.
    switch = '<p class="nav">' + "".join(
        f'<a data-switch="{to}" href="{attr(_edit_address(entry.slug) + "&view=" + to)}"'
        f'{" hidden" if to == view else ""}>{say(key)}</a>'
        for to, key in ((MARKS, "editor.show_marks"), (VISUAL, "page_editor.show_visual"))
    ) + "</p>"
    return f"""{stylesheets}
<p class="nav"><a href="/">{say("face.your_writing")}</a> <span id="save-status"></span></p>
<div class="states">{standing}</div>
{switch}
{message_box("notices")}
<form id="editor" data-slug="{attr(entry.slug)}" data-draft="{'1' if draft else '0'}"
 data-base="{attr(base)}" data-missing="{attr(json.dumps(missing))}"
 data-on-site="{'1' if on_site else '0'}" data-view="{attr(view)}" onsubmit="return false">
<label>{say("editor.title")} <input name="title" value="{attr(entry.title)}"></label>
<label>{say("editor.categories")} <input name="categories"
 value="{attr(store.LIST_SEPARATOR.join(entry.categories))}"></label>
<label>{say("editor.tags")} <input name="tags"
 value="{attr(store.LIST_SEPARATOR.join(entry.tags))}"></label>
{address}
<p><button type="button" data-editor="publish">{say("editor.press")}</button>
 {visit}
 <button type="button" data-undo>{say("editor.undo")}</button></p>
<p id="publish-status" class="press-status" role="status"{pressed}>{attr(said)}</p>
<p id="photograph-missing" hidden></p>
{_entry_panel(folder, entry.body, hidden=view == MARKS)}
<div id="marks-view"{" hidden" if view == VISUAL else ""}>
<p><button type="button" data-editor="photograph">{say("editor.add_photograph")}</button>
 <input type="file" id="photograph-file" hidden
 accept="{photographs.ACCEPT}">
 <span id="photograph-status"></span></p>
<textarea name="body" class="{attr(builder.BODY_CLASS)}" rows="24">
{html.escape(entry.body)}</textarea>
{cheatsheet.panel()}
</div>
<p><button type="button" data-editor="throw">{
 say("script.editor.throw_entry" if on_site else "editor.throw_draft")}</button></p>
</form>
{message_box("failure", (failure or "") + (ended or ""), forgets=True)}
{message_box("address-hint", focus="address")}
<div id="undo-result"></div>
<div id="proof">{true_colours(choices.read(folder).true_colours)}
<iframe id="preview" title="{attr(say("editor.proof_title"))}" sandbox="allow-same-origin"
 src="{attr(preview or 'about:blank')}"></iframe></div>
<script>{_EDITOR_SCRIPT}</script>
<script>{TYPING_SCRIPT}</script>
<script>{_VISUAL_SCRIPT}</script>
<script>{_UNDO_SCRIPT}</script>"""


def script_json(payload: object) -> str:
    """JSON for an inline `<script type="application/json">` block, with every
    character that could open an HTML tag or comment escaped, so user content
    carried in it cannot break out of the element (OWASP A03 / CWE-116). A
    `</script>`, a `<!--` and a `<script` all begin with `<`, so escaping `<`
    (and `>`/`&` with it) closes the hole the bare `</` replacement left open."""
    return (json.dumps(payload)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def _colours() -> dict:
    """§ 4.4: the colour marks as the page writes them, from their own rows,
    so the script keeps a colour span exactly as `to_html` wrote it."""
    named, held = {}, "\x00"
    picked = None
    for row in marks.MARKS:
        if row.kind != "wrap" or row.content != "marks":
            continue
        opening = row.render(marks.Span(row.name, held if row.arg else None, ()), "", str)
        found = re.fullmatch(r'<span style="([^"]*)">', opening.partition("</")[0])
        if found is None:
            continue
        if row.arg is None:
            named[row.name] = html.unescape(found.group(1))
        else:
            picked = {"prefix": found.group(1).partition(held)[0], "pattern": row.arg}
    return {"named": named, "picked": picked}


def _entry_panel(folder: Path, body: str, *, hidden: bool) -> str:
    """PRESS-0346 § 4.3: the side panel, every control in place from the
    start; the script shows the ones the picked block uses, inside a panel of
    fixed size, so nothing beside it moves."""
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    link_row = next(row for row in marks.MARKS if row.name == "link")
    data = script_json({
        "blocks": outline(body), "body_class": builder.BODY_CLASS,
        "originals": ORIGINALS_ADDRESS, "link": link_row.arg, "colours": _colours(),
    })
    kinds = "".join(f'<option value="{kind}">{say(words)}</option>'
                    for kind, words in _KIND_WORDS.items())
    names = "".join(f'<option value="{attr(name)}">{html.escape(name)}</option>'
                    for name in store.list_photographs(folder))
    named = "".join(f'<button type="button" data-colour="{attr(name)}">'
                    f'{say(_COLOUR_WORDS[name])}</button>'
                    for name in _colours()["named"])
    return f"""<aside id="panel" aria-label="{attr(say("page_editor.panel.title"))}"{
        " hidden" if hidden else ""}>
<script type="application/json" id="blocks">{data}</script>
<p id="picked" role="status">{say("script.entry.nothing")}</p>
<div class="panel-add"><label>{say("page_editor.panel.add")}
 <select id="add-kind">{kinds}</select></label>
<button type="button" data-act="add">{say("page_editor.panel.add_button")}</button>
<p id="add-where">{say("script.entry.end")}</p></div>
<div class="panel-row" data-for="typed">
<button type="button" data-act="bold"><b>{say("page_editor.panel.bold")}</b></button>
<button type="button" data-act="italic"><i>{say("page_editor.panel.italic")}</i></button>
<button type="button" data-act="link">{say("page_editor.panel.link")}</button></div>
<div class="panel-row" data-for="typed">{named}
<label>{say("editor.panel.colour.picked")} <input type="color" id="picked-colour"
 value="#c0453a"></label>
<button type="button" data-act="colour">{say("editor.panel.colour.use")}</button></div>
<label data-for="photo">{say("editor.panel.photograph")} <select data-field="name">
<option value="">{say("editor.panel.choose")}</option>{names}</select></label>
<p data-for="photo"><button type="button" data-act="photograph">{
    say("editor.add_photograph")}</button>
<input type="file" id="panel-photograph-file" hidden accept="{photographs.ACCEPT}"></p>
<label data-for="photo">{say("page_editor.panel.caption")}
 <input data-field="caption" autocomplete="off"></label>
<p data-for="marks">{say("editor.panel.marks_note")}</p>
<label data-for="marks">{say("editor.panel.marks")}
<textarea data-field="marks" rows="8" spellcheck="false"></textarea></label>
<p class="panel-row"><button type="button" data-act="up">{say("page_editor.panel.move_up")}</button>
<button type="button" data-act="down">{say("page_editor.panel.move_down")}</button>
<button type="button" data-act="remove">{say("page_editor.panel.remove")}</button></p>
<p id="panel-said" role="status"></p>
</aside>"""


def _address_field(slug: str, *, hidden: bool) -> str:
    value = html.escape(slug, quote=True)
    return (f'<span id="address"{" hidden" if hidden else ""}><label>{say("editor.address")} '
            f'<input name="address" value="{value}">'
            '</label> <button type="button" data-editor="address">'
            f'{say("editor.change_address")}</button></span>')


def save(folder: Path, form: dict[str, str]) -> tuple[store.Entry, str]:
    """PRESS-0012 § 4.8 steps 1 to 4: write the box to its draft, and return the
    entry written and its new digest. Takes no lock; the caller holds LOCK."""
    slug, draft, base = form.get("slug", ""), form.get("draft") == "1", form.get("base", "")
    path = store.path_for(folder, slug, draft=draft)
    entry = store.read(path)
    if digest(path) != base:
        raise ChangedElsewhere(f"the entry {slug} changed since this window read it")
    extra = entry.extra
    written_slug = slug
    if not draft:
        if working_copy(folder, slug) is not None:
            raise ChangedElsewhere(f"the entry {slug} gained a working copy")
        written_slug = free_address(folder, slug + COPY_SUFFIX)
        extra = tuple(field for field in entry.extra
                      if field[0] != REPLACES) + ((REPLACES, slug),)
    if form.get("view") == VISUAL:
        try:
            posted = json.loads(form.get("blocks", ""))
            removed = json.loads(form.get("removed", ""))
        except ValueError as exc:
            raise BlocksUnreadable(f"the save of {slug} does not name its blocks") from exc
        body = put_blocks(entry.body, posted, removed)
    else:
        body = form.get("body", "").replace("\r\n", "\n").replace("\r", "\n")
    written = store.Entry(
        slug=written_slug, title=form.get("title", "").strip(), date=entry.date,
        categories=_names_of(folder, form.get("categories", ""), "categories"),
        tags=_names_of(folder, form.get("tags", ""), "tags"), body=body, extra=extra)
    new_base = digest(store.write(folder, written, draft=True))
    pressing.forget()  # PRESS-0235 decision 6
    return written, new_base


# ------------------------------------------- the visual view (PRESS-0346) ---

# Each block's name on the screen; the script reads the same keys by kind.
_KIND_WORDS = {"paragraph": "script.entry.kind.paragraph", "photo": "script.entry.kind.photo",
               "quote": "script.entry.kind.quote"}
# The named colour marks' buttons (§ 4.3), by the mark each writes.
_COLOUR_WORDS = {"accent": "editor.panel.colour.accent", "muted": "editor.panel.colour.muted"}
_KIND_OF = {row.kind: row.name for row in marks.MARKS if row.kind in ("block", "prefix")}
_TYPED = {row.name for row in marks.MARKS if row.kind == "wrap" and row.content == "marks"}


def _typed(nodes: tuple) -> bool:
    """Whether the page can show these nodes as typed (§ 3 decision 7): text
    and the marks the panel offers, and nothing worked out or per letter."""
    return all(isinstance(node, marks.Text)
               or (isinstance(node, marks.Span) and node.mark in _TYPED and _typed(node.children))
               for node in nodes)


def outline(body: str) -> list[dict]:
    """§ 4.2: each block of the body, in order, as the script pairs it with
    the frame: its kind, whether it is typed on, and its marks as written."""
    shown = []
    for block, text in zip(marks.parse(body), marks.sources(body)[1], strict=True):
        item: dict = {"marks": text}
        if isinstance(block, marks.Photo):
            caption = marks.normal(block).caption
            item.update(kind="photo", typed=False, name=block.name, caption=caption or "")
        else:
            paragraphs = block.paragraphs if isinstance(block, marks.Quote) else (block,)
            item.update(kind="quote" if isinstance(block, marks.Quote) else "paragraph",
                        typed=all(_typed(line.children)
                                  for paragraph in paragraphs for line in paragraph.lines))
        shown.append(item)
    return shown


def _words(value: object) -> marks.Paragraph:
    if not isinstance(value, str):
        raise BlocksUnreadable(f"{value!r} is not words")
    paragraph = marks.from_inline(value)
    if paragraph is None:
        raise marks.Unwritable("the words hold styling no mark can keep")
    return paragraph


def _built(item: object) -> tuple[marks.Block, ...]:
    """A block built anew, or none where it holds nothing (§ 4.5)."""
    if not isinstance(item, dict) or len(item) not in (1, 2):
        raise BlocksUnreadable(f"{item!r} is not a block")
    if "paragraph" in item:
        paragraph = _words(item["paragraph"])
        return (paragraph,) if paragraph.lines else ()
    if "quote" in item:
        if not isinstance(item["quote"], list):
            raise BlocksUnreadable(f"{item!r} is not a block")
        paragraphs = tuple(p for p in map(_words, item["quote"]) if p.lines)
        return (marks.Quote(_KIND_OF["prefix"], paragraphs),) if paragraphs else ()
    if "photo" in item:
        name, caption = item["photo"], item.get("caption", "")
        if not isinstance(name, str) or not isinstance(caption, str):
            raise BlocksUnreadable(f"{item!r} is not a block")
        # The caption as a Text holds it, so an '&' typed stays an '&'.
        lines = _words(html.escape(caption, quote=False)).lines
        held = "".join(node.value for node in lines[0].children) if lines else ""
        return (marks.Photo(_KIND_OF["block"], name.strip(), held or None),)
    raise BlocksUnreadable(f"{item!r} is not a block")


def put_blocks(body: str, posted: object, removed: object) -> str:
    """§ 4.5 steps 1 to 3: the body written from the posted blocks. Raises
    BlocksUnreadable, or marks.Unwritable from a block built anew."""
    if not isinstance(posted, list) or not isinstance(removed, list):
        raise BlocksUnreadable("the save does not name the entry's blocks")
    gaps, texts = marks.sources(body)
    held = marks.parse(body)

    def index(value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < len(held):
            raise BlocksUnreadable(f"{value!r} names no block of the entry")
        return value

    # Each piece is the block index it keeps, or None, its text and its blocks.
    pieces: list[tuple[int | None, str, tuple[marks.Block, ...]]] = []
    for item in posted:
        if isinstance(item, dict) and set(item) == {"keep"}:
            at = index(item["keep"])
            pieces.append((at, texts[at], (held[at],)))
        elif isinstance(item, dict) and set(item) == {"marks"}:
            if not isinstance(item["marks"], str):
                raise BlocksUnreadable(f"{item!r} is not a block")
            text = item["marks"].replace("\r\n", "\n").replace("\r", "\n").strip()
            if text:
                pieces.append((None, text, marks.parse(text)))
        else:
            pieces.extend((None, marks.write(block), (block,)) for block in _built(item))
    named = [at for at, _, _ in pieces if at is not None] + [index(at) for at in removed]
    if sorted(named) != list(range(len(held))):
        raise BlocksUnreadable("the save does not name each of the entry's blocks once")

    # Kept neighbours keep what lay between them; anything else gets a blank line.
    out = [gaps[0]]
    for number, (at, text, _) in enumerate(pieces):
        if number:
            before = pieces[number - 1][0]
            out.append(gaps[at] if at is not None and before == (at - 1) else "\n\n")
        out.append(text)
    out.append(gaps[-1])
    new = "".join(out)
    wanted = tuple(marks.normal(block) for _, _, blocks in pieces for block in blocks)
    if tuple(marks.normal(block) for block in marks.parse(new)) != wanted:
        raise BlocksUnreadable("the save would not read back as the entry's blocks")
    return new


def _save(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.8."""
    form = form_fields(request)
    with lock, face.capture() as notices:
        try:
            written, new_base = save(folder, form)
        except SAVE_FAILURES as exc:
            failure: Exception | None = exc
        else:
            failure = None
            preview, preview_failure = _preview(face, folder, written, draft=True)
            missing = photographs.missing(folder, written.body)
    if failure is not None:
        return failed(face, notices, failure)
    # PRESS-0346 § 4.5: the body and its outline, so either view opens from
    # the reply after a switch.
    return json_reply({"slug": written.slug, "draft": True, "base": new_base, "preview": preview,
                  "failure": preview_failure, "notices": render_notices(notices),
                  "missing": missing, "body": written.body, "outline": outline(written.body)})


def _photograph(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0016: keep the posted file as an original and name it. The body is
    the file itself, and its chosen name comes in the query."""
    with lock, face.capture() as notices:
        try:
            name = photographs.add(folder, request.query.get("name", ""), request.body)
        except (store.StoreError, photographs.NotAPhotograph, jpegxl.NotInstalled,
                OSError) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return failed(face, notices, failure)
    # `address`: where the site publishes it, which a page's picture names.
    return json_reply({"name": name, "address": builder.web_photograph(name),
                       "notices": render_notices(notices)})


class AddressRefused(Exception):
    """An address change `_address_refused` turns down; `hint` says why."""

    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.hint = hint
        self.slots = {"hint": hint}


SENTENCES[AddressRefused] = Sentence(
    "failure.editor.AddressRefused.what",
    Site.UNCHANGED,
    "failure.editor.AddressRefused.next",
)


def change_address(folder: Path, slug: str, base: str, address: str, *, draft: bool) -> str:
    """§ 4.9, and PRESS-0182 § 4.2 for a published entry: move the entry at
    `slug` to `address` and return its new digest, or `base` where the address
    is its own. Raises AddressRefused. Takes no lock (PRESS-0337 § 4.7)."""
    entry = (store.read(store.path_for(folder, slug, draft=draft))
             if slug in store.list_slugs(folder, draft=draft) else None)
    hint = _address_refused(folder, entry, slug, address, draft=draft)
    if hint is not None:
        raise AddressRefused(hint)
    if address == slug:
        return base
    return _move(folder, _keeping_votes(folder, entry, draft=draft), slug, address, base,
                 draft=draft)


def _address(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.9, and PRESS-0182 § 4.2 for a published entry: its old address
    forwards to the new one."""
    form = form_fields(request)
    slug, base, address = form.get("slug", ""), form.get("base", ""), form.get(
        "address", "").strip()
    # A request without `draft` has PRESS-0012 § 4.9's shape, from before a
    # published entry could move, and then only a draft could.
    draft = form.get("draft", "1") == "1"
    hint = None
    with lock, face.capture() as notices:
        try:
            base = change_address(folder, slug, base, address, draft=draft)
            slug = address
        except AddressRefused as refused:
            hint = refused.hint
            failure: Exception | None = None
        except (store.StoreError, ChangedElsewhere, TooManyCopies) as exc:
            failure = exc
        else:
            failure = None
    if failure is not None:
        return failed(face, notices, failure)
    return json_reply({"slug": slug, "draft": draft, "base": base, "preview": None,
                  "failure": None, "notices": render_notices(notices), "hint": hint})


def _keeping_votes(folder: Path, entry: store.Entry, *, draft: bool) -> store.Entry:
    """PRESS-0211 § 4.2: `entry` holding the key from before its move, where it
    could have votes (it is published, or undo took it off the site), buttons
    are on, and it holds no key already."""
    if draft and not any(name == UNDONE for name, _ in entry.extra):
        return entry
    if any(name == store.VOTE_KEY for name, _ in entry.extra):
        return entry
    try:
        on = settings.load(folder).votes is not None
    except (settings.NotSetUp, settings.SettingsError):
        return entry
    key = store.vote_key(entry)
    if not on or key is None:
        return entry
    return dataclasses.replace(entry, extra=(*entry.extra, (store.VOTE_KEY, key)))


def _address_refused(folder: Path, entry: store.Entry | None, slug: str, address: str,
                     *, draft: bool) -> str | None:
    """The hint saying why `entry`, at `slug`, may not move to `address`, or
    None where it may (PRESS-0182 § 4.2 step 1). Keeping its own address is
    never refused, though an entry that has gone, or a proof, still is."""
    if entry is None:
        return say("editor.hint.gone")
    if draft and _replaced(folder, entry) is not None:
        return say("editor.hint.proof")
    if not draft and working_copy(folder, slug) is not None:
        return say("editor.hint.proof_waiting")
    if address == slug:
        return None
    try:
        taken = store.exists(folder, address)
    except store.StoreError:
        return say("editor.hint.bad_address")
    if taken:
        return say("editor.hint.taken")
    if store.read_forwards(folder).get(address, slug) != slug:
        return say("editor.hint.forwarded")
    return None


def _move(folder: Path, entry: store.Entry, slug: str, address: str, base: str, *,
          draft: bool) -> str:
    """Move `entry`, at `slug`, to `address`, with its forwards and comments, and return
    the moved file's digest: the window's new base. `base` must still match."""
    path = store.path_for(folder, slug, draft=draft)
    if digest(path) != base:
        raise ChangedElsewhere(f"the entry {slug} changed since this window read it")
    # The order leaves two copies, never none (§ 4.2).
    store.write(folder, dataclasses.replace(entry, slug=address), draft=draft)
    # Retarget every pair aimed here. A pair FROM the new address can only be
    # aimed here (_address_refused refuses any other), so it becomes a loop
    # and the last line drops it: moving back.
    forwards = {old: (address if new == slug else new)
                for old, new in store.read_forwards(folder).items()}
    if not draft:
        forwards[slug] = address
    forwards = {old: new for old, new in forwards.items() if old != new}
    if forwards != store.read_forwards(folder):
        store.write_forwards(folder, forwards)
    comments = store.comments_path_for(folder, slug)
    if comments.is_file():
        store.write_comments(folder, address, store.read_comments(comments))
        store.move_to_bin(folder, comments)
    store.move_to_bin(folder, path)
    return digest(store.path_for(folder, address, draft=draft))


def discard(folder: Path, slug: str, base: str) -> str:
    """§ 4.10: bin the working copy `slug` and return the published entry's
    address. Takes no lock (PRESS-0337 § 4.7)."""
    if slug not in store.list_slugs(folder, draft=True):
        raise ChangedElsewhere(f"the draft {slug} is not there")
    path = store.path_for(folder, slug, draft=True)
    named = _replaced(folder, store.read(path))
    if named is None or digest(path) != base:
        raise ChangedElsewhere(f"the draft {slug} is not the working copy this window read")
    store.move_to_bin(folder, path)
    return named


def _discard(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.10."""
    form = form_fields(request)
    with lock, face.capture() as notices:
        try:
            named = discard(folder, form.get("slug", ""), form.get("base", ""))
        except (store.StoreError, ChangedElsewhere) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return failed(face, notices, failure)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=_edit_address(named))


def throw(folder: Path, slug: str, base: str, *, draft: bool) -> None:
    """PRESS-0128: bin the entry -- a draft, or a published entry and any
    working copy of it -- with its comments file. A published one leaves the
    site at the next press, and undoing that press brings it back. The entry
    goes first, so an interruption leaves at most a draft or a comments file
    behind, never an entry half thrown away. Takes no lock (PRESS-0337 § 4.7)."""
    if slug not in store.list_slugs(folder, draft=draft):
        raise ChangedElsewhere(f"the entry {slug} is not there")
    path = store.path_for(folder, slug, draft=draft)
    if digest(path) != base:
        raise ChangedElsewhere(f"the entry {slug} changed since this window read it")
    if draft:
        named = _replaced(folder, store.read(path))
    elif working_copy(folder, slug) is not None:
        raise ChangedElsewhere(f"the entry {slug} gained a working copy")
    else:
        named = slug
    if named is not None:
        store.move_to_bin(folder, store.path_for(folder, named, draft=False))
        # PRESS-0182 § 4.2: its old addresses go with it.
        forwards = store.read_forwards(folder)
        kept = {old: new for old, new in forwards.items() if new != named}
        if kept != forwards:
            store.write_forwards(folder, kept)
    comments = store.comments_path_for(folder, named or slug)
    if comments.is_file():
        store.move_to_bin(folder, comments)
    if draft:
        store.move_to_bin(folder, path)


def _throw(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0128: bin the entry this window shows (`throw`)."""
    form = form_fields(request)
    with lock, face.capture() as notices:
        try:
            throw(folder, form.get("slug", ""), form.get("base", ""),
                  draft=form.get("draft") == "1")
        except (store.StoreError, ChangedElsewhere, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return failed(face, notices, failure)
    return json_reply({"thrown": True, "notices": render_notices(notices)})


# PRESS-0015 s 4.6. Both pages carry this. Neither reloads itself (s 4.2):
# the reply is the only place the summary and the gathered notices exist, and a
# reload throws both away before he has read them. So the box is replaced with
# what came back, and a link back to his list is offered instead.
_UNDO_SCRIPT = pressing.SCRIPT + """
(() => {
  const button = document.querySelector("button[data-undo]");
  if (!button) return;
  // PRESS-0234: an editor's press row has one status line for both buttons.
  const said = document.getElementById("publish-status") ||
    document.getElementById("undo-status");
  const result = document.getElementById("undo-result");

  const show = (fragment, sentence) => {
    result.innerHTML = fragment || "";
    if (sentence) {
      const line = document.createElement("p");
      line.textContent = sentence;
      result.appendChild(line);
    }
    const back = document.createElement("p");
    const link = document.createElement("a");
    link.href = "/";
    link.textContent = say("script.undo.back");
    back.appendChild(link);
    result.appendChild(back);
    for (const box of [document.getElementById("editor"),
                       document.getElementById("listing")]) {
      if (box) box.hidden = true;
    }
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    said.textContent = say("script.press.undoing");
    try {
      const answer = await fetch("/undo", {method: "POST"});
      const text = await answer.text();
      said.textContent = "";
      if (answer.status !== 200) { show("", text); return; }
      const reply = JSON.parse(text);
      if (window.presslessPress.busy(reply)) return;
      said.textContent = reply.undone
        ? say("script.press.undone") : say("script.press.not_undone");
      show((reply.notices || "") + (reply.undone ? "" : reply.failure || ""),
           reply.undone ? reply.summary : "");
    } catch (error) {
      said.textContent = "";
      show("", say("script.undo.unreachable"));
    } finally {
      button.disabled = window.presslessPress.asking();
    }
  });
})();
"""


# PRESS-0012 § 4.7 and PRESS-0135: both editors' leaving, the entry's here and
# page_editor._PAGE_SCRIPT's. An unsaved change goes with the page unless a
# save is in flight. A keepalive request carries at most 64 KiB, so where the
# change is larger the browser asks before leaving instead. `unsaved` says a
# change waits and saving has not stopped; `sending` says a save is in flight.
LEAVING_SCRIPT = """
window.presslessLeaving = (address, fields, unsaved, sending) => {
  window.addEventListener("pagehide", () => {
    if (!unsaved() || sending()) return;
    fetch(address, {method: "POST", body: fields(), keepalive: true}).catch(() => {});
  });
  window.addEventListener("beforeunload", (event) => {
    if (unsaved() && new Blob([fields().toString()]).size > 60000) event.preventDefault();
  });
};
"""


# § 4.7: both editors' saving, the entry's here and page_editor._PAGE_SCRIPT's.
# `send` posts a change; `waiting` says one waits and saving has not stopped.
# A save runs about a second after `schedule`, never two at once. A request
# that posts what a save would post, or may move it, calls `settle` first: it
# waits out a save in flight, saves a waiting change first where `first` says
# so, and holds saves back until the request has answered (PRESS-0135,
# PRESS-0309, PRESS-0329). `release` lets them go, saving what was typed
# meanwhile. `sending` says a save or a held request is in flight.
SAVING_SCRIPT = """
window.presslessSaving = (send, waiting) => {
  let timer = null, held = null, done = null;
  const hold = () => { held = new Promise((resolve) => { done = resolve; }); };
  const free = () => { held = null; done(); };
  const schedule = () => { clearTimeout(timer); timer = setTimeout(save, 1000); };
  async function save() {
    if (held || !waiting()) return;
    hold();
    try { await send(); } finally { release(); }
  }
  async function settle(first) {
    for (;;) {
      clearTimeout(timer);
      while (held) await held;
      if (!first || !waiting()) break;
      first = false;
      await save();
    }
    hold();
  }
  function release() {
    free();
    if (waiting()) schedule();
  }
  return {schedule, settle, release, sending: () => held !== null};
};
"""


# PRESS-0260 § 4.4's reading of typed words, shared by both visual views: the
# page editor's and the entry's (PRESS-0346 § 4.4). The words are read from
# the element's nodes, never from innerHTML, and a paste is its plain text.
TYPING_SCRIPT = r"""
window.presslessTyping = (() => {
  const text = (value) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/ /g, " ");
  // blocks.address_allowed's rule, which the save holds to: the scheme read as
  // a browser reads it, outer spaces and controls stripped, tabs and line
  // breaks removed (PRESS-0306).
  const allowed = (href) => {
    const folded = href.replace(/^[\x00-\x20]+|[\x00-\x20]+$/g, "").replace(/[\t\n\r]/g, "");
    const scheme = /^([A-Za-z][A-Za-z0-9+.-]*):/.exec(folded);
    return !scheme || ["http", "https", "mailto"].includes(scheme[1].toLowerCase());
  };
  // `linkable` says which addresses a link may keep; `keep`, where given,
  // returns the tags to write for an element other words keep, such as the
  // entry editor's colour spans, or null.
  function inline(element, {linkable = allowed, keep = () => null} = {}) {
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
        } else if (tag === "a" && !linked && href && linkable(href)) {
          wrap('<a href="' + text(href).replace(/"/g, "&quot;") + '">', "</a>", child, true);
        } else if (keep(child)) {
          wrap(...keep(child), child, linked);
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

  function paste(doc, event) {
    event.preventDefault();
    const words = (event.clipboardData.getData("text/plain") || "").replace(/\s*\n\s*/g, " ");
    doc.execCommand("insertText", false, words);
  }
  return {text, allowed, inline, paste};
})();
"""


# PRESS-0346: the entry's visual view. The frame is the Builder's preview and
# runs no script; this one reaches into it, finds the body's blocks by
# position (§ 4.2), and makes the picked one typeable. What it posts is the
# blocks, kept by index or built anew (§ 4.5); _EDITOR_SCRIPT saves it.
_VISUAL_SCRIPT = r"""
(() => {
  const form = document.getElementById("editor");
  const frame = document.getElementById("preview");
  const panel = document.getElementById("panel");
  const given = JSON.parse(document.getElementById("blocks").textContent);
  const {text, inline, paste} = window.presslessTyping;
  // § 4.3: a link takes only an address the link mark takes.
  const LINK = new RegExp(given.link);
  const linkable = (href) => LINK.test(href);
  // § 4.4: a colour span is kept exactly as to_html wrote it.
  const NAMED = Object.values(given.colours.named);
  const PICKED = given.colours.picked;
  const colour = (style) => style !== null && (NAMED.includes(style) || (PICKED !== null
    && style.startsWith(PICKED.prefix)
    && new RegExp(PICKED.pattern).test(style.slice(PICKED.prefix.length))));
  const keep = (element) => {
    const style = element.localName === "span" ? element.getAttribute("style") : null;
    return colour(style)
      ? ['<span style="' + text(style).replace(/"/g, "&quot;") + '">', "</span>"] : null;
  };
  const words = (element) => inline(element, {linkable, keep});

  // ---- the model -------------------------------------------------------
  // One item per block, in order. `index` is its place in the file as last
  // written, or null for one not written yet; `edited` says its marks were
  // changed in the panel's box.
  let rev = 0;
  const model = [];
  let removed = [];
  let picked = null, editing = null, waitingPreview = null, selected = null;
  const node = (block, index) => ({kind: block.kind, typed: block.typed, marks: block.marks,
    name: block.name || "", caption: block.caption || "", index, changed: index === null,
    edited: false, rev: 0, el: null, held: null});
  function open(blocks) {
    if (picked) show(null, false);
    model.length = 0;
    removed = [];
    editing = waitingPreview = null;
    (blocks || given.blocks).forEach((block, at) => model.push(node(block, at)));
  }
  open(given.blocks);
  const changed = () => window.presslessEntryPage.changed();
  const touch = (item) => { item.changed = true; item.rev = ++rev; changed(); };
  const typeable = (item) => item && item.kind !== "photo" && item.typed && !item.edited;

  // ---- what is posted (§ 4.5) ------------------------------------------
  const empty = (item) => item.kind === "photo" ? !item.name
    : typeable(item) && item.el !== null && !item.el.textContent.trim();
  // A quotation's paragraphs; words typed loose in it, as a browser may
  // leave them, are a paragraph of their own.
  const quoted = (element) => {
    const parts = [];
    let loose = null;
    for (const child of element.childNodes) {
      if (child.nodeType === Node.ELEMENT_NODE && ["p", "div"].includes(child.localName)) {
        parts.push(child);
        loose = null;
      } else {
        if (!loose) parts.push(loose = element.ownerDocument.createElement("p"));
        loose.append(child.cloneNode(true));
      }
    }
    return parts.map(words);
  };
  function itemOf(item) {
    if (!item.changed && item.index !== null) return {keep: item.index};
    if (item.edited) return {marks: item.marks};
    if (item.kind === "photo") return {photo: item.name, caption: item.caption};
    if (item.kind === "quote") return {quote: quoted(item.el)};
    return {paragraph: words(item.el)};
  }
  function post() {
    // An emptied block is posted as removed, and waits on the page to be typed in.
    const sent = model.filter((item) => !(item.changed && empty(item)));
    const revs = new Map(model.map((item) => [item, item.rev]));
    const gone = removed.filter((item) => item.index !== null);
    const named = [...gone.map((item) => item.index), ...model
      .filter((item) => item.changed && item.index !== null).map((item) => item.index)];
    return {
      blocks: JSON.stringify(sent.map(itemOf)),
      removed: JSON.stringify(named),
      saved(reply) {
        removed = removed.filter((item) => !gone.includes(item));
        if (reply.outline.length !== sent.length) {
          // A marks box written as more or fewer blocks: open the body afresh.
          open(reply.outline);
          rebuild(reply.preview);
          return;
        }
        model.forEach((item) => { if (!sent.includes(item)) item.index = null; });
        sent.forEach((item, at) => {
          item.index = at;
          if (revs.get(item) !== item.rev) return;
          const block = reply.outline[at];
          Object.assign(item, {changed: false, edited: false, kind: block.kind,
                               typed: block.typed, marks: block.marks});
        });
        if (picked) fill();
        if (reply.preview) rebuild(reply.preview);
      },
    };
  }

  // ---- the frame (§ 4.2) -----------------------------------------------
  const STYLE = "[data-pressless-picked]{box-shadow:0 0 0 3px #e9a23b}"
    + "[data-pressless-empty]:empty::before{content:attr(data-pressless-empty);opacity:.5}";
  const bodyOf = (doc) => [...doc.querySelectorAll("[class]")]
    .find((element) => element.getAttribute("class") === given.body_class) || null;
  function made(doc, item) {
    if (item.kind === "photo") {
      const figure = doc.createElement("figure");
      figure.append(doc.createElement("img"));
      return figure;
    }
    const element = doc.createElement(item.kind === "quote" ? "blockquote" : "p");
    if (item.kind === "quote") element.append(doc.createElement("p"));
    return element;
  }
  function photo(item) {
    const image = item.el && item.el.querySelector("img");
    if (!image) return;
    if (item.name) image.src = given.originals + encodeURIComponent(item.name);
    image.alt = item.caption;
  }
  function pair() {
    const doc = frame.contentDocument;
    // The frame's first, empty document is not the preview yet.
    if (!doc || !doc.body || doc.URL === "about:blank" || form.dataset.view !== "visual") return;
    // A preview that failed shows its failure, not an entry; a save rebuilds it.
    const holder = bodyOf(doc);
    if (!holder) return;
    const shown = [...holder.children];
    const held = model.filter((item) => item.index !== null);
    if (shown.length !== held.length || held.some((item) => item.index >= shown.length)) {
      window.presslessEntryPage.switchTo("marks", say("script.entry.unpaired"));
      return;
    }
    const style = doc.createElement("style");
    style.textContent = STYLE;
    doc.head.appendChild(style);
    for (const item of model) {
      item.el = item.index !== null ? shown[item.index] : made(doc, item);
      // What was typed since the save outlives the frame it was typed in.
      if (item.changed && item.held !== null) item.el.innerHTML = item.held;
      if (item.changed && item.kind === "photo") photo(item);
      holder.append(item.el);
    }
    // A body with nothing in it offers one empty paragraph to type into.
    if (!model.length) addAfter(null, "paragraph", false);
    doc.addEventListener("click", clicked, true);
    doc.addEventListener("keydown", keyed);
    doc.addEventListener("input", typed);
    doc.addEventListener("paste", pasted);
    doc.addEventListener("selectionchange", () => {
      const chosen = doc.getSelection();
      if (picked && picked.el && chosen.rangeCount && !chosen.isCollapsed
          && picked.el.contains(chosen.anchorNode)) selected = chosen.getRangeAt(0).cloneRange();
    });
    doc.addEventListener("focusout", () => { editing = null; setTimeout(settled, 0); });
    doc.addEventListener("focusin", (event) => {
      editing = picked && picked.el && picked.el.contains(event.target) ? picked : null;
    });
    if (picked) show(picked, false);
  }
  // § 4.5: never rebuilt while the caret is in a block.
  function rebuild(address) {
    waitingPreview = address ? address + "?n=" + Date.now() : frame.src;
    settled();
  }
  function settled() {
    if (editing || !waitingPreview) return;
    for (const item of model) item.held = item.changed && item.el ? item.el.innerHTML : null;
    const scrolled = frame.contentWindow ? frame.contentWindow.scrollY : 0;
    frame.addEventListener("load", () => frame.contentWindow.scrollTo(0, scrolled),
                           {once: true});
    frame.src = waitingPreview;
    waitingPreview = null;
  }
  frame.addEventListener("load", pair);
  if (frame.contentDocument && frame.contentDocument.readyState === "complete"
      && frame.contentDocument.body) pair();

  // ---- picking, and the side panel (§ 4.3) -----------------------------
  function clicked(event) {
    event.preventDefault();
    const found = model.find((item) => item.el && item.el.contains(event.target)) || null;
    if (found !== picked) show(found, Boolean(found));
  }
  function letGo(event) {
    if (event.key !== "Escape" || !picked) return false;
    event.preventDefault();
    show(null, false);
    return true;
  }
  panel.addEventListener("keydown", letGo);
  function show(item, focus) {
    if (picked && picked.el) {
      picked.el.removeAttribute("contenteditable");
      picked.el.removeAttribute("data-pressless-picked");
    }
    picked = item;
    selected = null;
    if (picked && picked.el) {
      picked.el.setAttribute("data-pressless-picked", "");
      if (typeable(picked)) {
        picked.el.setAttribute("contenteditable", "true");
        const empty = picked.kind === "quote" ? picked.el.querySelector("p") : picked.el;
        if (empty) empty.setAttribute("data-pressless-empty",
                                      say("script.entry.kind." + picked.kind));
        if (focus) {
          picked.el.focus();
          // The caret goes in a quotation's paragraph, never beside it.
          if (empty && empty !== picked.el && !picked.el.textContent) {
            picked.el.ownerDocument.getSelection().collapse(empty, 0);
          }
        }
      }
    }
    fill();
  }
  const field = (name) => panel.querySelector("[data-field=" + name + "]");
  const act = (name) => panel.querySelector("[data-act=" + name + "]");
  function fill() {
    const part = !picked ? "" : picked.kind === "photo" ? "photo"
      : typeable(picked) ? "typed" : "marks";
    panel.querySelectorAll("[data-for]").forEach((shown) => {
      shown.hidden = shown.dataset.for !== part;
    });
    document.getElementById("picked").textContent = picked
      ? say("script.visual.picked", {kind: say("script.entry.kind." + picked.kind)})
      : say("script.entry.nothing");
    document.getElementById("panel-said").textContent = "";
    if (picked) {
      field("name").value = picked.name;
      field("caption").value = picked.caption;
      field("marks").value = picked.marks;
    }
    const at = model.indexOf(picked);
    act("up").disabled = !picked || at <= 0;
    act("down").disabled = !picked || at >= model.length - 1;
    act("remove").disabled = !picked;
    document.getElementById("add-where").textContent =
      say(picked ? "script.entry.below" : "script.entry.end");
  }
  panel.addEventListener("input", (event) => {
    // The panel says what changed itself, so choosing a colour to use, or a
    // kind to add, saves nothing.
    event.stopPropagation();
    const name = event.target.dataset.field;
    if (!picked || !name) return;
    if (name === "marks") {
      picked.marks = event.target.value;
      picked.edited = true;
    } else {
      picked[name] = event.target.value;
      photo(picked);
    }
    touch(picked);
  });

  // Bold, Italic, Link and the colours keep the caret in the frame.
  panel.querySelectorAll("[data-act=bold], [data-act=italic], [data-act=link], "
                         + "[data-colour], [data-act=colour]").forEach((button) => {
    button.addEventListener("mousedown", (event) => event.preventDefault());
  });
  ["bold", "italic", "link"].forEach((name) => {
    act(name).addEventListener("click", () => format(name));
  });
  function format(name) {
    if (!typeable(picked) || !picked.el) return;
    const doc = frame.contentDocument;
    if (name === "link") {
      const address = window.prompt(say("script.visual.ask_link"), "https://");
      if (!address) return;
      if (!linkable(address)) {
        document.getElementById("panel-said").textContent = say("script.entry.link_refused");
        return;
      }
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
  // § 4.4: a colour wraps the words picked in the span its mark writes.
  function paint(style) {
    if (!typeable(picked) || !selected || selected.collapsed) return;
    const doc = frame.contentDocument;
    const span = doc.createElement("span");
    span.setAttribute("style", style);
    span.append(selected.extractContents());
    selected.insertNode(span);
    selected = null;
    touch(picked);
  }
  panel.querySelectorAll("[data-colour]").forEach((button) => {
    button.addEventListener("click", () => paint(given.colours.named[button.dataset.colour]));
  });
  act("colour").addEventListener("click", () => {
    if (PICKED) paint(PICKED.prefix + document.getElementById("picked-colour").value);
  });

  // ---- adding, moving, removing ----------------------------------------
  function addAfter(at, kind, focus) {
    const item = node({kind, typed: true, marks: ""}, null);
    model.splice(at ? model.indexOf(at) + 1 : model.length, 0, item);
    const doc = frame.contentDocument;
    const holder = doc && bodyOf(doc);
    if (holder) {
      item.el = made(doc, item);
      if (at && at.el) at.el.after(item.el); else holder.append(item.el);
    }
    show(item, focus);
    return item;
  }
  act("add").addEventListener("click", () => {
    addAfter(picked, document.getElementById("add-kind").value, true);
  });
  function move(by) {
    if (!picked) return;
    const at = model.indexOf(picked), to = at + by;
    if (to < 0 || to >= model.length) return;
    const other = model[to];
    model.splice(at, 1);
    model.splice(to, 0, picked);
    if (picked.el && other.el) {
      if (by < 0) other.el.before(picked.el); else other.el.after(picked.el);
    }
    changed();
    fill();
  }
  act("up").addEventListener("click", () => move(-1));
  act("down").addEventListener("click", () => move(1));
  function drop(item) {
    model.splice(model.indexOf(item), 1);
    if (item.index !== null) removed.push(item);
    if (item.el) item.el.remove();
    changed();
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
    if (typeable(picked) && picked.el) paste(frame.contentDocument, event);
  }
  function keyed(event) {
    if (letGo(event)) return;
    if (!typeable(picked) || !picked.el || !picked.el.contains(event.target)) return;
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
    if (event.key === "Enter" && picked.kind === "quote") {
      // In a quotation, a new paragraph of the same quotation.
      event.preventDefault();
      doc.execCommand("insertParagraph");
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
      touch(picked);
      const item = addAfter(picked, "paragraph", true);
      if (item.el) {
        item.el.append(...[...after.childNodes].filter((part) => part.textContent !== ""
                                                        || part.nodeName === "BR"));
        selection.collapse(item.el, 0);
      }
      touch(item);
      return;
    }
    if (event.key === "Backspace" && picked.kind === "paragraph" && selection.isCollapsed
        && selection.rangeCount) {
      const head = doc.createRange();
      head.setStart(picked.el, 0);
      head.setEnd(selection.anchorNode, selection.anchorOffset);
      if (head.toString() !== "" || head.cloneContents().querySelector("br, img")) return;
      const above = model[model.indexOf(picked) - 1];
      if (!above || above.kind !== "paragraph" || !typeable(above) || !above.el) return;
      event.preventDefault();
      const joined = above.el.childNodes.length;
      above.el.append(...picked.el.childNodes);
      const gone = picked;
      touch(above);
      show(above, true);
      drop(gone);
      selection.collapse(above.el, joined);
    }
  }

  // ---- a photograph Pressless holds (§ 4.3) ------------------------------
  const chooser = document.getElementById("panel-photograph-file");
  act("photograph").addEventListener("click", () => { chooser.value = ""; chooser.click(); });
  chooser.addEventListener("change", async () => {
    const file = chooser.files[0];
    if (!file || !picked || picked.kind !== "photo") return;
    const answer = await fetch("/photograph?name=" + encodeURIComponent(file.name),
                               {method: "POST", body: file});
    const reply = await answer.text();
    if (answer.status !== 200) { document.getElementById("failure").innerHTML = reply; return; }
    const name = JSON.parse(reply).name;
    if (![...field("name").options].some((option) => option.value === name)) {
      field("name").append(new Option(name, name));
    }
    field("name").value = name;
    picked.name = name;
    photo(picked);
    touch(picked);
  });

  window.presslessEntry = {
    post, open,
    letGo: () => show(null, false),
    reload: () => rebuild(null),
  };
  fill();
})();
"""


# The entry's script (§ 4.7). A change saves about a second after the last one,
# never two saves at once, and on leaving only where a change is unsaved. Its
# twin is page_editor._PAGE_SCRIPT: a fix to how either saves or presses is
# owed to both, and both save through SAVING_SCRIPT.
_EDITOR_SCRIPT = pressing.SCRIPT + LEAVING_SCRIPT + SAVING_SCRIPT + """
(() => {
  const form = document.getElementById("editor");
  const state = {slug: form.dataset.slug, draft: form.dataset.draft, base: form.dataset.base};
  const status = document.getElementById("save-status");
  let dirty = false, stopped = false;

  // PRESS-0346 § 4.5: the visual view's snapshot of the body, or null in
  // the marks view, where the box is posted.
  const posting = () => form.dataset.view === "visual" && window.presslessEntry
    ? window.presslessEntry.post() : null;
  const fields = (posted = posting()) => {
    const data = new URLSearchParams();
    data.set("slug", state.slug); data.set("draft", state.draft); data.set("base", state.base);
    for (const name of ["title", "categories", "tags"]) {
      data.set(name, form.elements[name].value);
    }
    if (posted) {
      data.set("view", "visual");
      data.set("blocks", posted.blocks);
      data.set("removed", posted.removed);
    } else {
      data.set("body", form.elements.body.value);
    }
    return data;
  };
  // The body as last written and its outline, which a switch opens from.
  const box = form.elements.body;
  let latest = {body: box.value, outline: null};
  const written = (reply, posted) => {
    if (!("body" in reply)) return;
    latest = {body: reply.body, outline: reply.outline};
    if (posted) {
      box.value = reply.body;
      posted.saved(reply);
    }
  };
  // PRESS-0339: while a press runs, its words stay on the status line.
  let pressing = false;
  const adopt = (reply) => {
    state.slug = reply.slug; state.draft = reply.draft ? "1" : "0"; state.base = reply.base;
    document.querySelectorAll("input[name=base]").forEach((input) => { input.value = reply.base; });
    history.replaceState(null, "", "/edit?slug=" + encodeURIComponent(reply.slug));
    document.querySelectorAll("#standing [data-when]").forEach((part) => {
      part.hidden = part.dataset.when !== state.draft;
    });
    document.querySelectorAll("#standing input[name=slug]").forEach((input) => {
      input.value = reply.slug;
    });
    document.getElementById("notices").innerHTML = reply.notices;
    if ("missing" in reply) showMissing(reply.missing);
    // PRESS-0182: a proof's address cannot change, so its page offers none.
    // _page always draws the field, hidden where it does not apply.
    const addressField = document.getElementById("address");
    if (state.draft === "1" && form.dataset.draft === "0") {
      addressField.hidden = true;
    }
    // PRESS-0128: a press puts a draft on his site without reloading the page.
    // PRESS-0185: from then on this is a published entry's page.
    if (state.draft === "0") {
      form.dataset.onSite = "1";
      form.dataset.draft = "0";
      const draftLine = document.getElementById("draft-standing");
      if (draftLine) draftLine.remove();
      document.getElementById("standing").hidden = false;
      // PRESS-0186: and its address can change again.
      addressField.hidden = false;
      document.querySelector("button[data-editor=throw]").textContent =
        say("script.editor.throw_entry");
    }
    if (!pressing) document.getElementById("publish-status").textContent = standing();
  };
  // PRESS-0234: what the press row's status line says between presses.
  const standing = () => say(state.draft === "0" ? "script.standing.on_site"
    : form.dataset.onSite === "1" ? "script.standing.changes" : "script.standing.off_site");
  window.presslessPress.standing(standing);
  const stop = (text) => {
    stopped = true;
    status.textContent = say("script.editor.not_saved");
    document.getElementById("failure").innerHTML = text;
  };

  // PRESS-0016: a photograph this entry names that Pressless does not have.
  // A press still stops on it; this says so while he writes.
  const missingLine = document.getElementById("photograph-missing");
  function showMissing(names) {
    missingLine.hidden = names.length === 0;
    missingLine.textContent = names.length === 0 ? "" :
      say(names.length === 1 ? "script.editor.missing_one" : "script.editor.missing_many",
          {names: names.join(", ")});
  }
  showMissing(JSON.parse(form.dataset.missing));

  async function send() {
    dirty = false; status.textContent = say("script.editor.saving");
    try {
      const posted = posting();
      const answer = await fetch("/save", {method: "POST", body: fields(posted)});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      const reply = JSON.parse(text);
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      written(reply, posted);
      if (reply.preview && !posted) {
        document.getElementById("preview").src = reply.preview + "?n=" + Date.now();
      }
      status.textContent = say("script.editor.saved");
    } catch (error) {
      stop("");
    }
  }
  // Publish, address and throw post the address and base a save would post,
  // and may move them, so each settles first and releases after.
  const {schedule, settle, release, sending} =
    window.presslessSaving(send, () => dirty && !stopped);

  const changed = () => { dirty = true; schedule(); };
  form.addEventListener("input", (event) => {
    if (event.target.name === "address") return;
    changed();
  });
  window.presslessLeaving("/save", fields, () => !stopped && dirty, sending);

  const publish = document.querySelector("button[data-editor=publish]");
  publish.addEventListener("click", async () => {
    // PRESS-0339: said at once, though a save in flight is waited out first.
    const said = document.getElementById("publish-status");
    publish.disabled = true;
    said.textContent = say("script.press.checking");
    pressing = true;
    // PRESS-0345: what waits is saved first, so the plan reads it; saves stay
    // held while the box is open.
    await settle(true);
    const unpressed = () => {
      said.textContent = standing(); pressing = false; publish.disabled = false; release();
    };
    try {
      const asked = new URLSearchParams({slug: state.slug});
      if (!(await window.presslessCheck(asked))) { unpressed(); return; }
    } catch (error) {
      unpressed(); stop(""); return;
    }
    said.textContent = say("script.press.publishing");
    try {
      const posted = posting();
      const body = fields(posted);
      dirty = false;
      const answer = await fetch("/publish", {method: "POST", body: body});
      const text = await answer.text();
      if (answer.status !== 200) { said.textContent = standing(); stop(text); return; }
      const reply = JSON.parse(text);
      // Another press runs: nothing was saved, so the change is still to save.
      if (window.presslessPress.busy(reply)) { dirty = true; return; }
      adopt(reply);
      written(reply, posted);
      document.getElementById("failure").innerHTML = reply.failure || "";
      said.textContent = reply.published
        ? say("script.press.published") : say("script.press.not_published");
      if (reply.published) window.presslessPress.viewable();
    } catch (error) {
      said.textContent = standing(); stop("");
    } finally {
      pressing = false;
      publish.disabled = window.presslessPress.asking();
      release();
    }
  });

  // PRESS-0346 § 4.1: the switch changes view in place. What was typed is
  // saved first, and the other view opens from the body as written.
  const views = {marks: document.getElementById("marks-view"),
                 visual: document.getElementById("panel")};
  async function switchTo(to, notice) {
    if (to === form.dataset.view) return;
    await settle(true);
    release();
    if (stopped) return;
    if (to === "marks") window.presslessEntry.letGo();
    form.dataset.view = to;
    document.querySelectorAll("a[data-switch]").forEach((link) => {
      link.hidden = link.dataset.switch === to;
    });
    for (const [view, part] of Object.entries(views)) part.hidden = view !== to;
    if (to === "marks") {
      box.value = latest.body;
    } else {
      window.presslessEntry.open(latest.outline);
      window.presslessEntry.reload();
    }
    if (notice) {
      document.getElementById("notices").replaceChildren(
        Object.assign(document.createElement("p"), {textContent: notice}));
    } else {
      fetch("/edit/view", {method: "POST", body: new URLSearchParams({view: to})})
        .catch(() => {});
    }
  }
  document.querySelectorAll("a[data-switch]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      switchTo(link.dataset.switch);
    });
  });
  window.presslessEntryPage = {changed, switchTo};

  // PRESS-0016: the chosen file is kept as an original, and its picture mark
  // goes on a line of its own where he was typing.
  const picker = document.getElementById("photograph-file");
  const photoSaid = document.getElementById("photograph-status");
  let caret = null;
  document.querySelector("button[data-editor=photograph]").addEventListener("click", () => {
    caret = [box.selectionStart, box.selectionEnd];
    picker.value = "";
    picker.click();
  });
  picker.addEventListener("change", async () => {
    const file = picker.files[0];
    if (!file) return;
    photoSaid.textContent = say("script.editor.adding_photograph");
    try {
      const answer = await fetch("/photograph?name=" + encodeURIComponent(file.name),
                                 {method: "POST", body: file});
      const text = await answer.text();
      photoSaid.textContent = "";
      if (answer.status !== 200) {
        document.getElementById("failure").innerHTML = text;
        return;
      }
      const reply = JSON.parse(text);
      document.getElementById("notices").innerHTML = reply.notices;
      const [start, end] = caret || [box.value.length, box.value.length];
      const before = box.value.slice(0, start), after = box.value.slice(end);
      const lead = before === "" || before.endsWith("\\n") ? "" : "\\n";
      const mark = lead + "{photo: " + reply.name + "}" + (after.startsWith("\\n") ? "" : "\\n");
      box.value = before + mark + after;
      box.focus();
      box.setSelectionRange(before.length + mark.length, before.length + mark.length);
      photoSaid.textContent = say("script.editor.photograph_added", {name: reply.name});
      dirty = true; schedule();
    } catch (error) {
      photoSaid.textContent = "";
      stop("");
    }
  });

  const button = document.querySelector("button[data-editor=address]");
  if (button) {
    button.addEventListener("click", async () => {
      await settle(true);
      try {
        if (stopped) return;
        // PRESS-0182: asked first, since links to it are out in the world.
        if (state.draft === "0" && !window.confirm(say("script.editor.confirm_address"))) return;
        const data = new URLSearchParams();
        data.set("slug", state.slug); data.set("draft", state.draft);
        data.set("base", state.base);
        data.set("address", document.querySelector("input[name=address]").value);
        const answer = await fetch("/address", {method: "POST", body: data});
        const text = await answer.text();
        if (answer.status !== 200) { stop(text); return; }
        const reply = JSON.parse(text);
        document.getElementById("address-hint").textContent = reply.hint || "";
        if (!reply.hint) adopt(reply);
      } catch (error) {
        stop("");
      } finally {
        release();
      }
    });
  }

  // PRESS-0128: asked first, since a published entry leaves his site. Saves
  // settle before, and none follows: the file it would write is in the bin.
  const throwAway = document.querySelector("button[data-editor=throw]");
  throwAway.addEventListener("click", async () => {
    const question = say(form.dataset.onSite === "1"
      ? "script.editor.confirm_throw_entry" : "script.editor.confirm_throw_draft");
    if (!window.confirm(question)) return;
    await settle(true);
    try {
      if (stopped) return;
      const data = new URLSearchParams();
      data.set("slug", state.slug); data.set("draft", state.draft); data.set("base", state.base);
      const answer = await fetch("/throw", {method: "POST", body: data});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      stopped = true;
      window.location.assign("/");
    } catch (error) {
      stop("");
    } finally {
      release();
    }
  });
})();
"""
