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
import hashlib
import http.client
import io
import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser
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
    publishing,
    starter,
    store,
    undo,
)

DOOR_FILE = "assistant-door.json"
SWITCH_FILE = "assistant.json"
LOG_FILE = "pressless.log"
CHANGED_WORDS = "This entry was changed in another window or outside Pressless"
LOCKED_WORDS = "which the AI helper may not do"
ONE_WAITING_WORDS = "A request is already waiting"
OPEN_WORDS = "Pressless is not open, or its AI helper is switched off"
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
             cookie: bool = False) -> tuple[int, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", host or f"127.0.0.1:{self.port}")
            if bearer is not None:
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


# ----------------------------------------------------------------- INV-10 ---


def test_one_at_a_time(tmp_path):
    """INV-10. Breaks when the door lock is per tool."""
    with _pressless(tmp_path) as pressless:
        replies: list[dict] = []
        with assistant.LOCK:
            caller = threading.Thread(target=lambda: replies.append(
                pressless.call("list_entries")))
            caller.start()
            caller.join(timeout=0.5)
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
        assert look.read(folder).width == changed["width"]


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
    leaves out a file the build reads."""
    _key(monkeypatch)
    github = _github()
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
        again = pressless.waiting()
        assert again["request"] == asked and again["stamp"] != first["stamp"]
        assert pressless.ok("request_status", {"request": asked})["status"] == "waiting"

        # Nothing changed since: yes publishes.
        reply = pressless.answer(asked, yes=True)
        assert reply["status"] == "done", reply
        assert _wrote(github)
        assert store.list_slugs(folder, draft=False) == ("seaside",)
        assert pressless.ok("request_status", {"request": asked})["status"] == "done"


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
    assert assistant.SWITCH_NAME == SWITCH_FILE


@pytest.mark.parametrize("name, arguments, why", [
    ("nothing", {}, "there is no tool 'nothing'"),
    ("read_entry", {}, "read_entry needs address"),
    ("read_entry", {"address": 1}, "address must be string"),
    ("read_entry", {"address": "a", "more": 1}, "read_entry takes no more"),
    ("read_insights", {"days": 30}, "days must be one of [7, 28, 365]"),
    ("read_insights", {"days": True}, "days must be a whole number"),
    ("save_entry", {"address": "a", "version": "b", "tags": [1]}, "tags must list text"),
])
def test_the_catalogue_refuses_a_bad_call(name, arguments, why):
    assert assistant_tools.problem(name, arguments) == why


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
    assert assistant._program() == (str(program), ["--assistant"])


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
