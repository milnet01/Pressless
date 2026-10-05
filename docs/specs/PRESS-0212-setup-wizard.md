<!-- ants-spec-format: 1 -->
# PRESS-0212 — Setup becomes a wizard that walks a stranger through GitHub

**Status:** accepted (2026-10-03). One review round, the user's budget for a new spec; its fixes were read by no lane.
**Kind:** feature.
**Source:** ROADMAP PRESS-0212 (user decision 2026-10-02, settled
2026-10-03) and PRESS-0220 (user request 2026-10-03).

**Pairs with:** PRESS-0220. Its shared wizard pattern is § 4.1 here, and its
roadmap entry points at this spec. Setup is the first wizard; the pattern is
built with it.

**Amends:** PRESS-0021 (§ 3 decisions 2 and 10, §§ 4.2, 4.3, 4.6, 4.9) and
PRESS-0127 (§ 3 decision 2). § 11 lists each edit.

Layman: someone who has never used GitHub is taken through getting their
site's free home there one screen at a time, with Back and Next. Pressless
checks each step itself, switches the site on, and remembers where they got
to if they stop halfway.

## 1. Goal

After this ships, first run is a wizard, not one form. It takes a person with
no GitHub account to a saved setup. Each step is one screen with Back and
Next and says which step of how many it is. A step that can be checked is
checked before Next moves on. Pressless switches GitHub Pages on itself.
Closing Pressless halfway keeps what was done, and the next launch resumes at
the step reached. Settings, once setup is done, is the one page it is today.

The wizard pattern itself is shared, so the later wizards PRESS-0220 names
are built on it rather than beside it.

## 2. Problem

1. **First run assumes the repository already exists.** `setup._form` asks
   for "Your site's repository on GitHub (owner/name)" and a publishing key.
   Someone with no GitHub account has no way to answer either, and nothing
   says how.
2. **GitHub Pages is never mentioned.** A repository with Pages off serves
   nothing, so a stranger can finish setup, publish, and have no site. Setup
   checks the repository (`publisher.root_entries`) and never Pages.
3. **The address is typed by hand.** `site_address` is an answer on the form,
   though GitHub knows it once Pages is on. A wrong address breaks every link
   the Builder writes from it.
4. **One form cannot be resumed.** Making an account and a key on GitHub takes
   time away from Pressless. If the page is closed, everything typed is lost.
   GitHub shows a new key only once, so a lost key means making another.

## 3. Scope decisions (agreed with the user)

1. **Pressless does not create the repository.** Decided by the user
   2026-10-03 (PRESS-0212). It gives exact clicks and checks each step itself.
   *PRESS-0231 § 3 decision 2 overturns this for a copy carrying a
   registered GitHub App.*
2. **Setup is the first wizard, and the pattern is shared.** Decided by the
   user 2026-10-03 (PRESS-0220): one step per screen, Back and Next, which
   step of how many, a check before Next where a step can be checked, and
   leaving halfway keeps what was done.
3. **(decided here) Pressless switches Pages on itself.** The key the wizard
   asks for carries Pages permission as well as Contents, on that one
   repository only. This widens PRESS-0212's "the publishing key stays limited
   to one site's contents" to that one site's contents *and its Pages
   switch*. It still cannot reach another repository, create one or delete
   one. A key that can already replace every file on the site gains little
   power from switching Pages on. It saves the stranger a trip through
   GitHub's settings, and PRESS-0222's own-domain wizard needs the same
   permission.
4. **(decided here) Setup may write to GitHub when Pages is off: an empty
   `.nojekyll` file, then the Pages switch.** This overturns PRESS-0127 § 3
   decision 2, "Setup keeps reading GitHub and never writing to it", for
   these two requests. `.nojekyll` makes Pages serve files as they are:
   Pages' default build drops any name starting with `_`, and
   `photographs.name_for("_DSC1234.JPG", "JPEG")` returns `_dsc1234.jpg`.
   On an empty repository it is also the first commit, which Pages needs, so
   PRESS-0127 § 3 decision 1 holds: the person adds no file by hand. It is a
   root entry the Builder does not produce, so the untouchable list keeps it.
   A wizard abandoned after these writes leaves Pages on, which is what the
   person was setting up anyway.
