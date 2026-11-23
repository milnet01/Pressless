"""Setting the log relay up (PRESS-0436 § 4.4): what scripts/relay-setup.py
does before and after it reaches GitHub and Cloudflare.

The script is loaded by path. Nothing here reaches GitHub, Cloudflare or a
browser: each test stops the script before the step that would.
"""
from __future__ import annotations

import io
import os
import urllib.error

import pytest
from _scripts import load_script


class _Stop(Exception):
    """Raised where the script would next reach the network."""


@pytest.fixture
def script(tmp_path, monkeypatch):
    loaded = load_script("relay-setup.py")
    kept = tmp_path / "kept"
    monkeypatch.setattr(loaded, "KEPT", kept)
    monkeypatch.setattr(loaded, "KEY", kept / "log-relay-app.pem")
    monkeypatch.setattr(loaded, "APP", kept / "log-relay-app.json")

    def never(*args, **options):
        raise _Stop

    monkeypatch.setattr(loaded, "_make_app", never)
    monkeypatch.setattr(loaded, "_installation", never)
    return loaded


def test_a_key_left_without_its_app_file_is_never_replaced(script):
    """review-code: a run stopped between the key and the App file left the
    key alone; the next run made a second App and wrote over the first
    one's only key."""
    script.KEPT.mkdir()
    script.KEY.write_bytes(b"the first App's key")
    with pytest.raises(SystemExit, match="stopped part way"):
        script.main([])
    assert script.KEY.read_bytes() == b"the first App's key"


def test_an_app_file_left_without_its_key_is_refused(script):
    script.KEPT.mkdir()
    script.APP.write_text('{"id": 1, "slug": "s"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="stopped part way"):
        script.main([])


def test_nothing_kept_makes_an_app(script):
    with pytest.raises(_Stop):
        script.main([])


def test_a_key_given_by_hand_never_replaces_a_kept_one(script, tmp_path):
    script.KEPT.mkdir()
    script.KEY.write_bytes(b"a live App's key")
    download = tmp_path / "download.pem"
    download.write_bytes(b"another key")
    with pytest.raises(SystemExit, match="already holds a key"):
        script.main(["--key", str(download), "--app-id", "7"])
    assert script.KEY.read_bytes() == b"a live App's key"
    assert download.read_bytes() == b"another key"


def test_a_key_given_by_hand_is_kept_and_its_download_removed(script, tmp_path):
    download = tmp_path / "download.pem"
    download.write_bytes(b"the new key")
    with pytest.raises(_Stop):
        script.main(["--key", str(download), "--app-id", "7"])
    assert script.KEY.read_bytes() == b"the new key"
    assert script.APP.read_text(encoding="utf-8") == '{"id": 7, "slug": "pressless-log-relay"}'
    assert not download.exists()
    if os.name != "nt":
        assert script.KEY.stat().st_mode & 0o777 == 0o600


def test_the_kept_key_given_as_the_download_is_not_deleted(script):
    script.KEPT.mkdir()
    script.KEY.write_bytes(b"the kept key")
    with pytest.raises(_Stop):
        script.main(["--key", str(script.KEY), "--app-id", "7"])
    assert script.KEY.read_bytes() == b"the kept key"


@pytest.mark.parametrize("argv", [["--key", "a.pem"], ["--app-id", "7"], ["--key"]])
def test_a_half_given_app_is_a_usage_error(script, argv):
    """review-readability lead: --key without --app-id was a KeyError
    traceback, and an odd argument was dropped without a word."""
    with pytest.raises(SystemExit) as stopped:
        script.main(argv)
    assert stopped.value.code == 2


def test_a_failed_write_leaves_the_kept_file_whole(script, monkeypatch):
    script.KEPT.mkdir()
    script.KEY.write_bytes(b"whole")

    def failing(handle):
        raise OSError("the drive is full")

    monkeypatch.setattr(script.os, "fsync", failing)
    with pytest.raises(OSError):
        script._write_private(script.KEY, b"half")
    assert script.KEY.read_bytes() == b"whole"
    assert sorted(path.name for path in script.KEPT.iterdir()) == ["log-relay-app.pem"]


_SETTINGS = '{\n  "vars": {\n    "APP_ID": "1",\n    "INSTALLATION_ID": "2"\n  }\n}\n'


def test_both_ids_are_filled(script):
    filled = script._with_ids(_SETTINGS, 31, 42)
    assert '"APP_ID": "31"' in filled
    assert '"INSTALLATION_ID": "42"' in filled


@pytest.mark.parametrize("name", ["APP_ID", "INSTALLATION_ID"])
def test_a_settings_file_lacking_an_id_is_refused(script, name):
    """review-code: re.sub changed nothing where the key was missing, and the
    Worker was deployed with the old ids."""
    with pytest.raises(SystemExit, match=name):
        script._with_ids(_SETTINGS.replace(name, "OTHER"), 31, 42)


@pytest.mark.parametrize(("status", "said"), [(429, "wait a minute"),
                                              (502, "could not reach GitHub"),
                                              (500, "wrangler tail")])
def test_a_refused_test_log_is_named(script, monkeypatch, status, said):
    """review-code: a 429 or 502 from the relay was an uncaught traceback."""
    def refusing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, status, "no", {}, io.BytesIO(b""))

    monkeypatch.setattr(script.urllib.request, "urlopen", refusing)
    with pytest.raises(SystemExit, match=f"answered {status}.*{said}"):
        script._test_log("https://relay.invalid/log")
