# PRESS-0004 — Marks: one table, one parser, one renderer

**Status:** accepted (2026-08-25), amended since; each amendment was
gated or exempt as recorded in `../history/PRESS-0004-marks.md`.
PRESS-0123 amends §4.1, §4.2, §4.3 and §4.5 (accepted 2026-09-29).
**Kind:** implement.
**Source:** ROADMAP PRESS-0004 (`docs/design.md` § The parts; ADR-0001).

**Blocker for:** PRESS-0007, PRESS-0008, PRESS-0012, PRESS-0016, PRESS-0018.

<!-- Layman -->
**In plain English:** the small styling language — bold, italic, a colour,
a photograph — written down once, so the box the writer types into and
the page his readers see can never disagree about what a poem looks like.

## 1. Goal

After this ships there is one piece of code that turns a writer's marked
text into HTML, and every part that renders — the Builder making the live
page, the Face showing the preview, the cheat sheet listing what he can
type — reads it. It touches no disk and no network, so it can be tested
exhaustively against the twelve-year archive before anything else exists.

## 2. Problem

Nothing renders yet, and two different parts will need to. `docs/design.md`
§ What may depend on what rule 2 forbids them each having their own path:
two renderers diverge, and the first person to find out is the writer,
after publishing. Rule 3 forbids this part touching a disk or a network.

The archive is what makes the contract sharp rather than obvious. What
follows was measured against the WordPress export, over the entries Import
carries — published, drafts and private, but not trashed (the *What Import
brings across* paragraph of `docs/design.md`). The archive test prints the
figures; §7 owns that, and they are deliberately not repeated here.

1. **Most entries are raw newline text.** For these the line break *is*
   the content — ADR-0001 — so any rule that reflows a paragraph destroys
   the writing.
2. **A handful of entries already contain `*`**, every one of them
   self-censoring prose or a divider: `f*cking`, `sh*t`, `p*rn`, `b**bs`,
   and one line of nothing but asterisks. Almost all are lone asterisks
   with no partner on their line. A naive italic rule run over a whole
   body rather than a line pairs them across line breaks and italicises
   several published poems.
3. **Many raw-text entries contain `&`**, always as a character reference
   — `&nbsp;`, `&apos;`, `&amp;` — and **never bare**. So a blanket
   `&` → `&amp;` would put a literal `&nbsp;` on every one of those pages.
4. **Some raw-text entries contain `<` or `>`**, mostly stray
   `<span id="selectionBoundary_…">` left by the WordPress editor. Today's
   generator escapes them, and pages on the live site show that markup as
   visible text today. That is the current behaviour, and reproducing it is
   the contract — improving it is a separate decision about his writing.

Today's behaviour is `tools/build_blog.py::wpautop()` and
`tools/build_blog.py::render_body()` in the sibling workspace: blank line
starts a paragraph, single newline becomes `<br>`, `<` and `>` are escaped,
`&` is left alone. That function is what PRESS-0008 re-homes.

**Marks is deliberately not that function, and INV-5 owns the
difference.** It adds a mark language, and it escapes an `&` that begins
no character reference, where `wpautop()` leaves one alone. Neither difference shows on the archive,
because nothing in the archive triggers either — a fact about the data,
not a property of the code.

## 3. Scope decisions (agreed with the user)

The choices below marked as the user's or as decided here were preference
rather than deduction. The rest follow
from §2.

1. **The two named site colours are `{accent}` and `{muted}`.** ADR-0001
   and the roadmap say "the site's own colours" without naming them. The
   live stylesheet defines exactly one accent (`--accent`, a comment on the
   token block reads *"accent: ONE colour, every tint derived from it"*)
   and one secondary ink (`--muted`). Those are the two.
2. **Named colours render as the CSS variable, never as a hex value.**
   `{accent}` emits `var(--accent)`. Repainting the site then repaints
   twelve years of entries; baking `#8fd0e0` into the HTML would freeze
   today's palette into every page written from now on.
3. **There is no escape character.** A writer cannot type a literal
   `{accent}` and have it appear on the page. §8 records why, and §9 keeps
   the door open.
