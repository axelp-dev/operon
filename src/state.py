# ==========================================================
#                       States
# ==========================================================

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class FetchState(TypedDict):
    # Query params & storage
    max_results: int
    next_queries: list[str]
    seen_queries: list[str]

    # Articles containers
    raw_candidates: list[dict]
    new_articles: list[dict]

    # Iterations management
    n_iter: int
    max_iter: int


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
    ] = "pending_filtering"
