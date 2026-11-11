<!-- ants-spec-format: 1 -->
# PRESS-0345 — Publish lists what will change before it goes live

**Status:** accepted (2026-11-06), implemented. No review: owed on the three-subsystems trigger alone (`CLAUDE.md` rule 14).
**Kind:** ux.
**Source:** ROADMAP PRESS-0345 (the 2026-11-03 usability study).

Layman: pressing a page or entry to the site first shows a box saying which
pages and files will change, with Publish now and Not yet.

## 1. Goal

Press to site, in the entry editor and the page editor, opens a box over the
page listing what the publish would change on the live site. Publish now runs
the press as it runs today. Not yet closes the box, and nothing has changed.

## 2. Problem

A press goes live the moment it is clicked. The writer cannot see that a
press also carries other changes waiting in the Store, such as a new look or
a page pressed elsewhere, because `publishing.publish` builds the whole site
and `publisher.publish` sends every file that differs. Leading editors list
the changes first.

## 3. Scope decisions (agreed with the user)

- **A box before publishing**, with Publish now and Not yet, rather than a
  list always shown under the button. The user, 2026-11-06, taking the
  recommended option.
- **Photographs are named, not resized, in the list's build** (§ 4.2). Decided
  here: a full second build resized every photograph again, measured
  2026-11-06 at 0.111 s per 12-megapixel photograph (`builder._shrunk` and
  `_bare` on a 4000 by 3000 JPEG, ten runs), which is minutes on a site with
  hundreds of them.

## 4. Design

### 4.1 The publisher's plan

```python
@dataclass(frozen=True)
class Plan:
    uploaded: tuple[str, ...]   # paths a publish would write, sorted
    removed: tuple[str, ...]    # paths a publish would delete, sorted

def plan(settings: Settings, folder: Path, token: str,
         transport: Transport | None = None, *,
         named: frozenset[str] = frozenset()) -> Plan: ...
```

`plan` makes the reads `publish` makes before its first write, and no write.
It compares as `publish` does (PRESS-0009 § 4.2, INV-4), so both share one
function for the comparison and neither copies it. A repository with no
commits plans every unprotected file as uploaded.

`named` holds paths whose bytes the folder does not carry (§ 4.2). Each is
compared by presence alone: uploaded where the listing lacks it, never
removed.

### 4.2 The preview build

`builder.build` gains `photographs: bool = True`. Where it is False, each
photograph and the site icon is recorded in `Built.files` and not written.
`Built` gains `named: tuple[str, ...]`, the files recorded and not written.

`publishing.preview(folder, settings, key, *, entry=None, page=None,
transport=None) -> Preview` builds with `change=` the entry or page a press
would publish, `photographs=False`, into a scratch folder inside Pressless's
own folder. It then calls `plan` with `named=Built.named`, reads each changed
HTML page's `<title>`, and deletes the scratch folder whatever happens.

The entry `change` is the one `_move` would publish: `_move`'s choice of
slug and date for a working copy (PRESS-0015 § 4.5) moves into a function
both call. The page `change` is the page's waiting copy as a `builder.Html`.

`preview` runs the press's refusals that need no write: the journal being
off, a takeover owed, and the build's own stops. Each raises as the press
would.

### 4.3 The routes

`POST /publish/plan` takes an entry's `slug`, or a page's or part's `kind`
and `name`, whose waiting copy is the change. It saves nothing: the editor
saves what waits first (§ 4.4). It answers JSON:

```json
{"pages": ["Home", "Seaside walk"], "added": 3, "removed": 1, "failure": null}
```

`pages` holds the sorted titles of the HTML pages a publish would write, a
page with no title by its path. The source copy under `content/` is not
pages: its HTML would name each page twice and each part by its path.
`added` counts the other files it would write, and `removed` every file it would delete. A failure answers only
`failure`, as a press's failure reads.

It is not a press: it takes no `pressing` slot and publishes nothing.

*Folded back 2026-11-06: the route saved the fields itself in the draft, which
would have changed the file version the press posts next.*

### 4.4 The box

Press to site shows *Checking what will change…* on the status line, saves
what waits and holds further saves, then posts the plan route.
`pressing.SCRIPT` carries the request and the box, so both editors share them. The answer opens a dialog over the page listing the
pages, then the counts, or saying nothing on the site would change. Publish
now closes it and runs the press as PRESS-0013 § 4.4 and PRESS-0339 say. Not
yet closes it and puts the standing words back. A failure opens the failure
box, as a press's does.

