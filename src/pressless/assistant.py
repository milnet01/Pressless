"""The AI helper's door, inside the Face (PRESS-0337,
docs/specs/PRESS-0337-ai-assistant.md).

An AI app on this computer starts `pressless --assistant`, the bridge, which
posts each tool call here. The door does the work with the same plain
functions the screens call, under the same locks, so the design's rules 1 and
10 hold: only the Face orders a write, a build and a publish, and only the
Face reaches Credentials. Nothing the door answers holds a key.

A call that would publish, undo a publish or bin something is not run: it
becomes the one waiting request, which every Face page shows in a box until
the writer answers yes or not yet (§ 4.6).

Off until the writer switches it on in /assistant/setup (§ 4.2). While it is
on and this Face serves, the door file in Pressless's own folder tells the
bridge the port and the token.
"""
from __future__ import annotations

import base64
import binascii
import contextlib
import dataclasses
import html
import json
import os
import secrets
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from pressless import (
    __version__,
    assistant_tools,
    blocks,
    builder,
    dashboard,
    editor,
    files,
    files_screen,
    look,
    look_screen,
    marks,
    menu,
    page_editor,
    paths,
    photographs,
    pressing,
    publisher,
    publishing,
    safe_write,
    settings,
    store,
    undo,
)
from pressless.face import (
    SENTENCES,
    Face,
    Reply,
    Request,
    Sentence,
    Site,
    _is_secret,
    sentence_for,
)
from pressless.words import say

SWITCH_NAME = "assistant.json"        # {"on": true|false}; absent means off
DOOR_NAME = "assistant-door.json"     # the port, the token and the version
ADDRESS = "/assistant"
SETUP = "/assistant/setup"
WAITING = "/assistant/waiting"
ANSWER = "/assistant/answer"
CONNECT = "/assistant/connect"
EXPIRES_SECONDS = 30 * 60

# A request's states (§ 4.5's request_status).
WAITING_STATE, REFUSED, EXPIRED, RUNNING, DONE, FAILED, UNKNOWN = (
    "waiting", "refused", "expired", "running", "done", "failed", "unknown")

# One call at a time, for the whole call (§ 4.3). Module-wide: one Face serves
# at a time.
LOCK = threading.Lock()

_STATUS_WORDS = {
    WAITING_STATE: "assistant.status.waiting", REFUSED: "assistant.status.refused",
    EXPIRED: "assistant.status.expired", RUNNING: "assistant.status.running",
    DONE: "assistant.status.done", FAILED: "assistant.status.failed",
    UNKNOWN: "assistant.status.unknown"}
_JSON = "application/json"
_KEEP_FINISHED = 50                   # finished requests kept for request_status
_PUBLISHING_KEY = "failure.secret.publishing_key"
_PRESSES = {"publish": pressing.PUBLISH, "undo_last_publish": pressing.UNDO,
            "remove_page": pressing.PUBLISH, "rename_page": pressing.PUBLISH}


class Refused(Exception):
    """The door turns a call down before it changes anything; `key` names the
    words saying why."""

    def __init__(self, key: str, **slots: str) -> None:
        super().__init__(key)
        self.key = key
        self.slots = {"said": say(key, **slots)}


SENTENCES[Refused] = Sentence(
    "failure.assistant.Refused.what",
    Site.UNCHANGED,
    "failure.assistant.Refused.next",
)


# ------------------------------------------------------------ the switch ---


