# A whole site saved to one file, and opened again (PRESS-0224).
#
# Fixtures are made up here: sentinel words, never real writing. A hostile file
# is built in the test with zipfile.
from __future__ import annotations

import errno
import json
import os
import shutil
import stat
import sys
import zipfile
from collections import namedtuple
from pathlib import Path

import pytest

from pressless import credentials, settings, sitefile, sites, store, zip_member

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


def _work_left(own: Path) -> list[str]:
    """What an open left under sites/ that is no site."""
    held = own / "sites"
    return sorted(path.name for path in held.iterdir()
                  if not path.name.startswith("site-")) if held.is_dir() else []


def _saved(tmp_path: Path) -> tuple[Path, Path]:
    own = _own(tmp_path, "from")
    site = sites.current_site(own)
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
            "choices.json", "import", "youtube.json", "jpeg-xl-views"} == sitefile.LEFT_OUT


def test_an_imported_site_stays_unpublished_in_its_file(tmp_path: Path) -> None:
    """PRESS-0425. Breaks when the imported-site marker is left out of a saved
    file, so the opened site ticks the web step before a publish."""
    from pressless import publishing
    site = tmp_path / "site"
    site.mkdir()
    store.write_identity(site, store.Identity("Field Notes"))
    publishing.mark_imported(site)
    target = tmp_path / "out.pressless"
    sitefile.save(site, target)
    opened = sitefile.open_into(target, _own(tmp_path))
    assert publishing.imported_unpublished(opened)


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
    # PRESS-0383: Windows starts the path again at a later part's drive, and
    # drops a part's trailing dots and spaces, so `.. ` is `..` there.
    ({"photographs/D:/x": b"x"}, GOOD, None),
    ({"drafts/a:b": b"x"}, GOOD, None),
    ({"drafts/.. /x": b"x"}, GOOD, None),
    ({"drafts/x.": b"x"}, GOOD, None),
    ({"drafts/x ": b"x"}, GOOD, None),
    ({"files/NUL.txt": b"x"}, GOOD, None),
    ({"secrets/x": b"x"}, GOOD, None),
    ({"drafts/../../x": b"x"}, GOOD, None),
    ({}, GOOD, "drafts/a-link"),
    ({"drafts/x.txt": b"x"}, None, None),
    ({"drafts/x.txt": b"x"}, {"format": "pressless-site", "version": 2}, None),
    ({"drafts/x.txt": b"x"}, {"format": "something-else", "version": 1}, None),
], ids=["dotdot", "absolute", "backslash", "backslash-dotdot", "drive", "later-drive",
        "colon", "dotdot-space", "trailing-dot", "trailing-space", "device", "not-kept",
        "deep-dotdot", "link",
        "no-manifest", "newer", "other-format"])
def test_a_bad_file_writes_nothing(tmp_path: Path, members, manifest, link) -> None:
    """INV-3. Breaks when a member is unpacked before every member is checked,
    or one escapes the site's folder. Every bad file carries a good member
    too, so an unpacking that ran first would leave it behind."""
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)
    before = _files(own)
    bad = _zip(tmp_path / "bad.zip", {"published/good.txt": b"good", **members}, manifest, link)
    with pytest.raises(sitefile.Refused):   # the check itself, before any unpacking
        sitefile.check(bad, 10**9)
    with pytest.raises(sitefile.Refused) as refused:
        sitefile.open_into(bad, own)
    assert str(tmp_path) not in str(refused.value)
    assert _files(own) == before
    assert not (tmp_path / "x").exists()


def test_import_keeps_its_own_leaving_out() -> None:
    """PRESS-0125 § 4.4 and PRESS-0210 § 4.1 check members by stays_inside.
    Breaks when a name that climbs out on Windows passes, or when a device
    name, which Import leaves out by itself, refuses the whole ZIP."""
    for name in ("wp/D:/x.jpg", "wp/a:b", "wp/.. /x", "wp/x.", "wp/x "):
        assert not zip_member.stays_inside(name), name
    for name in ("wp/con/x.txt", "uploads/2012/05/a.jpg", "site/"):
        assert zip_member.stays_inside(name), name


def _flagged(path: Path, name: str, data: bytes) -> Path:
    """A site file whose member `name` is marked locked (encrypted) in the
    central directory; zipfile writes no locked member itself."""
    _zip(path, {"published/good.txt": b"good", name: data}, GOOD)
    held = bytearray(path.read_bytes())
    at = held.rindex(b"PK\x01\x02")   # the last member's central entry
    held[at + 8] |= 0x1
    path.write_bytes(bytes(held))
    return path


