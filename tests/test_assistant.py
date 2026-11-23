# The AI helper's door (PRESS-0337).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0337-ai-assistant.md § 5. The file names and words a test
# pins are written out here rather than imported, so the module is never
# compared against itself (docs/working-here.md, Writing or changing tests).
#
# GitHub is the Publisher tests' recording double and Credentials a double,
# so no test reaches the network or a real keyring.
from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import html
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from _face_session import Browser
from _signalled import Signalled
from test_publisher import _listing, _reads, _Transport, _writes
from test_publishing import KEY, _base, _entry, _folder, _key

from pressless import (
    assistant,
    assistant_tools,
    blocks,
    bridge,
    dashboard,
    editor,
    face,
    look,
    page_editor,
    pressing,
    publisher,
    publishing,
    starter,
    store,
    undo,
    words,
)

DOOR_FILE = "assistant-door.json"
SWITCH_FILE = "assistant.json"
LOG_FILE = "pressless.log"
CHANGED_WORDS = "This entry was changed in another window or outside Pressless"
LOCKED_WORDS = "which the AI helper may not do"
ONE_WAITING_WORDS = "A request is already waiting"
OPEN_WORDS = "Pressless is not open, or its AI helper is switched off"
UNKNOWN_WORDS = "Pressless cannot tell whether your site changed."
UNCHANGED_WORDS = "Your site has not changed."
_OWN = "the door file's own"     # `post` sends the door's token


def _github(**kwargs) -> _Transport:
    return _Transport(reads=_reads(_listing([])), writes=_writes(), **kwargs)


def _wrote(transport: _Transport) -> list[str]:
    return [url for method, url, *_ in transport.requests if method != "GET"]


class _Pressless:
    """A served Face with the helper on it, and the two ways in: the door,
    as the bridge uses it, and the screens, as a browser does."""

    def __init__(self, served: face.Face, own: Path, folder: Path) -> None:
        self.served, self.own, self.folder = served, own, folder
        self.port = served.port
        self.browser = Browser(served, timeout=30)

    def token(self) -> str:
        return json.loads((self.own / DOOR_FILE).read_text(encoding="utf-8"))["token"]

    def post(self, body: bytes, *, path: str = "/assistant", bearer: str | None = _OWN,
             origin: str | None = None, host: str | None = None,
             cookie: bool = False, authorization: str | None = None) -> tuple[int, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", host or f"127.0.0.1:{self.port}")
            if authorization is not None:
                connection.putheader("Authorization", authorization)
            elif bearer is not None:
                connection.putheader("Authorization",
                                     f"Bearer {self.token() if bearer is _OWN else bearer}")
            if origin is not None:
                connection.putheader("Origin", origin)
            if cookie:
                connection.putheader("Cookie", self.browser.cookie)
            connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            connection.close()

    def call(self, tool: str, arguments: dict | None = None, **how: object) -> dict:
        status, text = self.post(json.dumps({"tool": tool, "arguments": arguments or {},
                                             "version": pressless_version()}).encode(), **how)
        assert status == 200, text
        return json.loads(text)

    def ok(self, tool: str, arguments: dict | None = None) -> dict:
        reply = self.call(tool, arguments)
        assert reply["ok"] is True, reply
        return reply["result"]

    def waiting(self) -> dict:
        status, _, text = self.browser.request("GET", "/assistant/waiting")
        assert status == 200, text
        return json.loads(text)

    def answer(self, request: str, yes: bool) -> dict:
        status, _, text = self.browser.request(
            "POST", "/assistant/answer", {"request": request, "yes": "1" if yes else "0"})
        assert status == 200, text
        return json.loads(text)

    def log(self) -> str:
        path = self.own / LOG_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""


def pressless_version() -> str:
    import pressless
    return pressless.__version__


def _switch(own: Path, on: bool) -> None:
    (own / SWITCH_FILE).write_text(json.dumps({"on": on}), encoding="utf-8")


@contextlib.contextmanager
def _pressless(tmp_path: Path, transport: _Transport | None = None, *,
               on: bool = True) -> Iterator[_Pressless]:
    own = tmp_path / "own"
    own.mkdir()
    if on:
        _switch(own, True)
    folder = _folder(tmp_path)
    github = transport if transport is not None else _github()
    served = face.serve(own, site=folder)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=github)
        page_editor.register(served, folder, transport=github)
        undo.register(served, folder, transport=github)
        pressing.register(served)
        assistant.register(served, folder, own=own, transport=github)
        yield _Pressless(served, own, folder)
    finally:
        served.stop()


def _tree(folder: Path) -> dict[str, str]:
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.rglob("*")) if path.is_file()}


def _page_with_code(folder: Path) -> None:
    """The page `about`, live: words, then a script, a style and a code
    section, each locked."""
    text = starter.new_page("about", "About", ())
    held = blocks.read("about", text)
    sections = (*held.sections,
                blocks.Section(blocks.SCRIPT, {"code": "console.log(1);"}),
                blocks.Section(blocks.STYLE, {"code": "p { color: red; }"}),
                blocks.Section(blocks.CODE, source="<!-- pressless:code --><b>own</b>"
                                                   "<!-- /pressless:code -->"))
    page = blocks.Page(held.before, sections, ("\n",) * (len(sections) + 1), held.after)
    store.write_html(folder, store.PAGES_FOLDER, "about", blocks.write(page))


# ------------------------------------------------------------------ INV-2 ---


def test_the_door_refuses(tmp_path):
    """INV-2. Breaks when `add_door` routes are answered after the cookie
    check is skipped but before the token check."""
    with _pressless(tmp_path) as pressless:
        body = json.dumps({"tool": "site_overview", "arguments": {},
                           "version": pressless_version()}).encode()
        assert pressless.post(body)[0] == 200           # the door does open
        before = pressless.log()
        refusals = {
            "no token": dict(bearer=None),
            "a wrong token": dict(bearer="x" * 43),
            "an Origin": dict(origin=pressless.served.origin),
            "a foreign Host": dict(host="evil.example:80"),
        }
        for name, how in refusals.items():
            status, _ = pressless.post(body, **how)
            assert status == 403, name
        _switch(pressless.own, False)
        assert pressless.post(body)[0] == 403, "the switch off"
        assert pressless.log() == before


# ------------------------------------------------------------------ INV-3 ---


def test_token_and_cookie_stay_apart(tmp_path):
    """INV-3. Breaks when the door's check is written as "token or cookie"."""
    with _pressless(tmp_path) as pressless:
        token = pressless.token()
        for path in ("/", "/assistant/answer", "/publish"):
            status, _ = pressless.post(b"request=x&yes=1", path=path, bearer=token)
            assert status == 403, path
        body = json.dumps({"tool": "site_overview", "arguments": {},
                           "version": pressless_version()}).encode()
        status, _ = pressless.post(body, bearer=None, cookie=True)
        assert status == 403


# ------------------------------------------------------------------ INV-9 ---


def test_off_by_default(tmp_path):
    """INV-9. Breaks when absent `assistant.json` is read as on."""
    with _pressless(tmp_path, on=False) as pressless:
        assert not (pressless.own / DOOR_FILE).exists()
        body = json.dumps({"tool": "site_overview", "arguments": {},
                           "version": pressless_version()}).encode()
        status, _ = pressless.post(body, bearer="A" * 43)
        assert status == 403
        # Switched on from the screen, the door opens and its file appears.
        status, _, _ = pressless.browser.request("POST", "/assistant/setup", {"on": "1"})
        assert status == 303
        assert pressless.ok("site_overview")["journal"] is True
        pressless.browser.request("POST", "/assistant/setup", {"on": "0"})
        assert not (pressless.own / DOOR_FILE).exists()


def test_the_door_file_goes_with_the_face(tmp_path):
    """§ 4.2: written when the Face starts with the switch on, removed when it
    stops, with a new token each time."""
    with _pressless(tmp_path) as pressless:
        door = json.loads((pressless.own / DOOR_FILE).read_text(encoding="utf-8"))
        assert door["port"] == pressless.port and door["version"] == pressless_version()
        own = pressless.own
    assert not (own / DOOR_FILE).exists()


