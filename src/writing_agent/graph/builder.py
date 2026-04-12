from __future__ import annotations

from collections.abc import Callable

from writing_agent.graph.nodes.draft_wechat import draft_wechat_node
from writing_agent.graph.nodes.draft_xiaohongshu import draft_xiaohongshu_node
from writing_agent.graph.nodes.export import export_node
from writing_agent.graph.nodes.image_generate import image_generate_node
from writing_agent.graph.nodes.image_plan import image_plan_node
from writing_agent.graph.nodes.ingest import ingest_node
from writing_agent.graph.nodes.outline import outline_node
from writing_agent.graph.nodes.qc import qc_node
from writing_agent.graph.nodes.research import research_node
from writing_agent.graph.state import GraphState

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None


NodeFn = Callable[[GraphState], dict]
NODE_SEQUENCE: list[tuple[str, NodeFn]] = [
    ("ingest", ingest_node),
    ("research", research_node),
    ("outline", outline_node),
    ("image_plan", image_plan_node),
    ("image_generate", image_generate_node),
    ("draft_xiaohongshu", draft_xiaohongshu_node),
    ("draft_wechat", draft_wechat_node),
    ("quality_check", qc_node),
    ("export", export_node),
]


class SimpleGraphRunner:
    def __init__(self, sequence: list[tuple[str, NodeFn]]):
        self.sequence = sequence

    def invoke(self, state: GraphState) -> GraphState:
        current_state = dict(state)
        for _, node in self.sequence:
            current_state.update(node(current_state))
        return current_state


def build_writing_graph():
    if StateGraph is None:
        return SimpleGraphRunner(NODE_SEQUENCE)

    graph = StateGraph(GraphState)
    for name, node in NODE_SEQUENCE:
        graph.add_node(name, node)

    graph.add_edge(START, "ingest")
    for index in range(len(NODE_SEQUENCE) - 1):
        graph.add_edge(NODE_SEQUENCE[index][0], NODE_SEQUENCE[index + 1][0])
    graph.add_edge("export", END)
    return graph.compile()
