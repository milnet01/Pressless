"""Usage reports, sent only when the user says yes (PRESS-0262).

Each test names the invariant it holds, from
docs/specs/PRESS-0262-usage-reports.md § 5. Nothing here reaches Google: every
report goes to a recording double, and the key is a made-up pair of words.
"""
from __future__ import annotations

import contextlib
import json
import threading
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser
from test_publishing import _entry, _key, _refusing
from test_publishing import _folder as _publishing_folder
from test_publishing import _settings as _publishing_settings
from test_setup import _GitHub, _step

from pressless import editor, face, publishing, settings, setup, store, usage

# Plain words a report must never carry (INV-4): each names one thing of the
# user's -- the site, an entry, its words, the repository, the folder.
MARKERS = ("periwinklesite", "periwinkleentry", "periwinklewords", "periwinklerepo",
           "periwinklefolder", "periwinklefailure")


class _Recorder:
    """A transport double: records each report, and can hold one until let go."""

    def __init__(self, *, hold: bool = False) -> None:
        self.bodies: list[dict] = []
        self.urls: list[str] = []
        self.released = threading.Event()
        if not hold:
            self.released.set()
        self._lock = threading.Lock()

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.released.wait(10)
        with self._lock:
            self.urls.append(url)
            self.bodies.append(json.loads(body or b"null"))
        return 204, {}, b""

    def now(self) -> float:
        return 0.0


class _NoFace:
    """What `usage.register` needs of a Face, for tests that serve no pages."""

    def __init__(self) -> None:
        self.notes: list[str] = []

    def note(self, text: str) -> None:
        self.notes.append(text)

    def add_page(self, *args, **kwargs) -> None:
        return None

    def add_to_list(self, *args, **kwargs) -> None:
        return None


def _keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(usage, "MEASUREMENT_ID", "G-PLAINWORDS")
    monkeypatch.setattr(usage, "API_SECRET", "plain-words-secret")


def _settle() -> None:
    """Wait for every report on its way."""
    for thread in threading.enumerate():
        if thread.name == "pressless-usage":
            thread.join(10)


def _events(recorder: _Recorder) -> list[str]:
    _settle()
    return [body["events"][0]["name"] for body in recorder.bodies]


# ------------------------------------------------------------------ INV-1 ---


@pytest.mark.parametrize("case", ["no file", "no", "malformed", "no key", "yes"])
def test_nothing_is_sent_without_a_yes(tmp_path, monkeypatch, case):
    """Breaks when `report` sends before both the key and a yes are known."""
    _keyed(monkeypatch)
    recorder = _Recorder()
    usage.register(_NoFace(), tmp_path, transport=recorder)
    if case == "no":
        usage.set_answer(tmp_path, False)
    elif case == "malformed":
        (tmp_path / usage.FILE_NAME).write_text('{"version": 1, "yes": "yes"}',
                                                encoding="utf-8")
    elif case in ("no key", "yes"):
        usage.set_answer(tmp_path, True)
    if case == "no key":
        monkeypatch.setattr(usage, "API_SECRET", "")

    usage.report("screen", screen="/")

    assert len(_events(recorder)) == (1 if case == "yes" else 0)
    assert (tmp_path / usage.SENT_NAME).exists() == (case == "yes")
    assert usage.answer(tmp_path) is {"no file": None, "no": False, "malformed": False,
                                      "no key": True, "yes": True}[case]


def test_nothing_is_sent_before_register(tmp_path, monkeypatch):
    """Breaks when `report` reaches for a folder or transport nobody gave it."""
    _keyed(monkeypatch)
    usage.set_answer(tmp_path, True)
    usage.report("screen", screen="/")
    _settle()
    assert not (tmp_path / usage.SENT_NAME).exists()


# ------------------------------------------------------------------ INV-2 ---


def _set_up(folder: Path) -> None:
    folder.mkdir(exist_ok=True)
    settings.save(folder, _publishing_settings(folder))


@contextlib.contextmanager
def _served(folder: Path, recorder: _Recorder) -> Iterator[Browser]:
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        usage.register(served, folder, transport=recorder)
        yield Browser(served)
    finally:
        served.stop()


