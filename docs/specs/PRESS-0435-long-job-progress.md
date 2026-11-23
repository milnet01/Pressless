<!-- ants-spec-format: 1 -->
# PRESS-0435 — Long jobs show how far they have got

**Status:** accepted (2026-11-21), implemented. No review: owed on the three-subsystems trigger alone (`CLAUDE.md` rule 14).
**Kind:** ux.
**Source:** ROADMAP PRESS-0435 (user, 2026-11-21: a short spec first; no
release until it is in).
**Pairs with:** PRESS-0433, its first case: setup's step 5 reading an
existing site.
**Amends:** PRESS-0009 INV-1 (§ 11).

Layman: while Pressless downloads, sends or packs your site, the "Working…"
note shows a bar and a running count, such as "120 of 480 files, 3.2 MB of
14 MB".

## 1. Goal

Every job that can run minutes shows, in the note PRESS-0434 puts up, a bar
and a line saying what it is doing and how far it has got: files done, of how
many where that is known, and the size so far. The note stays where it is
and keeps its size while the count changes.

## 2. Problem

1. **Step 5 looks frozen.** `setup.py`'s `check_pages` reads a root holding a
   site through `takein.look`, then `takein.look_folder` for a site Pressless
   did not make. Both reach `publisher._fetch`, which reads one blob per
   request inside the POST. The page shows only "Working…" for as long as
   that takes. A first-time user gave up there (PRESS-0433). The user's
   `pressless.log` has not been read; the cause is from the code.
2. **The same holds for every long job.** `publisher.publish` sends one blob
   per request with `BLOB_PACE_SECONDS` between them. `undo.undo` fetches
   through `publisher.fetch_previous` and then publishes.
   `pressless_import.fetch.fetch_site` downloads one file at a time. `sitefile.save` and `sitefile._unpack` walk every member. None
   says how far it has got.
3. **Screens whose scripts send without leaving the page show nothing
   new.** PRESS-0434 left them to their own lines.

## 3. Scope decisions (agreed with the user)

1. **A bar and a count, not a step name alone.** User, 2026-11-21: "a
   progress bar for how far a download has got, or at least that it is
   downloading and how much has come so far."
2. **Step 5 first, then publishing, importing, undo and restore, and the
   site file, plus the screens that send by script.** User, 2026-11-21.
3. **The count rides the request, not each screen.** *(decided here)*
   Every POST the Face dispatches gets one record; the loops in § 2 report
   into whichever record their thread holds. No screen is wired one by one,
   so a screen added later is covered.
4. **Words are made on the server.** *(decided here)* `GET /progress`
   answers the sentence already in the user's language, so the page script
   needs no new words of its own.

## 4. Design

### 4.1 `src/pressless/progress.py`

A new module that imports no `pressless` module, so PRESS-0009 INV-1's
reason (no route to the key) holds for it.

```python
def job() -> AbstractContextManager[None]:
    """The calling thread's record while the block runs; removed after."""

def count(key: str, done: int, total: int | None = None,
          bytes_done: int = 0, bytes_total: int | None = None) -> None:
    """The calling thread's record now says `key` with these numbers.
    Does nothing on a thread holding no record."""

def now() -> Counted | None:
    """The record updated last among those running, or None."""

@dataclass(frozen=True)
class Counted:
    key: str; done: int; total: int | None; bytes_done: int; bytes_total: int | None
```

Records are kept per thread under one lock, held only to read or change
them. `Face._dispatch` wraps each POST in `progress.job()`.

### 4.2 Where counts come from

| Loop | Key | Total known |
|------|-----|-------------|
| `publisher._fetch` (look, take-in, bring-in, undo, takeover) | `progress.downloading` | yes, files and size from the tree listing's `size` |
| `publisher.publish`, the blob loop | `progress.sending` | yes, files and size of `uploaded` |
| `pressless_import.fetch._Crawl`, each page kept | `progress.downloading` | no |
| `sitefile.save` | `progress.packing` | yes |
| `sitefile._unpack` | `progress.unpacking` | yes |

Each loop reports before its first file (0 done) and after each one.
`pressless_import.fetch.fetch_all`, a WordPress import's pictures, needs
none: it runs in a thread of its own and its screen already counts it.
`publishing` reports `progress.building`, with no numbers, before it calls
the Builder.

### 4.3 `GET /progress`

Registered by the Face. Takes no `editor.LOCK`. Answers JSON:

```json
{"running": true, "said": "Downloading your site: 120 of 480 files, 3.2 MB of 14 MB",
 "fraction": 0.23}
```

`said` is `say(key)` filled with the numbers; a number not known leaves its
part out. Sizes are one decimal, in KB, MB or GB. `fraction` is
`bytes_done / bytes_total` where `bytes_total` is known and above 0, else
`done / total`, else null. Where `now()` is None: `{"running": false, "said": "",
"fraction": null}`.

### 4.4 The note

The frame script's `showWorking` (PRESS-0434) becomes
`window.presslessWorking(key)`. The note it shows holds three rows from the
start: the words, a `<progress>` with no value (the moving kind), and a
count line one line high and empty. While the note is up the script asks
`GET /progress` every second. A running answer fills the count line with
`said` and sets the bar's value to `fraction` where it is not null. The
note's width is fixed, so nothing moves when the count arrives.

The note goes up on three paths:

1. **A form sent** — as PRESS-0434 does now. The old page's script keeps
   running until the reply arrives, so its asks keep coming.
