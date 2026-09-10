from __future__ import annotations

import re
from pathlib import Path

ALLOWED_TYPES = {
    "flash-news",
    "rapid-analysis",
    "deep-dive",
    "product-analysis",
    "product-review",
    "open-source-analysis",
    "tool-release",
    "opinion",
}
ALLOWED_STATUSES = {
    "idea",
    "researching",
    "draft",
    "fact-checked",
    "approved",
    "published",
    "archived",
}


def has_template_placeholder(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "YYYY-MM-DD",
            "](URL)",
            "](<URL>)",
            "<your-",
        )
    )


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    values = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def check_markdown_file(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    metadata = _frontmatter(text)
    errors: list[str] = []
    warnings: list[str] = []
    for key in ("title", "content_type", "status", "created_at", "updated_at"):
        if not metadata.get(key):
            errors.append(f"元数据 {key} 未填写")
    if metadata.get("content_type") and metadata["content_type"] not in ALLOWED_TYPES:
        errors.append(f"未知 content_type：{metadata['content_type']}")
    if metadata.get("status") and metadata["status"] not in ALLOWED_STATUSES:
        errors.append(f"未知 status：{metadata['status']}")
    if metadata.get("content_type") in {"flash-news", "rapid-analysis"} and not metadata.get(
        "source_checked_at"
    ):
        warnings.append("时效稿未填写 source_checked_at")
    if not re.search(r"https?://", text):
        warnings.append("未发现可访问的来源 URL")
    if re.search(r"(?:今天|昨天|刚刚)", text):
        warnings.append("发现相对时间，请补充绝对日期")
    if has_template_placeholder(text):
        warnings.append("仍包含模板占位符")
    return errors, warnings
