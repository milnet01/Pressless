"""The public keys a release's signed list must verify against (PRESS-0023 § 4.1).

Each is a raw 32-byte Ed25519 public key in base64, decoded where a signature
is checked. The maintainer makes a key with scripts/make-signing-key.py and
pastes the line it prints here. Until then this is empty, and an empty tuple
offers nothing (INV-3). A new key is added beside the old one and shipped
before it signs anything (scope decision 4).

Imports nothing of Pressless's.
"""
from __future__ import annotations

TRUSTED: tuple[str, ...] = ()
