"""The shared HTTPS client (PRESS-0331): its redirect policy, and that it
reaches no other part of Pressless.

Each sharing module's own tests check that its client carries this handler,
passes its timeout and maps a broken reply to OSError. These ask the handler
directly, so none of them opens a network connection; the kept-connection
tests (PRESS-0461) stand a recording double in for http.client's.
"""
from __future__ import annotations

import ast
import http.client
import inspect
import io
import socket
import ssl
import threading
import urllib.request

import pytest

from pressless import https


def _authorised_request(url):
    return urllib.request.Request(  # noqa: S310 -- literal url, below
        url,
        headers={"Authorization": "Bearer THE-PUBLISHING-KEY",
                 "Accept": "application/json"},
        method="GET",
    )


def test_a_cross_origin_redirect_drops_the_key():
    """PRESS-0052: the Authorization header does not follow a redirect to
    another origin.

    urllib's own handler copies every header but the content ones onto the
    target, a different host included, and follows up to ten hops -- so a
    redirect would hand the key to whoever answered.

    Breaks when an implementer takes urllib's default redirect handling,
    which is what this module did until PRESS-0052. Nothing about the code
    looked wrong, because the leak is in the library's behaviour rather
    than in anything the module writes.
    """
    handler = https.NoCrossOriginAuth()
    original = _authorised_request("https://api.github.com/a/b")

    redirected = handler.redirect_request(
        original, None, 302, "Found", {}, "https://elsewhere.example/x"
    )

    carried = dict(redirected.headers)
    assert 'THE-PUBLISHING-KEY' not in str(carried), (
        f"the key followed the redirect: {carried!r}"
    )
    assert carried.get("Accept") is not None, (
        f"only the Authorization header should be dropped, but the "
        f"ordinary headers went with it: {carried!r}"
    )


def test_a_same_origin_redirect_keeps_the_key():
    """PRESS-0052: a redirect that stays on the same origin keeps the
    header, so an endpoint that answers with a 301 still resolves.

    Breaks when an implementer refuses every redirect, or strips the header
    unconditionally. Both close the hole, both break the ordinary case, and
    a test asserting only the cross-origin half passes against either.
    """
    handler = https.NoCrossOriginAuth()
    original = _authorised_request("https://api.github.com/a/b")

    redirected = handler.redirect_request(
        original, None, 301, "Moved", {}, "https://api.github.com/c/d"
    )

    assert redirected.headers.get("Authorization") == "Bearer THE-PUBLISHING-KEY", (
        f"a same-origin redirect lost the header: "
        f"{dict(redirected.headers)!r}"
    )


@pytest.mark.parametrize("target, what", [
    ("http://api.github.com/a/b", "a downgrade to cleartext http"),
    ("https://api.github.com:8443/a/b", "a hop to another port"),
])
def test_a_same_host_change_of_origin_drops_the_key(target, what):
    """PRESS-0052: the origin is scheme, host AND port, so the same host
    reached another way is still somewhere else.

    Breaks when an implementer compares hostnames alone. The header would
    then ride a cleartext hop, or reach a different service on the same
    machine -- in both cases to a host that reads as the right one.
    """
    handler = https.NoCrossOriginAuth()
    original = _authorised_request("https://api.github.com/a/b")

    redirected = handler.redirect_request(
        original, None, 302, "Found", {}, target
    )

    assert "Authorization" not in dict(redirected.headers), (
        f"the header survived {what}: {dict(redirected.headers)!r}"
    )


