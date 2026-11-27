# Operon — System Architecture (`library` Module)

## 1. Architectural Overview

Operon is designed as a **decoupled, multi-stage research pipeline**. Rather than relying on monolithic cloud APIs or downloading gigabytes of irrelevant PDFs upfront, the `library` module separates **lightweight metadata exploration** from **heavy full-text ingestion**.

Core design principles:

1. **Local-First Inference:** All semantic filtering and query planning run locally via Ollama (`ChatOllama`).
2. **Metadata-Before-Assets:** Abstracts are scored (`0–5`) and filtered *before* triggering PDF/XML downloads.
3. **Dual-Topology State Machines:** Bibliographic discovery is split into two independent LangGraph workflows (`build_search_graph()` for cyclic Boolean query exploration and `build_snowball_graph()` for linear co-citation expansion) sharing a common ingestion pipeline (`filter -> read -> save_index`).
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
├── main.py               # Entrypoint 
├── README.md
├── requirements.txt
└── src
    ├── __init__.py
    ├── config.py         # Graphs & model config 
    ├── library
    │   ├── graphs.py     # Graphs builders 
    │   ├── llm_tasks.py  # LLM callers 
    │   ├── nodes.py      # LangGraph nodes definitions
    │   ├── providers.py  # Web search providers 
    │   ├── state.py      # States & Classes definitions
    │   └── storage.py    # BD interractions
    ├── logger.py         # CLI logger 
    └── models.py         # LLM models definotions
