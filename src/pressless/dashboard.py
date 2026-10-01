"""The dashboard (PRESS-0020): how many people read the site, and from where.

A Face page. It asks `google_setup.token` for an access token and
`insights.read` for the numbers, and turns every failure into the Face's
sentence. Nothing about writing or publishing depends on it (ADR-0005): the
card it adds to the list reads only the cache, so the list never waits on
Google.

It offers three windows and no others, which is the fixed, small set
PRESS-0019 § 4.2 requires of it: the cache keeps one reply per window asked
for, and nothing else bounds it. A `days` value outside the set is answered
as the default rather than passed on.

Flags are pictures from `_flag_data`, never flag characters, because Windows
draws a flag character as its two letters (docs/design.md § The dashboard).
"""

from __future__ import annotations

import base64
import dataclasses
import functools
import html
import json
import time
import zlib
from pathlib import Path

from pressless import _flag_data, google_setup, insights, settings
from pressless.face import Face, Request, render_notices

PAGE = "/visitors"

# (days, the button's words, the sentence's words). 28 is Insights' default.
WINDOWS = (
    (7, "Last 7 days", "the last 7 days"),
    (28, "Last 4 weeks", "the last 4 weeks"),
    (365, "Last 12 months", "the last 12 months"),
)
DEFAULT_DAYS = insights.DEFAULT_DAYS

_UNKNOWN_NAME = "Somewhere Google could not tell"
# Theme colours only, so the page follows whichever look he picked. One
# movement: the bars grow in once, and not at all where motion is turned down.
_STYLE = """<style>
.face .windows a, .face .windows strong { margin-right: 1rem; }
.face .visitors-count { font-size: 1.35rem; margin: .5rem 0 0; display: flex;
  align-items: baseline; flex-wrap: wrap; gap: .2rem .7rem; }
.face .visitors-count b { font: 700 clamp(3rem, 9vw, 4.75rem)/1 Arial, Calibri,
  "Liberation Sans", Helvetica, sans-serif; color: var(--amber-ink);
  font-variant-numeric: tabular-nums; }
.face .strip { list-style: none; display: flex; align-items: flex-end; gap: 3px;
  height: 9rem; margin: 1.5rem 0 .4rem; padding: 0; border-bottom: 2px solid var(--line); }
.face .strip li { flex: 1; height: var(--h); min-height: 4px; position: relative;
  background: var(--amber); border-radius: 5px 5px 0 0; transform-origin: bottom;
  animation: pl-grow .6s cubic-bezier(.2, .8, .2, 1) both; animation-delay: var(--d); }
.face .strip li.none { background: var(--line); }
.face .strip li:hover, .face .strip li:focus { outline: 2px solid var(--ink);
  outline-offset: 2px; }
.face .strip li:hover::after, .face .strip li:focus::after { content: attr(data-tip);
  position: absolute; bottom: calc(100% + .5rem); left: 50%; transform: translateX(-50%);
  white-space: nowrap; background: var(--ink); color: var(--paper); padding: .35rem .7rem;
  border-radius: 8px; font-size: 1rem; z-index: 2; }
.face .strip li:nth-child(-n+4)::after { left: 0; transform: none; }
.face .strip li:nth-last-child(-n+4)::after { left: auto; right: 0; transform: none; }
.face .strip-ends { display: flex; justify-content: space-between; color: var(--soft); }
.face .reading { display: grid; gap: 0 1.25rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 24rem), 1fr)); }
.face .reading .wide { grid-column: 1 / -1; }
.face .ranked { width: 100%; }
.face .ranked th, .face .ranked td { padding-right: 1rem; }
.face .ranked .num { text-align: right; font-variant-numeric: tabular-nums;
  white-space: nowrap; }
.face .ranked th:last-child, .face .ranked td:last-child { padding-right: 0; }
.face .ranked td:first-child { overflow-wrap: anywhere; }
.face .ranked img { width: 1.6em; height: 1.2em; vertical-align: -.2em;
  margin-right: .6em; border: 1px solid var(--line); border-radius: 3px; }
.face .ranked small { display: block; }
.face .meter { display: block; height: .5rem; margin-top: .4rem; border-radius: 99px;
  background: var(--line); overflow: hidden; }
.face .meter i { display: block; height: 100%; width: var(--w); background: var(--amber);
  border-radius: inherit; transform-origin: left; animation: pl-fill .7s ease-out both; }
@media (max-width: 40rem) {
  .face .pages thead { display: none; }
  .face .pages tr { display: flex; flex-wrap: wrap; gap: 0 1rem;
    border-bottom: 1px solid var(--line); padding: .4rem 0; }
  .face .pages td { border: 0; padding: 0; }
  .face .pages td:first-child { flex: 0 0 100%; margin-bottom: .3rem; }
  .face .pages td.num::before { content: attr(data-label) " "; color: var(--soft); } }
@keyframes pl-grow { from { transform: scaleY(0); } }
@keyframes pl-fill { from { transform: scaleX(0); } }
@media (prefers-reduced-motion: reduce) {
  .face .strip li, .face .meter i { animation: none; } }
</style>"""
_BACK = '<p><a href="/">Back to your writing</a></p>'
_SIGN_IN_AGAIN = (f'<p>If Google no longer accepts the sign-in, '
                  f'<a href="{google_setup.PAGE}">sign in again</a>.</p>')


