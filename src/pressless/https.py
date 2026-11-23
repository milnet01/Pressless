"""The one HTTPS client the parts that reach a web service share.

Each part once held its own copy, and a fix to one was owed to the others
(PRESS-0331). They hold it three ways, so a change to `Client` is checked
against all three. The Publisher and Insights subclass it as their own
`_Urllib`, adding the clock their seam promises, so a test double still
replaces that one name; the GitHub sign-in borrows the Publisher's. Usage
reports, the votes setup and Send my log make a `Client` directly. The Updater keeps its
own: it refuses any redirect off https, and its seam streams a body rather
than returning one (PRESS-0023 § 4.5).

It is not a part of Pressless: it imports no pressless module, so a module
allowed to import it reaches nothing else through it, as safe_write does
(PRESS-0019 INV-1, PRESS-0009 INV-1).

urllib.request rather than a third-party HTTP library (PRESS-0009 § 3
decision 3): PRESS-0022 has to carry every dependency into a packaged
artefact, and a convenience library here would be one bought for syntax.
"""
from __future__ import annotations

import http.client
import select
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
import weakref

import certifi


class NoCrossOriginAuth(urllib.request.HTTPRedirectHandler):
    """A redirect handler that drops the key when the origin changes.

    urllib copies every header but the content ones onto a redirect target,
    a different host included, and follows up to ten hops -- so a redirect
    would hand the Authorization header to whoever answered (PRESS-0052).
    No service this client reaches is expected to redirect across origins;
    a same-origin redirect keeps the header, so a renamed
    repository still resolves for a read. A write is never followed, whatever
    the status: urllib would follow a POST answered 301, 302 or 303 as a GET,
    dropping its body. It returns as its status, which the Publisher reads as
    RepositoryMoved (PRESS-0009 § 6, PRESS-0167).
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.get_method() not in ("GET", "HEAD"):
            return None
        redirected = super().redirect_request(req, fp, code, msg, headers,
                                              newurl)
        if redirected is None:
            return None
        if origin(newurl) != origin(req.full_url):
            redirected.remove_header("Authorization")
            redirected.remove_header("X-goog-api-key")   # PRESS-0081 INV-2
        return redirected


def origin(url: str) -> tuple[str, str]:
    """Scheme, host and port -- the whole origin.

    So a downgrade to cleartext, and a hop to another port on the same
    machine, are both changes of origin. netloc carries the port.
    """
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme, parsed.netloc)


class KeptOpen(urllib.request.HTTPSHandler):
    """HTTPS that keeps a read's connection open for the same thread's next
    read of the same host, so a run of reads pays one handshake rather than
    one each (PRESS-0461). The connection is made with the handler's own
    context, as the stock handler makes it, so the certificate is checked the
    same way. A write, or a request through a proxy, takes the stock path: a
    write is never sent twice, so it is never sent on a connection that may
    have gone stale."""

    def __init__(self, context: ssl.SSLContext) -> None:
        super().__init__(context=context)
        self._verifying = context
        self._held = threading.local()
        self._lock = threading.Lock()
        self._made: list[http.client.HTTPSConnection] = []
        weakref.finalize(self, _close_all, self._made, self._lock)

    def https_open(self, req):
        if req.get_method() not in ("GET", "HEAD") or req.has_proxy():
            return super().https_open(req)
        held = self._held.__dict__.setdefault("by_host", {})
        kept = held.pop(req.host, None)
        if kept is not None and _idle(*kept):
            try:
                response = self._send(kept[0], req)
            except (OSError, http.client.HTTPException) as error:
                # Closed by the server as the read was sent: asked again, once.
                # A silent server is not, so it costs one timeout, not two.
                if any(isinstance(each, TimeoutError)
                       for each in (error, getattr(error, "reason", None))):
                    raise
            else:
                held[req.host] = (kept[0], response)
                return response
        elif kept is not None:
            kept[0].close()
        connection = http.client.HTTPSConnection(req.host, timeout=req.timeout,
                                                 context=self._verifying)
        with self._lock:
            # Closed ones dropped, so a long-lived client holds only its open ones.
            self._made[:] = [each for each in self._made if each.sock is not None]
            self._made.append(connection)
        response = self._send(connection, req)
        held[req.host] = (connection, response)
        return response

    def _send(self, connection: http.client.HTTPSConnection, req):
        """do_open's request without its `Connection: close`."""
        headers = dict(req.unredirected_hdrs)
        headers.update(req.headers)
        headers = {name.title(): value for name, value in headers.items()}
        try:
            try:
                connection.request(req.get_method(), req.selector, req.data, headers)
            except OSError as error:
                raise urllib.error.URLError(error) from None
            response = connection.getresponse()
        except BaseException:
            connection.close()
            raise
        response.url = req.get_full_url()
        response.msg = response.reason
        return response


def _idle(connection: http.client.HTTPSConnection, last) -> bool:
    """Whether `connection` can carry another request: its last answer was
    read to the end, and nothing waits on its socket, which an idle one
    shows only once the server has closed it."""
    if not last.isclosed() or connection.sock is None:
        return False
    try:
        return not select.select([connection.sock], [], [], 0)[0]
    except (OSError, ValueError):
        return False


def _close_all(made: list, lock: threading.Lock) -> None:
    with lock:
        for connection in made:
            connection.close()
        made.clear()


class Client:
    """`request` as every sharing module's seam states it: the status, the
    response headers and the body, with every HTTP status, error statuses
    included, returned rather than raised, and OSError only where no answer
    came. Each caller passes its own timeout. With `keep_alive`, reads reuse
    their connection (`KeptOpen`)."""

    def __init__(self, timeout: float, *, keep_alive: bool = False) -> None:
        self._timeout = timeout
        # Certificates from the bundled certifi set, never the host's store: the
        # AppImage's OpenSSL looks where openSUSE keeps nothing (PRESS-0142).
        context = ssl.create_default_context(cafile=certifi.where())
        handler = (KeptOpen if keep_alive else urllib.request.HTTPSHandler)(context=context)
        self._opener = urllib.request.build_opener(NoCrossOriginAuth, handler)

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]
                ) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(url, data=body, headers=headers,
                                         method=method)
        try:
            with self._opener.open(request,
                                   timeout=self._timeout) as response:
                return (response.status, dict(response.headers),
                        response.read())
        except urllib.error.HTTPError as error:
            # An error STATUS is an answer, so it is returned rather than
            # raised -- only a genuine absence of one reaches the caller as
            # OSError, which is what the seam promises. Its body is read under
            # the same guard as a success's (PRESS-0135).
            answer = error
        except (http.client.HTTPException, ValueError) as error:
            raise no_answer(url, error) from None
        try:
            return (answer.code, dict(answer.headers or {}), answer.read())
        except (http.client.HTTPException, ValueError) as error:
            raise no_answer(url, error) from None


def no_answer(url: str, error: Exception) -> OSError:
    """A missing answer as the seam's OSError (PRESS-0040), naming only the
    host and the type. Neither http.client failure is an OSError, and every
    caller catches only that. Raised `from None`: http.client quotes a refused
    header whole, key included, and a traceback prints every chained cause
    (PRESS-0135).
    """
    return OSError(f"no answer from {urllib.parse.urlsplit(url).netloc} "
                   f"({type(error).__name__})")
