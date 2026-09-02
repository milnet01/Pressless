"""Insights — asking Google Analytics how the site is being read.

The contract is roadmap item PRESS-0019; its invariants are written down in
tests/test_insights.py's header, there being no docs/specs file for it. This
module imports no other part of Pressless than Settings (INV-1): it is handed
the Google access token as an argument and never reaches Credentials, which is
what keeps docs/design.md rule 10 true. Obtaining and refreshing that token is
setup's work, not this module's.

It answers one question — how many people read the site over the last so many
days, and from which countries — and it is the one part of Pressless allowed a
cache (ADR-0005, docs/design.md § State), because Google limits how often it
will answer. The cache is one file, it holds the last reply with the time it
was fetched, and deleting it costs nothing but a fresh fetch.

Nothing about writing or publishing may depend on any of this (docs/design.md
rule 8). A writer who declines the Google step loses the dashboard and nothing
else, which is why an absent property id is its own typed failure rather than
an error about the network.

Every failure is one of the typed exceptions below and none of them carries the
token (INV-7). The Face turns each into the three-part sentence
docs/design.md § Errors requires; this module writes none of them.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pressless.settings import Settings

API = "https://analyticsdata.googleapis.com/v1beta"

# The cache is one file, in Pressless's own folder — never the site folder,
# which is published in full (docs/design.md § Where everything sits on disk).
CACHE_NAME = "insights.json"
CACHE_VERSION = 1

# Four weeks. Long enough that a quiet week does not read as a dead site, short
# enough to still be about now; well inside Google's own data retention. The
# window is a parameter so the dashboard can offer others without changing this
# part.
DEFAULT_DAYS = 28

# An hour between fetches. Google meters this API per property per hour, and a
# dashboard the writer opens repeatedly must not spend that budget on answers
# that have not changed. Deliberately conservative: one refetch an hour is a
# rounding error against the quota, and the reply carries when it was fetched
# so nothing is passed off as newer than it is.
DEFAULT_MAX_AGE = 3600.0

# Google returns aggregate rows — the metricAggregations we asked for — in the
# rows themselves, marked in the dimension rather than separated out. They are
# not countries.
AGGREGATE_PREFIX = "RESERVED_"

# Every request carries this, so a black-holed connection fails instead of
# hanging forever (PRESS-0041). It bounds each socket operation rather than
# the whole request, so a large upload that keeps making progress is not cut
# off.
TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Country:
    code: str      # ISO 3166-1 alpha-2, which the flag pictures are keyed by
    people: int


@dataclass(frozen=True)
class Report:
    people: int                     # Google's own total, never the rows summed
    countries: tuple[Country, ...]  # most-read first
    days: int                       # the window this answers for
    fetched_at: float               # when Google answered, not when this was read
    stale: bool                     # True where Google could not be reached and
                                    # this is the last answer we kept


class InsightsError(Exception):
    """Anything this module refuses to act on."""


class NotConfigured(InsightsError):
    """No Analytics property id in Settings — the writer declined the dashboard."""


class Unreachable(InsightsError):
    """No answer from Google."""


class Refused(InsightsError):
    """Google rejected the authorisation, or it does not reach this property."""


class RateLimited(InsightsError):
    """Google asked us to slow down."""


class Transport(Protocol):
    """The one seam. Tests are its only other caller.

    Two things about it are part of the contract, because a test double must
    supply both. It returns the response HEADERS alongside the status, and it
    signals *no answer* by raising OSError — every HTTP status, error statuses
    included, is RETURNED rather than raised, so this module owns the mapping
    to the types above.

    And `now` is the clock. Nothing here reads the wall clock directly, so a
    test decides whether a cache is fresh by moving the double's clock rather
    than by waiting.
    """

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]
                ) -> tuple[int, dict[str, str], bytes]: ...

    def now(self) -> float: ...


class _NoCrossOriginAuth(urllib.request.HTTPRedirectHandler):
    """A redirect handler that drops the key when the origin changes.

    urllib copies every header but the content ones onto a redirect target,
    a different host included, and follows up to ten hops -- so a redirect
    would hand the Authorization header to whoever answered (PRESS-0052).
    Neither service Pressless talks to legitimately redirects across
    origins; a same-origin redirect keeps the header, so a renamed
    repository still resolves.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers,
                                              newurl)
        if redirected is None:
            return None
        if _origin(newurl) != _origin(req.full_url):
            redirected.remove_header("Authorization")
        return redirected


