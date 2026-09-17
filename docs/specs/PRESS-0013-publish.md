# PRESS-0013 — Publish: one button writes, builds and publishes, and the double-click opens Pressless

**Status:** draft (2026-09-17).
**Kind:** implement.
**Source:** ROADMAP PRESS-0013 (`docs/design.md` § What may depend on what
rules 1, 9 and 10; discovery S1, S6).

**Blocked by:** PRESS-0007, PRESS-0008, PRESS-0009, PRESS-0012, PRESS-0021,
PRESS-0022 — all shipped.
**Blocker for:** PRESS-0014, PRESS-0015, PRESS-0128.

Layman: he clicks Publish beside the entry he is writing, and a few minutes
later it is on his site. If it fails, his files go back to how they were and
he is told what to do. Double-clicking Pressless now opens it in his browser.

## 1. Goal

After this ships, the editor page has a Publish button. One click saves the
box, moves the entry into what is published, builds the site and sends it to
GitHub. A failure puts his files back and says what happened. And the
double-click starts the Face, with setup, the editor and publishing on it, and
opens his browser.

## 2. Problem

1. **Nothing sends writing to the site.** `builder.build` and
   `publisher.publish` exist, and no page calls them in order. Design rule 1
   gives that order to the Face.
2. **A draft has no way into `published/`**, and a working copy has no way
   over its entry. PRESS-0012 § 3 decisions 2 and 6 leave both to this item.
3. **A failed publish must not leave his list lying.** The Store and the site
   disagree if the entry is moved and the site is not.
4. **Nothing guards against replacing the site with an empty one.** Design
   rule 9 gives that guard to this item.
5. **The double-click prints a report and stops.** PRESS-0022 § 4.5's program
   is a placeholder; setup and the editor are reachable only from a test.

## 3. Scope decisions (agreed with the user)

1. **The Publish button is on the editor page and publishes the entry open
   there.** Decided by the user 2026-09-17. The rebuilt site carries any other
   finished change with it.
2. **A failed publish puts the entry back as it was.** Decided by the user
   2026-09-17. A draft stays a draft and a working copy stays waiting. Where
   the outcome is unknown, the entry stays published and he is told to publish
   again.
3. **The console window stays on Windows.** Decided by the user 2026-09-17,
   revisiting PRESS-0022 § 3 decision 4. It says to keep it open, and to close
   it to stop Pressless. The batch file stays too.
4. **A plain waiting message while it publishes.** Decided by the user
   2026-09-17. No file count, so the Publisher does not change.
5. **A new entry is dated when he first publishes it.** Decided by the user
   2026-09-17 (PRESS-0012 § 3 decision 6). Every draft this item publishes
   that is not a working copy takes the moment of publishing as its date.
6. **The guard counts the entry being published.** Decided by the user
   2026-09-17 (PRESS-0124, `docs/design.md` rule 9). Publishing refuses only
   when no published entry would remain.
7. **(decided here) Publish rides on a save.** The click runs PRESS-0012
   § 4.8 steps 1 to 4 first, so what is published is exactly what the box
   holds.
8. **(decided here) Settings and the key are read before the Store moves.**
   A missing key or an unset machine then needs nothing put back.
9. **(decided here) The double-click prints the same report, then serves.**
   `--self-check` prints it and stops. So the route the release job tests is
   still the writer's route (PRESS-0022 § 4.5).
10. **(decided here) The sequence lives in the Face, as
    `src/pressless/publishing.py`.** Only the Face knows the order (design
    rule 1), and only the Face reaches Credentials (rule 10).

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/publishing.py

MESSAGE = "Publish {slug}"     # the commit message; {slug} is the entry's address

class NothingToPublish(Exception): ...   # no published entry would remain

def publish(folder: Path, settings: Settings, key: str, *, entry: str | None,
            transport: publisher.Transport | None = None) -> publisher.Outcome: ...
def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None: ...
```

`publish` is § 4.3's sequence from the Store move on. `entry` is the address
of the draft to publish, or `None` to publish the site as the Store holds it.
PRESS-0014 and PRESS-0128 call it with `None`. `register` adds
`POST /publish`, with `publishing=True` (§ 4.5).

```python
# src/pressless/editor.py — added

LOCK: threading.Lock                     # every write, preview and publish runs under it

