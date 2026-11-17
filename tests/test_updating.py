# The Face side of updating: the offer, the switch, and Update now
# (PRESS-0023 § 4.9).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0023-self-update.md § 5. The real Face and the real editor
# run; the network is the by-URL double from test_updater, and the spawn and
# the exit are always replaced. The words he sees are written out here rather
# than imported, so the test holds its own copy.
from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_editor import _Browser, _folder
from test_updater import _list, _Net, _Release

from pressless import editor, face, installer, overview, setup, update_key, updating

OFFER = "is ready to install. Your sites stay where they are."
LOOKING = "Pressless looks for a new version each time it starts."
NOT_LOOKING = "Pressless does not look for new versions."
INSTALLING = "Pressless is installing version 0.1.3 and will open again by itself"
ALLOWED = {"updates.json", "update.log", "pressless.lock", "pressless.log", "pressless.log.1"}
NEW = b"the new program"


@pytest.fixture
def signer(monkeypatch):
    from test_updater import _key
    private, public = _key()
    monkeypatch.setattr(update_key, "TRUSTED", (public,))
    return private


@pytest.fixture(autouse=True)
def _free_the_lock():
    """Update now keeps editor.LOCK to the exit on purpose (INV-15), and the
    exit is replaced here -- so it is released for the next test."""
    yield
    if editor.LOCK.locked():
        editor.LOCK.release()


class _Exit:
    def __init__(self, monkeypatch) -> None:
        self.codes: list[int] = []
        monkeypatch.setattr(updating, "_exit", self.codes.append)


def _artefact(tmp_path: Path) -> Path:
    apps = tmp_path / "apps"
    apps.mkdir(exist_ok=True)
    artefact = apps / "Pressless-0.1.2-x86_64.AppImage"
    if not artefact.exists():
        artefact.write_bytes(b"the old program")
    return artefact


def _release(signer, version: str) -> tuple[_Release, dict[str, object]]:
    release = _Release(f"v{version}", _list(version, linux=NEW), [signer])
    answers = release.answers()
    answers[release.url("linux")] = NEW
    return release, answers


@contextlib.contextmanager
def _pressless(folder: Path, artefact: Path, answers: dict[str, object]) -> Iterator[_Browser]:
    """One run of Pressless: a fresh Face, Your site, Settings, and updating."""
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        overview.register(served, folder)
        setup.register(served, folder)
        running = updating.register(served, folder, artefact=artefact, platform="linux",
                                    running="0.1.2", transport=_Net(answers))
        running.wait(10)
        yield _Browser(served)
    finally:
        served.stop()


def _shown(browser: _Browser, address: str = "/") -> str:
    status, _, text = browser.request("GET", address)
    assert status == 200, text
    return text


# ----------------------------------------------------------------- INV-13 ---


def test_skip_and_later(tmp_path, signer, monkeypatch):
    """Breaks when Later is written to disk or Skip is held in memory."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    _, offers_3 = _release(signer, "0.1.3")
    _, offers_4 = _release(signer, "0.1.4")

    with _pressless(folder, artefact, offers_3) as browser:
        assert f"Pressless 0.1.3 {OFFER}" in _shown(browser)
        status, headers, _ = browser.request("POST", "/update/skip")
        assert status == 303 and headers.get("Location") == "/", (status, headers)
        assert OFFER not in _shown(browser)
    assert json.loads((folder / "updates.json").read_text(encoding="utf-8"))["skip"] == "0.1.3"

    with _pressless(folder, artefact, offers_3) as browser:
        assert OFFER not in _shown(browser)
    with _pressless(folder, artefact, offers_4) as browser:
        assert f"Pressless 0.1.4 {OFFER}" in _shown(browser)
        on_disk = (folder / "updates.json").read_bytes()
        status, _, _ = browser.request("POST", "/update/later")
        assert status == 303
        assert OFFER not in _shown(browser)
        assert (folder / "updates.json").read_bytes() == on_disk
    with _pressless(folder, artefact, offers_4) as browser:
        assert f"Pressless 0.1.4 {OFFER}" in _shown(browser)


def test_the_switch(tmp_path, signer):
    """§ 4.9, as PRESS-0353 § 4.6 places it: the offer is on Your site, above
    the tiles, and the line that switches checking is on Settings, and
    writes updates.json."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    _, answers = _release(signer, "0.1.3")
    with _pressless(folder, artefact, answers) as browser:
        site = _shown(browser)
        assert LOOKING not in site and site.index(OFFER) < site.index('<div class="tiles">')
        page = _shown(browser, "/setup/computer")
        assert LOOKING in page and "Stop looking" in page
        status, headers, _ = browser.request("POST", "/update/checking", {"check": "false"})
        assert status == 303 and headers.get("Location") == "/setup/computer"
        page = _shown(browser, "/setup/computer")
        assert NOT_LOOKING in page and "Look when Pressless starts" in page
    assert json.loads((folder / "updates.json").read_text(encoding="utf-8")) == {
        "version": 1, "check": False, "skip": None}
    with _pressless(folder, artefact, answers) as browser:
        assert OFFER not in _shown(browser)


