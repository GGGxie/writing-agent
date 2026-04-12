from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.services.source_resolver import resolve_source_inputs
from writing_agent.services.tracing import traceable


@traceable(name="ingest_inputs")
def ingest_node(state: GraphState) -> dict:
    request = state["request"]
    materials, source_items = resolve_source_inputs(request.materials)
    if not materials:
        materials = [f"围绕主题“{request.topic}”进行结构化创作。"]

    return {"materials": materials, "source_items": source_items}
