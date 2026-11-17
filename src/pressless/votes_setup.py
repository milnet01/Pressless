"""The Like and Dislike buttons' setup screen (PRESS-0211 § 4.6).

Step-by-step help to make a site's own free Firebase project, the box its
firebaseConfig text is pasted into, and Check, which asks Google whether the
project is ready. The steps are given rather than automated: automating them
needs a Google permission beyond the one Pressless holds (§ 3 decision 14).
"""
from __future__ import annotations

import dataclasses
import html
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pressless import editor, https, settings, setup, votes
from pressless.face import Face, Request, loaded_settings, message_box, render_notices
from pressless.words import say

PAGE = votes.ADDRESS
TIMEOUT_SECONDS = 30.0
_STEPS = ("votes_setup.step.1", "votes_setup.step.2", "votes_setup.step.3",
          "votes_setup.step.4", "votes_setup.step.5")
# Check's own vote, on an entry no date on a site can name. It must still pass
# votes.RULES' two `entry` clauses, or Check reads its own refusal as missing rules.
_CHECK_ENTRY = "0000-00-00-pressless-check"
_SIGN_UP = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"

_READY = "votes_setup.check.ready"
_ANONYMOUS = "votes_setup.check.anonymous"
_NO_RULES = "votes_setup.check.rules"
_WRONG_RULES = "votes_setup.check.rules_wrong"
_NO_DATABASE = "votes_setup.check.database"
_KEY_REFUSED = "votes_setup.check.key"
_UNREACHABLE = "votes_setup.check.unreachable"

# The Copy button. It says so in a place that moves nothing.
_SCRIPT = """
document.querySelector("button[data-copy-rules]").addEventListener("click", async (event) => {
  await navigator.clipboard.writeText(document.getElementById("votes-rules").textContent);
  document.getElementById("rules-copied").textContent = event.target.dataset.copyRules;
});
"""


class Transport(Protocol):
    """`https.Client.request`: every HTTP status returned, OSError where no answer came."""

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]: ...


def register(face: Face, folder: Path, *, client: Transport | None = None) -> None:
    """Add the screen's pages to `face`."""
    folder = Path(folder)
    face.add_page("GET", PAGE, lambda request: _show(face, folder))
    face.add_page("POST", PAGE, lambda request: _save(face, folder, client, request))
    face.add_page("POST", PAGE + "/check", lambda request: _checked(face, folder, client))
    face.add_page("POST", PAGE + "/off", lambda request: _off(face, folder))


def _not_set_up(shown: str) -> str:
    return shown + f"<h1>{say('votes_setup.title')}</h1><p>{say('setup.first')}</p>"


def _back() -> str:
    return f'<p><a href="/setup">{say("setup.back")}</a></p>'


def _button(action: str, label: str) -> str:
    return (f'<form method="post" action="{action}">'
            f'<p><button type="submit">{html.escape(label)}</button></p></form>')


def _show(face: Face, folder: Path, *, hint: str = "", typed: dict[str, str] | None = None) -> str:
    saved, shown = loaded_settings(face, folder)
    if saved is None:
        return _not_set_up(shown)
    e = html.escape
    typed = typed or {}
    steps = "".join(f"<li>{say(key)}</li>" for key in _STEPS)
    state = (say("votes_setup.on", project=e(saved.votes.project_id))
             if saved.votes is not None else say("votes_setup.not_on"))
    controls = ""
    if saved.votes is not None:
        controls = (_button(PAGE + "/check", say("votes_setup.check"))
                    + _button(PAGE + "/off", say("votes_setup.off")))
    copied = e(say("votes_setup.copied"), quote=True)
    invalid = ' aria-invalid="true"' if hint else ""
    return (shown + f"<h1>{say('votes_setup.title')}</h1>"
            + f"<p>{state}</p>" + controls
            + f"<p>{say('votes_setup.about')}</p><ol>{steps}</ol>"
            + f'<pre id="votes-rules">{e(votes.RULES)}</pre>'
            + f'<p><button type="button" data-copy-rules="{copied}">{say("votes_setup.copy")}'
              '</button> <span id="rules-copied" role="status"></span></p>'
            + f"<p>{say('votes_setup.warning')}</p>"
            + f'<form method="post" action="{PAGE}">'
            + f'<p><label for="config">{say("votes_setup.box")}</label><br>'
              f'<textarea id="config" name="config" rows="9" cols="60"{invalid}>'
              f'{e(typed.get("config", ""))}</textarea></p>'
            + "<details>"
            + f"<summary>{say('votes_setup.app_check.title')}</summary>"
            + f"<p>{say('votes_setup.app_check')}</p>"
            + f"<p>{say('votes_setup.app_check.steps')}</p>"
            + f'<p><label for="recaptcha_key">{say("votes_setup.app_check.box")}</label><br>'
              f'<input id="recaptcha_key" name="recaptcha_key" size="50" '
              f'value="{e(typed.get("recaptcha_key", ""), quote=True)}"></p>'
            + "</details>"
            + f'<p><button type="submit">{say("votes_setup.save")}</button></p></form>'
            + (message_box("config-hint", e(hint), focus="config") if hint else "")
            + _back() + f"<script>{_SCRIPT}</script>")


