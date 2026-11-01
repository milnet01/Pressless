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

import html
import http.client
import ipaddress
import posixpath
import re
import socket
import ssl
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import certifi

from pressless import __version__, builder

from . import Export, ImportStopped, _field, _place
from ._folder import (
    _CSS,
    _CSS_TOKEN,
    _SCHEME,
    _SCRIPT,
    _SHEET,
    MEMBERS_MOST,
    _attribute_edit,
    _declares_utf8,
    _edited,
    _import_address,
    _new_value,
    _page_text,
    _Paths,
    _quoted,
    _spots,
    _why_not_kept,
)

SECONDS = 30                    # without data, a fetch stops (§ 4.4)
_REDIRECTS = 5
_PIECE = 64 * 1024
_MOVED = frozenset({301, 302, 303, 307, 308})
_URL_SAFE = "/%:@!$&'()*+,;=~"
NO_ROOM = "there was no room left on this drive"
_OUT_OF_THE_SITE = "it redirected out of the site"
_PARENT = "its address climbs out of the site"
_TOO_MANY = "the site holds too many files to bring in whole"
_DEFAULT_PORTS = {"http": 80, "https": 443}
_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.I)
_SITEMAP = "sitemap.xml"
_CRAWL_PART = ".crawl-part"

Resolve = Callable[[str, int], list[str]]
Connect = Callable[[str, str, int, bool], http.client.HTTPConnection]


def _resolve(host: str, port: int) -> list[str]:
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
          resolve: Resolve = _resolve, connect: Connect = _connect,
          within: Callable[[str], bool] | None = None,
          answered: list[tuple[str, str]] | None = None) -> str | None:
    """Fetch `address` into `target`: None where it was written, else why not.
    Nothing part-written is left behind. With `within`, a hop it refuses is not
    made; `answered` gains the address that answered, and its content type."""
    if room() < 0:
        return NO_ROOM
    for _hop in range(_REDIRECTS + 1):
        if within is not None and not within(address):
            return _OUT_OF_THE_SITE
        parts = urlsplit(address)
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            return "its address names no port Pressless can use"
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return "its address is not a web address"
        try:
            found = resolve(parts.hostname, port)
        except (OSError, UnicodeError):
            # getaddrinfo raises UnicodeError for an empty or over-long label
            return "the old site's name could not be found"
        if not found or not all(_global(one) for one in found):
            return "its address leads inside this computer or its network"
        connection = connect(found[0], parts.hostname, port, parts.scheme == "https")
        try:
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
                    return f"the old site answered {answer.status} and named no address"
                address = urljoin(address, moved)
                continue
            if answer.status != 200:
                return f"the old site answered {answer.status}"
            if answered is not None:
                answered.append((address, answer.getheader("Content-Type") or ""))
            return _keep(answer, target, room)
        except TimeoutError:
            return f"the old site sent nothing for {SECONDS} seconds"
        except (OSError, http.client.HTTPException, UnicodeError) as exc:
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


# ------------------------------------------------------- PRESS-0333 § 4.2 ----


@dataclass(frozen=True)
class Crawled:
    left: tuple[tuple[str, str], ...]  # (address's path, why it was not kept)


class _Site:
    """What counts as the site at `address`, and where its addresses land."""

    def __init__(self, address: str) -> None:
        parts = urlsplit(address)
        self.scheme, self.netloc = parts.scheme, parts.netloc
        self.host = self._host(parts)
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
        parts = urlsplit(address)
        path = parts.path or "/"
        return (parts.scheme in _DEFAULT_PORTS and self._host(parts) == self.host
                and (path.startswith(self.base) or f"{path}/" == self.base))

    def asked(self, address: str) -> str:
        """The address to fetch: this site's scheme, no query and no fragment."""
        return urlunsplit((self.scheme, self.netloc, urlsplit(address).path or "/", "", ""))

    def path(self, address: str) -> str:
        """The address's path below the site, decoded."""
        return unquote((urlsplit(address).path or "/").removeprefix(self.base.rstrip("/"))
                       ).removeprefix("/")


def _landing(path: str, kind: str) -> str:
    """§ 4.2: the file an answer to `path` lands at, given its content type."""
    if not path or path.endswith("/"):
        return f"{path}index.html"
    if not posixpath.splitext(path)[1] and kind.split(";")[0].strip().lower() == "text/html":
        return f"{path}.html"
    return path


