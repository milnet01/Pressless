# INV-1..11 for PRESS-0006 (the rest of the Store: fixed pages, furniture,
# templates, comments, and where a photograph's original sits). One test per
# invariant, named in that spec's §5 and §10. Unlabelled: it needs nothing but a
# temporary directory and always runs (§7), unlike the conformance run against
# the real export, which lives in tests/test_store_extras_archive.py.
#
# Why this exists: docs/specs/PRESS-0006-pages-furniture-comments.md is the
# contract.
from __future__ import annotations

import ast
import dataclasses
import inspect
import os
from datetime import datetime
from pathlib import Path

import pytest
from _open_watch import _watch_opens

import pressless.store as store_module
from pressless.store import (
    FURNITURE_NAMES,
    Comment,
    DanglingReply,
    Entry,
    StoreError,
    comments_path_for,
    html_path_for,
    list_slugs,
    photograph_path_for,
    read_comments,
    read_html,
    template_path_for,
    write,
    write_comments,
    write_html,
    write_template,
)

# The documented folder names, suffixes and furniture names (§4.1, §4.3),
# written out here rather than imported from the module under test. Sharing the
# literal would have the module compared against itself: PAGES_FOLDER could name
# anything at all and every assertion below would stay green. Do not tidy these
# into imports.
_PAGES = "pages"
_FURNITURE = "furniture"
_TEMPLATES = "templates"
_COMMENTS = "comments"
_PHOTOGRAPHS = "photographs"
_PUBLISHED = "published"
_DRAFTS = "drafts"
_HTML_SUFFIX = ".html"
_COMMENTS_SUFFIX = ".json"
_ENTRY_SUFFIX = ".txt"
_FURNITURE_NAMES = ("header", "footer", "navigation")

# Naive on purpose: §4.2 writes a comment's date in the entry Date format, which
# is `YYYY-MM-DD HH:MM:SS` and carries no zone.
_A_DATE = datetime(2014, 11, 9, 21, 32, 0)  # noqa: DTZ001 -- see above


def _entry(slug: str = "an-example", **overrides) -> Entry:
    """PRESS-0005 §4.1's Entry, valid unless an override makes it otherwise."""
    fields = {
        "slug": slug,
        "title": "An example",
        "date": _A_DATE,
        "categories": ("poetry",),
        "tags": ("one", "two"),
        "body": "The body starts here.\n",
        "extra": (),
    }
    fields.update(overrides)
    return Entry(**fields)


def _comment(identifier: str = "1", **overrides) -> Comment:
    """§4.1's Comment, with §4.2's empty parent for a top-level one."""
    fields = {
        "identifier": identifier,
        "author": "A reader",
        "author_url": "",
        "date": _A_DATE,
        "body": "A short comment.\n",
        "parent": "",
    }
    fields.update(overrides)
    return Comment(**fields)


