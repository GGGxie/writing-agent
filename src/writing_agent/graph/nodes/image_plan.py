from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.schemas.blocks import ImagePlanItem
from writing_agent.services.tracing import traceable


@traceable(name="plan_images")
def image_plan_node(state: GraphState) -> dict:
    request = state["request"]
    outline = state.get("outline", [])
    items: list[ImagePlanItem] = [
        ImagePlanItem(
            image_id="cover-main",
            purpose="封面图",
            placement_hint="文章开头",
            prompt=f"为主题“{request.topic}”生成中文内容封面，风格舒适、清爽、有留白，适合{request.audience}阅读。",
            style="editorial, clean layout, premium social media illustration",
            alt_text=f"{request.topic} 的封面视觉",
        )
    ]
    for index, section in enumerate(outline[:3], start=1):
        items.append(
            ImagePlanItem(
                image_id=f"section-{index}",
                purpose=f"{section.heading} 段间插图",
                placement_hint=f"插入在章节“{section.heading}”附近",
                prompt=(
                    f"围绕“{request.topic}”中的“{section.heading}”章节生成插图，"
                    f"重点表现：{'，'.join(section.key_points[:2])}。"
                ),
                style="soft editorial poster with modern Chinese content aesthetics",
                alt_text=f"{section.heading} 的辅助插图",
            )
        )
    return {"image_plan": items}
