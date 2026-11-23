"""The finish-setting-up list at the foot of Your site (PRESS-0344, PRESS-0353).

Each item is read from the Store, so it ticks itself as the site gets there,
and the list goes once every item is done. Your site draws it.
"""
from __future__ import annotations

import html
from collections.abc import Callable
from pathlib import Path

from pressless import editor, publishing, starter, store, takeover
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
            # Where Home or the menu was never there, its link opens the
            # Pages screen, which adds it (PRESS-0423).
            ("checklist.home",
             _HOME if _held(folder, store.PAGES_FOLDER, "index") else editor.PAGES_ADDRESS,
             _own(folder, store.PAGES_FOLDER, "index",
                  lambda: starter.home_page(identity.name))),
            ("checklist.menu",
             editor.page_address(store.FURNITURE_FOLDER, "navigation")
             if _held(folder, store.FURNITURE_FOLDER, "navigation") else editor.PAGES_ADDRESS,
             _own(folder, store.FURNITURE_FOLDER, "navigation", starter.navigation)),
            # Done once something of his is on the web: no starter marker
            # (any publish that lands removes it, PRESS-0126 § 4.5), no
            # takeover owed (PRESS-0393), no imported site unpublished
            # (PRESS-0422), and something live (PRESS-0419). The link opens
            # the takeover where one is owed, else Home, else the Pages
            # screen, where a page is made.
            ("checklist.publish",
             publishing.TAKEOVER_ADDRESS if takeover.owed(folder)
             else _HOME if _held(folder, store.PAGES_FOLDER, "index")
             else editor.PAGES_ADDRESS,
             not starter.unpublished(folder) and not takeover.owed(folder)
             and not publishing.imported_unpublished(folder) and _holds_live(folder)),
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
    waiting to be pressed included. One the starter did not write is his own,
    and one he removed has nothing left to do. One never there is to do: a
    blank site has neither, and the Pages screen adds each (PRESS-0423). A
    site filled before starter.FILLED is compared with
    `started()`, the starter's text as worded today."""
    held = _held(folder, kind, name)
    wrote = starter.filled(folder)
    if not held:
        return wrote is not None and name in wrote
    if wrote is not None:
        return name not in wrote or any(starter.digest(text) != wrote[name] for text in held)
    return any(text != started() for text in held)


def _held(folder: Path, kind: str, name: str) -> list[str]:
    """The page or part's text, live and waiting, where each is held."""
    return [store.read_html(path) for path in
            (store.html_path_for(folder, kind, name, waiting=waiting) for waiting in (False, True))
            if path.is_file()]


def _holds_live(folder: Path) -> bool:
    """Whether anything of his is on the site: a published entry, or a page
    or part pressed to it. Nothing is, on a blank site (PRESS-0419)."""
    return bool(store.list_slugs(folder, draft=False)
                or any(store.list_html(folder, kind)
                       for kind in (store.PAGES_FOLDER, store.FURNITURE_FOLDER)))
