"""Your site, the first screen: a tile for each part of the site (PRESS-0353 § 4.3).

Every figure comes from the Store or a cache, so the screen never waits on
the network (ADR-0005). A part this module does not know reaches the screen
through Face.add_piece.
"""
from __future__ import annotations

import html
import urllib.parse
from pathlib import Path

from pressless import (
    builder,
    checklist,
    dashboard,
    editor,
    insights,
    look,
    pressing,
    settings,
    store,
)
from pressless.face import Face, message_box, render_notices
from pressless.words import say


def register(face: Face, folder: Path) -> None:
    """Add GET / to `face`. `folder` is the open site's."""
    folder = Path(folder)
    face.add_page("GET", "/", lambda request: _show(face, folder))


def _show(face: Face, folder: Path) -> str:
    """§ 4.3, in an order that does not change with the site's state."""
    with face.capture() as notices:
        site = editor._site_line(folder)
        tiles = "".join(tile(folder) for tile in (_pages, _journal, _look))
        tiles += _parts() + _files(folder) + _visitors(face, folder)
        below = checklist.render(folder)
    with face.capture():  # its reads repeat the tiles', and Pages shows the rest
        waiting = _waiting(folder)
    # PRESS-0235 § 4.5: the press row is the undo line, and Publish shares it.
    said, running, ended = pressing.shown("")
    buttons = (f'{face.view_site()} <button type="button" data-editor="publish" '
               f'data-publish-site>{say("overview.publish")}</button> ')
    return (render_notices(notices) + f"<h1>{say('face.your_site')}</h1>" + site
            + editor._undo_row(said, running=running, before=buttons) + waiting
            + "".join(face.pieces("site-notices"))
            # PRESS-0236: a press's failure opens over the screen.
            + message_box("failure", ended or "", forgets=True)
            + '<div id="undo-result"></div><div id="listing">'
            + f'<div class="tiles">{tiles}{"".join(face.pieces("site-tiles"))}</div>'
            + below + "".join(face.pieces("site-below")) + "</div>"
            + f"<script>{editor._UNDO_SCRIPT}{_PUBLISH_SCRIPT}</script>")


def _waiting(folder: Path) -> str:
    """PRESS-0364: how many changes are not on the site yet, by kind, each
    kind linking to the screen that publishes it. Counted from the Store
    alone, so a change only GitHub holds is missed. Its own line, apart from
    Publish, which sends none of them. Nothing waiting, or nothing readable,
    draws nothing."""
    try:
        counts = [
            (len(store.list_html(folder, store.PAGES_FOLDER, waiting=True)),
             ("overview.waiting.pages.one", "overview.waiting.pages.many"), editor.PAGES_ADDRESS),
            (len(store.list_html(folder, store.FURNITURE_FOLDER, waiting=True)),
             ("overview.waiting.parts.one", "overview.waiting.parts.many"), editor.PAGES_ADDRESS),
        ]
        if store.journal_on(folder):  # off, no entry can reach the site
            entries, _ = editor.read_entries(folder)
            counts.append((
                len(entries.drafts) + len(entries.unreadable[True]) + len(entries.changed),
                ("overview.waiting.entries.one", "overview.waiting.entries.many"),
                editor.JOURNAL_ADDRESS))
    except store.StoreError:
        return ""
    total = sum(count for count, _, _ in counts)
    if not total:
        return ""
    kinds = ", ".join(
        f'<a href="{html.escape(address, quote=True)}">'
        f'{say(keys[0] if count == 1 else keys[1], count=count)}</a>'
        for count, keys, address in counts if count)
    said = say("overview.waiting.one" if total == 1 else "overview.waiting.many",
               count=total, kinds=kinds)
    return f'<p class="waiting">{said}</p>'


def _tile(heading: str, figures: str, links: str) -> str:
    """One part of the site: its heading, a line of figures where it has one,
    and its links. A figure that cannot be read is left out (§ 6)."""
    line = f"<p>{figures}</p>" if figures else ""
    return f'<section class="card tile"><h2>{say(heading)}</h2>{line}<p>{links}</p></section>'


