# Operon

**Operon** is an open-source, modular muti-agent LangGtaph based system to automate scientific litterature research and experimental methodology testing. 

> **Current Development Scope (`library` branch):**  
> This repository currently implements the **Bibliographic Discovery & Curation Engine** (`library` module)—an autonomous LangGraph pipeline that queries biomedical repositories, filters out off-topic organisms via local LLMs, extracts domain-specific keywords, iteratively expands Boolean queries, and builds a structured local knowledge base (`data/index.json`).

## Key Features (Library Module)

## Key Features (Library Module)

- **Multi-Provider Resilient Search:** Queries **Europe PMC**, **NCBI PubMed (E-utilities)**, and **OpenAlex** with automatic failover against HTTP `503` errors and network timeouts.
- **Local-First Semantic Evaluation:** Uses local Ollama models (`qwen2.5:3b` / `qwen3:4b`) with Pydantic structured outputs (`ArticleEvaluation`) to score abstracts (`0–5`) and reject non-human or off-topic studies before downloading heavy full-text files.
- **Dynamic Query Generation:** Synthesizes new broad Boolean search queries using local LLM calls grounded on top-scoring articles and extracted keywords.
- **Zero-Duplication Indexing & History:** Deduplicates candidates against session query history (`seen_queries`), persistent accepted storage (`data/index.json`), and persistent rejection cache (`data/history.json`).
- **Deferred Asset Retrieval:** Supports downloading Open Access PDF and JATS XML full-text files (`PMID_<id>.pdf` / `PMID_<id>.xml`) with Unpaywall fallback once articles pass semantic screening.
- **Structured Scoped Logging:** Provides color-coded, single-line console progress updates alongside full `DEBUG`-level execution logs in `data/operon.log`.

## Project Structure

```text
.
├── ARCHITECTURE.md
├── CHANGELOG.md
├── data
│   ├── history.json
│   ├── index.json
│   └── operon.log
├── langgraph.json
├── main.py
├── README.md
├── requirements.txt
└── src
    ├── __init__.py
    ├── config.py
    ├── library
    │   ├── graphs.py
    │   ├── llm_tasks.py
    │   ├── nodes.py
    │   ├── providers.py
    │   ├── state.py
    │   └── storage.py
    ├── logger.py
    └── models.py
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

Curated articles, evaluation scores, reasoning, and extracted keywords are incrementally saved to `data/index.json`, while rejected candidates are cached in `data/history.json` to avoid redundant LLM evaluations across runs.
