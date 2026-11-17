# ==========================================================
#                       States
# ==========================================================

from typing import TypedDict, Literal
from pydantic import BaseModel


class FetchState(TypedDict):
    query: str
    max_results: int
    raw_candidates: list[dict]
    new_articles: list[dict]


class ArticleMeta(BaseModel):
    """Article container for langraph"""

    pmid: str
    pmcid: str | None = None
    doi: str | None = None
    title: str
    year: int | None = None
    abstract: str = ""
    pdf_path: str | None = None
    xml_path: str | None = None
    status: Literal["pending_download", "pending_parse", "parsed", "no_pdf"] = (
        "pending_download"
    )
