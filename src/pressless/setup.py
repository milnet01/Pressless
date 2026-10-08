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
    github_setup,
    github_signin,
    google_signin,
    publisher,
    restarting,
    settings,
    shortcuts,
    starter,
    store,
    wizard,
)
from pressless.face import Face, Request, render_notices
from pressless.store import StoreError
from pressless.words import say

SITE_FOLDER = "site"                  # inside Pressless's own folder
GITHUB_ACCOUNT = "github"             # the account the publishing key is filed under

# The answers a refused SettingsError can name; any other key is a failure.
_ANSWERED = ("repository", "site_address", "measurement_id")
_FIELDS = ("repository", "site_name", "site_description", "site_address",
           "daily_prompt_filter", "measurement_id")
# PRESS-0213 § 4.6: the two answers the Store keeps, by the field each is typed in.
_IDENTITY_FIELDS = {"name": "site_name", "description": "site_description"}

_HINTS = {          # the words key for each refused answer
    "repository": "setup.hint.repository",
    "site_name": "setup.hint.site_name",
    "site_description": "setup.hint.site_description",
    "site_address": "setup.hint.site_address",
    "measurement_id": "setup.hint.measurement_id",     # PRESS-0199 § 4.4
}


def _new_repository(account: str) -> str:
    """How to make the repository, for the wizard's step and Settings' help.
    `account` is already escaped."""
    return (f"<ol><li>{say('setup.new_repository.1')}</li>"
            f"<li>{say('setup.new_repository.2', account=account)}</li>"
            f"<li>{say('setup.new_repository.3')}</li>"
            f"<li>{say('setup.new_repository.4')}</li></ol>")


def _new_key() -> str:
    """How to make the publishing key, for the wizard's step and Settings' help."""
    steps = "".join(f"<li>{say(key)}</li>" for key in (
        "setup.new_key.1", "setup.new_key.2", "setup.new_key.3", "setup.new_key.4",
        "setup.new_key.5", "setup.new_key.6"))
    return f"<ol>{steps}</ol>"


# The help paragraphs of the boxes whose help is paragraphs alone.
_HELP_PARAGRAPHS = {
    "site_name": ("setup.help.site_name",),
    "site_description": ("setup.help.site_description",),
    "site_address": ("setup.help.site_address", "setup.help.site_address.named"),
    "daily_prompt_filter": ("setup.help.daily_prompt_filter",
                            "setup.help.daily_prompt_filter.empty"),
}


def _settings_help(name: str) -> str:
    """Settings' "?" beside each box (PRESS-0228): where the answer comes from."""
    if name == "repository":
        return (f"<p>{say('setup.help.repository')}</p>"
                f"<p>{say('setup.help.repository.new')}</p>" + _new_repository("your-name"))
    if name == "measurement_id":
        steps = "".join(f"<li>{say(key)}</li>" for key in (
            "setup.help.measurement_id.1", "setup.help.measurement_id.2",
            "setup.help.measurement_id.3", "setup.help.measurement_id.4"))
        return f"<p>{say('setup.help.measurement_id')}</p><ol>{steps}</ol>"
    if name == "key":
        return f"<p>{say('setup.help.key')}</p>" + _new_key()
    return "".join(f"<p>{say(key)}</p>" for key in _HELP_PARAGRAPHS[name])


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

    face.add_to_list(lambda: _unpublished_starter(folder), above=True)
    face.add_unseen(lambda: starter.unpublished(folder))
    face.add_page("GET", "/setup", page)
    face.add_page("POST", "/setup", page)
    face.add_page("POST", SHORTCUTS, change)