def _snapshot(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, by path relative to it, with its bytes.

    Both halves matter wherever this is used: the key set catches a file created
    or removed, and the bytes catch one rewritten in place."""
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def _recording_replace(calls: list[tuple[str, str]]):
    """An os.replace that records where it was asked to write, then fails.

    Built by a factory rather than closed over in the loop below, so each case
    records into its own list."""

    def interrupted_replace(src, dst, *args, **kwargs):
        calls.append((os.fspath(src), os.fspath(dst)))
        raise OSError("interrupted before the replace completed")

    return interrupted_replace


def _public_names(module) -> set[str]:
    """The module's own top-level public names, read off its source.

    Read from the AST rather than from dir(), so an imported name (os, Path,
    datetime) is not mistaken for part of the Store's surface: an import binds a
    name at module level exactly as an assignment does, and INV-11 is about what
    the Store OFFERS."""
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {name for name in names if not name.startswith("_")}


# ---------------------------------------------------------------- INV-1 ----

# CRLF line endings, an unclosed <p> and <em>, a raw & beside an escaped one,
# and indentation that is nobody's house style. Every one of those is something
# a parser, a formatter or a splitlines()-and-rejoin would change. Against
# well-formed, LF, tidily indented HTML there is nothing to change and the
# assertion would stay green whatever read_html and write_html did.
_UNTIDY_HTML = (
    "<section>\r\n"
    "  <h1>An example</h1>\r\n"
    "      <p>Tea &amp; toast, and a raw & standing on its own.\r\n"
    "<em>unclosed\r\n"
    "</section>\r\n"
)


def test_html_survives_a_round_trip(tmp_path):
    """INV-1: a page or furniture file's bytes survive read_html then write_html
    unchanged -- line endings, indentation and markup errors included.

    Breaks when an implementer runs the file through an HTML parser, a formatter
    or str.splitlines() and rejoins it. Each of those reads as tidying, and each
    one changes his file: §3 decision 1 has the code view hand him the file
    entire, so its bytes are his."""
    original = _UNTIDY_HTML.encode("utf-8")

    for kind, name in ((_PAGES, "about"), (_FURNITURE, "header")):
        path = tmp_path / kind / (name + _HTML_SUFFIX)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)

        text = read_html(path)
        assert text == _UNTIDY_HTML, (
            f"{kind}/{name}: read_html did not return the file's own characters "
            f"(§4.2). Expected {_UNTIDY_HTML!r}, got {text!r}"
        )

        written = Path(write_html(tmp_path, kind, name, text))
        assert written.read_bytes() == original, (
            f"{kind}/{name}: the bytes did not survive read_html -> write_html "
            f"(§4.2, INV-1). Expected {original!r}, got {written.read_bytes()!r}"
        )
        assert read_html(written) == _UNTIDY_HTML, (
            f"{kind}/{name}: the text did not survive a second round trip. "
            f"Expected {_UNTIDY_HTML!r}, got {read_html(written)!r}"
        )


# ---------------------------------------------------------------- INV-2 ----

# An HTML parser, a templating engine, and the network modules PRESS-0005 INV-1
# already forbids. os, pathlib, tempfile, json, dataclasses and datetime are all
# legitimate here -- the Store's whole job is files, and §3 decision 6 puts the
# comments in JSON.
_FORBIDDEN_TOP_LEVEL_IMPORTS = {
    # HTML parsers and markup libraries. `html` covers html.parser and
    # html.entities: entity rewriting is exactly the tidying INV-1 forbids.
    "html", "HTMLParser", "lxml", "bs4", "html5lib", "xml", "markupsafe",
    # Templating.
    "jinja2", "mako", "chameleon", "genshi", "pystache", "cheetah",
    # Network, as PRESS-0005 INV-1 has them.
    "socket", "ssl", "urllib", "http", "requests", "httpx",
    "ftplib", "smtplib", "poplib", "imaplib", "xmlrpc", "webbrowser",
}


def test_store_imports_nothing_forbidden():
    """INV-2: store.py imports no HTML parser, no templating module, still no
    network module, and not pressless.marks.

    Walks the module's AST, as PRESS-0005 INV-1's test does. The source is read
    here, by the test, never by store.py itself.

    Breaks when an implementer imports html.parser to check that a page is well
    formed, which is the obvious way to be helpful here and is what makes INV-1
    unholdable.

    This test proves what the module imports and nothing else (§7): it passes
    against an empty file, and against the stub, by design."""
    tree = ast.parse(inspect.getsource(store_module))

    imported: set[str] = set()
    relative_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_imports.append(node.module or "")
            elif node.module:
                imported.add(node.module)

    forbidden = {
        name for name in imported if name.split(".")[0] in _FORBIDDEN_TOP_LEVEL_IMPORTS
    }
    assert not forbidden, (
        f"store.py imports {sorted(forbidden)!r}. §4.5: the Store never parses "
        f"the HTML it holds, never produces HTML and never reaches the network. "
        f"Expected none of {sorted(_FORBIDDEN_TOP_LEVEL_IMPORTS)!r}"
    )

    marks = {
        name for name in imported
        if name == "pressless.marks" or name.startswith("pressless.marks.")
    }
    assert not marks, (
        f"store.py imports {sorted(marks)!r}. §4.5: turning marked text into "
        f"HTML is Marks' job and the Store does not import Marks"
    )
    assert "marks" not in relative_imports, (
        f"store.py has a relative import of {relative_imports!r}, which can only "
        f"name a sibling pressless module -- 'marks' is forbidden (§4.5)"
    )


# ---------------------------------------------------------------- INV-3 ----

# §4.3: every name that becomes a slug-shaped file name takes the slug rule
# store.path_for applies. A separator or `..` writes outside the handed folder;
# an upper-case letter is two files on Linux and one on Windows.
_ILLEGAL_NAMES = {
    "the parent directory": "..",
    "a path separator": "an/example",
    "an absolute path": "/an-example",
    "the empty name": "",
    "an upper-case letter": "An-Example",
}


def test_illegal_names_are_refused(tmp_path):
    """INV-3: a page, furniture or template name, or a comments slug, that is
    not a legal slug raises StoreError and produces no path; and a furniture
    name outside FURNITURE_NAMES raises StoreError too.

    Every call that turns a name into a slug-shaped path is exercised, because
    the mistake this catches is a NEW path function joining the name without the
    guard -- so a test naming only some of them goes green on the one that was
    forgotten. photograph_path_for is deliberately not here: INV-11 gives it the
    weaker rule, its name being PRESS-0016's to decide.

    The positive control at the end is load-bearing. Without it a function that
    raised StoreError at every call would satisfy every assertion above."""
    assert tuple(FURNITURE_NAMES) == _FURNITURE_NAMES, (
        f"FURNITURE_NAMES is {tuple(FURNITURE_NAMES)!r}, not §4.1's three names "
        f"{_FURNITURE_NAMES!r}. §3 decision 2: the site has exactly one header, "
        f"one footer and one navigation"
    )

    calls = (
        ("html_path_for(pages)", lambda name: html_path_for(tmp_path, _PAGES, name)),
        ("html_path_for(furniture)", lambda name: html_path_for(tmp_path, _FURNITURE, name)),
        ("template_path_for", lambda name: template_path_for(tmp_path, name)),
        ("comments_path_for", lambda name: comments_path_for(tmp_path, name)),
    )
    cases = [
        (f"{label}, {description}", call, name)
        for label, call in calls
        for description, name in _ILLEGAL_NAMES.items()
    ]
    # A legal slug that is not one of the three furniture files. §4.1: an open
    # furniture folder would let a fourth file exist the Builder has no place
    # for. This case is what separates the allow-list from the slug rule -- the
    # illegal names above are refused by either.
    cases.append((
        "html_path_for(furniture), a legal name outside FURNITURE_NAMES",
        lambda name: html_path_for(tmp_path, _FURNITURE, name),
        "sidebar",
    ))

    before = _snapshot(tmp_path)
    failures: list[str] = []
    for case, call, name in cases:
        try:
            produced = call(name)
        except StoreError:
            pass
        except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
            failures.append(f"{case} ({name!r}): raised {exc!r}; expected StoreError")
        else:
            failures.append(
                f"{case} ({name!r}): returned the path {produced!r}; expected "
                f"StoreError and no path (§4.3, INV-3)"
            )
        after = _snapshot(tmp_path)
        if after != before:
            failures.append(
                f"{case} ({name!r}): the folder changed although the name was "
                f"refused. Expected {sorted(before)!r}, got {sorted(after)!r}"
            )
    assert not failures, "INV-3 breaches:\n" + "\n".join(failures)

    accepted = {
        "html_path_for(pages)": (
            html_path_for(tmp_path, _PAGES, "about"),
            tmp_path / _PAGES / ("about" + _HTML_SUFFIX),
        ),
        "html_path_for(furniture)": (
            html_path_for(tmp_path, _FURNITURE, "header"),
            tmp_path / _FURNITURE / ("header" + _HTML_SUFFIX),
        ),
        "template_path_for": (
            template_path_for(tmp_path, "a-template"),
            tmp_path / _TEMPLATES / ("a-template" + _ENTRY_SUFFIX),
        ),
        "comments_path_for": (
            comments_path_for(tmp_path, "an-example"),
            tmp_path / _COMMENTS / ("an-example" + _COMMENTS_SUFFIX),
        ),
    }
    for case, (produced, expected) in accepted.items():
        assert Path(produced) == expected, (
            f"{case}: a legal name did not produce §4.3's path. Expected "
            f"{expected!r}, got {produced!r}"
        )


# ---------------------------------------------------------------- INV-4 ----

# One export record, with two values that appear nowhere else in it. Both are
# invented: nothing from the real archive is written into a fixture (§7).
_SENTINEL_EMAIL = "a-reader-4f7q@example.invalid"
_SENTINEL_IP = "203.0.113.77"
_EXPORT_RECORD = {
    "comment_id": "41",
    "comment_author": "A reader",
    "comment_author_url": "https://example.invalid/a-reader",
    "comment_author_email": _SENTINEL_EMAIL,
    "comment_author_IP": _SENTINEL_IP,
    "comment_date": "2014-11-09 21:32:00",
    "comment_content": "A short comment about the tune.\n",
    "comment_parent": "0",
}

# §4.1's six fields, written out rather than read off the dataclass, which would
# compare Comment against itself.
_COMMENT_FIELDS = {"identifier", "author", "author_url", "date", "body", "parent"}


def test_comments_carry_no_contact_details(tmp_path):
    """INV-4: a Comment has no field for an email address or an IP address, so
    no value the export carries in comment_author_email or comment_author_IP is
    written by the Store as a field of its own.

    A body is out of scope on purpose: it is the reader's own words and INV-6
    carries it verbatim, so an address a reader typed into their own comment
    stays. What this forbids is the Store carrying the fields WordPress
    collected around them.

    Breaks when an implementer widens Comment to whatever the export offers, or
    keeps the original record alongside for later. Both are the same mistake:
    this is the field set, not a subset of a bigger one.

    The field-name half passes against the stub, which declares the dataclass;
    the written-bytes half needs write_comments."""
    actual = {field.name for field in dataclasses.fields(Comment)}
    assert actual == _COMMENT_FIELDS, (
        f"Comment's fields are {sorted(actual)!r}, not §4.1's six "
        f"{sorted(_COMMENT_FIELDS)!r}. An email or IP field here is the one "
        f"thing in this spec that cannot be undone once written (§4.5)"
    )

    elsewhere = [
        f"{key}={value!r}" for key, value in _EXPORT_RECORD.items()
        if key not in ("comment_author_email", "comment_author_IP")
        and (_SENTINEL_EMAIL in value or _SENTINEL_IP in value)
    ]
    assert not elsewhere, (
        f"the fixture's own record carries the sentinel values outside the email "
        f"and IP fields ({elsewhere!r}), so finding them in the written file "
        f"would prove nothing -- fix the fixture, not the assertion"
    )

    from_the_export = _comment(
        identifier=_EXPORT_RECORD["comment_id"],
        author=_EXPORT_RECORD["comment_author"],
        author_url=_EXPORT_RECORD["comment_author_url"],
        body=_EXPORT_RECORD["comment_content"],
    )
    write_comments(tmp_path, "an-example", (from_the_export,))

    for name, content in _snapshot(tmp_path).items():
        for label, value in (("email", _SENTINEL_EMAIL), ("IP", _SENTINEL_IP)):
            assert value.encode("utf-8") not in content, (
                f"the {label} address the export collected is in {name}. "
                f"Expected {value!r} to appear in no file the Store writes, "
                f"got:\n{content!r}"
            )


# ---------------------------------------------------------------- INV-5 ----


def test_a_dangling_reply_is_refused(tmp_path):
    """INV-5: write_comments raises DanglingReply when a reply's parent is not
    in the same set, and writes nothing.

    Asserting the exception alone would not bite: an implementation that writes
    the file and then validates leaves the Builder the broken tree anyway. The
    folder is compared byte for byte, so a temporary file left behind counts too.

    Breaks when an implementer validates nothing and leaves the Builder a tree
    with a missing branch, which shows up as a comment silently not rendering
    rather than as an error."""
    good = (
        _comment("1", body="The first comment.\n"),
        _comment("2", body="A reply to the first.\n", parent="1"),
    )
    written = Path(write_comments(tmp_path, "an-example", good))
    before = _snapshot(tmp_path)

    dangling = (
        _comment("1", body="The first comment.\n"),
        _comment("3", body="A reply to nothing here.\n", parent="absent"),
    )
    try:
        write_comments(tmp_path, "an-example", dangling)
    except DanglingReply:
        pass
    except Exception as exc:
        raise AssertionError(
            f"write_comments raised {exc!r} for a reply naming the absent "
            f"parent 'absent'; §4.4 requires DanglingReply"
        ) from exc
    else:
        raise AssertionError(
            "write_comments accepted a set whose reply names the absent parent "
            "'absent'; §4.4 requires DanglingReply and nothing written"
        )

    after = _snapshot(tmp_path)
    assert after == before, (
        f"the folder changed although the set was refused. Expected "
        f"{sorted(before)!r} with unchanged bytes, got {sorted(after)!r}"
    )
    assert read_comments(written) == good, (
        f"after a refused write the file no longer holds the previous set. "
        f"Expected {good!r}, got {read_comments(written)!r}"
    )


# ---------------------------------------------------------------- INV-6 ----

# A blank line, a quotation mark, a backslash, a non-ASCII character and a line
# that looks like JSON. The last is what catches a reader that re-parses a body;
# the backslash and the quotation mark catch an escaping rule that loses one.
_AWKWARD_BODY = (
    'First line.\n'
    '\n'
    'A quotation mark: " and a backslash: \\ on one line.\n'
    'An accented word: café.\n'
    '{"looks": "like JSON", "parent": "99"}\n'
)


def test_comments_survive_a_round_trip(tmp_path):
    """INV-6: comments survive write_comments then read_comments with every
    field and their order unchanged.

    The reply is ordered BEFORE the comment it answers, which is the case that
    fails against an implementation reordering replies under their parents at
    rest. Both are in the set, so INV-5 has nothing to refuse.

    Breaks when an implementer sorts on read, or reorders replies under their
    parents at rest. Sorting looks like a service and makes the file no longer
    what was written; ordering is the Builder's decision (§4.2)."""
    comments = (
        _comment(
            "2",
            author="Another reader",
            author_url="https://example.invalid/another",
            body=_AWKWARD_BODY,
            parent="1",
            date=datetime(2015, 3, 2, 7, 45, 0),  # noqa: DTZ001 -- naive, as §4.2 has it
        ),
        _comment("1", body="The comment being answered.\n"),
        _comment("3", author="", author_url="", body="\n"),
    )

    written = Path(write_comments(tmp_path, "an-example", comments))
    read_back = read_comments(written)

    assert len(read_back) == len(comments), (
        f"read_comments returned {len(read_back)} comments, not the "
        f"{len(comments)} that were written. Got {read_back!r}"
    )
    assert [comment.identifier for comment in read_back] == [
        comment.identifier for comment in comments
    ], (
        f"the comments came back in a different order. Expected "
        f"{[comment.identifier for comment in comments]!r}, got "
        f"{[comment.identifier for comment in read_back]!r} -- §4.2 keeps file "
        f"order, and ordering is the Builder's decision"
    )
    for expected, actual in zip(comments, read_back):
        for field in sorted(_COMMENT_FIELDS):
            assert getattr(actual, field) == getattr(expected, field), (
                f"comment {expected.identifier!r}: field {field!r} did not "
                f"survive the round trip. Expected "
                f"{getattr(expected, field)!r}, got {getattr(actual, field)!r}"
            )


# ---------------------------------------------------------------- INV-7 ----

# §4.1's three template names and nothing else. There is deliberately no
# read_template (PRESS-0005's read takes a path) and deliberately nothing that
# moves a template into an entry folder.
_TEMPLATE_NAMES = {"TEMPLATES_FOLDER", "template_path_for", "list_templates", "write_template"}


def test_a_template_is_never_an_entry(tmp_path):
    """INV-7: no template appears in list_slugs for either entry folder, and the
    Store offers no call that moves one into them.

    Breaks when an implementer stores templates as drafts with a marker field,
    which is the cheap shortcut (§8) and puts them one bug away from being
    published -- the worst failure this project has.

    The name half passes against the stub; the list_slugs half needs
    write_template."""
    offered = {name for name in _public_names(store_module) if "template" in name.lower()}
    assert offered == _TEMPLATE_NAMES, (
        f"the Store's template-related public names are {sorted(offered)!r}, "
        f"not §4.1's {sorted(_TEMPLATE_NAMES)!r}. A call that publishes, copies "
        f"or promotes a template is the route INV-7 forbids"
    )

    (tmp_path / _PUBLISHED).mkdir()
    (tmp_path / _DRAFTS).mkdir()
    written = Path(write_template(tmp_path, _entry(slug="a-template")))

    assert written == tmp_path / _TEMPLATES / ("a-template" + _ENTRY_SUFFIX), (
        f"write_template put the file at {written!r}; §4.3 requires "
        f"{tmp_path / _TEMPLATES / ('a-template' + _ENTRY_SUFFIX)!r}"
    )
    for draft in (False, True):
        folder = _DRAFTS if draft else _PUBLISHED
        assert list_slugs(tmp_path, draft=draft) == (), (
            f"list_slugs(draft={draft}) returned "
            f"{list_slugs(tmp_path, draft=draft)!r} after a template was "
            f"written; expected () -- no template is reachable as an entry, and "
            f"{folder}/ holds none"
        )


# ---------------------------------------------------------------- INV-8 ----


def test_comments_are_not_entries(tmp_path):
    """INV-8: a comments file is written under COMMENTS_FOLDER and never into
    either entry folder.

    Comparing list_slugs would not catch the breach: it keeps only names ending
    in the entry suffix, so a .json file in an entry folder is invisible to it
    and the layout could be breached with the assertion still green. The folder
    LISTING is what has to be asserted, which is why _snapshot is used here.

    The slug that does not exist is the second case on purpose: an
    implementation writing beside the entry has to create something somewhere,
    and where there is no entry it is likelier to guess.

    Breaks when an implementer puts the comments beside the entry after all."""
    write(tmp_path, _entry(slug="an-example"), draft=False)
    write(tmp_path, _entry(slug="unfinished"), draft=True)
    before = {
        folder: _snapshot(tmp_path / folder) for folder in (_PUBLISHED, _DRAFTS)
    }

    path = Path(comments_path_for(tmp_path, "an-example"))
    assert path == tmp_path / _COMMENTS / ("an-example" + _COMMENTS_SUFFIX), (
        f"comments_path_for resolved to {path!r}; §4.3 requires "
        f"{tmp_path / _COMMENTS / ('an-example' + _COMMENTS_SUFFIX)!r} -- a "
        f"folder of their own, not the entry's (§3 decision 5)"
    )

    for slug in ("an-example", "not-an-entry"):
        written = Path(write_comments(tmp_path, slug, (_comment("1"),)))
        assert written == tmp_path / _COMMENTS / (slug + _COMMENTS_SUFFIX), (
            f"write_comments({slug!r}) wrote to {written!r}; §4.3 requires "
            f"{tmp_path / _COMMENTS / (slug + _COMMENTS_SUFFIX)!r}"
        )

    for folder in (_PUBLISHED, _DRAFTS):
        after = _snapshot(tmp_path / folder)
        assert after == before[folder], (
            f"the {folder}/ folder changed when comments were written. Expected "
            f"{sorted(before[folder])!r} with unchanged bytes, got "
            f"{sorted(after)!r} -- a comments file never lands in an entry folder"
        )


# ---------------------------------------------------------------- INV-9 ----


def test_writes_are_atomic(tmp_path, monkeypatch):
    """INV-9: after a write of any kind here interrupted before completion, the
    file on disk is the previous one.

    Asserting os.replace's DESTINATION as well as the effect is what pins the
    mechanism (§4.4, PRESS-0005 §4.5). Against an implementation that opens the
    target and writes into it the patch never fires, the write completes, and the
    file on disk is the new one -- so the effect half alone would not bite.

    Breaks when an implementer writes the new calls with a plain open, having
    taken the atomic route only in the entry code it copied from."""
    cases = (
        (
            "write_html",
            lambda: write_html(tmp_path, _PAGES, "about", "<p>The previous page.\n"),
            lambda: write_html(tmp_path, _PAGES, "about", "<p>The new page.\n"),
            tmp_path / _PAGES / ("about" + _HTML_SUFFIX),
        ),
        (
            "write_template",
            lambda: write_template(tmp_path, _entry(slug="a-template", body="Previous.\n")),
            lambda: write_template(tmp_path, _entry(slug="a-template", body="New.\n")),
            tmp_path / _TEMPLATES / ("a-template" + _ENTRY_SUFFIX),
        ),
        (
            "write_comments",
            lambda: write_comments(tmp_path, "an-example", (_comment("1", body="Previous.\n"),)),
            lambda: write_comments(tmp_path, "an-example", (_comment("1", body="New.\n"),)),
            tmp_path / _COMMENTS / ("an-example" + _COMMENTS_SUFFIX),
        ),
    )

    for case, first, second, expected in cases:
        target = Path(first())
        before = target.read_bytes()

        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(os, "replace", _recording_replace(calls))
        try:
            # Not a bare Exception: a blind assertion here passes against any
            # failure at all, the stub's NotImplementedError included.
            with pytest.raises((StoreError, OSError)):
                second()
        finally:
            monkeypatch.undo()

        assert calls, (
            f"{case}: never reached os.replace -- it wrote into the target "
            f"directly, so there is no point at which an interruption leaves "
            f"the previous file (§4.4)"
        )
        destinations = {destination for _, destination in calls}
        assert destinations == {os.fspath(expected)}, (
            f"{case}: replaced {destinations!r}; §4.3 requires the destination "
            f"to be {os.fspath(expected)!r}"
        )
        assert target.read_bytes() == before, (
            f"{case}: after a write interrupted at the replace the file on disk "
            f"is not the previous one. Expected {before!r}, got "
            f"{target.read_bytes()!r}"
        )


# --------------------------------------------------------------- INV-10 ----

# A CRLF line ending and a non-ASCII word, in a page. §4.2 keeps a page's bytes
# and normalises everything else, so this is the fixture that separates the two
# rules: LF everywhere rewrites his page, which §3 decision 1 forbids.
_A_PAGE_WITH_CRLF = "<h1>An example</h1>\r\n<p>A café, and a second line.</p>\r\n"
_A_BODY_WITH_CRLF = "A line.\r\nAnother line.\r\n"


def test_encodings_are_as_specified(tmp_path, monkeypatch):
    """INV-10: a comments file is UTF-8 with LF line endings whatever the
    platform's defaults; a page or furniture file is UTF-8 and keeps the bytes it
    was given, line endings included.

    Breaks when an implementer applies one newline rule to everything.

    NEITHER half can be settled from the bytes on Linux: os.linesep is "\n"
    here, so a write that left the newline to the platform produces the same
    file as one that named it. Measured 2026-09-02 by mutation probe --
    newline=None survived the byte assertions below. So the bytes are asserted
    for what they do catch (a CRLF rewritten out of a page, a CRLF written into
    the JSON), and what the Store NAMED when it opened the file is asserted
    after them, which is the half the platform cannot vary. A comment body's
    own CRLF is the reader's and comes back whole (INV-6)."""
    page = Path(write_html(tmp_path, _PAGES, "about", _A_PAGE_WITH_CRLF))
    raw = page.read_bytes()
    assert b"\r\n" in raw, (
        f"the page's CRLF line endings were rewritten. Expected b'\\r\\n' in "
        f"the file, got {raw!r} -- §4.2 keeps a page's bytes, the code view "
        f"hands him the file entire, and rewriting his line endings on save is "
        f"the reformatting §3 decision 1 forbids"
    )
    assert raw == _A_PAGE_WITH_CRLF.encode("utf-8"), (
        f"the page is not the UTF-8 encoding of the text it was given. Expected "
        f"{_A_PAGE_WITH_CRLF.encode('utf-8')!r}, got {raw!r}"
    )

    comments = Path(
        write_comments(tmp_path, "an-example", (_comment("1", body=_A_BODY_WITH_CRLF),))
    )
    written = comments.read_bytes()
    assert b"\r" not in written, (
        f"the comments file carries a carriage return, so its own line endings "
        f"are not LF (§4.2, INV-10). Expected no b'\\r' anywhere, got {written!r}"
    )
    read_back = read_comments(comments)
    assert read_back and read_back[0].body == _A_BODY_WITH_CRLF, (
        f"the reader's own CRLF did not survive the round trip. Expected "
        f"{_A_BODY_WITH_CRLF!r}, got "
        f"{read_back[0].body if read_back else read_back!r}"
    )

    # What was NAMED at the open, watched at every entry point an
    # implementation might reach for, so a watch cannot miss the one it used.
    opens = _watch_opens(monkeypatch)
    write_html(tmp_path, _PAGES, "about", _A_PAGE_WITH_CRLF)
    page_writes = [one for one in opens if one.writes() and not one.binary]
    assert page_writes, (
        "write_html performed no text write, so what it named cannot be read. "
        "A page is written as text with translation off, not as bytes (§4.2)"
    )
    for one in page_writes:
        assert one.encoding == "utf-8", (
            f"write_html named encoding {one.encoding!r}; §4.2 requires "
            f"'utf-8'. Python's default is the locale's -- cp1252 on Windows"
        )
        assert one.newline == "", (
            f"write_html named newline {one.newline!r}; §4.2 requires '' -- "
            f"translation OFF, so the line endings he saved are the line "
            f"endings on disk. None leaves it to the platform, which rewrites "
            f"his page to CRLF on Windows, and that is what §3 decision 1 "
            f"forbids"
        )

    opens.clear()
    write_comments(tmp_path, "an-example", (_comment("1", body=_A_BODY_WITH_CRLF),))
    comment_writes = [one for one in opens if one.writes() and not one.binary]
    assert comment_writes, "write_comments performed no text write to watch"
    for one in comment_writes:
        assert one.encoding == "utf-8", (
            f"write_comments named encoding {one.encoding!r}; §4.2 requires "
            f"'utf-8'"
        )
        assert one.newline == "\n", (
            f"write_comments named newline {one.newline!r}; §4.2 requires "
            f"'\\n' whatever the platform's defaults -- a comments file takes "
            f"the LF rule, unlike a page"
        )


# --------------------------------------------------------------- INV-11 ----

# PRESS-0005 §4.1's surface and this spec's §4.1, written out rather than read
# off the module. Sharing the lists with the module would compare it against
# itself, and a copy-a-photograph call could then be added with this green.
_PRESS_0005_SURFACE = {
    "Entry", "RECOGNISED_FIELDS", "LIST_SEPARATOR", "FILE_SUFFIX",
    "PUBLISHED_FOLDER", "DRAFTS_FOLDER",
    "path_for", "exists", "list_slugs", "read", "write", "publish", "unpublish",
    "StoreError", "EntryNotFound", "SlugInUse",
}
_PRESS_0006_SURFACE = {
    "Comment", "PAGES_FOLDER", "FURNITURE_FOLDER", "TEMPLATES_FOLDER",
    "COMMENTS_FOLDER", "PHOTOGRAPHS_FOLDER", "HTML_SUFFIX", "COMMENTS_SUFFIX",
    "FURNITURE_NAMES", "DanglingReply",
    "html_path_for", "list_html", "read_html", "write_html",
    "template_path_for", "list_templates", "write_template",
    "comments_path_for", "read_comments", "write_comments",
    "photograph_path_for", "list_photographs",
}

# §3 decision 10 leaves a photograph's file name to PRESS-0016 -- the archive's
# own attachment names carry underscores and would not pass the slug rule -- so
# only these three, which reach outside the folder, are refused.
_NAMES_THAT_REACH_OUTSIDE = {
    "the parent directory": "..",
    "a path separator": "photographs/an-example.jpg",
    "an absolute path": "/an-example.jpg",
    # A backslash is one component's name on Linux and two on Windows, and the
    # app runs on both -- so a rule checking only this platform's separator
    # lets a name reach outside the folder there. Added 2026-09-02: a mutation
    # probe dropping the backslash guard survived every case above.
    "a Windows path separator": "photographs\\an-example.jpg",
}
# Not from the archive (§7 writes nothing of it into a fixture): the SHAPE the
# archive carries -- underscores and an extension, which no slug rule admits.
_A_PHOTOGRAPH_NAME = "An_Example_Photograph_2014.jpg"


def test_photographs_stay_where_they_are(tmp_path):
    """INV-11: a photograph's original has a place in Pressless's own folder and
    no route to the site folder.

    Breaks when an implementer has the Store copy an original toward the site
    folder to save the Builder a step, which publishes the full original of
    every photograph he has. The surface assertion is what catches that: a
    copy-a-photograph call cannot be added without this test failing.

    The accepting case is load-bearing twice over. Without it a function that
    refused everything would pass, and a name of the archive's own shape is what
    stops the weaker rule being tightened into the slug rule §3 decision 10
    withdrew."""
    failures: list[str] = []
    for description, name in _NAMES_THAT_REACH_OUTSIDE.items():
        try:
            produced = photograph_path_for(tmp_path, name)
        except StoreError:
            continue
        except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
            failures.append(
                f"{description} ({name!r}): raised {exc!r}; expected StoreError"
            )
        else:
            failures.append(
                f"{description} ({name!r}): returned {produced!r}; expected "
                f"StoreError -- a photograph's name must be a single path "
                f"component, so it cannot reach outside the folder (INV-11)"
            )
    assert not failures, "INV-11 breaches:\n" + "\n".join(failures)

    produced = Path(photograph_path_for(tmp_path, _A_PHOTOGRAPH_NAME))
    expected = tmp_path / _PHOTOGRAPHS / _A_PHOTOGRAPH_NAME
    assert produced == expected, (
        f"photograph_path_for({_A_PHOTOGRAPH_NAME!r}) returned {produced!r}; "
        f"§4.3 requires {expected!r}. The name is PRESS-0016's to decide and "
        f"carries underscores and an extension no slug rule admits (§3 "
        f"decision 10)"
    )

    surface = _public_names(store_module)
    expected_surface = _PRESS_0005_SURFACE | _PRESS_0006_SURFACE
    assert surface == expected_surface, (
        f"the Store's public names are not PRESS-0005 §4.1's surface together "
        f"with PRESS-0006 §4.1's. Added: {sorted(surface - expected_surface)!r}. "
        f"Missing: {sorted(expected_surface - surface)!r}. A call that copies a "
        f"photograph anywhere is the one INV-11 forbids"
    )
