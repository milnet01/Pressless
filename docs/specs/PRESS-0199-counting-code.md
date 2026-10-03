<!-- ants-spec-format: 1 -->
# PRESS-0199 — Pressless puts Google's counting code on the site

**Status:** accepted (2026-10-02).
**Kind:** feature.
**Source:** ROADMAP PRESS-0199 (user decision 2026-10-01; `docs/design.md`
§ What may depend on what, "Pressless writes the counting code itself" and
"Privacy is the one page Pressless keeps").

**Amends:** PRESS-0001 (§ 4.1, § 4.2, INV-6), PRESS-0008 (§ 4.3, § 4.4),
PRESS-0021 (§§ 4.3 to 4.6, § 4.9), PRESS-0122 (§ 4.2), PRESS-0126
(§ 4.3). § 11 lists each edit.

Layman: once you have a Google Analytics property, Pressless finds its
counting code and puts it on every page of your site, adds a Privacy page
that says so, and links it from your footer, so your visitor numbers start
filling in.

## 1. Goal

After this ships, Settings holds the site's Google measurement id
(`G-…`). Where it holds one, every page the Builder publishes carries
Google's tag with that id; where it holds none, no page does. Pressless
finds the id itself after the Google step's property is chosen, and the
Settings page takes one typed in. While counting is on, a Store holding a
site also holds a Privacy page disclosing it, and the footer a link to it.

## 2. Problem

1. **Nothing puts the tag on a page.** Google counts only pages carrying
   its tag, and `builder._Build.page` writes none. A stranger's dashboard
   (PRESS-0019) therefore reads nothing.
2. **Nothing holds the id.** `settings.Settings` carries
   `analytics_property_id`, the numeric id Google's reporting interface is
   queried by, and no `G-…` id. PRESS-0001 § 4.2 says *"Pressless never
   writes that tag, so it does not hold one"*; the user overturned that on
   2026-10-01, and `docs/design.md` now says Settings holds both.
3. **Counting needs a disclosure.** `docs/design.md` § Privacy: while
   counting is on the site must carry a page disclosing it, under POPIA.
   No Store holds one, and the starter set (PRESS-0126) has none.

## 3. Scope decisions (agreed with the user)

1. **Automate what can be automated, give steps for the rest.** Decided by
   the user 2026-10-01.
2. **Privacy is added, published, while counting is on.** Decided by the
   user 2026-10-02 (`docs/design.md` § Privacy).
3. **Pressless finds the id itself** after the Google step's property is
   chosen. *(decided here)* Google's Admin interface lists a property's
   data streams under the read-only permission Pressless already holds,
   and a web stream carries its `measurementId`. Sources:
   https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1beta/properties.dataStreams/list
   and
   https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1beta/properties.dataStreams
4. **The Settings page also takes the id typed in.** *(decided here)* The
   dashboard is declinable (ADR-0005), and a user who declines it may still
   want counting.
5. **A preview never carries the tag.** *(decided here)* The user's own
   previewing is not a visit.
6. **A page already holding Google's tag is left alone.** *(decided here)*
   An imported page may carry one by hand, and two tags count each visit
   twice.
7. **Counting on adds a Privacy link to the footer, where it has none.**
   *(decided here)* A disclosure nobody can reach does not disclose. The
   footer is the one place every page shares.
8. **Clearing the id switches counting off and leaves the Privacy page.**
   *(decided here)* The page is the user's once it is in the Store.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 Settings

```python
# src/pressless/settings.py — added
@dataclass(frozen=True)
class Settings:
    ...
    measurement_id: str | None   # Google's G-... id for the counting code
```

`measurement_id` is optional on load, as `analytics_property_id` is:
absent and `null` both load as `None`. `check` refuses any other value
that does not match `\AG-[A-Z0-9]+\Z`, with `SettingsError.key` set to
`"measurement_id"`. `save` writes it as a top-level key. `version` stays
`1`: a build before this one carries an unrecognised top-level key
through (PRESS-0001 § 4.4), so neither direction loses it.

