from __future__ import annotations

from writing_agent.editorial.evidence import evaluate_evidence, score_topic
from writing_agent.editorial.resources import load_editorial_context, load_template
from writing_agent.graph.state import GraphState


def editorial_context_node(state: GraphState) -> dict:
    request = state["request"]
    return {
        "editorial_context": load_editorial_context(request.profile_id),
        "selected_template": load_template(request.content_type),
    }


def topic_score_node(state: GraphState) -> dict:
    return {
        "topic_score": score_topic(
            state["request"],
            state.get("source_items", []),
        )
    }


def evidence_gate_node(state: GraphState) -> dict:
    topic_score = state.get("topic_score")
    if topic_score is None:
        raise RuntimeError("选题评分尚未生成")
    gate = evaluate_evidence(
        state["request"],
        state.get("source_items", []),
        topic_score,
    )
    warnings = list(state.get("warnings", []))
    if not gate.can_draft:
        warnings.append("证据不足：本次只生成研究材料，不生成可发布草稿。")
    return {"evidence_gate": gate, "warnings": warnings}
