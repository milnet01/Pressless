"""Like and Dislike buttons on an entry (PRESS-0211).

The contract is docs/specs/PRESS-0211-likes-and-dislikes.md. What the writer
pastes into Firebase, what the Builder writes into an entry page, and how a
pasted firebaseConfig is read. It touches no disk and no network: the browser
of whoever reads the site talks to Google, and only ever to the site's own
project.

Everything `page_code` carries has passed settings.check_votes, whose patterns
are what make it safe to write without escaping.
"""
from __future__ import annotations

import html
import json
import re

from pressless import settings
from pressless.words import say

ADDRESS = "/votes"   # the setup screen, which setup.py links to

# § 4.4. Measured on the emulators by scripts/by-hand-votes-rules.py.
RULES = """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /entries/{entry}/votes/{voter} {
      allow list: if true;
      allow get, delete: if request.auth != null && request.auth.uid == voter;
      allow create, update: if request.auth != null
        && request.auth.uid == voter
        && entry.size() <= 200
        && entry.matches('[0-9]{4}-[0-9]{2}-[0-9]{2}-.+')
        && request.resource.data.keys().hasOnly(['value'])
        && request.resource.data.value in [1, -1];
    }
  }
}
"""

# § 4.3: colours inherit, a pressed button differs by more than colour, and a
# count holds its space empty, so nothing shifts when numbers arrive.
_STYLE = (
    ".votes{display:flex;flex-wrap:wrap;gap:.75em;margin:1.5em 0}"
    ".votes .vote{font:inherit;color:inherit;background:none;border:2px solid currentColor;"
    "border-radius:.4em;padding:.5em 1em;cursor:pointer}"
    ".votes .vote:disabled{cursor:default;opacity:.7}"
    '.votes .vote[aria-pressed="true"]{text-decoration:underline;'
    "box-shadow:inset 0 0 0 2px currentColor}"
    ".votes .vote-count{display:inline-block;min-width:4ch;text-align:left}"
)

_FIREBASE_FILES = "https://www.gstatic.com/firebasejs/13.1.0/"

# § 4.3 step 4, where the site's owner chose App Check.
_APP_CHECK = f"""
const {{initializeApp}} = await import("{_FIREBASE_FILES}firebase-app.js");
const {{initializeAppCheck, ReCaptchaEnterpriseProvider, getToken}} =
  await import("{_FIREBASE_FILES}firebase-app-check.js");
const appCheck = initializeAppCheck(
  initializeApp({{apiKey: CONFIG.key, projectId: CONFIG.project, appId: CONFIG.app}}),
  {{provider: new ReCaptchaEnterpriseProvider(CONFIG.recaptcha),
    isTokenAutoRefreshEnabled: true}});
const guarded = async (sent) =>
  ({{...sent, "X-Firebase-AppCheck": (await getToken(appCheck)).token}});
"""

_NO_APP_CHECK = "const guarded = async (sent) => sent;\n"