def _door_file_unwritable(monkeypatch) -> None:
    write_whole = assistant.safe_write.write_whole

    def refusing(target, text, *, prefix, **kwargs):
        if Path(target).name == DOOR_FILE:
            raise OSError("no room")
        return write_whole(target, text, prefix=prefix, **kwargs)

    monkeypatch.setattr(assistant.safe_write, "write_whole", refusing)


def test_a_door_file_that_cannot_be_written_leaves_pressless_serving(tmp_path, monkeypatch):
    """§ 4.2, § 6: switched on, with the door file unwritable, the Face still
    serves, the log notes it and the setup screen says so. Breaks when the
    failure stops the Face starting."""
    _door_file_unwritable(monkeypatch)
    with _pressless(tmp_path) as pressless:
        assert not (pressless.own / DOOR_FILE).exists()
        page = pressless.browser.request("GET", "/assistant/setup")[2]
        assert "could not write the file an AI app finds it by" in page
        assert "assistant: the door did not open, OSError" in pressless.log()


def test_a_switch_whose_door_cannot_open_stays_off(tmp_path, monkeypatch):
    """§ 4.2: turned on from the screen with the door file unwritable, the
    switch is not saved on, so the next launch does not try again. Breaks
    when the switch is saved before the door opens."""
    with _pressless(tmp_path, on=False) as pressless:
        _door_file_unwritable(monkeypatch)
        status, _, _ = pressless.browser.request("POST", "/assistant/setup", {"on": "1"})
        assert status == 303
        assert not assistant.is_on(pressless.own)
        page = pressless.browser.request("GET", "/assistant/setup")[2]
        assert "could not write the file an AI app finds it by" in page
        monkeypatch.undo()
        pressless.browser.request("POST", "/assistant/setup", {"on": "1"})
        assert assistant.is_on(pressless.own) and (pressless.own / DOOR_FILE).exists()
        page = pressless.browser.request("GET", "/assistant/setup")[2]
        assert "could not write the file" not in page


def test_the_door_file_is_made_private_before_the_token(tmp_path, monkeypatch):
    """§ 4.2: on Windows, where mkstemp's mode is only the read-only flag, the
    door file is made owner-only while it is still empty. Breaks when the
    token is written under the folder's own permissions."""
    sizes: list[int] = []
    monkeypatch.setattr(assistant, "_windows_owner_only",
                        lambda handle: sizes.append(os.fstat(handle).st_size))
    door = assistant._Door(SimpleNamespace(port=1234), tmp_path, tmp_path, None)
    monkeypatch.setattr(assistant.sys, "platform", "linux")
    door.open()
    assert sizes == []          # mkstemp's 0600 already does it
    monkeypatch.setattr(assistant.sys, "platform", "win32")
    door.open()
    assert sizes == [0]
    assert json.loads((tmp_path / DOOR_FILE).read_text(encoding="utf-8"))["token"] == door.token


@pytest.mark.skipif(sys.platform != "win32", reason="Windows access lists")
def test_the_door_file_is_the_owners_alone_on_windows(tmp_path):
    """§ 4.2 on real Windows: the door file's access list grants its owner
    alone, inherits nothing from the folder, and the owner still reads it.
    Breaks when the access list is not set."""
    import ctypes
    from ctypes import wintypes

    door = assistant._Door(SimpleNamespace(port=1234), tmp_path, tmp_path, None)
    door.open()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    described, dacl, text = ctypes.c_void_p(), ctypes.c_void_p(), wintypes.LPWSTR()
    dacl_only = wintypes.DWORD(0x4)
    assert advapi32.GetNamedSecurityInfoW(str(tmp_path / DOOR_FILE), 1, dacl_only, None, None,
                                          ctypes.byref(dacl), None,
                                          ctypes.byref(described)) == 0
    assert advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
        described, 1, dacl_only, ctypes.byref(text), None)
    shown = text.value
    kernel32.LocalFree(text)
    kernel32.LocalFree(described)
    # "P": inherits nothing. Windows may add "AI", which marks how the list
    # was set and grants no one anything.
    flags, aces = shown[2:shown.index("(")], shown[shown.index("("):]
    assert shown.startswith("D:") and "P" in flags and aces == "(A;;FA;;;OW)", shown
    assert json.loads((tmp_path / DOOR_FILE).read_text(encoding="utf-8"))["token"] == door.token


# ----------------------------------------------------------------- INV-15 ---


def test_the_door_proves_its_token_and_runs_nothing(tmp_path):
    """INV-15, § 4.3: asked to prove, the door answers the token's proof of
    the nonce and runs nothing the body asks, and refuses while switched off.
    Breaks when a proof request is admitted as a call."""
    with _pressless(tmp_path) as pressless:
        body = json.dumps({"tool": "new_entry", "arguments": {"title": "Sneaked in"},
                           "version": pressless_version()}).encode()
        status, text = pressless.post(body, authorization="Prove a-nonce")
        assert status == 200
        assert json.loads(text) == {"proof": assistant_tools.proof(pressless.token(), "a-nonce")}
        assert store.list_slugs(pressless.folder, draft=True) == ()
        assert "assistant:" not in pressless.log()
        # The next call on the door still needs the token.
        assert pressless.post(body, bearer="x" * 43)[0] == 403
        _switch(pressless.own, False)
        assert pressless.post(body, authorization="Prove a-nonce")[0] == 403


# ----------------------------------------------------------------- INV-10 ---


def test_one_at_a_time(tmp_path, monkeypatch):
    """INV-10. Breaks when the door lock is per tool."""
    held = threading.Lock()
    door_lock = Signalled(held)
    monkeypatch.setattr(assistant, "LOCK", door_lock)
    with _pressless(tmp_path) as pressless:
        replies: list[dict] = []
        with held:
            caller = threading.Thread(target=lambda: replies.append(
                pressless.call("list_entries")))
            caller.start()
            assert door_lock.trying.wait(30), "the call never waited for the door lock"
            assert caller.is_alive() and not replies
        caller.join(timeout=30)
        assert replies and replies[0]["ok"] is True

        first = pressless.call("undo_last_publish")
        second = pressless.call("undo_last_publish")
        assert first["ok"] is True and first["result"]["status"] == "waiting"
        assert second["ok"] is False and ONE_WAITING_WORDS in second["said"]


# ----------------------------------------------------------------- INV-11 ---