### 4.2 The tag

```python
# src/pressless/builder.py — added
def counting_code(measurement_id: str) -> str: ...
```

`counting_code` returns Google's tag for that id:

```html
<script async src="https://www.googletagmanager.com/gtag/js?id=G-…"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-…');</script>
```

The id has passed `check`'s pattern, so it needs no escaping.

**`build` alone writes it** — the build `publishing.publish` makes, whose
`photo_src` is `None`. `preview` and `preview_html` never do.

- **A page the Builder writes whole** (`_Build.page`) carries it inside
  `<head>`.
- **A fixed page** carries it immediately before its first `</head>`,
  matched ignoring case; where there is none, immediately after its first
  `<body…>` tag; where there is neither, at its end.
- **A forward** carries none: it sends the reader on at once, and the page
  it sends them to counts the visit.
- **A page whose finished text already holds `googletagmanager.com/gtag/js`**
  — its own, or a header or footer filled into it — gets no second tag.
  Its markers are filled as usual.
- **`content/` holds the Store's bytes unchanged** (PRESS-0008 § 4.7), so
  no tag is added there.

### 4.3 Finding the id

```python
# src/pressless/google_signin.py — added
def measurement_ids(token: str, property_id: str, site_address: str,
                    client: Transport | None = None) -> tuple[str, ...]: ...
```

It reads `GET https://analyticsadmin.googleapis.com/v1beta/properties/<id>/dataStreams`,
following `nextPageToken` at most `PAGE_LIMIT` times, as `properties`
does, and keeps each stream whose `type` is `WEB_DATA_STREAM` and whose
`webStreamData.measurementId` matches § 4.1's pattern.

- Where one of those streams' `webStreamData.defaultUri` has the host of
  `site_address`, compared ignoring case and a leading `www.`, the answer
  is that stream's id alone.
- Otherwise the answer is every web stream's id, in Google's order.

**After the Google step's property is chosen** (`google_setup._choose`),
with the access token already in hand:

