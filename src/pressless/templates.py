"""Templates: pick a shape when starting something new (PRESS-0017).

A template is an entry file in the Store's templates folder that never becomes
a page (docs/design.md; PRESS-0006 § 3 decision 3). This module writes the four
starters once, shows each template in a page of its own, and adds and bins
them. Picking one is the editor's New form, which reads the Store alone, so the
editor does not import this module (docs/specs/PRESS-0017-templates.md § 4).
"""
from __future__ import annotations

import html
import urllib.parse
from datetime import datetime
from pathlib import Path

from pressless import builder, cheatsheet, editor, store
from pressless.face import Face, Reply, Request, render_notices
from pressless.words import say

_STARTED = datetime(2026, 9, 27)


def _starter(name: str, title: str, body: str) -> store.Entry:
    return store.Entry(slug=name, title=title, date=_STARTED, categories=(), tags=(),
                       body=body, extra=())


def starters() -> tuple[store.Entry, ...]:
    """The four starters, in the words in use when they are written. Shipped
    to every install, so they name nobody and assume nothing about the
    writer's life (§ 3 decision 6). The names are file names and stay."""
    return (
        _starter("poem", say("templates.poem"), say("templates.poem.body")),
        _starter("lyric", say("templates.lyric"), say("templates.lyric.body")),
        _starter("photograph", say("templates.photograph"),
                 say("templates.photograph.body")),
        _starter("journal", say("templates.journal"), say("templates.journal.body")),
    )


def seed(folder: Path) -> bool:
    """Write the starters where the templates folder does not exist (§ 4.2).

    False where it existed, empty or not: it is his. A StoreError propagates,
    and the folder the first write made stays, so a failure is final.
    """
    if (Path(folder) / store.TEMPLATES_FOLDER).exists():
        return False
    for starter in starters():
        store.write_template(folder, starter)
    return True


def register(face: Face, folder: Path) -> None:
    """Write the starters if they are owed, and add the template routes."""
    folder = Path(folder)
    try:
        seed(folder)
    except store.StoreError:
        face.note("templates: starters not written")

    def route(handler):
        return lambda request: handler(face, folder, request)

    face.add_page("GET", "/template", route(_open))
    face.add_page("POST", "/template/save", route(_save))
    face.add_page("POST", "/template/new", route(_new))
    face.add_page("POST", "/template/bin", route(_bin))
    face.add_to_list(lambda: _listed(folder), above=False)


def _address(name: str) -> str:
    return "/template?" + urllib.parse.urlencode({"name": name})


def _listed(folder: Path) -> str:
    """§ 4.5: his templates, each opening its page, and the New template form."""
    try:
        names = store.list_templates(folder)
    except store.StoreError:
        items = f'<p>{say("templates.unreadable")}</p>'
    else:
        items = "<ul>" + "".join(
            f'<li><a href="{html.escape(_address(name), quote=True)}">'
            f"{html.escape(name)}</a></li>" for name in names) + "</ul>"
    return (f'<section class="card"><h2>{say("templates.yours")}</h2>' + items +
            f'<form method="post" action="/template/new"><label>{say("templates.name")} '
            '<input name="name" autocomplete="off"></label> '
            f'<button>{say("templates.new")}</button></form></section>')


def _open(face: Face, folder: Path, request: Request) -> str:
    """§ 4.4."""
    name = request.query.get("name", "")
    with editor.LOCK, face.capture() as notices:
        try:
            path = store.template_path_for(folder, name)
            template = store.read(path)
            base = editor._digest(path)
        except store.StoreError as exc:
            return render_notices(notices) + face.fail(exc, publishing=False)
    return render_notices(notices) + _page(template, base)


def _page(template: store.Entry, base: str) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    tags = say("editor.tags")
    return f"""<p><a href="/">{say('face.your_writing')}</a></p>
<p>{say('templates.about', name=html.escape(template.slug))}</p>
<form method="post" action="/template/save">
<input type="hidden" name="name" value="{attr(template.slug)}">
<input type="hidden" name="base" value="{attr(base)}">
<label>{say('editor.title')} <input name="title" value="{attr(template.title)}"></label>
<label>{say('editor.categories')} <input name="categories"
 value="{attr(store.LIST_SEPARATOR.join(template.categories))}"></label>
<label>{tags} <input name="tags" value="{attr(store.LIST_SEPARATOR.join(template.tags))}"></label>
<textarea name="body" class="{attr(builder.BODY_CLASS)}" rows="24">
{html.escape(template.body)}</textarea>
<p><button>{say('templates.save')}</button></p>
</form>
<form method="post" action="/template/bin">
<input type="hidden" name="name" value="{attr(template.slug)}">
<input type="hidden" name="base" value="{attr(base)}">
<button>{say('templates.bin')}</button></form>
{cheatsheet.panel()}"""


def _checked(folder: Path, name: str, base: str) -> tuple[Path, store.Entry]:
    """The template as this window last saw it, or ChangedElsewhere."""
    path = store.template_path_for(folder, name)
    template = store.read(path)
    if editor._digest(path) != base:
        raise editor.ChangedElsewhere(f"the template {name} changed since this window read it")
    return path, template


def _save(face: Face, folder: Path, request: Request) -> str | Reply:
    """§ 4.4."""
    form = editor._form(request)
    name = form.get("name", "")
    with editor.LOCK, face.capture() as notices:
        try:
            path, template = _checked(folder, name, form.get("base", ""))
            body = form.get("body", "").replace("\r\n", "\n").replace("\r", "\n")
            written = store.Entry(
                slug=name, title=form.get("title", "").strip(), date=template.date,
                categories=editor._names_of(folder, form.get("categories", ""), "categories"),
                tags=editor._names_of(folder, form.get("tags", ""), "tags"),
                body=body, extra=template.extra)
            store.write_template(folder, written)
            base = editor._digest(path)
        except (store.StoreError, editor.ChangedElsewhere) as exc:
            return editor._failed(face, notices, exc)
    return render_notices(notices) + _page(written, base)


def _new(face: Face, folder: Path, request: Request) -> Reply:
    """§ 4.5: a free name is one no file sits at, so on Windows a hand-named
    Poem.txt answers for poem and is not overwritten."""
    typed = editor._form(request).get("name", "")
    wanted = editor.address_for(typed)
    with editor.LOCK, face.capture() as notices:
        try:
            number = 1
            while True:
                name = wanted if number == 1 else f"{wanted}-{number}"
                if not store.template_path_for(folder, name).is_file():
                    break
                number += 1
            store.write_template(folder, store.Entry(
                slug=name, title=typed.strip(), date=datetime.now().replace(microsecond=0),
                categories=(), tags=(), body="", extra=()))
        except store.StoreError as exc:
            return editor._failed(face, notices, exc)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=_address(name))


def _bin(face: Face, folder: Path, request: Request) -> Reply:
    """§ 4.5."""
    form = editor._form(request)
    with editor.LOCK, face.capture() as notices:
        try:
            path, _ = _checked(folder, form.get("name", ""), form.get("base", ""))
            store.move_to_bin(folder, path)
        except (store.StoreError, editor.ChangedElsewhere) as exc:
            return editor._failed(face, notices, exc)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location="/")
