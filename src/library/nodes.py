# ==========================================================
#                   Nodes
# ==========================================================

import json

from src.config import CONTEXT, HISTORY_PATH, INDEX_PATH
from src.library.llm_tasks import generate_llm_queries, parse_article
from src.library.providers import (
    download_pmc_assets,
    get_references_europe_pmc,
    get_references_ncbi_pubmed,
    get_references_openalex,
    search_europe_pmc,
    search_ncbi_pubmed,
    search_openalex,
)
from src.library.state import BaseLibraryState, FetchState, SnowballState
from src.library.storage import _load_json_database
from src.logger import log

# --- NODES -------------------------------


SEARCH_PROVIDERS = [
    ("EuropePMC", search_europe_pmc),
    ("NCBI_PubMed", search_ncbi_pubmed),
    ("OpenAlex", search_openalex),
]


REF_PROVIDERS = [
    ("EuropePMC", lambda art: get_references_europe_pmc.invoke({"pmid": art["pmid"]})),
    (
        "NCBI_PubMed",
        lambda art: get_references_ncbi_pubmed.invoke({"pmid": art["pmid"]}),
    ),
    (
        "OpenAlex",
        lambda art: get_references_openalex.invoke(
            {"pmid": art["pmid"], "doi": art.get("doi")}
        ),
    ),
]


def node_fetch_refs(state: BaseLibraryState) -> dict:
    """Get articles from current library and
    extend it using cited references"""

    # --- Step 1 : Get articles from actual librry ---

    return {}


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


def node_filter_existing_articles(state: BaseLibraryState) -> dict:
    """Filter existing articles in FetchState["raw_candidates"]
    and return only non existing articles.
    Modify state 'new_articles' list and re-init 'raw_candidates' one.
    """

    # --- Load JSON database ---
    # index.json -> saved articles
    index = _load_json_database(INDEX_PATH)
    history = _load_json_database(HISTORY_PATH)

    # --- Create new_items dict ---
    new_items = []
    for art in state["raw_candidates"]:
        if art["pmid"] not in index and art["pmid"] not in history:
            art["status"] = "pending_parsing"
            new_items.append(art)
    log.filter(
        f"Keeping {len(new_items)} articles from {len(state['raw_candidates'])} raw candidates"
    )
    return {"new_articles": new_items, "raw_candidates": []}


def node_read_articles(state: BaseLibraryState) -> dict:
    """Read all articles using Ollama model to retrieve
    methods, keywords and related articles"""

    log.read(f"Starting reading {len(state['new_articles'])} articles...")

    accepted_articles = []
    rejected_articles = []
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
            else:
                art["evaluation"] = eval.model_dump()
                art["status"] = "rejected"
                rejected_articles.append(art)

    return {"new_articles": accepted_articles, "rejected_articles": rejected_articles}


def node_save_index(state: BaseLibraryState) -> dict:
    """
    Save new_articles into index.json database
    & puh 'rejected_articles' into history.json to prevent
    future parsings
    """

    # --- Load JSON database ---
    index = _load_json_database(INDEX_PATH)
    history = _load_json_database(HISTORY_PATH)

    # --- Save articles ---
    for art in state["new_articles"]:
        index[art["pmid"]] = art

    for art in state["rejected_articles"]:
        history[art["pmid"]] = art

    INDEX_PATH.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    log.index(f"Saved {len(index)} accepted articles in {INDEX_PATH}")
    log.index(f"Saved {len(history)} rejected articles in {HISTORY_PATH}")
    return {}


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
