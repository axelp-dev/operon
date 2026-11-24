# Operon

**Operon** is an open-source, modular muti-agent LangGtaph based system to automate scientific litterature research and experimental methodology testing. 

> **Current Development Scope (`library` branch):**  
> This repository currently implements the **Bibliographic Discovery & Curation Engine** (`library` module)—an autonomous LangGraph pipeline that queries biomedical repositories, filters out off-topic organisms via local LLMs, extracts domain-specific keywords, iteratively expands Boolean queries, and builds a structured local knowledge base (`data/index.json`).

## Key Features (Library Module)

* **Multi-Provider Resilient Search:** Queries **Europe PMC**, **NCBI PubMed (E-utilities)**, and **OpenAlex** with automatic failover against HTTP `503` errors and network timeouts.
* **Local-First Semantic Evaluation:** Uses local Ollama models (`qwen2.5:3b` / `qwen3:4b`) with Pydantic structured outputs (`ArticleEvaluation`) to score abstracts (`0–5`) and reject non-human or off-topic studies before downloading heavy full-text files.
* **Dynnamic Query Generation**: Generates new queries for web search using parsed keywords and LLM calls. 
* **Zero-Duplication Indexing:** Deduplicates candidates against both session query history (`seen_queries`), persistent PMID storage (`data/index.json`).
* **Deferred Asset Retrieval:** Supports downloading Open Access PDF and JATS XML full-text files (`PMID_<id>.pdf` / `PMID_<id>.xml`) with Unpaywall fallback once articles pass semantic screening.

## Project Structure

```text
.
├── CHANGELOG.md
├── data
│   └── index.json
├── dev
│   └── dev_models.py
├── main.py
├── README.md
├── requirements.txt
└── src
    ├── config.py
    ├── edges.py
    ├── models.py
    ├── nodes.py
    ├── state.py
    └── tools.py
```

## Prerequisites & Setup

* Python 3.12+ and a local Ollama instance running on macOS or Linux.
* Pull a lightweight local model calibrated for structured JSON output:

```bash
ollama pull qwen2.5:3b
```

* Create and activate the virtual environment, then install dependencies:

```bash
python -m venv .venv 
source .venv/bin/activate 
pip install -r requirements.txt
```

## Usage

Configure your seed query, iteration budget (`max_iter`), and batch size (`max_results`) in `main.py`, then run:

```bash
python main.py
```

Curated articles, evaluation scores, reasoning, and extracted keywords are incrementally saved to `data/index.json`.
