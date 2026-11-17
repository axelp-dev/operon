import json
from os import dup2
from pathlib import Path
from langchain_core.tools import tool
from typing import TypedDict, Literal
import httpx
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END

# --- ENVIRONMENT ------------------------------

DATA_DIR = Path("data")
PDF_DIR = DATA_DIR / "pdf"
XML_DIR = DATA_DIR / "xml"
INDEX_PATH = DATA_DIR / "index.json"

HEADERS = {"User-Agent": "OperonBiblioBot/0.1 (mailto:contact@operon.local)"}


# --- STATES ------------------------------
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


# --- TOOLS -------------------------------


@tool
def parse_article(query: str, limit: int) -> None:
    """Parse PDF downloaded article and apped it to
    the database"""
    raise NotImplementedError()


@tool
def search_europe_pmc(query: str, max_results: int = 10) -> list[dict]:
    """Search & query Open Access articles on Europe PMC (PubMed + PMC)."""
    # Definind general query url
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": f"({query}) AND OPEN_ACCESS:Y",
        "format": "json",
        "resultType": "core",
        "pageSize": max_results,
    }
    # Asking for the query
    resp = httpx.get(url, params=params, timeout=15.0)
    resp.raise_for_status()

    articles = []
    for item in resp.json().get("resultList", {}).get("result", []):
        pmid = item.get("pmid")
        if not pmid:
            continue
        articles.append(
            ArticleMeta(
                pmid=str(pmid),
                pmcid=item.get("pmcid"),
                doi=item.get("doi"),
                title=item.get("title", "Sans titre"),
                year=int(item["pubYear"]) if item.get("pubYear") else None,
                abstract=item.get("abstractText", ""),
            ).model_dump()
        )
    return articles


def _try_download_pdf(url: str, dest: Path, client: httpx.Client) -> bool:
    """Helper interne pour télécharger un flux PDF valide."""
    try:
        with client.stream("GET", url, follow_redirects=True) as resp:
            content_type = resp.headers.get("content-type", "").lower()
            if resp.status_code == 200 and "application/pdf" in content_type:
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
                return True
    except httpx.HTTPError:
        pass
    return False


@tool
def download_pmc_assets(pmid: str, pmcid: str, doi: str | None = None) -> dict:
    """Download both fullTextPDF (with Unpaywall fallback) and fullTextXML for a PMC article."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    XML_DIR.mkdir(parents=True, exist_ok=True)

    pdf_dest = PDF_DIR / f"PMID_{pmid}.pdf"
    xml_dest = XML_DIR / f"PMID_{pmid}.xml"

    saved_pdf: str | None = str(pdf_dest) if pdf_dest.exists() else None
    saved_xml: str | None = str(xml_dest) if xml_dest.exists() else None

    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
        # Download PDF article (Europe PMC REST -> fallback Unpaywall)
        if not saved_pdf:
            ebi_pdf_url = (
                f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextPDF"
            )
            if _try_download_pdf(ebi_pdf_url, pdf_dest, client):
                saved_pdf = str(pdf_dest)
            elif doi:
                # Fallback on Unpaywall
                try:
                    upw_url = (
                        f"https://api.unpaywall.org/v2/{doi}?email=contact@operon.local"
                    )
                    upw_resp = client.get(upw_url)
                    if upw_resp.status_code == 200:
                        best_oa = upw_resp.json().get("best_oa_location") or {}
                        pdf_url = best_oa.get("url_for_pdf")
                        if pdf_url and _try_download_pdf(pdf_url, pdf_dest, client):
                            saved_pdf = str(pdf_dest)
                except httpx.HTTPError:
                    pass

        # Download XML (Europe PMC REST)
        if not saved_xml:
            ebi_xml_url = (
                f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
            )
            try:
                xml_resp = client.get(ebi_xml_url, follow_redirects=True)
                if xml_resp.status_code == 200 and "<article" in xml_resp.text:
                    xml_dest.write_text(xml_resp.text, encoding="utf-8")
                    saved_xml = str(xml_dest)
            except httpx.HTTPError:
                pass

    return {"pdf_path": saved_pdf, "xml_path": saved_xml}


# --- NODES -------------------------------


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


# --- BUILD GRAPH -------------------------------


builder = StateGraph(FetchState)

# Nodes
builder.add_node("search", node_search)
builder.add_node("filter", node_filter_existing_articles)
builder.add_node("download", node_download)
builder.add_node("save_index", node_save_index)

# Edges
builder.add_edge(START, "search")
builder.add_edge("search", "filter")

# Condition to continue
builder.add_conditional_edges(
    "filter",
    route_after_filter,
    {"download": "download", "end": END},
)
builder.add_edge("download", "save_index")
builder.add_edge("save_index", END)

fetch_graph = builder.compile()


if __name__ == "__main__":
    fetch_graph.invoke(
        {
            "query": "Madagascar Genomic Population Origin",
            "max_results": 5,
            "raw_candidates": [],
            "new_articles": [],
        }
    )
