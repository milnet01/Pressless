# Pressless — Discovery

> **Purpose — so that later, anyone can tell whether the thing being
> built is still the thing that was wanted.**

Not a kick-off document. This is what everything is checked against for
the life of the project, which is why the signs of success below have to
be things you could actually observe.

**This document is a gate.** Design does not start until it is agreed —
`~/.claude/workflow.md` § 2. It passes when a stranger could read it and
say whether a given feature serves it.

**Status:** agreed 2026-08-17; amended and re-agreed 2026-08-24.

**What the amendment changed, and why it is recorded rather than quietly
patched.** Three things were asked for on 2026-08-24: a what-you-see-is-
what-you-get editor, editing the fixed pages, and reaching the site's own
code. The first is a *how* and belongs to design. The other two were
listed below as deliberately out of the first version, so this document
became false, and `~/.claude/workflow.md` § 7 sends a false discovery
back to state 1 with the human gate re-armed. Nothing was in flight and
no code existed, so the whole cost was this edit and agreeing it.
**The reversed exclusions are struck through rather than deleted** — a
decision that was reversed is more useful to a later reader than one
that was erased.

## The problem

The writer this was built for has twelve years of journal entries. They
live on a free WordPress.com blog, which means three things he does not
want and cannot change:

1. **His writing is not his to move.** Getting it out took an export
   file and a program written specially to read it. Anything he writes
   from here stays in the same trap unless something changes.
2. **The free plan decides what his site looks like.** No custom styling,
   no custom fonts, and WordPress's own marketing on his pages.
3. **He cannot tell when something is broken.** His subscribe box had no
   working connection behind it for years. Visitors typed their address,
   believed they had subscribed, and nothing was recorded. Nobody found
   out until somebody went looking.

A new site fixes all three — but only while somebody technical is
available to publish it. **That is the actual hurt this project
addresses: right now he cannot change a word of his own site without
asking someone else to do it for him.** He writes at odd hours; the
person who can publish does not.

## Who it is for

- **A person who writes most days, often late, and wants what he just
  wrote to be readable by other people within the hour** — without
  waiting for anyone, and without learning what a repository is.
- **A person who has been burned once by a service owning his words**,
  and will not agree to that a second time even if it is more convenient.

A third, secondarily: **a person in the same position** — the
app is deliberately not named after him, because the problem is not his
alone. Nothing in the first version is built for that person, but
nothing should be built in a way that locks them out either.

## Signs it is working

- **S1** — He writes a new entry on his own machine, clicks one
  button, and within a few minutes it is on the live site. Nobody else
  touched anything.
- **S2** — A poem he publishes through Pressless has the same line
  breaks on the live site as in the box he typed it into. Not a
  paragraph; the lines he wrote, where he wrote them.
- **S3** — With Pressless closed, deleted, or never installed, all his
  writing is still readable: ordinary files in an ordinary folder, one
  per entry, openable in Notepad.
- **S4** — He installs it on Windows by following the written steps and
  nothing in those steps is different from the ones followed on Linux,
  other than which file is double-clicked.
- **S5** — He is asked for his publishing key exactly once, during
  setup, and never sees it again in normal use.
- **S6** — When publishing fails — no internet, wrong key, GitHub down —
  he is told so in a sentence he understands, the site is unchanged, and
  clicking Publish again after fixing it works. He is never left unsure
  whether it went out.
- **S7** — An entry he has not finished is not on the live site. He can
  close the app mid-sentence, come back tomorrow, and it is where he
  left it and nowhere else.
- **S8** — He changes the wording on his About page himself and within a
  few minutes the live site says the new thing. He did not write an
  entry to do it, and nobody else touched anything.
- **S9** — After a change that made the site wrong, he gets it back the
  way it was in one step, and can see for himself that it is back. He is
  never left having broken something he cannot undo.
- **S10** — A word he styles while typing looks the same on the live site
  as it did in the box. What he saw is what he got, and he did not have
  to publish to find out.
- **S11** — He opens Pressless and can see how many people read his site
  and which countries they came from, each country shown with its flag.
  He did not log in to anything and did not leave the app.

## What it deliberately does not do

**Not in the first version, and that is a decision rather than a
backlog:**

