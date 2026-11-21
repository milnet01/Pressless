<!-- ants-spec-format: 1 -->
# PRESS-0436 — One button sends the log to the developer, privately

**Status:** accepted (2026-11-21). Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0436 (user, 2026-11-21: never ask people for log
files; one button, private, through a relay that holds the key).

Layman: when something goes wrong, press Send my log and Pressless sends its
log privately to the developer, and gives you a short reference to quote.

## 1. Goal

A failure page and Report a problem carry a **Send my log** button. It
opens a box saying in plain words what goes and where. **Send** posts
`pressless.log` and `pressless.log.1` to a relay. The relay files them as an
issue in the private repository `milnet01/pressless-logs` and answers a
short reference, which the box shows. No key that can read or write that
repository is in the app.

## 2. Problem

1. **Getting a log needs computer skills.** A failure page names the log and
   its folder (`face.render_failure`, `failure.log`) and leaves the user to
   find it, attach it and send it.
2. **Report a problem sends no log.** `report.issue_address` opens a public
   issue, which must not hold a log (§ 3 decision 2).
3. **The app cannot hold a GitHub key.** It is public; anyone could take the
   key out and read every log sent.

## 3. Scope decisions (agreed with the user)

1. **One button on failure pages and Report a problem; it shows what goes
   and where, then sends both log files, then shows a reference.** User,
   2026-11-21 (PRESS-0436's body).
2. **The destination is an issue in a private GitHub repository,
   `milnet01/pressless-logs`.** User, 2026-11-21; repository created that day.
3. **The relay is a Cloudflare Worker.** User, 2026-11-21.
4. **The relay reaches GitHub as a GitHub App installed on that repository
   alone.** User, 2026-11-21: its key never runs out.
5. **Nothing is sent without a press of Send in the box.** *(decided here)*
   The box is the consent; there is no setting that sends on its own.
6. **The relay takes no key from the app.** *(decided here)* A key shipped
   in a public app is no key. Abuse is held off by size and rate limits
   (§ 4.3).

## 4. Design

### 4.1 The button and the box

`render_failure` and `report._page` gain a button `data-action="send-log"`.
Its script opens a `<dialog class="message">` holding `sendlog.box`'s words:

- what goes: the two log files, the Pressless version and the system name;
- what they hold: what Pressless did and what went wrong, with the names of
  the site, its pages and its files; written to leave out keys, passwords,
  account names and full paths (PRESS-0003 § 10);
- where: privately to the developer, through Cloudflare and GitHub;
- **Send** and **Not now**.

**Send** posts `/log/send` with no body. While it runs the PRESS-0435 note
shows. The box then shows `sendlog.sent` with the reference, or the failure
fragment. **Not now** closes the box; nothing is sent.

### 4.2 `src/pressless/sendlog.py`

```python
RELAY = "https://pressless-logs.<account>.workers.dev/log"  # public, not a secret
LARGEST = 2 * log.MAX_BYTES + 65_536

def send(folder: Path, client: https.Client | None = None) -> str:
    """Post both logs; the reference the relay answers. Raises
    LogNotSent, a PublishError subclass with a Face sentence."""

def register(face: Face) -> None:   # POST /log/send
```

The request: `POST RELAY`, `Content-Type: application/json`, body

```json
{"version": "1.1.1", "system": "Linux", "log": "<text>", "old": "<text>"}
```

`log` and `old` are each file read as UTF-8 with `errors="replace"`, "" where
absent. `system` is `usage.system()`, cut to 128 characters. A body over `LARGEST` sends the newest
part of each file that fits. The answer `200 {"reference": "K7Q2MX"}` gives
the reference; any other answer, or none, raises `LogNotSent`. Its words
say the log was not sent and to try again later. The press is logged with
the reference and never the log text.

### 4.3 The relay — `relay/`

`relay/src/index.js` and `relay/wrangler.jsonc`, deployed as the Worker
`pressless-logs`. Secrets, set by `wrangler secret put` and never in the
repository: `APP_KEY` (the App's private key as PKCS#8 PEM; GitHub issues
PKCS#1, which Web Crypto refuses). Plain variables:
`APP_ID`, `INSTALLATION_ID`, `REPOSITORY`.

`POST /log` only; anything else answers 404. In order:

1. **Rate limit**: Cloudflare's rate-limiting binding, keyed by the
   `CF-Connecting-IP` header, one send per 60 seconds. The binding's period
   is 10 or 60 seconds, and its counts are approximate and per Cloudflare
   location. Over → 429.
2. **Size**: a body over 2.2 MiB → 413, read no further.
3. **Shape**: JSON with string `version` (at most 32 characters, digits,
   dots, letters and `-`), string `system` (at most 128), strings `log` and
   `old` → else 400.
4. **Token**: a JWT signed RS256 with `APP_KEY` (Web Crypto), exchanged at
   `POST /app/installations/{INSTALLATION_ID}/access_tokens` for a token
   limited to `contents: write, issues: write`.
5. **Files**: the reference is six characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`.
   `PUT /repos/{REPOSITORY}/contents/logs/{reference}/pressless.log` and
   `.../pressless.log.1`, each base64.
6. **Issue**: `POST /repos/{REPOSITORY}/issues`, title
   `Log {reference}: Pressless {version} on {system}`, body naming both
   files' paths and the last 100 lines of `log`, cut to their last 60,000
   characters, in a fenced block.
7. Answer `200 {"reference"}`. A GitHub failure at 4 to 6 → 502, logging
   the status and never the body.

### 4.4 Setting the relay up once

`relay/README.md` holds the steps; `scripts/relay-setup.py` does what a
script can:

1. The user makes a free Cloudflare account and runs `npx wrangler login`.
2. The script serves a page on `127.0.0.1` posting a GitHub App manifest
   (name, no webhook, `contents: write`, `issues: write`, redirect back to
   that page). The user presses **Create** on GitHub.
3. The script exchanges the code (`POST /app-manifests/{code}/conversions`),
   writes the key to `~/.config/pressless/log-relay-app.pem` (mode 600) and
   never prints it.
4. The user installs the App on `milnet01/pressless-logs` alone.
5. The script reads the installation id, sets the variables, converts the
   key to PKCS#8 (`openssl pkcs8 -topk8 -nocrypt`), pipes it into
   `wrangler secret put APP_KEY`, deploys, and sends a test log whose
   issue it then closes. It prints the Worker's address, which is
   committed as `sendlog.RELAY`.

## 5. Invariants

- **INV-1** — `POST /log/send` sends nothing until it is called; no other
  route, timer or start of Pressless reaches `sendlog.send`.
  *Test:* `tests/test_sendlog.py::test_only_the_send_route_sends`.
  *Breaks when:* any caller besides the route calls `send`.
- **INV-2** — The body `send` posts holds exactly the keys `version`,
  `system`, `log`, `old`, with the two files' text and nothing added: no
  site address, settings or folder path beyond what the files hold.
  *Test:* `tests/test_sendlog.py::test_the_body_is_the_logs_and_nothing_else`.
  *Breaks when:* a key is added, or the folder's path is put in.
- **INV-3** — A log over the limit sends its newest part, and the body is
  never over `LARGEST` bytes.
  *Test:* `tests/test_sendlog.py::test_a_large_log_sends_its_newest_part`.
  *Breaks when:* the oldest part is kept, or the cut is by characters, not
  bytes.
- **INV-4** — Any answer but `200` with a reference, and no answer, raise
  `LogNotSent`, and the box shows the failure fragment saying the log
  was not sent.
  *Test:* `tests/test_sendlog.py::test_a_refused_send_says_so`.
  *Breaks when:* a 429 or 502 reads as sent.
- **INV-5** — The log never records the log text it sent.
  *Test:* `tests/test_sendlog.py::test_the_send_is_logged_without_the_text`.
  *Breaks when:* the note logs the body.
- **INV-6** — The relay refuses a body over the size limit, a wrong shape
  and a method or path other than `POST /log`, before it asks GitHub for a
  token.
  *Test:* `node --test relay/test` → every test passes.
  *Breaks when:* a check moves after step 4.
- **INV-7** — No file in this repository holds the App's key, and the app
  holds no credential the relay accepts.
  *Test:* the machine-wide pre-push hook's `gitleaks` scan refuses a
  commit holding a private key. The leak sweep in `scripts/local-ci.sh`
  matches no key.
  *Breaks when:* the key file lands in the tree.
- **INV-8** — The box appears before anything is sent, and Not now sends
  nothing.
  *Test:* `scripts/by-hand-browser-checks.py`'s `send_log` rows, by hand.
  *Breaks when:* Send my log posts at once.

## 6. Failure modes

- **No network, relay down, or over the rate limit.** `LogNotSent`; the box
  says try again later. Nothing is queued.
- **The relay's GitHub access lapses** (App removed). Every send answers
  502; `LogNotSent` as above. The setup script run again restores it.
- **Someone floods the relay.** About one per address per minute; GitHub's
  own limits behind that. The worst case is junk issues in a private repository.
- **The log files are unreadable or absent.** Sent as "" each; the issue
  still records version and system.

## 7. Tests

`tests/test_sendlog.py`, new, in CI: INV-1 to INV-5, through the Face's own
server with a recording `https.Client` double. `relay/test/index.test.js`,
`node --test`, with GitHub faked by a replaced `fetch`: INV-6.
`local-ci.sh` runs it where `node` is on the path. INV-7 is the pre-push hook's `gitleaks` scan.
INV-8 is a browser row. Each test is seen to fail before its code exists.

## 8. Alternatives considered (and rejected)

- **A key in the app.** Anyone could read every log (§ 2 item 3).
- **A personal access token in the relay.** It runs out; the user chose the
  App (§ 3 decision 4).
- **The log in the issue body alone.** An issue body holds at most 65,536
  characters; a log is up to 1 MiB.
- **A public issue with the log attached.** Logs name the user's pages and
  files.

## 9. Out of scope

- Sending a log from the tray menu — deferred; not yet queued.
- Deleting old logs from the repository — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_sendlog.py::test_only_the_send_route_sends` |
| INV-2 | `tests/test_sendlog.py::test_the_body_is_the_logs_and_nothing_else` |
| INV-3 | `tests/test_sendlog.py::test_a_large_log_sends_its_newest_part` |
| INV-4 | `tests/test_sendlog.py::test_a_refused_send_says_so` |
| INV-5 | `tests/test_sendlog.py::test_the_send_is_logged_without_the_text` |
| INV-6 | `relay/test/index.test.js`, where `node` is present |
| INV-7 | `gitleaks` in the machine-wide pre-push hook; nothing in CI |
| INV-8 | **Partial:** `scripts/by-hand-browser-checks.py`, by hand; nothing in CI |
| § 4.3 step 1's rate limit | **nothing** — Cloudflare's binding; checked once after deploy |
| § 4.3 steps 5 and 6 against real GitHub | **nothing** in CI — the setup script's test send |

## 11. Cross-doc impact

- The Hub's privacy policy: what Send my log sends, to whom, and how long
  it is kept. Sent to the `ants-projects-hub-website` session with the
  release.
- `report.py`'s docstring: it no longer says no log is ever sent.
- CHANGELOG, under the release.
- `docs/working-here.md`: a section on the log relay.
- Words in all five languages.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0436-send-my-log-loop-log.md`.
