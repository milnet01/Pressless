"""The gate's --sweep option (PRESS-0277): the leak pattern over named files.

A review packet sits outside the tree, so the tree, commit and ref sweeps
never read it. --sweep runs the script's own pattern over the files named,
and nothing else, so the pattern stays in one place.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "local-ci.sh"
_BASH = shutil.which("bash")

# Built here, so the tree sweep never meets the whole word in this file.
_NAMED = "Ch" + "arl"

# On Windows `bash` can resolve to WSL's, which sees none of this checkout.
pytestmark = pytest.mark.skipif(sys.platform == "win32" or _BASH is None,
                                reason="the gate script runs under bash on Linux and in CI")


def _sweep(*files: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([_BASH, str(_SCRIPT), "--sweep", *map(str, files)],  # noqa: S603 -- this repository's own gate
                          capture_output=True, text=True, timeout=120, check=False)


def test_a_named_file_naming_the_writer_fails(tmp_path):
    """Breaks when a hit prints its text: GitHub's log is public, and would
    publish the very thing the sweep found. Where it is, and only that."""
    packet = tmp_path / "packet.md"
    packet.write_text(f"Plain words.\nA line by {_NAMED} here.\n", encoding="utf-8")
    ran = _sweep(packet)
    assert ran.returncode == 1
    assert f"{packet}:2" in ran.stderr
    assert "A line by" not in ran.stderr
    assert f"{packet} names the writer" in ran.stderr


def test_a_clean_file_passes_and_nothing_else_runs(tmp_path):
    packet = tmp_path / "packet.md"
    packet.write_text("Plain words.\n", encoding="utf-8")
    ran = _sweep(packet)
    assert ran.returncode == 0, ran.stderr
    assert f"clean: {packet}" in ran.stdout
    assert "clean: tree" not in ran.stdout
    assert "=== ruff ===" not in ran.stdout


def test_a_location_never_completes_a_match(tmp_path):
    """PRESS-0439. Breaks when the pattern is matched against the line's
    location as well as its text: line 18 starting "down" read as a hit."""
    packet = tmp_path / "packet.md"
    packet.write_text("Plain words.\n" * 17 + "down the road\n", encoding="utf-8")
    ran = _sweep(packet)
    assert ran.returncode == 0, ran.stderr
    assert f"clean: {packet}" in ran.stdout


def test_every_file_named_is_swept(tmp_path):
    clean, named = tmp_path / "clean.md", tmp_path / "named.md"
    clean.write_text("Plain words.\n", encoding="utf-8")
    named.write_text(f"{_NAMED}\n", encoding="utf-8")
    ran = _sweep(clean, named)
    assert ran.returncode == 1
    assert f"{named} names the writer" in ran.stderr


def test_a_missing_file_fails_rather_than_passing(tmp_path):
    ran = _sweep(tmp_path / "absent.md")
    assert ran.returncode == 1
    assert "absent.md" in ran.stderr


def test_sweep_with_no_file_fails():
    ran = _sweep()
    assert ran.returncode == 1
    assert "--sweep" in ran.stderr


def test_an_unknown_option_is_refused_before_anything_runs(tmp_path):
    """PRESS-0300. Breaks when the gate takes a mistyped option, `--doc` for
    `--docs`, as no option, and runs the whole gate instead of refusing.

    A Python that refuses to run is first on PATH, so a regression stops at
    the gate's interpreter step rather than running the suite from inside it.
    """
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    for name in ("python3", "python"):
        (stand_ins / name).write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (stand_ins / name).chmod(0o755)
    ran = subprocess.run([_BASH, str(_SCRIPT), "--doc"],  # noqa: S603 -- this repository's own gate
                         env={"PATH": f"{stand_ins}:/usr/bin:/bin", "HOME": str(tmp_path)},
                         capture_output=True, text=True, timeout=120, check=False)
    assert ran.returncode == 1
    assert "unknown option --doc" in ran.stderr
    assert "=== " not in ran.stdout


# The machine-local key's patterns, as a harmless stand-in: a scratch
# repository sets it, so no real identifying string is ever written here.
_STAND_IN = "zebra" + "quokka"
_GIT = shutil.which("git")


class _Scratch:
    """A throwaway repository holding the real gate script, with the stand-in
    as its machine-local pattern and no config from this machine."""

    def __init__(self, tmp_path: Path, patterns: str = _STAND_IN) -> None:
        self.root = tmp_path / "repository"
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(_SCRIPT, self.root / "scripts" / "local-ci.sh")
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"}
        self.git("init", "-q")
        self.git("config", "ants.pressless.leakPatterns", patterns)
        self.commit("start")

    def git(self, *arguments: str) -> str:
        return subprocess.run([_GIT, *arguments], cwd=self.root, env=self.env,  # noqa: S603 -- a scratch repository
                              check=True, capture_output=True, text=True).stdout

    def commit(self, message: str, *, who: str = "gate <gate@example.invalid>") -> None:
        name, email = who.removesuffix(">").split(" <")
        self.git("add", "-A")
        self.git("-c", f"user.name={name}", "-c", f"user.email={email}",
                 "commit", "-q", "--allow-empty", "-m", message)

    def sweep(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([_BASH, str(self.root / "scripts" / "local-ci.sh"), *arguments],  # noqa: S603
                              cwd=self.root, env=self.env, capture_output=True, text=True,
                              timeout=120, check=False)


def _picture(scratch: _Scratch, words: str) -> None:
    """A file git calls binary (it holds a NUL), with `words` among its bytes."""
    (scratch.root / "picture.png").write_bytes(b"\x89PNG\x00\x01" + words.encode() + b"\x00")


def test_the_stand_in_is_found_in_a_text_file(tmp_path):
    """The control for the binary case below: the same words, in a file git
    reads as text."""
    scratch = _Scratch(tmp_path)
    (scratch.root / "notes.txt").write_text(f"one\n{_STAND_IN}\n", encoding="utf-8")
    scratch.commit("notes")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert "notes.txt:2" in ran.stderr
    assert "tree names the writer" in ran.stderr


def test_a_binary_file_naming_the_writer_fails_the_tree_sweep(tmp_path):
    """Breaks when a binary match, which git grep reports as `Binary file X
    matches` with no text, is dropped as a line the pattern does not match.
    A picture's metadata is where a name most easily hides."""
    scratch = _Scratch(tmp_path)
    _picture(scratch, _STAND_IN)
    scratch.commit("picture")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert "picture.png" in ran.stderr.splitlines()
    assert "tree names the writer" in ran.stderr


