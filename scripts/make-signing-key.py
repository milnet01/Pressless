#!/usr/bin/env python3
"""Make the key that signs Pressless releases -- PRESS-0023 § 4.8.

    python3 scripts/make-signing-key.py <path outside this repository>

Writes a new Ed25519 private key to <path>, readable by its owner alone, and
prints only the public key, in the form src/pressless/update_key.py's TRUSTED
holds. Paste that line there. Then tell git where the key is, so
scripts/sign-release.py can find it:

    git config --add ants.pressless.signingKey <path>

Refuses a path that exists or lies inside this repository: the private key
must never be committed (INV-18), and nothing here overwrites a key a
release may already depend on. Keep a copy on a second drive. A lost key
cannot be recovered from (scope decision 4).
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    target = Path(argv[0]).expanduser().resolve()
    if target.is_relative_to(ROOT):
        print("refused: the key must live outside this repository", file=sys.stderr)
        return 1
    if target.exists():
        print("refused: that path already exists", file=sys.stderr)
        return 1

    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, "wb") as out:
        out.write(private)
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    print(base64.b64encode(public).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
