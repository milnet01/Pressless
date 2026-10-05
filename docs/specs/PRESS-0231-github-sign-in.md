<!-- ants-spec-format: 1 -->
# PRESS-0231 — Sign in with GitHub, so Pressless makes the repository and switches the site on

**Status:** accepted (2026-10-05). One review round, the user's budget for a new spec; its fixes were read by no lane.
**Kind:** feature.
**Source:** ROADMAP PRESS-0231 (user request 2026-10-05; GitHub App chosen
by the user the same day).

**Amends:** PRESS-0212 (§ 3 decision 1, § 4.4), PRESS-0002 (what the GitHub
secret may be) and PRESS-0021 (the Settings page). § 11 lists each edit.

Layman: instead of making a GitHub key by hand, the person signs in to GitHub
once by typing a short code on GitHub's site. Pressless then makes the site's
repository and switches the site on itself, and quietly keeps its sign-in
fresh.

## 1. Goal

After this ships, a copy of Pressless that carries a registered GitHub App
sets up without the person making a key. First run signs them in to GitHub,
has them install the Pressless app, makes a Public repository, and switches
Pages on. Every later GitHub request uses a short-lived pass that Pressless
renews by itself. A copy without a registered app runs PRESS-0212's wizard
unchanged.

## 2. Problem

1. **The key is the hardest step.** PRESS-0212's *key* step sends the person
   deep into GitHub's settings to make a fine-grained key with the right
   permissions on one repository. The 2026-10-05 by-hand run found it the
   step most likely to go wrong (PRESS-0230).
2. **The person makes the repository by hand.** PRESS-0212 § 3 decision 1
   kept it that way because the key that could create one could also delete
   one. The fine-grained key PRESS-0230 settled on already carries
   Administration, which can delete the repository it reaches.
3. **A hand-made key runs out.** GitHub asks how long it lasts; when it ends,
   publishing fails until the person makes another the same way.

## 3. Scope decisions (agreed with the user)

1. **A GitHub App, not an OAuth app.** Decided by the user 2026-10-05. An
   OAuth token needs the `repo` scope to switch Pages on, which reads and
   writes every repository the person has, private ones too, and never
   expires. A GitHub App's user token carries only the permissions the app
   asks for, reaches only repositories the app is installed on, and expires
   after 8 hours. The person can remove the app in one click.
   Source: https://docs.github.com/en/rest/pages/pages
   Source: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
2. **Pressless makes the repository.** Requested by the user 2026-10-05.
   This overturns PRESS-0212 § 3 decision 1 for a copy with a registered
   app. The app's Administration permission can delete a repository it is
   installed on; PRESS-0230's key already could.
3. **(decided here) The device flow, with a press of Next as the poll.** The
   person types a code on `github.com/login/device`. The flow needs no client
   secret, for the first token or for renewing it, so nothing secret ships in
   Pressless. Pressless asks GitHub only when the person presses Next, so no
   background thread polls.
   Source: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens
4. **(decided here) The stored secret is the refresh token, told apart by its
   prefix.** It is filed under PRESS-0212's `GITHUB_ACCOUNT`, where a key is
   filed today. GitHub's refresh tokens start `ghr_`; no key does. Settings'
   format does not change.
   Source: https://github.blog/engineering/platform-security/behind-githubs-new-authentication-token-formats/
5. **(decided here) The hand-made key stays.** A copy without a registered
   app uses PRESS-0212's steps, and Settings keeps its key box on every copy.
   A key typed there replaces a sign-in.
6. **(decided here) Signing in again is a page, `/setup/github`,** reached
   from Settings, as the Google step is reached at `/setup/google`.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The sign-in conversation (the Publisher)

A new module in the Publisher part (`docs/design.md` rule 5). It uses
`publisher.Transport` and `publisher`'s failure types.

