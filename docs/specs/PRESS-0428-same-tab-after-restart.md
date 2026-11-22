<!-- ants-spec-format: 1 -->
# PRESS-0428 — Come back in the same tab after an update or a restart

**Status:** spec draft (2026-11-22).
**Kind:** ux.
**Source:** ROADMAP PRESS-0428 (the user, 2026-11-21, during the real 1.0.2
to 1.1.0 update on Linux).

**Layman:** After Pressless updates or restarts, the browser tab you were
using carries on working, instead of Pressless opening a new one.

## 1. Goal

After a Restart (Settings, the tray, opening another site) or an Update
now, every Pressless tab still open keeps working against the new Face, and
the tab that asked goes on to the home page by itself. A new tab opens only
where no open tab comes back.

## 2. Problem

Each Face makes its own secret, session and port (`face.Face.__init__`),
and the cookie's name carries the port, so a tab is tied to one Face.

1. A restart serves a new Face on a port the system chooses
   (`__main__._serve_once` calls `face.serve` with port 0 unless
   `PRESSLESS_PORT` names one). Every open tab then points at a dead
   address, and the launcher opens a fresh tab (PRESS-0013 § 4.5 step 6).
2. A Linux Update now replaces the process (`installer.reopen_linux`);
   a Windows one starts a new process from a helper
   (`installer.apply_windows`). Either way the new process starts as a
   double-click does: new port, new session, new tab (PRESS-0023 § 4.9
   step 5).
3. The pages that ask for a restart say so: `restarting.going` tells him
   to close the tab, and `restarting.ask` warns that every tab stops
   working.

## 3. Scope decisions (agreed with the user)

1. **Come back in the same tab** — the user, 2026-11-21.
2. **Design, one review, then build** — the user, 2026-11-22.
3. **A fresh start is unchanged** (decided here). A double-click after a
   stop still makes a new port, session and tab. Only a restart or an
   update hands over, because only then is an open tab known to exist.
4. **Only the pages that asked move on** (decided here). The restart,
   site-switch and update pages go to `/` once the new Face answers. Any
   other open page stays as it is, and its next click reaches the new
   Face. Reloading it could lose words typed in a box that does not save
   by itself.

## 4. Design

### 4.1 The hand-over

A hand-over is the previous Face's port and session:

```python
@dataclass(frozen=True)
class HandOver:          # face.py
    port: int
    session: str

Face.hand_over(self) -> HandOver
serve(folder, port=0, *, site=None, session=None) -> Face
```

`serve` with `session` uses it as the Face's session instead of making
one. The one-use secret is always new, and never equal to the session
(§ 4.5 of PRESS-0011 already holds that for a made session).

**Which port and session the next Face takes:**

| `PRESSLESS_PORT` | Hand-over | The next Face |
|---|---|---|
| unset | none | system port, new session (today) |
| unset | port P | binds P with the handed session; P held → system port, **new** session |
| names Q | none | Q, new session; Q held → `PortHeld` (PRESS-0431) |
| names Q | port Q | Q with the handed session; Q held → `PortHeld` |
| names Q | port P ≠ Q | Q, new session |

A session is never carried to another port: a different port is a
different cookie name, so no tab could present it there.

### 4.2 Within one process

`__main__._serve_held` keeps the last Face's `hand_over()` and gives it to
the next `_serve_once`. This covers Settings' Restart, the tray's Restart
and opening another site (PRESS-0223 § 4.4).

### 4.3 Across an update

The hand-over travels in one environment variable, never on a command
line:

```
PRESSLESS_RESUME=<port>:<session>
```

- **Linux:** `_serve` passes the last Face's hand-over to
  `installer.reopen_linux(appimage, folder, resume)`, which puts it into
  `_helper_environment()`'s result before the `execve`. The arguments stay
  `[appimage]`.
- **Windows:** `updating._update_now` passes `face.hand_over()` to
  `installer.apply_windows(program, staged, folder, resume)`, which puts it
  into the helper's environment. The helper starts the batch file, which
  inherits it. The helper's arguments are unchanged.
- **The new process** reads `PRESSLESS_RESUME` at the top of
  `__main__.main` and deletes it from `os.environ` before anything starts a
  program, so no browser, opener or helper inherits it. A value that is
  not `<1–65535>:<a token_urlsafe string>` is ignored.

