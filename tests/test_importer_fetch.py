# INV-3 and INV-4 for PRESS-0125 (the Import anyone runs): what a fetch from
# the old site may reach, and what it sends. No network: every fetch goes
# through a fake resolver and a recording connection, so the test sees each
# address asked for and each request made.
#
# Why this exists: docs/specs/PRESS-0125-wordpress-import.md § 4.4. An export
# comes from anyone, and its addresses are fetched from the user's own
# computer, so an address naming the user's router, a cloud's metadata
# service or the computer itself must be refused before a connection opens.
#
# Every host is .example.org, and every global address a public resolver's.
from __future__ import annotations

from pathlib import Path

import pytest

from pressless import __version__, builder
from pressless_import import fetch

GLOBAL = "8.8.4.4"


class _Answer:
    def __init__(self, status: int, body: bytes = b"", headers: dict | None = None):
        self.status = status
        self._body = body
        self._headers = headers or {}

    def getheader(self, name, default=None):
        return self._headers.get(name, default)

    def read(self, size=-1):
        piece, self._body = (self._body, b"") if size < 0 else (self._body[:size],
                                                                 self._body[size:])
        return piece


class _Network:
    """A resolver and a connection maker, answering by host and path, and
    recording every connection and request."""

    def __init__(self, hosts: dict[str, list[str]], answers: dict[str, _Answer]):
        self.hosts = hosts
        self.answers = answers
        self.connected: list[tuple[str, str, int, bool]] = []
        self.requests: list[tuple[str, str, dict]] = []

    def resolve(self, host, port):
        return list(self.hosts.get(host, []))

    def connect(self, address, host, port, secure):
        self.connected.append((address, host, port, secure))
        network = self

        class Connection:
            def request(self, method, path, headers):
                network.requests.append((method, path, dict(headers)))
                self._path = f"{host}{path}"

            def getresponse(self):
                return network.answers[self._path]

            def close(self):
                pass

        return Connection()


def _fetch(network: _Network, address: str, tmp_path: Path, room=lambda: 10**12):
    target = tmp_path / "media" / "2012" / "05" / "a.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    why = fetch.fetch(address, target, room, resolve=network.resolve,
                      connect=network.connect)
    return why, target


def test_a_fetch_writes_what_the_old_site_answers(tmp_path):
    network = _Network({"old.example.org": [GLOBAL]},
                       {"old.example.org/wp-content/uploads/2012/05/a.jpg": _Answer(200, b"jpeg")})
    why, target = _fetch(network, "https://old.example.org/wp-content/uploads/2012/05/a.jpg",
                         tmp_path)
    assert why is None and target.read_bytes() == b"jpeg"
    assert network.connected == [(GLOBAL, "old.example.org", 443, True)], (
        "the connection goes to the address the resolver gave, never resolved again"
    )



def test_a_non_ascii_path_is_sent_quoted_and_an_escaped_one_unchanged(tmp_path):
    # http.client refuses a request line that is not ASCII, and the export's
    # attachment_url may carry raw Unicode.
    network = _Network({"old.example.org": [GLOBAL]},
                       {"old.example.org/a/%D1%84.jpg": _Answer(200, b"jpeg"),
                        "old.example.org/b/%D1%84.jpg?x=%20": _Answer(200, b"jpeg")})
    assert _fetch(network, "https://old.example.org/a/ф.jpg", tmp_path)[0] is None
    assert _fetch(network, "https://old.example.org/b/%D1%84.jpg?x=%20", tmp_path)[0] is None


def test_a_name_the_resolver_cannot_encode_is_a_failure_not_a_crash(tmp_path):
    def resolve(host, port):
        raise UnicodeError("label empty or too long")

    target = tmp_path / "a.jpg"
    why = fetch.fetch("https://exa..mple.org/a.jpg", target, lambda: 10**12,
                      resolve=resolve, connect=_Network({}, {}).connect)
    assert why == "the old site's name could not be found"

@pytest.mark.parametrize("answer", [["127.0.0.1"], ["10.0.0.1"], ["169.254.169.254"],
                                    [GLOBAL, "127.0.0.1"], ["::1"], ["::ffff:127.0.0.1"]])
def test_a_fetch_to_an_address_that_is_not_global_is_refused(tmp_path, answer):
    """INV-3: unless EVERY address the host resolves to is global, nothing is
    opened -- a resolver whose second answer is the computer itself included.

    Breaks when only the first answer, or no answer, is checked."""
    network = _Network({"old.example.org": answer}, {})
    why, target = _fetch(network, "http://old.example.org/wp-content/uploads/2012/05/a.jpg",
                         tmp_path)
    assert why and not target.exists()
    assert network.connected == [], f"no connection opens to a refused address: {answer}"


@pytest.mark.parametrize("address", ["file:///etc/passwd", "ftp://old.example.org/a.jpg",
                                     "gopher://old.example.org/a.jpg", "http:///a.jpg"])
def test_only_an_http_or_https_address_is_fetched(tmp_path, address):
    network = _Network({"old.example.org": [GLOBAL]}, {})
    why, _target = _fetch(network, address, tmp_path)
    assert why and network.connected == []


def test_each_redirect_is_checked_as_the_first_hop_is(tmp_path):
    """INV-3: a redirect from a global host to a private one is refused, and
    the second connection never opens.

    Breaks when only the first hop is checked."""
    network = _Network(
        {"old.example.org": [GLOBAL], "inside.example.org": ["127.0.0.1"]},
        {"old.example.org/a.jpg": _Answer(302, headers={
            "Location": "http://inside.example.org/secret"})})
    why, target = _fetch(network, "http://old.example.org/a.jpg", tmp_path)
    assert why and not target.exists()
    assert [host for _address, host, _port, _secure in network.connected] == [
        "old.example.org"], network.connected


