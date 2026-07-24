---
type: Table
title: chunks
description: The retrieval unit — chunk text, the contextual text that is embedded, the vector, and the Swedish full-text vector.
resource: postgres://chunks
tags: [data-model, table, chunks, retrieval, embedding]
timestamp: 2026-07-24T00:00:00Z
---

# `chunks`

The retrieval layer. Each chunk is a unit of search and retrieval.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| document_id | UUID | FK → [documents](/data-model/documents.md) |
| chunk_index | INTEGER | Position within document (ordering) |
| chunk_text | TEXT | Raw chunk content. Displayed in citations. |
| contextual_text | TEXT | Summary + chunk text. Used for embedding. Never shown to end users. |
| embedding | VECTOR(1024) | pgvector. Width is set by the embedding model — see [embedding dimension](/decisions/embedding-dimension.md) |
| tsv | TSVECTOR | Generated from `chunk_text` using the Swedish text search config. For BM25-style search. |
| created_at | TIMESTAMPTZ | Row creation |

`chunk_text` is what the user sees in citations; `contextual_text` (the document summary
prepended to the chunk) is what gets embedded and searched against, and is never shown
to end users. `tsv` is a `GENERATED ALWAYS ... STORED` column populated automatically at
insert time — see [design notes](/data-model/design-notes.md). Chunks are produced by
the [chunk worker](/pipeline/chunk.md) and vectors written by the
[embed worker](/pipeline/embed.md). Retrieval over this table is described in the
[retrieval agent](/retrieval/agent.md).