def register(face: Face, folder: Path, *,
             client: insights.Transport | None = None) -> None:
    """Add the dashboard page, and its card at the top of the list. `client`
    is the Transport double a test hands in, as `google_setup.register` takes."""
    folder = Path(folder)
    face.add_page("GET", PAGE,
                  lambda request: _show(face, folder, request, client) + _BACK)
    face.add_to_list(lambda: _card(face, folder), above=True)


def _days(raw: str) -> int:
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_DAYS
    return days if any(days == window[0] for window in WINDOWS) else DEFAULT_DAYS


def _sentence(days: int) -> str:
    return next(words for count, _, words in WINDOWS if count == days)


def _settings(face: Face, folder: Path) -> tuple[settings.Settings | None, str]:
    with face.capture() as notices:
        try:
            saved = settings.load(folder)
        except (settings.NotSetUp, settings.SettingsError):
            saved = None
    return saved, render_notices(notices)


def _set_up(saved: settings.Settings) -> bool:
    return bool(saved.analytics_property_id) and saved.credentials.google_account is not None


def _kept(folder: Path, days: int) -> insights.Report | None:
    """The last reply kept for this window, marked stale, or None.

    For when no token can be had because Google cannot be reached: Insights
    answers from its cache only where it was handed a token, so the page asks
    the cache itself rather than show an error over numbers it holds.
    """
    kept = insights._cached(insights.cache_path(folder), days)
    return dataclasses.replace(kept, stale=True) if kept is not None else None


# ---------------------------------------------------------------- the card ----


def _card(face: Face, folder: Path) -> str:
    """The list's card. Reads the cache and never Google, so the list does not
    wait on the network (ADR-0005)."""
    saved, _ = _settings(face, folder)
    if saved is None or not _set_up(saved):
        return ""
    kept = insights._cached(insights.cache_path(folder), DEFAULT_DAYS)
    if kept is None:
        line = f'<a href="{PAGE}">See who is reading your site</a>'
    else:
        line = (f"{_people(kept.people)} read your site in "
                f"{_sentence(DEFAULT_DAYS)}, as of {_when(kept.fetched_at)}. "
                f'<a href="{PAGE}">See where they are</a>')
    return f'<section class="card"><h2>Who is reading</h2><p>{line}</p></section>'


# ---------------------------------------------------------------- the page ----


