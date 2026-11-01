"""A wizard puts the site on its own domain name (PRESS-0222).

GitHub says to add the domain before the records at the seller, so another GitHub
account cannot claim it. So the person sees the records and what will change, Next
sets the domain on GitHub, and the last steps check the records and turn on the
secure address. Leaving part way is harmless: the wizard resumes from Settings.
"""
from __future__ import annotations

import dataclasses
import html
from collections.abc import Callable
from pathlib import Path

from pressless import github_setup, publisher, settings, takeover, wizard
from pressless.face import Face, Request, render_notices
from pressless.words import say
from pressless_import import fetch

ADDRESS = "/domain"
_APEX_ADDRESSES = ("185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153")
_IPV6_ADDRESSES = ("2606:50c0:8000::153", "2606:50c0:8001::153", "2606:50c0:8002::153",
                   "2606:50c0:8003::153")
_GITHUB = frozenset({*_APEX_ADDRESSES, *_IPV6_ADDRESSES})
_LABEL_LONGEST = 63
_NAME_LONGEST = 253
_CERTIFICATE_READY = "approved"
_CERTIFICATE_FAILED = frozenset({"errored", "bad_authz", "dns_changed", "authorization_revoked"})
_OWN_NAMES = ("github.io", "github.com")   # GitHub's, so never a person's own domain


def clean(typed: str) -> str | None:
    """The domain in what was typed, however it was pasted, or None. A name in another
    alphabet becomes the form GitHub and the seller's records use."""
    name = typed.strip().lower().removeprefix("https://").removeprefix("http://")
    name = name.split("/", 1)[0].rstrip(".")
    try:
        name = name.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = name.split(".")
    if (len(labels) < 2 or len(name) > _NAME_LONGEST
            or not all(_good_label(label) for label in labels)
            or labels[-1].isdigit()
            or any(name == own or name.endswith(f".{own}") for own in _OWN_NAMES)):
        return None
    return name


def _good_label(label: str) -> bool:
    return (0 < len(label) <= _LABEL_LONGEST and not label.startswith("-")
            and not label.endswith("-")
            and all(c.isascii() and (c.isalnum() or c == "-") for c in label))


def _record_row(kind: str, name: str, value: str) -> str:
    e = html.escape
    return (f"<tr><td>{kind}</td><td><code>{e(name)}</code></td>"
            f"<td><code>{e(value)}</code></td></tr>")


def _table(rows: list[str]) -> str:
    return (f"<table><thead><tr><th>{say('domain.records.type')}</th>"
            f"<th>{say('domain.records.name')}</th><th>{say('domain.records.value')}</th></tr>"
            f"</thead><tbody>{''.join(rows)}</tbody></table>")


def _apex_rows() -> list[str]:
    return [_record_row("A", "@", address) for address in _APEX_ADDRESSES]


def records(domain: str, repository: str) -> str:
    """The records to copy to the seller, GitHub's own values. Nothing in the standard
    library knows whether `example.co.za` is a whole bought name or a part of one, so
    where a name could be either, both are shown, each saying when it applies."""
    e = html.escape
    host = f"{repository.split('/', 1)[0].lower()}.github.io"
    first, _, rest = domain.partition(".")
    subdomain = _table([_record_row("CNAME", first, host)])
    if first == "www":
        return (f"<p>{say('domain.records.www', domain=e(domain), bought=e(rest))}</p>"
                + _table([_record_row("CNAME", "www", host), *_apex_rows()]))
    if "." not in rest:
        return (f"<p>{say('domain.records.whole', domain=e(domain))}</p>" + _table(_apex_rows()))
    return (f"<p>{say('domain.records.whole', domain=e(domain))}</p>" + _table(_apex_rows())
            + f"<p>{say('domain.records.part', domain=e(domain))}</p>" + subdomain)


def _state(domain: str, resolve: fetch.Resolve) -> str:
    """Where the name leads from this computer, as a words key."""
    try:
        found = set(resolve(domain, 443))
    except (OSError, UnicodeError):
        found = set()
    if not found:
        return "domain.state.not_yet"
    return "domain.state.ready" if found <= _GITHUB else "domain.state.elsewhere"


