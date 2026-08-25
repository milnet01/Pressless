# ADR-0001: An entry is plain text with small marks — not Markdown, not HTML

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

S3 requires that with Pressless gone, every entry is still readable as an
ordinary file in an ordinary folder. S2 requires that a poem keeps the
exact lines it was typed with. S10 and the agreed shape require a
what-you-see-is-what-you-get editor with bold, italic, colours down to a
single character, and run-wide effects.

Those pull against each other. Markdown is the obvious plain-text
answer and it collapses single newlines into one paragraph — for a poem
the line break *is* the content, so Markdown's central rule is wrong
here. HTML carries every style perfectly and stops the file being
readable prose: open it in Notepad and you get angle brackets.

## Decision

Entries are UTF-8 text. A short `Key: value` header, a blank line, then
the body verbatim. **Every single newline in the body is a line break.**

Styling is a small set of marks the body carries inline:
`**bold**`, `*italic*`, `{accent}word{/}` for the site's own colours,
`{#c0453a}word{/}` for any colour he picks, and `{rainbow}word{/}` for
run-wide effects.

**Anything the parser does not recognise is preserved byte-for-byte and
never dropped.**

## Consequences

- S2 holds by construction rather than by care — there is no rule that
  could collapse a line.
- S3 holds for ordinary writing. It **degrades exactly where he styles
  heavily**: a line where every character is individually coloured is
  still text, but it is no longer a readable poem. That cost is paid
  only on the words he chose to style, and `{rainbow}` exists so the
  common reason for per-character colour does not incur it.
- We own a parser. It is small, but it is ours to keep correct, and
  every one of the 616 existing entries must survive a round trip
  through it unchanged.
- Nothing else can read these files natively. That is the price of not
  using Markdown, and it is why the preserve-what-you-do-not-understand
  rule is not optional.