def _show(face: Face, folder: Path, request: Request,
          client: insights.Transport | None) -> str:
    days = _days(request.query.get("days", ""))
    saved, shown = _settings(face, folder)
    head = _STYLE + "<h1>Who is reading</h1>"
    if saved is None:
        return (shown + head + "<p>Set up Pressless first, "
                '<a href="/setup">on the setup page</a>.</p>')
    if not _set_up(saved):
        return (shown + head + "<p>Visitor numbers are off. Pressless can read them "
                "from Google Analytics if you sign in with Google: "
                f'<a href="{google_setup.PAGE}">turn on visitor numbers</a>.</p>')
    head += _windows(days)
    try:
        token = google_setup.token(folder)
    except insights.Unreachable as exc:
        report = _kept(folder, days)
        if report is None:
            return shown + head + face.fail(exc, publishing=False)
    except (insights.InsightsError, *google_setup._CREDENTIAL_FAILURES) as exc:
        return (shown + head + face.fail(exc, publishing=False, secret=google_setup.SIGN_IN)
                + _SIGN_IN_AGAIN)
    else:
        try:
            report = insights.read(saved, token, folder, days=days, client=client)
        except insights.Refused as exc:
            return (shown + head + face.fail(exc, publishing=False, secret=google_setup.SIGN_IN)
                    + _SIGN_IN_AGAIN)
        except insights.InsightsError as exc:
            return shown + head + face.fail(exc, publishing=False)
    return shown + head + _report(report, saved.site_address)


def _windows(days: int) -> str:
    links = []
    for count, label, _ in WINDOWS:
        if count == days:
            links.append(f'<strong aria-current="page">{label}</strong>')
        else:
            links.append(f'<a href="{PAGE}?days={count}">{label}</a>')
    return f'<p class="windows">{"".join(links)}</p>'


def _report(report: insights.Report, address: str = "") -> str:
    if report.stale:
        when = (f"<p>Pressless could not reach Google just now, so these are the "
                f"numbers from {_when(report.fetched_at)}.</p>")
    else:
        when = f"<p>Last updated {_when(report.fetched_at)}.</p>"
    if report.people == 0:
        count = f"Nobody read your site in {_sentence(report.days)}, as far as Google can tell."
    else:
        noun = "person" if report.people == 1 else "people"
        count = (f"<b>{report.people:,}</b> <span>{noun} read your site in "
                 f"{_sentence(report.days)}.</span>")
    page = f'<p class="visitors-count">{count}</p>' + _strip(report.daily) + when
    cards = [_countries(report.countries), _sources(report.sources),
             _pages(report.pages, address)]
    return page + '<div class="reading">' + "".join(cards) + "</div>"


def _strip(days: tuple[insights.Day, ...]) -> str:
    """One bar per day (per month for a long window), tallest = busiest."""
    if not days:
        return ""
    top = max(day.people for day in days) or 1
    bars = []
    for i, day in enumerate(days):
        tip = f"{_day_name(day.label)}: {_people(day.people) if day.people else 'nobody'}"
        none = ' class="none"' if day.people == 0 else ""
        bars.append(f'<li{none} tabindex="0" data-tip="{html.escape(tip, quote=True)}" '
                    f'aria-label="{html.escape(tip, quote=True)}" '
                    f'style="--h:{100 * day.people / top:.1f}%;--d:{min(i, 60) * 12}ms"></li>')
    by = "month" if len(days[0].label) == 7 else "day"
    return (f'<ol class="strip" aria-label="People each {by}">{"".join(bars)}</ol>'
            f'<p class="strip-ends"><span>{_day_name(days[0].label)}</span>'
            f"<span>{_day_name(days[-1].label)}</span></p>")


def _day_name(label: str) -> str:
    try:
        if len(label) == 7:
            return time.strftime("%b %Y", time.strptime(label, "%Y-%m"))
        moment = time.strptime(label, "%Y-%m-%d")
        return f"{time.strftime('%a', moment)} {moment.tm_mday} {time.strftime('%b', moment)}"
    except ValueError:
        return label


def _meter(value: int, top: int) -> str:
    return f'<span class="meter"><i style="--w:{100 * value / (top or 1):.1f}%"></i></span>'


