from __future__ import annotations

from writing_agent.graph.builder import build_writing_graph
from writing_agent.graph.state import create_initial_state
from writing_agent.schemas.blocks import GenerateRequest, GenerateResponse, SourceSummaryResponse
from writing_agent.services.pydantic_compat import model_validate
from writing_agent.services.source_resolver import summarize_only


def run_pipeline(request: GenerateRequest, feedback: str = "") -> GenerateResponse:
    graph = build_writing_graph()
    state = create_initial_state(request, feedback=feedback)
    result = graph.invoke(state)
    response = result.get("response", {})
    return model_validate(GenerateResponse, response)


def summarize_sources(request: GenerateRequest) -> SourceSummaryResponse:
    return SourceSummaryResponse(
        topic=request.topic,
        source_items=summarize_only(request.materials),
    )
