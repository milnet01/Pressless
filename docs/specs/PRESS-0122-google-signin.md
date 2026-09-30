# PRESS-0122 — Setup's second step: signing in with Google for the dashboard

**Status:** accepted (2026-10-01). Gated for one loop, the user's round budget; every verified finding fixed, none left in the tail.
Amended 2026-10-01 after registration measured Google requiring the client
secret: §3 decision 3, §4.7 and INV-16 by the user's decision, and INV-17
from the first real sign-in. Re-gated for one loop the same day; every verified finding fixed.
**Kind:** implement.
**Source:** ROADMAP PRESS-0122 (split from PRESS-0021 by the user
2026-09-17; the route and the property list chosen by the user
2026-10-01; the research of 2026-09-30 is in the roadmap item's body).

**Blocked by:** PRESS-0019 and PRESS-0021, both shipped.
**Blocker for:** PRESS-0020.
**Amends:** PRESS-0011 (§4.5), PRESS-0021 (§4.6, §4.9) and PRESS-0019
(§9). §11 lists each edit.

Layman: he clicks "Sign in with Google", picks his site from a list, and
Pressless can read his visitor numbers from then on; or he says no and
loses only the dashboard.

## 1. Goal

After this ships, a set-up Pressless offers an optional second step at
`/setup/google`. He signs in on Google's own page, comes back to
Pressless, and picks his Analytics property from a list of the ones his
Google account can see. Pressless keeps Google's long-lived permission
in the same store as the publishing key, and turns it into the
short-lived token Insights needs whenever the dashboard asks. He can
turn it off again, and Google is told.

## 2. Problem

1. **Insights has a token argument and nothing supplies it.**
   `insights.read` takes `token: str`, and PRESS-0019 §9 leaves obtaining
   and refreshing it to setup. Setup writes `credentials.google_account`
   and `analytics_property_id` as absent (PRESS-0021 §3 decision 1), so
   nothing ever fills them.
2. **The Face refuses the page Google sends him back to.** The session
   cookie is `SameSite=Strict` (PRESS-0011 §4.5, `face._Handler._dispatch`).
   A Strict cookie is sent *"only for requests originating from the same
   site that set the cookie"*, and Google's redirect originates on
   Google's site, so the Face answers 403. Source:
   <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie>.
   Unmeasured here; §7's hand check is where it is seen.
3. **Google requires a client secret, and it cannot sit in this
   repository.** Measured 2026-10-01 against the registered client: an
   exchange without one answers `400` with *"client_secret is missing."*,
   though Google's desktop-app page lists the field as optional. The
   repository is public, and GitHub push-protects Google secrets by default
   and tells Google, which may revoke them. Source:
   <https://github.blog/changelog/2026-03-31-github-secret-scanning-nine-new-types-and-more/>
4. **The numeric property id is hard to find.** `settings.check` refuses
   the `G-…` tag people paste instead (PRESS-0056), which says the mistake
   is common. The user chose a list over a typed number.

## 3. Scope decisions (agreed with the user)

1. **Route A: sign in with Google, one desktop OAuth client shipped with
   Pressless.** Decided by the user 2026-10-01. The user registers the
   client in their own Google Cloud account (§4.6). Route B, a service
   account per person, is not built.
2. **The property is picked from a list.** Decided by the user
   2026-10-01. Pressless asks Google's Admin API which properties the
   account can see.
3. **The client secret is added when a release is packaged, and never
   committed.** Decided by the user 2026-10-01, after §2 item 3's
   measurement. The secret is a GitHub Actions secret; the release build
   writes it into the packaged program (§4.7). Google's own page says an
   installed app's secret is not treated as a secret, so shipping it inside
   the program is its intended use; keeping it out of the repository is
   what GitHub's push protection requires. PKCE is kept.
4. **(decided here) The Face's own server is the loopback redirect.**
   Google accepts `http://127.0.0.1:<port>/<path>` with any port for a
   desktop client (same source), and the Face already listens there.
5. **(decided here) Turning it off revokes at Google and clears both
   settings fields.** The stored value is left in the store, dead, and the
   next sign-in writes over it. Credentials has no delete, and adding one
   would amend PRESS-0002 for a value that no longer opens anything.
6. **(decided here) The code that talks to Google belongs to Insights**
   (`docs/design.md` rule 8), in its own module. The pages are the Face's,
   in their own module beside `setup.py`.
7. **(decided here) What the dashboard does when a refresh fails is
   PRESS-0020's.** This item supplies the token and the typed failures.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 Talking to Google: `src/pressless/google_signin.py`

Part: Insights. It imports `insights` for `Transport`, the failure types
and its client, and `_google_secret` (§4.7), and no other Pressless module.

```python
CLIENT_ID = "…"         # the registered Desktop client's id (§4.6)
CLIENT_SECRET = …       # _google_secret.CLIENT_SECRET, or "" where that module is absent
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
ACCOUNTS_URL = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
ATTEMPT_SECONDS = 600.0  # how long a sign-in may take on Google's page
PAGE_LIMIT = 10          # accountSummaries pages followed, at 200 accounts each

@dataclass(frozen=True)
class Attempt:
    state: str
    verifier: str
    redirect_uri: str
    started: float       # the transport's clock

@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_at: float    # the transport's clock

@dataclass(frozen=True)
class Property:
    id: str              # digits only, the form Settings keeps
    name: str            # Google's display name
    account: str         # the Analytics account's display name

class Declined(insights.InsightsError): ...  # he said no on Google's page
class Expired(insights.InsightsError): ...   # the sign-in took too long

def available() -> bool
def begin(redirect_uri: str, client: Transport | None = None) -> tuple[Attempt, str]
def finish(attempt: Attempt, query: dict[str, str],
           client: Transport | None = None) -> str
def access_token(refresh_token: str,
                 client: Transport | None = None) -> AccessToken
def properties(token: str, client: Transport | None = None) -> tuple[Property, ...]
def revoke(refresh_token: str, client: Transport | None = None) -> None
```

`client` defaults to the client Insights builds for itself (certifi's
certificates, its timeout, `_NoCrossOriginAuth`). Same part, so this is
not one part reaching inside another.

- **`available()`** is true where `CLIENT_ID` and `CLIENT_SECRET` are both
  non-empty.
- **`begin`** makes `state = secrets.token_urlsafe(32)` and
  `verifier = secrets.token_urlsafe(64)`, which is 86 characters, inside
  PKCE's 43 to 128. It returns the attempt and the address of Google's
  page: `AUTH_URL` with `client_id`, `redirect_uri`, `response_type=code`,
  `scope=SCOPE`, `state`, `code_challenge` (unpadded base64url of the
  verifier's SHA-256), `code_challenge_method=S256`,
  `access_type=offline` and `prompt=consent`. The last two make Google
  hand back a refresh token every time, not only on the first consent.
  It makes no request.
- **`finish`** checks, in this order, before any request: the query's
  `state` equals `attempt.state` (`hmac.compare_digest`), else
  `Expired`; the attempt is younger than `ATTEMPT_SECONDS`, else
  `Expired`; the query carries no `error`, else `Declined` when it is
  `access_denied` and `InsightsError` otherwise. Then one `POST` to
  `TOKEN_URL`, form-encoded: `code`, `client_id`, `client_secret`,
  `code_verifier`, `redirect_uri`, `grant_type=authorization_code`. It returns the answer's
  `refresh_token`. An answer without one is an `InsightsError`.
- **`access_token`** posts `client_id`, `client_secret`, `refresh_token`
  and `grant_type=refresh_token` to `TOKEN_URL`. `expires_at` is the clock
  when the request was made, plus the answer's `expires_in`.
- **`properties`** sends `GET ACCOUNTS_URL?pageSize=200` with the token as
  a bearer header, and follows `nextPageToken` for at most `PAGE_LIMIT`
  pages. Each `propertySummaries` entry's `property` is
  `properties/<digits>`; the digits become `id`. An entry whose id is not
  ASCII digits after that prefix is dropped. Google's order is kept. An
  answer with no `accountSummaries`, or a summary with no
  `propertySummaries`, is no properties, not a missing field.
- **`revoke`** posts `token=<refresh_token>` to `REVOKE_URL`.

**What each answer means**, for every request above:

| What happens | What is raised |
|---|---|
| The transport raises `OSError` | `insights.Unreachable` |
| 400 whose `error` is `invalid_grant`, or 401, or 403 | `insights.Refused` |
| 429 | `insights.RateLimited` |
| Anything else that is not 200 | `insights.InsightsError` |
| 200 that is not JSON, or lacks the field this call reads — except `revoke`, which reads no body | `insights.InsightsError` |

Google's error code rides on `detail` — the sign-in endpoints' `error`,
the Admin API's `error.status` — and never its free-text description,
which can quote what was sent. **No message or detail ever carries a
token, the code, the verifier or the client secret.**

### 4.2 The pages: `src/pressless/google_setup.py`

Part: the Face. Registered by `google_setup.register(face, folder, *,
client=None)`, called wherever `setup.register` is.

```python
GOOGLE_ACCOUNT = "google"                 # the account the refresh token is filed under
SIGN_IN = "your Google sign-in"           # the {secret} noun (PRESS-0011 § 4.2)
RETURN_PATH = "/setup/google/back"        # the redirect_uri's path

def register(face: Face, folder: Path, *,
             client: insights.Transport | None = None) -> None: ...
def token(folder: Path) -> str: ...       # for PRESS-0020's dashboard
```

The module holds, in memory and under one lock: **the pending attempt**
(at most one), **the pending list** (the last return's properties, with
its refresh and access tokens; at most one), and **the held token** (an `AccessToken` or nothing).
None of these is ever written to disk.

Every page but the return (§4.3) first runs `settings.load(folder)`
inside `face.capture()`. Anything but a `Settings` shows a sentence
sending him to `/setup` and does nothing else. The return loads no
Settings: it is reached only through an attempt, which start made after
its own load.

| Request | What it does |
|---|---|
| `GET /setup/google` | Where `available()` is false: says this copy of Pressless cannot connect to Google, and offers nothing. Where a pending list exists: the list, as one choice per property (its name and account), and a Use this site button. Otherwise, where `google_account` is set: the property id in use, a Sign in again button, which posts to `/setup/google/start` like first sign-in and is the route after a `Refused`, and a Turn off button. Otherwise: what the dashboard is, a warning about Google's unverified-app screen, and a Sign in with Google button. |
| `POST /setup/google/start` | Where `available()` is false, the same page as above and no redirect. Otherwise `begin(redirect_uri)` with `redirect_uri = face origin + RETURN_PATH`; the attempt replaces any pending one; the answer is `303` to Google's page. |
| `GET RETURN_PATH` | §4.3. |
| `POST /setup/google/choose` | The body's `property` must equal one pending `Property.id`, or the list is shown again with a hint and nothing is written. Then `credentials.write(saved store, folder, GOOGLE_ACCOUNT, pending refresh token)`. Then the candidate is the loaded `Settings` with `credentials.google_account = GOOGLE_ACCOUNT` and `analytics_property_id` the chosen id; `settings.check`, then `settings.save`, inside `face.capture()`. Only then does the pending access token become the held token, and the pending list is cleared. The page says the dashboard is ready. |
| `POST /setup/google/off` | Where `google_account` is set: `credentials.read` it, then `revoke`. A failed read is a failed revoke. Whatever `revoke` does, save the loaded `Settings` with `google_account` and `analytics_property_id` both `None`, and drop the held token and the pending list. Where the revoke failed, the page says so and names Google's own page for removing access, <https://myaccount.google.com/permissions>. |

**`token(folder)`** uses the `client` `register` was given, and its
clock; so `register` runs first, as it does at every launch. It loads Settings, raises `insights.NotConfigured` where
`google_account` is `None`, and otherwise returns the held token's value
while it is more than 60 seconds from `expires_at`. Past that, it
`credentials.read`s the refresh token, calls `access_token`, holds the
answer and returns its value. It raises what those raise. A choose
replaces the held token and an off drops it.

The warning before sign-in says, in his words: Google will say it has not
verified this app; Pressless only reads visitor numbers; to carry on, click
Advanced and then Go to Pressless. The exact words are the implementer's.

### 4.3 The return from Google

Google sends the browser to `RETURN_PATH?state=…&code=…`, or `…&error=…`.
It carries no Face cookie (§2 item 2). So:

1. **The Face lets this one GET through without the cookie.** It is
   registered with a new `face.add_return_page(path, page)`: GET only, one
   path per call, and every other check in PRESS-0011 §4.5 still runs,
   `Host` included. A POST to it, or any other path without the cookie,
   is 403 as before.
2. **The page authenticates the request itself, with the attempt.** No
   pending attempt, or a `state` that does not match it, answers `403`
   exactly as a missing cookie does, and leaves any pending attempt
   pending. A matching `state` **spends the attempt**, whatever follows,
   so the same address a second time is 403.
3. Then `finish`, then `access_token`, then `properties`. The refresh
   token, the access token and the list are held **with the pending list**,
   in memory. **Nothing is written here, and the held token is not
   replaced**: the store and Settings change only at choose, so a sign-in
   left before choosing leaves the dashboard as it was.
4. **The answer does not depend on the cookie.** It says he is signed in
   and carries one link to `/setup/google`, plus
   `<meta http-equiv="refresh" content="0; url=/setup/google">`. Following
   either is a navigation this page starts, so the browser sends the
   cookie. **A failure is shown through `Face.fail` on this same page, with
   the link and no refresh**, so the failure stays on screen until he
   follows it.
5. **An empty list is not a failure, and is shown like one:** the link and
   no refresh. The page says his Google account can see no Analytics
   property, and to sign in with the account that can.

A credential failure at choose passes `secret=SIGN_IN`. The code and the
state are in the address bar and the browser's history; both are useless
once the attempt is spent, and the code is useless without the verifier,
which never leaves memory.

### 4.4 What the Face says

`Declined`: he chose not to let Pressless read his visitor numbers; the
site is unchanged; sign in again from Settings whenever he likes.
`Expired`: the sign-in took too long; sign in again. A return whose
attempt was replaced by a later sign-in gets §4.3's bare 403. Both are entries in the Face's failure table, which
PRESS-0011 INV-1 already requires of every failure type. The existing
`insights.Refused` sentence already says to sign in to Google again from
Settings.

### 4.5 Where he reaches it

- **Setup's done page** (`setup._done`) ends with a link to
  `/setup/google`, labelled as optional, where `available()` is true.
- **The Settings page** (`/setup` once set up) carries the same link.

### 4.6 Registering the client

Done once, by the user, in their own Google Cloud account, before
`CLIENT_ID` is filled:

1. A project, with the Google Analytics Data API and the Google
   Analytics Admin API enabled.
2. An OAuth consent screen, External, with the scope `SCOPE`, **published
   to In production**. Left in Testing, refresh tokens die after seven days
   and only listed testers may sign in (the roadmap item's research).
3. An OAuth client of type Desktop app. Its id goes into `CLIENT_ID`.
   Its secret goes, by the user's own hand, into the repository's GitHub
   Actions secret `GOOGLE_CLIENT_SECRET`, and on a development machine
   through §4.7's script. It is copied nowhere else.
4. One real sign-in, exchange and refresh through Pressless. The
   dashboard's first live read is PRESS-0020's and PRESS-0132's.

The steps go in `docs/working-here.md` (§11). Where either value is
missing, `available()` is false and nothing in this section is reachable.

### 4.7 Where the secret comes from

```python
# src/pressless/_google_secret.py -- generated, never committed
CLIENT_SECRET = "…"
```

`scripts/write_google_secret.py [path]` writes that file, `path`
defaulting to `src/pressless/_google_secret.py`. It takes the value from
the environment variable `GOOGLE_CLIENT_SECRET`, or, where that is unset
and it runs in a terminal, asks for it without echoing it
(`getpass`). Unset and no terminal is an empty value. It refuses, exiting non-zero and writing nothing, a value
that is empty or holds anything but ASCII letters, digits, `-` and `_`.
It writes the value with `repr`, and prints nothing that carries it.

- **`.gitignore` names the file**, so `git add -A` cannot commit it.
- **Both release jobs in `.github/workflows/release.yml` run the script
  after the suite and before their Build step**, with `GOOGLE_CLIENT_SECRET` set from
  `${{ secrets.GOOGLE_CLIENT_SECRET }}`. A release whose secret is missing
  fails there, before anything is built or signed.
- **PyInstaller finds the module by its import in `google_signin`**, so no
  build flag changes. The import is inside `try`/`except ImportError`,
  which a development checkout without the file needs.

## 5. Invariants

`tests/test_google_signin.py` holds INV-1 to INV-8, driving a
`Transport` double that records each request and answers from a script.
`tests/test_google_setup.py` holds INV-10 to INV-15 and INV-17, through `face.serve(tmp_path)`
with that double, a `credentials` double, and a real settings file.

- **INV-1** — `google_signin` imports no Pressless module but `insights`
  and `_google_secret`.
  *Test:* `test_signin_imports_only_insights_and_its_secret`, reading the module's
  imports as `test_insights_imports_no_forbidden_sibling` does.
  *Breaks when:* it imports `credentials` or `settings` to fetch the token
  or the property id itself, which `docs/design.md` rule 10 gives to the
  Face.

- **INV-2** — `begin`'s address carries every parameter §4.1 names, the
  challenge is the S256 of the attempt's verifier, the verifier is 43 to
  128 unreserved characters, two calls give different states and
  verifiers, and no request is made.
  *Test:* `test_begin_builds_a_pkce_address`.
  *Breaks when:* the challenge is the plain verifier, the state is fixed,
  or `access_type=offline` is dropped, after which Google sends no refresh
  token.

- **INV-3** — `finish` makes no request unless the state matches, the
  attempt is in time, and the query carries no error.
  *Test:* `test_finish_refuses_before_any_request` — a wrong state and a
  late attempt each raise `Expired`; `error=access_denied` raises
  `Declined`; the double records no request in any of the three.
  *Breaks when:* the exchange runs first and the state is compared after.

- **INV-4** — The exchange and the refresh send exactly the fields §4.1
  names, `client_secret` included; `revoke` and `properties` send no
  secret.
  *Test:* `test_the_secret_goes_only_to_the_token_endpoint`, reading each
  recorded body with `urllib.parse.parse_qs` and each header.
  *Breaks when:* the secret is dropped from the refresh, after which every
  dashboard read after the first hour fails; or it is sent to the Admin
  API.

- **INV-5** — An exchange answered without a `refresh_token` raises; it is
  never stored as an empty string.
  *Test:* `test_an_exchange_without_a_refresh_token_is_refused`.
  *Breaks when:* `finish` returns `answer.get("refresh_token", "")`.

- **INV-6** — Every request maps its answers as §4.1's table says.
  *Test:* `test_each_answer_maps_to_its_failure`, over the exchange, the
  refresh, `properties` and `revoke`, with `OSError`, 400 `invalid_grant`,
  400 other, 401, 403, 429, 500, and a 200 that is not JSON.
  *Breaks when:* 400 `invalid_grant` becomes a plain `InsightsError`, and
  a revoked sign-in tells him something went wrong instead of to sign in
  again.

- **INV-7** — No failure's message or detail carries the refresh token,
  the access token, the code, the verifier or the client secret.
  *Test:* `test_no_failure_names_a_token`, with a sentinel in each, and a
  Google answer that quotes all five back.
  *Breaks when:* Google's `error_description` is copied into `detail`
  unfiltered while it quotes the token.

- **INV-8** — `properties` follows pages to `PAGE_LIMIT` and no further,
  strips `properties/`, drops an id that is not ASCII digits, and keeps
  Google's order; an answer with no `accountSummaries` is no properties.
  *Test:* `test_properties_are_listed_across_pages` — two pages, one entry
  named `properties/12x`; then a double that always names a next page,
  which stops at `PAGE_LIMIT` requests; then `{}`, which returns `()`.
  *Breaks when:* the loop follows `nextPageToken` without a cap, or keeps
  an id `settings.check` would then refuse.

- **INV-9** — Only `RETURN_PATH`, only by GET, is reached without the
  cookie, and the `Host` check still applies to it.
  *Test:* `tests/test_face.py::test_a_return_page_is_the_only_door_without_the_cookie`
  — with a return page registered: its GET without the cookie reaches it;
  its POST without the cookie is 403; `/setup/google` without the cookie
  is 403; its GET with `Host: pressless.example` is 403.
  *Breaks when:* `add_return_page` registers an ordinary page with the
  cookie check switched off for the whole Face, or for every method.

- **INV-10** — A return is honoured once, and only for the pending
  attempt.
  *Test:* `test_the_return_is_honoured_once` — a return with no pending
  attempt is 403; a wrong state is 403 and the right one then still
  works; the right one a second time is 403.
  *Breaks when:* a wrong state spends the attempt, letting any local page
  cancel his sign-in, or the right one is accepted twice.

- **INV-11** — The refresh token is written under `GOOGLE_ACCOUNT` in the
  saved store, and reaches no page, the log or the console.
  *Test:* `test_the_sign_in_is_stored_and_never_shown`, with a sentinel
  token, reading the page, `pressless.log` and captured output.
  *Breaks when:* the return page echoes Google's answer, or a failure's
  detail carries it.

- **INV-12** — Settings and the store are written only by a choose, and
  only with an id from the pending list.
  *Test:* `test_only_a_listed_property_is_saved` — after a return the
  settings file is unchanged, `credentials.write` was not called, and
  `token` still returns the earlier sign-in's token; a choose naming an id not in the list
  re-shows the list and leaves the file unchanged; a listed id saves
  `google_account` and the id, and the file loads.
  *Breaks when:* the return page saves the first property or stores the
  new sign-in, or choose trusts the posted id.

- **INV-13** — Turning off clears both fields whether or not Google
  answered the revoke, and says so when it did not.
  *Test:* `test_turning_off_clears_both_fields` — once with `revoke`
  answering 200 and once raising `OSError`; both save `None` twice, and
  the second page names Google's permissions page.
  *Breaks when:* a failed revoke stops the save, so offline he cannot turn
  the dashboard off.

- **INV-14** — `token` reuses the held token until 60 seconds before it
  expires, refreshes after; a choose replaces it and an off drops it.
  *Test:* `test_the_token_is_reused_until_it_nearly_expires`, moving the
  double's clock.
  *Breaks when:* every dashboard view refreshes, or a token from before
  Turn off is still handed out.

- **INV-15** — With an empty `CLIENT_ID` or `CLIENT_SECRET`, nothing
  reaches Google.
  *Test:* `test_an_unregistered_copy_offers_no_sign_in` — `/setup/google`
  has no Sign in button, `POST /setup/google/start` answers without a
  redirect, setup's done page has no link, and the double records no
  request; once with each value empty.
  *Breaks when:* the button is shown and Google answers him with an error
  page about a missing client.

- **INV-16** — The secret file is never committed, and a release cannot
  be built without it.
  *Test:* `tests/test_write_google_secret.py` — `git check-ignore` names
  `src/pressless/_google_secret.py`; the script with the variable empty,
  or holding a quote, exits non-zero and writes nothing; with a valid
  value it writes a file whose `CLIENT_SECRET` imports back equal, and
  its output does not carry the value; and each job in `release.yml`
  runs the script, with `GOOGLE_CLIENT_SECRET` set from the Actions
  secret, after its suite step and before its Build step.
  *Breaks when:* the `.gitignore` line is dropped, the script writes an
  empty secret, or a job loses the step — each ships a release with the
  Google step silently unavailable.

- **INV-17** — A failed return keeps its failure on screen.
  *Test:* `test_a_failed_return_stays_on_screen`, where the exchange
  answers `400`, and one whose account sees no property: each page
  carries its message, the link, and no `http-equiv="refresh"`; a
  successful return carries the refresh.
  *Breaks when:* the refresh is added to every return, and the failure
  flashes past before it can be read — which the first real sign-in
  measured.

## 6. Failure modes

- **He closes Google's page.** The attempt stays pending until it is
  replaced or expires. Nothing was written.
- **Pressless restarts during a sign-in.** The Face has a new port and no
  attempt, so Google's redirect reaches nothing. He starts again.
- **The refresh token is revoked at Google, or unused for six months.**
  The next `token` raises `Refused`, whose sentence says to sign in again
  from Settings.
- **The store cannot be written.** `credentials.write` raises, the page
  shows it with `SIGN_IN`, and Settings is unchanged.
- **Offline at Turn off.** Settings is cleared anyway (INV-13), and the
  refresh token stays valid at Google until he removes it there.
- **Google's lifetime user cap is reached, or the client is disabled.**
  Google's page shows its own error and returns `error=…`; he sees an
  `InsightsError` carrying Google's reason. Pressless cannot fix either.

## 7. Tests

§5 names each test, and §10 lists them by invariant:
`tests/test_google_signin.py` covers INV-1, INV-2, INV-3, INV-4, INV-5,
INV-6, INV-7 and INV-8; `tests/test_face.py` covers INV-9;
`tests/test_google_setup.py` covers INV-10, INV-11, INV-12, INV-13,
INV-14, INV-15 and INV-17; `tests/test_write_google_secret.py` covers
INV-16. Each is seen failing against a stub before the code it
locks is written. INV-1's pattern already exists in
`tests/test_insights.py`.

**By hand, once the client is registered** (`docs/working-here.md`
§ Windows and browser checks): a real sign-in in Firefox, Chrome and Edge,
on Linux and on the Windows box, confirming that the continue navigation
carries the cookie (§4.3 step 4), and a packaged release's sign-in
(§4.7).

## 8. Alternatives considered (and rejected)

| Rejected | Why |
|---|---|
| **Route B, a service account per person** | Six steps in Google's console for each person, and a key too long for Windows' credential store without splitting it. The user chose route A. |
| **A typed property id** | The user chose the list; the typed id is the mistake `settings.check` already has to catch. |
| **Shipping the client secret in the source** | GitHub blocks the push and Google may revoke the secret (§2 item 3). |
| **Disguising the secret in the source** so the scanner misses it | Rejected by the user 2026-10-01: it defeats a safety check, and Google could still find and revoke it. |
| **No secret, PKCE alone** | Google refuses the exchange (§2 item 3). |
| **A second listener for the redirect** | The Face already listens on `127.0.0.1`; a second server is a second boundary to defend. |
| **Relaxing the cookie to `SameSite=Lax`** | Every GET on the Face would then carry the cookie from any site's link, for the sake of one path. |
| **Saving the first property automatically** | Most people have one, but one account can see many, and a wrong property shows someone else's numbers without saying so. |
| **Deleting the stored token at Turn off** | Needs a delete in Credentials, amending PRESS-0002, for a value the revoke has already made useless. |
| **A lazy token passed into `insights.read`** | Would let a fresh cache answer offline without a refresh, but it amends PRESS-0019's contract. It is PRESS-0020's choice, with the facts in §9. |

## 9. Out of scope

- **The dashboard, and what it does when `token` raises** — PRESS-0020.
  Its decision: calling `token` first means a failed refresh hides numbers
  a fresh or stale cache could have shown; avoiding that needs
  `insights.read` to take the token lazily, which amends PRESS-0019.
- **The first live read of the Data API** — PRESS-0132, while building
  PRESS-0020.
- **Google's verification of the app**, which lifts the warning and the
  user cap — deferred; not yet queued.
- **Showing the property's name where it is in use.** Settings keeps the
  id only, and keeping the name would add a settings field — deferred;
  not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_google_signin.py::test_signin_imports_only_insights_and_its_secret` |
| INV-2 | `tests/test_google_signin.py::test_begin_builds_a_pkce_address` |
| INV-3 | `tests/test_google_signin.py::test_finish_refuses_before_any_request` |
| INV-4 | `tests/test_google_signin.py::test_the_secret_goes_only_to_the_token_endpoint` |
| INV-5 | `tests/test_google_signin.py::test_an_exchange_without_a_refresh_token_is_refused` |
| INV-6 | `tests/test_google_signin.py::test_each_answer_maps_to_its_failure` |
| INV-7 | `tests/test_google_signin.py::test_no_failure_names_a_token` |
| INV-8 | `tests/test_google_signin.py::test_properties_are_listed_across_pages` |
| INV-9 | `tests/test_face.py::test_a_return_page_is_the_only_door_without_the_cookie` |
| INV-10 | `tests/test_google_setup.py::test_the_return_is_honoured_once` |
| INV-11 | `tests/test_google_setup.py::test_the_sign_in_is_stored_and_never_shown` |
| INV-12 | `tests/test_google_setup.py::test_only_a_listed_property_is_saved` |
| INV-13 | `tests/test_google_setup.py::test_turning_off_clears_both_fields` |
| INV-14 | `tests/test_google_setup.py::test_the_token_is_reused_until_it_nearly_expires` |
| INV-15 | `tests/test_google_setup.py::test_an_unregistered_copy_offers_no_sign_in` |
| INV-16 | `tests/test_write_google_secret.py` |
| INV-17 | `tests/test_google_setup.py::test_a_failed_return_stays_on_screen` |
| §4.4's two new sentences | `tests/test_face.py`'s PRESS-0011 INV-1 test, which fails on a failure type with no entry |
| §4.3 step 4, the cookie arriving on the continue navigation | **nothing automatic** — browser behaviour; the hand check in §7 |
| §4.7, a packaged release carrying the secret | **Partial:** INV-16 holds the step and the script; that the frozen program imported the module is seen only by §7's hand check on a release |
| §4.6 step 2, the consent screen published to In production | **nothing** — a setting in the user's Google Cloud account; a Testing screen shows as sign-ins failing after seven days |

## 11. Cross-doc impact

The new direction is gated in this spec; each edit below is a pointer to
it.

- **PRESS-0011** — §4.5's *"Every other request must carry the session
  cookie"* gains *"except a GET to a path registered with
  `add_return_page` (PRESS-0122 §4.3)"*, and its `add_page` bullet names
  `add_return_page` beside it.
- **PRESS-0021** — §4.6's closing paragraph gains setup's link to
  `/setup/google` (PRESS-0122 §4.5). §4.9's last bullet gains *"setup.py
  never touches …; PRESS-0122's pages do"*.
- **PRESS-0019** — §9's first bullet names PRESS-0122 as the owner of
  obtaining and refreshing the token.
- **`docs/design.md` rule 10** — unchanged: the Face still fetches the
  secret and hands a token to Insights.
- **`docs/working-here.md`** — a section *Registering the Google client*,
  carrying §4.6's steps.
- **`CHANGELOG.md`** — an entry when this ships.
- **`.github/workflows/release.yml`** — both jobs gain §4.7's step.
- **PRESS-0022** — its release steps gain a pointer to §4.7.
- **The leak sweep** — nothing: `CLIENT_ID` is not a secret, and the
  secret never enters the repository.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0122-google-signin-loop-log.md`.

## 13. Resource cost

Three small values in memory, each bounded at one: an attempt, a
pending list capped by `PAGE_LIMIT` with its two tokens, and a held token. No new dependency: `hashlib`,
`hmac`, `base64` and `secrets` are the standard library.
