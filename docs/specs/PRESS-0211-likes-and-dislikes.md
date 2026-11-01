<!-- ants-spec-format: 1 -->
# PRESS-0211 — Visitors can like or dislike an entry, counted in the site's own free database

**Status:** accepted (2026-11-01).
**Kind:** feature.
**Source:** ROADMAP PRESS-0211 (user decision 2026-10-02; `docs/discovery.md`
§ Decided, not yet scheduled).

**Amends:** PRESS-0001 (§ 4.2), PRESS-0008 (§ 4.3), PRESS-0015 (§ 4.4),
PRESS-0182 (§ 4.2), PRESS-0195 (§ 4.4), PRESS-0199 (§ 4.5). § 11 lists each edit.

Layman: a site can show Like and Dislike buttons with public counts under each
entry. Each site uses its own free Google database, which Pressless helps set
up, and the buttons are off until then.

## 1. Goal

After this ships, a site whose Settings hold a Firebase project publishes every
entry with a Like and a Dislike button and their counts. A visitor can vote,
change the vote and take it back. Google's database enforces one vote per
anonymous visitor per entry. A site without a project publishes exactly what it
publishes today. The site never needs a billing account.

## 2. Problem

1. **A site of plain files cannot keep a count.** `docs/design.md` § The stack
   rules out a server of Pressless's own, and says a visitor's browser may talk
   to an outside service, naming likes as the second case after counting.
2. **Nothing identifies an entry for longer than its address.**
   `store.Entry` holds `slug` and `date`, and `builder.entry_path` makes the
   address from them. `POST /address` (`editor._address`, PRESS-0182) changes
   the slug. `store.read_forwards` maps old slugs to the current one, with no
   order among several, so it cannot name an entry's first address.
3. **Nothing puts a vote on a page.** `_Build.entry_page` writes the article,
   and `_Build.counted` is the only outside service's code a page gets.
4. **The Privacy page assumes counting.** `starter.privacy_page` always says the
   site counts visits with Google Analytics. `setup._privacy` runs only where
   Settings hold a `measurement_id`. A site with votes and no counting would
   carry a false page, or none.

## 3. Scope decisions (agreed with the user)

The user, 2026-10-02:

1. **Both buttons, with public counts**, in each site's own free Firebase
   database.
2. **Anonymous sign-in**, so one vote per person per entry. It is not a login:
   the visitor sees and does nothing for it.
3. **Billing stays off**, so the worst case of abuse is a quiet day.
4. **A line on the privacy page.**
5. **Optional per site, with step-by-step help** to set the database up.
6. **Four anti-spam layers:** a note in the visitor's browser, anonymous
   sign-in, a security rule, and App Check. One vote document per person buys
   changing and taking back a vote. `count()` avoids Cloud Functions.

Decided here, each open to the maintainer to overturn:

7. **App Check is supported and left to the site's owner, with off as the
   advice.** Firebase enforces it on every Firestore request, reads included, so
   it would put Google's reCAPTCHA on every entry page. reCAPTCHA's free
   allowance is 10,000 assessments a month, and with no billing account it then
   returns an error for the rest of the month. Sources:
   <https://docs.cloud.google.com/recaptcha/docs/billing-information>,
   <https://firebase.google.com/docs/app-check/web/recaptcha-enterprise-provider>.
   With enforcement on, that error stops the buttons. This changes how layer 4
   of decision 6 is applied, and the other three layers always run.
8. **The page talks to Google directly, with no Firebase library** (§ 8).
9. **Entries only.** Fixed pages, journal lists and forwards carry no buttons.
10. **Buttons are words with numbers, "Like 3"**, not icons. The user is
    partially sighted, and so are some readers.
11. **A preview shows the buttons, disabled and with no numbers**, so the writer
    sees where they sit. Its frame runs no script (PRESS-0217 § 4.2).
12. **Each vote is publicly readable, as a random id and a choice.** Probed on
    the emulator (§ 4.4): the rule that allows counting allows reading. The
    Privacy words say so.
13. **One person means one browser.** Clearing the browser's storage gives a
    new anonymous visitor. The discovery note accepts that with its "blunts".
