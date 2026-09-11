"""python -m pressless_import EXPORT ORIGINALS INTO (PRESS-0007 §4.1)."""
import sys

from . import main

raise SystemExit(main(sys.argv[1:]))
