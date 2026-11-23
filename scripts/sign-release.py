#!/usr/bin/env python3
"""Sign a draft release and publish it -- PRESS-0023 § 4.8.

    python3 scripts/sign-release.py v<X.Y.Z>

Run by hand, on the maintainer's machine, after the release workflow has built
the draft. It runs on Linux only. CI never signs: the key would live in the
repository's secrets, and anyone who can change the workflow could sign
(scope decision 5).

1. Reads every key path from `git config --get-all ants.pressless.signingKey`.
2. Refuses unless the release is a draft holding both artefacts and nothing
   but this release's files, and the release workflow run that built it was
   for the tag's own commit (FIBR-0318).
3. Downloads the two artefacts and refuses unless each one's SHA-256 is the
   one that run recorded (PRESS-0486). Then writes the signed list (§ 4.3)
   and the changes file (§ 4.12, from CHANGELOG.md at the tag), and signs
   each with each key.
4. Verifies every signature against update_key.TRUSTED as committed at the
   tag -- never against the key it just signed with -- and attaches nothing
   if one fails.
5. Uploads both files and their .sig files, replacing any a failed run
   left, reads the asset list back, and requires exactly those names beside
   the two artefacts (FIBR-0275).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _refusing  # noqa: E402 -- beside this script, shared with publish-jpeg-xl.py
from _refusing import Refused  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = os.environ.get("PRESSLESS_UPDATE_REPOSITORY") or "milnet01/Pressless"
WORKFLOW = "release.yml"
# What release.yml's publish job names the record of each file's SHA-256 it
# keeps with the run, and the one file inside it. Kept with the run, not the
# draft, so whoever can swap a draft's files cannot rewrite it.
RECORD = "fingerprints"
RECORD_FILE = "fingerprints.txt"
_RECORDED = re.compile(r"([0-9a-f]{64}) [ *](.+)", re.ASCII)
_TAG = re.compile(r"v([0-9]+\.[0-9]+\.[0-9]+)", re.ASCII)
# What an installed copy will read of a changes file: updater.CHANGES_LIMIT.
# Written out, because this script reads nothing of Pressless's but at the tag.
CHANGES_LIMIT = 512 * 1024


def require_trusted(text: bytes, signatures: bytes, trusted: tuple[str, ...]) -> None:
    """Every signature verifies against some key in `trusted`, the keys the
    tag's own commit ships -- so a release is never signed with a key the
    copies it reaches do not hold."""
    try:
        keys = [Ed25519PublicKey.from_public_bytes(base64.b64decode(k, validate=True))
                for k in trusted]
    except (ValueError, TypeError):
        raise Refused("a key in the tag's update_key.TRUSTED is not a base64 "
                      "Ed25519 public key") from None
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


def require_recorded(record: str, files: dict[str, bytes]) -> None:
    """Each file is byte for byte the one the release run built: its SHA-256
    is the one `sha256sum` wrote for it in that run (PRESS-0486)."""
    recorded: dict[str, str] = {}
    for line in record.splitlines():
        found = _RECORDED.fullmatch(line)
        if found is None:
            raise Refused("the release run's record of fingerprints cannot be read")
        recorded[found.group(2)] = found.group(1)
    for name, data in files.items():
        if name not in recorded:
            raise Refused(f"the release run recorded no fingerprint for {name}")
        if hashlib.sha256(data).hexdigest() != recorded[name]:
            raise Refused(f"{name} is not the file the release run built: "
                          "its SHA-256 is not the one that run recorded")


def _record(run: str, folder: Path) -> str:
    """The record of fingerprints the release run `run` kept with it."""
    try:
        _run("gh", "run", "download", run, "--repo", REPOSITORY,
             "--name", RECORD, "--dir", str(folder))
        return (folder / RECORD_FILE).read_text(encoding="ascii")
    except (Refused, OSError, UnicodeDecodeError) as exc:
        raise Refused("the release run left no record of its files' fingerprints, "
                      f"so nothing shows these are the files it built ({exc})") from None


def require_built_from(tag_commit: str, run_commit: str) -> None:
    """The artefacts were built from the commit the tag names (FIBR-0318)."""
    if tag_commit != run_commit:
        raise Refused(f"the release was built from {run_commit[:12]}, "
                      f"and the tag names {tag_commit[:12]}")


def _run(*args: str) -> str:
    # UTF-8 whatever the locale: CHANGELOG.md is UTF-8, and so is its changes file.
    return _refusing.run(args)


def _configured() -> str:
    """What `git config --get-all` holds for the signing keys. It exits 1 and
    prints nothing for a key that is not set; that is load_keys' refusal to
    word, not _run's (PRESS-0184)."""
    args = ("git", "-C", str(ROOT), "config", "--get-all", "ants.pressless.signingKey")
    done = subprocess.run(args, check=False, capture_output=True,  # noqa: S603
                          encoding="utf-8")
    if done.returncode not in (0, 1):
        raise Refused(f"git config failed: {done.stderr.strip()}")
    return done.stdout


