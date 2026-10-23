"""Every network client verifies certificates against the bundled set (PRESS-0142).

Measured with the released v0.1.2 AppImage on openSUSE: its OpenSSL looks for
certificates in /usr/lib/ssl, which that system does not have, so Setup's
check against GitHub answered "could not reach GitHub" where source answered
401. Naming /etc/ssl/ca-bundle.pem made the same AppImage get its 401. So each
client builds its TLS context from certifi, which rides inside the bundle,
rather than from wherever the host keeps its roots.
"""
from __future__ import annotations

import ssl
import urllib.request

import certifi

from pressless import insights, publisher, updater


def test_every_client_verifies_against_the_bundled_certificates(monkeypatch):
    """Breaks when a client falls back to urllib's default context, which
    reads the host's store."""
    made: list[tuple[object, ssl.SSLContext]] = []
    real = ssl.create_default_context

    def recording(*args, **kwargs):
        context = real(*args, **kwargs)
        made.append((kwargs.get("cafile"), context))
        return context

    monkeypatch.setattr(ssl, "create_default_context", recording)
    for module in (publisher, insights, updater):
        made.clear()
        opener = module._Urllib()._opener
        https = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPSHandler)]
        assert https, module.__name__
        assert [cafile for cafile, _ in made] == [certifi.where()], (module.__name__, made)
        assert any(h._context is made[0][1] for h in https), (
            f"{module.__name__} built the context and handed it to no handler")


def test_the_import_fetch_verifies_against_the_bundled_certificates(monkeypatch):
    """Breaks when the Import's safe fetch builds its context from the
    host's store, which the AppImage cannot find (as above)."""
    from pressless_import import fetch

    made: list[object] = []
    real = ssl.create_default_context

    def recording(*args, **kwargs):
        made.append(kwargs.get("cafile"))
        return real(*args, **kwargs)

    monkeypatch.setattr(ssl, "create_default_context", recording)
    fetch._Checked("8.8.4.4", "old.example.org", 443)
    assert made == [certifi.where()], made