4. **Marks gains a link mark and a quote mark.** Decided with the user
   2026-09-11, so the archive's WordPress-HTML entries convert with
   nothing he wrote lost (PRESS-0007). **(decided here: the syntax.)** A
   link is `{link: address}words{/}`, because every other mark that takes
   an argument is a brace mark. A quotation is lines beginning with `>`,
   because a quotation spans lines and no mark may (INV-3). **A picture's
   link to its own full-size file is not carried**: that file is an
   original, and originals are never published (PRESS-0007 §3 decision 7).

## 4. Design

### 4.1 The public surface

`src/pressless/marks.py` exports the table (`MARKS`, `Mark`), three
functions, the node types `parse` returns (§4.3), and the two callable
aliases `PhotoSrc` and `Renderer`, and `value_text` (PRESS-0123 §4.1).
Nothing else.

```python
def parse(body: str) -> Document              # text in, structure out
def to_html(doc: Document, photo_src: PhotoSrc, today: date | None = None) -> str
def render(body: str, photo_src: PhotoSrc, today: date | None = None) -> str   # parse + to_html
```

`today` is what a `value` mark is worked out against; PRESS-0123 §4.1
owns it.

`PhotoSrc` is `Callable[[str], str]`: given a picture's file name it
returns the address to put in `src`. **The name is one plain file name**
(§4.2) — at least as strict as PRESS-0006's INV-11, which governs where the
original is kept. So a name Marks accepts is always one the Store accepts,
never the reverse: Marks also refuses DEL, which the Store takes, so a name
the Store stores can be one Marks will not display, and PRESS-0016 owns
that gap rather than this document. **Marks never builds a path.** The
Builder passes its web-copy naming rule (PRESS-0008 owns that rule); the
Face passes an address serving the original for preview (PRESS-0012). This
callable is how rule 3 is kept while the picture mark still works.

### 4.2 The table

```python
@dataclass(frozen=True)
class Mark:
    name: str        # "bold", "colour", "rainbow", "photo" -- Span.mark
    kind: str        # "wrap" | "block" | "prefix" | "value"
    opens: str       # literal prefix; longest is tried first
    closes: str | None       # None for a block mark
    arg: str | None          # regex the argument must match IN FULL
    content: str             # "marks" | "text" -- is the body scanned on?
    render: Renderer         # this mark's HTML, built here and nowhere else
    example: str             # what the cheat sheet shows, and a fixture
    explains: str            # one plain-English line, his words not ours
    value: Callable[[str, date], str | None] | None = None   # a value row's sum (PRESS-0123 §4.1)

Renderer = Callable[[Span | Photo | Quote | Value, str, PhotoSrc], str]
```

A `Renderer` receives its node, its already-rendered children, and
`photo_src`. A `Quote`'s children are its rendered paragraphs, joined by
`\n`. Only the `photo` row uses `photo_src`; only `{rainbow}`
ignores the rendered children and walks its own text itself.

**`MARKS` is the only route to a mark.** `to_html` holds no delimiter
literal and compares against no mark name at all — it calls `row.render`.
The scanner holds two literals of its own, both of which §4.5 requires: the
asterisk of a run, and the `}` that ends an argument. Carrying the HTML as a template string instead would
force `to_html` to special-case the rows a template cannot express, which
is the hidden second table this design exists to prevent. INV-6 is what
fails when it stops being so.

The rows:

| `name` | Written | Kind | Becomes |
|---|---|---|---|
| `bold` | `**word**` | wrap | `<strong>word</strong>` |
| `italic` | `*word*` | wrap | `<em>word</em>` |
| `accent` | `{accent}word{/}` | wrap | `<span style="color:var(--accent)">word</span>` |
| `muted` | `{muted}word{/}` | wrap | `<span style="color:var(--muted)">word</span>` |
| `colour` | `{#c0453a}word{/}` | wrap | `<span style="color:#c0453a">word</span>` |
| `rainbow` | `{rainbow}word{/}` | wrap | one `<span class="mk-rainbow" style="--mk-i:N">` per unit, below |
| `photo` | `{photo: seaside.jpg}`, or `{photo: seaside.jpg \| Late light}` | block | `<figure><img src="…" alt=""></figure>`; with a caption, `alt` carries it and a `<figcaption>` follows |
| `link` | `{link: https://example.org}the words{/}` | wrap | `<a href="https://example.org">the words</a>` |
| `quote` | lines beginning `>` | prefix | `<blockquote>` holding its paragraphs, below |
| `years_since` | `{years_since: 2010-01-01}` | value | the whole years since that date, as text (PRESS-0123 §4.1) |

