# ==========================================================
#                   Nodes
# ==========================================================

import json

from src.config import CONTEXT, DATA_DIR, INDEX_PATH
from src.logger import log
from src.state import FetchState
from src.tools import (
    build_anchored_queries,
    download_pmc_assets,
    generate_llm_queries,
    parse_article,
    search_europe_pmc,
    search_ncbi_pubmed,
    search_openalex,
)

# --- NODES -------------------------------


SEARCH_PROVIDERS = [
    ("EuropePMC", search_europe_pmc),
    ("NCBI_PubMed", search_ncbi_pubmed),
    ("OpenAlex", search_openalex),
]


def node_search(state: FetchState) -> dict:
    """
    Deterministic searching node with automatic provider fallback.
    """
    log.wave(state["n_iter"], state["max_iter"])

    # Get next query
    query = state["next_queries"][0]
    # Delete used query from query list
    remaining_queries = state["next_queries"][1:]

    results = []
    for provider_name, search_tool in SEARCH_PROVIDERS:
        try:
            results = search_tool.invoke(
                {"query": query, "max_results": state["max_results"]}
            )
            log.query(f"({provider_name}) Found {len(results)} articles using {query}")
            break  # Succès -> on sort de la boucle de fallback
        except Exception as exc:
            log.warn(
                f"({provider_name}) Failed ({type(exc).__name__}), trying next provider..."
            )

    return {
        "raw_candidates": results,
        "n_iter": state["n_iter"] + 1,
        "next_queries": remaining_queries,
        "seen_queries": state["seen_queries"] + [query],
    }


def node_filter_existing_articles(state: FetchState) -> dict:
    """Filter existing articles in FetchState["raw_candidates"]
    and return only non existing articles.
    Modify state 'new_articles' list and re-init 'raw_candidates' one.
    """

    # --- Load JSON database ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_index = {}
    if INDEX_PATH.exists():
        existing_index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    # --- Create new_items dict ---
    new_items = []
    for art in state["raw_candidates"]:
        if art["pmid"] not in existing_index:
            art["status"] = "pending_parsing"
            new_items.append(art)
    log.filter(
        f"Keeping {len(new_items)} articles from {len(state['raw_candidates'])} raw candidates"
    )
    return {"new_articles": new_items, "raw_candidates": []}


def node_read_articles(state: FetchState) -> dict:
    """Read all articles using Ollama model to retrieve
    methods, keywords and related articles"""

    log.read(f"Starting reading {len(state['new_articles'])} articles...")

    accepted_articles = []
    # Call model for all pending_parsing articles
    total = len(state["new_articles"])
    for i, art in enumerate(state["new_articles"], start=1):
        if art["status"] == "pending_parsing":
            uid = art.get("doi") or art["pmid"]
            log.reading_progress(i, total, uid)

            # Build article str
            article_str = f"""title : {art["title"]}, year : {art["year"]}, abtract : {art["abstract"]}"""

            # Call the tool
            eval = parse_article(CONTEXT, article_str)
            keep = eval.score >= 3
            log.article(i, total, uid, eval.score, keep)

            if keep:
                # Append the eval to the article
                art["evaluation"] = eval.model_dump()
                art["status"] = "accepted_pending_download"
                # Append the article to saved ones
                accepted_articles.append(art)

    return {"new_articles": accepted_articles}


def node_save_index(state: FetchState) -> dict:
    """Save new_articles into index.json database"""

    # --- Load JSON database ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index = {}
    if INDEX_PATH.exists():
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    # --- Save articles ---
    for art in state["new_articles"]:
        index[art["pmid"]] = art

    INDEX_PATH.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.index(f"Saved ({len(index)} articles in {INDEX_PATH})")
    return {}


def node_build_queries(state: FetchState) -> dict:
    """Build new queries from articles parsing using
    extracted keytwords"""

    log.query("Building queries...")

    # --- Build Keywords Score Dict ---
    articles_keywords = {}
    for art in state["new_articles"]:
        # Get article info
        if art["evaluation"] is not None:
            keywords = art["evaluation"]["keywords"]
            art_score = art["evaluation"]["score"]
        else:
            continue
        # Append keywords to keywords_dict
        for w in keywords:
            if w in articles_keywords:
                # Adding word scores
                articles_keywords[w] += art_score
            else:
                # Simply add it with current score
                articles_keywords[w] = art_score

    # --- Build new queries ---
    # Delete low-score keywords
    filtered_keywords = {
        w.strip().lower(): articles_keywords[w]
        for w in articles_keywords
        if articles_keywords[w] >= 3
    }
    sorted_kw = dict(
        sorted(filtered_keywords.items(), key=lambda item: item[1], reverse=True)
    )

    log.debug(scope="DEBUG", msg="Keywords : {sorted_kw}")

    new_queries = build_anchored_queries(
        sorted_keywords=sorted_kw,
        seen_queries=set(state["seen_queries"]),
        top_pool_size=12,  # Get best 12 keywords
        n_queries=3,  # Generates 3 requests
        keywords_per_query=2,  # Use 2 words per requests
    )
    # Appending queries to pending ones
    queries = state["next_queries"] + new_queries
    # Update n_iter at the end of the loop
    new_n_iter = state["n_iter"] + 1
    return {"next_queries": queries, "new_articles": [], "n_iter": new_n_iter}


def node_build_queries_llm(state: FetchState) -> dict:

    log.query("Building queries with LLM...")

    new_queries = generate_llm_queries(
        context=CONTEXT,
        accepted_articles=state["new_articles"],
        seen_queries=state["seen_queries"],
        n_queries=3,
    )
    log.query(f"Generated {len(new_queries)}")
    log.query(f"New Queries : {new_queries}")

    return {"next_queries": state["next_queries"] + new_queries}


def node_download(state: FetchState) -> dict:
    """Download both PDF and XML assets for filtered articles."""
    updated = []
    for art in state["new_articles"]:
        if not art.get("pmcid"):
            art["status"] = "no_content"
            updated.append(art)
            continue

        assets = download_pmc_assets.invoke(
            {
                "pmid": art["pmid"],
                "pmcid": art["pmcid"],
                "doi": art.get("doi"),
            }
        )
        art["pdf_path"] = assets["pdf_path"]
        art["xml_path"] = assets["xml_path"]

        if art["pdf_path"] or art["xml_path"]:
            art["status"] = "pending_parse"
            log.search(
                f"[Download] {art['pmid']} -> PDF: {bool(art['pdf_path'])} | XML: {bool(art['xml_path'])}"
            )
        else:
            art["status"] = "no_content"
            log.search("Unable to download assets for {art['pmid']}")

        updated.append(art)

    return {"new_articles": updated}


# --- CONDITIONNAL NODES -------------------------------


def route_after_filter(state: FetchState) -> str:
    """Decide to continue download of not"""
    if len(state["new_articles"]) > 0:
        return "read"
    if len(state["next_queries"]) > 0:
        log.info("0 new articles, trying next queued query...")
        return "search"
    log.info("No new articles, trying next queued query...")
    return "end"


def route_after_indexing(state: FetchState) -> str:
    """Decide to query new articles or not"""
    if state["n_iter"] == state["max_iter"]:
        log.info("max_iter reached")
        return "end"
    return "build_queries"


def route_after_building_queries(state: FetchState) -> str:
    """Decide to restart querying of not accroding
    to the query number"""
    if len(state["next_queries"]) == 0:
        log.info("No queries in the stack. Stopping...")
        return "end"
    else:
        log.info(
            f"[Continue] Restart query for iter {state['n_iter']}/{state['max_iter']}..."
        )
        return "query"
