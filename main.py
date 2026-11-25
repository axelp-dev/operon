from pathlib import Path

from langgraph.graph import END, START, StateGraph

from src.logger import log
from src.nodes import (
    node_build_queries_llm,
    node_filter_existing_articles,
    node_read_articles,
    node_save_index,
    node_search,
    route_after_building_queries,
    route_after_filter,
    route_after_indexing,
)
from src.state import FetchState

# --- INIT LOGGER -------------------------------

log.setup(log_file=Path("data/operon.log"))

# --- BUILD GRAPH -------------------------------

builder = StateGraph(FetchState)

# Nodes
builder.add_node("search", node_search)
builder.add_node("filter", node_filter_existing_articles)
# builder.add_node("download", node_download)
builder.add_node("read", node_read_articles)
builder.add_node("save_index", node_save_index)
# builder.add_node("generate_queries", node_build_queries)
builder.add_node("generate_queries", node_build_queries_llm)

# Describe nodes links
builder.add_edge(START, "search")
builder.add_edge("search", "filter")

# Condition after filter operation
builder.add_conditional_edges(
    "filter", route_after_filter, {"read": "read", "end": END, "search": "search"}
)
builder.add_edge("read", "save_index")
builder.add_conditional_edges(
    "save_index",
    route_after_indexing,
    {"build_queries": "generate_queries", "end": END},
)
builder.add_conditional_edges(
    "generate_queries", route_after_building_queries, {"query": "search", "end": END}
)

fetch_graph = builder.compile()


if __name__ == "__main__":
    fetch_graph.invoke(
        {
            "max_results": 5,
            "next_queries": [
                "(TITLE:Madagascar OR TITLE:Malagasy) AND (human OR Austronesian OR Bantu) AND (genomic OR genetic OR admixture OR ancestry)"
            ],
            "seen_queries": [],
            "raw_candidates": [],
            "new_articles": [],
            "n_iter": 1,
            "max_iter": 5,
        }
    )
