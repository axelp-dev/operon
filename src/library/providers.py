"""
Web searching providers
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from langchain_core.tools import tool

from src.config import HEADERS
from src.library.state import ArticleMeta
from src.logger import log

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


# --- REFERENCES FETCH -------------------------------

REF_PROVIDERS = [
    (
        "OpenAlex",
        lambda art: get_references_openalex.invoke({"pmid": art.pmid, "doi": art.doi}),
    ),
    ("NCBI_PubMed", lambda art: get_references_ncbi_pubmed.invoke({"pmid": art.pmid})),
    ("EuropePMC", lambda art: get_references_europe_pmc.invoke({"pmid": art.pmid})),
]


@tool
def get_references_europe_pmc(pmid: str, max_refs: int = 100) -> list[str]:
    """Fetch cited PMIDs for a given article from Europe PMC."""
    if not pmid.isdigit():
        return []
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/MED/{pmid}/references"
    params = {"page": 1, "pageSize": max_refs, "format": "json"}
    resp = httpx.get(url, params=params, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()

    refs = []
    for item in resp.json().get("referenceList", {}).get("reference", []):
        ref_pmid = item.get("id")
        if ref_pmid and str(ref_pmid).isdigit():
            refs.append(str(ref_pmid))
    return refs


@tool
def get_references_ncbi_pubmed(pmid: str) -> list[str]:
    """Fetch cited PMIDs for a given article via NCBI E-utilities (elink)."""
    if not pmid.isdigit():
        return []
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    params = {
        "dbfrom": "pubmed",
        "db": "pubmed",
        "linkname": "pubmed_pubmed_refs",
        "id": pmid,
        "retmode": "json",
    }
    resp = httpx.get(url, params=params, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()

    linksets = resp.json().get("linksets", [])
    if not linksets:
        return []
    for linksetdb in linksets[0].get("linksetdbs", []):
        if linksetdb.get("linkname") == "pubmed_pubmed_refs":
            return [str(uid) for uid in linksetdb.get("links", [])]
    return []


@tool
def get_references_openalex(pmid: str, doi: str | None = None) -> list[str]:
    """Fetch cited OpenAlex Work IDs (W...) using DOI or PMID fallback."""
    identifier = f"https://doi.org/{doi}" if doi else f"pmid:{pmid}"
    url = f"https://api.openalex.org/works/{identifier}"
    params = {"select": "referenced_works", "mailto": "contact@operon.local"}
    resp = httpx.get(url, params=params, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()

    raw_urls = resp.json().get("referenced_works", [])
    # Transforme "https://openalex.org/W2741809807" en "W2741809807"
    return [u.rstrip("/").split("/")[-1] for u in raw_urls if u]


def fetch_article_references(article: ArticleMeta) -> list[str]:
    """
    Get IDs from cited articles cited by an ArticleMeta object
    using sequential fallback (EuropePMC -> NCBI_PubMed -> OpenAlex).
    """
    for provider_name, fetcher in REF_PROVIDERS:
        try:
            refs = fetcher(article)
            if refs:
                log.debug(
                    "SNOWBALL", f"({provider_name}) {article.pmid} -> {len(refs)} refs"
                )
                return refs
        except Exception as exc:
            log.warn(
                f"({provider_name}) Failed refs for {article.pmid} ({type(exc).__name__})"
            )

    return []


def fetch_references_batch_openalex(
    articles: list[ArticleMeta],
) -> dict[str, list[str]]:
    """
    Récupère les références sortantes (IDs OpenAlex W...) de toute une liste
    d'articles en 1 seul appel HTTP batch via DOI (ou PMID en fallback).
    Retourne {article.pmid: ["W...", "W...", ...]}.
    """
    if not articles:
        return {}

    # Mapping pour rattacher chaque réponse OpenAlex à l'article d'origine
    doi_to_pmid = {art.doi.lower().strip(): art.pmid for art in articles if art.doi}
    pmid_set = {art.pmid for art in articles if art.pmid.isdigit()}

    results: dict[str, list[str]] = {art.pmid: [] for art in articles}

    # 1. Batch par DOI (couvre >95% des articles)
    if doi_to_pmid:
        dois_filter = "|".join(
            f"https://doi.org/{d}" for d in list(doi_to_pmid.keys())[:50]
        )
        url = "https://api.openalex.org/works"
        params = {
            "filter": f"doi:{dois_filter}",
            "select": "doi,referenced_works",
            "per-page": 50,
            "mailto": "contact@operon.local",
        }
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=20.0)
        resp.raise_for_status()

        for work in resp.json().get("results", []):
            raw_doi = (
                (work.get("doi") or "").replace("https://doi.org/", "").lower().strip()
            )
            owner_pmid = doi_to_pmid.get(raw_doi)
            if owner_pmid:
                results[owner_pmid] = [
                    u.rstrip("/").split("/")[-1]
                    for u in work.get("referenced_works", [])
                    if u
                ]

    # 2. Batch par PMID pour les articles restants sans DOI (ou non trouvés via DOI)
    missing_pmids = [p for p in pmid_set if not results.get(p)]
    if missing_pmids:
        pmids_filter = "|".join(missing_pmids[:50])
        url = "https://api.openalex.org/works"
        params = {
            "filter": f"pmid:{pmids_filter}",
            "select": "ids,referenced_works",
            "per-page": 50,
            "mailto": "contact@operon.local",
        }
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=20.0)
        resp.raise_for_status()

        for work in resp.json().get("results", []):
            raw_pmid = (
                (work.get("ids", {}).get("pmid") or "").rstrip("/").split("/")[-1]
            )
            if raw_pmid in results:
                results[raw_pmid] = [
                    u.rstrip("/").split("/")[-1]
                    for u in work.get("referenced_works", [])
                    if u
                ]

    return results


def fetch_articles_by_ids(ref_ids: list[str]) -> list[dict]:
    """
    Hydrate une liste mixte d'IDs OpenAlex ('W...') et de PMIDs numériques ('12345678')
    en métadonnées ArticleMeta sérialisées (list[dict]).
    """
    if not ref_ids:
        return []

    openalex_ids = [rid.strip() for rid in ref_ids if rid.startswith("W")]
    pmids = [rid.strip() for rid in ref_ids if rid.isdigit()]

    articles: list[dict] = []
    seen_ids: set[str] = set()

    def _parse_openalex_results(items: list[dict]) -> None:
        for item in items:
            ids = item.get("ids", {})
            raw_pmid = ids.get("pmid", "")
            pmid = raw_pmid.rstrip("/").split("/")[-1] if raw_pmid else None
            article_id = pmid or item.get("id", "").split("/")[-1]

            if not article_id or article_id in seen_ids:
                continue
            seen_ids.add(article_id)

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

    # 1. Batch par OpenAlex ID (W...)
    for i in range(0, len(openalex_ids), 50):
        chunk = "|".join(openalex_ids[i : i + 50])
        resp = httpx.get(
            "https://api.openalex.org/works",
            params={
                "filter": f"openalex:{chunk}",
                "per-page": 50,
                "mailto": "contact@operon.local",
            },
            headers=HEADERS,
            timeout=20.0,
        )
        resp.raise_for_status()
        _parse_openalex_results(resp.json().get("results", []))

    # 2. Batch par PMID numérique (si fallback NCBI/EuropePMC déclenché)
    for i in range(0, len(pmids), 50):
        chunk = "|".join(pmids[i : i + 50])
        resp = httpx.get(
            "https://api.openalex.org/works",
            params={
                "filter": f"pmid:{chunk}",
                "per-page": 50,
                "mailto": "contact@operon.local",
            },
            headers=HEADERS,
            timeout=20.0,
        )
        resp.raise_for_status()
        _parse_openalex_results(resp.json().get("results", []))

    return articles
