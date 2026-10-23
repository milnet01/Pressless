"""The shared HTTPS client (PRESS-0331): its redirect policy, and that it
reaches no other part of Pressless.

Each sharing module's own tests check that its client carries this handler,
passes its timeout and maps a broken reply to OSError. These ask the handler
directly, so none of them opens a socket.
"""
from __future__ import annotations

import ast
import inspect
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
