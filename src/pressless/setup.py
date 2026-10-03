"""Setup (PRESS-0021): the publishing key once, and the same page as Settings.

The contract is docs/specs/PRESS-0021-setup.md. One page at `/setup`: with no
settings file it is first-run setup, and afterwards the same page is Settings.
It checks the answers, asks GitHub what sits at the repository root, stores
the key, derives the untouchable list, and saves Settings last (§ 4.6).

It lives in the Face because only the Face knows what order things happen in
and only the Face reaches Credentials (`docs/design.md` rules 1 and 10). It
never reads the Store (§ 3 decision 9) and never runs Import.
"""

from __future__ import annotations

import dataclasses
import html
import urllib.parse
from collections.abc import Callable, Iterable
from pathlib import Path

from pressless import (
    builder,
    credentials,
    google_signin,
    publisher,
    settings,
    shortcuts,
    starter,
)
from pressless.face import Face, Request, render_notices
from pressless.store import StoreError

SITE_FOLDER = "site"                  # inside Pressless's own folder
GITHUB_ACCOUNT = "github"             # the account the publishing key is filed under
KEY = "your publishing key"           # the {secret} noun (PRESS-0011 § 4.2)

# The answers a refused SettingsError can name; any other key is a failure.
_ANSWERED = ("repository", "site_name", "site_address", "measurement_id")
_FIELDS = ("repository", "site_name", "site_address", "daily_prompt_filter",
           "measurement_id")

_HINTS = {
    "repository": "Type it as owner/name, the way GitHub shows it.",
    "site_name": "Type the site's name on one line.",
    "site_address": "Type the site's full address, starting with https://.",
    # PRESS-0199 § 4.4.
    "measurement_id": "Type the measurement id as Google shows it: G- and then "
                      "capital letters and numbers, or leave it empty.",
}
_NO_SUCH_REPOSITORY = (
    "GitHub has no repository by that name that this key can reach."
)
_KEY_MISSING = "Paste your publishing key."
_KEY_MALFORMED = "A publishing key has no spaces or line breaks. Paste it again."

_CREDENTIAL_FAILURES = (credentials.NoStore, credentials.NotStored, credentials.CredentialError)

SHORTCUTS = "/setup/shortcuts"        # PRESS-0183


def untouchable(root: Iterable[str]) -> tuple[str, ...]:
    """The root entries the Builder does not produce, compared with casefold
    on both sides (§ 4.7, PRESS-0009 § 4.4). ROOT_OUTPUT is read at call time,
    never copied."""
    produced = {name.casefold() for name in builder.ROOT_OUTPUT}
    return tuple(sorted(e for e in root if e.rstrip("/").casefold() not in produced))


def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None,
             shortcut_places: Callable[[], shortcuts.Places | None] = shortcuts.places,
             ) -> None:
    """Add `GET /setup`, `POST /setup` and `POST /setup/shortcuts` to `face`.
    `folder` is Pressless's own folder, the one `face.serve` was handed;
    `shortcut_places` says where this copy's shortcuts go (PRESS-0183)."""
    folder = Path(folder)

    def page(request: Request) -> str:
        return _setup(face, folder, request, transport, shortcut_places)

    def change(request: Request) -> str:
        return _shortcuts(face, shortcut_places(), request)

    face.add_page("GET", "/setup", page)
    face.add_page("POST", "/setup", page)
    face.add_page("POST", SHORTCUTS, change)


def _setup(face: Face, folder: Path, request: Request,
           transport: publisher.Transport | None,
           shortcut_places: Callable[[], shortcuts.Places | None]) -> str:
    # § 4.2: which page he sees.
    refused: settings.SettingsError | None = None
    saved: settings.Settings | None = None
    with face.capture() as notices:
        try:
            saved = settings.load(folder)
        except settings.NotSetUp:
            pass
        except settings.SettingsError as exc:
            # A site_folder refusal is a file carried from another machine,
            # and is first run. Anything else is never written over.
            if exc.key != "site_folder":
                refused = exc

    if refused is not None:
        return render_notices(notices) + face.fail(refused, publishing=False)
    # PRESS-0126 § 4.4: the starter site is offered on a Store holding no site.
    try:
        offer = starter.offered(folder)
    except StoreError as exc:
        return render_notices(notices) + face.fail(exc, publishing=False)
    if request.method != "POST":
        values = _values_from(saved)
        # PRESS-0183: Settings shows the shortcuts as they are now.
        where = shortcut_places() if saved is not None else None
        return (render_notices(notices)
                + _form(saved is not None, values, {}, google_on=_google_on(saved),
                        start=(saved is None) if offer else None)
                + (_shortcut_form(where, shortcuts.present(where)) if where else ""))

    answers = _read_answers(request.body)
    # PRESS-0183: first run offers them, ticked, once setup is done.
    where = shortcut_places() if saved is None else None
    return render_notices(notices) + _submit(face, folder, saved, answers, transport,
                                             offer, where)


