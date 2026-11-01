"""The YouTube screen (PRESS-0081 § 4.3): a channel's public counts, and the steps
to get a key. Only this part reaches Credentials for that key (docs/design.md
rule 10). Nothing about writing or publishing depends on it, and the list's card
reads the kept figures and never YouTube.
"""
from __future__ import annotations

import dataclasses
import html
import time
from pathlib import Path

from pressless import credentials, dashboard, editor, insights, settings, sites, youtube
from pressless.face import SENTENCES, Face, Request, Sentence, Site, loaded_settings, render_notices
from pressless.words import say

PAGE = settings.YOUTUBE_ADDRESS
SETUP = PAGE + "/setup"
SHOWN = 50
_TERMS = "https://www.youtube.com/t/terms"
_PRIVACY = "https://www.google.com/policies/privacy"
_STEPS = ("youtube.step.1", "youtube.step.2", "youtube.step.3", "youtube.step.4")

# Their own sentences, as sites_screen gives sitefile's: Insights' say Google
# and to sign in, and neither is so here.
SENTENCES[youtube.YouTubeError] = Sentence(
    "failure.youtube.YouTubeError.what", Site.UNCHANGED, "failure.youtube.YouTubeError.next")
SENTENCES[youtube.Unreachable] = Sentence(
    "failure.youtube.Unreachable.what", Site.UNCHANGED, "failure.youtube.Unreachable.next")
SENTENCES[youtube.Refused] = Sentence(
    "failure.youtube.Refused.what", Site.UNCHANGED, "failure.youtube.Refused.next")
SENTENCES[youtube.RateLimited] = Sentence(
    "failure.youtube.RateLimited.what", Site.UNCHANGED, "failure.youtube.RateLimited.next")
SENTENCES[youtube.ChannelNotFound] = Sentence(
    "failure.youtube.ChannelNotFound.what", Site.UNCHANGED, "failure.youtube.ChannelNotFound.next")


def register(face: Face, folder: Path, *, client: insights.Transport | None = None) -> None:
    """Add the screen's pages and the list's card. `client` is a test's double."""
    folder = Path(folder)
    face.add_page("GET", PAGE, lambda request: _show(face, folder, client))
    face.add_page("GET", SETUP, lambda request: _setup(face, folder))
    face.add_page("POST", SETUP, lambda request: _save(face, folder, client, request))
    face.add_page("POST", PAGE + "/off", lambda request: _off(face, folder))
    face.add_to_list(lambda: _card(face, folder), above=True)


def _set_up(saved: settings.Settings) -> bool:
    return bool(saved.youtube_channel) and saved.credentials.youtube_account is not None


def _head() -> str:
    return dashboard._STYLE + f"<h1>{say('youtube.title')}</h1>"


def _back() -> str:
    return f'<p><a href="/">{say("script.undo.back")}</a></p>'


def _to_setup() -> str:
    return f'<p><a href="{SETUP}">{say("youtube.to_setup")}</a></p>'


def _card(face: Face, folder: Path) -> str:
    saved, _ = loaded_settings(face, folder)
    if saved is None or not _set_up(saved):
        return ""
    held = youtube.kept(folder, saved.youtube_channel, time.time())
    if held is None:
        line = say("youtube.card.ask", page=PAGE)
    else:
        line = say("youtube.card.read", title=html.escape(held.title), views=f"{held.views:,}",
                   when=dashboard._when(held.fetched_at), page=PAGE)
    return f'<section class="card"><h2>{say("youtube.title")}</h2><p>{line}</p></section>'


