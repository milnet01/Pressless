# `docs/design.md` — history

What `docs/design.md` used to say, and why it changed. Nothing here
instructs anything; that document governs.

## Rewritten 2026-10-02 for a full website creator and editor

`docs/discovery.md` was rewritten and agreed again on 2026-10-02
(PRESS-0198): Pressless builds and edits any kind of site, from nothing
or from an existing one, for any user. The design until then described
one writer's journal with a fixed set of pages, and these parts of it
stopped being true.

**Fixed pages.** Home, About, Music and Privacy were a fixed set. The
plain box edited a page's visible words in place and the code view
edited the file entire; a page was never regenerated, so Marks was never
involved. The home page was six picture tiles, so there the code view
was the real editor. Replaced by Blocks, a visual editor and a code
editor, and the round-trip rule that a section Blocks would not write
exactly as stored is kept as code.

**Import ran only on the maintainer's machine.** Rule 9 said the
maintainer runs Import once, before anything else, because that machine
held the photograph originals. The writer received the Pressless-data
folder it made, carrying the Store and a copy of the site's `assets/`
(PRESS-0007 decision 12), and no settings file. Decided with the user
2026-09-11; setup on an empty install added 2026-09-17 (PRESS-0124).
Replaced by an Import anyone runs, as one of setup's three starts.

**Settings held no measurement id.** Settled 2026-08-26: Settings held
the property id alone, and Pressless never wrote the footer tag.
Overturned by the user 2026-10-01 (PRESS-0199): Pressless writes the
tag itself.

**The site's name was in Settings.** Moved to the Store with the rest of
the site's identity, decided with the user 2026-10-02.

**What the first writer's Import measured.** The export held 616
published posts, 62 drafts, 8 private and 3 trashed; 29 Daily Prompt
entries, which the Builder filters on WordPress's own `dailyprompt-NNNN`
tag on his 2026-08-17 decision, so the site carried 587; 70 approved
comments on published posts, 7 of them on Daily Prompt entries; 6
categories and 167 tags. The footer reached 862 pages.

**The untouchable list, measured on his repository 2026-08-24**: seven
entries — `CNAME`, `.nojekyll`, `README.md`, the Search Console
verification file, `favicon.ico`, `apple-touch-icon.png` and
`COPY-ME-new-page.html`. Templates retired `COPY-ME-new-page.html` as a
way of working, but it stays on the site because it is untouchable.

**Why the header is single-copy.** The sibling workspace had written its
header out in eight places, and they had drifted: the journal carried a
six-item menu against the rest of the site's five.
