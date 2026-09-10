from __future__ import annotations

from writing_agent.config import get_settings
from writing_agent.graph.state import GraphState
from writing_agent.services.source_resolver import resolve_source_inputs
from writing_agent.services.source_snapshot import SourceSnapshotError, read_source_snapshot
from writing_agent.services.tracing import traceable


@traceable(name="ingest_inputs")
def ingest_node(state: GraphState) -> dict:
    request = state["request"]
    if request.source_summary_token:
        try:
            source_items = read_source_snapshot(
                request.source_summary_token,
                request.materials,
                get_settings(),
            )
            materials = [item.content.strip() for item in request.materials if item.content.strip()]
            return {"materials": materials, "source_items": source_items}
        except SourceSnapshotError as exc:
            warning = f"已保存的来源检查结果不可用，已重新检查：{exc}"
            materials, source_items = resolve_source_inputs(request.materials)
            return {
                "materials": materials,
                "source_items": source_items,
                "warnings": [*state.get("warnings", []), warning],
            }
    materials, source_items = resolve_source_inputs(request.materials)
    if not materials:
        materials = [f"围绕主题“{request.topic}”进行结构化创作。"]

    return {"materials": materials, "source_items": source_items}
