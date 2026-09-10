from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.models import OutlineSection
from writing_agent.services.llm import concise_excerpt, generate_text_strict
from writing_agent.services.research import summarize_notes
from writing_agent.services.tracing import traceable


@traceable(name="build_outline")
def outline_node(state: GraphState) -> dict:
    gate = state.get("evidence_gate")
    if gate is not None and not gate.can_draft:
        return {"outline": []}
    request = state["request"]
    notes_text = summarize_notes(state.get("research_notes", []))
    materials_text = "\n".join(state.get("materials", []))[:12_000]
    fallback_sections = [
        OutlineSection(
            heading="开场钩子",
            purpose="快速建立读者兴趣，并点明文章核心价值。",
            key_points=[
                f"主题：{request.topic}",
                f"受众关注：{request.audience}",
                "先给结果或直击痛点",
            ],
        ),
        OutlineSection(
            heading="核心展开",
            purpose="用 2 到 3 个关键角度承接价值表达。",
            key_points=[
                concise_excerpt(notes_text, 100),
                "穿插案例、经验或结构化建议",
                "安排一张段间插图承接节奏",
            ],
        ),
        OutlineSection(
            heading="结尾行动",
            purpose="收束观点并给出清晰互动指令。",
            key_points=[
                "总结最关键的启发",
                "引导收藏、转发、私信或留言",
            ],
        ),
    ]
    fallback = "\n".join(
        f"{section.heading}: {'; '.join(section.key_points)}" for section in fallback_sections
    )
    prompt = (
        "你是中文内容策划。请根据编辑规范、内容类型模板和研究材料生成自然大纲，"
        "不要强制三段式。只输出 5 到 8 个正文段落，不要单独输出文章标题。"
        "每段一行：段落标题：要点1；要点2；要点3。\n"
        f"主题：{request.topic}\n"
        f"创作方式：{request.creation_mode.value}\n"
        f"核心问题：{request.core_question or '未填写'}\n"
        f"初步观点：{request.initial_thesis or '未填写'}\n"
        f"分析对象：{request.analysis_target or '未填写'}\n"
        f"受众：{request.audience}\n"
        f"语气：{request.tone}\n"
        f"作者笔记与实践材料：\n{materials_text}\n"
        f"研究摘要：\n{notes_text}\n"
        f"编辑规范：\n{state.get('editorial_context', '')}\n"
        f"内容模板：\n{state.get('selected_template', '')}\n"
    )
    warnings = list(state.get("warnings", []))
    try:
        generated = generate_text_strict(prompt)
    except RuntimeError as exc:
        generated = fallback
        warnings.append(f"大纲模型不可用，已使用明确的基础大纲：{exc}")

    outline: list[OutlineSection] = []
    for line in generated.splitlines():
        separator = "：" if "：" in line else ":" if ":" in line else None
        if separator is None:
            continue
        heading, raw_points = line.split(separator, 1)
        heading = heading.strip().lstrip("-# ").strip()
        if heading in {"标题", "文章标题"}:
            continue
        points = [item.strip(" ;") for item in raw_points.split("；") if item.strip(" ;")]
        if not points:
            points = [item.strip(" ;") for item in raw_points.split(";") if item.strip(" ;")]
        outline.append(
            OutlineSection(
                heading=heading.strip(),
                purpose=f"围绕“{heading.strip()}”完成内容展开。",
                key_points=points[:4],
            )
        )
        if len(outline) >= 8:
            break
    if not outline:
        outline = fallback_sections

    return {"outline": outline, "warnings": list(dict.fromkeys(warnings))}