5. **(decided here) The key is stored as soon as GitHub accepts it.** It is
   not kept until the end of the wizard. GitHub shows a new key once, so
   holding it only in memory would lose it on a quit. It is never in the
   progress file (§ 4.2).
6. **(decided here) The wizard asks only what a new site needs.** The Daily
   Prompt filter and Google's measurement id are not asked on first run. Both
   stay on Settings. This overturns PRESS-0021 § 3 decision 10's "First run
   offers an empty box"; first run saves `""` and `None`, as an empty box did.
7. **(decided here) The welcome step recommends naming the repository
   `<account>.github.io`.** That gives the shortest address. Any other name
   works and gives `https://<account>.github.io/<name>/`. The step says both.
8. **(decided here) The manual link waits for the manual.** PRESS-0220 says
   each step links to its manual page. PRESS-0219 has not built the manual,
   so this spec adds no link. PRESS-0219 adds one per step.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

*PRESS-0213 § 4.6 changes the *site* step.*

### 4.1 The wizard pattern (PRESS-0220)

A new module, in the Face (`docs/design.md` rule 1).

```python
# src/pressless/wizard.py

Answers = dict[str, str]

@dataclass(frozen=True)
class Hint:               # a refused answer: shown beside its field
    field: str            # "" when the step has no field it is about
    text: str

@dataclass(frozen=True)
class Stop:               # a failure fragment, from Face.fail: shown above the step
    fragment: str

@dataclass(frozen=True)
class Done:               # the wizard is finished: show this, forget the progress
    fragment: str

@dataclass(frozen=True)
class Step:
    name: str                                    # stable; the progress file names it
    title: str
    fields: tuple[str, ...]                      # the answers this step's form posts
    show: Callable[[Answers, Hint | None], str]  # the step's body, fields filled from Answers
    check: Callable[[Answers], Answers | Hint | Stop | Done] | None = None

class Wizard:
    def __init__(self, name: str, steps: Sequence[Step], folder: Path) -> None: ...
    def page(self, face: Face, request: Request) -> str: ...
```

`Wizard.page` serves both the GET and the POST of one address, which its
owner registers with `Face.add_page` (PRESS-0021 INV-14).

- **GET** shows the step the progress file names, with its answers filled
  in. No file, an unreadable one, or a step name the wizard does not have:
  the first step, with no answers.
- **POST** carries `step`, the step's fields, and `go`, either `next` or
  `back`. A `step` that is not the current one is answered with the current
  step and changes nothing, so a stale tab cannot skip a check.
- **Back** moves to the previous step and keeps the answers as they were
  before this step's form. It runs no check and writes nothing but the
  progress file.
- **Next** merges the posted fields into the answers and runs the step's
  `check`. A step with no check advances. A check's result:
  - `Answers`: they replace the answers, the progress file is written, and
    the next step is shown.
  - `Hint`: the same step again, with the posted answers and the hint. The
    progress file is not written. A hint whose `field` is not one of the
    step's fields is shown above them.
  - `Stop`: the fragment above the same step. The progress file is not
    written.
  - `Done`: the progress file is removed and the fragment is the page.
- **Every step's page** has the step's title, "Step *n* of *N*" where *N*
  counts the steps, Next, and Back on every step but the first. A step's
  fields keep their posted values across a `Hint`, except a field whose name
  ends in `key`, which is never filled in.

### 4.2 The progress file

`<folder>/wizards/<name>.json`, where `folder` is Pressless's own folder.
Written whole with `safe_write.write_whole`, under a lock held by the
`Wizard`, so two tabs cannot interleave.

