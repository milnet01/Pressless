# PRESS-0019 — Insights: asking Google how the site is being read

**Status:** accepted (2026-09-06). Written after the code shipped, which is
not the direction a spec usually runs; §1 says why this one does, and which of
it is a record and which is a contract for work still to come. Gated to its
cap on the day it was written — a violent cap, so it routes to implementation
rather than a third cold read.
**Kind:** doc.
**Source:** ROADMAP PRESS-0063 (PRESS-0056 item 4; ADR-0005; `docs/design.md`
rule 8 and § State).

**Blocker for:** PRESS-0020.

<!-- Layman -->
**In plain English:** the part that asks Google how many people read the site,
written down at last — including a fix for the moment the dashboard offers a
second time span, where today's design would start spending the writer's
hourly allowance on every click.

## 1. Goal

Two jobs, and they are different in kind.

**A contract for what already ships.** Every other module names a spec;
this one names its own test file, and `insights.py`'s docstring cites
invariants that live only in that file's header. A test that both asserts a
rule and *is* the rule cannot falsify it, and a reader has nothing to hold the
code to. §5 gives those invariants a home outside the tests, unchanged in
number — so the module's own INV-1, INV-2, INV-7 and INV-14 citations still
resolve. **Its two INV-8 citations do not**: they name the whole-file promise,
which is INV-24 here, and §11 records the move.

**A decision for work not yet done.** PRESS-0056 item 4 left the cache
holding one report at a time. That is latent while the dashboard offers one
window and breaks the moment it offers two, so it needed deciding before
PRESS-0020 builds. §3 decision 1 decides it and §4.2 specifies it.

**Everything else here is a record, not a new instruction.** Where a
behaviour was never decided, this document says so rather than deciding it
now.

## 2. Problem

The module is relied on and has no contract a reader can breach.

**The cache holds one report, and the quota is what it protects.** `_cached`
refuses a stored reply written for any window but the one asked for, and
`_store` replaces the file. So with one window offered the cache works, and
with two every click alternates: each fetch evicts the other window's reply
and the next click refetches. Google meters this API per property per hour,
which is the whole reason the cache exists, so the guard stops guarding
exactly when the dashboard grows.

**Nothing about writing or publishing may depend on any of this**
(`docs/design.md` rule 8). A writer who declines the Google step loses the
dashboard and nothing else — which is why an absent property id is its own
typed failure rather than an error about the network.

**What is not the problem: the module's behaviour.** It ships, its invariants
are asserted, and PRESS-0056's other four items are closed. This document
does not reopen them.

## 3. Scope decisions (agreed with the user)

1. **The cache holds one report per window.** Decided 2026-09-06. The
   alternative — one slot, refetching whenever the window changes — is what
   ships, and it disables the quota guard as soon as a second window exists.
   This changes the cache file's shape, so it takes a `CACHE_VERSION` bump.
2. **The window ends at today.** Decided 2026-09-04 (PRESS-0070 item 6): the
   window carries one more calendar day than `days` and its last day is
   incomplete, so the same question asked twice in a day gives two numbers.
   The fresher figure was chosen over one that holds still.
3. **A behaviour nobody decided is recorded as open, not settled here.** §9
   lists the two.

## 4. Design

### 4.1 The public surface

`src/pressless/insights.py` exports `read`, `cache_path`, the `Report` and
`Country` results, the `Transport` seam, and the failure types
`InsightsError`, `NotConfigured`, `Unreachable`, `Refused` and `RateLimited`.

```python
def read(settings: Settings, token: str, folder: Path, *,
         days: int = DEFAULT_DAYS,
         max_age_seconds: float = DEFAULT_MAX_AGE,
         client: Transport | None = None) -> Report
def cache_path(folder: Path) -> Path
```

`DEFAULT_DAYS` is 28 and `DEFAULT_MAX_AGE` is 3600.0 — four weeks of
readership, and an hour between fetches. §4.4 says why the second is the
figure it is.

**The token is an argument and never fetched here.** Only the Face reaches
Credentials (`docs/design.md` rule 10), and INV-1 is what keeps that true.

**`Transport` is the one seam, and two of its properties are contract.** It
returns the response headers alongside the status and body; and it signals *no
answer* by raising `OSError`, every HTTP status being returned rather than
raised, so this module owns the mapping to the types above. It also supplies
the clock, so a test decides whether a cache is fresh by moving that clock.

### 4.2 The cache file

