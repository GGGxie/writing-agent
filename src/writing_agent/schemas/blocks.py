from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Platform(str, Enum):
    XIAOHONGSHU = "xiaohongshu"
    WECHAT = "wechat"


class BlockType(str, Enum):
    COVER = "cover"
    TITLE = "title"
    SUMMARY = "summary"
    PARAGRAPH = "paragraph"
    IMAGE = "image"
    QUOTE = "quote"
    TIPS = "tips"
    TAGS = "tags"
    HEADING = "heading"


class MaterialInput(BaseModel):
    kind: str = Field(default="text")
    content: str
    source: str | None = None


class SourceItem(BaseModel):
    source_kind: str
    url: str | None = None
    platform: str = "generic"
    title: str
    summary: str
    site_name: str | None = None
    content_excerpt: str | None = None
    fetched: bool = False


class GenerateRequest(BaseModel):
    topic: str
    audience: str = "泛内容读者"
    tone: str = "专业但有亲和力"
    goal: str = "产出适合发布的图文草稿"
    materials: list[MaterialInput] = Field(default_factory=list)
    platforms: list[Platform] = Field(
        default_factory=lambda: [Platform.XIAOHONGSHU, Platform.WECHAT]
    )
    extra_requirements: list[str] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    request: GenerateRequest
    feedback: str


class ResearchNote(BaseModel):
    title: str
    summary: str
    bullets: list[str] = Field(default_factory=list)


class OutlineSection(BaseModel):
    heading: str
    purpose: str
    key_points: list[str] = Field(default_factory=list)


class ImagePlanItem(BaseModel):
    image_id: str
    purpose: str
    placement_hint: str
    prompt: str
    style: str
    alt_text: str


class GeneratedImage(BaseModel):
    image_id: str
    purpose: str
    prompt: str
    alt_text: str
    file_path: str
    public_url: str


class ContentBlock(BaseModel):
    id: str
    type: BlockType
    text: str | None = None
    image_id: str | None = None
    image_url: str | None = None
    caption: str | None = None
    alt_text: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class QualityCheckResult(BaseModel):
    score: int = 80
    findings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ArticleDraft(BaseModel):
    platform: Platform
    title: str
    summary: str
    markdown: str
    tags: list[str] = Field(default_factory=list)
    blocks: list[ContentBlock] = Field(default_factory=list)
    quality: QualityCheckResult | None = None


class GenerateResponse(BaseModel):
    topic: str
    source_items: list[SourceItem] = Field(default_factory=list)
    research_notes: list[ResearchNote] = Field(default_factory=list)
    outline: list[OutlineSection] = Field(default_factory=list)
    image_plan: list[ImagePlanItem] = Field(default_factory=list)
    generated_images: list[GeneratedImage] = Field(default_factory=list)
    drafts: list[ArticleDraft] = Field(default_factory=list)


class SourceSummaryResponse(BaseModel):
    topic: str
    source_items: list[SourceItem] = Field(default_factory=list)
