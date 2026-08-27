<!-- ants-roadmap-format: 1 -->
# Pressless — Roadmap

> What is planned, in progress and shipped. [CHANGELOG.md](CHANGELOG.md)
> is the user-facing record of what shipped; released items stay here and
> flip to ✅.
>
> **Format:** `~/.claude/standards/roadmap-format.md`. Theme emojis
> (§ 3.4), priority bands (§ 3.12) and the full bullet field set (§ 3.5)
> are defined there and deliberately not restated here.

**Legend**

- ✅ Done · 🚧 In progress · 📋 Planned · 💭 Considered

## P01 — (first block)

> Pre-1.0 projects use phase blocks (`## P01 — …`); these promote into
> `## 1.0.0 — initial release` at 1.0. Such a roadmap does not rotate
> into archives — see § 3.9.
>
> **Nothing goes here until design is agreed.** Items are broken out of
> the design, and the gate on doing so is that every sign of success in
> `docs/discovery.md` — each carrying an `S<n>` id — is claimed by at
> least one item, and every item
> names what must close before it can start, in `Blocked-by:`
> (`~/.claude/workflow.md` § 5, `roadmap-format.md` § 3.5).

- ✅ [PRESS-0001] **Settings holds what is true of this machine, and nothing else.**
  Where the site folder is, which repository to publish to, the Daily
  Prompt tag filter, the untouchable-path list, and a pointer to where
  both credentials are kept. It depends on nothing, and every other part
  reads it.
  The untouchable list is DERIVED from the live repository root at setup
  -- every entry the Builder does not produce -- never typed from the
  design document. A list is only that rule's output on the day it was read; the rule is the contract.
  Serves no sign of success on its own; nothing else can run without it.
  Blocked-by: nothing.
  Layman: The settings file: where the site sits on this machine, and which site to publish to.
  Progress (2026-08-25): Settings gains the rule for where Pressless's
  own folder lives -- beside the program file, not under the home
  directory. Decided with the user so that drafts, photograph
  originals and the log do not land on a system drive short of space.
  The path is derived, not typed: Settings records nothing a move of
  the program file would invalidate. PRESS-0022 owns finding the
  program file's real location, which on an AppImage is not the
  running process's own path.
  Picked 2026-08-25. Root of the graph: PRESS-0002, 0003, 0005, 0008, 0009, 0011 and 0019 all name it in Blocked-by, and it names nothing. Spec required -- spec-format.md § 1, first trigger: every other part binds to these keys, and the untouchable-path list is a safety boundary rather than a preference.
  Spec accepted 2026-08-25: docs/specs/PRESS-0001-settings.md, two cold-eyes loops, nothing deferred. Four decisions worth knowing without opening it. Settings is HANDED its folder and never derives one, which is what keeps its design row's "depends on nothing" true and leaves the AppImage location question inside PRESS-0022. The file is JSON and the writer never opens it -- asked and answered by the user that day, which is what removed the argument for TOML and its bundled dependency. An absent untouchable list is an error where an empty one is valid, so a half-finished setup cannot delete the CNAME and detach the domain. And daily_prompt_filter is an fnmatch glob rather than a regex: measured, the two readings are INVERTED on both live tag shapes, so a regex reading would publish what was asked to be filtered and filter the writer's own entries. The gate also proved section 6 false by running it -- os.replace onto a read-only file in a writable directory succeeds on Linux -- so the failure mode is the folder's permissions, not the file's.
  Progress (2026-08-25): tests/test_settings.py written and red — one
  test per invariant, INV-1 to INV-7, against a stub declaring §4.1's
  surface. Seven collected, five failing on behaviour; INV-1 and INV-6
  pass against a correct stub by design. Checked against a disposable
  reference implementation (not committed): green, and eleven mutations
  probed, ten killed. The survivor was INV-7's own named breach, a
  fallback searching the parent folder, and the test was strengthened
  until it died. The implementation is next.
  Resolved (2026-08-25): src/pressless/settings.py implements §4's
  surface; the seven invariant tests pass and the suite is green. Every
  case in §4.3's outcome table, §4.2's two declinable fields, §4.4's
  saving rules and §6's failure modes was executed rather than reasoned
  about, including §6's measured read-only-file behaviour. Eleven
  mutations probed: the eight that break an invariant all died. The
  three that survived are the three §10 already names as guarded by
  nothing — the version row and the two shape rows — so that gap is now
  measured rather than predicted, and it is unchanged rather than new.
  Every read and write names UTF-8, because Python's default is the
  locale's and the app must run on Windows too.
  Progress (2026-08-26): the Analytics field is renamed to analytics_property_id and the spec took a second cold-eyes run, two loops, thirteen verified and thirteen fixed, a calm cap. Three things changed behaviour or contract rather than prose. load() now rejects a relative site_folder -- it was accepted silently, and the Builder would have resolved it against whatever directory the process started in; test_relative_site_folder_is_rejected locks it. INV-7 was an over-broad cleanup claim over the folder that also holds ADR-0003's fallback credentials file and Insights' cache, so a literal implementer would have deleted the publishing key; it is now an addition rule. And INV-5 claimed save() never leaves a file load() rejects, which is false by execution -- save() validates nothing, and §4.4 now says so.
  Kind: implement.
  Source: design-2026-08-24 § The parts.
  Lanes: Settings.

- ✅ [PRESS-0002] **Both credentials live in the operating system's keyring.**
  The GitHub publishing key and the Google authorisation, through one
  library covering Windows Credential Manager and Linux Secret Service.
  Where no keyring exists, an owner-readable file in Pressless's own
  folder, and Pressless says plainly that it fell back -- ADR-0003, whose
  scope design widened on 2026-08-24 to cover both.
  Neither is ever written to the log, echoed to the screen, or placed in
  the site folder. The fallback path is the weaker one and is tested
  deliberately, because on this Linux machine the keyring will normally be
  there.
  Claims S5 together with PRESS-0021, which is where he is asked.
  Blocked-by: PRESS-0001.
  Layman: The publishing key and the Google permission are kept where the operating system keeps other passwords, not in a file we wrote.
  Progress (2026-08-25): the contract is written and accepted --
  docs/specs/PRESS-0002-credentials.md, two cold-eyes loops, eighteen
  verified findings all fixed, reached the spec cap of 2. Status stays
  planned: no code exists yet.

  Two scope choices were put to the user and answered. Windows never falls
  back to a file, because os.chmod there sets only the read-only flag and
  cannot make a file private to one user, so a fallback would leave a key
  that can rewrite the live site readable by anyone using that machine.
  And the store that answered is always named, because the keyring can
  turn out to be a plaintext file and nothing else would distinguish it.

  BLOCKED ON A DECISION THAT IS NOT THIS ITEM'S. design.md rule 5 lets the
  Publisher read Settings and a folder of finished files and nothing else,
  and rule 8 says the same for Insights. This module is neither, and
  The parts does not list it, so as those rules stand neither part may
  call the thing both depend on -- and PRESS-0001 refuses to hold the
  secret, so routing through Settings is not open either. Either name this
  module in both rules, or make the Face fetch the secret and hand it
  over. PRESS-0009 and PRESS-0019 wait on that choice; the spec's
  cross-doc section records both routes and picks neither.
  Resolved 2026-08-25. src/pressless/credentials.py and
  tests/test_credentials.py, one test per INV-1..9. Red run made against a
  stub, and it came out as spec §7 predicted -- nine collected, seven failing
  on assertions, INV-1 and INV-6 green against a stub by design. Suite after:
  24 passed, 1 skipped (the archive test, correct without PRESSLESS_ARCHIVE);
  ruff clean.

  The tests were then checked by mutation rather than trusted: eight
  deliberate breaks -- deleting the probe before the member walk, naming the
  nominated chain instead of the answering member, catching every exception as
  "no store", returning the store's answer unexamined, writing the file
  directly and chmodding after, reporting a Windows refusal as the wrong type,
  rebuilding the file from the one secret in hand, and naming the secret in a
  failure message -- were each caught by the invariant that names them. INV-1
  was not probed; §5 says outright it is weak by design.

  pyproject.toml gains keyring>=25, the project's first runtime dependency,
  pinned at the major version §4.6 was measured on. CLAUDE.md § Build and test
  no longer says the project has none.

  Still owed from spec §11, and NOT done here: docs/design.md's amendment (a
  row for this part, plus the hand-off sentence) and ADR-0003's three
  corrections. Both are contract edits that re-arm rule 14's cold-eyes gate.
  Kind: security.
  Source: design-2026-08-24 § Where everything sits on disk, ADR-0003.
  Lanes: Settings.