def save(folder: Path, form: dict[str, str]) -> tuple[store.Entry, str]: ...
```

`save` is PRESS-0012 § 4.8 steps 1 to 4, moved out of the route so publishing
runs the same code. It returns the entry written and its new `base`, and raises
what those steps raise. The editor's own routes take `LOCK` in place of the
lock `register` made.

`publishing.py` adds its type's sentence to `face.SENTENCES` when it is
imported, as `editor.py` does, because `face.py` cannot import it back.

### 4.2 The route

`POST /publish` takes § 4.8's save fields. In order, under `editor.LOCK`:

1. **Save.** `editor.save(folder, form)`. A failure answers exactly as a
   failed save does (PRESS-0012 § 4.8): status 409, the failure's fragment.
2. **Settings.** `settings.load(folder)`.
3. **The key.** `credentials.read(store, folder, github_account)` from the
   loaded Settings.
4. **Publish.** `publish(folder, settings, key, entry=<the saved address>)`.

Every Store and Settings call runs inside `face.capture()`.

**A failure at steps 2 to 4 answers status 200 with JSON**, because the save
at step 1 landed and the page needs its new address and `base`:

```json
{"published": false, "slug": "…", "draft": true, "base": "…",
 "failure": "<fragment>", "notices": "<fragment>"}
