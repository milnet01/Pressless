## Files read
- src/pressless/setup.py — 1–1075 / 1075
- src/pressless/settings.py — 1–460 / 460
- src/pressless/credentials.py — 1–467 / 467
- src/pressless/github_setup.py — 1–188 / 188
- src/pressless/github_signin.py — 1–264 / 264
- src/pressless/google_setup.py — 1–393 / 393
- src/pressless/google_signin.py — 1–318 / 318
- src/pressless/insights.py — 1–787 / 787
- src/pressless/dashboard.py — 1–384 / 384
- src/pressless/usage.py — 1–300 / 300

(Each total is the last numbered line `Read` returned.) Outside the lane I read only what a finding or a cost grade needed: publisher.py 185–290 and 826–842, store.py 90–106 and 1570–1610, PRESS-0001 §4.4 and INV-1, PRESS-0021 §4.9, and some search hits in tests/test_settings.py.

## What I started with
- The global `~/.claude/CLAUDE.md`.
- A context block with the user's email.
- The review-lane agent definition.
- A SessionStart hook message about the Ants MCP verbs.
- No project `CLAUDE.md`, no memory index, no git snapshot.

## Summary
These files run Pressless's setup. A first-run wizard walks the writer through linking a GitHub account and repository. After that, the same `/setup` page becomes Settings. The files also decide where the GitHub and Google secrets are stored (the system keyring, or a private file). They handle signing in to GitHub and to Google. The Visitors dashboard asks Google Analytics how many people read the site, from where, and which pages, and keeps a one-hour copy of the answer. The usage reports are opt-in, and every report sent is kept on the computer so the writer can read it.

## Findings

[Q4] MEDIUM `setup.py:10` — `never reads the Store (§ 3 decision 9) and never runs Import.` — This is false. Setup reads the Store at 325 (`store.holds_a_site`), 386, 409 and 827 (`store.read_identity`), and through `starter.offered`. A stranger who trusts the header would think adding a Store read breaks a rule, or would miss these reads when changing the Store. PRESS-0021 §4.9 itself notes that PRESS-0126 changed this rule. Fix: say what Setup reads from the Store (the identity and the starter offer) and why.
Cost: one edit (comment only).
Searched: PRESS-0021-setup.md lines 294–308.

[Q1] MEDIUM `settings.py:161-173` and `:329-341` — `except UnicodeDecodeError as exc:` — `load` and `save` each repeat the same file checks: decode, read error, JSON, object, version (186–195 and 352–367). The comments record fixes that had to patch both copies: PRESS-0049, and PRESS-0066 "closed on the read side only" leading to PRESS-0053. The next rule added to the file check goes in one copy and gets missed in the other. The copies already differ in their error wording. Fix: one private reader of the raw mapping that `load` and `save` both call, each keeping its own message.
Cost: unsure. No spec names the new helper, but tests/test_settings.py:97 and :111 walk settings.py's code structure, and I did not read what they pin.
Candidate: dup:090491ef9f2f.

[Q4] MEDIUM `settings.py:122-124` (and `credentials.py:65-67`) — `a shared helper would be a new part the design does not have.` — The comment's reason for copying `_why` conflicts with the spec. PRESS-0001 §4.4 says "**`safe_write` is not a part** … A module that knows no part leaves that true", and both files already import `safe_write`. A stranger would keep the copies for a reason the spec does not support. `_why` is defined in credentials.py:57, settings.py:114, publisher.py:832, builder.py:334 (not read) and store.py:624 (a variant taking `Exception`). Fix: correct the comment to the real reason, or move `_why` into a module that knows no part.
Cost: the comment is one edit. The move is unsure: PRESS-0001 INV-1 says the `SettingsError` wording "stays in settings.py", and I could not tell whether `_why` counts as part of that wording.
Candidate: dup:850a6de8538e.
Searched: `def _why\(` in src; `safe_write` in docs.

