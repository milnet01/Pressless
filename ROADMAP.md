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

- ✅ [PRESS-0005] **The Store: one file per entry, with drafts kept apart from published.**
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
  Progress (2026-08-27): contract accepted at
  docs/specs/PRESS-0005-store.md. Two cold-eyes loops to the spec cap,
  three lanes each, 22 verified findings all fixed. Status stays planned
  -- no code yet.
  Resolved (2026-08-28): src/pressless/store.py, with
  tests/test_store.py and tests/test_store_archive.py. All ten invariants
  green. The whole archive round-trips with no field changed.
  mutation_probe killed nine of ten routes; the survivor is the
  file-name-against-Slug-header gap the spec's own coverage table already
  records as covered by nothing.
  **Layman:** Every entry is an ordinary text file in an ordinary folder, openable in Notepad, and unfinished ones are kept off the web.
  Kind: implement.
  Source: design-2026-08-24 § Persistence, § Where everything sits on disk.
  Lanes: Store.

- ✅ [PRESS-0006] **The Store also holds the fixed pages, the page furniture, the templates and the historical comments.**
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
  Progress (2026-08-31): spec accepted at
  docs/specs/PRESS-0006-pages-furniture-comments.md. Two cold-eyes loops,
  21 verified findings, all fixed; the run reached the spec cap of 2 and
  the tail is empty. Two decisions worth knowing before building. The
  comments file is JSON in a folder of its own rather than text beside the
  entry, because a comment body may hold any line and a delimiter would
  need inventing; replies are preserved, and the export spells a top-level
  parent `0` where the Store wants it empty. And this spec settles only
  WHERE a photograph's original sits -- loop 2 withdrew the naming rule to
  PRESS-0016 after measuring that most of the archive's attachment names
  cannot satisfy a slug. Status is not flipped: a spec being accepted is
  not work having started.
  Resolved (2026-09-02). Twelve calls added to src/pressless/store.py, not
  a second module -- they share the name rule, the atomic write, the error
  types and the folder handle with the entry code. Three pieces of that
  code are now shared rather than copied: the slug rule, the entry
  serialisation and the atomic write, so a template is written by the same
  code that writes an entry. write() lost 39 lines with its behaviour
  unchanged.

  Eleven invariants in tests/test_store_extras.py, proven red against a
  stub before the code existed. The conformance run writes all 78 of the
  archive's real comments through the Store and reads them back: 0 fields
  changed, all 18 replies resolve, and no email address or IP address the
  export carries reaches a file the Store writes.

  Probed after the code landed: 14 mutants, one per route the invariants'
  own Breaks-when clauses name, 13 killed. Two gaps the probe found are
  closed here rather than filed. INV-10 could not fail on Linux at all --
  os.linesep is LF, so a write leaving the newline to the platform produces
  the same bytes as one naming it, and newline=None survived the byte
  assertions; the test now also asserts what the Store named at the open,
  and test_store.py's open-watcher moved to tests/_open_watch.py so both
  files share one. INV-11 had no backslash case, so dropping that guard
  survived; a backslash is one name on Linux and two on Windows.

  The surviving mutant is os.path.basename's guard in photograph_path_for
  -- redundant on Linux given the two separator checks, load-bearing on
  Windows for a drive-relative name, and unreachable by any test here.

  The name rule was run over the archive's own 193 attachment names and
  refused none, which is the evidence for decision 10 that a slug rule
  could not have been met by the files it was written for.
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
  Progress (2026-08-28): PRESS-0005's archive run found one slug wanted
  by two entries -- a published entry, and a draft with no slug whose
  post-id fallback resolves to the same string. They land in different
  folders, so the Store loses neither, but Import has one address for two
  entries and must stop rather than overwrite. Deciding which entry keeps
  the slug is this item's. PRESS-0005 §3 decision 5 said nothing in the
  archive collides; that claim is now corrected.
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

- ✅ [PRESS-0019] **Insights asks Google Analytics how the site is being read.**
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
  Started (2026-08-27). No spec: spec-format.md § 1's test comes back no -- one subsystem, and design rule 8 forbids anything depending on Insights, so a wrong shape is cheap to undo. Google's reporting surface verified against its own reference rather than recalled: countryId is ISO 3166-1 alpha-2, which is what the flag lookup binds to; activeUsers is the metric; the total is asked for rather than summed, because a visitor seen in two countries is counted in both rows.
  Resolved (2026-08-27). src/pressless/insights.py, one entry point, no new
  dependency. Sixteen invariants locked in tests/test_insights.py, proven red
  against a stub before the code existed and then probed: nine mutations, one
  per route the invariants name, all nine killed against a verified green
  baseline. Decisions taken here rather than left implicit -- the token is an
  argument and setup owns refreshing it, so design rule 10 stays literally
  true; the window is a parameter defaulting to four weeks; a failed refetch
  answers from the cache with the reply marked stale rather than raising,
  which is what the dashboard's own "as of" line makes safe.
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

- 🚧 [PRESS-0022] **One double-clickable file per system, built by CI from the first release.**
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
  Progress (2026-09-02): chosen by the user as the next block of work,
  over writing the Setup spec and over finishing the rest of PRESS-0067.
  Nothing is started.

  The reason it was chosen, which is the reason to keep it next: it is
  the only item that turns the Windows test box into EVIDENCE. Nothing
  can run there today — the box deliberately has no Python, which is what
  makes it a fair test of a packaged artefact — so every Windows claim
  this project has made so far is reasoned rather than measured. Three
  items shipped today (PRESS-0047, and PRESS-0067 items 2 and 3) address
  Windows-only defects that no test here can execute; PRESS-0005 § 10
  carries a row saying so.

  Treat a difference in behaviour between Windows and Linux as a defect
  rather than a platform nuance. That is a standing priority, not a
  judgement call per item.

  Inherit before starting: PRESS-0068 item 1. Every keyring backend is
  discovered through the keyring distribution's entry-point metadata, and
  a PyInstaller bundle that does not collect it registers NO backend — so
  the probe raises and Pressless tells EVERY Windows user their machine
  has no credential store. The discriminator cannot tell "no metadata"
  from "no store". The fix belongs to this item: --copy-metadata keyring,
  plus pywin32-ctypes. That item records it here for exactly this reason.
  Progress (2026-09-02, second note): prerequisites checked before
  planning. Nothing built.

  The design amendment this item says is owed has ALREADY LANDED, so the
  note above is stale. docs/design.md § The stack names an AppImage on
  Linux and a zipped extracted folder on Windows; § Where everything sits
  on disk carries the beside-the-program-file rule and resolves the Linux
  path through the APPIMAGE variable; ADR-0004 § Decision names both
  shapes. That text sits inside a document gated to its cap, so rule 14
  is discharged and this item is not waiting on it.

  Recorded nowhere but here: the batch file. The decision gives Windows a
  zip holding the app plus a batch file the writer double-clicks. Neither
  document mentions it, and it is the whole of what S4 asks a Windows
  user to do.

  Blocked-by PRESS-0013 is real and measurable, not bookkeeping. The
  package holds library modules only -- no entry point, no project
  scripts table, no Face. There is nothing to package into a
  double-clickable file today, and PRESS-0013 is itself blocked by four
  items. The CI workflow runs the gate alone; no release build exists.

  It NEEDS a spec. spec-format.md § 1 is hit three ways: a new on-disk
  shape that is hard to reverse, a real design choice this item's own
  body defers into it (what becomes of a previous data folder when a
  release ships a new artefact), and a contract PRESS-0001 already
  assumes.
  Two decisions taken by the user (2026-09-02), both changing what this
  item builds:

  1. Build the packaging pipeline NOW, against a deliberately minimal
     program, rather than waiting for PRESS-0013. That program starts,
     resolves where its own folder goes, probes the credential store and
     reports what it found. It is a real double-clickable artefact, so
     the Windows box can answer the three questions packaging exists to
     answer: does the bundle carry what it needs, does the Windows
     credential store work through it, does the folder land beside the
     artefact. The Face replaces the placeholder when PRESS-0013 lands.
     The Blocked-by therefore constrains when this item can be CLOSED,
     not when it can be started.

  2. A new version does not migrate anything. The written install steps
     say to extract over the old copy, so the folder is already beside
     the new artefact. Nothing is remembered outside the app and nothing
     is moved. The residual risk is accepted and must be stated to the
     writer rather than engineered away: extracting elsewhere gives a
     first-run setup with the drafts stranded beside the old artefact,
     and drafts are the one thing nothing backs up. This closes the
     question deferred here from the design gate.
  Started (2026-09-02): writing the packaging spec, per the two
  decisions above.
  Spec accepted (2026-09-02): docs/specs/PRESS-0022-packaging.md.
  Two cold-eyes loops, three lanes each, 22 verified findings, all fixed,
  none deferred. The run reached the spec cap of 2 and the cap was
  VIOLENT -- about ten of loop 2's twelve landed on text loop 1 wrote --
  so the document is routed to implementation rather than a third gate.

  What the spec settles, so it is not re-litigated: one-folder freezes on
  both systems, wrapped as an AppImage on Linux and zipped with a batch
  file on Windows; a new paths.py resolving the folder beside the
  artefact, injected downward and never imported by Settings or
  Credentials; a release workflow whose Windows job runs the suite, which
  ADR-0004 requires and which is what finally puts this project's tests
  on a Windows machine; and a self-check whose output shape and exit rule
  are pinned, because three things bind to them.

  Still open for the user, in section 15: whether Pressless-data is the
  right name for the folder he will see, and whether Windows needs the
  batch file at all now that one-folder puts the executable at the top of
  the extracted folder.

  Not started: no code, no workflow, no tests. Nothing in section 4 is
  built.
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

- ✅ [PRESS-0025] **CLAUDE.md records a roadmap limitation that has since been fixed.**
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
  Resolved (2026-08-27). The Layman: section is narrowed to the half that is still true, with both branches measured rather than asserted -- amend_field writes the column, refuses field_shadowed_by_body on a body-declared bullet and names amend_body; deleting the declaration is refused with render_gate_unmet. ants.gate.docsGlob is documented, together with core.hooksPath, which was the undocumented key that actually decides whether any hook fires.

  The gate ran three loops to the standard cap and found fifteen defects, five of them in the edit this item made. The most consequential was not in that edit: the documented history sweep used git grep -l, which prints no matched line, so the rule that tells a reader which hits are expected could not be applied to it -- a real historical leak in CLAUDE.md or the gate script would have read as the self-reference. Fixed to the script's form; all three documented sweeps re-run clean as written.

  PRESS-0032 filed rather than fixed: the gate script's own history pass runs a narrower pattern than its other two.
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

- ✅ [PRESS-0027] **The suite runs in a different order here than in CI.**
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
  Resolved (2026-08-31): took the bullet's own better option and
  declared the plugin in the dev extra, so the stronger check is the
  shared one. CI installs that extra, so both sides now randomise, and
  the seed printed in the run header reproduces any failure. The order
  dependence this could expose was looked for before declaring it --
  five seeds without the archive and two with it, all green. CLAUDE.md's
  list of what the gate needs named two tools and now names three.
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

- ✅ [PRESS-0032] **The leak sweep's history pass covers fewer identifiers than its other two.**
  scripts/local-ci.sh runs three leak surfaces. The tree and commit-message
  passes are fed the full five-fragment pattern. The history pass runs
  `git grep` over every revision with the three-fragment subset, and only
  the lines that pass finds are re-matched against the full pattern -- so a
  fragment outside the subset is never surfaced from history at all.

  Confirmed by execution 2026-08-27: the three-fragment pattern does not
  match the analytics id, so a commit whose files carried only that id
  would go unreported by the history pass while the tree pass would catch
  it in the working tree.

  This may be deliberate -- walking every revision with a wider pattern is
  the most expensive of the three passes, and the name fragments are the
  higher-value subset. Nothing records that reasoning either way, which is
  the actual defect: a narrowing nobody wrote down is indistinguishable
  from an oversight.

  Decide it, then either widen the history pattern or say in the script why
  it is narrower. The documentation half was fixed in the same gate --
  CLAUDE.md's hand-run history command used `git grep -l`, which prints no
  matched line, so the "only expected hits are the pattern lines" rule
  could not be applied to its output.

  Blocked-by: nothing.
  Resolved (2026-08-31): decided by measurement rather than by
  argument. The wide and narrow patterns time the same over this
  repository's revisions, so the expense that would have justified a
  deliberate narrowing does not exist, and the history pass now
  searches the same pattern as the other two. The fix was proved in a
  throwaway repository: a revision adding the analytics id, followed by
  one deleting the file, is invisible to both the tree pass and the old
  history pass and is caught by the new one. SELF is no longer a second
  search pattern -- only the self-exclusion literal it was already used
  as. CLAUDE.md's hand-run command carried the same narrowing and was
  widened with it.
  **Layman:** The check that stops private details reaching the public site looks for five things in today's files and only three in the older ones.
  Kind: security.
  Source: CLAUDE.md gate 2026-08-27, loop 3, code-side finding surfaced by two lanes and confirmed by execution.
  Lanes: CI.

- ✅ [PRESS-0033] **Nothing names the promises a Pressless release may not break.**
  versioning.md section 3 says SemVer is written for something other
  code imports, which Pressless is not -- so "the public API" has no
  referent here and each project must name its own breaking surfaces,
  once, in docs/standards/versioning-overrides.md. That file does not
  exist; docs/standards/ holds only its README. Section 3 calls it the
  one override a project otherwise following the global set still writes,
  and the only path a merge or an audit can be told to open.

  Section 4 puts a 0.x project's 1.0 exit condition in the same file.
  Pressless HAS that condition and it is good -- ROADMAP.md section
  Milestones, agreed with the user 2026-08-25 -- but it is not where the
  standard says an auditor will look. The fix is a pointer rather than a
  copy: one fact, one home.

  What is genuinely missing is the surface list. Without it every future
  release re-argues whether it broke something, and the argument happens
  under release pressure with no record of what was promised.

  Blocked-by: nothing. Needs a decision from the user on which surfaces
  count, which is why it is filed rather than written.
  Resolved (2026-08-27). docs/standards/versioning-overrides.md holds both
  answers section 3 and section 4 ask each project for: the breaking surfaces,
  and the 1.0 exit condition stated in one line here as section 4 requires.
  The surfaces are the user's decisions of 2026-08-27 -- setup state survives an
  upgrade, published addresses are frozen -- plus the writer's own files, which
  the user deferred. What is deliberately NOT a surface is named too, each with
  its own reason. docs/standards/README.md corrected in the same change: it
  called an overrides file deltas-only, and this one holds answers rather than
  deltas.

  Gated with review-contract --genre standard, three loops to the cap, three
  cold lanes each. The cap was violent -- most of the last loop landed on text
  the run itself had written -- so the document is not re-gated as it stands.
  Its loop log carries the detail. PRESS-0034 carries the one question the gate
  raised and did not decide.
  **Layman:** Writes down what Pressless promises never to break, so a future version cannot break it by accident.
  Kind: doc.
  Source: in-session-2026-08-27, versioning.md sections 3 and 4.
  Lanes: docs.

- ✅ [PRESS-0034] **The milestone version numbers may not be reachable under the 0.x ladder.**
  versioning.md section 4: inside 0.x a BREAKING change bumps the minor
  and everything else, a new capability included, bumps the patch. The
  Milestones section plans v0.1.0, then v0.5.0 adding the keyring, the
  Publisher, undo, the editor box, the one button and setup -- all
  additive. Under section 4 those are patch bumps, so v0.5.0 is
  unreachable without four breaking releases in between.

  Raised by one lane as an open question and filed as a finding by
  another on the next loop, both cold.

  Three readings, and the user decides which:
  1. The milestone names are labels for which signs of success hold, not
     cut versions. Milestones' own opening line supports this -- "A
     version number here says WHICH OF THE ELEVEN SIGNS OF SUCCESS HOLD".
     Nothing changes but a sentence saying so.
  2. They are literal targets, in which case this is a departure from
     section 4 and docs/standards/versioning-overrides.md is where it has
     to be recorded.
  3. Renumber the milestones to what the ladder produces.

  Not fixed by the gate that found it: which one is true is a decision,
  and guessing it would put a wrong rule in the file that governs every
  release.

  Blocked-by: a decision from the user.
  Resolved (2026-08-27): the user chose reading 1 -- the milestone
  numbers name goalposts, not cut releases. Recorded in
  docs/standards/versioning-overrides.md, under what would make this
  1.0, rather than in ROADMAP section Milestones: that section's intro
  is held in the roadmap store and no verb amends one, so a hand edit
  there is discarded by the next render.
  **Layman:** Checks whether the version numbers in the plan -- 0.1, 0.5, 1.0 -- are the numbers the rules would actually produce.
  Kind: investigate.
  Source: versioning gate on PRESS-0033, loops 2 and 3.
  Lanes: docs.

- ✅ [PRESS-0035] **The Marks archive test has never run: it looks for the generator one folder too high.**
  tests/test_marks_archive.py resolves the sibling generator at
  parents[2]/tools, which is one level above the workspace that holds it,
  so the file is never found. _load_build_blog() catches every exception
  and returns None, and the test then skips with a message saying the
  generator is not on this machine -- which is false here. So PRESS-0004
  INV-5, which its own spec calls the proof of the migration's S2, has
  produced no result on any machine, and the skip is indistinguishable
  from the expected one.

  tests/test_store_archive.py finds the same file by globbing one level
  deeper, which is the fix; that test is the evidence the path is
  reachable. Making it run may turn it red, which is why this is its own
  item rather than a change inside PRESS-0005.

  Blocked-by: nothing.
  Resolved (2026-08-31): the loader now globs both shapes, as
  tests/test_store_archive.py already did, and borrows that file's
  _exec_module helper because ruff S112 rejects the inline
  try/except/continue. INV-5 ran for the first time and came back
  green: every raw-text entry in the archive matches wpautop(), no
  mismatch, and both precondition sets are empty. It was expected to
  go red and did not, so nothing further was filed. mutation_probe
  against the shipped marks.py killed one escaping and two paragraph
  mutants through this test alone. The unreachable-generator skip was
  re-checked from a checkout where the sibling is absent and still
  skips cleanly.
  **Layman:** The test that proves twelve years of writing survives the move has never actually run once -- it looks for the old site's code in the wrong folder and quietly skips instead of saying so.
  Kind: fix.
  Source: in-session-2026-08-28, found while building PRESS-0005.

- 📋 [PRESS-0036] **Two accepted documents disagree with PRESS-0006's spec, and neither is corrected.**
  PRESS-0006's spec records both in its § 11 and corrects neither,
  because each belongs to a document with its own accepted status.

  `docs/design.md`, under *What Import brings across*, cites the count of
  published comments in the sentence telling Import to carry them. Import's
  population is published, draft AND private -- PRESS-0005 § 7 fixes that --
  so the number of comments Import carries is larger than the figure quoted
  there. Measured while gating PRESS-0006; the published-only figure is what
  the document names.

  `docs/specs/PRESS-0005-store.md` § 1 lists the photographs among what
  PRESS-0006 covers. PRESS-0006 settles only where an original sits; its
  name and everything else is PRESS-0016's, which is what
  `versioning-overrides.md` § The breaking surfaces already says.

  Neither changes what anyone builds today, which is why the gate left them.
  Both will mislead the next reader.

  Blocked-by: nothing.
  **Layman:** Two documents we already signed off say things the new plan proved wrong; nobody has gone back to fix them.
  Kind: doc-fix.
  Source: in-session-2026-08-31, found while gating PRESS-0006.

- 📋 [PRESS-0037] **A spec's mechanical checks report themselves clean when they did not run.**
  `spec_lint` returns `ok: true` with `findings: []` while its three
  test-surface checks are listed in `skipped[]` and `surfaces_checked` is
  false: the verb resolves a surface only in a `tests/features/<name>/`
  shape, which this project does not use, so no spec here can ever turn
  that check on. `doc_citations` returns `count: 0` and says in its own
  hint that this is SILENT rather than clean -- it read backticked spans it
  could not resolve.

  So a clean-looking envelope covers checks that never ran, and the work
  falls to the session: resolve the `*Test:*` clauses by hand, and resolve
  the cited symbols by hand. That was done for PRESS-0006 and is recorded
  in its packet, but nothing tells the next spec author to do it.

  Write it into CLAUDE.md beside the existing test traps -- it is the same
  class as `test_marks_is_pure` passing against an empty file. Filed rather
  than written now because adding an instruction to CLAUDE.md re-arms rule
  14's gate, which is a cost this session should not spend silently.

  Blocked-by: nothing.
  **Layman:** Two of our automatic document checks return a tick even when they checked nothing, and a future session will read that tick as a pass.
  Kind: doc.
  Source: in-session-2026-08-31, met while gating PRESS-0006.