def _css_through(css: str, write: Callable[[str, bool], str | None]) -> str:
    """Each url() and @import in `css` through `write`, a None leaving it."""
    def token(found: re.Match) -> str:
        whole = found.group(0)
        if found.group("import"):
            address = _import_address(found)
        else:
            address = found.group("u1") or found.group("u2") or found.group("u3")
        if not address:
            return whole
        new = write(address, False)
        if new is None:
            return whole
        at = whole.index(address)
        return whole[:at] + new + whole[at + len(address):]
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
                 resolve: Resolve, connect: Connect) -> None:
        self.site, self.start = _Site(address), address
        self.into, self.room, self.resolve, self.connect = into, room, resolve, connect
        self.part = into.parent / _CRAWL_PART
        self.waiting: deque[str] = deque()
        self.seen: set[str] = set()
        self.landed: dict[str, str] = {}     # the asked address -> the path it landed at
        self.urls: dict[str, str] = {}       # a text file's path -> the address it came from
        self.taken = _Paths()
        self.left: list[tuple[str, str]] = []

    def note(self, address: str, base: str) -> None:
        """`address`, read on the page at `base`, waits its turn if it is the site's."""
        address = address.strip()
        if not address or address[0] == "#" or (_SCHEME.match(address)
                                                and not address.lower().startswith("http")):
            return
        joined = urljoin(base, address)
        if not self.site.holds(joined):
            return
        asked = self.site.asked(joined)
        if asked not in self.seen:
            self.seen.add(asked)
            self.waiting.append(asked)

    def get(self, asked: str) -> tuple[str | None, str, str]:
        """Fetch `asked` to the part file: why not, what answered, and its type."""
        answered: list[tuple[str, str]] = []
        why = fetch(asked, self.part, self.room, resolve=self.resolve, connect=self.connect,
                    within=self.site.holds, answered=answered)
        final, kind = answered[0] if answered else (asked, "")
        return why, final, kind

    def take(self, asked: str) -> bool:
        """One address: fetch it, land it, and note what it names. False where it
        could not be read."""
        path = self.site.path(asked)
        if ".." in path.split("/"):
            self.left.append((path, _PARENT))
            return False
        if len(self.urls) >= MEMBERS_MOST:
            self.left.append((path, _TOO_MANY))
            return False
        why, final, kind = self.get(asked)
        if why is not None:
            self.left.append((path, why))
            return False
        final = self.site.asked(final)
        self.seen.add(final)
        landing = _landing(self.site.path(final), kind)
        if final in self.landed:
            self.landed[asked] = self.landed[final]
            self.part.unlink(missing_ok=True)
            return True
        why = _why_not_kept(landing, self.part.stat().st_size, self.taken)
        if why is not None:
            self.left.append((landing, why))
            self.part.unlink(missing_ok=True)
            return False
        target = self.into / landing
        target.parent.mkdir(parents=True, exist_ok=True)
        self.part.replace(target)
        self.landed[asked] = self.landed[final] = landing
        self.urls[landing] = final
        self._read(landing, final, target)
        return True

    def _read(self, landing: str, final: str, target: Path) -> None:
        def noted(address: str, _image: bool) -> None:
            self.note(address, final)
        if landing.lower().endswith((".html", ".htm")):
            read = _page_text(target.read_bytes())
            if read is not None:
                _page_through(read[0], noted)
        elif landing.lower().endswith(".css"):
            _css_through(target.read_bytes().decode("utf-8", "replace"), noted)

    def sitemap(self) -> None:
        """The pages `sitemap.xml` names, where it answers. It is not kept."""
        why, _final, _kind = self.get(urljoin(self.site.asked(self.start), _SITEMAP))
        if why is not None:
            return
        text = self.part.read_bytes().decode("utf-8", "replace")
        self.part.unlink(missing_ok=True)
        for found in _LOC.finditer(text):
            address = html.unescape(found.group(1))
            if not address.lower().endswith(".xml"):
                self.note(address, self.start)

    def written(self, address: str, base: str) -> str | None:
        """§ 4.2's rewrite: the site's own full or root address names where it landed;
        a root address that is not the site's becomes full. Others stay."""
        stripped = address.strip()
        if not stripped or stripped[0] in "#?" or (
                _SCHEME.match(stripped) and not stripped.lower().startswith("http")):
            return None
        full = bool(_SCHEME.match(stripped)) or stripped.startswith("//")
        if not full and not stripped.startswith("/"):
            return None
        joined = urljoin(base, stripped)
        if not self.site.holds(joined):
            return None if full else urlunsplit(
                (self.site.scheme, self.site.netloc, *urlsplit(joined)[2:]))
        split = urlsplit(joined)
        place = self.landed.get(self.site.asked(joined), self.site.path(joined))
        tail = (f"?{split.query}" if split.query else "") + (
            f"#{split.fragment}" if split.fragment else "")
        return f"/{quote(place)}{tail}"

    def rewrite(self) -> None:
        """When the crawl ends, as only then is it known where an address lands."""
        for landing, url in self.urls.items():
            target = self.into / landing
            def write(address: str, _image: bool, url: str = url) -> str | None:
                return self.written(address, url)
            if landing.lower().endswith((".html", ".htm")):
                read = _page_text(target.read_bytes())
                if read is not None:
                    new = _page_through(read[0], write)
                    if new != read[0]:
                        target.write_text(_declares_utf8(new) if read[1] else new,
                                          encoding="utf-8", newline="")
            elif landing.lower().endswith(".css"):
                text = target.read_bytes().decode("utf-8", "replace")
                new = _css_through(text, write)
                if new != text:
                    target.write_text(new, encoding="utf-8", newline="")


def fetch_site(address: str, into: Path, room: Callable[[], int], *,
               resolve: Resolve | None = None, connect: Connect | None = None) -> Crawled:
    """§ 4.2: the live site at `address`, laid out at `into`. An `address` it cannot
    read ends the crawl with nothing kept. Each check `fetch` makes applies to every
    hop, so a host resolving inside the network is never reached."""
    into.mkdir(parents=True, exist_ok=True)
    # Read from the module when called, so a test can stand in for the network.
    crawl = _Crawl(address, into, room, resolve or _resolve, connect or _connect)
    try:
        first = crawl.site.asked(address)
        crawl.seen.add(first)
        if not crawl.take(first):
            return Crawled(tuple(crawl.left))
        crawl.sitemap()
        while crawl.waiting:
            crawl.take(crawl.waiting.popleft())
        crawl.rewrite()
    finally:
        crawl.part.unlink(missing_ok=True)
    return Crawled(tuple(crawl.left))
