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
import re
import socket
import sys
import urllib.parse
from pathlib import Path

import pytest
from _face_session import Browser, follow_link, session_cookie

import pressless
from pressless import credentials, face, insights, publisher, store, themes

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
        # The link is spent, and its secret is never a session.
        assert follow_link(served.url)[0] == 403
        assert client.request("GET", f"/?t={client.secret}")[0] == 403
        secret_as_cookie = _Client(served, follow=False)
        secret_as_cookie.cookie = f"{name}={client.secret}"
        assert secret_as_cookie.request("GET", "/")[0] == 403
        assert client.request("GET", "/", host="pressless.example")[0] == 403
        status = client.request("POST", "/folder/open", origin="http://127.0.0.1:1")[0]
        assert status == 403
        assert opened == []
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
    "font-src 'self'; script-src 'self'; connect-src 'self'; frame-src 'none'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)
FRAMES_POLICY_WORDS = "frame-src 'self'; frame-ancestors 'self'"
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


def test_files_carry_the_policy(tmp_path: Path) -> None:
    """PRESS-0012 INV-8."""
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    types = {"page.HTML": "text/html; charset=utf-8", "site.css": "text/css; charset=utf-8",
             "site.js": "text/javascript; charset=utf-8",
             "notes.txt": "application/octet-stream"}
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
