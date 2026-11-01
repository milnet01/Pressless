<!-- ants-spec-format: 1 -->
# PRESS-0081 — Show a YouTube channel's public counts, by the writer's own key

**Status:** accepted (2026-11-01).
**Kind:** feature.
**Source:** ROADMAP PRESS-0081 (user request 2026-09-02; user decision 2026-11-01).

**Amends:** PRESS-0001 (§ 4.2), PRESS-0223 (§ 4.2), PRESS-0224 (§ 4.1). § 11 lists
each edit.

Layman: a writer who pastes in a free YouTube key and their channel's address
sees the channel's public figures, and each video's, inside Pressless.

## 1. Goal

After this ships, a site whose Settings hold a YouTube channel and key has a
YouTube screen. It shows the channel's subscribers, views and video count, and
each video's views, likes and comments. A site without them is unchanged, and
nothing about writing or publishing depends on them.

## 2. Problem

1. **Insights reads one service.** `insights.read` asks Google Analytics alone.
   `docs/design.md` rule 8 already allows a second service, with one cache file
   per service (PRESS-0079).
2. **The dashboard page needs an Analytics sign-in.** `dashboard._set_up` is false
   without `analytics_property_id` and `google_account`, and `dashboard._show` then
   shows nothing else. A channel must not need either.
3. **Settings has nowhere for it.** `settings.Credentials` names two secrets, and
   `settings.Settings` no channel.

## 3. Scope decisions (agreed with the user)

The user, 2026-11-01:

1. **Public counts first, by an API key.** The owner's watch time is not built.
2. **Spotify, Apple Music and Amazon Music are parked**, as the writer is focusing
   on YouTube for now.

Decided here, each open to the maintainer to overturn:

3. **Each writer makes their own key.** YouTube's policies forbid embedding API
   credentials "in open source projects", and Pressless is one. Source:
   <https://developers.google.com/youtube/terms/developer-policies> § III.D.1.
4. **The key is a secret, in Credentials.** A Firebase web key is public by design
   (PRESS-0211). This one is not published anywhere, and spends the writer's quota.
5. **A screen of its own, not a panel on the dashboard**, by § 2 item 2.
6. **Only what YouTube says.** The policies forbid using API data "to create new or
   derived data or metrics", so no totals, ratios, trends or history. Sorting is
   not a metric.
7. **Figures are kept at most 30 days.** The policies say an API client "must not
   store statistics retrieved as Non-Authorized Data for more than 30 days". That
   a key's reads are Non-Authorized Data is this spec's reading.
8. **The screen says YouTube is the source, and links YouTube's Terms of Service and
   Google's Privacy Policy**, as § III.A of the policies asks of an API client.
   Whether the policy's "agree to a privacy policy" reaches a writer using their
   own key on their own computer is unsettled by the page; the links are the cheap
   half, and nobody else's data is involved.

## 4. Design

### 4.1 Settings and Credentials

```python
class Credentials:
    ...
    youtube_account: str | None = None   # optional on load

class Settings:
    ...
    youtube_channel: str | None = None   # "@handle" or "UC..."; optional on load
```

`settings.check` refuses a channel matching neither `@[^\s/?#&<>"']{1,100}` nor
`UC[A-Za-z0-9_-]{22}`, with key `"youtube_channel"`. The key's account name is
`sites.account("youtube", folder)`. `setup`'s `_candidate` keeps both fields, as it
keeps `votes`.

### 4.2 The part: `src/pressless/youtube.py`

The second file of Insights (rule 8). It imports `Transport`, `_own_client`,
`_within`, `DEFAULT_MAX_AGE` and the failure classes from `insights`, and gains two:

```python
class ChannelNotFound(InsightsError): ...

CACHE_NAME = "youtube.json"
MAX_KEPT = 30 * 24 * 3600.0
PAGE_SIZE = 50
VIDEO_LIMIT = 500

@dataclass(frozen=True)
class Video:
    id: str
    title: str
    published: str             # snippet.publishedAt, as given
    views: int | None
    likes: int | None          # None where YouTube gives no number
    comments: int | None

@dataclass(frozen=True)
class Report:
    channel: str               # the value asked about
    title: str
    subscribers: int | None    # None where hidden
    views: int
    video_count: int
    videos: tuple[Video, ...]  # most viewed first
    fetched_at: float
    stale: bool

def parse_channel(text: str) -> str              # raises ValueError
def check(channel: str, key: str, *, client=None) -> str    # the channel's title
def read(channel: str, key: str, folder: Path, site_folder: Path, *,
         max_age_seconds: float = DEFAULT_MAX_AGE, client=None) -> Report
def kept(folder: Path, channel: str, now: float) -> Report | None
def forget(folder: Path) -> None
```

