#!/usr/bin/env bash
# Build the Windows artefact -- PRESS-0022 § 4.1 and § 4.4: the frozen program
# folder and a batch file that starts it, zipped. Runs under bash on
# windows-latest. Prints the artefact's path as its last line.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

# shellcheck source=scripts/python.sh
. scripts/python.sh

# release.yml's Windows INV-6 step runs the program at
# $work/dist/Pressless/Pressless.exe: change both together.
work=build/freeze
stage=build/zip
rm -rf "$work" "$stage"

# Python on Windows prints CRLF; the carriage returns would become part of
# each argument. Assigned first, so set -e sees freeze_flags.py fail, as
# build-linux.sh says.
flags=$("$PY" scripts/freeze_flags.py args "$work" | tr -d '\r')
mapfile -t args <<<"$flags"
"$PY" -m PyInstaller "${args[@]}" >&2
version=$("$PY" scripts/freeze_flags.py version | tr -d '\r')

mkdir -p "$stage" dist
cp -a "$work/dist/Pressless" "$stage/Pressless"
# The batch file stays (scope decision 6): the program prints a report and
# finishes, so a double-clicked .exe would close its console before he could
# read it. Written here with CRLF, which cmd.exe expects.
# One line, ending the batch itself: cmd.exe reads a running batch file again
# from its old offset, so the console an update leaves paused would run
# whatever a changed file holds past it (measured on the Windows box). Never
# longer than the three-line form before it, so that console reads nothing.
printf '@"%%~dp0Pressless\\Pressless.exe" %%*&pause&exit /b\r\n' \
    > "$stage/Start Pressless.bat"

out="dist/Pressless-$version-windows.zip"
"$PY" - "$stage" "$out" <<'ZIP'
import shutil, sys
shutil.make_archive(sys.argv[2].removesuffix(".zip"), "zip", root_dir=sys.argv[1])
ZIP
printf '%s\n' "$out"
