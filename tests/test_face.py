# The Face: the error contract and the local server (PRESS-0011).
#
# Each test names the invariant it holds, from docs/specs/PRESS-0011-face.md
# § 5. The words the Face must show are written out here rather than imported
# from face.py: shared, they would compare the module against itself and pass
# whatever it said (the trap CLAUDE.md records for test_settings.py).
#
# Every server is started inside the test that uses it, never in a fixture, so
# a red run against a stub fails in the test body for the stub's reason.
from __future__ import annotations

import http.client
import importlib
import inspect
import pkgutil
import socket
import urllib.parse
from pathlib import Path

import pytest

import pressless
from pressless import credentials, face, insights, publisher, store

LABEL_WORDS = "the Pressless-data folder, beside the program"
LOG_NAME = "pressless.log"
UNCHANGED_WORDS = "Your site has not changed."
UNFORESEEN_WHAT = "Something went wrong that Pressless did not expect."
UNFORESEEN_NEXT = "Try again, and send the details below to whoever helps you."
NOTICE_NEXT_WORDS = "Nothing was lost. Send this to whoever helps you if you did not expect it."

SENTINEL_WORD = "SENTINEL-SECRET-4f1c"
SENTINEL_PATH = "/home/sentinel-user/private/draft.txt"


def _failure_types() -> list[type[Exception]]:
    """Every failure type the package defines, found by walking it (INV-1).

    The walk, not a hand list, is what lets a part's new failure type fail
    this: a list would have to be remembered, which is the thing that fails.
    """
    found: list[type[Exception]] = []
    for info in pkgutil.iter_modules(pressless.__path__):
        module = importlib.import_module(f"pressless.{info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, Exception)
                and not issubclass(cls, Warning)
                and cls.__module__ == module.__name__
            ):
                found.append(cls)
    return found


def _log_text(folder: Path) -> str:
    target = folder / LOG_NAME
    return target.read_text(encoding="utf-8") if target.exists() else ""