- ✅ [PRESS-0038] **Close the check-code whole-tree sweep: five verified findings fixed, six dismissed.**
  Fifteen tools ran; only shfmt was owed a line and skipped, for want
  of an .editorconfig section selecting *.sh. Fixed: a dead `*/-` case
  pattern in .githooks/pre-commit that `*-` already subsumed (verdict
  diff over the real population moved 0 of 7); `usedforsecurity=False`
  on both copies of the git blob hash, which leaves the digest
  byte-identical on empty, text and binary input so PRESS-0009 INV-4
  holds, and lets the hash work under a FIPS policy; an unused
  `_valid_settings` helper left over from the PRESS-0001 red run;
  `unparseable` -> `unparsable`; three lines over the project's own
  declared 100-column limit.

  Six findings dismissed to .ants_review_falsepos.jsonl with reasons:
  bandit B310 / ruff S310 (every URL is built from a hardcoded https
  module constant), B314 defusedxml (the input is the writer's own
  local export, in tests skipped by default), four of the six vulture
  hits (spec-declared surface, an unbuilt consumer, and framework
  dispatch pytest and HTMLParser perform by name), B905 zip strict
  (the unequal-length case is handled deliberately two lines below),
  and the mypy/pyright correlated-optional and test-kwargs clusters.

  Gate green after the fixes: 66 tests collected and passed, leak
  sweep clean on all three surfaces.
  **Layman:** The automatic code checkers were run over the whole project; five real problems were fixed and six false alarms were written down so nobody re-investigates them.
  Kind: audit-fix.
  Source: check-code --tree 2026-08-31.

- ✅ [PRESS-0039] **Four atomic writers call os.replace with no fsync, so three specs promise durability the code does not have.**
  Found by three lanes independently -- the strongest signal in the
  sweep. settings.py:192, credentials.py:242, store.py:246 and
  insights.py:362 all use temp-plus-rename and none calls fsync.
  rename(2) orders the namespace, not the data, so a power loss or
  kernel panic can commit the rename before the blocks.

  Three specs claim the protection: PRESS-0001 4.4 "never a truncated
  one", PRESS-0005 INV-3 and 4.5 "the previous file rather than half an
  entry", PRESS-0002 4.4. On ext4 the auto_da_alloc heuristic usually
  covers it; that is the filesystem's luck rather than the code's, and
  Windows is a first-class target.

  Worst consequence is credentials': _write_file reads the file first
  and does not catch, so a truncated one makes read() AND write() raise
  permanently, with no message saying the recovery is deleting it.

  NOT VISIBLE TO THE TEST SUITE: PRESS-0001 INV-5's fixture patches
  os.replace, so the test that exists to prove this cannot see it.

  The fix is one shared _atomic_write helper, which PRESS-0006 will
  need three more copies of if it is not written first.

  AND THE COPIES HAVE ALREADY DIVERGED -- a separate defect from the
  missing fsync, filed here because it is the same four call sites and
  the same fix. Verified in source: only store.py:246 names the newline
  explicitly. settings.py:192, credentials.py:242 and insights.py:362
  do not, so on Windows those three write CRLF where store writes LF.

  For settings and credentials that is harmless to JSON but means the
  file PRESS-0001 4.2 calls a shape the installation carries between
  machines is not byte-identical across them. For insights it is
  harmless outright: the cache is never published and never diffed.

  The point is that four copies of one idiom already disagree on one
  parameter BEFORE PRESS-0006 adds three more, which is the argument
  for extracting the helper now rather than later.

  design.md's Persistence section states UTF-8 and LF line endings
  written explicitly, unconditionally, so either those three sites are
  wrong or the rule needs scoping to files git sees. The document side
  is PRESS-0060.

  Progress (2026-09-02): NOT started, because the prescribed fix cannot
  be built as written. Verified in the accepted specs: PRESS-0001 INV-1
  says settings.py imports no network module and no other pressless
  module, and PRESS-0002 INV-1 says credentials.py imports no other
  pressless module. A shared _atomic_write helper is a pressless
  module, so importing it breaches both -- and neither invariant is
  incidental: design rule 10 and PRESS-0001's depends-on-nothing are why
  they read that way. Verified in source: settings.py, credentials.py
  and store.py import no pressless module today; insights.py imports
  Settings. PRESS-0005 INV-1 forbids only the network and
  pressless.marks, so store.py could take a helper; the other two
  cannot. So the choice is between adding fsync inline at each of the
  four sites -- surgical, no invariant touched, and the duplication this
  item objects to -- or amending two accepted specs' INV-1 to permit one
  stdlib-only helper, which is a design change owing CLAUDE.md rule 14's
  gate on both. Inline looks right for the durability half, with the
  helper question filed separately since PRESS-0006 adds more copies.
  Also verified: no os.fsync anywhere in the tree, and on the newline
  half store.py's writer already names it while settings.py,
  credentials.py and insights.py do not -- that half needs no decision
  and can land with the fsync. The directory fsync that makes os.replace
  durable needs a platform guard: a directory cannot be opened for fsync
  on Windows, which is a first-class target here.

  Resolved (2026-09-02): each of the four sites now flushes and fsyncs
  the temporary's descriptor before os.replace, and the three that left
  the newline to the platform now name it, so all four write LF as
  design.md's Persistence rule requires.

  Built INLINE rather than as the shared helper this item prescribes,
  for the reason the progress note above records: that helper is
  unbuildable without amending two accepted specs' INV-1. The helper
  question is NOT closed by this item -- PRESS-0006 will add more copies
  of the idiom, and extracting it is still a design change owing rule
  14's gate on PRESS-0001 and PRESS-0002.

  Scoped to the DATA fsync. The directory fsync is deliberately not
  here: syncing the temporary before the rename is exactly what the
  three specs promise -- the old file or the new one, never a truncated
  one -- while a directory fsync only makes a completed save survive a
  power cut, which no spec promises, and it is the half needing the
  Windows platform guard.

  No document change was owed: the code now conforms to design.md as
  written, so the scoping question that paragraph raised does not arise.
  PRESS-0060 is untouched -- it is about PRESS-0005 4.2, not this.

  Tests: tests/_durability_watch.py records mkstemp, fsync and replace
  in order and asserts each rename was preceded by an fsync of that
  temporary's own descriptor. It reads the file size AT the sync, so an
  fsync with no flush ahead of it fails too -- that mutation was run and
  caught, and it leaves no trace on disk for any assertion over the file
  to find. The newline half asserts what the code named, not the bytes,
  because os.linesep is LF here and a byte assertion passes against the
  defect. All seven tests were red before the change; gate green.

  Not verified on Windows: the test box deliberately has no Python
  (CLAUDE.md), and there is no packaged executable yet.

  Tidied (2026-09-02): a garbled duplicate of three paragraphs above sat
  at the end of this body, written with literal backslash-n sequences by
  a bad tool payload. It could not be removed until the Ants MCP gained
  op:set_body, and this body was rewritten with that verb.
  **Layman:** A power cut at the wrong moment could leave a file empty even though the code was written to make that impossible.
  Kind: review-fix.
  Source: review-code 2026-08-31 lanes settings/credentials/store/insights.

- ✅ [PRESS-0040] **Both network modules use except OSError as their typed-failure seam, and http.client.HTTPException is not one.**
  Confirmed by execution: issubclass(http.client.HTTPException,
  OSError) is False.

  insights.py:222 and publisher.py:326 both catch OSError as the seam's
  signal for "no answer". IncompleteRead (a truncated response body),
  BadStatusLine, LineTooLong and InvalidURL all inherit from Exception.
  urlopen can also raise a bare ValueError.

  Both module docstrings state that every failure is one of the typed
  exceptions; both are false.

  In insights it skips the documented stale-cache fallback, so a writer
  holding a good cache gets an unexpected-error screen instead of
  yesterday's numbers marked stale. In publisher it is worse: on the
  reference update it defeats OutcomeUnknown, which is the one place
  the design has decided it must never guess.

  Fix in _Urllib.request in both, catching (OSError,
  http.client.HTTPException, ValueError) and re-raising as OSError, so
  the seam contract is kept where it is implemented.
  Resolved (2026-09-02): _Urllib.request in both modules now catches
  http.client.HTTPException and ValueError and re-raises them as
  OSError, so the seam's contract is kept where it is implemented
  rather than at each call site. The raised error names only the
  host, so INV-7 still holds. Both module docstrings claimed every
  failure is one of the typed exceptions; that is now true.
  **Layman:** A half-received reply from the network escapes the app's error handling and shows an unexpected-error screen instead of the friendly message.
  Kind: review-fix.
  Source: review-code 2026-08-31 lanes insights/publisher.

- ✅ [PRESS-0041] **Neither network module sets a urlopen timeout, so a black-holed connection hangs forever.**
  Confirmed by execution: the string "timeout" appears nowhere in
  either insights.py or publisher.py. urlopen with no timeout uses the
  global default socket timeout, which is None unless something sets
  one, and nothing in src/ does.

  Not "slow" -- forever, with no cancellation path.

  It defeats insights' stale-cache fallback and design.md rule 8's
  promise that everything from S1 to S10 still works when Google is
  unreachable, because the code never reaches the point of raising
  Unreachable. In publisher, a hang on the PATCH means the writer never
  learns whether the publish went out.

  socket.timeout is a TimeoutError and therefore an OSError, so it maps
  onto the existing Unreachable / OutcomeUnknown handling once set.
  Expose it as a parameter so a test can drive it.

  NO TOOL CATCHES THIS. Checked: bandit B113 (request_without_timeout)
  reads the requests and httpx modules only -- its plugin source does
  not mention urllib. This is a gap in the available tooling rather
  than in how check-code was configured.
  Resolved (2026-09-02): a thirty-second timeout in both modules,
  passed on every request and exposed as a constructor argument so a
  test can drive it. It bounds each socket operation rather than the
  whole request, so a large first publish that keeps making progress
  is not cut off.

  Measured against a socket that accepts and never answers:
  TimeoutError in 0.44s at a 0.4s bound, where the old code waited
  indefinitely. socket.timeout is an OSError, so it lands on the
  existing Unreachable / OutcomeUnknown handling unchanged.
  **Layman:** If the network goes strange in a particular way, the app stops responding and never recovers on its own.
  Kind: review-fix.
  Source: review-code 2026-08-31 lanes insights/publisher.

- ✅ [PRESS-0042] **The owner-only guarantee on the fallback credentials file is asserted and never verified.**
  The sweep's one raw CRITICAL, and it stays CRITICAL after
  calibration.

  ADR-0003 states a CAPABILITY test -- "where a file cannot be made
  private to one user there is no fallback: setup stops and says so".
  credentials.py:213 implements a PLATFORM proxy instead: it refuses
  Windows and allows everything else.

  tempfile.mkstemp requests 0600, but a mount's fmask / file_mode
  overrides it on every filesystem that does not enforce POSIX modes --
  vfat, exFAT, NTFS, CIFS/SMB and many FUSE mounts -- where the result
  is typically 0644 or 0666 and chmod returns EPERM. os.replace carries
  that permissive mode onto the target. credentials.py:231-245 never
  stats the result, so write("file", ...) returns None for success with
  the key readable by anyone on the machine.

  WHY THIS IS NOT OUT OF SCOPE FOR A SINGLE-USER APP: PRESS-0002 3
  decision 1 names the exact scenario as its own justification -- "the
  writer chooses where Pressless sits, which may be a shared or
  removable drive". Windows is refused for this reason; Linux on a USB
  stick is the same defect and is allowed. 4.6's measurement was taken
  on ext4 and is asserted, never checked, at runtime.

  Fix: os.fstat(handle).st_mode & 0o077 on the mkstemp descriptor
  BEFORE the secret is written into it; discard and raise NoStore where
  any group or other bit is set. Checking the temp rather than the
  target means the secret never touches a permissive filesystem at all,
  and it costs one syscall on a path that already exists.

  Pair with the read side: credentials.py:258 follows symlinks and
  checks neither ownership nor mode, so on the same drive another user
  can substitute a file and read() hands their token to the Publisher.
  Resolved (2026-09-02): _write_file now reads the mode off the
  descriptor mkstemp returned, before the secret is written into it, and
  raises NoStore where any group or other bit is set. That is ADR-0003's
  capability test rather than the platform proxy that stood in for it,
  and checking the temporary rather than the target means the secret
  never reaches a filesystem that cannot keep it private. One syscall on
  a path that already existed. Test
  test_a_folder_that_cannot_keep_a_file_private_is_refused, proven red
  first with DID NOT RAISE; it fakes fstat, since that is the one call
  reporting what the mount actually granted. Verdict space read whole
  rather than sampled: only the owner bits pass, so 0600 and 0700 are
  allowed and every mode carrying a group or other bit is refused.
  PRESS-0002's write table, its § 4.6 measurement and its § 10 table now
  say so. The read side is NOT done and is filed as PRESS-0085 -- it
  needs a decision that contradicts _write_file's own written design
  choice, so it owes a rule 14 gate rather than a quiet edit.
  **Layman:** On some kinds of drive the file holding the publishing key can end up readable by anyone, and the app reports success anyway.
  Kind: security.
  Source: review-code 2026-08-31 lane credentials.

- ✅ [PRESS-0043] **A missing or empty site folder deletes the whole published site in one commit and reports success.**
  Raised from the lane's HIGH to CRITICAL in calibration: it needs no
  adversary and no unusual input.

  Confirmed by execution: Path.rglob("*") on a non-existent directory
  returns an empty iterator with NO exception, and publish() has no
  is_dir() guard. So publisher.py:168 gives local == {}, and :179-182
  puts every unprotected remote path into `removed`. A clean Outcome is
  returned.

  Reached by a mis-set site_folder, an unmounted drive, or a Builder
  that failed before writing. Nothing in the module or in Settings
  guards it, and ADR-0002 says this class is uncaught downstream.

  Fix: precondition at the top of publish() -- refuse a folder that is
  not a directory -- plus a refusal when `uploaded` is empty and
  `removed` covers the whole remote set. A full wipe is never a
  legitimate publish.
  Resolved (2026-09-02): two preconditions in publish(). A folder that
  is not a directory is refused before the first request; a publish that
  would remove every unprotected path while writing none is refused
  after the listing is read and before the first write. Both raise
  PublishError, and the spec's failure table carries both. Tests
  test_a_site_folder_that_is_not_a_directory_is_refused and
  test_a_publish_that_would_empty_the_site_is_refused, each proven red
  first with DID NOT RAISE. No existing publish fixture reaches either
  guard -- confirmed by reading the fixtures, not by running them.
  **Layman:** If the folder the app publishes from is wrong or empty, it wipes the live site and tells you it worked.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane publisher.

- ✅ [PRESS-0044] **The untouchable rule has two diverged implementations, and the one that silently protects nothing is the safety-critical one.**
  Raised from HIGH to CRITICAL: with the item above, this is the
  site-destruction pair. The untouchable list is the single guard
  against the deletion PRESS-0009 2 calls unrecoverable.

  publisher.py:401-409 does `path.split("/", 1)[0] in untouchable`.
  publisher.py:412-422 (_within_prefix) rstrips a trailing slash and
  accepts multi-segment values, and its docstring claims "the same rule
  4.4 gives the untouchable list". It is not the same rule.

  Confirmed by execution:
    untouchable='CNAME/'          protects 'CNAME'           -> False
    untouchable='docs/robots.txt' protects 'docs/robots.txt' -> False
    _within_prefix('docs/robots.txt', 'docs/')               -> True

  A nested entry protects NOTHING -- not even itself -- because only a
  path's first segment is compared against the whole entry.

  Nothing enforces the form: settings.py:96-101 validates only
  isinstance(entry, str). So a hand-edited settings.json, or the Setup
  code that has not been written yet, disables the guard with no error
  at any layer.

  Fix on both sides: normalise in _is_protected, and reject a malformed
  entry in settings.py's loader so it is loud rather than inert.
  Resolved (2026-09-02): _is_protected now ignores a trailing slash on
  an entry, and settings.load refuses an entry it cannot resolve to a
  root name -- one naming a path inside a directory, or empty. Both
  sides move because a hand-written settings file reaches the Publisher
  without passing the loader. A trailing slash is not refused at load:
  it names one root entry unambiguously. _within_prefix's docstring no
  longer claims a rule it does not share. Verdict diff of old against
  new over the real population: 5 of 110 moved, every one a
  trailing-slash entry and every one toward more protection; no
  well-formed entry changed verdict.
  **Layman:** The list of files the app promises never to touch stops working if an entry is written in a slightly different but reasonable form -- with no error anywhere.
  Kind: security.
  Source: review-code 2026-08-31 lane publisher.

- ✅ [PRESS-0045] **No Content-Type header, so all four JSON writes go to GitHub as form-encoded.**
  Confirmed by execution against urllib's own handler: with a JSON body
  and no Content-Type set, the header actually sent is
  "application/x-www-form-urlencoded". publisher.py:315-319 sets
  Authorization, Accept and User-Agent and no Content-Type.
  AbstractHTTPHandler.do_request_ inserts that default whenever
  request.data is not None.

  PRESS-0009 4.3 specifies four JSON writes against a documented JSON
  API.

  Whether GitHub tolerates it cannot be settled from here -- 10 of that
  spec declares the live API an unrunnable region, and the test double
  never runs _Urllib, so this is precisely the defect class the suite
  cannot see. If GitHub does not tolerate it, every write fails on the
  first real publish.

  Fix: add "Content-Type": "application/json". One line, and it removes
  the largest unverified assumption in the module.
  Measured (2026-09-02) against the live API, in the same throwaway
  repository PRESS-0072 used. Both halves of this item are now settled,
  and they point opposite ways.

  The header claim is CONFIRMED. Replicating publisher.py's headers --
  Authorization, Accept, User-Agent, no Content-Type -- and reading
  urllib's own request object after the call:

    Content-Type actually transmitted: application/x-www-form-urlencoded

  So the module really does describe its JSON as form-encoded.

  The CONSEQUENCE claim is refuted. GitHub accepts it: the same POST to
  git/blobs returned 201, as did the control carrying
  Content-Type application/json. So "if GitHub does not tolerate it,
  every write fails on the first real publish" does not happen -- it
  tolerates it.

  This item stays open and the one-line fix is still right: sending a
  header that contradicts the body is wrong whether or not the far end
  is forgiving, and tolerance measured today is not a guarantee. But it
  is no longer the largest unverified assumption in the module, because
  it is no longer unverified. Reprioritise it as an ordinary correctness
  fix rather than a release blocker.
  Resolved (2026-09-04). _call now sets Content-Type: application/json,
  but only where a body exists. The condition is not decoration: measured
  against urllib's own handler, a body-less GET has no default inserted,
  so declaring a type for a request with no body would be a second wrong
  claim rather than a fix. No spec invariant governs request headers, so
  no document was edited. A regression test asserts the header on every
  §4.3 write and its absence on every body-less request; a mutation probe
  killed all three routes the defect could return by -- dropped as
  redundant, set unconditionally, and set to the wrong value.
  **Layman:** The app tells GitHub its messages are one format while actually sending another.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane publisher.

- ✅ [PRESS-0046] **OutcomeUnknown covers only the OSError branch, the rate-limit handling has three defects, and fetch_previous is not atomic.**
  Three MEDIUMs in one module, grouped because they share the failure
  path.

  OUTCOME (publisher.py:219-222, :343-345). A 5xx ANSWER to the
  reference update raises plain PublishError, though a 502 after the
  ref was applied leaves state exactly as unknown as a dropped
  connection. PRESS-0009 6 generalises every non-OutcomeUnknown row to
  "unchanged", so the Face would tell the writer his site had not moved
  when it may have -- the S6 breach 2 says the design exists to
  prevent. Fix: with outcome_unknown set, map any status outside {200,
  201, 409, 422} to OutcomeUnknown; 409/422 prove refusal and stay
  Conflict.

  RATE LIMITS (publisher.py:441-459, :465-466). (a) GitHub's PRIMARY
  limit answers 403 with x-ratelimit-remaining: 0 and no Retry-After,
  so it falls through to Refused and tells the writer to re-enter a key
  that is fine; x-ratelimit-reset is never read. (b) A hintless 429
  waits PACE_SECONDS, so MAX_RETRIES = 4 exhausts in about four seconds
  against GitHub's documented 60. (c) max(float(after), 0.0) has no
  upper bound, so Retry-After: 3600 becomes a one-hour blocking sleep.

  FETCH (publisher.py:282-285). fetch_previous is not atomic and does
  not clear `into`, so a partial failure leaves a hybrid of previous
  and pre-existing files that the Face cannot distinguish from a
  complete fetch. Undo is PRESS-0009 2's highest-value safety feature
  and publishing a hybrid is the failure it must not produce.
  Resolved (2026-09-04): all three fixed in f375cc6, each test run red
  against the old code first. OUTCOME narrowed from the finding's own
  prescription: it asked for every status outside {200, 201, 409, 422},
  which would contradict §6's Refused row and hide a rejected key behind
  "your site may have moved". Only a 5xx is genuinely ambiguous, since
  GitHub authenticates and validates before it acts. RATE LIMITS all
  three: the primary limit's x-ratelimit-reset is read, a hintless breach
  waits the documented minute, and a hint too long to honour raises
  RateLimited rather than sleeping. Verdict-diffed over 96 status/header
  combinations -- 8 moved, 88 unchanged, including every 403 carrying no
  rate-limit header. FETCH stages inside the target and moves into place
  only once every file is fetched. Spec §4.3, §4.5, §6 and §10 updated;
  rule 14 answered No in the commit body.
  **Layman:** Three separate ways the publishing step can mislead the writer about what happened.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane publisher.

