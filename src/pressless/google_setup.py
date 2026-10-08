"""Setup's second step (PRESS-0122): signing in with Google for the dashboard.

The contract is docs/specs/PRESS-0122-google-signin.md § 4.2 to § 4.5. The
pages live in the Face, beside setup.py, because only the Face reaches
Credentials (`docs/design.md` rule 10); talking to Google is
`google_signin`'s, which belongs to Insights.

Three values are held in memory and never written to disk: the pending
attempt, the pending list (with the tokens its sign-in produced), and the
held access token. The store and Settings change only when he chooses a
property, so a sign-in left half-way leaves the dashboard as it was.
"""

from __future__ import annotations

import dataclasses
import hmac
import html
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from pressless import credentials, google_signin, insights, settings, starter
from pressless.face import Face, Reply, Request, message_box, render_notices
from pressless.google_signin import AccessToken, Attempt, Property
from pressless.store import StoreError
from pressless.words import say

GOOGLE_ACCOUNT = "google"                 # the account the refresh token is filed under
RETURN_PATH = "/setup/google/back"        # the redirect_uri's path

PAGE = "/setup/google"
_REFRESH_MARGIN = 60.0   # seconds before expiry a held token stops being handed out
_PERMISSIONS = "https://myaccount.google.com/permissions"
_CREDENTIAL_FAILURES = (credentials.NoStore, credentials.NotStored, credentials.CredentialError)


@dataclass(frozen=True)
class _Pending:
    properties: tuple[Property, ...]
    refresh_token: str
    access: AccessToken


class _State:
    """Everything this module holds, for one launch (§ 4.2)."""

    def __init__(self, face: Face, folder: Path,
                 client: insights.Transport | None) -> None:
        self.face = face
        self.folder = Path(folder)
        self.client = client
        self.lock = threading.Lock()
        self.attempt: Attempt | None = None
        self.pending: _Pending | None = None
        self.held: AccessToken | None = None

    def transport(self) -> insights.Transport:
        return self.client if self.client is not None else insights._own_client()


_state: _State | None = None


def register(face: Face, folder: Path, *,
             client: insights.Transport | None = None) -> None:
    """Add the Google step's pages to `face` (§ 4.2)."""
    global _state
    state = _State(face, folder, client)
    _state = state
    face.add_page("GET", PAGE, lambda request: _show(state))
    face.add_page("POST", PAGE + "/start", lambda request: _start(state))
    face.add_page("POST", PAGE + "/sites", lambda request: _sites(state))
    face.add_page("POST", PAGE + "/choose", lambda request: _choose(state, request))
    face.add_page("POST", PAGE + "/off", lambda request: _off(state))
    face.add_return_page(RETURN_PATH, lambda request: _back(state, request))


def token(folder: Path) -> str:
    """An access token for `insights.read` (§ 4.2), for PRESS-0020's dashboard.

    Uses the client `register` was given, and its clock. The held token is
    reused until it is within a minute of expiring (INV-14).
    """
    state = _state
    if state is None:
        raise RuntimeError("google_setup.register has not run")
    with state.face.capture():
        saved = settings.load(folder)
    account = saved.credentials.google_account
    if account is None:
        raise insights.NotConfigured("the dashboard was never set up")
    transport = state.transport()
    with state.lock:
        held = state.held
    if held is not None and held.expires_at - transport.now() > _REFRESH_MARGIN:
        return held.value
    refresh = credentials.read(saved.credentials.store, Path(folder), account)
    access = google_signin.access_token(refresh, transport)
    with state.lock:
        state.held = access
    return access.value


# ---------------------------------------------------------------- pages ----


def _load(state: _State) -> tuple[settings.Settings | None, str]:
    """Settings, or None and the page to show instead."""
    with state.face.capture() as notices:
        try:
            saved = settings.load(state.folder)
        except (settings.NotSetUp, settings.SettingsError):
            saved = None
    shown = render_notices(notices)
    if saved is None:
        return None, shown + f"<h1>{say('google_setup.title')}</h1><p>{say('setup.first')}</p>"
    return saved, shown


