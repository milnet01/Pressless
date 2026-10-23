## Files read
- scripts/build-linux.sh — 51 / 51
- scripts/build-windows.sh — 41 / 41
- scripts/local-ci.sh — 237 / 237
- scripts/windows-gate.sh — 134 / 134
- scripts/by-hand-browser-checks.py — 1519 / 1519 (two pages: 1–1043, 1044–1519)
- scripts/by-hand-editor-races.py — 124 / 124
- scripts/freeze_flags.py — 67 / 67
- scripts/make-signing-key.py — 78 / 78
- scripts/make_flags.py — 62 / 62
- scripts/practice.py — 187 / 187
- scripts/sign-release.py — 223 / 223
- scripts/write_google_secret.py — 63 / 63
- scripts/write_usage_key.py — 62 / 62
- run.sh — 9 / 9
- .githooks/commit-msg — 90 / 90
- .githooks/pre-commit — 122 / 122
- .githooks/pre-push — 34 / 34
- packaging/linux/AppRun — 9 / 9

## What I started with
- The global `~/.claude/CLAUDE.md`, injected by the system.
- A SessionStart hook note about the Ants MCP verbs.
- The environment block: working directory `/home/ants/.cache/lane-neutral`, not a git repo, so no git snapshot.
- The review-lane agent prompt, and the brief with its shared context.
- No project CLAUDE.md and no memory index.

## Summary
These are the helper programs around Pressless, not Pressless itself:
- **Builds.** Scripts that turn the source into a Linux AppImage and a Windows zip.
- **Release.** A script that signs a finished release and publishes it, plus one that makes the signing key.
- **Secrets.** Two scripts that write private keys into the program at build time.
- **The checking gate.** A script run before every push and by GitHub. It looks for the writer's name leaking into the public repository, then runs the tests, optionally on a Windows machine too.
- **Browser checks.** A long script that drives a real browser through the editor's screens, run by hand before a release.
- **The rest.** A "practice copy" launcher, git hooks that check commit messages and documents, and the AppImage's start-up stub.

## Findings

[Q4] HIGH `scripts/windows-gate.sh:124` — `# Exit 2 means the box could not be reached, which local-ci.sh reports and passes; any other non-zero is the suite's failure.`
- **The problem.** In suite mode the remote script exits with pytest's own exit code (`\$code = \$LASTEXITCODE`, line 66), and pytest itself returns 2 when it is interrupted. That includes errors while collecting the tests.
- **What follows.** So exit 2 can mean "the suite broke on Windows", and `local-ci.sh:226` then prints "not reachable" and lets the push through.
- **Where a stranger goes wrong.** Someone trusting this comment, or its twin at `local-ci.sh:218` ("an UNREACHABLE box (exit 2)"), would look for a network fault when the Windows suite is actually broken. Nothing nearby corrects them.
- **Fix:** turn the remote's exit 2 into some other non-zero code before `exit "$status"`, so that 2 is only ever `unreachable()`'s; correct both comments to match.
- **Cost:** one edit. Searched: "windows-gate" across the tree. Only `docs/working-here.md` and ROADMAP mention the script, and neither names the exit code.

[Q1] HIGH `scripts/by-hand-browser-checks.py:816` — `page.wait_for_function("document.getElementById('save-status').textContent !== "`
- **The copies.** "Wait for the save to finish" is written out ten times, at:
  - 567–569 `kept_files`
  - 719–721 `added_by_upload`
  - 749–751 `enlarge_photograph`
  - 814–817 `visual_editor.saved`
  - 1087–1090 `move_between_columns.move`
  - 1137–1140 `drag_sections.drag`
  - 1216–1219 and 1231–1235 `pieces`
  - 1309–1312 `furniture_views.saved`
  - 1363–1366 `switch_in_place.saved`