A session in the environment is readable by his own account, which can
already read the browser's cookies, and not by another account. That is
why the command line, which other accounts can read, never carries it.

### 4.4 Telling that a tab came back

Every Face page's script (`face._SCRIPT`) asks `GET /alive` every two
seconds. The route is one of the Face's own (`_OWN`), so it needs the
session cookie, and answers:

```json
{"face": "<this Face's id: 16 hex characters, made at start, not a secret>"}
```

The Face sets `Face.returned` (a `threading.Event`) on the first request
the cookie admits.

After serving a Face that took a hand-over, `_serve_once` waits up to
`RETURN_SECONDS = 6` for `returned`. Set: no tab opens and the console
prints `main.running` alone. Not set: the launcher opens `served.url` as
today. The session is the handed one, so that new tab and any late old
tab both work. A Face with no hand-over opens its tab at once, as today.

### 4.5 The pages that asked

The three pages answering a restart — `restarting`'s `POST /restart`,
`sites_screen._going` and `updating._update_now`'s answer — carry
`<p data-after-restart="/">` in their reply. When `/alive` answers with a
`face` id other than the one the page first saw, a page holding that
element calls `location.replace("/")`. A page that never saw an answer
(the Face stopped before its first ask) treats the first answer after a
failed ask as the new Face.

Words change to match:

- `restarting.ask`: open tabs carry on once Pressless is back; anything
  typed and not saved in another tab is still lost.
- `restarting.going` and `updating.installing`: this tab carries on by
  itself once Pressless is back; if a new tab opens instead, use that.

## 5. Invariants

- **INV-1** — A restart within one process serves the same port and
  accepts the old session cookie. *Test:*
  `tests/test_main.py::test_a_restart_keeps_the_port_and_session`.
  *Breaks when:* `_serve_once` is given no hand-over, or `serve` ignores
  `session`.
- **INV-2** — A handed-over port that is held gives a system port and a
  new session; a held `PRESSLESS_PORT` still raises `PortHeld`. *Test:*
  `tests/test_main.py::test_a_held_handed_port_starts_afresh`.
  *Breaks when:* the session is carried to another port, or the fallback
  raises.
- **INV-3** — `PRESSLESS_RESUME` is gone from `os.environ` before
  `_serve` runs, and a malformed value starts afresh. *Test:*
  `tests/test_main.py::test_the_resume_variable_is_read_once_and_removed`.
  *Breaks when:* the variable is read and left in place, so a browser
  started later inherits the session.
- **INV-4** — The hand-over reaches the new process only through its
  environment: `reopen_linux`'s `execve` arguments are `[appimage]`, and
  `apply_windows`'s helper arguments name no session. *Test:*
  `tests/test_installer.py::test_the_hand_over_travels_in_the_environment`.
  *Breaks when:* the session is added to an argument list.
- **INV-5** — After a hand-over, a request bearing the session within
  `RETURN_SECONDS` means no tab opens; none means `served.url` opens.
  *Test:* `tests/test_main.py::test_a_returning_tab_means_no_new_tab`.
  *Breaks when:* the launcher opens a tab regardless, or never opens one.
- **INV-6** — A Face's link is always new and one-use, a handed session
  included. *Test:* `tests/test_face.py::test_a_handed_session_keeps_the_link_one_use`.
  *Breaks when:* `serve(session=s)` derives the secret from `s`, or lets
  the link be followed twice.
- **INV-7** — `GET /alive` without the session cookie is refused 403.
  *Test:* `tests/test_face.py::test_alive_needs_the_session`.
  *Breaks when:* `/alive` is registered as a return page or a door.
- **INV-8** — In a real browser, the restart page goes to `/` by itself
  after Restart, and no second tab opens. *Test:* a row in
  `scripts/by-hand-browser-checks.py`.
  *Breaks when:* the page script never compares `face` ids, or the
  launcher opens a tab before waiting.

## 6. Failure modes

