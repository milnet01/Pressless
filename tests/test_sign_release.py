"""The signer's two refusals (PRESS-0023 INV-19).

scripts/sign-release.py is loaded by path: its name is not an importable
module name. Only its two refusal functions run here; nothing reaches GitHub
and every key is made inside the test.
"""
from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sign-release.py"


def _signer():
    spec = importlib.util.spec_from_file_location("sign_release", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
