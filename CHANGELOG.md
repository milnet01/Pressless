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

- **A test pinning that every network open passes a timeout** (PRESS-0071)
  No static-analysis tool in the project's set reads urllib, so this
  guard could have been removed without anything noticing.

- **The Store also holds the fixed pages, the page furniture, the templates and the historical comments.** (PRESS-0006)
  His About page, the bits repeated on every page, the templates a new
  piece starts from and the old readers' comments all become ordinary
  files beside his writing, in the same folder Pressless keeps it in.

  A fixed page and a header or footer are kept exactly as typed, down to
  the line endings and any markup mistake -- so the plain box and the code
  view can edit the same file without either tidying the other's work
  away. A template is an ordinary entry file in a folder of its own, and
  there is no way to publish one by accident.

  The comments are the ones readers already left; the site takes no new
  ones. Replies stay attached to what they answer, and a reply pointing at
  a comment that is not there is refused rather than quietly dropped. What
  never comes across is the email address and the IP address WordPress
  collected around each comment -- a reader's own words are carried whole,
  whatever is in them, but nothing else about them is.

  Proven against the real archive: all 78 comments written out and read
  back with nothing changed, every reply still pointing at the right
  comment, and no address reaching any file.

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

- **CI runs the suite in random order, as the maintainer's machine already did** (PRESS-0027)
  pytest-randomly is declared in the dev extra rather than merely
  installed locally, so the shared gate script no longer runs the
  suite two different ways.

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

- **A file whose `Slug` header is not a legal slug is refused when it is read** (PRESS-0074)
  Only the file name and the header were compared, so a hand-created
  file agreeing with its own header opened as an entry the Store then
  refused to save.

- **Saving settings no longer overwrites a file written by a different version of Pressless** (PRESS-0001)
  The check that stops one version relabelling another version's settings
  file was stricter when reading than when writing, so a file Pressless
  refuses to open was one it would happily save over.

- **The dashboard stops trusting a clock that went backwards, keeps its cache out of the published folder, and reads a quiet week as zero** (PRESS-0056)
  A cache whose timestamp is in the future is refetched rather than treated
  as fresh for ever. The cache is refused a home inside the folder that gets
  published, so readership figures cannot end up on the public site. A week
  nobody read now reports zero instead of an error. And a property id that
  is not the numeric one is refused at the point it is entered, rather than
  becoming a puzzling failure from Google later.

- **The settings file is checked properly before Pressless acts on it** (PRESS-0066)
  A version written by another Pressless is no longer mistaken for one this
  build understands. A repository name carrying punctuation that would
  change what gets asked of GitHub is refused, while every real repository
  name still loads. A settings file too deeply nested to parse now gets a
  sentence rather than a crash, and a save that cannot get started no
  longer leaves a file handle open.

- **Publishing reports a server error honestly, waits out GitHub's real rate limits, and never leaves a half-fetched folder** (PRESS-0046)
  A server error answering the last step of a publish now says the outcome
  is unknown rather than claiming the site did not move. GitHub's main rate
  limit is waited out instead of being read as a rejected key, a slow-down
  with no interval waits the minute GitHub asks for, and a wait too long to
  sit through is reported rather than slept. Fetching the previous state
  puts nothing in the folder until every file has arrived.

- **An entry dated with a time zone is refused instead of being silently moved by hours.** (PRESS-0067)
  An entry file records the date and time you wrote at, with no time zone.
  Handing Pressless a date that carried one used to store the clock reading
  and drop the zone without saying so — which could put the entry hours
  away from when it was written, and near midnight give it a different
  published address.

  It now refuses that date and says what to do instead. A date with
  fractions of a second is still accepted, rounded down to the second, so
  saving with the current time goes on working.

- **An entry carrying a character that cannot be saved now says so, instead of showing an unexpected error.** (PRESS-0067)
  A few characters cannot be written to a text file at all. Pasting one
  into an entry used to reach the unexpected-error screen; it is now
  refused the way any other unsaveable entry is, with nothing written and
  the previous version of the entry untouched.

  Interrupting a save yourself is still reported as an interruption, not
  as a fault in your writing.

- **An older copy of Pressless can no longer quietly relabel a file a newer one wrote.** (PRESS-0053)
  Both the settings file and the credentials file carry a version number,
  and Pressless already refuses to READ one written by a newer version.
  It did not check when SAVING -- so an older copy would keep the newer
  copy's contents while stamping its own version on top, after which
  neither could read the file properly.

  This cannot happen yet, because there is only one version. Holding it
  now is what stops it happening the first time there are two.

