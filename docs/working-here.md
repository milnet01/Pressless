# Working here — read when the task comes up

Notes `CLAUDE.md` points at, each by the task that needs it. They were
moved out of it, word for word, because it is read on every turn
(PRESS-0177). Read one section at a time: `read_region` with `section=`
and the heading below.

## Archive tests and a fresh clone's keys

**The archive test files are skipped in CI and they are the most
important ones.** `tests/test_marks_archive.py`,
`tests/test_store_archive.py` and `tests/test_store_extras_archive.py`
prove S2 against the real WordPress export, which is personal data and
cannot live in a public repository — so they run only where that file
is, and a green CI run says nothing about any of them. The gate points
`PRESSLESS_ARCHIVE` at a path held in a machine-local git config key:

```bash
git config ants.pressless.archive /path/to/wordpress-export.xml
```

**The first two need a second thing the third does not**, and it decides
what a green push proves. They load the sibling generator in a private
workspace, so they skip where no generator is found at all — which
includes the isolated checkout the pre-push hook builds, unless
`PRESSLESS_GENERATOR` is exported in the pushing shell. **Absence is the
only skip** (PRESS-0108): a generator that is present and will not load,
has been renamed, or is one of several candidates is a FAILURE naming
its cause. Set `PRESSLESS_GENERATOR` to pin which generator is read.
`test_store_extras_archive.py` keys comments by the export's own post id
and needs nothing but the export, so it DOES run at pre-push. Read the
skip reasons, not the exit code.

Or set it for one run:

```bash
PRESSLESS_ARCHIVE=<path to the WordPress export> python3 -m pytest
```

`tests/test_importer_archive.py` proves Import against the same export
(PRESS-0007). Its INV-6, INV-7 and INV-11 tests run the whole import, so
they also need the photograph originals, the live site's folder and
today's header and footer templates, each held the same way; its INV-2
and INV-3 tests need the sibling generator; INV-5's needs the export
alone:

```bash
git config ants.pressless.originals /path/to/originals
git config ants.pressless.liveSite /path/to/the/live/site
git config ants.pressless.templates /path/to/the/templates
```

`tests/test_builder_archive.py` proves the Builder against the live site
(PRESS-0008 INV-15). It imports the archive first, so it needs all of the
above, and it builds with the site's own name and address. Both identify
the writer, so they are machine-local values the gate exports as
`PRESSLESS_SITE_NAME` and `PRESSLESS_SITE_ADDRESS`. Read them off the live
site — its page titles and `sitemap.xml` — never from memory:

```bash
git config ants.pressless.siteName '<the name after the dash in a page title>'
git config ants.pressless.siteAddress '<the address sitemap.xml lists>'
```

## Writing or changing tests

**Two test results mean less than they look.** `test_marks_is_pure`
(INV-7) passes against *any* module that imports and calls nothing
forbidden — an empty file included — so it is evidence about imports and
calls, never about the code working. And with `marks.py` absent the suite
errors at *collection*, so no assertion runs at all: a run that says
nothing failed may have run nothing. Read the collected count, not the
exit code.

**`spec_lint` does not check a spec's test surfaces here, and says so
only in one field.** It resolves a surface only in a
`tests/features/<name>/` shape, which this project does not use, so on a
spec here it reports `surfaces_resolved: 0` beside `surfaces_checked:
true` and `ok`. `doc_citations` counts a citation `ok` when the cited
line exists, and `unchecked` when nothing on that line was compared. So
each `*Test:*` clause is resolved by hand before its item ships: the
named test must exist and must assert what the clause says.

**Probe after the code lands, and probe one mutation per route the
invariant's own *Breaks when* names.** `mutation_probe` refuses without a
green baseline, so it cannot run while the tests are red. Where a stub is
the only thing that exists, the probe needs a throwaway reference
implementation outside the tree.

**A `killed` verdict can still be a false kill.** A mutation that leaves
the file unparseable now reads `broken`, not `killed` (ANTS-5360,
checked here 2026-09-29). But a mutation naming something undefined
fails every test on a `NameError` and reads `killed`, which says nothing
about the rule it meant to break. Mutate with values that run. **And a batch of kills does not mean the suite is
sound** — the survivors are where the evidence is.

**A test double written before the implementation encodes a guess about
the request shape, and the guess can make a faithful implementation
impossible to pass.** Give the double a by-URL answer for each read
rather than bending the code toward the fixture. Watch for it whenever a
double answers positionally: an implementation that legitimately adds one
request shifts every later answer onto the wrong step.

