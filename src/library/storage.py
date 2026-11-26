"""
Operon library storage manager
JSON <-> LangGraph managing functions
"""

import json
from pathlib import Path

from src.config import DATA_DIR
from src.library.state import ArticleMeta


def _load_json_database(db_path: Path) -> dict:
    """Load json database from given path"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index = {}
    if db_path.exists():
        index = json.loads(db_path.read_text(encoding="utf-8"))
    return index


def get_min_scored_articles(
    index: dict, min_score: int, max_articles: int
) -> list[ArticleMeta]:
    """
    Fetch current library and return all stored articles
    with art[score] >= min_score. Select the most
    max_articles number of them.
    """
    selected_articles: list[ArticleMeta] = []
    # --- Parse index library ---
    for raw_art in index.values():
        evaluation = raw_art.get("evaluation")
        if evaluation and evaluation.get("score", 0) >= min_score:
            # Create ArticleMeta & save article for return
            art: ArticleMeta = ArticleMeta.model_validate(raw_art)
            selected_articles.append(art)

    # --- Cut too long result ---
    selected_articles.sort(
        key=lambda art: art.evaluation.score if art.evaluation else 0, reverse=True
    )
    return selected_articles[:max_articles]
