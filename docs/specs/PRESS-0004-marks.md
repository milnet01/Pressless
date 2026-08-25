# PRESS-0004 — Marks: one table, one parser, one renderer

**Status:** spec draft (2026-08-25).
**Kind:** implement.
**Source:** ROADMAP PRESS-0004 (`docs/design.md` § The parts; ADR-0001).

**Blocker for:** PRESS-0008, PRESS-0012, PRESS-0016, PRESS-0018.

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

The archive is what makes the contract sharp rather than obvious. Measured
against the WordPress export (686 entries — 616 published, 62 drafts, 8
private; the 3 trashed are not carried — the *What Import brings across*
paragraph of `docs/design.md`):

1. **554 entries are raw newline text.** For these the line break *is* the
   content — ADR-0001 — so any rule that reflows a paragraph destroys the
   writing.
2. **Six entries already contain `*`**, and every one of them is
   self-censoring prose or a divider: `f*cking`, `sh*t`, `p*rn`, `b**bs`,
   and one line of 35 asterisks. Only **two raw-text lines in the whole
   archive carry a second asterisk** — `b**bs` and that divider; the rest
   are lone asterisks with no partner on their line. A naive italic rule
   run over a whole body rather than a line pairs across line breaks and
   italicises **four** published poems. (A sixth entry carries `f**cking`,
   but it is Gutenberg rather than raw text, so it reaches Marks only
   through whatever PRESS-0007 writes.)
3. **104 raw-text entries contain `&`**, always as a character reference
   (156 occurrences of `&nbsp;`, 14 of `&apos;`, 2 of `&amp;`) and **never bare** — so a
   blanket `&` → `&amp;` puts literal `&nbsp;` on 104 pages.
4. **39 raw-text entries contain `<` or `>`**, mostly stray
   `<span id="selectionBoundary_…">` left by the WordPress editor. Today's
   generator escapes them and 7 built pages show that markup as visible
   text. That is the current behaviour, and reproducing it is the contract
   — improving it is a separate decision about his writing.

Today's behaviour is `tools/build_blog.py::wpautop()` and
`tools/build_blog.py::render_body()` in the sibling workspace: blank line
starts a paragraph, single newline becomes `<br>`, `<` and `>` are escaped,
`&` is left alone. That function is what PRESS-0008 re-homes, so Marks
must be able to stand in for it exactly.

## 3. Scope decisions (agreed with the user)

Three choices below were preference rather than deduction. The rest follow
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

## 4. Design

### 4.1 The public surface

Four names, in `src/pressless/marks.py`. Nothing else is public.

```python
MARKS: tuple[Mark, ...]                       # the one table (§4.2)

def parse(body: str) -> Document              # text in, structure out
def to_html(doc: Document, photo_src: PhotoSrc) -> str
def render(body: str, photo_src: PhotoSrc) -> str   # parse + to_html
```

`PhotoSrc` is `Callable[[str], str]`: given a picture's file name it
returns the address to put in `src`. **Marks never builds a path.** The
Builder passes its web-copy naming rule (PRESS-0008 owns that rule); the
Face passes an address serving the original for preview (PRESS-0012). This
callable is how rule 3 is kept while the picture mark still works.

### 4.2 The table

```python
@dataclass(frozen=True)
class Mark:
    name: str          # "bold", "accent", "photo"
    kind: str          # "wrap" | "block"
    opens: str         # literal prefix: "**", "{accent}", "{photo: "
    arg: str | None    # regex the argument must match, or None
    closes: str | None # "**", "{/}", None for a block mark
    content: str       # "marks" | "text" -- is the body scanned further?
    renders: str       # HTML template; "{}" is the rendered content
    example: str       # what the cheat sheet shows, and a parse fixture
    explains: str      # one plain-English line, his words not ours
```

`MARKS` is the single source **and the only route to a mark**: the scanner
holds no delimiter literal of its own, and `to_html` no `name` branch of its
own — both read the rows. That is what makes it true rather than intended,
and INV-6 is what fails when it stops being so. Without `renders`, `to_html`
would carry a second, hidden table, and a new row would parse, reach the
cheat sheet, and render as nothing.

`arg` is what lets a row describe a mark whose opener is not a fixed
string: `{#…}` carries `^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$`, `{photo: }`
carries the name and optional `| caption`, and every other row carries
`None`. `content` is `"marks"` everywhere except `{rainbow}`, which is
`"text"`.

The rows:

