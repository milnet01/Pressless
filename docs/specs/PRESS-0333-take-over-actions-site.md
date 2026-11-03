<!-- ants-spec-format: 1 -->
# PRESS-0333 — Setup takes over a site GitHub Actions builds, in the same repository

**Status:** accepted (2026-11-01). Gated for one round, the user's budget for a new spec; every verified finding fixed, and no lane read the fixes.
**Kind:** feature.
**Source:** ROADMAP PRESS-0333 (user decisions 2026-10-23 and 2026-11-01; one
review round, the user's budget for a new spec, 2026-09-29).

**Changes:** PRESS-0212 § 4.4 and INV-8; PRESS-0218 § 3 decision 2; PRESS-0210
§ 9; PRESS-0125 § 4.4; PRESS-0009 § 4.5; PRESS-0013; PRESS-0015; `docs/design.md`
rule 9 and § Setup's three starts. § 11 lists each edit.
**Pairs with:** PRESS-0210, whose reading and writing bring the pages in.

Layman: someone whose GitHub site is made by its own build script switches it to
Pressless and keeps the same web address, told before anything changes.

## 1. Goal

Setup accepts a repository whose GitHub Pages is built by GitHub Actions. It
downloads the live site, shows what came and what will change, and at Finish
brings the pages into Pressless through PRESS-0210. Nothing changes on GitHub
during setup. The first publish asks first, has the person remove the build
workflow file on GitHub, publishes, and switches Pages to the branch. The address
and any custom domain stay. Afterwards the person is told what changed.

## 2. Problem

1. **Setup refuses such a repository.** `setup`'s `check_pages` answers
   `setup.hint.elsewhere` where `publisher.pages` says on and not `serves_root`.
2. **Its pages are not in the repository.** It holds what a tool builds from, so
   `takein.look_folder` cannot find them. `read_folder` says `built_by_a_tool`, or
   finds no `index.html`.
3. **The Pages artifact is not a way in.** `actions/upload-pages-artifact`'s
   `retention-days` defaults to 1, and listing artifacts needs the Actions
   permission, which neither the app nor the key holds.
   Source: https://github.com/actions/upload-pages-artifact
   Source: https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps
4. **Pressless may not change a workflow file.** GitHub's lists name a Workflows
   permission for `DELETE contents/{path}` and `PATCH git/refs/{ref}`, and the
   permissions Pressless asks for (`docs/working-here.md` § Registering the GitHub
   App, and the key step's words in `words.py`) do not include it. The docs do not
   spell out the refusal; it was not run against GitHub.
   Source: https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens
5. **Switching Pages first would take the site down.** A branch build serves the
   repository's root, which holds the tool's source until a publish replaces it.
6. **A custom domain needs a file after the switch.** "If you are publishing from
   a branch, custom domains are stored in a CNAME file in the root of your
   publishing source", and an Actions build ignores that file, so the root may
   hold none, or a stale one.
   Source: https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/troubleshooting-custom-domains-and-github-pages
7. **A publish removes what it does not know.** `publisher.publish` removes every
   path that is neither in the folder nor on `Settings.untouchable`. A `.nojekyll`
   or `CNAME` written after setup would go on the next publish.

## 3. Scope decisions (agreed with the user)

1. **The same repository.** The user, 2026-10-23.
2. **Warn first.** Nothing changes until the person confirms, they are told what
   will change, and they are told afterwards what did. The user, 2026-10-23.
3. **The workflow file goes by one hand step, with no new permission.** The user,
   2026-11-01, replacing "Pressless removes it" of 2026-10-23 once § 2 item 4 was
   found. Pressless links to GitHub's own delete page and checks the file has gone.
4. **One review round.** The user, 2026-09-29.
5. **(decided here) The live site is downloaded by following its links.** § 2 item
   3 rules out the artifact, and the roadmap item says "downloading the live site".
6. **(decided here) The switch happens at the first publish, not at Finish.** The
   person can check the brought-in site first, and the old site stays up until the
   new one is ready to serve.
7. **(decided here) A build workflow is one naming `actions/deploy-pages`.** It is
   the action that makes an Actions deployment, and a substring test needs no YAML
   reader, which the standard library lacks. A file also holding other jobs is
   named as a whole, so the person sees that before removing it.
8. **(decided here) A branch-built site stays refused**, a workflow pushing to
   `gh-pages` included. `build_type` is `legacy` there, and § 4.1's test does not
   match.

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 Recognising such a site (Publisher, Face)

```python
# src/pressless/publisher.py
@dataclass(frozen=True)
class Pages:
    on: bool
    address: str | None
    serves_root: bool
    built_by_actions: bool = False   # new: build_type is "workflow"
    domain: str | None = None        # new: the answer's cname

def head_commit(settings: Settings, token: str,
                transport: Transport | None = None) -> str: ...
def default_branch(repository: str, token: str,
                   transport: Transport | None = None) -> str: ...
def switch_pages_to_branch(repository: str, token: str, domain: str | None,
                           transport: Transport | None = None) -> Pages: ...

# src/pressless/takeover.py — new. `publishing` reads it, so it imports neither
# `takein` nor `pressless_import`.
BUILD_MARK = "actions/deploy-pages"
def build_files(folder: Path, settings: Settings, key: str,
                transport: publisher.Transport | None = None) -> tuple[str, ...]: ...
```

`build_files` calls `publisher.fetch_state` with prefix `.github/workflows/` into
the fetch area, and answers the sorted paths of each `.yml` or `.yaml` directly in
that folder whose text holds `BUILD_MARK`. The fetch area is emptied as `look`'s is.

**pages step**, in `check_pages`, where `shown.on and not shown.serves_root`:

- Not `built_by_actions`, or `build_files` empty: `setup.hint.elsewhere`, as today.
- Otherwise `takein.look_site` (§ 4.2) lays the live site out. Where `read_folder`
  finds no `index.html` or says `built_by_a_tool`, `takein.forget_folder` runs and
  the answer is a new hint, `setup.hint.site_unreadable`.
- Otherwise the answers gain `bring_in_commit`, the branch's head commit, and
  `take_over: "yes"`. `site_address` is `shown.address`. Pages is not switched and
  `.nojekyll` is not written.

`take_over` and `bring_in_commit` are removed at the start of `check_pages`, as
`bring_in_commit` is today. Neither ends in `key`, so the progress file keeps them.

### 4.2 Downloading the live site (Import)

```python
# src/pressless_import/fetch.py — added; still the one module that reaches the network
@dataclass(frozen=True)
class Crawled:
    left: tuple[tuple[str, str], ...]  # (address's path, why it was not kept)

def fetch_site(address: str, into: Path, room: Callable[[], int], *,
               resolve: Resolve | None = None, connect: Connect | None = None) -> Crawled: ...

# src/pressless/takein.py
def look_site(folder: Path, settings: Settings, key: str, address: str, commit: str = "",
              transport: publisher.Transport | None = None
              ) -> tuple[pressless_import.Found, str]: ...
```

`look_site` empties the held folder as `look_folder` does, and calls
`fetch_site(address, held, room)`. It writes `import/folder.json` naming `commit`,
or `head_commit` where that is empty, and `import/folder-left.json`, whose shape
`importing` already reads, holding `Crawled.left`. That file's name and reader move
to the package, as `pressless_import.FOLDER_LEFT` and `read_folder_left`, so `setup`
reads it without importing `importing`. It answers `read_folder`'s `Found`
and the commit.

A `resolve` or `connect` left `None` is read from the module when called, so
`tests/test_takeover.py` patches `fetch._resolve` and `fetch._connect`.

**What it follows.** `fetch_site` starts at `address`. An `address` it cannot read
ends the crawl with nothing kept. Otherwise it takes addresses first found first:

- from a page: what `_folder._spots` finds, an `<a href>` included;
- from a stylesheet, or a `style` element or attribute: each `url(...)` and `@import`;
- from `sitemap.xml` at the site's root, where it answers: each `<loc>`.

A query and a fragment are dropped from what is fetched. An address or a redirect
no parser can read is not followed, and the redirect is `left`.

**What stays in the site.** An address is the site's where its host equals
`address`'s, its port does too, a scheme's default port counting as none, and its
path lies under `address`'s path. Its scheme is ignored, and every fetch uses
`address`'s. Anything else is not fetched and not listed. A redirect leading out of
the site is `left`.
`fetch`'s checks apply to each hop: every address a host resolves to is global, and
no cookie and no key is sent.

**Where it lands.** The path, percent-decoded, without `address`'s path. A path
ending `/`, or empty, gains `index.html`. An answer of type `text/html` to a path
with no suffix gains `.html`. A redirect's final address names the file. A path
holding a `..` segment once decoded, which `urljoin` leaves only where it was encoded, or
failing `_why_not_kept`, is `left`. So is a path once
`MEMBERS_MOST` files are held, with the reason saying the site is too large to
bring in whole, and each answer over `builder.FILE_LARGEST`, or that fails. A second
address landing at a path already held, as `/index.html` beside `/`, is that file.

**Absolute addresses.** Static site tools commonly write the site's own address in
full, and PRESS-0210 § 4.5 leaves an address with a host as written, which would
leave pictures on the old layout's paths. So when the crawl ends, each address in a
page or stylesheet that is the site's, by the test above, becomes `/` and the path it
lands at, its query and fragment kept. § 4.5 of PRESS-0210 then reads it as any other.
So does a relative one landing elsewhere than it says. One with no host that is not
the site's, such as `/other/` or `../other/` beside a project site, becomes a full
address, which § 4.5 leaves as written.

**What a crawl cannot see** is said on the screen (§ 4.4): a page no link reaches,
and a page a script builds in the browser, which arrives as the script's shell.

### 4.3 Finish (Face)

`takein.found_held` and `takein.bring_folder` gain `address: str = ""`. Where it is
set, laying the folder out again calls `look_site` with that commit, not
`look_folder`. So what is
written is what was shown, and a held folder that has gone is downloaded again.

`_save_sequence` gains `take_over: bool = False`. Where set, after `bring_folder`
returns and before Settings is saved:

```python
# src/pressless/takeover.py
MARKER = "takeover-owed"             # in the site's folder: the build files' names, a line each
def owed(folder: Path) -> bool: ...
def mark(folder: Path, files: tuple[str, ...]) -> None: ...  # OSError is the caller's
def named(folder: Path) -> tuple[str, ...]: ...   # for the report, once they have gone
def done(folder: Path) -> None: ...  # absent is fine
```

`sites.SITE_NAMES` gains the marker, as it holds `starter-unpublished`, so
`sitefile.KEPT` carries it and a site opened from a file still owes the takeover.
The Report and the done page are PRESS-0210's,
with one more sentence, `setup.done.take_over`, saying the site on the web has not
changed and what the first publish will ask.

Where `address` is set, `import/folder-left.json` goes to `bring_in_folder` as `left`,
as a ZIP's does, and `_work_out` adds `Found.left` itself. `forget_folder` also removes
that file. The Store's list page shows `setup.takeover.owed` above the list while the
marker exists, as `_unpublished_starter` does for the starter.

### 4.4 The warning, before Finish (Face)

The *site* step, where the answers carry `take_over`, shows `_show_take_over`, which
holds `_show_bring_in`'s rows, under its own opening sentence through an `intro`
argument, and these, each in its own words:

- GitHub Pages will switch from the build to what Pressless publishes;
- the build workflow file, by name, is to be removed by the person at the first
  publish, stays in the repository's history, and each other file in
  `.github/workflows/` stays;
- the address stays, and the custom domain, by name, where there is one;
- Finish changes nothing on GitHub, and the old site stays up until then;
- `.nojekyll`, and `CNAME` where there is a domain, will be added, and a `CNAME` with
  no domain behind it removed;
- what could not be read: each `Crawled.left` path, and § 4.2's two limits, always.

### 4.5 The first publish (Face)

```python
# src/pressless/publishing.py
class TakeoverOwed(Exception): ...   # SENTENCES entry: Site.UNCHANGED, as WouldReplaceASite
TAKEOVER_ADDRESS = "/publish/takeover"

def publish(folder, settings, key, *, entry, emptying=False, taking_over=False,
            capture=..., notices=None, transport=None) -> Published: ...
```

`guard_and_build` raises `TakeoverOwed` first, where `takeover.owed(folder)` and not
`taking_over`. `publish` is the one way out for `_pressed`, `undo` and `page_editor`,
so none of them skips it. `replace_link` also answers the link to `TAKEOVER_ADDRESS`
for this failure.

**GET `/publish/takeover`**, with no marker: `publishing.nothing`. With one, after
`takeover.build_files` over the branch's current state:

- each change from § 4.4, and the domain as `publisher.pages` reads it now;
- each build file, with a link to GitHub's delete page, opening in a new tab, each
  path segment quoted:
  `https://github.com/<repository>/delete/<branch>/<path>`;
- the steps in plain words: press the link, press GitHub's *Commit changes*, come
  back;
- the button `publishing.takeover.button`.

**POST**, in `editor.LOCK` and through `pressing.run` as a press is:

1. `build_files` again. Any left: the page again with `publishing.takeover.still_there`,
   and no write is sent.
2. `publisher.pages` for the domain.
3. Settings saved with `.nojekyll`, and `CNAME` where there is a domain, joined to
   `untouchable`, where absent. With no domain, `CNAME` is taken off it, so step 4's
   publish removes a stale one, which a branch build would read as the domain. Pages
   no longer built by Actions: the marker is removed, the answer says Pages has
   already been changed and what it now serves, and the POST ends here.
4. `publish(..., entry=None, taking_over=True)`. A failure stops here, and is shown
   as a press's is. The old site is still up, and the page can be pressed again.
5. `publisher.switch_pages_to_branch(repository, key, domain)`. A failure stops here,
   and the page says the new site is on GitHub, not yet on the web, and to press
   again. A second press's publish finds nothing differing and writes nothing
   (PRESS-0009 INV-4), then this step runs.
6. `takeover.done`, then the report page: Pages switched, the workflow files
   named, the domain kept, the files added and removed, the root entries replaced,
   with `publisher.Outcome`'s counts, and that a first build takes GitHub a few minutes.
   Where `Outcome.commit` is empty, it says an earlier press published the site, in
   place of the counts.

`switch_pages_to_branch`:

- writes an empty `.nojekyll` where the root lacks one, as `switch_pages_on` does,
  sharing its code;
- where `domain` is set, reads `contents/CNAME` and writes `domain` where it is
  absent or holds another name, its `sha` sent where it exists;
- sends `PUT pages` with `build_type: "legacy"`, `source` the default branch and
  `/`, and `cname: domain` where `domain` is set. `cname` is never sent as null,
  which GitHub documents as removing the domain, and omitting it is undocumented;
- accepts `PUT pages`'s 204, GitHub's documented answer, which `_Session._call` raises
  on today;
- then sends `POST pages/builds`. GitHub builds a branch site only when a commit
  lands, and every commit here precedes the switch: the 2026-11-03 hand check saw
  the old site stay up with no build until one was asked for;
- answers `_pages`.

No Pressless write names a path under `.github`. It stays on `untouchable` because
the Builder produces no such root, so `publisher.publish` leaves the rest of it.

### 4.6 Files touched

`publisher.py`, `takein.py`, new `takeover.py`, `pressless_import/fetch.py`,
`pressless_import/_folder.py`, `importing.py`, `setup.py`, `publishing.py`, `sites.py`
and `words.py`.

## 5. Invariants

- **INV-1** — Setup over a site Actions builds sends no write to GitHub, from the
  *repository* step to Finish, and the site's Pages setting is untouched.
  *Test:* `tests/test_takeover.py::test_setup_writes_nothing_to_github`.
  *Breaks when:* `check_pages` falls through to `switch_pages_on`.
- **INV-2** — What cannot be taken over is still a `Hint`, and no write is sent.
  *Test:* `tests/test_takeover.py::test_what_cannot_be_taken_over_is_refused`, one
  fixture each: `build_type` legacy on `gh-pages`; `workflow` with no file naming
  `BUILD_MARK`; and a front page answering 404, which is the only rule failing in
  that fixture.
  *Breaks when:* `built_by_actions` alone opens the way, or a failed front page goes
  on with no pages.
- **INV-3** — Before Finish the *site* step names every § 4.4 row, each build file
  and the domain, and the Store is unchanged.
  *Test:* `tests/test_takeover.py::test_the_screen_says_what_will_change`.
  *Breaks when:* a row is dropped, or the body writes to the Store.
- **INV-4** — While the marker exists, no publish reaches the build. *Test:*
  `tests/test_takeover.py::test_no_publish_passes_the_marker`, through
  `publishing.publish` with `entry` set, with `entry=None`, and through `undo.undo`:
  `TakeoverOwed`, `builder.build` not called, no write sent, and the moved entry put
  back.
  *Breaks when:* the guard sits in `_pressed` alone.
- **INV-5** — A build file still there stops the takeover before any write.
  *Test:* `tests/test_takeover.py::test_a_file_still_there_stops_it`: the POST sends
  no non-GET, and Settings and the marker are unchanged; the GET holds the quoted
  delete link.
  *Breaks when:* the list is read once, from setup's answers.
- **INV-6** — The switch comes after the publish lands. *Test:*
  `tests/test_takeover.py::test_the_switch_follows_the_publish`, whose double records
  the order: `PATCH git/refs` before `PUT contents/.nojekyll` before `PUT pages`,
  and `POST pages/builds` last.
  *Breaks when:* Pages is switched first, which serves the tool's source (§ 2 item 5),
  or no build is asked for after it.
- **INV-7** — A custom domain stays, through this publish and the next. *Test:*
  `tests/test_takeover.py::test_the_domain_stays`: `PUT pages` carries `cname`,
  `CNAME` holds the domain over an absent and a stale file, and a second publish
  removes neither `CNAME` nor `.nojekyll`, after a takeover and after a re-point by hand.
  With no domain, a stale `CNAME` is gone before `PUT pages`.
  *Breaks when:* the two files miss `untouchable` (§ 2 item 7), or `cname` goes null.
- **INV-8** — A failure leaves the takeover able to finish. *Test:*
  `tests/test_takeover.py::test_a_failure_can_be_pressed_again`: a refused publish
  sends no `PUT pages`, and the marker stays; a refused `PUT pages` leaves the marker,
  and the next POST makes no new commit and sends `PUT pages`.
  *Breaks when:* the marker goes before the switch.
- **INV-9** — Pressless writes no path under `.github`, and another workflow file
  stays. *Test:* `tests/test_takeover.py::test_nothing_writes_a_workflow_file`: `test.yml`
  beside a removed `deploy.yml`, and no tree entry or Contents write naming `.github`,
  over a full takeover.
  *Breaks when:* `.github` leaves `untouchable`. A crawled `.github/` path would put it
  in `Brought.roots`, which `read_folder` prevents by leaving out every dot name.
- **INV-10** — A crawl stays in the site. *Test:*
  `tests/test_importer_fetch.py::test_a_site_download_stays_in_the_site`: an address on
  another host, one outside a project site's path, a redirect to another host, a host
  resolving to a private address, and `%2e%2e/x`: none is requested beyond the redirect's
  own hop, nothing lands outside `into`, and the redirect and the `..` are `left`.
  *Breaks when:* `urljoin`'s answer is fetched unchecked.
- **INV-11** — What a crawl lays out reads as PRESS-0210's folder. *Test:*
  `tests/test_importer_fetch.py::test_a_downloaded_site_builds_whole`, a double serving
  a project site at `/site/`: `/about/`, `/team` redirecting to `/team/`, an extensionless
  `text/html` answer, a page only `sitemap.xml` names, a stylesheet by `url()` and
  `@import`, `srcset`, and full addresses to the site's own files, one with a fragment.
  After `bring_in_folder` and `builder.build`, each address in each built page resolves to
  a built file, but a link to `/other/`, which is a full address.
  *Breaks when:* a full address stays as written, or a path keeps `/site/`.
- **INV-12** — A file that could not be read is named. *Test:*
  `tests/test_takeover.py::test_what_was_not_read_is_named`: a 404 and an over-large
  answer reach § 4.4's row and the Report.
  *Breaks when:* `Crawled.left` is not written to `import/folder-left.json`.
- **INV-13** — What is written is what was shown. *Test:*
  `tests/test_takeover.py::test_finish_writes_what_was_shown`: the double's site changes
  after *pages*, and Finish sends no site request and writes the first state; with
  `import/folder/` gone, Finish downloads again; a second press after a failed Settings
  save downloads nothing and leaves the marker.
  *Breaks when:* `bring_folder` lays out by `look_folder`, or the marker is written after
  the save.
- **INV-14** — The person is told what changed. *Test:*
  `tests/test_takeover.py::test_the_report_says_what_changed`: Pages, each file, the
  domain and the files added; the marker gone; the list page's line gone.
  *Breaks when:* the POST redirects to the list.
- **INV-15** — What Pressless shows is escaped, and a link's path quoted. *Test:*
  `tests/test_takeover.py::test_names_are_escaped`: a workflow named `a&'b x.yml`, which
  Windows can hold, and a domain holding `<`.
  *Breaks when:* a name is written raw into the link or the list.

## 6. Failure modes

| What fails | What happens |
|---|---|
| The live site cannot be reached | *pages* is `setup.hint.site_unreadable`; nothing is kept |
| Some files cannot be read | Each is listed before Finish and in the Report (INV-12) |
| The site is too large for `MEMBERS_MOST` | The rest are `left`, with that reason, before Finish |
| No room on the drive | `fetch`'s `NO_ROOM`, for that file and each after it, as `left` |
| A page is built by a script | Not detected; the screen says so, and § 7's hand check looks |
| A script module (`type="module"`) | PRESS-0210 § 4.6 leaves it `left`, named |
| The workflow file is still there at the POST | The page again; no write (INV-5) |
| A branch protection rule stops the person deleting the file | The file stays, so the page stays, and GitHub's own page says why |
| A repository rule refuses the publish | A press's failure; the old site is up (INV-8) |
| Pressless closes between steps 4 and 6 | The marker stays; the next press finishes (INV-8) |
| The person removes the file and never publishes | The site stays up from its last deployment; not verified how long GitHub keeps it |
| The site was re-pointed by hand meanwhile | Step 3 removes the marker and says so |
| GitHub's `PUT pages` keeps or drops state it does not document | § 7's hand check |

## 7. Tests

`tests/test_takeover.py` is new, over `tests/test_takein.py`'s `_Repository` double with
`GET`/`PUT pages`, `PUT` answering 204, Contents and a fake site added: INV-1, INV-2,
INV-3, INV-4, INV-5,
INV-6, INV-7, INV-8, INV-9, INV-12, INV-13, INV-14 and INV-15.
`tests/test_importer_fetch.py` holds INV-10 and INV-11, by its `resolve` and `connect`
doubles. Each named test is seen to fail against today's code before its change.

**By hand, before release, on a scratch repository built by an Actions workflow with a
custom domain:** setup through Finish leaves the site unchanged; the delete link works
signed in; the takeover keeps the domain and HTTPS; how long the old site stays up
around the switch; a publish after it keeps the domain. Also a real static site tool's
output, compared in a browser. This is added to PRESS-0133's list.

## 8. Alternatives considered (and rejected)

- **Ask for the Workflows permission.** Rejected by the user, 2026-11-01: every person
  would grant a right over code that runs with a repository's secrets, for a step most
  never use, and existing installs would need approving again.
- **Download the Pages artifact.** Rejected: § 2 item 3.
- **Run the tool's own build.** Rejected: it needs the tool on the person's computer,
  which `docs/design.md` § The stack rules out.
- **Leave the workflow in place.** Rejected: it would run on every publish, and the user
  chose its removal.
- **Switch at Finish.** Rejected: § 3 decision 6, § 2 item 5.
- **Publish the workflow's removal in the same commit.** Rejected: it is the write
  § 2 item 4 needs the permission for.

## 9. Out of scope

- A site a workflow pushes to a branch — deferred; not yet queued. It stays refused.
- A takeover into a new repository: the user chose the same one.
- Keeping the tool's source usable afterwards. It stays in the repository where the
  Builder does not replace it, and in its history.
- Setting up a new domain — PRESS-0222.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_takeover.py::test_setup_writes_nothing_to_github` |
| INV-2 | `tests/test_takeover.py::test_what_cannot_be_taken_over_is_refused` |
| INV-3 | `tests/test_takeover.py::test_the_screen_says_what_will_change` |
| INV-4 | `tests/test_takeover.py::test_no_publish_passes_the_marker` |
| INV-5 | `tests/test_takeover.py::test_a_file_still_there_stops_it` |
| INV-6 | `tests/test_takeover.py::test_the_switch_follows_the_publish` |
| INV-7 | `tests/test_takeover.py::test_the_domain_stays` |
| INV-8 | `tests/test_takeover.py::test_a_failure_can_be_pressed_again` |
| INV-9 | `tests/test_takeover.py::test_nothing_writes_a_workflow_file` |
| INV-10 | `tests/test_importer_fetch.py::test_a_site_download_stays_in_the_site` |
| INV-11 | `tests/test_importer_fetch.py::test_a_downloaded_site_builds_whole` |
| INV-12 | `tests/test_takeover.py::test_what_was_not_read_is_named` |
| INV-13 | `tests/test_takeover.py::test_finish_writes_what_was_shown` |
| INV-14 | `tests/test_takeover.py::test_the_report_says_what_changed` |
| INV-15 | `tests/test_takeover.py::test_names_are_escaped` |
| GitHub really keeps the domain and the site through the switch | **nothing** — § 7's hand check |
| GitHub's delete page stays at that address | **nothing** — § 7's hand check |
| A brought-in site looks as it did | **nothing** — § 7's hand check |

## 11. Cross-doc impact

- **PRESS-0212 § 4.4 and INV-8**: *pages* goes on for a site Actions builds; the
  refusal narrows to INV-2 here.
- **PRESS-0218 § 3 decision 2** and **PRESS-0210 § 9**: point here as built.
- **PRESS-0125 § 4.4**: `fetch.py` also downloads a site's own pages at setup.
- **PRESS-0009 § 4.5**: `Pages` gains two fields, and `switch_pages_to_branch` is added.
- **PRESS-0013** and **PRESS-0015**: a publish and an undo can be refused by
  `TakeoverOwed`.
- **`docs/design.md` rule 9**: Import may also fetch the pages of the site being taken
  over; **§ Setup's three starts**: the second start gains this route.
- **ROADMAP PRESS-0333**: its body's "Pressless removes" is superseded by § 3 decision 3.
- **CHANGELOG** gains an Added entry when this ships.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0333-take-over-actions-site-loop-log.md`.

## 13. Resource cost

- A site is downloaded once, one file at a time, into `import/folder/`, then moved into
  the Store by rename as PRESS-0210 § 13 says. A Next press holds the page for as long
  as that takes, as `look_folder` does.
- `build_files` reads only `.github/workflows/`, one blob request a file, twice per
  takeover press at most.
- No new dependency.

## 14. Folded back from the build

The build found these, and each section above now says them; no reviewer read
them: `read_folder_left` and `FOLDER_LEFT` moved to the package; `takeover.named`;
`publisher.default_branch` and `head_commit`; `_show_bring_in`'s `intro` argument; a
second address for one file; an address or redirect no parser can read; and a relative
address landing elsewhere or leaving a project site. Tests: `tests/test_takeover.py`,
`tests/test_importer_fetch.py`.