```json
{"version": 1, "step": "repository", "answers": {"account": "...", "repository": "..."}}
```

- **It never holds a field whose name ends in `key`.** The wizard drops those
  from the answers before writing. A step that needs a secret kept stores it
  itself, through Credentials (§ 4.4 step *key*).
- **It is a convenience, never a record.** A file that will not read as this
  shape is treated as absent. Nothing else reads it.
- **`Done` removes it.** A failure to remove it is logged, not shown: the
  next GET of a finished setup shows Settings regardless (§ 4.3).

### 4.3 Which page `/setup` shows

PRESS-0021 § 4.2's table changes in its first two rows only:

| Outcome | What `/setup` does |
|---|---|
| `NotSetUp` | **first run**: the setup wizard |
| `SettingsError` whose `key` is `site_folder` | **first run**: the setup wizard |
| any other `SettingsError` | unchanged |
| a `Settings` | **Settings**: unchanged, the one form |

The wizard is served at `/setup` itself on first run, GET and POST, so
`__main__`'s launch link is unchanged. A POST to `/setup` once a settings
file loads is the Settings form, as today. The first-run form of PRESS-0021
§ 4.3 is gone.

### 4.4 The setup wizard's steps

*PRESS-0231 § 4.3: where `github_signin.available()`, the steps are that
section's.*

Every GitHub request goes through the Publisher (`docs/design.md` rule 5).
The words on each step are the implementer's, except where a sentence is
quoted. Instructions name GitHub's own button and menu words, so a person can
follow them on GitHub's pages.

| Step | Fields | What it shows | Its check |
|---|---|---|---|
| *welcome* | none | what the wizard does, what is needed (an email address), and that it can be left and resumed | none |
| *account* | `account` | how to make a free GitHub account, step by step, with the sign-up link | `publisher.account_exists(account)` |
| *repository* | `repository` | how to make a **Public** repository, and the naming advice of § 3 decision 7 | `publisher.public_repository("account/repository")` |
| *key* | `key` | how to make a fine-grained key: only that repository; Contents, Pages and Administration **Read and write** | the key sequence below |
| *pages* | none | whether Pages is on, and the address | the Pages sequence below |
| *site* | `site_name`, `start` | the site's name, the address found, and PRESS-0126's starter box where it is offered | the save sequence below |

After *site*, `Done` shows PRESS-0021's done page, which ends with
PRESS-0183's shortcut boxes. That is the wizard's last screen.

**account.** A name GitHub does not know is a `Hint`: "GitHub has no
account by that name. Check the spelling, or finish making it first." The
read is unauthenticated: there is no key yet.

**repository.** The answer is the repository's name alone; the wizard joins
it to `account`. A repository GitHub does not show to an unauthenticated read
is a `Hint` saying it may be misspelled or Private, and that it must be
Public. GitHub answers 404 to both, and the hint covers both. The joined
`owner/name` must pass `settings.check`'s repository rule, or the hint is
PRESS-0021's.

**key.** In this order, each only when the one before succeeded:

1. **The box.** Empty, where the answers already hold `store`: an earlier
   pass through this step stored a key, and the empty box keeps it. The key
   in hand is then `credentials.read(store, folder, GITHUB_ACCOUNT)`, and
   sub-step 4 does not run. Empty otherwise: a `Hint`, as on PRESS-0021's
   first run. Typed: PRESS-0021 § 4.4's key shape rule, and a malformed key
   is a `Hint` before any request (PRESS-0021 INV-12).
2. `publisher.root_entries(candidate, key)`. A `RemoteStateMissing` is a
   `Hint` on `key`, saying this key cannot reach that repository. Any other
   `PublishError` is a `Stop` through `Face.fail`.
3. `publisher.pages(repository, key)`. A refusal (401 or 403) is a `Hint`
   saying the key lacks Pages permission and how to edit it on GitHub.
