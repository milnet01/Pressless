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

- **The Store: one file per entry, with drafts kept apart from published.** (PRESS-0005)
  Every entry is an ordinary text file in an ordinary folder, openable in Notepad, and unfinished ones are kept off the web.

- **Pressless can ask Google Analytics how the site is being read** (PRESS-0019)
  Fetches the visitor numbers Google already collects -- how many
  people, and which countries they read from -- ready for the dashboard
  to show. Countries come back as the two-letter codes the flag pictures
  are keyed by, and the number of people is the one Google works out
  rather than the rows added up, which would count a visitor seen in two
  countries twice. It keeps the last answer on disk so opening the
  dashboard repeatedly does not spend the daily allowance Google gives,
  and if Google cannot be reached it shows the last answer it has,
  labelled as old, instead of an error. Setting this up is optional:
  decline it and nothing else about writing or publishing changes.

- **The Publisher can fetch back a previous state of the repository.** (PRESS-0010)
  Reads an earlier version of the site back out of GitHub -- half of what undo needs.

- **The Publisher makes GitHub match the folder it was handed.** (PRESS-0009)
  Sends the finished site to GitHub without git being installed, and never touches the few files that are not ours.

- **Checks now run before anything is published, on this machine and on GitHub** (PRESS-0024)
  One file holds the checks and GitHub runs that same file, so what
  passes here is what passes there. Before publishing, it makes sure
  nothing anywhere -- the files, their whole history, or the messages
  attached to them -- names the writer, then checks the code and runs
  the tests. The most important test needs the real blog export, which
  cannot be published; it now runs automatically on the machine that
  has it.

- **The two secrets are kept in the operating system's own credential store** (PRESS-0002)
  Pressless now has one place that keeps the publishing key and the
  Analytics key, and it puts them where the rest of your passwords
  already live rather than in a file of its own. It tells you which
  store answered, so a plain-file store can never pass itself off as a
  protected one. On Windows it refuses the file fallback outright: a
  file cannot be made private to one person there. Nothing it can go
  wrong with ever prints the key itself.

- **Settings — the one place that holds what is true of this machine.** (PRESS-0001)
  Where the finished site is written, which repository it is published
  to, which tag the Builder filters, which files in that repository are
  not ours to touch, which store the two secrets are filed under, and
  the Analytics property id. It holds no secret itself, only the names
  they are kept under. It reads nothing else — no store, no network, no
  other part of Pressless — because six parts depend on it and it may
  depend on nothing. A save is whole or not at all: a crash mid-write
  leaves the previous settings, never half of the new ones, and a key
  written by a later Pressless survives an older one saving over it.

- **Marks — the small styling language, and the first working code.** (PRESS-0004)
  Bold, italic, the site's own two colours, any colour picked as a hex
  code, a per-character rainbow, and a photograph on a line of its own.
  One table, one parser, one renderer, so the box the writer types into
  and the page his readers see cannot disagree. It touches no disk and
  no network. Proved against the real twelve-year archive: 556 raw-text
  entries render byte-identically to today's generator, so migrating
  loses no line of a poem.

- **The design is broken into PRESS-NNNN roadmap items.**
  Every sign of success in discovery is named by at least one item, and
  every item records what must close before it can start.

### Changed

- **The design now says what the publishing part may write, and where it goes.** (PRESS-0026)
  The rule permitted reading only, while fetching back a previous state
  writes files to disk. It now names that write and pins where it lands --
  inside Pressless's own folder, never the folder that gets published.

- **The flag-rendering claim behind the dashboard design is measured rather than assumed.**
  Confirmed on a Windows 10 test box: country flags have no glyphs and
  must ship as images. The same box makes the packaged Windows executable
  testable before release.

- **The roadmap is served from the Ants roadmap store rather than from ROADMAP.md.**
  The file is now a generated render of the store, so a hand edit to it
  is discarded by the next write.

### Fixed

- **The leak sweep searches every pattern on all three surfaces** (PRESS-0032)
  The history pass searched a subset, so a revision whose files
  carried only the analytics id or a private address was reported by
  no surface once the file itself was gone.

- **The Marks archive conformance test now runs instead of always skipping** (PRESS-0035)
  It resolved the sibling generator one directory too high, so the
  lookup failed and the test skipped with a message saying the
  generator was not on the machine. INV-5 had produced no result
  anywhere; it now runs and passes.