def test_an_unpackaged_run_never_checks(tmp_path, signer):
    """§ 4.4: where paths.artefact_path() raises NotPackaged, no check."""
    folder = _folder(tmp_path)
    _, answers = _release(signer, "0.1.3")
    net = _Net(answers)
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        overview.register(served, folder)
        updating.register(served, folder, transport=net).wait(10)
        assert net.requests == []
        assert OFFER not in _shown(_Browser(served))
    finally:
        served.stop()


# ----------------------------------------------------------------- INV-14 ---


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): (p.read_bytes() if p.is_file() else b"<dir>")
            for p in sorted(folder.rglob("*")) if p.relative_to(folder).parts[0] not in ALLOWED}


def test_update_now_leaves_his_folder_alone(tmp_path, signer, monkeypatch):
    """Breaks when the staged file or folder is put inside Pressless's own
    folder."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    _, answers = _release(signer, "0.1.3")
    spawned: list[list[str]] = []
    monkeypatch.setattr(installer.subprocess, "Popen",
                        lambda args, **kwargs: spawned.append(list(args)) or object())
    exited = _Exit(monkeypatch)
    # The swap moves the staged file away, so the end state alone cannot show
    # where it sat: that is read at the moment the swap begins.
    at_swap: list[tuple[Path, dict[str, bytes]]] = []
    real_apply = installer.apply_linux

    def apply(appimage, staged, where):
        at_swap.append((staged.parent, _snapshot(folder)))
        return real_apply(appimage, staged, where)

    monkeypatch.setattr(installer, "apply_linux", apply)

    with _pressless(folder, artefact, answers) as browser:
        before = _snapshot(folder)
        status, _, text = browser.request("POST", "/update")
        assert status == 200, text
        assert INSTALLING in text, text
        for _ in range(50):
            if exited.codes:
                break
            time.sleep(0.1)
    assert _snapshot(folder) == before
    assert at_swap == [(artefact.parent, before)], at_swap
    assert artefact.read_bytes() == NEW
    assert len(spawned) == 1 and exited.codes == [0]
    assert sorted(p.name for p in artefact.parent.iterdir()) == [artefact.name]


def test_a_failed_download_shows_its_sentence_and_changes_nothing(tmp_path, signer,
                                                                   monkeypatch):
    """§ 4.9 step 1: a failure shows its sentence, takes no lock and exits
    nothing."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    release, answers = _release(signer, "0.1.3")
    exited = _Exit(monkeypatch)
    with _pressless(folder, artefact, answers) as browser:
        answers[release.url("linux")] = NEW[:-2] + b"!!"
        status, _, text = browser.request("POST", "/update")
    assert "did not prove it came from Pressless" in text, text
    assert artefact.read_bytes() == b"the old program"
    assert not editor.LOCK.locked() and exited.codes == []


# ----------------------------------------------------------------- INV-15 ---


def test_update_waits_for_a_save(tmp_path, signer, monkeypatch):
    """Breaks when the lock is skipped, or released before the exit."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    _, answers = _release(signer, "0.1.3")
    applied = threading.Event()

    def apply(appimage, staged, where):
        assert editor.LOCK.locked()
        applied.set()
        return True

    monkeypatch.setattr(installer, "apply_linux", apply)
    exited = _Exit(monkeypatch)

    with _pressless(folder, artefact, answers) as browser:
        editor.LOCK.acquire()
        replies: list[tuple[int, str]] = []
        worker = threading.Thread(
            target=lambda: replies.append(browser.request("POST", "/update")[::2]))
        worker.start()
        assert not applied.wait(1.0), "apply ran while a save held the lock"
        editor.LOCK.release()
        assert applied.wait(10), "apply never ran once the lock was free"
        worker.join(10)
        assert replies and replies[0][0] == 200, replies
        for _ in range(50):
            if exited.codes:
                break
            time.sleep(0.1)
        assert exited.codes == [0]
        assert editor.LOCK.locked(), "the lock was released before the exit"


def test_a_second_update_now_goes_home(tmp_path, signer, monkeypatch):
    """review-code 2026-11-16 lane 11: the Face serves each request on its
    own thread, so a double click or a second tab downloaded a second copy
    beside the first, then waited on the lock for good.

    Breaks when a second Update now starts while one is under way, or a
    failed one keeps the next from starting."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    release, answers = _release(signer, "0.1.3")
    address = release.url("linux")
    # Every download fails once let go, so no copy reaches the swap or the
    # exit, whichever way the test goes.
    answers[address] = OSError("let go")
    asked, go_on = threading.Event(), threading.Event()

    class _Slow(_Net):
        def open(self, url):
            if url == address:
                asked.set()
                go_on.wait(10)
            return super().open(url)

    exited = _Exit(monkeypatch)
    net = _Slow(answers)
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        overview.register(served, folder)
        updating.register(served, folder, artefact=artefact, platform="linux",
                          running="0.1.2", transport=net).wait(10)
        browser = _Browser(served, timeout=5)
        first = threading.Thread(target=browser.request, args=("POST", "/update"))
        first.start()
        assert asked.wait(10), "the first Update now never downloaded"
        status, headers, _ = browser.request("POST", "/update")
        assert status == 303 and headers.get("Location") == "/", (status, headers)
        go_on.set()
        first.join(10)
        assert net.requests.count(address) == 1, net.requests
        # A failed one lets the next try.
        assert browser.request("POST", "/update")[0] == 200
        assert net.requests.count(address) == 2, net.requests
        assert exited.codes == [] and not editor.LOCK.locked()
    finally:
        go_on.set()
        served.stop()