def test_stale_version_refused(tmp_path):
    """INV-11. Breaks when a tool reads the digest itself instead of taking
    it from the caller."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        entry = store.path_for(folder, "seaside", draft=True).read_bytes()
        reply = pressless.call("save_entry", {"address": "seaside", "version": "0" * 64,
                                              "body": "Overwritten."})
        assert reply["ok"] is False and CHANGED_WORDS in reply["said"]
        assert store.path_for(folder, "seaside", draft=True).read_bytes() == entry

        _page_with_code(folder)
        page = store.html_path_for(folder, store.PAGES_FOLDER, "about").read_bytes()
        read = pressless.ok("read_page", {"name": "about"})
        keep = [{"keep": item["path"]} for item in read["sections"] if len(item["path"]) == 1]
        reply = pressless.call("save_page", {"name": "about", "version": "0" * 64,
                                             "sections": keep})
        assert reply["ok"] is False
        assert store.html_path_for(folder, store.PAGES_FOLDER, "about").read_bytes() == page
        assert not store.html_path_for(folder, store.PAGES_FOLDER, "about",
                                       waiting=True).exists()

        look.save(folder, look.defaults(look.LAYOUTS[0]), "")
        shown = pressless.ok("read_look")
        before = look.digest(folder)
        changed = dict(shown["choices"], width="wide" if shown["choices"]["width"] != "wide"
                       else "narrow")
        reply = pressless.call("save_look", {"version": "0" * 64, "choices": changed})
        assert reply["ok"] is False and look.digest(folder) == before
        # The right version saves.
        assert pressless.ok("save_look", {"version": shown["version"], "choices": changed})
        assert look.read(folder, waiting=True).width == changed["width"]


# ------------------------------------------------------------------ INV-6 ---


def test_locked_sections_hold(tmp_path):
    """INV-6. Breaks when the comparison ignores order, so swapping two
    locked sections passes."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        _page_with_code(folder)
        read = pressless.ok("read_page", {"name": "about"})
        top = [item for item in read["sections"] if len(item["path"]) == 1]
        locked = [item for item in top if item.get("locked")]
        assert [item["kind"] for item in locked] == ["script", "style", "code"]
        assert all("fields" not in item for item in locked)       # no code shown
        keep = [{"keep": item["path"]} for item in top]
        at = {item["kind"]: number for number, item in enumerate(top)}
        script, style = at["script"], at["style"]

        swapped = list(keep)
        swapped[script], swapped[style] = swapped[style], swapped[script]
        breaches = {
            "added": [*keep, {"kind": "script", "fields": {"code": "evil();"}, "parts": []}],
            "added as code": [*keep, {"code": "<script>evil()</script>"}],
            "changed": [item if number != script else
                        {"kind": "script", "fields": {"code": "evil();"}, "parts": []}
                        for number, item in enumerate(keep)],
            "moved": swapped,
            "removed": [item for number, item in enumerate(keep) if number != style],
        }
        for name, sections in breaches.items():
            reply = pressless.call("save_page", {"name": "about", "version": read["version"],
                                                 "sections": sections})
            assert reply["ok"] is False and LOCKED_WORDS in reply["said"], name
            assert not store.html_path_for(folder, store.PAGES_FOLDER, "about",
                                           waiting=True).exists(), name

        words = next(number for number, item in enumerate(top) if item["kind"] == "text")
        fine = [item if number != words else
                {"kind": "text", "fields": {"html": "New words."}, "parts": []}
                for number, item in enumerate(keep)]
        saved = pressless.ok("save_page", {"name": "about", "version": read["version"],
                                           "sections": fine})
        waiting = store.read_html(store.html_path_for(folder, store.PAGES_FOLDER, "about",
                                                      waiting=True))
        assert "New words." in waiting and "console.log(1);" in waiting
        assert saved["version"] == hashlib.sha256(waiting.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ INV-4 ---


def test_asks_change_nothing(tmp_path, monkeypatch):
    """INV-4. Breaks when an ask calls its press function instead of
    recording it."""
    _key(monkeypatch)
    github = _github()
    with _pressless(tmp_path, github) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        store.write(folder, _entry("harbour"), draft=False)
        store.write(folder, _entry("harbour-changes", extra=(("Replaces", "harbour"),)),
                    draft=True)
        _page_with_code(folder)
        (folder / store.FILES_FOLDER).mkdir()
        (folder / store.FILES_FOLDER / "notes.txt").write_text("notes", encoding="utf-8")
        before = _tree(folder)
        copy = _base(folder, "harbour-changes", draft=True)
        asks = [
            ("publish", {"entry": "seaside"}),
            ("publish", {}),
            ("undo_last_publish", {}),
            ("remove_entry", {"address": "seaside",
                              "version": _base(folder, "seaside", draft=True)}),
            ("discard_changes", {"entry": "harbour", "version": copy}),
            ("remove_page", {"name": "about"}),
            ("rename_page", {"name": "about", "to": "story"}),
            ("remove_file", {"name": "notes.txt"}),
        ]
        assert {tool for tool, _ in asks} == {
            tool.name for tool in assistant_tools.TOOLS if tool.kind == assistant_tools.ASK}
        for tool, arguments in asks:
            reply = pressless.ok(tool, arguments)
            assert reply["status"] == "waiting", tool
            assert pressless.waiting()["request"] == reply["request"], tool
            pressless.answer(reply["request"], yes=False)
            assert pressless.ok("request_status", {"request": reply["request"]})[
                "status"] == "refused"
        assert _tree(folder) == before
        assert _wrote(github) == []


# ------------------------------------------------------------------ INV-5 ---


def test_yes_after_a_change_replans(tmp_path, monkeypatch):
    """INV-5. Breaks when the yes path skips the mark comparison, or the mark
    leaves out a file the build reads. A re-plan counts no failed press
    (§ 4.6 step 2)."""
    _key(monkeypatch)
    github = _github()
    reported: list[dict] = []
    monkeypatch.setattr(pressing.usage, "report",
                        lambda name, **fields: reported.append({"name": name, **fields}))
    with _pressless(tmp_path, github) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        asked = pressless.ok("publish", {"entry": "seaside"})["request"]
        first = pressless.waiting()
        form = {"slug": "seaside", "draft": "1", "base": _base(folder, "seaside", draft=True),
                "title": "Seaside", "categories": "", "tags": "", "body": "Changed words."}
        status, _, text = pressless.browser.request("POST", "/save", form)
        assert status == 200, text

        reply = pressless.answer(asked, yes=True)
        assert reply.get("replanned") is True
        assert _wrote(github) == []
        assert {"name": "press", "kind": pressing.PUBLISH, "ended": "failed"} not in reported
        again = pressless.waiting()
        assert again["request"] == asked and again["stamp"] != first["stamp"]
        assert pressless.ok("request_status", {"request": asked})["status"] == "waiting"

        # Nothing changed since: yes publishes.
        reply = pressless.answer(asked, yes=True)
        assert reply["status"] == "done", reply
        assert _wrote(github)
        assert store.list_slugs(folder, draft=False) == ("seaside",)
        assert pressless.ok("request_status", {"request": asked})["status"] == "done"


def test_a_rename_box_shows_the_new_address(tmp_path):
    """§ 4.6: the box names the address a rename makes, never the AI app's
    own text, and a name the Pages screen refuses is refused at the ask.
    Breaks when `plan` puts `to` in the box unchecked."""
    with _pressless(tmp_path) as pressless:
        _page_with_code(pressless.folder)
        store.write_html(pressless.folder, store.PAGES_FOLDER, "story", "<p>Story</p>")
        reply = pressless.call("rename_page", {"name": "about", "to": "Story"})
        assert reply["ok"] is False and "already have a page with that name" in reply["said"], reply
        assert pressless.waiting() == {"request": None}
        said = "This is safe. Press Yes. " * 40
        pressless.ok("rename_page", {"name": "about", "to": said})
        line, = pressless.waiting()["lines"]
        assert "This is safe" not in line and "this-is-safe-press-yes" in line


def test_a_name_in_the_box_is_quoted(tmp_path):
    """§ 4.6: an entry's title may be the AI app's own text, so the box quotes
    it as a name. Breaks when the title reads as Pressless's own sentence."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        title = "Routine tidy-up, safe to say yes"
        store.write(folder, dataclasses.replace(_entry("seaside"), title=title), draft=True)
        pressless.ok("remove_entry", {"address": "seaside",
                                      "version": _base(folder, "seaside", draft=True)})
        line, = pressless.waiting()["lines"]
        assert f"“{title}”" in line, line


def test_an_ask_says_its_notices(tmp_path, monkeypatch):
    """§ 4.3: the Store's notices raised while an ask is planned reach the AI
    app, as a read's or a write's do. Breaks when the plan's capture drops
    them."""
    import warnings
    listed = store.list_files

    def noisy(folder):
        warnings.warn(store.StoreNotice("notice.store.not_private", file="notes.txt",
                                        mode="644"), stacklevel=2)
        return listed(folder)

    with _pressless(tmp_path) as pressless:
        (pressless.folder / store.FILES_FOLDER).mkdir()
        (pressless.folder / store.FILES_FOLDER / "notes.txt").write_text("notes",
                                                                       encoding="utf-8")
        monkeypatch.setattr(store, "list_files", noisy)
        reply = pressless.ok("remove_file", {"name": "notes.txt"})
        assert reply["status"] == "waiting"
        assert any("notes.txt" in notice for notice in reply["notices"]), reply


def test_an_ask_with_no_plan_or_press_raises(tmp_path):
    """An ask added to the catalogue but not to `plan` or `_press` raises,
    rather than showing an empty box or ending as done with nothing run."""
    door = assistant._Door(SimpleNamespace(capture=contextlib.nullcontext), tmp_path,
                           tmp_path, None)
    with pytest.raises(ValueError):
        door.plan("nothing", {})
    made = assistant._Ask("id", "nothing", {}, 0.0, {}, "")
    with pytest.raises(ValueError):
        door._press(made)


def test_a_request_is_answered_once(tmp_path, monkeypatch):
    """§ 4.6: the first Yes takes the request. A second tab's answer while
    the bin runs finds nothing to answer, and a running request neither
    expires nor shows in a box. Breaks when `answer` leaves the request
    waiting until the press, or expiry reads a running request."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        asked = pressless.ok("remove_entry", {
            "address": "seaside", "version": _base(folder, "seaside", draft=True)})["request"]
        started, go_on = threading.Event(), threading.Event()
        throw = editor.throw

        def slow_throw(*args, **kwargs):
            started.set()
            assert go_on.wait(30)
            return throw(*args, **kwargs)

        monkeypatch.setattr(editor, "throw", slow_throw)
        replies: dict[str, dict] = {}

        def answer(which: str) -> threading.Thread:
            thread = threading.Thread(
                target=lambda: replies.update({which: pressless.answer(asked, yes=True)}))
            thread.start()
            return thread

        first = answer("first")
        try:
            assert started.wait(30)
            second = answer("second")
            second.join(timeout=5)
            assert not second.is_alive() and replies["second"] == {"answered": False}
            monkeypatch.setattr(assistant, "EXPIRES_SECONDS", 0)
            assert pressless.ok("request_status", {"request": asked})["status"] == "running"
            assert pressless.waiting() == {"request": None}
        finally:
            go_on.set()
            first.join(timeout=30)
        assert replies["first"]["status"] == "done", replies
        assert pressless.ok("request_status", {"request": asked})["status"] == "done"


