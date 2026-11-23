# PRESS-0009 — Publisher: making GitHub match the folder it was handed

**Status:** accepted (2026-08-26). Implemented, §4.1's five own-type failures included and each asserted by name (PRESS-0116, 2026-09-08). Amended 2026-09-27: on Windows a fetch refuses a path the disk cannot hold, as `UnfetchablePath` (§4.5, INV-11; PRESS-0160). Gated for one loop: five verified, five fixed, not converged. **Amended 2026-09-27, before implementation**: an unexpected success or an unreadable answer to a write that can change the site is `OutcomeUnknown` (PRESS-0166), and a write answered with a redirect is `RepositoryMoved` (PRESS-0167). That changes direction, so the gate re-armed. Amended 2026-11-06: files are hashed, then read again to be sent (§4.2, INV-13; PRESS-0088). Every gate this document has taken, and how each ended, is §12 — kept there so this line does not carry a count that goes stale on the next loop.
**Kind:** implement.
**Source:** ROADMAP PRESS-0009 and PRESS-0010 (`docs/design.md` § The
parts, § What may depend on what rules 5, 7 and 10; ADR-0002).

**Covers:** PRESS-0009 and PRESS-0010, as one umbrella
(`spec-format.md` §2). PRESS-0010 is the fetch-back capability — §4.5 and
INV-8 — and it shares this module's transport, branch resolution, failure
types and test seam. Two specs would restate all four.

**Blocked by:** PRESS-0001 and PRESS-0002, both shipped.
**Blocker for:** the Face's publish sequence; PRESS-0015, the undo
sequence that uses fetch-back; PRESS-0014, via PRESS-0010.

*Layman:* the part that sends the finished site to GitHub without git
being installed, leaves alone the handful of files that are not ours,
and can fetch back the version before this one.

## 1. Goal

After this ships, one module answers three requests and nothing else:
*make the repository match this folder*, *what sits at the repository
root*, and *fetch back the state before the current one*.

It reads Settings and a folder of finished files. It is handed a
publishing key rather than fetching one. It writes no prose for the
writer, holds no state between calls, and cannot tell an entry from a
stylesheet.

## 2. Problem

ADR-0002 rules out shelling out to `git`, because that means the writer
installing and configuring git before he can publish — which is the
thing this project exists to remove. So publishing is HTTP against
GitHub's own interface, and every safety property git would have given
for free has to be built and checked here instead.
`docs/decisions/ADR-0002-publish-via-github-api.md` says so outright:
*"If Pressless computes the wrong set of changed files, nothing
downstream catches it"*.

Four things make this a contract rather than a helper.

1. **Three callers bind to the surface.** The Face's publish sequence,
   its undo sequence, and setup's derivation of the untouchable list all
   call this module, and rule 1 gives the Face the ordering. A surface
   that changes shape later changes all three.

2. **Deleting the wrong file is unrecoverable in a way a bad page is
   not.** `docs/design.md` says it in those terms: one root entry holds
   the custom domain and another proves the site's identity to a search
   engine, and losing either is silent and slow. The rule that protects
   them is *every root entry the Builder does not produce*, and the list
   Settings holds is that rule's derived form.

3. **Publishing is many writes that must read as one act.** S6 requires
   the writer never be left unsure whether his change went out. A
   sequence that can stop halfway with the site half-updated cannot
   deliver that, so where the sequence is interruptible has to be a
   decided property rather than an accident of the code.

4. **Undo is the highest-value safety feature in the app** — the design
   calls the header edit the highest-blast-radius act there is, and undo
   is the answer to it. What "the previous state" means is not obvious
   once undo itself publishes, and getting it wrong restores the very
   thing the writer rejected.

## 3. Scope decisions (agreed with the user)

1. **Undo goes plain one step back.** Decided by the user 2026-08-26,
   with the consequence stated in the question and accepted: because an
   undo is itself an ordinary publish, pressing undo twice returns the
   site to the version the first undo rejected. Two alternatives were
   offered and declined — skipping past previous undos, and disabling
   undo after one press. §8 records why they lost. **This is a decided
   behaviour, not a defect**, and §10 records that nothing catches it.

2. **The Publisher is handed its key, never fetches one.**
   `docs/design.md` rule 10, settled 2026-08-25. This is what keeps rule
   5 literally true and lets every test here run without a keyring.

3. **The transport is the standard library.** `urllib.request`, not a
   third-party HTTP library. § The stack names one runtime dependency
   plus the imaging library, and PRESS-0022 has to carry every
   dependency into a packaged artefact. A convenience library here would
   be a third, bought for syntax.

4. **Fetching back may be narrowed by a path prefix.** The undo sequence
   needs one directory of the fetched state, and fetching a whole site
   to recover it costs the writer a large download on a domestic
   connection. The prefix is an opaque string to this module, so rule 5
   holds: it still cannot tell an entry from a stylesheet.

## 4. Design

### 4.1 The public surface

*PRESS-0345 § 4.1 adds `plan`, the reads `publish` makes before its first
write, sharing its comparison.*

```python
# src/pressless/publisher.py

@dataclass(frozen=True)
class Outcome:
    commit: str                  # sha written; "" when nothing differed
    uploaded: tuple[str, ...]    # repository-relative paths written
    removed: tuple[str, ...]     # repository-relative paths deleted

@dataclass(frozen=True)
class Fetched:
    commit: str                  # the sha fetched from
    paths: tuple[str, ...]       # repository-relative paths written out

class PublishError(Exception): ...         # raised itself only where §6 names no other type
class Unreachable(PublishError): ...       # no answer from GitHub, before the branch was touched
class OutcomeUnknown(PublishError): ...    # a write that can move the site was attempted and its result is unknown
class Refused(PublishError): ...           # key rejected, or no write access
class RepositoryMissing(PublishError): ... # the repository URL itself answers 404
class Conflict(PublishError): ...          # the branch moved under us
class TooLarge(PublishError): ...          # a documented GitHub limit was hit
class RateLimited(PublishError): ...       # GitHub asked us to slow down, and retrying did not clear it
class NoPreviousState(PublishError): ...   # nothing before the current commit

# Each is its own type because `docs/design.md` § Errors requires every
# message to end with what to do next, and for each of these that differs
# (PRESS-0116). SiteFolderMissing: fix the setting. StrayFile: remove the
# file. SiteWouldBeEmptied: rebuild the site. FetchNotWritten: free space.
# RemoteStateMissing: retry. UnfetchablePath (PRESS-0160): rename that file
# on the site. RepositoryMoved (PRESS-0167): enter the repository's new name
# in Settings. This pairing is the one place they are paired;
# §6 orders its rows differently, so nothing anywhere reads them off a list.
# The first four refuse before anything reaches GitHub -- FetchNotWritten
# can still have written to the folder it was handed, which is §4.5's
# residual window. RemoteStateMissing refuses at no fixed point: `_failure`
# maps a status on any request, so a 404 inside a repository that answers
# can arrive after blobs have been sent. §4.3's property is what keeps its
# row "unchanged" -- nothing a reader sees moves until the reference
# update.
class SiteFolderMissing(PublishError): ...  # the handed folder is not a directory
class StrayFile(PublishError): ...          # the folder holds what the Builder did not produce (§4.4)
class SiteWouldBeEmptied(PublishError): ... # every unprotected path removed and none written
class FetchNotWritten(PublishError): ...    # fetch_previous could not write into the folder
class RemoteStateMissing(PublishError): ... # something INSIDE a repository that answers is absent
class UnfetchablePath(PublishError): ...    # a fetched path this system's disk cannot hold (§4.5)
class RepositoryMoved(PublishError): ...    # a write was redirected: the repository was renamed or moved

class Transport(Protocol):
    """The one seam. Tests are its only other caller."""
    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]
                ) -> tuple[int, dict[str, str], bytes]: ...
    def wait(self, seconds: float) -> None: ...

def publish(settings: Settings, folder: Path, token: str, message: str,
            transport: Transport | None = None) -> Outcome: ...

def root_entries(settings: Settings, token: str,
                 transport: Transport | None = None) -> tuple[str, ...]: ...

def remote_paths(settings: Settings, token: str,
                 transport: Transport | None = None) -> tuple[str, ...]: ...
    # every file on the default branch, () for an empty repository (PRESS-0446)

def fetch_previous(settings: Settings, token: str, into: Path,
                   prefix: str = "",
                   transport: Transport | None = None) -> Fetched: ...
```

