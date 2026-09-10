from __future__ import annotations

import re

from writing_agent.editorial.checker import has_template_placeholder
from writing_agent.graph.state import GraphState
from writing_agent.models import ArticleDraft, BlockType, CreationMode, QualityCheckResult

HYPE_WORDS = (
    "炸裂",
    "封神",
    "史诗级",
    "颠覆一切",
    "遥遥领先",
    "所有人必须",
    "显而易见",
)
FIRST_PERSON_CLAIMS = (
    "我实测",
    "我测试了",
    "我采访了",
    "用户告诉我",
    "读者告诉我",
    "我用了一个月",
)


def score_draft(draft: ArticleDraft, state: GraphState) -> QualityCheckResult:
    findings: list[str] = []
    suggestions: list[str] = []
    blockers: list[str] = []
    image_count = sum(1 for block in draft.blocks if block.type == BlockType.IMAGE)
    paragraph_count = sum(1 for block in draft.blocks if block.type == BlockType.PARAGRAPH)
    score = 100

    gate = state.get("evidence_gate")
    if gate is None or not gate.can_draft:
        blockers.append("证据闸门未通过")
        score -= 40
    if paragraph_count < 3:
        findings.append("正文段落偏少，可能尚未形成完整文章。")
        score -= 10
    if image_count == 0:
        findings.append("没有段间配图；这不阻止事实稿，但需要人工确认排版。")
        suggestions.append("按内容价值决定是否增加示意图，不为凑数量配图。")
        score -= 3
    if not re.search(r"https?://", draft.markdown):
        if state["request"].creation_mode == CreationMode.ORIGINAL_IDEA:
            findings.append("观点稿没有外部来源 URL；请确认正文没有需要核验的外部事实。")
            score -= 5
        else:
            blockers.append("正文没有可追溯来源 URL")
            score -= 20
    if re.search(r"(?:今天|昨天|刚刚)", draft.markdown):
        findings.append("发现相对时间表达。")
        suggestions.append("补充绝对日期。")
        score -= 5
    for word in HYPE_WORDS:
        if word in draft.markdown:
            findings.append(f"发现高风险夸张词：{word}")
            score -= 3
    has_experience_record = any(
        material.kind in {"test_record", "practice_record", "code_record", "tool_record"}
        and len(material.content.strip()) >= 80
        for material in state["request"].materials
    )
    for claim in FIRST_PERSON_CLAIMS:
        if claim in draft.markdown:
            if has_experience_record and claim in {"我实测", "我测试了"}:
                findings.append(f"发现有记录支撑的第一人称经历，发布前仍需确认：{claim}")
                score -= 2
            else:
                blockers.append(f"第一人称经历需要人工确认：{claim}")
                score -= 10
    if has_template_placeholder(draft.markdown):
        blockers.append("仍包含模板占位符")
        score -= 15
    if not findings and not blockers:
        findings.append("机械检查未发现明显问题，仍需人工事实审校。")

    return QualityCheckResult(
        score=max(score, 0),
        findings=findings,
        suggestions=suggestions,
        blockers=blockers,
        passed=not blockers and score >= 70,
    )


def qc_node(state: GraphState) -> dict:
    updates: dict = {"quality_checks": {}}
    quality_checks = {}
    for key, name in (("xhs_draft", "xiaohongshu"), ("wechat_draft", "wechat")):
        draft = state.get(key)
        if draft is None:
            continue
        draft.quality = score_draft(draft, state)
        quality_checks[name] = draft.quality
        updates[key] = draft
    updates["quality_checks"] = quality_checks
    return updates
