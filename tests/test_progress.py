# How far a long job has got (PRESS-0435).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0435-long-job-progress.md § 5. The words are written out
# here rather than imported: shared, they would compare the module against
# itself.
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

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
    # A fetch reads its blobs four at a time (PRESS-0461), so what the record
    # says when a read starts depends on which reader got there first. Every
    # report the record takes is watched instead, from whichever thread.
    reports: list[progress.Counted] = []
    counted = progress.Counted

    def watched(*args, **kwargs):
        reports.append(counted(*args, **kwargs))
        return reports[-1]

    fetching = _Watching(reads=_reads(listing, blob=b"words"))
    with pytest.MonkeyPatch.context() as patch, progress.job():
        patch.setattr(progress, "Counted", watched)
        publisher.fetch_state(_settings(), "a key", tmp_path / "fetched",
                              ("index.html", "about.html"), "base-commit-sha", fetching)
        fetched = progress.now()
    assert [(c.done, c.total, c.bytes_total) for c in reports] == [
        (0, 2, 400), (1, 2, 400), (2, 2, 400)]
    assert fetching.seen[0] == reports[0], "0 of 2 before the first blob"
    assert fetched.key == "progress.downloading"
    assert (fetched.done, fetched.total,
            fetched.bytes_done, fetched.bytes_total) == (2, 2, 400, 400)

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
    assert [(c.key, c.done, c.total, c.bytes_total) for c in sending.seen] == [
        ("progress.sending", 0, 2, 8), ("progress.sending", 1, 2, 8)]
    assert (sent.done, sent.total, sent.bytes_done, sent.bytes_total) == (2, 2, 8, 8)


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
    (progress.Counted("progress.sending", 3, 10, seconds_left=2480),
     SENDING + "3 of 10 files. GitHub's hourly allowance is used up; "
     "carrying on in 41:20.", 0.3),
])
def test_the_count_is_said_in_words(counted, said, fraction):
    """§ 4.3: a number not known leaves its part out."""
    from pressless import face
    assert face.progress_said(counted) == {"running": True, "said": said,
                                           "fraction": fraction}


def test_a_size_takes_the_languages_decimal_mark():
    """PRESS-0241 § 4.4: a size in the working note takes the language's
    decimal mark. Breaks when German reads 1.5 KB, which it reads as fifteen
    hundred."""
    from pressless import face, words
    words.choose("de")
    assert face._said_bytes(1536) == "1,5 KB"
    assert face._said_bytes(3 * 1024 * 1024 // 2) == "1,5 MB"
    words.choose("en")
    assert face._said_bytes(1536) == "1.5 KB"


# --------------------------------------------------------------- PRESS-0464 ---


def test_a_download_counts_as_it_packs(tmp_path):
    """A download is a GET whose page packs before it answers. Breaks when only
    a POST holds a record, so its counts go nowhere."""
    from _face_session import Browser

    from pressless import face

    counted, release = threading.Event(), threading.Event()

    def packing(request):
        progress.count("progress.packing", 3, 10)
        counted.set()
        assert release.wait(30), "the test never let the download go"
        return face.Reply(b"zip", "application/zip")

    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/packing", packing)
        browser = Browser(served)
        replies = []
        thread = threading.Thread(target=lambda: replies.append(
            browser.request("GET", "/packing")[0]))
        thread.start()
        try:
            assert counted.wait(10)
            during = _progress(browser)
        finally:
            release.set()
            thread.join(30)
        after = _progress(browser)
    finally:
        served.stop()
    assert replies == [200]
    assert during == {"running": True, "fraction": 0.3,
                      "said": "Packing the site file: 3 of 10 files."}
    assert after["running"] is False


def test_the_long_jobs_count(tmp_path):
    """PRESS-0464: the press's check of its files, the Builder's pages and
    photographs, a bring-in's writing and an update's download each report
    a count. Breaks when one of them stops reporting."""
    import io

    from test_builder import _entry as _built_entry
    from test_builder import _image, _photograph, _store
    from test_builder import _settings as _built_settings
    from test_importer import _export, _item

    from pressless import builder, store, updater
    from pressless_import import bring_in

    seen: list[progress.Counted] = []
    real = progress._count

    def kept(me, key, done, total, bytes_done, bytes_total):
        seen.append(progress.Counted(key, done, total, bytes_done, bytes_total))
        real(me, key, done, total, bytes_done, bytes_total)

    with pytest.MonkeyPatch.context() as patch, progress.job():
        patch.setattr(progress, "_count", kept)
        site = tmp_path / "site"
        site.mkdir()
        for name in ("a.html", "b.html"):
            (site / name).write_text(name, encoding="utf-8")
        publisher._local_files(site, ())

        folder = _store(tmp_path)
        _photograph(folder, "small.png", _image("PNG"))
        store.write(folder, _built_entry("pictured", "2024-03-05 09:00:00",
                                         body="{photo: small.png}"), draft=False)
        builder.build(folder, _built_settings(), tmp_path / "built")

        data = b"x" * 100
        offer = SimpleNamespace(asset_url="https://example.org/a", size=len(data),
                                sha256=hashlib.sha256(data).hexdigest())
        answer = SimpleNamespace(status=200, headers={"Content-Length": str(len(data))},
                                 read=io.BytesIO(data).read, close=lambda: None)
        with open(tmp_path / "update", "wb") as out:
            updater._stream(offer, SimpleNamespace(open=lambda url: answer), out)

        held = tmp_path / "held"
        (held / "media").mkdir(parents=True)
        (held / "export.xml").write_text(_export(_item(1, slug="one"), _item(2, slug="two")),
                                         encoding="utf-8")
        bring_in(held / "export.xml", held / "media", tmp_path / "brought", "meadow")

    by_key = {}
    for each in seen:
        by_key.setdefault(each.key, []).append(each)
    checking = [(c.done, c.total) for c in by_key["progress.checking"]]
    assert checking == [(0, 2), (1, 2), (2, 2)]
    building = by_key["progress.building"]
    assert [c.done for c in building] == list(range(building[0].total + 1))
    assert building[0].total > 1                  # an entry's page and a fixed page
    assert [(c.done, c.total) for c in by_key["progress.photographs"]] == [(1, 1)]
    assert by_key["progress.updating"][-1].bytes_done == len(data)
    assert by_key["progress.updating"][-1].bytes_total == len(data)
    bringing = [(c.done, c.total) for c in by_key["progress.bringing"]]
    assert bringing[0] == (0, bringing[0][1]) and bringing[-1] == (bringing[0][1],) * 2
    assert len(bringing) == bringing[0][1] + 1