Every failure this module **raises** is one of the types above. A crash
raises nothing and is §6's own row. None of them carries a sentence for
the writer — `docs/design.md` § Errors gives that job to the Face alone.

**`transport` is the test seam for every request, and it is stated here
because §7 depends on it.** `None` means the module's own `urllib.request` client.
Nothing in Pressless passes it; tests hand in a double that answers with
prepared responses and records every request. A module-private global
patched by name would work equally well for tests and would leave the
surface silent about it, which is what an implementer would otherwise
have to invent. **The one other seam is the platform test for §4.5's
Windows check**: the module attribute `_ON_WINDOWS`, read on each call,
which INV-11's test sets.

**Three things about the seam are part of the contract, because a test
double must supply all three.** It returns the response **headers**, which
is where a rate-limit hint arrives and without which §4.3's retry could
not read one. It signals *no answer* by raising `OSError`; every HTTP
status, error statuses included, is returned rather than raised, so the
module owns the mapping to §4.1's types and a double does not have to
guess it. And `wait` is the pacing clock: the module never calls `sleep`
itself, so a test observes the spacing INV-9 asserts by recording calls
rather than by waiting real seconds.

### 4.2 Working out what differs, without downloading anything

The repository's current state is read once, as a recursive tree listing.
That listing carries each file's path and its git blob hash; it does not
carry file content.

A local file is unchanged when its own git blob hash equals the hash the
listing gives for that path. The hash is computable locally, so an
unchanged file is never uploaded and never downloaded.

**Measured 2026-08-26**, because the rule the whole design rests on was
otherwise being recalled:

```
printf 'hello world\n' > f.txt; head -c 2048 /dev/urandom > f.bin; : > f.empty
git hash-object f.txt f.bin f.empty
python3 -c 'import hashlib,pathlib,sys
for n in sys.argv[1:]:
    d=pathlib.Path(n).read_bytes()
    print(hashlib.sha1(b"blob %d\0"%len(d)+d).hexdigest())' f.txt f.bin f.empty
```

Both commands agreed on all three, the empty file included. The
computation is `sha1(b"blob " + str(len(data)).encode() + b"\0" + data)`.

**A file is hashed when the folder is read, and read again to be sent**
(PRESS-0088). Only its hash is kept between the two, so a publish holds
about one file's bytes at a time, however large the site. The second
read must give the hash the first one did. Otherwise the publish raises
`PublishError` before the tree is written, and the site is unchanged.
Sending the second read unchecked would publish bytes nothing compared.

**Which branch, and it is not configurable.** All three functions act on
the repository's **default branch**, never on a stored name, and they
reach it two ways. `publish` asks the repository for the branch and then
reads that branch's head, because it needs the name again for the
reference update. `root_entries` and `fetch_previous` read `commits/HEAD`,
which GitHub resolves to the same branch's head, and neither needs the
name — so each spends one request rather than two. A repository with no
commits answers these reads differently, and PRESS-0127 §4.1 says how. Settings holds no branch field, and
adding one would change PRESS-0001's shipped file format and its setup —
so the alternative to resolving it is hard-coding a name that is wrong for
any repository whose default differs. §10 records that nothing here checks
the default branch is the branch GitHub Pages actually serves from.

**A truncated listing is a failure, not a smaller answer.** GitHub caps
the recursive listing and flags a response it had to cut. Treating a cut
listing as the repository's contents would make every missing path look
locally-new and every deletion invisible, so a flagged response raises
`TooLarge` rather than being used.

**Some conditions on the handed folder are refused rather than published,
and §6 is the list; this section owns two of them.** §4.4's stray rule is a
third and is stated there.
A folder that is not a directory is refused before the first request:
`rglob` yields nothing for one and raises nothing, so it would read as a
site with no files and every unprotected path would be deleted. And a
publish that would remove every unprotected path while writing none is
refused once the listing has been read and before the first write — a
finished build is never empty, and §3 decision 1 makes that commit
unrecoverable from inside Pressless. The first raises
`SiteFolderMissing`, the second `SiteWouldBeEmptied` (§6).

### 4.3 Writing the commit

Four steps, in this order, and the last one is the only one that changes
what a reader sees:

1. **One blob per changed file**, created explicitly and always
   base64-encoded. GitHub's tree endpoint also accepts inline content,
   and its documentation does not state what encoding that field takes —
   so this design does not use it. One rule covers prose and photographs
   alike rather than two rules split by a property of the file.
2. **One tree**, built on the current commit's tree, listing every
   changed path against its new blob and every removed path against a
   null hash.
3. **One commit**, whose parent is the commit the listing was read from.
4. **One reference update**, never forced.

**The site is unchanged until step 4.** Blobs and trees that nothing
points at are invisible to a reader and are collected by GitHub. So an
interruption at any earlier point leaves the site exactly as it was,
which is what lets the Face tell the writer *"your site has not
changed"* truthfully rather than hopefully.

**Never forcing step 4 is what makes a moved branch safe.** The commit's
parent is the state that was read, so if anything else has written to the
branch meanwhile the update is not a fast-forward and GitHub refuses it.
That refusal becomes `Conflict`. Forcing it would silently discard the
other write.

**Writes are paced, and a breach is honoured rather than raised.**
GitHub's documentation ADVISES at least a second between successive write
requests, and a breach is answered with a retry hint rather than a plain
refusal. Advice and enforcement are different things here, and the split
below turns on the difference: what is advised of writes generally is not
what is enforced on blob creation.

