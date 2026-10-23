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

from pressless import backups, sitefile, sites
from pressless.face import SENTENCES, Download, Face, Request, Sentence, Site, file_box
from pressless.words import say

ADDRESS = "/sites"

# docs/design.md § Errors: the screen shows its own words for a refused file,
# and this sentence is the one any other path to Face.fail would show.
SENTENCES[sitefile.Refused] = Sentence(
    "failure.sitefile.Refused.what",
    Site.UNCHANGED,
    "failure.sitefile.Refused.next",
)


def register(face: Face, own: Path, restart: Callable[[], None]) -> None:
    """Add the Sites screen's routes to `face`: `GET /sites`, `POST
    /sites/open`, `POST /sites/new`, `GET /sites/save`, `POST
    /sites/backups` and the upload `POST /sites/open-file`.
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

    def save(request: Request) -> Download | str:
        # PRESS-0221: the move wizard saves each site by name; with none, the
        # open one.
        named = request.query.get("site")
        site = sites.open_site(own)
        if named is not None:
            held = {path.name: path for path in sites.all_sites(own)}
            if named not in held:
                return _screen(own, say("sites_screen.not_a_site"))
            site = held[named]
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

    def keep_backups_in(request: Request) -> str:
        form = urllib.parse.parse_qs(request.body.decode("utf-8", "replace"))
        try:
            backups.set_folder(own, form.get("folder", [""])[0])
        except ValueError:
            return _screen(own, say("sites_screen.backups.not_a_folder"))
        except OSError as exc:
            return _screen(own, face.fail(exc, publishing=False), raw=True)
        return _screen(own, say("sites_screen.backups.chosen"))

    face.add_page("GET", ADDRESS, screen)
    face.add_page("POST", f"{ADDRESS}/open", open_one)
    face.add_page("POST", f"{ADDRESS}/new", start)
    face.add_page("GET", f"{ADDRESS}/save", save)
    face.add_page("POST", f"{ADDRESS}/backups", keep_backups_in)
    face.add_upload(f"{ADDRESS}/open-file", open_file, own)


def file_name(site: Path) -> str:
    """PRESS-0224 § 4.1: the site's name and the day it was saved."""
    return f"{sitefile.stem(site)} {datetime.date.today().isoformat()}.zip"


def _going(face: Face, restart: Callable[[], None]) -> str:
    face.after_reply(restart)
    return (f'<h1>{say("restarting.going.title")}</h1>'
            f'<p>{say("restarting.going")}</p>')


def _screen(own: Path, hint: str = "", *, raw: bool = False) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    current = sites.open_site(own)
    rows = []
    for site in sites.all_sites(own):
        named = html.escape(sitefile.name_of(site))
        if site == current:
            rows.append(f"<li><b>{named}</b> {say('sites_screen.open_now')}</li>")
        else:
            rows.append(f'<li><form method="post" action="{ADDRESS}/open">{named} '
                        f'<input type="hidden" name="site" value="{attr(site.name)}">'
                        f'<button>{say("sites_screen.open")}</button></form></li>')
    said = (hint if raw else f'<p class="hint" role="alert">{html.escape(hint)}</p>'
            ) if hint else ""
    # PRESS-0225: where the daily backups go, and what went wrong last.
    chosen = backups.folder_of(own) != own.parent / backups.DEFAULT_FOLDER
    went_wrong = backups.trouble(own)
    trouble = (f'<p class="hint" role="alert">{html.escape(went_wrong)}</p>'
               if went_wrong else "")
    where = say("sites_screen.backups.chosen_folder" if chosen
                else "sites_screen.backups.default_folder")
    value = attr(str(backups.folder_of(own))) if chosen else ""
    return (f'<p class="nav"><a href="/">{say("face.your_writing")}</a></p>'
            f'<h1>{say("sites_screen.title")}</h1><p>{say("sites_screen.about")}</p>'
            f'{said}<ul class="sites">{"".join(rows)}</ul>'
            f'<form method="post" action="{ADDRESS}/new">'
            f'<button>{say("sites_screen.new")}</button></form>'
            # PRESS-0224 § 4.6: the open site to one file, and a file to a site.
            f'<h2>{say("sites_screen.file_title")}</h2><p>{say("sites_screen.file_about")}</p>'
            f'<p class="nav"><a href="{ADDRESS}/save">{say("sites_screen.save")}</a></p>'
            + file_box("site-file", ".zip", f"{ADDRESS}/open-file",
                       say("sites_screen.open_file"), sending="script.sites.opening")
            + f'<h2>{say("sites_screen.backups.title")}</h2>'
            f'<p>{say("sites_screen.backups.about")}</p><p>{where}</p>{trouble}'
            f'<form method="post" action="{ADDRESS}/backups"><label>'
            f'{say("sites_screen.backups.folder")} <input name="folder" value="{value}" '
            'autocomplete="off"></label> '
            f'<button>{say("sites_screen.backups.use")}</button></form>'
            + _move_wizard(own))


def _move_wizard(own: Path) -> str:
    """PRESS-0221: the move to a new computer, as a dialog over this screen
    (the user, 2026-10-05), one step at a time. Each site saves to its own
    file, which the new computer opens on its Sites screen."""
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    saves = "".join(
        f'<a href="{ADDRESS}/save?site={attr(site.name)}">'
        f'{html.escape(say("sites_screen.move.save_one", site=sitefile.name_of(site)))}'
        "</a>" for site in sites.all_sites(own))
    steps = (
        ("sites_screen.move.step_save", f'<p>{say("sites_screen.move.save")}</p>'
                                        f'<p class="nav">{saves}</p>'),
        ("sites_screen.move.step_carry", f'<p>{say("sites_screen.move.carry")}</p>'),
        ("sites_screen.move.step_open", f'<p>{say("sites_screen.move.open")}</p>'),
    )
    shown = "".join(
        f'<section data-step="{number}"{"" if number == 1 else " hidden"}>'
        f'<h3>{say(title)}</h3>{body}</section>'
        for number, (title, body) in enumerate(steps, start=1))
    return (f'<p><button type="button" data-help="move-wizard" aria-haspopup="dialog">'
            f'{say("sites_screen.move.button")}</button></p>'
            f'<dialog id="move-wizard" aria-labelledby="move-wizard-title">'
            f'<h2 id="move-wizard-title">{say("sites_screen.move.title")}</h2>{shown}'
            f'<p><button type="button" data-move="back" disabled>{say("wizard.back")}</button> '
            f'<button type="button" data-move="next">{say("wizard.next")}</button> '
            f'<button type="button" data-close>{say("wizard.close")}</button></p>'
            f"</dialog><script>{_MOVE_SCRIPT}</script>")


# PRESS-0221: Next and Back show one step of the dialog at a time; the Face's
# own script opens it and closes it.
_MOVE_SCRIPT = r"""
(() => {
  const box = document.getElementById("move-wizard");
  const steps = [...box.querySelectorAll("[data-step]")];
  const back = box.querySelector("[data-move=back]");
  const next = box.querySelector("[data-move=next]");
  let at = 0;
  const show = () => {
    steps.forEach((step, number) => { step.hidden = number !== at; });
    back.disabled = at === 0;
    next.disabled = at === steps.length - 1;
  };
  back.addEventListener("click", () => { at = Math.max(0, at - 1); show(); });
  next.addEventListener("click", () => { at = Math.min(steps.length - 1, at + 1); show(); });
  box.addEventListener("close", () => { at = 0; show(); });
})();
"""
