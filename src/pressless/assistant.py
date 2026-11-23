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
import shlex
import subprocess
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
    log,
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
    is_secret,
    sentence_for,
)
from pressless.words import say

SWITCH_NAME = "assistant.json"        # {"on": true|false}; absent means off
DOOR_NAME = "assistant-door.json"     # the port, the token and the version
# The door and the screens' routes. bridge.DOOR_PATH copies ADDRESS, and
# _BOX_SCRIPT writes the box's two out; a test checks each copy matches.
ADDRESS = "/assistant"
SETUP = "/assistant/setup"
WAITING_ROUTE = "/assistant/waiting"
ANSWER_ROUTE = "/assistant/answer"
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
_NONCE_LIMIT = 128                    # the longest PROVE nonce answered
_KEY_WORDS = "failure.secret.publishing_key"     # the words naming the key, never the key
# What list_files says names a file, by builder.FileUser's kind: a page and a
# part may share a name (PRESS-0420).
_USER_KINDS = {store.PAGES_FOLDER: "page", store.FURNITURE_FOLDER: "part",
               store.LOOK_FOLDER: "look"}
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


def _owner_only(handle: int) -> None:
    """write_whole's check for the door file: the temporary is made private
    to its owner before the token is written (§ 4.2). mkstemp's 0600 does
    that elsewhere; on Windows it only sets the read-only flag, so the file
    would take its folder's permissions, which may let other users read it."""
    if sys.platform == "win32":
        _windows_owner_only(handle)


# SDDL for a protected access list granting the file's owner everything and
# no one else anything, nothing inherited from the folder.
_OWNER_ONLY_SDDL = "D:P(A;;FA;;;OW)"
_FS_PERSISTENT_ACLS = 0x8
_SE_FILE_OBJECT = 1
_DACL_PROTECTED = 0x4 | 0x80000000     # DACL_ and PROTECTED_DACL_SECURITY_INFORMATION


def _windows_owner_only(handle: int) -> None:
    """Give the open file `handle` _OWNER_ONLY_SDDL's access list. A drive
    with no permissions to set (FAT, exFAT) is left as it is: § 4.2 asks for
    owner-only "where the system has them". Raises OSError where Windows
    refuses, so no token is written to a file others may read."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    opened = wintypes.HANDLE(msvcrt.get_osfhandle(handle))
    flags = wintypes.DWORD()
    if not kernel32.GetVolumeInformationByHandleW(
            opened, None, 0, None, None, ctypes.byref(flags), None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not flags.value & _FS_PERSISTENT_ACLS:
        return
    name = ctypes.create_unicode_buffer(32768)
    if not kernel32.GetFinalPathNameByHandleW(opened, name, len(name), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    described = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            _OWNER_ONLY_SDDL, 1, ctypes.byref(described), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        if not advapi32.GetSecurityDescriptorDacl(
                described, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
            raise ctypes.WinError(ctypes.get_last_error())
        error = advapi32.SetNamedSecurityInfoW(
            name, _SE_FILE_OBJECT, wintypes.DWORD(_DACL_PROTECTED), None, None, dacl, None)
        if error:
            raise ctypes.WinError(error)
    finally:
        kernel32.LocalFree(described)


# ----------------------------------------------------------- the requests ---


@dataclasses.dataclass
class _Ask:
    """One request an ask made (§ 4.6): what it asks, the plan the box lists,
    and the Store's mark when that plan was made. Not face.Request, an HTTP
    request."""
    id: str
    tool: str
    arguments: dict
    made: float
    plan: dict
    mark: str
    status: str = WAITING_STATE
    said: str = ""


def _said(failure: BaseException, *, secret: str | None = None) -> str:
    """A failure as plain text: its sentence's three parts (§ 4.3), as the
    writer's screen words it. An unforeseen failure left the site unchanged:
    the Publisher raises OutcomeUnknown itself where an upload may be unknown
    (PRESS-0013 § 4.3)."""
    if isinstance(failure, Refused):
        return failure.slots["said"]
    told = sentence_for(failure, publishing=False, secret=secret)
    return " ".join(part for part in (told.what, told.site.words, _chat_next(told.next))
                    if part)


# A screen's next step may point "below", at a failure's details or a link; a
# chat has neither (§ 4.3). Each such step's words for a chat, by the screen's
# key. A step is matched by its words, not its failure's type, so a failure
# whose sentence fell back to the unforeseen one gets that one's.
_CHAT_NEXT = {
    "failure.again": "assistant.next.again",
    "failure.unforeseen.next": "assistant.next.unforeseen",
    "failure.store.DanglingReply.next": "assistant.next.send_log",
    "failure.credentials.NoStore.next": "assistant.next.send_log",
    "failure.settings.SettingsError.next": "assistant.next.settings",
    "failure.builder.BuildStopped.next": "assistant.next.build_stopped",
    "failure.insights.InsightsError.next": "assistant.next.again_later",
    "failure.credentials.CredentialError.next": "assistant.next.credential",
    "failure.publisher.TooLarge.next": "assistant.next.too_large",
    # A publish builds the site first, so trying again is building again.
    "failure.publisher.SiteFolderMissing.next": "assistant.next.again",
    "failure.publisher.UnfetchablePath.next": "assistant.next.unfetchable",
    "failure.publishing.NothingToPublish.next": "assistant.next.nothing_to_publish",
    "failure.publishing.TakeoverOwed.next": "assistant.next.takeover",
    "failure.publishing.WouldReplaceASite.next": "assistant.next.would_replace",
}


def _chat_next(screen: str) -> str:
    """`screen`, a next step's words, as the AI app is told it: _CHAT_NEXT's
    words where the screen's point below, naming the log the details are in."""
    for key, chat in _CHAT_NEXT.items():
        if say(key) == screen:
            return say(chat, log=say("assistant.log", file=log.FILE_NAME))
    return screen


