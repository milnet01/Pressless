# PRESS-0015 — Undo: one step back, ending with the site and his files agreeing

**Status:** spec draft (2026-09-21).
**Kind:** implement.
**Source:** ROADMAP PRESS-0015 (`docs/design.md` § What undo actually does;
discovery S9).

**Blocked by:** PRESS-0010, PRESS-0013 — both shipped.
**Pairs with:** PRESS-0128.

Layman: after a change that made his site wrong, one press puts the site back
the way it was — and puts his own files back to match, so the next publish
does not put the trouble straight back.

## 1. Goal

After this ships, a press of **Undo the last publish** fetches the state
before the last publish, writes its `content/` back into the Store, rebuilds
and publishes. The site and his own files then agree. Nothing of his is
deleted: an entry the fetched state does not hold becomes a draft, and a
version of his that undo writes over is kept beside it. A definite failure
puts his files back as they were before the press.

## 2. Problem

1. **Nothing reaches back.** `publisher.fetch_previous` writes a previous
   state into a folder it is handed and stops there. No page calls it, and
   nothing copies from that folder into the Store.
2. **A revert alone is not S9.** The Store would still hold the text that
   caused the trouble, so his next publish would put it back. The site would
   be right for an hour and wrong again without him doing anything wrong.
3. **A demoted entry would be re-dated.** `publishing._move` sets a
   published draft's `Date` to `_now()` for every draft that is not a working
   copy. An entry undo turns back into a draft goes through that branch when
   he publishes it again. PRESS-0012 § 3 decision 6 leaves the marker to this
   item.
4. **A waiting working copy would be orphaned.** `publishing._move` treats a
   draft as a working copy only where its `Replaces` names a **published**
   entry — `editor._replaced` applies the same test. Once undo demotes the
   entry, the copy stops being recognised and would publish under its own
   address.
5. **The first publish has nothing before it.** The state before it holds no
   `content/`, so undoing it would demote every imported entry at once.

## 3. Scope decisions (agreed with the user)

1. **A definite failure puts his files back; an unknown outcome stays
   undone.** Decided by the user 2026-09-19. The same split `publishing.publish`
   already makes (PRESS-0013 § 4.3).
2. **Undo is offered beside the Published message on the editor page, and as
   "Undo the last publish" on the front page.** Decided by the user
   2026-09-19.
3. **The button always shows, and nothing asks GitHub before showing it.**
   Decided by the user 2026-09-19. After a first publish, pressing it changes
   nothing and says why in one sentence.
4. **A saved working copy of an entry undo demotes is kept, and publishing it
   later puts the entry back with his changes.** Decided by the user
   2026-09-19.
5. **His first publish cannot be undone.** Decided by the user 2026-09-11. The
   state before it is what the sibling generator built and holds no `content/`.
   The maintainer is on hand for that first publish instead.
6. **Undo goes plain one step back, and is a toggle.** Decided by the user
   2026-08-26 (PRESS-0009 § 3 decision 1). Pressing it twice returns the state
   the first press replaced.
7. **(decided here) A version of his that undo writes over becomes an
   ordinary draft, not a working copy.** Decided by the user 2026-09-21. A
   working copy would make the press reversible in one click, and an entry may
   already have one — two drafts naming one entry is `editor.TooManyCopies`,
   which refuses to open it until he moves one out by hand. § 8 records the
   rejected option.
8. **(decided here) An entry's comments stay filed under its address.**
   Decided by the user 2026-09-21. A demoted entry's comments are not built,
   because the Builder writes `content/comments/<slug>.json` for published
   entries only (PRESS-0008 § 4.7); publish it again and they return.
9. **(decided here) Publishing honours a copy of a demoted entry, and neither
   page says anything about demoted entries.** Decided by the user 2026-09-21.
   Decision 4 is met in `publishing._move` alone. The list and the edit page
   keep today's wording about working copies, which talks about published
   entries. **Both pages still gain decision 2's Undo button** (§ 4.6); that is
   the only change either one takes.
