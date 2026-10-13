"""PRESS-0215 INV-1 and INV-5 over the live site's own pages.

The pages are the writer's, so they are read at run time from a path held
outside this repository (PRESSLESS_LIVE_SITE, which the gate sets from
`ants.pressless.liveSite`), and nothing from them is printed or written
here; a failure names the page alone. Skipped where the path is unset, as
the other archive tests are.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_blocks import _meaning

from pressless import blocks, builder

PRESSLESS_LIVE_SITE = os.environ.get("PRESSLESS_LIVE_SITE")

pytestmark = [
    pytest.mark.archive,
    pytest.mark.skipif(not PRESSLESS_LIVE_SITE,
                       reason="PRESS-0215: set PRESSLESS_LIVE_SITE to the live site's folder "
                              "to run this"),
]


def _pages() -> dict[str, str]:
    site = Path(PRESSLESS_LIVE_SITE)
    assert site.is_dir(), "PRESSLESS_LIVE_SITE is set and does not name a folder"
    paths = [site / "index.html", *sorted((site / "pages").glob("*.html"))]
    return {path.stem: path.read_bytes().decode("utf-8") for path in paths}


def test_the_live_pages_adopt_without_changing_what_they_show():
    """INV-1, INV-5 and INV-6 over every fixed page the live site holds: each
    adopted page writes back as it was, shows what the original showed, and
    is unchanged outside its `main`."""
    adopted_count = 0
    for name, text in _pages().items():
        adopted = blocks.adopt(text, builder.furniture_spans(name, text))
        if adopted is None:
            continue
        adopted_count += 1
        page = blocks.read(name, adopted)
        assert page is not None, name
        assert blocks.write(page) == adopted, name
        assert _meaning(blocks.unmarked(name, adopted)) == _meaning(text), name
        assert blocks.adopt(adopted, builder.furniture_spans(name, adopted)) == adopted, name
    print(f"live pages adopted: {adopted_count}")