14. **The setup steps are given, not automated.** Automating them needs a Google
    permission beyond the `analytics.readonly` `google_signin.SCOPE` holds.

## 4. Design

### 4.1 Settings

```python
# src/pressless/settings.py — added
@dataclass(frozen=True)
class Votes:
    api_key: str               # Firebase's public web key; not a secret
    project_id: str
    app_id: str
    recaptcha_key: str | None  # App Check, where the site's owner chose it

class Settings:
    ...
    votes: Votes | None = None
```

`votes` is optional on load: absent and `null` both load as `None`. `save` writes
it as a top-level object. `version` stays `1`, as for `measurement_id`
(PRESS-0199 § 4.1). `setup._candidate` names every field of the `Settings` it
builds, so it carries the saved `votes`; otherwise a Settings save clears them.
`check` refuses a value failing these with `SettingsError.key` `"votes"`:

| Field | Pattern |
|---|---|
| `api_key`, `recaptcha_key` | `\A[A-Za-z0-9_-]{20,100}\Z` |
| `project_id` | `\A[a-z][a-z0-9-]{4,39}\Z` |
| `app_id` | `\A[0-9]+:[0-9]+:web:[0-9a-f]+\Z` |

The patterns are what make § 4.3's code safe to write without escaping.
Firebase says these values are public by design
(<https://firebase.google.com/docs/projects/api-keys>), so they live in Settings
and never in Credentials. A saved site's file carries them with its settings.

### 4.2 The vote key

```python
# src/pressless/store.py — added
VOTE_KEY = "vote-key"          # an Entry.extra field

def vote_key(entry: Entry) -> str | None: ...
```

`vote_key` returns the entry's `vote-key` field where it has one, else
`YYYY-MM-DD-<slug>` from `entry.date` and `entry.slug`. It returns `None` where
the result fails `\A[0-9]{4}-[0-9]{2}-[0-9]{2}-[^/\s"'<>&]{1,189}\Z`. An entry
with `None` gets no buttons, so a hand-edited field cannot break the page.

**`_address` keeps the key.** Moving a published entry, or a draft carrying
undo's `Undone` mark (it was published, and can have votes), while Settings hold
`votes`, adds `vote-key` with the key from before the move, where the entry has
none. Later moves leave it. The field is an unrecognised header field, which
`store` already carries unchanged, so PRESS-0005's format does not change.
`undo._keep` drops the field, since the draft it keeps becomes another entry.

### 4.3 The page

```python
# src/pressless/votes.py — new; touches no disk and no network
RULES: str                                       # § 4.4
def buttons(key: str) -> str: ...                # the markup below, disabled
def page_code(votes: settings.Votes) -> str: ... # a <script type="module">
def parse_config(pasted: str) -> dict[str, str]: ...  # § 4.6
```

**`_Build.entry_page`**, where Settings hold `votes` and `vote_key` is not
`None`, puts this immediately after the `post-tags` paragraph, in a preview and
on a publish alike:

```html
<div class="votes" data-vote="2026-11-01-seaside">
  <button type="button" class="vote" data-value="1" aria-pressed="false" disabled>Like <span class="vote-count"></span></button>
  <button type="button" class="vote" data-value="-1" aria-pressed="false" disabled>Dislike <span class="vote-count"></span></button>
</div>
```

The markup comes with a small `<style>` so it works on any site's look: colours
inherit, a pressed button differs by more than colour, and a count holds its
space empty, so nothing shifts when numbers arrive. The two labels come from
Words.

**A publishing build** adds `page_code` to that page through `_inserted`, as
`counted` does. A preview never does. `_Build.page` takes the code as an optional
argument, so only `entry_page` can pass it.

**What the script does**, with `KEY` the box's `data-vote`:

1. **On load:** ask Firestore for each button's count with
   `POST https://firestore.googleapis.com/v1/projects/P/databases/(default)/documents/entries/KEY:runAggregationQuery?key=K`,
   a `count` over `votes` where `value` equals the button's value. It sends no
   sign-in. Then fill the numbers, mark the button the visitor's note names, and
   enable both.
2. **On a press:** disable both, then get a token: exchange the stored refresh
   token at `https://securetoken.googleapis.com/v1/token`. Where there is none, or
   Google refuses it with a 400, sign up at
   `https://identitytoolkit.googleapis.com/v1/accounts:signUp`, store what it
   returns and clear the note's `votes`, so this press is a first vote. Any other
   failure is a failed press. Then:
   - the button already pressed: `DELETE .../entries/KEY/votes/<uid>`;
   - otherwise: `PATCH .../entries/KEY/votes/<uid>` with `value`.
   On success, update the note, the numbers and `aria-pressed`. Then enable both.
3. **The note** is one `localStorage` item, `pressless-votes`:
   `{"refresh": "...", "votes": {"KEY": 1}}`. Nothing is stored before the first
   press, while `recaptcha_key` is unset.
4. **With `recaptcha_key`:** before step 1, import `firebase-app.js` and
   `firebase-app-check.js` from `https://www.gstatic.com/firebasejs/13.1.0/`,
   start App Check with `ReCaptchaEnterpriseProvider`, and send its token as
   `X-Firebase-AppCheck` on every Firestore call. Whether Firestore's REST
   interface honours that header is **unverified**, and § 7's hand check settles
   it. Firebase documents the header for a site's own server
   (<https://firebase.google.com/docs/app-check/web/custom-resource>). Google's
   preflight accepts it from a browser: measured 2026-11-01 with `curl -X OPTIONS`
   on all three hosts.

Any failure leaves the buttons as they were before the press, or disabled with
no numbers where step 1 failed. The script catches everything and shows no
message, and it never touches anything outside the box.

### 4.4 The rules

`votes.RULES`, which the writer pastes into Firebase:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /entries/{entry}/votes/{voter} {
      allow list: if true;
      allow get, delete: if request.auth != null && request.auth.uid == voter;
      allow create, update: if request.auth != null
        && request.auth.uid == voter
        && entry.size() <= 200
        && entry.matches('[0-9]{4}-[0-9]{2}-[0-9]{2}-.+')
        && request.resource.data.keys().hasOnly(['value'])
        && request.resource.data.value in [1, -1];
    }
  }
}
```

**The document id is the visitor's id**, so a second vote can only overwrite the
first. **Measured 2026-11-01** on the Firestore and Auth emulators
(`firebase-tools` 15.34.2, emulator 1.22.0), over REST: each `write` refused
below answered 403, and counts stayed right through a vote, a change and a
removal.

**`allow list: if true` is required.** `if false` refuses `count`. Narrowing
does not hide votes: `if request.query.limit == null` allowed `count` and refused
a plain listing, and a `runQuery` with no limit still returned every vote. So
§ 3 decision 12 stands.

### 4.5 The Privacy page

```python
# src/pressless/starter.py — changed
def privacy_page(site_name, sheets, *, counting: bool, votes: bool, recaptcha: bool) -> str: ...
def add_privacy(folder, site_name, *, counting: bool, votes: bool, recaptcha: bool) -> tuple[bool, bool]: ...
```

`privacy_page` writes the counting words only with `counting`, and new votes
words only with `votes`. The votes words say, in words the implementer chooses:
pressing Like or Dislike stores a random id in the visitor's browser and a vote
in a Google Firebase database; the vote and the random id can be read by anyone;
no name, email address or account is involved, and Google sees the visitor's
internet address; a link to Google's privacy policy. `recaptcha`, which is
`recaptcha_key` being set, adds words saying that every entry page loads Google's
reCAPTCHA and Firebase's App Check on each visit, before any press.

`add_privacy` keeps its footer step. **Where the page exists** and its text lacks
`Google Analytics` while `counting`, `Firebase` while `votes`, or `reCAPTCHA` while
`recaptcha` (each ignoring case), it adds those words as sections immediately
before `<!-- /pressless:page -->`. A page with no such mark gets them as plain
paragraphs, since section marks outside an area do not pair: before the first
`</main>`, else at the end. So each is added once, and a writer's own wording of any stands. It treats a
waiting copy of the page the same way, since pressing that copy replaces the page.

`setup._privacy` runs where Settings hold either, and the save in § 4.6 calls it
too. `google_setup`'s own call to `add_privacy` passes what Settings hold. A failure
keeps the settings, as PRESS-0199 § 4.5 does.

`page_editor._reshape_hint` refuses to remove the Privacy page while Settings
hold either.

### 4.6 Setting it up

A new screen, `votes_setup.py`, reached from a row on the Settings page. It is
part of the Face, as `google_setup` is.

**`GET /votes`** shows the state, then numbered steps from Words:

1. Open `console.firebase.google.com` and add a project. Refuse any offer of a
   paid plan, and Google Analytics is not needed.
2. Create a Firestore database in production mode, in the nearest location.
3. In its Rules, replace the text with `votes.RULES`, shown with a Copy button,
   and publish.
4. In Authentication, turn on the Anonymous sign-in method.
5. Add a web app to the project, copy the `firebaseConfig` text, and paste it
   into the box below.

The steps also warn that GitHub may flag the key once published, and Google may
email about it, and that this is expected: GitHub's table lists `google_api_key`
for alerts and not for push protection
(<https://docs.github.com/en/code-security/secret-scanning/introduction/supported-secret-scanning-patterns>).
App Check's steps are folded away, stating § 3 decision 7's cost.

**`POST /votes`** runs `votes.parse_config` over the box: it finds
`apiKey`, `projectId` and `appId`, each `name: "value"` or `"name": "value"`. A
missing one, or one § 4.1 refuses, is a hint beside the box and saves nothing.
An optional second box holds `recaptcha_key`. Saving runs § 4.5, then **Check**,
and says buttons appear at the next press.

**`POST /votes/check`** asks Google, through `https`, in this order:

| Step | Answer | Says |
|---|---|---|
| sign up | refused | turn on Anonymous sign-in (step 4) |
| write `entries/0000-00-00-pressless-check/votes/<uid>` `value` 1 | 403 | paste the rules (step 3) |
| | 404 | create the database (step 2) |
| write it again with `value` 5 | accepted | the rules are not the ones shown (step 3) |
| count, with no sign-in | refused | the rules are not the ones shown (step 3) |
| delete it | refused | the rules are not the ones shown (step 3) |
| all passed | | ready |
| no answer at any step | | could not reach Google; nothing is wrong yet |

With `recaptcha_key` set, Check does not run and the screen says it cannot be
checked from this computer. **`POST /votes/off`** clears `votes`.

**Switching off** removes the buttons at the next press. Votes stay in the
writer's database, and the Privacy words stay, as PRESS-0199's decision 8 keeps
its page.

### 4.7 Files touched

New: `src/pressless/votes.py`, `src/pressless/votes_setup.py`,
`tests/test_votes.py`, `scripts/by-hand-votes-rules.py`. Changed: `settings.py`,
`store.py`, `builder.py`, `editor.py`, `starter.py`, `setup.py`, `google_setup.py`,
`page_editor.py`, `undo.py`, `__main__.py` (registers the screen), `words.py`,
`scripts/by-hand-browser-checks.py`, and `tests/test_blocks.py` and
`tests/test_words.py`, which call the two changed `starter` functions.
`tests/test_settings.py`, `tests/test_builder.py`, `tests/test_store_extras.py`
and `tests/test_setup.py` pin what this item adds or changes.

## 5. Invariants

- **INV-1** — `votes` round-trips through `settings.save` and `load`; a file
  without it loads as `None`; a save from the Settings page keeps it; a value
  failing § 4.1 is refused with key `"votes"`.
  *Test:* `tests/test_votes.py::test_settings_votes_round_trip`, `::test_settings_page_keeps_votes`, `::test_settings_refuses_a_bad_votes_value`.
  *Breaks when:* a field is dropped on save, `_candidate` omits `votes`, or `check` lets a quote through.

- **INV-2** — With `votes` `None`, no built page holds `class="votes"`,
  `firestore.googleapis.com` or a Votes style.
  *Test:* `tests/test_votes.py::test_off_adds_nothing`.
  *Breaks when:* the markup or style is written unconditionally.

- **INV-3** — With `votes` set, a publish puts buttons and `page_code` on each
  entry page and on nothing else. A preview shows the buttons, disabled, and no
  `page_code`.
  *Test:* `tests/test_votes.py::test_publish_entry_pages_only`, `::test_preview_has_no_code`.
  *Breaks when:* the code goes through `_Build.page` for every page, or `preview` passes it.

- **INV-4** — Trust boundary, what the writer pastes and what an entry file holds.
  Nothing in a `Votes` value or a `vote-key` field reaches a page unless it passes
  its pattern, so neither can add markup or script. Pressless never stores these
  values in Credentials, and never holds Firebase's secret reCAPTCHA material.
  *Test:* `tests/test_votes.py::test_hostile_vote_key_gets_no_buttons`, `::test_parse_config_refuses_markup`.
  *Breaks when:* `vote_key` returns a field unchecked, or `parse_config` skips § 4.1.

- **INV-5** — An entry's vote key does not change when its address does, through
  repeated moves and an undo. A draft `undo._keep` makes holds no `vote-key`.
  *Test:* `tests/test_votes.py::test_key_survives_moves_and_undo`, `::test_kept_draft_has_no_key`.
  *Breaks when:* `_address` overwrites an existing field, computes the key after the move, or `_keep` copies the field.

- **INV-6** — `votes.RULES` refuses each of: voting with no sign-in, writing
  another visitor's vote, deleting another's vote, a value other than 1 or -1, a
  value of another type, an extra field, an entry key of the wrong shape or too
  long, and any write outside `entries`. It allows counting with no sign-in, and a
  visitor's own vote, change and removal.
  *Test:* `scripts/by-hand-votes-rules.py`, which runs `votes.RULES` on the
  emulators and exits non-zero on any wrong answer.
  *Breaks when:* a clause of the rule is removed; the script's probe for it must then fail.
  The one exception is `request.auth != null` on create and update: `request.auth.uid == voter`
  already refuses a visitor with no sign-in, so removing it changes no answer (measured 2026-11-01).

- **INV-7** — The page script: a press with no vote stores the vote; a press on
  the other button changes it; a press on the same button removes it; the numbers
  follow each. Before the first press it stores nothing and sends no sign-up. A
  refused refresh token signs up anew and clears the note's `votes`; an exchange
  with no answer signs up nothing.
  *Test:* rows in `scripts/by-hand-browser-checks.py`, with the three Google hosts
  answered by a test double, on Chrome, Edge and Firefox.
  *Breaks when:* the script signs up on load, or a repeat press sends a PATCH.

- **INV-8** — Where any Google call fails, the entry reads as normal. A failed
  load leaves both buttons disabled with no numbers, and a failed press restores
  the state from before it, with neither shifting the layout.
  *Test:* rows in `scripts/by-hand-browser-checks.py`, one per call failing.
  *Breaks when:* a rejected fetch escapes, or the numbers change before the answer.

- **INV-9** — A page `privacy_page` writes with votes and no counting says nothing
  of Google Analytics; with `recaptcha` it names reCAPTCHA, and without it does not. Each disclosure is added to an existing Privacy page once, and a
  Store holding no site gets no page. The page cannot be removed while `votes` is set.
  *Test:* `tests/test_votes.py::test_privacy_says_only_what_is_on`, `::test_privacy_adds_each_once`, `::test_privacy_page_stays_while_votes_on`.
  *Breaks when:* `privacy_page` keeps its counting words unconditionally, or `_reshape_hint` still reads `measurement_id` alone.

- **INV-10** — Check gives § 4.6's answer for each Google reply, and removes its own
  test vote on every path past the first write.
  *Test:* `tests/test_votes.py::test_check_answers`, with `https` answered by a double.
  *Breaks when:* a 403 on the first write reads as "could not reach Google", or a
  failure skips the delete.

- **INV-11** — Switching off clears `votes` alone: the next build carries no buttons,
  `vote-key` fields stay, and the Privacy words stay.
  *Test:* `tests/test_votes.py::test_off_keeps_keys_and_privacy`.
  *Breaks when:* switching off strips fields or rewrites the Privacy page.

- **INV-12** — A saved site's file brings `votes` with it to another computer.
  *Test:* `tests/test_votes.py::test_site_file_carries_votes`.
  *Breaks when:* `sitefile`'s rewrite of the settings names its keys and omits `votes`.

## 6. Failure modes

- **A quota runs out:** Google refuses, and INV-8 applies until the quota resets
  around midnight Pacific. The Firebase plans page also says Spark usage of a
  product is "shut off for the remainder of that month", with no reconciliation
  against its daily Firestore quotas, so the free tier's real stopping behaviour
  is unverified. No bill arises either way.
- **Someone scripts votes:** anonymous sign-ups are limited per IP address; counts
  can still be skewed, and stored votes can fill the free storage. The owner can
  turn on App Check, or delete data in Firebase. Nothing costs money.
- **reCAPTCHA's allowance runs out with App Check enforced:** buttons disabled, as
  § 3 decision 7 warns, until the next month.
- **The visitor's browser refuses `localStorage`:** counts show, and both buttons
  stay disabled, since a vote could not be remembered.
- **The refresh token stops working:** the visitor signs up anew and can vote again.
  The old vote stays counted, under the old id.
- **An undo takes a moved entry back to its old address:** `undo._demote` leaves the
  moved copy as a draft holding `vote-key`. Pressing that draft while the restored
  entry is on the site gives the two one count. Accepted, because a demoted entry
  with no restored twin must keep its votes.
- **An entry moved while `votes` was off:** it has no field, so its earlier votes
  stay under its old key. Accepted: it needs a switch off, a move and a switch on.
- **An entry is thrown away and a new one takes its date and slug:** it inherits the
  votes. Accepted as vanishingly rare.
- **A site's own policy blocks inline scripts or Google:** the buttons stay disabled.
- **Firebase changes its console:** the steps go stale, and § 7's hand check reads
  them against it.

## 7. Tests

`tests/test_votes.py` locks INV-1, INV-2, INV-3, INV-4, INV-5, INV-9, INV-10,
INV-11 and INV-12 on Linux and on Windows. Each fails against code without this item. Values look fake, per the
project's sentinel rule.

**Nothing in CI runs Firestore's rules, or the page's script.**
`scripts/by-hand-votes-rules.py` (INV-6) needs Java and `firebase-tools`, and
says so and exits non-zero where they are absent. The browser rows (INV-7, INV-8)
answer Google's hosts with a double.

**Owed by hand before the next release, on a real scratch Firebase project and
scratch repository**, added to PRESS-0133:

- Every step of § 4.6, read against the console as it stands, on a project with
  no billing account; Check answering "ready", and each wrong state it names.
- A real publish and vote, in Chrome, Edge and Firefox, from Linux and the Windows
  box: vote, change, take back, reload, and a second browser's count.
- What GitHub and Google actually do about the published key.
- `recaptcha_key` with enforcement on: whether Firestore's REST interface honours
  `X-Firebase-AppCheck`, and that a request without it is refused. **If it does
  not, App Check support comes out and the spec is folded back.**
- The rules, confirmed on real Firestore as § 4.4 measured on the emulator.

## 8. Alternatives considered (and rejected)

- **Firebase's JavaScript library.** Firebase documents it from the CDN
  (<https://firebase.google.com/docs/web/alt-setup>). Every entry view would load
  `firebase-app.js` and `firebase-firestore.js` at 13.1.0: 23,818 and 186,805
  compressed bytes, measured 2026-11-01 with `curl --compressed -w
  '%{size_download}'`, to fetch two numbers. Plain calls need a short script, were
  proved on the emulator, and Google's preflight allows them from a browser. The
  cost is that the script handles tokens itself, which § 4.3 keeps to one exchange
  per press.
- **The script as a published file.** It saves bytes per page and adds a file the
  Builder owns. `page_code` inline is what `counting_code` already does.
- **Counters in the database.** They need a trusted server to stay honest, which is
  Cloud Functions and so billing.
- **Hiding individual votes.** § 4.4 measured that the rules cannot.
- **Keying votes on the current address.** A move would lose them.
- **Keying votes on `store.read_forwards`.** It holds no order, so the first address
  cannot be found.
- **Setting the project up through Google's interfaces.** § 3 decision 14.
- **A switch on each entry.** Nothing asked for it.
- **reCAPTCHA v3 for App Check.** Firebase recommends Enterprise for new
  integrations, and v3 adds a secret key for the owner to handle.

## 9. Out of scope

- Totals in Insights or the dashboard — deferred; not yet queued.
- Votes on fixed pages — deferred; not yet queued.
- Moving votes between entries, or an entry whose field is lost — deferred; not yet queued.
- Restricting the public key to the site's address in Google Cloud — deferred; not
  yet queued. A script can send any address, so it stops little and costs a step.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_votes.py::test_settings_votes_round_trip`, `::test_settings_page_keeps_votes`, `::test_settings_refuses_a_bad_votes_value` |
