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

- **Marks gains a link mark and a quote mark** (PRESS-0004)
  `{link: address}words{/}` makes a link. The address must be one http
  or https address, or the mark stays as typed. Lines beginning `>`
  make a quotation that keeps its line breaks; a blank line ends it.
  Import needs both to carry the archive's links and quotations
  (PRESS-0007).

- **The Face: Pressless's own web server, and a plain sentence for every failure.** (PRESS-0011)
  Pressless serves its pages from his own computer only, behind a secret
  made at launch, and every failure any part raises now becomes three
  parts: what happened, what it means for his site, and what to do next.
  Show details names the log file and the Pressless-data folder, with
  buttons to copy its location or open it, and never prints a path.

- **Pressless can be packaged: an AppImage for Linux and a zip for Windows, built by a release workflow from a version tag** (PRESS-0022)
  Each artefact keeps the writer's folder, Pressless-data, beside itself.
  Today it runs a self-check that reports where that folder is and which
  password store it found; the app itself replaces it later.

- **The Store deletes a file by moving it into a bin in Pressless's own folder** (PRESS-0099)
  move_to_bin keeps the file's place under a dated folder, so he can move
  it back by hand. Nothing the Store holds is ever unlinked.

- **A rolling plain-English log, beside the settings and bounded forever** (PRESS-0003)
  Pressless now keeps a plain diary of what it did, in its own folder
  next to the settings file. It rolls by size and keeps exactly one old
  copy, so it cannot fill the drive however long the app runs, and the
  two files together always cover the recent past.

  Nothing secret or identifying goes in it. It adds nothing to the
  message it is handed, and the design now places the obligation on the
  part that raises a failure rather than on whatever writes it down —
  so there is nothing downstream to strip. Where something fails that
  Pressless did not raise itself, only the failure's type is recorded,
  because a stock file error quotes the path it failed on.

  A log that cannot be written is simply not written. Nothing the writer
  does fails because the diary did.

- **On a drive that cannot make files private, Pressless says so and carries on** (PRESS-0097)
  Some drives — a memory stick, a shared network folder — will not let the
  app lock its files to you alone. Your settings and your writing still
  save, and you are told once. The part that holds your publishing key
  still refuses outright, because that one is a secret.

- **A real security policy: what Pressless protects, and how to report a problem privately** (PRESS-0065)
  SECURITY.md shipped with its sections still as the template's own
  prompts, under a header saying an empty policy is worse than none. It
  now names the four places data crosses into Pressless and what guards
  each, and points reporters at GitHub's private reporting rather than
  the public issue tracker.

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

- **Each way publishing can be refused now says which one it was** (PRESS-0116)
  Five different things can stop a publish — a missing site folder, a
  stray file, a build that would empty the site, a folder that cannot be
  written, and something absent inside the repository. They used to look
  identical to the part that explains them, so it could only offer one
  generic sentence. Each is now its own kind, so each can say what to do
  next.

- **The first publish spends half as long waiting** (PRESS-0114)
  Pressless paused a second between every file it uploaded. Measured against
  GitHub, that pause is not asked for on file uploads -- 550 went up in one
  rate-limit hour at a sustained 136 a minute, every one accepted. Uploads now
  pause half a second, which is still slower than the rate GitHub was measured
  accepting.

  The three requests that finish a publish keep the full second. Those are the
  ones GitHub's limits are plausibly about, nothing has measured them, and
  there are only three of them.

  On a first publish of the whole site that is roughly seven minutes of
  waiting instead of fourteen.

- **A stray file in the folder Pressless publishes from now stops the publish instead of going up with the site** (PRESS-0089)
  The folder Pressless builds into is Pressless's alone. Anything else that
  turns up in it -- a hidden file your computer left there, a shortcut, a
  leftover from another program -- used to be published to the live site or
  quietly ignored. Now the publish stops and names the file, so you find out
  rather than not.

  Anything on the untouchable list is left alone as before, so the file
  holding your domain name is never what stops a publish.

- **A photograph with a caption now describes itself to a screen reader** (PRESS-0059)
  The caption the writer already types becomes the picture's description as
  well, so a reader who cannot see the photograph is told what it is. A
  photograph with no caption stays decorative, as before.

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

- **Failure messages from the Store and the Publisher no longer name a folder on his computer or the account his site is published under** (PRESS-0117)
  A file is named by its own name, an entry by its slug, and a request by
  what it asked for. A system error is reported by its reason, never by
  its own words, which quote the path it failed on.

- **Failure messages no longer name a folder on his computer** (PRESS-0117)
  The Publisher, Insights, Credentials and Settings all put the full
  folder path into messages when something went wrong, and Credentials
  named the account his key is filed under. Both identify him, and the
  message is what he would send to whoever helps him. They now name the
  thing that failed instead.

- **A file error no longer repeats the path in its own words** (PRESS-0117)
  Where the operating system reported a problem, its own wording was
  pasted into the message, and that wording quotes the file it failed
  on. So every one of those messages named the path twice. Only the
  reason is kept now.