| Written | Kind | Becomes |
|---|---|---|
| `**word**` | wrap | `<strong>word</strong>` |
| `*word*` | wrap | `<em>word</em>` |
| `{accent}word{/}` | wrap | `<span style="color:var(--accent)">word</span>` |
| `{muted}word{/}` | wrap | `<span style="color:var(--muted)">word</span>` |
| `{#c0453a}word{/}` | wrap | `<span style="color:#c0453a">word</span>` |
| `{rainbow}word{/}` | wrap | one `<span class="mk-rainbow" style="--mk-i:N">` per character |
| `{photo: seaside.jpg}` | block | `<figure><img src="…" alt=""></figure>` |
| `{photo: seaside.jpg \| Late light}` | block | the same, plus `<figcaption>` |

`{rainbow}` emits an index rather than a colour, so the site's stylesheet
owns the palette and Marks owns no colour decision. `N` counts characters
from 0 within one rainbow run; whitespace is emitted bare and does not
advance it.

**A `block` mark owns its whole line, and that is what `block` means.** A
photo mark alone on a line ends the paragraph: the `<figure>` is emitted as
a sibling of the `<p>` elements, never inside one. A photo mark with any
other text on its line is not a mark at all and stays literal. Without this
rule `<figure>` lands inside `<p>`, every HTML parser closes the paragraph
at it, and the lines after it fall outside — so the Face's preview and the
built page would style the same entry differently.

### 4.3 The structure

```python
@dataclass(frozen=True)
class Text:      value: str
@dataclass(frozen=True)
class Span:      mark: str; arg: str | None; children: tuple[Node, ...]
@dataclass(frozen=True)
class Photo:     name: str; caption: str | None
@dataclass(frozen=True)
class Line:      children: tuple[Node, ...]
@dataclass(frozen=True)
class Paragraph: lines: tuple[Line, ...]

Node     = Text | Span | Photo
Document = tuple[Paragraph, ...]
```

`Line` exists as its own level rather than as a `<br>` in a node list
because that is what makes INV-1 structural: a document cannot represent a
lost line break, so no rendering bug can collapse a poem.

### 4.4 Splitting the body

1. Normalise `\r\n` and `\r` to `\n`.
2. Strip the whole body.
3. A run of blank lines ends a paragraph, where **blank means empty or
   whitespace-only** — `wpautop()` splits on `\n\s*\n`.
4. Strip each paragraph, and drop it if nothing is left.
5. Every remaining newline is a `Line` boundary.

Rendering: `<p>` per paragraph, `<br>\n` between lines, paragraphs joined
by `\n`.

**Steps 2, 3 and 4 discard whitespace, deliberately, because `wpautop()`
does.** An indented opening line comes back unindented and a whitespace-only
paragraph disappears. Leave any of them out and INV-5 fails byte-comparison
on the first entry with a leading newline or a trailing space — and it fails
looking like a broken test rather than a wrong spec.

### 4.5 Scanning one line

Left to right. At each position, try each `MARKS` row's `opens`, longest
first, so `**` is tried before `*`. A row matches only when **all** of:

- the opener is not immediately followed by a space; and for `**` and `*`
  not by another `*` either, so `***…***` opens nothing. **A `{…}` mark has
  no such character**, so `{accent}{muted}word{/}{/}` opens legally and
  nests — which is what the depth counter below is for;
- for a `wrap`, its `closes` occurs later **on the same line**, preceded by
  a character that is neither a space nor the delimiter — `b**bs` therefore
  closes nothing;
- for `{#…}`, the argument is 3 or 6 hexadecimal digits and nothing else;
- for `{photo: …}`, a `}` occurs later on the same line **and the mark is
  the only thing on that line** (§4.2 — it is a `block` mark).

Anything that fails is emitted as literal text and scanning resumes one
character on. The inner text of a matched `wrap` is scanned by the same
rule, so marks nest; a nested `{…}` opener increments a depth counter so
the right `{/}` closes the right span.

**`{rainbow}` is the exception: its content is taken as text.** A mark
inside it is literal. §8 records the alternative.

### 4.6 Escaping

Two different rules, and mixing them up is how an injection gets in.

**Text:** `<` → `&lt;`, `>` → `&gt;`, and `&` → `&amp;` **only where it does
not already begin a character reference** — that is, where it does not
match `&(?:[A-Za-z][A-Za-z0-9]{0,30};|#[0-9]{1,7};|#[xX][0-9A-Fa-f]{1,6};)`.
Measured: this leaves all 156 `&nbsp;`, 14 `&apos;` and 2 `&amp;` in the
archive untouched, and there is no bare `&` anywhere in it to change.