def test_a_member_zipfile_cannot_unpack_is_refused_first(tmp_path: Path) -> None:
    """§ 4.3. Breaks when a locked or oddly packed member reaches the unpack,
    where it fails as no refusal and leaves the open half done."""
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)
    before = _files(own)
    packed = tmp_path / "packed.zip"
    with zipfile.ZipFile(packed, "w") as made:
        made.writestr(MANIFEST, json.dumps(GOOD))
        made.writestr("published/good.txt", b"good")
        made.writestr("drafts/x.txt", b"x" * 100, compress_type=zipfile.ZIP_BZIP2)
    for bad in (_flagged(tmp_path / "locked.zip", "drafts/x.txt", b"x"), packed):
        with pytest.raises(sitefile.Refused):
            sitefile.check(bad, 10**9)
        with pytest.raises(sitefile.Refused):
            sitefile.open_into(bad, own)
        assert _files(own) == before


def test_settings_nested_past_reading_are_refused(tmp_path: Path) -> None:
    """§ 4.4: a refusal removes the folder new_site made. Breaks when JSON
    nested past Python's depth escapes as no refusal and leaves that site."""
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)
    deep = _zip(tmp_path / "deep.zip", {"settings.json": b"[" * 200_000}, GOOD)
    with pytest.raises(sitefile.Refused):
        sitefile.open_into(deep, own)
    assert [path.name for path in sites.all_sites(own)] == ["site-1"]


def test_a_large_manifest_is_refused_before_it_is_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§ 4.3: the manifest is read whole. Breaks when its size is not
    checked first, so a small file can declare gigabytes."""
    own = _own(tmp_path)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as made:
        made.writestr(MANIFEST, json.dumps(GOOD) + " " * (64 * 1024))
    read = zipfile.ZipFile.read

    def never(held: zipfile.ZipFile, name: object, pwd: object = None) -> bytes:
        if getattr(name, "filename", name) == MANIFEST:
            raise AssertionError("the manifest was read before its size was checked")
        return read(held, name, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "read", never)
    with pytest.raises(sitefile.Refused):
        sitefile.open_into(bad, own)


def test_a_file_with_too_many_members_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§ 4.3: MEMBERS_MOST. Breaks when empty members, which add nothing to
    the size, can fill the drive with files."""
    monkeypatch.setattr(sitefile, "MEMBERS_MOST", 2)
    own = _own(tmp_path)
    bad = _zip(tmp_path / "bad.zip", {"drafts/a": b"", "drafts/b": b""}, GOOD)
    with pytest.raises(sitefile.Refused, match="more files than a site"):
        sitefile.check(bad, 10**9)
    with pytest.raises(sitefile.Refused):
        sitefile.open_into(bad, own)
    assert _work_left(own) == []


def test_a_site_in_place_that_cannot_be_named_is_no_refusal(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§ 4.4 step 6. Breaks when the last step's failure says the file could
    not be opened, although the site is already in place."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)

    def full(own: Path, name: str) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sites, "choose", full)
    with pytest.raises(OSError) as raised:
        sitefile.open_into(target, own)
    assert not isinstance(raised.value, sitefile.Refused)
    assert (own / "sites" / "site-2" / "settings.json").is_file()


def test_a_long_name_is_cut_for_a_file_name(tmp_path: Path) -> None:
    """§ 4.1. Breaks when a long site name makes every backup's path longer
    than Windows takes."""
    site = tmp_path / "site"
    site.mkdir()
    store.write_identity(site, store.Identity("Sea " * 40))
    assert len(sitefile.stem(site)) <= 60
    assert sitefile.stem(site) == sitefile.stem(site).strip()


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
    assert _work_left(own) == []


# ------------------------------------------------------------------ INV-5 ---


