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
import re
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
    wizard,
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
    `shortcut_places` says where this copy's shortcuts go (PRESS-0183).
    On first run `/setup` is the setup wizard (PRESS-0212)."""
    folder = Path(folder)
    first_run = _first_run_wizard(face, folder, transport, shortcut_places)

    def page(request: Request) -> str:
        return _setup(face, folder, request, transport, shortcut_places, first_run)

    def change(request: Request) -> str:
        return _shortcuts(face, shortcut_places(), request)

    face.add_page("GET", "/setup", page)
    face.add_page("POST", "/setup", page)
    face.add_page("POST", SHORTCUTS, change)


def _setup(face: Face, folder: Path, request: Request,
           transport: publisher.Transport | None,
           shortcut_places: Callable[[], shortcuts.Places | None],
           first_run: wizard.Wizard) -> str:
    # § 4.2, as PRESS-0212 § 4.3 changes it: which page he sees.
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
    if saved is None:
        return render_notices(notices) + first_run.page(face, request)
    if request.method != "POST":
        # PRESS-0183: Settings shows the shortcuts as they are now.
        where = shortcut_places()
        return (render_notices(notices)
                + _form(_values_from(saved), {}, google_on=_google_on(saved),
                        start=False if offer else None)
                + (_shortcut_form(where, shortcuts.present(where)) if where else ""))
    return render_notices(notices) + _submit(face, folder, saved,
                                             _read_answers(request.body), transport, offer)


def _submit(face: Face, folder: Path, saved: settings.Settings,
            answers: dict[str, str], transport: publisher.Transport | None,
            offer: bool) -> str:
    """Settings: check the answers, then the save sequence."""
    box = (answers["start"] == "starter") if offer else None   # PRESS-0126 § 4.4
    typed_key = answers["key"]
    values = {name: answers[name] for name in _FIELDS}
    hints: dict[str, str] = {}

    # § 4.4: the key. An empty box keeps the saved one.
    if typed_key and _malformed(typed_key):
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
        return _form(values, hints, google_on=_google_on(saved), start=box)

    # § 4.6 step 1: the key in hand.
    key = typed_key
    if not key:
        try:
            key = credentials.read(saved.credentials.store, folder,
                                   saved.credentials.github_account)
        except _CREDENTIAL_FAILURES as exc:
            return _credential_failure(face, exc)

    done = _save_sequence(face, folder, candidate, key, transport, typed_key=typed_key,
                          starter_ticked=answers["start"] == "starter",
                          choice=None, where=None)
    if isinstance(done, publisher.RemoteStateMissing):
        return _form(values, {"repository": _NO_SUCH_REPOSITORY},
                     google_on=_google_on(saved), start=box)
    return done


def _malformed(key: str) -> bool:
    """PRESS-0021 § 4.4's shape rule for a typed key."""
    return not (key.isascii() and key.isprintable() and not any(c.isspace() for c in key))


def _save_sequence(face: Face, folder: Path, candidate: settings.Settings, key: str,
                   transport: publisher.Transport | None, *, typed_key: str,
                   starter_ticked: bool, choice: credentials.Choice | None,
                   where: shortcuts.Places | None) -> str | publisher.RemoteStateMissing:
    """PRESS-0021 § 4.6 from step 2: ask GitHub, store a typed key, fill the
    starter where ticked, save, and say it is done. `candidate` already
    carries the store; nothing here chooses one. A repository GitHub cannot
    find inside comes back for the caller to word."""
    # Step 2: ask GitHub.
    try:
        entries = publisher.root_entries(candidate, key, transport)
    except publisher.RemoteStateMissing as exc:
        # root_entries reads commits/HEAD first, and a 404 there is this type,
        # never RepositoryMissing (§ 4.6 step 2).
        return exc
    except publisher.PublishError as exc:
        return face.fail(exc, publishing=False)

    # Step 4: store the key, only when he typed one.
    if typed_key:
        try:
            credentials.write(candidate.credentials.store, folder,
                              candidate.credentials.github_account, typed_key)
        except _CREDENTIAL_FAILURES as exc:
            return _credential_failure(face, exc)

    # PRESS-0126 § 4.4: fill, only where the box was ticked and the starter is
    # still offered. Before the save, so a failure leaves first run where it was.
    filled = False
    with face.capture() as filling:
        try:
            if starter_ticked and starter.offered(folder):
                starter.fill(folder, candidate.site_name)
                filled = True
        except StoreError as exc:
            fill_failure: str | None = face.fail(exc, publishing=False)
        else:
            fill_failure = None
    if fill_failure is not None:
        return render_notices(filling) + fill_failure

    # Step 5: save, last.
    final = dataclasses.replace(candidate, untouchable=untouchable(entries))
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


