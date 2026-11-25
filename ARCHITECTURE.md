# Operon — System Architecture (`library` Module)

## 1. Architectural Overview

Operon is designed as a **decoupled, multi-stage research pipeline**. Rather than relying on monolithic cloud APIs or downloading gigabytes of irrelevant PDFs upfront, the `library` module separates **lightweight metadata exploration** from **heavy full-text ingestion**.

Core design principles:

1. **Local-First Inference:** All semantic filtering and query planning run locally via Ollama (`ChatOllama`).
2. **Metadata-Before-Assets:** Abstracts are scored (`0–5`) and filtered *before* triggering PDF/XML downloads.
3. **Flat Cyclic State Machine:** Bibliographic exploration is modeled as a single-level **LangGraph `StateGraph`** operating in iterative search waves rather than recursive per-article sub-loops.
4. **Provider Fault Tolerance:** External scientific APIs are abstracted behind uniform `ArticleMeta` schemas with sequential fallback (`Europe PMC -> NCBI PubMed -> OpenAlex`).
5. **Persistent Deduplication:** Both accepted articles (`data/index.json`) and rejected candidates (`data/history.json`) are persisted across runs to prevent redundant LLM evaluations.

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

### Transverse Modules (`src/`)

- **`src/config.py`**: Centralizes filesystem paths (`DATA_DIR`, `INDEX_PATH`, `HISTORY_PATH`), HTTP `HEADERS`, and the research `CONTEXT` prompt.
- **`src/models.py`**: Configures local `ChatOllama` model instances (`qwen_llm`, `qwen_llm_25`) with bounded context windows (`num_ctx`) and timeouts.
- **`src/logger.py`**: Provides a singleton `OperonLogger` (`log`) with scope-aligned ANSI console formatting (`SEARCH`, `FILTER`, `READ`, `INDEX`, `QUERY`, `WARN`, `INFO`), single-line progress updates (`\r`) during LLM evaluation, and full `DEBUG`-level file logging (`data/operon.log`).

## 2. State Management (`src/library/state.py`)

### Graph State (`FetchState`)

`FetchState` is an immutable `TypedDict` passed across nodes. Each node returns partial dictionary updates rather than mutating state lists in place:

- `max_results` (`int`): Maximum candidates fetched per provider query.
- `next_queries` (`list[str]`): FIFO queue of pending Boolean search queries.
- `seen_queries` (`list[str]`): History of executed queries used to prevent duplicate API calls within a session.
- `raw_candidates` (`list[dict]`): Transient buffer holding raw `ArticleMeta` dicts from the current search wave.
- `new_articles` (`list[dict]`): Filtered candidates currently undergoing evaluation and indexing.
- `rejected_articles` (`list[dict]`): Transient buffer of articles rejected (`score < 3`) during the current wave before persistence to `data/history.json`.
- `n_iter` (`int`) / `max_iter` (`int`): Wave counters bounding graph execution.

### Domain Schemas (Pydantic v2)

- **`ArticleMeta`**: Canonical representation of a scientific paper (`pmid`, `pmcid`, `doi`, `title`, `year`, `abstract`, `pdf_path`, `xml_path`, `evaluation`, and pipeline `status` tracking lifecycle transitions from `pending_filtering` / `pending_parsing` to `accepted_pending_download`, `rejected`, `no_content`, or `pending_parse`).
- **`ArticleEvaluation`**: Structured LLM output schema. Fields are intentionally ordered **`reasoning` -> `keywords` -> `score`** so small local models (3B–4B) articulate domain relevance *before* committing to an integer score (`0–5`).
- **`QueryBatch`**: Structured output schema used when delegating Boolean query synthesis to the LLM.

## 3. Control Flow & LangGraph Topology (`src/library/graphs.py` & `src/library/nodes.py`)

The `library` module executes as a cyclic LangGraph state machine (`build_search_graph()`) that iterates across query waves until `max_iter` is reached or the query queue is exhausted.

```text
[START]
   │
   ▼
(search) ◄──────────────────────────────────────────────┐
   │                                                    │
   ▼                                                    │
(filter: index.json + history.json)                     │
   │                                                    │
   ├──[0 new]──► [next_queries == 0 ?] ──(no)───────────┤
   │                   │                                │
[has new]            (yes)                              │
   │                   │                                │
   ▼                   ▼                                │
(read)               [END]                              │
   │                   ▲                                │
   ▼                   │                                │
(save: index.json + history.json)                       │
   │                   │                                │
   ▼                   │                                │
[n_iter >= max_iter ?] ──(yes)                          │
   │                   ▲                                │
  (no)                 │                                │
   │                   │                                │
   ▼                   │                                │
(build_queries: excl. history.json) ──[0 queries]───────┘
   │                                                    │
[has queries] ──────────────────────────────────────────┘
```