class _Door:
    def __init__(self, face: Face, folder: Path, own: Path,
                 transport: publisher.Transport | None) -> None:
        self.face, self.folder, self.own, self.transport = face, folder, own, transport
        self.token = secrets.token_urlsafe(32)
        self.requests: dict[str, _Ask] = {}
        # The one open request: waiting for the writer, or running after Yes.
        self.open_ask: _Ask | None = None
        self.state = threading.Lock()     # guards `requests` and `open_ask`, briefly
        # Where the door file could not be written, so no AI app can connect.
        self.unopened = False
        # The nonce `admits` took a PROVE header with, for `call` on the same
        # request's thread: the Face runs both there, one after the other.
        self._proving = threading.local()

    # -------------------------------------------------------- the door file ---

    def open(self) -> None:
        """Write the door file with a new token (§ 4.2)."""
        self.token = secrets.token_urlsafe(32)
        safe_write.write_whole(door_path(self.own), json.dumps(
            {"port": self.face.port, "token": self.token, "version": __version__}),
            prefix=".assistant-door-", check=_owner_only)

    def open_door(self) -> bool:
        """`open`, or False where the door file cannot be written: the log
        notes it, the setup screen says so, and the Face serves on (§ 6)."""
        try:
            self.open()
        except OSError as exc:
            self.face.note(f"assistant: the door did not open, {type(exc).__name__}")
            self.unopened = True
            return False
        self.unopened = False
        return True

    def shut(self) -> None:
        door_path(self.own).unlink(missing_ok=True)

    def admits(self, authorization: str) -> bool:
        """§ 4.3: the switch is on, and the header carries this door's token
        or asks the door to prove it holds it, which runs nothing."""
        scheme, _, offered = authorization.partition(" ")
        offered = offered.strip()
        self._proving.nonce = None
        if not is_on(self.own):
            return False
        if scheme == assistant_tools.PROVE and 0 < len(offered) <= _NONCE_LIMIT:
            self._proving.nonce = offered
            return True
        return scheme == "Bearer" and is_secret(offered, self.token)

    # ------------------------------------------------------------- a call ---

    def call(self, request: Request) -> Reply:
        nonce, self._proving.nonce = getattr(self._proving, "nonce", None), None
        if nonce is not None:
            # Admitted without the token: the proof, and nothing the body asks.
            return _answer({"proof": assistant_tools.proof(self.token, nonce)})
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
            key, slots = why
            return _answer({"ok": False, "said": say("assistant.bad_call", why=say(key, **slots))})
        with LOCK:
            try:
                result = self.run(tool, arguments)
            except Exception as exc:  # noqa: BLE001 -- every failure is said, none raised
                self.face.note(f"assistant: {tool} refused {type(exc).__name__}")
                self.face.fail(exc, publishing=False)     # its details, in the log
                secret = (say("failure.secret.google_sign_in") if tool == "read_insights"
                          else say(_KEY_WORDS))
                return _answer({"ok": False, "said": _said(exc, secret=secret)})
        self.face.note(f"assistant: {tool} ok")
        return _answer({"ok": True, "result": result})

    def run(self, tool: str, arguments: dict) -> dict:
        # Every tool's work is the method named "_" and its name; request_status
        # alone is `status`. A tool's name must not be a helper's below.
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
            open_ask = self._open_ask()
            asked = (None if open_ask is None else
                     {"request": open_ask.id, "tool": open_ask.tool, "status": open_ask.status})
        return {"name": identity.name if identity is not None else "",
                "address": self.face.live_address(), "journal": store.journal_on(folder),
                "entries": len(self._entries()), "pages": len(pages),
                "publishing": pressing.state()["running"],
                "waiting": asked}

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
        path, _ = page_editor.current_file(self.folder, kind, name)
        text = store.read_html(path)
        version = editor.digest(path)
        if page_editor.is_menu(kind, name):
            return {"name": name, "version": version,
                    "links": [{"at": at, "words": words, "href": href}
                              for at, (words, href) in enumerate(menu.links(text))]}
        page = _sections_of(kind, name, text)
        return {"name": name, "version": version,
                "sections": [_shown(at, section) for at, section in
                             page_editor.section_paths(page).items()]}

    def _list_files(self) -> dict:
        folder = self.folder
        named = builder.files_named(folder)
        return {"photographs": [{"name": name, "address": builder.web_photograph(name)}
                                for name in store.list_photographs(folder)],
                "files": [{"name": name,
                           "used_by": [{"kind": _USER_KINDS[user.kind], "name": user.name}
                                       for user in named.get(name, ())]}
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
        path, waiting = page_editor.current_file(folder, kind, name)
        if editor.digest(path) != version:
            raise editor.ChangedElsewhere(f"the {kind} file {name} changed since it was read")
        form = {"kind": kind, "name": name, "waiting": "1" if waiting else "0",
                "base": version, "view": page_editor.VISUAL}
        if page_editor.is_menu(kind, name):
            if links is None:
                raise Refused("assistant.links_owed")
            form["links"] = json.dumps(links)
        else:
            if sections is None:
                raise Refused("assistant.sections_owed")
            old = _sections_of(kind, name, store.read_html(path))
            kept = {tuple(item["keep"]) for item in sections
                    if isinstance(item, dict) and isinstance(item.get("keep"), list)}
            # Top-level paths only, as the page screen's script posts them: a
            # changed section is sent whole and its old place marked removed
            # (page_editor.put_sections).
            removed = [[at] for at in range(len(old.sections)) if (at,) not in kept]
            adopted = page_editor.sections_area(kind, name, store.read_html(path))
            new = blocks.read(name, page_editor.put_sections(name, adopted, sections, removed))
            if _locked(old) != _locked(new):
                raise Refused("assistant.locked_section")
            form.update(sections=json.dumps(sections), removed=json.dumps(removed))
        _, new_base = page_editor.write_copy(folder, form)
        return {"name": name, "version": new_base}

    def _add_photograph(self, filename: str, data: str) -> dict:
        name = photographs.add(self.folder, filename, _decoded(data))
        return {"name": name, "address": builder.web_photograph(name)}

    def _add_file(self, filename: str, data: str) -> dict:
        return {"name": files.add(self.folder, filename, _decoded(data))}

    def _save_look(self, version: str, choices: dict) -> dict:
        folder = self.folder
        # § 4.5: the save posts the route and the hand-written CSS the Look
        # screen would post, so neither changes. A site offering both routes
        # with no Pressless style code stands on its own stylesheets, and a
        # save of choices would move it to the Pressless look: refused.
        offers_routes = look_screen.offers_routes(folder)
        if offers_routes and not look_screen.has_style_code(folder):
            raise Refused("assistant.own_stylesheets")
        form = {"base": version, "extra": look.read_extra(folder),
                "route": look_screen.PRESSLESS if offers_routes else ""}
        for name in _PLAIN_CHOICES:
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
            if self._open_ask() is not None:
                raise Refused("assistant.one_waiting")
        plan, notices = self._planned(tool, arguments)
        made = _Ask(secrets.token_urlsafe(8), tool, arguments, time.monotonic(), plan,
                        self.mark())
        with self.state:
            if self._open_ask() is not None:
                raise Refused("assistant.one_waiting")
            self.open_ask = self.requests[made.id] = made
            self._prune()
        asked = {"request": made.id, "status": WAITING_STATE}
        if notices:
            asked["notices"] = notices      # as `run` adds them to a read or a write
        return asked

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

    def _planned(self, tool: str, arguments: dict) -> tuple[dict, list[str]]:
        """`plan`, and the Store's notices it raised. Captured for every ask
        but a publish, whose plan builds and so holds no capture (see `run`)."""
        if tool == "publish":
            return self.plan(tool, arguments), []
        with self.face.capture() as notices:
            plan = self.plan(tool, arguments)
        return plan, notices

    def mark(self) -> str:
        return store.mark(self.folder, settings.path_for(self.folder))

    # An ask lives in five places, each kept by hand: its Tool in
    # assistant_tools, its `_<name>` method above, a branch in `plan` and in
    # `_press`, and an entry in _PRESSES where it publishes or undoes. A sixth
    # where its plan builds, as publish's does: `_planned`, which must then
    # hold no capture. A tool missing from `plan` or `_press` raises rather
    # than doing nothing.

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
                # § 4.5: an entry with nothing waiting publishes the site as it
                # stands; `_press` makes the same choice.
                shown = publishing.press_preview(folder, entry=slug if draft else None,
                                                 transport=self.transport)
            elif page is not None:
                page_editor.current_file(folder, _kind(page), page)     # it exists
                # A page with nothing waiting: publishing.press_preview falls back to
                # the whole site, as `_press` does.
                shown = publishing.press_preview(folder, page=(_kind(page), page),
                                                 transport=self.transport)
            else:
                shown = publishing.press_preview(folder, transport=self.transport)
            return {"pages": sorted(shown.pages.values()), "added": shown.added,
                    "removed": shown.removed, "lines": lines}
        if tool == "undo_last_publish":
            lines.append(say("assistant.box.undo"))
        elif tool in ("remove_page", "rename_page"):
            name, renaming = arguments["name"], tool == "rename_page"
            if not store.html_path_for(folder, store.PAGES_FOLDER, name).is_file():
                raise store.EntryNotFound(f"there is no page {name}")
            to = arguments.get("to", "")
            hint = page_editor.reshape_hint(folder, name, to, renaming, settings.load(folder))
            if hint is not None:
                raise page_editor.NameRefused(hint)     # the Pages screen's own refusal
            # The box names the address the rename makes, never the AI app's
            # own text (§ 4.6).
            lines.append(say("assistant.box.rename", name=name, to=editor.name_address(to))
                         if renaming else say("assistant.box.remove", name=name))
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
            store.file_path_for(folder, name)     # refuses a name the Store would not keep
            if name not in store.list_files(folder):
                raise store.EntryNotFound(f"there is no file {name}")
            lines.append(say("assistant.box.bin", name=name))
        else:
            raise ValueError(f"no plan for the ask {tool}")
        return {"pages": [], "added": 0, "removed": 0, "lines": lines}

    def _open_ask(self) -> _Ask | None:
        """The one open request: waiting for the writer, or taken by a Yes and
        running. One waiting past its time expires first; one running never
        does. The caller holds `state`."""
        waiting = self.open_ask
        if (waiting is not None and waiting.status == WAITING_STATE
                and time.monotonic() - waiting.made >= EXPIRES_SECONDS):
            waiting.status, self.open_ask = EXPIRED, None
        return self.open_ask

    def _close(self, made: _Ask, status: str, said: str = "") -> None:
        """`made` has ended with `status`; it stops being the open request
        only if it still is one. The caller holds `state`."""
        made.status, made.said = status, said
        if self.open_ask is made:
            self.open_ask = None

    def _prune(self) -> None:
        finished = [made for made in self.requests.values() if made is not self.open_ask]
        for old in finished[:-_KEEP_FINISHED]:
            del self.requests[old.id]

    def status(self, request_id: str) -> dict:
        with self.state:
            self._open_ask()
            made = self.requests.get(request_id)
        if made is None:
            return {"status": UNKNOWN, "said": say(_STATUS_WORDS[UNKNOWN])}
        return {"status": made.status,
                "said": made.said or say(_STATUS_WORDS[made.status])}

    # ------------------------------------------------- the writer's answer ---

    def waiting_now(self, request: Request) -> Reply:
        """GET /assistant/waiting (§ 4.6): the waiting request's plan, or none."""
        with self.state:
            waiting = self._open_ask()
            if waiting is None or waiting.status != WAITING_STATE:
                return _answer({"request": None})     # a taken request has no box
            # Read together, as a re-plan writes them together.
            shown = {"request": waiting.id, "stamp": waiting.mark[:16], **waiting.plan}
        return _answer({**shown, "publishing": pressing.state()["running"]})

    def answer(self, request: Request) -> Reply:
        """POST /assistant/answer (§ 4.6): yes runs the press, not yet refuses.
        A Yes takes the request before `state` is let go, so an answer from
        another tab finds nothing waiting until the press ends or the request
        is handed back to wait."""
        form = editor.form_fields(request)
        with self.state:
            made = self._open_ask()
            if made is None or made.id != form.get("request") or made.status != WAITING_STATE:
                return _answer({"answered": False})
            if form.get("yes") != "1":
                self._close(made, REFUSED)
                self.face.note(f"assistant: {made.tool} not yet")
                return _answer({"answered": True, "status": REFUSED})
            made.status = RUNNING
        kind = _PRESSES.get(made.tool)
        if kind is None:
            with editor.LOCK:
                return self._yes(made, None)

        def busy(said: str) -> Reply:
            self._hand_back(made)
            return _answer({"answered": False, "busy": True, "said": said})

        return pressing.run(kind, busy, lambda told: self._yes(made, told))

    def _hand_back(self, made: _Ask) -> None:
        """A taken request that did not run waits again."""
        with self.state:
            if self.open_ask is made:
                made.status = WAITING_STATE

    def _yes(self, made: _Ask, told: Callable[[pressing.Outcome], None] | None) -> Reply:
        """§ 4.6 steps 1 to 3, with the press record taken where one is owed.
        The mark is compared under editor.LOCK, so nothing can change between
        it and the press."""
        kind = _PRESSES.get(made.tool)
        # Without a press record the caller already holds editor.LOCK, which
        # is not re-entrant, so taking it again here would hang.
        lock = editor.LOCK if told is not None else contextlib.nullcontext()
        # Whatever raises, a taken request ends, unless it waits again: one
        # left running would refuse every later ask.
        status, said, failure = FAILED, say(_STATUS_WORDS[FAILED]), None
        try:
            with lock:
                try:
                    if self.mark() != made.mark:
                        plan, _ = self._planned(made.tool, made.arguments)
                        mark = self.mark()
                        with self.state:
                            made.plan, made.mark = plan, mark
                        self._hand_back(made)
                        status = WAITING_STATE
                        if told is not None:
                            # Nothing ran: no words, and no failed press counted.
                            told(pressing.quiet())
                        return _answer({"answered": False, "replanned": True})
                    if kind is not None:
                        self._press(made)      # a press captures step by step itself
                    else:
                        with self.face.capture():
                            self._press(made)
                except Exception as exc:  # noqa: BLE001 -- told to the AI app and the writer
                    # As the writer's own press shows it, the way on included
                    # (PRESS-0417, PRESS-0424). A re-plan that finds the ask
                    # can no longer run fails it the same way (§ 4.6).
                    status, said = FAILED, _said(exc, secret=say(_KEY_WORDS))
                    failure = publishing.press_failure(self.face, exc)
                else:
                    status, said = DONE, say(_STATUS_WORDS[DONE])
                if told is not None:
                    told(pressing.ended(kind, status == DONE, failure))
        finally:
            if status != WAITING_STATE:
                with self.state:
                    self._close(made, status, said)
        self.face.note(f"assistant: {made.tool} {status}")
        # A press's failure is on the press row; the box's script shows only an
        # ask's that runs none, which no row shows (PRESS-0403).
        return _answer({"answered": True, "status": status,
                        "failure": failure if told is None else None})

    def _press(self, made: _Ask) -> None:
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
            # § 4.5: an entry or page with nothing waiting publishes the site
            # as it stands, as `plan` showed it.
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
        else:
            raise ValueError(f"no press for the ask {made.tool}")

    # ------------------------------------------------------------ the screen ---

    def setup_page(self, request: Request) -> str:
        on = is_on(self.own)
        return (f'<h1>{say("assistant.title")}</h1><p>{say("assistant.about")}</p>'
                f'<form method="post" action="{SETUP}" class="switch-row">'
                f'<div class="states"><p>{say(_switch_words(on, self.unopened))}</p>'
                f'</div><span class="states"><button name="on" value="{"0" if on else "1"}">'
                f'{say("assistant.switch_off" if on else "assistant.switch_on")}</button>'
                f"</span></form>"
                f'<h2>{say("assistant.connect")}</h2>{self._connecting(request)}'
                f"<script>{_COPY_SCRIPT}</script>")

    def _connecting(self, request: Request) -> str:
        """The program an AI app starts and each app's steps, or why there is
        none (PRESS-0418)."""
        try:
            program, arguments = _program(self.own)
        except paths.NotPackaged:
            return f'<p>{say("assistant.no_program")}</p>'
        block = json.dumps({"mcpServers": {"pressless": {
            "command": program, "args": arguments}}}, indent=2)
        # The outcome's words are picked from this list, never taken from the address.
        told = _CONNECT_WORDS.get(request.query.get("connect", ""))
        e = html.escape
        command = _command_line(program, arguments)
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
        return (f'<p>{say("assistant.program")}</p>'
                f'<pre id="assistant-program">{e(command)}</pre>'
                f'<p>{say("assistant.block")}</p><pre id="assistant-block">{e(block)}</pre>'
                f'<p><button type="button" data-copy="assistant-block">'
                f'{say("assistant.copy")}</button></p>{steps}')

    def set_switch(self, request: Request) -> Reply:
        """The switch is saved on only once the door is open, so a door that
        cannot open is not tried again at every launch."""
        on = editor.form_fields(request).get("on") == "1"
        if on and self.open_door():
            try:
                switch(self.own, True)
            except BaseException:
                self.shut()
                raise
        elif not on:
            switch(self.own, False)
            self.shut()
            self.unopened = False
        return Reply(b"", "text/plain; charset=utf-8", status=303, location=SETUP)

    def connect(self, request: Request) -> Reply:
        """POST /assistant/connect (§ 4.2): Pressless's entry into Claude
        Desktop's settings file, then the screen saying how it went."""
        try:
            program, arguments = _program(self.own)
        except paths.NotPackaged:
            # The screen says why there is no program to connect (PRESS-0418).
            return Reply(b"", "text/plain; charset=utf-8", status=303, location=SETUP)
        # A words key, of which the address carries only the last part.
        outcome = connect_claude_desktop(claude_desktop_config(), program, arguments)
        ended = outcome.rsplit(".", 1)[1]
        self.face.note(f"assistant: connect Claude Desktop, {ended}")
        return Reply(b"", "text/plain; charset=utf-8", status=303,
                     location=f"{SETUP}?connect={ended}")

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
    face.add_page("GET", WAITING_ROUTE, door.waiting_now)
    face.add_page("POST", ANSWER_ROUTE, door.answer)
    face.add_piece("site-notices", door.list_line)
    face.add_to_every_page(door.every_page)
    face.at_stop(door.shut)
    if is_on(own):
        door.open_door()


# ------------------------------------------------------------ the helpers ---


def _answer(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


def _switch_words(on: bool, unopened: bool) -> str:
    """The setup screen's line: the switch, or why no app can connect."""
    if unopened:
        return "assistant.unopened"
    return "assistant.on" if on else "assistant.off"


def _command_line(program: str, arguments: list[str]) -> str:
    """`program` and `arguments` as one line a shell reads back as the same
    list: a source run's folder may hold a space."""
    if sys.platform == "win32":
        return subprocess.list2cmdline([program, *arguments])
    return shlex.join([program, *arguments])


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
    adopted = page_editor.sections_area(kind, name, text)
    page = blocks.read(name, adopted) if adopted is not None else None
    if page is None:
        raise page_editor.SectionsUnreadable(f"the {kind} file {name} has no sections area")
    return page


_LOCKED_KINDS = (blocks.SCRIPT, blocks.STYLE, blocks.CODE)
# The look's choices that are one word each, the form fields of the same
# names: look.Choices' text fields, so a new one is posted without an edit here.
_PLAIN_CHOICES = tuple(field.name for field in dataclasses.fields(look.Choices)
                       if field.type in ("str", str))


def _is_locked(section: blocks.Section) -> bool:
    """§ 4.8: a script, style or code section. Words holding a Builder
    placeholder too, since the visual editor shows them as code."""
    return section.kind in _LOCKED_KINDS or (
        section.kind in (blocks.TEXT, blocks.HEADING) and "{{" in section.fields.get("html", ""))


def _locked(page: blocks.Page) -> list[blocks.Section]:
    """The locked sections in order: equal lists mean none was added, changed,
    moved or removed (§ 4.8)."""
    return [section for section in page_editor.section_paths(page).values() if _is_locked(section)]


def _shown(path: tuple[int, ...], section: blocks.Section) -> dict:
    if _is_locked(section):
        return {"path": list(path), "kind": section.kind, "locked": True}
    return {"path": list(path), "kind": section.kind, "fields": dict(section.fields),
            "parts": len(section.parts)}


def _program(own: Path) -> tuple[str, list[str]]:
    """What an AI app starts: the packaged program, else this Python running
    the package, each with --assistant (§ 4.2). A source run has no artefact
    to find its folder beside, so it names `own`, this Face's (§ 4.4). On
    Windows the artefact is the program's folder, and an app starts the
    Pressless.exe inside it. A packaged program that cannot find itself
    raises NotPackaged: it cannot run `-m pressless`, and its bridge would
    not find its folder either (PRESS-0418)."""
    try:
        artefact = paths.artefact_path()
    except paths.NotPackaged:
        if getattr(sys, "frozen", False):
            raise
        return sys.executable, ["-m", "pressless", "--assistant", str(Path(own).absolute())]
    if sys.platform == "win32":
        return sys.executable, ["--assistant"]
    return str(artefact), ["--assistant"]


_CLAUDE_FILE = "claude_desktop_config.json"
_CLAUDE_COPY = "claude_desktop_config.before-pressless.json"
_CLAUDE_FOLDER = "Claude"
_WINDOWS_SETTINGS = ("AppData", "Roaming")     # where %APPDATA% is unset
_MAC_SETTINGS = ("Library", "Application Support")
# Every outcome connect_claude_desktop answers, which writes each key out in
# full so the words test finds it: an outcome missing here shows no words.
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
    INV-14). A copy of the file as it was before Pressless is kept beside it
    first: made while the file holds no Pressless entry, or no copy exists,
    so connecting again does not replace it. A file that does not read as
    that app's settings is left exactly as it is. The outcomes are
    _CONNECT_WORDS'."""
    if not config.parent.is_dir():
        return "assistant.connect.not_found"
    try:
        # Decoded as it is, so the copy keeps the file's own line endings and
        # any byte-order mark; the JSON is read without the mark.
        was = config.read_bytes().decode("utf-8") if config.is_file() else ""
        text = was.removeprefix("\ufeff")
        held = json.loads(text) if text.strip() else {}
        servers = held.get("mcpServers", {}) if isinstance(held, dict) else None
        if not isinstance(servers, dict):
            return "assistant.connect.unreadable"
        entry = {"command": program, "args": arguments}
        if servers.get("pressless") != entry:
            copy = config.with_name(_CLAUDE_COPY)
            if config.is_file() and ("pressless" not in servers or not copy.exists()):
                safe_write.write_whole(copy, was, prefix=".pressless-", newline="")
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
    // page with a press row shows it running; after it Your site, Pages or Journal,
    // whose lists the press changed, is drawn again. Other screens may hold typing.
    // A failure the answer carries, which no press row shows, opens over any page.
    if (yes) window.presslessPress.ask();
    try {
      const reply = await (await fetch("/assistant/answer", {method: "POST", body})).json();
      if (reply.busy || reply.replanned) shown = "";
      else if (reply.failure) window.presslessFailed(reply.failure);
      else if (yes && reply.answered
               && ["/", "/pages", "/journal"].includes(window.location.pathname)) {
        window.location.reload();
      }
    } catch (error) { shown = ""; }
  };
  setInterval(ask, 2000);
  return true;
})();
"""
