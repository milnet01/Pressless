<!-- ants-spec-format: 1 -->
# PRESS-0218 — Setup takes in a Pressless site already in a GitHub repository

**Status:** accepted (2026-10-23). Two review rounds of one loop each,
the user's budget; the second round's fixes were read by no lane.
**Kind:** feature.
**Source:** ROADMAP PRESS-0218 (user decision 2026-10-02; scope settled by
the user 2026-10-23).

**Blocker for:** PRESS-0210, whose folder-of-pages Import is where a
repository Pressless did not make goes. **Pairs with:** PRESS-0333, the
takeover of a site GitHub Actions builds, split out of this item.

**Amends:** PRESS-0212 (§ 4.4, the *pages* and *site* steps), PRESS-0231
(§ 4.3 and INV-6, a taken name) and PRESS-0009 (§ 4.5, fetching).
§ 11 lists each edit.

Layman: someone whose Pressless site is already on GitHub — on another
computer, or before a reinstall — points setup at that repository, is shown
what will come across, and carries on editing the same site.

## 1. Goal

After this ships, setup accepts a repository that already holds a site
Pressless published, and fills the empty Store from it. Before anything is
saved, the last step shows what was found, what will come across, and what
will not. Finish fills the Store and saves Settings; nothing in the
repository changes. The site keeps its address and its own domain, because
both stay in the repository untouched. A repository holding a site Pressless
did not make is still refused, now with a sentence saying so, until
PRESS-0210 can bring it in.

## 2. Problem

1. **The sign-in flow refuses every existing repository that holds files.**
   `setup._first_run_wizard`'s `check_new_repository` accepts a 422 only over
   a Public repository whose `publisher.root_entries` is `()`. Anything else
   is the hint `setup.hint.taken`, so a person whose site is already on
   GitHub cannot set up against it (PRESS-0231 INV-6).
2. **The hand-made-key flow accepts the repository and then fills a
   starter.** `check_repository` checks only the name and
   `publisher.public_repository`. The *site* step then fills the starter
   where it is ticked, and the first publish meets
   `publishing.WouldReplaceASite`. `docs/design.md` § Setup's three starts
   says setup offers to take that site in instead; nothing does.
3. **Nothing fetches a repository's current state.**
   `publisher.fetch_previous` reads the current commit's first parent, and
   raises `NoPreviousState` where there is none.
