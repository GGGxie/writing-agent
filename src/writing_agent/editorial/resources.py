from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from writing_agent.config import get_settings
from writing_agent.models import ContentType

TEMPLATE_NAMES = {
    ContentType.FLASH_NEWS: "flash-news.md",
    ContentType.RAPID_ANALYSIS: "rapid-analysis.md",
    ContentType.DEEP_DIVE: "deep-dive.md",
    ContentType.PRODUCT_ANALYSIS: "product-analysis.md",
    ContentType.PRODUCT_REVIEW: "product-review.md",
    ContentType.OPEN_SOURCE_ANALYSIS: "open-source-analysis.md",
    ContentType.TOOL_RELEASE: "tool-release.md",
    ContentType.OPINION: "opinion.md",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"无法读取编辑资源 {path}: {exc}") from exc


@lru_cache(maxsize=8)
def load_editorial_context(profile_id: str = "tech-ai-wechat") -> str:
    if profile_id != "tech-ai-wechat":
        raise ValueError(f"未知编辑档案：{profile_id}")
    root = get_settings().editorial_resources_dir
    sections = [
        _read(root / "positioning.md"),
        _read(root / "voice-guide.md"),
        _read(root / "source-policy.md"),
    ]
    return "\n\n".join(sections)


@lru_cache(maxsize=16)
def load_template(content_type: ContentType) -> str:
    root = get_settings().editorial_resources_dir / "templates"
    return _read(root / TEMPLATE_NAMES[content_type])
