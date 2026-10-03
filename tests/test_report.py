"""PRESS-0179: a "Suggest or report a problem" page that opens a ready-filled
issue on GitHub and sends nothing itself.

The repository and the security route are written out here rather than
imported, so a module naming another repository fails.
"""
from __future__ import annotations

import html
import platform
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from test_face import _Client

from pressless import __version__, face, report, settings, store

SENTINEL = "zqxsentinelzqx"


def _page(folder: Path) -> str:
    served = face.serve(folder)
    try:
        report.register(served)
        status, _, body = _Client(served).request("GET", "/report")
    finally:
        served.stop()
    assert status == 200
    return body


def _issue_link(body: str) -> urllib.parse.SplitResult:
    hrefs = [html.unescape(href) for href in re.findall(r'href="([^"]+)"', body)]
    return next(urllib.parse.urlsplit(href) for href in hrefs if "/issues/new" in href)


def test_the_issue_is_ready_filled_and_carries_nothing_of_theirs(tmp_path):
    """Breaks when the link names another repository, drops the version, the
    system or the blanks, or carries the site's address or an entry."""
    store.write(tmp_path, store.Entry(
        slug="seaside", title=SENTINEL, date=datetime(2020, 1, 2, 3, 4, 5),
        categories=(), tags=(), body=SENTINEL, extra=()), draft=False)
    settings.save(tmp_path, settings.Settings(
        site_folder=tmp_path / "site", repository=f"owner/{SENTINEL}",
        site_address=f"https://{SENTINEL}.example.org",
        daily_prompt_filter="", untouchable=("CNAME",),
        credentials=settings.Credentials(store="keyring", github_account="github",
                                         google_account=None),
        analytics_property_id=None))
    store.write_identity(tmp_path, store.Identity(SENTINEL))
    body = _page(tmp_path)
    link = _issue_link(body)
    assert (link.scheme, link.netloc, link.path) == (
        "https", "github.com", "/milnet01/Pressless/issues/new")
    query = urllib.parse.parse_qs(link.query)
    assert set(query) == {"title", "body"}
    text = query["body"][0]
    assert f"Pressless {__version__}" in text
    assert platform.system() in text
    for blank in ("What I pressed", "What I expected", "What I saw"):
        assert blank in text
    assert SENTINEL not in body


def test_it_says_the_issue_is_public_and_points_security_elsewhere(tmp_path):
    """Breaks when the page drops the warning or the private route."""
    body = _page(tmp_path)
    assert "public" in body
    assert 'href="https://github.com/milnet01/Pressless/security/advisories/new"' in body