```python
# src/pressless/github_signin.py

CLIENT_ID = ""        # the registered app's client id; not a secret
APP_SLUG = ""         # its name in github.com/apps/<slug>

@dataclass(frozen=True)
class DeviceCode:
    device_code: str   # never shown
    user_code: str     # shown: the person types it on GitHub
    address: str       # GitHub's verification_uri
    expires_in: int    # seconds, as GitHub gives it
    interval: int

@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str
    expires_in: int    # the access token's life, in seconds

class Pending(PublishError): ...    # authorization_pending or slow_down
class Expired(PublishError): ...    # expired_token
class Declined(PublishError): ...   # access_denied
class SignedOut(PublishError): ...  # a refresh GitHub refused

@dataclass(frozen=True)
class Installation:
    id: int
    all_repositories: bool            # repository_selection == "all"

def available() -> bool: ...          # CLIENT_ID and APP_SLUG both set
def begin(transport=None) -> DeviceCode: ...
def poll(code: DeviceCode, transport=None) -> Tokens: ...
def refresh(refresh_token: str, transport=None) -> Tokens: ...
def login(token: str, transport=None) -> str: ...
def installation(token: str, login: str, transport=None) -> Installation | None: ...
def create_repository(token: str, name: str, transport=None) -> bool: ...
def include(token: str, installation: Installation, repository: str,
            transport=None) -> None: ...
```

- `begin` POSTs `client_id` to `https://github.com/login/device/code`.
- `poll` POSTs `client_id`, `device_code` and `grant_type`
  `urn:ietf:params:oauth:grant-type:device_code` to
  `https://github.com/login/oauth/access_token`. GitHub's `error` field maps
  as named above; `device_flow_disabled` is a `Refused`.
- `refresh` POSTs `client_id`, `grant_type` `refresh_token` and the refresh
  token to the same address. Any `error` answer is `SignedOut`. GitHub
  returns a new refresh token and the old one stops working.
- Every request to `github.com` sends `Accept: application/json`.
- `login` reads `GET /user`'s `login`.
- `installation` reads `GET /user/installations` and returns the one whose
  `app_slug` is `APP_SLUG` and whose `account.login` is `login`, else
  `None`. An organisation's installation of the app is never it.
- `create_repository` POSTs `{"name": name, "private": false}` to
  `/user/repos` and returns `True`. A 422 is `False`: the name is taken in
  this account.
- `include`, where `installation.all_repositories` is false, reads the
  repository's `id` with `GET /repos/{owner}/{name}` and sends
  `PUT /user/installations/{installation.id}/repositories/{id}`. Otherwise
  it sends nothing.
  Source: https://docs.github.com/en/rest/apps/installations
- **No device code, access token or refresh token reaches a message.** Each
  failure's text has them replaced, as `google_signin._scrub` does for
  Google's.

The app is registered by hand under the maintainer's account: public, device
flow enabled, no webhook, and the repository permissions Contents, Pages and
Administration **Read and write** plus Repository creation, as GitHub's
permission list names it. `docs/working-here.md` gains the steps, as it has
Google's. Until both constants are filled, `available()` is false.
Source: https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps

### 4.2 The pass every GitHub request uses (the Face)

A new Face module, `src/pressless/github_setup.py`, holding the access token
for one launch.

```python
def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None,
             clock: Callable[[], float] = time.time) -> None: ...
def token(folder: Path, store: str, account: str) -> str: ...
def hold(tokens: github_signin.Tokens) -> None: ...   # a sign-in's first pass
```

`token` takes the arguments `credentials.read` takes and replaces that call
wherever a GitHub secret is read: in `publishing`, `undo`, `page_editor` and
`setup`.

1. `secret = credentials.read(store, folder, account)`.
2. A `secret` not starting `ghr_` is a key: return it.
3. A held access token more than 60 seconds from its expiry is returned.
4. Otherwise `github_signin.refresh(secret)`; then `credentials.write` of the
   new refresh token; then the new access token is held and returned. The
   write comes before the return, because the old refresh token has stopped
   working.

Steps 1 to 4 run under one lock held by the module: GitHub's refresh token
works once, so two renewals at once would leave one of them signed out.

`register` runs at launch, as `google_setup.register` does. `token`, `hold`,
the *signin* step and `/setup/github` use its transport and its clock, and
turn each `expires_in` into a time with that clock. Tests pass a recording
transport and a fake clock there.

A `SignedOut` reaches `Face.fail` like any `PublishError`. Its sentence says
GitHub has signed Pressless out, the site has not changed, and to sign in
again in Settings, with a link to `/setup/github`.

### 4.3 The setup wizard with sign-in

Where `github_signin.available()`, PRESS-0212 § 4.4's steps become:

| Step | Fields | What it shows | Its check |
|---|---|---|---|
| *welcome* | none | what the wizard does; that a GitHub account is needed, with the sign-up link | none |
| *signin* | none | how to sign in with a code | the sign-in sequence below |
| *install* | none | how to install the Pressless app, with `https://github.com/apps/<APP_SLUG>/installations/new` | `installation` is not `None`, else a `Hint`; the answers gain `all_repositories` |
| *repository* | `repository` | the naming advice of PRESS-0212 § 3 decision 7, the box filled with `<login>.github.io` | the repository sequence below |
| *pages* | none | as PRESS-0212 | as PRESS-0212, the key in hand from `token`, except that a `Refused` hint says the Pressless app cannot reach this repository and to check its installation on GitHub |
| *site* | as PRESS-0212 | as PRESS-0212 | as PRESS-0212, the key in hand from `token` |

