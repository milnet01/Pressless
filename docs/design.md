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
| **Settings** | What is true of this machine and this site rather than of his writing: where the site folder is, which repository to publish to, the Daily Prompt filter, the untouchable list, where **both** his secrets are kept, and the Analytics identifier Insights is queried by. | Everything. It depends on nothing. |
| **Credentials** | Keeping the two secrets themselves — the GitHub publishing key and the Google reporting authorisation — in the operating system's keyring, or in an owner-only file where there is no keyring. Where a file cannot be made private to one user — Windows, where the read-only flag is all there is — there is no fallback: setup stops and says so. Hands one back when asked. | Settings, the Store, GitHub, Google, the browser — everything it needs is handed to it. |
| **Store** | Everything that shapes the site: entries as marked text, the fixed pages, the templates, the header, footer and navigation, the historical comments, and any photograph an entry uses. Drafts kept apart from published. Reads, writes, lists. | GitHub, the browser |
| **Import** | Turning the twelve years in the WordPress export into Store files, once. Run at setup and never again. | GitHub, the browser, the Face |
| **Marks** | The small styling language. Turns marked-up text into a structure, and a structure into HTML. Pure calculation, touches no disk and no network. | Files, GitHub, the browser |
| **Builder** | Turning the Store plus Settings into a finished site folder. This is `build_blog.py` re-homed and separated from the writer. | GitHub, the browser, where the writing came from |
| **Publisher** | Making GitHub match the folder it was handed — leaving Settings' untouchable list alone — listing what sits at its root, and fetching back a previous state of it, when asked. | Entries, pages, poems, what a draft is |
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
   anything reaching GitHub. **Of his entries it writes only the
   published ones into the site folder** — the fixed pages, the templates
   and the page furniture go there too, and a draft is the one thing held
   back. That is where S7's guarantee lives, and it is the only part that
   can hold it.
5. **The Publisher may read Settings and a folder of finished files, may
   read and write GitHub, and writes to disk only into a folder it is
   handed — and nothing else.** It must not be able to tell an entry from
   a stylesheet — which is exactly why it cannot be the part that keeps a
   draft back. A part that publishes whatever it is handed has nothing
   to decide with, so rule 4 carries S7 and this rule does not. **That
   disk write is the fetch-back's**: a previous state is laid out in the
   fetch area inside Pressless's own folder — never the site folder,
   which is published. The Publisher never writes into the Store; only
   the Face's undo sequence copies from the fetch area (rule 1).
6. **The Store may read Settings and may never PRODUCE HTML** — turning
   marked text into HTML is Marks' job and nobody else's. It may *hold*
   a fixed page written as HTML, because the code view below is editable
   and that is the thing he edits. S3 is about entries — one file per
   entry — and an entry is never HTML.
7. **No part reaches inside another.** Each has one small documented way
   in; the insides are private.
8. **Insights may read Settings, may talk to Google, and keeps one
   cache file in Pressless's own folder — and nothing else.** It never
   opens the Store, never calls Marks, and nothing about writing or
   publishing may depend on it. If Google is
   unreachable, or he never sets it up at all, everything from S1 to S10
   still works — the dashboard is the only thing that says so.
9. **Nothing may depend on Import once it has run.** Setup invokes it,
   once, before anything else has; after that it is the only part that
   may be deleted from a working installation without changing what the
   others do.
10. **Only the Face reaches Credentials.** It fetches a secret and hands
    it to the Publisher or Insights as an argument, so rules 5 and 8 stay
    literally true and both parts stay testable without a real keyring.

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

The most recent publish is recoverable in one step (S9), which is what
makes handing him the HTML safe rather than reckless.

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
back into the Store, rebuild, publish. **An undo deletes nothing of
his**: an entry the fetched state does not hold becomes a draft, and a
fixed page, template, furniture file or comments file it does not hold is
kept beside them — and, being kept, is built and published again, so an
undo removes his additions from neither the Store nor the site. **It does not reach a photograph's original**, which never goes to
the site folder, so an original deleted since the fetched state is not
brought back by one. It ends with the site and his own files
agreeing, which is the only reading of "back the way it was" that
survives the next thing he does. **Drafts are untouched by an undo**,
since they were never in the repository to fetch back — so an unfinished
poem can never be lost to one. **Undo reaches back one publish and no
further**: pressing it again returns the state the first undo replaced,
so it is a toggle rather than a history.

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

