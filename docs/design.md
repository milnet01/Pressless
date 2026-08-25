# Pressless — Design

> **Purpose — so the shape is decided once, and anyone can tell where a
> new piece of work belongs and what it is allowed to touch.**

**This document is a gate.** Work is not broken into items until it is
agreed — `~/.claude/workflow.md` § 2. It passes when someone can take any
item off the queue and say which part it belongs in and what it may
touch.

**Status:** agreed 2026-08-24.

It works within the shape `docs/discovery.md` § *Shape agreed with the
user* fixed, and does not reopen it. Where a choice below had two
defensible answers it has an ADR in `docs/decisions/`, named here.

## The parts

> One line each: what this part is responsible for. You cannot place work
> without knowing the parts.

| Part | Responsible for | Deliberately knows nothing about |
|---|---|---|
| **Settings** | What is true of this machine and this site rather than of his writing: where the site folder is, which repository to publish to, the Daily Prompt filter, the untouchable list, and where **both** his secrets are kept. | Everything. It depends on nothing. |
| **Store** | Everything that shapes the site: entries as marked text, the fixed pages, the templates, the header, footer and navigation, the historical comments, and any photograph an entry uses. Drafts kept apart from published. Reads, writes, lists. | GitHub, the browser |
| **Import** | Turning the twelve years in the WordPress export into Store files, once. Run at setup and never again. | GitHub, the browser, the Face |
| **Marks** | The small styling language. Turns marked-up text into a structure, and a structure into HTML. Pure calculation, touches no disk and no network. | Files, GitHub, the browser |
| **Builder** | Turning the Store plus Settings into a finished site folder. This is `build_blog.py` re-homed and separated from the writer. | GitHub, the browser, where the writing came from |
| **Publisher** | Making GitHub match the folder it was handed — leaving Settings' untouchable list alone — and fetching back a previous state of it when asked. | Entries, pages, poems, what a draft is |
| **Insights** | Asking Google Analytics how the site is being read, and handing back plain numbers: how many people, and which countries. | Entries, pages, marks, HTML, GitHub |
| **Face** | The local web server and the pages he sees in his browser — the editor, the preview, the buttons, the cheat sheet, the dashboard. | *Nothing calls it* |

**Marks is a part rather than a detail inside the editor**, and that is
the least obvious decision in this document. Two different things
render his writing: the Builder, when it makes the live page, and the
Face, when it shows him what he is typing. If those are two pieces of
code, "what you see is what you get" is a claim nobody is keeping —
they will diverge, and the first person to find out will be the writer,
after publishing. One part, used by both, is what makes S10 true rather
than hoped for.

## What may depend on what

> The load-bearing section — this is what stops the shape rotting, and it
> is what the pick-an-item gate reads.

**The rules, and they are rules rather than arrows:**

1. **Only the Face knows what order things happen in.** Write → build →
   publish is a sequence the Face owns. No lower part ever calls the
   next one along, and no part may reach back into the Face.
2. **The Builder and the Face must render through the same Marks code.**
   Not similar code, not code kept in step by hand — the same part. Any
   change that gives either its own rendering path breaks S10 and is out
   of bounds.
3. **Marks touches no disk and no network, ever.** It takes text and
   returns a structure. This is what makes it cheap to test exhaustively,
   which matters because it is the part every poem passes through.
4. **The Builder may read the Store and Settings and may never touch the
   network.** So S2 — a poem keeps its lines — is provable without
   anything reaching GitHub. **It writes only published entries into the
   site folder.** That is where S7's guarantee lives, and it is the only
   part that can hold it.
5. **The Publisher may read Settings and a folder of finished files, and
   nothing else.** It must not be able to tell an entry from a
   stylesheet — which is exactly why it cannot be the part that keeps a
   draft back. A part that publishes whatever it is handed has nothing
   to decide with, so rule 4 carries S7 and this rule does not.
6. **The Store may read Settings and may never PRODUCE HTML** — turning
   marked text into HTML is Marks' job and nobody else's. It may *hold*
   a fixed page written as HTML, because the code view below is editable
   and that is the thing he edits. S3 is about entries — one file per
   entry — and an entry is never HTML.
