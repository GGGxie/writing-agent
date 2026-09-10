from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from writing_agent.models import (
    ArticleDraft,
    BlockType,
    ContentBlock,
    ContentType,
    GeneratedImage,
    Platform,
    WorkflowStatus,
)
from writing_agent.services.llm import concise_excerpt


def _strip_code_fence(markdown: str) -> str:
    text = markdown.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _body_blocks(markdown: str) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    paragraph: list[str] = []

    def flush() -> None:
        if not paragraph:
            return
        text = "\n".join(paragraph).strip()
        if text:
            blocks.append(
                ContentBlock(
                    id=f"paragraph-{len(blocks) + 1}",
                    type=BlockType.PARAGRAPH,
                    text=text,
                )
            )
        paragraph.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("# "):
            flush()
            blocks.append(
                ContentBlock(
                    id="title",
                    type=BlockType.TITLE,
                    text=line[2:].strip(),
                )
            )
        elif line.startswith("## "):
            flush()
            blocks.append(
                ContentBlock(
                    id=f"heading-{len(blocks) + 1}",
                    type=BlockType.HEADING,
                    text=line[3:].strip(),
                )
            )
        elif line.startswith("> "):
            flush()
            blocks.append(
                ContentBlock(
                    id=f"quote-{len(blocks) + 1}",
                    type=BlockType.QUOTE,
                    text=line[2:].strip(),
                )
            )
        else:
            paragraph.append(raw_line.strip())
    flush()
    return blocks


def _with_images(
    blocks: list[ContentBlock],
    images: list[GeneratedImage],
) -> list[ContentBlock]:
    image_map = {image.image_id: image for image in images}
    result: list[ContentBlock] = []
    cover = image_map.get("cover-main")
    if cover:
        result.append(
            ContentBlock(
                id="cover",
                type=BlockType.COVER,
                image_id=cover.image_id,
                image_url=cover.public_url,
                alt_text=cover.alt_text,
                caption="文章封面",
            )
        )
    section_index = 0
    for block in blocks:
        result.append(block)
        if block.type == BlockType.HEADING:
            section_index += 1
            image = image_map.get(f"section-{section_index}")
            if image:
                result.append(
                    ContentBlock(
                        id=f"image-{section_index}",
                        type=BlockType.IMAGE,
                        image_id=image.image_id,
                        image_url=image.public_url,
                        alt_text=image.alt_text,
                        caption=f"{block.text or '章节'}插图",
                    )
                )
    return result


def _markdown_for_blocks(blocks: list[ContentBlock]) -> str:
    lines: list[str] = []
    for block in blocks:
        if block.type == BlockType.COVER:
            if block.image_url:
                lines.append(f"![{block.alt_text or ''}]({block.image_url})")
        elif block.type == BlockType.TITLE:
            lines.append(f"# {block.text or ''}")
        elif block.type == BlockType.HEADING:
            lines.append(f"## {block.text or ''}")
        elif block.type == BlockType.QUOTE:
            lines.append(f"> {block.text or ''}")
        elif block.type == BlockType.IMAGE:
            if block.image_url:
                lines.append(f"![{block.alt_text or ''}]({block.image_url})")
                if block.caption:
                    lines.append(f"*{block.caption}*")
        elif block.type in {BlockType.PARAGRAPH, BlockType.SUMMARY, BlockType.TIPS, BlockType.TAGS}:
            lines.append(block.text or "")
        lines.append("")
    return "\n".join(lines).strip()


def build_draft(
    *,
    raw_markdown: str,
    platform: Platform,
    content_type: ContentType,
    topic: str,
    tags: list[str],
    images: list[GeneratedImage],
    event_time: datetime | None,
) -> ArticleDraft:
    body = _strip_code_fence(raw_markdown)
    blocks = _with_images(_body_blocks(body), images)
    title_block = next((item for item in blocks if item.type == BlockType.TITLE), None)
    if title_block is None:
        title_block = ContentBlock(id="title", type=BlockType.TITLE, text=topic)
        insert_at = 1 if blocks and blocks[0].type == BlockType.COVER else 0
        blocks.insert(insert_at, title_block)
    title = (title_block.text or topic).strip()
    first_paragraph = next(
        (item.text for item in blocks if item.type == BlockType.PARAGRAPH and item.text),
        f"围绕{topic}的研究草稿。",
    )
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    frontmatter = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"content_type: {json.dumps(content_type.value)}",
        f"status: {json.dumps(WorkflowStatus.DRAFT.value)}",
        f"created_at: {json.dumps(now.date().isoformat())}",
        f"updated_at: {json.dumps(now.date().isoformat())}",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
        f"generated_at: {json.dumps(now.isoformat(timespec='minutes'))}",
    ]
    if event_time:
        frontmatter.append(f"event_time: {json.dumps(event_time.isoformat())}")
    frontmatter.extend(["---", ""])
    markdown = "\n".join(frontmatter) + _markdown_for_blocks(blocks)
    return ArticleDraft(
        platform=platform,
        title=title,
        summary=concise_excerpt(first_paragraph, width=100),
        markdown=markdown,
        tags=tags,
        blocks=blocks,
        content_type=content_type,
        status=WorkflowStatus.DRAFT,
        source_checked_at=None,
        generated_at=now,
    )