- 📋 [PRESS-0003] **One rolling plain-English log, and no credential anywhere in it.**
  Beside the settings file in Pressless's own folder, never in the site
  folder. A test proves neither credential reaches it, not even shortened.
  The Face's Show details toggle names its location, for whoever helps him
  rather than for him.
  Serves no sign of success on its own; the error contract leans on it.
  Blocked-by: PRESS-0001.
  Progress (2026-08-25): the design gate found this bullet AND docs/design.md
  section What Import brings across both silent on the export's photographs,
  while rule 9 makes Import unrepeatable -- so on the bullets as written the
  originals stay on WordPress for good and every imported entry goes on
  pointing at the old site. design.md now carries a fifth bullet: Import
  carries the originals into Pressless's own folder and rewrites each entry's
  image references to the picture mark. PRESS-0016 does not cover this -- it
  owns the picture mark through to the web-sized copy, not the one-time
  migration. Scope here widens accordingly.
  **Layman:** A plain diary of what the app did, kept beside the settings, with nothing secret in it.
  Kind: implement.
  Source: design-2026-08-24 § Logging.
  Lanes: Settings, Face.

- ✅ [PRESS-0004] **Marks: one table, one parser, one renderer, used by everything that renders.**
  The marks of ADR-0001: bold, italic, the site's own two colours, any
  colour he picks down to a single letter, run-wide effects such as
  rainbow, and the picture mark. Text in, structure out, structure to
  HTML. It touches no disk and no network, which is what makes it cheap to
  test exhaustively -- and it is the part every poem passes through.
  Every single newline in the body is a line break, so a poem keeps the
  lines it was typed with. Claims S2.
  Anything it does not recognise is preserved byte-for-byte and never
  silently dropped. That is a promise about twelve years of writing, not a
  parser detail.
  One table of every mark it understands, which is the single source the
  cheat sheet is generated from.
  Blocked-by: nothing.
  Progress (2026-08-25): `docs/specs/PRESS-0004-marks.md` is written and
  accepted. Two cold-gate loops, three lanes each, eighteen verified
  findings, all fixed; the cap for a spec is two and it bound.
  What the spec settles that the design left open: the two named site
  colours are `{accent}` and `{muted}` and they render as CSS variables
  so a repaint reaches old entries; an incomplete mark is literal text,
  which is what keeps the archive's self-censored words out of italics;
  `<` and `>` are always escaped while a valid character reference is
  left alone, so the entities in the existing entries survive; a picture
  mark owns its line and renders outside the paragraph; and the mark
  table carries its own renderer, so nothing renders from a second
  hidden table.
  The contract other parts bind to is `parse` / `to_html` / `render` plus
  a `photo_src` callable the caller supplies -- that callable is how the
  no-disk rule is kept while the picture mark still works. PRESS-0008 and
  PRESS-0012 pass different ones.
  Next: `write-test` for the failing tests, then the code. The archive
  conformance run is the proof of S2 and is skipped unless
  `PRESSLESS_ARCHIVE` names an export, because that file is personal data
  and cannot live in a public repository.
  Progress (2026-08-25): tests first. write-test is authoring the invariant tests for INV-1..INV-8; no implementation exists yet.
  Progress (2026-08-25): tests written and proven to fail. With the module
  absent the suite errors at collection, which proves nothing about the
  assertions, so the red run was repeated against throwaway stubs: all nine
  tests were collected and each reached its own assertion. INV-7 was the one
  that passed against stubs, so it was mutated (an added disk import) to prove
  it can fail, then restored. INV-5 was run against the real export and
  reached the comparison. Stubs deleted; no implementation exists.

  Owed when the module lands: a mutation probe. Q3 -- would a test still fail
  if the defect returned another way -- is answered only for INV-7, because a
  probe needs a green baseline and there is none yet. Run it against
  src/pressless/marks.py once the suite is green, one mutation per route each
  invariant could be broken by.
  Progress (2026-08-25): `src/pressless/marks.py` is written and the suite is
  green — 8 pure tests, plus the archive run, which passes over 556 raw-text
  entries with zero mismatches against today's generator and both of INV-5's
  divergence sets empty. That run is the proof of S2.

  The mutation probe this bullet owed has been run: 16 mutations against the
  real module, one per route each invariant could be broken by. Twelve were
  killed. Four survived and they split two ways.

  Two are a real gap and are owed to `write-test`: INV-2's fixtures measure
  NEITHER adjacency clause. Drop the opener clause or the closer clause and
  `b**bs`, `f*cking` and the asterisk divider all still render literally,
  because each fixture is carried by the other clause or by having no partner
  at all. Two inputs do separate them, both verified by rendering against
  hand-mutated copies — `**x*` for the opener (`*<em>x</em>` as written,
  `<em>*x</em>` without) and `*x **` for the closer (literal as written,
  `<em>x *</em>` without). Until those land, INV-2 has a passing test that
  does not measure it.

  Two survivors are correct rather than gaps. The archive cannot measure the
  bare-`&` rule because it contains no bare `&` — INV-5 asserts that emptiness
  itself, and INV-4's own test kills that mutation. And the body-level strip
  is provably redundant with the per-paragraph strip: every chunk reaches
  `_paragraph`, which strips it, so no body whitespace can survive by another
  route. It is kept because §4.4 step 2 pins it and it mirrors the generator.

  The spec was amended three times by the implementation, no re-gate (it is at
  its cold-eyes cap and this is the tail rule 14 routes to the build): §4.5's
  adjacency clauses are a `wrap`'s alone, or they reject §4.2's own
  `{photo: seaside.jpg}`; an argument runs from the end of `opens` to the next
  `}`, which nothing had said; and the gloss "so ***...*** opens nothing" was
  false of its own rule, since scanning resumes one character on.
  Resolved (2026-08-25): the INV-2 gap the probe found is closed, and the
  item is done. `write-test` Route 4 — no reachable broken state, since the
  module was never wrong here — so the fixtures are proven by mutation
  rather than by a historical red run, and that is the honest label: they
  have never been observed to fail against a defect that actually shipped.

  The gap was worse than first reported. Each adjacency clause has two
  independent halves, a space half and an asterisk half, so there were four
  uncovered routes and the first pass covered two. The probe itself found
  the third by surviving; checking the closer for the same split found the
  fourth. INV-2 now carries one fixture per route — `* a*` and `*a *` for
  the space halves, `*x **` and `**x*` for the asterisk ones. Five mutations
  killed, and a control mutation survives, so the test discriminates rather
  than reddening at anything.

  `**x*` is the one that is not a literal fixture: that clause decides where
  the boundary falls rather than whether a mark forms, so it asserts the
  exact output `<p>*<em>x</em></p>`. An assertion that merely looked for the
  absence of a tag could not see it — which is how the original fixtures
  missed it.

  `write-test` Step 2 dispatches a `test-writer` agent to author the test.
  It did not run: this session carries an explicit no-agents instruction,
  which global rule 15 says governs, and rule 14's carve-out reaches only
  the review gates. The fixtures were authored inline and the red run —
  which that skill says may never be delegated — was performed here.
  **Layman:** The small styling language -- bold, italic, colours -- written once so the editor and the live page can never disagree.
  Kind: implement.
  Source: design-2026-08-24 § The parts, ADR-0001.
  Lanes: Marks.