4. Only for a key typed in the box: `credentials.choose()` where the
   answers hold no `store` yet, then `credentials.write(store, folder,
   GITHUB_ACCOUNT, key)`. A credential failure is a `Stop` with
   `secret=KEY` (PRESS-0021 INV-13); `NoStore` says setup cannot finish on
   this computer, as today.
5. Where `choose` ran, the answers gain `store` (the `Choice.store`) and
   `store_name` (`Choice.name`) for the done page.

**pages.** It reads the key back with `credentials.read(store, folder,
GITHUB_ACCOUNT)`, then `publisher.pages(repository, key)`. Its hints have no
field (§ 4.1).

- **On, serving the default branch's root by a branch build**: Pages is left
  as GitHub has it. No write is sent.
- **On, serving anything else** — another branch, `/docs`, or a workflow
  build: a `Hint` saying this repository already puts a site on the web
  another way, and to go Back and choose another repository (PRESS-0229).
  Pressless publishes to the default branch's root and nowhere else, so it
  cannot publish there. It never changes Pages, and never tells him to:
  re-pointing it would take the site already there offline.
- **Off**: `publisher.switch_pages_on(repository, key)`. A `Refused` is a
  `Hint` saying the key lacks Pages or Administration **write**, and how to
  edit it.
- Any other `PublishError` is a `Stop` through `Face.fail`.

Pages on, the answers gain `site_address`, GitHub's `html_url`. It must pass
`settings.check`'s address rule, or it is a `Stop`: it is GitHub's value, not
an answer he can correct.

**site.** PRESS-0021 § 4.6 runs from step 2 to step 5, then the
PRESS-0126 fill and the done page, exactly as `_submit` does today, with
three differences:

- the key in hand is `credentials.read`, as on the *pages* step;
- step 3 is skipped: the store was chosen on the *key* step, and the
  candidate carries it;
- step 4 is skipped: the key is already stored.

The candidate is PRESS-0021 § 4.5's first-run column, with `repository`,
`site_name` and `site_address` from the answers, `daily_prompt_filter` `""`
and `measurement_id` `None`. A refused `site_name` is a `Hint`. A save
failure is a `Stop`. Success is `Done`.

### 4.5 The Publisher's additions

```python
# src/pressless/publisher.py — added

@dataclass(frozen=True)
class Pages:
    on: bool
    address: str | None       # GitHub's html_url while on
    serves_root: bool         # a branch build of the default branch's "/"

def account_exists(account: str, transport: Transport | None = None) -> bool: ...
def public_repository(repository: str, transport: Transport | None = None) -> bool: ...
def pages(repository: str, token: str, transport: Transport | None = None) -> Pages: ...
def switch_pages_on(repository: str, token: str,
                    transport: Transport | None = None) -> Pages: ...
```

- `account_exists` reads `GET /users/{account}`; `public_repository` reads
  `GET /repos/{owner}/{name}`. Both send no `Authorization` header. A 404 is
  `False`. Every other answer keeps § 6's types of PRESS-0009.
- `pages` reads `GET /repos/{owner}/{name}/pages`. 404 is `Pages(False,
  None)`.
- `serves_root` holds when the answer's `build_type` is `legacy` (or
  absent), `source.path` is `/`, and `source.branch` is the default branch
  `_default_branch` resolves.
- `switch_pages_on`, in order:
  1. Unless the root already holds `.nojekyll` (`root_entries`), writes it
     empty with `PUT contents/.nojekyll`. On an empty repository this is the
     first commit, as PRESS-0127's start file is: `root_entries` answers
     `()` there, so it is written. The write goes through `_Session.write`
     with `outcome_unknown=True`, as the start file's does.
  2. Sends `POST /repos/{owner}/{name}/pages` with `{"build_type": "legacy",
     "source": {"branch": <default branch>, "path": "/"}}`, the branch read
     after step 1 so an empty repository has one.
  3. Returns `pages(...)`.
