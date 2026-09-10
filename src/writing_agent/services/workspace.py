from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from writing_agent.config import get_settings
from writing_agent.models import (
    ArticleDraft,
    EvidenceGateResult,
    GenerateRequest,
    ResearchNote,
    SourceItem,
    TopicScoreResult,
)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return slug[:64] or "article"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def save_research_dossier(
    request: GenerateRequest,
    sources: list[SourceItem],
    notes: list[ResearchNote],
    score: TopicScoreResult,
    gate: EvidenceGateResult,
    run_id: str,
) -> Path:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    filename = f"{now:%Y%m%d-%H%M%S-%f}-{run_id[:8]}-{_slug(request.topic)}.md"
    path = get_settings().workspace_dir / "research" / filename
    lines = [
        "---",
        f'title: "{request.topic.replace(chr(34), chr(39))}"',
        f'workflow_id: "{request.workflow_id}"',
        f'run_id: "{run_id}"',
        f'creation_mode: "{request.creation_mode.value}"',
        f'content_type: "{request.content_type.value}"',
        f'status: "{gate.next_status.value}"',
        f'created_at: "{now.date().isoformat()}"',
        f'updated_at: "{now.date().isoformat()}"',
        "---",
        "",
        f"# {request.topic}",
        "",
        "## 写作简报",
        "",
        f"- 创作方式：{request.creation_mode.value}",
        f"- 核心问题：{request.core_question or '未填写'}",
        f"- 初步观点：{request.initial_thesis or '未填写'}",
        f"- 分析对象：{request.analysis_target or '未填写'}",
        "",
        "## 选题评分",
        "",
        f"总分 {score.total}/25；建议：{score.recommendation}。",
        "",
        "## 证据闸门",
        "",
        f"- 是否允许成稿：{'是' if gate.can_draft else '否'}",
        "- A/B/C 来源："
        f"{gate.primary_source_count}/{gate.reliable_source_count}/"
        f"{gate.signal_source_count}",
    ]
    lines.extend(f"- 缺失：{item}" for item in gate.missing_requirements)
    lines.extend(["", "## 来源", ""])
    for item in sources:
        url = item.url or "无链接"
        lines.append(
            f"- [{item.source_tier.value}级] {item.title} — {url}"
            f"（{'已抓取' if item.fetched else '未抓取'}；"
            f"{'等级已确认' if item.tier_verified else '等级仅为声明'}；{item.tier_reason}）"
        )
    lines.extend(["", "## 研究摘要", ""])
    for note in notes:
        lines.extend([f"### {note.title}", "", note.summary, ""])
        lines.extend(f"- {item}" for item in note.bullets)
        if note.source_urls:
            lines.extend(f"- 来源：{url}" for url in note.source_urls)
        lines.append("")
    lines.extend(["## 待确认", ""])
    if gate.missing_requirements:
        lines.extend(f"- [ ] {item}" for item in gate.missing_requirements)
    else:
        lines.append("- [ ] 发布前重新打开核心来源并确认时间、版本和适用范围")
    _atomic_write(path, "\n".join(lines).rstrip() + "\n")
    return path


def save_draft(draft: ArticleDraft, run_id: str) -> Path:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    filename = f"{now:%Y%m%d-%H%M%S-%f}-{run_id[:8]}-{draft.platform.value}-{_slug(draft.title)}.md"
    path = get_settings().workspace_dir / "drafts" / filename
    _atomic_write(path, draft.markdown.rstrip() + "\n")
    return path
