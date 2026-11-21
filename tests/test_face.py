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

import html
import http.client
import importlib
import inspect
import json
import os
import pkgutil
import re
import shutil
import socket
import stat
import subprocess
import sys
import urllib.parse
import warnings
from pathlib import Path

import pytest
from _face_session import Browser, follow_link, session_cookie
from test_publishing import _entry
from test_setup import _saved

import pressless
from pressless import (
    credentials,
    editor,
    face,
    insights,
    look,
    overview,
    page_editor,
    publisher,
    settings,
    sites,
    store,
    themes,
    usage,
)

LABEL_WORDS = "the Pressless-data folder, beside the program"
LOG_NAME = "pressless.log"
UNCHANGED_WORDS = "Your site has not changed."
UNFORESEEN_WHAT = "Something went wrong that Pressless did not expect."
UNFORESEEN_NEXT = "Try again, and send the details below to whoever helps you."
NOTICE_NEXT_WORDS = "Nothing was lost. Send this to whoever helps you if you did not expect it."

SENTINEL_WORD = "SENTINEL-SECRET-4f1c"
SENTINEL_PATH = "/home/sentinel-user/private/draft.txt"


# Each system's tray half imports what only that system has, so tray.py
# imports one (PRESS-0204 § 4.1). Neither defines a failure type.
_OTHER_SYSTEMS_TRAY = "_tray_linux" if sys.platform == "win32" else "_tray_windows"


def _failure_types() -> list[type[Exception]]:
    """Every failure type the package defines, found by walking it (INV-1).

    The walk, not a hand list, is what lets a part's new failure type fail
    this: a list would have to be remembered, which is the thing that fails.
    """
    found: list[type[Exception]] = []
    for info in pkgutil.iter_modules(pressless.__path__):
        if info.name == _OTHER_SYSTEMS_TRAY:
            continue
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


class _Client(Browser):
    """Sends Origin only when a test names one, and keeps the link's secret."""

    def __init__(self, served: face.Face, *, follow: bool = True) -> None:
        super().__init__(served, follow=follow)
        self.secret = urllib.parse.parse_qs(urllib.parse.urlsplit(served.url).query)["t"][0]

    def request(self, method: str, path: str, form: dict[str, str] | None = None, *,
                cookie: bool = True, origin: str | None = None,
                host: str | None = None) -> tuple[int, dict[str, str], str]:
        return super().request(method, path, form, cookie=cookie, origin=origin, host=host)


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


class _NamesItsSecret(Exception):
    """A failure carrying its own `secret` slot. Not a PublishError, so the
    every-type walk above never meets it."""

    def __init__(self) -> None:
        super().__init__("made up")
        self.slots = {"secret": "the made-up key"}


def test_a_failure_may_carry_a_secret_slot(monkeypatch) -> None:
    """PRESS-0305. Breaks when a failure's own `secret` slot collides with
    the one the Face fills, and the sentence raises instead of being said.
    A secret the Face names wins; the failure's own comes next."""
    monkeypatch.setitem(face.SENTENCES, _NamesItsSecret, face.SENTENCES[credentials.NotStored])
    own = face.sentence_for(_NamesItsSecret(), publishing=False)
    named = face.sentence_for(_NamesItsSecret(), publishing=False,
                              secret="the named key")  # noqa: S106 -- a label, not a secret
    assert own.what == "Pressless does not have the made-up key yet."
    assert named.what == "Pressless does not have the named key yet."


class _LeavesAGap(Exception):
    """A failure whose sentence has a gap it does not fill."""


def test_a_sentence_with_an_unfilled_gap_says_the_unforeseen_one(monkeypatch) -> None:
    """§ Errors' last-resort path runs sentence_for, so a KeyError there left
    the connection closed with no answer. Breaks when a gap the failure does
    not fill raises instead of falling back to the unforeseen sentence."""
    monkeypatch.setitem(face.SENTENCES, _LeavesAGap,
                        face.Sentence("failure.log", face.Site.UNCHANGED, "failure.again"))
    sentence = face.sentence_for(_LeavesAGap(), publishing=True)
    assert sentence == face.sentence_for(RuntimeError(), publishing=True)


def test_a_part_failing_on_every_page_still_lets_the_page_through(tmp_path: Path,
                                                                  monkeypatch) -> None:
    """PRESS-0337 § 4.6: what a part adds to every page is drawn for every
    page, failure pages included. Breaks when one part raising, or reading
    the site's name, loses the page itself, and the browser gets a closed
    connection."""
    served = face.serve(tmp_path)

    def broken() -> str:
        raise RuntimeError("a part's own failure")

    monkeypatch.setattr(served, "site_name", broken)
    try:
        served.add_to_every_page(broken)
        served.add_to_every_page(lambda: "<p>still here</p>")
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        status, _, body = _Client(served).request("GET", "/words")
    finally:
        served.stop()
    assert status == 200 and "<p>Words</p>" in body and "still here" in body


def test_a_refused_sign_in_sends_him_to_sign_in_again() -> None:
    """PRESS-0233. Breaks when GitHub refusing a sign-in tells him to enter a
    publishing key again, which a signed-in person never made."""
    sentence = face.sentence_for(publisher.SignInRefused("x"), publishing=True)
    assert sentence.what == "GitHub would not accept Pressless's sign-in."
    assert sentence.next == "Sign in to GitHub again in Settings, then try again."
    assert sentence.link == ("/setup/github", "Sign in to GitHub again")


def test_what_it_means_for_his_site() -> None:
    """INV-2."""
    unknown, unchanged = face.Site.UNKNOWN, face.Site.UNCHANGED
    assert unchanged.words == UNCHANGED_WORDS

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

    served = face.serve(tmp_path)
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

    served = face.serve(tmp_path)
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


def test_a_return_page_is_the_only_door_without_the_cookie(tmp_path: Path) -> None:
    """PRESS-0122 INV-9. Breaks when add_return_page switches the cookie check
    off for the whole Face, or for every method."""
    served = face.serve(tmp_path)
    try:
        served.add_return_page("/back", lambda request: "came back")
        served.add_page("POST", "/back", lambda request: "posted")
        served.add_page("GET", "/other", lambda request: "other")
        client = _Client(served)
        status, _, body = client.request("GET", "/back?state=x", cookie=False)
        assert (status, "came back" in body) == (200, True)
        assert client.request("POST", "/back", cookie=False)[0] == 403
        assert client.request("GET", "/other", cookie=False)[0] == 403
        assert client.request("GET", "/back", cookie=False, host="pressless.example")[0] == 403
        assert client.request("GET", "/other")[0] == 200
    finally:
        served.stop()


def test_another_programs_odd_cookie_does_not_lock_him_out(tmp_path: Path) -> None:
    """PRESS-0011 § 4.5: browsers share cookies across every port of
    127.0.0.1, so another local program's cookies arrive beside Pressless's.
    Breaks when one the standard parser cannot read throws the whole header
    away and every page answers 403. A cookie merely named like the session
    still opens nothing."""
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/other", lambda request: "other")
        client = _Client(served)
        own = client.cookie
        for before in ("junk", "path=/", 'a=1; b={"k":"v"}', "a=b c", 'a="x'):
            client.cookie = f"{before}; {own}"
            assert client.request("GET", "/other")[0] == 200, before
        name = own.split("=", 1)[0]
        client.cookie = f"{name}x={own.split('=', 1)[1]}; {name}=wrong"
        assert client.request("GET", "/other")[0] == 403
    finally:
        served.stop()


SPENT = "This link has already been used. Close this tab and start Pressless again."