def test_a_sixth_redirect_is_refused(tmp_path):
    answers = {f"old.example.org/{n}": _Answer(301, headers={"Location": f"/{n + 1}"})
               for n in range(10)}
    network = _Network({"old.example.org": [GLOBAL]}, answers)
    why, _target = _fetch(network, "http://old.example.org/0", tmp_path)
    assert why and len(network.connected) == 6, "the first hop and five redirects"


def test_a_fetch_sends_no_credentials(tmp_path):
    """INV-4: no cookie and no Authorization header, not even from an
    address carrying a user name and password; the User-Agent names Pressless.

    Breaks when a shared opener carrying the GitHub key is reused."""
    network = _Network({"old.example.org": [GLOBAL]},
                       {"old.example.org/a.jpg": _Answer(200, b"jpeg")})
    why, _target = _fetch(network, "https://someone:secret@old.example.org/a.jpg", tmp_path)
    assert why is None
    ((method, path, headers),) = network.requests
    named = {name.lower() for name in headers}
    assert not named & {"cookie", "authorization", "proxy-authorization"}, headers
    assert headers["User-Agent"] == f"Pressless/{__version__}"
    assert headers["Host"] == "old.example.org" and (method, path) == ("GET", "/a.jpg")


def test_an_answer_other_than_ok_is_named(tmp_path):
    network = _Network({"old.example.org": [GLOBAL]},
                       {"old.example.org/a.jpg": _Answer(404)})
    why, target = _fetch(network, "http://old.example.org/a.jpg", tmp_path)
    assert "404" in why and not target.exists()


def test_a_file_past_the_largest_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "FILE_LARGEST", 8)
    network = _Network({"old.example.org": [GLOBAL]},
                       {"old.example.org/a.jpg": _Answer(200, b"x" * 9)})
    why, target = _fetch(network, "http://old.example.org/a.jpg", tmp_path)
    assert why and not target.exists()
    assert not list(target.parent.iterdir()), "nothing part-written is left behind"


def test_no_fetch_starts_without_room(tmp_path):
    network = _Network({"old.example.org": [GLOBAL]},
                       {"old.example.org/a.jpg": _Answer(200, b"jpeg")})
    why, target = _fetch(network, "http://old.example.org/a.jpg", tmp_path, room=lambda: -1)
    assert why == fetch.NO_ROOM and network.connected == [] and not target.exists()


def test_fetching_an_export_resumes_and_lists_what_failed(tmp_path):
    """§ 4.4: each attachment goes to media/<place>; a file already there is
    not fetched again, so a stopped fetch resumes; a failure is listed by its
    place and never stops the rest."""
    from test_importer import _export, _item

    import pressless_import

    export = tmp_path / "export.xml"
    export.write_text(_export(
        _item(1, kind="attachment", status="inherit", attachment="2012/05/held.jpg"),
        _item(2, kind="attachment", status="inherit", attachment="2012/05/gone.jpg"),
        _item(3, kind="attachment", status="inherit", attachment="2012/06/new.jpg"),
    ), encoding="utf-8")
    media = tmp_path / "media"
    (media / "2012" / "05").mkdir(parents=True)
    (media / "2012" / "05" / "held.jpg").write_bytes(b"already here")
    base = "old.example.org/wp-content/uploads"
    network = _Network({"old.example.org": [GLOBAL]},
                       {f"{base}/2012/05/gone.jpg": _Answer(404),
                        f"{base}/2012/06/new.jpg": _Answer(200, b"new")})
    seen = []

    missing = fetch.fetch_all(pressless_import.read(export), media, lambda: 10**12,
                              resolve=network.resolve, connect=network.connect,
                              progress=lambda done, total: seen.append((done, total)))

    assert set(missing) == {"2012/05/gone.jpg"} and "404" in missing["2012/05/gone.jpg"]
    assert (media / "2012" / "06" / "new.jpg").read_bytes() == b"new"
    assert (media / "2012" / "05" / "held.jpg").read_bytes() == b"already here"
    assert len(network.requests) == 2, "the held file is not fetched again"
    assert seen[-1] == (3, 3), seen


def test_a_place_a_folder_cannot_hold_is_never_fetched(tmp_path):
    """§ 4.4: a place is checked as `_photographs` checks it. A decoded
    backslash is a separator on Windows, so `..%5C` would climb out of the
    media folder there; it is listed and nothing is fetched."""
    from test_importer import _export, _item

    import pressless_import

    export = tmp_path / "export.xml"
    export.write_text(_export(_item(1, kind="attachment", status="inherit",
                                    attachment="2012/05/..%5C..%5Cescape.jpg")),
                      encoding="utf-8")
    network = _Network({"old.example.org": [GLOBAL]}, {})
    missing = fetch.fetch_all(pressless_import.read(export), tmp_path / "media",
                              lambda: 10**12, resolve=network.resolve,
                              connect=network.connect)
    assert len(missing) == 1 and network.connected == [], missing


def test_a_checked_connection_wraps_with_its_own_verifying_context(monkeypatch):
    """PRESS-0323: `_Checked` keeps the context it made, rather than reading
    `http.client`'s private `_context`, so a Python that keeps it elsewhere
    still verifies the certificate against the host's own name."""
    import socket
    import ssl

    wrapped: list[tuple[ssl.SSLContext, str]] = []
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket",
                        lambda context, sock, server_hostname: wrapped.append(
                            (context, server_hostname)) or sock)
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: object())
    connection = fetch._Checked(GLOBAL, "old.example.org", 443)
    connection._context = None    # what a Python keeping it elsewhere leaves
    connection.connect()
    assert len(wrapped) == 1, wrapped
    context, name = wrapped[0]
    assert name == "old.example.org"
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
