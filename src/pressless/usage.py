"""Usage reports, sent only when the user says yes (PRESS-0262).

The contract is docs/specs/PRESS-0262-usage-reports.md. With the user's yes,
each event in EVENTS goes to a Google Analytics property kept for Pressless
alone: which screens are opened, where setup stops, how presses end and what
fails. Every value sent is one Pressless chose -- a path it registered, a name
in its code, a class name -- never the user's writing, names, addresses or
paths. The last reports sent are kept on this computer, word for word, and
the Usage reports screen lists them.

The fourth module that may reach the network (§ 5 INV-9). Nothing waits for a
report: each goes on a thread of its own, and a failure is one log line.
"""
from __future__ import annotations

import html
import json
import platform
import secrets
import ssl
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import certifi

from pressless import __version__, safe_write, settings
from pressless.words import say

if TYPE_CHECKING:
    from pressless import insights
    from pressless.face import Face, Request

try:
    from pressless._usage_key import API_SECRET, MEASUREMENT_ID
except ImportError:  # a development checkout, before write_usage_key.py runs
    API_SECRET = MEASUREMENT_ID = ""

FILE_NAME = "usage.json"         # in Pressless's own folder
SENT_NAME = "usage-sent.json"    # the last reports sent, newest last
KEPT = 50                        # how many SENT_NAME holds
ADDRESS = "/usage"
ENDPOINT = "https://region1.google-analytics.com/mp/collect"
VERSION = 1
TIMEOUT_SECONDS = 5
_LONGEST = 100                   # a longer value is cut to this many characters

EVENTS: Mapping[str, tuple[str, ...]] = {
    "screen":      ("screen",),
    "wizard_step": ("wizard", "step"),
    "wizard_done": ("wizard",),
    "press":       ("kind", "ended"),
    "failure":     ("error", "screen", "publishing"),
}
COMMON = ("app_version", "system", "session_id", "engagement_time_msec")

# What `register` keeps. _LOCK also orders writes to SENT_NAME.
_LOCK = threading.Lock()
_folder: Path | None = None
_transport: insights.Transport | None = None


def _unregistered(text: str) -> None:
    """The log before `register`: nothing reaches it, since nothing is sent."""


_note: Callable[[str], None] = _unregistered
_session = 0


def can_send() -> bool:
    """Whether this build carries the property's key."""
    return bool(MEASUREMENT_ID) and bool(API_SECRET)


def _record(folder: Path) -> dict | None:
    """usage.json's record; None where it is absent, {} where it is unusable."""
    try:
        text = (folder / FILE_NAME).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return {}
    try:
        record = json.loads(text)
    except ValueError:
        return {}
    if (not isinstance(record, dict) or record.get("version") != VERSION
            or not isinstance(record.get("yes"), bool)):
        return {}
    return record


def answer(folder: Path) -> bool | None:
    """The user's answer; None where they were never asked, False where the
    file cannot be read or is malformed (§ 4.2)."""
    record = _record(Path(folder))
    if record is None:
        return None
    return record.get("yes", False)


def set_answer(folder: Path, yes: bool) -> None:
    """Record the answer. A yes gets a new client id; a no forgets the client
    and the reports sent. Raises OSError where it cannot be written."""
    folder = Path(folder)
    client = uuid.uuid4().hex if yes else None
    with _LOCK:
        safe_write.write_whole(
            folder / FILE_NAME,
            json.dumps({"version": VERSION, "yes": yes, "client": client}) + "\n",
            prefix=".usage-")
        if not yes:
            (folder / SENT_NAME).unlink(missing_ok=True)


def system() -> str:
    """The system, plainly: "Windows 11", or "Linux (openSUSE Tumbleweed)"."""
    name = platform.system()
    if name == "Windows":
        return f"Windows {platform.release()}"
    if name == "Linux":
        try:
            pretty = platform.freedesktop_os_release().get("PRETTY_NAME")
        except OSError:
            pretty = None
        return f"Linux ({pretty})" if pretty else "Linux"
    return name or "an unknown system"


