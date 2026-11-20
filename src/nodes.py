# ==========================================================
#                   Nodes
# ==========================================================

import json

from src.config import CONTEXT, DATA_DIR, INDEX_PATH
from src.state import FetchState
from src.tools import (
    build_anchored_queries,
    download_pmc_assets,
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
    print("-------------------------")
    print(f"[Search] Searching for iter {state['n_iter']}...")

    query = state["next_queries"][0]
    remaining_queries = state["next_queries"][1:]  # Pas de del sur le state !

    results = []
    for provider_name, search_tool in SEARCH_PROVIDERS:
        try:
            results = search_tool.invoke(
                {"query": query, "max_results": state["max_results"]}
            )
            print(
                f"[Search] ({provider_name}) Found {len(results)} articles using {query}"
            )
            break  # Succès -> on sort de la boucle de fallback
        except Exception as exc:
            print(
                f"[Search] ({provider_name}) Failed ({type(exc).__name__}), trying next provider..."
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
    print(
        f"[Filter] Keeping {len(new_items)} articles from {len(state['raw_candidates'])} raw candidates"
    )
    return {"new_articles": new_items, "raw_candidates": []}


def node_read_articles(state: FetchState) -> dict:
    """Read all articles using Ollama model to retrieve
    methods, keywords and related articles"""
    print(f"[Read] Starting reading {len(state['new_articles'])} articles...")
    accepted_articles = []
    # Call model for all pending_parsing articles
    total = len(state["new_articles"])
    cpt = 1
    for art in state["new_articles"]:
        if art["status"] == "pending_parsing":
            # Build article str
            article_str = f"""title : {art["title"]}, year : {art["year"]}, abtract : {art["abstract"]}"""
            print(f"[Read] Reading article {cpt}/{total} --- {art['doi']}...")
            # Call the tool
            eval = parse_article(CONTEXT, article_str)
            if eval.score >= 3:
                # Append the eval to the article
                art["evaluation"] = eval.model_dump()
                # Append the article to saved ones
                accepted_articles.append(art)
                art["status"] = "parsed"
                print("[Read] Accepted !")
            else:
                print("[Read] Rejected !")
            cpt += 1
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
    print(f"[Index] Saved ({len(index)} articles in {INDEX_PATH})")
    return {}


def node_build_queries(state: FetchState) -> dict:
    """Build new queries from articles parsing using
    extracted keytwords"""
    print("[Query] Building queries...")

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
    print(f"[DEBUG] Keywords : {sorted_kw}")
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
            print(
                f"[Download] {art['pmid']} -> PDF: {bool(art['pdf_path'])} | XML: {bool(art['xml_path'])}"
            )
        else:
            art["status"] = "no_content"
            print(f"[Download] Unable to download assets for {art['pmid']}")

        updated.append(art)

    return {"new_articles": updated}


# --- CONDITIONNAL NODES -------------------------------


def route_after_filter(state: FetchState) -> str:
    """Decide to continue download of not"""
    if len(state["new_articles"]) == 0:
        # Stop downloading
        print("[Stop] No new articles to download.")
        return "end"
    return "read"


def route_after_indexing(state: FetchState) -> str:
    """Decide to query new articles or not"""
    if state["n_iter"] == state["max_iter"]:
        print("[Stop] max_iter reached")
        return "end"
    return "build_queries"


def route_after_building_queries(state: FetchState) -> str:
    """Decide to restart querying of not accroding
    to the query number"""
    if len(state["next_queries"]) == 0:
        print("[Stop] No queries in the stack. Stopping...")
        return "end"
    else:
        print(
            f"[Continue] Restart query for iter {state['n_iter']}/{state['max_iter']}..."
        )
        return "query"