**A blob write is paced faster than the other three, and the split is
measured rather than advised.** PRESS-0092 sent 550 blob creations
inside ONE rate-limit hour, serial, every one accepted, at a sustained 136 a
minute — so the run itself took about four minutes, and it is past both
documented content-generating thresholds, the 80 a minute and the 500 an
hour. **It reached 550, not a first publish's full count**: ADR-0002's
figure is larger, so the hourly budget beyond 550 is measured by nothing and
the primary limit is what would answer if it bit. So the second is not what GitHub
requires of blob creation, and a first publish is almost all blobs: at a
second each, ADR-0002's figure puts over fourteen minutes of a first publish
in deliberate waiting. **Blobs are paced at half a second**, which holds the
rate under the 136 a minute that was measured accepted rather than removing
the pace. **The tree, the commit and the reference update keep the full
second**: those three are plausibly the content-generating requests the
documented limits are about, nothing has measured them, and there are three
of them per publish, so pacing them costs nothing worth having.

**The pace before a write is the pace THAT write requires**, not the one
before it — a tree write following a blob waits the full second. Otherwise
the rule depends on ordering, and the three slow writes are exactly where
being wrong is least recoverable. The
Publisher waits as asked and retries, a bounded number of times; only when
that is exhausted does it raise `RateLimited`. Raising on the first hint
would fail a first publish for a condition GitHub expects the caller to
wait out. A first publish writes the whole site and is therefore slow —
ADR-0002 says so — and every publish after it writes a handful of files.

**The hint arrives three ways, and one too long to honour is refused.** A
secondary limit answers 429, or 403 carrying a `Retry-After`, or 403 with
neither header and a message naming the rate limit. GitHub's REST
rate-limit documentation asks that last one to be waited out for at least a
minute (read 2026-11-17). The primary limit sends no `Retry-After` at all:
it reports a spent budget as `x-ratelimit-remaining: 0` and names when it
resets. **The hints are read only on a 429, or on a 403 carrying one of
them** — never on a status that succeeded. A response that succeeded can
carry a spent budget too, and honouring the header there would make
Pressless sleep after a request that worked; a 403 carrying none of them is
an ordinary refusal and must not be retried. Reading only
`Retry-After` made that an ordinary refusal, which sends the writer to
replace a key that is perfectly good. A hint naming longer than a publish
will block for raises `RateLimited` rather than being slept out, so the
writer is told rather than left waiting. A limit naming no usable interval
waits GitHub's documented minimum rather than the pacing interval, which
would spend the whole retry bound in seconds (PRESS-0046).

**Successive retries wait longer.** GitHub asks for an exponentially
increasing wait between retries, and warns that continuing to request while
limited risks the integration being banned. **Each retry waits the hint
GitHub has JUST given, doubled once for every retry already taken** — so the
first waits exactly what was asked and the growth compounds from there. Not
twice the previous WAIT: the hint is re-read from every response, and the
primary limit's is a countdown to a reset, which shrinks as the reset
approaches. Doubling the previous wait would ignore that and keep growing
past a budget the hint says is coming back. The
growth is ours rather than GitHub's ask, so a grown wait that would pass the
bound is **clamped to it rather than raising** — the refusal above is
reserved for an interval GitHub itself named (PRESS-0113).

### 4.4 What is never touched

Settings holds the untouchable list. An entry on it is **neither written
nor removed**, whatever the handed folder contains. Both halves matter:
a list applied only to deletion still lets a stray file in the folder
overwrite the entry holding the custom domain.

**An entry is a bare repository-root name, and it matches a path's FIRST
segment.** So an entry naming a directory protects everything beneath it,
and one naming a file matches only that file. Comparing whole paths for
equality instead would leave every file inside an untouchable directory
unprotected, which is the failure this list exists to prevent.

**A trailing slash on an entry is ignored rather than trusted to be
absent.** PRESS-0001's `load` accepts `CNAME/` and stores it as written,
so an entry compared exactly would protect nothing while reading as
configured.

**The comparison ignores case, folded with `str.casefold()`.** The operation
is named rather than left to the implementer because §11 requires a second
artefact to agree with it, and `str.lower()` differs on non-ASCII names:
`straße` and `STRASSE` casefold together and lower apart. GitHub's paths are
case-sensitive and the Windows and macOS local filesystems are not, so a
folder holding `cname` beside a repository holding `CNAME` is two paths. No
single casing of the entry is right for both: one casing deletes the entry
holding the custom domain, the other uploads a second file claiming it, and
neither is reported. Ignoring case closes both, because the entry then
protects the local file from being uploaded and the remote file from being
removed. It over-protects a repository that deliberately holds two root
entries differing only in case, and that costs in both directions. A file is
left undeleted, which the writer removes himself. And — the one to watch — a
Builder output whose first segment differs only in case from a stored entry
is then never published, which he cannot remedy from the app. So a stale
entry is worse under this rule than under an exact one, and the list's
derivation must fold case the same way (§11). §2 makes the deletion
unrecoverable, and that asymmetry is what decides it.

Every other path is made to match the folder, deletions included, so a
page the writer removes actually goes.

**The rule is not re-evaluated at publish time.** `docs/design.md` is
explicit: the rule says what the list must contain, and the list is what
the Publisher consults. Deriving it afresh at publish would protect
exactly the pages the writer has just deleted, because the Builder has
stopped producing them.

**The site folder is Pressless's alone, and a stray file is refused rather
than sent.** Decided by the user (2026-09-04, mechanism 2026-09-08). The
Builder produces that folder; anything else in it is an error, and the
publish stops naming the file instead of publishing it. **Refusing is not
skipping**: a skip publishes a correct site and says nothing, so the stray
stays and nobody learns of it. Making it visible is the whole reason this
branch was chosen over a filter.

**Two shapes are refused, because between them they are what the Publisher
can recognise without a manifest of the Builder's output — which does not
exist, and which PRESS-0008 would have to supply.**

**Neither test fires on a path whose first segment the untouchable list
names.** Those are not Pressless's to manage at all — an entry on that list
is neither written nor removed whatever the folder holds — so refusing a
publish over one would fail on a file the Publisher had already decided to
leave alone. Nothing there is read either, so one the writer cannot read
fails nothing. A symlinked `CNAME` is left where it is, not refused. The
dot-name bullet's own carve-out below is this rule, not a second one.

- **Anything that is neither an ordinary file nor a directory** — a symlink,
  a device, a socket, a named pipe. **A directory is descended into, not
  refused**: the Builder puts published files in `content/`, so every real
  site folder holds them, and a rule written as *not an ordinary file* over a
  recursive walk refuses every publish there is. **An entry is classified
  before it is followed, and a symlink is a stray whatever it points at** — a
  symlinked directory refuses rather than being descended into. Measured:
  such an entry answers `is_symlink()` and `is_dir()` both true, so testing
  for a directory first descends through the link and publishes files from
  outside the folder, which the next sentence forbids. **This reverses
  PRESS-0069's sub-decision**, which skipped a
  symlink on the ground that refusing "would fail a publish over something
  harmless". Under this rule it is not harmless: a skipped symlink is a page
  silently absent from the site, which is the same silence the rule exists to
  end. The link's target is still never read.
