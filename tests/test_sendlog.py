"""PRESS-0436: Send my log posts the two log files to the relay, only when
Send is pressed, and nothing else.

The relay's address and the log's file names are written out here rather than
imported, so a module posting elsewhere, or sending other files, fails.
"""
from __future__ import annotations

import ast
import base64
import gzip
import hashlib
import json
import re
from pathlib import Path

import pytest
from _face_session import Browser

from pressless import __version__, face, log, report, sendlog, usage

RELAY = "https://pressless-logs.pressless-logs.workers.dev/log"
NEWEST = "newestlinezqx"
OLDEST = "oldestlinezqx"
SENTINEL = "sentinellogtextzqx"


class _Relay:
    """`https.Client.request` that records each request and answers as told."""

    def __init__(self, status: int = 200, body: bytes = b'{"reference": "K7Q2MX"}',
                 fails: bool = False) -> None:
        self.sent: list[tuple[str, str, bytes, dict[str, str]]] = []
        self._answer = (status, {}, body)
        self._fails = fails

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.sent.append((method, url, body or b"", headers))
        if self._fails:
            raise OSError("no answer from pressless-logs.pressless-logs.workers.dev (URLError)")
        return self._answer


def _logs(folder: Path, new: str, old: str | None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pressless.log").write_text(new, encoding="utf-8")
    if old is not None:
        (folder / "pressless.log.1").write_text(old, encoding="utf-8")


def _opened(body: bytes) -> tuple[dict, str, str]:
    """The body's first line, and the two files' text it carries."""
    line, _, parts = body.partition(b"\n")
    head = json.loads(line)
    texts = [gzip.decompress(base64.b64decode(part, validate=True)).decode("utf-8")
             for part in (parts[:head["log"]], parts[head["log"]:])]
    assert head["log"] + head["old"] == len(parts)
    return head, texts[0], texts[1]


def _press(tmp_path: Path, relay: _Relay) -> tuple[int, str, Path]:
    """Serve the Face from `tmp_path / "own"`, its log files beside it, and
    press Send. The answer's status, its text, and the Face's own log."""
    own = tmp_path / "own"
    _logs(own, f"{SENTINEL}\n", f"{SENTINEL} older\n")
    served = face.serve(own)
    try:
        sendlog.register(served, own, client=relay)
        status, _, text = Browser(served).request("POST", "/log/send")
    finally:
        served.stop()
    return status, text, own / "pressless.log"


def test_only_the_send_route_sends(tmp_path):
    """INV-1. Breaks when a start, a page or any module but the route calls
    send."""
    relay = _Relay()
    own = tmp_path / "own"
    _logs(own, "a line\n", None)
    served = face.serve(own)
    try:
        sendlog.register(served, own, client=relay)
        report.register(served)
        browser = Browser(served)
        for page in ("/", "/report"):
            browser.request("GET", page)
        assert relay.sent == []
        browser.request("POST", "/log/send")
    finally:
        served.stop()
    assert [(method, url) for method, url, _, _ in relay.sent] == [("POST", RELAY)]

    source = Path(sendlog.__file__).parent
    callers = [path.name for path in sorted(source.rglob("*.py"))
               if path.name != "sendlog.py" and _calls_send(path.read_text(encoding="utf-8"))]
    assert callers == []


def _calls_send(text: str) -> bool:
    """Whether a module imports `send` from sendlog, or calls `.send` on
    sendlog under any name it imports it as."""
    tree = ast.parse(text)
    names = {"sendlog"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "pressless.sendlog":
            if any(alias.name in ("send", "*") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module == "pressless":
            names |= {alias.asname or alias.name for alias in node.names
                      if alias.name == "sendlog"}
        elif isinstance(node, ast.Import):
            names |= {alias.asname for alias in node.names
                      if alias.name == "pressless.sendlog" and alias.asname}
    return any(isinstance(node, ast.Attribute) and node.attr == "send"
               and ((isinstance(node.value, ast.Name) and node.value.id in names)
                    or (isinstance(node.value, ast.Attribute) and node.value.attr == "sendlog"))
               for node in ast.walk(tree))


@pytest.mark.parametrize("text", [
    "from pressless.sendlog import send\nsend(folder)\n",
    "from pressless import sendlog\nsendlog.send (folder)\n",
    "from pressless import sendlog as logs\nlogs.send(folder)\n",
    "import pressless.sendlog\npressless.sendlog.send(folder)\n",
    "import pressless.sendlog as logs\nlogs.send(folder)\n",
])
def test_the_caller_check_sees_every_spelling(text):
    """INV-1's walk. Breaks when it matches one spelling of the call only."""
    assert _calls_send(text)
    assert not _calls_send("from pressless import sendlog\nsendlog.register(face, folder)\n")


def test_the_body_is_the_logs_and_nothing_else(tmp_path):
    """INV-2. Breaks when a key is added, or the folder's path is put in."""
    relay = _Relay()
    folder = tmp_path / "logs"
    _logs(folder, f"{NEWEST}\n", f"{OLDEST}\n")
    assert sendlog.send(folder, relay) == "K7Q2MX"
    [(method, url, body, headers)] = relay.sent
    assert (method, url) == ("POST", RELAY)
    assert headers["Content-Type"] == "application/x-pressless-log"
    head, text, old = _opened(body)
    assert head == {"version": __version__, "system": usage.system()[:128],
                    "tail": NEWEST, "log": head["log"], "old": head["old"]}
    assert (text, old) == (f"{NEWEST}\n", f"{OLDEST}\n")
    assert str(tmp_path).encode("utf-8") not in body


def test_the_tail_is_the_last_100_lines_cut_to_60000_characters(tmp_path):
    """§ 4.2's `tail`, which the relay quotes in the issue. Breaks when it
    keeps more lines, or the first characters of an over-long line."""
    relay = _Relay()
    folder = tmp_path / "logs"
    _logs(folder, "".join(f"line {number}\n" for number in range(300)), None)
    sendlog.send(folder, relay)
    tail = _opened(relay.sent[0][2])[0]["tail"]
    assert tail.split("\n") == [f"line {number}" for number in range(200, 300)]
    relay = _Relay()
    _logs(folder, "start" + "é" * 70_000 + "end\n", None)
    sendlog.send(folder, relay)
    tail = _opened(relay.sent[0][2])[0]["tail"]
    assert len(tail) == 60_000 and tail.endswith("éend")


def test_known_secret_shapes_are_removed_before_sending(tmp_path):
    """§ 4.2: a secret that slipped into a log never leaves the machine.
    Breaks when a file is sent as read. Built in parts, so no file here
    holds anything shaped like a secret."""
    key = "PRI" + "VATE KEY"
    shapes = ["gh" + "p_" + "fake" * 9, "github" + "_pat_" + "fake" * 6,
              "AI" + "za" + "fake" * 9, "ya" + "29." + "fake" * 4, "1/" + "/" + "fake" * 6,
              "s" + "k-" + "fake" * 6, f"-----BEGIN {key}-----\nfake\n-----END {key}-----"]
    relay = _Relay()
    folder = tmp_path / "logs"
    lines = "".join(f"{NEWEST} {shape} kept\n" for shape in shapes)
    _logs(folder, lines + "Authorization: Bearer " + "fake" * 4 + "\n", lines)
    sendlog.send(folder, relay)
    head, text, old = _opened(relay.sent[0][2])
    for sent in (text, old):
        assert "fake" not in sent
        assert sent.count(f"{NEWEST} [removed] kept\n") == len(shapes)
    assert text.endswith("Authorization: Bearer [removed]\n")
    assert "fake" not in head["tail"]


def test_the_relay_takes_what_the_app_sends():
    """The app's cap and reference pattern against relay/src/index.js.
    Breaks when one side changes and the other does not."""
    relay_source = (Path(__file__).parents[1] / "relay" / "src" / "index.js").read_text(
        encoding="utf-8")
    largest = int(re.search(r"\bLARGEST = ([0-9_]+);", relay_source)[1].replace("_", ""))
    alphabet = re.search(r'ALPHABET = "([A-Z0-9]+)";', relay_source)[1]
    length = int(re.search(r"function reference\(\) \{.*?Uint8Array\((\d+)\)",
                           relay_source, re.DOTALL)[1])
    assert sendlog.LARGEST <= largest
    pattern = sendlog._REFERENCE.pattern
    assert all(re.fullmatch(pattern, letter * length) for letter in alphabet)
    assert not re.fullmatch(pattern, alphabet[0] * (length + 1))
    assert not re.fullmatch(pattern, alphabet[0] * (length - 1))
    outside = [chr(code) for code in range(ord("0"), ord("Z") + 1)
               if chr(code).isalnum() and chr(code) not in alphabet]
    assert not any(re.fullmatch(pattern, letter * length) for letter in outside)


def test_an_absent_old_log_is_sent_empty(tmp_path):
    """§ 4.2: "" where a file is absent. Breaks when an absent file raises."""
    relay = _Relay()
    folder = tmp_path / "logs"
    _logs(folder, "only\n", None)
    sendlog.send(folder, relay)
    assert _opened(relay.sent[0][2])[2] == ""


def test_a_large_log_sends_its_newest_part(tmp_path):
    """INV-3. Breaks when the oldest part is kept, or the cut is by characters,
    not bytes. Two-byte letters make the two measures differ."""
    relay = _Relay()
    folder = tmp_path / "logs"
    filler = "é" * (log.MAX_BYTES * 6 // 10)    # 1.2 MiB in UTF-8 each
    _logs(folder, f"{OLDEST}\n{filler}\n{NEWEST}\n", f"{OLDEST}\n{filler}\n{NEWEST}\n")
    sendlog.send(folder, relay)
    body = relay.sent[0][2]
    assert len(body) <= sendlog.LARGEST
    _, text, old = _opened(body)
    assert text.endswith(f"{NEWEST}\n")
    assert old.endswith(f"{NEWEST}\n")
    assert OLDEST not in old
    sent = len(text.encode("utf-8")) + len(old.encode("utf-8"))
    assert 2 * 1_048_576 < sent <= 2 * 1_048_576 + 65_536   # only what had to go went


def test_text_that_does_not_compress_still_fits(tmp_path):
    """INV-3. Breaks when TEXT_LARGEST is raised past what LARGEST holds.
    Hashed bytes as base64 barely compress, and a tail of control characters is
    written six bytes each in JSON; the bound covers text that cannot
    compress at all."""
    relay = _Relay()
    folder = tmp_path / "logs"
    noise = base64.b64encode(hashlib.shake_256(b"PRESS-0494").digest(975_000)).decode()
    _logs(folder, noise + "\x01" * 60_000, noise)
    sendlog.send(folder, relay)
    body = relay.sent[0][2]
    print(f"body {len(body):,} bytes of LARGEST {sendlog.LARGEST:,}")
    assert len(body) <= sendlog.LARGEST
    # Text that does not compress at all: zlib's compressBound, plus gzip's
    # 18 bytes of frame, per file; base64's 4 for 3; the tail as JSON.
    text = sendlog.TEXT_LARGEST
    zipped = text + (text >> 12) + (text >> 14) + (text >> 25) + 2 * (13 + 18)
    worst = 4 * (zipped // 3 + 2) + 6 * 60_000 + 1024
    print(f"worst {worst:,} bytes")
    assert worst <= sendlog.LARGEST


@pytest.mark.parametrize("relay", [
    _Relay(status=429), _Relay(status=502), _Relay(status=200, body=b"{}"),
    _Relay(status=200, body=b"not json"), _Relay(status=200, body=b'{"reference": "<b>"}'),
    _Relay(fails=True),
], ids=["429", "502", "no reference", "not json", "a strange reference", "no answer"])
def test_a_refused_send_says_so(tmp_path, relay):
    """INV-4. Breaks when a 429, a 502 or an answer with no reference reads as
    sent."""
    with pytest.raises(sendlog.LogNotSent):
        sendlog.send(tmp_path, relay)
    status, text, _ = _press(tmp_path, relay)
    assert status == 200
    assert "K7Q2MX" not in text
    assert 'class="failure"' in text
    assert face.render_failure(sendlog.LogNotSent("x"), publishing=False).split(
        '<p class="site">')[0] in text


def test_a_sent_log_shows_its_reference(tmp_path):
    """§ 4.1: the box shows the reference. Breaks when the answer drops it."""
    status, text, _ = _press(tmp_path, _Relay())
    assert status == 200
    assert "K7Q2MX" in text
    assert 'class="failure"' not in text


def test_the_send_is_logged_without_the_text(tmp_path):
    """INV-5. Breaks when the note logs the body, before or after the
    reference: the seeded first line is the log's only copy of the text."""
    _, _, own_log = _press(tmp_path, _Relay())
    written = own_log.read_text(encoding="utf-8")
    assert written.startswith(f"{SENTINEL}\n")
    assert written.count(SENTINEL) == 1
    assert "K7Q2MX" in written


def test_failure_pages_and_report_carry_the_button(tmp_path):
    """§ 4.1. Breaks when either page loses the button or its box."""
    fragment = face.render_failure(sendlog.LogNotSent("x"), publishing=False)
    served = face.serve(tmp_path)
    try:
        report.register(served)
        _, _, page = Browser(served).request("GET", "/report")
    finally:
        served.stop()
    for html in (fragment, page):
        assert 'data-action="send-log"' in html
        assert '<dialog class="send-log"' in html
        assert 'data-action="send-log-now"' in html
