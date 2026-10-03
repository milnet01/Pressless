# The dashboard (PRESS-0020): how many people read the site, and from where.
#
# No spec: the roadmap item is the contract, and these tests lock its parts.
# Google is a recording double answering by address, and the credential store
# is a recording double: no test reaches Google or the machine's keyring.
from __future__ import annotations

import contextlib
import dataclasses
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser

from pressless import credentials, dashboard, face, google_setup, google_signin, settings

REFRESH = "1//SENTINELrefresh0123456789"
COUNTRIES = (("ZA", 7), ("US", 3), ("(not set)", 1))


class _Google:
    """Answers the token refresh and the report. `down` makes every request
    the seam's no-answer."""

    def __init__(self, *, rows=COUNTRIES, total: int = 10, report_status: int = 200) -> None:
        self.clock = 1000.0
        self.rows = rows
        self.total = total
        self.report_status = report_status
        self.down = False
        self.reports: list[dict] = []
        self.requests = 0

    def request(self, method, url, body, headers):
        self.requests += 1
        if self.down:
            raise OSError("no answer")
        if url.startswith("https://oauth2.googleapis.com/token"):
            return 200, {}, json.dumps({"access_token": "access-token",
                                        "expires_in": 3600}).encode()
        if url.endswith(":batchRunReports"):
            self.reports.append(json.loads(body)["requests"][0])
            if self.report_status != 200:
                return self.report_status, {}, b"{}"
            rows = [{"dimensionValues": [{"value": code}], "metricValues": [{"value": str(n)}]}
                    for code, n in self.rows]
            countries = {"rows": rows,
                         "totals": [{"metricValues": [{"value": str(self.total)}]}]}
            answer = {"reports": [countries, {}, {}, {}]}
            return 200, {}, json.dumps(answer).encode()
        return 404, {}, b""

    def now(self) -> float:
        return self.clock

    def windows_asked(self) -> list[str]:
        return [report["dateRanges"][0]["startDate"] for report in self.reports]


class _Browser(Browser):
    def get(self, path: str) -> str:
        status, _, page = self.request("GET", path)
        assert status == 200, status
        return page

    def card(self) -> str:
        return "".join(self.served.list_pieces(above=True))


def _seen(page: str) -> str:
    """The words a reader sees: tags dropped, spaces closed up."""
    return " ".join(re.sub(r"<[^>]+>", " ", page).split()).replace(" .", ".")


@contextlib.contextmanager
def _served(folder: Path, google: _Google) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        google_setup.register(served, folder, client=google)
        dashboard.register(served, folder, client=google)
        yield _Browser(served)
    finally:
        served.stop()


