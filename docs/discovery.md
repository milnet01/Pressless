# Pressless — Discovery

> **Purpose — so that later, anyone can tell whether the thing being
> built is still the thing that was wanted.**

Not a kick-off document. This is what everything is checked against for
the life of the project, which is why the signs of success below have to
be things you could actually observe.

**This document is a gate.** Design does not start until it is agreed —
`~/.claude/workflow.md` § 2. It passes when a stranger could read it and
say whether a given feature serves it.

**Status:** agreed 2026-08-17; rewritten for a full website creator and
editor and agreed again 2026-10-02 (PRESS-0198). How it got here
is in [`history/discovery.md`](history/discovery.md).

## The problem

Pressless began with one writer whose whole website — its pages, its
music, its photographs, and twelve years of journal entries — sat on
free WordPress.com. That meant three things he did not want and could
not change:

1. **His writing was not his to move.** Getting it out took an export
   file and a program written specially to read it.
2. **The free plan decided what his site looked like.** No custom
   styling, no custom fonts, and WordPress's own marketing on his pages.
3. **He could not tell when something was broken.** His subscribe box
   had no working connection behind it for years, and nobody found out
   until somebody went looking.

A new site fixed all three — but only while somebody technical was
available to publish it. **That is the hurt this project addresses: a
person cannot change a word of their own site without asking someone
else to do it for them.**

The problem is not his alone. Anyone who wants a website they own and
run themselves is offered the same two choices: a hosted service that
owns their words and decides their look, or code they cannot write.
Pressless is a third choice: **a full website creator and editor that
runs on their own computer and needs no code.** It builds any kind of
site from nothing — a band's, a business's, a club's, a journal — or
takes in a site that already exists and lets them change every part of
it. A journal of dated entries is one thing a site can hold, not what a
site is.

## Who it is for

All of these equally. A feature that serves one and locks out another
is out of scope.

- **A person who writes most days, often late, and wants what they just
  wrote to be readable by other people within the hour** — without
  waiting for anyone, and without learning what a repository is.
- **A person who has been burned once by a service owning their words**,
  and will not agree to that a second time even if it is more convenient.
- **A person starting from nothing**, with no site and no web skills,
  who wants a site of their own — whatever kind — that they can build,
  change and keep running by themselves.
- **A person with a site already**, on WordPress or as a folder of web
  pages, who wants to run it themselves, and needs every page, picture,
  file and word to come with them.

## Signs it is working

The labels are permanent: specs and code cite them, so a sign is
reworded, never renumbered.

- **S1** — They write a new entry on their own computer, click one
  button, and within a few minutes it is on the live site. Nobody else
  touched anything.
- **S2** — A poem they publish has the same line breaks on the live site
  as in the box they typed it into. Not a paragraph; the lines they
  wrote, where they wrote them.
- **S3** — With Pressless closed, deleted, or never installed, all their
  writing is still readable: ordinary files in an ordinary folder, one
  per entry, openable in Notepad.
- **S4** — They install it on Windows themselves, by following the
  written steps and asking nobody for help. The steps are complete for
  their machine: nothing has to be installed first, and nothing has to
  be translated from another system's instructions.
- **S5** — They are asked for their publishing key exactly once, during
  setup, and never see it again in normal use.
- **S6** — When publishing fails — no internet, wrong key, GitHub down —
  they are told so in a sentence they understand, the site is unchanged,
  and clicking Publish again after fixing it works. They are never left
  unsure whether it went out, **except** where GitHub may have taken the
  last step without confirming it, or where something Pressless did not
  foresee fails while a publish is running. Then nobody can know whether
  the site changed, so they are told plainly that the outcome is unknown.
  Pressless or their computer stopping partway through a publish is
  outside S6. Either way, clicking Publish again is safe and settles it.
- **S7** — An entry they have not finished is not on the live site. They
  can close the app mid-sentence, come back tomorrow, and it is where they
  left it and nowhere else.
- **S8** — They change the wording on their About page themselves and
  within a few minutes the live site says the new thing. They did not
  write an entry to do it, and nobody else touched anything.
- **S9** — After a change that made the site wrong, they get it back the
  way it was in one step, and can see for themselves that it is back.
  They are never left having broken something they cannot undo.
- **S10** — A word they style while typing looks the same on the live
  site as it did in the box. What they saw is what they got, and they did
  not have to publish to find out.
- **S11** — They open Pressless and can see how many people read their
  site and which countries, and which provinces or states within them,
  they came from, each country shown with its flag, without leaving the
  app. Never cities: a visitor's city is guessed from their provider and
  is often wrong.
- **S12** — Someone with no site downloads Pressless, sets it up, and
  publishes a working site of the kind they want, with a homepage, a
  menu, a header and a footer. They wrote no code and asked nobody for
  help.
- **S13** — Someone with an existing site, on WordPress or as a folder
  of web pages, brings all of it in themselves — pages, menus, entries,
  drafts, comments, photographs and files — and is told, item by item,
  about anything that could not come across. From then on every part of
  it can be changed in Pressless.
- **S14** — They add a page, rename one, or remove one, and the site's
  menu follows. They wrote no code.
