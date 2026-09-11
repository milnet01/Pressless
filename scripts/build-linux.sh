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

PY=
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys' 2>/dev/null; then
        PY=$candidate
        break
    fi
done
[[ -n $PY ]] || { echo "no working python3 or python on PATH" >&2; exit 1; }

work=build/freeze
appdir=build/AppDir
rm -rf "$work" "$appdir"

mapfile -t args < <("$PY" scripts/freeze_flags.py args "$work")
"$PY" -m PyInstaller "${args[@]}" >&2
version=$("$PY" scripts/freeze_flags.py version)

mkdir -p "$appdir/usr/bin" dist
cp -a "$work/dist/Pressless" "$appdir/usr/bin/Pressless"
install -m 755 packaging/linux/AppRun "$appdir/AppRun"
cp packaging/linux/pressless.desktop "$appdir/pressless.desktop"

# A placeholder icon, generated rather than committed: an AppImage requires one,
# and there is no artwork yet. A flat 256-pixel square, stdlib only.
"$PY" - "$appdir/pressless.png" <<'PNG'
import struct, sys, zlib
side = 256
rows = b"".join(b"\x00" + bytes((40, 90, 160)) * side for _ in range(side))
def chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
header = struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0)
with open(sys.argv[1], "wb") as out:
    out.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
              + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
PNG

out="dist/Pressless-$version-x86_64.AppImage"
ARCH=x86_64 "${APPIMAGETOOL:-appimagetool}" --runtime-file "$APPIMAGE_RUNTIME" \
    "$appdir" "$out" >&2
printf '%s\n' "$out"
