from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Platform(str, Enum):
    XIAOHONGSHU = "xiaohongshu"
    WECHAT = "wechat"


class ContentType(str, Enum):
    FLASH_NEWS = "flash-news"
    RAPID_ANALYSIS = "rapid-analysis"
    DEEP_DIVE = "deep-dive"
    PRODUCT_ANALYSIS = "product-analysis"
    PRODUCT_REVIEW = "product-review"
    OPEN_SOURCE_ANALYSIS = "open-source-analysis"
    TOOL_RELEASE = "tool-release"
    OPINION = "opinion"


class CreationMode(str, Enum):
    EXTERNAL_SIGNAL = "external-signal"
    ORIGINAL_IDEA = "original-idea"
    ARTIFACT_ANALYSIS = "artifact-analysis"


class WorkflowStatus(str, Enum):
    IDEA = "idea"
    RESEARCHING = "researching"
    DRAFT = "draft"
    FACT_CHECKED = "fact-checked"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SourceTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    UNCLASSIFIED = "unclassified"


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
    content: str = Field(min_length=1, max_length=100_000)
    source: str | None = None
    source_tier: SourceTier | None = None
    verified_by_user: bool = False
    author: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceItem(BaseModel):
    source_kind: str
    url: str | None = None
    platform: str = "generic"
    title: str
    summary: str
    site_name: str | None = None
    content_excerpt: str | None = None
    fetched: bool = False
    source_tier: SourceTier = SourceTier.UNCLASSIFIED
    tier_reason: str = "尚未分级"
    tier_verified: bool = False
    retrieved_at: datetime | None = None
    fetch_error: str | None = None


class GenerateRequest(BaseModel):
    workflow_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    topic: str = Field(min_length=1, max_length=200)
    creation_mode: CreationMode = CreationMode.EXTERNAL_SIGNAL
    core_question: str | None = Field(default=None, max_length=500)
    initial_thesis: str | None = Field(default=None, max_length=2_000)
    analysis_target: str | None = Field(default=None, max_length=500)
    audience: str = Field(default="泛内容读者", max_length=500)
    tone: str = Field(default="专业但有亲和力", max_length=500)
    goal: str = Field(default="产出等待人工确认的图文草稿", max_length=1_000)
    materials: list[MaterialInput] = Field(default_factory=list, max_length=30)
    platforms: list[Platform] = Field(default_factory=lambda: [Platform.WECHAT], min_length=1)
    extra_requirements: list[str] = Field(default_factory=list, max_length=20)
    content_type: ContentType = ContentType.RAPID_ANALYSIS
    profile_id: str = "tech-ai-wechat"
    event_time: datetime | None = None
    source_version: str | None = None
    source_summary_token: str | None = Field(default=None, max_length=100_000)


class FormSuggestionRequest(BaseModel):
    workflow_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    creation_mode: CreationMode = CreationMode.EXTERNAL_SIGNAL
    core_question: str | None = Field(default=None, max_length=500)
    initial_thesis: str | None = Field(default=None, max_length=2_000)
    analysis_target: str | None = Field(default=None, max_length=500)
    materials: list[MaterialInput] = Field(default_factory=list, max_length=30)


class FormSuggestionResponse(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    audience: str = Field(min_length=1, max_length=500)
    tone: str = Field(min_length=1, max_length=500)
    goal: str = Field(min_length=1, max_length=1_000)
    content_type: ContentType
    source_version: str | None = None
    core_question: str | None = None
    initial_thesis: str | None = None
    analysis_target: str | None = None
    source_items: list[SourceItem] = Field(default_factory=list)
    source_summary_token: str | None = None


class ReviewRequest(BaseModel):
    request: GenerateRequest
    feedback: str = Field(max_length=10_000)


class GoogleCredentialRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=16_384)
    csrf_token: str = Field(min_length=16, max_length=256)


class ResearchNote(BaseModel):
    title: str
    summary: str
    bullets: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


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
    blockers: list[str] = Field(default_factory=list)
    passed: bool = False


class TopicScoreResult(BaseModel):
    timeliness: int
    relevance: int
    credibility: int
    uniqueness: int
    extensibility: int
    total: int
    recommendation: str


class EvidenceGateResult(BaseModel):
    can_draft: bool
    next_status: WorkflowStatus
    primary_source_count: int = 0
    reliable_source_count: int = 0
    signal_source_count: int = 0
    reasons: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)


class ArticleDraft(BaseModel):
    platform: Platform
    title: str
    summary: str
    markdown: str
    tags: list[str] = Field(default_factory=list)
    blocks: list[ContentBlock] = Field(default_factory=list)
    quality: QualityCheckResult | None = None
    content_type: ContentType = ContentType.RAPID_ANALYSIS
    status: WorkflowStatus = WorkflowStatus.DRAFT
    source_checked_at: datetime | None = None
    generated_at: datetime | None = None
    artifact_path: str | None = None


class GenerateResponse(BaseModel):
    workflow_id: str
    run_id: str
    topic: str
    source_items: list[SourceItem] = Field(default_factory=list)
    research_notes: list[ResearchNote] = Field(default_factory=list)
    outline: list[OutlineSection] = Field(default_factory=list)
    image_plan: list[ImagePlanItem] = Field(default_factory=list)
    generated_images: list[GeneratedImage] = Field(default_factory=list)
    drafts: list[ArticleDraft] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.RESEARCHING
    topic_score: TopicScoreResult | None = None
    evidence_gate: EvidenceGateResult | None = None
    artifact_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceSummaryResponse(BaseModel):
    workflow_id: str
    topic: str
    source_items: list[SourceItem] = Field(default_factory=list)
    source_summary_token: str | None = None


class SignalRecord(BaseModel):
    source_type: str
    source_id: str
    source_name: str
    title: str
    content: str
    url: str
    discovered_at: datetime
    published_at: datetime | None = None
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_tier: SourceTier = SourceTier.C
    metadata: dict[str, Any] = Field(default_factory=dict)
