<!-- ants-spec-format: 1 -->
# PRESS-0262 — Usage reports, sent only when the user says yes

**Status:** accepted (2026-10-13). Gated for one round, the user's budget for a new spec; every verified finding fixed.
**Kind:** feature.
**Source:** ROADMAP PRESS-0262 (the user 2026-10-13: whether the app could
learn, whether usage reports would help, and how to read them).

**Amends:** PRESS-0023 INV-8, which names the modules that may reach the
network (§ 11).

Layman: Pressless asks once whether it may send anonymous reports of
which screens are used, where setup stops and what goes wrong. Nothing
is sent until they say yes, they can see every report sent, and their
writing, names, addresses and files are never in one.

## 1. Goal

After this ships, a user who says yes sends small anonymous reports to a
Google Analytics property kept for Pressless alone. A user who says no,
or never answers, sends nothing, and a Pressless built without the
property's key never asks. A session can turn the reports into a short
plain-language summary and roadmap items, by a recorded procedure.

## 2. Problem

1. **We cannot see where people get stuck.** The only channel back is
   `report.py`'s Report a problem page, which a user fills in by hand.
   A setup that stops halfway, or a press that fails on Windows, is
   invisible unless they write in.
2. **Pressless has promised to send nothing it is not asked to.**
   `report.py`'s module comment says nothing but the filled-in form is
   sent. Reports change that, so the asking is the whole contract.
3. **Only three modules may reach the network** (PRESS-0023 INV-8,
   `tests/test_network_confined.py`). A fourth needs that rule changed.
4. **Reports nobody reads change nothing.** Their shape has to be fixed
   so a report procedure can rely on it.

## 3. Scope decisions (agreed with the user)

1. **Always opt-in, never on by default.** The user, 2026-10-13. It may
   be switched off for everyone in a later release.
2. **Asked in setup, and once for current users.** The user,
   2026-10-13. Leaving the question unanswered counts as no.
3. **Screens opened, setup steps reached, each press and how it ended,
   and an error's kind and screen, with the version and system.** The
   user, 2026-10-13. Never writing, names, addresses or paths.
4. **Sent to a separate Google Analytics property.** The user,
   2026-10-13, not the site's own.
5. **The user can read every report sent.** The user, 2026-10-13.
6. **(decided here) The switch and the list live on a Usage reports
   screen** linked from every screen's top bar. Pressless has no
   Settings screen; its settings file is changed by setup alone.
7. **(decided here) The answer is kept in its own file, not in
   Settings.** Setup asks before Settings is saved, and a current
   user's answer must not rewrite a settings file it has no part in.
8. **(decided here) The key is written in when a release is built and
   never committed**, as the Google sign-in's secret is (PRESS-0122
   § 4.7). The repository is public.
9. **(decided here) Reports go to Google's European endpoint,**
   `region1.google-analytics.com`.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/usage.py -- the fourth module that may reach the network

FILE_NAME = "usage.json"         # in Pressless's own folder
SENT_NAME = "usage-sent.json"    # the last reports sent, newest last
KEPT = 50                        # how many SENT_NAME holds
ADDRESS = "/usage"
ENDPOINT = "https://region1.google-analytics.com/mp/collect"

EVENTS: Mapping[str, tuple[str, ...]] = {
    "screen":      ("screen",),
    "wizard_step": ("wizard", "step"),
    "wizard_done": ("wizard",),
    "press":       ("kind", "ended"),
    "failure":     ("error", "screen", "publishing"),
}
COMMON = ("app_version", "system", "session_id", "engagement_time_msec")

def can_send() -> bool: ...                 # this build carries the key
def answer(folder: Path) -> bool | None: ...  # None: never asked
def set_answer(folder: Path, yes: bool) -> None: ...
def system() -> str: ...                    # moved here from report._system
def report(name: str, **params: str) -> None: ...
def register(face: Face, folder: Path, *,
             transport: insights.Transport | None = None) -> None: ...