[Q1] MEDIUM `insights.py:195-306` — `class _NoCrossOriginAuth` / `class _Urllib` / `_no_answer` — The whole HTTP client is copied in publisher.py:201–284. Both copies cite PRESS-0135 in the same comments, which means a past fix had to patch both. A third copy, `usage._Opener` (197–217), differs: no cross-origin redirect handler, built on first request, and no error-status handling. updater.py:125 has a fourth `class _Urllib`, which I did not read. A stranger fixing redirect or certificate handling fixes one or two of these and misses the rest. insights says "for the reason publisher.py gives", which points at one twin only. Fix: one shared client module the others import.
Cost: pinned. PRESS-0262 (around line 180) names `insights._Urllib`, PRESS-0023 lines 154 and 214 name `_Urllib`, and tests/test_network_timeouts.py and tests/test_network_confined.py walk every module's network imports.
Candidates: dup:cfea936c5d6b, dup:2219d0a65502, dup:5670ccf581b4.
Searched: `class _Urllib|class _Opener` in src; `_Urllib` in docs/specs.

[Q2] MEDIUM `setup.py:699` — `def _first_run_wizard(` — This is 269 lines of twelve inner functions sharing `folder`, `transport`, `sign_in`, `signing_in` and `noun`. The reader loses the thread at `check_key` (758). Only lines 945–967 show which checks belong to the sign-in flow (`check_signin`, `check_install`, `check_new_repository`) and which to the hand-made-key flow (`check_account`, `check_repository`, `check_key`). The rest are shared. Someone editing `check_key` cannot tell that sign-in users never reach it, or why it uses the default `noun` while `check_signin` passes `noun`. Fix: build each flow's steps in its own function, or label each inner function with its flow.
Cost: a split that keeps the name is one edit. Renaming it is pinned: PRESS-0125-wordpress-import.md:94 names `setup._first_run_wizard`.
Candidate: size setup.py:699.
Searched: `_first_run_wizard` in docs.

[Q5] MEDIUM `github_setup.py:71` — `with state.lock if state is not None else threading.Lock():` — Nothing says why `token` works before `register` for a hand-made key and only fails (`RuntimeError` at 76) for a sign-in. A stranger tidying this to `state = _need()` would break every caller that reaches `token` before `register` with a hand-made key. The callers are page_editor.py:882 and :1150, publishing.py:344, undo.py:526, and setup.py:240 and :730. Fix: one comment saying a hand-made key needs no registered state, and naming who relies on that.
Cost: one edit (comment).
Searched: `github_setup\.token\(` in src.

[Q1] LOW `github_setup.py:160-164`, `google_setup.py:110-114`, `dashboard.py:125-129` — `except (settings.NotSetUp, settings.SettingsError):` — Three identical "load Settings, catch notices, None on failure" blocks. A change to how a refused settings file is shown on these pages would need three edits. Fix: one shared helper.
Cost: unsure. There is no obvious home: rule 10 limits which modules may import which, and I did not read it.
Candidate: dup:81126c5d0be2.

[Q1] LOW `setup.py:112` — `_CREDENTIAL_FAILURES = (credentials.NoStore, credentials.NotStored, credentials.CredentialError)` — The same tuple is in github_setup.py:31 and google_setup.py:35. dashboard.py:185 reaches into `google_setup._CREDENTIAL_FAILURES`, a name that looks private. A fourth credential failure type added later would be missed in some copies. `_REFRESH_MARGIN` is also copied (github_setup.py:30, google_setup.py:33). Fix: one public tuple in `credentials`.
Cost: unsure. No spec names the tuple, but tests/test_credentials.py:121 walks credentials.py's code structure, and I did not read what it pins.
Searched: `_CREDENTIAL_FAILURES` in src and docs/specs.

[Q1] LOW `credentials.py:353` — `if type(carried_version) is not int or carried_version != FILE_VERSION:` — The write path repeats `_secrets`' version check (297), with a comment recording the PRESS-0053 fix on the write side. It also differs: `_write_file` quietly replaces a `secrets` field that is not an object, which `_secrets` refuses. `_delete_file` calls `_secrets` ("Judged as read() judges it"). A stranger changing what counts as a valid file updates `_secrets` and misses this copy. Fix: have `_write_file` judge a carried file through `_secrets`.
Cost: unsure (tests/test_credentials.py:121 walks the code structure).

