# ADR-0004: The Windows executable is built in CI, because it cannot be built here

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Development happens on Linux; the writer is on Windows. The stack packages
Pressless into one double-clickable file per system, and PyInstaller
cannot cross-compile — a Windows executable must be produced by Windows.

## Decision

Releases are built by GitHub Actions: the Linux file on a Linux runner,
`Pressless.exe` on a Windows runner, both attached to the release. The
repository is public, so the minutes cost nothing.

## Consequences

- **Releases go through CI from the very first one.** This is not
  something to add later; without it there is no Windows build at all,
  and S4 cannot even be demonstrated.
- **The Windows build can be exercised before he ever sees it.** A
  Windows test box is reachable over SSH from the development machine,
  so the built executable can be staged and run there. That does not
  weaken the rule above — the Windows job must still run the test suite
  rather than only producing a file — but his double-click is no longer
  the first real exercise, which was the worst possible place to find a
  problem. **The box has no Python installed, deliberately**: that is
  what makes it evidence for S4 rather than a friendly environment, and
  installing one would remove the only proof the executable carries
  everything it needs.
- A CI outage blocks releasing to him entirely, with no local route
  around it.
- It is a dependency on GitHub for building as well as for hosting and
  publishing. Concentrated, and worth knowing.
