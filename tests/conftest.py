# Suite-wide settings. Keep this file to what every test needs.
from __future__ import annotations

from pressless import face

# Stopping a Face waits for its loop's next check, half a second in the app.
# The suite stops hundreds of them, and waited about a minute on that alone.
face._POLL_SECONDS = 0.02