[Q4] LOW `settings.py:42-48` — `_MEASUREMENT_ID = re.compile(r"\AG-[A-Z0-9]+\Z")   # PRESS-0199 § 4.1` — The six-line comment about http/https and hosts describes `_SITE_ADDRESS`, but `_MEASUREMENT_ID` sits directly under it. A stranger reads the comment as the measurement id's rules. Fix: move the `_MEASUREMENT_ID` line above the comment.
Cost: one edit. The line moves within the file and no name changes.

[Q3] LOW `google_setup.py:165` — `def _pending() -> str:` — It returns Google's unverified-app warning. Elsewhere in the same file, `pending`, `state.pending` and `_Pending` all mean the list of properties waiting to be chosen. At the call site (155) a stranger assumes it shows that list. Fix: rename it after the warning.
Cost: one edit. Searched: `_pending\(` across the whole tree; only google_setup.py:155 and :165.

[Q3] LOW `usage.py:49` — `VERSION = 1` — This is usage.json's format version, but it sits beside the imported `__version__` (the app version, sent at 167). A stranger bumping the app version may bump this and make every saved answer read as invalid. Other modules call this `FILE_VERSION` or `CACHE_VERSION`. Fix: rename it `FILE_VERSION`.
Cost: unsure. `usage\.VERSION` has no hits across the tree, but I did not search PRESS-0262 for a bare `VERSION`.

