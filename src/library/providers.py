"""
Web searching providers
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from langchain_core.tools import tool

from src.config import HEADERS
from src.library.state import ArticleMeta

# --- HERLPERS -------------------------------


def _reconstruct_openalex_abstract(inverted_index: dict | None) -> str:
    """Reconstruit le texte de l'abstract depuis l'index inversé OpenAlex."""
    if not inverted_index:
        return ""
    words = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words.keys()))


def _try_download_pdf(url: str, dest: Path, client: httpx.Client) -> bool:
    """Helper interne pour télécharger un flux PDF valide."""
    try:
        with client.stream("GET", url, follow_redirects=True) as resp:
            content_type = resp.headers.get("content-type", "").lower()
            if resp.status_code == 200 and "application/pdf" in content_type:
                with open(dest, "wb") as f:
                    f.writelines(resp.iter_bytes())
                return True
    except httpx.HTTPError:
        pass
    return False


# --- LANGGRAPH TOOLS -------------------------------


@tool
def search_europe_pmc(query: str, max_results: int = 10) -> list[dict]:
    """Search & query Open Access articles on Europe PMC (PubMed + PMC)."""
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": f"({query}) AND OPEN_ACCESS:Y",
        "format": "json",
        "resultType": "core",
        "pageSize": max_results,
    }
    resp = httpx.get(url, params=params, headers=HEADERS, timeout=30.0)
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


@tool
def search_ncbi_pubmed(query: str, max_results: int = 10) -> list[dict]:
    """Search Open Access articles directly on NCBI PubMed (esearch + efetch)."""
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Étape 1 : Récupérer les PMIDs (filtrés sur PMC Open Access)
    esearch_params = {
        "db": "pubmed",
        "term": f"({query}) AND pubmed pmc open access[filter]",
        "retmode": "json",
        "sort": "relevance",
        "retmax": max_results,
    }
    r_search = httpx.get(
        f"{base_url}/esearch.fcgi", params=esearch_params, headers=HEADERS, timeout=30.0
    )
    r_search.raise_for_status()
    pmids = r_search.json().get("esearchresult", {}).get("idlist", [])

    if not pmids:
        return []

    # Étape 2 : Récupérer les métadonnées complètes en XML
    efetch_params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    r_fetch = httpx.get(
        f"{base_url}/efetch.fcgi", params=efetch_params, headers=HEADERS, timeout=30.0
    )
    r_fetch.raise_for_status()

    root = ET.fromstring(r_fetch.text)
    articles = []

    for article_el in root.findall(".//PubmedArticle"):
        pmid = article_el.findtext(".//MedlineCitation/PMID")
        if not pmid:
            continue

        title_el = article_el.find(".//ArticleTitle")
        if title_el is not None:
            title = "".join(title_el.itertext())
        else:
            title = "Sans titre"

        abstract_parts = [
            "".join(ab.itertext())
            for ab in article_el.findall(".//Abstract/AbstractText")
        ]
        abstract = "\n".join(abstract_parts)

        year_str = article_el.findtext(".//Journal/JournalIssue/PubDate/Year")
        year = int(year_str) if year_str and year_str.isdigit() else None

        # Extraction DOI et PMCID depuis ArticleIdList
        doi, pmcid = None, None
        for id_el in article_el.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = id_el.attrib.get("IdType")
            if id_type == "doi":
                doi = id_el.text
            elif id_type == "pmc":
                pmcid = id_el.text

        articles.append(
            ArticleMeta(
                pmid=str(pmid),
                pmcid=pmcid,
                doi=doi,
                title=title,
                year=year,
                abstract=abstract,
            ).model_dump()
        )

    return articles


@tool
def search_openalex(query: str, max_results: int = 10) -> list[dict]:
    """Search Open Access scientific articles via OpenAlex API."""
    # Nettoyage basique des tags spécifiques Europe PMC (TITLE:, ABSTRACT:) pour OpenAlex
    clean_query = query.replace("TITLE:", "").replace("ABSTRACT:", "")

    url = "https://api.openalex.org/works"
    params = {
        "search": clean_query,
        "filter": "is_oa:true,has_abstract:true",
        "per-page": max_results,
        "mailto": "contact@operon.local",  # Donne accès au "polite pool" ultra-rapide
    }
    resp = httpx.get(url, params=params, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()

    articles = []
    for item in resp.json().get("results", []):
        ids = item.get("ids", {})
        # OpenAlex renvoie le PMID sous forme d'URL "https://pubmed.ncbi.nlm.nih.gov/12345678"
        raw_pmid = ids.get("pmid", "")
        pmid = raw_pmid.rstrip("/").split("/")[-1] if raw_pmid else None

        # Fallback sur l'ID OpenAlex (ex: W2741809807) si l'article n'est pas indexé sur PubMed
        article_id = pmid or item.get("id", "").split("/")[-1]
        if not article_id:
            continue

        raw_pmcid = ids.get("pmcid", "")
        pmcid = raw_pmcid.rstrip("/").split("/")[-1] if raw_pmcid else None

        raw_doi = item.get("doi", "")
        doi = raw_doi.replace("https://doi.org/", "") if raw_doi else None

        articles.append(
            ArticleMeta(
                pmid=str(article_id),
                pmcid=pmcid,
                doi=doi,
                title=item.get("title") or "Sans titre",
                year=item.get("publication_year"),
                abstract=_reconstruct_openalex_abstract(
                    item.get("abstract_inverted_index")
                ),
            ).model_dump()
        )

    return articles


@tool
def download_pmc_assets(
    pmid: str,
    pmcid: str,
    PDF_DIR: Path,
    XML_DIR: Path,
    HEADERS: dict,
    doi: str | None = None,
) -> dict:
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