10. **(decided here) The sequence lives in the Face, as
    `src/pressless/undo.py`.** Only the Face knows the order (`docs/design.md`
    rule 1), and only the Face may copy from the fetch area into the Store
    (rule 5). It is its own module rather than more of `publishing.py`, which
    it calls.
11. **(decided here) Undo writes into the Store through the Store's own
    calls**, never by copying bytes. § 8 records why.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 The public surface

```python
# src/pressless/undo.py

FETCH_FOLDER = "fetch"      # inside Pressless's own folder; emptied when the sequence ends
CONTENT = "content/"        # the prefix fetched (PRESS-0008 § 4.7)
KEPT_SUFFIX = "-before-undo"

class NothingToUndo(Exception): ...   # the state before holds no content/ (§ 3 decision 5)

@dataclass(frozen=True)
class Undone:
    outcome: publisher.Outcome
    restored: tuple[str, ...]  # addresses the fetched state put back
    demoted: tuple[str, ...]   # entries turned back into drafts
    kept: tuple[str, ...]      # addresses his own versions were kept under

def undo(folder: Path, settings: Settings, key: str, *,
         capture: Callable[[], ContextManager[list[str]]] = _nothing_captured,
         notices: list[str] | None = None,
         transport: publisher.Transport | None = None) -> Undone: ...

def register(face: Face, folder: Path, *,
             transport: publisher.Transport | None = None) -> None: ...
```

```python
# src/pressless/publishing.py — added

UNDONE = "Undone"    # the header marking a draft undo demoted; § 4.5
```

`undo` is § 4.3's sequence. `notices` carries PRESS-0013 § 4.1's meaning
unchanged, and `undo` passes both it and `capture` to `publishing.publish`.
`register` adds `POST /undo`.

**`capture` wraps steps 4 and 5 — the read and the reconcile — and nothing
else.** The reconcile writes many files, and PRESS-0005 § 4.1 emits a
`StoreNotice` only a capturing caller sees, so those have to be inside one. The
fetch is outside it for the reason PRESS-0013 § 4.1 gives about the upload: a
capture holds a process-wide lock (PRESS-0011 § 4.4), and a fetch is minutes
long, so one around it would stall setup's page. `publishing.publish` then
applies `capture` to its own steps as it already does.

**`undo.register` is called from `pressless.__main__`**, beside
`setup.register`, `editor.register` and `publishing.register` (PRESS-0013
§ 4.5 step 3). Without that line `POST /undo` is never added and no button can
reach it.

`undo.py` adds `NothingToUndo`'s sentence to `face.SENTENCES` when it is
imported, as `publishing.py` and `editor.py` do.

### 4.2 The route

`POST /undo` takes no fields. It runs under `editor.LOCK`, held for the whole
sequence, so a save in another window cannot meet a Store write half way
through. In order:

1. **Settings.** `settings.load(folder)`.
2. **The key.** `credentials.read(store, folder, github_account)`.
3. **Undo.** `undo(folder, settings, key, capture=face.capture,
   notices=<the reply's list>, transport=…)`.

Steps 1 and 2 run inside `face.capture()`; step 3 passes it on. A failure at
any step answers status 200 rather than an error status, so the page can render
the failure beside what it already shows:

```json
{"undone": false, "failure": "<fragment>", "notices": "<fragment>",
 "summary": null}
```

Success answers `"undone": true`, `"failure": null`, and a `summary` fragment
naming what changed: `restored`, `demoted` and `kept`, one clause each.
**The page reloads on success only**, on both pages, because either may now be
showing an entry whose state changed. **A failure does not reload** — the
`failure` and `notices` fragments stay on screen, or he never reads why the
undo stopped.

### 4.3 The sequence

`undo` runs these in order. Each step runs only if the one before it
succeeded.

1. **Empty the fetch area.** Remove `folder/FETCH_FOLDER` and recreate it.
   PRESS-0009 § 4.5 leaves a residual window in which a failed fetch leaves
   the folder part old and part new, and says this item must not be built
   assuming otherwise. Undo therefore never reads a fetch area it did not
   just create.