- 📋 [PRESS-0005] **The Store: one file per entry, with drafts kept apart from published.**
  UTF-8 with LF line endings written explicitly, because Windows would
  otherwise rewrite them and every publish would look as though it touched
  the whole site. A short header, a blank line, then the body verbatim.
  The header carries title, slug, date, categories and tags -- read off
  build_blog.py's Post, and losing any of them costs the live site its categories, its tags and its by-year archive.
  Never rewritten in place: write a temporary file, then rename it over
  the old one, which is atomic on both Windows and Linux, so a crash
  mid-save cannot leave half an entry.
  Drafts live in Pressless's own folder, OUTSIDE the site folder, because
  everything in his repository is publicly fetchable -- measured, HTTP 200
  on a file nothing links to. The cost is real and he is told it:
  unfinished work is not backed up.
  Claims S3 and S7.
  Blocked-by: PRESS-0001.
  **Layman:** Every entry is an ordinary text file in an ordinary folder, openable in Notepad, and unfinished ones are kept off the web.
  Kind: implement.
  Source: design-2026-08-24 § Persistence, § Where everything sits on disk.
  Lanes: Store.

- 📋 [PRESS-0006] **The Store also holds the fixed pages, the page furniture, the templates and the historical comments.**
  Home, About, Music and Privacy, stored as HTML and never generated from
  marks, so the plain box and the code view cannot fight. Privacy is named
  because leaving it out is a legal exposure rather than a missing page --
  the site discloses its visitor counting there.
  Exactly one copy of the header, footer and navigation, inside content/
  so that undo brings them back. One edit there reaches every page on the
  site, the whole journal included.
  The historical comments in a file BESIDE the entry rather than inside
  it, read-only, so an entry file stays his prose.
  Templates are entries that are never published, in the same marks as
  everything else.
  Blocked-by: PRESS-0005.
  **Layman:** His About page, the bits that appear on every page, his starting templates and the old readers' comments all live beside his entries.
  Kind: implement.
  Source: design-2026-08-24 § Where the fixed pages live.
  Lanes: Store.

- 📋 [PRESS-0007] **Import carries twelve years across, once, and declines nothing it could not get back.**
  The WordPress export becomes Store files: every published post with its title, slug, date, categories and tags; the drafts and the private posts as drafts, because they are his writing and he never deleted them; the trashed ones skipped, because he did. The published comments with commenter names only -- email addresses and IP addresses must never
  enter the Store at all.
  The Daily Prompt entries come across WITH their tag. Filtering here
  would delete that writing permanently; the filter stays in
  Settings and the Builder goes on excluding them, so his decision
  stays reversible by changing one setting.
  Nothing may depend on Import and it runs once, so anything it declines
  to carry is outside Pressless for good. It is a prerequisite for S1:
  without it the first publish rebuilds a site that has forgotten the old
  entries.
  Blocked-by: PRESS-0005, PRESS-0006.
  **Layman:** A one-time job that turns his 616 WordPress entries into files -- and carries everything, because it only ever runs once.
  Kind: implement.
  Source: design-2026-08-24 § What Import brings across.
  Lanes: Import.

- 📋 [PRESS-0008] **The Builder turns the Store and Settings into a finished site folder.**
  build_blog.py re-homed and separated from the writer: pagination, the by-year
  archive, the categories and the tags, sitemap.xml and robots.txt. It
  renders through the same Marks part the editor uses and never grows a
  rendering path of its own.
  It may read the Store and Settings and may NEVER touch the network, so
  S2 is provable without anything reaching GitHub. It writes only
  published entries into the site folder, which is where S7's guarantee
  lives -- the Publisher has nothing to decide with, so it cannot hold
  that line.
  It copies the Store's published files into content/ as ordinary output,
  and it owns the naming rule for web-sized photograph copies -- the one
  place that rule is written down.
  Blocked-by: PRESS-0001, PRESS-0004, PRESS-0005, PRESS-0006.
  **Layman:** The part that makes the actual web pages -- his existing site generator, re-homed and no longer needing anyone technical.
  Kind: implement.
  Source: design-2026-08-24 § The parts, § What may depend on what.
  Lanes: Builder.

