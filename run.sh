#!/usr/bin/env bash
# Start a practice copy of Pressless from this source tree (PRESS-0202): made-up
# writing, and no way to publish or reach Google. The local web-server manager
# sets PORT and stops it with SIGTERM.
PORT=${PORT:-8471}
export PORT
cd "$(dirname "$0")" || exit 1
exec python3 scripts/practice.py
