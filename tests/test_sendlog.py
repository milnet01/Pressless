"""PRESS-0436: Send my log posts the two log files to the relay, only when
Send is pressed, and nothing else.

The relay's address and the log's file names are written out here rather than
imported, so a module posting elsewhere, or sending other files, fails.
"""
from __future__ import annotations

import json
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
               if "sendlog.send(" in path.read_text(encoding="utf-8")]
    assert callers == []


def test_the_body_is_the_logs_and_nothing_else(tmp_path):
    """INV-2. Breaks when a key is added, or the folder's path is put in."""
    relay = _Relay()
    folder = tmp_path / "logs"
    _logs(folder, f"{NEWEST}\n", f"{OLDEST}\n")
    assert sendlog.send(folder, relay) == "K7Q2MX"
    [(method, url, body, headers)] = relay.sent
    assert (method, url) == ("POST", RELAY)
    assert headers["Content-Type"] == "application/json"
    sent = json.loads(body)
    assert sent == {"version": __version__, "system": usage.system()[:128],
                    "log": f"{NEWEST}\n", "old": f"{OLDEST}\n"}
    assert str(tmp_path) not in body.decode("utf-8")


def test_an_absent_old_log_is_sent_empty(tmp_path):
    """§ 4.2: "" where a file is absent. Breaks when an absent file raises."""
    relay = _Relay()
    folder = tmp_path / "logs"
    _logs(folder, "only\n", None)
    sendlog.send(folder, relay)
    assert json.loads(relay.sent[0][2])["old"] == ""


def test_a_large_log_sends_its_newest_part(tmp_path):
    """INV-3. Breaks when the oldest part is kept, or the cut is by characters,
    not bytes. Two-byte letters make the two measures differ."""
    relay = _Relay()
    folder = tmp_path / "logs"
    filler = "é" * (log.MAX_BYTES * 6 // 10)    # 1.2 MiB in UTF-8 each
    _logs(folder, f"{OLDEST}\n{filler}\n{NEWEST}\n", f"{OLDEST}\n{filler}\n{NEWEST}\n")
    sendlog.send(folder, relay)
    body = relay.sent[0][2]
    assert len(body) <= 2 * 1_048_576 + 65_536
    sent = json.loads(body)
    assert sent["log"].endswith(f"{NEWEST}\n")
    assert sent["old"].endswith(f"{NEWEST}\n")
    assert OLDEST not in sent["old"]
    assert len(body) > 2 * 1_048_576       # only what had to go went


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
    """INV-5. Breaks when the note logs the body."""
    _, _, own_log = _press(tmp_path, _Relay())
    written = own_log.read_text(encoding="utf-8")
    after = written.split(f"{SENTINEL} older\n")[-1].split(f"{SENTINEL}\n", 1)[-1]
    assert "K7Q2MX" in after
    assert SENTINEL not in after


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
