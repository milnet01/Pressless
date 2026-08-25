# ADR-0002: Publishing goes through the GitHub API, not through git

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

S4 requires that installing on Windows takes the same steps as on Linux
apart from which file is double-clicked, and the project exists to stop
the writer needing anyone technical. Publishing means putting a built
site into the repository his GitHub Pages site is served from.

The familiar way is to shell out to `git`. That requires git installed
and configured on his machine — a download, an installer, and a
credential setup, each a place he gets stuck and phones someone.

## Decision

The Publisher talks to GitHub's own web interface. It reads the current
state of the repository, works out which files actually differ, and
writes one commit containing only those.

## Consequences

- Nothing to install beyond Pressless itself. S4 is achievable.
- **Undo becomes cheap and real**, which is what makes S9 possible:
  GitHub already holds every previous version, so going back is another
  ordinary commit rather than a recovery procedure.
- The first publish writes the whole site — roughly 862 files — and is
  slow. Every publish after it writes a handful. Worth saying out loud
  so the first run is not mistaken for a fault.
- We depend on that interface staying as it is. If it changes, publishing
  breaks and the app cannot fall back to git without reintroducing the
  install.
- We do not get git's own safety checks. If Pressless computes the wrong
  set of changed files, nothing downstream catches it — so that
  computation needs tests that a git-based version would not have needed.