def _submit(face: Face, folder: Path, saved: settings.Settings | None,
            answers: dict[str, str], transport: publisher.Transport | None,
            offer: bool, where: shortcuts.Places | None) -> str:
    first_run = saved is None
    box = (answers["start"] == "starter") if offer else None   # PRESS-0126 § 4.4
    typed_key = answers["key"]
    values = {name: answers[name] for name in _FIELDS}
    hints: dict[str, str] = {}

    # § 4.4: the key.
    if not typed_key:
        if first_run:
            hints["key"] = _KEY_MISSING
    elif not (typed_key.isascii() and typed_key.isprintable()
              and not any(c.isspace() for c in typed_key)):
        hints["key"] = _KEY_MALFORMED

    # § 4.4: the rest, against the rules the next launch reads them with.
    candidate = _candidate(folder, saved, values)
    try:
        settings.check(candidate)
    except settings.SettingsError as exc:
        if exc.key not in _ANSWERED:
            return face.fail(exc, publishing=False)
        hints[exc.key] = _HINTS[exc.key]
    if hints:
        return _form(not first_run, values, hints, google_on=_google_on(saved),
                     start=box)

    # § 4.6 step 1: the key in hand.
    key = typed_key
    if not key:
        try:
            key = credentials.read(saved.credentials.store, folder,
                                   saved.credentials.github_account)
        except _CREDENTIAL_FAILURES as exc:
            return _credential_failure(face, exc)

    # Step 2: ask GitHub.
    try:
        entries = publisher.root_entries(candidate, key, transport)
    except publisher.RemoteStateMissing:
        # root_entries reads commits/HEAD first, and a 404 there is this type,
        # never RepositoryMissing (§ 4.6 step 2).
        return _form(not first_run, values, {"repository": _NO_SUCH_REPOSITORY},
                     google_on=_google_on(saved), start=box)
    except publisher.PublishError as exc:
        return face.fail(exc, publishing=False)

    # Step 3: choose the store, first run only.
    store = candidate.credentials.store
    choice = None
    if first_run:
        try:
            choice = credentials.choose()
        except _CREDENTIAL_FAILURES as exc:
            return _credential_failure(face, exc)
        store = choice.store

    # Step 4: store the key, only when he typed one.
    if typed_key:
        try:
            credentials.write(store, folder, candidate.credentials.github_account, typed_key)
        except _CREDENTIAL_FAILURES as exc:
            return _credential_failure(face, exc)

    # PRESS-0126 § 4.4: fill, only where the box was ticked and the starter is
    # still offered. Before the save, so a failure leaves first run where it was.
    filled = False
    with face.capture() as filling:
        try:
            if answers["start"] == "starter" and starter.offered(folder):
                starter.fill(folder, candidate.site_name)
                filled = True
        except StoreError as exc:
            fill_failure: str | None = face.fail(exc, publishing=False)
        else:
            fill_failure = None
    if fill_failure is not None:
        return render_notices(filling) + fill_failure

    # Step 5: save, last.
    final = dataclasses.replace(
        candidate,
        untouchable=untouchable(entries),
        credentials=dataclasses.replace(candidate.credentials, store=store),
    )
    with face.capture() as notices:
        try:
            settings.save(folder, final)
        except settings.SettingsError as exc:
            failed = face.fail(exc, publishing=False)
        else:
            failed = None
    if failed is not None:
        return render_notices(filling) + render_notices(notices) + failed
    privacy, privacy_failure = _privacy(face, folder, final)
    return (render_notices(filling) + render_notices(notices) + privacy_failure
            + _done(final, choice, filled) + privacy
            + (_shortcut_form(where, (True, True)) if where else ""))