def test_the_overview_says_a_request_is_running(tmp_path):
    """§ 4.5: site_overview names the open request with its status, so a
    request taken by a Yes does not read as waiting for the writer. Breaks
    when the status is left out."""
    with _pressless(tmp_path) as pressless:
        asked = pressless.ok("undo_last_publish")["request"]
        door = pressless.served._doors["/assistant"][0].__self__
        door.open_ask.status = "running"
        assert pressless.ok("site_overview")["waiting"] == {
            "request": asked, "tool": "undo_last_publish", "status": "running"}


def test_a_yes_that_raises_late_still_ends_the_request(tmp_path, monkeypatch):
    """§ 4.6 step 3: where reporting a failure itself raises, the request
    still ends as failed, and the next ask is not refused as one waiting.
    Breaks when the request is closed only after the failure is reported."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        asked = pressless.ok("remove_entry", {
            "address": "seaside", "version": _base(folder, "seaside", draft=True)})["request"]

        def refuse(*args, **kwargs):
            raise OSError("the bin is gone")

        def worse(*args, **kwargs):
            raise RuntimeError("reporting the failure failed")

        monkeypatch.setattr(editor, "throw", refuse)
        monkeypatch.setattr(publishing, "press_failure", worse)
        pressless.browser.request("POST", "/assistant/answer", {"request": asked, "yes": "1"})
        assert pressless.ok("request_status", {"request": asked})["status"] == "failed"
        assert pressless.ok("undo_last_publish")["status"] == "waiting"


def test_a_box_never_pairs_a_stamp_with_another_plan(tmp_path, monkeypatch):
    """§ 4.6: the box keys on the stamp, so the stamp and the plan it is sent
    with are read together. Breaks when the plan is read after a re-plan
    could have replaced it."""
    with _pressless(tmp_path) as pressless:
        pressless.ok("undo_last_publish")
        door = pressless.served._doors["/assistant"][0].__self__
        state = pressing.state

        def replanned_meanwhile() -> dict:
            door.open_ask.plan = {**door.open_ask.plan, "lines": ["a newer plan"]}
            door.open_ask.mark = "f" * 64
            return state()

        stamp = door.open_ask.mark[:16]
        monkeypatch.setattr(assistant.pressing, "state", replanned_meanwhile)
        shown = pressless.waiting()
        assert (shown["stamp"] == stamp) == (shown["lines"] != ["a newer plan"]), shown


def test_a_busy_yes_leaves_the_request_waiting(tmp_path):
    """§ 6: a Yes while another press runs is answered busy, and the request
    stays waiting for the next Yes. Breaks when the taken request is not
    handed back."""
    with _pressless(tmp_path) as pressless:
        asked = pressless.ok("undo_last_publish")["request"]
        assert pressing.start(pressing.PUBLISH)
        try:
            assert pressless.answer(asked, yes=True)["busy"] is True
        finally:
            pressing.end(pressing.Outcome(""))
        assert pressless.ok("request_status", {"request": asked})["status"] == "waiting"
        assert pressless.waiting()["request"] == asked


def test_a_yes_that_can_no_longer_run_says_so(tmp_path):
    """§ 4.6: where the re-plan after Yes finds the ask cannot run, the answer
    says it failed and the log says why. Breaks when the failure is kept
    from the writer as a re-plan."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        asked = pressless.ok("remove_entry", {
            "address": "seaside", "version": _base(folder, "seaside", draft=True)})["request"]
        store.path_for(folder, "seaside", draft=True).unlink()     # binned elsewhere
        reply = pressless.answer(asked, yes=True)
        assert reply["answered"] is True and reply["status"] == "failed", reply
        assert "assistant: remove_entry failed" in pressless.log()
        assert "EntryNotFound" in pressless.log()
        assert pressless.ok("request_status", {"request": asked})["status"] == "failed"


@pytest.mark.parametrize("failure, words, not_words", [
    (RuntimeError("the line went down"), UNCHANGED_WORDS, UNKNOWN_WORDS),
    (publisher.OutcomeUnknown("the upload stopped"), UNKNOWN_WORDS, UNCHANGED_WORDS),
])
def test_a_failed_publish_reads_as_on_the_writers_screen(tmp_path, monkeypatch, failure,
                                                         words, not_words):
    """PRESS-0424, PRESS-0013 § 4.2: the AI app and the press row say what the
    writer's own publish says. An unforeseen failure left the site unchanged,
    since the Publisher raises OutcomeUnknown itself where an upload may be
    unknown. Breaks when the door words an unforeseen failure as unknown, or
    an unknown upload as unchanged."""
    _key(monkeypatch)
    with _pressless(tmp_path) as pressless:
        store.write(pressless.folder, _entry("seaside"), draft=False)
        asked = pressless.ok("publish")["request"]

        def broken(*args, **kwargs):
            raise failure

        monkeypatch.setattr(publishing, "press_site", broken)
        assert pressless.answer(asked, yes=True)["status"] == "failed"
        said = pressless.ok("request_status", {"request": asked})["said"]
        row = pressing.state()["failure"]
        assert words in said and not_words not in said, said
        assert words in row and not_words not in row, row


_PUBLISHED = publishing.Published(None, True)


