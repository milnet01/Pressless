# A whole site saved to one file, and opened again (PRESS-0224).
#
# Fixtures are made up here: sentinel words, never real writing. A hostile file
# is built in the test with zipfile.
from __future__ import annotations

import json
import shutil
import stat
import sys
import zipfile
from collections import namedtuple
from pathlib import Path

import pytest

from pressless import credentials, settings, sitefile, sites, store

MANIFEST = "pressless-site.json"
SENTINEL_KEY = "a made up secret that must never travel"


def _site(site: Path) -> None:
    """A site holding a file under every name a site has."""
    files = {
        "drafts/half-a-thought.txt": "Title: Half a thought\n\nRain.\n",
        "published/a-walk.txt": "Title: A walk\n\nGulls.\n",
        "photographs/sea.jpg": "\xff\xd8 not really a photograph",
        "files/notes.pdf": "%PDF-1.4 made up",
        "templates/poem.txt": "a template",
        "identity/identity.json": '{"name": "Sentinel Site"}\n',
        "look/style.css": "p { color: red; }",
        "preview-assets/site.css": "body {}",
        "starter-unpublished": "",
        "credentials.json": json.dumps({"version": 1,
                                        "secrets": {"github": SENTINEL_KEY}}),
        "site/index.html": "<p>built</p>",
        "preview/index.html": "<p>preview</p>",
        "fetch/x": "fetched",
        "insights.json": "{}",
        "wizards/setup.json": "{}",
        "choices.json": "{}",
    }
    for name, text in files.items():
        (site / name).parent.mkdir(parents=True, exist_ok=True)
        (site / name).write_text(text, encoding="utf-8")
    settings.save(site, settings.Settings(
        site_folder=site / "site", repository="owner/owner.github.io",
        site_address="https://example.org", daily_prompt_filter="", untouchable=(),
        credentials=settings.Credentials(store="file", github_account="github",
                                         google_account="google"),
        analytics_property_id=None))


def _own(tmp_path: Path, name: str = "own") -> Path:
    own = tmp_path / name
    own.mkdir()
    return own


def _files(folder: Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in sorted(folder.rglob("*")) if path.is_file()}


@pytest.fixture(autouse=True)
def _a_file_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """This machine's store, asked when a site opens; never the real keyring."""
    monkeypatch.setattr(credentials, "choose",
                        lambda: credentials.Choice("file", "file double"))


def _saved(tmp_path: Path) -> tuple[Path, Path]:
    own = _own(tmp_path, "from")
    site = sites.open_site(own)
    _site(site)
    target = tmp_path / "saved.zip"
    sitefile.save(site, target)
    return site, target


# ------------------------------------------------------------------ INV-1 ---


def test_a_saved_site_holds_no_key_and_no_path(tmp_path: Path) -> None:
    """INV-1. Breaks when a left-out name is written, or the path stays in."""
    site, target = _saved(tmp_path)
    with zipfile.ZipFile(target) as saved:
        names = saved.namelist()
        assert names[0] == MANIFEST
        assert json.loads(saved.read(MANIFEST)) == {"format": "pressless-site", "version": 1}
        kept = {name for name in _files(site) if name.split("/")[0] in sitefile.KEPT}
        assert set(names[1:]) == kept
        assert not [name for name in names if name.split("/")[0] in sitefile.LEFT_OUT]
        assert all(SENTINEL_KEY.encode() not in saved.read(name) for name in names)
        assert str(tmp_path).encode() not in saved.read("settings.json")
        assert json.loads(saved.read("settings.json"))["site_folder"] == ""
        assert saved.getinfo("photographs/sea.jpg").compress_type == zipfile.ZIP_STORED
        assert saved.getinfo("drafts/half-a-thought.txt").compress_type == zipfile.ZIP_DEFLATED


def test_every_site_name_is_kept_or_left_out() -> None:
    """§ 4.1. Breaks when a site name is in neither set, so it is silently
    dropped from every saved file."""
    assert sitefile.KEPT | sitefile.LEFT_OUT == sites.SITE_NAMES
    assert not sitefile.KEPT & sitefile.LEFT_OUT
    assert {"credentials.json", "site", "preview", "fetch", "insights.json", "wizards",
            "choices.json", "import"} == sitefile.LEFT_OUT


# ------------------------------------------------------------------ INV-2 ---


def test_a_site_comes_back_whole(tmp_path: Path) -> None:
    """INV-2. Breaks when a file is dropped, renamed, or changed in the trip."""
    site, target = _saved(tmp_path)
    own = _own(tmp_path)
    opened = sitefile.open_into(target, own)
    before = {name: data for name, data in _files(site).items()
              if name.split("/")[0] in sitefile.KEPT and name != "settings.json"}
    after = {name: data for name, data in _files(opened).items() if name != "settings.json"}
    assert after == before
    was, now = (json.loads((folder / "settings.json").read_text(encoding="utf-8"))
                for folder in (site, opened))
    for key in ("site_folder", "credentials"):
        was.pop(key)
        now.pop(key)
    assert now == was


# ------------------------------------------------------------------ INV-3 ---


