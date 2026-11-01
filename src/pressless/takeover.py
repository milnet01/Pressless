"""Taking over a site GitHub Actions builds, in the same repository (PRESS-0333).

The contract is docs/specs/PRESS-0333-take-over-actions-site.md. Setup brings the
live site in and leaves a marker here; while it exists no publish goes through. The
first publish then asks, has the person remove the build file on GitHub, publishes,
and switches Pages (publishing.py owns that order). Pressless never writes a
workflow file, which would need a permission it does not ask for.
"""
from __future__ import annotations

import html
from pathlib import Path

from pressless import publisher, undo
from pressless.settings import Settings
from pressless.words import say

MARKER = "takeover-owed"   # in the site's folder: the build files' names, a line each
BUILD_MARK = "actions/deploy-pages"   # the action that makes an Actions deployment
_WORKFLOWS = ".github/workflows/"
_SUFFIXES = (".yml", ".yaml")


def owed(folder: Path) -> bool:
    return (Path(folder) / MARKER).is_file()


def mark(folder: Path, files: tuple[str, ...]) -> None:
    """An OSError is the caller's."""
    (Path(folder) / MARKER).write_text("".join(f"{name}\n" for name in files), encoding="utf-8")


def named(folder: Path) -> tuple[str, ...]:
    """The build files setup found, for the report once they have gone."""
    try:
        return tuple((Path(folder) / MARKER).read_text(encoding="utf-8").splitlines())
    except OSError:
        return ()


def done(folder: Path) -> None:
    """Absent is fine. An OSError is the caller's."""
    (Path(folder) / MARKER).unlink(missing_ok=True)


def build_files(folder: Path, settings: Settings, key: str,
                transport: publisher.Transport | None = None) -> tuple[str, ...]:
    """The workflow files at the branch's head that deploy to Pages, read through
    the fetch area, emptied before and after as a take-in's is."""
    fetch = Path(folder) / undo.FETCH_FOLDER
    undo.empty_fetch(fetch)
    try:
        fetched = publisher.fetch_state(settings, key, fetch, (_WORKFLOWS,),
                                        transport=transport)
        return tuple(sorted(
            path for path in fetched.paths
            if "/" not in path.removeprefix(_WORKFLOWS) and path.endswith(_SUFFIXES)
            and BUILD_MARK in (fetch / path).read_text(encoding="utf-8", errors="replace")))
    finally:
        try:
            undo.empty_fetch(fetch)
        except OSError:
            pass    # the next fetch empties the area again


def change_rows(files: tuple[str, ...], address: str, domain: str | None,
                stale_cname: bool) -> list[str]:
    """PRESS-0333 § 4.4: what the first publish changes, each row already escaped."""
    e = html.escape
    rows = [say("takeover.pages")]
    rows += [say("takeover.file", file=f"<code>{e(name)}</code>") for name in files]
    rows += [say("takeover.other_files"), say("takeover.address", address=e(address))]
    if domain:
        rows.append(say("takeover.domain", domain=e(domain)))
    rows.append(say("takeover.added"))
    if domain:
        rows.append(say("takeover.added_domain", domain=e(domain)))
    elif stale_cname:
        rows.append(say("takeover.stale"))
    return rows