| INV-2 | `tests/test_votes.py::test_off_adds_nothing` |
| INV-3 | `tests/test_votes.py::test_publish_entry_pages_only`, `::test_preview_has_no_code` |
| INV-4 | `tests/test_votes.py::test_hostile_vote_key_gets_no_buttons`, `::test_parse_config_refuses_markup` |
| INV-5 | `tests/test_votes.py::test_key_survives_moves_and_undo`, `::test_kept_draft_has_no_key` |
| INV-6 | **Partial:** `scripts/by-hand-votes-rules.py` on the emulators, run by hand; real Firestore only by § 7's hand check |
| INV-7 | **Partial:** `scripts/by-hand-browser-checks.py`, run by hand, against a double |
| INV-8 | **Partial:** `scripts/by-hand-browser-checks.py`, run by hand, against a double |
| INV-9 | `tests/test_votes.py::test_privacy_says_only_what_is_on`, `::test_privacy_adds_each_once`, `::test_privacy_page_stays_while_votes_on` |
| INV-10 | `tests/test_votes.py::test_check_answers` |
| INV-11 | `tests/test_votes.py::test_off_keeps_keys_and_privacy` |
| INV-12 | `tests/test_votes.py::test_site_file_carries_votes` |
| The steps match Firebase's console | **nothing** — § 7's hand check, once per release; the console changes without notice |
| Billing stays off | **nothing** — a choice the site's owner makes in Google's console; the steps tell them to refuse |
| App Check works over plain calls | **nothing** until § 7's hand check; unverified |

