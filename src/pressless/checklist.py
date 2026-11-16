"""The finish-setting-up list at the foot of Your site (PRESS-0344, PRESS-0353).

Each item is read from the Store, so it ticks itself as the site gets there,
and the list goes once every item is done. Your site draws it.
"""
from __future__ import annotations

import html
from collections.abc import Callable
from pathlib import Path

from pressless import editor, starter, store
from pressless.words import say

_HOME = editor.page_address(store.PAGES_FOLDER, "index")


def render(folder: Path) -> str:
    """The list, or "" where every item is done or the Store cannot say."""
    try:
        identity = store.read_identity(folder)
        if identity is None:
            return ""
        items = (
            ("checklist.describe", "/setup", bool(identity.description)),
            ("checklist.icon", "/setup", bool(identity.icon)),
            ("checklist.home", _HOME, _own(folder, store.PAGES_FOLDER, "index",
                                           lambda: starter.home_page(identity.name))),
            ("checklist.menu", editor.page_address(store.FURNITURE_FOLDER, "navigation"),
             _own(folder, store.FURNITURE_FOLDER, "navigation", starter.navigation)),
            # Any publish that lands removes the starter's marker (PRESS-0126
            # § 4.5), a page's Press to site included, so the link opens Home,
            # the starter's first page, rather than Publish.
            ("checklist.publish", _HOME, not starter.unpublished(folder)),
        )
    except store.StoreError:
        return ""
    if all(done for _, _, done in items):
        return ""
    rows = "".join(
        f'<li class="{"done" if done else "to-do"}">'
        f'<span role="img" aria-label="{say("checklist.done" if done else "checklist.to_do")}">'
        f'{"✔" if done else "☐"}</span> '
        f'<a href="{html.escape(address, quote=True)}">{say(key)}</a></li>'
        for key, address, done in items)
    count = say("checklist.count", done=sum(done for _, _, done in items), total=len(items))
    return (f'<section class="card" id="checklist"><h2>{say("checklist.title")}</h2>'
            f"<p>{count}</p><ul>{rows}</ul></section>")


def _own(folder: Path, kind: str, name: str, started: Callable[[], str]) -> bool:
    """Whether the page or part differs from what the starter wrote, a change
    waiting to be pressed included. One that is gone, or that the starter did
    not write, has nothing left to do. A site filled before starter.FILLED is
    compared with `started()`, the starter's text as worded today."""
    held = [store.read_html(path) for path in
            (store.html_path_for(folder, kind, name, waiting=waiting) for waiting in (False, True))
            if path.is_file()]
    wrote = starter.filled(folder)
    if wrote is not None:
        return not held or name not in wrote or any(
            starter.digest(text) != wrote[name] for text in held)
    return not held or any(text != started() for text in held)
