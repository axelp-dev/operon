"""
LangGraph definition & compilation for
Orepon library module
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.library.nodes import (
    node_build_queries_llm,
    node_fetch_refs,
    node_filter_existing_articles,
    node_read_articles,
    node_save_index,
    node_search,
    route_after_building_queries,
    route_after_filter,
    route_after_indexing,
)
from src.library.state import BaseLibraryState, FetchState, SnowballState

# --- BUILD GRAPHS -------------------------------


def build_search_graph() -> CompiledStateGraph:
    """Build & Compile search graph for
    articles parsing & evaluation
    """
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
        "generate_queries",
        route_after_building_queries,
        {"query": "search", "end": END},
    )

    fetch_graph = builder.compile()
    return fetch_graph


def build_snowball_graph() -> CompiledStateGraph:
    """
    Build a snowball search LangGraph object for
    in-depth references exploration from existing
    articles in library.
    """
    builder = StateGraph(SnowballState)

    # Nodes definitions
    builder.add_node("fetch_refs", node_fetch_refs)

    # --- Graph Build ---
    # Fetch top-ranked articles' references
    builder.add_edge(START, "fetch_refs")
    builder.add_edge("fetch_refs", END)

    # Get most cited references

    # filter -> read -> save index

    snowball_graph = builder.compile()
    return snowball_graph
