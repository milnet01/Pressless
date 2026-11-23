"""Fetching the files an export names from the old site (PRESS-0125 § 4.4), and
downloading a live site by following its links (PRESS-0333 § 4.2).

The one module of `pressless_import` that reaches the network, and the
maintainer's `run` never calls it (PRESS-0007 INV-10). An export comes from
anyone, and its addresses are fetched from the user's own computer, so each
host is resolved here, every address it resolves to must be global, and the
connection goes to an address that was checked -- never resolved again,
redirects included. No cookie and no key is ever sent.
"""
from __future__ import annotations

import errno
import html
import http.client
import ipaddress
import posixpath
import re
import socket
import ssl
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import certifi

from pressless import __version__, blocks, builder, os_reason
from pressless.progress import count as count_progress
from pressless.words import say

from . import Export, ImportStopped, _field, _place
from ._folder import (
    _CSS,
    _CSS_TOKEN,
    _PAGE_SUFFIXES,
    _SCHEME,
    _SCRIPT,
    _SHEET,
    MEMBERS_MOST,
    _attribute_edit,
    _declares_utf8,
    _decoded,
    _edited,
    _new_value,
    _page_text,
    _Paths,
    _quoted,
    _spots,
    _token_address,
    _token_with,
    _web_slashes,
    _why_not_kept,
)

SECONDS = 30                    # without data, a fetch stops (§ 4.4)
LONGEST = 30 * 60               # a fetch still sending after this stops too
_REDIRECTS = 5
# Files fetched at once (PRESS-0461). Each is its own fetch, checked hop by hop
# on its own connection as one alone is. Four is what a browser's six per host
# stays well under, so an old site's host is not asked for more than a reader
# would ask; a fetch streams to disk, so each costs one piece of memory.
FETCHES_AT_ONCE = 4
_PIECE = 64 * 1024
_MOVED = frozenset({301, 302, 303, 307, 308})
_URL_SAFE = "/%:@!$&'()*+,;=~"
# Why a file was not fetched: words keys, said where the reason is made.
NO_ROOM = "import.fetch.why.no_room"
TOO_SLOW = "import.fetch.why.too_slow"
_NOT_FOUND = "import.fetch.why.not_found"
_NOT_WEB = "import.fetch.why.not_web"
_OUT_OF_THE_SITE = "import.fetch.why.out_of_the_site"
_PARENT = "import.fetch.why.parent"
_TOO_MANY = "import.fetch.why.too_many"
_DEFAULT_PORTS = {"http": 80, "https": 443}
_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.I)
_SITEMAP = "sitemap.xml"
_CRAWL_PART = ".crawl-part"
# Addresses a crawl asks for at most, those that fail included, so a site of
# broken links cannot keep it fetching without end.
_ASKED_MOST = 2 * MEMBERS_MOST

Resolve = Callable[[str, int], list[str]]
Connect = Callable[[str, str, int, bool], http.client.HTTPConnection]
_clock = time.monotonic


def addresses(host: str, port: int) -> list[str]:
    """The addresses `host` resolves to: the resolver `fetch` uses when handed none,
    and the domain wizard's (PRESS-0222)."""
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


class _Checked(http.client.HTTPSConnection):
    """HTTPS to an address already checked, the certificate checked against
    the host's own name and the bundled certifi set, never the host's store
    (PRESS-0142)."""

    def __init__(self, address: str, host: str, port: int) -> None:
        # Kept here, not read back from http.client's private _context.
        self._verifying = ssl.create_default_context(cafile=certifi.where())
        super().__init__(address, port, timeout=SECONDS, context=self._verifying)
        self._name = host

    def connect(self) -> None:
        # Held as `sock` before the handshake, so _Deadline can cut a server
        # that drips the handshake too.
        self.sock = self._verifying.wrap_socket(
            socket.create_connection((self.host, self.port), timeout=SECONDS),
            server_hostname=self._name, do_handshake_on_connect=False)
        self.sock.do_handshake()


