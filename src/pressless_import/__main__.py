"""python -m pressless_import EXPORT ORIGINALS LIVE_SITE TEMPLATES INTO (PRESS-0007 §4.1)."""
import sys

from . import main

raise SystemExit(main(sys.argv[1:]))