- **The account name never reaches a message.** `_without_account` takes the
  account out of `repos/<account>/<name>` only; it gains the same for
  `users/<account>`, so a failure of `account_exists` names no account
  (`docs/design.md` § Logging).

GitHub's documentation for these: Pages read needs the fine-grained
permission Pages read, and `POST .../pages` needs both Pages write and
Administration write (PRESS-0230: a key without Administration was refused
in the 2026-10-05 by-hand run).
Source: https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens

**Why `.nojekyll`.** A branch build runs Jekyll unless the root holds
`.nojekyll`, and Jekyll leaves out a name starting with `_`. Pressless keeps
`_DSC1234.JPG` as `_dsc1234.jpg`, so without it such photographs vanish from
the site.
Source: https://github.blog/news-insights/the-library/bypassing-jekyll-on-github-pages

## 5. Invariants

Tests run the page through `face.serve(tmp_path)` with a fake Publisher
transport and the recording Credentials doubles `tests/test_setup.py`
already uses. The wizard tests are in `tests/test_wizard.py`; the setup ones
in `tests/test_setup.py`; the Publisher ones in `tests/test_publisher.py`.

- **INV-1** — One step per screen. Each page carries one step's fields,
  "Step *n* of *N*", Next, and Back on every step but the first.
  *Test:* `test_each_screen_is_one_step`, walking a three-step wizard with no
  checks forward and back, asserting the fields, the counter and the buttons
  on each page.
  *Breaks when:* a page shows two steps' fields, the counter counts the done
  screen, or the first step offers Back.

- **INV-2** — A refused check does not advance or write. On `Hint` or `Stop`
  the same step is shown and the progress file is byte-identical to before.
  *Test:* `test_a_refused_check_stays_put`, with a check answering `Hint`
  then `Stop`, comparing the file's bytes before and after each.
  *Breaks when:* the wizard writes the posted answers before running the
  check, or moves on after a `Hint`.

- **INV-3** — Leaving keeps what was done. A second `Wizard` over the same
  folder, as after a relaunch, shows the step reached with its answers.
  *Test:* `test_a_new_launch_resumes`, advancing two steps, building a fresh
  `Wizard` and `Face`, and GETting.
  *Breaks when:* progress lives only in memory, or GET always starts at the
  first step.

- **INV-4** — A stale POST changes nothing. A POST naming a step that is not
  the current one shows the current step and runs no check.
  *Test:* `test_a_stale_tab_cannot_skip_a_check`, posting `go=next` for an
  earlier step with a recording check.
  *Breaks when:* the wizard trusts the posted `step` and runs or skips a
  check from it.

- **INV-5** — The progress file never holds a key. After the setup wizard's
  *key* step succeeds, no file under `folder/wizards` contains the key's
  bytes, and no answer named `key` is in it.
  *Test:* `test_the_key_never_reaches_the_progress_file`, with a key of
  plain words, so the push gate's secret scanner does not mistake it.
  *Breaks when:* the wizard writes every posted field, or a step stores the
  key in its answers.

- **INV-6** — The key is stored only after GitHub has answered, and
  `choose` runs once. A key refused at sub-steps 1 to 3 of *key* leaves no
  stored key and no call to `choose`. A key accepted is stored, and the
  *site* step never calls `choose` or `write`.
  *Test:* `test_the_key_is_stored_once_github_answers`, posting a malformed
  key, then one GitHub answers 401, then one whose Pages read answers 403,
  then a good one; then finishing.
  *Breaks when:* `write` moves ahead of `root_entries` or `pages`, or the
  save sequence keeps step 3 or 4 of PRESS-0021 § 4.6.