def _unpublished_starter(folder: Path) -> str:
    """Above the list until the starter site is first published."""
    if not starter.unpublished(folder):
        return ""
    return (f'<p id="starter-unpublished">{say("setup.starter.unpublished")} '
            f'{say("setup.starter.publish")}</p>')


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
        try:
            values = _values_from(folder, saved)
        except StoreError as exc:
            return render_notices(notices) + face.fail(exc, publishing=False)
        return (render_notices(notices)
                + _form(values, {}, google_on=_google_on(saved),
                        start=False if offer else None,
                        signed_in=_signed_in(folder, saved))
                + (_shortcut_form(where, shortcuts.present(where)) if where else "")
                + restarting.link())
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
        hints["key"] = say("setup.hint.key_malformed")

    # § 4.4: the rest, against the rules the next launch reads them with.
    candidate = _candidate(folder, saved, values)
    try:
        settings.check(candidate)
    except settings.SettingsError as exc:
        if exc.key not in _ANSWERED:
            return face.fail(exc, publishing=False)
        hints[exc.key] = say(_HINTS[exc.key])
    identity = _identity(values)
    refused_identity = _identity_hint(identity)
    if refused_identity is not None:
        hints[refused_identity] = say(_HINTS[refused_identity])
    if hints:
        return _form(values, hints, google_on=_google_on(saved), start=box,
                     look=answers["look"], signed_in=_signed_in(folder, saved))

    # § 4.6 step 1: the key in hand, or the pass a sign-in buys (PRESS-0231).
    key = typed_key
    if not key:
        try:
            key = github_setup.token(folder, saved.credentials.store,
                                     saved.credentials.github_account)
        except _CREDENTIAL_FAILURES as exc:
            return _credential_failure(face, exc)
        except publisher.PublishError as exc:
            return face.fail(exc, publishing=False)

    done = _save_sequence(face, folder, candidate, identity, key, transport,
                          typed_key=typed_key, starter_ticked=answers["start"] == "starter",
                          look=answers["look"], choice=None, where=None)
    if isinstance(done, publisher.RemoteStateMissing):
        return _form(values, {"repository": say("setup.hint.no_such_repository")},
                     google_on=_google_on(saved), start=box, look=answers["look"],
                     signed_in=_signed_in(folder, saved))
    return done


def _malformed(key: str) -> bool:
    """PRESS-0021 § 4.4's shape rule for a typed key."""
    return not (key.isascii() and key.isprintable() and not any(c.isspace() for c in key))


