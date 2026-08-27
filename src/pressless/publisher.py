"""Publisher — making GitHub match the folder it was handed.

The contract is docs/specs/PRESS-0009-publisher.md. This module answers
three requests and nothing else: make the repository match a folder, what
sits at the repository root, and fetch back the state before the current
one.

It imports no other pressless module but pressless.settings (§5 INV-1): it
is handed a publishing key rather than fetching one (docs/design.md rule
10), and it never reaches Credentials, the Store, the Builder, Marks or the
Face.

STUB (PRESS-0009): this file declares the public surface only. Every
function body raises NotImplementedError. The real implementation is a
separate item and is not this one's.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pressless.settings import Settings


@dataclass(frozen=True)
class Outcome:
    """What a publish did (§4.1)."""

    commit: str                  # sha written; "" when nothing differed
    uploaded: tuple[str, ...]    # repository-relative paths written
    removed: tuple[str, ...]     # repository-relative paths deleted


@dataclass(frozen=True)
class Fetched:
    """What fetch_previous wrote out (§4.1)."""

    commit: str                  # the sha fetched from
    paths: tuple[str, ...]       # repository-relative paths written out


class PublishError(Exception):
    """Base for every failure this module raises (§4.1). None of them
    carries a sentence for the writer — docs/design.md § Errors gives that
    job to the Face alone."""


class Unreachable(PublishError):
    """No answer from GitHub, before the branch was touched."""


class OutcomeUnknown(PublishError):
    """The reference update was attempted and its result is unknown."""


class Refused(PublishError):
    """Key rejected, or no write access."""


class RepositoryMissing(PublishError):
    """settings.repository resolves to nothing."""


class Conflict(PublishError):
    """The branch moved under us."""


class TooLarge(PublishError):
    """A documented GitHub limit was hit."""


class RateLimited(PublishError):
    """GitHub asked us to slow down, and retrying did not clear it."""


class NoPreviousState(PublishError):
    """Nothing before the current commit."""


class Transport(Protocol):
    """The one seam. Tests are its only other caller (§4.1, §7).

    `request` returns the response headers and body for every HTTP status,
    error statuses included — this module owns the mapping to the types
    above. It signals *no answer at all* by raising OSError. `wait` is the
    pacing clock: this module never calls `sleep` itself, so a test can
    observe the spacing INV-9 asserts by recording calls to `wait` rather
    than by waiting real seconds.
    """

    def request(
        self, method: str, url: str, body: bytes | None, headers: dict[str, str]
    ) -> tuple[int, dict[str, str], bytes]: ...

    def wait(self, seconds: float) -> None: ...


def publish(
    settings: Settings,
    folder: Path,
    token: str,
    message: str,
    transport: Transport | None = None,
) -> Outcome:
    """Make the repository match `folder` (§4.2–§4.4)."""
    raise NotImplementedError


def root_entries(
    settings: Settings,
    token: str,
    transport: Transport | None = None,
) -> tuple[str, ...]:
    """Every entry at the repository root, bare names, no trailing slash
    (§4.4). Decides nothing and filters nothing."""
    raise NotImplementedError


def fetch_previous(
    settings: Settings,
    token: str,
    into: Path,
    prefix: str = "",
    transport: Transport | None = None,
) -> Fetched:
    """Write the state before the current commit into `into` (§4.5)."""
    raise NotImplementedError
