## Files read
- `src/pressless/__init__.py`: 8 / 8
- `src/pressless/__main__.py`: 287 / 287
- `src/pressless/updater.py`: 441 / 441
- `src/pressless/updating.py`: 193 / 193
- `src/pressless/installer.py`: 217 / 217
- `src/pressless/update_key.py`: 13 / 13
- `src/pressless/shortcuts.py`: 301 / 301
- `src/pressless/sites.py`: 133 / 133
- `src/pressless/sites_screen.py`: 225 / 225
- `src/pressless/sitefile.py`: 228 / 228
- `src/pressless/backups.py`: 133 / 133
- `src/pressless/starter.py`: 241 / 241

Outside the lane, to confirm findings: `importing.py` lines 270–305, `builder.stylesheets`, `face.Download`, plus the searches named below.

## What I started with
- The user's global `~/.claude/CLAUDE.md`.
- The review-lane agent prompt.
- A SessionStart hook note about the Ants MCP tools.
- The user's email address, attached as context.

There was no project `CLAUDE.md`, no memory index and no git snapshot. On a disagreement between the brief and the lane file I had none to settle: the brief lets me open other files to confirm a finding, and that matches the lane file's carve-out.

## Summary
This code starts the Pressless program and keeps it from running twice. It checks for a newer release, proves the release is genuine with a signature, downloads it and swaps it in. It also keeps the Start Menu and desktop shortcuts pointing at the program. It holds several websites side by side and lets the user switch between them, save one as a single .zip file, or open such a file. It makes a backup of every site once a day, and it can fill an empty site with a ready-made starter site.

## Findings

[Q4] HIGH `starter.py:20` — `MARKER = "starter-unpublished"   # in Pressless's own folder; empty file` (also the module docstring, lines 6–7: "A marker in Pressless's own folder") — **false since several sites (PRESS-0223).** The marker now lives in each site's folder:
- `sites.SITE_NAMES` lists it as a site name, and `move_in` moves it into `site-1`.
- `setup.py:301` calls `fill` with the site folder.
- `sitefile.KEPT` carries it inside a saved site.

A stranger would look for the marker at the top of `Pressless-data`, or pass `own` to `unpublished`/`published`. Nothing nearby puts them right. — Fix: say "in the site's folder" in both places.
Cost: one edit (comment only). `docs/specs/PRESS-0126-starter-site.md` line 91 carries the same false comment. Searched: `starter\.(fill|MARKER|unpublished|published|offered)` across the tree; `starter-unpublished` in docs.

[Q3] MEDIUM `__main__.py:165` — `def _serve(folder: Path) -> int:` — `folder` means Pressless's own folder in `main`, `_hold`, `_serve` and `_serve_held`. Inside `_serve_once` (line 201), `folder = sites.open_site(own)` means the open site. The name flips meaning between neighbouring functions. A stranger adding a startup step to `_serve` (as `importing.finish_moves` was added) would assume `folder` is the site and pass the machine's folder. `updating.register`'s `folder` (`updating.py:70`) is also the own folder, while every other `register` takes the site; only its docstring says so. — Fix: name the own folder `own` throughout `__main__`.
Cost: one edit. Searched docs/tests for `_serve_once`: `PRESS-0223-several-sites.md:126` names `_serve_once(own)`, which this rename matches rather than changes.

[Q1] MEDIUM `sites_screen.py:208` vs `importing.py:280` — `_OPEN_SCRIPT` / `_SEND_SCRIPT` — two copies of "choose a file, POST it, replace the page", and they have diverged:
- The Sites copy changes the button text to `say("script.sites.opening")`; Import's does not.
- Import's is generic (`data-file`/`data-to`); the Sites copy hard-codes `"/sites/open-file"` instead of using `ADDRESS`.

A fix to error handling (see Correctness leads) would be made in one copy and missed in the other. Changing `ADDRESS` would silently break the Sites script. — Fix: one shared script that takes an optional "opening" label, wired by data attributes.
Cost: one edit. Searched outside `src` for `_OPEN_SCRIPT|_SEND_SCRIPT`: nothing. Confirms **dup:8668bbc915c5**.

[Q1] MEDIUM `starter.py:53` / `starter.py:96` — `_PAGE = """<!doctype html>` and `_PRIVACY = """<!doctype html>` (with `_NEW_PAGE` built from `_PRIVACY`). Two copies of one page skeleton that differ:
- `_PAGE` links one stylesheet, `{up}look/style.css`, and takes `{page}`.
- `_PRIVACY` takes a `{links}` list built from `builder.stylesheets`.

No comment says why Home and About link a fixed sheet while Privacy and new pages follow `builder.stylesheets`. A stranger adding something to every page's head would edit one copy and miss the other. — Fix: one skeleton with `{links}` and `{page}`; Home and About pass their sheet as the links.
Cost: pinned — `docs/specs/PRESS-0215-blocks.md:264` names `starter._PAGE`. Confirms **dup:37339784aab7**.

[Q1] MEDIUM `__main__.py:118` vs `installer.py:144` — `for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):` — the same restore-from-`_ORIG` loop, both labelled PRESS-0146. That ticket had to patch both, so the pair counts as three. They have also diverged: `__main__` skips unless frozen and not Windows, while `installer` always runs. A stranger adding a third loader variable would fix one copy. — Fix: one function both call; `installer` can own it, since it imports nothing.
Cost: unsure. `PRESS-0023-self-update.md:478` describes the helper environment's behaviour, but I did not read whether it names the function. `ROADMAP.md` names `_unbundle_environment`, but a roadmap is not a spec.