def test_an_opened_site_is_set_up_for_this_computer(tmp_path: Path) -> None:
    """INV-5. Breaks when the opened site reads or writes another site's key."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)
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
    unused = sites.current_site(fresh)
    (unused / "templates").mkdir()
    (unused / "templates" / "poem.txt").write_text("seeded at launch", encoding="utf-8")
    (unused / "wizards").mkdir()
    assert sitefile.open_into(target, fresh) == fresh / "sites" / "site-1"
    assert (fresh / "sites" / "site-1" / "drafts" / "half-a-thought.txt").is_file()
    assert [path.name for path in sites.all_sites(fresh)] == ["site-1"]
    # PRESS-0299: the unused site, moved aside first, is gone afterwards.
    assert [path.name for path in (fresh / "sites").iterdir()] == ["site-1"]

    busy = _own(tmp_path, "busy")
    first = sites.current_site(busy)
    store.write(first, _entry(), draft=True)
    before = _files(first)
    assert sitefile.open_into(target, busy) == busy / "sites" / "site-2"
    assert _files(first) == before

    set_up = _own(tmp_path, "set-up")
    _site(sites.current_site(set_up))
    before = _files(set_up / "sites" / "site-1")
    assert sitefile.open_into(target, set_up) == set_up / "sites" / "site-2"
    assert _files(set_up / "sites" / "site-1") == before


def test_a_failed_rename_keeps_the_open_site(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """PRESS-0299: where the open site is unused it is the target, and the
    last rename can still fail. Breaks when the open site is removed before
    the opened one is safely in its place."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    current = sites.current_site(own)
    (current / "kept.txt").write_text("still here", encoding="utf-8")
    before = _files(current)
    real = Path.rename

    def fails_for_opening(self: Path, to: Path) -> Path:
        if self.name.startswith(".o"):   # the file, unpacked
            raise OSError("the drive went away")
        return real(self, to)

    monkeypatch.setattr(Path, "rename", fails_for_opening)
    with pytest.raises(OSError) as raised:   # the drive's failure, never a refusal
        sitefile.open_into(target, own)
    assert not isinstance(raised.value, sitefile.Refused)
    assert [path.name for path in sites.all_sites(own)] == ["site-1"]
    assert _files(current) == before
    assert sorted(path.name for path in (own / "sites").iterdir()) == ["site-1"]


def test_a_refused_open_leaves_no_new_site(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """§ 4.4: a refusal after the target is chosen removes the site new_site
    made. Breaks when an empty site is left in the list."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)

    def refuses(folder: Path) -> settings.Settings:
        raise settings.SettingsError("made up", "repository")

    monkeypatch.setattr(settings, "load", refuses)
    with pytest.raises(sitefile.Refused):
        sitefile.open_into(target, own)
    assert [path.name for path in sites.all_sites(own)] == ["site-1"]
    assert _work_left(own) == []


def test_an_unforeseen_failure_still_cleans_up(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """§ 4.4. Breaks when a failure that is no refusal leaves `.opening` or
    the site new_site made."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)

    def unforeseen(folder: Path) -> settings.Settings:
        raise LookupError("made up")

    monkeypatch.setattr(settings, "load", unforeseen)
    with pytest.raises(LookupError):
        sitefile.open_into(target, own)
    assert [path.name for path in sites.all_sites(own)] == ["site-1"]
    assert _work_left(own) == []


def test_a_file_dated_before_1980_is_saved(tmp_path: Path) -> None:
    """A hand-copied file can carry any date; zip cannot hold one before
    1980. Breaks when strict timestamps refuse the whole save."""
    site = tmp_path / "site"
    _site(site)
    os.utime(site / "photographs" / "sea.jpg", (0, 0))
    target = tmp_path / "saved.pressless"
    sitefile.save(site, target)
    with zipfile.ZipFile(target) as saved:
        assert "photographs/sea.jpg" in saved.namelist()


# ------------------------------------------------- 2026-11-23 review fixes ---


def test_consent_to_replace_a_site_never_travels(tmp_path: Path) -> None:
    """PRESS-0126 § 4.5. Breaks when a file from anyone arrives with the
    starter's agreement to replace the site already on GitHub."""
    from pressless import starter
    site, _ = _saved(tmp_path)
    starter.agree_to_replace(site)
    target = tmp_path / "agreed.zip"
    sitefile.save(site, target)
    opened = sitefile.open_into(target, _own(tmp_path))
    assert starter.unpublished(opened)
    assert not starter.replace_agreed(opened)


def test_consent_is_dropped_from_a_site_saved_before_setup(tmp_path: Path) -> None:
    """Breaks when the consent is dropped only where the file holds settings."""
    from pressless import starter
    agreed = _zip(tmp_path / "agreed.zip", {"starter-unpublished": b"replace\n",
                                             "drafts/x.txt": b"x"}, GOOD)
    opened = sitefile.open_into(agreed, _own(tmp_path))
    assert starter.unpublished(opened) and not starter.replace_agreed(opened)


@pytest.mark.parametrize("held", ["not json {", "[]"])
def test_a_site_whose_settings_are_unreadable_still_saves(tmp_path: Path, held: str) -> None:
    """Breaks when a damaged settings file stops the site being saved or
    backed up at all, just when something on disk is already wrong."""
    site = tmp_path / "site"
    _site(site)
    (site / "settings.json").write_text(held, encoding="utf-8")
    target = tmp_path / "saved.zip"
    sitefile.save(site, target)
    with zipfile.ZipFile(target) as saved:
        assert "settings.json" not in saved.namelist()
        assert "drafts/half-a-thought.txt" in saved.namelist()


def test_a_drive_failure_while_opening_is_no_refusal(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when the drive failing after the file is unpacked is reported
    as the file being refused, and the reason lost."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    store.write(sites.current_site(own), _entry(), draft=True)

    def full(own: Path) -> Path:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sites, "new_site", full)
    with pytest.raises(OSError) as raised:
        sitefile.open_into(target, own)
    assert not isinstance(raised.value, sitefile.Refused)
    assert sorted(path.name for path in (own / "sites").iterdir()) == ["site-1"]


def test_a_save_with_no_room_writes_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when a save fills the drive to nothing before it fails, so every
    other write in that moment fails too."""
    site = tmp_path / "site"
    _site(site)
    folder = tmp_path / "out"
    folder.mkdir()
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(0, 0, 1024 * 1024 * 1024 + 10))
    written: list[Path] = []
    monkeypatch.setattr(sitefile, "save", lambda site, target: written.append(target))
    with pytest.raises(OSError) as raised:
        sitefile.save_part(site, folder)
    assert raised.value.errno == errno.ENOSPC
    assert written == [] and list(folder.iterdir()) == []


def test_a_save_whose_rename_fails_leaves_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when a save that cannot take its name leaves the whole site,
    drafts included, in a half-made file."""
    site = tmp_path / "site"
    _site(site)
    folder = tmp_path / "out"
    folder.mkdir()

    def refuses(self: Path, to: Path) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "rename", refuses)
    with pytest.raises(PermissionError):
        sitefile.save_as(site, folder / "kept.zip")
    assert list(folder.iterdir()) == []