@pytest.mark.parametrize("target, ask, patched, press, key, outcome", [
    ("site", {}, "press_site", lambda: (_PUBLISHED, None), "notice.publishing.kept_copy",
     "done"),
    ("entry", {"entry": "seaside"}, "press_entry", lambda: (_PUBLISHED, None),
     "notice.publishing.kept_copy", "done"),
    ("page", {"page": "about"}, "press_page", lambda: (_PUBLISHED, None),
     "notice.page_editor.kept_copy", "done"),
    ("site", {}, "press_site", lambda: (None, publisher.OutcomeUnknown("stopped")),
     "notice.publishing.kept_copy_unknown", "failed"),
    ("page", {"page": "about"}, "press_page",
     lambda: (None, publisher.OutcomeUnknown("stopped")),
     "notice.page_editor.kept_copy_unknown", "failed"),
])
def test_a_publish_that_kept_a_copy_says_so_to_the_ai_app(tmp_path, monkeypatch, target, ask,
                                                          patched, press, key, outcome):
    """PRESS-0488, PRESS-0013 § 4.3 step 5: the AI app is told, in the writer's
    words, that a publish left (or may have left) a working copy, as the Publish
    button tells the writer, for a site, an entry and a page, and after an
    unknown outcome. Breaks when any of those answers drops it."""
    _key(monkeypatch)
    returns, raises = press()
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=(target == "entry"))
        if target == "page":
            _page_with_code(folder)
            live = store.html_path_for(folder, store.PAGES_FOLDER, "about")
            waiting = store.html_path_for(folder, store.PAGES_FOLDER, "about", waiting=True)
            waiting.parent.mkdir(parents=True, exist_ok=True)
            waiting.write_bytes(live.read_bytes())
        asked = pressless.ok("publish", ask)["request"]
        stand_in = _kept_press_for(key, raises, returns, patched)
        monkeypatch.setattr(publishing if patched != "press_page" else page_editor,
                            patched, stand_in)
        assert pressless.answer(asked, yes=True)["status"] == outcome
        said = pressless.ok("request_status", {"request": asked})["said"]
        assert words.say(key) in said, said


def _kept_press_for(key, raises, returns, patched):
    def press(*args, notices, **kwargs):
        # The real publish adds the unknown-outcome notice before it raises, and
        # press_page its kept-copy one; an entry's or site's kept copy is the
        # caller's to say, from `copy_kept` (PRESS-0488).
        if raises is not None or patched == "press_page":
            notices.append(face.Notice(words.say(key), face.Site.UPDATED))
        if raises is not None:
            raise raises
        return (None, returns) if patched == "press_entry" else returns
    return press


def test_a_publish_that_kept_no_copy_says_nothing_of_one(tmp_path, monkeypatch):
    """PRESS-0488: a clean publish's answer is only the status."""
    _key(monkeypatch)
    with _pressless(tmp_path) as pressless:
        store.write(pressless.folder, _entry("seaside"), draft=False)
        asked = pressless.ok("publish")["request"]
        monkeypatch.setattr(publishing, "press_site",
                            lambda *args, **kwargs: publishing.Published(None, False))
        assert pressless.answer(asked, yes=True)["status"] == "done"
        said = pressless.ok("request_status", {"request": asked})["said"]
        assert said == words.say("assistant.status.done")


def test_only_a_failure_no_press_row_shows_goes_to_the_box(tmp_path, monkeypatch):
    """PRESS-0403, § 4.6: a bin that fails after Yes runs no press, so its
    answer carries the failure for the box's script to show. A publish's
    failure is on the press row, so its answer carries none, or the writer
    would see it twice. Breaks when the answer drops a bin's failure, or
    hands on a press's."""
    _key(monkeypatch)
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        asked = pressless.ok("remove_entry", {
            "address": "seaside", "version": _base(folder, "seaside", draft=True)})["request"]
        store.path_for(folder, "seaside", draft=True).unlink()     # binned elsewhere
        reply = pressless.answer(asked, yes=True)
        assert reply["status"] == "failed" and "EntryNotFound" in reply["failure"], reply
        store.write(folder, _entry("harbour"), draft=False)
        asked = pressless.ok("publish")["request"]

        def broken(*args, **kwargs):
            raise RuntimeError("the line went down")

        monkeypatch.setattr(publishing, "press_site", broken)
        reply = pressless.answer(asked, yes=True)
        assert reply["status"] == "failed" and reply["failure"] is None, reply
        assert pressing.state()["failure"], "the press row lost the publish's failure"


@pytest.mark.parametrize("refusal, address", [
    (publishing.WouldReplaceASite("held"), publishing.REPLACE_ADDRESS),
    (publishing.TakeoverOwed("owed"), publishing.TAKEOVER_ADDRESS),
])
def test_a_refused_ai_publish_offers_the_way_on(tmp_path, monkeypatch, refusal, address):
    """PRESS-0417: a publish an AI app asked for, refused because it would
    replace a site or a takeover is owed, offers on its press row the same
    link as the writer's own publish. Breaks when the door renders the
    failure without publishing.way_on."""
    _key(monkeypatch)
    with _pressless(tmp_path) as pressless:
        store.write(pressless.folder, _entry("harbour"), draft=False)
        asked = pressless.ok("publish")["request"]

        def refused(*args, **kwargs):
            raise refusal

        monkeypatch.setattr(publishing, "press_site", refused)
        assert pressless.answer(asked, yes=True)["status"] == "failed"
        assert f'href="{address}"' in pressing.state()["failure"]


# The box's script runs in a browser; Node runs it, with pressing.SCRIPT before
# it as every page has, against a page with no failure box of its own, a fetch
# answering a waiting bin and then `answer`, and a writer who says yes.
_NODE = shutil.which("node")
_BOX_HARNESS = """const window = globalThis;
const made = [];
const element = (tag) => {
  const node = {tag, children: [], dataset: {}, classes: [], open: false,
    classList: {add: (...names) => node.classes.push(...names)},
    append: (...nodes) => node.children.push(...nodes),
    addEventListener: () => {}, showModal: () => { node.open = true; },
    close: () => { node.open = false; }, remove: () => {}};
  made.push(node);
  return node;
};
const document = {getElementById: () => null, querySelector: () => null,
  querySelectorAll: () => [], createElement: element,
  body: {append: (node) => { node.inPage = true; }}};
let reloaded = false;
window.location = {pathname: "/journal", reload: () => { reloaded = true; }};
window.presslessPlan = async () => true;
const replies = {
  "/assistant/waiting": {request: "r1", stamp: "s1", publishing: false, pages: [], lines: []},
  "/assistant/answer": %s,
};
const fetch = async (url) => ({json: async () => replies[url]});
let tick = null;
const setInterval = (run) => { tick = run; };
const say = (key) => "<" + key + ">";
%s
%s
(async () => {
  await tick();
  const boxes = made.filter((node) => node.tag === "dialog" && node.inPage);
  const shown = boxes.map((box) => box.children.map((child) => child.innerHTML || ""));
  process.stdout.write(JSON.stringify({reloaded, open: boxes.map((box) => box.open), shown}));
})();
"""


def _box_after_yes(tmp_path: Path, answer: dict) -> dict:
    harness = tmp_path / "box.js"
    harness.write_text(_BOX_HARNESS % (json.dumps(answer), pressing.SCRIPT,
                                       assistant._BOX_SCRIPT), encoding="utf-8")
    run = subprocess.run([_NODE, str(harness)], capture_output=True,  # noqa: S603
                         check=False, timeout=30)
    assert run.returncode == 0, run.stderr.decode()
    return json.loads(run.stdout)


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_a_failure_after_yes_is_shown_on_any_page(tmp_path):
    """PRESS-0403, § 4.6: a bin, discard or file removal that fails after Yes
    shows its failure in a box over whatever page the writer is on, and the
    list is not reloaded over it. A Yes that ran is reloaded as before.
    Breaks when the box's script ignores the answer's failure."""
    failure = '<section class="failure"><p class="what">Not binned.</p></section>'
    seen = _box_after_yes(tmp_path, {"answered": True, "status": "failed", "failure": failure})
    assert seen["reloaded"] is False and seen["open"] == [True], seen
    assert failure in seen["shown"][0], seen
    seen = _box_after_yes(tmp_path, {"answered": True, "status": "done", "failure": None})
    assert seen == {"reloaded": True, "open": [], "shown": []}


# ----------------------------------------------------------------- INV-12 ---


