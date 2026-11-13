"""The signer's two refusals (PRESS-0023 INV-19).

scripts/sign-release.py is loaded by path: its name is not an importable
module name. Only its two refusal functions run here; nothing reaches GitHub
and every key is made inside the test.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _scripts import load_script
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from pressless import update_key

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sign-release.py"


def _signer():
    return load_script("sign-release.py")


def _public(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


def test_a_signature_the_committed_keys_reject_attaches_nothing():
    """Breaks when it verifies against the key it just signed with."""
    signer = _signer()
    ours, theirs = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    text = b"pressless-release 1\nversion 0.1.3\n"
    signatures = ours.sign(text)

    signer.require_trusted(text, signatures, (_public(ours),))
    with pytest.raises(signer.Refused):
        signer.require_trusted(text, signatures, (_public(theirs),))
    with pytest.raises(signer.Refused):
        signer.require_trusted(text, signatures, ())
    # Every signature must verify, not any one of them.
    with pytest.raises(signer.Refused):
        signer.require_trusted(text, ours.sign(text) + theirs.sign(text), (_public(ours),))


def test_a_build_from_another_commit_attaches_nothing():
    signer = _signer()
    signer.require_built_from("a" * 40, "a" * 40)
    with pytest.raises(signer.Refused):
        signer.require_built_from("a" * 40, "b" * 40)


def _key_file(folder: Path, name: str) -> Path:
    from cryptography.hazmat.primitives.serialization import NoEncryption, PrivateFormat
    path = folder / name
    path.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return path


def test_the_configured_keys_load_or_are_refused(tmp_path):
    """PRESS-0162 (review-code L8.3, L8.4): the paths were split on any
    whitespace, so a key on a drive whose name holds a space broke apart;
    an unreadable or malformed key raised a traceback; and nothing capped
    the keys at the four an installed copy accepts."""
    signer = _signer()
    spaced = tmp_path / "a drive"
    spaced.mkdir()
    one = _key_file(spaced, "one.pem")
    assert len(signer.load_keys(f"{one}\n")) == 1

    five = "\n".join(str(_key_file(tmp_path, f"k{n}.pem")) for n in range(5))
    bad = tmp_path / "bad.pem"
    bad.write_text("not a key")
    for configured in ("", five, str(tmp_path / "missing.pem"), str(bad)):
        with pytest.raises(signer.Refused):
            signer.load_keys(configured)


def test_a_local_tag_on_another_commit_signs_nothing():
    """PRESS-0162 (review-code L8.5): TRUSTED is read from the local tag,
    so a tag moved on GitHub and not fetched checked another commit."""
    signer = _signer()
    signer.require_local_tag("a" * 40, "a" * 40)
    with pytest.raises(signer.Refused):
        signer.require_local_tag("a" * 40, "b" * 40)


def test_no_configured_key_is_refused_in_words(tmp_path, monkeypatch):
    """PRESS-0184: `git config --get-all` exits 1 and prints nothing for a key
    that is not set, and the signer reported that as "git -C failed:" with
    nothing after it. Breaks when an unset key stops reaching load_keys."""
    signer = _signer()
    git = shutil.which("git")
    if git is None:
        pytest.skip("no git, so there is no configuration to read")
    subprocess.run((git, "init", "-q", str(tmp_path)), check=True)  # noqa: S603
    monkeypatch.setattr(signer, "ROOT", tmp_path)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    with pytest.raises(signer.Refused, match="no ants.pressless.signingKey is configured"):
        signer.sign("v0.0.0")


def test_the_committed_trusted_holds_a_key():
    """PRESS-0184: 0.6.0 was tagged with TRUSTED empty, and the signer found
    it only after the build. The gate runs this before any tag exists."""
    assert update_key.TRUSTED, "a release tagged now could never be signed"
    for key in update_key.TRUSTED:
        assert len(base64.b64decode(key, validate=True)) == 32


@pytest.mark.skipif(os.name == "nt", reason="Windows has no executable bit")
def test_the_signer_runs_by_its_own_name():
    """PRESS-0184: working-here.md gives the command without `python3`."""
    assert os.access(_SCRIPT, os.X_OK)


def test_the_changes_file_starts_at_the_release(monkeypatch):
    """PRESS-0023 INV-25. Breaks when the file starts above the release being
    signed, is cut inside a release, or outgrows what an installed copy reads."""
    from pressless import updater

    signer = _signer()
    log = ("# Changelog\n\n## [Unreleased]\n\n## [0.1.3] - d\n\nthree\n\n"
           "## [0.1.2] - d\n\ntwo\n\n## [0.1.1] - d\n\none\n")
    whole = (b"pressless-changes 1\nversion 0.1.3\n## [0.1.3] - d\n\nthree\n\n"
             b"## [0.1.2] - d\n\ntwo\n\n## [0.1.1] - d\n\none\n")
    assert signer.changes_text("0.1.3", log) == whole
    with pytest.raises(signer.Refused):
        signer.changes_text("0.1.4", log)

    assert signer.CHANGES_LIMIT == updater.CHANGES_LIMIT
    # One byte short of the whole: the oldest release goes, whole.
    monkeypatch.setattr(signer, "CHANGES_LIMIT", len(whole) - 1)
    cut = signer.changes_text("0.1.3", log)
    assert cut == whole[:whole.index(b"## [0.1.1]")], cut
    monkeypatch.setattr(signer, "CHANGES_LIMIT", 40)
    with pytest.raises(signer.Refused):
        signer.changes_text("0.1.3", log)


def test_an_installed_copy_reads_the_real_changelog():
    """What the signer writes from this repository's CHANGELOG.md is what the
    Updater reads back: the one release after 0.14.0, up to 0.15.0."""
    from pressless import updater

    log = (_SCRIPT.parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    found = updater.read_changes(_signer().changes_text("0.15.0", log), "0.15.0", "0.14.0")
    assert [version for version, _ in found] == ["0.15.0"], found
    assert "An AI helper can drive Pressless" in found[0][1], found
