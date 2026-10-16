<!-- ants-spec-format: 1 -->
# PRESS-0227 — The site's icon and its sharing picture

**Status:** spec draft (2026-10-16).
**Kind:** feature.
**Source:** ROADMAP PRESS-0227 (split from PRESS-0213 by the user's
decision of 2026-10-03).

**Blocked by:** PRESS-0197 (shipped).
**Amends:** PRESS-0213 (§ 4.1 the identity file, § 4.6 the Settings
page), PRESS-0008 (§ 4.1 `ROOT_OUTPUT`). § 11 lists each edit.

Layman: they pick a picture for the little icon in the browser tab, and
a picture that shows when someone shares a link to the site.

## 1. Goal

After this ships, the Settings page chooses two pictures: the site's
icon and its sharing picture. Each is a photograph, uploaded there as a
picture section uploads one. A publish gives every page of the site an
icon link and a sharing-picture tag. With neither chosen, the Builder
inserts nothing.

## 2. Problem

1. **A built page has no icon.** `_Build.page`'s head holds charset,
   viewport, title, description and stylesheet links, and nothing in
   `builder.py` or `starter.py` writes `rel="icon"`. The browser tab shows
   its blank default.
2. **A shared link shows no picture.** No `og:image` tag is written
   anywhere, so a social site picks one of its own or none.
3. **The identity file holds text only.** `store.Identity` carries `name`
   and `description`; PRESS-0213 § 9 left the two pictures for this item.

## 3. Scope decisions (agreed with the user)

1. **The two pictures belong with the identity** — user, 2026-10-03,
   splitting PRESS-0213.
2. **Both are photographs, kept where photographs are kept.** The
   identity file names them; it does not hold their bytes. Recommended by
   Claude, 2026-10-16: the upload, the naming rule (`photographs.keep`)
   and the format check (`builder.photograph_format`) already exist, and
   photographs are never removed, so a name undo restores always
   resolves.
3. **Settings only, not the setup wizard's *site* step.** Recommended by
   Claude, 2026-10-16: both are optional, and the wizard stays short.
   PRESS-0212 § 9 had planned them for that step.
4. **A page that already carries its own icon or sharing tag keeps it.**
   Recommended by Claude, 2026-10-16: an imported fixed page may hold
   either, and two icon links make the browser's choice arbitrary.
   `_Build.counted` already skips a page holding its own Google tag.

## 4. Design

### 4.1 The identity file (amends PRESS-0213 § 4.1)

```python
# src/pressless/store.py
@dataclass(frozen=True)
class Identity:
    name: str
    description: str = ""
    icon: str = ""       # PRESS-0227: a photograph's name, or ""
    picture: str = ""    # PRESS-0227: a photograph's name, or ""
```

- `read_identity` reads `"icon"` and `"picture"` as `"description"` is
  read: absent is `""`, a value that is not a string raises `StoreError`.
- `identity_problem` returns `"icon"` or `"picture"` where that field is
  not `""` and `photograph_path_for` refuses it, or it begins with `.`
  (`_Build.web_copy` refuses such a name).
- `write_identity` writes `"icon"` and `"picture"` only when not `""`. An
  identity with neither writes the bytes it writes today.
- An older Pressless reading the wider file ignores the two keys
  (PRESS-0213 § 4.1: "Other keys are ignored").

### 4.2 The Settings page (amends PRESS-0213 § 4.6)

`setup._form` gains, after the description, a *Site icon* row and a
*Sharing picture* row. Each holds:

- a hidden input, `site_icon` or `site_picture`, holding the chosen name;
- the chosen picture, shown through `editor.photo_src`, when there is one;
- a file input with `accept` set to `photographs.ACCEPT`, which sends the
  file to `POST /photograph?name=…` as the page editor's panel does, then
  sets the hidden input to the answered `name` and shows the picture;
- a *Remove* button that empties the hidden input and hides the picture.

A refused upload shows the answer's sentence beside the row and leaves
the hidden input as it was. `_FIELDS` gains `site_icon` and
`site_picture`; `_IDENTITY_FIELDS` maps `icon` and `picture` to them;
`setup._identity` builds all four fields; `_values_from` reads them from
`read_identity`. Each row has help beside it (`_HELP_PARAGRAPHS`).

The wizard's `check_site` keeps the Store's `icon` and `picture`, through
`dataclasses.replace` on the identity `read_identity` returns, so a
first run over a carried folder does not drop them.

### 4.3 The Builder (amends PRESS-0008 § 4.1)

