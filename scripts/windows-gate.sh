#!/usr/bin/env bash
# The suite on real Windows, before a push (PRESS-0192).
#
#   scripts/windows-gate.sh <ssh-host>
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
# not-ignored files laid over it. An ignored file, the Google secret among
# them, never leaves this machine.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

host=${1:?usage: windows-gate.sh <ssh-host>}
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

git ls-files -co --exclude-standard -z | python3 -c '
import sys, zipfile
names = [n for n in sys.stdin.buffer.read().decode().split("\0") if n]
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as out:
    for name in names:
        out.write(name)
' "$scratch/tree.zip"

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
    & \$python -m pip install --quiet --disable-pip-version-check $deps
    if (\$LASTEXITCODE -ne 0) { throw "pip could not install the dependencies" }
    & \$python -m pytest --version
    & \$python -m pytest -ra -q -p no:cacheprovider
    \$code = \$LASTEXITCODE
} catch {
    Write-Output "windows gate: \$_"
} finally {
    Set-Location \$env:USERPROFILE
    Remove-Item -Recurse -Force \$work -ErrorAction SilentlyContinue
    Remove-Item -Force "\$env:USERPROFILE\\$run.zip", "\$env:USERPROFILE\\$run.bundle", "\$env:USERPROFILE\\$run.ps1" -ErrorAction SilentlyContinue
}
exit \$code
EOF

cp "$scratch/tree.zip" "$scratch/$run.zip"
git bundle create -q "$scratch/$run.bundle" HEAD
scp -q -o ConnectTimeout=15 "$scratch/$run.zip" "$scratch/$run.bundle" "$scratch/$run.ps1" "$host:" \
    || { printf 'windows gate: %s is not reachable\n' "$host" >&2; exit 2; }
ssh -o ConnectTimeout=15 "$host" "powershell -NoProfile -ExecutionPolicy Bypass -File $run.ps1"
