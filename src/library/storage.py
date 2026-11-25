"""
Operon library storage manager
JSON <-> LangGraph managing functions
"""

import json
from pathlib import Path

from src.config import DATA_DIR


def _load_json_database(db_path: Path) -> dict:
    """Load json database from given path"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index = {}
    if db_path.exists():
        index = json.loads(db_path.read_text(encoding="utf-8"))
    return index