def test_an_unanswered_question_is_no(tmp_path, monkeypatch):
    """Breaks when the answer is written only on a button press, so a user who
    leaves the question is asked for ever, or counted as yes."""
    _keyed(monkeypatch)
    _set_up(tmp_path)
    with _served(tmp_path, _Recorder()) as browser:
        status, _, page = browser.request("GET", "/")
        assert status == 200
        assert 'id="usage-question"' in page
        assert 'action="/usage/yes"' in page
        assert usage.answer(tmp_path) is False
        assert 'id="usage-question"' not in browser.request("GET", "/")[2]

        status, _, page = browser.request("POST", "/usage/yes")
        assert status == 200
        assert usage.answer(tmp_path) is True


def test_no_question_without_the_key_or_before_setup(tmp_path, monkeypatch):
    """Breaks when a copy that cannot send asks, or asks before setup."""
    with _served(tmp_path, _Recorder()) as browser:
        _set_up(tmp_path)
        assert 'id="usage-question"' not in browser.request("GET", "/")[2]
        assert "not available in this copy" in browser.request("GET", "/usage")[2]
    assert usage.answer(tmp_path) is None


# ------------------------------------------------------------------ INV-3 ---


def test_events_carry_their_fixed_fields(tmp_path, monkeypatch):
    """Breaks when a caller's new parameter is sent, or COMMON loses one."""
    _keyed(monkeypatch)
    usage.set_answer(tmp_path, True)
    recorder = _Recorder()
    usage.register(_NoFace(), tmp_path, transport=recorder)
    for name, fields in usage.EVENTS.items():
        usage.report(name, **{field: "x" * 150 for field in fields})
    _settle()

    sent = {body["events"][0]["name"]: body for body in recorder.bodies}
    assert set(sent) == set(usage.EVENTS)
    client = json.loads((tmp_path / usage.FILE_NAME).read_text(encoding="utf-8"))["client"]
    for name, fields in usage.EVENTS.items():
        assert set(sent[name]) == {"client_id", "events"}
        assert sent[name]["client_id"] == client
        params = sent[name]["events"][0]["params"]
        assert set(params) == set(fields) | set(usage.COMMON), name
        assert all(params[field] == "x" * 100 for field in fields), name
        assert params["engagement_time_msec"] == 1
        assert isinstance(params["session_id"], int)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(recorder.urls[0]).query)
    assert recorder.urls[0].startswith(usage.ENDPOINT + "?")
    assert query == {"measurement_id": ["G-PLAINWORDS"], "api_secret": ["plain-words-secret"]}

    with pytest.raises(ValueError):
        usage.report("error", error="x", screen="/", publishing="no")
    with pytest.raises(ValueError):
        usage.report("screen", screen="/", page="periwinkleentry")
    with pytest.raises(ValueError):
        usage.report("press", kind="publish")


def test_a_bad_call_fails_whatever_the_answer(tmp_path):
    """Breaks when the check moves after the answer, so it passes in every
    test that never says yes."""
    with pytest.raises(ValueError):
        usage.report("screen", screen="/", page="x")


# ------------------------------------------------------------------ INV-4 ---


