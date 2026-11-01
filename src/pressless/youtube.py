"""Insights' second file: a YouTube channel's public counts (PRESS-0081).

It only reads, by a key the writer made, and the key comes in as an argument
(docs/design.md rules 8 and 10). It keeps what YouTube said and works nothing
out from it: YouTube's policies forbid derived figures, and storing statistics
for more than 30 days (§ 3 decisions 6 and 7).
"""
from __future__ import annotations

import dataclasses
import json
import re
import time
import urllib.parse
from pathlib import Path

from pressless import insights
from pressless.insights import DEFAULT_MAX_AGE, InsightsError, Transport, _detail, _own_client
from pressless.safe_write import write_whole

API = "https://www.googleapis.com/youtube/v3/"
CACHE_NAME = "youtube.json"
CACHE_VERSION = 1
MAX_KEPT = 30 * 24 * 3600.0     # YouTube's limit on keeping statistics
_CLOCK_SLIP = 24 * 3600.0       # a kept reply this far ahead has no honest age
PAGE_SIZE = 50                  # the most playlistItems.list gives at once
# Ten pages of ids and ten of figures: 21 of a default 10,000 units a day.
VIDEO_LIMIT = 500

_HANDLE = r"@[^\s/?#&<>\"']{1,100}"
_CHANNEL_ID = r"UC[A-Za-z0-9_-]{22}"
_CHANNEL = re.compile(rf"\A(?:{_HANDLE}|{_CHANNEL_ID})\Z")
_ADDRESS = re.compile(
    rf"\A(?:https?://)?(?:www\.|m\.)?youtube\.com/(?:channel/)?({_HANDLE}|{_CHANNEL_ID})/?\Z")
VIDEO_ID = re.compile(r"\A[A-Za-z0-9_-]+\Z")


class YouTubeError(InsightsError):
    """YouTube answered in a way this part did not expect."""


class Unreachable(YouTubeError):
    """No answer from YouTube."""


class Refused(YouTubeError):
    """YouTube would not take the key."""


class RateLimited(YouTubeError):
    """The day's allowance is used up, or YouTube asked us to slow down."""


class ChannelNotFound(YouTubeError):
    """YouTube knows no such channel."""


@dataclasses.dataclass(frozen=True)
class Video:
    id: str
    title: str
    published: str
    views: int | None        # None where YouTube gives no number
    likes: int | None
    comments: int | None


@dataclasses.dataclass(frozen=True)
class Report:
    channel: str             # the value asked about
    title: str
    subscribers: int | None  # None where hidden
    views: int
    video_count: int
    videos: tuple[Video, ...]   # most viewed first
    fetched_at: float
    stale: bool = False


def parse_channel(text: str) -> str:
    """The stored form of what the writer pasted; ValueError where it names no
    channel. channels.list has no parameter for a /c/ or /user/ address."""
    text = text.strip()
    if _CHANNEL.fullmatch(text):
        return text
    found = _ADDRESS.fullmatch(text)
    if found is None:
        raise ValueError("not a YouTube channel's address")
    return found.group(1)


def check(channel: str, key: str, *, client: Transport | None = None) -> str:
    """The channel's title, or the failure a read would give."""
    return _channel(client if client is not None else _own_client(), channel, key)["title"]


def read(channel: str, key: str, folder: Path, site_folder: Path, *,
         max_age_seconds: float = DEFAULT_MAX_AGE, client: Transport | None = None) -> Report:
    """The channel's figures: from the cache while it is young, else from
    YouTube, else the kept ones marked stale. A refused key and a lost channel
    raise past the cache, as the writer has something to fix."""
    folder = Path(folder)
    if insights._within(folder, Path(site_folder)):
        raise YouTubeError("the cache folder is inside the site folder, which is published "
                           "in full, so the cache may not be kept there")
    now = client.now() if client is not None else time.time()
    held = kept(folder, channel, now)
    if held is not None and 0.0 <= now - held.fetched_at < max_age_seconds:
        return held
    try:
        report = _fetch(client if client is not None else _own_client(), channel, key)
    except (Refused, ChannelNotFound):
        raise
    except InsightsError:
        if held is None:
            raise
        return dataclasses.replace(held, stale=True)
    _store(folder, report)
    return report


def cache_path(folder: Path) -> Path:
    return Path(folder) / CACHE_NAME


def forget(folder: Path) -> None:
    """Remove the cache. A missing file is not a failure; OSError is the Face's."""
    cache_path(folder).unlink(missing_ok=True)


def kept(folder: Path, channel: str, now: float) -> Report | None:
    """The kept report for this channel, or None. One past YouTube's limit, or
    dated well ahead of the clock, is deleted rather than kept any longer."""
    target = cache_path(folder)
    report = _load(target)
    if report is None:
        return None
    if now - report.fetched_at > MAX_KEPT or report.fetched_at - now > _CLOCK_SLIP:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass  # not shown either way; the next look tries again
        return None
    return report if report.channel == channel else None


def _fetch(transport: Transport, channel: str, key: str) -> Report:
    when = transport.now()
    found = _channel(transport, channel, key)
    videos = (_videos(transport, _video_ids(transport, found["uploads"], key), key)
              if found["video_count"] else ())
    return Report(channel, found["title"], found["subscribers"], found["views"],
                  found["video_count"], videos, when)