One file, in Pressless's own folder, named by `cache_path`. **Never inside the
site folder**, which is published in full — `read()` refuses such a folder
before making any request, because country-level readership on a public site
is a leak rather than an untidiness.

```json
{
  "version": 2,
  "windows": {
    "28": { "fetched_at": 0.0, "people": 0,
            "countries": [ { "code": "GB", "people": 0 } ] }
  }
}
```

**Keyed by the window**, so a reply for one window neither answers nor evicts
another's (INV-17). The key is the day count as a string, JSON having no other
kind of key.

**A file of another version reads as absent** (INV-18). Nothing migrates:
the cache is a copy of something Google can be asked for again, so a version
bump costs one request per window and no migration code that must then be kept
correct forever.

**Nothing prunes, and the bound is a requirement on the caller rather than a
rule this module enforces.** `days` is not writer-supplied — it comes from
whatever inside Pressless asks — so the file holds an entry per distinct
window asked for. **This document therefore requires that the dashboard offer
a fixed and small set of windows.** PRESS-0020 does not say so today; it
describes what the writer sees and names no window at all. A caller passing an
unbounded range of day counts grows this file without limit, and a cap is the
fix at that point. Nothing here checks it (§10).

**A cache that cannot be written is not worth failing a fetch over** — the
numbers in hand are still good. It is written the way Settings writes: a
temporary in the same directory, flushed and synced, then renamed over the
target, so a reader never sees a half-written file and no temporary is left
behind.

### 4.3 The request

**One request, and one is the whole of it — there is no retry.** A rate limit
is what the cache exists for, so answering it with more requests is the
opposite of the design.

A `POST` to `https://analyticsdata.googleapis.com/v1beta/properties/<property
id>:runReport`, carrying the token as an `Authorization: Bearer` header, asking for the last `days` days with dimension
`countryId`, metric `activeUsers`, and `metricAggregations` of `TOTAL`.

- **`countryId`, never `country`** — the first is the ISO alpha-2 code the flag
  pictures are keyed by, the second a localised display name.
- **The total is read, never summed.** Without `TOTAL` Google's answer carries
  no total, and adding the rows counts a visitor seen in two countries twice.
- **A row whose dimension value STARTS WITH `RESERVED_` is dropped**, an
  aggregate marker not being a country. The test is on the start of the value,
  which is where Google puts the marker.

### 4.4 Freshness, staleness, and the clock

A cached reply for this window answers where its age is **at or after zero and
below `max_age_seconds`**. Both ends bind: a one-sided test let a negative age
pass, so after a clock correction or a restored backup the cache read fresh
forever and showed old numbers labelled current, which is worse than showing
them stale.

**Any typed failure of the fetch falls back to a cached reply for this
window**, returned with `stale` set rather than raised — a refusal and a rate
limit as much as an unreachable host, since a dashboard showing yesterday's
numbers, labelled, beats one showing an error. With nothing cached for the
window, the failure is raised. §4.5's table is therefore what a caller sees
when nothing is cached.

**`max_age_seconds` is what makes the cache a quota guard, and the caller
chooses it.** The default is an hour because Google meters this API per
property per hour; a caller passing a much smaller value spends that budget
and breaches nothing this document can check (§10).

`Report.fetched_at` is when the request was made, not when the reply was read.
The two differ by the time Google took to answer, and the earlier stamp is the
conservative one: it can only make a cached reply look older than it is.

### 4.5 What each failure means

**The first two rows are raised before the cache is consulted at all**, so a
cached reply changes nothing about them — that is what INV-2 and INV-23 mean
by *before any request*. The rest are fetch failures, and where a reply is
cached for this window §4.4's fallback answers instead of raising them.

| What happens | What is raised |
|---|---|
| No property id in Settings | `NotConfigured`, before any request |
| The cache folder is, or is inside, the site folder | `InsightsError`, before any request |
| The transport raises `OSError` | `Unreachable` |
| Google answers 401 or 403 | `Refused` |
| Google answers 429 | `RateLimited` |
| Google answers anything else that is not 200 | `InsightsError` |
| Google's answer is not JSON, or names no total where it carried rows, or has a row naming no country | `InsightsError` |

**Google's own words ride on the failure and never in its message.** The
message is the writer-facing sentence `docs/design.md` § Errors requires; the
detail is what that sentence's *show me* toggle has to show, capped so a long
reply cannot become the message.

## 5. Invariants

