## Files read
- `src/pressless_import/__init__.py`: 772 / 772
- `src/pressless_import/__main__.py`: 7 / 7
- `src/pressless_import/_bring.py`: 597 / 597
- `src/pressless_import/_html.py`: 652 / 652
- `src/pressless_import/fetch.py`: 168 / 168
- `src/pressless/importing.py`: 345 / 345

## What I started with
- The global `~/.claude/CLAUDE.md`.
- An email-address context note from the harness.
- A SessionStart hook message saying the Ants MCP verbs are connected.
- No project `CLAUDE.md`, no memory index and no git snapshot.
- Then `shared-context.md`, which is the brief.

## Summary
This code moves a WordPress website into Pressless's own files.

It reads the export file WordPress makes. It turns each post's web markup into Pressless's simpler text marks. It fetches the pictures and files the export names from the old website, with checks so a hostile export cannot make it reach inside the user's own network.

It writes everything into a working folder first, then moves it into place, so a site arrives whole or not at all. It ends with a report of what could not come across exactly as written. There are two ways in: a one-off command for the maintainer (`run`) and a step-by-step screen anyone can use (`bring_in`, driven by `importing.py`).

## Findings

[Q4] HIGH `src/pressless_import/_bring.py:55` — `_MISSING = "its original is missing"`
- **What goes wrong:** `bring_in` (line 475) uses this constant to recognise one specific reason from `_photographs` and swap in the fetch's own reason. It does that by comparing against the literal text that `__init__.py:424` writes, `unheld.append((upload_path, "its original is missing"))`.
- Nothing at line 424 says that another module matches this wording.
- So a stranger rewording the report message (PRESS-0294 already reworded report lines) breaks the swap silently. The report would then say "its original is missing" for a file whose real problem was a failed fetch.
- **Fix:** define the reason once in `__init__`, use it at line 424, and import it in `_bring`.
- **Cost:** one edit. Searched: `its original is missing|_MISSING\b` across the tree, which found only these three sites; searched `docs` for `_MISSING`, nothing found.

[Q1] MEDIUM `src/pressless_import/_bring.py:139` — `return urlparse(address).netloc.lower().removeprefix("www.")`
- **What goes wrong:** the rule "how two hosts are compared" is written four times: `_bring.py:139` (`_host`), `_bring.py:148` (`old = old_site.lower().removeprefix("www.")`), `_html.py:547` (`_host`, an identical copy) and `_html.py:299` (`self._old_site = ...`).
- `_bring` already imports from `_html` but defines its own `_host`.
- A stranger changing how hosts match (for example, ignoring the port, or treating `http` and `https` alike) fixes the converter's copy. Page addresses in `_bring` then disagree about what counts as "the old site".
- **Fix:** one host-normalising helper in `_html`, used by all four sites.
- **Cost:** one edit. Searched: `removeprefix("www.")` across the tree (the only other hit is in `google_signin.py`, unrelated); searched `docs` for `_host`, nothing found.

[Q1] MEDIUM `src/pressless/importing.py:280` — `_SEND_SCRIPT = r"""`
- **What goes wrong:** `_file_box`'s docstring says it works "as the Sites screen's file box does". The two scripts (`importing.py:280-299`, `sites_screen.py:212-225`) are copies that have diverged.
- Import's copy wires every `button[data-file]` and marks each as `wired`. The Sites copy uses fixed element ids and changes the button's label to "opening".
- A fix to the shared behaviour, such as handling a failed `fetch` (see Correctness leads), would be made in one copy and missed in the other.
- **Fix:** keep one generic script and use it from both screens.
- **Cost:** one edit. Searched: `docs` for `_SEND_SCRIPT|_OPEN_SCRIPT`, nothing found.
- Confirms dup:8668bbc915c5.

[Q4] MEDIUM `src/pressless_import/_bring.py:53` — `_MEDIA = "media"`
- **What goes wrong:** `finish` deletes `import/media/` using this constant. Meanwhile `importing.py:40` keeps its own `_MEDIA = "media"`, builds `held / _MEDIA` itself, and passes that path to `bring_in` and `fetch_all`.
- Neither copy says the other must match it. `IMPORT_FOLDER` shows the intended pattern: exported once, used by both.
- A stranger renaming the folder in `importing.py` gets imports that still work, but `finish` would never delete the downloaded files.
- **Fix:** export the media folder name, or a path helper, from `pressless_import`, as `IMPORT_FOLDER` already is.
- **Cost:** one edit. Searched: `"media"|_MEDIA =` across the tree, which found the two definitions plus tests that write the folder name as a literal; searched `docs` for `_MEDIA`, nothing found.

[Q3] MEDIUM `src/pressless_import/__init__.py:380` — `def _photographs(channel, ns, originals: Path, *, strict: bool = True,`
- **What goes wrong:** under `bring_in`, this function names every attachment, including PDFs and other non-pictures that `_held` later sends to `files/`.
- In the same way, `Report.renamed_photographs` (line 79) is filled at `_bring.py:467` with renamed files too. `importing.py:325` shows it with the key `import.report.renamed_file`.
- A stranger trusting the names would assume non-picture attachments never pass through here, or that this field lists only pictures. They would then add a picture-only rule in the wrong place, or count photographs from the wrong field.
- **Fix:** rename to say "attachments", or add a field comment saying it covers files too.
- **Cost:** pinned. `docs/specs/PRESS-0125-wordpress-import.md` names `_photographs` (lines 40 and 156); `docs/specs/PRESS-0007-import.md` names `renamed_photographs` (line 130). A comment-only fix needs neither change.