Where it is false, the steps are PRESS-0212's, unchanged.

**signin.** The device code is held by the wizard's owner in memory, never in
the progress file (PRESS-0212 § 4.2).

1. No code held, or the held one past its expiry: `begin`, hold it, and
   return a `Hint` showing `user_code` and a link to `address`, saying to
   type the code there, click Authorize, and press Next.
2. A code held: `poll`. `Pending` is a `Hint` saying GitHub has not heard
   yet, with the same code. `Expired` drops the code and runs step 1.
   `Declined` drops the code and is a `Hint` saying the sign-in was
   cancelled on GitHub.
3. `Tokens`: `credentials.choose()` where the answers hold no `store`, then
   `credentials.write(store, folder, GITHUB_ACCOUNT, tokens.refresh)`. A
   credential failure is a `Stop`, as on PRESS-0212's *key* step. Then
   `github_setup.hold(tokens)`, and the code is dropped.
4. The answers gain `store`, `store_name` and `account`, `login`'s answer.

**repository.** The joined `account/repository` must pass `settings.check`'s
repository rule, or the hint is PRESS-0021's.

1. `create_repository`. `True` goes to step 3.
2. `False`: `publisher.public_repository`, then `publisher.root_entries`
   with no key, as `public_repository` reads (its `token` becomes
   `str | None`). A Public repository whose root answers `()` is taken as this person's own
   new one: a Next after a lost answer finds what the first press made. Any
   other is a `Hint`: a repository by that name already exists, choose
   another name. Nothing is written to it.
3. `include`, with `installation` read again.

The *pages* step then gives an empty repository `.nojekyll` as its first
commit, as PRESS-0212 § 4.5 already does. Where the answers'
`all_repositories` holds, the done page adds how to narrow the app to this
one repository on GitHub. Nothing depends on the person doing it.

### 4.4 Settings, and signing in again

The Settings form (PRESS-0021 § 4.3) is unchanged except for one line above
the key box on a copy whose stored secret starts `ghr_`: Pressless is signed
in to GitHub, typing a key replaces the sign-in, and a link to
`/setup/github`. Its save sequence reads the key with `token`.

`/setup/github`, GET and POST, runs the *signin* step's sequence on its own,
with the saved store. Success replaces the stored secret and the held token,
and shows Settings. It is registered behind the Face's boundary like every
other page.

## 5. Invariants

The pass and Settings tests are in `tests/test_github_setup.py`,
the wizard ones in `tests/test_setup.py`, with the recording Credentials
doubles `tests/test_setup.py` already uses. Secrets are plain words, so the
push gate's secret scanner does not mistake them.

- **INV-1** — A key is handed over as it is, and a refresh token never is.
  `token` returns a stored secret not starting `ghr_` unchanged, with no
  request sent. For one starting `ghr_` it returns the access token, and the
  refresh token never appears in any request's `Authorization` header.
  *Test:* `test_a_key_is_used_and_a_refresh_token_is_not`.
  *Breaks when:* every secret is refreshed, or the stored secret is sent as
  the bearer token.

- **INV-2** — The pass is renewed only when it is nearly spent, and the new
  refresh token is stored before the pass is used. Two `token` calls an hour
  apart send one refresh; one 7 hours 59.5 minutes after the first sends a
  second. The write precedes `token`'s return.
  *Test:* `test_the_pass_is_renewed_when_nearly_spent`, with a fake clock and
  a write double that raises, asserting no token is returned.
  *Breaks when:* every call refreshes, the held token is used past expiry, or
  the new refresh token is not stored.

- **INV-3** — No device code, access token or refresh token reaches a page,
  the log or the progress file. The user code does reach the page.
  *Test:* `test_the_sign_in_secrets_stay_out_of_sight`, walking *signin* and
  a failing refresh, reading every page, the log and `wizards/setup.json`.
  *Breaks when:* a failure's text carries GitHub's answer, or the wizard
  writes the held code into the answers.

