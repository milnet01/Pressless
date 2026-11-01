# A YouTube channel's public counts (PRESS-0081).
#
# Each test names the invariant it holds, from
# docs/specs/PRESS-0081-youtube-public-counts.md § 5. YouTube is a double, so no
# test reaches the network.
from __future__ import annotations

import contextlib
import dataclasses
import html
import json
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from _face_session import Browser
from test_setup import _answers, _GitHub, _saved, _setup_page
from test_setup import _Store as _SetupStore

from pressless import credentials, face, https, settings, sitefile, sites, youtube, youtube_screen
from pressless.words import say

KEY = "sentinel-youtube-key-for-tests"
OTHER_KEY = "another-sentinel-key-for-tests"
HANDLE = "@sentinelchannel"
NOW = 2_000_000_000.0
HOUR = 3600.0


class _YouTube:
    """Answers the three methods by name, and records each call. `videos` is how
    many the channel has; a status or an OSError stands in for any failure."""

    def __init__(self, videos: int = 3, *, status: int = 200, body: bytes = b"{}",
                 raises: bool = False, statistics: dict | None = None,
                 items: list | None = None, video_item=None) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.count = videos
        self.status = status
        self.body = body
        self.raises = raises
        self.statistics = statistics
        self.items = items
        self.video_item = video_item
        self.clock = NOW

    def now(self) -> float:
        return self.clock

    def request(self, method: str, url: str, body: bytes | None,
                headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((url, headers))
        if self.raises:
            raise OSError(f"no route, holding {headers['X-Goog-Api-Key']}")
        if self.status != 200:
            return self.status, {}, self.body
        name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[1]
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        return 200, {}, json.dumps(getattr(self, "_" + name)(query)).encode("utf-8")

    def _channels(self, query: dict[str, str]) -> dict:
        if self.items is not None:
            return {"items": self.items}
        statistics = self.statistics if self.statistics is not None else {
            "viewCount": "9000", "subscriberCount": "1230", "videoCount": str(self.count)}
        return {"items": [{"snippet": {"title": "A <b>Channel</b>"}, "statistics": statistics,
                           "contentDetails": {"relatedPlaylists": {"uploads": "UUplaylist"}}}]}

    def _playlistItems(self, query: dict[str, str]) -> dict:
        start = int(query.get("pageToken", "0"))
        stop = min(start + int(query["maxResults"]), self.count)
        answer: dict = {"items": [{"snippet": {"resourceId": {"videoId": f"video{at}"}}}
                                  for at in range(start, stop)]}
        if stop < self.count:
            answer["nextPageToken"] = str(stop)
        return answer

    def _videos(self, query: dict[str, str]) -> dict:
        ids = query["id"].split(",")
        return {"items": [self._video(each) for each in ids if each != "video1"]}

    def _video(self, each: str) -> dict:
        if self.video_item is not None:
            return self.video_item
        return {"id": each, "snippet": {"title": f"Title {each}",
                                        "publishedAt": "2026-01-02T03:04:05Z"},
                "statistics": {"viewCount": each[5:] + "0", "likeCount": "2", "commentCount": "1"}}


def _fresh(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


def _read(folder: Path, client: _YouTube, **changes) -> youtube.Report:
    return youtube.read(HANDLE, KEY, folder, folder / "site", client=client, **changes)


class _Keys:
    """Recording doubles for credentials.read, write and delete."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, delete_fails: bool = False) -> None:
        self.held: dict[str, str] = {}
        self.deleted: list[str] = []

        def read(store: str, folder: Path, account: str) -> str:
            if account not in self.held:
                raise credentials.NotStored(account)
            return self.held[account]

        def write(store: str, folder: Path, account: str, secret: str) -> None:
            self.held[account] = secret

        def delete(store: str, folder: Path, account: str) -> None:
            self.deleted.append(account)
            self.held.pop(account, None)
            if delete_fails:
                raise credentials.CredentialError("the store could not remove that secret")

        monkeypatch.setattr(credentials, "read", read)
        monkeypatch.setattr(credentials, "write", write)
        monkeypatch.setattr(credentials, "delete", delete)


@contextlib.contextmanager
def _screen(folder: Path, client: _YouTube) -> Iterator[Browser]:
    served = face.serve(folder)
    try:
        youtube_screen.register(served, folder, client=client)
        yield Browser(served)
    finally:
        served.stop()


def _on(folder: Path, keys: _Keys, channel: str = HANDLE) -> settings.Settings:
    keys.held["youtube"] = KEY
    plain = _saved(folder)
    return_value = dataclasses.replace(
        plain, youtube_channel=channel,
        credentials=dataclasses.replace(plain.credentials, youtube_account="youtube"))
    settings.save(folder, return_value)
    return return_value


# ------------------------------------------------------------------ INV-1 ---


def test_settings_round_trip(tmp_path: Path) -> None:
    """INV-1. Breaks when a field is dropped on save, or absent stops loading as None."""
    plain = _saved(tmp_path)
    written = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    del written["youtube_channel"]
    del written["credentials"]["youtube_account"]
    (tmp_path / "settings.json").write_text(json.dumps(written), encoding="utf-8")
    loaded = settings.load(tmp_path)
    assert loaded.youtube_channel is None and loaded.credentials.youtube_account is None

    held = dataclasses.replace(
        plain, youtube_channel=HANDLE,
        credentials=dataclasses.replace(plain.credentials, youtube_account="youtube"))
    settings.save(tmp_path, held)
    assert settings.load(tmp_path) == held


def test_settings_page_keeps_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-1. Breaks when setup's candidate omits a field: it names each one."""
    _SetupStore(monkeypatch)
    plain = _saved(tmp_path)
    settings.save(tmp_path, dataclasses.replace(
        plain, youtube_channel=HANDLE,
        credentials=dataclasses.replace(plain.credentials, youtube_account="youtube")))
    with _setup_page(tmp_path, _GitHub()) as browser:
        status, page = browser.post(_answers(key=""))
    assert status == 200, page
    kept = settings.load(tmp_path)
    assert kept.youtube_channel == HANDLE and kept.credentials.youtube_account == "youtube"


@pytest.mark.parametrize("channel", [
    "no-at-sign", '@quo"te', "@with space", "@a/b", "@<b>", "UCshort", "@" + "x" * 101, "",
])
def test_settings_refuses_a_bad_channel(tmp_path: Path, channel: str) -> None:
    """INV-1. Breaks when `check` lets one through, or names another key."""
    plain = _saved(tmp_path)
    with pytest.raises(settings.SettingsError) as refused:
        settings.check(dataclasses.replace(plain, youtube_channel=channel))
    assert refused.value.key == "youtube_channel"


# ------------------------------------------------------------------ INV-2 ---


def test_key_only_in_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-2. Breaks when the key goes in `key=`, or a failure quotes the request."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    client = _YouTube()
    with _screen(folder, client) as browser:
        pages = [browser.request("GET", "/youtube")[2], browser.request("GET", "/youtube/setup")[2]]
    assert client.calls
    for url, headers in client.calls:
        assert headers["X-Goog-Api-Key"] == KEY
        assert KEY not in url
    for path in folder.rglob("*"):
        if path.is_file():
            assert KEY not in path.read_text(encoding="utf-8", errors="replace"), path
    assert not any(KEY in page for page in pages)

    for broken in (_YouTube(status=400, body=b"bad"), _YouTube(status=403, body=b"no"),
                   _YouTube(status=500), _YouTube(raises=True)):
        youtube.forget(folder)
        with pytest.raises(youtube.YouTubeError) as failed:
            _read(folder, broken)
        assert KEY not in str(failed.value) and KEY not in repr(failed.value.detail)
        assert failed.value.__cause__ is None


def test_a_redirect_to_another_origin_drops_the_key() -> None:
    """INV-2. Breaks when only Authorization is removed: urllib copies every other
    header onto a redirect's target, a different host included."""
    asked = urllib.request.Request("https://www.googleapis.com/youtube/v3/channels",
                                   headers={"X-Goog-Api-Key": KEY})
    handler = https.NoCrossOriginAuth()
    across = handler.redirect_request(asked, None, 302, "Found", {}, "https://example.org/")
    assert not across.has_header("X-goog-api-key")
    same = handler.redirect_request(asked, None, 302, "Found", {},
                                    "https://www.googleapis.com/elsewhere")
    assert same.has_header("X-goog-api-key")


# ------------------------------------------------------------------ INV-3 ---


def test_hostile_title_and_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-3. Breaks when a title goes unescaped, or an id is joined unchecked."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    hostile = {"id": 'x"><script>bad()</script>',
               "snippet": {"title": "<script>worse()</script>",
                           "publishedAt": "<i>then</i>"},
               "statistics": {"viewCount": "5"}}
    with _screen(folder, _YouTube(1 + 0, video_item=hostile)) as browser:
        page = browser.request("GET", "/youtube")[2]
    assert "A &lt;b&gt;Channel&lt;/b&gt;" in page and "<b>Channel" not in page
    assert "&lt;script&gt;worse()" in page and "<script>worse" not in page
    assert "<i>then" not in page
    assert "watch?v=" not in page, "an id outside the pattern gets no link"


def test_a_good_id_gets_a_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-3's other side: the check above must not pass by showing no videos."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    with _screen(folder, _YouTube()) as browser:
        page = browser.request("GET", "/youtube")[2]
    assert 'href="https://www.youtube.com/watch?v=video2"' in page


# ------------------------------------------------------------------ INV-4 ---


def test_off_asks_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-4. Breaks when the card calls read, or one setting alone turns it on."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    plain = _saved(folder)
    client = _YouTube()
    half = (plain,
            dataclasses.replace(plain, youtube_channel=HANDLE),
            dataclasses.replace(plain, credentials=dataclasses.replace(
                plain.credentials, youtube_account="youtube")))
    keys.held["youtube"] = KEY
    for each in half:
        settings.save(folder, each)
        with _screen(folder, client) as browser:
            page = browser.request("GET", "/youtube")[2]
            card = "".join(browser.served.list_pieces(above=True))
        assert "/youtube/setup" in page
        assert card == ""
    assert client.calls == []


def test_the_card_never_asks_youtube(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-4. Set up, with nothing kept: the list says to look, and asks nothing."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    client = _YouTube()
    with _screen(folder, client) as browser:
        card = "".join(browser.served.list_pieces(above=True))
    assert 'href="/youtube"' in card and client.calls == []


# ------------------------------------------------------------------ INV-5 ---


@pytest.mark.parametrize(("age", "shown", "stale"), [
    (HOUR - 1, True, False),
    (HOUR + 1, True, True),
    (youtube.MAX_KEPT - 1, True, True),
    (youtube.MAX_KEPT + 1, False, False),
])
def test_cache_ages_when_youtube_cannot_be_asked(tmp_path: Path, age: float, shown: bool,
                                                 stale: bool) -> None:
    """INV-5. Breaks when read falls back on the raw file, past YouTube's limit."""
    folder = _fresh(tmp_path)
    _read(folder, _YouTube())
    away = _YouTube(raises=True)
    away.clock = NOW + age
    if shown:
        assert _read(folder, away).stale is stale
    else:
        with pytest.raises(youtube.Unreachable):
            _read(folder, away)
        assert not youtube.cache_path(folder).exists(), "past the limit it is deleted"


def test_cache_ages(tmp_path: Path) -> None:
    """INV-5. Under the hour asks nothing; over it asks again; ahead of the clock
    by more than a day is deleted and asks; a little ahead asks and is replaced."""
    folder = _fresh(tmp_path)
    _read(folder, _YouTube())
    young = _YouTube()
    young.clock = NOW + HOUR - 1
    _read(folder, young)
    assert young.calls == []

    older = _YouTube()
    older.clock = NOW + HOUR + 1
    assert _read(folder, older).fetched_at == older.clock and older.calls

    behind = _YouTube()
    behind.clock = older.clock - 60
    _read(folder, behind)
    assert behind.calls, "a negative age is not a fresh cache"

    assert youtube.kept(folder, HANDLE, behind.clock - 2 * 24 * HOUR) is None
    assert not youtube.cache_path(folder).exists()


# ------------------------------------------------------------------ INV-6 ---


def test_cache_is_per_channel(tmp_path: Path) -> None:
    """INV-6. Breaks when kept does not compare the channel."""
    folder = _fresh(tmp_path)
    _read(folder, _YouTube())
    assert youtube.kept(folder, HANDLE, NOW) is not None
    assert youtube.kept(folder, "@another", NOW) is None
    other = _YouTube()
    youtube.read("@another", KEY, folder, folder / "site", client=other)
    assert other.calls


def test_cache_inside_the_site_folder_is_refused(tmp_path: Path) -> None:
    """§ 4.2. The site folder is published in full."""
    client = _YouTube()
    with pytest.raises(youtube.YouTubeError):
        youtube.read(HANDLE, KEY, tmp_path / "site" / "x", tmp_path / "site", client=client)
    assert client.calls == []


@pytest.mark.parametrize("text", ["not json", '{"version": 99}', '{"version": 1}', "[]"])
def test_an_unreadable_cache_reads_as_absent(tmp_path: Path, text: str) -> None:
    folder = _fresh(tmp_path)
    youtube.cache_path(folder).write_text(text, encoding="utf-8")
    assert youtube.kept(folder, HANDLE, NOW) is None


# ------------------------------------------------------------------ INV-7 ---


def test_walks_pages(tmp_path: Path) -> None:
    """INV-7. Breaks when nextPageToken is ignored: the first page alone is fifty."""
    folder = _fresh(tmp_path)
    client = _YouTube(120)
    report = _read(folder, client)
    assert len(report.videos) == 119, "video1 is one YouTube omits"
    assert "video119" in {video.id for video in report.videos}
    assert "video1" not in {video.id for video in report.videos}
    for url, _ in client.calls:
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        if "/videos" in url:
            assert len(query["id"].split(",")) <= youtube.PAGE_SIZE
    assert [video.views for video in report.videos[:2]] == [1190, 1180]


def test_stops_at_the_limit(tmp_path: Path) -> None:
    """INV-7. Breaks when the walk has no bound."""
    client = _YouTube(youtube.VIDEO_LIMIT + 200)
    report = _read(_fresh(tmp_path), client)
    assert len(report.videos) == youtube.VIDEO_LIMIT - 1
    pages = [url for url, _ in client.calls if "playlistItems" in url]
    assert len(pages) == youtube.VIDEO_LIMIT // youtube.PAGE_SIZE


def test_a_missing_view_count_sorts_last(tmp_path: Path) -> None:
    """INV-7. Breaks when a None reaches the sort as a number."""
    client = _YouTube(3)
    plain = client._video
    client._video = lambda each: ({**plain(each), "statistics": {}} if each == "video0"
                                  else plain(each))
    report = _read(_fresh(tmp_path), client)
    assert report.videos[-1].id == "video0" and report.videos[-1].views is None


def test_an_empty_channel_asks_for_no_videos(tmp_path: Path) -> None:
    client = _YouTube(0)
    assert _read(_fresh(tmp_path), client).videos == ()
    assert len(client.calls) == 1


# ------------------------------------------------------------------ INV-8 ---


def test_hidden_is_not_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-8. Breaks when a missing number defaults to 0."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    bare = {"id": "video0", "snippet": {"title": "Quiet", "publishedAt": "2026-01-02"},
            "statistics": {"viewCount": "7"}}
    client = _YouTube(1, statistics={"viewCount": "9", "videoCount": "1", "subscriberCount": "0",
                                     "hiddenSubscriberCount": True}, video_item=bare)
    report = _read(folder, client)
    assert report.subscribers is None
    assert report.videos[0].likes is None and report.videos[0].comments is None
    youtube.forget(folder)
    with _screen(folder, client) as browser:
        page = browser.request("GET", "/youtube")[2]
    assert page.count('>hidden</td>') == 3


def test_a_shown_zero_stays_zero(tmp_path: Path) -> None:
    """INV-8's other side: a real 0 is not hidden."""
    client = _YouTube(1, statistics={"viewCount": "0", "videoCount": "1", "subscriberCount": "0"},
                      video_item={"id": "video0", "snippet": {"title": "T"},
                                  "statistics": {"viewCount": "0", "likeCount": "0",
                                                 "commentCount": "0"}})
    report = _read(_fresh(tmp_path), client)
    assert report.subscribers == 0 and report.videos[0].likes == 0


# ------------------------------------------------------------------ INV-9 ---


@pytest.mark.parametrize(("client", "kind"), [
    (_YouTube(status=400, body=b"API_KEY_INVALID"), youtube.Refused),
    (_YouTube(status=403, body=b"forbidden"), youtube.Refused),
    (_YouTube(status=403, body=b'"reason": "quotaExceeded"'), youtube.RateLimited),
    (_YouTube(status=429), youtube.RateLimited),
    (_YouTube(status=500), youtube.YouTubeError),
    (_YouTube(raises=True), youtube.Unreachable),
    (_YouTube(items=[]), youtube.ChannelNotFound),
    (_YouTube(items=[{"snippet": {}}]), youtube.YouTubeError),
    (_YouTube(statistics={"videoCount": "1"}), youtube.YouTubeError),
])
def test_failures(tmp_path: Path, client: _YouTube, kind: type) -> None:
    """INV-9. Breaks when quota reads as a bad key, or a bad shape reads as a good one."""
    with pytest.raises(youtube.YouTubeError) as failed:
        _read(_fresh(tmp_path), client)
    assert type(failed.value) is kind


@pytest.mark.parametrize("broken", [_YouTube(status=403, body=b"no"), _YouTube(items=[])])
def test_refused_beats_the_cache(tmp_path: Path, broken: _YouTube) -> None:
    """INV-9. Breaks when a dead key hides behind old figures."""
    folder = _fresh(tmp_path)
    _read(folder, _YouTube())
    broken.clock = NOW + 2 * HOUR
    with pytest.raises((youtube.Refused, youtube.ChannelNotFound)):
        _read(folder, broken)


@pytest.mark.parametrize("broken", [_YouTube(status=403, body=b"quotaExceeded"),
                                    _YouTube(status=500), _YouTube(raises=True)])
def test_other_failures_show_the_kept_figures(tmp_path: Path, broken: _YouTube) -> None:
    folder = _fresh(tmp_path)
    _read(folder, _YouTube())
    broken.clock = NOW + 2 * HOUR
    assert _read(folder, broken).stale is True


@pytest.mark.parametrize("failure", [
    youtube.YouTubeError, youtube.Unreachable, youtube.Refused, youtube.RateLimited,
    youtube.ChannelNotFound])
def test_each_failure_has_its_own_words(failure: type) -> None:
    """INV-9. Breaks when a class has no sentence: sentence_for calls it unforeseen."""
    sentence = face.sentence_for(failure("x"), publishing=False)
    assert "YouTube" in sentence.what or "key" in sentence.what


def test_a_refusal_links_the_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    with _screen(folder, _YouTube(status=403, body=b"no")) as browser:
        page = browser.request("GET", "/youtube")[2]
    assert "YouTube would not take your key" in page and 'href="/youtube/setup"' in page


def test_no_key_held_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    del keys.held["youtube"]
    client = _YouTube()
    with _screen(folder, client) as browser:
        page = browser.request("GET", "/youtube")[2]
    assert "your YouTube key" in page and client.calls == []


# ----------------------------------------------------------------- INV-10 ---


@pytest.mark.parametrize(("text", "stored"), [
    ("@name", "@name"),
    ("  @name \n", "@name"),
    ("@naïve.name-1", "@naïve.name-1"),
    ("UC" + "a" * 22, "UC" + "a" * 22),
    ("youtube.com/@name", "@name"),
    ("www.youtube.com/@name/", "@name"),
    ("https://www.youtube.com/@name", "@name"),
    ("http://m.youtube.com/@name", "@name"),
    ("https://youtube.com/channel/UC" + "b" * 22, "UC" + "b" * 22),
])
def test_parse_channel(text: str, stored: str) -> None:
    """INV-10, and each result passes Settings' own check."""
    assert youtube.parse_channel(text) == stored
    assert settings._YOUTUBE_CHANNEL.fullmatch(stored)


@pytest.mark.parametrize("text", [
    "", "name", "https://www.youtube.com/c/name", "https://www.youtube.com/user/name",
    "https://evil.example/youtube.com/@name", "https://youtube.com.evil.example/@name",
    "https://www.youtube.com/@name/videos", "https://www.youtube.com/watch?v=abc",
    "@<script>", '@a"b', "UCshort",
])
def test_parse_channel_refuses(text: str) -> None:
    """INV-10. Breaks when it searches for youtube.com anywhere in the text."""
    with pytest.raises(ValueError):
        youtube.parse_channel(text)


# ----------------------------------------------------------------- INV-11 ---


@pytest.mark.parametrize(("form", "client", "hint"), [
    ({"channel": "nonsense", "key": KEY}, _YouTube(), "youtube.hint.channel"),
    ({"channel": HANDLE, "key": ""}, _YouTube(), "youtube.hint.key"),
    ({"channel": HANDLE, "key": KEY}, _YouTube(status=400, body=b"API_KEY_INVALID"),
     "youtube.hint.refused"),
    ({"channel": HANDLE, "key": KEY}, _YouTube(items=[]), "youtube.hint.not_found"),
    ({"channel": HANDLE, "key": KEY}, _YouTube(raises=True), "youtube.hint.unreachable"),
])
def test_setup_refused_saves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                     form: dict[str, str], client: _YouTube, hint: str) -> None:
    """INV-11. Breaks when the key is written before the check."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _saved(folder)
    with _screen(folder, client) as browser:
        status, _, page = browser.request("POST", "/youtube/setup", form)
    assert status == 200 and html.escape(say(hint)) in page
    assert keys.held == {}
    assert settings.load(folder).youtube_channel is None


def test_setup_saves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-11's other side, and an empty box keeps the key on a later save."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _saved(folder)
    client = _YouTube()
    with _screen(folder, client) as browser:
        page = browser.request("POST", "/youtube/setup",
                               {"channel": "https://www.youtube.com/@name", "key": KEY})[2]
        assert "A &lt;b&gt;Channel" in page
        saved = settings.load(folder)
        assert saved.youtube_channel == "@name" and keys.held == {"youtube": KEY}
        assert saved.credentials.youtube_account == "youtube"

        _read(folder, client)
        browser.request("POST", "/youtube/setup", {"channel": "@another", "key": ""})
    assert keys.held == {"youtube": KEY}
    assert settings.load(folder).youtube_channel == "@another"
    assert not youtube.cache_path(folder).exists(), "a changed channel forgets the old figures"


def test_off_removes_everything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-11. Breaks when a removal is skipped, or one setting stays."""
    keys = _Keys(monkeypatch)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    _read(folder, _YouTube())
    with _screen(folder, _YouTube()) as browser:
        page = browser.request("POST", "/youtube/off")[2]
    saved = settings.load(folder)
    assert saved.youtube_channel is None and saved.credentials.youtube_account is None
    assert keys.held == {} and not youtube.cache_path(folder).exists()
    assert "could not remove" not in page