- **No newsletter.** It is the feature with the most ways to go wrong —
  consent, a mail service, unsubscribes, South African data-protection
  law — and it serves very few confirmed opt-ins. It comes after S1 to
  S10 are all true.
- **No comments.** Agreed with him. The 70 historical ones stay on the
  site as a read-only record. When comments return, Pressless is where
  he approves them.
- ~~**No editing the fixed pages** (About, Songs, Images). Writing
  entries is what he does daily; the other pages change a few times a
  year and can wait.~~ **Reversed 2026-08-24.** Editing the fixed pages
  is in the first version, and so is reaching a page's own code behind a
  "show me the code" view. S8 and S9 are the signs that say whether it
  works. The original reasoning measured frequency, and frequency was
  the wrong measure: a change he makes twice a year still costs him a
  phone call, and the phone call is the hurt this project exists to
  remove.
- ~~**No editing entries already published.** Publishing a new one is
  the whole first version.~~ **Reversed 2026-08-24.** It was withheld to
  keep the first version small, and withholding it stopped meaning
  anything the moment he could reach the site's files: he could edit a
  published entry anyway, by a worse route and with no safety net. A
  capability held by accident is more dangerous than one designed for.
- ~~**No visitor statistics.**~~ **Reversed 2026-08-24: Pressless shows
  them.** Asked for on 2026-08-17 and recorded
  here so it is not lost: he wants to know how many people visit and
  roughly where from. Settled with the user the same day — **country and
  province, and city is explicitly not wanted**, because a visitor's
  location is worked out from their internet provider's nearest hub and a
  South African mobile user in Potchefstroom reads as Johannesburg. City
  would be a number that looks precise and is not.

  Two things about it are already fixed by decisions above, and design
  does not get to reopen them. **Pressless cannot collect this**, because
  it runs on his own machine and is never reachable from the internet, so
  a visitor cannot report to it. And **GitHub Pages keeps no visitor log**
  — the traffic graph on a GitHub repository counts people reading the
  code, not the site. So the shape is a service collecting and Pressless
  displaying, never Pressless collecting.

  It sits here rather than among the signs of success because it serves
  nobody's ability to publish. It is a thing he would like to see, not a
  thing that makes the first version work.

  **Overtaken by events, then reversed.** Google Analytics went live on
  the site on 2026-08-23, which answered the collecting half without
  Pressless.
  The displaying half was asked for on 2026-08-24 and is now S11, so
  **Pressless does display these numbers in the first version** — the
  struck heading above is the whole of what was reversed, and the shape
  this paragraph predicted (a service collects, Pressless displays) is
  exactly what was built.

  Two details settled with it. **Province was dropped, leaving country
  only**, because what was asked for was visits by country with its flag
  — a departure from the sentence above, recorded here rather than left
  for a reader to notice. And **city, which this document says was
  explicitly not wanted, is reported by what shipped** — a disagreement
  about the site rather than about this app, still open below.

**Not ever, as far as this document is concerned:**

- **Pressless is not a website host and never talks to visitors.** It
  runs on his own machine, is not reachable from the internet, and
  has no login, no accounts and no users. The published site is plain
  files served by GitHub.
- **Pressless does not own his writing.** If this project is abandoned
  tomorrow, S3 must still hold. Any design that makes his entries
  readable only through this app is out of scope by definition.
- **Pressless is not a WordPress replacement for the general public.**
  One person's site, on one person's machine.

## Shape agreed with the user (2026-08-17)

Recorded here because design must not silently choose otherwise. The
*reasons* belong in `docs/design.md`; these are the constraints it works
within.

| Decision | Chosen |
|---|---|
| First version does | Write an entry, preview it, publish it |
| How it appears | Opens in his normal browser; runs entirely on his own machine |
| How it publishes | Straight to GitHub, using a key he pastes in once at setup |
| Where writing lives | One plain text file per entry, in a folder he can see |

**Added 2026-08-24, same standing — design works within these, and the
reasons live in `docs/design.md` and the ADRs beside it.**

