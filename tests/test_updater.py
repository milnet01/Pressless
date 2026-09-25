# The Updater: find a release, prove its signed list, download and unpack
# (PRESS-0023).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0023-self-update.md § 5. No test reaches the network: the
# double answers by URL, never by position (CLAUDE.md). Signing uses a key made
# inside the test and patched into TRUSTED; nothing here reads a real key.
#
# The API address, the asset names and the list's shape are written out here
# rather than built from the module's constants, so the test holds its own copy
# of the contract.
from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from email.message import Message
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from pressless import update_key, updater

API = "https://api.github.com/repos/milnet01/Pressless/releases/latest"
RUNNING = "0.1.2"
DOWNLOADS = "https://github.com/milnet01/Pressless/releases/download"


# ------------------------------------------------------------- the double ---


class _Response:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self._body = io.BytesIO(body)

    def read(self, n: int) -> bytes:
        return self._body.read(min(n, 7))  # small chunks, so a reader must loop

    def close(self) -> None:
        pass


class _Net:
    """Answers by URL. An answer that is an exception is raised."""

    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.requests: list[str] = []

    def open(self, url: str) -> _Response:
        self.requests.append(url)
        answer = self.answers.get(url)
        if answer is None:
            raise OSError(f"no answer for {url}")
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, _Response):
            return answer
        return _Response(200, {}, answer)