def _zip(path: Path, members: dict[str, bytes], manifest: dict | None = None,
         link: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as made:
        if manifest is not None:
            made.writestr(MANIFEST, json.dumps(manifest))
        for name, data in members.items():
            made.writestr(name, data)
        if link is not None:
            info = zipfile.ZipInfo(link)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            made.writestr(info, "/etc/passwd")
    return path


GOOD = {"format": "pressless-site", "version": 1}


@pytest.mark.parametrize(("members", "manifest", "link"), [
    ({"../x": b"x"}, GOOD, None),
    ({"/x": b"x"}, GOOD, None),
    pytest.param({"drafts\\x.txt": b"x"}, GOOD, None, marks=pytest.mark.skipif(
        sys.platform == "win32", reason="zipfile on Windows reads a backslash as a "
        "separator, so this name is drafts/x.txt, inside the site")),
    ({"drafts\\..\\..\\x": b"x"}, GOOD, None),
    ({"C:x": b"x"}, GOOD, None),
    ({"secrets/x": b"x"}, GOOD, None),
    ({"drafts/../../x": b"x"}, GOOD, None),
    ({}, GOOD, "drafts/a-link"),
    ({"drafts/x.txt": b"x"}, None, None),
    ({"drafts/x.txt": b"x"}, {"format": "pressless-site", "version": 2}, None),
    ({"drafts/x.txt": b"x"}, {"format": "something-else", "version": 1}, None),
], ids=["dotdot", "absolute", "backslash", "backslash-dotdot", "drive", "not-kept",
        "deep-dotdot", "link",
        "no-manifest", "newer", "other-format"])
def test_a_bad_file_writes_nothing(tmp_path: Path, members, manifest, link) -> None:
    """INV-3. Breaks when a member is unpacked before every member is checked,
    or one escapes the site's folder. Every bad file carries a good member
    too, so an unpacking that ran first would leave it behind."""
    own = _own(tmp_path)
    store.write(sites.open_site(own), _entry(), draft=True)
    before = _files(own)
    bad = _zip(tmp_path / "bad.zip", {"published/good.txt": b"good", **members}, manifest, link)
    with pytest.raises(sitefile.Refused) as refused:
        sitefile.open_into(bad, own)
    assert str(tmp_path) not in str(refused.value)
    assert _files(own) == before
    assert not (tmp_path / "x").exists()


def test_a_file_that_is_no_zip_is_refused(tmp_path: Path) -> None:
    """§ 4.3. Breaks when a broken file reaches the user as an unforeseen
    failure rather than a refusal."""
    own = _own(tmp_path)
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip at all")
    with pytest.raises(sitefile.Refused):
        sitefile.open_into(junk, own)


def _entry() -> store.Entry:
    from test_publishing import _entry as made
    return made("a-draft-of-its-own")


# ------------------------------------------------------------------ INV-4 ---


def test_a_file_too_big_for_the_drive_is_refused(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-4. Breaks when the sizes are not added before unpacking."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda path: usage(0, 0, 1024 * 1024 * 1024 + 100))
    with pytest.raises(sitefile.Refused):
        sitefile.open_into(target, own)
    assert not (own / "sites" / ".opening").exists()


# ------------------------------------------------------------------ INV-5 ---


def test_an_opened_site_is_set_up_for_this_computer(tmp_path: Path) -> None:
    """INV-5. Breaks when the opened site reads or writes another site's key."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    store.write(sites.open_site(own), _entry(), draft=True)
    opened = sitefile.open_into(target, own)
    assert opened == own / "sites" / "site-2"
    loaded = settings.load(opened)
    assert loaded.site_folder == opened / "site"
    assert loaded.credentials == settings.Credentials(
        store="file", github_account="github-site-2", google_account="google-site-2")
    assert json.loads((own / "sites.json").read_text(encoding="utf-8"))["open"] == "site-2"
    assert not (opened / "credentials.json").exists()


# ------------------------------------------------------------------ INV-6 ---


def test_opening_never_writes_over_a_site(tmp_path: Path) -> None:
    """INV-6. Breaks when a site with settings or writing is removed."""
    _, target = _saved(tmp_path)
    fresh = _own(tmp_path, "fresh")
    unused = sites.open_site(fresh)
    (unused / "templates").mkdir()
    (unused / "templates" / "poem.txt").write_text("seeded at launch", encoding="utf-8")
    (unused / "wizards").mkdir()
    assert sitefile.open_into(target, fresh) == fresh / "sites" / "site-1"
    assert (fresh / "sites" / "site-1" / "drafts" / "half-a-thought.txt").is_file()
    assert [path.name for path in sites.all_sites(fresh)] == ["site-1"]

    busy = _own(tmp_path, "busy")
    first = sites.open_site(busy)
    store.write(first, _entry(), draft=True)
    before = _files(first)
    assert sitefile.open_into(target, busy) == busy / "sites" / "site-2"
    assert _files(first) == before

    set_up = _own(tmp_path, "set-up")
    _site(sites.open_site(set_up))
    before = _files(set_up / "sites" / "site-1")
    assert sitefile.open_into(target, set_up) == set_up / "sites" / "site-2"
    assert _files(set_up / "sites" / "site-1") == before


def test_a_refused_open_leaves_no_new_site(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """§ 4.4: a refusal after the target is chosen removes the site new_site
    made. Breaks when an empty site is left in the list."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    store.write(sites.open_site(own), _entry(), draft=True)

    def refuses(folder: Path) -> settings.Settings:
        raise settings.SettingsError("made up", "repository")

    monkeypatch.setattr(settings, "load", refuses)
    with pytest.raises(sitefile.Refused):
        sitefile.open_into(target, own)
    assert [path.name for path in sites.all_sites(own)] == ["site-1"]
    assert not (own / "sites" / ".opening").exists()
