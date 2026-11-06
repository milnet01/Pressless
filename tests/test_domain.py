# A wizard puts the site on its own domain name (PRESS-0222). This file is that
# item's contract, as it has no spec: GitHub hears of the domain only after the
# person has been told what changes, and GitHub's own order is kept (the file and
# the setting, then the records); a publish afterwards keeps the file; the secure
# address goes on only when the certificate is ready; what is typed never reaches a
# record or a page unchecked.
#
# GitHub is tests/test_takein.py's recording double, with Pages added. The record
# values are written out here, from GitHub's "managing a custom domain" page.
from __future__ import annotations

import base64
import contextlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_publishing import _settings
from test_setup import _Browser, _step
from test_takein import KEY, REPOSITORY, _published, _Repository

from pressless import credentials, domain, face, publisher, publishing, settings, takeover

GITHUB_A = ["185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"]
OWN = "www.example.org"


class _Pages(_Repository):
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        super().__init__(files if files is not None else {"index.html": b"<html></html>"})
        self.on, self.serves_root = True, True
        self.cname: str | None = None
        self.enforced, self.certificate = False, "new"
        self.sent: list[dict] = []
        self.refuse_pages = False

    def request(self, method, url, body, headers):
        path = url.removeprefix(publisher.API)
        if path == f"{REPOSITORY}pages":
            self.calls.append((method, url, headers.get("Authorization", "")))
            if method == "PUT":
                if self.refuse_pages:
                    return 403, {}, b'{"message": "refused"}'
                sent = json.loads(body)
                self.sent.append(sent)
                self.cname = sent.get("cname", self.cname)
                self.enforced = sent.get("https_enforced", self.enforced)
                return 204, {}, b""
            if not self.on:
                return 404, {}, b'{"message": "Not Found"}'
            return 200, {}, json.dumps({
                "html_url": "https://owner.github.io/", "build_type": "legacy",
                "cname": self.cname, "https_enforced": self.enforced,
                "https_certificate": {"state": self.certificate},
                "source": {"branch": "main" if self.serves_root else "other", "path": "/"},
            }).encode()
        if method == "GET" and path == f"{REPOSITORY}contents/CNAME":
            self.calls.append((method, url, headers.get("Authorization", "")))
            held = self.holds().get("CNAME")
            if held is None:
                return 404, {}, b'{"message": "Not Found"}'
            return 200, {}, json.dumps({
                "sha": "cname-sha", "encoding": "base64",
                "content": base64.b64encode(held).decode("ascii")}).encode()
        return super().request(method, url, body, headers)

    def writes(self) -> list[tuple[str, str]]:
        return [(method, url.removeprefix(publisher.API)) for method, url, _ in self.calls
                if method != "GET"]


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[_Pages, Path]:
    monkeypatch.setattr(credentials, "read", lambda kind, folder, account: KEY)
    _github, folder = _published(tmp_path)
    settings.save(folder, _settings(folder))
    return _Pages(), folder


@contextlib.contextmanager
def _wizard(folder: Path, github: _Pages, found: list[str] | None = None) -> Iterator[_Browser]:
    served = face.serve(folder)
    try:
        def resolve(_host: str, _port: int) -> list[str]:
            if found is None:
                raise OSError("no such name")
            return found
        domain.register(served, folder, transport=github, resolve=resolve)
        yield _Browser(served)
    finally:
        served.stop()


def _post(browser: _Browser, step: str, **answers: str) -> str:
    return browser.post({"step": step, "go": "next", **answers}, path=domain.ADDRESS)[1]


def _next(browser: _Browser, page: str) -> str:
    return _post(browser, _step(page))


# -------------------------------------------------------------- what was typed ---


@pytest.mark.parametrize(("typed", "name"), [
    ("example.org", "example.org"), (" WWW.Example.org ", "www.example.org"),
    ("https://www.example.org/", "www.example.org"), ("example.org.", "example.org"),
    ("http://example.co.za/a/page", "example.co.za"), ("münchen.de", "xn--mnchen-3ya.de"),
])
def test_a_name_is_found_however_it_was_pasted(typed, name):
    assert domain.clean(typed) == name


@pytest.mark.parametrize("typed", [
    "", "example", "owner.github.io", "github.com", "a..b", "-bad.org", "bad-.org",
    "exa mple.org", "<b>.org", "185.199.108.153", "a_b.org", f"{'a' * 64}.org",
])
def test_what_is_not_a_domain_is_refused(typed):
    assert domain.clean(typed) is None


# ------------------------------------------------------------------ the records ---


def test_a_www_name_shows_githubs_records_under_the_owners_host():
    shown = domain.records(OWN, "Owner/site")
    assert "owner.github.io" in shown and "<code>www</code>" in shown
    assert all(address in shown for address in GITHUB_A)
    assert "site" not in shown.replace("your site", ""), "the host leaves the repository out"


def test_a_two_part_name_shows_only_the_address_records():
    shown = domain.records("example.org", "owner/site")
    assert all(address in shown for address in GITHUB_A) and "CNAME" not in shown


def test_a_whole_name_under_a_two_part_ending_shows_only_the_address_records():
    """PRESS-0342: `co.za` is an ending sold names sit under, so `example.co.za` is a
    whole name. Breaks when both sets are shown, or the name is read as a part."""
    shown = domain.records("example.co.za", "owner/site")
    assert all(address in shown for address in GITHUB_A) and "CNAME" not in shown


@pytest.mark.parametrize(("name", "part"), [("blog.example.com", "blog"),
                                            ("blog.team.example.co.za", "blog.team")])
def test_a_part_of_a_bought_name_shows_only_its_cname(name, part):
    """PRESS-0342. Breaks when the address records are shown too, or the record
    is named after the first label alone."""
    shown = domain.records(name, "owner/site")
    assert f"<code>{part}</code>" in shown and "owner.github.io" in shown
    assert not any(address in shown for address in GITHUB_A)