`arg` is `^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$` on the `colour` row, the
name-and-caption grammar below on the `photo` row, the address grammar
below on the `link` row, and `None` on the rest. `content` is `"marks"` everywhere except `rainbow`, which is
`"text"`.

**A photograph's caption is its description.** Where a caption is
written it is also the `img`'s `alt`; where none is, `alt` is empty,
which declares the picture decorative. These are content images on a
public writing site, so an empty `alt` leaves a screen-reader user with
nothing where the writer had already said what the picture is. Reusing
his caption adds no step to placing a photograph. INV-10 holds it;
agreed with the user 2026-09-06.

**The name's grammar is that row's `arg`, not a separate gate**, so
`MARKS` stays the only route and a name breaking it fails the row's own
match (§4.5). Whitespace either side of the name, and either side of the
caption, is stripped first, so the written form `{photo: seaside.jpg}`
names `seaside.jpg`. What remains must be one plain file name: no `/` or
backslash anywhere, no colon, none of `< > " ? *`, no control character,
not `.` or `..`, not empty, not ending in a dot, and not a device name as
PRESS-0006 decision 10 lists and judges them. That is at least as strict as PRESS-0006's INV-11, which governs
where the original is kept; the enumeration here is the definition. Both
separators and the colon are refused on either platform, because the app
runs on both and a name is carried between them. Marks
hands the name to `photo_src`, which is the caller's file world, so this
is what defends that boundary (INV-9) — escaping the address that comes
back says nothing about the name that went in. Pinned now because
narrowing it once callers exist is a contract change.