**The rule says what the list must contain; the list is what the
Publisher consults.** At publish it removes any path absent from the
folder it was handed unless its first segment is on the list. It never
re-evaluates the rule there — the Builder stops producing a page the
writer has just deleted too, so the rule would protect exactly what he
asked to remove. **Setup derives it — the Face asks the Publisher what
sits at the repository root, removes everything the Builder produces, and
writes the rest into Settings — and the Face offers that same action
afterwards**. **The Builder is what names its own root output**, for the
reason rule 2 gives: a list kept anywhere else is a list kept in step by
hand, and it rots the day the Builder writes something new, because a file added to the
root outside Pressless is unprotected until it runs again.

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
folder; the Builder writes the web-sized copy and **owns the naming
rule for it, which is written down in one place**. Marks does not know
that rule: its caller hands in the one that turns `seaside.jpg` into an
address — the Builder its own, the Face one pointing at the original it
is serving — and Marks renders what it is given without touching a disk.
Rule 3 holds, rule 7 holds, and there is no second copy to drift. **The
preview shows the original scaled in the browser**, so a photograph in an
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
- **The 70 published comments**, in a file beside the entry rather than
  inside it — an entry file stays his prose, which is S3. They are
  read-only and the Builder renders them as it does today, which shows
  63: the other seven sit on Daily Prompt entries the Builder filters
  out. Import carries all 70 for the same reason it carries those
  entries — carrying only what the site shows today would lose seven
  readers' words permanently. Without this
  they are not in the Store, so the Builder emits pages without them and
  the Publisher removes 63 real people's words from the live site on the
  first publish. Commenter names are published, as they are now; their
  email addresses and IP addresses are not, and Import must not carry
  them into the Store at all.
- **The photographs, and every entry's image references rewritten to the
  picture mark.** The originals go where the Store keeps them, in
  Pressless's own folder. Rule 9 makes this the only chance: skipped,
  they stay on WordPress and every imported entry goes on pointing at the
  site he is leaving.

**Where the cheat sheet comes from.** Marks owns one table of every mark
it understands, and the cheat sheet is generated from that table — the
in-app panel and the printable page both. Neither is written by hand.
A hand-written card drifts the first time a mark changes, and then it
teaches him something that does not work.

**A template is a Store file in the same marks as an entry, and never
becomes a page**, and that is the whole design. Starting something new offers a list — a poem, a lyric with
verses, an entry built around one photograph, a plain journal entry —
and picking one copies its text into a new draft. He edits one in the
same box, adds his own, and nothing new has to be built, learned or
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
  **Insights hands back those two-letter codes rather than country
  names**, which is what this lookup binds to.
  **Measured 2026-08-25 and confirmed** on a Windows 10 22H2 box over
  SSH, in Chromium 151, which is the kind of browser the dashboard opens
  in: the flag sequence renders identically to its two letters forced
  apart, and takes exactly their combined width. A control emoji
  rendered normally in the same test, so the fonts are present and it is
  flags specifically that are missing. His own machine is not the one
  measured, but the claim is no longer an assumption.
- **There are two Analytics identifiers and they are not
  interchangeable.** The site's footer tag carries a measurement id
  (`G-…`); Google's reporting interface is queried by a numeric property
  id. Settled 2026-08-26: Settings holds the property id, as
  `analytics_property_id`, and holds no measurement id — Pressless never
  writes the footer tag. Passing the other fails every fetch.
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
| **The site folder** — what the Builder writes and the Publisher is handed | Everything the Builder writes, `content/` included: the published entries, fixed pages, templates, page furniture and historical comments, in their source form | **Yes**, all of it |
| **Pressless's own folder**, outside the site folder | All his writing — drafts and published entries alike, kept apart — photograph originals, the settings file, the rolling log, the Insights cache, the fetch area a previous state is laid out in and undo reads back, emptied when that sequence ends — and, only where there is no keyring, the credential file ADR-0003 falls back to, owner-readable and nothing else | **Never** |
| **The operating system's keyring** | Both credentials — the publishing key and the Google authorisation | Never |