def _channel(transport: Transport, channel: str, key: str) -> dict:
    by = "forHandle" if channel.startswith("@") else "id"
    answer = _get(transport, "channels", {"part": "snippet,statistics,contentDetails", by: channel},
                  key)
    items = answer.get("items")
    if not isinstance(items, list) or not items:
        raise ChannelNotFound("YouTube knows no such channel")
    try:
        item = items[0]
        statistics = item["statistics"]
        hidden = statistics.get("hiddenSubscriberCount") is True
        views = _count(statistics, "viewCount")
        video_count = _count(statistics, "videoCount")
        found = {"title": str(item["snippet"]["title"]),
                 "subscribers": None if hidden else _count(statistics, "subscriberCount"),
                 "views": views, "video_count": video_count,
                 "uploads": str(item["contentDetails"]["relatedPlaylists"]["uploads"])}
    except (KeyError, TypeError, AttributeError):
        raise YouTubeError("YouTube's answer about the channel has the wrong shape") from None
    if views is None or video_count is None:
        raise YouTubeError("YouTube's answer about the channel carries no figures")
    return found


def _video_ids(transport: Transport, uploads: str, key: str) -> list[str]:
    """Every id it gives, to the limit. The pages are bounded, not the ids
    alone, so an answer of empty pages cannot go on for ever."""
    ids: list[str] = []
    token = None
    for _ in range(VIDEO_LIMIT // PAGE_SIZE):
        query = {"part": "snippet", "maxResults": str(PAGE_SIZE), "playlistId": uploads}
        if token:
            query["pageToken"] = token
        answer = _get(transport, "playlistItems", query, key)
        for item in answer.get("items") or ():
            try:
                ids.append(str(item["snippet"]["resourceId"]["videoId"]))
            except (KeyError, TypeError):
                continue
        token = answer.get("nextPageToken")
        if not token:
            break
    return ids[:VIDEO_LIMIT]


def _videos(transport: Transport, ids: list[str], key: str) -> tuple[Video, ...]:
    videos: list[Video] = []
    for start in range(0, len(ids), PAGE_SIZE):
        query = {"part": "snippet,statistics", "id": ",".join(ids[start:start + PAGE_SIZE])}
        for item in _get(transport, "videos", query, key).get("items") or ():
            try:
                statistics = item.get("statistics") or {}
                videos.append(Video(str(item["id"]), str(item["snippet"]["title"]),
                                    str(item["snippet"].get("publishedAt", "")),
                                    _count(statistics, "viewCount"),
                                    _count(statistics, "likeCount"),
                                    _count(statistics, "commentCount")))
            except (KeyError, TypeError, AttributeError):
                continue
    return tuple(sorted(videos, key=lambda each: (each.views is None, -(each.views or 0))))


def _count(holder: dict, name: str) -> int | None:
    """YouTube sends a count as a string; anything else is no number."""
    value = holder.get(name)
    return int(value) if isinstance(value, str) and value.isascii() and value.isdigit() else None


def _get(transport: Transport, method: str, query: dict[str, str], key: str) -> dict:
    """One call. The key goes in a header, so no address, failure or log can
    carry it. No retry: the cache is what a refusal is answered with."""
    url = API + method + "?" + urllib.parse.urlencode(query)
    headers = {"X-Goog-Api-Key": key, "User-Agent": "Pressless"}
    try:
        status, _, data = transport.request("GET", url, None, headers)
    except OSError as exc:
        # The type and not the message, as insights._fetch: a substituted
        # client's OSError could quote the header it was handed.
        raise Unreachable("no answer from YouTube", type(exc).__name__) from None
    if status != 200:
        raise _failure(status, data)
    try:
        answer = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise YouTubeError("YouTube's answer is not readable") from None
    if not isinstance(answer, dict):
        raise YouTubeError("YouTube's answer has the wrong shape")
    return answer


def _failure(status: int, data: bytes) -> YouTubeError:
    """Reading the body breaks `insights._detail`'s rule on purpose: quota and a
    bad key are both 403s, and they ask different things of the writer. A wrong
    match still shows YouTube's own words."""
    detail = _detail(data)
    if status == 429 or (status == 403 and b"quotaExceeded" in data):
        return RateLimited("YouTube's allowance for the day is used up", detail)
    if status in (400, 401, 403):
        return Refused(f"YouTube refused the key ({status})", detail)
    return YouTubeError(f"YouTube answered {status}", detail)


def _load(target: Path) -> Report | None:
    """A file of another version, or one that does not read, is absent: it is a
    copy of something YouTube can be asked for again."""
    try:
        held = json.loads(target.read_text(encoding="utf-8"))
        if held["version"] != CACHE_VERSION:
            return None
        return Report(str(held["channel"]), str(held["title"]),
                      None if held["subscribers"] is None else int(held["subscribers"]),
                      int(held["views"]), int(held["video_count"]),
                      tuple(Video(**each) for each in held["videos"]),
                      float(held["fetched_at"]))
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return None


def _store(folder: Path, report: Report) -> None:
    """A cache that cannot be written fails nothing: the figures in hand are good."""
    data = dataclasses.asdict(report)
    del data["stale"]
    text = json.dumps({"version": CACHE_VERSION, **data}, indent=2, ensure_ascii=False) + "\n"
    try:
        write_whole(cache_path(folder), text, prefix=".youtube-")
    except OSError:
        return