[Q3] LOW `setup.py:839` — `kept = answers.get("store", "")` — In this file `kept` also holds an answers dict (790, 880), a `Credentials` (358), the untouchable list (`register`'s `kept` parameter) and an HTML list (579). At 848, `credentials.Choice(kept, …)` reads as if it receives the answers. `box` has the same problem: a yes/no at 211 and HTML at 1065. Fix: rename this one `store`.
Cost: one edit (a local name).

[Q4] LOW `github_setup.py:8` — `Every GitHub secret is read through `token`.` — setup.py:536 reads the GitHub secret directly with `credentials.read` (to tell a sign-in from a key). A stranger adding a check inside `token`, believing it sees every read, misses that path. Fix: say "every secret sent to GitHub".
Cost: one edit (comment).
Searched: `credentials\.read\(` in src.

[Q4] LOW `google_signin.py:51` — `PAGE_LIMIT = 10          # accountSummaries pages followed, at 200 accounts each` — `PAGE_LIMIT` also limits `measurement_ids`' dataStreams pages (202). The 200 is hard-coded separately at 169 and 203. Someone changing the page size edits the comment or one literal and misses the rest. Fix: a named page-size constant, and a comment naming both lists.
Cost: one edit. No spec search was needed: the fix renames nothing.
Candidate: comment google_signin.py:51.

[Q4] LOW `insights.py:10-11` — `It answers one question — how many people read the site over the last so many days, and from which countries` — The module now also returns readers per day, pages and sources (`_fetch`, 415–450). A stranger sizing a change to the cache or the request would underestimate what is involved. Fix: list all four tables.
Cost: one edit (comment).

[Q4] LOW `insights.py:175` — `The one seam. Tests are its only other caller.` — `usage._Opener` implements `insights.Transport`, and `google_signin` and `google_setup` pass it around. A stranger changing the Protocol on the strength of this line would break usage's client. Fix: drop "Tests are its only other caller" or name the real users.
Cost: one edit (comment).
Searched: `_own_client\(` and `class _Opener` in src.

[Q5] LOW `dashboard.py:41` — `DEFAULT_DAYS = insights.DEFAULT_DAYS` — `_sentence(DEFAULT_DAYS)` (`_card`, line 162) raises `StopIteration` unless the default is one of `WINDOWS`. The comment at 35 says only "28 is Insights' default". A stranger changing Insights' default breaks the list card. Fix: a comment stating that the default must be one of `WINDOWS`.
Cost: one edit (comment).

[Q3] LOW `settings.py:59` — `google_account: str | None    # None where the dashboard was declined` — It holds the name the secret is filed under (`sites.account("google", folder)`, google_setup.py:264), not the writer's Google account. Its sibling at 58 says this, but this line does not. A stranger would assume an email address. Fix: extend the comment the way line 58 does.
Cost: one edit (comment). The key name itself is fixed by the settings file format.

[Q4] LOW `settings.py:84` — `because Settings is blocker for the Store and may not import from it.` — "is blocker for" does not parse, so the stated dependency direction has to be guessed. Fix: reword it, for example "Settings sits below the Store".
Cost: one edit (comment).

[Q3] LOW `github_signin.py:78` — `_POLL_ERRORS: dict[str, type[PublishError]] = {` — `begin` (97) maps its errors through this table too. A stranger editing it for polling changes `begin` without knowing. Fix: rename it, or note that `begin` uses it.
Cost: one edit. Searched: `_POLL_ERRORS` across the tree; github_signin.py plus a test docstring at tests/test_github_signin.py:206 (not an ANCHORS entry).

[Q2] LOW `google_setup.py:308` — `+ _counting(saved.measurement_id if removed is None else None, found,` — To follow this you must work back through the swap at 281–284 to see that `kept` means the old id unless it was replaced. A stranger "simplifying" this to pass the new `measurement_id` would report a newly found id as kept. Fix: name the value before the call, for example `kept_id`.
Cost: one edit (a local name).

`settings.py:436`, `:448` — `target` is never used in `_required` or `_optional`. [tool?: unused argument]
`github_signin.py:138` — the parameter `login` shadows the module's own `login()` function. [tool?: redefined-outer-name]

## Candidates dismissed
- dup:4312e9c164bd — The copies differ only in their own notice type and words key, which INV-1 requires (settings may not import the Store). The SettingsNotice docstring says so.
- dup:3f9b6498042e — Two identical copies. The docstring says "as StoreNotice is", and INV-1 bars sharing it. No recorded fix touched both.
- dup:baeb82c37ac4 — Same reason as 4312e9c164bd.
- dup:4467d7066cd1 — Not a real divergence: `_back` has no Settings notices to prepend, because it never loads Settings.
- dup:55fa18cf4ac2 — Two identical page loops, with no recorded joint fix.
- dup:33fd9412c4cc — Two parsers that read different fields (`error` versus `error.status`), with no recorded joint fix.
- dup:a9f123edfd98 — A shared "read, or empty on failure" pattern with different meanings (a cache versus the user's answer). Not one behaviour.
- size insights.py:398 `_fetch` — Mostly the request body, with every table commented. Easy to follow.
- size settings.py:312 `save` — Its length is the duplicated read block, already reported under Q1.
- size settings.py:227 `check` and :148 `load` — Straight lists of rules, each commented.
- size setup.py:263 `_save_sequence` — Numbered step comments carry the reader through.
- size google_setup.py:252 `_choose` — The only real snag is reported as the Q2 at line 308.
- size insights.py:336 `read` — Short sections, each commented.
- comment insights.py:67 "400 names" — The 400 is HTTP status 400, not a count that drifts.

## Correctness leads
`google_setup.py:291-293` — `settings.check` and `settings.save` are not caught in `_choose`, after the refresh token has already been written. `_off` at 382–383 is the same. A `SettingsError` reaches whatever the Face does with uncaught errors. — Searched: none (the Face's catch-all not read)
`github_setup.py:75-76` — A stored sign-in with `register` not yet run raises an untyped `RuntimeError`. The callers catch only credential failures and `PublishError`. — Searched: `github_setup\.token\(` in src (callers listed above)
`credentials.py:359-365` — `_write_file` quietly replaces a `secrets` field that is not an object, where the read path refuses the file. — Searched: none

## Not checked
- updater.py's `_Urllib` and builder.py's `_why`: I confirmed each exists but did not read either.
- What tests/test_settings.py:97 and :111, tests/test_credentials.py:121, tests/test_google_signin.py:71 and tests/test_insights.py:273 pin. This is why several cost grades are "unsure".
- `docs/design.md` rule 10 and the import limits between parts. These would decide where a shared settings-loading helper could live.
- How the Face handles an uncaught exception.
- The CSS in dashboard.py `_STYLE` was read but not reviewed in detail. The JavaScript in setup.py `_PICTURE_SCRIPT` was read, and I found nothing in it.
