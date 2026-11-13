#!/bin/bash
# PRESS-0219 § 7's by-hand check on Linux: freeze Pressless with the release's
# pinned packages (no AppImage wrap), run it with the network cut, and drive
# its manual. Prints what frozen_check.py saw; a person reads it.
#
#   scripts/manual-media/frozen-check.sh
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
export PRESSLESS_MANUAL_WORK=${PRESSLESS_MANUAL_WORK:-$ROOT/scratch/manual-media}
W=$PRESSLESS_MANUAL_WORK
mkdir -p "$W"
cd "$ROOT"

[ -d "$W/venv" ] || python3 -m venv "$W/venv"
"$W/venv/bin/pip" install -q --require-hashes -r packaging/release-requirements.txt
rm -rf "$W/freeze" "$W/frozen-home" "$W/frozen-link.txt"
mapfile -t args < <("$W/venv/bin/python" scripts/freeze_flags.py args "$W/freeze")
PYTHONPATH=src "$W/venv/bin/python" -m PyInstaller --log-level WARN "${args[@]}"

# The program keeps its folder beside the file $APPIMAGE names, so naming one
# in a fresh folder gives it an empty install and leaves the real one alone.
mkdir -p "$W/frozen-home"
touch "$W/frozen-home/Pressless.AppImage"
export APPIMAGE="$W/frozen-home/Pressless.AppImage" BROWSER="$HERE/save-link.sh"
# A new network namespace has only its own loopback: nothing outside answers.
# shellcheck disable=SC2016  # the inner shell expands these, not this one
unshare -rn bash -c '
    ip link set lo up
    "$1/freeze/dist/Pressless/Pressless" > "$1/frozen.log" 2>&1 &
    trap "kill $!" EXIT
    python3 "$2/frozen_check.py"
' _ "$W" "$HERE"