def _key() -> tuple[Ed25519PrivateKey, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, base64.b64encode(public).decode("ascii")


def _list(version: str, *, linux: bytes = b"linux bytes", windows: bytes = b"windows bytes",
          linux_size: int | None = None, names_version: str | None = None) -> bytes:
    named = names_version or version
    return (
        "pressless-release 1\n"
        f"version {version}\n"
        f"linux Pressless-{named}-x86_64.AppImage {linux_size or len(linux)} "
        f"{hashlib.sha256(linux).hexdigest()}\n"
        f"windows Pressless-{named}-windows.zip {len(windows)} "
        f"{hashlib.sha256(windows).hexdigest()}\n"
    ).encode("ascii")


class _Release:
    """One release as GitHub would serve it, signed with `signers`."""

    def __init__(self, tag: str, text: bytes, signers: list[Ed25519PrivateKey]) -> None:
        self.tag = tag
        self.version = tag.removeprefix("v")
        self.text = text
        self.sig = b"".join(key.sign(text) for key in signers)
        self.names = {
            "list": f"Pressless-{self.version}-release.txt",
            "sig": f"Pressless-{self.version}-release.txt.sig",
            "linux": f"Pressless-{self.version}-x86_64.AppImage",
            "windows": f"Pressless-{self.version}-windows.zip",
        }

    def url(self, which: str) -> str:
        return f"{DOWNLOADS}/{self.tag}/{self.names[which]}"

    def assets(self) -> list[dict[str, str]]:
        return [{"name": name, "browser_download_url": self.url(which)}
                for which, name in self.names.items()]

    def answers(self, assets: list[dict[str, str]] | None = None) -> dict[str, object]:
        body = json.dumps({"tag_name": self.tag, "draft": False, "prerelease": False,
                           "assets": self.assets() if assets is None else assets})
        return {API: body.encode("utf-8"), self.url("list"): self.text,
                self.url("sig"): self.sig}


@pytest.fixture
def signer(monkeypatch) -> Ed25519PrivateKey:
    private, public = _key()
    monkeypatch.setattr(update_key, "TRUSTED", (public,))
    return private


def _check(folder: Path, answers: dict[str, object], platform: str = "linux"):
    net = _Net(answers)
    return updater.check(folder, RUNNING, platform, net), net


# ------------------------------------------------------------------ INV-1 ---


def test_check_is_on_by_default(tmp_path, signer):
    """Breaks when the default is read as off, or a malformed file reads as
    off."""
    release = _Release("v0.1.3", _list("0.1.3"), [signer])
    for name, text in (("missing", None), ("unparseable", "{"),
                       ("wrong shape", '{"version": 1, "check": "no", "skip": null}'),
                       ("a list", "[]")):
        folder = tmp_path / name
        folder.mkdir()
        if text is not None:
            (folder / "updates.json").write_text(text, encoding="utf-8")
        found, net = _check(folder, release.answers())
        assert net.requests[:1] == [API], (name, net.requests)
        assert isinstance(found, updater.Offer), (name, found)

    folder = tmp_path / "off"
    folder.mkdir()
    (folder / "updates.json").write_text('{"version": 1, "check": false, "skip": null}',
                                         encoding="utf-8")
    found, net = _check(folder, release.answers())
    assert net.requests == [] and found == updater.Miss(1), (found, net.requests)


# ------------------------------------------------------------------ INV-2 ---


def test_only_a_signed_newer_list_is_offered(tmp_path, signer):
    """One fixture per step of § 4.4. Breaks when any step is skipped, a .sig
    from another key verifies, or only the first signature is tried."""
    stranger, _ = _key()
    text = _list("0.1.3")
    good = _Release("v0.1.3", text, [signer])

    found, _ = _check(tmp_path, good.answers())
    assert found == updater.Offer("0.1.3", good.url("linux"), len(b"linux bytes"),
                                  hashlib.sha256(b"linux bytes").hexdigest()), found
    found, _ = _check(tmp_path, good.answers(), platform="windows")
    assert found == updater.Offer("0.1.3", good.url("windows"), len(b"windows bytes"),
                                  hashlib.sha256(b"windows bytes").hexdigest()), found

    # Two signatures, the trusted one second: every signature is tried.
    for signers in ([stranger, signer], [signer, stranger]):
        found, _ = _check(tmp_path, _Release("v0.1.3", text, signers).answers())
        assert isinstance(found, updater.Offer), (signers, found)

    cases: list[tuple[str, int, dict[str, object]]] = []

    answers = good.answers()
    answers[API] = _Response(500, {}, b"{}")
    cases.append(("the API answers 500", 2, answers))
    answers = good.answers()
    answers[API] = b"not json"
    cases.append(("the API answers nonsense", 2, answers))
    answers = good.answers()
    answers[API] = b"[" * 300_000
    cases.append(("the API answers past its bound", 2, answers))

    for tag in ("v0.1.2", "v0.1.1", "v0.1.3-rc1", "v0.1_3", "v 0.1.3", "v0.1.٣"):
        cases.append((f"tag {tag}", 3, _Release(tag, _list("0.1.3"), [signer]).answers()))

    assets = good.assets()
    cases.append(("no .sig asset", 4, good.answers([a for a in assets
                                                    if not a["name"].endswith(".sig")])))
    cases.append(("two list assets", 4, good.answers([*assets, assets[0]])))
    cases.append(("no artefact for this platform", 4,
                  good.answers([a for a in assets if not a["name"].endswith("AppImage")])))
    http = [dict(a, browser_download_url=a["browser_download_url"].replace("https:", "http:"))
            if a["name"].endswith(".txt") else a for a in assets]
    cases.append(("an http list address", 4, good.answers(http)))

    answers = good.answers()
    answers[good.url("sig")] = good.sig + b"x"
    cases.append(("a .sig of 65 bytes", 5, answers))
    answers = good.answers()
    answers[good.url("sig")] = b"".join(signer.sign(text) for _ in range(5))
    cases.append(("a .sig of five signatures", 5, answers))
    big = text + b"x" * (16 * 1024)
    cases.append(("a list past 16 KiB", 5, _Release("v0.1.3", big, [signer]).answers()))

    answers = good.answers()
    answers[good.url("list")] = text.replace(b"0.1.3\n", b"0.1.4\n", 1)
    cases.append(("one byte changed in the list", 6, answers))
    answers = good.answers()
    answers[good.url("sig")] = bytes([good.sig[0] ^ 1]) + good.sig[1:]
    cases.append(("one byte changed in the .sig", 6, answers))
    cases.append(("signed by a stranger", 6, _Release("v0.1.3", text, [stranger]).answers()))
    cases.append(("a signed list that does not parse", 6,
                  _Release("v0.1.3", text + b"extra\n", [signer]).answers()))
    cases.append(("a signed list in CRLF", 6,
                  _Release("v0.1.3", text.replace(b"\n", b"\r\n"), [signer]).answers()))

    cases.append(("a list for another version", 7,
                  _Release("v0.1.3", _list("0.1.4"), [signer]).answers()))

    cases.append(("an artefact past 512 MiB", 8,
                  _Release("v0.1.3", _list("0.1.3", linux_size=512 * 1024 * 1024 + 1),
                           [signer]).answers()))

    for what, step, answers in cases:
        found, _ = _check(tmp_path, answers)
        assert found == updater.Miss(step), (what, found)

    (tmp_path / "updates.json").write_text('{"version": 1, "check": true, "skip": "0.1.3"}',
                                           encoding="utf-8")
    found, _ = _check(tmp_path, good.answers())
    assert found == updater.Miss(3), ("the skipped version", found)


def test_versions_parse_only_as_three_ascii_numbers():
    """§ 4.2: int() is not the guard -- it accepts "1_0" and " 1"."""
    assert updater.parse_version("v0.1.3") == (0, 1, 3)
    assert updater.parse_version("10.20.30") == (10, 20, 30)
    for text in ("0.1", "0.1.3.4", "v0.1_3", " 0.1.3", "0.1.3 ", "0.1.٣", "V0.1.3",
                 "vv0.1.3", "0.1.-3", "0.1.+3", ""):
        assert updater.parse_version(text) is None, text


# ------------------------------------------------------------------ INV-3 ---


def test_no_key_no_offer(tmp_path, monkeypatch):
    """Breaks when verification is skipped where no key exists."""
    private, _ = _key()
    monkeypatch.setattr(update_key, "TRUSTED", ())
    found, _ = _check(tmp_path, _Release("v0.1.3", _list("0.1.3"), [private]).answers())
    assert found == updater.Miss(6), found


# ------------------------------------------------------------------ INV-4 ---


def test_an_old_release_under_a_new_tag_is_refused(tmp_path, signer):
    """A genuinely signed list for 0.1.2, served behind a tag reading 0.1.9.
    Breaks when the version is read from the tag alone."""
    old = _list("0.1.2")
    served = _Release("v0.1.9", old, [signer])
    served.names["list"] = "Pressless-0.1.9-release.txt"
    found, _ = _check(tmp_path, served.answers())
    assert found == updater.Miss(7), found


# ------------------------------------------------------------------ INV-5 ---


def test_a_failed_check_is_silent(tmp_path, signer):
    """A double raising at each request: check returns the Miss of that step
    and raises nothing. The line updating writes for it names no URL and no
    path. Breaks when an exception escapes, or a log line carries a URL."""
    from pressless import updating

    good = _Release("v0.1.3", _list("0.1.3"), [signer])
    for url, step in ((API, 2), (good.url("list"), 5), (good.url("sig"), 5)):
        for failure in (OSError("down"), RuntimeError("odd"), ValueError("bad")):
            answers = good.answers()
            answers[url] = failure
            found, _ = _check(tmp_path, answers)
            assert found == updater.Miss(step), (url, failure, found)
            line = updating.miss_line(found)
            assert "http" not in line and "/" not in line and "\\" not in line, line
            assert str(step) in line, line


# ------------------------------------------------------------------ INV-6 ---


def _offer(data: bytes, url: str = "https://example.org/a") -> updater.Offer:
    return updater.Offer("0.1.3", url, len(data), hashlib.sha256(data).hexdigest())


def test_download_rows(tmp_path):
    """One case per row of § 4.6. Breaks when the hash is compared after the
    file is kept, a short stream raises UpdateRejected, or the file is staged
    anywhere but `beside`."""
    beside = tmp_path / "apps"
    beside.mkdir()
    (beside / "Pressless-0.1.2-x86_64.AppImage").write_bytes(b"old")
    before = sorted(beside.iterdir())
    data = b"the new program " * 50
    offer = _offer(data)

    rows = (
        ("Content-Length disagrees", _Response(200, {"Content-Length": str(len(data) + 1)}, data),
         updater.DownloadFailed),
        ("the stream ends early", _Response(200, {}, data[:-3]), updater.DownloadEndedEarly),
        ("more bytes arrive", _Response(200, {}, data + b"x"), updater.UpdateRejected),
        ("the hash differs", _Response(200, {}, data[:-1] + b"?"), updater.UpdateRejected),
        ("the transport fails", OSError("reset"), updater.DownloadFailed),
        ("an HTTP error status", _Response(404, {}, b"missing"), updater.DownloadFailed),
    )
    for what, answer, raised in rows:
        with pytest.raises(updater.UpdateError) as caught:
            updater.download(offer, beside, _Net({offer.asset_url: answer}))
        assert type(caught.value) is raised, (what, caught.value)
        assert sorted(beside.iterdir()) == before, (what, sorted(beside.iterdir()))

    lower = _Response(200, {"content-length": str(len(data))}, data)
    got = updater.download(offer, beside, _Net({offer.asset_url: lower}))
    assert got.parent == beside and got.read_bytes() == data
    assert got.name.startswith(".pressless-update-"), got.name


# ------------------------------------------------------------------ INV-7 ---


def test_redirect_to_http_is_refused():
    """Breaks when the default redirect handler is used."""
    handler = updater._HttpsOnly()
    request = urllib.request.Request("https://api.github.com/x")
    with pytest.raises(Exception):  # noqa: B017 -- any refusal stops the hop
        handler.redirect_request(request, None, 302, "Found", Message(), "http://evil.example/x")
    passed = handler.redirect_request(request, None, 302, "Found", Message(),
                                      "https://objects.githubusercontent.com/x")
    assert passed is not None and passed.full_url.startswith("https://")

    opener = updater._Urllib()._opener
    redirecting = [h for h in opener.handlers
                   if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert redirecting and all(isinstance(h, updater._HttpsOnly) for h in redirecting), (
        redirecting)


# ------------------------------------------------------------------ INV-9 ---


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_a_stray_zip_member_writes_nothing(tmp_path, monkeypatch):
    """Breaks when members are checked while being written, or a directory
    entry is refused.

    A refused zip's folder is removed afterwards either way, so the end state
    cannot tell the two orders apart: what is watched is whether anything was
    extracted at all before the refusal."""
    extracted: list[str] = []
    real_extract, real_extractall = zipfile.ZipFile.extract, zipfile.ZipFile.extractall
    monkeypatch.setattr(zipfile.ZipFile, "extract", lambda self, member, *a, **k: (
        extracted.append(str(member)), real_extract(self, member, *a, **k))[1])
    monkeypatch.setattr(zipfile.ZipFile, "extractall", lambda self, *a, **k: (
        extracted.append("*"), real_extractall(self, *a, **k))[1])
    beside = tmp_path / "program"
    beside.mkdir()
    (beside / "Pressless").mkdir()
    before = sorted(p.name for p in beside.iterdir())
    good = {"Pressless/": b"", "Pressless/Pressless.exe": b"exe",
            "Start Pressless.bat": b"@echo off\r\n"}
    for stray in ("evil.txt", "/etc/evil", "Pressless/../evil", "C:/evil",
                  "Pressless\\..\\evil", "Pressless/../../evil", "c:evil",
                  "Pressless/sub/../../evil", "Start Pressless.bat/x"):
        archive = _zip(beside / "update.zip", {**good, stray: b"stray"})
        with pytest.raises(updater.UpdateRejected):
            updater.unpack(archive, beside)
        assert sorted(p.name for p in beside.iterdir()) == before, (stray, list(beside.iterdir()))
        assert extracted == [], (stray, extracted)

    stage = tmp_path / "stage"
    (stage / "Pressless" / "_internal").mkdir(parents=True)
    (stage / "Pressless" / "Pressless.exe").write_bytes(b"exe")
    (stage / "Pressless" / "_internal" / "python.dll").write_bytes(b"dll")
    (stage / "Start Pressless.bat").write_bytes(b"@echo off\r\n")
    built = Path(shutil.make_archive(str(beside / "Pressless-0.1.3-windows"), "zip",
                                     root_dir=stage))
    unpacked = updater.unpack(built, beside)
    assert unpacked.parent == beside and unpacked.name.startswith("Pressless.new-"), unpacked
    assert (unpacked / "Pressless" / "_internal" / "python.dll").read_bytes() == b"dll"
    assert (unpacked / "Start Pressless.bat").read_bytes() == b"@echo off\r\n"
    assert not built.exists()


# ------------------------------------------------------------------ state ---


def test_the_state_file_round_trips(tmp_path):
    """§ 4.9: updates.json holds the switch and the skipped version, in its
    own shape."""
    assert updater.read_state(tmp_path) == (True, None)
    updater.write_state(tmp_path, check=False, skip="0.1.3")
    assert json.loads((tmp_path / "updates.json").read_text(encoding="utf-8")) == {
        "version": 1, "check": False, "skip": "0.1.3"}
    assert updater.read_state(tmp_path) == (False, "0.1.3")