## 11. Cross-doc impact

- **PRESS-0001 § 4.2:** Settings gains `votes`.
- **PRESS-0008 § 4.3:** an entry page may carry the buttons and `page_code`.
- **PRESS-0015 § 4.4:** undo's kept draft drops `vote-key`.
- **PRESS-0182 § 4.2:** moving an entry may add `vote-key` (§ 4.2 says which).
- **PRESS-0195 § 4.4:** the Privacy page also stays while `votes` is set.
- **PRESS-0199 § 4.5:** the Privacy page's words depend on what is on, and an
  existing page gains missing words.
- **`docs/discovery.md`** § Decided, not yet scheduled: the note points here, with
  § 3 decision 7's change of how App Check applies.
- **`docs/design.md`**, "Privacy is the one page Pressless keeps": votes join
  counting as a reason for the page.
- **`CHANGELOG.md`:** under the release that carries it.
- **The Hub:** told after the release, as any change a visitor would notice.
- **PRESS-0133:** § 7's rows.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0211-likes-and-dislikes-loop-log.md`.

## 13. Resource cost

**On the visitor:** the script and its style inline on each entry page, and two
requests per view. App Check, where chosen, adds Firebase's two files and Google's
reCAPTCHA.

**On the site's free quota:** each view spends at least two document reads, one per
`count`, or one more per further thousand votes on the entry. Firestore's free
quota is 50,000 reads and 20,000 writes a day
(<https://firebase.google.com/docs/firestore/pricing>), so about 25,000 entry views a
day on entries under a thousand votes.

**Dependencies:** none added to Pressless. `firebase-tools` and Java are needed only
by the by-hand script, and are never packaged.