- **Any path with a dot-name segment, ANYWHERE in it.** That is `.git`,
  `.DS_Store`, an editor's swap file — machine state rather than site output.
  **Any segment, not the first**: macOS writes `.DS_Store` into every
  directory it opens, so a first-segment rule catches `.DS_Store` and misses
  `content/.DS_Store`, which is the one a real site actually acquires. The
  carve-out above is still keyed on the FIRST segment, because that is what
  an untouchable entry matches — so an entry naming a directory exempts
  everything beneath it, and the two rules keep the semantics each already
  had. `.nojekyll` and its kind are on the list, so they are refused by
  nothing and reach the site the way §4.4 already says: an untouchable entry
  is neither written nor removed, so it never travels through the upload at
  all.

**A dot-name the Builder produces must sit under an untouchable first
segment, and that is a constraint PRESS-0008 inherits.** Setup removes Builder output
from the list (§4.4 above), so a dot-name the Builder starts emitting would
fall off it and then refuse every publish, permanently, with nothing telling
the writer why. `.nojekyll` is safe because it is on the list today. Nothing
here can check this: §10 records it.

**What this does NOT claim** is that everything surviving both tests is
Builder output. It cannot: an ordinary non-dot file the writer drops in the
folder still publishes. Closing that needs the Builder to declare what it
wrote, and PRESS-0008 owns it.

`root_entries` is how the list is derived. It reports **every** entry at
the repository root, files and directories alike, as bare names with no
trailing slash. It decides nothing and filters nothing — rule 5 leaves it
unable to tell a stylesheet from an entry, so it cannot know which of them
the Builder produces. Setup and the Face remove those and store the rest.

**That filtering is theirs, and `docs/design.md` names the cost of getting
it wrong:** `content/` is ordinary Builder output, and a list that kept it
would make a deleted poem's source text permanent on the web.

### 4.5 Fetching back

`fetch_previous` reads the current commit's first parent and writes that
state into the folder it is given, optionally narrowed to a path prefix.
It writes files and returns; it does not publish, does not touch the
Store, and does not decide what the fetched state means. Undo is a
sequence the Face owns, and this is one step of it.

**A fetched file lands at `into` joined to its full repository-relative
path, with `prefix` used to select and never to strip.** So `Fetched.paths`
and the layout under `into` are the same strings, and the Face's undo step
reads them without reconstructing anything.

**`fetch_state` fetches a chosen commit, or the default branch's current
one, keeping paths within any of several prefixes** (PRESS-0218 § 4.1). It
shares `fetch_previous`'s body, so every rule of this section holds for
both; `fetch_previous` passes its parent and its one prefix. A repository
with no commits raises `RemoteStateMissing`.

**`prefix` matches on path-segment boundaries, and a trailing slash is
optional and ignored.** Matched as a bare string instead, `content` would
also select `contents.html`, and undo would write into the Store a file the
fetched directory never held. §4.4's untouchable rule tolerates a
trailing slash too. Where the two differ is depth: a prefix may name a path
several segments deep, an untouchable entry may not, and PRESS-0001's `load`
refuses one that does.

Where the current commit has no parent there is nothing before it, and
that raises `NoPreviousState`.