- ✅ [PRESS-0047] **An entry saved with Windows line endings is rejected, and the message misstates the cause.**
  store.py:139-144 does text.partition("\n\n"). A CRLF file contains
  "\r\n\r\n" and therefore no "\n\n" substring, so partition finds no
  separator and every CRLF entry raises StoreError "has no blank line,
  so where the header ends and the body begins is undecidable".

  Confirmed by execution against a CRLF fixture.

  PRESS-0005 1 (S3) invites the writer to open entries without
  Pressless, the app ships on Windows, and a Windows editor that
  normalises on save turns his own entry into an unreadable file with a
  diagnosis that sends him hunting for something that is not the cause.

  PRESS-0005 4.2 pins CRLF on the WRITE side and is silent on the read
  side, so which side is wrong is a contract question -- see the
  document item filed alongside this. The error text is wrong either
  way.

  Fix: accept "\r\n\r\n" as a separator on read, keep writing LF (4.2
  already normalises), or at minimum detect \r\n and say so.
  Resolved (2026-09-02): read() now accepts both spellings of the blank
  line that ends the header and takes whichever comes FIRST. Order is the
  part that matters -- a body may hold blank lines of its own, so a reader
  trying "\r\n\r\n" ahead of "\n\n" splits inside the body and reports a
  header line with no colon. That mistake has its own test, which passes
  before the fix and so was proved by mutation rather than by a red run.

  The body is unchanged by the fix: §4.4 forbids a repair and INV-5 keeps
  every line break the writer typed, so a CRLF body stays CRLF. read()
  still decodes bytes rather than opening text, so no newline translation
  reaches it. Writing is untouched -- §4.2 already pins LF there.

  Took the "accept \r\n\r\n on read" branch this item offered rather than
  the minimum "detect and say so". The standing requirement is that the
  app runs on Windows as well as on Linux, and a message that correctly
  names the cause still leaves the writer unable to open his own entry.

  This does not settle the contract question. PRESS-0005 is silent on the
  read side, so nothing in it was contradicted, but nothing in it now
  states the behaviour either -- PRESS-0060 still owns that, and its
  choice is now recording what was built rather than deciding it.
  **Layman:** Open an entry in a Windows editor, save it, and the app says the file has no blank line -- pointing at a blank line that is plainly there.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane store.

- ✅ [PRESS-0048] **Three holes in the extra-field guard silently corrupt an entry, including replacing the writer's title.**
  store.py's _refuse_what_the_format_cannot_carry checks an extra
  field's name for newline and carriage return, and for nothing else.
  All three confirmed by execution.

  1. COLON IN THE NAME (:315-317). extra=(("A:B","v"),) writes "A:B: v"
  and reads back as ('A', 'B: v').

  2. NAME COLLIDING WITH A RECOGNISED FIELD (:236) -- the worst of the
  three, and worse than the lane reported. read's loop is last-wins, so
  Entry(title="Real", extra=(("Title","Other"),)) reads back with
  title='Other' and extra=(). The writer's actual title is REPLACED and
  the extra field disappears. With "Slug" the file becomes permanently
  unreadable via the stem check at :182.

  3. NEAR MISS (:157-171). Matching is exact and the name side is never
  stripped, so " Title: x" routes to extra and write() then emits an
  empty "Title: " alongside the original line.

  The exposed caller is Import (PRESS-0007), which builds extra from
  the WordPress export -- so fixing this before Import is written is
  the difference between a refusal and a corrupted archive.

  Fix: refuse ":" in a name, refuse a name in RECOGNISED_FIELDS, refuse
  an empty name; strip the name before comparing.
  Resolved (2026-09-02): all three, and each was reproduced before the
  fix rather than taken from the report.

  The guard now refuses an extra name that is empty once stripped, that
  contains a colon, or that matches a recognised field once stripped.
  read() compares the header name stripped, so a near miss is the field
  it looks like rather than a new one -- which is what stopped
  " Title: x" reading back as an empty title and then emitting a second,
  empty Title line beside the original.

  The collision test is parametrized over RECOGNISED_FIELDS itself
  rather than a copy of it, so a field added to the format is refused
  here too instead of the list going quietly out of date.

  An ordinary extra field still survives a round trip, asserted -- the
  guard could otherwise have been met by refusing every extra, which
  would break ADR-0001's promise in the act of keeping it. Five
  mutations killed, including that over-strict one.

  The archive conformance run passes with the stricter guard, so the
  real export carries no extra field this refuses. That matters for
  PRESS-0007: Import builds extra straight from the export, and this
  landing first is the difference between a refusal and a corrupted
  archive.
  **Layman:** An unusual field name in an entry file can quietly overwrite the entry's title or scramble its contents.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane store.

- ✅ [PRESS-0049] **A settings file with one undecodable byte escapes load() and save() as neither NotSetUp nor SettingsError.**
  Confirmed by execution: the escape is a UnicodeDecodeError, which is
  a ValueError and NOT an OSError.

  settings.py:70 does target.read_text(encoding="utf-8") inside a try
  whose arms catch FileNotFoundError and OSError. Neither matches, so
  it escapes load() uncaught. PRESS-0001 4.3's row -- "File present,
  not valid JSON or not decodable as UTF-8 -> SettingsError, naming the
  file" -- is not implemented.

  The intended catch EXISTS, at :78, as except (ValueError,
  UnicodeDecodeError) around json.loads(text) where text is already a
  str -- so json.loads can never raise UnicodeDecodeError there. The
  guard sits in the one place it cannot fire and is absent from the
  place it can. save() repeats it at :154/:162.

  The module's own docstring at :7-9 names the triggering scenario: a
  cp1252 write on Windows of an accented site_folder, "written here and
  unreadable there".

  Consequence: PRESS-0011, which will handle NotSetUp and
  SettingsError, gets an exception in neither family, so a one-byte
  corruption crashes rather than being reported.

  Fix: catch UnicodeDecodeError before the OSError arm at both sites,
  and drop the unreachable one from :78 and :162.
  Resolved (2026-09-02): both reads now catch UnicodeDecodeError, and
  the unreachable half is dropped from both json arms rather than left
  there reading as cover -- json.loads is handed a str and can never
  raise it.

  The fix is small; what made it worth checking carefully is that the
  guard already existed, one block down, in the one place it could not
  fire. A reader scanning for it finds it and moves on.

  One mutation, killing both tests -- load() and save(), the second
  reached while the writer is trying to save.
  **Layman:** One corrupted character in the settings file crashes the app instead of producing the friendly message that was written for exactly that case.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane settings.

- ✅ [PRESS-0050] **The one unguarded get_keyring() breaks a contract the rest of the module keeps exactly.**
  credentials.py:62 is the only get_keyring() call in the module
  outside a try; write() at :119-124 and _read_keyring() at :167-172
  are both guarded. So an untyped exception escapes choose().

  This breaches PRESS-0002 4.3's "Every one of these is typed, and that
  is a requirement rather than tidiness", and the named consequence is
  that the Face's last-resort catch tells the writer something
  unexpected went wrong during setup.

  Reachable with no adversary. keyring's core.load_config() reads
  ~/.config/python_keyring/keyringrc.cfg and calls load_keyring()
  outside its own except guard, so a stale config naming an uninstalled
  backend -- the ordinary state after uninstalling keyrings.alt --
  raises ModuleNotFoundError straight through choose(). class_.priority
  can also raise RuntimeError by the library's documented convention.

  Fix: wrap :62, raising CredentialError naming the exception type.
  NoKeyringError cannot arise here, so the existing discriminator is
  unaffected.
  Resolved (2026-09-02): choose()'s get_keyring() is wrapped, raising
  CredentialError naming the exception type.

  The guard is deliberately narrow and a second test holds it there.
  NoKeyringError comes from the probe write below rather than from the
  load, and it is §4.2's discriminator for "no store at all" -- widening
  the new guard over the probe would stop the file fallback ever firing,
  and a machine with no store would be told its store is broken. Two
  mutations killed, including that widening.
  **Layman:** A leftover setting on the machine can make setup fail with an unexpected-error screen instead of a clear message.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane credentials.

- ✅ [PRESS-0051] **A third-party backend's own error message can carry the secret into an exception INV-6 says never holds one.**
  credentials.py:120-124 interpolates {exc} into a CredentialError, and
  uses `from exc`. exc is a message produced by an arbitrary third-party
  backend that was JUST HANDED the secret as an argument. The module
  has no control over what a backend puts in its message, and `from
  exc` additionally exposes it through __cause__ to anything that
  formats the chain -- a traceback, or PRESS-0003's rolling log.

  WHY THE TEST CANNOT SEE IT: PRESS-0002 5's INV-6 test uses patched
  stores, so it proves only that the module's own literals are clean.
  The invariant is stated absolutely and is checked against a
  substitute that cannot breach it.

  Fix: on this one site interpolate type(exc).__name__ instead of
  {exc}, and use `from None` so the cause cannot carry the value into a
  formatted chain. The other interpolation sites (:78, :171, :240,
  :248, :262, :267) never have a secret in scope and can keep {exc}.

  See also the document item on INV-6's test surface.
  Resolved (2026-09-02): the site now names the exception TYPE rather
  than the backend's message, and raises from None. Both halves were
  needed and the second is the one a str/repr assertion cannot see --
  __cause__ is formatted by a traceback and by PRESS-0011's rolling log,
  so from exc would have carried the value there even with a clean
  message.

  A new test hands the module a backend whose exception message quotes
  the secret, which is what the existing INV-6 test could not do, and
  asserts the formatted exception chain as well as str and repr. Three
  mutations killed: the original defect, the clean-message-but-from-exc
  case, and an over-correction naming nothing at all.

  One correction to this item's own reasoning, recorded because it was
  checked: the other {exc} sites were said never to have a secret in
  scope, and _write_file does take one. What makes its three sites safe
  is narrower -- their exceptions come from mkstemp, fstat and the write
  syscalls, none of which is handed the value, and an OSError's message
  is an errno and a path. They keep {exc}.

  The document item on INV-6's test surface is untouched by this. The
  new test sits beside INV-6 rather than replacing its clause, so the
  spec still describes a test that proves less than the invariant
  claims.
  **Layman:** If the password store fails in an unusual way, its complaint could quote the publishing key back into an error message.
  Kind: security.
  Source: review-code 2026-08-31 lane credentials.

- ✅ [PRESS-0052] **Both network modules let the Authorization header follow a cross-host redirect.**
  Found by two lanes independently.

  Confirmed by execution: urllib's HTTPRedirectHandler.redirect_request
  source contains no Authorization handling at all -- it copies every
  header except the content headers onto the redirect target, including
  a different host, and follows up to 10 hops. The requests library
  strips Authorization on a cross-host redirect; urllib does not.

  publisher.py:126-131 carries "Authorization: Bearer <the publishing
  key>", which can rewrite the writer's whole site. insights.py:137
  carries the Google OAuth token.

  TLS to a pinned hostname makes this unlikely rather than impossible,
  and neither API legitimately redirects here.

  Fix, once, shared: an opener whose redirect handler strips
  Authorization on a host change, or refuses 3xx outright.
  Resolved (2026-09-02): both modules build their opener with a
  redirect handler that drops Authorization when the origin changes,
  where origin is scheme, host and port. A same-origin redirect keeps
  the header, so a renamed repository's 301 still works.

  "Fix once, shared" was not available. Each module's INV-1 forbids
  importing any pressless module but Settings, so a shared helper
  would breach both; two copies is below the Rule of Three.

  Proved over real sockets outside the tree: a cross-origin redirect
  is still followed and the target sees no Authorization header, a
  same-origin one still carries it. The committed tests open no
  socket, per both test files' own rule.
  **Layman:** If a server redirected the app somewhere else, it would hand over the publishing key or the Google token to whoever answered.
  Kind: security.
  Source: review-code 2026-08-31 lanes insights/publisher.

- ✅ [PRESS-0053] **Both file formats refuse a newer version on read and silently downgrade it on write.**
  Found by two lanes independently, same shape in both modules.

  settings.py:170-172 -- save() carries an existing file's unknown
  keys forward while unconditionally stamping version: 1, and never
  looks at the version it read. credentials.py:222-229 -- _write_file
  never checks the existing version, while _read_file:191-196 does.

  So the same file that the read path refuses "rather than guessing at
  it" is guessed at on the write path. An older build run over a file
  written by a later Pressless produces a file labelled v1 still
  carrying v2's keys; the old build then reads it and the new build
  rejects its own settings.

  Unreachable until a v2 exists, which is exactly why it is cheap to
  fix now.

  The code matches PRESS-0001 4.2 as written, so that document needs
  the write-side row too -- filed separately.
  Resolved (2026-09-02): both write paths now refuse a file whose
  version this build does not write, so neither relabels a file another
  Pressless wrote.

  Both checks look only at a file that is THERE -- setup's first save has
  nothing to carry, and refusing it would make the app unusable from the
  start. A counter-case test in each suite holds that, and it is not
  decoration: the over-strict mutation kills five tests in settings and
  seven in credentials, so refusing everything is not a way to pass.

  Four mutations killed.

  The document side stays with PRESS-0057, as this item said: PRESS-0001
  §4.2 has no write-side version row, so the code matched the spec as
  written and the spec is what is short.
  **Layman:** An older copy of the app can quietly relabel a file written by a newer one, so neither can then read it properly.
  Kind: review-fix.
  Source: review-code 2026-08-31 lanes settings/credentials.

- ✅ [PRESS-0054] **A brace anywhere inside a colour mark silently kills the mark, and a deeply nested line crashes the parser.**
  Three defects in the scanner, grouped because they share the nesting
  path.

  BRACE COUNTING (marks.py:363). `if nests and text[i] == closes[0]:
  depth += 1` increments on ANY literal { character, not on a mark
  opener. PRESS-0004 4.5 says "a nested {...} opener increments a depth
  counter". So `{accent}the set {x} of things{/}` consumes the real
  {/} as a decrement, _closes_at returns None, and the whole line falls
  out as literal text -- the writer silently loses his colour for
  typing a brace. A balanced variant shifts the boundary instead. Same
  for muted, the hex colour and rainbow. 6 has no failure row for it.

  UNBOUNDED RECURSION (:388 and :491). _scan recurses per nesting level
  and node_html recurses again on render, with no depth bound. About
  5 KB on one line raises an uncaught RecursionError, where 6 promises
  literal text for malformed input and names photo_src as the only
  thing that raises. Fix with a depth cap that falls back to literal --
  the degradation the module already documents.

  QUADRATIC SCAN (:352-366). _closes_at scans to end of line at every
  position where an opener matches and no closer exists. The asterisk
  family is short-circuited by the adjacency guards at :380-382; the
  brace marks have no such guard. "{accent}a" * 5000 is on the order of
  2.25e8 steps.
  Resolved (2026-09-02), all three, each reproduced before the fix.

  Brace counting fires on an opener now, any brace mark's and with the
  argument validated, which keeps the {accent}{muted}x{/}{/} nesting the
  scanning section names as one it must accept. No spec change: §4.5
  already says a nested opener increments the counter, so this was code
  diverging from the contract.

  Nesting is bounded at 64, past which the rest of the line is literal.
  No amendment either: §6 already promises literal text for malformed
  input and names photo_src as the only thing that raises, so an
  implementation raising RecursionError breached it as written. The
  number is how that promise is kept rather than a new promise -- if the
  spec should pin it, that is a document item and not this one.

  The quadratic scan is reduced rather than removed, and it is worth
  saying which: whether the closer occurs at all is now checked once, so
  4000 unclosed openers went from 8.2s to 0.04s, but the check is still
  quadratic in C. 20000 openers is 0.65s.

  Verdicts diffed over the real population -- 729 posts, 11,221 lines,
  173 containing a brace -- and ZERO moved between the old scanner and
  the new one. That is the writer's real prose, NOT the marks archive
  conformance run, which cannot run on this machine because it needs a
  generator in a private workspace. Evidence the change is surgical on
  real text; not a substitute for INV-5.

  Five mutations killed, including narrowing the brace family to one
  mark and dropping the argument check.
  **Layman:** Type an ordinary curly bracket inside coloured text and the colour silently vanishes from the published page.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane marks.

- 📋 [PRESS-0055] **The photograph mark's name reaches the caller's file world unconstrained, though the spec says the escapes are that boundary's whole defence.**
  marks.py:208's _PHOTO_ARG captures `name` as any run of characters
  except | and }. marks.py:177 does
  _escape_attr(photo_src(node.name)) -- so the escape happens AFTER
  photo_src has already been called on the raw string.

  What reaches the caller: "../../../../etc/passwd", "..\\..\\", a
  leading /, a NUL, a URL. Also "{photo:   }", since the pattern admits
  a whitespace-only argument.

  PRESS-0004 5 states "INV-4 and INV-8 are that boundary's whole
  defence, and there is no other sanitiser downstream". `name` passes
  through NEITHER on its way into photo_src, so that sentence is not
  true of this path.

  The HTML sink itself is safe -- _escape_attr cannot be broken out of,
  and the lane confirmed every other sink in the module is escaped. It
  is the CALLABLE argument that is unconstrained.

  The consumer that will build a path from it is PRESS-0008, not yet
  written. Constraining the grammar now is a one-line change;
  constraining it after two callers exist is a contract change.

  Fix: bar /, backslash, } and control characters in the name group.
  Assessed 2026-09-02, not started, and what it needs is now precise.

  Confirmed in the spec: PRESS-0004 pins no pattern for the photograph
  name anywhere. So the code is not contradicting a written rule -- but
  §5's "INV-4 and INV-8 are that boundary's whole defence, and there is
  no other sanitiser downstream" is FALSE of this path, since the name
  reaches photo_src through neither.

  That makes the fix two halves, and only one of them is free. Making
  the code defend the boundary is what turns that sentence true. But the
  constraint itself -- bar /, backslash, } and control characters, and
  refuse a whitespace-only name -- is a rule an implementer has to be
  TOLD, and nothing in the spec says it today. Adding it changes what a
  conformer builds, so it re-arms CLAUDE.md rule 14 and owes the full
  gate. review-contract --quick is forbidden for a gate another rule
  mandates, so there is no cheap route.

  Still worth doing soon for the reason this item already gives: the
  consumer that will build a path from the name is PRESS-0008, which is
  not written. One caller makes this a grammar change; two make it a
  contract change.

  Sequence, so the next session does not have to work it out: amend
  PRESS-0004 §4.2 with the name's grammar and §5 with an invariant
  holding it, gate the spec, then write the code and the test.
  Second reason to sequence it carefully, found while assessing it and
  better than the first: narrowing the name's grammar narrows what
  INPUT is accepted. A photograph mark whose name contains a slash stops
  forming a mark and becomes literal text on the page.

  Whether the writer's own twelve years contain such a name is exactly
  what INV-5's archive conformance run would answer, and that run cannot
  execute on this machine -- it needs a generator in a private
  workspace. The verdict diff used for PRESS-0054 does not substitute:
  the export is WordPress HTML rather than Pressless marks, so it says
  nothing about photograph marks.

  So the fix wants either that run, or a deliberate decision that a name
  with a slash was never valid and any entry carrying one is to be
  corrected. That is a decision, not a detail, which is a further reason
  the spec amendment comes first.
  DEFERRED TO ME by the user 2026-09-04, so this is the decision rather
  than a proposal. It differs from the two branches this bullet describes,
  and the difference is the point.

  DO NOT bar the slash wholesale. That is the only part of the fix that
  could turn an existing entry into literal text on the page, and it is
  the only part the archive run was needed to make safe. Every hazard this
  bullet actually names is reachable without it.

  The grammar to amend PRESS-0004 4.2 with: refuse a backslash, a colon,
  any control character, a leading slash, any `..` segment, and a name
  that is whitespace only. Allow an interior slash.

  Why that covers the named exposure. "../../../../etc/passwd" and
  "..\\..\\" carry a `..` segment; a leading slash is barred outright; NUL
  is a control character; a URL and a Windows drive path both need the
  colon. Traversal above the handed folder requires `..` or a leading
  slash, so barring those two closes it whatever the interior looks like.
  An interior slash alone is a plausible folder name a writer would use
  and is not a traversal.

  This needs no archive run, which is what unblocks it. If that run ever
  becomes available it can still tell us whether a `..` or a colon appears
  in a real name -- but those are corrections rather than a question,
  because no such name was ever meant to work.

  Sequence is unchanged and still applies: amend 4.2 with the grammar and
  5 with an invariant holding it, gate the spec, then the code and test.
  Section 5's claim that the escapes are the boundary's whole defence
  becomes true only when the code enforces this.
  **Layman:** A photo name in an entry is passed straight out to whatever looks the file up, without being checked first.
  Kind: security.
  Source: review-code 2026-08-31 lane marks.

