# Operon — System Architecture (`library` Module)

## 1. Architectural Overview

Operon is designed as a **decoupled, multi-stage research pipeline**. Rather than relying on monolithic cloud APIs or downloading gigabytes of irrelevant PDFs upfront, the `library` module separates **lightweight metadata exploration** from **heavy full-text ingestion**.

Core design principles:

1. **Local-First Inference:** All semantic filtering and query planning run locally via Ollama (`ChatOllama`) under strict memory (`num_ctx`) and latency (`timeout`) constraints.
2. **Metadata-Before-Assets:** Abstracts are scored (`0–5`) and filtered *before* triggering PDF/XML downloads.
3. **Flat Cyclic State Machine:** Bibliographic exploration is modeled as a single-level **LangGraph `StateGraph`** operating in iterative search waves rather than recursive per-article sub-loops.
4. **Provider Fault Tolerance:** External scientific APIs are abstracted behind uniform `ArticleMeta` schemas with sequential fallback (`Europe PMC -> NCBI PubMed -> OpenAlex`).

```text
operon/
├── main.py                 # LangGraph state graph assembly & execution entry point
├── data/                   # Persistent local storage (ignored by Git)
│   ├── index.json          # Curated metadata & LLM evaluations keyed by PMID
│   ├── pdf/                # Downloaded Open Access full-text PDFs
│   └── xml/                # Downloaded JATS XML articles
└── src/
    ├── config.py           # Paths, HTTP headers, and domain research context
    ├── state.py            # TypedDict FetchState & Pydantic schemas (ArticleMeta, ArticleEvaluation)
    ├── models.py           # Local Ollama ChatOllama client configuration
    ├── tools.py            # Search APIs (Europe PMC, NCBI, OpenAlex), LLM parser, query builder, asset downloader
    └── nodes.py            # Deterministic LangGraph nodes & conditional routing functions
```

---

## 2. State Management (`src/state.py`)

### Graph State (`FetchState`)

`FetchState` is an immutable `TypedDict` passed across nodes. Each node returns partial dictionary updates rather than mutating state lists in place:

* `max_results` (`int`): Maximum candidates fetched per provider query.
* `next_queries` (`list[str]`): FIFO queue of pending Boolean search queries.
* `seen_queries` (`list[str]`): History of executed queries used to prevent duplicate API calls.
* `raw_candidates` (`list[dict]`): Transient buffer holding raw `ArticleMeta` dicts from the current search wave.
* `new_articles` (`list[dict]`): Filtered candidates currently undergoing evaluation and indexing.
* `n_iter` (`int`) / `max_iter` (`int`): Wave counters bounding graph execution.

### Domain Schemas (Pydantic v2)

* **`ArticleMeta`**: Canonical representation of a scientific paper (`pmid`, `pmcid`, `doi`, `title`, `year`, `abstract`, `status`, `pdf_path`, `xml_path`, `evaluation`).
* **`ArticleEvaluation`**: Structured LLM output schema. Fields are intentionally ordered **`reasoning` -> `keywords` -> `score`** so small local models (3B–4B) articulate domain relevance *before* committing to an integer score (`0–5`).
* **`QueryBatch`**: Structured output schema used when delegating Boolean query synthesis to the LLM.

---

## 3. Control Flow & LangGraph Topology (`main.py` & `src/nodes.py`)

```text
┌──────────────────────────────────────────┐
                       ▼                                          │
[START] ──► (search) ──► (filter) ──[has new]──► (read) ──► (save_index)
                            │                                     │
                      [0 new articles]                      [n_iter < max_iter]
                            │                                     ▼
                            ▼                             (generate_queries)
                          [END] ◄──[no queries left]──────────────┘
```

### Nodes

1. **`search` (`node_search`)**: Pops `next_queries[0]`, queries scientific providers with automatic fallback, populates `raw_candidates`, and increments `n_iter`.
2. **`filter` (`node_filter_existing_articles`)**: Loads `data/index.json` and discards any candidate whose `pmid` is already indexed, flushing `raw_candidates` into `new_articles`.
3. **`read` (`node_read_articles`)**: Invokes `parse_article()` on each candidate in `new_articles`. Articles scoring `>= 3` have their serialized `ArticleEvaluation` attached and are kept; lower-scoring articles (e.g., non-human ecology, veterinary studies) are dropped.
4. **`save_index` (`node_save_index`)**: Upserts accepted `ArticleMeta` records into `data/index.json` keyed by `pmid`.
5. **`generate_queries` (`node_build_queries`)**: Synthesizes new geographically anchored Boolean queries from the top-scoring articles/keywords of the current wave, deduplicating against `seen_queries`.

### Conditional Routers

* **`route_after_filter`**: Short-circuits to `END` if `new_articles` is empty, avoiding wasted LLM inference cycles.
* **`route_after_indexing`**: Terminates at `END` once `n_iter >= max_iter`, otherwise transitions to `generate_queries`.
* **`route_after_queries`**: Guards against empty query queues (`len(next_queries) == 0`) before looping back to `search`.

---

## 4. External Data Providers (`src/tools.py`)

All search tools normalize heterogeneous API payloads into `ArticleMeta.model_dump()`:

| Priority | Provider | Endpoint / Mechanism | Notes |
| :--- | :--- | :--- | :--- |
| 1 | **Europe PMC** | `/europepmc/webservices/rest/search` (`resultType=core`) | Primary source; supports field tags (`TITLE:`, `ABSTRACT:`) and `OPEN_ACCESS:Y`. |
| 2 | **NCBI PubMed** | `esearch.fcgi` + `efetch.fcgi` (XML) | Fallback on HTTP 503 / timeout; parses JATS/PubMed XML via `xml.etree.ElementTree`. |
| 3 | **OpenAlex** | `https://api.openalex.org/works` (`filter=is_oa:true`) | High-availability fallback; reconstructs full abstracts from inverted word indices. |

Full-text retrieval (`download_pmc_assets`) is implemented as a standalone tool targeting Europe PMC (`fullTextPDF` / `fullTextXML`) with an **Unpaywall API** fallback via DOI.

---

## 5. Integration into the Global Operon System

Within the broader Operon architecture, `data/index.json` and `data/xml/` act as the **clean interface boundary** between the `library` module and downstream reasoning agents:

1. **Module 1 (`library` — Current):** Queries biomedical APIs, executes the LangGraph semantic filtering and query expansion loop, and persists curated metadata and raw assets to `data/index.json` and `data/xml/`.
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