def _origin(url: str) -> tuple[str, str]:
    """Scheme, host and port -- the whole origin.

    So a downgrade to cleartext, and a hop to another port on the same
    machine, are both changes of origin. netloc carries the port.
    """
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme, parsed.netloc)


class _Urllib:
    """The module's own client, used when no double is handed in.

    urllib.request rather than a third-party HTTP library, for the reason
    publisher.py gives: PRESS-0022 has to carry every dependency into a
    packaged artefact, and a convenience library here would be one bought for
    syntax.
    """

    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._opener = urllib.request.build_opener(_NoCrossOriginAuth)

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]
                ) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(url, data=body, headers=headers,
                                         method=method)
        try:
            with self._opener.open(request,
                                   timeout=self._timeout) as response:
                return (response.status, dict(response.headers),
                        response.read())
        except urllib.error.HTTPError as error:
            # An error STATUS is an answer, so it is returned rather than
            # raised -- only a genuine absence of one reaches the caller as
            # OSError, which is what the seam promises.
            return (error.code, dict(error.headers or {}), error.read())

    def now(self) -> float:
        return time.time()


def cache_path(folder: Path) -> Path:
    return Path(folder) / CACHE_NAME


def read(settings: Settings, token: str, folder: Path, *,
         days: int = DEFAULT_DAYS,
         max_age_seconds: float = DEFAULT_MAX_AGE,
         client: Transport | None = None) -> Report:
    """How the site was read over the last `days` days.

    Answers from the cache while it is younger than `max_age_seconds` and was
    fetched for this same window; otherwise asks Google. Where Google cannot
    answer and a cached reply for this window exists, that reply is returned
    with `stale` set rather than raising — a dashboard showing yesterday's
    numbers, labelled, beats one showing an error.
    """
    property_id = settings.analytics_property_id
    if not property_id:
        # Checked before anything else: a writer who declined the dashboard is
        # told he declined it, not that his connection is down, and no request
        # is made on his behalf (INV-2).
        raise NotConfigured(
            "no Analytics property id in Settings, so the dashboard was "
            "never set up"
        )

    transport = client if client is not None else _Urllib()
    target = cache_path(folder)
    cached = _cached(target, days)

    if cached is not None and transport.now() - cached.fetched_at < max_age_seconds:
        return cached

    try:
        report = _fetch(transport, property_id, token, days)
    except InsightsError:
        if cached is not None:
            return Report(cached.people, cached.countries, cached.days,
                          cached.fetched_at, True)
        raise

    _store(target, report)
    return report