- ✅ [PRESS-0009] **The Publisher makes GitHub match the folder it was handed.**
  Through GitHub's own web interface rather than git, so there is nothing
  for him to install (ADR-0002). It reads the current state, works out
  which files differ, and writes one commit of those -- deletions
  included, so a page he removes actually goes.
  It never writes or removes a path on Settings' untouchable list.
  Deleting CNAME detaches his domain; deleting the Search Console file
  silently un-verifies the site months later.
  It cannot tell an entry from a stylesheet, and does not need to.
  Blocked-by: PRESS-0001, PRESS-0002.
  Layman: Sends the finished site to GitHub without git being installed, and never touches the few files that are not ours.
  Blocked (2026-08-25) on a design.md decision, not on PRESS-0002's
  contract, which is written and accepted. design.md rule 5 lets this part
  read Settings and a folder of finished files and nothing else. The
  publishing key lives in a separate module (see
  docs/specs/PRESS-0002-credentials.md), which is not Settings and is not
  listed in The parts -- and PRESS-0001 refuses to hold the secret, so
  reaching it through Settings is not open either. So as rule 5 stands
  this part cannot legally fetch the key it needs. Either name that module
  in rule 5, or make the Face fetch the secret and hand it over. Section 11
  of the PRESS-0002 spec records both routes and deliberately picks
  neither. Do not work around it by importing anyway.
  Routing decided 2026-08-25 (user deferred the choice): the Face fetches
  the secret from the credentials module and hands it to the Publisher as an
  argument. Design rules 5 and 8 are NOT widened -- rule 1 already gives the
  Face the sequence, being handed a value is not reading a module, and a
  Publisher that takes a token argument is testable without touching a real
  keyring. Still blocked until docs/design.md carries the amendment (a row
  for the credentials part in The parts, plus the hand-off sentence) and that
  amendment passes its cold-eyes gate.
  Progress (2026-08-25): UNBLOCKED. The docs/design.md decision this waited on
  is made -- rule 10 has the Face fetch a secret and hand it to the Publisher
  as an argument, so rules 5 and 8 stand unchanged. Two things the same gate
  added to this item's scope: the Publisher now also lists what sits at the
  repository root when asked (that is how the untouchable list gets derived,
  and nothing could derive it before), and at publish it removes a root entry
  absent from the handed folder unless that entry is on the list -- it never
  re-evaluates the rule there, or it would protect every page just deleted.
  Deferred from the same gate (loop 6, filed not fixed): undo publishes a new
  commit, so after one undo "the previous state" is the state undo just
  replaced. A second undo then restores the broken site. Settle which state the
  fetch names -- the commit before the current one, or the last state before
  the change being undone -- before building the fetch-back way in; the Face's
  undo sequence binds to whichever it is.
  Spec accepted (2026-08-26): docs/specs/PRESS-0009-publisher.md, after two
  cold-eyes loops that reached the spec cap. The deferred undo question above
  is SETTLED by the user: undo steps back one publish, so pressing it twice
  returns the site to the version the first undo replaced. The spec records
  that as decided behaviour, not a defect, and says nothing checks it.
  The spec is an umbrella also covering PRESS-0010 -- the gate found that this
  item had absorbed that one's scope silently.
  Surfaced rather than fixed: design rule 5 permits the Publisher to READ
  Settings and a folder and names no write, while fetch-back writes a fetched
  state to disk. Rule 8 shows the form the design uses when a part writes.
  That amendment is the design document's own gate and is not yet made.
  Progress (2026-08-27): the nine invariant tests are written and
  committed red, with a stub declaring the section 4.1 surface --
  tests/test_publisher.py and src/pressless/publisher.py. INV-1 passes
  against the stub, as the spec's section 7 says it will; the other nine
  fail where they call into it. The implementation is what remains.
  What that red run does NOT prove: every failure lands at the call into
  the stub, so no assertion has executed yet. It is evidence the tests
  reach the right entry points, not that any assertion catches a breach.
  A mutation probe settles that and needs a green baseline, so it is owed
  once the code lands.
  Resolved (2026-08-27): src/pressless/publisher.py implements section 4.1's
  surface -- publish, root_entries and fetch_previous. All nine invariants
  green; the suite is 35 passed, 1 skipped; the gate passes.
  Proved rather than asserted: a mutation probe ran 19 mutations, one per
  route each invariant's Breaks-when names. 18 were killed. The one that
  survived is why the probe was run -- forcing the reference update changed
  nothing the suite measured, because INV-5's clause stripped spaces from the
  request body and then searched it for a needle carrying a space, so it could
  never match. The red run could not have seen that. Fixed and re-probed.
  Carried out of this item as PRESS-0026: design rule 5 permits this part to
  read and names no write, while fetch-back writes to disk.
  Kind: implement.
  Source: design-2026-08-24 § The parts, ADR-0002.
  Lanes: Publisher.

- ✅ [PRESS-0010] **The Publisher can fetch back a previous state of the repository.**
  Read a previous commit's files back out of GitHub. On its own this is
  not S9: the Store still holds the text that caused the trouble, so his
  next publish would put it straight back. It is deliberately a capability
  rather than a feature, and PRESS-0015 is the sequence that uses it.
  Blocked-by: PRESS-0009.
  Covered by docs/specs/PRESS-0009-publisher.md (2026-08-26), which is an
  umbrella naming both ids per spec-format section 2. This bullet stays its
  own unit of work and closes with the code that spec governs; nothing about
  its scope moves. Section 4.5 and INV-8 are its half of the contract, and
  the user settled its undo semantics on the same day.
  Progress (2026-08-27): its half of the umbrella contract is under test.
  INV-8's two tests -- test_fetch_previous_names_its_source and
  test_first_commit_has_no_previous_state -- are committed red in
  tests/test_publisher.py, against a stub. fetch_previous is unimplemented.
  Resolved (2026-08-27): fetch_previous ships with PRESS-0009, its umbrella.
  It reads the current commit's FIRST parent -- not the branch's second-newest
  commit, which differs as soon as anything is merged -- writes that state
  under the folder it is handed, and names the sha it fetched. A path prefix
  selects and never strips, matched on segment boundaries, so "content" cannot
  also select "contents.html". INV-8's two tests cover it and both mutations
  aimed at them were killed.
  Still only a capability, as the bullet says: PRESS-0015 is the sequence that
  uses it.
  **Layman:** Reads an earlier version of the site back out of GitHub -- half of what undo needs.
  Kind: implement.
  Source: design-2026-08-24 § What undo actually does.
  Lanes: Publisher.

- 📋 [PRESS-0011] **The Face: the local server, and the error contract every message keeps.**
  The standard library's own web server, opening in his normal browser and
  reachable only from his machine.
  Every message says what happened in his words, what it means for his
  site, and what to do next. The middle one is what a technical error
  always omits, and it is what stops him being left unsure whether it went
  out.
  Parts raise typed failures; only the Face turns them into sentences.
  Nothing raw reaches the screen -- anything unforeseen becomes a plain
  apology saying his site has not changed, with a Show details toggle
  holding the technical text and the log's location, for whoever helps
  him.
  A test walks every failure type and fails if one has no sentence, or a
  sentence that omits what it means for his site. Claims S6.
  Blocked-by: PRESS-0001, PRESS-0003.
  Amended by the PRESS-0026 design gate (2026-08-27). This body describes the last-resort message as an apology saying his site has not changed. docs/design.md no longer allows that unconditionally: an unforeseen failure raised after the reference update has landed would be telling him the site is unchanged when it is not. The message now says what it can honestly say -- unchanged where nothing was in flight, outcome unknown where a publish had reached its last step -- and it carries a next-step clause, because the three-part rule has no exception for point 3. The design's Errors section is the contract; build from it rather than from this line. The same gate also corrected the check: the test walks every failure type for all three parts, not for point 2 alone.
  **Layman:** The app opens in his normal browser, and every message tells him what happened, what it means for his site, and what to do next.
  Kind: implement.
  Source: design-2026-08-24 § Errors.
  Lanes: Face.

- 📋 [PRESS-0012] **The editor box, styled as the finished page, with the preview beside it.**
  What he sees is what he gets, because the box renders through the same
  Marks part the Builder uses. Two rendering paths would diverge, and the
  first person to find out would be the writer, after publishing. Claims S10.
  The disk is the truth and nothing is held between requests: he can close
  the app mid-sentence, come back tomorrow, and the draft file is the
  whole of what survives. That is S7 from the writing side.
  Blocked-by: PRESS-0004, PRESS-0005, PRESS-0011.
  **Layman:** He types into a box that already looks like the finished page, so what he sees is what he gets.
  Kind: implement.
  Source: design-2026-08-24 § The parts, § State.
  Lanes: Face.

