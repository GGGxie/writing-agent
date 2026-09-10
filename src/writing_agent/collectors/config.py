from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from writing_agent.config import get_settings
from writing_agent.models import SourceTier


@dataclass(frozen=True)
class XRule:
    tag: str
    value: str


@dataclass(frozen=True)
class XCollectorConfig:
    enabled: bool = False
    sync_rules: bool = False
    managed_tag_prefix: str = "wechat-source:"
    tags: list[str] = field(default_factory=lambda: ["X"])
    rules: list[XRule] = field(default_factory=list)


@dataclass(frozen=True)
class RssFeed:
    id: str
    name: str
    url: str
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    source_tier: SourceTier = SourceTier.C


@dataclass(frozen=True)
class RssCollectorConfig:
    enabled: bool = True
    poll_interval_seconds: int = 300
    request_timeout_seconds: float = 20
    max_items_per_feed: int = 20
    max_item_age_hours: int | None = 168
    feeds: list[RssFeed] = field(default_factory=list)


@dataclass(frozen=True)
class CollectorConfig:
    max_seen_items: int
    x: XCollectorConfig
    rsshub: RssCollectorConfig


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是对象")
    return value


def load_collector_config(path: Path | None = None) -> CollectorConfig:
    config_path = path or get_settings().sources_config_path
    if not config_path.exists():
        raise FileNotFoundError(
            f"找不到 {config_path}；请复制 config/sources.example.yaml 为 config/sources.yaml"
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    root = _mapping(raw, "配置")
    x_raw = _mapping(root.get("x"), "x")
    rss_raw = _mapping(root.get("rsshub"), "rsshub")

    rules = [
        XRule(tag=str(item["tag"]).strip(), value=str(item["value"]).strip())
        for item in x_raw.get("rules", [])
    ]
    if len({rule.tag for rule in rules}) != len(rules):
        raise ValueError("X 规则 tag 不能重复")

    feeds: list[RssFeed] = []
    for item in rss_raw.get("feeds", []):
        tier_value = str(item.get("source_tier", "C"))
        try:
            tier = SourceTier(tier_value)
        except ValueError as exc:
            raise ValueError(f"RSS 源 {item.get('id')} 的 source_tier 无效") from exc
        feeds.append(
            RssFeed(
                id=str(item["id"]).strip(),
                name=str(item["name"]).strip(),
                url=str(item["url"]).strip(),
                enabled=bool(item.get("enabled", True)),
                tags=[str(value).strip() for value in item.get("tags", []) if str(value).strip()],
                source_tier=tier,
            )
        )
    if len({feed.id for feed in feeds}) != len(feeds):
        raise ValueError("RSS 源 id 不能重复")

    max_age = rss_raw.get("max_item_age_hours", 168)
    return CollectorConfig(
        max_seen_items=int(root.get("max_seen_items", 50_000)),
        x=XCollectorConfig(
            enabled=bool(x_raw.get("enabled", False)),
            sync_rules=bool(x_raw.get("sync_rules", False)),
            managed_tag_prefix=str(x_raw.get("managed_tag_prefix", "wechat-source:")),
            tags=[str(value).strip() for value in x_raw.get("tags", ["X"])],
            rules=rules,
        ),
        rsshub=RssCollectorConfig(
            enabled=bool(rss_raw.get("enabled", True)),
            poll_interval_seconds=int(rss_raw.get("poll_interval_seconds", 300)),
            request_timeout_seconds=float(rss_raw.get("request_timeout_seconds", 20)),
            max_items_per_feed=int(rss_raw.get("max_items_per_feed", 20)),
            max_item_age_hours=None if max_age is None else int(max_age),
            feeds=feeds,
        ),
    )
