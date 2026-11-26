# ==========================================================
#                       States
# ==========================================================

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


# --- Article Evaluation -------------------------------


class ArticleEvaluation(BaseModel):
    reasoning: str = Field(
        description="2-sentence analysis explaining whether the study deals with human population genetics/genomics, Madagascar/Malagasy ancestry, or relevant statistical genomics methods."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="3 to 5 concise English scientific keywords if relevant, otherwise empty list.",
    )
    score: int = Field(
        ge=0,
        le=5,
        description="Relevance score from 0 (unrelated/non-human) to 5 (directly studies Malagasy human population genomics).",
    )


# --- Article container -------------------------------


class ArticleMeta(BaseModel):
    """Article container for langraph"""

    # General infos
    pmid: str
    pmcid: str | None = None
    doi: str | None = None
    title: str
    year: int | None = None
    abstract: str = ""

    # Storage informations
    pdf_path: str | None = None
    xml_path: str | None = None

    # Evaluation
    evaluation: ArticleEvaluation | None = None

    # Pipeline status
    status: Literal[
        "pending_filtering",  # Article just added to the current state
        "pending_parsing",  # Pending LLM parsing
        "accepted_pending_download",
    ] = "pending_filtering"


class QueryBatch(BaseModel):
    """Query format for query construction by local
    LLM from extratected keyword"""

    queries: list[str] = Field(
        description="3 distinct Boolean search queries for Europe PMC targeting human population genetics of Madagascar."
    )


# --- LangGraph States -------------------------------

"""
Use heritency for the two graphs (fetch_graph & snowball_graph): 
- BaseLibraryState - Mother-class 
  |
  -> FetchState used by fetch_graph 
  |
  -> SnownbalState used by snowball_graph 
"""


class BaseLibraryState(TypedDict):
    """
    Mother class for library LagGraphs
    """

    # --- Articles Containers ---
    # Found articles - not parsed or indexed
    raw_candidates: list[dict]
    # Accepted articles -> to save in index.json
    new_articles: list[dict]
    # Rejected articles -> to save in history.json
    rejected_articles: list[dict]


class FetchState(BaseLibraryState):
    # --- Query Management ---
    # Max query results
    max_results: int
    # Next queries in the stack to fetch
    next_queries: list[str]
    seen_queries: list[str]

    # Iterations management
    n_iter: int
    max_iter: int


class SnowballState(BaseLibraryState):
    # --- Config ---
    # Min score for an article to search its references
    min_score: int
    # Number of minimal citations for a reference to be fetched
    min_refs: int

    # --- Containers ---
    # Selected articles for references extention
    selected_articles: list[ArticleMeta]
    # References to fetch
    raw_references: list[str]