```

The fragment is `face.fail(failure, publishing=…, secret=setup.KEY)`, with
`publishing` true only for a failure raised from `publisher.publish`. `slug`,
`draft` and `base` name the file as § 4.3 left it.

**Success answers the same shape** with `"published": true`, `"failure":
null`, the published entry's address, `"draft": false`, and the digest of its
published file.

### 4.3 The sequence

`publish` runs these in order. Each step runs only if the one before it
succeeded.

1. **Move the entry**, where `entry` is not `None`. Read the draft at `entry`.
   - **A working copy** — a draft whose `Replaces` names a published entry.
     Remember that published entry as `store.read` gives it. Then write, as
     published, the copy's fields under the address `Replaces` names, without
     any `Replaces` field. The copy keeps its date, which is its entry's.
   - **Any other draft.** Remember it as read. Write it with its date set to
     `_now()` with microseconds dropped, then `store.publish` it.
2. **The guard.** `NothingToPublish` unless `store.list_slugs(folder,
   draft=False)` is non-empty.
3. **Build.** `builder.build(folder, settings, settings.site_folder)`.
4. **Publish.** `publisher.publish(settings, settings.site_folder, key,
   MESSAGE.format(slug=…), transport)`, with the published address, or `site`
   where `entry` is `None`.
5. **Finish.** Bin a working copy with `store.move_to_bin`.

`_now()` is a module-level function, so a test can set it.

**A failure at steps 2 to 4 puts step 1 back, then raises it** (§ 3
decision 2):

| Moved | Put back |
|---|---|
| a working copy | the remembered published entry written back; the copy is left as it is |
| any other draft | `store.unpublish`, then the remembered draft written back |

**Two failures are not put back**: `publisher.OutcomeUnknown`, and any
exception that is not a `publisher.PublishError`, raised from step 4. GitHub
may have taken the change, so the entry stays published, step 5 runs, and the
failure is raised after it. Its sentence says to publish again (PRESS-0011
§ 4.2).

**A failure while putting back** is raised in place of the original, so he is
told something is wrong with his files rather than only with GitHub.

### 4.4 The editor page

PRESS-0012 § 4.7's page gains a **Publish** button beside the box. Its script,
on a click:

- stops the save timer and waits for a save in flight;
- shows *"Publishing… this can take a few minutes the first time. Keep this
  page open."*, and disables the button;
- posts `/publish` with the save fields;
- on a 409 reply, stops saving and shows the body, as a failed save does;
- on a JSON reply, takes `slug`, `draft` and `base` as a save reply does, then
  shows the failure, or *"Published. Your site shows it within a few
  minutes."* and replaces the address bar's `slug`.

### 4.5 Launching

`pressless.__main__.main(argv)`:

1. **The report**, PRESS-0022 § 4.5's three lines, unchanged. A non-zero exit
   there ends the run with that code, whatever the flag.
2. **`--self-check` stops here** and returns 0.
3. **Serve.** `face.serve(folder, open_browser=False)`, then
   `setup.register`, `editor.register` and `publishing.register` on it.
4. **Choose the first page.** `settings.load(folder)` inside
   `face.capture()`. `NotSetUp`, or a `SettingsError` whose `key` is
   `site_folder`, opens `/setup` (PRESS-0021 § 4.8). Anything else opens `/`.
5. **Open the browser** at the Face's link with that path in place of `/`:
   the link's `t` works on any path (PRESS-0011 § 4.5). Where no browser
   opens, print the link.
6. **Wait.** Print *"Pressless is running. Keep this window open while you use
   it, and close it to stop Pressless."* Then block in `_wait()`, a
   module-level function a test can replace. `KeyboardInterrupt` stops the
   Face and returns 0.

### 4.6 What this item never does

- It never publishes a folder it did not just build.
- It never moves an entry after the key has failed to read.
- It never puts back an entry whose publish outcome is unknown.
- It never writes the key into a page, the log or the console.
- It never passes `change` to `builder.build` (PRESS-0008 § 4.1).

## 5. Invariants

The tests below are in `tests/test_publishing.py` unless named otherwise. The
Publisher is reached through a fake `Transport`, as `tests/test_publisher.py`
does, and Credentials through a recording double, as `tests/test_setup.py`
does.

- **INV-1** — Publishing a draft dates it and moves it into `published/`, then
  builds and publishes in that order.
  *Test:* `test_a_draft_is_dated_and_published`. With `_now()` set, the draft
  of 2014 is published, its `Date` is `_now()`, `drafts/` no longer holds it,
  and the fake transport's reference update names a tree carrying the entry's
  page.
  *Breaks when:* the date is kept, the move is skipped, or the Publisher is
  handed a folder built before the move.

- **INV-2** — Publishing a working copy writes it over its entry, without
  `Replaces`, and bins the copy.
  *Test:* `test_a_working_copy_is_published_over_its_entry`. The published
  file holds the copy's body, keeps its entry's date, and carries no
  `Replaces`. The copy is in the bin.
  *Breaks when:* the copy is published under its own address, or keeps its
  `Replaces` field.

- **INV-3** — A definite failure puts his files back.
  *Test:* `test_a_failed_publish_puts_the_files_back`. For a draft and for a
  working copy, the transport answers 401. After each, `published/` and
  `drafts/` hold byte-identical files to before the click's step 4, and the
  bin is empty. Then `builder.build` is made to raise `BuildStopped`, with the
  same result.
  *Breaks when:* the move is not put back, or is put back only for one of the
  two kinds.

- **INV-4** — An unknown outcome is not put back.
  *Test:* `test_an_unknown_outcome_stays_published`. The transport raises on
  the reference update, which the Publisher reports as `OutcomeUnknown`. The
  entry is published, the copy is binned, and the reply's fragment says the
  outcome is unknown.
  *Breaks when:* every `PublishError` is put back.

- **INV-5** — Nothing moves before the key is read.
  *Test:* `test_nothing_moves_without_a_key`. The credentials double raises
  `NotStored`. The draft is still a draft with its old date, and the transport
  records no request.
  *Breaks when:* the key is read after the Store move.

- **INV-6** — The guard refuses a site with no published entry.
  *Test:* `test_publishing_nothing_is_refused`. `publish(…, entry=None)` over a
  Store with furniture and no published entry raises `NothingToPublish`, the
  site folder is not created, and the transport records no request.
  *Breaks when:* the guard is dropped, or runs after the build.

- **INV-7** — The key never reaches a page, the log or the console.
  *Test:* `test_the_key_is_never_shown`, with a sentinel key, through a
  success and a 401. The reply bodies, the log file and `capfd` do not hold
  it.
  *Breaks when:* a failure is formatted with its arguments.

- **INV-8** — The double-click serves, and opens setup when setup is owed.
  *Test:* `tests/test_main.py::test_the_double_click_opens_pressless`. With
  `face.serve`, `webbrowser.open` and `_wait` replaced, `main([])` prints the
  report, registers `/setup`, `/`, `/save` and `/publish`, and opens a link
  whose path is `/setup` over an empty folder and `/` over a set-up one.
  `main(["--self-check"])` serves nothing.
  *Breaks when:* the flag and the double-click take different reports, or the
  first page ignores `NotSetUp`.

- **INV-9** — A publish failure after the save still hands back the saved
  file.
  *Test:* `test_a_failed_publish_names_the_saved_file`. For a published entry
  with no copy yet, a 401 answers 200 with `"published": false`, and the
  `slug` and `base` the reply names are the working copy's, as on disk.
  *Breaks when:* a failure at steps 2 to 4 answers 409, which leaves the page
  saving over a file whose digest it does not hold.

`NothingToPublish` gets a sentence.
`tests/test_face.py::test_every_failure_type_has_a_sentence` finds it.

`tests/test_main.py::test_the_double_click_takes_the_same_path` is
re-fixtured to § 4.5: it replaces `face.serve` and `_wait`, and still asserts
the first line.

## 6. Failure modes

| What breaks | What he sees | What is left on disk |
|---|---|---|
| The save fails | the save's own failure; saving stops | the file as it was |
| Pressless is not set up | `NotSetUp`, beside the saved box | the saved draft |
| The key is missing or unreadable | the Credentials sentence, naming the key | the saved draft |
| GitHub refuses the key, or is unreachable | its sentence; the site has not changed | the entry as it was |
| A file cannot be built | `BuildStopped` | the entry as it was |
| GitHub may have taken it | the unknown-outcome sentence | the entry published |
| Something unforeseen during the upload | the unknown-outcome sentence | the entry published |
| Putting back fails | the Store's failure | whatever the failure left; nothing is deleted |
| No published entry would remain | `NothingToPublish` | nothing moved |
| He closes the console mid-publish | nothing | the entry published or not, as far as it got; publishing again settles it |
| No browser opens | the link, printed in the console | nothing |

## 7. Tests

`tests/test_publishing.py` — new, in CI. It carries INV-1, INV-2, INV-3, INV-4, INV-5,
INV-6, INV-7 and INV-9.

`tests/test_main.py` gains INV-8 and re-fixtures one test (§ 5).

Each test is seen failing against stubs that raise `NotImplementedError`, then
mutation-probed once the code lands.

## 8. Alternatives considered (and rejected)

- **Build with `change` and move the entry only after success.** Rejected:
  PRESS-0008 § 4.1 forbids `change` on a publish, and the Store would not
  hold what the site shows.
- **Leave the entry published on a definite failure.** Rejected by the user;
  his list would say an entry is on the site when it is not.
- **A live file count.** Rejected by the user; it changes the Publisher's
  accepted spec.
- **No console, and a Close button.** Rejected by the user.
- **A separate report route for the double-click.** Rejected: PRESS-0022
  § 4.5 has the release job test the writer's route.

## 9. Out of scope

- Undo, and offering it beside a publish — PRESS-0015.
- Publishing a fixed page or the furniture — PRESS-0014, which calls `publish`
  with `entry=None`.
- Deleting an entry — PRESS-0128.
- One Pressless at a time — not queued (PRESS-0011 § 9).
- A window or a quit button on Linux — not queued; the desktop entry already
  runs in a terminal.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_publishing.py::test_a_draft_is_dated_and_published` |
