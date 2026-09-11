# PRESS-0011 — The Face: the local server, and the error contract every message keeps

**Status:** accepted (2026-09-11). One cold-eyes loop by user instruction, folded in, nothing deferred; not converged, and no cold read has seen the fixes.
**Kind:** implement.
**Source:** ROADMAP PRESS-0011 (`docs/design.md` § The parts, § Errors,
§ Logging).

**Blocked by:** PRESS-0001, PRESS-0003 — both shipped.
**Blocker for:** PRESS-0012, PRESS-0018, PRESS-0020, PRESS-0021.

**Layman:** Pressless opens in his normal browser, reachable only from his
own computer, and every problem it reports tells him what happened, what it
means for his site, and what to do next.

## 1. Goal

After this ships, Pressless has a Face: a web server on his own machine that
his browser talks to, and the one place where a failure any part raises
becomes a sentence he understands. The editor (PRESS-0012), the publish button
(PRESS-0013) and setup (PRESS-0021) add pages to it. This item builds the
server they sit on and the error contract every page keeps.

## 2. Problem

1. **Every part raises typed failures and writes no prose**, and nothing turns
   them into sentences. `docs/design.md` § Errors gives that job to the Face
   alone, and there is no Face.
2. **Three specs leave a job to this one by name.** The Store's and Settings'
   notices reach the writer only if the Face captures them (PRESS-0005 § 4.1,
   PRESS-0001 § 4.1). Credentials names no secret, and the Face supplies the
   noun (PRESS-0002 § 4.3). A failure no part of Pressless raised is recorded
   by its type alone (PRESS-0003 § 2).
3. **PRESS-0073 item 5 is open**: does the Face format a failure's
   `__cause__` when it logs? Nothing answers it.
4. **A server on his machine is a trust boundary.** A loopback socket stops
   other machines. It does not stop a web page he visits from sending requests
   to it through his own browser.

## 3. Scope decisions (agreed with the user)

1. **The location label is "the Pressless-data folder, beside the
   program".** Decided by the user 2026-09-11. On Windows that folder sits
   beside the program's own `Pressless/` folder (PRESS-0022 scope decision 5),
   so a label saying "the Pressless folder" points a helper at the wrong one.
   `docs/design.md` § Errors is amended to match.
2. **(decided here) Loopback only, on a port the system chooses.** A fixed
   port collides with whatever else holds it. Pressless opens the browser on
   every launch, so nobody bookmarks the address.
3. **(decided here) Every request carries a secret made at launch.** Without
   it, any page he visits can send requests to the server through his browser.
4. **(decided here) The Face never formats a failure's cause, context or
   traceback.** This answers PRESS-0073 item 5.
5. **(decided here) The folder buttons never put the path in the page.**
6. **(decided here) This item wires no double-click.** `pressless.__main__`
   stays PRESS-0022's self-check. PRESS-0013 replaces its body (PRESS-0022
   § 4.5), and that is where `face.serve` is first called.

Every "(decided here)" is open to the writer's maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/face.py

LABEL = "the Pressless-data folder, beside the program"

class Site(enum.Enum):
    UNCHANGED = "Your site has not changed."
    UNKNOWN = "Pressless cannot tell whether your site changed."

@dataclass(frozen=True)
class Sentence:
    what: str      # what happened, in his words; may hold the "{secret}" slot
    site: Site     # what it means for his site
    next: str      # what to do next

SENTENCES: dict[type[Exception], Sentence]

def sentence_for(failure: BaseException, *, publishing: bool,
                 secret: str | None = None) -> Sentence: ...
def details_for(failure: BaseException) -> str: ...
def render_failure(failure: BaseException, *, publishing: bool,
                   secret: str | None = None) -> str: ...   # an HTML fragment
def render_notices(notices: list[str]) -> str: ...           # an HTML fragment

NOTICE_NEXT = "Nothing was lost. Send this to whoever helps you if you did not expect it."

@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str]
    body: bytes

Page = Callable[[Request], str]      # returns the page's HTML body

def serve(folder: Path, *, open_browser: bool = True) -> Face: ...

class Face:
    url: str                                  # the one link carrying the secret
    def add_page(self, method: str, path: str, page: Page, *,
                 publishing: bool = False) -> None: ...    # § 4.5
    def capture(self) -> ContextManager[list[str]]: ...   # notices, § 4.4
    def fail(self, failure: BaseException, *, publishing: bool,
             secret: str | None = None) -> str: ...        # shows and logs it
    def stop(self) -> None: ...
