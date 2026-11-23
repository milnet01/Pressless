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


@pytest.mark.skipif(os.name == "nt", reason="the signer runs on Linux only")
def test_git_output_is_read_as_utf_8_whatever_the_locale(tmp_path):
    """The changes file is UTF-8 (PRESS-0023 § 4.12), and `git show` hands it
    over as bytes. Read in the locale's encoding, a non-UTF-8 locale garbled
    it or raised. Breaks when _run decodes in anything but UTF-8."""
    import sys

    probe = tmp_path / "probe.py"
    probe.write_text(
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from _scripts import load_script\n"
        "said = load_script('sign-release.py')._run(sys.executable, '-c',\n"
        "    \"import sys; sys.stdout.buffer.write('caf\\\\u00e9'.encode('utf-8'))\")\n"
        "sys.stdout.buffer.write(said.encode('utf-8'))\n", encoding="utf-8")
    plain = {**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONCOERCECLOCALE": "0",
             "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run(  # noqa: S603 -- this interpreter, our own probe
        (sys.executable, "-X", "utf8=0", str(probe), str(Path(__file__).parent)),
        capture_output=True, env=plain, check=False)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout.decode("utf-8") == "café"


def test_a_malformed_trusted_is_refused_in_words(monkeypatch):
    """review-code: a TRUSTED that is not base64 keys, or is a bare annotation,
    raised a traceback rather than a refusal."""
    signer = _signer()
    key = Ed25519PrivateKey.generate()
    for trusted in (("not base64!",), (base64.b64encode(b"short").decode(),), (5,)):
        with pytest.raises(signer.Refused):
            signer.require_trusted(b"text", key.sign(b"text"), trusted)
    for source in ("TRUSTED: tuple[str, ...]\n", "TRUSTED = load()\n", "TRUSTED = 5\n"):
        monkeypatch.setattr(signer, "_run", lambda *args, source=source: source)
        with pytest.raises(signer.Refused):
            signer._trusted_at("v1.2.3")


_SHA = "c" * 40


class _GitHub:
    """`gh` and `git` as sign() calls them, over one draft release.

    `held` is the draft's assets. An upload of a name it already holds fails
    unless --clobber is passed, as gh's does. `runs` is the release workflow's
    runs, newest first, and --status and --limit are honoured."""

    def __init__(self, signer, folder: Path, key: Ed25519PrivateKey, held: set[str],
                 runs: list[str]) -> None:
        self.signer, self.held, self.runs = signer, set(held), runs
        self.trusted = f"TRUSTED = ({_public(key)!r},)\n"
        self.uploads: list[tuple[str, ...]] = []
        self.published = False

    def __call__(self, *args: str) -> str:
        import json
        if args[:3] == ("gh", "release", "view"):
            fields = args[-1]
            answer = {"assets": [{"name": name} for name in sorted(self.held)]}
            if "isDraft" in fields:
                answer["isDraft"] = not self.published
            return json.dumps(answer)
        if args[:2] == ("gh", "api") or "rev-parse" in args:
            return _SHA + "\n"
        if args[:3] == ("gh", "run", "list"):
            runs = self.runs
            if "--status" in args:
                runs = [run for run in runs if run == args[args.index("--status") + 1]]
            runs = runs[:int(args[args.index("--limit") + 1])]
            return json.dumps([{"headSha": _SHA, "conclusion": run} for run in runs])
        if "show" in args:
            return self.trusted if args[-1].endswith("update_key.py") else (
                "# Changelog\n\n## [1.2.3] - d\n\nthree\n")
        if args[:3] == ("gh", "release", "download"):
            folder = Path(args[args.index("--dir") + 1])
            for index, word in enumerate(args):
                if word == "--pattern":
                    (folder / args[index + 1]).write_bytes(b"built")
            return ""
        if args[:3] == ("gh", "release", "upload"):
            names = {Path(arg).name for arg in args[6:] if arg != "--clobber"}
            if names & self.held and "--clobber" not in args:
                raise self.signer.Refused("gh release upload failed: asset already exists")
            self.uploads.append(args)
            self.held |= names
            return ""
        if args[:3] == ("gh", "release", "edit"):
            self.published = True
            return ""
        raise AssertionError(f"not expected: {args}")


def _signing(monkeypatch, tmp_path, held=(), runs=("success",)):
    signer = _signer()
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(signer, "ROOT", tmp_path / "repository")
    monkeypatch.setattr(signer, "load_keys", lambda configured: [key])
    monkeypatch.setattr(signer, "_configured", lambda: "")
    built = {"Pressless-1.2.3-x86_64.AppImage", "Pressless-1.2.3-windows.zip"}
    github = _GitHub(signer, tmp_path, key, built | set(held), list(runs))
    monkeypatch.setattr(signer, "_run", github)
    return signer, github


def test_a_run_that_failed_after_uploading_can_be_run_again(monkeypatch, tmp_path):
    """review-code: a run failing after its upload left the signed files on the
    draft, and every rerun then failed at the upload, which never replaced them."""
    left = {"Pressless-1.2.3-release.txt", "Pressless-1.2.3-release.txt.sig"}
    signer, github = _signing(monkeypatch, tmp_path, held=left)
    signer.sign("v1.2.3")
    assert github.published
    # review-tests: publishing alone passed a sign() that skipped the names
    # the draft held, so the failed run's stale files shipped.
    [upload] = github.uploads
    assert "--clobber" in upload
    assert left <= {Path(arg).name for arg in upload[6:]}


def test_the_signer_names_each_file_an_installed_copy_fetches():
    """review-readability: the release's file names are spelt here and in
    updater._names, and a rename on one side only would make every
    installed copy refuse every release."""
    from pressless import updater

    signer = _signer()
    assert set(updater._names("1.2.3").values()) == signer.release_assets("1.2.3")


def test_a_failed_git_call_names_what_git_was_asked():
    """review-readability lead: every failed `git -C <root> ...` read
    "git -C failed"."""
    signer = _signer()
    with pytest.raises(signer.Refused, match=r"^git show v0\.0\.0:none failed: "):
        signer._run("git", "-C", str(_SCRIPT.parent), "show", "v0.0.0:none")


def test_a_draft_holding_a_stranger_is_refused_before_anything_is_uploaded(
        monkeypatch, tmp_path):
    """review-code: the draft's assets were read and never examined, so a stray
    file was refused only after this run had uploaded its own."""
    signer, github = _signing(monkeypatch, tmp_path, held={"notes.txt"})
    with pytest.raises(signer.Refused):
        signer.sign("v1.2.3")
    assert github.uploads == []
    assert not github.published


def test_a_success_behind_several_failed_runs_is_found(monkeypatch, tmp_path):
    """Lead: `--limit 5` was applied before the success filter, so five failed
    reruns hid the run that built the release."""
    signer, github = _signing(monkeypatch, tmp_path, runs=["failure"] * 5 + ["success"])
    signer.sign("v1.2.3")
    assert github.published