def test_a_binary_file_only_in_history_fails_the_history_sweep(tmp_path):
    """Breaks the same way, for a file a later commit removed."""
    scratch = _Scratch(tmp_path)
    _picture(scratch, _STAND_IN)
    scratch.commit("picture")
    scratch.git("rm", "-q", "picture.png")
    scratch.commit("no picture")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert "clean: tree" in ran.stdout
    assert any(line.endswith(":picture.png") for line in ran.stderr.splitlines())
    assert "history names the writer" in ran.stderr


@pytest.mark.parametrize("who", [f"{_STAND_IN} <someone@example.invalid>",
                                 f"someone <{_STAND_IN}@example.invalid>"])
def test_a_commit_identity_naming_the_writer_fails(tmp_path, who):
    """Breaks when the sweep reads a commit's message but not who wrote it.
    A push publishes the author's and committer's names and addresses."""
    scratch = _Scratch(tmp_path)
    scratch.commit("plain words", who=who)
    head = scratch.git("rev-parse", "HEAD").strip()
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert head in ran.stderr
    assert _STAND_IN not in ran.stderr


def test_a_tagger_naming_the_writer_fails(tmp_path):
    """Breaks when the refs surface reads a tag's message but not its tagger."""
    scratch = _Scratch(tmp_path)
    scratch.git("-c", f"user.name={_STAND_IN}", "-c", "user.email=someone@example.invalid",
                "tag", "-a", "v1", "-m", "plain words")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert "refs/tags/v1" in ran.stderr


def test_a_path_naming_the_writer_fails(tmp_path):
    """Breaks when only file CONTENTS are searched: a push publishes every
    path in every commit, and git grep never reads a path."""
    scratch = _Scratch(tmp_path)
    (scratch.root / f"{_STAND_IN}.txt").write_text("plain words\n", encoding="utf-8")
    scratch.commit("a file")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert "names the writer" in ran.stderr


