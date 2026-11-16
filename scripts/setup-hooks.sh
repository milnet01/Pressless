#!/usr/bin/env bash
# Run once in every clone: ./scripts/setup-hooks.sh
#
# git keeps core.hooksPath in .git/config, which no clone inherits. Without
# it no hook in .githooks/ runs, and nothing says so (local-gate.md § 2).
# The gate's own keys travel committed, in .ants/gate.conf. The keys that
# point at the writer's own material stay machine-local, set by hand:
# docs/working-here.md names them.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

git config core.hooksPath .githooks
printf 'hooks on: core.hooksPath is .githooks\n'
