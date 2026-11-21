#!/usr/bin/env bash
# The gate. GitHub runs this exact file; so does the pre-push hook.
#
# WHY ONE FILE. A hand-written local mirror of a workflow is correct the day
# it is written and drifts from then on, and a drifted mirror returns green
# for a pipeline that will fail (commits.md § 4.2). .github/workflows/ci.yml
# calls this script and holds no checks of its own.
#
# --docs runs the leak sweep ALONE. No test here reads a document, so a
# documentation-only push has no code check to run -- but this repository is
# public and must not name the writer, and a name leaks through prose more
# easily than through code. That sweep is never skipped.
#
# --sweep FILE... runs the same pattern over the files named, and nothing
# else. A review packet sits outside the tree, so no surface below reads it
# (PRESS-0277).
set -Eeuo pipefail

step() { printf '\n=== %s ===\n' "$1"; }
fail() {
    printf 'FAILED: %s\n' "$1" >&2
    exit 1
}

DOCS_ONLY=0
SWEEP=()
case ${1-} in
--docs) DOCS_ONLY=1 ;;
--sweep)
    shift
    (($#)) || fail "--sweep needs one or more files"
    for file in "$@"; do
        [[ -f $file && -r $file ]] || fail "--sweep cannot read $file"
        SWEEP+=("$(realpath "$file")")
    done
    ;;
"") ;;
*) fail "unknown option $1; use --docs, --sweep FILE..., or nothing" ;;
esac
cd "$(dirname "$0")/.."

# ── Leak sweep ──────────────────────────────────────────────────────────────
# Four surfaces, because a push publishes all four: the tree, the files in
# every commit, the commits themselves (message, author, committer and the
# paths they touch), and the refs, a tag's message and tagger among them.
# `git grep` reads file contents only, so a name in a subject line, an
# address or a file name passes it unseen.
#
# This script, and earlier CLAUDE.md in the history, spell these patterns, so
# those lines match. They carry the pipe-separated pattern itself; a real leak
# would not. Filtering on that needs no path list and no line numbers.
step "leak sweep"
PAT='charl|jordaan|18[^a-z0-9]?down|G-Y7N2F5SNY2|192\.168'
# Every surface searches PAT. SELF is not a second pattern: it is the
# literal fragment every line that merely QUOTES the pattern contains, which
# is what the self-exclusion below matches on. It stops short of the site's
# name, so it also matches the older spelling of the pattern that the history
# still holds (PRESS-0119).
SELF='charl|jordaan|18'
# Strings that identify the writer but cannot be spelled here without
# publishing them live in a machine-local config key, as the archive path
# below does (PRESS-0119). Every push from the maintainer's machine sweeps
# them; a checkout without the key says so rather than passing quietly.
extra=$(git config --get ants.pressless.leakPatterns || true)
if [[ -n $extra ]]; then
    PAT="$PAT|$extra"
else
    printf 'note: ants.pressless.leakPatterns is not set -- only the pattern above is swept\n'
fi
# The pattern reaches every search through a file, never a command line, which
# any process on this machine can read. Inside .git, as windows-gate.sh's
# scratch is: on the repository's own disk, never /tmp, which is RAM here.
patterns=$(mktemp "$(git rev-parse --path-format=absolute --git-common-dir)/leak-sweep.XXXXXX")
trap 'rm -f "$patterns"' EXIT
printf '%s\n' "$PAT" >"$patterns"
# grep exits 1 for no match and 2 for a pattern it cannot read. A malformed key
# would otherwise match nothing, everywhere, and pass.
status=0
grep -E -f "$patterns" </dev/null || status=$?
((status == 1)) || fail "the leak pattern does not compile; check ants.pressless.leakPatterns"

