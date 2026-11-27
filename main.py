from pathlib import Path

from src.library.graphs import build_search_graph, build_snowball_graph
from src.logger import log

# --- INIT LOGGER -------------------------------

log.setup(log_file=Path("data/operon.log"))


# --- COMPILE & INVOKE GRAPHS -------------------------------

"""
# Build search graph
fetch_graph = build_search_graph()
fetch_graph.invoke(
    {
        "max_results": 20,
        "next_queries": [
            "(TITLE:Madagascar OR TITLE:Malagasy) AND (human OR Austronesian OR Bantu) AND (genomic OR genetic OR admixture OR ancestry)"
        ],
        "seen_queries": [],
        "raw_candidates": [],
        "new_articles": [],
        "rejected_articles": [],
        "n_iter": 1,
        "max_iter": 10,
    }
)
"""

snowball_graph = build_snowball_graph()
snowball_graph.invoke(
    {
        "min_score": 3,
        "min_refs": 2,
        "max_selected": 15,
        "selected_articles": [],
        "raw_candidates": [],
    }
)
