# Security policy — Pressless

`~/.claude/standards/security.md` owns what a trust boundary is and what
defending one requires. This file is only what an outside reader needs.

## Trust boundaries

- **The writer's own text becoming a public page.** An entry body is
  writer-supplied text rendered into HTML and then published. Escaping in
  the markup part is what defends that crossing;
  `docs/specs/PRESS-0004-marks.md` § 5 states the rule, and the gaps found
  in it so far are tracked as open roadmap items rather than claimed
  closed.
- **The publishing key at rest.** The key can rewrite the live site. It is
  held in the operating system's own credential store — or, where there is
  none, in a file in Pressless's folder with owner-only permissions, which
  Pressless says plainly it fell back to
  (`docs/decisions/ADR-0003-where-the-key-lives.md`).
- **The Face's own server on `127.0.0.1`.** The writer's browser drives
  Pressless through it, and any page open in that browser can send it a
  request. Each request must carry the per-run secret (as the link's query or
  its cookie), a POST naming another origin is refused, and the `Host` header
  must name the server exactly; `docs/specs/PRESS-0011-face.md` § 4.5.
- **Self-update.** Pressless downloads a new release and replaces itself with
  it. A release is trusted only through its signed list, checked against the
  keys built into Pressless, and each download must match the size and
  SHA-256 that list names; `docs/specs/PRESS-0023-self-update.md` § 4.3.
- **Starting another program.** Open folder hands one path to the system's
  own folder opener. An update runs a fixed script in `/bin/sh` or
  PowerShell, and hands it each path as a separate argument, never as part
  of the script's text.
- **The libraries Pressless runs.** `keyring`, `Pillow`, `cryptography` and
  `certifi` run inside it, and the packaged program bundles them.
  `pyproject.toml` sets only a lowest version for each, so a build takes
  whatever is newest above it; nothing pins them or checks their hashes.
- **Privilege: none.** Pressless runs as the logged-on user and never asks
  for more rights.
- **Two third-party services over the network.** Pressless talks to GitHub
  to publish, and to Google Analytics to read visitor numbers. What comes
  back is treated as untrusted: paths taken from a GitHub reply are
  confined to the folder that was asked for, and every network read is
  opened with a timeout.
- **Files on disk that Pressless did not write.** The entry files, the
  settings file and the dashboard cache are all read back and parsed, and
  the writer may edit any of them by hand. Each is refused with a stated
  reason rather than half-read. On Linux every file Pressless writes is
  left readable by its owner alone; Windows cannot deliver that, and
  where the publishing key itself cannot be kept private Pressless stops
  rather than writing it.

## Supported versions

Pressless has not reached 1.0. Only the latest release is supported, and
fixes land on `main`.

## Reporting a vulnerability

Please report privately, through GitHub's own private vulnerability
reporting on this repository's **Security** tab. Do not open a public
issue: that discloses the problem before there is a fix.

Expect an acknowledgement, and then either a fix or an explanation of why
it is not one. This is a single-maintainer project, so no response time is
promised.
