from __future__ import annotations

from typing import TypedDict

from writing_agent.schemas.blocks import (
    ArticleDraft,
    GenerateRequest,
    GeneratedImage,
    ImagePlanItem,
    OutlineSection,
    QualityCheckResult,
    ResearchNote,
    SourceItem,
)


class GraphState(TypedDict, total=False):
    request: GenerateRequest
    materials: list[str]
    source_items: list[SourceItem]
    research_notes: list[ResearchNote]
    outline: list[OutlineSection]
    image_plan: list[ImagePlanItem]
    generated_images: list[GeneratedImage]
    xhs_draft: ArticleDraft | None
    wechat_draft: ArticleDraft | None
    review_feedback: str
    quality_checks: dict[str, QualityCheckResult]
    response: dict


def create_initial_state(request: GenerateRequest, feedback: str = "") -> GraphState:
    return {
        "request": request,
        "materials": [],
        "source_items": [],
        "research_notes": [],
        "outline": [],
        "image_plan": [],
        "generated_images": [],
        "xhs_draft": None,
        "wechat_draft": None,
        "review_feedback": feedback,
        "quality_checks": {},
        "response": {},
    }
