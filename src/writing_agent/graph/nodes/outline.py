from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.schemas.blocks import OutlineSection
from writing_agent.services.llm import concise_excerpt, generate_text
from writing_agent.services.research import summarize_notes
from writing_agent.services.tracing import traceable


@traceable(name="build_outline")
def outline_node(state: GraphState) -> dict:
    request = state["request"]
    notes_text = summarize_notes(state.get("research_notes", []))
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
    generated = generate_text(
        prompt=(
            "你是中文内容策划，请围绕下列信息写出三段式创作大纲，"
            "每段一行：标题：要点1；要点2；要点3。\n"
            f"主题：{request.topic}\n"
            f"受众：{request.audience}\n"
            f"语气：{request.tone}\n"
            f"研究摘要：\n{notes_text}\n"
        ),
        fallback=fallback,
    )

    outline: list[OutlineSection] = []
    for line in generated.splitlines():
        if ":" not in line:
            continue
        heading, raw_points = line.split(":", 1)
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
    if not outline:
        outline = fallback_sections

    return {"outline": outline}