`ROOT_OUTPUT` gains `"site-icon.png"`. On a publishing build
(`photo_src is None`):

- **Icon chosen.** `_Build.icon_copy(name)` opens the photograph as
  `web_copy` does, with the same `BuildStopped` sentences for a missing or
  unreadable one. It writes `site-icon.png`: the first frame,
  `ImageOps.exif_transpose`, then `ImageOps.fit` to `ICON_SIDE = 180`
  pixels square, centred, saved as PNG.
- **Picture chosen.** `web_copy(name)` publishes it as any photograph.

`_Build.identified(text, depth)` returns `text` with these inserted by
`_inserted`, beside `counted` in `page` and `fixed_page`:

```html
<link rel="icon" type="image/png" href="{up}site-icon.png">
<link rel="apple-touch-icon" href="{up}site-icon.png">
<meta property="og:image" content="{address}/{web_photograph(picture)}">
<meta name="twitter:card" content="summary_large_image">
```

`up` is `"../" * depth`. `address` is `settings.site_address` with its
trailing `/` removed; `og:image` needs an absolute address. The two icon
lines are left out where no icon is chosen, or where the text already
matches `_OWN_ICON`, a `<link` whose `rel` holds the word `icon`, any
case. The two picture lines are left out where no picture is chosen, or
where the text already holds `og:image`. A preview build inserts neither.

### 4.4 A repository's own `site-icon.png`

PRESS-0197 § 4.7's two rules cover it unchanged, since both read
`ROOT_OUTPUT` at call time: a new setup no longer keeps a root
`site-icon.png`, and a saved list that still keeps one makes a publish
with an icon chosen raise `KeptFolderBuilt`.

## 5. Invariants

- **INV-1** — `read_identity` returns `Identity("A", "", "a.png", "")` for
  `{"name": "A", "icon": "a.png"}`, and raises for `{"name": "A",
  "picture": 1}`. `identity_problem` returns `"icon"` for `icon=".a.png"`
  and `icon="a/b.png"`, and `"picture"` for `picture="con.png"`.
  *Test:* `tests/test_store_extras.py::test_the_identity_names_its_pictures`.
  *Breaks when:* a refused name is accepted, or a non-string is read.
- **INV-2** — `write_identity(folder, Identity("A", "B"))` writes exactly
  `{\n  "description": "B",\n  "name": "A"\n}\n`; with `icon="a.png"` the
  file holds `"icon"` and no `"picture"`. *Test:*
  `tests/test_store_extras.py::test_an_identity_without_pictures_is_written_as_before`.
  *Breaks when:* empty keys are written, or the key order changes.
- **INV-3** — With an icon chosen, the built site holds `site-icon.png`,
  a 180 by 180 PNG made from a 300 by 200 photograph; an entry page at
  depth 2 links `../../site-icon.png` as `icon` and `apple-touch-icon`,
  and `index.html` links `site-icon.png`. *Test:*
  `tests/test_builder.py::test_the_icon_is_square_and_on_every_page`.
  *Breaks when:* the icon is not square, a page lacks the link, or `up`
  is wrong.
- **INV-4** — With a picture chosen and `site_address`
  `https://example.org/`, every page holds `<meta property="og:image"
  content="https://example.org/photographs/<name>">` and the
  `twitter:card` tag, and the site holds `photographs/<name>`. *Test:*
  `tests/test_builder.py::test_the_sharing_picture_is_absolute_on_every_page`.
  *Breaks when:* the address is relative, doubled at the `/`, or a page
  lacks the tag.
- **INV-5** — A fixed page whose head holds `<LINK REL="shortcut icon"
  href="x.ico">` and an `og:image` of its own is built with neither
  inserted, and keeps its own. *Test:*
  `tests/test_builder.py::test_a_page_keeps_its_own_icon_and_picture`.
  *Breaks when:* a second icon link or `og:image` is inserted, or the
  match is case-sensitive.
- **INV-6** — With neither chosen, `_Build.identified` returns its text
  unchanged, no page of a built starter site holds `rel="icon"`,
  `og:image` or `twitter:card`, and no `site-icon.png` is written. A
  preview build with both chosen inserts neither. *Test:*
  `tests/test_builder.py::test_no_pictures_change_nothing`.
  *Breaks when:* any line is inserted with nothing chosen, or a preview
  carries one.
- **INV-7** — An icon naming a photograph that is not there stops the
  build with `the photograph <name> is not in the photographs folder`.
  *Test:* `tests/test_builder.py::test_a_missing_icon_stops_the_build`.
  *Breaks when:* the build goes on without the icon.
