# The bridge an AI app starts (PRESS-0337 § 4.4, INV-7 and INV-8).
#
# These check our reading of MCP's 2026-07-28 specification, not the
# specification itself; § 7's by-hand check runs real AI apps.
from __future__ import annotations

import ast
import io
import json
import sys
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