def _privacy(face: Face, folder: Path, final: settings.Settings) -> tuple[str, str]:
    """PRESS-0199 § 4.5: after a save holding a measurement id, the Privacy
    page and its footer link where absent. Returns what to say, and a failure
    fragment; the id is saved either way, and the next save retries."""
    if final.measurement_id is None:
        return "", ""
    with face.capture() as notices:
        try:
            page, link = starter.add_privacy(folder, final.site_name)
        except StoreError as exc:
            return "", render_notices(notices) + (
                "<p>Visitor counting is on, but the Privacy page or its link could "
                "not be added. Saving again tries once more.</p>"
                + face.fail(exc, publishing=False))
    said = []
    if page:
        said.append("<p>Your site now has a Privacy page saying that it counts "
                    "visitors. Open it from Your pages and add how people can "
                    "reach you.</p>")
    if link:
        said.append("<p>Your footer now links to the Privacy page.</p>")
    return render_notices(notices) + "".join(said), ""


def _candidate(folder: Path, saved: settings.Settings | None,
               values: dict[str, str]) -> settings.Settings:
    """§ 4.5. First run's store is a placeholder, replaced before saving."""
    if saved is None:
        kept = settings.Credentials(store="keyring", github_account=GITHUB_ACCOUNT,
                                    google_account=None)
        property_id = None
    else:
        kept = saved.credentials
        property_id = saved.analytics_property_id
    return settings.Settings(
        site_folder=folder / SITE_FOLDER,
        repository=values["repository"],
        site_name=values["site_name"],
        site_address=values["site_address"],
        daily_prompt_filter=values["daily_prompt_filter"],
        untouchable=(),
        credentials=kept,
        analytics_property_id=property_id,
        measurement_id=values["measurement_id"] or None,   # PRESS-0199 § 4.4
    )


def _read_answers(body: bytes) -> dict[str, str]:
    parsed = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    return {name: (parsed.get(name) or [""])[0].strip()
            for name in (*_FIELDS, "key", "start")}


def _values_from(saved: settings.Settings | None) -> dict[str, str]:
    if saved is None:
        return {name: "" for name in _FIELDS}
    return {name: getattr(saved, name) or "" for name in _FIELDS}


def _credential_failure(face: Face, failure: Exception) -> str:
    fragment = face.fail(failure, publishing=False, secret=KEY)
    if isinstance(failure, credentials.NoStore):
        return "<p>Setup cannot finish on this computer.</p>" + fragment
    return fragment


def _form(settings_page: bool, values: dict[str, str], hints: dict[str, str], *,
          google_on: bool = False, start: bool | None = None) -> str:
    """`start` is None where the starter site is not offered, else whether its
    box is ticked (PRESS-0126 § 4.4)."""
    e = html.escape

    def field(name: str, label: str) -> str:
        hint = hints.get(name)
        shown = f'<p class="hint" id="{name}-hint">{e(hint)}</p>' if hint else ""
        return (
            f'<p><label>{e(label)} <input type="text" name="{name}" '
            f'value="{e(values.get(name, ""), quote=True)}"></label></p>{shown}'
        )

    key_hint = hints.get("key")
    key_note = (
        "<p>Leave the key box empty to keep the key Pressless already has.</p>"
        if settings_page else
        "<p>Make a key on GitHub under Settings, Developer settings, Personal access "
        "tokens, with permission to change the contents of your site's repository.</p>"
    )
    button = ("Check the repository again and save" if settings_page
              else "Check with GitHub and save")
    return (
        f"<h1>{'Settings' if settings_page else 'Set up Pressless'}</h1>"
        '<form method="post" action="/setup">'
        + field("repository", "Your site's repository on GitHub (owner/name)")
        + field("site_name", "Your site's name")
        + field("site_address", "Your site's address")
        + field("daily_prompt_filter",
                "Leave out entries with a tag matching (optional, for example dailyprompt-*)")
        + field("measurement_id",
                "Google's measurement id, to count your visitors (optional, starts G-)")
        + _starter_box(start)
        + key_note
        + '<p><label>Your publishing key <input type="password" name="key" '
          'autocomplete="off"></label></p>'
        + (f'<p class="hint" id="key-hint">{e(key_hint)}</p>' if key_hint else "")
        + f'<p><button type="submit">{e(button)}</button></p></form>'
        + (_google_link(google_on) if settings_page else "")
    )


def _starter_box(start: bool | None) -> str:
    if start is None:
        return ""
    return ('<p><label><input type="checkbox" name="start" value="starter"'
            + (" checked" if start else "")
            + "> Start with a plain site: a homepage, an About page, a menu, a header "
              "and a footer, ready for you to change.</label></p>"
              "<p>Leave it unticked if you will bring in a site you already have: "
              "that needs an empty copy of Pressless.</p>")