- **INV-4** — The *signin* step stores only what GitHub issued, and does not
  advance before. `Pending`, `Expired` and `Declined` leave no stored secret,
  no call to `choose`, and the step unadvanced. `Tokens` stores the refresh
  token once.
  *Test:* `test_signing_in_stores_only_what_github_issued`, answering pending,
  expired, declined, then tokens.
  *Breaks when:* a pending answer stores something, or the step advances on
  it.

- **INV-5** — An expired code is replaced, not polled. A Next after
  the code's expiry sends `begin` and no `poll`.
  *Test:* `test_an_expired_code_is_replaced`, advancing the fake clock past
  the code's life.
  *Breaks when:* the step polls a dead code and shows GitHub's error.

- **INV-6** — A taken name writes nothing to the repository that holds it.
  A 422 over a repository whose root holds files is a `Hint`, and no
  non-GET request names that repository.
  *Test:* `test_a_taken_name_is_left_alone`.
  *Breaks when:* the step adopts any existing repository, or *pages* runs
  over it.

- **INV-7** — A lost answer does not make a second repository. A 422 over a
  Public repository whose root answers `()` advances, and `/user/repos` is
  POSTed once per press.
  *Test:* `test_a_second_press_finds_the_first_repository`.
  *Breaks when:* the 422 is always a `Hint`, so a dropped answer strands the
  person.

- **INV-8** — The new repository is in the installation. With
  `repository_selection` `selected`, `include` sends the PUT; with `all`, it
  sends nothing.
  *Test:* `test_the_new_repository_is_included`, both selections.
  *Breaks when:* the PUT is skipped for `selected`, so the *pages* step meets
  a 404.

- **INV-9** — Setup's GitHub writes with sign-in are `POST /user/repos`, the
  PUT of INV-8 where it applies, and then PRESS-0212 INV-9's two. No request
  is a DELETE.
  *Test:* `test_signed_in_setup_writes_only_what_it_needs`, walking the whole
  wizard against the recording transport and asserting the method and path
  of every non-GET request to `api.github.com`. The sign-in's own POSTs go
  to `github.com`.
  *Breaks when:* a step writes another file, setting or repository.

- **INV-10** — Without a registered app, first run is PRESS-0212's wizard.
  With `CLIENT_ID` empty the step names are `welcome`, `account`,
  `repository`, `key`, `pages`, `site`, and with both constants set they are
  `welcome`, `signin`, `install`, `repository`, `pages`, `site`.
  *Test:* `test_the_steps_follow_the_registration`.
  *Breaks when:* a development copy offers a sign-in GitHub will refuse, or a
  registered one still asks for a key.

- **INV-11** — A lapsed sign-in is told plainly. A refresh GitHub refuses
  makes a publish fail with `SignedOut`'s sentence and a link to
  `/setup/github`, and the site is unchanged: no write request is sent.
  *Test:* `test_a_lapsed_sign_in_says_sign_in_again`.
  *Breaks when:* the failure reads as a refused key, or the publish goes on
  with no token.

- **INV-12** — Signing in again replaces the stored secret and the held
  pass. After `/setup/github` succeeds, the next `token` returns the new
  access token and sends no refresh.
  *Test:* `test_signing_in_again_replaces_the_pass`.
  *Breaks when:* the old held token outlives the new sign-in.

- **INV-13** — The sign-in pages sit behind the Face's boundary. PRESS-0212
  INV-12, carried to `/setup/github`'s POST.
  *Test:* `test_signing_in_again_sits_behind_the_faces_boundary`.
  *Breaks when:* the page is served by its own handler.

## 6. Failure modes

| What fails | What they see | What is kept |
|---|---|---|
| No internet on *signin*, *install* or *repository* | `Face.fail`'s `Unreachable` sentence | the step, unadvanced |
| The person never types the code | the same code, and "GitHub has not heard yet" | the step |
| The code expires (15 minutes) | a new code | the step |
| The person clicks Cancel on GitHub | a hint that the sign-in was cancelled; Next starts again | the step |
| The app is not installed | the install hint and link | the stored refresh token |
| The name is taken by a repository with files | a hint to choose another name | the stored refresh token |
| The create's answer is lost | Next again finds the empty repository and goes on | everything before |
| The new refresh token cannot be stored | the credential failure's sentence; the next renewal signs Pressless out | the site, unchanged |
| Six months unused | `SignedOut`'s sentence and the link to sign in again | the site, unchanged |
| The app is installed on all repositories | nothing; the done page says how to narrow it to this one | everything |

## 7. Tests

