# `docs/discovery.md` — history

What `docs/discovery.md` used to say, and why it changed. Nothing here
instructs anything; that document governs.

## Agreed 2026-08-17; amended and re-agreed 2026-08-24

Three things were asked for on 2026-08-24: a what-you-see-is-what-you-get
editor, editing the fixed pages, and reaching the site's own code. The
first is a *how* and belongs to design. The other two were listed as
deliberately out of the first version, so the document became false, and
`~/.claude/workflow.md` § 7 sends a false discovery back to state 1 with
the human gate re-armed. Nothing was in flight and no code existed, so
the whole cost was the edit and agreeing it. S6 was amended 2026-09-11 on
the user's decision.

## S4 reworded 2026-08-25

S4 read "nothing in those steps is different from the ones followed on
Linux, other than which file is double-clicked". That stopped being true
when Windows became a zip that is extracted and Linux an AppImage.
Identical steps were only ever a proxy for installing it unaided, and it
is the proxy that broke.

## S11 reworded 2026-10-02

S11 read "He did not log in to anything and did not leave the app." That
held for the first writer, whose Google authorisation was set up for
him. Someone new must sign in to Google once to let Pressless read their
numbers (PRESS-0199, S18), so the sign now says only that they do not
leave the app. The same day the user asked for provinces or states as
well as countries, and confirmed cities are not needed. That settled
the open question of whether the city exclusion still held: it does.

## Likes decided 2026-10-02

Likes had been parked since 2026-08-24 on whether a site may quietly
remember which entries a visitor's browser has voted on. The user said
yes on 2026-10-02, as a roadmap item after the whole-site work.

## Exclusions reversed 2026-08-24

- **No editing the fixed pages** (About, Songs, Images). The reasoning
  measured frequency, and frequency was the wrong measure: a change he
  makes twice a year still cost him a phone call, and the phone call is
  the hurt the project exists to remove. S8 and S9 replaced it.
- **No editing entries already published.** Withheld to keep the first
  version small. It stopped meaning anything once he could reach the
  site's files: he could edit a published entry anyway, by a worse route
  and with no safety net.
- **No visitor statistics.** Asked for on 2026-08-17: how many people
  visit and roughly where from — country and province, and city
  explicitly not wanted, because a visitor's location is worked out from
  their provider's nearest hub. Two things were fixed then: Pressless
  cannot collect this, since it is never reachable from the internet; and
  GitHub Pages keeps no visitor log. So a service collects and Pressless
  displays. Google Analytics went live on the site on 2026-08-23; the
  displaying half was asked for on 2026-08-24 and became S11. Province
  was dropped, leaving country only, because what was asked for was
  visits by country with its flag.

## Open questions settled

- **Photographs in an entry** — settled 2026-08-24: in the first version.
  Leaving them out meant he still had to ask someone for a third of what
  he writes.
- **The existing entries have to become files** — a one-time conversion
  of the WordPress export, a prerequisite for S1. Done by PRESS-0007.
- **His GitHub account does not exist yet** — settled 2026-08-17: it
  exists. The account, repository and domain are named in this machine's
  settings, not in the documents.
- **The untitled entries** — settled by PRESS-0012 § 3: an entry needs no
  title, and one without takes the address `untitled`.
- **What happens to a mark the app does not recognise** — settled by
  ADR-0001: it is preserved byte for byte.

## Rewritten 2026-10-02 for a full WordPress replacement (PRESS-0198)

On 2026-10-01 the user widened Pressless from writing and publishing
entries to managing the whole site, and said this was always the aim: a
WordPress replacement for the first writer and for anyone else who needs
one (PRESS-0194). On 2026-10-02 the user made it explicit: a full
website creator and editor, for any kind of site, built from nothing or
taken in and then changed in every part. The first writer's site is a
whole website that includes a journal, and the document had been
describing it as a blog. The document had said, under *Not ever*: "Pressless is
not a WordPress replacement for the general public. One person's site, on
one person's machine." That line was removed, and S12 to S18 were added.
The user's decisions of 2026-10-02 are recorded on PRESS-0198.

Until then the people it was for were listed as the first writer twice
over, with a third, secondarily: "a person in the same position — the app
is deliberately not named after him, because the problem is not his
alone. Nothing in the first version is built for that person, but nothing
should be built in a way that locks them out either." On 2026-09-17
(PRESS-0124) the user ruled that no design should cater only for him,
and on 2026-10-02 that both are served equally.
