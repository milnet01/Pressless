# Suite-wide settings. Keep this file to what every test needs.
from __future__ import annotations

import pytest

from pressless import face, github_signin, pressing, usage

# Stopping a Face waits for its loop's next check, half a second in the app.
# The suite stops hundreds of them, and waited about a minute on that alone.
face._POLL_SECONDS = 0.02


@pytest.fixture(autouse=True)
def _no_registered_app(monkeypatch):
    """Every test runs as a copy without the GitHub App, so setup asks for a
    key, unless it registers one itself (PRESS-0231). The shipped constants
    would otherwise send a key-path test to the sign-in, and to GitHub."""
    monkeypatch.setattr(github_signin, "CLIENT_ID", "")
    monkeypatch.setattr(github_signin, "APP_SLUG", "")


@pytest.fixture(autouse=True)
def _no_press_on_record(monkeypatch):
    """Every test starts with no press running or remembered (PRESS-0235). The
    record lives as long as the process, so one test's publish would otherwise
    change the words on a later test's page."""
    monkeypatch.setattr(pressing, "_running", None)
    monkeypatch.setattr(pressing, "_outcome", None)


@pytest.fixture(autouse=True)
def _no_usage_reports(monkeypatch):
    """Every test runs as a copy without the usage-report key, with nothing
    registered to send, unless it says otherwise (PRESS-0262). A key written
    into this checkout would otherwise add a setup step to every wizard test,
    and one test's registration would send another test's events."""
    monkeypatch.setattr(usage, "MEASUREMENT_ID", "")
    monkeypatch.setattr(usage, "API_SECRET", "")
    monkeypatch.setattr(usage, "_folder", None)
    monkeypatch.setattr(usage, "_transport", None)