- one id, and Settings holding none → it is saved with the property id;
- none → the page says how to add a web stream in Google Analytics
  (Admin, Data streams, Add stream, Web, the site's address), and that the
  id can then be typed on the Settings page;
- several → the page lists them, and says to type the right one on the
  Settings page;
- Settings already holding an id → it is kept, and a different id found
  is shown beside it;
- a failure reaching Google → shown through `Face.fail`; the property id
  is saved as today.

### 4.4 The Settings page

The form (PRESS-0021 § 4.3) gains an optional box,
`measurement_id`, filled from Settings and empty on first run. An empty
box saves `None`. A value failing § 4.1's pattern is a refused answer
with a hint beside the box: `measurement_id` joins `repository`,
`site_name` and `site_address` among PRESS-0021 § 4.4's refused answers,
and § 4.5's candidate takes the answer on both paths.

### 4.5 Switching counting on

*PRESS-0213 § 4.6 changes this section.*

**Every save, from § 4.3 or § 4.4, that leaves Settings holding an id**
runs these after `settings.save` succeeds, **and only where the Store holds
a site** (`store.holds_a_site`): an empty copy stays empty for Import
(`docs/design.md` rule 9). On first run with the starter box ticked the
fill has already run, so the Store holds one.

1. Where the Store holds no `pages/privacy.html`, write
   `starter.privacy_page(site_name, builder.stylesheets(folder))` there,
   published.
2. Where the footer furniture file exists and holds no
   `pages/privacy.html`, insert
   `<a href="{{UP}}pages/privacy.html">Privacy</a>` immediately before its
   first `</footer>`, matched ignoring case, or at its end where it has
   none. Pressless never creates a footer file.

Each step checks before it writes, so a later save adds nothing twice and
retries what an earlier one could not add.

A failure in either is shown through `Face.fail` after the save, so the
id is kept and counting is on; the page says the Privacy page or link
could not be added. The done page names both, and says the Privacy page
needs the user's contact details added.

**The Privacy page** is a whole HTML document in the shape of the starter
pages (PRESS-0126 § 4.3): it links each stylesheet it is handed from depth
1 (`../` before each), its header pair carries `page="privacy"`, and it
says, in words the implementer chooses:
the site counts visits with Google Analytics, which uses cookies; what is
counted (pages read, the visitor's country and region, the kind of device
and browser); that the counts are used only to see how the site is read;
a link to Google's own privacy policy and to Google's opt-out browser
add-on; and a sentence the user replaces with how to reach them. It names
nobody. `starter.fill` does not write it: the starter set holds it only as
the text `privacy_page` returns.

### 4.6 What this never does

- It never writes the tag into the Store: only the site folder carries it.
- It never adds a second tag to a fixed page that has one.
- It never removes the Privacy page or its link.

## 5. Invariants

- **INV-1** — Settings loads a file with no `measurement_id` as `None`,
  refuses `"UA-1234"` and `"g-abc"` with `key == "measurement_id"`, and
  round-trips `"G-ABC123"`. *Test:*
  `tests/test_settings.py::test_the_measurement_id_is_optional_and_shaped`.
  *Breaks when:* an older file fails to load, or a malformed id is saved.
- **INV-2** — With an id in Settings, every HTML page a `build` writes
  outside `content/`, a forward excepted, carries
  `googletagmanager.com/gtag/js` exactly once, with `?id=<id>` where its
  text held no tag of its own; with none, no page carries
  `googletagmanager`. *Test:*
  `tests/test_builder.py::test_every_built_page_carries_the_counting_code`,
  with a header furniture file holding a tag in a second build.
  *Breaks when:* an entry page, a listing or a fixed page lacks it, a
  forward or a `content/` copy carries it, or a page whose header holds a
  tag gets a second.
- **INV-3** — A fixed page holding `</HEAD>` gets the tag just before it; one
  with no head gets it just after `<body class="x">`; one already holding
  a gtag.js script gets no added tag and has its markers filled. *Test:*
  `tests/test_builder.py::test_the_counting_code_finds_its_place`.
  *Breaks when:* the match is case-sensitive, or a hand-written tag is
  doubled.
- **INV-4** — `preview` and `preview_html` write no `googletagmanager`
  with an id in Settings. *Test:*
  `tests/test_builder.py::test_a_preview_is_never_counted`.
  *Breaks when:* the preview build takes the publishing branch.
- **INV-5** — `measurement_ids` keeps web streams only, returns the stream
  matching the site's host alone where one does, and every web stream's id
  otherwise. *Test:*
  `tests/test_google_signin.py::test_measurement_ids_reads_the_web_streams`,
  with a fake transport holding an app stream, a `www.` match and a
  mismatch.
  *Breaks when:* an app stream is returned, or the host match ignores
  `www.` handling.
- **INV-6** — After a property is chosen and Google answers one id, Settings
  holds it, the Store holds `pages/privacy.html`, and the footer links it.
  Where Settings already held a different id, it is kept. *Test:*
  `tests/test_google_setup.py::test_choosing_a_property_switches_counting_on`.
  *Breaks when:* the found id is not saved, overwrites a typed one, or the
  Privacy page is not added.
- **INV-7** — Saving the Settings page with an id adds the Privacy page
  and footer link where absent; saving again adds neither twice; a Store
  already holding `pages/privacy.html` keeps its own; a Store holding no
  site gains nothing. *Test:*
  `tests/test_setup.py::test_switching_counting_on_adds_privacy_once`.
  *Breaks when:* the link is inserted on every save, the user's Privacy
  page is replaced, or an empty Store is written to.
- **INV-8** — A refused `measurement_id` answer writes nothing and shows a
  hint beside the box. *Test:*
  `tests/test_setup.py::test_a_malformed_measurement_id_is_a_refused_answer`.
  *Breaks when:* a malformed id reaches `settings.save`.

## 6. Failure modes

- **Google unreachable after the property is chosen**: the property id is
  saved as today, counting stays off, and the page says so; the id can be
  typed on the Settings page.
- **The Privacy page or link cannot be written**: the id is kept and
  counting is on; the page says what could not be added, and the next
  save retries it.
- **Counting switched on over a Store holding no site**: nothing is added;
  the next save after the site exists adds both, and Import owes the same
  (PRESS-0125).
- **A fixed page with a hand-written tag for an older id** keeps counting
  under that id; Pressless does not rewrite a tag it did not write.
- **A footer with no `</footer>`** gets the link at its end, which the
  user may move in the page editor.

## 7. Tests

`tests/test_settings.py` gains INV-1; `tests/test_builder.py` INV-2,
INV-3 and INV-4; `tests/test_google_signin.py` INV-5;
`tests/test_google_setup.py` INV-6; `tests/test_setup.py` INV-7 and
INV-8.

Each test is seen failing against the code before this item, then
mutation-probed once the code lands.

**By hand, before release:** a real property's data streams read through
the Google step on the Windows box, and Google's Realtime report showing
a visit to a page published with the tag.

## 8. Alternatives considered (and rejected)

- **The user copies the id from Google.** Rejected (§ 3 decision 3): the
  read-only permission already reaches it.
- **Widen the Google permission to create a web stream.** Rejected:
  `analytics.edit` asks for more than reading numbers needs, and Google
  reviews each permission an app asks for (PRESS-0200).
- **A tag in the footer furniture.** Rejected: the user edits that file,
  and a tag removed by hand would stop counting without a word.
- **Tag every preview.** Rejected (§ 3 decision 5).
- **A Privacy page with no footer link.** Rejected (§ 3 decision 7).

## 9. Out of scope

- Refusing to remove the Privacy page while counting is on — PRESS-0195,
  which brings removing pages.
- Making the Google Analytics account and property for the user —
  Google requires a person to do it; the steps are the Google step's.
- A cookie banner — deferred; not yet queued. Whether one is owed is the
  user's to decide.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_settings.py::test_the_measurement_id_is_optional_and_shaped` |
| INV-2 | `tests/test_builder.py::test_every_built_page_carries_the_counting_code` |
| INV-3 | `tests/test_builder.py::test_the_counting_code_finds_its_place` |
| INV-4 | `tests/test_builder.py::test_a_preview_is_never_counted` |
| INV-5 | `tests/test_google_signin.py::test_measurement_ids_reads_the_web_streams` |
| INV-6 | `tests/test_google_setup.py::test_choosing_a_property_switches_counting_on` |
| INV-7 | `tests/test_setup.py::test_switching_counting_on_adds_privacy_once` |
| INV-8 | `tests/test_setup.py::test_a_malformed_measurement_id_is_a_refused_answer` |
| § 4.5 the Privacy page's words | **Partial:** the leak sweep catches the names it holds; whether the words are accurate is read |
| A real stream and a real visit | **nothing** in CI — by hand (§ 7) |

## 11. Cross-doc impact

Each edit below is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0001-settings.md` § 4.1, § 4.2 and INV-6 — Settings
  gains `measurement_id`, and § 4.2's "Pressless never writes that tag"
  is overturned.
- `docs/specs/PRESS-0008-builder.md` §§ 4.3 and 4.4 — published pages
  carry the counting code.
- `docs/specs/PRESS-0021-setup.md` §§ 4.3 to 4.6 and 4.9 — the form gains
  a box, `measurement_id` is a refused answer and a candidate field, and a
  save holding an id writes the Privacy page and footer link.
- `docs/specs/PRESS-0126-starter-site.md` § 4.3 — the starter set gains
  `privacy_page`, which `fill` does not write.
- `docs/specs/PRESS-0122-google-signin.md` § 4.2 — choosing a property
  also reads its web streams.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0199-counting-code-loop-log.md`.
