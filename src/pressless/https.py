"""The one HTTPS client the Publisher, Insights and usage reports share.

Each of those modules once held its own copy, and a fix to one was owed to
the others (PRESS-0331). Each subclasses `Client` as its own `_Urllib`,
adding the clock its seam promises, so a test double still replaces that one
name. The Updater keeps its own: it refuses any redirect off https, and its
seam streams a body rather than returning one (PRESS-0023 § 4.5).

It is not a part of Pressless: it imports no pressless module, so a module
allowed to import it reaches nothing else through it, as safe_write does
(PRESS-0019 INV-1, PRESS-0009 INV-1).

urllib.request rather than a third-party HTTP library (PRESS-0009 § 3
decision 3): PRESS-0022 has to carry every dependency into a packaged
artefact, and a convenience library here would be one bought for syntax.
"""
from __future__ import annotations

import http.client
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi


class NoCrossOriginAuth(urllib.request.HTTPRedirectHandler):
    """A redirect handler that drops the key when the origin changes.

    urllib copies every header but the content ones onto a redirect target,
    a different host included, and follows up to ten hops -- so a redirect
    would hand the Authorization header to whoever answered (PRESS-0052).
    Neither service Pressless talks to legitimately redirects across
    origins; a same-origin redirect keeps the header, so a renamed
    repository still resolves for a read. A write is not followed: GitHub
    redirects one with 307, which urllib does not follow for POST or PATCH,
    so it returns as status 307 and the Publisher reads it as RepositoryMoved
    (PRESS-0009 § 6, PRESS-0167).
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers,
                                              newurl)
        if redirected is None:
            return None
        if origin(newurl) != origin(req.full_url):
            redirected.remove_header("Authorization")
        return redirected


def origin(url: str) -> tuple[str, str]:
    """Scheme, host and port -- the whole origin.

    So a downgrade to cleartext, and a hop to another port on the same
    machine, are both changes of origin. netloc carries the port.
    """
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme, parsed.netloc)


class Client:
    """`request` as every sharing module's seam states it: the status, the
    response headers and the body, with every HTTP status, error statuses
    included, returned rather than raised, and OSError only where no answer
    came. Each caller passes its own timeout."""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout
        # Certificates from the bundled certifi set, never the host's store: the
        # AppImage's OpenSSL looks where openSUSE keeps nothing (PRESS-0142).
        context = ssl.create_default_context(cafile=certifi.where())
        self._opener = urllib.request.build_opener(
            NoCrossOriginAuth, urllib.request.HTTPSHandler(context=context))

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