- **Setup no longer pastes a password store's own error text into its message** (PRESS-0068)
  The store Pressless asks can be a plain file, and its errors quote
  their own location under his home folder. Setup now reports what kind
  of failure it was and nothing more.

- **The entry-format promise now says which parser it is about** (PRESS-0060)
  ADR-0001 promised that anything the parser does not recognise is kept
  exactly as written, without saying which parser. It means the one that reads
  your formatting marks. The design document had extended the same promise to
  the entry file's header, and that half was measurably untrue -- an
  unrecognised header field keeps its name and its value, but not the exact
  spacing around it. Both documents now say what actually happens.

- **If GitHub asks Pressless to wait twice, it now waits longer the second time** (PRESS-0113)
  GitHub asks callers to back off by an increasing amount, and warns that
  keeping up the same pace risks being blocked. Pressless waited the same
  interval every time. The first wait is unchanged; each one after it is
  longer.

- **The tests that prove twelve years of writing survives can no longer stop running in silence** (PRESS-0108)
  Those tests compare against a generator that lives outside this
  repository. Every way of failing to load it -- a typo in the path, a
  renamed function, a broken file -- was reported as "it is not on this
  machine", which is the one cause that is normal and skips. So the most
  important test in the project could have stopped running without anyone
  noticing. Only genuine absence skips now; everything else fails and says
  why.

- **Several tests checked for one spelling of a problem and would have missed the same problem written another way** (PRESS-0110)
  One guard listed seven things the text-formatting code must not use, so
  anything not on the list passed -- including the very thing it exists to
  keep out. It now lists what IS allowed. Another checked that files are
  saved safely by pairing each save with the wrong temporary file, so a
  faulty save could pass. Each fix was proved by breaking the code on
  purpose and watching the test catch it.

- **Saving no longer leaks a file handle when the privacy notice is treated as an error** (PRESS-0075)
  A caller configured to treat warnings as errors could make the
  could-not-make-this-private notice fail the save part-way, leaving one
  operating-system file handle open each time. Both the settings file and
  your entries were affected.

- **Comments with a missing or repeated identifier are refused rather than written** (PRESS-0094)
  A comment with no identifier could be replied to, and the reply would
  silently be treated as a top-level comment instead of an answer. Two
  comments sharing an identifier left a reply pointing at both. Either now
  refuses the whole set and writes nothing.

- **A stray file in a folder no longer stops the site building** (PRESS-0098)
  Drop a file with an unusable name into your entries, pages or templates
  folder and Pressless now builds from the files it can read and tells you
  which one it passed over. Before, the listing handed that name back and
  the next step refused it.

- **Publishing over a file you renamed yourself now says what it found** (PRESS-0093)
  If you rename an entry file by hand and then publish that entry, the
  folder can end up holding both. The publish still goes through — nothing
  is written over — and Pressless now names the second file, which it could
  not otherwise reach.

- **The dashboard's cache keeps one answer per time span** (PRESS-0101)
  Google is asked how the site is being read, and the answer is kept for
  an hour so the site's hourly allowance is not spent on every click.
  That store held one answer, so offering a second time span would have
  made each one evict the other and every click ask again. It now holds
  one answer per span. Existing cache files are ignored and refetched
  once; nothing needs deleting by hand.

- **A credentials file whose version is missing or the wrong type is refused** (PRESS-0100)
  The check accepted `true` and `1.0` as version 1, because Python treats
  them as equal, and said nothing about a file carrying no version at all.
  It now matches the settings file next door, which was always strict.

- **A blob GitHub sends back malformed now reports as itself rather than crashing.** (PRESS-0095)
  One kind of bad answer from GitHub reached the writer as "something
  went wrong" instead of a sentence about his site. It is now one of the
  Publisher's own named failures, like every other answer it can get.

- **An entry no longer gains header lines it never had when it is saved** (PRESS-0060)
  Saving an entry written without a Categories or Tags line added an
  empty one of each. Every imported entry would have gained two.

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

- **The leak sweep catches more ways the writer could be named** (PRESS-0119)
  The gate's sweep now matches the site's name with a separator in it,
  reads further patterns from a machine-local key that never enters the
  repository, and checks tag messages as well as commits. A checkout
  without the key says so on every run.

- **A failed read of the publishing key can no longer quote the store's own words** (PRESS-0100)
  When the operating system's password store fails, its own message can
  repeat what it was handling. Saving the key already guarded against
  that; reading it did not, so the store's text could reach an error
  report and the app's log. Both sides now name only the kind of fault.

- **A photograph's name is checked before it reaches the file system** (PRESS-0055)
  A name carrying a folder separator, a colon, a control character or `..`
  no longer forms a photograph mark; the line stays as the writer typed it.
  Marks hands that name straight to whatever looks the file up, so nothing
  further along could have caught it.

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
