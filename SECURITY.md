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
- **Two third-party services over the network.** Pressless talks to GitHub
  to publish, and to Google Analytics to read visitor numbers. What comes
  back is treated as untrusted: paths taken from a GitHub reply are
  confined to the folder that was asked for, and every network read is
  opened with a timeout.
- **Files on disk that Pressless did not write.** The entry files, the
  settings file and the dashboard cache are all read back and parsed, and
  the writer may edit any of them by hand. Each is refused with a stated
  reason rather than half-read. Every file Pressless writes is left
  readable by its owner alone.

## Supported versions

Pressless has not reached 1.0 and has no released version yet. Until it
does, fixes land on `main` and there is nothing older to support.

## Reporting a vulnerability

Please report privately, through GitHub's own private vulnerability
reporting on this repository's **Security** tab. Do not open a public
issue: that discloses the problem before there is a fix.

Expect an acknowledgement, and then either a fix or an explanation of why
it is not one. This is a single-maintainer project, so no response time is
promised.
