#!/usr/bin/env bash
# The suite on real Windows, before a push (PRESS-0192).
#
#   scripts/windows-gate.sh <ssh-host>
#   scripts/windows-gate.sh <ssh-host> --browsers edge firefox
#
# With --browsers it runs scripts/by-hand-browser-checks.py instead of the
# suite, once per browser named: chrome, edge or firefox (PRESS-0292). They
# run in %USERPROFILE%\pressless-browsers\venv, made from the portable Python
# below and kept between runs with Playwright's Firefox, so the suite's own
# Python never gains Playwright. Edge and Chrome are the box's installed ones.
#
# local-ci.sh calls this where the machine-local key ants.pressless.windowsHost
# names a Windows machine. GitHub never does: its own Windows job is the same
# suite, and the key is unset there.
#
# WHY. Two faults reached Windows CI that Linux cannot show the same way: NUL
# reads as a terminal there, and a socket closed with unread bytes resets. The
# only check that behaves like Windows is Windows.
#
# The machine needs a portable Python unpacked at
# %USERPROFILE%\pressless-gate\python -- the NuGet `python` package's tools
# folder, never installed and never on PATH, so the packaged Pressless tested
# on the same machine cannot see it. docs/working-here.md says how.
#
# What is copied is what the Linux suite just ran on: HEAD as a git clone, so
# the tests that ask git have a checkout, with the working tree's tracked and
# not-ignored files laid over it. A tracked file deleted but not staged is the
# exception: the box keeps HEAD's copy. An ignored file, the Google secret among
# them, never leaves this machine.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

usage="usage: windows-gate.sh <ssh-host> [--browsers <browser>...]"
host=${1:?$usage}
shift
browsers=()
if (($#)); then
    [[ $1 == --browsers && $# -gt 1 ]] || { echo "$usage" >&2; exit 64; }
    shift
    for browser; do
        case $browser in
            chrome|edge|firefox) browsers+=("\"$browser\"") ;;
            *) echo "windows gate: no browser called $browser" >&2; exit 64 ;;
        esac
    done
fi
# Inside .git: on the repository's own disk, never /tmp, which is RAM here.
scratch=$(mktemp -d "$(git rev-parse --path-format=absolute --git-common-dir)/windows-gate.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
run="run-$(date +%s)-$$"

# The same dependency list CI installs: the project's own and the dev extra,
# upgraded on each run, because a fresh CI install resolves today's versions.
deps=$(python3 - <<'PY'
import tomllib
project = tomllib.load(open("pyproject.toml", "rb"))["project"]
print(" ".join(f'"{d}"' for d in project["dependencies"] + project["optional-dependencies"]["dev"]))
PY
)

if ((${#browsers[@]} == 0)); then
    body=$(cat <<EOF
    & \$python -m pip install --quiet --disable-pip-version-check --upgrade --upgrade-strategy eager $deps
    if (\$LASTEXITCODE -ne 0) { throw "pip could not install the dependencies" }
    & \$python -m pytest --version
    & \$python -m pytest -ra -q -p no:cacheprovider
    \$code = \$LASTEXITCODE
EOF
)
else
    # The same Playwright as this machine's, where it has one.
    playwright=$(python3 -c 'import importlib.metadata as m; print("==" + m.version("playwright"))' \
        2>/dev/null || true)
    list=$(IFS=,; echo "${browsers[*]}")
    body=$(cat <<EOF
    \$root = "\$env:USERPROFILE\\pressless-browsers"
    \$venv = "\$root\\venv\\Scripts\\python.exe"
    if (-not (Test-Path \$venv)) { & \$python -m venv "\$root\\venv" }
    if (-not (Test-Path \$venv)) { throw "no Playwright environment at \$venv" }
    & \$venv -m pip install --quiet --disable-pip-version-check $deps "playwright$playwright"
    if (\$LASTEXITCODE -ne 0) { throw "pip could not install the dependencies" }
    \$code = 0
    foreach (\$browser in @($list)) {
        if (\$browser -eq "firefox") { & \$venv -m playwright install firefox | Out-Null }
        & \$venv scripts\\by-hand-browser-checks.py --browser \$browser
        if (\$LASTEXITCODE -ne 0) { \$code = 1 }
    }
EOF
)
fi

# ls-files also lists a tracked file deleted but not yet staged. It is not on
# disk to send, so it is left out, and the box keeps HEAD's copy of it.
git ls-files -co --exclude-standard -z | python3 -c '
import os, sys, zipfile
names = [n for n in sys.stdin.buffer.read().decode().split("\0") if n]
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as out:
    for name in names:
        if os.path.lexists(name):
            out.write(name)
' "$scratch/$run.zip"

cat > "$scratch/$run.ps1" <<EOF
\$ErrorActionPreference = "Stop"
\$gate = "\$env:USERPROFILE\\pressless-gate"
\$python = "\$gate\\python\\python.exe"
\$work = "\$gate\\$run"
\$code = 1
try {
    if (-not (Test-Path \$python)) { throw "no portable Python at \$python" }
    git clone --quiet "\$env:USERPROFILE\\$run.bundle" \$work
    if (\$LASTEXITCODE -ne 0) { throw "git could not clone the bundle" }
    Expand-Archive -Force "\$env:USERPROFILE\\$run.zip" \$work
    Set-Location \$work
$body
} catch {
    Write-Output "windows gate: \$_"
} finally {
    Set-Location \$env:USERPROFILE
    Remove-Item -Recurse -Force \$work -ErrorAction SilentlyContinue
    Remove-Item -Force "\$env:USERPROFILE\\$run.zip", "\$env:USERPROFILE\\$run.bundle", "\$env:USERPROFILE\\$run.ps1" -ErrorAction SilentlyContinue
}
exit \$code
EOF

git bundle create -q "$scratch/$run.bundle" HEAD
# Exit 2 means the box could not be reached, which local-ci.sh reports and
# passes; any other non-zero is the suite's failure. ssh's own failure is 255,
# and the remote's own 2 -- pytest's, for an interrupted run or a collection
# error -- becomes 1, so only unreachable() ever exits 2.
unreachable() { printf 'windows gate: %s is not reachable\n' "$host" >&2; exit 2; }
scp -q -o ConnectTimeout=8 "$scratch/$run.zip" "$scratch/$run.bundle" "$scratch/$run.ps1" "$host:" \
    || unreachable
status=0
ssh -o ConnectTimeout=8 "$host" "powershell -NoProfile -ExecutionPolicy Bypass -File $run.ps1" \
    || status=$?
((status != 255)) || unreachable
((status != 2)) || status=1
exit "$status"
