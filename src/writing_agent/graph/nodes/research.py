from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.services.research import (
    build_research_brief,
    improve_with_feedback,
    run_research,
)


def research_node(state: GraphState) -> dict:
    gate = state.get("evidence_gate")
    if gate is not None and not gate.can_draft:
        notes = build_research_brief(
            state["request"],
            state.get("source_items", []),
            gate.missing_requirements,
        )
        research_warnings: list[str] = []
    else:
        notes, research_warnings = run_research(
            state["request"], state.get("source_items", [])
        )
    notes = improve_with_feedback(notes, state.get("review_feedback", ""))
    warnings = list(dict.fromkeys([*state.get("warnings", []), *research_warnings]))
    return {"research_notes": notes, "warnings": warnings}