2. **Fetch.** `publisher.fetch_previous(settings, key, folder / FETCH_FOLDER,
   CONTENT, transport)`. `NoPreviousState` where the current commit has no
   parent. Any `publisher.PublishError` here is raised with the Store
   untouched.
3. **Refuse a first publish.** `NothingToUndo` where `Fetched.paths` is empty
   — the state before holds no `content/` (§ 3 decision 5).
4. **Read the whole fetched state, before writing anything.** Every fetched
   file is read through the Store's own reader for its kind (§ 4.4). A file
   the Store cannot read raises here, with the Store untouched.
5. **Reconcile the Store** (§ 4.4), recording a reversal for every change.
   **Each reversal carries the value the reconcile read before it wrote** —
   which it already holds, since reading it is how it decided the file
   differs — and puts that value back through the Store's own writer. **A
   reversal never bins a file it is putting back**, because nothing moves a
   file out of the bin and `store.move_to_bin` stamps to the second, so
   binning one path twice inside a second is refused and would replace the
   failure being reported. A file the forward pass binned stays binned, as a
   spare copy of what is now back in place. **The one thing a reversal does
   bin is a file the reconcile itself created** — a kept draft — since that is
   the only removal the Store offers, and it is a path the forward pass never
   binned.
6. **Publish.** `publishing.publish(folder, settings, key, entry=None,
   emptying=True, capture=capture, notices=notices, transport=transport)`.
   `emptying=True` because undo's publish is the result that was asked for
   (`docs/design.md` rule 9, PRESS-0013 § 4.1).
7. **Finish.** Empty the fetch area.

**A definite failure at step 6 runs the reversals in reverse order, then
raises it** (§ 3 decision 1). A definite failure is any exception but
`publisher.OutcomeUnknown`. **An `OutcomeUnknown` leaves the Store as undo
made it** and is raised after step 7: GitHub may have taken the change, and
his files must not disagree with a site that may already show the older state.

**A failure while reversing is raised in place of the original**, so he is
told something is wrong with his files rather than only with GitHub.

**Step 7 runs however the sequence ends** — success, definite failure, or
unknown outcome. The fetch area is the Publisher's scratch space, never a
record.

### 4.4 Reconciling the Store

The fetched state's layout is PRESS-0008 § 4.7's, at the Store's own relative
paths. Each kind is read and written through the Store's own calls:

| Fetched path | Read with | Written with |
|---|---|---|
| `content/published/<slug>.txt` | `store.read` | `store.write(…, draft=False)` |
| `content/comments/<slug>.json` | `store.read_comments` | `store.write_comments` |
| `content/pages/<name>.html` | `store.read_html` | `store.write_html(…, "pages", …)` |
| `content/furniture/<name>.html` | `store.read_html` | `store.write_html(…, "furniture", …)` |
| `content/templates/<name>.txt` | `store.read` | `store.write_template` |

**Differs** means differs as the Store holds it — the value its reader
returns, not the bytes. `store.Entry` and `store.Comment` are frozen
dataclasses, so each compares by value.

**Entries the fetched state holds:**

- **The Store publishes it and it does not differ.** Nothing.
- **The Store publishes it and it differs.** His version is written as a draft
  under `editor.free_address(folder, slug + KEPT_SUFFIX)`, carrying no
  `Replaces` field (§ 3 decision 7). Then the fetched entry is written as
  published.
- **A draft holds that slug.** His draft is written under
  `editor.free_address(folder, slug + KEPT_SUFFIX)`, **keeping its own fields**
  — so a draft that was a working copy of some other entry stays one — and the
  old draft file is binned. Then the fetched entry is written as published.
  Otherwise one slug would name two files, which `docs/design.md` rules out.
- **The Store holds neither.** The fetched entry is written as published.

**An entry the Store publishes and the fetched state does not hold** is
demoted: `store.unpublish(folder, slug)`, then written back as a draft
carrying `publishing.UNDONE` (§ 4.5).