**On Windows, the selected paths are checked before any blob is fetched.**
A path equal, once case is ignored (`str.casefold`), to another selected
path or to a folder above one would land on one file, and a segment
Windows cannot hold fails its write or lands elsewhere — and all of these
used to end as `FetchNotWritten`, whose answer is to free space. The
check raises `UnfetchablePath` naming the first path, in listing order,
that clashes with one before it or holds such a segment, and nothing is
written. A segment Windows cannot hold carries `< > : " | ? * \` or a
control character, ends in a dot or a space, or is a device name:
`con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`, `conin$`,
`conout$` and the superscript `com¹`–`com³` and `lpt¹`–`lpt³`, judged on
the part before the first dot with trailing spaces removed, case ignored.
**(decided here) The check runs on Windows only**: it is about what this
computer's disk can hold, and elsewhere those paths fetch correctly, so
refusing there would take a working undo away. Pressless ships for Linux
and Windows only (`docs/design.md` § The stack, and what it rules out), so Windows is the one
case-insensitive disk it writes to. Under `content/` the Store's own names
cannot trip it — its slug test refuses device names (PRESS-0067) — so it
fires on a repository something other than Pressless wrote.

**No fetched file lands at its final path under `into` until every file
has been fetched.** Written as they go, a failure part-way leaves a mixture
of the previous state and whatever was already there — which the Face
cannot tell from a complete fetch, and undo is the feature that must not
produce one (PRESS-0046). Staging goes in a temporary directory **inside**
`into`, so the moves that follow are renames on one filesystem; staged
beside it, each would be a cross-filesystem copy that can fail half-done.

**A residual window remains, and it is not closed here.** The move phase is
one rename per fetched file, not one rename: a failure part-way through it
leaves the files already moved at their final paths. So the mixture this
paragraph says undo must not produce is still reachable, in a narrower
window than writing as-you-go. Making the move phase itself all-or-nothing
is a design change this document does not take; §10 records that nothing
checks it, and PRESS-0015 must not be built assuming `into` is never part
old and part new.

**The consequence of §3 decision 1 lives here.** A second `fetch_previous`
called after an undo has been published reads the parent of the undo
commit, which is the state the undo replaced. That is the decided
behaviour.

**PRESS-0333 § 4.1 and § 4.5 add to the setup reads.** `Pages` gains
`built_by_actions` and `domain`, and `switch_pages_to_branch`, `head_commit`
and `default_branch` are added.

### 4.6 What this module never does

- It never reaches Credentials. Rule 10 hands it a key.
- It never reaches the Store, the Builder, Marks or the Face.
- It never writes prose for the writer.
- It never decides what a draft is. Rule 4 carries S7, and rule 5 says
  this part has nothing to decide with.
- It never keeps state between calls.

## 5. Invariants

- **INV-1** — `src/pressless/publisher.py` imports no `pressless` module
  other than `pressless.settings` and `pressless.https`, the HTTPS client
  it shares with Insights and usage reports (PRESS-0331), and
  `pressless.os_reason`, which gives a failure its reason without its path
  (PRESS-0401), and `pressless.progress`, which a long fetch or publish
  tells how far it has got (PRESS-0435). None imports a `pressless` module
  itself, so no route to Credentials runs through them.
  *Test:* `tests/test_publisher.py::test_publisher_imports_no_forbidden_sibling`,
  walking the module's imports as
  `tests/test_settings.py::test_settings_imports_nothing_forbidden` does,
  and `tests/test_https.py::test_https_imports_no_pressless_module`.
  *Breaks when:* an implementer imports `pressless.credentials` to fetch
  the key rather than taking it as an argument, which is the breach of
  rule 10 that rule 5 was rewritten to avoid.
  **It is a weak test in the way this project has already met:** an
  import walk passes against a module that does nothing. It is evidence
  about imports and never about where the key came from.

- **INV-2** — An entry on `settings.untouchable` is neither written nor
  removed, matched against a path's first segment and ignoring case. This
  holds when the handed folder contains a file of that name and when it
  does not, and it holds for every path beneath an entry naming a
  directory.
  *Test:* `tests/test_publisher.py::test_untouchable_is_neither_written_nor_removed`
  — three fixtures: the folder holds a *differing* file at an untouchable
  path; it holds nothing there; and the repository holds files beneath an
  untouchable *directory*. Assert the recorded requests carry no tree
  entry for any of them. All three match casing exactly, so none of them
  observes the case clause. That is
  `tests/test_publisher.py::test_an_untouchable_entry_protects_whatever_its_casing`,
  separate rather than a fourth fixture here: this test asserts a breach
  by exact membership, so a case fixture added to it could not bite.
  *Breaks when:* an implementer applies the list to deletions only,
  which reads as protection and leaves the entry overwritable. And when
  the comparison is exact, which breaks in two directions of which only
  one deletes anything. A stored entry the REMOTE path's first segment
  cannot match leaves that path unprotected, so it is removed — §4.4's
  unrecoverable case. A stored entry the LOCAL path's cannot match
  uploads a second file claiming the same address and removes nothing. A
  fixture built from the second and asserted against the first passes
  green on the breach it was written to catch.
  **Only this rule can reject the write fixture:** every other rule in
  §4.4 makes a differing file an ordinary upload.

- **INV-3** — No request that changes the branch is made until every
  blob, the tree and the commit have succeeded. The reference update is
  the last write of a publish, and a transport failure raised *by that
  request* surfaces as `OutcomeUnknown`, never as the `Unreachable` any
  earlier step raises — PRESS-0127's start write aside, whose own failure
  is `OutcomeUnknown` too.
  *Test:* `tests/test_publisher.py::test_reference_update_is_last` — a
  recording transport; assert the reference update is the final entry,
  that a transport failing at the tree or commit step makes no reference
  request at all and raises `Unreachable`, and that one failing on the
  reference request itself raises `OutcomeUnknown`.
  *Breaks when:* an implementer updates the branch per batch to make a
  large first publish resumable, which is the change that turns a
  half-finished publish into a half-updated site.
  *Amended by PRESS-0127:* a repository with no commits is first
  started with one file of the folder, before any blob (PRESS-0127 §4.4).

- **INV-4** — A file whose local git blob hash equals the hash in the
  repository listing is not uploaded, and a publish where no file differs
  writes no commit and returns an empty `Outcome.commit`.
  *Test:* `tests/test_publisher.py::test_unchanged_files_are_not_uploaded`
  — publish against a listing that already matches the folder; assert no
  blob request, no commit request, and an empty commit sha.
  *Breaks when:* an implementer compares modification time or size,
  either of which reports a rewritten-but-identical file as changed —
  which is exactly what the Builder produces on every run.

- **INV-5** — The reference update is never forced, and a branch that
  moved since the listing was read raises `Conflict` rather than
  overwriting.
  *Test:* `tests/test_publisher.py::test_branch_that_moved_is_a_conflict`
  — assert no request body sets force TRUE, the update sending it
  explicitly false; and that a refused update surfaces as `Conflict`.
  *Breaks when:* an implementer forces the update to clear a failure seen
  during development, which converts a refusal into silent data loss.
  **Asserting the type is what makes it bite:** an unreachable network
  also produces no successful update, so a clause asserting only that
  something was raised passes against an implementation reporting a
  conflict as a network fault.

- **INV-6** — A listing GitHub flags as cut short raises `TooLarge` and
  is never used to compute what differs.
  *Test:* `tests/test_publisher.py::test_truncated_listing_is_refused` —
  a listing carrying the truncation flag; assert `TooLarge` and that no
  blob request follows.
  *Breaks when:* an implementer reads the entries and ignores the flag,
  which makes every unlisted path look new and every deletion invisible.

- **INV-7** — No failure raised by this module carries the key, in its
  message or its representation. **Those two are the surfaces it
  covers.** The key also sits as a value in the request headers of the
  frame that raises, where a handler printing a traceback's local
  variables would show it. `docs/design.md` § Errors closes that surface
  rather than this module: the Face shows a typed failure's own words and
  an unforeseen one's type alone, never a raw traceback.
  *Test:* `tests/test_publisher.py::test_no_failure_names_the_key` —
  force each failure type with a recognisable key value; assert that
  value appears in neither `str()` nor `repr()` of what is raised.
  *Breaks when:* an implementer includes the request headers in an error
  to make a failure diagnosable, and the key is a header.

- **INV-8** — `fetch_previous` reads the current commit's first parent,
  names the sha it fetched, and raises `NoPreviousState` where the
  current commit has no parent.
  *Test:* `tests/test_publisher.py::test_fetch_previous_names_its_source`
  and `::test_first_commit_has_no_previous_state`.
  *Breaks when:* an implementer resolves "previous" against the branch's
  second-newest commit by listing history, which differs from the first
  parent as soon as anything is merged.

- **INV-9** — Successive write requests are separated by the pacing wait
  **the FOLLOWING write requires** — half a second before a blob, a full
  second before the tree, the commit and the reference update (§4.3) — and a
  retry hint short enough to honour is waited out and retried rather than
  raised.
  *Test:* `tests/test_publisher.py::test_writes_are_paced_and_hints_retried`
  — a recording transport capturing the wait between writes, plus one
  answering the first write with a retry hint; assert the write is retried
  and that `RateLimited` is raised once the bound is exhausted. §4.3 owns
  the hint too long to honour, which is refused without waiting at all.
  Plus `::test_each_write_is_preceded_by_its_own_pace` — a two-file publish,
  asserting the recorded wait SEQUENCE is `[0.5, 1.0, 1.0, 1.0]`. **The
  sequence, not a count and not a set**: a count passes a single flat pace,
  and a set passes the split applied AFTER each write instead of before the
  next — which under-paces the TREE write, the first of the three slow ones,
  and is the ordering §4.3 warns of. Only the tree: the commit and the
  reference update still follow a slow write and still get their second.
  *Breaks when:* an implementer writes as fast as the loop allows; or keeps
  one flat pace for all four, which is what shipped before PRESS-0114 and
  passes any assertion about how MANY waits there were; or inverts the two
  values.

- **INV-10** — A publish REFUSES, naming the path, where the handed folder
  holds **a symlink**, anything else that is neither an ordinary file nor a
  directory, or a path carrying a dot-name segment — **in either case only
  where the untouchable list does not name the path's FIRST segment**. The
  symlink is named FIRST and separately because a symlink to a directory
  answers `is_dir()`: written as *neither a file nor a directory* alone, the
  rule does not reach it, and the link is descended into. Nothing is
  written and nothing is removed; the site is unchanged (§4.4).
  *Test:* `tests/test_publisher.py::test_a_stray_file_refuses_the_publish`
  — a folder carrying a symlink to a FILE, one a symlink to a DIRECTORY, one
  `.git/config`, and one `content/.DS_Store`. Assert **`StrayFile`** naming
  the offending path, and that the transport recorded no write — the type
  by name, on §10's rule.
  **The symlinked DIRECTORY and `content/.DS_Store` are what carry the
  rule.** The first is the case an *ordinary file or directory* test passes:
  it answers `is_dir()`, so such a rule descends the link and publishes what
  it points at. The second is the case a FIRST-segment test passes, and it
  is the one a real site acquires. A plain `content/` subdirectory must NOT
  refuse, or the rule refuses every real site;
  `::test_a_plain_subdirectory_does_not_refuse` is that half. Plus
  `::test_an_untouchable_dot_name_does_not_refuse`, a
  folder carrying `.nojekyll` with that name on the untouchable list, and
  `::test_an_untouchable_symlink_does_not_refuse`, a folder whose `CNAME` is
  a symlink with `CNAME` on the list. **Both halves of the carve-out need a
  fixture**: the dot-name one alone leaves an implementation that carved out
  only that limb passing every assertion here, and the limb it missed
  refuses every publish for good.
  *Breaks when:* the stray is SKIPPED rather than refused. That publishes a
  correct site and says nothing, so the writer never learns the file is
  there — the silence §4.4 chose this branch to end, and the shape the
  symlink case shipped as until PRESS-0089.

- **INV-11** — On Windows, `fetch_previous` refuses a listing whose selected
  paths clash by case or name a segment Windows cannot hold, raising
  `UnfetchablePath` naming the path, before any blob is read; elsewhere the
  same listing fetches.
  *Test:* `tests/test_publisher.py::test_a_path_windows_cannot_hold_is_named`
  — with `_ON_WINDOWS` set, one listing each holding `content/A.txt`
  beside `content/a.txt`, `content/Post` beside `content/post/x.txt`,
  `content/published/con.txt`, `content/nul .jpg`, `content/x:y.txt`,
  `content/a\b.txt` and `content/dot.`. Each raises `UnfetchablePath`
  whose message names the later path, the double records no blob read,
  and `into` holds no file. Plus
  `::test_a_path_windows_cannot_hold_fetches_elsewhere`: with it cleared,
  on a host that is not Windows, the `con.txt` listing fetches.
  *Breaks when:* the check runs after staging, so a clash overwrites one
  file with the other in silence; or it runs everywhere, and Linux loses
  undo for a site holding such a path.

- **INV-12** — The reference update or the start write answered with a
  2xx other than 200 or 201, or with a body that does not parse, raises
  `OutcomeUnknown`, and so does a start-write answer naming no commit. Any
  write answered 307 or 308 raises `RepositoryMoved` and is not sent again.
  *Test:* `tests/test_publisher.py::test_an_odd_success_is_unknown`: the
  reference update answered 202, then answered 200 with a body that is
  not JSON, each raises `OutcomeUnknown`; so do the start write answered
  204 and the start write answered 201 with `{}`.
  `::test_a_redirected_write_names_the_move`: a blob write answered 307
  and the reference update answered 308 each raise `RepositoryMoved`, and
  neither request is sent again. `::test_the_client_follows_no_redirected_write`
  drives the module's own client against a fake opener: a POST, a PATCH
  and a PUT answered 307 and 308 each come back as that status, with one
  request made.
  *Breaks when:* an odd 2xx falls to the base type, whose row says
  unchanged; or a redirected write is followed, publishing to a
  repository the settings do not name.

- **INV-13** — A publish holds no file's bytes from the comparison to the
  commit, and a file whose second read differs from its first refuses the
  publish before the tree is written (§4.2).
  *Test:* `tests/test_publisher.py::test_a_publish_holds_one_file_at_a_time`:
  twenty 1 MiB files publish with peak traced memory under eight of them.
  `::test_a_file_changed_during_the_publish_is_refused`: a file rewritten
  as the first blob is sent raises `PublishError` naming it, and no tree
  is written.
  *Breaks when:* every file's bytes are kept from the comparison on; or
  the second read is sent without its hash being checked.

## 6. Failure modes

| What happens | What is raised | What the writer's site is |
|---|---|---|
| The handed folder is not a directory | `SiteFolderMissing` | unchanged |
| `fetch_previous` cannot write into the folder it was handed — full disk, unwritable folder | `FetchNotWritten` | unchanged |
| `fetch_previous`, on Windows, selects two paths equal but for case, or a path Windows cannot hold (§4.5) | `UnfetchablePath` | unchanged |
| The handed folder holds a stray — a symlink, anything else neither an ordinary file nor a directory, or a path carrying a dot-name segment, in either case under a first segment the untouchable list does not name (§4.4) | `StrayFile` | unchanged |
| The publish would remove every unprotected path and write none | `SiteWouldBeEmptied` | unchanged |
| No answer from GitHub, before the reference update — PRESS-0127's start write aside | `Unreachable` | unchanged |
| No answer from GitHub, **during** the reference update or PRESS-0127's start write | `OutcomeUnknown` | **unknown — may or may not have changed** |
| GitHub answers a server error **to** the reference update or PRESS-0127's start write | `OutcomeUnknown` | **unknown — may or may not have changed** |
| GitHub answers the reference update or PRESS-0127's start write with a 2xx other than 200 or 201, or with a body that is not JSON; or answers the start write without naming its commit | `OutcomeUnknown` | **unknown — may or may not have changed** |
| GitHub answers a write with a 307 or 308 redirect — its answer for a repository that was renamed or moved | `RepositoryMoved` | unchanged |
| Key rejected, or no write access | `Refused` | unchanged |
| The same, where the key is a GitHub App sign-in's pass (it starts `ghu_`) | `SignInRefused`, a `Refused` | unchanged |
| `settings.repository` resolves to nothing, on the request that names the repository itself | `RepositoryMissing` | unchanged |
| Something asked for INSIDE a repository that answers is absent — a deleted branch, a missing blob | `RemoteStateMissing` | unchanged |
| Branch moved since the listing was read — not a read GitHub answers as an empty repository, which PRESS-0127 §4.1 owns | `Conflict` | unchanged |
| A documented GitHub limit was hit | `TooLarge` | unchanged |
| Retry hints exhausted | `RateLimited` | unchanged |
| Pressless stops before the reference update (crash, power loss) | nothing — the process is gone | unchanged |
| `fetch_previous` on a first commit | `NoPreviousState` | unchanged |
| GitHub answers a status no row above names — a server error before the reference update, the start write aside, among them — or a file in the handed folder cannot be read, or changes between its hashing and its sending | `PublishError` itself | unchanged |

**These five rows each carry their own type**, added 2026-09-08 by
PRESS-0116. Four refuse before anything reaches GitHub;
`RemoteStateMissing` can arrive later, and stays *unchanged* on §4.3's
property rather than on its timing. They shared the bare `PublishError`,
and `docs/design.md` § Errors requires the Face to end each message with
what to do next — which for these five differs. §4.1 pairs each type with
its answer, and the rows below are in a different order, so neither list
can be read off the other. A shared type left the Face inventing a discriminator or giving one
generic answer to five different situations, which is the failure § Errors
names. It is the same ground `OutcomeUnknown` is its own type on.
`UnfetchablePath` joined them 2026-09-27 (PRESS-0160), on the same ground,
and `RepositoryMoved` the same day (PRESS-0167): his next step is to enter
the repository's new name, which `RepositoryMissing`'s *check the name*
does not tell him.

**A redirect on a write is never followed.** A read follows GitHub's
redirect to the new name; a write comes back as the 307 or 308 itself,
because `urllib` follows neither for POST or PATCH. Following it would
publish to a repository Settings does not name, so the writer is told
instead, and nothing was written: GitHub redirects before it acts.

**An odd success is unknown, not unchanged.** A 2xx is GitHub saying it
acted. On the two writes that can move the site — the reference update
and PRESS-0127's start write — a 2xx other than 200 or 201, a body that
does not parse, or a start-write answer naming no commit cannot say how,
so it is `OutcomeUnknown`. Reported as the
base type, whose row says *unchanged*, it told the writer nothing moved
after the update was applied (PRESS-0166).

**Every row but three says *unchanged*, and those three are the ones that
matter.** §4.3's property is that nothing a reader sees changes until the
reference update — so a failure *during* that update is the case where the
site's state is genuinely unknown. Reporting it as unchanged
would tell the writer his site had not moved when it had, which is exactly
the S6 promise §2 says this design exists to keep. **A server error is that
same case and not a refusal**: a gateway can fail after the update was
applied, so it leaves the state exactly as unknown as a dropped connection
does. Every other status is a definitive answer — GitHub authenticates and
validates before it acts — so each keeps its own row and its *unchanged*
(PRESS-0046). `OutcomeUnknown` is a
type of its own so the Face has something to branch on — a shared type
would leave it unable to tell the two apart. It must say the outcome is
unknown rather than claim either; confirming would mean reaching GitHub,
which is by definition what has just failed.

The Face turns each row into the three-part sentence `docs/design.md`
§ Errors requires; this module writes none of them.

## 7. Tests

`tests/test_publisher.py`, following the pattern of
`tests/test_credentials.py`.

**No test here reaches the network.** Every test of `publish`,
`root_entries` and `fetch_previous` hands in a double through §4.1's
`transport` argument — a recorder that answers with prepared responses and
keeps every request. INV-1's import walk hands in nothing, and the tests of
the module's own client drive it against a fake opener instead. That is what lets INV-3, INV-5
and INV-9 assert on request *order*, *absence* and *spacing*, which is
where this module's real risks are.

**A recording double is the test surface, not a convenience.** ADR-0002
notes that git's own safety checks are gone, so the checks have to be on
what Pressless sends. Assertions about the requests are the only place
that is observable.

Green against a stub that declares the surface and raises
`NotImplementedError`: INV-1 alone. Every other invariant needs the real
code, so a green INV-1 says nothing about the rest.

## 8. Alternatives considered (and rejected)

- **Shelling out to `git`.** Rejected by ADR-0002: it requires the writer
  to install and configure git, which is the problem this project exists
  to remove.
- **Undo that skips past previous undos.** Offered to the user
  2026-08-26 and declined in favour of §3 decision 1. It never restores a
  rejected version, at the cost of marking which commits were undos and
  of an undo whose effect depends on history the writer cannot see.
- **Undo disabled after one press.** Offered the same day and declined.
  It cannot restore a rejected version either, and needs nothing marked —
  but it leaves no way back beyond one step.
- **Inline file content in the tree request.** Rejected in §4.3: the
  documented field does not state its encoding, so photographs would rest
  on an assumption. Explicit base64 blobs cost one request per changed
  file and remove the question. Measured 2026-09-08 (PRESS-0092): the
  field stores what it is given as UTF-8 text and does not base64-decode
  it, and arbitrary bytes cannot be expressed in a JSON string at all, so
  it could not carry photographs even if the encoding were stated.
- **A third-party HTTP library.** Rejected by §3 decision 3 — a runtime
  dependency bought for syntax, which PRESS-0022 would then have to
  package.
- **Updating the branch in batches during a large first publish.**
  Rejected by INV-3: it makes the first publish resumable and every
  publish interruptible into a half-updated site, trading the property
  S6 depends on for a convenience on a run that happens once.

## 9. Out of scope

- **Deciding what is published.** Rule 4 gives that to the Builder.
- **The undo sequence itself.** Rule 1 gives the ordering to the Face;
  this module supplies one step of it.
- **Deriving and storing the untouchable list.** `root_entries` reports;
  setup and the Face decide and store.
- **Progress reporting during a slow first publish.** The Face's — and
  `publish` hands it nothing to state a proportion from: it takes no
  callback and returns only once the commit is made. So the Face can show
  that a publish is running and not how far through it is. §4.3 owns why a
  first publish is the slow one.
- **Photograph originals.** They never reach the site folder, so this
  module never sees one.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_publisher.py::test_publisher_imports_no_forbidden_sibling` |