| INV-2 | `tests/test_publishing.py::test_a_working_copy_is_published_over_its_entry` |
| INV-3 | `tests/test_publishing.py::test_a_failed_publish_puts_the_files_back` |
| INV-4 | `tests/test_publishing.py::test_an_unknown_outcome_stays_published` |
| INV-5 | `tests/test_publishing.py::test_nothing_moves_without_a_key` |
| INV-6 | `tests/test_publishing.py::test_publishing_nothing_is_refused` |
| INV-7 | `tests/test_publishing.py::test_the_key_is_never_shown` |
| INV-8 | `tests/test_main.py::test_the_double_click_opens_pressless` |
| INV-9 | `tests/test_publishing.py::test_a_failed_publish_names_the_saved_file` |
| The script's waiting message and page switch (§ 4.4) | **nothing** in CI — by hand, in a browser |
| That the console stays open on Windows and closing it stops Pressless | **nothing** in CI — the Windows box, by hand, in the desktop session |
| A real publish to GitHub | **nothing** in CI — by hand, against the maintainer's test repository |

## 11. Cross-doc impact

- `docs/specs/PRESS-0022-packaging.md` § 4.5 — the double-click now serves
  after the report, and § 3 decisions 4 and 6 are revisited here; the section
  points here.
- `docs/specs/PRESS-0012-editor.md` § 4.7 and § 4.8 — the page gains the
  button, and the save moves into `editor.save`; the sections point here.
- `docs/specs/PRESS-0021-setup.md` § 4.8 — the launch opens `/setup` (§ 4.5).
- PRESS-0015 — undo publishes through `publish` with `entry=None`, and an
  entry it turns back into a draft needs a mark, or this item dates it again
  (PRESS-0012 § 3 decision 6).
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0013-publish-loop-log.md`.