- ✅ [PRESS-0056] **Five unpinned Insights behaviours: a backwards clock, the cache folder, the property id shape, one cache slot, and a zero-visitor report.**
  All five follow from the module having no spec (filed separately);
  grouped because one document decides them together.

  BACKWARDS CLOCK (insights.py:180). The freshness test is one-sided:
  `now() - fetched_at < max_age_seconds`. Confirmed -- a negative age
  always passes, so after an NTP correction, a manual clock change or a
  restored backup the cache reads FRESH forever and shows old numbers
  labelled current, which is worse than showing them stale. Fix:
  require 0.0 <= age < max_age.

  CACHE FOLDER (:150-151). cache_path takes a caller-supplied folder
  with no relationship to settings.site_folder, while the comment at
  :41-42 asserts "never the site folder, which is published in full".
  If the Face passes it, the Builder copies it and the Publisher
  uploads it -- country-level readership data becomes publicly
  fetchable. The module asserts an invariant it cannot keep. Fix:
  refuse a folder that is, or is under, settings.site_folder.

  PROPERTY ID SHAPE (:202). design.md and PRESS-0001 both fix it as
  numeric; settings.py:137 type-checks only, while repository,
  site_folder and store all get shape checks eleven lines earlier under
  the stated reasoning "Shape, not merely type". A pasted G- tag gives
  "Google answered 404" instead of a sentence naming the confusion.

  ONE CACHE SLOT (:322-325). _cached rejects any other window and
  _store overwrites, so the moment the dashboard offers a second window
  the quota guard protects nothing -- one API call per click.

  ZERO VISITORS (:253-256). GA4 omits default-valued fields; if totals
  is absent on a zero-row report, a quiet week raises instead of
  returning zero. Open: unverified against the live API.
  Progress (2026-09-04): items 1, 2 and 5 fixed in 21969df, each proved
  red first. The freshness test is bounded at both ends; read() refuses a
  cache folder inside the site folder before any request; a window with no
  rows and no total reads as zero. That last is deliberately narrow -- an
  answer carrying rows but no total is still refused, since summing them
  is the overstated number that refusal exists to keep out -- and remains
  unverified against the live API, as the finding said.

  Items 3 and 4 are NOT done, and neither is a coding decision. Item 3
  (property id shape) needs a PRESS-0001 §4.3 row: that table enumerates
  the shape refusals and does not list this field, so adding the check
  re-arms CLAUDE.md rule 14. §4.1 and design.md already call the field
  numeric, so the check conforms to them -- it is the refusal table that
  is silent. Item 4 (one cache slot) is a design question the module has
  no spec to answer: it is latent until the dashboard offers a second
  window, so it belongs with PRESS-0063. Both put to the user.
  Resolved (2026-09-04): items 1, 2 and 5 in 21969df; item 3 in 7583759
  with the PRESS-0001 §4.3 amendment, gated by review-contract to its cap
  (loops 4 and 5, ten verified and ten fixed, plus one filed as
  PRESS-0091). Item 4 is NOT fixed and is not outstanding here: the user
  routed the one-cache-slot question to the Insights spec, PRESS-0063,
  which is where how many windows to cache gets decided. It is latent
  until the dashboard offers a second window.

  The gate paid for itself twice over on the way. It found that loop 4's
  own fix left save()'s version gate looser than load()'s, so a file
  load() refuses was one save() would relabel and carry forward -- the
  PRESS-0053 harm by the route PRESS-0066 closed on the read side only.
  Fixed in 5ad9a4e. It also found §4.3 pinned no character set for
  repository while the code enforces one, and that INV-2's own fixture
  cannot falsify its "neither is the other" clause.
  **Layman:** Five things the analytics part does that nobody ever decided, each of which can mislead or misfire.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane insights.

- 📋 [PRESS-0057] **PRESS-0001 has three gaps the code cannot be blamed for: no write-side version row, shape checks for three fields of five, and an INV-5 fixture that cannot see what it tests.**
  DOCUMENT SIDE. Gate with review-contract
  docs/specs/PRESS-0001-settings.md --genre spec. None of these is a
  code defect: the code conforms to what is written.

  1. 4.2 says the file is "written from the schema, never from what was
  read", and there is no row deciding what save() does when the
  existing file's version is NEWER than this build's. The read table
  refuses such a file; the write table has no equivalent. See
  PRESS-0053.

  2. 4.3 requires shape validation for repository, credentials.store
  and site_folder, and type-only for untouchable and
  analytics_property_id -- though 2 calls the untouchable list the
  Publisher's WHOLE protection, and an entry that is empty or
  mis-segmented silently protects nothing (PRESS-0044). The property id
  is the one field design.md says is easy to confuse, and it is the one
  with no shape check (PRESS-0056).

  3. INV-5's prescribed fixture patches os.replace, so the invariant
  that exists to prove a crash never leaves a truncated file cannot
  observe the missing fsync that makes the claim untrue (PRESS-0039).
  The test surface needs to name durability, not just atomicity.

  Also open, raised by the lane and not settled: after any save() the
  file's mode becomes 0600 from mkstemp, discarding whatever it had.
  Nothing specifies the mode.
  2026-09-04: the 0600 note in this bullet's tail has a Store-side twin.
  PRESS-0074 item 3 raised the same unsettled question about store.py's
  write, and measurement there confirms the behaviour on both paths -- a
  fresh write is 0600, and a rewrite narrows an existing 0644 back to it.
  Nothing specifies the mode in PRESS-0001 or PRESS-0005.

  Settle it once here and apply the answer to both documents. Deciding it
  in one alone is a direction change in that document and leaves the other
  saying nothing, which is how the two drift. PRESS-0074 is closed on
  every other count and defers this item rather than pre-empting it.
  **Layman:** The settings design document is missing rules the code was never told to follow.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lane settings -- document side.

- 📋 [PRESS-0058] **PRESS-0002's write table has no version row, and INV-6's test surface cannot detect the breach INV-6 forbids.**
  DOCUMENT SIDE. Gate with review-contract
  docs/specs/PRESS-0002-credentials.md --genre spec.

  1. 4.3's read table refuses a file from a later version "rather than
  guessing at it"; the write table has no such row, so the same file is
  guessed at on the other side. 2 point 4 flags exactly this class --
  "an on-disk shape an installation carries forward" -- and the
  contract implements the refusal in one direction only. Code side is
  PRESS-0053.

  2. INV-6 says no exception this module raises contains a secret
  value, and 5's test surface uses PATCHED stores. So it proves only
  that the module's own literals are clean, and cannot see a real
  backend's message being interpolated into a CredentialError
  (PRESS-0051). An invariant whose test substitutes the thing that
  would breach it is not falsifiable.

  3. Related, and the sharper one: ADR-0003 states a CAPABILITY test
  for the fallback file, and neither that ADR nor this spec gives it a
  test surface -- 4.6's measurement was taken once, on ext4, by hand.
  PRESS-0042 is the code side; the contract needs an invariant that
  binds at runtime.
  **Layman:** The credentials design document asks for a guarantee and then checks it in a way that cannot fail.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lane credentials -- document side.

- 📋 [PRESS-0059] **PRESS-0004 has four passages the marks lane found wrong or unfalsifiable, including a trust-boundary sentence that is not true.**
  DOCUMENT SIDE. Gate with review-contract
  docs/specs/PRESS-0004-marks.md --genre spec.

  1. 5 says "INV-4 and INV-8 are that boundary's whole defence, and
  there is no other sanitiser downstream". FALSE of the photograph
  name, which passes through neither on its way into photo_src
  (PRESS-0055). This is the sentence an implementer of PRESS-0008 would
  rely on.

  2. 4.5 says a nested "{...} opener" increments the depth counter and
  the code increments on any literal brace (PRESS-0054). One side is
  wrong and 6 has no failure row either way, so a writer losing his
  colour has no documented explanation.

  3. 4.2's table specifies alt="" on every photograph. An empty alt
  declares a DECORATIVE image; these are content images on a public
  writing site, so a screen-reader user gets nothing where a caption
  exists and could have been referenced. 9's out-of-scope list does not
  mention accessibility, so this reads as unexamined rather than
  decided. Both document and code are on the wrong side.

  4. 4.6 and INV-4 state the text-escaping rule unconditionally, with
  no carve-out for rainbow -- which escapes one character at a time, so
  the "leave an existing character reference alone" branch can never
  fire inside it and &nbsp; reaches the page literally. A per-character
  span cannot hold an entity together, so the spec should say so.

  5. Open, and unverifiable from this tree: INV-5 claims byte-identity
  with a wpautop() in a sibling workspace that is not present here, so
  nothing in this repository can check it.
  **Layman:** The markup design document overstates what protects the published page, and specifies an accessibility choice nobody examined.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lane marks -- document side.

- 📋 [PRESS-0060] **PRESS-0005 claims extra fields are kept byte-for-byte, and they are not; its read side is also silent on line endings.**
  DOCUMENT SIDE. Gate with review-contract
  docs/specs/PRESS-0005-store.md --genre spec.

  1. 4.2 says an unrecognised field is "kept byte-for-byte" and INV-4
  asserts byte-identical after read-then-write. Both are false, and
  measured:

    before b'...\nX:   spaced   \n\nbody\n'
    after  b'...\nCategories: \nTags: \nX: spaced\n\nbody\n'

  The round trip strips the value's surrounding whitespace AND injects
  Categories: and Tags: lines that were never in the file. The lane
  judged the DOCUMENT the wrong side for the stripping, since 4.2
  mandates the same normalisation for recognised fields and lists -- so
  the claim should be "preserved, with surrounding whitespace
  normalised". The injected lines were not reported by the lane and are
  mine; whether they are wanted is open.

  2. 4.2 pins LF on the WRITE side and says nothing about the read
  side, so whether a CRLF entry is meant to be readable is undecided --
  which is what makes PRESS-0047 a contract question rather than an
  obvious bug. The app ships on Windows and S3 invites external
  editing, so the document should choose.

  3. ADR-0001 has no version marker in the entry format, deliberately,
  while settings.py carries FILE_VERSION. Noted by the lane as a
  recorded choice rather than a defect; confirm it is still wanted
  before Import (PRESS-0007) writes twelve years of entries.
  Progress (2026-09-02): item 2 narrowed by PRESS-0047, which shipped the
  code side. read() now accepts a CRLF blank line as the header separator
  and leaves the body exactly as found; write is unchanged and still pins
  LF. So this item's item 2 is no longer a choice the document has to
  make -- it is a behaviour the document has to STATE, which per rule 14's
  carve-out records what was built and does not re-arm the gate on its
  own. Items 1 and 3 are untouched and still open.
  Progress (2026-09-02, second note): item 1 is WIDER than this bullet
  records, found by the review-contract run on PRESS-0005 and filed here
  rather than carried into that document.

  The byte-for-byte promise for unrecognised fields is stated in THREE
  places, not one: PRESS-0005 (§4.2 and INV-4), ADR-0001, and design.md
  § Persistence. PRESS-0005's two were corrected in that run — measured,
  `X-Note:  spaced  ` reads back as ('X-Note', 'spaced') and re-emits as
  `X-Note: spaced`, so the field survives but the line's spacing does
  not, and an implementer taking the word literally builds a different
  `extra` contract. The other two documents still say byte-for-byte, so
  they now disagree with the spec where before all three agreed and were
  wrong together.

  Fixing those two is a policy statement about the format's promise
  rather than a sentence repair, and each belongs to its own gate, which
  is why this run filed it instead. The open half of item 1 — the header
  lines the round trip injects — is untouched and still needs a decision.
  Item 1's open half is DECIDED (2026-09-02, by the user): the round trip
  stops injecting Categories: and Tags: lines. An entry the writer never
  gave them to comes back without them.

  The reason, in his words rather than the format's: the design promises
  everywhere else that his files survive the round trip, and twelve years
  of imported entries would otherwise every one gain two empty lines they
  never had. Predictable shape was the argument the other way, and it
  lost to not silently editing files nobody asked Pressless to change.

  This is a change of direction for work still to come, so the code side
  owes PRESS-0005 an amendment and rule 14's gate, and the amendment
  should be written before the code rather than after. What it must say
  is narrower than deleting a feature: the emitted header carries the
  recognised fields the entry ACTUALLY HAS, plus its unrecognised ones,
  and nothing else.

  Still open and untouched: item 3, and the wider half of item 1 -- ADR-0001
  and design.md still promise byte-for-byte where PRESS-0005 now says
  preserved with surrounding whitespace normalised, so those two now
  disagree with the spec where before all three agreed and were wrong
  together. Each belongs to its own gate.
  Progress (2026-09-03): PRESS-0005's §4.2 wording moved again, in the
  review-contract run that gated PRESS-0067 item 6. A cold lane found
  that §4.2 still asserted "ADR-0001's promise is that nothing is
  dropped or altered, and that holds" — which is both a misquotation
  (ADR-0001 says *preserved byte-for-byte and never dropped*) and a
  contradiction of the same bullet, which strips spacing and re-spells
  the separator.

  §4.2 now quotes ADR-0001 as written and states the departure: the
  field is never dropped and its name and value survive; the surrounding
  spacing is not kept byte-for-byte.

  That does NOT close this item. It makes PRESS-0005 honest about the
  gap rather than closing it, so the wider half of item 1 stands exactly
  as recorded — ADR-0001 and design.md still promise byte-for-byte, and
  each is its own gate. What has changed is that PRESS-0005 now names
  the disagreement instead of papering over it, so whoever takes those
  two documents has the sentence to work from.

  Also unresolved and worth knowing before that gate: whether ADR-0001's
  "anything the parser does not recognise" means the MARKS parser or the
  entry parser. In ADR-0001 the sentence sits under the styling set,
  which reads as marks; `versioning-overrides.md` glosses it the same
  way. If it is marks-only, the Store's header stripping never breached
  it and the wider half of item 1 is a wording fix. If it reaches header
  fields, it is a breaking-surface question. Nobody has decided, and the
  answer changes how big that gate is.
  Worked 2026-09-04. Item 1's decided half is DONE, spec first then code,
  as this bullet sequenced it.

  PRESS-0005 4.2 and 4.5 now say the emitted header carries only the
  recognised fields the entry has; _entry_text implements it; two tests
  pin it, one asserting the emitted BYTES because a re-read cannot tell an
  omitted line from an empty one. The archive round trip passes, so the
  writer's real entries survive the rule. Gate green, 187 passed.

  The gate ran to the spec cap of 2 and is recorded in the spec's own loop
  log as rows 6 and 7. Ten verified findings, ten fixed. Roughly three fell
  inside the amended span; the rest were pre-existing, so it was as much
  audit as gate. Two are worth knowing here: decision 4 credited the
  sibling generator's safe_slug with a post-id fallback that belongs to its
  caller -- found by all three lanes of loop 7, and it would have had
  Import resolve a large share of drafts to the empty slug; and 7 stated
  its stub rule unconditionally, so an implementer would have stubbed out
  the shipped module to get this amendment's red run.

  FILED, NOT FIXED: PRESS-0093, the code half of a gap loop 7 found in
  4.3 -- publish onto a destination differing only in the suffix's case
  succeeds, leaving one folder holding two files that name one slug. A
  docs gate may not edit code.

  STILL OPEN on this item, unchanged:
  - Item 3, ADR-0001 having no version marker. Needs a confirmation that
    the choice is still wanted before Import writes twelve years.
  - Item 1's WIDER half. ADR-0001 and design.md still promise unrecognised
    fields byte-for-byte where PRESS-0005 now says preserved with
    surrounding spacing normalised. Each is its own gate, and both are
    still blocked on the question this bullet already records: whether
    ADR-0001's "anything the parser does not recognise" means the MARKS
    parser or the entry parser. Nobody has decided, and the answer changes
    how big that gate is.

  Item 2 was already closed before this session: 4.2 states the read side's
  line endings in its blank-line bullet.
  **Layman:** The entry-format document promises the file comes back exactly as it went in, which is measurably untrue.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lane store -- document side.

- ✅ [PRESS-0061] **PRESS-0009 generalises every failure to "the site is unchanged", which its own 4.3 does not support, and misdescribes its own prefix rule.**
  DOCUMENT SIDE. Gate with review-contract
  docs/specs/PRESS-0009-publisher.md --genre spec.

  1. 6's table generalises every non-OutcomeUnknown row to "unchanged".
  4.3 supports that only for an interruption EARLIER than the reference
  update. A 5xx ANSWER to the PATCH leaves state exactly as unknown as
  a dropped connection, so the Face would tell the writer his site had
  not moved when it may have -- breaking S6, the one promise 2 says the
  design exists to keep. Loop 1 of the gate split this row for the
  OSError case and did not reach the status case. Code side is
  PRESS-0046.

  2. 4.5 and the _within_prefix docstring both say it applies "the same
  rule 4.4 gives the untouchable list". Measured, it does not --
  _within_prefix accepts a trailing slash and multi-segment values and
  _is_protected accepts neither (PRESS-0044). One rule, two
  implementations, and the document asserts they agree.

  3. 9 assigns "progress reporting during a slow first publish" to the
  Face, and publish() exposes no callback while blocking for at least
  862 seconds of pacing alone on ADR-0002's own first-publish figure.
  Either the code needs a hook or 9 needs to say progress means an
  indeterminate wait.

  4. Open: 4.2 says all three entry points resolve the default branch
  "from the repository itself once per call", and root_entries and
  fetch_previous use commits/HEAD instead. Equivalent on GitHub today.
  Drift or deliberate shortcut is undecided.
  Progress (2026-09-05). All four items settled in the document; the gate this
  bullet asks for has NOT run yet, so the item stays open.

  Item 1 was already fixed and is not re-fixed: section 6 now carries its own
  row and prose for a server error answering the reference update, and section
  4.3 backs the unchanged verdict on every other row. Verified rather than taken
  on trust.

  Item 2 fixed. Section 4.5 called the prefix rule "the same rule 4.4 gives the
  untouchable list". Measured, only the trailing-slash tolerance is shared:
  _within_prefix accepts a multi-segment value, and settings.load refuses an
  untouchable entry carrying an interior slash. The docstring had already been
  corrected; the spec had not. Code side stays PRESS-0044.

  Item 3 fixed. Section 9 gave progress reporting to the Face while publish
  takes no callback and returns only once the commit is made. It now says what
  the Face can show -- that a publish is running, not how far through. A hook
  stays open as a later choice; no code changed.

  Item 4 fixed, the user deciding to correct the document rather than the code.
  Measured: publish resolves the default branch and then reads that branch's
  head; root_entries and fetch_previous read commits/HEAD, which resolves to the
  same branch's head in one request. No behaviour a user sees differs.

  NEXT: review-contract docs/specs/PRESS-0009-publisher.md --genre spec. Commit
  975bdec is its baseline.
  Resolved (2026-09-05). The gate this bullet asked for has run:
  review-contract on docs/specs/PRESS-0009-publisher.md, genre spec, two
  loops of three cold lanes, twelve verified and eleven fixed. Cap reached
  and calm -- none of loop 2's findings landed on text loop 1 wrote.

  Loop 1 fixed six. The Status line still surfaced design rule 5's missing
  write as open while section 11 records it closed by PRESS-0026. Section
  4.4 was credited by 4.5 and 10 with a trailing-slash tolerance it never
  stated; executed, settings.load accepts "CNAME/" and stores the slash,
  so an entry compared exactly protects nothing. INV-5's test clause fails
  a conforming module, which sends force explicitly false. INV-9 said
  RateLimited is raised only once the bound is exhausted, which 4.3's
  too-long branch contradicts. Section 4.3 now says what a limit naming no
  usable interval waits. Section 4.5's "nothing lands in into" was false --
  staging is inside it, and staging beside it makes the last step a
  cross-filesystem copy.

  Loop 2 fixed five and filed one. All three lanes found section 6 giving
  RepositoryMissing to any repository resolving to nothing; executed, only
  the request naming the repository itself yields it, so the Face's setup
  branch for a mistyped repository was dead. "Every row but one says
  unchanged" against two unknown rows. Section 7's "every test hands in a
  double" against an import walk and three client tests.

  Filed rather than applied, a docs gate not editing code: PRESS-0095 (a
  malformed blob answer escapes the typed contract) and PRESS-0096
  (design.md admits one unknown-outcome case where section 6 has two).

  Recorded: the gate was armed by 975bdec and not one of the twelve
  findings landed inside that span, so this run was an audit of the whole
  document rather than a gate on its trigger.
  **Layman:** The publishing document promises the site is untouched after any failure, and there is one case where nobody can know that.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lane publisher -- document side.