```

`folder` is Pressless's own folder, from `paths.ensure(paths.own_folder())`.
The Face writes the log there and opens it for the Open folder button.

### 4.2 The error contract

**Every failure type the package defines has its own entry in `SENTENCES`,
keyed by the class object.** Three short names are defined twice —
`Unreachable`, `Refused` and `RateLimited` in both `publisher.py` and
`insights.py` — so a name key hands one module's sentence to the other's
failure. Measured by walking the package:

```
python3 -c 'import importlib, inspect, pkgutil, pressless; ...'   # see INV-1
```

**`sentence_for` looks up the failure's own type, never a base.** A subclass
with no entry of its own is an unforeseen failure, not its base's case: the
base's sentence is written for no situation in particular, and PRESS-0009 § 6
gave the Publisher's failures types of their own for exactly that reason.

**The site part is `UNKNOWN` for `publisher.OutcomeUnknown` and
`UNCHANGED` for every other typed failure** (PRESS-0009 § 6).

**An unforeseen failure** — any type with no entry, including one from outside
the package — gets the last-resort sentence of `docs/design.md` § Errors:
*"Something went wrong that Pressless did not expect."*, then `UNKNOWN` where
`publishing` is true and `UNCHANGED` where it is false, then *"Try again, and
send the details below to whoever helps you."* The Face owns the publish
sequence (design rule 1), so it always knows which.

**A credential failure's sentence names the secret through `{secret}`.**
`sentence_for` fills the slot from the `secret` argument, which the Face
supplies because it knows which secret it asked for — *your publishing key*
or *your Google sign-in* (PRESS-0002 § 4.3, design rule 10).

**The words are the implementer's, the shape is not.** Each Publisher type's
*next* follows the answer PRESS-0009 § 4.1 pairs with it. What a test binds to
is that every entry has all three parts and the site part above.

### 4.3 Show details and the log

**`details_for` returns a typed failure's type and its own words**, as
`<module>.<Type>: <str(failure)>`. Each part keeps those words free of a
credential, an account name and a full path (`docs/design.md` § Logging).

**An `InsightsError` carrying a `detail` adds it on the next line.** That is
Google's own words about what it rejected, which PRESS-0019 § 4.5 and its
INV-25 keep off the message for this panel.

**For an unforeseen failure it returns the type's qualified name alone.** A
stock file error quotes the path it failed on (PRESS-0003 § 2).

**Nothing else, ever.** Not `__cause__`, not `__context__`, not a traceback,
not a frame's locals — for any failure.

**`Face.fail` shows the sentence and notes `details_for` in the log**, through
`log.open_log(folder)` opened by `serve`. The log never raises
(PRESS-0003 § 4.4), so a log that cannot be written costs nothing on screen.

**The details panel names the log file as `log.FILE_NAME`, its older half as
`log.OLD_NAME`, and their folder as `LABEL`** (PRESS-0003 § 11), beside two
buttons:

| Button | What happens |
|---|---|
| Open folder | `POST /folder/open`: the server opens `folder` with the platform's opener — `os.startfile` on Windows, `xdg-open` elsewhere |
| Copy location | `GET /folder/location` returns the path as `text/plain`; the page writes it to the clipboard on the click and never inserts it into the document |

The copy route relies on the page being a secure context for the clipboard.
The W3C Secure Contexts rule counts `http://127.0.0.1` as potentially
trustworthy. Source: https://www.w3.org/TR/secure-contexts/#is-origin-trustworthy

### 4.4 Notices

**`Face.capture()` records every `StoreNotice` and `SettingsNotice` raised
inside it**, with `warnings.catch_warnings(record=True)` and
`simplefilter("always")`. The default filter would show a repeat once, and
PRESS-0005 § 4.1 leaves suppressing repeats to the caller. Any other warning
raised inside it is dropped: nobody here wrote its words, and they may name a
path.

**`capture` holds one lock for its whole extent.** `catch_warnings` swaps
process-wide state, so two captures overlapping on the server's threads would
restore each other's filters.
Source: https://docs.python.org/3/library/warnings.html#warnings.catch_warnings