- 📋 [PRESS-0013] **One button: write, build, publish.**
  The Face owns the order; no lower part calls the next one along. He
  clicks once and within a few minutes it is on the live site, with nobody
  else touching anything. Claims S1.
  When it fails -- no internet, wrong key, GitHub down -- the site is
  unchanged, he is told so in a sentence he understands, and clicking
  Publish again after fixing it works. Claims S6 with PRESS-0011.
  The first publish writes the whole site and is slow; every one after it
  writes a handful of files. Worth saying out loud before he meets it.
  Blocked-by: PRESS-0007, PRESS-0008, PRESS-0009, PRESS-0012.
  **Layman:** He clicks Publish once and his new entry is on the live site a few minutes later, with nobody else involved.
  Kind: implement.
  Source: design-2026-08-24 § What may depend on what rule 1.
  Lanes: Face.

- 📋 [PRESS-0014] **Editing a fixed page: the words in the same box, the code behind a show-me-the-code view.**
  The plain box shows only the page's visible words and writes them back
  in place, leaving every tag around them byte-for-byte as it was. The
  code view edits the file entire. Neither regenerates the page, so Marks
  is not involved in a fixed page at all and nothing he hand-writes can be
  silently reformatted.
  The box offers no styling on a page -- that is done in the code view,
  where the tags already are. It keeps one honest sentence for him: the
  box changes words, the code view changes anything.
  The same code view edits the header, footer and navigation, which is the
  highest-blast-radius edit in the app. So the preview must show a real
  page built with the change before it is published, and Pressless must
  say plainly that editing a header inside a page is wasted work, because
  the next build overwrites it from the single copy.
  Claims S8.
  Blocked-by: PRESS-0006, PRESS-0012, PRESS-0013.
  **Layman:** He can change the wording on his About page himself, and open the page's own code when he wants to.
  Kind: implement.
  Source: design-2026-08-24 § Where the fixed pages live.
  Lanes: Face, Store.

- 📋 [PRESS-0015] **Undo in one step, ending with the site and his own files agreeing.**
  A revert alone is not enough: the Store would still hold the text that
  caused the trouble, so the site would be right for an hour and wrong
  again without him doing anything wrong. Undo is therefore a sequence the
  Face owns -- fetch the previous state, write its content/ back into the
  Store, rebuild, publish.
  He can see for himself that it is back. Drafts are untouched, since they
  were never in the repository to fetch back, so an unfinished poem can
  never be lost to an undo.
  Offered in the same breath as the edit rather than found later in a
  menu. Claims S9.
  Blocked-by: PRESS-0010, PRESS-0013.
  **Layman:** After a change that made the site wrong, one step puts it back -- and he can see that it worked.
  Kind: implement.
  Source: design-2026-08-24 § What undo actually does.
  Lanes: Face.

- 📋 [PRESS-0016] **Photographs, from the picture mark to the web-sized copy.**
  A picture mark naming the file, with an optional caption, so the cheat
  sheet generates it like every other mark.
  The Store keeps the original in Pressless's own folder, never in the
  site folder: originals are never modified and never published, and the
  existing ones would not fit under GitHub Pages' size limit anyway. The
  Builder writes the web-sized copy and owns its naming rule; Marks
  renders the address from that rule without touching a disk.
  The preview shows the original scaled in the browser, so a photograph in
  an unbuilt draft is visible at once rather than a broken image. That is
  what S10 asks for.
  Pillow is already proven by resize.py in the sibling workspace.
  Blocked-by: PRESS-0004, PRESS-0008, PRESS-0012.
  **Layman:** He can put a photograph in an entry, and it is shrunk for the web without his originals ever being touched.
  Kind: feature.
  Source: design-2026-08-24 § Where photographs live.
  Lanes: Marks, Store, Builder, Face.

- 📋 [PRESS-0017] **Starting something new picks from a list of templates.**
  A poem, a lyric with verses, an entry built around one photograph, a
  plain journal entry. Picking one copies its text into a new draft.
  Templates are Store files in the same marks as everything else, so he
  edits one in the same box and adds his own. Nothing in the parts changes
  to support them, which is the test that this is the right shape rather
  than a feature.
  They retire COPY-ME-new-page.html as a way of working. The file itself
  stays on the site: it is untouchable, so the Publisher never removes it.
  Blocked-by: PRESS-0006, PRESS-0012.
  **Layman:** New entries start from a shape he chooses -- a poem, a lyric, an entry around a photograph -- rather than an empty box.
  Kind: feature.
  Source: design-2026-08-24 § A template is an entry he never publishes.
  Lanes: Store, Face.

- 📋 [PRESS-0018] **The cheat sheet is generated from the same table the app parses with.**
  The in-app panel and the printable page, both generated from Marks' one
  table. Neither is written by hand: a hand-written card drifts the first
  time a mark changes, and then it teaches him something that does not
  work.
  Blocked-by: PRESS-0004, PRESS-0011.
  **Layman:** The card telling him how to write bold or a colour is made from the app's own rules, so it can never be out of date.
  Kind: implement.
  Source: design-2026-08-24 § Where the cheat sheet comes from.
  Lanes: Marks, Face.

- 📋 [PRESS-0019] **Insights asks Google Analytics how the site is being read.**
  The live property already on the site, through Google's reporting
  interface, handing back plain numbers: how many people, and which
  countries. Province was dropped -- what was asked for is visits by
  country.
  It may read Settings and talk to Google, and nothing else. Nothing about
  writing or publishing may depend on it, so if Google is unreachable, or
  he never sets it up at all, everything else still works (ADR-0005).
  It keeps the one cache in Pressless, because Google limits how often it
  will answer: the last reply with the time it was fetched. Deleting that
  file costs nothing but a fresh fetch.
  Blocked-by: PRESS-0001, PRESS-0002.
  Blocked (2026-08-25) on the same design.md decision as PRESS-0009, by
  rule 8 rather than rule 5: this part may read Settings and talk to
  Google and nothing else, and the Google authorisation lives in the
  separate credentials module described by
  docs/specs/PRESS-0002-credentials.md. That contract is written and
  accepted; what is missing is permission for this part to call it.
  Section 11 of that spec records the two routes and picks neither.
  Note the authorisation is optional per ADR-0005, so whichever route is
  taken must still let a writer decline the dashboard and lose nothing
  else.
  Routing decided 2026-08-25 (user deferred the choice): the Face fetches
  the secret from the credentials module and hands it to Insights as an
  argument. Design rules 5 and 8 are NOT widened -- see PRESS-0009 for the
  reasoning. Still blocked until docs/design.md carries the amendment and
  that amendment passes its cold-eyes gate.
  Progress (2026-08-25): UNBLOCKED. The docs/design.md decision this waited on
  is made -- rule 10 has the Face fetch the Google authorisation and hand it
  to Insights as an argument, so rule 8 stands unchanged and Insights stays
  testable without a real keyring. Two things to settle before building: rule
  8 now names the one cache file explicitly, and WHICH Analytics identifier
  Settings holds is open -- the reporting interface is queried by a numeric
  property id, the footer tag carries a G- measurement id, and the shipped
  field is named analytics_measurement_id. Passing the wrong one fails every
  fetch.
  Settled (2026-08-26) by the user: Settings holds the NUMERIC property id, and no measurement id. The field is renamed analytics_property_id across the module, its tests and PRESS-0001; docs/design.md's two-identifier bullet records the decision. Pressless never writes the site's footer tag, so it has no use for the G- form. This item's remaining blocker is gone -- it is startable.
  **Layman:** Fetches the visitor numbers Google already collects for his site, and hands back how many people and which countries.
  Kind: implement.
  Source: design-2026-08-24 § The dashboard, ADR-0005.
  Lanes: Insights.

