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
# The Publisher, Insights and the Store are walked here; the Store's rule is
# PRESS-0005 § 4.4 and PRESS-0006 § 4.4. Credentials and Settings are
# walked in their own suites, against PRESS-0001 and PRESS-0002's § 4
# tables. Packaging is not built yet, so it has nothing to walk.
#
# NOT ASSERTED, deliberately: that a message is useful. Anonymity and
# diagnosability trade against each other, and this file holds only the
# side that can be checked mechanically.
import json
import os
import re
from dataclasses import replace
from datetime import datetime, timezone
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
from test_store import _wide_grant

from pressless import store
from pressless.insights import InsightsError
from pressless.insights import read as insights_read
from pressless.publisher import (
    Conflict,
    FetchNotWritten,
    PublishError,
    RateLimited,
    Refused,
    RemoteStateMissing,
    RepositoryMissing,
    SiteFolderMissing,
    SiteWouldBeEmptied,
    TooLarge,
    Unreachable,
    fetch_previous,
    publish,
)
from pressless.store import EntryNotFound, SlugInUse, StoreError, StoreNotice

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


def test_no_store_failure_names_a_path(tmp_path, monkeypatch):
    """Every message the Store raises or warns with names no path.

    PRESS-0005 § 4.4 and PRESS-0006 § 4.4 put the rule on the Store: an entry
    is named by its slug, any other file by its own name, and an `OSError` by
    its reason. One site per kind of failure the Store reports, its notices
    included -- a notice reaches the log exactly as a failure does.

    Every offender is collected before the assertion, so a red run names
    each site at once rather than the first.

    Breaks when an implementer interpolates `target` to say which file
    failed. The file's own name already says that, and says nothing about
    where Pressless sits on his machine.
    """
    folder = tmp_path / "pressless"
    folder.mkdir()
    messages: list[tuple[str, str]] = []

    def failure(what, invoke, kind=StoreError):
        with pytest.raises(kind) as caught:
            invoke()
        messages.append((what, str(caught.value)))

    def notice(what, invoke):
        with pytest.warns(StoreNotice) as caught:
            invoke()
        messages.extend((what, str(w.message)) for w in caught)

    def put(relative: str, data: bytes) -> Path:
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    entry = folder / "published" / "an-entry.txt"
    failure("a missing entry", lambda: store.read(entry), EntryNotFound)
    for what, data in (
        ("an entry that is not UTF-8", b"Slug: an-entry\n\n\xff"),
        ("an entry with no blank line", b"Slug: an-entry"),
        ("a header line with no colon", b"Slug an-entry\n\nbody"),
        ("an entry with no Slug", b"Date: 2026-01-01 00:00:00\n\nbody"),
        ("an entry whose Slug is illegal", b"Slug: An_Entry\n\nbody"),
        ("an entry with no Date", b"Slug: an-entry\n\nbody"),
        ("an entry with a malformed Date", b"Slug: an-entry\nDate: soon\n\nbody"),
        ("an entry named unlike its Slug",
         b"Slug: another\nDate: 2026-01-01 00:00:00\n\nbody"),
    ):
        put("published/an-entry.txt", data)
        failure(what, lambda: store.read(entry))
    entry.unlink()

    failure("a handed folder that is not one",
            lambda: store.list_slugs(tmp_path / "absent", draft=False))
    failure("publishing a draft that is not there",
            lambda: store.publish(folder, "no-such-entry"), EntryNotFound)

    good = store.Entry(
        slug="taken", title="", date=datetime(2026, 1, 1), categories=(),
        tags=(), body="body", extra=(),
    )
    store.write(folder, good, draft=True)
    store.write(folder, good, draft=False)
    failure("publishing onto a slug already published",
            lambda: store.publish(folder, "taken"), SlugInUse)

    def no_hard_links(source, target):
        raise OSError(1, "Operation not permitted", str(source))

    store.write(folder, replace(good, slug="stuck"), draft=True)
    monkeypatch.setattr(store.os, "link", no_hard_links)
    failure("a move on a filesystem with no hard links",
            lambda: store.publish(folder, "stuck"))
    monkeypatch.undo()

    def full_disk(*args, **kwargs):
        raise OSError(28, "No space left on device", str(folder))

    monkeypatch.setattr(store.tempfile, "mkstemp", full_disk)
    failure("a write onto a full disk",
            lambda: store.write(folder, replace(good, slug="full"), draft=True))
    monkeypatch.undo()

    page = store.html_path_for(folder, "pages", "about")
    failure("a missing page", lambda: store.read_html(page))
    put("pages/about.html", b"\xff")
    failure("a page that is not UTF-8", lambda: store.read_html(page))

    comments = store.comments_path_for(folder, "an-entry")
    record = {"identifier": "1", "author": "a reader", "author_url": "",
              "date": "2026-01-01 00:00:00", "body": "a comment", "parent": ""}
    for what, carried in (
        ("comments that are not JSON", b"{"),
        ("comments that are not a list", b"{}"),
        ("a comment that is not an object", b"[1]"),
        ("a comment carrying an extra field",
         json.dumps([{**record, "email": "x"}]).encode()),
        ("a comment missing a field",
         json.dumps([{k: v for k, v in record.items() if k != "body"}]).encode()),
    ):
        put("comments/an-entry.json", carried)
        failure(what, lambda: store.read_comments(comments))

    one = store.Comment(identifier="1", author="a reader", author_url="",
                        date=datetime(2026, 1, 1), body="a comment", parent="")
    for what, kind, carried in (
        ("a reply to a comment that is absent", store.DanglingReply,
         (replace(one, parent="9"),)),
        ("a comment with no identifier", StoreError, (replace(one, identifier=""),)),
        ("two comments sharing an identifier", StoreError, (one, one)),
        ("a comment date carrying a zone", StoreError,
         (replace(one, date=datetime(2026, 1, 1, tzinfo=timezone.utc)),)),
    ):
        failure(
            what,
            lambda carried=carried: store.write_comments(folder, "an-entry", carried),
            kind,
        )

    put("drafts/unusable_name.txt", b"")
    notice("a listing passing a file over",
           lambda: store.list_slugs(folder, draft=True))
    (folder / "drafts" / "unusable_name.txt").unlink()

    store.write(folder, replace(good, slug="twin"), draft=True)
    put("published/twin.TXT", b"Slug: twin\n\nbody")
    notice("a move stranding a second file",
           lambda: store.publish(folder, "twin"))

    _wide_grant(monkeypatch)
    notice("a write the mount would not make private",
           lambda: store.write(folder, replace(good, slug="wide"), draft=True))

    offenders = [
        (what, message) for what, message in messages
        if str(tmp_path) in message or _ABSOLUTE.search(message)
    ]
    assert not offenders, (
        "docs/design.md § Logging forbids a full filesystem path in anything "
        "Pressless shows or writes down, and PRESS-0005 § 4.4 puts that on the "
        "Store. These messages name one:\n"
        + "\n".join(f"  {what}: {message!r}" for what, message in offenders)
    )