7. **No part reaches inside another.** Each has one small documented way
   in; the insides are private.
8. **Insights may read Settings and may talk to Google, and nothing
   else.** It never opens the Store, never calls Marks, and nothing
   about writing or publishing may depend on it. If Google is
   unreachable, or he never sets it up at all, everything from S1 to S10
   still works — the dashboard is the only thing that says so.
9. **Nothing may depend on Import.** It runs once, before anything else
   has run, and is the only part that may be deleted from a working
   installation without changing what the others do.

**Where the fixed pages live.** Home, About, Music **and Privacy** are
the Store's, not the Builder's — they are writing he edits, and the only
thing separating them from an entry is that they are not dated and do
not appear in the journal. Giving them to the Store is what lets S8
reuse the editor rather than grow a second one. **Privacy is named
because leaving it out is a legal exposure, not a missing page**: the
site discloses its visitor counting there, and the footer links to it
from all 862 pages.

**The code view is editable, and that is what decides rule 6.** "Show me
the code" opens a fixed page's own HTML for editing — that is the access
that was asked for, and the reason the Store may hold HTML.

**A fixed page is stored as HTML and is never generated from marks.**
That is the whole round-trip rule, and without it the two editors fight.
The plain box shows only the page's **visible words** and writes them
back in place, leaving every tag around them byte-for-byte as it was;
the code view edits the file entire. Neither ever regenerates the page,
so Marks is not involved in a fixed page at all and nothing he hand-
writes in the code view can be silently reformatted by the box. The home
page is six picture tiles rather than prose, so there the words are
nearly all it can offer and the code view is the real editor.

**The Face owns reading those words out and writing them back**, and it
is a text swap rather than a rendering — no part produces HTML from
marks here, so rule 6 is untouched. **The box offers no styling on a
fixed page**: bold, colour and effects are entry things, and on a page
they are done in the code view, which is where the tags already are.
That keeps one honest sentence for him — *the box changes words, the
code view changes anything* — instead of a styling menu that works
differently depending on what he opened.

Every edit is recoverable in one step (S9), which is what makes handing
him the HTML safe rather than reckless.

**The header, footer and navigation are the Store's, and there is
exactly one copy of each.** Every page is built from them, so he edits
them in the same code view as a fixed page — and one edit reaches **all
862 pages**, the whole journal included. They sit in the Store rather
than in Settings because they are site material he edits, not machine
facts: that is what puts them inside `content/`, and therefore inside
what undo brings back.

**That makes it the highest-blast-radius edit in the app, and it is why
undo is not a nicety.** A mistake in a fixed page spoils one page; a
mistake in the footer spoils the site, and the site is the only place he
would see it. Two things follow for whoever builds this: the preview
must show a real page built with the change *before* it is published,
and undo must be offered in the same breath as the edit rather than
found later in a menu.

**And Pressless must say plainly that editing a header inside a page is
wasted work**, because the next build overwrites it from the single
copy. The sibling workspace learned this the expensive way — the header
was written out in eight places and had already drifted, the journal
carrying a six-item menu against the rest of the site's five.

**What undo actually does, and why a revert is not enough.** The
Publisher can fetch back a previous state of the repository, and that
alone is not S9: the Store still holds the text that caused the trouble,
so his next publish would put it straight back — the site would be right
for an hour and wrong again without him doing anything wrong. So undo is
a sequence the Face owns: fetch the previous state, write its `content/`
back into the Store, rebuild, publish. It ends with the site and his own
files agreeing, which is the only reading of "back the way it was" that
survives the next thing he does. **Drafts are untouched by an undo**,
since they were never in the repository to fetch back — so an unfinished
poem can never be lost to one.

**Some files in his repository are not ours to touch, and deleting one
is unrecoverable in a way a bad page is not.** **The rule is what binds,
not a list: every entry at the repository root that the Builder does not
produce is untouchable.** Settings holds the list; the Publisher neither
writes nor removes a path on it. Everything else is the Builder's and is
made to match the folder — deletions included, so a page he removes
actually goes.