**`parse_channel`** takes `@name`, a bare `UC...` id, or an address ending
`youtube.com/@name` or `youtube.com/channel/UC...`, with or without `https://`,
`www.` or `m.`, and returns the value § 4.1 stores. Anything else raises, a
`/c/` or `/user/` address included, since `channels.list` has no parameter for them.

**The calls**, each to `https://www.googleapis.com/youtube/v3/`, each with the key in
an `X-Goog-Api-Key` header, never in the address. Measured 2026-11-01: a fake key
in that header gets the same 400 `API_KEY_INVALID` as in `key=`, and no key gets a
403. So error text and logs cannot carry the key.

1. `channels?part=snippet,statistics,contentDetails` with `forHandle` or `id`.
   `items` empty or absent raises `ChannelNotFound`.
2. `playlistItems?part=snippet&maxResults=50&playlistId=<uploads>`, following
   `nextPageToken`, stopping at `VIDEO_LIMIT` ids. `uploads` is
   `contentDetails.relatedPlaylists.uploads`, and an id is
   `snippet.resourceId.videoId`. YouTube's page does not state an order.
3. `videos?part=snippet,statistics&id=<up to 50, comma-joined>`. A video the answer
   omits is left out. YouTube's page states no limit on ids; § 7 confirms 50.