def test_a_path_only_a_merge_adds_fails(tmp_path):
    """Breaks when the commit log lists no paths for a merge, as `git log`
    does by default: a file added while resolving one, with clean contents,
    then passes every surface."""
    scratch = _Scratch(tmp_path)
    scratch.git("checkout", "-q", "-b", "side")
    (scratch.root / "side.txt").write_text("plain words\n", encoding="utf-8")
    scratch.commit("side")
    scratch.git("checkout", "-q", "-")
    (scratch.root / "main.txt").write_text("plain words\n", encoding="utf-8")
    scratch.commit("main")
    scratch.git("-c", "user.name=gate", "-c", "user.email=gate@example.invalid",
                "merge", "-q", "--no-ff", "--no-commit", "side")
    (scratch.root / f"{_STAND_IN}.txt").write_text("plain words\n", encoding="utf-8")
    scratch.commit("merge")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert "commits: messages, authors and paths names the writer" in ran.stderr


def test_on_github_a_location_naming_the_writer_is_not_printed(tmp_path):
    """Breaks when a ref whose own name matches is printed as the place of the
    hit: GitHub's log is public, so that repeats the name there."""
    scratch = _Scratch(tmp_path)
    scratch.git("branch", f"notes-{_STAND_IN}")
    scratch.env["CI"] = "true"
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert "refs and tag messages names the writer" in ran.stderr
    assert _STAND_IN not in ran.stderr + ran.stdout


def test_off_github_the_location_is_printed(tmp_path):
    """The control: on the maintainer's machine the hit names its ref."""
    scratch = _Scratch(tmp_path)
    scratch.git("branch", f"notes-{_STAND_IN}")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 1
    assert f"refs/heads/notes-{_STAND_IN}" in ran.stderr


def test_a_clean_scratch_repository_passes(tmp_path):
    """The control for the cases above: a binary file, a tag and the gate
    script's own spelling of the pattern, the stand-in nowhere, and the sweep
    passes every surface."""
    scratch = _Scratch(tmp_path)
    _picture(scratch, "plain")
    scratch.commit("picture")
    scratch.git("-c", "user.name=gate", "-c", "user.email=gate@example.invalid",
                "tag", "-a", "v1", "-m", "plain words")
    ran = scratch.sweep("--docs")
    assert ran.returncode == 0, ran.stderr
    for surface in ("tree", "history", "refs and tag messages"):
        assert f"clean: {surface}" in ran.stdout


def test_a_malformed_pattern_key_fails_rather_than_matching_nothing(tmp_path):
    """Breaks when grep's exit 2, a pattern it cannot read, is taken for its
    exit 1, no match, and every file reports clean."""
    scratch = _Scratch(tmp_path, patterns="unclosed(")
    packet = tmp_path / "packet.md"
    packet.write_text("plain words\n", encoding="utf-8")
    ran = scratch.sweep("--sweep", str(packet))
    assert ran.returncode == 1
    assert "clean:" not in ran.stdout
    assert "ants.pressless.leakPatterns" in ran.stderr


def test_the_patterns_never_reach_a_command_line(tmp_path):
    """Breaks when the pattern is passed as an argument, where any process on
    the machine can read it in /proc/<pid>/cmdline. Every program the sweep
    starts is found on PATH, and each is a stand-in that records its
    arguments. A program called by its full path would escape the record."""
    scratch = _Scratch(tmp_path)
    record = tmp_path / "arguments.txt"
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    for name in ("git", "grep", "sh", "xargs", "awk", "sed", "tr", "cut",
                 "cat", "dirname", "mktemp", "rm"):
        real = shutil.which(name, path="/usr/bin:/bin")
        recorder = f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{record}"\nexec {real} "$@"\n'
        (stand_ins / name).write_text(recorder, encoding="utf-8")
        (stand_ins / name).chmod(0o755)
    scratch.env["PATH"] = f"{stand_ins}:/usr/bin:/bin"
    ran = scratch.sweep("--docs")
    assert ran.returncode == 0, ran.stderr
    arguments = record.read_text(encoding="utf-8")
    assert "grep" in arguments
    assert _STAND_IN not in arguments


