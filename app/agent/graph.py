"""Assemble the sourcing agent StateGraph.

Flow: identify -> fetch amazon data -> (conditional route by mode) ->
one of three research nodes -> compute profit -> score & report -> END.
The abort path from routing skips research and goes straight to scoring.
"""

from functools import lru_cache

from langgraph.graph import END, StateGraph

from app.agent.nodes.research import (
    artisan_research,
    retail_arb_research,
    wholesale_research,
)
from app.agent.nodes.scoring import compute_profit, score_and_report
from app.agent.nodes.shared import (
    fetch_amazon_data,
    identify_product,
    route_by_mode,
)
from app.agent.state import SourcingState

RESEARCH_NODES = {
    "retail_arb_research": retail_arb_research,
    "wholesale_research": wholesale_research,
    "artisan_research": artisan_research,
}


def build_graph() -> StateGraph:
    g = StateGraph(SourcingState)

    g.add_node("identify_product", identify_product)
    g.add_node("fetch_amazon_data", fetch_amazon_data)
    for name, fn in RESEARCH_NODES.items():
        g.add_node(name, fn)
    g.add_node("compute_profit", compute_profit)
    g.add_node("score_and_report", score_and_report)

    g.set_entry_point("identify_product")
    g.add_edge("identify_product", "fetch_amazon_data")

    # conditional fan-out; route_by_mode returns a node name (incl. the
    # abort shortcut to "score_and_report")
    g.add_conditional_edges(
        "fetch_amazon_data",
        route_by_mode,
        {**{k: k for k in RESEARCH_NODES}, "score_and_report": "score_and_report"},
    )

    # all research nodes converge on profit computation
    for name in RESEARCH_NODES:
        g.add_edge(name, "compute_profit")

    g.add_edge("compute_profit", "score_and_report")
    g.add_edge("score_and_report", END)
    return g


@lru_cache
def get_compiled_graph():
    """Compiled app. Add a Postgres checkpointer here in production so failed
    runs resume from the last completed node."""
    return build_graph().compile()
