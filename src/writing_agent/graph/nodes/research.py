from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.services.research import improve_with_feedback, run_research


def research_node(state: GraphState) -> dict:
    notes = run_research(state["request"], state.get("source_items", []))
    notes = improve_with_feedback(notes, state.get("review_feedback", ""))
    return {"research_notes": notes}