def _connect(address: str, host: str, port: int, secure: bool) -> http.client.HTTPConnection:
    if secure:
        return _Checked(address, host, port)
    return http.client.HTTPConnection(address, port, timeout=SECONDS)


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _global(address: str) -> bool:
    """Whether `address` is global, and so is every IPv4 address it carries:
    IPv4-mapped, 6to4, Teredo, or NAT64's, which a gateway reaches for it."""
    try:
        found = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if not found.is_global:
        return False
    if found.version == 4:
        return True
    carried = [found.ipv4_mapped, found.sixtofour, *(found.teredo or ())]
    if found in _NAT64:
        carried.append(ipaddress.IPv4Address(int(found) & 0xFFFFFFFF))
    return all(one.is_global for one in carried if one is not None)


class _Deadline:
    """Cuts a connection once its fetch has run LONGEST in all (§ 4.4). A
    socket's timeout counts only a silence, so a server sending a byte now and
    then, headers or handshake included, would otherwise hold a fetch for days."""

    def __init__(self, connection: http.client.HTTPConnection, ends: float) -> None:
        self.cut = False
        self._connection = connection
        self._timer = threading.Timer(max(0.0, ends - _clock()), self._cut)
        self._timer.daemon = True
        self._timer.start()

    def _cut(self) -> None:
        self.cut = True
        sock = getattr(self._connection, "sock", None)
        if sock is not None:
            try:
                # The plain socket's own shutdown, which wakes a read blocked
                # in another thread; an SSL socket's would unwrap it first.
                socket.socket.shutdown(sock, socket.SHUT_RDWR)
            except OSError:
                pass

    def stop(self) -> None:
        self._timer.cancel()


def _not_written(exc: OSError) -> str | None:
    """Why a write on this computer failed, or None where `exc` came from
    the network: a file's own error names the file, and a full drive says
    ENOSPC on every system."""
    if exc.errno == errno.ENOSPC:
        return say(NO_ROOM)
    if exc.filename is not None:
        return say("import.folder.why.unwritable", why=os_reason.of(exc))
    return None


def _not_made(exc: OSError | ValueError) -> str:
    """Why a file's place on this computer could not be made. Python refuses a
    path past Windows's 32,767-character limit with a ValueError, before
    asking the system (PRESS-0385)."""
    if isinstance(exc, ValueError):
        return say("import.folder.why.too_long")
    return _not_written(exc) or say("import.folder.why.unwritable", why=os_reason.of(exc))


def _failed(exc: Exception) -> str:
    return say("import.fetch.why.connection", what=type(exc).__name__)


def fetch(address: str, target: Path, room: Callable[[], int], *,
          resolve: Resolve | None = None, connect: Connect | None = None,
          within: Callable[[str], bool] | None = None,
          answered: list[tuple[str, str]] | None = None) -> str | None:
    """Fetch `address` into `target`: None where it was written, else why not.
    Nothing part-written is left behind. With `within`, a hop it refuses is not
    made; `answered` gains the address that answered, and its content type.
    `resolve` and `connect` are read from the module when called, so a test
    can stand in for the network."""
    resolve, connect = resolve or addresses, connect or _connect
    if room() < 0:
        return say(NO_ROOM)
    ends = _clock() + LONGEST       # for every hop together
    for _hop in range(_REDIRECTS + 1):
        if within is not None and not within(address):
            return say(_OUT_OF_THE_SITE)
        try:
            parts = urlsplit(address)
        except ValueError:      # an address no parser can read, as `http://[x/`
            return say(_NOT_WEB)
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            return say("import.fetch.why.port")
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return say(_NOT_WEB)
        try:
            found = resolve(parts.hostname, port)
        except (OSError, UnicodeError):
            # getaddrinfo raises UnicodeError for an empty or over-long label
            return say(_NOT_FOUND)
        if not found:
            return say(_NOT_FOUND)
        if not all(_global(one) for one in found):
            return say("import.fetch.why.inside")
        connection = deadline = None
        try:
            # Inside the try: making the TLS context reads the certificate
            # bundle, and its failure is this file's, never the whole fetch's.
            connection = connect(found[0], parts.hostname, port, parts.scheme == "https")
            deadline = _Deadline(connection, ends)
            host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
            # http.client sends the request line as ASCII, and an export's
            # attachment_url can carry raw Unicode; quoting leaves an
            # already-escaped address as it was.
            path = quote(parts.path or "/", safe=_URL_SAFE)
            query = quote(parts.query, safe=_URL_SAFE + "?")
            connection.request("GET", path + (f"?{query}" if query else ""),
                               headers={"Host": host if parts.port is None
                                        else f"{host}:{parts.port}",
                                        "User-Agent": f"Pressless/{__version__}"})
            answer = connection.getresponse()
            if answer.status in _MOVED:
                moved = answer.getheader("Location")
                if not moved:
                    return say("import.fetch.why.moved_nowhere", status=str(answer.status))
                address = urljoin(address, moved)
                continue
            if answer.status != 200:
                return say("import.fetch.why.answered", status=str(answer.status))
            if answered is not None:
                answered.append((address, answer.getheader("Content-Type") or ""))
            return _keep(answer, target, room, ends, deadline)
        except (OSError, http.client.HTTPException, ValueError) as exc:
            if deadline is not None and deadline.cut:
                return _too_slow()
            if isinstance(exc, TimeoutError):
                return say("import.fetch.why.silent", seconds=str(SECONDS))
            return (isinstance(exc, OSError) and _not_written(exc)) or _failed(exc)
        finally:
            if deadline is not None:
                deadline.stop()
            if connection is not None:
                connection.close()
    return say("import.fetch.why.redirects", most=str(_REDIRECTS))


