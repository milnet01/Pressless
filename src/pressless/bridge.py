"""The bridge an AI app starts as `pressless --assistant` (PRESS-0337 § 4.4,
docs/specs/PRESS-0337-ai-assistant.md).

It speaks a subset of the Model Context Protocol over stdio: one JSON-RPC
message per line, read from stdin, answered on stdout. Nothing else goes to
stdout. It lists the tools from the catalogue, and posts each call to the
door inside the running Pressless, found through the door file, which it
reads afresh on every call. It holds no lock and no state, and knows nothing
about the site.

Protocol: https://modelcontextprotocol.io/specification/2026-07-28 (stdio
transport, versioning, server/discover, tools). Legacy clients negotiate with
`initialize`, as the 2025-11-25 lifecycle says.
"""
from __future__ import annotations

import http.client
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pressless import __version__, assistant_tools, paths
from pressless.words import say

MODERN = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18")     # newest first
SUPPORTED = (MODERN, *LEGACY)
VERSION_META = "io.modelcontextprotocol/protocolVersion"
DOOR_NAME = "assistant-door.json"          # assistant.DOOR_NAME; a test checks they match
DOOR_PATH = "/assistant"
TIMEOUT_SECONDS = 300
LIST_TTL_MS = 3_600_000

# JSON-RPC's codes, and MCP's for a version it does not speak.
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
UNSUPPORTED_VERSION = -32022

_SERVER = {"name": "pressless", "version": __version__}
_IGNORED = frozenset({"notifications/initialized", "notifications/cancelled"})


# An answer is ("result", the result) or ("error", the JSON-RPC error object).
_Answer = tuple[str, dict]


def run(stdin: TextIO, stdout: TextIO, *,
        door: Callable[[str, dict], dict | None] | None = None) -> None:
    """Answer each line of `stdin` until it ends. `door` posts one call to
    Pressless and returns its reply, or None where no Pressless answers; a
    test hands in its own."""
    post = door or _post
    for line in stdin:
        if not line.strip():
            continue
        reply = _handle(line, post)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()


def _handle(line: str, post: Callable[[str, dict], dict | None]) -> dict | None:
    try:
        message = json.loads(line)
    except ValueError:
        return _reply(None, _error(PARSE_ERROR, "not JSON"))
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _reply(message.get("id") if isinstance(message, dict) else None,
                      _error(INVALID_REQUEST, "not a JSON-RPC 2.0 message"))
    if "id" not in message or message.get("method") in _IGNORED:
        return None                             # a notification is never answered
    params = message.get("params")
    params = {} if params is None else params
    if not isinstance(params, dict):
        return _reply(message["id"], _error(INVALID_PARAMS, "params is not an object"))
    return _reply(message["id"], _answer(message.get("method"), params, post))


def _reply(ident: object, answer: _Answer) -> dict:
    kind, body = answer
    return {"jsonrpc": "2.0", "id": ident, kind: body}


def _error(code: int, message: str, data: object = None) -> _Answer:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return "error", error


def _answer(method: object, params: dict, post: Callable[[str, dict], dict | None]) -> _Answer:
    if method == "initialize":
        asked = params.get("protocolVersion")
        chosen = asked if asked in LEGACY else LEGACY[0]
        return "result", {"protocolVersion": chosen, "capabilities": {"tools": {}},
                          "serverInfo": _SERVER}
    if method == "ping":
        return "result", {}
    meta = params.get("_meta")
    asked = meta.get(VERSION_META) if isinstance(meta, dict) else None
    if asked is not None and asked != MODERN:
        return _error(UNSUPPORTED_VERSION, "Unsupported protocol version",
                      {"supported": list(SUPPORTED), "requested": asked})
    modern = asked == MODERN        # a request naming no version is legacy
    # 2026-07-28: every result says it is complete, and discovery and the
    # list carry caching hints; neither holds anything of the writer's.
    complete = {"resultType": "complete"} if modern or method == "server/discover" else {}
    cached = {"ttlMs": LIST_TTL_MS, "cacheScope": "public"}
    if method == "server/discover":
        return "result", {**complete, "supportedVersions": list(SUPPORTED),
                          "capabilities": {"tools": {}},
                          "_meta": {"io.modelcontextprotocol/serverInfo": _SERVER}, **cached}
    if method == "tools/list":
        listed = {"tools": [{"name": tool.name, "description": tool.description,
                             "inputSchema": tool.schema()} for tool in assistant_tools.TOOLS]}
        return "result", {**complete, **listed, **(cached if modern else {})}
    if method == "tools/call":
        kind, body = _call(params, post)
        return (kind, {**complete, **body}) if kind == "result" else (kind, body)
    return _error(METHOD_NOT_FOUND, f"no method {method!r}")


def _call(params: dict, post: Callable[[str, dict], dict | None]) -> _Answer:
    name, arguments = params.get("name"), params.get("arguments", {})
    if not isinstance(name, str) or name not in assistant_tools.BY_NAME:
        return _error(INVALID_PARAMS, f"no tool {name!r}")
    if not isinstance(arguments, dict):
        return _error(INVALID_PARAMS, "arguments is not an object")
    reply = post(name, arguments)
    if reply is not None and reply.get("ok") is True:
        result = reply.get("result", {})
        return "result", {"content": [{"type": "text",
                                       "text": json.dumps(result, ensure_ascii=False)}],
                          "structuredContent": result, "isError": False}
    said = reply.get("said") if reply is not None else None
    return "result", {"content": [{"type": "text",
                                   "text": str(said or say("assistant.open_pressless"))}],
                      "isError": True}


def door_file() -> Path:
    return paths.own_folder() / DOOR_NAME


def _post(tool: str, arguments: dict) -> dict | None:
    """One call to the door, read from the door file now (§ 4.4). None where
    no Pressless answers there: closed, switched off, or something else on its
    old port (§ 6)."""
    try:
        door = json.loads(door_file().read_text(encoding="utf-8"))
        port, token = int(door["port"]), str(door["token"])
    except (OSError, ValueError, KeyError, TypeError, paths.NotPackaged):
        return None
    body = json.dumps({"tool": tool, "arguments": arguments, "version": __version__})
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT_SECONDS)
    try:
        connection.request("POST", DOOR_PATH, body.encode("utf-8"), {
            "Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read()
        reply = json.loads(data.decode("utf-8")) if response.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()
    return reply if isinstance(reply, dict) else None


def main() -> int:
    """`pressless --assistant`: serve stdin until it ends."""
    # UTF-8 both ways and bare newlines, whatever the console's own settings.
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n" if stream is sys.stdout else None)
    run(sys.stdin, sys.stdout)
    return 0