A full read of `VIDEO_LIMIT` videos costs 21 units of a default 10,000 a day
(1 + 10 + 10, one unit a call: the three methods' list pages and
<https://developers.google.com/youtube/v3/getting-started>).

**Numbers.** YouTube sends them as strings. A missing `likeCount`, `commentCount` or
`viewCount` reads as `None`: the documents do not settle what a hidden one looks
like. `hiddenSubscriberCount` true, or a missing `subscriberCount`, gives `None`.
A channel's missing `viewCount` or `videoCount`, or an answer of the wrong shape,
raises `InsightsError`.

**Failures.** No answer raises `Unreachable`. 400, 401 and 403 raise `Refused`, except
that a body holding `quotaExceeded` raises `RateLimited`. The rest raise
`InsightsError`. Each carries `insights._detail`. Reading the body breaks that
function's "never parsed for meaning" on purpose: a wrong match still shows YouTube's
own words, and the writer needs to know whether to fix the key or wait.

**`read`** refuses a `folder` inside `site_folder`, as `insights.read` does. It answers
from the cache while `0 <= age < max_age_seconds` and the cache is for this `channel`;
otherwise it asks YouTube. On `InsightsError` it returns the `kept` report with
`stale` set, or raises where there is none, except `Refused` and `ChannelNotFound`,
which always raise: the writer has something to fix.

**`kept`** returns the cached report for this channel. Where the file's `fetched_at` is
more than `MAX_KEPT` old, or in the future by more than a day, it deletes the file and
returns `None`. A write failure on the cache fails nothing, as in `insights._store`.

**The cache** is `youtube.json` in `folder`, one report, written with `write_whole`.
Another version reads as absent. It joins `sites.SITE_NAMES` and `sitefile.LEFT_OUT`,
so it stays with its site's folder and out of a site's file.

### 4.3 The screen: `src/pressless/youtube_screen.py`

Part of the Face. Only it reaches Credentials for this key (rule 10).

**`GET /youtube`**, with neither setting: says it is off and links the setup. With
both: reads the key, calls `read`, and shows:

- the channel's title, "From YouTube", and when it was fetched, or that the figures
  are old and when from (`Report.stale`), so history is "presented accurately in
  context of time";
- subscribers, as "about N" since YouTube rounds down to three significant figures,
  or "hidden"; views; videos;
- a table of the fifty most viewed: title, published date, views, likes, comments.
  A `None` shows "hidden". Each title links
  `https://www.youtube.com/watch?v=<id>`. Where more exist, a line says how many
  are shown of how many read;
- the two links of § 3 decision 8.

The columns keep their place, per the project's fixed-layout rule. A failure uses
`face.fail(exc, publishing=False)`; `Refused` and `ChannelNotFound` add a link to the
setup. A `credentials.FAILURES` failure is told as one, naming the YouTube key.

**The list's card**, added with `face.add_to_list`, shows only with both settings. It
calls `kept` and never YouTube, as `dashboard._card` does.

**`GET /youtube/setup`** shows the state, numbered steps from Words, a channel box and
a password box:

1. Open `console.cloud.google.com` and create a project.
2. In its API library, enable YouTube Data API v3.
3. In Credentials, create an API key, and restrict it to that one API.
4. Paste it below, with your channel's address.

**`POST /youtube/setup`**: `parse_channel`, then `check`, then `credentials.write` and
`settings.save`. An empty key box with a key held keeps it. Any failure is a hint beside
its box, and saves nothing. A changed channel calls `forget`.

**`POST /youtube/off`** does as `google_setup._off`: deletes the key and the cache and
clears both settings, each failure stopping nothing, the page saying what may remain.

**Settings** gains a row beside the votes row, linking `/youtube/setup`.

### 4.4 Files touched

New: `src/pressless/youtube.py`, `src/pressless/youtube_screen.py`,
`tests/test_youtube.py`. Changed: `settings.py`, `setup.py`, `sites.py`, `sitefile.py`,
`__main__.py` (registers the screen), `words.py`.

## 5. Invariants

- **INV-1** — Both fields round-trip through `settings.save` and `load`; a file without
  them loads as `None`; a save from the Settings page keeps them; a channel failing
  § 4.1 is refused with key `"youtube_channel"`.
  *Test:* `tests/test_youtube.py::test_settings_round_trip`, `::test_settings_page_keeps_them`, `::test_settings_refuses_a_bad_channel`.
  *Breaks when:* `_candidate` omits a field, or `check` lets a quote through.

- **INV-2** — Trust boundary, the key. It goes out in the header alone, and never reaches
  an address, a failure's words, the cache, a page or `settings.json`.
  *Test:* `tests/test_youtube.py::test_key_only_in_header`, with a double recording each request, a failure from each status, and a search of every file written and page shown.
  *Breaks when:* the key goes in `key=`, or a failure formats the request.

- **INV-3** — Trust boundary, what YouTube sends. A title holding markup shows as text, and
  a video id outside `[A-Za-z0-9_-]+` gets no link.
  *Test:* `tests/test_youtube.py::test_hostile_title_and_id`.
  *Breaks when:* a title reaches the page unescaped, or an id is joined unchecked.

- **INV-4** — With neither setting, `/youtube` makes no request, the card is absent, and the
  dashboard and a publish are as they were.
  *Test:* `tests/test_youtube.py::test_off_asks_nothing`.
  *Breaks when:* the card calls `read`, or the screen requires one setting and not both.

- **INV-5** — A cache older than `MAX_KEPT` is deleted and not shown, even when YouTube cannot
  be reached; one younger is shown marked stale, and one under `max_age_seconds` asks nothing.
  *Test:* `tests/test_youtube.py::test_cache_ages`, using times just each side of each limit.
  *Breaks when:* `read` falls back on the raw file, or `kept` tests only one end of the age.

- **INV-6** — A cache for another channel answers nothing.
  *Test:* `tests/test_youtube.py::test_cache_is_per_channel`.
  *Breaks when:* `kept` does not compare `channel`.

- **INV-7** — `read` follows every page, stops at `VIDEO_LIMIT`, sends at most 50 ids a call,
  omits a video YouTube omits, and orders by views with `None` last.
  *Test:* `tests/test_youtube.py::test_walks_pages`, against a double whose first page alone would pass a one-page read.
  *Breaks when:* `nextPageToken` is ignored, or a `None` raises in the sort.

- **INV-8** — A hidden subscriber count, like count or comment count shows "hidden", never 0.
  *Test:* `tests/test_youtube.py::test_hidden_is_not_zero`.
  *Breaks when:* a missing number defaults to 0.

- **INV-9** — Each failure gets § 4.2's type: a 400, a 403, a 403 with `quotaExceeded`, a 500,
  no answer, an empty `items`. `Refused` and `ChannelNotFound` raise past a kept report.
  *Test:* `tests/test_youtube.py::test_failures`, `::test_refused_beats_the_cache`.
  *Breaks when:* quota reads as a bad key, or a dead key hides behind old figures.

- **INV-10** — `parse_channel` takes each form of § 4.2 and refuses `/c/`, `/user/`, another host,
  and text holding markup.
  *Test:* `tests/test_youtube.py::test_parse_channel`.
  *Breaks when:* it searches for `youtube.com` anywhere in the text, so `evil.example/youtube.com/@x` passes.

- **INV-11** — A refused setup saves nothing, keyring and file alike. Turning off removes the key,
  the cache and both settings, and says what could not be removed.
  *Test:* `tests/test_youtube.py::test_setup_refused_saves_nothing`, `::test_off_removes_everything`.
  *Breaks when:* the key is written before `check`, or a failed delete stops the save.

- **INV-12** — `youtube.json` stays out of a site's file and within its own site's folder, and the
  file names the right account on the other computer.
  *Test:* `tests/test_youtube.py::test_site_file_leaves_the_cache_out`, `::test_site_file_renames_the_account`.
  *Breaks when:* `LEFT_OUT` or `SITE_NAMES` omit it, or `sitefile._settle` omits `youtube_account`.

## 6. Failure modes

- **The day's quota runs out:** kept figures show marked stale, or the page says to try tomorrow.
- **A key is deleted or restricted away:** `Refused` shows YouTube's words and the setup link.
- **The channel changes its handle:** `ChannelNotFound`, and the setup link.
- **A channel with more than `VIDEO_LIMIT` videos:** some are unread, and the page says how many
  of how many. YouTube states no order, so which ones is not promised.
- **Pressless stays closed past 30 days:** the file sits on the writer's own computer until the
  next start's card deletes it. Accepted: nothing runs while it is closed.
- **YouTube's error text changes:** quota reads as `Refused`, still with YouTube's words.
- **Google's console changes:** the steps go stale, and § 7 reads them against it.

## 7. Tests

`tests/test_youtube.py` locks INV-1, INV-2, INV-3, INV-4, INV-5, INV-6, INV-7, INV-8, INV-9,
INV-10, INV-11 and INV-12 on Linux and on Windows, with `https` answered by a double. Each fails against code without this item. Values look fake, per the project's sentinel rule.

**Owed by hand before the release that carries it**, added to PRESS-0133, with a real key on a
scratch Google project and a real public channel:

- Each step of § 4.3, read against the console.
- A channel of more than 50 videos: 50 ids in a call is accepted, and the figures match YouTube's
  own page.
- A real channel with hidden subscribers, and a video with comments off: what YouTube actually sends.
- A wrong key, and a key restricted to another API, on the setup screen.
- What a used-up quota actually answers, by lowering the project's quota in the console.

## 8. Alternatives considered (and rejected)

- **The owner's figures by a Google sign-in.** § 3 decision 1.
- **One key built into Pressless.** § 3 decision 3.
- **A panel on the dashboard.** § 2 item 2 would need a second state for every part of that page.
- **The key in Settings, as Firebase's is.** § 3 decision 4.
- **`key=` in the address.** It reaches logs and failure text; the header needs nothing more.
- **`search.list` for the videos.** It costs far more quota, and the uploads playlist gives them all.
- **Reading one page of videos.** YouTube states no order, so "the newest fifty" cannot be promised.

## 9. Out of scope

- The owner's watch time and traffic sources — deferred; not yet queued.
- Spotify, Apple Music, Amazon Music — parked, PRESS-0082, PRESS-0083, PRESS-0084.
- Showing counts on the published site — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_youtube.py::test_settings_round_trip`, `::test_settings_page_keeps_them`, `::test_settings_refuses_a_bad_channel` |
| INV-2 | `tests/test_youtube.py::test_key_only_in_header` |
| INV-3 | `tests/test_youtube.py::test_hostile_title_and_id` |
| INV-4 | `tests/test_youtube.py::test_off_asks_nothing` |
| INV-5 | `tests/test_youtube.py::test_cache_ages` |
| INV-6 | `tests/test_youtube.py::test_cache_is_per_channel` |
| INV-7 | `tests/test_youtube.py::test_walks_pages` |
| INV-8 | `tests/test_youtube.py::test_hidden_is_not_zero` |
| INV-9 | `tests/test_youtube.py::test_failures`, `::test_refused_beats_the_cache` |
| INV-10 | `tests/test_youtube.py::test_parse_channel` |
| INV-11 | `tests/test_youtube.py::test_setup_refused_saves_nothing`, `::test_off_removes_everything` |
| INV-12 | `tests/test_youtube.py::test_site_file_leaves_the_cache_out`, `::test_site_file_renames_the_account` |
| The steps match Google's console | **nothing** — § 7's hand check; the console changes without notice |
| What YouTube sends for hidden numbers and a used-up quota | **nothing** until § 7's hand check; the documents do not settle it |

## 11. Cross-doc impact

- **PRESS-0001 § 4.2:** Settings gains `youtube_channel`, and Credentials `youtube_account`.
- **PRESS-0223 § 4.2:** `SITE_NAMES` gains `youtube.json`.
- **PRESS-0224 § 4.1:** `LEFT_OUT` gains `youtube.json`.
- **`docs/design.md`:** the parts table's Insights row and Credentials' secrets, as PRESS-0079's
  note says each source owes.
- **The Hub:** the privacy policy says what Pressless holds, so it is told at the release; the
  key and figures stay on the writer's computer.
- **`CHANGELOG.md`:** under the release that carries it.
- **PRESS-0133:** § 7's rows.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0081-youtube-public-counts-loop-log.md`.
