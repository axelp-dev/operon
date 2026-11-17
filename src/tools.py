# ==========================================================
#                   TOOLS
# ==========================================================

from pathlib import Path
from langchain_core.tools import tool
import httpx

from main import PDF_DIR, XML_DIR, HEADERS
from src.state import ArticleMeta


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
