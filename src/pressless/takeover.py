"""Taking over a site GitHub Actions builds, in the same repository (PRESS-0333), or
one a workflow pushes to a branch (PRESS-0336).

The contract is docs/specs/PRESS-0333-take-over-actions-site.md. Setup brings the
live site in and leaves a marker here; while it exists no publish goes through. The
first publish then asks, has the person remove the build file on GitHub, publishes,
and switches Pages (publishing.py owns that order). Pressless never writes a
workflow file, which would need a permission it does not ask for.
"""
from __future__ import annotations

import html
import re
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


def build_files(folder: Path, settings: Settings, key: str, shown: publisher.Pages,
                transport: publisher.Transport | None = None) -> tuple[str, ...]:
    """The workflow files at the default branch's head that make the site `shown`
    serves, read through the fetch area, emptied before and after as a take-in's is.
    Empty where Pages is not built elsewhere: there is nothing to take over."""
    if not shown.built_elsewhere:
        return ()
    fetch = Path(folder) / undo.FETCH_FOLDER
    undo.empty_fetch(fetch)
    try:
        fetched = publisher.fetch_state(settings, key, fetch, (_WORKFLOWS,),
                                        transport=transport)
        return tuple(sorted(
            path for path in fetched.paths
            if "/" not in path.removeprefix(_WORKFLOWS) and path.endswith(_SUFFIXES)
            and _builds(shown, (fetch / path).read_text(encoding="utf-8", errors="replace"))))
    finally:
        try:
            undo.empty_fetch(fetch)
        except OSError:
            pass    # the next fetch empties the area again


# PRESS-0336: the two common actions that push a built site to a branch, each
# defaulting to gh-pages, so a file using one need not name the branch at all.
_BRANCH_ACTIONS = ("peaceiris/actions-gh-pages", "jamesives/github-pages-deploy-action")
_THEIR_BRANCH = "gh-pages"


def _builds(shown: publisher.Pages, text: str) -> bool:
    """An Actions build: the file names `BUILD_MARK`. A branch build (PRESS-0336): it
    names the branch as a word of its own, so `site` is not found in `website`, or
    it uses an action whose default is that branch."""
    if shown.built_by_actions:
        return BUILD_MARK in text
    branch = shown.branch or ""
    if re.search(rf"(?<![\w.-]){re.escape(branch)}(?![\w.-])", text):
        return True
    return branch == _THEIR_BRANCH and any(name in text.casefold() for name in _BRANCH_ACTIONS)


def change_rows(files: tuple[str, ...], address: str, shown: publisher.Pages,
                stale_cname: bool) -> list[str]:
    """PRESS-0333 § 4.4: what the first publish changes, each row already escaped."""
    e = html.escape
    domain = shown.domain
    rows = [say("takeover.pages")]
    rows += [say("takeover.file", file=f"<code>{e(name)}</code>") for name in files]
    rows += [say("takeover.other_files"), say("takeover.address", address=e(address))]
    if shown.branch:
        rows.append(say("takeover.branch", branch=f"<code>{e(shown.branch)}</code>"))
    if domain:
        rows.append(say("takeover.domain", domain=e(domain)))
    rows.append(say("takeover.added"))
    if domain:
        rows.append(say("takeover.added_domain", domain=e(domain)))
    elif stale_cname:
        rows.append(say("takeover.stale"))
    return rows
