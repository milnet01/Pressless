# The bridge an AI app starts (PRESS-0337 § 4.4, INV-7 and INV-8).
#
# These check our reading of MCP's 2026-07-28 specification, not the
# specification itself; § 7's by-hand check runs real AI apps.
from __future__ import annotations

import ast
import http.server
import io
import json
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pressless import __main__ as main_module
from pressless import assistant_tools, bridge

SOURCE = Path(__file__).resolve().parent.parent / "src" / "pressless" / "bridge.py"
OPEN_WORDS = "Pressless is not open, or its AI helper is switched off"
MODERN = "2026-07-28"


def _talk(*messages: dict, door=None) -> list[dict]:
    out = io.StringIO()
    bridge.run(io.StringIO("".join(json.dumps(message) + "\n" for message in messages)), out,
               door=door or (lambda tool, arguments: None))
    return [json.loads(line) for line in out.getvalue().splitlines()]


def _modern(ident: int, method: str, **params: object) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "method": method,
            "params": {**params, "_meta": {"io.modelcontextprotocol/protocolVersion": MODERN}}}


# ------------------------------------------------------------------ INV-7 ---


def test_stdout_is_protocol_only(tmp_path, monkeypatch, capsys):
    """INV-7. Breaks when the report is printed before the route is chosen."""
    monkeypatch.setenv("PRESSLESS_FOLDER", str(tmp_path))     # no door file there
    lines = [_modern(1, "server/discover"), _modern(2, "tools/list"),
             _modern(3, "tools/call", name="site_overview", arguments={})]
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(m) + "\n" for m in lines)))
    assert main_module.main(["--assistant"]) == 0
    out = capsys.readouterr().out
    assert "pressless: ok" not in out
    replies = [json.loads(line) for line in out.splitlines()]
    assert [reply["id"] for reply in replies] == [1, 2, 3]
    assert all(reply["jsonrpc"] == "2.0" and ("result" in reply or "error" in reply)
               for reply in replies)
    assert replies[2]["result"]["isError"] is True
    assert OPEN_WORDS in replies[2]["result"]["content"][0]["text"]