| §4.2's two folder preconditions | `tests/test_publisher.py::test_a_site_folder_that_is_not_a_directory_is_refused` and `::test_a_publish_that_would_empty_the_site_is_refused` |
| §4.4's trailing-slash tolerance | `tests/test_publisher.py::test_an_untouchable_entry_with_a_trailing_slash_still_protects` |
| §4.4's case tolerance | `tests/test_publisher.py::test_an_untouchable_entry_protects_whatever_its_casing` |
| INV-2 | `tests/test_publisher.py::test_untouchable_is_neither_written_nor_removed` |
| INV-3 | `tests/test_publisher.py::test_reference_update_is_last` |
| INV-4 | `tests/test_publisher.py::test_unchanged_files_are_not_uploaded` |
| INV-5 | `tests/test_publisher.py::test_branch_that_moved_is_a_conflict` |
| INV-6 | `tests/test_publisher.py::test_truncated_listing_is_refused` |
| INV-7 | `tests/test_publisher.py::test_no_failure_names_the_key` |
| INV-8 | `tests/test_publisher.py::test_fetch_previous_names_its_source` and `::test_first_commit_has_no_previous_state` |
| That GitHub behaves as §4.3 describes | **nothing here** — no test reaches the network, so every assertion is about what Pressless sends and none about what GitHub does with it. PRESS-0022 stages a built artefact before release; the first real publish is where this is observed |
| §3 decision 1's consequence — a second undo restoring the rejected version | **nothing, and nothing should** — it is the decided behaviour, recorded here so a later reader does not fix it as a bug |
| Whether the stored untouchable list is still correct | **nothing** — a file added to the repository root outside Pressless is unprotected until `root_entries` is run again. `docs/design.md` names this and gives the Face a re-derive action; no check here can see it |
| The documented GitHub limits being the real ones | **nothing** — INV-6 refuses a listing GitHub itself flags, which needs no number. The limits in §4.3's reasoning are not asserted anywhere and would go stale silently if they were |
| INV-9 | `tests/test_publisher.py::test_writes_are_paced_and_hints_retried` and `::test_each_write_is_preceded_by_its_own_pace`, which asserts the wait sequence rather than a count |
| What the Face branches on to tell §6's own-type rows apart | **the type itself** — §4.1 declares `SiteFolderMissing`, `StrayFile`, `SiteWouldBeEmptied`, `FetchNotWritten`, `RemoteStateMissing`, `UnfetchablePath` and `RepositoryMoved`, and pairs each with the answer its message ends on. PRESS-0116 settled it; PRESS-0011 branches on type rather than on a discriminator of its own |
| INV-10 | `tests/test_publisher.py::test_a_stray_file_refuses_the_publish`, `::test_a_plain_subdirectory_does_not_refuse`, `::test_an_untouchable_dot_name_does_not_refuse` and `::test_an_untouchable_symlink_does_not_refuse` |
| INV-11 | `tests/test_publisher.py::test_a_path_windows_cannot_hold_is_named` and `::test_a_path_windows_cannot_hold_fetches_elsewhere` |
| INV-12 | `tests/test_publisher.py::test_an_odd_success_is_unknown`, `::test_a_redirected_write_names_the_move` and `::test_the_client_follows_no_redirected_write` |
| INV-13 | `tests/test_publisher.py::test_a_publish_holds_one_file_at_a_time` and `::test_a_file_changed_during_the_publish_is_refused` |
| That `fetch_previous`'s move phase is all-or-nothing | **nothing, and §4.5 says why** — it is one rename per file, so a failure part-way leaves the files already moved at their final paths. Closing it is a design change this document does not take; PRESS-0015 must not be built assuming otherwise |
| That the Builder emits no dot-name segment outside an untouchable first segment | **nothing here** — setup removes Builder output from the untouchable list, so a dot-name the Builder starts emitting would refuse every publish permanently. PRESS-0008 owns not emitting one, and nothing in this module can see it |
| Whether everything surviving §4.4's two stray tests IS Builder output | **nothing, and nothing here can** — an ordinary non-dot file the writer drops in the folder still publishes. Closing that needs the Builder to declare what it wrote, which is PRESS-0008's |
| §6's server-error route to `OutcomeUnknown` | `tests/test_publisher.py::test_a_server_error_on_the_reference_update_is_outcome_unknown`, which also holds a refusal to its own row |
| §6's two 404 rows — the repository itself against something inside it | `tests/test_publisher.py::test_a_missing_blob_is_not_reported_as_a_missing_repository`, which holds both sides |
| §4.3's two hint shapes, and the bound on one | `tests/test_publisher.py::test_the_primary_rate_limit_is_waited_out_not_read_as_a_refusal`, `::test_a_rate_limit_naming_no_interval_waits_the_documented_minute` and `::test_a_wait_longer_than_the_bound_is_refused_rather_than_slept` |
| §4.3's third hint shape, a 403 whose message names the rate limit | `tests/test_publisher.py::test_a_secondary_limit_naming_no_interval_is_waited_out`, with `::test_a_plain_refusal_is_still_a_refusal` holding a 403 that names none to `Refused` |
| §4.4's untouchable entries left unread | `tests/test_publisher.py::test_nothing_on_the_untouchable_list_is_read` |
| §4.3's growth between successive retries, and its clamp | `tests/test_publisher.py::test_successive_retry_waits_grow_rather_than_repeating` and `::test_grown_retry_waits_stop_at_the_bound_rather_than_raising` |
| §4.5's all-or-nothing fetch | `tests/test_publisher.py::test_a_fetch_that_fails_part_way_leaves_the_folder_as_it_was` |
| Whether the pacing interval is long *enough* under real load | **nothing** — INV-9 fixes that the wait and the retry exist, which is falsifiable here. Whether the interval suffices is observable only against the real service, on a first publish |
| That the default branch is the branch GitHub Pages serves from | **nothing** — §4.2 resolves the default branch, and a repository serving Pages from another branch would publish successfully while the live site never changed. No check here can see it; the first real publish is where it shows |