- **Three more publishing failures now explain themselves instead of showing an unexpected error.** (PRESS-0073)
  A reply from GitHub missing a piece of information, a disk with no room
  left while fetching an older version of the site, and a file in the site
  folder that cannot be read. All three used to surface as an unexpected
  error; each now says what happened.

- **A leftover password-store setting on your machine no longer causes an unexpected-error screen during setup.** (PRESS-0050)
  Your system's password store is chosen by a small config file. If that
  file named a store that is no longer installed -- the ordinary state
  after removing one -- setup failed with an unexpected error instead of
  saying what went wrong.

- **A settings file with one damaged character now gives a clear message instead of crashing.** (PRESS-0049)
  If a single character in the settings file could not be read -- which
  happens when a file written on Windows is opened elsewhere -- Pressless
  crashed rather than telling you which file was at fault. It now names
  the file, both when opening it and when saving over it.

- **A line with a great many marks on it no longer crashes, and no longer crawls.** (PRESS-0054)
  Two ways an unusual line could go wrong. A line nesting marks
  thousands deep crashed outright, where the rule is that anything
  Pressless cannot make sense of is left as plain text. And a long line
  of unfinished marks got slower and slower the longer it was -- four
  thousand of them took over eight seconds.

  Both are fixed: deeply nested text falls back to plain text as it
  should, and that same line now takes about four hundredths of a
  second.

- **Typing a curly bracket inside coloured text no longer makes the colour vanish.** (PRESS-0054)
  Colour marks are written as {accent}like this{/}. If the words in
  between happened to contain a curly bracket of their own, Pressless
  lost track of where the colour ended -- and the whole line came out as
  plain text with the marks showing. Nothing warned you; the colour was
  just gone from the published page.

  Checked against your own writing: across every post in the archive,
  including the lines that contain curly brackets, this change alters
  nothing that was already correct.

- **An unusual field name in an entry can no longer overwrite the entry's title or scramble it.** (PRESS-0048)
  An entry file can carry extra labelled lines beyond the ones Pressless
  knows about, and it keeps them. But three kinds of label quietly broke
  the file.

  A label containing a colon was split in the wrong place when read back.
  A label with the same name as one Pressless already uses -- Title, for
  instance -- REPLACED the entry's real title and then vanished; if it
  was Slug, the file could not be opened again at all. And a label with a
  stray space in front of it, like " Title", was treated as a new one, so
  the entry lost its title and gained a second, empty title line.

  All three are now refused when saving, before anything is written, and
  a label with a stray space is read as the label it plainly is. Ordinary
  extra labels are still kept exactly as before.

- **Fetching part of the site with "/" now means the whole site, not nothing.** (PRESS-0069)
  Asking for a folder of "/" matched no file at all, and reported
  success -- so you got an empty result that looked like a completed
  fetch.

- **Branch names with unusual characters now work.** (PRESS-0069)
  A branch name containing a `#`, or letters outside the English
  alphabet, was put into the web address as-is. The `#` silently cut the
  address short and the accented letters made the request fail
  outright. Both are now encoded properly.

- **A missing branch is no longer reported as a missing repository.** (PRESS-0069)
  If GitHub said a branch or a file was not there, Pressless told you
  your repository setting pointed at nothing -- sending you to check a
  setting that was correct. It now says the repository is there and the
  thing inside it is not.

- **A reply that arrives cut short is reported as a connection failure, not a crash.** (PRESS-0040)
  A reply that arrived truncated or malformed slipped past the app's
  error handling and reached you as an unexpected-error screen. It is
  now treated as what it is -- no answer -- so the dashboard falls back
  to the numbers it already has, and a publish says plainly that it does
  not know the outcome.

- **A connection that goes quiet no longer leaves the app hanging forever.** (PRESS-0041)
  Every request now gives up after thirty seconds. Before this, a
  connection that was accepted and then never answered would wait
  indefinitely with nothing able to cancel it -- so the dashboard could
  not fall back to yesterday's numbers, and a publish could leave you
  never learning whether it went out.