def _trusted_at(tag: str) -> tuple[str, ...]:
    source = _run("git", "-C", str(ROOT), "show", f"{tag}:src/pressless/update_key.py")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AnnAssign | ast.Assign) and node.value is not None:
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            if any(isinstance(t, ast.Name) and t.id == "TRUSTED" for t in targets):
                try:
                    return tuple(ast.literal_eval(node.value))
                except (ValueError, TypeError):
                    raise Refused("the tag's update_key.TRUSTED is not a written-out "
                                  "list of keys") from None
    raise Refused("the tag's update_key.py assigns no TRUSTED")


def artefacts(version: str) -> dict[str, str]:
    """The two files the release workflow builds, by platform, as
    build-linux.sh and build-windows.sh name them. updater._names spells
    these and signed_files' names again, for an installed copy to fetch;
    tests/test_sign_release.py holds the two equal."""
    return {"linux": f"Pressless-{version}-x86_64.AppImage",
            "windows": f"Pressless-{version}-windows.zip"}


def signed_files(version: str) -> tuple[str, str]:
    """The list (§ 4.3) and the changes file (§ 4.12) this script signs."""
    return f"Pressless-{version}-release.txt", f"Pressless-{version}-changes.txt"


def release_assets(version: str) -> set[str]:
    """Everything a signed release holds, and nothing else."""
    return {*artefacts(version).values(),
            *(name + ending for name in signed_files(version) for ending in ("", ".sig"))}


def _list(version: str, folder: Path) -> bytes:
    lines = ["pressless-release 1", f"version {version}"]
    for platform, name in artefacts(version).items():
        data = (folder / name).read_bytes()
        lines.append(f"{platform} {name} {len(data)} {hashlib.sha256(data).hexdigest()}")
    return ("\n".join(lines) + "\n").encode("ascii")


def changes_text(version: str, changelog: str) -> bytes:
    """The changes file (§ 4.12): CHANGELOG.md from `version`'s heading down.
    Past CHANGES_LIMIT the oldest releases are left off, each one whole."""
    start = changelog.find(f"\n## [{version}]")
    if start < 0:
        raise Refused(f"CHANGELOG.md has no heading for {version}")
    header = f"pressless-changes 1\nversion {version}\n"
    kept = changelog[start + 1:]
    while len((header + kept).encode("utf-8")) > CHANGES_LIMIT:
        cut = kept.rfind("\n## [")
        if cut < 0:
            raise Refused(f"{version}'s own changelog entry is past the changes file's size")
        kept = kept[:cut + 1]
    return (header + kept).encode("utf-8")


def load_keys(configured: str) -> list[Ed25519PrivateKey]:
    """The signing keys, one path per line of `git config --get-all`.

    Split on lines, not whitespace, so a path holding a space stays whole; a
    key that will not load is a refusal, not a traceback; and no more than
    four, because an installed copy accepts one to four signatures (§ 4.3)
    and a fifth publishes a release every copy misses (PRESS-0162).
    """
    paths = [line.strip() for line in configured.splitlines() if line.strip()]
    if not paths:
        raise Refused("no ants.pressless.signingKey is configured")
    if len(paths) > 4:
        raise Refused(f"{len(paths)} signing keys are configured; a release carries at most 4")
    keys: list[Ed25519PrivateKey] = []
    for path in paths:
        try:
            loaded = load_pem_private_key(Path(path).expanduser().read_bytes(), password=None)
        except (OSError, ValueError, TypeError) as exc:
            raise Refused(f"a configured signing key could not be loaded: "
                          f"{type(exc).__name__}") from None
        if not isinstance(loaded, Ed25519PrivateKey):
            raise Refused("a configured signing key is not an Ed25519 key")
        keys.append(loaded)
    return keys


