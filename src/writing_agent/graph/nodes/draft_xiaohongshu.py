from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.schemas.blocks import ArticleDraft, BlockType, ContentBlock, Platform
from writing_agent.services.llm import generate_text
from writing_agent.services.tracing import traceable


def _markdown_for_blocks(blocks: list[ContentBlock]) -> str:
    lines: list[str] = []
    for block in blocks:
        if block.type == BlockType.TITLE:
            lines.append(f"# {block.text}")
        elif block.type == BlockType.SUMMARY:
            lines.append(block.text or "")
        elif block.type == BlockType.HEADING:
            lines.append(f"## {block.text}")
        elif block.type == BlockType.PARAGRAPH:
            lines.append(block.text or "")
        elif block.type == BlockType.IMAGE:
            lines.append(f"![{block.alt_text or ''}]({block.image_url or ''})")
            if block.caption:
                lines.append(f"*{block.caption}*")
        elif block.type == BlockType.TIPS:
            lines.append(f"> {block.text}")
        elif block.type == BlockType.TAGS:
            lines.append(block.text or "")
        lines.append("")
    return "\n".join(lines).strip()


@traceable(name="draft_xiaohongshu")
def draft_xiaohongshu_node(state: GraphState) -> dict:
    request = state["request"]
    outline = state.get("outline", [])
    feedback = state.get("review_feedback", "")
    image_map = {image.image_id: image for image in state.get("generated_images", [])}
    title_fallback = f"{request.topic}｜把内容写得更有画面感的 3 个办法"
    title = generate_text(
        prompt=(
            f"为小红书笔记写一个 18 字以内中文标题，主题是“{request.topic}”，"
            "要求有吸引力但不过度夸张。只返回标题。"
        ),
        fallback=title_fallback,
    ).replace("\n", "").strip("《》 ")
    summary = f"这篇内容会用更轻松、留白更足的方式讲清楚“{request.topic}”，读起来不累，也更容易收藏。"
    if feedback:
        summary += f" 这次还特别吸收了你的反馈：{feedback}"

    blocks: list[ContentBlock] = [
        ContentBlock(
            id="xhs-cover",
            type=BlockType.COVER,
            image_id="cover-main",
            image_url=image_map.get("cover-main").public_url if image_map.get("cover-main") else None,
            alt_text=image_map.get("cover-main").alt_text if image_map.get("cover-main") else None,
            caption="封面图",
        ),
        ContentBlock(id="xhs-title", type=BlockType.TITLE, text=title),
        ContentBlock(id="xhs-summary", type=BlockType.SUMMARY, text=summary),
    ]

    for index, section in enumerate(outline, start=1):
        paragraph = (
            f"{section.heading}这部分，我会先点出最值得关注的内容："
            f"{'，'.join(section.key_points[:2])}。"
            "表达上保持短句和留白，让读者能快速抓到重点。"
        )
        blocks.append(
            ContentBlock(
                id=f"xhs-heading-{index}",
                type=BlockType.HEADING,
                text=section.heading,
            )
        )
        blocks.append(
            ContentBlock(
                id=f"xhs-paragraph-{index}",
                type=BlockType.PARAGRAPH,
                text=paragraph,
            )
        )
        image = image_map.get(f"section-{index}")
        if image:
            blocks.append(
                ContentBlock(
                    id=f"xhs-image-{index}",
                    type=BlockType.IMAGE,
                    image_id=image.image_id,
                    image_url=image.public_url,
                    alt_text=image.alt_text,
                    caption=f"{section.heading} 的情绪插图",
                    meta={"placement_hint": "after_section"},
                )
            )
        blocks.append(
            ContentBlock(
                id=f"xhs-tip-{index}",
                type=BlockType.TIPS,
                text=f"可直接提炼成一句记忆点：{' / '.join(section.key_points[:2])}",
            )
        )

    tags = ["#小红书写作", "#图文排版", "#内容创作", f"#{request.topic.replace(' ', '')}"]
    blocks.append(
        ContentBlock(
            id="xhs-tags",
            type=BlockType.TAGS,
            text=" ".join(tags),
        )
    )

    draft = ArticleDraft(
        platform=Platform.XIAOHONGSHU,
        title=title,
        summary=summary,
        markdown=_markdown_for_blocks(blocks),
        tags=tags,
        blocks=blocks,
    )
    return {"xhs_draft": draft}