# Every surface arrives as `where<TAB>text` lines that already match. A line
# that only quotes the pattern is dropped, and the rest fail the gate. Only
# WHERE is printed: GitHub's log is public, and the text is the leak itself.
scan() {
    local what=$1 hits
    hits=$(grep -avF -- "$SELF" | cut -f1 || true)
    [[ -z $hits ]] || {
        printf '%s\n' "$hits" >&2
        fail "$what names the writer"
    }
    printf 'clean: %s\n' "$what"
}
matching() { grep -a -iE -f "$patterns" || (($? == 1)); }
# git grep's lines. --null keeps a `:` in a path from shifting the fields. A
# binary file's match carries no text, only `Binary file X matches`, and fails
# the gate all the same: a picture's metadata can hold a name.
from_git_grep() {
    tr '\0' '\t' | sed -e 's/\t/:/' -e 's/^Binary file \(.*\) matches$/\1\tbinary file/'
}
# Commits and refs carry no location on each line, so each line is tagged with
# the commit or ref above it. Git writes that header line after a \001 mark.
tagged() {
    awk -v mark="$(printf '\001')" \
        'index($0, mark) == 1 { where = substr($0, 2) } { print where "\t" $0 }'
}
if ((${#SWEEP[@]})); then
    for file in "${SWEEP[@]}"; do
        awk '{ print FILENAME ":" FNR "\t" $0 }' "$file" | matching | scan "$file"
    done
    exit 0
fi
{ git grep -n --null -iE -f "$patterns" -- . || (($? == 1)) || fail "git grep could not search the tree"; } \
    | from_git_grep | scan "tree"
git log --all --name-only --format='%x01%H%n%an <%ae>%n%cn <%ce>%n%B' \
    | tagged | matching | scan "commits: messages, authors and paths"
# An annotated tag carries a message and a tagger, which no commit log shows.
git for-each-ref --format='%01%(refname)%0a%(taggername) %(taggeremail)%0a%(contents)' \
    | tagged | matching | scan "refs and tag messages"
# In batches: one command line holding every revision passes Windows' limit
# (about 790 of them) as the history grows, and the release job runs this on
# windows-latest (PRESS-0135). git grep exits 1 for a batch with no match, which
# is not a failure; any other exit still fails the gate.
# shellcheck disable=SC2016  # $0 and $@ belong to the inner shell
git rev-list --all \
    | { xargs -n 200 sh -c 'git grep -n --null -iE -f "$0" "$@" -- . || [ $? -eq 1 ]' "$patterns" \
        || fail "git grep could not search the history"; } \
    | from_git_grep | scan "history"

if ((DOCS_ONLY)); then
    printf '\ndocumentation-only: no test here reads a document, so nothing else to run.\n'
    exit 0
fi

# ── The interpreter ── scripts/python.sh says why it is resolved, not named.
# shellcheck source=scripts/python.sh
. scripts/python.sh

# ── The same tools GitHub resolves ──────────────────────────────────────────
# ci.yml installs afresh on every run, so it always has today's versions. (The
# release jobs run this script on the hash-locked versions in
# packaging/release-requirements.txt instead.) Here the machine's own copies
# age, and a gate on older tools passes what GitHub then fails. So a local run
# keeps its own gitignored .venv, brought up to what a fresh install resolves.
# It never touches the machine's shared tools, which other projects use. GitHub
# sets CI and has just installed, so it skips this.
if [[ -z ${CI-} ]]; then
    step "gate environment"
    own_python() {
        if [[ -x .venv/Scripts/python.exe ]]; then
            echo .venv/Scripts/python.exe
        else
            echo .venv/bin/python
        fi
    }
    # A system Python upgrade can leave .venv's interpreter a dangling link,
    # and every tool would then fail with an error naming neither cause.
    if [[ -d .venv ]] && ! "$(own_python)" -c 'import sys' 2>/dev/null; then
        printf 'note: .venv'"'"'s Python no longer runs -- making .venv afresh\n'
        rm -rf .venv
    fi
    [[ -d .venv ]] || "$PY" -m venv .venv || fail "could not make .venv"
    PY=$(own_python)
    # Offline, the versions already there still run, and the note says so.
    "$PY" -m pip install --quiet --disable-pip-version-check \
        --upgrade --upgrade-strategy eager -e '.[dev]' \
        || printf 'WARNING: .venv could not be updated -- these may not be the versions GitHub runs\n' >&2
fi

# ── What is about to run ────────────────────────────────────────────────────
# REPORTED, never enforced. The dev floors in pyproject.toml are open on
# purpose and that file says why: a release that breaks the project should
# surface on the next CI run rather than months later. What the floors do not
# cover is the two ENVIRONMENTS resolving different versions -- this machine
# and the runner install independently, so sharing one gate script stops them
# running different CHECKS and does nothing about different VERSIONS.
#
# That is PRESS-0027's shape returning: there the two ran the suite
# differently, because pytest-randomly was auto-loading here and absent in
# CI, and nothing said so. Printing what resolved does not stop the drift. It
# puts the same line in a local run and in the CI log, so a mismatch is
# readable from either (PRESS-0105).
step "tool versions"
"$PY" -m ruff --version
"$PY" -m pytest --version
# A plugin has no --version of its own, and an ABSENT one is the case worth
# reporting: without it the suite runs in file order, which is the PRESS-0027
# failure exactly. Said in words rather than left to a missing line.
"$PY" - <<'PY'
from importlib.metadata import PackageNotFoundError, version
try:
    print(f"pytest-randomly {version('pytest-randomly')}")
except PackageNotFoundError:
    print("pytest-randomly NOT INSTALLED -- the suite is running in file order")
PY

step "ruff"
"$PY" -m ruff check src/ tests/ || fail "lint"

# The archive tests read the writer's own material, which is personal data and
# cannot live here -- so CI is permanently silent about them, S2 included: the
# project's most important invariant, proven against the real WordPress
# export. The one machine that CAN run them is the maintainer's, which is where
# the pre-push hook fires. A machine-local config key per input runs them
# automatically, and keeps it out of this public repository:
#
#   ants.pressless.archive      the WordPress export, a file (S2)
#   ants.pressless.originals    the photograph originals, a folder (PRESS-0007 § 7)
#   ants.pressless.liveSite     the live site's folder (PRESS-0007 § 7)
#   ants.pressless.templates    today's header and footer templates, a folder
#   ants.pressless.siteName     the name in every page title (PRESS-0008 § 7)
#   ants.pressless.siteAddress  the site's address (PRESS-0008 § 7)
#
# An already-set variable wins, so CI and a one-off run are unaffected. A key
# naming no such file or folder says so, and never prints the path.
while read -r variable key kind; do
    [[ -z ${!variable-} ]] || continue
    value=$(git config --get "ants.pressless.$key" || true)
    [[ -n $value ]] || continue
    if [[ $kind == file && ! -f $value || $kind == folder && ! -d $value ]]; then
        printf 'note: ants.pressless.%s is set but names no %s -- its tests do not run\n' "$key" "$kind"
        continue
    fi
    export "$variable=$value"
done <<'KEYS'
PRESSLESS_ARCHIVE archive file
PRESSLESS_ORIGINALS originals folder
PRESSLESS_LIVE_SITE liveSite folder
PRESSLESS_TEMPLATES templates folder
PRESSLESS_SITE_NAME siteName value
PRESSLESS_SITE_ADDRESS siteAddress value
KEYS

# The suite errors at COLLECTION if a module is missing, and an exit code alone
# does not distinguish that from a clean run. -ra prints the collected count.
step "pytest"
"$PY" -m pytest -ra || fail "tests"

# The log relay's own tests (PRESS-0436 INV-6), where node is on the path.
# CI's runners carry node; a machine without it says so and goes on.
if command -v node >/dev/null; then
    step "relay tests (node $(node --version))"
    node --test 'relay/test/*.test.js' || fail "relay tests"
else
    printf '\nnote: node is not on the path -- the relay tests did not run\n'
fi

# The same suite on real Windows, where a machine-local key names one
# (PRESS-0192). Windows CI found two faults the Linux run could not show, so a
# push from the maintainer's machine runs Windows too, before GitHub does:
#   git config ants.pressless.windowsHost <ssh-host>
# Unset on GitHub and on any other clone, which says so and goes on.
# The box is not always on, so an UNREACHABLE box (exit 2, which the gate
# keeps for that alone) is a loud warning and GitHub's Windows job remains
# the check; a failing suite still fails.
# The user ruled this on 2026-10-01.
windows=$(git config --get ants.pressless.windowsHost || true)
if [[ -n $windows ]]; then
    step "pytest on Windows ($windows)"
    status=0
    ./scripts/windows-gate.sh "$windows" || status=$?
    if ((status == 2)); then
        printf '\nWARNING: %s is not reachable -- the Windows tests DID NOT RUN.\n' "$windows" >&2
        printf 'Only GitHub'"'"'s Windows job will check this push.\n' >&2
    elif ((status != 0)); then
        fail "tests on Windows"
    fi
else
    printf '\nnote: ants.pressless.windowsHost is not set -- the suite ran on this system only\n'
fi

printf '\nall checks passed\n'
