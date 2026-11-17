from pathlib import Path
from langgraph.graph import StateGraph, START, END

from src.tools import *
from src.nodes import *
from src.state import FetchState


# --- ENVIRONMENT ------------------------------

DATA_DIR = Path("data")
PDF_DIR = DATA_DIR / "pdf"
XML_DIR = DATA_DIR / "xml"
INDEX_PATH = DATA_DIR / "index.json"

HEADERS = {"User-Agent": "OperonBiblioBot/0.1 (mailto:contact@operon.local)"}


# --- BUILD GRAPH -------------------------------


builder = StateGraph(FetchState)

# Nodes
builder.add_node("search", node_search)
builder.add_node("filter", node_filter_existing_articles)
builder.add_node("download", node_download)
builder.add_node("save_index", node_save_index)

# Edges
builder.add_edge(START, "search")
builder.add_edge("search", "filter")

# Condition to continue
builder.add_conditional_edges(
    "filter",
    route_after_filter,
    {"download": "download", "end": END},
)
builder.add_edge("download", "save_index")
builder.add_edge("save_index", END)

fetch_graph = builder.compile()


if __name__ == "__main__":
    fetch_graph.invoke(
        {
            "query": "Madagascar Genomic Population Origin",
            "max_results": 5,
            "raw_candidates": [],
            "new_articles": [],
        }
    )
