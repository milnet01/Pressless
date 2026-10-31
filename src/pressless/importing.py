"""The Import anyone runs, as a wizard (PRESS-0125).

The contract is docs/specs/PRESS-0125-wordpress-import.md. One of setup's
three starts, at /import, on a Store holding no site: the user hands over
WordPress's export, Pressless fetches every file it names from the old site,
takes a media download for any it could not, asks for a look, and brings the
whole site in at once, then shows what did not come across as written.

The second wizard, at /import/folder, takes a folder of web pages as a ZIP
instead (PRESS-0210 § 4.2).

The work is pressless_import's; this module is the order of things, which
only the Face knows (`docs/design.md` rule 1). Everything it keeps is in the
site's own import/ folder, which is never published and never saved in a
site file.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pressless_import
from pressless import face as face_module
from pressless import import_report, safe_write, setup, starter, store, wizard
from pressless.face import Face, Reply, Request, message_box
from pressless.import_report import counted as _counted
from pressless.import_report import shown as _shown
from pressless.words import say
from pressless_import import fetch

ADDRESS = setup.IMPORT
FOLDER_ADDRESS = setup.IMPORT_A_FOLDER

EXPORT_LARGEST = 256 * 1024 * 1024    # § 4.3: refused at upload
_EXPORT = "export.xml"
_UNFETCHED = "unfetched.json"         # what the fetch could not have, once it ended
_FOLDER_LEFT = "folder-left.json"     # PRESS-0210 § 4.2: what unpack_folder left out


def finish_moves(folder: Path) -> str | None:
    """§ 4.7: finish the moves a stop left part done; a sentence to print
    where they could not be finished."""
    return pressless_import.finish(folder)


@dataclass
class _Fetching:
    """One site's fetch, run beside the Face so a page can show its progress."""
    done: int = 0
    total: int = 0
    running: bool = False
    failed: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)


_FETCHING: dict[Path, _Fetching] = {}
_FETCHING_LOCK = threading.Lock()


def _fetching(folder: Path) -> _Fetching:
    with _FETCHING_LOCK:
        return _FETCHING.setdefault(folder, _Fetching())


