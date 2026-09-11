#!/usr/bin/env bash
# Build the Windows artefact -- PRESS-0022 § 4.1 and § 4.4: the frozen program
# folder and a batch file that starts it, zipped. Runs under bash on
# windows-latest. Prints the artefact's path as its last line.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

PY=
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys' 2>/dev/null; then
        PY=$candidate
        break
    fi
done
[[ -n $PY ]] || { echo "no working python3 or python on PATH" >&2; exit 1; }

work=build/freeze
stage=build/zip
rm -rf "$work" "$stage"

# Python on Windows prints CRLF; the carriage returns would become part of
# each argument.
mapfile -t args < <("$PY" scripts/freeze_flags.py args "$work" | tr -d '\r')
"$PY" -m PyInstaller "${args[@]}" >&2
version=$("$PY" scripts/freeze_flags.py version | tr -d '\r')

mkdir -p "$stage" dist
cp -a "$work/dist/Pressless" "$stage/Pressless"
# The batch file stays (scope decision 6): the program prints a report and
# finishes, so a double-clicked .exe would close its console before he could
# read it. Written here with CRLF, which cmd.exe expects.
printf '@echo off\r\n"%%~dp0Pressless\\Pressless.exe" %%*\r\npause\r\n' \
    > "$stage/Start Pressless.bat"

out="dist/Pressless-$version-windows.zip"
"$PY" - "$stage" "$out" <<'ZIP'
import shutil, sys
shutil.make_archive(sys.argv[2].removesuffix(".zip"), "zip", root_dir=sys.argv[1])
ZIP
printf '%s\n' "$out"
