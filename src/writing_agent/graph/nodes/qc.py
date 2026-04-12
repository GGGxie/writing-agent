from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.schemas.blocks import ArticleDraft, BlockType, QualityCheckResult


def _score_draft(draft: ArticleDraft) -> QualityCheckResult:
    findings: list[str] = []
    suggestions: list[str] = []
    image_count = sum(1 for block in draft.blocks if block.type == BlockType.IMAGE)
    paragraph_count = sum(1 for block in draft.blocks if block.type == BlockType.PARAGRAPH)

    score = 80
    if image_count == 0:
        findings.append("没有检测到段间配图，图文体验偏弱。")
        suggestions.append("至少为封面外再增加 1 张段间插图。")
        score -= 15
    if paragraph_count < 3:
        findings.append("正文段落偏少，信息承接可能不够。")
        suggestions.append("补足至少 3 段正文，增强内容完成度。")
        score -= 10
    if draft.platform.value == "xiaohongshu" and paragraph_count > 5:
        findings.append("小红书段落略多，可能削弱轻阅读体验。")
        suggestions.append("压缩长段落，多拆成短句和卡点。")
        score -= 5
    if draft.platform.value == "wechat" and image_count < 2:
        findings.append("公众号章节配图偏少，容易出现整屏压字。")
        suggestions.append("在关键章节之间插入插图或引用块。")
        score -= 5

    if not findings:
        findings.append("图文结构完整，已具备可继续人工润色的基础。")
        suggestions.append("下一步重点优化品牌语气和细节事实。")

    return QualityCheckResult(score=max(score, 60), findings=findings, suggestions=suggestions)


def qc_node(state: GraphState) -> dict:
    updates: dict = {"quality_checks": {}}
    xhs = state.get("xhs_draft")
    wechat = state.get("wechat_draft")
    quality_checks = {}

    if xhs is not None:
        xhs.quality = _score_draft(xhs)
        quality_checks["xiaohongshu"] = xhs.quality
        updates["xhs_draft"] = xhs
    if wechat is not None:
        wechat.quality = _score_draft(wechat)
        quality_checks["wechat"] = wechat.quality
        updates["wechat_draft"] = wechat

    updates["quality_checks"] = quality_checks
    return updates
