from __future__ import annotations

import calendar
import hashlib
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from time import sleep
from typing import Any

import feedparser
import httpx

from writing_agent.collectors import rsshub_instances
from writing_agent.collectors.config import RssCollectorConfig, RssFeed
from writing_agent.collectors.store import CollectorStore
from writing_agent.models import SignalRecord

_MAX_AUTO_INSTANCE_CANDIDATES = 5
_CACHED_INSTANCE_TTL = timedelta(hours=1)


class _HtmlToTextParser(HTMLParser):
    """把 RSSHub 常见的渲染用 HTML（如 Twitter 路由的 <br>/<img>/<video>/<blockquote>）
    转成纯文本，同时保留段落换行。RSS 阅读器会渲染这些标签，但我们把 content
    当作纯文本摘要使用（存库、写 Markdown、前端卡片展示、"基于此线索创作"预填），
    不做 HTML 渲染，所以要在采集时就转换一次，而不是让原始标签流到下游。"""

    _BREAK_TAGS = {"br", "p", "div", "li", "blockquote", "hr", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BREAK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in self._BREAK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BREAK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        lines = ("".join(self._parts)).splitlines()
        cleaned = [" ".join(line.split()) for line in lines]
        return "\n".join(line for line in cleaned if line).strip()


def _html_to_text(value: str) -> str:
    if "<" not in value:
        return value.strip()
    parser = _HtmlToTextParser()
    parser.feed(value)
    parser.close()
    return parser.get_text()


def _entry_text(entry: Any) -> str:
    if entry.get("content"):
        raw = str(entry.content[0].get("value", ""))
    else:
        raw = str(entry.get("summary") or entry.get("description") or "")
    return _html_to_text(raw)


def _published_at(entry: Any) -> datetime | None:
    value = entry.get("published_parsed") or entry.get("updated_parsed")
    if not value:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)


def _to_signal(feed: RssFeed, entry: Any, now: datetime) -> SignalRecord:
    url = str(entry.get("link") or feed.url)
    title = str(entry.get("title") or "未命名 RSS 条目").strip()
    content = _entry_text(entry)
    source_id = str(
        entry.get("id")
        or entry.get("guid")
        or url
        or hashlib.sha256(f"{title}\0{content}".encode()).hexdigest()
    )
    author = str(entry.get("author") or "").strip() or None
    return SignalRecord(
        source_type="rsshub",
        source_id=f"{feed.id}:{source_id}",
        source_name=feed.name,
        title=title,
        content=content,
        url=url,
        discovered_at=now,
        published_at=_published_at(entry),
        author=author,
        tags=list(dict.fromkeys(["RSSHub", *feed.tags])),
        source_tier=feed.source_tier,
        metadata={"feed_id": feed.id, "feed_url": feed.url},
    )


def _conditional_headers(cursor: dict[str, str]) -> dict[str, str]:
    headers = {
        "Accept": (
            "application/atom+xml, application/rss+xml, application/xml, "
            "text/xml;q=0.9, */*;q=0.1"
        ),
        "User-Agent": "writing-agent/0.2",
    }
    if cursor.get("etag"):
        headers["If-None-Match"] = cursor["etag"]
    if cursor.get("last_modified"):
        headers["If-Modified-Since"] = cursor["last_modified"]
    return headers


def _fetch_and_parse(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
) -> tuple[Any | None, httpx.Response]:
    """获取并解析订阅源；返回 (None, response) 表示 304 未变化。"""
    response = client.get(url, headers=headers)
    if response.status_code == 304:
        return None, response
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"无法解析订阅源：{parsed.bozo_exception}")
    return parsed, response


def _process_entries(
    feed: RssFeed,
    parsed: Any,
    config: RssCollectorConfig,
    store: CollectorStore,
    now: datetime,
    summary: dict[str, int],
) -> None:
    entries = parsed.entries[: config.max_items_per_feed]
    summary["fetched"] += len(entries)
    for entry in entries:
        signal = _to_signal(feed, entry, now)
        if (
            config.max_item_age_hours is not None
            and signal.published_at is not None
            and signal.published_at < now - timedelta(hours=config.max_item_age_hours)
        ):
            summary["skipped_old"] += 1
            continue
        if store.save_signal(signal):
            summary["saved"] += 1
        else:
            summary["duplicates"] += 1