- ✅ [PRESS-0062] **PRESS-0006 has an invariant that cannot pass against correct code, and two failure-table rows that collapse distinctions the Store makes.**
  DOCUMENT SIDE, and PRESS-0006 HAS NO CODE YET -- all 24 hits for its
  symbols are in the spec itself, which is what makes fixing it now
  cheap. Gate with review-contract
  docs/specs/PRESS-0006-pages-furniture-comments.md --genre spec.
  Distinct from PRESS-0036, which covers two OTHER documents
  disagreeing with this one.

  1. INV-11 requires asserting that the module's public names are
  exactly PRESS-0005 4.1's list plus this spec's 4.1. store.py declares
  no __all__, so its namespace also carries os, re, tempfile,
  dataclass, datetime, Path and annotations -- an implementer taking
  the invariant literally gets a RED test against correct code. Loop 2
  of that spec's own gate caught this shape once already. Fix: add
  __all__ to store.py and have INV-11 assert against it.

  2. 6's row "A folder is missing | Reading lists nothing" does not
  separate the HANDED folder from the SUB-folder. list_slugs raises
  StoreError for a handed path that is not a directory and returns ()
  for a missing published/. An implementer building list_html from that
  row makes a mistyped folder return silence.

  3. read(path) raises EntryNotFound; 6 has read_comments(path) return
  (). Both take a path and disagree, with nothing in the surface naming
  which applies. The comments choice is well argued; it should be
  stated on read_comments in 4.1 rather than only in a failure table.

  4. Open, and it reaches PRESS-0007 and PRESS-0012: does PRESS-0005 3
  decision 5's Store-wide slug uniqueness extend to templates and
  comments? exists() checks only published/ and drafts/.
  Resolved (2026-09-05). All four items done, and two changed shape once read
  against the code rather than against this bullet. The bullet's premise that
  PRESS-0006 has no code yet is STALE: store.py carries its whole surface and
  tests/test_store_extras.py implements every invariant. So item 1 needed no
  __all__ -- the shipped test already excludes imported names by reading the
  module's AST -- and the fix was to state that rule in INV-11. Item 2's folder
  row was split; item 3 put read_comments' empty result on the call in 4.1;
  item 4 became decision 11, the user deciding slug uniqueness covers entries
  only.

  Then the gate, two loops, three cold lanes each, capped and calm. Fourteen
  verified, fourteen fixed, none dismissed. Loop 3 found seven, not one a Q1 --
  every defect was a rule the code keeps that the document never stated,
  including two the project had already measured by mutation probe and fixed in
  the tests without writing back: INV-10's byte half cannot fail on Linux, and
  INV-11's clause had no backslash case. Re-measured both here. All three lanes
  found the zoned comment date, which PRESS-0090 left unwritten on purpose
  because naming it re-arms this gate; it is INV-12. One Q2 was a leak risk in a
  public repository -- INV-11 said to use a name the archive actually carries,
  where section 7 forbids the archive reaching a fixture.

  Loop 4 found seven more and falsified a rationale loop 3 had just written: the
  Store CAN see two comments sharing an identifier, since each call is handed
  the whole set. INV-13 follows, decided by the user. Its code and test halves,
  with two other test-case gaps, are PRESS-0094 -- filed rather than done, since
  a docs gate does not edit code.
  **Layman:** The newest design document asks for a test that would fail against code that is working correctly.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lane store -- PRESS-0006 read as a contract.

- 📋 [PRESS-0063] **insights.py is the only module with no spec, and its source cites five invariant ids that resolve to nothing a reader may read.**
  Every sibling module names a docs/specs/PRESS-NNNN document. This one
  names its own test file: insights.py:3-4 says "its invariants are
  written down in tests/test_insights.py's header, there being no
  docs/specs file for it". The shipped source then cites INV-1, INV-2,
  INV-7, INV-8 and INV-14, which resolve to nothing outside that
  header.

  This is the circularity verify-delivery exists to catch: the tests
  cannot falsify a contract they ARE.

  spec-format.md 1 may well have answered "no spec" correctly for the
  BUILD decision, and the roadmap records that reasoning. The
  consequence is separate: behaviours that needed deciding were decided
  silently by whatever the tests happened to assert. PRESS-0056 lists
  five of them -- the timeout, the backwards clock, the cache folder,
  the window keying, the property id shape and the zero-visitor report
  -- and each is a question with no answer anybody can breach.

  Route: write-spec for docs/specs/PRESS-0019-insights.md, carrying the
  invariant list currently in the test header, then review-contract.
  Not a code fix.

  Found by the lane that was told it was the only contract review the
  module had ever had.

  SHARPER THAN THE LANE PUT IT: PRESS-0019 is marked SHIPPED. So this
  is not a module awaiting its contract -- it is the only module the
  project has declared done without one, while its own bullet says of
  PRESS-0002 "That contract is written and accepted" and treats that as
  the normal state. Every other shipped module (PRESS-0001, 0002, 0004,
  0005, 0009) names a spec. Whatever is written should therefore be a
  contract for code that already exists and is relied on, which is a
  different job from specifying work not yet done: fold in what the
  implementation settled, and mark as OPEN the questions PRESS-0056
  lists rather than inventing answers the code has not been built to.
  Carries an obligation from PRESS-0056 (2026-09-04, user's decision):
  item 4, the single cache slot. _cached refuses any window but the one
  stored and _store overwrites, so the quota guard protects nothing the
  moment the dashboard offers a second window. Nothing is broken while
  only one window is offered, and how many to cache is a design question
  this spec is the place to answer. Deciding it changes the cache file
  format, so it wants a CACHE_VERSION bump.
  **Layman:** The analytics part of the app has no design document, so its rules live only in its own tests -- which cannot prove themselves wrong.
  Kind: doc.
  Source: review-code 2026-08-31 lane insights.

- 📋 [PRESS-0064] **Two modules that share a folder each document it as holding only their own file, and following either literally deletes the publishing key.**
  Found by two lanes independently. A TRAP FOR THE NEXT IMPLEMENTER
  rather than a live defect -- neither module actually sweeps, and I
  checked: both _discard functions unlink only their own named temp
  path.

  settings.py:232 -- "Leave nothing behind in the folder but the
  settings file (5 INV-7)".
  insights.py:338 -- "Replace the cache with this reply, leaving
  nothing else in the folder."

  design.md:344 puts drafts, photograph originals, the settings file,
  the rolling log, the fetch area, the Insights cache AND ADR-0003's
  owner-only credentials fallback in that same folder.

  Why this is worth an item rather than a shrug: PRESS-0001's own gate
  already had to narrow an over-broad cleanup claim over this folder
  ONCE (recorded on the roadmap), and the same phrasing has now
  reappeared in a second module. An implementer who reads either
  docstring literally and adds a tidy-up deletes the key that can
  rewrite the site.

  Fix: both docstrings to say "leaving no temporary file of its own
  behind", and PRESS-0001 INV-7's wording checked to match.
  **Layman:** Two files carry a comment that, if a future developer believes it, would make them delete the writer's publishing key.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lanes insights/settings -- cross-cutting.

- 📋 [PRESS-0065] **SECURITY.md ships its trust-boundary section unfilled, under a header saying an empty policy is worse than no file.**
  SECURITY.md's Trust boundaries section reads, verbatim, "(Filled once
  design names them.)" -- while the file's own header says "Delete this
  file if this project has no trust boundary ... an empty policy is
  worse than no file -- it claims a promise nobody is keeping." The
  Supported versions and Reporting a vulnerability sections are
  likewise still their template prompts.

  This is not cosmetic. It was the missing input to this sweep's
  threat-model calibration: review-code 4 part 3 requires re-ranking
  raw lane severities against the project's documented threat model,
  and there is none, so the calibration was done against design.md,
  ADR-0003, PRESS-0009 2 and CLAUDE.md instead and had to say so.

  The design HAS now named the boundaries -- the writer's own text
  becoming HTML on a public site (PRESS-0004 5), the publishing key at
  rest (ADR-0003), two third-party APIs over the network, and the entry
  files on disk. Four lines would fill the section.

  Also confirm the intended answer for a pre-1.0 project on Supported
  versions, and pick a private reporting channel that is not the public
  issue tracker -- this repository is public.
  **Layman:** The security policy file promises to list what the app protects and against what, and that section is still the template placeholder.
  Kind: doc-fix.
  Source: review-code 2026-08-31 synthesis -- threat model.

- ✅ [PRESS-0066] **Settings low cluster: the version gate accepts true and 1.0, the repository gate admits query strings, and two rare escapes.**
  All confirmed by execution unless noted.

  1. :84 -- `version != FILE_VERSION`. In Python True != 1 is False and
  1.0 != 1 is False, so {"version": true} and {"version": 1.0} both
  load as if they were 1, where 4.3 requires SettingsError for anything
  that is not 1. Elsewhere this module isinstance-checks carefully.
  This sits on the gate protecting every future migration.

  2. :116-120 -- the owner/name shape gate. Confirmed accepted:
  'o/n?x=y' (adds a query string to every GitHub API call), 'o/n#frag',
  'o/n%2fz' (decoded server-side), 'o/n ' and 'o/n\tz' -- the last two
  not reported by the lane and found in verification. Input is the
  writer's own file so the blast radius is small, and CR/LF is blocked
  by urllib rather than here. NOT the dismissed urlopen finding: that
  one is the scheme, this is the path.

  3. :77 -- deeply nested JSON raises RecursionError, which is neither
  NotSetUp nor SettingsError. Same family as PRESS-0049, far cheaper.

  4. :186-192 -- if os.fdopen itself raises, the raw fd from mkstemp is
  never closed; _discard unlinks the path but leaks the descriptor.
  Rare, real.

  5. :235-236 -- `except OSError: pass` in _discard is the justified
  kind but carries no inline comment saying why. NOTE: the lane tagged
  this [tool: bandit B110] and that attribution is WRONG -- bandit at
  the LOW threshold returns zero B110 hits, because that rule fires on
  bare except:/except Exception:, not a typed except OSError. Logged to
  the false-positive ledger.
  Resolved (2026-09-04): all five closed in 0a1c559. Every claim was
  re-confirmed by execution first -- the stale line numbers aside, all
  five were real. Item 1 now checks the type with the value, since a bool
  is an int in Python. Item 2 states GitHub's own name grammar; the
  second-slash clause went with it as dead code. Verdict-diffed over 46
  values: 18 moved, every one a reject that belongs, and all twelve real
  repository names still load. Items 3 and 4 are one-line and one-block
  fixes. Item 5 wanted no code change and now carries its reason inline;
  the [tool: bandit B110] attribution stays wrong and stays in the ledger.
  Spec §10 corrected -- it claimed nothing checked the version and
  repository shapes, which these tests now do.
  **Layman:** Small holes in the settings file checks that let through values nobody intended.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane settings -- low cluster.

- ✅ [PRESS-0067] **Store low cluster: Windows reserved slugs, a TOCTOU in _move that defeats INV-10, and four smaller round-trip gaps.**
  1. :285-292 -- TOCTOU in _move. `if target.exists(): raise
  SlugInUse(...)` then os.replace. Between the check and the rename a
  second copy of the app -- which 6 names as a real case -- or a hand
  copy can create the destination, and os.replace destroys it
  silently. That is precisely what INV-10 exists to make impossible.
  Fix: os.link then unlink on POSIX (link fails EEXIST), os.rename on
  Windows; keep exists() only for the friendly message.

  2. :50 -- _LEGAL_SLUG admits the Windows reserved device names con,
  aux, nul, prn, com1-lpt9. published/nul.txt cannot be created on
  Windows even with an extension, so an entry saves on Linux and fails
  on Windows. 6 names the path-length trap and not this one.

  3. :110 -- the .txt suffix match is case-sensitive while
  path_for(...).is_file() at :90 is not on Windows, so a file named
  entry.TXT makes exists() true and list_slugs blind to it.

  4. :108 -- a stray file named exactly ".txt" yields an empty slug,
  which then raises out of path_for in every caller that round-trips a
  listing.

  5. :252-254 -- `except BaseException: _discard; raise` re-raises
  non-OSError failures raw, so write() can raise outside the StoreError
  contract 4.1 and 6 state -- a UnicodeEncodeError from a lone
  surrogate in a body, a TypeError from a non-str category.

  6. :229 -- strftime truncates microseconds, so write-then-read does
  not return an equal datetime. No invariant covers it.

  7. :354-359 -- no sweep of orphaned .entry-*.tmp files, so kill -9
  leaves litter against 4.5's "leave nothing behind".
  Progress (2026-09-02): items 1 and 4 shipped; the item stays open for
  the other five.

  Item 1 (TOCTOU): the refusal is now made by the move rather than by the
  exists() check -- os.link then unlink on POSIX, os.rename on Windows,
  both raising FileExistsError instead of replacing. The check stays for
  the friendly message, which is what this item prescribed. Trade-off
  taken knowingly: the POSIX route needs a filesystem with hard links, so
  on one without them a move raises StoreError with the system's own
  message rather than racing quietly. Tested by simulating the window --
  the destination stays on disk and only the check is blinded -- so the
  test is deterministic and an implementation resting on the check fails
  it.

  Item 4 (a file named exactly ".txt"): no longer listed, so no caller
  round-trips an empty slug back through path_for.

  NOT done, and items 2 and 3 are blocked rather than merely queued.
  Both are Windows-parity defects whose fix contradicts the accepted spec,
  so each owes CLAUDE.md rule 14's gate on PRESS-0005:

    2. Windows reserved device names. The spec states "A slug is one or
       more of a-z, 0-9 and -, and nothing else", so `nul` is legal by
       the contract and rejecting it narrows what the document allows.

    3. The .TXT suffix. The spec fixes the entry file as <slug>.txt; a
       case-insensitive match widens that, and matching case-insensitively
       on Windows alone makes the listing platform-dependent, which is its
       own problem.

  Items 5, 6 and 7 are queued and unblocked. Item 5 in particular needs a
  read of what §4.1 and §6 actually promise about which exception type
  escapes write(), which was not done here.
  Progress (2026-09-02, second note): items 2 and 3 shipped. Four of
  seven done; items 5, 6 and 7 remain and the item stays open.

  Both needed PRESS-0005 amended first, because both contradicted it —
  the spec made `nul` a legal slug and fixed the file as `<slug>.txt`.
  The user took both decisions, the amendment ran through rule 14's gate
  (review-contract, two loops to the spec cap, fourteen verified
  findings), and the code was written after it rather than before.

  Item 2: the device names are refused in the one place a name becomes a
  path, so `path_for` and `exists` refuse them as `write` does. Measured
  while gating: `safe_slug("NUL")` returns `nul`, so Import really can
  produce one — and no entry in the export resolves to one today, so
  nothing existing is affected. The whole set is tested, not one member,
  plus six near misses, because refusing too widely would stop an
  ordinary title being addressable.

  Item 3: `list_slugs` and `exists` now share ONE matcher that compares
  the suffix ignoring case. Sharing it is the fix rather than a tidy-up —
  the defect was never in either alone but in the pair disagreeing, and
  the test asserts them together. Proved by mutation that fixing one
  alone fails it. `path_for` still composes exactly, and §4.3 states what
  that costs on Linux.

  Also settled on the way: `exists` raises `StoreError` on an illegal
  slug rather than answering `False`. It always did, through `path_for`;
  the contract now says so, which matters because PRESS-0012 asks it
  about a name the writer typed.

  NOT proved: that any of this behaves as intended ON Windows. The suite
  runs on Linux, and the test box has no Python by design. §10 carries a
  row saying so. PRESS-0022 is where it becomes observable.
  Progress (2026-09-03): items 5 and 7 closed; six of seven done. Item
  6 is in flight and the item stays open.

  Item 5 (the exception contract). The finding named §4.1 and §6 as
  stating a StoreError-only contract for `write`. Neither does — no
  sentence there says which exception types may escape. INV-9 is what
  covers it: "a value the format or the file system cannot carry is
  refused with `StoreError` and nothing is written". A lone surrogate in
  a body is such a value, and `write` raised `UnicodeEncodeError`.
  Measured before fixing.

  `_write_atomically` now catches `UnicodeError` beside `OSError`. The
  up-front check could not have caught it — it reads header values, not
  the encoded bytes — so the refusal has to come from the write. The
  finding's other example, a `TypeError` from a non-str category, was
  NOT fixed: that is a caller passing the wrong type, and turning it
  into a `StoreError` would hide the caller's bug rather than keep a
  promise. The comment on the catch says so.

  Two tests, and the second is the counter-case: INV-9's table gains a
  lone-surrogate body, and a new test asserts a `KeyboardInterrupt`
  mid-save escapes as itself. Without it the rule could be met by
  catching everything, which would report an interruption the writer
  caused as a fault in his entry. Mutation-probed both directions and
  both mutants died.

  Item 7 (orphaned temporary files) — DECLINED, and the finding's cited
  authority does not exist. "Leave nothing behind" is not in §4.5; it is
  `_discard`'s own docstring paraphrasing itself, which is where the
  finding read it. So no contract is breached. Every error route already
  discards the temporary, `BaseException` included, so only a killed
  process leaves one; `list_slugs` matches the suffix and never lists it;
  and a sweep could not tell an orphan from a second copy of Pressless
  writing its own, mkstemp names being random. That would need an age
  heuristic and a race, for litter nothing can see. The docstring now
  states what is true and why there is no sweep, so the next reader does
  not re-derive it. Decided by the user.

  Item 6 (the Date field) is in flight. Measured first, and it is worse
  than the finding says: microseconds truncate, but an aware `datetime`
  silently loses its zone — one written at 21:32:00+02:00 reads back as
  21:32:00, moving the entry two hours. The user chose to refuse an
  aware `datetime` and keep truncating the fraction, because refusing
  that too would reject `datetime.now()`. That contradicts what
  PRESS-0005 allows, so the spec was amended first and CLAUDE.md rule
  14's gate re-armed; the code follows the gate.
  Resolved (2026-09-03): all seven items closed. Five fixed, one
  declined with its reason recorded, one narrowed.

  Item 6 landed last and needed the spec amended first, because refusing
  an aware `datetime` narrows what §4.1's `datetime` annotation allows.
  The user took the decision, `review-contract` ran to the spec cap of 2
  on PRESS-0005 — twelve verified findings, all fixed — and the code was
  written after it. Measured before any of that: an aware `datetime`
  written at 21:32:00+02:00 read back as 21:32:00, and since decision 4
  makes the date supply every address segment but the last, near midnight
  that is a different published address. Worse than the finding said,
  which reported the microsecond half alone.

  The zone is refused and the fraction is truncated, because the losses
  differ: nothing recovers an offset, so the caller is made to decide and
  §4.2 names the decision so Import and the archive test make the same
  one, while a fraction misorders nothing and refusing it would reject
  `datetime.now()`. Two test cases pointing opposite ways; the positive
  one is what stops the rule being met by refusing every `datetime` the
  format cannot hold exactly, proved by a mutation that widens it.

  Item 5 was narrowed on the evidence. The finding named §4.1 and §6 as
  stating a StoreError-only contract and neither does; INV-9 is what
  covers it. So the `UnicodeEncodeError` half was fixed and the
  `TypeError` half deliberately was not — a caller passing a non-str
  category has a bug, and a `StoreError` would hide it.

  Item 7 was declined. Its cited authority does not exist: "leave nothing
  behind" is not in §4.5 but in `_discard`'s own docstring. Every error
  route already discards the temporary, only a killed process leaves one,
  nothing lists it, and a sweep could not tell an orphan from a second
  copy of Pressless writing its own.

  NOT proved, and the same row §10 already carries: none of this is
  observed on Windows. The suite runs on Linux and the test box has no
  Python by design. PRESS-0022 is where it becomes observable.

  Surfaced, not fixed: `write_comment` formats a comment date with the
  same `_DATE_FORMAT` and has no zone guard. Comments are PRESS-0006's
  contract and §9 puts them out of PRESS-0005.
  **Layman:** Small entry-handling problems, including one where two copies of the app running at once could overwrite an entry.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane store -- low cluster.

- 📋 [PRESS-0068] **Credentials low cluster: a PyInstaller build may report every Windows machine as having no credential store, plus three smaller items.**
  1. PACKAGING RISK, and it belongs to PRESS-0022 rather than to this
  file. Every keyring backend, Windows included, is discovered through
  the keyring distribution's entry_points.txt via
  metadata.entry_points(group='keyring.backends'). A PyInstaller bundle
  that does not collect that metadata registers NO backend, so
  _detect_backend falls to fail.Keyring, the probe raises
  NoKeyringError, and on Windows choose() therefore raises NoStore --
  on EVERY machine, with a message asserting the machine has no
  credential store. The discriminator cannot distinguish "no metadata"
  from "no store". Fix in the packaging item: --copy-metadata keyring
  plus pywin32-ctypes. Recorded here so PRESS-0022 inherits it.

  2. :157-163 -- ChainerBackend.delete_password returns on the first
  member that does not raise NotImplementedError, and a member holding
  nothing raises PasswordDeleteError, which the chainer does not catch
  and _delete_probe swallows. So the probe can be left PERMANENTLY in
  the writer's real keyring as Pressless / pressless-store-probe. Not a
  secret, but 4.2's "only then deletes it" reads as an assurance. Fix:
  delete via the answering member, not via the chain.

  3. :131 -- sys.platform.startswith("win") is correct for CPython on
  Windows but false under Cygwin and MSYS2. Marginal, and PRESS-0042's
  mode check subsumes it correctly.

  4. :180 onward -- failure messages carry the account name and the
  full filesystem path, both of which identify the writer. Not a
  repository leak; a bug-report and log-attachment exposure, and it
  interacts with PRESS-0003's rolling log.
  Item 1 fold-back (2026-09-02): the DIAGNOSIS holds and the prescribed
  FIX does not. Measured while writing the PRESS-0022 spec, against
  PyInstaller 6.20.0 and keyring 25.7.0.

  PyInstaller ships hook-keyring.py in its own hooks directory, and its
  two effective lines are exactly what this item asks for --
  collect_submodules on keyring.backends, and copy_metadata on keyring.
  It ships hook-win32ctypes.core.py for the Windows half, and keyring's
  own metadata declares pywin32-ctypes on win32, so a Windows runner
  installs it without being told to. Two onedir bundles were built, one
  with the prescribed flag and one without: identical entry points, and
  both resolved a real chained backend. The flag changes nothing.

  So taking it would be a charm rather than a fix, and worse, an
  invisible one -- a flag duplicating a shipped hook stops meaning
  anything the day the hook changes, and nothing would notice. PRESS-0022
  section 4.3 records the measurement and closes the risk with a check on
  the built artefact instead, which holds whatever the hooks do. That is
  its INV-6, and the gate found and fixed a hole in it: read the store
  KIND, never the member name alone, because PRESS-0002 section 4.2
  returns a file store off Windows and a member name is therefore
  present in exactly the broken case.

  What is NOT settled is Windows. keyring.backends.Windows imports
  win32ctypes inside a function and forces a demand-import, which is the
  shape static analysis is least likely to follow. Only running the
  artefact on Windows answers it, which is what PRESS-0022 is for.

  Items 2, 3 and 4 are untouched and this item stays open for them.
  Progress (2026-09-04). Item 2 is FIXED. _answering_member now returns
  the member rather than its name, choose() hands that member to
  _delete_probe, and the delete is addressed to it; _member_name carries
  the naming half. Deleting through the chain was the defect: its
  delete_password returns on the first member that does not raise
  NotImplementedError, a member holding nothing raises
  PasswordDeleteError, and the best-effort catch swallowed it, so the
  probe stayed in the writer's real keyring for good. No spec was edited
  -- §4.2 already asserts the probe is deleted and INV-7 already requires
  the delete to come after the walk, so this implements both rather than
  narrowing either, and rule 14 asked for no gate.

  INV-7's own fixture cannot see this defect: its chain records a delete
  and pops from its own empty values, so the ordering assertion passes
  while the holder keeps the probe. The new test asserts the EFFECT --
  the answering member holds nothing afterwards -- against a chain that
  raises PasswordDeleteError the way the library does. A mutation probe
  killed all four routes: delete sent to the chain, the caller dropping
  the member argument, delete sent to the first member instead of the
  answering one, and the name taken from something other than the member.

  Item 3 is DECLINED. sys.platform.startswith("win") is false under
  Cygwin and MSYS2, but the finding's own assessment is that PRESS-0042's
  mode check subsumes it, and the supported install path is the packaged
  artefact (PRESS-0022), where sys.platform is win32. Running from source
  under those shells is not an install route this project offers.

  Item 4 is OPEN and needs a decision, not a fix. Confirmed as a real
  exposure: `account` is Settings.credentials.github_account, so a
  credential failure names the writer's own account, and `target` is a
  full path carrying his home directory. Nothing here is a repository
  leak, and no invariant covers it -- INV-6 forbids naming the SECRET and
  says nothing about the account -- so quieting these messages is a new
  rule, which means amending PRESS-0002 §4.3 and re-arming rule 14's
  gate. It also trades diagnosability against anonymity, and it interacts
  with PRESS-0003's rolling log. Put to the user rather than decided here.
  Item 4, the two options put to the user (2026-09-04), neither chosen
  yet: (a) leave the messages as they are and revisit when PRESS-0003's
  rolling log exists, since that is what turns a one-off message into a
  stored record; or (b) drop the account name and shorten the path now,
  which means amending PRESS-0002 §4.3 and paying for rule 14's gate.
  Nothing else in this item is outstanding.
  **Layman:** Once the app is packaged, Windows users could be told their PC has no password store when it does.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane credentials -- low cluster.