**Each captured notice is shown through `render_notices` and noted in the
log.** It is shown in the three parts `docs/design.md` § Errors requires: its
own words, `Site.UNCHANGED` — a Store or Settings call never touches the site
— and `NOTICE_NEXT`. One next step serves every notice because `StoreNotice`
covers three occasions under one type, so the Face cannot tell them apart. A
notice is not a failure: the call it came from completes.

**Every call the Face makes into the Store or Settings runs inside
`capture`.** Outside one, a notice is printed to the console prefixed with the
path of the file that called it — measured — and while another request holds a
capture, it lands on that request's list.

### 4.5 The server and its boundary

- `http.server.ThreadingHTTPServer` bound to `("127.0.0.1", 0)`, so the
  system picks the port. Run in a background thread; `stop` shuts it down.
- **The secret** is `secrets.token_urlsafe(32)`, made by `serve`. `url` is
  `http://127.0.0.1:<port>/?t=<secret>`. A request carrying the right `t`
  gets `Set-Cookie: pressless-<port>=<secret>; HttpOnly; SameSite=Strict;
  Path=/` and a redirect to the same path without the query. Every other
  request must carry that cookie, or it is refused with 403.
- **The cookie's name carries the port.** Browsers do not separate cookies
  by port, so a second Pressless would otherwise overwrite the first's.
  Source: https://www.rfc-editor.org/rfc/rfc6265#section-8.5
- **A POST whose `Origin` header names any other origin is refused with
  403.** A page served on another port of `127.0.0.1` is the same site, so
  its requests carry the cookie; its `Origin` is what gives it away.
- **The `Host` header must be exactly `127.0.0.1:<port>`**, or 403. That is
  what stops a page on the web reaching the server by pointing a name at the
  loopback address.
- **The request line is never printed or logged.** The handler's
  `log_message` is overridden to write nothing, because the standard one
  writes the request line — the secret included — to the console.
- `serve` opens the browser at `url` with `webbrowser.open`. Where no browser
  opens, it prints `url` to the console, which is his own. With
  `open_browser=False` it prints nothing; that is how the tests run it.
- **`handle_error` is overridden too**, to note the exception's type in the
  log and print nothing. The standard one prints a traceback naming the full
  path of every file in it to the console — measured.
- **Pages are added with `add_page`.** Past the checks above, a request runs
  the page registered for its method and path, or gets 404. One page today:
  `/` says Pressless is running. PRESS-0012, PRESS-0013, PRESS-0018,
  PRESS-0020 and PRESS-0021 add theirs.
- **Every page runs inside one catch** that hands any exception to
  `Face.fail`, with the `publishing` its `add_page` call gave, and answers 500
  with the fragment it returns. That is `docs/design.md` § Errors' last-resort
  catch. A page shows a failure it caught itself through `Face.fail` too,
  never by calling `render_failure`, so every failure shown is also logged.
- **`render_failure` and `render_notices` escape everything they insert**
  with `html.escape`. A failure's words and a notice's are text, not markup,
  and a notice names files he named himself.

### 4.6 What this module never does

- It never binds an address other than `127.0.0.1`.
- It never formats a failure's cause, context, traceback or locals.
- It never puts Pressless's folder path into a page.
- It never reaches GitHub or Google itself. It calls the parts that do, and
  hands Credentials' secret to them as an argument (design rule 10).

## 5. Invariants

- **INV-1** — Every failure type the package defines has an entry of its own
  in `SENTENCES`, with a non-empty *what* and *next* and a `Site`.
  *Test:* `tests/test_face.py::test_every_failure_type_has_a_sentence` — walk
  `pressless` with `pkgutil`, collect every `Exception` subclass that is not a
  `Warning` and whose `__module__` is the module defining it, and assert each
  is a key of `SENTENCES` with all three parts.
  *Breaks when:* a part gains a failure type and nobody writes its sentence;
  or an entry is keyed by name, so `publisher.Refused`'s sentence answers
  `insights.Refused`. The walk, not a hand list, is what lets a new type fail
  this.

- **INV-2** — The site part is `UNKNOWN` for `OutcomeUnknown` and for an
  unforeseen failure while publishing, and `UNCHANGED` for everything else.
  *Test:* `tests/test_face.py::test_what_it_means_for_his_site` — over
  `OutcomeUnknown`, a typed failure, a subclass with no entry of its own, and
  a `RuntimeError` with `publishing` true and false.
  *Breaks when:* the last-resort sentence says *unchanged* mid-publish, or a
  subclass falls back to its base's sentence.

