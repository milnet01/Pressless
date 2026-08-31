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
fail() { printf 'FAILED: %s\n' "$1" >&2; exit 1; }

# ── Leak sweep ──────────────────────────────────────────────────────────────
# Three surfaces, because a push publishes all three: the tree, the files in
# every commit, and the commit messages. `git grep` reads trees only, so a name
# in a subject line passes it without a hit.
#
# CLAUDE.md documents these patterns, so its own lines match. Those lines carry
# the pipe-separated pattern itself; a real leak would not. Filtering on that
# needs no path list and no line numbers, so it cannot go stale.
step "leak sweep"
PAT='charl|jordaan|18down|G-Y7N2F5SNY2|192\.168'
# All three surfaces search PAT. SELF is not a second pattern: it is the
# literal fragment every line that merely QUOTES the pattern contains, which
# is what the self-exclusion below matches on.
SELF='charl|jordaan|18down'
# Each surface is fed in as text and matched here, so all three are matched the
# same way -- and the commit-message surface has no matcher of its own.
scan() {
    local what=$1 hits
    hits=$(grep -inE "$PAT" | grep -vF "$SELF" || true)
    [[ -z $hits ]] || { printf '%s\n' "$hits" >&2; fail "$what names the writer"; }
    printf 'clean: %s\n' "$what"
}
git grep -n -iE "$PAT" -- . | scan "tree"
git log --all --format='%H %s%n%b'  | scan "commit messages"
# shellcheck disable=SC2046  # the revision list must expand into arguments
git grep -n -iE "$PAT" $(git rev-list --all) -- . | scan "history"

if (( DOCS_ONLY )); then
    printf '\ndocumentation-only: no test here reads a document, so nothing else to run.\n'
    exit 0
fi

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

# The suite errors at COLLECTION if a module is missing, and an exit code alone
# does not distinguish that from a clean run. -ra prints the collected count.
step "pytest"
python3 -m pytest -ra || fail "tests"

printf '\nall checks passed\n'
