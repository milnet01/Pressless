# PRESS-0007 §7 — Import's archive conformance run.
#
# Why this exists: Import runs once, over the real export, and anything it
# gets wrong there is lost for good (docs/specs/PRESS-0007-import.md §2). The
# small exports test_importer.py builds cannot say what the real archive
# holds; these tests read it. §7 names them and their skip conditions, §10
# says what each proves.
#
# This file names no person, no site and no domain -- only "the writer" and
# "the archive" -- per this repository's own CLAUDE.md § This repository is
# PUBLIC. Nothing from the archive is printed: a passing run prints counts,
# and a failing one names post ids, never text.
"""§7: Import over the real export.

Each test skips only where what it reads is absent: PRESSLESS_ARCHIVE for
all of them, PRESSLESS_ORIGINALS for the ones that run the whole import, and
today's generator for INV-2's and INV-3's, which compare against it. Anything
present and unusable fails, as the other archive tests do.
"""
from __future__ import annotations

import difflib
import html
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from _archive_oracle import load_generator

from pressless import store
from pressless.marks import render
from pressless_import import convert, is_markup, resolve_slug, run, visible_lines

PRESSLESS_ARCHIVE = os.environ.get("PRESSLESS_ARCHIVE")
PRESSLESS_ORIGINALS = os.environ.get("PRESSLESS_ORIGINALS")

pytestmark = pytest.mark.archive

needs_archive = pytest.mark.skipif(
    not PRESSLESS_ARCHIVE,
    reason="PRESS-0007: set PRESSLESS_ARCHIVE to a WordPress export path to run this",
)
needs_originals = pytest.mark.skipif(
    not PRESSLESS_ORIGINALS,
    reason="PRESS-0007: set PRESSLESS_ORIGINALS to the photograph originals to run this",
)

_GALLERY = re.compile(r"\[gallery\b[^\]]*\]")
_PHOTO_MARK = re.compile(r"\{photo:\s*([^|}]+?)\s*(?:\|[^}]*)?\}")
_LINK_MARK = re.compile(r"\{link:\s*([^}\s]+)\s*\}")
_RESIZED = re.compile(r"-\d+x\d+(?=\.[^./]+$)")


# -------------------------------------------------------------- reading ----


def _export():
    """The export's <channel> and its `wp:` namespace, read off the document."""
    path = Path(PRESSLESS_ARCHIVE)
    assert path.is_file(), "PRESSLESS_ARCHIVE is set and does not name a file"
    root = ET.parse(path).getroot()
    namespace = next(
        (element.tag[1:].split("}", 1)[0] for element in root.iter()
         if isinstance(element.tag, str)
         and element.tag.startswith("{http://wordpress.org/export/")),
        None,
    )
    assert namespace, "the export declares no wordpress.org/export namespace"
    channel = root.find("channel")
    assert channel is not None, "the export has no <channel>"
    return channel, {"wp": namespace}


def _field(item, name, ns) -> str:
    return (item.findtext(f"wp:{name}", "", ns) or "").strip()


def _body(item) -> str:
    return item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""


def _carried(channel, ns):
    """§4.2's population: posts published, draft or private, and pages."""
    for item in channel.findall("item"):
        kind, status = _field(item, "post_type", ns), _field(item, "status", ns)
        if kind == "page" or (kind == "post" and status in ("publish", "draft", "private")):
            yield item


def _upload_path(address: str) -> str | None:
    path = unquote(urlparse(address).path)
    index = path.find("/uploads/")
    return path[index + len("/uploads/"):] if index >= 0 else None


def _lookups(channel, ns):
    """§4.1's two lookups, over the export's attachments, and the old site's
    host. The names they answer are stand-ins: only whether an address is an
    attachment decides what `convert` writes, and the page never shows a
    picture's file name."""
    by_upload, by_id = {}, {}
    for item in channel.findall("item"):
        if _field(item, "post_type", ns) != "attachment":
            continue
        upload_path = _upload_path(_field(item, "attachment_url", ns))
        if upload_path:
            name = f"attachment-{_field(item, 'post_id', ns)}"
            by_upload[upload_path] = name
            by_id[_field(item, "post_id", ns)] = name

    def by_address(address):
        upload_path = _upload_path(address)
        if upload_path is None:
            return None
        return by_upload.get(upload_path) or by_upload.get(_RESIZED.sub("", upload_path))

    base = channel.findtext("wp:base_blog_url", "", ns) or channel.findtext("link") or ""
    return by_address, by_id.get, urlparse(base.strip()).netloc