- **INV-3** — Show details carries a failure's type, a typed failure's own
  words and an Insights failure's `detail`, and nothing else. A failure's
  cause, context and traceback reach neither the page, the log nor the
  console.
  *Test:* `tests/test_face.py::test_details_carry_no_cause` — a typed failure
  raised `from` an exception whose words hold a sentinel secret and a sentinel
  path: neither appears in `details_for`, the rendered page or the log line.
  An unforeseen `OSError` quoting a path: `details_for` is its type alone. An
  `InsightsError` with a detail: the detail is in `details_for`. A `/` whose
  page raises: the page holds the last-resort sentence and the console stays
  empty.
  *Breaks when:* details are built with `traceback.format_exception`, or with
  `str()` of an unforeseen failure; an Insights failure's detail is dropped;
  or the server keeps the standard `handle_error`.

- **INV-4** — A credential failure's sentence names the secret the Face asked
  for.
  *Test:* `tests/test_face.py::test_a_credential_failure_names_the_secret` —
  for each credentials type, `sentence_for(..., secret=<sentinel>)` has the
  sentinel in *what*.
  *Breaks when:* a sentence hard-codes *your publishing key*, which is false
  when the Face asked for the Google sign-in.

- **INV-5** — The server answers only its own origin, on the loopback address.
  *Test:* `tests/test_face.py::test_the_server_answers_only_its_own_origin` —
  `serve(folder, open_browser=False)`: the bound host is `127.0.0.1`; `/`
  without the cookie is 403; the `url` link is a redirect setting the cookie;
  `/` with the cookie is 200; with the cookie and `Host: pressless.example`
  it is 403; `POST /folder/open` with the cookie and
  `Origin: http://127.0.0.1:1` is 403 and opens nothing.
  *Breaks when:* the server binds `0.0.0.0`, skips the `Host` or `Origin`
  check, or takes the query secret on every request instead of trading it
  for the cookie.

- **INV-6** — A failure's words and a notice's reach the page escaped.
  *Test:* `tests/test_face.py::test_a_failure_is_escaped_on_the_page` — a
  `store.StoreError` whose words hold `<script>`, and a notice whose words
  hold `<script>`: each fragment holds `&lt;script&gt;` and no `<script>`.
  *Breaks when:* `render_failure` or `render_notices` inserts raw text.

- **INV-7** — The page names the log by its file name and its folder by
  `LABEL`, and never by its path.
  *Test:* `tests/test_face.py::test_the_details_name_the_label_not_the_path`
  — on `serve(tmp_path, open_browser=False)`, `fail` a typed failure: the
  fragment holds the label's words and `pressless.log`, each written out in
  the test, and not `str(tmp_path)`; `GET /folder/location` with the cookie
  returns the path.
  *Breaks when:* the page embeds the path for the Copy button to read.

- **INV-8** — A notice is shown and logged, and the call it came from
  completes.
  *Test:* `tests/test_face.py::test_a_notice_is_shown_and_the_call_completes`
  — the Store lists a folder holding a hand-dropped file it passes over,
  twice from one call site, inside `capture()` — the default filter keys on
  where a warning is raised, so only a repeat from one line tests it: each
  listing returns, two notices are on the
  captured list and in the log, and `render_notices` shows each with the words
  "Your site has not changed." and `NOTICE_NEXT`'s sentence, written out in the
  test.
  *Breaks when:* a notice is left to the default warnings filter, which shows
  the second once only; is turned into a failure; or is shown without the
  site and next-step parts.

- **INV-9** — The secret is never printed or logged after the opening link.
  *Test:* `tests/test_face.py::test_the_secret_is_never_printed_or_logged` —
  capture the console from before `serve(tmp_path, open_browser=False)`, make
  the opening request and one more: the console output and the log hold no
  copy of the secret.
  *Breaks when:* the handler keeps the standard `log_message`, which prints
  the request line.

## 6. Failure modes

