<!-- ants-spec-format: 1 -->
# PRESS-0235 — Publishing status survives leaving the page

**Status:** accepted (2026-10-07). One review round, the user's budget for a new spec; its fixes were read by no lane.
**Kind:** feature.
**Source:** ROADMAP PRESS-0235 (user request 2026-10-05, seen on PRESS-0231's
packaged run; the user chose a short spec and one review round).

**Amends:** PRESS-0012 (§§ 4.5, 4.7), PRESS-0013 (§§ 4.2, 4.4), PRESS-0014
(§§ 4.5, 4.7), PRESS-0015 (§§ 4.2, 4.6). § 11 lists each edit.

Layman: if you click away while your site is publishing, the page you land
on still says it is publishing, and then whether it worked.

## 1. Goal

After this ships, a press — Press to site in either editor, or Undo the last
press — is known to Pressless itself, not only to the page that started it.
Any editor or the list opened during a press says the press is running, and
says how it ended once it does. A second press while one runs is refused at
once instead of queuing behind it.

## 2. Problem

1. **Only the starting page hears the result.** `publishing._publish`,
   `page_editor._publish` and `undo._undo` each answer their own request and
   keep nothing. Leave the page and the answer goes to a page that is gone,
   though the press finishes.
2. **Opening an editor during a press stalls.** `editor._edit` and
   `page_editor._open` take `editor.LOCK`, which every press holds for its
   whole run, so the browser shows a blank loading page for as long as the
   press takes.
3. **A second press queues silently.** A press from a second tab waits on
   `editor.LOCK`, then saves and publishes again. An Undo pressed mid-press
   waits, then reverses the press that just landed.
4. **The pages tell the user to stay.** Both editors' scripts and
   `editor._UNDO_SCRIPT` say "Keep this page open." while a press runs.

## 3. Scope decisions (agreed with the user)