def test_a_packaged_bridge_takes_no_folder(tmp_path, monkeypatch):
    """PRESS-0404: only a source run's bridge is told its folder. A packaged
    one finds its own, so a settings file naming another folder cannot send
    an AI app's calls to another door. Breaks when a packaged program takes
    the folder."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(SystemExit) as stopped:
        main_module.main(["--assistant", str(tmp_path)])
    assert stopped.value.code == 2


# ------------------------------------------------------------------ INV-8 ---


def test_bridge_imports():
    """INV-8. Breaks when the bridge imports `credentials`, `store` or
    `settings` for convenience."""
    reached: set[str] = set()
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module == "pressless":
            reached |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pressless."):
            reached.add(node.module.split(".", 1)[1])
        elif isinstance(node, ast.Import):
            reached |= {alias.name.split(".", 1)[1] for alias in node.names
                        if alias.name.startswith("pressless.")}
    assert reached - {"__version__"} == {"assistant_tools", "paths", "words"}


def test_bridge_reaches_only_this_computer():
    """§ 4.4, and why PRESS-0262 INV-9 lets the bridge import http.client:
    every connection it opens is to 127.0.0.1."""
    calls = [node for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr in ("HTTPConnection", "HTTPSConnection", "create_connection",
                                    "urlopen", "socket")]
    assert calls, "the bridge opens no connection, so this test checks nothing"
    for call in calls:
        assert call.func.attr == "HTTPConnection"
        assert isinstance(call.args[0], ast.Constant) and call.args[0].value == "127.0.0.1"


# ----------------------------------------------------- framing and versions ---


def test_legacy_initialize_negotiates():
    """§ 4.4: a listed legacy version is echoed; any other gets the newest
    legacy version, and the app decides."""
    for asked, chosen in (("2025-06-18", "2025-06-18"), ("2025-11-25", "2025-11-25"),
                          ("2024-11-05", "2025-11-25")):
        reply, = _talk({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": asked, "capabilities": {},
                                   "clientInfo": {"name": "t", "version": "1"}}})
        assert reply["result"]["protocolVersion"] == chosen
        assert reply["result"]["capabilities"] == {"tools": {}}


def test_an_unknown_modern_version_is_refused():
    reply, = _talk({"jsonrpc": "2.0", "id": 7, "method": "tools/list",
                    "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}}})
    assert reply["error"]["code"] == -32022
    assert reply["error"]["data"] == {"supported": [MODERN, "2025-11-25", "2025-06-18"],
                                      "requested": "2099-01-01"}


def test_discovery_and_the_list():
    discover, listed = _talk(_modern(1, "server/discover"), _modern(2, "tools/list"))
    assert discover["result"]["resultType"] == "complete"
    assert discover["result"]["supportedVersions"][0] == MODERN
    assert discover["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "pressless"
    result = listed["result"]
    assert result["resultType"] == "complete" and result["cacheScope"] == "public"
    assert isinstance(result["ttlMs"], int) and result["ttlMs"] >= 0
    names = [tool["name"] for tool in result["tools"]]
    assert names == [tool.name for tool in assistant_tools.TOOLS]
    assert all(tool["inputSchema"]["type"] == "object" for tool in result["tools"])
    # Legacy: the same tools, with no 2026 fields.
    legacy, = _talk({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert [tool["name"] for tool in legacy["result"]["tools"]] == names
    assert "resultType" not in legacy["result"] and "ttlMs" not in legacy["result"]


def test_a_call_carries_the_door_reply():
    sent = []

    def door(tool, arguments):
        sent.append((tool, arguments))
        return {"ok": True, "result": {"entries": []}}

    reply, = _talk(_modern(1, "tools/call", name="list_entries", arguments={}), door=door)
    assert sent == [("list_entries", {})]
    assert reply["result"]["isError"] is False
    assert reply["result"]["structuredContent"] == {"entries": []}
    assert json.loads(reply["result"]["content"][0]["text"]) == {"entries": []}

    refused, = _talk(_modern(2, "tools/call", name="list_entries", arguments={}),
                     door=lambda tool, arguments: {"ok": False, "said": "Not that."})
    assert refused["result"]["isError"] is True
    assert refused["result"]["content"] == [{"type": "text", "text": "Not that."}]


@pytest.mark.parametrize("message, code", [
    ({"jsonrpc": "2.0", "id": 1, "method": "resources/list"}, -32601),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nothing"}}, -32602),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
      "params": {"name": "list_entries", "arguments": []}}, -32602),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": []}, -32602),
    ({"id": 1, "method": "tools/list"}, -32600),
])
def test_a_bad_request_gets_its_code(message, code):
    reply, = _talk(message)
    assert reply["error"]["code"] == code and reply["id"] == 1


def test_notifications_and_framing():
    """One message per line, no reply to a notification, and a line that is
    not JSON answered with -32700."""
    out = io.StringIO()
    bridge.run(io.StringIO('{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
                           "\n"
                           "not json\n"
                           '{"jsonrpc":"2.0","id":"a","method":"ping"}\n'
                           '{"jsonrpc":"2.0","method":"notifications/cancelled",'
                           '"params":{"requestId":"a"}}\n'), out,
               door=lambda tool, arguments: None)
    lines = out.getvalue().split("\n")
    assert lines[-1] == "" and all(lines[:-1])
    replies = [json.loads(line) for line in lines[:-1]]
    assert replies == [{"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "not JSON"}},
                       {"jsonrpc": "2.0", "id": "a", "result": {}}]


def test_a_lone_surrogate_is_answered():
    """§ 4.4 framing: a request id holding a lone surrogate escape parses, and
    its echo is written as ASCII escapes, since strict UTF-8 cannot write it.
    Breaks when the reply is written unescaped and the bridge dies."""
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")
    bridge.run(io.StringIO('{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n'
                           '{"jsonrpc":"2.0","id":2,"method":"ping"}\n'), out,
               door=lambda tool, arguments: None)
    out.flush()
    replies = [json.loads(line) for line in out.buffer.getvalue().decode("ascii").splitlines()]
    assert [reply["id"] for reply in replies] == ["\ud800", 2]


def test_a_fault_in_one_call_is_answered_and_the_next_runs():
    """JSON-RPC's internal error: a call that raises inside the bridge is
    answered -32603, and the bridge reads on. Breaks when the exception
    ends `run`."""
    def door(tool, arguments):
        raise RuntimeError("unforeseen")

    replies = {reply["id"]: reply for reply in _talk(
        _modern(1, "tools/call", name="list_entries", arguments={}),
        _modern(2, "tools/list"), door=door)}
    assert replies[1]["error"]["code"] == -32603
    assert "tools" in replies[2]["result"]


def test_a_ping_is_answered_while_a_call_waits():
    """§ 4.4: a call may wait minutes on the door, and an AI app may drop a
    server whose ping goes unanswered, so a ping is answered meanwhile.
    Breaks when the bridge reads its next line only after the call ends."""
    pinged, answered = threading.Event(), []

    class Out(io.StringIO):
        def write(self, text: str) -> int:
            if '"id":2' in text:
                pinged.set()
            return super().write(text)

    def door(tool, arguments):
        answered.append(pinged.wait(10))
        return {"ok": True, "result": {}}

    out = Out()
    bridge.run(io.StringIO(json.dumps(_modern(1, "tools/call", name="list_entries",
                                              arguments={})) + "\n"
                           + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}) + "\n"),
               out, door=door)
    assert answered == [True]
    assert [json.loads(line)["id"] for line in out.getvalue().splitlines()] == [2, 1]


# ------------------------------------------------------------------ INV-15 ---

_HELD = "the door file's token"


@contextmanager
def _listener(tmp_path: Path, monkeypatch, answer: Callable) -> Iterator[list[dict]]:
    """A server on the door file's port, as after a crash: `answer(handler,
    heard)` replies to each POST. Yields what it heard, each request's
    Authorization and body."""
    heard: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            heard.append({"authorization": self.headers.get("Authorization", ""),
                          "body": self.rfile.read(length).decode("utf-8")})
            answer(self, heard[-1])

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        (tmp_path / "assistant-door.json").write_text(json.dumps(
            {"port": server.server_address[1], "token": _HELD, "version": "0"}),
            encoding="utf-8")
        monkeypatch.setenv("PRESSLESS_FOLDER", str(tmp_path))
        yield heard
    finally:
        server.shutdown()
        server.server_close()


def _send(handler, body: bytes, length: int | None = None) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body) if length is None else length))
    handler.end_headers()
    handler.wfile.write(body)


def _proving(then: Callable) -> Callable:
    """A listener that holds the token: it proves it, then answers with `then`."""
    def answer(handler, heard: dict) -> None:
        scheme, _, nonce = heard["authorization"].partition(" ")
        if scheme == assistant_tools.PROVE:
            _send(handler, json.dumps({"proof": assistant_tools.proof(_HELD, nonce)}).encode())
        else:
            then(handler, heard)
    return answer


def test_an_impostor_on_the_port_gets_nothing(tmp_path, monkeypatch):
    """INV-15, § 6: something else on a crashed Pressless's old port is sent
    neither the token nor the call, and its answer is not believed. Breaks
    when the bridge posts the call before the door proves the token."""
    forged = json.dumps({"ok": True, "result": {"forged": True}, "proof": "0" * 64}).encode()
    with _listener(tmp_path, monkeypatch,
                   lambda handler, heard: _send(handler, forged)) as heard:
        reply = bridge._post("save_entry", {"body": "a private draft"})
    assert reply is None
    assert len(heard) == 1 and heard[0]["authorization"].startswith(assistant_tools.PROVE + " ")
    assert "a private draft" not in json.dumps(heard) and _HELD not in json.dumps(heard)


def test_a_proved_door_gets_the_call(tmp_path, monkeypatch):
    """INV-15's other half: a listener proving the token is sent the call
    with the token, and its reply is believed."""
    def reply(handler, heard: dict) -> None:
        _send(handler, json.dumps({"ok": True, "result": {"entries": []}}).encode())

    with _listener(tmp_path, monkeypatch, _proving(reply)) as heard:
        assert bridge._post("list_entries", {}) == {"ok": True, "result": {"entries": []}}
    assert heard[1]["authorization"] == f"Bearer {_HELD}"
    assert json.loads(heard[1]["body"])["tool"] == "list_entries"


def test_a_reply_past_the_limit_is_not_believed(tmp_path, monkeypatch):
    """§ 4.4: a reply larger than any door sends is refused, not read whole.
    Breaks when the reply is read with no cap."""
    monkeypatch.setattr(bridge, "REPLY_LIMIT", 1000)
    big = json.dumps({"ok": True, "result": {"text": "x" * 5000}}).encode()
    with _listener(tmp_path, monkeypatch, _proving(lambda handler, heard: _send(handler, big))):
        assert bridge._post("list_entries", {}) is None


def test_a_trickling_reply_ends_at_the_timeout(tmp_path, monkeypatch):
    """§ 4.4: the timeout is the whole call's, so a reply sent a byte at a
    time cannot hold the bridge past it. Breaks when the timeout applies
    to each read alone."""
    monkeypatch.setattr(bridge, "TIMEOUT_SECONDS", 0.5)
    stop = threading.Event()

    def trickle(handler, heard: dict) -> None:
        _send(handler, b"", length=10_000)
        while not stop.wait(0.05):
            handler.wfile.write(b" ")
            handler.wfile.flush()

    with _listener(tmp_path, monkeypatch, _proving(trickle)):
        started = time.monotonic()
        try:
            reply = bridge._post("list_entries", {})
        finally:
            stop.set()
        took = time.monotonic() - started
    assert took < 5, took
    assert reply is not None and "took too long to answer" in reply["said"]


def test_a_slow_door_is_not_called_closed(tmp_path, monkeypatch):
    """§ 6: a door that takes longer than the timeout may still be doing the
    call, so the AI app is told to check, not that Pressless is closed.
    Breaks when a timeout is answered as `assistant.open_pressless`."""
    import socket
    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    listening.listen(1)
    try:
        (tmp_path / "assistant-door.json").write_text(json.dumps(
            {"port": listening.getsockname()[1], "token": "a token", "version": "0"}),
            encoding="utf-8")
        monkeypatch.setenv("PRESSLESS_FOLDER", str(tmp_path))
        monkeypatch.setattr(bridge, "TIMEOUT_SECONDS", 0.2)
        reply = bridge._post("list_entries", {})
    finally:
        listening.close()
    assert reply is not None and reply["ok"] is False
    assert "took too long to answer" in reply["said"] and OPEN_WORDS not in reply["said"]
