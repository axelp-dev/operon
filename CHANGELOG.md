# Operon Changes

## TODO


---

## Unreleased

### Added

- Wire complete `build_snowball_graph()` pipeline (`fetch_refs -> filter -> read -> save_index`) sharing ingestion nodes with `build_search_graph()`.
- Implement batch OpenAlex outbound reference extraction (`fetch_references_batch_openalex`) and mixed ID/PMID hydration (`fetch_articles_by_ids`) in `src/library/providers.py`.
- Implement `node_fetch_refs` for co-citation ranking and candidate hydration in `src/library/nodes.py`.
- Implement `get_min_scored_articles()` in `src/library/storage.py` using Pydantic `ArticleMeta.model_validate()`.
- Write benchmark plotting script using Matplotlib & PDF output from existing generated JSON benchmark file. 
- Add `matplotlib` to Python environment for benchmark plotting
- Add benchmark script for Qwen model on articles evaluation. 
- Use new `data/history.json` database for rejected articles saving. 
  - Load `history.json` while filtering articles to prevent unnecessary llm calls.
  - Save `history.json` with LLM rejected articles while indexing database. 
- `OperonLogger::reading_progres()` and `OperonLogger::article()` for fancy article readning progress display. 
- Branch LLM on query generation from extracted keywords. 
- First working LangGraph loop.
- Implements `nodes.py`, `state.py` and `tools.py` for a first LangGraph model.

### Changed

- Refactor graph states into `FetchState` and `SnowballState` inheriting from `BaseLibraryState` so ingestion nodes (`filter`, `read`, `save_index`) can be shared across independent graphs.
- Modularize `library` package (`graphs.py`, `llm_tasks.py`, `nodes.py`, `providers.py`, `state.py`, `storage.py`).

### Fixed
