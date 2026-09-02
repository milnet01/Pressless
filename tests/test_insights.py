# INV-1..16 for PRESS-0019 (Insights). One test per invariant, named in the
# list below. There is no docs/specs file for this item, so the roadmap item
# PRESS-0019 is the contract and this header is where its invariants are
# written down.
#
# Why this exists: Insights is the part that asks Google Analytics how the
# site is being read. Three things about it are easy to get wrong and
# expensive to notice later -- it is HANDED the access token and must never
# reach another part of Pressless for one; it must report the total Google
# names rather than the sum of the rows, which double-counts a visitor seen
# in two countries; and it must answer from its cache when Google will not
# answer at all, because a dashboard that raises rather than showing
# yesterday's numbers is a dashboard the writer stops opening.
#
# No test reaches the network. Every test hands in a recording double
# through the `client` argument, which is what lets INV-3, INV-4 and the
# cache invariants assert on requests made and requests NOT made. The double
# also supplies the clock (`now()`), so every cache-age test is
# deterministic and nothing here sleeps.
#
# THE CONTRACT
#
#   INV-1   insights.py imports no pressless module other than
#           pressless.settings: not credentials, not the store, not marks,
#           not the publisher. The token is an argument.
#   INV-2   settings.analytics_property_id is None -- the writer declined
#           the dashboard -- so read() raises NotConfigured and makes no
#           request at all.
#   INV-3   read() sends ONE request: a POST to the property's :runReport
#           endpoint on Google's analytics-data host, carrying the token as
#           an "Authorization: Bearer <token>" header.
#   INV-4   the request body asks for the last `days` days, dimension
#           "countryId" (never "country"), metric "activeUsers", and
#           metricAggregations ["TOTAL"].
#   INV-5   Report.people is read from Google's "totals", never summed from
#           the rows; an answer carrying no "totals" raises InsightsError.
#   INV-6   Report.countries is ordered by people descending, and a row
#           whose dimension value starts with "RESERVED_" is an aggregate
#           marker rather than a country and is dropped.
#   INV-7   no failure raised by this module carries the token, in its
#           message or its representation.
#   INV-8   there is exactly one cache file and it is at
#           cache_path(folder) == folder/"insights.json".
#   INV-9   a cached reply younger than max_age_seconds answers with no
#           request being made, and Report.stale is False.
#   INV-10  a cached reply for a DIFFERENT `days` window does not answer;
#           the window asked for is fetched.
#   INV-11  a cached reply older than max_age_seconds is refetched, and the
#           fresh reply replaces the old one on disk.
#   INV-12  a refetch that fails while a cached reply for this window exists
#           returns the cached reply with Report.stale True, rather than
#           raising.
#   INV-13  a refetch that fails with nothing cached raises the typed
#           failure.
#   INV-14  a corrupt cache file is ignored and refetched over, never fatal.
#   INV-15  Report.fetched_at is when the reply was FETCHED, not when it was
#           read.
#   INV-16  401/403 -> Refused, 429 -> RateLimited, a transport OSError ->
#           Unreachable, anything else -> InsightsError.
#
# NOT ASSERTED, deliberately: that read() builds the module's own client
# when client=None. Proving it would mean letting a test reach Google. Every
# test here passes a double instead.
#
# INV-1 passes against the stub by design -- an import walk passes against a
# module that does nothing, so it is evidence about imports and never about
# where the token came from. Every other invariant needs the real
# implementation; against the stub each one fails where it calls read() or
# cache_path(), because the stub raises NotImplementedError unconditionally.
# That failure is expected and is the point of this run: PRESS-0019 is not
# yet implemented.
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest
from _durability_watch import _assert_synced_before_replace, _watch_durability
from _open_watch import _watch_opens

import pressless.insights as insights_module
from pressless.insights import (
    DEFAULT_DAYS,
    Country,
    InsightsError,
    NotConfigured,
    RateLimited,
    Refused,
    Report,
    Unreachable,
    cache_path,
    read,
)
from pressless.settings import Credentials, Settings

# The cache file's name, written out here rather than imported from the
# module under test. Sharing the literal would have INV-8 compare the module
# against itself, so cache_path() could name any file and stay green -- the
# same reasoning CLAUDE.md records for FILE_NAME in test_settings.py. Do not
# tidy this into an import.
CACHE_FILE_NAME = "insights.json"

# A value no real access token would be. INV-7 asserts it reaches no
# failure's str() or repr().
SENTINEL = "sentinel-token-must-not-appear-in-any-message"

