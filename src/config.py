from pathlib import Path

# --- ENVIRONMENT ------------------------------

DATA_DIR = Path("data")
PDF_DIR = DATA_DIR / "pdf"
XML_DIR = DATA_DIR / "xml"
INDEX_PATH = DATA_DIR / "index.json"

HEADERS = {"User-Agent": "OperonBiblioBot/0.1 (mailto:contact@operon.local)"}

CONTEXT = """
You are evaluating scientific abstracts for a research project on human population genetics and the genetic origins of Madagascar (Austronesian and Bantu admixture, Indian Ocean migrations, human population genomics methods).

Rate the relevance of each article from 0 to 5 using these calibration examples:
- Score 5: "Genome-wide analysis of Malagasy populations reveals Austronesian and Bantu admixture" -> Human population genetics of Madagascar.
- Score 4: "Population genomics of Austronesian expansion across Island Southeast Asia and the Indian Ocean" -> Regional human migration/admixture directly linked to Madagascar.
- Score 3: "Inferring complex admixture history using haplotype-sharing and f-statistics in human cohorts" -> Population genomics methods applicable to human ancestry.
- Score 0: "Phylogeography of Malagasy frogs / lemurs / malaria parasites / livestock" -> Non-human organisms, ecology, or clinical medicine.

Extract 3 to 5 concise English scientific keywords if score >= 3.
"""