def _made_by_deleting_stars(source: str, rendered: str) -> bool:
    """§4.3: the rendered line is the source line with `*` deleted and nothing else."""
    position = 0
    for character in source:
        if position < len(rendered) and character == rendered[position]:
            position += 1
        elif character != "*":
            return False
    return position == len(rendered)


def _only_allowed_differences(source, rendered, body) -> bool:
    """§4.3's three purposeful differences, and no other.

    A gallery shortcode's text becomes its pictures, so its line may vanish.
    A video, an embed or a picture with no attachment gains its address as a
    link's words, so a line that is an address the body itself carries may
    appear. And a pair of his asterisks is styled by Marks, so a line may lose
    `*` characters and nothing else."""
    addresses = html.unescape(body)
    matcher = difflib.SequenceMatcher(a=source, b=rendered, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed = [line for line in source[i1:i2] if not _GALLERY.fullmatch(line)]
        added = [line for line in rendered[j1:j2]
                 if not (line.startswith(("http://", "https://")) and line in addresses)]
        if len(removed) == len(added) and all(
            _made_by_deleting_stars(s, r) for s, r in zip(removed, added, strict=True)
        ):
            continue
        return False
    return True


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    """The whole import, once, into a temporary folder -- removed afterwards,
    since it holds a copy of every original and pytest keeps old temp folders."""
    originals = Path(PRESSLESS_ORIGINALS)
    assert originals.is_dir(), "PRESSLESS_ORIGINALS is set and does not name a folder"
    into = tmp_path_factory.mktemp("import") / "pressless-data"
    report = run(Path(PRESSLESS_ARCHIVE), originals, into)
    print(
        f"carried: {report.published} published, {report.drafts} drafts, "
        f"{report.comments} comments, {report.photographs} photographs; "
        f"{len(report.renamed_slugs)} slugs and {len(report.renamed_photographs)} "
        f"photographs renamed; {len(report.dropped)} report lines over "
        f"{len({d.slug for d in report.dropped})} entries"
    )
    yield into, report
    shutil.rmtree(into, ignore_errors=True)


def _bodies(into: Path):
    for draft in (False, True):
        for slug in store.list_slugs(into, draft=draft):
            yield slug, store.read(store.path_for(into, slug, draft=draft)).body


# ------------------------------------------------------------ INV-2 -------


@needs_archive
def test_slugs_match_the_live_rule():
    """INV-2, archive half: `resolve_slug` equals today's generator's rule on
    every item of the archive -- its slug rule, then the post id where
    nothing survives."""
    generator = load_generator("safe_slug")
    channel, ns = _export()
    items = channel.findall("item")
    differ = [
        _field(item, "post_id", ns) for item in items
        if resolve_slug(_field(item, "post_name", ns), _field(item, "post_id", ns))
        != (generator.safe_slug(_field(item, "post_name", ns)) or _field(item, "post_id", ns))
    ]
    print(f"items compared: {len(items)}")
    assert not differ, f"resolve_slug departs from the live rule on post ids {differ[:20]}"


# ------------------------------------------------------------ INV-3 -------


@needs_archive
def test_markup_is_decided_as_today():
    """INV-3, archive half: on every carried item `is_markup` agrees with
    today's generator, and every plain body renders through Marks exactly as
    `wpautop()` renders it -- the pages Import adds included."""
    generator = load_generator("HAS_TAGS", "wpautop")
    channel, ns = _export()
    disagree, rendered_differently, plain = [], [], 0
    for item in _carried(channel, ns):
        body = _body(item)
        today = "<!-- wp:" in body or bool(generator.HAS_TAGS.search(body))
        if is_markup(body) != today:
            disagree.append(_field(item, "post_id", ns))
        if not today:
            plain += 1
            if render(body, lambda name: name) != generator.wpautop(body):
                rendered_differently.append(_field(item, "post_id", ns))
    print(f"plain bodies rendered: {plain}")
    assert not disagree, f"is_markup departs from today's test on post ids {disagree[:20]}"
    assert not rendered_differently, (
        f"a plain body renders differently from today on post ids {rendered_differently[:20]}"
    )


# ------------------------------------------------------------ INV-5 -------


@needs_archive
def test_no_line_is_lost():
    """INV-5: for every converted body in the archive, the lines a reader sees
    are unchanged, except for the differences §4.3's check allows -- whether
    or not the report lists them."""
    channel, ns = _export()
    by_address, by_id, old_site = _lookups(channel, ns)
    compared, lost = 0, []
    for item in _carried(channel, ns):
        body = _body(item)
        if not is_markup(body):
            continue
        compared += 1
        text, _dropped = convert(body, by_address, by_id, old_site=old_site)
        before = visible_lines(body)
        after = visible_lines(render(text, lambda name: name))
        if not _only_allowed_differences(before, after, body):
            lost.append(_field(item, "post_id", ns))
    print(f"converted bodies compared: {compared}")
    assert compared, "no converted body was found, so this proved nothing"
    assert not lost, f"a reader's lines changed on post ids {lost[:20]}"


# ------------------------------------------------------------ INV-6 -------


@needs_archive
@needs_originals
def test_every_picture_resolves(imported):
    """INV-6, archive half: every original is in the photographs folder byte
    for byte, every picture mark names a file there, and no traced picture
    kept its WordPress address."""
    into, report = imported
    channel, ns = _export()
    originals = Path(PRESSLESS_ORIGINALS)
    renamed = dict(report.renamed_photographs)
    mismatched = []
    attachments = 0
    for item in channel.findall("item"):
        if _field(item, "post_type", ns) != "attachment":
            continue
        upload_path = _upload_path(_field(item, "attachment_url", ns))
        attachments += 1
        name = renamed.get(upload_path, upload_path.rsplit("/", 1)[-1])
        copied = store.photograph_path_for(into, name)
        if not copied.is_file() or copied.read_bytes() != (originals / upload_path).read_bytes():
            mismatched.append(_field(item, "post_id", ns))
    photographs = set(store.list_photographs(into))
    by_address, _by_id, _old_site = _lookups(channel, ns)
    unresolved, kept_address = [], []
    for slug, body in _bodies(into):
        if any(name not in photographs for name in _PHOTO_MARK.findall(body)):
            unresolved.append(slug)
        if any(by_address(address) for address in _LINK_MARK.findall(body)):
            kept_address.append(slug)
    print(f"attachments: {attachments}; photographs written: {len(photographs)}")
    assert not mismatched, f"an original was not copied byte for byte: post ids {mismatched[:20]}"
    assert not unresolved, f"{len(unresolved)} entries name a photograph that is not there"
    assert not kept_address, f"{len(kept_address)} entries kept a traced picture's address"


# ------------------------------------------------------------ INV-7 -------


@needs_archive
@needs_originals
def test_no_address_reaches_the_folder(imported):
    """INV-7, archive half: no value the export carries in a commenter's email
    or IP field reaches any file Import writes. The values are never printed,
    on a pass or a failure."""
    into, _report = imported
    channel, ns = _export()
    values = set()
    for element in channel.iter():
        if isinstance(element.tag, str) and element.tag.endswith("}comment"):
            for field in ("comment_author_email", "comment_author_IP"):
                value = (element.findtext(f"wp:{field}", "", ns) or "").strip()
                if value:
                    values.add(value.encode("utf-8"))
    assert values, "the export carries no contact value, so this run would prove nothing"
    files = [path for path in into.rglob("*") if path.is_file()]
    hits = sum(1 for path in files for value in values if value in path.read_bytes())
    print(f"contact values searched for: {len(values)}; files searched: {len(files)}")
    assert not hits, f"{hits} contact value(s) reached a file Import wrote -- not printed"