- 📋 [PRESS-0020] **The dashboard, with flags as bundled pictures rather than flag characters.**
  He opens Pressless and sees how many people read his site and which
  countries they came from, each country shown with its flag, without
  logging in to anything and without leaving the app. Claims S11. The
  dashboard says when the numbers were last updated.
  Windows has no glyphs for flag emoji and draws the two letters instead.
  It looks right on the Linux machine this is built on and wrong on the
  only machine he uses, so a small set of flag images ships with the
  app, keyed by country code.
  Measured 2026-08-25 on a Windows 10 22H2 box over SSH, in Chromium 151:
  the flag sequence renders identically to its two letters forced apart,
  while a control emoji rendered normally. So it is flags specifically
  that are missing, and the images are needed rather than merely prudent.
  Blocked-by: PRESS-0011, PRESS-0019.
  **Layman:** He opens Pressless and sees how many people read his site and which countries they came from, each with its flag.
  Kind: feature.
  Source: design-2026-08-24 § The dashboard.
  Lanes: Face.

- 📋 [PRESS-0021] **Setup asks for the publishing key once; the dashboard's second step can be declined.**
  He is asked for his publishing key exactly once, during setup, and never
  sees it again in normal use. Claims S5.
  Reading Analytics is a separate Google authorisation, so setup grows a
  second step -- and the dashboard is the one feature whose setup he can
  decline and lose nothing else by declining.
  Setup is also where the untouchable list is derived from the live
  repository, and where Import runs, once.
  Blocked-by: PRESS-0002, PRESS-0007, PRESS-0011, PRESS-0019.
  **Layman:** He pastes his publishing key in once when he first runs Pressless, and never sees it again.
  Kind: implement.
  Source: design-2026-08-24 § The dashboard, ADR-0003.
  Lanes: Face, Settings.

- 📋 [PRESS-0022] **One double-clickable file per system, built by CI from the first release.**
  PyInstaller packages Pressless into one file per system. It does not
  cross-compile, so the Windows file must be produced by a Windows runner:
  releases go through GitHub Actions from the very first one, not later
  (ADR-0004). The repository is public, so the minutes cost nothing.
  The written install steps must be the same on Windows and on Linux apart
  from which file is double-clicked. Claims S4.
  The built executable is staged to a Windows test box over SSH and run
  there before release, so his double-click is not its first exercise.
  That box has no Python installed and must not be given one: a machine
  with an interpreter cannot show that the executable carries everything
  it needs, which is the whole of S4.
  Blocked-by: PRESS-0013.
  Layman: Pressless installs on Windows by following the same steps as on Linux, apart from which file is double-clicked.
  Progress (2026-08-25): the packaging shape is decided with the user.
  Linux ships one AppImage. Windows ships a zip that is extracted and
  run. So this bullet's headline is now true of Linux only, and the
  Windows install gains an extract step that Linux does not have --
  which is a departure from S4 as discovery words it, and needs
  settling there rather than here.
  Pressless's own folder is created BESIDE the program file, never
  under the home directory. It holds drafts, photograph originals and
  the log, so on a small system drive the default location is the
  wrong one; choosing where the AppImage sits is how the drive gets
  chosen.
  An AppImage runs from a temporary read-only mount, so the running
  process's own path is not the AppImage's path. Finding the file's
  real location is a step of this item and must be verified against a
  built AppImage. It could not be verified from the sources on this
  machine and is therefore not recorded as a fact anywhere.
  Where that folder cannot be created -- a read-only or unwritable
  location -- Pressless stops and says so, in the three-part form the
  design requires. It must never fall back to the home directory
  silently: that fills the drive this rule exists to protect, and
  nobody would see it happen.
  Correction (2026-08-25): the note above says the AppImage's own path
  could not be verified from the sources on this machine. It can be, and
  now is. The sibling project finbreak ships an AppImage updater that
  resolves it from the `APPIMAGE` environment variable, and its
  `tests/features/auto_update/spec.md` pins the behaviour both ways --
  with the variable unset, the feature detects no installer and turns
  itself off. So the mechanism is sourced from working code rather than
  assumed, and the open question is closed.
  Windows is a zip that is extracted and run, which also settles what the
  data folder sits beside there: the extracted folder, not an installed
  program. PRESS-0023 depends on this item and its Windows half differs
  from finbreak's for the same reason.
  Deferred from the docs/design.md gate, 2026-08-25 (loop 6, filed not fixed).
  The design says Pressless's own folder sits beside the program file, and that
  folder holds all his writing, the drafts nothing backs up, the settings file
  and the fallback credential file. Every release ships a NEW artefact
  (ADR-0004), and the design never says what happens to the old folder. Resolve
  it as part of this item: the folder moves with the program, or Pressless
  finds and migrates a previous one, or setup detects an existing one and
  offers it. Left unresolved, a writer who unzips version 2 somewhere else gets
  a first-run setup, no writing, and unbacked-up drafts stranded beside the old
  artefact. PRESS-0001 section 4.5 already assumes the opposite is handled.
  Shape decided by the user (2026-08-26), and it is NOT one file per
  system. Linux gets a single AppImage, which keeps its settings beside
  itself where it is run from rather than under the home directory --
  the system drive is short of space, which is the reason. Windows gets
  a ZIP holding the app plus a batch file that starts it; the writer
  extracts it and double-clicks the batch file. So this item's headline
  overstates Windows: two artefacts, one shape each, not one shape twice.
  docs/design.md § The stack and ADR-0004 both say one artefact per
  system and need the amendment before this is built -- a direction
  change, so that amendment owes its own cold-eyes gate.
  Kind: package.
  Source: design-2026-08-24 § The stack, ADR-0004.
  Lanes: Packaging.