- **They have diverged.** Four add a further `wait_for_timeout(800)` and the rest do not. `visual_editor` adds one ad hoc at 957. No comment says why the 800 ms is there.
- **Silent failure.** Every copy hard-codes the status text `'Saving'`, whose real home is `src/pressless/words.py:503` (`"script.editor.saving": "Saving"`). If that wording changes, every wait stops waiting without any error, and the checks turn flaky.
- **Where a stranger goes wrong.** A stranger adjusting the wait in one row will miss the other nine, and cannot tell which variant is correct.
- **Fix:** one module-level save-wait helper with the 800 ms as a named, commented option.
- **Cost:** one edit. Searched: "by-hand-browser-checks" in docs/specs. Only the row `switch_in_place` is named (PRESS-0285), and this fix does not rename it. No ANCHORS.

[Q1] MEDIUM `scripts/build-linux.sh:21` — `PY=`
- **The copies.** The same python-finding loop appears three times: `build-linux.sh:21-28`, `build-windows.sh:8-15` and `local-ci.sh:108-115`.
- **The reason lives in only one.** Only `local-ci.sh` explains it, at 102–107: Windows has no `python3`, and a store alias that runs nothing.
- **Where a stranger goes wrong.** `build-windows.sh` needs that reason most and carries none. A stranger "simplifying" one build script to `python3`, or adding `py` to one copy, misses the other two.
- **Fix:** move the loop and its comment into one sourced script that all three use.
- **Cost:** one edit. Searched: "candidate in python3 python" across the tree; only the three sites.
- Confirms **dup:a3d8b61ede97**.

[Q1] MEDIUM `scripts/write_google_secret.py:48` — `value = os.environ.get("GOOGLE_CLIENT_SECRET")`
- **Two diverged copies.** `write_usage_key.py:33-38` (`_value`) reads a secret the same way but `.strip()`s it. Its comment says why: a value pasted into GitHub's secret box keeps a trailing line break. `write_google_secret.py` does not strip.
- **The effect.** The same paste is accepted by one script and refused by the other.
- **Where a stranger goes wrong.** A stranger fixing a "refused secret" report in the release job will not know the fix already exists in the sibling script.
- **Fix:** move `_value` beside `_asks` in `write_google_secret.py` and use it in both.
- **Cost:** unsure. Searched: "write_google_secret" and "write_usage_key". `tests/test_write_usage_key.py:17` imports `_steps` from the google test, and PRESS-0262 spec line 114 says the usage script works "as `scripts/write_google_secret.py` does". That spec line describes behaviour rather than a function name, so it may not pin the fix. I did not read the spec's surrounding text.

[Q5] MEDIUM `scripts/by-hand-browser-checks.py:516` — `code_colours(page, origin)`
- **Hidden ordering.** The helper calls at 515–530 must run in this order, and nothing says so:
  - `code_colours` (1000) and `true_colours_kept` (1040) open the page `visual` but never write it. They depend on `visual_editor` having written it, and on the code box holding `"<div>new code</div>"` from line 930.
  - `site_file` depends on `sites_listed` having switched the open site.
- **Partial cover only.** The one ordering comment (1455) covers only the rows after `switch_in_place`.
- **Where a stranger goes wrong.** Someone commenting out `visual_editor` to debug, or reordering rows, gets failures that point at the wrong row.
- **Fix:** a one-line comment above 515 saying the order is load-bearing, naming which rows use which earlier rows' pages.
- **Cost:** one edit (comment only).

[Q2] MEDIUM `scripts/by-hand-browser-checks.py:427` — `# PRESS-0235 decision 6: the refusal stays shown, in its box with`
- **Where the thread is lost.** `run` holds about 330 lines of inline rows (185–513) that all change one entry, `seaside`, in turn: draft, pressed (329), proofed (360), binned (371), undo pressed (412), saved again (434).
- **The puzzle.** By 427 the reader is told "the refusal stays shown", but the checks just above (415–425) assert the undo's "putting back" message and a reply. Nothing says the transport double refuses the undo, or what state `seaside` is in afterwards.
- **Where a stranger goes wrong.** Inserting a row between 350 and 435 means guessing that state.
- **By contrast.** Rows after 515 are each their own function with their own page.
- **Fix:** split the inline rows into named row functions as the later ones are, each stating the state it expects.
- **Cost:** one edit. Searched: "by-hand-browser-checks" in docs/specs. Only `switch_in_place` is named, which this fix leaves alone. No ANCHORS.