**The AI helper's requests open the same box** (PRESS-0337 § 4.6), with
their own title and buttons, and `lines`: sentences for an ask whose plan
is not a build. Every field is written as text.

## 5. Invariants

- **INV-1** — A plan writes nothing to GitHub.
  *Test:* `tests/test_publisher.py::test_a_plan_writes_nothing`: a plan of a
  folder differing from its listing records only GET requests.
  *Breaks when:* `plan` reaches a write, or calls `publish`.

- **INV-2** — A plan names what a publish of the same folder sends.
  *Test:* `tests/test_publisher.py::test_a_plan_names_what_a_publish_sends`:
  over one folder and listing, with one file changed, one new and one gone,
  `plan`'s paths equal the blob and removal paths `publish` then records.
  *Breaks when:* the two compare differently, or a protected path is planned.

- **INV-3** — A named path is compared by presence alone.
  *Test:* `tests/test_publisher.py::test_a_named_path_is_compared_by_presence`:
  a named path the listing holds is not planned; one it lacks is uploaded.
  *Breaks when:* a named path is read from the folder, or planned as removed.

- **INV-4** — A preview changes nothing on disk outside its scratch folder,
  and leaves none behind.
  *Test:* `tests/test_publishing.py::test_a_preview_changes_nothing`: every
  file in Pressless's folder hashes the same before and after a preview, and
  no scratch folder remains, including after a preview the build stops.
  *Breaks when:* the preview moves the draft, builds into the site folder, or
  keeps its scratch folder.

- **INV-5** — A preview lists the entry or page being pressed.
  *Test:* `tests/test_publishing.py::test_a_preview_lists_what_is_pressed`: a
  new draft's preview lists its title; a working copy's lists the published
  entry's address; a page's waiting copy lists the page.
  *Breaks when:* the preview builds without `change=`, or with a change other
  than the one `_move` publishes.

- **INV-6** — Press to site publishes only after Publish now.
  *Test:* a node harness in `tests/test_editor.py` and `tests/test_page_editor.py`:
  a click posts the plan route alone; Not yet posts nothing more and restores
  the standing words; Publish now posts the press route.
  *Breaks when:* the click posts the press route, or Not yet leaves the button
  off.

## 6. Failure modes

| What happens | What the writer sees | The site |
|---|---|---|
| GitHub cannot be reached, or refuses the key, during the plan | the failure box, as a press shows it | unchanged |
| The build stops (a missing photograph, a page that cannot be built) | the failure box | unchanged |
| A photograph cannot be read as a picture | the list does not notice, since it is named and not opened; the press stops as it does today | unchanged |
| The journal is off, or a takeover is owed | the failure box with the press's own words | unchanged |
| The Store changes between the plan and Publish now | the press publishes what the Store then holds | as the press leaves it |
| A photograph's original is replaced under the same name | the list does not count it; the press still sends it | as the press leaves it |

## 7. Tests

INV-1, INV-2 and INV-3 in `tests/test_publisher.py`, INV-4 and INV-5 in
`tests/test_publishing.py`, INV-6 in each editor's tests. Each is seen to fail
before its code exists.

## 8. Alternatives considered (and rejected)

- **A full second build.** Exact for photographs, but it resizes every
  photograph again on every press (§ 3).
- **Build once: plan, hold the built site, publish it on Publish now.**
  Saves a build, but the draft moves before the box shows, so a closed tab
  leaves an entry the Store calls published and the site lacks.
- **A list from the Store alone.** Cheap, but blind to changes that are not
  the pressed item: a new look, a pressed page, a removed file.

## 9. Out of scope

- The box for Rename, Remove, Undo and the takeover's publish. — deferred;
  not yet queued.
- Naming each photograph and file, rather than counting them. — deferred;
  not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_publisher.py::test_a_plan_writes_nothing` |
| INV-2 | `tests/test_publisher.py::test_a_plan_names_what_a_publish_sends` |
| INV-3 | `tests/test_publisher.py::test_a_named_path_is_compared_by_presence` |
| INV-4 | `tests/test_publishing.py::test_a_preview_changes_nothing` |
| INV-5 | `tests/test_publishing.py::test_a_preview_lists_what_is_pressed` |
| INV-6 | the node harnesses in `tests/test_editor.py` and `tests/test_page_editor.py` |
| The box opens over the page, in a real browser | `scripts/by-hand-browser-checks.py`, by hand |

## 11. Cross-doc impact

PRESS-0013 § 4.4 gains a pointer: a click now opens this box first.
PRESS-0009 gains `plan` beside `publish`. CHANGELOG.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0345-publish-lists-changes-loop-log.md`.
