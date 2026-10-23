# shellcheck shell=bash
# Sourced, never run: sets PY to a Python that works, or exits.
# Used by local-ci.sh, build-linux.sh and build-windows.sh.
#
# Resolved, never named. Windows runs these scripts too (PRESS-0022 § 7
# step 1). Its installer ships python.exe and creates no python3, and a
# python3 that IS on PATH there can be a store alias that runs nothing. So
# each candidate must actually run. On Linux python3 wins.
PY=
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys' 2>/dev/null; then
        PY=$candidate
        break
    fi
done
[[ -n $PY ]] || { echo "no working python3 or python on PATH" >&2; exit 1; }