# §§ 4.3 and 6. The numbers and the pressed mark change only on success, so a
# failed press has nothing to put back. Any failure ends in the last catch: no
# message, and nothing outside the box is touched.
_SCRIPT = """
const box = document.querySelector(".votes[data-vote]");
const buttons = [...box.querySelectorAll("button.vote")];
const KEY = box.dataset.vote;
const NOTE = "pressless-votes";
const GATE = `?key=${CONFIG.key}`;
const ENTRY = `https://firestore.googleapis.com/v1/projects/${CONFIG.project}` +
  `/databases/(default)/documents/entries/${encodeURIComponent(KEY)}`;
const JSON_TYPE = {"Content-Type": "application/json"};
const counts = {};

function worked(answer) {
  if (!answer.ok) throw new Error(`answered ${answer.status}`);
  return answer;
}

async function firestore(path, method, body, token) {
  const sent = await guarded(token ? {...JSON_TYPE, Authorization: `Bearer ${token}`} : JSON_TYPE);
  return worked(await fetch(ENTRY + path + GATE, {method, headers: sent,
                                                  body: body && JSON.stringify(body)}));
}

async function counted(value) {
  const answer = await firestore(":runAggregationQuery", "POST", {
    structuredAggregationQuery: {
      structuredQuery: {
        from: [{collectionId: "votes"}],
        where: {fieldFilter: {field: {fieldPath: "value"}, op: "EQUAL",
                              value: {integerValue: String(value)}}},
      },
      aggregations: [{alias: "n", count: {}}],
    },
  });
  const [row] = await answer.json();
  return Number(row.result.aggregateFields.n.integerValue);
}

function canRemember() {
  try {
    localStorage.setItem(NOTE + "-probe", "1");
    localStorage.removeItem(NOTE + "-probe");
    return true;
  } catch {
    return false;
  }
}

function readNote() {
  try {
    const held = JSON.parse(localStorage.getItem(NOTE));
    if (typeof held.refresh === "string" && typeof held.votes === "object" && held.votes) {
      return held;
    }
  } catch { /* no note yet, or one that cannot be read: a first vote */ }
  return {refresh: null, votes: {}};
}

function writeNote(note) {
  localStorage.setItem(NOTE, JSON.stringify(note));
}

// One exchange per press. Only a refused token signs up anew: an exchange with
// no answer is a failed press, or a passing outage would double a visitor.
async function session(note) {
  if (note.refresh) {
    const answer = await fetch(`https://securetoken.googleapis.com/v1/token${GATE}`, {
      method: "POST",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: new URLSearchParams({grant_type: "refresh_token", refresh_token: note.refresh}),
    });
    if (answer.ok) {
      const held = await answer.json();
      note.refresh = held.refresh_token;
      writeNote(note);
      return {uid: held.user_id, token: held.id_token};
    }
    if (answer.status !== 400) throw new Error(`answered ${answer.status}`);
  }
  const made = await worked(await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signUp${GATE}`,
    {method: "POST", headers: JSON_TYPE, body: JSON.stringify({returnSecureToken: true})},
  )).json();
  note.refresh = made.refreshToken;
  note.votes = {};
  writeNote(note);
  return {uid: made.localId, token: made.idToken};
}

function show(chosen) {
  for (const button of buttons) {
    const value = Number(button.dataset.value);
    button.querySelector(".vote-count").textContent = String(counts[value]);
    button.setAttribute("aria-pressed", String(value === chosen));
  }
}

function enable(on) {
  for (const button of buttons) button.disabled = !on;
}

async function press(button) {
  enable(false);
  try {
    const note = readNote();
    const {uid, token} = await session(note);
    const value = Number(button.dataset.value);
    const held = note.votes[KEY];
    const path = `/votes/${encodeURIComponent(uid)}`;
    if (held === value) {
      await firestore(path, "DELETE", null, token);
      delete note.votes[KEY];
      counts[value] -= 1;
    } else {
      await firestore(path, "PATCH",
                      {fields: {value: {integerValue: String(value)}}}, token);
      if (held !== undefined) counts[held] -= 1;
      note.votes[KEY] = value;
      counts[value] += 1;
    }
    writeNote(note);
    show(note.votes[KEY]);
  } catch { /* § 4.3: as it was before the press */ }
  enable(true);
}

async function start() {
  await Promise.all(buttons.map(async (button) => {
    counts[button.dataset.value] = await counted(button.dataset.value);
  }));
  if (!canRemember()) {
    show(undefined);    // § 6: a vote could not be remembered, so none is offered
    return;
  }
  show(readNote().votes[KEY]);
  box.addEventListener("click", (event) => {
    const button = event.target.closest("button.vote");
    if (button && !button.disabled) press(button);
  });
  enable(true);
}

start().catch(() => { /* § 4.3: disabled, with no numbers */ });
"""


def buttons(key: str) -> str:
    """§ 4.3: the box, its style, and both buttons disabled, as a preview shows
    them and a published page's script then wakes them."""
    return (f"<style>{_STYLE}</style>\n"
            f'<div class="votes" data-vote="{html.escape(key, quote=True)}">\n'
            + _button("1", say("votes.like")) + _button("-1", say("votes.dislike"))
            + "</div>")


def _button(value: str, label: str) -> str:
    return (f'  <button type="button" class="vote" data-value="{value}" aria-pressed="false" '
            f'disabled>{html.escape(label)} <span class="vote-count"></span></button>\n')


def page_code(votes: settings.Votes) -> str:
    """§ 4.3: the script a published entry page carries."""
    config = {"key": votes.api_key, "project": votes.project_id, "app": votes.app_id,
              "recaptcha": votes.recaptcha_key}
    return ('<script type="module">\n'
            f"const CONFIG = {json.dumps(config)};\n"
            + (_APP_CHECK if votes.recaptcha_key is not None else _NO_APP_CHECK)
            + _SCRIPT + "</script>\n")


def parse_config(pasted: str) -> dict[str, str]:
    """§ 4.6: `api_key`, `project_id` and `app_id` from Firebase's firebaseConfig
    text, each `name: "value"` or `"name": "value"`. Raises SettingsError, key
    "votes", where one is missing or § 4.1 refuses it."""
    found = {}
    for field, name in (("api_key", "apiKey"), ("project_id", "projectId"), ("app_id", "appId")):
        match = re.search(rf'(?<![A-Za-z0-9_]){name}"?\s*:\s*"([^"]*)"', pasted)
        if match is None:
            raise settings.SettingsError(f"the pasted text holds no {name}", "votes")
        found[field] = match.group(1)
    settings.check_votes(settings.Votes(**found, recaptcha_key=None))
    return found