def _panel(title: str, head: str, rows: str, wide: bool = False) -> str:
    kind, table = ("card wide", "ranked pages") if wide else ("card", "ranked")
    return (f'<section class="{kind}"><h2>{title}</h2><table class="{table}">'
            f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></section>")


def _countries(countries: tuple[insights.Country, ...]) -> str:
    if not countries:
        return ""
    top = max(country.people for country in countries)
    rows = "".join(
        f"<tr><td>{_flag(country.code)}{html.escape(_name(country.code))}"
        f"{_meter(country.people, top)}</td><td class=\"num\">{country.people:,}</td></tr>"
        for country in countries)
    return _panel("Where they are",
                 '<th scope="col">Country</th><th scope="col" class="num">People</th>', rows)


# Google's channel groups, in his words. Anything new falls back to Google's.
_CHANNELS = {
    "Organic Search": "A search engine",
    "Paid Search": "A search advert",
    "Direct": "Typed the address or used a bookmark",
    "Referral": "A link on another site",
    "Organic Social": "Social media",
    "Paid Social": "A social media advert",
    "Email": "An email",
    "Organic Video": "A video site",
    "Unassigned": "Google could not tell",
}


def _sources(sources: tuple[insights.Source, ...]) -> str:
    if not sources:
        return ""
    top = max(source.visits for source in sources)
    rows = []
    for source in sources:
        how = html.escape(_CHANNELS.get(source.channel, source.channel))
        where = "" if source.source in ("(direct)", "(not set)", "") else source.source
        if source.channel.endswith("Search") and "." not in where:
            where = where.title()   # "google" is an engine's name, so "Google"
        detail = f"<small>{html.escape(where)}</small>" if where else ""
        rows.append(f"<tr><td>{how}{detail}{_meter(source.visits, top)}</td>"
                    f'<td class="num">{source.visits:,}</td>'
                    f'<td class="num">{source.people:,}</td></tr>')
    return _panel("How they found you",
                 '<th scope="col">Came from</th><th scope="col" class="num">Visits</th>'
                 '<th scope="col" class="num">People</th>', "".join(rows))


def _pages(pages: tuple[insights.Page, ...], address: str) -> str:
    if not pages:
        return ""
    top = max(page.views for page in pages)
    base = address.rstrip("/")
    rows = []
    for page in pages:
        shown = html.escape(page.path)
        link = (f'<a href="{html.escape(base + page.path, quote=True)}" target="_blank" '
                f'rel="noopener">{shown}</a>' if base and page.path.startswith("/") else shown)
        rows.append(f"<tr><td>{link}{_meter(page.views, top)}</td>"
                    f'<td class="num" data-label="Views">{page.views:,}</td>'
                    f'<td class="num" data-label="People">{page.people:,}</td>'
                    f'<td class="num" data-label="Time on page">'
                    f"{_duration(page.seconds)}</td></tr>")
    return _panel("What they read",
                 '<th scope="col">Page</th><th scope="col" class="num">Views</th>'
                 '<th scope="col" class="num">People</th>'
                 '<th scope="col" class="num">Time on page</th>', "".join(rows), wide=True)


def _duration(seconds: float) -> str:
    whole = round(seconds)
    if whole <= 0:
        return "–"
    minutes, rest = divmod(whole, 60)
    return f"{minutes}m {rest:02d}s" if minutes else f"{rest}s"


def _people(count: int) -> str:
    return "1 person" if count == 1 else f"{count:,} people"


def _when(moment: float) -> str:
    return time.strftime("%d %b %Y at %H:%M", time.localtime(moment))


def _name(code: str) -> str:
    if code == insights.UNKNOWN_COUNTRY:
        return _UNKNOWN_NAME
    return _flag_data.NAMES.get(code, code)


def _flag(code: str) -> str:
    """The flag as an inline picture, or nothing where there is none."""
    picture = _pictures().get(code)
    if picture is None:
        return ""
    encoded = base64.b64encode(picture.encode("utf-8")).decode("ascii")
    return f'<img src="data:image/svg+xml;base64,{encoded}" alt="">'


@functools.cache
def _pictures() -> dict[str, str]:
    """Unpacked once, on the first flag drawn, not at launch."""
    return json.loads(zlib.decompress(base64.b64decode(_flag_data.PACKED)))