def require_local_tag(local: str, remote: str) -> None:
    """Refuse unless the local tag is the commit GitHub's tag names."""
    if local != remote:
        raise Refused("the local tag is not the commit GitHub's tag names; "
                      "fetch the tags and run this again")


def sign(tag: str) -> None:
    matched = _TAG.fullmatch(tag)
    if matched is None:
        raise Refused("the tag must read v<X.Y.Z>")
    version = matched.group(1)

    keys = load_keys(_configured())

    release = json.loads(_run("gh", "release", "view", tag, "--repo", REPOSITORY,
                              "--json", "isDraft,assets"))
    if not release["isDraft"]:
        raise Refused("the release is already published; only a draft is signed")
    held = {asset["name"] for asset in release["assets"]}
    wanted = release_assets(version)
    # A failed run may have left this release's own files; anything else is refused.
    if not set(artefacts(version).values()) <= held or not held <= wanted:
        raise Refused(f"the draft holds {sorted(held)}; it must hold both artefacts "
                      f"and nothing but {sorted(wanted)}")
    tag_commit = _run("gh", "api", f"repos/{REPOSITORY}/commits/{tag}", "--jq", ".sha").strip()
    # TRUSTED is read from the LOCAL tag below, so it must be GitHub's commit.
    require_local_tag(_run("git", "-C", str(ROOT), "rev-parse", f"{tag}^{{commit}}").strip(),
                      tag_commit)
    # Filtered by gh before the limit, so failed reruns cannot hide the success.
    runs = json.loads(_run("gh", "run", "list", "--repo", REPOSITORY, "--workflow", WORKFLOW,
                           "--branch", tag, "--status", "success",
                           "--json", "databaseId,headSha,conclusion", "--limit", "1"))
    built = [run for run in runs if run.get("conclusion") == "success"]
    if not built:
        raise Refused("no successful release workflow run is recorded for the tag")
    require_built_from(tag_commit, built[0]["headSha"])

    trusted = _trusted_at(tag)
    # Beside the repository, never the system temporary folder: two artefacts
    # are downloaded, and on this machine /tmp is memory.
    work = Path(tempfile.mkdtemp(prefix="pressless-sign-", dir=ROOT.parent))
    try:
        _run("gh", "release", "download", tag, "--repo", REPOSITORY, "--dir", str(work),
             *(word for name in artefacts(version).values() for word in ("--pattern", name)))
        # Before anything is signed: the bytes are the ones that run built.
        require_recorded(_record(str(built[0]["databaseId"]), work / RECORD),
                         {name: (work / name).read_bytes()
                          for name in artefacts(version).values()})
        changes = changes_text(version, _run("git", "-C", str(ROOT), "show",
                                             f"{tag}:CHANGELOG.md"))
        # Both are signed and proved before either is attached.
        uploads: list[str] = []
        for name, data in zip(signed_files(version), (_list(version, work), changes),
                              strict=True):
            signatures = b"".join(key.sign(data) for key in keys)
            require_trusted(data, signatures, trusted)
            (work / name).write_bytes(data)
            (work / f"{name}.sig").write_bytes(signatures)
            uploads += [str(work / name), str(work / f"{name}.sig")]
        # --clobber replaces what a run that failed after its upload left.
        _run("gh", "release", "upload", tag, "--repo", REPOSITORY, "--clobber", *uploads)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    names = {asset["name"] for asset in json.loads(_run(
        "gh", "release", "view", tag, "--repo", REPOSITORY, "--json", "assets"))["assets"]}
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