def register(face: Face, folder: Path) -> None:
    """Add /import, its two file boxes, and the list page's offer."""
    folder = Path(folder)
    held = folder / pressless_import.IMPORT_FOLDER
    media = held / pressless_import.MEDIA_FOLDER

    def empty() -> bool:
        try:
            return not store.holds_a_site(folder)
        except store.StoreError:
            return False

    def room() -> int:
        return face_module._room(folder)

    def missing() -> dict[str, str]:
        try:
            read_in = json.loads((held / _UNFETCHED).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(place): str(why) for place, why in read_in.items()} if isinstance(
            read_in, dict) else {}

    def start_fetching() -> None:
        state = _fetching(folder)
        with state.lock:
            if state.running or (held / _UNFETCHED).exists():
                return
            state.running, state.failed, state.done = True, "", 0

        def progress(done: int, total: int) -> None:
            state.done, state.total = done, total

        def run() -> None:
            try:
                left = fetch.fetch_all(pressless_import.read(held / _EXPORT), media,
                                       room, progress=progress)
                safe_write.write_whole(held / _UNFETCHED, json.dumps(left, indent=1) + "\n",
                                       prefix=".unfetched-")
            except Exception as exc:
                # Anything at all: a thread that dies unrecorded leaves the
                # Media step waiting, and reloading, for good.
                state.failed = face.fail(exc, publishing=False)
            finally:
                state.running = False

        threading.Thread(target=run, name="pressless-import-fetch", daemon=True).start()

    def check_export(answers: wizard.Answers):
        try:
            read_in = pressless_import.read(held / _EXPORT)
        except pressless_import.ImportStopped:
            return wizard.Hint("", say("import.export.none"))
        counts = {"posts": 0, "pages": 0, "files": 0}
        for item in read_in.channel.findall("item"):
            kind = item.findtext("wp:post_type", "", read_in.ns).strip()
            name = {"post": "posts", "page": "pages", "attachment": "files"}.get(kind)
            if name:
                counts[name] += 1
        return {**answers, **{name: str(count) for name, count in counts.items()}}

    def show_media(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
        start_fetching()
        state = _fetching(folder)
        total = answers.get("files", "0")
        counts = say(
            "import.media.counts",
            posts=_counted(answers.get("posts", "0"),
                           "import.count.posts.one", "import.count.posts.many"),
            pages=_counted(answers.get("pages", "0"),
                           "import.count.pages.one", "import.count.pages.many"),
            files=_counted(total, "import.count.held.one", "import.count.held.many"))
        counts = f"<p>{counts}</p>"
        if state.failed:
            return counts + state.failed
        if state.running or not (held / _UNFETCHED).exists():
            fetching = say("import.media.fetching", done=str(state.done), total=total)
            return counts + f"<p>{fetching}</p><script>{_RELOAD}</script>"
        left = len(missing())
        return counts + (f"<p>{say('import.media.missing', count=str(left))}</p>" if left
                         else f"<p>{say('import.media.done')}</p>")

    def check_media(answers: wizard.Answers):
        if not (held / _UNFETCHED).exists():
            return wizard.Hint("", say("import.media.wait"))
        return answers

    def show_gaps(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
        left = missing()
        if not left:
            return f"<p>{say('import.gaps.none')}</p>"
        rows = "".join(f"<li>{_shown(place)}: {_shown(why)}</li>"
                       for place, why in sorted(left.items()))
        return (f"<p>{say('import.gaps.list', count=str(len(left)))}</p><ul>{rows}</ul>"
                f"<p>{say('import.gaps.how')}</p>"
                + face_module.file_box("import-media", ".zip", f"{ADDRESS}/media",
                                         say("import.gaps.choose")))

    def show_look(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
        return (f"<p>{say('import.look')}</p>"
                f'<fieldset class="looks"><legend>{say("setup.starter.look")}</legend>'
                + setup.look_choices("look", answers.get("look", "")) + "</fieldset>")

    def check_look(answers: wizard.Answers):
        if answers.get("look") not in starter.LOOKS:
            return wizard.Hint("", say("import.look.choose"))
        return answers

    def check_bring(answers: wizard.Answers):
        try:
            report = pressless_import.bring_in(held / _EXPORT, media, folder,
                                               answers.get("look", ""), unfetched=missing())
        except pressless_import.ImportStopped as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        return wizard.Done(_reported(face, held, report))

    steps = (
        wizard.Step("export", "import.step.export", (), lambda answers, hint: _show_export(
            held), check_export),
        wizard.Step("media", "import.step.media", (), show_media, check_media),
        wizard.Step("gaps", "import.step.gaps", (), show_gaps),
        wizard.Step("look", "import.step.look", ("look",), show_look, check_look),
        wizard.Step("bring", "import.step.bring", (),
                    lambda answers, hint: f"<p>{say('import.bring')}</p>", check_bring),
    )
    flow = wizard.Wizard("import", steps, folder, ADDRESS)

    def to_the_list() -> Reply:
        return Reply(b"", "text/plain; charset=utf-8", status=303, location="/")

    def page(request: Request) -> str | Reply:
        if not empty():
            return to_the_list()
        return flow.page(face, request)

    def shown_again(said: str) -> str:
        return said + flow.page(face, Request("GET", ADDRESS, {}, b""))

    def export_file(taken: Path) -> str | Reply:
        if not empty():
            return to_the_list()
        if taken.stat().st_size > EXPORT_LARGEST:
            return shown_again(message_box("import-hint", say("import.export.too_large")))
        try:
            pressless_import.read(taken)
        except pressless_import.ImportStopped:
            return shown_again(message_box("import-hint", say("import.export.refused")))
        held.mkdir(exist_ok=True)
        os.replace(taken, held / _EXPORT)
        # A new export is fetched afresh; files already held stay, by place.
        (held / _UNFETCHED).unlink(missing_ok=True)
        return shown_again(f"<p>{say('import.export.held')}</p>")

    def media_file(taken: Path) -> str | Reply:
        if not empty():
            return to_the_list()
        left = missing()
        try:
            filled = pressless_import.unpack_media(taken, media, tuple(left), room)
        except pressless_import.ImportStopped:
            return shown_again(message_box("import-hint", say("import.gaps.refused")))
        for place in filled:
            left.pop(place, None)
        safe_write.write_whole(held / _UNFETCHED, json.dumps(left, indent=1) + "\n",
                               prefix=".unfetched-")
        return shown_again(f"<p>{say('import.gaps.filled', count=str(len(filled)))}</p>")

    def offer() -> str:
        return setup.import_offer() if empty() else ""

    face.add_page("GET", ADDRESS, page)
    face.add_page("POST", ADDRESS, page)
    face.add_upload(f"{ADDRESS}/export", export_file, folder)
    face.add_upload(f"{ADDRESS}/media", media_file, folder)
    face.add_to_list(offer, above=True)
    _register_folder(face, folder, empty, room, to_the_list)


def _reported(face: Face, held: Path, report: pressless_import.Report) -> str:
    """The Report's page, its words kept beside the import's other files."""
    said = import_report.lines(report)
    try:
        import_report.keep(held, said)
    except OSError as exc:
        face.fail(exc, publishing=False)    # logged; the page still shows it
    return import_report.page(said)


def _register_folder(face: Face, folder: Path, empty, room, to_the_list) -> None:
    """PRESS-0210 § 4.2: /import/folder, and its file box."""
    held = folder / pressless_import.IMPORT_FOLDER
    unpacked = held / pressless_import.FOLDER

    def left_out() -> tuple[tuple[str, str], ...]:
        try:
            read_in = json.loads((held / _FOLDER_LEFT).read_text(encoding="utf-8"))
            return tuple((str(path), str(why)) for path, why in read_in)
        except (OSError, ValueError, TypeError):
            return ()

    def check_folder(answers: wizard.Answers):
        found = pressless_import.read_folder(unpacked) if unpacked.is_dir() else None
        if found is None or not found.pages:
            return wizard.Hint("", say("import.folder.none"))
        if found.built_by_a_tool:
            return wizard.Hint("", say("import.folder.built"))
        return answers

    def show_found(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
        found = pressless_import.read_folder(unpacked)
        return _show_found(found, left_out())

    def check_bring(answers: wizard.Answers):
        try:
            brought = pressless_import.bring_in_folder(unpacked, folder, left=left_out())
        except pressless_import.ImportStopped as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        return wizard.Done(_reported(face, held, brought.report))

    steps = (
        wizard.Step("folder", "import.step.folder", (),
                    lambda answers, hint: _show_folder(unpacked), check_folder),
        wizard.Step("found", "import.step.found", (), show_found),
        wizard.Step("bring", "import.step.bring", (),
                    lambda answers, hint: f"<p>{say('import.bring')}</p>", check_bring),
    )
    flow = wizard.Wizard("import-folder", steps, folder, FOLDER_ADDRESS)

    def page(request: Request) -> str | Reply:
        if not empty():
            return to_the_list()
        return flow.page(face, request)

    def shown_again(said: str) -> str:
        return said + flow.page(face, Request("GET", FOLDER_ADDRESS, {}, b""))

    def zip_file(taken: Path) -> str | Reply:
        if not empty():
            return to_the_list()
        try:
            left = pressless_import.unpack_folder(taken, unpacked, room)
        except pressless_import.ImportStopped:
            return shown_again(message_box("import-hint", say("import.folder.refused")))
        (held / "folder.json").unlink(missing_ok=True)
        if not pressless_import.read_folder(unpacked).pages:
            shutil.rmtree(unpacked, ignore_errors=True)
            return shown_again(message_box("import-hint", say("import.folder.no_page")))
        safe_write.write_whole(held / _FOLDER_LEFT, json.dumps(left, indent=1) + "\n",
                               prefix=".folder-left-")
        return shown_again(f"<p>{say('import.folder.held')}</p>")

    face.add_page("GET", FOLDER_ADDRESS, page)
    face.add_page("POST", FOLDER_ADDRESS, page)
    face.add_upload(f"{FOLDER_ADDRESS}/zip", zip_file, folder)


def _show_folder(unpacked: Path) -> str:
    steps = "".join(f"<li>{say(key)}</li>" for key in (
        "import.folder.windows", "import.folder.linux"))
    kept = f"<p>{say('import.folder.held')}</p>" if unpacked.is_dir() else ""
    return (f"<p>{say('import.folder.how')}</p><ul>{steps}</ul>" + kept
            + face_module.file_box("import-folder", ".zip", f"{FOLDER_ADDRESS}/zip",
                                   say("import.folder.choose")))


def _show_found(found: pressless_import.Found, left: tuple[tuple[str, str], ...]) -> str:
    """§ 4.3's counts, every path that will not come across, and the look."""
    counts = say("import.folder.counts",
                 pages=_counted(len(found.pages), "import.count.pages.one",
                                "import.count.pages.many"),
                 photographs=_counted(len(found.photographs), "import.count.photographs.one",
                                      "import.count.photographs.many"),
                 files=_counted(len(found.files), "import.count.files.one",
                                "import.count.files.many"))
    rows = "".join(f"<li>{_shown(path)}: {_shown(why)}</li>" for path, why in (*left, *found.left))
    listed = f"<p>{say('import.folder.left')}</p><ul>{rows}</ul>" if rows else ""
    return f"<p>{counts}</p>{listed}<p>{say('import.folder.look')}</p>"


def _show_export(held: Path) -> str:
    steps = "".join(f"<li>{say(key)}</li>" for key in (
        "import.export.1", "import.export.2", "import.export.3"))
    kept = (f"<p>{say('import.export.held')}</p>" if (held / _EXPORT).is_file() else "")
    return (f"<p>{say('import.export.how')}</p><ol>{steps}</ol>" + kept
            + face_module.file_box("import-export", ".xml", f"{ADDRESS}/export",
                                 say("import.export.choose")))


# The step is shown again after each check, so it reloads itself until the
# fetch has ended; a GET, never the POST that showed it.
_RELOAD = f"setTimeout(() => location.replace({json.dumps(ADDRESS)}), 2000);"