def _candidate_base_urls(feed: RssFeed, store: CollectorStore, client: httpx.Client) -> list[str]:
    cached = store.get_feed_instance(feed.id)
    ordered: list[str] = []
    resolved_at_raw = cached.get("resolved_at")
    if cached.get("base_url") and resolved_at_raw:
        try:
            resolved_at = datetime.fromisoformat(resolved_at_raw)
        except ValueError:
            resolved_at = None
        age = None if resolved_at is None else datetime.now(timezone.utc) - resolved_at
        if age is not None and age < _CACHED_INSTANCE_TTL:
            ordered.append(cached["base_url"])
    for base_url in rsshub_instances.fetch_instance_candidates(client):
        if base_url not in ordered:
            ordered.append(base_url)
    return ordered


def _collect_feed_fixed_url(
    feed: RssFeed,
    config: RssCollectorConfig,
    store: CollectorStore,
    client: httpx.Client,
    now: datetime,
    summary: dict[str, int],
) -> None:
    cursor = store.get_feed_cursor(feed.id)
    headers = _conditional_headers(cursor)
    parsed, response = _fetch_and_parse(client, feed.url, headers)
    if parsed is None:
        store.set_feed_cursor(
            feed.id, etag=cursor.get("etag"), last_modified=cursor.get("last_modified")
        )
        return
    _process_entries(feed, parsed, config, store, now, summary)
    store.set_feed_cursor(
        feed.id,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )


def _collect_feed_auto_instance(
    feed: RssFeed,
    config: RssCollectorConfig,
    store: CollectorStore,
    client: httpx.Client,
    now: datetime,
    summary: dict[str, int],
) -> None:
    cursor = store.get_feed_cursor(feed.id)
    headers = _conditional_headers(cursor)
    candidates = _candidate_base_urls(feed, store, client)[:_MAX_AUTO_INSTANCE_CANDIDATES]
    last_error: Exception | None = None
    for base_url in candidates:
        full_url = base_url.rstrip("/") + feed.url
        try:
            parsed, response = _fetch_and_parse(client, full_url, headers)
        except Exception as exc:
            last_error = exc
            continue
        store.set_feed_instance(feed.id, base_url)
        if parsed is None:
            store.set_feed_cursor(
                feed.id, etag=cursor.get("etag"), last_modified=cursor.get("last_modified")
            )
            return
        _process_entries(feed, parsed, config, store, now, summary)
        store.set_feed_cursor(
            feed.id,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )
        return
    raise RuntimeError(f"尝试了 {len(candidates)} 个公共实例均失败：{last_error}")


def collect_rss_once(
    config: RssCollectorConfig,
    store: CollectorStore,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    summary = {"fetched": 0, "saved": 0, "duplicates": 0, "skipped_old": 0, "failed_feeds": 0}
    own_client = client is None
    client = client or httpx.Client(timeout=config.request_timeout_seconds, follow_redirects=True)
    now = datetime.now(timezone.utc)
    try:
        for feed in (item for item in config.feeds if item.enabled):
            try:
                if feed.auto_instance:
                    _collect_feed_auto_instance(feed, config, store, client, now, summary)
                else:
                    _collect_feed_fixed_url(feed, config, store, client, now, summary)
            except Exception as exc:
                summary["failed_feeds"] += 1
                print(f"[RSSHub] {feed.name} 采集失败：{exc}")
    finally:
        if own_client:
            client.close()
    return summary


def watch_rss(config: RssCollectorConfig, store: CollectorStore) -> None:
    while True:
        result = collect_rss_once(config, store)
        print(f"[RSSHub] {result}")
        sleep(config.poll_interval_seconds)