def test_photographs_and_files_are_packed_after_the_lock_is_let_go(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PRESS-0224 § 4.2. Breaks when the editor's lock is held while the
    photographs are packed, so every save and publish waits for the whole
    zip; or when what is packed then is not what the lock saw."""
    from pressless import editor
    site = tmp_path / "sites" / "site-1"
    _site(site)
    locked: dict[str, bool] = {}
    write = zipfile.ZipFile.write

    def noting(made: zipfile.ZipFile, filename: object, arcname: str | None = None,
               *args: object, **kwargs: object) -> None:
        locked[arcname] = editor.LOCK.locked()
        if arcname == "photographs/sea.jpg":   # moved away once the lock is free
            (site / "photographs" / "sea.jpg").unlink()
        write(made, filename, arcname, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "write", noting)
    target = tmp_path / "saved.zip"
    sitefile.save(site, target)
    assert locked["photographs/sea.jpg"] is False and locked["files/notes.pdf"] is False
    assert locked["drafts/half-a-thought.txt"] is True
    with zipfile.ZipFile(target) as saved:
        assert saved.read("photographs/sea.jpg") == "\xff\xd8 not really a photograph".encode()
    assert sorted(path.name for path in (tmp_path / "sites").iterdir()) == ["site-1"]


def test_a_drive_that_cannot_link_packs_everything_under_the_lock(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when a drive with no hard links, such as exFAT, stops a save,
    or leaves the links' folder behind."""
    from pressless import editor
    site = tmp_path / "sites" / "site-1"
    _site(site)

    def no_links(source: object, link: object) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    locked: dict[str, bool] = {}
    write = zipfile.ZipFile.write

    def noting(made: zipfile.ZipFile, filename: object, arcname: str | None = None,
               *args: object, **kwargs: object) -> None:
        locked[arcname] = editor.LOCK.locked()
        write(made, filename, arcname, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "write", noting)
    target = tmp_path / "saved.zip"
    sitefile.save(site, target)
    assert locked["photographs/sea.jpg"] is True
    with zipfile.ZipFile(target) as saved:
        assert "photographs/sea.jpg" in saved.namelist()
    assert sorted(path.name for path in (tmp_path / "sites").iterdir()) == ["site-1"]


def test_a_file_unpacks_under_a_name_no_longer_than_a_site(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks when the unpacking folder's name is longer than site-1's, so a
    file whose deepest member fits on Windows is refused there."""
    _, target = _saved(tmp_path)
    own = _own(tmp_path)
    unpack = sitefile._unpack
    into: list[str] = []

    def noting(source: Path, opening: Path) -> None:
        into.append(opening.name)
        unpack(source, opening)

    monkeypatch.setattr(sitefile, "_unpack", noting)
    sitefile.open_into(target, own)
    assert len(into) == 1 and len(into[0]) <= len("site-1")
    assert _work_left(own) == []