def _fetch(transport: Transport, property_id: str, token: str,
           days: int) -> Report:
    """One request, and one is the whole of it — there is no retry.

    A rate limit is what the cache exists for, so answering it with more
    requests is the opposite of the design.
    """
    url = f"{API}/properties/{property_id}:runReport"
    body = json.dumps({
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
        # countryId, never country: the first is the ISO alpha-2 code the flag
        # pictures are keyed by, the second is a localised display name.
        "dimensions": [{"name": "countryId"}],
        "metrics": [{"name": "activeUsers"}],
        # Without this Google's answer carries no total, and summing the rows
        # counts a visitor seen in two countries twice.
        "metricAggregations": ["TOTAL"],
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Pressless",
    }

    when = transport.now()
    try:
        status, _, data = transport.request("POST", url, body, headers)
    except OSError as exc:
        raise Unreachable("no answer from Google") from exc

    if status != 200:
        raise _failure(status)

    answer = _parse(data)
    return Report(_total(answer), _countries(answer), days, when, False)


def _failure(status: int) -> InsightsError:
    """The typed failure for an HTTP status. Never names the token.

    401 and 403 are one answer to the writer — the authorisation Pressless
    holds does not open this property — and 403 is the commoner of the two,
    being what Google returns for a valid token pointed at somebody else's
    property.
    """
    if status in (401, 403):
        return Refused(f"Google refused the authorisation ({status})")
    if status == 429:
        return RateLimited("Google asked us to slow down")
    return InsightsError(f"Google answered {status}")


def _total(answer: dict) -> int:
    """Google's own total for the window.

    Read rather than summed: the per-country rows count a visitor seen in two
    countries once each, so they add up to more than the number of people.
    """
    totals = answer.get("totals")
    if not isinstance(totals, list) or not totals:
        raise InsightsError("Google's answer does not name a total")
    return _number(totals[0], "the total")


def _countries(answer: dict) -> tuple[Country, ...]:
    rows = answer.get("rows") or []
    if not isinstance(rows, list):
        raise InsightsError("Google's answer does not list countries")

    found = []
    for row in rows:
        code = _code(row)
        if code.startswith(AGGREGATE_PREFIX):
            continue
        found.append(Country(code, _number(row, f"the count for {code}")))
    # Most-read first; ties by code, so the order is the same on every fetch.
    return tuple(sorted(found, key=lambda country: (-country.people, country.code)))


def _code(row: dict) -> str:
    values = row.get("dimensionValues") if isinstance(row, dict) else None
    if not isinstance(values, list) or not values:
        raise InsightsError("Google's answer has a row naming no country")
    value = values[0].get("value") if isinstance(values[0], dict) else None
    if not isinstance(value, str) or not value:
        raise InsightsError("Google's answer has a row naming no country")
    return value


def _number(holder: dict, what: str) -> int:
    values = holder.get("metricValues") if isinstance(holder, dict) else None
    if not isinstance(values, list) or not values:
        raise InsightsError(f"Google's answer does not give {what}")
    raw = values[0].get("value") if isinstance(values[0], dict) else None
    try:
        # Google sends integer metrics as strings; float() first accepts the
        # decimal form its schema also permits.
        return int(float(raw))
    except (TypeError, ValueError) as exc:
        raise InsightsError(f"Google's answer does not give {what}") from exc


def _parse(data: bytes) -> dict:
    try:
        parsed = json.loads(data or b"{}")
    except ValueError as exc:
        raise InsightsError(f"Google's answer is not valid JSON: {exc}") from exc
    return parsed if isinstance(parsed, dict) else {}


def _cached(target: Path, days: int) -> Report | None:
    """The last reply for this window, or None.

    Anything unreadable, unparsable or written for another window reads as
    None: the cache is a copy of something Google can be asked for again, so a
    half-written one costs a request and nothing else (INV-14).
    """
    try:
        data = target.read_bytes()
    except OSError:
        return None
    try:
        held = json.loads(data)
    except ValueError:
        return None
    if not isinstance(held, dict) or held.get("version") != CACHE_VERSION:
        return None
    if held.get("days") != days:
        # A 28-day cache must not answer a 7-day question, or the writer reads
        # one window's numbers under the other's heading.
        return None
    try:
        countries = tuple(
            Country(str(entry["code"]), int(entry["people"]))
            for entry in held["countries"]
        )
        return Report(int(held["people"]), countries, int(held["days"]),
                      float(held["fetched_at"]), False)
    except (KeyError, TypeError, ValueError):
        return None


def _store(target: Path, report: Report) -> None:
    """Replace the cache with this reply, leaving nothing else in the folder.

    The same write settings.py makes: a temporary in the same directory, then
    a rename over the target, so a reader never sees a half-written file and
    nothing is left behind (INV-8). A cache that cannot be written is not
    worth failing a fetch over — the numbers in hand are still good.
    """
    data = {
        "version": CACHE_VERSION,
        "days": report.days,
        "fetched_at": report.fetched_at,
        "people": report.people,
        "countries": [
            {"code": country.code, "people": country.people}
            for country in report.countries
        ],
    }
    try:
        handle, temporary = tempfile.mkstemp(
            dir=str(target.parent), prefix=".insights-", suffix=".tmp"
        )
    except OSError:
        return
    try:
        # newline is named rather than left to the platform, so the cache is
        # the same bytes on both systems (PRESS-0039).
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            # rename(2) orders the namespace, not the data, so without
            # this a power loss can commit the rename before the blocks
            # and leave an empty file where INV-8 promises a whole file (PRESS-0039).
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError:
        _discard(temporary)
    except BaseException:
        _discard(temporary)
        raise


def _discard(temporary: str) -> None:
    try:
        os.unlink(temporary)
    except OSError:
        pass