# A numeric property id, which is what Settings holds -- never the G-...
# measurement tag.
PROPERTY = "123456789"

# A fixed clock, deliberately in the PAST relative to any real run. The
# double's now() is the module's only clock (INV-9, INV-11, INV-15), and an
# implementation that reaches for the wall clock instead would read every
# seeded cache as older than the real epoch and refetch it -- which is what
# test_fresh_cache_answers_without_a_request catches.
NOW = 1_600_000_000.0

# The standard answer. The rows sum to 1500 and the total is 1200: a visitor
# seen in two countries appears in both rows, so summing overstates. Every
# test that reads a people count uses this fixture, so no test in this file
# can pass against an implementation that sums (INV-5).
ROWS = (("GB", 400), ("ZA", 900), ("US", 200))
TOTAL = 1200


def _settings(**overrides) -> Settings:
    """A Settings whose fields tests don't care about are filled with
    neutral placeholders. Never a real repository, account or path."""
    values = {
        "site_folder": Path("/writer/Pressless/site"),
        "repository": "owner/name",
        "daily_prompt_filter": "dailyprompt-*",
        "untouchable": ("CNAME", ".nojekyll"),
        "credentials": Credentials(
            store="keyring",
            github_account="publishing-key",
            google_account="dashboard-token",
        ),
        "analytics_property_id": PROPERTY,
    }
    values.update(overrides)
    return Settings(**values)


def _google(rows=ROWS, total: int | None = TOTAL) -> bytes:
    """An answer shaped like Google's runReport reply. `total=None` omits
    the "totals" block entirely -- INV-5's refusal case."""
    payload: dict = {
        "rows": [
            {
                "dimensionValues": [{"value": code}],
                "metricValues": [{"value": str(people)}],
            }
            for code, people in rows
        ],
        "rowCount": len(rows),
    }
    if total is not None:
        payload["totals"] = [{"metricValues": [{"value": str(total)}]}]
    return json.dumps(payload).encode("utf-8")


def _ok(body: bytes) -> tuple[int, dict[str, str], bytes]:
    return (200, {}, body)


