from __future__ import annotations

import re

import httpx

INSTANCE_LIST_URL = "https://docs.rsshub.app/zh/guide/instances"
FALLBACK_INSTANCES: list[str] = [
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
    "https://hub.slarker.me",
    "https://rsshub.cups.moe",
    "https://rsshub.isrss.com",
]

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_FIRST_LINK_RE = re.compile(r'<a[^>]*\bhref="(https://[^"]+)"')
# 部分站点会按 UA 拦截非浏览器请求（例如把默认的 python-httpx UA 当作
# feed reader 限流），这里复用 source_resolver.py 里同样的浏览器 UA。
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def parse_instance_list(html: str) -> list[str]:
    """从实例列表页的表格中按行提取第一列（实例地址），忽略维护者链接等其他列。"""
    seen: set[str] = set()
    result: list[str] = []
    for row in _ROW_RE.findall(html):
        match = _FIRST_LINK_RE.search(row)
        if not match:
            continue
        url = match.group(1).rstrip("/")
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def fetch_instance_candidates(client: httpx.Client) -> list[str]:
    candidates: list[str] = []
    try:
        response = client.get(
            INSTANCE_LIST_URL, timeout=10, headers={"User-Agent": _BROWSER_USER_AGENT}
        )
        response.raise_for_status()
        candidates = parse_instance_list(response.text)
    except Exception:
        candidates = []
    if not candidates:
        candidates = list(FALLBACK_INSTANCES)
    if "https://rsshub.app" not in candidates:
        candidates.append("https://rsshub.app")
    return candidates
