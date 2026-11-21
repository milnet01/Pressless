"""Send my log (PRESS-0436): the two log files, sent privately to the
developer through a relay, once the user presses Send in a box saying what
goes and where.

The relay files them in a private repository and answers a short reference.
Pressless holds no key the relay checks: one shipped in a public app is no
key (§ 3 decision 6). Nothing here runs until POST /log/send is pressed.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pressless import __version__, https, log, usage
from pressless.publisher import PublishError
from pressless.words import say

if TYPE_CHECKING:
    from pressless.face import Face

ADDRESS = "/log/send"
# Public, not a secret: anyone may post a log to it, within its limits.
RELAY = "https://pressless-logs.pressless-logs.workers.dev/log"
LARGEST = 2 * log.MAX_BYTES + 65_536
TIMEOUT_SECONDS = 60.0
_SYSTEM_LONGEST = 128               # the relay refuses a longer one
_REFERENCE = re.compile(r"[A-HJ-NP-Z2-9]{6}")


class LogNotSent(PublishError):
    """The relay did not take the log, or could not be reached."""


class Transport(Protocol):
    """`https.Client.request`: every HTTP status returned, OSError where no answer came."""

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]: ...


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _newest(text: str, drop: int) -> str:
    """`text` without its first `drop` bytes, cut on a whole character."""
    return text.encode("utf-8")[drop:].decode("utf-8", errors="ignore")


def _body(folder: Path) -> bytes:
    """The request body, at most LARGEST bytes. Over that, the old file loses
    its oldest part first, then the current one."""
    fields = {"version": __version__, "system": usage.system()[:_SYSTEM_LONGEST],
              "log": _read(folder / log.FILE_NAME), "old": _read(folder / log.OLD_NAME)}
    while True:
        body = json.dumps(fields, ensure_ascii=False).encode("utf-8")
        over = len(body) - LARGEST
        if over <= 0:
            return body
        # JSON never writes a byte shorter than the text holds it, so each
        # cut removes at least `over`; it ends within three rounds.
        fields["old" if fields["old"] else "log"] = _newest(
            fields["old"] or fields["log"], over)


def send(folder: Path, client: Transport | None = None) -> str:
    """Post both logs in `folder`; the reference the relay answers. Raises
    LogNotSent where the relay is not reached or does not take them."""
    client = client or https.Client(TIMEOUT_SECONDS)
    try:
        status, _, answer = client.request(
            "POST", RELAY, _body(folder),
            {"Content-Type": "application/json", "User-Agent": f"Pressless/{__version__}"})
    except OSError as error:
        raise LogNotSent(str(error)) from None
    if status != 200:
        raise LogNotSent(f"the log relay answered {status}")
    try:
        reference = json.loads(answer)["reference"]
    except (ValueError, KeyError, TypeError):
        reference = None
    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        raise LogNotSent("the log relay's answer held no reference")
    return reference


def button() -> str:
    """Send my log and its box, for a failure page and Report a problem. The
    Face's script opens the box; only its Send posts anything (INV-8)."""
    return (
        '<div class="send-log"><p><button type="button" data-action="send-log">'
        f'{say("sendlog.button")}</button></p>'
        '<dialog class="send-log"><div class="said">'
        f'<p>{say("sendlog.what")}</p><p>{say("sendlog.holds")}</p><p>{say("sendlog.where")}</p>'
        '</div><p><button type="button" data-action="send-log-now">'
        f'{say("sendlog.send")}</button> '
        f'<button type="button" data-close>{say("sendlog.not_now")}</button>'
        "</p></dialog></div>"
    )


def register(face: Face, folder: Path, *, client: Transport | None = None) -> None:
    """Add POST /log/send to `face`, sending the logs in `folder`."""
    from pressless.face import Reply  # face imports this module

    def pressed(request: object) -> Reply:
        try:
            reference = send(Path(folder), client)
        except LogNotSent as failure:
            said = face.fail(failure, publishing=False)
        else:
            face.note(f"log sent to the developer as {reference}")
            said = f'<p>{say("sendlog.sent", reference=html.escape(reference))}</p>'
        return Reply(said.encode("utf-8"), "text/html; charset=utf-8")

    face.add_page("POST", ADDRESS, pressed)
