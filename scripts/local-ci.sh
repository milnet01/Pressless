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
set -Eeuo pipefail
cd "$(dirname "$0")/.."

DOCS_ONLY=0
[[ ${1-} == --docs ]] && DOCS_ONLY=1

step() { printf '\n=== %s ===\n' "$1"; }
fail() {
    printf 'FAILED: %s\n' "$1" >&2
    exit 1
}

# ── Leak sweep ──────────────────────────────────────────────────────────────
# Four surfaces, because a push publishes all four: the tree, the files in
# every commit, the commit messages, and the refs, a tag's message among them.
# `git grep` reads trees only, so a name in a subject line passes it unseen.
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
# Each surface is fed in as text and matched here, so all are matched the same
# way -- and the message and ref surfaces have no matcher of their own.
scan() {
    local what=$1 hits
    hits=$(grep -inE "$PAT" | grep -vF "$SELF" || true)
    [[ -z $hits ]] || {
        printf '%s\n' "$hits" >&2
        fail "$what names the writer"
    }
    printf 'clean: %s\n' "$what"
}
git grep -n -iE "$PAT" -- . | scan "tree"
git log --all --format='%H %s%n%b' | scan "commit messages"
# An annotated tag carries a message of its own, which no commit log shows.
git for-each-ref --format='%(refname) %(contents)' | scan "refs and tag messages"
# shellcheck disable=SC2046  # the revision list must expand into arguments
git grep -n -iE "$PAT" $(git rev-list --all) -- . | scan "history"

if ((DOCS_ONLY)); then
    printf '\ndocumentation-only: no test here reads a document, so nothing else to run.\n'
    exit 0
fi

# ── The interpreter ─────────────────────────────────────────────────────────
# Resolved, never named. The release workflow runs this file on windows-latest
# too (PRESS-0022 § 7 step 1), where the installer ships python.exe and creates
# no python3 -- and a python3 that IS on PATH there can be a store alias that
# runs nothing. So each candidate must actually run. On Linux python3 wins, as
# it always did.
PY=
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys' 2>/dev/null; then
        PY=$candidate
        break
    fi
done
[[ -n $PY ]] || fail "no working python3 or python on PATH"

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
ruff --version
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
ruff check src/ tests/ || fail "lint"

# The archive test proves S2 against the real WordPress export, which is
# personal data and cannot live here -- so CI is permanently silent about the
# project's most important invariant. The one machine that CAN run it is the
# maintainer's, which is where the pre-push hook fires. Point a machine-local
# config key at the export and it runs automatically:
#
#   git config ants.pressless.archive /path/to/wordpress-export.xml
#
# The path stays out of this public repository. An already-set
# PRESSLESS_ARCHIVE wins, so CI and a one-off run are unaffected.
if [[ -z ${PRESSLESS_ARCHIVE-} ]]; then
    archive=$(git config --get ants.pressless.archive || true)
    if [[ -n $archive && -f $archive ]]; then
        export PRESSLESS_ARCHIVE="$archive"
    elif [[ -n $archive ]]; then
        printf 'note: ants.pressless.archive is set but %s is missing -- S2 not proven\n' "$archive"
    fi
fi
# Import's archive tests also read the photograph originals (PRESS-0007 §7),
# which are the writer's own files and stay out of this repository the same
# way: git config ants.pressless.originals /path/to/originals
if [[ -z ${PRESSLESS_ORIGINALS-} ]]; then
    originals=$(git config --get ants.pressless.originals || true)
    if [[ -n $originals && -d $originals ]]; then
        export PRESSLESS_ORIGINALS="$originals"
    elif [[ -n $originals ]]; then
        printf 'note: ants.pressless.originals is set but that folder is missing\n'
    fi
fi

# The suite errors at COLLECTION if a module is missing, and an exit code alone
# does not distinguish that from a clean run. -ra prints the collected count.
step "pytest"
"$PY" -m pytest -ra || fail "tests"

printf '\nall checks passed\n'