| What happens | What the Face does |
|---|---|
| A part raises a typed failure | Shows its sentence, notes `details_for` in the log |
| Something raises a type with no entry | The last-resort sentence, with the site part from `publishing` |
| A notice is raised | Shows it as a line and logs it; the call completes |
| No browser opens | Prints `url` to the console |
| A page's work raises | The last-resort sentence on the page, the type alone in the log, nothing on the console |
| A request names a method and path no `add_page` registered | 404, with a plain body |
| The platform opener is missing or fails | Says it could not open the folder, and leaves Copy location working |
| The log cannot be written | Nothing on screen: the log never raises (PRESS-0003 § 4.4) |
| A request lacks the cookie, names a foreign `Host`, or is a POST from a foreign `Origin` | 403, with a plain body |
| He opens another page served on `127.0.0.1` | That page's server receives the cookie, since cookies are not separated by port. Accepted: only a program already serving on his own machine can receive it, and only when he opens its page |
| Pressless is launched twice | A second server on another port and a second tab. Accepted: nothing here keeps state between requests (`docs/design.md` § State) |

## 7. Tests

`tests/test_face.py`, unlabelled. It needs the loopback address and nothing
beyond it, so it runs everywhere, CI included. INV-1, INV-2, INV-3, INV-4,
INV-5, INV-6, INV-7, INV-8 and INV-9 each have the test their clause names.
Each is seen failing against a stub `face.py` that
declares the surface and raises `NotImplementedError`, then mutation-probed
once the code lands, one mutation per *Breaks when* route.

## 8. Alternatives considered (and rejected)

- **A fixed port.** It collides with whatever else holds it, and the browser
  is opened fresh on every launch, so a stable address buys nothing.
- **Loopback with no secret.** Any page he visits can send requests to a
  loopback server through his browser, and the `Host` check alone does not
  stop a request whose `Host` is right.
- **A desktop window instead of the browser.** `docs/design.md` § The stack
  chose the standard library's web server, and a window library is a new
  runtime dependency bought to replace something already chosen.
- **Keying sentences by class name.** Three names are shared between two
  modules, so it gives one module's sentence to the other's failure.
- **Falling back to a base type's sentence.** A base's sentence is written for
  no situation in particular, which is the failure § Errors names.
- **A traceback in Show details.** It carries frames, paths and locals, all of
  which § Logging forbids.

## 9. Out of scope

- The editor box and preview — PRESS-0012.
- The publish button and the write, build, publish sequence — PRESS-0013,
  which also wires the double-click to `face.serve`.
- Setup and the publishing key — PRESS-0021.
- Undo — PRESS-0015. The dashboard — PRESS-0020.
- One Pressless at a time — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_face.py::test_every_failure_type_has_a_sentence` |
| INV-2 | `tests/test_face.py::test_what_it_means_for_his_site` |
| INV-3 | `tests/test_face.py::test_details_carry_no_cause` |
| INV-4 | `tests/test_face.py::test_a_credential_failure_names_the_secret` |
| INV-5 | `tests/test_face.py::test_the_server_answers_only_its_own_origin` |
| INV-6 | `tests/test_face.py::test_a_failure_is_escaped_on_the_page` |
| INV-7 | `tests/test_face.py::test_the_details_name_the_label_not_the_path` |
| INV-8 | `tests/test_face.py::test_a_notice_is_shown_and_the_call_completes` |
| INV-9 | `tests/test_face.py::test_the_secret_is_never_printed_or_logged` |
| That each sentence reads well to him | **nothing** — a person reads them; S4's staged run is the first |
| The Open folder button on Windows | **nothing** — Windows cannot be run here; PRESS-0022's staged box is the first place it is observed |
| The clipboard write in a real browser | **nothing** — no test drives a browser; the route and the page script are checked, the browser's clipboard is not |

## 11. Cross-doc impact

- `docs/design.md` § Errors — the label reads "the Pressless-data folder,
  beside the program" (§ 3 decision 1), amended and gated 2026-09-11.
- PRESS-0003 § 11 and PRESS-0019 § 4.5 — the details panel binds to
  `log.FILE_NAME`, `log.OLD_NAME` and `InsightsError.detail` (§ 4.3).
- PRESS-0012, PRESS-0013, PRESS-0018, PRESS-0020 and PRESS-0021 — each adds
  its pages through `add_page` and keeps § 4.4's `capture` rule.
- PRESS-0073 — item 5 answered by § 3 decision 4.
- PRESS-0013 — replaces `pressless.__main__`'s body with a call to
  `face.serve`.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0011-face-loop-log.md`.

## 13. Resource cost

No cache and no state between requests (`docs/design.md` § State). One thread
per request while it runs. The log is PRESS-0003's, bounded there. No new
dependency: the server, the secret, the escaping and the browser launch are
all standard library.