- 📋 [PRESS-0023] **Pressless updates itself, and installs nothing it cannot prove we signed.**
  Asked for by the user 2026-08-25. Modelled on the sibling project
  finbreak, which ships this and has already paid for the mistakes: read
  `tests/features/auto_update/spec.md` there before designing anything, and
  the modules it names under `src/finbreak/services/`.

  What to carry across, and why each one is not optional:

  The download is verified against an Ed25519 signature before it is
  installed, and a tampered blob or signature installs nothing. An updater
  without this is a way to run someone else's code on his machine. The
  private key never enters the repository, and a test scans for one.

  Network access lives in a single module, with a test that fails if any
  other module imports a network library. The design already forbids Marks
  and the Builder from touching the network; this is how that stays true
  once an updater exists.

  On Linux the AppImage is swapped in place, staging the temporary file on
  the same filesystem so the replace is atomic. finbreak finds the running
  AppImage through the `APPIMAGE` environment variable -- which is also the
  answer PRESS-0022 needs, and it is now sourced rather than assumed.

  The relaunch spawns a detached process and exits; it must not re-exec in
  place. finbreak hit exactly that bug between two releases and the app
  closed without reopening.

  Windows cannot overwrite its own running program, so the swap happens
  out of process after Pressless exits. Our Windows build is an extracted
  folder rather than one file, so what gets replaced differs from
  finbreak's and the shape needs deciding.

  A failed check is silent and changes nothing. A failed verification is
  shown, in the three-part form the design requires, and leaves the
  installed version alone.

  Two things are open and are not decided here: whether updating is on by
  default -- finbreak's is off, and its user is technical, which he is not
  -- and what he is offered besides Update now.

  Blocked-by: PRESS-0022.
  Milestone: v0.5.0. It rides with the Publisher and the one button,
  because that is when he starts using Pressless daily and a fix needs a
  way to reach him. The hop from v0.1.0 to v0.5.0 is therefore the one
  download he still does by hand, and every hop after it is automatic.
  Recorded here rather than in the Milestones section because that
  section's intro is store-owned prose and no verb amends it -- so its
  sentence naming the item count was already stale when this item was
  filed, and could not be corrected. Filed as Ants MCP feedback.
  **Layman:** Pressless tells him when there is a newer version and installs it for him, so he never has to download anything again.
  Kind: feature.
  Source: user-request-2026-08-25.

- ✅ [PRESS-0024] **The pre-push hook reads as a safety net and gates nothing.**
  Measured 2026-08-25 while checking this project is still a correct
  instance of the skeleton. `core.hooksPath` is `.githooks`, all three
  hooks are executable, and `commit-msg` genuinely refuses a bad subject
  (probed: exit 1). But `pre-push` prints "no local gate found, and no
  pipeline to gate -- nothing to run" and exits 0 on every push, because
  this repo has no CI workflow and no gate script.

  Why it matters more than it looks: the suite here is fast and the
  archive run -- the proof of S2 -- is skipped unless PRESSLESS_ARCHIVE is
  set, so a green CI run would be silent about the most important
  invariant even if CI existed. The one machine that can run it is the
  maintainer's, which is exactly where pre-push fires. A hook that ran
  `python3 -m pytest` with the archive path when that file is present
  would turn the strongest available check into an automatic one.

  Not urgent, and deliberately not done in the session that found it:
  nothing has been published that the missing gate would have caught. The
  risk is the opposite one -- the hook LOOKS like protection, so a future
  session may trust it.
  Blocked-by: nothing.
  Resolved (2026-08-26): scripts/local-ci.sh holds the checks and
  .github/workflows/ci.yml calls that same file, so the local run and
  GitHub cannot drift. The gate sweeps the three surfaces a push
  publishes -- tree, every commit's files, commit messages -- then lints
  and runs the suite; --docs runs the sweep alone, since no test here
  reads a document. Proven by planting a name in a staged file: exit 1,
  naming the surface. The archive run this bullet asked for is wired
  through a machine-local config key, so the export path stays out of the
  public repository and the suite reports nothing skipped here. First
  GitHub run green.
  **Layman:** The check that runs before publishing now really runs the tests, instead of quietly doing nothing.
  Kind: chore.
  Source: in-session-2026-08-25.