**Attribute values** (a photo's `src`, whatever `photo_src` returned):
strict — `&`, `<`, `>`, `"` and `'` are all escaped unconditionally. A
caller returning a name with a quote in it cannot break out of the tag.

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
  *Breaks when:* the opener test drops its "not followed by a space or its
  own delimiter" clause, or the closer is allowed to be missing.

- **INV-3** — No mark spans a newline. A `Span` never contains a `Line`.
  *Test:* `tests/test_marks.py::test_no_mark_spans_a_newline`.
  *Breaks when:* scanning is done over the whole body instead of per line.

- **INV-4** — In text, `<` and `>` are always escaped and `&` is escaped
  only where it does not already begin a character reference. In an
  attribute value, all five of `& < > " '` are escaped unconditionally.
  *Test:* `tests/test_marks.py::test_escaping_text_and_attributes`.
  *Breaks when:* one escape helper is used for both contexts.

- **INV-5** — For every raw-text entry in the archive, `render()` produces
  output byte-identical to today's `tools/build_blog.py::wpautop()`.
  *Test:* `tests/test_marks_archive.py::test_matches_wpautop`, skipped
  unless `PRESSLESS_ARCHIVE` names a WordPress export.
  *Breaks when:* any escaping or paragraph rule changes; and it is the
  proof of S2 rather than a claim about it.

- **INV-6** — Every row in `MARKS` parses: its `example` yields a structure
  containing a node of that row's `name`; and **neither the scanner nor
  `to_html` names a mark the table does not** — walking the module's AST,
  every string literal used as a delimiter and every `name` branch is one
  `MARKS` supplies.
  *Test:* `tests/test_marks.py::test_every_table_row_parses` and
  `::test_no_mark_outside_the_table`.
  *Breaks when:* a mark is added to the scanner without a row, which is
  exactly what would leave the cheat sheet teaching something that does not
  work.

- **INV-7** — `src/pressless/marks.py` imports nothing that reaches a disk
  or a network: not `pathlib`, `os`, `io`, `open`, `socket`, `urllib`,
  `requests`, `subprocess`, nor any other `pressless` module.
  *Test:* `tests/test_marks.py::test_marks_is_pure`, which walks the
  module's AST rather than grepping its text.
  *Breaks when:* someone resolves a photo's path here instead of in the
  caller — the one change rule 3 exists to stop.

- **INV-8** — A colour argument reaches the `style` attribute only after
  matching `#[0-9A-Fa-f]{3}` or `#[0-9A-Fa-f]{6}`; a named colour reaches
  it only as one of the two fixed `var(--…)` strings.
  *Test:* `tests/test_marks.py::test_colour_argument_cannot_carry_css`.
  *Breaks when:* the argument is passed through for CSS to validate.

**Trust boundary.** An entry body is writer-supplied text rendered into
HTML that is then published. INV-4 and INV-8 are that boundary's whole
defence, and there is no other sanitiser downstream: the Builder writes
what Marks returns and the Publisher uploads what the Builder wrote.

## 6. Failure modes

| When | What happens |
|---|---|
| An unclosed mark | Literal text (INV-2). Nothing raises; the writer sees his own characters and can see the mistake in the preview. |
| An unknown mark name — `{sparkle}x{/}` | Literal text. It is not an error: preserving what we do not understand is ADR-0001's promise about twelve years of writing. |
| A malformed colour — `{#xyz}` | Literal text (INV-8). |
| A photo mark sharing its line with other text | Literal text — it is a `block` mark (§4.2), so it is only a mark when it owns the line. He sees his own characters in the preview and can move it. |
| `photo_src` raises | Marks does not catch it. The caller owns the file world and owns the failure; the Face turns it into a sentence (`docs/design.md` § Errors). |
| `photo_src` returns a name for a picture that does not exist | A broken image on the page. Marks cannot tell — it has no disk. PRESS-0016 owns checking. |
| An empty body | An empty document, and `render()` returns `""`. Two archive entries are empty. |

## 7. Tests

`tests/test_marks.py` — pure, no fixtures on disk, runs in CI. It carries
the invariant tests named in §5.

`tests/test_marks_archive.py` — the INV-5 conformance run over the real
export. It is skipped unless `PRESSLESS_ARCHIVE` points at a WXR file,
because that file is personal data and cannot live in a public repository
(`docs/design.md` § Where everything sits on disk). It prints **every §2
figure derived from the export**, so those are an output rather than a
transcription. §2's count of built pages carrying `selectionBoundary` is
not among them: it measures the current built site, not the export, and
stays a dated measurement.

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

## 9. Out of scope

- The entry file's `Key: value` header, and preserving unknown header
  fields — the Store's, PRESS-0005.
- The web-copy naming rule for photographs — the Builder's, PRESS-0008.
- Generating the cheat sheet from `MARKS` — PRESS-0018.
- **The 130 entries that are not raw text**, and with them the difference
  between INV-5's 554 and ADR-0001's *"every one of the 616 existing
  entries must survive a round trip"*. That promise is about the format,
  and it binds whatever Import writes: once those entries are Store files
  they are text with marks like any other, and INV-5's rule applies to them
  in full. What it does not do is oblige Marks to parse HTML. Deciding what
  Import writes for them is PRESS-0007's, and until it decides, no
  round-trip over them can be tested here.
- What Import writes for the 67 Gutenberg and 63 classic-HTML entries —
  PRESS-0007. Marks renders text with marks; those entries are HTML, and
  which of the two they become is Import's call to make once.
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
| INV-5 | `tests/test_marks_archive.py::test_matches_wpautop` — **skipped in CI**, because the archive is personal data and cannot be committed. It runs on the maintainer's machine only, and a green CI run is silent about it. |
| INV-6 | `tests/test_marks.py::test_every_table_row_parses` + `::test_no_mark_outside_the_table` |
| INV-7 | `tests/test_marks.py::test_marks_is_pure` |
| INV-8 | `tests/test_marks.py::test_colour_argument_cannot_carry_css` |
| §3.1's claim that the site has one accent and one muted ink | **nothing** — a repaint of the site could add a third named colour and this spec would not notice. It is a one-line edit to `MARKS` when it happens. |
| §4.2's `mk-rainbow` class existing in the site's stylesheet | **nothing** — Marks emits the class and the stylesheet is in another repository. A rainbow run renders as plain text until PRESS-0008 adds the rule; tracked by PRESS-0008. |

## 11. Cross-doc impact

- `CHANGELOG.md` — an Added entry when it ships.
- `README.md` — the Status section stops saying there is no code.
- `CLAUDE.md` — § Stack and § Build and test are both placeholders today;
  this is the item that fills them.
- `docs/design.md` — no change. This spec settles detail that document
  deliberately left open.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-25 | 3, cold — genre pinned `spec`; packet carried ADR-0001 whole, windows on the design's dependency rules and photograph/cheat-sheet paragraphs, the live site generator's rendering path, the site's colour tokens, and every archive figure re-measured by command. No unrunnable region: the export and the current generator are both on disk, so Q1 was fully in scope. | 1 | 3 | 3 | 2 | **Nine verified, nine fixed, none dismissed.** All three lanes read the document in full and **all three independently found the same defect**, which is the strongest signal in the run: §4.4 said normalising line endings changed nothing else, while the generator it claims byte-identity with strips the body, strips each paragraph, drops empty ones and treats a whitespace-only line as blank. An implementer following §4.4 would have failed INV-5 on the first entry with a leading newline, and the failure would have read as a broken test rather than a wrong spec. **All three also found `{photo:}` undefined**: the table called it `standalone` and nothing said what that meant structurally, while §4.3 made it a node inside a line inside a paragraph — so `<figure>` lands inside `<p>`, every parser closes the paragraph at it, and the preview and the built page style the same entry differently. `standalone` is now `block`, defined as owning its whole line. **And all three found INV-6's second clause unfalsifiable** — if the scanner dispatches from the table, *no mark the parser recognises is absent from it* is true by construction, so the one breach INV-6 exists to catch would have shipped undetected; it now pins an AST check that no delimiter literal or `name` branch exists outside `MARKS`. **Two lanes found the table could not express its own rows**: `opens` was a fixed string, so `{#…}` had no representation, and no field carried the *Becomes* column, meaning `to_html` would hold a second hidden table and a new row would parse, reach the cheat sheet and render as nothing. `Mark` gained `arg`, `content` and `renders`. **The one Q1 was my own count**: §2 claimed a naive italic rule italicises five published poems, and measurement says four — one entry carries a single lone asterisk that cannot pair — and `f**cking` was listed among raw-text collisions when it is in a Gutenberg entry. **One lane filed, and a second raised as an open question, that §8's security rationale was false**: leaving `&` unescaped was said to let `&lt;` inject markup. Executed with a real HTML parser — `&lt;script&gt;` parses as text, never as an element, and both `&` rules emit `&lt;` unchanged. The row now reads as a validity difference, which is what it is; escaping `<` and `>` is what closes injection. **Two more from one lane each:** *its own delimiter character* was defined only by the asterisk example, so a builder could read `{` as the delimiter and refuse to nest brace marks, contradicting the depth counter four lines below; and ADR-0001 promises all 616 entries round-trip while INV-5 covers 554, now reconciled as a promise about the format that binds whatever Import writes. **Three collateral fixes, all mine, caught by the sweep rather than a lane**: adding a second test to INV-6 stranded §7's *seven invariant tests* and §10's INV-6 row, and the new `block` rule created a failure mode §6 did not list. **Three lane open questions resolved clean and are not counted** — the design's disk section exists and does carry the personal-data rule, `CLAUDE.md`'s Stack and Build-and-test are both placeholders, and the missing `mk-rainbow` rule is the Builder's. Every claim a fix added was executed, including the refuting cases: the colour regex rejects `#c0453a;color:red`, which is the CSS injection INV-8 exists for. |