| Decision | Chosen |
|---|---|
| How he writes | A what-you-see-is-what-you-get box styled as the finished page. The file underneath stays plain text with small marks |
| How he styles | Bold and italic, his site's own two colours, any colour he picks down to a single letter, and run-wide effects such as rainbow |
| Learning the marks | A cheat sheet **generated from the same table the app parses with**, so the card and the app cannot disagree. In-app panel and a printable page |
| Fixed pages | Editable — the words in the same box as an entry (words only; styling a page is done in the code view), the page's own code behind a "show me the code" view |
| Getting back | One step returns the site to how it was, and he can see that it worked |
| Where the site lives | His entries sit inside his site folder as `content/`, so publishing backs up twelve years of writing as a side effect |
| Photographs | In the first version. About one entry in three carries one |
| Starting something new | He picks from a list of templates — a poem, a lyric, an entry around a photograph, a plain entry — and it opens already shaped. He can edit them and add his own |

## Open questions

These are not blockers for design, but each has to be answered before
the thing it touches is built.

- ~~**Photographs in an entry.**~~ **Settled 2026-08-24: in the first
  version.** Leaving them out meant he still had to ask someone for a
  third of what he writes, which is most of the hurt left standing. The
  shrinking already exists and works — `_work/resize.py` in the sibling
  workspace turns 220 MB of camera originals into 31 MB.
- **The 616 existing entries have to become files.** Choosing "one file
  per entry" means the twelve years currently held in the WordPress
  export must be converted once, up front — otherwise publishing a new
  entry would rebuild a site that has forgotten all the old ones. This
  is a one-time job and it is a prerequisite for S1, not a later nicety.
- ~~**His GitHub account does not exist yet.**~~ **Settled 2026-08-17:
  it exists.** The account, the repository and the live domain are named
  in this machine's settings rather than here, which is the same rule the
  paragraph below applies to the app. Publishing can be tested against
  the real thing.

  **The rule it carried still stands, and now costs something.** Testing
  against his live site means a wrong move is visible to the public
  within a minute. So the difference between his repository and a
  throwaway one must stay out of the app — it belongs in settings — and
  the automated tests publish to a repository we control, never to his.
- **The 172 untitled entries.** Mostly recent daily-prompt writing.
  Whether Pressless should require a title, suggest one, or accept none
  is a question about his habit, and he should be asked.
- **Does the visitor-statistics decision still hold?** This document
  says city was explicitly not wanted; what went live on 2026-08-23
  reports it. Nothing in the first version depends on the answer —
  Pressless neither collects nor shows these numbers — but the two
  records disagree and one of them should change. It is his call,
  and it is a question about the site rather than about this app.
- **Likes and dislikes on entries — agreed in principle 2026-08-24,
  parked on one question for him.** Both buttons, publicly, counts
  stored in a free Google (Firebase) database. It is not designed or
  built yet and is deliberately absent from `docs/design.md`, because it
  would be the site's first dependency on a live service: today the site
  is plain files and cannot break.

  **The parked question is narrow and is being put to him: may the
  site quietly remember which entries a visitor's browser has already
  voted on?** That is anonymous sign-in — no account, no password,
  nothing the visitor sees or does — and it is what lets Google, rather
  than the page, enforce one vote per person per entry. **It is not a
  login**, and the distinction matters because *this document already
  rules real logins out* under "Not ever". If the answer is no, the
  counts fall back to a note the visitor's own browser keeps and can
  erase, which stops an honest double-click and nothing else.

  Two things settled whatever he answers: billing stays switched off on
  the database, so the worst case of abuse is a quiet day rather than a
  bill; and the privacy page gains a line, since POPIA applies here as
  it does to the visitor counting.

  **The anti-spam design, recorded so it is not re-derived.** Four
  layers, all free: a note in the visitor's own browser (stops the honest
  double-click and nothing else); anonymous sign-in (the parked
  question); a security rule allowing one vote document per person per
  entry, which Google enforces so editing the page's code achieves
  nothing; and App Check, which is the layer that actually blunts
  scripted abuse. One vote document per person also buys vote-changing
  and un-voting, which a bare counter cannot do. **Counting them with
  the database's own `count()` avoids Cloud Functions**, and that is
  what keeps billing switchable-off — verify against current Firebase
  terms on the day, rather than trusting this line.

- **What happens to a mark the app does not recognise?** The intended
  answer is that it is left exactly as written and never silently
  dropped, which is what stops an editor eating writing it did not
  understand. Recorded here because it is a promise about his twelve
  years, and design must state it rather than assume it.