[Q4] MEDIUM `sites_screen.py:35` — `"""Add `GET /sites`, `POST /sites/open` and `POST /sites/new` to `face`.` — `register` also adds `GET /sites/save`, `POST /sites/backups` and the upload `/sites/open-file`. `keep_backups_in` is defined in the middle of the `add_page` calls, so the route list reads as finished at line 83. A stranger looking for where backups are posted would trust the docstring and look elsewhere. — Fix: list all six routes, and move `keep_backups_in` above the registrations.
Cost: one edit (comment, plus a move inside the function). No spec names the nested function; searched outside `src` for `_OPEN_SCRIPT|_SEND_SCRIPT…` only, so: unsure for the move, one edit for the comment.

[Q4] LOW `installer.py:3` — `Each function returns once the new version is in place and a helper has been started to open it` — this is false for `apply_windows`, which returns before the swap, since the helper swaps after exit. It is also false for `apply_linux` when it returns `False`. The function docstrings a few lines on correct it. — Fix: say Linux swaps then returns; Windows returns and the helper swaps.
Cost: one edit (comment only).

[Q5] LOW `updater.py:51` — `_SIG_SIZES = (64, 128, 192, 256)` — this silently caps a `.sig` file at four signatures, and nothing says so. The module `update_key.py` tells the maintainer to add new keys beside old ones. Signing with a fifth key would make every client stop at `Miss(5)`, which `updating` logs only as "step 5". — Fix: a comment naming the cap and its tie to `TRUSTED`.
Cost: one edit (comment only).

[Q5] LOW `updater.py:288` — `if tag.removeprefix("v") != version or version == skipped:` — the reason is not stated. This refuses a tag like `v1.02.3`, whose rebuilt version would not match the asset names. A stranger tidying it would think it redundant after `parse_version`. — Fix: one-line comment.
Cost: one edit (comment only).

[Q5] LOW `updating.py:124` — `elif found.step > 1:` — why step 1 is never logged is unstated. Step 1 is "the switch is off", but see Correctness leads. — Fix: one-line comment.
Cost: one edit (comment only).

[Q4] LOW `updater.py:117` — `not publisher._NoCrossOriginAuth: the two are not shared (rule 7).` — it does not say which document's rule 7. Elsewhere the tree writes "design rule 7" (`store.py:630`, the PRESS-0023 spec). — Fix: "docs/design.md rule 7".
Cost: one edit. Searched: `rule 7` across the tree.

[Q4] LOW `__main__.py:280` — `"""Block until the console window is closed or interrupted, or until restart is set. True on a restart."""` — this implies a `False` return. The function only ever returns `True`: closing the console kills the process, and an interrupt raises. A stranger might add handling for a `False` that never comes. — Fix: say it returns only on a restart.
Cost: one edit (comment only).

[tool?: unused constant] `updater.py:54` — `PLATFORMS = ("linux", "windows")` — defined and never read. Searched: `PLATFORMS` across the whole tree; one row, not truncated.

## Candidates dismissed
- **size `__main__.py:192:_serve_once`** — most of it is a flat list of `register` calls. The one subtle part, the `editor.LOCK` in `finally`, carries its reason. Where a stranger goes wrong here is the naming, filed under Q3, not the length.
- **size `sites_screen.py:34:register`** — five short nested handlers. The real problem is the stale docstring and the out-of-place `keep_backups_in`, filed under Q4.
- **size `updater.py:264:check`** — a linear series of numbered steps that mirrors the spec. Easy to follow.
- **size `updating.py:70:register`** — four small closures and a thread start. Easy to follow.
- **comment `installer.py:34`, "2 the process"** — `$2` is the script's second positional argument, and the comment is accurate. "0.1 s for at most 60 s" matches `600` tries.
- (Not a candidate, but checked) `updater._allowed` vs `sitefile.stays_inside`: these differ on backslashes. The updater's docstring states why ("a separator on the system that unpacks it"), and its module may not import `sitefile`'s dependencies (§ 4.1). Not a finding.

## Correctness leads
- `updating.py:124` — a failure at step 1 is never logged, so it looks the same as the switch being off. That includes `_Urllib()` failing (an ssl or certifi error) inside `check`'s try. Searched: none (both sites read in-lane).
- `sites_screen.py:218` and `importing.py:291` — if `fetch` rejects (the connection drops), the promise is unhandled. The button stays disabled, and on Sites it keeps saying "opening", with no message. Searched: read both copies.
- `sitefile.py:211` — when `target == current` (an unused open site), `shutil.rmtree(target)` runs before `opening.rename(target)`. If the rename fails, the current site folder is gone, which contradicts the docstring's "leaves sites/ as it was". `open_site` would remake it as an empty folder. Searched: none.
- `sites.py:122`, `backups.py:110` — sentences shown to the user are hard-coded English rather than going through `say()`, unlike the rest of these files. I did not check whether `words` is meant to cover them. Searched: none.

## Not checked
- I did not read `PRESS-0023-self-update.md` around line 478, so I could not grade the cost of the loader-variable merge.
- I did not judge the PowerShell or shell script logic for correctness beyond reading its comments.
- I did not check `importing.py` beyond the duplicate window.
- I did not check whether `look.save`'s style code path equals `look/style.css`, which bears on whether `_PAGE`'s fixed sheet and `builder.stylesheets` really disagree in practice.
