from __future__ import annotations

import json
from datetime import datetime, timezone
from time import sleep
from typing import Any

import httpx

from writing_agent.collectors.config import XCollectorConfig
from writing_agent.collectors.store import CollectorStore
from writing_agent.config import get_settings
from writing_agent.models import SignalRecord, SourceTier

X_STREAM_URL = "https://api.x.com/2/tweets/search/stream"
X_RULES_URL = f"{X_STREAM_URL}/rules"


def _headers() -> dict[str, str]:
    token = get_settings().x_bearer_token.strip()
    if not token:
        raise RuntimeError("X_BEARER_TOKEN 未设置")
    return {"Authorization": f"Bearer {token}", "User-Agent": "writing-agent/0.2"}


def _all_rules(client: httpx.Client) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        params = {"max_results": "1000"}
        if token:
            params["pagination_token"] = token
        response = client.get(X_RULES_URL, headers=_headers(), params=params)
        response.raise_for_status()
        payload = response.json()
        rules.extend(payload.get("data", []))
        token = payload.get("meta", {}).get("next_token")
        if not token:
            return rules


def sync_x_rules(config: XCollectorConfig, client: httpx.Client | None = None) -> dict[str, int]:
    own_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        existing = _all_rules(client)
        managed = [
            rule
            for rule in existing
            if str(rule.get("tag", "")).startswith(config.managed_tag_prefix)
        ]
        desired = [
            {"value": rule.value, "tag": f"{config.managed_tag_prefix}{rule.tag}"}
            for rule in config.rules
        ]
        desired_by_tag = {rule["tag"]: rule for rule in desired}
        delete_ids = [
            str(rule["id"])
            for rule in managed
            if rule.get("tag") not in desired_by_tag
            or desired_by_tag[str(rule.get("tag"))]["value"] != rule.get("value")
        ]
        pairs = {(rule.get("tag"), rule.get("value")) for rule in managed}
        add = [rule for rule in desired if (rule["tag"], rule["value"]) not in pairs]
        if delete_ids:
            response = client.post(
                X_RULES_URL,
                headers=_headers(),
                json={"delete": {"ids": delete_ids}},
            )
            response.raise_for_status()
        if add:
            response = client.post(X_RULES_URL, headers=_headers(), json={"add": add})
            response.raise_for_status()
        return {"added": len(add), "deleted": len(delete_ids)}
    finally:
        if own_client:
            client.close()


def _signal(payload: dict[str, Any], config: XCollectorConfig) -> SignalRecord | None:
    post = payload.get("data") or {}
    if not post.get("id") or not post.get("text"):
        return None
    users = (payload.get("includes") or {}).get("users") or []
    user = next((item for item in users if item.get("id") == post.get("author_id")), {})
    username = user.get("username")
    author = f"@{username}" if username else user.get("name")
    managed_tags = [
        str(rule.get("tag"))[len(config.managed_tag_prefix) :]
        for rule in payload.get("matching_rules", [])
        if str(rule.get("tag", "")).startswith(config.managed_tag_prefix)
    ]
    published_at = None
    if post.get("created_at"):
        published_at = datetime.fromisoformat(str(post["created_at"]).replace("Z", "+00:00"))
    post_id = str(post["id"])
    url = (
        f"https://x.com/{username}/status/{post_id}"
        if username
        else f"https://x.com/i/web/status/{post_id}"
    )
    text = str(post["text"]).strip()
    return SignalRecord(
        source_type="x",
        source_id=post_id,
        source_name=f"X @{username}" if username else "X",
        title=" ".join(text.split())[:90],
        content=text,
        url=url,
        discovered_at=datetime.now(timezone.utc),
        published_at=published_at,
        author=author,
        tags=list(dict.fromkeys([*config.tags, *managed_tags])),
        source_tier=SourceTier.C,
        metadata={"matching_rules": payload.get("matching_rules", [])},
    )


def stream_x(config: XCollectorConfig, store: CollectorStore) -> None:
    if config.sync_rules:
        print(f"[X] 规则同步：{sync_x_rules(config)}")
    retry = 1
    params = {
        "tweet.fields": "author_id,created_at,lang,public_metrics",
        "expansions": "author_id",
        "user.fields": "id,name,username",
    }
    while True:
        try:
            timeout = httpx.Timeout(connect=20, read=None, write=20, pool=20)
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "GET", X_STREAM_URL, headers=_headers(), params=params
                ) as response:
                    response.raise_for_status()
                    print("[X] Filtered Stream 已连接")
                    retry = 1
                    for line in response.iter_lines():
                        if not line:
                            continue
                        signal = _signal(json.loads(line), config)
                        if signal:
                            result = "新增" if store.save_signal(signal) else "重复"
                            print(f"[X] {result}：{signal.url}")
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"[X] 连接失败，{retry} 秒后重试：{exc}")
            sleep(retry)
            retry = min(retry * 2, 120)
