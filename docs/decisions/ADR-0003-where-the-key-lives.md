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
covers both. Where no keyring exists, a file in Pressless's own folder
with owner-only permissions, and Pressless says plainly that it fell back
and names the store that answered.

**Where a file cannot be made private to one user there is no fallback:
setup stops and says so.** On Windows `os.chmod` sets only the read-only
flag, so a file there would be readable by every account on the machine —
which is the protection this decision exists to provide.

The key is never logged, never echoed back to the screen, and never
written into the site folder.

**The Google authorisation the dashboard needs lives the same way**, under
its own account name. It is a second secret rather than a second scheme:
one store, one fallback, one rule about never writing a secret down. It is
also optional, because ADR-0005 lets the writer decline the dashboard, and
declining must not leave Pressless unable to start.

## Consequences

- S5 is met, and the key is protected by the same thing protecting his
  other passwords.
- **Settings records the account names, never the secrets** — which store
  is in use, and the name each secret is filed under. It is written in
  plain text beside the program, so a secret in it would sit outside the
  protection this record exists to provide (PRESS-0001 §4.5).
- **Two code paths, and the fallback is the weaker one.** It has to be
  tested deliberately, because on this Linux machine the keyring will
  usually be present and the fallback would otherwise never run.
- Moving to a new machine means entering the key again. Correct, but he
  should be told rather than left guessing.
- A keyring prompt can appear at an odd moment on Linux. That is the
  operating system asking, not Pressless, and the wording is not ours to
  fix — so the setup instructions have to warn him it may happen.
