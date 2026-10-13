# ADR-0006: A page's sections are marked by comments naming the kind, inside its `main`

- **Status:** Accepted
- **Date:** 2026-10-13

## Context

A visual editor needs a page in units it can show, move and change. A
fixed page is the user's own HTML, and nothing in it says where one part
ends and the next begins. The round-trip rule in `docs/design.md` says a
section whose HTML is not exactly what Blocks writes is kept as code, so
the marks must not themselves become a second copy of the page.
`docs/specs/PRESS-0215-blocks.md` holds the full design.

## Decision

- **A mark is an HTML comment naming the kind and nothing else**, such
  as `<!-- pressless:text -->`. Every value a section holds is read from
  its HTML.
- **A page has one sections area, inside its `main`.** Everything outside
  it, the header and footer markers included, is the page's frame and is
  changed only in the code view.

## Consequences

- **One copy of each value.** WordPress puts a block's values as JSON in
  its opening comment as well as in the HTML, and the two can disagree.
  Here there is nothing to disagree with.
- **An element is never changed to mark it.** `data-` attributes would
  have marked sections too, but a page taken into sections would then
  gain attributes, and a plain paragraph would stop being plain.
- **The frame is out of the visual editor's reach**, so it cannot move
  the header markers or the `head`.
- **The marks never reach the published site**: the Builder removes them.