```

`register` keeps `folder`, Pressless's own folder (the Face's), and the
transport, which defaults to one built as § 4.5 says; `report` uses
both, and does nothing before `register` has run. Tests hand in a
double, as `insights.read` takes one as `client`. `usage` imports the Face for
typing only, so the Face may call `report`; `report.py` calls
`usage.system()`.

```python
# src/pressless/_usage_key.py -- written by scripts/write_usage_key.py,
# named by .gitignore, never committed
MEASUREMENT_ID = "G-..."
API_SECRET = "..."
```

`can_send()` is true where `_usage_key` imports and both values are
non-empty. `scripts/write_usage_key.py` takes them from
`PRESSLESS_USAGE_MEASUREMENT_ID` and `PRESSLESS_USAGE_API_SECRET`, or
asks without echoing, and never prints them, as
`scripts/write_google_secret.py` does.

### 4.2 The answer

`usage.json` holds `{"version": 1, "yes": <bool>, "client": <str|null>}`.
`answer` returns `None` where the file is absent and `False` where it is
unreadable or malformed. `set_answer(folder, True)` writes `yes` and a
new `client`, `uuid.uuid4().hex`; `set_answer(folder, False)` writes
`yes: false`, `client: null`, and deletes `usage-sent.json`. Both write
through `safe_write`, as Settings does.

**A report is sent only where `can_send()` and `answer(folder)` are both
true.** Every other case returns from `report`, once § 4.4's check of
the call has passed, before anything is built.

### 4.3 Asking

- **Setup** gains a step `reports`, straight after `welcome`, in both
  of `setup.py`'s step lists, where `can_send()` holds. Every step
  before it is unanswered, so § 4.7's funnel starts at `reports`. It shows the
  explanation (§ 4.6) and one checkbox, unticked. Its check calls
  `set_answer` with the box's state.
- **A current user** — Settings loads, `can_send()` holds and
  `answer(folder)` is `None` —
  sees the same explanation above the list at `/`, with **Yes, send
  them** and **No thanks**, through `face.add_to_list(..., above=True)`.
  Showing it calls `set_answer(folder, False)` first, so leaving it
  unanswered is no. **Yes** posts to `/usage/yes`.
- **The Usage reports screen** at `/usage` says whether reports are on,
  has one button to turn them on or off (`/usage/yes`, `/usage/no`),
  and lists the contents of `usage-sent.json`, newest first, each as the
  JSON sent. Every screen's top bar links to it beside Report a problem.

### 4.4 What is sent

Each event is one `POST` to `ENDPOINT` with
`?measurement_id=<id>&api_secret=<secret>` and a JSON body
`{"client_id": <client>, "events": [{"name": <name>, "params": {...}}]}`.
Callers pass only the event's names in `EVENTS`; `report` adds
`COMMON`, so `params` holds exactly both. **`report` checks the call
first, whatever the answer**: it raises `ValueError` for a name not in
`EVENTS` or a missing or extra parameter, so a bad call fails in every
test. It cuts any value longer than 100 characters to its first 100.

| Event | Sent from | Values |
|---|---|---|
| `screen` | the Face's `_answer`, for a `GET` whose page returns HTML rather than a `Reply` | `screen`: the registered path, never the query |
| `wizard_step` | `wizard.Wizard` when it shows a step | `wizard`: the wizard's name; `step`: the step's name |
| `wizard_done` | `wizard.Wizard` when a step's check returns `Done` | `wizard`: the wizard's name |
| `press` | `pressing.run`, once the record ends | `kind`: the press's kind; `ended`: `done` where the outcome's words are `script.press.published`'s or `script.press.undone`'s, else `failed` |
| `failure` | the Face's `_answer`, in its last-resort catch | `error`: `type(exc).__name__`; `screen`: the registered path; `publishing`: `yes` or `no` |

`app_version` is `pressless.__version__`. `system` is `system()`.
`session_id` is one random integer per start of Pressless, and
`engagement_time_msec` the integer `1`, which Google needs to count a
user; both are sent as JSON numbers, every other value as a string.

**Every value in `params` is one Pressless chose** — a path it
registered, a name in its code, a class name or one of the fixed words
above. None but `system`, which reads the operating system's name, is
read from a request's query or body, a file, Settings or the Store.

### 4.5 Sending

`report` appends the body to `usage-sent.json`, keeping the last `KEPT`,
and sends it on a daemon thread through an opener built as
`insights._Urllib` builds its own: certifi's certificates and a timeout
of 5 seconds. The thread ignores the answer, and any failure is one
`Log.note` naming the event and the failure's type. **Nothing waits for
it**: no page, press or exit is held by a report.

### 4.6 The words

The explanation, in the words table under `usage.`:

> *Pressless can send anonymous reports of which screens you use, where
> setup stops and what goes wrong, with its version and your system. They
> help us fix what gets in people's way. They never hold your writing,
> your pages' names, your site's address or your files. You can see
> every report sent, and turn them off at any time, under Usage reports.*

### 4.7 Reading the reports

`docs/usage-reports.md`, new, holds the procedure a session follows to
turn the reports into decisions, through the Google Analytics connector
(`run_report`, `run_funnel_report`) against the Pressless property:

1. **Where setup stops**: a funnel over `wizard_step` with `wizard`
   `setup`, in step order, split by `system`.
2. **What goes wrong**: `failure` counted by `error`, `screen`,
   `app_version` and `system`.
3. **How presses end**: `press` counted by `kind` and `ended`, by
   `app_version`.
4. **What is used**: `screen` counted by `screen`.

It says how to write the summary, and that an error or a stopping step
seen in more than one report is filed with `roadmap_log`, citing the
query that found it. Every parameter in `EVENTS` and `COMMON` but
`engagement_time_msec` is registered in the property as an event-scoped
custom dimension; the document lists them.

### 4.8 What this item never does

- It sends nothing for a user who has not said yes.
- It sends no value § 4.4 does not name.
- It changes nothing in Settings, the Store or the site.

## 5. Invariants

- **INV-1** — No request is opened unless `can_send()` and
  `answer(folder)` are both true.
  *Test:* `tests/test_usage.py::test_nothing_is_sent_without_a_yes`,
  with a transport double counting requests, over: no file, `yes:
  false`, a malformed file, no key, and a yes — only the last sends.
  *Breaks when:* `report` builds or queues before checking the answer.

- **INV-2** — Showing a current user the question records no before
  any answer is given.
  *Test:* `tests/test_usage.py::test_an_unanswered_question_is_no`:
  `GET /` with no `usage.json`, then `answer(folder)` is `False`.
  *Breaks when:* the file is written only on a button press.

- **INV-3** — Every event sent carries exactly its names in `EVENTS`
  plus `COMMON`, and `report` refuses any other.
  *Test:* `tests/test_usage.py::test_events_carry_their_fixed_fields`:
  each event's body is compared key for key; an extra parameter and an
  unknown name each raise `ValueError`.
  *Breaks when:* a caller passes a new parameter and it is sent.

- **INV-4** — No value in an event's `params` but `system` is taken
  from a request's query or body, a file, Settings or the Store.
  *Test:* `tests/test_usage.py::test_no_users_words_are_sent`: a session
  through setup, the page editor and a failing press, with a site name,
  page name, repository and folder of plain marker words; no sent body
  holds any marker.
  *Breaks when:* `screen` takes `self.path`, or `failure`'s `error`
  takes the exception's message.

- **INV-5** — A report never delays a reply.
  *Test:* `tests/test_usage.py::test_a_slow_endpoint_holds_nothing`: a
  transport that sleeps past the timeout; the page's reply returns
  before it does.
  *Breaks when:* `report` sends on the calling thread.

- **INV-6** — Saying no deletes the client id and the sent list.
  *Test:* `tests/test_usage.py::test_no_forgets_the_client`.
  *Breaks when:* `set_answer(False)` keeps `client` or `usage-sent.json`.

- **INV-7** — `usage-sent.json` holds exactly the bodies sent, the last
  `KEPT` of them.
  *Test:* `tests/test_usage.py::test_the_list_is_what_was_sent`: the
  transport's recorded bodies against the file, past `KEPT` sends.
  *Breaks when:* the list is written from anything but the body sent.

- **INV-8** — The key is never in the repository: `.gitignore` names
  `_usage_key.py`.
  *Test:* `git check-ignore src/pressless/_usage_key.py` →
  `src/pressless/_usage_key.py`.
  *Breaks when:* `.gitignore` loses the line.

- **INV-9** — Only `publisher.py`, `insights.py`, `updater.py` and
  `usage.py` import a network module.
  *Test:* `tests/test_network_confined.py::test_only_four_modules_reach_the_network`.
  *Breaks when:* a fifth module opens a socket. This replaces
  PRESS-0023 INV-8.

## 6. Failure modes

| What happens | What the user sees |
|---|---|
| No internet, or Google does not answer | Nothing; one log line per report |
| `usage.json` unreadable | Treated as no; the question is not shown again |
| A build without the key | No question, no switch: the screen says reports are not available in this copy |
| Google changes the endpoint | Reports stop arriving; we see it as silence in the property, and nothing breaks in Pressless |
| Someone sends fake reports with the public key | Figures are a guide, never exact; § 4.7's procedure says so |

## 7. Tests

| Test | Locks |
|---|---|
| `tests/test_usage.py` | INV-1, INV-2, INV-3, INV-4, INV-5, INV-6, INV-7 |
| `git check-ignore` in INV-8 | INV-8 |
| `tests/test_network_confined.py` | INV-9 |
| `tests/test_network_timeouts.py` | its own rule, over `usage.py` |

Each test is seen failing before the code it locks exists.

## 8. Alternatives considered (and rejected)

- **Firebase.** Built for phone and web apps; a desktop app's events
  would need charts we build ourselves (the user, 2026-10-13).
- **The site's own Analytics property.** It would mix a reader's visit
  with a writer's use of Pressless.
- **On until switched off.** Ruled out by the user (§ 3 decision 1).
- **The answer in Settings.** § 3 decision 7.
- **Sending the error's message.** Messages hold paths and names
  (`docs/design.md` § Errors); the class name and screen are enough to
  find the code.
- **Batching reports and sending at exit.** A crash or a closed window
  loses the batch, and the batch is where the crash report is.

## 9. Out of scope

- The app remembering choices on the computer — PRESS-0263.
- Timings — not chosen by the user (§ 3 decision 3).
- A weekly automatic report — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | `tests/test_usage.py::test_nothing_is_sent_without_a_yes` |
| INV-2 | `tests/test_usage.py::test_an_unanswered_question_is_no` |
| INV-3 | `tests/test_usage.py::test_events_carry_their_fixed_fields` |
| INV-4 | `tests/test_usage.py::test_no_users_words_are_sent` |
| INV-5 | `tests/test_usage.py::test_a_slow_endpoint_holds_nothing` |
| INV-6 | `tests/test_usage.py::test_no_forgets_the_client` |
| INV-7 | `tests/test_usage.py::test_the_list_is_what_was_sent` |
| INV-8 | `git check-ignore` |
| INV-9 | `tests/test_network_confined.py::test_only_four_modules_reach_the_network` |
| § 4.7's procedure | **nothing** — a document a session follows; read when it is run |

## 11. Cross-doc impact

- PRESS-0023 INV-8 and its § 10 row name four modules, and say
  PRESS-0262 INV-9 replaced them.
- `docs/design.md` § The parts gains a **Usage** row: sending the
  reports the user agreed to, and knowing nothing of the site.
- `docs/usage-reports.md`, new (§ 4.7).
- `docs/working-here.md` gains *Registering the usage-report property*:
  making the property and its web stream, the API secret, the custom
  dimensions, and the two release variables.
- `report.py`'s module comment, and `README.md`, say that usage reports
  are a separate, opt-in channel.
- `CHANGELOG.md`: one entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0262-usage-reports-loop-log.md`.

## 13. Resource cost

No new dependency. One thread per report, ending within its timeout.
`usage-sent.json` is capped at `KEPT` bodies.