- 🚧 [PRESS-0025] **CLAUDE.md records a roadmap limitation that has since been fixed.**
  § "A corrected `Layman:` cannot be put back the way it was" is stale.
  Measured 2026-08-26: `roadmap_log op:amend_field` shipped that day
  (ANTS-4667) and sets the layman column directly; on the four bullets
  that declare `Layman:` in their own body it refuses with
  `field_shadowed_by_body` and NAMES the route, `op:amend_body`, which
  edits the declaration in place. Both were exercised, one for real
  (PRESS-0024) and one as a dry run (PRESS-0001).

  What is still true is the one-way half: a body declaration cannot be
  converted back to a column, so the two styles still coexist and
  reconciling them is still not worth attempting. The section should be
  narrowed to that, not deleted.

  Not done in the session that found it because it changes an
  instruction -- CLAUDE.md rule 14 -- so it re-arms that file's own
  cold-eyes gate and deserves the gate rather than a quiet edit.

  Two machine-local git config keys are also undocumented and are lost
  on a fresh clone: `ants.gate.docsGlob` (unset, the pre-push hook then
  falls back to a list commits.md § 4.2 forbids) and
  `ants.pressless.archive` (documented in § Build and test, so only the
  first is missing). Fold the first into the same edit.
  Blocked-by: nothing.
  Started 2026-08-27. One correction to this bullet before the work: ants.gate.docsGlob is no longer unset -- it now reads docs/*|*.md|LICENSE|*.txt|*.rst, which is the hook's own fallback value. commits.md § 4.2 objects to a hook GUESSING by extension when nobody has told it, so the key being set satisfies the letter, and the value is right here for the reason CLAUDE.md now records rather than this bullet. What is still owed is the documenting: the key is machine-local and lost on a fresh clone.
  **Layman:** A note in our own instructions says something cannot be done, which can now be done.
  Kind: doc-fix.
  Source: in-session-2026-08-26.

- ✅ [PRESS-0026] **Design rule 5 should name the Publisher's one write.**
  Rule 5 reads that the Publisher may read Settings and a folder of
  finished files, and nothing else -- it names no write. Rule 8 shows the
  form the design already uses when a part writes, naming Insights' one
  cache file explicitly.

  fetch_previous writes a fetched state into a folder it is handed, so
  rule 5 as written does not cover it. That section is what the
  pick-an-item gate reads, so the gap is load-bearing rather than
  cosmetic.

  Surfaced by the PRESS-0009 spec gate rather than fixed there: it is
  another document's rule, and changing direction in a contract document
  owes its own review-contract gate. Filed here so it did not leave the
  roadmap when PRESS-0009 closed.

  Blocked-by: nothing. The code it describes is already shipped, so this
  is the document catching up.
  Started 2026-08-27. Scope confirmed with the user: this item alone. PRESS-0022's packaging amendment edits a different section of the same document and also needs ADR-0004, so it keeps its own gate rather than folding in here.
  Resolved (2026-08-27). Rule 5 now names the Publisher's write, in rule 8's form: it may read Settings and a folder of finished files, may read and write GitHub, and writes to disk only into a folder it is handed. The fetched state's home is named in the disk table -- the fetch area inside Pressless's own folder, never the site folder.

  The gate ran three loops and reached the ADR cap. It found that the first attempt made things worse: naming only the local write turned an omission into an exhaustive write list that excluded the Publisher's principal write to GitHub. All three lanes found that independently.

  Eighteen defects were verified and fixed across the run, most of them pre-existing rather than introduced here. Four items were filed rather than fixed: PRESS-0028, PRESS-0029, PRESS-0030, PRESS-0031. The cap was violent -- two thirds of the last loop landed on text the run itself wrote -- so the document is not re-gated as it stands.
  **Layman:** A design rule says the publishing part only reads things; it now also writes one folder, so the rule needs to say so.
  Kind: doc.
  Source: PRESS-0009 spec section 11, surfaced 2026-08-26 and not applied.

- 📋 [PRESS-0027] **The suite runs in a different order here than in CI.**
  pytest-randomly is installed on the maintainer's machine and auto-loads,
  so the suite runs in a random order here. CI installs only the dev extra
  -- pytest and ruff -- so it runs in file order. The gate script is shared
  and cannot drift, but the plugin set underneath it does.

  Random order is the better check: it is what catches a test that only
  passes because an earlier one ran first. The defect is that nobody chose
  it. A failure here may not reproduce there, and vice versa, and the
  seed is not recorded anywhere.

  Two ways out, and they are opposite: declare pytest-randomly in the dev
  extra so CI randomises too, or pin the order for both. Declaring it is
  the better one -- it makes the stronger check the shared one -- and it
  costs a dependency the packaged artefact never sees, since the dev extra
  is not a runtime dependency.

  Noticed because a subagent reported test order varying between two runs
  and the claim was checked rather than taken.

  Blocked-by: nothing.
  **Layman:** Tests run in a random order on the maintainer's machine and a fixed order on GitHub, so a failure in one place may not show up in the other.
  Kind: test.
  Source: observed while implementing PRESS-0009, 2026-08-27.

- 📋 [PRESS-0028] **S6 is stated absolutely in discovery, and the system admits one case.**
  docs/discovery.md S6 reads that he is never left unsure whether it went
  out. The PRESS-0009 spec settles the exception: a failure during the
  reference update is the one case where the site's state is genuinely
  unknown, and confirming it would mean reaching GitHub, which is by
  definition what has just failed. docs/design.md now says the same after
  this gate.

  So the sign of success is the only document left stating it absolutely.
  That matters because a sign of success is what delivery is checked
  against: as written, S6 either cannot be met or is met by a sentence
  that contradicts it.

  Amending a sign of success is a policy choice rather than a wording fix,
  and discovery.md owes its own gate, so this was filed rather than
  applied.
  **Layman:** One promise says he is never left guessing whether his site went out. There is a single failure where nobody can tell, so the promise needs to say so.
  Kind: doc.
  Source: PRESS-0026 design gate 2026-08-27, loop 7, filed not fixed.
  Lanes: Publisher, Face.

- 📋 [PRESS-0029] **ADR-0005's Decision forbids the cache its own Consequences grant.**
  The Decision paragraph reads that Insights may read Settings and talk to
  Google, and nothing else. Its own last Consequence calls Insights the one
  part allowed a cache, and docs/design.md rule 8 grants it one cache file
  by name.

  A builder reading the Decision alone builds no cache, and Google's rate
  limit is the reason the cache exists.

  Found by a lane during the PRESS-0026 design gate. Not carried into
  design.md, which is already correct; ADR-0005 is a contract document with
  its own gate ahead of it.
  **Layman:** One decision record contradicts itself about whether the dashboard may keep a saved copy of Google's answer.
  Kind: doc-fix.
  Source: PRESS-0026 design gate 2026-08-27, loop 7, lane finding on a cross-reference.
  Lanes: Insights.

- 📋 [PRESS-0030] **Nothing says which part builds the preview page.**
  docs/design.md requires the preview show a real page built with the
  change before it is published -- the promise that makes a footer edit
  safe, and it calls that the highest-blast-radius edit in the app. The
  same document has the preview show a photograph's original scaled in the
  browser, which is a Face-rendered view rather than a built page.

  Rule 1 lets the Face call the Builder and rule 2 requires only shared
  Marks, not shared page assembly, so the dependency rules settle neither.

  An implementer who invokes the Builder gets real page furniture and a
  write into the site folder that the next publish then carries. One who
  assembles inside the Face gets originals inline and writes nothing. Only
  the first keeps the real-page promise.

  Filed rather than fixed: choosing between them is a design decision, and
  whether a preview build writes into the site folder changes what publish
  sends.
  **Layman:** Before he publishes, Pressless shows him the page. Nobody has decided which part of the app makes that page, and the two answers behave differently.
  Kind: investigate.
  Source: PRESS-0026 design gate 2026-08-27, loop 8, stop condition -- needs a decision.
  Lanes: Face, Builder.

- 📋 [PRESS-0031] **Undo has no stated answer for an edit made since the last publish.**
  Undo is sourced entirely from the repository: fetch the previous state,
  write its content/ back into the Store, rebuild, publish. Persistence
  keeps one file per entry, renamed over the old one, so no local prior
  version exists.

  fetch_previous reads the current commit's first parent. So for an entry
  edited but not yet published, undo overwrites the unpublished text with
  the state before the last publish -- and the design says an undo deletes
  nothing of his, which is then false for exactly that entry.

  The gate narrowed the recoverability claim to published edits, which is
  what S9 itself is scoped to. What it did not do is decide the behaviour:
  undo could refuse while unpublished edits exist, keep them beside the
  fetched text the way it keeps a fixed page, or warn and proceed.

  Filed rather than fixed: the document cannot state a behaviour nobody
  has chosen.
  **Layman:** Undo brings the site back to how it was. If he changed something and has not published it yet, nobody has said what undo does to that change.
  Kind: investigate.
  Source: PRESS-0026 design gate 2026-08-27, loop 8, stop condition -- needs a decision.
  Lanes: Face, Store.

## Milestones

A version number here says WHICH OF THE ELEVEN SIGNS OF SUCCESS HOLD, not how
many items are done. `docs/discovery.md` § Signs it is working owns S1-S11.
Every one of the 22 items above belongs to exactly one milestone below, and none
belongs to two. Agreed with the user 2026-08-25.

**v0.1.0 - twelve years survived.** PRESS-0001, 0003, 0004, 0005, 0006, 0007,
0008, 0011, 0022. He installs the packaged file, points it at the WordPress
export, and looks at his whole archive rendered on his own machine. There is no
Publisher yet, so nothing can reach the live site: the one irreversible step,
Import, is exercised while the stakes are zero. Holds S2, S3, S4. Deliberately
read-only - the editor box waits for v0.5.0 so that he never has a box that
writes to nowhere.

**v0.5.0 - he publishes without a phone call.** PRESS-0002, 0009, 0010, 0012,
0013, 0015, 0021. Adds the keyring, the Publisher, undo in one step, the editor
box, the one button and setup. Holds S1, S5, S6, S7, S9, S10. This is the
version that does the thing the project exists for. It is 0.5 rather than 1.0
because it has been used by one person for a week, not a season.

**v1.0.0 - all eleven, and the format is frozen.** PRESS-0014, 0016, 0017, 0018,
0019, 0020. Adds fixed pages, photographs, templates, the cheat sheet and the
dashboard. Holds S8 and S11, so all eleven hold. What actually makes it 1.0
rather than 0.9 is the promise attached to it: an entry file written by 1.0
stays readable by every later version. Before 1.0 the on-disk format of ADR-0001
may still change; after it, S3 stops being a design intention and becomes a
compatibility guarantee.

**Every release is built by CI, including the first.** ADR-0004: PyInstaller
does not cross-compile, so `Pressless.exe` can only be produced by a Windows
runner, and S4 cannot be demonstrated without one. That is why PRESS-0022 sits
in v0.1.0 rather than at the end - packaging is not the last step, it is the
first release's precondition.
