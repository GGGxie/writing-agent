from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from writing_agent.schemas.blocks import MaterialInput, SourceItem
from writing_agent.services.llm import concise_excerpt, generate_text


URL_RE = re.compile(r"^https?://", re.IGNORECASE)
VIDEO_HOSTS = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "bilibili.com": "bilibili",
    "douyin.com": "douyin",
    "vimeo.com": "vimeo",
}


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.paragraphs: list[str] = []
        self._collect_paragraph = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = attrs_dict.get("property") or attrs_dict.get("name")
            content = attrs_dict.get("content")
            if key and content:
                self.meta[key.lower()] = content.strip()
        elif tag == "p":
            self._collect_paragraph = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "p":
            self._collect_paragraph = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split()).strip()
        if not text:
            return
        if self.in_title and not self.title:
            self.title = text
        if self._collect_paragraph and len(text) > 20:
            self.paragraphs.append(text)


def looks_like_url(value: str) -> bool:
    return bool(URL_RE.match(value.strip()))


def classify_url(url: str) -> tuple[str, str]:
    host = (urlparse(url).netloc or "").lower().replace("www.", "")
    if host in VIDEO_HOSTS:
        return "video", VIDEO_HOSTS[host]
    if "xiaohongshu.com" in host:
        return "note", "xiaohongshu"
    if "mp.weixin.qq.com" in host:
        return "article", "wechat"
    if host:
        return "article", host.split(".")[0]
    return "article", "generic"


def fetch_url_metadata(url: str) -> dict[str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=8) as response:
        raw = response.read(120_000).decode("utf-8", errors="ignore")

    parser = MetadataParser()
    parser.feed(raw)
    title = (
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or parser.title
        or url
    )
    summary = (
        parser.meta.get("og:description")
        or parser.meta.get("description")
        or parser.meta.get("twitter:description")
        or concise_excerpt(" ".join(parser.paragraphs[:3]), width=220)
        or "未提取到摘要，将基于链接主题进行写作。"
    )
    site_name = parser.meta.get("og:site_name") or urlparse(url).netloc
    excerpt = concise_excerpt(" ".join(parser.paragraphs[:3]), width=280)
    return {
        "title": title,
        "summary": summary,
        "site_name": site_name,
        "content_excerpt": excerpt,
    }


def build_source_summary(
    *,
    source_kind: str,
    platform: str,
    title: str,
    summary: str,
    excerpt: str | None,
) -> str:
    fallback = summary or excerpt or "未提取到有效摘要。"
    if source_kind == "text":
        return fallback

    return generate_text(
        prompt=(
            "请把下面这个来源内容总结成 2 句中文摘要，"
            "第一句说这个来源主要讲了什么，第二句说它对后续写文章有什么可用价值。"
            "不要写套话。\n"
            f"来源类型：{source_kind}\n"
            f"平台：{platform}\n"
            f"标题：{title}\n"
            f"原摘要：{summary}\n"
            f"摘录：{excerpt or '无'}\n"
        ),
        fallback=fallback,
    )


def resolve_source_inputs(materials: list[MaterialInput]) -> tuple[list[str], list[SourceItem]]:
    normalized: list[str] = []
    source_items: list[SourceItem] = []

    for material in materials:
        content = material.content.strip()
        source = material.source or content
        if not content:
            continue

        if material.kind in {"url", "article", "video"} or looks_like_url(content):
            source_kind, platform = classify_url(source)
            title = source
            summary = "将基于链接主题生成内容。"
            site_name = urlparse(source).netloc or None
            excerpt = None
            fetched = False
            try:
                metadata = fetch_url_metadata(source)
                title = metadata["title"]
                summary = metadata["summary"]
                site_name = metadata["site_name"]
                excerpt = metadata["content_excerpt"]
                summary = build_source_summary(
                    source_kind=source_kind,
                    platform=platform,
                    title=title,
                    summary=summary,
                    excerpt=excerpt,
                )
                fetched = True
            except Exception:
                pass

            item = SourceItem(
                source_kind=source_kind,
                url=source,
                platform=platform,
                title=title,
                summary=summary,
                site_name=site_name,
                content_excerpt=excerpt,
                fetched=fetched,
            )
            source_items.append(item)
            normalized.append(
                f"[{source_kind}|{platform}] {title}。摘要：{summary}"
            )
        else:
            item = SourceItem(
                source_kind="text",
                title="文本素材",
                summary=concise_excerpt(content, width=120),
                content_excerpt=content[:280],
                fetched=False,
            )
            source_items.append(item)
            normalized.append(content)

    if not normalized:
        normalized = ["围绕当前主题进行结构化创作。"]
    return normalized, source_items


def summarize_only(materials: list[MaterialInput]) -> list[SourceItem]:
    _, source_items = resolve_source_inputs(materials)
    return source_items