def is_on(own: Path) -> bool:
    """Whether the writer switched the helper on. Absent or unreadable is off
    (§ 4.2, INV-9)."""
    try:
        value = json.loads((Path(own) / SWITCH_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(value, dict) and value.get("on") is True


def switch(own: Path, on: bool) -> None:
    safe_write.write_whole(Path(own) / SWITCH_NAME, json.dumps({"on": on}),
                           prefix=".assistant-")


def door_path(own: Path) -> Path:
    return Path(own) / DOOR_NAME


# ----------------------------------------------------------- the requests ---


@dataclasses.dataclass
class _Request:
    """One ask (§ 4.6): what it asks, the plan the box lists, and the Store's
    mark when that plan was made."""
    id: str
    tool: str
    arguments: dict
    made: float
    plan: dict
    mark: str
    status: str = WAITING_STATE
    said: str = ""


def _said(failure: BaseException, *, secret: str | None = None) -> str:
    """A failure as plain text: its sentence's three parts (§ 4.3)."""
    if isinstance(failure, Refused):
        return failure.slots["said"]
    told = sentence_for(failure, publishing=False, secret=secret)
    # A screen's next step may point "below" at a link; a chat has none.
    following = say(_CHAT_NEXT[type(failure)]) if type(failure) in _CHAT_NEXT else told.next
    return " ".join(part for part in (told.what, told.site.words, following) if part)


_CHAT_NEXT = {publishing.WouldReplaceASite: "assistant.next.would_replace"}


class _Door:
    def __init__(self, face: Face, folder: Path, own: Path,
                 transport: publisher.Transport | None) -> None:
        self.face, self.folder, self.own, self.transport = face, folder, own, transport
        self.token = secrets.token_urlsafe(32)
        self.requests: dict[str, _Request] = {}
        self.waiting: _Request | None = None
        self.state = threading.Lock()     # guards `requests` and `waiting`, briefly

    # -------------------------------------------------------- the door file ---

    def open(self) -> None:
        """Write the door file with a new token (§ 4.2)."""
        self.token = secrets.token_urlsafe(32)
        safe_write.write_whole(door_path(self.own), json.dumps(
            {"port": self.face.port, "token": self.token, "version": __version__}),
            prefix=".assistant-door-")

    def shut(self) -> None:
        door_path(self.own).unlink(missing_ok=True)

    def admits(self, authorization: str) -> bool:
        """§ 4.3: the switch is on and the header carries this door's token."""
        scheme, _, offered = authorization.partition(" ")
        return (scheme == "Bearer" and is_on(self.own)
                and _is_secret(offered.strip(), self.token))

    # ------------------------------------------------------------- a call ---

    def call(self, request: Request) -> Reply:
        try:
            sent = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            sent = None
        if not isinstance(sent, dict):
            self.face.note("assistant: a call refused, bad_call")
            return _answer({"ok": False, "said": say("assistant.not_json")})
        if sent.get("version") != __version__:
            self.face.note("assistant: a call refused, restart_app")
            return _answer({"ok": False, "said": say("assistant.restart_app")})
        tool, arguments = sent.get("tool"), sent.get("arguments", {})
        why = assistant_tools.problem(tool if isinstance(tool, str) else "", arguments)
        if why is not None:
            self.face.note("assistant: a call refused, bad_call")
            return _answer({"ok": False, "said": say("assistant.bad_call", why=why)})
        with LOCK:
            try:
                result = self.run(tool, arguments)
            except Exception as exc:  # noqa: BLE001 -- every failure is said, none raised
                self.face.note(f"assistant: {tool} refused {type(exc).__name__}")
                self.face.fail(exc, publishing=False)     # its details, in the log
                secret = (say("failure.secret.google_sign_in") if tool == "read_insights"
                          else say(_PUBLISHING_KEY))
                return _answer({"ok": False, "said": _said(exc, secret=secret)})
        self.face.note(f"assistant: {tool} ok")
        return _answer({"ok": True, "result": result})

    def run(self, tool: str, arguments: dict) -> dict:
        if tool == "request_status":
            return self.status(arguments["request"])
        handler = getattr(self, "_" + tool)
        if assistant_tools.BY_NAME[tool].kind == assistant_tools.ASK:
            # An ask's plan may build and ask GitHub, so it holds no capture:
            # a capture's lock is the whole process's (face.capture).
            with editor.LOCK:
                return handler(**arguments)
        with editor.LOCK, self.face.capture() as notices:
            result = handler(**arguments)
        if notices:
            result["notices"] = notices
        return result

    # -------------------------------------------------------------- reads ---

    def _site_overview(self) -> dict:
        folder = self.folder
        identity = store.read_identity(folder)
        pages = (set(store.list_html(folder, store.PAGES_FOLDER))
                 | set(store.list_html(folder, store.PAGES_FOLDER, waiting=True)))
        with self.state:
            waiting = self._still_waiting()
        return {"name": identity.name if identity is not None else "",
                "address": self.face.live_address(), "journal": store.journal_on(folder),
                "entries": len(self._entries()), "pages": len(pages),
                "publishing": pressing.state()["running"],
                "waiting": ({"request": waiting.id, "tool": waiting.tool}
                            if waiting is not None else None)}

    def _writing_guide(self) -> dict:
        return {"marks": [{"you_type": say("mark." + row.name + ".example"),
                           "does": say("mark." + row.name)} for row in marks.MARKS]}

    def _entries(self) -> list[dict]:
        folder = self.folder
        published = store.list_slugs(folder, draft=False)
        copies: set[str] = set()
        listed = []
        for slug in store.list_slugs(folder, draft=True):
            entry = store.read(store.path_for(folder, slug, draft=True))
            named = editor.replaces_field(entry)
            if named in published:
                copies.add(named)
                continue
            listed.append({"address": slug, "title": entry.title,
                           "date": entry.date.isoformat(sep=" "), "draft": True,
                           "has_changes": False})
        for slug in published:
            entry = store.read(store.path_for(folder, slug, draft=False))
            listed.append({"address": slug, "title": entry.title,
                           "date": entry.date.isoformat(sep=" "), "draft": False,
                           "has_changes": slug in copies})
        return listed

    def _list_entries(self) -> dict:
        return {"entries": self._entries()}

    def _read_entry(self, address: str) -> dict:
        slug, draft = _entry_file(self.folder, address)
        path = store.path_for(self.folder, slug, draft=draft)
        entry = store.read(path)
        return {"address": address, "title": entry.title,
                "date": entry.date.isoformat(sep=" "), "categories": list(entry.categories),
                "tags": list(entry.tags), "body": entry.body,
                "draft": draft and editor.replaces_field(entry) is None,
                "version": editor.digest(path)}

    def _list_pages(self) -> dict:
        folder = self.folder
        live = store.list_html(folder, store.PAGES_FOLDER)
        waiting = store.list_html(folder, store.PAGES_FOLDER, waiting=True)
        pages = [{"name": name, "changed": name in waiting, "live": name in live}
                 for name in sorted(set(live) | set(waiting))]
        parts = [{"name": name, "changed": store.html_path_for(
                      folder, store.FURNITURE_FOLDER, name, waiting=True).is_file()}
                 for name in store.FURNITURE_NAMES
                 if store.html_path_for(folder, store.FURNITURE_FOLDER, name).is_file()]
        return {"pages": pages, "parts": parts}

    def _read_page(self, name: str) -> dict:
        kind = _kind(name)
        path, _ = page_editor._read(self.folder, kind, name)
        text = store.read_html(path)
        version = editor.digest(path)
        if page_editor._is_menu(kind, name):
            return {"name": name, "version": version,
                    "links": [{"at": at, "words": words, "href": href}
                              for at, (words, href) in enumerate(menu.links(text))]}
        page = _sections_of(kind, name, text)
        return {"name": name, "version": version,
                "sections": [_shown(at, section) for at, section in
                             page_editor._paths(page).items()]}

    def _list_files(self) -> dict:
        folder = self.folder
        named = builder.files_named(folder)
        return {"photographs": [{"name": name, "address": builder.web_photograph(name)}
                                for name in store.list_photographs(folder)],
                "files": [{"name": name, "used_by": list(named.get(name, ()))}
                          for name in store.list_files(folder)]}

    def _read_look(self) -> dict:
        chosen = look.read(self.folder)
        return {"choices": dataclasses.asdict(chosen) if chosen is not None else None,
                "version": look.digest(self.folder)}

    def _read_insights(self, days: int = dashboard.DEFAULT_DAYS) -> dict:
        return dataclasses.asdict(dashboard.figures(self.folder, days))

    # ------------------------------------------------------------- writes ---

    def _new_entry(self, title: str, template: str = "") -> dict:
        entry = editor.new_draft(self.folder, title, template)
        path = store.path_for(self.folder, entry.slug, draft=True)
        return {"address": entry.slug, "version": editor.digest(path)}

    def _save_entry(self, address: str, version: str, **change: object) -> dict:
        slug, draft = _entry_file(self.folder, address)
        entry = store.read(store.path_for(self.folder, slug, draft=draft))
        form = {"slug": slug, "draft": "1" if draft else "0", "base": version,
                "view": editor.MARKS,
                "title": change.get("title", entry.title),
                "body": change.get("body", entry.body),
                "categories": ", ".join(change.get("categories", entry.categories)),
                "tags": ", ".join(change.get("tags", entry.tags))}
        _, new_base = editor.save(self.folder, form)
        return {"address": address, "version": new_base}

    def _change_entry_address(self, address: str, version: str, to: str) -> dict:
        slug, draft = _entry_file(self.folder, address)
        new_base = editor.change_address(self.folder, slug, version, to.strip(), draft=draft)
        return {"address": to.strip(), "version": new_base}

    def _new_page(self, name: str) -> dict:
        return {"name": page_editor.new_page(self.folder, name.strip())}

    def _save_page(self, name: str, version: str, sections: list | None = None,
                   links: list | None = None) -> dict:
        folder, kind = self.folder, _kind(name)
        path, waiting = page_editor._read(folder, kind, name)
        if editor.digest(path) != version:
            raise editor.ChangedElsewhere(f"the {kind} file {name} changed since it was read")
        form = {"kind": kind, "name": name, "waiting": "1" if waiting else "0",
                "base": version, "view": page_editor.VISUAL}
        if page_editor._is_menu(kind, name):
            if links is None:
                raise Refused("assistant.links_owed")
            form["links"] = json.dumps(links)
        else:
            if sections is None:
                raise Refused("assistant.sections_owed")
            old = _sections_of(kind, name, store.read_html(path))
            kept = {tuple(item["keep"]) for item in sections
                    if isinstance(item, dict) and isinstance(item.get("keep"), list)}
            removed = [[at] for at in range(len(old.sections)) if (at,) not in kept]
            adopted = page_editor._area(kind, name, store.read_html(path))
            new = blocks.read(name, page_editor.put_sections(name, adopted, sections, removed))
            if _locked(old) != _locked(new):
                raise Refused("assistant.locked_section")
            form.update(sections=json.dumps(sections), removed=json.dumps(removed))
        _, new_base = page_editor._write(folder, form)
        return {"name": name, "version": new_base}

    def _add_photograph(self, filename: str, data: str) -> dict:
        name = photographs.add(self.folder, filename, _decoded(data))
        return {"name": name, "address": builder.web_photograph(name)}

    def _add_file(self, filename: str, data: str) -> dict:
        return {"name": files.add(self.folder, filename, _decoded(data))}

    def _save_look(self, version: str, choices: dict) -> dict:
        folder = self.folder
        # § 4.5: the route and their own CSS the Look screen would post unchanged.
        styled = look_screen._has_style_code(folder)
        if look_screen._offers_routes(folder) and not styled:
            raise Refused("assistant.own_stylesheets")
        form = {"base": version, "extra": look.read_extra(folder),
                "route": look_screen.PRESSLESS if look_screen._offers_routes(folder) else ""}
        for name in ("layout", "body_font", "heading_font", "text_size", "width"):
            form[name] = str(choices.get(name, ""))
        for scheme in ("light", "dark"):
            colours = choices.get(scheme) if isinstance(choices.get(scheme), dict) else {}
            for colour in look.COLOURS:
                form[f"{scheme}.{colour}"] = str(colours.get(colour, ""))
        effects = choices.get("effects") if isinstance(choices.get("effects"), list) else []
        for effect in look.EFFECTS:
            if effect in effects:
                form[f"effect.{effect}"] = "on"
        look_screen.save(folder, form)
        return {"version": look.digest(folder)}

    # --------------------------------------------------------------- asks ---

    def _ask(self, tool: str, arguments: dict) -> dict:
        with self.state:
            if self._still_waiting() is not None:
                raise Refused("assistant.one_waiting")
        plan = self._planned(tool, arguments)
        made = _Request(secrets.token_urlsafe(8), tool, arguments, time.monotonic(), plan,
                        self.mark())
        with self.state:
            if self._still_waiting() is not None:
                raise Refused("assistant.one_waiting")
            self.waiting = self.requests[made.id] = made
            self._prune()
        return {"request": made.id, "status": WAITING_STATE}

    def _publish(self, **arguments: str) -> dict:
        return self._ask("publish", arguments)

    def _undo_last_publish(self) -> dict:
        return self._ask("undo_last_publish", {})

    def _remove_entry(self, **arguments: str) -> dict:
        return self._ask("remove_entry", arguments)

    def _discard_changes(self, **arguments: str) -> dict:
        return self._ask("discard_changes", arguments)

    def _remove_page(self, **arguments: str) -> dict:
        return self._ask("remove_page", arguments)

    def _rename_page(self, **arguments: str) -> dict:
        return self._ask("rename_page", arguments)

    def _remove_file(self, **arguments: str) -> dict:
        return self._ask("remove_file", arguments)

    def _planned(self, tool: str, arguments: dict) -> dict:
        """`plan`, capturing the Store's notices for every ask but a publish,
        whose plan builds and so holds no capture (see `run`)."""
        if tool == "publish":
            return self.plan(tool, arguments)
        with self.face.capture():
            return self.plan(tool, arguments)

    def mark(self) -> str:
        return store.mark(self.folder, settings.path_for(self.folder))

    def plan(self, tool: str, arguments: dict) -> dict:
        """§ 4.6's plan: what the box lists. Checks the ask can run now, so a
        stale version or a missing entry is refused at once. The caller holds
        editor.LOCK."""
        folder = self.folder
        lines: list[str] = []
        if tool == "publish":
            entry, page = arguments.get("entry"), arguments.get("page")
            if entry is not None and page is not None:
                raise Refused("assistant.entry_or_page")
            if entry is not None:
                slug, draft = _entry_file(folder, entry)
                shown = publishing.plan(folder, entry=slug if draft else None,
                                        transport=self.transport)
            elif page is not None:
                page_editor._read(folder, _kind(page), page)     # it exists
                shown = publishing.plan(folder, page=(_kind(page), page),
                                        transport=self.transport)
            else:
                shown = publishing.plan(folder, transport=self.transport)
            return {"pages": sorted(shown.pages.values()), "added": shown.added,
                    "removed": shown.removed, "lines": lines}
        if tool == "undo_last_publish":
            lines.append(say("assistant.box.undo"))
        elif tool in ("remove_page", "rename_page"):
            name = arguments["name"]
            if not store.html_path_for(folder, store.PAGES_FOLDER, name).is_file():
                raise store.EntryNotFound(f"there is no page {name}")
            lines.append(say("assistant.box.rename", name=name, to=arguments["to"])
                         if tool == "rename_page" else say("assistant.box.remove", name=name))
        elif tool == "remove_entry":
            slug, draft = _entry_file(folder, arguments["address"])
            path = store.path_for(folder, slug, draft=draft)
            _same(path, arguments["version"])
            lines.append(say("assistant.box.bin", name=store.read(path).title or slug))
        elif tool == "discard_changes":
            entry, page = arguments.get("entry"), arguments.get("page")
            if (entry is None) == (page is None):
                raise Refused("assistant.entry_or_page")
            if entry is not None:
                slug, _ = _entry_file(folder, entry)
                path = store.path_for(folder, slug, draft=True)
                named = entry
            else:
                path = store.html_path_for(folder, _kind(page), page, waiting=True)
                named = page
            if not path.is_file():
                raise editor.ChangedElsewhere(f"{named} has no changes waiting")
            _same(path, arguments["version"])
            lines.append(say("assistant.box.discard", name=named))
        elif tool == "remove_file":
            name = arguments["name"]
            store.file_path_for(folder, name)
            if name not in store.list_files(folder):
                raise store.EntryNotFound(f"there is no file {name}")
            lines.append(say("assistant.box.bin", name=name))
        return {"pages": [], "added": 0, "removed": 0, "lines": lines}

    def _still_waiting(self) -> _Request | None:
        """The waiting request, after expiring one past its time. The caller
        holds `state`."""
        waiting = self.waiting
        if waiting is not None and time.monotonic() - waiting.made >= EXPIRES_SECONDS:
            waiting.status, self.waiting = EXPIRED, None
        return self.waiting

    def _prune(self) -> None:
        finished = [made for made in self.requests.values() if made is not self.waiting]
        for old in finished[:-_KEEP_FINISHED]:
            del self.requests[old.id]

    def status(self, request: str) -> dict:
        with self.state:
            self._still_waiting()
            made = self.requests.get(request)
        if made is None:
            return {"status": UNKNOWN, "said": say(_STATUS_WORDS[UNKNOWN])}
        return {"status": made.status,
                "said": made.said or say(_STATUS_WORDS[made.status])}

    # ------------------------------------------------- the writer's answer ---

    def waiting_now(self, request: Request) -> Reply:
        """GET /assistant/waiting (§ 4.6): the waiting request's plan, or none."""
        with self.state:
            waiting = self._still_waiting()
        if waiting is None:
            return _answer({"request": None})
        return _answer({"request": waiting.id, "stamp": waiting.mark[:16],
                        "publishing": pressing.state()["running"], **waiting.plan})

    def answer(self, request: Request) -> Reply:
        """POST /assistant/answer (§ 4.6): yes runs the press, not yet refuses."""
        form = editor.form_fields(request)
        with self.state:
            made = self._still_waiting()
            if made is None or made.id != form.get("request"):
                return _answer({"answered": False})
            if form.get("yes") != "1":
                made.status, self.waiting = REFUSED, None
                self.face.note(f"assistant: {made.tool} not yet")
                return _answer({"answered": True, "status": REFUSED})
        kind = _PRESSES.get(made.tool)
        if kind is None:
            with editor.LOCK:
                return self._yes(made, None)

        def busy(said: str) -> Reply:
            return _answer({"answered": False, "busy": True, "said": said})

        return pressing.run(kind, busy, lambda told: self._yes(made, told))

    def _yes(self, made: _Request, told: Callable[[pressing.Outcome], None] | None) -> Reply:
        """§ 4.6 steps 1 to 3, with the press record taken where one is owed.
        The mark is compared under editor.LOCK, so nothing can change between
        it and the press."""
        lock = editor.LOCK if told is not None else contextlib.nullcontext()
        with lock:
            if self.mark() != made.mark:
                try:
                    made.plan = self._planned(made.tool, made.arguments)
                    made.mark = self.mark()
                except Exception as exc:  # noqa: BLE001 -- the ask can no longer run
                    with self.state:
                        made.status, made.said, self.waiting = FAILED, _said(exc), None
                if told is not None:
                    told(pressing.Outcome(""))     # nothing ran, so nothing to say
                return _answer({"answered": False, "replanned": True})
            with self.state:
                made.status = RUNNING
            kind = _PRESSES.get(made.tool)
            try:
                if kind is not None:
                    self._press(made)      # a press captures step by step itself
                else:
                    with self.face.capture():
                        self._press(made)
            except Exception as exc:  # noqa: BLE001 -- told to the AI app and the writer
                failure = self.face.fail(exc, publishing=kind is not None,
                                         secret=say(_PUBLISHING_KEY))
                status, said = FAILED, _said(exc, secret=say(_PUBLISHING_KEY))
            else:
                failure, status, said = None, DONE, say(_STATUS_WORDS[DONE])
            if told is not None:
                told(pressing.ended(kind, status == DONE, failure))
            with self.state:
                made.status, made.said, self.waiting = status, said, None
        self.face.note(f"assistant: {made.tool} {status}")
        return _answer({"answered": True, "status": status, "failure": failure})

    def _press(self, made: _Request) -> None:
        folder, arguments, transport = self.folder, made.arguments, self.transport
        pressed = {"capture": self.face.capture, "notices": [], "transport": transport}
        if made.tool == "publish":
            entry, page = arguments.get("entry"), arguments.get("page")
            if entry is not None:
                slug, draft = _entry_file(folder, entry)
                if draft:
                    publishing.press_entry(folder, _entry_form(folder, slug), **pressed)
                    return
            elif page is not None:
                kind = _kind(page)
                copy = store.html_path_for(folder, kind, page, waiting=True)
                if copy.is_file():
                    text = store.read_html(copy)
                    page_editor.press_page(folder, {
                        "kind": kind, "name": page, "waiting": "1",
                        "base": editor.digest(copy), "view": page_editor.CODE, "text": text},
                        **pressed)
                    return
            publishing.press_site(folder, **pressed)
        elif made.tool == "undo_last_publish":
            undo.press_undo(folder, **pressed)
        elif made.tool in ("remove_page", "rename_page"):
            page_editor.reshape(folder, arguments["name"], arguments.get("to", ""),
                                renaming=made.tool == "rename_page", **pressed)
        elif made.tool == "remove_entry":
            slug, draft = _entry_file(folder, arguments["address"])
            editor.throw(folder, slug, arguments["version"], draft=draft)
        elif made.tool == "discard_changes":
            if arguments.get("entry") is not None:
                slug, _ = _entry_file(folder, arguments["entry"])
                editor.discard(folder, slug, arguments["version"])
            else:
                page = arguments["page"]
                page_editor.discard(folder, _kind(page), page, arguments["version"])
        elif made.tool == "remove_file":
            files_screen.remove(folder, arguments["name"])

    # ------------------------------------------------------------ the screen ---

    def setup_page(self, request: Request) -> str:
        on = is_on(self.own)
        program, arguments = _program()
        block = json.dumps({"mcpServers": {"pressless": {
            "command": program, "args": arguments}}}, indent=2)
        # The outcome's words are picked from this list, never taken from the address.
        told = _CONNECT_WORDS.get(request.query.get("connect", ""))
        e = html.escape
        command = " ".join([f'"{program}"', *arguments])
        # § 4.2: the apps named are the ones § 7 checks by hand.
        steps = (f'<h3>{say("assistant.app.claude_desktop")}</h3>'
                 f'<p>{say("assistant.connect.about")}</p>'
                 f'<form method="post" action="{CONNECT}"><p><button>'
                 f'{say("assistant.connect.button")}</button></p></form>'
                 f'<p role="status">{say(told) if told else ""}</p>'
                 f'<p>{say("assistant.steps.claude_desktop")}</p>'
                 f'<h3>{say("assistant.app.claude_code")}</h3>'
                 f'<p>{say("assistant.steps.claude_code")}</p>'
                 f'<pre id="assistant-claude-code">'
                 f'{e("claude mcp add --scope user pressless -- " + command)}</pre>'
                 f'<p><button type="button" data-copy="assistant-claude-code">'
                 f'{say("assistant.copy")}</button></p>'
                 f'<h3>{say("assistant.app.other")}</h3><p>{say("assistant.steps.other")}</p>')
        return (f'<h1>{say("assistant.title")}</h1><p>{say("assistant.about")}</p>'
                f'<form method="post" action="{SETUP}" class="switch-row">'
                f'<div class="states"><p>{say("assistant.on" if on else "assistant.off")}</p>'
                f'</div><span class="states"><button name="on" value="{"0" if on else "1"}">'
                f'{say("assistant.switch_off" if on else "assistant.switch_on")}</button>'
                f"</span></form>"
                f'<h2>{say("assistant.connect")}</h2><p>{say("assistant.program")}</p>'
                f'<pre id="assistant-program">{e(command)}</pre>'
                f'<p>{say("assistant.block")}</p><pre id="assistant-block">{e(block)}</pre>'
                f'<p><button type="button" data-copy="assistant-block">'
                f'{say("assistant.copy")}</button></p>{steps}'
                f"<script>{_COPY_SCRIPT}</script>")

    def set_switch(self, request: Request) -> Reply:
        on = editor.form_fields(request).get("on") == "1"
        switch(self.own, on)
        if on:
            self.open()
        else:
            self.shut()
        return Reply(b"", "text/plain; charset=utf-8", status=303, location=SETUP)

    def connect(self, request: Request) -> Reply:
        """POST /assistant/connect (§ 4.2): Pressless's entry into Claude
        Desktop's settings file, then the screen saying how it went."""
        said = connect_claude_desktop(claude_desktop_config(), *_program())
        self.face.note(f"assistant: connect Claude Desktop, {said.rsplit('.', 1)[1]}")
        return Reply(b"", "text/plain; charset=utf-8", status=303,
                     location=f"{SETUP}?connect={said.rsplit('.', 1)[1]}")

    def list_line(self) -> str:
        on = is_on(self.own)
        return (f'<p class="assistant-line"><a href="{SETUP}">{say("assistant.title")}</a> '
                f'{say("assistant.on" if on else "assistant.off")}</p>')

    def every_page(self) -> str:
        return f"<script>{pressing.SCRIPT}{_BOX_SCRIPT}</script>" if is_on(self.own) else ""


def register(face: Face, folder: Path, *, own: Path,
             transport: publisher.Transport | None = None) -> None:
    """Add the door, its setup screen, the box's two routes and the list's
    line to `face`, and open the door where the switch is on. `folder` is the
    open site's, `own` Pressless's own."""
    door = _Door(face, Path(folder), Path(own), transport)
    face.add_door(ADDRESS, door.call, door.admits)
    face.add_page("GET", SETUP, door.setup_page)
    face.add_page("POST", SETUP, door.set_switch)
    face.add_page("POST", CONNECT, door.connect)
    face.add_page("GET", WAITING, door.waiting_now)
    face.add_page("POST", ANSWER, door.answer)
    face.add_to_list(door.list_line, above=False)
    face.add_to_every_page(door.every_page)
    face.at_stop(door.shut)
    if is_on(own):
        door.open()


# ------------------------------------------------------------ the helpers ---


def _answer(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


def _kind(name: str) -> str:
    """A part's name is the part's; any other is a page's (§ 4.5)."""
    return store.FURNITURE_FOLDER if name in store.FURNITURE_NAMES else store.PAGES_FOLDER


def _entry_file(folder: Path, address: str) -> tuple[str, bool]:
    """The file an entry's address names, as the editor opens it: a draft;
    a published entry's working copy where one exists; else the entry."""
    if address in store.list_slugs(folder, draft=True):
        return address, True
    if address in store.list_slugs(folder, draft=False):
        copy = editor.working_copy(folder, address)
        return (copy, True) if copy is not None else (address, False)
    raise store.EntryNotFound(f"there is no entry {address!r}")


def _entry_form(folder: Path, slug: str) -> dict[str, str]:
    """The form a press takes, built from the draft as stored (§ 4.7), so the
    press saves nothing new."""
    path = store.path_for(folder, slug, draft=True)
    entry = store.read(path)
    return {"slug": slug, "draft": "1", "base": editor.digest(path), "view": editor.MARKS,
            "title": entry.title, "body": entry.body,
            "categories": ", ".join(entry.categories), "tags": ", ".join(entry.tags)}


def _same(path: Path, version: str) -> None:
    if not path.is_file() or editor.digest(path) != version:
        raise editor.ChangedElsewhere(f"{path.stem} changed since it was read")


def _decoded(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise Refused("assistant.bad_data") from None


def _sections_of(kind: str, name: str, text: str) -> blocks.Page:
    adopted = page_editor._area(kind, name, text)
    page = blocks.read(name, adopted) if adopted is not None else None
    if page is None:
        raise page_editor.SectionsUnreadable(f"the {kind} file {name} has no sections area")
    return page


_LOCKED_KINDS = (blocks.SCRIPT, blocks.STYLE, blocks.CODE)


def _is_locked(section: blocks.Section) -> bool:
    """§ 4.8: a script, style or code section. Words holding a Builder
    placeholder too, since the visual editor shows them as code."""
    return section.kind in _LOCKED_KINDS or (
        section.kind in (blocks.TEXT, blocks.HEADING) and "{{" in section.fields.get("html", ""))


def _locked(page: blocks.Page) -> list[blocks.Section]:
    """The locked sections in order: equal lists mean none was added, changed,
    moved or removed (§ 4.8)."""
    return [section for section in page_editor._paths(page).values() if _is_locked(section)]


def _shown(path: tuple[int, ...], section: blocks.Section) -> dict:
    if _is_locked(section):
        return {"path": list(path), "kind": section.kind, "locked": True}
    return {"path": list(path), "kind": section.kind, "fields": dict(section.fields),
            "parts": len(section.parts)}


def _program() -> tuple[str, list[str]]:
    """What an AI app starts: the packaged program, else this Python running
    the package, each with --assistant (§ 4.2). On Windows the artefact is
    the program's folder, and an app starts the Pressless.exe inside it."""
    try:
        artefact = paths.artefact_path()
    except paths.NotPackaged:
        return sys.executable, ["-m", "pressless", "--assistant"]
    if sys.platform == "win32":
        return sys.executable, ["--assistant"]
    return str(artefact), ["--assistant"]


_CLAUDE_FILE = "claude_desktop_config.json"
_CLAUDE_COPY = "claude_desktop_config.before-pressless.json"
_CLAUDE_FOLDER = "Claude"
_WINDOWS_SETTINGS = ("AppData", "Roaming")     # where %APPDATA% is unset
_MAC_SETTINGS = ("Library", "Application Support")
_CONNECT_WORDS = {word: "assistant.connect." + word
                  for word in ("done", "not_found", "unreadable")}


def claude_desktop_config() -> Path:
    """Where Claude Desktop keeps its settings file on this system (§ 4.2)."""
    if sys.platform == "win32":
        folder = Path(os.environ.get("APPDATA") or Path.home().joinpath(*_WINDOWS_SETTINGS))
    elif sys.platform == "darwin":
        folder = Path.home().joinpath(*_MAC_SETTINGS)
    else:
        folder = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return folder / _CLAUDE_FOLDER / _CLAUDE_FILE


def connect_claude_desktop(config: Path, program: str, arguments: list[str]) -> str:
    """Put Pressless's entry into Claude Desktop's settings file, keeping
    everything else in it, and answer the words saying how it went (§ 4.2,
    INV-14). A copy of the file as it was is kept beside it first. A file that
    does not read as that app's settings is left exactly as it is."""
    if not config.parent.is_dir():
        return "assistant.connect.not_found"
    try:
        # Bytes, so the copy keeps the file's own line endings.
        text = config.read_bytes().decode("utf-8-sig") if config.is_file() else ""
        held = json.loads(text) if text.strip() else {}
        servers = held.get("mcpServers", {}) if isinstance(held, dict) else None
        if not isinstance(servers, dict):
            return "assistant.connect.unreadable"
        entry = {"command": program, "args": arguments}
        if servers.get("pressless") != entry:
            if config.is_file():
                safe_write.write_whole(config.with_name(_CLAUDE_COPY), text,
                                       prefix=".pressless-", newline="")
            held["mcpServers"] = {**servers, "pressless": entry}
            safe_write.write_whole(
                config, json.dumps(held, indent=2, ensure_ascii=False) + "\n",
                prefix=".pressless-")
    except (OSError, ValueError):     # not read, not JSON, or not written
        return "assistant.connect.unreadable"
    return "assistant.connect.done"


_COPY_SCRIPT = """
document.querySelectorAll("button[data-copy]").forEach((button) => {
  button.addEventListener("click", () => {
    const text = document.getElementById(button.dataset.copy).textContent;
    if (navigator.clipboard) navigator.clipboard.writeText(text);
  });
});
"""

# § 4.6: every Face page asks for the waiting request every two seconds while
# the switch is on, and shows it in PRESS-0345's box. A box whose request has
# gone or been re-planned closes; no box opens while a press runs.
_BOX_SCRIPT = """
window.presslessHelper = window.presslessHelper || (() => {
  let shown = "";
  const ask = async () => {
    let now;
    try { now = await (await fetch("/assistant/waiting")).json(); } catch (error) { return; }
    const stamp = now.request ? now.request + ":" + now.stamp : "";
    const open = document.querySelector("dialog.plan[data-request]");
    if (open && open.dataset.request !== stamp) { open.close(); open.remove(); }
    if (!stamp || stamp === shown || now.publishing) return;
    shown = stamp;
    const yes = await window.presslessPlan(now, {title: "script.assistant.title",
      go: "script.assistant.go", wait: "script.assistant.wait", request: stamp});
    const body = new URLSearchParams({request: now.request, yes: yes ? "1" : "0"});
    // PRESS-0356: the answer comes back when the press has ended. Until then a
    // page with a press row shows it running; after it the home screen, whose
    // lists the press changed, is drawn again. Other screens may hold typing.
    if (yes) window.presslessPress.ask();
    try {
      const reply = await (await fetch("/assistant/answer", {method: "POST", body})).json();
      if (reply.busy || reply.replanned) shown = "";
      else if (yes && reply.answered && window.location.pathname === "/") {
        window.location.reload();
      }
    } catch (error) { shown = ""; }
  };
  setInterval(ask, 2000);
  return true;
})();
"""
