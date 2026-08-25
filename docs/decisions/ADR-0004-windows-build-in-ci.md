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
- The Windows build is the one nobody here can test by running it. Its
  first real exercise is him double-clicking it, which is the worst
  place to find a problem — so the Windows job must run the test suite,
  not just produce a file.
- A CI outage blocks releasing to him entirely, with no local route
  around it.
- It is a dependency on GitHub for building as well as for hosting and
  publishing. Concentrated, and worth knowing.