def test_off_says_what_remains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-11. Breaks when a failed delete stops the save, or goes unsaid."""
    keys = _Keys(monkeypatch, delete_fails=True)
    folder = _fresh(tmp_path)
    _on(folder, keys)
    with _screen(folder, _YouTube()) as browser:
        page = browser.request("POST", "/youtube/off")[2]
    assert settings.load(folder).youtube_channel is None
    assert "could not remove" in page


# ----------------------------------------------------------------- INV-12 ---


def test_site_file_leaves_the_cache_out(tmp_path: Path) -> None:
    """INV-12. Breaks when LEFT_OUT or SITE_NAMES omit it."""
    assert youtube.CACHE_NAME in sites.SITE_NAMES
    assert youtube.CACHE_NAME in sitefile.LEFT_OUT
    assert youtube.CACHE_NAME not in sitefile.KEPT


def test_site_file_renames_the_account(tmp_path: Path) -> None:
    """INV-12. Breaks when sitefile's rewrite omits youtube_account: the second
    site would read the first site's key."""
    own = tmp_path / "from"
    own.mkdir()
    site = sites.open_site(own)
    plain = _saved(site)
    settings.save(site, dataclasses.replace(
        plain, youtube_channel=HANDLE,
        credentials=dataclasses.replace(plain.credentials, youtube_account="youtube")))
    target = tmp_path / "saved.zip"
    sitefile.save(site, target)
    other = sitefile.open_into(target, own)
    loaded = settings.load(other)
    assert loaded.youtube_channel == HANDLE
    assert loaded.credentials.youtube_account == sites.account("youtube", other)
    assert loaded.credentials.youtube_account != "youtube"