def test_the_server_answers_only_its_own_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-5."""
    opened: list[Path] = []
    monkeypatch.setattr(face, "_open_folder", opened.append)
    served = face.serve(tmp_path)
    try:
        client = _Client(served, follow=False)
        assert urllib.parse.urlsplit(served.url).hostname == "127.0.0.1"
        # Bound to 127.0.0.1 alone, so another loopback address is refused.
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.2", client.port), timeout=2).close()

        assert client.request("GET", "/", cookie=False)[0] == 403
        assert client.request("GET", "/?t=wrong", cookie=False)[0] == 403

        status, headers = follow_link(served.url)
        assert status in (302, 303)
        set_cookie = headers.get("Set-Cookie", "")
        name, _, value = set_cookie.split(";", 1)[0].partition("=")
        assert name == f"pressless-{client.port}"
        # The session is not the link's secret: the link sits on the browser's
        # command line, where another account can read it (§ 3 decision 3).
        assert value and value != client.secret
        assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie
        assert headers.get("Location") == "/"

        client.cookie = f"{name}={value}"
        assert client.request("GET", "/")[0] == 200
        # The link is spent, and its secret is never a session. A reload or Back
        # lands on it: with the session it goes on to the page, without it he
        # is told to start Pressless again (PRESS-0245).
        assert follow_link(served.url)[0] == 403
        status, _, body = client.request("GET", "/?t=spent", cookie=False)
        assert status == 403 and body == SPENT, body
        status, headers, _ = client.request("GET", f"/?t={client.secret}")
        assert (status, headers.get("Location")) == (303, "/")
        assert "Set-Cookie" not in headers
        secret_as_cookie = _Client(served, follow=False)
        secret_as_cookie.cookie = f"{name}={client.secret}"
        assert secret_as_cookie.request("GET", "/")[0] == 403
        assert client.request("GET", "/", host="pressless.example")[0] == 403
        status = client.request("POST", "/folder/open", origin="http://127.0.0.1:1")[0]
        assert status == 403
        assert opened == []
    finally:
        served.stop()


@pytest.mark.parametrize("spend_first", [True, False], ids=["spent", "unspent"])
def test_a_fresh_link_admits_once_and_retires_the_one_before(
        tmp_path: Path, spend_first: bool) -> None:
    """PRESS-0204 INV-1 and INV-2: the tray's Open makes a new one-use link.
    It sets the cookie once; the link before it, spent or not, no longer
    admits; and a cookie set before it still does.

    Breaks when fresh_link re-arms the old secret, keeps a second secret
    beside it, or replaces the session."""
    served = face.serve(tmp_path)
    try:
        old = served.url
        earlier = session_cookie(old) if spend_first else None
        fresh = served.fresh_link("/settings")
        assert fresh != old and served.url != old
        assert urllib.parse.urlsplit(served.url).path == "/"

        # The old link first: once the fresh one is spent, a re-armed old
        # secret would be spent too, and pass for retired.
        assert follow_link(old)[0] == 403, "the link before it still admits"
        status, headers = follow_link(fresh)
        assert status == 303 and headers.get("Location") == "/settings"
        assert headers.get("Set-Cookie", "").startswith(f"pressless-{served.port}=")
        assert follow_link(fresh)[0] == 403, "the fresh link admitted twice"

        if earlier is not None:
            client = _Client(served, follow=False)
            client.cookie = earlier
            assert client.request("GET", "/")[0] == 200, "the session was replaced"
    finally:
        served.stop()


def test_serve_binds_the_port_it_is_given(tmp_path: Path) -> None:
    """INV-11: the practice copy's start script names a port (PRESS-0202)."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    served = face.serve(tmp_path, port=port)
    try:
        assert served.url.startswith(f"http://127.0.0.1:{port}/")
        status, headers = follow_link(served.url)
        assert status in (302, 303)
        assert headers.get("Set-Cookie", "").startswith(f"pressless-{port}=")
    finally:
        served.stop()

    first, second = face.serve(tmp_path), face.serve(tmp_path)
    try:
        ports = {urllib.parse.urlsplit(each.url).port for each in (first, second)}
        assert len(ports) == 2 and 0 not in ports
    finally:
        first.stop()
        second.stop()

    # Held, so the bind fails: nothing falls back to another port (§ 4.5).
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        with pytest.raises(OSError):
            face.serve(tmp_path, port=held.getsockname()[1])


def test_a_failure_is_escaped_on_the_page() -> None:
    """INV-6."""
    fragment = face.render_failure(
        store.StoreError("<script>alert(1)</script>"), publishing=False
    )
    notices = face.render_notices(["<script>alert(2)</script> was passed over"])
    kept = face.render_notices([face.Notice("<script>alert(3)</script> was left",
                                            face.Site.UPDATED)])
    for shown in (fragment, notices, kept):
        assert "&lt;script&gt;" in shown
        assert "<script>" not in shown


