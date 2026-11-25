"""
LLM calls tools and helpers
"""

from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from src.library.state import ArticleEvaluation, QueryBatch
from src.models import qwen_llm, qwen_llm_25


def generate_llm_queries(
    context: str,
    accepted_articles: list[dict],
    seen_queries: list[str],
    n_queries: int = 3,
) -> list[str]:
    """Asks LLM to build relevent queries from extracted keywords"""

    summaries = [
        f"- {art['title']} (keywords: {', '.join(art['evaluation']['keywords'])})"
        for art in accepted_articles
        if art.get("evaluation") and art["evaluation"]["score"] >= 4
    ]
    if not summaries:
        summaries = [
            f"- {art['title']}" for art in accepted_articles if art.get("evaluation")
        ]
    prompt = f"""Based on these relevant human genetics articles we just found:
{chr(10).join(summaries[:8])}

Generate {n_queries} broad Boolean search queries to discover MORE articles on human population genomics, admixture, and peopling history of Madagascar and the Indian Ocean.

Rules:
1. Do NOT use field prefixes like TITLE: or ABSTRACT:. Use plain terms with uppercase AND / OR.
2. Keep queries broad using at most TWO AND-clauses: (Geography) AND (Genetics/Population terms).
   Good example: (Madagascar OR Malagasy) AND (admixture OR Austronesian OR Bantu OR haplogroup)
   Good example: ("Indian Ocean" OR Comoros OR Madagascar) AND ("population genomics" OR "human migration" OR IBD)
3. Focus ONLY on human populations and genomics.
4. Do NOT repeat these already executed queries: {seen_queries}
"""
    planner_llm = qwen_llm.with_structured_output(QueryBatch)
    res = planner_llm.invoke(
        [
            SystemMessage(content=context),
            HumanMessage(content=prompt),
        ]
    )
    batch = QueryBatch.model_validate(res) if isinstance(res, dict) else res

    seen_norm = {q.strip().lower() for q in seen_queries}
    return [q.strip() for q in batch.queries if q.strip().lower() not in seen_norm]


def parse_article(context: str, article_str: str) -> ArticleEvaluation:
    """Parse article using Ollama and return ArticleEvaluation
    object"""
    # Devine output format - ArticleEvaluation
    # evaluator_llm = qwen_llm.with_structured_output(ArticleEvaluation)
    evaluator_llm = qwen_llm_25.with_structured_output(ArticleEvaluation)
    # Build prompt using CONTEXT and article_str content
    messages = [
        SystemMessage(content=context),
        HumanMessage(content=f"Evaluate this article metadata:\n{article_str[:3000]}"),
    ]
    # Call the llm
    eval = evaluator_llm.invoke(messages)
    if isinstance(eval, dict):
        return ArticleEvaluation.model_validate(eval)
    return cast(ArticleEvaluation, eval)
