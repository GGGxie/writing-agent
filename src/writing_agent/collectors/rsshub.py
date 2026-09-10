from __future__ import annotations

import calendar
import hashlib
from datetime import datetime, timedelta, timezone
from time import sleep
from typing import Any

import feedparser
import httpx

from writing_agent.collectors.config import RssCollectorConfig, RssFeed
from writing_agent.collectors.store import CollectorStore
from writing_agent.models import SignalRecord


def _entry_text(entry: Any) -> str:
    if entry.get("content"):
        return str(entry.content[0].get("value", "")).strip()
    return str(entry.get("summary") or entry.get("description") or "").strip()


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
            cursor = store.get_feed_cursor(feed.id)
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
            try:
                response = client.get(feed.url, headers=headers)
                if response.status_code == 304:
                    store.set_feed_cursor(
                        feed.id,
                        etag=cursor.get("etag"),
                        last_modified=cursor.get("last_modified"),
                    )
                    continue
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
                if parsed.bozo and not parsed.entries:
                    raise ValueError(f"无法解析订阅源：{parsed.bozo_exception}")
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
                store.set_feed_cursor(
                    feed.id,
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )
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
