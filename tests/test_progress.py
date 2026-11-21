# How far a long job has got (PRESS-0435).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0435-long-job-progress.md § 5. The words are written out
# here rather than imported: shared, they would compare the module against
# itself.
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from test_pressing import _entry_form, _press, _pressless, folder  # noqa: F401
from test_publisher import _blob_hash, _listing, _reads, _settings, _Transport, _writes

from pressless import progress, publisher

SENDING = "Sending your site to GitHub: "


class _HeldAtUpload(_Transport):
    """Waits at its first write, a blob upload, until `release` is set."""

    def __init__(self) -> None:
        super().__init__(reads=_reads(_listing([])), writes=_writes())
        self.started, self.release = threading.Event(), threading.Event()

    def request(self, method, url, body, headers):
        if method != "GET" and not self.started.is_set():
            self.started.set()
            assert self.release.wait(30), "the test never let the press go"
        return super().request(method, url, body, headers)


def _held(browser, site: Path, transport: _HeldAtUpload, during) -> None:
    """Run `during` while a publish is held at its first upload."""
    replies = []
    thread = threading.Thread(target=lambda: replies.append(
        browser.request("POST", "/publish", _entry_form(site), timeout=30)))
    thread.start()
    try:
        assert transport.started.wait(10), "the publish never reached an upload"
        during()
    finally:
        transport.release.set()
        thread.join(30)
    assert replies and replies[0][0] == 200, replies


def _progress(browser) -> dict:
    status, _, text = browser.request("GET", "/progress")
    assert status == 200, text
    return json.loads(text)


# ------------------------------------------------------------------ INV-1 ---


def test_a_held_fetch_is_counted_then_forgotten(folder):  # noqa: F811
    """Breaks when _dispatch does not wrap a POST in progress.job(), or the
    record outlives its request."""
    transport = _HeldAtUpload()
    seen = []
    with _pressless(folder, transport) as browser:
        _held(browser, folder, transport, lambda: seen.append(_progress(browser)))
        after = _progress(browser)
    assert seen[0]["running"] is True
    assert seen[0]["said"].startswith(SENDING + "0 of "), seen
    assert seen[0]["fraction"] == 0
    assert after == {"running": False, "said": "", "fraction": None}


# ------------------------------------------------------------------ INV-2 ---


def test_a_count_with_no_job_is_ignored():
    """Breaks when count makes a record, or raises, where none is held."""
    progress.count("progress.sending", 1, 2)
    assert progress.now() is None
    with progress.job():
        assert progress.now() is None
        progress.count("progress.sending", 1, 2)
        assert progress.now() == progress.Counted("progress.sending", 1, 2)
    assert progress.now() is None


# ------------------------------------------------------------------ INV-3 ---


class _Watching(_Transport):
    """Records what progress says at each blob request."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.seen: list[progress.Counted | None] = []

    def request(self, method, url, body, headers):
        if "/git/blobs" in url:
            self.seen.append(progress.now())
        return super().request(method, url, body, headers)


def test_fetch_and_publish_count_every_blob(tmp_path):
    """Breaks when a loop counts a blob it skips, skips one it reads, or
    reports only at the end."""
    listing = json.dumps({"sha": "base-tree-sha", "truncated": False, "tree": [
        {"path": "index.html", "type": "blob", "sha": "a", "size": 100},
        {"path": "about.html", "type": "blob", "sha": "b", "size": 300},
        {"path": "pictures", "type": "tree", "sha": "c"},
        {"path": "outside.txt", "type": "blob", "sha": "d", "size": 999}]}).encode()
    fetching = _Watching(reads=_reads(listing, blob=b"words"))
    with progress.job():
        publisher.fetch_state(_settings(), "a key", tmp_path / "fetched",
                              ("index.html", "about.html"), "base-commit-sha", fetching)
        fetched = progress.now()
    assert [(c.done, c.total, c.whole) for c in fetching.seen] == [(0, 2, 400), (1, 2, 400)]
    assert fetched.key == "progress.downloading"
    assert (fetched.done, fetched.total, fetched.size, fetched.whole) == (2, 2, 400, 400)

    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_bytes(b"12345")
    (site / "about.html").write_bytes(b"123")
    (site / "same.html").write_bytes(b"kept")
    remote = _listing([("same.html", _blob_hash(b"kept"))])
    sending = _Watching(reads=_reads(remote), writes=_writes())
    with progress.job():
        publisher.publish(_settings(untouchable=()), site, "a key", "A message.", sending)
        sent = progress.now()
    assert [(c.key, c.done, c.total, c.whole) for c in sending.seen] == [
        ("progress.sending", 0, 2, 8), ("progress.sending", 1, 2, 8)]
    assert (sent.done, sent.total, sent.size, sent.whole) == (2, 2, 8, 8)


# ------------------------------------------------------------------ INV-5 ---


def test_progress_answers_during_a_press(folder):  # noqa: F811
    """Breaks when GET /progress takes editor.LOCK or waits on the job. The
    browser gives each request one second."""
    transport = _HeldAtUpload()
    with _pressless(folder, transport) as browser:
        answers = []
        _held(browser, folder, transport, lambda: answers.append(
            (_progress(browser)["running"], _press(browser)["running"])))
    assert answers == [(True, True)]


@pytest.mark.parametrize(("counted", "said", "fraction"), [
    (progress.Counted("progress.sending", 3, 10, 1536, 2 * 1024 * 1024),
     SENDING + "3 of 10 files, 1.5 KB of 2.0 MB.", 1536 / (2 * 1024 * 1024)),
    (progress.Counted("progress.sending", 3, 10), SENDING + "3 of 10 files.", 0.3),
    (progress.Counted("progress.downloading", 4, None, 2048),
     "Downloading your site: 4 files so far, 2.0 KB.", None),
    (progress.Counted("progress.building"), "Building your pages.", None),
])
def test_the_count_is_said_in_words(counted, said, fraction):
    """§ 4.3: a number not known leaves its part out."""
    from pressless import face
    assert face.progress_said(counted) == {"running": True, "said": said,
                                           "fraction": fraction}
