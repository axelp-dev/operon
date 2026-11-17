# ==========================================================
#                   Nodes
# ==========================================================

import json
from src.state import FetchState
from main import DATA_DIR, INDEX_PATH
from src.tools import search_europe_pmc, download_pmc_assets


def node_search(state: FetchState) -> dict:
    """
    Deterministic searching node: execute search using
    searching tool.
    - Get current graph state FetchState
    - Return added articles to modify the current state
    """
    # Invoke the searching tool
    results = search_europe_pmc.invoke(
        {"query": state["query"], "max_results": state["max_results"]}
    )
    print(f"[Search] Found {len(results)} articles using {state['query']}")
    return {"raw_candidates": results}


def node_filter_existing_articles(state: FetchState) -> dict:
    """Filter existing articles in FetchState["raw_candidates"]
    and return only non existing articles"""
    # --- Load JSON database ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_index = {}
    if INDEX_PATH.exists():
        existing_index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    # --- Create new_items dict ---
    new_items = [
        art for art in state["raw_candidates"] if art["pmid"] not in existing_index
    ]
    print(
        f"[Filter] {len(new_items)} filtered from {len(state['raw_candidates'])} raw candidates"
    )
    return {"new_articles": new_items}


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


# --- CONDITIONNAL NODES -------------------------------


def route_after_filter(state: FetchState) -> str:
    """Decide to continue download of not"""
    if len(state["new_articles"]) == 0:
        # Stop downloading
        print("[Stop] No new articles to download.")
        return "end"
    return "download"