**The list is derived, never typed from memory.** Measured on the live
repository 2026-08-24 it is **seven**: `CNAME`, `.nojekyll`, `README.md`,
`google26e8bc6a1b61c6cf.html`, `favicon.ico`, `apple-touch-icon.png` and
`COPY-ME-new-page.html`. **Deleting `CNAME` detaches his domain** and
deleting the Google file silently un-verifies his site in search results
months later, so the item that builds this derives the list from the
repository rather than reading it from this paragraph.

**`content/` is not on that list — it is ordinary Builder output**, and
saying otherwise was how an earlier draft of this document made it
unwritable by anybody. The Builder copies the Store's published files
into `content/` in the site folder; the Publisher then treats it like
every other thing it was handed, so it is uploaded, updated, and pruned
when he deletes an entry. That last part matters: on the untouchable
reading, a deleted poem's source text would have stayed on the web
forever.

**`COPY-ME-new-page.html` stays on the site.** Templates retire it as a
*way of working* — he is no longer expected to find, copy and rename a
file by hand — but it is untouchable, so the Publisher never removes it.
Retiring a habit and deleting a file are different acts and this document
means the first.

**Where photographs live.** Marks has a picture mark — `{photo:
seaside.jpg}`, or `{photo: seaside.jpg | Late light on the water}` with
a caption — so the cheat sheet generates it like every other mark. The
Store keeps the original in Pressless's own folder, never in the site
folder; the Builder writes the web-sized copy, **owns the naming rule
for it, and is the one place that rule is written down** — Marks renders
the `src` from that rule without ever touching a disk. **The preview
shows the original scaled in the browser**, so a photograph in an
unbuilt draft is visible immediately rather than appearing as a broken
image, which is what S10 asks for. Originals are never modified and never published —
the same rule the sibling workspace already runs on, and here it is
forced: the existing originals alone are **453 MB against GitHub Pages'
1 GB limit**.

**What Import brings across, and why it brings everything.** Rule 9
makes Import unrepeatable, so anything it declines to bring is outside
Pressless for good — which settles every question below in the same
direction: carry it, and let the Builder decide what to publish.

- **The 616 published posts**, each with the fields the Builder already
  reads: title, slug, date, categories and tags. Dropping any of them
  costs the live site its 6 categories, 167 tags and its by-year archive.
- **The 62 drafts and 8 private posts, as drafts.** They are his writing
  and he never deleted them. The 3 trashed are skipped, because he did.
- **The 29 Daily Prompt entries, tagged as they are.** The live site
  publishes 587 rather than 616 because the Builder filters them on
  WordPress's own `dailyprompt-NNNN` tag, on his 2026-08-17
  decision. **Import must not apply that filter** — it keeps the tag, the
  filter stays in Settings where it already lives, and the Builder goes
  on excluding them. Filtering at Import instead would delete 29 pieces
  of his writing permanently; filtering at build leaves his decision
  reversible by changing one setting.
- **The 63 published comments**, in a file beside the entry rather than
  inside it — an entry file stays his prose, which is S3. They are
  read-only and the Builder renders them as it does today. Without this
  they are not in the Store, so the Builder emits pages without them and
  the Publisher removes 63 real people's words from the live site on the
  first publish. Commenter names are published, as they are now; their
  email addresses and IP addresses are not, and Import must not carry
  them into the Store at all.

**Where the cheat sheet comes from.** Marks owns one table of every mark
it understands, and the cheat sheet is generated from that table — the
in-app panel and the printable page both. Neither is written by hand.
A hand-written card drifts the first time a mark changes, and then it
teaches him something that does not work.

**A template is an entry he never publishes**, and that is the whole
design. Starting something new offers a list — a poem, a lyric with
verses, an entry built around one photograph, a plain journal entry —
and picking one copies its text into a new draft. Templates are Store
files in the same marks as everything else, so he edits one in the same
box, adds his own, and nothing new has to be built, learned or
documented. **Nothing in the parts changes to support them**, which is
the test that this is the right shape rather than a feature.

They also retire `COPY-ME-new-page.html`, which is the same idea done by
hand: a file he was expected to find, copy and rename himself.