| What happens | What he sees |
|---|---|
| The old tab was closed | After `RETURN_SECONDS`, a new tab opens, as today |
| The tab is hidden long enough for the browser to slow its timers | It may not ask within `RETURN_SECONDS`; a new tab opens, and the old one also works when it asks |
| The handed port is taken in the gap | A system port and a new session; a new tab opens; the old tab cannot come back, and its page says to use a new tab |
| The update's new program cannot start | Nothing answers; the page keeps asking, and its words already say what to do if no tab comes back. The console prints `updating.not_reopened` (Linux) |
| An update to a version without this feature | It ignores `PRESSLESS_RESUME`, leaves it in its environment, and opens a new tab. The session it would leak is not that version's session, so it admits nothing |
| The first update from 1.1.1 or earlier | The old version sets no `PRESSLESS_RESUME`; a new tab opens |
| His cookies were cleared | `/alive` is refused; no tab returns; a new tab opens after `RETURN_SECONDS` |
| Pressless is stopped, not restarted | Open pages keep asking `/alive` and fail quietly. A later double-click makes a new session, which those tabs cannot present |

Timers: Chrome slows chained timers in a page hidden for five minutes to
one wake-up a minute. Source:
https://developer.chrome.com/blog/timer-throttling-in-chrome-88/

## 7. Tests

Each test in § 5 is written first and seen to fail against today's code.
INV-1 to INV-5 drive `__main__` with the `_Opened` stand-in in
`tests/test_main.py`, as the PRESS-0431 port tests do. INV-4 reads the
arguments the installer would pass, without starting anything. INV-6 and
INV-7 use a real `Face` and `urllib`. INV-8 is by hand, on Linux and on the
Windows box, once per release.

## 8. Alternatives considered (and rejected)

- **Start the new Face before stopping the old, and have the old one send
  its tabs to the new address.** Works within a process, but not for an
  update: on Windows the old process must end before its folder can be
  swapped, and on Linux the new program replaces the old process.
- **The same port on every launch.** Collides with whatever holds it
  (PRESS-0011 § 3 decision 2), and would let a tab from a stopped run
  reach a fresh one.
- **Server-sent events instead of asking.** One held connection per tab
  holds a server thread, and the old server's connections would have to
  be cut on stop for the tab to notice. Asking reuses `fetch`.
- **The session on the new process's command line.** Other accounts can
  read a command line (PRESS-0011 § 4.5).
- **The session in a file in Pressless's folder.** It outlives a crash and
  has to be cleaned up; an environment variable ends with the process.
- **Reload every open page once the new Face answers.** Loses words typed
  in a box that does not save by itself.

## 9. Out of scope

- A tab left from a stopped run coming back after a fresh start —
  deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_main.py::test_a_restart_keeps_the_port_and_session` |
| INV-2 | `tests/test_main.py::test_a_held_handed_port_starts_afresh` |
| INV-3 | `tests/test_main.py::test_the_resume_variable_is_read_once_and_removed` |
| INV-4 | `tests/test_installer.py::test_the_hand_over_travels_in_the_environment` |
| INV-5 | `tests/test_main.py::test_a_returning_tab_means_no_new_tab` |
| INV-6 | `tests/test_face.py::test_a_handed_session_keeps_the_link_one_use` |
| INV-7 | `tests/test_face.py::test_alive_needs_the_session` |
| INV-8 | **by hand** — `scripts/by-hand-browser-checks.py`, once per release |
| § 4.3's "deleted before anything starts a program" | INV-3's test, for `_serve`; nothing checks code added earlier in `main` |

## 11. Cross-doc impact

- `docs/specs/PRESS-0011-face.md` — `serve` gains `session`; `Face`
  gains `hand_over` and `returned`; `GET /alive` joins the Face's own
  routes.
- `docs/specs/PRESS-0023-self-update.md` § 4.9 step 5 — the new process
  comes back in the open tab where one returns.
- `docs/specs/PRESS-0204-tray-icon.md` — the by-hand Restart check
  expects the same tab.
- `docs/specs/PRESS-0223-several-sites.md` INV-9 — opening another site
  carries on in the same tab.
- `src/pressless/restarting.py`'s docstring.
- CHANGELOG, under the release that ships it.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0428-same-tab-after-restart-loop-log.md`.

## 13. Resource cost

One `GET /alive` from each open Pressless tab every two seconds, answered
from memory. No new dependency.
