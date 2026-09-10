from __future__ import annotations

from writing_agent.config import get_settings
from writing_agent.graph.builder import build_writing_graph
from writing_agent.graph.state import create_initial_state
from writing_agent.models import GenerateRequest, GenerateResponse, SourceSummaryResponse
from writing_agent.services.source_resolver import summarize_only
from writing_agent.services.source_snapshot import SourceSnapshotError, read_source_snapshot
from writing_agent.services.tracing import traceable


@traceable(name="writing_pipeline")
def run_pipeline(request: GenerateRequest, feedback: str = "") -> GenerateResponse:
    graph = build_writing_graph()
    state = create_initial_state(request, feedback=feedback)
    result = graph.invoke(
        state,
        config={
            "configurable": {"thread_id": request.workflow_id},
            "metadata": {
                "thread_id": request.workflow_id,
                "workflow_id": request.workflow_id,
                "content_type": request.content_type.value,
                "creation_mode": request.creation_mode.value,
            },
            "tags": ["writing-agent", "generate"],
        },
    )
    response = result.get("response", {})
    return GenerateResponse.model_validate(response)


@traceable(name="summarize_sources")
def summarize_sources(request: GenerateRequest) -> SourceSummaryResponse:
    source_items = None
    if request.source_summary_token:
        try:
            source_items = read_source_snapshot(
                request.source_summary_token,
                request.materials,
                get_settings(),
            )
        except SourceSnapshotError:
            source_items = None
    return SourceSummaryResponse(
        workflow_id=request.workflow_id,
        topic=request.topic,
        source_items=(
            source_items if source_items is not None else summarize_only(request.materials)
        ),
    )