[Q5] LOW `scripts/by-hand-browser-checks.py:1170` — `"</body></html>\n").replace("2026-12-25T18:00", "2099-12-25T18:00").replace(`
- **The problem.** The countdown fixture's date is rewritten to 2099 with no comment saying why. The reason is presumably that the fixture date (in `tests/features/blocks/forms/countdown-1.html`) will soon be in the past, and the 1290 check wants time left.
- **Where a stranger goes wrong.** If they change the fixture's date, `.replace` silently matches nothing.
- **Fix:** a comment naming the reason, or an assertion that the replace matched.
- **Cost:** one edit.

[Q3] LOW `scripts/by-hand-browser-checks.py:1409` — `added = frame.locator("p", has_text="Added in code too")`
- **The reuse.** `added` holds an HTML string at 1398, then becomes a locator at 1409. Likewise `shown` in `visual_editor` holds a list (912), then code text (927), then a pixel width (958).
- **Where a stranger goes wrong.** Moving a line across the rebinding uses the wrong kind of value.
- **Fix:** distinct names per meaning.
- **Cost:** one edit (local names only).

[Q4] LOW `scripts/by-hand-browser-checks.py:3` — `Rows satisfied here (all say "nothing in CI -- by hand, in a browser"):`
- **The mismatch.** This hand-kept list names 14 rows. The file also checks PRESS-0016, 0128, 0182, 0185, 0186, 0015, 0221, 0223, 0224, 0227, 0279, 0280, 0282, 0287, 0288 and 0289.
- **The specs disagree with it too.** Several of them name this script as their by-hand check: PRESS-0182, PRESS-0223, PRESS-0224, PRESS-0227 and PRESS-0197 INV-10.
- **Where a stranger goes wrong.** Someone asking "is PRESS-0224's row driven here?" would read the list and conclude no.
- **Fix:** bring the list up to date, or replace it with a pointer to the `check(...)` labels.
- **Cost:** one edit (docstring only).

[Q5] LOW `scripts/by-hand-browser-checks.py:1141` — `return shown and outer is not None`
- **The problem.** `outer`, the preview's bounding box, is fetched only to decide whether the drag succeeded, and nothing says why.
- **Where a stranger goes wrong.** They cannot tell whether it is a guard or a leftover, and would hesitate to remove it.
- **Fix:** drop it, or say what it guards.
- **Cost:** one edit.

[Q4] LOW `scripts/windows-gate.sh:122` — `cp "$scratch/tree.zip" "$scratch/$run.zip"`
- **The problem.** The zip is built as `tree.zip` (line 97) and then copied to `$run.zip`; `tree.zip` is never used again.
- **Where a stranger goes wrong.** They would hunt for a second reader of `tree.zip`.
- **Fix:** write `$run.zip` directly at line 97.
- **Cost:** one edit. Searched: "tree.zip". It appears only in this file.

[Q1] LOW `scripts/local-ci.sh:157` — `if [[ -z ${PRESSLESS_ARCHIVE-} ]]; then`
- **The copies.** "Take an env var from a git config key unless it is already set" is written four times in three shapes: 157–164 (file), 168–175 (folder), 181–191 (folder loop), 198–206 (value loop).
- **Partly justified.** The file/folder/value checks differ for stated reasons. But the `originals` block is the same as the folder loop and sits outside it.
- **Where a stranger goes wrong.** Someone adding a key, or changing the "already-set wins" rule, has four places to edit.
- **Fix:** fold `originals` into the folder loop.
- **Cost:** one edit.