**§6's own-type rows are asserted BY TYPE NAME, never by
`PublishError`.** Every §4.1 type subclasses it, so the base name passes
against a module raising the bare type at every site, and the mapping the
Face branches on is then checked by nothing. The tests that own it are
`::test_a_site_folder_that_is_not_a_directory_is_refused`,
`::test_a_publish_that_would_empty_the_site_is_refused`,
`::test_a_stray_file_refuses_the_publish`,
`::test_a_fetch_that_cannot_be_written_is_a_typed_failure`,
`::test_a_missing_blob_is_not_reported_as_a_missing_repository` and
`::test_a_path_windows_cannot_hold_is_named`. Each names
its own type; the rows above credit them on that condition.

## 11. Cross-doc impact

- **`docs/design.md` § What may depend on what — rule 5 named no write.
  Closed by PRESS-0026 on 2026-08-27, not by this spec.** §4.5 has
  `fetch_previous` write a fetched state into a folder it is handed, and
  rule 5 did not cover it. Rule 5 now takes rule 8's form. Its own gate
  found that naming the local write alone made things worse — it turned
  an omission into an exhaustive write list that excluded the Publisher's
  GitHub traffic — so the rule grants that traffic too.
- `docs/design.md` § The parts is unchanged, and rules 7 and 10 are used
  as they stand — which is what §3 decision 2 records.
