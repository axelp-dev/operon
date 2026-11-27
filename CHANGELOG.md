# Operon Changes

## TODO


---

## Unreleased

### Added

- Add benchmark script for Qwen model on articles evaluation. 
- Implement `node_fetch_refs` for references selection in library. 
- Implement score-fetching article on the library in `library.storage`. 
- Use new `data/history.json` database for rejected articles saving. 
  - Load `history.json` while filtering articles to prevent unnecessary llm calls.
  - Save `history.json` with LLM rejected articles while indexing database. 
- `OperonLogger::reading_progres()` and `OperonLogger::article()` for fancy article readning progress display. 
- Branch LLM on query generation from extracted keywords. 
- First working LangGraph loop.
- Implements `nodes.py`, `state.py` and `tools.py` for a first LangGraph model.

### Changed

- Create more structured StateGraph using `FetchState` and `SnowballState` derivating from a blobal `BaseLibraryState` for snowball_graph implementation.
- `library` architecture refactorign using `src/library` folder & dispatch `tool.py` functions into more specific files. 

### Fixed