**Drafts are outside the site folder because of the measurement above,
and for no other reason.** Inside it they would be backed up by every
publish — genuinely attractive — and every unfinished poem would be
readable by anyone who guessed the address. That is S7 broken in the
worst way: not a draft appearing as a page, but a draft appearing and
nobody noticing. **The cost is real and he should be told it:
unfinished work is not backed up.** Backing drafts up somewhere that is
not his public site is a good later item; it is not this one.

**Pressless's own folder sits beside the program file, not under the
home directory.** Decided with the user 2026-08-25. It holds the
photograph originals, so the default location puts hundreds of
megabytes on a system drive that may have no room for them; choosing
where the program file lives is how the drive gets chosen. On Linux
that file is the AppImage, found through the `APPIMAGE` environment
variable rather than the running process's own path, which points into
a temporary mount. On Windows it is the extracted folder. **Where the
folder cannot be created, Pressless stops and says so** — falling back
to the home directory silently would fill the drive this rule exists to
protect, and nobody would see it happen.

**Published entries in `content/` are fetchable, and that is fine** —
they are the source text of writing already on the page.

**`content/` carries everything that shapes the site, not just entries:**
the published entries and their comments, the fixed pages, the templates,
and the header, footer and navigation. That is what makes undo whole —
fetching a previous state brings back the page furniture along with the
writing, so the one edit that reaches all 862 pages is recoverable by the
same single step as everything else. Settings keeps what is
machine-specific instead; the parts table above lists it, and none of it
is writing. **The settings file lives in Pressless's own folder** and is
never published.

**The keyring line is a widening of ADR-0003, recorded 2026-08-24.**
That decision was written about the publishing key when it was the only
credential. The Google authorisation is a credential on the same
footing and lives in the same place — never in the site folder, and never
in the settings file, which sits in a folder that is not published but
is also not protected. Where there is no keyring it falls back to the
same owner-only file the publishing key does, which is what ADR-0003
means by one store, one fallback, one rule.

### Errors — he must be able to tell what went wrong

**Every message he can reach has three things, in this order:**

1. **What happened**, in his words. *"Pressless could not reach
   GitHub."* Never a code, never a stack trace, never the word
   *exception*.
2. **What it means for his site.** *"Your site has not changed."* This
   is S6's actual requirement — he is told where his site stands — and
   it is the part a technical error message always omits. **One failure
   cannot say that**: where the reference update was sent and no result
   came back, the sentence says the outcome is unknown rather than
   guessing. That is the one case S6 admits.
3. **What to do next.** *"Check your internet and click Publish again."*
   An error that does not say this leaves him stuck holding a fact.

**Parts raise typed failures; only the Face turns them into sentences.**
No part writes prose for him — it says *what* failed and the Face owns
*how it reads*. That keeps one place to check, and one place to fix a
sentence that confuses him.

**Nothing raw ever reaches the screen.** The Face has a last-resort
catch: anything unforeseen becomes *"Something went wrong that Pressless
did not expect."*, then what it can honestly say about the site — *"Your
site has not changed."* where nothing was in flight, and the unknown
sentence above where a publish had reached its last step — then *"Try
again, and send the details below to whoever helps you."* A **Show
details** toggle holds the technical text and the log file's location,
for whoever helps him rather than for him.

**This is checkable, and it is checked.** Every failure type carries a
written sentence, and a test walks the list and fails if any one of them
has no sentence, or has a sentence missing any of the three parts. An
error nobody wrote is caught by the test, not by him.

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
operating system's keyring for his key, and PyInstaller to package one
artefact per system — an AppImage on Linux, an extracted folder shipped
as a zip on Windows, which is what § Where everything sits on disk
resolves against.