- **INV-8** — Saving Settings with `site_icon=a.png` writes an identity
  with `icon="a.png"`, keeping the name and description; saving with
  `site_icon=` empties it; `site_icon=.a.png` gets the row's hint and
  writes neither the identity nor settings. A first run's *site* step over
  a Store whose identity names an icon keeps it. *Test:*
  `tests/test_setup.py::test_settings_choose_the_icon_and_picture`.
  *Breaks when:* a save drops a picture, keeps a removed one, or writes on
  a refused name.
- **INV-9** — On the Settings page, choosing a picture file uploads it,
  shows it and fills the hidden input; *Remove* empties it. *Test:* a row
  in `scripts/by-hand-browser-checks.py`.
  *Breaks when:* the upload's answer is not read into the input.

The upload reuses `POST /photograph`, behind the Face's boundary, and the
Face serves nothing new. `face.FILES_POLICY` and the preview frame's
sandbox are unchanged.

## 6. Failure modes

- **A picture Pillow cannot decode** is refused at upload by
  `photographs.add`, whose sentence the row shows.
- **A photograph removed by hand** after it was chosen stops the next
  publish (INV-7), naming it. Choosing another or *Remove* clears it.
- **Undo** restores `identity.json` (PRESS-0213 § 4.5), so a restored
  identity may name an earlier picture. Photographs are never removed by
  Pressless, so that name resolves.
- **A site served below a path**, such as `owner.github.io/blog/`, keeps
  that path in `site_address`, so `og:image` carries it.
- **A social site's cache** may show an old picture for a while after a
  change. Pressless cannot clear it.

## 7. Tests

`tests/test_store_extras.py` gains INV-1 and INV-2; `tests/test_builder.py`
INV-3, INV-4, INV-5, INV-6 and INV-7; `tests/test_setup.py` INV-8;
`scripts/by-hand-browser-checks.py` INV-9. The new Settings words join
`tests/test_words.py` through the Settings page it already reads.
Fixtures are pictures Pillow draws in the test, never real media. Each
test is seen failing against the code before this item, then
mutation-probed once it lands.

## 8. Alternatives considered (and rejected)

- **Keeping the pictures' bytes in `identity/`.** Rejected: a second
  upload path, a second naming rule and a second format check, for files
  `photographs.keep` already places.
- **`favicon.ico` at the root.** Rejected: an ICO writer is a new format
  to get right, every current browser takes a PNG icon, and a
  repository's own `favicon.ico` is a common kept root entry.
- **One fixed name inside `photographs/`.** Rejected: any name there can
  be a photograph's, and a collision overwrites one.
- **Cropping the sharing picture to 1200 by 630.** Rejected: a crop can
  cut the subject out, and social sites crop to their own shapes anyway.
- **Writing `og:title` and `og:description` too.** Rejected: social
  sites fall back to the page's `<title>` and description, which every
  generated page already has.

## 9. Out of scope

- Choosing the two pictures in the setup wizard — deferred; not yet
  queued (§ 3 decision 3).
- A sharing picture per page — deferred; not yet queued.
- Filling the identity into a fixed page's head beyond these tags —
  PRESS-0213 § 9.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_store_extras.py::test_the_identity_names_its_pictures` |
| INV-2 | `tests/test_store_extras.py::test_an_identity_without_pictures_is_written_as_before` |
| INV-3 | `tests/test_builder.py::test_the_icon_is_square_and_on_every_page` |
| INV-4 | `tests/test_builder.py::test_the_sharing_picture_is_absolute_on_every_page` |
| INV-5 | `tests/test_builder.py::test_a_page_keeps_its_own_icon_and_picture` |
| INV-6 | `tests/test_builder.py::test_no_pictures_change_nothing` |
| INV-7 | `tests/test_builder.py::test_a_missing_icon_stops_the_build` |
| INV-8 | `tests/test_setup.py::test_settings_choose_the_icon_and_picture` |
| INV-9 | `scripts/by-hand-browser-checks.py`, run by hand in Chrome; Firefox and Edge by hand |
| § 4.2 the rows' words | `tests/test_words.py` |
| § 6 a social site's cache | **nothing** — outside Pressless |

## 11. Cross-doc impact

Each edit below is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0213-site-identity.md` § 4.1 — the file gains `icon`
  and `picture`; § 4.6 — the Settings page chooses them; § 9 — the icon
  line points here.
- `docs/specs/PRESS-0008-builder.md` § 4.1 — `ROOT_OUTPUT` gains
  `site-icon.png`.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0227-site-icon-and-picture-loop-log.md`.
