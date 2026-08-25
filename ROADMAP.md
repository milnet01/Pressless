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

- 📋 [PRESS-0001] **Settings holds what is true of this machine, and nothing else.**
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
  Kind: implement.
  Source: design-2026-08-24 § The parts.
  Lanes: Settings.

- 📋 [PRESS-0002] **Both credentials live in the operating system's keyring.**
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

- 📋 [PRESS-0009] **The Publisher makes GitHub match the folder it was handed.**
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
  Kind: implement.
  Source: design-2026-08-24 § The parts, ADR-0002.
  Lanes: Publisher.

- 📋 [PRESS-0010] **The Publisher can fetch back a previous state of the repository.**
  Read a previous commit's files back out of GitHub. On its own this is
  not S9: the Store still holds the text that caused the trouble, so his
  next publish would put it straight back. It is deliberately a capability
  rather than a feature, and PRESS-0015 is the sequence that uses it.
  Blocked-by: PRESS-0009.
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
