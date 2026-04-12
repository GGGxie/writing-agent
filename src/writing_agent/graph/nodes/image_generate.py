from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.services.image_generation import generate_images


def image_generate_node(state: GraphState) -> dict:
    return {"generated_images": generate_images(state.get("image_plan", []))}