def _done(final: settings.Settings, choice: credentials.Choice | None,
          filled: bool = False) -> str:
    e = html.escape
    kept = "".join(f"<li>{e(name)}</li>" for name in final.untouchable)
    left_alone = (
        f"<p>Pressless will leave these alone on your site:</p><ul>{kept}</ul>"
        if kept else "<p>Pressless found nothing on your site it must leave alone.</p>"
    )
    stored = ""
    if choice is not None:
        stored = f"<p>Your publishing key is kept in {e(choice.name)}.</p>"
        if choice.store == "file":
            stored += (
                "<p>No keyring was found on this computer, so the key is kept in a "
                "file only your account can read, in the Pressless-data folder.</p>"
            )
    started = ("<p>Your starter site is in place. It is not on the web until you "
               "publish it.</p>" if filled else "")
    return ("<h1>Setup is done.</h1>" + started + left_alone + stored
            + _google_link(_google_on(final)))


def _google_on(saved: settings.Settings | None) -> bool:
    return saved is not None and saved.credentials.google_account is not None


def _google_link(on: bool) -> str:
    """The optional second step (PRESS-0122 § 4.5), where this copy can offer it.

    Once it is set up, the link names the current state rather than offering
    it again (PRESS-0207).
    """
    if not google_signin.available():
        return ""
    if on:
        return ('<p>Visitor numbers are on: <a href="/setup/google">change the site '
                "or turn them off</a>.</p>")
    return ('<p>Optional: <a href="/setup/google">see how many people read your '
            "site</a>, from Google Analytics.</p>")


def _shortcuts(face: Face, where: shortcuts.Places | None, request: Request) -> str:
    """PRESS-0183: make or remove the menu entry and the desktop icon, as ticked."""
    if where is None:
        return ("<p>Pressless can add itself to the menu and the desktop only when "
                "it runs from the file you downloaded.</p>")
    parsed = urllib.parse.parse_qs(request.body.decode("utf-8", "replace"))
    menu, desktop = parsed.get("menu") == ["on"], parsed.get("desktop") == ["on"]
    before = shortcuts.present(where)
    try:
        shortcuts.apply(where, menu=menu, desktop=desktop and where.desktop is not None)
    except shortcuts.ShortcutError as exc:
        return face.fail(exc, publishing=False) + _shortcut_form(where, shortcuts.present(where))
    after = shortcuts.present(where)
    said = []
    if after[0] and not before[0]:
        said.append(_PINNING[where.windows])
    elif before[0] and not after[0]:
        said.append(f"<p>Pressless is no longer in {_MENU[where.windows]}.</p>")
    if after[1] and not before[1]:
        said.append("<p>There is a Pressless icon on your desktop.</p>")
    elif before[1] and not after[1]:
        said.append("<p>The Pressless icon is gone from your desktop.</p>")
    return (("".join(said) or "<p>Nothing needed changing.</p>")
            + '<p><a href="/">Go to your list</a></p>')


_MENU = {True: "the Start Menu", False: "your app menu"}
_PINNING = {
    True: "<p>Pressless is in the Start Menu. To pin it to the taskbar, find it in the "
          "Start Menu, right-click it and choose Pin to taskbar.</p>",
    False: "<p>Pressless is in your app menu. To add it to your panel, find it in the "
           "menu, right-click it and choose the option that pins it or adds it to the "
           "panel. Its name differs between desktops.</p>",
}


def _shortcut_form(where: shortcuts.Places, ticked: tuple[bool, bool]) -> str:
    """The two boxes, ticked as `ticked` says. The desktop box is left out
    where there is no desktop folder."""
    def box(name: str, on: bool, label: str) -> str:
        return (f'<p><label><input type="checkbox" name="{name}" value="on"'
                + (" checked" if on else "") + f"> {html.escape(label)}</label></p>")

    menu = _MENU[where.windows]
    return (
        f"<h2>{'Start Menu' if where.windows else 'App menu'} and desktop</h2>"
        f'<form method="post" action="{SHORTCUTS}">'
        + box("menu", ticked[0], f"Put Pressless in {menu}")
        + (box("desktop", ticked[1], "Put a Pressless icon on the desktop")
           if where.desktop is not None else "")
        + "<p>Untick a box and save to take that one away again.</p>"
        + '<p><button type="submit">Save these</button></p></form>'
    )
