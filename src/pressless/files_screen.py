"""The Files screen: every kept file, the pages naming it, and its removal
(PRESS-0197 § 4.4, docs/specs/PRESS-0197-upload-any-file.md).

It also takes an upload, and serves the kept files to the preview at the
address a page names them by. A file a page names, published or waiting, is
not removed, since the Builder would skip the address in silence (§ 3
decision 7).
"""
from __future__ import annotations

import html
import threading
from pathlib import Path

from pressless import builder, editor, files, store
from pressless.face import SENTENCES, Face, Reply, Request, Sentence, Site, render_notices
from pressless.words import say

ADDRESS = "/files"
REMOVED = "removed"   # the query a removal sends the screen back with


class FileInUse(Exception):
    """A page names the file, so it is not removed (§ 3 decision 7)."""

    def __init__(self, message: str, pages: str) -> None:
        super().__init__(message)
        self.slots = {"pages": pages}


SENTENCES[FileInUse] = Sentence(
    "failure.files_screen.FileInUse.what",
    Site.UNCHANGED,
    "failure.files_screen.FileInUse.next",
)

# The furniture a file may be named by, in words; any other name is a page's.
_FURNITURE_WORDS = {"header": "files_screen.header", "footer": "files_screen.footer"}


def register(face: Face, folder: Path) -> None:
    """Add the Files screen, the upload and the preview's kept files to `face`."""
    folder = Path(folder)

    def route(handler):
        return lambda request: handler(face, folder, editor.LOCK, request)

    face.add_page("GET", ADDRESS, route(_open))
    face.add_page("POST", "/file", route(_upload))
    face.add_page("POST", ADDRESS + "/remove", route(_remove))
    face.add_files(editor.PREVIEW_ADDRESS + store.FILES_FOLDER + "/",
                   lambda name: store.file_path_for(folder, name))


def _pages(names: tuple[str, ...]) -> str:
    return ", ".join(say(_FURNITURE_WORDS[name]) if name in _FURNITURE_WORDS else name
                     for name in names)


def _size(size: int) -> str:
    if size < 1000:
        return say("files_screen.bytes", n=str(size))
    if size < 1000 * 1000:
        return say("files_screen.kb", n=f"{size / 1000:.0f}")
    return say("files_screen.mb", n=f"{size / 1000 / 1000:.1f}")


def _open(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str:
    with lock, face.capture() as notices:
        try:
            kept = store.list_files(folder)
            named = builder.files_named(folder)
            sizes = {name: store.file_path_for(folder, name).stat().st_size for name in kept}
        except (store.StoreError, OSError) as exc:
            return render_notices(notices) + face.fail(exc, publishing=False)
    said = f"<p>{say('files_screen.removed')}</p>" if request.query.get(REMOVED) else ""
    return render_notices(notices) + _page(kept, named, sizes, said)


def _page(kept: tuple[str, ...], named: dict[str, tuple[str, ...]],
          sizes: dict[str, int], said: str) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(name)}</td><td>{e(_size(sizes[name]))}</td>"
        f"<td>{e(_pages(named[name])) if name in named else say('files_screen.unused')}</td>"
        f'<td><form method="post" action="{ADDRESS}/remove">'
        f'<input type="hidden" name="name" value="{e(name, quote=True)}">'
        f'<button type="submit">{say("files_screen.remove")}</button></form></td></tr>'
        for name in kept)
    listing = (f'<table class="kept-files"><thead><tr><th scope="col">'
               f'{say("files_screen.name")}</th><th scope="col">{say("files_screen.size")}</th>'
               f'<th scope="col">{say("files_screen.used_by")}</th><td></td></tr></thead>'
               f"<tbody>{rows}</tbody></table>" if kept
               else f"<p>{say('files_screen.none')}</p>")
    return (f'<p><a href="/">{say("face.your_writing")}</a></p>'
            f'<h1>{say("files_screen.title")}</h1><p>{say("files_screen.about")}</p>'
            f'<div role="status">{said}</div>{listing}')


def _upload(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.4: the body is the file, its chosen name in the query, answered as
    editor._photograph answers."""
    with lock, face.capture() as notices:
        try:
            name = files.add(folder, request.query.get("name", ""), request.body)
        except (store.StoreError, files.NotAllowed, files.TooLarge, OSError) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return editor._failed(face, notices, failure)
    return editor._json({"name": name, "notices": render_notices(notices)})


def _remove(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.4: refused while any page, published or waiting, names the file;
    else the file goes to the bin."""
    name = editor._form(request).get("name", "")
    with lock, face.capture() as notices:
        try:
            path = store.file_path_for(folder, name)
            pages = builder.files_named(folder).get(name)
            if pages:
                raise FileInUse(f"pages name {name}", _pages(pages))
            store.move_to_bin(folder, path)
        except (store.StoreError, FileInUse) as exc:
            return editor._failed(face, notices, exc)
    return Reply(b"", "text/plain; charset=utf-8", status=303,
                 location=f"{ADDRESS}?{REMOVED}=1")