def test_box_is_escaped(tmp_path, monkeypatch):
    """INV-12. Breaks when the plan's titles are inserted as HTML."""
    _key(monkeypatch)
    title = "<img src=x onerror=alert(1)>"
    with _pressless(tmp_path) as pressless:
        store.write(pressless.folder, _entry("seaside", extra=()), draft=True)
        entry = store.read(store.path_for(pressless.folder, "seaside", draft=True))
        store.write(pressless.folder, store.Entry(
            slug="seaside", title=title, date=entry.date, categories=(), tags=(),
            body="Words.", extra=()), draft=True)
        pressless.ok("publish", {"entry": "seaside"})
        assert title in pressless.waiting()["pages"]
    plan = pressing.SCRIPT[pressing.SCRIPT.index("window.presslessPlan ="):]
    for script in (plan, assistant._BOX_SCRIPT):
        assert "innerHTML" not in script and "insertAdjacentHTML" not in script
        assert "outerHTML" not in script and "document.write" not in script
    assert 'make("li", title)' in plan and 'make("p", line)' in plan


# ------------------------------------------------------------------ INV-1 ---


def test_no_tool_returns_a_key(tmp_path, monkeypatch):
    """INV-1. Breaks when a raised failure's own words quote the key, or a
    tool returns a settings object or transport that holds one."""
    _key(monkeypatch)
    quoting = json.dumps({"message": f"Bad credentials {KEY}"}).encode()
    github = _Transport(responses=[(401, {}, quoting)])
    with _pressless(tmp_path, github) as pressless:
        folder = pressless.folder
        store.write(folder, _entry("seaside"), draft=True)
        store.write(folder, _entry("harbour"), draft=False)
        _page_with_code(folder)
        replies = []
        for tool in assistant_tools.TOOLS:
            arguments = _arguments_for(tool.name, folder)
            replies.append(pressless.call(tool.name, arguments))
            waiting = pressless.waiting()
            if waiting["request"]:
                replies.append(pressless.answer(waiting["request"], yes=True))
                replies.append(pressless.call("request_status",
                                              {"request": waiting["request"]}))
        assert any(reply.get("status") == "failed" for reply in replies)
        text = json.dumps(replies)
        assert KEY not in text
        assert KEY not in pressless.log()


def _arguments_for(tool: str, folder: Path) -> dict:
    """Arguments each tool runs with, made when it is called: an earlier tool
    may have moved what a later one names."""
    def version(slug: str, *, draft: bool) -> str:
        path = store.path_for(folder, slug, draft=draft)
        return _base(folder, slug, draft=draft) if path.exists() else "0"

    made = {
        "read_entry": lambda: {"address": "seaside"},
        "read_page": lambda: {"name": "about"},
        "read_insights": lambda: {"days": 28},
        "request_status": lambda: {"request": "nothing"},
        "new_entry": lambda: {"title": "Another"},
        "save_entry": lambda: {"address": "seaside",
                               "version": version("seaside", draft=True), "body": "More."},
        "change_entry_address": lambda: {"address": "harbour",
                                         "version": version("harbour", draft=False),
                                         "to": "port"},
        "new_page": lambda: {"name": "Contact"},
        "save_page": lambda: {"name": "about", "version": "0", "sections": []},
        "add_photograph": lambda: {"filename": "a.png", "data": "not base64!"},
        "add_file": lambda: {"filename": "notes.txt",
                             "data": base64.b64encode(b"notes").decode()},
        "save_look": lambda: {"version": "0", "choices": {}},
        "remove_entry": lambda: {"address": "seaside",
                                 "version": version("seaside", draft=True)},
        "discard_changes": lambda: {"entry": "seaside", "version": "0"},
        "remove_page": lambda: {"name": "about"},
        "rename_page": lambda: {"name": "about", "to": "story"},
        "remove_file": lambda: {"name": "notes.txt"},
    }
    return made[tool]() if tool in made else {}


# -------------------------------------------------------- the tools work ---


def test_the_reads_and_writes_work(tmp_path):
    """§ 4.5: each read answers, and each write lands where its screen's
    would."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        overview = pressless.ok("site_overview")
        assert overview["entries"] == 0 and overview["waiting"] is None
        assert pressless.ok("writing_guide")["marks"]

        made = pressless.ok("new_entry", {"title": "First words"})
        assert made["address"] == "first-words"
        saved = pressless.ok("save_entry", {"address": "first-words", "version": made["version"],
                                            "body": "Hello.", "tags": ["sea", "Sky Blue"]})
        read = pressless.ok("read_entry", {"address": "first-words"})
        assert read["body"] == "Hello." and read["tags"] == ["sea", "sky-blue"]
        assert read["version"] == saved["version"] and read["draft"] is True
        moved = pressless.ok("change_entry_address", {"address": "first-words",
                                                      "version": read["version"], "to": "hello"})
        assert moved["address"] == "hello"
        assert [entry["address"] for entry in pressless.ok("list_entries")["entries"]] == ["hello"]

        # A published entry's change waits as its working copy, as on screen.
        store.write(folder, _entry("harbour"), draft=False)
        shown = pressless.ok("read_entry", {"address": "harbour"})
        assert shown["draft"] is False
        pressless.ok("save_entry", {"address": "harbour", "version": shown["version"],
                                    "title": "Harbour lights"})
        assert store.read(store.path_for(folder, "harbour", draft=False)).title == "Harbour"
        listed = {entry["address"]: entry for entry in pressless.ok("list_entries")["entries"]}
        assert listed["harbour"]["has_changes"] is True
        assert pressless.ok("read_entry", {"address": "harbour"})["title"] == "Harbour lights"

        assert pressless.ok("new_page", {"name": "Contact us"})["name"] == "contact-us"
        pages = pressless.ok("list_pages")
        assert {"name": "contact-us", "changed": True, "live": False} in pages["pages"]
        assert {part["name"] for part in pages["parts"]} == {"header", "navigation", "footer"}
        navigation = pressless.ok("read_page", {"name": "navigation"})
        assert navigation["links"][0]["words"] == "Journal"

        added = pressless.ok("add_file", {"filename": "notes.txt",
                                          "data": base64.b64encode(b"notes").decode()})
        assert added["name"] == "notes.txt"
        assert pressless.ok("list_files")["files"] == [{"name": "notes.txt", "used_by": []}]
        bad = pressless.call("add_photograph", {"filename": "a.png", "data": "not base64!"})
        assert bad["ok"] is False

        unknown = pressless.call("read_entry", {"address": "nowhere"})
        assert unknown["ok"] is False
        missing = pressless.call("read_entry", {})
        assert missing["ok"] is False and "read_entry needs address" in missing["said"]


def test_list_files_names_the_kind_of_each_user(tmp_path):
    """PRESS-0420: a page named footer and the footer part are told apart,
    as on the Files screen, and the look is named as the look. Breaks when
    used_by answers bare names."""
    with _pressless(tmp_path) as pressless:
        folder = pressless.folder
        target = store.file_path_for(folder, "notes.pdf")
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b"%PDF-1.4\n")
        store.write_html(folder, store.PAGES_FOLDER, "footer",
                         '<p><a href="../files/notes.pdf">Notes</a></p>')
        store.write_html(folder, store.FURNITURE_FOLDER, "footer",
                         '<footer><a href="{{UP}}files/notes.pdf">Notes</a></footer>')
        store.write_style_code(folder, "body{background:url(../files/notes.pdf)}")
        listed = pressless.ok("list_files")["files"]
    assert listed == [{"name": "notes.pdf", "used_by": [
        {"kind": "part", "name": "footer"}, {"kind": "page", "name": "footer"},
        {"kind": "look", "name": "look"}]}]


def test_an_old_bridge_is_told_to_restart(tmp_path):
    """§ 4.3: a version other than the running program's is refused."""
    with _pressless(tmp_path) as pressless:
        status, text = pressless.post(json.dumps({"tool": "site_overview", "arguments": {},
                                                  "version": "0.0.1"}).encode())
        assert status == 200
        assert "Restart the AI app" in json.loads(text)["said"]


def test_a_request_expires(tmp_path, monkeypatch):
    """§ 4.6: a request waiting 30 minutes expires, and changes nothing."""
    with _pressless(tmp_path) as pressless:
        asked = pressless.ok("undo_last_publish")["request"]
        monkeypatch.setattr(assistant, "EXPIRES_SECONDS", 0)
        assert pressless.waiting()["request"] is None
        assert pressless.ok("request_status", {"request": asked})["status"] == "expired"
        assert pressless.answer(asked, yes=True) == {"answered": False}