def _form(values: dict[str, str], hints: dict[str, str], *,
          google_on: bool = False, start: bool | None = None) -> str:
    """The Settings page. `start` is None where the starter site is not
    offered, else whether its box is ticked (PRESS-0126 § 4.4)."""
    def field(name: str, label: str, kind: str = "text") -> str:
        hint = wizard.Hint(name, hints[name]) if name in hints else None
        return wizard.field(name, label, values, hint, kind)

    return (
        "<h1>Settings</h1>"
        '<form method="post" action="/setup">'
        + field("repository", "Your site's repository on GitHub (owner/name)")
        + field("site_name", "Your site's name")
        + field("site_address", "Your site's address")
        + field("daily_prompt_filter",
                "Leave out entries with a tag matching (optional, for example dailyprompt-*)")
        + field("measurement_id",
                "Google's measurement id, to count your visitors (optional, starts G-)")
        + _starter_box(start)
        + "<p>Leave the key box empty to keep the key Pressless already has.</p>"
        + field("key", "Your publishing key", "password")
        + '<p><button type="submit">Check the repository again and save</button></p></form>'
        + _google_link(google_on)
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


# --------------------------------------------- the setup wizard (PRESS-0212) ----
# docs/specs/PRESS-0212-setup-wizard.md § 4.4. First run, one step per screen.
# Every GitHub request goes through the Publisher; the key goes into
# Credentials the moment GitHub accepts it, and never into the progress file.

_ACCOUNT = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_PLACEHOLDER_NAME = "Pressless"                     # until the site step asks for it
_PLACEHOLDER_ADDRESS = "https://github.com"

_NO_ACCOUNT = ("GitHub has no account by that name. Check the spelling, or finish "
               "making it first.")
_NOT_PUBLIC = ("GitHub shows no public repository by that name. Check the spelling, "
               "and that you chose Public when you made it.")
_KEY_NOT_GRANTED = ("This key cannot reach that repository. On GitHub, edit the key and "
                    "choose your site's repository under Repository access.")
_NO_PAGES_READ = ("This key cannot see GitHub Pages. On GitHub, edit the key and set "
                  "Pages to Read and write under Repository permissions.")
_NO_PAGES_WRITE = ("This key cannot switch GitHub Pages on. On GitHub, edit the key and "
                   "set Pages to Read and write under Repository permissions, then press "
                   "Next again.")
_ELSEWHERE = ("GitHub Pages is on, but it serves something other than your repository's "
              "main branch, so it would never show what Pressless publishes. On GitHub, "
              "open your repository's Settings, then Pages. Under Build and deployment, "
              "choose Deploy from a branch, your main branch, and / (root), and press "
              "Save. Then press Next again.")


def _first_run_wizard(face: Face, folder: Path, transport: publisher.Transport | None,
                      shortcut_places: Callable[[], shortcuts.Places | None]
                      ) -> wizard.Wizard:
    def repository(answers: wizard.Answers) -> str:
        return f"{answers.get('account', '')}/{answers.get('repository', '')}"

    def probe(name: str, address: str = _PLACEHOLDER_ADDRESS) -> settings.Settings:
        """A candidate for the Publisher's reads and the shape rules, before
        the site step has asked for the rest."""
        return _candidate(folder, None, {
            "repository": name, "site_name": _PLACEHOLDER_NAME, "site_address": address,
            "daily_prompt_filter": "", "measurement_id": ""})

    def refused(candidate: settings.Settings) -> settings.SettingsError | None:
        try:
            settings.check(candidate)
        except settings.SettingsError as exc:
            return exc
        return None

    def check_account(answers: wizard.Answers):
        if not _ACCOUNT.fullmatch(answers["account"]):
            return wizard.Hint("account", "Type your GitHub account name, as GitHub shows it.")
        try:
            if not publisher.account_exists(answers["account"], transport):
                return wizard.Hint("account", _NO_ACCOUNT)
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        return answers

    def check_repository(answers: wizard.Answers):
        name = repository(answers)
        if refused(probe(name)) is not None:
            return wizard.Hint("repository", "Type the repository's name alone, as GitHub "
                                             "shows it after your account name.")
        try:
            if not publisher.public_repository(name, transport):
                return wizard.Hint("repository", _NOT_PUBLIC)
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        return answers

    def check_key(answers: wizard.Answers):
        typed = answers.get("key", "")
        store = answers.get("store")
        # Sub-step 1: the box.
        if not typed:
            if not store:
                return wizard.Hint("key", _KEY_MISSING)
            try:
                key = credentials.read(store, folder, GITHUB_ACCOUNT)
            except _CREDENTIAL_FAILURES as exc:
                return wizard.Stop(_credential_failure(face, exc))
        elif _malformed(typed):
            return wizard.Hint("key", _KEY_MALFORMED)
        else:
            key = typed
        name = repository(answers)
        # Sub-steps 2 and 3: ask GitHub.
        try:
            publisher.root_entries(probe(name), key, transport)
        except publisher.RemoteStateMissing:
            return wizard.Hint("key", _KEY_NOT_GRANTED)
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        try:
            publisher.pages(name, key, transport)
        except publisher.Refused:
            return wizard.Hint("key", _NO_PAGES_READ)
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        if not typed:
            return answers
        # Sub-step 4: store it, choosing the store once.
        kept = dict(answers)
        try:
            if not store:
                choice = credentials.choose()
                kept.update(store=choice.store, store_name=choice.name)
            credentials.write(kept["store"], folder, GITHUB_ACCOUNT, typed)
        except _CREDENTIAL_FAILURES as exc:
            return wizard.Stop(_credential_failure(face, exc))
        return kept

    def check_pages(answers: wizard.Answers):
        name = repository(answers)
        try:
            key = credentials.read(answers.get("store", ""), folder, GITHUB_ACCOUNT)
        except _CREDENTIAL_FAILURES as exc:
            return wizard.Stop(_credential_failure(face, exc))
        try:
            shown = publisher.pages(name, key, transport)
            if shown.on and not shown.serves_root:
                return wizard.Hint("", _ELSEWHERE)
            if not shown.on:
                shown = publisher.switch_pages_on(name, key, transport)
        except publisher.Refused:
            return wizard.Hint("", _NO_PAGES_WRITE)
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        address = shown.address or ""
        problem = refused(probe(name, address))
        if problem is not None:
            return wizard.Stop(face.fail(problem, publishing=False))
        return {**answers, "site_address": address}

    def check_site(answers: wizard.Answers):
        candidate = _candidate(folder, None, {
            "repository": repository(answers), "site_name": answers["site_name"],
            "site_address": answers.get("site_address", ""), "daily_prompt_filter": "",
            "measurement_id": ""})
        store = answers.get("store", "")
        candidate = dataclasses.replace(
            candidate, credentials=dataclasses.replace(candidate.credentials, store=store))
        problem = refused(candidate)
        if problem is not None:
            if problem.key == "site_name":
                return wizard.Hint("site_name", _HINTS["site_name"])
            return wizard.Stop(face.fail(problem, publishing=False))
        try:
            key = credentials.read(store, folder, GITHUB_ACCOUNT)
        except _CREDENTIAL_FAILURES as exc:
            return wizard.Stop(_credential_failure(face, exc))
        choice = credentials.Choice(store, answers.get("store_name", store))
        done = _save_sequence(face, folder, candidate, key, transport, typed_key="",
                              starter_ticked=answers.get("start") == "starter",
                              choice=choice, where=shortcut_places())
        if isinstance(done, publisher.RemoteStateMissing):
            return wizard.Stop(face.fail(done, publishing=False))
        # The sequence words its own failures and success alike; the settings
        # file is written last, so its presence says which this was.
        if not settings.path_for(folder).exists():
            return wizard.Stop(done)
        return wizard.Done(done)

    return wizard.Wizard("setup", (
        wizard.Step("welcome", "Set up Pressless", (), _show_welcome),
        wizard.Step("account", "A GitHub account", ("account",), _show_account,
                    check_account),
        wizard.Step("repository", "A home for your site", ("repository",),
                    _show_repository, check_repository),
        wizard.Step("key", "A key for Pressless", ("key",), _show_key, check_key),
        wizard.Step("pages", "Switch the site on", (), _show_pages, check_pages),
        wizard.Step("site", "Your site", ("site_name", "start"),
                    lambda answers, hint: _show_site(folder, answers, hint), check_site),
    ), folder, "/setup")


def _show_welcome(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return ("<p>Pressless publishes your site on GitHub, which hosts it for free. "
            "These steps take you through getting it ready, one screen at a time. "
            "You need an email address and about fifteen minutes.</p>"
            "<p>Some steps happen on GitHub's own pages. Keep this page open beside "
            "them. If you close Pressless partway, it starts again where you left "
            "off.</p>")


def _show_account(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return ("<p>If you already have a GitHub account, type its name below.</p>"
            "<p>If not, make one:</p><ol>"
            '<li>Open <a href="https://github.com/signup" target="_blank" '
            'rel="noopener">github.com/signup</a>.</li>'
            "<li>Type your email address, a password and a username, and follow "
            "GitHub's steps. It sends a code to your email to check it is yours.</li>"
            "<li>When GitHub asks which plan, the free one is all Pressless needs.</li>"
            "</ol>"
            + wizard.field("account", "Your GitHub account name", answers, hint))


def _show_repository(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    e = html.escape
    account = e(answers.get("account", "your-name"))
    return ("<p>A repository is the folder on GitHub your site lives in. Make one:</p><ol>"
            "<li>On GitHub, click the <b>+</b> at the top right, then "
            "<b>New repository</b>.</li>"
            f"<li>Under <b>Repository name</b>, type <b>{account}.github.io</b>. Your "
            f"site's address is then https://{account}.github.io. Any other name works "
            f"too, and gives https://{account}.github.io/<i>the-name</i>/.</li>"
            "<li>Choose <b>Public</b>. GitHub hosts sites for free only from public "
            "repositories.</li>"
            "<li>Click <b>Create repository</b>. Leave everything else as it is.</li></ol>"
            + wizard.field("repository", "The repository's name", answers, hint))


def _show_key(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    kept = ("<p>Pressless already has the key you gave it. Leave the box empty to "
            "keep it, or paste a new one.</p>" if answers.get("store") else "")
    return ("<p>Pressless needs a key that lets it change your site, and nothing "
            "else. Make one:</p><ol>"
            "<li>On GitHub, click your picture at the top right, then <b>Settings</b>.</li>"
            "<li>At the bottom of the left-hand list, click <b>Developer settings</b>, "
            "then <b>Personal access tokens</b>, then <b>Fine-grained tokens</b>.</li>"
            "<li>Click <b>Generate new token</b>. Name it <b>Pressless</b>, and choose how "
            "long it lasts. When it runs out, make a new one the same way and paste it "
            "into Settings.</li>"
            "<li>Under <b>Repository access</b>, choose <b>Only select repositories</b>, "
            "then your site's repository.</li>"
            "<li>Under <b>Repository permissions</b>, set <b>Contents</b> to <b>Read and "
            "write</b>, and <b>Pages</b> to <b>Read and write</b>.</li>"
            "<li>Click <b>Generate token</b>, then copy it. GitHub shows it only once.</li>"
            "</ol>" + kept
            + wizard.field("key", "Paste the key here", answers, hint, "password")
            + "<p>Pressless keeps the key in your computer's own safe store, never in a "
              "file it shows anyone.</p>")


def _show_pages(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return ("<p>GitHub Pages is what puts your repository on the web. Press Next and "
            "Pressless checks it, and switches it on if it is off.</p>"
            "<p>It also adds an empty file named .nojekyll to your repository, which "
            "tells GitHub to show your site's files exactly as Pressless makes "
            "them.</p>")


def _show_site(folder: Path, answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    e = html.escape
    try:
        offered = starter.offered(folder)
    except StoreError:
        offered = False       # setup's own check fails the page before this
    box = ""
    if offered:
        ticked = answers.get("start", "starter") == "starter"
        box = _starter_box(ticked)
    return (f"<p>Your site's address is {e(answers.get('site_address', ''))}. It can "
            "take a few minutes after your first publish before it shows.</p>"
            + wizard.field("site_name", "Your site's name", answers, hint)
            + box
            + "<p>Press Next to check everything with GitHub one last time and "
              "finish.</p>")