def _saved(folder: Path, *, signed_in: bool = True) -> None:
    settings.save(folder, settings.Settings(
        site_folder=folder / "site",
        repository="owner/owner.github.io",
        site_name="A Journal",
        site_address="https://example.org",
        daily_prompt_filter="",
        untouchable=(),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account="google" if signed_in else None),
        analytics_property_id="999" if signed_in else None,
    ))


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(google_signin, "CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setattr(google_signin, "CLIENT_SECRET", "sentinel-client-secret")
    monkeypatch.setattr(credentials, "read", lambda kind, folder, account: REFRESH)


def test_only_the_three_windows_are_ever_asked_for(tmp_path: Path) -> None:
    """PRESS-0019 § 4.2 requires a fixed, small set. Breaks when a days value
    from the address reaches Google as it was typed."""
    _saved(tmp_path)
    google = _Google()
    with _served(tmp_path, google) as browser:
        page = browser.get("/visitors")
        assert 'aria-current="page">Last 4 weeks<' in page
        for days in ("7", "365", "90", "-1", "abc", "28"):
            browser.get(f"/visitors?days={days}")
    assert google.windows_asked() == ["28daysAgo", "7daysAgo", "365daysAgo"]
    assert set(google.windows_asked()) == {f"{d}daysAgo" for d, _, _ in dashboard.WINDOWS}


def test_flags_are_pictures_and_countries_have_names(tmp_path: Path) -> None:
    """Breaks when a flag is drawn as a flag character, which Windows shows as
    two letters, or a country shows as its code."""
    _saved(tmp_path)
    with _served(tmp_path, _Google()) as browser:
        page = browser.get("/visitors")
    assert "10 people read your site in the last 4 weeks." in _seen(page)
    assert '<a href="/">Back to your writing</a>' in page
    assert page.count('src="data:image/svg+xml;base64,') == 2
    assert "South Africa" in page and "United States of America" in page
    assert "Somewhere Google could not tell" in page
    assert not any(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in page)
    assert page.index("South Africa") < page.index("United States of America")


def test_every_flag_unpacks_and_has_a_name() -> None:
    """Breaks when the generated data loses a picture or a name."""
    pictures = dashboard._pictures()
    assert set(pictures) == set(dashboard._flag_data.NAMES)
    assert {"ZA", "GB", "US", "DE"} <= set(pictures)
    assert all(svg.startswith("<svg") for svg in pictures.values())


@pytest.mark.parametrize(("total", "rows", "words"), [
    (1, (("ZA", 1),), "1 person read your site"),
    (0, (), "Nobody read your site in the last 4 weeks"),
])
def test_one_reader_and_none(tmp_path: Path, total: int, rows, words: str) -> None:
    """Breaks on "1 people", or on a quiet window shown as an error."""
    _saved(tmp_path)
    with _served(tmp_path, _Google(total=total, rows=rows)) as browser:
        page = browser.get("/visitors")
    assert words in _seen(page)
    assert ("Where they are" in page) == bool(rows)


def test_turned_off_shows_the_way_on_and_asks_nobody(tmp_path: Path) -> None:
    """ADR-0005: declining loses only the dashboard. Breaks when the page asks
    Google anyway, or offers no way to turn it on."""
    _saved(tmp_path, signed_in=False)
    google = _Google()
    with _served(tmp_path, google) as browser:
        page = browser.get("/visitors")
        assert browser.card() == ""
    assert 'href="/setup/google"' in page and "Visitor numbers are off" in page
    assert google.requests == 0


def test_unreachable_google_shows_the_numbers_kept(tmp_path: Path) -> None:
    """Breaks when no token can be had and the page shows an error over
    numbers it holds, or shows them without saying they are old."""
    _saved(tmp_path)
    google = _Google()
    with _served(tmp_path, google) as browser:
        browser.get("/visitors")
        google.clock += 2 * 3600       # the held token and the cache are both old
        google.down = True
        page = browser.get("/visitors")
    assert "could not reach Google just now" in page
    assert "10 people read your site" in _seen(page)
    assert "South Africa" in page


def test_unreachable_with_nothing_kept_is_a_failure_not_a_blank(tmp_path: Path) -> None:
    _saved(tmp_path)
    google = _Google()
    google.down = True
    with _served(tmp_path, google) as browser:
        page = browser.get("/visitors?days=7")
    assert 'class="failure' in page
    assert "people read your site" not in page


def test_a_refused_sign_in_offers_signing_in_again(tmp_path: Path) -> None:
    """Breaks when Google's refusal leaves him no route back."""
    _saved(tmp_path)
    with _served(tmp_path, _Google(report_status=403)) as browser:
        page = browser.get("/visitors")
    assert 'class="failure' in page
    assert f'<a href="{google_setup.PAGE}">sign in again</a>' in page


def test_the_card_reads_the_cache_and_never_google(tmp_path: Path) -> None:
    """ADR-0005: the list never waits on Google. Breaks when drawing the card
    makes a request."""
    _saved(tmp_path)
    google = _Google()
    with _served(tmp_path, google) as browser:
        before = browser.card()
        assert google.requests == 0
        assert 'href="/visitors">See who is reading your site<' in before
        browser.get("/visitors")
        asked = google.requests
        after = browser.card()
        assert google.requests == asked
    assert "10 people read your site in the last 4 weeks, as of" in after


def test_a_kept_report_is_marked_stale(tmp_path: Path) -> None:
    _saved(tmp_path)
    with _served(tmp_path, _Google()) as browser:
        browser.get("/visitors")
    kept = dashboard._kept(tmp_path, 28)
    assert kept is not None and kept.stale and kept.people == 10
    assert dataclasses.replace(kept, stale=False) == dashboard.insights._cached(
        dashboard.insights.cache_path(tmp_path), 28)