**INV-1 to INV-16 are carried from `tests/test_insights.py`'s header unchanged
in number**, because `insights.py` cites several of them by id. **INV-17 is
the only one describing work still to do.** INV-18's behaviour already ships —
`_cached` refuses a version this build does not write before reading a field —
and what the cache change alters is the version's value; its test is new. INV-19 onwards are
behaviours that ship and are tested and that the header's list never named —
several of them the fixes that closed PRESS-0039 through PRESS-0056, each of
which settled something the contract had left open.

- **INV-1** — `insights.py` imports no `pressless` module other than
  `pressless.settings`. The token is an argument.
  *Test:* `tests/test_insights.py::test_insights_imports_no_forbidden_sibling`.
  *Breaks when:* someone fetches the token here instead of being handed it,
  which is the change `docs/design.md` rule 10 exists to stop.
  **It passes against a module that does nothing**, so it is evidence about
  imports and never about where the token came from.

- **INV-2** — With no property id in Settings, `read()` raises `NotConfigured`
  and makes no request at all.
  *Test:* `tests/test_insights.py::test_declined_dashboard_raises_and_asks_nothing`.
  *Breaks when:* the check moves after the request is built, and a writer who
  declined the dashboard is told his connection is down.

- **INV-3** — `read()` sends one request: a `POST` to the property's
  `:runReport` endpoint, carrying the token as an `Authorization: Bearer`
  header.
  *Test:* `tests/test_insights.py::test_one_request_names_the_property_and_carries_the_token`.
  *Breaks when:* a retry is added, which spends the quota the cache protects.

- **INV-4** — The body asks for the last `days` days, dimension `countryId`,
  metric `activeUsers`, and `metricAggregations` of `TOTAL`.
  *Test:* `tests/test_insights.py::test_request_body_asks_for_country_codes`.
  *Breaks when:* `country` replaces `countryId` and the flag pictures stop
  resolving, or `TOTAL` is dropped and §4.3's summing hazard returns.

- **INV-5** — `Report.people` is read from Google's `totals` and never summed
  from the rows; an answer carrying rows but no total raises `InsightsError`.
  *Test:* `tests/test_insights.py::test_total_is_read_and_never_summed` and
  `::test_answer_without_totals_is_refused`.
  *Breaks when:* the rows are summed, which counts a visitor seen in two
  countries twice and overstates the figure the writer reads.

- **INV-6** — `Report.countries` is ordered by people descending and ties by
  country code, so the same data always yields the same order, and a row whose
  dimension value starts with `RESERVED_` is dropped.
  *Test:* `tests/test_insights.py::test_countries_are_ordered_and_aggregate_rows_dropped`.
  *Breaks when:* the aggregate marker is treated as a country, which puts a
  row with no flag at the top of the list; or the tie-break is dropped, and a
  cached reply and a fresh one for identical data list the same countries in
  different orders, since only the fetch path sorts.

- **INV-7** — No failure this module raises carries the token, in its message
  or its representation.
  *Test:* `tests/test_insights.py::test_no_failure_names_the_token`.
  *Breaks when:* a request is interpolated into an error to make it easier to
  diagnose, and the token lands in the log the Face keeps.

- **INV-8** — There is exactly one cache file, at `cache_path(folder)`, which
  is `folder` and the name `insights.json`.
  *Test:* `tests/test_insights.py::test_cache_is_one_file_with_the_agreed_name`.
  *Breaks when:* a second file appears beside it, which is a second thing to
  delete and a second thing to leave behind.

- **INV-9** — A cached reply younger than `max_age_seconds` answers with no
  request made, and `stale` is False.
  *Test:* `tests/test_insights.py::test_fresh_cache_answers_without_a_request`.
  *Breaks when:* the age test is dropped, and every dashboard open spends a
  request.

- **INV-10** — A cached reply for a different window does not answer; the
  window asked for is fetched.
  *Test:* `tests/test_insights.py::test_cache_for_another_window_does_not_answer`.
  *Breaks when:* the window is not compared, and the writer reads one window's
  numbers under another's heading.

- **INV-11** — A cached reply older than `max_age_seconds` is refetched, and
  the fresh reply replaces the old one on disk.
  *Test:* `tests/test_insights.py::test_expired_cache_is_refetched_and_replaced`.
  *Breaks when:* the fetch happens and the write does not, so every open
  refetches.

