---
type: Concept
title: Data Model Design Notes
description: Cross-cutting rationale behind the schema — progressive metadata, contextual text, idempotency, the graph-in-Postgres tables, and enum-backed columns.
tags: [data-model, design, rationale]
timestamp: 2026-08-02T00:00:00Z
---

# Data Model Design Notes

Cross-cutting notes that apply across the [tables](/data-model/documents.md). The
embedding vector width has its own record — see
[embedding dimension](/decisions/embedding-dimension.md).

## Generated tsvector column

`chunks.tsv` is a `GENERATED ALWAYS AS (to_tsvector('swedish', chunk_text)) STORED`
column. PostgreSQL computes and stores it automatically at INSERT time when `chunk_text`
is written (during the [chunk step](/pipeline/chunk.md)). The [embed
worker](/pipeline/embed.md) does not touch it — attempting to UPDATE a `GENERATED ALWAYS
STORED` column fails with a PostgreSQL error. Postgres supplies Swedish stemming and stop
words, so no application-side maintenance is needed.

## Finite-set columns stay `str`, values come from `StrEnum`

`tasks.step`/`status`, `entities.type`, and `document_entities.relevance` are
`VARCHAR`/`Mapped[str]`; their values are the `shared.enums` StrEnum members
(`PipelineStep`, `TaskStatus`, `EntityType`, `EntityRelevance`). Because a `StrEnum`
member is the exact stored text, adopting the enums needed **no migration**.

## Progressive metadata

Each pipeline step fills in its columns progressively. A document with `gcs_uri` set but
`raw_text` null means download succeeded but parsing hasn't run yet. Combined with
[tasks](/data-model/tasks.md) this gives full observability.

## `contextual_text` vs `chunk_text`

Stored separately. `chunk_text` is what the user sees in citations. `contextual_text`
(document summary prepended via `summary\n\n---\n\nchunk_text`) is what gets embedded and
searched against. Never shown to end users.

## Idempotency pattern

Re-processing a document deletes existing chunks before re-inserting (DELETE+INSERT).
Embeddings are updated in-place via UPDATE on the `embedding` column — no chunk rows are
recreated. There are **no soft deletes**: to reprocess a document, wipe its chunks and
reset its tasks. Simple at this scale.

## Chunk sizing rationale

The chunk token budget is **derived**, not hand-picked: it is the embedding model's
sequence window (512 for e5-large) minus the fixed overhead every chunk carries into
embedding — special tokens, the passage prefix, the prepended summary's reserve, the
separator, and a safety margin — leaving **349 tokens** for chunk text at a 34-token
overlap. This is a hard ceiling, not a granularity choice: past it,
`sentence-transformers` truncates the embedding input silently, and the tail of the chunk
never reaches its vector. See [embedding window](/decisions/embedding-window.md) for the
full arithmetic and why the window is observed from the tokenizer rather than declared as
a constant. Sentence-aware boundaries prevent mid-sentence splits; overlap is a fixed
share (10%) of the budget so it tracks the budget rather than drifting independently of
it — see [chunk worker](/pipeline/chunk.md).

## Task-queue alignment

When a pipeline step publishes to the next Pub/Sub topic, it also inserts a `pending`
[task](/data-model/tasks.md) row for the next step. The consuming worker updates that row
through its lifecycle (see [worker patterns](/pipeline/worker-patterns.md)).

## Listing metadata persisted at crawl time

The Svenska kyrkan OData listing supplies `documentId`, `headline` and `publishDate` for
free, so they are stored rather than discarded. `source_document_id` gives a stable
numeric identity that survives file renames and backs a second unique constraint;
`source_headline` and `source_published_at` let the metadata step cross-check the case
number and date it extracts from the PDF text. All three are nullable so rows created by
the earlier HTML scraper survive — Postgres allows repeated NULLs under a UNIQUE
constraint, so those legacy rows do not collide. See
[crawl source](/reference/crawl-source.md).

## Graph-in-Postgres

The [entities](/data-model/entities.md),
[document_entities](/data-model/document-entities.md), and
[document_references](/data-model/document-references.md) tables capture GraphRAG
concepts without a graph database. The [agent](/retrieval/agent.md) uses these for
entity-based pre-filtering (e.g. "find all documents where entity X is primary → semantic
search within that set") and relationship traversal ("what other decisions cite this
one?"). Standard SQL joins replace graph queries at this scale — see the rationale in the
[architectural register](/decisions/architectural-register.md).

## Unresolved references

Cross-references where the target is not yet in the corpus are stored in
[unresolved_references](/data-model/unresolved-references.md) rather than dropped.
Reconciliation happens automatically when the target document is ingested (the [extract
worker](/pipeline/extract.md)'s `reconcile_references()`). This keeps
`document_references.target_document_id` a non-nullable FK without loss of reference data.