- **INV-7** — No settings file exists until the *site* step succeeds, and a
  failed save leaves first run where it was. PRESS-0021 INV-2, carried.
  *Test:* `test_settings_are_written_last_by_the_wizard`, checking for the
  file after every step, and making `settings.save` fail on *site*.
  *Breaks when:* any earlier step saves a partial `Settings`.

- **INV-8** — Pages is switched on only when it is off. On and serving the
  default branch's root, no write is sent and the address is GitHub's. On
  and serving anything else, no write is sent and the step does not advance.
  *Test:* `test_pages_is_left_as_github_has_it`, with the fake transport
  recording methods: Pages off, on at the root, and on from `/docs`.
  *Breaks when:* the step always POSTs, overwrites an existing Pages source,
  or accepts a site served from somewhere Pressless does not publish.

- **INV-9** — Setup's GitHub writes are `PUT contents/.nojekyll`, only
  where the root lacks it, and then `POST .../pages`, both only when Pages is
  off. An empty repository gets both, in that order.
  *Test:* `test_setup_writes_only_what_pages_needs`, walking the whole wizard
  against the recording transport, once over a repository with a root and
  once over an empty one, asserting every non-GET request's method and path.
  *Breaks when:* a step writes another file, a branch or a setting, or sends
  the switch before the empty repository has its first commit.

- **INV-10** — The account and repository checks send no key.
  *Test:* `test_the_first_reads_carry_no_key` in `tests/test_publisher.py`,
  asserting no `Authorization` header on `account_exists` and
  `public_repository`.
  *Breaks when:* they reuse an authenticated session.

- **INV-11** — Finishing forgets the progress and hands over to Settings.
  After `Done`, the progress file is gone and a GET of `/setup` shows the
  Settings form.
  *Test:* `test_a_finished_setup_shows_settings`.
  *Breaks when:* `Done` leaves the file, or `/setup` checks the progress
  file before `settings.load`.

- **INV-12** — The wizard sits behind the Face's boundary. PRESS-0021
  INV-14, carried to the wizard's POST.
  *Test:* `test_the_wizard_sits_behind_the_faces_boundary`, posting `go=next`
  on *account* with no cookie and with a foreign `Origin` (403 both, no
  progress file), then with both (advances).
  *Breaks when:* the wizard is served by its own handler.

## 6. Failure modes

| What fails | What he sees | What is kept |
|---|---|---|
| No internet on *account* or *repository* | `Face.fail`'s sentence for `Unreachable` | the step, unadvanced |
| GitHub rate-limits the unauthenticated reads | `Face.fail`'s `RateLimited` sentence | the step |
| The key's store refuses | PRESS-0021 INV-13's sentence | everything before *key* |
| Pages switch refused (a key without Pages write) | a hint on *pages* saying how to add the permission | the stored key |
| Pages on, serving another branch, `/docs` or a workflow | a hint on *pages* saying how to set it | the stored key |
| The `.nojekyll` write's answer is unreadable or lost | `Face.fail`'s `OutcomeUnknown` sentence; Next tries again, and finds the file if it landed | the stored key |
| The progress file cannot be written | `Face.fail`'s sentence for the write's `OSError` | the step, unadvanced |
| Pressless is closed on any step | nothing; the next launch resumes | everything up to the last Next |
| He renames the repository on GitHub mid-wizard | the *key* or *pages* check fails with its hint; Back to *repository* | the earlier answers |

## 7. Tests

The tests of § 5, each written first and seen to fail against today's code:
INV-1, INV-2, INV-3 and INV-4 in `tests/test_wizard.py`; INV-5, INV-6,
INV-7, INV-8, INV-9, INV-11 and INV-12 in `tests/test_setup.py`; INV-10 in
`tests/test_publisher.py`.

PRESS-0021's first-run tests post the one form. They are re-pointed to walk
the wizard, keeping the invariant each one locks.

**By hand, before release:** the whole wizard against a new GitHub account's
new Public repository, once on Linux and once on the Windows box, ending with
a publish whose page answers at the address the wizard found. CI cannot reach
GitHub.

