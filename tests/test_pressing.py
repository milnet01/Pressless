# The running press and how it ended, known to Pressless itself (PRESS-0235).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0235-press-status.md § 5. The words a page must carry are
# written out here rather than imported: shared, they would compare the module
# against itself.
#
# A publish is held mid-run by a transport that waits on an event at its first
# request, so a test can ask Pressless what it knows while the press runs.
from __future__ import annotations

import contextlib
import json
import threading
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser
from test_page_editor import _folder
from test_publisher import _listing, _reads, _Transport, _writes

from pressless import (
    credentials,
    editor,
    face,
    page_editor,
    pressing,
    publishing,
    store,
    undo,
)
from pressless.face import Request

KEY = "not a real key for the press tests"
PUBLISHING = "Publishing… this can take a few minutes the first time."
PUBLISHED = "Published. Your site shows it within a few minutes."
NOT_PUBLISHED = "Not published. The reason is below."


class _Held(_Transport):
    """Waits at its first request until `release` is set, or raises `raises`."""

    def __init__(self, raises: BaseException | None = None) -> None:
        super().__init__(reads=_reads(_listing([])), writes=_writes())
        self.started, self.release = threading.Event(), threading.Event()
        self.raises = raises

    def request(self, method, url, body, headers):
        if not self.started.is_set():
            self.started.set()
            if self.raises is not None:
                raise self.raises
            assert self.release.wait(30), "the test never let the press go"
        return super().request(method, url, body, headers)


class _Quick(Browser):
    """One browser per Face, since the opening link is spent once. Every request
    must answer within a second, which INV-2, INV-3 and INV-5 ask of a press in
    flight, unless it says otherwise."""

    def __init__(self, served: face.Face) -> None:
        super().__init__(served, timeout=1)

    def request(self, method, path, form=None, *, timeout: float = 1, **more):
        self.timeout = timeout
        return super().request(method, path, form, **more)


class _Unforeseen(BaseException):
    """Past every route's `except Exception` (INV-4)."""


@pytest.fixture
def folder(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(credentials, "read", lambda kind, folder, account: KEY)
    return _folder(tmp_path)


@contextlib.contextmanager
def _pressless(folder: Path, transport: _Transport) -> Iterator[_Quick]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=transport)
        page_editor.register(served, folder, transport=transport)
        undo.register(served, folder, transport=transport)
        pressing.register(served)
        yield _Quick(served)
    finally:
        served.stop()


def _entry_form(folder: Path) -> dict[str, str]:
    path = store.path_for(folder, "seaside", draft=False)
    return {"slug": "seaside", "draft": "0", "base": page_editor._digest(path),
            "title": "Seaside", "categories": "", "tags": "", "body": "Words."}


def _page_form(folder: Path) -> dict[str, str]:
    path = store.html_path_for(folder, "pages", "about")
    return {"kind": "pages", "name": "about", "view": page_editor.CODE, "show": "",
            "waiting": "0", "base": page_editor._digest(path),
            "text": store.read_html(path)}


@contextlib.contextmanager
def _held_publish(browser: _Quick, folder: Path, transport: _Held) -> Iterator[None]:
    """A publish running in the background, held at its first upload request."""
    replies: list[tuple[int, str]] = []
    form = _entry_form(folder)

    def press() -> None:
        status, _, text = browser.request("POST", "/publish", form, timeout=30)
        replies.append((status, text))

    thread = threading.Thread(target=press)
    thread.start()
    try:
        assert transport.started.wait(10), "the publish never reached GitHub"
        yield
    finally:
        transport.release.set()
        thread.join(30)
    assert replies and replies[0][0] == 200, replies


def _press(browser: _Quick) -> dict:
    status, _, text = browser.request("GET", "/press")
    assert status == 200, text
    return json.loads(text)


def _line(page: str) -> str:
    """The press row's status line."""
    return page.split('id="publish-status"', 1)[1].split("</p>", 1)[0]


# ------------------------------------------------------------------ INV-1 ---


def test_one_press_at_a_time():
    assert pressing.start(pressing.PUBLISH) is True
    assert pressing.start(pressing.PUBLISH) is False
    assert pressing.start(pressing.UNDO) is False
    pressing.end(pressing.Outcome("Done."))
    assert pressing.start(pressing.UNDO) is True


# ------------------------------------------------------------------ INV-2 ---