def _too_slow() -> str:
    return say(TOO_SLOW, minutes=str(LONGEST // 60))


def _keep(answer, target: Path, room: Callable[[], int], ends: float,
          deadline: _Deadline) -> str | None:
    """The answer's body into `target`, by a part-file renamed once whole."""
    largest = builder.FILE_LARGEST
    part = target.with_name(f".{target.name}.part")
    written, why = 0, None
    try:
        out = open(part, "wb")  # noqa: SIM115 -- closed below
    except ValueError as exc:   # past Windows's whole-path limit (PRESS-0385)
        return _not_made(exc)
    try:
        with out:
            while piece := answer.read(_PIECE):
                written += len(piece)
                if written > largest:
                    why = say("import.folder.why.large", **builder.largest_slots())
                    break
                if room() < 0:
                    why = say(NO_ROOM)
                    break
                if _clock() > ends:
                    why = _too_slow()
                    break
                out.write(piece)
        if why is None and deadline.cut:
            why = _too_slow()
        elif why is None and getattr(answer, "length", None):
            # http.client ends a body cut short by the server as if it were whole.
            why = say("import.fetch.why.cut_short")
        if why is None:
            part.replace(target)
    finally:
        part.unlink(missing_ok=True)
    return why


def fetch_all(export: Export, media: Path, room: Callable[[], int], *,
              resolve: Resolve | None = None, connect: Connect | None = None,
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
        except ValueError:      # an address no parser can read, as `http://[x]/`
            missing[address] = say(_NOT_WEB)
    no_room = say(NO_ROOM)
    full = threading.Event()

    def get(address: str, place: str) -> str | None:
        target = media / place
        if target.is_file():
            return None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            return _not_made(exc)
        why = no_room if full.is_set() else fetch(address, target, room, resolve=resolve,
                                                  connect=connect)
        if why == no_room:
            full.set()
        return why

    def get_each(items: list[tuple[str, str]]) -> list[tuple[str, str | None]]:
        # One place's addresses in turn, as one at a time took them: a later
        # one is fetched only where an earlier one left no file.
        return [(place, get(address, place)) for address, place in items]

    # Places one name apart only in case are one file on Windows, so they go
    # to the same fetcher and never write one part file from two.
    by_place: dict[str, list[tuple[str, str]]] = {}
    for address, place in wanted:
        by_place.setdefault(place.casefold(), []).append((address, place))
    done = 0
    with ThreadPoolExecutor(FETCHES_AT_ONCE, thread_name_prefix="import-fetch") as pool:
        for answers in pool.map(get_each, by_place.values()):
            for place, why in answers:
                if why is not None:
                    missing[place] = why
                done += 1
                if progress is not None:
                    progress(done, len(wanted))
    return missing


# ------------------------------------------------------- PRESS-0333 § 4.2 ----


@dataclass(frozen=True)
class Crawled:
    left: tuple[tuple[str, str], ...]  # (address's path, why it was not kept)


class _Site:
    """What counts as the site at `address`, and where its addresses land."""

    def __init__(self, address: str) -> None:
        parts = urlsplit(address)
        self.scheme, self.netloc = parts.scheme, parts.netloc
        self.host_and_port = self._host(parts)
        self.base = parts.path if parts.path.endswith("/") else f"{parts.path}/"

    @staticmethod
    def _host(parts) -> tuple[str, int | None]:
        """The host and port, a scheme's default port counting as none."""
        try:
            port = parts.port
        except ValueError:
            port = -1
        return (parts.hostname or "").casefold(), (
            None if port == _DEFAULT_PORTS.get(parts.scheme) else port)

    def holds(self, address: str) -> bool:
        try:
            parts = urlsplit(address)
        except ValueError:      # an address no parser can read, as `http://[x/`
            return False
        path = parts.path or "/"
        return (parts.scheme in _DEFAULT_PORTS and self._host(parts) == self.host_and_port
                and (path.startswith(self.base) or f"{path}/" == self.base))

    def asked(self, address: str) -> str:
        """The address to fetch: this site's scheme, no query and no fragment."""
        return urlunsplit((self.scheme, self.netloc, urlsplit(address).path or "/", "", ""))

    def path(self, address: str) -> str:
        """The address's path below the site, decoded."""
        return unquote((urlsplit(address).path or "/").removeprefix(self.base.rstrip("/"))
                       ).removeprefix("/")


def _followed(address: str) -> str | None:
    """`address` as the crawl reads it, stripped and a backslash in its path a
    slash; None for one it neither follows nor rewrites: empty, a fragment or
    query alone, which name the page it is on, or another scheme's."""
    address = _web_slashes(address.strip())
    scheme = _SCHEME.match(address)
    if not address or address[0] in "#?" or (
            scheme and scheme.group(0)[:-1].lower() not in _DEFAULT_PORTS):
        return None
    return address


def _landing(path: str, kind: str) -> str:
    """§ 4.2: the file an answer to `path` lands at, given its content type."""
    if not path or path.endswith("/"):
        return f"{path}index.html"
    if not posixpath.splitext(path)[1] and kind.split(";")[0].strip().lower() == "text/html":
        return f"{path}.html"
    return path


def _base(text: str, address: str) -> str:
    """The address a page's own addresses are read against: its first `<base
    href>`, read against `address`, as the HTML standard says, else `address`."""
    for event in blocks._scan(text):
        if event.tag == "base" and event.kind in ("start", "startend"):
            href = dict(event.attrs).get("href")
            if href is not None:
                try:
                    return urljoin(address, href.strip())
                except ValueError:
                    return address
    return address


def _is_page(landing: str) -> bool:
    return landing.casefold().endswith(_PAGE_SUFFIXES)


def _css_through(css: str, write: Callable[[str, bool], str | None]) -> str:
    """Each url() and @import in `css` through `write`, a None leaving it."""
    def token(found: re.Match) -> str:
        address = _token_address(found)
        new = write(address, False) if address else None
        return found.group(0) if new is None else _token_with(found, new)
    return _CSS_TOKEN.sub(token, css)


def _page_through(text: str, write: Callable[[str, bool], str | None]) -> str:
    """Each address in a page through `write`, in every place `_spots` finds one."""
    edits: list[tuple[int, int, str]] = []
    for spot in _spots(text):
        if spot.kind in (_SHEET, _SCRIPT):
            new = write(spot.value, False)
            if new is not None:
                edits.append(_attribute_edit(text, spot, new))
        elif spot.kind == _CSS:
            new = _css_through(spot.value, write)
            if new != spot.value:
                edits.append((spot.start, spot.end, new if spot.tag == "style"
                               else _quoted(new, spot.quote)))
        else:
            new = _new_value(spot, write)
            if new is not None:
                edits.append((spot.start, spot.end, _quoted(new, spot.quote)))
    return _edited(text, edits)


class _Crawl:
    """One download: what is waiting, what landed, and what was left."""

    def __init__(self, address: str, into: Path, room: Callable[[], int],
                 resolve: Resolve | None, connect: Connect | None) -> None:
        self.site, self.start = _Site(address), address
        self.into, self.room, self.resolve, self.connect = into, room, resolve, connect
        self.part = into.parent / _CRAWL_PART
        # One part file for each fetch at once (PRESS-0461).
        self.parts = [self.part.with_name(f"{_CRAWL_PART}-{each}")
                      for each in range(FETCHES_AT_ONCE)]
        self.waiting: deque[str] = deque()
        self.seen: set[str] = set()
        self.landed: dict[str, str] = {}     # the asked address -> the path it landed at
        # Every landed file's path, pictures too -> the address it came from;
        # MEMBERS_MOST counts it.
        self.urls: dict[str, str] = {}
        self.taken = _Paths()
        self.left: list[tuple[str, str]] = []
        self.size = 0                       # bytes landed, for PRESS-0435's count
        self.asked = 0                      # fetches made, _ASKED_MOST at most

    def note(self, address: str, base: str) -> None:
        """`address`, read on the page at `base`, waits its turn if it is the site's."""
        address = _followed(address)
        if address is None:
            return
        try:
            joined = urljoin(base, address)
        except ValueError:
            return
        if not self.site.holds(joined):
            return
        asked = self.site.asked(joined)
        if asked not in self.seen:
            self.seen.add(asked)
            self.waiting.append(asked)

    def get(self, asked: str, part: Path | None = None) -> tuple[str | None, str, str]:
        """Fetch `asked` to a part file: why not, what answered, and its type."""
        answered: list[tuple[str, str]] = []
        why = fetch(asked, part or self.part, self.room, resolve=self.resolve,
                    connect=self.connect, within=self.site.holds, answered=answered)
        final, kind = answered[0] if answered else (asked, "")
        return why, final, kind

    def _climbs(self, asked: str) -> bool:
        return ".." in self.site.path(asked).split("/")

    def take(self, asked: str) -> bool:
        """One address: fetch it, land it, and note what it names. False where it
        could not be read."""
        path = self.site.path(asked)
        if self._climbs(asked):
            self.left.append((path, say(_PARENT)))
            return False
        if len(self.urls) >= MEMBERS_MOST or self.asked >= _ASKED_MOST:
            self.left.append((path, say(_TOO_MANY)))
            return False
        self.asked += 1
        return self._land(asked, *self.get(asked), self.part)

    def take_some(self, pool: ThreadPoolExecutor) -> None:
        """The next waiting addresses, up to FETCHES_AT_ONCE, fetched together and
        landed in turn, so what lands, what is left and the order of both are as
        `take` one at a time gives. Near either limit, one at a time."""
        some = min(FETCHES_AT_ONCE, len(self.waiting))
        if (some == 1 or len(self.urls) + some >= MEMBERS_MOST
                or self.asked + some >= _ASKED_MOST):
            self.take(self.waiting.popleft())
            return
        batch = [self.waiting.popleft() for _ in range(some)]
        fetched = [asked for asked in batch if not self._climbs(asked)]
        self.asked += len(fetched)
        parts = dict(zip(fetched, self.parts, strict=False))
        got = dict(zip(fetched, pool.map(lambda asked: self.get(asked, parts[asked]),
                                         fetched), strict=True))
        for asked in batch:
            if asked in got:
                self._land(asked, *got[asked], parts[asked])
            else:
                self.left.append((self.site.path(asked), say(_PARENT)))

    def _land(self, asked: str, why: str | None, final: str, kind: str, part: Path) -> bool:
        """What `get` brought to `part`, landed, and what it names noted."""
        path = self.site.path(asked)
        if why is not None:
            self.left.append((path, why))
            return False
        final = self.site.asked(final)
        self.seen.add(final)
        landing = _landing(self.site.path(final), kind)
        if final in self.landed or landing in self.urls:
            # A second address for one file, as `/` and `/index.html`.
            self.landed[asked] = self.landed.get(final, landing)
            part.unlink(missing_ok=True)
            return True
        size = part.stat().st_size
        why = _why_not_kept(landing, size, self.taken)
        if why is not None:
            self.left.append((landing, why))
            part.unlink(missing_ok=True)
            return False
        target = self.into / landing
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            part.replace(target)
        except (OSError, ValueError) as exc:
            # A whole path longer than the system holds, as Windows' 260 characters.
            self.left.append((landing, _not_made(exc)))
            part.unlink(missing_ok=True)
            return False
        self.taken.take(landing)
        self.landed[asked] = self.landed[final] = landing
        self.urls[landing] = final
        self.size += size
        count_progress("progress.downloading", len(self.urls), None, self.size)
        try:
            self._read(landing, final, target)
        except OSError:
            pass    # it landed; what it names is not followed
        return True

    def _read(self, landing: str, final: str, target: Path) -> None:
        if _is_page(landing):
            text = _page_text(target.read_bytes())[0]
            base = _base(text, final)
            _page_through(text, lambda address, _image: self.note(address, base))
        elif landing.casefold().endswith(".css"):
            text = _decoded(target.read_bytes())[0]
            _css_through(text, lambda address, _image: self.note(address, final))

    def sitemap(self) -> None:
        """The pages `sitemap.xml` names, where it answers. It is not kept."""
        why, _final, _kind = self.get(
            f"{self.site.scheme}://{self.site.netloc}{self.site.base}{_SITEMAP}")
        if why is not None:
            return
        text = self.part.read_bytes().decode("utf-8", "replace")
        self.part.unlink(missing_ok=True)
        for found in _LOC.finditer(text):
            address = html.unescape(found.group(1))
            if not address.lower().endswith(".xml"):
                self.note(address, self.start)

    def written(self, address: str, base: str) -> str | None:
        """§ 4.2's rewrite: the site's own full or root address names where it landed, as
        does a relative one landing elsewhere than it says; one with no host that is not
        the site's becomes full. Others stay."""
        stripped = _followed(address)
        if stripped is None:
            return None
        full = bool(_SCHEME.match(stripped)) or stripped.startswith("//")
        try:
            joined = urljoin(base, stripped)
        except ValueError:
            return None
        if not self.site.holds(joined):
            return None if full else urlunsplit(
                (self.site.scheme, self.site.netloc, *urlsplit(joined)[2:]))
        split = urlsplit(joined)
        place = self.landed.get(self.site.asked(joined), self.site.path(joined))
        if not full and not stripped.startswith("/") and place == self.site.path(joined):
            return None
        tail = (f"?{split.query}" if split.query else "") + (
            f"#{split.fragment}" if split.fragment else "")
        return f"/{quote(place)}{tail}"

    def rewrite(self) -> None:
        """When the crawl ends, as only then is it known where an address lands.
        A file this computer cannot rewrite is `left`, never half-written."""
        for landing, url in self.urls.items():
            target = self.into / landing
            try:
                new = self._rewritten(landing, url, target.read_bytes())
                if new is not None:
                    part = target.with_name(f".{target.name}.rewrite")
                    try:
                        part.write_text(new, encoding="utf-8", newline="")
                        part.replace(target)
                    finally:
                        part.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                self.left.append((landing, _not_made(exc)))
                target.unlink(missing_ok=True)

    def _rewritten(self, landing: str, url: str, data: bytes) -> str | None:
        """The file's text with § 4.2's addresses rewritten, as UTF-8, which
        reading it as a folder tries first; None where nothing changes."""
        if _is_page(landing):
            read = _page_text(data)
            base = _base(read[0], url)
            new = _page_through(read[0], lambda address, _image: self.written(address, base))
            return None if new == read[0] else _declares_utf8(new) if read[1] else new
        if landing.casefold().endswith(".css"):
            read = _decoded(data)
            new = _css_through(read[0], lambda address, _image: self.written(address, url))
            return None if new == read[0] else new
        return None


def fetch_site(address: str, into: Path, room: Callable[[], int], *,
               resolve: Resolve | None = None, connect: Connect | None = None) -> Crawled:
    """§ 4.2: the live site at `address`, laid out at `into`. An `address` it cannot
    read ends the crawl with nothing kept. Each check `fetch` makes applies to every
    hop, so a host resolving inside the network is never reached."""
    into.mkdir(parents=True, exist_ok=True)
    crawl = _Crawl(address, into, room, resolve, connect)
    count_progress("progress.downloading", 0, None, 0)     # PRESS-0435 § 4.2
    try:
        first = crawl.site.asked(address)
        crawl.seen.add(first)
        if not crawl.take(first):
            return Crawled(tuple(crawl.left))
        crawl.sitemap()
        with ThreadPoolExecutor(FETCHES_AT_ONCE, thread_name_prefix="crawl") as pool:
            while crawl.waiting:
                crawl.take_some(pool)
        crawl.rewrite()
    finally:
        for part in (crawl.part, *crawl.parts):
            part.unlink(missing_ok=True)
    return Crawled(tuple(crawl.left))
