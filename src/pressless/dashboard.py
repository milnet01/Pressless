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
from pressless.words import say

PAGE = "/visitors"

# (days, the button's key, the sentence's key). 28 is Insights' default.
WINDOWS = (
    (7, "dashboard.window.7", "dashboard.window.7.phrase"),
    (28, "dashboard.window.28", "dashboard.window.28.phrase"),
    (365, "dashboard.window.365", "dashboard.window.365.phrase"),
)
DEFAULT_DAYS = insights.DEFAULT_DAYS

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


def _sign_in_again() -> str:
    return f'<p>{say("dashboard.sign_in_again", page=google_setup.PAGE)}</p>'


def register(face: Face, folder: Path, *,
             client: insights.Transport | None = None) -> None:
    """Add the dashboard page, and its card at the top of the list. `client`
    is the Transport double a test hands in, as `google_setup.register` takes."""
    folder = Path(folder)
    face.add_page("GET", PAGE,
                  lambda request: _show(face, folder, request, client)
                  + f'<p><a href="/">{say("script.undo.back")}</a></p>')
    face.add_to_list(lambda: _card(face, folder), above=True)


def _days(raw: str) -> int:
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_DAYS
    return days if any(days == window[0] for window in WINDOWS) else DEFAULT_DAYS


def _sentence(days: int) -> str:
    return say(next(key for count, _, key in WINDOWS if count == days))


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
        line = say("dashboard.card.ask", page=PAGE)
    else:
        line = say("dashboard.card.read", people=_people(kept.people),
                   window=_sentence(DEFAULT_DAYS), when=_when(kept.fetched_at), page=PAGE)
    return f'<section class="card"><h2>{say("dashboard.title")}</h2><p>{line}</p></section>'


# ---------------------------------------------------------------- the page ----


def _show(face: Face, folder: Path, request: Request,
          client: insights.Transport | None) -> str:
    days = _days(request.query.get("days", ""))
    saved, shown = _settings(face, folder)
    head = _STYLE + f'<h1>{say("dashboard.title")}</h1>'
    if saved is None:
        return shown + head + f'<p>{say("setup.first")}</p>'
    if not _set_up(saved):
        return shown + head + f'<p>{say("dashboard.off", page=google_setup.PAGE)}</p>'
    head += _windows(days)
    try:
        token = google_setup.token(folder)
    except insights.Unreachable as exc:
        report = _kept(folder, days)
        if report is None:
            return shown + head + face.fail(exc, publishing=False)
    except (insights.InsightsError, *google_setup._CREDENTIAL_FAILURES) as exc:
        return (shown + head
                + face.fail(exc, publishing=False, secret=say("failure.secret.google_sign_in"))
                + _sign_in_again())
    else:
        try:
            report = insights.read(saved, token, folder, days=days, client=client)
        except insights.Refused as exc:
            return (shown + head
                    + face.fail(exc, publishing=False, secret=say("failure.secret.google_sign_in"))
                    + _sign_in_again())
        except insights.InsightsError as exc:
            return shown + head + face.fail(exc, publishing=False)
    return shown + head + _report(report, saved.site_address)


def _windows(days: int) -> str:
    links = []
    for count, key, _ in WINDOWS:
        label = say(key)
        if count == days:
            links.append(f'<strong aria-current="page">{label}</strong>')
        else:
            links.append(f'<a href="{PAGE}?days={count}">{label}</a>')
    return f'<p class="windows">{"".join(links)}</p>'


