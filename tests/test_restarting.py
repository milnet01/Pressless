# PRESS-0203: Restart Pressless from inside the app. Settings links to a page
# that asks first; only its POST asks the launcher for a restart, and only once
# the answer has been sent. The launcher's half is in tests/test_main.py.
from __future__ import annotations

import threading

from _face_session import Browser
from test_setup import _GitHub, _saved, _setup_page, _Store

from pressless import face, restarting


def test_settings_links_to_restart(tmp_path, monkeypatch):
    _Store(monkeypatch)
    _saved(tmp_path)
    with _setup_page(tmp_path, _GitHub()) as browser:
        _, page = browser.get()
    assert f'href="{restarting.PATH}"' in page


def test_restart_asks_first_and_restarts_only_on_the_post(tmp_path):
    asked = threading.Event()
    served = face.serve(tmp_path)
    try:
        restarting.register(served, asked.set)
        browser = Browser(served)

        status, _, page = browser.request("GET", restarting.PATH)
        assert status == 200
        assert f'method="post" action="{restarting.PATH}"' in page
        assert not asked.wait(0.2), "showing the question restarted Pressless"

        status, _, page = browser.request("POST", restarting.PATH)
        assert status == 200
        assert "new tab" in page
        assert asked.wait(5), "the POST did not ask the launcher to restart"
    finally:
        served.stop()


def test_a_post_from_elsewhere_restarts_nothing(tmp_path):
    asked = threading.Event()
    served = face.serve(tmp_path)
    try:
        restarting.register(served, asked.set)
        status, _, _ = Browser(served).request("POST", restarting.PATH,
                                               origin="http://127.0.0.1:1")
        assert status != 200
        assert not asked.wait(0.2)
    finally:
        served.stop()