- **An entry whose address is a name Windows reserves is refused everywhere, and a hand-renamed file suffix no longer hides an entry from half the app.** (PRESS-0067)
  Two more items of the same cluster. A handful of short names — con,
  nul, com1 and their kin — cannot be filenames on Windows, so an entry
  addressed that way saved on Linux and vanished on Windows. They are now
  refused on both, so an entry that saves on one machine saves on the
  other. Separately, the two ways the app looks for an entry disagreed
  about a file whose .txt had been renamed .TXT by hand; they now share
  one rule and cannot disagree.

- **Publishing an entry can no longer overwrite one that appears while the check is running, and a stray file cannot break a listing.** (PRESS-0067)
  Two items of a larger cluster. The refusal to overwrite is now made by
  the move itself rather than by a check taken beforehand, so a second
  copy of the app running at the same time cannot destroy an entry. A file
  named only ".txt" is no longer read as an entry with no name.

- **An entry saved with Windows line endings is rejected, and the message misstates the cause.** (PRESS-0047)
  An entry opened and saved in a Windows editor was refused with a
  message naming a blank line that was plainly there. Both spellings of
  the blank line ending the header are now read, and the body is handed
  back exactly as it was found.

- **Four atomic writers call os.replace with no fsync, so three specs promise durability the code does not have.** (PRESS-0039)
  Settings, Credentials, the Store and the Insights cache each renamed a
  temporary over the target without syncing it first, so a power loss
  could commit the rename before the data and leave an empty file. All
  four now write LF explicitly as well.

- **Five findings from the first whole-tree static-analysis sweep** (PRESS-0038)
  A dead case pattern in the pre-commit hook, a git blob hash that
  would refuse to run under a FIPS policy, a leftover test helper, a
  misspelling, and three lines over the project's own column limit.
  None changes what the app does.

- **The leak sweep searches every pattern on all three surfaces** (PRESS-0032)
  The history pass searched a subset, so a revision whose files
  carried only the analytics id or a private address was reported by
  no surface once the file itself was gone.

- **The Marks archive conformance test now runs instead of always skipping** (PRESS-0035)
  It resolved the sibling generator one directory too high, so the
  lookup failed and the test skipped with a message saying the
  generator was not on the machine. INV-5 had produced no result
  anywhere; it now runs and passes.

### Security

- **A shortcut left in your site folder is no longer published.** (PRESS-0069)
  Pressless publishes every file it finds in the site folder. If one of
  those was a shortcut pointing somewhere else on your computer,
  Pressless read what it pointed at and published that -- to a public
  site. Shortcuts are now skipped.

  Ordinary hidden files are still published, deliberately: .nojekyll is
  one, and the site needs it.

- **Fetching an older version of the site can no longer write files outside the folder you asked for.** (PRESS-0069)
  When Pressless fetches back a previous version, it takes the file
  names from GitHub's own listing. A specially crafted entry could name
  a path that climbs out of the folder you pointed it at. It is now
  checked before anything is written.

- **If your computer's password store fails oddly, its complaint can no longer quote the publishing key back.** (PRESS-0051)
  Pressless hands the key to your system's password store to save it. If
  that store then failed in an unusual way, its own complaint was copied
  into the error Pressless showed -- and the store had just been given
  the key, so its complaint could contain it.

  Pressless now records only what KIND of fault it was, never the store's
  own wording, and it no longer keeps the original fault attached
  underneath, where a crash report or the log would have printed it
  anyway.

- **The backup file holding your publishing key is now checked to be yours before it is read.** (PRESS-0085)
  Where your computer has no password store, Pressless keeps the key in
  a file of its own. It now refuses that file if it has been replaced by
  a shortcut to somewhere else, or if it belongs to another account on
  the machine -- so on a drive you share, nobody can swap in their own
  file and have Pressless use it.

  It deliberately does NOT refuse a file whose permissions look loose.
  That is the file you get when you carry your setup over from another
  machine, and refusing it would block the one case the fallback exists
  for.

  Two limits, stated rather than glossed: on a memory stick or an
  external drive formatted without ownership, every file looks like
  yours, so the ownership half cannot help there -- the shortcut check
  still does. And Windows offers neither check, where nothing writes
  this file in the first place.

- **The publishing key is no longer handed to a server the app was redirected to.** (PRESS-0052)
  If something on the network answered a request by pointing the app
  somewhere else, the app carried the key that can rewrite the whole
  site -- or the Google sign-in -- along to whoever answered. It now
  drops them whenever the redirect leads somewhere else, and keeps them
  when it stays in the same place, so an address that has simply moved
  still works.
