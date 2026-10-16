"""The Sites screen: the sites Pressless holds, opening another, and starting
a new one (PRESS-0223 § 4.6, docs/specs/PRESS-0223-several-sites.md); and
saving the open site to one file, or opening such a file as a site
(PRESS-0224 § 4.6).

Opening a site is a restart (§ 3 decision 4): sites.json names the site, and
the launcher's next Face opens it, every part registered again over its
folder, so nothing can go on acting on the site that was open.
"""
from __future__ import annotations

import datetime
import html
import secrets
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from pressless import settings, sitefile, sites, store
from pressless.face import SENTENCES, Download, Face, Request, Sentence, Site
from pressless.words import say

ADDRESS = "/sites"

# docs/design.md § Errors: the screen shows its own words for a refused file,
# and this sentence is the one any other path to Face.fail would show.
SENTENCES[sitefile.Refused] = Sentence(
    "failure.sitefile.Refused.what",
    Site.UNCHANGED,
    "failure.sitefile.Refused.next",
)


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

    def save(request: Request) -> Download:
        site = sites.open_site(own)
        target = own / f".saving-{secrets.token_hex(8)}.zip"
        try:
            sitefile.save(site, target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return Download(target, file_name(site))

    def open_file(path: Path) -> str:
        try:
            sitefile.open_into(path, own)
        except sitefile.Refused as exc:
            return _screen(own, say("sites_screen.file_newer" if exc.newer
                                    else "sites_screen.file_refused"))
        return _going(face, restart)

    face.add_page("GET", ADDRESS, screen)
    face.add_page("POST", f"{ADDRESS}/open", open_one)
    face.add_page("POST", f"{ADDRESS}/new", start)
    face.add_page("GET", f"{ADDRESS}/save", save)
    face.add_upload(f"{ADDRESS}/open-file", open_file, own)


def file_name(site: Path) -> str:
    """PRESS-0224 § 4.1: the site's name, kept to letters, digits, spaces and
    hyphens, and the day it was saved."""
    kept = "".join(c for c in name_of(site) if c.isalnum() or c in " -")
    return f'{" ".join(kept.split()) or say("sites_screen.file_unnamed")} ' \
           f"{datetime.date.today().isoformat()}.zip"


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
            f'<button>{say("sites_screen.new")}</button></form>'
            # PRESS-0224 § 4.6: the open site to one file, and a file to a site.
            f'<h2>{say("sites_screen.file_title")}</h2><p>{say("sites_screen.file_about")}</p>'
            f'<p class="nav"><a href="{ADDRESS}/save">{say("sites_screen.save")}</a></p>'
            f'<p><button type="button" id="open-site-file">{say("sites_screen.open_file")}'
            '</button><input type="file" id="site-file" accept=".zip" hidden></p>'
            f"<script>{_OPEN_SCRIPT}</script>")


# PRESS-0224 § 4.6: the chosen file is sent as the body, and the answer, the
# restarting page or this screen with what went wrong, replaces the page.
_OPEN_SCRIPT = r"""
(() => {
  const button = document.getElementById("open-site-file");
  const chooser = document.getElementById("site-file");
  button.addEventListener("click", () => { chooser.value = ""; chooser.click(); });
  chooser.addEventListener("change", async () => {
    const file = chooser.files[0];
    if (!file) return;
    button.disabled = true;
    button.textContent = say("script.sites.opening");
    const answer = await fetch("/sites/open-file", {method: "POST", body: file});
    const page = await answer.text();
    document.open();
    document.write(page);
    document.close();
  });
})();
"""
