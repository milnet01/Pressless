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

from pressless import builder, cheatsheet, paths, photographs, settings, store
from pressless.face import (
    SENTENCES,
    TRUE_COLOURS,
    Face,
    Reply,
    Request,
    Sentence,
    Site,
    render_notices,
    within,
)

PREVIEW_FOLDER = "preview"          # inside Pressless's own folder; the Face's alone
REPLACES = "Replaces"               # the header naming the published entry a copy changes
UNTITLED = "untitled"
COPY_SUFFIX = "-changes"
LONGEST_ADDRESS = 60
PREVIEW_ADDRESS = "/preview/"
ASSETS_ADDRESS = "/preview/assets/"
ORIGINALS_ADDRESS = "/originals/"


class ChangedElsewhere(Exception):
    """The file is not the one this window last saw (§ 4.8)."""


class TooManyCopies(Exception):
    """Two drafts replace one published entry (§ 4.1)."""


class LeftOut(store.StoreNotice):
    """A typed category or tag with nothing an address can keep (§ 4.8)."""


# Added here rather than in face.py, which cannot import this module back
# (§ 4.1).
SENTENCES[ChangedElsewhere] = Sentence(
    "This entry was changed in another window or outside Pressless, so Pressless "
    "did not save over it.",
    Site.UNCHANGED,
    "Copy anything you typed since, then open the entry again from your list.",
)
SENTENCES[TooManyCopies] = Sentence(
    "More than one draft holds unpublished changes to this entry, so Pressless did "
    "not open it.",
    Site.UNCHANGED,
    "Open your Pressless-data folder, keep one of those drafts, and move the others "
    "out of the drafts folder.",
)
SENTENCES[photographs.NotAPhotograph] = Sentence(
    "That file is not a picture Pressless can put on your site, so it was not added.",
    Site.UNCHANGED,
    "Choose a JPEG, PNG, WebP or GIF photograph.",
)

# Every write, preview and publish runs under it; a threading.Lock cannot be
# taken twice, so `save` leaves it to its caller (PRESS-0013 § 4.1).
LOCK = threading.Lock()

_JSON = "application/json"
_HTML = "text/html; charset=utf-8"


def address_for(title: str) -> str:
    """A new entry's address, from its title (§ 4.1)."""
    return name_address(title) or UNTITLED


def name_address(name: str) -> str:
    """`address_for`'s rule for a category or tag; "" where nothing is left."""
    text = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf"))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:LONGEST_ADDRESS].strip("-")


def free_address(folder: Path, wanted: str) -> str:
    """`wanted`, or the first of `wanted-2`, `wanted-3` … no entry holds, no old
    address forwards from, and the Store accepts (§ 4.1; PRESS-0182)."""
    # Read once, outside the loop: its StoreError must stop the search, not be
    # skipped as a refused name (PRESS-0182 § 4.2).
    forwarded = store.read_forwards(folder)
    number = 1
    while True:
        candidate = wanted if number == 1 else f"{wanted}-{number}"
        try:
            if candidate not in forwarded and not store.exists(folder, candidate):
                return candidate
        except store.StoreError:
            pass  # a name the Store refuses, such as a Windows device name
        number += 1


def working_copy(folder: Path, slug: str) -> str | None:
    """The draft holding unpublished changes to the published entry `slug`
    (§ 4.1). Raises TooManyCopies where two drafts do."""
    if slug not in store.list_slugs(folder, draft=False):
        return None
    found = [draft for draft in store.list_slugs(folder, draft=True)
             if _named(folder, draft) == slug]
    if len(found) > 1:
        raise TooManyCopies(f"{len(found)} drafts replace the entry {slug}")
    return found[0] if found else None


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
    face.add_page("POST", "/address", route(_address))
    face.add_page("POST", "/discard", route(_discard))
    face.add_page("POST", "/throw", route(_throw))
    face.add_page("POST", "/photograph", route(_photograph))
    face.add_page("POST", "/journal", route(_journal))
    face.add_files(ASSETS_ADDRESS, within(folder / paths.PREVIEW_ASSETS))
    face.add_files(PREVIEW_ADDRESS, within(folder / PREVIEW_FOLDER))
    face.add_files(ORIGINALS_ADDRESS, lambda name: store.photograph_path_for(folder, name))