1. **Pressless keeps the running press and its outcome; every editor and the
   list show it in the press row's status line.** Decided by the user
   2026-10-05 (PRESS-0235's body).
2. **The press still runs inside its request.** *(decided here)* The three
   replies keep their shapes, so the starting page works as today. Pressless
   only records the press beside it.
3. **A press or an Undo while one runs is refused, never queued.**
   *(decided here)* A queued Undo reverses a press the user has not seen
   finish. A queued second publish repeats the work.
4. **An editor opened during a press shows a short holding page that opens
   the editor when the press ends.** *(decided here)* A loading page that
   stays blank for minutes reads as broken, worst of all to a user who cannot
   easily see the browser's own loading sign.
5. **A page asks about the press only while one is running.** *(decided
   here)* A page loaded while none runs learns of a later one when its own
   press is refused (decision 3). No page asks forever.
6. **How the last press ended is shown until the next save.** *(decided
   here)* After a save the page has changes the press did not publish, so
   "Published." beside them would mislead.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The record

```python
# src/pressless/pressing.py — new
PUBLISH, UNDO = "publish", "undo"

def start(kind: str) -> bool: ...        # False where a press is running
def end(outcome: Outcome) -> None: ...   # the press has ended, with this outcome
def forget() -> None: ...                # a save: an ended outcome stops being shown
def state() -> dict: ...                 # § 4.2's JSON
def register(face: Face) -> None: ...    # GET /press
```

One record per process, behind its own lock, held only to read or change the
record. `start` checks and marks running in one step, so two presses arriving
together cannot both start. `Outcome` holds the line's words and the failure's
HTML (`face.fail`'s output, or None). `forget` does nothing while a press
runs, since every publish saves first. Nothing is written to disk; a restart
starts with no record.

### 4.2 `GET /press`

Answers JSON `{"running", "kind", "said", "failure"}`:

- **Running:** `running` true, `kind` the press's kind, `said` the running
  words, `failure` null.
- **Ended, not yet forgotten:** `running` false, `said` the outcome's words,
  `failure` its HTML or null.
- **Nothing to say:** `running` false, `said` "", `failure` null.

It takes no `editor.LOCK`, so it answers during a press.

### 4.3 The words

`words.py` holds every press-row line under `script.press.` (PRESS-0242),
and the scripts and `pressing.py` take them from it,
so each sentence has one home:

| When | Words |
|---|---|
| A publish runs | "Publishing… this can take a few minutes the first time." |
| An undo runs | "Putting your site back… this can take a few minutes." |
| Published | "Published. Your site shows it within a few minutes." |
| Refused for paragraphs (PRESS-0234) | "Not published, because the box holds a different number of paragraphs from your page." |
| A publish failed | "Not published. The reason is below." |
| Undone | "Your site was put back." |
| An undo failed | "Your site was not put back. The reason is below." |
| Refused, a press is running | the running press's words |

"Keep this page open." goes from all three scripts.

### 4.4 The press routes

`publishing._publish`, `page_editor._publish` and `undo._undo` each:

1. call `pressing.start(kind)` before taking `editor.LOCK`. Where it returns
   False, answer at once with the route's usual keys: `published` (or
   `undone`) false, `failure` null, the posted `slug`, `draft` and `base`
   (or `waiting` and `base`) echoed back as the `PiecesChanged` refusal
   does, and new keys `"busy": true` and `said`, the running press's
   words. Nothing is saved and nothing is published.
2. call `pressing.end` with the outcome in a `finally`, so an unforeseen
   exception still ends the record, with the failed words. Only a request
   whose `start` returned True calls `end`.

Every other reply carries `"busy": false`. A `PiecesChanged` refusal ends the
record with its own words (§ 4.3).

`editor.save` and `page_editor._write` call `pressing.forget()` after writing,
which ends what decision 6 shows.

### 4.5 The pages

- **A page that opens during a press** writes the running words into its
  press-row line, disables Press to site and Undo the last press, and asks
  `GET /press` every two seconds. When `running` turns false it writes `said`
  into the line, or the standing words where `said` is empty, the failure
  where it shows failures today, and enables both buttons again.
- **A page that opens after a press ended** carries, from the server, the
  outcome's words in its line in place of the standing words, and its failure
  where it shows failures today, until `forget`.
- **A busy reply** shows its `said`, marks the page's change unsaved again so
  it is saved later, and starts asking, as above.
- **The starting page** behaves as today on its own reply, with § 4.3's
  words. Undo's summary still shows only there.
- **The list** has no press row; its `#undo-status` is the line, and its
  failure goes in its `#failure` box (PRESS-0236).
- **`editor._edit` and `page_editor._open` during a press** answer at once,
  without taking `editor.LOCK`, with a holding page: the running words in a
  `press-status` line, and a script that asks `GET /press` and reloads the
  page's own address when the press ends. A press that starts between the
  check and the lock is waited for as today.

## 5. Invariants

- **INV-1** — `pressing.start` returns True once and then False until `end`
  is called. *Test:* `tests/test_pressing.py::test_one_press_at_a_time`.
  *Breaks when:* a second `start` succeeds, or `end` leaves it running.
- **INV-2** — With a publish held mid-run, `GET /press` answers within a
  second with `running` true and the publish's words. After it ends, it
  answers `running` false with the published words. *Test:*
  `tests/test_pressing.py::test_the_press_is_known_while_it_runs`, holding
  the transport on an event.
  *Breaks when:* `/press` takes `editor.LOCK`, or the record is not ended.
- **INV-3** — With a publish held mid-run, `POST /publish`, `POST
  /page/publish` and `POST /undo` each answer within a second with `busy`
  true, the transport is called by the first press only, and `GET /press`
  still answers `running` true. *Test:*
  `tests/test_pressing.py::test_a_second_press_is_refused`.
  *Breaks when:* a route checks after taking the lock, skips the check, or
  ends the record on a refusal.
- **INV-4** — A publish whose transport raises a `BaseException` subclass,
  which no route's `except Exception` catches, leaves `GET /press` at
  `running` false with the failed words. *Test:*
  `tests/test_pressing.py::test_an_unforeseen_failure_ends_the_press`.
  *Breaks when:* `end` is not in a `finally`.
- **INV-5** — With a publish held mid-run, `GET /edit` and `GET /page`
  answer within a second with a `press-status` line holding the publish's
  words. *Test:* `tests/test_pressing.py::test_an_editor_opened_mid_press_holds`.
  *Breaks when:* either takes `editor.LOCK` before checking the record.
- **INV-6** — After a publish ends, `GET /edit` and `GET /page` carry the
  published words in their line; after a save, the standing words. *Test:*
  `tests/test_pressing.py::test_the_outcome_shows_until_a_save`.
  *Breaks when:* the server renders standing words over an unforgotten
  outcome, or `forget` is not called by a save.
- **INV-7** — Each editor script, `editor._UNDO_SCRIPT` and the holding
  page's script fetch `/press`, and none says "Keep this page open." *Test:*
  `tests/test_pressing.py::test_every_page_asks_about_the_press`, by script
  text. *Breaks when:* a script drops the ask or keeps the old words.

## 6. Failure modes

- **The starting page is gone when its reply is written.** The write fails;
  the record already holds the outcome.
- **A restart or update during a press** waits on `editor.LOCK` as today, so
  the press ends first.
- **A press that never ends** (a stuck upload) keeps pages asking, as today's
  page waits on its request. `publisher.TIMEOUT_SECONDS` bounds each
  request the press makes.
- **Two tabs, one idle:** the idle tab says nothing of the other's press until
  its own press is refused (decision 5).

## 7. Tests

`tests/test_pressing.py` gains INV-1, INV-2, INV-3, INV-4, INV-5, INV-6 and
INV-7. Each is seen failing against
the code before this item, then mutation-probed once the code lands. The
existing reply tests in `tests/test_publishing.py`, `tests/test_page_editor.py`
and `tests/test_undo.py` gain the `busy` key.

## 8. Alternatives considered (and rejected)

- **Run each press on a background thread and answer at once.** Rejected:
  every reply contract and the starting page's script change for no gain the
  record does not already give (decision 2).
- **Queue a second press.** Rejected (decision 3).
- **Let an editor opened mid-press wait, as today.** Rejected (decision 4).
- **Every page asks all the time.** Rejected (decision 5): a request every
  few seconds from every open tab, for a case the busy refusal covers.
- **Show the outcome once, to the first page that asks.** Rejected: with two
  tabs open the wrong one can take it.

## 9. Out of scope

- Telling an idle tab of another tab's press without its own press.
- Keeping a press across a restart.
- The undo summary on pages other than the starting one.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_pressing.py::test_one_press_at_a_time` |
| INV-2 | `tests/test_pressing.py::test_the_press_is_known_while_it_runs` |
| INV-3 | `tests/test_pressing.py::test_a_second_press_is_refused` |
| INV-4 | `tests/test_pressing.py::test_an_unforeseen_failure_ends_the_press` |
| INV-5 | `tests/test_pressing.py::test_an_editor_opened_mid_press_holds` |
| INV-6 | `tests/test_pressing.py::test_the_outcome_shows_until_a_save` |
| INV-7 | Partial: `tests/test_pressing.py::test_every_page_asks_about_the_press` reads script text; whether the scripts disable, ask and reload correctly is **nothing** — checked by hand in a browser |
| § 4.3 the words | **nothing** — read on the page |

## 11. Cross-doc impact

Each edit below is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0012-editor.md` § 4.5 — the list's `#undo-status` shows
  a press; § 4.7 — `GET /edit` holds during a press.
- `docs/specs/PRESS-0013-publish.md` § 4.2 — the route starts and ends the
  record and answers `busy`; § 4.4 — the page's words come from § 4.3.
- `docs/specs/PRESS-0014-fixed-pages.md` § 4.5 — `GET /page` holds during a
  press; § 4.7 — as PRESS-0013 § 4.2.
- `docs/specs/PRESS-0015-undo.md` § 4.2 — as PRESS-0013 § 4.2; § 4.6 — the
  pages' words.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0235-press-status-loop-log.md`.