- **S15** — They build a new homepage, with their own pictures, links,
  header, footer and menu, and see it in the preview before it goes
  live. They wrote no code, and could have opened the page's code had
  they wanted to.
- **S16** — They change their site's colours, fonts and layout by
  picking from choices, and see the result in the preview before
  publishing. Anyone who wants more can edit the style code itself.
- **S17** — They put a music file, a download or a PDF on their site and
  link to it from a page. They wrote no code.
- **S18** — Someone new switches on visitor numbers by following
  Pressless's own steps. Pressless puts the counting code on every page
  itself; the steps cover only what Google makes a person do in person.

## What it deliberately does not do

**Not now — each is a decision, and each can return as its own
decision later:**

- **No newsletter.** It is the feature with the most ways to go wrong —
  consent, a mail service, unsubscribes, South African data-protection
  law.
- **No new comments.** Comments already on a site stay as a read-only
  record. A site of plain files cannot take comments without an outside
  service.
- **One site per copy of Pressless.** Someone with two sites keeps two
  Pressless folders.
- **GitHub Pages is the only place a site is published.** Pressless does
  as much of the GitHub setup as it can, and gives step-by-step help for
  the rest.

**Not ever, as far as this document is concerned:**

- **Pressless is not a website host and never talks to visitors.** It
  runs on the person's own computer, is not reachable from the internet,
  and has no login, no accounts and no users. The published site is plain
  files served by GitHub.
- **Pressless does not own anyone's writing.** If this project is
  abandoned tomorrow, S3 must still hold. Any design that makes entries
  readable only through this app is out of scope by definition.
- **The automated tests never publish to a real person's site.** A wrong
  move there is public within a minute, so tests publish only to a
  repository the project controls, and which repository is a setting,
  never code.

## Shape agreed with the user

Design works within these and must not silently choose otherwise. The
*reasons* live in `docs/design.md` and the ADRs beside it.

| Decision | Chosen |
|---|---|
| What it does | Build a whole website of any kind from nothing, or take in an existing one; change every page, menu, header, footer, picture, file and style in it; write, preview and publish entries where the site keeps a journal |
| How it appears | Opens in their normal browser; runs entirely on their own computer |
| How it publishes | Straight to GitHub Pages, using a key they give it once at setup |
| Where writing lives | One plain text file per entry, in a folder they can see |
| How they write | A what-you-see-is-what-you-get box styled as the finished page. The file underneath stays plain text with small marks |
| How they style | Bold and italic, the site's own colours, any colour they pick down to a single letter, and run-wide effects such as rainbow |
| Learning the marks | A cheat sheet **generated from the same table the app parses with**, so the card and the app cannot disagree. In-app panel and a printable page |
| Building pages | No code needed for anything, the homepage included. As WordPress does it, but simpler: a visual editor that shows the page as it will look, and a code editor for anyone who wants it |
| The menu | Follows the pages by itself — a new page joins it, a removed one leaves it — and a list lets them reorder it, hide a page from it, or add a link to another site |
| Interactivity | A few ready-made interactive pieces a page can hold, such as a picture slideshow or questions that fold open, and a place for their own script for anyone who writes one |
| The site's look | Ready-made choices — colours, fonts, layouts — with a live preview, plus the style code for anyone who wants more |
| Getting back | One step returns the site to how it was, and they can see that it worked |
| Where the site lives | Entries sit inside the site folder as `content/`, so publishing backs up their writing as a side effect |
| Photographs and files | Photographs, music, downloads and documents, each linked from a page |
| Starting something new | They pick from a list of templates — a poem, a lyric, an entry around a photograph, a plain entry — and it opens already shaped. They can edit them and add their own |
| Starting from nothing | A plain starter site — homepage, menu, header, footer and About — that they change into their own |
| Help | Whatever Pressless can do for them, it does. Whatever it cannot comes with step-by-step instructions |

## Decided, not yet scheduled

- **Likes and dislikes on entries** — agreed 2026-10-02, a roadmap item
  of its own after the whole-site work. Both buttons, publicly, counts
  stored in a free Google (Firebase) database, because a site of plain
  files cannot keep a count. Optional per site, and it would be a site's
  first dependency on a live service. Each site needs its own database,
  which Pressless helps set up step by step.

  **The site quietly remembers which entries a visitor's browser has
  already voted on.** That is anonymous sign-in — no account, no
  password, nothing the visitor sees or does — and it lets Google,
  rather than the page, enforce one vote per person per entry. **It is
  not a login**, which *Not ever* rules out.

  Billing stays switched off on the database, so the worst case of abuse
  is a quiet day rather than a bill; and the privacy page gains a line,
  since POPIA applies here as it does to the visitor counting.

  **The anti-spam design, recorded so it is not re-derived.** Four
  layers, all free: a note in the visitor's own browser; anonymous
  sign-in (the parked question); a security rule allowing one vote
  document per person per entry, which Google enforces so editing the
  page's code achieves nothing; and App Check, which blunts scripted
  abuse. One vote document per person also buys vote-changing and
  un-voting. **Counting with the database's own `count()` avoids Cloud
  Functions**, which keeps billing switchable-off — verify against
  current Firebase terms on the day.
