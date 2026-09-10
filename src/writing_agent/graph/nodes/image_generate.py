from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.services.image_generation import generate_images


def image_generate_node(state: GraphState) -> dict:
    gate = state.get("evidence_gate")
    if gate is not None and not gate.can_draft:
        return {"generated_images": []}
    generated_images, image_warnings = generate_images(
        state.get("image_plan", []), state["run_id"]
    )
    warnings = list(dict.fromkeys([*state.get("warnings", []), *image_warnings]))
    return {"generated_images": generated_images, "warnings": warnings}