`{rainbow}` emits an index rather than a colour, so the site's stylesheet
owns the palette and Marks owns no colour decision. **Its unit is a whole
character reference where the text carries one (§4.6's pattern), and a
single character otherwise** — split per character, an entity loses its
meaning and its own text reaches the page. `N` counts units from 0 within
one rainbow run. A unit that is a single whitespace character is emitted
bare and does not advance it; a character reference always takes a span,
`&nbsp;` included.

**A `block` mark owns its whole line.** It is a mark only when it is the
entire line, leading and trailing spaces ignored; with any other text
beside it, it stays literal. §4.3 gives it
a place in the document and §4.4 the step that puts it there — without
both, `<figure>` lands inside `<p>`, every parser closes the paragraph at
it, and the preview and the built page style the same entry differently.

**A link's address is one absolute `http` or `https` address**, matched
by the `link` row's `arg` in full once the whitespace either side is
stripped: the scheme, then no whitespace, quote, angle bracket, brace or
backslash. That refuses `javascript:` and every other scheme, which is
what defends the `href` (INV-11); §4.6's attribute rule then escapes it.
It cannot contain `}`, because the argument ends at the first one (§4.5).

**A `prefix` mark owns every line that begins with it.** The `quote`
row's `opens` is `>`: a line whose first character other than whitespace
is `>` belongs to a quotation, and a run of such lines is one `Quote`
(§4.4 step 4). The whitespace before the `>`, the `>`, and one space after
it where there is one are removed before the line is scanned, so its words
keep their wrap marks. A block mark inside a quotation stays literal. **No
line can begin with a literal `>`**: there is no escape character (§3
decision 3). The archive's raw-text entries hold no such line, which §7's
run asserts; a converted entry is PRESS-0007's to check (its INV-5).

### 4.3 The structure

```python
@dataclass(frozen=True)
class Text:      value: str
@dataclass(frozen=True)
class Span:      mark: str; arg: str | None; children: tuple[Node, ...]
@dataclass(frozen=True)
class Photo:     mark: str; name: str; caption: str | None
@dataclass(frozen=True)
class Line:      children: tuple[Node, ...]
@dataclass(frozen=True)
class Paragraph: lines: tuple[Line, ...]
@dataclass(frozen=True)
class Quote:     mark: str; paragraphs: tuple[Paragraph, ...]

Node     = Text | Span | Photo | Value   # Value: PRESS-0123 §4.1
Block    = Paragraph | Photo | Quote
Document = tuple[Block, ...]
```

`Quote` carries `mark` for the reason `Photo` does, and holds `Paragraph`s
so INV-1 reaches inside a quotation unchanged.

`Line` exists as its own level rather than as a `<br>` in a node list
because that is what makes INV-1 structural: a document cannot represent a
lost line break, so no rendering bug can collapse a poem.

`Photo` appears in both unions on purpose — as a `Block` when it owns its
line, which is the only way it is ever produced today. It carries `mark`
alongside `name` so every node says which row made it; `name` is the file
name, stripped (§4.2), and §4.1 says what a caller may be handed.

### 4.4 Splitting the body

1. Normalise `\r\n` and `\r` to `\n`.
2. Strip the whole body.
3. A run of blank lines ends a paragraph, where **blank means empty or
   whitespace-only** — `wpautop()` splits on `\n\s*\n`.
4. A line that is entirely one `block` mark ends the current paragraph and
   becomes its own `Block` after it. **A run of consecutive lines each
   beginning with a `prefix` mark does the same, as one `Quote`**: from
   each line the whitespace before the prefix, the prefix, and one space
   after it where there is one are removed; a line left empty separates
   the quote's paragraphs, and each of those is split into lines as below.
5. Strip each paragraph, and drop it if nothing is left.
6. Every remaining newline is a `Line` boundary.

Rendering: `<p>` per paragraph, `<br>\n` between lines, a `block` node
rendered as a sibling of the `<p>` elements, blocks joined by `\n`. A
`Quote` is `<blockquote>` holding its paragraphs, each rendered the same
way and joined by `\n`.

**Steps 2, 3 and 5 discard whitespace deliberately, because `wpautop()`
does.** Leave them out and INV-5 fails on the first entry with a leading
newline, looking like a broken test rather than a wrong spec.

### 4.5 Scanning one line

Left to right. At each position, try each `MARKS` row's `opens`, longest
first, so `**` is tried before `*`. **A row's opening construct is its
`opens`, plus the argument and its `}` where the row has one.** A row
matches only when **all** of:

- for a `wrap`, the opening construct is not immediately followed by
  whitespace, and for `**` and `*` not by another `*` — so in `***x***` no
  mark opens at the run's first asterisk. It does not follow that `***…***` opens nothing:
  scanning resumes one character on, and the run's later asterisks are tried
  in turn, so `***x***` renders `*<strong>x</strong>*`. What the clause
  decides is where the boundary falls, not whether a mark forms at all —
  `**x*` is `*<em>x</em>` with it and `<em>*x</em>` without;
- for a `wrap`, its `closes` occurs later **on the same line**, not
  immediately preceded by whitespace, and for `**` and `*` not by another
  `*` — so `*x **` closes nothing. Not `b**bs`, which closes nothing for
  want of an opener: `*a b**bs` is `<em>a b</em>*bs`;
- `arg`, where the row has one, matches the argument **in full**. **The
  argument runs from the end of `opens` to the next `}` on the line**, which
  is why an argument-bearing row's `opens` stops short of one: every mark
  that takes an argument is a brace mark, so there is exactly one terminator;
- a `block` row matches only when the mark is the whole line (§4.2);
- a `prefix` row is never tried here: §4.4 step 4 matches it at the start
  of a line, before the line is scanned;
- a `value` row is tried with the `wrap` rows, and PRESS-0123 §4.1 says
  when it matches.

**Both adjacency clauses are a `wrap`'s alone**, which is what the two
`for a wrap` prefixes carry. A `block` row is matched by the whole-line
rule instead (§4.2), and that rule is the whole reason: a mark owning its
line has nothing to be adjacent to. The clauses
exist for the asterisk family, whose delimiters are characters the writing
itself is full of; a `block` mark owning its whole line cannot collide that
way and needs no such rule.

Anything that fails is emitted as literal text and scanning resumes one
character on. The inner text of a matched `wrap` is scanned by the same
rule when its `content` is `"marks"`, so marks nest; a nested `{…}` opener
increments a depth counter, and **the counter alone decides which `{/}`
closes which span** — so `{accent}{muted}word{/}{/}` nests as written.
An opener increments it. A brace the writer typed is not one: count the
character instead and an ordinary `{` swallows the real `{/}`, and the
line falls out literal with the colour silently gone. Nesting is
bounded, and past the bound the rest of the line is literal (§6) —
unbounded, the recursion raises, which §6 forbids.

**`{rainbow}` is the exception: its `content` is `"text"`.** A mark inside
it is literal. §8 records the alternative.

### 4.6 Escaping

Two different rules, and mixing them up is how an injection gets in.

**Text:** `<` → `&lt;`, `>` → `&gt;`, and `&` → `&amp;` **only where it does
not already begin a character reference** — that is, where it does not
match `&(?:[A-Za-z][A-Za-z0-9]{0,30};|#[0-9]{1,7};|#[xX][0-9A-Fa-f]{1,6};)`.
The archive's existing entities are left untouched; §7's run prints what
it found rather than this prose carrying a figure that ages.

**This is where the text rule departs from `wpautop()`**, which escapes
no `&` at all. INV-5 owns that departure and checks it.

**Attribute values** — a photo's `src`, whatever `photo_src` returned, a
caption used as `alt`, and a colour's `style` value: strict, `&`, `<`,
`>`, `"` and `'` all escaped
unconditionally. Neither a returned name nor a caption carrying a quote
can break out of the tag. So a caption is escaped once per destination
and by a different rule each time: the text rule for `<figcaption>`, this
one for `alt`.

## 5. Invariants

- **INV-1** — Every single newline in a paragraph produces exactly one
  `<br>`; no input collapses two lines into one.
  *Test:* `tests/test_marks.py::test_every_newline_survives`.
  *Breaks when:* a paragraph rule joins lines, or `Line` is flattened out
  of the structure.

- **INV-2** — A delimiter that does not form a complete mark on its own
  line is rendered as literal text, byte for byte.
  *Test:* `tests/test_marks.py::test_censored_words_and_divider_are_literal`,
  whose fixtures are the archive's own `b**bs`, `f*cking` and the 35-asterisk
  line.
  *Breaks when:* the opener test drops its "not followed by whitespace or
  its own delimiter" clause, or the closer is allowed to be missing.
  **The archive's own fixtures do not separate the adjacency clauses**,
  measured by mutation 2026-08-25: drop either one and `b**bs`, `f*cking`
  and the asterisk divider all still render literally, because each is
  carried by the other clause or by having no partner at all. **Each clause
  has two independent halves — a space half and an asterisk half — so there
  are four routes**, and the test now carries one fixture apiece: `* a*`
  and `*a *` for the space halves, `*x **` for the closer's asterisk half,
  and `**x*` for the opener's. The first three are literal as written; the
  fourth is `*<em>x</em>`, because that clause decides where the boundary
  falls rather than whether a mark forms, so a fixture asserting only that
  no tag appeared cannot see it. All five mutations are killed and a
  control mutation survives.

- **INV-3** — No mark spans a newline: no `Text` inside a `Span` contains
  `\n`, and a mark's opener and closer come from the same `Line`.
  *Test:* `tests/test_marks.py::test_no_mark_spans_a_newline`.
  *Breaks when:* scanning runs over the whole body instead of per line —
  which is how a lone asterisk pairs with one three stanzas down. Do not
  restate this as *a `Span` never contains a `Line`*: `Node` excludes
  `Line`, so nothing could fail it.

- **INV-4** — In text, `<` and `>` are always escaped and `&` is escaped
  only where it does not already begin a character reference. In an
  attribute value, all five of `& < > " '` are escaped unconditionally.
  *Test:* `tests/test_marks.py::test_escaping_text_and_attributes`.
  *Breaks when:* one escape helper is used for both contexts.

- **INV-5** — For every raw-text entry in the archive, `render()` produces
  output byte-identical to today's `tools/build_blog.py::wpautop()` —
  **and the two functions are separable, so the test proves the reason
  rather than relying on the result.** Exactly two inputs tell them
  apart: an `&` that begins no character reference by §4.6's pattern,
  which Marks escapes and `wpautop()` does not, and
  text forming a complete mark, which Marks renders and `wpautop()`
  leaves alone — among it, since the quote mark (§3 decision 4), a line
  whose first character other than whitespace is `>`. The archive
  contains neither. The test asserts that
  emptiness directly and names which set stopped being empty, because an
  agreement nothing enforces breaks silently on the next import.
  *Test:* `tests/test_marks_archive.py::test_matches_wpautop`. Neither the
  export nor the oracle is part of this repository, so nothing checked out
  from it can run this — but **only absence skips**. `PRESSLESS_ARCHIVE`
  unset, or no generator found at all, is the expected state everywhere but
  the maintainer's machine and skips cleanly. Either one present and
  unusable — a path that names no file, an oracle that will not load, a
  renamed export, an ambiguous discovery — **fails**, naming the cause. A
  silent skip there would take the proof of S2 off the one machine that can
  run it, which is what a skip reporting every cause as absence did.
  *Breaks when:* any escaping or paragraph rule changes. A non-empty
  divergence set is **not** a fault in Marks — it is new source material
  the migration has never seen, and it is a decision, not a bug. It is
  the proof of S2 rather than a claim about it.

- **INV-6** — Every row in `MARKS` parses: its `example` yields a structure
  whose `mark` field is that row's `name`; and **`to_html` compares against
  no mark name at all** — walking the module's AST, it holds no delimiter
  literal and no branch on a mark name, because it calls `row.render`.
  *Test:* `tests/test_marks.py::test_every_table_row_parses` and
  `::test_no_mark_outside_the_table`.
  *Breaks when:* a mark is added to the scanner without a row, which is
  exactly what would leave the cheat sheet teaching something that does not
  work.

- **INV-7** — `src/pressless/marks.py` reaches no disk and no network. It
  imports **only** modules that can reach neither, and no other `pressless`
  module, **and calls nothing that opens a file or loads code**: `open`
  needs no import, so an import rule alone cannot catch the breach named
  below, and neither `builtins.open` nor `__import__` is spelled `open`.
  The permitted modules are enumerated in the test rather than here. This
  clause listed forbidden ones until PRESS-0110, and a list of what may not
  be imported is only ever as long as the last person's imagination: that
  one admitted `http.client`, which is the module INV-7 exists to keep out.
  *Test:* `tests/test_marks.py::test_marks_is_pure`, which walks the
  module's AST — imports and calls — rather than grepping its text.
  *Breaks when:* marks.py imports a module outside the test's allowlist;
  calls `open`, `__import__` or `import_module` **by any spelling**, since
  those do the same thing however they are reached; calls the builtins
  `eval`, `exec` or `compile` **by bare name**, which is narrower because a
  module attribute of the same name is innocent and `re.compile` is one this
  module itself calls; or names `builtins` or `__builtins__` at all, which
  is the way round that split. What the walk does **not** see is a path built by string
  concatenation, which needs neither an import nor a call — so rule 3's
  architectural claim is wider than this invariant, and §10 records the gap.

- **INV-8** — A colour argument reaches the `style` attribute only after
  matching `^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$` **in full**; a named
  colour reaches it only as one of the two fixed `var(--…)` strings. **The
  full match is the invariant, not the anchors** — the pattern is compared
  with `re.fullmatch`, so stripping `^` and `$` still refuses
  `#c0453a;background:url(…)` (executed). What admits that payload is
  comparing with `re.search` and a pattern that is not anchored; §4.2's
  `arg` column states the rule the implementer must keep.
  *Test:* `tests/test_marks.py::test_colour_argument_cannot_carry_css`.
  *Breaks when:* the argument is passed through for CSS to validate.

- **INV-9** — A photograph's name reaches `photo_src` only after matching
  §4.2's grammar in full.
  *Test:* `tests/test_marks.py::test_photo_name_cannot_escape_its_folder`
  — its refused names include `a?.jpg`, `a*.jpg`, `dot.jpg.`, `nul .jpg`,
  `nul.tar.gz`, `COM1.jpg`, `com¹.jpg` and `conin$.jpg`, and it accepts
  `com0.jpg`.
  *Breaks when:* the argument split is taken for the whole grammar, which
  is how `../../etc/passwd` reaches the caller's file world.

- **INV-10** — A photograph's `alt` is its caption where one was written,
  and empty where none was.
  *Test:*
  `tests/test_marks.py::test_a_caption_becomes_the_photograph_description`.
  *Breaks when:* `alt` is a fixed empty string, which declares every
  photograph decorative whatever the writer captioned it.

- **INV-11** — A link's address reaches `href` only after matching §4.2's
  address grammar in full, and only escaped by §4.6's attribute rule.
  *Test:* `tests/test_marks.py::test_a_link_address_cannot_carry_a_script`
  — `{link: javascript:alert(1)}x{/}` and an address carrying a `"` stay
  literal; `{link: https://example.org/a?b=1&c=2}x{/}` renders an `href`
  whose `&` is `&amp;`.
  *Breaks when:* the grammar is searched rather than matched in full, it
  admits any scheme, or the address is inserted unescaped.

- **INV-12** — A quotation keeps its lines: consecutive `>` lines are one
  `<blockquote>`, every newline inside one of its paragraphs produces one
  `<br>` as INV-1 requires, the prefix never reaches the page, and a blank
  line ends it.
  *Test:* `tests/test_marks.py::test_a_quote_keeps_its_lines`.
  *Breaks when:* a quotation's lines are joined, the `>` is left in the
  text, or the quotation runs on past a blank line.

**Trust boundary.** An entry body is writer-supplied text rendered into
HTML that is then published, and it leaves Marks by two routes. The HTML
is defended by INV-4, INV-8 and INV-11, with no other sanitiser downstream: the
Builder writes what Marks returns and the Publisher uploads what the
Builder wrote. The photograph's name is defended by INV-9, because it
leaves through `photo_src` before any escaping runs.

## 6. Failure modes

| When | What happens |
|---|---|
| An unclosed mark | Literal text (INV-2). Nothing raises; the writer sees his own characters and can see the mistake in the preview. |
| An unknown mark name — `{sparkle}x{/}` | Literal text. It is not an error: preserving what we do not understand is ADR-0001's promise about twelve years of writing. |
| A malformed colour — `{#xyz}` | Literal text (INV-8). |
| A photo mark sharing its line with other text | Literal text — it is a `block` mark (§4.2), so it is only a mark when it owns the line. He sees his own characters in the preview and can move it. |
| A photograph name outside §4.2's grammar — `{photo: ../x.jpg}` | Literal text (INV-9). He sees his own characters in the preview. |
| `photo_src` raises | Marks does not catch it. The caller owns the file world and owns the failure; the Face turns it into a sentence (`docs/design.md` § Errors). |
| `photo_src` returns a name for a picture that does not exist | A broken image on the page. Marks cannot tell — it has no disk. PRESS-0016 owns checking. |
| An empty body | An empty document, and `render()` returns `""`. Two archive entries are empty. |
| Nesting past the parser's bound | The rest of the line is literal (§4.5). Nothing raises. |
| A link address outside §4.2's grammar — `{link: javascript:x}y{/}` | Literal text (INV-11). He sees his own characters in the preview. |
| A line he meant to begin with a literal `>` | A quotation. There is no escape character (§3 decision 3); the archive's raw-text entries hold no such line, and PRESS-0007 checks the converted ones. |
| A block mark inside a quotation | Literal text: a quotation's lines hold wrap marks only (§4.2). |

## 7. Tests

`tests/test_marks.py` — pure, no fixtures on disk, runs in CI. It carries
the tests §5 names for INV-1, INV-2, INV-3, INV-4, INV-6, INV-7, INV-8,
INV-9, INV-10, INV-11 and INV-12.

`tests/test_marks_archive.py` — the INV-5 conformance run over the real
export. The export is personal data and cannot live in a public repository
(`docs/design.md` § Where everything sits on disk), and the oracle belongs
to today's generator rather than to this project — so it skips where
**either** is absent, and **fails rather than skipping** where either is
present and unusable (INV-5 states the two outcomes). `PRESSLESS_GENERATOR`
pins which generator is read when more than one could be found. **It prints
the population it read, the raw-text count it compared and each divergence
count**, so those numbers are an output of the run rather than a
transcription in prose that ages. **It also asserts INV-5's two
divergence sets are empty before comparing anything**, so a byte mismatch
and a changed archive are told apart by the run and not by whoever reads
the failure. What it cannot print is anything about
the current built site, which is not its input.

Each test is to be seen failing before the code exists — `testing.md` §1,
and `write-test` performs that run.

## 8. Alternatives considered (and rejected)

| Rejected | Why |
|---|---|
| **Markdown** | ADR-0001. Its central rule collapses single newlines, and the line break is the content. |
| **A backslash escape (`\*`)** | New syntax that itself needs escaping, on an archive with two measured collisions that "unclosed is literal" already covers. Cost now, for a case nobody has hit. |
| **Marks resolving a photo's path** | Breaks rule 3 and makes the part untestable without a disk. The `photo_src` callable costs one argument. |
| **Named colours as hex** | Freezes today's palette into every future page. |
| **`{rainbow}` parsing marks inside itself** | A character counter threaded through nested rendering, for bold-inside-rainbow. Text-only is the shortest correct thing; §9 keeps it open. |
| **Blanket `&` → `&amp;`** | Puts literal `&nbsp;` on 104 pages. |
| **Escaping `&` never** (today's `wpautop`) | Correct for the archive, and leaves a bare `&` in a future entry as invalid HTML. **Not a security difference** — `&lt;` matches the character-reference pattern, so both rules emit it unchanged, and an entity is never re-parsed as markup. Escaping `<` and `>` is what closes injection, and INV-4 does that unconditionally. |
| **Markdown's `[words](address)` for a link** | A second shape of mark beside the brace family, built from `[` and `(`, which his writing already uses. Every other mark taking an argument is a brace mark. |
| **`{quote}…{/}` for a quotation** | A quotation spans lines, and no mark may (INV-3). |

## 9. Out of scope

- The entry file's `Key: value` header, and preserving unknown header
  fields — the Store's, PRESS-0005.
- The web-copy naming rule for photographs — the Builder's, PRESS-0008.
- Generating the cheat sheet from `MARKS` — PRESS-0018.
- **Every entry that is not raw text** — the Gutenberg ones and the classic
  HTML ones. An empty entry is raw text and stays in INV-5's population;
  §6 gives it a row, and the conformance run's classifier excludes only the
  two shapes named here. ADR-0001 promises *"every one of the 616
  existing entries must survive a round trip"*; that promise is about the
  format and binds whatever Import writes, since a Store file is text with
  marks whatever it came from. It does not oblige Marks to parse HTML.
  PRESS-0007 converts them into marks, the link and quote marks included
  (§3 decision 4).
- An escape character, and marks nested inside `{rainbow}`. Both are
  additions this design leaves room for; neither is queued.
- The stray `<span id="selectionBoundary_…">` markup visible on 7 built
  pages. INV-5 reproduces it deliberately. Removing it is an edit to his
  writing and is his decision, not a rendering change.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_marks.py::test_every_newline_survives` |
| INV-2 | `tests/test_marks.py::test_censored_words_and_divider_are_literal` |
| INV-3 | `tests/test_marks.py::test_no_mark_spans_a_newline` |
| INV-4 | `tests/test_marks.py::test_escaping_text_and_attributes` |
| INV-5 | `tests/test_marks_archive.py::test_matches_wpautop` — **skipped in CI**, because the archive is personal data and cannot be committed and the oracle it compares against is in a private workspace. It runs on the maintainer's machine only, and a green CI run is silent about it. |
| INV-6 | `tests/test_marks.py::test_every_table_row_parses` + `::test_no_mark_outside_the_table` |
| INV-7 | `tests/test_marks.py::test_marks_is_pure` |
| INV-8 | `tests/test_marks.py::test_colour_argument_cannot_carry_css` |
| INV-9 | `tests/test_marks.py::test_photo_name_cannot_escape_its_folder` |
| INV-10 | `tests/test_marks.py::test_a_caption_becomes_the_photograph_description` |
| INV-11 | `tests/test_marks.py::test_a_link_address_cannot_carry_a_script` |
| INV-12 | `tests/test_marks.py::test_a_quote_keeps_its_lines` |
| INV-7's wider claim that no path is resolved in `marks.py` | **nothing** — `test_marks_is_pure` walks imports and call spellings, and a path built by string concatenation needs neither. Rule 3 is kept by review here, not by a test. |
| §3.1's claim that the site has one accent and one muted ink | **nothing** — a repaint of the site could add a third named colour and this spec would not notice. It is a one-line edit to `MARKS` when it happens. |
| §4.2's `mk-rainbow` class existing in the site's stylesheet | **nothing** — Marks emits the class and the stylesheet is in another repository. A rainbow run renders as plain text until PRESS-0008 adds the rule; tracked by PRESS-0008. |

## 11. Cross-doc impact

- `CHANGELOG.md` — an Added entry when it ships.
- `README.md` — the Status section stops saying there is no code.
- `CLAUDE.md` — § Stack and § Build and test were placeholders; this item
  filled them.
- `docs/design.md` — no change. This spec settles detail that document
  deliberately left open.
- PRESS-0007 — Import writes the link and quote marks for the archive's
  WordPress-HTML entries (§3 decision 4).
- PRESS-0018 — the cheat sheet gains the two rows, generated from
  `MARKS`.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0004-marks-loop-log.md`.
