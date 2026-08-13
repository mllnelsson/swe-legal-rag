# Data Model

## Tables

* [documents](documents.md) - The document registry — one row per PDF, tracking both identity and progressive ingestion state.
* [tasks](tasks.md) - One row per document per pipeline step — the unit of work that queue messages map to 1:1.
* [chunks](chunks.md) - The retrieval unit — chunk text, the contextual text that is embedded, the vector, and the Swedish full-text vector.
* [entities](entities.md) - Extracted legal concepts, roles, parishes, regulations, and declared keywords — the nodes of the in-Postgres knowledge graph.
* [document_entities](document-entities.md) - Junction table mapping entities to documents with a relevance weight (primary or mentioned).
* [document_references](document-references.md) - Resolved cross-citations between decisions — one decision citing another as precedent.
* [unresolved_references](unresolved-references.md) - Lazy-resolution store for citations whose target decision is not yet in the corpus.
* [sessions](sessions.md) - Conversation history backing the chat endpoint's follow-up support; holds the question and the answer only, never the evidence a turn gathered.

## Cross-cutting

* [Indexes](indexes.md) - The index catalog across all tables — HNSW/GIN for retrieval, btree for constraints and lookups.
* [Repository Layer](repositories.md) - The function-based data-access layer bridging SQLAlchemy models and Pydantic DTOs, injected into services as Protocol-typed namespaces.
* [Data Model Design Notes](design-notes.md) - Cross-cutting rationale behind the schema — progressive metadata, contextual text, idempotency, the graph-in-Postgres tables, and enum-backed columns.