def test_no_users_words_are_sent(tmp_path, monkeypatch):
    """Breaks when `screen` takes the request's address with its query, when
    `failure` takes the exception's message, or when any other value is read
    from the user's files or answers."""
    _keyed(monkeypatch)
    recorder = _Recorder()

    # Setup, in a folder named with a marker; a yes at its reports step.
    fresh = tmp_path / "periwinklefolder-new"
    fresh.mkdir()
    served = face.serve(fresh)
    try:
        setup.register(served, fresh, transport=_GitHub(), shortcut_places=lambda: None)
        usage.register(served, fresh, transport=recorder)
        browser = Browser(served)
        page = browser.request("GET", "/setup")[2]
        assert _step(page) == "welcome"
        page = browser.request("POST", "/setup", {"step": "welcome", "go": "next"})[2]
        assert _step(page) == "reports"
        page = browser.request("POST", "/setup",
                               {"step": "reports", "go": "next", "reports": "yes"})[2]
        assert usage.answer(fresh) is True
        page = browser.request("POST", "/setup", {"step": "account", "go": "next",
                                                  "account": "owner"})[2]
        page = browser.request("POST", "/setup", {"step": "repository", "go": "next",
                                                  "repository": "periwinklerepo"})[2]
        assert _step(page) == "repository"     # refused, and shown again
    finally:
        served.stop()

    # The editors and a failing press, over a site full of markers.
    (tmp_path / "periwinklefolder").mkdir()
    folder = _publishing_folder(tmp_path / "periwinklefolder")
    settings.save(folder, settings.Settings(
        site_folder=folder / "site", repository="owner/periwinklerepo",
        site_address="https://periwinklesite.example.org",
        daily_prompt_filter="", untouchable=("CNAME",),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))
    store.write_identity(folder, store.Identity("periwinklesite"))
    store.write(folder, _entry("periwinkleentry", body="periwinklewords"), draft=True)
    usage.set_answer(folder, True)
    _key(monkeypatch)

    def broken(request):
        raise RuntimeError("periwinklefailure in periwinklefolder")

    served = face.serve(folder)
    try:
        editor.register(served, folder)
        publishing.register(served, folder, transport=_refusing())
        usage.register(served, folder, transport=recorder)
        served.add_page("GET", "/broken", broken)
        browser = Browser(served)
        assert browser.request("GET", "/")[0] == 200
        assert browser.request("GET", "/edit?slug=periwinkleentry")[0] == 200
        entry = store.read(store.path_for(folder, "periwinkleentry", draft=True))
        browser.request("POST", "/publish", {
            "slug": "periwinkleentry", "draft": "1", "base": "", "title": entry.title,
            "categories": "", "tags": "", "body": "periwinklewords"})
        assert browser.request("GET", "/broken?periwinkleentry")[0] == 500
    finally:
        served.stop()

    names = _events(recorder)
    assert {"screen", "wizard_step", "press", "failure"} <= set(names), names
    sent = json.dumps(recorder.bodies)
    assert not [marker for marker in MARKERS if marker in sent], sent
    screens = {body["events"][0]["params"].get("screen") for body in recorder.bodies}
    assert {"/", "/edit", "/broken"} <= screens
    presses = [body["events"][0]["params"] for body in recorder.bodies
               if body["events"][0]["name"] == "press"]
    assert [(press["kind"], press["ended"]) for press in presses] == [("publish", "failed")]


# ------------------------------------------------------------------ INV-5 ---


def test_a_slow_endpoint_holds_nothing(tmp_path, monkeypatch):
    """Breaks when `report` sends on the calling thread: the page would wait
    for Google."""
    _keyed(monkeypatch)
    _set_up(tmp_path)
    usage.set_answer(tmp_path, True)
    recorder = _Recorder(hold=True)
    try:
        with _served(tmp_path, recorder) as browser:
            browser.timeout = 3
            assert browser.request("GET", "/usage")[0] == 200
            assert recorder.bodies == []          # still held when the page arrived
    finally:
        recorder.released.set()
    assert _events(recorder) == ["screen"]


def test_a_failed_report_is_one_note(tmp_path, monkeypatch):
    """Breaks when a failure reaches the caller, or the note names the address,
    which holds the key."""
    _keyed(monkeypatch)
    usage.set_answer(tmp_path, True)

    class Refusing(_Recorder):
        def request(self, *args):
            raise OSError("no route to periwinklesite")

    noted = _NoFace()
    usage.register(noted, tmp_path, transport=Refusing())
    usage.report("screen", screen="/")
    _settle()
    assert noted.notes == ["usage report screen not sent: OSError"]


# ------------------------------------------------------------------ INV-6 ---


