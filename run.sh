#!/usr/bin/env bash
# Start Pressless for the local web-server manager, which sets PORT and stops
# it with SIGTERM. Where this clone's ants.pressless.runProgram key names a
# released program, that runs, on PORT passed on as PRESSLESS_PORT
# (PRESS-0431). Otherwise the practice copy from this source tree
# (PRESS-0202): made-up writing, and no way to publish or reach Google.
PORT=${PORT:-8471}
export PORT
cd "$(dirname "$0")" || exit 1
program=$(git config --get ants.pressless.runProgram)
if [ -n "$program" ]; then
    if [ ! -x "$program" ]; then
        echo "ants.pressless.runProgram names $program, which is not a program." >&2
        exit 1
    fi
    PRESSLESS_PORT=$PORT exec "$program"
fi
exec python3 scripts/practice.py