def test_the_details_name_the_label_not_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-7."""
    opened: list[Path] = []
    monkeypatch.setattr(face, "_open_folder", opened.append)
    served = face.serve(tmp_path)
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

    served = face.serve(home)
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

    # PRESS-0145: a Notice shows its own site part, never UNCHANGED's.
    updated = face.render_notices([face.Notice("The copy was left.", face.Site.UPDATED)])
    assert "Your site has been updated." in updated
    assert UNCHANGED_WORDS not in updated
    assert NOTICE_NEXT_WORDS in updated


def test_the_top_bar_reads_raise_no_notice(tmp_path: Path) -> None:
    """PRESS-0397: § 4.4 exempts the two reads every page makes outside
    `capture` -- `site_name` and `live_address` -- because they raise no
    notice. Taking the capture lock there would hold every page behind a
    publish. Breaks when either read raises a Store or Settings notice in
    any state the site folder can be in: not set up, unreadable, set up, a
    file readable by others, an identity present or broken."""
    served = face.serve(tmp_path)

    def raised() -> list[str]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            served.live_address()
            served.site_name()
        return [str(each.message) for each in caught
                if issubclass(each.category, (store.StoreNotice, settings.SettingsNotice))]

    identity = store.identity_path_for(tmp_path)
    try:
        seen = {"not set up": raised()}
        settings.path_for(tmp_path).write_text("{", encoding="utf-8")
        seen["unreadable settings"] = raised()
        settings.path_for(tmp_path).unlink()   # setup refuses to save over it
        _saved(tmp_path)
        seen["set up"] = raised()
        store.write_identity(tmp_path, store.Identity("Seaside"))
        seen["identity"] = raised()
        for each in (settings.path_for(tmp_path), identity):
            each.chmod(0o644)
        seen["readable by others"] = raised()
        identity.write_text("[]", encoding="utf-8")
        seen["broken identity"] = raised()
    finally:
        served.stop()
    assert served.site_name() == ""   # the broken identity was read
    assert {state: notices for state, notices in seen.items() if notices} == {}

def test_the_secret_is_never_printed_or_logged(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """INV-9."""
    capfd.readouterr()
    served = face.serve(tmp_path)
    try:
        client = _Client(served, follow=False)
        client.cookie = session_cookie(served.url)
        client.request("GET", "/")
    finally:
        served.stop()
    out, err = capfd.readouterr()
    assert client.secret not in out + err + _log_text(tmp_path)


# ------------------------------------------ PRESS-0012 INV-7, INV-8, INV-9 ---

FILES_POLICY_WORDS = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; script-src 'none'; connect-src 'self'; frame-src 'none'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)
FRAMES_POLICY_WORDS = ("style-src 'self' 'unsafe-inline'; font-src 'self'; "
                       "img-src 'self' data:; frame-src 'self'; frame-ancestors 'self'")
ANCESTORS_WORDS = "frame-ancestors 'self'"


def test_files_never_leave_their_folder(tmp_path: Path) -> None:
    """PRESS-0012 INV-7."""
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    (mounted / "inside.txt").write_text("inside", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("OUTSIDE-BYTES", encoding="utf-8")
    link = mounted / "link.txt"
    try:
        link.symlink_to(tmp_path / "outside.txt")
    except OSError:
        link = None  # a Windows account without the symlink privilege
    served = face.serve(tmp_path / "own")
    try:
        served.add_files("/m/", face.within(mounted))
        served.add_files("/plain/", lambda rest: mounted / rest)
        nested = tmp_path / "nested"
        nested.mkdir()
        (nested / "inside.txt").write_text("nested", encoding="utf-8")
        served.add_files("/m/sub/", face.within(nested))
        client = _Client(served)
        assert client.request("GET", "/m/inside.txt")[0] == 200
        # The longest registered prefix answers, as the editor's assets need.
        assert client.request("GET", "/m/sub/inside.txt")[2] == "nested"
        escapes = ["/m/..", "/m/%2e%2e/outside.txt", "/m/a%2f..%2f..%2foutside.txt",
                   "/m/..%5coutside.txt", "/m/inside.txt%00", "/m//inside.txt"]
        if link is not None:
            escapes.append("/m/link.txt")
        for path in escapes:
            status, _, body = client.request("GET", path)
            assert status == 404, path
            assert "OUTSIDE-BYTES" not in body, path
        # Only the Face's own segment check stands between this and the file.
        status, _, body = client.request("GET", "/plain/%2e%2e/outside.txt")
        assert status == 404 and "OUTSIDE-BYTES" not in body
    finally:
        served.stop()


def test_a_served_file_past_one_piece_arrives_whole(tmp_path: Path) -> None:
    """A kept song or video is sent in pieces rather than read whole into
    memory. Breaks when a piece is dropped, repeated or reordered, or the
    length does not match what is sent."""
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    sent = bytes(range(256)) * (face._PIECE // 256 * 3 + 1)
    (mounted / "song.mp3").write_bytes(sent)
    served = face.serve(tmp_path / "own")
    try:
        served.add_files("/m/", face.within(mounted))
        status, headers, body = _Client(served).raw("GET", "/m/song.mp3")
    finally:
        served.stop()
    assert (status, headers["Content-Length"], body == sent) == (200, str(len(sent)), True)
    assert headers["Content-Security-Policy"] == FILES_POLICY_WORDS


def test_files_carry_the_policy(tmp_path: Path) -> None:
    """PRESS-0012 INV-8."""
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    types = {"page.HTML": "text/html; charset=utf-8", "site.css": "text/css; charset=utf-8",
             "site.js": "text/javascript; charset=utf-8",
             "dusk.AVIF": "image/avif",   # PRESS-0274
             "notes.txt": "text/plain; charset=utf-8",   # PRESS-0197
             "notes.unknown": "application/octet-stream"}
    for name in types:
        (mounted / name).write_bytes(b"x")
    served = face.serve(tmp_path / "own")
    try:
        served.add_files("/m/", face.within(mounted))
        client = _Client(served)
        for name, kind in types.items():
            status, headers, _ = client.request("GET", f"/m/{name}")
            assert status == 200, name
            assert headers.get("Content-Security-Policy") == FILES_POLICY_WORDS, name
            assert headers.get("X-Content-Type-Options") == "nosniff", name
            assert headers.get("Cache-Control") == "no-store", name
            assert headers.get("Content-Type") == kind, name
    finally:
        served.stop()


def test_every_page_links_to_settings(tmp_path: Path) -> None:
    """PRESS-0193. Breaks when the top bar loses the Settings link, on an
    ordinary page or on a failure page."""
    def broken(request: face.Request) -> str:
        raise ValueError("x")

    _set_up(tmp_path)
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        served.add_page("GET", "/broken", broken)
        client = _Client(served)
        for path, expected in (("/words", 200), ("/broken", 500)):
            status, _, body = client.request("GET", path)
            bar = body.split('<header class="bar">', 1)[1].split("</header>", 1)[0]
            assert status == expected, path
            assert '<a href="/setup">Settings</a>' in bar, path
    finally:
        served.stop()


def test_every_page_links_back_to_your_site(tmp_path: Path) -> None:
    """PRESS-0281. Breaks when the top bar has no way back to Your site, on an
    ordinary page or on a failure page."""
    def broken(request: face.Request) -> str:
        raise ValueError("x")

    _set_up(tmp_path)
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        served.add_page("GET", "/broken", broken)
        client = _Client(served)
        for path, expected in (("/words", 200), ("/broken", 500)):
            status, _, body = client.request("GET", path)
            bar = body.split('<header class="bar">', 1)[1].split("</header>", 1)[0]
            assert status == expected, path
            assert '<a href="/">Your site</a>' in bar, path
    finally:
        served.stop()


def test_the_bar_names_the_parts_of_a_site(tmp_path: Path) -> None:
    """INV-1 (PRESS-0353 § 4.2), with PRESS-0343's More: on a normal page and a
    failure page the parts of a site stand on the bar in order, and Report,
    Usage, About and the two pickers stay under More. Breaks when a link is
    missing, added or out of order, or View your site is still in the bar."""
    def broken(request: face.Request) -> str:
        raise ValueError("x")

    _saved(tmp_path)
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        served.add_page("GET", "/broken", broken)
        client = _Client(served)
        bodies = [client.request("GET", path) for path in ("/words", "/broken")]
    finally:
        served.stop()
    assert [status for status, _, _ in bodies] == [200, 500]
    for _, _, body in bodies:
        bar = body.split('<header class="bar">', 1)[1].split("</header>", 1)[0]
        more = re.search(r'<details class="more">(.*?)</details>', bar, re.S)
        assert more, "no More menu"
        standing = bar.replace(more.group(0), "")
        assert re.findall(r'<a href="([^"]*)"', standing) == [
            "/sites", "/", "/pages", "/journal", "/look", "/files", "/visitors", "/setup",
            "/manual"]
        assert "<select" not in standing and "data-site" not in standing
        assert "View your site" not in standing
        for inside in ('href="/report"', 'href="/about"', usage.ADDRESS,
                       "data-theme-picker", "data-size-picker"):
            assert inside in more.group(1), inside


def test_a_piece_shows_in_its_place(tmp_path: Path) -> None:
    """INV-5 (PRESS-0353 § 4.6). Breaks when places share one list, or a
    mistyped place is accepted and its piece never shows."""
    served = face.serve(tmp_path)
    try:
        served.add_piece("journal-below", lambda: "<p>a journal piece</p>")
        with pytest.raises(ValueError):
            served.add_piece("nowhere", lambda: "<p>lost</p>")
        assert served.pieces("journal-below") == ["<p>a journal piece</p>"]
        assert all(served.pieces(place) == [] for place in face.PLACES
                   if place != "journal-below")
        editor.register(served, tmp_path)
        overview.register(served, tmp_path)
        client = _Client(served)
        journal = client.request("GET", "/journal")[2]
        home = client.request("GET", "/")[2]
    finally:
        served.stop()
    assert "a journal piece" in journal and "a journal piece" not in home


def test_the_bar_leaves_the_live_site_to_your_site_screen(tmp_path: Path) -> None:
    """PRESS-0232, as PRESS-0353 § 4.2 reshapes it: View your site is no
    longer in the top bar, set up or not, and a missing or unreadable
    settings file stops no page from rendering. Breaks when the link returns
    to the bar or the bar reads the settings in a way that fails a page."""
    def broken(request: face.Request) -> str:
        raise ValueError("x")

    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        served.add_page("GET", "/broken", broken)
        client = _Client(served)

        def bars() -> list[tuple[int, str]]:
            found = []
            for path in ("/words", "/broken"):
                status, _, body = client.request("GET", path)
                found.append((status, body.split('<header class="bar">', 1)[1]
                              .split("</header>", 1)[0]))
            return found

        assert [status for status, _ in bars()] == [200, 500]
        _saved(tmp_path)
        (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
        for (status, bar), expected in zip(bars(), (200, 500), strict=True):
            assert status == expected and '<a href="/sites">Sites</a>' in bar
        (tmp_path / "settings.json").unlink()
        _saved(tmp_path)
        for status, bar in bars():
            assert "View your site" not in bar and "data-site" not in bar, status
            assert '<a href="/setup">Settings</a>' in bar, status
    finally:
        served.stop()


def test_view_your_site_is_live_only_with_something_to_see(tmp_path: Path) -> None:
    """PRESS-0234. Breaks when the button beside Press to site is live with
    no address, or while a part says there is nothing to see, or is greyed
    out once there is a site."""
    def button(address: str, live: bool) -> str:
        return (f'<button type="button" data-view-site="{address}"'
                f'{"" if live else " disabled"}>View your site</button>')

    served = face.serve(tmp_path)
    try:
        assert served.view_site() == button("", False)
        _saved(tmp_path)
        assert served.view_site() == button("https://example.org", True)
        unseen = [True]
        served.add_unseen(lambda: unseen[0])
        assert served.view_site() == button("https://example.org", False)
        unseen[0] = False
        assert served.view_site() == button("https://example.org", True)
    finally:
        served.stop()


def test_a_reply_is_sent_as_given(tmp_path: Path) -> None:
    """PRESS-0012 INV-9."""
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/moved", lambda request: face.Reply(
            b"", "text/plain", status=303, location="/elsewhere"))
        served.add_page("GET", "/data", lambda request: face.Reply(
            b'{"a": 1}', "application/json"))
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        client = _Client(served)

        status, headers, body = client.request("GET", "/moved")
        assert status == 303 and headers.get("Location") == "/elsewhere" and body == ""
        status, headers, body = client.request("GET", "/data")
        assert status == 200 and headers.get("Content-Type") == "application/json"
        assert body == '{"a": 1}'
        status, headers, body = client.request("GET", "/words")
        assert status == 200 and body.startswith("<!doctype html>") and "<p>Words</p>" in body
        assert headers.get("Content-Security-Policy") == FRAMES_POLICY_WORDS
    finally:
        served.stop()


def _served_style(tmp_path: Path) -> tuple[str, str]:
    """The page the Face serves for a bare body, and the stylesheet inside it."""
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        status, _, body = _Client(served).request("GET", "/words")
    finally:
        served.stop()
    assert status == 200
    style = re.search(r"<style>(.*?)</style>", body, re.S)
    assert style, "the page carries no stylesheet"
    return body, style.group(1)


def test_every_page_carries_a_light_and_a_dark_look(tmp_path: Path) -> None:
    """PRESS-0178: the look follows the system, and every screen has it."""
    body, style = _served_style(tmp_path)
    assert '<body class="face">' in body
    assert "color-scheme: light dark" in style
    assert "@media (prefers-color-scheme: dark)" in style


def test_every_page_shows_the_app_icon_in_its_tab(tmp_path: Path) -> None:
    """PRESS-0240: the browser tab carries the packaged icon, drawn inline so
    the Face serves no file for it."""
    body, _ = _served_style(tmp_path)
    head = body.split("</head>", 1)[0]
    found = re.search(r'<link rel="icon" href="data:image/svg\+xml,([^"]*)">', head)
    assert found, "the page carries no icon"
    icon = Path(__file__).resolve().parents[1] / "packaging" / "icons" / "pressless-icon.svg"
    assert urllib.parse.unquote(found.group(1)) == icon.read_text(encoding="utf-8").strip()


def test_the_look_is_scoped_and_leaves_the_box_to_his_site(tmp_path: Path) -> None:
    """PRESS-0178: the editor links his site's stylesheets into the same page.

    Every rule sits under `.face`, so a bare `body` or `a` rule of his cannot
    restyle the Face. And the box is only ever reached through `:where()`, so
    his `.post-body` rule outranks it and he types in his site's own font
    (PRESS-0012: the box takes builder.BODY_CLASS).
    """
    _, style = _served_style(tmp_path)
    selectors = [group for group in re.findall(r"([^{}]+)\{", style)
                 if not group.strip().startswith("@")]
    assert selectors, "no rules were read"
    for group in selectors:
        for selector in group.split(","):
            selector = selector.strip()
            assert selector.startswith((".face", "body.face", ":root")), selector
            assert "textarea" not in re.sub(r":where\([^)]*\)", "", selector), selector


def test_his_body_rule_cannot_lay_out_the_face(tmp_path: Path) -> None:
    """PRESS-0133's 0.8.0 run: the Meadow look's `body { display: grid }` set a
    property no `.face` rule sets, so it laid the editor out in two columns.
    Breaks when the Face's body rule stops resetting every property first."""
    _, style = _served_style(tmp_path)
    body = re.search(r"body\.face\s*\{([^}]*)\}", style)
    assert body is not None, "no body.face rule"
    assert body.group(1).strip().startswith("all: unset;"), body.group(1)
    assert "display: block;" in body.group(1), body.group(1)