def _report(report: insights.Report, address: str = "") -> str:
    fetched = _when(report.fetched_at)
    if report.stale:
        when = f'<p>{say("dashboard.stale", when=fetched)}</p>'
    else:
        when = f'<p>{say("dashboard.updated", when=fetched)}</p>'
    window = _sentence(report.days)
    if report.people == 0:
        count = say("dashboard.count.none", window=window)
    else:
        key = "dashboard.count.one" if report.people == 1 else "dashboard.count.many"
        count = say(key, count=f"{report.people:,}", window=window)
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
        tip = say("dashboard.day", day=_day_name(day.label),
                  people=_people(day.people) if day.people else say("dashboard.nobody"))
        none = ' class="none"' if day.people == 0 else ""
        bars.append(f'<li{none} tabindex="0" data-tip="{html.escape(tip, quote=True)}" '
                    f'aria-label="{html.escape(tip, quote=True)}" '
                    f'style="--h:{100 * day.people / top:.1f}%;--d:{min(i, 60) * 12}ms"></li>')
    by = say("dashboard.each_month" if len(days[0].label) == 7 else "dashboard.each_day")
    by = html.escape(by, quote=True)
    return (f'<ol class="strip" aria-label="{by}">{"".join(bars)}</ol>'
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
    return _panel(say("dashboard.where"),
                 f'<th scope="col">{say("dashboard.country")}</th>'
                 f'<th scope="col" class="num">{say("dashboard.people")}</th>', rows)


# Google's channel groups, and the keys of his words for them. Anything new
# falls back to Google's.
_CHANNELS = {
    "Organic Search": "dashboard.channel.organic_search",
    "Paid Search": "dashboard.channel.paid_search",
    "Direct": "dashboard.channel.direct",
    "Referral": "dashboard.channel.referral",
    "Organic Social": "dashboard.channel.organic_social",
    "Paid Social": "dashboard.channel.paid_social",
    "Email": "dashboard.channel.email",
    "Organic Video": "dashboard.channel.organic_video",
    "Unassigned": "dashboard.channel.unassigned",
}


def _sources(sources: tuple[insights.Source, ...]) -> str:
    if not sources:
        return ""
    top = max(source.visits for source in sources)
    rows = []
    for source in sources:
        key = _CHANNELS.get(source.channel)
        how = html.escape(say(key) if key else source.channel)
        where = "" if source.source in ("(direct)", "(not set)", "") else source.source
        if source.channel.endswith("Search") and "." not in where:
            where = where.title()   # "google" is an engine's name, so "Google"
        detail = f"<small>{html.escape(where)}</small>" if where else ""
        rows.append(f"<tr><td>{how}{detail}{_meter(source.visits, top)}</td>"
                    f'<td class="num">{source.visits:,}</td>'
                    f'<td class="num">{source.people:,}</td></tr>')
    return _panel(say("dashboard.how"),
                 f'<th scope="col">{say("dashboard.came_from")}</th>'
                 f'<th scope="col" class="num">{say("dashboard.visits")}</th>'
                 f'<th scope="col" class="num">{say("dashboard.people")}</th>', "".join(rows))


def _pages(pages: tuple[insights.Page, ...], address: str) -> str:
    if not pages:
        return ""
    top = max(page.views for page in pages)
    base = address.rstrip("/")
    rows = []
    views = html.escape(say("dashboard.views"), quote=True)
    people = html.escape(say("dashboard.people"), quote=True)
    spent = html.escape(say("dashboard.time_on_page"), quote=True)
    for page in pages:
        shown = html.escape(page.path)
        link = (f'<a href="{html.escape(base + page.path, quote=True)}" target="_blank" '
                f'rel="noopener">{shown}</a>' if base and page.path.startswith("/") else shown)
        rows.append(f"<tr><td>{link}{_meter(page.views, top)}</td>"
                    f'<td class="num" data-label="{views}">{page.views:,}</td>'
                    f'<td class="num" data-label="{people}">{page.people:,}</td>'
                    f'<td class="num" data-label="{spent}">'
                    f"{_duration(page.seconds)}</td></tr>")
    return _panel(say("dashboard.what"),
                 f'<th scope="col">{say("dashboard.page")}</th>'
                 f'<th scope="col" class="num">{views}</th>'
                 f'<th scope="col" class="num">{people}</th>'
                 f'<th scope="col" class="num">{spent}</th>', "".join(rows), wide=True)


def _duration(seconds: float) -> str:
    whole = round(seconds)
    if whole <= 0:
        return "–"
    minutes, rest = divmod(whole, 60)
    if minutes:
        return say("dashboard.minutes", minutes=str(minutes), seconds=f"{rest:02d}")
    return say("dashboard.seconds", seconds=str(rest))


def _people(count: int) -> str:
    if count == 1:
        return say("dashboard.people.one")
    return say("dashboard.people.many", count=f"{count:,}")


def _when(moment: float) -> str:
    local = time.localtime(moment)
    return say("dashboard.when", date=time.strftime("%d %b %Y", local),
               clock=time.strftime("%H:%M", local))


def _name(code: str) -> str:
    if code == insights.UNKNOWN_COUNTRY:
        return say("dashboard.unknown_country")
    return say("country." + code) if code in _flag_data.NAMES else code


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