**Every other kind the fetched state holds** is written where it differs or is
absent, the superseded version going to the bin first with
`store.move_to_bin`.

**Every file the fetched state does not hold, other than an entry, is kept
untouched.** `docs/design.md` says so, and adds the consequence: being kept,
it is built and published again, so an undo removes nothing of his from the
Store.

**Photograph originals are never touched.** They never reach the site folder,
so the fetched state cannot hold one.

**Comments are not moved with a demoted entry** (§ 3 decision 8). The comments
folder is not split into published and draft, so there is nowhere for a
demotion to move the file to, and the Builder already holds a draft's comments
back. **This narrows `docs/design.md`**, which says an entry's comments file
follows its entry *demoted*, published, binned or renamed with it; § 11 carries
the amendment that document is owed.

### 4.5 The demotion mark

A demoted draft carries one extra header field:

```
Undone: 2026-09-21 14:02:11
```

`publishing.UNDONE` is the field name. **Nothing parses the value** — it is
the moment of the demotion, written so that a person reading his own file can
see what happened. Presence is what is read.

Two changes to `publishing._move` follow, and nothing else about it changes:

1. **A draft carrying `UNDONE` keeps its `Date` when published**, and the
   field is stripped along with `Replaces`. Without this, § 2 item 3's branch
   dates it again and an entry from years ago arrives at the top of his site.
2. **A draft whose `Replaces` names a draft carrying `UNDONE` is a working
   copy of it** (§ 3 decision 4). It is published under that address with the
   demoted draft's date, both fields stripped; the demoted draft is binned at
   the finish step, beside the copy.

**The mark is what makes the second change safe.** Without it, any draft whose
`Replaces` named another draft would publish over it, and a `Replaces` field
left on an ordinary draft — which PRESS-0013 § 4.3 already guards against on
the way in — would destroy an unrelated draft.

`_Moved.copy` becomes the paths to bin at the finish step rather than one
path, so both files go. A failure there still never replaces the publish's
result (PRESS-0013 § 4.3 step 5).

**The put-back for the demoted-copy branch is `store.move_to_bin` on the file
it wrote**, because nothing else removes a file the Store did not hold before.
His two drafts are left as they were, and the bin keeps the copy undo wrote.

### 4.6 The pages

**The front page** (`editor._list`) gains an **Undo the last publish** button.
It always shows (§ 3 decision 3).

**The editor page** gains the same button beside the Published message its
script shows after a publish (PRESS-0013 § 4.4).

Both post `/undo`, disable the button, and show *"Putting your site back…
this can take a few minutes. Keep this page open."* On a JSON reply they show
the failure and stay, or show the summary and reload (§ 4.2).

### 4.7 What this item never does

- It never deletes anything of his. Every removal is `store.move_to_bin`.
- It never reaches back more than one publish.
- It never touches a draft the fetched state does not publish.
- It never touches a photograph original.
- It never writes into the Store by copying bytes.
- It never asks GitHub anything before the button is pressed.

## 5. Invariants

The tests below are in `tests/test_undo.py` unless named otherwise. The
Publisher is reached through a fake `Transport`, as `tests/test_publisher.py`
does, and Credentials through a recording double, as `tests/test_setup.py`
does.

- **INV-1** — Undo empties the fetch area before fetching, and empties it
  again however the sequence ends.
  *Test:* `test_the_fetch_area_is_emptied_at_both_ends`. A stray file is
  placed in the fetch area; after a successful undo, after a definite failure
  and after an unknown outcome, the folder holds nothing and the stray file is
  gone.
  *Breaks when:* the folder is reused, or emptied only on success — the state
  PRESS-0009 § 4.5 says this item must not assume away.

- **INV-2** — An entry the fetched state does not hold becomes a draft and is
  not deleted.
  *Test:* `test_an_entry_the_previous_state_lacks_becomes_a_draft`. The entry
  is in `drafts/`, reads back through `store.read` with its body unchanged, and
  `published/` no longer holds it.
  *Breaks when:* the entry is binned or unlinked instead of demoted.