def _properties(style: str) -> dict[str, set[str]]:
    """Each selector in `style`, with the property names its rules set."""
    found: dict[str, set[str]] = {}
    for group, body in re.findall(r"([^{}]+)\{([^{}]*)\}", style):
        names = {part.partition(":")[0].strip() for part in body.split(";") if ":" in part}
        for selector in group.split(","):
            found.setdefault(selector.strip(), set()).update(names)
    return found


def test_a_site_look_cannot_restyle_the_faces_own_headings(tmp_path: Path) -> None:
    """PRESS-0284: Harbour's `h1 { color: var(--heading) }` reached the
    editor's own h1, which set no colour, and left it near-invisible. Each
    property a starter look sets on a heading the Face styles, the Face sets
    too; a decoration the look adds, the Face takes away.
    Breaks when a `.face` heading rule stops setting one of them."""
    _, style = _served_style(tmp_path)
    own = _properties(style)
    for layout in look.LAYOUTS:
        for selector, names in _properties(look.css(look.defaults(layout), "")).items():
            tag, _, pseudo = selector.partition("::")
            if not re.fullmatch(r"h[1-6]", tag) or f".face {tag}" not in own:
                continue
            if pseudo:
                assert "content" in own.get(f".face {selector}", set()), (layout, selector)
                continue
            missing = {name for name in names - own[f".face {tag}"]
                       if name.partition("-")[0] not in own[f".face {tag}"]}
            assert not missing, (layout, selector, missing)


def test_the_look_reaches_only_the_faces_own_frame(tmp_path: Path) -> None:
    """PRESS-0187: a browser add-on injects its own iframe into every page.

    A rule reaching any iframe gave that empty frame a white card most of the
    screen tall, over the top bar's theme picker. Only the proof frame, which
    the editors mark `#preview`, takes the Face's frame look.
    """
    _, style = _served_style(tmp_path)
    for group in re.findall(r"([^{}]+)\{", style):
        for selector in group.split(","):
            if re.search(r"\biframe\b", selector):
                assert "#preview" in selector, selector.strip()


def _rule(style: str, selector: str) -> str:
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", style)
    assert found, f"no rule for {selector}"
    return found.group(1)


def test_the_bar_and_a_screens_own_links_look_like_buttons(tmp_path: Path) -> None:
    """PRESS-0286. Breaks when the top bar's links, or a screen's own way back
    and view switch, lose the button look, or leave a property a site's own
    `a` rule could set, which would restyle them in the editors."""
    _, style = _served_style(tmp_path)
    rule = _rule(style, ".face .bar > a, .face .nav > a")
    for declaration in ("display: inline-block", "color: var(--ink)",
                        "background: var(--sheet)", "border: 1px solid var(--line)",
                        "border-radius: 999px", "text-decoration: none", "font-weight: 600"):
        assert declaration in rule, declaration
    # On the bar's own sheet, a bar link takes the paper, so it stands out.
    assert "background: var(--paper)" in _rule(style, ".face .bar > a")
    hover = _rule(style, ".face .bar > a:hover, .face .nav > a:hover")
    assert "color: var(--ink)" in hover and "border-color: var(--amber)" in hover


