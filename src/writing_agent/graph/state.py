from __future__ import annotations

from typing import TypedDict
from uuid import uuid4

from writing_agent.models import (
    ArticleDraft,
    EvidenceGateResult,
    GeneratedImage,
    GenerateRequest,
    ImagePlanItem,
    OutlineSection,
    QualityCheckResult,
    ResearchNote,
    SourceItem,
    TopicScoreResult,
)


class GraphState(TypedDict, total=False):
    run_id: str
    request: GenerateRequest
    materials: list[str]
    source_items: list[SourceItem]
    research_notes: list[ResearchNote]
    editorial_context: str
    selected_template: str
    topic_score: TopicScoreResult | None
    evidence_gate: EvidenceGateResult | None
    outline: list[OutlineSection]
    image_plan: list[ImagePlanItem]
    generated_images: list[GeneratedImage]
    xhs_draft: ArticleDraft | None
    wechat_draft: ArticleDraft | None
    review_feedback: str
    quality_checks: dict[str, QualityCheckResult]
    response: dict
    warnings: list[str]
    artifact_paths: list[str]


def create_initial_state(request: GenerateRequest, feedback: str = "") -> GraphState:
    return {
        "run_id": uuid4().hex,
        "request": request,
        "materials": [],
        "source_items": [],
        "research_notes": [],
        "editorial_context": "",
        "selected_template": "",
        "topic_score": None,
        "evidence_gate": None,
        "outline": [],
        "image_plan": [],
        "generated_images": [],
        "xhs_draft": None,
        "wechat_draft": None,
        "review_feedback": feedback,
        "quality_checks": {},
        "response": {},
        "warnings": [],
        "artifact_paths": [],
    }
