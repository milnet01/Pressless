# PRESS-0008 §7 — the Builder's archive conformance run (INV-15).
#
# Why this exists: a published page's address is a breaking surface
# (docs/standards/versioning-overrides.md § The live site). The first publish
# replaces every page today's generator wrote, and a moved address is found by
# a reader. Only the real archive and the real live site can say whether any
# moved, so this imports the archive, builds it, and compares.
#
# This file names no person, no site and no domain. The site's name and
# address come from PRESSLESS_SITE_NAME and PRESSLESS_SITE_ADDRESS, which the
# gate reads from machine-local keys. A failing run names addresses on the
# site, never its text.
"""INV-15: over the real archive, every page the live site serves as
`index.html`, under `pages/` or under `blog/` is built at the same address,
with the same title, heading, date line, pagination links and chip addresses.

It prints, and does not fail on, every other live file under a ROOT_OUTPUT
segment the build does not produce, every category label whose text differs
from today's (decision 7), and the build's duration.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest
from test_importer_archive import (
    PRESSLESS_ARCHIVE,
    PRESSLESS_LIVE_SITE,
    PRESSLESS_ORIGINALS,
    PRESSLESS_TEMPLATES,
    imported,  # noqa: F401 -- the fixture, shared rather than copied
)

from pressless import store
from pressless.builder import ROOT_OUTPUT, build, preview
from pressless.settings import Credentials, Settings

PRESSLESS_SITE_NAME = os.environ.get("PRESSLESS_SITE_NAME")
PRESSLESS_SITE_ADDRESS = os.environ.get("PRESSLESS_SITE_ADDRESS")

pytestmark = pytest.mark.archive

needs_everything = pytest.mark.skipif(
    not all((PRESSLESS_ARCHIVE, PRESSLESS_ORIGINALS, PRESSLESS_LIVE_SITE,
             PRESSLESS_TEMPLATES, PRESSLESS_SITE_NAME, PRESSLESS_SITE_ADDRESS)),
    reason="PRESS-0008: set PRESSLESS_ARCHIVE, PRESSLESS_ORIGINALS, PRESSLESS_LIVE_SITE, "
           "PRESSLESS_TEMPLATES, PRESSLESS_SITE_NAME and PRESSLESS_SITE_ADDRESS to run this",
)

_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_HEADING = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.S)
_TIME = re.compile(r"<time\b[^>]*>.*?</time>", re.S)
_PAGER = re.compile(r'<nav class="pager".*?</nav>', re.S)
_HREF = re.compile(r'href="([^"]*)"')
_CHIP = re.compile(r'<a class="chip[^"]*" href="([^"]*)"')


def _served(root: Path) -> list[str]:
    """The HTML pages §4.3 addresses: index.html, and every .html under
    pages/ or blog/."""
    found = ["index.html"] if (root / "index.html").is_file() else []
    for segment in ("pages", "blog"):
        found += sorted(path.relative_to(root).as_posix()
                        for path in (root / segment).rglob("*.html"))
    return found


def _elements(text: str) -> dict[str, object]:
    """INV-15's elements. The heading is the first <h1> after the site header,
    because the header carries a wordmark <h1> of its own."""
    body = text.split("</header>", 1)[-1]
    heading = _HEADING.search(body)
    main = body.split("<footer", 1)[0]
    pager = _PAGER.search(main)
    return {
        "title": (found.group(1).strip() if (found := _TITLE.search(text)) else None),
        "heading": heading.group(1).strip() if heading else None,
        "date line": _TIME.findall(main),
        "pagination links": _HREF.findall(pager.group(0)) if pager else [],
        "chip addresses": _CHIP.findall(main),
    }


@needs_everything
def test_the_first_publish_moves_no_page(imported, tmp_path):  # noqa: F811
    into_store, _report = imported
    live = Path(PRESSLESS_LIVE_SITE)
    assert live.is_dir(), "PRESSLESS_LIVE_SITE is set and does not name a folder"
    settings = Settings(
        site_folder=tmp_path / "site", repository="owner/name",
        site_name=PRESSLESS_SITE_NAME, site_address=PRESSLESS_SITE_ADDRESS,
        daily_prompt_filter="dailyprompt-*", untouchable=("assets",),
        credentials=Credentials(store="keyring", github_account="publishing-key",
                                google_account=None),
        analytics_property_id=None,
    )

    started = time.monotonic()
    built = build(into_store, settings, settings.site_folder)
    print(f"build: {time.monotonic() - started:.1f} s, {len(built.files)} files, "
          f"{len(built.filtered)} entries filtered")
    # PRESS-0012 § 3 decision 1's evidence: one page, against the whole site.
    newest = max(store.list_slugs(into_store, draft=False))
    started = time.monotonic()
    preview(into_store, settings, tmp_path / "preview",
            store.read(store.path_for(into_store, newest, draft=False)),
            photo_src=lambda name: name)
    print(f"preview: {time.monotonic() - started:.2f} s, one page")

    produced = set(built.files)
    missing, differing, labels = [], [], {}
    seen = {"date line": 0, "pagination links": 0, "chip addresses": 0}
    for address in _served(live):
        if address not in produced:
            missing.append(address)
            continue
        today = _elements((live / address).read_text(encoding="utf-8"))
        ours = _elements((settings.site_folder / address).read_text(encoding="utf-8"))
        for name in seen:
            seen[name] += bool(today[name])
        for name, value in today.items():
            if ours[name] == value:
                continue
            # Decision 7: a category page's label is derived from its slug, and a
            # label differing from today's is printed rather than failed.
            if address.startswith("blog/category/") and name in ("title", "heading"):
                labels[address.split("/")[2]] = (today["heading"], ours["heading"])
                continue
            differing.append(f"{address}: {name}")

    served = set(_served(live))
    others = sorted(
        name for path in live.rglob("*") if path.is_file()
        if (name := path.relative_to(live).as_posix()).split("/")[0] in ROOT_OUTPUT
        and name not in produced and name not in served)
    print(f"live files under a root output the build does not produce: {len(others)}")
    for name in others:
        print(f"  {name}")
    print(f"category labels differing from today's: {len(labels)}")
    for slug, (today_label, our_label) in sorted(labels.items()):
        print(f"  {slug}: today {today_label!r}, built {our_label!r}")

    print(f"pages compared: {len(served)}; pages carrying each element: {seen}")
    # A pattern that stopped matching today's markup would compare empty lists
    # and pass. Every element is on hundreds of live pages, so none may be absent.
    assert all(seen.values()), f"an element was found on no live page: {seen}"
    assert not missing, f"these live addresses are not built: {missing}"
    assert not differing, f"these pages differ from today's: {differing}"
