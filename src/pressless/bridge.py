"""The bridge an AI app starts as `pressless --assistant` (PRESS-0337 § 4.4,
docs/specs/PRESS-0337-ai-assistant.md).

It speaks a subset of the Model Context Protocol over stdio: one JSON-RPC
message per line, read from stdin, answered on stdout. Nothing else goes to
stdout. It lists the tools from the catalogue, and posts each call to the
door inside the running Pressless, found through the door file, which it
reads afresh on every call. The door proves it holds the file's token before
the call is sent. It keeps nothing between calls, holds no lock but its own
output's, and knows nothing about the site.

Protocol: https://modelcontextprotocol.io/specification/2026-07-28 (stdio
transport, versioning, server/discover, tools). Legacy clients negotiate with
`initialize`, as the 2025-11-25 lifecycle says.
"""
from __future__ import annotations

import hmac
import http.client
import json
import queue
import secrets
import sys
import threading
import time
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
DOOR_PATH = "/assistant"                   # assistant.ADDRESS; a test checks they match
# A publish ask builds the whole site to plan it, and the door queues calls
# behind one another (§ 4.3), so a call may wait minutes on a large site.
TIMEOUT_SECONDS = 300
LIST_TTL_MS = 3_600_000
# The most a door reply may hold: the Face's own body cap. A listener sending
# more is not the door.
REPLY_LIMIT = 64 * 1024 * 1024
_PROOF_LIMIT = 1024
_CHUNK = 64 * 1024

# JSON-RPC's codes, and MCP's for a version it does not speak.
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
INTERNAL_ERROR = -32603
UNSUPPORTED_VERSION = -32022

_SERVER = {"name": "pressless", "version": __version__}
_IGNORED = frozenset({"notifications/initialized", "notifications/cancelled"})


# An answer is ("result", the result) or ("error", the JSON-RPC error object).
_Answer = tuple[str, dict]


def run(stdin: TextIO, stdout: TextIO, *,
        door: Callable[[str, dict], dict | None] | None = None) -> None:
    """Answer each line of `stdin` until it ends, then each call still
    waiting. `door` posts one call to Pressless and returns its reply, or
    None where no Pressless answers; a test hands in its own.

    Calls wait on the door, up to TIMEOUT_SECONDS, so they run one after
    another on their own thread, and a ping meanwhile is answered at once
    (§ 4.4). Replies may then come out of order, which JSON-RPC allows."""
    post = door or _post
    written = threading.Lock()

    def write(reply: dict | None) -> None:
        if reply is None:
            return
        with written:
            # ASCII escapes: a string from the request may hold a lone
            # surrogate, which UTF-8 cannot write.
            stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
            stdout.flush()

    calls: queue.Queue[dict | None] = queue.Queue()

    def call_each() -> None:
        while (message := calls.get()) is not None:
            write(_handle(message, post))

    caller = threading.Thread(target=call_each, name="bridge-calls", daemon=True)
    caller.start()
    try:
        for line in stdin:
            if not line.strip():
                continue
            message, refused = _parsed(line)
            if refused is not None:
                write(refused)
            elif message.get("method") == "tools/call":
                calls.put(message)
            else:
                write(_handle(message, post))
    finally:
        calls.put(None)
        caller.join()


def _parsed(line: str) -> tuple[dict, dict | None]:
    """The line's message, and the reply refusing it, or None."""
    try:
        message = json.loads(line)
    except ValueError:
        return {}, _reply(None, _error(PARSE_ERROR, "not JSON"))
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {}, _reply(message.get("id") if isinstance(message, dict) else None,
                          _error(INVALID_REQUEST, "not a JSON-RPC 2.0 message"))
    return message, None


