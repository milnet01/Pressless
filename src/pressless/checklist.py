"""The finish-setting-up list at the foot of Your site (PRESS-0344, PRESS-0353).

Each item is read from the Store, so it ticks itself as the site gets there,
and the list goes once every item is done. Your site draws it.
"""
from __future__ import annotations

import html
from pathlib import Path

from pressless import starter, store
from pressless.words import say

_HOME = "/page?kind=pages&name=index"


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
                                           starter.home_page(identity.name))),
            ("checklist.menu", "/page?kind=furniture&name=navigation",
             _own(folder, store.FURNITURE_FOLDER, "navigation", starter.navigation())),
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


def _own(folder: Path, kind: str, name: str, started: str) -> bool:
    """Whether the page or part differs from the starter's, a change waiting to
    be pressed included. One that is gone has nothing left to do."""
    held = [store.read_html(path) for path in
            (store.html_path_for(folder, kind, name, waiting=waiting) for waiting in (False, True))
            if path.is_file()]
    return not held or any(text != started for text in held)