def _save(face: Face, folder: Path, client: Transport | None, request: Request) -> str:
    saved, shown = loaded_settings(face, folder)
    if saved is None:
        return _not_set_up(shown)
    form = editor.form_fields(request)
    try:
        found = votes.parse_config(form.get("config", ""))
    except settings.SettingsError:
        return _show(face, folder, hint=say("votes_setup.hint"), typed=form)
    value = settings.Votes(**found, recaptcha_key=form.get("recaptcha_key", "").strip() or None)
    try:
        settings.check_votes(value)
    except settings.SettingsError:
        return _show(face, folder, hint=say("votes_setup.hint.recaptcha"), typed=form)
    candidate = dataclasses.replace(saved, votes=value)
    with face.capture() as notices:
        settings.save(folder, candidate)
    said, failure = setup.update_privacy(face, folder, candidate)
    return (shown + render_notices(notices) + f"<h1>{say('votes_setup.saved.title')}</h1>"
            + said + failure + f"<p>{say('votes_setup.saved')}</p>"
            + f"<p>{say(_verdict(value, client))}</p>"
            + f'<p><a href="{PAGE}">{say("votes_setup.back")}</a></p>')


def _checked(face: Face, folder: Path, client: Transport | None) -> str:
    saved, shown = loaded_settings(face, folder)
    if saved is None or saved.votes is None:
        return _show(face, folder)
    return (shown + f"<h1>{say('votes_setup.title')}</h1>"
            + f"<p>{say(_verdict(saved.votes, client))}</p>"
            + f'<p><a href="{PAGE}">{say("votes_setup.back")}</a></p>')


def _off(face: Face, folder: Path) -> str:
    """§ 4.6: `votes` alone goes. Votes stay in the writer's database, and the
    Privacy words and each entry's key stay."""
    saved, shown = loaded_settings(face, folder)
    if saved is None:
        return _not_set_up(shown)
    with face.capture() as notices:
        settings.save(folder, dataclasses.replace(saved, votes=None))
    return (shown + render_notices(notices) + f"<h1>{say('votes_setup.title')}</h1>"
            + f"<p>{say('votes_setup.off.done')}</p>"
            + f'<p><a href="{PAGE}">{say("votes_setup.back")}</a></p>')


def _verdict(value: settings.Votes, client: Transport | None) -> str:
    """§ 4.6's table: the words key for what Google answered."""
    # A project enforcing App Check refuses any call without its token, which
    # only a browser on the site can get: Check would report false failures.
    if value.recaptcha_key is not None:
        return "votes_setup.check.recaptcha"
    return _check(value, client if client is not None else https.Client(TIMEOUT_SECONDS))


def _check(value: settings.Votes, client: Transport) -> str:
    """The page's own calls, as votes._SCRIPT makes them: change one, change
    both, or Check tests calls no page sends."""
    gate = f"?key={value.api_key}"
    entry = (f"https://firestore.googleapis.com/v1/projects/{value.project_id}"
             f"/databases/(default)/documents/entries/{_CHECK_ENTRY}")
    json_type = {"Content-Type": "application/json"}
    try:
        status, _, reply = client.request("POST", _SIGN_UP + gate,
                                          json.dumps({"returnSecureToken": True}).encode("utf-8"),
                                          json_type)
        if 400 <= status < 500:
            return _refused_sign_up(status, reply)
        made = json.loads(reply)
        if status != 200 or not isinstance(made, dict):
            return _UNREACHABLE
        vote = f"{entry}/votes/{made['localId']}{gate}"
        signed_in = {**json_type, "Authorization": f"Bearer {made['idToken']}"}

        def write(number: int) -> int:
            body = {"fields": {"value": {"integerValue": str(number)}}}
            return client.request("PATCH", vote, json.dumps(body).encode("utf-8"), signed_in)[0]

    except (OSError, ValueError, KeyError):
        return _UNREACHABLE

    def delete() -> int:
        return client.request("DELETE", vote, None, signed_in)[0]

    try:
        status = write(1)
    except OSError:
        status = None
    if status is None or status >= 500:
        # Sent, with no answer that says whether it landed: remove it anyway.
        _asked(delete)
        return _UNREACHABLE
    if status == 403:
        return _NO_RULES
    if status == 404:
        return _NO_DATABASE
    if not 200 <= status < 300:
        return _UNREACHABLE

    def count() -> int:
        query = {"structuredAggregationQuery": {
            "structuredQuery": {
                "from": [{"collectionId": "votes"}],
                "where": {"fieldFilter": {"field": {"fieldPath": "value"}, "op": "EQUAL",
                                          "value": {"integerValue": "1"}}}},
            "aggregations": [{"alias": "n", "count": {}}]}}
        return client.request("POST", f"{entry}:runAggregationQuery{gate}",
                              json.dumps(query).encode("utf-8"), json_type)[0]

    # The first write landed: the test vote goes whatever came between.
    found = _rules_fault(write, count)
    deleted = _asked(delete)
    return found or deleted or _READY


def _refused_sign_up(status: int, reply: bytes) -> str:
    """Sign-up refused: the key itself, or Anonymous sign-in left off.
    Firebase's Auth reference names "API key not valid" and
    OPERATION_NOT_ALLOWED as answers. A 403 is Google's answer to a key
    restricted from this call or an API turned off; that is not measured."""
    try:
        message = json.loads(reply)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = ""
    if status == 403 or (isinstance(message, str) and message.startswith("API key not valid")):
        return _KEY_REFUSED
    return _ANONYMOUS


def _rules_fault(write: Callable[[int], int], count: Callable[[], int]) -> str | None:
    """None where the rules hold: a value of 5 refused, and a count with no
    sign-in allowed. Else the words key for what is wrong."""
    try:
        status = write(5)
    except OSError:
        return _UNREACHABLE
    if 200 <= status < 300:
        return _WRONG_RULES
    if status >= 500:
        return _UNREACHABLE
    return _asked(count)


def _asked(step: Callable[[], int]) -> str | None:
    """None where Google allowed `step`, else what to say."""
    try:
        status = step()
    except OSError:
        return _UNREACHABLE
    if 200 <= status < 300:
        return None
    return _WRONG_RULES if status < 500 else _UNREACHABLE