def _show(state: _State, hint: str = "") -> str:
    saved, shown = _load(state)
    if saved is None:
        return shown
    e = html.escape
    head = f"<h1>{say('google_setup.title')}</h1>"
    back = f'<p><a href="/setup">{say("setup.back")}</a></p>'
    if not google_signin.available():
        return shown + head + f"<p>{say('google_setup.unavailable')}</p>" + back
    with state.lock:
        pending = state.pending
    if pending is not None:
        choices = "".join(
            f'<p><label><input type="radio" name="property" value="{e(p.id, quote=True)}"> '
            f"{e(p.name)} ({e(p.account)})</label></p>"
            for p in pending.properties
        )
        shown_hint = message_box("property-hint", e(hint), focus="property") if hint else ""
        return (shown + head + f"<p>{say('google_setup.which')}</p>"
                + f'<form method="post" action="{PAGE}/choose">{choices}{shown_hint}'
                f'<p><button type="submit">{say("google_setup.use")}</button></p></form>'
                + back)
    if saved.credentials.google_account is not None:
        return (shown + head
                + "<p>" + say("google_setup.reading",
                              property=e(saved.analytics_property_id or "")) + "</p>"
                + _button("/sites", say("google_setup.choose_other"))
                + _button("/start", say("google_setup.sign_in_again"))
                + _button("/off", say("google_setup.turn_off")) + back)
    return (shown + head
            + f"<p>{say('google_setup.offer')}</p>"
            + _pending()
            + _button("/start", say("google_setup.sign_in")) + back)


def _pending() -> str:
    """Google's unverified-app warning, explained while its review runs (PRESS-0200)."""
    if google_signin.APPROVED:
        return ""
    return f"<p>{say('google_setup.unverified')}</p>"


def _button(action: str, label: str) -> str:
    return (f'<form method="post" action="{PAGE}{action}">'
            f'<p><button type="submit">{html.escape(label)}</button></p></form>')


def _start(state: _State) -> str | Reply:
    saved, shown = _load(state)
    if saved is None:
        return shown
    if not google_signin.available():
        return _show(state)
    attempt, address = google_signin.begin(state.face.origin + RETURN_PATH, state.transport())
    with state.lock:
        state.attempt = attempt   # replaces any pending one
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=address)


def _back(state: _State, request: Request) -> str | Reply:
    """Google's return (§ 4.3). Reached without the cookie, so the attempt is
    the authentication: no match is the same 403 a missing cookie gets."""
    with state.lock:
        attempt = state.attempt
        if attempt is None or not hmac.compare_digest(request.query.get("state", ""),
                                                      attempt.state):
            return Reply(b"Forbidden", "text/plain", status=403)
        state.attempt = None   # spent, whatever follows
    transport = state.transport()
    try:
        refresh = google_signin.finish(attempt, request.query, transport)
        access = google_signin.access_token(refresh, transport)
        found = google_signin.properties(access.value, transport)
    except insights.InsightsError as exc:
        return (state.face.fail(exc, publishing=False,
                                secret=say("failure.secret.google_sign_in"))
                + _continue(moving=False))
    if not found:
        return _none_found() + _continue(moving=False)
    with state.lock:
        state.pending = _Pending(found, refresh, access)
    return f"<h1>{say('google_setup.signed_in')}</h1>" + _continue(moving=True)


def _sites(state: _State) -> str:
    """The list again from the stored sign-in, so changing site needs no
    new one (PRESS-0206). Nothing is written until he chooses."""
    saved, shown = _load(state)
    if saved is None:
        return shown
    account = saved.credentials.google_account
    if not google_signin.available() or account is None:
        return _show(state)
    transport = state.transport()
    try:
        refresh = credentials.read(saved.credentials.store, state.folder, account)
        access = google_signin.access_token(refresh, transport)
        found = google_signin.properties(access.value, transport)
    except (insights.InsightsError, *_CREDENTIAL_FAILURES) as exc:
        return (shown + state.face.fail(exc, publishing=False,
                                        secret=say("failure.secret.google_sign_in"))
                + _continue(moving=False))
    if not found:
        return shown + _none_found() + _continue(moving=False)
    with state.lock:
        state.pending = _Pending(found, refresh, access)
    return _show(state)


def _continue(*, moving: bool) -> str:
    # A navigation this page starts is same-site, so the browser sends the
    # cookie the redirect from Google could not carry (§ 4.3 step 4). Only a
    # success moves on by itself: a failure stays until he has read it (INV-17).
    refresh = f'<meta http-equiv="refresh" content="0; url={PAGE}">' if moving else ""
    return refresh + f'<p><a href="{PAGE}">{say("google_setup.continue")}</a></p>'