def test_a_restart_keeps_the_offer_and_later(tmp_path, signer):
    """§ 4.9: the offer and a Later are held for the life of the process. A
    Restart, or opening another site, serves a new Face in the same process
    and hands it the same Updates (__main__._serve_held).

    Breaks when a Face handed that state checks again, or forgets Later."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    _, answers = _release(signer, "0.1.3")
    net = _Net(answers)
    kept = updating.Updates()
    asked = 0
    for first in (True, False):
        served = face.serve(folder)
        try:
            editor.register(served, folder)
            overview.register(served, folder)
            updating.register(served, folder, artefact=artefact, platform="linux",
                              running="0.1.2", transport=net, state=kept).wait(10)
            browser = _Browser(served)
            if first:
                assert f"Pressless 0.1.3 {OFFER}" in _shown(browser)
                assert browser.request("POST", "/update/later")[0] == 303
                asked = len(net.requests)
            assert OFFER not in _shown(browser)
        finally:
            served.stop()
    assert len(net.requests) == asked, net.requests


def test_a_start_clears_what_a_stopped_update_left(tmp_path, signer):
    """review-code 2026-11-16 lane 11: a Pressless stopped during a download
    or an unpack, or a Windows helper that died, left a file or folder the
    size of the program beside it for good. A packaged start removes those
    before its check, and nothing else.

    Breaks when one is left, or another file beside the program goes."""
    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    beside = artefact.parent
    (beside / ".pressless-update-0a1b2c3d").write_bytes(b"half a download")
    (beside / "Pressless.new-0a1b" / "Pressless").mkdir(parents=True)
    (beside / "pressless-update-0a1b.ps1").write_text("the helper", encoding="ascii")
    kept = ("notes.txt", "pressless-update-notes.txt", "Pressless.newer")
    for name in kept[:2]:
        (beside / name).write_text("his", encoding="ascii")
    (beside / "Pressless.newer").mkdir()
    _, answers = _release(signer, "0.1.3")
    with _pressless(folder, artefact, answers):
        pass
    assert sorted(p.name for p in beside.iterdir()) == sorted((artefact.name, *kept))


# ----------------------------------------------------------------- INV-24 ---


def test_the_offer_shows_what_changed(tmp_path, signer):
    """Breaks when the changes are left off the page, or their text reaches
    the page unescaped."""
    from test_updater import _with_changes

    folder = _folder(tmp_path)
    artefact = _artefact(tmp_path)
    text = (
        b"pressless-changes 1\nversion 0.1.4\n"
        b"## [0.1.4] - 2026-01-04\n\n### Added\n\n"
        b"- **A bold thing** (PRESS-0001)\n  It does <script>alert(1)</script> more.\n\n"
        b"## [0.1.3] - 2026-01-03\n\n**Theme:** Third\n\n"
        b"## [0.1.2] - 2026-01-02\n\nthe running one\n"
    )
    release = _Release("v0.1.4", _list("0.1.4", linux=NEW), [signer])

    with _pressless(folder, artefact, _with_changes(release, text, [signer])) as browser:
        page = _shown(browser)
    assert "What is new since version 0.1.2" in page, page
    assert "Version 0.1.4" in page and "Version 0.1.3" in page, page
    assert "<strong>A bold thing</strong>" in page and "<h4>Added</h4>" in page, page
    assert "It does &lt;script&gt;alert(1)&lt;/script&gt; more." in page, page
    assert "<script>alert(1)" not in page and "PRESS-0001" not in page, page
    assert "Third" in page and "the running one" not in page, page

    _, plain = _release(signer, "0.1.4")
    with _pressless(folder, artefact, plain) as browser:
        page = _shown(browser)
    assert f"Pressless 0.1.4 {OFFER}" in page and "What is new" not in page, page