- **INV-12** — A refetch that fails while a cached reply for this window
  exists returns that reply with `stale` True, rather than raising.
  *Test:* `tests/test_insights.py::test_failed_refetch_falls_back_to_the_cache`.
  *Breaks when:* the failure propagates, and a dashboard that could have shown
  yesterday's numbers shows an error instead.

- **INV-13** — A refetch that fails with nothing cached raises the typed
  failure.
  *Test:* `tests/test_insights.py::test_failed_refetch_without_a_cache_raises`.
  *Breaks when:* an empty report is returned instead, and a broken connection
  reads as a site nobody visited.

- **INV-14** — A cache file that is unreadable or unparsable is ignored and
  refetched over, never fatal.
  *Test:* `tests/test_insights.py::test_corrupt_cache_is_refetched_over`.
  *Breaks when:* the read is trusted, and a half-written file takes the
  dashboard down.

- **INV-15** — `Report.fetched_at` is when the reply was fetched, not when it
  was read.
  *Test:* `tests/test_insights.py::test_fetched_at_is_when_the_reply_was_fetched`.
  *Breaks when:* it is stamped on read, and every cached reply looks new — so
  nothing is ever stale and INV-12's label means nothing.

- **INV-16** — 401 and 403 raise `Refused`, 429 raises `RateLimited`, a
  transport `OSError` raises `Unreachable`, and anything else that is not 200
  raises `InsightsError`.
  *Test:* `tests/test_insights.py::test_http_status_maps_to_the_typed_failure`.
  *Breaks when:* the statuses are collapsed, and the writer is told to slow
  down when his authorisation is what Google refused.

- **INV-17** — Storing a report for one window leaves every other window's
  entry in the cache intact.
  *Test:* `tests/test_insights.py::test_one_windows_reply_does_not_evict_another`
  — fetch two windows, then assert the first still answers from the cache with
  no request made.
  *Breaks when:* the file holds one report rather than one per window, which
  is what ships today: the guard then protects nothing from the moment a
  second window is offered, and the failure is invisible because each answer
  is correct.

- **INV-18** — A cache file carrying a `version` other than the one this build
  writes reads as absent, and nothing is migrated.
  *Test:* `tests/test_insights.py::test_another_versions_cache_reads_as_absent`.
  *Breaks when:* a foreign file is read field by field, and a shape this build
  does not know is interpreted as though it did.

- **INV-19** — A redirect that changes origin drops the `Authorization`
  header; a same-origin redirect keeps it. Scheme, host and port together are
  the origin.
  *Test:* `tests/test_insights.py::test_a_cross_origin_redirect_drops_the_token`,
  `::test_a_same_origin_redirect_keeps_the_token`,
  `::test_a_same_host_change_of_origin_drops_the_token` and
  `::test_the_client_installs_the_redirect_handler`.
  *Breaks when:* the module's own client is built without the handler, and
  whoever answers a redirect is handed the token — the library copies every
  header onto the target, another host included.

- **INV-20** — Every request carries a timeout.
  *Test:* `tests/test_insights.py::test_every_request_carries_a_timeout`.
  *Breaks when:* a black-holed connection hangs the dashboard instead of
  failing it.

- **INV-21** — A reply the transport cannot complete reaches the caller as
  `OSError`, which is the seam's own word for *no answer*.
  *Test:* `tests/test_insights.py::test_a_broken_reply_reaches_the_caller_as_oserror`.
  *Breaks when:* a truncated body or a malformed status line escapes as its own
  type, past every caller of the seam, and the typed failures this module
  promises are not what the Face receives.

- **INV-22** — A clock that moved backwards does not freeze the cache: an age
  below zero is not fresh.
  *Test:* `tests/test_insights.py::test_a_clock_that_moved_backwards_does_not_freeze_the_cache`.
  *Breaks when:* the age test is one-sided, and after a clock correction or a
  restored backup the cache reads fresh forever and shows old numbers labelled
  current.

- **INV-23** — A cache folder that is, or is inside, the site folder is
  refused before any request is made.
  *Test:* `tests/test_insights.py::test_a_cache_folder_inside_the_site_folder_is_refused`.
  *Breaks when:* the rule is asserted in a comment rather than enforced: the
  site folder is published in full, so the Builder would copy the cache and the
  Publisher would upload it, putting country-level readership on a public site.

