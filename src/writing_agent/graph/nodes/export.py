from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.schemas.blocks import GenerateResponse
from writing_agent.services.pydantic_compat import model_dump


def export_node(state: GraphState) -> dict:
    drafts = [draft for draft in [state.get("xhs_draft"), state.get("wechat_draft")] if draft]
    response = GenerateResponse(
        topic=state["request"].topic,
        source_items=state.get("source_items", []),
        research_notes=state.get("research_notes", []),
        outline=state.get("outline", []),
        image_plan=state.get("image_plan", []),
        generated_images=state.get("generated_images", []),
        drafts=drafts,
    )
    return {"response": model_dump(response)}
