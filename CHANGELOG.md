# Changelog

All notable changes to Pressless are documented in this file.

The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The format
contract is `~/.claude/standards/changelog-format.md` § 4.

The `[Unreleased]` block stays at the top, always, even when empty.

## [Unreleased]

(Nothing yet. Scaffolding is not a release — the first dated section
appears once something has actually shipped.)

### Added

- **The design is broken into PRESS-NNNN roadmap items.**
  Every sign of success in discovery is named by at least one item, and
  every item records what must close before it can start.

### Changed

- **The roadmap is served from the Ants roadmap store rather than from ROADMAP.md.**
  The file is now a generated render of the store, so a hand edit to it
  is discarded by the next write.