@pytest.mark.parametrize("address", ["/edit?slug=seaside",
                                     "/page?kind=pages&name=index",
                                     "/page?kind=pages&name=index&view=code"])
def test_the_editors_way_back_and_switch_are_buttons(tmp_path: Path, address: str) -> None:
    """PRESS-0286. Breaks when an editor's way back or its view switch
    sits outside a `.nav` line, so it shows as a plain link."""
    folder = tmp_path / "data"
    folder.mkdir()
    store.write(folder, _entry("seaside"), draft=True)
    store.write_html(folder, store.PAGES_FOLDER, "index",
                     "<!doctype html><html><head><title>Home</title></head><body><main>"
                     "<!-- pressless:page --><!-- pressless:text --><p>Hi</p>"
                     "<!-- /pressless:text --><!-- /pressless:page --></main></body></html>")
    served = face.serve(folder)
    try:
        editor.register(served, folder)
        page_editor.register(served, folder)
        body = _Client(served).request("GET", address)[2]
    finally:
        served.stop()
    lines = re.findall(r'<p class="nav">(.*?)</p>', body, re.S)
    back = ('<a href="/journal">Journal</a>' if address.startswith("/edit")
            else '<a href="/pages">Pages</a>')
    assert any(back in line for line in lines), address
    if address.startswith("/page"):
        assert any("Show me the code" in line or "View editor" in line
                   for line in lines), address


def test_a_dark_look_dims_the_preview_until_he_asks_for_true_colours(
        tmp_path: Path) -> None:
    """PRESS-0187: the preview shows his site's own colours, so on a dark look
    a light site glares. Every dark look dims it, no light look does, and the
    switch that undoes the dimming shows only where there is dimming."""
    _, style = _served_style(tmp_path)
    for theme in themes.THEMES:
        rule = _rule(style, f':root[data-theme="{theme.key}"]')
        dimmed = "--preview-dim: brightness(" in rule
        switch = "--preview-switch: block" in rule
        assert dimmed == switch == theme.dark, theme.key
    assert "--preview-dim: none" in _rule(style, ":root")
    dark = style[style.index("@media (prefers-color-scheme: dark)"):]
    assert "--preview-dim: brightness(" in _rule(dark, ":root")
    assert "filter: var(--preview-dim)" in _rule(style, ".face iframe#preview")
    assert "filter: none" in _rule(style, ".face iframe#preview.undimmed")
    assert "display: var(--preview-switch)" in _rule(style, ".face .true-colours")
    assert "data-true-colours" in face._SCRIPT


def test_a_round_button_or_tick_box_sits_left_of_its_words(tmp_path: Path) -> None:
    """PRESS-0201: every label stacks its words over a text box, and that put
    the Google step's round buttons centred above each site's name, in a text
    box's frame. A label holding one sits in a row, and the button has no
    frame."""
    _, style = _served_style(tmp_path)
    label = _rule(style, '.face label:has(> input[type="radio"]), '
                         '.face label:has(> input[type="checkbox"])')
    assert "flex-direction: row" in label
    assert "align-items: center" in label
    box = _rule(style, '.face input[type="radio"], .face input[type="checkbox"]')
    assert "padding: 0" in box


def _raises(request: face.Request) -> str:
    raise RuntimeError("a page that fails")


def test_no_other_origin_can_frame_the_face(tmp_path: Path) -> None:
    """PRESS-0011 INV-10. A page on another 127.0.0.1 port is the same site, so
    a frame of a Face page carries the cookie and its clicks carry the Face's
    own Origin (PRESS-0151). Every answer path names frame-ancestors 'self'.

    Breaks when one answer path is left without the directive.
    """
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    (mounted / "page.html").write_bytes(b"<p>x</p>")
    served = face.serve(tmp_path / "own")
    try:
        served.add_files("/m/", face.within(mounted))
        served.add_page("GET", "/data", lambda request: face.Reply(
            b"{}", "application/json"))
        served.add_page("GET", "/fails", _raises)
        sent = tmp_path / "sent.zip"
        sent.write_bytes(b"a file")
        served.add_page("GET", "/down", lambda request: face.Download(sent, "Site.zip"))
        link_status, link_headers = follow_link(served.url)
        client = _Client(served, follow=False)
        client.cookie = link_headers["Set-Cookie"].split(";", 1)[0]
        answers = {
            "the link's redirect": (link_status, link_headers),
            "a wrapped page": client.request("GET", "/")[:2],
            "a page that raises": client.request("GET", "/fails")[:2],
            "a file": client.request("GET", "/m/page.html")[:2],
            "a Reply": client.request("GET", "/data")[:2],
            "a 403": client.request("GET", "/", cookie=False)[:2],
            "a 404": client.request("GET", "/nowhere")[:2],
            "a file 404": client.request("GET", "/m/absent.html")[:2],
            "the folder's location": client.request("GET", "/folder/location")[:2],
            # http.server's own send_error answers these.
            "a method it does not take": client.request("PUT", "/")[:2],
            "a HEAD": client.request("HEAD", "/")[:2],
            "a download": client.request("GET", "/down")[:2],
        }
        for what, (status, headers) in answers.items():
            policy = headers.get("Content-Security-Policy", "")
            directives = [d.strip() for d in policy.split(";")]
            assert "frame-ancestors 'self'" in directives, (what, status, policy)
            assert [d for d in directives if d.startswith("frame-ancestors")] == [
                "frame-ancestors 'self'"], (what, policy)
    finally:
        served.stop()


def test_a_non_ascii_secret_is_refused_not_dropped(tmp_path: Path) -> None:
    """PRESS-0135 #16: § 4.5 refuses a wrong secret with 403. A link or cookie
    carrying a non-ASCII character is a wrong secret too; compare_digest raises
    TypeError on such a str, which dropped the connection and let any page that
    found the port write to the log without the cookie.

    Breaks when the secret is compared as str.
    """
    served = face.serve(tmp_path)
    try:
        client = _Client(served, follow=False)
        assert client.request("GET", "/?t=%C3%A9", cookie=False)[0] == 403
        client.cookie = f"pressless-{client.port}=é"
        assert client.request("GET", "/")[0] == 403
    finally:
        served.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="the xdg-open branch")
@pytest.mark.parametrize("code, fails", [(0, False), (3, True)])
def test_an_opener_that_fails_is_a_folder_not_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, fails: bool
) -> None:
    """PRESS-0135 #19: PRESS-0011 § 6 says the Face says it could not open the
    folder. xdg-open that starts and then fails answered success, because
    nothing waited for it.

    Breaks when the opener's exit status is never read.
    """
    class _Opener:
        def __init__(self, *args, **kwargs):
            pass

        def wait(self, timeout=None):
            return code

    monkeypatch.setattr(face.subprocess, "Popen", _Opener)
    if fails:
        with pytest.raises(face.FolderNotOpened):
            face._open_folder(tmp_path)
    else:
        face._open_folder(tmp_path)


