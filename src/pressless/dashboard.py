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
_STYLE = ("<style>.face .visitors-count { font-size: 1.6rem; margin: .5rem 0; }"
          ".face .windows a, .face .windows strong { margin-right: 1rem; }"
          ".face .countries img { width: 1.6em; height: 1.2em; vertical-align: -.2em;"
          " margin-right: .6em; border: 1px solid var(--line); }"
          ".face .countries td:last-child, .face .countries th:last-child"
          " { text-align: right; padding-right: 0; }</style>")
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
    return shown + head + _report(report)


def _windows(days: int) -> str:
    links = []
    for count, label, _ in WINDOWS:
        if count == days:
            links.append(f'<strong aria-current="page">{label}</strong>')
        else:
            links.append(f'<a href="{PAGE}?days={count}">{label}</a>')
    return f'<p class="windows">{"".join(links)}</p>'


def _report(report: insights.Report) -> str:
    if report.stale:
        when = (f"<p>Pressless could not reach Google just now, so these are the "
                f"numbers from {_when(report.fetched_at)}.</p>")
    else:
        when = f"<p>Last updated {_when(report.fetched_at)}.</p>"
    if report.people == 0:
        count = f"Nobody read your site in {_sentence(report.days)}, as far as Google can tell."
    else:
        count = f"{_people(report.people)} read your site in {_sentence(report.days)}."
    page = f'<p class="visitors-count">{count}</p>' + when
    if report.countries:
        rows = "".join(f"<tr><td>{_flag(country.code)}{html.escape(_name(country.code))}</td>"
                       f"<td>{country.people:,}</td></tr>"
                       for country in report.countries)
        page += ('<section class="card"><h2>Where they are</h2><table class="countries">'
                 '<thead><tr><th scope="col">Country</th><th scope="col">People</th>'
                 f"</tr></thead><tbody>{rows}</tbody></table></section>")
    return page


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