def test_the_bridge_reaches_the_door(tmp_path, monkeypatch):
    """§ 4.4 end to end: the bridge reads the door file and posts the call."""
    with _pressless(tmp_path) as pressless:
        monkeypatch.setenv("PRESSLESS_FOLDER", str(pressless.own))
        lines = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "list_entries", "arguments": {}}}]
        out = io.StringIO()
        bridge.run(io.StringIO("".join(json.dumps(line) + "\n" for line in lines)), out)
        reply = json.loads(out.getvalue())
        assert reply["result"]["isError"] is False
        assert reply["result"]["structuredContent"] == {"entries": []}
    # Pressless closed: the door file is gone, and the call says to open it.
    out = io.StringIO()
    bridge.run(io.StringIO(json.dumps(lines[0]) + "\n"), out)
    reply = json.loads(out.getvalue())
    assert reply["result"]["isError"] is True
    assert OPEN_WORDS in reply["result"]["content"][0]["text"]


def test_the_catalogue_matches_the_parts(tmp_path):
    """The catalogue's own copies: Insights' spans, and every tool has its
    work in the door."""
    assert assistant_tools.INSIGHTS_DAYS == tuple(days for days, *_ in dashboard.WINDOWS)
    for tool in assistant_tools.TOOLS:
        assert tool.name == "request_status" or hasattr(assistant._Door, "_" + tool.name)
    assert bridge.DOOR_NAME == DOOR_FILE == assistant.DOOR_NAME
    assert bridge.DOOR_PATH == "/assistant" == assistant.ADDRESS
    for route in ("/assistant/waiting", "/assistant/answer"):
        assert f'"{route}"' in assistant._BOX_SCRIPT
    assert (assistant.WAITING_ROUTE, assistant.ANSWER_ROUTE) == (
        "/assistant/waiting", "/assistant/answer")
    assert assistant.SWITCH_NAME == SWITCH_FILE
    # save_look posts each of the look's one-word choices.
    assert assistant._PLAIN_CHOICES == ("layout", "body_font", "heading_font", "text_size",
                                        "width")
    # A schema type the call check cannot read would fail every call to it.
    for tool in assistant_tools.TOOLS:
        for schema in tool.arguments.values():
            assert schema["type"] in assistant_tools._TYPES, (tool.name, schema)
            assert schema["type"] != "array" or "type" in schema.get("items", {})


@pytest.mark.parametrize("name, arguments, why", [
    ("nothing", {}, "there is no tool 'nothing'"),
    ("read_entry", [], "the arguments are not an object"),
    ("read_entry", {}, "read_entry needs address"),
    ("read_entry", {"address": 1}, "address must be string"),
    ("read_entry", {"address": "a", "more": 1}, "read_entry takes no more"),
    ("read_insights", {"days": 30}, "days must be one of [7, 28, 365]"),
    ("read_insights", {"days": True}, "days must be a whole number"),
    ("save_entry", {"address": "a", "version": "b", "tags": [1]},
     "each item of tags must be string"),
    ("save_page", {"name": "navigation", "version": "b", "links": ["/"]},
     "each item of links must be object"),
])
def test_the_catalogue_refuses_a_bad_call(name, arguments, why):
    """§ 4.3: a call the catalogue refuses is said in the words table's words.
    Breaks when a reason is English the table does not hold, or an array's
    items are checked only where they are text."""
    key, slots = assistant_tools.problem(name, arguments)
    assert words.say(key, **slots) == why


def test_the_setup_screen_and_the_box(tmp_path):
    """§ 4.2 and § 4.6: the screen shows the switch and what an AI app starts,
    and every page carries the box's script only while the switch is on."""
    with _pressless(tmp_path, on=False) as pressless:
        status, _, page = pressless.browser.request("GET", "/assistant/setup")
        assert status == 200
        assert "Off: no AI app can connect." in page and "--assistant" in page
        assert "&quot;mcpServers&quot;" in page     # escaped inside <pre>
        assert "/assistant/waiting" not in pressless.browser.request("GET", "/")[2]
        pressless.browser.request("POST", "/assistant/setup", {"on": "1"})
        status, _, page = pressless.browser.request("GET", "/assistant/setup")
        assert "On: an AI app can connect while Pressless is open." in page
        assert "/assistant/waiting" in pressless.browser.request("GET", "/")[2]
        assert pressless.waiting() == {"request": None}


def test_the_screen_names_the_program_on_windows(monkeypatch, tmp_path):
    """§ 4.2, found by § 7 on the Windows box: an AI app starts a program, and
    on Windows the packaged artefact is a folder, so the screen names the
    Pressless.exe inside it. Breaks when the folder is named."""
    program = tmp_path / "Pressless" / "Pressless.exe"
    monkeypatch.setattr(assistant.sys, "platform", "win32")
    monkeypatch.setattr(assistant.sys, "frozen", True, raising=False)
    monkeypatch.setattr(assistant.sys, "executable", str(program))
    assert assistant._program(tmp_path) == (str(program), ["--assistant"])


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_the_command_reads_back_as_one_folder(monkeypatch, tmp_path, platform):
    """§ 4.2, § 4.4: a source run's folder may hold a space, and the line the
    screen shows still gives the AI app that one folder. Breaks when only the
    program is quoted."""
    import shlex
    program, arguments = "/a python/bin/python3", ["-m", "pressless", "--assistant",
                                                     "/home/me/My Pressless"]
    monkeypatch.setattr(assistant, "_program", lambda own: (program, arguments))
    monkeypatch.setattr(assistant.sys, "platform", platform)
    door = assistant._Door(SimpleNamespace(port=1234), tmp_path, tmp_path, None)
    page = door._connecting(SimpleNamespace(query={}))
    shown = html.unescape(page.split('<pre id="assistant-program">')[1].split("</pre>")[0])
    if platform == "win32":
        assert shown == '"/a python/bin/python3" -m pressless --assistant "/home/me/My Pressless"'
    else:
        assert shlex.split(shown) == [program, *arguments]


def test_a_source_run_names_its_folder(monkeypatch, tmp_path, capsys):
    """PRESS-0404, § 4.4: a source run has no artefact to find its folder
    beside, so what an AI app starts names the folder this Face uses, and
    that bridge finds the door there with no PRESSLESS_FOLDER set. Breaks
    when a source run's bridge looks only where PRESSLESS_FOLDER points."""
    from pressless import __main__ as main_module
    monkeypatch.setattr(assistant.sys, "frozen", False, raising=False)
    with _pressless(tmp_path) as pressless:
        program, arguments = assistant._program(pressless.own)
        assert program == sys.executable
        assert arguments == ["-m", "pressless", "--assistant", str(pressless.own.absolute())]
        monkeypatch.delenv("PRESSLESS_FOLDER", raising=False)
        line = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "list_entries", "arguments": {}}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(line) + "\n"))
        assert main_module.main(arguments[2:]) == 0
    reply = json.loads(capsys.readouterr().out)
    assert reply["result"]["structuredContent"] == {"entries": []}, reply


def test_a_packaged_run_that_cannot_find_itself_offers_no_program(monkeypatch, tmp_path):
    """PRESS-0418: a frozen Linux program whose $APPIMAGE names no file
    cannot be started as `-m pressless`, and a packaged bridge refuses a
    folder, so the screen says why it names no program and Connect writes
    nothing. Breaks when a frozen run is offered the source run's line."""
    config = tmp_path / "claude" / "claude_desktop_config.json"
    monkeypatch.setattr(assistant, "claude_desktop_config", lambda: config)
    def lost() -> Path:
        raise assistant.paths.NotPackaged("lost")

    with _pressless(tmp_path) as pressless:
        # Not sys.platform: the Face's own thread reads it while this serves.
        monkeypatch.setattr(assistant.paths, "artefact_path", lost)
        monkeypatch.setattr(assistant.sys, "frozen", True, raising=False)
        page = pressless.browser.request("GET", "/assistant/setup")[2]
        status, headers, _ = pressless.browser.request("POST", "/assistant/connect")
    assert "-m pressless" not in page and "--assistant" not in page
    assert "Pressless cannot tell where its program is" in page
    assert (status, headers["Location"]) == (303, "/assistant/setup")
    assert not config.exists()