def _steps(face: Face, folder: Path, transport: publisher.Transport | None,
           resolve: fetch.Resolve) -> tuple[wizard.Step, ...]:
    def signed_in() -> tuple[settings.Settings, str]:
        saved = settings.load(folder)
        return saved, github_setup.token(folder, saved.credentials.store,
                                         saved.credentials.github_account)

    def stopped(exc: Exception) -> wizard.Stop:
        return wizard.Stop(face.fail(exc, publishing=False,
                                     secret=say("failure.secret.publishing_key")))

    def repository() -> str:
        return settings.load(folder).repository

    def show_name(answers: wizard.Answers, hint: wizard.Hint | None) -> str:
        return (f"<p>{say('domain.intro')}</p>"
                + wizard.field("domain", say("domain.field"), answers, hint))

    def check_name(answers: wizard.Answers):
        domain = clean(answers.get("domain", ""))
        if domain is None:
            return wizard.Hint("domain", say("domain.hint.name"))
        if takeover.owed(folder):
            return wizard.Hint("", say("domain.hint.takeover"))
        try:
            saved, key = signed_in()
            shown = publisher.pages(saved.repository, key, transport)
        except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page
            return stopped(exc)
        if not shown.on or not shown.serves_root:
            return wizard.Hint("", say("domain.hint.not_serving"))
        return {**answers, "domain": domain}

    def show_change(answers: wizard.Answers, _hint: wizard.Hint | None) -> str:
        e = html.escape
        domain = answers.get("domain", "")
        rows = "".join(f"<li>{say(key, domain=e(domain))}</li>" for key in (
            "domain.change.address", "domain.change.file", "domain.change.gap"))
        return (f"<p>{say('domain.change')}</p><ul>{rows}</ul>"
                + f"<p>{say('domain.change.ready')}</p>" + records(domain, repository())
                + f"<p>{say('domain.change.verify')}</p>"
                + f"<p>{say('domain.change.next')}</p>")

    def check_change(answers: wizard.Answers):
        domain = answers.get("domain", "")
        try:
            saved, key = signed_in()
            publisher.set_domain(saved.repository, key, domain, transport)
            settings.save(folder, dataclasses.replace(
                saved, site_address=f"https://{domain}/",
                untouchable=publisher.kept_on_a_branch(saved.untouchable, domain)))
        except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page
            return stopped(exc)
        return answers

    def show_records(answers: wizard.Answers, _hint: wizard.Hint | None) -> str:
        domain = answers.get("domain", "")
        return (f"<p>{say('domain.set', domain=html.escape(domain))}</p>"
                + records(domain, repository())
                + f'<p id="domain-state">{say(_state(domain, resolve))}</p>'
                + f"<p>{say('domain.leave')}</p>")

    def show_secure(answers: wizard.Answers, _hint: wizard.Hint | None) -> str:
        return f"<p>{say('domain.secure', domain=html.escape(answers.get('domain', '')))}</p>"

    def check_secure(answers: wizard.Answers):
        domain = answers.get("domain", "")
        try:
            saved, key = signed_in()
            shown = publisher.pages(saved.repository, key, transport)
            if not shown.https_enforced:
                if shown.certificate in _CERTIFICATE_FAILED:
                    return wizard.Hint("", say("domain.hint.certificate_failed"))
                if shown.certificate != _CERTIFICATE_READY:
                    return wizard.Hint("", say("domain.hint.certificate_wait"))
                publisher.enforce_https(saved.repository, key, domain, transport)
        except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page
            return stopped(exc)
        return wizard.Done(_finished(domain))

    return (
        wizard.Step("name", "domain.step.name", ("domain",), show_name, check_name),
        wizard.Step("change", "domain.step.change", (), show_change, check_change),
        wizard.Step("records", "domain.step.records", (), show_records),
        wizard.Step("secure", "domain.step.secure", (), show_secure, check_secure),
    )


def _finished(domain: str) -> str:
    e = html.escape
    address = e(f"https://{domain}/", quote=True)
    link = f'<a href="{address}">{e(domain)}</a>'
    return (f"<h1>{say('domain.done.heading')}</h1><p>{say('domain.done', link=link)}</p>"
            f"<p>{say('domain.done.publish')}</p><p>{say('domain.done.remove')}</p>"
            f'<p class="nav"><a href="/">{say("face.your_writing")}</a></p>')


def register(face: Face, folder: Path, *, transport: publisher.Transport | None = None,
             resolve: Callable[[str, int], list[str]] | None = None) -> None:
    flow = wizard.Wizard("domain", _steps(face, Path(folder), transport, resolve or fetch._resolve),
                         Path(folder), ADDRESS)

    def page(request: Request) -> str:
        with face.capture() as notices:
            try:
                settings.load(folder)
            except (settings.NotSetUp, settings.SettingsError) as exc:
                return render_notices(notices) + face.fail(exc, publishing=False)
            body = flow.page(face, request)
        return render_notices(notices) + body

    face.add_page("GET", ADDRESS, page)
    face.add_page("POST", ADDRESS, page)