def _save_sequence(face: Face, folder: Path, candidate: settings.Settings,
                   identity: store.Identity, key: str,
                   transport: publisher.Transport | None, *, typed_key: str,
                   starter_ticked: bool, choice: credentials.Choice | None,
                   look: str = "",
                   where: shortcuts.Places | None, signed_in: bool = False,
                   narrow: str = "") -> str | publisher.RemoteStateMissing:
    """PRESS-0021 § 4.6 from step 2: ask GitHub, store a typed key, fill the
    starter where ticked, in the look chosen (PRESS-0239), write the identity
    (PRESS-0213 § 4.6), save, and say it is done. `candidate` already
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
    # still offered; then the identity. Both before the save, so a failure
    # leaves first run where it was.
    filled = False
    with face.capture() as filling:
        try:
            if starter_ticked and starter.offered(folder):
                starter.fill(folder, identity.name, look)
                filled = True
            store.write_identity(folder, identity)
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
            + _done(final, choice, filled, signed_in=signed_in, narrow=narrow) + privacy
            + (_shortcut_form(where, (True, True)) if where else ""))


def _privacy(face: Face, folder: Path, final: settings.Settings) -> tuple[str, str]:
    """PRESS-0199 § 4.5: after a save holding a measurement id, the Privacy
    page and its footer link where absent. Returns what to say, and a failure
    fragment; the id is saved either way, and the next save retries."""
    if final.measurement_id is None:
        return "", ""
    with face.capture() as notices:
        try:
            page, link = starter.add_privacy(folder, starter.privacy_name(folder))
        except StoreError as exc:
            return "", render_notices(notices) + (
                f"<p>{say('setup.privacy.failed')}</p>" + face.fail(exc, publishing=False))
    said = []
    if page:
        said.append(f"<p>{say('setup.privacy.page')}</p>")
    if link:
        said.append(f"<p>{say('setup.privacy.link')}</p>")
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
            for name in (*_FIELDS, "key", "start", "look")}


def _values_from(folder: Path, saved: settings.Settings) -> dict[str, str]:
    """The Settings page's answers: the identity from the Store (PRESS-0213
    § 4.6), empty where it holds none, and the rest from Settings."""
    identity = store.read_identity(folder) or store.Identity("")
    held = {"site_name": identity.name, "site_description": identity.description}
    return {name: held[name] if name in held else getattr(saved, name) or ""
            for name in _FIELDS}


def _identity(values: dict[str, str]) -> store.Identity:
    return store.Identity(values["site_name"], values["site_description"])


def _identity_hint(identity: store.Identity) -> str | None:
    """The field a refused identity names, or None."""
    problem = store.identity_problem(identity)
    return None if problem is None else _IDENTITY_FIELDS[problem]


def carry_name_across(folder: Path) -> str | None:
    """PRESS-0213 § 4.3: move the name an older Pressless kept in Settings into
    the Store, once. Returns a sentence to print where it could not be moved."""
    name = settings.retired_site_name(folder)
    if name is None:
        return None
    try:
        if store.read_identity(folder) is None:
            store.write_identity(folder, store.Identity(name))
    except StoreError as exc:
        return say("setup.name_not_moved", reason=str(exc))
    try:
        settings.save(folder, settings.load(folder), retire=("site_name",))
    except settings.SettingsError:
        pass        # the identity is written; a later launch retires the key
    return None


def _credential_failure(face: Face, failure: Exception,
                        noun: str = "failure.secret.publishing_key") -> str:
    fragment = face.fail(failure, publishing=False, secret=say(noun))
    if isinstance(failure, credentials.NoStore):
        return f"<p>{say('setup.cannot_finish')}</p>" + fragment
    return fragment


def _form(values: dict[str, str], hints: dict[str, str], *,
          google_on: bool = False, start: bool | None = None, look: str = "",
          signed_in: bool = False) -> str:
    """The Settings page. `start` is None where the starter site is not
    offered, else whether its box is ticked (PRESS-0126 § 4.4), and `look`
    the look chosen for it (PRESS-0239). `signed_in`
    says the stored secret is a GitHub sign-in (PRESS-0231 § 4.4)."""
    def field(name: str, label: str, kind: str = "text") -> str:
        hint = wizard.Hint(name, hints[name]) if name in hints else None
        return wizard.field(name, label, values, hint, kind, _settings_help(name))

    return (
        f"<h1>{say('face.settings')}</h1>"
        '<form method="post" action="/setup">'
        + field("repository", say("setup.field.repository"))
        + field("site_name", say("setup.field.site_name"))
        + field("site_description", say("setup.field.site_description"))
        + field("site_address", say("setup.field.site_address"))
        + field("daily_prompt_filter", say("setup.field.daily_prompt_filter"))
        + field("measurement_id", say("setup.field.measurement_id"))
        + _starter_box(start, look)
        + (f'<p id="signed-in">{say("setup.signed_in")}</p>' if signed_in else "")
        + f"<p>{say('setup.key_kept')}</p>"
        + field("key", say("setup.field.key"), "password")
        + f'<p><button type="submit">{say("setup.save")}</button></p></form>'
        + _google_link(google_on)
    )


def _signed_in(folder: Path, saved: settings.Settings) -> bool:
    """Whether the stored GitHub secret is a sign-in. Only a copy that can
    sign in reads it; one that cannot read it says nothing."""
    if not github_signin.available():
        return False
    try:
        secret = credentials.read(saved.credentials.store, folder,
                                  saved.credentials.github_account)
    except _CREDENTIAL_FAILURES:
        return False
    return github_setup.signed_in(secret)


# PRESS-0239: each look's name and what it looks like, as words keys.
_LOOK_WORDS = {"sunrise": ("setup.look.sunrise", "setup.look.sunrise.about"),
               "meadow": ("setup.look.meadow", "setup.look.meadow.about"),
               "harbour": ("setup.look.harbour", "setup.look.harbour.about")}


def _starter_box(start: bool | None, look: str = "") -> str:
    """The starter's box, and beneath it a choice of look, each with a
    small drawing of it. A look Pressless does not have chooses the first."""
    if start is None:
        return ""
    chosen = look if look in starter.LOOKS else starter.LOOKS[0]
    choices = "".join(
        f'<label class="look"><input type="radio" name="look" value="{name}"'
        + (" checked" if name == chosen else "")
        + f'> <span class="mini mini-{name}" aria-hidden="true">'
        "<span></span><span></span><span></span></span>"
        f"<span><b>{say(_LOOK_WORDS[name][0])}</b>: {say(_LOOK_WORDS[name][1])}</span></label>"
        for name in starter.LOOKS)
    return ('<p><label><input type="checkbox" name="start" value="starter"'
            + (" checked" if start else "")
            + f"> {say('setup.starter.box')}</label></p>"
              f"<p>{say('setup.starter.box.empty')}</p>"
              f'<fieldset class="looks"><legend>{say("setup.starter.look")}</legend>'
            + choices + "</fieldset>")


def _done(final: settings.Settings, choice: credentials.Choice | None,
          filled: bool = False, *, signed_in: bool = False, narrow: str = "") -> str:
    e = html.escape
    kept = "".join(f"<li>{e(name)}</li>" for name in final.untouchable)
    left_alone = (
        f"<p>{say('setup.done.left_alone')}</p><ul>{kept}</ul>"
        if kept else f"<p>{say('setup.done.nothing_left_alone')}</p>"
    )
    stored = ""
    if choice is not None:
        held = "setup.done.kept_sign_in" if signed_in else "setup.done.kept_key"
        stored = f"<p>{say(held, store=e(choice.name))}</p>"
        if choice.store == "file":
            stored += f"<p>{say('setup.done.in_a_file')}</p>"
    started = (f"<p>{say('setup.done.starter')}</p><p>{say('setup.starter.publish')}</p>"
               if filled else "")
    return (f"<h1>{say('setup.done')}</h1>"
            + f"<p>{say('setup.done.address', link=_site_link(final.site_address))}</p>"
            + started + left_alone + stored + narrow
            + _google_link(_google_on(final)) + f'<p><a href="/">{say("setup.onward")}</a></p>')


def _site_link(address: str) -> str:
    """The site's address as a link that opens it (PRESS-0232), or as text
    where it is not an http or https address."""
    shown = html.escape(address)
    if not address.startswith(("https://", "http://")):
        return shown
    return (f'<a href="{html.escape(address, quote=True)}" target="_blank" '
            f'rel="noopener">{shown}</a>')


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
        return f"<p>{say('setup.google.on')}</p>"
    return f"<p>{say('setup.google.offer')}</p>"


def _shortcuts(face: Face, where: shortcuts.Places | None, request: Request) -> str:
    """PRESS-0183: make or remove the menu entry and the desktop icon, as ticked."""
    if where is None:
        return f"<p>{say('setup.shortcuts.unavailable')}</p>"
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
        said.append(f"<p>{say(_PINNING[where.windows])}</p>")
    elif before[0] and not after[0]:
        said.append(f"<p>{say('setup.shortcuts.removed', menu=say(_MENU[where.windows]))}</p>")
    if after[1] and not before[1]:
        said.append(f"<p>{say('setup.shortcuts.icon_added')}</p>")
    elif before[1] and not after[1]:
        said.append(f"<p>{say('setup.shortcuts.icon_removed')}</p>")
    return (("".join(said) or f"<p>{say('setup.shortcuts.unchanged')}</p>")
            + f'<p><a href="/">{say("setup.onward")}</a></p>')


# Keyed by whether this is Windows.
_MENU = {True: "setup.shortcuts.start_menu", False: "setup.shortcuts.app_menu"}
_PINNING = {True: "setup.shortcuts.pinning.windows", False: "setup.shortcuts.pinning"}


def _shortcut_form(where: shortcuts.Places, ticked: tuple[bool, bool]) -> str:
    """The two boxes, ticked as `ticked` says. The desktop box is left out
    where there is no desktop folder."""
    def box(name: str, on: bool, label: str) -> str:
        return (f'<p><label><input type="checkbox" name="{name}" value="on"'
                + (" checked" if on else "") + f"> {html.escape(label)}</label></p>")

    menu = say(_MENU[where.windows])
    title = "setup.shortcuts.title.windows" if where.windows else "setup.shortcuts.title"
    return (
        f"<h2>{say(title)}</h2>"
        f'<form method="post" action="{SHORTCUTS}">'
        + box("menu", ticked[0], say("setup.shortcuts.menu", menu=menu))
        + (box("desktop", ticked[1], say("setup.shortcuts.desktop"))
           if where.desktop is not None else "")
        + f"<p>{say('setup.shortcuts.untick')}</p>"
        + f'<p><button type="submit">{say("setup.shortcuts.save")}</button></p></form>'
    )


# --------------------------------------------- the setup wizard (PRESS-0212) ----
# docs/specs/PRESS-0212-setup-wizard.md § 4.4. First run, one step per screen.
# Every GitHub request goes through the Publisher; the key goes into
# Credentials the moment GitHub accepts it, and never into the progress file.

_ACCOUNT = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_PLACEHOLDER_ADDRESS = "https://github.com"


def _add_to_app(repository: str) -> str:
    """The repository step's hint where the app reaches chosen repositories
    and not this one. A hint is text, escaped where it is shown."""
    return say("setup.hint.add_to_app", repository=repository.partition("/")[2])


def _other_account(signed_in: str, typed: str) -> str:
    """PRESS-0231 INV-14: the sign-in reached an account he did not name."""
    return say("setup.hint.other_account", signed_in=signed_in, typed=typed)


def _first_run_wizard(face: Face, folder: Path, transport: publisher.Transport | None,
                      shortcut_places: Callable[[], shortcuts.Places | None]
                      ) -> wizard.Wizard:
    def repository(answers: wizard.Answers) -> str:
        return f"{answers.get('account', '')}/{answers.get('repository', '')}"

    def probe(name: str, address: str = _PLACEHOLDER_ADDRESS) -> settings.Settings:
        """A candidate for the Publisher's reads and the shape rules, before
        the site step has asked for the rest."""
        return _candidate(folder, None, {
            "repository": name, "site_address": address,
            "daily_prompt_filter": "", "measurement_id": ""})

    def refused(candidate: settings.Settings) -> settings.SettingsError | None:
        try:
            settings.check(candidate)
        except settings.SettingsError as exc:
            return exc
        return None

    # PRESS-0231: where this copy carries a registered GitHub App, he signs in
    # rather than making a key, and Pressless makes the repository.
    signing_in = github_signin.available()
    noun = "failure.secret.github_sign_in" if signing_in else "failure.secret.publishing_key"
    sign_in = github_setup.SignIn()     # its device code, in memory only

    def key_for(answers: wizard.Answers) -> str | wizard.Stop:
        """The key in hand: a hand-made key, or the pass a sign-in buys."""
        try:
            return github_setup.token(folder, answers.get("store", ""), GITHUB_ACCOUNT)
        except _CREDENTIAL_FAILURES as exc:
            return wizard.Stop(_credential_failure(face, exc, noun))
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))

    def check_account(answers: wizard.Answers):
        if not _ACCOUNT.fullmatch(answers["account"]):
            return wizard.Hint("account", say("setup.hint.type_account"))
        try:
            if not publisher.account_exists(answers["account"], transport):
                return wizard.Hint("account", say("setup.hint.no_account"))
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        return answers

    def check_repository(answers: wizard.Answers):
        name = repository(answers)
        if refused(probe(name)) is not None:
            return wizard.Hint("repository", say("setup.hint.name_alone"))
        try:
            if not publisher.public_repository(name, transport):
                return wizard.Hint("repository", say("setup.hint.not_public"))
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        return answers

    def check_key(answers: wizard.Answers):
        typed = answers.get("key", "")
        store = answers.get("store")
        # Sub-step 1: the box.
        if not typed:
            if not store:
                return wizard.Hint("key", say("setup.hint.key_missing"))
            held = key_for(answers)
            if isinstance(held, wizard.Stop):
                return held
            key = held
        elif _malformed(typed):
            return wizard.Hint("key", say("setup.hint.key_malformed"))
        else:
            key = typed
        name = repository(answers)
        # Sub-steps 2 and 3: ask GitHub.
        try:
            publisher.root_entries(probe(name), key, transport)
        except publisher.RemoteStateMissing:
            return wizard.Hint("key", say("setup.hint.key_not_granted"))
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        try:
            publisher.pages(name, key, transport)
        except publisher.Refused:
            return wizard.Hint("key", say("setup.hint.no_pages_read"))
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
        key = key_for(answers)
        if isinstance(key, wizard.Stop):
            return key
        try:
            shown = publisher.pages(name, key, transport)
            if shown.on and not shown.serves_root:
                # PRESS-0229: never advice to re-point Pages, which would take
                # that site offline.
                return wizard.Hint("", say("setup.hint.elsewhere"))
            if not shown.on:
                shown = publisher.switch_pages_on(name, key, transport)
        except publisher.Refused:
            return wizard.Hint("", say("setup.hint.app_cannot_reach" if signing_in
                                       else "setup.hint.no_pages_write"))
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        address = shown.address or ""
        problem = refused(probe(name, address))
        if problem is not None:
            return wizard.Stop(face.fail(problem, publishing=False))
        return {**answers, "site_address": address}

    def check_site(answers: wizard.Answers):
        identity = store.Identity(answers.get("site_name", ""),
                                  answers.get("site_description", ""))
        refused_identity = _identity_hint(identity)
        if refused_identity is not None:
            return wizard.Hint(refused_identity, say(_HINTS[refused_identity]))
        candidate = _candidate(folder, None, {
            "repository": repository(answers),
            "site_address": answers.get("site_address", ""), "daily_prompt_filter": "",
            "measurement_id": ""})
        kept = answers.get("store", "")
        candidate = dataclasses.replace(
            candidate, credentials=dataclasses.replace(candidate.credentials, store=kept))
        problem = refused(candidate)
        if problem is not None:
            return wizard.Stop(face.fail(problem, publishing=False))
        key = key_for(answers)
        if isinstance(key, wizard.Stop):
            return key
        choice = credentials.Choice(kept, answers.get("store_name", kept))
        narrow = (_narrow(repository(answers))
                  if answers.get("all_repositories") == "yes" else "")
        done = _save_sequence(face, folder, candidate, identity, key, transport, typed_key="",
                              starter_ticked=answers.get("start") == "starter",
                              look=answers.get("look", ""), choice=choice, where=shortcut_places(),
                              signed_in=signing_in, narrow=narrow)
        if isinstance(done, publisher.RemoteStateMissing):
            return wizard.Stop(face.fail(done, publishing=False))
        # The sequence words its own failures and success alike; the settings
        # file is written last, so its presence says which this was.
        if not settings.path_for(folder).exists():
            return wizard.Stop(done)
        return wizard.Done(done)

    def check_signin(answers: wizard.Answers):
        # § 4.3 signin: each press polls GitHub once; nothing is stored until
        # GitHub has issued the tokens (INV-4), and then only for the account
        # he named (INV-14).
        typed = answers.get("account", "")
        if not _ACCOUNT.fullmatch(typed):
            return wizard.Hint("account", say("setup.hint.type_account"))
        try:
            pressed = sign_in.press()
            if isinstance(pressed, str):
                return wizard.Hint("", pressed)
            account = github_signin.login(pressed.access, transport)
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        # GitHub's account names ignore case; the name kept is GitHub's.
        if account.lower() != typed.lower():
            return wizard.Hint("account", _other_account(account, typed))
        kept = dict(answers)
        try:
            if not kept.get("store"):
                choice = credentials.choose()
                kept.update(store=choice.store, store_name=choice.name)
            credentials.write(kept["store"], folder, GITHUB_ACCOUNT, pressed.refresh)
        except _CREDENTIAL_FAILURES as exc:
            return wizard.Stop(_credential_failure(face, exc, noun))
        github_setup.hold(pressed)
        kept["account"] = account
        return kept

    def check_install(answers: wizard.Answers):
        key = key_for(answers)
        if isinstance(key, wizard.Stop):
            return key
        try:
            found = github_signin.installation(key, answers.get("account", ""), transport)
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        if found is None:
            return wizard.Hint("", say("setup.hint.not_installed"))
        return {**answers, "all_repositories": "yes" if found.all_repositories else "no"}

    def check_new_repository(answers: wizard.Answers):
        name = repository(answers)
        if refused(probe(name)) is not None:
            return wizard.Hint("repository", say("setup.hint.name_alone"))
        key = key_for(answers)
        if isinstance(key, wizard.Stop):
            return key
        try:
            # A 422 over a Public repository with nothing at its root is the
            # one an earlier press made and lost the answer to (INV-7); any
            # other is left alone (INV-6).
            if not (github_signin.create_repository(key, answers["repository"], transport)
                    or (publisher.public_repository(name, transport)
                        and publisher.root_entries(probe(name), None, transport) == ())):
                return wizard.Hint("repository", say("setup.hint.taken"))
            found = github_signin.installation(key, answers.get("account", ""), transport)
            if found is None:
                return wizard.Hint("", say("setup.hint.not_installed"))
            if not github_signin.reaches(key, found, name, transport):
                return wizard.Hint("", _add_to_app(name))
        except publisher.PublishError as exc:
            return wizard.Stop(face.fail(exc, publishing=False))
        return answers

    pages = wizard.Step("pages", "setup.step.pages", (), _show_pages, check_pages)
    site = wizard.Step("site", "setup.step.site",
                       ("site_name", "site_description", "start", "look"),
                       lambda answers, hint: _show_site(folder, answers, hint), check_site)
    if signing_in:
        return wizard.Wizard("setup", (
            wizard.Step("welcome", "setup.step.welcome", (), _show_welcome_signing_in),
            wizard.Step("signin", "github_setup.title", ("account",),
                        lambda answers, hint: _show_signin(answers, hint, sign_in),
                        check_signin),
            wizard.Step("install", "setup.step.install", (), _show_install,
                        check_install),
            wizard.Step("repository", "setup.step.repository", ("repository",),
                        _show_new_repository, check_new_repository),
            pages, site,
        ), folder, "/setup")
    return wizard.Wizard("setup", (
        wizard.Step("welcome", "setup.step.welcome", (), _show_welcome),
        wizard.Step("account", "setup.step.account", ("account",), _show_account,
                    check_account),
        wizard.Step("repository", "setup.step.repository", ("repository",),
                    _show_repository, check_repository),
        wizard.Step("key", "setup.step.key", ("key",), _show_key, check_key),
        pages, site,
    ), folder, "/setup")


def _show_welcome(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return f"<p>{say('setup.welcome')}</p><p>{say('setup.welcome.beside')}</p>"


def _sign_up() -> str:
    """How to make a GitHub account, for the wizard's first steps."""
    steps = "".join(f"<li>{say(key)}</li>" for key in (
        "setup.sign_up.1", "setup.sign_up.2", "setup.sign_up.3"))
    return f"<ol>{steps}</ol>"


