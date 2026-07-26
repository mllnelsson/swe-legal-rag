# Decisions

* [Architectural Decision Register](architectural-register.md) - The consolidated register of accepted system-shaping decisions — retrieval, storage, pipeline, data-layer, and library choices.
* [Embedding model choice](embedding-model.md) - Why intfloat/multilingual-e5-large (1024 dims) was selected for Swedish retrieval, and the tiktoken tokenizer used for chunk sizing.
* [Embedding model hosting](embedding-hosting.md) - Where the e5-large embedding model is hosted — Berget.ai hosted inference is the default, replacing any self-hosted option.
* [Embedding dimension coupling and startup verification](embedding-dimension.md) - Why EMBEDDING_MODEL and EMBEDDING_DIMENSION must change together, and how a startup check guards the mismatch.
* [The crawl tag filter is mandatory](tag-filter.md) - Why the crawl query must filter on decision tags — without it the API returns every binary file on the web, not the decision corpus.
* [Appendices are labelled, not dropped](appendix-segmentation.md) - Why appended lower-instance decisions stay in the index with a section marker rather than being discarded or left undistinguished.
* [Body-first retrieval over one vector index](body-first-retrieval.md) - Why appendix scoping is a WHERE predicate on the existing HNSW index rather than a second index, and why it must be a hard filter rather than a ranking penalty.
