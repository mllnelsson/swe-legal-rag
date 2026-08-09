# Decisions

* [Architectural Decision Register](architectural-register.md) - The consolidated register of accepted system-shaping decisions — retrieval, storage, pipeline, data-layer, and library choices.
* [Per-task LLM model and provider selection](llm-model-selection.md) - Why each task gets its own model and provider, declared in llm_config.yaml rather than in environment variables or code.
* [Embedding model choice](embedding-model.md) - Why intfloat/multilingual-e5-large (1024 dims) was selected for Swedish retrieval.
* [Embedding model hosting](embedding-hosting.md) - Where the e5-large embedding model is hosted — Berget.ai hosted inference rather than any self-hosted option, selected per environment via llm_config.yaml, which ships defaulting to the in-process local fallback.
* [Embedding dimension coupling and startup verification](embedding-dimension.md) - Why EMBEDDING_MODEL and EMBEDDING_DIMENSION must change together, and how a startup check guards the mismatch.
* [Embedding sequence window is observed, not declared](embedding-window.md) - Why the chunk token budget is derived from the embedding model's own tokenizer and its observed sequence window rather than a hand-picked constant, and the arithmetic behind the 349-token chunk budget.
* [The crawl tag filter is mandatory](tag-filter.md) - Why the crawl query must filter on decision tags — without it the API returns every binary file on the web, not the decision corpus.
* [Appendices are labelled, not dropped](appendix-segmentation.md) - Why appended lower-instance decisions stay in the index with a section marker rather than being discarded or left undistinguished.
* [Body-first retrieval over one vector index](body-first-retrieval.md) - Why appendix scoping is a WHERE predicate on the existing HNSW index rather than a second index, and why it must be a hard filter rather than a ranking penalty.
* [Structural fields are parsed, not inferred](structural-fields-are-parsed.md) - Why case number, decision number, decision date, category, and lagrum citations are extracted by rule alone with no LLM fallback, and where LLM fallback is used instead.
* [Forced grounding for the text-to-SQL agent](sql-agent.md) - Why the SQL agent's predicates over free-text columns must be grounded against real column values before a query runs, why that precondition is enforced in code rather than left to the prompt, the rejected structured-query-DTO alternative, and the safety posture — including why no dedicated read-only database role was added.