class _Client:
    """Talks to a served Face with every header under the test's control."""

    def __init__(self, served: face.Face) -> None:
        parts = urllib.parse.urlsplit(served.url)
        assert parts.port is not None
        self.port = parts.port
        self.secret = urllib.parse.parse_qs(parts.query)["t"][0]
        self.host = f"127.0.0.1:{self.port}"
        self.origin = f"http://{self.host}"
        self.cookie = f"pressless-{self.port}={self.secret}"

    def request(
        self,
        method: str,
        path: str,
        *,
        host: str | None = None,
        cookie: bool = True,
        origin: str | None = None,
    ) -> tuple[int, dict[str, str], str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", host or self.host)
            if cookie:
                conn.putheader("Cookie", self.cookie)
            if origin:
                conn.putheader("Origin", origin)
            if method == "POST":
                conn.putheader("Content-Length", "0")
            conn.endheaders()
            response = conn.getresponse()
            body = response.read().decode("utf-8", "replace")
            return response.status, dict(response.getheaders()), body
        finally:
            conn.close()


def test_every_failure_type_has_a_sentence() -> None:
    """INV-1."""
    types = _failure_types()
    # Both modules that share short names must be reached, or the walk proves
    # nothing about keying by class rather than by name.
    assert publisher.Refused in types and insights.Refused in types

    missing = [f"{t.__module__}.{t.__qualname__}" for t in types if t not in face.SENTENCES]
    assert not missing, (
        f"these failure types have no sentence of their own: {missing}. "
        "docs/design.md § Errors: every failure type carries a written sentence."
    )
    for kind in types:
        sentence = face.SENTENCES[kind]
        assert sentence.what.strip(), kind
        assert sentence.next.strip(), kind
        assert isinstance(sentence.site, face.Site), kind


def test_what_it_means_for_his_site() -> None:
    """INV-2."""
    unknown, unchanged = face.Site.UNKNOWN, face.Site.UNCHANGED
    assert unchanged.value == UNCHANGED_WORDS

    for kind, sentence in face.SENTENCES.items():
        expected = unknown if kind is publisher.OutcomeUnknown else unchanged
        assert sentence.site is expected, kind

    for publishing in (True, False):
        outcome = face.sentence_for(publisher.OutcomeUnknown("x"), publishing=publishing)
        assert outcome.site is unknown
    assert face.sentence_for(publisher.Conflict("x"), publishing=True).site is unchanged

    class Unseen(publisher.Conflict):
        """A subclass with no entry of its own: unforeseen, not its base."""

    for publishing, site in ((True, unknown), (False, unchanged)):
        for failure in (Unseen("x"), RuntimeError("x")):
            sentence = face.sentence_for(failure, publishing=publishing)
            assert sentence.site is site, (failure, publishing)
            assert sentence.what == UNFORESEEN_WHAT
            assert sentence.next == UNFORESEEN_NEXT


def test_details_carry_no_cause(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """INV-3."""
    try:
        try:
            raise OSError(f"{SENTINEL_WORD} {SENTINEL_PATH}")
        except OSError as cause:
            raise store.StoreError("a draft could not be read") from cause
    except store.StoreError as caught:
        failure = caught

    details = face.details_for(failure)
    assert details == "pressless.store.StoreError: a draft could not be read"

    served = face.serve(tmp_path, open_browser=False)
    try:
        page = served.fail(failure, publishing=False)
    finally:
        served.stop()
    logged = _log_text(tmp_path)
    assert "a draft could not be read" in logged
    for surface in (details, page, logged):
        assert SENTINEL_WORD not in surface
        assert SENTINEL_PATH not in surface

    assert face.details_for(OSError(f"cannot open {SENTINEL_PATH}")) == "OSError"

    rejected = insights.InsightsError("Google refused the request", detail="GOOGLE-SAID-quota")
    assert "GOOGLE-SAID-quota" in face.details_for(rejected)

    def broken(request: face.Request) -> str:
        raise RuntimeError(f"{SENTINEL_WORD} {SENTINEL_PATH}")

    served = face.serve(tmp_path, open_browser=False)
    try:
        served.add_page("GET", "/", broken)
        client = _Client(served)
        capfd.readouterr()
        status, _, body = client.request("GET", "/")
        # An exception escaping a request entirely goes to the server's
        # handle_error; the standard one prints a traceback to the console.
        try:
            raise RuntimeError(SENTINEL_PATH)
        except RuntimeError:
            served._server.handle_error(None, ("127.0.0.1", 0))
    finally:
        served.stop()
    out, err = capfd.readouterr()
    assert status == 500
    assert UNFORESEEN_WHAT in body
    assert SENTINEL_WORD not in body and SENTINEL_PATH not in body
    assert out == "" and err == "", f"the console carried {out + err!r}"


def test_a_credential_failure_names_the_secret() -> None:
    """INV-4."""
    noun = "SENTINEL-NOUN"
    for kind in (credentials.NoStore, credentials.NotStored, credentials.CredentialError):
        sentence = face.sentence_for(kind("x"), publishing=False, secret=noun)
        assert noun in sentence.what, kind


def test_the_server_answers_only_its_own_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-5."""
    opened: list[Path] = []
    monkeypatch.setattr(face, "_open_folder", opened.append)
    served = face.serve(tmp_path, open_browser=False)
    try:
        client = _Client(served)
        assert urllib.parse.urlsplit(served.url).hostname == "127.0.0.1"
        # Bound to 127.0.0.1 alone, so another loopback address is refused.
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.2", client.port), timeout=2).close()

        assert client.request("GET", "/", cookie=False)[0] == 403

        status, headers, _ = client.request("GET", f"/?t={client.secret}", cookie=False)
        assert status in (302, 303)
        set_cookie = headers.get("Set-Cookie", "")
        assert set_cookie.startswith(f"pressless-{client.port}={client.secret}")
        assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie
        assert headers.get("Location") == "/"

        assert client.request("GET", "/?t=wrong", cookie=False)[0] == 403
        assert client.request("GET", "/")[0] == 200
        assert client.request("GET", "/", host="pressless.example")[0] == 403
        status = client.request("POST", "/folder/open", origin="http://127.0.0.1:1")[0]
        assert status == 403
        assert opened == []
    finally:
        served.stop()


def test_a_failure_is_escaped_on_the_page() -> None:
    """INV-6."""
    fragment = face.render_failure(
        store.StoreError("<script>alert(1)</script>"), publishing=False
    )
    notices = face.render_notices(["<script>alert(2)</script> was passed over"])
    for shown in (fragment, notices):
        assert "&lt;script&gt;" in shown
        assert "<script>" not in shown


def test_the_details_name_the_label_not_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-7."""
    opened: list[Path] = []
    monkeypatch.setattr(face, "_open_folder", opened.append)
    served = face.serve(tmp_path, open_browser=False)
    try:
        fragment = served.fail(store.StoreError("a draft could not be read"), publishing=False)
        client = _Client(served)
        status, headers, body = client.request("GET", "/folder/location")
        open_status = client.request("POST", "/folder/open", origin=client.origin)[0]
    finally:
        served.stop()
    assert LABEL_WORDS in fragment
    assert LOG_NAME in fragment
    assert str(tmp_path) not in fragment
    assert status == 200
    assert headers.get("Content-Type", "").startswith("text/plain")
    assert body == str(tmp_path)
    assert open_status in (200, 204)
    assert opened == [tmp_path]


def test_a_notice_is_shown_and_the_call_completes(tmp_path: Path) -> None:
    """INV-8."""
    shelf = tmp_path / "store"
    (shelf / "published").mkdir(parents=True)
    (shelf / "published" / ".txt").write_text("hand-dropped", encoding="utf-8")
    home = tmp_path / "data"
    home.mkdir()

    served = face.serve(home, open_browser=False)
    try:
        with served.capture() as notices:
            # One call site, twice: the default warnings filter keys on where a
            # warning is raised, so only a repeat from the same line tests it.
            # Two separate calls are two places, and pass under that filter.
            listings = [store.list_slugs(shelf, draft=False) for _ in range(2)]
    finally:
        served.stop()

    assert listings == [(), ()]
    assert len(notices) == 2, notices
    assert _log_text(home).count("passed over") == 2
    shown = face.render_notices(notices)
    assert shown.count(UNCHANGED_WORDS) == 2
    assert shown.count(NOTICE_NEXT_WORDS) == 2


def test_the_secret_is_never_printed_or_logged(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """INV-9."""
    capfd.readouterr()
    served = face.serve(tmp_path, open_browser=False)
    try:
        client = _Client(served)
        client.request("GET", f"/?t={client.secret}", cookie=False)
        client.request("GET", "/")
    finally:
        served.stop()
    out, err = capfd.readouterr()
    assert client.secret not in out + err + _log_text(tmp_path)
