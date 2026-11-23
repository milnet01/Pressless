#!/usr/bin/env bash
# Build the Linux artefact -- PRESS-0022 § 4.1 and § 4.4.
#
# Freezes one folder, wraps it in an AppDir, and hands that to appimagetool.
# Prints the artefact's path as its last line, for the release job to read.
# APPIMAGETOOL names the tool; unset, appimagetool on PATH.
#
# APPIMAGE_RUNTIME names the AppImage runtime file, and is required.
# appimagetool otherwise downloads the runtime itself from a release tagged
# `continuous`, which moves -- so the same commit could ship a different
# runtime on each build, and here the download hung outright. The release job
# downloads a pinned runtime and checks its hash before calling this.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

[[ -n ${APPIMAGE_RUNTIME-} && -f $APPIMAGE_RUNTIME ]] || {
    echo "APPIMAGE_RUNTIME must name the AppImage runtime file" >&2
    exit 1
}

# shellcheck source=scripts/python.sh
. scripts/python.sh

work=build/freeze
appdir=build/AppDir
rm -rf "$work" "$appdir"

# Assigned first, so set -e sees freeze_flags.py fail: a process
# substitution's exit status is lost, and PyInstaller would freeze from a
# list cut short.
flags=$("$PY" scripts/freeze_flags.py args "$work")
mapfile -t args <<<"$flags"
"$PY" -m PyInstaller "${args[@]}" >&2
version=$("$PY" scripts/freeze_flags.py version)

mkdir -p "$appdir/usr/bin" dist
cp -a "$work/dist/Pressless" "$appdir/usr/bin/Pressless"
install -m 755 packaging/linux/AppRun "$appdir/AppRun"
cp packaging/linux/pressless.desktop "$appdir/pressless.desktop"
# Its menu text in every other language Pressless speaks: the words setup's
# own shortcut uses (PRESS-0241).
PYTHONPATH=src PYTHONIOENCODING=utf-8 "$PY" - >>"$appdir/pressless.desktop" <<'PY'
from pressless import words
for code in words.LANGUAGES:
    if code != "en":
        print(f"Comment[{code}]={words.say_in(code, 'shortcuts.comment')}")
PY

# The icon the AppImage shows, and the one Pressless copies out for its menu
# entry (PRESS-0183). Rendered from packaging/icons/pressless-icon.svg.
cp packaging/icons/pressless.png "$appdir/pressless.png"

out="dist/Pressless-$version-x86_64.AppImage"
ARCH=x86_64 "${APPIMAGETOOL:-appimagetool}" --runtime-file "$APPIMAGE_RUNTIME" \
    "$appdir" "$out" >&2
printf '%s\n' "$out"