**A test that pins a name must hold its own copy of the name.**
`tests/test_settings.py` writes `"settings.json"` out rather than
importing `FILE_NAME` from the module under test. Share the literal and
INV-5 compares the module against itself, so `path_for` could name any
file and stay green. Do not tidy this into an import.

**Every `PublishError` subclass needs a Face sentence, a private one
included.** `tests/test_face.py::test_every_failure_type_has_a_sentence`
walks every subclass, so a private type used only for internal control
flow reddens the gate.

## Releasing

**A release is a draft until it is signed.** The release workflow builds
it; `scripts/sign-release.py v<X.Y.Z>`, run on the maintainer's machine,
signs and publishes it (PRESS-0023 § 4.8). It reads each key's path from
a machine-local key. The key lives outside the repository and never
enters a session:

```bash
git config --add ants.pressless.signingKey <path to the key>
```

**A session may run the script** (user decision 2026-09-29): it reads the
key file and never prints it. It also publishes, so it runs last, after
the by-hand checks; `.claude/bump.json` lists it as the final step.

**The gate refuses an empty `update_key.TRUSTED`**
(`tests/test_sign_release.py`), so a tag nobody could sign is caught
before it exists.

## Windows and browser checks

**Windows is testable, and that is not obvious from anything else here.**
Development happens on Linux and the app must run on both. A Windows 10
test box is reachable over SSH from the maintainer's machine under the
host alias `wintest`; the connection details live in that machine's SSH
config and deliberately not in this public repository. Chrome and Edge
are both installed.

**Python is NOT installed on that box, and must not be.** A machine with
an interpreter cannot show that the packaged executable carries
everything it needs, which is the whole of S4. Anything the app needs at
runtime it must bring with it.

**A program started over SSH cannot reach the Windows credential vault.**
The packaged self-check answers `store: unanswered -- CredentialError`
there and `store: keyring Windows WinVaultKeyring` in the desktop session
(PRESS-0120). Run anything touching the keyring in the logged-on session:
a one-off `schtasks /Create ... /IT` then `/Run`, writing its output to a
file, and delete the task afterwards.

**A packaged run holds its output back when a script reads it through a
pipe.** Check the packaged program from a console, or with
`--self-check`, which prints and exits.

**A browser check runs through Playwright and the system Chrome.** The
Claude-in-Chrome extension is not connected on this machine; the
`playwright` Python package is installed and drives
`/usr/bin/google-chrome` headless. It says nothing about Windows, which
stays the Windows box's by-hand row.

## Editing the roadmap

`roadmap_log op:"amend_field"` corrects a bullet's `Layman:` after
creation. It writes the store column, so it works wherever the render
composes that trailer — the bold-style bullets. Where the body declares
`Layman:` at a line start it refuses `field_shadowed_by_body` and names
`op:"amend_body"` as the route, because a declaration wins at render and
would be re-parsed back over the column.

**What stays one-way is the declaration itself**: deleting it does not
hand the column back, because the render gate refuses a bullet left
carrying no `Layman:` at all. **Leave the two styles as they are** —
reconciling them changes nothing anyone reads.

**A section intro is amendable.** `roadmap_log op:"set_intro"` replaces
one. A hand edit to `ROADMAP.md` is still discarded by the next render,
so the verb is the only route. **Still avoid a count, an id list or a
date in an intro** — the Milestones intro carries all three and every one
has gone stale (PRESS-0136). Amendable is not the same as maintained.

## Editing documents and building reviews

**Prose here hard-wraps at about 70 columns, and that breaks exact-match
editing.** A replacement string retyped from a sentence you just read will
not match, because the line breaks fall in places you did not notice — it
fails as a zero-count assertion, not as a wrong edit, so it is safe but it
costs a round trip every time. Build the `old` string from the file's
actual bytes (`sed -n 'A,Bp'`), never from memory of the sentence. The
same wrap is why a plain `grep` returns false negatives on a quoted
phrase: use `workspace_search` with `match_wrapped: true` before believing
a miss.

**Building a review packet trips the global config lock, and the message
names the wrong cause.** A gate assembles its brief from `~/.claude`
files; one shell command that both reads those paths and redirects to a
file is refused with *"the ~/.claude instruction surface is edited from a
session whose cwd is ~/.claude"* -- although nothing under `~/.claude` is
being written. The hook matches the command text, not its direction.
Split the read from the write, or reuse the brief half of the previous
packet. Do not reach for the bypass token or relaunch with the unlock
variable: neither is warranted, because no edit to that surface is
intended.