**The dashboard, and the two things about it that are easy to get
wrong.** Insights reads the live Google Analytics property already on
the site, through Google's reporting
interface, and hands the Face plain numbers. Two traps:

- **Flags must be bundled pictures, not flag characters.** The obvious
  route is the flag emoji — 🇿🇦 — and **Windows has no glyphs for them**:
  it draws the two letters `ZA` instead. It looks right on the Linux
  machine this is built on and wrong on the only machine he uses. So
  a small set of flag images ships with the app, keyed by country code.
  **Verify this on his actual machine before building it** — it is a
  claim about his Windows version, and the cost of being wrong is a
  dashboard full of letter pairs.
- **It needs a second credential.** Reading Analytics is a separate
  Google authorisation from the GitHub publishing key. S5 is about the
  publishing key and is not broken by this, but setup grows a second
  step, and the dashboard is the one feature whose setup he can decline
  and lose nothing else by declining.

## What every part does the same way

> Errors, state, persistence, logging. Decided once here, or every item
> invents its own.

### Where everything sits on disk

**Two folders and a keyring, and the difference between them is what
reaches the web.** This is decided here because four separate questions
— where drafts live, where photograph originals live, where the log and
the Insights cache live, where the second credential lives — are all the
same question, and answering them one at a time is how they end up
answered differently.

**What makes it load-bearing: everything in his repository is publicly
fetchable.** Measured 2026-08-24 — the live site serves the README at
its repository root, returning HTTP 200. That file is not a page and is not linked from
anywhere, and it is served all the same. So "in the repository" and "on
the web" are the same statement, and any file placed there for safe
keeping is also published.

| Where | What lives there | Published? |
|---|---|---|
| **The site folder** — the git working copy | Everything the Builder writes, `content/` included: the published entries, fixed pages, templates, page furniture and historical comments, in their source form | **Yes**, all of it |
| **Pressless's own folder**, outside the site folder | Drafts, photograph originals, the settings file, the rolling log, the Insights cache — and, only where there is no keyring, the credential file ADR-0003 falls back to, owner-readable and nothing else | **Never** |
| **The operating system's keyring** | Both credentials — the publishing key and the Google authorisation | Never |

**Drafts are outside the site folder because of the measurement above,
and for no other reason.** Inside it they would be backed up by every
publish — genuinely attractive — and every unfinished poem would be
readable by anyone who guessed the address. That is S7 broken in the
worst way: not a draft appearing as a page, but a draft appearing and
nobody noticing. **The cost is real and he should be told it:
unfinished work is not backed up.** Backing drafts up somewhere that is
not his public site is a good later item; it is not this one.

**Published entries in `content/` are fetchable, and that is fine** —
they are the source text of writing already on the page.

**`content/` carries everything that shapes the site, not just entries:**
the published entries, the fixed pages, the templates, and the header,
footer and navigation. That is what makes undo whole — fetching a
previous state brings back the page furniture along with the writing, so
the one edit that reaches all 862 pages is recoverable by the same single
step as everything else. Settings keeps only what is machine-specific:
where the site folder is, which repository to publish to, and a pointer
to the keyring. **The settings file lives in Pressless's own folder** and
is never published.

**The keyring line is a widening of ADR-0003, recorded 2026-08-24.**
That decision was written about the publishing key when it was the only
credential. The Google authorisation is a credential on the same
footing and lives in the same place — never in either folder, and never
in the settings file, which sits in a folder that is not published but
is also not protected.

### Errors — he must be able to tell what went wrong

**Every message he can reach has three things, in this order:**

1. **What happened**, in his words. *"Pressless could not reach
   GitHub."* Never a code, never a stack trace, never the word
   *exception*.
2. **What it means for his site.** *"Your site has not changed."* This
   is S6's actual requirement — he is never left unsure whether it went
   out — and it is the part a technical error message always omits.
3. **What to do next.** *"Check your internet and click Publish again."*
   An error that does not say this leaves him stuck holding a fact.

**Parts raise typed failures; only the Face turns them into sentences.**
No part writes prose for him — it says *what* failed and the Face owns
*how it reads*. That keeps one place to check, and one place to fix a
sentence that confuses him.