- `docs/design.md`'s untouchable paragraph names both of §4.4's
  tolerances, case and the trailing slash (PRESS-0112).
- **The list's derivation must fold case the way §4.4 does.** §9 puts the
  derivation outside this spec, and Setup's filter removes everything the
  Builder produces. An exact-cased filter against a case-folding
  Publisher leaves a stale entry such as `Index.html` on the list, after
  which `index.html` is never uploaded and never removed and the home
  page silently stops updating. Two settlements of one question,
  disagreeing through the stored list. PRESS-0001 §9 names PRESS-0021 as the
  derivation's owner, so that item carries the requirement; §4.4 pins the
  fold by name so both artefacts bind to one operation.
- `ROADMAP.md` PRESS-0009 — its body records §3 decision 1 as settled.
  Nothing further is owed there.
- `ROADMAP.md` PRESS-0010 — **absorbed into this spec as an umbrella**,
  per the header. Its bullet stays as its own unit of work and closes with
  the code this contract governs; nothing about its scope moves. PRESS-0014
  and PRESS-0015, which depend on it, are unaffected.
- `docs/design.md` § Errors names both of §6's routes to
  `OutcomeUnknown` (PRESS-0096).
- `docs/decisions/ADR-0002` is unchanged and is this spec's source.
- `CHANGELOG.md` — an entry when it ships.
- PRESS-0001 and PRESS-0002 are unchanged. This spec consumes
  `settings.repository` and `settings.untouchable` as shipped, and takes
  its key as an argument rather than reaching PRESS-0002 at all.
- PRESS-0019 is unaffected. It shares rule 10's hand-off shape but no
  code.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0009-publisher-loop-log.md`.