### Nodes (`src/library/nodes.py`)

1. **`search` (`node_search`)**: Pops `next_queries[0]`, queries scientific providers with sequential fallback, populates `raw_candidates`, appends the query to `seen_queries`, and increments `n_iter`.
2. **`filter` (`node_filter_existing_articles`)**: Loads both `data/index.json` and `data/history.json` via `src/library/storage.py` (`_load_json_database`) and discards any candidate whose `pmid` already exists in either store, flushing `raw_candidates` into `new_articles`.
3. **`read` (`node_read_articles`)**: Invokes `parse_article()` (`src/library/llm_tasks.py`) on each candidate in `new_articles`. Articles scoring `>= 3` are kept in `new_articles` (`status="accepted_pending_download"`), while lower-scoring articles are routed to `rejected_articles` (`status="rejected"`).
4. **`save_index` (`node_save_index`)**: Upserts accepted `ArticleMeta` records into `data/index.json` and rejected records into `data/history.json` keyed by `pmid`.
5. **`generate_queries` (`node_build_queries_llm`)**: Calls `generate_llm_queries()` (`src/library/llm_tasks.py`) to synthesize new broad Boolean queries (at most two `AND` clauses, no field prefixes) from top-scoring articles (`score >= 4`) while deduplicating against `seen_queries`.
6. **`download` (`node_download`)**: Standalone node invoking `download_pmc_assets` for accepted articles with a `pmcid` (implemented in `nodes.py`, decoupled from the main search loop).


## 4. External Data Providers (`src/library/providers.py`)

All search tools normalize heterogeneous API payloads into `ArticleMeta.model_dump()`:

| Priority | Provider | Endpoint / Mechanism | Notes |
| :--- | :--- | :--- | :--- |
| 1 | **Europe PMC** | `/europepmc/webservices/rest/search` (`resultType=core`) | Primary source; supports field tags (`TITLE:`, `ABSTRACT:`) and `OPEN_ACCESS:Y`. |
| 2 | **NCBI PubMed** | `esearch.fcgi` + `efetch.fcgi` (XML) | Fallback on HTTP 503 / timeout; parses JATS/PubMed XML via `xml.etree.ElementTree`. |
| 3 | **OpenAlex** | `https://api.openalex.org/works` (`filter=is_oa:true`) | High-availability fallback; reconstructs full abstracts from inverted word indices. |


Full-text retrieval (`download_pmc_assets`) is implemented as a standalone `@tool` accepting `pmid`, `pmcid`, `PDF_DIR`, `XML_DIR`, `HEADERS`, and optional `doi`, targeting Europe PMC (`fullTextPDF` / `fullTextXML`) with an **Unpaywall API** fallback via DOI.

---

## 5. Integration into the Global Operon System

Within the broader Operon architecture, `data/index.json` and `data/xml/` act as the **clean interface boundary** between the `library` module and downstream reasoning agents:

1. **Module 1 (`library` — Current):** Queries biomedical APIs, executes the LangGraph semantic filtering and query expansion loop, and persists curated metadata (`data/index.json`) and rejection history (`data/history.json`).
2. **Module 2 (`ingestion` — Planned):** Consumes `data/index.json` and parses JATS XML / PDF files into structured section-level chunks (Methods, Cohorts, Bioinformatic Tools) stored in a vector/structured database.
3. **Module 3 (`synthesis` — Planned):** Downstream reasoning agents query the ingested knowledge base to recommend statistical methods and bioinformatic pipelines for Malagasy human population genomic datasets.

```text
[Module 1: library (Current)]
  Web APIs ──► LangGraph Filter & Query Loop ──► data/index.json + data/xml/
                                                        │
[Module 2: ingestion (Planned)]                         ▼
  JATS XML / PDF Parser ──► Methods, Tools & Cohort Extraction ──► Vector / Structured Store
                                                        │
[Module 3: synthesis (Planned)]                         ▼
  Experimental Design Agents ──► Bioinformatic Workflow & Statistical Recommendations
```