**Why:** the risky part of this project is not the app, it is twelve
years of irregular content — three source formats, entries with no
title at all, poems whose line breaks are the content. `build_blog.py`
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
| 4 | 2026-08-25 | 3, cold — genre pinned `adr`, packet rebuilt from disk and extended with PRESS-0002's public surface, PRESS-0001 §4.1 and the implemented `credentials.py`; Windows / PyInstaller / GitHub API / Analytics API declared an unrunnable region | 1 | 5 | 3 | n/a | **Nine verified, nine fixed, none dismissed. First loop of a new run** — the 2026-08-24 run ended at a violent cap routing this document to implementation, and that bar lapsed with the authoring edit this loop gates: a Credentials part and rule 10, answering the choice PRESS-0002 §11 refused to make. **A calm loop — one finding landed on text this run wrote**, the vague hedge in the new Credentials row. **The sharpest finding is one no lane could settle, only raise:** Import was to carry *"the 63 published comments"*, and the export holds **70** approved comments on published posts — the other seven sit on the 29 Daily Prompt entries the Builder filters out. Rule 9 makes Import unrepeatable, so carrying what the site shows today would have lost seven readers' words permanently — the exact trap the Daily Prompt bullet one line above argues against. Measured off the WXR, not reasoned. **All three lanes found two things.** Rule 4's *"It writes only published entries into the site folder"* contradicted the disk table and `content/`: a literal implementer never publishes the fixed pages or the page furniture, and undo — which fetches `content/` back — could not recover the footer edit this document calls its highest-blast-radius. And the photograph naming rule was the Builder's, *"the one place that rule is written down"*, while Marks had to render the `src` from it, with rule 3 forbidding Marks a disk and rule 7 forbidding it reaching into the Builder. **The fix was not invented:** `PRESS-0004` §4.1 and `marks.py` already carry `PhotoSrc`, a callable the caller hands in — the design was the only document that did not say so. **Two lanes found the fallback file has two homes**, ADR-0003 putting it in the writer's profile directory and this document in Pressless's own folder; fixed in ADR-0003, along with the other two corrections PRESS-0002 §11 had owed since that spec was accepted. **Two lanes found the Analytics identifier ambiguous, and it is worse than they could see:** this document, PRESS-0001's prose and the changelog all say *property id*, while PRESS-0001 §4.1, `settings.py` and its tests spell the field `analytics_measurement_id` with an example value of `G-XXXXXXXXXX`. Measured against a live account, the reporting interface names a property as `properties/<number>`, so a measurement id cannot query it. The document now says which identifier and why; **the spec-and-code half is surfaced, not applied**, because it renames an accepted spec's field and shipped code. **One lane found rule 8's *"and nothing else"* barred the Insights cache** this same document puts on disk two sections later — the literal reading rule 10 exists to respect. **One lane found the untouchable list had no derivation moment**, so a verification token added to the repository root after setup is deleted on the next publish, unrecoverably by this section's own words. **One lane found the site folder called *"the git working copy"*** against the stack's *"No git on his machine"*. **Collateral, all caught by the sweep rather than a lane:** PRESS-0002's Status line and §11 still called the design decision open, and `CLAUDE.md`'s state block said PRESS-0002 had no code and was blocked — stale since the module shipped. **Two open questions resolved clean and are not counted:** 143 against 172 untitled entries are different populations, and the README's HTTP 200 is loop 2's measurement, still in the record. |
| 5 | 2026-08-25 | 3, cold — identical brief less one sentence, which asserted the document was otherwise unchanged and had stopped being true; packet rebuilt whole from disk, and deliberately NOT extended with the `PhotoSrc` window loop 4's fix would have been confirmed by | 1 | 3 | 2 | n/a | **Six verified, six fixed, none dismissed. Two of the six landed on text loop 4 wrote**, which is 4a-min's pattern and both were additions rather than deletions. **All three lanes found the worst of them, and it was mine:** loop 4 fixed the Analytics identifier by asserting Settings holds the property id *"never the `G-…` measurement id"* — while the shipped `settings.py` and PRESS-0001 §4.1 declare `analytics_measurement_id`, and the footer's tag needs exactly the id my sentence said Settings never holds. A confident fix in the direction the evidence pointed, past the point the evidence reached. **The over-claim is deleted and the choice is named rather than made** — a third dashboard trap says the two identifiers are not interchangeable, which of them Settings holds is unsettled, and passing the wrong one fails every fetch. **All three also found the packaging shape**: § The stack said *"one file per system"* against this document's own *"On Windows it is the extracted folder"* and discovery's record that Windows became a zip — so an implementer builds `--onefile` and Pressless's own folder, drafts and hundreds of megabytes of originals resolve beside a lone `.exe` in Downloads. ADR-0004 and `CLAUDE.md` carried the same stale shape and were corrected with it. **And all three found loop 4's other addition ambiguous**: with the rule re-applied at every publish, a root entry the Builder *stopped* producing is one it *does not* produce, so either nothing at root is ever deletable or the list protects nothing after setup. Now the rule says what the list must contain, the list is what the Publisher consults, and a file added to the root outside Pressless is stated as unprotected until the list is derived again. **Two lanes found undo silent on writing the fetched state does not hold** — delete it and S9 destroys writing against §Persistence's *"never silently dropped"*; keep it and undo does not undo a deletion. It becomes a draft. **One lane found the disk table names no home for the Store's published entries**, the one section whose job is to place everything, leaving Import, the Builder and undo to bind to an invention. **One lane found §`content/` said Settings *"keeps only"* three things against the parts table's six** — drop the Daily Prompt filter and the 2026-08-17 decision stops being reversible. That enumeration also omitted the historical comments loop 4 had just made load-bearing, so an undo could not have restored them. **Two open questions dismissed as immaterial and not counted:** *Chromium 151* against the test box's *Chrome and Edge* changes nothing built, and whether Insights returns country names or codes is a local choice between two dimensions Google offers, which is what Q3's narrowing leaves to the implementer. |
| 6 | 2026-08-25 | 3, cold — identical brief, packet rebuilt whole from disk; the open Analytics-identifier choice declared already-surfaced so it would not be re-found each loop | 0 | 4 | 7 | n/a | **Eleven verified, nine fixed, two filed. Cap reached (3 for an ADR / design doc); the run files its tail and exits.** **A CALM cap: about four of the eleven landed on text this run wrote**, each anchor checked against loops 4 and 5's ledger rather than recall — against roughly four-fifths at the 2026-08-24 cap. The document held more defects than the cap held loops, which is the shipping case rather than the oscillating one; at ~500 lines the size signal indicates no split. **Not one Q1** — every defect was a contradiction or a gap. **The two sharpest were pre-existing and structural, both first found here.** § What Import brings across carried four bullets and none of them the export's photographs, while rule 9 makes Import unrepeatable and the same document puts 453 MB of originals in the Store — so on the bullets as written twelve years of photographs stay on WordPress for good and every imported entry goes on pointing at the site he is leaving. And **nobody could derive the untouchable list**: the rule mandates a derived list, rule 5 lets the Publisher read *"Settings and a folder of finished files, and nothing else"*, and no part was given the capability — the same shape PRESS-0002 §11 recorded for Credentials, which rule 10 was added to settle. The Face now asks the Publisher what sits at the root and writes the result into Settings, and the Publisher's row gained that way in. **Rule 9 forbade the dependency setup needs** — *"Nothing may depend on Import"* against an Import row reading *"Run at setup and never again"*, with rule 1 giving the Face all ordering; it now binds after Import has run, and names setup as its caller. **Three findings were this run's own collateral, all in loop 5's additions.** Undo's *"an entry the fetched state does not hold becomes a draft"* covered entries and left the fixed pages, templates and page furniture that `content/` also carries with no rule, and said nothing about a photograph's original, which never goes to the site folder at all. And loop 5's *"setup is not the only moment that may happen"* named no other moment while the paragraph above it forbade the obvious one. **Two lanes found a template both an entry and not one** — *"A template is an entry he never publishes"* against rule 4 writing templates into the site folder and the disk table publishing them; it is now a Store file that never becomes a page, and the sentence restating it three lines down is deleted rather than reconciled. **ADR-0001's mark set omits the picture mark** that `PRESS-0004`'s table carries, so a parser built from the accepted file-format decision would print `{photo: seaside.jpg}` on the page as literal text — silently, by that ADR's own preserve rule. **Filed rather than fixed, both needing a decision this gate may not take:** which state a second undo fetches, and what becomes of Pressless's own folder when the program file it sits beside is replaced by the next release — PRESS-0022 owns the second. **The 143-untitled count is deleted rather than scoped**, per this project's own rule on counts. **Route from here: implementation.** |
| 7 | 2026-08-27 | 3, cold — genre pinned `adr`, packet carried all five ADRs whole, four `publisher.py` windows and the PRESS-0009 spec's §4 and §11; Windows / PyInstaller / the GitHub API and the Analytics API declared an unrunnable region, so Q1 was out of scope there | 2 | 2 | 0 | n/a | **Four verified, four fixed; three dismissed. First loop of a new run**, triggered by PRESS-0026's amendment to rule 5 — the 2026-08-25 run ended at a calm cap and that bar lapsed with this authoring edit. **All three lanes independently found the same defect, and it was this run's own amendment.** Rule 5 was widened to name the fetch-back's local write, in rule 8's form, as PRESS-0009 §11 asked. That turned an omission into an **exhaustive write list that excluded the Publisher's principal write** — `publish` POSTs blobs, a tree and a commit and PATCHes a reference to GitHub, and the parts table calls the part "Making GitHub match the folder it was handed". One lane found the sharpest reading: rule 10 says *"so rules 5 and 8 stay literally true"*, so rule 5 is meant to be read exhaustively, and it had just stopped being true. Rule 5 now takes rule 8's **full** form and grants the GitHub traffic. **Two lanes found the untouchable list's derivation naming no filter** — `root_entries`' own docstring says it "decides nothing and filters nothing … Setup and the Face remove those and store the rest", while the design said setup "writes the result into Settings", which puts `content/` on the list and stops it ever being pruned: the exact harm the same section names two paragraphs down. **One lane found the deletion rule scoped to root entries** while two neighbouring passages require pruning at any depth; `_is_protected` matches a path's first segment, so the fix states that. **One lane found *"he is never left unsure whether it went out"* false** against `OutcomeUnknown`. Not a design decision this gate took: the accepted PRESS-0009 spec already settles it — the honest "unknown" sentence is what keeps S6, and a read-back is ruled out because confirming would mean reaching GitHub, which is what just failed. **Collateral, caught by 4c and not by any lane:** the spec's §11 quoted rule 5's old text verbatim and still described the gap as open. **Dismissed:** ADR-0003's provenance sentence (all three lanes raised it; two judged it immaterial themselves, and nothing builds differently), the present-tense "it is checked" claim about an unbuilt test (the whole document is written in that voice), and untouchable directory semantics (no live divergence — none of the seven is a directory). **Filed, not fixed, both neighbouring contract documents with their own gates ahead:** PRESS-0028, `docs/discovery.md`'s S6 still stated absolutely; PRESS-0029, ADR-0005's Decision forbidding the cache its own Consequences grant. |
| 8 | 2026-08-27 | 3, cold — identical brief, packet rebuilt whole from disk and extended with the `_is_protected` window and the spec's § 9 failure table | 0 | 3 | 5 | n/a | **Eight verified, seven fixed, one filed. Not one Q1** — every defect was two passages disagreeing or a decision nobody had taken. **All three lanes independently re-opened rule 5, the deletion rule and the setup derivation against the code and found them consistent**, which is loop 7's four fixes verified by a cold read rather than by assertion. **About a third of the loop landed on text this run wrote**, each anchor checked against loop 7's ledger — a moderate figure, and the rest were pre-existing. **Two lanes found the sharpest defect, and it was loop 7's own fix**: rule 5 now granted a disk write and never said where it lands, while § Where everything sits on disk claims to settle exactly that class of question and lists two folders and a keyring. The site folder is itself "a folder it is handed", so the rule permitted fetching a previous state into the folder that gets published — one implementer re-uploads the old site's root files, another picks a scratch directory. The fetch area is now named in the disk table and in rule 5. **A lane's open question became the second**: "may talk to GitHub" is the form rule 8 uses for a read-only relationship, so "writes only into a folder it is handed" could still be read as covering every write. Rule 5 now says *may read and write GitHub*, and *writes to disk only*. **Two lanes found the last-resort message asserting "Your site has not changed" for anything unforeseen** — which, after loop 7 forbade guessing at an unknown outcome, is the one place nothing typed the guess out; and it carried no next-step clause, though the three-part rule has no exception for point 3 as it now does for point 2. **One lane found the Errors test checking point 2 alone** while the rule requires three parts, under the sentence "This is checkable, and it is checked". **One lane found the undo disposition naming entries, fixed pages, templates and furniture but not comments** — readers' words, so "an undo deletes nothing of **his**" does not reach them, and an implementer would delete them. **One lane found Insights specified to return country names while the flag lookup is keyed by country code** — two parts that must interoperate, settled one sentence each, differently. **One lane found "Every edit is recoverable in one step (S9)"** false for an edit not yet published: undo is sourced from the repository alone and Persistence keeps no prior version. Narrowed to *every published edit*, which is S9's own scope. **Filed, not fixed, both needing a decision this gate may not take:** PRESS-0030, which part builds the preview page; PRESS-0031, what undo does to a Store file changed since the last publish. **Dismissed:** ADR-0003's provenance (raised by two lanes, both judging it inert themselves), "all 862 pages" against ADR-0002's "roughly 862 files" (the lane could name no line anyone builds differently), and ADR-0005's internal split, already filed as PRESS-0029 by loop 7. |
| 9 | 2026-08-27 | 3, cold — identical brief, packet rebuilt whole from disk and extended with the `settings.py` surface; the two decisions filed by loop 8 declared already-surfaced so they would not be re-found | 0 | 4 | 2 | n/a | **Six verified, six fixed; one dismissed. Cap reached (3 for an ADR); the tail is empty of unfixed findings and the run exits.** **A VIOLENT cap: four of the six landed on text THIS RUN wrote**, each anchor checked against loops 7 and 8's ledger rather than recalled. **Correction to loop 7's row, which is not edited: that loop verified FIVE and fixed four.** A lane found *"never in either folder"* contradicting the ADR-0003 fallback the disk table and the Credentials row both grant; it was verified, then dropped between verification and the fix pass, and the row's count was written from the fix pass rather than from the ledger. A lane in this loop re-found it, which is the loop working, and it is now fixed — the Google authorisation falls back to the same owner-only file the publishing key does. **Two lanes found loop 8's recoverability fix still too strong**: narrowing *every edit* to *every published edit* was not enough, because `fetch_previous` reads the current commit's first parent and the spec records the consequence as decided — a second undo returns the state the first replaced. Undo is a toggle, not a history; the promise is now *the most recent publish*, and § What undo actually does says so. **Two lanes found loop 8's own last-resort fix leaning on a signal that does not exist** — it branches on whether a publish was in flight, and § 4.6 says the Publisher never keeps state between calls. Named: the Face knows because it drives the sequence (rule 1). **One lane found rule 5's fetch-back sentence had drifted to the wrong subject** — "so it never reaches the Store" reads as *the previous state* never reaching the Store, which is what undo exists to do; the Publisher is now the subject. **One lane found the undo disposition's kept files are rebuilt and republished**, so an undo removes an added fixed page from neither the Store nor the site — stated, since "an undo deletes nothing of his" already decided it. **One lane found nothing says how the Face learns what the Builder produces**, which loop 7's own fix introduced; the Builder names its own root output, for the reason rule 2 gives. **Dismissed:** the data-folder migration on upgrade, already filed in PRESS-0022 by loop 6 — a packet gap, since this run carried loop 8's filed items into the brief and not loop 6's. **Settled as a non-finding:** `root_entries` and `fetch_previous` read `commits/HEAD` where `publish` resolves the default branch by name; both resolve the same ref, so the routes differ and the behaviour does not — a code-side observation, out of a docs gate's scope. **Routing.** Size is not the problem: this document's body is about 30 KB against 31-37 KB for every spec sibling, so it is not oversized and a split is not indicated. The oscillation is concentrated — loops 8 and 9 both landed mostly on rule 5's fetch-back sentence and § Errors, the two places this run was actively editing. Per the violent-cap rule the review of this document AS IT STANDS ends here; it is not re-gated, and the bar lapses with the next authoring edit that changes direction. |
