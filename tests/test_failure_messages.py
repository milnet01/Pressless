# PRESS-0117: no failure message names a full filesystem path.
#
# docs/design.md § Logging forbids a credential, an account name either
# secret is filed under, or a full filesystem path in anything Pressless
# shows or writes down, and puts the obligation on the part that RAISES
# rather than on the Face. A path names the writer -- it carries his home
# directory -- and the log is what he sends to whoever helps him.
#
# Why this file exists rather than an assertion inside each module's own
# tests: the rule is one rule across every part, and a scattered assertion
# proves each message clean without ever proving the RULE holds. Here the
# walk is the test, so a part that gains a message gains a row.
#
# The two modules covered are the ones whose contracts pin no path, so
# their messages were changed with no spec amendment. Credentials and
# Settings are PRESS-0001 and PRESS-0002's, whose §4 tables now name the
# file by what it is; Store, pages and packaging still carry the breach
# and are PRESS-0117's remainder.
#
# NOT ASSERTED, deliberately: that a message is useful. Anonymity and
# diagnosability trade against each other, and this file holds only the
# side that can be checked mechanically.
import os
import re
from pathlib import Path

import pytest
from test_insights import _settings as _insights_settings
from test_publisher import (
    _blob_hash,
    _listing,
    _reads,
    _settings,
    _Transport,
    _writes,
)

from pressless.insights import InsightsError
from pressless.insights import read as insights_read
from pressless.publisher import (
    FetchNotWritten,
    PublishError,
    SiteFolderMissing,
    SiteWouldBeEmptied,
    fetch_previous,
    publish,
)

# An absolute POSIX path: a slash that opens the string or follows a space
# or a quote, then a segment, then another slash. A site-relative path like
# `content/index.html` has no leading slash and is deliberately allowed --
# it names a place inside the folder he chose, never where that folder is.
_ABSOLUTE = re.compile(r"(?:^|[\s'\"(])(?:/[A-Za-z0-9_.-]+){2,}")


def _refuse_a_path(what: str, message: str, folder: Path) -> None:
    """Fail if `message` names `folder`, or any absolute path at all."""
    assert str(folder) not in message, (
        f"{what} names the folder it was handed: {message!r}. "
        f"docs/design.md § Logging forbids a full filesystem path in "
        f"anything Pressless shows or writes down -- it carries his home "
        f"directory, and the log is what he sends to whoever helps him."
    )
    found = _ABSOLUTE.search(message)
    assert found is None, (
        f"{what} carries the absolute path {found.group(0)!r} in "
        f"{message!r}. A location is named by what it is, never spelled."
    )


def test_no_publisher_failure_names_a_path(tmp_path):
    """Every message the Publisher raises about a folder names no path.

    Walks the four sites that interpolated one: the site folder that is not
    a directory, the publish that would empty the site, the fetch area that
    cannot be written, and the local file that cannot be read. The last two
    also carried the OSError's own words, which quote the path it failed on
    -- a second leak by a different route, and the reason `_why` reports the
    reason alone.

    Breaks when an implementer puts the folder back to make a failure
    diagnosable. That is the trade this rule already refused: § Errors hands
    the real path over through a copy button, which the Face owns.
    """
    messages: list[tuple[str, str]] = []

    def collect(kind, invoke):
        with pytest.raises(kind) as caught:
            invoke()
        messages.append((kind.__name__, str(caught.value)))

    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html>site</html>", encoding="utf-8")
    listing = _listing([("index.html", _blob_hash(b"<html>old</html>"))])

    # The handed folder is not a directory.
    collect(
        SiteFolderMissing,
        lambda: publish(
            _settings(),
            tmp_path / "not-a-directory",
            "a-token",
            "a commit message",
            transport=_Transport(reads=_reads(listing), writes=_writes()),
        ),
    )

    # Every unprotected path removed and none written.
    empty = tmp_path / "empty"
    empty.mkdir()
    collect(
        SiteWouldBeEmptied,
        lambda: publish(
            _settings(),
            empty,
            "a-token",
            "a commit message",
            transport=_Transport(
                reads=_reads(
                    _listing(
                        [
                            ("CNAME", _blob_hash(b"a-domain.example.test\n")),
                            ("index.html", _blob_hash(b"<html>site</html>")),
                        ]
                    )
                ),
                writes=_writes(),
            ),
        ),
    )

    # The fetch area cannot be created: a file already stands where the
    # folder must go, so mkdir raises the OSError the site reports.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a folder", encoding="utf-8")
    collect(
        FetchNotWritten,
        lambda: fetch_previous(
            _settings(),
            "a-token",
            blocked,
            transport=_Transport(
                reads=_reads(
                    _listing([("index.html", "some-blob-sha")]),
                    blob=b"<html>previous</html>",
                )
            ),
        ),
    )

    for kind, message in messages:
        _refuse_a_path(f"{kind} from the Publisher", message, tmp_path)


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root reads a mode-000 file, so nothing fails"
)
def test_an_unreadable_site_file_names_no_path(tmp_path):
    """The site file that cannot be read is named relative to the folder.

    Its own site had the absolute path AND the OSError's words, which name
    the file a second time. `relative` is what the writer recognises and it
    identifies nobody.

    Breaks when an implementer reaches for the loop's `path` rather than its
    `relative`, which is the nearer variable and reads as equivalent.
    """
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html>site</html>", encoding="utf-8")
    secret = site / "unreadable.html"
    secret.write_text("<html>cannot be read</html>", encoding="utf-8")
    secret.chmod(0o000)

    try:
        with pytest.raises(PublishError) as caught:
            publish(
                _settings(),
                site,
                "a-token",
                "a commit message",
                transport=_Transport(
                    reads=_reads(
                        _listing([("index.html", _blob_hash(b"<html>old</html>"))])
                    ),
                    writes=_writes(),
                ),
            )
    finally:
        secret.chmod(0o600)

    message = str(caught.value)
    _refuse_a_path("PublishError for an unreadable site file", message, tmp_path)
    assert "unreadable.html" in message, (
        f"the message must still say WHICH file could not be read; it said "
        f"{message!r}. Anonymity is the path, never the name he gave it."
    )


def test_no_insights_failure_names_a_path(tmp_path):
    """The cache folder inside the site folder is refused without a path.

    Insights keeps one cache file, and a cache inside the site folder would
    put country-level readership on a public site. The refusal named the
    folder, which is where Pressless sits on his machine.

    Breaks when an implementer interpolates the folder to say which one was
    wrong. There is only one candidate, so the sentence does not need it.
    """
    site = tmp_path / "site"
    site.mkdir()
    inside = site / "cache"
    inside.mkdir()

    with pytest.raises(InsightsError) as caught:
        insights_read(
            _insights_settings(site_folder=site),
            "a-token",
            inside,
            days=7,
        )

    _refuse_a_path("InsightsError from Insights", str(caught.value), tmp_path)