- **INV-3** — A demoted draft carries the mark, and publishing it again keeps
  its date and strips the mark.
  *Test:* `tests/test_publishing.py::test_a_demoted_draft_keeps_its_date`.
  With `publishing._now()` set to a later moment, the republished entry's
  `Date` is the one it carried as a published entry, and its file holds no
  `Undone` field.
  *Breaks when:* the mark is not written, or `_move` dates every
  non-working-copy draft as it does today.

- **INV-4** — A working copy whose `Replaces` names a demoted draft publishes
  over that address, and both drafts are binned.
  *Test:*
  `tests/test_publishing.py::test_a_copy_of_a_demoted_entry_publishes_over_it`.
  The published file holds the copy's body and the demoted draft's date,
  carries neither `Replaces` nor `Undone`, and `drafts/` holds neither file.
  *Breaks when:* the working-copy test still requires a published target, so
  the copy publishes under its own address.

- **INV-5** — A draft whose `Replaces` names a draft carrying no mark is an
  ordinary draft.
  *Test:*
  `tests/test_publishing.py::test_a_replaces_naming_a_plain_draft_is_not_a_copy`.
  Publishing it writes it under its own address and leaves the named draft
  where it was.
  *Breaks when:* the widening in INV-4 keys on `Replaces` alone, which lets
  one draft destroy another.

- **INV-6** — A version of his that undo writes over is kept as a draft under
  a free address, with no `Replaces`.
  *Test:* `test_his_own_version_is_kept_beside_the_one_put_back`. For a
  published entry whose Store version differs, and for a draft whose slug the
  fetched state publishes, the kept draft holds the title, date, categories,
  tags and body the Store held, its `Slug` is the free address, and it names no
  entry undo restored in a `Replaces` field. Equality of the whole `Entry` is
  not asserted: `store.Entry` is frozen and carries `slug`, and the kept draft
  is written under a different address, so it can never hold.
  *Breaks when:* the differing version is overwritten, or is kept as a working
  copy of the entry just put back — which § 3 decision 7 rules out and
  `editor.TooManyCopies` would then refuse.

- **INV-7** — A fixed page, template or furniture file the fetched state does
  not hold is kept untouched.
  *Test:* `test_a_file_the_previous_state_lacks_is_kept`. After the undo the
  file is still in its own folder, reads back unchanged, and the folder the
  Builder wrote carries its page.
  *Breaks when:* undo treats the fetched state as the whole truth and bins
  what it does not name.

- **INV-8** — Undo's publish is not refused by the no-published-entry guard.
  *Test:* `test_undoing_to_an_empty_site_is_not_refused`. Against a fetched
  state holding furniture and no published entry, the undo builds and
  publishes, and `publishing.NothingToPublish` is not raised.
  *Breaks when:* `emptying=True` is not passed.

- **INV-9** — A previous state holding no `content/` is refused, and nothing
  in the Store moves.
  *Test:* `test_the_first_publish_cannot_be_undone`. The fake transport
  answers a parent commit whose tree holds no `content/`. `NothingToUndo` is
  raised, every file in `published/` and `drafts/` reads back equal to before,
  and the bin is empty.
  *Breaks when:* an empty `Fetched.paths` is read as "the previous state had
  nothing", which demotes every entry at once.

- **INV-10** — A definite failure puts his files back; an unknown outcome does
  not.
  *Test:* `test_a_definite_failure_puts_the_files_back`. With the transport
  answering 401, and again with `builder.build` made to raise, every file in
  `published/`, `drafts/`, `pages/`, `furniture/`, `templates/` and
  `comments/` reads back equal to before the undo. With the transport raising
  on the reference update, the Store holds the undone state instead.
  *Breaks when:* every failure is reversed, which contradicts a site that may
  already show the older state.