# ------------------------------------------------------------- the Store ---


def _named(folder: Path, draft: str) -> str | None:
    """The `Replaces` value of a draft, or None -- an unreadable one included,
    which the list reports on its own (§ 4.5)."""
    try:
        entry = store.read(store.path_for(folder, draft, draft=True))
    except store.StoreError:
        return None
    return _replaces(entry)


def _replaces(entry: store.Entry) -> str | None:
    return next((value for name, value in entry.extra if name == REPLACES), None)


def _replaced(folder: Path, entry: store.Entry) -> str | None:
    """The published entry a draft is a working copy of, or None: a draft whose
    `Replaces` names no published entry is an ordinary draft (§ 4.1)."""
    named = _replaces(entry)
    if named is None or named not in store.list_slugs(folder, draft=False):
        return None
    return named


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _form(request: Request) -> dict[str, str]:
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


def _names_of(folder: Path, value: str, box: str) -> tuple[str, ...]:
    """§ 4.8 step 3: a part the Store takes is kept, any other becomes an
    address, and repeats are dropped. A part that leaves nothing the Store would
    take is left out, and a notice names it."""
    names: list[str] = []
    for part in value.split(","):
        typed = part.strip()
        if not typed:
            continue
        name = typed if _usable(folder, typed) else name_address(typed)
        usable = bool(name) and _usable(folder, name)
        if not usable:
            warnings.warn(LeftOut(
                f"\u201c{typed}\u201d was left out of the {box}: Pressless cannot "
                "make it part of a web address. Give it another name."), stacklevel=2)
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


def _failed(face: Face, notices: list[str], failure: Exception) -> Reply:
    body = render_notices(notices) + face.fail(failure, publishing=False)
    return Reply(body.encode("utf-8"), _HTML, status=409)