[Q5] LOW `.githooks/commit-msg:28` — `echo "  rule:    ~/.claude/standards/commits.md §$2" >&2`
- **The problem.** This error message, and `.githooks/pre-commit:106`, point at a file outside the repository, which does not exist on a colleague's clone.
- **Where a stranger goes wrong.** Nothing in either hook says that the rules live only on the maintainer's machine (`pre-push` does say this for itself).
- **Fix:** say in each hook's header that the cited standard is machine-local.
- **Cost:** one edit (comment only).
- Searched: "commits.md" outside ROADMAP and CHANGELOG. There is no copy in the repository; it is only mentioned in CLAUDE.md, a docs record and local-ci.sh.

[Q5] LOW `scripts/make-signing-key.py:47` — `print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)`
- **The problem.** The usage message is "line 2 of the module docstring". `make_flags.py:29` does the same.
- **Where a stranger goes wrong.** Adding a second summary line to either docstring silently prints the wrong usage.
- **Fix:** a literal usage string, as `sign-release.py:211` uses.
- **Cost:** one edit.

[tool?: unused assignment] `scripts/by-hand-browser-checks.py:1486` — `violations: list[str] = []` is overwritten at 1496 before any read.

[tool?: redundant import] `scripts/by-hand-browser-checks.py:1467` — `from pressless import editor as ed` re-imports a module already imported at the top as `editor`.

## Candidates dismissed
- **dup:a3d8b61ede97** — confirmed, above.
- **size `run`** — confirmed in a different form. Its length is not the problem: the inline rows' shared, unstated state is (Q2 above), and so is the call order (Q5 above).
- **size `visual_editor`** — dismissed. It is one page, one row per step, each step checked in order, and readable top to bottom. Only the `shown` rebinding is reported (Q3 above).
- **size `switch_in_place`** — dismissed. It is linear, its inner helpers are named and short, and its timing comment (1410) explains the one wait. Only the `added` rebinding is reported.
- **size `pieces`** — dismissed. It is linear, under banner comments ("the editor…", "the published site…"), and the built-site half is already split out into `_published_pieces`.
- **comment `by-hand-browser-checks.py:286` "~1"** — dismissed. The editor's save delay is `setTimeout(save, 1000)` (`src/pressless/page_editor.py:1280`, and `editor.py:950`), so "~1s" is true. 150 ms is inside it.
- **comment `windows-gate.sh:124` "2 means"** — confirmed as false, the HIGH finding above. It was dismissed only as a census number.

## Correctness leads
- `scripts/windows-gate.sh:66` with `local-ci.sh:226` — when pytest on Windows exits 2 (interrupted, for example by collection errors), the gate prints "not reachable" and passes the push. Searched: none beyond these two files. "pytest exits 2 on collection errors" is pytest's documented behaviour, not checked in this tree.
- `scripts/write_google_secret.py:51` — a `GOOGLE_CLIENT_SECRET` pasted into GitHub with a trailing newline is refused here, while `write_usage_key.py` accepts the same paste. This may fail a release job. Searched: "write_google_secret". I did not read `.github/workflows` to see whether the job pre-strips it.
- `scripts/windows-gate.sh:91` — `git ls-files -co` lists a tracked file that has been deleted from disk but not staged, so `zipfile.write` raises and the gate reports "tests on Windows" failed. Searched: none. The global pre-push may check pushed commits out into a clean worktree, which would hide this; that hook was not read.
- `scripts/local-ci.sh:27` — an unknown first argument (for example `--doc`) silently runs the full gate rather than refusing. Searched: none.

## Not checked
- `tests/features/blocks/forms/countdown-1.html`: I did not read it, so I did not confirm that both date spellings replaced at line 1170 occur in it. The search shows one matching line.
- The global `~/.claude/githooks/pre-push` that `.githooks/pre-push` hands off to: not read, because it is outside the lane.
- `.github/workflows/*`: not read, so I did not check how the release job calls `build-*.sh` and `write_*` (environment variables, stripping).
- The PRESS-0262 spec's text around line 114, which would settle the cost grade of the secret-reading finding.
- Whether the PowerShell and JavaScript embedded in the strings run correctly. I judged them for readability only.