2. **A POST sent by a page script** — the frame wraps `window.fetch`. A POST
   still unanswered after 600 ms puts the note up; when no wrapped POST is
   left unanswered, the note goes.
3. **A press running when a page opens** — `pressing.SCRIPT`'s `ask` calls
   `presslessWorking` while `GET /press` says one runs.

## 5. Invariants

- **INV-1** — During a POST whose loop has reported, `GET /progress`
  answers `running` true with that loop's words and numbers; after the POST
  ends it answers `running` false.
  *Test:* `tests/test_progress.py::test_a_held_fetch_is_counted_then_forgotten`.
  *Breaks when:* `_dispatch` does not wrap POSTs in `progress.job()`, or
  the record outlives its request.
- **INV-2** — `progress.count` on a thread holding no record changes
  nothing and raises nothing, so every caller outside the Face, tests
  included, runs as today.
  *Test:* `tests/test_progress.py::test_a_count_with_no_job_is_ignored`.
  *Breaks when:* `count` creates a record, or raises, where none is held.
- **INV-3** — `publisher._fetch` reports 0 of N before its first blob and
  N of N after its last, where N is the blobs it fetches, with `bytes_total` the
  sum of their listed sizes; `publisher.publish` does the same for the
  blobs it sends.
  *Test:* `tests/test_progress.py::test_fetch_and_publish_count_every_blob`.
  *Breaks when:* a loop counts blobs it skips, skips one it reads, or
  reports only at the end.
- **INV-4** — `src/pressless/progress.py` imports no `pressless` module.
  *Test:* `tests/test_publisher.py::test_publisher_imports_no_forbidden_sibling`,
  which walks `progress` too.
  *Breaks when:* `progress` imports `words`, `face` or anything else of
  Pressless.
- **INV-5** — `GET /progress` answers within a second while a POST holds
  `editor.LOCK`.
  *Test:* `tests/test_progress.py::test_progress_answers_during_a_press`.
  *Breaks when:* the handler takes `editor.LOCK` or waits on the job.
- **INV-6** — In headless Chrome and Firefox, setup's step 5 sent against a
  fake GitHub that holds each blob shows the count line filling while the
  POST is unanswered, and the note's box keeps its size from before the
  first count to after it.
  *Test:* `scripts/by-hand-browser-checks.py`'s `progress_note` rows, by
  hand in each browser, over a real `publisher.fetch_state` behind a form.
  *Breaks when:* the browser stops the old page's script during a pending
  form submit, or the count line is not reserved.
- **INV-7** — A POST sent by `fetch` that takes over 600 ms puts the note
  up and takes it down when answered; one answered sooner never shows it.
  *Test:* the same rows, against a slow and a quick POST.
  *Breaks when:* the wrapper misses `fetch` calls, or leaves the note up.

## 6. Failure modes

- **`GET /progress` fails or stops answering.** The note stays up with its
  moving bar and last count; the script stops asking after five misses, as
  `pressing.SCRIPT` does.
- **Two jobs at once** (two tabs). The note shows the one updated last.
  The count may switch between them; neither job is affected.
- **A listing without `size`.** `bytes_total` is None, so the bar runs on files.
- **A browser that stops scripts during a pending submit** (INV-6 fails).
  The note shows "Working…" and the moving bar, as PRESS-0434 does now.

## 7. Tests

`tests/test_progress.py`, new, in CI: INV-1, INV-2, INV-3 and INV-5, through
the Face's own server and the recording transport `tests/test_publisher.py`
already uses. INV-4 extends the existing import walk. INV-6 and INV-7 are
browser rows in `scripts/by-hand-browser-checks.py`, run by hand before
the release. Each new test is seen to
fail before the code it covers exists.

## 8. Alternatives considered (and rejected)

- **Each screen starts its own job and polls its own address.** More
  wiring per screen, and a screen added later shows nothing until someone
  remembers.
- **Run long jobs in the background and poll for the result.** Changes
  every reply's shape and PRESS-0235 § 3 decision 2. A larger change than
  showing a count.
- **Add the count to `GET /press`.** Reaches presses only, and changes
  PRESS-0235 § 4.2's shape.

## 9. Out of scope

- How far the browser has got sending an uploaded file to Pressless. The
  count starts once the file has arrived — deferred; not yet queued.
- Step 5 reading a plain site twice (`takein.look`, then
  `takein.look_folder`). The bar shows each read — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_progress.py::test_a_held_fetch_is_counted_then_forgotten` |
| INV-2 | `tests/test_progress.py::test_a_count_with_no_job_is_ignored` |
| INV-3 | `tests/test_progress.py::test_fetch_and_publish_count_every_blob` |
| INV-4 | `tests/test_publisher.py::test_publisher_imports_no_forbidden_sibling` |
| INV-5 | `tests/test_progress.py::test_progress_answers_during_a_press` |
| INV-6 | **Partial:** `scripts/by-hand-browser-checks.py`, run by hand; nothing in CI |
| INV-7 | **Partial:** `scripts/by-hand-browser-checks.py`, run by hand; nothing in CI |
| § 4.2's crawl and site-file counts | **nothing** — no test reads them |

## 11. Cross-doc impact

- PRESS-0009 INV-1 names `pressless.progress` beside `pressless.https`.
- PRESS-0434's roadmap entry: the screens it left are covered here.
- CHANGELOG, under the release that carries it.
- Words in all five languages.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0435-long-job-progress-loop-log.md`.
