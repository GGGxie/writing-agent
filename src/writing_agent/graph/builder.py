from __future__ import annotations

from collections.abc import Callable

from writing_agent.graph.nodes.draft_wechat import draft_wechat_node
from writing_agent.graph.nodes.draft_xiaohongshu import draft_xiaohongshu_node
from writing_agent.graph.nodes.editorial import (
    editorial_context_node,
    evidence_gate_node,
    topic_score_node,
)
from writing_agent.graph.nodes.export import export_node
from writing_agent.graph.nodes.image_generate import image_generate_node
from writing_agent.graph.nodes.image_plan import image_plan_node
from writing_agent.graph.nodes.ingest import ingest_node
from writing_agent.graph.nodes.outline import outline_node
from writing_agent.graph.nodes.qc import qc_node
from writing_agent.graph.nodes.research import research_node
from writing_agent.graph.state import GraphState
from writing_agent.services.observability import instrument_graph_node

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None


NodeFn = Callable[[GraphState], dict]
RAW_NODE_SEQUENCE: list[tuple[str, NodeFn]] = [
    ("ingest", ingest_node),
    ("editorial_context", editorial_context_node),
    ("topic_score", topic_score_node),
    ("evidence_gate", evidence_gate_node),
    ("research", research_node),
    ("outline", outline_node),
    ("image_plan", image_plan_node),
    ("image_generate", image_generate_node),
    ("draft_xiaohongshu", draft_xiaohongshu_node),
    ("draft_wechat", draft_wechat_node),
    ("quality_check", qc_node),
    ("export", export_node),
]
NODE_SEQUENCE: list[tuple[str, NodeFn]] = [
    (name, instrument_graph_node(name, node)) for name, node in RAW_NODE_SEQUENCE
]


class SimpleGraphRunner:
    def __init__(self, sequence: list[tuple[str, NodeFn]]):
        self.sequence = sequence

    def invoke(self, state: GraphState, config: dict | None = None) -> GraphState:
        current_state = dict(state)
        research_only = False
        for name, node in self.sequence:
            if research_only and name != "export":
                continue
            current_state.update(node(current_state))
            if name == "research":
                gate = current_state.get("evidence_gate")
                research_only = gate is not None and not gate.can_draft
        return current_state


def _route_after_research(state: GraphState) -> str:
    gate = state.get("evidence_gate")
    return "draft" if gate is not None and gate.can_draft else "research_only"


def build_writing_graph():
    if StateGraph is None:
        return SimpleGraphRunner(NODE_SEQUENCE)

    graph = StateGraph(GraphState)
    for name, node in NODE_SEQUENCE:
        graph.add_node(name, node)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "editorial_context")
    graph.add_edge("editorial_context", "topic_score")
    graph.add_edge("topic_score", "evidence_gate")
    graph.add_edge("evidence_gate", "research")
    graph.add_conditional_edges(
        "research",
        _route_after_research,
        {"draft": "outline", "research_only": "export"},
    )
    drafting_sequence = [
        "outline",
        "image_plan",
        "image_generate",
        "draft_xiaohongshu",
        "draft_wechat",
        "quality_check",
        "export",
    ]
    for index in range(len(drafting_sequence) - 1):
        graph.add_edge(drafting_sequence[index], drafting_sequence[index + 1])
    graph.add_edge("export", END)
    return graph.compile()