def test_a_body_length_that_is_not_a_count_is_refused(tmp_path) -> None:
    """PRESS-0162 (review-code L5.1): a non-numeric Content-Length raised with
    no answer, and a negative one was truthy, so read(-5) waited for the client
    to close and held the thread. Both are refused with 400, promptly."""
    served = face.serve(tmp_path)
    try:
        served.add_page("POST", "/echo", lambda request: face.Reply(b"ok", "text/plain"))
        client = _Client(served)
        for value in ("-5", "lots"):
            conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=5)
            try:
                conn.putrequest("POST", "/echo", skip_host=True, skip_accept_encoding=True)
                conn.putheader("Host", client.host)
                conn.putheader("Cookie", client.cookie)
                conn.putheader("Content-Length", value)
                conn.endheaders()
                assert conn.getresponse().status == 400, value
            finally:
                conn.close()
    finally:
        served.stop()


def test_a_credential_failure_fits_a_write_as_well_as_a_read() -> None:
    """PRESS-0162 (review-code L6.4): setup's store step raises
    CredentialError where nothing was read, and the sentence said "could
    not safely read" and sent him to re-enter a key -- which a locked
    keyring, or a Windows program started remotely, does not fix."""
    said = face.render_failure(credentials.CredentialError("locked"),
                               publishing=False, secret="your GitHub key")  # noqa: S106 -- a label, not a secret
    assert "safely read" not in said
    assert "unlock" in said


def test_serve_opens_no_browser_and_prints_nothing(tmp_path, monkeypatch, capfd):
    """§ 4.5 (PRESS-0170): the launcher, PRESS-0013 § 4.5, owns opening the
    browser and the line printed where none opens. A second copy here had
    drifted from it and had no production caller."""
    opened = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: opened.append(a) or True)
    served = face.serve(tmp_path)
    served.stop()
    assert opened == []
    printed = capfd.readouterr()
    assert printed.out == "" and printed.err == ""


@pytest.mark.parametrize(("signed_in", "expected"), [(False, 403), (True, 404)])
def test_a_refused_post_is_answered_not_reset(
    tmp_path: Path, signed_in: bool, expected: int,
) -> None:
    """A POST refused before its body is read must still get its 403.

    Closing a socket with unread bytes resets it, and the sender sees a
    dropped connection instead of the answer; Windows CI showed it as
    WinError 10053 on a refused save. A body larger than the socket
    buffers makes Linux show it too.
    """
    served = face.serve(tmp_path)
    try:
        client = _Client(served)
        body = b"x" * (16 * 1024 * 1024)
        conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=10)
        try:
            headers = {"Host": client.host, "Content-Length": str(len(body))}
            if signed_in:
                headers["Cookie"] = client.cookie
            conn.request("POST", "/anything", body=body, headers=headers)
            status = conn.getresponse().status
        finally:
            conn.close()
    finally:
        served.stop()
    assert status == expected


def test_every_page_links_to_the_report_page(tmp_path: Path) -> None:
    """PRESS-0179. Breaks when the top bar loses the link, on an ordinary page
    or on a failure page."""
    def broken(request: face.Request) -> str:
        raise ValueError("x")

    _set_up(tmp_path)
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        served.add_page("GET", "/broken", broken)
        client = _Client(served)
        for path in ("/words", "/broken"):
            _, _, body = client.request("GET", path)
            bar = body.split('<header class="bar">', 1)[1].split("</header>", 1)[0]
            assert '<a href="/report">Suggest or report a problem</a>' in bar, path
    finally:
        served.stop()


def test_an_oversize_registered_post_body_is_refused(tmp_path: Path) -> None:
    """Security: a registered page's POST body is read whole into memory, so a
    Content-Length past the ceiling is refused with 413 before a byte is read.
    Breaks when the cap is dropped and a forged or runaway length is buffered."""
    served = face.serve(tmp_path)
    served.add_page("POST", "/sink", lambda request: "")
    try:
        client = _Client(served)
        conn = socket.create_connection(("127.0.0.1", client.port), timeout=10)
        try:
            request = (
                f"POST /sink HTTP/1.1\r\n"
                f"Host: {client.host}\r\n"
                f"Cookie: {client.cookie}\r\n"
                f"Origin: {client.origin}\r\n"
                f"Content-Type: application/x-www-form-urlencoded\r\n"
                f"Content-Length: {face._MAX_BODY + 1}\r\n"
                f"Connection: close\r\n\r\n"
            )
            conn.sendall(request.encode("ascii") + b"x")
            conn.shutdown(socket.SHUT_WR)
            raw = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
        finally:
            conn.close()
    finally:
        served.stop()
    assert raw.split(b"\r\n", 1)[0].split(b" ")[1] == b"413"


def _held_open(client: _Client, head: str, sent: bytes = b"") -> bytes:
    """Send `head` and `sent`, keep the socket open for writing, and return
    what arrives before the server closes. Raises socket.timeout where the
    server is still waiting for the body after three seconds."""
    conn = socket.create_connection(("127.0.0.1", client.port), timeout=3)
    try:
        conn.sendall(head.encode("ascii") + sent)
        raw = b""
        while chunk := conn.recv(4096):
            raw += chunk
        return raw
    finally:
        conn.close()


def test_a_stalled_body_does_not_hold_a_thread(tmp_path: Path, monkeypatch) -> None:
    """A client that declares a body and stops sending holds a server thread
    until the stall limit, never for ever. Breaks when the handler has no
    timeout. The limit is shortened so the test waits half a second."""
    monkeypatch.setattr(face, "_STALL_SECONDS", 0.5, raising=False)
    served = face.serve(tmp_path)
    served.add_page("POST", "/sink", lambda request: "")
    try:
        client = _Client(served)
        _held_open(client, f"POST /sink HTTP/1.1\r\nHost: {client.host}\r\n"
                           f"Cookie: {client.cookie}\r\nContent-Length: 100\r\n\r\n")
    finally:
        served.stop()


def test_a_refused_request_is_drained_only_so_far(tmp_path: Path, monkeypatch) -> None:
    """A request refused before the cookie check is anyone's, so its body is
    read no further than the page ceiling before the 403 goes. Breaks when a
    declared length past it keeps a thread reading. The ceiling is lowered
    so the test sends a kilobyte."""
    monkeypatch.setattr(face, "_MAX_BODY", 1024)
    served = face.serve(tmp_path)
    try:
        client = _Client(served)
        raw = _held_open(client, f"POST /sink HTTP/1.1\r\nHost: {client.host}\r\n"
                                 f"Content-Length: {10 * 1024 * 1024}\r\n\r\n", b"x" * 1024)
    finally:
        served.stop()
    assert raw.split(b"\r\n", 1)[0].split(b" ")[1] == b"403"


# ------------------------------------------------------------ PRESS-0224 ----


def test_an_upload_streams_past_the_page_ceiling(tmp_path: Path, monkeypatch) -> None:
    """PRESS-0224 INV-7. Breaks when the body is read whole, or the file is
    left behind. The ceiling is lowered so the test sends kilobytes, not 64 MiB."""
    monkeypatch.setattr(face, "_MAX_BODY", 1024)
    into = tmp_path / "own"
    into.mkdir()
    body = bytes(range(256)) * 20
    seen: list[tuple[bytes, bool]] = []

    def took(path: Path) -> str:
        seen.append((path.read_bytes(), path.parent == into))
        return "<p>taken</p>"

    served = face.serve(into)
    try:
        served.add_upload("/up", took, into)
        served.add_page("POST", "/page", lambda request: "<p>page</p>")
        client = _Client(served)
        status, _, page = client.raw("POST", "/up", body)
        assert status == 200 and b"taken" in page
        assert client.raw("POST", "/page", body)[0] == 413
    finally:
        served.stop()
    assert seen == [(body, True)]
    assert not list(into.glob(".upload-*"))