def test_no_publisher_failure_names_the_account(tmp_path):
    """No Publisher message names the account a repository sits under.

    docs/design.md § Logging: a repository is named by its short name, never
    `account/name`. Every request URL carries `repos/<account>/<name>`, and
    these messages quoted the URL whole, so each named the account his site
    is published under -- which identifies him as surely as a path does.

    Breaks when an implementer puts the URL back in a message to make a
    failure diagnosable. The method and what was asked for say which request
    failed; the account adds nothing but him.
    """
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html>new</html>", encoding="utf-8")
    listing = _listing([("index.html", _blob_hash(b"<html>old</html>"))])
    branch = ("/repos/", (200, {}, json.dumps({"default_branch": "main"}).encode()))

    def answer(status, headers=None):
        return (status, headers or {}, b"{}")

    def raised(kind, reads, writes=None, **failing):
        with pytest.raises(kind) as caught:
            publish(
                _settings(), site, "a-token", "a commit message",
                transport=_Transport(reads=reads, writes=writes or _writes(),
                                     **failing),
            )
        return kind.__name__, str(caught.value)

    messages = [
        raised(Refused, [("/repos/", answer(401))]),
        raised(RepositoryMissing, [("/repos/", answer(404))]),
        raised(RemoteStateMissing, [("/commits/", answer(404)), branch]),
        raised(TooLarge, [("/commits/", answer(413)), branch]),
        raised(PublishError, [("/commits/", answer(502)), branch]),
        raised(RateLimited, [("/repos/", answer(429, {"retry-after": "99999"}))]),
        raised(Unreachable, _reads(listing), fail_at="/repos/", fail_on_read=True),
        raised(Conflict, _reads(listing),
               writes=[("/git/refs", answer(409))] + _writes()),
    ]

    offenders = [(kind, message) for kind, message in messages if "owner/" in message]
    assert not offenders, (
        "docs/design.md § Logging names a repository by its short name, never "
        "account/name. These Publisher messages name the account:\n"
        + "\n".join(f"  {kind}: {message!r}" for kind, message in offenders)
    )
