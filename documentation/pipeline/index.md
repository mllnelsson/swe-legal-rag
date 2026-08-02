# Ingestion Pipeline

* [Ingestion Pipeline Overview](overview.md) - The queue-driven ingestion topology — seven Cloud Run workers connected by Pub/Sub topics, each checkpointing its output for resumability.
* [Crawl Worker](crawl.md) - One-shot pipeline entry point — queries the Svenska kyrkan OData API for decisions, deduplicates, and enqueues download tasks.
* [Download Worker](download.md) - Subscriber worker that fetches PDFs from source URLs, stores them via the storage backend, and enqueues parse tasks.
* [Parse Worker](parse.md) - Subscriber worker that extracts raw text from stored PDFs with pypdfium2 and enqueues metadata tasks.
* [Metadata Worker](metadata.md) - Subscriber worker that extracts structured metadata (case number, date, outcome, category) rule-based first with an LLM fallback for missing fields.
* [Extract Worker](extract.md) - Subscriber worker that extracts entities and cross-references from document text into the graph-in-Postgres tables, then enqueues chunk tasks.
* [Chunk Worker](chunk.md) - Subscriber worker that generates a document summary and splits text into overlapping token-bounded chunks with the summary prepended (contextual retrieval).
* [Embed Worker](embed.md) - Terminal pipeline worker that generates vector embeddings for a document's chunks and bulk-updates the chunks table.
* [Worker Architecture Patterns](worker-patterns.md) - The conventions every subscriber worker shares — the run_pipeline_step task envelope, the subscribe/serve startup split, injected trace scopes, and the commit-before-publish invariant.