def sent(folder: Path) -> list[dict]:
    """The reports sent, oldest first; [] where there are none or the file
    cannot be read."""
    try:
        bodies = json.loads((Path(folder) / SENT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [body for body in bodies if isinstance(body, dict)] if isinstance(bodies, list) else []


def report(name: str, **params: str) -> None:
    """Send event `name` with `params`, its names in EVENTS, where the user
    said yes. Raises ValueError for an unknown name or a wrong parameter,
    whatever the answer, so a bad call fails in every test (§ 4.4)."""
    fields = EVENTS.get(name)
    if fields is None:
        raise ValueError(f"no usage event is named {name!r}")
    if set(params) != set(fields):
        raise ValueError(f"{name} takes {sorted(fields)}, not {sorted(params)}")
    if not all(isinstance(value, str) for value in params.values()):
        raise ValueError(f"{name}'s values must be strings")
    with _LOCK:
        folder, transport, note, session = _folder, _transport, _note, _session
    if folder is None or transport is None or not can_send():
        return
    record = _record(folder)
    client = record.get("client") if record else None
    if not (record and record.get("yes") is True and isinstance(client, str) and client):
        return
    body = {"client_id": client, "events": [{"name": name, "params": {
        **{key: value[:_LONGEST] for key, value in params.items()},
        "app_version": __version__[:_LONGEST],
        "system": system()[:_LONGEST],
        "session_id": session,
        "engagement_time_msec": 1,
    }}]}
    try:
        with _LOCK:
            kept = (sent(folder) + [body])[-KEPT:]
            safe_write.write_whole(folder / SENT_NAME, json.dumps(kept, indent=1) + "\n",
                                   prefix=".usage-sent-")
    except OSError as exc:
        # Unlisted is unsent: the user can read every report that went.
        note(f"usage report {name} not sent: {type(exc).__name__}")
        return
    query = urllib.parse.urlencode({"measurement_id": MEASUREMENT_ID, "api_secret": API_SECRET})
    data = json.dumps(body).encode("utf-8")
    threading.Thread(target=_send, args=(transport, f"{ENDPOINT}?{query}", data, name, note),
                     name="pressless-usage", daemon=True).start()


def _send(transport: insights.Transport, url: str, data: bytes, name: str,
          note: Callable[[str], None]) -> None:
    """One report. The answer is ignored; a failure is one log line naming the
    event and the failure's type, never the address, which holds the key."""
    try:
        transport.request("POST", url, data, {"Content-Type": "application/json"})
    except Exception as exc:  # noqa: BLE001 -- nothing a report does may reach the user
        note(f"usage report {name} not sent: {type(exc).__name__}")


class _Opener:
    """The module's own client, built as insights._Urllib builds its own:
    certifi's certificates and a timeout. Built on its first request, so a
    missing certificate file is that report's failure, on its thread."""

    def __init__(self) -> None:
        self._opener: urllib.request.OpenerDirector | None = None

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        if self._opener is None:
            context = ssl.create_default_context(cafile=certifi.where())
            self._opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
        # The address is ENDPOINT's, https, fixed above.
        request = urllib.request.Request(url, data=body, headers=headers,  # noqa: S310
                                         method=method)
        with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, dict(response.headers), response.read()

    def now(self) -> float:
        return time.time()


def register(face: Face, folder: Path, *,
             transport: insights.Transport | None = None) -> None:
    """Keep `folder`, Pressless's own folder, and the transport for `report`;
    add the Usage reports screen and, for a current user never asked, the
    question above the list at /."""
    global _folder, _transport, _note, _session
    folder = Path(folder)
    with _LOCK:
        _folder = folder
        _transport = transport if transport is not None else _Opener()
        _note = face.note
        _session = 1 + secrets.randbelow(2**31 - 1)   # one per start of Pressless

    def screen(request: Request) -> str:
        return _screen(folder)

    def yes(request: Request) -> str:
        return _choose(face, folder, True)

    def no(request: Request) -> str:
        return _choose(face, folder, False)

    face.add_page("GET", ADDRESS, screen)
    face.add_page("POST", f"{ADDRESS}/yes", yes)
    face.add_page("POST", f"{ADDRESS}/no", no)
    face.add_to_list(lambda: _question(face, folder), above=True)


def _question(face: Face, folder: Path) -> str:
    """§ 4.3: asked once, above the list, of a user set up before reports
    existed. Recorded as no before it shows, so leaving it is no."""
    if not can_send() or answer(folder) is not None:
        return ""
    try:
        settings.load(folder)
    except (settings.NotSetUp, settings.SettingsError):
        return ""
    try:
        set_answer(folder, False)
    except OSError as exc:
        face.note(f"the usage-report answer could not be saved: {type(exc).__name__}")
        return ""
    return (f'<section class="card" id="usage-question"><h2>{say("usage.title")}</h2>'
            f'<p>{say("usage.explain")}</p>'
            f'<form method="post" action="{ADDRESS}/yes"><p>'
            f'<button>{say("usage.yes")}</button> '
            f'<button formmethod="get" formaction="/">{say("usage.no")}</button>'
            "</p></form></section>")


def _choose(face: Face, folder: Path, yes: bool) -> str:
    if not can_send():
        return _screen(folder)
    try:
        set_answer(folder, yes)
    except OSError as exc:
        return face.fail(exc, publishing=False) + _screen(folder)
    return _screen(folder)


def _screen(folder: Path) -> str:
    """The Usage reports screen: whether reports are on, the one switch, and
    every report kept, newest first, as it was sent."""
    head = f'<h1>{say("usage.title")}</h1>'
    if not can_send():
        return head + f'<p>{say("usage.unavailable")}</p>'
    on = answer(folder) is True
    switch = (f'<form method="post" action="{ADDRESS}/{"no" if on else "yes"}"><p>'
              f'<button>{say("usage.turn_off" if on else "usage.turn_on")}</button></p></form>')
    bodies = sent(folder) if on else []
    listed = ("".join(f"<li><pre>{html.escape(json.dumps(body, indent=1))}</pre></li>"
                      for body in reversed(bodies))
              if bodies else "")
    return (head + f'<p>{say("usage.explain")}</p>'
            f'<p id="usage-state">{say("usage.on" if on else "usage.off")}</p>' + switch
            + f'<section class="card"><h2>{say("usage.sent")}</h2>'
            + (f"<ol>{listed}</ol>" if listed else f'<p>{say("usage.none_sent")}</p>')
            + "</section>")