def test_the_press_is_known_while_it_runs(folder):
    transport = _Held()
    with _pressless(folder, transport) as browser:
        with _held_publish(browser, folder, transport):
            assert _press(browser) == {"running": True, "kind": "publish",
                                      "said": PUBLISHING, "failure": None}
        assert _press(browser)["running"] is False
        assert _press(browser)["said"] == PUBLISHED


# ------------------------------------------------------------------ INV-3 ---


def test_a_second_press_is_refused(folder):
    transport = _Held()
    with _pressless(folder, transport) as browser:
        with _held_publish(browser, folder, transport):
            for path, form in (("/publish", _entry_form(folder)),
                               ("/page/publish", _page_form(folder)),
                               ("/undo", {})):
                status, _, text = browser.request("POST", path, form)
                assert status == 200, (path, text)
                reply = json.loads(text)
                assert reply["busy"] is True and reply["said"] == PUBLISHING, (path, reply)
                assert reply.get("published", reply.get("undone")) is False, (path, reply)
                assert reply["failure"] is None, (path, reply)
            # The held press waits before its first request is recorded, so any
            # request here came from a refused press.
            assert transport.requests == [], transport.requests
            assert _press(browser)["running"] is True


def test_a_refused_publish_keeps_the_page_on_its_file(folder):
    transport = _Held()
    with _pressless(folder, transport) as browser:
        with _held_publish(browser, folder, transport):
            form = _entry_form(folder)
            reply = json.loads(browser.request("POST", "/publish", form)[2])
            assert (reply["slug"], reply["draft"], reply["base"]) == (
                "seaside", False, form["base"])
            page = _page_form(folder)
            reply = json.loads(browser.request("POST", "/page/publish", page)[2])
            assert (reply["waiting"], reply["base"]) == (False, page["base"])


# ------------------------------------------------------------------ INV-4 ---


def test_an_unforeseen_failure_ends_the_press(folder):
    transport = _Held(raises=_Unforeseen())
    with _pressless(folder, transport) as browser:
        body = urllib.parse.urlencode(_entry_form(folder)).encode("utf-8")
        with pytest.raises(_Unforeseen):
            publishing._publish(browser.served, folder, Request("POST", "/publish", {}, body),
                                transport)
        assert _press(browser) == {"running": False, "kind": None, "said": NOT_PUBLISHED,
                                  "failure": None}


# ------------------------------------------------------------------ INV-5 ---


def test_an_editor_opened_mid_press_holds(folder):
    transport = _Held()
    with _pressless(folder, transport) as browser:
        with _held_publish(browser, folder, transport):
            for path in ("/edit?slug=seaside", "/page?kind=pages&name=about"):
                status, _, page = browser.request("GET", path)
                assert status == 200, (path, page)
                assert 'class="press-status"' in page, path
                assert f">{PUBLISHING}</p>" in page, path
                assert 'data-press="hold"' in page, path


# ------------------------------------------------------------------ INV-6 ---


def test_the_outcome_shows_until_a_save(folder):
    transport = _Held()
    with _pressless(folder, transport) as browser:
        with _held_publish(browser, folder, transport):
            pass
        for path in ("/edit?slug=seaside", "/page?kind=pages&name=about"):
            status, _, page = browser.request("GET", path)
            assert status == 200, (path, page)
            assert _line(page).endswith(f">{PUBLISHED}"), (path, _line(page))
        status, _, text = browser.request("POST", "/page/save", _page_form(folder))
        assert status == 200, text
        for path in ("/edit?slug=seaside", "/page?kind=pages&name=about"):
            line = _line(browser.request("GET", path)[2])
            assert PUBLISHED not in line, (path, line)
        assert _line(browser.request("GET", "/page?kind=pages&name=about")[2]).endswith(
            ">Changes not published yet"), "the page's standing words"


# ------------------------------------------------------------------ INV-7 ---


def test_every_page_asks_about_the_press():
    assert pressing.start(pressing.PUBLISH)
    held = pressing.holding()
    assert held is not None
    for name, script in (("entry", editor._EDITOR_SCRIPT), ("page", page_editor._PAGE_SCRIPT),
                         ("undo", editor._UNDO_SCRIPT), ("holding", held)):
        assert 'fetch("/press")' in script, name
        assert "Keep this page open." not in script, name