- **INV-24** — The cache reaches the disk before the rename, no temporary is
  left behind on any path, and its line endings are written explicitly rather
  than left to the platform.
  *Test:* `tests/test_insights.py::test_cache_reaches_the_disk_before_the_rename`
  and `::test_cache_names_the_line_endings`.
  *Breaks when:* the sync is dropped, so a power loss commits the rename ahead
  of the blocks and leaves an empty file; a failure leaves its temporary in
  Pressless's folder to accumulate; or the platform decides the endings and the
  same cache is different bytes on the two systems.

- **INV-25** — Google's own words about what it rejected ride on the failure
  and never in its message, capped in length.
  *Test:* `tests/test_insights.py::test_googles_own_reason_is_carried_on_the_failure`.
  *Breaks when:* the body is read and discarded, and the *show me* toggle
  `docs/design.md` § Errors requires has nothing to show; or it is put in the
  message, and a long reply becomes the sentence the writer reads.

- **INV-26** — A window Google reports with neither rows nor a total reads as
  zero people rather than raising.
  *Test:* `tests/test_insights.py::test_a_window_with_no_visitors_reads_as_zero`.
  *Breaks when:* an absent total is refused unconditionally, and a quiet week
  becomes an error. Deliberately narrow: an answer carrying rows and no total
  is still refused (INV-5), because summing those is the overstated number that
  refusal keeps out.

## 6. Failure modes

| When | What happens |
|---|---|
| The writer declined the dashboard | `NotConfigured`, no request. Writing and publishing are untouched (rule 8) |
| The fetch fails any typed way, and this window is cached | The cached reply, `stale` True |
| The fetch fails, and nothing is cached for this window | That typed failure (§4.5) |
| The cache file is corrupt | Ignored, refetched over |
| The cache file is a version this build does not write | Ignored, refetched over (INV-18) |
| The cache cannot be written | The report is still returned; the next call refetches |
| A window nobody read | Zero people, no countries — see §9's open question |

## 7. Tests

`tests/test_insights.py` — every invariant's tests are named in §5 and
tabulated in §10. Mostly one apiece; where an invariant has two halves that
break separately, it names both, and INV-19 names four because dropping the
header and keeping it are different failures on different redirects. **No test reaches the network.** Every test of `read()` hands in a recording
double through `client`, which is what lets the request invariants assert on
requests made and on requests *not* made, and that double supplies the clock,
so every cache-age test is deterministic and nothing sleeps. **INV-1's test is
an import walk, and INV-19 to INV-21 exercise the module's own client
directly** — the `client` seam replaces that client, so nothing handed through
it could observe the redirect handler, the timeout or the `OSError`
conversion.

**INV-17 and INV-18 are the two tests this document adds.** INV-17 is to be
seen failing first, against the shipped single-slot cache. **INV-18 is not**:
its behaviour ships, so its test passes on the run that introduces it, and
demanding a red run there would mean building something broken to produce
one.

**Not asserted, deliberately:** that `read()` builds the module's own client
when none is handed in. Proving it would mean letting a test reach Google.

## 8. Alternatives considered (and rejected)

| Rejected | Why |
|---|---|
| **Keeping one cache slot** | What ships. It disables the quota guard the moment a second window is offered, and the symptom is invisible: every answer is correct and only the request count moves. |
| **One file per window** | A second thing to delete, a second thing to leave behind, and INV-8 exists to stop exactly that. The window is a key inside one file instead. |
| **Migrating a version-1 cache to version 2** | Migration code for a file whose entire content can be fetched again. A bump costs one request per window, once. |
| **Capping how many windows are kept** | A cap needs a number nobody has a reason for, and §4.2 says why the file cannot grow without bound as things stand. The cap becomes necessary if a caller ever passes an arbitrary window. |
| **Retrying a rate limit** | The cache is the answer to a rate limit; more requests is the opposite of the design. |

## 9. Out of scope

- **Obtaining and refreshing the Google token** — setup's, not this module's.
  It is handed in as an argument.
- **The dashboard itself, and which windows it offers** — PRESS-0020's.
- **OPEN: the zero-visitor answer is unverified against the live API.** A
  window with no rows and no total reads as zero rather than raising, which
  PRESS-0056 item 5 settled by reasoning about GA4 omitting default-valued
  fields. Nobody has seen Google do it.
- **OPEN: whether Google's aggregate row can appear among the country rows.**
  The prefix filter is the guard for that reading of Google's wording; which
  of the two readings is right is PRESS-0074's, and unsettled.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_insights.py::test_insights_imports_no_forbidden_sibling` |