def _json(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


def _edit_address(slug: str) -> str:
    return "/edit?slug=" + urllib.parse.quote(slug, safe="")


# ---------------------------------------------------------------- routes ---


def _journal_switch(journal: bool | None, published: bool) -> str:
    """PRESS-0214 § 4.5: whether the journal is on, and the one button that
    switches it. None where the options file could not be read."""
    if journal is None:
        return ""
    if journal:
        said = "Your journal is on."
        if published:
            said += (" Turning it off takes your published entries off your site "
                     "at your next publish; turning it on again brings them back.")
        button = "Turn the journal off"
    else:
        said = ("Your journal is off, so entries are not on your site. A link to "
                "the journal in your menu stays until you remove it from the header "
                "or navigation in Your pages.")
        button = "Turn the journal on"
    return (f'<form method="post" action="/journal"><p>{said} '
            f"<button>{button}</button></p></form>")


def _journal(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0214 § 4.5: switch the journal to the opposite of what it is."""
    with lock, face.capture() as notices:
        try:
            store.write_journal(folder, not store.journal_on(folder))
        except store.StoreError as exc:
            return _failed(face, notices, exc)
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
        try:
            pages = _pages(folder)
        except store.StoreError as exc:
            first_failure = first_failure or exc
            pages = "<p>Pressless cannot open your pages folder.</p>"
        try:
            journal: bool | None = store.journal_on(folder)
        except store.StoreError as exc:
            first_failure = first_failure or exc
            journal = None
    # Every listed slug, readable or not: _replaced and working_copy ask
    # list_slugs, so an unreadable published entry still has its working copy
    # (PRESS-0162).
    published = {entry.slug for entry in readable[False]} | set(unreadable[False])
    changed = {_replaces(entry) for entry in readable[True]} & published
    drafts = [entry for entry in readable[True] if _replaces(entry) not in published]

    def rows(entries: list[store.Entry], broken: list[str]) -> str:
        ordered = sorted(sorted(entries, key=lambda entry: entry.slug),
                         key=lambda entry: entry.date, reverse=True)
        items = []
        for entry in ordered:
            note = (" <em>changes not on your site yet</em>"
                    if entry.slug in changed else "")
            items.append(
                f'<li><a href="{html.escape(_edit_address(entry.slug), quote=True)}">'
                f"{html.escape(entry.title or 'untitled')}</a> "
                f"<small>{entry.date:%d %b %Y}</small>{note}</li>")
        items.extend(f"<li>{html.escape(slug)} <em>Pressless cannot open this file</em></li>"
                     for slug in broken)
        return "<ul>" + "".join(items) + "</ul>" if items else "<p>None yet.</p>"

    failure = face.fail(first_failure, publishing=False) if first_failure else ""
    return (render_notices(notices) + failure +
            '<h1>Your writing</h1>'
            # PRESS-0023 § 4.9: what other parts show here, without this
            # module importing them.
            + "".join(face.list_pieces(above=True)) +
            '<div id="undo-result"></div>'
            '<div id="listing">'
            '<form method="post" action="/new"><label>Title '
            '<input name="title" autocomplete="off"></label> '
            f"{_template_choice(folder)}"
            "<button>New entry</button></form>"
            # PRESS-0015 § 4.6: it always shows, and nothing asks GitHub before
            # showing it (§ 3 decision 3).
            '<p><button type="button" data-undo>Undo the last press</button> '
            '<span id="undo-status"></span></p>'
            f"{_journal_switch(journal, bool(published))}"
            # PRESS-0189: each list is a card.
            f'<section class="card"><h2>Drafts</h2>{rows(drafts, unreadable[True])}</section>'
            '<section class="card"><h2>On your site</h2>'
            f"{rows(readable[False], unreadable[False])}</section>"
            f'<section class="card"><h2>Your pages</h2>{pages}</section>'
            "</div>"
            + "".join(face.list_pieces(above=False)) +
            f"<script>{_UNDO_SCRIPT}</script>")


def _template_choice(folder: Path) -> str:
    """PRESS-0017 § 4.3: a blank entry first, then each template that reads,
    labelled with its title or, where that is empty, its name."""
    options = ['<option value="">A blank entry</option>']
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
    return f'<label>Start from <select name="template">{"".join(options)}</select></label> '


def _pages(folder: Path) -> str:
    """PRESS-0014 § 4.4: each fixed page, then the three furniture files, each
    saying where its changes are not on the site yet. Drawn from the Store
    alone, so this module imports nothing of page_editor.py."""
    rows = [(store.PAGES_FOLDER, name, "Home" if name == "index" else name)
            for name in store.list_html(folder, store.PAGES_FOLDER)]
    rows += [(store.FURNITURE_FOLDER, name, name.capitalize())
             for name in ("header", "footer", "navigation")]
    items = []
    for kind, name, label in rows:
        address = "/page?" + urllib.parse.urlencode({"kind": kind, "name": name})
        note = (" <em>changes not on your site yet</em>"
                if store.html_path_for(folder, kind, name, waiting=True).is_file() else "")
        items.append(f'<li><a href="{html.escape(address, quote=True)}">'
                     f"{html.escape(label)}</a>{note}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def _new(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.6."""
    form = _form(request)
    title, chosen = form.get("title", ""), form.get("template", "")
    with lock, face.capture() as notices:
        try:
            # PRESS-0017 § 4.3: the template's words, categories and tags;
            # never its title, and the template file is only read.
            shape = (store.read(store.template_path_for(folder, chosen)) if chosen
                     else store.Entry(slug="", title="", date=datetime.now(),
                                      categories=(), tags=(), body="", extra=()))
        except store.StoreError as exc:
            return _failed(face, notices, exc)
        slug = free_address(folder, address_for(title))
        store.write(folder, store.Entry(
            slug=slug, title=title.strip(), date=datetime.now().replace(microsecond=0),
            categories=shape.categories, tags=shape.tags, body=shape.body, extra=()),
            draft=True)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=_edit_address(slug))


def _edit(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str | Reply:
    """§ 4.7."""
    slug = request.query.get("slug", "")
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
            base = _digest(path)
        except (store.StoreError, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
            preview, preview_failure = _preview(face, folder, entry, draft=draft)
            missing = photographs.missing(folder, entry.body)
    if failure is not None:
        return render_notices(notices) + face.fail(failure, publishing=False)
    return render_notices(notices) + _page(folder, entry, draft, base, preview, preview_failure,
                                           missing)


def _page(folder: Path, entry: store.Entry, draft: bool, base: str,
          preview: str | None, failure: str | None, missing: list[str]) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    named = _replaced(folder, entry) if draft else None
    on_site = not draft or named is not None
    proof = named is not None
    published, waiting = (" hidden", "") if proof else ("", " hidden")
    # Both states on every page, because a save turns a published entry's page
    # into a working copy's editor, and a press turns a draft's or a proof's
    # into a published entry's, without reloading it; the script shows the one
    # that holds and names the copy (PRESS-0162, PRESS-0185).
    standing = (f'<div id="standing"{"" if on_site else " hidden"}>'
                f'<p data-when="0"{published}>This entry is on your site. Your changes stay on '
                "this computer until you publish it.</p>"
                f'<p data-when="1"{waiting}>These changes are not on your site yet.</p>'
                f'<form data-when="1"{waiting} method="post" action="/discard">'
                f'<input type="hidden" name="slug" value="{attr(entry.slug) if proof else ""}">'
                f'<input type="hidden" name="base" value="{attr(base)}">'
                "<button>Bin this proof</button></form></div>")
    if not on_site:
        standing = '<p id="draft-standing">A draft. It is not on your site.</p>' + standing
    # PRESS-0182: a published entry moves too; the script hides this once a
    # save makes a proof, whose address cannot change, and shows it again
    # once that proof is pressed (PRESS-0186).
    address = _address_field(named if proof else entry.slug, hidden=proof)
    stylesheets = "".join(f'<link rel="stylesheet" href="{attr(PREVIEW_ADDRESS + sheet)}">'
                          for sheet in builder.STYLESHEETS)
    return f"""{stylesheets}
<p><a href="/">Your writing</a> <span id="save-status"></span></p>
{standing}
<div id="notices"></div>
<form id="editor" data-slug="{attr(entry.slug)}" data-draft="{'1' if draft else '0'}"
 data-base="{attr(base)}" data-missing="{attr(json.dumps(missing))}"
 data-on-site="{'1' if on_site else '0'}" onsubmit="return false">
<label>Title <input name="title" value="{attr(entry.title)}"></label>
<label>Categories <input name="categories"
 value="{attr(store.LIST_SEPARATOR.join(entry.categories))}"></label>
<label>Tags <input name="tags" value="{attr(store.LIST_SEPARATOR.join(entry.tags))}"></label>
{address}
<p><button type="button" data-editor="publish">Press to site</button>
 <span id="publish-status"></span>
 <button type="button" data-undo>Undo the last press</button>
 <span id="undo-status"></span></p>
<p><button type="button" data-editor="photograph">Add a photograph</button>
 <input type="file" id="photograph-file" hidden
 accept="image/jpeg,image/png,image/webp,image/gif">
 <span id="photograph-status"></span></p>
<p id="photograph-missing" hidden></p>
<textarea name="body" class="{attr(builder.BODY_CLASS)}" rows="24">
{html.escape(entry.body)}</textarea>
<p><button type="button" data-editor="throw">Throw this {'entry' if on_site else 'draft'}
 away</button></p>
</form>
{cheatsheet.panel()}
<div id="failure">{failure or ""}</div>
<div id="undo-result"></div>
<div id="proof">{TRUE_COLOURS}
<iframe id="preview" title="Proof (preview)" sandbox="allow-same-origin"
 src="{attr(preview or 'about:blank')}"></iframe></div>
<script>{_EDITOR_SCRIPT}</script>
<script>{_UNDO_SCRIPT}</script>"""


def _address_field(slug: str, *, hidden: bool) -> str:
    value = html.escape(slug, quote=True)
    return (f'<span id="address"{" hidden" if hidden else ""}><label>Address '
            f'<input name="address" value="{value}">'
            '</label> <button type="button" data-editor="address">'
            'Change address</button> <span id="address-hint"></span></span>')


def save(folder: Path, form: dict[str, str]) -> tuple[store.Entry, str]:
    """PRESS-0012 § 4.8 steps 1 to 4: write the box to its draft, and return the
    entry written and its new digest. Takes no lock; the caller holds LOCK."""
    slug, draft, base = form.get("slug", ""), form.get("draft") == "1", form.get("base", "")
    path = store.path_for(folder, slug, draft=draft)
    entry = store.read(path)
    if _digest(path) != base:
        raise ChangedElsewhere(f"the entry {slug} changed since this window read it")
    extra = entry.extra
    written_slug = slug
    if not draft:
        if working_copy(folder, slug) is not None:
            raise ChangedElsewhere(f"the entry {slug} gained a working copy")
        written_slug = free_address(folder, slug + COPY_SUFFIX)
        extra = tuple(field for field in entry.extra
                      if field[0] != REPLACES) + ((REPLACES, slug),)
    body = form.get("body", "").replace("\r\n", "\n").replace("\r", "\n")
    written = store.Entry(
        slug=written_slug, title=form.get("title", "").strip(), date=entry.date,
        categories=_names_of(folder, form.get("categories", ""), "categories"),
        tags=_names_of(folder, form.get("tags", ""), "tags"), body=body, extra=extra)
    return written, _digest(store.write(folder, written, draft=True))


def _save(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.8."""
    form = _form(request)
    with lock, face.capture() as notices:
        try:
            written, new_base = save(folder, form)
        except (store.StoreError, ChangedElsewhere, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
            preview, preview_failure = _preview(face, folder, written, draft=True)
            missing = photographs.missing(folder, written.body)
    if failure is not None:
        return _failed(face, notices, failure)
    return _json({"slug": written.slug, "draft": True, "base": new_base, "preview": preview,
                  "failure": preview_failure, "notices": render_notices(notices),
                  "missing": missing})


def _photograph(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0016: keep the posted file as an original and name it. The body is
    the file itself, and its chosen name comes in the query."""
    with lock, face.capture() as notices:
        try:
            name = photographs.add(folder, request.query.get("name", ""), request.body)
        except (store.StoreError, photographs.NotAPhotograph, OSError) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    return _json({"name": name, "notices": render_notices(notices)})


def _address(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.9, and PRESS-0182 § 4.2 for a published entry: its old address
    forwards to the new one."""
    form = _form(request)
    slug, base, address = form.get("slug", ""), form.get("base", ""), form.get(
        "address", "").strip()
    draft = form.get("draft", "1") == "1"
    hint = None
    with lock, face.capture() as notices:
        try:
            entry = (store.read(store.path_for(folder, slug, draft=draft))
                     if slug in store.list_slugs(folder, draft=draft) else None)
            if entry is None:
                hint = "This entry is not there any more."
            elif draft and _replaced(folder, entry) is not None:
                hint = "A proof's address cannot be changed."
            elif not draft and working_copy(folder, slug) is not None:
                hint = ("Press your changes to your site, or bin this proof, "
                        "then change the address.")
            elif address != slug:
                try:
                    taken = store.exists(folder, address)
                except store.StoreError:
                    hint = "An address uses only the letters a to z, the digits 0 to 9 and -."
                else:
                    forwards = store.read_forwards(folder)
                    if taken:
                        hint = "Another entry already uses that address."
                    elif forwards.get(address, slug) != slug:
                        hint = "Another entry's old address forwards from there."
            if hint is None and entry is not None and address != slug:
                path = store.path_for(folder, slug, draft=draft)
                if _digest(path) != base:
                    raise ChangedElsewhere(f"the entry {slug} changed since this window read it")
                # The order leaves two copies, never none (§ 4.2).
                store.write(folder, dataclasses.replace(entry, slug=address), draft=draft)
                # Retarget every pair aimed here. A pair FROM the new address can
                # only be aimed here (the hint above refuses any other), so it
                # becomes a loop and the last line drops it: moving back.
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
                slug = address
                base = _digest(store.path_for(folder, slug, draft=draft))
        except (store.StoreError, ChangedElsewhere, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    return _json({"slug": slug, "draft": draft, "base": base, "preview": None,
                  "failure": None, "notices": render_notices(notices), "hint": hint})


def _discard(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.10."""
    form = _form(request)
    slug, base = form.get("slug", ""), form.get("base", "")
    with lock, face.capture() as notices:
        try:
            if slug not in store.list_slugs(folder, draft=True):
                raise ChangedElsewhere(f"the draft {slug} is not there")
            path = store.path_for(folder, slug, draft=True)
            named = _replaced(folder, store.read(path))
            if named is None or _digest(path) != base:
                raise ChangedElsewhere(f"the draft {slug} is not the working copy this "
                                       "window read")
            store.move_to_bin(folder, path)
        except (store.StoreError, ChangedElsewhere) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=_edit_address(named))


def _throw(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """PRESS-0128: bin the entry this window shows -- a draft, or a published
    entry and any working copy of it -- with its comments file. A published
    one leaves the site at the next press, and undoing that press brings it
    back. The entry goes first, so an interruption leaves at most a draft or a
    comments file behind, never an entry half thrown away."""
    form = _form(request)
    slug, draft, base = form.get("slug", ""), form.get("draft") == "1", form.get("base", "")
    with lock, face.capture() as notices:
        try:
            if slug not in store.list_slugs(folder, draft=draft):
                raise ChangedElsewhere(f"the entry {slug} is not there")
            path = store.path_for(folder, slug, draft=draft)
            if _digest(path) != base:
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
        except (store.StoreError, ChangedElsewhere, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    return _json({"thrown": True, "notices": render_notices(notices)})


# The page's script (§ 4.7). A change saves about a second after the last one,
# never two saves at once, and on leaving only where a change is unsaved.
# PRESS-0015 s 4.6. Both pages carry this. Neither reloads itself (s 4.2):
# the reply is the only place the summary and the gathered notices exist, and a
# reload throws both away before he has read them. So the box is replaced with
# what came back, and a link back to his list is offered instead.
_UNDO_SCRIPT = """
(() => {
  const button = document.querySelector("button[data-undo]");
  if (!button) return;
  const said = document.getElementById("undo-status");
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
    link.textContent = "Back to your writing";
    back.appendChild(link);
    result.appendChild(back);
    for (const box of [document.getElementById("editor"),
                       document.getElementById("listing")]) {
      if (box) box.hidden = true;
    }
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    said.textContent = "Putting your site back\u2026 this can take a few minutes. " +
      "Keep this page open.";
    try {
      const answer = await fetch("/undo", {method: "POST"});
      const text = await answer.text();
      said.textContent = "";
      if (answer.status !== 200) { show("", text); return; }
      const reply = JSON.parse(text);
      show((reply.notices || "") + (reply.undone ? "" : reply.failure || ""),
           reply.undone ? reply.summary : "");
    } catch (error) {
      said.textContent = "";
      show("", "Pressless could not reach itself. Your site was not changed.");
    } finally {
      button.disabled = false;
    }
  });
})();
"""


_EDITOR_SCRIPT = """
(() => {
  const form = document.getElementById("editor");
  const state = {slug: form.dataset.slug, draft: form.dataset.draft, base: form.dataset.base};
  const status = document.getElementById("save-status");
  let timer = null, inFlight = false, dirty = false, stopped = false;

  const fields = () => {
    const data = new URLSearchParams();
    data.set("slug", state.slug); data.set("draft", state.draft); data.set("base", state.base);
    for (const name of ["title", "categories", "tags", "body"]) {
      data.set(name, form.elements[name].value);
    }
    return data;
  };
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
    const addressField = document.getElementById("address");
    if (addressField && state.draft === "1" && form.dataset.draft === "0") {
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
        "Throw this entry away";
    }
  };
  const stop = (text) => {
    stopped = true;
    status.textContent = "Not saved";
    document.getElementById("failure").innerHTML = text;
  };

  // PRESS-0016: a photograph this entry names that Pressless does not have.
  // A press still stops on it; this says so while he writes.
  const missingLine = document.getElementById("photograph-missing");
  function showMissing(names) {
    missingLine.hidden = names.length === 0;
    missingLine.textContent = names.length === 0 ? "" :
      "Pressless does not have " + (names.length === 1 ? "this photograph: " :
      "these photographs: ") + names.join(", ") + ". Add " +
      (names.length === 1 ? "it" : "each") + " with Add a photograph, or correct " +
      "the name, before you press this entry to your site.";
  }
  showMissing(JSON.parse(form.dataset.missing));

  async function save() {
    if (stopped || inFlight || !dirty) return;
    inFlight = true; dirty = false; status.textContent = "Saving";
    try {
      const answer = await fetch("/save", {method: "POST", body: fields()});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      const reply = JSON.parse(text);
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      if (reply.preview) {
        document.getElementById("preview").src = reply.preview + "?n=" + Date.now();
      }
      status.textContent = "Saved";
    } catch (error) {
      stop("");
    } finally {
      inFlight = false;
      if (dirty && !stopped) schedule();
    }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(save, 1000); }

  form.addEventListener("input", (event) => {
    if (event.target.name === "address") return;
    dirty = true; schedule();
  });
  window.addEventListener("pagehide", () => {
    if (stopped || inFlight || !dirty) return;
    fetch("/save", {method: "POST", body: fields(), keepalive: true}).catch(() => {});
  });
  // A keepalive request carries at most 64 KiB, so a larger unsaved change
  // cannot be sent as the page goes; the browser asks before leaving instead
  // (PRESS-0135).
  window.addEventListener("beforeunload", (event) => {
    if (!stopped && dirty && new Blob([fields().toString()]).size > 60000) {
      event.preventDefault();
    }
  });

  const publish = document.querySelector("button[data-editor=publish]");
  publish.addEventListener("click", async () => {
    clearTimeout(timer);
    while (inFlight) await new Promise((resolve) => setTimeout(resolve, 100));
    // A save queued while this runs waits for it: it would post the address
    // and base the publish is about to move (PRESS-0135).
    inFlight = true;
    const said = document.getElementById("publish-status");
    publish.disabled = true;
    said.textContent = "Publishing\u2026 this can take a few minutes the first time. " +
      "Keep this page open.";
    try {
      const body = fields();
      dirty = false;
      const answer = await fetch("/publish", {method: "POST", body: body});
      const text = await answer.text();
      if (answer.status !== 200) { said.textContent = ""; stop(text); return; }
      const reply = JSON.parse(text);
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      said.textContent = reply.published
        ? "Published. Your site shows it within a few minutes." : "";
    } catch (error) {
      said.textContent = ""; stop("");
    } finally {
      publish.disabled = false;
      inFlight = false;
      if (dirty && !stopped) schedule();
    }
  });

  // PRESS-0016: the chosen file is kept as an original, and its picture mark
  // goes on a line of its own where he was typing.
  const box = form.elements["body"];
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
    photoSaid.textContent = "Adding the photograph\u2026";
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
      photoSaid.textContent = "Added " + reply.name + ".";
      dirty = true; schedule();
    } catch (error) {
      photoSaid.textContent = "";
      stop("");
    }
  });

  const button = document.querySelector("button[data-editor=address]");
  if (button) {
    button.addEventListener("click", async () => {
      // Settle first: the address change reads the base a save in flight is
      // about to replace (PRESS-0135).
      clearTimeout(timer);
      while (inFlight) await new Promise((resolve) => setTimeout(resolve, 100));
      if (dirty && !stopped) await save();
      if (stopped) return;
      // PRESS-0182: asked first, since links to it are out in the world.
      if (state.draft === "0" && !window.confirm(
          "Change this entry's address? It moves now in your Pressless-data folder, " +
          "and on your site the next time you press to site. Links to the old " +
          "address will still reach it.")) return;
      try {
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
      }
    });
  }

  // PRESS-0128: asked first, since a published entry leaves his site. Saves
  // settle before, and none follows: the file it would write is in the bin.
  const throwAway = document.querySelector("button[data-editor=throw]");
  throwAway.addEventListener("click", async () => {
    const question = form.dataset.onSite === "1"
      ? "Throw this entry away? It moves to the bin in your Pressless-data folder " +
        "now, and leaves your site the next time you press to site. Undo the last " +
        "press can bring it back after that."
      : "Throw this draft away? It moves to the bin in your Pressless-data folder.";
    if (!window.confirm(question)) return;
    clearTimeout(timer);
    while (inFlight) await new Promise((resolve) => setTimeout(resolve, 100));
    if (dirty && !stopped) await save();
    if (stopped) return;
    inFlight = true;
    try {
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
      inFlight = false;
    }
  });
})();
"""