**Nothing raw ever reaches the screen.** The Face has a last-resort
catch: anything unforeseen becomes *"Something went wrong that Pressless
did not expect. Your site has not changed."*, plus a **Show details**
toggle holding the technical text and the log file's location. The
details are there for whoever helps him, not for him.

**This is checkable, and it is checked.** Every failure type carries a
written sentence, and a test walks the list and fails if any one of them
has no sentence, or has a sentence that omits point 2. An error nobody
wrote is caught by the test, not by him.

### State

**The disk is the truth and nothing is held between requests.** Kill the
app mid-sentence and the draft file on disk is the whole of what
survives, which is exactly S7. There is no session and nothing to lose
in a crash that was not already saved.

**Insights is the one part that keeps a cache, and it is a cache rather
than an exception.** Google limits how often it will answer, so the last
reply is kept on disk with the time it was fetched, and the dashboard
says when it was last updated. Deleting that file costs nothing but a
fresh fetch. Nothing else in Pressless may keep one: a cache of his
writing would be a second copy that can disagree with the first, and
which one is true is exactly the question S3 exists to make unaskable.

### Persistence

- **UTF-8, and LF line endings written explicitly** — Windows would
  otherwise rewrite them, and a changed line ending is a changed file to
  git, which would make every publish look like it touched everything.
- **One file per entry, and never rewritten in place.** Write a
  temporary file, then rename it over the old one. Rename is atomic on
  both Windows and Linux, so a crash mid-save cannot leave half an entry.
- **Anything Pressless does not understand is left exactly as written.**
  A mark it does not know, a header field it has no use for — kept
  byte-for-byte, never silently dropped. This is a promise about twelve
  years of writing, and it is the reason the Store never rewrites a file
  it was only asked to read.

### Logging

One rolling plain-English log beside the settings. **No credential is
ever written to it, not even shortened** — neither the publishing key
nor the Google authorisation — `security.md` and S5.

## The stack, and what it rules out

**Chosen:** Python 3, the standard library's own web server for the
Face, `Pillow` for photographs (already proven — `_work/resize.py` in
the sibling workspace turns 220 MB of camera originals into 31 MB), the
operating system's keyring for his key, and PyInstaller to package the
whole thing into one file per system.

**Why:** the risky part of this project is not the app, it is twelve
years of irregular content — three source formats, 143 untitled
entries, poems whose line breaks are the content. `build_blog.py`
already handles all of it and has been proven against his real archive.
Reusing it means the hard part starts working rather than starting
again. The runner-up was a single Go binary, which is smaller and
installs even more cleanly; it was turned down because it buys a better
install by rewriting the one component we have evidence about.

**What it rules out — the half that matters more than it looks:**

- **No git on his machine.** Publishing goes through GitHub's own web
  interface, building one commit from only the files that changed.
  Shelling out to `git` would mean he installs it first, which is the
  phone call this project exists to remove. See ADR-0002.
- **No compiler, no database, no Python install** on his side.
- **No feature that needs a server.** Pressless is not reachable from
  the internet — discovery fixes that — so anything requiring a visitor
  to reach it is out of the stack's reach by construction. Visitor
  statistics are the live example.
- **The Windows file cannot be built on this machine.** PyInstaller does
  not cross-compile. `Pressless.exe` has to be produced by a Windows
  machine, which in practice means a GitHub Actions Windows runner. The
  repository is public, so those minutes are free — but **releases go
  through CI from the first one**, not later, and S4 cannot be
  demonstrated without it. See ADR-0004.

## Close calls

> Each gets an ADR in `docs/decisions/`, so it is not re-argued later.

| ADR | The call |
|---|---|
| [ADR-0001](decisions/ADR-0001-entry-file-format.md) | Entries are plain text with small marks, not Markdown and not HTML |
| [ADR-0002](decisions/ADR-0002-publish-via-github-api.md) | Publishing goes through the GitHub API rather than git |
| [ADR-0003](decisions/ADR-0003-where-the-key-lives.md) | The publishing key lives in the operating system's keyring |
| [ADR-0004](decisions/ADR-0004-windows-build-in-ci.md) | The Windows executable is built in CI, because it cannot be built here |
| [ADR-0005](decisions/ADR-0005-dashboard-is-optional-and-separate.md) | The dashboard is a separate part that publishing never depends on |