- **INV-11** — Nothing in the Store moves before the fetched state has been
  read whole.
  *Test:* `test_an_unreadable_fetched_file_moves_nothing`. One fetched entry
  is malformed. The raise names it, and every file in `published/` and
  `drafts/` reads back equal to before.
  *Breaks when:* the reconcile reads and writes file by file, which leaves the
  Store part old and part new for the same reason PRESS-0009 § 4.5 stages its
  fetch.

- **INV-12** — The key never reaches a page, the log or the console.
  *Test:* `test_the_key_is_never_shown`, with a sentinel key, through a
  success and a 401. The reply bodies, the log file and `capfd` do not hold
  it.
  *Breaks when:* a failure is formatted with its arguments.

`NothingToUndo` gets a sentence.
`tests/test_face.py::test_every_failure_type_has_a_sentence` finds it.

## 6. Failure modes

| What breaks | What he sees | What is left on disk |
|---|---|---|
| Pressless is not set up | `NotSetUp` | nothing moved |
| The key is missing or unreadable | the Credentials sentence | nothing moved |
| GitHub is unreachable, or refuses the key | its sentence | nothing moved |
| The repository has one commit | the `NoPreviousState` sentence | nothing moved |
| The state before holds no `content/` | the `NothingToUndo` sentence, saying the first publish cannot be undone | nothing moved |
| A fetched file cannot be read | the Store's failure, naming the file | nothing moved |
| A file cannot be built | `BuildStopped` | his files put back |
| GitHub refuses the upload | its sentence | his files put back |
| GitHub may have taken it | the unknown-outcome sentence | his files left undone |
| Putting back fails | the Store's failure | whatever the failure left; nothing deleted |
| The fetch area cannot be written | `FetchNotWritten` | nothing moved; the area is emptied |
| A copy of a demoted entry is published and the drafts cannot be binned — **the Publish route's, not undo's** (§ 4.5) | success, and a note that the waiting drafts can be thrown away | the entry published, both drafts still in `drafts/` |
| He closes the console mid-undo | nothing | as far as it got; pressing Undo again settles it |

**Pressing Undo twice returns the site to the state the first press
replaced** (§ 3 decision 6). That is decided behaviour, not a failure, and
nothing catches a reader who expects a history.

## 7. Tests

`tests/test_undo.py` — new, in CI. It carries INV-1, INV-2, INV-6, INV-7,
INV-8, INV-9, INV-10, INV-11 and INV-12.

`tests/test_publishing.py` gains INV-3, INV-4 and INV-5.

Each test is seen failing against stubs that raise `NotImplementedError`, then
mutation-probed once the code lands, one mutation per route each invariant's
*Breaks when* names.

## 8. Alternatives considered (and rejected)

- **Keep his version as a working copy, so one click is a redo.** Rejected by
  the user 2026-09-21. An entry may already have a working copy, and two
  drafts naming one entry is `editor.TooManyCopies`, which refuses to open it
  until he moves one out by hand.
- **Move a demoted entry's comments to the bin.** Rejected by the user
  2026-09-21. The Builder already holds a draft's comments back, and binning
  them would lose them from a later republish unless he moved the file back.
- **Widen `editor.working_copy` and the editor's pages to know about demoted
  entries.** Rejected by the user 2026-09-21: it reopens PRESS-0012 for
  wording, and decision 4 is met in `publishing._move` alone.
- **Copy the fetched bytes into the Store.** Rejected: the Store's own writers
  carry the atomic write and the owner-only mode (PRESS-0005 § 4.5), and a
  direct copy would reintroduce the wide-permission defect PRESS-0075 closed.
  The cost is that "differs" means differs as the Store holds it rather than
  byte for byte.
- **Reverse undo by re-fetching and re-applying.** Rejected: it needs GitHub
  at the moment GitHub has just failed.
- **Skip past previous undos, or disable undo after one press.** Both offered
  to the user and declined 2026-08-26; PRESS-0009 § 8 records why.

## 9. Out of scope

- Deleting an entry, and changing a published entry's address — PRESS-0128.
- Publishing a fixed page or the furniture — PRESS-0014.
- A publish that reads the whole site into memory — PRESS-0088.
- Reaching back more than one publish — declined by the user 2026-08-26; not
  queued.
