from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.schemas.blocks import ArticleDraft, BlockType, ContentBlock, Platform
from writing_agent.services.llm import concise_excerpt, generate_text
from writing_agent.services.research import summarize_notes
from writing_agent.services.tracing import traceable


def _markdown_for_blocks(blocks: list[ContentBlock]) -> str:
    lines: list[str] = []
    for block in blocks:
        if block.type == BlockType.TITLE:
            lines.append(f"# {block.text}")
        elif block.type == BlockType.SUMMARY:
            lines.append(f"> {block.text}")
        elif block.type == BlockType.HEADING:
            lines.append(f"## {block.text}")
        elif block.type == BlockType.PARAGRAPH:
            lines.append(block.text or "")
        elif block.type == BlockType.QUOTE:
            lines.append(f"> {block.text}")
        elif block.type == BlockType.IMAGE:
            lines.append(f"![{block.alt_text or ''}]({block.image_url or ''})")
            if block.caption:
                lines.append(f"*{block.caption}*")
        lines.append("")
    return "\n".join(lines).strip()


@traceable(name="draft_wechat")
def draft_wechat_node(state: GraphState) -> dict:
    request = state["request"]
    outline = state.get("outline", [])
    notes = state.get("research_notes", [])
    image_map = {image.image_id: image for image in state.get("generated_images", [])}
    title = generate_text(
        prompt=(
            f"请为公众号文章生成一个正式但不僵硬的中文标题，主题“{request.topic}”。"
            "只返回标题。"
        ),
        fallback=f"关于{request.topic}，一篇更适合阅读的图文表达方案",
    ).replace("\n", "").strip("《》 ")
    summary = concise_excerpt(
        f"本文围绕{request.topic}，结合研究摘要与图文节奏设计，给出一篇适合公众号阅读的混排文章。",
        width=80,
    )

    blocks: list[ContentBlock] = [
        ContentBlock(
            id="wechat-cover",
            type=BlockType.COVER,
            image_id="cover-main",
            image_url=image_map.get("cover-main").public_url if image_map.get("cover-main") else None,
            alt_text=image_map.get("cover-main").alt_text if image_map.get("cover-main") else None,
            caption="文章封面",
        ),
        ContentBlock(id="wechat-title", type=BlockType.TITLE, text=title),
        ContentBlock(id="wechat-summary", type=BlockType.SUMMARY, text=summary),
        ContentBlock(
            id="wechat-quote",
            type=BlockType.QUOTE,
            text=concise_excerpt(summarize_notes(notes), width=90),
        ),
    ]

    for index, section in enumerate(outline, start=1):
        body = (
            f"围绕“{section.heading}”，文章会展开这几个维度："
            f"{'；'.join(section.key_points[:3])}。"
            "公众号版本会保留更完整的叙述和解释，让信息密度与阅读舒适度保持平衡。"
        )
        blocks.append(
            ContentBlock(
                id=f"wechat-heading-{index}",
                type=BlockType.HEADING,
                text=section.heading,
            )
        )
        blocks.append(
            ContentBlock(
                id=f"wechat-paragraph-{index}",
                type=BlockType.PARAGRAPH,
                text=body,
            )
        )
        image = image_map.get(f"section-{index}")
        if image:
            blocks.append(
                ContentBlock(
                    id=f"wechat-image-{index}",
                    type=BlockType.IMAGE,
                    image_id=image.image_id,
                    image_url=image.public_url,
                    alt_text=image.alt_text,
                    caption=f"{section.heading} 的章节插图",
                    meta={"placement_hint": "between_sections"},
                )
            )

    blocks.append(
        ContentBlock(
            id="wechat-ending",
            type=BlockType.PARAGRAPH,
            text="结尾建议回收全文核心观点，并给出一个明确的互动问题或行动建议，帮助读者完成情绪收束。",
        )
    )

    draft = ArticleDraft(
        platform=Platform.WECHAT,
        title=title,
        summary=summary,
        markdown=_markdown_for_blocks(blocks),
        tags=["公众号", "图文写作", request.topic],
        blocks=blocks,
    )
    return {"wechat_draft": draft}