def _handle(message: dict, post: Callable[[str, dict], dict | None]) -> dict | None:
    if "id" not in message or message.get("method") in _IGNORED:
        return None                             # a notification is never answered
    params = message.get("params")
    params = {} if params is None else params
    if not isinstance(params, dict):
        return _reply(message["id"], _error(INVALID_PARAMS, "params is not an object"))
    try:
        answer = _answer(message.get("method"), params, post)
    except Exception:  # noqa: BLE001 -- one request's fault never ends the bridge
        answer = _error(INTERNAL_ERROR, "internal error")
    return _reply(message["id"], answer)


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
    # 2026-07-28: every result below says it is complete, and discovery and
    # the list carry caching hints; neither holds anything of the writer's.
    # `ping` answered above is legacy only, and answers {} (§ 4.4).
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


def door_file(own: Path | None = None) -> Path:
    """The door file in `own`, a source run's folder, else Pressless's own."""
    return (own if own is not None else paths.own_folder()) / DOOR_NAME


def _post(tool: str, arguments: dict, own: Path | None = None) -> dict | None:
    """One call to the door, read from `door_file(own)` now (§ 4.4). None
    where no Pressless answers there: closed, switched off, or something else
    on its old port, which cannot prove it holds the token (§ 6). The whole
    call, proof included, has TIMEOUT_SECONDS."""
    try:
        door = json.loads(door_file(own).read_text(encoding="utf-8"))
        port, token = int(door["port"]), str(door["token"])
    except (OSError, ValueError, KeyError, TypeError, paths.NotPackaged):
        return None
    deadline = time.monotonic() + TIMEOUT_SECONDS
    nonce = secrets.token_urlsafe(16)
    try:
        # Nothing of the writer's, and not the token, goes before the proof.
        proved = _exchange(port, f"{assistant_tools.PROVE} {nonce}", b"", _PROOF_LIMIT,
                           deadline)
        if not (isinstance(proved, dict) and isinstance(proved.get("proof"), str)
                and hmac.compare_digest(proved["proof"], assistant_tools.proof(token, nonce))):
            return None
        body = json.dumps({"tool": tool, "arguments": arguments, "version": __version__})
        reply = _exchange(port, f"Bearer {token}", body.encode("utf-8"), REPLY_LIMIT, deadline)
    except TimeoutError:
        # The door may still be doing the call; "closed" would be untrue (§ 6).
        return {"ok": False, "said": say("assistant.still_working")}
    except (OSError, ValueError, http.client.HTTPException):
        return None
    return reply if isinstance(reply, dict) else None


def _exchange(port: int, authorization: str, body: bytes, limit: int,
              deadline: float) -> object:
    """POST `body` to the door on `port`: its JSON reply, or None where the
    status is not 200 or the reply passes `limit` bytes. Raises TimeoutError
    once `deadline` passes, however slowly the reply trickles in."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_left(deadline))
    try:
        connection.request("POST", DOOR_PATH, body, {
            "Host": f"127.0.0.1:{port}", "Authorization": authorization,
            "Content-Type": "application/json"})
        # Held here: the connection lets go of its socket once a reply that
        # closes it arrives, and the reply is still read through it.
        sock = connection.sock
        response = connection.getresponse()
        if response.status != 200:
            return None
        data = bytearray()
        while not response.isclosed():      # closed once its last byte is read
            sock.settimeout(_left(deadline))
            chunk = response.read1(_CHUNK)     # what has come, so the deadline is checked
            if not chunk:
                break
            data += chunk
            if len(data) > limit:
                return None
        return json.loads(data.decode("utf-8"))
    finally:
        connection.close()


def _left(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError
    return left


def main(own: Path | None = None) -> int:
    """`pressless --assistant`: serve stdin until it ends. `own` is the folder
    a source run is told (§ 4.4); a packaged program finds its own."""
    # UTF-8 both ways and bare newlines, whatever the console's own settings.
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n" if stream is sys.stdout else None)
    run(sys.stdin, sys.stdout,
        door=None if own is None else lambda tool, arguments: _post(tool, arguments, own))
    return 0