[Q4] LOW `src/pressless_import/__init__.py:84` — `unfetched: tuple[tuple[str, str], ...] = ()   # (upload path, why it is not held)`
- **What goes wrong:** when `strict` is off, an attachment with no usable place goes into this list keyed by its `attachment_url`, a full web address, not an upload path (line 398).
- Likewise `fetch_all` keys refusals by `address` (`fetch.py:154`), though its docstring says "each place not held".
- A stranger treating every key as a path under `media/` (to open it, or to match it against `unpack_media`'s places) would get no match, with nothing to say why.
- **Fix:** state in both comments that a refused attachment is keyed by its address.
- **Cost:** one edit (comment only).

[Q2] LOW `src/pressless_import/_bring.py:473` — `unfetched=tuple(dict(`
- **What goes wrong:** lines 473-475 do four things in one expression: they dedupe by place, substitute the fetch's reason only for `_MISSING`, supply a default sentence, and turn the result into a tuple.
- This is where a reader of `bring_in` loses the thread. It is also the site that hides the HIGH finding above.
- **Fix:** move it into a named helper beside `_dropped`.
- **Cost:** one edit. Searched: `docs` for `_MISSING` and `unfetched`; the spec names the `unfetched` field, not this expression.

[Q4] LOW `src/pressless_import/__init__.py:505` — `# ------------------------------------------------------------- the run ----`
- **What goes wrong:** the banner is followed directly by another banner (`fixed pages and furniture`). `run` itself is about 130 lines further down.
- A stranger scrolling to "the run" lands on `_read_text`.
- **Fix:** move the banner to just above `run`.
- **Cost:** one edit (comment only).

[Q4] LOW `src/pressless/importing.py:278` — `_RELOAD = 'setTimeout(() => location.replace("/import"), 2000);'`
- **What goes wrong:** this repeats `setup.IMPORT` ("/import") by hand, while everything else in the module uses `ADDRESS`.
- If the address changes, the fetching page would reload to the old address.
- **Fix:** build the script from `ADDRESS`.
- **Cost:** one edit. Searched: `"/import"` across the tree; found here and in `setup.py:115` only.

[Q5] LOW `src/pressless_import/_bring.py:385` — `layout = layout if layout in starter.LOOKS else starter.LOOKS[0]`
- **What goes wrong:** an unknown look is silently replaced by the first one, and no comment says why.
- The wizard's `check_look` refuses an unknown look first. A stranger cannot tell whether this line is a deliberate fallback for other callers or dead code, so they might remove it, or rely on it to check input.
- **Fix:** add a one-line comment naming who may pass an unknown look.
- **Cost:** one edit (comment only).

[Q4] LOW `src/pressless_import/_html.py:197` — `# What a reader never sees, so neither function hands it on.`
- **What goes wrong:** "neither function" names neither. The two are `visible_lines` and `_Converter.walk`, which sit far apart.
- A stranger adding a hidden tag cannot tell from this comment which two places depend on `_HIDDEN`.
- **Fix:** name the two functions.
- **Cost:** one edit (comment only).

## Candidates dismissed
- **size `src/pressless/importing.py:70:register`:** it is long, but it is a list of short, named closures, followed by a `steps` table that reads in wizard order. I found no point where a reader loses the thread. The signal "`unfetched.json` exists means the fetch has ended" is explained by the comment at line 41.
- **size `src/pressless_import/_bring.py:373:bring_in`:** the phases run in the order its docstring lists, and the rollback is short. The one dense spot, lines 473-475, is filed above as a LOW of its own, not as a size problem.
- **size `src/pressless_import/__init__.py:640:run`:** a straight sequence that matches its docstring's order. I found no point where a reader loses the thread.
- **size `src/pressless_import/__init__.py:380:_photographs`:** the docstring spells out the four-part return and the `strict`/`shown` behaviour. The difference between `names` and `pictures` can be read from the code at line 428. Its naming problem is filed separately under Q3.

## Correctness leads
- `src/pressless/importing.py:291` — `await fetch(...)` has no catch, so on a network error the button stays disabled and the page never changes. The Sites copy (`sites_screen.py:218`) has the same gap. Searched: read both copies.
- `src/pressless/importing.py:99-100` — `progress` writes `state.done` and `state.total` from the fetch thread without `state.lock`, while `show_media` reads them. Probably harmless for display. Searched: none.
- `src/pressless_import/fetch.py:154` and `_bring.py:474` — `unfetched.get(place, ...)` looks up by upload place, but a refused attachment is keyed by its full address in both `fetch_all` and `_photographs`. The lookup still works because the address-keyed entry already carries its own reason, but only by coincidence. Searched: read both functions.
- `src/pressless_import/fetch.py:48` — `_Checked.connect` uses `self._context`, a private field of `http.client.HTTPSConnection`, which could change between Python versions. Searched: none.

## Not checked
- I did not open `pressless.store`, `builder`, `blocks`, `menu`, `starter`, `wizard` or `face`, beyond `face._room` and `sites_screen.py` lines 195-225. So claims about what those calls do rest on names and docstrings.
- I did not read the specs' text, beyond the search hits used to grade costs.
- Two pairs of identical copies were not filed, because the brief excludes identical pairs with no recorded double fix: `_GALLERY` (`__init__.py:97`, `_html.py:33`), and the `menu_order` parsing and the `meta` dict in `_bring.py`/`__init__.py`.