## Review loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-24 | 3, cold — genre pinned `adr` (design doc), packet carried discovery, all five ADRs, both CLAUDE.md files and the measured source facts; Windows / PyInstaller / GitHub API / Analytics API declared an unrunnable region, so Q1 was out of scope there | 3 | 2 | 3 | n/a | **Eight verified, eight fixed, none dismissed. First gate on this document.** **Three were found independently by all three lanes**, the strongest signal in the run: no part owned the one-time conversion of the 616 existing entries (zero mentions in the whole document, while discovery calls it "a prerequisite for S1"); the "show me the code" view from the agreed shape was never placed, colliding with rule 6's ban on the Store producing HTML; and `S6` was cited where draft-safety is `S7`. **The most dangerous was found by one lane and got worse on verification.** The Publisher was to make GitHub "hold exactly the folder it was handed", which contradicts ADR-0002's "only those [that differ]" — and the live repository holds **six files the Builder does not produce** (`CNAME`, `.nojekyll`, `README.md`, the Search Console token, and two icons). Under the mirror reading the first publish deletes all six, and **deleting `CNAME` detaches his domain**. Settings now holds an untouchable list the Publisher may never write or remove. **A second Q1 the lanes reached from opposite ends:** the fixed-page set named three pages and the site has four — `privacy.html` is a POPIA disclosure whose footer link reaches all 862 pages, so dropping it while the Analytics tag is live is a legal exposure rather than a missing page. **One Q1 was a mechanism that could not work:** draft-safety was pinned on the Publisher being unable to tell a draft from a stylesheet, and a part that publishes whatever it is handed has nothing to decide with — S7's guarantee moved to the Builder, which is the only part that can hold it. **One Q2 was a security hole in the making:** the parts table called the publishing key "the one secret" while the dashboard section needs a second Google credential, and the logging rule named only the publishing key — so a refresh token could have landed in the rolling log. **Photographs had no owning part** despite being fixed into the first version that morning. **Three fixes were this session's own collateral, all caught by the sweep rather than by a lane:** the new Import rule landed as rule 9 between rules 6 and 7; "the one structural decision in this document" stopped being true once Import became a second one; and `CLAUDE.md` still read `S1–S10` after S11 was added. **Two open questions resolved clean and are not counted:** 143 vs 172 untitled entries are different populations (172 less the 29 dropped Daily Prompt entries is exactly 143), and Insights showing countries rather than provinces follows S11, the visitor-statistics paragraph having already been marked overtaken by events. ADR-0002 was left unedited — it is silent on the untouchable list rather than contradicting it, and the dependency rules' home is this document. |
| 2 | 2026-08-24 | 3, cold — identical brief, packet rebuilt from disk and extended with the measured live-repo root listing and the four hand-authored pages | 1 | 4 | 5 | n/a | **Ten verified, ten fixed, none dismissed. The run is oscillating: about two-thirds landed on text loop 1 wrote**, which is 4a-min's measured pattern — loop 1 added Import, the untouchable list, photographs, the code view and a second credential, and each addition arrived under-specified. **Four findings shared one root cause, and patching them separately would have been the wrong fix**: the document never said where Pressless's own files sit relative to the published site folder, which generated `content/` being absent (and therefore deleted by the Publisher's own mirror rule), photograph originals being neither in nor out, the Insights cache having no home, and the Google authorisation having no store. A new § *Where everything sits on disk* answers all four at once. **The measurement that settled it is the sharpest thing in the run**: the live site serves its repository's README with **HTTP 200**, so everything in the repository is publicly fetchable — meaning drafts kept in `content/` for backup would be readable by anyone who guessed the address. Not a draft rendered as a page, but a draft published and nobody noticing, which is S7 broken in the worst available way. Drafts are therefore outside the site folder, and the cost (unfinished work is not backed up) is stated rather than hidden. Originals are outside too, and that one is forced: 453 MB of existing originals against GitHub Pages' 1 GB. **All three lanes found the untouchable list wrong** — `COPY-ME-new-page.html` was a seventh entry loop 1 missed — so the list became a *rule* (every root entry the Builder does not produce) with the enumeration marked as derived and dated. **All three found undo incomplete**: the Publisher can revert GitHub, the Store still holds the bad text, and the next publish restores the fault — so undo is now a Face-owned sequence ending with site and files agreeing. **All three found province**, which loop 1 had dismissed as clean; they were right, and the fix records the departure in discovery rather than adding province. **Two lanes caught a contradiction this session introduced**: discovery's reversal said Pressless shows the numbers while a paragraph below still said it neither collects nor displays them. Also settled: the picture mark now has a form, a fixed page is stored as HTML and never regenerated from marks (so the two editors cannot fight), and Import brings across the 62 drafts and 8 private posts — rule 9 makes it unrepeatable, so what it declines is outside Pressless for good. **The subject widened twice mid-run** (templates, then header/footer/nav editing), against Phase 1a; both were small and reuse existing parts, and are recorded here because the next loop reads a document this one did not review. |
| 3 | 2026-08-24 | 3, cold — identical brief, packet rebuilt from disk and extended with the complete measured repo root, the fetchability measurement and the export's four post counts | 1 | 3 | 8 | n/a | **Twelve verified, twelve fixed, none dismissed, none deferred. Cap reached (3 for an ADR / design doc); the run files an empty tail and exits.** **A VIOLENT cap: about seven of the nine merged findings landed on text THIS RUN wrote**, each anchor checked against loops 1 and 2's ledger rather than recall. **The diagnosis is not that the document cannot settle — it is that the subject grew six times during the review** (page editing, editing published entries, the dashboard, templates, header/footer/nav editing, with likes pending), two of them mid-run against Phase 1a. Each loop's fixes described new surface, and new surface arrives under-specified. At 378 lines the size signal does not indicate a split. **All three lanes found the same defect, and it was mine from loop 2**: the untouchable rule barred the Publisher from *writing* a listed path while `content/` sat on that list, so nothing could ever create it — the backup discovery promises would silently never happen and undo would have nothing to fetch. Resolved by removing the asymmetry rather than documenting it: `content/` is ordinary Builder output, uploaded, updated and pruned like everything else, which also stops a deleted poem's source text staying public forever. **The most dangerous finding came from one lane and concerns real people**: the 63 published comments had no home in any part, so the Builder would emit pages without them and the Publisher — mirroring, deletions included — would remove sixty-three readers' words from the live site on the first publish, with rule 9 making Import unrepeatable. They now live in a file beside the entry, read-only, names published as they are today and email addresses and IP addresses never entering the Store. **Two lanes found Import would have undone a decision of the writer's**: it wrote all 616 as published while the live site carries 587, the 29 Daily Prompt entries being filtered on WordPress's own tag. Filtering at Import would have deleted them permanently; the tag is now carried and the filter stays at build, where the decision remains reversible. **One lane found undo could not fix the thing undo exists for** — it restored `content/` and rebuilt from the still-bad footer, and the footer reaches all 862 pages. The page furniture moved from Settings into the Store and therefore into `content/`, so one fetch brings it back. **Two Q1s were stale counts of my own**: the derived untouchable list was given as eight including `content/`, which is not in the measured root and only exists after Pressless writes it — seven is the measured number. Also settled: the entry header must carry title, slug, date, categories and tags (read off `build_blog.py`'s `Post`, whose loss would cost the site 6 categories, 167 tags and the archive); the fixed-page box edits words only, the Face owning the swap, so no new part produces HTML; the Builder owns the web-copy naming rule and the preview scales the original so an unbuilt photograph is not a broken image; and the settings file and ADR-0003's no-keyring fallback have a stated home. **Route from here: implementation, not a fourth loop.** A fresh run would start at loop 1 against a document whose last three loops each repaired the one before, and nothing in the evidence suggests a fourth would differ. |