- ✅ [PRESS-0069] **Publisher low cluster: a crafted tree entry can write outside the fetch folder, the key sits in a frame local INV-7 cannot reach, and five smaller items.**
  1. :282 -- `target = Path(into) / path` with path taken verbatim from
  GitHub's tree listing, no containment check. A crafted tree entry
  containing .. writes outside `into` (CWE-22). Requires a hand-built
  git object, hence low, but the fix is one line: reject unless
  (into / path).resolve().is_relative_to(into.resolve()).

  2. :315-319 -- INV-7 is tested on str() and repr(), but the key also
  lives as a VALUE in the local headers dict of the frame that raises.
  Any locals-dumping traceback handler or crash reporter in the Face
  exposes it. Not a defect in this module today; it is a hole in what
  INV-7 can promise, and PRESS-0011 is where it becomes one.

  3. :392-398, :171-177 -- _local_files reads EVERY file of the site
  into one dict before anything is compared, and b64encode + json.dumps
  + .encode add about three further copies of each uploaded file.
  ADR-0002 puts the first publish at ~862 files; on a
  photograph-carrying site that is a large resident set on a modest
  Windows box.

  4. :419-422 -- `if not prefix: return True` runs BEFORE rstrip("/"),
  so prefix="/" selects nothing rather than everything.

  5. :465-468 -- a 404 on git/blobs/{sha} or commits/{branch} raises
  RepositoryMissing ("settings.repository resolves to nothing"), a
  false diagnosis for a missing blob or branch.

  6. :163, :220, :280 -- branch name and sha are interpolated into URLs
  unencoded; git permits % and # in a refname and a non-ASCII branch
  raises UnicodeEncodeError out of urlopen.

  7. :395-397 -- rglob("*") + is_file() follows file symlinks and
  includes dotfiles, so anything the Builder leaves in the site folder
  -- a .git/, an editor temp file, a symlink pointing outside -- is
  published verbatim.
  Resolved (2026-09-02) for items 1, 4, 5, 6 and half of 7. Items 2 and
  3 are not closed here and are filed as PRESS-0087 and PRESS-0088; the
  unresolved half of item 7 is PRESS-0089.

  Item 1: both sides resolved and compared before the write, so a tree
  entry carrying .. is refused. Item 4: the empty test now runs AFTER
  the strip, so a prefix of "/" selects the whole site rather than
  nothing. Item 5: only a 404 on the repository itself is
  RepositoryMissing now -- the rest say the repository is there and what
  was asked for inside it is not. No spec change was owed: §6 already
  gives that type one meaning, so this was code diverging from the
  contract. Item 6: refname and sha are percent-encoded, slashes kept,
  since a refname may legitimately be several segments deep.

  Item 7 split. The symlink half is closed: is_file() follows a link, so
  a link left in the site folder had its target read and published to a
  public site. The dotfile half was NOT guessed at -- .nojekyll is a
  dotfile a site needs, and the default untouchable list names it, so a
  blanket skip would break the published site. What it needs first is a
  rule about what the site folder may contain, which is PRESS-0089.

  Five mutations run and all five killed.
  **Layman:** Smaller publishing issues, including one where a crash report could expose the publishing key.
  Kind: review-fix.
  Source: review-code 2026-08-31 lane publisher -- low cluster.

- ✅ [PRESS-0070] **Marks and Insights low cluster: rainbow breaks character references, and five smaller Insights items including silent cache failure.**
  MARKS
  1. :163-171 -- _rainbow escapes one character at a time, so
  _CHAR_REF_OR_AMP's "leave an existing character reference alone"
  branch can never fire inside a rainbow: every & becomes &amp;. So
  {rainbow}A&nbsp;B{/} puts a literal &nbsp; on the page. INV-4 and 4.6
  state the rule unconditionally -- see PRESS-0059 for the document
  side.
  2. :168 -- each non-space rainbow character emits about 45 bytes, a
  ~45x output amplification with no bound; a 10k-character line yields
  ~450 KB of HTML on the published page.
  3. :208 -- {photo:    } yields Photo(name=" ") and photo_src(" ") is
  called. Fail-safe today; folded into PRESS-0055's grammar fix.
  4. :489 -- to_html is public surface and raises a bare KeyError on a
  Span/Photo whose mark is not a table row. 6 documents no such mode.

  INSIGHTS
  5. :359-377 -- every cache-write failure is silent. If target.parent
  does not exist, mkstemp raises on every call, the cache is never
  written, every dashboard open refetches, and the quota guard is
  permanently off with NO observable difference from working
  correctly. The swallow is right; the invisibility is not, against
  design.md's promised rolling log (PRESS-0003).
  6. :204 -- {"startDate": f"{days}daysAgo", "endDate": "today"} is
  days+1 calendar days and its last day is incomplete, so the same
  28-day question answered twice in a day gives two numbers. Fix:
  "yesterday".
  7. :144, :226 -- the HTTP error body is read and DISCARDED. Google's
  400 body says which field was rejected, and design.md's Show details
  toggle then has nothing to show. Carry a length-capped excerpt on the
  exception, never in the writer-facing sentence.
  8. :362 -- no newline="", so this writes CRLF on Windows against
  design.md's "LF line endings written explicitly". settings.py:191
  does the same, so the two have not diverged. Document side is
  PRESS-0060.
  Progress (2026-09-04): item 7 fixed in 21969df -- a capped excerpt of
  Google's error body now rides on the exception, never in the
  writer-facing sentence.

  Item 8 needs NO code change and is closed on inspection: it reports
  insights.py and settings.py writing CRLF for want of a newline argument,
  and both already name one. PRESS-0039 covers it.

  Item 3 belongs to PRESS-0055 by the finding's own words. Item 5 (silent
  cache-write failure) needs the rolling log PRESS-0003 files -- the
  swallow is right and the invisibility is not, and there is nowhere yet
  to make it visible. Item 6 (the window ends at "today", so the same
  question answered twice in a day gives two numbers) has a named fix, but
  it changes what the writer reads on the dashboard and an existing test
  pins the current range; put to the user rather than decided here. Marks
  items 1, 2 and 4 are untouched -- a separate file and a separate
  reading.
  Progress (2026-09-04), on the user's decisions. Item 6 is DECIDED, not
  fixed: the window goes on ending at "today". The fresher number was
  chosen over the one that holds still, and the code now says so at the
  dateRanges site so the next reader does not "fix" it. Item 5 is routed
  to PRESS-0003, which files the rolling log -- the swallow is right and
  there is nowhere yet to make it visible.

  Still open, and all in marks.py: items 1, 2 and 4. Item 4 (to_html
  raising a bare KeyError on a mark that is not a table row) looks like a
  decline on the precedent set for PRESS-0067 item 5 -- parse() turns an
  unknown mark into literal text by §6, so reaching that line means a
  caller hand-built a Document, which is a programming error a typed
  failure would hide. Item 1 (rainbow breaking character references) has
  two possible answers and PRESS-0059 proposes the document one; item 2
  (the unbounded output amplification) needs a bound nobody has chosen.
  None is decided here.
  Progress (2026-09-04), on the user's decisions. Items 2 and 4 are
  DECLINED, not fixed. Item 2 (unbounded rainbow output amplification): a
  rainbow only ever comes from what the writer types, since the import
  carries no Pressless marks, so the size is already bounded by hand
  typing; a cap would silently drop what was asked for and nobody has a
  number to justify. Item 4 (to_html raising a bare KeyError on a mark
  that is not a table row): declined on the PRESS-0067 item 5 precedent --
  parse() turns an unknown mark into literal text, so reaching that line
  means a caller hand-built a Document, and a typed failure would hide a
  programming error. Item 1 (rainbow breaking character references) is to
  be FIXED in the code: the spec is right as written, so no document edit
  and no contract gate.
  Resolved (2026-09-04). Every item now has a disposition. Item 1 is
  FIXED: _rainbow walks character-reference-or-character units, built from
  _CHAR_REF_OR_AMP's own pattern so §4.6's grammar keeps one copy, and a
  reference takes one span per §4.2. INV-4 and §4.6 state the rule with no
  carve-out for {rainbow}, so the spec was right and no document was
  edited. Verified by a verdict diff of the old walk against the new over
  the archive's own prose: every line whose output moved carries a
  character reference, and none moved without one. The gate ran with the
  export present, so INV-5's byte-identity run still holds. A mutation
  probe over the routes the defect could return by found the test pinned
  one entity name; a numeric reference now closes that route. Items 2 and
  4 are declined and items 3, 5 and 6 were routed or decided earlier; item
  8 needed no code change.
  **Layman:** Small display and reporting problems, including one where the app silently stops caching and nobody can tell.
  Kind: review-fix.
  Source: review-code 2026-08-31 lanes marks/insights -- low cluster.