- Bringing back a photograph original — `docs/design.md` rules it out; not
  queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_undo.py::test_the_fetch_area_is_emptied_at_both_ends` |
| INV-2 | `tests/test_undo.py::test_an_entry_the_previous_state_lacks_becomes_a_draft` |
| INV-3 | `tests/test_publishing.py::test_a_demoted_draft_keeps_its_date` |
| INV-4 | `tests/test_publishing.py::test_a_copy_of_a_demoted_entry_publishes_over_it` |
| INV-5 | `tests/test_publishing.py::test_a_replaces_naming_a_plain_draft_is_not_a_copy` |
| INV-6 | `tests/test_undo.py::test_his_own_version_is_kept_beside_the_one_put_back` |
| INV-7 | `tests/test_undo.py::test_a_file_the_previous_state_lacks_is_kept` |
| INV-8 | `tests/test_undo.py::test_undoing_to_an_empty_site_is_not_refused` |
| INV-9 | `tests/test_undo.py::test_the_first_publish_cannot_be_undone` |
| INV-10 | `tests/test_undo.py::test_a_definite_failure_puts_the_files_back` |
| INV-11 | `tests/test_undo.py::test_an_unreadable_fetched_file_moves_nothing` |
| INV-12 | `tests/test_undo.py::test_the_key_is_never_shown` |
| `NothingToUndo` has a sentence | `tests/test_face.py::test_every_failure_type_has_a_sentence` |
| The buttons and the reload (§ 4.6) | **nothing** in CI — by hand, in a browser; PRESS-0133 carries the by-hand rows |
| A real undo against GitHub | **nothing** in CI — by hand, against the maintainer's test repository |
| That the move phase of a fetch is not all-or-nothing | **nothing** — PRESS-0009 § 4.5 records the residual window; INV-1 removes undo's exposure to it by never reusing the folder, and does not close it |
| That pressing Undo twice is a toggle rather than a history | **nothing** — decided behaviour (§ 6); PRESS-0009 § 10 records the same gap |

## 11. Cross-doc impact

- `docs/specs/PRESS-0013-publish.md` § 4.1 and § 4.3 — `_move` gains the two
  changes in § 4.5, and `_Moved.copy` becomes the paths to bin. The sections
  point here. Its § 11 already says this item owes the mark.
- `docs/specs/PRESS-0012-editor.md` § 3 decision 6 — the marker it leaves to
  this item is `publishing.UNDONE`; the decision points here.
- `docs/specs/PRESS-0012-editor.md` § 4.5 and § 4.7 — the list and the editor
  page each gain the Undo button (§ 4.6), as PRESS-0013 § 11 pointed them at
  the Publish button. Nothing else on either page changes (§ 3 decision 9).
- `docs/specs/PRESS-0013-publish.md` § 4.5 step 3 — the launch registers
  `undo.register` beside the other three, and `pressless.__main__` gains that
  line. PRESS-0013's INV-8 asserts which routes are registered, so its test
  gains `/undo`.
- `docs/design.md` § What undo actually does — **an amendment is owed.** That
  section says an entry's comments file follows its entry *demoted*, published,
  binned or renamed with it. § 3 decision 8 narrows the demoted case to staying
  filed under the same address. It is a gated design document and the change is
  a decision rather than a correction, so it is filed rather than made here.
- `docs/specs/PRESS-0009-publisher.md` § 4.5 — its warning that this item must
  not assume `into` is whole is met by § 4.3 step 1; the section points here.
- `docs/specs/PRESS-0005-store.md` — no change. Undo uses the calls it already
  offers.
- `CHANGELOG.md` — an Added entry when it ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0015-undo-loop-log.md`.

## 13. Resource cost

§ 4.3 step 4 reads the whole fetched `content/` before writing anything, so
undo holds the previous state's writing in memory for the length of the
reconcile. That is the same shape as the publish PRESS-0088 measures, on the
same material, and it is deferred to the same measurement on the Windows box.
No new dependency.