def test_the_screen_gives_each_app_its_own_line(tmp_path):
    """§ 4.2: Claude Code's line adds Pressless for every folder and has its
    own Copy button; only the apps checked by hand (§ 7) are named."""
    with _pressless(tmp_path) as pressless:
        page = pressless.browser.request("GET", "/assistant/setup")[2]
    assert "claude mcp add --scope user pressless -- " in page
    assert 'data-copy="assistant-claude-code"' in page
    assert "ChatGPT" not in page


def test_a_refusal_names_no_place_on_a_screen():
    """§ 4.3: the AI app relays a refusal to the writer in a chat, where no
    "below" exists, so the replace refusal says where in Pressless to go."""
    said = assistant._said(publishing.WouldReplaceASite("held"))
    assert "below" not in said and "Publish" in said


def test_no_failure_points_an_ai_app_below():
    """PRESS-0402, § 4.3: no failure the door can meet tells the AI app to
    look "below", at details or a link a chat does not have; the details
    are in the log, which the words name. Breaks when a failure's screen
    words pointing below reach the AI app as they are."""
    import pressless_import
    from pressless import installer, takein, updater, updating, words  # noqa: F401
    # No tool takes a site in or updates Pressless, so these never reach the
    # door; a Refused carries its own words.
    not_at_the_door = {pressless_import.ImportStopped, updater.UpdateRejected,
                       installer.InstallFailed, assistant.Refused}
    below = [kind for kind, sentence in face.SENTENCES.items()
             if "below" in words.ENGLISH[sentence.next] and kind not in not_at_the_door]
    assert publishing.TakeoverOwed in below and store.DanglingReply in below
    for kind in [*below, RuntimeError]:
        said = assistant._said(kind.__new__(kind))
        assert "below" not in said, (kind, said)
    assert LOG_FILE in assistant._said(store.DanglingReply())
    assert LOG_FILE in assistant._said(RuntimeError())


# ----------------------------------------------------------------- INV-14 ---

# Windows line endings and a letter outside ASCII: both are kept.
_HELD = ('{\r\n  "preferences": {"sidebarMode": "café", "nested": [1, {"deep": true}]},\r\n'
         '  "mcpServers": {"other": {"command": "other-program", "args": ["--flag"]}}\r\n}\r\n')


def test_connecting_claude_desktop_keeps_the_rest(tmp_path):
    """INV-14. Breaks when the file is rewritten from Pressless's block alone,
    or when no copy of the file as it was is kept."""
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir()
    config.write_bytes(_HELD.encode("utf-8"))
    said = assistant.connect_claude_desktop(config, "the-program", ["--assistant"])
    assert said == "assistant.connect.done"
    now, was = json.loads(config.read_text(encoding="utf-8")), json.loads(_HELD)
    assert now["preferences"] == was["preferences"]
    assert now["mcpServers"]["other"] == was["mcpServers"]["other"]
    assert now["mcpServers"]["pressless"] == {"command": "the-program",
                                              "args": ["--assistant"]}
    assert set(now) == {"preferences", "mcpServers"}
    assert "café" in config.read_text(encoding="utf-8")
    copy = config.with_name("claude_desktop_config.before-pressless.json")
    assert copy.read_bytes() == _HELD.encode("utf-8")
    # A second press changes nothing, so the copy stays the file as it was.
    held = config.read_bytes()
    assert assistant.connect_claude_desktop(
        config, "the-program", ["--assistant"]) == "assistant.connect.done"
    assert config.read_bytes() == held and copy.read_bytes() == _HELD.encode("utf-8")


def test_the_copy_stays_the_file_before_pressless(tmp_path):
    """INV-14: the copy is the file as it was, byte for byte, a byte-order
    mark included, and connecting again from a moved program keeps it.
    Breaks when the copy is written from the decoded text, or rewritten
    whenever Pressless's entry changes."""
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir()
    held = b"\xef\xbb\xbf" + _HELD.encode("utf-8")
    config.write_bytes(held)
    copy = config.with_name("claude_desktop_config.before-pressless.json")
    for program in ("the-program", "the-moved-program"):
        assert assistant.connect_claude_desktop(
            config, program, ["--assistant"]) == "assistant.connect.done"
        assert copy.read_bytes() == held, program
    assert json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["pressless"][
        "command"] == "the-moved-program"
    assert set(assistant._CONNECT_WORDS.values()) == {
        "assistant.connect.done", "assistant.connect.not_found", "assistant.connect.unreadable"}


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '{"mcpServers": "words"}'])
def test_connecting_changes_nothing_it_cannot_read(tmp_path, text):
    """INV-14. Breaks when a file Pressless cannot read as Claude Desktop's
    settings is replaced."""
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir()
    config.write_text(text, encoding="utf-8")
    said = assistant.connect_claude_desktop(config, "the-program", ["--assistant"])
    assert said == "assistant.connect.unreadable"
    assert config.read_text(encoding="utf-8") == text
    assert [path.name for path in config.parent.iterdir()] == [config.name]


def test_connecting_needs_claude_desktop(tmp_path):
    """§ 4.2: with no Claude folder nothing is made; with the folder and no
    file, the file is made holding Pressless alone."""
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    said = assistant.connect_claude_desktop(config, "the-program", ["--assistant"])
    assert said == "assistant.connect.not_found" and not config.parent.exists()
    config.parent.mkdir()
    assert assistant.connect_claude_desktop(
        config, "the-program", ["--assistant"]) == "assistant.connect.done"
    assert json.loads(config.read_text(encoding="utf-8")) == {"mcpServers": {"pressless": {
        "command": "the-program", "args": ["--assistant"]}}}
    assert [path.name for path in config.parent.iterdir()] == [config.name]


def test_claude_desktops_file_on_each_system(monkeypatch, tmp_path):
    """§ 4.2: where Claude Desktop keeps its settings file, by system."""
    monkeypatch.setattr(assistant.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    name = "claude_desktop_config.json"
    for platform, folder in (("win32", tmp_path / "Roaming"),
                             ("darwin", tmp_path / "Library" / "Application Support"),
                             ("linux", tmp_path / "xdg")):
        monkeypatch.setattr(assistant.sys, "platform", platform)
        assert assistant.claude_desktop_config() == folder / "Claude" / name
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert assistant.claude_desktop_config() == tmp_path / ".config" / "Claude" / name


def test_the_connect_button(monkeypatch, tmp_path):
    """§ 4.2: the button writes the program the screen names into Claude
    Desktop's file, and the screen then says what happened."""
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    monkeypatch.setattr(assistant, "claude_desktop_config", lambda: config)
    with _pressless(tmp_path) as pressless:
        page = pressless.browser.request("GET", "/assistant/setup")[2]
        assert 'action="/assistant/connect"' in page and "Connect Claude Desktop" in page
        status, headers, _ = pressless.browser.request("POST", "/assistant/connect")
        assert status == 303 and not config.parent.exists()
        page = pressless.browser.request("GET", headers["Location"])[2]
        assert "could not find Claude Desktop" in page
        config.parent.mkdir()
        status, headers, _ = pressless.browser.request("POST", "/assistant/connect")
        page = pressless.browser.request("GET", headers["Location"])[2]
        assert "Claude Desktop is connected" in page
        program, arguments = assistant._program(pressless.own)
        assert json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["pressless"] == {
            "command": program, "args": arguments}
        # The words shown come from a fixed list, never from the address.
        page = pressless.browser.request("GET", "/assistant/setup?connect=<b>x</b>")[2]
        assert "<b>x</b>" not in page