The tests of § 5, each written first and seen to fail against today's code:
INV-1, INV-2, INV-11 and INV-12 in `tests/test_github_setup.py`; INV-3,
INV-4, INV-5, INV-6, INV-7, INV-8, INV-9, INV-10 and INV-13 in
`tests/test_setup.py`. `tests/test_github_signin.py`
holds the protocol's own tests: each request's address and fields, and each
`error` answer's type.

**By hand, before building the *install* step's words:** register the app,
then open its install page as a new account with no repositories and record
what GitHub offers under **Repository access**. The step's instructions say
what that run found.

**By hand, before release:** the whole wizard against a new GitHub account,
once on Linux and once on the Windows box, ending with a publish whose page
answers at the address the wizard found. Then revoke Pressless on GitHub,
publish again, and record what is shown. CI cannot reach GitHub.

## 8. Alternatives considered (and rejected)

- **An OAuth app.** Rejected by the user (§ 3 decision 1): its token reaches
  every repository the person has, and never expires.
- **Keep only the hand-made key.** Rejected by the user's request: it is the
  step a stranger is most likely to get wrong.
- **Opt the app out of expiring tokens.** Rejected: one stored token would
  then last until revoked. An expiring pass limits what a copied one is worth,
  for the price of one refresh a working day.
- **Poll GitHub in the background while the person signs in.** Rejected: a
  thread and its cancellation, to save one press of Next.
- **Record the kind of secret in Settings.** Rejected: a settings format
  change for a fact the secret's own prefix carries.
- **Adopt any repository whose name is taken.** Rejected: it could publish
  over a site the person already has. Bringing an existing site in is
  PRESS-0218.

## 9. Out of scope

- Bringing an existing site in, from GitHub or elsewhere — PRESS-0218.
- A repository owned by an organisation rather than the person.
- A Sign out button that revokes the app's token.
- Settings as a dialog, and the sign-in-again page as one — PRESS-0220's
  dialog pattern, when Settings' other dialogs are built.
- Several sites in one Pressless — PRESS-0223.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_github_setup.py::test_a_key_is_used_and_a_refresh_token_is_not` |
| INV-2 | `tests/test_github_setup.py::test_the_pass_is_renewed_when_nearly_spent` |
| INV-3 | `tests/test_setup.py::test_the_sign_in_secrets_stay_out_of_sight` |
| INV-4 | `tests/test_setup.py::test_signing_in_stores_only_what_github_issued` |
| INV-5 | `tests/test_setup.py::test_an_expired_code_is_replaced` |
| INV-6 | `tests/test_setup.py::test_a_taken_name_is_left_alone` |
| INV-7 | `tests/test_setup.py::test_a_second_press_finds_the_first_repository` |
| INV-8 | `tests/test_setup.py::test_the_new_repository_is_included` |
| INV-9 | `tests/test_setup.py::test_signed_in_setup_writes_only_what_it_needs` |
| INV-10 | `tests/test_setup.py::test_the_steps_follow_the_registration` |
| INV-11 | `tests/test_github_setup.py::test_a_lapsed_sign_in_says_sign_in_again` |
| INV-12 | `tests/test_github_setup.py::test_signing_in_again_replaces_the_pass` |
| INV-13 | `tests/test_setup.py::test_signing_in_again_sits_behind_the_faces_boundary` |
| § 4.1 GitHub's real answers to the device flow, refresh and installation requests | **nothing** in CI — the by-hand run of § 7 |
| § 4.3 the instructions match GitHub's pages | **nothing** — read by hand in § 7's run; GitHub changes its pages without notice |

## 11. Cross-doc impact

Each spec edit is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0212-setup-wizard.md` § 3 decision 1 — overturned for a
  copy with a registered app. § 4.4 — the steps where `available()` holds.
- `docs/specs/PRESS-0002-credentials.md` — the GitHub secret may be a
  GitHub App refresh token, renewed on each refresh.
- `docs/specs/PRESS-0021-setup.md` § 4.3 — the signed-in line above the key
  box, and `/setup/github`. § 4.6 step 1 — the key is read with
  `github_setup.token`.
- `docs/design.md` § The parts — the Publisher row: it also signs in to
  GitHub, makes the repository and adds it to the installation; the
  Credentials row: the GitHub secret is a publishing key or a sign-in.
- `docs/working-here.md` — a section on registering the GitHub App.
- `README.md` § Getting started — the person signs in to GitHub rather than
  making a key.
- `CHANGELOG.md` — one line under Added.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0231-github-sign-in-loop-log.md`.
