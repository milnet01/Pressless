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
# What is copied is what the Linux suite just ran on: HEAD's history as a git
# clone, so the tests that ask git have a repository, and the working tree's
# tracked and not-ignored files as the only files. The clone checks nothing
# out, so a file deleted here, staged or not, or the old name of a move, is
# absent there too. An ignored file, the Google secret among them, never
# leaves this machine.
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

# The same dependency list CI installs: the project's own and the dev extra.
deps=$(python3 - <<'PY'
import tomllib
project = tomllib.load(open("pyproject.toml", "rb"))["project"]
print(" ".join(f'"{d}"' for d in project["dependencies"] + project["optional-dependencies"]["dev"]))
PY
)

# $body is pasted into the PowerShell script below, inside its try block. It
# runs in the clone, may use $python, the portable Python, and must set $code:
# 0 for a pass, anything else for a failure. \$ is PowerShell's; a bare $ is
# expanded here.
#
# The suite's dependencies are upgraded on each run, because a fresh CI
# install resolves today's versions. The browser checks are not CI's mirror,
# and keep what their kept venv already holds. The suite runs as local-ci.sh
# runs it (-ra), with -q for a shorter log and no cache, since the clone is
# deleted afterwards.
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
# disk to send, so it is left out, and so it is absent on the box too.
git ls-files -co --exclude-standard -z | python3 -c '
import os, sys, zipfile
names = [n for n in sys.stdin.buffer.read().decode().split("\0") if n]
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as out:
    for name in names:
        if os.path.lexists(name):
            out.write(name)
' "$scratch/$run.zip"

# PRESS-0475: a run cut short, by a dropped connection say, never reaches its
# own finally below. So each run first clears what such runs left a day or
# more ago: only names $run takes, in the two folders a run writes to. A
# failure here only says so; it never fails the gate.
sweep=$(cat <<'EOF'
try {
    $stale = (Get-Date).AddDays(-1)
    Get-ChildItem -LiteralPath $gate -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^run-\d+-\d+$' -and $_.LastWriteTime -lt $stale } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $userHome -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^run-\d+-\d+\.(zip|bundle|ps1)$' -and $_.LastWriteTime -lt $stale } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
} catch {
    Write-Output "windows gate: old runs were not cleared: $_"
}
EOF
)

cat > "$scratch/$run.ps1" <<EOF
\$ErrorActionPreference = "Stop"
\$userHome = \$env:USERPROFILE
\$gate = "\$userHome\\pressless-gate"
\$python = "\$gate\\python\\python.exe"
\$work = "\$gate\\$run"
\$code = 1
$sweep
try {
    if (-not (Test-Path \$python)) { throw "no portable Python at \$python" }
    git clone --quiet --no-checkout "\$env:USERPROFILE\\$run.bundle" \$work
    if (\$LASTEXITCODE -ne 0) { throw "git could not clone the bundle" }
    # The index from HEAD, and no file but the zip's.
    git -C \$work reset --quiet
    if (\$LASTEXITCODE -ne 0) { throw "git could not read the bundle's HEAD" }
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
# passes; any other non-zero is a failure. The remote's own 2 -- pytest's, for
# an interrupted run or a collection error -- becomes 1, so only the probe
# below ever exits 2.
#
# ssh exits 255 for an unreachable box, but also for a changed host key, a
# refused key, or a connection lost mid-run, and those must fail the gate. So
# a probe asks first, and only a connection that never formed is unreachable.
# Once it has answered, any failure is the gate's. A timeout counts only in
# connect's own message: "timed out during banner exchange" means the box
# connected and then said nothing.
probe=0
said=$(ssh -o ConnectTimeout=8 "$host" exit 2>&1) || probe=$?
if ((probe != 0)); then
    case $said in
        *"Could not resolve hostname"* | *"No route to host"* | *"connect to host "*": Connection timed out"* \
            | *"Connection refused"* | *"Network is unreachable"*)
            printf 'windows gate: %s is not reachable\n' "$host" >&2
            exit 2 ;;
    esac
    printf 'windows gate: ssh to %s failed: %s\n' "$host" "$said" >&2
    exit 1
fi
scp -q -o ConnectTimeout=8 "$scratch/$run.zip" "$scratch/$run.bundle" "$scratch/$run.ps1" "$host:" \
    || { printf 'windows gate: could not copy the run to %s\n' "$host" >&2; exit 1; }
status=0
ssh -o ConnectTimeout=8 "$host" "powershell -NoProfile -ExecutionPolicy Bypass -File $run.ps1" \
    || status=$?
((status != 2)) || status=1
exit "$status"