def _show(face: Face, folder: Path, client: insights.Transport | None) -> str:
    saved, shown = loaded_settings(face, folder)
    if saved is None:
        return shown + _head() + f'<p>{say("setup.first")}</p>' + _back()
    if not _set_up(saved):
        return shown + _head() + f'<p>{say("youtube.off", page=SETUP)}</p>' + _back()
    secret = say("failure.secret.youtube_key")
    try:
        key = credentials.read(saved.credentials.store, folder, saved.credentials.youtube_account)
    except credentials.FAILURES as exc:
        return shown + _head() + face.fail(exc, publishing=False, secret=secret) + _to_setup()
    try:
        report = youtube.read(saved.youtube_channel, key, folder, saved.site_folder, client=client)
    except (youtube.Refused, youtube.ChannelNotFound) as exc:
        return shown + _head() + face.fail(exc, publishing=False) + _to_setup() + _back()
    except insights.InsightsError as exc:
        return shown + _head() + face.fail(exc, publishing=False) + _back()
    return shown + _head() + _report(report) + _to_setup() + _back()


def _report(report: youtube.Report) -> str:
    e = html.escape
    when = dashboard._when(report.fetched_at)
    fresh = say("youtube.stale" if report.stale else "youtube.updated", when=when)
    subscribers = (say("youtube.hidden") if report.subscribers is None
                   else say("youtube.about", count=f"{report.subscribers:,}"))
    figures = (f"<tr><th scope='row'>{say('youtube.subscribers')}</th>"
               f'<td class="num">{subscribers}</td></tr>'
               f"<tr><th scope='row'>{say('youtube.views')}</th>"
               f'<td class="num">{report.views:,}</td></tr>'
               f"<tr><th scope='row'>{say('youtube.videos')}</th>"
               f'<td class="num">{report.video_count:,}</td></tr>')
    more = ""
    if len(report.videos) > SHOWN or len(report.videos) < report.video_count:
        more = "<p>" + say("youtube.some", shown=f"{min(SHOWN, len(report.videos)):,}",
                           read=f"{len(report.videos):,}", total=f"{report.video_count:,}") + "</p>"
    return (f"<h2>{e(report.title)}</h2><p>{say('youtube.source')}</p><p>{fresh}</p>"
            f'<table class="ranked"><tbody>{figures}</tbody></table>'
            + _videos(report.videos[:SHOWN]) + more
            + f"<p>{say('youtube.terms', terms=_TERMS, privacy=_PRIVACY)}</p>")


def _videos(videos: tuple[youtube.Video, ...]) -> str:
    if not videos:
        return ""
    labels = {"views": html.escape(say("youtube.views"), quote=True),
              "likes": html.escape(say("youtube.likes"), quote=True),
              "comments": html.escape(say("youtube.comments"), quote=True),
              "published": html.escape(say("youtube.published"), quote=True)}
    rows = []
    for video in videos:
        title = html.escape(video.title)
        if youtube.VIDEO_ID.fullmatch(video.id):
            title = (f'<a href="https://www.youtube.com/watch?v={video.id}" target="_blank" '
                     f'rel="noopener">{title}</a>')
        cells = "".join(f'<td class="num" data-label="{labels[name]}">{_number(value)}</td>'
                        for name, value in (("views", video.views), ("likes", video.likes),
                                            ("comments", video.comments)))
        rows.append(f'<tr><td>{title}</td><td class="num" data-label="{labels["published"]}">'
                    f"{html.escape(video.published[:10])}</td>{cells}</tr>")
    head = (f'<th scope="col">{say("youtube.video")}</th>'
            + "".join(f'<th scope="col" class="num">{labels[name]}</th>'
                      for name in ("published", "views", "likes", "comments")))
    return dashboard._panel(say("youtube.table"), head, "".join(rows), wide=True)


def _number(value: int | None) -> str:
    return say("youtube.hidden") if value is None else f"{value:,}"