## 8. Alternatives considered (and rejected)

- **Pressless creates the repository.** Rejected by the user (§ 3 decision
  1): it needs a key that can also delete repositories.
- **The person switches Pages on by hand.** Rejected (§ 3 decision 3): more
  steps through GitHub's settings for a stranger, and PRESS-0222 needs the
  permission anyway.
- **Keep the key in memory until the end.** Rejected (§ 3 decision 5): a quit
  loses a key GitHub will not show again.
- **Save a partial `Settings` as progress.** Rejected: the settings file is
  what makes a machine set up (PRESS-0021 § 4.6), and every other part reads
  it. A partial one would tell them setup was done.
- **Carry the answers in hidden form fields.** Rejected: nothing survives a
  closed tab.
- **Keep the one-page form beside the wizard for first run.** Rejected: two
  first-run paths, one of them shown to nobody.

## 9. Out of scope

- The site's identity: a short description, an icon, a sharing picture —
  PRESS-0213 adds them to the *site* step.
- A link from each step to the manual — PRESS-0219.
- The other wizards — Google sign-in and counting (PRESS-0199, PRESS-0122),
  Import (PRESS-0125), moving and backups (PRESS-0221), an own domain
  (PRESS-0222).
- Several sites in one Pressless — PRESS-0223, which will change where the
  progress file and the key are filed.
- Settings as a wizard. Settings stays one page.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_wizard.py::test_each_screen_is_one_step` |
| INV-2 | `tests/test_wizard.py::test_a_refused_check_stays_put` |
| INV-3 | `tests/test_wizard.py::test_a_new_launch_resumes` |
| INV-4 | `tests/test_wizard.py::test_a_stale_tab_cannot_skip_a_check` |
| INV-5 | `tests/test_setup.py::test_the_key_never_reaches_the_progress_file` |
| INV-6 | `tests/test_setup.py::test_the_key_is_stored_once_github_answers` |
| INV-7 | `tests/test_setup.py::test_settings_are_written_last_by_the_wizard` |
| INV-8 | `tests/test_setup.py::test_pages_is_left_as_github_has_it` |
| INV-9 | `tests/test_setup.py::test_setup_writes_only_what_pages_needs` |
| INV-10 | `tests/test_publisher.py::test_the_first_reads_carry_no_key` |
| INV-11 | `tests/test_setup.py::test_a_finished_setup_shows_settings` |
| INV-12 | `tests/test_setup.py::test_the_wizard_sits_behind_the_faces_boundary` |
| § 4.5 GitHub's real answers to the four new requests | **nothing** in CI — the by-hand run of § 7 |
| § 4.4 the instructions match GitHub's pages | **nothing** — read by hand in § 7's run; GitHub changes its pages without notice |

## 11. Cross-doc impact

Each spec edit is a pointer to this spec beside the clause it changes.

- `docs/specs/PRESS-0021-setup.md` § 3 decisions 2 and 10 — first run is the
  wizard and asks neither the filter nor the address. § 4.2 — the first two
  rows. § 4.3 — the form is Settings only. § 4.6 — on first run, steps 3
  and 4 move to the wizard's *key* step. § 4.9 — where Pages is off,
  first-run setup writes `.nojekyll` and switches Pages on.
- `docs/specs/PRESS-0127-empty-repository.md` § 3 decisions 2 and 3, and
  INV-9 — first-run setup starts an empty repository with `.nojekyll`; INV-9
  now holds for Settings only, and its test moves to Settings.
- `docs/design.md` § The parts, the Publisher row — it also reads whether an
  account and a public repository exist, and switches Pages on.
  § Where everything sits on disk — the `wizards` folder.
- `README.md` § Getting started — after the download, Pressless walks them
  through GitHub.
- `CHANGELOG.md` — one line under Added.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0212-setup-wizard-loop-log.md`.