@pytest.mark.skipif(sys.platform == "win32", reason="SECURITY.md: Windows has no owner-only mode")
def test_an_upload_is_written_owner_only(tmp_path: Path) -> None:
    """SECURITY.md: on Linux every file Pressless writes is readable by its
    owner alone, and a handler may rename the upload into the Store. Breaks
    when the upload's file is created at the umask's mode."""
    into = tmp_path / "own"
    into.mkdir()
    modes: list[int] = []

    def took(path: Path) -> str:
        modes.append(stat.S_IMODE(path.stat().st_mode))
        return "<p>taken</p>"

    old = os.umask(0o022)
    served = face.serve(into)
    try:
        served.add_upload("/up", took, into)
        assert _Client(served).raw("POST", "/up", b"a file")[0] == 200
    finally:
        served.stop()
        os.umask(old)
    assert modes == [0o600]


NO_ROOM = "This computer's drive has too little free space to take that file."


@pytest.mark.parametrize("room", ["short", "unreadable"])
def test_an_upload_refused_for_room_says_why(tmp_path: Path, monkeypatch, room: str) -> None:
    """docs/design.md § Errors: a refusal he can reach is a sentence. The file
    box writes the answer over the page, so an empty 413 left a blank screen.
    Breaks when the room refusal answers without a page, or when free space
    that cannot be read lets the body through."""
    if room == "short":
        monkeypatch.setattr(face, "_room", lambda folder: 10)
    else:
        def unreadable(folder):
            raise OSError("no answer")
        monkeypatch.setattr(face.shutil, "disk_usage", unreadable)
    into = tmp_path / "own"
    into.mkdir()
    served = face.serve(into)
    try:
        served.add_upload("/up", lambda path: "<p>taken</p>", into)
        status, _, page = _Client(served).raw("POST", "/up", b"x" * 100)
    finally:
        served.stop()
    assert status == 413
    assert NO_ROOM in html.unescape(page.decode("utf-8")) and b"taken" not in page
    assert not list(into.glob(".upload-*"))


def test_an_upload_past_its_routes_largest_is_answered_unwritten(
        tmp_path: Path, monkeypatch) -> None:
    """PRESS-0384: a route's own ceiling is checked against the declared
    length before a byte is written, and its `too_large` page answers.
    Breaks when the body is copied to disk first, or a body at the ceiling
    is refused."""
    real_open = open
    written: list[str] = []

    def watched(path, *args, **kwargs):
        if ".upload-" in str(path):
            written.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(face, "open", watched, raising=False)
    into = tmp_path / "own"
    into.mkdir()
    taken: list[bytes] = []

    def took(path: Path) -> str:
        taken.append(path.read_bytes())
        return "<p>taken</p>"

    served = face.serve(into)
    try:
        served.add_upload("/up", took, into, largest=10,
                          too_large=lambda request: "<p>too large</p>")
        client = _Client(served)
        status, _, page = client.raw("POST", "/up", b"x" * 11)
        assert (status, b"too large" in page) == (200, True)
        assert written == [] and taken == []
        assert client.raw("POST", "/up", b"x" * 10)[0] == 200
    finally:
        served.stop()
    assert taken == [b"x" * 10]


def test_a_failed_upload_write_still_answers_with_its_page(tmp_path: Path,
                                                           monkeypatch) -> None:
    """PRESS-0304. Breaks when the rest of the body is left unread after the
    write fails: the socket closes with bytes unread, and the sender sees a
    dropped connection rather than the failure page. The body is far past
    the socket buffers, so an unread one cannot hide in them."""
    real_open = open

    def full_drive(path, *args, **kwargs):
        if ".upload-" in str(path):
            raise OSError(28, "No space left on device")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(face, "open", full_drive, raising=False)
    into = tmp_path / "own"
    into.mkdir()
    served = face.serve(into)
    try:
        served.add_upload("/up", lambda path: "<p>taken</p>", into)
        try:
            status, _, page = _Client(served).raw("POST", "/up", b"x" * (8 * 1024 * 1024))
        except OSError as exc:
            status, page = 0, repr(exc).encode()
    finally:
        served.stop()
    assert status == 500, page
    assert not list(into.glob(".upload-*"))


def test_an_upload_needs_the_session(tmp_path: Path) -> None:
    """PRESS-0224 INV-8. Breaks when the upload route skips a check a page
    gets, or writes a byte before it."""
    into = tmp_path / "own"
    into.mkdir()
    sent = tmp_path / "sent.zip"
    sent.write_bytes(b"a file")
    served = face.serve(into)
    try:
        served.add_upload("/up", lambda path: "<p>taken</p>", into)
        served.add_page("GET", "/down", lambda request: face.Download(sent, "Site.zip"))
        client = _Client(served)
        assert client.raw("POST", "/up", b"x" * 100, cookie=False)[0] == 403
        assert client.raw("POST", "/up", b"x" * 100,
                          origin="http://pressless.example")[0] == 403
        assert client.raw("GET", "/down", cookie=False)[0] == 403
    finally:
        served.stop()
    assert not list(into.glob(".upload-*"))
    assert sent.read_bytes() == b"a file"