def _show_account(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return (f"<p>{say('setup.account.have')}</p><p>{say('setup.account.make')}</p>"
            + _sign_up()
            + wizard.field("account", say("setup.field.account"), answers, hint))


def _show_welcome_signing_in(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return (_show_welcome(answers, hint)
            + f"<p>{say('setup.account.need')}</p>" + _sign_up())


def _show_signin(answers: wizard.Answers, hint: wizard.Hint | None,
                 sign_in: github_setup.SignIn) -> str:
    return (github_setup.how()
            + f"<p>{say('setup.signin.account')}</p>"
            + wizard.field("account", say("setup.field.account"), answers, hint)
            + sign_in.shown())


def _show_install(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    # Its words follow GitHub's pages as the 2026-10-05 by-hand run found
    # them, from an account with no repositories (§ 7).
    e = html.escape
    address = github_signin.INSTALL_URL.format(github_signin.APP_SLUG)
    account = e(answers.get("account", ""))
    link = (f'<a href="{e(address, quote=True)}" target="_blank" '
            f'rel="noopener">{e(address)}</a>')
    return (f"<p>{say('setup.install')}</p><ol>"
            f"<li>{say('setup.install.1', link=link)}</li>"
            f"<li>{say('setup.install.2', account=account)}</li>"
            f"<li>{say('setup.install.3')}</li>"
            f"<li>{say('setup.install.4')}</li>"
            f"</ol><p>{say('setup.install.already')}</p>")


def _show_new_repository(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    account = answers.get("account", "")
    filled = {**answers, "repository": answers.get("repository") or f"{account}.github.io"}
    e = html.escape(account)
    return (f"<p>{say('setup.new_repository')}</p>"
            f"<p>{say('setup.new_repository.named', account=e)}</p>"
            + wizard.field("repository", say("setup.field.repository_name"), filled, hint))


def _narrow(repository: str) -> str:
    """The done page's advice where the app reaches every repository (§ 4.3)."""
    return f"<p>{say('setup.narrow', repository=html.escape(repository))}</p>"


def _show_repository(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return (f"<p>{say('setup.repository')}</p>"
            + _new_repository(html.escape(answers.get("account", "your-name")))
            + wizard.field("repository", say("setup.field.repository_name"), answers, hint))


def _show_key(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    kept = f"<p>{say('setup.key.kept')}</p>" if answers.get("store") else ""
    return (f"<p>{say('setup.key')}</p>" + _new_key() + kept
            + wizard.field("key", say("setup.field.paste_key"), answers, hint, "password")
            + f"<p>{say('setup.key.safe')}</p>")


def _show_pages(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    return f"<p>{say('setup.pages')}</p><p>{say('setup.pages.nojekyll')}</p>"


def _show_site(folder: Path, answers: wizard.Answers, hint: wizard.Hint | None) -> str:
    try:
        offered = starter.offered(folder)
    except StoreError:
        offered = False       # setup's own check fails the page before this
    box = ""
    if offered:
        ticked = answers.get("start", "starter") == "starter"
        box = _starter_box(ticked, answers.get("look", ""))
    link = _site_link(answers.get("site_address", ""))
    return (f"<p>{say('setup.site', link=link)}</p>"
            + wizard.field("site_name", say("setup.field.site_name"), answers, hint)
            + wizard.field("site_description", say("setup.field.site_description"),
                           answers, hint)
            + box
            + f"<p>{say('setup.site.finish')}</p>")