4. **Nothing fills an empty Store from a fetched `content/`.** Undo reads one
   (`undo._read`) and writes it back over a Store that holds a site
   (`undo._reconcile`), but it carries no photographs and no added files,
   which sit outside `content/` (`docs/design.md` § Setup's three starts).

## 3. Scope decisions (agreed with the user)

1. **A repository Pressless did not make goes to PRESS-0210** (user,
   2026-10-23), whose § 4.11 brings its pages in. Only one holding what a
   tool builds from is still refused.
2. **A site GitHub Actions builds is PRESS-0333's** (user, 2026-10-23),
   split out so this spec settles in one review round. The PRESS-0229
   refusal stays until it ships.
3. **The user is told before any change, and after it** (user, 2026-10-23,
   for every takeover and take-in). The *site* step names what will come
   across and what will not, and nothing is written to the Store until
   Finish. The done page says what came across.
4. **One review round** for this spec (user, 2026-09-29), and one more
   for the amendment below (user, 2026-10-23).
5. **A failed take-in deletes the photographs it placed** (user,
   2026-10-23). They were never the user's: they are copies into an empty
   Store, and the repository still holds them. No other caller may delete
   a photograph (§ 4.3).
6. **A site published before the identity file existed is still taken in**
   (user, 2026-10-23). Pressless began writing `content/identity/` with
   PRESS-0213, so an older site has none (§ 4.2).

Every other choice below follows from § 2 and `docs/design.md` § Setup's
three starts, which already decides that a fetched `content/` becomes the
Store the way undo writes it back, and that published photographs and added
files are carried as originals.

## 4. Design

### 4.1 Fetching a chosen state (Publisher)

```python
# src/pressless/publisher.py — added

def fetch_state(settings: Settings, token: str, into: Path,
                prefixes: tuple[str, ...], commit: str = "",
                transport: Transport | None = None) -> Fetched: ...
```

`fetch_state` writes the tree of `commit`, or of the default branch's
current commit where `commit` is `""`, into `into`, keeping only paths
within one of `prefixes`. It shares `fetch_previous`'s body: one private
helper takes the commit and the prefixes, and `fetch_previous` passes its
parent and `(prefix,)`. So both keep § 4.5's guarantees: a path lands at
`into` joined to its full repository-relative path, nothing lands until
every file has been fetched, and a path that would be written outside
`into` is refused. `Fetched.commit` is the commit read. A repository with no
commits raises `RemoteStateMissing`.

### 4.2 What a take-in reads (Face)

A new module, `src/pressless/takein.py`, a Face sequence like undo
(`docs/design.md` rule 1).

```python
PREFIXES = ("content/", "photographs/", "files/", "site-icon.png")

@dataclass(frozen=True)
class Found:
    commit: str                       # the state read; the take-in uses this one
    made_here: bool                   # § 4.2's test of a Pressless site
    entries: int                      # published entries
    pages: int                        # fixed pages
    comments: int                     # entries with comments
    photographs: int
    files: int
    identity: store.Identity | None
    left: tuple[str, ...]             # fetched paths that will not come across (§ 4.4)

def look(folder: Path, settings: Settings, key: str, commit: str = "",
         transport: publisher.Transport | None = None) -> Found: ...

@dataclass(frozen=True)
class TakenIn:
    found: Found                      # what came across; the done page's counts
    reverse: Callable[[], None]       # undoes every write take_in made (§ 4.3)

def take_in(folder: Path, settings: Settings, key: str, commit: str, *,
            capture: Callable[[], AbstractContextManager[list[str]]] = ...,
            notices: list[str] | None = None,
            transport: publisher.Transport | None = None) -> TakenIn: ...
```

`capture` and `notices` are undo's (`undo.undo`): `capture` wraps the
Store writes and never the fetch, which is minutes long while a capture
holds a process-wide lock.

`look` empties the fetch area (`undo.FETCH_FOLDER`), calls `fetch_state`
with `PREFIXES` and `commit`, reads what landed, empties the fetch area
again and returns `Found`. It writes nothing to the Store.

**`made_here` is the one test of a Pressless site.** It is true where
`store.read_identity` over the fetched `content/` returns an identity, or
where the shared read (below) finds at least one published entry, fixed
page or furniture piece. The second arm takes in a site published before
PRESS-0213, which has no identity file (§ 3 decision 6). Both arms read
only Pressless's own layout, `content/<kind>/<name>` with the Store's
folder names and suffixes, so another tool's `content/` — Markdown posts
under `content/posts/`, say — meets neither. A `content/` folder alone is
not enough.

The read is undo's: `undo._read`'s body becomes a function both modules
call, `undo.read_state`, so the two cannot disagree about which `content/` paths are Store
files. Photographs are `photographs/<name>` and files `files/<name>`, one
segment each.

### 4.3 What a take-in writes (Face)

`take_in` refuses with `TakeInStopped` where `store.holds_a_site(folder)` is
true: it fills an empty Store only, as Import does (`docs/design.md` rule 9).
Otherwise it fetches `commit` — the state `look` read, so what is written is
what was shown — and writes it through the Store's own calls:

1. Every entry, page, furniture piece, template, comment file, forwards
   file, option, look file and the identity, through undo's reconcile
   (`undo._reconcile`'s body, shared as `undo.reconcile`), which over an empty Store writes each
   one and demotes nothing.
2. Each `photographs/<name>` as the original `name`, through
   `photographs.keep` with `store.photograph_path_for`, and each
   `files/<name>` as the kept file `name`, through `store.file_path_for`.
   The Builder publishes both under the original's own name
   (`builder._Build.web_copy`, `builder._Build.file_copy`), so the naming
   rule `docs/design.md` § Setup's three starts asks for maps each name to
   itself. A photograph comes across as its web copy, smaller
   than the original it was made from.
3. `site-icon.png`, where the identity names an icon: kept as the photograph
   `site-icon.png`, and the identity's `icon` set to that name. The Builder
   publishes an icon as `site-icon.png` only (`builder._Build.icon_copy`),
   never under its own name, so the original is not in the repository.
   Where the identity names an icon and the repository holds no
   `site-icon.png`, the identity's `icon` is cleared, or the next build
   would stop on a photograph the Store does not hold.

Each write records its reversal, as undo's do. A failure at any step
reverses every write before it, so the Store is empty again, and raises.
A photograph is reversed with a new Store call, the one that deletes a
photograph (§ 3 decision 5):

```python
# src/pressless/store.py — added
def unplace_photograph(folder: Path, name: str) -> None:
    """Delete the original `name`. Only a take-in reversing its own
    placement into an empty Store calls this (PRESS-0218)."""
```

`move_to_bin` still refuses a photograph, and `store.unplace_photograph`
has one caller, `takein` (INV-12).
The fetch area is emptied when the sequence ends, whatever happened.

### 4.4 What does not come across

`Found.left` names, by path, every fetched path no step of § 4.3 writes,
and the screen groups them:

- a `photographs/` or `files/` name the Store refuses
  (`store.photograph_path_for`, `store.file_path_for` raise), which
  `take_in` skips;
- anything under `content/` that `undo.read_state` passes over.

A `content/` file the Store refuses is not left behind: `undo.read_state` raises
`StoreError`, as it does for undo, and the *pages* step is a `Stop`.

And three things the repository never held, always said: drafts, which are
never published; the full-size photograph originals; and Settings kept on
another computer (the measurement id, the property id, the Daily Prompt
filter), which are set again in Settings.

Root entries Pressless does not make — a `CNAME`, a `README.md`, a
`.github` folder — are not fetched. They stay in the repository, and setup
puts them on the untouchable list as it does today (`setup.untouchable`).

### 4.5 The wizard (amends PRESS-0212 § 4.4 and PRESS-0231 § 4.3)

The step list does not change in either flow.

**repository, sign-in flow.** A 422 over a Public repository whose root
holds files is no longer `setup.hint.taken`. The answers gain
`existing: "yes"`, and the step goes on to the installation checks as for a
new one. Nothing is written to that repository by this step.

**pages.** Before any write, where the root holds `content` or an entry
`publishing.A_SITE` names (the test the starter's first publish uses):

- `takein.look`. Not `made_here` → PRESS-0210 § 4.11 (§ 3 decision 1).
- `made_here` → the answers gain `take_in_commit`, `Found.commit`.

Any other root goes on as a new repository, and `take_in_commit` is
removed from the answers.

Then Pages is read and switched on as today. The step's words say, before
Next, that Next switches GitHub Pages on where it is off, which puts what
the repository holds on the web and adds one empty file, `.nojekyll`.

**site**, where the answers carry `take_in_commit`. The body is the take-in
screen in place of the name, description and starter fields:

- what was found: the site's name, and the counts of § 4.2's `Found`,
  from `takein.look` with `take_in_commit`;
- that Finish copies it into Pressless on this computer and changes nothing
  on GitHub;
- what will not come across (§ 4.4).

Where that `look` fails, the body is `Face.fail`'s sentence for the
failure in place of the take-in screen.

The check runs PRESS-0021 § 4.6 from step 2, with `takein.take_in` and
that commit in the starter fill's place, passed `face.capture` and called
outside the fill's capture, and `starter_ticked` false. The identity is
the one the take-in wrote; where it wrote none (INV-11), the identity
check and the identity write are skipped. A failure after the take-in
calls `TakenIn.reverse`. A `TakeInStopped` or a `PublishError` is a `Stop`
through `Face.fail`, and Settings is not saved, except that a
`RemoteStateMissing` from the take-in says the repository changed since
it was shown and to go Back to *pages*. The done page says the site came
in, with `TakenIn.found`'s counts.

`take_in_commit` and `existing` are plain answers: neither ends in `key`, so
the progress file keeps them (`wizard.is_secret`), and a resumed wizard
takes in the same state it showed.

## 5. Invariants

- **INV-1** — A take-in sends no write to GitHub but Pages being switched
  on where it was off. Over a repository whose Pages already serves its
  root, setup from the *repository* step to Finish sends no non-GET
  request naming that repository. The sign-in flow's `POST /user/repos`,
  answered 422, names none.
  *Test:* `tests/test_takein.py::test_a_take_in_writes_nothing_to_github`.
  *Breaks when:* any step adopts the repository by writing to it — a
  `.nojekyll`, a starter, a publish.
- **INV-2** — A repository whose root holds a site (§ 4.5 *pages*) and
  whose fetched `content/` meets neither arm of § 4.2's `made_here` test
  is a `Hint` on the *pages* step, and no write is sent.
  *Test:* `tests/test_takein.py::test_a_site_made_elsewhere_is_refused`,
  over a fixture laid out as another site tool lays out `content/`:
  Markdown posts under `content/posts/`, and no identity.
  *Breaks when:* `made_here` tests for a `content/` folder alone, or its
  second arm counts a file outside the Store's own layout.
  *Narrowed by PRESS-0210 INV-14, which replaces this refusal of every site
  made elsewhere; the test keeps its name.*
- **INV-3** — `take_in` writes only into a Store that holds no site.
  *Test:* `tests/test_takein.py::test_a_take_in_needs_an_empty_store`.
  *Breaks when:* the check is dropped, or tested after the first write.
- **INV-4** — A take-in carries every Store file a publish put in
  `content/`, and every photograph and kept file the publish wrote, byte
  for byte as the repository holds it. A Store published to a recording
  double and taken into an empty folder reads back equal for every kind
  `content/` carries, the identity's `icon` aside (INV-8). Its photographs
  are exactly the publish's web copies, plus `site-icon.png` where there is
  an icon, and its kept files exactly the publish's.
  *Test:* `tests/test_takein.py::test_a_published_site_comes_back_whole`.
  *Breaks when:* a kind `undo.read_state` or the reconcile knows is
  skipped, or the take-in reads a second copy of it that drifts.
- **INV-5** — Nothing is written to the Store before Finish: after the
  *pages* and *site* steps are shown, every folder § 4.3 writes into holds
  the files it held before them.
  *Test:* `tests/test_takein.py::test_looking_writes_nothing`.
  *Breaks when:* `look` fills the Store, or the *site* step's body does.
- **INV-6** — What is written is the state that was shown: `take_in`
  fetches `take_in_commit`, not the branch's current commit.
  *Test:* `tests/test_takein.py::test_the_state_shown_is_the_state_taken`,
  where the double's branch moves between *pages* and Finish.
  *Breaks when:* `take_in` calls `fetch_state` with no commit.
- **INV-7** — A failure part-way leaves the Store empty and Settings
  unsaved: afterwards every folder § 4.3 writes into holds the files it
  held before the take-in, so Finish can be pressed again.
  *Test:* `tests/test_takein.py::test_a_failed_take_in_leaves_nothing`,
  failing the write of the last photograph, and again failing the
  Settings save after the take-in.
  *Breaks when:* a write records no reversal, or a placed photograph is
  left behind.
- **INV-8** — A site with an icon comes back with one: the identity's
  `icon` names the kept photograph `site-icon.png`, and the next build
  publishes the icon.
  *Test:* `tests/test_takein.py::test_the_icon_comes_back`.
  *Breaks when:* the identity keeps the old icon name, whose original is
  not in the repository, and the build stops.
- **INV-9** — The *site* step names, before Finish, every path in
  `Found.left` and the three things § 4.4 always says do not come across.
  *Test:* `tests/test_takein.py::test_the_screen_says_what_stays_behind`.
  *Breaks when:* a refused name is dropped without being listed.
- **INV-10** — `fetch_state` lands nothing until every file is fetched,
  and refuses a path outside `into`, as `fetch_previous` does.
  *Test:* `tests/test_publisher.py::test_fetch_state_lands_nothing_on_failure`
  and the existing `fetch_previous` tests, run over the shared helper.
  *Breaks when:* the two functions stop sharing one body.
- **INV-11** — A site whose `content/` holds published entries and no
  identity file is taken in, with no identity written.
  *Test:* `tests/test_takein.py::test_a_site_from_before_identities_comes_in`.
  *Breaks when:* `made_here` reads the identity alone.
- **INV-12** — `store.unplace_photograph` has one caller, `takein`, and
  `move_to_bin` still refuses a photograph.
  *Test:* `tests/test_takein.py::test_only_a_take_in_deletes_a_photograph`,
  which walks `src/` for calls, beside the existing
  `tests/test_store.py::test_binning_refuses_a_path_outside_the_store`.
  *Breaks when:* another module deletes a photograph through it.

## 6. Failure modes

| What fails | What happens |
|---|---|
| The fetch fails part-way | Nothing lands (INV-10); the *pages* step or Finish is a `Stop`, and the Store is empty |
| A Store write fails | Every earlier write is reversed (INV-7), the fetch area is emptied, Finish is a `Stop` |
| The repository moves on after *pages* | Finish takes in the commit that was shown (INV-6) |
| That commit is gone (history rewritten) | `fetch_state` raises `RemoteStateMissing`; a `Stop` saying to go Back |
| The Store holds a site at Finish | `TakeInStopped`, a `Stop`; nothing is written (INV-3) |
| A fetched photograph or file name the Store refuses | Not carried, and listed (INV-9) |
| On Windows, a fetched path Windows cannot hold | `fetch_state` raises `UnfetchablePath` before anything lands (PRESS-0009 § 4.5); the *pages* step is a `Stop` |
| A fetched `content/` file the Store refuses | `look` raises `StoreError`; the *pages* step is a `Stop` (§ 4.4) |
| Pressless closes between *pages* and Finish | The progress file keeps `take_in_commit`; the resumed wizard shows the same state |

## 7. Tests

`tests/test_takein.py` is new and holds INV-1, INV-2, INV-3, INV-4, INV-5,
INV-6, INV-7, INV-8, INV-9, INV-11 and INV-12, all through doubles:
a recording GitHub double answering the tree and blob reads, and an empty
temporary folder for the Store. INV-4 publishes a Store built from the
starter, with a published entry and its comments, a forwards file, a
photograph, a kept file and an icon, into that double
first, so the fixture is what a publish writes rather than a hand copy.
INV-10's new test is in `tests/test_publisher.py` beside `fetch_previous`'s.
Each test is seen to fail against the code before it is written: INV-1 and
INV-2 against today's `check_new_repository` and `check_pages`.

## 8. Alternatives considered (and rejected)

- **A new wizard step for the take-in.** Rejected: `wizard.Step` has no
  condition, so a step shown only for an existing repository would need a
  new mechanism, and the step count would change between runs. The *site*
  step is where the starter is offered today, and a take-in replaces the
  starter.
- **Fetch the whole repository.** Rejected: only `content/`, `photographs/`,
  `files/` and `site-icon.png` become Store files, and the rest stays in the
  repository as untouchable.
- **Fetch again at Finish without a commit.** Rejected: the user would
  confirm one state and receive another (INV-6).
- **Recognise a Pressless site by a `content/` folder.** Rejected: other site
  tools use the name (INV-2).

## 9. Out of scope

- A repository Pressless did not make — PRESS-0210 § 4.11.
- A site GitHub Actions builds — tracked by PRESS-0333.
- Taking a site in after setup, from the Sites screen — deferred; not yet
  queued. A new site already runs the first-run wizard (PRESS-0223 § 4.6),
  so this spec reaches it there; PRESS-0223 § 4.6 opens `/setup` for it.
- Drafts and full-size originals: the repository never held them.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_takein.py::test_a_take_in_writes_nothing_to_github` |
| INV-2 | `tests/test_takein.py::test_a_site_made_elsewhere_is_refused` |
| INV-3 | `tests/test_takein.py::test_a_take_in_needs_an_empty_store` |
| INV-4 | `tests/test_takein.py::test_a_published_site_comes_back_whole` |
| INV-5 | `tests/test_takein.py::test_looking_writes_nothing` |
| INV-6 | `tests/test_takein.py::test_the_state_shown_is_the_state_taken` |
| INV-7 | `tests/test_takein.py::test_a_failed_take_in_leaves_nothing` |
| INV-8 | `tests/test_takein.py::test_the_icon_comes_back` |
| INV-9 | `tests/test_takein.py::test_the_screen_says_what_stays_behind` |
| INV-10 | `tests/test_publisher.py::test_fetch_state_lands_nothing_on_failure` |
| INV-11 | `tests/test_takein.py::test_a_site_from_before_identities_comes_in` |
| INV-12 | `tests/test_takein.py::test_only_a_take_in_deletes_a_photograph` |
| § 4.5's words are plain and say what changes | **nothing** — the words are read by hand before the step ships |
| A real repository taken in end to end | **nothing** — a by-hand run on a scratch repository before release |

## 11. Cross-doc impact

- **PRESS-0009 § 4.5** gains `fetch_state`, and says `fetch_previous`
  shares its body.
- **PRESS-0212 § 4.4**: the *pages* step's take-in read and words, and the
  *site* step's take-in body (§ 4.5 here).
- **PRESS-0021 § 4.9**: setup also writes the Store through
  `takein.take_in`, not only through `starter.fill`.
- **PRESS-0005 § 4.1's deletion rule**: `move_to_bin` is how anything the
  Store holds is deleted, except `unplace_photograph`, a take-in reversing
  its own placement (§ 4.3 here).
- **PRESS-0231 § 4.3 and INV-6**: a 422 over a repository with files goes
  on, marked `existing`; INV-6 becomes "the *repository* step writes
  nothing to an existing repository", and its *Breaks when* names a write.
- **`docs/design.md` § Setup's three starts** is unchanged. Its "otherwise
  its pages go to Import" is PRESS-0210 § 4.11.
- **CHANGELOG** gains an Added entry when this ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0218-take-in-github-site-loop-log.md`.