def _none_found() -> str:
    return (f"<h1>{say('google_setup.none_found.title')}</h1>"
            f"<p>{say('google_setup.none_found')}</p>")


def _choose(state: _State, request: Request) -> str:
    saved, shown = _load(state)
    if saved is None:
        return shown
    fields = urllib.parse.parse_qs(request.body.decode("utf-8", errors="replace"))
    chosen = (fields.get("property") or [""])[0]
    with state.lock:
        pending = state.pending
    if pending is None:
        return _show(state)
    if chosen not in {p.id for p in pending.properties}:
        return _show(state, hint=say("google_setup.choose_hint"))
    try:
        credentials.write(saved.credentials.store, state.folder, GOOGLE_ACCOUNT,
                          pending.refresh_token)
    except _CREDENTIAL_FAILURES as exc:
        return shown + state.face.fail(exc, publishing=False,
                                       secret=say("failure.secret.google_sign_in"))
    # PRESS-0199 § 4.3: the property's web streams, read with the token in
    # hand. A failure here keeps today's save and says counting is still off.
    found: tuple[str, ...] = ()
    lookup_failure = ""
    try:
        found = google_signin.measurement_ids(pending.access.value, chosen,
                                              saved.site_address, state.client)
    except insights.InsightsError as exc:
        lookup_failure = state.face.fail(exc, publishing=False)
    measurement_id = saved.measurement_id
    if measurement_id is None and len(found) == 1:
        measurement_id = found[0]
    candidate = dataclasses.replace(
        saved,
        credentials=dataclasses.replace(saved.credentials, google_account=GOOGLE_ACCOUNT),
        analytics_property_id=chosen,
        measurement_id=measurement_id,
    )
    with state.face.capture() as notices:
        settings.check(candidate)
        settings.save(state.folder, candidate)
    with state.lock:
        state.held = pending.access
        state.pending = None
    privacy = ""
    if candidate.measurement_id is not None:
        with state.face.capture() as privacy_notices:
            try:
                starter.add_privacy(state.folder, starter.privacy_name(state.folder))
            except StoreError as exc:
                privacy = (f"<p>{say('google_setup.privacy_failed')}</p>"
                           + state.face.fail(exc, publishing=False))
        privacy = render_notices(privacy_notices) + privacy
    return (shown + render_notices(notices) + lookup_failure
            + f"<h1>{say('google_setup.ready')}</h1>"
            + _counting(saved.measurement_id, found, lookup_failure != "") + privacy
            + f'<p><a href="/">{say("script.undo.back")}</a></p>')


def _counting(kept: str | None, found: tuple[str, ...], failed: bool) -> str:
    """PRESS-0199 § 4.3: what became of the counting code."""
    e = html.escape
    if failed:
        return f"<p>{say('google_setup.counting.failed')}</p>"
    if kept is not None:
        other = [i for i in found if i != kept]
        extra = (" " + say("google_setup.counting.also", ids=e(", ".join(other)))
                 if other else "")
        return f"<p>{say('google_setup.counting.kept', id=e(kept))}{extra}</p>"
    if len(found) == 1:
        return f"<p>{say('google_setup.counting.found', id=e(found[0]))}</p>"
    if found:
        return f"<p>{say('google_setup.counting.several', ids=e(', '.join(found)))}</p>"
    return f"<p>{say('google_setup.counting.none')}</p>"


def _off(state: _State) -> str:
    saved, shown = _load(state)
    if saved is None:
        return shown
    told = True
    account = saved.credentials.google_account
    if account is not None:
        try:
            refresh = credentials.read(saved.credentials.store, state.folder, account)
            google_signin.revoke(refresh, state.transport())
        except (insights.InsightsError, *_CREDENTIAL_FAILURES):
            told = False
    candidate = dataclasses.replace(
        saved,
        credentials=dataclasses.replace(saved.credentials, google_account=None),
        analytics_property_id=None,
    )
    with state.face.capture() as notices:
        settings.save(state.folder, candidate)
    with state.lock:
        state.held = None
        state.pending = None
    page = shown + render_notices(notices) + f"<h1>{say('google_setup.off')}</h1>"
    if not told:
        link = f'<a href="{_PERMISSIONS}">{_PERMISSIONS}</a>'
        page += f"<p>{say('google_setup.not_told', link=link)}</p>"
    return page + f'<p><a href="/setup">{say("setup.back")}</a></p>'