@pytest.mark.parametrize(("name", "bought"), [
    ("example.co.za", "example.co.za"), ("blog.example.co.za", "example.co.za"),
    ("example.com", "example.com"), ("example.za", "example.za"),
    ("a.b.c.ck", "b.c.ck"), ("www.ck", "www.ck"), ("co.za", None), ("com", None)])
def test_the_bought_name_follows_the_public_suffix_list(name, bought):
    """PRESS-0342: the list's rules, its wildcards and exceptions included, and
    its default that a last label alone is an ending. Breaks when a rule kind
    is read wrongly."""
    assert domain.bought(name) == bought


def test_an_ending_alone_is_not_a_domain():
    assert domain.clean("co.za") is None


# ----------------------------------------------------------------- the wizard ---


def test_nothing_changes_on_github_before_the_person_has_been_told(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    before = settings.load(folder)
    with _wizard(folder, github) as browser:
        page = _post(browser, "name", domain=f"https://{OWN}/")
    for words in ("Your site&#x27;s address becomes", "CNAME", "stays in the repository",
                  "cannot be reached", GITHUB_A[0], "Press Next when you are ready"):
        assert words in page or words.replace("&#x27;", "'") in page, words
    assert github.writes() == []
    assert settings.load(folder) == before


def test_a_refused_name_stays_on_its_step_and_is_not_echoed_raw(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    with _wizard(folder, github) as browser:
        page = _post(browser, "name", domain="<script>alert(1)</script>")
    assert "Type the name you bought" in page
    assert "<script>alert(1)" not in page and github.writes() == []


def test_next_sets_the_domain_the_file_before_the_setting(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    with _wizard(folder, github) as browser:
        _next(browser, _post(browser, "name", domain=OWN))
    assert github.holds()["CNAME"].decode().strip() == OWN
    assert github.sent == [{"cname": OWN}]
    written = [path.rsplit("/", 1)[-1] for method, path in github.writes() if method == "PUT"]
    assert written == ["CNAME", "pages"]
    saved = settings.load(folder)
    assert saved.site_address == f"https://{OWN}/"
    assert {"CNAME", ".nojekyll"} <= set(saved.untouchable)


def test_a_publish_after_it_keeps_the_domain_and_uses_the_new_address(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    with _wizard(folder, github) as browser:
        _next(browser, _post(browser, "name", domain=OWN))
    saved = settings.load(folder)
    publishing.publish(folder, saved, KEY, entry=None, transport=github)
    held = github.holds()
    assert held["CNAME"].decode().strip() == OWN
    assert OWN.encode() in held["sitemap.xml"]


def test_a_refused_write_leaves_settings_and_stays_on_the_step(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    github.refuse_pages = True
    before = settings.load(folder)
    with _wizard(folder, github) as browser:
        page = _next(browser, _post(browser, "name", domain=OWN))
    assert "What will change" in page
    assert settings.load(folder) == before


@pytest.mark.parametrize(("on", "root"), [(False, True), (True, False)])
def test_a_site_github_is_not_serving_from_the_root_is_refused(tmp_path, monkeypatch, on, root):
    github, folder = _ready(tmp_path, monkeypatch)
    github.on, github.serves_root = on, root
    with _wizard(folder, github) as browser:
        page = _post(browser, "name", domain=OWN)
    assert "Publish your site first" in page and github.writes() == []


def test_a_takeover_owed_comes_first(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    takeover.mark(folder, ("deploy.yml",))
    with _wizard(folder, github) as browser:
        page = _post(browser, "name", domain=OWN)
    assert "still built by GitHub Actions" in page and github.writes() == []


@pytest.mark.parametrize(("found", "words"), [
    (None, "cannot find the name yet"),
    (GITHUB_A, "now leads to GitHub"),
    ([*GITHUB_A, "2606:50c0:8000::153"], "now leads to GitHub"),
    ([GITHUB_A[0], "93.184.216.34"], "somewhere besides GitHub"),
])
def test_the_records_step_says_where_the_name_leads(tmp_path, monkeypatch, found, words):
    github, folder = _ready(tmp_path, monkeypatch)
    with _wizard(folder, github, found) as browser:
        page = _next(
            browser, _post(browser, "name", domain=OWN))
    assert words in page and 'id="domain-state"' in page


def _at_secure(browser: _Browser) -> str:
    return _next(browser, _next(browser, _post(browser, "name", domain=OWN)))


def test_the_secure_address_waits_for_the_certificate(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    with _wizard(folder, github) as browser:
        page = _next(browser, _at_secure(browser))
        assert "not ready yet" in page and github.enforced is False
        github.certificate = "errored"
        page = _next(browser, page)
        assert "could not make the certificate" in page and github.enforced is False
        github.certificate = "approved"
        page = _next(browser, page)
    assert github.enforced is True and github.sent[-1] == {"cname": OWN, "https_enforced": True}
    assert "has its own domain name" in page and f'href="https://{OWN}/"' in page


def test_leaving_and_coming_back_resumes_the_step(tmp_path, monkeypatch):
    github, folder = _ready(tmp_path, monkeypatch)
    with _wizard(folder, github) as browser:
        _at_secure(browser)
    with _wizard(folder, github) as browser:
        assert "security certificate" in browser.request("GET", domain.ADDRESS)[2]


def test_a_site_not_set_up_is_told_so(tmp_path, monkeypatch):
    folder = tmp_path / "empty"
    folder.mkdir()
    with _wizard(folder, _Pages()) as browser:
        status, _, page = browser.request("GET", domain.ADDRESS)
    assert status == 200 and 'name="domain"' not in page