def _gate_in_a_scratch_repository(tmp_path: Path, env: dict[str, str],
                                  keys: dict[str, str] | None = None,
                                  prepare=None, args: tuple[str, ...] = ()) -> tuple[Path, str]:
    """The real gate script, run in a throwaway repository with a stand-in for
    Python that records each call, and the PRESSLESS_ variables pytest is given,
    and answers yes. `keys` are set in the repository's own config, and
    `prepare` gets the repository before the run. Returns the repository and
    the record. `args` are passed to the gate."""
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    for name in ("local-ci.sh", "python.sh"):
        shutil.copy(_SCRIPT.parent / name, repository / "scripts" / name)
    (repository / "pyproject.toml").write_text("", encoding="utf-8")
    record = tmp_path / "record.txt"
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    # `-m venv <where>` makes <where>/bin/python, the stand-in again.
    python = (f'#!/bin/sh\necho "$0 $*" >> "{record}"\n'
              f'if [ "$2 $3" = "pytest -ra" ]; then env | grep "^PRESSLESS_" >> "{record}"; fi\n'
              'if [ "$1 $2" = "-m venv" ]; then mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; fi\n')
    (stand_ins / "python3").write_text(python, encoding="utf-8")
    (stand_ins / "python3").chmod(0o755)
    environment = {"PATH": f"{stand_ins}:/usr/bin:/bin", "HOME": str(tmp_path),
                   "GIT_CONFIG_NOSYSTEM": "1", **env}
    identity = ["-c", "user.name=gate", "-c", "user.email=gate@example.invalid"]
    git = shutil.which("git")
    settings = [["config", f"ants.pressless.{key}", value] for key, value in (keys or {}).items()]
    commit = [*identity, "commit", "-qm", "scratch"]
    for arguments in (["init", "-q"], *settings, ["add", "."], commit):
        subprocess.run([git, *arguments], cwd=repository, env=environment,  # noqa: S603 -- a scratch repository
                       check=True, capture_output=True)
    if prepare:
        prepare(repository)
    ran = subprocess.run([_BASH, str(repository / "scripts" / "local-ci.sh"), *args],  # noqa: S603 -- this repository's own gate
                         env=environment, capture_output=True, text=True, timeout=120, check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    return repository, record.read_text(encoding="utf-8") + ran.stdout


def test_a_local_run_uses_the_versions_github_would_install(tmp_path):
    """A local run brings its own environment up to what a fresh install
    resolves today, and runs ruff and pytest from it.

    Breaks when the gate runs whatever this machine last installed, so it can
    pass what GitHub then fails."""
    repository, record = _gate_in_a_scratch_repository(tmp_path, {})
    assert "-m venv .venv" in record
    own = next(line for line in record.splitlines() if "pip install" in line)
    assert own.split()[0].endswith(".venv/bin/python")
    assert "--upgrade --upgrade-strategy eager -e .[dev]" in own
    for tool in ("-m ruff check src/ tests/", "-m pytest -ra"):
        line = next(line for line in record.splitlines() if tool in line)
        assert line.split()[0].endswith(".venv/bin/python"), line
    assert (repository / ".venv").is_dir()


def test_github_keeps_the_environment_it_installed(tmp_path):
    """On GitHub the workflow has just installed everything, and a second
    environment would only cost the run's time.

    Breaks when the gate makes .venv under CI too."""
    repository, record = _gate_in_a_scratch_repository(tmp_path, {"CI": "true"})
    assert "-m venv" not in record
    assert "pip install" not in record
    assert not (repository / ".venv").exists()


def test_a_venv_whose_python_no_longer_runs_is_made_afresh(tmp_path):
    """Breaks when the gate keeps a .venv whose interpreter a system Python
    upgrade left dangling, and every tool then fails with an error naming
    neither cause."""
    def dangling(repository: Path) -> None:
        (repository / ".venv" / "bin").mkdir(parents=True)
        (repository / ".venv" / "bin" / "python").symlink_to(tmp_path / "python3.12-gone")

    repository, record = _gate_in_a_scratch_repository(tmp_path, {}, prepare=dangling)
    assert "-m venv .venv" in record
    assert "no longer runs" in record
    assert (repository / ".venv" / "bin" / "python").resolve().exists()


def test_release_runs_from_the_lock_alone(tmp_path):
    """--release installs what the release jobs install, the hash-checked lock
    and nothing else, and runs ruff and pytest from that environment
    (PRESS-0495).

    Breaks when a release is checked on the newest versions, which is how
    v1.2.1 passed the gate and failed its build."""
    repository, record = _gate_in_a_scratch_repository(tmp_path, {}, args=("--release",))
    assert "-m venv .venv-release" in record
    own = next(line for line in record.splitlines() if "pip install" in line)
    assert own.split()[0].endswith(".venv-release/bin/python")
    assert "--require-hashes -r packaging/release-requirements.txt" in own
    assert "-e" not in own.split()
    for tool in ("-m ruff check src/ tests/", "-m pytest -ra"):
        line = next(line for line in record.splitlines() if tool in line)
        assert line.split()[0].endswith(".venv-release/bin/python"), line
    assert not (repository / ".venv").exists()


def test_release_makes_its_environment_afresh(tmp_path):
    """A package an earlier lock installed would stay behind in a reused
    environment, which the release jobs' fresh runner never has.

    Breaks when --release reuses .venv-release."""
    def stale(repository: Path) -> None:
        (repository / ".venv-release" / "bin").mkdir(parents=True)
        (repository / ".venv-release" / "left-behind").write_text("", encoding="utf-8")

    repository, record = _gate_in_a_scratch_repository(tmp_path, {}, prepare=stale,
                                                       args=("--release",))
    assert "-m venv .venv-release" in record
    assert not (repository / ".venv-release" / "left-behind").exists()


def test_the_archive_keys_reach_the_suite(tmp_path):
    """Each machine-local key becomes the variable its tests read. A key naming
    no such file or folder says so and is not passed on, and an already-set
    variable wins.

    Breaks when one of the keys is dropped, or a missing folder is passed."""
    export = tmp_path / "export.xml"
    export.write_text("<rss/>", encoding="utf-8")
    keys = {"archive": str(export), "originals": str(tmp_path / "absent"),
            "siteName": "A Site", "siteAddress": "https://site.example.invalid"}
    _, record = _gate_in_a_scratch_repository(
        tmp_path, {"PRESSLESS_SITE_ADDRESS": "https://set.example.invalid"}, keys=keys)
    assert f"PRESSLESS_ARCHIVE={export}" in record
    assert "PRESSLESS_SITE_NAME=A Site" in record
    assert "PRESSLESS_SITE_ADDRESS=https://set.example.invalid" in record
    assert "PRESSLESS_ORIGINALS" not in record
    assert "ants.pressless.originals is set but" in record


def test_setup_hooks_turns_the_hooks_on_in_a_fresh_clone(tmp_path):
    """local-gate.md § 2: a clone inherits no core.hooksPath, so a script a
    clone runs sets it. Breaks when the script stops setting it, and a fresh
    clone pushes with no gate and no word said."""
    repository = tmp_path / "clone"
    (repository / "scripts").mkdir(parents=True)
    shutil.copy(_SCRIPT.parent / "setup-hooks.sh", repository / "scripts")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run([_GIT, "init", "-q"], cwd=repository, env=env, check=True)  # noqa: S603 -- a scratch repository
    ran = subprocess.run([_BASH, "scripts/setup-hooks.sh"], cwd=repository, env=env,  # noqa: S603
                         capture_output=True, text=True, timeout=60, check=False)
    assert ran.returncode == 0, ran.stderr
    hooks = subprocess.run([_GIT, "config", "--get", "core.hooksPath"], cwd=repository, env=env,  # noqa: S603
                           capture_output=True, text=True, check=True)
    assert hooks.stdout.strip() == ".githooks"


def test_the_committed_docs_glob_leaves_out_what_a_test_reads():
    """PRESS-0362: a test reads the manual's en.txt and the release build reads
    a .txt lock, so `*.txt` must not make a push documentation-only.
    test_sign_release reads CHANGELOG.md, so a push changing it runs the
    whole gate (PRESS-0457). The hook matches a path as bash's `==` does,
    where `*` crosses a `/`, as fnmatch's does."""
    conf = _SCRIPT.parent.parent / ".ants" / "gate.conf"
    glob = subprocess.run([_GIT, "config", "-f", str(conf), "--get", "ants.gate.docsGlob"],  # noqa: S603
                          capture_output=True, text=True, check=True).stdout.strip()
    patterns = glob.split("|")

    def documentation(path: str) -> bool:
        return any(fnmatchcase(path, pattern) for pattern in patterns)

    for path in ("README.md", "CLAUDE.md", "ROADMAP.md", "docs/design.md", "relay/README.md"):
        assert documentation(path), path
    for path in ("CHANGELOG.md", "src/pressless/manual_files/en.txt",
                 "packaging/release-requirements.txt"):
        assert not documentation(path), path
    assert not any(pattern in {"*", "*.*"} for pattern in patterns)