def test_no_forgets_the_client(tmp_path, monkeypatch):
    """Breaks when saying no keeps the client id or the reports sent."""
    _keyed(monkeypatch)
    usage.set_answer(tmp_path, True)
    usage.register(_NoFace(), tmp_path, transport=_Recorder())
    usage.report("screen", screen="/")
    _settle()
    assert (tmp_path / usage.SENT_NAME).exists()

    usage.set_answer(tmp_path, False)
    record = json.loads((tmp_path / usage.FILE_NAME).read_text(encoding="utf-8"))
    assert record == {"version": 1, "yes": False, "client": None}
    assert not (tmp_path / usage.SENT_NAME).exists()

    usage.set_answer(tmp_path, True)
    again = json.loads((tmp_path / usage.FILE_NAME).read_text(encoding="utf-8"))["client"]
    assert isinstance(again, str) and len(again) == 32


# ------------------------------------------------------------------ INV-7 ---


def test_the_list_is_what_was_sent(tmp_path, monkeypatch):
    """Breaks when the list is written from anything but the body sent, or
    stops trimming at KEPT."""
    _keyed(monkeypatch)
    usage.set_answer(tmp_path, True)
    recorder = _Recorder()
    usage.register(_NoFace(), tmp_path, transport=recorder)
    for number in range(usage.KEPT + 3):
        usage.report("screen", screen=f"/{number}")
    _settle()

    kept = json.loads((tmp_path / usage.SENT_NAME).read_text(encoding="utf-8"))
    assert len(kept) == usage.KEPT
    order = lambda body: int(body["events"][0]["params"]["screen"][1:])  # noqa: E731
    assert kept == sorted(recorder.bodies, key=order)[-usage.KEPT:]
    assert [order(body) for body in kept] == list(range(3, usage.KEPT + 3))


def test_the_screen_lists_what_was_sent(tmp_path, monkeypatch):
    """Breaks when the Usage reports screen shows anything but the list."""
    _keyed(monkeypatch)
    _set_up(tmp_path)
    usage.set_answer(tmp_path, True)
    recorder = _Recorder()
    with _served(tmp_path, recorder) as browser:
        usage.report("wizard_done", wizard="setup")
        _settle()
        page = browser.request("GET", "/usage")[2]
        assert "Usage reports are on." in page
        assert "&quot;wizard_done&quot;" in page
        page = browser.request("POST", "/usage/no")[2]
        assert "Usage reports are off." in page
        assert "wizard_done" not in page
    assert usage.answer(tmp_path) is False


def test_every_screen_links_to_the_usage_screen(tmp_path):
    """Breaks when the top bar loses the link (§ 4.3)."""
    with _served(tmp_path, _Recorder()) as browser:
        page = browser.request("GET", "/usage")[2]
    assert '<a href="/usage">Usage reports</a>' in page


def test_an_error_status_is_logged_and_a_success_is_not():
    """PRESS-0262 § 4.5, PRESS-0331: the shared client returns an error
    status rather than raising it, so `_send` reads the status. Breaks when
    `_send` ignores the answer again: a report Google refused then leaves no
    log line at all."""
    class _Answers:
        def __init__(self, status):
            self.status = status

        def request(self, *args):
            return self.status, {}, b""

    notes: list[str] = []
    usage._send(_Answers(400), "https://x.invalid/mp/collect", b"{}", "screen", notes.append)
    usage._send(_Answers(204), "https://x.invalid/mp/collect", b"{}", "press", notes.append)
    assert notes == ["usage report screen not sent: status 400"]


def test_a_failed_send_logs_no_secret_and_no_url():
    """Security (PRESS-0262): when a report cannot be sent, the one log line
    names the event and the exception type only -- never the address, which
    carries the api_secret in its query. Breaks when `_send` logs str(exc) or
    the url instead of type(exc).__name__."""
    notes: list[str] = []

    class _Raiser:
        def request(self, *args):
            raise OSError("POST https://x/mp/collect?api_secret=plain-words-secret failed")

    url = ("https://www.google-analytics.com/mp/collect"
           "?measurement_id=G-PLAINWORDS&api_secret=plain-words-secret")
    usage._send(_Raiser(), url, b"{}", "screen", notes.append)
    assert notes and "not sent" in notes[0]
    assert "plain-words-secret" not in notes[0]
    assert "api_secret" not in notes[0]
    assert "google-analytics" not in notes[0]