class _Transport:
    """A recording double for the module's Transport protocol.

    Every call is recorded, in call order, in `.requests` as
    (method, url, body, headers) -- what INV-3, INV-4 and every "no request
    was made" assertion read.

    `answers` maps a URL substring to a response, first match winning;
    anything it does not name falls through to `default`. Answering by URL
    rather than by call position is what keeps these tests blind to how many
    requests an implementation makes: a positional queue breaks the moment
    an implementation legitimately adds one, shifting every later answer
    onto the wrong step.

    `unreachable` makes every request raise OSError instead of answering --
    Google not answering at all, never a status code.

    `.clock` is the module's clock, read through now(). Tests move it by
    assignment, so no cache-age test sleeps or reads the wall clock.
    """

    def __init__(
        self,
        answers: list[tuple[str, tuple[int, dict[str, str], bytes]]] | None = None,
        default: tuple[int, dict[str, str], bytes] | None = None,
        unreachable: bool = False,
        clock: float = NOW,
    ) -> None:
        self.requests: list[tuple[str, str, bytes | None, dict[str, str]]] = []
        self._answers = list(answers) if answers is not None else []
        self._default = default if default is not None else _ok(_google())
        self._unreachable = unreachable
        self.clock = clock

    def request(
        self, method: str, url: str, body: bytes | None, headers: dict[str, str]
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests.append((method, url, body, headers))
        if self._unreachable:
            raise OSError("no answer from Google")
        for substring, response in self._answers:
            if substring in url:
                return response
        return self._default

    def now(self) -> float:
        return self.clock


def _seed(folder: Path, transport: _Transport, *, days: int = DEFAULT_DAYS,
          max_age_seconds: float = 3600.0) -> Report:
    """Populate the cache the way the module itself writes it -- by reading
    through it.

    Hand-writing the file would encode a guess about its shape, which is the
    same failure the Publisher's first test double made about request order
    (CLAUDE.md, "a test double written before the implementation encodes a
    guess"). Only test_corrupt_cache_is_refetched_over writes the file
    directly, and what it writes is not JSON at all, so it assumes nothing
    about the format.
    """
    return read(
        _settings(),
        "a-token",
        folder,
        days=days,
        max_age_seconds=max_age_seconds,
        client=transport,
    )


def _authorization(headers: dict[str, str]) -> str | None:
    """The Authorization header, looked up case-insensitively: HTTP header
    names are case-insensitive and INV-3 is about the token being sent as a
    bearer credential, not about one spelling of the key."""
    for name, value in headers.items():
        if name.lower() == "authorization":
            return value
    return None


def _codes(report: Report) -> list[str]:
    return [country.code for country in report.countries]


# --------------------------------------------------------------- INV-1 ----


def test_insights_imports_no_forbidden_sibling():
    """INV-1: insights.py imports no pressless module other than
    pressless.settings.

    Walks the module's AST, as test_marks_is_pure and
    test_publisher_imports_no_forbidden_sibling do.

    Breaks when an implementer imports pressless.credentials to fetch the
    Google token rather than taking it as an argument -- the breach of
    docs/design.md rule 10 this invariant exists to catch. Reaching the
    store, marks or the publisher is caught the same way.

    Weak in the way the Publisher's twin is weak: an import walk passes
    against a module that does nothing, so it passes against the stub by
    design. It is evidence about imports and never about where the token
    came from.
    """
    tree = ast.parse(inspect.getsource(insights_module))

    pressless_imports = set()
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "pressless":
                    pressless_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_imports.append(node)
            elif node.module and node.module.split(".")[0] == "pressless":
                if node.module == "pressless":
                    for alias in node.names:
                        pressless_imports.add(f"pressless.{alias.name}")
                else:
                    pressless_imports.add(node.module)

    forbidden = pressless_imports - {"pressless.settings"}
    assert not forbidden, (
        f"insights.py imports {sorted(forbidden)!r}, not just "
        f"pressless.settings -- this is the breach of docs/design.md rule 10 "
        f"that INV-1 exists to catch: reaching another part of Pressless for "
        f"the Google token rather than taking it as an argument"
    )
    assert not relative_imports, (
        f"insights.py has relative import(s) "
        f"{[node.module for node in relative_imports]!r}, which can only name "
        f"a sibling pressless module"
    )


# --------------------------------------------------------------- INV-2 ----


def test_declined_dashboard_raises_and_asks_nothing(tmp_path):
    """INV-2: where settings.analytics_property_id is None the writer
    declined the dashboard, so read() raises NotConfigured and makes no
    request.

    Asserting the TYPE is what makes it bite: an unreachable network also
    produces no numbers, so a clause asserting only that something was
    raised passes against an implementation that reports a declined
    dashboard as a network fault -- and the writer is then told to check his
    connection about a feature he turned off.

    Breaks when an implementer builds the URL first and lets Google refuse
    an empty property id, which reaches the network on behalf of a writer
    who asked for no dashboard at all.
    """
    transport = _Transport()

    with pytest.raises(NotConfigured):
        read(
            _settings(analytics_property_id=None),
            "a-token",
            tmp_path,
            client=transport,
        )

    assert not transport.requests, (
        f"a declined dashboard still reached the network: "
        f"{[(m, u) for m, u, _, _ in transport.requests]!r}"
    )


# --------------------------------------------------------------- INV-3 ----


def test_one_request_names_the_property_and_carries_the_token(tmp_path):
    """INV-3: read() sends one request, a POST to the property's :runReport
    endpoint on Google's analytics-data host, with the token as a bearer
    credential.

    The host and the path shape are pinned; the API version segment between
    them is not, because a version bump is a change to the module rather
    than a breach of this invariant. The scheme is pinned to https: a
    plaintext request would put the token on the wire.

    Breaks when an implementer sends the token as a query parameter, which
    lands it in Google's request logs and in any proxy's.
    """
    transport = _Transport()

    read(_settings(), SENTINEL, tmp_path, client=transport)

    assert len(transport.requests) == 1, (
        f"expected exactly one request; got "
        f"{[(m, u) for m, u, _, _ in transport.requests]!r}"
    )
    method, url, _, headers = transport.requests[0]
    assert method == "POST", f"expected a POST; got {method!r} for {url!r}"
    assert url.startswith("https://analyticsdata.googleapis.com/"), (
        f"expected an https request to Google's analytics-data host; got {url!r}"
    )
    assert url.endswith(f"/properties/{PROPERTY}:runReport"), (
        f"expected a URL ending /properties/{PROPERTY}:runReport, naming the "
        f"property id from Settings; got {url!r}"
    )
    assert _authorization(headers) == f"Bearer {SENTINEL}", (
        f"expected the token as an Authorization: Bearer header; got "
        f"{_authorization(headers)!r} from headers {sorted(headers)!r}"
    )
    assert SENTINEL not in url, f"the token is in the URL: {url!r}"


# --------------------------------------------------------------- INV-4 ----


def test_request_body_asks_for_country_codes(tmp_path):
    """INV-4: the body asks for the last `days` days, dimension
    "countryId", metric "activeUsers", and metricAggregations ["TOTAL"].

    countryId, never country: countryId is ISO 3166-1 alpha-2, and the
    dashboard's flag pictures are keyed by those two-letter codes. "country"
    returns display names ("South Africa"), which are localised by Google to
    the caller's locale -- so an implementation using it looks correct here
    and hands the dashboard keys no flag file is named after.

    metricAggregations is what makes "totals" appear in the answer at all,
    so INV-5 has nothing to read without it.

    Breaks when an implementer hard-codes the window instead of
    interpolating `days`, which this test catches by asking for a
    non-default one.
    """
    transport = _Transport()

    read(_settings(), "a-token", tmp_path, days=7, client=transport)

    assert transport.requests, "no request was made at all"
    _, _, body, _ = transport.requests[0]
    assert body, "the request carried no body"
    payload = json.loads(body)

    assert payload.get("dateRanges") == [
        {"startDate": "7daysAgo", "endDate": "today"}
    ], (
        f"expected dateRanges [{{'startDate': '7daysAgo', 'endDate': "
        f"'today'}}] for days=7; got {payload.get('dateRanges')!r}"
    )
    assert payload.get("dimensions") == [{"name": "countryId"}], (
        f"expected dimensions [{{'name': 'countryId'}}] -- the ISO alpha-2 "
        f"code the flag pictures are keyed by, never the localised display "
        f"name from 'country'; got {payload.get('dimensions')!r}"
    )
    assert payload.get("metrics") == [{"name": "activeUsers"}], (
        f"expected metrics [{{'name': 'activeUsers'}}]; got "
        f"{payload.get('metrics')!r}"
    )
    assert payload.get("metricAggregations") == ["TOTAL"], (
        f"expected metricAggregations ['TOTAL'], without which Google's "
        f"answer carries no 'totals' block for INV-5 to read; got "
        f"{payload.get('metricAggregations')!r}"
    )


# --------------------------------------------------------------- INV-5 ----


def test_total_is_read_and_never_summed(tmp_path):
    """INV-5: Report.people comes from Google's "totals", not from summing
    the rows.

    The fixture's rows sum to 1500 while the total is 1200, which is the
    ordinary case rather than a contrived one: a visitor seen in two
    countries appears in both rows, so the sum overstates. A fixture where
    the two agree cannot tell the implementations apart.

    Breaks when an implementer adds the rows up because it is one line
    shorter than reaching into "totals" -- the resulting number is wrong in
    the writer's favour, which is the direction nobody questions.
    """
    transport = _Transport()

    report = _seed(tmp_path, transport)

    assert isinstance(report, Report), f"read() returned {report!r}, not a Report"
    row_sum = sum(people for _, people in ROWS)
    assert report.people == TOTAL, (
        f"expected people {TOTAL}, read from Google's 'totals'; got "
        f"{report.people} (the rows sum to {row_sum}, so {report.people} "
        f"means the rows were summed)"
    )
    assert report.days == DEFAULT_DAYS, (
        f"expected the report to name its window as {DEFAULT_DAYS} days; got "
        f"{report.days!r}"
    )


def test_answer_without_totals_is_refused(tmp_path):
    """INV-5: an answer carrying no "totals" is Google declining to name the
    total, and raises InsightsError.

    Breaks when an implementer falls back to summing the rows where "totals"
    is absent, which silently produces the overstated number INV-5 exists to
    keep out -- and produces it exactly when nobody can check it.
    """
    transport = _Transport(default=_ok(_google(total=None)))

    with pytest.raises(InsightsError):
        read(_settings(), "a-token", tmp_path, client=transport)


# --------------------------------------------------------------- INV-6 ----


def test_countries_are_ordered_and_aggregate_rows_dropped(tmp_path):
    """INV-6: Report.countries is ordered by people descending, and a row
    whose dimension value starts with "RESERVED_" is dropped.

    The fixture hands the rows in neither ascending nor descending order, so
    an implementation that passes them through unchanged fails. RESERVED_
    rows are Google's own aggregate markers -- shown as a country they read
    as a place with more readers than anywhere real.

    Breaks when an implementer sorts by country code, which looks ordered.
    """
    rows = (
        ("GB", 400),
        ("RESERVED_TOTAL", 5000),
        ("ZA", 900),
        ("US", 200),
    )
    transport = _Transport(default=_ok(_google(rows=rows)))

    report = read(_settings(), "a-token", tmp_path, client=transport)

    assert _codes(report) == ["ZA", "GB", "US"], (
        f"expected countries ['ZA', 'GB', 'US'] -- ordered by people "
        f"descending, with the RESERVED_ aggregate marker dropped; got "
        f"{_codes(report)!r}"
    )
    assert report.countries[0] == Country("ZA", 900), (
        f"expected the first country to be Country('ZA', 900); got "
        f"{report.countries[0]!r}"
    )


# --------------------------------------------------------------- INV-7 ----


def test_no_failure_names_the_token(tmp_path):
    """INV-7: no failure raised by this module carries the token, in its
    message or its representation.

    Forces every failure type this module can raise, with SENTINEL as the
    token each attempt is made with; asserts SENTINEL appears in neither
    str() nor repr() of what is raised.

    Breaks when an implementer includes the request headers in an error to
    make a failure diagnosable, and the token is a header. A dashboard
    failure is the kind a writer pastes into an issue.
    """
    messages: list[tuple[str, str]] = []

    def folder(name: str) -> Path:
        """A real, empty folder per attempt. Empty so nothing falls back to a
        cache (INV-12), and real so a faithful implementation looking for one
        fails on the attempt being made rather than on a missing directory."""
        made = tmp_path / name
        made.mkdir()
        return made

    def collect(kind, invoke):
        with pytest.raises(kind) as caught:
            invoke()
        messages.append((str(caught.value), repr(caught.value)))

    # NotConfigured -- no property id, so no request is made at all.
    collect(
        NotConfigured,
        lambda: read(
            _settings(analytics_property_id=None),
            SENTINEL,
            folder("declined"),
            client=_Transport(),
        ),
    )

    # Refused -- Google rejects the authorisation.
    collect(
        Refused,
        lambda: read(
            _settings(),
            SENTINEL,
            folder("refused"),
            client=_Transport(
                default=(401, {}, b'{"error": {"message": "Invalid Credentials"}}')
            ),
        ),
    )

    # RateLimited -- Google asks us to slow down, nothing cached.
    collect(
        RateLimited,
        lambda: read(
            _settings(),
            SENTINEL,
            folder("limited"),
            client=_Transport(
                default=(429, {}, b'{"error": {"message": "Quota exceeded"}}')
            ),
        ),
    )

    # Unreachable -- no answer at all, nothing cached.
    collect(
        Unreachable,
        lambda: read(
            _settings(),
            SENTINEL,
            folder("unreachable"),
            client=_Transport(unreachable=True),
        ),
    )

    # InsightsError -- an answer with no total in it.
    collect(
        InsightsError,
        lambda: read(
            _settings(),
            SENTINEL,
            folder("no-total"),
            client=_Transport(default=_ok(_google(total=None))),
        ),
    )

    leaked = [(text, shown) for text, shown in messages if SENTINEL in text or SENTINEL in shown]
    assert not leaked, f"a failure names the token: {leaked!r}"


# --------------------------------------------------------------- INV-8 ----


def test_cache_is_one_file_with_the_agreed_name(tmp_path):
    """INV-8: there is exactly one cache file, at
    cache_path(folder) == folder/"insights.json".

    The name is written out here rather than imported (see CACHE_FILE_NAME
    above): sharing the literal with the module would compare it against
    itself.

    Breaks when an implementer writes the reply beside a lock file or leaves
    the atomic-write temporary behind, either of which puts a file in the
    writer's folder that nothing later knows how to clean up.
    """
    folder = tmp_path / "state"
    folder.mkdir()

    assert cache_path(folder) == folder / CACHE_FILE_NAME, (
        f"expected the cache at {folder / CACHE_FILE_NAME}; got "
        f"{cache_path(folder)}"
    )

    _seed(folder, _Transport())

    left_behind = sorted(entry.name for entry in folder.iterdir())
    assert left_behind == [CACHE_FILE_NAME], (
        f"expected the folder to hold only {CACHE_FILE_NAME!r} after a read; "
        f"it holds {left_behind!r}"
    )


# --------------------------------------------------------------- INV-9 ----


def test_fresh_cache_answers_without_a_request(tmp_path):
    """INV-9: a cached reply younger than max_age_seconds answers with no
    request being made, and Report.stale is False.

    The second transport would answer if asked -- so this asserts silence,
    not failure. Its clock is ten seconds past the seed against a one-hour
    window.

    Breaks when an implementer reads the wall clock rather than the
    transport's now(): the seeded fetched_at is an epoch well in the past,
    so every cache reads as older than any real max_age and every read
    refetches -- a dashboard that asks Google again on every open.
    """
    _seed(tmp_path, _Transport(clock=NOW), max_age_seconds=3600.0)

    second = _Transport(clock=NOW + 10.0)
    report = read(
        _settings(), "a-token", tmp_path, max_age_seconds=3600.0, client=second
    )

    assert not second.requests, (
        f"a cache 10s old, against a 3600s window, still asked Google: "
        f"{[(m, u) for m, u, _, _ in second.requests]!r}"
    )
    assert report.people == TOTAL, (
        f"expected the cached people {TOTAL}; got {report.people}"
    )
    assert report.stale is False, (
        f"expected stale False for a cache well inside its window; got "
        f"{report.stale!r}"
    )


# -------------------------------------------------------------- INV-10 ----


def test_cache_for_another_window_does_not_answer(tmp_path):
    """INV-10: a cached reply for a different `days` window does not answer
    a request for this one.

    Breaks when an implementer keys the cache on the folder alone, which is
    the shortest thing that works -- and then a writer switching the
    dashboard from 28 days to 7 sees the 28-day numbers under a 7-day
    heading, with nothing anywhere saying so.
    """
    _seed(tmp_path, _Transport(clock=NOW), days=28, max_age_seconds=3600.0)

    seven = _Transport(
        default=_ok(_google(rows=(("ZA", 30),), total=44)), clock=NOW + 10.0
    )
    report = read(
        _settings(),
        "a-token",
        tmp_path,
        days=7,
        max_age_seconds=3600.0,
        client=seven,
    )

    assert seven.requests, (
        "a cache for the 28-day window answered a request for the 7-day "
        "window; no request was made"
    )
    assert report.people == 44, (
        f"expected the freshly fetched 7-day people 44; got {report.people} "
        f"({TOTAL} is the cached 28-day figure)"
    )
    assert report.days == 7, (
        f"expected the report to name its window as 7 days; got {report.days!r}"
    )


# -------------------------------------------------------------- INV-11 ----


def test_expired_cache_is_refetched_and_replaced(tmp_path):
    """INV-11: a cached reply older than max_age_seconds is refetched, and
    the fresh reply replaces the old one on disk.

    Replacement is checked by reading the cache file's bytes for the new
    total and for the absence of the old one. That is deliberately the only
    claim made about the file's contents -- not its shape, not its keys --
    because an implementation storing Google's reply verbatim and one
    storing a parsed structure both satisfy it, while an implementation that
    appends rather than replaces fails it.

    Breaks when an implementer refetches but writes nothing back, which
    passes every other cache test here and turns every dashboard open into a
    request Google eventually rate-limits.
    """
    _seed(tmp_path, _Transport(clock=NOW), max_age_seconds=3600.0)

    fresh_rows = (("ZA", 2000), ("GB", 700), ("US", 300))
    fresh_total = 3000
    second = _Transport(
        default=_ok(_google(rows=fresh_rows, total=fresh_total)),
        clock=NOW + 7200.0,
    )
    report = read(
        _settings(), "a-token", tmp_path, max_age_seconds=3600.0, client=second
    )

    assert second.requests, (
        "a cache 7200s old, against a 3600s window, was not refetched"
    )
    assert report.people == fresh_total, (
        f"expected the refetched people {fresh_total}; got {report.people}"
    )
    assert report.stale is False, (
        f"expected stale False for a successful refetch; got {report.stale!r}"
    )

    written = (tmp_path / CACHE_FILE_NAME).read_bytes()
    assert str(fresh_total).encode() in written, (
        f"the refetched total {fresh_total} is not in the cache file, so the "
        f"fresh reply was not written back: {written!r}"
    )
    assert str(TOTAL).encode() not in written, (
        f"the superseded total {TOTAL} is still in the cache file, so the "
        f"fresh reply was added beside the old one rather than replacing it: "
        f"{written!r}"
    )


# -------------------------------------------------------------- INV-12 ----


def test_failed_refetch_falls_back_to_the_cache(tmp_path):
    """INV-12: where the refetch fails and a cached reply for this window
    exists, read() returns the cached one with Report.stale True rather than
    raising.

    All three failure routes are exercised -- no answer, a refusal, and a
    rate limit -- because an implementation that catches OSError alone looks
    correct against the first and raises against the other two.

    stale True is half the invariant: numbers shown as current when they are
    a day old are worse than numbers labelled old, because the writer acts
    on them.

    Breaks when an implementer lets the typed failure out because a cache
    hit on the failure path is easy to forget -- and the dashboard then
    shows an error every time the writer's connection drops.
    """
    _seed(tmp_path, _Transport(clock=NOW), max_age_seconds=3600.0)

    failures = {
        "no answer at all": _Transport(unreachable=True, clock=NOW + 7200.0),
        "a refusal": _Transport(
            default=(403, {}, b'{"error": {"message": "forbidden"}}'),
            clock=NOW + 7200.0,
        ),
        "a rate limit": _Transport(
            default=(429, {}, b'{"error": {"message": "Quota exceeded"}}'),
            clock=NOW + 7200.0,
        ),
    }

    for description, transport in failures.items():
        report = read(
            _settings(), "a-token", tmp_path, max_age_seconds=3600.0, client=transport
        )
        assert report.people == TOTAL, (
            f"after a refetch that failed with {description}, expected the "
            f"cached people {TOTAL}; got {report.people}"
        )
        assert report.stale is True, (
            f"after a refetch that failed with {description}, expected stale "
            f"True; got {report.stale!r}"
        )
        assert _codes(report) == ["ZA", "GB", "US"], (
            f"after a refetch that failed with {description}, expected the "
            f"cached countries ['ZA', 'GB', 'US']; got {_codes(report)!r}"
        )


# -------------------------------------------------------------- INV-13 ----


def test_failed_refetch_without_a_cache_raises(tmp_path):
    """INV-13: where the refetch fails and nothing is cached, the typed
    failure is raised.

    The twin of INV-12, and the reason INV-12 cannot be satisfied by
    swallowing every failure: with no cache there is nothing truthful to
    return, so an empty Report reading zero readers would be a lie the
    dashboard shows without comment.
    """
    for name, transport, expected in (
        ("no answer at all", _Transport(unreachable=True), Unreachable),
        (
            "a refusal",
            _Transport(default=(403, {}, b'{"error": {"message": "forbidden"}}')),
            Refused,
        ),
        (
            "a rate limit",
            _Transport(default=(429, {}, b'{"error": {"message": "Quota"}}')),
            RateLimited,
        ),
    ):
        folder = tmp_path / name.replace(" ", "-")
        folder.mkdir()
        with pytest.raises(expected):
            read(_settings(), "a-token", folder, client=transport)


# -------------------------------------------------------------- INV-14 ----


def test_corrupt_cache_is_refetched_over(tmp_path):
    """INV-14: a corrupt cache file is ignored and refetched over, never
    fatal.

    What is written is not JSON at all, so this test assumes nothing about
    the cache's format -- the one place in this file that writes the cache
    file directly.

    A cache is a copy of something Google can be asked for again, so a
    half-written one -- a machine that lost power mid-write -- must cost a
    request and nothing else.

    Breaks when an implementer lets json.loads raise through read(), which
    leaves the writer with a dashboard that refuses to open until somebody
    who knows where the file lives deletes it.
    """
    (tmp_path / CACHE_FILE_NAME).write_bytes(b"{ this is not json at all")

    transport = _Transport()
    report = read(_settings(), "a-token", tmp_path, client=transport)

    assert transport.requests, "a corrupt cache was neither used nor refetched over"
    assert report.people == TOTAL, (
        f"expected the freshly fetched people {TOTAL}; got {report.people}"
    )
    assert report.stale is False, (
        f"expected stale False for a fresh fetch over a corrupt cache; got "
        f"{report.stale!r}"
    )


# -------------------------------------------------------------- INV-15 ----


def test_fetched_at_is_when_the_reply_was_fetched(tmp_path):
    """INV-15: Report.fetched_at is when the reply was fetched, not when it
    was read.

    Breaks when an implementer stamps the report at return time, which is
    indistinguishable from correct on a fresh fetch and wrong on every cache
    hit -- so the dashboard's "as of" line reads as current however old the
    numbers are, which is the same lie INV-12's stale flag exists to
    prevent.
    """
    first = _seed(tmp_path, _Transport(clock=NOW), max_age_seconds=3600.0)
    assert first.fetched_at == NOW, (
        f"expected fetched_at {NOW} on a fresh fetch; got {first.fetched_at}"
    )

    later = read(
        _settings(),
        "a-token",
        tmp_path,
        max_age_seconds=3600.0,
        client=_Transport(clock=NOW + 600.0),
    )
    assert later.fetched_at == NOW, (
        f"expected fetched_at {NOW} -- when the cached reply was FETCHED -- "
        f"on a read 600s later; got {later.fetched_at}"
    )


# -------------------------------------------------------------- INV-16 ----


def test_http_status_maps_to_the_typed_failure(tmp_path):
    """INV-16: 401 and 403 raise Refused, 429 raises RateLimited, a
    transport OSError raises Unreachable, and any other status raises
    InsightsError -- mirroring publisher.py's _failure().

    Each case runs against a folder with no cache, so nothing falls back
    (INV-12).

    The catch-all case asserts the failure is an InsightsError and none of
    the named subclasses. Asserting InsightsError alone would pass against
    an implementation that maps every status to Refused, since all of them
    are InsightsErrors.

    Breaks when an implementer maps 403 to a generic failure: 403 is what
    Google returns when the token is fine but does not reach this property,
    which is the writer's commonest setup mistake and the one the typed
    failure exists to name.
    """
    cases = (
        ("401", _Transport(default=(401, {}, b'{"error": {"message": "no"}}')), Refused),
        ("403", _Transport(default=(403, {}, b'{"error": {"message": "no"}}')), Refused),
        (
            "429",
            _Transport(default=(429, {}, b'{"error": {"message": "slow down"}}')),
            RateLimited,
        ),
        ("OSError", _Transport(unreachable=True), Unreachable),
    )

    for name, transport, expected in cases:
        folder = tmp_path / f"status-{name}"
        folder.mkdir()
        with pytest.raises(expected) as caught:
            read(_settings(), "a-token", folder, client=transport)
        assert type(caught.value) is expected, (
            f"{name} raised {type(caught.value).__name__}, not "
            f"{expected.__name__}"
        )

    folder = tmp_path / "status-500"
    folder.mkdir()
    with pytest.raises(InsightsError) as caught:
        read(
            _settings(),
            "a-token",
            folder,
            client=_Transport(default=(500, {}, b'{"error": {"message": "boom"}}')),
        )
    assert not isinstance(caught.value, (Refused, RateLimited, Unreachable, NotConfigured)), (
        f"500 raised {type(caught.value).__name__}, which names a cause "
        f"Google did not give; an unrecognised status is a plain InsightsError"
    )


# ------------------------------------------------------------ PRESS-0039 ----


def test_cache_reaches_the_disk_before_the_rename(tmp_path, monkeypatch):
    """INV-8's rename is what keeps a reader from seeing a half-written cache,
    and a rename alone does not survive a power loss.

    Asserting the ORDER is the whole test: the file left on disk is identical
    whether or not the temporary was synced, so nothing read back can tell a
    durable write from one whose blocks are still in the kernel's cache.

    Breaks when the cache is renamed unsynced, which can leave an empty file
    that the next read has to treat as corrupt and refetch over.
    """
    folder = tmp_path / "state"
    folder.mkdir()

    events = _watch_durability(monkeypatch)
    try:
        _seed(folder, _Transport())
    finally:
        monkeypatch.undo()

    _assert_synced_before_replace(events, "the cache write")


def test_cache_names_the_line_endings(tmp_path, monkeypatch):
    """design.md § Persistence: UTF-8, and LF line endings written explicitly.

    Asserting what the write NAMED rather than the bytes it produced:
    os.linesep is "\\n" on the machine running this suite, so a write that left
    the newline to the platform produces the same bytes here as one that named
    it, and a byte-level assertion passes against the defect it exists to
    catch.

    Breaks when the cache temporary is opened without newline="\\n", which
    writes CRLF on Windows.
    """
    folder = tmp_path / "state"
    folder.mkdir()

    opens = _watch_opens(monkeypatch)
    try:
        _seed(folder, _Transport())
    finally:
        monkeypatch.undo()

    writing = [record for record in opens if record.writes() and not record.binary]
    assert writing, "no text write was recorded at all -- the watch did not fire"
    unnamed = [record for record in writing if record.newline != "\n"]
    assert not unnamed, (
        f"the cache write named newline {[record.newline for record in unnamed]!r}; "
        f"the line endings must be named so the file does not depend on which "
        f"system wrote it"
    )
