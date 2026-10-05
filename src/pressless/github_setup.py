"""The GitHub pass (PRESS-0231 § 4.2), and signing in to GitHub again (§ 4.4).

The contract is docs/specs/PRESS-0231-github-sign-in.md. It lives in the Face,
beside setup.py, because only the Face reaches Credentials (`docs/design.md`
rule 10); talking to GitHub is `github_signin`'s, which belongs to the
Publisher.

Every GitHub secret is read through `token`. A hand-made key is handed over
as it is. A sign-in's refresh token is never handed over: it buys a pass that
lasts eight hours, held in memory for one launch and never written to disk.
GitHub's refresh token works once, so renewing it and storing the new one run
under one lock: two renewals at once would leave one of them signed out.
"""

from __future__ import annotations

import html
import threading
import time
from collections.abc import Callable
from pathlib import Path

from pressless import credentials, github_signin, publisher, settings
from pressless.face import Face, Reply, Request, render_notices
from pressless.github_signin import DeviceCode, Tokens

PAGE = "/setup/github"
SIGN_IN = "your GitHub sign-in"          # the {secret} noun (PRESS-0011 § 4.2)
_REFRESH_PREFIX = "ghr_"                 # every GitHub refresh token; no key starts so
_REFRESH_MARGIN = 60.0   # seconds before expiry a held pass stops being handed out
_CREDENTIAL_FAILURES = (credentials.NoStore, credentials.NotStored, credentials.CredentialError)

_TYPE_IT = "Type this code on GitHub's page, click Authorize, then press Next here."
_NOT_HEARD = ("GitHub has not heard from you yet. Type the code on GitHub's page, "
              "click Authorize, then press Next here.")
_CANCELLED = "The sign-in was cancelled on GitHub. Press Next to start again."


class _State:
    """Everything this module holds, for one launch (§ 4.2)."""

    def __init__(self, face: Face, folder: Path, transport: publisher.Transport | None,
                 clock: Callable[[], float]) -> None:
        self.face = face
        self.folder = Path(folder)
        self.transport = transport
        self.clock = clock
        self.lock = threading.Lock()
        self.held: tuple[str, float] | None = None     # the pass, and when it ends
        self.again = SignIn()                          # /setup/github's own sign-in


_state: _State | None = None


def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None,
             clock: Callable[[], float] = time.time) -> None:
    """Add `/setup/github` to `face`, and hold the pass for this launch."""
    global _state
    state = _State(face, folder, transport, clock)
    _state = state
    face.add_page("GET", PAGE, lambda request: _page(state, request))
    face.add_page("POST", PAGE, lambda request: _page(state, request))


def signed_in(secret: str) -> bool:
    """Whether a stored GitHub secret is a sign-in rather than a hand-made key."""
    return secret.startswith(_REFRESH_PREFIX)


def token(folder: Path, store: str, account: str) -> str:
    """What to send GitHub as the key, from the secret stored under `account`
    (§ 4.2). Takes the arguments `credentials.read` takes."""
    state = _state
    with state.lock if state is not None else threading.Lock():
        secret = credentials.read(store, Path(folder), account)
        if not signed_in(secret):
            return secret
        if state is None:
            raise RuntimeError("github_setup.register has not run")
        asked = state.clock()
        if state.held is not None and state.held[1] - asked > _REFRESH_MARGIN:
            return state.held[0]
        renewed = github_signin.refresh(secret, state.transport)
        # Before the pass is used: the old refresh token has stopped working.
        credentials.write(store, Path(folder), account, renewed.refresh)
        state.held = (renewed.access, asked + renewed.expires_in)
        return renewed.access


def hold(tokens: Tokens) -> None:
    """A sign-in's first pass, so the next `token` needs no renewal."""
    state = _need()
    with state.lock:
        state.held = (tokens.access, state.clock() + tokens.expires_in)


def _need() -> _State:
    if _state is None:
        raise RuntimeError("github_setup.register has not run")
    return _state


class SignIn:
    """One sign-in under way (§ 4.3): its device code, held in memory and
    never in the progress file. Each `press` is one press of Next."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._code: DeviceCode | None = None
        self._ends = 0.0

    def press(self) -> str | Tokens:
        """The tokens once GitHub has issued them; until then, what to tell
        him. Any other failure is raised for the caller to show."""
        state = _need()
        with self._lock:
            if self._code is None or state.clock() >= self._ends:
                return self._begin(state)
            try:
                tokens = github_signin.poll(self._code, state.transport)
            except github_signin.Pending:
                return _NOT_HEARD
            except github_signin.Expired:
                return self._begin(state)
            except github_signin.Declined:
                self._code = None
                return _CANCELLED
            self._code = None
            return tokens

    def shown(self) -> str:
        """The code and where to type it, while one is held."""
        with self._lock:
            code = self._code
        if code is None:
            return ""
        e = html.escape
        return (f'<p class="sign-in-code">Your code: <strong>{e(code.user_code)}</strong></p>'
                f'<p>Type it at <a href="{e(code.address, quote=True)}" target="_blank" '
                f'rel="noopener">{e(code.address)}</a></p>')

    def _begin(self, state: _State) -> str:
        self._code = None
        asked = state.clock()
        code = github_signin.begin(state.transport)
        self._code, self._ends = code, asked + code.expires_in
        return _TYPE_IT


HOW = ("<p>Pressless signs in to GitHub with a short code rather than your "
       "password.</p><ol>"
       "<li>Press <b>Next</b>. Pressless shows a code and a link to GitHub.</li>"
       "<li>Open the link, sign in to GitHub if it asks, and type the code.</li>"
       "<li>Click <b>Authorize</b> on GitHub's page.</li>"
       "<li>Come back here and press <b>Next</b> again.</li></ol>")


def _page(state: _State, request: Request) -> str | Reply:
    """§ 4.4: the sign-in sequence on its own, with the saved store."""
    with state.face.capture() as notices:
        try:
            saved = settings.load(state.folder)
        except (settings.NotSetUp, settings.SettingsError):
            saved = None
    shown = render_notices(notices) + "<h1>Sign in to GitHub</h1>"
    back = '<p><a href="/setup">Back to Settings</a></p>'
    if saved is None:
        return shown + '<p>Set up Pressless first, <a href="/setup">on the setup page</a>.</p>'
    if not github_signin.available():
        return (shown + "<p>This copy of Pressless cannot sign in to GitHub. Paste a "
                "publishing key in Settings instead.</p>" + back)
    above = ""
    if request.method == "POST":
        try:
            pressed = state.again.press()
            if isinstance(pressed, Tokens):
                credentials.write(saved.credentials.store, state.folder,
                                  saved.credentials.github_account, pressed.refresh)
                hold(pressed)
                return Reply(b"", "text/plain; charset=utf-8", status=303, location="/setup")
            above = f'<p class="hint">{html.escape(pressed)}</p>'
        except publisher.PublishError as exc:
            above = state.face.fail(exc, publishing=False)
        except _CREDENTIAL_FAILURES as exc:
            above = state.face.fail(exc, publishing=False, secret=SIGN_IN)
    return (shown + above + HOW + state.again.shown()
            + f'<form method="post" action="{PAGE}">'
              '<p><button type="submit">Next</button></p></form>' + back)