def test_https_imports_no_pressless_module():
    """PRESS-0009 INV-1 and PRESS-0019 INV-1 let the Publisher and Insights
    import this module because it imports no pressless module itself, so no
    route to Credentials runs through it.

    Breaks when the shared client imports a part of Pressless -- settings,
    say, for a timeout -- and hands both modules a route their own import
    walks cannot see.
    """
    found = set()
    for node in ast.walk(ast.parse(inspect.getsource(https))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." if node.level else (node.module or "").split(".")[0])
    assert not found & {"pressless", "."}, sorted(found)


# ----------------------------------------------------------- PRESS-0461 ----


class _Wire:
    """A socket's read side holding one answer, for http.client.HTTPResponse."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def makefile(self, mode):
        return io.BytesIO(self._data)


class _Connection:
    """http.client.HTTPSConnection as KeptOpen and the stock handler use it,
    recording what each is made with and sent. Its socket is one end of a
    real pair, so the handler can ask whether anything waits on it."""

    made: list[_Connection] = []
    debuglevel = 0
    failing: type[BaseException] | None = None     # raised by the next reused send

    def __init__(self, host, timeout=None, context=None, **_):
        self.host, self.timeout, self.context = host, timeout, context
        self.sent: list[tuple[str, str, dict]] = []
        self.sock, self.far = socket.socketpair()
        _Connection.made.append(self)

    def set_debuglevel(self, level):
        pass

    def request(self, method, selector, body=None, headers=None, **_):
        if self.sent and _Connection.failing is not None:
            failing, _Connection.failing = _Connection.failing, None
            raise failing()
        self.sent.append((method, selector, dict(headers or {})))

    def getresponse(self):
        answer = http.client.HTTPResponse(
            _Wire(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"))
        answer.begin()
        return answer

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        self.far.close()


@pytest.fixture
def connections(monkeypatch):
    _Connection.made = []
    _Connection.failing = None
    monkeypatch.setattr(http.client, "HTTPSConnection", _Connection)
    yield _Connection.made
    for each in _Connection.made:
        each.close()


def _get(client, path="/a"):
    return client.request("GET", f"https://api.example.org{path}", None, {})


def test_reads_from_one_thread_share_one_connection(connections):
    """PRESS-0461: a run of reads pays one handshake. Breaks when KeptOpen
    makes a connection per read, or sends urllib's `Connection: close`."""
    client = https.Client(5.0, keep_alive=True)
    assert _get(client, "/a")[2] == b"ok"
    assert _get(client, "/b")[2] == b"ok"
    assert len(connections) == 1
    assert [selector for _m, selector, _h in connections[0].sent] == ["/a", "/b"]
    assert all("Connection" not in headers for *_rest, headers in connections[0].sent)


def test_a_kept_connection_checks_certificates_as_a_write_s_does(connections):
    """PRESS-0461: a reused connection is made with the client's own
    verifying context, the one the stock handler hands a write. Breaks when
    KeptOpen builds a context of its own, or none."""
    client = https.Client(5.0, keep_alive=True)
    _get(client)
    client.request("POST", "https://api.example.org/w", b"{}", {})
    read, write = connections
    assert read.context is write.context
    assert read.context.verify_mode == ssl.CERT_REQUIRED and read.context.check_hostname


def test_a_write_never_rides_a_kept_connection(connections):
    """PRESS-0461: a write is never sent twice, so it never goes on a
    connection that may have gone stale. Breaks when KeptOpen keeps writes."""
    client = https.Client(5.0, keep_alive=True)
    _get(client)
    client.request("POST", "https://api.example.org/w", b"{}", {})
    _get(client, "/b")
    assert len(connections) == 2
    assert connections[1].sent[0][2].get("Connection") == "close"
    assert [selector for _m, selector, _h in connections[0].sent] == ["/a", "/b"]


def test_a_connection_the_server_closed_is_not_reused(connections):
    """PRESS-0461: an idle connection with something waiting on it has been
    closed by the server. Breaks when KeptOpen skips its idle check."""
    client = https.Client(5.0, keep_alive=True)
    _get(client)
    connections[0].far.close()          # the server hangs up while it sits idle
    _get(client, "/b")
    assert len(connections) == 2
    assert connections[1].sent[0][1] == "/b"


def test_a_read_cut_off_on_a_kept_connection_is_asked_again(connections):
    """PRESS-0461: a server may close a kept connection as a read is sent; a
    read is safe to ask again, once, on a new connection. A timeout is not
    asked again, so a silent server costs one timeout. Breaks when the retry
    goes, or takes a timeout too."""
    client = https.Client(5.0, keep_alive=True)
    _get(client)
    _Connection.failing = http.client.RemoteDisconnected
    assert _get(client, "/b")[2] == b"ok"
    assert len(connections) == 2

    _Connection.failing = TimeoutError
    with pytest.raises(OSError):
        _get(client, "/c")
    assert len(connections) == 2


def test_each_thread_reads_on_its_own_connection(connections):
    """PRESS-0461: a fetch reads from several threads at once, and an
    http.client connection carries one request at a time. Breaks when the
    kept connections are shared across threads."""
    client = https.Client(5.0, keep_alive=True)
    _get(client)
    other = threading.Thread(target=_get, args=(client, "/b"))
    other.start()
    other.join()
    assert len(connections) == 2