def _link(address: str, key: str) -> str:
    return f'<a href="{html.escape(address, quote=True)}">{say(key)}</a>'


def _pages(folder: Path) -> str:
    try:
        names = sorted(store.list_html(folder, store.PAGES_FOLDER))
    except store.StoreError:
        names = None
    figures = ("" if names is None else ", ".join(
        html.escape(say("editor.pages.home") if name == "index" else builder.label(name))
        for name in names))
    return _tile("face.pages", figures, _link(editor.PAGES_ADDRESS, "overview.open_pages"))


def _journal(folder: Path) -> str:
    try:
        on = store.journal_on(folder)
        entries, _ = editor.read_entries(folder)  # a working copy is no draft
    except store.StoreError:
        figures = ""
    else:
        published = len(entries.published) + len(entries.unreadable[False])
        drafts = len(entries.drafts) + len(entries.unreadable[True])
        figures = (say("overview.journal.figures", published=published,
                       drafts=say("overview.drafts.one" if drafts == 1 else "overview.drafts.many",
                                  count=drafts))
                   if on else say("overview.journal.off"))
    return _tile("face.journal", figures, _link(editor.JOURNAL_ADDRESS, "overview.open_journal"))


def _look(folder: Path) -> str:
    try:
        chosen = look.read(folder)
    except store.StoreError:
        chosen = None
    figures = say(f"setup.look.{chosen.layout}") if chosen is not None else ""
    return _tile("face.look", figures, _link("/look", "overview.open_look"))


def _parts() -> str:
    """Each part of every page opens its own editor."""
    links = " ".join(
        _link("/page?" + urllib.parse.urlencode({"kind": store.FURNITURE_FOLDER, "name": name}),
              key)
        for name, key in (("navigation", "editor.pages.navigation"),
                          ("header", "editor.pages.header"), ("footer", "editor.pages.footer")))
    return _tile("overview.parts", "", links)


def _files(folder: Path) -> str:
    try:
        count = len(store.list_files(folder))
    except (store.StoreError, OSError):
        figures = ""
    else:
        figures = say("overview.files.one" if count == 1 else "overview.files.many", count=count)
    return _tile("face.files", figures, _link("/files", "overview.open_files"))


def _visitors(face: Face, folder: Path) -> str:
    """The cached figure only: Google is never asked from here (§ 4.3)."""
    try:
        saved = settings.load(folder)
    except (settings.NotSetUp, settings.SettingsError):
        saved = None
    if saved is None or not dashboard._set_up(saved):
        figures = say("overview.visitors.not_set_up")
    else:
        kept = insights._cached(insights.cache_path(folder), dashboard.DEFAULT_DAYS)
        figures = (say("overview.visitors.none_yet") if kept is None else say(
            "overview.visitors.read", people=dashboard._people(kept.people),
            window=dashboard._sentence(dashboard.DEFAULT_DAYS)))
    return _tile("face.visitors", figures, _link(dashboard.PAGE, "overview.open_visitors"))


# PRESS-0353 § 4.3: Publish asks what the site as it stands would change, in
# PRESS-0345's box, then presses it as a page's Publish does.
_PUBLISH_SCRIPT = """
(() => {
  const button = document.querySelector("button[data-publish-site]");
  if (!button) return;
  const said = document.getElementById("undo-status");
  const failure = document.getElementById("failure");
  button.addEventListener("click", async () => {
    if (window.presslessPress.asking()) return;
    button.disabled = true;
    try {
      said.textContent = say("script.press.checking");
      if (!await window.presslessCheck(new URLSearchParams())) {
        said.textContent = "";
        return;
      }
      said.textContent = say("script.press.publishing");
      const reply = await (await fetch("/publish/site", {method: "POST"})).json();
      if (window.presslessPress.busy(reply)) return;
      said.textContent = reply.published
        ? say("script.press.published") : say("script.press.not_published");
      failure.innerHTML = (reply.notices || "") + (reply.failure || "");
      if (reply.published) window.presslessPress.viewable();
    } catch (error) {
      said.textContent = say("script.press.not_published");
    } finally {
      button.disabled = false;
    }
  });
})();
"""