- ✅ [PRESS-0071] **No tool in the check-code set catches a missing urlopen timeout, and the sweep proved the expensive lanes earned their cost.**
  Recorded so the next sweep does not re-derive it.

  1. THE GAP. bandit's B113 (request_without_timeout) reads the
  requests and httpx modules only -- verified by reading the plugin
  source, which does not mention urllib. So PRESS-0041 is caught by NO
  tool in the set. This is a gap in the AVAILABLE tooling rather than
  in how check-code was configured, and it will not close by adding a
  tool row. Options: a project-specific semgrep rule for
  urlopen-without-timeout, or accept that it is a review finding.

  2. NOT TOOL-DECIDABLE EITHER. ruff --select BLE returns clean on
  src/, correctly, because the code re-raises -- so PRESS-0040 is
  findable only by knowing HTTPException is not an OSError.

  3. A DISMISSED FINDING IS NOT A CLEAN LINE. bandit B310 fired on both
  urlopen sites and was correctly dismissed for the scheme -- and sat
  one line from two real HIGH defects, pointing at neither.

  4. THE MEASUREMENT. Zero of the eleven HIGH-and-above findings from
  review-code were reachable by any tool in the set. On this tree the
  expensive sweep is not redundant with check-code.

  5. CONFIGURATION, separate from the above and worth a decision:
  [tool.ruff] sets line-length and target-version but no `select`, so
  ruff runs its default E4,E7,E9,F -- E501 is never enforced and the
  declared 100-column limit is decorative, and bugbear (B) and the
  bandit rules (S) are off. A supplementary run with --select E,F,B,S
  found 191 findings, 179 of them S101 in tests. Adding `select` plus a
  tests/** per-file-ignore for S101 is a project decision, not a
  suppression.
  Worked 2026-09-04.

  Item 1 CLOSED, by a third option the item did not list. No semgrep rule
  and no accepting it as a review-only finding: tests/test_network_timeouts.py
  walks the AST for every network open in src/ and asserts each passes a
  timeout. That is this project's existing idiom, so it costs no dependency
  and runs in the gate already. It walks all of src/ rather than the two
  modules that open a socket today, so a third is covered when it is
  written. Probed: removing either opener's timeout kills it, and so does a
  matcher recognising nothing or a glob finding no source.

  Item 5 was already CLOSED, by PRESS-0077, before this session. Measured
  today: [tool.ruff.lint] sets select = E, W, F, I, B, S, UP with reasoned
  per-file ignores, and ruff --select E,F,B,S over src/ and tests/ is
  clean. The 100-column limit is enforced. This item's text still reads as
  though the decision is outstanding; it is not.

  Items 2, 3 and 4 are a RECORD rather than work -- what the tools can and
  cannot decide on this tree, and the measurement that zero of the eleven
  HIGH findings were tool-reachable. Nothing to do; they are the reason the
  item says "recorded so the next sweep does not re-derive it".

  So every actionable half of this item is now done.
  Resolved 2026-09-04. The investigation is concluded and both actionable
  halves are closed; items 2 to 4 stay in the body as the record they were
  filed to be. Flipped rather than left open because a 📋 says work is
  outstanding, and none is.
  **Layman:** A note for next time about which problems the automatic checkers can and cannot find here.
  Kind: investigate.
  Source: review-code 2026-08-31 synthesis part 4 -- tool gaps.

- ✅ [PRESS-0072] **If GitHub rejects mode and type on a deletion tree entry, every publish containing a deletion fails, and nothing here can find out.**
  The sharpest thing the sweep could NOT settle, and it had no item
  until now.

  publisher.py:198-200 sends a removal as {"path": ..., "mode":
  "100644", "type": "blob", "sha": None}. GitHub documents deletion as
  setting sha to null against a base_tree. Whether it ALSO accepts
  mode and type on that entry is not stated, and PRESS-0009 10 declares
  the live API an unrunnable region -- so no test in this repository
  can answer it and the transport double never exercises it.

  If GitHub rejects the entry, every publish containing a deletion
  fails at the tree step. That fails SAFELY -- before the reference
  update, so the site is unchanged -- but it means the delete half of
  publish has never executed successfully anywhere, and the first real
  publish that removes a file is the first test of it.

  Pairs with PRESS-0045, the missing Content-Type: both are
  assumptions about GitHub's tolerance that nothing local can check.

  Route: one manual call against a scratch repository, or a recorded
  fixture. Cheap to answer, and the answer decides whether PRESS-0015
  (undo) rests on a working mechanism.
  Resolved (2026-09-02) by execution against a throwaway private
  repository, with the user's agreement. GitHub ACCEPTS the entry, and
  the control reverses this item's worry.

  Measured, in publisher.py's exact shape -- path, mode 100644, type
  blob, sha null, against a base_tree:

    POST git/trees  -> 201, and the returned tree no longer holds the
                       path
    POST git/commits, then PATCH git/refs/heads/main with force false
                    -> 201 and 200; the file then 404s on the branch

  So the whole delete path executes end to end, not merely the tree step,
  and the reference update is a fast-forward as section 4.5 expects.

  The control is the useful half. The same deletion WITHOUT mode and type
  is REFUSED:

    422  "Must supply a valid tree.mode"

  So mode is REQUIRED rather than merely tolerated, and this item had the
  risk backwards: the danger was never that Pressless sends too much, it
  is that a later tidy-up removing mode or type from the deletion entry
  would break every publish containing a deletion. Worth a comment at the
  call site rather than an invariant, since the API refuses it loudly.

  PRESS-0015 (undo) therefore rests on a mechanism proven to work.
  The scratch repository was created solely for this and is being
  removed.
  Correction (2026-09-02): the note above says the scratch repository "is
  being removed". That was not true when written and is still not true.
  The gh token carries gist, read:org, repo and workflow, and deleting a
  repository needs delete_repo — so the delete returned 403 and
  milnet01/gh-tree-deletion-probe is STILL PRESENT.

  It is private and holds nothing but the probe. Removing it needs either
  `gh auth refresh -h github.com -s delete_repo` and then
  `gh repo delete milnet01/gh-tree-deletion-probe --yes`, or one click in
  the browser. Recorded rather than left in a chat window, because the
  finding above is settled and this loose end would otherwise outlive the
  session that made it.
  **Layman:** The way the app tells GitHub to delete a file may not be a form GitHub accepts, and there is no way to check without trying it for real.
  Kind: investigate.
  Source: review-code 2026-08-31 lane publisher -- open question.

- 🚧 [PRESS-0073] **Four more untyped escapes and a library config path that can execute code, none of them covered by the typed-failure items.**
  Residue from two lanes' dim-7 findings that PRESS-0040 (the
  http.client family) does not cover.

  PUBLISHER
  1. :280 -- f"git/blobs/{entry['sha']}" raises a bare KeyError on a
  tree entry lacking sha. _blobs_in:386 correctly uses .get; this site
  does not. Use _required.
  2. :284 -- target.write_bytes in fetch_previous raises a bare OSError
  on a full disk.
  3. :397 -- path.read_bytes in _local_files raises a bare OSError on an
  unreadable local file.
  All three escape PRESS-0009 4.1's "every failure ... is one of the
  types above".

  CREDENTIALS
  4. keyring's core._load_keyring_path prepends a keyring-path value
  from ~/.config/python_keyring/keyringrc.cfg to sys.path before
  importing the named class. So keyring.get_keyring() can execute code
  from a user config file. Inherited from the library and nothing this
  module can prevent beyond PRESS-0050's guard, which converts the
  failure into a typed one but does not stop the import. Recorded so it
  is a known property rather than a surprise.

  5. OPEN, and it decides whether PRESS-0051 is live or latent: does
  the Face format __cause__ when it logs a CredentialError? PRESS-0011
  and PRESS-0003 own the answer. If it does, a backend message quoting
  the secret reaches the rolling log.
  Progress (2026-09-02): items 1, 2 and 3 are fixed and tested -- the
  bare KeyError on a tree entry with no sha, the bare OSError writing a
  fetched file, and the bare OSError reading a local one. Three
  mutations killed. The disk-full case is arranged as a folder that is
  really a file, which is the same OSError by a route that works on both
  systems.

  In progress rather than shipped, because two items are not code this
  item can write.

  Item 4 is a property of the keyring library, not a defect here: its
  config file can prepend a path to sys.path before importing the
  backend it names. PRESS-0050's guard now converts the resulting
  failure into a typed one, which is all this module can do; it does not
  stop the import. Recorded, which was this item's own stated purpose
  for it.

  Item 5 is the open question, and it is the reason this stays open:
  does the Face format __cause__ when it logs a CredentialError?
  PRESS-0011 and PRESS-0003 own the answer, and it decides whether
  PRESS-0051 was live or latent. PRESS-0051 raises from None now, so the
  answer no longer changes what is safe -- only what was true before it.
  **Layman:** A few more ways the app can fail with an unexpected error instead of a clear message.
  Kind: review-fix.
  Source: review-code 2026-08-31 lanes publisher/credentials -- residue.

- ✅ [PRESS-0074] **Eight smaller lane findings and open questions that no other item picked up.**
  STORE
  1. _parse_list drops whitespace-only values and strips each, so
  categories=(" ",) round-trips to () and ("a ",) to ("a",). INV-9
  refuses neither.
  2. read accepts a slug the Store can never write back: only
  stem-versus-header equality is checked, not _LEGAL_SLUG, so a
  hand-created My_Entry.txt reads fine and fails on save.
  3. mkstemp creates at 0600, so every save silently narrows an
  existing entry's permissions from the umask default. Harmless, and
  nothing documents it. Same shape as the settings-side note in
  PRESS-0057.
  4. OPEN: exists() raises on an illegal slug via path_for, while
  PRESS-0005 4.1 types it -> bool and 6 does not list it among the
  raising calls. PRESS-0012 asking "is this proposed slug free?" about
  user-typed text gets an exception rather than False.
  5. OPEN, PRESS-0006: a comments object MISSING one of the six fields
  has no row in 6, which specifies only the extra-field case.

  MARKS
  6. Mark.arg is stored as a pattern STRING, so every brace on every
  line pays an re-cache lookup rather than using a compiled object.
  re's 512-entry cache makes this cheap, not free.
  7. {accent}{/} parses to a Span with no children and emits an empty
  coloured span. Harmless; not in 6.

  INSIGHTS
  8. OPEN: is AGGREGATE_PREFIX (:59-62) live or inert? The comment
  claims Google returns aggregate rows "in the rows themselves"; the
  lane's reading of v1beta is that RESERVED_TOTAL appears in the
  totals[] rows instead, which would make the filter at :267 dead code
  AND the comment wrong about the external API. Behaviourally free, but
  _total's hard failure rests on that model.
  9. OPEN: nothing lets the writer force a refresh -- read() has no
  bypass for max_age_seconds, while PRESS-0020 shows when the numbers
  were last updated, which invites a refresh button this signature
  cannot serve.
  Worked 2026-09-04. Every item was executed before it was judged, and
  three of the four OPEN questions were settled by that run rather than by
  reading.

  FIXED. Item 2 -- confirmed: read returned an Entry write then refuses.
  The guard is in read now, reusing _refuse_illegal_slug; PRESS-0005 6
  gained a row. No gate: 4.2 states the rule of a slug, not only of one
  being written, so this implements it. Item 5 -- the code already refuses
  a missing field; only PRESS-0006 6 lacked the row, now added. Item 8 --
  the comment asserted the aggregate is NOT separated out while _total
  reads it from totals, two models of one API in one module. The comment
  now states what the code does and marks the rest unsettled; the filter
  stands. Which reading is right could not be measured here: the analytics
  MCP exposes no metric_aggregations argument, so no available caller
  makes _fetch's request.

  CLOSED, NOT A DEFECT. Item 4 -- already fixed. exists calls
  _refuse_illegal_slug directly and PRESS-0005 4.1 and 6 both say it
  raises; the PRESS-0005 loop-4 gate closed it. Item 9 -- wrong as stated.
  max_age_seconds IS the bypass: measured, read(..., max_age_seconds=0)
  refetches past a fresh cache and returns stale=False. PRESS-0020 needs
  no new signature.

  DECLINED. Item 1 -- the strip is documented and a whitespace-only
  category is not a category; no invariant claims a byte round trip for
  Categories or Tags. Item 6 -- re's cache makes it cheap, and a compiled
  object is the over-engineering the item itself hedges. Item 7 -- an
  empty coloured span is inert in the page.

  STILL OPEN, and it is the same question as PRESS-0057's. Item 3 --
  measured: a fresh write is 0600 and a rewrite narrows an existing 0644
  back to it. PRESS-0057's tail carries the identical unsettled note on
  the settings side. What the mode SHOULD be is one decision for both
  documents, and taking it here would change direction in PRESS-0005
  alone. Settle it on PRESS-0057's gate and apply the answer to both.
  Resolved 2026-09-04. Three fixed, two closed as not defects, three
  declined; item 3 is now PRESS-0057's, which owns the decision for both
  documents. Nothing here is left unrouted.
  **Layman:** A tidy-up list of small things the review noticed that did not fit anywhere else.
  Kind: review-fix.
  Source: review-code 2026-08-31 lanes store/marks/insights -- residue.

- 📋 [PRESS-0075] **The test tree is larger than the code it tests and has never been reviewed, and three invariants are already known to be unfalsifiable.**
  tests/ is 4,298 lines against 2,256 lines of src/. No sweep has ever
  looked at it: check-code decides tool findings, review-code's scope
  is production code, and review-tests has not been run on this
  project.

  This is not speculative -- the code sweep already found three
  invariants whose test surface cannot observe the thing the invariant
  asserts, each found by a different lane:

    PRESS-0001 INV-5  fixture patches os.replace, so it cannot see the
                      missing fsync that makes 4.4's claim untrue
    PRESS-0002 INV-6  uses patched stores, so it proves only that the
                      module's own literals are clean
    PRESS-0006 INV-11 as written cannot pass against correct code

  Three in one sweep, from lanes that were not looking for them,
  suggests the population is larger.

  CLAUDE.md already records two more of this kind: test_marks_is_pure
  passes against any module importing nothing forbidden, an empty file
  included; and with marks.py absent the suite errors at COLLECTION, so
  a run that says nothing failed may have run nothing.

  Route: review-tests. Baseline for its run: 66 collected, 66 passed
  with PRESSLESS_ARCHIVE set; 62 passed and 4 skipped without it.
  Known gap (2026-09-04), found by mutation probe while closing
  PRESS-0070 and recorded here because this item is where test-tree gaps
  belong. Nothing pins PRESS-0004 §4.2's rule that whitespace inside a
  rainbow is emitted bare and does not advance the index: the guard can
  be removed and the suite stays green. Pre-existing rather than new --
  the rainbow row had no tests at all until PRESS-0070 -- so it was left
  alone rather than widening that item's scope.

  The same probe found two live examples of the wider defect this item
  names. PRESS-0068's INV-7 fixture could not catch its own bug: the fake
  chain recorded a delete and popped from its own empty values, so the
  ordering assertion passed while the probe stayed in the holder. And a
  test docstring claimed to catch a condition it did not measure. Both
  are now closed. The lesson for this item's eventual sweep: run the
  probe rather than reading the assertions, because a test that passes
  and a test that watches look identical from the outside.
  **Layman:** The tests have never been checked, and we already know three of them cannot fail even if the thing they check is broken.
  Kind: test.
  Source: review-code 2026-08-31 synthesis part 5 -- coverage gap.

- 📋 [PRESS-0076] **Nothing has ever checked whether this project's dependencies, runtime, runner image or action pins are current.**
  Explicitly out of scope for the 2026-08-31 sweep and recorded here so
  the gap is not mistaken for a clean result. check-code holds pinact
  but no signal selects it, so an ordinary run does not answer the pin
  question at all, and review-code's scope excludes versions.

  The surfaces that exist today:

    pyproject.toml   keyring>=25 (the sole runtime dependency), plus
                     pytest, pytest-randomly and ruff in [dev]
    ci.yml           python-version 3.13, runs-on ubuntu-latest,
                     actions/checkout and actions/setup-python, both
                     already pinned to a commit sha with a version
                     comment -- so the question is staleness rather
                     than mutability
    future           Pillow joins when photographs land (PRESS-0016),
                     PyInstaller when packaging lands (PRESS-0022)

  Note pyproject.toml already carries a hold reason for the keyring
  floor -- 25 is the oldest release where .backends resolves on a chain
  -- which is what dependencies.md asks for, so that pin is documented
  rather than accidental.

  Route: check-dependencies. Worth running before PRESS-0022, since
  packaging is where a runtime version stops being a detail.
  **Layman:** Nobody has checked whether the outside pieces the app relies on are up to date.
  Kind: chore.
  Source: review-code 2026-08-31 synthesis -- coverage gap.

- ✅ [PRESS-0077] **One gate tool cannot run at all for want of a config section, and another runs against defaults nobody chose.**
  Both reported by the whole-tree check-code run and neither is a code
  defect. Filed because a tool that cannot run looks exactly like a
  tool that found nothing.

  1. SHFMT NEVER RUNS. It is skipped as "no config to run against",
  correctly: .editorconfig has [*] indent_size = 2 plus sections for
  *.md, Makefile, C/C++, Go and Python, and NONE whose glob selects
  *.sh. check-code treats a blanket [*] as not a declaration for shell
  -- deliberately, on a measurement where the loose reading produced
  397 diff lines against a conforming project. So shell formatting is
  checked by nothing. Fix: add an [*.sh] section stating the shell
  style actually used (the hooks and local-ci.sh are 4-space), which
  turns the tool on.

  2. YAMLLINT HAS NO PROJECT CONFIG, so its defaults apply and it
  reports 6 findings on .github/workflows/ci.yml: missing document
  start at 4:1, truthy `on:` at 6:1 (a known GitHub Actions quirk that
  is not a defect), two "too few spaces before comment", and two lines
  over its 80-column default -- against a repository whose Python is
  set to 100. Nobody chose 80 for YAML. Fix: a .yamllint pinning the
  line length and disabling truthy for workflow files, or accept the
  six and record that.

  3. Related and already recorded in PRESS-0071 item 5: [tool.ruff]
  sets line-length and target-version but no select, so the declared
  100-column limit is not enforced and bugbear and the bandit rules are
  off.
  Resolved (2026-09-02). All three decided by the user and applied; the
  gate is green with every tool now running.

  Item 1, shfmt: .editorconfig gains an [*.sh] section at 4 spaces,
  measured from the files rather than chosen. Turning it on was NOT free
  -- it reformats the gate script and three hooks, all of it expanding
  one-line brace groups. That contradicts what I told the user when
  recommending it, and the reformat is applied rather than deferred.
  Behaviour preserving: gate green, hooks still executable.

  Item 2, yamllint: .yamllint pins the width to ruff's and disables the
  truthy check, which was objecting to the spelling GitHub requires for
  a workflow trigger. ci.yml is clean under it.

  Item 3, ruff select: E, W, F, I, B, S, UP. Eleven findings. Four S310
  and three S314 are suppressed with their reasons recorded beside them
  -- both urlopen sites build their URL from a module-level literal, and
  the archive tests parse the writer's own export. The four B905 are
  fixed rather than suppressed: two intend truncation and now say so,
  two sit under a length check and now assert it.

  Worth recording because it bears on what this check buys: NONE of the
  eleven was a latent bug. Every zip already handled the mismatch. The
  value delivered is that three tools which reported nothing now actually
  run.
  **Layman:** One of the automatic checkers is switched off by accident, and another is complaining about things nobody decided were wrong.
  Kind: chore.
  Source: check-code --tree 2026-08-31 -- config recommendations.

- 📋 [PRESS-0078] **The untouchable list matches case-sensitively, and on Windows the local filesystem does not.**
  Raised as an open question by the publisher lane and not filed by
  the first pass.

  Verified in source:
    untouchable=("CNAME",) protects remote "CNAME" -> True
    untouchable=("CNAME",) protects local  "cname" -> False

  _is_protected compares exactly. GitHub's paths are case-sensitive;
  the Windows local filesystem is not. So a writer whose site folder
  holds "cname" while the repository holds "CNAME" produces two
  distinct paths: the local one is uploaded as a new file, and the
  remote one appears in no local listing, which puts it in `removed`
  unless the untouchable entry happens to match its exact casing.

  That is the deletion PRESS-0009 2 calls unrecoverable, reached by a
  difference in capitalisation.

  Distinct from PRESS-0044, which is about the two diverged matchers
  and fires on entry SHAPE. This one fires on entry CASE and would
  survive that fix.

  Not decided here because answering it needs the Setup spec
  (PRESS-0021), which does not exist yet: whether Setup normalises what
  it writes, and whether matching should be case-insensitive on Windows
  only or everywhere, is a decision that belongs with the code that
  derives the list.

  Related and already filed: PRESS-0067 records the same
  case-sensitivity shape in store.py, where a .TXT suffix makes
  exists() true and list_slugs blind.
  **Layman:** A protected file could be missed on Windows because the app and GitHub disagree about whether capital letters matter.
  Kind: investigate.
  Source: review-code 2026-08-31 lane publisher -- open question.

- 📋 [PRESS-0079] **Design rule 8 lets Insights talk to Google alone, and four more sources are wanted.**
  docs/design.md § What may depend on what, rule 8: "Insights may read
  Settings, may talk to Google, and keeps one cache file in Pressless's
  own folder -- and nothing else." Taken literally that forbids every
  source the writer has now asked for, so the rule is widened before any
  of them is built rather than breached four times.

  What the amendment has to settle, not just permit: whether one cache
  file still serves N sources or each keeps its own, and whether the rule
  names services one by one or states a shape ("read-only, outward, and
  nothing about writing or publishing may depend on it"). The second
  reads better and stops the rule needing an edit per service.

  Rule 10 already carries the pattern for the secrets -- the Face fetches
  each one from Credentials and hands it over as an argument -- so it
  needs widening only in the same breath, not redesigning.

  Editing design.md re-arms global rule 14's cold-eyes gate, which is the
  real cost of this item and the reason it is filed rather than done in
  passing.

  Blocked-by: nothing.
  **Layman:** The design says the stats part may only talk to Google. Adding YouTube, Spotify, Apple and Amazon means changing that rule first.
  Kind: doc.
  Source: user-request-2026-09-02.
  Lanes: Insights, design.

- 📋 [PRESS-0080] **Whether the three music services publish listening figures at all, and by what route.**
  The three music items behind this one all assume figures can be
  fetched. That assumption is doubtful and checking it is cheap, so it is
  checked once here rather than discovered three times during
  implementation.

  The position to disprove, held as of filing and NOT taken as settled --
  re-read each service's own current documentation, because this is
  recalled rather than verified and these surfaces change:

  - Spotify's Web API returns catalogue data, an artist's follower count
    and a 0-100 popularity score. Stream counts and listener numbers are
    Spotify for Artists', which has no public API.
  - Apple's Music API is catalogue too. Apple Music for Artists has no
    public API.
  - Amazon Music for Artists has no public API.

  If that holds, the honest answer for those three is not an app that
  fetches figures. The fallback worth pricing is the export each service
  offers a signed-in artist: a file he downloads and Pressless reads,
  which needs no API and no secret, and shows figures dated to the last
  download rather than live.

  Deliverable: for each of the three, one of -- a usable API, a
  downloadable export, or nothing -- with the documentation page that
  says so. YouTube is not in scope here; its two APIs are public and its
  item is startable.

  Blocked-by: nothing.
  **Layman:** Before building anything, find out whether Spotify, Apple and Amazon actually let an app fetch his listening figures -- they may not.
  Kind: investigate.
  Source: user-request-2026-09-02.
  Lanes: Insights.

- 📋 [PRESS-0081] **Insights asks YouTube how the channel and its videos are being watched.**
  Two levels, because the writer asked for both: the channel as a whole,
  and the individual videos and music on it.

  The startable one of the four. Google publishes two APIs and they
  answer different questions. The Data API v3 gives public counts --
  views, likes, comments per video, subscribers per channel -- and needs
  only an API key. The Analytics API gives the owner-only figures --
  watch time, how far through people get, where they came from -- and
  needs OAuth as the channel's owner. Decide which the dashboard is
  asking for before building; the public counts alone may be the whole
  of what was wanted, and they are far cheaper to reach.

  It sits behind the same wall PRESS-0019 put Google Analytics behind:
  read-only, outward, and nothing about writing or publishing may depend
  on it. If YouTube is unreachable, or he never sets it up, the rest of
  the app is unaffected. The secret comes from the Face as an argument,
  per design rule 10.

  No spec expected -- one subsystem, and the shape is PRESS-0019's,
  already built and tested. Confirm against spec-format.md § 1 rather
  than assuming.

  Blocked-by: PRESS-0079.
  **Layman:** The dashboard also shows how his YouTube channel is doing, and how each video and music track on it is doing.
  Kind: feature.
  Source: user-request-2026-09-02.
  Lanes: Insights.

- 📋 [PRESS-0082] **Insights shows how the music is doing on Spotify.**
  What this fetches, and whether it can fetch anything, is PRESS-0080's
  to answer first. The doubt is specific: Spotify's public API is a
  catalogue API, and the stream and listener figures an artist actually
  wants live in Spotify for Artists behind a sign-in.

  So there are two shapes this could take and PRESS-0080 picks one. If
  an API reaches the figures, this is PRESS-0019's shape again. If it
  does not, the honest version reads an export he downloads himself,
  shows the figures dated, and says on the dashboard when they were last
  refreshed -- which is worth building and is not what was asked for, so
  it goes back to him before it is built.

  What is reachable without a sign-in either way, and may be enough:
  follower count and Spotify's own popularity score for each release.

  Blocked-by: PRESS-0079, PRESS-0080.
  **Layman:** The dashboard also shows how his music is doing on Spotify.
  Kind: feature.
  Source: user-request-2026-09-02.
  Lanes: Insights.

- 📋 [PRESS-0083] **Insights shows how the music is doing on Apple Music.**
  Same shape as the Spotify item and the same doubt, one step worse:
  Apple's Music API is a catalogue API, and Apple Music for Artists --
  where the play figures are -- is believed to publish no API at all.
  PRESS-0080 confirms or refutes that.

  If it publishes none, the export route is the only one, and this item
  becomes reading a file he downloads rather than talking to Apple.
  That is a different feature from the one asked for, so it goes back to
  him rather than being substituted quietly.

  Apple's catalogue API also needs a developer token signed with a
  private key from a paid developer account, which is a cost the other
  three do not carry. Price that before committing to it.

  Blocked-by: PRESS-0079, PRESS-0080.
  **Layman:** The dashboard also shows how his music is doing on Apple Music.
  Kind: feature.
  Source: user-request-2026-09-02.
  Lanes: Insights.

- 📋 [PRESS-0084] **Insights shows how the music is doing on Amazon Music.**
  The least likely of the four to be buildable as asked. Amazon Music
  for Artists is believed to publish no public API whatever, so unlike
  Spotify and Apple there may be no catalogue surface to fall back on
  either. PRESS-0080 settles it.

  If that holds, the only routes are an export he downloads, or nothing
  -- and "nothing" is a real outcome to report rather than a failure to
  work around. Do not reach for scraping the artist dashboard: it needs
  his sign-in, it breaks whenever the page changes, and it is the kind
  of thing that gets an account suspended.

  Blocked-by: PRESS-0079, PRESS-0080.
  **Layman:** The dashboard also shows how his music is doing on Amazon Music.
  Kind: feature.
  Source: user-request-2026-09-02.
  Lanes: Insights.

- ✅ [PRESS-0085] **The fallback credentials file is read through a symlink, with neither owner nor mode checked.**
  Split out of PRESS-0042 rather than folded into it, because the
  write side was mandated by ADR-0003 and this side is not: it needs a
  decision that contradicts a design choice already written down.

  _read_mapping uses Path.read_text, which follows a symlink and checks
  neither st_uid nor the mode. So on a shared or removable drive another
  user can substitute the file and read() hands their secret to the
  Publisher.

  WHY IT WAS NOT FIXED WITH THE WRITE SIDE: _write_file's own comment
  records the design -- "read() carries no such refusal: reading one back
  is how such a machine is recovered". Adding a refusal to the read path
  therefore changes direction rather than recording what was built, so it
  owes CLAUDE.md rule 14's gate on PRESS-0002 before any code lands.

  The two candidate rules are not equivalent and the choice is the work.
  Refusing on MODE breaks the recovery case the comment protects: a file
  carried from a machine that wrote it permissively is exactly what
  recovery reads. Refusing on OWNERSHIP does not -- a file copied or
  restored by the writer is owned by the writer -- and O_NOFOLLOW closes
  the symlink half without touching either. Ownership plus O_NOFOLLOW
  looks right; it is not obviously right, which is why it is filed.

  Severity is below PRESS-0042's. The substituted secret is used against
  settings.repository, so it fails to authenticate rather than publishing
  anywhere the attacker chose, and os.replace replaces a symlink rather
  than writing through it, so the write path is not a route to another
  user's file.
  Resolved (2026-09-02): every read of the fallback file now goes
  through _read_ours -- O_NOFOLLOW where the platform offers it, so a
  symlink is refused by the open rather than followed, then the owner
  read off the open descriptor. Both raise CredentialError. The mode is
  not checked, which is what keeps the recovery case working.

  The decision this item said it owed was taken the way it said: §3
  decision 6 of the PRESS-0002 spec was written and re-gated under rule
  14 before any code landed. Two cold loops, every verified finding
  fixed, cap reached.

  Two of those findings decided the shape. Guarding read() alone leaves
  the attack intact, because write()'s pre-read would merge a planted
  file forward into one the writer then owns, which a later compliant
  read() accepts -- both paths already shared _read_mapping, so the fix
  sits there. And the first draft of INV-10's test passed against the
  defect: a symlink to any ordinary file fails to parse and raises the
  right error for the wrong reason, so the target has to be a
  well-formed file holding a different secret.

  Scoped honestly, and the spec says so: ownership reaches a shared
  POSIX drive and not removable media, where every file reports the
  mounting user. The symlink refusal holds on both. Windows offers
  neither check, so the read there is unchecked -- stated as the
  intended end state, since nothing on Windows writes this file and
  refusing a carried one would refuse the recovery.

  Four mutations run and all four killed, including the over-strict one
  that refuses on mode. Not verified on Windows.
  **Layman:** Another user on a shared drive could swap the file holding the publishing key, and the app would read theirs without noticing.
  Kind: security.
  Source: in-session-2026-09-02, split from PRESS-0042.

- 📋 [PRESS-0086] **Most open items belong to no milestone, so "what gets us to v1.0.0" has no complete answer.**
  ROADMAP section Milestones says every one of the 22 items above belongs
  to exactly one milestone and none to two. That was true when written.
  Measured 2026-09-02: 61 items are open, 14 of them are in a milestone,
  and 47 are in none — everything the reviews filed (PRESS-0028 onward)
  plus self-update.

  So the milestone map answers "what gets us to v0.1.0" for the original
  build items and is silent about the rest, which is most of the queue.

  The obvious fix does not work, and that is why this is an item rather
  than an edit. Section Milestones is a store-held section intro; no verb
  amends one, and a hand edit to ROADMAP.md is discarded by the next
  render. That is also why its count still reads 22. CLAUDE.md records
  the trap.

  The route that does work: put a Milestone: line on each item's own
  body, which roadmap_log op:amend_field and op:annotate can both reach.
  The map then lives with the items rather than in a paragraph that
  cannot be corrected, and it stays true as items are filed. Section
  Milestones keeps the prose about what each version MEANS, which is the
  half worth having there and the half that does not go stale.

  Decide first whether every review-fix item needs a milestone at all. A
  defect in shipped code arguably belongs to the release that ships the
  fix rather than to a goalpost, and forcing all 47 into three buckets
  may be inventing structure. The question this item has to answer is
  narrower than it looks: which of the 47 BLOCK a sign of success, and
  which are simply work.

  Priority order given by the user 2026-09-02, recorded because it
  outranks the roadmap's own ordering and would otherwise live only in a
  chat window:
    1. Implement outstanding fixes from any and all reviews, backlog
       included.
    2. Open items that get us to v1.0.0.
    3. Additional open items that get us to the next version.
  Decided by the user 2026-09-02, answering the question this item
  asks: only an item that BLOCKS a sign of success needs a milestone.
  A defect in shipped code belongs to whichever release ships the fix
  rather than to a goalpost, so forcing every review-fix into a bucket
  would be inventing structure.

  That makes the work narrower than the item first reads. Walk the open
  items, put a milestone line in the body of each one that blocks a
  stated sign of success, and leave the rest unmapped on purpose --
  unmapped is then an answer rather than a gap. Section Milestones keeps
  the prose about what each version means, which is the half that does
  not go stale.
  **Layman:** The plan says which work belongs to which version, but only for the original items — most of what has been filed since is unsorted.
  Kind: doc-fix.
  Source: in-session-2026-09-02, measured while answering the user's versioning question.

- 📋 [PRESS-0087] **The publishing key sits in a frame local that INV-7's test cannot reach.**
  INV-7 is tested on str() and repr() of what is raised, and both are
  clean. But the key also lives as a VALUE in the headers dict of the
  frame that raises, so any locals-dumping traceback handler or crash
  reporter prints it.

  Not a defect in publisher.py today: nothing in the tree dumps locals.
  It is a hole in what INV-7 can PROMISE, and PRESS-0011 -- the rolling
  log and the Face's last-resort catch -- is where it becomes real. The
  same shape as PRESS-0051, which was about __cause__ rather than
  locals.

  So the work is a decision rather than a patch: either PRESS-0011's
  handler is forbidden from formatting locals, or the key stops living
  in a long-lived local. Whichever is chosen, INV-7's clause should say
  which surfaces it covers, because as written it reads as absolute and
  is checked on two.
  **Layman:** A crash report that lists variables could show the publishing key, even though every error message is careful never to.
  Kind: security.
  Source: review-code 2026-08-31 lane publisher, split from PRESS-0069 item 2 on 2026-09-02.

- 📋 [PRESS-0088] **A publish reads the whole site into memory and then copies each uploaded file about three more times.**
  _local_files reads EVERY file of the site into one dict before
  anything is compared, and the upload path adds roughly three further
  copies of each file: b64encode, json.dumps, then .encode.

  ADR-0002 puts the first publish at around 862 files. On a text-only
  site that is nothing; on a photograph-carrying one it is a large
  resident set on the modest Windows box PRESS-0022 targets.

  Not fixed with the rest of PRESS-0069 because it is a design change
  rather than a defect: the comparison wants a hash per file rather than
  its bytes, and the upload wants streaming. Both alter the shape of the
  publish loop, and INV-4 pins how files are compared.
  **Layman:** Publishing a site with many photographs could use a lot of memory on a modest computer.
  Kind: perf.
  Source: review-code 2026-08-31 lane publisher, split from PRESS-0069 item 3 on 2026-09-02.

- 📋 [PRESS-0089] **Nothing decides what the publisher may find in the site folder besides the site.**
  _local_files publishes every ordinary file under the folder. The
  symlink half is closed -- a link's target is no longer read -- but
  anything else the Builder leaves behind still goes up: an editor's
  temp file, a .git directory, an OS thumbnail cache.

  Dotfiles were deliberately NOT excluded when the symlink half was
  fixed. A site legitimately carries .nojekyll, and the default
  untouchable list names it, so a blanket dotfile skip would break the
  published site. That makes this a decision rather than a filter to
  write.

  What it needs first is the rule: is the site folder Pressless's alone,
  so anything unexpected in it is an error worth refusing, or is it a
  folder the writer may also keep things in, so the publisher needs a
  list of what it will and will not send? PRESS-0009 §4.4 answers
  neither today.
  DECIDED by the user 2026-09-04: the site folder is Pressless's alone.
  Anything in it the Builder did not produce is an error, and the publish
  refuses naming the file rather than sending it.

  That settles the question this item said PRESS-0009 4.4 answers neither
  way, so the item is no longer blocked. What it now needs, in order: 4.4
  amended with the rule, the spec gated (the rule changes what an
  implementer builds, so rule 14 applies), then _local_files refusing
  rather than filtering.

  Note for whoever writes it: refusing is not the same as skipping. A skip
  publishes a correct site and says nothing; a refusal is what makes the
  stray file visible, which is the whole point of choosing this branch.
  The untouchable list is unaffected -- .nojekyll is Builder output or a
  listed entry, not an unexpected file.
  **Layman:** If a stray file ends up in the folder Pressless publishes from, it gets published too.
  Kind: investigate.
  Source: in-session-2026-09-02, the half of PRESS-0069 item 7 that was not guessed at.

- ✅ [PRESS-0090] **A comment's date carrying a zone is still written silently, where an entry's is now refused.**
  `write_comment` formats a comment's date with the same `_DATE_FORMAT`
  as an entry's and applies no zone check, so an aware `datetime` has
  its offset dropped in silence — the defect PRESS-0067 item 6 just
  fixed for entries, on the other path.

  Surfaced rather than fixed there on purpose: comments are
  PRESS-0006's contract, and PRESS-0005 §9 puts them out of scope, so
  fixing it under PRESS-0067 would have been an edit no spec asked for.

  Two things to settle before writing code, and the second may make
  this a no-op:

  1. Whether PRESS-0006 wants the same rule. An entry's date decides
     its published address (PRESS-0005 decision 4), which is what made
     the entry case sharp; a comment's date is displayed rather than
     addressed, so the harm is smaller and the answer may legitimately
     differ.

  2. Whether an aware value can reach `write_comment` at all. The
     WordPress export's `wp:comment_date` is wall-clock with no zone,
     parsed by `strptime`, so Import cannot produce one today — the
     same measurement that settled the entry side. If nothing can
     reach it, the honest fix may be a line in PRESS-0006 saying so
     rather than a guard.

  If it does want the rule, it is the same three lines and the same
  pair of tests: refuse before anything is written, and a positive
  case so the fix cannot pass by refusing every date.
  Resolved (2026-09-04). Both questions this bullet raised were settled by
  measurement rather than by choosing.

  Question 2, whether an aware value can reach the write: not today. No
  import module exists, and read_comments builds every date through
  strptime, so the only in-tree route yields a naive value. That does NOT
  make the item a no-op -- Import (PRESS-0007) is the caller it is written
  for, and it is unwritten, so the guard is cheaper in place before its
  caller exists than retrofitted after.

  Question 1, whether PRESS-0006 wants the rule: INV-6 answers it. A round
  trip must return every field unchanged, and an aware value cannot, since
  §4.2's format holds no offset -- strftime drops it and strptime reads
  back naive. Refusing therefore IMPLEMENTS INV-6 rather than narrowing
  past it, so no spec was amended and rule 14 asked for no gate. Note the
  finding named write_comment; the function is write_comments.

  _refuse_a_zoned_date mirrors _refuse_a_dangling_reply and runs before
  anything is written. Tests cover the refusal, that the folder is
  byte-identical afterwards, and two positive cases. A mutation probe over
  four return routes initially left one alive -- halving the two-part
  condition went unnoticed -- so a tzinfo yielding no offset, which Python
  calls naive, is now pinned as accepted. All four routes are killed.

  STILL OPEN, and deliberately not done here: PRESS-0006 §4.2 does not
  NAME this decision the way PRESS-0005 §4.2 does for an entry. Adding it
  would narrow the documented contract and so re-arms rule 14's gate. The
  error message carries the instruction meanwhile.
  **Layman:** Old readers' comments can still be stored at the wrong time, in the way entries no longer can.
  Kind: review-fix.
  Source: in-session-2026-09-03, surfaced while closing PRESS-0067 item 6.

- ✅ [PRESS-0091] **design.md's untouchable rule matches on a path's first segment, which a stored entry carrying a trailing slash never equals.**
  DOCUMENT SIDE, and it belongs to docs/design.md rather than to
  PRESS-0001. Gate with review-contract docs/design.md --genre adr.

  § What may depend on what has the Publisher remove any path absent from
  the folder it was handed "unless its first segment is on the list". A
  first-segment comparison against a list entry "CNAME/" does not equal the
  root entry "CNAME": the stored string carries the slash and the entry
  does not. PRESS-0001 §4.3 admits the trailing slash, and its test
  asserts such a value loads, so the slash does reach the Publisher.

  The CODE is already correct and is not what needs changing: _is_protected
  compares first == entry.rstrip("/"). What is missing is the design rule
  saying so, and PRESS-0009 §4.4 says it where design.md does not.

  An implementer of the Publisher who reads the design rule literally --
  and it is the rule PRESS-0001 §2 calls this list's whole protection --
  deletes CNAME and detaches the custom domain, which is the exact loss
  that section names.

  Found by one lane; the other two verified the code side independently and
  did not reach the design rule.
  Resolved 2026-09-04. Both sides measured before the edit. settings.py
  validates on entry.rstrip("/") and stores the value as given, so
  "CNAME/" reaches the Publisher with its slash; _is_protected already
  compares first == entry.rstrip("/"). The code was correct and is
  unchanged, as this bullet said.

  The rule in design.md now says the match ignores a trailing slash on the
  entry, and names the consequence of comparing exactly.

  NO GATE, against this bullet's own instruction, and recorded rather than
  done quietly. The bullet asked for review-contract --genre adr; that was
  written before the disposition was known. With the code side already
  correct, the amendment records what was built, which is rule 14's
  recording branch and does not re-arm the gate. If the next session wants
  the cold read anyway, the trigger is one command and nothing here
  depends on skipping it.

  Related and still open: PRESS-0078 asks whether normalisation belongs on
  the write side (Setup) instead, and defers to the unwritten PRESS-0021.
  This fix does not pre-empt that -- documenting that consumers strip on
  compare leaves Setup free to normalise on write as well.
  **Layman:** The rule protecting the writer's domain name is written in a way that would not protect it.
  Kind: doc-fix.
  Source: review-contract 2026-09-04 loop 5 on PRESS-0001, filed out of scope.

- 📋 [PRESS-0092] **The first publish needs more content-creating requests than GitHub allows in an hour, so as designed it cannot finish.**
  Not a credentials problem, and no token raises this. The Publisher
  already authenticates (publisher.py sends Authorization: Bearer on every
  request), so the PRIMARY limit is 5,000 requests an hour and is not what
  bites. The SECONDARY limit is, and it is per-account behaviour rather
  than quota.

  MEASURED AGAINST THE DOCUMENTATION (2026-09-04,
  docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api):
  "no more than 80 content-generating requests per minute and no more than
  500 content-generating requests per hour are allowed."

  Against publish()'s own shape: one POST /git/blobs per changed file, then
  one tree, one commit, one reference update. ADR-0002 fixes the first
  publish at roughly 862 files, so about 865 content-creating requests.

  The per-minute cap is already satisfied -- PACE_SECONDS spaces writes a
  second apart, which is 60 a minute against a cap of 80, and matches the
  documentation's own "wait at least one second between each request".

  The hourly cap is not. The budget runs out after roughly eight minutes of
  writing, short by around 365 requests.

  WHY A RETRY DOES NOT RESCUE IT. INV-3 makes the reference update the last
  write, so nothing has been committed when the limit hits: the site is
  correctly unchanged, which is the invariant working. But the blobs
  written are referenced by no commit, and the next attempt computes what
  differs against the repository's tree -- which is still empty of them. So
  the retry re-uploads from the beginning, spends its new budget, and stops
  in the same place. The first publish never completes.

  WHAT WOULD ACTUALLY FIX IT is fewer requests, not more quota. The tree
  endpoint accepts inline content, which would collapse every blob POST
  into the single tree call -- about three content-creating requests for
  the whole first publish. PRESS-0009 4.3 rejected that, and its stated
  reason was re-checked today and still holds: the documentation for
  tree[].content says only "The content you want this file to have. GitHub
  will write this blob out and use that SHA for this entry", and states
  nothing about encoding, size limits or binary support -- which matters
  because photographs are binary. That is now a trade against a first
  publish that cannot finish, which is not the trade that was made.

  ONE RESIDUAL UNCERTAINTY, stated rather than assumed: GitHub does not
  enumerate which endpoints count as content-generating. Blob, tree and
  commit creation are the obvious reading and the conservative one. If
  blob creation is not counted, this item is void -- so establishing that
  is the first step, and it is cheap against a scratch repository.

  SMALLER, SEPARATE: the documentation prescribes exponentially increasing
  waits between retries and an error after a bounded number. PRESS-0046
  gave the retry a fixed wait and a bound; the backoff is not implemented.
  The same page warns that "Continuing to make requests while you are rate
  limited may result in the banning of your integration."
  Approved (2026-09-04): the user agreed to a throwaway GitHub repository
  for step one, on the PRESS-0072 precedent. Step one is unchanged and is
  the cheap decisive one -- establish whether blob creation counts as
  content-generating. If it does not, this item is void. gh is
  authenticated as the main account with repo scope; it still lacks
  delete_repo, so the scratch repository from PRESS-0072 is still there
  and a new one will persist too. Not started.
  **Layman:** The very first publish asks GitHub to accept more new files in an hour than it will accept, so it would stop part way and never get through.
  Kind: investigate.
  Source: user question 2026-09-04, verified against GitHub's REST documentation the same day.

- 📋 [PRESS-0093] **A move can leave one folder holding two files that name one slug.**
  MEASURED 2026-09-04, on Linux:

    drafts/a-slug.txt written by the Store
    published/a-slug.TXT created by hand
    store.exists(folder, "a-slug")  -> True
    store.publish(folder, "a-slug") -> SUCCEEDS, no SlugInUse
    published/ then holds ['a-slug.TXT', 'a-slug.txt']

  _move composes both paths with path_for, which spells the suffix
  exactly, and then tests target.exists(). So a destination differing only
  in the suffix's case is invisible to it, while the Store's own exists()
  folds case and reports the address taken. The two disagree.

  PRESS-0005 6 requires SlugInUse "onto a slug the published folder
  already holds" and INV-10 requires it "given a slug held in both
  folders". Held by whose reading is the question, and the spec was silent
  until loop 7 -- which stated the current behaviour as the trade rather
  than deciding it, because a docs gate may not change code.

  WHAT IS ACTUALLY LOST. Nothing is overwritten, so no writing is
  destroyed. But the writer ends with two files naming one address, and
  read() opens only the .txt -- so his hand-made .TXT is stranded and
  invisible from that moment, with nothing said.

  REACHABLE ON LINUX ONLY, and never produced by the Store: it needs a
  file the writer renamed himself, which S3 invites. On Windows the two
  names are one file and the platform refuses the move.

  THE DECISION, which is why this is filed rather than fixed: either the
  moves consult the folded view, and a .TXT destination becomes SlugInUse
  -- consistent with exists(), and it makes a hand-renamed file block a
  publish; or the exact view stands and the spec's trade is kept, in which
  case the honest fix is that publish reports the stranded file rather
  than leaving it silent. The second is smaller and matches 4.3's stated
  preference for not writing over his file.

  Related: PRESS-0067 closed the list_slugs/exists half of exactly this
  shape. This is the half that pair fix did not reach.
  **Layman:** Publishing an entry can quietly leave two copies of it, and the writer's own copy is the one that gets stranded.
  Kind: fix.
  Source: review-contract 2026-09-04 loop 7 on PRESS-0005, filed as the code half.

- 📋 [PRESS-0094] **The Store checks the comment identifiers it is handed, and two invariants get the test case that would falsify them.**
  CODE SIDE. PRESS-0006's gate settled all three on the document; the
  code and the suite have not caught up. Nothing here is a defect the
  suite can currently see, which is the point.

  1. INV-13, new. `write_comments` refuses a set carrying an empty
  identifier or two that are equal, and writes nothing. Decided by the
  user 2026-09-05. Both are visible in the set handed in, which is the
  ground `_refuse_a_dangling_reply` and `_refuse_a_zoned_date` already
  stand on, so it is a third guard beside them rather than a new kind of
  check. The empty one is the sharp case: "" is also `parent`'s top-level
  sentinel, so a reply naming that comment is read as top-level and lost
  rather than refused -- INV-5 passes on a reply whose parent is gone.
  Test named in the spec as `test_unsound_identifiers_are_refused`, with a
  positive case so the guard cannot pass by refusing every set. Probe it
  after the code lands, one mutation per route the Breaks-when names.

  2. INV-3's test has no reserved-device-name case. `_refuse_illegal_slug`
  refuses `con`, `prn`, `aux`, `nul`, `com1`-`com9` and `lpt1`-`lpt9`, and
  `_ILLEGAL_NAMES` in the suite carries five cases, none of them a device
  name. So a hand-rolled character check passes every listed case and lets
  `pages/nul.html` through -- which on Windows reaches the null device.
  The spec now names the case; add it.

  3. INV-10 never reaches `write_template`. That call writes with
  `newline="\n"`, and nothing asserts it: the suite's INV-10 test watches
  `write_html` and `write_comments` only, and the spec used to delegate the
  template half to PRESS-0005 INV-6, whose test exercises `write` -- a call
  that predates `write_template`. Measured 2026-09-04: on Linux a file
  written with the newline named and one written without are byte
  identical, so only a call assertion bites. The spec now puts the test
  here; add the template case to it.
  **Layman:** Three small gaps between what the comments design now promises and what the code and tests actually do.
  Kind: implement.
  Source: review-contract 2026-09-05 loop 4 on PRESS-0006 -- code side of three findings.

- ✅ [PRESS-0095] **A malformed blob answer escapes the Publisher's typed-failure contract, and two docstrings still carry a claim the spec has narrowed.**
  PRESS-0009 4.1 says every failure this module raises is one of its
  types. `_content_of` calls `base64.b64decode` and `.encode` with no
  guard, so a blob answer whose content is malformed or is not a string
  escapes untyped.

  Executed 2026-09-05 against the shipped module: a short base64 string
  raises binascii.Error, a non-string raises TypeError, and a non-string
  under a non-base64 encoding raises AttributeError. Only an ABSENT
  content field is typed. Every neighbouring conversion is guarded and
  cites PRESS-0073; this is the site that was missed.

  The Face branches on 4.1's types, so an untyped escape reaches the
  last-resort catch instead of a sentence about the site. The spec is the
  contract and is right; the module is in breach.

  Also here, because they share the fix pass: two docstrings still say
  RepositoryMissing means settings.repository resolves to nothing --
  publisher.py's class docstring and test_publisher.py's docstring for
  test_a_missing_blob_is_not_reported_as_a_missing_repository. Section 6
  now scopes the type to the request that names the repository itself,
  which is what that test already pins.

  A docs gate may not edit code, so it is filed rather than applied.
  Resolved (2026-09-05): `_content_of` now wraps both conversions and
  raises PublishError, in the idiom its three PRESS-0073 neighbours use.
  The two docstrings are narrowed to §6's scope -- the class docstring now
  reads as §4.1's own inline comment does. `_failure`'s comment keeps the
  old phrase deliberately: it describes what a wrong report WOULD say, and
  that reasoning is unchanged.

  Locked by tests/test_publisher.py::test_a_malformed_blob_content_field_
  is_a_typed_failure, parametrized over all three measured routes. Proved
  red before the fix; mutation_probe then killed five mutants on the
  shipped code -- narrowing the guard to ValueError alone, dropping each
  of the three types in turn, and re-raising untyped. Gate green.
  **Layman:** One kind of bad answer from GitHub reaches the writer as "something went wrong" instead of a sentence about his site.
  Kind: review-fix.
  Source: review-contract 2026-09-05, PRESS-0009 gate loop 2.

- 📋 [PRESS-0096] **design.md admits one unknown-outcome case and the Publisher now reaches that state by two routes.**
  docs/design.md section Errors says the unknown-outcome sentence covers
  the reference update being sent and no result coming back, and calls
  that the one case S6 admits.

  PRESS-0009 section 6 reaches the same state by a second route: a server
  error answering that update, which IS a result coming back. PRESS-0046
  established the route and design.md was not amended with it.

  A Face built from design.md reports the site unchanged for a publish
  that may have gone out -- the S6 breach both documents say the design
  exists to prevent.

  PRESS-0009 section 11 names this as another document's gate. design.md
  is gated as an ADR, so the amendment re-arms that gate.
  **Layman:** The design document promises the writer a clear answer in a case where the app can no longer give one.
  Kind: doc-fix.
  Source: review-contract 2026-09-05, PRESS-0009 gate loop 2.

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