def _setup(face: Face, folder: Path, *, hint: str = "", typed: str | None = None) -> str:
    saved, shown = loaded_settings(face, folder)
    if saved is None:
        return shown + f"<h1>{say('youtube.title')}</h1><p>{say('setup.first')}</p>"
    e = html.escape
    held = _set_up(saved)
    state = (say("youtube.on", channel=e(saved.youtube_channel)) if held
             else say("youtube.not_on"))
    channel = typed if typed is not None else (saved.youtube_channel or "")
    steps = "".join(f"<li>{say(key)}</li>" for key in _STEPS)
    off = (f'<form method="post" action="{PAGE}/off"><p><button type="submit">'
           f'{say("youtube.turn_off")}</button></p></form>') if held else ""
    return (shown + f"<h1>{say('youtube.title')}</h1><p>{state}</p>{off}"
            + f"<p>{say('youtube.about_key')}</p><ol>{steps}</ol>"
            + f'<form method="post" action="{SETUP}">'
            + f'<p><label for="channel">{say("youtube.box.channel")}</label><br>'
              f'<input id="channel" name="channel" size="50" value="{e(channel, quote=True)}"></p>'
            + f'<p><label for="key">{say("youtube.box.key")}</label><br>'
              '<input id="key" name="key" type="password" size="50" autocomplete="off"></p>'
            + (f"<p>{say('youtube.key_kept')}</p>" if held else "")
            + f'<p id="channel-hint" role="status">{e(hint)}</p>'
            + f'<p><button type="submit">{say("youtube.save")}</button></p></form>'
            + f"<p>{say('youtube.terms', terms=_TERMS, privacy=_PRIVACY)}</p>"
            + f'<p><a href="/setup">{say("setup.back")}</a></p>')


def _save(face: Face, folder: Path, client: insights.Transport | None, request: Request) -> str:
    saved, shown = loaded_settings(face, folder)
    if saved is None:
        return _setup(face, folder)
    form = editor.form_fields(request)
    typed = form.get("channel", "")

    def refuse(words: str) -> str:
        return _setup(face, folder, hint=say(words), typed=typed)

    try:
        channel = youtube.parse_channel(typed)
    except ValueError:
        return refuse("youtube.hint.channel")
    new_key = form.get("key", "").strip()
    try:
        key = new_key or credentials.read(saved.credentials.store, folder,
                                          saved.credentials.youtube_account or "")
    except credentials.FAILURES:
        return refuse("youtube.hint.key")
    try:
        title = youtube.check(channel, key, client=client)
    except youtube.ChannelNotFound:
        return refuse("youtube.hint.not_found")
    except youtube.Refused:
        return refuse("youtube.hint.refused")
    except insights.InsightsError:
        return refuse("youtube.hint.unreachable")
    account = sites.account("youtube", folder)
    candidate = dataclasses.replace(
        saved, youtube_channel=channel,
        credentials=dataclasses.replace(saved.credentials, youtube_account=account))
    try:
        if new_key:
            credentials.write(saved.credentials.store, folder, account, new_key)
    except credentials.FAILURES as exc:
        return (shown + f"<h1>{say('youtube.title')}</h1>"
                + face.fail(exc, publishing=False, secret=say("failure.secret.youtube_key"))
                + _to_setup())
    if channel != saved.youtube_channel:
        try:
            youtube.forget(folder)
        except OSError:
            pass  # kept() answers only for the channel it holds
    with face.capture() as notices:
        settings.save(folder, candidate)
    return (shown + render_notices(notices) + f"<h1>{say('youtube.title')}</h1>"
            + f"<p>{say('youtube.saved', title=html.escape(title), page=PAGE)}</p>" + _back())


def _off(face: Face, folder: Path) -> str:
    """As google_setup._off: whatever one removal does, the next still runs, and
    the page says what may remain."""
    saved, shown = loaded_settings(face, folder)
    if saved is None:
        return _setup(face, folder)
    removed = True
    try:
        credentials.delete(saved.credentials.store, folder, sites.account("youtube", folder))
    except credentials.FAILURES:
        removed = False
    try:
        youtube.forget(folder)
    except OSError:
        removed = False
    candidate = dataclasses.replace(
        saved, youtube_channel=None,
        credentials=dataclasses.replace(saved.credentials, youtube_account=None))
    with face.capture() as notices:
        settings.save(folder, candidate)
    return (shown + render_notices(notices) + f"<h1>{say('youtube.title')}</h1>"
            + f"<p>{say('youtube.off.done')}</p>"
            + ("" if removed else f"<p>{say('youtube.not_removed')}</p>")
            + f'<p><a href="/setup">{say("setup.back")}</a></p>')