```

### Transverse Modules (`src/`)

Despite a strict & modular architecture, some modules are stored dorectly in `str/` folders because their define more global configs: 
- **`src/config.py`**: Centralizes filesystem paths (`DATA_DIR`, `INDEX_PATH`, `HISTORY_PATH`), HTTP `HEADERS`, and the research `CONTEXT` prompt.
- **`src/models.py`**: Configures local `ChatOllama` model instances (`qwen_llm`, `qwen_llm_25`) with bounded context windows (`num_ctx`) and timeouts.
- **`src/logger.py`**: Provides a singleton `OperonLogger` (`log`) with scope-aligned ANSI console formatting (`SEARCH`, `FILTER`, `READ`, `INDEX`, `QUERY`, `WARN`, `INFO`), single-line progress updates (`\r`) during LLM evaluation, and full `DEBUG`-level file logging (`data/operon.log`).

## 2. State Management (`src/library/state.py`)

LangGraph & LangChain library build pipeline graphs using states objects which defines the current state of the graph. Each node can modify the current state by returning a dictionnary of changes. 

Here are presented the used states in the `library` module and their attributes. 

### Graph States (`BaseLibraryState`, `FetchState`, `SnowballState`)

All graph states are immutable `TypedDict` schemas inheriting from a shared `BaseLibraryState` so core ingestion nodes can be reused across independent pipelines without state conversion:

- **`BaseLibraryState` (Shared Ingestion Buffers):**
  - `raw_candidates` (`list[dict]`): Transient buffer holding raw `ArticleMeta` dicts fetched during the current step.
  - `new_articles` (`list[dict]`): Deduplicated candidates undergoing LLM evaluation and indexing.
  - `rejected_articles` (`list[dict]`): Transient buffer of articles rejected (`score < 3`) before persistence to `data/history.json`.
- **`FetchState(BaseLibraryState)` (`build_search_graph`):**
  - `max_results` (`int`): Maximum candidates fetched per provider query.
  - `next_queries` (`list[str]`): FIFO queue of pending Boolean search queries.
  - `seen_queries` (`list[str]`): History of executed queries preventing duplicate API calls within a session.
  - `n_iter` (`int`) / `max_iter` (`int`): Wave counters bounding cyclic graph execution.
- **`SnowballState(BaseLibraryState)` (`build_snowball_graph`):**
  - `min_score` (`int`): Minimum evaluation score required for an existing `data/index.json` article to act as a snowball seed.
  - `min_refs` (`int`): Minimum co-citation count across seed articles required for a cited reference to be hydrated.
  - `max_selected` (`int`): Maximum number of seed articles selected and top co-cited references hydrated per snowball pass.

### Domain Schemas

- **`ArticleMeta`**: Canonical representation of a scientific paper (`pmid`, `pmcid`, `doi`, `title`, `year`, `abstract`, outbound citation `references`, `refs_explored` flag, `pdf_path`, `xml_path`, `evaluation`, and pipeline `status` tracking lifecycle transitions from `pending_filtering` / `pending_parsing` to `accepted_pending_download`, `rejected`, `no_content`, or `pending_parse`).
- **`ArticleEvaluation`**: Structured LLM output schema. Fields are intentionally ordered **`reasoning` -> `keywords` -> `score`** so small local models (3B–4B) articulate domain relevance *before* committing to an integer score (`0–5`).
- **`QueryBatch`**: Structured output schema used when delegating Boolean query synthesis to the LLM.

## 3. Control Flow & LangGraph Topology (`src/library/graphs.py` & `src/library/nodes.py`)

The `library` module exposes two independent compiled graphs in `src/library/graphs.py` that share the downstream `filter -> read -> save_index` nodes:

1. **Search Graph (`build_search_graph`):** A cyclic state machine iterating across Boolean query waves until `max_iter` is reached or `next_queries` is exhausted.
2. **Snowball Graph (`build_snowball_graph`):** A linear backward-citation expansion pipeline (`START -> fetch_refs -> filter -> read -> save_index -> END`) that mines outbound references from top-scored articles in `data/index.json`, retains co-cited foundational works, and feeds them into the standard curation pipeline.



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
7. **`fetch_refs` (`node_fetch_refs`)**: Loads top-scoring seed articles (`score >= min_score`, capped at `max_selected`) from `data/index.json` via `get_min_scored_articles()`, retrieves their outbound cited references in batch (`fetch_references_batch_openalex` with `fetch_article_references` fallback), ranks references by co-citation frequency (`>= min_refs`), and hydrates the top candidates into `raw_candidates` via `fetch_articles_by_ids()`.

## 4. External Data Providers (`src/library/providers.py`)

All search tools normalize heterogeneous API payloads into `ArticleMeta.model_dump()`:

| Priority | Provider | Endpoint / Mechanism | Notes |
| :--- | :--- | :--- | :--- |
| 1 | **Europe PMC** | `/europepmc/webservices/rest/search` (`resultType=core`) | Primary source; supports field tags (`TITLE:`, `ABSTRACT:`) and `OPEN_ACCESS:Y`. |
| 2 | **NCBI PubMed** | `esearch.fcgi` + `efetch.fcgi` (XML) | Fallback on HTTP 503 / timeout; parses JATS/PubMed XML via `xml.etree.ElementTree`. |
| 3 | **OpenAlex** | `https://api.openalex.org/works` (`filter=is_oa:true`) | High-availability fallback; reconstructs full abstracts from inverted word indices. |


Full-text retrieval (`download_pmc_assets`) is implemented as a standalone `@tool` accepting `pmid`, `pmcid`, `PDF_DIR`, `XML_DIR`, `HEADERS`, and optional `doi`, targeting Europe PMC (`fullTextPDF` / `fullTextXML`) with an **Unpaywall API** fallback via DOI.

### Citation & Hydration Endpoints (`src/library/providers.py`)

- **Batch Outbound References (`fetch_references_batch_openalex`)**: Resolves `referenced_works` (`W...` IDs) for up to 50 seed articles in a single HTTP request via DOI batching (with PMID batch fallback), falling back per-article to `OpenAlex -> NCBI PubMed (elink) -> Europe PMC (/references)`.
- **Batch Candidate Hydration (`fetch_articles_by_ids`)**: Hydrates mixed lists of OpenAlex Work IDs (`W...`) and numeric PMIDs into normalized `ArticleMeta` records ready for deduplication and LLM evaluation.

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