def test_a_download_whose_size_cannot_be_read_is_still_removed(tmp_path: Path,
                                                              monkeypatch) -> None:
    """PRESS-0224 § 4.5: a download is deleted, sent or not. Windows refuses
    to delete a file still open, which this test's unlink does too. Breaks
    when the handle is left open after its size cannot be read, so the
    delete fails and the failure page never arrives."""
    real_open, real_fstat, real_unlink = open, os.fstat, Path.unlink
    handles: list = []

    def tracked(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        if str(path).endswith("sent.zip"):
            handles.append(handle)
        return handle

    def no_size(descriptor):
        if any(not h.closed and h.fileno() == descriptor for h in handles):
            raise OSError("the size cannot be read")
        return real_fstat(descriptor)

    def as_windows(path, *args, **kwargs):
        if any(not h.closed for h in handles) and path.name == "sent.zip":
            raise PermissionError("the file is open")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(face, "open", tracked, raising=False)
    monkeypatch.setattr(face.os, "fstat", no_size)
    monkeypatch.setattr(Path, "unlink", as_windows)
    sent = tmp_path / "sent.zip"
    sent.write_bytes(b"a file")
    served = face.serve(tmp_path / "own")
    try:
        served.add_page("GET", "/down", lambda request: face.Download(sent, "Site.zip"))
        status = _Client(served).raw("GET", "/down")[0]
    finally:
        served.stop()
    assert status == 500
    assert not sent.exists()


def test_a_download_is_sent_as_an_attachment_and_removed(tmp_path: Path) -> None:
    """PRESS-0224 § 4.5. Breaks when the file is answered inline, its name is
    not quoted for the browser, or it is left behind."""
    sent = tmp_path / ".saving-1.zip"
    sent.write_bytes(b"PK zip bytes")
    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/down", lambda request: face.Download(sent, "Mé Site 2026.zip"))
        status, headers, data = _Client(served).raw("GET", "/down")
    finally:
        served.stop()
    assert status == 200 and data == b"PK zip bytes"
    disposition = headers["Content-Disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''M%C3%A9%20Site%202026.zip" in disposition
    assert "frame-ancestors 'self'" in headers["Content-Security-Policy"]
    assert not sent.exists()


# ------------------------------------------------------------- PRESS-0319 ---

# The file box's script runs in a browser; Node runs it against a stand-in
# button, chooser and message, with a fetch that never reaches Pressless.
_NODE = shutil.which("node")
_FILE_BOX_HARNESS = """const on = {};
const button = {dataset: {file: "box"}, textContent: "Send", disabled: false,
                addEventListener: (kind, run) => { on["button " + kind] = run; }};
const chooser = {dataset: {to: "/to"}, files: [{}], value: "", click() {},
                 addEventListener: (kind, run) => { on["chooser " + kind] = run; }};
const message = {textContent: ""};
const document = {
  querySelectorAll: () => [button],
  getElementById: (id) => ({box: chooser, "box-message": message})[id] || null,
  open() { throw new Error("the page was replaced"); }, write() {}, close() {},
};
const fetch = () => Promise.reject(new TypeError("Failed to fetch"));
const say = (key) => "<" + key + ">";
%s
(async () => {
  try { await on["chooser change"](); } catch (error) {}
  process.stdout.write(JSON.stringify(
    {disabled: button.disabled, label: button.textContent, message: message.textContent}));
})();
"""


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_a_file_box_that_cannot_reach_pressless_says_so(tmp_path):
    """PRESS-0319. Breaks when a dropped connection leaves the button
    disabled, or shows no message."""
    box = face.file_box("box", ".zip", "/to", "Send")
    script = re.search(r"<script>(.*)</script>", box, re.S).group(1)
    harness = tmp_path / "box.js"
    harness.write_text(_FILE_BOX_HARNESS % script, encoding="utf-8")
    run = subprocess.run([_NODE, str(harness)], capture_output=True,  # noqa: S603
                         check=True, timeout=30)
    assert json.loads(run.stdout) == {
        "disabled": False, "label": "Send", "message": "<script.file_box.unreachable>"}


# ------------------------------------------------------------- PRESS-0335 ---

# A folder box packs the chosen folder into a ZIP in the browser. Node runs the
# script with real File objects, each carrying the path a folder chooser gives.
_FOLDER_BOX_HARNESS = """const on = {};
const button = {dataset: {file: "box"}, textContent: "Send", disabled: false,
                addEventListener: (kind, run) => { on["button " + kind] = run; }};
const chooser = {dataset: {to: "/to", folder: "1"}, files: FILES, value: "", click() {},
                 addEventListener: (kind, run) => { on["chooser " + kind] = run; }};
const message = {textContent: ""};
let sent = null;
const document = {
  querySelectorAll: () => [button],
  getElementById: (id) => ({box: chooser, "box-message": message})[id] || null,
  open() {}, write() {}, close() {},
};
const fetch = async (to, how) => {
  sent = Buffer.from(await how.body.arrayBuffer()).toString("base64");
  return {text: async () => "<p>taken</p>"};
};
const say = (key) => "<" + key + ">";
SCRIPT
(async () => {
  await on["chooser change"]();
  process.stdout.write(JSON.stringify(
    {sent, disabled: button.disabled, label: button.textContent, message: message.textContent}));
})();
"""

# Each file as the browser hands it over: a File, plus the path inside the
# chosen folder, which the File constructor cannot set.
_FOLDER_FILE = ("Object.defineProperty(new File([Buffer.from({data!r}, 'base64')], {name!r}),"
                " 'webkitRelativePath', {{value: {path!r}}})")


def _run_folder_box(tmp_path, files: str) -> dict:
    box = face.file_box("box", "", "/to", "Send", folder=True)
    script = re.search(r"<script>(.*)</script>", box, re.S).group(1)
    harness = tmp_path / "folder.js"
    harness.write_text(_FOLDER_BOX_HARNESS.replace("FILES", files).replace("SCRIPT", script),
                       encoding="utf-8")
    run = subprocess.run([_NODE, str(harness)], capture_output=True,  # noqa: S603
                         check=True, timeout=30)
    return json.loads(run.stdout)


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_a_folder_box_sends_a_zip_the_importer_unpacks(tmp_path):
    """PRESS-0335. Breaks when the browser's ZIP is malformed, carries a wrong
    checksum, loses a file's bytes, or mangles a name outside plain ASCII."""
    import base64
    import zipfile

    import pressless_import
    chosen = {"site/index.html": b"<h1>Home</h1>",
              "site/café/menu.html": "<p>Café</p>".encode(),
              "site/photo.jpg": bytes(range(256)) * 40}
    files = "[" + ",".join(
        _FOLDER_FILE.format(data=base64.b64encode(data).decode(),
                            name=path.rsplit("/", 1)[1], path=path)
        for path, data in chosen.items()) + "]"
    said = _run_folder_box(tmp_path, files)
    assert (said["disabled"], said["message"]) == (True, "")
    held = tmp_path / "sent.zip"
    held.write_bytes(base64.b64decode(said["sent"]))
    assert zipfile.is_zipfile(held)
    with zipfile.ZipFile(held) as sent:
        assert sent.testzip() is None
    into = tmp_path / "folder"
    assert pressless_import.unpack_folder(held, into, lambda: 10**9) == ()
    assert {path.relative_to(into).as_posix(): path.read_bytes()
            for path in into.rglob("*") if path.is_file()} == {
        path.removeprefix("site/"): data for path, data in chosen.items()}


@pytest.mark.skipif(_NODE is None, reason="needs node to run the page's script")
def test_a_folder_too_large_for_a_plain_zip_is_not_sent(tmp_path):
    """PRESS-0335. A plain ZIP cannot hold past 4 GiB. Breaks when such a
    folder is sent anyway, or the button stays disabled with no message."""
    files = ('[{name: "film.mp4", webkitRelativePath: "site/film.mp4", size: 5e9,'
             ' stream() { throw new Error("read"); },'
             ' arrayBuffer: async () => new ArrayBuffer(0)}]')
    assert _run_folder_box(tmp_path, files) == {
        "sent": None, "disabled": False, "label": "Send",
        "message": "<script.file_box.too_large>"}


def test_a_posted_form_is_read_one_way() -> None:
    """PRESS-0383: every page reads its form through Request.form. Breaks
    when a blank field is kept without being asked for, or a body that is
    not UTF-8 is read with replacement where a page asked for strict."""
    request = face.Request("POST", "/x", {}, b"a=1&b=&c=caf%C3%A9&d=%FF")
    assert request.form() == {"a": ["1"], "c": ["café"], "d": ["�"]}
    assert request.form(blanks=True)["b"] == [""]
    with pytest.raises(UnicodeDecodeError):
        face.Request("POST", "/x", {}, b"a=\xff").form(strict=True)


def _set_up(folder: Path) -> None:
    """A site past setup, so its bar is the ordinary one."""
    (folder / "site").mkdir()
    _saved(folder)


def _bar(served: face.Face) -> str:
    served.add_page("GET", "/words", lambda request: "<p>Words</p>")
    _, _, body = _Client(served).request("GET", "/words")
    return body.split('<header class="bar">', 1)[1].split("</header>", 1)[0]


def test_the_top_bar_is_locked_until_setup_is_done(tmp_path) -> None:
    """User 2026-11-21: a first-time user clicked the top bar while setup was
    working and could not find the way back. Breaks when a bar link leads
    away from an unfinished setup, or when Help and More's pages open in the
    setup's own tab rather than a new one."""
    served = face.serve(tmp_path)
    try:
        bar = _bar(served)
    finally:
        served.stop()
    for address in ("/sites", "/", "/pages", "/journal", "/look", "/files",
                    "/visitors", "/setup"):
        assert f'href="{address}"' not in bar, address
    for address in ("/manual", "/report", "/about"):
        assert f'href="{address}" target="_blank"' in bar, address


def test_the_top_bar_unlocks_once_setup_is_done(tmp_path) -> None:
    """The lock lifts with the settings file: a set-up site's bar leads
    everywhere in the same tab."""
    _set_up(tmp_path)
    served = face.serve(tmp_path)
    try:
        bar = _bar(served)
    finally:
        served.stop()
    assert 'href="/pages"' in bar and 'href="/manual">' in bar
    assert "target=" not in bar


def test_sites_stays_open_while_another_site_is_set_up(tmp_path) -> None:
    """A second site's setup must not trap him away from his first site."""
    first = sites.open_site(tmp_path)
    _set_up(first)
    second = sites.new_site(tmp_path)
    served = face.serve(tmp_path, site=second)
    try:
        bar = _bar(served)
    finally:
        served.stop()
    assert 'href="/sites"' in bar and 'href="/pages"' not in bar
