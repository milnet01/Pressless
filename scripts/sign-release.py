#!/usr/bin/env python3
"""Sign a draft release and publish it -- PRESS-0023 § 4.8.

    python3 scripts/sign-release.py v<X.Y.Z>

Run by hand, on the maintainer's machine, after the release workflow has built
the draft. CI never signs: the key would live in the repository's secrets,
and anyone who can change the workflow could sign (scope decision 5).

1. Reads every key path from `git config --get-all ants.pressless.signingKey`.
2. Refuses unless the release is a draft and the release workflow run that
   built it was for the tag's own commit (FIBR-0318).
3. Downloads the two artefacts, writes the signed list (§ 4.3), and signs it
   with each key.
4. Verifies every signature against update_key.TRUSTED as committed at the
   tag -- never against the key it just signed with -- and attaches nothing
   if one fails.
5. Uploads the list and its .sig, reads the asset list back, and requires
   exactly the four names (FIBR-0275).
6. Publishes the draft.

PRESSLESS_UPDATE_REPOSITORY names another repository for one run, as it does
for the Updater (§ 7.1). Needs `gh`, signed in, and `git`.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import load_pem_private_key

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = os.environ.get("PRESSLESS_UPDATE_REPOSITORY") or "milnet01/Pressless"
WORKFLOW = "release.yml"
_TAG = re.compile(r"v([0-9]+\.[0-9]+\.[0-9]+)", re.ASCII)


class Refused(Exception):
    """The release is not signed or published, and why."""


def require_trusted(text: bytes, signatures: bytes, trusted: tuple[str, ...]) -> None:
    """Every signature verifies against some key in `trusted`, the keys the
    tag's own commit ships -- so a release is never signed with a key the
    copies it reaches do not hold."""
    keys = [Ed25519PublicKey.from_public_bytes(base64.b64decode(k, validate=True))
            for k in trusted]
    if not keys:
        raise Refused("the tag's update_key.TRUSTED is empty, so no copy could verify this")
    if not signatures or len(signatures) % 64:
        raise Refused("the signatures are not whole 64-byte signatures")
    for start in range(0, len(signatures), 64):
        signature = signatures[start:start + 64]
        if not any(_verifies(key, signature, text) for key in keys):
            raise Refused("a signature does not verify against the keys committed at the tag")


def _verifies(key: Ed25519PublicKey, signature: bytes, text: bytes) -> bool:
    try:
        key.verify(signature, text)
    except InvalidSignature:
        return False
    return True


def require_built_from(tag_commit: str, run_commit: str) -> None:
    """The artefacts were built from the commit the tag names (FIBR-0318)."""
    if tag_commit != run_commit:
        raise Refused(f"the release was built from {run_commit[:12]}, "
                      f"and the tag names {tag_commit[:12]}")


def _run(*args: str) -> str:
    done = subprocess.run(args, check=False, capture_output=True, text=True)  # noqa: S603
    if done.returncode != 0:
        raise Refused(f"{args[0]} {args[1]} failed: {done.stderr.strip()}")
    return done.stdout


def _trusted_at(tag: str) -> tuple[str, ...]:
    source = _run("git", "-C", str(ROOT), "show", f"{tag}:src/pressless/update_key.py")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AnnAssign | ast.Assign):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            if any(isinstance(t, ast.Name) and t.id == "TRUSTED" for t in targets):
                return tuple(ast.literal_eval(node.value))
    raise Refused("the tag's update_key.py assigns no TRUSTED")


def _list(version: str, folder: Path) -> bytes:
    lines = ["pressless-release 1", f"version {version}"]
    for platform, name in (("linux", f"Pressless-{version}-x86_64.AppImage"),
                           ("windows", f"Pressless-{version}-windows.zip")):
        data = (folder / name).read_bytes()
        lines.append(f"{platform} {name} {len(data)} {hashlib.sha256(data).hexdigest()}")
    return ("\n".join(lines) + "\n").encode("ascii")


def sign(tag: str) -> None:
    matched = _TAG.fullmatch(tag)
    if matched is None:
        raise Refused("the tag must read v<X.Y.Z>")
    version = matched.group(1)

    paths = _run("git", "-C", str(ROOT), "config", "--get-all",
                 "ants.pressless.signingKey").split()
    if not paths:
        raise Refused("no ants.pressless.signingKey is configured")
    keys: list[Ed25519PrivateKey] = []
    for path in paths:
        loaded = load_pem_private_key(Path(path).expanduser().read_bytes(), password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise Refused("a configured signing key is not an Ed25519 key")
        keys.append(loaded)

    release = json.loads(_run("gh", "release", "view", tag, "--repo", REPOSITORY,
                              "--json", "isDraft,assets"))
    if not release["isDraft"]:
        raise Refused("the release is already published; only a draft is signed")
    tag_commit = _run("gh", "api", f"repos/{REPOSITORY}/commits/{tag}", "--jq", ".sha").strip()
    runs = json.loads(_run("gh", "run", "list", "--repo", REPOSITORY, "--workflow", WORKFLOW,
                           "--branch", tag, "--json", "headSha,conclusion", "--limit", "5"))
    built = [run["headSha"] for run in runs if run.get("conclusion") == "success"]
    if not built:
        raise Refused("no successful release workflow run is recorded for the tag")
    require_built_from(tag_commit, built[0])

    trusted = _trusted_at(tag)
    # Beside the repository, never the system temporary folder: two artefacts
    # are downloaded, and on this machine /tmp is memory.
    work = Path(tempfile.mkdtemp(prefix="pressless-sign-", dir=ROOT.parent))
    try:
        _run("gh", "release", "download", tag, "--repo", REPOSITORY, "--dir", str(work),
             "--pattern", f"Pressless-{version}-x86_64.AppImage",
             "--pattern", f"Pressless-{version}-windows.zip")
        text = _list(version, work)
        signatures = b"".join(key.sign(text) for key in keys)
        require_trusted(text, signatures, trusted)
        listed = work / f"Pressless-{version}-release.txt"
        listed.write_bytes(text)
        (work / f"{listed.name}.sig").write_bytes(signatures)
        _run("gh", "release", "upload", tag, "--repo", REPOSITORY,
             str(listed), f"{listed}.sig")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    names = {asset["name"] for asset in json.loads(_run(
        "gh", "release", "view", tag, "--repo", REPOSITORY, "--json", "assets"))["assets"]}
    wanted = {f"Pressless-{version}-x86_64.AppImage", f"Pressless-{version}-windows.zip",
              f"Pressless-{version}-release.txt", f"Pressless-{version}-release.txt.sig"}
    if names != wanted:
        raise Refused(f"the release holds {sorted(names)}, not exactly {sorted(wanted)}")
    _run("gh", "release", "edit", tag, "--repo", REPOSITORY, "--draft=false")
    print(f"{tag} is signed and published.")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: sign-release.py v<X.Y.Z>", file=sys.stderr)
        return 2
    try:
        sign(argv[0])
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
