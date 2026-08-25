# ADR-0003: The publishing key lives in the operating system's keyring

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

S5: he is asked for his publishing key exactly once, during setup, and
never sees it again. The key can write to his live site, so anything
that leaks it lets someone else change it.

Pressless is public and will be read by strangers, which rules out
anything that could put the key near the repository.

## Decision

The key goes in the operating system's own credential store — Credential
Manager on Windows, Secret Service on Linux — through one library that
covers both. Where no keyring exists, a file in his profile directory
with owner-only permissions, and Pressless says plainly that it fell back.

The key is never logged, never echoed back to the screen, and never
written into the site folder.

## Consequences

- S5 is met, and the key is protected by the same thing protecting his
  other passwords.
- **Two code paths, and the fallback is the weaker one.** It has to be
  tested deliberately, because on this Linux machine the keyring will
  usually be present and the fallback would otherwise never run.
- Moving to a new machine means entering the key again. Correct, but he
  should be told rather than left guessing.
- A keyring prompt can appear at an odd moment on Linux. That is the
  operating system asking, not Pressless, and the wording is not ours to
  fix — so the setup instructions have to warn him it may happen.
