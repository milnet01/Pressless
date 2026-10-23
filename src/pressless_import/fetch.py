"""Fetching the files an export names from the old site (PRESS-0125 § 4.4).

The one module of `pressless_import` that reaches the network, and the
maintainer's `run` never calls it (PRESS-0007 INV-10). An export comes from
anyone, and its addresses are fetched from the user's own computer, so each
host is resolved here, every address it resolves to must be global, and the
connection goes to an address that was checked -- never resolved again,
redirects included. No cookie and no key is ever sent.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from pressless import __version__, builder

from . import Export, ImportStopped, _field, _place

SECONDS = 30                    # without data, a fetch stops (§ 4.4)
_REDIRECTS = 5
_PIECE = 64 * 1024
_MOVED = frozenset({301, 302, 303, 307, 308})
NO_ROOM = "there was no room left on this drive"

Resolve = Callable[[str, int], list[str]]
Connect = Callable[[str, str, int, bool], http.client.HTTPConnection]


def _resolve(host: str, port: int) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


class _Checked(http.client.HTTPSConnection):
    """HTTPS to an address already checked, the certificate checked against
    the host's own name."""

    def __init__(self, address: str, host: str, port: int) -> None:
        # Kept here, not read back from http.client's private _context.
        self._verifying = ssl.create_default_context()
        super().__init__(address, port, timeout=SECONDS, context=self._verifying)
        self._name = host

    def connect(self) -> None:
        self.sock = self._verifying.wrap_socket(
            socket.create_connection((self.host, self.port), timeout=SECONDS),
            server_hostname=self._name)


def _connect(address: str, host: str, port: int, secure: bool) -> http.client.HTTPConnection:
    if secure:
        return _Checked(address, host, port)
    return http.client.HTTPConnection(address, port, timeout=SECONDS)


def _global(address: str) -> bool:
    try:
        found = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(found, "ipv4_mapped", None)
    return (mapped or found).is_global


def fetch(address: str, target: Path, room: Callable[[], int], *,
          resolve: Resolve = _resolve, connect: Connect = _connect) -> str | None:
    """Fetch `address` into `target`: None where it was written, else why not.
    Nothing part-written is left behind."""
    if room() < 0:
        return NO_ROOM
    for _hop in range(_REDIRECTS + 1):
        parts = urlsplit(address)
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            return "its address names no port Pressless can use"
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return "its address is not a web address"
        try:
            found = resolve(parts.hostname, port)
        except OSError:
            return "the old site's name could not be found"
        if not found or not all(_global(one) for one in found):
            return "its address leads inside this computer or its network"
        connection = connect(found[0], parts.hostname, port, parts.scheme == "https")
        try:
            host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
            connection.request("GET", (parts.path or "/") + (f"?{parts.query}" if parts.query
                                                             else ""),
                               headers={"Host": host if parts.port is None
                                        else f"{host}:{parts.port}",
                                        "User-Agent": f"Pressless/{__version__}"})
            answer = connection.getresponse()
            if answer.status in _MOVED:
                moved = answer.getheader("Location")
                if not moved:
                    return f"the old site answered {answer.status} and named no address"
                address = urljoin(address, moved)
                continue
            if answer.status != 200:
                return f"the old site answered {answer.status}"
            return _keep(answer, target, room)
        except TimeoutError:
            return f"the old site sent nothing for {SECONDS} seconds"
        except (OSError, http.client.HTTPException) as exc:
            return f"the connection failed ({type(exc).__name__})"
        finally:
            connection.close()
    return f"the old site redirected it more than {_REDIRECTS} times"


def _keep(answer, target: Path, room: Callable[[], int]) -> str | None:
    """The answer's body into `target`, by a part-file renamed once whole."""
    largest = builder.FILE_LARGEST
    part = target.with_name(f".{target.name}.part")
    written, why = 0, None
    try:
        with open(part, "wb") as out:
            while piece := answer.read(_PIECE):
                written += len(piece)
                if written > largest:
                    why = f"it is larger than the {largest // (1024 * 1024)} MB Pressless keeps"
                    break
                if room() < 0:
                    why = NO_ROOM
                    break
                out.write(piece)
        if why is None:
            part.replace(target)
    finally:
        part.unlink(missing_ok=True)
    return why


def fetch_all(export: Export, media: Path, room: Callable[[], int], *,
              resolve: Resolve = _resolve, connect: Connect = _connect,
              progress: Callable[[int, int], None] | None = None) -> dict[str, str]:
    """Each attachment the export names, fetched from its `attachment_url`
    into `media/<place>` where it is not there already, so a stopped fetch
    resumes. Returns each place not held, with why -- keyed by its full
    address where the attachment has no usable place; a failure never stops
    the rest, and once the drive is full the rest are listed as such."""
    wanted: list[tuple[str, str | None]] = []
    missing: dict[str, str] = {}
    for item in export.channel.findall("item"):
        if _field(item, "post_type", export.ns) != "attachment":
            continue
        address = _field(item, "attachment_url", export.ns)
        try:
            wanted.append((address, _place(item, export.ns)))
        except ImportStopped as exc:
            missing[address] = str(exc)
    full = False
    for done, (address, place) in enumerate(wanted, start=1):
        target = media / place
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            why = NO_ROOM if full else fetch(address, target, room, resolve=resolve,
                                             connect=connect)
            full = full or why == NO_ROOM
            if why is not None:
                missing[place] = why
        if progress is not None:
            progress(done, len(wanted))
    return missing
