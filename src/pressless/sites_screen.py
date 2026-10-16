"""The Sites screen: the sites Pressless holds, opening another, and starting
a new one (PRESS-0223 § 4.6, docs/specs/PRESS-0223-several-sites.md).

Opening a site is a restart (§ 3 decision 4): sites.json names the site, and
the launcher's next Face opens it, every part registered again over its
folder, so nothing can go on acting on the site that was open.
"""
from __future__ import annotations

import html
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from pressless import settings, sites, store
from pressless.face import Face, Request
from pressless.words import say

ADDRESS = "/sites"


def name_of(site: Path) -> str:
    """The site's own name, else the repository it publishes to, else the
    words for a site not set up yet."""
    try:
        identity = store.read_identity(site)
    except store.StoreError:
        identity = None
    if identity is not None and identity.name.strip():
        return identity.name
    try:
        return settings.load(site).repository
    except (settings.NotSetUp, settings.SettingsError):
        return say("sites_screen.unnamed")


def register(face: Face, own: Path, restart: Callable[[], None]) -> None:
    """Add `GET /sites`, `POST /sites/open` and `POST /sites/new` to `face`.
    `own` is Pressless's own folder; `restart` runs once the answer is sent,
    as restarting.register's does."""
    own = Path(own)

    def screen(request: Request) -> str:
        return _screen(own)

    def open_one(request: Request) -> str:
        form = urllib.parse.parse_qs(request.body.decode("utf-8", "replace"))
        try:
            sites.choose(own, form.get("site", [""])[0])
        except ValueError:
            return _screen(own, say("sites_screen.not_a_site"))
        return _going(face, restart)

    def start(request: Request) -> str:
        sites.choose(own, sites.new_site(own).name)
        return _going(face, restart)

    face.add_page("GET", ADDRESS, screen)
    face.add_page("POST", f"{ADDRESS}/open", open_one)
    face.add_page("POST", f"{ADDRESS}/new", start)


def _going(face: Face, restart: Callable[[], None]) -> str:
    face.after_reply(restart)
    return (f'<h1>{say("restarting.going.title")}</h1>'
            f'<p>{say("restarting.going")}</p>')


def _screen(own: Path, hint: str = "") -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    current = sites.open_site(own)
    rows = []
    for site in sites.all_sites(own):
        named = html.escape(name_of(site))
        if site == current:
            rows.append(f"<li><b>{named}</b> {say('sites_screen.open_now')}</li>")
        else:
            rows.append(f'<li><form method="post" action="{ADDRESS}/open">{named} '
                        f'<input type="hidden" name="site" value="{attr(site.name)}">'
                        f'<button>{say("sites_screen.open")}</button></form></li>')
    said = f'<p class="hint" role="alert">{html.escape(hint)}</p>' if hint else ""
    return (f'<p class="nav"><a href="/">{say("face.your_writing")}</a></p>'
            f'<h1>{say("sites_screen.title")}</h1><p>{say("sites_screen.about")}</p>'
            f'{said}<ul class="sites">{"".join(rows)}</ul>'
            f'<form method="post" action="{ADDRESS}/new">'
            f'<button>{say("sites_screen.new")}</button></form>')
