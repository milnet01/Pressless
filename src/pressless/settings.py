"""Settings — what is true of this machine and this site, and nothing else.

STUB. This declares the public surface docs/specs/PRESS-0001-settings.md §4.1
documents and implements none of it, so tests/test_settings.py is COLLECTED and
its behavioural tests fail on the behaviour rather than on an import error.
That is §7's red run. The implementation replaces this file.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Credentials:
    store: str                   # "keyring" or "file" -- ADR-0003's two paths
    github_account: str          # the keyring account name, or the file's key name
    google_account: str | None   # None where the dashboard was declined


@dataclass(frozen=True)
class Settings:
    site_folder: Path            # where the Builder writes the finished site
    repository: str              # "owner/name" on GitHub
    daily_prompt_filter: str     # fnmatch glob, matched per tag
    untouchable: tuple[str, ...] # repository-root entries the Publisher leaves alone
    credentials: Credentials     # where the two secrets are kept -- never the secrets
    analytics_measurement_id: str | None


class NotSetUp(Exception):
    """No settings file yet -- run setup."""


class SettingsError(Exception):
    """A settings file we will not act on."""


def load(folder: Path) -> Settings:
    raise NotImplementedError


def save(folder: Path, settings: Settings) -> None:
    raise NotImplementedError


def path_for(folder: Path) -> Path:
    raise NotImplementedError