| INV-2 | `tests/test_insights.py::test_declined_dashboard_raises_and_asks_nothing` |
| INV-3 | `tests/test_insights.py::test_one_request_names_the_property_and_carries_the_token` |
| INV-4 | `tests/test_insights.py::test_request_body_asks_for_country_codes` |
| INV-5 | `tests/test_insights.py::test_total_is_read_and_never_summed` + `::test_answer_without_totals_is_refused` |
| INV-6 | `tests/test_insights.py::test_countries_are_ordered_and_aggregate_rows_dropped` |
| INV-7 | `tests/test_insights.py::test_no_failure_names_the_token` |
| INV-8 | `tests/test_insights.py::test_cache_is_one_file_with_the_agreed_name` |
| INV-9 | `tests/test_insights.py::test_fresh_cache_answers_without_a_request` |
| INV-10 | `tests/test_insights.py::test_cache_for_another_window_does_not_answer` |
| INV-11 | `tests/test_insights.py::test_expired_cache_is_refetched_and_replaced` |
| INV-12 | `tests/test_insights.py::test_failed_refetch_falls_back_to_the_cache` |
| INV-13 | `tests/test_insights.py::test_failed_refetch_without_a_cache_raises` |
| INV-14 | `tests/test_insights.py::test_corrupt_cache_is_refetched_over` |
| INV-15 | `tests/test_insights.py::test_fetched_at_is_when_the_reply_was_fetched` |
| INV-16 | `tests/test_insights.py::test_http_status_maps_to_the_typed_failure` |
| INV-17 | `tests/test_insights.py::test_one_windows_reply_does_not_evict_another` — not yet written; the cache change is what it gates |
| INV-18 | `tests/test_insights.py::test_another_versions_cache_reads_as_absent` — not yet written; the behaviour it locks already ships |
| INV-19 | `tests/test_insights.py::test_a_cross_origin_redirect_drops_the_token` + `::test_a_same_origin_redirect_keeps_the_token` + `::test_a_same_host_change_of_origin_drops_the_token` + `::test_the_client_installs_the_redirect_handler` |
| INV-20 | `tests/test_insights.py::test_every_request_carries_a_timeout` |
| INV-21 | `tests/test_insights.py::test_a_broken_reply_reaches_the_caller_as_oserror` |
| INV-22 | `tests/test_insights.py::test_a_clock_that_moved_backwards_does_not_freeze_the_cache` |
| INV-23 | `tests/test_insights.py::test_a_cache_folder_inside_the_site_folder_is_refused` |
| INV-24 | `tests/test_insights.py::test_cache_reaches_the_disk_before_the_rename` + `::test_cache_names_the_line_endings` |
| INV-25 | `tests/test_insights.py::test_googles_own_reason_is_carried_on_the_failure` |
| INV-26 | `tests/test_insights.py::test_a_window_with_no_visitors_reads_as_zero` |
| §3 decision 2's window ending at today | **nothing** — the same question asked twice in a day gives two numbers by design, so no assertion can tell that from a fault |
| The zero-visitor reading of GA4 | **nothing against the live API** — the test asserts what this module does with such an answer, never that Google sends one |
| A cache written outside Pressless's own folder by a caller passing one | `read()`'s own refusal covers the site folder; anywhere else is the caller's choice and nothing here checks it |
| §4.2's requirement that the dashboard offer a fixed, small set of windows | **nothing** — the module cannot see how many distinct windows a caller will ask for, and a cap here would need a number nobody has a reason for. PRESS-0020 is where the set gets fixed |

## 11. Cross-doc impact

- `CHANGELOG.md` — an entry when the cache change ships, not for this
  document.
- `insights.py`'s docstring — it says the invariants live in the test header
  and that there is no specs file. Both stop being true when this is accepted.
- `tests/test_insights.py`'s header — same sentence, same fix: it becomes a
  pointer here rather than the contract itself.
- `docs/design.md` § State — **it says the last reply is kept, singular.**
  That stops being true when the cache holds one per window, so it needs
  widening when the cache change ships, with its own gate; this document does
  not edit it.
- **PRESS-0020 must record the set of windows it offers**, which §4.2 requires
  and nothing here can enforce. Its bullet names no window today.
- `insights.py`'s `_store` cites INV-8 twice for the whole-file promise —
  once in its docstring and once at the fsync. That promise is INV-24 here, so
  both citations move when the docstring is repointed.

## 12. Cold-eyes loop log

The rows live in `docs/reviews/PRESS-0019-insights-loop-log.md`.
